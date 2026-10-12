# VAL VENTURA v3 — Firebase

Tercera arquitectura de la app de validación física. Ver
[`ARQUITECTURA.md`](ARQUITECTURA.md) para el análisis que llevó a ella.

**Firebase es Google Cloud**, así que cumple la política de TI de no salir de
Google, y además elimina el techo de rendimiento de Apps Script.

---

## Por qué existe esta versión

Medición sobre el archivo real de la recepción VW:

| | Apps Script + Sheets | Firestore |
|---|---|---|
| Celdas leídas por escaneo | **1.067.029** | 1 documento (~200 bytes) |
| De esas, las que usa | 129 | 129 |
| Latencia por escaneo | 1–3 s | 50–150 ms |
| Concurrencia | `LockService` pone a todos en fila | `increment()` atómico por contador |
| Tiempo real | No existe | `onSnapshot` nativo |

El factor de desperdicio era de **8.272×**: para saber si un SKU existe había que
recorrer las 15.687 filas del maestro, en cada escaneo. Una hoja de cálculo no
tiene índices.

---

## Estado

| Pieza | Estado |
|---|---|
| Modelo de datos y reglas de seguridad | Listo |
| Registro de conteos (transaccional, idempotente) | Listo · 21 pruebas |
| Administración de operarios y credenciales | Listo · 15 pruebas |
| Adaptador de Depot + resolución de códigos | Listo, contra mock |
| Importador del packing list | Pendiente |
| Cierre, informe por correo y exportación | Pendiente |
| Cliente PWA | Pendiente |
| Conexión a la API real de Depot | **Bloqueado**: faltan los endpoints |

```bash
cd functions && npm test      # 36 pruebas, sin desplegar nada
```

Las pruebas corren sobre un simulador de Firestore que implementa transacciones
optimistas con reintento e `increment()` real, así que un fallo ahí es un fallo
de verdad.

---

## Modelo de datos

```
usuarios/{uid}                     perfil y rol

recepciones/{id}
  ├── lineas/{lineaId}             packing list inmutable
  ├── skus/{sku}                   agregado en vivo  ← lo que lee el operario
  ├── eventos/{idempotencyKey}     libro mayor append-only
  └── adicionales/{sku}            SKU fuera de la lista (pestaña aparte)

productos/{sku}                    caché del maestro Depot
codigos/{codigo}                   índice inverso: SKU, EAN o alterno → sku
config/depot                       configuración (sin credenciales)
```

### Las dos escrituras de un conteo

Cada conteo escribe en una sola transacción:

1. **`eventos/{idempotencyKey}`** — el libro mayor. Nunca se modifica ni se
   borra; corregir es registrar una reversa. De aquí salen la trazabilidad y los
   KPIs históricos.
2. **`skus/{sku}`** — el agregado, con `increment()`. Existe para que el operario
   lea un documento en vez de sumar N eventos, y para que `onSnapshot` propague
   el cambio a los demás dispositivos al instante.

El id del evento **es** la clave de idempotencia: un reintento escribe el mismo
documento, no uno nuevo. El doble disparo del lector no suma dos veces.

---

## Dos detalles que costaron una prueba cada uno

**El punto del subpallet.** Firestore trata el punto como separador de ruta:
escribir `pallets.B04.1` crea `pallets → B04 → 1`, no la clave `"B04.1"`. Como
los subpallets son justo los que llevan punto, el desglose se corrompía. Las
claves se codifican con `~`, que el validador de pallets no admite y por tanto
no puede colisionar. `decodificarPallets()` las devuelve al leer.

**`null` no es `undefined`.** `crearAdaptador(null)` llegaba al mock con
`productos = null`, y el valor por defecto de un parámetro solo cubre
`undefined`. Reventaba exactamente en el caso sin configuración, que es el que
usamos para construir sin la API real.

---

## Seguridad

El cliente nunca decide quién es. La identidad sale del token verificado por el
servidor, y las reglas rechazan cualquier evento cuyo `operadorUid` no coincida:

```javascript
allow create: if request.auth != null
           && request.resource.data.operadorUid == request.auth.uid
           && request.resource.data.operadorEmail == request.auth.token.email
           && request.resource.data.creadoEn == request.time;
```

Suplantar a otro operario deja de ser escribir otro nombre: habría que tener su
contraseña. La hora también la pone el servidor.

Los roles viajan como *custom claims*, así que las reglas los verifican sin leer
la base. Desactivar a alguien o cambiarle el rol **revoca sus tokens vigentes**:
el cambio surte efecto en el acto, no cuando venza la sesión.

### Credenciales de Depot

Van a **Secret Manager**, nunca a Firestore ni al dispositivo. El panel de
administración las escribe pero no puede volver a leerlas: muestra una máscara
(`to********90`) y la fecha del último cambio. Un administrador con la sesión
abierta en un teléfono perdido no expone la credencial del WMS.

```javascript
match /config/{doc} {
  allow read: if esAdmin() && doc != 'depot_secreto';
  allow write: if false;   // solo por Cloud Function
}
```

---

## Para conectar la API real

Todo habla con la interfaz `DepotAdapter`, nunca con la API directa. Hay dos
implementaciones: `HttpDepotAdapter` y `MockDepotAdapter`. Conectar la real es
configurar `baseUrl` y, si hace falta, ajustar `mapearProducto`.

`mapearProducto` ya tolera varios nombres de campo (`producto_id`, `sku`,
`codigo`, `itemCode`…) porque el contrato real todavía no se conoce. Cuando
llegue, se reduce al mapeo exacto.

Falta por definir:

1. URL base y entorno de pruebas, si existe.
2. Método de autenticación: token fijo, OAuth, o usuario y contraseña.
3. Endpoint de consulta de producto: ruta, parámetros y una respuesta de ejemplo.
4. Endpoint de códigos de barra, si es distinto.
5. Si existe consulta en lote: cambia el precalentado de N llamadas a unas pocas.

> Las credenciales se cargan desde el panel de administración. **No se pegan en
> el chat ni se suben al repositorio.**

---

## Despliegue

```bash
npm install -g firebase-tools
firebase login
firebase use --add                       # elegir el proyecto
cd functions && npm install && cd ..
firebase deploy --only firestore:rules,storage:rules,firestore:indexes
firebase deploy --only functions
```

Para el primer administrador, una vez desplegado:

```bash
firebase auth:import usuarios.json       # o crearlo desde la consola
# y asignarle el claim { rol: 'ADMIN', activo: true }
```

Desarrollo local sin tocar producción:

```bash
firebase emulators:start
```
