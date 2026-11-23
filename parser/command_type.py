"""Enumeração dos tipos de comandos VM suportados pelo Parser."""

from enum import Enum


class CommandType(Enum):
    """Tipos de comandos da linguagem VM (Parte 1)."""

    C_ARITHMETIC = "C_ARITHMETIC"
    C_PUSH = "C_PUSH"
    C_POP = "C_POP"
