"""Pruebas de los testigos de un solo uso y del correo transaccional."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kalman.legal import LEGAL_VERSION, PRIVACY, TERMS, pending_placeholders
from kalman.notifications.email import (
    EmailError,
    EmailSender,
    EmailSettings,
    _ocultar,
    email_verify_body,
    password_reset_body,
)
from kalman.security.tokens import (
    PURPOSES,
    TOKEN_LIFETIME_MINUTES,
    TokenError,
    generate_token,
    hash_token,
    is_expired,
)


# ------------------------------------------------------------------ testigos

@pytest.mark.parametrize("purpose", sorted(PURPOSES))
def test_se_genera_un_testigo_por_cada_uso(purpose: str) -> None:
    raw, digest, expires = generate_token(purpose)
    assert len(raw) > 30
    assert len(digest) == 64
    assert expires > datetime.now(UTC)


def test_un_uso_inventado_se_rechaza() -> None:
    """La base de datos repite esta restricción, pero mejor fallar antes."""
    with pytest.raises(TokenError, match="desconocido"):
        generate_token("lo_que_sea")


def test_dos_testigos_nunca_coinciden() -> None:
    valores = {generate_token("password_reset")[0] for _ in range(300)}
    assert len(valores) == 300


def test_el_hash_es_estable_y_no_revela_el_testigo() -> None:
    """Se busca por hash en la base, así que debe ser determinista."""
    raw, digest, _ = generate_token("email_verify")
    assert hash_token(raw) == digest
    assert hash_token(f"  {raw}  ") == digest
    assert raw not in digest


def test_el_de_recuperar_dura_menos_que_el_de_verificar() -> None:
    """Recuperar contraseña es más sensible: el tiempo de ir a mirar el correo.

    Verificar puede esperar, porque alguien se da de alta un viernes por la
    tarde y abre el correo el lunes.
    """
    assert TOKEN_LIFETIME_MINUTES["password_reset"] <= 60
    assert TOKEN_LIFETIME_MINUTES["email_verify"] > TOKEN_LIFETIME_MINUTES["password_reset"]


def test_la_caducidad_se_respeta() -> None:
    ahora = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    assert not is_expired(ahora + timedelta(minutes=1), ahora)
    assert is_expired(ahora - timedelta(seconds=1), ahora)
    assert is_expired(ahora, ahora)


def test_una_fecha_sin_zona_horaria_no_revienta() -> None:
    """Algunos controladores la devuelven así, y comparar con zona lanza error."""
    ahora = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    sin_zona = datetime(2026, 9, 11, 13, 0)
    assert not is_expired(sin_zona, ahora)


# -------------------------------------------------------------------- correo

def test_sin_configurar_no_envia_y_lo_dice() -> None:
    """Sin credenciales el producto arranca igual; sólo avisa al usarlo."""
    sender = EmailSender(EmailSettings("", 465, "", "", ""))
    assert not sender.available
    with pytest.raises(EmailError, match="no está configurado"):
        sender.send("a@b.es", "Asunto", "Cuerpo")


def test_se_considera_configurado_con_todo_puesto() -> None:
    sender = EmailSender(
        EmailSettings("smtp.gmail.com", 465, "yo@gmail.com", "clave", "yo@gmail.com")
    )
    assert sender.available


def test_los_registros_no_llevan_el_correo_entero() -> None:
    """Los registros del servidor los ve más gente de la que debería ver la
    lista de correos de los clientes."""
    assert _ocultar("joel.rodriguez@gestoria.es") == "j***@gestoria.es"
    assert _ocultar("sin-arroba") == "***"


def test_el_correo_de_recuperacion_dice_que_hacer_si_no_fue_el_usuario() -> None:
    """Es lo que convierte un correo automático en uno fiable."""
    cuerpo = password_reset_body("Asesoría Gómez", "https://x.es/?reset=abc", 60)
    assert "https://x.es/?reset=abc" in cuerpo
    assert "60 minutos" in cuerpo
    assert "no has pedido" in cuerpo.lower()


def test_el_correo_de_verificacion_lleva_el_enlace_y_su_plazo() -> None:
    cuerpo = email_verify_body("Asesoría Gómez", "https://x.es/?verify=abc", 48)
    assert "https://x.es/?verify=abc" in cuerpo
    assert "48 horas" in cuerpo


@pytest.mark.parametrize(
    "cuerpo",
    [
        password_reset_body("Empresa", "https://x.es/?reset=t", 60),
        email_verify_body("Empresa", "https://x.es/?verify=t", 48),
    ],
)
def test_los_correos_van_en_texto_plano(cuerpo: str) -> None:
    """Un correo de recuperación con maquetación se parece más a una
    suplantación, y los filtros de muchas empresas lo tratan peor."""
    assert "<html" not in cuerpo.lower()
    assert "<div" not in cuerpo.lower()


# --------------------------------------------------------------------- legal

def test_los_textos_legales_existen_y_tienen_cuerpo() -> None:
    assert len(TERMS) > 1500
    assert len(PRIVACY) > 1500
    assert LEGAL_VERSION in TERMS
    assert LEGAL_VERSION in PRIVACY


def test_la_privacidad_dice_que_el_fichero_no_se_guarda() -> None:
    """Es la promesa central del producto y tiene que estar por escrito."""
    assert "no se guarda" in PRIVACY.lower()
    assert "encargado del tratamiento" in PRIVACY.lower()


def test_la_privacidad_no_llama_anonimizacion_a_la_seudonimizacion() -> None:
    """El error que cometía la versión anterior del producto, por escrito."""
    assert "seudonimización" in PRIVACY.lower()
    assert "no es anonimización" in PRIVACY.lower()


def test_las_condiciones_distinguen_lo_exacto_de_lo_estadistico() -> None:
    """Prometer exactitud en la deduplicación sería prometer lo que no se
    puede cumplir."""
    assert "deterministas" in TERMS.lower()
    assert "estadística" in TERMS.lower()


def test_quedan_huecos_por_rellenar_antes_de_publicar() -> None:
    """Esta prueba avisa mientras los textos lleven corchetes sin rellenar.

    No falla a propósito: falla cuando alguien los rellene, para que se acuerde
    de quitarla. Una página legal con un corchete es peor que no tenerla.
    """
    pendientes = pending_placeholders()
    assert pendientes, (
        "Ya no quedan huecos en los textos legales. "
        "Quita esta prueba y pon una que compruebe que NO quedan."
    )
