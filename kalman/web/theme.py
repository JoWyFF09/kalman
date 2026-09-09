"""Sistema de diseño de Kalman.

Un solo fichero para las dos interfaces, la demo pública y la aplicación con
sesión. Si el estilo viviera duplicado en cada una, en dos semanas serían dos
productos distintos con el mismo nombre.

Decisiones y por qué
--------------------
**Fondo claro.** El oscuro se lee como herramienta de programador. El comprador
de Kalman es una gestoría o una pyme, y ahí el fondo claro se lee como software
serio. Es una decisión de producto, no de gusto.

**Un solo color de acento.** Los productos que usan cinco colores de marca
parecen plantillas. Aquí el azul se reserva para lo accionable, y el verde, el
ámbar y el rojo sólo aparecen para decir válido, sospechoso o inválido, que es
justo el vocabulario del producto.

**Cifras en tipografía tabular.** Una columna de números que baila al cambiar
de dígito parece amateur y cuesta de leer. `font-variant-numeric: tabular-nums`
lo arregla y casi nadie lo pone.

Todo son variables CSS. Cambiar la marca es cambiar `PALETTE`, no buscar
colores repartidos por el código.
"""

from __future__ import annotations

import streamlit as st

#: Paleta. Contrastes comprobados sobre fondo blanco para cumplir el nivel AA
#: de accesibilidad en el texto principal.
PALETTE: dict[str, str] = {
    "bg": "#FFFFFF",
    "surface": "#F7F8FA",
    "surface_alt": "#EFF2F6",
    "border": "#E3E7ED",
    "border_strong": "#CBD3DD",
    "ink": "#0E1726",
    "ink_soft": "#3B4757",
    "muted": "#66738A",
    "accent": "#1D4ED8",
    "accent_dark": "#1739A8",
    "accent_soft": "#EEF3FF",
    "ok": "#047857",
    "ok_soft": "#ECFDF5",
    "warn": "#B45309",
    "warn_soft": "#FFFBEB",
    "bad": "#B42318",
    "bad_soft": "#FEF3F2",
}

#: Pila tipográfica. Inter si el navegador puede traerla, y si no, la fuente
#: del sistema. Nunca se deja sin alternativa: una página que espera a una
#: fuente remota parpadea en blanco con conexión lenta.
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


def logo(size: int = 34) -> str:
    """Marca de Kalman como SVG en línea.

    Representa lo que hace el producto: una señal ruidosa que entra por la
    izquierda y sale limpia por la derecha. Va en línea y no como fichero para
    que no dependa de ninguna descarga y se vea aunque falle la red.
    """
    return _one_line(f"""
    <svg width="{size}" height="{size}" viewBox="0 0 40 40" fill="none"
         xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Kalman">
      <rect width="40" height="40" rx="10" fill="{PALETTE['ink']}"/>
      <path d="M7 24 L10 16 L13 27 L16 12 L19 22"
            stroke="{PALETTE['muted']}" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" opacity="0.75"/>
      <path d="M19 22 L23 20 L33 20"
            stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round"/>
      <circle cx="33" cy="20" r="2.6" fill="{PALETTE['accent']}"/>
    </svg>
    """)


