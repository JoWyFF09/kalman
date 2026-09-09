# De Spacenet AI a Kalman

Qué ha cambiado, por qué, y qué tienes que hacer tú.

## Resumen

| | Antes | Ahora |
|---|---|---|
| Ficheros de código | 3 | 24 |
| Líneas en el fichero mayor | 1.010 | 330 |
| Pruebas automáticas | 0 | 212 |
| Dependencias de instalación | ~600 MB | ~50 MB |
| Motor de detección | Autoencoder de 4 entradas | Reglas exactas más MAD |
| Alta de un cliente nuevo | Editar código y desplegar | Ninguna acción |

## Fallos de seguridad corregidos

### El muro de pago se saltaba escribiendo un email

En el código anterior, el usuario escribía un correo en una caja de texto y la
aplicación preguntaba a Stripe si ese correo tenía suscripción. Si la tenía,
desbloqueaba la sesión.

Cualquiera que supiese el correo de un cliente de pago entraba gratis. Y el
correo de una empresa está en su web y en su firma.

Ahora el derecho de uso lo escribe únicamente el webhook de Stripe, tras
verificar la firma criptográfica del evento, y se guarda asociado a la
organización que el servidor puso en la sesión de pago.

### Contraseñas en claro

Estaban en un fichero de configuración y se comparaban con el operador de
igualdad, que además filtra información por el tiempo que tarda. Ahora se
derivan con scrypt, con sal por usuario, y se comparan en tiempo constante.

### El botón que borraba todo

Había un botón en la barra lateral que ejecutaba `TRUNCATE TABLE` sobre los
datos de todos los clientes a la vez, sin confirmación. Se ha eliminado.

### Anonimización que no lo era

Se aplicaba SHA-256 sin clave a los correos y se presentaba como datos
anonimizados y seguros. Un diccionario de direcciones revierte esa tabla en
minutos, y bajo el Reglamento General de Protección de Datos eso es
seudonimización, no anonimización. Detalle en [PRIVACY.md](../PRIVACY.md).

### El precio viajaba desde el navegador

Cada pago enviaba el importe en la petición. Ahora se usan identificadores de
precio creados en Stripe, así que el importe lo controla Stripe y cambiarlo no
requiere desplegar.

## El informe ya no inventa cifras

El PDF anterior imprimía `ahorro_estimado = alertas * 15` y afirmaba haber
evitado un coste de tantos euros. Ese quince no venía de ningún sitio.

Entregar una cifra inventada en un documento con membrete, marcado como
confidencial, a una empresa que puede usarla para decidir, es un riesgo que no
compensa nada. Ahora el informe muestra sólo lo medido. Si el cliente quiere
euros, aporta él su coste por incidencia y el documento cita su origen.

## Fallos que encontró la prueba con datos realistas

Ninguno de estos tres se veía con datos escritos a mano. Aparecieron al pasar
el motor por un fichero generado de 3.208 filas.

1. **Teléfonos convertidos a coma flotante.** Una sola celda vacía obliga a
   pandas a convertir la columna entera a decimal. El número 612345678 pasaba a
   612345678.0, que al limpiar deja diez dígitos, y **todos** los teléfonos del
   fichero se marcaban como inválidos.
2. **La columna "Nº Cliente" se apropiaba del campo nombre**, porque su
   cabecera contiene la palabra "cliente". Después sus valores numéricos se
   marcaban como nombres falsos, uno por fila.
3. **El código postal corregido no cabía en su columna.** "01001" es texto y la
   columna era de enteros, así que pandas lanzaba una excepción y tumbaba el
   análisis completo.

Los tres tienen ahora una prueba de regresión en `tests/test_dtypes.py`.

## Sobre el nombre

Kalman viene del filtro de Kalman, el algoritmo que Rudolf Kálmán publicó en
1960 para estimar el estado real de un sistema a partir de mediciones ruidosas.
Se usó en la navegación del programa Apolo y hoy va a bordo de casi todo lo que
vuela, incluidos los cohetes.

Es lo que hace el producto y encaja con el sitio al que quieres llegar.

**Antes de usarlo en serio, comprueba dos cosas:** que el dominio esté libre y
que no haya una marca registrada en la clase de servicios informáticos en la
Oficina Española de Patentes y Marcas. Registrar la marca cuesta unos 150 euros
y evita tener que cambiar el nombre cuando ya tengas clientes.

## Qué tienes que hacer tú

### Ahora mismo, sin excusa

1. **Rota todos los secretos.** Cambia la contraseña de la base de datos en
   Supabase y regenera la clave de Stripe. Si alguna vez estuvieron en el
   repositorio, en un `secrets.toml` o en una captura de pantalla, están
   comprometidos.
2. **Borra el histórico si subiste datos.** El repositorio anterior contenía
   `clientes_sucios.csv`. Eran datos generados, así que no hay problema legal,
   pero acostúmbrate: un CSV con NIF e IBAN reales publicado en GitHub es una
   brecha notificable a la Agencia Española de Protección de Datos en 72 horas.
3. **Genera la clave de seudonimización** y guárdala fuera del servidor.

### Antes del primer cliente de pago

4. Crear los precios en Stripe y configurar el webhook.
5. Aplicar el esquema con `scripts/bootstrap.py`.
6. Comprobar que la copia de seguridad de la base **restaura de verdad**. Una
   copia que nunca se ha restaurado no es una copia.
7. Poner un límite de peticiones por minuto en la API.
8. Que un abogado revise el contrato de encargo del tratamiento.

### Lo que no es código

9. **Habla con veinte gestorías o pequeñas empresas** antes de tocar nada más.
   Enséñales el fichero de ejemplo con sus propios errores. Pregunta qué hacen
   hoy cuando un recibo vuelve devuelto y cuánto tiempo les come.

El código ya no es el cuello de botella. Lo era antes; ahora ya no.
