"""Genera un fichero de ejemplo con errores realistas.

Sirve para dos cosas: probar el motor y, sobre todo, enseñar el producto en una
llamada. Un fichero de demostración con errores que el cliente reconoce como
los suyos convence mucho más que uno con edades de 150 años.

Los errores que se inyectan son los que aparecen de verdad en un volcado de
CRM español, no fallos inventados:

  - NIF y CIF con la letra o el dígito de control cambiado, que es lo que pasa
    al teclearlos a mano.
  - IBAN con dos cifras intercambiadas.
  - Códigos postales de Álava sin el cero inicial, comidos por Excel.
  - La misma empresa escrita como "S.L." y como "Sociedad Limitada".
  - Dominios de correo mal escritos.

    python scripts/generate_sample.py --filas 2000 --salida ejemplo.csv
"""

from __future__ import annotations

import argparse
import random
import sys
import unicodedata
from pathlib import Path

import pandas as pd

# Permite ejecutar el script directamente desde la raíz del proyecto sin
# haberlo instalado antes con pip.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalman.core.validators.iban import mod97  # noqa: E402
from kalman.core.validators.identity import _cif_control, nif_control_letter

FORMAS = ["S.L.", "Sociedad Limitada", "SL", "S.A.", "SLU"]
GIROS = [
    "Talleres", "Construcciones", "Panaderia", "Asesoria", "Transportes",
    "Distribuciones", "Informatica", "Reformas", "Clinica", "Gestoria",
]
APELLIDOS = [
    "Gomez", "Rodriguez", "Fernandez", "Lopez", "Martinez", "Sanchez",
    "Perez", "Garcia", "Muñoz", "Peña", "Ruiz", "Diaz",
]
NOMBRES = ["Joel", "Maria", "Carlos", "Ana", "Javier", "Lucia", "Miguel", "Carmen"]
DOMINIOS = ["gmail.com", "hotmail.com", "empresa.es", "outlook.com"]


def nif_valido(rng: random.Random) -> str:
    number = rng.randint(10_000_000, 99_999_999)
    return f"{number:08d}{nif_control_letter(number)}"


def cif_valido(rng: random.Random) -> str:
    letra = rng.choice("ABEH")
    digitos = f"{rng.randint(0, 9_999_999):07d}"
    return f"{letra}{digitos}{_cif_control(digitos)}"


def iban_valido(rng: random.Random) -> str:
    """Construye un IBAN español que pasa el módulo 97."""
    cuerpo = f"{rng.randint(0, 10**20 - 1):020d}"
    for control in range(1, 100):
        candidato = f"ES{control:02d}{cuerpo}"
        if mod97(candidato) == 1:
            return candidato
    raise RuntimeError("No se ha encontrado un dígito de control válido.")


def romper_control(identificador: str) -> str:
    """Cambia el último carácter, que es el error humano más frecuente."""
    ultimo = identificador[-1]
    if ultimo.isdigit():
        return identificador[:-1] + str((int(ultimo) + 1) % 10)
    return identificador[:-1] + chr((ord(ultimo) - 65 + 1) % 26 + 65)


def transponer(texto: str, posicion: int = 10) -> str:
    """Intercambia dos cifras contiguas, el otro error clásico al copiar."""
    chars = list(texto)
    chars[posicion], chars[posicion + 1] = chars[posicion + 1], chars[posicion]
    return "".join(chars)


def generar(filas: int, semilla: int = 42) -> pd.DataFrame:
    rng = random.Random(semilla)
    registros: list[dict[str, object]] = []

    for indice in range(filas):
        empresa_base = f"{rng.choice(GIROS)} {rng.choice(APELLIDOS)}"
        empresa = f"{empresa_base} {rng.choice(FORMAS)}"
        contacto = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        cif = cif_valido(rng)
        iban = iban_valido(rng)
        # El dominio incluye el índice para que los únicos duplicados del
        # fichero sean los que se inyectan a propósito más abajo. Sin esto, con
        # sólo diez giros y doce apellidos, los correos chocaban y el motor
        # detectaba miles de duplicados que no eran tales.
        # Un dominio de correo real es ASCII. "peña.es" se registra como
        # punycode, así que se transcribe aquí en vez de generar un email que
        # el motor rechazaría con razón.
        dominio = (
            unicodedata.normalize("NFKD", empresa_base.lower())
            .encode("ascii", "ignore")
            .decode()
            .replace(" ", "")
        )
        email = f"info@{dominio}{indice}.{rng.choice(['es', 'com'])}"
        telefono = f"{rng.choice('6789')}{rng.randint(0, 99_999_999):08d}"
        cp = f"{rng.randint(1, 52):02d}{rng.randint(0, 999):03d}"
        facturacion = round(rng.gauss(180_000, 90_000), 2)

        registro = {
            "Nº Cliente": indice + 1,
            "Razón Social": empresa,
            "Persona de contacto": contacto,
            "CIF": cif,
            "Correo electrónico": email,
            "Teléfono": telefono,
            "Cuenta bancaria": iban,
            "CP": cp,
            "Facturación anual": facturacion,
        }

        # Un 18% de filas con exactamente un defecto. Más de uno por fila hace
        # la demostración confusa y no se parece a los datos reales.
        if rng.random() < 0.18:
            fallo = rng.choice([
                "cif", "iban", "email", "telefono", "cp", "facturacion", "contacto",
            ])
            if fallo == "cif":
                registro["CIF"] = romper_control(cif)
            elif fallo == "iban":
                registro["Cuenta bancaria"] = transponer(iban)
            elif fallo == "email":
                registro["Correo electrónico"] = rng.choice([
                    email.replace(".com", ".con").replace(".es", ".con"),
                    "no_email.com",
                    "",
                ])
            elif fallo == "telefono":
                registro["Teléfono"] = rng.choice(["111111111", "12345", ""])
            elif fallo == "cp":
                # El cero comido por Excel, sólo en provincias del 01 al 09.
                registro["CP"] = str(int(cp)) if cp.startswith("0") else "99999"
            elif fallo == "facturacion":
                registro["Facturación anual"] = rng.choice([-5000, 25_000_000, None])
            else:
                registro["Persona de contacto"] = rng.choice([
                    contacto + str(rng.randint(1, 99)), "TEST", "aaaa", "",
                ])

        registros.append(registro)

        # Un 6% de duplicados con la forma societaria escrita de otra manera,
        # que es como aparecen de verdad tras fusionar dos listas.
        if rng.random() < 0.06:
            copia = dict(registro)
            copia["Nº Cliente"] = filas + indice + 1
            copia["Razón Social"] = f"{empresa_base.upper()} SOCIEDAD LIMITADA"
            copia["Correo electrónico"] = str(registro["Correo electrónico"]).upper()
            registros.append(copia)

    return pd.DataFrame(registros)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un CSV de ejemplo.")
    parser.add_argument("--filas", type=int, default=2000)
    parser.add_argument("--salida", default="ejemplo_clientes.csv")
    parser.add_argument("--semilla", type=int, default=42)
    args = parser.parse_args()

    df = generar(args.filas, args.semilla)
    df.to_csv(args.salida, index=False)
    print(f"Escritas {len(df):,} filas en {args.salida}".replace(",", "."))
    print("Pruébalo con:")
    print(f"  python -m kalman.cli clean {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
