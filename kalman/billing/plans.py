"""Catálogo de planes.

Cambio de estrategia de precios frente a la versión anterior
-----------------------------------------------------------
Antes: 79, 199 y 499 euros al mes, sin plan gratuito y sin relación entre lo
que se cobra y lo que se entrega. Un desconocido sin clientes ni reputación no
cierra una venta de 199 euros al mes con un formulario. Ese precio exige un
comercial, y no hay comercial.

Ahora: hay un plan gratuito de verdad, el primer plan de pago cuesta menos que
una comida y el precio va ligado a una unidad que el cliente entiende, que son
las filas procesadas. El objetivo de esta fase no es maximizar el ingreso por
cliente, es conseguir los diez primeros clientes y aprender de ellos. El precio
se sube después, cuando haya casos reales que lo justifiquen.

Los importes se declaran en céntimos porque es la unidad de Stripe. Trabajar
en euros con decimales acaba, siempre, en un céntimo perdido por redondeo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Plan:
    """Un plan del catálogo."""

    key: str
    name: str
    price_cents: int
    monthly_rows: int
    api_access: bool
    retention_days: int
    summary: str
    features: tuple[str, ...]

    @property
    def price_eur(self) -> float:
        return self.price_cents / 100

    @property
    def is_free(self) -> bool:
        return self.price_cents == 0

    @property
    def price_label(self) -> str:
        return "Gratis" if self.is_free else f"{self.price_eur:,.0f} €/mes"


PLANS: dict[str, Plan] = {
    "free": Plan(
        key="free",
        name="Free",
        price_cents=0,
        monthly_rows=2_000,
        api_access=False,
        retention_days=7,
        summary="Para probar con datos reales sin dar una tarjeta.",
        features=(
            "2.000 filas al mes",
            "Validación de NIF, CIF, NIE e IBAN",
            "Detección de duplicados",
            "Exportación a CSV",
        ),
    ),
    "starter": Plan(
        key="starter",
        name="Starter",
        price_cents=2_900,
        monthly_rows=50_000,
        api_access=False,
        retention_days=30,
        summary="Para una gestoría o una empresa pequeña.",
        features=(
            "50.000 filas al mes",
            "Todo lo del plan Free",
            "Informe de auditoría en PDF",
            "Historial de 30 días",
        ),
    ),
    "growth": Plan(
        key="growth",
        name="Growth",
        price_cents=9_900,
        monthly_rows=500_000,
        api_access=True,
        retention_days=90,
        summary="Para integrarlo en un proceso automático.",
        features=(
            "500.000 filas al mes",
            "Acceso a la API con claves propias",
            "Seudonimización con clave de la organización",
            "Historial de 90 días",
        ),
    ),
    "scale": Plan(
        key="scale",
        name="Scale",
        price_cents=39_900,
        monthly_rows=5_000_000,
        api_access=True,
        retention_days=365,
        summary="Para volumen alto y requisitos de cumplimiento.",
        features=(
            "5.000.000 de filas al mes",
            "Todo lo del plan Growth",
            "Contrato de encargado del tratamiento firmado",
            "Historial de 365 días",
        ),
    ),
}

FREE_PLAN = PLANS["free"]

#: Planes que dan acceso a la API. Se deriva del catálogo para que añadir un
#: plan no obligue a acordarse de tocar una segunda lista.
API_PLANS = frozenset(k for k, p in PLANS.items() if p.api_access)

#: Estados de Stripe que conceden acceso. `past_due` se incluye a propósito:
#: cortar el servicio en el primer recibo devuelto pierde clientes que sólo
#: han cambiado de tarjeta. Stripe reintenta durante días.
ENTITLED_STATUSES = frozenset({"active", "trialing", "past_due"})


def get_plan(key: str | None) -> Plan:
    """Devuelve un plan por su clave, o el gratuito si no existe.

    Nunca lanza. Un plan desconocido en base de datos, por ejemplo tras
    retirar un plan del catálogo, degrada al gratuito en lugar de tumbar la
    aplicación del cliente.
    """
    return PLANS.get((key or "").lower(), FREE_PLAN)


def plan_from_amount(amount_cents: int | None) -> str | None:
    """Deduce el plan a partir del importe cobrado.

    Es la red de seguridad para cuando falta la metadata en Stripe, por
    ejemplo en una suscripción creada a mano desde el panel.
    """
    if amount_cents is None:
        return None
    for key, plan in PLANS.items():
        if plan.price_cents == amount_cents and not plan.is_free:
            return key
    return None


def can_process(plan_key: str, rows_used: int, rows_requested: int) -> tuple[bool, str]:
    """Comprueba si una organización tiene cupo para el trabajo que pide.

    Devuelve el motivo en lenguaje llano, porque va directo a la pantalla del
    usuario. Un mensaje de cuota que no dice cuánto queda es una llamada a
    soporte garantizada.
    """
    plan = get_plan(plan_key)
    remaining = plan.monthly_rows - rows_used

    if rows_requested <= remaining:
        return True, ""

    if remaining <= 0:
        return False, (
            f"Has consumido las {plan.monthly_rows:,} filas de tu plan {plan.name} "
            f"este mes. El contador se reinicia el día 1."
        )

    return False, (
        f"Este fichero tiene {rows_requested:,} filas y sólo te quedan "
        f"{remaining:,} en el plan {plan.name} este mes."
    )
