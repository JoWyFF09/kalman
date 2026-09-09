# Privacidad y protección de datos

Este documento describe cómo trata Kalman los datos personales. Está escrito
para que lo pueda leer el responsable de protección de datos de un cliente y
decidir en diez minutos si puede firmar.

## Precisión terminológica

Kalman **seudonimiza**. No anonimiza. La diferencia no es de estilo.

El artículo 4.5 del Reglamento General de Protección de Datos define la
seudonimización como el tratamiento que impide atribuir los datos a una persona
sin usar información adicional guardada por separado. Los datos seudonimizados
**siguen siendo datos personales** y siguen bajo el reglamento.

La anonimización, en cambio, es irreversible y saca los datos del ámbito del
reglamento. Kalman no la ofrece, porque un dato verdaderamente anónimo ya no
sirve para deduplicar ni para conciliar con el sistema del cliente.

### Por qué esto importa

Una versión anterior de este producto aplicaba SHA-256 sin clave a los correos
electrónicos y presentaba el resultado como datos anonimizados y seguros. Eso
era incorrecto por dos motivos:

1. El espacio de las direcciones de correo es pequeño y enumerable. Con un
   diccionario de direcciones se calculan sus hashes y se revierte la tabla
   entera en minutos.
2. Aunque fuese irreversible, la afirmación "anonimizado" en un documento
   entregado a un cliente le hace creer que puede tratar esos datos fuera del
   reglamento. Es una afirmación que puede costarle una sanción.

Kalman usa HMAC-SHA256 con una clave secreta que no sale del servidor. Sin la
clave no hay tabla precalculada que sirva. Con la clave, el responsable del
tratamiento puede revertir, que es exactamente lo que la ley espera.

## Qué se guarda

| Dato | ¿Se guarda? | Dónde |
|---|---|---|
| Fichero que subes | No | Se procesa en memoria y se descarta |
| Filas de tus clientes | No | Nunca se persisten |
| Recuento de incidencias por regla | Sí | Tabla `jobs` |
| Nombre del fichero, número de filas, duración | Sí | Tabla `jobs` |
| Email y contraseña de tus usuarios | Sí | Tabla `users`, contraseña con scrypt |
| Identificador de cliente de Stripe | Sí | Tabla `subscriptions` |
| Registro de accesos y descargas | Sí | Tabla `audit_log` |

Lo que se guarda de una ejecución es el informe, no los datos. Un fichero de un
millón de filas deja unos pocos kilobytes de recuentos.

## Base jurídica y papeles

Cuando procesas datos de tus clientes con Kalman:

- Tú eres el **responsable del tratamiento**.
- Kalman es el **encargado del tratamiento**.
- Hace falta un contrato de encargo conforme al artículo 28 del reglamento.
  Está incluido a partir del plan Scale y disponible bajo petición en los demás.

## Ubicación de los datos

La base de datos está en la Unión Europea. No hay transferencias
internacionales salvo las de Stripe para el cobro, que opera bajo sus propias
cláusulas contractuales tipo.

## Conservación

Los metadatos de las ejecuciones se conservan según el plan contratado, entre
7 y 365 días. Después se eliminan.

## Tus derechos

Para ejercer acceso, rectificación, supresión, portabilidad, limitación u
oposición, escribe a la dirección de soporte configurada en el despliegue. El
registro de auditoría permite responder a una solicitud de acceso con quién ha
hecho qué y cuándo.

## Brechas de seguridad

Ante una brecha que afecte a datos personales, la notificación a la Agencia
Española de Protección de Datos debe hacerse en **72 horas**. El registro de
auditoría existe para que ese plazo sea cumplible.

## Lo que este documento no es

No es asesoramiento jurídico. Antes de firmar un contrato de encargo del
tratamiento con un cliente, que lo revise un abogado especializado en
protección de datos.
