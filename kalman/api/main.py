"""API HTTP de Kalman.

Por qué existe una API y no sólo una pantalla
---------------------------------------------
Una web donde alguien sube un CSV a mano es una herramienta que se usa cuando
uno se acuerda. Una API se mete dentro del proceso del cliente y se ejecuta
sola cada vez que entra un pedido. Lo segundo no se cancela, porque cancelarlo
rompe algo. Es la diferencia entre un producto que se abandona en tres meses y
uno que se queda.

Además es lo que hace posible vender por volumen en vez de por asiento, que es
lo que permite crecer sin contratar a nadie.
"""

from __future__ import annotations

import io
import logging
from typing import Annotated, Any

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..billing.plans import can_process, get_plan
from ..billing.webhooks import WebhookError, handle_event, verify_signature
from ..config import ConfigError, get_settings
from ..core.engine import CleaningEngine, CleanOptions
from ..core.pseudonymize import Pseudonymizer
from ..db import Repository
from ..security.passwords import hash_api_key

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Kalman API",
    version="2.0.0",
    description=(
        "Validación y limpieza de datos de clientes españoles. "
        "Verifica NIF, CIF, NIE e IBAN con su dígito de control oficial, "
        "normaliza contacto y detecta duplicados."
    ),
    docs_url="/docs",
)

_repository: Repository | None = None


def get_repository() -> Repository:
    """Pool compartido, creado en la primera petición."""
    global _repository
    if _repository is None:
        _repository = Repository(get_settings().database_url)
    return _repository


# --------------------------------------------------------------------- modelos

class CleanRequest(BaseModel):
    """Petición de limpieza con los registros en el cuerpo."""

    records: list[dict[str, Any]] = Field(
        ..., max_length=100_000,
        description="Filas a validar. Las columnas se reconocen solas.",
    )
    apply_normalizations: bool = True
    detect_duplicates: bool = True
    pseudonymize: bool = False
    column_overrides: dict[str, str] = Field(default_factory=dict)


class CleanResponse(BaseModel):
    report: dict[str, Any]
    valid: list[dict[str, Any]]
    quarantine: list[dict[str, Any]]
    duplicates: list[dict[str, Any]]


class ValidateRequest(BaseModel):
    """Validación de un valor suelto. Es el punto de entrada más barato.

    Un cliente lo prueba desde la documentación en diez segundos sin
    registrarse, y ese es el momento en que decide si el producto sirve.
    """

    kind: str = Field(..., pattern="^(tax_id|iban|email|phone|postal_code)$")
    value: str


# ------------------------------------------------------------- autenticación

