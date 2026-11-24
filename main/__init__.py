"""Módulo de entrada CLI e orquestração do tradutor VM."""

from main.cli import (
    CLIError,
    collect_program_symbols,
    main,
    resolve_io,
    translate,
    translate_file,
)

__all__ = [
    "CLIError",
    "collect_program_symbols",
    "main",
    "resolve_io",
    "translate",
    "translate_file",
]
