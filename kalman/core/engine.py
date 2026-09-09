"""Motor de limpieza. Orquesta detección de esquema, validación y duplicados.

Este módulo es puro: no toca red, ni disco, ni base de datos, ni Stripe.
Entra un DataFrame y sale un DataFrame más un informe. Esa restricción es lo
que permite tener una batería de pruebas que corre en menos de un segundo y
que hace que el motor se pueda vender también como biblioteca o como API sin
reescribir nada.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import outliers as outliers_mod
from .dedupe import DuplicateGroup, find_duplicates
from .normalize import collapse_spaces, name_looks_synthetic, title_case_name
from .pseudonymize import Pseudonymizer, mask_email, mask_phone, mask_tax_id
from .schema_map import ColumnMatch, detect_schema
from .types import Action, CleanReport, FieldResult, Finding, Severity
from .validators.contact import validate_email, validate_phone_es, validate_postal_code_es
from .validators.iban import validate_iban
from .validators.identity import validate_tax_id

#: Versión del motor. Se incluye en cada informe para que un cliente pueda
#: reproducir exactamente un resultado del pasado, que es un requisito de
#: cualquier auditoría seria.
ENGINE_VERSION = "2.0.0"

#: Campo canónico -> función validadora.
FIELD_VALIDATORS = {
    "email": validate_email,
    "phone": validate_phone_es,
    "tax_id": validate_tax_id,
    "iban": validate_iban,
    "postal_code": validate_postal_code_es,
}

#: Campos numéricos sobre los que se busca atípicos.
NUMERIC_FIELDS = ("age", "income")

#: Correspondencia con las cotas de dominio de `outliers`.
_DOMAIN_KEYS = {"age": "edad", "income": "ingresos_anuales"}


def _apply_proposals(
    df: pd.DataFrame, proposals: dict[tuple[int, str], object]
) -> None:
    """Escribe las correcciones ampliando el tipo de la columna si hace falta.

    Este caso aparece constantemente con datos reales. Excel guarda el código
    postal de Álava como el número 1001 en lugar del texto "01001", pandas lee
    esa columna como entero de 64 bits y la corrección que propone el motor es
    la cadena "01001". Escribir texto en una columna entera lanza `TypeError`
    en pandas 2.x, así que la columna se amplía a tipo objeto antes de tocarla.

    Se agrupa por columna para convertir una sola vez y no una por celda.
    """
    by_column: dict[str, list[tuple[int, object]]] = {}
    for (row, column), value in proposals.items():
        by_column.setdefault(column, []).append((row, value))

    for column, changes in by_column.items():
        series = df[column]
        needs_object = series.dtype != object and any(
            isinstance(value, str) for _, value in changes
        )
        if needs_object:
            df[column] = series.astype(object)
        for row, value in changes:
            df.at[row, column] = value


@dataclass(slots=True)
class CleanOptions:
    """Parámetros de una ejecución.

    Todo lo configurable vive aquí. No hay ningún número mágico repartido por
    el código, que era el caso del umbral 0.05 de la versión anterior.
    """

    outlier_threshold: float = outliers_mod.DEFAULT_THRESHOLD
    duplicate_threshold: float = 0.92
    quarantine_on: Severity = Severity.ERROR
    """Gravedad mínima que manda una fila a cuarentena."""

    apply_normalizations: bool = True
    """Si es falso, las correcciones se proponen pero no se escriben."""

    detect_duplicates: bool = True
    pseudonymize: bool = False
    """Sustituye datos personales por seudónimos HMAC en la salida."""

    mask_output: bool = False
    """Enmascara datos personales conservando su forma legible."""

    column_overrides: dict[str, str] = field(default_factory=dict)
    max_findings: int = 100_000
    """Tope de hallazgos guardados, para que un fichero catastrófico no agote
    la memoria del servidor."""


@dataclass(slots=True)
class CleanResult:
    """Salida completa de una ejecución."""

    valid: pd.DataFrame
    quarantine: pd.DataFrame
    report: CleanReport
    duplicates: list[DuplicateGroup]
    schema_matches: list[ColumnMatch]
    outlier_models: dict[str, outliers_mod.OutlierModel]


class CleaningEngine:
    """Motor de limpieza de datos.

    Uso:
        engine = CleaningEngine()
        result = engine.run(df, options=CleanOptions())
    """

    version = ENGINE_VERSION

    def __init__(self, pseudonymizer: Pseudonymizer | None = None) -> None:
        self._pseudonymizer = pseudonymizer

    def run(self, df: pd.DataFrame, options: CleanOptions | None = None) -> CleanResult:
        started = time.perf_counter()
        options = options or CleanOptions()

        if df.empty:
            report = CleanReport(engine_version=self.version)
            return CleanResult(df.copy(), df.copy(), report, [], [], {})

        working = df.copy()
        working.reset_index(drop=True, inplace=True)

        samples = {c: working[c].dropna().head(50).tolist() for c in working.columns}
        mapping, matches, unmapped = detect_schema(
            list(working.columns), samples, options.column_overrides
        )

        report = CleanReport(engine_version=self.version, rows_in=len(working))
        report.columns_detected = mapping
        report.unmapped_columns = unmapped

        canonical = {v: k for k, v in mapping.items()}

        # Estas dos estructuras acumulan el veredicto por fila. Se resuelven
        # al final, de modo que una fila con cinco errores se cuente una vez.
        row_severity = np.zeros(len(working), dtype=np.int8)
        proposals: dict[tuple[int, str], object] = {}

        self._validate_fields(working, canonical, report, row_severity, proposals, options)
        self._validate_names(working, canonical, report, row_severity, proposals)
        models = self._detect_outliers(working, canonical, report, row_severity, options)

        duplicates: list[DuplicateGroup] = []
        if options.detect_duplicates:
            duplicates = self._detect_duplicates(
                working, canonical, report, options
            )

        if options.apply_normalizations:
            _apply_proposals(working, proposals)

        threshold = {"info": 0, "warning": 1, "error": 2}[options.quarantine_on.value]
        is_quarantined = row_severity >= threshold

        valid = working.loc[~is_quarantined].copy()
        quarantine = working.loc[is_quarantined].copy()

        if options.pseudonymize or options.mask_output:
            valid = self._protect(valid, canonical, options)

        report.rows_valid = len(valid)
        report.rows_quarantined = len(quarantine)
        report.duration_ms = int((time.perf_counter() - started) * 1000)

        return CleanResult(valid, quarantine, report, duplicates, matches, models)

    # ---------------------------------------------------------------- interno

    def _record(
        self,
        report: CleanReport,
        row_severity: np.ndarray,
        row: int,
        column: str,
        result: FieldResult,
        options: CleanOptions,
        proposals: dict[tuple[int, str], object],
    ) -> None:
        """Anota un hallazgo y actualiza la gravedad acumulada de la fila."""
        if len(report.findings) >= options.max_findings:
            return

        action = Action.KEPT
        if result.normalized is not None and not result.ok:
            action = Action.QUARANTINED
        elif result.normalized is not None:
            action = Action.NORMALIZED

        report.add(
            Finding(
                row=row,
                column=column,
                rule=result.rule,
                severity=result.severity,
                message=result.message,
                action=action,
                original=None,
                proposed=result.normalized,
                confidence=result.confidence,
            )
        )
        level = {"info": 0, "warning": 1, "error": 2}[result.severity.value]
        row_severity[row] = max(row_severity[row], level)

    def _validate_fields(
        self,
        df: pd.DataFrame,
        canonical: dict[str, str],
        report: CleanReport,
        row_severity: np.ndarray,
        proposals: dict[tuple[int, str], object],
        options: CleanOptions,
    ) -> None:
        """Aplica el validador correspondiente a cada campo reconocido."""
        for field_name, validator in FIELD_VALIDATORS.items():
            column = canonical.get(field_name)
            if column is None:
                continue

            for row, value in enumerate(df[column].tolist()):
                result = validator(value)

                if result.ok:
                    # Aun siendo válido puede haber cambiado de forma, por
                    # ejemplo un teléfono pasado a E.164.
                    if result.normalized is not None and str(result.normalized) != str(value):
                        proposals[(row, column)] = result.normalized
                        report.add(
                            Finding(
                                row=row, column=column, rule=f"{field_name}.normalized",
                                severity=Severity.INFO,
                                message="Valor normalizado a formato canónico.",
                                action=Action.NORMALIZED,
                                original=value, proposed=result.normalized,
                            )
                        )
                    continue

                self._record(report, row_severity, row, column, result, options, proposals)

                # Una sugerencia con confianza alta se aplica; una dudosa sólo
                # se reporta. El umbral está aquí y no repartido por el código.
                if result.severity is Severity.WARNING and result.confidence >= 0.85:
                    if result.normalized is not None:
                        proposals[(row, column)] = result.normalized

    def _validate_names(
        self,
        df: pd.DataFrame,
        canonical: dict[str, str],
        report: CleanReport,
        row_severity: np.ndarray,
        proposals: dict[tuple[int, str], object],
    ) -> None:
        """Detecta nombres sintéticos y normaliza la capitalización."""
        for field_name in ("name", "company"):
            column = canonical.get(field_name)
            if column is None:
                continue

            for row, value in enumerate(df[column].tolist()):
                synthetic, reason = name_looks_synthetic(value)
                if synthetic:
                    report.add(
                        Finding(
                            row=row, column=column, rule=f"{field_name}.synthetic",
                            severity=Severity.WARNING, message=reason,
                            action=Action.KEPT, original=value,
                        )
                    )
                    row_severity[row] = max(row_severity[row], 1)
                    continue

                cleaned = (
                    title_case_name(value) if field_name == "name" else collapse_spaces(value)
                )
                if cleaned and cleaned != str(value):
                    proposals[(row, column)] = cleaned
                    report.add(
                        Finding(
                            row=row, column=column, rule=f"{field_name}.formatted",
                            severity=Severity.INFO,
                            message="Capitalización y espacios normalizados.",
                            action=Action.NORMALIZED,
                            original=value, proposed=cleaned,
                        )
                    )

    def _detect_outliers(
        self,
        df: pd.DataFrame,
        canonical: dict[str, str],
        report: CleanReport,
        row_severity: np.ndarray,
        options: CleanOptions,
    ) -> dict[str, outliers_mod.OutlierModel]:
        """Marca valores numéricos imposibles y estadísticamente atípicos."""
        models: dict[str, outliers_mod.OutlierModel] = {}

        for field_name in NUMERIC_FIELDS:
            column = canonical.get(field_name)
            if column is None:
                continue

            numeric = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
            model = outliers_mod.fit_outlier_model(
                numeric, column, options.outlier_threshold
            )
            models[field_name] = model
            scores = model.score(np.nan_to_num(numeric, nan=model.median))
            low, high = model.bounds()
            domain_key = _DOMAIN_KEYS.get(field_name, field_name)

            for row, value in enumerate(numeric):
                if not np.isfinite(value):
                    report.add(
                        Finding(
                            row=row, column=column, rule=f"{field_name}.missing",
                            severity=Severity.WARNING,
                            message="Valor numérico ausente o no convertible.",
                            action=Action.KEPT,
                        )
                    )
                    row_severity[row] = max(row_severity[row], 1)
                    continue

                # Capa 1: lo imposible. Independiente de los datos.
                domain_message = outliers_mod.check_domain(domain_key, float(value))
                if domain_message:
                    report.add(
                        Finding(
                            row=row, column=column, rule=f"{field_name}.impossible",
                            severity=Severity.ERROR, message=domain_message,
                            action=Action.QUARANTINED, original=value,
                        )
                    )
                    row_severity[row] = 2
                    continue

                # Capa 2: lo raro. Relativo a este conjunto concreto.
                if abs(scores[row]) > model.threshold:
                    report.add(
                        Finding(
                            row=row, column=column, rule=f"{field_name}.outlier",
                            severity=Severity.WARNING,
                            message=(
                                f"Valor atípico. El rango habitual de esta columna "
                                f"va de {low:,.0f} a {high:,.0f}."
                            ),
                            action=Action.KEPT, original=value,
                            confidence=min(0.99, abs(float(scores[row])) / 10),
                        )
                    )
                    row_severity[row] = max(row_severity[row], 1)

        return models

    def _detect_duplicates(
        self,
        df: pd.DataFrame,
        canonical: dict[str, str],
        report: CleanReport,
        options: CleanOptions,
    ) -> list[DuplicateGroup]:
        """Agrupa filas que representan la misma entidad."""
        records: list[dict[str, object]] = []
        for row in range(len(df)):
            record: dict[str, object] = {}
            for field_name in ("tax_id", "iban", "email", "phone", "name", "company", "postal_code"):
                column = canonical.get(field_name)
                if column is not None:
                    record[field_name] = df.at[row, column]
            records.append(record)

        groups = find_duplicates(records, options.duplicate_threshold)
        report.duplicate_groups = len(groups)
        report.duplicate_rows = sum(len(g.duplicates) for g in groups)

        for group in groups:
            for row in group.duplicates:
                report.add(
                    Finding(
                        row=row, column="__row__", rule="duplicate.group",
                        severity=Severity.WARNING,
                        message=(
                            f"Duplicado de la fila {group.survivor} "
                            f"por coincidencia de {group.key_type}."
                        ),
                        action=Action.KEPT, confidence=group.confidence,
                    )
                )
        return groups

    def _protect(
        self, df: pd.DataFrame, canonical: dict[str, str], options: CleanOptions
    ) -> pd.DataFrame:
        """Aplica seudonimización o enmascarado a los campos personales."""
        protected = df.copy()

        if options.pseudonymize:
            if self._pseudonymizer is None:
                raise ValueError(
                    "Se ha pedido seudonimizar sin configurar la clave. "
                    "Construye el motor con CleaningEngine(Pseudonymizer(clave, org))."
                )
            for field_name in ("name", "company", "email", "phone", "tax_id", "iban", "address"):
                column = canonical.get(field_name)
                if column is not None and column in protected.columns:
                    protected[column] = protected[column].map(
                        lambda v, f=field_name: self._pseudonymizer.token(v, f)
                    )
            return protected

        maskers = {"email": mask_email, "phone": mask_phone, "tax_id": mask_tax_id, "iban": mask_tax_id}
        for field_name, masker in maskers.items():
            column = canonical.get(field_name)
            if column is not None and column in protected.columns:
                protected[column] = protected[column].map(masker)
        return protected
