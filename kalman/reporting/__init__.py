"""Lo que Kalman entrega al cliente.

Son dos cosas distintas y conviene no confundirlas:

- El **informe**, en `pdf`, dice cuántos datos están mal. Es el diagnóstico y
  sirve para enseñárselo a un jefe.
- La **lista de trabajo**, en `worklist`, dice qué hay que arreglar y a quién
  hay que llamar. Es lo que el equipo abre el lunes y va tachando.

La segunda es el producto. La primera es la prueba de que hacía falta.
"""

from .pdf import RULE_LABELS, Composed, CostAssumption, Line, Section, build_report, compose
from .worklist import build_worklist, summary_line, to_excel

__all__ = [
    "compose",
    "build_report",
    "Composed",
    "Section",
    "Line",
    "CostAssumption",
    "RULE_LABELS",
    "build_worklist",
    "to_excel",
    "summary_line",
]
