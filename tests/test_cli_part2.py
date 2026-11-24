"""Testes de integração e linha de comando (CLI) da Parte 2."""

import os
from pathlib import Path
import re
import stat

import pytest

from codewriter import CodeWriter
from main import CLIError, main, resolve_io, translate


def test_single_file_never_emits_bootstrap_even_if_named_sys_vm(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sys_vm = tmp_path / "Sys.vm"
    sys_vm.write_text(
        "function Sys.init 0\n"
        "label LOOP\n"
        "goto LOOP\n",
        encoding="utf-8",
    )

    files, output_path, should_bootstrap = resolve_io(str(sys_vm))
    assert files == [sys_vm]
    assert output_path == tmp_path / "Sys.asm"
    assert should_bootstrap is False

    assert main([str(sys_vm)]) == 0
    assert capsys.readouterr().err == ""

    content = output_path.read_text(encoding="utf-8")
    assert "// bootstrap" not in content
    assert "@256" not in content
    assert "(Sys.init)" in content
    assert "(Sys.init$LOOP)" in content


def test_directory_without_sys_vm_translates_in_sorted_order_without_bootstrap(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "NoSysProj"
    proj_dir.mkdir()
    (proj_dir / "Beta.vm").write_text(
        "function Beta.run 0\npush static 0\nreturn\n",
        encoding="utf-8",
    )
    (proj_dir / "Alpha.vm").write_text(
        "function Alpha.run 0\npush static 0\nreturn\n",
        encoding="utf-8",
    )
    (proj_dir / "README.txt").write_text("ignorar\n", encoding="utf-8")
    nested = proj_dir / "nested"
    nested.mkdir()
    (nested / "Ignored.vm").write_text("push constant 999\n", encoding="utf-8")

    files, output_path, should_bootstrap = resolve_io(str(proj_dir))
    assert [f.name for f in files] == ["Alpha.vm", "Beta.vm"]
    assert output_path == proj_dir / "NoSysProj.asm"
    assert should_bootstrap is False

    assert main([str(proj_dir)]) == 0
    assert capsys.readouterr().err == ""

    content = output_path.read_text(encoding="utf-8")
    assert "// bootstrap" not in content
    assert "@Alpha.0" in content
    assert "@Beta.0" in content
    assert content.index("(Alpha.run)") < content.index("(Beta.run)")
    assert "999" not in content


def test_directory_with_sys_vm_emits_bootstrap_and_isolates_statics_and_labels(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "MultiFileProj"
    proj_dir.mkdir()
    (proj_dir / "Class1.vm").write_text(
        "function Class1.set 0\n"
        "push argument 0\n"
        "pop static 0\n"
        "push constant 0\n"
        "eq\n"
        "return\n",
        encoding="utf-8",
    )
    (proj_dir / "Class2.vm").write_text(
        "function Class2.set 0\n"
        "push argument 0\n"
        "pop static 0\n"
        "push constant 0\n"
        "eq\n"
        "return\n",
        encoding="utf-8",
    )
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\n"
        "push constant 6\n"
        "call Class1.set 1\n"
        "push constant 8\n"
        "call Class2.set 1\n"
        "label END\n"
        "goto END\n",
        encoding="utf-8",
    )

    exit_code = main([f"{proj_dir}/"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""

    output_path = proj_dir / "MultiFileProj.asm"
    assert output_path.is_file()

    content = output_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == "// bootstrap"
    assert "@256" in lines
    assert "// call Sys.init 0" in lines
    assert "@Class1.0" in lines
    assert "@Class2.0" in lines
    assert "(Sys.init$END)" in lines

    declared_labels = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\(([^)]+)\)", line))
    ]
    assert len(declared_labels) == len(set(declared_labels))


def test_directory_isolates_global_labels_across_files_without_functions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "GlobalFlowProj"
    proj_dir.mkdir()
    (proj_dir / "FileA.vm").write_text(
        "label LOOP\n"
        "push constant 0\n"
        "if-goto LOOP\n"
        "goto LOOP\n",
        encoding="utf-8",
    )
    (proj_dir / "FileB.vm").write_text(
        "label LOOP\n"
        "push constant 1\n"
        "if-goto LOOP\n"
        "goto LOOP\n",
        encoding="utf-8",
    )

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""

    lines = (proj_dir / "GlobalFlowProj.asm").read_text(encoding="utf-8").splitlines()
    assert "(GLOBAL$FileA$LOOP)" in lines
    assert lines.count("@GLOBAL$FileA$LOOP") == 2
    assert "(GLOBAL$FileB$LOOP)" in lines
    assert lines.count("@GLOBAL$FileB$LOOP") == 2

    declared_labels = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\(([^)]+)\)", line))
    ]
    assert len(declared_labels) == len(set(declared_labels))


