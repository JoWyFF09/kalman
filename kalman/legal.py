"""Condiciones de uso y política de privacidad.

Están en código y no en un fichero suelto por dos motivos: quedan versionadas
en el historial, de modo que se puede demostrar qué texto aceptó un cliente el
día que se dio de alta, y se pueden comprobar con pruebas.

AVISO IMPORTANTE
----------------
Esto es un borrador de trabajo, no un texto revisado por un abogado. Cubre lo
básico y está redactado con sentido común, pero antes de firmar un contrato
con una empresa, y desde luego antes de tratar datos personales de sus
clientes, tiene que revisarlo alguien que sepa de protección de datos. En
particular falta el contrato de encargado del tratamiento del artículo 28 del
reglamento europeo, que es un documento aparte y obligatorio.

Los huecos marcados con corchetes hay que rellenarlos con datos reales. Una
página legal con un corchete sin rellenar es peor que no tenerla.
"""

from __future__ import annotations

#: Fecha de la versión vigente. Si cambia el texto, cambia esto: es lo que
#: permite saber qué aceptó cada cliente.
LEGAL_VERSION = "2026-09-11"

TERMS = f"""
### Condiciones de uso

**Versión {LEGAL_VERSION}**

#### 1. Qué es Kalman

Kalman es un servicio que revisa ficheros de datos de clientes y señala los
errores que encuentra: identificadores fiscales y cuentas bancarias cuyo
dígito de control no cuadra, teléfonos y códigos postales mal formados, y
registros duplicados.

Kalman **señala y propone**. No corrige nada en tus sistemas ni accede a
ellos. Las decisiones sobre tus datos las sigues tomando tú.

#### 2. Quién presta el servicio

[NOMBRE O RAZÓN SOCIAL], con identificación fiscal [NIF O CIF] y domicilio en
[DIRECCIÓN]. Para cualquier asunto relacionado con el servicio: [EMAIL].

#### 3. Tu cuenta

Necesitas una cuenta para usar el servicio. Eres responsable de mantener tu
contraseña a salvo y de lo que se haga desde tu cuenta. Avísanos en cuanto
sospeches que alguien más ha entrado.

Debes tener capacidad legal para contratar. Si actúas en nombre de una
empresa, debes estar autorizado a obligarla.

#### 4. Planes y pago

El plan gratuito tiene un límite mensual de filas y no requiere tarjeta. Los
planes de pago se facturan por adelantado, cada mes, y se renuevan solos hasta
que los canceles.

Puedes cancelar cuando quieras desde el portal de facturación. La cancelación
surte efecto al final del periodo que ya has pagado, y no se devuelve la parte
no consumida de ese periodo salvo que la ley lo exija.

Los precios pueden cambiar. Si cambian, se te avisa con al menos 30 días y el
cambio se aplica en tu siguiente renovación.

#### 5. Qué no puedes hacer

- Subir datos sobre los que no tengas derecho a tratarlos.
- Intentar saltarte los límites de uso, acceder a datos de otros clientes o
  interferir en el funcionamiento del servicio.
- Revender el servicio sin un acuerdo por escrito.

#### 6. Lo que Kalman garantiza, y lo que no

Las comprobaciones de dígito de control de NIF, NIE, CIF e IBAN son
deterministas: se calculan con el algoritmo oficial y su resultado es exacto.

La detección de duplicados y de valores atípicos es estadística. Puede señalar
algo correcto o pasar por alto algo incorrecto, y por eso Kalman propone y no
decide. Revisa siempre antes de actuar.

El servicio se presta tal cual, sin garantía de disponibilidad ininterrumpida.
Se hace lo razonable por mantenerlo en funcionamiento.

#### 7. Responsabilidad

Kalman no responde de las decisiones que tomes a partir de sus resultados ni
del lucro cesante. En cualquier caso, la responsabilidad total queda limitada
al importe que hayas pagado en los doce meses anteriores al hecho que la
origine.

Nada de esto limita la responsabilidad que la ley no permite limitar.

#### 8. Tus datos

El tratamiento de datos personales se rige por la política de privacidad, que
forma parte de estas condiciones.

#### 9. Cambios y terminación

Podemos cambiar estas condiciones avisándote con al menos 30 días. Si no estás
de acuerdo, puedes cancelar.

Podemos suspender una cuenta que incumpla estas condiciones, avisando salvo
que la gravedad no lo permita.

#### 10. Ley aplicable

Se aplica la ley española. Para cualquier disputa, los juzgados del domicilio
del prestador, salvo que seas consumidor, en cuyo caso se aplican los fueros
que la ley te reconozca.
"""


