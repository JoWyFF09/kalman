"""Capa de datos."""

from pathlib import Path

from .repository import Repository

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def load_schema() -> str:
    """Devuelve el SQL del esquema."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


__all__ = ["Repository", "load_schema", "SCHEMA_PATH"]
