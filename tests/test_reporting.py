"""Pruebas del informe.

La comprobación que más importa aquí no es que el PDF se genere, es que no
contenga una cifra de ahorro inventada. Se hace sobre el contenido compuesto,
no sobre los bytes del PDF, porque buscar palabras dentro de un PDF depende de
cómo se codifique el texto y da falsa confianza.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kalman.core.engine import CleaningEngine
from kalman.reporting.pdf import CostAssumption, compose


@pytest.fixture
def informe() -> dict:
    df = pd.DataFrame({
        "CIF": ["A58818501", "A58818500", "B65410011"],
        "Correo": ["a@b.com", "roto", "c@d.es"],
        "CP": ["28001", "99999", "08001"],
    })
    return CleaningEngine().run(df).report.as_dict()


# ------------------------------------------------------------------ contenido

def test_sin_coste_del_cliente_no_aparece_ninguna_cifra_de_ahorro(informe: dict) -> None:
    """La regla del módulo, comprobada sobre el texto exacto del informe."""
    texto = compose(informe, "Empresa").as_text().lower()
    for prohibido in ("ahorro", "hemos evitado", "estimado en", "coste evitado"):
        assert prohibido not in texto


def test_sin_coste_se_explica_por_que_no_hay_cifra(informe: dict) -> None:
    texto = compose(informe, "Empresa").as_text().lower()
    assert "no calcula cuánto dinero" in texto


def test_con_coste_del_cliente_se_cita_el_origen(informe: dict) -> None:
    coste = CostAssumption(12.5, "comisión media por recibo devuelto en 2026")
    texto = compose(informe, "Empresa", coste).as_text()

    assert "lo ha aportado el cliente" in texto
    assert "comisión media por recibo devuelto en 2026" in texto
    assert "no ha estimado ni validado" in texto


def test_el_total_es_el_producto_exacto(informe: dict) -> None:
    """Si el cliente da la cifra, la aritmética debe ser suya y verificable."""
    errores = informe["counts_by_severity"]["error"]
    coste = CostAssumption(10.0, "dato del cliente")
    texto = compose(informe, "Empresa", coste).as_text()
    assert f"{errores * 10.0:,.2f} EUR" in texto


def test_las_reglas_se_traducen_a_lenguaje_llano(informe: dict) -> None:
    texto = compose(informe, "Empresa").as_text()
    assert "tax_id.cif.checksum" not in texto
    assert "CIF con dígito de control incorrecto" in texto


def test_el_informe_incluye_la_metodologia(informe: dict) -> None:
    """Un cliente técnico pregunta cómo se ha calculado. Debe estar escrito."""
    texto = compose(informe, "Empresa").as_text()
    assert "Iglewicz" in texto
    assert "dígito de control oficial" in texto


def test_se_dice_que_los_duplicados_no_se_fusionan(informe: dict) -> None:
    assert "nunca se fusionan" in compose(informe, "Empresa").as_text()


def test_la_version_del_motor_va_en_el_informe(informe: dict) -> None:
    """Sin versión el informe no es reproducible y no vale para una auditoría."""
    assert informe["engine_version"] in compose(informe, "Empresa").as_text()


def test_informe_vacio_no_rompe() -> None:
    vacio = CleaningEngine().run(pd.DataFrame()).report.as_dict()
    assert compose(vacio, "Empresa").as_text()


# ----------------------------------------------------------------- renderizado

def test_genera_un_pdf_valido(informe: dict) -> None:
    pytest.importorskip("fpdf", reason="El PDF requiere fpdf2.")
    from kalman.reporting.pdf import build_report

    contenido = build_report(informe, "Talleres Gómez S.L.")
    assert contenido.startswith(b"%PDF-")
    assert contenido.rstrip().endswith(b"%%EOF")
    assert len(contenido) > 1000


def test_el_nombre_con_tildes_no_rompe_la_generacion(informe: dict) -> None:
    """fpdf2 con fuentes básicas sólo cubre Latin-1."""
    pytest.importorskip("fpdf", reason="El PDF requiere fpdf2.")
    from kalman.reporting.pdf import build_report

    for nombre in ["Panadería Ñoño S.L.", "Construcciones Muñoz & Peña", "Açaí 東京"]:
        assert build_report(informe, nombre).startswith(b"%PDF-")


def test_el_simbolo_del_euro_se_transcribe(informe: dict) -> None:
    """Latin-1 no tiene el euro. Sin transcribirlo, la generación falla."""
    pytest.importorskip("fpdf", reason="El PDF requiere fpdf2.")
    from kalman.reporting.pdf import build_report

    coste = CostAssumption(9.99, "coste interno € por incidencia")
    assert build_report(informe, "Empresa €", coste).startswith(b"%PDF-")
