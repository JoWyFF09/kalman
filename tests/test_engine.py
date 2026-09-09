"""Pruebas de integración del motor completo."""

from __future__ import annotations

import pandas as pd
import pytest

from kalman.core.engine import CleaningEngine, CleanOptions
from kalman.core.pseudonymize import Pseudonymizer
from kalman.core.types import Severity

CLAVE_DE_PRUEBA = "clave-solo-para-tests-no-usar-en-produccion-1234567890"


@pytest.fixture
def datos_reales() -> pd.DataFrame:
    """Un fichero como los que llegan de verdad: columnas en español,
    mayúsculas inconsistentes, un NIF mal, un IBAN mal y un duplicado.
    """
    return pd.DataFrame(
        {
            "Nº Cliente": [1, 2, 3, 4, 5],
            "Razón Social": [
                "Talleres Gómez S.L.",
                "TALLERES GOMEZ SOCIEDAD LIMITADA",
                "Panadería  Central   SA",
                "Cliente7777",
                "Construcciones Sur SL",
            ],
            "CIF": ["A58818501", "A58818501", "B65410011", "A58818500", "12345678Z"],
            "Correo electrónico": [
                "info@gomez.es",
                "INFO@GOMEZ.ES",
                "hola@panaderia.com",
                "no_email.com",
                "ventas@gmail.con",
            ],
            "Tlf": ["600123456", "+34 600 12 34 56", "912345678", "111111111", "677889900"],
            "Cuenta bancaria": [
                "ES9121000418450200051332",
                "ES91 2100 0418 4502 0005 1332",
                "ES9121000418450200051333",
                "",
                "ES9121000418450200051332",
            ],
            "CP": ["28001", "28001", "08001", "99999", "28001"],
            "Facturación": [120000.0, 120000.0, 85000.0, -5000.0, 95000.0],
        }
    )


def test_detecta_el_esquema_sin_configuracion(datos_reales: pd.DataFrame) -> None:
    """Ningún cliente debería tener que decirle al motor cómo se llaman sus columnas."""
    resultado = CleaningEngine().run(datos_reales)
    detectado = set(resultado.report.columns_detected.values())

    for campo in ("company", "tax_id", "email", "phone", "iban", "postal_code", "income"):
        assert campo in detectado, f"No se detectó {campo}"


def test_cif_invalido_manda_la_fila_a_cuarentena(datos_reales: pd.DataFrame) -> None:
    resultado = CleaningEngine().run(datos_reales)
    reglas = resultado.report.counts_by_rule()
    assert reglas.get("tax_id.cif.checksum", 0) == 1
    assert resultado.report.rows_quarantined >= 1


def test_iban_invalido_se_detecta(datos_reales: pd.DataFrame) -> None:
    resultado = CleaningEngine().run(datos_reales)
    assert resultado.report.counts_by_rule().get("iban.checksum", 0) == 1


def test_telefono_se_normaliza_a_e164(datos_reales: pd.DataFrame) -> None:
    resultado = CleaningEngine().run(datos_reales)
    telefonos = set(resultado.valid["Tlf"].tolist())
    assert "+34600123456" in telefonos


def test_encuentra_el_duplicado(datos_reales: pd.DataFrame) -> None:
    """Las filas 0 y 1 son la misma empresa escrita de dos formas."""
    resultado = CleaningEngine().run(datos_reales)
    assert resultado.report.duplicate_groups >= 1
    grupo = resultado.duplicates[0]
    assert 0 in grupo.rows and 1 in grupo.rows


def test_las_filas_validas_y_en_cuarentena_suman_el_total(datos_reales: pd.DataFrame) -> None:
    """Invariante fundamental: no se pierde ni se inventa ninguna fila."""
    resultado = CleaningEngine().run(datos_reales)
    assert resultado.report.rows_valid + resultado.report.rows_quarantined == len(datos_reales)
    assert len(resultado.valid) + len(resultado.quarantine) == len(datos_reales)


def test_columnas_desconocidas_se_conservan() -> None:
    """Perder una columna del cliente sería inaceptable."""
    df = pd.DataFrame({
        "Email": ["a@b.com"],
        "Campo_Interno_Raro": ["valor que importa al cliente"],
    })
    resultado = CleaningEngine().run(df)
    assert "Campo_Interno_Raro" in resultado.valid.columns
    assert resultado.valid["Campo_Interno_Raro"].iloc[0] == "valor que importa al cliente"


def test_cada_hallazgo_es_explicable(datos_reales: pd.DataFrame) -> None:
    """Ningún hallazgo puede llegar al cliente sin regla ni mensaje."""
    resultado = CleaningEngine().run(datos_reales)
    assert resultado.report.findings
    for hallazgo in resultado.report.findings:
        assert hallazgo.rule
        assert hallazgo.message or hallazgo.severity is Severity.INFO
        assert 0.0 <= hallazgo.confidence <= 1.0
        assert hallazgo.as_dict()["rule"] == hallazgo.rule


def test_el_informe_no_estima_ahorro_economico(datos_reales: pd.DataFrame) -> None:
    """El motor informa de lo que mide, no inventa euros.

    Esta prueba existe para que nadie vuelva a colar un "ahorro estimado" en el
    informe sin datos del cliente que lo respalden.
    """
    informe = CleaningEngine().run(datos_reales).report.as_dict()
    texto = str(informe).lower()
    for prohibido in ("ahorro", "eur", "euro", "saving", "roi"):
        assert prohibido not in texto


