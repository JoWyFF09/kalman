"""Interfaz web.

Este fichero es fino a propósito. Toda la lógica vive en `kalman.core`,
`kalman.billing` y `kalman.db`, que se prueban sin navegador. Aquí sólo hay
pantalla.

La versión anterior tenía mil líneas en un solo fichero con el motor de IA, el
SQL, el PDF, el correo, Stripe y la interfaz mezclados. Eso no se puede probar,
no se puede revisar y no se puede reutilizar desde la API.

Sobre los imports de este fichero
---------------------------------
Aquí se usan imports absolutos, `from kalman.x import y`, y no relativos,
`from ..x import y`, aunque el fichero viva dentro del paquete.

El motivo es que Streamlit no importa este fichero como módulo: lo ejecuta
como un script suelto. En esa situación Python no sabe a qué paquete pertenece
y cualquier import relativo falla con "attempted relative import with no known
parent package". Hay una prueba en tests/test_web_entrypoint.py que impide que
alguien los vuelva a poner relativos sin darse cuenta.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# Streamlit pone en sys.path la carpeta del script, que es kalman/web, no la
# raíz del proyecto. Sin esto, "import kalman" no encuentra nada.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from kalman.billing.plans import PLANS, can_process, get_plan  # noqa: E402
from kalman.billing.stripe_gateway import BillingError, StripeGateway  # noqa: E402
from kalman.billing.webhooks import entitlement_is_active  # noqa: E402
from kalman.config import get_settings  # noqa: E402
from kalman.core.engine import CleaningEngine, CleanOptions  # noqa: E402
from kalman.core.pseudonymize import Pseudonymizer  # noqa: E402
from kalman.db import Repository  # noqa: E402
from kalman.reporting.pdf import CostAssumption, build_report  # noqa: E402

st.set_page_config(
    page_title="Kalman · Calidad de datos",
    page_icon="◐",
    layout="wide",
)


@st.cache_resource
def get_repository() -> Repository:
    return Repository(get_settings().database_url)


@st.cache_resource
def get_gateway() -> StripeGateway:
    settings = get_settings()
    import os

    price_ids = {
        key: os.environ.get(f"STRIPE_PRICE_{key.upper()}", "")
        for key in PLANS
        if not PLANS[key].is_free
    }
    return StripeGateway(settings.stripe_secret_key, settings.app_url, price_ids)


# ------------------------------------------------------------------ sesión

def login_screen() -> None:
    """Pantalla de acceso.

    El mensaje de error es siempre el mismo, exista el usuario o no. Decir
    "usuario no encontrado" le confirma a un atacante qué correos están dados
    de alta, que es la mitad del trabajo.
    """
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        st.title("Kalman")
        st.caption("Señal, no ruido, en los datos de tu empresa.")

        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Entrar", width="stretch")

        if submitted:
            user = get_repository().authenticate(email, password)
            if user is None:
                st.error("Credenciales incorrectas.")
                return
            st.session_state.user = user
            get_repository().record_audit(
                user["org_id"], "auth.login", {}, actor_id=user["id"]
            )
            st.rerun()


def current_user() -> dict | None:
    return st.session_state.get("user")


# ---------------------------------------------------------------- facturación

def subscription_panel(user: dict) -> dict:
    """Muestra el plan y el consumo. Lee de la base, nunca de la sesión."""
    repository = get_repository()
    subscription = repository.get_subscription(user["org_id"])
    plan = get_plan(subscription.get("plan"))
    used = repository.get_usage(user["org_id"])

    st.sidebar.subheader("Tu plan")
    st.sidebar.metric(plan.name, plan.price_label)

    progress = min(1.0, used / plan.monthly_rows) if plan.monthly_rows else 0.0
    st.sidebar.progress(progress)
    st.sidebar.caption(
        f"{used:,} de {plan.monthly_rows:,} filas este mes".replace(",", ".")
    )

    if subscription.get("stripe_customer_id"):
        if st.sidebar.button("Facturación y facturas", width="stretch"):
            try:
                url = get_gateway().create_portal(subscription["stripe_customer_id"])
                st.sidebar.link_button("Abrir portal de Stripe", url, width="stretch")
            except BillingError as exc:
                st.sidebar.error(str(exc))

    return {"plan": plan, "subscription": subscription, "used": used}


def pricing_section(user: dict) -> None:
    """Catálogo de planes con enlace a la pasarela."""
    st.subheader("Planes")
    columns = st.columns(len(PLANS))

    for column, plan in zip(columns, PLANS.values()):
        with column:
            st.markdown(f"### {plan.name}")
            st.markdown(f"**{plan.price_label}**")
            st.caption(plan.summary)
            for feature in plan.features:
                st.markdown(f"- {feature}")

            if plan.is_free:
                st.button("Incluido", key=f"free_{plan.key}", disabled=True, width="stretch")
                continue

            if st.button(f"Elegir {plan.name}", key=f"buy_{plan.key}", width="stretch"):
                try:
                    session = get_gateway().create_checkout(
                        user["org_id"], user["org_name"], user["email"], plan.key,
                        with_trial=(plan.key == "starter"),
                    )
                    st.link_button("Continuar al pago", session.url, width="stretch")
                except BillingError as exc:
                    st.error(str(exc))


# -------------------------------------------------------------------- limpieza

def cleaning_section(user: dict, context: dict) -> None:
    """Pantalla principal: subir fichero, ver hallazgos, descargar."""
    plan = context["plan"]
    repository = get_repository()

    st.subheader("Analizar un fichero")
    uploaded = st.file_uploader(
        "Arrastra un CSV o un Excel",
        type=["csv", "xlsx", "xls"],
        help="Las columnas se reconocen solas. No hace falta configurar nada.",
    )

    with st.expander("Opciones"):
        col1, col2 = st.columns(2)
        with col1:
            apply_norm = st.checkbox(
                "Aplicar correcciones seguras", value=True,
                help="Normaliza teléfonos, capitalización y espacios. "
                     "Desactívalo para auditar sin tocar nada.",
            )
            find_dupes = st.checkbox("Buscar duplicados", value=True)
        with col2:
            pseudonymize = st.checkbox(
                "Seudonimizar la salida", value=False,
                help="Sustituye los datos personales por códigos estables "
                     "usando una clave que sólo conoce el servidor.",
            )

    if uploaded is None:
        return

    try:
        raw = uploaded.getvalue()
        if uploaded.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        st.error(f"No se ha podido leer el fichero: {exc}")
        return

    allowed, reason = can_process(plan.key, context["used"], len(df))
    if not allowed:
        st.warning(reason)
        pricing_section(user)
        return

    if not st.button("Analizar", type="primary"):
        return

    with st.spinner("Analizando..."):
        engine = (
            CleaningEngine(Pseudonymizer(get_settings().pseudonym_key, user["org_id"]))
            if pseudonymize
            else CleaningEngine()
        )
        result = engine.run(
            df,
            CleanOptions(
                apply_normalizations=apply_norm,
                detect_duplicates=find_dupes,
                pseudonymize=pseudonymize,
            ),
        )
        repository.record_job(
            user["org_id"], user["id"], result.report.as_dict(), uploaded.name
        )

    st.session_state.last_result = result
    _render_result(user, result, plan)


def _render_result(user: dict, result, plan) -> None:
    report = result.report

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Filas analizadas", f"{report.rows_in:,}".replace(",", "."))
    col2.metric("Sin incidencias", f"{report.rows_valid:,}".replace(",", "."))
    col3.metric("En cuarentena", f"{report.rows_quarantined:,}".replace(",", "."))
    col4.metric("Grupos duplicados", f"{report.duplicate_groups:,}".replace(",", "."))

    detected = ", ".join(f"`{k}` → {v}" for k, v in report.columns_detected.items())
    st.caption(f"Columnas reconocidas: {detected or 'ninguna'}")
    if report.unmapped_columns:
        st.caption(
            "Columnas conservadas sin analizar: " + ", ".join(report.unmapped_columns)
        )

    tabs = st.tabs(["Incidencias", "Datos válidos", "Cuarentena", "Duplicados"])

    with tabs[0]:
        counts = report.counts_by_rule()
        if not counts:
            st.success("No se ha encontrado ninguna incidencia.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [{"Regla": k, "Incidencias": v} for k, v in counts.items()]
                ),
                width="stretch", hide_index=True,
            )
            with st.expander("Ver detalle fila a fila"):
                st.dataframe(
                    pd.DataFrame([f.as_dict() for f in report.findings[:2000]]),
                    width="stretch", hide_index=True,
                )

    with tabs[1]:
        st.dataframe(result.valid, width="stretch")
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
            st.dataframe(result.quarantine, width="stretch")
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
                "Kalman propone los grupos y no fusiona nada. "
                "Unir dos clientes que no lo eran destruye información."
            )

    _pdf_section(user, report, plan)


def _pdf_section(user: dict, report, plan) -> None:
    """Descarga del informe. Sólo con plan de pago activo."""
    st.divider()
    st.subheader("Informe de auditoría")

    subscription = get_repository().get_subscription(user["org_id"])
    entitled = entitlement_is_active(
        subscription.get("status", "inactive"), subscription.get("plan", "free")
    )

    if not entitled:
        st.info("El informe en PDF está incluido a partir del plan Starter.")
        pricing_section(user)
        return

    st.caption(
        "Kalman no estima cuánto dinero supone esto para tu empresa. "
        "Si quieres una cifra en euros en el informe, aporta tu coste por "
        "incidencia y quedará constancia de que el dato es tuyo."
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        euros = st.number_input(
            "Coste por incidencia (€)", min_value=0.0, value=0.0, step=0.5
        )
    with col2:
        source = st.text_input(
            "Origen de esa cifra",
            placeholder="Ej.: comisión media por recibo devuelto en 2026",
        )

    cost = None
    if euros > 0:
        if not source.strip():
            st.warning("Indica de dónde sale esa cifra para poder citarla.")
        else:
            cost = CostAssumption(euros_per_error=euros, source=source.strip())

    if st.button("Generar informe"):
        pdf_bytes = build_report(report.as_dict(), user["org_name"], cost)
        st.download_button(
            "Descargar PDF",
            pdf_bytes,
            file_name=f"kalman_auditoria_{user['org_slug']}.pdf",
            mime="application/pdf",
        )


# ------------------------------------------------------------------ historial

def history_section(user: dict) -> None:
    st.subheader("Historial")
    jobs = get_repository().recent_jobs(user["org_id"])
    if not jobs:
        st.info("Todavía no has analizado ningún fichero.")
        return
    st.dataframe(pd.DataFrame(jobs), width="stretch", hide_index=True)
    st.caption(
        "Kalman guarda el recuento de incidencias de cada ejecución, no los "
        "datos de tus clientes. El fichero se procesa en memoria y se descarta."
    )


# ----------------------------------------------------------------------- main

def main() -> None:
    user = current_user()
    if user is None:
        login_screen()
        return

    st.sidebar.title("Kalman")
    st.sidebar.caption(user["org_name"])
    context = subscription_panel(user)

    st.sidebar.divider()
    if st.sidebar.button("Cerrar sesión", width="stretch"):
        st.session_state.clear()
        st.rerun()

    page = st.sidebar.radio("", ["Analizar", "Historial", "Planes"], label_visibility="collapsed")

    st.title("Calidad de datos")
    if page == "Analizar":
        cleaning_section(user, context)
    elif page == "Historial":
        history_section(user)
    else:
        pricing_section(user)


if __name__ == "__main__":
    main()
