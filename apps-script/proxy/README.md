# Proxy de Depot en Apps Script

Para el servidor MySQL, consultar [la guia local](../../docs/OPERACION_LOCAL.md).
`Proxy.gs` corresponde a **Codigo.gs** y `Clientes.gs` a **Clientes.gs** en
el proyecto existente. Agregar `Servidor.gs` para entregas HMAC desde el
servidor; no requiere Firebase ni registra conteos en Sheets. La autenticacion
Firebase anterior se conserva mientras se comprueba la retirada del hosting.

Pieza de servidor para el plan Spark de Firebase, que no incluye Cloud Functions
ni Cloud Storage.

| Archivo | Qué es |
|---|---|
| `Proxy.gs` | El proxy completo. Se pega en un proyecto de Apps Script |
| [`../test/proxy.test.js`](../test/proxy.test.js) | 18 pruebas sobre un simulador de los servicios |

```bash
node apps-script/test/proxy.test.js
```

## Qué resuelve

1. **Guarda las credenciales de Depot** donde el navegador no las ve.
2. **Esquiva CORS y el contenido mixto.** La API es `http://` y la app será
   `https://`: el navegador bloquearía la llamada directa, el servidor no.
3. **Sube las fotos a Drive**, que reemplaza a Cloud Storage.
4. **Envía el informe final** por correo.

No participa en el escaneo. Esa ruta es el navegador contra Firestore, y por eso
sigue costando 50-150 ms.

## Seguridad

Cada petición trae el token de sesión de Firebase del operario. Se verifica
contra Google y se exige que el correo sea del dominio corporativo, antes de
tocar el WMS. La verificación se cachea 5 minutos para no añadir latencia.

Publicado como "Cualquier usuario" porque la app necesita llamarlo, pero sin
sesión válida y del dominio no hace absolutamente nada. Hay pruebas que lo
vigilan.

## El token

```
Consulta → caché del script (0 ms) → propiedades (~10 ms) → GET /gettoken/ (~500 ms)
```

Un solo `gettoken` al día. El caché de Apps Script expira a las 6 horas, así que
las propiedades lo sostienen el resto de la jornada. Si el WMS revoca el token
antes de tiempo, la llamada que recibe el 401 lo renueva y reintenta sola.

El valor del token no sale nunca: `estadoToken` solo dice si está vigente y
cuántos minutos le quedan.

## Diagnóstico

Desde el editor, sin pasar por la app:

- `verificarConfiguracion()` — qué propiedades faltan
- `probarDepot()` — prueba `gettoken` y `getstock` por separado, e imprime los
  nombres de campo que devuelve el WMS

Instalación paso a paso: [`firebase/INSTALACION.md`](../../firebase/INSTALACION.md)
