"""Demo pública de Kalman.

Por qué es un fichero aparte y no un modo de la aplicación principal
--------------------------------------------------------------------
Esta demo no tiene registro, ni base de datos, ni pagos. Sólo importa
`kalman.core` y `kalman.reporting`. Se despliega gratis y se abre sin cuenta.

Podría haberse hecho como un "modo demo" dentro de `kalman/web/app.py`, y
habría sido peor. Mezclar en el mismo fichero el camino autenticado y el camino
público es la forma más fácil de que un día una condición mal puesta deje la
aplicación real accesible sin contraseña. Dos entradas separadas no pueden
fallar así.

Ejecutar en local:
    streamlit run demo_app.py
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from kalman.core.engine import CleaningEngine, CleanOptions
from kalman.core.validators.contact import (
    validate_email,
    validate_phone_es,
    validate_postal_code_es,
)
from kalman.core.validators.iban import format_iban, validate_iban
from kalman.core.validators.identity import validate_tax_id
from kalman.reporting.pdf import RULE_LABELS, build_report
from kalman.sample import generate

#: Tope de filas de la demo. Sin él, la demo es un servicio gratuito ilimitado
#: y deja de ser una demo.
MAX_ROWS = 5_000

st.set_page_config(
    page_title="Kalman · Calidad de datos",
    page_icon="◐",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.5rem; max-width: 1100px; }
      #MainMenu, footer { visibility: hidden; }
      .kal-hero h1 { font-size: 2.6rem; margin-bottom: .2rem; letter-spacing: -.02em; }
      .kal-hero p  { font-size: 1.05rem; opacity: .72; margin-top: 0; }
      .kal-ok   { color: #15803d; font-weight: 600; }
      .kal-bad  { color: #b91c1c; font-weight: 600; }
      .kal-note { font-size: .82rem; opacity: .62; }
    </style>
    """,
    unsafe_allow_html=True,
)

VALIDATORS = {
    "NIF, NIE o CIF": ("tax_id", validate_tax_id),
    "IBAN": ("iban", validate_iban),
    "Email": ("email", validate_email),
    "Teléfono": ("phone", validate_phone_es),
    "Código postal": ("postal_code", validate_postal_code_es),
}

EXAMPLES = {
    "tax_id": "B65410011",
    "iban": "ES91 2100 0418 4502 0005 1332",
    "email": "info@empresa.es",
    "phone": "600 12 34 56",
    "postal_code": "28001",
}


# ------------------------------------------------------------------ cabecera

