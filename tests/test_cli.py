"""Testes de integração e linha de comando (CLI) da Parte 1."""

import errno
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import pytest

from codewriter import CodeWriter
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


@pytest.mark.parametrize(
    "vm_content",
    [
        "push constant 7\ninvalid_cmd\n",
        "push constant 7\npop constant 0\n",
    ],
)
def test_cli_preserves_existing_asm_and_cleans_temp_on_analysis_or_generation_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    vm_content: str,
) -> None:
    vm_file = tmp_path / "Preserve.vm"
    vm_file.write_text(vm_content, encoding="utf-8")
    asm_file = tmp_path / "Preserve.asm"
    previous_content = "// versao valida anterior\n@0\n"
    asm_file.write_text(previous_content, encoding="utf-8")

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err != ""
    assert asm_file.read_text(encoding="utf-8") == previous_content
    assert {entry.name for entry in tmp_path.iterdir()} == {
        "Preserve.vm",
        "Preserve.asm",
    }


def test_cli_preserves_existing_asm_and_cleans_temp_on_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "CloseFail.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = tmp_path / "CloseFail.asm"
    previous_content = "// versao valida anterior\n@1\n"
    asm_file.write_text(previous_content, encoding="utf-8")

    original_close = CodeWriter.close

    def failing_close(self: CodeWriter) -> None:
        original_close(self)
        raise OSError("falha simulada no close")

    monkeypatch.setattr(CodeWriter, "close", failing_close)

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "falha simulada no close" in captured.err
    assert asm_file.read_text(encoding="utf-8") == previous_content
    assert {entry.name for entry in tmp_path.iterdir()} == {
        "CloseFail.vm",
        "CloseFail.asm",
    }


def test_cli_preserves_existing_asm_and_cleans_temp_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "ReplaceFail.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = tmp_path / "ReplaceFail.asm"
    previous_content = "// versao valida anterior\n@2\n"
    asm_file.write_text(previous_content, encoding="utf-8")

    def failing_replace(src: Path | str, dst: Path | str) -> None:
        raise OSError("falha simulada no replace")

    monkeypatch.setattr("main.cli.os.replace", failing_replace)

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "falha simulada no replace" in captured.err
    assert asm_file.read_text(encoding="utf-8") == previous_content
    assert {entry.name for entry in tmp_path.iterdir()} == {
        "ReplaceFail.vm",
        "ReplaceFail.asm",
    }


def test_cli_replaces_existing_asm_and_leaves_no_temp_on_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "ReplaceSuccess.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = tmp_path / "ReplaceSuccess.asm"
    asm_file.write_text("// versao antiga\n", encoding="utf-8")

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    new_content = asm_file.read_text(encoding="utf-8")
    assert "// push constant 42" in new_content
    assert "// versao antiga" not in new_content
    assert {entry.name for entry in tmp_path.iterdir()} == {
        "ReplaceSuccess.vm",
        "ReplaceSuccess.asm",
    }


def test_cli_rejects_function_and_static_symbol_collision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "Foo.vm"
    vm_file.write_text(
        "function Foo.0 0\n"
        "push static 0\n"
        "return\n",
        encoding="utf-8",
    )

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "colisão" in captured.err
    assert "Foo.0" in captured.err
    assert not (tmp_path / "Foo.asm").exists()


@pytest.mark.parametrize(
    ("content", "expected_symbol"),
    [
        (
            "function Dup.f 0\nreturn\nfunction Dup.f 0\nreturn\n",
            "Dup.f",
        ),
        (
            "function Main.f 0\nlabel LOOP\nlabel LOOP\nreturn\n",
            "Main.f$LOOP",
        ),
    ],
)
def test_cli_rejects_duplicate_function_and_label_definitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    content: str,
    expected_symbol: str,
) -> None:
    vm_file = tmp_path / "DuplicateDef.vm"
    vm_file.write_text(content, encoding="utf-8")

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "definição duplicada" in captured.err
    assert expected_symbol in captured.err
    assert not (tmp_path / "DuplicateDef.asm").exists()


@pytest.mark.parametrize("command", ["function", "call"])
@pytest.mark.parametrize(
    "predefined",
    ["SP", "LCL", "ARG", "THIS", "THAT", "SCREEN", "KBD"]
    + [f"R{i}" for i in range(16)],
)
def test_cli_rejects_predefined_hack_function_symbol(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    predefined: str,
    command: str,
) -> None:
    vm_file = tmp_path / "PredefinedCollision.vm"
    vm_file.write_text(
        f"{command} {predefined} 0\n"
        "return\n",
        encoding="utf-8",
    )

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert f"{vm_file}:1:" in captured.err
    assert "predefinido" in captured.err
    assert predefined in captured.err
    assert not (tmp_path / "PredefinedCollision.asm").exists()


