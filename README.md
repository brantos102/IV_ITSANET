# ITSANET IMS

[Versión 51: columnas ordenables y justificación de la validación de Depot en Excel y correo](docs/COLUMNAS_Y_VALIDACION_DEPOT_51.md).

[Versión 50: cámara dentro de la ficha y recuperación del borrador del operario](docs/FOTO_OPERADOR_Y_BORRADOR_50.md).

[Versión 49: correo con selección de fotos, escáner móvil y ayudas operativas](docs/CORREO_CAMARA_Y_AYUDAS_49.md).

[Informe técnico del servidor, HTTPS/cámara y almacenamiento · 18/10/2026](docs/descargas/ITSANET-informe-servidor-20261018.md) · [Descargar HTML y captura de lectura](docs/descargas/ITSANET-informe-servidor-20261018.zip).

[Versión 48: diagnóstico de Google y errores 502 del piloto](docs/DIAGNOSTICO_GOOGLE_PILOTO_48.md).

[Versión 47: demos autónomas, FAQ, instalación por supervisor y acceso al estado de Drive](docs/MANUALES_Y_DEMOS_47.md).

[Versión 46: nombres de fotos, clasificación histórica y carpetas por bulto](docs/FOTOS_AUDITORIA_Y_CARPETAS_46.md).

[Versión 43: cámara optimizada, fotos recuperables, manuales descargables y piloto desde una PC](docs/CAMARA_FOTOS_MANUALES_Y_PILOTO_43.md).

[Descargar demos y guías actualizadas en ZIP](docs/descargas/ITSANET-manuales-v47.zip) · [Guías anteriores 43](docs/descargas/ITSANET-manuales-v43.zip).

Manuales interactivos: [Operario](firebase/public/manuales/operario.html), [Supervisor](firebase/public/manuales/supervisor.html), [Instalación por supervisor](firebase/public/manuales/instalacion-supervisor.html), [Técnico](firebase/public/manuales/tecnico.html).

[Versión 41: lecturas del escáner, etiquetas ampliadas y modales](docs/LECTURAS_ETIQUETAS_Y_NAVEGACION_41.md).

**Desarrollo en tu PC Windows con MySQL separado de producción:**
[arranque con Docker Desktop](docs/DESARROLLO_EN_PC.md).

[Mejoras en desarrollo: ingreso, evidencias en Drive y puente Zebra configurable](docs/INGRESO_EVIDENCIAS_E_IMPRESION.md).

[Configuración Google, formatos Depot y etiqueta desde stock](docs/GOOGLE_Y_FORMATOS.md).

[Vista movil, Google, credenciales ADMIN y etiquetas Zebra](docs/MEJORAS_MOVIL.md).

**Operacion local actual (MySQL, puerto 3002):** seguir
[docs/OPERACION_LOCAL.md](docs/OPERACION_LOCAL.md). Incluye actualizacion de la
rama operativa, Drive/correo sin Firebase y Sheets solo como exportacion
opcional. No requiere importar historicos ni reinstalar otros servicios.

App para la validación física de recepciones de Impoventura.

Recibe el packing list del sistema, guía el conteo físico de varios operadores
en paralelo y entrega el **packing list final** con faltantes, sobrantes y
ubicación en pallet de cada SKU — con trazabilidad completa para KPIs.

---

## Por qué está construida así

La decisión de diseño que sostiene todo lo demás: **el conteo físico no se
guarda como un total que se actualiza, sino como un libro mayor de eventos que
solo crece** (`scan_events`). Los totales siempre se derivan con `SUM()`.

Si dos operadores cuentan el mismo SKU al mismo tiempo y el sistema hiciera
`UPDATE total = total + n`, uno de los dos conteos se perdería silenciosamente
y nadie lo notaría hasta el reclamo del cliente. Con el libro mayor eso es
imposible: cada conteo es un `INSERT` independiente.

De esa única decisión salen gratis cuatro cosas que el flujo pedía:

| Requerimiento | Cómo lo resuelve |
|---|---|
| Varios operadores, una sola base por packing list | Cada conteo es una fila propia; nunca compiten por la misma celda |
| Proteger los datos registrados | Nada se borra ni se sobrescribe; corregir es registrar un evento compensatorio |
| Datos reales contra datos del sistema | `SUM(scan_events)` vs `SUM(packing_items)`, calculado al momento |
| KPIs históricos por SKU, recepción y fecha | Cada evento ya trae SKU, pallet, operador y hora |

Está verificado con una prueba de 8 hilos haciendo 25 conteos simultáneos del
mismo SKU: las 200 unidades quedan registradas, ninguna se pierde ni se duplica
(`tests/test_concurrencia.py`).

---

## Stack

| Pieza | Elección | Motivo |
|---|---|---|
| Backend | Python 3.11+ / FastAPI | Un solo lenguaje, API autodocumentada en `/docs` |
| Base de datos | SQLite en modo WAL | Un archivo, sin servidor; soporta la bodega completa |
| Frontend | HTML servido + JS plano | Sin build, sin `node_modules`; corre en cualquier teléfono |
| Excel | openpyxl | Lee el packing list y genera el final con el mismo formato |

**Migrar a PostgreSQL** cuando crezca: se usa SQLAlchemy, así que basta cambiar
`VAL_DATABASE_URL`. No hay que tocar código.

---

## Instalación

```bash
git clone https://github.com/brantos102/IV_ITSANET.git && cd IV_ITSANET
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh                      # http://0.0.0.0:8000
```

Al primer arranque se crea el usuario `admin` con PIN `1234`. **Cámbielo.**

```bash
python scripts/crear_operador.py admin "Administrador" 7391 --rol ADMIN
python scripts/crear_operador.py juan "Juan Perez" 4821 --rol OPERADOR
python scripts/cargar_maestro.py maestro_depot.xlsx     # catálogo de productos
```

