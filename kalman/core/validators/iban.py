"""Validación de IBAN por el algoritmo mod-97 de la norma ISO 13616.

Un IBAN mal grabado en una base de datos de domiciliaciones produce un recibo
devuelto. En España el banco cobra comisión por cada devolución y el cliente
entra en un ciclo de reclamación manual. Es el tipo de error que una empresa
puede cuantificar sin que nadie se lo estime por ella.
"""

from __future__ import annotations

import re

from ..normalize import text_value
from ..types import FieldResult, Severity

#: Longitud oficial del IBAN por país. Sólo se incluye la zona SEPA relevante
#: para un cliente español; un país ausente se valida únicamente por mod-97.
IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24,
    "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22,
    "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21,
    "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18, "NO": 15,
    "PL": 28, "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27,
}

_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]+$")


def clean_iban(value: object) -> str:
    """Elimina espacios y guiones y pasa a mayúsculas."""
    return re.sub(r"[\s\-]", "", text_value(value).upper())


def mod97(iban: str) -> int:
    """Resto mod-97 de un IBAN ya normalizado.

    Se mueven los cuatro primeros caracteres al final y cada letra se sustituye
    por su posición en el alfabeto más 9. El número resultante puede tener más
    de treinta dígitos, así que se reduce por bloques para no depender del
    tamaño de entero de la plataforma.
    """
    rearranged = iban[4:] + iban[:4]
    remainder = 0
    for char in rearranged:
        if char.isdigit():
            chunk = char
        else:
            chunk = str(ord(char) - 55)
        for digit in chunk:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder


def format_iban(iban: str) -> str:
    """Agrupa el IBAN de cuatro en cuatro, que es como lo leen las personas."""
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def validate_iban(value: object) -> FieldResult:
    """Valida un IBAN y devuelve su forma canónica sin espacios."""
    candidate = clean_iban(value)
    if not candidate:
        return FieldResult(
            ok=False,
            rule="iban.missing",
            severity=Severity.ERROR,
            message="IBAN vacío.",
        )

    if not _IBAN_RE.match(candidate):
        return FieldResult(
            ok=False,
            normalized=candidate,
            rule="iban.format",
            severity=Severity.ERROR,
            message="El IBAN debe empezar por dos letras de país y dos dígitos de control.",
        )

    country = candidate[:2]
    expected_length = IBAN_LENGTHS.get(country)
    if expected_length is not None and len(candidate) != expected_length:
        return FieldResult(
            ok=False,
            normalized=candidate,
            rule="iban.length",
            severity=Severity.ERROR,
            message=(
                f"Un IBAN de {country} tiene {expected_length} caracteres, "
                f"este tiene {len(candidate)}."
            ),
        )

    if mod97(candidate) != 1:
        return FieldResult(
            ok=False,
            normalized=candidate,
            rule="iban.checksum",
            severity=Severity.ERROR,
            message="Los dígitos de control no cuadran. Hay al menos una cifra mal transcrita.",
        )

    if expected_length is None:
        return FieldResult(
            ok=True,
            normalized=candidate,
            rule="iban.ok_unknown_country",
            severity=Severity.WARNING,
            message=f"País {country} fuera de la lista SEPA verificada.",
            confidence=0.8,
        )

    return FieldResult(ok=True, normalized=candidate, rule="iban.ok")
