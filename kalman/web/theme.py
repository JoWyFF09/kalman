"""Sistema de diseño de Kalman.

Un solo fichero para las dos interfaces, la demo pública y la aplicación con
sesión. Si el estilo viviera duplicado en cada una, en dos semanas serían dos
productos distintos con el mismo nombre.

De dónde sale este diseño
-------------------------
Está inspirado en cómo resuelve OpenAI su web, después de medir la suya en
vivo. Lo que se ha tomado son principios, no adornos, y ninguno es propiedad
de nadie:

1. **Casi monocromo.** Un color de marca en cada botón hace que todo grite a
   la vez. Aquí la acción principal es blanco sobre negro. El color se reserva
   para el veredicto de un dato, que es lo único que de verdad debe gritar.
2. **Botones en píldora.** Radio completo. Es la señal más reconocible de
   interfaz cuidada y no cuesta nada.
3. **Peso medio, no negrita.** Los títulos van en 540 o 550, no en 700. La
   negrita se lee como plantilla barata.
4. **Interletraje negativo en los títulos**, y proporcional al tamaño. Es lo
   que hace que un titular parezca dibujado y no escrito con la fuente por
   defecto.
5. **Escala tipográfica contenida.** Su web usa 14 y 16 píxeles en casi todo.
   Un texto pequeño y seguro transmite más autoridad que uno grande.
6. **Superficies en vez de cajas.** Una línea de un píxel y un fondo apenas
   más claro, en lugar de bordes gruesos y sombras.

Lo que NO se ha copiado: su tipografía, que tiene licencia cerrada, su
logotipo, y la estructura literal de sus páginas. Kalman debe parecerse a un
producto cuidado, no a otro producto.

Cambiar la marca entera es cambiar `DARK` y `LIGHT`, no buscar colores
repartidos por el código.
"""

from __future__ import annotations

import streamlit as st

#: Paleta oscura. Es la que se despliega. Los contrastes se comprueban en las
#: pruebas: todo el texto cumple el nivel AA del W3C sobre su fondo.
DARK: dict[str, str] = {
    "bg": "#0A0A0A",
    "surface": "#151515",
    "surface_alt": "#1E1E1E",
    "border": "#282828",
    "border_strong": "#3A3A3A",
    "ink": "#FFFFFF",
    "ink_soft": "#E4E4E7",
    "muted": "#9A9AA5",
    "accent": "#FFFFFF",
    "on_accent": "#0A0A0A",
    "accent_soft": "#1E1E1E",
    "ok": "#4ADE80",
    "ok_soft": "#12251A",
    "warn": "#FBBF24",
    "warn_soft": "#2A2110",
    "bad": "#FB7185",
    "bad_soft": "#2B1418",
}

#: Paleta clara. No se despliega hoy, pero un cliente grande la pedirá algún
#: día y tenerla escrita cuesta veinte líneas ahora y una semana después.
LIGHT: dict[str, str] = {
    "bg": "#FFFFFF",
    "surface": "#F7F7F8",
    "surface_alt": "#EFEFF1",
    "border": "#E4E4E7",
    "border_strong": "#C9C9CF",
    "ink": "#0D0D0D",
    "ink_soft": "#3D3D46",
    "muted": "#63636E",
    "accent": "#0D0D0D",
    "on_accent": "#FFFFFF",
    "accent_soft": "#F0F0F2",
    "ok": "#047857",
    "ok_soft": "#ECFDF5",
    "warn": "#B45309",
    "warn_soft": "#FFFBEB",
    "bad": "#B42318",
    "bad_soft": "#FEF3F2",
}

#: Paleta activa. Se despliega la oscura.
PALETTE = DARK

#: Pila tipográfica. Inter es la alternativa abierta más cercana a lo que usan
#: las webs cuidadas de hoy. Nunca se deja sin alternativa del sistema: una
#: página que espera a una fuente remota parpadea en blanco con conexión lenta.
FONT_STACK = (
    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)

MONO_STACK = "'JetBrains Mono', 'SF Mono', Consolas, 'Liberation Mono', monospace"


def _one_line(html: str) -> str:
    """Devuelve el HTML sin saltos de línea ni sangrado.

    Es imprescindible, no cosmético. Streamlit pasa el texto por un intérprete
    de Markdown antes de tratarlo como HTML, y Markdown convierte en bloque de
    código cualquier línea con cuatro espacios de sangrado. Escribir el HTML
    bien indentado, que es lo legible, hace que se muestre en crudo en la
    página en lugar de renderizarse.
    """
    return " ".join(line.strip() for line in html.strip().splitlines())


