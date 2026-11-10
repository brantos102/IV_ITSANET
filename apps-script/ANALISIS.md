# Análisis de ITSANET IMS (Apps Script) contra los requerimientos iniciales

Revisión de `Código.gs` (195 líneas) e `Index.html` (914 líneas) como están hoy
en producción.

---

## Resumen ejecutivo

La interfaz es buena: mejor resuelta visualmente que la mía. El asistente de voz,
el modo oscuro, la firma de conformidad, el banner de offline y el reporte por
correo son aportes reales que conviene conservar.

El problema está debajo. **El ciclo principal está roto en producción** por tres
defectos reproducibles (ver `PARCHE-CRITICO.md` y `repro-bugs.js`), y de los
nueve requerimientos iniciales, **cuatro no están implementados y tres lo están
parcialmente**.

Los tres defectos explican exactamente lo que se ve en las capturas enviadas:
filas con cantidad física cargada e iconos de estado correctos, pero
`PROGRESO DE RECEPCIÓN 0%` y `0 / 0 Refs`.

---

## Defectos que rompen el ciclo principal

| # | Defecto | Efecto |
|---|---|---|
| 1 | `playSound` se invoca 7 veces y no está definida | **Ningún escaneo se guarda.** El número sube en pantalla, el Sheet nunca se actualiza |
| 2 | `calcularKPIs` escribe en `kpiTotal` y `kpiUnidadesEsperadas`, que no existen en el HTML | Progreso, contador de refs, gráfico y celebración congelados en 0 |
| 3 | `manejarEscaneo` usa `.find()` sobre SKU que ocupan varias líneas | Solo cuenta la primera línea; las demás quedan en 0 como faltantes fantasma |

El #1 es el más grave y el más fácil de pasar por alto, porque **la pantalla
miente**: el operador ve el número subir y asume que quedó registrado.

### Por qué un bug de audio tumba el guardado

```js
if(f === e) { playSound('beep'); speak("Completado"); }   // ← ReferenceError
...
guardarLocal(idx, false); sincronizarCelda(idx);          // ← inalcanzable
```

El `playSound` está *antes* del guardado y sin `try/catch`. Una función
accesoria quedó en el camino crítico. La corrección no es solo definirla: es
envolver audio y voz en `try/catch` para que no puedan volver a hacerlo — en
bodega el navegador bloquea `AudioContext` hasta que hay interacción del usuario,
y eso reproduciría el fallo aunque la función exista.

---

## Requerimientos iniciales, uno por uno

| # | Requerimiento | Estado | Dónde |
|---|---|---|---|
| 1 | Subir packing list y empezar a validar | ✅ Implementado | `procesarArchivo`, `obtenerDatosContenedor` |
| 2 | Validar existencia en Depot al escanear | ❌ **Ausente** | — |
| 3 | Mensaje "validar a profundidad o crearlo" | ❌ **Ausente** | — |
| 4 | Registrar código EAN para subida al sistema | ❌ **Ausente** | — |
| 5 | Ingresar cantidad física encontrada | ✅ Implementado | `manejarEscaneo`, `guardarLocal` |
| 6 | Mismo SKU en varios pallets | ❌ **Ausente** | Un solo campo pallet por fila |
| 7 | Sugerir el pallet donde ya se guardó el SKU | ⚠️ **Parcial** | `ultimoPallet` sugiere otra cosa |
| 8 | Suma sin cruces de datos entre operadores | ⚠️ **Parcial** | `guardarFilaRecepcion` escribe celda directa |
| 9 | Trazabilidad histórica para KPIs | ❌ **Ausente** | Sin histórico entre recepciones |

### 2 y 3 · Validación contra Depot

No existe ninguna llamada a Depot. `manejarEscaneo` solo comprueba si el código
está en el packing list cargado; si no está, muestra `alert("SKU no existe")` y
descarta el escaneo.

Esto tiene una consecuencia concreta: **la app no puede registrar el sobrante
que ocurrió en la recepción real**. El SKU `6EA837885A` llegó físicamente sin
estar en la lista, y el informe enviado al cliente lo reporta como
"SOBRANTE CONFIRMADO". Con el código actual, ese item es imposible de capturar.

Además, en el archivo real **17 de los 67 SKU no existen en el maestro Depot** —
son los `#N/A` de la columna `ok`, que es un VLOOKUP contra la hoja `MAESTRO`.
Hoy el operador no se entera de ninguno.

### 4 · Código EAN

No hay campo de EAN en ninguna parte: ni en la tabla, ni en el modelo de datos,
ni en el guardado. El dato que pediste capturar para la subida al sistema no se
captura.

### 6 y 7 · Pallets

La tabla tiene **un campo de texto por fila**, así que un SKU no puede estar en
dos pallets: es estructuralmente imposible en el modelo actual.

Sobre la sugerencia, `ultimoPallet` recuerda **el último pallet que escribió este
operador**, no **el pallet donde ya se guardó este SKU**. Son cosas distintas, y
la diferencia importa: si Juan guardó el SKU en B04 hace veinte minutos y María
lo escanea ahora, `ultimoPallet` le propone el pallet que María usó recién, que
puede ser cualquier otro. Justo el cruce que querías evitar.

Tampoco hay validación de formato: el campo acepta cualquier texto, sin la regla
alfanumérico (`A1`) con subpallet secuencial (`A1.1`) del diagrama.

### 8 · Concurrencia — el punto estructural

```js
function guardarFilaRecepcion(fileId, filaExcel, cantFisica, pallet) {
  var hoja = SpreadsheetApp.openById(fileId).getSheets()[0];
  hoja.getRange(filaExcel, 10).setValue(cantFisica);   // sobrescribe
  hoja.getRange(filaExcel, 12).setValue(pallet);
}
```

