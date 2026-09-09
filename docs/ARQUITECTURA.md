# Arquitectura

## La regla que ordena todo lo demás

`kalman/core` no importa nada del resto del proyecto. Ni base de datos, ni
Stripe, ni Streamlit, ni configuración, ni red.

Entra un DataFrame, sale un DataFrame y un informe. Nada más.

Esa restricción no es purismo. Produce cuatro consecuencias medibles:

1. La batería de pruebas del motor corre en **menos de un segundo**. Se ejecuta
   después de cada cambio, no una vez al día, y por eso encuentra los fallos.
2. El mismo motor sirve la web, la API, la línea de comandos y un proceso por
   lotes **sin duplicar una línea**.
3. Se puede publicar como paquete instalable con `pip install kalman` sin
   arrastrar credenciales ni servidores.
4. Un cliente puede leer el motor entero en una tarde y comprobar que es
   correcto. Eso es lo que convierte a un ingeniero en prescriptor interno.

Cuando dudes de dónde poner algo, la pregunta es: ¿esto necesita saber quién
paga, quién ha iniciado sesión o dónde está la base de datos? Si la respuesta
es no, va en el núcleo.

## Capas

```
                    ┌─────────────────────────────┐
   navegador ──────▶│  web/app.py     (Streamlit) │
                    ├─────────────────────────────┤
   proceso   ──────▶│  api/main.py    (FastAPI)   │
   del cliente      ├─────────────────────────────┤
                    │  cli.py         (terminal)  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │        kalman/core          │
                    │  puro, sin efectos externos │
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
   ┌────▼─────┐             ┌──────▼──────┐            ┌──────▼──────┐
   │ billing  │             │     db      │            │  reporting  │
   │ Stripe   │             │  Postgres   │            │  PDF, HTML  │
   └──────────┘             └─────────────┘            └─────────────┘
```

## Dentro del núcleo

| Módulo | Responsabilidad | Por qué está separado |
|---|---|---|
| `types.py` | Hallazgo, gravedad, informe | Contrato estable con el cliente |
| `normalize.py` | Texto y tipos de pandas | Lo usan todos los validadores |
| `validators/` | Una función por campo | Cada una se prueba aislada |
| `outliers.py` | Atípicos y cotas de dominio | Estadística, sin nada de negocio |
| `dedupe.py` | Resolución de entidades | El algoritmo más caro, aislado |
| `schema_map.py` | Reconocer las columnas | Sustituye el mapeo por cliente |
| `engine.py` | Orquestar y componer el informe | Único punto que conoce el resto |

### Las dos capas de detección numérica

La estadística dice qué es raro **en este fichero**. El dominio dice qué es
imposible **en el mundo**.

Hacen falta las dos. Si el fichero entero tuviera edades de 150 años, ninguna
estadística lo detectaría, porque 150 sería la normalidad de ese conjunto. Y al
revés: un sueldo de 300.000 euros no es imposible, pero sí es atípico en una
lista de sueldos de 45.000.

### Por qué la mediana y no la media

El motor anterior escalaba con mínimo y máximo. Con un solo ingreso de
2.500.000 en la columna, todos los sueldos reales quedaban comprimidos entre
0,00 y 0,02 y el detector perdía casi toda su capacidad de discriminar. Se
rompía justo con los datos que debía detectar.

La mediana y la desviación absoluta mediana tienen un punto de ruptura del
50%: hay que corromper la mitad del conjunto para moverlas.

## Decisiones que conviene no revertir

**Sin red neuronal.** El autoencoder anterior recibía cuatro columnas, dos de
las cuales ya eran la respuesta calculada por una expresión regular. Aprendía a
reconstruir un `if`. Costaba 600 MB de dependencias, minutos de arranque en
frío y un servidor con memoria suficiente. Se cambió por reglas exactas y
estadística robusta: mismo o mejor resultado, explicable, y despliegue de unos
50 MB que arranca en segundos.

Si algún día vuelve el aprendizaje automático, que sea para algo que las reglas
no puedan hacer, como emparejar direcciones postales escritas de forma libre.
No para adornar.

**El derecho de uso vive en la base de datos.** Sólo lo escribe el webhook de
Stripe tras verificar la firma. Ni la sesión del navegador ni un formulario
deciden quién ha pagado.

**El aislamiento entre clientes lo impone Postgres.** Con seguridad a nivel de
fila, un olvido en una cláusula `WHERE` deja de ser una fuga entre clientes.

**Las columnas se reconocen solas.** El motor anterior tenía una rama `if` por
cliente. Cien clientes eran cien ramas y un despliegue por venta. Ese era el
verdadero techo de escala, y no tenía nada que ver con el servidor.

**Nada de datos del cliente en la base.** Se guarda el recuento por regla, no
las filas. Un fichero de un millón de filas deja unos kilobytes.

## Rendimiento

Sobre 3.208 filas con errores realistas, en un portátil corriente:

| Fase | Tiempo |
|---|---|
| Motor completo con duplicados | 594 ms |
| Diez mil filas sin duplicados | menos de 1 s |

La deduplicación es la parte cara porque compara pares. Por eso se bloquea por
código postal y se descarta un bloque de más de 2.000 filas, donde el bloqueo
ya no discrimina y el coste se dispararía.

## Qué falta

Sinceridad sobre el estado del proyecto:

- Las pruebas contra base de datos real no están escritas. Las de facturación
  usan un almacén en memoria que cumple el mismo protocolo.
- No hay proceso asíncrono. Un fichero muy grande bloquea la petición.
- El emparejamiento de direcciones postales no existe.
- La API no tiene límite de peticiones por minuto. Antes del primer cliente de
  pago hay que ponerlo.
