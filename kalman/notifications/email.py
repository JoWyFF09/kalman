"""Envío de correo transaccional, por API o por SMTP.

Por qué hay dos formas de enviar
--------------------------------
La primera versión usaba SMTP con Gmail. Funciona en un portátil y falla en
Render con este error:

    OSError: [Errno 101] Network is unreachable

La conexión ni siquiera sale de la máquina. Muchos alojamientos gestionados
cierran la salida por los puertos de correo, 25, 465 y 587, para que no se
usen sus servidores como plataforma de envío masivo. Es una medida razonable y
no hay forma de rodearla desde el código.

Lo que sí está abierto es el 443, el de HTTPS, porque por ahí hablan Stripe y
la base de datos. Así que el envío va por la API del proveedor de correo, no
por SMTP.

Se mantienen las dos formas: SMTP sirve en un portátil o en un servidor
propio, y la API sirve en cualquier sitio. Se elige sola según lo que esté
configurado, dando prioridad a la que funciona en todas partes.

Qué es transaccional y qué no
-----------------------------
Aquí sólo van correos que el usuario ha provocado: ha pedido recuperar su
contraseña, o acaba de darse de alta y hay que confirmar su dirección. Nada de
avisos comerciales ni boletines. Eso cambiaría las obligaciones legales y la
forma de gestionar las bajas.
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger(__name__)

#: Cuánto se espera antes de rendirse. Corto a propósito: el usuario está
#: mirando la pantalla y prefiere un aviso a un reloj girando.
TIMEOUT_SECONDS = 15

#: Punto de entrada de la API de Brevo para correo transaccional.
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class EmailError(RuntimeError):
    """No se ha podido enviar, con un motivo que se le puede enseñar."""


@dataclass(frozen=True, slots=True)
class EmailSettings:
    """Todo lo necesario para enviar, por cualquiera de las dos vías."""

    sender: str
    sender_name: str = "Kalman"

    # Vía API. Es la que funciona en un alojamiento gestionado.
    api_key: str = ""

    # Vía SMTP. Sirve en un portátil o en un servidor propio.
    host: str = ""
    port: int = 465
    user: str = ""
    password: str = ""

    @property
    def api_configured(self) -> bool:
        return bool(self.api_key and self.sender)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.sender)


class Sender(Protocol):
    """Lo que necesita el resto de la aplicación para mandar un correo."""

    @property
    def available(self) -> bool: ...

    def send(self, to: str, subject: str, body: str) -> None: ...


class DisabledSender:
    """Remitente inactivo. No falla al construirse, sólo al usarse.

    Así el producto arranca igual en un portátil recién clonado y las pantallas
    que dependen del correo enseñan un mensaje claro en vez de una traza.
    """

    available = False

    def send(self, to: str, subject: str, body: str) -> None:
        raise EmailError("El envío de correo no está configurado en este despliegue.")


class BrevoSender:
    """Envía por HTTPS a través de la API de Brevo.

    Se usa `urllib` de la biblioteca estándar y no un cliente HTTP externo. Es
    una sola petición POST con JSON, y el despliegue público de la demo lleva
    cinco dependencias: añadir una sexta para esto no compensa.
    """

    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings

    @property
    def available(self) -> bool:
        return self._settings.api_configured

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.available:
            raise EmailError("Falta la clave de la API de correo.")

        carga = json.dumps({
            "sender": {
                "email": self._settings.sender,
                "name": self._settings.sender_name,
            },
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        }).encode("utf-8")

        peticion = urllib.request.Request(
            BREVO_ENDPOINT,
            data=carga,
            method="POST",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": self._settings.api_key,
            },
        )

        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT_SECONDS) as respuesta:
                if respuesta.status >= 300:
                    raise EmailError("El proveedor de correo ha rechazado el envío.")
        except urllib.error.HTTPError as exc:
            detalle = _detalle_http(exc)
            logger.error("El proveedor rechaza el envio a %s: %s", _ocultar(to), detalle)
            raise EmailError(_traducir_rechazo(exc.code, detalle)) from exc
        except urllib.error.URLError as exc:
            logger.exception("No se ha podido contactar con el proveedor de correo")
            raise EmailError("No se ha podido contactar con el proveedor de correo.") from exc

        logger.info("Correo enviado a %s por API: %s", _ocultar(to), subject)


class SmtpSender:
    """Envía por SMTP. Sirve en local, no en un alojamiento gestionado."""

    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings

    @property
    def available(self) -> bool:
        return self._settings.smtp_configured

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.available:
            raise EmailError("El envío por SMTP no está configurado.")

        mensaje = EmailMessage()
        mensaje["Subject"] = subject
        mensaje["From"] = f"{self._settings.sender_name} <{self._settings.sender}>"
        mensaje["To"] = to
        # Texto plano y no HTML a propósito: un correo de recuperación con
        # maquetación se parece mucho más a una suplantación, y los filtros de
        # muchas empresas lo tratan peor.
        mensaje.set_content(body)

        contexto = ssl.create_default_context()
        try:
            if self._settings.port == 465:
                with smtplib.SMTP_SSL(
                    self._settings.host, self._settings.port,
                    timeout=TIMEOUT_SECONDS, context=contexto,
                ) as smtp:
                    smtp.login(self._settings.user, self._settings.password)
                    smtp.send_message(mensaje)
            else:
                with smtplib.SMTP(
                    self._settings.host, self._settings.port, timeout=TIMEOUT_SECONDS
                ) as smtp:
                    smtp.starttls(context=contexto)
                    smtp.login(self._settings.user, self._settings.password)
                    smtp.send_message(mensaje)
        except smtplib.SMTPAuthenticationError as exc:
            logger.error("El servidor de correo rechaza las credenciales")
            raise EmailError(
                "El servidor de correo ha rechazado las credenciales. Con Gmail "
                "hace falta una contraseña de aplicación, no la de la cuenta."
            ) from exc
        except OSError as exc:
            logger.exception("Fallo de red enviando correo a %s", _ocultar(to))
            raise EmailError(_traducir_fallo_de_red(exc)) from exc
        except smtplib.SMTPException as exc:
            logger.exception("Fallo SMTP enviando correo a %s", _ocultar(to))
            raise EmailError("No se ha podido enviar el correo.") from exc

        logger.info("Correo enviado a %s por SMTP: %s", _ocultar(to), subject)


def build_sender(settings: EmailSettings) -> Sender:
    """Elige cómo enviar según lo que esté configurado.

    La API va primero porque funciona en todas partes. SMTP queda como
    alternativa para quien despliegue en su propio servidor.
    """
    if settings.api_configured:
        return BrevoSender(settings)
    if settings.smtp_configured:
        return SmtpSender(settings)
    return DisabledSender()


# ------------------------------------------------------------------ auxiliares

def _traducir_fallo_de_red(exc: OSError) -> str:
    """Convierte un error de red en una instrucción concreta.

    "Network is unreachable" al conectar con un puerto de correo casi siempre
    significa que el alojamiento cierra la salida por ahí. Decir sólo "no se
    ha podido enviar" hace perder una tarde revisando contraseñas.
    """
    if exc.errno == 101 or "unreachable" in str(exc).lower():
        return (
            "El servidor no puede salir por el puerto de correo. Muchos "
            "alojamientos lo cierran para evitar el envío masivo. Configura el "
            "envío por API, que va por HTTPS."
        )
    if "timed out" in str(exc).lower():
        return "El servidor de correo no ha respondido a tiempo."
    return "No se ha podido conectar con el servidor de correo."


def _traducir_rechazo(codigo: int, detalle: str) -> str:
    """Convierte el rechazo del proveedor en algo accionable."""
    bajo = detalle.lower()

    if codigo in (401, 403):
        return "La clave de la API de correo no es válida o no tiene permisos."
    if "sender" in bajo and ("not valid" in bajo or "no valid" in bajo or "verif" in bajo):
        return (
            "La dirección remitente no está verificada en el proveedor. "
            "Verifícala en su panel antes de enviar."
        )
    if codigo == 429:
        return "Se ha superado el límite diario de envíos del proveedor."
    return f"El proveedor de correo ha rechazado el envío ({codigo})."


def _detalle_http(exc: urllib.error.HTTPError) -> str:
    """Extrae el mensaje del proveedor sin dejar que un fallo aquí tape el real."""
    try:
        cuerpo = exc.read().decode("utf-8", "replace")
    except Exception:
        return ""
    try:
        datos = json.loads(cuerpo)
        return str(datos.get("message") or datos.get("error") or cuerpo)[:200]
    except ValueError:
        return cuerpo[:200]


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
