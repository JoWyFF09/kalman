"""Límite de peticiones por minuto.

Por qué hace falta antes de abrir nada al público
--------------------------------------------------
`/v1/validate` está abierto sin autenticación a propósito: es la demostración
del producto. Sin freno, una sola persona con un bucle de tres líneas puede
lanzar mil peticiones por segundo y tumbar el servicio para todos los demás.
No hace falta mala intención: basta con un script mal escrito.

Cómo funciona: cubo de fichas
-----------------------------
Cada cliente tiene un cubo con un número máximo de fichas. Cada petición gasta
una. El cubo se rellena solo a un ritmo constante.

Se ha elegido esto y no una simple cuenta por minuto porque el cubo permite
ráfagas. Un cliente que integra Kalman en su proceso nocturno manda cincuenta
peticiones seguidas y luego nada durante una hora. Con una cuenta por minuto
eso se rechaza; con el cubo se acepta, que es lo correcto, porque en promedio
no está abusando.

Límite de este diseño, dicho claramente
---------------------------------------
Los cubos viven en memoria del proceso. Con dos copias del servidor detrás de
un balanceador, cada una lleva su propia cuenta y el límite real es el doble
del configurado. Para el tamaño actual eso da igual. El día que haya varias
copias, esto se mueve a Redis y la interfaz de este módulo no cambia.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

#: Peticiones por minuto según el plan. El punto público es el más restrictivo
#: porque es el único que puede usar cualquiera sin identificarse.
LIMITS_PER_MINUTE: dict[str, int] = {
    # Darse de alta escribe en la base de datos sin que nadie se haya
    # identificado, asi que es el punto mas abusable de todos. Cinco por
    # minuto sobra para una persona y arruina un bucle.
    "signup": 5,
    "public": 30,
    "free": 60,
    "starter": 60,
    "growth": 120,
    "scale": 600,
}

#: Cuántas fichas caben en el cubo, como múltiplo del ritmo por minuto. Con 1.0
#: se permite gastar el minuto entero de golpe y luego esperar.
BURST_FACTOR = 1.0

#: Cada cuántos segundos se barren los cubos que ya nadie usa. Sin esto el
#: diccionario crece sin límite y una lluvia de direcciones distintas acaba
#: comiéndose la memoria del servidor, que es el propio ataque que se pretende
#: evitar.
SWEEP_EVERY_SECONDS = 300


@dataclass(slots=True)
class Decision:
    """Resultado de pedir permiso para una petición."""

    allowed: bool
    remaining: int
    retry_after: int
    limit: int


class _Bucket:
    __slots__ = ("tokens", "last_refill", "last_seen")

    def __init__(self, tokens: float, now: float) -> None:
        self.tokens = tokens
        self.last_refill = now
        self.last_seen = now


class RateLimiter:
    """Cubos de fichas por clave, con barrido de los que caducan."""

    def __init__(self, sweep_every: int = SWEEP_EVERY_SECONDS) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._sweep_every = sweep_every
        # Se deja sin fijar a proposito. Si aqui se pusiera time.monotonic(),
        # una prueba que inyecta su propio reloj comparara dos relojes
        # distintos y el barrido no se disparara nunca. El primer check lo
        # inicializa con el mismo reloj que se este usando.
        self._last_sweep: float | None = None

    def check(self, key: str, plan: str = "public", now: float | None = None) -> Decision:
        """Consume una ficha del cubo de `key`. No bloquea nunca.

        Se usa el reloj monotónico y no la hora del sistema: si alguien cambia
        la hora del servidor o entra el horario de verano, un reloj normal
        podría regalar o robar minutos enteros de cuota.
        """
        per_minute = LIMITS_PER_MINUTE.get(plan, LIMITS_PER_MINUTE["public"])
        capacity = max(1.0, per_minute * BURST_FACTOR)
        refill_per_second = per_minute / 60.0
        instant = time.monotonic() if now is None else now

        with self._lock:
            self._maybe_sweep(instant)

            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(capacity, instant)
                self._buckets[key] = bucket

            elapsed = max(0.0, instant - bucket.last_refill)
            bucket.tokens = min(capacity, bucket.tokens + elapsed * refill_per_second)
            bucket.last_refill = instant
            bucket.last_seen = instant

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return Decision(True, int(bucket.tokens), 0, per_minute)

            faltan = 1.0 - bucket.tokens
            espera = max(1, int(faltan / refill_per_second) + 1)
            return Decision(False, 0, espera, per_minute)

    def _maybe_sweep(self, now: float) -> None:
        """Elimina los cubos llenos que nadie ha tocado en un buen rato.

        Sólo se borran los que están llenos: un cubo a medias todavía guarda
        deuda de quien lo usó, y borrarlo sería regalarle el límite.
        """
        if self._last_sweep is None:
            self._last_sweep = now
            return
        if now - self._last_sweep < self._sweep_every:
            return
        self._last_sweep = now

        limite = now - self._sweep_every
        capacidad_maxima = max(LIMITS_PER_MINUTE.values()) * BURST_FACTOR
        for clave in [
            k for k, b in self._buckets.items()
            if b.last_seen < limite and b.tokens >= min(capacidad_maxima, 1.0)
        ]:
            del self._buckets[clave]

    @property
    def tracked(self) -> int:
        """Cuántos cubos hay vivos. Sirve para vigilar la memoria."""
        with self._lock:
            return len(self._buckets)

    def reset(self) -> None:
        """Vacía todos los cubos. Sólo para las pruebas."""
        with self._lock:
            self._buckets.clear()
            self._last_sweep = None


def client_key(forwarded_for: str | None, client_host: str | None) -> str:
    """Identifica al llamante anónimo de la forma menos mala posible.

    Detrás de un proxy, la dirección real viene en `X-Forwarded-For` y la
    primera de la lista es la del cliente. Ese encabezado lo puede falsificar
    cualquiera, así que sólo debe confiarse cuando el servicio está
    efectivamente detrás de un proxy que lo reescribe, que es el caso en los
    alojamientos gestionados. Si no hay nada, se usa la dirección de la
    conexión.
    """
    if forwarded_for:
        primera = forwarded_for.split(",")[0].strip()
        if primera:
            return primera
    return client_host or "desconocido"