Escribe el **valor absoluto** de la celda, sin `LockService` ni control de
versión. Dos operadores sobre el mismo SKU producen una pérdida silenciosa: el
último en guardar borra lo del otro, y nadie se entera hasta el reclamo del
cliente.

No es hipotético. El `ultimoPallet` de cada navegador es independiente, la cola
offline (`offlineQueue`) se filtra solo por `fila` sin mirar `fileId`, y
`syncOfflineQueue` dispara los guardados **sin handler de error** y borra
`localStorage` de inmediato:

```js
let pending = [...offlineQueue]; offlineQueue = []; localStorage.removeItem('recepcion_offline');
pending.forEach(req => { google.script.run.guardarFilaRecepcion(...); });  // sin withFailureHandler
```

Si una de esas llamadas falla, el dato ya se borró del dispositivo. Se pierde sin
rastro.

Pediste explícitamente "proteger los datos registrados ya que las cantidades
serán subidas al sistema". Este es el punto donde el diseño actual no lo cumple.

### 9 · Trazabilidad histórica

Las cantidades físicas se escriben **dentro del propio archivo del packing list**
y la recepción se marca `Cerrado` en `Historial`. No queda:

- quién contó qué (el nombre del operario es un campo de texto libre que nadie
  verifica, y ni siquiera se guarda en el Sheet),
- cuándo se contó cada item,
- ningún registro consultable por SKU, por recepción y por fecha.

Pediste "revisar KPIs sobre las mismas recepciones, datos por cada SKU por cada
recepción por fechas". Con el modelo actual no se puede responder "¿cuántas veces
llegó corto el SKU X en los últimos seis meses?", porque ese dato nunca se
guardó en un lugar consultable.

---

## Otros hallazgos

| Severidad | Hallazgo |
|---|---|
| Alta | **Sin autenticación.** Cualquiera con el enlace abre cualquier contenedor y modifica cantidades. El operario es un `<input type="text">` con valor por defecto "Danny Ochoa" |
| Alta | **Faltante confirmado indistinguible de no contado.** Un `0` escrito a mano y una fila sin tocar se ven igual (`evaluarEstado` devuelve `pending` para ambos) |
| Media | `calcularKPIs` cuenta completadas solo si `e !== 0`, así que una línea con cantidad 0 —el archivo real tiene una— nunca puede completarse y el 100 % jamás se alcanza |
| Media | `finalizarRecepcionConfirmada` hace `idDrive.indexOf(fileId)` sobre un valor que puede no ser string; si ninguna fila coincide, envía el correo igual con "Desconocido" y **sin cerrar** la recepción |
| Media | `Session.getActiveUser().getEmail()` como destinatario del reporte: según el modo de despliegue es el operario, no gerencia |
| Media | Sin saneamiento de celdas: la regla "no caracteres especiales" del diagrama no se aplica en ningún punto |
| Baja | XSS vía `tr.innerHTML` con datos del Sheet sin escapar |
| Baja | ID del libro maestro `1h3BrU2k...` repetido en tres funciones, sin constante |

---

## Recomendación

**Conservar la interfaz, cambiar el motor.**

La UI es un activo y sería un desperdicio tirarla. El modelo de almacenamiento es
el pasivo: escribir cantidades directamente en celdas de un Google Sheet no
soporta varios operadores de forma segura, y sin un registro de eventos no hay
histórico del que sacar KPIs.

Hay dos caminos razonables y la decisión es tuya, porque implican compromisos
distintos:

### Opción A — Reescribir el backend en Apps Script

Mantiene Google Workspace, cero infraestructura, cero costo de servidor.

- Hoja `EVENTOS` append-only: un registro por conteo, nunca se sobrescribe.
- `LockService` en cada escritura.
- Hoja `MAESTRO` como catálogo Depot para la validación al escanear.
- Totales por `SUM()` sobre eventos, no por celda.

**Techo real:** `LockService` serializa las escrituras y cada llamada a
`SpreadsheetApp` tarda cerca de un segundo. Son del orden de 1–2 escaneos por
segundo en total, repartidos entre todos los operadores. Para 70 líneas con 3
personas alcanza de sobra; para un contenedor de 800 líneas con 6 personas se
siente. También hay cuotas diarias (`MailApp` 100 correos/día) y el límite de 6
minutos por ejecución.

### Opción B — Portar la interfaz sobre el motor de IV_ITSANET

El backend del PR anterior ya resuelve los nueve requerimientos y está probado
contra tu archivo real: libro mayor append-only, validación Depot con caché,
multi-pallet con sugerencia por SKU, EAN, idempotencia y KPIs históricos.

Lo que falta ahí es justamente lo que esta app hace bien: voz, firma, modo
oscuro, celebración, el diseño. Portarlo es trabajo de front-end, no de
arquitectura.

**Costo:** requiere un servidor, aunque sea un equipo en la bodega. Deja de ser
"solo un enlace de Google".

### Mi recomendación

**Opción B**, con el parche crítico aplicado hoy a la app actual para que no siga
perdiendo escaneos mientras se hace la migración.

El motivo es el requerimiento 9. Los KPIs históricos por SKU y por fecha no son
un extra: son la razón por la que pediste almacenar los datos en algún lado. En
Apps Script eso significa consultar hojas de cálculo con decenas de miles de
filas de eventos en cada carga del dashboard, y ahí el modelo se cae por
rendimiento antes que por diseño.

Si la restricción de "nada de servidores" es firme, la Opción A es defendible y
la implemento — pero conviene decidirlo sabiendo dónde está el techo.
