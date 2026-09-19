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

import hashlib
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
from kalman.api.ratelimit import RateLimiter, client_key  # noqa: E402
from kalman.db import Repository  # noqa: E402
from kalman.db.repository import RegistrationError  # noqa: E402
from kalman.legal import PRIVACY, TERMS  # noqa: E402
from kalman.notifications.email import (  # noqa: E402
    EmailError,
    EmailSettings,
    Sender,
    build_sender,
    email_verify_body,
    password_reset_body,
)
from kalman.reporting.pdf import CostAssumption, build_report  # noqa: E402
from kalman.security.passwords import MIN_PASSWORD_LENGTH, WeakPasswordError  # noqa: E402
from kalman.security.tokens import TOKEN_LIFETIME_MINUTES  # noqa: E402
from kalman.reporting.worklist import build_worklist, summary_line, to_excel  # noqa: E402
from kalman.web.theme import brand, hero, inject_styles, note, plan_card  # noqa: E402

st.set_page_config(
    page_title="Kalman · Calidad de datos",
    page_icon="◐",
    layout="wide",
)

inject_styles()


@st.cache_resource
def get_repository() -> Repository:
    return Repository(get_settings().database_url)


@st.cache_resource
def _remitente() -> Sender:
    """Remitente de correo, construido una vez por proceso.

    Elige solo entre la API y SMTP segun lo que este configurado.
    """
    s = get_settings()
    return build_sender(
        EmailSettings(
            sender=s.email_from,
            api_key=s.email_api_key,
            host=s.smtp_host, port=s.smtp_port,
            user=s.smtp_user, password=s.smtp_password,
        )
    )


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


#: Limitador de altas, contado por direccion. El ritmo lo fija el plan
#: "signup" de kalman.api.ratelimit.
_signup_limiter = RateLimiter()


def _visitante() -> str:
    """Identifica al visitante lo mejor que se puede desde Streamlit.

    Detras del proxy de Render la direccion real viene en X-Forwarded-For.
    Si no hubiera nada se cae a una etiqueta comun, que es conservador: en el
    peor caso limita de mas, nunca de menos.
    """
    try:
        cabeceras = st.context.headers or {}
        reenviada = cabeceras.get("X-Forwarded-For") or cabeceras.get("x-forwarded-for")
        return client_key(reenviada, st.context.ip_address)
    except Exception:
        return "desconocido"


# ------------------------------------------------------------------ sesión

@st.dialog("Condiciones de uso", width="large")
def _dialogo_condiciones() -> None:
    st.markdown(TERMS)


@st.dialog("Política de privacidad", width="large")
def _dialogo_privacidad() -> None:
    st.markdown(PRIVACY)


def login_screen() -> None:
    """Pantalla de entrada: acceso, alta y recuperación de contraseña."""
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        brand("Señal, no ruido, en los datos de tu empresa")

        if st.session_state.get("modo_auth") == "recuperar":
            _formulario_recuperar()
            return

        entrar, registrarse = st.tabs(["Entrar", "Crear cuenta"])
        with entrar:
            _formulario_acceso()
        with registrarse:
            _formulario_alta()

        _pie_legal()


def _pie_legal() -> None:
    """Enlaces a los textos legales. Visibles antes de crear ninguna cuenta."""
    st.divider()
    izquierda, derecha = st.columns(2)
    if izquierda.button("Condiciones de uso", width="stretch", key="ver_condiciones"):
        _dialogo_condiciones()
    if derecha.button("Política de privacidad", width="stretch", key="ver_privacidad"):
        _dialogo_privacidad()


def _formulario_acceso() -> None:
    """Acceso de un cliente que ya tiene cuenta.

    El mensaje de error es siempre el mismo, exista el usuario o no. Decir
    "usuario no encontrado" le confirma a un atacante qué correos están dados
    de alta, que es la mitad del trabajo.
    """
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", width="stretch", type="primary")

    if st.button("He olvidado mi contraseña", key="ir_recuperar"):
        st.session_state.modo_auth = "recuperar"
        st.rerun()

    if not submitted:
        return

    user = get_repository().authenticate(email, password)
    if user is None:
        st.error("Credenciales incorrectas.")
        return

    _iniciar_sesion(user, "auth.login")


