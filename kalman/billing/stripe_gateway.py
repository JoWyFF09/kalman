"""Creación de sesiones de pago y portal de cliente.

Dos cambios de fondo respecto a la versión anterior.

Primero, el precio ya no se envía desde la aplicación con `price_data`. Se usan
identificadores de precio creados una vez en Stripe. Enviar el importe en cada
petición significa que el importe vive en el código, y basta un despliegue mal
hecho para cobrar de menos a todo el mundo. Con un identificador fijo, el
precio lo controla Stripe y se cambia sin tocar el código.

Segundo, la sesión lleva siempre el identificador de la organización. Es lo que
permite al webhook saber a quién activar sin preguntarle al navegador.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import stripe

from .plans import PLANS, Plan, get_plan

logger = logging.getLogger(__name__)

#: Días de prueba. Siete es corto para un producto que se usa una vez al mes.
#: Catorce da tiempo a que el cliente pase por un cierre contable, que es
#: cuando de verdad le duele tener los datos sucios.
TRIAL_DAYS = 14


class BillingError(RuntimeError):
    """Error al hablar con Stripe, ya traducido a lenguaje del usuario."""


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    id: str
    url: str


class StripeGateway:
    """Envoltorio fino sobre la API de Stripe.

    Existe para que el resto de la aplicación no importe `stripe` por ninguna
    parte. Así las pruebas no necesitan red y cambiar de pasarela algún día
    toca un solo fichero.
    """

    def __init__(
        self,
        api_key: str,
        app_url: str,
        price_ids: dict[str, str] | None = None,
    ) -> None:
        if not api_key:
            raise BillingError("Falta la clave secreta de Stripe.")
        self._client = stripe.StripeClient(api_key)
        self._app_url = app_url.rstrip("/")
        self._price_ids = price_ids or {}
        self._live = api_key.startswith("sk_live_")

    @property
    def is_live(self) -> bool:
        return self._live

    def _price_for(self, plan: Plan) -> str:
        price_id = self._price_ids.get(plan.key)
        if not price_id:
            raise BillingError(
                f"No hay identificador de precio configurado para el plan {plan.name}. "
                f"Define STRIPE_PRICE_{plan.key.upper()} en el entorno."
            )
        return price_id

    def ensure_customer(self, org_id: str, org_name: str, email: str) -> str:
        """Localiza o crea el cliente de Stripe de una organización.

        La búsqueda es por metadata y no por email: el email de facturación
        cambia y puede repetirse entre organizaciones, el identificador de
        organización no.
        """
        try:
            found = self._client.v1.customers.search(
                params={"query": f"metadata['org_id']:'{org_id}'", "limit": 1}
            )
            if found.data:
                return found.data[0].id

            created = self._client.v1.customers.create(
                params={
                    "email": email,
                    "name": org_name,
                    "metadata": {"org_id": org_id},
                }
            )
            return created.id
        except stripe.error.StripeError as exc:
            logger.exception("Error creando cliente de Stripe para %s", org_id)
            raise BillingError("No se ha podido contactar con la pasarela de pago.") from exc

    def create_checkout(
        self,
        org_id: str,
        org_name: str,
        email: str,
        plan_key: str,
        with_trial: bool = False,
    ) -> CheckoutSession:
        """Crea una sesión de pago para una organización y un plan."""
        plan = get_plan(plan_key)
        if plan.is_free:
            raise BillingError("El plan gratuito no requiere pago.")

        customer_id = self.ensure_customer(org_id, org_name, email)

        subscription_data: dict[str, object] = {
            "metadata": {"org_id": org_id, "plan": plan.key},
        }
        if with_trial:
            subscription_data["trial_period_days"] = TRIAL_DAYS

        try:
            session = self._client.v1.checkout.sessions.create(
                params={
                    "mode": "subscription",
                    "customer": customer_id,
                    "line_items": [{"price": self._price_for(plan), "quantity": 1}],
                    "success_url": f"{self._app_url}/?checkout=success",
                    "cancel_url": f"{self._app_url}/?checkout=cancel",
                    # Estos dos campos son los que el webhook lee para saber a
                    # quién activar. Sin ellos habría que fiarse del navegador.
                    "client_reference_id": org_id,
                    "metadata": {
                        "org_id": org_id,
                        "plan": plan.key,
                        "trial": "1" if with_trial else "0",
                    },
                    "subscription_data": subscription_data,
                    "locale": "es",
                    "allow_promotion_codes": True,
                    # Recoge el NIF del cliente para poder emitir factura con
                    # inversión del sujeto pasivo dentro de la Unión Europea.
                    "tax_id_collection": {"enabled": True},
                    "billing_address_collection": "required",
                }
            )
            return CheckoutSession(id=session.id, url=session.url)
        except stripe.error.StripeError as exc:
            logger.exception("Error creando checkout para %s", org_id)
            raise BillingError("No se ha podido abrir la pasarela de pago.") from exc

    def create_portal(self, customer_id: str) -> str:
        """Abre el portal de cliente de Stripe.

        Todo lo que es cambiar de plan, actualizar tarjeta, descargar facturas
        y cancelar se delega aquí. Reimplementar eso a mano, como hacía la
        versión anterior con su botón de cancelar, es asumir la responsabilidad
        de un flujo delicado sin ninguna ventaja.
        """
        try:
            session = self._client.v1.billing_portal.sessions.create(
                params={
                    "customer": customer_id,
                    "return_url": f"{self._app_url}/",
                    "locale": "es",
                }
            )
            return session.url
        except stripe.error.StripeError as exc:
            logger.exception("Error abriendo portal para %s", customer_id)
            raise BillingError("No se ha podido abrir el portal de facturación.") from exc

    def sync_subscription(self, subscription_id: str) -> dict[str, object]:
        """Relee una suscripción desde Stripe.

        Se usa como red de seguridad cuando se sospecha que se ha perdido un
        webhook, no como camino normal. El camino normal es el webhook.
        """
        try:
            subscription = self._client.v1.subscriptions.retrieve(subscription_id)
            return dict(subscription)
        except stripe.error.StripeError as exc:
            raise BillingError("No se ha podido leer la suscripción.") from exc


def required_price_env_vars() -> list[str]:
    """Variables de entorno de precios que hay que definir antes de vender."""
    return [f"STRIPE_PRICE_{key.upper()}" for key, plan in PLANS.items() if not plan.is_free]
