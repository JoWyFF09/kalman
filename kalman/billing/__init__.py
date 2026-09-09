"""Facturación. Stripe es la única fuente de verdad del derecho de uso.

El catálogo de planes y la lógica de webhooks no dependen del SDK de Stripe y
se importan siempre. La pasarela sí lo necesita, así que se carga bajo demanda
mediante el gancho de módulo del PEP 562. De este modo un despliegue que sólo
use el motor, por ejemplo un proceso por lotes, no arrastra el SDK ni exige
credenciales para arrancar.
"""

from typing import TYPE_CHECKING, Any

from .plans import (
    API_PLANS,
    ENTITLED_STATUSES,
    FREE_PLAN,
    PLANS,
    Plan,
    can_process,
    get_plan,
    plan_from_amount,
)
from .webhooks import (
    HANDLED_EVENTS,
    WebhookError,
    WebhookResult,
    entitlement_is_active,
    handle_event,
    verify_signature,
)

if TYPE_CHECKING:
    from .stripe_gateway import BillingError, CheckoutSession, StripeGateway

_LAZY = {"StripeGateway", "CheckoutSession", "BillingError"}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from . import stripe_gateway

        return getattr(stripe_gateway, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PLANS",
    "Plan",
    "FREE_PLAN",
    "API_PLANS",
    "ENTITLED_STATUSES",
    "HANDLED_EVENTS",
    "get_plan",
    "can_process",
    "plan_from_amount",
    "StripeGateway",
    "CheckoutSession",
    "BillingError",
    "verify_signature",
    "handle_event",
    "entitlement_is_active",
    "WebhookError",
    "WebhookResult",
]
