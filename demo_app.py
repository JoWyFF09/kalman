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
from kalman.reporting.worklist import build_worklist, summary_line, to_excel
from kalman.sample import generate
from kalman.web.theme import brand, hero, inject_styles, note, verdict

#: Tope de filas de la demo. Sin él, la demo es un servicio gratuito ilimitado
#: y deja de ser una demo.
MAX_ROWS = 5_000

st.set_page_config(
    page_title="Kalman · Calidad de datos",
    page_icon="◐",
    layout="wide",
)

inject_styles()

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

brand("Calidad de datos para empresas españolas")

hero(
    title="Un dato mal escrito cuesta dinero. Kalman los encuentra.",
    lead=(
        "Comprueba NIF, CIF, NIE e IBAN con su dígito de control oficial, "
        "normaliza teléfonos y códigos postales y detecta clientes duplicados. "
        "Sin instalar nada y sin registro."
    ),
    eyebrow="Demo pública",
)

note(
    "Nada de lo que subas aquí se guarda. El fichero se procesa en memoria y "
    "se descarta al cerrar la página."
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
        verdict(
            "ok", "Válido",
            "Comprobado contra el dígito de control oficial. No es una estimación.",
            value=str(shown),
        )
    else:
        sugerencia = ""
        if result.normalized and str(result.normalized) != value.strip():
            sugerencia = f" ¿Querías decir {result.normalized}?"
        verdict("bad", "No válido", result.message + sugerencia)

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

    tabs = st.tabs(
        ["Lista de trabajo", "Resumen", "Filas correctas", "Cuarentena", "Duplicados"]
    )

    with tabs[0]:
        # Va la primera porque es lo que hace que alguien pague. El recuento
        # dice cuántos datos están mal; esta lista dice a quién hay que llamar.
        worklist = build_worklist(df, report, result.duplicates)
        if worklist.empty:
            st.success("No hay nada que arreglar en este fichero.")
        else:
            st.markdown(f"**{summary_line(worklist)}**")
            note(
                "Ordenada por urgencia. Cada línea dice a qué cliente llamar, "
                "qué campo está mal y qué preguntarle."
            )
            st.dataframe(worklist.head(500), width="stretch", hide_index=True)
            if len(worklist) > 500:
                st.caption(
                    f"Se muestran 500 de {len(worklist):,} líneas. "
                    "La descarga las incluye todas.".replace(",", ".")
                )
            st.download_button(
                "Descargar la lista en Excel",
                to_excel(worklist),
                file_name="kalman_lista_de_trabajo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

    with tabs[1]:
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

    with tabs[2]:
        st.dataframe(result.valid.head(500), width="stretch")
        st.download_button(
            "Descargar CSV depurado",
            result.valid.to_csv(index=False).encode("utf-8"),
            file_name="kalman_limpio.csv",
            mime="text/csv",
        )

    with tabs[3]:
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

    with tabs[4]:
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
    # Sin boton intermedio: al pulsar una descarga Streamlit reejecuta el
    # fichero entero, el boton de arriba devolveria False y la descarga
    # desapareceria justo despues de usarla.
    st.download_button(
        "Descargar el informe en PDF",
        build_report(report.as_dict(), "Informe de demostración"),
        file_name="kalman_auditoria_demo.pdf",
        mime="application/pdf",
        type="primary",
    )

st.divider()

col_a, col_b, col_c = st.columns(3)
with col_a:
    st.markdown("**Exacto, no probabilístico**")
    note(
        "Los identificadores fiscales y los IBAN llevan dígito de control. "
        "O cuadra o no cuadra, y Kalman te dice cuál falla y por qué."
    )
with col_b:
    st.markdown("**Sin configurar nada**")
    note(
        "Kalman reconoce tus columnas por su nombre y por su contenido. "
        "Las que no entiende las deja intactas."
    )
with col_c:
    st.markdown("**Auditable**")
    note(
        "El motor es de código abierto y cada hallazgo lleva su regla, su "
        "motivo y su nivel de confianza."
    )
