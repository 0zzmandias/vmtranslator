"""Ponto de entrada CLI e orquestração da tradução VM -> Assembly Hack."""

from collections.abc import Sequence
from pathlib import Path
import sys

from codewriter import CodeWriter, CodeWriterError
from parser import CommandType, Parser, ParserError


class CLIError(Exception):
    """Erro de invocação ou resolução de entrada/saída na linha de comando."""


def resolve_io(input_arg: str) -> tuple[Path, Path]:
    """Valida a entrada da Parte 1 (arquivo .vm) e determina o caminho .asm de saída."""
    if not input_arg or not input_arg.strip():
        raise CLIError("Caminho de entrada não informado.")

    input_path = Path(input_arg)
    if not input_path.exists():
        raise CLIError(f"Arquivo de entrada não encontrado: '{input_path}'.")

    if input_path.is_dir():
        raise CLIError(
            f"O caminho '{input_path}' é um diretório. "
            "Na Parte 1, informe um único arquivo com extensão .vm."
        )

    if not input_path.is_file():
        raise CLIError(f"O caminho '{input_path}' não é um arquivo regular.")

    if input_path.suffix != ".vm":
        raise CLIError(
            f"Extensão inválida em '{input_path}': esperado arquivo '.vm'."
        )

    output_path = input_path.with_suffix(".asm")
    return input_path, output_path


def translate_file(vm_path: Path, code_writer: CodeWriter) -> None:
    """Traduz um único arquivo .vm utilizando um CodeWriter já aberto."""
    code_writer.setFileName(vm_path.stem)
    vm_parser = Parser(vm_path)

    while vm_parser.hasMoreCommands():
        vm_parser.advance()
        command_type = vm_parser.commandType()

        if command_type == CommandType.C_ARITHMETIC:
            code_writer.writeArithmetic(vm_parser.arg1())
        elif command_type == CommandType.C_PUSH:
            code_writer.writePush(vm_parser.arg1(), vm_parser.arg2())
        elif command_type == CommandType.C_POP:
            code_writer.writePop(vm_parser.arg1(), vm_parser.arg2())
        else:
            raise CLIError(f"Tipo de comando não suportado: '{command_type.value}'.")


def translate(input_arg: str) -> Path:
    """Executa o fluxo completo de tradução para um arquivo .vm e retorna o .asm gerado."""
    input_path, output_path = resolve_io(input_arg)
    writer: CodeWriter | None = None

    try:
        writer = CodeWriter(output_path)
        translate_file(input_path, writer)
    except Exception:
        if writer is not None:
            writer.close()
            output_path.unlink(missing_ok=True)
        raise
    else:
        writer.close()

    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    """Função principal da CLI do vmtranslator."""
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1:
        print("Uso: vmtranslator <caminho/Arquivo.vm>", file=sys.stderr)
        return 1

    try:
        translate(args[0])
    except (CLIError, ParserError, CodeWriterError, NotImplementedError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