def test_cli_allows_repeated_calls_gotos_and_static_accesses(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "RepeatedRefs.vm"
    vm_file.write_text(
        "function Main.ok 0\n"
        "push constant 1\n"
        "pop static 0\n"
        "push static 0\n"
        "pop static 0\n"
        "call Helper.step 0\n"
        "call Helper.step 0\n"
        "label LOOP\n"
        "goto LOOP\n"
        "push constant 0\n"
        "if-goto LOOP\n"
        "return\n",
        encoding="utf-8",
    )

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert (tmp_path / "RepeatedRefs.asm").is_file()


def test_cli_skips_reserved_return_and_comparison_labels_declared_later(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "LaterCollision.vm"
    vm_file.write_text(
        "function Main.f 0\n"
        "call Other.g 0\n"
        "label ret.0\n"
        "push constant 1\n"
        "push constant 1\n"
        "eq\n"
        "return\n"
        "function VM_EQ_TRUE_2 0\n"
        "return\n",
        encoding="utf-8",
    )

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""

    lines = (tmp_path / "LaterCollision.asm").read_text(encoding="utf-8").splitlines()
    assert "@Main.f$ret.1" in lines
    assert "(Main.f$ret.1)" in lines
    assert "@Main.f$ret.0" not in lines
    assert lines.count("(Main.f$ret.0)") == 1
    assert "(VM_EQ_TRUE_3)" in lines
    assert "(VM_EQ_END_3)" in lines
    assert "(VM_EQ_END_2)" not in lines
    assert lines.count("(VM_EQ_TRUE_2)") == 1

    declared_labels = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\(([^)]+)\)", line))
    ]
    assert len(declared_labels) == len(set(declared_labels))


def test_translate_returns_generated_asm_path(tmp_path: Path) -> None:
    vm_file = tmp_path / "ReturnPath.vm"
    vm_file.write_text("push constant 1\npush constant 2\nadd\n", encoding="utf-8")

    output_path = translate(str(vm_file))

    assert output_path == tmp_path / "ReturnPath.asm"
    assert output_path.is_file()


@pytest.mark.parametrize("filename", ["Module.vm", "Sys.vm"])
def test_single_file_allows_unresolved_external_function(
    tmp_path: Path,
    filename: str,
) -> None:
    vm_file = tmp_path / filename
    vm_file.write_text(
        "function Module.run 0\n"
        "push constant 2\n"
        "push constant 3\n"
        "call Math.multiply 2\n"
        "return\n",
        encoding="utf-8",
    )

    lines = translate(str(vm_file)).read_text(encoding="utf-8").splitlines()
    assert "@Math.multiply" in lines
    assert "(Math.multiply)" not in lines
    assert "// bootstrap" not in lines


@pytest.mark.parametrize(
    "command_prefix",
    ["push constant", "pop local", "function Main.f", "call Main.f"],
)
@pytest.mark.parametrize("existing_output", [False, True])
def test_cli_reports_oversized_numeric_argument_without_traceback(
    tmp_path: Path,
    command_prefix: str,
    existing_output: bool,
) -> None:
    vm_file = tmp_path / "Oversized.vm"
    token = "9" * 4301
    vm_file.write_text(
        f"// comentario\n\n{command_prefix} {token}\n",
        encoding="utf-8",
    )
    asm_file = vm_file.with_suffix(".asm")
    previous_content = b"// assembly anterior\n@256\n"
    if existing_output:
        asm_file.write_bytes(previous_content)

    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "int_max_str_digits=4300",
            "-c",
            "from main import main; raise SystemExit(main())",
            str(vm_file),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert f"Erro: {vm_file}:3:" in result.stderr
    assert f"'{command_prefix.split()[0]}'" in result.stderr
    assert "conversão" in result.stderr
    assert "Traceback" not in result.stderr
    assert token not in result.stderr
    if existing_output:
        assert asm_file.read_bytes() == previous_content
    else:
        assert not asm_file.exists()
    expected_files = {vm_file.name, asm_file.name} if existing_output else {vm_file.name}
    assert {entry.name for entry in tmp_path.iterdir()} == expected_files


@pytest.mark.parametrize("value", [32767, 32768])
def test_cli_preserves_constant_15bit_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    value: int,
) -> None:
    vm_file = tmp_path / "ConstantLimit.vm"
    vm_file.write_text(f"push constant {value}\n", encoding="utf-8")
    asm_file = vm_file.with_suffix(".asm")

    exit_code = main([str(vm_file)])
    captured = capsys.readouterr()
    if value == 32767:
        assert exit_code == 0
        assert captured.err == ""
        assert "@32767" in asm_file.read_text(encoding="utf-8").splitlines()
    else:
        assert exit_code == 1
        assert "15 bits" in captured.err
        assert not asm_file.exists()


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o600, 0o1640])
def test_cli_preserves_existing_asm_permission_bits(
    tmp_path: Path,
    mode: int,
) -> None:
    vm_file = tmp_path / "Permissions.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = vm_file.with_suffix(".asm")
    asm_file.write_text("// versao anterior\n", encoding="utf-8")
    asm_file.chmod(mode)
    assert stat.S_IMODE(asm_file.stat().st_mode) == mode

    previous_umask = os.umask(0o077)
    try:
        assert translate(str(vm_file)) == asm_file
        assert os.umask(0o077) == 0o077
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(asm_file.stat().st_mode) == mode & 0o777
    assert "// push constant 42" in asm_file.read_text(encoding="utf-8")
    assert {entry.name for entry in tmp_path.iterdir()} == {vm_file.name, asm_file.name}


