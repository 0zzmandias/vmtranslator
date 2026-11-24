"""Gerador de código Assembly Hack a partir de comandos da linguagem VM."""

from collections.abc import Callable, Iterable
from pathlib import Path
import re
from types import TracebackType
from typing import Self


_HACK_SYMBOL_RE = re.compile(r"[A-Za-z_.$:][A-Za-z0-9_.$:]*")
_VM_IDENTIFIER_RE = re.compile(r"[A-Za-z_.:][A-Za-z0-9_.:]*")
_DEFAULT_FUNCTION_SCOPE = "GLOBAL"
_MAX_INDEX = 32767
_TEMP_BASE = 5
_MAX_TEMP_INDEX = 7
_CALL_FRAME_SIZE = 5

_PREDEFINED_HACK_SYMBOLS: frozenset[str] = frozenset(
    {
        "SP",
        "LCL",
        "ARG",
        "THIS",
        "THAT",
        "SCREEN",
        "KBD",
        *(f"R{index}" for index in range(16)),
    }
)

_BINARY_ARITHMETIC_OPS: dict[str, str] = {
    "add": "M=D+M",
    "sub": "M=M-D",
    "and": "M=D&M",
    "or": "M=D|M",
}

_UNARY_ARITHMETIC_OPS: dict[str, str] = {
    "neg": "M=-M",
    "not": "M=!M",
}

_COMPARISON_JUMPS: dict[str, str] = {
    "eq": "JEQ",
    "gt": "JGT",
    "lt": "JLT",
}

_INDIRECT_SEGMENTS: dict[str, str] = {
    "local": "LCL",
    "argument": "ARG",
    "this": "THIS",
    "that": "THAT",
}

_POINTER_SEGMENTS: dict[int, str] = {
    0: "THIS",
    1: "THAT",
}

_VALID_ARITHMETIC_COMMANDS = frozenset(
    _BINARY_ARITHMETIC_OPS | _UNARY_ARITHMETIC_OPS | _COMPARISON_JUMPS
)

_VALID_SEGMENTS = frozenset(
    {"constant", "temp", "pointer", "static"} | _INDIRECT_SEGMENTS.keys()
)


class CodeWriterError(Exception):
    """Erro semântico ou de E/S durante a geração de código Assembly Hack."""


