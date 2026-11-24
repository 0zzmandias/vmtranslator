"""Ponto de entrada CLI e orquestração da tradução VM -> Assembly Hack."""

from collections.abc import Sequence
import os
from pathlib import Path
import sys
import tempfile

from codewriter import CodeWriter, CodeWriterError
from parser import CommandType, Parser, ParserError


_SYMBOL_CATEGORY_LABELS: dict[str, str] = {
    "function": "função",
    "label": "rótulo",
    "static": "variável static",
}


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


def collect_program_symbols(
    vm_files: Sequence[Path],
    include_bootstrap: bool = False,
) -> set[str]:
    """Realiza pré-varredura dos arquivos .vm, valida colisões e retorna os símbolos reservados."""
    symbol_categories: dict[str, tuple[str, str]] = {}
    symbol_definitions: dict[str, tuple[str, str]] = {}

    def register_symbol(
        symbol: str,
        category: str,
        *,
        is_definition: bool,
        location: str,
    ) -> None:
        category_label = _SYMBOL_CATEGORY_LABELS[category]

        if is_definition and symbol in CodeWriter.PREDEFINED_HACK_SYMBOLS:
            raise CLIError(
                f"{location}: definição de {category_label} '{symbol}' conflita com "
                "símbolo predefinido da arquitetura Hack."
            )

        if symbol in symbol_categories:
            prev_category, prev_location = symbol_categories[symbol]
            if prev_category != category:
                prev_label = _SYMBOL_CATEGORY_LABELS[prev_category]
                raise CLIError(
                    f"{location}: colisão de símbolo Assembly '{symbol}' entre "
                    f"{category_label} e {prev_label} (registrado em {prev_location})."
                )

        if is_definition:
            if symbol in symbol_definitions:
                _, prev_def_location = symbol_definitions[symbol]
                raise CLIError(
                    f"{location}: definição duplicada de {category_label} '{symbol}' "
                    f"(já definido em {prev_def_location})."
                )
            symbol_definitions[symbol] = (category, location)

        if symbol not in symbol_categories:
            symbol_categories[symbol] = (category, location)

    if include_bootstrap:
        register_symbol(
            "Sys.init",
            "function",
            is_definition=False,
            location="bootstrap",
        )

    for vm_file in vm_files:
        file_name = vm_file.stem
        CodeWriter.validate_file_name(file_name)
        vm_parser = Parser(vm_file)
        current_function: str | None = None

        while vm_parser.hasMoreCommands():
            vm_parser.advance()
            command_type = vm_parser.commandType()
            location = f"{vm_file}:{vm_parser.current_line_number}"

            if command_type == CommandType.C_FUNCTION:
                func_name = vm_parser.arg1()
                register_symbol(
                    func_name,
                    "function",
                    is_definition=True,
                    location=location,
                )
                current_function = func_name
            elif command_type == CommandType.C_CALL:
                register_symbol(
                    vm_parser.arg1(),
                    "function",
                    is_definition=False,
                    location=location,
                )
            elif command_type == CommandType.C_LABEL:
                scoped = CodeWriter.format_scoped_label(
                    vm_parser.arg1(),
                    file_name=file_name,
                    function_name=current_function,
                )
                register_symbol(
                    scoped,
                    "label",
                    is_definition=True,
                    location=location,
                )
            elif command_type in (CommandType.C_GOTO, CommandType.C_IF):
                scoped = CodeWriter.format_scoped_label(
                    vm_parser.arg1(),
                    file_name=file_name,
                    function_name=current_function,
                )
                register_symbol(
                    scoped,
                    "label",
                    is_definition=False,
                    location=location,
                )
            elif command_type in (CommandType.C_PUSH, CommandType.C_POP):
                if vm_parser.arg1() == "static":
                    static_symbol = CodeWriter.format_static_symbol(
                        file_name,
                        vm_parser.arg2(),
                    )
                    register_symbol(
                        static_symbol,
                        "static",
                        is_definition=False,
                        location=location,
                    )

    return set(symbol_categories.keys())


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
    reserved_symbols = collect_program_symbols(
        vm_files,
        include_bootstrap=should_bootstrap,
    )

    fd, raw_temp_path = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(raw_temp_path)
    writer: CodeWriter | None = None
    close_attempted = False
    replaced = False

    try:
        os.close(fd)
        writer = CodeWriter(temp_path, reserved_symbols=reserved_symbols)
        if should_bootstrap:
            writer.writeInit()
        for vm_file in vm_files:
            translate_file(vm_file, writer)
        close_attempted = True
        writer.close()
        os.replace(temp_path, output_path)
        replaced = True
    finally:
        if writer is not None and not close_attempted:
            try:
                writer.close()
            except Exception:
                pass
        if not replaced:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

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