def _formulario_alta() -> None:
    """Alta de una empresa nueva, sin que nadie tenga que intervenir."""
    with st.form("signup"):
        org_name = st.text_input("Nombre de tu empresa", placeholder="Asesoría Gómez S.L.")
        email = st.text_input("Tu email de trabajo", key="alta_email")
        password = st.text_input(
            "Contraseña", type="password", key="alta_password",
            help=f"Mínimo {MIN_PASSWORD_LENGTH} caracteres. "
                 "Una frase larga es más segura y más fácil de recordar.",
        )
        repetida = st.text_input("Repite la contraseña", type="password")
        acepta = st.checkbox(
            "He leído y acepto las condiciones de uso y la política de privacidad."
        )
        submitted = st.form_submit_button(
            "Crear cuenta gratis", width="stretch", type="primary"
        )

    note(
        f"El plan gratuito incluye {PLANS['free'].monthly_rows:,} filas al mes "
        "y no pide tarjeta. Nada de lo que subas se guarda: el fichero se "
        "procesa en memoria y se descarta.".replace(",", ".")
    )

    if not submitted:
        return

    # La aceptación se comprueba aquí y se guarda con la hora en la base de
    # datos. Sin constancia de cuándo aceptó qué versión, el consentimiento no
    # se puede demostrar.
    if not acepta:
        st.error("Tienes que aceptar las condiciones para crear la cuenta.")
        return
    if password != repetida:
        st.error("Las dos contraseñas no coinciden.")
        return

    permitido = _signup_limiter.check(f"alta:{_visitante()}", "signup")
    if not permitido.allowed:
        st.error(
            "Demasiados intentos de registro desde esta conexión. "
            f"Espera {permitido.retry_after} segundos."
        )
        return

    try:
        user = get_repository().register_organization(org_name, email, password)
    except (WeakPasswordError, RegistrationError) as exc:
        st.error(str(exc))
        return
    except Exception:
        # No se enseña el error crudo: puede llevar dentro la cadena de
        # conexión a la base de datos.
        st.error("No se ha podido crear la cuenta. Inténtalo de nuevo en un minuto.")
        raise

    _enviar_verificacion(user, silencioso=True)
    st.success(f"Cuenta creada para {user['org_name']}. Entrando...")
    _iniciar_sesion(user, "auth.signup")


def _formulario_recuperar() -> None:
    """Pide el correo y manda un enlace para elegir una contraseña nueva."""
    st.markdown("#### Recuperar contraseña")
    ajustes = get_settings()

    if not ajustes.email_configured:
        st.warning(
            "El envío de correo no está configurado en este despliegue, así que "
            "no se puede recuperar la contraseña automáticamente. Escribe a "
            f"{ajustes.support_email}."
        )
        if st.button("Volver", key="volver_sin_correo"):
            st.session_state.modo_auth = None
            st.rerun()
        return

    with st.form("recuperar"):
        email = st.text_input("El email con el que te registraste")
        enviado = st.form_submit_button(
            "Enviarme el enlace", width="stretch", type="primary"
        )

    if st.button("Volver al acceso", key="volver_acceso"):
        st.session_state.modo_auth = None
        st.rerun()

    if not enviado:
        return

    permitido = _signup_limiter.check(f"reset:{_visitante()}", "signup")
    if not permitido.allowed:
        st.error(f"Demasiadas peticiones. Espera {permitido.retry_after} segundos.")
        return

    # El mensaje final es el mismo exista la cuenta o no. Si cambiara, este
    # formulario se convertiría en una forma cómoda de averiguar qué correos
    # están dados de alta en el servicio.
    repositorio = get_repository()
    usuario = repositorio.find_user_by_email(email)

    if usuario is not None:
        try:
            testigo = repositorio.create_auth_token(str(usuario["id"]), "password_reset")
            enlace = f"{ajustes.app_url}/?reset={testigo}"
            _remitente().send(
                usuario["email"],
                "Recuperar tu contraseña de Kalman",
                password_reset_body(
                    usuario["org_name"], enlace,
                    TOKEN_LIFETIME_MINUTES["password_reset"],
                ),
            )
            repositorio.record_audit(
                str(usuario["org_id"]), "auth.password_reset_requested", {},
                actor_id=str(usuario["id"]),
            )
        except EmailError as exc:
            # Se enseña el motivo concreto: "no se ha podido enviar" hace
            # perder una tarde revisando contraseñas cuando el problema es que
            # el alojamiento cierra el puerto.
            st.error(str(exc))
            return

    st.success(
        "Si esa dirección tiene una cuenta, te hemos mandado un enlace. "
        "Caduca en una hora y sólo sirve una vez. Mira también en la carpeta "
        "de correo no deseado."
    )


