"""Pruebas de detección de duplicados."""

from __future__ import annotations

from kalman.core.dedupe import find_duplicates, similarity
from kalman.core.normalize import normalize_company, strip_accents, title_case_name


def test_mismo_nif_es_duplicado_seguro() -> None:
    registros = [
        {"tax_id": "12345678Z", "name": "Joel Rodriguez"},
        {"tax_id": "12345678Z", "name": "J. Rodriguez"},
        {"tax_id": "00000000T", "name": "Otra Persona"},
    ]
    grupos = find_duplicates(registros)
    assert len(grupos) == 1
    assert grupos[0].confidence == 1.0
    assert grupos[0].rows == [0, 1]
    assert grupos[0].survivor == 0


def test_agrupacion_transitiva() -> None:
    """A y B comparten email, B y C comparten teléfono. Los tres son uno."""
    registros = [
        {"email": "a@x.com", "phone": "+34600000001"},
        {"email": "a@x.com", "phone": "+34600000002"},
        {"email": "c@x.com", "phone": "+34600000002"},
    ]
    grupos = find_duplicates(registros)
    assert len(grupos) == 1
    assert grupos[0].rows == [0, 1, 2]


def test_forma_societaria_distinta_es_la_misma_empresa() -> None:
    registros = [
        {"company": "Talleres Gómez S.L.", "postal_code": "28001"},
        {"company": "TALLERES GOMEZ SOCIEDAD LIMITADA", "postal_code": "28001"},
    ]
    grupos = find_duplicates(registros)
    assert len(grupos) == 1


def test_codigos_postales_distintos_no_se_fusionan() -> None:
    """El bloqueo por código postal evita fusionar sucursales distintas."""
    registros = [
        {"company": "Talleres Gómez S.L.", "postal_code": "28001"},
        {"company": "Talleres Gómez S.L.", "postal_code": "08001"},
    ]
    grupos = find_duplicates(registros)
    assert grupos == []


def test_empresas_distintas_no_se_fusionan() -> None:
    """Falso positivo caro: fusionar dos clientes reales destruye datos."""
    registros = [
        {"company": "Construcciones Norte SL", "postal_code": "28001"},
        {"company": "Construcciones Sur SL", "postal_code": "28001"},
        {"company": "Panaderia Central SL", "postal_code": "28001"},
    ]
    assert find_duplicates(registros) == []


def test_lista_sin_duplicados_devuelve_vacio() -> None:
    registros = [
        {"tax_id": "12345678Z", "email": "a@x.com"},
        {"tax_id": "00000000T", "email": "b@x.com"},
    ]
    assert find_duplicates(registros) == []


def test_valores_vacios_no_agrupan() -> None:
    """Tres filas sin email no son tres veces el mismo cliente."""
    registros = [{"email": None}, {"email": ""}, {"email": "nan"}]
    assert find_duplicates(registros) == []


def test_survivor_es_la_fila_mas_antigua() -> None:
    registros = [{"tax_id": "12345678Z"}] * 3
    grupo = find_duplicates(registros)[0]
    assert grupo.survivor == 0
    assert grupo.duplicates == [1, 2]


def test_normalize_company_unifica_formas() -> None:
    assert normalize_company("Gómez S.L.") == normalize_company("GOMEZ SOCIEDAD LIMITADA")
    assert normalize_company("Acme S.A.") != normalize_company("Acme S.L.")


def test_la_enye_se_conserva() -> None:
    """Peña y Pena son apellidos distintos."""
    assert strip_accents("Peña") == "Peña"
    assert strip_accents("Muñoz Gutiérrez") == "Muñoz Gutierrez"
    assert similarity(normalize_company("Peña SL"), normalize_company("Pena SL")) < 1.0


def test_capitalizacion_espanola_de_nombres() -> None:
    assert title_case_name("JOEL DE LA TORRE") == "Joel de la Torre"
    assert title_case_name("maria del carmen ruiz") == "Maria del Carmen Ruiz"
