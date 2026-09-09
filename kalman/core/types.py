"""Tipos del núcleo.

Regla de oro de este paquete: todo hallazgo es explicable.
Cada vez que Kalman marca un dato, debe poder responder tres preguntas
sin ambigüedad: qué regla saltó, con qué confianza y qué se propone hacer.
Un cliente que paga no acepta "la red neuronal dice que es raro".
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Severity(enum.StrEnum):
    """Gravedad de un hallazgo.

    El orden importa: se usa para priorizar en los informes.
    """

    INFO = "info"
    """Se ha normalizado algo sin pérdida de información."""

    WARNING = "warning"
    """El dato es sospechoso pero puede ser legítimo. Revisión humana."""

    ERROR = "error"
    """El dato es inválido de forma demostrable. No debe usarse en producción."""


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
}


class Action(enum.StrEnum):
    """Qué se ha hecho con el valor."""

    KEPT = "kept"
    NORMALIZED = "normalized"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class Finding:
    """Un hallazgo sobre una celda concreta.

    `rule` es un identificador estable y versionado. Los clientes construyen
    automatismos sobre él, así que nunca se renombra sin subir la versión mayor
    del motor.
    """

    row: int
    column: str
    rule: str
    severity: Severity
    message: str
    action: Action = Action.KEPT
    original: Any = None
    proposed: Any = None
    confidence: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "column": self.column,
            "rule": self.rule,
            "severity": str(self.severity),
            "message": self.message,
            "action": str(self.action),
            "original": None if self.original is None else str(self.original),
            "proposed": None if self.proposed is None else str(self.proposed),
            "confidence": round(self.confidence, 4),
        }


@dataclass(frozen=True, slots=True)
class FieldResult:
    """Resultado de validar un único valor."""

    ok: bool
    normalized: Any = None
    rule: str = ""
    severity: Severity = Severity.ERROR
    message: str = ""
    confidence: float = 1.0


@dataclass(slots=True)
class CleanReport:
    """Informe auditable de una ejecución.

    No contiene ninguna estimación de ahorro económico. Kalman informa de lo
    que ha medido; cuánto vale eso lo decide el cliente con sus propias cifras.
    """

    engine_version: str
    rows_in: int = 0
    rows_valid: int = 0
    rows_quarantined: int = 0
    duplicate_groups: int = 0
    duplicate_rows: int = 0
    findings: list[Finding] = field(default_factory=list)
    columns_detected: dict[str, str] = field(default_factory=dict)
    unmapped_columns: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def counts_by_rule(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.rule] = counts.get(f.rule, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def counts_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity.value] += 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "rows_in": self.rows_in,
            "rows_valid": self.rows_valid,
            "rows_quarantined": self.rows_quarantined,
            "duplicate_groups": self.duplicate_groups,
            "duplicate_rows": self.duplicate_rows,
            "columns_detected": self.columns_detected,
            "unmapped_columns": self.unmapped_columns,
            "counts_by_rule": self.counts_by_rule(),
            "counts_by_severity": self.counts_by_severity(),
            "duration_ms": self.duration_ms,
        }