class CodeWriter:
    """Traduz comandos VM para Assembly Hack e grava no arquivo .asm de saída."""

    PREDEFINED_HACK_SYMBOLS: frozenset[str] = _PREDEFINED_HACK_SYMBOLS

    def __init__(
        self,
        output_path: str | Path,
        reserved_symbols: Iterable[str] | None = None,
    ) -> None:
        self._output_path = Path(output_path)
        self._file_name: str | None = None
        self._current_function: str | None = None
        self._label_counter: int = 0
        self._reserved_symbols: set[str] = set(_PREDEFINED_HACK_SYMBOLS)
        if reserved_symbols is not None:
            self._reserved_symbols.update(reserved_symbols)
        self._closed: bool = False

        try:
            self._file = self._output_path.open("w", encoding="utf-8", newline="\n")
        except OSError as exc:
            raise CodeWriterError(
                f"Não foi possível abrir o arquivo de saída '{self._output_path}': {exc}"
            ) from exc

    @staticmethod
    def validate_file_name(name: str) -> None:
        """Valida se o nome base do arquivo .vm é um símbolo Assembly Hack válido."""
        if not isinstance(name, str) or not name or not _HACK_SYMBOL_RE.fullmatch(name):
            raise CodeWriterError(
                f"Nome de arquivo inválido para símbolos Assembly Hack: {name!r}."
            )

    @staticmethod
    def format_scope(
        file_name: str | None = None,
        function_name: str | None = None,
    ) -> str:
        """Resolve o prefixo de escopo Assembly para função corrente, arquivo ou global."""
        if function_name is not None:
            return function_name
        if file_name is not None:
            return f"{_DEFAULT_FUNCTION_SCOPE}${file_name}"
        return _DEFAULT_FUNCTION_SCOPE

    @staticmethod
    def format_scoped_label(
        label: str,
        file_name: str | None = None,
        function_name: str | None = None,
    ) -> str:
        """Retorna o nome Assembly final de um rótulo VM no escopo informado."""
        scope = CodeWriter.format_scope(
            file_name=file_name,
            function_name=function_name,
        )
        return f"{scope}${label}"

    @staticmethod
    def format_static_symbol(file_name: str, index: int) -> str:
        """Retorna o nome Assembly final de uma variável do segmento static."""
        return f"{file_name}.{index}"

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise CodeWriterError(
                "Não é possível escrever após o fechamento do CodeWriter."
            )

    def _validate_non_negative_int(self, value: int, context: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CodeWriterError(
                f"Índice inválido para {context}: esperado inteiro não negativo, "
                f"recebido {value!r}."
            )

    def _validate_15bit_index(self, index: int, context: str) -> None:
        if index > _MAX_INDEX:
            raise CodeWriterError(
                f"Índice fora do limite de 15 bits (0..{_MAX_INDEX}) para {context}: {index}."
            )

    def _validate_identifier(self, name: str, context: str) -> None:
        if not isinstance(name, str) or not _VM_IDENTIFIER_RE.fullmatch(name):
            raise CodeWriterError(
                f"Identificador inválido para {context}: {name!r}."
            )

    def _validate_function_name(self, name: str, context: str) -> None:
        self._validate_identifier(name, context)
        if name in _PREDEFINED_HACK_SYMBOLS:
            raise CodeWriterError(
                f"Identificador '{name}' para {context} conflita com "
                "símbolo predefinido da arquitetura Hack."
            )

    def _current_scope(self) -> str:
        return self.format_scope(
            file_name=self._file_name,
            function_name=self._current_function,
        )

    def _scoped_label(self, label: str) -> str:
        return self.format_scoped_label(
            label,
            file_name=self._file_name,
            function_name=self._current_function,
        )

    def _require_file_name(self) -> str:
        if self._file_name is None:
            raise CodeWriterError(
                "Nome do arquivo .vm não definido: chame setFileName() antes de acessar 'static'."
            )
        return self._file_name

    def _next_label_id(self) -> int:
        label_id = self._label_counter
        self._label_counter += 1
        return label_id

    def _allocate_internal_labels(
        self,
        build_labels: Callable[[int], tuple[str, ...]],
    ) -> tuple[str, ...]:
        """Reserva atomicamente um conjunto de rótulos internos livres de colisão."""
        while True:
            label_id = self._next_label_id()
            candidates = build_labels(label_id)
            if all(symbol not in self._reserved_symbols for symbol in candidates):
                self._reserved_symbols.update(candidates)
                return candidates

    def _write_lines(self, lines: list[str]) -> None:
        self._ensure_open()
        try:
            self._file.write("\n".join(lines) + "\n")
        except OSError as exc:
            raise CodeWriterError(
                f"Falha ao gravar no arquivo '{self._output_path}': {exc}"
            ) from exc

    def _push_d(self) -> list[str]:
        """Retorna instruções Hack para empilhar o valor em D e incrementar SP."""
        return [
            "@SP",
            "A=M",
            "M=D",
            "@SP",
            "M=M+1",
        ]

    def _pop_to_d(self) -> list[str]:
        """Retorna instruções Hack para decrementar SP e carregar o topo em D."""
        return [
            "@SP",
            "AM=M-1",
            "D=M",
        ]

    def setFileName(self, name: str) -> None:
        """Define o nome do arquivo .vm corrente (sem extensão) para símbolos static."""
        self._ensure_open()
        self.validate_file_name(name)
        self._file_name = name
        self._current_function = None

    def writeInit(self) -> None:
        """Emite o código de bootstrap: SP = 256 seguido de call Sys.init 0."""
        self._ensure_open()
        self._write_lines(
            [
                "// bootstrap",
                "@256",
                "D=A",
                "@SP",
                "M=D",
            ]
        )
        self.writeCall("Sys.init", 0)

    def writeArithmetic(self, cmd: str) -> None:
        """Traduz um comando aritmético ou lógico para Assembly Hack."""
        self._ensure_open()
        if cmd not in _VALID_ARITHMETIC_COMMANDS:
            raise CodeWriterError(f"Comando aritmético/lógico inválido: '{cmd}'.")

        if cmd in _BINARY_ARITHMETIC_OPS:
            operation = _BINARY_ARITHMETIC_OPS[cmd]
            self._write_lines(
                [
                    f"// {cmd}",
                    "@SP",
                    "AM=M-1",
                    "D=M",
                    "A=A-1",
                    operation,
                ]
            )
            return

        if cmd in _UNARY_ARITHMETIC_OPS:
            operation = _UNARY_ARITHMETIC_OPS[cmd]
            self._write_lines(
                [
                    f"// {cmd}",
                    "@SP",
                    "A=M-1",
                    operation,
                ]
            )
            return

        jump = _COMPARISON_JUMPS[cmd]
        cmd_upper = cmd.upper()

        if cmd == "eq":
            true_label, end_label = self._allocate_internal_labels(
                lambda label_id: (
                    f"VM_{cmd_upper}_TRUE_{label_id}",
                    f"VM_{cmd_upper}_END_{label_id}",
                )
            )
            self._write_lines(
                [
                    f"// {cmd}",
                    "@SP",
                    "AM=M-1",
                    "D=M",
                    "A=A-1",
                    "D=M-D",
                    f"@{true_label}",
                    f"D;{jump}",
                    "@SP",
                    "A=M-1",
                    "M=0",
                    f"@{end_label}",
                    "0;JMP",
                    f"({true_label})",
                    "@SP",
                    "A=M-1",
                    "M=-1",
                    f"({end_label})",
                ]
            )
            return

        # gt e lt: verifica sinais de x e y antes de subtrair para evitar overflow em 16 bits
        (
            x_neg_label,
            same_sign_label,
            false_label,
            true_label,
            end_label,
        ) = self._allocate_internal_labels(
            lambda label_id: (
                f"VM_{cmd_upper}_XNEG_{label_id}",
                f"VM_{cmd_upper}_SAME_{label_id}",
                f"VM_{cmd_upper}_FALSE_{label_id}",
                f"VM_{cmd_upper}_TRUE_{label_id}",
                f"VM_{cmd_upper}_END_{label_id}",
            )
        )
        if cmd == "gt":
            x_nonneg_y_neg_target = true_label
            x_neg_y_nonneg_target = false_label
        else:
            x_nonneg_y_neg_target = false_label
            x_neg_y_nonneg_target = true_label

        self._write_lines(
            [
                f"// {cmd}",
                "@SP",
                "AM=M-1",
                "D=M",
                "@R13",
                "M=D",
                "@SP",
                "A=M-1",
                "D=M",
                f"@{x_neg_label}",
                "D;JLT",
                "@R13",
                "D=M",
                f"@{same_sign_label}",
                "D;JGE",
                f"@{x_nonneg_y_neg_target}",
                "0;JMP",
                f"({x_neg_label})",
                "@R13",
                "D=M",
                f"@{same_sign_label}",
                "D;JLT",
                f"@{x_neg_y_nonneg_target}",
                "0;JMP",
                f"({same_sign_label})",
                "@R13",
                "D=M",
                "@SP",
                "A=M-1",
                "D=M-D",
                f"@{true_label}",
                f"D;{jump}",
                f"({false_label})",
                "@SP",
                "A=M-1",
                "M=0",
                f"@{end_label}",
                "0;JMP",
                f"({true_label})",
                "@SP",
                "A=M-1",
                "M=-1",
                f"({end_label})",
            ]
        )

    def writePush(self, segment: str, index: int) -> None:
        """Traduz um comando push para o segmento e índice informados."""
        self._ensure_open()
        if segment not in _VALID_SEGMENTS:
            raise CodeWriterError(f"Segmento de memória inválido: '{segment}'.")
        self._validate_non_negative_int(index, f"push {segment}")

        if segment == "constant":
            self._validate_15bit_index(index, "push constant")
            self._write_lines(
                [
                    f"// push constant {index}",
                    f"@{index}",
                    "D=A",
                    *self._push_d(),
                ]
            )
            return

        if segment in _INDIRECT_SEGMENTS:
            self._validate_15bit_index(index, f"push {segment}")
            base_symbol = _INDIRECT_SEGMENTS[segment]
            self._write_lines(
                [
                    f"// push {segment} {index}",
                    f"@{base_symbol}",
                    "D=M",
                    f"@{index}",
                    "A=D+A",
                    "D=M",
                    *self._push_d(),
                ]
            )
            return

        if segment == "temp":
            if index > _MAX_TEMP_INDEX:
                raise CodeWriterError(
                    f"Índice fora do intervalo permitido para temp (0..{_MAX_TEMP_INDEX}): {index}."
                )
            self._write_lines(
                [
                    f"// push temp {index}",
                    f"@{_TEMP_BASE + index}",
                    "D=M",
                    *self._push_d(),
                ]
            )
            return

        if segment == "pointer":
            pointer_symbol = _POINTER_SEGMENTS.get(index)
            if pointer_symbol is None:
                raise CodeWriterError(
                    f"Índice fora do intervalo permitido para pointer (0 ou 1): {index}."
                )
            self._write_lines(
                [
                    f"// push pointer {index}",
                    f"@{pointer_symbol}",
                    "D=M",
                    *self._push_d(),
                ]
            )
            return

        # segment == "static"
        self._validate_15bit_index(index, "push static")
        file_name = self._require_file_name()
        static_symbol = self.format_static_symbol(file_name, index)
        self._reserved_symbols.add(static_symbol)
        self._write_lines(
            [
                f"// push static {index}",
                f"@{static_symbol}",
                "D=M",
                *self._push_d(),
            ]
        )

    def writePop(self, segment: str, index: int) -> None:
        """Traduz um comando pop para o segmento e índice informados."""
        self._ensure_open()
        if segment not in _VALID_SEGMENTS:
            raise CodeWriterError(f"Segmento de memória inválido: '{segment}'.")
        self._validate_non_negative_int(index, f"pop {segment}")

        if segment == "constant":
            raise CodeWriterError(
                "Operação inválida: não existe 'pop' para o segmento 'constant'."
            )

        if segment in _INDIRECT_SEGMENTS:
            self._validate_15bit_index(index, f"pop {segment}")
            base_symbol = _INDIRECT_SEGMENTS[segment]
            self._write_lines(
                [
                    f"// pop {segment} {index}",
                    f"@{base_symbol}",
                    "D=M",
                    f"@{index}",
                    "D=D+A",
                    "@R13",
                    "M=D",
                    *self._pop_to_d(),
                    "@R13",
                    "A=M",
                    "M=D",
                ]
            )
            return

        if segment == "temp":
            if index > _MAX_TEMP_INDEX:
                raise CodeWriterError(
                    f"Índice fora do intervalo permitido para temp (0..{_MAX_TEMP_INDEX}): {index}."
                )
            self._write_lines(
                [
                    f"// pop temp {index}",
                    *self._pop_to_d(),
                    f"@{_TEMP_BASE + index}",
                    "M=D",
                ]
            )
            return

        if segment == "pointer":
            pointer_symbol = _POINTER_SEGMENTS.get(index)
            if pointer_symbol is None:
                raise CodeWriterError(
                    f"Índice fora do intervalo permitido para pointer (0 ou 1): {index}."
                )
            self._write_lines(
                [
                    f"// pop pointer {index}",
                    *self._pop_to_d(),
                    f"@{pointer_symbol}",
                    "M=D",
                ]
            )
            return

        # segment == "static"
        self._validate_15bit_index(index, "pop static")
        file_name = self._require_file_name()
        static_symbol = self.format_static_symbol(file_name, index)
        self._reserved_symbols.add(static_symbol)
        self._write_lines(
            [
                f"// pop static {index}",
                *self._pop_to_d(),
                f"@{static_symbol}",
                "M=D",
            ]
        )

    def writeLabel(self, label: str) -> None:
        """Traduz o comando label com qualificação pelo escopo corrente."""
        self._ensure_open()
        self._validate_identifier(label, "label")
        scoped = self._scoped_label(label)
        self._reserved_symbols.add(scoped)
        self._write_lines(
            [
                f"// label {label}",
                f"({scoped})",
            ]
        )

    def writeGoto(self, label: str) -> None:
        """Traduz o comando goto (salto incondicional)."""
        self._ensure_open()
        self._validate_identifier(label, "goto")
        scoped = self._scoped_label(label)
        self._reserved_symbols.add(scoped)
        self._write_lines(
            [
                f"// goto {label}",
                f"@{scoped}",
                "0;JMP",
            ]
        )

    def writeIf(self, label: str) -> None:
        """Traduz o comando if-goto (salta se o valor desempilhado for diferente de 0)."""
        self._ensure_open()
        self._validate_identifier(label, "if-goto")
        scoped = self._scoped_label(label)
        self._reserved_symbols.add(scoped)
        self._write_lines(
            [
                f"// if-goto {label}",
                *self._pop_to_d(),
                f"@{scoped}",
                "D;JNE",
            ]
        )

    def writeFunction(self, function_name: str, num_vars: int) -> None:
        """Traduz a declaração de função, atualizando o escopo e zerando num_vars locais."""
        self._ensure_open()
        self._validate_function_name(function_name, "function")
        self._validate_non_negative_int(num_vars, "function")
        self._validate_15bit_index(num_vars, "function")

        self._current_function = function_name
        self._reserved_symbols.add(function_name)
        lines = [
            f"// function {function_name} {num_vars}",
            f"({function_name})",
        ]
        for _ in range(num_vars):
            lines.extend(
                [
                    "@SP",
                    "A=M",
                    "M=0",
                    "@SP",
                    "M=M+1",
                ]
            )
        self._write_lines(lines)

    def writeCall(self, function_name: str, num_args: int) -> None:
        """Traduz a chamada de função salvando o frame do chamador e saltando para function_name."""
        self._ensure_open()
        self._validate_function_name(function_name, "call")
        self._validate_non_negative_int(num_args, "call")
        arg_offset = _CALL_FRAME_SIZE + num_args
        self._validate_15bit_index(arg_offset, "call")

        self._reserved_symbols.add(function_name)
        scope = self._current_scope()
        (return_label,) = self._allocate_internal_labels(
            lambda label_id: (f"{scope}$ret.{label_id}",)
        )
        lines = [
            f"// call {function_name} {num_args}",
            f"@{return_label}",
            "D=A",
            *self._push_d(),
        ]
        for segment_symbol in ("LCL", "ARG", "THIS", "THAT"):
            lines.extend(
                [
                    f"@{segment_symbol}",
                    "D=M",
                    *self._push_d(),
                ]
            )
        lines.extend(
            [
                "@SP",
                "D=M",
                f"@{arg_offset}",
                "D=D-A",
                "@ARG",
                "M=D",
                "@SP",
                "D=M",
                "@LCL",
                "M=D",
                f"@{function_name}",
                "0;JMP",
                f"({return_label})",
            ]
        )
        self._write_lines(lines)

    def writeReturn(self) -> None:
        """Traduz o retorno de função restaurando o frame do chamador."""
        self._ensure_open()
        self._write_lines(
            [
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
                *self._pop_to_d(),
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
        )

    def close(self) -> None:
        """Fecha o arquivo .asm de saída."""
        if not self._closed:
            self._file.close()
            self._closed = True
