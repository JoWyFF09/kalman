"""Recepción de webhooks de Stripe.

El agujero que esto cierra
--------------------------
En la versión anterior, el desbloqueo del producto funcionaba así: el usuario
escribía un email en una caja de texto, la aplicación preguntaba a Stripe si
ese email tenía suscripción y, si la tenía, marcaba la sesión como pagada.

Cualquiera que supiera el email de un cliente de pago entraba gratis. Y el
email de un cliente aparece en su web, en su firma de correo y en su factura.
No hacía falta ni adivinarlo.

La regla correcta, que es la que aplica Stripe en su propia documentación: el
navegador nunca decide si alguien ha pagado. Lo decide el servidor de Stripe,
que lo comunica por webhook firmado, y ese webhook es lo único que escribe la
tabla de suscripciones. La organización se identifica por el `client_reference_id`
que el servidor puso al crear la sesión, no por nada que el usuario teclee.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .plans import ENTITLED_STATUSES, get_plan, plan_from_amount

# El SDK de Stripe se importa dentro de `verify_signature` y no aquí. Toda la
# lógica de decisión de este módulo trabaja sobre diccionarios corrientes, así
# que puede probarse sin el paquete instalado, sin red y sin credenciales. Sólo
# la verificación criptográfica de la firma necesita el SDK.

logger = logging.getLogger(__name__)

#: Eventos que cambian el derecho de uso. Cualquier otro se ignora en silencio:
#: Stripe envía decenas de tipos y suscribirse a todos sólo añade ruido.
HANDLED_EVENTS = frozenset({
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
})


class SubscriptionStore(Protocol):
    """Lo que el webhook necesita de la capa de datos.

    Se declara como protocolo para que el módulo sea comprobable sin base de
    datos y sin conexión a Stripe.
    """

    def upsert_subscription(
        self,
        org_id: str,
        *,
        plan: str,
        status: str,
        stripe_customer_id: str | None,
        stripe_subscription_id: str | None,
        current_period_end: datetime | None,
        cancel_at_period_end: bool,
    ) -> None: ...

    def find_org_by_stripe_customer(self, customer_id: str) -> str | None: ...

    def record_audit(self, org_id: str | None, action: str, metadata: dict[str, Any]) -> None: ...

    def was_event_processed(self, event_id: str) -> bool: ...

    def mark_event_processed(self, event_id: str) -> None: ...


class WebhookError(Exception):
    """El webhook no se ha podido procesar."""


@dataclass(frozen=True, slots=True)
class WebhookResult:
    handled: bool
    event_type: str
    org_id: str | None = None
    detail: str = ""


def verify_signature(
    payload: bytes, signature_header: str, webhook_secret: str
) -> dict[str, Any]:
    """Verifica la firma del webhook y devuelve el evento.

    Sin esta comprobación, cualquiera que conozca la URL puede enviar un
    "pago completado" falso y regalarse el plan más caro. La verificación
    incluye una marca de tiempo, lo que además impide reenviar un evento
    legítimo capturado antes.

    Es importante pasar el cuerpo tal cual llegó, en bytes y sin volver a
    serializar. La firma cubre los bytes exactos: reordenar una clave del JSON
    la invalida.
    """
    import stripe  # noqa: PLC0415

    if not signature_header:
        raise WebhookError("Falta la cabecera Stripe-Signature.")
    if not webhook_secret:
        raise WebhookError("No hay secreto de webhook configurado.")
    try:
        return stripe.Webhook.construct_event(payload, signature_header, webhook_secret)
    except ValueError as exc:
        raise WebhookError("Cuerpo del webhook malformado.") from exc
    except stripe.SignatureVerificationError as exc:
        raise WebhookError("Firma del webhook inválida.") from exc


def _timestamp(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, tz=UTC) if value else None


def _resolve_plan(subscription: dict[str, Any]) -> str:
    """Determina el plan de una suscripción.

    Se prefiere la metadata, que la fija el servidor al crear la sesión. Si
    falta, se deduce del importe. Si tampoco cuadra, se degrada al gratuito en
    lugar de conceder acceso por defecto, que es el fallo clásico.
    """
    metadata = subscription.get("metadata") or {}
    candidate = metadata.get("plan")
    if candidate and candidate in {"starter", "growth", "scale"}:
        return candidate

    items = (subscription.get("items") or {}).get("data") or []
    if items:
        amount = (items[0].get("price") or {}).get("unit_amount")
        deduced = plan_from_amount(amount)
        if deduced:
            return deduced

    logger.warning(
        "Suscripción %s sin plan identificable. Se degrada a free.",
        subscription.get("id"),
    )
    return "free"


def handle_event(event: dict[str, Any], store: SubscriptionStore) -> WebhookResult:
    """Aplica un evento verificado sobre el estado de suscripciones.

    Es idempotente: Stripe reintenta los webhooks que no reciben un 200, y
    reintenta también cuando la respuesta tarda. Procesar dos veces el mismo
    evento debe dar exactamente el mismo resultado.
    """
    event_type = event["type"]
    event_id = event["id"]

    if event_type not in HANDLED_EVENTS:
        return WebhookResult(handled=False, event_type=event_type, detail="Evento no relevante.")

    if store.was_event_processed(event_id):
        return WebhookResult(handled=True, event_type=event_type, detail="Evento ya procesado.")

    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        result = _handle_checkout_completed(obj, store)
    elif event_type == "invoice.payment_failed":
        result = _handle_payment_failed(obj, store)
    else:
        result = _handle_subscription_change(obj, store)

    store.mark_event_processed(event_id)
    return result


def _org_from(obj: dict[str, Any], store: SubscriptionStore) -> str | None:
    """Localiza la organización de un objeto de Stripe.

    Orden de preferencia: la metadata que puso el servidor, el
    `client_reference_id`, y como último recurso la búsqueda por cliente de
    Stripe. En ningún caso se usa el email, que es lo que el usuario controla.
    """
    metadata = obj.get("metadata") or {}
    org_id = metadata.get("org_id") or obj.get("client_reference_id")
    if org_id:
        return str(org_id)

    customer = obj.get("customer")
    if isinstance(customer, dict):
        customer = customer.get("id")
    if customer:
        return store.find_org_by_stripe_customer(str(customer))
    return None


def _handle_checkout_completed(session: dict[str, Any], store: SubscriptionStore) -> WebhookResult:
    org_id = _org_from(session, store)
    if not org_id:
        logger.error("Checkout %s sin organización identificable.", session.get("id"))
        return WebhookResult(False, "checkout.session.completed", detail="Sin organización.")

    if session.get("mode") != "subscription":
        return WebhookResult(False, "checkout.session.completed", org_id, "No es suscripción.")

    metadata = session.get("metadata") or {}
    plan = metadata.get("plan") or "free"
    customer = session.get("customer")
    subscription_id = session.get("subscription")

    # El estado real lo trae el evento de suscripción que llega justo después.
    # Aquí sólo se enlaza la organización con el cliente de Stripe para que ese
    # evento sepa a quién aplicarse.
    store.upsert_subscription(
        org_id,
        plan=plan if plan in {"starter", "growth", "scale"} else "free",
        status="trialing" if metadata.get("trial") == "1" else "active",
        stripe_customer_id=str(customer) if customer else None,
        stripe_subscription_id=str(subscription_id) if subscription_id else None,
        current_period_end=None,
        cancel_at_period_end=False,
    )
    store.record_audit(org_id, "billing.checkout_completed", {"plan": plan})
    return WebhookResult(True, "checkout.session.completed", org_id, f"Plan {plan} activado.")


def _handle_subscription_change(
    subscription: dict[str, Any], store: SubscriptionStore
) -> WebhookResult:
    org_id = _org_from(subscription, store)
    if not org_id:
        logger.error("Suscripción %s sin organización.", subscription.get("id"))
        return WebhookResult(False, "customer.subscription", detail="Sin organización.")

    status = subscription.get("status", "inactive")
    plan = _resolve_plan(subscription) if status in ENTITLED_STATUSES else "free"

    customer = subscription.get("customer")
    store.upsert_subscription(
        org_id,
        plan=plan,
        status=status,
        stripe_customer_id=str(customer) if customer else None,
        stripe_subscription_id=str(subscription.get("id")),
        current_period_end=_timestamp(subscription.get("current_period_end")),
        cancel_at_period_end=bool(subscription.get("cancel_at_period_end")),
    )
    store.record_audit(
        org_id, "billing.subscription_updated", {"plan": plan, "status": status}
    )
    return WebhookResult(True, "customer.subscription", org_id, f"{plan} / {status}")


def _handle_payment_failed(invoice: dict[str, Any], store: SubscriptionStore) -> WebhookResult:
    """Un recibo devuelto no corta el servicio de inmediato.

    Stripe reintenta durante varios días. Cortar en el primer fallo castiga a
    un cliente que sólo ha renovado la tarjeta. El corte llega solo, vía
    `customer.subscription.updated` con estado `canceled`, si nunca paga.
    """
    org_id = _org_from(invoice, store)
    if org_id:
        store.record_audit(
            org_id,
            "billing.payment_failed",
            {"invoice": invoice.get("id"), "attempt": invoice.get("attempt_count")},
        )
    return WebhookResult(True, "invoice.payment_failed", org_id, "Registrado, sin cortar acceso.")


def entitlement_is_active(status: str, plan: str) -> bool:
    """Única función que decide si una organización puede usar el producto.

    Toda la aplicación pregunta aquí. Tener un solo sitio donde se decide es lo
    que evita que dentro de seis meses haya tres comprobaciones distintas y una
    de ellas esté mal.
    """
    return status in ENTITLED_STATUSES and not get_plan(plan).is_free
