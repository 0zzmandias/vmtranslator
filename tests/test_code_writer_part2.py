"""Testes unitários abrangentes do módulo codewriter (Parte 2)."""

from pathlib import Path
import re

import pytest

from codewriter import CodeWriter, CodeWriterError
from tests.hack_simulator import _execute_hack_asm


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
        "(GLOBAL$BasicLoop$LOOP)",
        "// goto LOOP",
        "@GLOBAL$BasicLoop$LOOP",
        "0;JMP",
        "// if-goto LOOP",
        "@SP",
        "AM=M-1",
        "D=M",
        "@GLOBAL$BasicLoop$LOOP",
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
    assert "(GLOBAL$ClassB$LOOP)" in lines


def test_global_labels_are_isolated_across_files_and_before_set_file_name(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "GlobalLevels.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeLabel("START")
        cw.writeGoto("START")

        cw.setFileName("FileA")
        cw.writeLabel("LOOP")
        cw.writeGoto("LOOP")
        cw.writeIf("LOOP")

        cw.setFileName("FileB")
        cw.writeLabel("LOOP")
        cw.writeGoto("LOOP")
        cw.writeIf("LOOP")

    lines = _read_lines(asm_file)
    assert "(GLOBAL$START)" in lines
    assert "@GLOBAL$START" in lines
    assert "(GLOBAL$FileA$LOOP)" in lines
    assert lines.count("@GLOBAL$FileA$LOOP") == 2
    assert "(GLOBAL$FileB$LOOP)" in lines
    assert lines.count("@GLOBAL$FileB$LOOP") == 2


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


def test_write_call_skips_reserved_return_label_from_vm_label(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "ReservedReturn.asm"
    with CodeWriter(asm_file, reserved_symbols={"Main.f$ret.0"}) as cw:
        cw.writeFunction("Main.f", 0)
        cw.writeCall("Other.g", 0)
        cw.writeLabel("ret.0")

    lines = _read_lines(asm_file)
    assert "@Main.f$ret.1" in lines
    assert "(Main.f$ret.1)" in lines
    assert lines.count("(Main.f$ret.0)") == 1
    assert "@Main.f$ret.0" not in lines


def test_write_call_avoids_collision_with_static_symbol_and_prior_label(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "StaticAndLabelCollision.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("Main.f$ret")
        cw.writePush("static", 0)
        cw.writeFunction("Main.f", 0)
        cw.writeLabel("ret.1")
        cw.writeCall("Other.g", 0)

    lines = _read_lines(asm_file)
    assert "@Main.f$ret.0" in lines
    assert "(Main.f$ret.0)" not in lines
    assert lines.count("(Main.f$ret.1)") == 1
    assert "@Main.f$ret.2" in lines
    assert "(Main.f$ret.2)" in lines


def test_write_init_skips_reserved_global_return_label(tmp_path: Path) -> None:
    asm_file = tmp_path / "BootstrapReserved.asm"
    with CodeWriter(asm_file, reserved_symbols={"GLOBAL$ret.0"}) as cw:
        cw.writeInit()

    lines = _read_lines(asm_file)
    assert "@GLOBAL$ret.0" not in lines
    assert "(GLOBAL$ret.0)" not in lines
    assert "@GLOBAL$ret.1" in lines
    assert "(GLOBAL$ret.1)" in lines


def test_comparison_avoids_collision_with_reserved_function_name(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "ComparisonFunctionCollision.asm"
    with CodeWriter(asm_file, reserved_symbols={"VM_LT_TRUE_0"}) as cw:
        cw.writeArithmetic("lt")
        cw.writeFunction("VM_LT_TRUE_0", 0)

    lines = _read_lines(asm_file)
    assert "(VM_LT_TRUE_1)" in lines
    assert "(VM_LT_END_1)" in lines
    assert "(VM_LT_END_0)" not in lines
    assert lines.count("(VM_LT_TRUE_0)") == 1


def test_write_return_reads_retaddr_before_overwriting_arg0_and_restores_frame(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "Return.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeFunction("Main.run", 0)
        cw.writeReturn()

    lines = _read_lines(asm_file)
    assert lines[:2] == ["// function Main.run 0", "(Main.run)"]
    lines = lines[2:]
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


@pytest.mark.parametrize("command", ["function", "call"])
@pytest.mark.parametrize(
    "predefined",
    ["SP", "LCL", "ARG", "THIS", "THAT", "SCREEN", "KBD"]
    + [f"R{i}" for i in range(16)],
)
def test_predefined_function_symbol_is_rejected_without_changing_writer_state(
    tmp_path: Path,
    command: str,
    predefined: str,
) -> None:
    asm_file = tmp_path / "Predefined.asm"
    reference_file = tmp_path / "Reference.asm"
    with CodeWriter(reference_file) as cw:
        cw.writeFunction("Main.run", 0)
        cw.writeLabel("AFTER")
        cw.writeCall("External.f", 0)

    with CodeWriter(asm_file) as cw:
        cw.writeFunction("Main.run", 0)
        with pytest.raises(CodeWriterError, match="predefinido") as exc_info:
            if command == "function":
                cw.writeFunction(predefined, 0)
            else:
                cw.writeCall(predefined, 0)
        assert predefined in str(exc_info.value)
        cw.writeLabel("AFTER")
        cw.writeCall("External.f", 0)

    assert asm_file.read_bytes() == reference_file.read_bytes()


@pytest.mark.parametrize("context", ["initial", "call", "bootstrap", "new_file"])
def test_write_return_rejects_missing_function_without_emitting_code(
    tmp_path: Path,
    context: str,
) -> None:
    asm_file = tmp_path / "Outside.asm"
    reference_file = tmp_path / "Reference.asm"

    def prepare(writer: CodeWriter) -> None:
        if context == "call":
            writer.writeCall("External.f", 0)
        elif context == "bootstrap":
            writer.writeInit()
        elif context == "new_file":
            writer.setFileName("First")
            writer.writeFunction("First.run", 0)
            writer.setFileName("Second")

    with CodeWriter(reference_file) as cw:
        prepare(cw)
        cw.writeFunction("Main.run", 0)
        cw.writeReturn()

    with CodeWriter(asm_file) as cw:
        prepare(cw)
        with pytest.raises(CodeWriterError, match="fora de função"):
            cw.writeReturn()
        cw.writeFunction("Main.run", 0)
        cw.writeReturn()

    assert asm_file.read_bytes() == reference_file.read_bytes()


@pytest.mark.parametrize("num_vars", [0, 3])
def test_function_initializes_locals_on_nonzero_ram(
    tmp_path: Path,
    num_vars: int,
) -> None:
    asm_file = tmp_path / "LocalsBehavior.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeFunction("Main.run", num_vars)
        cw.writeLabel("READY")
        cw.writePush("constant", 99)

    initial = {0: 300, 1: 300, 300: 11, 301: -7, 302: 19, 303: 23}
    ram = _execute_hack_asm(
        _read_lines(asm_file), initial_ram=initial, stop_label="Main.run$READY",
    )
    assert ram[0] == 300 + num_vars
    assert ram[1] == 300
    for address in range(300, 304):
        assert ram[address] == (0 if address < 300 + num_vars else initial[address])


def test_call_without_arguments_returns_and_restores_caller_frame(tmp_path: Path) -> None:
    asm_file = tmp_path / "ZeroArgsBehavior.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("Caller")
        cw.writeCall("Worker.run", 0)
        cw.writePush("constant", 77)
        cw.writePop("temp", 0)
        cw.writeGoto("HALT")
        cw.writeFunction("Worker.run", 0)
        cw.writePush("constant", 111)
        cw.writePop("pointer", 0)
        cw.writePush("constant", 222)
        cw.writePop("pointer", 1)
        cw.writePush("constant", 42)
        cw.writeReturn()
        cw.setFileName("Caller")
        cw.writeLabel("HALT")

    initial = {0: 300, 1: 400, 2: 500, 3: 600, 4: 700}
    ram = _execute_hack_asm(
        _read_lines(asm_file), initial_ram=initial, stop_label="GLOBAL$Caller$HALT",
    )
    assert ram[0] == 301
    assert ram[300] == 42
    assert [ram[i] for i in range(1, 5)] == [400, 500, 600, 700]
    assert ram[5] == 77


def test_call_with_arguments_passes_values_and_returns_result(tmp_path: Path) -> None:
    asm_file = tmp_path / "ArgsBehavior.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("Caller")
        cw.writePush("constant", 7)
        cw.writePush("constant", 3)
        cw.writeCall("Worker.subtract", 2)
        cw.writeGoto("HALT")
        cw.writeFunction("Worker.subtract", 0)
        cw.writePush("argument", 0)
        cw.writePush("argument", 1)
        cw.writeArithmetic("sub")
        cw.writeReturn()
        cw.setFileName("Caller")
        cw.writeLabel("HALT")

    initial = {0: 300, 1: 400, 2: 500, 3: 600, 4: 700}
    lines = _read_lines(asm_file)
    entry = _execute_hack_asm(lines, initial_ram=initial, stop_label="Worker.subtract")
    assert (entry[0], entry[1], entry[2]) == (307, 307, 300)
    assert (entry[300], entry[301]) == (7, 3)
    ram = _execute_hack_asm(lines, initial_ram=initial, stop_label="GLOBAL$Caller$HALT")
    assert ram[0] == 301
    assert ram[300] == 4
    assert [ram[i] for i in range(1, 5)] == [400, 500, 600, 700]


def test_nested_calls_restore_each_frame_and_resume_execution(tmp_path: Path) -> None:
    asm_file = tmp_path / "NestedBehavior.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("Caller")
        cw.writeCall("Outer.run", 0)
        cw.writePush("constant", 77)
        cw.writePop("temp", 0)
        cw.writeGoto("HALT")
        cw.writeFunction("Outer.run", 1)
        cw.writePush("constant", 17)
        cw.writePop("local", 0)
        cw.writePush("constant", 111)
        cw.writePop("pointer", 0)
        cw.writePush("constant", 222)
        cw.writePop("pointer", 1)
        cw.writePush("constant", 8)
        cw.writeCall("Inner.run", 1)
        cw.writeLabel("AFTER")
        cw.writePush("local", 0)
        cw.writeArithmetic("add")
        cw.writeReturn()
        cw.writeFunction("Inner.run", 0)
        cw.writePush("constant", 333)
        cw.writePop("pointer", 0)
        cw.writePush("constant", 444)
        cw.writePop("pointer", 1)
        cw.writePush("argument", 0)
        cw.writePush("constant", 2)
        cw.writeArithmetic("add")
        cw.writeReturn()
        cw.setFileName("Caller")
        cw.writeLabel("HALT")

    initial = {0: 300, 1: 400, 2: 500, 3: 600, 4: 700}
    lines = _read_lines(asm_file)
    outer = _execute_hack_asm(lines, initial_ram=initial, stop_label="Outer.run$AFTER")
    assert [outer[i] for i in range(5)] == [307, 305, 300, 111, 222]
    assert (outer[305], outer[306]) == (17, 10)
    ram = _execute_hack_asm(lines, initial_ram=initial, stop_label="GLOBAL$Caller$HALT")
    assert [ram[i] for i in range(5)] == [301, 400, 500, 600, 700]
    assert ram[300] == 27
    assert ram[5] == 77
