# La API de Depot desde el servidor

Hasta ahora el maestro de productos entraba de una sola forma: alguien exportaba
un Excel del WMS y lo subía a mano. Sigue valiendo —no se ha quitado nada— pero
ya no es el único camino: el servidor habla directamente con la API de Depot.

## El protocolo, que no es el que parecía

El cliente que había en `app/services/depot.py` hablaba con una API inventada:
`GET /productos/{sku}` con un token fijo en `Authorization: Bearer`. El WMS no
tiene eso. Lo que tiene es lo que ya lleva meses funcionando en el proxy de
Apps Script:

| | |
|---|---|
| `GET /gettoken` | cabeceras `usuario`, `clave`, `cliente` → un token |
| `GET /getstock` | cabecera `token` → el inventario **entero** |

Tres consecuencias que condicionan todo lo demás:

1. **No hay búsqueda por SKU.** `/getstock` devuelve el inventario completo. Por
   eso el servidor lo baja entero a su espejo local (`productos`) y el escaneo
   resuelve contra el espejo. Un handheld no puede esperar a que baje el
   inventario de un cliente en cada código.
2. **El token se revoca.** Un 401 o un 403 en `/getstock` no es un fallo: es
   «pide otro». Se reintenta una vez. Si el segundo también lo rechaza,
   entonces sí son las credenciales, y ahí no se insiste: insistir bloquea la
   cuenta.
3. **No viene el código de barras.** `/getstock` no devuelve EAN. La validación
   por EAN no puede salir de aquí; hay que resolverla por otra vía.

Una fila de `/getstock` es una **posición**, no un producto: el mismo SKU viene
repetido en cada ubicación donde haya piezas. El servidor consolida por SKU.

## Dónde van las credenciales

En `/etc/iv-itsanet.env`, que solo lee root, el mismo archivo donde ya está la
contraseña de MySQL. **No** en el archivo del servicio (lo lee cualquier usuario
del servidor), **no** en el repositorio, **no** en la línea del cron.

```
DEPOT_BASE_URL=https://ec.itsanet.com/q_apidepot
DEPOT_USUARIO=...
DEPOT_CLAVE=...
DEPOT_CLIENTE=            # opcional: lo manda como cabecera al pedir el token
```

Después: `sudo systemctl restart iv-itsanet`.

Si están definidas en la terminal cuando se ejecuta `scripts/servicio.sh`, el
script las guarda ahí solo. Sin ellas el servidor arranca igual y trabaja contra
el espejo: lo que hacía hasta hoy no deja de funcionar.

## Cómo se usa

```bash
# ¿Valen las credenciales? Pide el token y sale, sin bajar nada.
.venv/bin/python scripts/sincronizar_depot.py --probar

# Bajar el maestro al espejo local.
.venv/bin/python scripts/sincronizar_depot.py
.venv/bin/python scripts/sincronizar_depot.py --cliente VENTURA
```

Y desde la aplicación, para un supervisor:

| | |
|---|---|
| `GET /api/catalogo/depot/probar` | distingue «sin credenciales», «credenciales rechazadas» y «el WMS no responde» |
| `POST /api/catalogo/depot/sincronizar` | baja el maestro; `?cliente=VENTURA` para uno solo |
| `GET /api/catalogo/depot/clientes` | de qué clientes hay data y de cuándo |
| `GET /api/catalogo/estado` | el cuadro completo, incluido qué variable falta |

El token no se devuelve nunca en ninguna respuesta, y la clave tampoco: con el
token se consulta el inventario de todos los clientes de esa credencial.

## Lo primero que hay que mirar al sincronizar

El recuento **por cliente**:

```
  por cliente:
    VENTURA              1843
    IMPOFACTOR            210
```

Con una sola credencial el WMS puede devolver varios clientes. Si aparece uno
que no se esperaba, o falta el que sí, la credencial no es la que se creía — y
eso es mejor saberlo antes de que un operario valide una recepción contra un
maestro ajeno.

## Una vez al día

```
crontab -e
40 5 * * * cd /home/bryan/IV_ITSANET && \
  set -a && . /etc/iv-itsanet.env && set +a && \
  .venv/bin/python scripts/sincronizar_depot.py >> /tmp/depot.log 2>&1
```

Un catálogo que solo se actualiza a mano se queda viejo el día que la persona
que lo subía está de vacaciones.

## Qué está comprobado y qué no

`tests/test_depot_api.py` (39 comprobaciones) le pone delante un WMS de mentira
—`httpx.MockTransport`— y comprueba el protocolo: las siete formas en que puede
venir el token, que las credenciales viajan en las cabeceras que espera el WMS y
no como `Bearer`, que un token revocado se renueva y la consulta sale adelante,
que solo se reintenta una vez, que una fila sin código no rompe la descarga, y
que el mismo SKU en dos ubicaciones es un producto y no dos.

Lo que **no** está comprobado: que el WMS real responda como se espera. Eso no
se puede saber sin credenciales y sin red hacia `ec.itsanet.com`, y es lo
primero que hay que ejecutar en el servidor:

```bash
.venv/bin/python scripts/sincronizar_depot.py --probar
```
