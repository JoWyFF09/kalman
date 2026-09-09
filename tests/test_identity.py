"""Pruebas de NIF, NIE y CIF.

Los casos válidos son identificadores públicos de ejemplo o construidos con el
algoritmo oficial. Los inválidos son el mismo identificador con el dígito de
control cambiado, que es el error real que comete una persona al teclear.
"""

from __future__ import annotations

import pytest

from kalman.core.validators.identity import (
    clean_id,
    nif_control_letter,
    validate_tax_id,
)


@pytest.mark.parametrize(
    "value",
    [
        "12345678Z",   # NIF de ejemplo canónico
        "00000000T",   # Caso límite: resto cero
        "99999999R",
        "12345678-Z",  # Con separador
        "12.345.678 Z",
        "es12345678z",  # Con prefijo intracomunitario y en minúsculas
    ],
)
def test_nif_valido(value: str) -> None:
    assert validate_tax_id(value).ok


@pytest.mark.parametrize("value", ["12345678A", "12345678B", "00000000A"])
def test_nif_letra_incorrecta(value: str) -> None:
    result = validate_tax_id(value)
    assert not result.ok
    assert result.rule == "tax_id.nif.checksum"


@pytest.mark.parametrize("value", ["X1234567L", "Y1234567X", "Z1234567R"])
def test_nie_valido(value: str) -> None:
    assert validate_tax_id(value).ok


def test_nie_letra_incorrecta() -> None:
    result = validate_tax_id("X1234567M")
    assert not result.ok
    assert result.rule == "tax_id.nie.checksum"


@pytest.mark.parametrize(
    "value",
    [
        "A58818501",  # Entidad tipo A, control numérico obligatorio
        "B65410011",
        "Q2826000H",  # Organismo público, control alfabético obligatorio
    ],
)
def test_cif_valido(value: str) -> None:
    result = validate_tax_id(value)
    assert result.ok, result.message


def test_cif_control_incorrecto() -> None:
    result = validate_tax_id("A58818500")
    assert not result.ok
    assert result.rule == "tax_id.cif.checksum"


def test_cif_letra_obligatoria_no_acepta_digito() -> None:
    """Una entidad Q debe llevar letra de control, nunca cifra."""
    letra = validate_tax_id("Q2826000H")
    assert letra.ok
    digito = validate_tax_id("Q28260007")
    assert not digito.ok


@pytest.mark.parametrize(
    "value,rule",
    [
        (None, "tax_id.missing"),
        ("", "tax_id.missing"),
        ("   ", "tax_id.missing"),
        ("1234567Z", "tax_id.length"),
        ("123456789012", "tax_id.length"),
        ("ÑÑÑÑÑÑÑÑÑ", "tax_id.format"),
    ],
)
def test_casos_invalidos(value: object, rule: str) -> None:
    result = validate_tax_id(value)
    assert not result.ok
    assert result.rule == rule


def test_clean_id_quita_separadores() -> None:
    assert clean_id(" 12.345.678-z ") == "12345678Z"


def test_letra_de_control_coincide_con_tabla_oficial() -> None:
    """La letra sólo depende del resto módulo 23."""
    assert nif_control_letter(0) == "T"
    assert nif_control_letter(23) == "T"
    assert nif_control_letter(14) == "Z"


def test_todo_nif_generado_se_valida() -> None:
    """Propiedad: cualquier NIF construido con el algoritmo debe validar.

    Cubre los 23 restos posibles, que es el espacio completo del algoritmo.
    """
    for number in range(0, 23 * 40, 37):
        candidate = f"{number:08d}{nif_control_letter(number)}"
        assert validate_tax_id(candidate).ok, candidate
