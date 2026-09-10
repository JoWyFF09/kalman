"""Pruebas del límite de peticiones.

Se prueban con un reloj falso que se pasa por parámetro, no esperando de
verdad. Una prueba que duerme sesenta segundos para comprobar un límite por
minuto no la ejecuta nadie, y una prueba que no se ejecuta no protege nada.
"""

from __future__ import annotations

import threading

import pytest

from kalman.api.ratelimit import LIMITS_PER_MINUTE, RateLimiter, client_key


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter()


def test_deja_pasar_dentro_del_limite(limiter: RateLimiter) -> None:
    tope = LIMITS_PER_MINUTE["public"]
    for i in range(tope):
        assert limiter.check("ip:1", "public", now=100.0).allowed, f"fallo en la {i}"


def test_corta_al_pasarse(limiter: RateLimiter) -> None:
    tope = LIMITS_PER_MINUTE["public"]
    for _ in range(tope):
        limiter.check("ip:1", "public", now=100.0)

    decision = limiter.check("ip:1", "public", now=100.0)
    assert not decision.allowed
    assert decision.remaining == 0
    assert decision.limit == tope


def test_dice_cuanto_hay_que_esperar(limiter: RateLimiter) -> None:
    """Sin Retry-After, un cliente reintenta en bucle y lo empeora."""
    for _ in range(LIMITS_PER_MINUTE["public"] + 1):
        decision = limiter.check("ip:1", "public", now=100.0)
    assert decision.retry_after >= 1
    assert decision.retry_after <= 60


def test_el_cubo_se_rellena_con_el_tiempo(limiter: RateLimiter) -> None:
    tope = LIMITS_PER_MINUTE["public"]
    for _ in range(tope):
        limiter.check("ip:1", "public", now=100.0)
    assert not limiter.check("ip:1", "public", now=100.0).allowed

    # Medio minuto despues debe haber recuperado la mitad de la cuota.
    assert limiter.check("ip:1", "public", now=130.0).allowed


def test_un_minuto_entero_devuelve_la_cuota_completa(limiter: RateLimiter) -> None:
    tope = LIMITS_PER_MINUTE["public"]
    for _ in range(tope):
        limiter.check("ip:1", "public", now=100.0)

    for i in range(tope):
        assert limiter.check("ip:1", "public", now=161.0).allowed, f"fallo en la {i}"


def test_permite_rafagas(limiter: RateLimiter) -> None:
    """Un proceso nocturno manda cincuenta seguidas y luego nada en una hora.

    Con una cuenta simple por minuto eso se rechazaria. Con el cubo de fichas
    se acepta, que es lo correcto: en promedio no esta abusando.
    """
    for _ in range(LIMITS_PER_MINUTE["growth"]):
        assert limiter.check("org:a", "growth", now=500.0).allowed


def test_cada_cliente_tiene_su_cubo(limiter: RateLimiter) -> None:
    """Que uno se pase no puede dejar fuera a los demas."""
    for _ in range(LIMITS_PER_MINUTE["public"] + 5):
        limiter.check("ip:abusa", "public", now=100.0)

    assert limiter.check("ip:inocente", "public", now=100.0).allowed


def test_cada_plan_tiene_su_cuota(limiter: RateLimiter) -> None:
    """Pagar mas tiene que dar mas. Si no, el catalogo miente."""
    assert LIMITS_PER_MINUTE["scale"] > LIMITS_PER_MINUTE["growth"]
    assert LIMITS_PER_MINUTE["growth"] > LIMITS_PER_MINUTE["public"]

    for _ in range(LIMITS_PER_MINUTE["public"] + 1):
        limiter.check("org:grande", "scale", now=100.0)
    assert limiter.check("org:grande", "scale", now=100.0).allowed


def test_un_plan_desconocido_cae_al_mas_restrictivo(limiter: RateLimiter) -> None:
    """Ante la duda se deniega, no se concede."""
    decision = limiter.check("org:raro", "plan_inventado", now=100.0)
    assert decision.limit == LIMITS_PER_MINUTE["public"]


# ------------------------------------------------------------------- memoria

def test_los_cubos_caducados_se_barren() -> None:
    """Sin barrido, una lluvia de IP distintas se come la memoria del servidor.

    Es decir, el propio ataque que el limite pretende evitar.
    """
    limiter = RateLimiter(sweep_every=10)

    for i in range(200):
        limiter.check(f"ip:{i}", "public", now=100.0)
    assert limiter.tracked == 200

    # Muy despues, y con una peticion que dispara el barrido.
    limiter.check("ip:nueva", "public", now=1000.0)
    assert limiter.tracked < 200


def test_no_se_barra_a_quien_tiene_deuda() -> None:
    """Borrar un cubo a medias seria regalarle el limite a quien se paso."""
    limiter = RateLimiter(sweep_every=10)

    for _ in range(LIMITS_PER_MINUTE["public"]):
        limiter.check("ip:abusa", "public", now=100.0)

    limiter.check("ip:otra", "public", now=1000.0)
    # Al barrer no se ha reiniciado su cuota: sigue sin poder pasar de golpe.
    decision = limiter.check("ip:abusa", "public", now=1000.5)
    assert decision.allowed  # ya se ha rellenado por tiempo, no por el barrido


# ------------------------------------------------------------ concurrencia

def test_aguanta_hilos_a_la_vez(limiter: RateLimiter) -> None:
    """Un servidor atiende varias peticiones a la vez.

    Sin cerrojo, dos hilos leen el mismo saldo y ambos gastan la misma ficha,
    con lo que el limite deja pasar el doble.
    """
    permitidas: list[bool] = []
    cerrojo = threading.Lock()
    tope = LIMITS_PER_MINUTE["public"]

    def golpear() -> None:
        for _ in range(20):
            ok = limiter.check("ip:concurrente", "public", now=100.0).allowed
            with cerrojo:
                permitidas.append(ok)

    hilos = [threading.Thread(target=golpear) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sum(permitidas) == tope, f"pasaron {sum(permitidas)}, el tope es {tope}"


# ------------------------------------------------------ identidad del cliente

def test_usa_la_primera_direccion_de_forwarded_for() -> None:
    """Detras de un proxy, la del cliente es la primera de la lista."""
    assert client_key("203.0.113.9, 70.41.3.18", "10.0.0.1") == "203.0.113.9"


def test_sin_proxy_usa_la_conexion() -> None:
    assert client_key(None, "203.0.113.9") == "203.0.113.9"
    assert client_key("", "203.0.113.9") == "203.0.113.9"


def test_sin_nada_no_revienta() -> None:
    assert client_key(None, None) == "desconocido"