def test_directory_rejects_function_and_static_collision_across_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "CrossFileCollision"
    proj_dir.mkdir()
    (proj_dir / "Foo.vm").write_text(
        "function Foo.init 0\n"
        "push constant 1\n"
        "pop static 0\n"
        "return\n",
        encoding="utf-8",
    )
    (proj_dir / "Main.vm").write_text(
        "function Foo.0 0\n"
        "return\n",
        encoding="utf-8",
    )

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "colisão" in captured.err
    assert "Foo.0" in captured.err
    assert not (proj_dir / "CrossFileCollision.asm").exists()


def test_directory_rejects_call_reference_and_static_collision_across_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "RefStaticCollision"
    proj_dir.mkdir()
    (proj_dir / "Foo.vm").write_text(
        "function Foo.init 0\n"
        "push static 0\n"
        "return\n",
        encoding="utf-8",
    )
    (proj_dir / "Main.vm").write_text(
        "function Main.run 0\n"
        "call Foo.0 0\n"
        "return\n",
        encoding="utf-8",
    )

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "colisão" in captured.err
    assert "Foo.0" in captured.err
    assert not (proj_dir / "RefStaticCollision.asm").exists()


def test_directory_rejects_duplicate_function_across_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "DupFuncAcrossFiles"
    proj_dir.mkdir()
    (proj_dir / "A.vm").write_text("function Shared.f 0\nreturn\n", encoding="utf-8")
    (proj_dir / "B.vm").write_text("function Shared.f 0\nreturn\n", encoding="utf-8")

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "definição duplicada" in captured.err
    assert "Shared.f" in captured.err
    assert not (proj_dir / "DupFuncAcrossFiles.asm").exists()


def test_directory_reserves_symbols_from_later_files_and_protects_bootstrap(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "LaterReservation"
    proj_dir.mkdir()
    (proj_dir / "A.vm").write_text(
        "function B.run 0\n"
        "push constant 1\n"
        "push constant 1\n"
        "eq\n"
        "call Z.done 0\n"
        "return\n",
        encoding="utf-8",
    )
    (proj_dir / "B.run$ret.vm").write_text(
        "function Helper.keep 0\n"
        "push static 4\n"
        "return\n",
        encoding="utf-8",
    )
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\n"
        "call B.run 0\n"
        "label HALT\n"
        "goto HALT\n"
        "function GLOBAL 0\n"
        "label ret.0\n"
        "return\n",
        encoding="utf-8",
    )
    (proj_dir / "Z.vm").write_text(
        "function Z.done 0\n"
        "return\n"
        "function VM_EQ_END_2 0\n"
        "return\n",
        encoding="utf-8",
    )

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""

    lines = (proj_dir / "LaterReservation.asm").read_text(encoding="utf-8").splitlines()
    assert "@GLOBAL$ret.1" in lines
    assert "(GLOBAL$ret.1)" in lines
    assert "@GLOBAL$ret.0" not in lines
    assert lines.count("(GLOBAL$ret.0)") == 1

    assert "(VM_EQ_TRUE_3)" in lines
    assert "(VM_EQ_END_3)" in lines
    assert "(VM_EQ_TRUE_2)" not in lines
    assert lines.count("(VM_EQ_END_2)") == 1

    assert "@B.run$ret.4" in lines
    assert "(B.run$ret.4)" not in lines
    assert "@B.run$ret.5" in lines
    assert "(B.run$ret.5)" in lines

    declared_labels = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\(([^)]+)\)", line))
    ]
    assert len(declared_labels) == len(set(declared_labels))


