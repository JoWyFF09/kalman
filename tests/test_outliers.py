"""Pruebas de detección de atípicos.

La prueba central de este fichero es `test_un_solo_extremo_no_ciega_al_detector`.
Es exactamente el fallo que tenía el motor anterior y el motivo por el que se
sustituyó el escalado min-max por la desviación absoluta mediana.
"""

from __future__ import annotations

import numpy as np

from kalman.core.outliers import check_domain, fit_outlier_model


def _sueldos_normales(n: int = 500) -> np.ndarray:
    generator = np.random.default_rng(7)
    return generator.normal(45_000, 12_000, n)


def test_un_solo_extremo_no_ciega_al_detector() -> None:
    """Con min-max, un valor de 2,5 millones aplastaba todo lo demás.

    Aquí se comprueba que la mediana y la MAD apenas se mueven y que el
    detector sigue marcando el extremo.
    """
    limpios = _sueldos_normales()
    con_extremo = np.append(limpios, 2_500_000.0)

    modelo_limpio = fit_outlier_model(limpios, "income")
    modelo_sucio = fit_outlier_model(con_extremo, "income")

    # La mediana se desplaza menos de un 1% pese al valor absurdo.
    desplazamiento = abs(modelo_sucio.median - modelo_limpio.median) / modelo_limpio.median
    assert desplazamiento < 0.01

    # Y el extremo se detecta con holgura.
    score = modelo_sucio.score(np.array([2_500_000.0]))[0]
    assert score > modelo_sucio.threshold


def test_resiste_veinte_por_ciento_de_corrupcion() -> None:
    """Punto de ruptura alto: la MAD aguanta hasta el 50% de datos corruptos."""
    limpios = _sueldos_normales(400)
    basura = np.full(100, 9_999_999.0)
    modelo = fit_outlier_model(np.concatenate([limpios, basura]), "income")

    assert 35_000 < modelo.median < 55_000
    assert modelo.score(np.array([9_999_999.0]))[0] > modelo.threshold


def test_valores_centrales_no_se_marcan() -> None:
    """Ningún falso positivo en el grueso de la distribución."""
    valores = _sueldos_normales(1000)
    modelo = fit_outlier_model(valores, "income")
    scores = np.abs(modelo.score(valores))
    tasa_falsos = float((scores > modelo.threshold).mean())
    assert tasa_falsos < 0.02


def test_columna_constante_no_produce_hallazgos() -> None:
    """Si todo el mundo tiene el mismo valor, nada es atípico."""
    modelo = fit_outlier_model(np.full(100, 42.0), "age")
    assert modelo.fallback == "constant"
    assert np.all(modelo.score(np.array([42.0, 43.0])) == 0)


def test_mad_cero_recurre_a_desviacion_media() -> None:
    """Más de la mitad de las filas iguales anula la MAD, pero no el detector."""
    valores = np.array([10.0] * 60 + [11.0, 12.0, 9.0, 8.0, 500.0])
    modelo = fit_outlier_model(valores, "age")
    assert modelo.fallback == "mean_abs_dev"
    assert modelo.score(np.array([500.0]))[0] > modelo.threshold


def test_columna_vacia_no_rompe() -> None:
    modelo = fit_outlier_model(np.array([np.nan, np.nan]), "age")
    assert modelo.fallback == "empty"
    assert modelo.n_fitted == 0


def test_bounds_son_explicables() -> None:
    """Los límites se enseñan al cliente, así que deben ser sensatos."""
    modelo = fit_outlier_model(_sueldos_normales(), "income")
    low, high = modelo.bounds()
    assert low < modelo.median < high
    assert 0 < low < 45_000 < high


def test_cotas_de_dominio_detectan_lo_imposible() -> None:
    """La estadística no salva de lo físicamente imposible."""
    assert check_domain("edad", 150.0) is not None
    assert check_domain("edad", -10.0) is not None
    assert check_domain("edad", 40.0) is None
    assert check_domain("ingresos_anuales", -5000.0) is not None


def test_cota_de_dominio_gana_a_la_estadistica() -> None:
    """Si todas las edades fueran 150, la MAD no vería nada raro.

    La capa de dominio es la que impide ese fallo silencioso.
    """
    valores = np.full(200, 150.0)
    modelo = fit_outlier_model(valores, "age")
    assert modelo.score(np.array([150.0]))[0] == 0
    assert check_domain("edad", 150.0) is not None
