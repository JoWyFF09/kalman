"""Escribe un CSV de ejemplo con errores realistas.

La lógica vive en `kalman.sample` porque también la usa la demo pública. Aquí
sólo está la interfaz de línea de comandos.

    python scripts/generate_sample.py --filas 2000 --salida ejemplo.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar el script desde la raíz del proyecto sin instalarlo antes.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalman.sample import generate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un CSV de ejemplo.")
    parser.add_argument("--filas", type=int, default=2000)
    parser.add_argument("--salida", default="ejemplo_clientes.csv")
    parser.add_argument("--semilla", type=int, default=42)
    args = parser.parse_args()

    df = generate(args.filas, args.semilla)
    df.to_csv(args.salida, index=False)

    print(f"Escritas {len(df):,} filas en {args.salida}".replace(",", "."))
    print("Pruébalo con:")
    print(f"  python -m kalman.cli clean {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