def logo(size: int = 26) -> str:
    """Marca de Kalman como SVG en línea.

    Representa lo que hace el producto: una señal ruidosa que entra por la
    izquierda y sale limpia por la derecha.

    Se dibuja con `currentColor` y sin recuadro de fondo, de modo que hereda el
    color del texto y funciona igual sobre negro que sobre blanco. Un logotipo
    con el fondo quemado obliga a mantener dos ficheros, y uno de los dos
    siempre acaba desactualizado.
    """
    return _one_line(f"""
    <svg width="{size}" height="{size}" viewBox="0 0 32 32" fill="none"
         xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Kalman"
         style="display:block">
      <path d="M2 20 L5 11 L8 24 L11 6 L14 17"
            stroke="currentColor" stroke-width="1.9" stroke-linecap="round"
            stroke-linejoin="round" opacity="0.45"/>
      <path d="M14 17 L18 15 L28 15"
            stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <circle cx="28" cy="15" r="2.4" fill="currentColor"/>
    </svg>
    """)


def _css(palette: dict[str, str]) -> str:
    p = palette
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

      :root {{
        --kal-bg: {p['bg']};
        --kal-surface: {p['surface']};
        --kal-surface-alt: {p['surface_alt']};
        --kal-border: {p['border']};
        --kal-border-strong: {p['border_strong']};
        --kal-ink: {p['ink']};
        --kal-ink-soft: {p['ink_soft']};
        --kal-muted: {p['muted']};
        --kal-accent: {p['accent']};
        --kal-on-accent: {p['on_accent']};
        --kal-accent-soft: {p['accent_soft']};
        --kal-ok: {p['ok']};
        --kal-ok-soft: {p['ok_soft']};
        --kal-warn: {p['warn']};
        --kal-warn-soft: {p['warn_soft']};
        --kal-bad: {p['bad']};
        --kal-bad-soft: {p['bad_soft']};
        --kal-pill: 9999px;
        --kal-radius: 12px;
        --kal-radius-lg: 16px;
      }}

      html, body, [data-testid="stAppViewContainer"] {{
        font-family: {FONT_STACK};
        color: var(--kal-ink);
        background: var(--kal-bg);
        -webkit-font-smoothing: antialiased;
      }}

      /* Los iconos de Streamlit son ligaduras de una fuente propia: el
         elemento contiene literalmente la palabra "upload" y la fuente la
         dibuja como un icono. Si se le aplica la tipografia del texto, la
         ligadura no se resuelve y aparece "uploadUpload" escrito. */
      [data-testid="stIconMaterial"],
      [class*="material-symbols"],
      [class*="material-icons"],
      span.material-icons,
      span.material-icons-outlined {{
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
                     'Material Icons' !important;
        font-weight: normal !important;
        letter-spacing: normal !important;
      }}

      [data-testid="stHeader"] {{ background: transparent; }}
      #MainMenu, footer {{ visibility: hidden; }}

      .block-container {{
        padding-top: 2.4rem;
        padding-bottom: 5rem;
        max-width: 1080px;
      }}

      /* --------------------------------------------------- tipografia */

      h1, h2, h3, h4 {{
        color: var(--kal-ink);
        font-weight: 550;
        line-height: 1.18;
      }}
      /* El interletraje negativo escala con el tamano: un titular grande
         necesita mas correccion que un epigrafe pequeno. */
      h1 {{ font-size: 2.35rem; letter-spacing: -.035em; }}
      h2 {{ font-size: 1.3rem;  letter-spacing: -.021em; margin-top: .5rem; }}
      h3 {{ font-size: 1.02rem; letter-spacing: -.014em; }}
      h4 {{ font-size: .95rem;  letter-spacing: -.01em; }}

      p, li, .stMarkdown {{
        color: var(--kal-ink-soft);
        font-size: .93rem;
        line-height: 1.62;
        font-weight: 400;
      }}

      /* Las cifras nunca deben bailar al cambiar de digito. */
      [data-testid="stMetricValue"], code, .kal-num,
      [data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}

      code {{
        font-family: {MONO_STACK};
        background: var(--kal-surface-alt);
        color: var(--kal-ink);
        padding: .14em .45em;
        border-radius: 6px;
        font-size: .86em;
        border: 1px solid var(--kal-border);
      }}

      /* ------------------------------------------------------ cabecera */

      .kal-brand {{
        display: flex; align-items: center; gap: .6rem; margin-bottom: 1.5rem;
        color: var(--kal-ink);
      }}
      .kal-brand-name {{
        font-size: 1.05rem; font-weight: 600; letter-spacing: -.02em;
        line-height: 1.15;
      }}
      .kal-brand-tag {{
        font-size: .78rem; color: var(--kal-muted); font-weight: 400;
        letter-spacing: -.005em;
      }}

      .kal-hero {{ margin: 1.4rem 0 2rem; }}
      .kal-hero h1 {{ margin: 0 0 .75rem; max-width: 20ch; }}
      .kal-hero .lead {{
        font-size: 1.02rem; color: var(--kal-muted);
        max-width: 60ch; line-height: 1.6; margin: 0; font-weight: 400;
      }}

      .kal-eyebrow {{
        display: inline-flex; align-items: center;
        font-size: .74rem; font-weight: 500; letter-spacing: .01em;
        color: var(--kal-ink-soft);
        background: var(--kal-surface);
        border: 1px solid var(--kal-border);
        padding: .3rem .75rem; border-radius: var(--kal-pill);
        margin-bottom: 1.1rem;
      }}

      .kal-note {{
        font-size: .84rem; color: var(--kal-muted); line-height: 1.6;
        font-weight: 400;
      }}

      /* -------------------------------------------------------- botones */

      .stButton > button, .stDownloadButton > button, .stLinkButton > a,
      [data-testid^="stBaseButton"] {{
        border-radius: var(--kal-pill) !important;
        border: 1px solid var(--kal-border-strong);
        background: transparent;
        color: var(--kal-ink);
        font-weight: 500;
        font-size: .875rem;
        letter-spacing: -.006em;
        padding: .5rem 1.15rem;
        box-shadow: none;
        transition: background .13s ease, border-color .13s ease, opacity .13s ease;
      }}
      .stButton > button:hover, .stDownloadButton > button:hover,
      .stLinkButton > a:hover {{
        background: var(--kal-surface);
        border-color: var(--kal-ink);
        color: var(--kal-ink);
      }}

      /* La accion principal es monocroma: blanco sobre negro. Un color de
         marca en cada boton hace que todo grite a la vez. */
      .stButton > button[kind^="primary"],
      .stDownloadButton > button[kind^="primary"],
      .stLinkButton > a[kind^="primary"],
      [data-testid^="stBaseButton-primary"] {{
        background: var(--kal-accent) !important;
        border-color: var(--kal-accent) !important;
        color: var(--kal-on-accent) !important;
      }}
      .stButton > button[kind^="primary"]:hover,
      .stDownloadButton > button[kind^="primary"]:hover,
      .stLinkButton > a[kind^="primary"]:hover,
      [data-testid^="stBaseButton-primary"]:hover {{
        opacity: .88;
      }}
      .stButton > button:focus-visible,
      .stDownloadButton > button:focus-visible {{
        outline: 2px solid var(--kal-ink);
        outline-offset: 2px;
      }}
      .stButton > button:disabled {{ opacity: .38; }}

      /* Streamlit mete el texto del boton dentro de un <p> o un <div> propio.
         Sin esto, la regla generica de parrafo le pone color de texto normal y
         la etiqueta queda gris clara sobre el boton blanco. */
      .stButton > button p, .stButton > button div,
      .stDownloadButton > button p, .stDownloadButton > button div,
      .stLinkButton > a p, .stLinkButton > a div,
      [data-testid^="stBaseButton"] p, [data-testid^="stBaseButton"] div {{
        color: inherit !important;
        font-size: inherit !important;
        font-weight: inherit !important;
        letter-spacing: inherit !important;
      }}

      /* --------------------------------------------------------- campos */

      [data-baseweb="input"], [data-baseweb="select"] > div,
      .stTextArea textarea, [data-testid="stNumberInputContainer"] {{
        border-radius: var(--kal-radius) !important;
        border: 1px solid var(--kal-border) !important;
        background: var(--kal-surface) !important;
        color: var(--kal-ink) !important;
      }}
      [data-baseweb="input"]:focus-within,
      [data-baseweb="select"] > div:focus-within {{
        border-color: var(--kal-ink) !important;
        background: var(--kal-bg) !important;
      }}
      input, textarea {{ color: var(--kal-ink) !important; }}
      input::placeholder {{ color: var(--kal-muted) !important; }}

      label, [data-testid="stWidgetLabel"] p {{
        font-weight: 500 !important;
        color: var(--kal-ink) !important;
        font-size: .855rem !important;
        letter-spacing: -.005em;
      }}

      /* -------------------------------------------------------- metricas */

      [data-testid="stMetric"] {{
        background: var(--kal-surface);
        border: 1px solid var(--kal-border);
        border-radius: var(--kal-radius-lg);
        padding: 1.05rem 1.15rem;
      }}
      [data-testid="stMetricLabel"] p {{
        font-size: .78rem !important;
        font-weight: 400 !important;
        letter-spacing: -.004em;
        text-transform: none;
        color: var(--kal-muted) !important;
      }}
      [data-testid="stMetricValue"] {{
        font-size: 1.75rem;
        font-weight: 600;
        letter-spacing: -.035em;
        color: var(--kal-ink);
      }}

      /* ---------------------------------------------------------- fichas */

      .kal-card {{
        background: var(--kal-surface);
        border: 1px solid var(--kal-border);
        border-radius: var(--kal-radius-lg);
        padding: 1.5rem 1.5rem 1.6rem;
        height: 100%;
      }}
      .kal-card h3 {{ margin: 0 0 .35rem; font-size: .98rem; font-weight: 600; }}
      .kal-card .price {{
        font-size: 1.75rem; font-weight: 600; letter-spacing: -.038em;
        color: var(--kal-ink); margin: .15rem 0 .55rem; line-height: 1.1;
      }}
      .kal-card ul {{ margin: .85rem 0 0; padding-left: 0; list-style: none; }}
      .kal-card li {{
        font-size: .86rem; margin-bottom: .45rem; color: var(--kal-ink-soft);
        padding-left: 1.15rem; position: relative; line-height: 1.45;
      }}
      .kal-card li::before {{
        content: ""; position: absolute; left: 0; top: .52em;
        width: 5px; height: 5px; border-radius: 50%;
        background: var(--kal-muted);
      }}
      .kal-card.is-featured {{
        border-color: var(--kal-border-strong);
        background: var(--kal-surface-alt);
      }}

      /* -------------------------------------------------------- veredicto */

      .kal-verdict {{
        display: flex; align-items: flex-start; gap: .7rem;
        border-radius: var(--kal-radius); padding: .9rem 1.1rem;
        border: 1px solid; margin-top: .45rem;
      }}
      .kal-verdict .dot {{
        width: 7px; height: 7px; border-radius: 50%; margin-top: .48rem; flex: none;
      }}
      .kal-verdict .title {{
        font-weight: 600; font-size: .93rem; margin: 0; letter-spacing: -.008em;
      }}
      .kal-verdict .body {{
        font-size: .85rem; margin: .22rem 0 0; color: var(--kal-ink-soft);
        font-weight: 400; line-height: 1.5;
      }}
      .kal-verdict .value {{
        font-family: {MONO_STACK}; font-size: .88rem; opacity: .85;
        margin-left: .4rem;
      }}

      .kal-verdict.ok  {{ background: var(--kal-ok-soft);  border-color: var(--kal-ok);  color: var(--kal-ok); }}
      .kal-verdict.bad {{ background: var(--kal-bad-soft); border-color: var(--kal-bad); color: var(--kal-bad); }}
      .kal-verdict.warn{{ background: var(--kal-warn-soft);border-color: var(--kal-warn);color: var(--kal-warn); }}
      .kal-verdict.ok .dot   {{ background: var(--kal-ok); }}
      .kal-verdict.bad .dot  {{ background: var(--kal-bad); }}
      .kal-verdict.warn .dot {{ background: var(--kal-warn); }}

      /* ---------------------------------------------------------- pestanas */

      [data-baseweb="tab-list"] {{
        gap: .15rem; border-bottom: 1px solid var(--kal-border);
        background: transparent;
      }}
      [data-baseweb="tab"] {{
        font-weight: 400; color: var(--kal-muted);
        font-size: .885rem; padding: .6rem .95rem;
        letter-spacing: -.006em;
      }}
      [data-baseweb="tab"]:hover {{ color: var(--kal-ink-soft); }}
      [data-baseweb="tab"][aria-selected="true"] {{
        color: var(--kal-ink); font-weight: 500;
      }}
      [data-baseweb="tab-highlight"] {{ background: var(--kal-ink); height: 1.5px; }}
      [data-baseweb="tab-border"] {{ background: transparent; }}

      /* ---------------------------------------------------------- tablas */

      [data-testid="stDataFrame"] {{
        border: 1px solid var(--kal-border);
        border-radius: var(--kal-radius);
        overflow: hidden;
      }}

      /* --------------------------------------------------------- avisos */

      [data-testid="stAlert"] {{
        border-radius: var(--kal-radius);
        border: 1px solid var(--kal-border);
        background: var(--kal-surface);
      }}
      [data-testid="stAlert"] p {{ font-size: .88rem; }}

      /* ------------------------------------------------------- subida */

      [data-testid="stFileUploader"] section {{
        border: 1px dashed var(--kal-border-strong);
        border-radius: var(--kal-radius-lg);
        background: var(--kal-surface);
        padding: 1.1rem;
        transition: border-color .15s ease, background .15s ease;
      }}
      [data-testid="stFileUploader"] section:hover {{
        border-color: var(--kal-ink);
        background: var(--kal-surface-alt);
      }}
      [data-testid="stFileUploader"] small {{ color: var(--kal-muted); }}

      /* -------------------------------------------------------- lateral */

      [data-testid="stSidebar"] {{
        background: var(--kal-bg);
        border-right: 1px solid var(--kal-border);
      }}
      [data-testid="stSidebar"] .block-container {{ padding-top: 1.8rem; }}

      /* --------------------------------------------------------- barra */

      [data-testid="stProgress"] > div > div {{
        background: var(--kal-surface-alt);
        border-radius: var(--kal-pill);
      }}
      [data-testid="stProgress"] > div > div > div {{
        background: var(--kal-ink);
        border-radius: var(--kal-pill);
      }}

      /* -------------------------------------------------------- separador */

      hr, [data-testid="stDivider"] {{
        border-color: var(--kal-border) !important;
        margin: 2rem 0 !important;
      }}

      /* ---------------------------------------------------------- movil */

      @media (max-width: 640px) {{
        h1, .kal-hero h1 {{ font-size: 1.72rem; }}
        .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
        [data-testid="stMetricValue"] {{ font-size: 1.35rem; }}
        .kal-card {{ padding: 1.2rem; }}
      }}
    </style>
    """


def inject_styles(mode: str = "dark") -> None:
    """Aplica el sistema de diseño. Se llama una vez, tras set_page_config.

    `mode` acepta "dark" o "light". Se despliega la oscura; la clara existe
    para el día que un cliente la pida y no haya que rehacer nada.
    """
    st.markdown(_css(LIGHT if mode == "light" else DARK), unsafe_allow_html=True)


def brand(tagline: str = "Calidad de datos", size: int = 26) -> None:
    """Bloque de marca: logotipo, nombre y descriptor."""
    st.markdown(
        _one_line(f"""
        <div class="kal-brand">
          {logo(size)}
          <div>
            <div class="kal-brand-name">Kalman</div>
            <div class="kal-brand-tag">{tagline}</div>
          </div>
        </div>
        """),
        unsafe_allow_html=True,
    )


def hero(title: str, lead: str, eyebrow: str = "") -> None:
    """Titular principal de una página."""
    etiqueta = f'<span class="kal-eyebrow">{eyebrow}</span>' if eyebrow else ""
    st.markdown(
        _one_line(f"""
        <div class="kal-hero">
          {etiqueta}
          <h1>{title}</h1>
          <p class="lead">{lead}</p>
        </div>
        """),
        unsafe_allow_html=True,
    )


def verdict(kind: str, title: str, body: str = "", value: str = "") -> None:
    """Resultado de una comprobación: válido, sospechoso o inválido.

    `kind` es "ok", "warn" o "bad". Es lo único de la interfaz que lleva color
    saturado, porque es la única información que de verdad tiene que gritar.
    """
    trozo_valor = f'<span class="value">{value}</span>' if value else ""
    trozo_cuerpo = f'<p class="body">{body}</p>' if body else ""
    st.markdown(
        _one_line(f"""
        <div class="kal-verdict {kind}">
          <span class="dot"></span>
          <div>
            <p class="title">{title}{trozo_valor}</p>
            {trozo_cuerpo}
          </div>
        </div>
        """),
        unsafe_allow_html=True,
    )


def note(text: str) -> None:
    """Texto secundario, para condiciones y aclaraciones."""
    st.markdown(f'<p class="kal-note">{text}</p>', unsafe_allow_html=True)


def plan_card(
    name: str, price: str, summary: str, features: tuple[str, ...], featured: bool = False
) -> None:
    """Ficha de un plan del catálogo."""
    puntos = "".join(f"<li>{f}</li>" for f in features)
    clase = "kal-card is-featured" if featured else "kal-card"
    st.markdown(
        _one_line(f"""
        <div class="{clase}">
          <h3>{name}</h3>
          <div class="price">{price}</div>
          <p class="kal-note">{summary}</p>
          <ul>{puntos}</ul>
        </div>
        """),
        unsafe_allow_html=True,
    )
