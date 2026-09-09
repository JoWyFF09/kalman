"""Validación de identificadores fiscales españoles: NIF, NIE y CIF.

Esta es la pieza con valor económico más directo del motor. Un NIF mal escrito
en una factura la invalida frente a la AEAT, y un CIF erróneo rompe la
conciliación con el cliente. A diferencia de "parece un email", aquí no hay
heurística: hay un dígito de control y o cuadra o no cuadra.

Referencias del algoritmo:
  - NIF de persona física: letra = tabla[numero % 23].
  - NIE: la letra inicial X, Y o Z se sustituye por 0, 1 o 2 y se aplica NIF.
  - NIF de entidad jurídica (el antiguo CIF): Orden EHA/451/2008.
"""

from __future__ import annotations

import re

from ..normalize import text_value
from ..types import FieldResult, Severity

#: Tabla oficial de letras de control del NIF. El orden no es alfabético
#: a propósito: está diseñado para que una errata en un dígito casi nunca
#: produzca una letra válida.
_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"

#: Letras iniciales válidas para entidades jurídicas.
_CIF_ORG_LETTERS = "ABCDEFGHJKLMNPQRSUVW"

#: Entidades cuyo dígito de control es obligatoriamente una letra.
_CIF_LETTER_ONLY = "KPQRSNW"

#: Entidades cuyo dígito de control es obligatoriamente un número.
_CIF_DIGIT_ONLY = "ABEH"

#: Tabla de conversión del dígito de control numérico a letra.
_CIF_CONTROL_LETTERS = "JABCDEFGHI"

_NIF_RE = re.compile(r"^(\d{8})([A-Z])$")
_NIE_RE = re.compile(r"^([XYZ])(\d{7})([A-Z])$")
_CIF_RE = re.compile(rf"^([{_CIF_ORG_LETTERS}])(\d{{7}})([0-9A-J])$")


def clean_id(value: object) -> str:
    """Deja el identificador en forma canónica: mayúsculas y sin separadores.

    Los CRM españoles guardan el NIF de mil formas distintas: "12345678-z",
    "12.345.678 Z", "es12345678z". Todas son el mismo número.
    """
    text = text_value(value).upper()
    text = re.sub(r"[\s\-\.\_/]", "", text)
    # Prefijo de país usado en facturación intracomunitaria.
    if text.startswith("ES") and len(text) > 9:
        text = text[2:]
    return text


def nif_control_letter(number: int) -> str:
    """Letra de control que corresponde a un número de 8 dígitos."""
    return _NIF_LETTERS[number % 23]


def _cif_control(digits: str) -> int:
    """Dígito de control de una entidad jurídica.

    Las posiciones impares se duplican y se suman sus cifras; las pares se
    suman tal cual. Es la misma mecánica que el algoritmo de Luhn de las
    tarjetas de crédito, con la numeración empezando en 1.
    """
    total = 0
    for index, char in enumerate(digits, start=1):
        digit = int(char)
        if index % 2 == 1:
            doubled = digit * 2
            total += doubled if doubled < 10 else doubled - 9
        else:
            total += digit
    return (10 - (total % 10)) % 10


def validate_tax_id(value: object) -> FieldResult:
    """Valida un NIF, NIE o CIF español y devuelve su forma canónica.

    Devuelve `ok=True` sólo si el dígito de control cuadra. No hay grados
    intermedios: un identificador fiscal es válido o no lo es.
    """
    candidate = clean_id(value)
    if not candidate:
        return FieldResult(
            ok=False,
            rule="tax_id.missing",
            severity=Severity.ERROR,
            message="Identificador fiscal vacío.",
        )

    if len(candidate) != 9:
        return FieldResult(
            ok=False,
            normalized=candidate,
            rule="tax_id.length",
            severity=Severity.ERROR,
            message=f"Un identificador fiscal español tiene 9 caracteres, este tiene {len(candidate)}.",
        )

    match = _NIF_RE.match(candidate)
    if match:
        number, letter = match.group(1), match.group(2)
        expected = nif_control_letter(int(number))
        if letter == expected:
            return FieldResult(ok=True, normalized=candidate, rule="tax_id.nif")
        return FieldResult(
            ok=False,
            normalized=candidate,
            rule="tax_id.nif.checksum",
            severity=Severity.ERROR,
            message=f"Letra de control incorrecta: se esperaba {expected} y hay {letter}.",
        )

    match = _NIE_RE.match(candidate)
    if match:
        prefix, number, letter = match.group(1), match.group(2), match.group(3)
        as_number = int(str("XYZ".index(prefix)) + number)
        expected = nif_control_letter(as_number)
        if letter == expected:
            return FieldResult(ok=True, normalized=candidate, rule="tax_id.nie")
        return FieldResult(
            ok=False,
            normalized=candidate,
            rule="tax_id.nie.checksum",
            severity=Severity.ERROR,
            message=f"Letra de control incorrecta: se esperaba {expected} y hay {letter}.",
        )

    match = _CIF_RE.match(candidate)
    if match:
        org_letter, digits, control = match.group(1), match.group(2), match.group(3)
        expected_digit = _cif_control(digits)
        expected_letter = _CIF_CONTROL_LETTERS[expected_digit]

        if org_letter in _CIF_DIGIT_ONLY:
            valid = control == str(expected_digit)
        elif org_letter in _CIF_LETTER_ONLY:
            valid = control == expected_letter
        else:
            valid = control in (str(expected_digit), expected_letter)

        if valid:
            return FieldResult(ok=True, normalized=candidate, rule="tax_id.cif")
        return FieldResult(
            ok=False,
            normalized=candidate,
            rule="tax_id.cif.checksum",
            severity=Severity.ERROR,
            message=(
                f"Dígito de control incorrecto para la entidad {org_letter}: "
                f"se esperaba {expected_digit} o {expected_letter}."
            ),
        )

    return FieldResult(
        ok=False,
        normalized=candidate,
        rule="tax_id.format",
        severity=Severity.ERROR,
        message="No corresponde al formato de un NIF, NIE ni CIF español.",
    )
