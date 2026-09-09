"""Validadores de campo. Cada uno devuelve un `FieldResult` explicable."""

from .contact import validate_email, validate_phone_es, validate_postal_code_es
from .iban import format_iban, validate_iban
from .identity import validate_tax_id

__all__ = [
    "validate_email",
    "validate_phone_es",
    "validate_postal_code_es",
    "validate_iban",
    "format_iban",
    "validate_tax_id",
]