@pytest.mark.parametrize(
    ("mask", "expected_mode"),
    [(0o022, 0o644), (0o077, 0o600), (0o777, 0o000)],
)
def test_cli_new_asm_respects_umask_and_restores_it(
    tmp_path: Path,
    mask: int,
    expected_mode: int,
) -> None:
    vm_file = tmp_path / "NewPermissions.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = vm_file.with_suffix(".asm")

    previous_umask = os.umask(mask)
    try:
        assert translate(str(vm_file)) == asm_file
        assert os.umask(mask) == mask
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(asm_file.stat().st_mode) == expected_mode
    # O modo 0000 impede a leitura por um usuário comum.
    if expected_mode == 0:
        asm_file.chmod(0o600)
    assert "// push constant 42" in asm_file.read_text(encoding="utf-8")
    assert {entry.name for entry in tmp_path.iterdir()} == {vm_file.name, asm_file.name}


def test_cli_preserves_existing_asm_on_output_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "StatFail.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = vm_file.with_suffix(".asm")
    previous_content = b"// assembly anterior\n@256\n"
    asm_file.write_bytes(previous_content)
    asm_file.chmod(0o640)
    original_stat = Path.stat

    def failing_stat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        if path == asm_file:
            raise PermissionError("falha simulada no stat da saída")
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", failing_stat)
        assert main([str(vm_file)]) == 1

    assert "falha simulada no stat" in capsys.readouterr().err
    assert asm_file.read_bytes() == previous_content
    assert stat.S_IMODE(asm_file.stat().st_mode) == 0o640
    assert {entry.name for entry in tmp_path.iterdir()} == {vm_file.name, asm_file.name}


@pytest.mark.parametrize("existing_output", [False, True])
def test_cli_cleans_temp_and_preserves_output_on_chmod_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing_output: bool,
) -> None:
    vm_file = tmp_path / "ChmodFail.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = vm_file.with_suffix(".asm")
    previous_content = b"// assembly anterior\n@256\n"
    if existing_output:
        asm_file.write_bytes(previous_content)
        asm_file.chmod(0o640)

    def failing_chmod(path: Path, mode: int) -> None:
        assert path.parent == tmp_path
        assert path.suffix == ".tmp"
        assert "// push constant 42" in path.read_text(encoding="utf-8")
        raise OSError("falha simulada no chmod do temporário")

    previous_umask = os.umask(0o777)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "chmod", failing_chmod)
            assert main([str(vm_file)]) == 1
        assert os.umask(0o777) == 0o777
    finally:
        os.umask(previous_umask)

    assert "falha simulada no chmod" in capsys.readouterr().err
    if existing_output:
        assert asm_file.read_bytes() == previous_content
        assert stat.S_IMODE(asm_file.stat().st_mode) == 0o640
    else:
        assert not asm_file.exists()
    expected_files = {vm_file.name, asm_file.name} if existing_output else {vm_file.name}
    assert {entry.name for entry in tmp_path.iterdir()} == expected_files


def test_cli_closes_descriptor_and_cleans_temp_on_fchmod_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vm_file = tmp_path / "FchmodFail.vm"
    vm_file.write_text("push constant 42\n", encoding="utf-8")
    asm_file = vm_file.with_suffix(".asm")
    previous_content = b"// assembly anterior\n@256\n"
    asm_file.write_bytes(previous_content)
    asm_file.chmod(0o640)
    descriptors: list[int] = []

    def failing_fchmod(fd: int, mode: int) -> None:
        descriptors.append(fd)
        raise OSError("falha simulada no fchmod do temporário")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fchmod", failing_fchmod)
        assert main([str(vm_file)]) == 1
        assert len(descriptors) == 1
        with pytest.raises(OSError) as exc_info:
            os.fstat(descriptors[0])
        assert exc_info.value.errno == errno.EBADF

    assert "falha simulada no fchmod" in capsys.readouterr().err
    assert asm_file.read_bytes() == previous_content
    assert stat.S_IMODE(asm_file.stat().st_mode) == 0o640
    assert {entry.name for entry in tmp_path.iterdir()} == {vm_file.name, asm_file.name}
