# IV ITSANET · Conteos pendientes y recuperación · v71

La ficha abierta puede guardar varios conteos y sus fotografías durante un corte de conexión. El dispositivo confirma primero una transacción en IndexedDB; solo entonces se limpia la ficha para el siguiente conteo. El servidor vuelve a validar cada movimiento al reconectar. La versión 71 es un candidato de desarrollo hasta realizar el pase controlado.

## Comprobación de esta entrega

La suite general aprobó 1.560 pruebas. Tras completar la respuesta de confirmación se verificaron 52 pruebas adicionales de API/gestión en SQLite y 30 en MySQL aislado. En MySQL, cuatro operarios generaron 40 movimientos y repitieron sus 40 solicitudes: persistieron exactamente 40 unidades y 40 eventos.

En navegador se cortó la red de un operario, se guardaron dos conteos y una fotografía, se recargó sin conexión y se recuperaron los pendientes. Otro operario confirmó 4 unidades; al reconectar se obtuvo un total de 9. Una respuesta perdida después del commit se reintentó sin duplicar, dejando 15 unidades. Se verificaron revisión de sobrante, restauración del mismo ID, rechazo de respaldo de otra cuenta y conservación de la ficha al simular cuota agotada. La fotografía quedó vinculada al conteo con enlace y clasificación PNC. No se usaron datos productivos ni se actualizó el servidor corporativo para estas pruebas.

## Trabajo del operario

1. Entrar con conexión y abrir la recepción. Se descargan las relaciones de lectura de los SKU y del cliente de esa recepción.
2. Escanear, escribir cantidad, pallet, ubicación y observación; adjuntar las fotos y pulsar **Guardar conteo**. El aviso inicial indica **Conteo pendiente de sincronizar**: confirma respaldo local, todavía no una escritura en el servidor.
3. Continuar con el siguiente código descargado. Un código desconocido o ambiguo exige recuperar conexión para resolverlo; no se inventa una equivalencia local.
4. Consultar **Respaldo de conteos en este dispositivo**: cantidad de pendientes de la recepción y de la cuenta, estados de envío y registros que requieren revisión. Los indicadores de recepción muestran solo totales confirmados del servidor.
5. Al recuperar conexión, mantener abierta la aplicación. El envío se reintenta automáticamente. **Pendiente sincronizado** confirma el servidor. Si la aplicación se cerró, volver con la cuenta original para recuperar la cola. No se inicia una sesión nueva sin conexión al servidor.
6. En **Revisar pendientes**, resolver sobrantes o el destino de las fotografías y reintentar. Un cierre, reparto desactualizado o falta de permiso conserva el pendiente; no se modifica ni fuerza el registro para hacerlo pasar.

Cuando no hay red tampoco llegan las presencias ni los conteos nuevos de otros equipos. Coordinar el pallet físico para no contar las mismas unidades dos veces. Antes del cierre, comprobar que todos los equipos hayan sincronizado; un supervisor no puede ver una captura que aún no salió de un dispositivo desconectado.

## Rescate y custodia

**Descargar respaldo** genera un JSON con datos, imágenes e identificadores originales. **Restaurar respaldo** permite recuperarlo en un navegador autenticado con la misma cuenta, conservando los IDs para que el servidor no duplique movimientos ya recibidos.

Usar la URL operativa habitual, el mismo navegador y perfil. Otra dirección, puerto, perfil o navegador tiene almacenamiento independiente. No limpiar los datos del sitio ni usar navegación privada para la operación. Se solicita almacenamiento persistente cuando el navegador lo permite; su concesión depende del equipo. Un borrado de datos o la pérdida física del dispositivo no puede recuperarse desde el servidor si el pendiente nunca llegó ni se exportó.

Si falla el almacenamiento o se agota la cuota, la ficha conserva sus campos y fotos y muestra el error: no anuncia un respaldo exitoso. Mantener la ficha abierta, conservar las imágenes originales y resolver el almacenamiento antes de continuar.

## Funcionamiento técnico

- Cola IndexedDB `itsanet-conteos-pendientes`, almacén `trabajos`, índice por cuenta. Se guardan el payload congelado, fotos Blob, ID de idempotencia, recepción, usuario, dispositivo y fecha de captura.
- Estados `PENDIENTE`, `ENVIANDO`, `REVISION` y `CONFIRMADO`. No se eliminan pendientes por antigüedad. El ACK persistido libera los binarios locales del trabajo; conserva el registro de confirmación.
- Arrendamiento atómico por trabajo, de 60 segundos y renovación cada 15, para coordinar pestañas de la misma cuenta. La idempotencia y los bloqueos del servidor siguen siendo la garantía frente a solicitudes repetidas.
- Reintentos progresivos de 5 a 60 segundos, señal `online` y botón manual; solicitudes del transportador limitadas a 30 segundos. No depende de Background Sync.
- Cada foto obtiene un enlace confirmado y se registra su progreso local antes de enviar el conteo. Si una respuesta se pierde, se conserva el ID; el servidor reconoce el evento y evita volver a sumar. La copia a Drive continúa por su cola existente y su estado se consulta por separado.
- `/api/auth/yo` comprueba la cuenta antes del lote; el servidor rechaza `operadorPendiente` o `operadorOrigen` ajenos a la sesión actual. Cambiar de cuenta no reenvía registros del usuario anterior.
- `capturadoEnDispositivo` y `dispositivoOrigen` quedan como información del evento. `creado_en` sigue siendo la fecha de registro del servidor; no se confunde con el reloj del handheld.
- El nuevo endpoint de lecturas locales requiere autenticación y limita la respuesta a los SKU de la recepción y a las relaciones de su cliente. No se cachean sesiones ni respuestas privadas de la API en el service worker.
- No hay nueva tabla MySQL, cambios de credenciales ni cambios de Apache en v71. La base del candidato incluye la tabla de relaciones añadida en v70.

## Mantenimiento

Inicio y fin de jornada: revisar pendientes por equipo y cuenta; resolver revisiones, confirmar fotos y verificar la sincronización antes del cierre. Ante cortes prolongados: exportar el respaldo por un canal interno autorizado. En cada actualización: conservar los datos del navegador y verificar una operación de recuperación, además del respaldo normal de MySQL y archivos del servidor. El respaldo del servidor no incluye los pendientes que siguen exclusivamente en los handhelds.

## Descargar los manuales con las capturas del Word

`scripts/preparar_manuales_desde_word.py` genera HTML privados y un ZIP usando el Word del responsable y las referencias sintéticas incluidas en `docs/muestras/manuales-v70`. Se puede ejecutar con Python estándar desde una copia separada del código; no arranca la aplicación, no conecta a MySQL o Google y no reinicia servicios.

Subir el Word al servidor desde el Explorador remoto de VS Code, ejecutar el generador con `--word`, `--salida` y `--revision`, y descargar el ZIP con clic derecho → **Descargar**. Los HTML incluyen sus imágenes y permiten imprimir a PDF desde Chrome/Edge. No guardar los documentos con capturas operativas bajo `firebase/public` ni publicarlos en el repositorio.
