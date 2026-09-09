# Puesta en marcha

## Lo que ya está hecho

### Stripe, cuenta de producción

Tres productos creados con precio recurrente mensual en euros. No hay ninguna
suscripción activa en la cuenta, así que nada de esto afecta a ningún cobro
existente.

| Plan | Precio | Identificador de precio |
|---|---|---|
| Kalman Starter | 29 €/mes | `price_1UDpAl2VrhLoHuYyMR6CJxpE` |
| Kalman Growth | 99 €/mes | `price_1UDpBE2VrhLoHuYyfZhS5USA` |
| Kalman Scale | 399 €/mes | `price_1UDpBZ2VrhLoHuYy4heZHflc` |

Los productos antiguos de Spacenet siguen ahí, activos y sin tocar. Cuando
tengas claro que no los quieres, archívalos desde el panel de Stripe. No los he
archivado yo porque archivar es tu decisión, no un cambio técnico.

### Supabase

El proyecto estaba pausado y lo he reactivado. Esquema aplicado con siete
tablas, todas con seguridad a nivel de fila activa, y **cero avisos de
seguridad** en el analizador de Supabase.

```
organizations   users   api_keys   subscriptions   usage_counters   jobs   audit_log
```

Nota: la tabla `clientes_purificados` del proyecto anterior no está en esta
base de datos. Sólo se han ejecutado sentencias de creación, así que no se ha
borrado nada.

## Lo que tienes que hacer tú

### 1. Rotar los secretos. Hoy.

Es lo primero y no admite aplazamiento. Si la clave de Stripe o la contraseña
de la base estuvieron alguna vez en el repositorio, en un `secrets.toml` o en
una captura de pantalla, considéralas comprometidas.

- Stripe: panel, Desarrolladores, Claves de API, revocar y crear otra.
- Supabase: ajustes del proyecto, base de datos, cambiar contraseña.

### 2. Crear el webhook de Stripe

Sin esto nadie puede activar un plan, porque el derecho de uso sólo lo escribe
el webhook.

En el panel de Stripe, Desarrolladores, Webhooks, añadir endpoint:

- URL: `https://TU-DOMINIO/v1/stripe/webhook`
- Eventos a escuchar:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_failed`

Copia el secreto de firma que te da Stripe, empieza por `whsec_`, y ponlo en
`STRIPE_WEBHOOK_SECRET`.

### 3. Generar la clave de seudonimización

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Va en `KALMAN_PSEUDONYM_KEY`. Guárdala también fuera del servidor. Si la
pierdes, los seudónimos ya emitidos dejan de poder cruzarse con lotes nuevos.

### 4. Crear tu organización y tu usuario

```bash
pip install -e ".[web,api,db,billing]"
python scripts/bootstrap.py --org "Kalman" --email tu@correo.com
```

Te pedirá la contraseña por consola y te enseñará una clave de API **una sola
vez**. Guárdala en ese momento.

### 5. Arrancar

```bash
streamlit run kalman/web/app.py
```

```bash
uvicorn kalman.api.main:app --reload
```

## Antes de cobrar a nadie

- [ ] Límite de peticiones por minuto en la API
- [ ] Copia de seguridad de la base restaurada de verdad una vez
- [ ] Contrato de encargado del tratamiento revisado por un abogado
- [ ] Comprobar que el nombre Kalman está libre como dominio y como marca en la
      Oficina Española de Patentes y Marcas
- [ ] Un adulto de confianza como titular del contrato, porque a los 17 no
      puedes obligarte por ti mismo en España

## Prueba de que funciona, en dos minutos

```bash
python scripts/generate_sample.py --filas 3000 --salida ejemplo.csv
python -m kalman.cli clean ejemplo.csv --out limpio.csv --cuarentena revisar.csv
```

Sobre 3.208 filas con errores realistas debe dar algo muy parecido a esto:

```
Filas analizadas:   3.208
Sin incidencias:    2.760
En cuarentena:        448
Grupos duplicados:    221
Tiempo:               594 ms
```

Ese fichero de ejemplo, con errores que un gestor reconoce como los suyos, es
tu mejor herramienta de venta. Enséñalo antes que ninguna otra cosa.

## Probar los planes de pago sin pagar

El derecho de uso solo lo concede el webhook de Stripe, asi que recien creada
tu organizacion se queda en el plan gratuito y no puedes probar lo que vendes.

Para desarrollo hay un script de consola:

```bash
python scripts/set_plan.py --listar
```

```bash
python scripts/set_plan.py --org kalman --plan growth
```

Para devolverlo al plan gratuito:

```bash
python scripts/set_plan.py --org kalman --plan free --estado inactive
```

Esto no contradice la regla de seguridad. La regla es que el navegador nunca
decide quien ha pagado, y ese camino sigue cerrado. Este script necesita la
cadena de conexion a la base de datos, es decir, credenciales de
administrador, y se niega a ejecutarse con KALMAN_ENV=production. Cada cambio
queda registrado en la tabla audit_log.
