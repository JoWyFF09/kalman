"""Pruebas de la línea de comandos."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from kalman.cli import main


def test_nif_valido_devuelve_cero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check-nif", "12345678Z"]) == 0
    assert "OK" in capsys.readouterr().out


def test_nif_invalido_devuelve_uno(capsys: pytest.CaptureFixture[str]) -> None:
    """El código de salida importa: permite usarlo en un script."""
    assert main(["check-nif", "12345678A"]) == 1
    salida = capsys.readouterr().out
    assert "MAL" in salida
    assert "letra de control" in salida.lower()


def test_iban_invalido_explica_el_motivo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check-iban", "ES9121000418450200051333"]) == 1
    assert "control" in capsys.readouterr().out.lower()


def test_email_con_errata_sugiere_correccion(capsys: pytest.CaptureFixture[str]) -> None:
    main(["check-email", "joel@gmail.con"])
    assert "gmail.com" in capsys.readouterr().out


def test_clean_escribe_los_ficheros(tmp_path: Path) -> None:
    entrada = tmp_path / "entrada.csv"
    pd.DataFrame({
        "CIF": ["A58818501", "A58818500"],
        "Email": ["a@b.com", "roto"],
    }).to_csv(entrada, index=False)

    salida = tmp_path / "limpio.csv"
    cuarentena = tmp_path / "cuarentena.csv"
    informe = tmp_path / "informe.json"

    codigo = main([
        "clean", str(entrada),
        "--out", str(salida),
        "--cuarentena", str(cuarentena),
        "--report", str(informe),
    ])

    assert codigo == 1  # hay filas en cuarentena
    assert salida.exists() and cuarentena.exists() and informe.exists()
    assert len(pd.read_csv(salida)) + len(pd.read_csv(cuarentena)) == 2


def test_clean_sin_incidencias_devuelve_cero(tmp_path: Path) -> None:
    entrada = tmp_path / "ok.csv"
    pd.DataFrame({"CIF": ["A58818501"], "Email": ["a@b.com"]}).to_csv(entrada, index=False)
    assert main(["clean", str(entrada)]) == 0


def test_fichero_inexistente_devuelve_dos(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["clean", "no_existe_este_fichero.csv"]) == 2
