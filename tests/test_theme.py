"""Pruebas del sistema de diseño.

La prueba central es la del sangrado. Streamlit pasa el texto por un intérprete
de Markdown antes de tratarlo como HTML, y Markdown convierte en bloque de
código cualquier línea con cuatro espacios delante. Escribir el HTML bien
indentado, que es lo natural, hacía que la marca apareciera en crudo en la
página en lugar de dibujarse.

Es un fallo silencioso: no lanza ninguna excepción, simplemente la página sale
fea. Sin una prueba que lo vigile, vuelve a la primera que alguien retoque una
plantilla.
"""

from __future__ import annotations

import re

import pytest

from kalman.web import theme


def test_el_logo_no_lleva_sangrado() -> None:
    svg = theme.logo()
    assert "\n" not in svg
    assert not re.search(r"^\s{4}", svg)
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")


def test_el_logo_respeta_el_tamano_pedido() -> None:
    assert 'width="52"' in theme.logo(52)
    assert 'height="52"' in theme.logo(52)


def test_el_logo_es_accesible() -> None:
    """Un icono sin texto alternativo no lo lee un lector de pantalla."""
    svg = theme.logo()
    assert 'role="img"' in svg
    assert "aria-label" in svg


def test_one_line_aplana_de_verdad() -> None:
    plano = theme._one_line("""
        <div>
          <span>hola</span>
        </div>
    """)
    assert plano == "<div> <span>hola</span> </div>"
    assert "\n" not in plano


@pytest.mark.parametrize(
    "nombre",
    ["brand", "hero", "verdict", "note", "plan_card"],
)
def test_todo_lo_que_pinta_html_pasa_por_one_line(nombre: str) -> None:
    """Cualquier ayudante que dibuje HTML debe aplanarlo antes.

    Se revisa el codigo fuente porque llamar a la funcion requiere una sesion
    de Streamlit, y lo que importa aqui es la regla, no el renderizado.
    """
    import inspect

    fuente = inspect.getsource(getattr(theme, nombre))
    if "st.markdown" not in fuente:
        pytest.skip(f"{nombre} no dibuja HTML directamente.")
    assert "_one_line" in fuente or '<p class="kal-note">' in fuente, (
        f"{nombre} pasa HTML a st.markdown sin aplanarlo. Con sangrado, "
        f"Markdown lo trata como bloque de codigo y sale en crudo."
    )


# ------------------------------------------------------------------- colores

def test_la_paleta_no_tiene_colores_malformados() -> None:
    """Un color mal escrito no rompe nada, solo se ignora, y eso es peor."""
    for nombre, valor in theme.PALETTE.items():
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", valor), f"{nombre} = {valor}"


def _luminancia(hexadecimal: str) -> float:
    """Luminancia relativa segun la formula del W3C."""
    canales = [int(hexadecimal[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    ajustados = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales
    ]
    return 0.2126 * ajustados[0] + 0.7152 * ajustados[1] + 0.0722 * ajustados[2]


def _contraste(uno: str, otro: str) -> float:
    a, b = _luminancia(uno), _luminancia(otro)
    claro, oscuro = max(a, b), min(a, b)
    return (claro + 0.05) / (oscuro + 0.05)


@pytest.mark.parametrize("clave", ["ink", "ink_soft", "muted", "accent", "ok", "bad", "warn"])
def test_contraste_suficiente_sobre_el_fondo(clave: str) -> None:
    """Nivel AA del W3C para texto normal: 4,5 a 1.

    Tus clientes van a leer esto en portatiles baratos con la pantalla mal
    calibrada. El contraste no es un detalle estetico.
    """
    ratio = _contraste(theme.PALETTE[clave], theme.PALETTE["bg"])
    assert ratio >= 4.5, f"{clave} tiene contraste {ratio:.2f} sobre el fondo"


def test_el_css_define_todas_las_variables_que_usa() -> None:
    """Una variable CSS sin definir se ignora y el elemento sale sin estilo."""
    css = theme._css()
    definidas = set(re.findall(r"(--kal-[a-z-]+):", css))
    usadas = set(re.findall(r"var\((--kal-[a-z-]+)\)", css))
    assert usadas <= definidas, f"sin definir: {sorted(usadas - definidas)}"


def test_la_fuente_tiene_alternativa_del_sistema() -> None:
    """Una pagina que espera a una fuente remota parpadea con conexion lenta."""
    assert "sans-serif" in theme.FONT_STACK
    assert theme.FONT_STACK.count(",") >= 3


def test_los_iconos_conservan_su_fuente() -> None:
    """Regresion.

    Los iconos de Streamlit son ligaduras: el elemento contiene la palabra
    "upload" y la fuente de iconos la dibuja como un simbolo. Al aplicar la
    tipografia del texto a todo, la ligadura dejaba de resolverse y en el boton
    de subir fichero aparecia "uploadUpload" escrito.
    """
    css = theme._css()
    assert "Material Symbols" in css, "falta la excepcion para la fuente de iconos"

    # La regla que lo rompio aplicaba la tipografia a cualquier clase que
    # empezara por "st-", que incluye los iconos.
    assert '[class*="st-"]' not in css, (
        "ese selector alcanza tambien a los iconos y les rompe la ligadura"
    )
