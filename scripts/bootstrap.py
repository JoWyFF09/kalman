"""Prepara la base de datos y crea la primera organización.

    python scripts/bootstrap.py --org "Mi Empresa" --email tu@correo.com

La contraseña se pide por consola y no se pasa como argumento: los argumentos
quedan en el historial del intérprete de comandos y en la lista de procesos,
donde los ve cualquiera con acceso a la máquina.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
import unicodedata
from pathlib import Path

# Permite ejecutar el script directamente desde la raíz del proyecto sin
# haberlo instalado antes con pip.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalman.config import ConfigError, get_settings  # noqa: E402
from kalman.db import Repository, load_schema  # noqa: E402
from kalman.security.passwords import WeakPasswordError, generate_api_key  # noqa: E402


def slugify(name: str) -> str:
    """Convierte un nombre de empresa en un identificador de URL."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return slug[:63] or "organizacion"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inicializa Kalman.")
    parser.add_argument("--org", required=True, help="Nombre de la organización.")
    parser.add_argument("--email", required=True, help="Email del primer usuario.")
    parser.add_argument("--tax-id", help="NIF o CIF de la organización, para facturar.")
    parser.add_argument(
        "--solo-esquema", action="store_true",
        help="Aplica el esquema y no crea nada más.",
    )
    args = parser.parse_args()

    try:
        settings = get_settings()
    except ConfigError as exc:
        print(f"Configuración incompleta: {exc}", file=sys.stderr)
        return 2

    repository = Repository(settings.database_url)

    print("Aplicando el esquema...")
    repository.apply_schema(load_schema())
    print("Esquema aplicado. Seguridad a nivel de fila activa.")

    if args.solo_esquema:
        return 0

    password = getpass.getpass("Contraseña del primer usuario: ")
    if password != getpass.getpass("Repítela: "):
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1

    slug = slugify(args.org)
    try:
        org_id = repository.create_organization(slug, args.org, args.tax_id)
        user_id = repository.create_user(org_id, args.email, password, role="owner")
    except WeakPasswordError as exc:
        print(f"Contraseña rechazada: {exc}", file=sys.stderr)
        return 1

    raw_key, digest = generate_api_key()
    with repository.connection(org_id) as conn:
        conn.execute(
            "INSERT INTO api_keys (org_id, name, key_hash, key_prefix, created_by)"
            " VALUES (%s, %s, %s, %s, %s)",
            (org_id, "Clave inicial", digest, raw_key[:12], user_id),
        )

    repository.record_audit(org_id, "org.created", {"slug": slug}, actor_id=user_id)

    print()
    print(f"Organización creada:  {args.org}  ({slug})")
    print(f"Identificador:        {org_id}")
    print(f"Usuario:              {args.email}")
    print()
    print("Clave de API. Se muestra una sola vez, guárdala ahora:")
    print(f"  {raw_key}")
    print()
    print("Siguientes pasos:")
    print("  1. Revisa que todo responda:")
    print("       python scripts/doctor.py")
    print("  2. Arranca la aplicacion:")
    print("       python -m streamlit run kalman/web/app.py --server.port 8502")
    print("  3. Antes de cobrar a nadie, crea el webhook de Stripe.")
    print("     Esta explicado en docs/PUESTA_EN_MARCHA.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
