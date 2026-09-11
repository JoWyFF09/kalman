"""Envío de correo transaccional.

Qué es transaccional y qué no
-----------------------------
Aquí sólo van correos que el usuario ha provocado: ha pedido recuperar su
contraseña, o acaba de darse de alta y hay que confirmar su dirección. Nada de
avisos comerciales, boletines ni recordatorios. Eso cambiaría las obligaciones
legales y la forma de gestionar las bajas.

Si no está configurado
----------------------
El envío es opcional a propósito. Sin credenciales de correo, `EmailSender`
no falla: se queda inactivo y avisa. Así el producto arranca igual en un
portátil recién clonado, y las pantallas que dependen del correo enseñan un
mensaje claro en vez de una traza.

Sobre Gmail
-----------
Con una cuenta de Gmail hay que generar una "contraseña de aplicación", que
exige tener la verificación en dos pasos activada. La contraseña normal de la
cuenta no funciona desde un programa, y eso es bueno.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)

#: Cuánto se espera al servidor de correo antes de rendirse. Corto a propósito:
#: el usuario está mirando la pantalla y prefiere un aviso a un reloj girando.
SMTP_TIMEOUT_SECONDS = 15


class EmailError(RuntimeError):
    """No se ha podido enviar, con un motivo que se le puede enseñar al usuario."""


@dataclass(frozen=True, slots=True)
class EmailSettings:
    """Configuración del servidor de correo."""

    host: str
    port: int
    user: str
    password: str
    sender: str
    sender_name: str = "Kalman"

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.sender)


class EmailSender:
    """Envía correo por SMTP. Inactivo y silencioso si no está configurado."""

    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings

    @property
    def available(self) -> bool:
        return self._settings.configured

    def send(self, to: str, subject: str, body: str) -> None:
        """Envía un correo de texto plano.

        Texto plano y no HTML a propósito: un correo de recuperación con
        maquetación se parece mucho más a una suplantación, y los filtros de
        muchas empresas lo tratan peor.
        """
        if not self.available:
            raise EmailError(
                "El envío de correo no está configurado en este despliegue."
            )

        mensaje = EmailMessage()
        mensaje["Subject"] = subject
        mensaje["From"] = f"{self._settings.sender_name} <{self._settings.sender}>"
        mensaje["To"] = to
        mensaje.set_content(body)

        contexto = ssl.create_default_context()
        try:
            if self._settings.port == 465:
                with smtplib.SMTP_SSL(
                    self._settings.host, self._settings.port,
                    timeout=SMTP_TIMEOUT_SECONDS, context=contexto,
                ) as smtp:
                    smtp.login(self._settings.user, self._settings.password)
                    smtp.send_message(mensaje)
            else:
                with smtplib.SMTP(
                    self._settings.host, self._settings.port,
                    timeout=SMTP_TIMEOUT_SECONDS,
                ) as smtp:
                    smtp.starttls(context=contexto)
                    smtp.login(self._settings.user, self._settings.password)
                    smtp.send_message(mensaje)
        except smtplib.SMTPAuthenticationError as exc:
            logger.error("El servidor de correo rechaza las credenciales: %s", exc)
            raise EmailError(
                "El servidor de correo ha rechazado las credenciales."
            ) from exc
        except (OSError, smtplib.SMTPException) as exc:
            logger.exception("Fallo enviando correo a %s", _ocultar(to))
            raise EmailError("No se ha podido enviar el correo.") from exc

        logger.info("Correo enviado a %s: %s", _ocultar(to), subject)


def _ocultar(direccion: str) -> str:
    """Enmascara una dirección para los registros del servidor.

    Los registros los puede leer más gente de la que debería ver la lista de
    correos de los clientes.
    """
    local, _, dominio = direccion.partition("@")
    if not dominio:
        return "***"
    visible = local[0] if local else ""
    return f"{visible}***@{dominio}"


# --------------------------------------------------------------------- textos

def password_reset_body(org_name: str, url: str, minutos: int) -> str:
    """Correo de recuperación de contraseña.

    Dice expresamente qué hacer si no lo ha pedido el usuario. Es lo que
    convierte un correo automático en uno en el que se puede confiar.
    """
    return f"""Hola,

Has pedido restablecer la contraseña de tu cuenta de Kalman en {org_name}.

Abre este enlace para elegir una nueva:

{url}

El enlace caduca en {minutos} minutos y sólo se puede usar una vez.

Si no has pedido tú este cambio, no hagas nada. Tu contraseña sigue siendo la
misma y nadie ha entrado en tu cuenta.

Kalman
Calidad de datos para empresas españolas
"""


def email_verify_body(org_name: str, url: str, horas: int) -> str:
    """Correo de confirmación de dirección."""
    return f"""Hola,

Gracias por crear la cuenta de {org_name} en Kalman.

Confirma que esta dirección es tuya abriendo este enlace:

{url}

El enlace caduca en {horas} horas.

Puedes usar Kalman mientras tanto con el plan gratuito. La confirmación hace
falta antes de contratar un plan de pago.

Si no te has dado de alta tú, ignora este correo: sin confirmar, la cuenta no
queda asociada a tu dirección.

Kalman
Calidad de datos para empresas españolas
"""
