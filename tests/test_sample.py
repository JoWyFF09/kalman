"""Pruebas del generador de datos de ejemplo.

La primera prueba viene de un fallo que encontro el usuario. Pedir 2.000 filas
devolvia 2.127, porque los duplicados se anadian por encima de la cuenta. Eso
agotaba la cuota del plan gratuito, que son 2.000 filas al mes, sin que se
entendiera el motivo.
"""

from __future__ import annotations

import pytest

from kalman.core.engine import CleaningEngine, CleanOptions
from kalman.sample import generate


@pytest.mark.parametrize("filas", [1, 10, 500, 1_999, 2_000])
def test_devuelve_exactamente_las_filas_pedidas(filas: int) -> None:
    assert len(generate(rows=filas, seed=3)) == filas


def test_cero_filas_se_rechaza() -> None:
    with pytest.raises(ValueError):
        generate(rows=0)


def test_es_reproducible() -> None:
    """La misma semilla debe dar el mismo fichero.

    Sin esto, una demostracion ante un cliente sale distinta cada vez y no se
    puede preparar lo que se va a ensenar.
    """
    uno = generate(rows=300, seed=11)
    otro = generate(rows=300, seed=11)
    assert uno.equals(otro)


def test_semillas_distintas_dan_ficheros_distintos() -> None:
    assert not generate(rows=300, seed=1).equals(generate(rows=300, seed=2))


def test_contiene_defectos_de_los_tres_tipos() -> None:
    """El fichero debe servir para ensenar el producto.

    Si no trae identificadores fiscales rotos, IBAN rotos y duplicados, la
    demostracion no ensena nada.
    """
    resultado = CleaningEngine().run(generate(rows=1_500, seed=5))
    reglas = resultado.report.counts_by_rule()

    assert reglas.get("tax_id.cif.checksum", 0) > 0
    assert reglas.get("iban.checksum", 0) > 0
    assert resultado.report.duplicate_groups > 0


def test_la_mayoria_de_las_filas_son_correctas() -> None:
    """Un fichero donde casi todo falla no se parece a los datos de nadie."""
    informe = CleaningEngine().run(
        generate(rows=1_500, seed=5), CleanOptions(detect_duplicates=False)
    ).report
    assert informe.rows_valid / informe.rows_in > 0.75


def test_cabe_en_el_plan_gratuito() -> None:
    """El tamano por defecto de la demo publica no puede pasarse de cuota."""
    from kalman.billing.plans import PLANS

    assert len(generate(rows=1_200, seed=7)) <= PLANS["free"].monthly_rows
