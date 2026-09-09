"""Informe de auditoría.

Qué se ha quitado y por qué
---------------------------
El informe anterior imprimía esto:

    ahorro_estimado = alertas * 15
    "hemos evitado un posible coste ... estimado en {ahorro} EUR"

Ese quince no venía de ningún sitio. Poner una cifra inventada en un documento
con membrete, marcado como confidencial y entregado a una empresa es un riesgo
serio: si el cliente la usa en su contabilidad o en una decisión y resulta
falsa, el problema es de quien firmó el informe.

La regla de este módulo: sólo se imprime lo que se ha medido. Si el cliente
quiere una cifra en euros, aporta él su coste unitario y el informe deja
constancia expresa de que ese número es suyo y no una estimación de Kalman.

Separación entre contenido y dibujo
-----------------------------------
`compose` decide qué dice el informe y devuelve una estructura de datos.
`build_report` la dibuja en PDF. Se separan por dos motivos: el contenido se
puede comprobar con exactitud en una prueba, cosa poco fiable sobre los bytes
de un PDF, y el día que haga falta el mismo informe en HTML o en un correo se
reutiliza `compose` sin tocar nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

#: Paleta sobria. Un informe de auditoría no necesita degradados.
_INK = (17, 24, 39)
_MUTED = (107, 114, 128)
_LINE = (229, 231, 235)
_ALERT = (185, 28, 28)


@dataclass(frozen=True, slots=True)
class CostAssumption:
    """Coste unitario aportado por el cliente.

    Existe para que la cifra en euros del informe tenga un origen trazable.
    `source` se imprime literalmente al lado del importe.
    """

    euros_per_error: float
    source: str

    def total(self, errors: int) -> float:
        return self.euros_per_error * errors


@dataclass(frozen=True, slots=True)
class Line:
    """Una fila de etiqueta y valor."""

    label: str
    value: str
    alert: bool = False


@dataclass(frozen=True, slots=True)
class Section:
    """Un bloque del informe."""

    title: str
    lines: tuple[Line, ...] = ()
    note: str = ""


@dataclass(frozen=True, slots=True)
class Composed:
    """Informe completo, listo para dibujar en cualquier formato."""

    org_name: str
    engine_version: str
    generated_at: datetime
    sections: tuple[Section, ...] = field(default_factory=tuple)

    def as_text(self) -> str:
        """Versión en texto plano. Es lo que comprueban las pruebas."""
        parts = [self.org_name, f"Kalman {self.engine_version}"]
        for section in self.sections:
            parts.append(section.title)
            parts.extend(f"{line.label}: {line.value}" for line in section.lines)
            if section.note:
                parts.append(section.note)
        return "\n".join(parts)


#: Nombre legible de cada regla del motor. Un informe que dice
#: "tax_id.cif.checksum" no lo lee nadie fuera del equipo técnico.
RULE_LABELS: dict[str, str] = {
    "tax_id.missing": "Identificador fiscal vacío",
    "tax_id.length": "Identificador fiscal con longitud incorrecta",
    "tax_id.format": "Identificador fiscal con formato desconocido",
    "tax_id.nif.checksum": "NIF con letra de control incorrecta",
    "tax_id.nie.checksum": "NIE con letra de control incorrecta",
    "tax_id.cif.checksum": "CIF con dígito de control incorrecto",
    "iban.missing": "IBAN vacío",
    "iban.checksum": "IBAN con dígitos de control incorrectos",
    "iban.length": "IBAN con longitud incorrecta",
    "iban.format": "IBAN con formato inválido",
    "email.missing": "Email vacío",
    "email.syntax": "Email con sintaxis inválida",
    "email.typo": "Email con posible errata en el dominio",
    "email.disposable": "Email de dominio desechable",
    "email.placeholder": "Email de relleno",
    "email.normalized": "Email normalizado",
    "phone.missing": "Teléfono vacío",
    "phone.format_es": "Teléfono que no corresponde a un número español",
    "phone.placeholder": "Teléfono de relleno",
    "phone.normalized": "Teléfono normalizado a formato internacional",
    "postal_code.province": "Código postal de provincia inexistente",
    "postal_code.length": "Código postal con longitud incorrecta",
    "postal_code.lost_zero": "Código postal sin el cero inicial",
    "duplicate.group": "Fila duplicada",
    "age.impossible": "Edad imposible",
    "income.impossible": "Importe imposible",
    "age.outlier": "Edad atípica",
    "income.outlier": "Importe atípico",
    "name.synthetic": "Nombre probablemente inventado",
    "name.formatted": "Nombre con capitalización corregida",
    "company.synthetic": "Razón social probablemente inventada",
}

_METHODOLOGY = (
    "Los identificadores fiscales y los IBAN se verifican con su dígito de "
    "control oficial: el resultado es exacto, no probabilístico. Los valores "
    "numéricos atípicos se detectan con la desviación absoluta mediana y el "
    "umbral publicado por Iglewicz y Hoaglin (1993). Los duplicados se "
    "proponen, nunca se fusionan automáticamente. Este informe es reproducible "
    "con la versión del motor indicada al pie."
)

_NO_ESTIMATE = (
    "Kalman no calcula cuánto dinero supone esto para su empresa. El coste de "
    "un dato incorrecto depende de su operativa y sólo usted lo conoce. "
    "Indíquenos su coste por incidencia y lo incorporamos al informe citando "
    "su origen."
)


def _miles(value: object) -> str:
    """Formatea un entero con el separador de miles español."""
    return f"{int(value):,}".replace(",", ".")


def compose(
    report: dict[str, object],
    org_name: str,
    cost: CostAssumption | None = None,
    top_rules: int = 12,
    now: datetime | None = None,
) -> Composed:
    """Decide qué dice el informe. No dibuja nada."""
    severities = report.get("counts_by_severity")
    errors = int(severities["error"]) if isinstance(severities, dict) else 0
    quarantined = int(report["rows_quarantined"])
    duplicate_groups = int(report["duplicate_groups"])

    sections: list[Section] = [
        Section(
            "Resumen",
            (
                Line("Filas analizadas", _miles(report["rows_in"])),
                Line("Filas sin incidencias", _miles(report["rows_valid"])),
                Line("Filas en cuarentena", _miles(quarantined), alert=quarantined > 0),
                Line(
                    "Grupos de duplicados", _miles(duplicate_groups),
                    alert=duplicate_groups > 0,
                ),
                Line("Tiempo de proceso", f"{_miles(report['duration_ms'])} ms"),
            ),
            note=(
                "Una fila en cuarentena contiene al menos un dato inválido de "
                "forma demostrable, como un dígito de control que no cuadra. "
                "No se ha eliminado: se ha separado para que usted decida."
            ),
        )
    ]

    counts = report.get("counts_by_rule")
    if isinstance(counts, dict) and counts:
        shown = list(counts.items())[:top_rules]
        sections.append(
            Section(
                "Incidencias por tipo",
                tuple(
                    Line(RULE_LABELS.get(rule, rule), _miles(count))
                    for rule, count in shown
                ),
                note=(
                    f"Se muestran los {top_rules} tipos más frecuentes de {len(counts)}."
                    if len(counts) > top_rules
                    else ""
                ),
            )
        )

    detected = report.get("columns_detected")
    unmapped = report.get("unmapped_columns")
    if isinstance(detected, dict) and detected:
        note = ""
        if isinstance(unmapped, list) and unmapped:
            note = (
                "Columnas no reconocidas y conservadas sin modificar: "
                + ", ".join(str(c) for c in unmapped[:20])
            )
        sections.append(
            Section(
                "Columnas reconocidas",
                tuple(Line(str(k), str(v)) for k, v in list(detected.items())[:15]),
                note=note,
            )
        )

    if cost is None:
        sections.append(Section("Impacto económico", note=_NO_ESTIMATE))
    else:
        sections.append(
            Section(
                "Impacto económico",
                (
                    Line("Incidencias demostrables", _miles(errors)),
                    Line("Coste por incidencia", f"{cost.euros_per_error:,.2f} EUR"),
                    Line("Total", f"{cost.total(errors):,.2f} EUR", alert=errors > 0),
                ),
                note=(
                    "El coste por incidencia lo ha aportado el cliente. Origen: "
                    f"{cost.source}. Kalman no ha estimado ni validado esta cifra."
                ),
            )
        )

    sections.append(Section("Metodología", note=_METHODOLOGY))

    return Composed(
        org_name=org_name,
        engine_version=str(report["engine_version"]),
        generated_at=now or datetime.now(UTC),
        sections=tuple(sections),
    )


def _latin1(text: str) -> str:
    """Reduce el texto a lo que cubren las fuentes básicas de fpdf2.

    Con las fuentes centrales sólo hay Latin-1. Las tildes y la eñe caben; el
    símbolo del euro y las comillas tipográficas, no.
    """
    replacements = {
        "€": "EUR", "—": "-", "–": "-", "“": '"', "”": '"', "’": "'", "·": "-",
    }
    cleaned = "".join(replacements.get(c, c) for c in str(text))
    return cleaned.encode("latin-1", "replace").decode("latin-1")


def build_report(
    report: dict[str, object],
    org_name: str,
    cost: CostAssumption | None = None,
    top_rules: int = 12,
) -> bytes:
    """Dibuja el informe en PDF.

    `report` es el diccionario que devuelve `CleanReport.as_dict()`.
    """
    from fpdf import FPDF  # noqa: PLC0415

    content = compose(report, org_name, cost, top_rules)

    class _Document(FPDF):
        def header(self) -> None:
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(*_INK)
            self.cell(0, 8, "KALMAN", align="L")
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*_MUTED)
            self.cell(
                0, 8, _latin1("Auditoría de calidad de datos"),
                align="R", new_x="LMARGIN", new_y="NEXT",
            )
            self.set_draw_color(*_LINE)
            self.line(10, 20, 200, 20)
            self.ln(8)

        def footer(self) -> None:
            self.set_y(-15)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*_MUTED)
            self.cell(
                0, 8,
                _latin1(
                    f"Kalman {content.engine_version} - {content.org_name} - "
                    f"Pagina {self.page_no()}"
                ),
                align="C",
            )

    pdf = _Document()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_title(_latin1(f"Auditoría de calidad de datos - {org_name}"))
    pdf.set_creator(f"Kalman {content.engine_version}")
    # Sin comprimir, el texto queda legible dentro del fichero y una
    # herramienta documental del cliente puede indexarlo. Un informe de unas
    # pocas páginas no gana nada por comprimirse.
    pdf.set_compression(False)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 9, _latin1(content.org_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(
        0, 5,
        _latin1(f"Ejecutado el {content.generated_at:%d/%m/%Y a las %H:%M} UTC"),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(4)

    for section in content.sections:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_INK)
        pdf.cell(0, 7, _latin1(section.title), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        for line in section.lines:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*_MUTED)
            pdf.cell(120, 7, _latin1(f" {line.label}"), border="B")
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*(_ALERT if line.alert else _INK))
            pdf.cell(
                70, 7, _latin1(f"{line.value} "), border="B",
                align="R", new_x="LMARGIN", new_y="NEXT",
            )

        if section.note:
            pdf.ln(2)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*_MUTED)
            pdf.multi_cell(0, 4.5, _latin1(section.note))
            pdf.ln(1)

    return bytes(pdf.output())
