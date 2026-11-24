"""Testes unitários abrangentes do módulo codewriter (Parte 1)."""

from pathlib import Path
import re

import pytest

from codewriter import CodeWriter, CodeWriterError


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_arithmetic_binary_commands_and_sub_operand_order(tmp_path: Path) -> None:
    asm_file = tmp_path / "Binary.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeArithmetic("add")
        cw.writeArithmetic("sub")
        cw.writeArithmetic("and")
        cw.writeArithmetic("or")

    lines = _read_lines(asm_file)
    assert lines == [
        "// add",
        "@SP",
        "AM=M-1",
        "D=M",
        "A=A-1",
        "M=D+M",
        "// sub",
        "@SP",
        "AM=M-1",
        "D=M",
        "A=A-1",
        "M=M-D",
        "// and",
        "@SP",
        "AM=M-1",
        "D=M",
        "A=A-1",
        "M=D&M",
        "// or",
        "@SP",
        "AM=M-1",
        "D=M",
        "A=A-1",
        "M=D|M",
    ]


def test_arithmetic_unary_commands(tmp_path: Path) -> None:
    asm_file = tmp_path / "Unary.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeArithmetic("neg")
        cw.writeArithmetic("not")

    lines = _read_lines(asm_file)
    assert lines == [
        "// neg",
        "@SP",
        "A=M-1",
        "M=-M",
        "// not",
        "@SP",
        "A=M-1",
        "M=!M",
    ]


def test_comparison_commands_generate_unique_labels_and_boolean_values(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "Comparisons.asm"
    with CodeWriter(asm_file) as cw:
        cw.writeArithmetic("eq")
        cw.writeArithmetic("eq")
        cw.writeArithmetic("gt")
        cw.writeArithmetic("lt")

    content = asm_file.read_text(encoding="utf-8")
    lines = content.splitlines()

    declared_labels = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\(([^)]+)\)", line))
    ]
    assert len(declared_labels) == 8
    assert len(set(declared_labels)) == 8

    assert "D;JEQ" in lines
    assert "D;JGT" in lines
    assert "D;JLT" in lines
    assert "D=M-D" in lines
    assert "M=-1" in lines
    assert "M=0" in lines


def test_comparison_labels_skip_reserved_symbols_atomically(tmp_path: Path) -> None:
    asm_file = tmp_path / "ReservedComparisons.asm"
    reserved = {"VM_EQ_END_0", "VM_GT_TRUE_2"}
    with CodeWriter(asm_file, reserved_symbols=reserved) as cw:
        cw.writeArithmetic("eq")
        cw.writeArithmetic("gt")

    lines = _read_lines(asm_file)
    assert "(VM_EQ_TRUE_0)" not in lines
    assert "(VM_EQ_END_0)" not in lines
    assert "(VM_EQ_TRUE_1)" in lines
    assert "(VM_EQ_END_1)" in lines
    assert "(VM_GT_TRUE_2)" not in lines
    assert "(VM_GT_END_2)" not in lines
    assert "(VM_GT_TRUE_3)" in lines
    assert "(VM_GT_END_3)" in lines


def test_predefined_hack_symbols_table_is_complete() -> None:
    expected = {
        "SP",
        "LCL",
        "ARG",
        "THIS",
        "THAT",
        "SCREEN",
        "KBD",
        *(f"R{index}" for index in range(16)),
    }
    assert CodeWriter.PREDEFINED_HACK_SYMBOLS == expected


@pytest.mark.parametrize("value", [0, 17, 32767])
def test_push_constant_valid_boundaries(tmp_path: Path, value: int) -> None:
    asm_file = tmp_path / f"Const_{value}.asm"
    with CodeWriter(asm_file) as cw:
        cw.writePush("constant", value)

    assert _read_lines(asm_file) == [
        f"// push constant {value}",
        f"@{value}",
        "D=A",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
    ]


@pytest.mark.parametrize(
    ("segment", "symbol"),
    [
        ("local", "LCL"),
        ("argument", "ARG"),
        ("this", "THIS"),
        ("that", "THAT"),
    ],
)
def test_indirect_segments_push_and_pop_use_r13(
    tmp_path: Path,
    segment: str,
    symbol: str,
) -> None:
    asm_file = tmp_path / f"{segment}.asm"
    with CodeWriter(asm_file) as cw:
        cw.writePush(segment, 0)
        cw.writePop(segment, 32767)

    assert _read_lines(asm_file) == [
        f"// push {segment} 0",
        f"@{symbol}",
        "D=M",
        "@0",
        "A=D+A",
        "D=M",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        f"// pop {segment} 32767",
        f"@{symbol}",
        "D=M",
        "@32767",
        "D=D+A",
        "@R13",
        "M=D",
        "@SP",
        "AM=M-1",
        "D=M",
        "@R13",
        "A=M",
        "M=D",
    ]


@pytest.mark.parametrize(("index", "expected_addr"), [(0, 5), (3, 8), (7, 12)])
def test_temp_segment_valid_boundaries(
    tmp_path: Path,
    index: int,
    expected_addr: int,
) -> None:
    asm_file = tmp_path / f"Temp_{index}.asm"
    with CodeWriter(asm_file) as cw:
        cw.writePush("temp", index)
        cw.writePop("temp", index)

    assert _read_lines(asm_file) == [
        f"// push temp {index}",
        f"@{expected_addr}",
        "D=M",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        f"// pop temp {index}",
        "@SP",
        "AM=M-1",
        "D=M",
        f"@{expected_addr}",
        "M=D",
    ]


