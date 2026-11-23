"""Testes unitários abrangentes do módulo codewriter (Parte 2)."""

from pathlib import Path
import re

import pytest

from codewriter import CodeWriter, CodeWriterError


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_program_flow_uses_default_global_scope_without_function(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "FlowGlobal.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("BasicLoop")
        cw.writeLabel("LOOP")
        cw.writeGoto("LOOP")
        cw.writeIf("LOOP")

    assert _read_lines(asm_file) == [
        "// label LOOP",
        "(GLOBAL$LOOP)",
        "// goto LOOP",
        "@GLOBAL$LOOP",
        "0;JMP",
        "// if-goto LOOP",
        "@SP",
        "AM=M-1",
        "D=M",
        "@GLOBAL$LOOP",
        "D;JNE",
    ]


def test_labels_are_isolated_by_function_scope_and_reset_on_new_file(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "FlowScopes.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("ClassA")
        cw.writeFunction("ClassA.first", 0)
        cw.writeLabel("LOOP")
        cw.writeGoto("LOOP")

        cw.writeFunction("ClassA.second", 0)
        cw.writeLabel("LOOP")
        cw.writeIf("LOOP")

        cw.setFileName("ClassB")
        cw.writeLabel("LOOP")

    lines = _read_lines(asm_file)
    assert "(ClassA.first$LOOP)" in lines
    assert "@ClassA.first$LOOP" in lines
    assert "(ClassA.second$LOOP)" in lines
    assert "@ClassA.second$LOOP" in lines
    assert "(GLOBAL$LOOP)" in lines


def test_write_function_zero_locals_emits_only_entry_label(tmp_path: Path) -> None:
    asm_file = tmp_path / "ZeroLocals.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeFunction("Main.zero", 0)

    assert _read_lines(asm_file) == [
        "// function Main.zero 0",
        "(Main.zero)",
    ]


def test_write_function_initializes_nvars_locals_to_zero(tmp_path: Path) -> None:
    asm_file = tmp_path / "ThreeLocals.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeFunction("Main.three", 3)

    zero_push = ["@SP", "A=M", "M=0", "@SP", "M=M+1"]
    assert _read_lines(asm_file) == [
        "// function Main.three 3",
        "(Main.three)",
        *zero_push,
        *zero_push,
        *zero_push,
    ]


def test_write_call_emits_full_frame_and_recalculates_arg_and_lcl(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "CallFrame.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeFunction("Sys.init", 0)
        cw.writeCall("Main.fibonacci", 2)

    lines = _read_lines(asm_file)
    assert lines == [
        "// function Sys.init 0",
        "(Sys.init)",
        "// call Main.fibonacci 2",
        "@Sys.init$ret.0",
        "D=A",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        "@LCL",
        "D=M",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        "@ARG",
        "D=M",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        "@THIS",
        "D=M",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        "@THAT",
        "D=M",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        "@SP",
        "D=M",
        "@7",
        "D=D-A",
        "@ARG",
        "M=D",
        "@SP",
        "D=M",
        "@LCL",
        "M=D",
        "@Main.fibonacci",
        "0;JMP",
        "(Sys.init$ret.0)",
    ]


def test_return_labels_and_comparison_labels_remain_globally_unique(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "UniqueLabels.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("File1")
        cw.writeFunction("Main.f", 0)
        cw.writeCall("Main.f", 1)
        cw.writeArithmetic("lt")
        cw.writeCall("Main.f", 1)
        cw.setFileName("File2")
        cw.writeFunction("Main.f", 0)
        cw.writeCall("Other.g", 0)
        cw.writeArithmetic("eq")

    lines = _read_lines(asm_file)
    declared_labels = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\(([^)]+)\)", line))
        and not line.startswith("(Main.f)")
    ]
    assert len(declared_labels) == len(set(declared_labels))
    assert "Main.f$ret.0" in declared_labels
    assert "Main.f$ret.2" in declared_labels
    assert "Main.f$ret.3" in declared_labels


def test_write_return_reads_retaddr_before_overwriting_arg0_and_restores_frame(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "Return.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeReturn()

    lines = _read_lines(asm_file)
    assert lines == [
        "// return",
        "@LCL",
        "D=M",
        "@R13",
        "M=D",
        "@5",
        "A=D-A",
        "D=M",
        "@R14",
        "M=D",
        "@SP",
        "AM=M-1",
        "D=M",
        "@ARG",
        "A=M",
        "M=D",
        "@ARG",
        "D=M+1",
        "@SP",
        "M=D",
        "@R13",
        "AM=M-1",
        "D=M",
        "@THAT",
        "M=D",
        "@R13",
        "AM=M-1",
        "D=M",
        "@THIS",
        "M=D",
        "@R13",
        "AM=M-1",
        "D=M",
        "@ARG",
        "M=D",
        "@R13",
        "AM=M-1",
        "D=M",
        "@LCL",
        "M=D",
        "@R14",
        "A=M",
        "0;JMP",
    ]
    assert lines.index("@R14") < lines.index("@ARG")


def test_write_init_sets_sp_256_and_executes_full_call_to_sys_init(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "Bootstrap.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeInit()

    lines = _read_lines(asm_file)
    assert lines[:6] == [
        "// bootstrap",
        "@256",
        "D=A",
        "@SP",
        "M=D",
        "// call Sys.init 0",
    ]
    assert "@5" in lines
    assert "@Sys.init" in lines
    assert "(GLOBAL$ret.0)" in lines


@pytest.mark.parametrize("bad_name", ["", "1BAD", "BAD$NAME", "has space", "a-b"])
def test_invalid_identifiers_raise_code_writer_error(
    tmp_path: Path,
    bad_name: str,
) -> None:
    asm_file = tmp_path / "BadIds.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError, match="Identificador inválido"):
            cw.writeLabel(bad_name)
        with pytest.raises(CodeWriterError, match="Identificador inválido"):
            cw.writeGoto(bad_name)
        with pytest.raises(CodeWriterError, match="Identificador inválido"):
            cw.writeIf(bad_name)
        with pytest.raises(CodeWriterError, match="Identificador inválido"):
            cw.writeFunction(bad_name, 0)
        with pytest.raises(CodeWriterError, match="Identificador inválido"):
            cw.writeCall(bad_name, 0)


@pytest.mark.parametrize("bad_count", [-1, 32768, True, False])
def test_write_function_invalid_nvars_raises_error(
    tmp_path: Path,
    bad_count: int | bool,
) -> None:
    asm_file = tmp_path / "BadFunc.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError):
            cw.writeFunction("Main.f", bad_count)


@pytest.mark.parametrize("bad_args", [-1, 32763, 32768, True, False])
def test_write_call_invalid_nargs_raises_error(
    tmp_path: Path,
    bad_args: int | bool,
) -> None:
    asm_file = tmp_path / "BadCall.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError):
            cw.writeCall("Main.f", bad_args)


def test_part2_methods_after_close_raise_error(tmp_path: Path) -> None:
    asm_file = tmp_path / "ClosedPart2.asm"
    cw = CodeWriter(asm_file)
    cw.close()

    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeInit()
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeLabel("L")
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeGoto("L")
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeIf("L")
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeFunction("Main.f", 0)
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeCall("Main.f", 0)
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeReturn()
