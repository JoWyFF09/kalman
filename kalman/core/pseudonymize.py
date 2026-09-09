"""Seudonimización de datos personales.

Precisión terminológica, porque aquí el proyecto anterior se equivocaba de
forma peligrosa
--------------------------------------------------------------------------
La versión previa aplicaba SHA-256 sin clave a los emails y presentaba el
resultado como datos anonimizados y seguros. Eso es falso por dos motivos.

Primero, el espacio de los emails es pequeño y enumerable. Un atacante con un
diccionario de direcciones calcula sus hashes y revierte la tabla entera en
minutos. Segundo, y más importante, el artículo 4.5 del Reglamento General de
Protección de Datos define esto como seudonimización, no anonimización: el
dato sigue siendo dato personal y sigue bajo el ámbito del reglamento.
Venderlo como anonimizado a una empresa española es exponerla a ella y a ti.

Lo que hace este módulo es seudonimización correcta: HMAC-SHA256 con una clave
secreta que nunca sale del servidor. Sin la clave no hay tabla arcoíris que
valga. Con la clave, el responsable del tratamiento puede volver atrás, que es
justo lo que la ley espera que sea posible.
"""

from __future__ import annotations

import hashlib
import hmac
import re

#: Longitud del seudónimo en caracteres hexadecimales. 32 caracteres son 128
#: bits, suficiente para que no haya colisiones en conjuntos de miles de
#: millones de filas.
TOKEN_LENGTH = 32


class Pseudonymizer:
    """Genera seudónimos estables y reversibles sólo con la clave.

    Estable significa que el mismo email produce siempre el mismo seudónimo
    dentro de la misma organización, que es lo que permite seguir haciendo
    analítica y detectar duplicados sobre datos seudonimizados.

    El seudónimo incorpora el identificador de la organización, de modo que
    dos clientes distintos con el mismo email producen seudónimos distintos.
    Sin eso se podría cruzar información entre clientes.
    """

    def __init__(self, secret_key: str, org_id: str) -> None:
        if not secret_key or len(secret_key) < 32:
            raise ValueError(
                "La clave de seudonimización debe tener al menos 32 caracteres. "
                "Genera una con: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        self._key = secret_key.encode("utf-8")
        self._org = org_id.encode("utf-8")

    def token(self, value: object, field: str = "") -> str:
        """Seudónimo de un valor.

        `field` separa los espacios de nombres: el mismo texto como nombre y
        como email produce seudónimos distintos, lo que impide inferir que el
        nombre de alguien coincide con su dirección.
        """
        if value is None or str(value).strip() == "":
            return ""
        message = b"\x00".join([
            self._org,
            field.encode("utf-8"),
            str(value).strip().lower().encode("utf-8"),
        ])
        digest = hmac.new(self._key, message, hashlib.sha256).hexdigest()
        return digest[:TOKEN_LENGTH]


def mask_email(value: object) -> str:
    """Enmascara un email conservando su forma para revisión humana.

    "joel.rodriguez@empresa.com" queda como "j***z@empresa.com". El dominio se
    conserva porque casi nunca identifica a una persona y sí es útil para
    diagnosticar problemas de calidad por proveedor de correo.
    """
    text = str(value or "").strip()
    if "@" not in text:
        return "***"
    local, domain = text.rsplit("@", 1)
    if len(local) <= 2:
        hidden = "*" * len(local)
    else:
        hidden = f"{local[0]}{'*' * max(1, len(local) - 2)}{local[-1]}"
    return f"{hidden}@{domain}"


def mask_phone(value: object) -> str:
    """Enmascara un teléfono dejando visibles los tres últimos dígitos.

    Tres dígitos son suficientes para que un operador confirme por teléfono
    con el cliente y demasiado pocos para reconstruir el número.
    """
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 4:
        return "*" * 9
    return f"{'*' * (len(digits) - 3)}{digits[-3:]}"


def mask_tax_id(value: object) -> str:
    """Enmascara un identificador fiscal dejando la letra de control.

    Es el formato que usa la propia Agencia Tributaria en sus notificaciones.
    """
    text = str(value or "").strip().upper()
    if len(text) < 4:
        return "*********"
    return f"{'*' * (len(text) - 4)}{text[-4:]}"
