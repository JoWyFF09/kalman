"""Testigos de un solo uso para recuperar contraseña y verificar el email.

Cómo se guardan, y por qué así
------------------------------
Al usuario se le manda un valor aleatorio de 256 bits. En la base de datos sólo
se guarda su SHA-256.

Si alguien roba la base, se lleva hashes que no sirven para nada: no puede
reconstruir el enlace que abriría la cuenta de otro. Es el mismo criterio que
con las claves de API, y por el mismo motivo por el que las contraseñas no se
guardan en claro.

Aquí basta SHA-256 sin derivación costosa, al contrario que con las
contraseñas. El testigo tiene 256 bits de azar real, así que no hay diccionario
ni fuerza bruta posible. Lo caro sólo hace falta cuando lo que se protege es
algo que una persona ha elegido y recordado.

Caducidad
---------
Una hora para recuperar contraseña: el tiempo de ir a mirar el correo, no más.
Cuarenta y ocho horas para verificar el email, porque alguien puede darse de
alta un viernes por la tarde.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

#: Minutos de validez de cada tipo de testigo.
TOKEN_LIFETIME_MINUTES: dict[str, int] = {
    "password_reset": 60,
    "email_verify": 48 * 60,
}

#: Los dos usos permitidos. La base de datos repite esta restricción, de modo
#: que un error de programación no pueda meter un testigo con un uso inventado.
PURPOSES = frozenset(TOKEN_LIFETIME_MINUTES)


class TokenError(ValueError):
    """El testigo no sirve: no existe, ya se usó o ha caducado."""


def generate_token(purpose: str) -> tuple[str, str, datetime]:
    """Crea un testigo. Devuelve el valor a enviar, su hash y su caducidad.

    El valor en claro no se guarda en ninguna parte: viaja en el correo y se
    olvida. Si el usuario pierde el correo, pide otro.
    """
    if purpose not in PURPOSES:
        raise TokenError(f"Uso de testigo desconocido: {purpose}")

    raw = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(minutes=TOKEN_LIFETIME_MINUTES[purpose])
    return raw, hash_token(raw), expires


def hash_token(raw: str) -> str:
    """Hash con el que se busca un testigo en la base de datos."""
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
    """Indica si un testigo ya no vale por tiempo.

    Se admite una fecha sin zona horaria y se interpreta como UTC, porque
    algunos controladores de base de datos la devuelven así y comparar una
    fecha con zona contra otra sin ella lanza TypeError.
    """
    momento = now or datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= momento
