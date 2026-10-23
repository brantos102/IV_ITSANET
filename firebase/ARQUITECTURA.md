# Arquitectura v3 — Firebase

Respuesta a los siete puntos de optimización, con la medición que la sustenta.

---

## El hallazgo que desbloquea todo

La restricción de TI era **"nada fuera de Google"**. Eso descartaba un servidor
propio, pero **Firebase es Google Cloud**: mismo proveedor, misma consola, mismas
credenciales corporativas. Cumple la política y además elimina el techo de
rendimiento de Apps Script.

No hay que elegir entre "rápido" y "dentro de Google". Se puede tener los dos.

---

## 1 · ¿Dónde se guardan los archivos y por qué tarda?

**Hoy:** `DriveApp.createFile(blob)` deja el `.xlsx` suelto en el Drive del dueño
del script. No hay base de datos: el archivo **es** la base de datos.

Dos cuellos de botella, medidos sobre tu archivo real:

| Problema | Medición |
|---|---|
| El archivo viaja en base64 por `google.script.run` | 4.0 MB se convierten en **5.3 MB** de texto, en una sola llamada síncrona |
| Cada operación relee hojas completas | **1.067.029 celdas** leídas por escaneo |
| De esas, el escaneo realmente usa | **129 celdas** |

Es un factor de desperdicio de **8.272×**. No es un problema de código: es que
una hoja de cálculo no tiene índices. Para responder "¿existe este SKU?" hay que
recorrer las 15.687 filas del maestro, cada vez.

**Solución:**

- El archivo sube **directo a Cloud Storage** desde el navegador, con subida
  reanudable y barra de progreso. No pasa por el servidor ni por base64. El
  operador no espera: 4 MB en segundo plano.
- Una Cloud Function se dispara con el evento de Storage, parsea el archivo
  **una sola vez** y escribe el packing list como documentos en Firestore.
- A partir de ahí nadie vuelve a abrir el `.xlsx`. El archivo queda como
  respaldo y evidencia, no como base de datos.

---

## 2 · Login con usuario, contraseña y correo

Tienes razón en el riesgo: hoy el operario es un `<input type="text">` que
cualquiera llena con el nombre de otro. La bitácora no prueba nada.

**Firebase Authentication** con correo y contraseña. Cada conteo queda firmado
con el `uid` y el correo **verificados por el servidor**, no con lo que el
operario escribió. Las reglas de seguridad de Firestore rechazan cualquier
escritura cuyo `operadorUid` no coincida con quien está autenticado:

```javascript
allow create: if request.auth != null
           && request.resource.data.operadorUid == request.auth.uid;
```

Suplantar a otro operario deja de ser cuestión de escribir otro nombre: habría
que tener su contraseña.

El módulo de administración da de alta operarios, asigna rol
(`OPERADOR` / `SUPERVISOR` / `ADMIN`) y desactiva cuentas. Los roles viajan como
*custom claims* del token, así que las reglas los verifican sin leer la base.

---

## 3 · Validación contra Depot, no contra el maestro del archivo

**El cambio de fondo: no validar al escanear, validar al subir.**

Cuando se carga el packing list, una Cloud Function resuelve **todos** los SKU
contra la API de Depot en lote, en segundo plano. Cuando el operario empieza a
escanear, cada SKU ya está resuelto y cacheado.

El escaneo deja de ser "llamar a una API" y pasa a ser "leer un documento":

```
Escaneo → índice `codigos/{codigo}` → `productos/{sku}`   ≈ 50-150 ms
```

La cadena de resolución, en orden:

1. **Índice de códigos** en Firestore → instantáneo.
2. **API de Depot** si el código no está en el índice (SKU nuevo, código recién
   cambiado) → una llamada, y se cachea.
3. **Modal de búsqueda** dentro del packing list si Depot tampoco lo conoce.

### Validar al 100% códigos que cambian

Mencionas que algunos ítems actualizan su código. Por eso la resolución no es
`sku → producto` sino un **índice inverso** de cualquier código al SKU:

```
codigos/{codigoNormalizado} → { sku, tipo: SKU|EAN|ALTERNO, vigente: true|false }
```

Un producto puede tener varios códigos apuntándole. Cuando Depot informa que un
código cambió, el viejo se marca `vigente: false` pero **sigue resolviendo**: la
caja que está en la bodega tiene impreso el código viejo. El operario escanea,
funciona, y la app avisa *"este código fue reemplazado por X"*. Eso es validar al
100% sin frenar la operación.

---

## 4 · Escaneo = 1 unidad, o cantidad pre-digitada

Un buffer de cantidad, visible siempre en pantalla:

| Acción | Resultado |
|---|---|
| Escanear sin tocar nada | Registra **1** unidad |
| Escanear otra vez | Otra unidad más |
| Digitar `5` y escanear | Registra **5** de un golpe, y el buffer vuelve a 1 |

Es el caso que describes: el operario cuenta físicamente 5, digita 5, escanea
una vez. Un solo escaneo, cinco unidades.

---

## 5 · Por qué Firestore y no seguir en Sheets

