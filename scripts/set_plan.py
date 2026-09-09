"""Asigna un plan a una organización a mano, para desarrollo y pruebas.

    python scripts/set_plan.py --org kalman --plan growth
    python scripts/set_plan.py --listar

Por qué esto no contradice la regla de seguridad
------------------------------------------------
La regla es que **el navegador nunca decide quién ha pagado**. El derecho de
uso lo escribe el webhook firmado de Stripe y ningún formulario puede
concedérselo a sí mismo.

Este script no es el navegador. Es una herramienta de consola que necesita la
cadena de conexión de la base de datos, es decir, credenciales de
administrador. Quien tiene esa cadena ya puede cambiar cualquier fila con
cualquier cliente de Postgres; negárselo aquí no protegería nada y solo haría
imposible probar el producto.

Lo que sí importa es que este camino no exista desde la web, y no existe.

Aun así se niega a ejecutarse con KALMAN_ENV=production, porque el sitio para
tocar una suscripción real es el panel de Stripe, no un script.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalman.billing.plans import PLANS  # noqa: E402
from kalman.config import ConfigError, load_dotenv  # noqa: E402

ESTADOS = ["active", "trialing", "past_due", "canceled", "inactive"]


def conectar():
    load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise ConfigError("Falta DATABASE_URL. Ejecuta antes: python scripts/doctor.py")

    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(url, row_factory=dict_row, connect_timeout=15)


def listar() -> int:
    with conectar() as conn:
        filas = conn.execute(
            """
            SELECT o.slug, o.name, s.plan, s.status, s.current_period_end
            FROM organizations o
            LEFT JOIN subscriptions s ON s.org_id = o.id
            WHERE o.deleted_at IS NULL
            ORDER BY o.created_at
            """
        ).fetchall()

    if not filas:
        print("No hay ninguna organizacion. Crea una con scripts/bootstrap.py")
        return 1

    print()
    print(f"{'IDENTIFICADOR':<24} {'NOMBRE':<24} {'PLAN':<10} ESTADO")
    print("-" * 72)
    for fila in filas:
        print(
            f"{fila['slug']:<24} {(fila['name'] or '')[:23]:<24} "
            f"{(fila['plan'] or 'free'):<10} {fila['status'] or 'inactive'}"
        )
    print()
    return 0


def asignar(slug: str, plan: str, estado: str) -> int:
    if os.environ.get("KALMAN_ENV", "").strip().lower() == "production":
        print("Este script no se ejecuta en produccion.", file=sys.stderr)
        print("Cambia la suscripcion desde el panel de Stripe.", file=sys.stderr)
        return 2

    with conectar() as conn:
        org = conn.execute(
            "SELECT id, name FROM organizations WHERE slug = %s", (slug,)
        ).fetchone()

        if org is None:
            print(f"No existe ninguna organizacion con identificador '{slug}'.")
            print("Mira cuales hay con: python scripts/set_plan.py --listar")
            return 1

        conn.execute(
            """
            INSERT INTO subscriptions (org_id, plan, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (org_id) DO UPDATE
            SET plan = EXCLUDED.plan, status = EXCLUDED.status
            """,
            (org["id"], plan, estado),
        )
        conn.execute(
            "INSERT INTO audit_log (org_id, action, target, metadata)"
            " VALUES (%s, 'billing.plan_set_manually', %s, %s)",
            (org["id"], plan, __import__("json").dumps({"estado": estado, "origen": "script"})),
        )
        conn.commit()

    info = PLANS[plan]
    print()
    print(f"Organizacion : {org['name']}  ({slug})")
    print(f"Plan         : {info.name}  {info.price_label}")
    print(f"Estado       : {estado}")
    print(f"Cuota        : {info.monthly_rows:,} filas al mes".replace(",", "."))
    print(f"Acceso a API : {'si' if info.api_access else 'no'}")
    print()
    print("Asignado a mano, sin pasar por Stripe. Queda registrado en audit_log.")
    print("Para devolverlo al plan gratuito:")
    print(f"  python scripts/set_plan.py --org {slug} --plan free --estado inactive")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Asigna un plan a una organizacion, solo para desarrollo."
    )
    parser.add_argument("--listar", action="store_true", help="Muestra las organizaciones.")
    parser.add_argument("--org", help="Identificador de la organizacion, su slug.")
    parser.add_argument("--plan", choices=sorted(PLANS), help="Plan a asignar.")
    parser.add_argument(
        "--estado", choices=ESTADOS, default="active", help="Estado de la suscripcion."
    )
    args = parser.parse_args()

    try:
        if args.listar:
            return listar()
        if not args.org or not args.plan:
            parser.print_help()
            return 2
        return asignar(args.org, args.plan, args.estado)
    except ConfigError as exc:
        print(f"Configuracion: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"{type(exc).__name__}: {str(exc).splitlines()[0]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