async def require_org(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Resuelve la clave de API a una organización.

    Se acepta únicamente la cabecera Authorization. Nunca por parámetro en la
    URL: las URL acaban en los registros del servidor, en el historial del
    navegador y en la cabecera Referer de terceros.

    El formato de la cabecera se comprueba antes de tocar la base de datos, y
    el pool se pide dentro de la función y no como dependencia declarada. Si se
    declarase, FastAPI lo resolvería antes de ejecutar esta comprobación y una
    petición sin credenciales acabaría en un error de servidor en lugar de en
    un 401. Además, así el tráfico anónimo no consume conexiones.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Falta la cabecera Authorization con la clave de API.")

    raw_key = authorization.split(" ", 1)[1].strip()
    if not raw_key:
        raise HTTPException(401, "Clave de API vacía.")

    repository = get_repository()
    org = repository.authenticate_api_key(raw_key)
    if org is None:
        raise HTTPException(401, "Clave de API inválida o revocada.")

    subscription = repository.get_subscription(org["org_id"])
    plan = get_plan(subscription.get("plan"))
    if not plan.api_access:
        raise HTTPException(
            403,
            f"El plan {plan.name} no incluye acceso a la API. "
            f"Se requiere Growth o superior.",
        )

    return {**org, "plan": plan.key, "status": subscription.get("status")}


def _engine_for(org_id: str, pseudonymize: bool) -> CleaningEngine:
    if not pseudonymize:
        return CleaningEngine()
    settings = get_settings()
    return CleaningEngine(Pseudonymizer(settings.pseudonym_key, org_id))


# ------------------------------------------------------------------ endpoints

@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Sonda de vida. No toca la base de datos a propósito.

    Una sonda que consulta la base tumba el servicio entero cuando la base
    tiene un hipo, en vez de dejarlo servir lo que sí puede.
    """
    return {"status": "ok", "engine": CleaningEngine.version}


@app.post("/v1/validate", tags=["validación"])
async def validate_single(payload: ValidateRequest) -> dict[str, Any]:
    """Valida un único valor. Abierto, sin autenticación y con límite de tamaño.

    Es deliberadamente gratis: es la demostración del producto.
    """
    from ..core.validators.contact import (
        validate_email, validate_phone_es, validate_postal_code_es,
    )
    from ..core.validators.iban import validate_iban
    from ..core.validators.identity import validate_tax_id

    validators = {
        "tax_id": validate_tax_id,
        "iban": validate_iban,
        "email": validate_email,
        "phone": validate_phone_es,
        "postal_code": validate_postal_code_es,
    }

    if len(payload.value) > 200:
        raise HTTPException(422, "El valor es demasiado largo.")

    result = validators[payload.kind](payload.value)
    return {
        "valid": result.ok,
        "normalized": result.normalized,
        "rule": result.rule,
        "severity": str(result.severity),
        "message": result.message,
        "confidence": result.confidence,
    }


@app.post("/v1/clean", response_model=CleanResponse, tags=["limpieza"])
async def clean(
    payload: CleanRequest,
    org: Annotated[dict[str, Any], Depends(require_org)],
) -> CleanResponse:
    """Limpia un lote de registros."""
    if not payload.records:
        raise HTTPException(422, "No se ha enviado ningún registro.")

    repository = get_repository()
    used = repository.get_usage(org["org_id"])
    allowed, reason = can_process(org["plan"], used, len(payload.records))
    if not allowed:
        raise HTTPException(429, reason)

    df = pd.DataFrame(payload.records)
    engine = _engine_for(org["org_id"], payload.pseudonymize)
    result = engine.run(
        df,
        CleanOptions(
            apply_normalizations=payload.apply_normalizations,
            detect_duplicates=payload.detect_duplicates,
            pseudonymize=payload.pseudonymize,
            column_overrides=payload.column_overrides,
        ),
    )

    report = result.report.as_dict()
    repository.record_job(org["org_id"], None, report, filename=None, source="api")

    return CleanResponse(
        report=report,
        valid=result.valid.where(pd.notna(result.valid), None).to_dict(orient="records"),
        quarantine=result.quarantine.where(
            pd.notna(result.quarantine), None
        ).to_dict(orient="records"),
        duplicates=[g.as_dict() for g in result.duplicates],
    )


@app.post("/v1/clean/file", tags=["limpieza"])
async def clean_file(
    org: Annotated[dict[str, Any], Depends(require_org)],
    file: Annotated[UploadFile, File()],
) -> StreamingResponse:
    """Limpia un CSV o un Excel y devuelve el CSV depurado."""
    settings = get_settings()
    raw = await file.read()
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"El fichero supera {settings.max_upload_mb} MB.")

    name = (file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(422, f"No se ha podido leer el fichero: {exc}") from exc

    repository = get_repository()
    used = repository.get_usage(org["org_id"])
    allowed, reason = can_process(org["plan"], used, len(df))
    if not allowed:
        raise HTTPException(429, reason)

    result = CleaningEngine().run(df)
    repository.record_job(
        org["org_id"], None, result.report.as_dict(), file.filename, source="api"
    )

    buffer = io.StringIO()
    result.valid.to_csv(buffer, index=False)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="kalman_limpio.csv"',
            "X-Kalman-Rows-In": str(result.report.rows_in),
            "X-Kalman-Rows-Valid": str(result.report.rows_valid),
            "X-Kalman-Rows-Quarantined": str(result.report.rows_quarantined),
        },
    )


@app.get("/v1/usage", tags=["cuenta"])
async def usage(
    org: Annotated[dict[str, Any], Depends(require_org)],
) -> dict[str, Any]:
    """Consumo del mes en curso."""
    plan = get_plan(org["plan"])
    used = get_repository().get_usage(org["org_id"])
    return {
        "plan": plan.key,
        "rows_used": used,
        "rows_included": plan.monthly_rows,
        "rows_remaining": max(0, plan.monthly_rows - used),
    }


@app.post("/v1/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
) -> JSONResponse:
    """Recibe los eventos de Stripe.

    Es el único camino por el que se concede o se retira el derecho de uso.
    Se responde 200 incluso ante un evento que no se sabe aplicar, porque un
    error aquí hace que Stripe reintente durante días y sature la cola. Lo que
    nunca se responde con 200 es una firma inválida.
    """
    try:
        settings = get_settings()
    except ConfigError as exc:
        # Sin secreto de webhook no se puede verificar nada. Se responde 503
        # para que Stripe reintente cuando el despliegue esté bien configurado,
        # en vez de dar por bueno un evento sin comprobar.
        logger.error("Webhook recibido con la configuración incompleta: %s", exc)
        raise HTTPException(503, "Servicio de facturación no configurado.") from exc

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    try:
        event = verify_signature(payload, signature, settings.stripe_webhook_secret)
    except WebhookError as exc:
        logger.warning("Webhook rechazado: %s", exc)
        raise HTTPException(400, str(exc)) from exc

    # El pool se pide aquí, después de verificar la firma. Un webhook falso no
    # debe llegar a consumir una conexión a la base de datos.
    try:
        result = handle_event(event, get_repository())
    except Exception:
        logger.exception("Fallo procesando el evento %s", event.get("id"))
        return JSONResponse({"received": True, "handled": False}, status_code=200)

    return JSONResponse(
        {"received": True, "handled": result.handled, "detail": result.detail},
        status_code=200,
    )
