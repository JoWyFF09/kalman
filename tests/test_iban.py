"""Pruebas del validador de IBAN."""

from __future__ import annotations

import pytest

from kalman.core.validators.iban import format_iban, mod97, validate_iban


@pytest.mark.parametrize(
    "value",
    [
        "ES9121000418450200051332",       # Ejemplo oficial de IBAN español
        "ES91 2100 0418 4502 0005 1332",  # Con los espacios que usa el banco
        "es9121000418450200051332",       # En minúsculas
        "ES91-2100-0418-4502-0005-1332",  # Con guiones
        "DE89370400440532013000",
        "FR1420041010050500013M02606",    # Con letra en el cuerpo
        "GB29NWBK60161331926819",
        "PT50000201231234567890154",
    ],
)
def test_iban_valido(value: str) -> None:
    result = validate_iban(value)
    assert result.ok, result.message


def test_iban_normaliza_a_forma_canonica() -> None:
    result = validate_iban("ES91 2100 0418 4502 0005 1332")
    assert result.normalized == "ES9121000418450200051332"


def test_digito_de_control_alterado_se_detecta() -> None:
    """Cambiar una sola cifra debe romper el mod-97.

    Es la garantía que vende el producto: una errata de tecleo no pasa.
    """
    result = validate_iban("ES9121000418450200051333")
    assert not result.ok
    assert result.rule == "iban.checksum"


def test_digitos_transpuestos_se_detectan() -> None:
    """El error humano más común es intercambiar dos cifras contiguas."""
    result = validate_iban("ES9121000418450200051323")
    assert not result.ok


@pytest.mark.parametrize(
    "value,rule",
    [
        (None, "iban.missing"),
        ("", "iban.missing"),
        ("1234", "iban.format"),
        ("ESXX2100041845", "iban.format"),
        ("ES91210004184502000513", "iban.length"),
    ],
)
def test_casos_invalidos(value: object, rule: str) -> None:
    result = validate_iban(value)
    assert not result.ok
    assert result.rule == rule


def test_mod97_de_un_iban_valido_es_uno() -> None:
    assert mod97("ES9121000418450200051332") == 1


def test_format_iban_agrupa_de_cuatro_en_cuatro() -> None:
    assert format_iban("ES9121000418450200051332") == "ES91 2100 0418 4502 0005 1332"
