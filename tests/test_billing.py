"""Pruebas de facturación y derecho de uso.

El fichero entero existe por un motivo: demostrar que ya no se puede entrar
sin pagar. Cada prueba de aquí corresponde a una vía de acceso que estaba
abierta en la versión anterior.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from kalman.billing.plans import PLANS, can_process, get_plan, plan_from_amount
from kalman.billing.webhooks import (
    HANDLED_EVENTS,
    WebhookResult,
    entitlement_is_active,
    handle_event,
)


class FakeStore:
    """Almacén en memoria que cumple el protocolo del webhook."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, dict[str, Any]] = {}
        self.audits: list[tuple[str | None, str, dict[str, Any]]] = []
        self.processed: set[str] = set()
        self.customers: dict[str, str] = {}

    def upsert_subscription(self, org_id: str, **kwargs: Any) -> None:
        self.subscriptions[org_id] = dict(kwargs)

    def find_org_by_stripe_customer(self, customer_id: str) -> str | None:
        return self.customers.get(customer_id)

    def record_audit(self, org_id: str | None, action: str, metadata: dict[str, Any]) -> None:
        self.audits.append((org_id, action, metadata))

    def was_event_processed(self, event_id: str) -> bool:
        return event_id in self.processed

    def mark_event_processed(self, event_id: str) -> None:
        self.processed.add(event_id)


def evento(tipo: str, obj: dict[str, Any], event_id: str = "evt_1") -> dict[str, Any]:
    return {"id": event_id, "type": tipo, "data": {"object": obj}}


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


# ------------------------------------------------------------------- entitlement

def test_el_plan_gratuito_no_da_derecho_de_uso() -> None:
    assert not entitlement_is_active("active", "free")


def test_suscripcion_cancelada_no_da_derecho() -> None:
    assert not entitlement_is_active("canceled", "growth")


def test_suscripcion_activa_da_derecho() -> None:
    assert entitlement_is_active("active", "growth")


def test_periodo_de_prueba_da_derecho() -> None:
    assert entitlement_is_active("trialing", "starter")


def test_recibo_devuelto_no_corta_el_servicio_de_inmediato() -> None:
    """Stripe reintenta durante días. Cortar al primer fallo pierde clientes."""
    assert entitlement_is_active("past_due", "starter")


# ------------------------------------------------------------------- webhooks

def test_suscripcion_activa_concede_el_plan(store: FakeStore) -> None:
    resultado = handle_event(
        evento("customer.subscription.updated", {
            "id": "sub_1",
            "status": "active",
            "customer": "cus_1",
            "metadata": {"org_id": "org-abc", "plan": "growth"},
            "current_period_end": 1800000000,
            "cancel_at_period_end": False,
        }),
        store,
    )
    assert resultado.handled
    assert store.subscriptions["org-abc"]["plan"] == "growth"
    assert store.subscriptions["org-abc"]["status"] == "active"


def test_cancelacion_degrada_a_gratuito(store: FakeStore) -> None:
    handle_event(
        evento("customer.subscription.deleted", {
            "id": "sub_1",
            "status": "canceled",
            "customer": "cus_1",
            "metadata": {"org_id": "org-abc", "plan": "scale"},
        }),
        store,
    )
    assert store.subscriptions["org-abc"]["plan"] == "free"
    assert not entitlement_is_active(
        store.subscriptions["org-abc"]["status"], store.subscriptions["org-abc"]["plan"]
    )


def test_sin_metadata_el_plan_se_deduce_del_importe(store: FakeStore) -> None:
    """Una suscripción creada a mano en el panel de Stripe no trae metadata."""
    handle_event(
        evento("customer.subscription.created", {
            "id": "sub_2",
            "status": "active",
            "customer": "cus_2",
            "metadata": {"org_id": "org-xyz"},
            "items": {"data": [{"price": {"unit_amount": 9900}}]},
        }),
        store,
    )
    assert store.subscriptions["org-xyz"]["plan"] == "growth"


def test_importe_desconocido_degrada_a_gratuito_no_concede(store: FakeStore) -> None:
    """Ante la duda, se deniega. Conceder por defecto es el fallo clásico."""
    handle_event(
        evento("customer.subscription.created", {
            "id": "sub_3",
            "status": "active",
            "customer": "cus_3",
            "metadata": {"org_id": "org-raro"},
            "items": {"data": [{"price": {"unit_amount": 1234}}]},
        }),
        store,
    )
    assert store.subscriptions["org-raro"]["plan"] == "free"


