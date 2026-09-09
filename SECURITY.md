# Seguridad

## Comunicar una vulnerabilidad

No abras una incidencia pública. Escribe a la dirección de soporte del
despliegue con los pasos para reproducirla. Se responde en 72 horas y se
publica el arreglo antes de dar detalles.

## Decisiones de diseño

### Contraseñas

Se derivan con **scrypt**, con sal aleatoria por usuario y parámetros
almacenados junto al hash para poder endurecerlos sin invalidar los existentes.
La comparación final usa `hmac.compare_digest`, que tarda lo mismo acierte o
falle.

Tras cinco intentos fallidos la cuenta se bloquea 15 minutos. El mensaje de
error es idéntico exista el usuario o no, para no confirmar qué correos están
dados de alta.

### Derecho de uso

Lo concede **exclusivamente** el webhook de Stripe, tras verificar la firma
criptográfica del evento, y se escribe en la tabla `subscriptions`. El
navegador nunca decide si alguien ha pagado.

Esto cierra el fallo más grave de la versión anterior, donde el usuario escribía
un correo en una caja de texto y la aplicación desbloqueaba el producto si ese
correo tenía suscripción. El correo de un cliente aparece en su web y en su
firma, así que cualquiera entraba gratis.

### Aislamiento entre clientes

Además del filtro en cada consulta, PostgreSQL aplica **seguridad a nivel de
fila**. La conexión fija la organización activa con `SET LOCAL app.current_org`
y las políticas impiden ver o escribir filas de otra organización. Un olvido en
una cláusula `WHERE` deja de ser una fuga de datos entre clientes.

`SET LOCAL` limita el efecto a la transacción, de modo que una conexión
devuelta al pool no arrastra la organización del usuario anterior.

### Claves de API

Se generan con 256 bits de entropía y prefijo `kal_`, que permite detectarlas
si aparecen en un repositorio público. Sólo se guarda su SHA-256. Si el cliente
pierde la clave se regenera, no se recupera.

Se aceptan únicamente en la cabecera `Authorization`. Nunca en la URL: las URL
acaban en los registros del servidor, en el historial del navegador y en la
cabecera `Referer` que se envía a terceros.

### Datos personales

El fichero que sube el cliente se procesa en memoria y no se persiste. De cada
ejecución se guarda el recuento de incidencias, no las filas. Ver
[PRIVACY.md](PRIVACY.md).

La seudonimización usa HMAC-SHA256 con clave de servidor, no un hash sin clave.

### Operaciones destructivas

La versión anterior tenía un botón que ejecutaba `TRUNCATE TABLE` sobre todos
los clientes a la vez, sin confirmación. Se ha eliminado. Las operaciones
destructivas se hacen desde una consola con acceso directo a la base y quedan
registradas.

## Lista de comprobación antes de aceptar el primer cliente de pago

- [ ] `.env` fuera del repositorio y confirmado en `.gitignore`
- [ ] Claves de Stripe y contraseña de base rotadas si alguna vez se subieron
- [ ] `KALMAN_ENV=production` y `APP_URL` con HTTPS
- [ ] Webhook de Stripe creado y su secreto configurado
- [ ] Esquema aplicado y seguridad a nivel de fila activa
- [ ] Copia de seguridad de la base comprobada, restaurando de verdad
- [ ] Clave de seudonimización guardada fuera del servidor
- [ ] Contrato de encargo del tratamiento revisado por un abogado

## Historial de vulnerabilidades corregidas

| Fecha | Problema | Estado |
|---|---|---|
| 2026-09 | Desbloqueo del producto escribiendo el correo de otro cliente | Corregido |
| 2026-09 | Contraseñas en claro comparadas con el operador de igualdad | Corregido |
| 2026-09 | `TRUNCATE` global sin confirmación desde la interfaz | Eliminado |
| 2026-09 | SHA-256 sin clave presentado como anonimización | Corregido |
| 2026-09 | Precio enviado desde el cliente en cada pago | Corregido |
