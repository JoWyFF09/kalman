"""Pruebas de regresión sobre los tipos que produce pandas al leer un CSV.

Los tres fallos de este fichero no aparecieron escribiendo pruebas: aparecieron
al ejecutar el motor contra un fichero de tres mil filas generado con errores
realistas. Ninguno se veía con datos escritos a mano en una prueba.

Se dejan aquí para que no vuelvan.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kalman.core.engine import CleaningEngine, CleanOptions
from kalman.core.normalize import normalize_key, text_value
from kalman.core.schema_map import detect_schema
from kalman.core.validators.contact import validate_phone_es, validate_postal_code_es
from kalman.core.validators.identity import validate_tax_id


# --------------------------------------------------- columna numérica con nulos

@pytest.mark.parametrize(
    "value,expected",
    [
        (612345678.0, "612345678"),
        (612345678, "612345678"),
        ("612345678.0", "612345678"),
        ("612345678", "612345678"),
        (float("nan"), ""),
        (None, ""),
        ("nan", ""),
        ("  ", ""),
        (28001.0, "28001"),
        (1234.56, "1234.56"),
    ],
)
def test_text_value_deshace_la_conversion_a_coma_flotante(
    value: object, expected: str
) -> None:
    assert text_value(value) == expected


def test_telefono_leido_como_flotante_sigue_siendo_valido() -> None:
    """El fallo: un hueco en la columna convierte todos los teléfonos a float.

    612345678 pasaba a 612345678.0, que al limpiar deja diez dígitos, y el
    motor marcaba como inválidos todos los teléfonos del fichero.
    """
    assert validate_phone_es(612345678.0).ok
    assert validate_phone_es(612345678.0).normalized == "+34612345678"


def test_columna_de_telefonos_con_un_hueco() -> None:
    """Reproduce la situación completa, desde el CSV."""
    df = pd.DataFrame({"Teléfono": [612345678, 677889900, None]})
    assert df["Teléfono"].dtype == np.float64  # así lo tipa pandas

    resultado = CleaningEngine().run(df, CleanOptions(detect_duplicates=False))
    reglas = resultado.report.counts_by_rule()

    assert reglas.get("phone.format_es", 0) == 0
    assert reglas.get("phone.missing", 0) == 1


def test_codigo_postal_leido_como_flotante() -> None:
    assert validate_postal_code_es(28001.0).ok
    assert validate_postal_code_es(28001.0).normalized == "28001"


def test_nif_leido_desde_columna_mixta() -> None:
    assert validate_tax_id("12345678Z").ok
    assert not validate_tax_id(float("nan")).ok
    assert validate_tax_id(float("nan")).rule == "tax_id.missing"


# ------------------------------------------- cabecera que reclama campo ajeno

def test_numero_de_cliente_no_se_apropia_del_nombre() -> None:
    """El fallo: "Nº Cliente" contiene "cliente", sinónimo del campo nombre.

    Esa columna se quedaba con el campo nombre y luego sus valores numéricos
    se marcaban como nombres falsos, uno por fila.
    """
    columnas = ["Nº Cliente", "Persona de contacto"]
    muestras = {
        "Nº Cliente": [1, 2, 3, 4, 5],
        "Persona de contacto": ["Ana Gomez", "Luis Ruiz", "Eva Diaz", "Jon Paz", "Iker Sanz"],
    }
    mapeo, _, _ = detect_schema(columnas, muestras)

    assert mapeo.get("Persona de contacto") == "name"
    assert mapeo.get("Nº Cliente") != "name"


def test_el_indicador_ordinal_se_normaliza() -> None:
    assert normalize_key("Nº Cliente") == "n cliente"
    assert normalize_key("1ª Factura") == "1 factura"


def test_una_columna_numerica_no_puede_ser_razon_social() -> None:
    columnas = ["Empresa"]
    muestras = {"Empresa": [101, 102, 103, 104, 105]}
    mapeo, _, sin_mapear = detect_schema(columnas, muestras)

    assert "Empresa" not in mapeo
    assert "Empresa" in sin_mapear


def test_una_columna_de_texto_si_puede_ser_razon_social() -> None:
    """El guardián no puede volverse tan estricto que rechace lo correcto."""
    columnas = ["Empresa"]
    muestras = {"Empresa": ["Talleres Gomez SL", "Panaderia Sur SA", "Asesoria Norte SL"]}
    mapeo, _, _ = detect_schema(columnas, muestras)

    assert mapeo.get("Empresa") == "company"


def test_sin_muestras_suficientes_no_se_rechaza() -> None:
    """Con dos filas no hay evidencia para contradecir la cabecera."""
    mapeo, _, _ = detect_schema(["Empresa"], {"Empresa": [1, 2]})
    assert mapeo.get("Empresa") == "company"


# -------------------------------------------------- fichero realista completo

def test_fichero_realista_no_marca_todo_como_invalido() -> None:
    """Prueba de cordura general.

    Con datos mayoritariamente correctos, la inmensa mayoría de las filas debe
    salir limpia. Que salieran cero era el síntoma de los tres fallos.
    """
    filas = 200
    df = pd.DataFrame({
        "Nº Cliente": list(range(1, filas + 1)),
        "Razón Social": [f"Talleres Numero {i} SL" for i in range(filas)],
        "Persona de contacto": [f"Ana Gomez Ruiz" for _ in range(filas)],
        "CIF": ["A58818501"] * filas,
        "Correo electrónico": [f"info{i}@empresa{i}.es" for i in range(filas)],
        "Teléfono": [600000000 + i for i in range(filas)],
        "CP": [28001] * filas,
    })
    # Un hueco, que es lo que fuerza la conversión a coma flotante.
    df.loc[0, "Teléfono"] = None

    resultado = CleaningEngine().run(df, CleanOptions(detect_duplicates=False))

    assert resultado.report.rows_valid >= filas - 5
    assert resultado.report.counts_by_rule().get("name.synthetic", 0) == 0


# ------------------------------------- columnas homogeneas para poder pintarlas

def test_la_columna_corregida_queda_toda_en_texto() -> None:
    """Regresion, vista en produccion.

    Al corregir el CP de Alava la columna quedaba mezclada: unos valores
    enteros y otros cadenas. Eso rompia el pintado de la tabla y, peor, al
    exportar el CSV las filas no corregidas volvian a perder el cero inicial.
    """
    df = pd.DataFrame({"CP": [1001, 28001, 8001], "Email": ["a@b.com"] * 3})
    resultado = CleaningEngine().run(df)
    todos = pd.concat([resultado.valid, resultado.quarantine])

    tipos = {type(v).__name__ for v in todos["CP"] if v is not None}
    assert tipos == {"str"}, f"la columna quedo mezclada: {tipos}"
    assert set(todos["CP"]) == {"01001", "28001", "08001"}


def test_la_tabla_corregida_se_puede_pintar() -> None:
    """Reproduce exactamente lo que hace Streamlit al mostrar un DataFrame.

    Streamlit serializa a Arrow, y una columna con enteros y cadenas a la vez
    lanza ArrowInvalid. En produccion salia:

        Could not convert '05046' with type str: tried to convert to int64
    """
    pa = pytest.importorskip("pyarrow", reason="Streamlit usa pyarrow para pintar.")

    df = pd.DataFrame({
        "CP": [1001, 28001, 8001, 2001],
        "Telefono": [612345678, 677889900, 600111222, None],
        "Email": ["a@b.com"] * 4,
    })
    resultado = CleaningEngine().run(df, CleanOptions(detect_duplicates=False))

    for tabla in (resultado.valid, resultado.quarantine):
        if not tabla.empty:
            pa.Table.from_pandas(tabla, preserve_index=False)


def test_los_huecos_siguen_siendo_huecos() -> None:
    """Un `astype(str)` a secas convertiria el vacio en la cadena "nan".

    Eso acaba impreso tal cual en el CSV que se lleva el cliente, y ademas
    deja de contarse como dato ausente. Se comprueba lo que de verdad importa:
    que el hueco siga siendo un hueco y que no aparezca escrito en el fichero.
    """
    df = pd.DataFrame({"CP": [1001, None, 28001], "Email": ["a@b.com"] * 3})
    resultado = CleaningEngine().run(df, CleanOptions(detect_duplicates=False))
    todos = pd.concat([resultado.valid, resultado.quarantine])

    assert todos["CP"].isna().sum() == 1
    assert "nan" not in todos.to_csv(index=False).lower()


def test_una_columna_sin_correcciones_no_se_convierte() -> None:
    """Convertir a texto lo que nadie ha tocado estropearia los importes."""
    df = pd.DataFrame({"Facturacion": [120000.5, 85000.0], "CP": ["28001", "08001"]})
    resultado = CleaningEngine().run(df, CleanOptions(detect_duplicates=False))
    todos = pd.concat([resultado.valid, resultado.quarantine])

    assert pd.api.types.is_numeric_dtype(todos["Facturacion"])
