"""Pruebas de los ficheros que Streamlit ejecuta como script.

Existen por un fallo real. `kalman/web/app.py` usaba imports relativos, que es
lo natural dentro de un paquete, y al arrancarlo con Streamlit reventaba:

    ImportError: attempted relative import with no known parent package

Streamlit no importa el fichero como módulo, lo ejecuta como un script suelto.
En esa situación Python no sabe a qué paquete pertenece y cualquier import
relativo falla. Las pruebas normales no lo detectan porque ellas sí importan el
módulo de la forma correcta.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Ficheros que Streamlit ejecuta directamente.
ENTRYPOINTS = [
    ROOT / "demo_app.py",
    ROOT / "kalman" / "web" / "app.py",
]


@pytest.mark.parametrize("ruta", ENTRYPOINTS, ids=lambda p: p.name)
def test_sin_imports_relativos(ruta: Path) -> None:
    """Ningún punto de entrada puede usar `from ..algo import x`."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))

    relativos = [
        f"linea {nodo.lineno}: from {'.' * nodo.level}{nodo.module or ''} import ..."
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom) and nodo.level > 0
    ]

    assert not relativos, (
        f"{ruta.name} lo ejecuta Streamlit como script, asi que no admite "
        f"imports relativos. Usa 'from kalman.x import y'. Encontrados: {relativos}"
    )


@pytest.mark.parametrize("ruta", ENTRYPOINTS, ids=lambda p: p.name)
def test_arranca_como_script_suelto(ruta: Path) -> None:
    """Reproduce lo que hace Streamlit: ejecutar el fichero por su ruta.

    Se ejecuta desde un directorio que no es el del proyecto, para que no sea
    el azar del directorio actual lo que haga funcionar los imports.

    Sólo se comprueba que no falle al importar. Que la interfaz se dibuje sin
    sesión de Streamlit no es asunto de esta prueba.
    """
    pytest.importorskip("streamlit", reason="Los puntos de entrada usan Streamlit.")

    proceso = subprocess.run(
        [sys.executable, str(ruta)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(ROOT.parent),
    )
    salida = proceso.stdout + proceso.stderr

    assert "attempted relative import" not in salida, salida[-2000:]
    assert "ModuleNotFoundError: No module named 'kalman'" not in salida, salida[-2000:]
