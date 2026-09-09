"""Configuración por entorno.

Ningún secreto vive en el código ni en el repositorio. Todo llega por variables
de entorno y se valida al arrancar: si falta algo, el proceso muere en el
arranque con un mensaje claro, no a las tres semanas en mitad de una demo.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Falta configuración obligatoria o es inválida."""


def _require(name: str, minimum_length: int = 1) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Falta la variable de entorno {name}. "
            f"Copia .env.example a .env y rellénala."
        )
    if len(value) < minimum_length:
        raise ConfigError(
            f"{name} debe tener al menos {minimum_length} caracteres."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuración validada de la aplicación."""

    environment: str
    database_url: str
    pseudonym_key: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    app_url: str
    support_email: str
    max_upload_mb: int
    session_ttl_hours: int

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def stripe_is_live(self) -> bool:
        return self.stripe_secret_key.startswith("sk_live_")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Lee y valida la configuración una sola vez por proceso."""
    environment = _optional("KALMAN_ENV", "development")

    settings = Settings(
        environment=environment,
        database_url=_require("DATABASE_URL"),
        # 32 caracteres es el mínimo para que HMAC-SHA256 no sea el eslabón
        # débil. La validación está aquí y no en el punto de uso para que un
        # despliegue mal configurado no llegue nunca a tocar datos personales.
        pseudonym_key=_require("KALMAN_PSEUDONYM_KEY", minimum_length=32),
        stripe_secret_key=_require("STRIPE_SECRET_KEY"),
        # Sin este secreto no se puede verificar la firma de los webhooks, y
        # sin verificar la firma cualquiera puede regalarse una suscripción.
        stripe_webhook_secret=_require("STRIPE_WEBHOOK_SECRET"),
        app_url=_optional("APP_URL", "http://localhost:8501").rstrip("/"),
        support_email=_optional("SUPPORT_EMAIL", "soporte@kalman.es"),
        max_upload_mb=int(_optional("MAX_UPLOAD_MB", "50")),
        session_ttl_hours=int(_optional("SESSION_TTL_HOURS", "12")),
    )

    if settings.is_production:
        if settings.app_url.startswith("http://"):
            raise ConfigError("En producción APP_URL debe usar HTTPS.")
        if not settings.stripe_is_live:
            raise ConfigError(
                "KALMAN_ENV es production pero STRIPE_SECRET_KEY es de prueba. "
                "Uno de los dos está mal y no voy a adivinar cuál."
            )

    return settings
