"""Detección automática del esquema de entrada.

El motor anterior tenía esto:

    if empresa == "Agencia_X":
        df = df.rename(columns={"Presupuesto_Mensual": "Ingresos_Anuales", ...})
    elif empresa == "Ecommerce_Y":
        ...

Cada cliente nuevo exigía editar el código, hacer una revisión y desplegar.
Con cien clientes eso son cien ramas en una función y un despliegue por venta.
Es el motivo por el que el producto no podía escalar, y no tiene nada que ver
con la capacidad del servidor.

Aquí las columnas se reconocen solas por sinónimos y por el contenido. Un
cliente se da de alta y sube su fichero sin que nadie toque nada. Si aun así
quiere fijar el mapeo, lo hace por configuración, no por código.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import normalize_key

#: Campo canónico -> sinónimos habituales en español e inglés.
#: Se comparan normalizados, así que "Nº Cliente" y "numero cliente" coinciden.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "record_id": (
        "id", "id cliente", "id_cliente", "codigo", "codigo cliente", "cod cliente",
        "numero cliente", "num cliente", "referencia", "customer id", "client id",
    ),
    "name": (
        "nombre", "nombre completo", "nombre y apellidos", "cliente",
        "cliente nombre", "contacto", "titular", "name", "full name", "contact",
    ),
    "company": (
        "empresa", "razon social", "compania", "compañia", "sociedad", "negocio",
        "denominacion social", "company", "company name", "business",
    ),
    "tax_id": (
        "nif", "cif", "nie", "dni", "documento", "doc identidad", "identificacion",
        "nif cif", "cif nif", "tax id", "vat", "vat number",
    ),
    "email": (
        "email", "e mail", "correo", "correo electronico", "mail",
        "email contacto", "correo contacto", "direccion email",
    ),
    "phone": (
        "telefono", "tlf", "tfno", "movil", "movil contacto", "telefono contacto",
        "phone", "mobile", "telephone", "celular",
    ),
    "iban": (
        "iban", "cuenta", "cuenta bancaria", "ccc", "numero cuenta",
        "bank account", "account",
    ),
    "postal_code": (
        "cp", "codigo postal", "c postal", "postal", "zip", "zipcode", "postcode",
    ),
    "city": ("ciudad", "poblacion", "localidad", "municipio", "city", "town"),
    "province": ("provincia", "region", "state", "province"),
    "address": ("direccion", "domicilio", "calle", "address", "street"),
    "age": ("edad", "años", "anos", "age"),
    "income": (
        "ingresos", "ingresos anuales", "facturacion", "presupuesto",
        "presupuesto mensual", "importe", "revenue", "income", "budget", "amount",
    ),
    "date": ("fecha", "fecha alta", "fecha registro", "created", "date", "fecha nacimiento"),
}

#: Índice inverso, construido una sola vez al importar.
_LOOKUP: dict[str, str] = {
    normalize_key(synonym): canonical
    for canonical, synonyms in SYNONYMS.items()
    for synonym in synonyms
}

# Patrones de contenido, usados cuando el nombre de la columna no dice nada
# útil, cosa muy frecuente en exportaciones que traen "Campo1", "Campo2".
_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I), 0.6),
    ("iban", re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9\s]{10,30}$", re.I), 0.6),
    ("tax_id", re.compile(r"^(?:[A-Z]?\d{7,8}[A-Z]|[A-Z]\d{8})$", re.I), 0.6),
    ("phone", re.compile(r"^(?:\+?34)?[\s\-]?[6789]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}$"), 0.6),
    ("postal_code", re.compile(r"^\d{5}$"), 0.4),
)


#: Campos cuyo contenido es texto por naturaleza. Una columna íntegramente
#: numérica no puede ser el nombre de una persona ni una razón social.
_TEXT_FIELDS = frozenset({"name", "company", "email", "address", "city", "province"})

_NUMERIC_RE = re.compile(r"^-?\d+([.,]\d+)?$")


def _looks_numeric(value: object) -> bool:
    return bool(_NUMERIC_RE.match(str(value).strip()))


def _content_contradicts(canonical: str, values: list[object]) -> bool:
    """Rechaza una asignación que el contenido desmiente.

    Nace de un fallo real. La cabecera "Nº Cliente" contiene la palabra
    "cliente", que es sinónimo del campo nombre, así que esa columna se
    apropiaba del nombre y luego todas sus filas se marcaban como nombres
    falsos por contener dígitos. El fichero entero quedaba inservible.

    El nombre de una columna es una pista; su contenido es la prueba.
    """
    if canonical not in _TEXT_FIELDS:
        return False
    sample = [v for v in values if str(v).strip() not in ("", "nan", "None")]
    if len(sample) < 3:
        return False
    return sum(1 for v in sample if _looks_numeric(v)) / len(sample) >= 0.9


@dataclass(frozen=True, slots=True)
class ColumnMatch:
    """Una columna del fichero asignada a un campo canónico."""

    source: str
    canonical: str
    confidence: float
    method: str


def detect_schema(
    columns: list[str],
    samples: dict[str, list[object]] | None = None,
    overrides: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[ColumnMatch], list[str]]:
    """Asigna cada columna del fichero a un campo canónico.

    Devuelve el mapeo directo, el detalle de cada decisión para poder
    enseñárselo al usuario, y la lista de columnas que no se han reconocido.

    Las columnas no reconocidas no se descartan: se conservan intactas en la
    salida. Perder una columna del cliente porque el motor no la entiende sería
    imperdonable.
    """
    overrides = overrides or {}
    samples = samples or {}

    mapping: dict[str, str] = {}
    matches: list[ColumnMatch] = []
    taken: set[str] = set()

    # Prioridad 1: lo que el cliente haya fijado explícitamente.
    for source, canonical in overrides.items():
        if source in columns and canonical not in taken:
            mapping[source] = canonical
            taken.add(canonical)
            matches.append(ColumnMatch(source, canonical, 1.0, "override"))

    # Prioridad 2: nombre exacto tras normalizar.
    for source in columns:
        if source in mapping:
            continue
        canonical = _LOOKUP.get(normalize_key(source))
        if canonical and canonical not in taken:
            if _content_contradicts(canonical, samples.get(source, [])):
                continue
            mapping[source] = canonical
            taken.add(canonical)
            matches.append(ColumnMatch(source, canonical, 0.95, "name"))

    # Prioridad 3: el nombre contiene un sinónimo, por ejemplo
    # "Email de contacto principal". Se prueban los sinónimos más largos
    # primero: "razon social" debe ganar a "social" si ambos encajasen.
    ordered_synonyms = sorted(_LOOKUP.items(), key=lambda kv: -len(kv[0]))
    for source in columns:
        if source in mapping:
            continue
        key = normalize_key(source)
        for synonym, canonical in ordered_synonyms:
            if canonical in taken or len(synonym) < 4:
                continue
            if not re.search(rf"\b{re.escape(synonym)}\b", key):
                continue
            if _content_contradicts(canonical, samples.get(source, [])):
                continue
            mapping[source] = canonical
            taken.add(canonical)
            matches.append(ColumnMatch(source, canonical, 0.75, "name_contains"))
            break

    # Prioridad 4: el contenido delata el campo.
    for source in columns:
        if source in mapping:
            continue
        values = [v for v in samples.get(source, []) if v not in (None, "")][:50]
        if not values:
            continue
        for canonical, pattern, base_confidence in _CONTENT_PATTERNS:
            if canonical in taken:
                continue
            hits = sum(1 for v in values if pattern.match(str(v).strip()))
            ratio = hits / len(values)
            if ratio >= 0.8:
                mapping[source] = canonical
                taken.add(canonical)
                matches.append(
                    ColumnMatch(source, canonical, base_confidence + 0.3 * ratio, "content")
                )
                break

    unmapped = [c for c in columns if c not in mapping]
    return mapping, matches, unmapped
