# Guía de instalación — VAL VENTURA

De cero a la app funcionando en los handheld, accediendo solo a un enlace.

**Tiempo estimado:** 45–60 minutos la primera vez.
**Lo que vas a obtener:** una URL tipo `https://val-ventura.web.app` que
cualquier dispositivo abre sin instalar nada, y que se puede añadir a la
pantalla de inicio como si fuera una app nativa.

---

## Índice

1. [Antes de empezar](#1-antes-de-empezar)
2. [Crear el proyecto en Firebase](#2-crear-el-proyecto-en-firebase)
3. [Instalar las herramientas](#3-instalar-las-herramientas)
4. [Conectar el repositorio con tu proyecto](#4-conectar-el-repositorio-con-tu-proyecto)
5. [Desplegar](#5-desplegar)
6. [Crear el primer administrador](#6-crear-el-primer-administrador)
7. [Cargar el token de Depot](#7-cargar-el-token-de-depot)
8. [Dar de alta a los operarios](#8-dar-de-alta-a-los-operarios)
9. [Instalar en los handheld](#9-instalar-en-los-handheld)
10. [Errores frecuentes](#10-errores-frecuentes)
11. [Mantenimiento](#11-mantenimiento)

---

## 1. Antes de empezar

### Lo que necesitas

| Requisito | Detalle |
|---|---|
| Cuenta de Google | La corporativa de Itsanet. Debe poder crear proyectos en Firebase |
| Tarjeta de crédito | Solo para activar el plan Blaze. **No se cobra** dentro del nivel gratuito |
| Node.js 20 o superior | [nodejs.org](https://nodejs.org) — descarga la versión LTS |
| Una terminal | PowerShell en Windows, Terminal en Mac |

### Por qué hace falta el plan Blaze

Las Cloud Functions **no funcionan en el plan gratuito Spark**. Blaze es "pago
por uso" y tiene el mismo nivel gratuito mensual incluido:

| Recurso | Gratis cada mes |
|---|---|
| Lecturas de Firestore | 50.000 por día |
| Escrituras de Firestore | 20.000 por día |
| Invocaciones de Functions | 2.000.000 |
| Almacenamiento | 5 GB |
| Hosting | 10 GB de transferencia |

Una recepción de 150 líneas con 3 operarios consume del orden de **500
escrituras**. Caben unas 40 recepciones diarias sin pagar nada.

> **Pon un presupuesto de todos modos.** En el paso 2.4 se explica cómo. Es la
> red de seguridad contra un bucle accidental que dispare el consumo.

### Verifica Node.js

```bash
node --version
```

Debe decir `v20.x.x` o superior. Si dice `v18` o da error, instala la versión LTS
desde [nodejs.org](https://nodejs.org) y **cierra y vuelve a abrir la terminal**.

---

## 2. Crear el proyecto en Firebase

### 2.1 Crear el proyecto

1. Entra a [console.firebase.google.com](https://console.firebase.google.com)
2. **Crear un proyecto**
3. Nombre: `val-ventura` (si está tomado, Firebase te sugiere `val-ventura-a1b2`)
4. Google Analytics: **desactívalo**. No aporta nada aquí y pide configuración extra
5. **Crear proyecto** y espera

> Anota el **ID del proyecto** exacto que quedó. Aparece bajo el nombre y puede
> no coincidir con lo que escribiste. Lo necesitarás varias veces.

### 2.2 Activar Authentication

1. Menú lateral → **Compilación** → **Authentication** → **Comenzar**
2. Pestaña **Sign-in method**
3. Clic en **Correo electrónico/contraseña**
4. Activa **la primera opción**. Deja desactivado el "vínculo de correo"
5. **Guardar**

### 2.3 Activar Firestore

1. **Compilación** → **Firestore Database** → **Crear base de datos**
2. Elige **Modo de producción**
   > No elijas modo de prueba: deja la base abierta a cualquiera durante 30 días.
   > Las reglas del repositorio se despliegan en el paso 5.
3. Ubicación: **`us-central1`** (o `southamerica-east1` si prefieres latencia
   menor desde Ecuador)
   > **La ubicación no se puede cambiar después.** Para cambiarla hay que borrar
   > el proyecto y empezar de nuevo.
4. **Habilitar**

### 2.4 Activar Storage

1. **Compilación** → **Storage** → **Comenzar**
2. **Modo de producción** → misma ubicación que Firestore → **Listo**

### 2.5 Pasar a Blaze y poner un presupuesto

1. Abajo a la izquierda: **Spark** → **Actualizar** → **Blaze**
2. Vincula una cuenta de facturación (o crea una)
3. Cuando te ofrezca una **alerta de presupuesto**, pon **10 USD**

Si te la saltaste:

1. [console.cloud.google.com/billing](https://console.cloud.google.com/billing)
2. Tu cuenta → **Presupuestos y alertas** → **Crear presupuesto**
3. Importe 10 USD, alertas al 50 %, 90 % y 100 %

> La alerta **avisa, no corta**. Es un aviso temprano, no un tope.

---

## 3. Instalar las herramientas

```bash
npm install -g firebase-tools
```

Verifica:

```bash
firebase --version
```

**Si da "no se reconoce el comando" en Windows:** cierra PowerShell y ábrelo de
nuevo. Si sigue, abre PowerShell **como administrador** y ejecuta:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Si da error de permisos en Mac/Linux:** no uses `sudo`. Mejor:

```bash
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc
source ~/.zshrc
npm install -g firebase-tools
```

### Iniciar sesión

```bash
firebase login
```

Se abre el navegador. Entra con la cuenta de Google del proyecto y acepta.

> **Si estás en un servidor sin navegador:** usa `firebase login --no-localhost`
> y pega el código que te da.

---

## 4. Conectar el repositorio con tu proyecto

```bash
git clone https://github.com/brantos102/VAL_VENTURA.git
cd VAL_VENTURA/firebase
```

Vincula tu proyecto:

```bash
firebase use --add
```

Elige el proyecto de la lista y, cuando pida un alias, escribe `default`.

Esto crea `.firebaserc`. Verifica:

```bash
firebase projects:list
```

Instala las dependencias de las Functions:

```bash
cd functions
npm install
cd ..
```

Comprueba que la lógica pasa sus pruebas **antes** de desplegar:

```bash
cd functions && npm test && cd ..
```

Debe terminar con `0 falladas` en los tres bloques. Si no, no despliegues: avisa
antes de seguir.

---

## 5. Desplegar

### 5.1 Reglas de seguridad primero

```bash
firebase deploy --only firestore:rules,firestore:indexes,storage:rules
```

> Siempre las reglas antes que nada. Si despliegas la app primero, hay una
> ventana en la que la base está sin proteger.

Los índices tardan unos minutos en construirse. Puedes seguir mientras tanto.

### 5.2 Las Functions

```bash
firebase deploy --only functions
```

**La primera vez** Firebase pedirá activar varias APIs de Google Cloud. Responde
que sí a todo. Puede tardar 3–5 minutos.

**Si falla con `Cloud Functions requires the Blaze plan`:** vuelve al paso 2.5.

**Si falla con `Billing account not configured`:** la facturación tarda unos
minutos en propagarse. Espera 5 minutos y repite.

**Si falla con `Permission denied on service account`:** tu cuenta no es
propietaria del proyecto. Pide el rol **Propietario** en
`console.cloud.google.com/iam-admin/iam`.

### 5.3 La aplicación web

```bash
firebase deploy --only hosting
```

Al terminar te da la URL:

```
Hosting URL: https://val-ventura.web.app
```

**Esa es la URL que reparten a los operarios.** Ábrela en el navegador para
confirmar que carga.

### 5.4 Todo junto, de aquí en adelante

```bash
firebase deploy
```

---

## 6. Crear el primer administrador

Hay un huevo y una gallina: para crear usuarios desde el panel hace falta ser
administrador, y todavía no hay ninguno. Se resuelve una sola vez a mano.

### 6.1 Crear el usuario

1. Consola de Firebase → **Authentication** → **Users** → **Agregar usuario**
2. Correo: el tuyo corporativo
3. Contraseña: una fuerte
4. **Agregar usuario**
5. **Copia el UID** que aparece en la lista (una cadena larga)

### 6.2 Darle el rol de administrador

Desde la carpeta `firebase/`:

```bash
node -e "
const admin = require('firebase-admin');
admin.initializeApp({ projectId: process.argv[1] });
admin.auth().setCustomUserClaims(process.argv[2], { rol: 'ADMIN', activo: true })
  .then(() => admin.firestore().collection('usuarios').doc(process.argv[2]).set({
     uid: process.argv[2], email: process.argv[3], nombre: process.argv[4],
     rol: 'ADMIN', activo: true, creadoEn: new Date(),
  }))
  .then(() => console.log('Administrador listo. Cierra sesión y vuelve a entrar.'))
  .catch(e => { console.error('ERROR:', e.message); process.exit(1); });
" TU_PROJECT_ID EL_UID tu@correo.com "Tu Nombre"
```

Sustituye los cuatro valores del final. Necesita credenciales de aplicación:

```bash
gcloud auth application-default login
```

**Si no tienes `gcloud`:** descarga una clave de cuenta de servicio desde
**Configuración del proyecto → Cuentas de servicio → Generar nueva clave
privada**, guárdala como `serviceAccount.json` dentro de `firebase/` y antes del
comando ejecuta:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=./serviceAccount.json   # Mac/Linux
$env:GOOGLE_APPLICATION_CREDENTIALS=".\serviceAccount.json"   # Windows
```

> **Borra `serviceAccount.json` en cuanto termines.** Es la llave maestra del
> proyecto. Ya está en `.gitignore`, pero no lo dejes en el disco.

### 6.3 Importante: volver a entrar

El rol viaja dentro del token de sesión. **Cierra sesión en la app y vuelve a
entrar**, o seguirás viendo la app como operario normal.

---

## 7. Cargar el token de Depot

Aquí va la credencial del WMS. **Nunca la escribas en un archivo del
repositorio.** El panel la guarda en Secret Manager, cifrada, y ni siquiera un
administrador puede volver a leerla: verá `to********90` y la fecha del cambio.

### 7.1 Averigua qué tipo de autenticación usa tu WMS

| Tipo | Cómo se reconoce | Qué llenas |
|---|---|---|
| **Login** | Hay un endpoint `/auth/login` que devuelve un token | Usuario, contraseña y ruta de login |
| **Token fijo** | Te dieron un token largo que no caduca | Solo el token |
| **Básica** | Usuario y contraseña en cada llamada | Usuario y contraseña |

El más común en WMS es **Login**, y es el que mejor soporta la app: pide el token
**una vez** y lo reutiliza toda la jornada.

### 7.2 Llenar el panel

En la app: **Administración → API de Depot**.

| Campo | Ejemplo | Notas |
|---|---|---|
| URL base | `https://wms.itsanet.com/api` | **Tiene que ser https.** La app rechaza http |
| Cliente | `VENTURA` | Si el WMS separa por cliente |
| Ruta de login | `/auth/login` | Vacío si usas token fijo |
| Campo usuario | `usuario` | El nombre que espera el WMS en el JSON |
| Campo contraseña | `clave` | Idem |
| Usuario / Contraseña | — | Lo que te dio el proveedor del WMS |
| Prefijo del token | `Bearer` | Algunos WMS usan `Token` o `JWT` |
| Horas de validez | `12` | Tope de reutilización |
| Ruta de producto | `/productos/{codigo}` | `{codigo}` se sustituye solo |
| Ruta de código de barras | `/productos/barcode/{codigo}` | Si es distinta |

### 7.3 Probar antes de confiar

Pulsa **Probar conexión** con un SKU que sepas que existe. Te responde:

```
Conexión correcta y producto encontrado.   312 ms
SKU: 2H0525345 — WASHER
```

Si algo falla, el mensaje dice qué revisar:

| Mensaje | Causa | Solución |
|---|---|---|
| `El WMS rechazó el usuario o la contraseña` | Credenciales malas | Confirma con el proveedor |
| `respondió sin token reconocible` | El token viene en un campo raro | Mándame la respuesta de ejemplo y lo mapeo |
| `No se pudo contactar al WMS` | Red, firewall o URL mal escrita | ¿El WMS acepta conexiones desde fuera de la red interna? |
| `La URL debe ser https` | Pusiste `http://` | Pide el endpoint seguro |

> **Si el WMS solo acepta conexiones desde la red interna de Itsanet**, las
> Cloud Functions no llegarán: salen desde Google Cloud. Hay solución (Cloud
> NAT con IP fija para que TI la autorice), pero cuéntamelo antes de seguir.

### 7.4 Cómo se reutiliza el token

Esto es lo que pediste, y así quedó implementado:

```
Escaneo → ¿token en memoria?     → sí: se usa          (0 ms)
                ↓ no
          ¿token en Firestore?   → sí: se usa          (~30 ms)
                ↓ no
          login contra el WMS    → se guarda y se usa  (~500 ms)
```

- **Un solo login al día.** Probado: 50 consultas seguidas hacen 1 login.
- **Entre instancias.** Cloud Functions escala a varias copias, y cada una
  arranca sin memoria. La segunda toma el token de Firestore, sin login.
- **Arranque en frío múltiple.** Si diez instancias necesitan el token a la vez,
  se coordinan y hacen **un** login, no diez.
- **Revocación.** Si el WMS invalida el token antes de tiempo, la primera
  llamada que reciba un 401 renueva y reintenta sola. El operario no se entera.
- **El token no se expone.** Vive en `_internal/`, que ninguna regla deja leer,
  ni a un administrador. El panel solo muestra si está vigente y cuántos minutos
  le quedan.

---

## 8. Dar de alta a los operarios

**Administración → Operarios → Nuevo operario**

| Campo | Regla |
|---|---|
| Correo | Real: es la identidad que firma cada conteo |
| Nombre completo | Mínimo 3 caracteres |
| Rol | `OPERADOR`, `SUPERVISOR` o `ADMIN` |
| Contraseña | Mínimo 8 caracteres |

### Qué puede hacer cada rol

| | OPERADOR | SUPERVISOR | ADMIN |
|---|---|---|---|
| Escanear y contar | Sí | Sí | Sí |
| Anular su propio conteo | Sí | Sí | Sí |
| Anular el de otro | No | Sí | Sí |
| Crear recepciones y subir packing list | No | Sí | Sí |
| Cerrar la validación | No | Sí | Sí |
| Crear operarios | No | No | Sí |
| Tocar las credenciales de Depot | No | No | Sí |

### Dar de baja a alguien

**Operarios → Desactivar.** Los tokens se revocan **en el acto**: deja de poder
escribir inmediatamente, no cuando venza su sesión. Sus conteos anteriores
siguen en la bitácora: nada se borra.

---

## 9. Instalar en los handheld

No hay instalador ni tienda de aplicaciones. **Solo el enlace.**

### Android (handheld Zebra, Honeywell, o teléfono)

1. Abre Chrome
2. Entra a `https://val-ventura.web.app`
3. Menú **⋮** → **Añadir a pantalla de inicio**
4. Aparece el icono como si fuera una app nativa

### iPhone / iPad

1. Abre **Safari** (en Chrome no aparece la opción)
2. Entra a la URL
3. Botón **Compartir** → **Añadir a pantalla de inicio**

### Pistola de código de barras

Las pistolas USB y Bluetooth emulan un teclado: escriben el código y mandan
Enter. **No hay nada que configurar.** Solo verifica dos cosas en el lector:

- Que el sufijo esté en **Enter (CR)**, no en Tab
- Que no esté en modo "teclado numérico" si los códigos llevan letras

### Sin conexión

El SDK de Firestore guarda los conteos en el dispositivo y los envía al
reconectar. El operario ve un aviso, pero **sigue trabajando**. No hay que
hacer nada manualmente.

> Aviso real: si el operario cierra el navegador con conteos sin enviar y no
> vuelve a abrirlo en ese dispositivo, esos conteos se quedan ahí. Antes de
> cerrar una recepción, la app comprueba que no quede nada pendiente.

---

## 10. Errores frecuentes

### Al desplegar

| Error | Causa | Solución |
|---|---|---|
| `HTTP Error: 403, Unknown Error` | Sesión vencida | `firebase logout` y `firebase login` |
| `Error: Failed to get Firebase project` | Proyecto mal vinculado | `firebase use --add` otra vez |
| `functions: command not found` | Faltan dependencias | `cd functions && npm install` |
| `Error: Cloud Functions requires Blaze` | Plan gratuito | Paso 2.5 |
| `The query requires an index` | Índices sin construir | Espera 5 min; el error trae un enlace que lo crea |
| `Deploy timed out` | Red lenta | Repite; el despliegue es idempotente |

### Al usar la app

| Síntoma | Causa | Solución |
|---|---|---|
| "Missing or insufficient permissions" | El usuario no tiene rol | Revisa sus claims; que cierre sesión y vuelva a entrar |
| Entra pero no ve el menú de administración | El token todavía tiene el rol viejo | **Cerrar sesión y volver a entrar.** Es lo más común |
| El escáner escribe en la pantalla pero no registra | El campo perdió el foco | Toca el campo de escaneo; se vuelve a enfocar solo |
| Un SKU aparece como inexistente y sí existe | El precalentado no terminó | Espera a que la recepción diga "Lista" |
| Todos los SKU salen como inexistentes | Depot mal configurado | **Probar conexión** en el panel |
| El progreso no avanza | Sin conexión | Mira el aviso; se sincroniza solo al volver |

### Si algo va muy mal

Ver qué pasó en las Functions:

```bash
firebase functions:log --only registrarConteo
```

Volver a la versión anterior del hosting:

```bash
firebase hosting:rollback
```

Respaldo de la base:

```bash
gcloud firestore export gs://TU_PROJECT_ID.appspot.com/respaldos/$(date +%F)
```

---

## 11. Mantenimiento

### Rutina

| Cada | Qué |
|---|---|
| Semana | Revisar **SKU sin Depot** y crearlos en el WMS |
| Mes | Revisar el consumo en la consola de facturación |
| Mes | Dar de baja operarios que ya no están |
| Trimestre | Rotar la contraseña del WMS y actualizarla en el panel |

### Actualizar la app

```bash
cd VAL_VENTURA
git pull
cd firebase/functions && npm install && npm test && cd ..
firebase deploy
```

Los operarios **no tienen que hacer nada**: la próxima vez que abran el enlace
tienen la versión nueva.

### Respaldo automático

```bash
gcloud firestore databases create-backup-schedule \
  --database='(default)' --retention=7d --recurrence=daily
```

---

## Resumen de comandos

```bash
# Preparar
npm install -g firebase-tools
firebase login
cd VAL_VENTURA/firebase
firebase use --add
cd functions && npm install && npm test && cd ..

# Desplegar
firebase deploy --only firestore:rules,firestore:indexes,storage:rules
firebase deploy --only functions
firebase deploy --only hosting

# Día a día
firebase deploy
firebase functions:log
firebase hosting:rollback
```

---

## Qué falta para estar en producción

La parte de datos está construida y probada (53 pruebas). Falta:

- Importador del packing list
- Cliente web (las pantallas que ve el operario)
- Cierre con informe por correo

Y para conectar el WMS de verdad necesito de ti:

1. **URL base** y si existe un entorno de pruebas
2. **Cómo se autentica**: ¿hay endpoint de login? ¿qué nombre tienen los campos
   de usuario y contraseña en el JSON?
3. **Una respuesta de ejemplo** del endpoint de producto, con datos ficticios
4. **Si existe consulta en lote**: cambia el precalentado de N llamadas a unas pocas

Con eso el adaptador queda conectado el mismo día: está detrás de una interfaz,
así que no hay que reescribir nada.
