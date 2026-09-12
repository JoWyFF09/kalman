"""Avisos al usuario. Hoy solo correo transaccional."""

from .email import (
    BrevoSender,
    DisabledSender,
    EmailError,
    EmailSettings,
    Sender,
    SmtpSender,
    build_sender,
    email_verify_body,
    password_reset_body,
)

__all__ = [
    "build_sender",
    "Sender",
    "EmailSettings",
    "EmailError",
    "BrevoSender",
    "SmtpSender",
    "DisabledSender",
    "password_reset_body",
    "email_verify_body",
]