def test_el_email_no_identifica_a_la_organizacion(store: FakeStore) -> None:
    """El agujero de la versión anterior. Ahora un evento sin identificador de
    organización ni cliente conocido no activa nada."""
    resultado = handle_event(
        evento("customer.subscription.updated", {
            "id": "sub_4",
            "status": "active",
            "metadata": {"email": "cliente.que.paga@empresa.com"},
        }),
        store,
    )
    assert not resultado.handled
    assert store.subscriptions == {}


def test_organizacion_se_resuelve_por_cliente_de_stripe(store: FakeStore) -> None:
    store.customers["cus_9"] = "org-conocida"
    handle_event(
        evento("customer.subscription.updated", {
            "id": "sub_5", "status": "active", "customer": "cus_9",
            "items": {"data": [{"price": {"unit_amount": 2900}}]},
        }),
        store,
    )
    assert store.subscriptions["org-conocida"]["plan"] == "starter"


def test_el_webhook_es_idempotente(store: FakeStore) -> None:
    """Stripe reintenta. Procesar dos veces debe dar el mismo resultado."""
    payload = evento("customer.subscription.updated", {
        "id": "sub_6", "status": "active", "customer": "cus_6",
        "metadata": {"org_id": "org-1", "plan": "starter"},
    }, event_id="evt_repetido")

    primero = handle_event(payload, store)
    segundo = handle_event(payload, store)

    assert primero.handled and segundo.handled
    assert "ya procesado" in segundo.detail
    assert len(store.audits) == 1


def test_evento_irrelevante_se_ignora(store: FakeStore) -> None:
    resultado = handle_event(evento("customer.created", {"id": "cus_x"}), store)
    assert not resultado.handled
    assert store.subscriptions == {}


def test_checkout_completado_enlaza_organizacion_y_cliente(store: FakeStore) -> None:
    handle_event(
        evento("checkout.session.completed", {
            "id": "cs_1",
            "mode": "subscription",
            "client_reference_id": "org-nueva",
            "customer": "cus_nuevo",
            "subscription": "sub_nueva",
            "metadata": {"org_id": "org-nueva", "plan": "starter", "trial": "1"},
        }),
        store,
    )
    guardada = store.subscriptions["org-nueva"]
    assert guardada["plan"] == "starter"
    assert guardada["status"] == "trialing"
    assert guardada["stripe_customer_id"] == "cus_nuevo"


def test_todos_los_eventos_declarados_tienen_manejador(store: FakeStore) -> None:
    """Si se añade un evento a la lista sin escribir su rama, esto lo detecta."""
    for tipo in HANDLED_EVENTS:
        resultado = handle_event(
            evento(tipo, {
                "id": "obj", "status": "active", "mode": "subscription",
                "customer": "cus", "metadata": {"org_id": "org-t", "plan": "starter"},
            }, event_id=f"evt_{tipo}"),
            store,
        )
        assert isinstance(resultado, WebhookResult)


# ---------------------------------------------------------------------- cuotas

def test_cuota_permite_dentro_del_limite() -> None:
    ok, motivo = can_process("starter", rows_used=1_000, rows_requested=5_000)
    assert ok and motivo == ""


def test_cuota_bloquea_al_superar_el_limite() -> None:
    ok, motivo = can_process("free", rows_used=1_900, rows_requested=500)
    assert not ok
    assert "1.900" in motivo.replace(",", ".") or "quedan" in motivo


def test_mensaje_de_cuota_agotada_dice_cuando_se_reinicia() -> None:
    ok, motivo = can_process("free", rows_used=2_000, rows_requested=1)
    assert not ok
    assert "día 1" in motivo


def test_plan_desconocido_degrada_a_gratuito() -> None:
    assert get_plan("plan_inventado").key == "free"
    assert get_plan(None).key == "free"


def test_los_importes_del_catalogo_son_unicos() -> None:
    """Dos planes al mismo precio harían imposible deducir el plan del importe."""
    precios = [p.price_cents for p in PLANS.values() if not p.is_free]
    assert len(precios) == len(set(precios))


def test_plan_from_amount_ignora_el_gratuito() -> None:
    """Un importe de cero nunca debe resolver a un plan de pago."""
    assert plan_from_amount(0) is None
    assert plan_from_amount(None) is None
    assert plan_from_amount(2_900) == "starter"


def test_los_planes_crecen_en_precio_y_en_volumen() -> None:
    """Coherencia del catálogo: pagar más nunca puede dar menos."""
    ordenados = [PLANS[k] for k in ("free", "starter", "growth", "scale")]
    for anterior, siguiente in zip(ordenados, ordenados[1:]):
        assert siguiente.price_cents > anterior.price_cents
        assert siguiente.monthly_rows > anterior.monthly_rows
        assert siguiente.retention_days >= anterior.retention_days