PRIVACY = f"""
### Política de privacidad

**Versión {LEGAL_VERSION}**

#### 1. Quién trata tus datos

[NOMBRE O RAZÓN SOCIAL], [NIF O CIF], [DIRECCIÓN]. Contacto: [EMAIL].

#### 2. Dos cosas distintas, y conviene no mezclarlas

**Tus datos de cuenta.** Tu nombre de empresa, tu correo y tu contraseña. De
esto somos responsables del tratamiento.

**Los datos que subes para analizar.** Los de tus clientes. De esos el
responsable eres tú, y Kalman actúa como encargado del tratamiento. Para eso
hace falta firmar un contrato de encargo, que se facilita aparte.

#### 3. Qué se guarda de los ficheros que subes

**El fichero no se guarda.** Se procesa en memoria y se descarta al terminar.

De cada análisis se conserva únicamente el recuento: cuántas filas se
revisaron, cuántas incidencias de cada tipo, cuánto tardó y qué columnas se
reconocieron. Ni una sola fila de tus clientes.

#### 4. Qué se guarda de tu cuenta

| Dato | Para qué | Cuánto tiempo |
|---|---|---|
| Correo y contraseña cifrada | Darte acceso | Mientras tengas cuenta |
| Nombre de la empresa | Identificar tu espacio y facturar | Mientras tengas cuenta |
| Recuento de análisis | Enseñarte tu historial y tu consumo | Según tu plan, de 7 a 365 días |
| Registro de accesos | Seguridad y obligaciones legales | 12 meses |
| Identificador de cliente de Stripe | Cobrar | Mientras tengas suscripción |

#### 5. Base jurídica

Tratamos tus datos de cuenta para poder ejecutar el contrato que tenemos
contigo. El registro de accesos se basa en nuestro interés legítimo en la
seguridad del servicio.

#### 6. Quién más los ve

- **Supabase**, que aloja la base de datos, dentro de la Unión Europea.
- **Render**, que aloja la aplicación, dentro de la Unión Europea.
- **Stripe**, sólo para cobrar, bajo sus propias cláusulas contractuales tipo.

No se venden ni se ceden a nadie más.

#### 7. Seudonimización, que no es anonimización

Kalman puede sustituir los datos personales de tus ficheros por códigos
estables. Eso es **seudonimización** según el artículo 4.5 del reglamento: el
dato sigue siendo dato personal y sigue protegido por la norma. No es
anonimización, y nadie debería decirte que lo es.

#### 8. Tus derechos

Puedes pedir acceso, rectificación, supresión, portabilidad, limitación y
oposición escribiendo a [EMAIL]. Si crees que no se han atendido bien, puedes
reclamar ante la Agencia Española de Protección de Datos.

#### 9. Brechas de seguridad

Ante una brecha que te afecte, se te notificará y se comunicará a la Agencia
Española de Protección de Datos en el plazo legal de 72 horas.
"""

#: Los huecos que hay que rellenar antes de publicar esto de verdad.
PLACEHOLDERS = (
    "[NOMBRE O RAZÓN SOCIAL]",
    "[NIF O CIF]",
    "[DIRECCIÓN]",
    "[EMAIL]",
)


def pending_placeholders() -> list[str]:
    """Devuelve los huecos sin rellenar que quedan en los textos legales.

    Una página legal con un corchete sin rellenar es peor que no tenerla: deja
    claro que nadie la ha leído. Hay una prueba que avisa mientras queden.
    """
    return sorted({p for p in PLACEHOLDERS if p in TERMS or p in PRIVACY})
