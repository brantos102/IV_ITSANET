# Acceso desde equipos autorizados

La regla solicitada admite un móvil y una laptop por cuenta. Con el control
activo solo hay una sesión válida por usuario: al entrar desde el otro equipo
aprobado se cierra la anterior. Un equipo nuevo no obtiene acceso solo por
conocer el usuario y la contraseña.

El control se entrega desactivado. La preparación de equipos se realiza antes
de activarlo y no altera recepciones, conteos, fotos ni usuarios existentes.

## Preparación y activación

1. Instalar el código con el actualizador de producción y su respaldo habitual.
   El inicio crea solo las dos tablas nuevas; no cambia el esquema de sesiones
   anterior ni convierte tablas operativas.
2. En ADMIN → Roles y reglas → Equipos autorizados, usar «Registrar este equipo
   de ADMIN». Introducir la cuenta y contraseña propias y describir el equipo.
3. Verificar presencialmente a la persona, el equipo y los ocho caracteres del
   código de solicitud. Aprobarlo. La etiqueta y el tipo declarados no son por
   sí solos una prueba del equipo.
4. Preparar los equipos de los usuarios. Cada uno solicita la inscripción desde
   su propio navegador en `/app/equipo.html`, con su cuenta y contraseña propias;
   ADMIN verifica y aprueba un móvil y una laptop. Cuando
   el control ya esté activo, el acceso rechazado muestra el formulario de
   solicitud. Durante la preparación se puede abrir la solicitud desde la
   página de solicitud anterior. El propietario no necesita entrar con una
   cuenta de administrador ni compartir su contraseña para solicitar el alta.
5. Activar el control desde el equipo aprobado de ADMIN. El servidor rechaza la
   activación si el equipo actual del administrador no está aprobado. Las
   sesiones previas deben volver a autenticarse. Coordinar primero la
   sincronización de registros pendientes en los equipos de la operación.

Un reemplazo exige indicar el ID del equipo anterior. La aprobación revoca el
anterior y cierra sus sesiones. No se admiten dos móviles o dos laptops
autorizados de la misma cuenta. Revocar no elimina el registro histórico.
La desactivación requiere motivo y no vuelve a habilitar sesiones antiguas.

## Mecanismo y tablas

- `app_dispositivos_usuario`: operador, tipo, nombre, estado, fechas y responsable
  de aprobación. Guarda únicamente SHA-256 de una credencial aleatoria de 256
  bits; no guarda su valor original ni la contraseña del usuario.
- `app_sesiones_dispositivo`: vínculo FK de la sesión con el equipo. Se elimina
  por cascada al cerrar la sesión; el historial de aprobaciones, reemplazos,
  revocaciones y accesos permanece en `app_auditoria_general`.
- La credencial del navegador viaja en una cookie `HttpOnly`, `SameSite=Lax` y
  `Secure` cuando el sitio usa HTTPS o `VAL_COOKIE_SECURE=1`. La solicitud usa
  una cookie pendiente separada; crearla no sustituye una credencial aprobada.
- Cada petición autenticada comprueba la sesión, su vínculo, la cuenta y la
  autorización del equipo. Copiar únicamente el token de sesión a otro
  navegador no permite acceder. El token deja de publicarse en el JSON del
  login cuando el control está activo.
- Tanto la entrada con contraseña como la entrada Google utilizan el mismo
  control central. Autorizar Gmail/Drive no aprueba equipos de acceso.
- El canal de actualización revalida antes de emitir información y al esperar
  actividad. Un relevo de usuario en el mismo navegador cierra la sesión previa.
- Las escrituras de acceso y aprobación se serializan por la fila del operador
  para evitar dos aprobaciones concurrentes del mismo tipo en MySQL/InnoDB.

## Alcance real y operación

El registro reconoce una credencial de un perfil de navegador. No es una
atestación de hardware, un número de serie, una prueba biométrica ni una prueba
de que una persona esté físicamente en la bodega. Una IP o un User-Agent que el
cliente puede declarar no se utilizan como identidad del equipo.

Borrar las cookies, usar otro navegador o un perfil privado requiere una nueva
inscripción. Las credenciales completas del navegador deben protegerse: copiar
todas sus cookies o prestar un equipo ya abierto no queda impedido por este
control. Las cuentas siguen siendo personales; no se debe atribuir una firma
electrónica a una identidad física comprobada por el solo hecho de que exista
un login válido. La revisión presencial y la custodia del equipo complementan
el control técnico.

El historial previo se conserva. Este control no puede demostrar de forma
retroactiva quién utilizó una cuenta que se hubiera prestado antes.

La restricción a la red de la bodega debe mantenerse en los controles de red y
del servidor administrados por TI. Este cambio no modifica Apache, el acceso
corporativo ni las reglas de red; no acredita presencia geográfica.

Los pendientes locales siguen perteneciendo a su cuenta original. Una sesión
revocada no puede sincronizarlos hasta volver a entrar desde un equipo aprobado;
no se reasignan ni se eliminan para permitir el relevo.

## Validación

Las pruebas automatizadas comprueban preparación sin bloqueo, aprobación,
reemplazo, revocación, dos tipos de equipo, sesión única, login Google, cookies,
roles y cierre de canales. Se ejecutan en base temporal aislada. La activación
real requiere comprobar dos equipos preparados y un navegador no registrado
en el servidor corporativo, sin usar la base de producción para ejecutar pytest.