| | Apps Script + Sheets | Firestore |
|---|---|---|
| Lectura por escaneo | 1.067.029 celdas | 1 documento (~200 bytes) |
| Latencia por escaneo | 1–3 s | 50–150 ms |
| Escrituras concurrentes | `LockService` serializa **todo** | `increment()` atómico, solo por contador |
| Tiempo real | No existe: hay que recargar | `onSnapshot`, nativo |
| Sin conexión | Cola propia en `localStorage` | Persistencia offline del SDK |
| Tope por ejecución | 6 minutos | No aplica |

La diferencia en concurrencia es la que más importa en bodega. `LockService`
pone a **todos** los operarios en fila, aunque cuenten SKU distintos.
`FieldValue.increment()` es atómico del lado del servidor y solo compite por el
contador de ese SKU: dos operarios en SKU distintos no se tocan, y dos operarios
en el mismo SKU suman correctamente sin bloquearse.

### Costo

Plan gratuito de Firestore: 50.000 lecturas y 20.000 escrituras por día. Una
recepción de 150 líneas con 3 operarios consume del orden de 500 escrituras.
Entran unas 40 recepciones diarias sin pagar nada.

---

## 6 · Tiempo real entre operarios

`onSnapshot` sobre `recepciones/{id}/skus`. Cuando Juan registra 3 unidades, la
pantalla de María se actualiza sola, sin recargar y sin polling. El contador
global y la barra de progreso son el mismo dato para todos.

Esto además previene el doble conteo: si un SKU ya está completo, los demás lo
ven en verde antes de ir a buscarlo.

---

## 7 · Móvil y handheld

95 % del uso es en dispositivo móvil, así que la app es una **PWA**:

- Se instala desde el navegador, sin tienda de aplicaciones ni MDM.
- Funciona sin conexión: el SDK de Firestore encola las escrituras y las envía
  al reconectar, sin código propio de sincronización.
- Pantalla de escaneo a una mano: el campo siempre enfocado, el lector dispara
  con Enter, confirmación por sonido y vibración.
- La cámara del dispositivo sirve como lector si no hay pistola.

---

## El flujo de validación, como lo definiste

```
1. Escanear o digitar el código
       ↓
2. ¿Existe?  ──no──→  Modal: buscar en el packing list
       │                     ↓ tampoco está
       │              Registrar como ADICIONAL
       │              (pestaña aparte, nunca una fila nueva)
       sí
       ↓
   Muestra descripción y detalles desde Depot
       ↓
3. Cantidad a registrar  (1 por defecto, o la pre-digitada)
       ↓
4. Pallet o subpallet destino   ← sugiere donde ya está ese SKU
       ↓
5. Observaciones e imágenes (opcional)
       ↓
6. Buen estado o PNC  → si es PNC, la foto es obligatoria
       ↓
7. Vuelve al campo de escaneo
```

### Regla de los adicionales

Lo dejaste explícito: **si el archivo tiene 22 filas, se entregan 22 filas.** Los
códigos que no estaban en el packing list van a una colección `adicionales` y se
exportan en una **pestaña separada** del archivo final.

> Vale la pena que lo sepas: el packing list real que entregaste en la recepción
> VW del 29-06-2026 **sí** trae el sobrante como fila 73, con cantidad 0. Tu regla
> nueva contradice esa práctica. Implemento la regla nueva porque es tu decisión;
> solo conviene avisar al ejecutivo de cuenta que el formato cambia.

---

## Arquitectura final

```
   Handheld / móvil  (PWA)
          │
          │  SDK Firestore — tiempo real, offline
          ▼
   ┌──────────────────────────────────────┐
   │  Firestore                           │
   │   recepciones / lineas / skus        │
   │   eventos (libro mayor)              │
   │   adicionales                        │
   │   productos + codigos (caché Depot)  │
   └──────────────────────────────────────┘
          ▲                    ▲
          │                    │
   Cloud Functions      Firebase Auth
    · importar xlsx      correo + contraseña
    · resolver Depot     roles por claims
    · cerrar + correo
    · exportar xlsx
          │
          ├──→  API Depot / WMS   (credenciales solo del lado servidor)
          ├──→  Cloud Storage     (xlsx y fotos de PNC)
          └──→  Gmail API         (informe final)
```

Las credenciales de Depot **nunca llegan al dispositivo**. Viven en Secret
Manager y solo las Cloud Functions las usan. Un operario con el teléfono en la
mano no puede extraerlas.

---

## Lo que falta para cerrar el diseño

El adaptador de Depot está detrás de una interfaz con una implementación
simulada, así que todo lo demás se construye y se prueba sin la API. Para
conectarla de verdad necesito:

1. **URL base** de la API de WMS y entorno de pruebas, si existe.
2. **Método de autenticación**: token fijo, OAuth, usuario y contraseña.
3. **Endpoint de consulta de producto**: ruta, parámetros y un ejemplo de
   respuesta real (puede ser con datos ficticios).
4. **Endpoint de códigos de barra**, si es distinto del de producto.
5. **Si existe**, un endpoint de consulta en lote: cambia el precalentado de
   N llamadas a unas pocas.

Las credenciales se cargan desde el módulo de administración, cifradas. **No se
pegan en el chat ni se suben al repositorio.**
