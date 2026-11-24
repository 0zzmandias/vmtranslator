"""Testes unitários abrangentes do módulo parser (Parte 2)."""

from pathlib import Path
import sys

import pytest

from parser import CommandType, Parser, ParserError


def _write_vm(tmp_path: Path, content: str, name: str = "Part2.vm") -> Path:
    vm_file = tmp_path / name
    vm_file.write_text(content, encoding="utf-8")
    return vm_file


@pytest.mark.parametrize(
    ("keyword", "expected_type", "label"),
    [
        ("label", CommandType.C_LABEL, "LOOP"),
        ("goto", CommandType.C_GOTO, "END_LOOP"),
        ("if-goto", CommandType.C_IF, "Main.step_1:ok"),
    ],
)
def test_parse_program_flow_commands(
    tmp_path: Path,
    keyword: str,
    expected_type: CommandType,
    label: str,
) -> None:
    vm_file = _write_vm(tmp_path, f"  {keyword}\t{label} // controle de fluxo\n")
    vm_parser = Parser(vm_file)

    assert vm_parser.hasMoreCommands() is True
    vm_parser.advance()
    assert vm_parser.commandType() == expected_type
    assert vm_parser.arg1() == label
    assert vm_parser.current_line_number == 1
    assert vm_parser.hasMoreCommands() is False


@pytest.mark.parametrize(
    ("keyword", "expected_type", "func_name", "count"),
    [
        ("function", CommandType.C_FUNCTION, "SimpleFunction.test", 0),
        ("function", CommandType.C_FUNCTION, "Sys.init", 2),
        ("function", CommandType.C_FUNCTION, "Math.mul", 32767),
        ("call", CommandType.C_CALL, "Sys.init", 0),
        ("call", CommandType.C_CALL, "Main.fibonacci", 1),
        ("call", CommandType.C_CALL, "Class1.set", 2),
    ],
)
def test_parse_function_and_call_commands(
    tmp_path: Path,
    keyword: str,
    expected_type: CommandType,
    func_name: str,
    count: int,
) -> None:
    vm_file = _write_vm(tmp_path, f"{keyword} {func_name} {count}\r\n")
    vm_parser = Parser(vm_file)

    vm_parser.advance()
    assert vm_parser.commandType() == expected_type
    assert vm_parser.arg1() == func_name
    assert vm_parser.arg2() == count
    assert vm_parser.hasMoreCommands() is False


def test_parse_return_command(tmp_path: Path) -> None:
    vm_file = _write_vm(tmp_path, "  return//fim\n")
    vm_parser = Parser(vm_file)

    vm_parser.advance()
    assert vm_parser.commandType() == CommandType.C_RETURN
    assert vm_parser.current_line_number == 1
    assert vm_parser.hasMoreCommands() is False


def test_arg1_and_arg2_on_return_raise_parser_error(tmp_path: Path) -> None:
    vm_file = _write_vm(tmp_path, "return\n")
    vm_parser = Parser(vm_file)
    vm_parser.advance()

    with pytest.raises(ParserError, match="não possui arg1"):
        vm_parser.arg1()
    with pytest.raises(ParserError, match="não possui arg2"):
        vm_parser.arg2()


@pytest.mark.parametrize("line", ["label L1", "goto L1", "if-goto L1"])
def test_arg2_on_program_flow_commands_raises_parser_error(
    tmp_path: Path,
    line: str,
) -> None:
    vm_file = _write_vm(tmp_path, f"{line}\n")
    vm_parser = Parser(vm_file)
    vm_parser.advance()

    with pytest.raises(ParserError, match="não possui arg2"):
        vm_parser.arg2()


@pytest.mark.parametrize(
    ("bad_line", "expected_fragment"),
    [
        ("label", "espera 1 argumento(s)"),
        ("label A B", "espera 1 argumento(s)"),
        ("goto", "espera 1 argumento(s)"),
        ("goto A B", "espera 1 argumento(s)"),
        ("if-goto", "espera 1 argumento(s)"),
        ("if-goto A B", "espera 1 argumento(s)"),
        ("function", "espera 2 argumento(s)"),
        ("function Main.f", "espera 2 argumento(s)"),
        ("function Main.f 1 2", "espera 2 argumento(s)"),
        ("call", "espera 2 argumento(s)"),
        ("call Main.f", "espera 2 argumento(s)"),
        ("call Main.f 1 2", "espera 2 argumento(s)"),
        ("return 0", "espera 0 argumento(s)"),
        ("label 1LOOP", "Identificador inválido"),
        ("goto BAD$LABEL", "Identificador inválido"),
        ("if-goto bad-label", "Identificador inválido"),
        ("function 9Func 0", "Identificador inválido"),
        ("call Foo$Bar 1", "Identificador inválido"),
        ("function Main.f -1", "inteiro não negativo"),
        ("function Main.f abc", "inteiro não negativo"),
        ("call Main.f -2", "inteiro não negativo"),
        ("call Main.f 1.5", "inteiro não negativo"),
        ("call Main.f +1", "inteiro não negativo"),
    ],
)
def test_part2_syntax_errors_report_file_and_line(
    tmp_path: Path,
    bad_line: str,
    expected_fragment: str,
) -> None:
    content = f"// linha 1\nfunction Main.ok 0\n{bad_line}\n"
    vm_file = _write_vm(tmp_path, content, name="BrokenPart2.vm")

    with pytest.raises(ParserError) as exc_info:
        Parser(vm_file)

    error = exc_info.value
    assert error.line_number == 3
    assert error.filename == str(vm_file)
    assert "BrokenPart2.vm:3:" in str(error)
    assert expected_fragment in str(error)


@pytest.mark.parametrize("command_prefix", ["function Main.f", "call Main.f"])
def test_oversized_numeric_argument_raises_contextual_parser_error(
    tmp_path: Path,
    command_prefix: str,
) -> None:
    token = "9" * 4301
    vm_file = _write_vm(tmp_path, f"// comentario\n\n{command_prefix} {token}\n")
    previous_limit = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(4300)
        with pytest.raises(ParserError) as exc_info:
            Parser(vm_file)
    finally:
        sys.set_int_max_str_digits(previous_limit)

    error = exc_info.value
    assert error.filename == str(vm_file)
    assert error.line_number == 3
    assert f"{vm_file}:3:" in str(error)
    assert f"'{command_prefix.split()[0]}'" in str(error)
    assert "conversão" in str(error)
    assert isinstance(error.__cause__, ValueError)
    assert token not in str(error)
