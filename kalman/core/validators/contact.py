"""Validación de email, teléfono y código postal.

Aquí sí hay heurística, y por eso cada resultado lleva una confianza asociada.
La diferencia con el motor anterior es que ahora la heurística está acotada y
se declara como tal, en vez de disfrazarse de red neuronal.
"""

from __future__ import annotations

import re

from ..normalize import text_value
from ..types import FieldResult, Severity

# Sintaxis local razonable. No se intenta implementar el RFC 5322 completo:
# el RFC admite direcciones que ningún proveedor real acepta, y una expresión
# que las cubra todas deja pasar más basura de la que filtra.
_EMAIL_RE = re.compile(
    r"^[A-Z0-9._%+\-]+@[A-Z0-9]([A-Z0-9\-]*[A-Z0-9])?(\.[A-Z0-9]([A-Z0-9\-]*[A-Z0-9])?)+$",
    re.IGNORECASE,
)

#: Dominios desechables más habituales en formularios de captación.
DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "yopmail.com", "guerrillamail.com", "10minutemail.com",
    "tempmail.com", "temp-mail.org", "throwawaymail.com", "trashmail.com",
    "sharklasers.com", "getnada.com", "maildrop.cc", "fakeinbox.com",
})

#: Erratas frecuentes en dominios españoles. La corrección se propone,
#: nunca se aplica en silencio.
DOMAIN_TYPOS: dict[str, str] = {
    "gmail.con": "gmail.com", "gmail.co": "gmail.com", "gmial.com": "gmail.com",
    "gmai.com": "gmail.com", "gmail.es": "gmail.com", "hotmai.com": "hotmail.com",
    "hotmail.con": "hotmail.com", "hotmial.com": "hotmail.com",
    "outlok.com": "outlook.com", "outllok.com": "outlook.com",
    "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com",
}

#: Valores que la gente escribe cuando un formulario obliga a rellenar el campo.
PLACEHOLDER_VALUES = frozenset({
    "n/a", "na", "no", "none", "null", "nulo", "sin", "sindatos", "sinemail",
    "test", "prueba", "asdf", "aaa", "xxx", "-", "--", ".", "0", "no@no.com",
    "test@test.com", "a@a.com", "email@email.com", "correo@correo.com",
})

_PHONE_ES_RE = re.compile(r"^[6789]\d{8}$")


def validate_email(value: object) -> FieldResult:
    """Valida sintaxis de email y detecta desechables, placeholders y erratas."""
    candidate = text_value(value).lower()
    if not candidate:
        return FieldResult(
            ok=False, rule="email.missing", severity=Severity.ERROR,
            message="Email vacío.",
        )

    if candidate in PLACEHOLDER_VALUES:
        return FieldResult(
            ok=False, normalized=candidate, rule="email.placeholder",
            severity=Severity.ERROR,
            message="Valor de relleno, no es una dirección real.",
        )

    if not _EMAIL_RE.match(candidate):
        return FieldResult(
            ok=False, normalized=candidate, rule="email.syntax",
            severity=Severity.ERROR,
            message="La dirección no tiene una sintaxis válida.",
        )

    domain = candidate.rsplit("@", 1)[1]

    if domain in DOMAIN_TYPOS:
        suggested = candidate.rsplit("@", 1)[0] + "@" + DOMAIN_TYPOS[domain]
        return FieldResult(
            ok=False, normalized=suggested, rule="email.typo",
            severity=Severity.WARNING,
            message=f"Dominio probablemente mal escrito. Sugerencia: {DOMAIN_TYPOS[domain]}.",
            confidence=0.85,
        )

    if domain in DISPOSABLE_DOMAINS:
        return FieldResult(
            ok=False, normalized=candidate, rule="email.disposable",
            severity=Severity.WARNING,
            message="Dominio de correo desechable.",
            confidence=0.95,
        )

    return FieldResult(ok=True, normalized=candidate, rule="email.ok")


def validate_phone_es(value: object, default_country: str = "34") -> FieldResult:
    """Normaliza un teléfono español a formato E.164.

    Se acepta prefijo internacional con o sin signo más, ceros de salida y
    cualquier separador. Lo que no se acepta es un número que, ya limpio, no
    corresponda a un rango asignado en España.
    """
    # `text_value` es imprescindible aquí. Si la columna tiene algún hueco,
    # pandas la convierte a coma flotante y 612345678 llega como 612345678.0,
    # que tras limpiar no dígitos son diez cifras en lugar de nueve.
    raw = text_value(value)
    if not raw:
        return FieldResult(
            ok=False, rule="phone.missing", severity=Severity.ERROR,
            message="Teléfono vacío.",
        )

    digits = re.sub(r"[^\d+]", "", raw)
    digits = digits.lstrip("+")

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith(default_country) and len(digits) == 9 + len(default_country):
        digits = digits[len(default_country) :]

    if not digits:
        return FieldResult(
            ok=False, normalized=raw, rule="phone.empty_after_clean",
            severity=Severity.ERROR,
            message="No queda ningún dígito tras limpiar el valor.",
        )

    if len(set(digits)) == 1:
        return FieldResult(
            ok=False, normalized=digits, rule="phone.placeholder",
            severity=Severity.ERROR,
            message="Todos los dígitos son iguales, es un valor de relleno.",
        )

    if not _PHONE_ES_RE.match(digits):
        return FieldResult(
            ok=False, normalized=digits, rule="phone.format_es",
            severity=Severity.ERROR,
            message=(
                "Un número español tiene 9 dígitos y empieza por 6, 7, 8 o 9. "
                f"Este tiene {len(digits)} dígitos."
            ),
        )

    return FieldResult(
        ok=True, normalized=f"+{default_country}{digits}", rule="phone.ok"
    )


#: Rango de códigos de provincia asignados en España.
_VALID_PROVINCE_CODES = frozenset(f"{i:02d}" for i in range(1, 53))


def validate_postal_code_es(value: object) -> FieldResult:
    """Valida un código postal español de cinco dígitos.

    Los dos primeros dígitos son el código de provincia y sólo existen del 01
    al 52. Un CP que empiece por 53 es imposible, no improbable.
    """
    text = text_value(value)
    if not text:
        return FieldResult(
            ok=False, rule="postal_code.missing", severity=Severity.ERROR,
            message="Código postal vacío.",
        )

    raw = re.sub(r"\D", "", text)

    # Es habitual que una hoja de cálculo se coma el cero inicial de Álava,
    # Albacete o Alicante y guarde 1001 en vez de 01001.
    if len(raw) == 4:
        padded = raw.zfill(5)
        if padded[:2] in _VALID_PROVINCE_CODES:
            return FieldResult(
                ok=False, normalized=padded, rule="postal_code.lost_zero",
                severity=Severity.WARNING,
                message="Falta el cero inicial, probablemente por formato numérico en Excel.",
                confidence=0.9,
            )

    if len(raw) != 5:
        return FieldResult(
            ok=False, normalized=raw, rule="postal_code.length",
            severity=Severity.ERROR,
            message=f"Un código postal español tiene 5 dígitos, este tiene {len(raw)}.",
        )

    if raw[:2] not in _VALID_PROVINCE_CODES:
        return FieldResult(
            ok=False, normalized=raw, rule="postal_code.province",
            severity=Severity.ERROR,
            message=f"El código de provincia {raw[:2]} no existe en España.",
        )

    return FieldResult(ok=True, normalized=raw, rule="postal_code.ok")
