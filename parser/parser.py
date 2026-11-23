"""Analisador léxico e sintático para arquivos da linguagem VM."""

from dataclasses import dataclass
from pathlib import Path
import re

from parser.command_type import CommandType


_VM_IDENTIFIER_RE = re.compile(r"^[A-Za-z_.:][A-Za-z0-9_.:]*$")


class ParserError(Exception):
    """Erro de leitura ou análise sintática de um arquivo VM."""

    def __init__(
        self,
        detail: str,
        filename: str | Path | None = None,
        line_number: int | None = None,
    ) -> None:
        self.detail = detail
        self.filename = str(filename) if filename is not None else None
        self.line_number = line_number

        location = ""
        if self.filename is not None and self.line_number is not None:
            location = f"{self.filename}:{self.line_number}: "
        elif self.filename is not None:
            location = f"{self.filename}: "
        elif self.line_number is not None:
            location = f"linha {self.line_number}: "

        super().__init__(f"{location}{detail}")


@dataclass(frozen=True)
class ParsedCommand:
    """Representação estruturada de um comando VM já decomposto."""

    command_type: CommandType
    arg1: str | None
    arg2: int | None
    line_number: int
    raw_text: str


@dataclass(frozen=True)
class _CommandSpec:
    """Especificação declarativa de tipo e aridade de um comando VM."""

    command_type: CommandType
    expected_tokens: int
    arg1_is_self: bool = False
    has_arg1: bool = True
    has_arg2: bool = False
    validate_identifier: bool = False


_ARITHMETIC_SPEC = _CommandSpec(
    command_type=CommandType.C_ARITHMETIC,
    expected_tokens=1,
    arg1_is_self=True,
    has_arg1=True,
    has_arg2=False,
)

_COMMAND_SPECS: dict[str, _CommandSpec] = {
    "add": _ARITHMETIC_SPEC,
    "sub": _ARITHMETIC_SPEC,
    "neg": _ARITHMETIC_SPEC,
    "eq": _ARITHMETIC_SPEC,
    "gt": _ARITHMETIC_SPEC,
    "lt": _ARITHMETIC_SPEC,
    "and": _ARITHMETIC_SPEC,
    "or": _ARITHMETIC_SPEC,
    "not": _ARITHMETIC_SPEC,
    "push": _CommandSpec(
        command_type=CommandType.C_PUSH,
        expected_tokens=3,
        arg1_is_self=False,
        has_arg1=True,
        has_arg2=True,
    ),
    "pop": _CommandSpec(
        command_type=CommandType.C_POP,
        expected_tokens=3,
        arg1_is_self=False,
        has_arg1=True,
        has_arg2=True,
    ),
    "label": _CommandSpec(
        command_type=CommandType.C_LABEL,
        expected_tokens=2,
        arg1_is_self=False,
        has_arg1=True,
        has_arg2=False,
        validate_identifier=True,
    ),
    "goto": _CommandSpec(
        command_type=CommandType.C_GOTO,
        expected_tokens=2,
        arg1_is_self=False,
        has_arg1=True,
        has_arg2=False,
        validate_identifier=True,
    ),
    "if-goto": _CommandSpec(
        command_type=CommandType.C_IF,
        expected_tokens=2,
        arg1_is_self=False,
        has_arg1=True,
        has_arg2=False,
        validate_identifier=True,
    ),
    "function": _CommandSpec(
        command_type=CommandType.C_FUNCTION,
        expected_tokens=3,
        arg1_is_self=False,
        has_arg1=True,
        has_arg2=True,
        validate_identifier=True,
    ),
    "call": _CommandSpec(
        command_type=CommandType.C_CALL,
        expected_tokens=3,
        arg1_is_self=False,
        has_arg1=True,
        has_arg2=True,
        validate_identifier=True,
    ),
    "return": _CommandSpec(
        command_type=CommandType.C_RETURN,
        expected_tokens=1,
        arg1_is_self=False,
        has_arg1=False,
        has_arg2=False,
    ),
}