@pytest.mark.parametrize(("index", "expected_symbol"), [(0, "THIS"), (1, "THAT")])
def test_pointer_segment_valid_boundaries(
    tmp_path: Path,
    index: int,
    expected_symbol: str,
) -> None:
    asm_file = tmp_path / f"Pointer_{index}.asm"
    with CodeWriter(asm_file) as cw:
        cw.writePush("pointer", index)
        cw.writePop("pointer", index)

    assert _read_lines(asm_file) == [
        f"// push pointer {index}",
        f"@{expected_symbol}",
        "D=M",
        "@SP",
        "A=M",
        "M=D",
        "@SP",
        "M=M+1",
        f"// pop pointer {index}",
        "@SP",
        "AM=M-1",
        "D=M",
        f"@{expected_symbol}",
        "M=D",
    ]


def test_static_segment_isolates_symbols_per_file_name(tmp_path: Path) -> None:
    asm_file = tmp_path / "StaticIsolation.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("Class1")
        cw.writePush("static", 0)
        cw.writePop("static", 3)
        cw.setFileName("Class2")
        cw.writePush("static", 0)
        cw.writePop("static", 3)

    lines = _read_lines(asm_file)
    assert "@Class1.0" in lines
    assert "@Class1.3" in lines
    assert "@Class2.0" in lines
    assert "@Class2.3" in lines


def test_part1_never_emits_pointer_initialization_or_bootstrap(tmp_path: Path) -> None:
    asm_file = tmp_path / "NoBootstrap.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("NoBootstrap")
        cw.writePush("constant", 1)
        cw.writePush("constant", 2)
        cw.writeArithmetic("add")
        cw.writePop("static", 0)

    content = asm_file.read_text(encoding="utf-8")
    assert "@256" not in content
    assert "Sys.init" not in content
    assert "\r\n" not in content


def test_pop_constant_raises_code_writer_error(tmp_path: Path) -> None:
    asm_file = tmp_path / "PopConst.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError, match="constant"):
            cw.writePop("constant", 0)


@pytest.mark.parametrize("bad_index", [-1, 32768, True, False])
def test_constant_and_indirect_out_of_range_or_invalid_indices(
    tmp_path: Path,
    bad_index: int | bool,
) -> None:
    asm_file = tmp_path / "BadIndices.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("BadIndices")
        with pytest.raises(CodeWriterError):
            cw.writePush("constant", bad_index)
        with pytest.raises(CodeWriterError):
            cw.writePush("local", bad_index)
        with pytest.raises(CodeWriterError):
            cw.writePop("argument", bad_index)
        with pytest.raises(CodeWriterError):
            cw.writePush("static", bad_index)
        with pytest.raises(CodeWriterError):
            cw.writePop("static", bad_index)


@pytest.mark.parametrize("bad_temp", [-1, 8, 100])
def test_temp_out_of_range_raises_error(tmp_path: Path, bad_temp: int) -> None:
    asm_file = tmp_path / "BadTemp.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError, match="temp"):
            cw.writePush("temp", bad_temp)
        with pytest.raises(CodeWriterError, match="temp"):
            cw.writePop("temp", bad_temp)


@pytest.mark.parametrize("bad_pointer", [-1, 2, 10])
def test_pointer_out_of_range_raises_error(tmp_path: Path, bad_pointer: int) -> None:
    asm_file = tmp_path / "BadPointer.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError, match="pointer"):
            cw.writePush("pointer", bad_pointer)
        with pytest.raises(CodeWriterError, match="pointer"):
            cw.writePop("pointer", bad_pointer)


def test_static_without_set_file_name_raises_error(tmp_path: Path) -> None:
    asm_file = tmp_path / "NoFileName.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError, match="setFileName"):
            cw.writePush("static", 0)
        with pytest.raises(CodeWriterError, match="setFileName"):
            cw.writePop("static", 0)


@pytest.mark.parametrize(
    "bad_name",
    [
        "",
        "1Invalid",
        "has space",
        "bad-name",
        "a/b",
        "Foo\n",
        "Foo\r",
        "Foo bar",
        "Foo/Bar",
    ],
)
def test_invalid_file_name_raises_error(tmp_path: Path, bad_name: str) -> None:
    asm_file = tmp_path / "BadName.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError, match="Nome de arquivo inválido"):
            cw.setFileName(bad_name)


def test_valid_hack_symbol_file_name_is_accepted(tmp_path: Path) -> None:
    asm_file = tmp_path / "ValidName.asm"
    with CodeWriter(asm_file) as cw:
        cw.setFileName("Module_1.Sub:A$B")
        cw.writePush("static", 0)

    assert "@Module_1.Sub:A$B.0" in _read_lines(asm_file)


def test_invalid_command_or_segment_raises_error(tmp_path: Path) -> None:
    asm_file = tmp_path / "InvalidCmd.asm"
    with CodeWriter(asm_file) as cw:
        with pytest.raises(CodeWriterError, match="inválido"):
            cw.writeArithmetic("mul")
        with pytest.raises(CodeWriterError, match="Segmento"):
            cw.writePush("heap", 0)
        with pytest.raises(CodeWriterError, match="Segmento"):
            cw.writePop("heap", 0)


def test_writing_after_close_raises_error_and_close_is_idempotent(
    tmp_path: Path,
) -> None:
    asm_file = tmp_path / "Closed.asm"
    cw = CodeWriter(asm_file)
    cw.close()
    cw.close()

    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.setFileName("Closed")
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writeArithmetic("add")
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writePush("constant", 1)
    with pytest.raises(CodeWriterError, match="fechamento"):
        cw.writePop("temp", 0)


def test_opening_unwritable_output_path_raises_error(tmp_path: Path) -> None:
    missing_dir_output = tmp_path / "nonexistent_dir" / "Out.asm"

    with pytest.raises(CodeWriterError, match="Não foi possível abrir"):
        CodeWriter(missing_dir_output)
