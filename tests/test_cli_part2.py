"""Testes de integração e linha de comando (CLI) da Parte 2."""

import os
from pathlib import Path
import re
import stat

import pytest

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
