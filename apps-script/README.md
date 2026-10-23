# ITSANET IMS — Recepción de mercadería (Apps Script)

Versión 2 de la app, en Google Workspace. Conserva la interfaz original y
reemplaza el motor de datos.

| Documento | Qué es |
|---|---|
| [`ANALISIS.md`](ANALISIS.md) | Revisión de la versión anterior contra los nueve requerimientos |
| [`PARCHE-CRITICO.md`](PARCHE-CRITICO.md) | Parche mínimo de los tres defectos, si se quiere arreglar la app actual sin migrar |
| [`src/`](src/) | Código de la versión 2 |
| [`test/`](test/) | Pruebas de la lógica, ejecutables en Node |

---

## Qué cambió y por qué

La versión anterior guardaba la cantidad física escribiendo **el valor absoluto
de una celda** del Google Sheet:

```js
hoja.getRange(filaExcel, 10).setValue(cantFisica);   // sin candado
```

Dos operadores contando el mismo SKU se borraban entre sí en silencio, y no
quedaba registro de quién contó qué.

Ahora cada conteo es **una fila nueva en la hoja `EVENTOS`, que nunca se
modifica ni se borra**. Los totales se derivan sumando. Corregir un error es
registrar un evento compensatorio, no sobrescribir el original.

De esa única decisión salen cuatro requerimientos sin trabajo extra:

| Requerimiento | Cómo lo resuelve |
|---|---|
| Varios operadores sobre una sola base | Cada conteo es una fila propia; nunca compiten por la misma celda |
| Proteger los datos registrados | Nada se sobrescribe; `LockService` serializa las escrituras |
| Datos reales contra datos del sistema | Suma de `EVENTOS` contra suma del packing list |
| KPIs históricos por SKU, recepción y fecha | Cada evento ya trae SKU, pallet, operario y hora |

---

## Estructura

```
src/
  Config.gs    IDs, columnas y constantes (antes repetidos en tres funciones)
  Util.gs      Normalización de SKU/pallet/EAN, saneamiento, candado
  Eventos.gs   Libro mayor append-only y agregados derivados
  Depot.gs     Validación contra el maestro: existe / validar a fondo / crear
  Codigo.gs    API del frontend: lookup, conteo, anulación, bitácora
  Cierre.gs    Packing list final y reporte por correo
  Kpi.gs       Indicadores históricos entre recepciones
  Index.html   Interfaz
```

El libro base usa cuatro hojas. `EVENTOS` y `PENDIENTES` se crean solas la
primera vez; `MAESTRO` se carga desde la pantalla de administración.

| Hoja | Contenido |
|---|---|
| `Historial` | Una fila por recepción (ya existía) |
| `EVENTOS` | Libro mayor de conteos, append-only |
| `MAESTRO` | Catálogo de productos Depot |
| `PENDIENTES` | SKU por crear o validar en Depot |

---

## Instalación

1. En el editor de Apps Script, crear un archivo por cada `.gs` de `src/` y
   pegar su contenido. El HTML va en un archivo llamado `Index`.
2. En `Config.gs`, confirmar `LIBRO_BASE` y poner el correo de gerencia en
   `EMAIL_REPORTE` (si queda vacío llega al dueño del script).
3. Desplegar como aplicación web: **Ejecutar como** el propietario,
   **Quién tiene acceso** según la política de la empresa.
4. Entrar a *Admin. Archivos* y cargar el maestro de productos Depot. Sin esto,
   la validación marca todos los SKU como inexistentes.

> La primera ejecución pide autorizar Drive, Sheets y Gmail.

---

## El flujo, paso a paso

### Carga del packing list

El archivo se sube a Drive y se registra en `Historial`. Antes de registrarlo se
verifica que se pueda abrir como hoja de cálculo; si Drive no lo convirtió, se
avisa en ese momento y no cuando el operario intente abrir la recepción.

### Escaneo

Al escanear, el sistema responde en un solo paso:

- **¿Existe en Depot?** Si no: *validar a profundidad* cuando hay códigos
  similares en el maestro, o *solicitar creación* cuando no los hay. En ambos
  casos pide el EAN y deja el SKU en `PENDIENTES`.
- **¿Está en el packing list?** Si no, avisa que será sobrante.
- **¿Dónde se guardó antes?** Si el SKU ya está en un pallet, lo ofrece como
  botón. Un SKU puede quedar en varios pallets cuando hace falta, y queda
  registrado cuánto hay en cada uno.

Luego se ingresa cantidad, pallet, estado físico y observación.

### Protecciones

| Situación | Comportamiento |
|---|---|
| Doble disparo del lector o reintento | Clave de idempotencia: el mismo envío no suma dos veces |
| Cantidad que supera lo declarado | Se bloquea y exige confirmar el sobrante |
| Pallet mal escrito | Se rechaza: debe ser `A1` o subpallet `A1.1` |
| Mal estado físico sin observación | Se rechaza |
| Error de conteo | Se anula con motivo; el original queda en la bitácora |
| Sin conexión | El conteo se guarda en el dispositivo y se envía de a uno al volver, borrándose solo cuando el servidor confirma |

### Cierre

El modal de firma pide las cifras **al servidor**, no al estado del navegador:
lo que se firma es lo que hay, aunque otro operario haya escaneado hace un
segundo. Al confirmar se escribe el packing list final respetando las tres
reglas del flujo:

- **No añadir filas** → una fila por línea original, en el orden original. Los
  sobrantes de SKU ausentes del packing list van al final, con cantidad 0.
- **No caracteres especiales** → celdas sin acentos ni símbolos.
- **1 SKU en dos pallets en la misma celda** → `B03 / B03.1`, con el desglose
  por pallet en la observación.

---

## Pruebas

```bash
node test/run-tests.js          # 25 pruebas de la lógica
node repro-bugs.js src/Index.html   # verifica que no vuelvan los 3 defectos
```

Las pruebas ejecutan los `.gs` reales sobre un simulador de `SpreadsheetApp`,
`LockService` y `MailApp` (`test/gas-stub.js`), así que no hace falta desplegar
nada para correrlas. Cubren la validación contra Depot, la concurrencia, la
idempotencia, los sobrantes, los pallets múltiples, las reglas del packing list
final y los KPIs históricos.

El candado del simulador es de un solo titular: si alguna ruta dejara de
liberarlo, la prueba lo detecta.

---

## Límites conocidos

- **Rendimiento.** `LockService` serializa las escrituras y cada llamada a
  `SpreadsheetApp` tarda cerca de un segundo: son del orden de 1–2 conteos por
  segundo entre todos los operadores. Suficiente para contenedores de hasta unas
  150 líneas; por encima de 500 se nota.
- **Cuotas de Google.** `MailApp` permite 100 correos por día y cada ejecución
  tiene 6 minutos de tope.
- **Sin autenticación propia.** El acceso depende de a quién se le comparta la
  app web. El nombre del operario es un campo de texto: identifica, no
  autentica. Si hace falta control real de identidad, hay que usar
  `Session.getActiveUser()` con despliegue por usuario.
- **El histórico crece.** Cada conteo es una fila en `EVENTOS`. A unas 300 filas
  por semana son ~15.000 al año, cómodo para una hoja; si eso cambia, conviene
  archivar por año.
