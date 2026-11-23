"""Gerador de código Assembly Hack a partir de comandos da linguagem VM."""

from pathlib import Path
import re
from types import TracebackType
from typing import Self


_HACK_SYMBOL_RE = re.compile(r"^[A-Za-z_.$:][A-Za-z0-9_.$:]*$")
_MAX_CONSTANT = 32767

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

_VALID_ARITHMETIC_COMMANDS = frozenset(
    _BINARY_ARITHMETIC_OPS | _UNARY_ARITHMETIC_OPS | _COMPARISON_JUMPS
)

_VALID_SEGMENTS = frozenset(
    {"constant", "local", "argument", "this", "that", "temp", "pointer", "static"}
)


class CodeWriterError(Exception):
    """Erro semântico ou de E/S durante a geração de código Assembly Hack."""


class CodeWriter:
    """Traduz comandos VM para Assembly Hack e grava no arquivo .asm de saída."""

    def __init__(self, output_path: str | Path) -> None:
        self._output_path = Path(output_path)
        self._file_name: str | None = None
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
            if index > _MAX_CONSTANT:
                raise CodeWriterError(
                    f"Valor fora do limite de 15 bits para constant (0..{_MAX_CONSTANT}): {index}."
                )
            self._write_lines(
                [
                    f"// push constant {index}",
                    f"@{index}",
                    "D=A",
                    *self._push_d(),
                ]
            )
            return

        raise NotImplementedError(
            f"Operação 'push {segment}' ainda não implementada."
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

        raise NotImplementedError(
            f"Operação 'pop {segment}' ainda não implementada."
        )

    def close(self) -> None:
        """Fecha o arquivo .asm de saída."""
        if not self._closed:
            self._file.close()
            self._closed = True