class Parser:
    """Lê um arquivo .vm, remove comentários/espaços e expõe um comando por vez."""

    def __init__(self, filename: str | Path) -> None:
        self._filepath = Path(filename)
        self._commands: list[ParsedCommand] = self._load_commands(self._filepath)
        self._index: int = -1
        self._current: ParsedCommand | None = None

    def _load_commands(self, filepath: Path) -> list[ParsedCommand]:
        if filepath.exists() and filepath.is_dir():
            raise ParserError(
                "Caminho informado é um diretório; esperado um arquivo .vm.",
                filename=filepath,
            )

        try:
            with filepath.open("r", encoding="utf-8") as source:
                raw_lines = source.readlines()
        except FileNotFoundError as exc:
            raise ParserError("Arquivo não encontrado.", filename=filepath) from exc
        except PermissionError as exc:
            raise ParserError(
                "Sem permissão de leitura para o arquivo.",
                filename=filepath,
            ) from exc
        except UnicodeDecodeError as exc:
            raise ParserError(
                "Arquivo não possui codificação UTF-8 válida.",
                filename=filepath,
            ) from exc
        except OSError as exc:
            raise ParserError(
                f"Falha ao ler arquivo: {exc}",
                filename=filepath,
            ) from exc

        commands: list[ParsedCommand] = []
        for line_number, raw_line in enumerate(raw_lines, start=1):
            clean_line = raw_line.split("//", 1)[0].strip()
            if not clean_line:
                continue
            tokens = clean_line.split()
            commands.append(self._parse_tokens(tokens, line_number))

        return commands

    def _parse_tokens(self, tokens: list[str], line_number: int) -> ParsedCommand:
        keyword = tokens[0]
        spec = _COMMAND_SPECS.get(keyword)
        if spec is None:
            raise ParserError(
                f"Comando VM desconhecido: '{keyword}'.",
                filename=self._filepath,
                line_number=line_number,
            )

        if len(tokens) != spec.expected_tokens:
            expected_args = spec.expected_tokens - 1
            received_args = len(tokens) - 1
            raise ParserError(
                f"Comando '{keyword}' espera {expected_args} argumento(s), "
                f"mas recebeu {received_args}.",
                filename=self._filepath,
                line_number=line_number,
            )

        if spec.arg1_is_self:
            arg1: str | None = tokens[0]
        elif spec.has_arg1:
            arg1 = tokens[1]
        else:
            arg1 = None

        if spec.validate_identifier and arg1 is not None:
            self._validate_identifier(arg1, keyword, line_number)

        arg2: int | None = None
        if spec.has_arg2:
            arg2 = self._parse_non_negative_int(tokens[2], keyword, line_number)

        return ParsedCommand(
            command_type=spec.command_type,
            arg1=arg1,
            arg2=arg2,
            line_number=line_number,
            raw_text=" ".join(tokens),
        )

    def _validate_identifier(
        self,
        token: str,
        keyword: str,
        line_number: int,
    ) -> None:
        if not _VM_IDENTIFIER_RE.fullmatch(token):
            raise ParserError(
                f"Identificador inválido '{token}' para o comando '{keyword}'. "
                "Use apenas letras, dígitos, '_', '.' ou ':', sem iniciar com dígito.",
                filename=self._filepath,
                line_number=line_number,
            )

    def _parse_non_negative_int(
        self,
        token: str,
        keyword: str,
        line_number: int,
    ) -> int:
        if not (token.isascii() and token.isdigit()):
            raise ParserError(
                f"Segundo argumento de '{keyword}' deve ser um inteiro não negativo, "
                f"mas recebeu '{token}'.",
                filename=self._filepath,
                line_number=line_number,
            )
        return int(token)

    def _require_current(self) -> ParsedCommand:
        if self._current is None:
            raise ParserError(
                "Nenhum comando ativo: chame advance() antes de consultar o comando atual.",
                filename=self._filepath,
            )
        return self._current

    def hasMoreCommands(self) -> bool:
        """Indica se ainda existem comandos a serem lidos."""
        return self._index + 1 < len(self._commands)

    def advance(self) -> None:
        """Avança para o próximo comando do arquivo."""
        if not self.hasMoreCommands():
            raise ParserError(
                "Não há mais comandos para avançar.",
                filename=self._filepath,
            )
        self._index += 1
        self._current = self._commands[self._index]

    def commandType(self) -> CommandType:
        """Retorna o tipo do comando atual."""
        return self._require_current().command_type

    def arg1(self) -> str:
        """Retorna o primeiro argumento do comando atual (ou o próprio comando aritmético)."""
        current = self._require_current()
        if current.arg1 is None:
            raise ParserError(
                f"O comando '{current.command_type.value}' não possui arg1.",
                filename=self._filepath,
                line_number=current.line_number,
            )
        return current.arg1

    def arg2(self) -> int:
        """Retorna o segundo argumento inteiro do comando atual."""
        current = self._require_current()
        if current.arg2 is None:
            raise ParserError(
                f"O comando '{current.command_type.value}' não possui arg2.",
                filename=self._filepath,
                line_number=current.line_number,
            )
        return current.arg2

    @property
    def current_line_number(self) -> int:
        """Retorna o número da linha original do comando atual no arquivo .vm."""
        return self._require_current().line_number