Los operadores entran desde el teléfono o la tablet a `http://<ip-del-servidor>:8000`.

---

## Flujo de trabajo

### 1. Recepción y carga del packing list

Se crea la recepción y se sube el `.xlsx`. El importador detecta la fila de
encabezados y mapea las columnas por nombre (`ITEM`, `Descripción`, `Cantidad`,
`Factura`, `Embarque`…), así que tolera archivos con el orden cambiado. Las
columnas de resultado que ya traiga el archivo (`Validación`, `PALLET`, `ok`…)
**se ignoran**: esa información la genera la app.

El packing list queda inmutable: es la versión del sistema contra la que se
compara. No se puede reemplazar una vez que hay conteos registrados.

### 2. Escaneo (`/recepciones/{id}/escanear`)

El operador escanea y el sistema responde en un solo paso:

- **¿Existe en Depot?** Si no: *validar a profundidad* (cuando hay códigos
  similares en el maestro) o *solicitar creación*. En ambos casos pide el EAN y
  deja el SKU en la lista de pendientes.
- **¿Está en el packing list?** Si no, avisa que todo lo que registre será sobrante.
- **¿Dónde se guardó antes?** Si el SKU ya está en un pallet, lo muestra como
  botón para reutilizarlo. Lo óptimo es un solo pallet por SKU, pero si por
  tamaño o cantidad hace falta repartirlo, se permite y queda registrado.

Luego ingresa cantidad física, pallet y estado (bueno/malo + observación).

Pensado para trabajar sin mirar la pantalla: el lector de códigos dispara el
flujo con Enter, hay confirmación por sonido y vibración, y `Esc` reinicia.

### 3. Protecciones durante el conteo

| Situación | Comportamiento |
|---|---|
| Doble disparo del lector o reintento de red | `idempotency_key`: el mismo envío no suma dos veces |
| Cantidad que supera lo declarado | Se bloquea y exige confirmar el sobrante explícitamente |
| Pallet mal escrito | Se rechaza: debe ser `A1` o subpallet `A1.1` |
| Item en mal estado sin observación | Se rechaza |
| Error de conteo | Se anula con motivo; el evento original **nunca se borra** |
| Recepción cerrada | No admite más conteos; reabrir exige rol supervisor y motivo |

### 4. Cierre y entrega

El supervisor cierra la validación y descarga el **packing list final**, que
respeta las tres reglas del flujo:

- **No añadir filas** → una fila por línea original, en el orden original. Los
  sobrantes de SKU que no estaban en la lista van al final, con cantidad 0.
- **No caracteres especiales** → celdas sin acentos ni símbolos que el sistema
  Depot rechace.
- **1 SKU en dos pallets puede ir en la misma celda** → `B03 / B03.1`, con el
  desglose por pallet en OBSERVACION.

El archivo trae además una hoja `RESUMEN` con los totales de la validación.

---

## Integración con Depot

```bash
export DEPOT_BASE_URL=https://depot.interno/api
export DEPOT_TOKEN=xxxxx
```

El cliente resuelve cada código así: **caché local → API → búsqueda difusa**.

El espejo local del maestro es lo que hace viable el escaneo: responde en
microsegundos y, si la API se cae, la bodega sigue trabajando. Un *circuit
breaker* deja de castigar cada escaneo tras 3 fallos y reintenta al minuto; el
resultado se marca como degradado para que el operador lo sepa.

Sin `DEPOT_BASE_URL` configurada la app funciona igual, solo contra el maestro
cargado desde Excel.

---

## KPIs (`/kpi`)

- **Por recepción**: exactitud, faltantes, sobrantes, horas de validación.
- **Por operador**: eventos, unidades, scans/hora, tasa de anulación.
- **Por SKU, histórico**: en cuántas recepciones apareció y en cuántas hubo
  discrepancia — sirve para detectar los SKU que fallan siempre.
- **Serie diaria** de actividad.

Todo sale de consultas sobre el libro mayor; no hay proceso de consolidación
que pueda quedar desactualizado.

---

## Pruebas

```bash
python -m pytest -q          # 21 pruebas + 6 end-to-end

# Las end-to-end necesitan el packing list real (no se versiona):
VAL_TEST_XLSX=/ruta/al/packing_list.xlsx python -m pytest -q   # 27
```

Incluyen un end-to-end contra el packing list real de la recepción VW del
29-06-2026: la app reproduce el resultado que se entregó al ejecutivo de cuenta
(71 Ok, 1 Faltante, 1 Sobrante) y detecta los mismos 17 SKU que no existen en el
maestro Depot.

---

## Configuración

| Variable | Default | Qué hace |
|---|---|---|
| `VAL_DATABASE_URL` | `sqlite:///data/ventura.db` | Base de datos |
| `VAL_DATA_DIR` | `./data` | Subidas, exports y fotos |
| `VAL_SECRET_KEY` | *(inseguro)* | **Cambiar en producción** |
| `VAL_SESSION_HOURS` | `12` | Duración de la sesión |
| `VAL_SANITIZE_EXPORT` | `1` | Saneado de celdas al exportar |
| `VAL_PALLET_SEPARADOR` | `" / "` | Separador de pallets en una celda |
| `DEPOT_BASE_URL` / `DEPOT_TOKEN` | *(vacío)* | API de Depot |

---

## Operación

- **Respaldo**: `sqlite3 data/ventura.db ".backup respaldo.db"` mientras la app corre.
- **Red**: todos los dispositivos en la misma WiFi que el servidor.
- **Capacidad**: holgada para decenas de operadores concurrentes.

---

## Documentación

- [`docs/API.md`](docs/API.md) — referencia de endpoints, con ejemplos y códigos de error.
