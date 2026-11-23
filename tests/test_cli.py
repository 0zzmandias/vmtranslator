"""Testes de integração e linha de comando (CLI) da Parte 1."""

from pathlib import Path
import re

import pytest

from main import CLIError, main, resolve_io, translate


def test_cli_translates_complete_part1_program(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "FullPart1.vm"
    vm_file.write_text(
        "// Programa completo de integração Parte 1\n"
        "push constant 10\n"
        "pop local 0\n"
        "push constant 21\n"
        "push constant 22\n"
        "pop argument 2\n"
        "pop argument 1\n"
        "push constant 3030\n"
        "pop pointer 0\n"
        "push constant 510\n"
        "pop temp 6\n"
        "push constant 111\n"
        "pop static 8\n"
        "push local 0\n"
        "push static 8\n"
        "eq\n"
        "push argument 1\n"
        "push temp 6\n"
        "sub\n"
        "neg\n"
        "not\n"
        "and\n"
        "push pointer 0\n"
        "or\n",
        encoding="utf-8",
    )

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""

    asm_file = tmp_path / "FullPart1.asm"
    assert asm_file.exists()

    content = asm_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert "// push constant 10" in lines
    assert "// pop local 0" in lines
    assert "@R13" in lines
    assert "@FullPart1.8" in lines
    assert "@11" in lines
    assert "@THIS" in lines
    assert "@256" not in content

    declared_labels = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\(([^)]+)\)", line))
    ]
    assert len(declared_labels) == len(set(declared_labels))


def test_cli_handles_empty_and_comment_only_vm_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty_vm = tmp_path / "Empty.vm"
    empty_vm.write_text("", encoding="utf-8")

    comments_vm = tmp_path / "OnlyComments.vm"
    comments_vm.write_text("// nada executável\n   \n// fim\n", encoding="utf-8")

    assert main([str(empty_vm)]) == 0
    assert main([str(comments_vm)]) == 0
    assert capsys.readouterr().err == ""

    assert (tmp_path / "Empty.asm").read_text(encoding="utf-8") == ""
    assert (tmp_path / "OnlyComments.asm").read_text(encoding="utf-8") == ""


@pytest.mark.parametrize("argv", [[], ["a.vm", "b.vm"]])
def test_cli_wrong_argument_count_returns_nonzero(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(argv)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Uso:" in captured.err


def test_resolve_io_rejects_blank_input() -> None:
    with pytest.raises(CLIError, match="não informado"):
        resolve_io("   ")


def test_cli_rejects_nonexistent_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "Missing.vm"
    exit_code = main([str(missing)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "não encontrado" in captured.err


def test_cli_rejects_directory_in_part1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "diretório" in captured.err


@pytest.mark.parametrize("filename", ["Program.txt", "Program"])
def test_cli_rejects_non_vm_extension(
    tmp_path: Path,
    filename: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid_file = tmp_path / filename
    invalid_file.write_text("add\n", encoding="utf-8")

    exit_code = main([str(invalid_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Extensão inválida" in captured.err
    assert not invalid_file.with_suffix(".asm").exists()


def test_cli_removes_partial_asm_on_syntax_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "SyntaxFail.vm"
    vm_file.write_text("push constant 7\ninvalid_cmd\n", encoding="utf-8")
    asm_file = tmp_path / "SyntaxFail.asm"

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "SyntaxFail.vm:2:" in captured.err
    assert not asm_file.exists()


def test_cli_removes_partial_asm_on_semantic_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "SemanticFail.vm"
    vm_file.write_text("push constant 7\npop constant 0\n", encoding="utf-8")
    asm_file = tmp_path / "SemanticFail.asm"

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "constant" in captured.err
    assert not asm_file.exists()


def test_cli_removes_partial_asm_on_invalid_utf8(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "BadBytes.vm"
    vm_file.write_bytes(b"\xff\xfe\xfd")
    asm_file = tmp_path / "BadBytes.asm"

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "UTF-8" in captured.err
    assert not asm_file.exists()


def test_translate_returns_generated_asm_path(tmp_path: Path) -> None:
    vm_file = tmp_path / "ReturnPath.vm"
    vm_file.write_text("push constant 1\npush constant 2\nadd\n", encoding="utf-8")

    output_path = translate(str(vm_file))

    assert output_path == tmp_path / "ReturnPath.asm"
    assert output_path.is_file()
