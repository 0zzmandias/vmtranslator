"""Gerador de código Assembly Hack a partir de comandos da linguagem VM."""

from pathlib import Path
import re
from types import TracebackType
from typing import Self


_HACK_SYMBOL_RE = re.compile(r"^[A-Za-z_.$:][A-Za-z0-9_.$:]*$")
_VM_IDENTIFIER_RE = re.compile(r"^[A-Za-z_.:][A-Za-z0-9_.:]*$")
_DEFAULT_FUNCTION_SCOPE = "GLOBAL"
_MAX_INDEX = 32767
_TEMP_BASE = 5
_MAX_TEMP_INDEX = 7

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

    def __init__(self, output_path: str | Path) -> None:
        self._output_path = Path(output_path)
        self._file_name: str | None = None
        self._current_function: str = _DEFAULT_FUNCTION_SCOPE
        self._label_counter: int = 0
        self._closed: bool = False

        try:
            self._file = self._output_path.open("w", encoding="utf-8", newline="\n")
        except OSError as exc:
            raise CodeWriterError(
                f"Não foi possível abrir o arquivo de saída '{self._output_path}': {exc}"
            ) from exc

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

    def _scoped_label(self, label: str) -> str:
        return f"{self._current_function}${label}"

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
        if not isinstance(name, str) or not name or not _HACK_SYMBOL_RE.match(name):
            raise CodeWriterError(
                f"Nome de arquivo inválido para símbolos Assembly Hack: {name!r}."
            )
        self._file_name = name
        self._current_function = _DEFAULT_FUNCTION_SCOPE

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
        label_id = self._next_label_id()
        true_label = f"VM_{cmd.upper()}_TRUE_{label_id}"
        end_label = f"VM_{cmd.upper()}_END_{label_id}"
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
        self._write_lines(
            [
                f"// push static {index}",
                f"@{file_name}.{index}",
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
        self._write_lines(
            [
                f"// pop static {index}",
                *self._pop_to_d(),
                f"@{file_name}.{index}",
                "M=D",
            ]
        )

    def writeLabel(self, label: str) -> None:
        """Traduz o comando label com qualificação pelo escopo da função corrente."""
        self._ensure_open()
        self._validate_identifier(label, "label")
        scoped = self._scoped_label(label)
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
        self._write_lines(
            [
                f"// if-goto {label}",
                *self._pop_to_d(),
                f"@{scoped}",
                "D;JNE",
            ]
        )

    def close(self) -> None:
        """Fecha o arquivo .asm de saída."""
        if not self._closed:
            self._file.close()
            self._closed = True
