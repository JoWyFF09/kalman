"""Pruebas de las primitivas de seguridad.

Cada prueba corresponde a un fallo concreto de la versión anterior, en la que
las contraseñas se guardaban en claro y se comparaban con el operador de
igualdad.
"""

from __future__ import annotations

import time

import pytest

from kalman.security.passwords import (
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    generate_api_key,
    hash_api_key,
    hash_password,
    needs_rehash,
    verify_password,
)

BUENA = "una frase larga y poco comun 2026"


def test_la_contrasena_no_aparece_en_el_hash() -> None:
    """Lo mínimo exigible, y lo que la versión anterior incumplía."""
    almacenado = hash_password(BUENA)
    assert BUENA not in almacenado
    assert "frase" not in almacenado


def test_verificacion_correcta() -> None:
    assert verify_password(BUENA, hash_password(BUENA))


def test_verificacion_incorrecta() -> None:
    assert not verify_password("otra cosa distinta 123", hash_password(BUENA))


def test_dos_hashes_de_la_misma_contrasena_son_distintos() -> None:
    """Sal aleatoria por usuario. Sin ella, dos usuarios con la misma
    contraseña se delatan mutuamente y una tabla precalculada las rompe todas.
    """
    assert hash_password(BUENA) != hash_password(BUENA)


def test_hash_corrupto_no_revienta() -> None:
    for basura in ("", "abc", "scrypt$mal", "$$$$$", "otroalgoritmo$1$2$3$aa$bb"):
        assert not verify_password(BUENA, basura)


def test_contrasena_vacia_nunca_valida() -> None:
    assert not verify_password("", hash_password(BUENA))


@pytest.mark.parametrize(
    "debil",
    ["corta", "1234567", "aaaaaaaaaaaaaaaa", "contrasena123", "spacenet1234"],
)
def test_contrasenas_debiles_se_rechazan(debil: str) -> None:
    with pytest.raises(WeakPasswordError):
        hash_password(debil)


def test_la_politica_exige_longitud_minima() -> None:
    with pytest.raises(WeakPasswordError, match=str(MIN_PASSWORD_LENGTH)):
        hash_password("a" * (MIN_PASSWORD_LENGTH - 1))


def test_el_formato_guarda_los_parametros() -> None:
    """Permite endurecer scrypt en el futuro sin invalidar los hashes viejos."""
    partes = hash_password(BUENA).split("$")
    assert partes[0] == "scrypt"
    assert int(partes[1]) >= 2**15


def test_detecta_parametros_obsoletos() -> None:
    debil = "scrypt$1024$8$1$" + "aa" * 16 + "$" + "bb" * 32
    assert needs_rehash(debil)
    assert not needs_rehash(hash_password(BUENA))


def test_verificacion_tarda_lo_mismo_acierte_o_falle() -> None:
    """Comparar con == permitiría deducir el hash midiendo tiempos.

    El margen es amplio a propósito: en una máquina compartida los tiempos
    fluctúan. Lo que se descarta aquí es una diferencia de orden de magnitud,
    que es la que explota un ataque real.
    """
    almacenado = hash_password(BUENA)

    inicio = time.perf_counter()
    for _ in range(5):
        verify_password(BUENA, almacenado)
    correcto = time.perf_counter() - inicio

    inicio = time.perf_counter()
    for _ in range(5):
        verify_password("xxxxxxxxxxxxxxxxxxxxx", almacenado)
    incorrecto = time.perf_counter() - inicio

    assert 0.2 < (correcto / incorrecto) < 5.0


# ------------------------------------------------------------- claves de API

def test_la_clave_de_api_lleva_prefijo_reconocible() -> None:
    """Un prefijo fijo permite detectar la clave si se filtra en un repositorio."""
    raw, _ = generate_api_key()
    assert raw.startswith("kal_")


def test_la_clave_de_api_tiene_entropia_suficiente() -> None:
    raw, _ = generate_api_key()
    assert len(raw) > 40


def test_dos_claves_nunca_coinciden() -> None:
    claves = {generate_api_key()[0] for _ in range(200)}
    assert len(claves) == 200


def test_el_hash_de_la_clave_es_estable() -> None:
    """Debe poder buscarse en base de datos, así que el hash es determinista."""
    raw, digest = generate_api_key()
    assert hash_api_key(raw) == digest
    assert hash_api_key(f"  {raw}  ") == digest


def test_la_clave_en_claro_no_se_deduce_del_hash() -> None:
    raw, digest = generate_api_key()
    assert raw not in digest
    assert len(digest) == 64
