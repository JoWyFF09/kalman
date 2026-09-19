"""Pruebas de que el resultado del análisis sobrevive a cada interacción.

Existen por un fallo real que se veía así: el cliente analizaba un fichero,
pulsaba "Descargar en Excel", y la pantalla volvía a quedarse vacía con el
botón de Analizar. Lo mismo al escribir el coste por incidencia y pulsar Enter.

La causa es cómo funciona Streamlit: ante CUALQUIER interacción vuelve a
ejecutar el fichero entero de arriba abajo, y `st.button` sólo devuelve True
en la ejecución inmediatamente posterior al clic. El código era:

    if not st.button("Analizar"):
        return
    ...todo el resultado...

Así que el resultado sólo existía durante esa única ejecución. Al pulsar una
descarga, el botón devolvía False y se perdía todo.

Aquí se comprueban las dos mitades del arreglo: la lógica de guardado, y que
la estructura defectuosa no vuelva a colarse en ninguno de los dos ficheros
que Streamlit ejecuta.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

ENTRYPOINTS = [
    ROOT / "demo_app.py",
    ROOT / "kalman" / "web" / "app.py",
]


# --------------------------------------------------------------- firma y memo

def _modulo():
    """Importa app.py de verdad, saltando si no hay Streamlit instalado."""
    pytest.importorskip("streamlit", reason="app.py usa Streamlit.")
    import importlib

    return importlib.import_module("kalman.web.app")


def test_la_firma_distingue_el_contenido() -> None:
    app = _modulo()
    assert app._firma(b"uno", True) != app._firma(b"dos", True)


def test_la_firma_distingue_las_opciones() -> None:
    """Dos análisis del mismo fichero con opciones distintas no son el mismo.

    Si no, desactivar "buscar duplicados" dejaría en pantalla el resultado
    anterior, que sí los traía.
    """
    app = _modulo()
    assert app._firma(b"igual", True, False) != app._firma(b"igual", True, True)


def test_la_firma_es_estable() -> None:
    """La misma entrada da la misma firma en reejecuciones sucesivas."""
    app = _modulo()
    assert app._firma(b"datos", True, False) == app._firma(b"datos", True, False)


def test_memo_no_reconstruye_con_la_misma_firma() -> None:
    """Bajarse el CSV no debe reconstruir el Excel de diez mil líneas."""
    app = _modulo()
    import streamlit as st

    st.session_state.clear()
    veces = []

    def construir():
        veces.append(1)
        return "caro"

    assert app._memo("k", "firma-a", construir) == "caro"
    assert app._memo("k", "firma-a", construir) == "caro"
    assert app._memo("k", "firma-a", construir) == "caro"
    assert len(veces) == 1, "se ha reconstruido sin que cambiara la entrada"


def test_memo_reconstruye_si_cambia_la_firma() -> None:
    """Y si el usuario cambia el coste declarado, el PDF tiene que rehacerse."""
    app = _modulo()
    import streamlit as st

    st.session_state.clear()
    valores = iter(["primero", "segundo"])

    assert app._memo("k", "firma-a", lambda: next(valores)) == "primero"
    assert app._memo("k", "firma-b", lambda: next(valores)) == "segundo"
    assert app._memo("k", "firma-b", lambda: next(valores)) == "segundo"


# ------------------------------------------------- guardia contra la regresión

def _llamadas_a(nodo: ast.AST, nombre: str) -> bool:
    """¿Hay en este subárbol una llamada a `st.<nombre>`?"""
    return any(
        isinstance(hijo, ast.Call)
        and isinstance(hijo.func, ast.Attribute)
        and hijo.func.attr == nombre
        for hijo in ast.walk(nodo)
    )


@pytest.mark.parametrize("ruta", ENTRYPOINTS, ids=lambda p: p.name)
def test_ninguna_descarga_depende_de_un_boton(ruta: Path) -> None:
    """Un `st.download_button` dentro de un `if st.button(...)` está roto.

    Al pulsar la descarga, Streamlit reejecuta el fichero, el `st.button` de
    fuera devuelve False y el botón de descarga desaparece justo después de
    usarlo. Parece que la aplicación se ha reiniciado sola.

    La descarga se dibuja siempre, y lo caro de construir se guarda con _memo.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))

    culpables = [
        nodo.lineno
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.If)
        and _llamadas_a(nodo.test, "button")
        and any(_llamadas_a(cuerpo, "download_button") for cuerpo in nodo.body)
    ]

    assert not culpables, (
        f"{ruta.name}, linea(s) {culpables}: hay una descarga dentro de un "
        "'if st.button(...)'. Desaparecera en cuanto el usuario la pulse."
    )


def test_el_analisis_se_guarda_en_la_sesion() -> None:
    """El resultado no puede vivir sólo en la ejecución del clic.

    Se comprueba la estructura, no el texto: dentro de `cleaning_section`
    tiene que haber una escritura a `st.session_state.analisis`, y el pintado
    del resultado NO puede estar dentro del `if st.button("Analizar")`.
    """
    ruta = ROOT / "kalman" / "web" / "app.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))

    funcion = next(
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "cleaning_section"
    )

    guarda = any(
        isinstance(nodo, ast.Attribute) and nodo.attr == "analisis"
        for nodo in ast.walk(funcion)
    )
    assert guarda, "cleaning_section no guarda el analisis en st.session_state"

    dentro_del_boton = [
        nodo.lineno
        for nodo in ast.walk(funcion)
        if isinstance(nodo, ast.If)
        and _llamadas_a(nodo.test, "button")
        and any(
            isinstance(hijo, ast.Call)
            and isinstance(hijo.func, ast.Name)
            and hijo.func.id == "_render_result"
            for cuerpo in nodo.body
            for hijo in ast.walk(cuerpo)
        )
    ]
    assert not dentro_del_boton, (
        f"linea(s) {dentro_del_boton}: el resultado se pinta dentro del "
        "'if st.button', asi que desaparecera en la siguiente interaccion."
    )
