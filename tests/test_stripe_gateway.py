"""Pruebas de la pasarela de pago.

Se prueban los parámetros que se le mandan a Stripe, con un cliente falso que
los apunta. No se toca la red: lo que importa aquí no es que Stripe conteste,
es que le pedimos exactamente lo que debemos.

La prueba central nace de un fallo que llegó a producción. Al recoger el NIF
del cliente para poder emitir factura, Stripe rechazaba la sesión con:

    Tax ID collection requires updating business name on the customer.

El motivo es que, cuando se pasa un cliente que ya existe, Stripe se niega a
recoger el NIF y la dirección si no se le autoriza expresamente a guardarlos en
esa ficha. Faltaba `customer_update`. El resultado era que el cliente pulsaba
el botón de pagar y no pasaba nada.
"""

from __future__ import annotations

from typing import Any

import pytest

from kalman.billing.stripe_gateway import BillingError, StripeGateway

PRECIOS = {
    "starter": "price_prueba_starter",
    "growth": "price_prueba_growth",
    "scale": "price_prueba_scale",
}


class _Recogido:
    """Objeto de respuesta mínimo, con los atributos que usa el código."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _ClienteFalso:
    """Cliente de Stripe que apunta lo que le piden en vez de llamar a nadie."""

    def __init__(self, cliente_existe: bool = True) -> None:
        self.checkout_params: dict[str, Any] | None = None
        self.customer_params: dict[str, Any] | None = None
        self.portal_params: dict[str, Any] | None = None
        self._existe = cliente_existe

        padre = self

        class _Customers:
            def search(self, params: dict[str, Any]) -> Any:
                padre.search_params = params
                datos = [_Recogido(id="cus_existente")] if padre._existe else []
                return _Recogido(data=datos)

            def create(self, params: dict[str, Any]) -> Any:
                padre.customer_params = params
                return _Recogido(id="cus_nuevo")

        class _Sessions:
            def create(self, params: dict[str, Any]) -> Any:
                padre.checkout_params = params
                return _Recogido(id="cs_prueba", url="https://checkout.stripe.com/prueba")

        class _PortalSessions:
            def create(self, params: dict[str, Any]) -> Any:
                padre.portal_params = params
                return _Recogido(url="https://billing.stripe.com/prueba")

        self.v1 = _Recogido(
            customers=_Customers(),
            checkout=_Recogido(sessions=_Sessions()),
            billing_portal=_Recogido(sessions=_PortalSessions()),
        )


@pytest.fixture
def gateway() -> StripeGateway:
    pasarela = StripeGateway("sk_test_falsa", "https://kalman-app.onrender.com", PRECIOS)
    pasarela._client = _ClienteFalso()  # type: ignore[assignment]
    return pasarela


def _params(gateway: StripeGateway) -> dict[str, Any]:
    gateway.create_checkout("org-1", "Talleres Gomez SL", "info@gomez.es", "growth")
    return gateway._client.checkout_params  # type: ignore[union-attr]


# --------------------------------------------------------------- regresion

def test_recoger_el_nif_exige_autorizar_la_actualizacion(gateway: StripeGateway) -> None:
    """El fallo que llego a produccion.

    Si se pide el NIF o la direccion de un cliente que ya existe sin mandar
    customer_update, Stripe rechaza la sesion entera y el cliente no llega a
    ver la pantalla de pago.
    """
    params = _params(gateway)

    assert params["tax_id_collection"] == {"enabled": True}
    assert "customer_update" in params, (
        "Sin customer_update, Stripe rechaza la sesion con "
        "'Tax ID collection requires updating business name on the customer'"
    )
    assert params["customer_update"]["name"] == "auto"
    assert params["customer_update"]["address"] == "auto"


def test_si_se_pide_direccion_tambien_hay_que_autorizarla(gateway: StripeGateway) -> None:
    """La misma regla vale para billing_address_collection."""
    params = _params(gateway)
    if params.get("billing_address_collection") == "required":
        assert params["customer_update"].get("address") == "auto"


# ------------------------------------------------------- identidad del pago

def test_la_sesion_lleva_la_organizacion(gateway: StripeGateway) -> None:
    """Es lo que el webhook lee para saber a quien activar.

    Sin esto habria que fiarse del navegador, que es justo el agujero que
    tenia la version anterior del producto.
    """
    params = _params(gateway)
    assert params["client_reference_id"] == "org-1"
    assert params["metadata"]["org_id"] == "org-1"
    assert params["subscription_data"]["metadata"]["org_id"] == "org-1"


def test_la_sesion_lleva_el_plan(gateway: StripeGateway) -> None:
    params = _params(gateway)
    assert params["metadata"]["plan"] == "growth"
    assert params["subscription_data"]["metadata"]["plan"] == "growth"


def test_usa_el_identificador_de_precio_configurado(gateway: StripeGateway) -> None:
    """El importe vive en Stripe, no en el codigo.

    Si viajara en cada peticion, un despliegue mal hecho cobraria otra cosa.
    """
    params = _params(gateway)
    assert params["line_items"] == [{"price": "price_prueba_growth", "quantity": 1}]
    assert "price_data" not in str(params)


def test_es_una_suscripcion_y_no_un_pago_suelto(gateway: StripeGateway) -> None:
    assert _params(gateway)["mode"] == "subscription"


def test_las_urls_de_vuelta_apuntan_a_la_aplicacion(gateway: StripeGateway) -> None:
    params = _params(gateway)
    assert params["success_url"].startswith("https://kalman-app.onrender.com/")
    assert "checkout=success" in params["success_url"]
    assert "checkout=cancel" in params["cancel_url"]


def test_la_pasarela_va_en_castellano(gateway: StripeGateway) -> None:
    assert _params(gateway)["locale"] == "es"


# --------------------------------------------------------------- periodo de prueba

def test_sin_prueba_no_hay_periodo_gratuito(gateway: StripeGateway) -> None:
    gateway.create_checkout("org-1", "Empresa", "a@b.es", "growth", with_trial=False)
    datos = gateway._client.checkout_params["subscription_data"]  # type: ignore[union-attr]
    assert "trial_period_days" not in datos


def test_con_prueba_se_manda_el_periodo(gateway: StripeGateway) -> None:
    gateway.create_checkout("org-1", "Empresa", "a@b.es", "starter", with_trial=True)
    datos = gateway._client.checkout_params["subscription_data"]  # type: ignore[union-attr]
    assert datos["trial_period_days"] > 0


# ------------------------------------------------------------------- errores

def test_el_plan_gratuito_no_pasa_por_la_pasarela(gateway: StripeGateway) -> None:
    with pytest.raises(BillingError, match="no requiere pago"):
        gateway.create_checkout("org-1", "Empresa", "a@b.es", "free")


def test_sin_precio_configurado_se_avisa_de_cual_falta() -> None:
    """Un mensaje que dice exactamente que variable de entorno poner."""
    pasarela = StripeGateway("sk_test_falsa", "https://x.es", {})
    pasarela._client = _ClienteFalso()  # type: ignore[assignment]

    with pytest.raises(BillingError, match="STRIPE_PRICE_GROWTH"):
        pasarela.create_checkout("org-1", "Empresa", "a@b.es", "growth")


def test_sin_clave_no_se_construye_la_pasarela() -> None:
    with pytest.raises(BillingError, match="clave secreta"):
        StripeGateway("", "https://x.es", PRECIOS)


# --------------------------------------------------------------- cliente

def test_el_cliente_se_busca_por_organizacion_no_por_email(gateway: StripeGateway) -> None:
    """El email cambia y puede repetirse entre organizaciones. El id no."""
    gateway.ensure_customer("org-77", "Empresa", "a@b.es")
    consulta = gateway._client.search_params["query"]  # type: ignore[union-attr]
    assert "org-77" in consulta
    assert "metadata" in consulta


def test_si_no_existe_el_cliente_se_crea_con_su_organizacion() -> None:
    pasarela = StripeGateway("sk_test_falsa", "https://x.es", PRECIOS)
    pasarela._client = _ClienteFalso(cliente_existe=False)  # type: ignore[assignment]

    assert pasarela.ensure_customer("org-9", "Empresa", "a@b.es") == "cus_nuevo"
    creado = pasarela._client.customer_params  # type: ignore[union-attr]
    assert creado["metadata"]["org_id"] == "org-9"


def test_el_modo_real_se_detecta_por_la_clave() -> None:
    """Sirve para avisar cuando se esta a punto de cobrar de verdad."""
    assert StripeGateway("sk_live_x", "https://x.es", PRECIOS).is_live
    assert not StripeGateway("sk_test_x", "https://x.es", PRECIOS).is_live
