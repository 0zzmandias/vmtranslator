"""Simulador Hack mínimo, exclusivo da suíte de testes."""

import re


_SYMBOL_RE = re.compile(r"[A-Za-z_.$:][A-Za-z0-9_.$:]*")


def _to_int16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _execute_hack_asm(
    lines: list[str],
    initial_sp: int = 256,
    *,
    initial_ram: dict[int, int] | None = None,
    stop_label: str | None = None,
    max_steps: int = 10_000,
) -> dict[int, int]:
    """Executa o subconjunto Hack usado pelos testes, não um emulador completo.

    A RAM inicial é copiada; suas entradas prevalecem sobre initial_sp.
    stop_label interrompe antes da instrução no endereço do rótulo.
    Sem rótulo de parada, a execução termina ao sair da ROM do programa.
    """
    assert max_steps > 0, "Limite de ciclos deve ser positivo."
    symbols: dict[str, int] = {
        "SP": 0,
        "LCL": 1,
        "ARG": 2,
        "THIS": 3,
        "THAT": 4,
        "SCREEN": 16384,
        "KBD": 24576,
        **{f"R{index}": index for index in range(16)},
    }
    rom: list[str] = []
    labels: set[str] = set()
    for raw_line in lines:
        clean = raw_line.split("//", 1)[0].strip()
        if not clean:
            continue
        if clean.startswith("(") and clean.endswith(")"):
            label = clean[1:-1]
            assert label not in symbols, f"Rótulo duplicado no Assembly: {label}"
            assert _SYMBOL_RE.fullmatch(label), f"Rótulo Hack inválido: {label!r}"
            symbols[label] = len(rom)
            labels.add(label)
        else:
            rom.append(clean)

    stop_pc: int | None = None
    if stop_label is not None:
        assert stop_label in labels, f"Rótulo de parada inexistente: {stop_label!r}"
        stop_pc = symbols[stop_label]

    next_var_addr = 16
    ram: dict[int, int] = {0: _to_int16(initial_sp)}
    if initial_ram is not None:
        for address, value in initial_ram.items():
            assert 0 <= address <= 0x7FFF, f"Endereço RAM inválido: {address}"
            ram[address] = _to_int16(value)
    reg_a = 0
    reg_d = 0
    pc = 0
    steps = 0

    while 0 <= pc < len(rom) and pc != stop_pc:
        steps += 1
        assert steps <= max_steps, "Limite de ciclos excedido na simulação Hack."
        instr = rom[pc]

        if instr.startswith("@"):
            token = instr[1:]
            if token.isdigit():
                reg_a = int(token)
                assert reg_a <= 0x7FFF, f"Constante A fora de 15 bits: {token!r}"
            else:
                assert _SYMBOL_RE.fullmatch(token), f"Símbolo Hack inválido: {token!r}"
                if token not in symbols:
                    symbols[token] = next_var_addr
                    next_var_addr += 1
                reg_a = symbols[token]
            pc += 1
            continue

        dest = ""
        jump = ""
        body = instr
        if "=" in body:
            dest, body = body.split("=", 1)
            assert dest in {"M", "D", "MD", "A", "AM", "AD", "AMD"}, (
                f"Destino Hack inválido: {dest!r}"
            )
        if ";" in body:
            comp, jump = body.split(";", 1)
        else:
            comp = body

        old_a = reg_a
        address = old_a & 0x7FFF
        mem_val = ram.get(address, 0)
        alu_ops: dict[str, int] = {
            "0": 0,
            "1": 1,
            "-1": -1,
            "D": reg_d,
            "A": reg_a,
            "M": mem_val,
            "!D": _to_int16(~reg_d),
            "!A": _to_int16(~reg_a),
            "!M": _to_int16(~mem_val),
            "-D": _to_int16(-reg_d),
            "-A": _to_int16(-reg_a),
            "-M": _to_int16(-mem_val),
            "D+1": _to_int16(reg_d + 1),
            "A+1": _to_int16(reg_a + 1),
            "M+1": _to_int16(mem_val + 1),
            "D-1": _to_int16(reg_d - 1),
            "A-1": _to_int16(reg_a - 1),
            "M-1": _to_int16(mem_val - 1),
            "D+A": _to_int16(reg_d + reg_a),
            "D+M": _to_int16(reg_d + mem_val),
            "D-A": _to_int16(reg_d - reg_a),
            "D-M": _to_int16(reg_d - mem_val),
            "A-D": _to_int16(reg_a - reg_d),
            "M-D": _to_int16(mem_val - reg_d),
            "D&A": _to_int16(reg_d & reg_a),
            "D&M": _to_int16(reg_d & mem_val),
            "D|A": _to_int16(reg_d | reg_a),
            "D|M": _to_int16(reg_d | mem_val),
        }
        assert comp in alu_ops, f"Expressão ALU Hack inválida: {comp!r}"
        result = alu_ops[comp]

        if "M" in dest:
            ram[address] = result
        if "D" in dest:
            reg_d = result
        if "A" in dest:
            reg_a = result

        jump_conditions: dict[str, bool] = {
            "": False,
            "JGT": result > 0,
            "JEQ": result == 0,
            "JGE": result >= 0,
            "JLT": result < 0,
            "JNE": result != 0,
            "JLE": result <= 0,
            "JMP": True,
        }
        assert jump in jump_conditions, f"Condição de salto Hack inválida: {jump!r}"
        pc = address if jump_conditions[jump] else pc + 1

    assert stop_pc is None or pc == stop_pc, "Rótulo de parada não alcançado."
    return ram
