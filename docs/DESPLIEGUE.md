# Desplegar Kalman en producción

## Por qué dos servicios

El webhook de Stripe es una petición que Stripe manda a una dirección pública
tuya. Streamlit no sirve rutas propias, sólo su interfaz, así que **no puede
recibirlo**. La API con FastAPI sí.

Por eso el despliegue son dos servicios que comparten código y base de datos:

| Servicio | Qué hace | Quién lo llama |
|---|---|---|
| `kalman-api` | Webhook de Stripe y API para clientes | Stripe y los sistemas de tus clientes |
| `kalman-app` | La pantalla donde entra el cliente | Personas con navegador |

La demo pública sigue aparte, gratis en Streamlit Community Cloud, porque no
lleva ningún secreto.

## Dónde alojarlo

**Render**, plan gratuito para empezar. Motivos: tiene un plan gratis de
verdad, admite variables de entorno secretas, da HTTPS con certificado, y el
fichero `render.yaml` de este repositorio ya lo deja todo configurado.

El plan gratuito duerme el servicio tras 15 minutos sin visitas y tarda unos
50 segundos en despertar. Eso es aceptable al principio y **no rompe los
pagos**: cuando Stripe no recibe respuesta reintenta con espera creciente
durante tres días, así que el evento acaba entrando.

Cuando tengas el primer cliente que paga, sube `kalman-api` al plan de pago.
Son unos 7 dólares al mes y es lo primero que debe dejar de ser gratis, porque
es el que recibe el dinero.

## Pasos

### 1. Crear los servicios

Entra en [render.com](https://render.com), inicia sesión con GitHub y elige
**New**, luego **Blueprint**. Selecciona el repositorio `JoWyFF09/kalman`.
Render lee `render.yaml` y crea los dos servicios solo.

### 2. Rellenar los secretos

Render te pedirá cada variable marcada como secreta. En ambos servicios pon
los mismos valores que tienes en tu `.env`, con dos diferencias importantes:

- `STRIPE_SECRET_KEY`: aquí va la clave **real**, la que empieza por `sk_live_`.
  La de pruebas es sólo para tu ordenador.
- `APP_URL`: la dirección de `kalman-app`, que Render te da al crearlo. Tiene
  la forma `https://kalman-app.onrender.com`. Sin barra al final.

`STRIPE_WEBHOOK_SECRET` déjalo vacío de momento. Lo rellenas en el paso 4.

### 3. Comprobar que arrancan

Abre `https://kalman-api.onrender.com/healthz`. Debe responder:

```json
{"status": "ok", "engine": "2.0.0"}
```

Y abre `https://kalman-app.onrender.com`, que debe enseñar la pantalla de
acceso.

Si la aplicación carga pero se queda girando, es la conexión por websocket
detrás del proxy. Añade `--server.enableCORS false` al `startCommand` de
`kalman-app` y vuelve a desplegar.

### 4. Crear el webhook de Stripe

En el panel de Stripe, con el **modo real** activado, ve a Desarrolladores,
luego Webhooks, y añade un endpoint:

- URL: `https://kalman-api.onrender.com/v1/stripe/webhook`
- Eventos:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_failed`

Stripe te dará un secreto de firma que empieza por `whsec_`. Ponlo en
`STRIPE_WEBHOOK_SECRET` en los dos servicios de Render y redespliega.

Sin ese secreto la API responde 503 a todos los webhooks, a propósito: es
preferible que Stripe reintente a dar por bueno un evento sin comprobar.

### 5. Comprobarlo

```bash
python scripts/check_webhook.py
```

Te dice si el endpoint existe, si está activo, si la ruta es la correcta y si
le falta algún evento por escuchar.

### 6. La prueba que no te puedes saltar

Antes de enseñárselo a nadie, haz un pago completo **en modo de pruebas**:

1. Cambia tu `.env` local a la clave `sk_test_` y crea en Stripe, en modo de
   pruebas, los tres precios y un webhook apuntando a tu API.
2. Entra en la aplicación y elige un plan.
3. Paga con la tarjeta de prueba `4242 4242 4242 4242`, cualquier fecha futura
   y cualquier CVC.
4. Comprueba que el plan cambia solo:

```bash
python scripts/set_plan.py --listar
```

Si el plan no cambia, el webhook no está entrando. Míralo en Stripe, en la
pestaña de intentos del endpoint, donde se ve la respuesta que dio tu API.

**Esto es lo que más silenciosamente se rompe de todo el sistema.** Si el
webhook falla, el cliente paga, ve el cargo en su banco, y en Kalman sigue sin
plan. Ese cliente no vuelve.

## Un dominio propio

`kalman-app.onrender.com` funciona, pero para vender conviene algo tuyo. Un
`.es` cuesta unos 10 euros al año. En Render, dentro del servicio, en Settings
y luego Custom Domain, te dice qué registro DNS añadir.

Cuando lo tengas, actualiza `APP_URL` y la URL del webhook en Stripe.

## Límite de peticiones

Ya está puesto y no hay que configurar nada. Por minuto:

| Quién | Peticiones |
|---|---|
| Cualquiera, sin identificarse | 30 |
| Plan Starter | 60 |
| Plan Growth | 120 |
| Plan Scale | 600 |

Los contadores viven en la memoria del proceso. Con una sola copia de cada
servicio, que es el caso, el límite es exacto. Si algún día pones dos copias
detrás de un balanceador, cada una llevará su cuenta y el límite real será el
doble. Ese día se mueve a Redis y no cambia nada más.
