"""Almacenamiento y verificación de contraseñas.

Lo que había antes
------------------
    usuarios_db = st.secrets["usuarios"]
    if str(usuarios_db[usuario]["password"]) == str(password):

Tres fallos en dos líneas. Las contraseñas estaban en claro en un fichero de
configuración, la comparación con el operador de igualdad filtra información
por el tiempo que tarda, y dar de alta un cliente exigía editar y desplegar.

Aquí se usa scrypt, que forma parte de la biblioteca estándar desde Python 3.6
y es una función de derivación de clave con coste de memoria configurable. Eso
significa que un atacante con la base de datos robada necesita mucha memoria
por cada intento, lo que arruina el ataque por fuerza bruta con tarjetas
gráficas.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: Parámetros de scrypt. n es el coste de CPU y memoria, r el tamaño de bloque
#: y p el paralelismo. Con n=2^15 cada verificación cuesta unos 32 MB de
#: memoria y decenas de milisegundos, que es imperceptible al iniciar sesión e
#: insoportable si intentas mil millones de combinaciones.
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LENGTH = 32
_SALT_BYTES = 16

_PREFIX = "scrypt"

#: Longitud mínima. El criterio actual del NIST y del Centro Criptológico
#: Nacional prima la longitud sobre los símbolos raros: una frase larga es más
#: fuerte y más fácil de recordar que "P@ssw0rd!".
MIN_PASSWORD_LENGTH = 12


class WeakPasswordError(ValueError):
    """La contraseña no cumple la política mínima."""


def validate_strength(password: str) -> None:
    """Comprueba la política de contraseñas y explica el motivo si falla."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )
    if password.lower() in _COMMON_PASSWORDS:
        raise WeakPasswordError(
            "Esa contraseña aparece en las listas públicas de contraseñas filtradas."
        )
    if len(set(password)) < 5:
        raise WeakPasswordError("La contraseña repite demasiado los mismos caracteres.")


_COMMON_PASSWORDS = frozenset({
    "contrasena123", "password1234", "123456789012", "qwertyuiop12",
    "administrador", "contraseña12", "bienvenido12", "spacenet1234",
})


def hash_password(password: str) -> str:
    """Devuelve el hash almacenable de una contraseña.

    El formato incluye los parámetros usados, de modo que se pueden endurecer
    en el futuro sin invalidar los hashes existentes.
    """
    validate_strength(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_LENGTH,
        maxmem=_SCRYPT_N * _SCRYPT_R * 256,
    )
    return f"{_PREFIX}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verifica una contraseña contra su hash almacenado.

    La comparación final usa `hmac.compare_digest`, que tarda lo mismo acierte
    o falle. Comparar con el operador de igualdad permitiría a un atacante
    deducir el hash carácter a carácter midiendo tiempos de respuesta.
    """
    if not stored or not password:
        return False
    try:
        prefix, n, r, p, salt_hex, expected_hex = stored.split("$")
        if prefix != _PREFIX:
            return False
        n_val, r_val, p_val = int(n), int(r), int(p)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
    except (ValueError, AttributeError):
        return False

    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n_val, r=r_val, p=p_val, dklen=len(expected),
        maxmem=n_val * r_val * 256,
    )
    return hmac.compare_digest(derived, expected)


def needs_rehash(stored: str) -> bool:
    """Indica si un hash usa parámetros más débiles que los actuales.

    Se llama tras un inicio de sesión correcto: es el único momento en que se
    tiene la contraseña en claro para poder regenerar el hash.
    """
    try:
        prefix, n, r, p, _, _ = stored.split("$")
    except ValueError:
        return True
    return (
        prefix != _PREFIX
        or int(n) < _SCRYPT_N
        or int(r) < _SCRYPT_R
        or int(p) < _SCRYPT_P
    )


def generate_api_key() -> tuple[str, str]:
    """Genera una clave de API y su hash.

    Se devuelve el par porque la clave en claro se enseña al usuario una sola
    vez y sólo se guarda el hash. Si la pierde, se regenera; no se recupera.
    Es el mismo criterio que sigue Stripe con sus propias claves.
    """
    raw = f"kal_{secrets.token_urlsafe(32)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest


def hash_api_key(raw: str) -> str:
    """Hash de una clave de API para buscarla en base de datos.

    Aquí sí basta SHA-256 sin derivación costosa: la clave tiene 256 bits de
    entropía real, así que no hay ataque de diccionario posible.
    """
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()
