"""Testes unitários abrangentes do módulo parser (Parte 1)."""

import os
from pathlib import Path
import stat

import pytest

from parser import CommandType, Parser, ParserError


def _write_vm(tmp_path: Path, content: str, name: str = "Sample.vm") -> Path:
    vm_file = tmp_path / name
    vm_file.write_text(content, encoding="utf-8")
    return vm_file


@pytest.mark.parametrize(
    "command",
    ["add", "sub", "neg", "eq", "gt", "lt", "and", "or", "not"],
)
def test_parse_all_arithmetic_commands(tmp_path: Path, command: str) -> None:
    vm_file = _write_vm(tmp_path, f"{command}\n")
    vm_parser = Parser(vm_file)

    assert vm_parser.hasMoreCommands() is True
    vm_parser.advance()
    assert vm_parser.commandType() == CommandType.C_ARITHMETIC
    assert vm_parser.arg1() == command
    assert vm_parser.current_line_number == 1
    assert vm_parser.hasMoreCommands() is False


@pytest.mark.parametrize(
    ("segment", "index"),
    [
        ("constant", 0),
        ("constant", 32767),
        ("local", 0),
        ("argument", 2),
        ("this", 6),
        ("that", 5),
        ("temp", 7),
        ("pointer", 1),
        ("static", 8),
    ],
)
def test_parse_push_and_pop_all_segments(
    tmp_path: Path,
    segment: str,
    index: int,
) -> None:
    vm_file = _write_vm(
        tmp_path,
        f"push {segment} {index}\npop {segment} {index}\n",
    )
    vm_parser = Parser(vm_file)

    vm_parser.advance()
    assert vm_parser.commandType() == CommandType.C_PUSH
    assert vm_parser.arg1() == segment
    assert vm_parser.arg2() == index
    assert vm_parser.current_line_number == 1

    vm_parser.advance()
    assert vm_parser.commandType() == CommandType.C_POP
    assert vm_parser.arg1() == segment
    assert vm_parser.arg2() == index
    assert vm_parser.current_line_number == 2
    assert vm_parser.hasMoreCommands() is False


def test_empty_file_has_no_commands(tmp_path: Path) -> None:
    vm_file = _write_vm(tmp_path, "")
    vm_parser = Parser(vm_file)

    assert vm_parser.hasMoreCommands() is False


def test_comments_and_whitespace_only_file_has_no_commands(tmp_path: Path) -> None:
    content = (
        "// comentario inicial\n"
        "   \t   \n"
        "   // comentario indentado\r\n"
        "\r\n"
        "//// barras extras\n"
    )
    vm_file = _write_vm(tmp_path, content)
    vm_parser = Parser(vm_file)

    assert vm_parser.hasMoreCommands() is False


def test_handles_crlf_tabs_extra_spaces_and_attached_comments(tmp_path: Path) -> None:
    content = (
        "// cabecalho\r\n"
        "\r\n"
        "  \t push   constant\t7//comentario colado\r\n"
        "\tpush\t\tconstant    8   // comentario com espacos\n"
        "add//soma final\r\n"
    )
    vm_file = tmp_path / "Formatting.vm"
    vm_file.write_bytes(content.encode("utf-8"))

    vm_parser = Parser(vm_file)
    parsed = []
    while vm_parser.hasMoreCommands():
        vm_parser.advance()
        cmd_type = vm_parser.commandType()
        arg2 = vm_parser.arg2() if cmd_type != CommandType.C_ARITHMETIC else None
        parsed.append((vm_parser.current_line_number, cmd_type, vm_parser.arg1(), arg2))

    assert parsed == [
        (3, CommandType.C_PUSH, "constant", 7),
        (4, CommandType.C_PUSH, "constant", 8),
        (5, CommandType.C_ARITHMETIC, "add", None),
    ]


@pytest.mark.parametrize(
    ("bad_line", "expected_fragment"),
    [
        ("mul", "desconhecido"),
        ("ADD", "desconhecido"),
        ("add 1", "espera 0 argumento(s)"),
        ("neg extra", "espera 0 argumento(s)"),
        ("push", "espera 2 argumento(s)"),
        ("push constant", "espera 2 argumento(s)"),
        ("push constant 7 8", "espera 2 argumento(s)"),
        ("pop local", "espera 2 argumento(s)"),
        ("pop local 1 2", "espera 2 argumento(s)"),
        ("push constant -1", "inteiro não negativo"),
        ("push constant 3.14", "inteiro não negativo"),
        ("push constant 0x10", "inteiro não negativo"),
        ("push constant abc", "inteiro não negativo"),
        ("push constant +5", "inteiro não negativo"),
        ("push constant ²", "inteiro não negativo"),
    ],
)
def test_syntax_errors_report_file_and_line(
    tmp_path: Path,
    bad_line: str,
    expected_fragment: str,
) -> None:
    content = f"// linha 1\npush constant 1\n{bad_line}\n"
    vm_file = _write_vm(tmp_path, content, name="Broken.vm")

    with pytest.raises(ParserError) as exc_info:
        Parser(vm_file)

    error = exc_info.value
    assert error.line_number == 3
    assert error.filename == str(vm_file)
    assert "Broken.vm:3:" in str(error)
    assert expected_fragment in str(error)


def test_accessing_command_before_advance_raises_error(tmp_path: Path) -> None:
    vm_file = _write_vm(tmp_path, "add\n")
    vm_parser = Parser(vm_file)

    with pytest.raises(ParserError, match="advance"):
        vm_parser.commandType()
    with pytest.raises(ParserError, match="advance"):
        vm_parser.arg1()
    with pytest.raises(ParserError, match="advance"):
        vm_parser.arg2()
    with pytest.raises(ParserError, match="advance"):
        _ = vm_parser.current_line_number


def test_advance_past_end_raises_error(tmp_path: Path) -> None:
    vm_file = _write_vm(tmp_path, "add\n")
    vm_parser = Parser(vm_file)
    vm_parser.advance()

    with pytest.raises(ParserError, match="Não há mais comandos"):
        vm_parser.advance()


def test_arg2_on_arithmetic_command_raises_error(tmp_path: Path) -> None:
    vm_file = _write_vm(tmp_path, "sub\n")
    vm_parser = Parser(vm_file)
    vm_parser.advance()

    with pytest.raises(ParserError, match="não possui arg2"):
        vm_parser.arg2()


def test_nonexistent_file_raises_parser_error(tmp_path: Path) -> None:
    missing = tmp_path / "DoesNotExist.vm"

    with pytest.raises(ParserError, match="não encontrado"):
        Parser(missing)


def test_directory_path_raises_parser_error(tmp_path: Path) -> None:
    with pytest.raises(ParserError, match="diretório"):
        Parser(tmp_path)


def test_invalid_utf8_file_raises_parser_error(tmp_path: Path) -> None:
    vm_file = tmp_path / "BadEncoding.vm"
    vm_file.write_bytes(b"\xff\xfe\x00\x01")

    with pytest.raises(ParserError, match="UTF-8"):
        Parser(vm_file)


@pytest.mark.skipif(os.geteuid() == 0, reason="Root ignora restrições de chmod.")
def test_unreadable_file_raises_parser_error(tmp_path: Path) -> None:
    vm_file = _write_vm(tmp_path, "add\n", name="NoRead.vm")
    vm_file.chmod(0)
    try:
        with pytest.raises(ParserError, match="permissão"):
            Parser(vm_file)
    finally:
        vm_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