def test_directory_without_vm_files_returns_error_and_creates_no_asm(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    only_other = tmp_path / "OnlyTxt"
    only_other.mkdir()
    (only_other / "notes.txt").write_text("sem vm\n", encoding="utf-8")

    exit_code = main([str(only_other)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Nenhum arquivo '.vm' encontrado" in captured.err
    assert not (only_other / "OnlyTxt.asm").exists()


def test_directory_error_in_second_file_removes_partial_asm(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "PartialFail"
    proj_dir.mkdir()
    (proj_dir / "A_Valid.vm").write_text(
        "function A.ok 0\npush constant 1\nreturn\n",
        encoding="utf-8",
    )
    (proj_dir / "B_Broken.vm").write_text(
        "function B.fail 0\ncall Bad$Name 1\n",
        encoding="utf-8",
    )
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\nreturn\n",
        encoding="utf-8",
    )

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "B_Broken.vm:2:" in captured.err
    assert not (proj_dir / "PartialFail.asm").exists()


@pytest.mark.parametrize(
    "second_file_content",
    [
        "function B.fail 0\ncall Bad$Name 1\n",
        "function B.fail 0\npush constant 1\npop constant 0\nreturn\n",
    ],
)
def test_directory_preserves_existing_asm_and_cleans_temp_on_second_file_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    second_file_content: str,
) -> None:
    proj_dir = tmp_path / "DirPreserve"
    proj_dir.mkdir()
    (proj_dir / "A_Valid.vm").write_text(
        "function A.ok 0\npush constant 1\nreturn\n",
        encoding="utf-8",
    )
    (proj_dir / "B_Broken.vm").write_text(second_file_content, encoding="utf-8")
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\nreturn\n",
        encoding="utf-8",
    )
    asm_file = proj_dir / "DirPreserve.asm"
    previous_content = "// versao valida anterior do diretorio\n@256\n"
    asm_file.write_text(previous_content, encoding="utf-8")

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err != ""
    assert asm_file.read_text(encoding="utf-8") == previous_content
    assert {entry.name for entry in proj_dir.iterdir()} == {
        "A_Valid.vm",
        "B_Broken.vm",
        "Sys.vm",
        "DirPreserve.asm",
    }


def test_directory_preserves_existing_asm_and_cleans_temp_on_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "DirCloseFail"
    proj_dir.mkdir()
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\nlabel HALT\ngoto HALT\n",
        encoding="utf-8",
    )
    asm_file = proj_dir / "DirCloseFail.asm"
    previous_content = "// versao valida anterior\n@10\n"
    asm_file.write_text(previous_content, encoding="utf-8")

    original_close = CodeWriter.close

    def failing_close(self: CodeWriter) -> None:
        original_close(self)
        raise OSError("falha simulada no close do diretorio")

    monkeypatch.setattr(CodeWriter, "close", failing_close)

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "falha simulada no close do diretorio" in captured.err
    assert asm_file.read_text(encoding="utf-8") == previous_content
    assert {entry.name for entry in proj_dir.iterdir()} == {
        "Sys.vm",
        "DirCloseFail.asm",
    }


def test_directory_preserves_existing_asm_and_cleans_temp_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "DirReplaceFail"
    proj_dir.mkdir()
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\nlabel HALT\ngoto HALT\n",
        encoding="utf-8",
    )
    asm_file = proj_dir / "DirReplaceFail.asm"
    previous_content = "// versao valida anterior\n@20\n"
    asm_file.write_text(previous_content, encoding="utf-8")

    def failing_replace(src: Path | str, dst: Path | str) -> None:
        raise OSError("falha simulada no replace do diretorio")

    monkeypatch.setattr("main.cli.os.replace", failing_replace)

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "falha simulada no replace do diretorio" in captured.err
    assert asm_file.read_text(encoding="utf-8") == previous_content
    assert {entry.name for entry in proj_dir.iterdir()} == {
        "Sys.vm",
        "DirReplaceFail.asm",
    }


