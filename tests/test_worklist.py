"""Pruebas de la lista de trabajo.

La lista es lo que de verdad se vende, asi que se comprueba lo que la hace
util: que diga a quien hay que llamar, que ordene lo urgente primero, y que el
numero de fila coincida con lo que la persona ve al abrir el fichero en Excel.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from kalman.core.engine import CleaningEngine
from kalman.reporting.worklist import build_worklist, summary_line, to_excel


@pytest.fixture
def datos() -> pd.DataFrame:
    return pd.DataFrame({
        "Razón Social": [
            "Talleres Gómez SL",
            "Panadería Central SA",
            "Construcciones Sur SL",
            "TALLERES GOMEZ SOCIEDAD LIMITADA",
        ],
        "CIF": ["A58818501", "A58818500", "B65410011", "A58818501"],
        "Correo": ["info@gomez.es", "roto", "hola@sur.es", "INFO@GOMEZ.ES"],
        "Cuenta": [
            "ES9121000418450200051332",
            "ES9121000418450200051333",
            "ES9121000418450200051332",
            "ES9121000418450200051332",
        ],
        "CP": ["28001", "99999", "08001", "28001"],
    })


@pytest.fixture
def lista(datos: pd.DataFrame) -> pd.DataFrame:
    resultado = CleaningEngine().run(datos)
    return build_worklist(datos, resultado.report, resultado.duplicates)


def test_dice_a_quien_hay_que_llamar(lista: pd.DataFrame) -> None:
    """Sin el nombre del cliente, la lista dice "fila 3" y no sirve."""
    con_cliente = lista[lista["Cliente"].astype(str).str.len() > 0]
    assert len(con_cliente) == len(lista)
    assert "Panadería Central SA" in set(lista["Cliente"])


def test_el_numero_de_fila_coincide_con_excel(datos: pd.DataFrame) -> None:
    """La fila 0 del DataFrame es la linea 2 del fichero: la 1 es la cabecera.

    Si el numero no coincide con lo que ve la persona en Excel, la lista es
    inutilizable.
    """
    resultado = CleaningEngine().run(datos)
    lista = build_worklist(datos, resultado.report, resultado.duplicates)

    cif_malo = lista[lista["Regla"] == "tax_id.cif.checksum"]
    assert len(cif_malo) == 1
    # El CIF invalido esta en la segunda fila de datos, o sea la linea 3.
    assert int(cif_malo.iloc[0]["Fila en el fichero"]) == 3


def test_lo_urgente_va_primero(lista: pd.DataFrame) -> None:
    """Quien abre la lista debe encontrar arriba lo que esta demostrablemente mal."""
    gravedades = lista["Gravedad"].tolist()
    orden = {"Error": 0, "Revisar": 1, "Corregido": 2}
    valores = [orden[g] for g in gravedades]
    assert valores == sorted(valores)
    assert gravedades[0] == "Error"


def test_cada_linea_dice_que_hacer(lista: pd.DataFrame) -> None:
    """Una lista de problemas sin instruccion genera una llamada a soporte."""
    assert (lista["Qué hacer"].astype(str).str.len() > 10).all()


def test_el_problema_esta_explicado_en_castellano(lista: pd.DataFrame) -> None:
    assert (lista["Problema"].astype(str).str.len() > 5).all()
    assert not lista["Problema"].astype(str).str.contains("checksum").any()


def test_incluye_los_duplicados(lista: pd.DataFrame) -> None:
    """Las filas 1 y 4 son la misma empresa escrita de dos formas."""
    duplicados = lista[lista["Regla"] == "duplicate.group"]
    assert len(duplicados) >= 1
    assert duplicados.iloc[0]["Campo"] == "Fila completa"


def test_el_iban_invalido_aparece_con_su_valor(lista: pd.DataFrame) -> None:
    iban = lista[lista["Regla"] == "iban.checksum"]
    assert len(iban) == 1
    assert "ES91" in str(iban.iloc[0]["Valor actual"])


def test_por_defecto_no_lista_lo_ya_corregido(datos: pd.DataFrame) -> None:
    """Una lista de tareas no empieza con doscientas cosas ya hechas."""
    resultado = CleaningEngine().run(datos)

    sin_info = build_worklist(datos, resultado.report, resultado.duplicates)
    con_info = build_worklist(
        datos, resultado.report, resultado.duplicates, include_info=True
    )

    assert "Corregido" not in set(sin_info["Gravedad"])
    assert len(con_info) > len(sin_info)


def test_fichero_perfecto_da_lista_vacia_con_columnas() -> None:
    """Vacia, pero con las columnas puestas: si no, Excel se queja al abrirla."""
    df = pd.DataFrame({"CIF": ["A58818501"], "Correo": ["a@b.com"]})
    resultado = CleaningEngine().run(df)
    lista = build_worklist(df, resultado.report, resultado.duplicates)

    assert lista.empty
    assert "Cliente" in lista.columns
    assert "Qué hacer" in lista.columns


# --------------------------------------------------------------------- Excel

def test_el_excel_se_abre(lista: pd.DataFrame) -> None:
    contenido = to_excel(lista)
    assert contenido[:2] == b"PK"  # un .xlsx es un zip

    leido = pd.read_excel(io.BytesIO(contenido))
    assert len(leido) == len(lista)
    assert "Qué hacer" in leido.columns


def test_el_excel_viene_listo_para_trabajar(lista: pd.DataFrame) -> None:
    """Cabecera fijada y filtros puestos.

    Una hoja donde hay que ensanchar columnas y poner filtros a mano antes de
    poder usarla no parece un producto por el que se paga.
    """
    from openpyxl import load_workbook

    hoja = load_workbook(io.BytesIO(to_excel(lista))).active
    assert hoja.freeze_panes == "A2"
    assert hoja.auto_filter.ref is not None
    assert hoja.column_dimensions["A"].width > 0


def test_el_excel_vacio_no_rompe() -> None:
    vacia = build_worklist(
        pd.DataFrame({"CIF": ["A58818501"]}),
        CleaningEngine().run(pd.DataFrame({"CIF": ["A58818501"]})).report,
    )
    assert to_excel(vacia)[:2] == b"PK"


# ------------------------------------------------------------------- resumen

def test_el_resumen_cuenta_lo_que_hay(lista: pd.DataFrame) -> None:
    frase = summary_line(lista)
    assert "corregir" in frase or "revisar" in frase
    assert "filas" in frase


def test_el_resumen_de_una_lista_vacia_es_una_buena_noticia() -> None:
    assert "No hay nada" in summary_line(build_worklist(
        pd.DataFrame({"CIF": ["A58818501"]}),
        CleaningEngine().run(pd.DataFrame({"CIF": ["A58818501"]})).report,
    ))