def _pantalla_nueva_contrasena(testigo: str) -> None:
    """Se abre desde el enlace del correo. Fija una contraseña nueva."""
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        brand("Elige una contraseña nueva")

        usuario = st.session_state.get("reset_user")
        if usuario is None:
            usuario = get_repository().consume_auth_token(testigo, "password_reset")

        if usuario is None:
            st.error(
                "Este enlace ya no sirve. Puede que haya caducado, que ya lo "
                "hayas usado o que hayas pedido otro después."
            )
            if st.button("Pedir uno nuevo", type="primary"):
                st.query_params.clear()
                st.session_state.modo_auth = "recuperar"
                st.rerun()
            return

        # El testigo ya se ha canjeado, así que se guarda en la sesión: un
        # error escribiendo la contraseña no debe obligar a pedir otro correo.
        st.session_state.reset_user = usuario

        with st.form("nueva_contrasena"):
            st.caption(f"Cuenta: {usuario['email']}")
            nueva = st.text_input("Contraseña nueva", type="password")
            repetida = st.text_input("Repítela", type="password")
            guardar = st.form_submit_button("Guardar", width="stretch", type="primary")

        if not guardar:
            return
        if nueva != repetida:
            st.error("Las dos contraseñas no coinciden.")
            return

        try:
            get_repository().set_password(usuario["id"], nueva)
        except WeakPasswordError as exc:
            st.error(str(exc))
            return

        get_repository().record_audit(
            usuario["org_id"], "auth.password_reset_done", {}, actor_id=usuario["id"]
        )
        st.session_state.pop("reset_user", None)
        st.query_params.clear()
        _iniciar_sesion(usuario, "auth.login")


def _procesar_verificacion(testigo: str) -> bool:
    """Marca el correo como confirmado desde el enlace.

    Devuelve si ha funcionado, para que quien llame pueda enseñar la pantalla
    de acceso en lugar de dejar la página en blanco.
    """
    usuario = get_repository().consume_auth_token(testigo, "email_verify")
    st.query_params.clear()

    if usuario is None:
        st.error("Este enlace de confirmación ya no sirve. Pide otro desde tu cuenta.")
        return False

    get_repository().mark_email_verified(usuario["id"])
    get_repository().record_audit(
        usuario["org_id"], "auth.email_verified", {}, actor_id=usuario["id"]
    )
    _iniciar_sesion(usuario, "auth.login")
    return True


def _enviar_verificacion(user: dict, silencioso: bool = False) -> bool:
    """Manda el correo de confirmación. Devuelve si se ha enviado."""
    ajustes = get_settings()
    if not ajustes.email_configured:
        if not silencioso:
            st.warning("El envío de correo no está configurado en este despliegue.")
        return False

    try:
        testigo = get_repository().create_auth_token(user["id"], "email_verify")
        enlace = f"{ajustes.app_url}/?verify={testigo}"
        _remitente().send(
            user["email"],
            "Confirma tu dirección en Kalman",
            email_verify_body(
                user["org_name"], enlace,
                TOKEN_LIFETIME_MINUTES["email_verify"] // 60,
            ),
        )
        return True
    except EmailError as exc:
        if not silencioso:
            st.error(str(exc))
        return False


def _aviso_verificacion(user: dict) -> None:
    """Recuerda confirmar la dirección, sin bloquear el plan gratuito.

    Bloquear la entrada por un correo sin confirmar rompería el alta que acaba
    de funcionar. La verificación se exige donde de verdad importa, que es
    antes de contratar un plan de pago.
    """
    if not get_settings().email_configured:
        return
    if get_repository().is_email_verified(user["id"]):
        return

    izquierda, derecha = st.columns([4, 1])
    izquierda.info(
        f"Confirma tu dirección {user['email']}. Hace falta para contratar un "
        "plan de pago."
    )
    if derecha.button("Reenviar", width="stretch", key="reenviar_verificacion"):
        if _enviar_verificacion(user):
            st.success("Correo de confirmación reenviado.")


