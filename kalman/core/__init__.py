"""Núcleo de Kalman.

Este paquete no tiene efectos secundarios: no abre conexiones, no lee
configuración del entorno y no escribe en disco. Se puede importar desde un
cuaderno, desde la API o desde un proceso por lotes sin arrastrar nada.
"""

from .engine import ENGINE_VERSION, CleaningEngine, CleanOptions, CleanResult
from .pseudonymize import Pseudonymizer
from .types import Action, CleanReport, Finding, Severity

__all__ = [
    "CleaningEngine",
    "CleanOptions",
    "CleanResult",
    "CleanReport",
    "Finding",
    "Severity",
    "Action",
    "Pseudonymizer",
    "ENGINE_VERSION",
]
