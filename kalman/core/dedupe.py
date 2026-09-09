"""Detección de duplicados por bloqueo y similitud.

Es la función que más dinero ahorra y la que el motor anterior no tenía. Un CRM
con el mismo cliente tres veces genera tres facturas, tres envíos de campaña y
un informe de ventas que no cuadra con contabilidad.

Estrategia en dos fases, que es la estándar en resolución de entidades:

1. Bloqueo. Comparar todas las filas contra todas es cuadrático: un millón de
   filas son quinientos mil millones de comparaciones. En su lugar se agrupa
   por claves baratas y sólo se compara dentro de cada grupo.
2. Puntuación. Dentro del bloque se compara con similitud de cadenas y se
   exige un umbral alto para declarar duplicado.

No se fusiona nada automáticamente. Se propone el grupo y decide el cliente.
Fusionar dos clientes que no lo eran es un error mucho más caro que dejar un
duplicado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .normalize import normalize_company, normalize_key


@dataclass(slots=True)
class DuplicateGroup:
    """Conjunto de filas que apuntan a la misma entidad del mundo real."""

    rows: list[int]
    key_type: str
    key_value: str
    confidence: float
    survivor: int = field(init=False)

    def __post_init__(self) -> None:
        # Se propone conservar la fila de menor índice, que en un volcado de
        # CRM suele ser el registro más antiguo y el que tiene el histórico.
        self.survivor = min(self.rows)

    @property
    def duplicates(self) -> list[int]:
        return [r for r in self.rows if r != self.survivor]

    def as_dict(self) -> dict[str, object]:
        return {
            "key_type": self.key_type,
            "key_value": self.key_value,
            "confidence": round(self.confidence, 4),
            "survivor_row": self.survivor,
            "duplicate_rows": self.duplicates,
            "size": len(self.rows),
        }


def similarity(a: str, b: str) -> float:
    """Similitud entre dos cadenas, entre 0 y 1.

    Se usa `difflib` de la biblioteca estándar en lugar de una dependencia
    externa. Para cadenas cortas como nombres y razones sociales la diferencia
    de calidad frente a Levenshtein no justifica añadir un paquete más.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


class _UnionFind:
    """Estructura para unir filas en grupos transitivos.

    Si A duplica a B por email y B duplica a C por teléfono, los tres son el
    mismo cliente. Sin unión-búsqueda saldrían dos grupos solapados.
    """

    def __init__(self) -> None:
        self._parent: dict[int, int] = {}

    def find(self, item: int) -> int:
        self._parent.setdefault(item, item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        # Compresión de caminos.
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a

    def groups(self) -> dict[int, list[int]]:
        result: dict[int, list[int]] = {}
        for item in list(self._parent):
            result.setdefault(self.find(item), []).append(item)
        return {k: sorted(v) for k, v in result.items() if len(v) > 1}


#: Umbral de similitud para declarar duplicado por nombre. Deliberadamente
#: alto: en resolución de entidades un falso positivo destruye datos.
NAME_MATCH_THRESHOLD = 0.92


def find_duplicates(
    records: list[dict[str, object]],
    name_threshold: float = NAME_MATCH_THRESHOLD,
) -> list[DuplicateGroup]:
    """Localiza grupos de filas que representan la misma entidad.

    `records` es una lista de diccionarios con las claves canónicas ya
    mapeadas. Se aprovechan, por orden de fiabilidad decreciente:
    identificador fiscal, IBAN, email, teléfono y por último nombre más
    código postal.
    """
    union = _UnionFind()
    evidence: dict[tuple[int, int], tuple[str, str, float]] = {}

    def link(rows: list[int], key_type: str, key_value: str, conf: float) -> None:
        for i in range(len(rows) - 1):
            union.union(rows[i], rows[i + 1])
            pair = (rows[i], rows[i + 1])
            if pair not in evidence or evidence[pair][2] < conf:
                evidence[pair] = (key_type, key_value, conf)

    # Fase 1: claves exactas. Un identificador fiscal repetido es certeza.
    exact_keys: list[tuple[str, str, float]] = [
        ("tax_id", "tax_id", 1.0),
        ("iban", "iban", 0.98),
        ("email", "email", 0.97),
        ("phone", "phone", 0.90),
    ]

    for key_type, field_name, conf in exact_keys:
        buckets: dict[str, list[int]] = {}
        for index, record in enumerate(records):
            value = record.get(field_name)
            if value in (None, "", "nan"):
                continue
            buckets.setdefault(str(value).strip().lower(), []).append(index)
        for value, rows in buckets.items():
            if len(rows) > 1:
                link(rows, key_type, value, conf)

    # Fase 2: nombre similar dentro del mismo código postal. El código postal
    # actúa de bloque: sin él habría que comparar cada nombre con todos.
    name_buckets: dict[str, list[tuple[int, str]]] = {}
    for index, record in enumerate(records):
        raw_name = record.get("company") or record.get("name")
        if not raw_name:
            continue
        key = (
            normalize_company(raw_name)
            if record.get("company")
            else normalize_key(raw_name)
        )
        if not key:
            continue
        block = str(record.get("postal_code") or "")[:5] or "_"
        name_buckets.setdefault(block, []).append((index, key))

    for block, entries in name_buckets.items():
        # Un bloque enorme indica que el código postal no discrimina, por
        # ejemplo cuando falta en la mayoría de filas. Comparar todo contra
        # todo ahí sería inaceptablemente lento, así que se omite.
        if len(entries) > 2000:
            continue
        for i in range(len(entries)):
            index_a, key_a = entries[i]
            for j in range(i + 1, len(entries)):
                index_b, key_b = entries[j]
                # Filtro barato antes del cálculo caro: si las longitudes
                # difieren mucho, la similitud no puede superar el umbral.
                if abs(len(key_a) - len(key_b)) / max(len(key_a), len(key_b), 1) > 0.2:
                    continue
                score = similarity(key_a, key_b)
                if score >= name_threshold:
                    link([index_a, index_b], "name", key_a, score * 0.9)

    groups: list[DuplicateGroup] = []
    for rows in union.groups().values():
        best_type, best_value, best_conf = "name", "", 0.0
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                for pair in ((rows[i], rows[j]), (rows[j], rows[i])):
                    if pair in evidence:
                        key_type, key_value, conf = evidence[pair]
                        if conf > best_conf:
                            best_type, best_value, best_conf = key_type, key_value, conf
        groups.append(DuplicateGroup(rows, best_type, best_value, best_conf))

    groups.sort(key=lambda g: (-g.confidence, g.survivor))
    return groups
