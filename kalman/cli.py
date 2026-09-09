"""Interfaz de línea de comandos.

Un cliente técnico no quiere una web: quiere meter esto en su proceso nocturno.
La CLI cuesta poco y abre un canal de distribución que la web no abre, porque
se puede publicar en el índice de paquetes de Python y probarla sin registro.

    pip install kalman
    kalman check-nif B65410011
    kalman clean clientes.csv --out limpio.csv --report informe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core.engine import CleaningEngine, CleanOptions
from .core.validators.contact import (
    validate_email,
    validate_phone_es,
    validate_postal_code_es,
)
from .core.validators.iban import validate_iban
from .core.validators.identity import validate_tax_id

_SINGLE_VALIDATORS = {
    "check-nif": ("identificador fiscal", validate_tax_id),
    "check-iban": ("IBAN", validate_iban),
    "check-email": ("email", validate_email),
    "check-phone": ("teléfono", validate_phone_es),
    "check-cp": ("código postal", validate_postal_code_es),
}


def _read_table(path: Path):
    import pandas as pd

    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def _cmd_check(command: str, value: str) -> int:
    label, validator = _SINGLE_VALIDATORS[command]
    result = validator(value)

    if result.ok:
        print(f"OK  {label}: {result.normalized or value}")
        return 0

    print(f"MAL {label}: {value}")
    print(f"    regla:  {result.rule}")
    print(f"    motivo: {result.message}")
    if result.normalized and result.normalized != value:
        print(f"    sugerencia: {result.normalized}")
    return 1


def _cmd_clean(args: argparse.Namespace) -> int:
    source = Path(args.fichero)
    if not source.exists():
        print(f"No existe el fichero {source}", file=sys.stderr)
        return 2

    df = _read_table(source)
    result = CleaningEngine().run(
        df,
        CleanOptions(
            apply_normalizations=not args.solo_auditar,
            detect_duplicates=not args.sin_duplicados,
        ),
    )
    report = result.report

    print(f"Filas analizadas:   {report.rows_in:,}".replace(",", "."))
    print(f"Sin incidencias:    {report.rows_valid:,}".replace(",", "."))
    print(f"En cuarentena:      {report.rows_quarantined:,}".replace(",", "."))
    print(f"Grupos duplicados:  {report.duplicate_groups:,}".replace(",", "."))
    print(f"Tiempo:             {report.duration_ms} ms")

    counts = report.counts_by_rule()
    if counts:
        print("\nIncidencias por regla:")
        for rule, count in list(counts.items())[:15]:
            print(f"  {count:>7,}  {rule}".replace(",", "."))

    if args.out:
        result.valid.to_csv(args.out, index=False)
        print(f"\nCSV depurado escrito en {args.out}")

    if args.cuarentena:
        result.quarantine.to_csv(args.cuarentena, index=False)
        print(f"Cuarentena escrita en {args.cuarentena}")

    if args.report:
        Path(args.report).write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Informe JSON escrito en {args.report}")

    # Código de salida distinto de cero si hay errores demostrables, para que
    # se pueda usar como puerta de calidad en un proceso automático.
    return 1 if report.rows_quarantined else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kalman",
        description="Validación y limpieza de datos de clientes españoles.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    for command, (label, _) in _SINGLE_VALIDATORS.items():
        single = sub.add_parser(command, help=f"Valida un {label}.")
        single.add_argument("valor")

    clean = sub.add_parser("clean", help="Limpia un CSV o un Excel completo.")
    clean.add_argument("fichero")
    clean.add_argument("--out", help="Ruta del CSV depurado.")
    clean.add_argument("--cuarentena", help="Ruta del CSV con las filas rechazadas.")
    clean.add_argument("--report", help="Ruta del informe en JSON.")
    clean.add_argument(
        "--solo-auditar", action="store_true",
        help="Informa sin modificar ningún valor.",
    )
    clean.add_argument("--sin-duplicados", action="store_true", help="Omite la deduplicación.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.comando in _SINGLE_VALIDATORS:
        return _cmd_check(args.comando, args.valor)
    return _cmd_clean(args)


if __name__ == "__main__":
    raise SystemExit(main())
