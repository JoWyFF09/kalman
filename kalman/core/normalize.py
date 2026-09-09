"""Normalización de texto libre.

Nada de esto es inteligencia artificial y no se va a presentar como tal.
Es el trabajo aburrido que hace que dos filas que se refieren a la misma
empresa se puedan comparar.
"""

from __future__ import annotations

import math
import re
import unicodedata

#: Valores que pandas y las hojas de cálculo usan para "no hay dato".
_NULL_TOKENS = frozenset({"", "nan", "none", "null", "<na>", "nat", "#n/a", "n/a"})

_TRAILING_ZEROS_RE = re.compile(r"^(-?\d+)\.0+$")


def text_value(value: object) -> str:
    """Convierte a texto un valor que pandas puede haber leído como número.

    Es la función más importante de este módulo y nace de un fallo real.

    Cuando una columna de teléfonos tiene aunque sea una celda vacía, pandas no
    puede usar enteros, porque el entero de numpy no admite nulos. Convierte
    toda la columna a coma flotante y el teléfono 612345678 pasa a ser
    612345678.0. Al validarlo como texto quedan diez dígitos en vez de nueve y
    todos los teléfonos del fichero se marcan como inválidos.

    Lo mismo ocurre con los identificadores fiscales que empiezan por dígito y
    con los códigos postales. Cualquier validador que reciba datos leídos de un
    CSV tiene que pasar por aquí primero.
    """
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, int):
        return str(value)

    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return ""

    # "612345678.0" cuando el número ya venía convertido a texto.
    match = _TRAILING_ZEROS_RE.match(text)
    return match.group(1) if match else text

#: Formas societarias españolas y su abreviatura canónica. Sin esto,
#: "Talleres Gómez S.L." y "TALLERES GOMEZ SOCIEDAD LIMITADA" son dos clientes.
LEGAL_FORMS: dict[str, str] = {
    "sociedad limitada": "sl",
    "sociedad de responsabilidad limitada": "sl",
    "s l": "sl", "s.l": "sl", "s.l.": "sl", "sl": "sl", "slu": "sl", "s.l.u": "sl",
    "sociedad anonima": "sa",
    "s a": "sa", "s.a": "sa", "s.a.": "sa", "sa": "sa", "sau": "sa",
    "sociedad cooperativa": "scoop", "s coop": "scoop",
    "comunidad de bienes": "cb", "c.b": "cb", "cb": "cb",
    "sociedad civil": "sc",
}

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

#: "º", "°" y "ª" son letras para el motor de expresiones regulares pero ruido
#: para nosotros. Aparecen en cabeceras como "Nº Cliente" y "1ª Factura".
_ORDINAL_TABLE = str.maketrans({"º": " ", "°": " ", "ª": " ", "º": " "})


def strip_accents(text: str) -> str:
    """Quita tildes y diéresis conservando la letra base.

    La eñe se conserva: en español no es una ene con tilde, es otra letra, y
    confundir "Peña" con "Pena" produce fusiones incorrectas.
    """
    protected = text.replace("ñ", "\x00").replace("Ñ", "\x01")
    decomposed = unicodedata.normalize("NFKD", protected)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_marks.replace("\x00", "ñ").replace("\x01", "Ñ")


def collapse_spaces(text: str) -> str:
    """Reduce cualquier secuencia de espacios a uno solo y recorta los extremos."""
    return _WHITESPACE_RE.sub(" ", str(text)).strip()


def normalize_key(text: object) -> str:
    """Clave de comparación: minúsculas, sin tildes, sin puntuación.

    Se usa exclusivamente para agrupar y comparar. El valor que se devuelve al
    cliente sigue siendo el original.
    """
    if text is None:
        return ""
    # Los indicadores ordinales se eliminan ANTES de quitar tildes. La
    # descomposición Unicode de compatibilidad convierte "º" en "o", así que
    # hacerlo después dejaría "No Cliente" y el sinónimo no coincidiría.
    lowered = str(text).translate(_ORDINAL_TABLE)
    lowered = strip_accents(lowered).lower()
    without_punct = _PUNCT_RE.sub(" ", lowered)
    return collapse_spaces(without_punct)


def normalize_company(name: object) -> str:
    """Clave de comparación para razones sociales.

    Unifica la forma societaria y la mueve al final, de modo que el orden en
    que estuviera escrita deje de importar.
    """
    key = normalize_key(name)
    if not key:
        return ""

    tokens = key.split()
    form: str | None = None
    kept: list[str] = []

    index = 0
    while index < len(tokens):
        # Se prueban primero las formas de tres palabras, luego dos, luego una.
        matched = False
        for size in (3, 2, 1):
            candidate = " ".join(tokens[index : index + size])
            if candidate in LEGAL_FORMS:
                form = LEGAL_FORMS[candidate]
                index += size
                matched = True
                break
        if not matched:
            kept.append(tokens[index])
            index += 1

    if form:
        kept.append(form)
    return " ".join(kept)


def title_case_name(name: object) -> str:
    """Presenta un nombre propio en capitalización española.

    Las partículas van en minúscula salvo que abran el nombre, que es la regla
    que sigue el Registro Civil.
    """
    particles = {"de", "del", "la", "las", "los", "y", "i", "da", "do", "van", "von"}
    cleaned = collapse_spaces(name)
    if not cleaned:
        return ""

    words = cleaned.lower().split()
    result = [words[0].capitalize()]
    for word in words[1:]:
        result.append(word if word in particles else word.capitalize())
    return " ".join(result)


_DIGIT_RE = re.compile(r"\d")
_SUSPICIOUS_NAME_RE = re.compile(r"(.)\1{3,}|^[^a-záéíóúüñ]+$", re.IGNORECASE)


def name_looks_synthetic(name: object) -> tuple[bool, str]:
    """Heurística sobre nombres inventados, con el motivo concreto.

    Devuelve el motivo para que el informe no diga sólo "sospechoso". Un
    comercial que revisa la cuarentena necesita saber qué mirar.
    """
    text = collapse_spaces(name)
    if not text:
        return True, "Nombre vacío."
    if len(text) < 2:
        return True, "Nombre de un solo carácter."
    if _DIGIT_RE.search(text):
        return True, "El nombre contiene dígitos."
    if _SUSPICIOUS_NAME_RE.search(text):
        return True, "Patrón de tecleo aleatorio o sin letras."
    if normalize_key(text) in {"test", "prueba", "asdf", "nombre", "cliente", "n a"}:
        return True, "Valor de relleno de formulario."
    return False, ""
