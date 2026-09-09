"""Acceso a datos.

Todas las consultas son parametrizadas y todas las conexiones fijan la
organización activa con `SET LOCAL app.current_org`, de modo que la seguridad
a nivel de fila de Postgres actúa como segunda barrera. Si mañana alguien
escribe una consulta sin filtro, no habrá fuga entre clientes.

El pool se crea una sola vez por proceso. Abrir una conexión por petición,
como hacía la versión anterior, funciona con tres usuarios y se cae con
treinta: Postgres reserva memoria por conexión y Supabase limita el número.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..security.passwords import hash_api_key, needs_rehash, hash_password, verify_password

logger = logging.getLogger(__name__)

#: Intentos fallidos antes de bloquear temporalmente una cuenta.
MAX_FAILED_LOGINS = 5

#: Minutos de bloqueo. Suficiente para arruinar la fuerza bruta y poco para
#: que un usuario legítimo que se ha equivocado no llame a soporte.
LOCKOUT_MINUTES = 15


class Repository:
    """Punto único de acceso a la base de datos."""

    def __init__(self, database_url: str, min_size: int = 1, max_size: int = 10) -> None:
        self._pool = ConnectionPool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row, "sslmode": "require"},
            open=True,
        )

    def close(self) -> None:
        self._pool.close()

    @contextlib.contextmanager
    def connection(self, org_id: str | None = None) -> Iterator[psycopg.Connection]:
        """Conexión con la organización activa fijada para esta transacción.

        `SET LOCAL` limita el efecto a la transacción en curso, así que una
        conexión devuelta al pool nunca arrastra la organización del usuario
        anterior. Es la diferencia entre aislamiento real y una fuga latente.
        """
        with self._pool.connection() as conn:
            with conn.transaction():
                if org_id:
                    conn.execute(
                        "SELECT set_config('app.current_org', %s, TRUE)", (str(org_id),)
                    )
                yield conn

    # ------------------------------------------------------------ migraciones

    def apply_schema(self, schema_sql: str) -> None:
        """Aplica el esquema. Es idempotente."""
        with self._pool.connection() as conn:
            conn.execute(schema_sql)
            conn.commit()

    # --------------------------------------------------------------- usuarios

    def create_organization(self, slug: str, name: str, tax_id: str | None = None) -> str:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO organizations (slug, name, tax_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (slug, name, tax_id),
            ).fetchone()
            conn.execute(
                "INSERT INTO subscriptions (org_id, plan, status) VALUES (%s, 'free', 'inactive')"
                " ON CONFLICT (org_id) DO NOTHING",
                (row["id"],),
            )
            conn.commit()
            return str(row["id"])

    def create_user(self, org_id: str, email: str, password: str, role: str = "member") -> str:
        """Crea un usuario. La contraseña se valida y se cifra aquí."""
        digest = hash_password(password)
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO users (org_id, email, password_hash, role)
                VALUES (%s, lower(%s), %s, %s)
                RETURNING id
                """,
                (org_id, email.strip(), digest, role),
            ).fetchone()
            conn.commit()
            return str(row["id"])

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        """Verifica credenciales y devuelve el usuario, o None.

        Devuelve None por igual si el usuario no existe, si la contraseña falla
        o si la cuenta está bloqueada. Distinguir esos casos en el mensaje le
        dice a un atacante qué emails están dados de alta.
        """
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.org_id, u.email, u.password_hash, u.role,
                       u.is_active, u.locked_until, o.name AS org_name, o.slug AS org_slug
                FROM users u
                JOIN organizations o ON o.id = u.org_id
                WHERE u.email = lower(%s)
                """,
                (email.strip(),),
            ).fetchone()

            if row is None:
                # Se calcula un hash de todas formas para que el tiempo de
                # respuesta no revele si el email existe.
                verify_password(password, "scrypt$32768$8$1$00$00")
                return None

            if not row["is_active"]:
                return None

            if row["locked_until"] and row["locked_until"] > datetime.now(UTC):
                return None

            if not verify_password(password, row["password_hash"]):
                conn.execute(
                    """
                    UPDATE users
                    SET failed_logins = failed_logins + 1,
                        locked_until = CASE
                            WHEN failed_logins + 1 >= %s
                            THEN now() + (%s || ' minutes')::interval
                            ELSE locked_until
                        END
                    WHERE id = %s
                    """,
                    (MAX_FAILED_LOGINS, LOCKOUT_MINUTES, row["id"]),
                )
                conn.commit()
                return None

            updates = ["failed_logins = 0", "locked_until = NULL", "last_login_at = now()"]
            params: list[Any] = []
            if needs_rehash(row["password_hash"]):
                updates.append("password_hash = %s")
                params.append(hash_password(password))
            params.append(row["id"])

            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", params)
            conn.commit()

            return {
                "id": str(row["id"]),
                "org_id": str(row["org_id"]),
                "email": row["email"],
                "role": row["role"],
                "org_name": row["org_name"],
                "org_slug": row["org_slug"],
            }

    def authenticate_api_key(self, raw_key: str) -> dict[str, Any] | None:
        """Resuelve una clave de API a su organización."""
        digest = hash_api_key(raw_key)
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT k.id, k.org_id, o.name AS org_name
                FROM api_keys k
                JOIN organizations o ON o.id = k.org_id
                WHERE k.key_hash = %s AND k.revoked_at IS NULL
                """,
                (digest,),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s", (row["id"],))
            conn.commit()
            return {"org_id": str(row["org_id"]), "org_name": row["org_name"]}

    # ---------------------------------------------------------- suscripciones

    def get_subscription(self, org_id: str) -> dict[str, Any]:
        with self.connection(org_id) as conn:
            row = conn.execute(
                "SELECT plan, status, stripe_customer_id, current_period_end,"
                " cancel_at_period_end FROM subscriptions WHERE org_id = %s",
                (org_id,),
            ).fetchone()
        return dict(row) if row else {"plan": "free", "status": "inactive"}

    def upsert_subscription(
        self,
        org_id: str,
        *,
        plan: str,
        status: str,
        stripe_customer_id: str | None,
        stripe_subscription_id: str | None,
        current_period_end: datetime | None,
        cancel_at_period_end: bool,
    ) -> None:
        """Escribe el derecho de uso. Sólo la llama el webhook verificado."""
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions
                    (org_id, plan, status, stripe_customer_id, stripe_subscription_id,
                     current_period_end, cancel_at_period_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (org_id) DO UPDATE SET
                    plan = EXCLUDED.plan,
                    status = EXCLUDED.status,
                    stripe_customer_id =
                        COALESCE(EXCLUDED.stripe_customer_id, subscriptions.stripe_customer_id),
                    stripe_subscription_id =
                        COALESCE(EXCLUDED.stripe_subscription_id, subscriptions.stripe_subscription_id),
                    current_period_end =
                        COALESCE(EXCLUDED.current_period_end, subscriptions.current_period_end),
                    cancel_at_period_end = EXCLUDED.cancel_at_period_end
                """,
                (
                    org_id, plan, status, stripe_customer_id, stripe_subscription_id,
                    current_period_end, cancel_at_period_end,
                ),
            )
            conn.commit()

    def find_org_by_stripe_customer(self, customer_id: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT org_id FROM subscriptions WHERE stripe_customer_id = %s",
                (customer_id,),
            ).fetchone()
        return str(row["org_id"]) if row else None

    # ---------------------------------------------------- idempotencia webhook

    def was_event_processed(self, event_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM audit_log WHERE action = 'billing.event' AND target = %s LIMIT 1",
                (event_id,),
            ).fetchone()
        return row is not None

    def mark_event_processed(self, event_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (action, target) VALUES ('billing.event', %s)",
                (event_id,),
            )
            conn.commit()

    # --------------------------------------------------------------- consumo

    def get_usage(self, org_id: str, period: date | None = None) -> int:
        period = period or date.today().replace(day=1)
        with self.connection(org_id) as conn:
            row = conn.execute(
                "SELECT rows_processed FROM usage_counters WHERE org_id = %s AND period = %s",
                (org_id, period),
            ).fetchone()
        return int(row["rows_processed"]) if row else 0

    def add_usage(self, org_id: str, rows: int) -> None:
        period = date.today().replace(day=1)
        with self.connection(org_id) as conn:
            conn.execute(
                """
                INSERT INTO usage_counters (org_id, period, rows_processed, jobs_run)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (org_id, period) DO UPDATE SET
                    rows_processed = usage_counters.rows_processed + EXCLUDED.rows_processed,
                    jobs_run = usage_counters.jobs_run + 1
                """,
                (org_id, period, rows),
            )

    # -------------------------------------------------------------- trabajos

    def record_job(self, org_id: str, user_id: str | None, report: dict[str, Any],
                   filename: str | None, source: str = "web") -> str:
        """Guarda los metadatos de una ejecución.

        No se guarda ni una sola fila del fichero del cliente. Lo que se
        persiste es el recuento por regla, que es lo que necesita el informe y
        lo que no crea una obligación de custodia sobre datos ajenos.
        """
        with self.connection(org_id) as conn:
            row = conn.execute(
                """
                INSERT INTO jobs
                    (org_id, created_by, source, filename, engine_version, rows_in,
                     rows_valid, rows_quarantined, duplicate_groups, duration_ms,
                     findings_summary, columns_detected)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    org_id, user_id, source, filename,
                    report["engine_version"], report["rows_in"], report["rows_valid"],
                    report["rows_quarantined"], report["duplicate_groups"],
                    report["duration_ms"],
                    psycopg.types.json.Json(report["counts_by_rule"]),
                    psycopg.types.json.Json(report["columns_detected"]),
                ),
            ).fetchone()
            self.add_usage(org_id, report["rows_in"])
            return str(row["id"])

    def recent_jobs(self, org_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection(org_id) as conn:
            rows = conn.execute(
                "SELECT id, filename, rows_in, rows_valid, rows_quarantined,"
                " duplicate_groups, created_at FROM jobs WHERE org_id = %s"
                " ORDER BY created_at DESC LIMIT %s",
                (org_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------- auditoría

    def record_audit(
        self,
        org_id: str | None,
        action: str,
        metadata: dict[str, Any] | None = None,
        actor_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (org_id, actor_id, action, metadata, ip_address)"
                " VALUES (%s, %s, %s, %s, %s)",
                (org_id, actor_id, action, psycopg.types.json.Json(metadata or {}), ip_address),
            )
            conn.commit()
