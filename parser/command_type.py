"""Enumeração dos tipos de comandos VM suportados pelo Parser."""

from enum import Enum


class CommandType(Enum):
    """Tipos de comandos da linguagem VM (Partes 1 e 2)."""

    C_ARITHMETIC = "C_ARITHMETIC"
    C_PUSH = "C_PUSH"
    C_POP = "C_POP"
    C_LABEL = "C_LABEL"
    C_GOTO = "C_GOTO"
    C_IF = "C_IF"
    C_FUNCTION = "C_FUNCTION"
    C_CALL = "C_CALL"
    C_RETURN = "C_RETURN"