def test_directory_replaces_existing_asm_and_leaves_no_temp_on_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj_dir = tmp_path / "DirReplaceSuccess"
    proj_dir.mkdir()
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\nlabel HALT\ngoto HALT\n",
        encoding="utf-8",
    )
    asm_file = proj_dir / "DirReplaceSuccess.asm"
    asm_file.write_text("// versao antiga do diretorio\n", encoding="utf-8")

    exit_code = main([str(proj_dir)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    new_content = asm_file.read_text(encoding="utf-8")
    assert "// bootstrap" in new_content
    assert "(Sys.init$HALT)" in new_content
    assert "// versao antiga do diretorio" not in new_content
    assert {entry.name for entry in proj_dir.iterdir()} == {
        "Sys.vm",
        "DirReplaceSuccess.asm",
    }


@pytest.mark.skipif(os.geteuid() == 0, reason="Root ignora restrições de chmod.")
def test_unreadable_directory_raises_cli_error(tmp_path: Path) -> None:
    locked_dir = tmp_path / "LockedDir"
    locked_dir.mkdir()
    (locked_dir / "Sys.vm").write_text("function Sys.init 0\n", encoding="utf-8")
    locked_dir.chmod(0)
    try:
        with pytest.raises(CLIError, match="permissão"):
            resolve_io(str(locked_dir))
    finally:
        locked_dir.chmod(stat.S_IRWXU)


def test_translate_directory_returns_generated_asm_path(tmp_path: Path) -> None:
    proj_dir = tmp_path / "DirReturn"
    proj_dir.mkdir()
    (proj_dir / "Sys.vm").write_text(
        "function Sys.init 0\nlabel HALT\ngoto HALT\n",
        encoding="utf-8",
    )

    output_path = translate(str(proj_dir))

    assert output_path == proj_dir / "DirReturn.asm"
    assert output_path.is_file()


@pytest.mark.parametrize("scope", ["global", "function"])
def test_label_validation_accepts_forward_backward_repeated_and_unused_labels(
    tmp_path: Path,
    scope: str,
) -> None:
    vm_file = tmp_path / "Flow.vm"
    prefix = "function Flow.run 0\n" if scope == "function" else ""
    vm_file.write_text(
        prefix
        + "goto LOOP\n"
        "push constant 1\n"
        "if-goto LOOP\n"
        "label LOOP\n"
        "goto LOOP\n"
        "label UNUSED\n",
        encoding="utf-8",
    )

    output_path = translate(str(vm_file))
    lines = output_path.read_text(encoding="utf-8").splitlines()
    label_prefix = "Flow.run" if scope == "function" else "GLOBAL$Flow"
    assert lines.count(f"@{label_prefix}$LOOP") == 3
    assert lines.count(f"({label_prefix}$LOOP)") == 1
    assert f"({label_prefix}$UNUSED)" in lines


@pytest.mark.parametrize("command", ["goto", "if-goto"])
@pytest.mark.parametrize("existing_output", [False, True])
def test_label_validation_rejects_missing_targets_and_preserves_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    existing_output: bool,
) -> None:
    vm_file = tmp_path / "Missing.vm"
    vm_file.write_text(
        f"// comentario\n\npush constant 1\n{command} ABSENT\n",
        encoding="utf-8",
    )
    asm_file = vm_file.with_suffix(".asm")
    previous_content = b"// assembly anterior\n@256\n"
    if existing_output:
        asm_file.write_bytes(previous_content)

    assert main([str(vm_file)]) == 1
    captured = capsys.readouterr()
    assert f"{vm_file}:4:" in captured.err
    assert "GLOBAL$Missing$ABSENT" in captured.err
    assert "não definido" in captured.err
    if existing_output:
        assert asm_file.read_bytes() == previous_content
    else:
        assert not asm_file.exists()
    expected_files = {vm_file.name, asm_file.name} if existing_output else {vm_file.name}
    assert {entry.name for entry in tmp_path.iterdir()} == expected_files


@pytest.mark.parametrize("command", ["goto", "if-goto"])
def test_label_validation_rejects_target_in_another_function(
    tmp_path: Path,
    command: str,
) -> None:
    vm_file = tmp_path / "Functions.vm"
    vm_file.write_text(
        "function Functions.first 0\n"
        "push constant 1\n"
        f"{command} LOOP\n"
        "function Functions.second 0\n"
        "label LOOP\n"
        "goto LOOP\n",
        encoding="utf-8",
    )

    with pytest.raises(CLIError) as exc_info:
        translate(str(vm_file))

    message = str(exc_info.value)
    assert f"{vm_file}:3:" in message
    assert "Functions.first$LOOP" in message
    assert "não definido" in message
    assert not vm_file.with_suffix(".asm").exists()


@pytest.mark.parametrize("command", ["goto", "if-goto"])
def test_label_validation_rejects_target_in_another_file(
    tmp_path: Path,
    command: str,
) -> None:
    proj_dir = tmp_path / "CrossFileFlow"
    proj_dir.mkdir()
    vm_file = proj_dir / "A.vm"
    vm_file.write_text(
        f"push constant 1\n{command} LOOP\n",
        encoding="utf-8",
    )
    (proj_dir / "B.vm").write_text(
        "label LOOP\ngoto LOOP\n",
        encoding="utf-8",
    )

    with pytest.raises(CLIError) as exc_info:
        translate(str(proj_dir))

    message = str(exc_info.value)
    assert f"{vm_file}:2:" in message
    assert "GLOBAL$A$LOOP" in message
    assert "não definido" in message
    assert {entry.name for entry in proj_dir.iterdir()} == {"A.vm", "B.vm"}