def _iniciar_sesion(user: dict, accion: str) -> None:
    """Guarda la sesión y recarga. Deja constancia en el registro de auditoría."""
    st.session_state.user = user
    st.session_state.modo_auth = None
    get_repository().record_audit(user["org_id"], accion, {}, actor_id=user["id"])
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
    """Catálogo de planes con enlace a la pasarela.

    Sin encabezado propio: se usa tanto en la página de planes, que ya lleva su
    titular, como dentro de un muro de pago, que ya lleva su aviso. Repetir la
    palabra "Planes" en ambos sitios queda redundante.
    """
    columns = st.columns(len(PLANS))

    for column, plan in zip(columns, PLANS.values()):
        # Growth es el plan que se quiere vender: es el primero con acceso a
        # la API, que es lo que convierte a un cliente en uno que no se va.
        destacado = plan.key == "growth"

        with column:
            plan_card(
                plan.name, plan.price_label, plan.summary, plan.features,
                featured=destacado,
            )
            st.write("")

            if plan.is_free:
                st.button("Incluido", key=f"free_{plan.key}", disabled=True, width="stretch")
                continue

            if st.button(
                f"Elegir {plan.name}",
                key=f"buy_{plan.key}",
                width="stretch",
                type="primary" if destacado else "secondary",
            ):
                # Aquí sí se exige la dirección confirmada. Es donde de verdad
                # importa: sin ella no se puede mandar una factura ni avisar de
                # un recibo devuelto, y la cuenta podría no ser de quien dice.
                if (
                    get_settings().email_configured
                    and not get_repository().is_email_verified(user["id"])
                ):
                    st.warning(
                        "Antes de contratar un plan, confirma tu dirección de "
                        "correo. Tienes el enlace en tu bandeja de entrada."
                    )
                    if st.button("Reenviar confirmación", key=f"reenv_{plan.key}"):
                        _enviar_verificacion(user)
                    continue
                try:
                    session = get_gateway().create_checkout(
                        user["org_id"], user["org_name"], user["email"], plan.key,
                        with_trial=(plan.key == "starter"),
                    )
                    st.link_button("Continuar al pago", session.url, width="stretch")
                except BillingError as exc:
                    st.error(str(exc))


# -------------------------------------------------------------------- limpieza

def _firma(raw: bytes, *opciones: object) -> str:
    """Identifica una entrada concreta: el fichero y las opciones elegidas.

    Sirve para dos cosas: saber si el resultado guardado sigue valiendo, y no
    rehacer un Excel de diez mil lineas porque el usuario ha escrito un numero
    en otra casilla.
    """
    return hashlib.sha256(raw + repr(opciones).encode("utf-8")).hexdigest()


def _memo(clave: str, firma: str, construir):
    """Devuelve lo ya construido si la firma no ha cambiado.

    Streamlit vuelve a ejecutar el fichero entero en CADA interaccion, y eso
    incluye pulsar un boton de descarga. Sin esto, bajarse el CSV reconstruye
    el Excel y el PDF por el camino, y escribir un decimal en el coste por
    incidencia los reconstruye otra vez.
    """
    guardado = st.session_state.get(clave)
    if guardado is not None and guardado[0] == firma:
        return guardado[1]
    valor = construir()
    st.session_state[clave] = (firma, valor)
    return valor


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

    firma = _firma(raw, apply_norm, find_dupes, pseudonymize)

    if st.button("Analizar", type="primary"):
        with st.spinner("Analizando..."):
            engine = (
                CleaningEngine(
                    Pseudonymizer(get_settings().pseudonym_key, user["org_id"])
                )
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
        # El fichero original se guarda junto al resultado porque la lista de
        # trabajo necesita el valor tal y como venia y el nombre del cliente.
        st.session_state.analisis = {"firma": firma, "resultado": result, "origen": df}

    guardado = st.session_state.get("analisis")
    if guardado is None:
        return

    # El analisis se guarda, y no se rehace, porque Streamlit reejecuta el
    # fichero entero en cada interaccion. Antes el resultado solo existia
    # durante la ejecucion del clic en Analizar, asi que al pulsar cualquier
    # descarga la pantalla se quedaba vacia. Rehacerlo sin mas tampoco vale:
    # record_job contaria el fichero dos veces y gastaria cuota del plan.
    if guardado["firma"] != firma:
        note(
            "Has cambiado el fichero o las opciones. Pulsa Analizar para ver "
            "el resultado nuevo."
        )
        return

    _render_result(user, guardado["resultado"], plan, guardado["origen"], firma)


def _render_result(
    user: dict, result, plan, source: pd.DataFrame, firma: str
) -> None:
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

    tabs = st.tabs(
        ["Lista de trabajo", "Resumen", "Datos válidos", "Cuarentena", "Duplicados"]
    )

    with tabs[0]:
        _worklist_tab(source, report, result.duplicates, firma)

    with tabs[1]:
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

    with tabs[2]:
        st.dataframe(result.valid, width="stretch")
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
            st.dataframe(result.quarantine, width="stretch")
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
                "Kalman propone los grupos y no fusiona nada. "
                "Unir dos clientes que no lo eran destruye información."
            )

    _pdf_section(user, report, plan, firma)