st.markdown(
    """
    <div class="kal-hero">
      <h1>Kalman</h1>
      <p>Comprueba los datos de tus clientes antes de que te cuesten dinero.
         NIF, CIF, NIE e IBAN verificados con su dígito de control oficial.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<p class="kal-note">Demo pública. Nada de lo que subas aquí se guarda: '
    "el fichero se procesa en memoria y se descarta al cerrar la página.</p>",
    unsafe_allow_html=True,
)

st.divider()


# --------------------------------------------------- comprobación de un valor

st.subheader("Comprueba un dato suelto")
st.caption("Sin registro. Escribe un NIF, un CIF o un IBAN y pulsa Intro.")

col_kind, col_value = st.columns([1, 2])
with col_kind:
    label = st.selectbox("Tipo", list(VALIDATORS), label_visibility="collapsed")
kind, validator = VALIDATORS[label]
with col_value:
    value = st.text_input(
        "Valor",
        placeholder=f"Por ejemplo: {EXAMPLES[kind]}",
        label_visibility="collapsed",
    )

if value.strip():
    result = validator(value)
    if result.ok:
        shown = result.normalized or value
        if kind == "iban":
            shown = format_iban(str(shown))
        st.markdown(
            f'<span class="kal-ok">Válido</span> &nbsp; <code>{shown}</code>',
            unsafe_allow_html=True,
        )
        st.caption("Comprobado contra el dígito de control oficial, no estimado.")
    else:
        st.markdown('<span class="kal-bad">No válido</span>', unsafe_allow_html=True)
        st.write(result.message)
        if result.normalized and str(result.normalized) != value.strip():
            st.info(f"¿Querías decir **{result.normalized}**?")

st.divider()


# ------------------------------------------------------- análisis de fichero

st.subheader("Analiza tu fichero de clientes")

col_upload, col_demo = st.columns([2, 1])
with col_upload:
    uploaded = st.file_uploader(
        "CSV o Excel", type=["csv", "xlsx", "xls"], label_visibility="collapsed"
    )
with col_demo:
    use_example = st.button("Usar datos de ejemplo", width="stretch")

st.caption(
    "No hace falta configurar nada: Kalman reconoce las columnas por su nombre "
    f"y por su contenido. En esta demo el máximo son {MAX_ROWS:,} filas.".replace(",", ".")
)

if "df" not in st.session_state:
    st.session_state.df = None
    st.session_state.origen = ""

if use_example:
    st.session_state.df = generate(rows=1200, seed=7)
    st.session_state.origen = "datos de ejemplo"

if uploaded is not None:
    try:
        raw = uploaded.getvalue()
        if uploaded.name.lower().endswith((".xlsx", ".xls")):
            st.session_state.df = pd.read_excel(io.BytesIO(raw))
        else:
            st.session_state.df = pd.read_csv(io.BytesIO(raw))
        st.session_state.origen = uploaded.name
    except Exception as exc:
        st.error(f"No se ha podido leer el fichero: {exc}")
        st.session_state.df = None

df = st.session_state.df

if df is not None:
    if len(df) > MAX_ROWS:
        st.warning(
            f"El fichero tiene {len(df):,} filas. La demo analiza las primeras "
            f"{MAX_ROWS:,}.".replace(",", ".")
        )
        df = df.head(MAX_ROWS)

    with st.spinner("Analizando..."):
        result = CleaningEngine().run(df, CleanOptions(detect_duplicates=True))

    report = result.report

    st.markdown(f"### Resultado sobre {st.session_state.origen}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Filas analizadas", f"{report.rows_in:,}".replace(",", "."))
    c2.metric("Sin incidencias", f"{report.rows_valid:,}".replace(",", "."))
    c3.metric("En cuarentena", f"{report.rows_quarantined:,}".replace(",", "."))
    c4.metric("Grupos duplicados", f"{report.duplicate_groups:,}".replace(",", "."))

    st.caption(
        f"Analizado en {report.duration_ms} ms con el motor {report.engine_version}. "
        "Una fila en cuarentena tiene al menos un dato inválido de forma "
        "demostrable. No se ha borrado, se ha separado."
    )

    tabs = st.tabs(["Qué se ha encontrado", "Filas correctas", "Cuarentena", "Duplicados"])

    with tabs[0]:
        counts = report.counts_by_rule()
        if not counts:
            st.success("No se ha encontrado ninguna incidencia.")
        else:
            tabla = pd.DataFrame(
                [
                    {"Incidencia": RULE_LABELS.get(rule, rule), "Filas": count}
                    for rule, count in counts.items()
                ]
            )
            st.dataframe(tabla, width="stretch", hide_index=True)
            st.caption(
                "Cada incidencia lleva su regla y su motivo. Kalman nunca dice "
                "sólo que algo es raro."
            )

    with tabs[1]:
        st.dataframe(result.valid.head(500), width="stretch")
        st.download_button(
            "Descargar CSV depurado",
            result.valid.to_csv(index=False).encode("utf-8"),
            file_name="kalman_limpio.csv",
            mime="text/csv",
        )

    with tabs[2]:
        if result.quarantine.empty:
            st.info("No hay filas en cuarentena.")
        else:
            st.dataframe(result.quarantine.head(500), width="stretch")
            st.download_button(
                "Descargar cuarentena",
                result.quarantine.to_csv(index=False).encode("utf-8"),
                file_name="kalman_cuarentena.csv",
                mime="text/csv",
            )

    with tabs[3]:
        if not result.duplicates:
            st.info("No se han encontrado duplicados.")
        else:
            st.dataframe(
                pd.DataFrame([g.as_dict() for g in result.duplicates]),
                width="stretch", hide_index=True,
            )
            st.caption(
                "Kalman propone los grupos y no fusiona nada por su cuenta. "
                "Unir dos clientes que no lo eran destruye información."
            )

    st.divider()
    st.subheader("Informe de auditoría")
    st.caption(
        "Kalman no calcula cuánto dinero supone esto para tu empresa. "
        "El coste de un dato incorrecto depende de tu operativa y sólo lo "
        "conoces tú."
    )
    if st.button("Generar informe en PDF"):
        pdf_bytes = build_report(report.as_dict(), "Informe de demostración")
        st.download_button(
            "Descargar PDF", pdf_bytes,
            file_name="kalman_auditoria_demo.pdf", mime="application/pdf",
        )

st.divider()
st.markdown(
    '<p class="kal-note">Kalman comprueba NIF, NIE, CIF e IBAN con su dígito de '
    "control oficial, normaliza teléfonos y códigos postales, detecta valores "
    "imposibles y encuentra clientes duplicados. El motor es de código abierto "
    "y se puede auditar.</p>",
    unsafe_allow_html=True,
)
