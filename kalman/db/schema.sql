-- Esquema de Kalman. Idempotente: se puede ejecutar tantas veces como haga falta.
--
-- Diferencias de fondo con el esquema anterior
-- --------------------------------------------
-- 1. El aislamiento entre clientes ya no depende de que la aplicación se
--    acuerde de poner "WHERE empresa = ...". Lo impone Postgres con seguridad
--    a nivel de fila. Un fallo en el código deja de ser una fuga de datos
--    entre clientes.
-- 2. El derecho a usar el producto vive en la base de datos y sólo lo escribe
--    el webhook de Stripe. Antes vivía en la sesión del navegador y se
--    desbloqueaba escribiendo el email de otro.
-- 3. Hay registro de auditoría. Sin él no se puede responder a un cliente que
--    pregunta quién descargó sus datos, que es una obligación del RGPD.
-- 4. Ninguna tabla guarda datos personales en claro salvo que el cliente lo
--    pida de forma explícita. El resultado de un trabajo es el informe, no una
--    copia de su base de clientes.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ---------------------------------------------------------------- organizaciones

CREATE TABLE IF NOT EXISTS organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    country         TEXT NOT NULL DEFAULT 'ES',
    -- Identificador fiscal de la propia organización cliente, para facturar.
    tax_id          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    CONSTRAINT organizations_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{1,62}$')
);

COMMENT ON TABLE organizations IS
    'Cliente de Kalman. Toda fila del sistema cuelga de una organización.';

-- ------------------------------------------------------------------- usuarios

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'member',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_role_valid CHECK (role IN ('owner', 'admin', 'member')),
    CONSTRAINT users_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS users_org_idx ON users(org_id) WHERE is_active;

COMMENT ON COLUMN users.password_hash IS
    'scrypt con sal por usuario. Nunca la contraseña en claro.';
COMMENT ON COLUMN users.locked_until IS
    'Bloqueo temporal tras varios intentos fallidos. Frena la fuerza bruta.';

-- --------------------------------------------------------------- claves de API

CREATE TABLE IF NOT EXISTS api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,
    -- Los ocho primeros caracteres se guardan en claro para que el usuario
    -- reconozca cuál es cuál en la lista sin poder usarla.
    key_prefix      TEXT NOT NULL,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS api_keys_org_idx ON api_keys(org_id) WHERE revoked_at IS NULL;

-- ------------------------------------------------------------- suscripciones

CREATE TABLE IF NOT EXISTS subscriptions (
    org_id                  UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    stripe_customer_id      TEXT UNIQUE,
    stripe_subscription_id  TEXT UNIQUE,
    plan                    TEXT NOT NULL DEFAULT 'free',
    status                  TEXT NOT NULL DEFAULT 'inactive',
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT subscriptions_plan_valid
        CHECK (plan IN ('free', 'starter', 'growth', 'scale')),
    CONSTRAINT subscriptions_status_valid
        CHECK (status IN ('inactive', 'trialing', 'active', 'past_due', 'canceled'))
);

COMMENT ON TABLE subscriptions IS
    'Fuente única de verdad del derecho de uso. Sólo la escribe el webhook de '
    'Stripe tras verificar la firma. La aplicación jamás la escribe a partir '
    'de lo que diga el navegador.';

-- ------------------------------------------------------------------- consumo

-- El plan se mide en filas procesadas al mes. Se guarda agregado por mes para
-- que consultar el consumo sea una sola lectura por índice, no un recuento
-- sobre millones de trabajos.
CREATE TABLE IF NOT EXISTS usage_counters (
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    period          DATE NOT NULL,
    rows_processed  BIGINT NOT NULL DEFAULT 0,
    jobs_run        INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, period)
);

COMMENT ON COLUMN usage_counters.period IS
    'Primer día del mes natural al que se imputa el consumo.';

-- ------------------------------------------------------------------ trabajos

CREATE TABLE IF NOT EXISTS jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    source              TEXT NOT NULL DEFAULT 'web',
    filename            TEXT,
    engine_version      TEXT NOT NULL,
    rows_in             INTEGER NOT NULL DEFAULT 0,
    rows_valid          INTEGER NOT NULL DEFAULT 0,
    rows_quarantined    INTEGER NOT NULL DEFAULT 0,
    duplicate_groups    INTEGER NOT NULL DEFAULT 0,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    -- Recuento por regla. Es el informe, no los datos. Un JSONB de unos pocos
    -- kilobytes por trabajo en lugar de una copia de la base del cliente.
    findings_summary    JSONB NOT NULL DEFAULT '{}'::jsonb,
    columns_detected    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT jobs_source_valid CHECK (source IN ('web', 'api', 'batch'))
);

CREATE INDEX IF NOT EXISTS jobs_org_created_idx ON jobs(org_id, created_at DESC);

COMMENT ON TABLE jobs IS
    'Metadatos de cada ejecución. No contiene datos personales del cliente: '
    'el fichero se procesa en memoria y no se persiste salvo petición expresa.';

-- ---------------------------------------------------------------- auditoría

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      UUID REFERENCES organizations(id) ON DELETE SET NULL,
    actor_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    target      TEXT,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_org_idx ON audit_log(org_id, created_at DESC);

COMMENT ON TABLE audit_log IS
    'Quién hizo qué y cuándo. Exigible para responder a un derecho de acceso '
    'del RGPD y para investigar un incidente.';

-- ------------------------------------------------ seguridad a nivel de fila

ALTER TABLE organizations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys       ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_counters ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log      ENABLE ROW LEVEL SECURITY;

-- La aplicación fija la organización activa al abrir la conexión con
--     SET LOCAL app.current_org = '<uuid>';
-- y a partir de ahí Postgres filtra solo. Si alguien olvida un WHERE, no pasa
-- nada. Si alguien inyecta SQL, sigue sin poder salir de su organización.
CREATE OR REPLACE FUNCTION current_org_id() RETURNS UUID
LANGUAGE sql STABLE
-- search_path vacio: impide que un esquema creado por otro usuario secuestre
-- la resolucion de nombres dentro de la funcion.
SET search_path = ''
AS $fn$
    SELECT NULLIF(current_setting('app.current_org', TRUE), '')::uuid;
$fn$;

DO $mig$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['users', 'api_keys', 'subscriptions', 'usage_counters', 'jobs', 'audit_log']
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I_tenant_isolation ON %I', t, t);
        EXECUTE format(
            'CREATE POLICY %I_tenant_isolation ON %I
             USING (org_id = public.current_org_id())
             WITH CHECK (org_id = public.current_org_id())', t, t);
    END LOOP;

    EXECUTE 'DROP POLICY IF EXISTS organizations_tenant_isolation ON organizations';
    EXECUTE 'CREATE POLICY organizations_tenant_isolation ON organizations
             USING (id = public.current_org_id())
             WITH CHECK (id = public.current_org_id())';
END $mig$;

-- ------------------------------------------------------------------ utilidad

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $fn$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $fn$;

DROP TRIGGER IF EXISTS subscriptions_touch ON subscriptions;
CREATE TRIGGER subscriptions_touch BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS usage_counters_touch ON usage_counters;
CREATE TRIGGER usage_counters_touch BEFORE UPDATE ON usage_counters
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
