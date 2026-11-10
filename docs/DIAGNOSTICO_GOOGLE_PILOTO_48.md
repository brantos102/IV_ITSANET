# Verificación Google con 502 en el piloto

Interfaz `20261018-48`. Etiqueta `itsanet-20261018-diagnostico-google-48`.

El usuario confirmó que **Verificar remitente y Drive** falla con 502 desde
el enlace `trycloudflare.com`, mientras producción conecta y registra fotos.
La captura acredita que se guardó configuración, pero no que Google la verificó.

La frase anterior «El servidor respondió 502» aparece cuando no llega un
detalle JSON reconocible. No permite deducir por sí sola si falló la salida
de Docker a Google, el puente, el servidor o el túnel. No cambiar la clave
ni tocar la conexión productiva sin diagnosticar.

## Actualizar y obtener el estado desde Windows

En PowerShell de la PC anfitriona, dentro del repositorio del piloto:

```powershell
git pull --ff-only origin desarrollo-local; if ($LASTEXITCODE -eq 0) { .\scripts\publicar_pruebas.ps1; if ($LASTEXITCODE -eq 0) { .\scripts\diagnosticar_google_pruebas.ps1 } }
```

El lanzador actualiza el código conservando datos y conexiones. Reinicia el
enlace temporal y anuncia su nueva URL confirmada; puede cambiar. Usar esa URL
y recargar con Ctrl+F5. La actualización no copia nada al servidor empresarial.

Si el piloto ya está ejecutándose con el código actualizado, basta con:

```powershell
.\scripts\diagnosticar_google_pruebas.ps1
```

El diagnóstico selecciona únicamente el servicio `app` del proyecto
`iv-itsanet-pruebas-publicas-pc`. No lee el archivo de contraseñas iniciales.
Dentro de ese contenedor se rechaza la ejecución si no está marcada la variable
de PRUEBAS públicas. No reinicia servicios, modifica registros, crea carpetas,
copia imágenes ni envía correo. La única operación firmada que permite es
`estado` de Google; no depende del túnel para consultar Google.

Muestra versión frontend en disco, presencia de correo y duplicados en fichas,
presencia de conexiones/cifrado, estados agregados de la cola y resultado de
Google. No muestra claves, contraseñas, URL /exec, enlaces privados ni el
cuerpo original de respuestas externas. Se comprueban hasta tres conexiones
por ejecución para limitar la duración.

Después consulta el estado público del enlace guardado durante 10 segundos.
Este GET no autentica a un usuario ni repite una solicitud de envío.
El diagnóstico es lectura del estado actual; no certifica que el proceso de
la app haya recargado todo el código. El lanzador recrea su contenedor para ello.

Para revisar configuración sin contactar Google:

```powershell
.\scripts\diagnosticar_google_pruebas.ps1 -SinRed
```

`-SinRed` omite las verificaciones Google dentro del contenedor. El wrapper
todavía puede consultar el estado público del enlace guardado.

## Interpretar el resultado

| Resultado | Acción |
| --- | --- |
| Sin puente registrado | En PRUEBAS completar la ficha del supervisor y autorizar su conexión con carpeta/proyecto de pruebas. |
| Correo ausente o repetido | ADMIN corrige la ficha del entorno de pruebas; no duplicar cuentas. |
| Falta archivo de cifrado | Recuperar la clave privada de ese piloto y su respaldo; no reemplazarla para intentar descifrar credenciales existentes. |
| Google confirmado y enlace público sin respuesta | Revisar el túnel/PC y la URL vigente antes de modificar Google. |
| Timeout o error de conexión a Google | Revisar DNS, HTTPS saliente, proxy y certificados desde Docker/PC. La verificación no prueba envío de correo. |
| Clave no coincide | Comprobar la misma SERVIDOR_HMAC en la conexión de pruebas y en su proyecto. Conservar el puente de producción. |
| Carpeta o autorización rechazadas | Ejecutar `verificarGoogleServidor` con la cuenta propietaria, revisar carpeta y permisos y publicar Nueva versión. |
| Cuenta ejecutora diferente | Revisar el correo de la ficha y «Ejecutar como: Yo» del proyecto de pruebas. |
| `fotosAuditables: false` | Actualizar Servidor.gs y publicar Nueva versión del mismo despliegue de pruebas. |

Si Google queda confirmado, usar **Gestionar → Drive** en la recepción de
pruebas y la acción de copia correspondiente; no volver a adjuntar fotos
ya guardadas. El diagnóstico no realiza esa copia automáticamente.

## Cambios de esta edición

- La consulta Google `estado` tiene lectura/escritura de 25 s y conexión de 8 s
  por petición HTTP. Las transferencias y finalización conservan su timeout
  de 120 s y sus errores para mantener el tratamiento de resultados inciertos.
- Los fallos de red de `estado` devuelven mensajes controlados sin secretos.
  El número de redirecciones y los límites HTTP no son un cronómetro global
  del despliegue externo.
- Un 502/503/504 o error 52x sin JSON se distingue de un error específico del
  puente. La interfaz no muestra HTML externo ni reintenta automáticamente.
- Guardar configuración sigue siendo distinto de verificar Google. Las
  comprobaciones de correo, identidad y firma no se omiten.

## Verificaciones

- Pruebas Python: diagnóstico restringido, lectura sin escrituras, ausencia
  de correo/conexión, duplicados, redacción de secretos, consulta exclusiva de
  estado, timeout corto y conservación de transferencias/errores originales.
  Regresión de Drive, conexión personal y entregas incluida.
- JavaScript: 502 HTML sin filtración ni reintento; 502 JSON conserva el motivo
  Google. Sintaxis y grafo de páginas/imports comprobados.
- PowerShell 7 sobre Linux con Docker/HTTP simulados: selección exacta del
  proyecto, piloto detenido/ambiguo, errores del helper, enlace vigente con
  `/app/`, enlace caído y ausencia de comandos de mutación.
- En un contenedor propio de PRUEBAS se ejecutó el helper con `--sin-red`.
  La pantalla ADMIN real se comprobó con respuestas 502 simuladas para el
  botón Verificar remitente y Drive, sin modificar configuración.

No se consultaron la PC, el Drive ni las credenciales del usuario. La causa
concreta de su 502 permanece pendiente del informe del diagnóstico.
No se acredita una prueba física de Windows ni de Google real con estos dobles.