def test_sin_normalizar_no_se_toca_el_dato(datos_reales: pd.DataFrame) -> None:
    """Modo auditoría: se informa de todo y no se modifica nada."""
    opciones = CleanOptions(apply_normalizations=False)
    resultado = CleaningEngine().run(datos_reales, opciones)
    original = set(datos_reales["Tlf"].tolist())
    salida = set(resultado.valid["Tlf"].tolist()) | set(resultado.quarantine["Tlf"].tolist())
    assert salida <= original


def test_seudonimizacion_es_estable_y_dependiente_de_la_organizacion() -> None:
    """El mismo dato da el mismo seudónimo, y distinta empresa da otro distinto."""
    uno = Pseudonymizer(CLAVE_DE_PRUEBA, "org_a")
    otro = Pseudonymizer(CLAVE_DE_PRUEBA, "org_b")

    assert uno.token("joel@x.com", "email") == uno.token("JOEL@X.COM ", "email")
    assert uno.token("joel@x.com", "email") != otro.token("joel@x.com", "email")
    assert uno.token("joel@x.com", "email") != uno.token("joel@x.com", "name")


def test_seudonimizacion_rechaza_clave_debil() -> None:
    with pytest.raises(ValueError, match="32 caracteres"):
        Pseudonymizer("corta", "org")


def test_seudonimizar_sin_clave_falla_en_vez_de_filtrar(datos_reales: pd.DataFrame) -> None:
    """Preferimos un error ruidoso a exportar datos personales en claro."""
    with pytest.raises(ValueError, match="sin configurar la clave"):
        CleaningEngine().run(datos_reales, CleanOptions(pseudonymize=True))


def test_seudonimizacion_borra_el_dato_original(datos_reales: pd.DataFrame) -> None:
    motor = CleaningEngine(Pseudonymizer(CLAVE_DE_PRUEBA, "org_a"))
    resultado = motor.run(datos_reales, CleanOptions(pseudonymize=True))
    correos = " ".join(str(v) for v in resultado.valid["Correo electrónico"].tolist())
    assert "@" not in correos


def test_enmascarado_conserva_la_forma(datos_reales: pd.DataFrame) -> None:
    resultado = CleaningEngine().run(datos_reales, CleanOptions(mask_output=True))
    correos = resultado.valid["Correo electrónico"].tolist()
    assert all("*" in str(c) and "@" in str(c) for c in correos)


def test_dataframe_vacio_no_rompe() -> None:
    resultado = CleaningEngine().run(pd.DataFrame())
    assert resultado.report.rows_in == 0
    assert resultado.valid.empty


def test_dataframe_sin_columnas_reconocibles() -> None:
    df = pd.DataFrame({"aaa": [1, 2], "bbb": ["x", "y"]})
    resultado = CleaningEngine().run(df)
    assert resultado.report.rows_valid == 2
    assert len(resultado.report.unmapped_columns) == 2


def test_el_informe_incluye_la_version_del_motor(datos_reales: pd.DataFrame) -> None:
    """Sin versión no hay auditoría reproducible."""
    informe = CleaningEngine().run(datos_reales).report
    assert informe.engine_version == CleaningEngine.version


def test_cero_perdido_en_columna_entera_no_rompe() -> None:
    """Regresión.

    Excel guarda el CP de Álava como el número 1001, pandas lee la columna como
    int64 y la corrección del motor es la cadena "01001". Escribir texto en una
    columna entera lanzaba TypeError y tumbaba el análisis completo.
    """
    df = pd.DataFrame({"CP": [1001, 28001, 8001], "Email": ["a@b.com"] * 3})
    resultado = CleaningEngine().run(df)

    todos = pd.concat([resultado.valid, resultado.quarantine])
    assert "01001" in set(todos["CP"].astype(str))
    assert "08001" in set(todos["CP"].astype(str))


def test_columna_numerica_sin_correcciones_conserva_su_tipo() -> None:
    """La ampliación a tipo objeto sólo debe ocurrir cuando hace falta."""
    df = pd.DataFrame({"CP": [28001, 8001], "Edad": [30, 40]})
    resultado = CleaningEngine().run(df, CleanOptions(detect_duplicates=False))
    todos = pd.concat([resultado.valid, resultado.quarantine])
    assert pd.api.types.is_numeric_dtype(todos["Edad"])


def test_rendimiento_en_diez_mil_filas() -> None:
    """Un fichero de diez mil filas debe procesarse en menos de diez segundos.

    Con el autoencoder anterior, sólo importar TensorFlow tardaba más que esto.
    """
    df = pd.DataFrame({
        "Nombre": [f"Cliente Numero {i}" for i in range(10_000)],
        "Email": [f"cliente{i}@empresa.com" for i in range(10_000)],
        "CP": ["28001"] * 10_000,
        "Edad": [30 + (i % 50) for i in range(10_000)],
    })
    resultado = CleaningEngine().run(df, CleanOptions(detect_duplicates=False))
    assert resultado.report.rows_in == 10_000
    assert resultado.report.duration_ms < 10_000
