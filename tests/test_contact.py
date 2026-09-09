"""Pruebas de email, teléfono y código postal."""

from __future__ import annotations

import pytest

from kalman.core.validators.contact import (
    validate_email,
    validate_phone_es,
    validate_postal_code_es,
)


@pytest.mark.parametrize(
    "value",
    ["joel@empresa.es", "a.b+etiqueta@sub.dominio.com", "  JOEL@EMPRESA.ES  "],
)
def test_email_valido(value: str) -> None:
    assert validate_email(value).ok


def test_email_se_normaliza_a_minusculas() -> None:
    assert validate_email("  JOEL@Empresa.ES ").normalized == "joel@empresa.es"


@pytest.mark.parametrize(
    "value,rule",
    [
        (None, "email.missing"),
        ("", "email.missing"),
        ("no_email.com", "email.syntax"),
        ("sin@arroba", "email.syntax"),
        ("dos@@arrobas.com", "email.syntax"),
        ("test@test.com", "email.placeholder"),
        # "n/a" lo trata `text_value` como ausencia de dato, igual que un nulo
        # de pandas. La gravedad es la misma y el motivo es más exacto.
        ("n/a", "email.missing"),
    ],
)
def test_email_invalido(value: object, rule: str) -> None:
    result = validate_email(value)
    assert not result.ok
    assert result.rule == rule


def test_email_con_errata_de_dominio_propone_correccion() -> None:
    result = validate_email("joel@gmail.con")
    assert not result.ok
    assert result.rule == "email.typo"
    assert result.normalized == "joel@gmail.com"
    assert result.confidence >= 0.8


def test_email_desechable_es_aviso_no_error() -> None:
    """Un correo desechable es sintácticamente correcto pero comercialmente inútil."""
    result = validate_email("alguien@mailinator.com")
    assert not result.ok
    assert result.rule == "email.disposable"
    assert result.severity == "warning"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("600123456", "+34600123456"),
        ("+34 600 12 34 56", "+34600123456"),
        ("0034600123456", "+34600123456"),
        ("600-123-456", "+34600123456"),
        ("912345678", "+34912345678"),
    ],
)
def test_telefono_se_normaliza_a_e164(value: str, expected: str) -> None:
    result = validate_phone_es(value)
    assert result.ok, result.message
    assert result.normalized == expected


@pytest.mark.parametrize(
    "value,rule",
    [
        (None, "phone.missing"),
        ("", "phone.missing"),
        ("111111111", "phone.placeholder"),
        ("123456789", "phone.format_es"),
        ("12345", "phone.format_es"),
        ("60012345678901", "phone.format_es"),
    ],
)
def test_telefono_invalido(value: object, rule: str) -> None:
    result = validate_phone_es(value)
    assert not result.ok
    assert result.rule == rule


@pytest.mark.parametrize("value", ["28001", "08001", "01001", "52001"])
def test_codigo_postal_valido(value: str) -> None:
    assert validate_postal_code_es(value).ok


def test_codigo_postal_recupera_el_cero_perdido_por_excel() -> None:
    """Excel convierte 01001 en el número 1001. Es un clásico."""
    result = validate_postal_code_es("1001")
    assert not result.ok
    assert result.rule == "postal_code.lost_zero"
    assert result.normalized == "01001"


@pytest.mark.parametrize(
    "value,rule",
    [
        (None, "postal_code.missing"),
        ("99999", "postal_code.province"),
        ("53001", "postal_code.province"),
        ("123456", "postal_code.length"),
    ],
)
def test_codigo_postal_invalido(value: object, rule: str) -> None:
    result = validate_postal_code_es(value)
    assert not result.ok
    assert result.rule == rule