def _worklist_tab(
    source: pd.DataFrame, report, duplicates, firma: str
) -> None:
    """La lista de tareas. Es lo que el cliente abre el lunes por la mañana.

    Va la primera de todas las pestañas a propósito. El recuento por regla
    dice cuántos datos están mal; esta lista dice a quién hay que llamar, y es
    la diferencia entre un diagnóstico y una herramienta.
    """
    worklist = _memo(
        "worklist", firma, lambda: build_worklist(source, report, duplicates)
    )

    if worklist.empty:
        st.success("No hay nada que arreglar en este fichero.")
        return

    st.markdown(f"**{summary_line(worklist)}**")
    note(
        "Ordenada por urgencia. Arriba lo que está mal de forma demostrable, "
        "debajo lo que conviene revisar. Cada línea dice a quién llamar y qué "
        "preguntarle."
    )

    st.dataframe(worklist.head(1000), width="stretch", hide_index=True)
    if len(worklist) > 1000:
        st.caption(
            f"Se muestran 1.000 de {len(worklist):,} líneas. "
            "La descarga las incluye todas.".replace(",", ".")
        )

    col_excel, col_csv = st.columns(2)
    with col_excel:
        st.download_button(
            "Descargar en Excel",
            _memo("worklist_excel", firma, lambda: to_excel(worklist)),
            file_name="kalman_lista_de_trabajo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
    with col_csv:
        st.download_button(
            "Descargar en CSV",
            worklist.to_csv(index=False).encode("utf-8-sig"),
            file_name="kalman_lista_de_trabajo.csv",
            mime="text/csv",
            width="stretch",
        )


def _pdf_section(user: dict, report, plan, firma: str) -> None:
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
            "Coste por incidencia (€)", min_value=0.0, value=0.0, step=0.5,
            key="coste_incidencia",
        )
    with col2:
        origen = st.text_input(
            "Origen de esa cifra",
            placeholder="Ej.: comisión media por recibo devuelto en 2026",
            key="origen_coste",
        )

    cost = None
    if euros > 0:
        if not origen.strip():
            st.warning("Indica de dónde sale esa cifra para poder citarla.")
        else:
            cost = CostAssumption(euros_per_error=euros, source=origen.strip())

    # Sin boton intermedio a proposito. Antes habia uno de "Generar informe"
    # que revelaba el de descarga, pero al pulsar la descarga Streamlit
    # reejecutaba el fichero, el boton intermedio devolvia False y la descarga
    # desaparecia. El PDF se construye una vez y se rehace solo si cambia el
    # coste declarado.
    pdf_bytes = _memo(
        "informe_pdf",
        f"{firma}:{euros}:{origen.strip()}",
        lambda: build_report(report.as_dict(), user["org_name"], cost),
    )
    st.download_button(
        "Descargar PDF",
        pdf_bytes,
        file_name=f"kalman_auditoria_{user['org_slug']}.pdf",
        mime="application/pdf",
        type="primary",
    )


# ------------------------------------------------------------------ historial

def history_section(user: dict) -> None:
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
    # Los enlaces del correo llegan como parámetros de la dirección y se
    # atienden antes que nada: quien pincha uno no ha iniciado sesión todavía.
    params = st.query_params
    if params.get("reset"):
        _pantalla_nueva_contrasena(params["reset"])
        return
    if params.get("verify"):
        if not _procesar_verificacion(params["verify"]):
            login_screen()
        return

    user = current_user()
    if user is None:
        login_screen()
        return

    with st.sidebar:
        brand(user["org_name"], size=30)

    context = subscription_panel(user)

    st.sidebar.divider()
    page = st.sidebar.radio(
        "Secciones",
        ["Analizar", "Historial", "Planes"],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    if st.sidebar.button("Cerrar sesión", width="stretch"):
        st.session_state.clear()
        st.rerun()

    titulos = {
        "Analizar": (
            "Calidad de datos",
            "Sube un fichero de clientes y Kalman te dice qué está mal y por qué.",
        ),
        "Historial": (
            "Historial",
            "Cada ejecución con su recuento de incidencias. Sin datos de tus clientes.",
        ),
        "Planes": (
            "Planes",
            "El precio va por filas procesadas al mes. Puedes cambiar o cancelar cuando quieras.",
        ),
    }
    titulo, entradilla = titulos[page]
    hero(titulo, entradilla)
    _aviso_verificacion(user)

    if page == "Analizar":
        cleaning_section(user, context)
    elif page == "Historial":
        history_section(user)
    else:
        pricing_section(user)


if __name__ == "__main__":
    main()
