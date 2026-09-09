# Kalman

**Señal, no ruido, en los datos de tu empresa.**

Kalman valida y limpia bases de datos de clientes españolas. Verifica NIF, NIE,
CIF e IBAN con su dígito de control oficial, normaliza contacto, detecta valores
imposibles y encuentra clientes duplicados.

El nombre viene del filtro de Kalman, el algoritmo que Rudolf Kálmán publicó en
1960 para estimar el estado real de un sistema a partir de mediciones ruidosas.
Se usó en la navegación del programa Apolo y hoy va a bordo de casi todo lo que
vuela. Es exactamente este problema.

---

## Lo que hace, y lo que no

Kalman **no adivina**. En la parte que importa no hay probabilidad: un NIF tiene
una letra de control calculada con módulo 23 y un IBAN tiene dos dígitos de
control calculados con módulo 97. O cuadran o no cuadran.

| Comprobación | Método | ¿Exacto? |
|---|---|---|
| NIF, NIE, CIF | Dígito de control oficial | Sí |
| IBAN | Módulo 97, norma ISO 13616 | Sí |
| Código postal | Rango de provincia asignado | Sí |
| Teléfono | Rango numérico español, salida en E.164 | Sí |
| Email | Sintaxis, dominios desechables, erratas frecuentes | Heurístico |
| Valores atípicos | Desviación absoluta mediana, umbral 3,5 | Estadístico |
| Duplicados | Bloqueo más similitud, umbral 0,92 | Estadístico |

Cada hallazgo lleva regla, mensaje, gravedad y confianza. Nada llega al cliente
como "el modelo dice que es raro".

**Kalman no estima cuánto dinero te ahorra.** El coste de un dato incorrecto
depende de tu operativa y sólo lo conoces tú. Si quieres una cifra en euros en
el informe, tú aportas el coste por incidencia y el documento deja constancia
de que la cifra es tuya.

---

## Empezar en treinta segundos

```bash
pip install pandas numpy
python -m kalman.cli check-nif B65410011
```

Limpiar un fichero entero:

```bash
python -m kalman.cli clean clientes.csv --out limpio.csv --report informe.json
```

Desde Python:

```python
import pandas as pd
from kalman.core import CleaningEngine

resultado = CleaningEngine().run(pd.read_csv("clientes.csv"))

print(resultado.report.counts_by_rule())
resultado.valid.to_csv("limpio.csv", index=False)
resultado.quarantine.to_csv("revisar.csv", index=False)
```

No hay que configurar el nombre de las columnas. Kalman las reconoce por
sinónimos y por contenido, y conserva intactas las que no entiende.

---

## Arquitectura

```
kalman/
  core/          Motor puro. Sin red, sin disco, sin base de datos.
    validators/  NIF, NIE, CIF, IBAN, email, teléfono, código postal
    outliers.py  Detección robusta por desviación absoluta mediana
    dedupe.py    Resolución de entidades por bloqueo y similitud
    engine.py    Orquestación e informe auditable
  billing/       Planes, Stripe y derecho de uso
  db/            Esquema con seguridad a nivel de fila, y acceso a datos
  security/      Contraseñas con scrypt y claves de API
  api/           API HTTP con FastAPI
  web/           Interfaz con Streamlit
  reporting/     Informe de auditoría en PDF
  cli.py         Línea de comandos
```

El núcleo no importa nada de las demás capas. Esa restricción es lo que permite
que la batería de pruebas corra en un segundo y que el mismo motor sirva la web,
la API, la línea de comandos y un proceso por lotes sin duplicar una línea.

Detalle en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

---

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate        # en Linux o macOS: source .venv/bin/activate
pip install -e ".[web,api,db,billing,dev]"

copy .env.example .env         # en Linux o macOS: cp
```

Rellena `.env`. La clave de seudonimización se genera así:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Aplica el esquema y crea la primera organización:

```bash
python scripts/bootstrap.py --org "Mi Empresa" --email tu@correo.com
```

Arranca la web:

```bash
streamlit run kalman/web/app.py
```

O la API:

```bash
uvicorn kalman.api.main:app --reload
```

---

## Pruebas

```bash
python -m pytest
```

166 pruebas, un segundo. Cubren los algoritmos de dígito de control, la
resistencia del detector de atípicos a datos corruptos, la deduplicación, el
derecho de uso y las contraseñas.

En Windows con Python de Microsoft Store hay que usar `scripts/run_tests.ps1`,
porque ese Python virtualiza `AppData\Roaming` y no ve los ficheros del
proyecto.

---

## Licencia

MIT. Ver [LICENSE](LICENSE).

El motor es abierto a propósito. Un algoritmo de dígito de control no es un
secreto industrial, está publicado en el Boletín Oficial del Estado. Lo que se
vende no es el algoritmo: es que funcione, esté mantenido, tenga soporte y
alguien responda cuando falle. Abrirlo es lo que hace que un ingeniero de una
empresa pueda leerlo, comprobar que es correcto y recomendarlo internamente,
que es el único camino de venta que no requiere un equipo comercial.

---

## Seguridad y privacidad

- [SECURITY.md](SECURITY.md): cómo comunicar una vulnerabilidad y qué garantías se dan.
- [PRIVACY.md](PRIVACY.md): qué se guarda, qué no, y por qué esto es seudonimización y no anonimización.

Si encuentras un fallo de seguridad, no abras una incidencia pública.

---

## Desplegar la demo publica

La demo es `demo_app.py`. No necesita base de datos, ni Stripe, ni ninguna
credencial, asi que se puede publicar en abierto tal cual.

En Streamlit Community Cloud:

1. Repositorio `JoWyFF09/kalman`, rama `main`.
2. Main file path: `demo_app.py`.
3. En Advanced settings, Python version: **3.12**.
4. No hay nada que rellenar en Secrets.

Streamlit Cloud no permite elegir el nombre del fichero de dependencias:
siempre usa `requirements.txt` de la raiz. Por eso ese fichero contiene solo
las cinco dependencias de la demo. El proyecto completo se instala con los
extras de `pyproject.toml`, no con ese fichero.

La aplicacion con login y cobro es `kalman/web/app.py` y **no** debe
desplegarse en Streamlit Community Cloud: necesita secretos de produccion y un
sitio donde el webhook de Stripe pueda llegar.
