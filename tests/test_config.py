"""Pruebas del lector de configuración.

La regla que más importa aquí es que el entorno real gana siempre sobre el
fichero. Sin eso, un `.env` olvidado en un servidor pisaría los secretos de
producción, que es una forma silenciosa y muy desagradable de romper un
despliegue.
"""

from __future__ import annotations

import os
from pathlib import Path

from kalman.config import load_dotenv


def escribir(tmp_path: Path, contenido: str) -> Path:
    ruta = tmp_path / ".env"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_carga_variables_simples(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("KALMAN_PRUEBA_A", raising=False)
    ruta = escribir(tmp_path, "KALMAN_PRUEBA_A=valor\n")

    assert load_dotenv(ruta) == 1
    assert os.environ["KALMAN_PRUEBA_A"] == "valor"


def test_el_entorno_real_gana_sobre_el_fichero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KALMAN_PRUEBA_B", "del_entorno")
    ruta = escribir(tmp_path, "KALMAN_PRUEBA_B=del_fichero\n")

    load_dotenv(ruta)
    assert os.environ["KALMAN_PRUEBA_B"] == "del_entorno"


def test_ignora_comentarios_y_lineas_vacias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("KALMAN_PRUEBA_C", raising=False)
    ruta = escribir(
        tmp_path,
        "# esto es un comentario\n\n   \nKALMAN_PRUEBA_C=uno\n# otro comentario\n",
    )
    assert load_dotenv(ruta) == 1
    assert os.environ["KALMAN_PRUEBA_C"] == "uno"


def test_quita_las_comillas(tmp_path: Path, monkeypatch) -> None:
    """Mucha gente rodea el valor de comillas por costumbre."""
    for nombre in ("KALMAN_PRUEBA_D", "KALMAN_PRUEBA_E"):
        monkeypatch.delenv(nombre, raising=False)

    ruta = escribir(
        tmp_path,
        'KALMAN_PRUEBA_D="con dobles"\nKALMAN_PRUEBA_E=\'con simples\'\n',
    )
    load_dotenv(ruta)

    assert os.environ["KALMAN_PRUEBA_D"] == "con dobles"
    assert os.environ["KALMAN_PRUEBA_E"] == "con simples"


def test_conserva_el_signo_igual_dentro_del_valor(tmp_path: Path, monkeypatch) -> None:
    """Una contraseña o una URL de conexión puede llevar un igual dentro."""
    monkeypatch.delenv("KALMAN_PRUEBA_F", raising=False)
    ruta = escribir(tmp_path, "KALMAN_PRUEBA_F=postgres://u:p=a=b@host/db\n")

    load_dotenv(ruta)
    assert os.environ["KALMAN_PRUEBA_F"] == "postgres://u:p=a=b@host/db"


def test_una_variable_vacia_se_carga_como_vacia(tmp_path: Path, monkeypatch) -> None:
    """Es el caso de un .env recién creado con los huecos sin rellenar.

    Debe quedar vacía para que la validación de arranque avise con su mensaje,
    no para que la variable desaparezca y el fallo salga en otro sitio.
    """
    monkeypatch.delenv("KALMAN_PRUEBA_G", raising=False)
    ruta = escribir(tmp_path, "KALMAN_PRUEBA_G=\n")

    load_dotenv(ruta)
    assert os.environ["KALMAN_PRUEBA_G"] == ""


def test_sin_fichero_no_falla(tmp_path: Path) -> None:
    """En un servidor no hay .env y eso es lo normal, no un error."""
    assert load_dotenv(tmp_path / "no_existe.env") == 0


def test_linea_sin_igual_se_ignora(tmp_path: Path) -> None:
    assert load_dotenv(escribir(tmp_path, "esto no es una asignacion\n")) == 0
