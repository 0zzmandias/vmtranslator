"""Ponto de entrada CLI e orquestração da tradução VM -> Assembly Hack."""

from collections.abc import Sequence
from pathlib import Path
import sys

from codewriter import CodeWriter, CodeWriterError
from parser import CommandType, Parser, ParserError


class CLIError(Exception):
    """Erro de invocação ou resolução de entrada/saída na linha de comando."""


def resolve_io(input_arg: str) -> tuple[list[Path], Path, bool]:
    """Valida a entrada (arquivo .vm ou diretório) e resolve arquivos, saída .asm e bootstrap."""
    if not input_arg or not input_arg.strip():
        raise CLIError("Caminho de entrada não informado.")

    input_path = Path(input_arg)
    if not input_path.exists():
        raise CLIError(f"Arquivo de entrada não encontrado: '{input_path}'.")

    if input_path.is_dir():
        dir_name = input_path.resolve().name
        if not dir_name:
            raise CLIError(
                f"Não foi possível determinar o nome do arquivo '.asm' para o diretório '{input_path}'."
            )

        try:
            vm_files = sorted(
                (
                    entry
                    for entry in input_path.iterdir()
                    if entry.is_file() and entry.suffix == ".vm"
                ),
                key=lambda path: path.name,
            )
        except PermissionError as exc:
            raise CLIError(
                f"Sem permissão de leitura para o diretório '{input_path}'."
            ) from exc
        except OSError as exc:
            raise CLIError(
                f"Falha ao listar o diretório '{input_path}': {exc}"
            ) from exc

        if not vm_files:
            raise CLIError(
                f"Nenhum arquivo '.vm' encontrado no diretório '{input_path}'."
            )

        output_path = input_path / f"{dir_name}.asm"
        should_bootstrap = any(vm_file.name == "Sys.vm" for vm_file in vm_files)
        return vm_files, output_path, should_bootstrap

    if not input_path.is_file():
        raise CLIError(f"O caminho '{input_path}' não é um arquivo regular.")

    if input_path.suffix != ".vm":
        raise CLIError(
            f"Extensão inválida em '{input_path}': esperado arquivo '.vm'."
        )

    output_path = input_path.with_suffix(".asm")
    return [input_path], output_path, False


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
        elif command_type == CommandType.C_LABEL:
            code_writer.writeLabel(vm_parser.arg1())
        elif command_type == CommandType.C_GOTO:
            code_writer.writeGoto(vm_parser.arg1())
        elif command_type == CommandType.C_IF:
            code_writer.writeIf(vm_parser.arg1())
        elif command_type == CommandType.C_FUNCTION:
            code_writer.writeFunction(vm_parser.arg1(), vm_parser.arg2())
        elif command_type == CommandType.C_CALL:
            code_writer.writeCall(vm_parser.arg1(), vm_parser.arg2())
        elif command_type == CommandType.C_RETURN:
            code_writer.writeReturn()
        else:
            raise CLIError(f"Tipo de comando não suportado: '{command_type.value}'.")


def translate(input_arg: str) -> Path:
    """Executa o fluxo completo de tradução (arquivo ou diretório) e retorna o .asm gerado."""
    vm_files, output_path, should_bootstrap = resolve_io(input_arg)
    writer: CodeWriter | None = None

    try:
        writer = CodeWriter(output_path)
        if should_bootstrap:
            writer.writeInit()
        for vm_file in vm_files:
            translate_file(vm_file, writer)
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
        print(
            "Uso: vmtranslator <caminho/Arquivo.vm | caminho/Diretorio>",
            file=sys.stderr,
        )
        return 1

    try:
        translate(args[0])
    except (CLIError, ParserError, CodeWriterError, NotImplementedError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
