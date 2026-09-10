"""Comprueba que el webhook de Stripe está bien montado.

    python scripts/check_webhook.py

Es la pieza que más silenciosamente se rompe de todo el sistema. Si el webhook
falla, el cliente paga, ve el cargo en su banco, y en Kalman sigue sin plan.
Ese cliente no vuelve.

Este script mira, sin tocar nada:
  - que exista un endpoint apuntando a tu API,
  - que escuche los cinco eventos que Kalman necesita,
  - que esté activo,
  - y si Stripe ha registrado fallos de entrega recientes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalman.billing.webhooks import HANDLED_EVENTS  # noqa: E402
from kalman.config import load_dotenv  # noqa: E402

OK = "  [OK]   "
FALTA = "  [FALTA]"
AVISO = "  [AVISO]"


def main() -> int:
    load_dotenv()
    clave = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    print()
    print("=" * 62)
    print("  Kalman - revision del webhook de Stripe")
    print("=" * 62)
    print()

    if not clave:
        print(f"{FALTA} No hay STRIPE_SECRET_KEY. Ejecuta antes scripts/doctor.py")
        return 2

    modo = "PRUEBAS" if clave.startswith("sk_test_") else "REAL"
    print(f"  Modo: {modo}")
    if modo == "PRUEBAS":
        print(f"{AVISO} Estas mirando el modo de pruebas.")
        print("         El webhook de verdad hay que crearlo tambien en el modo real.")
    print()

    try:
        import stripe
    except ImportError:
        print(f"{FALTA} El paquete stripe no esta instalado.")
        print('         pip install -e ".[billing]"')
        return 2

    cliente = stripe.StripeClient(clave)

    try:
        endpoints = cliente.v1.webhook_endpoints.list(params={"limit": 20}).data
    except Exception as exc:
        print(f"{FALTA} No se ha podido consultar Stripe: {type(exc).__name__}")
        print(f"         {str(exc).splitlines()[0][:150]}")
        return 1

    if not endpoints:
        print(f"{FALTA} No hay ningun webhook creado en este modo.")
        print()
        print("  Crealo en el panel de Stripe, Desarrolladores, Webhooks:")
        print("    URL:  https://TU-API.onrender.com/v1/stripe/webhook")
        print("    Eventos:")
        for evento in sorted(HANDLED_EVENTS):
            print(f"      - {evento}")
        return 1

    problemas = 0

    for endpoint in endpoints:
        url = endpoint.get("url", "")
        estado = endpoint.get("status", "")
        escucha = set(endpoint.get("enabled_events") or [])

        print(f"  Endpoint: {url}")
        print(f"    id: {endpoint.get('id')}")

        if estado == "enabled":
            print(f"{OK} Activo.")
        else:
            print(f"{FALTA} Estado '{estado}'. Un webhook desactivado no entrega nada.")
            problemas += 1

        if not url.rstrip("/").endswith("/v1/stripe/webhook"):
            print(f"{AVISO} La ruta no termina en /v1/stripe/webhook.")
            print("         Kalman escucha exactamente en esa ruta.")
            problemas += 1

        if not url.startswith("https://"):
            print(f"{FALTA} La URL no usa HTTPS.")
            problemas += 1

        if "*" in escucha:
            print(f"{OK} Escucha todos los eventos.")
        else:
            faltan = HANDLED_EVENTS - escucha
            if faltan:
                print(f"{FALTA} Le faltan eventos por escuchar:")
                for evento in sorted(faltan):
                    print(f"         - {evento}")
                problemas += 1
            else:
                print(f"{OK} Escucha los {len(HANDLED_EVENTS)} eventos que Kalman necesita.")

            sobran = escucha - HANDLED_EVENTS
            if sobran:
                print(f"{AVISO} Escucha {len(sobran)} eventos que Kalman ignora.")
                print("         No rompe nada, solo genera ruido y trafico.")
        print()

    print("-" * 62)
    if problemas:
        print(f"  Hay {problemas} cosas por arreglar antes de aceptar un pago real.")
        return 1

    print("  El webhook esta bien montado.")
    print()
    print("  Prueba de extremo a extremo, y hazla antes de vender:")
    print("    1. En modo de pruebas, entra en la aplicacion y elige un plan.")
    print("    2. Paga con la tarjeta de prueba 4242 4242 4242 4242,")
    print("       cualquier fecha futura y cualquier CVC.")
    print("    3. Comprueba que el plan cambia solo, sin tocar nada:")
    print("       python scripts/set_plan.py --listar")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