def _css() -> str:
    p = PALETTE
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

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
        --kal-accent-dark: {p['accent_dark']};
        --kal-accent-soft: {p['accent_soft']};
        --kal-ok: {p['ok']};
        --kal-warn: {p['warn']};
        --kal-bad: {p['bad']};
        --kal-radius: 10px;
        --kal-shadow: 0 1px 2px rgba(14,23,38,.06), 0 1px 3px rgba(14,23,38,.04);
        --kal-shadow-lift: 0 4px 12px rgba(14,23,38,.10);
      }}

      html, body, [data-testid="stAppViewContainer"] {{
        font-family: {FONT_STACK};
        color: var(--kal-ink);
      }}

      /* Los iconos de Streamlit son ligaduras de una fuente propia: el
         elemento contiene literalmente la palabra "upload" y la fuente la
         dibuja como un icono. Si se le aplica la tipografia del texto, la
         ligadura no se resuelve y en el boton de subir fichero aparece
         "uploadUpload" escrito. Por eso hay que devolverles su fuente. */
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

      [data-testid="stAppViewContainer"] {{ background: var(--kal-bg); }}
      [data-testid="stHeader"] {{ background: transparent; }}
      #MainMenu, footer {{ visibility: hidden; }}

      .block-container {{
        padding-top: 2.2rem;
        padding-bottom: 4rem;
        max-width: 1120px;
      }}

      /* --------------------------------------------------- tipografia */

      h1, h2, h3, h4 {{
        color: var(--kal-ink);
        font-weight: 650;
        letter-spacing: -.021em;
        line-height: 1.2;
      }}
      h1 {{ font-size: 2.1rem; }}
      h2 {{ font-size: 1.35rem; margin-top: .4rem; }}
      h3 {{ font-size: 1.08rem; }}

      p, li, label, .stMarkdown {{ color: var(--kal-ink-soft); line-height: 1.6; }}

      /* Las cifras nunca deben bailar al cambiar de digito. */
      [data-testid="stMetricValue"], code, .kal-num, [data-testid="stDataFrame"] {{
        font-variant-numeric: tabular-nums;
      }}

      code {{
        font-family: {MONO_STACK};
        background: var(--kal-surface-alt);
        color: var(--kal-ink);
        padding: .12em .4em;
        border-radius: 5px;
        font-size: .88em;
      }}

      /* ------------------------------------------------------ cabecera */

      .kal-brand {{
        display: flex; align-items: center; gap: .7rem; margin-bottom: 1.4rem;
      }}
      .kal-brand-name {{
        font-size: 1.22rem; font-weight: 680; letter-spacing: -.02em;
        color: var(--kal-ink);
      }}
      .kal-brand-tag {{
        font-size: .8rem; color: var(--kal-muted); margin-top: -2px;
      }}

      .kal-hero {{ margin: .4rem 0 1.6rem; }}
      .kal-hero h1 {{ font-size: 2.5rem; margin: 0 0 .5rem; }}
      .kal-hero .lead {{
        font-size: 1.06rem; color: var(--kal-ink-soft);
        max-width: 62ch; line-height: 1.55; margin: 0;
      }}

      .kal-eyebrow {{
        display: inline-block; font-size: .72rem; font-weight: 640;
        letter-spacing: .09em; text-transform: uppercase;
        color: var(--kal-accent); background: var(--kal-accent-soft);
        padding: .3rem .6rem; border-radius: 999px; margin-bottom: .9rem;
      }}

      .kal-note {{ font-size: .84rem; color: var(--kal-muted); line-height: 1.55; }}

      /* -------------------------------------------------------- botones */

      .stButton > button, .stDownloadButton > button, .stLinkButton > a {{
        border-radius: var(--kal-radius);
        border: 1px solid var(--kal-border-strong);
        background: var(--kal-bg);
        color: var(--kal-ink);
        font-weight: 560;
        padding: .52rem 1rem;
        transition: all .14s ease;
        box-shadow: var(--kal-shadow);
      }}
      .stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover {{
        border-color: var(--kal-accent);
        color: var(--kal-accent);
        box-shadow: var(--kal-shadow-lift);
        transform: translateY(-1px);
      }}
      /* El prefijo cubre tambien "primaryFormSubmit", que es el valor que pone
         Streamlit al boton de enviar de un formulario. Con la coincidencia
         exacta, ese boton se quedaba sin los estados de hover y de foco. */
      .stButton > button[kind^="primary"],
      .stLinkButton > a[kind^="primary"],
      [data-testid^="stBaseButton-primary"] {{
        background: var(--kal-accent);
        border-color: var(--kal-accent);
        color: #fff;
      }}
      .stButton > button[kind^="primary"]:hover,
      .stLinkButton > a[kind^="primary"]:hover,
      [data-testid^="stBaseButton-primary"]:hover {{
        background: var(--kal-accent-dark);
        border-color: var(--kal-accent-dark);
        color: #fff;
      }}
      .stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
        outline: 3px solid var(--kal-accent-soft);
        outline-offset: 1px;
      }}

      /* --------------------------------------------------------- campos */

      [data-baseweb="input"], [data-baseweb="select"] > div, .stTextArea textarea {{
        border-radius: var(--kal-radius) !important;
        border-color: var(--kal-border-strong) !important;
        background: var(--kal-bg) !important;
      }}
      [data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {{
        border-color: var(--kal-accent) !important;
        box-shadow: 0 0 0 3px var(--kal-accent-soft) !important;
      }}
      label, [data-testid="stWidgetLabel"] p {{
        font-weight: 560 !important; color: var(--kal-ink) !important;
        font-size: .88rem !important;
      }}

      /* -------------------------------------------------------- metricas */

      [data-testid="stMetric"] {{
        background: var(--kal-bg);
        border: 1px solid var(--kal-border);
        border-radius: var(--kal-radius);
        padding: 1rem 1.1rem;
        box-shadow: var(--kal-shadow);
      }}
      [data-testid="stMetricLabel"] p {{
        font-size: .74rem !important;
        font-weight: 620 !important;
        letter-spacing: .05em;
        text-transform: uppercase;
        color: var(--kal-muted) !important;
      }}
      [data-testid="stMetricValue"] {{
        font-size: 1.85rem;
        font-weight: 660;
        letter-spacing: -.02em;
        color: var(--kal-ink);
      }}

      /* ---------------------------------------------------------- fichas */

      .kal-card {{
        background: var(--kal-bg);
        border: 1px solid var(--kal-border);
        border-radius: 14px;
        padding: 1.4rem 1.5rem;
        box-shadow: var(--kal-shadow);
        height: 100%;
      }}
      .kal-card h3 {{ margin: 0 0 .2rem; font-size: 1.02rem; }}
      .kal-card .price {{
        font-size: 1.7rem; font-weight: 680; letter-spacing: -.025em;
        color: var(--kal-ink); margin: .1rem 0 .5rem;
      }}
      .kal-card ul {{ margin: .6rem 0 0; padding-left: 1.1rem; }}
      .kal-card li {{ font-size: .89rem; margin-bottom: .3rem; color: var(--kal-ink-soft); }}
      .kal-card.is-featured {{
        border-color: var(--kal-accent);
        box-shadow: 0 0 0 1px var(--kal-accent), var(--kal-shadow-lift);
      }}

      /* -------------------------------------------------------- veredicto */

      .kal-verdict {{
        display: flex; align-items: flex-start; gap: .75rem;
        border-radius: var(--kal-radius); padding: .95rem 1.1rem;
        border: 1px solid; margin-top: .3rem;
      }}
      .kal-verdict .dot {{
        width: 9px; height: 9px; border-radius: 50%; margin-top: .42rem; flex: none;
      }}
      .kal-verdict .title {{ font-weight: 640; font-size: .96rem; margin: 0; }}
      .kal-verdict .body {{ font-size: .88rem; margin: .18rem 0 0; opacity: .92; }}
      .kal-verdict .value {{ font-family: {MONO_STACK}; font-size: .92rem; }}

      .kal-verdict.ok  {{ background: {p['ok_soft']};  border-color: #A7E3C6; color: var(--kal-ok); }}
      .kal-verdict.bad {{ background: {p['bad_soft']}; border-color: #F3B5AE; color: var(--kal-bad); }}
      .kal-verdict.warn{{ background: {p['warn_soft']};border-color: #F1D08A; color: var(--kal-warn); }}
      .kal-verdict.ok .dot   {{ background: var(--kal-ok); }}
      .kal-verdict.bad .dot  {{ background: var(--kal-bad); }}
      .kal-verdict.warn .dot {{ background: var(--kal-warn); }}

      /* ---------------------------------------------------------- pestanas */

      [data-baseweb="tab-list"] {{
        gap: .3rem; border-bottom: 1px solid var(--kal-border);
      }}
      [data-baseweb="tab"] {{
        font-weight: 560; color: var(--kal-muted);
        padding: .55rem .9rem;
      }}
      [data-baseweb="tab"][aria-selected="true"] {{ color: var(--kal-accent); }}
      [data-baseweb="tab-highlight"] {{ background: var(--kal-accent); height: 2px; }}

      /* ---------------------------------------------------------- tablas */

      [data-testid="stDataFrame"] {{
        border: 1px solid var(--kal-border);
        border-radius: var(--kal-radius);
        overflow: hidden;
      }}

      /* --------------------------------------------------------- avisos */

      [data-testid="stAlert"] {{
        border-radius: var(--kal-radius);
        border-left-width: 3px;
      }}

      /* ------------------------------------------------------- subida */

      [data-testid="stFileUploader"] section {{
        border: 1.5px dashed var(--kal-border-strong);
        border-radius: 12px;
        background: var(--kal-surface);
        transition: all .15s ease;
      }}
      [data-testid="stFileUploader"] section:hover {{
        border-color: var(--kal-accent);
        background: var(--kal-accent-soft);
      }}

      /* -------------------------------------------------------- lateral */

      [data-testid="stSidebar"] {{
        background: var(--kal-surface);
        border-right: 1px solid var(--kal-border);
      }}
      [data-testid="stSidebar"] .block-container {{ padding-top: 1.6rem; }}
      [data-testid="stSidebarUserContent"] hr {{ border-color: var(--kal-border); }}

      /* -------------------------------------------------------- separador */

      hr, [data-testid="stDivider"] {{ border-color: var(--kal-border) !important; }}

      /* ---------------------------------------------------------- movil */

      @media (max-width: 640px) {{
        .kal-hero h1 {{ font-size: 1.8rem; }}
        .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
        [data-testid="stMetricValue"] {{ font-size: 1.45rem; }}
      }}
    </style>
    """


def inject_styles() -> None:
    """Aplica el sistema de diseño. Se llama una vez, tras set_page_config."""
    st.markdown(_css(), unsafe_allow_html=True)


def brand(tagline: str = "Calidad de datos", size: int = 34) -> None:
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

    `kind` es "ok", "warn" o "bad". Es el elemento que más se ve del producto,
    así que tiene forma propia en lugar de un `st.success` genérico.
    """
    trozo_valor = f'<span class="value">{value}</span>' if value else ""
    trozo_cuerpo = f'<p class="body">{body}</p>' if body else ""
    st.markdown(
        _one_line(f"""
        <div class="kal-verdict {kind}">
          <span class="dot"></span>
          <div>
            <p class="title">{title} {trozo_valor}</p>
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
