"""Pruebas del sistema de diseño.

Dos de estas pruebas vienen de fallos reales que ya ocurrieron.

La del sangrado: Streamlit pasa el texto por un intérprete de Markdown antes de
tratarlo como HTML, y Markdown convierte en bloque de código cualquier línea
con cuatro espacios delante. El HTML bien indentado salía escrito en crudo.

La de los iconos: los iconos de Streamlit son ligaduras de una fuente propia.
Al aplicar la tipografía del texto a todo, la ligadura dejaba de resolverse y
en el botón de subir fichero aparecía "uploadUpload" escrito.

Los dos son fallos silenciosos: no lanzan ninguna excepción, la página sale
fea. Sin pruebas que los vigilen, vuelven a la primera que alguien retoque una
plantilla.
"""

from __future__ import annotations

import re

import pytest

from kalman.web import theme

PALETAS = {"oscura": theme.DARK, "clara": theme.LIGHT}


# --------------------------------------------------------------------- logo

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


def test_el_logo_hereda_el_color_del_texto() -> None:
    """Asi funciona igual sobre negro que sobre blanco.

    Un logotipo con el fondo quemado obliga a mantener dos ficheros y uno de
    los dos siempre acaba desactualizado.
    """
    svg = theme.logo()
    assert "currentColor" in svg
    assert not re.search(r'(stroke|fill)="#', svg)


# ------------------------------------------------------------------ aplanado

def test_one_line_aplana_de_verdad() -> None:
    plano = theme._one_line("""
        <div>
          <span>hola</span>
        </div>
    """)
    assert plano == "<div> <span>hola</span> </div>"
    assert "\n" not in plano


@pytest.mark.parametrize("nombre", ["brand", "hero", "verdict", "note", "plan_card"])
def test_todo_lo_que_pinta_html_pasa_por_one_line(nombre: str) -> None:
    """Cualquier ayudante que dibuje HTML debe aplanarlo antes."""
    import inspect

    fuente = inspect.getsource(getattr(theme, nombre))
    if "st.markdown" not in fuente:
        pytest.skip(f"{nombre} no dibuja HTML directamente.")
    assert "_one_line" in fuente or '<p class="kal-note">' in fuente, (
        f"{nombre} pasa HTML a st.markdown sin aplanarlo. Con sangrado, "
        f"Markdown lo trata como bloque de codigo y sale en crudo."
    )


# ------------------------------------------------------------------- colores

@pytest.mark.parametrize("etiqueta", list(PALETAS))
def test_ninguna_paleta_tiene_colores_malformados(etiqueta: str) -> None:
    """Un color mal escrito no rompe nada, solo se ignora, y eso es peor."""
    for nombre, valor in PALETAS[etiqueta].items():
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", valor), f"{etiqueta}: {nombre} = {valor}"


def test_las_dos_paletas_definen_las_mismas_claves() -> None:
    """Si a una le falta una clave, cambiar de modo revienta con KeyError."""
    assert set(theme.DARK) == set(theme.LIGHT)


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


@pytest.mark.parametrize("etiqueta", list(PALETAS))
@pytest.mark.parametrize(
    "clave", ["ink", "ink_soft", "muted", "accent", "ok", "bad", "warn"]
)
def test_contraste_suficiente_sobre_el_fondo(etiqueta: str, clave: str) -> None:
    """Nivel AA del W3C para texto normal: 4,5 a 1.

    Tus clientes van a leer esto en portatiles baratos con la pantalla mal
    calibrada. El contraste no es un detalle estetico.
    """
    paleta = PALETAS[etiqueta]
    ratio = _contraste(paleta[clave], paleta["bg"])
    assert ratio >= 4.5, f"{etiqueta}: {clave} tiene contraste {ratio:.2f}"


@pytest.mark.parametrize("etiqueta", list(PALETAS))
@pytest.mark.parametrize("clave", ["ok", "warn", "bad"])
def test_el_veredicto_se_lee_sobre_su_propio_fondo(etiqueta: str, clave: str) -> None:
    """El veredicto no va sobre el fondo de la pagina, va sobre su panel.

    Comprobar solo contra el fondo general deja pasar un verde que no se lee
    encima del verde palido de su propio recuadro.
    """
    paleta = PALETAS[etiqueta]
    ratio = _contraste(paleta[clave], paleta[f"{clave}_soft"])
    assert ratio >= 4.5, f"{etiqueta}: {clave} sobre su fondo da {ratio:.2f}"


@pytest.mark.parametrize("etiqueta", list(PALETAS))
def test_el_boton_principal_se_lee(etiqueta: str) -> None:
    """La accion principal es monocroma: el texto va sobre el acento."""
    paleta = PALETAS[etiqueta]
    ratio = _contraste(paleta["on_accent"], paleta["accent"])
    assert ratio >= 4.5, f"{etiqueta}: texto sobre el acento da {ratio:.2f}"


# ---------------------------------------------------------------------- css

@pytest.mark.parametrize("etiqueta", list(PALETAS))
def test_el_css_define_todas_las_variables_que_usa(etiqueta: str) -> None:
    """Una variable CSS sin definir se ignora y el elemento sale sin estilo."""
    css = theme._css(PALETAS[etiqueta])
    definidas = set(re.findall(r"(--kal-[a-z-]+):", css))
    usadas = set(re.findall(r"var\((--kal-[a-z-]+)\)", css))
    assert usadas <= definidas, f"sin definir: {sorted(usadas - definidas)}"


def test_los_iconos_conservan_su_fuente() -> None:
    """Regresion. Ver el docstring del modulo."""
    css = theme._css(theme.DARK)
    assert "Material Symbols" in css, "falta la excepcion para la fuente de iconos"
    assert '[class*="st-"]' not in css, (
        "ese selector alcanza tambien a los iconos y les rompe la ligadura"
    )


def test_los_botones_son_pildoras() -> None:
    """Es la senal visual mas reconocible de interfaz cuidada."""
    css = theme._css(theme.DARK)
    assert "--kal-pill: 9999px" in css
    assert "border-radius: var(--kal-pill)" in css


def test_los_titulos_no_van_en_negrita() -> None:
    """La negrita en pantallas modernas se lee como plantilla barata."""
    css = theme._css(theme.DARK)
    bloque = css.split("h1, h2, h3, h4 {")[1].split("}")[0]
    peso = re.search(r"font-weight:\s*(\d+)", bloque)
    assert peso and int(peso.group(1)) <= 600


def test_los_titulos_llevan_interletraje_negativo() -> None:
    """Es lo que hace que un titular parezca dibujado."""
    css = theme._css(theme.DARK)
    assert re.search(r"h1 \{\{?[^}]*letter-spacing:\s*-\.", css) or "letter-spacing: -.035em" in css


def test_la_fuente_tiene_alternativa_del_sistema() -> None:
    """Una pagina que espera a una fuente remota parpadea con conexion lenta."""
    assert "sans-serif" in theme.FONT_STACK
    assert theme.FONT_STACK.count(",") >= 3


def test_no_se_usa_la_tipografia_de_openai() -> None:
    """Su tipografia tiene licencia cerrada. Inspirarse no es copiar."""
    css = theme._css(theme.DARK)
    assert "OpenAI Sans" not in css
    assert "OpenAI" not in theme.FONT_STACK


def test_inject_styles_acepta_los_dos_modos() -> None:
    """La paleta clara existe para el dia que un cliente la pida."""
    assert theme._css(theme.LIGHT) != theme._css(theme.DARK)
    assert theme.PALETTE is theme.DARK
