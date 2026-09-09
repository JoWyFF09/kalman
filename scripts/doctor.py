"""Revisa que la configuración esté completa y que todo responda.

    python scripts/doctor.py

Dice, en castellano, qué falta y qué hay que hacer. Existe para que un fallo de
configuración se vea en diez segundos y no en mitad de una demostración delante
de un cliente.

No imprime ninguna contraseña ni ninguna clave. Sólo dice si están y si
funcionan.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalman.config import load_dotenv  # noqa: E402

OK = "  [OK]   "
FALTA = "  [FALTA]"
AVISO = "  [AVISO]"

pendientes: list[str] = []


def titulo(texto: str) -> None:
    print()
    print(texto)
    print("-" * len(texto))


def revisar_fichero() -> bool:
    raiz = Path(__file__).resolve().parent.parent
    env = raiz / ".env"
    titulo("1. Fichero de configuracion")

    if not env.is_file():
        print(f"{FALTA} No existe {env}")
        print("         Copia .env.example a .env y rellenalo.")
        pendientes.append("crear el fichero .env")
        return False

    leidas = load_dotenv(env)
    print(f"{OK} Encontrado. Variables leidas: {leidas}")
    return True


def revisar_variables() -> None:
    import os

    titulo("2. Valores obligatorios")

    comprobaciones = [
        ("DATABASE_URL", "la cadena de conexion de Supabase", 20),
        ("KALMAN_PSEUDONYM_KEY", "la clave de seudonimizacion", 32),
        ("STRIPE_SECRET_KEY", "la clave secreta de Stripe", 10),
        ("STRIPE_WEBHOOK_SECRET", "el secreto del webhook", 5),
    ]

    for nombre, descripcion, minimo in comprobaciones:
        valor = os.environ.get(nombre, "").strip()
        if not valor:
            print(f"{FALTA} {nombre}: vacio. Falta {descripcion}.")
            pendientes.append(f"rellenar {nombre}")
        elif len(valor) < minimo:
            print(f"{FALTA} {nombre}: parece incompleto, solo {len(valor)} caracteres.")
            pendientes.append(f"revisar {nombre}")
        else:
            print(f"{OK} {nombre}: presente ({len(valor)} caracteres)")

    clave = os.environ.get("STRIPE_SECRET_KEY", "")
    if clave.startswith("sk_live_"):
        print(f"{AVISO} Estas usando la clave REAL de Stripe.")
        print("         En local es mas seguro la de pruebas, la que empieza por sk_test_.")
    elif clave.startswith("sk_test_"):
        print(f"{OK} Clave de Stripe en modo de pruebas. No se puede cobrar de verdad.")


def revisar_base_de_datos() -> None:
    import os

    titulo("3. Conexion con la base de datos")

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print(f"{FALTA} Sin DATABASE_URL no se puede probar.")
        return

    if "[YOUR-PASSWORD]" in url or "TUCONTRASENA" in url:
        print(f"{FALTA} No has sustituido el hueco de la contrasena en la cadena.")
        pendientes.append("poner la contrasena real en DATABASE_URL")
        return

    try:
        import psycopg
    except ImportError:
        print(f"{AVISO} psycopg no esta instalado. Instala con:")
        print('         pip install -e ".[db]"')
        return

    try:
        with psycopg.connect(url, connect_timeout=15) as conn:
            fila = conn.execute(
                "SELECT count(*) FROM information_schema.tables"
                " WHERE table_schema = 'public'"
            ).fetchone()
            tablas = fila[0] if fila else 0
        print(f"{OK} Conectado. Tablas en el esquema publico: {tablas}")
        if tablas < 7:
            print(f"{AVISO} Se esperaban 7 tablas. Aplica el esquema con:")
            print("         python scripts/bootstrap.py --solo-esquema --org x --email x@x.com")
    except Exception as exc:
        print(f"{FALTA} No se ha podido conectar.")
        print(f"         {type(exc).__name__}: {str(exc).strip().splitlines()[0][:160]}")
        print("         Revisa la contrasena y que la copiaste entera desde Supabase.")
        pendientes.append("arreglar la conexion a la base de datos")


def revisar_stripe() -> None:
    import os

    titulo("4. Conexion con Stripe")

    clave = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not clave:
        print(f"{FALTA} Sin STRIPE_SECRET_KEY no se puede probar.")
        return

    try:
        import stripe
    except ImportError:
        print(f"{AVISO} stripe no esta instalado. Instala con:")
        print('         pip install -e ".[billing]"')
        return

    try:
        cliente = stripe.StripeClient(clave)
        productos = cliente.products.list(params={"limit": 3})
        print(f"{OK} Clave valida. Productos visibles: {len(productos.data)}")
        for producto in productos.data:
            print(f"         - {producto.name}")
        if not productos.data:
            print(f"{AVISO} No hay productos en este modo de Stripe.")
            print("         Con la clave de pruebas es normal: los precios estan")
            print("         creados en el modo real. Los botones de pago daran error.")
    except Exception as exc:
        print(f"{FALTA} La clave no funciona.")
        print(f"         {type(exc).__name__}: {str(exc).strip().splitlines()[0][:160]}")
        pendientes.append("revisar la clave de Stripe")


def revisar_motor() -> None:
    titulo("5. Motor de limpieza")
    try:
        from kalman.core.engine import CleaningEngine
        from kalman.sample import generate

        resultado = CleaningEngine().run(generate(rows=200, seed=1))
        informe = resultado.report
        print(f"{OK} Motor {informe.engine_version} funcionando.")
        print(f"         {informe.rows_in} filas en {informe.duration_ms} ms, "
              f"{informe.rows_quarantined} en cuarentena.")
    except Exception as exc:
        print(f"{FALTA} El motor ha fallado: {type(exc).__name__}: {exc}")
        pendientes.append("revisar la instalacion del motor")


def main() -> int:
    print()
    print("=" * 62)
    print("  Kalman - revision de configuracion")
    print("=" * 62)

    if revisar_fichero():
        revisar_variables()
        revisar_base_de_datos()
        revisar_stripe()
    revisar_motor()

    titulo("Resumen")
    if not pendientes:
        print(f"{OK} Todo listo. Arranca la aplicacion con:")
        print("         python -m streamlit run kalman/web/app.py --server.port 8502")
        print()
        return 0

    print("  Te queda por hacer:")
    for i, tarea in enumerate(pendientes, start=1):
        print(f"    {i}. {tarea}")
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
