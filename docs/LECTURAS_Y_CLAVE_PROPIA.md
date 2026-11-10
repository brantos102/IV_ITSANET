# Lecturas de etiquetas, contraseña propia y remitentes

Entrega `itsanet-20261016-lecturas-claves-correo`, frontend `20261016-33`.

## Código de pieza dentro de una etiqueta

El escaneo conserva la lectura original. Los guiones, espacios y apóstrofos
se interpretan como separadores al consultar candidatos; no se modifica la
identidad de los productos del catálogo ni se crea una equivalencia automática.

Ejemplos: `2GJ'805'901'C '04100000` puede identificar `2GJ805901C` y
`2GJ-941-113       00000` puede identificar `2GJ941113`, siempre que la pieza
exista en el packing list o catálogo. La pantalla muestra la lectura, el código
consultado y la explicación. El conteo conserva esa información en su bitácora.
Consultar un código por sí solo no registra unidades.

Si aparecen varios códigos existentes, el operario elige cuál consultar. Sin
separación entre pieza y ceros finales se ofrecen coincidencias existentes para
confirmar; no se eliminan ceros de forma general. `000123`, `P555` y los códigos
completos terminados en ceros conservan su identidad cuando existen.

Los QR con campos SKU/número de pieza conservan su extracción específica:
cantidad, lote y fecha no sustituyen al SKU. Una lectura con varios campos que
no se reconoce solicita escanear o escribir solo la pieza, antes de permitir un
registro adicional. Una diferencia de dígitos sigue requiriendo confirmación.

## Cada usuario cambia su contraseña

Inicio → junto al nombre de la cuenta → **Cambiar mi contraseña**. Disponible
para OPERADOR, SUPERVISOR y ADMIN que acceden con contraseña.

El formulario pide contraseña actual, nueva (6–128 caracteres) y repetición de
la nueva. La contraseña actual incorrecta muestra su propio aviso y permite
corregirla sin declarar que la sesión caducó. No permite modificar otra cuenta.
Al guardar, conserva la sesión actual y revoca las demás sesiones del mismo
usuario, retirando también sus otras presencias activas. No cambia roles,
conteos ni sesiones de otros usuarios.

La operación bloquea la ficha de usuario en MySQL para impedir que dos cambios
simultáneos con la contraseña anterior se sobrescriban. El inicio de sesión
comparte ese bloqueo para evitar crear una sesión con una contraseña que acaba
de reemplazarse. La auditoría registra autor, fecha y cantidad de sesiones
cerradas; no registra contraseñas ni sus hashes.

No se rotan contraseñas existentes al desplegar. Las claves de MySQL, HMAC,
OAuth, Drive y VPN siguen siendo configuraciones diferentes.

## Prueba después del pase

1. Recargar la app y abrir una recepción existente. Probar las dos lecturas
   de ejemplo si esos SKU están en su lista o catálogo; revisar la explicación
   y cancelar la ficha sin registrar unidades.
2. Probar un código con ceros auténticos y una lectura que contenga dos SKU;
   la segunda debe pedir selección.
3. Con una cuenta de prueba, abrir dos sesiones en navegadores distintos.
   Cambiar la contraseña desde una; comprobar que esa sesión sigue abierta,
   la otra necesita volver a entrar y la contraseña anterior ya no permite
   iniciar sesión. Comprobar que otra cuenta continúa trabajando.

El pase usa el script con respaldo y conserva las recepciones y usuarios de
producción; no requiere trasladar datos de desarrollo ni cambiar el esquema.

## Remitente del informe

ADMIN → Operación → **Remitente de informes** permite fijar el correo
responsable y decidir si los supervisores pueden elegir su correo propio.
El cierre propone siempre **Responsable**. El correo propio solo aparece si
su ficha está activa como supervisor/ADMIN y tiene un puente Google configurado.
Ninguna de las opciones acepta escribir un remitente arbitrario.

Para esta operación se indicó como responsable `bespinoza@itsanet.com`:
vincular ese correo a su cuenta en Usuarios y guardar su puente en Administración
→ Drive y envío de correo. Escribirlo también como responsable predeterminado
y guardar la configuración operativa. No requiere cambiar código ni otra clave.

Si el campo responsable está vacío, se considera el responsable de la recepción
y, si no tiene correo registrado, el único puente configurado. Si existen varios
puentes, ADMIN debe elegir un responsable; no se toma uno al azar. Cuando un
responsable no está listo, no se cambia al correo personal de forma automática.

La cuenta elegida y el autor del cierre quedan separados en la entrega y su
auditoría. El servidor comprueba que la cuenta confirmada en pantalla no haya
cambiado antes de encolar. Las entregas ya pendientes conservan su remitente
original. Google debe confirmar la misma identidad antes de subir los archivos
y al terminar. Un acuse final ambiguo pasa a revisión y no se reenvía solo.

MailApp envía desde la cuenta Google que ejecuta el despliegue; `replyTo` no
cambia el remitente real. El Apps Script de cada cuenta debe desplegarse como
**Ejecutar como: Yo**, con autorización de Drive y correo y acceso a la carpeta
que se comparte con el destinatario.

Los errores de Google ahora distinguen cuenta (`userinfo.email`), correo,
cuota, acceso a Drive, carpeta raíz, identidad y versión del puente cuando su
respuesta permite identificar la causa. No se muestran textos sin filtrar que
puedan incluir secretos. Si Google no identifica la causa, ejecutar
`verificarGoogleServidor` desde el selector de funciones del editor Apps Script
con la cuenta responsable y revisar el registro. Esa comprobación no envía correo.

Las comprobaciones automáticas de envío usan un puente simulado. Para validar
la conexión real, ADMIN puede verificar remitente/Drive y después enviar una
prueba explícita al destinatario autorizado. Una tarea en cola no demuestra
que el correo haya llegado.

## Verificación de esta entrega

- Suite del proyecto: 938 pruebas aprobadas.
- MySQL en una base desechable separada: cambio simultáneo de contraseña,
  conservación de sesión actual, revocación de otras sesiones y 29 pruebas
  de remitentes/entregas aprobadas.
- Chromium a 390 px: cambio de contraseña de OPERADOR, dos lecturas de las
  imágenes, explicación visible y lectura original conservada al contar.
- Navegador móvil: responsable preseleccionado, correo personal opcional,
  comprobación de cuenta confirmada y panel de configuración ADMIN. La petición
  de envío externo se interceptó para impedir un correo real durante la prueba.
