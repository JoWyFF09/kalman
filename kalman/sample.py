"""Generación de datos de ejemplo con errores realistas.

Vive dentro del paquete y no en `scripts/` porque lo usa la demo pública, que
necesita poder ofrecer un fichero de prueba sin que el visitante tenga que
traer el suyo. Un botón que dice "probar con datos de ejemplo" convierte mucho
mejor que un formulario de subida vacío.

Los errores que se inyectan son los que aparecen de verdad en un volcado de
CRM español, no fallos inventados:

  - NIF y CIF con la letra o el dígito de control cambiado, que es lo que pasa
    al teclearlos a mano.
  - IBAN con dos cifras intercambiadas.
  - Códigos postales de Álava sin el cero inicial, comidos por Excel.
  - La misma empresa escrita como "S.L." y como "Sociedad Limitada".
  - Dominios de correo mal escritos.
"""

from __future__ import annotations

import random
import unicodedata

import pandas as pd

from .core.validators.iban import mod97
from .core.validators.identity import _cif_control, nif_control_letter

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

#: Proporción de filas con exactamente un defecto. Más de uno por fila hace la
#: demostración confusa y deja de parecerse a los datos reales.
DEFECT_RATE = 0.18

#: Proporción de filas que se repiten con la razón social escrita de otra
#: forma, que es como aparecen tras fusionar dos listas.
DUPLICATE_RATE = 0.06


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


def _ascii(texto: str) -> str:
    """Un dominio de correo real es ASCII.

    "peña.es" se registra como punycode, así que se transcribe aquí en vez de
    generar un email que el motor rechazaría con razón.
    """
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def generate(rows: int = 2000, seed: int = 42) -> pd.DataFrame:
    """Devuelve un DataFrame de clientes con defectos realistas."""
    rng = random.Random(seed)
    registros: list[dict[str, object]] = []

    for indice in range(rows):
        empresa_base = f"{rng.choice(GIROS)} {rng.choice(APELLIDOS)}"
        empresa = f"{empresa_base} {rng.choice(FORMAS)}"
        contacto = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        cif = cif_valido(rng)
        iban = iban_valido(rng)
        # El dominio incluye el índice para que los únicos duplicados del
        # fichero sean los que se inyectan a propósito más abajo. Sin esto, con
        # sólo diez giros y doce apellidos, los correos chocaban y el motor
        # detectaba miles de duplicados que no eran tales.
        dominio = _ascii(empresa_base.lower()).replace(" ", "")
        email = f"info@{dominio}{indice}.{rng.choice(['es', 'com'])}"
        telefono = f"{rng.choice('6789')}{rng.randint(0, 99_999_999):08d}"
        cp = f"{rng.randint(1, 52):02d}{rng.randint(0, 999):03d}"
        facturacion = round(rng.gauss(180_000, 90_000), 2)

        registro: dict[str, object] = {
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

        if rng.random() < DEFECT_RATE:
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

        if rng.random() < DUPLICATE_RATE:
            copia = dict(registro)
            copia["Nº Cliente"] = rows + indice + 1
            copia["Razón Social"] = f"{empresa_base.upper()} SOCIEDAD LIMITADA"
            copia["Correo electrónico"] = str(registro["Correo electrónico"]).upper()
            registros.append(copia)

    return pd.DataFrame(registros)
