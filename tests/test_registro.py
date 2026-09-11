"""Pruebas del alta de autoservicio.

Hasta ahora una cuenta se creaba ejecutando un script a mano por cada cliente.
Eso funciona con uno y es imposible con veinte.

Aquí se prueba lo que no necesita base de datos: la validación de los datos y
la generación del identificador de URL. El camino que escribe en la base se
comprueba en el entorno real, porque simularla con objetos falsos demostraría
que la simulación funciona, no que el producto funciona.
"""

from __future__ import annotations

import pytest

from kalman.core.normalize import slugify
from kalman.db.repository import RegistrationError, validar_alta


# ----------------------------------------------------------------- validacion

def test_un_alta_normal_pasa() -> None:
    nombre, email = validar_alta("Asesoría Gómez S.L.", "info@gomez.es")
    assert nombre == "Asesoría Gómez S.L."
    assert email == "info@gomez.es"


def test_el_email_se_normaliza_a_minusculas() -> None:
    """Si no, el mismo cliente puede registrarse dos veces cambiando mayúsculas."""
    _, email = validar_alta("Empresa", "  Info@Gomez.ES  ")
    assert email == "info@gomez.es"


def test_se_recortan_los_espacios_del_nombre() -> None:
    nombre, _ = validar_alta("   Asesoría Gómez   ", "a@b.es")
    assert nombre == "Asesoría Gómez"


@pytest.mark.parametrize(
    "nombre",
    ["", " ", "A", "   x   "],
)
def test_nombre_demasiado_corto(nombre: str) -> None:
    with pytest.raises(RegistrationError, match="nombre de tu empresa"):
        validar_alta(nombre, "a@b.es")


def test_nombre_desmesurado() -> None:
    with pytest.raises(RegistrationError, match="demasiado largo"):
        validar_alta("x" * 200, "a@b.es")


@pytest.mark.parametrize(
    "email",
    ["sin-arroba", "a@b", "@b.com", "a@", "a@@b.com", "a@.com", "a@b.", ""],
)
def test_email_invalido(email: str) -> None:
    with pytest.raises(RegistrationError, match="email"):
        validar_alta("Empresa", email)


def test_email_con_espacios() -> None:
    """Un copiar y pegar desde Word mete espacios raros con frecuencia."""
    with pytest.raises(RegistrationError, match="espacios"):
        validar_alta("Empresa", "a b@c.com")


def test_los_mensajes_van_dirigidos_a_una_persona() -> None:
    """Quien los lee es un gestor rellenando un formulario, no un programador."""
    for nombre, email in [("", "a@b.es"), ("Empresa", "roto")]:
        with pytest.raises(RegistrationError) as fallo:
            validar_alta(nombre, email)
        mensaje = str(fallo.value)
        assert mensaje[0].isupper()
        assert mensaje.endswith(".")
        assert "Error" not in mensaje
        assert "None" not in mensaje


# ------------------------------------------------------------ identificador

def test_el_identificador_es_apto_para_una_url() -> None:
    assert slugify("Asesoría Gómez & Hijos, S.L.") == "asesoria-gomez-hijos-s-l"


def test_la_enye_se_transcribe_en_la_url() -> None:
    """Al comparar apellidos, Peña y Pena son distintos. En una URL, una eñe
    sólo da problemas."""
    assert slugify("Talleres Peña") == "talleres-pena"


@pytest.mark.parametrize("nombre", ["A", "", "   ", "!!!", "---"])
def test_un_nombre_sin_letras_cae_al_valor_por_defecto(nombre: str) -> None:
    assert slugify(nombre) == "organizacion"


def test_el_identificador_cumple_lo_que_exige_el_esquema() -> None:
    """La tabla obliga a empezar por letra o dígito y a medir entre 2 y 63.

    Un slug que no cumpla revienta el alta con un error de restricción, que es
    justo lo que el cliente no debe ver.
    """
    import re

    patron = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
    ejemplos = [
        "Asesoría Gómez & Hijos, S.L.",
        "  ---Talleres---  ",
        "ñ" * 80,
        "123 Transportes",
        "Éléctrica Ñu",
        "x" * 200,
    ]
    for nombre in ejemplos:
        slug = slugify(nombre)
        assert patron.match(slug), f"{nombre!r} produjo {slug!r}"
