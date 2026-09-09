"""Pruebas de la API.

Sólo se prueban aquí los caminos que no tocan base de datos. Lo que sí la toca
se prueba contra una base real en el entorno de integración, porque simularla
con objetos falsos comprobaría que la simulación funciona, no que el producto
funciona.

Lo que sí se comprueba sin base de datos, y es lo importante, es que ninguna
ruta de pago o de datos responde sin autenticación.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="La API requiere FastAPI.")

from fastapi.testclient import TestClient  # noqa: E402

from kalman.api.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz_no_requiere_autenticacion(client: TestClient) -> None:
    respuesta = client.get("/healthz")
    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "ok"


def test_validate_es_publico_y_valida_un_nif(client: TestClient) -> None:
    """Es la demostración del producto. Debe funcionar sin registrarse."""
    respuesta = client.post("/v1/validate", json={"kind": "tax_id", "value": "B65410011"})
    assert respuesta.status_code == 200
    assert respuesta.json()["valid"] is True


def test_validate_explica_por_que_algo_es_invalido(client: TestClient) -> None:
    respuesta = client.post("/v1/validate", json={"kind": "iban", "value": "ES9121000418450200051333"})
    cuerpo = respuesta.json()
    assert cuerpo["valid"] is False
    assert cuerpo["rule"] == "iban.checksum"
    assert cuerpo["message"]


def test_validate_rechaza_un_tipo_desconocido(client: TestClient) -> None:
    respuesta = client.post("/v1/validate", json={"kind": "loquesea", "value": "x"})
    assert respuesta.status_code == 422


def test_validate_rechaza_un_valor_desmesurado(client: TestClient) -> None:
    """Sin este límite, el punto público gratuito es un vector de abuso."""
    respuesta = client.post("/v1/validate", json={"kind": "email", "value": "a" * 5000})
    assert respuesta.status_code == 422


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("post", "/v1/clean"),
        ("post", "/v1/clean/file"),
        ("get", "/v1/usage"),
    ],
)
def test_las_rutas_de_datos_exigen_clave_de_api(
    client: TestClient, metodo: str, ruta: str
) -> None:
    """Ninguna ruta que toque datos o cuota puede responder sin autenticar."""
    if metodo == "get":
        respuesta = client.get(ruta)
    else:
        respuesta = client.post(ruta, json={"records": [{"a": 1}]})
    assert respuesta.status_code == 401


def test_una_clave_mal_formada_no_pasa(client: TestClient) -> None:
    respuesta = client.get("/v1/usage", headers={"Authorization": "kal_sin_bearer"})
    assert respuesta.status_code == 401


def test_el_webhook_rechaza_una_firma_ausente(client: TestClient) -> None:
    """Sin firma verificada cualquiera se regalaría el plan más caro."""
    respuesta = client.post(
        "/v1/stripe/webhook",
        content=b'{"id":"evt_falso","type":"customer.subscription.updated"}',
    )
    assert respuesta.status_code in (400, 500)
    assert respuesta.status_code != 200


def test_el_webhook_rechaza_una_firma_invalida(client: TestClient) -> None:
    respuesta = client.post(
        "/v1/stripe/webhook",
        content=b'{"id":"evt_falso"}',
        headers={"stripe-signature": "t=1,v1=firmainventada"},
    )
    assert respuesta.status_code != 200


def test_la_documentacion_esta_publicada(client: TestClient) -> None:
    """Un cliente técnico decide en la página de documentación, no en la web."""
    assert client.get("/docs").status_code == 200
    esquema = client.get("/openapi.json").json()
    assert "/v1/clean" in esquema["paths"]
    assert "/v1/validate" in esquema["paths"]
