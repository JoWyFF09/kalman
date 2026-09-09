"""Configuración común de las pruebas.

Las variables de entorno se fijan antes de que nadie importe `kalman.config`,
porque la configuración se lee una sola vez por proceso y queda cacheada.

Los valores son deliberadamente falsos y evidentes. Ninguna prueba de esta
batería abre una conexión real ni habla con Stripe: lo que se comprueba es que
las capas de autenticación y de configuración se comportan bien, no que la red
funciona.
"""

from __future__ import annotations

import os

_FAKE_ENV = {
    "KALMAN_ENV": "development",
    "DATABASE_URL": "postgresql://usuario:clave@localhost:5432/kalman_test",
    "KALMAN_PSEUDONYM_KEY": "clave-de-pruebas-no-usar-en-produccion-0123456789",
    "STRIPE_SECRET_KEY": "sk_test_clave_falsa_para_pruebas",
    "STRIPE_WEBHOOK_SECRET": "whsec_secreto_falso_para_pruebas",
    "APP_URL": "http://localhost:8501",
}

for name, value in _FAKE_ENV.items():
    os.environ.setdefault(name, value)
