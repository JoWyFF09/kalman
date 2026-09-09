"""Detección de valores atípicos por desviación absoluta mediana.

Por qué esto y no el autoencoder que había antes
-------------------------------------------------
La versión anterior escalaba cada columna con min-max sobre el conjunto
completo, outliers incluidos. Con un ingreso de 2.500.000 en el máximo, todos
los sueldos reales quedaban aplastados entre 0.00 y 0.02 y el error de
reconstrucción perdía casi toda su capacidad de discriminar. El detector se
rompía justo con los datos que debía detectar.

La mediana y la MAD tienen un punto de ruptura del 50%: hace falta corromper
la mitad del conjunto para moverlas. Un solo millonario absurdo no las altera.

El umbral 3.5 sobre la puntuación z modificada procede de Iglewicz y Hoaglin,
"How to Detect and Handle Outliers" (ASQC, 1993). Es un valor publicado y
defendible ante un cliente, no un 0.05 escrito a mano.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Constante que hace la MAD un estimador consistente de la desviación típica
#: bajo distribución normal. Es el inverso del percentil 75 de la normal.
_MAD_TO_SIGMA = 0.6745

#: Umbral recomendado por Iglewicz y Hoaglin.
DEFAULT_THRESHOLD = 3.5


@dataclass(frozen=True, slots=True)
class OutlierModel:
    """Parámetros ajustados de una columna numérica.

    Es serializable y auditable: un cliente puede pedir por qué se marcó un
    valor y la respuesta cabe en una línea.
    """

    column: str
    median: float
    mad: float
    scale: float
    threshold: float
    n_fitted: int
    fallback: str | None = None

    def score(self, values: np.ndarray) -> np.ndarray:
        """Puntuación z modificada. Cuanto mayor, más atípico."""
        if self.scale == 0:
            return np.zeros_like(values, dtype=float)
        return _MAD_TO_SIGMA * (values - self.median) / self.scale

    def bounds(self) -> tuple[float, float]:
        """Intervalo de valores considerados normales.

        Sirve para explicar el hallazgo en lenguaje humano: "esperábamos entre
        18 y 76 años".
        """
        if self.scale == 0:
            return (self.median, self.median)
        delta = self.threshold * self.scale / _MAD_TO_SIGMA
        return (self.median - delta, self.median + delta)


def fit_outlier_model(
    values: np.ndarray,
    column: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> OutlierModel:
    """Ajusta el modelo sobre los valores no nulos de una columna.

    Si la MAD es cero, cosa que ocurre cuando más de la mitad de las filas
    comparten el mismo valor, se recurre a la desviación absoluta media. Si esa
    también es cero, la columna es constante y no hay nada que detectar.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return OutlierModel(column, 0.0, 0.0, 0.0, threshold, 0, fallback="empty")

    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))

    if mad > 0:
        return OutlierModel(column, median, mad, mad, threshold, int(finite.size))

    mean_abs_dev = float(np.mean(np.abs(finite - median)))
    if mean_abs_dev > 0:
        # El factor 1.253314 iguala la escala de la desviación absoluta media
        # a la de la MAD bajo normalidad, para que el umbral siga significando
        # lo mismo.
        return OutlierModel(
            column, median, 0.0, mean_abs_dev * 1.253314, threshold,
            int(finite.size), fallback="mean_abs_dev",
        )

    return OutlierModel(
        column, median, 0.0, 0.0, threshold, int(finite.size), fallback="constant"
    )


@dataclass(frozen=True, slots=True)
class DomainRule:
    """Cota dura conocida de antemano para una magnitud.

    La estadística dice qué es raro en este conjunto de datos. El dominio dice
    qué es imposible en el mundo. Una edad de 150 años es imposible aunque el
    conjunto entero esté lleno de ellas, y ninguna estadística lo detectará si
    la corrupción es mayoritaria. Las dos capas son necesarias.
    """

    minimum: float | None
    maximum: float | None
    message: str


#: Cotas para las magnitudes que aparecen en datos comerciales españoles.
DOMAIN_RULES: dict[str, DomainRule] = {
    "edad": DomainRule(0, 120, "La edad debe estar entre 0 y 120 años."),
    "ingresos_anuales": DomainRule(0, 10_000_000, "Ingresos anuales fuera de un rango plausible."),
    "importe": DomainRule(None, None, ""),
    "codigo_postal": DomainRule(1000, 52999, "Código postal fuera del rango español."),
}


def check_domain(column: str, value: float) -> str | None:
    """Devuelve el mensaje de la cota incumplida, o None si el valor es posible."""
    rule = DOMAIN_RULES.get(column)
    if rule is None:
        return None
    if rule.minimum is not None and value < rule.minimum:
        return rule.message
    if rule.maximum is not None and value > rule.maximum:
        return rule.message
    return None
