# Guía de instalación — VAL VENTURA

De cero a la app funcionando en los handheld, **sin tarjeta de crédito**.

**Resultado:** una URL tipo `https://iv-itsanet.web.app` que cualquier
dispositivo abre con la cuenta corporativa de Google. Sin instalador, sin
tienda de aplicaciones.

**Tiempo:** 50–70 minutos la primera vez.

---

## Lo que cambia por usar el plan Spark

El plan gratuito **no incluye Cloud Functions ni Cloud Storage**. Desde el 3 de
febrero de 2026, Cloud Storage exige una cuenta de facturación incluso con uso
mínimo. Eso obliga a mover dos piezas, y el resultado es igual de bueno:

| Pieza | Con Blaze | En Spark |
|---|---|---|
| Lectura y escritura de conteos | Firestore | **Firestore, igual** |
| Tiempo real entre operarios | Firestore | **Firestore, igual** |
| Proxy de la API de Depot | Cloud Function | **Apps Script** |
| Fotos de producto no conforme | Cloud Storage | **Google Drive** |
| Correo del informe final | Cloud Function | **Apps Script** |
| Importar el packing list | Cloud Function | **El navegador** |
| Roles de usuario | Custom claims | **Documento en Firestore** |

**Lo que no cambia es lo que más importa:** el escaneo sigue siendo el navegador
contra Firestore, 50–150 ms. Apps Script solo interviene en el precalentado
(una vez por recepción), alguna consulta suelta y el cierre.

### Por qué el proxy en Apps Script no es un parche

Hace tres cosas que el navegador no puede hacer solo:

1. **Guarda las credenciales de Depot** donde el dispositivo no las ve.
2. **Esquiva CORS y el contenido mixto.** Tu API es `http://dominio.com/apidepot`
   y la app será `https://`. Un navegador **bloquea** esa llamada; un servidor
   no. Sin el proxy, la app no podría hablar con Depot aunque quisiera.
3. **Sube las fotos a Drive** y **envía el correo**, que es justo lo que Spark
   quitó.

---

## Índice

0. [Dónde se hace cada cosa](#0-dónde-se-hace-cada-cosa)
1. [Antes de empezar](#1-antes-de-empezar)
2. [El proyecto de Firebase](#2-el-proyecto-de-firebase)
3. [Autenticación con Google corporativo](#3-autenticación-con-google-corporativo)
4. [Herramientas y despliegue](#4-herramientas-y-despliegue)
5. [El proxy de Depot en Apps Script](#5-el-proxy-de-depot-en-apps-script)
6. [Cargar el token y las credenciales](#6-cargar-el-token-y-las-credenciales)
7. [Probar la conexión con Depot](#7-probar-la-conexión-con-depot)
8. [El primer administrador](#8-el-primer-administrador)
8.bis [Quién entra y cómo](#8bis-quién-entra-y-cómo)
8.ter [Dónde queda guardada cada cosa](#8ter-dónde-queda-guardada-cada-cosa)
9. [Usar la app](#9-usar-la-app)
10. [Instalar en los handheld](#10-instalar-en-los-handheld)
11. [Errores frecuentes](#11-errores-frecuentes)
12. [Vigilar las cuotas](#12-vigilar-las-cuotas)

---

## 0. Dónde se hace cada cosa

Hay dos lugares distintos y conviene tenerlo claro desde el principio:

| Paso | Dónde | Qué es |
|---|---|---|
| 2 · Crear Firestore y registrar la app | **Navegador** | console.firebase.google.com |
| 3.2 y 3.3 · Activar Google y autorizar dominios | **Navegador** | Misma consola |
| 3.6 y 4 · Desplegar | **Terminal de tu PC** | PowerShell en Windows, Terminal en Mac |
| 5 · El proxy | **Navegador** | script.google.com |
| 6 y 7 · Token y pruebas | **Navegador** | Editor de Apps Script |
| 8 · Primer administrador | **Navegador** | Consola de Firebase |

Los comandos **se ejecutan en tu computador**, no en el servidor ni en la
consola de Firebase. Lo que hacen es subir los archivos del proyecto a Firebase.

### Abrir la terminal

**Windows:** tecla Windows → escribe `powershell` → Enter.
**Mac:** Cmd+Espacio → escribe `terminal` → Enter.

> **No la abras como administrador.** No hace falta para nada de esto, y
> arranca en `C:\WINDOWS\system32`, donde acabarías descargando el proyecto
> por error. La terminal normal arranca en tu carpeta de usuario, que es donde
> debe ir.

Verás una ventana donde se escriben comandos y se pulsa Enter después de cada
uno. Espera a que termine cada comando antes del siguiente.

### Lo que hay que instalar una sola vez

| Programa | Para qué | Dónde |
|---|---|---|
| **Node.js** (versión LTS) | Ejecuta las herramientas de Firebase | [nodejs.org](https://nodejs.org) |
| **Git** | Descarga el proyecto | [git-scm.com](https://git-scm.com/downloads) |

En ambos instaladores: **Siguiente** hasta el final, sin cambiar nada.

> **Después de instalar, cierra la terminal y ábrela de nuevo.** Si no, no
> reconocerá los comandos nuevos. Es el tropiezo más común.

Comprueba que quedaron bien:

```bash
node --version
git --version
```

Deben responder con un número de versión. Si alguno dice "no se reconoce el
comando", no se instaló o no reabriste la terminal.

### Por qué el `-b` del comando

El proyecto vive en la rama `pr_bep/serene-thompson-10qlxd`, no en `main`.
`main` solo tiene el README inicial.

Sin `-b`, Git descarga `main` y te deja una carpeta casi vacía: no existirá
`firebase`, y `firebase use --add` dirá *"must be run from a Firebase project
directory"*. **No es que falte instalar nada: es que no se descargó el
proyecto.**

Para comprobar qué rama tienes:

```bash
git branch --show-current
```

Debe responder `pr_bep/serene-thompson-10qlxd`. Si dice `main`:

```bash
git checkout pr_bep/serene-thompson-10qlxd
```

### Si prefieres no instalar Git

Puedes descargar el proyecto como archivo comprimido:

1. Entra a [la rama del proyecto](https://github.com/brantos102/IV_ITSANET/tree/pr_bep/serene-thompson-10qlxd)
2. Botón verde **Code** → **Download ZIP**
3. Descomprime en `Documentos`
4. En la terminal, entra a esa carpeta con `cd` (ver abajo)

> **Asegúrate de descargar el ZIP desde ese enlace**, que apunta a la rama. El
> ZIP de la página principal trae `main`, que está vacío.

Con Git es más cómodo para actualizar después, pero el ZIP funciona igual.

### Moverse entre carpetas

El comando `cd` cambia de carpeta. Si descargaste el proyecto en `Documentos`:

```bash
cd Documentos\IV_ITSANET\firebase      # Windows
cd ~/Documentos/IV_ITSANET/firebase      # Mac
```

**Atajo en Windows:** abre la carpeta `firebase` en el Explorador, haz clic en
la barra de direcciones, escribe `powershell` y pulsa Enter. Se abre una
terminal ya situada ahí.

Para saber dónde estás: `pwd` en Mac, `cd` sin nada en Windows.

---

## 1. Antes de empezar

| Requisito | Detalle |
|---|---|
| Cuenta de Google Workspace | La corporativa `@itsanet.com` |
| Node.js 20 o superior | [nodejs.org](https://nodejs.org), versión LTS |
| Una terminal | PowerShell en Windows, Terminal en Mac |
| **Nada de tarjeta** | Todo lo de esta guía entra en el nivel gratuito |

```bash
node --version
```

Debe decir `v20` o superior. Si no, instala la LTS y **cierra y vuelve a abrir
la terminal**.

### Datos que necesitas a mano

Antes de empezar, consigue esto de quien administra el WMS:

- [ ] URL base de la API, p. ej. `http://dominio.com/apidepot`
- [ ] Usuario y contraseña del cliente para `/gettoken/`, si los pide
- [ ] Un código de producto que exista, para probar
- [ ] **Confirmación de que la API responde desde fuera de la red interna**

> Lo último es importante. Apps Script llama desde los servidores de Google, no
> desde la red de Itsanet. Si el WMS solo acepta conexiones internas, hay que
> pedirle a TI que autorice el rango de salida de Apps Script. Compruébalo con
> `probarDepot()` en el paso 7 antes de seguir construyendo encima.

---

## 2. El proyecto de Firebase

Ya tienes **IV ITSANET** en plan Spark. Solo falta activar Firestore.

### 2.1 Firestore — crear la base DESDE LA CONSOLA

> **Este paso no se puede saltar, y hay que hacerlo en el navegador.**
>
> Si llegas al despliegue sin haber creado la base aquí, el CLI intentará
> crearla por su cuenta y fallará con un error que despista:
>
> ```
> firestore: Creating the new Firestore database (default)...
> Error: HTTP Error: 403, This API method requires billing to be enabled.
> ```
>
> **No significa que Firestore necesite plan de pago.** Significa que *crear* la
> base mediante la API administrativa sí lo necesita. Creándola desde la consola
> se usa otra ruta, que funciona en Spark con su cuota gratuita. Hecho eso, el
> despliegue de reglas ya no intenta crear nada y pasa sin problema.

1. [console.firebase.google.com](https://console.firebase.google.com) → tu proyecto
2. **Compilación** → **Firestore Database** → **Crear base de datos**
3. **Modo de producción**
   > No elijas modo de prueba: deja la base abierta a cualquiera 30 días. Las
   > reglas se despliegan en el paso 4.
4. Ubicación: **`us-central1`**, o `southamerica-east1` para menos latencia
   desde Ecuador
   > **No se puede cambiar después.** Cambiarla obliga a borrar el proyecto.
5. **Habilitar**

### 2.2 Registrar la aplicación web

1. **Configuración del proyecto** (el engranaje) → **Tus apps** → icono **`</>`**
2. Apodo: `val-ventura-pwa`
3. Marca **"También configura Firebase Hosting"**
4. **Registrar app**
5. **Copia el bloque `firebaseConfig`** que te muestra. Lo necesitas en el paso 4

```javascript
const firebaseConfig = {
  apiKey: "AIzaSy...",            // ← también la usarás en el paso 5
  authDomain: "iv-itsanet.firebaseapp.com",
  projectId: "iv-itsanet",
  storageBucket: "iv-itsanet.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123:web:abc"
};
```

> La `apiKey` **no es un secreto**. Identifica al proyecto, no da acceso. Lo que
> protege los datos son las reglas de Firestore.

---

## 3. Autenticación con Google corporativo

### 3.1 Sobre el tipo de cuenta corporativa

No hace falta averiguarlo por adelantado: **la app funciona con los dos tipos**,
y la página de comprobación del paso 3.6 te dice cuál tienes.

| Tipo | Qué es | ¿Funciona? |
|---|---|---|
| **Google Workspace** | El dominio está gestionado por Google | Sí |
| **Cuenta de Google con correo corporativo** | Una cuenta normal creada con una dirección `@itsanet.com` | Sí |
| **Sin cuenta de Google** | El correo es de Microsoft u otro, sin cuenta de Google asociada | No |

Si tu correo aparece en el selector de cuentas de Google, estás en los dos
primeros casos y todo funciona.

> **No uses `admin.google.com` para comprobarlo.** Esa consola solo la abren los
> *administradores* de Workspace, así que el mensaje "Accede con una cuenta de
> administrador" no dice nada sobre si tu cuenta sirve para la app.
>
> Si quieres saberlo con certeza, entra a
> [myaccount.google.com](https://myaccount.google.com) con la cuenta
> corporativa: si arriba dice *"Esta cuenta la gestiona itsanet.com"*, es
> Workspace.

#### Por qué `hd` viene apagado

`firebase/public/js/config.js` trae `USAR_PISTA_HD = false`, y conviene dejarlo
así salvo que confirmes que el dominio está en Workspace.

`hd` filtra el selector de Google a las cuentas **gestionadas por Workspace**,
comparando el dominio con un campo que solo esas cuentas llevan. Si tu correo
corporativo es en realidad una cuenta de Google normal, activarlo **esconde la
cuenta del selector** y el operario no puede entrar, sin ningún error que
explique por qué.

Como `hd` solo es comodidad —se puede saltar, no protege nada— no compensa el
riesgo. La protección real son las reglas de Firestore.

### 3.2 Activar el acceso con Google

1. Consola de Firebase → **Compilación** → **Authentication**
2. **Comenzar** (si es la primera vez)
3. Pestaña **Sign-in method**
4. Clic en **Google**
5. Activa el interruptor **Habilitar**
6. **Nombre público del proyecto:** `VAL VENTURA — Itsanet`
   > Es lo que verá el operario en la pantalla de Google. Que se reconozca.
7. **Correo de asistencia del proyecto:** elige el tuyo del desplegable
8. **Guardar**

Debe quedar **Google · Habilitado** en la lista.

### 3.3 Autorizar los dominios

Sin esto el login falla con `auth/unauthorized-domain`, que es el error más
común de este paso.

1. Misma pantalla → pestaña **Settings** → **Authorized domains**
2. Comprueba que estén:

   - `localhost`
   - `iv-itsanet.firebaseapp.com`
   - `iv-itsanet.web.app`

3. Si falta alguno: **Add domain** y escríbelo

### 3.4 Restringir al dominio corporativo

La restricción va en tres capas, porque una sola no basta:

| Capa | Dónde | Qué hace | ¿Protege? |
|---|---|---|---|
| Pista `hd` | `public/js/config.js` | El selector de Google solo ofrece cuentas `@itsanet.com` | **No.** Es comodidad: se puede saltar |
| Cierre de sesión | `public/js/auth.js` | Si el correo no es del dominio, cierra la sesión y avisa | Parcialmente |
| Reglas de Firestore | `firestore.rules` | Rechaza toda lectura y escritura | **Sí.** Esta es la real |

Un usuario de Gmail puede completar el login de Google. Lo que no puede es leer
ni escribir **nada**: las reglas lo rechazan.

> **Si tu dominio no es `itsanet.com`**, cámbialo en tres sitios:
> `firebase/firestore.rules` (busca `itsanet[.]com`), `DOMINIO` en
> `firebase/public/js/config.js`, y `DOMINIO_PERMITIDO` en las propiedades del
> Apps Script (paso 5).
>
> En las reglas el punto va escapado como `[.]` a propósito: en una expresión
> regular `.` casa con cualquier carácter, así que `itsanet.com` sin escapar
> también aceptaría `itsanetXcom`.

### 3.5 Tu configuración ya está puesta

El archivo `firebase/public/js/config.js` del repositorio ya trae los valores de
**IV ITSANET**. Compruébalo:

```javascript
apiKey: 'AIzaSyBCfPBE9YryYl8EX0vOVIgKQv2ZVro8ziM',
projectId: 'iv-itsanet',
```

> Esos valores **no son secretos**. Identifican al proyecto y viajan dentro del
> JavaScript que descarga cualquier visitante del sitio: no hay forma de
> ocultarlos ni hace falta. Lo que protege los datos son las reglas de
> Firestore. Lo que sí es secreto —las credenciales de Depot— vive en las
> propiedades del Apps Script, del lado servidor.

---

### 3.6 Probarlo

Aquí se verifica que los pasos 2 y 3 quedaron bien. Desde `IV_ITSANET/firebase`:

```bash
firebase use --add            # elige IV ITSANET, alias: default
firebase deploy --only firestore:rules,firestore:indexes
firebase deploy --only hosting
```

Abre la URL que te devuelve (`https://iv-itsanet.web.app`) y pulsa **Entrar con
Google**.

### Qué debe pasar

1. Se abre Google ofreciendo solo cuentas `@itsanet.com`
2. Entras
3. Aparece tu foto, tu nombre y el rol **OPERADOR**
4. Un aviso dice que se creó tu perfil
5. Abajo, una tabla de comprobación:

| | |
|---|---|
| SDK de Firebase | 10.14.1 |
| Proyecto | iv-itsanet |
| Base de datos | bd-iv-itsanet |
| Acceso con Google | activo |
| Dominio corporativo | @itsanet.com |
| Tipo de cuenta | Google Workspace *(o "Google con correo corporativo")* |
| Perfil en Firestore | creado |
| Rol asignado | OPERADOR |
| Leer Firestore | correcto |
| Proxy de Depot | pendiente (paso 5) |
| Recepciones | ninguna todavía |

**"Proxy de Depot: pendiente" es lo correcto en este punto.** Se configura en el
paso 5.

### Hazte administrador

Mientras estás aquí, aprovecha:

1. Consola de Firebase → **Firestore Database** → colección **`usuarios`**
2. Abre el documento con tu uid
3. Campo **`rol`**: cambia `OPERADOR` por `ADMIN`
4. **Recarga la app**

El chip debe pasar a **ADMIN** y aparecer *"Todo listo"*.

> Con los roles en Firestore el cambio es inmediato: no hay que cerrar sesión.
> Es la ventaja de haberlos movido ahí al perder las Cloud Functions.

### Si algo falla

| Lo que ves | Causa | Solución |
|---|---|---|
| `auth/unauthorized-domain` | Falta el dominio | Paso 3.3 |
| `auth/operation-not-allowed` | Google sin habilitar | Paso 3.2 |
| `auth/popup-blocked` | El navegador bloqueó la ventana | Permite ventanas emergentes, o pruébalo en el móvil (usa redirect) |
| "Esta aplicación es solo para cuentas de itsanet.com" | Entraste con una cuenta personal | Usa la corporativa. **Que salga este mensaje significa que la restricción funciona** |
| "Las reglas rechazan la lectura" | Reglas sin desplegar | `firebase deploy --only firestore:rules` |
| `unavailable` al leer Firestore | La base no existe | Paso 2.1 |
| Página en blanco | Error de carga | Abre la consola del navegador (F12) y mándame lo que diga |
| Entra pero no crea el perfil | Las reglas rechazan el alta | Confirma que el dominio de `firestore.rules` coincide con tu correo |
| Tu cuenta no aparece en el selector de Google | `USAR_PISTA_HD` activado sin tener Workspace | Ponlo en `false` en `public/js/config.js` y vuelve a desplegar |
| "No es una cuenta de Workspace" | Normal si el correo no está gestionado por Google | La app funciona igual. Afecta solo a la cuota de correo del paso 5: 100 al día en vez de 1500 |

**No sigas al paso 4 hasta que la tabla salga completa.** Cada paso se apoya en
el anterior, y un fallo aquí se manifiesta mucho más tarde y más confuso.

---

## 4. Herramientas y despliegue

```bash
npm install -g firebase-tools
firebase login
```

**Si Windows dice "no se reconoce el comando":** cierra PowerShell y ábrelo de
nuevo. Si persiste, como administrador:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Si Mac/Linux da error de permisos:** no uses `sudo`.

```bash
mkdir -p ~/.npm-global && npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc && source ~/.zshrc
npm install -g firebase-tools
```

### Clonar y vincular

```bash
git clone -b pr_bep/serene-thompson-10qlxd https://github.com/brantos102/IV_ITSANET.git
cd IV_ITSANET/firebase
firebase use --add          # elige IV ITSANET, alias: default
```

### Comprobar antes de desplegar

Estás dentro de `firebase/`, así que el runner va un nivel arriba:

```bash
node ../pruebas.js
```

Debe terminar con **«todas en verde»**. Si no, **no despliegues**.

### Desplegar

Si ya lo hiciste en el paso 3.6, no hay nada más que hacer aquí. Para volver a
desplegar tras un cambio:

```bash
firebase deploy --only firestore:rules,firestore:indexes
firebase deploy --only hosting
```

Las reglas **primero**. Si despliegas la app antes, hay una ventana con la base
sin proteger.

> **No despliegues `functions` ni `storage`.** Requieren Blaze y el comando
> fallará. En Spark esas piezas las cubre Apps Script.

Al terminar te da la URL:

```
Hosting URL: https://iv-itsanet.web.app
```

**Esa es la que reparten a los operarios.**

---

## 5. El proxy de Depot en Apps Script

### 5.1 Crear el proyecto

> **Quién crea el Apps Script es el dueño de los datos.** El proyecto, la
> carpeta de evidencias en Drive y las credenciales de Depot quedan bajo esa
> cuenta de Google.
>
> Si la cuenta no está gestionada por Workspace, la empresa **no** puede
> recuperarla si la persona se va o pierde el acceso. Para una herramienta de
> operación conviene crearlo con una cuenta que la empresa controle, o al menos
> compartir el proyecto y la carpeta con un segundo responsable
> (**Compartir** → rol **Editor**) desde el primer día.

1. Entra a [script.google.com](https://script.google.com) **con la cuenta
   corporativa**
2. **Nuevo proyecto** → nómbralo `VAL VENTURA — Proxy Depot`
3. Borra el contenido de `Código.gs` y pega entero `apps-script/proxy/Proxy.gs`
4. **Archivo → Nuevo → Secuencia de comandos**, nómbrala `Clientes`, y pega
   entero `apps-script/proxy/Clientes.gs`
5. Guarda (Ctrl+S)

> Son **dos** archivos. `Clientes.gs` es el que guarda las credenciales de cada
> cliente; sin él el proxy arranca pero no sabe a quién consultar.

### 5.2 Carpeta de Drive para las fotos

1. En Drive, crea una carpeta `VAL VENTURA — Evidencias`
2. Ábrela y copia el id de la URL:
   `https://drive.google.com/drive/folders/`**`1a2B3c4D5e6F7g8H`**

### 5.3 Las propiedades

En el editor de Apps Script: **Configuración del proyecto** (engranaje) →
**Propiedades de la secuencia de comandos** → **Agregar propiedad**.

| Propiedad | Valor | Obligatoria |
|---|---|---|
| `DEPOT_BASE_URL` | `https://ec.itsanet.com/q_apidepot` | Sí |
| `FIREBASE_API_KEY` | La `apiKey` del paso 2.2 | Sí |
| `FIREBASE_PROJECT_ID` | `iv-itsanet` | Sí |
| `FIREBASE_DATABASE_ID` | `bd-iv-itsanet` | Sí |
| `DOMINIO_PERMITIDO` | `itsanet.com` | Sí |
| `CARPETA_EVIDENCIAS` | El **enlace o el id** de la carpeta del paso 5.2 | Para fotos e informes |
| `DEPOT_RUTA_TOKEN` | `/gettoken` | No (ya es el valor por defecto) |
| `DEPOT_RUTA_STOCK` | `/getstock` | No (ya es el valor por defecto) |

> **El contrato real de la API**, confirmado contra el Centro de Mando:
>
> | | |
> |---|---|
> | Token | `GET /gettoken`, **sin barra final** |
> | Credenciales | cabeceras `userid` y `password` |
> | Token en la respuesta | `token`, `Token`, `Result` o `result` |
> | Consulta | `GET /getstock` (todo) o `/getstock/CODIGO` (uno) |
> | Autenticación | cabecera `token` |
> | Filas | array suelto, o dentro de `Result`, `result` o `data` |
>
> Campos que devuelve: `COD. PRODUCTO`, `DESCRIPCION`, `UNIDAD`, `CANTIDAD`,
> `NAVE`, `CALLE`, `COLUMNA`, `NIVEL`, `NRO. SERIE`, `NRO. LOTE`,
> `NRO. DESPACHO`, `NRO. PARTIDA`, `CAT. LOG.`, `EST. MERC.`, `COD. CLIENTE`,
> `FAMILIA`.
>
> **No hay código de barras.** La validación por EAN no puede salir de aquí.

> **Las credenciales de los clientes NO van aquí.** Se cargan desde el panel de
> administración de la app, que las guarda en estas mismas propiedades pero bajo
> `CRED_<ID>`, una por cliente. Así no hay que abrir el editor de Apps Script
> cada vez que entra un cliente nuevo.
>
> `FIREBASE_PROJECT_ID` y `FIREBASE_DATABASE_ID` son necesarias para que el
> proxy pueda comprobar que quien pide guardar credenciales es realmente un
> ADMIN: lo lee de Firestore con el token del propio operario, así que se
> aplican las mismas reglas que en la app.

### 5.4 Publicar

1. **Implementar** → **Nueva implementación**
2. Tipo: **Aplicación web**
3. Descripción: `v1`
4. **Ejecutar como:** `Yo`
5. **Quién tiene acceso:** `Cualquier usuario`
   > Suena abierto y no lo es: el script exige un token de sesión de Firebase
   > válido y del dominio corporativo antes de hacer nada. Está probado
   > (`apps-script/test/proxy.test.js`). Con `Solo yo` la app no podría llamarlo.
6. **Implementar**
7. Autoriza cuando lo pida: **Revisar permisos** → tu cuenta → **Avanzado** →
   **Ir a (no seguro)** → **Permitir**
   > La advertencia aparece porque el script no está verificado por Google. Es
   > tuyo y está en tu dominio.
8. **Copia la URL de la aplicación web** (`https://script.google.com/macros/s/.../exec`)

### 5.5 Guardar la URL en Firestore

Consola de Firebase → **Firestore** → **Iniciar colección**:

- Colección: `config`
- Id del documento: `proxy`
- Campo: `url` (string) = la URL del paso 5.4

---

## 6. Cargar el token y las credenciales

No hay que cargar ningún token a mano: **el proxy lo pide solo** a
`/gettoken/` y lo reutiliza toda la jornada.

```
Consulta → ¿token en caché del script?   → sí: se usa          (0 ms)
              ↓ no (el caché dura 6 h)
           ¿token en las propiedades?    → sí: se usa          (~10 ms)
              ↓ vencido
           GET /gettoken/                → se guarda y se usa  (~500 ms)
```

- **Un solo `gettoken` al día.** Probado: 20 consultas seguidas → 1 `gettoken`.
- **Sobrevive al caché.** El caché de Apps Script expira a las 6 horas; las
  propiedades lo mantienen el resto de la jornada.
- **Revocación.** Si el WMS invalida el token antes de tiempo, la llamada que
  reciba un 401 lo renueva y reintenta sola.
- **El token nunca sale.** `estadoToken` dice si está vigente y cuántos minutos
  le quedan, nunca su valor.

### El detalle que más confunde

Tu API usa una cabecera llamada **`token`**, no `Authorization: Bearer`:

```
GET http://dominio.com/apidepot/getstock/2H0525345
token: TK-abc123
```

Mandarlo como `Bearer` devuelve 401 sin explicar nada. El adaptador ya lo manda
bien, y hay una prueba que lo vigila.

---

### Si la página de administración dice «No se pudo contactar al proxy»

No adivines entre las causas: la propia página te dice cuál es. En
`/admin.html`, primer panel, **Conexión con el proxy** → **Probar conexión**.

Hace un GET a la URL y distingue los cuatro casos:

| Lo que responde | Qué significa |
|---|---|
| `{"ok":true,"servicio":"proxy-depot"}` | Correcto. Si aún falla, el problema está en las propiedades del script |
| El navegador no pudo llegar | El despliegue **no** está en «Cualquier usuario» |
| Una página HTML | Es la pantalla de acceso de Google: lo mismo |
| 404 | La URL está mal copiada o el despliegue se borró |

Los dos errores que más se repiten:

1. **«Cualquier usuario con cuenta de Google»** en vez de **«Cualquier
   usuario»**. Son opciones distintas y solo la segunda funciona: la primera
   redirige al login, y el navegador bloquea esa redirección. Se cambia en
   **Implementar → Gestionar implementaciones → ✏️**, y hay que guardar como
   **versión nueva**.
2. **La URL de `/dev`** en lugar de la de `/exec`. La de `/dev` es la de
   pruebas y exige tu sesión de Google; desde la app nunca va a funcionar.

Desde ese mismo panel puedes pegar la URL correcta y guardarla, sin entrar a
Firestore a mano.

---

## 7. Probar la conexión con Depot

**Antes de construir nada encima.** En el editor de Apps Script:

1. Selecciona la función `verificarConfiguracion` → **Ejecutar**
2. Mira **Registro de ejecución** (Ctrl+Enter)

```
Configuración completa.
URL base: http://dominio.com/apidepot
Dominio permitido: itsanet.com
```

3. Ahora `probarDepot` → **Ejecutar**

```
gettoken OK. Token de 36 caracteres.
getstock OK. 476 filas.
Campos que devuelve: codigo_producto, descripcion, codigo_barra, stock
Primera fila mapeada: {"sku":"2H0525345","descripcion":"WASHER",...}
```

**Esa línea de "Campos que devuelve" es la más valiosa de toda la instalación.**
Mándamela: con ella ajusto el mapeo exacto en vez de adivinar entre variantes.

### Si falla

| Mensaje | Causa | Qué hacer |
|---|---|---|
| `Falta DEPOT_BASE_URL` | Propiedad sin guardar | Paso 5.3 |
| `Depot rechazó las credenciales` | Usuario o clave mal | Confirma con quien administra el WMS |
| `sin un token reconocible` | `/gettoken/` responde en otro formato | **Mándame lo que imprime el registro** y lo mapeo |
| `Address unavailable` / timeout | El WMS no acepta conexiones externas | Pide a TI que autorice la salida de Apps Script |
| `Depot respondió 404` | La ruta no es `/gettoken/` | Ajusta `DEPOT_RUTA_TOKEN` |

> El error de timeout es el más probable y el que más tiempo ahorra detectar
> ahora. Si el WMS es solo interno, hay que resolverlo con TI antes de seguir.

---

## 8. El primer administrador

Con Google corporativo no hay que crear usuarios: **cada quien se da de alta al
entrar por primera vez**, y queda como `OPERADOR`. El dominio es la puerta.

Pero el primero tiene que ser `ADMIN`, y eso se hace una sola vez a mano.

1. Entra a `https://iv-itsanet.web.app` con tu cuenta corporativa
2. Eso crea tu documento en `usuarios`
3. Consola de Firebase → **Firestore** → colección `usuarios` → tu documento
4. Cambia el campo `rol` de `OPERADOR` a `ADMIN`
5. **Recarga la app**

> Con roles en Firestore el cambio es inmediato: no hay que cerrar sesión, a
> diferencia de los custom claims. Es la ventaja de haber tenido que moverlos.

### Los roles

| | OPERADOR | SUPERVISOR | ADMIN |
|---|---|---|---|
| Escanear y contar | Sí | Sí | Sí |
| Anular su propio conteo | Sí | Sí | Sí |
| Anular el de otro | No | Sí | Sí |
| Crear recepciones, subir packing list | No | Sí | Sí |
| Cerrar la validación | No | Sí | Sí |
| Cambiar roles | No | No | Sí |

Un ADMIN **no puede quitarse el rol a sí mismo**: evita quedarse sin ningún
administrador.

---

## 8.bis Quién entra y cómo

Tres caminos, y ninguno deja que alguien se asigne a sí mismo un rol.

| | Registro propio | Alta por el administrador | Cuenta de Google |
|---|---|---|---|
| Quién lo usa | cualquiera que llegue al enlace | operarios que no quieren registrarse | supervisores y administradores de `@itsanet.com` |
| Qué pide | nombre, apellido, usuario, correo real, contraseña | lo mismo, lo escribe el admin | nada, Google ya lo sabe |
| Nace | **desactivado** | activo | activo, como OPERADOR |
| Entra | cuando lo aprueban | enseguida | enseguida |

### El usuario y el correo son cosas distintas

El operario entra escribiendo `jperez`, no su correo: con guantes y en el
relevo de turno, cada carácter de más es un intento fallido.

Pero la **identidad** es un correo real, no uno inventado. Suponer que
`jperez@itsanet.com` existe es suponer algo que nadie comprobó, y si mañana hay
que escribirle a esa persona, no hay a dónde. Por eso el registro pide un buzón
que exista —corporativo o personal— y el alias es solo la forma corta de
entrar.

La correspondencia vive en la colección `alias`, que guarda únicamente el
usuario, su correo y su uid. Se lee sin haber iniciado sesión, porque hace
falta justo antes de entrar, pero **de uno en uno**: las reglas permiten `get`
y prohíben `list`, así que se puede comprobar un alias concreto y no se puede
sacar la lista de nadie.

### Por qué el registro abierto no es un agujero

Cualquiera que llegue al enlace puede pedir acceso. Lo que no puede es entrar:
la cuenta nace con `activo: false` y hasta que un administrador la apruebe no
ve ni un dato. Lo impone la regla de Firestore, no la pantalla:

```
allow create: if ... && request.resource.data.activo == false
                     && request.resource.data.rol == 'OPERADOR'
```

En **Usuarios**, los que esperan aprobación salen primero y con un aviso arriba.
Antes de aprobar a alguien, comprueba que sea quien dice ser.

### Activar el método (una sola vez)

Consola de Firebase → **Authentication** → **Sign-in method** →
**Correo electrónico/contraseña** → activar el primer interruptor. El segundo,
«Vínculo del correo electrónico», se queda apagado.

Sin esto, tanto el registro como el alta dan *«Ese método de acceso no está
activado»*.

### Dar de alta a un operario desde Administración

Entra como ADMIN → **Usuarios** → usuario, nombre, correo real y contraseña.
El botón **Sugerir contraseña** genera una fácil de dictar por radio: sin `O`/`0`
ni `l`/`1`, que con guantes y poca luz se confunden.

Al crear sale un recuadro con el enlace, el usuario y la contraseña: **es la
única vez que se muestra**. Ni la app ni Firebase la guardan en claro. Si se
pierde, se genera otra.

### Roles

| | OPERADOR | SUPERVISOR | ADMIN |
|---|:---:|:---:|:---:|
| Escanear y contar | sí | sí | sí |
| Registrar PNC con fotos | sí | sí | sí |
| Anular sus propios conteos | sí | sí | sí |
| Crear recepciones y subir el packing list | — | sí | sí |
| Descargar el catálogo de Depot | — | sí | sí |
| Anular el conteo de cualquiera | — | sí | sí |
| Cerrar y enviar el informe | — | sí | sí |
| Ver indicadores y trazabilidad | — | sí | sí |
| Dar de alta operarios | — | sí | sí |
| Credenciales de Depot por cliente | — | — | sí |
| Cambiar roles y aprobar registros | — | — | sí |

Esta misma tabla sale en la pantalla de inicio de cada persona, con lo que
puede y lo que no. Así nadie descubre a mitad de turno que no puede cerrar, y
un supervisor ve de un vistazo qué ve su gente.

Que un operario valide una recepción que subió un supervisor es lo esperado: el
supervisor prepara y cierra, el operario cuenta. Lo que no puede un operario es
abrirla, cerrarla, ni tocar lo que declara el sistema.

La **comprobación de la instalación** solo la ve un ADMIN. A un operario no le
dice nada y le llenaba la pantalla de configuración que no puede ni debe
tocar.

Cambiar un rol surte efecto **de inmediato**, sin esperar a que caduque la
sesión. Desactivar a alguien lo saca en la siguiente operación.

Un ADMIN no puede quitarse el rol a sí mismo, para que nunca quede el sistema
sin administrador.

---

## 8.ter Dónde queda guardada cada cosa

Pregunta legítima antes de entregar: si mañana hay una reclamación, ¿de dónde
se saca la prueba?

| Qué | Dónde | Quién puede verlo |
|---|---|---|
| Líneas del packing list | Firestore `bd-iv-itsanet` → `recepciones/{código}/lineas` | cualquier usuario activo |
| Conteo por SKU | → `recepciones/{código}/skus` | ídem |
| **Cada conteo, uno a uno** | → `recepciones/{código}/eventos` | ídem |
| Adicionales | → `recepciones/{código}/adicionales` | ídem |
| Usuarios y roles | → `usuarios/{uid}` | el propio usuario y los supervisores |
| Catálogo de Depot | → `productos` y `codigos` | cualquier usuario activo |
| **Fotos de PNC** | Google Drive, carpeta `CARPETA_EVIDENCIAS`, una subcarpeta por recepción | quien tenga acceso a esa carpeta |
| **Informe final `.xlsx`** | la misma subcarpeta de Drive, y adjunto en el correo | ídem |
| Credenciales de Depot | Propiedades del Apps Script | solo quien edita el script |

### Lo que no se borra nunca

`eventos` es un libro de sólo-añadir. Un conteo registrado no se modifica ni se
elimina: anularlo escribe un segundo registro que lo compensa, firmado por quien
lo anuló y con el motivo. Esa es la base de los KPI y de cualquier reclamación.

Las reglas de Firestore lo imponen; no es una convención que dependa de que la
app se porte bien:

```
match /recepciones/{id}/eventos/{eventoId} {
  allow create: ...        // con el uid y el correo de quien escribe
  allow update, delete: if false;
}
```

### El informe final

Al cerrar una recepción, el `.xlsx` va a **tres sitios a la vez**:

1. Se **descarga** en el equipo del supervisor.
2. Se **archiva en Drive**, junto a las fotos de esa misma recepción.
3. Se **envía por correo** a quien se indique, como adjunto.

El correo se borra y la descarga se pierde con el equipo; la copia de Drive es
la que queda. Si la recepción se cierra más de una vez, se numera —
`validacion-VW (2).xlsx` — en lugar de pisar la anterior.

### Dónde mirarlo a mano

- **Datos:** consola de Firebase → Firestore Database → base `bd-iv-itsanet`
- **Fotos e informes:** Google Drive → la carpeta cuyo id está en
  `CARPETA_EVIDENCIAS` de las propiedades del Apps Script

> **Quién es el dueño.** Hoy la carpeta de Drive y el Apps Script cuelgan de
> `bespinoza@itsanet.com`. Si esa cuenta se pierde, la empresa pierde las fotos,
> los informes archivados y las credenciales de Depot. Compártelos con un
> segundo responsable antes de entregar.

---

## 9. Usar la app

Son tres pantallas. El enlace es el mismo para todos:
`https://iv-itsanet.web.app`.

| Pantalla | Quién | Para qué |
|---|---|---|
| `/` | todos | Entrar y comprobar la instalación |
| `/recepciones.html` | supervisor | Crear la recepción, subir el packing list, bajar el catálogo |
| `/validar.html?r=CODIGO` | operario | Escanear y contar |
| `/kpis.html` | supervisor / admin | Indicadores y trazabilidad |
| `/usuarios.html` | supervisor / admin | Dar de alta operarios y asignar roles |
| `/admin.html` | admin | Credenciales de Depot por cliente |

### 9.1 Abrir una recepción (supervisor)

1. **Recepciones** → código (`VW-29-06-2026`), cliente, bultos → **Crear**.
2. **Archivo .xlsx** → se muestran las primeras líneas para confirmar que leyó
   la tabla correcta → **Guardar packing list**.

   Busca la fila de encabezados en las primeras 25, así que tolera logos y
   títulos encima. Necesita al menos las columnas **ITEM** (o SKU, CÓDIGO,
   PRODUCTO) y **CANTIDAD**.

3. **Descargar catálogo** — una sola vez por jornada.

   Esto es lo que hace que el escaneo sea instantáneo. `getstock` sin código
   devuelve el stock completo del cliente, así que es **una** llamada al WMS por
   cliente, no una por SKU. Después, cada escaneo es la lectura de un documento
   de Firestore en vez de una consulta a Depot.

   Si se omite, la app sigue funcionando: consulta Depot en vivo la primera vez
   que ve cada código y guarda la equivalencia. Solo es más lento.

### 9.2 Contar (operario)

En el listado, **Validar** abre la pantalla de escaneo. El flujo es el que
pediste:

1. **Escanear** — el cursor ya está en el campo; la pistola manda Enter sola.
2. **Validación** — si el código existe sale la descripción, la unidad, el stock
   y la posición que devuelve Depot. Si no existe, el paso 8.
3. **Cantidad** — viene con lo que falta de ese SKU. Un escaneo suma 1.

   > **Para contar varias de una vez:** el campo **Cantidad** está al lado del
   > escáner. Escribe ahí la cantidad *antes* de escanear y ese escaneo
   > registra esa cantidad completa. Vuelve a 1 después de cada registro.

4. **Pallet** — alfanumérico (`A1`, `B04`) con subpallets (`B04.1`). Si ese SKU
   ya se guardó en algún pallet, salen botones con cada ubicación y su cantidad:
   es la sugerencia de dónde ya está.
5. **Observación** — opcional.
6. **Estado** — BUENO o **PNC**. PNC exige observación y permite fotos, que se
   suben a la carpeta de Drive.
7. **Registrar** — y el cursor vuelve al campo de escaneo.

Suena un pitido agudo si se registró y uno grave si algo falló, y el handheld
vibra. El operario no tiene que mirar la pantalla para saber si contó.

**Varios operarios a la vez:** cada uno ve en el acto lo que registran los
demás. La tabla y los indicadores se actualizan sin recargar. Dos operarios
contando el mismo SKU suman bien; no se pisan.

**Un escaneo repetido no cuenta doble.** Si la pistola dispara dos veces o se
pierde la red y el envío se reintenta, se escribe el mismo registro, no uno
nuevo.

### 9.2.bis Dónde está hoy en Depot

Al validar un código, debajo de la ficha sale **En Depot hoy**: cada fila que el
WMS tiene de ese producto, con su posición, su cantidad, su lote, su serie, su
partida y su estado.

`getstock` devuelve **una fila por cada sitio** donde hay existencia, y una
misma posición puede traer varias filas del mismo código. No se agrupan: lo que
las distingue es justo lo que se mira para decidir dónde va lo que acaba de
llegar. Antes la app se quedaba con la primera fila y descartaba el resto.

**Tocar una posición la copia** al campo «Posición real asignada» y pone el
pallet en `DP`.

> **La app no opina sobre si cabe.** No ve la ubicación, no conoce su capacidad
> y no sabe el volumen de la mercadería. Quien está delante del pallet sí.
> Sugerirlo sería una opinión disfrazada de dato, y eso es peor que no decir
> nada.

### 9.2.ter El pallet `DP` y la posición real

Parte de la mercadería va directa a su ubicación sin armar pallet. Obligar a
inventarse uno ensucia el dato: queda un `A1` que no existe en el almacén.

Para eso está **`DP` — directo a posición**, con su botón al lado del campo de
pallet. El sitio donde quedó de verdad se anota en **Posición real asignada**.

Son dos datos distintos y por eso van en columnas distintas del informe:

| Columna | Qué dice |
|---|---|
| `PALLET` | Cómo se movió la mercadería |
| `POSICION REAL ASIGNADA` | Dónde está físicamente |

Para buscar algo después vale la segunda. La posición conserva sus guiones
(`A-01-03-2`): separan nave, calle, columna y nivel, y sin ellos no se puede
buscar en Depot.

### 9.2.quater Ningún SKU se queda sin dato

Hay **cinco** estados, no cuatro, y la diferencia entre dos de ellos es la que
más confunde si se mezclan:

| Estado | Qué significa |
|---|---|
| **Completo** | Cuadró con el packing list |
| **Sin buscar** | Nadie lo ha tocado todavía — es trabajo pendiente |
| **No apareció** | Se buscó, no estaba, y alguien lo declaró — se reclama |
| **Faltan unidades** | Apareció, pero menos de las declaradas |
| **Sobran unidades** | Apareció de más |

«Sin buscar» y «No apareció» son cosas distintas. Mezcladas, el operario no
sabe qué le queda por hacer y el supervisor no sabe qué reclamar.

Para declarar el segundo está el botón **No apareció**, al lado de Registrar.
Pide una nota —dónde se buscó, qué se vio— porque **un faltante sin motivo no
se le puede reclamar a nadie**. Queda como un conteo de cero en la bitácora,
con su firma, y se anula igual si el producto aparece después.

> **No se puede cerrar con referencias sin buscar.** El botón Finalizar lo
> impide, filtra la tabla por las que faltan y dice cuántas son. Dejar una en
> blanco significa «no sé», y en el informe eso es indistinguible de «no
> llegó»: quien reciba el archivo no puede saber cuál de las dos pasó.

### 9.2.quinquies Cuando la cantidad se reparte

De lo validado puede que solo unas unidades vayan a su posición definitiva y el
resto se quede en un pallet. Eso se registra en **dos conteos** del mismo SKU,
cada uno con su pallet y su posición.

En el informe van en una celda, no en filas nuevas:

```
DESGLOSE PALLET → POSICION
B04(5) DP→A-01-03-2(2)
```

Cinco unidades en el pallet B04, dos directas a la posición A-01-03-2.

> **El archivo nunca crece.** Entren 1, 22, 30, 100 o 300 filas, salen las
> mismas y en el mismo orden. Hay una prueba automática que lo comprueba con
> siete tamaños distintos, porque es la regla que más fácil se rompe sin darse
> cuenta.

### 9.2.sexies Consolidar varios packing lists

Dos embarques cortos el mismo día, o uno que llega partido: validarlos por
separado obliga a recorrer el almacén dos veces para la misma mercadería.

Desde el listado, **+ Lista** añade otro packing list a una recepción que ya
existe. Cada lista lleva su nombre (`RB48529`), y **el informe entrega una hoja
por lista, con sus propias filas**: si una trajo 22 y la otra 7, salen 22 y 7,
nunca 29 mezcladas. Quien recibe cada archivo espera el suyo.

El conteo sí es común —se cuenta una vez, contra la suma de lo declarado— y por
eso el operario no tiene que saber de qué lista salió cada pieza.

> **Cuando una referencia está en las dos listas**, la app avisa al cargar la
> segunda. Repartir después lo contado entre una lista y otra es una
> **convención, no un hecho**: el operario no dice de qué embarque salió cada
> unidad. La app llena primero las líneas de la primera lista y lo que sobre lo
> imputa a la última.
>
> Si de esa atribución depende una reclamación a un proveedor concreto,
> **valida esas listas por separado**. La consolidación ahorra recorridos, no
> sustituye a tener los datos bien separados cuando importan.

### 9.2.septies Exportar sin cerrar, y reabrir

Una validación de 300 líneas dura dos turnos. **Exportar ahora** descarga el
estado actual sin cerrar nada, para enseñar cómo va sin tener que elegir entre
informar y seguir trabajando. El archivo queda marcado como avance y la
exportación se registra en la auditoría igual que cualquier otra.

**Reabrir** devuelve a EN_VALIDACIÓN una recepción cerrada. Cerrar por error, o
descubrir al día siguiente que faltó un pallet, pasa; la alternativa —crear otra
recepción con el mismo packing list— parte el historial en dos y deja dos
informes del mismo embarque. No borra nada: los conteos siguen donde estaban, y
el cierre anterior y el motivo de la reapertura quedan en la auditoría.

Las dos son del supervisor. El operario entra y sale de las recepciones en curso
cuantas veces quiera —contar es su trabajo y no bloquea a nadie—, pero no cierra
ni reabre.

### 9.3 Código que no existe (paso 8)

Sale un modal con:

- **Códigos parecidos** en el packing list (mismo arranque), por si llegó con
  una variante.
- **Buscador** por código o por descripción dentro del packing list.
- **Registrar como adicional**, si de verdad llegó algo que no estaba.

### 9.4 Cerrar y el informe

**Finalizar** (solo supervisor) cierra la recepción, descarga el `.xlsx` y lo
envía por correo a quien indiques.

El archivo trae tres hojas:

| Hoja | Contenido |
|---|---|
| `VALIDADA` | El packing list con las columnas de validación añadidas |
| `ADICIONALES` | Lo que llegó sin estar en la lista |
| `BITACORA` | Cada conteo con su autor, su hora y sus fotos |
| `AUDITORIA` | Cada cierre y cada exportación: quién, cuándo y qué archivo salió |

La hoja `AUDITORIA` existe porque el agregado se puede volver a calcular, pero
lo que se entregó aquel día no. Sin ella, «el informe decía otra cosa» no se
puede resolver.

> **La regla de las filas se respeta.** Si el archivo que recibiste tiene 22
> filas, `VALIDADA` entrega 22 filas, en el mismo orden. No se añade ninguna.
> Por eso los adicionales van en su propia hoja.
>
> Cuando un mismo SKU viene en dos filas (distinta factura o embarque), el
> conteo se reparte: se completa la primera y el resto baja a la siguiente. El
> excedente, si lo hay, queda en la última fila de ese SKU. La suma por SKU
> siempre coincide con lo contado.

Después de cerrar, la recepción no admite más conteos. La pantalla queda en
solo lectura.

### 9.5 Corregir un conteo

**Bitácora** lista los últimos conteos. **Anular** pide el motivo y registra una
reversa: el conteo original **no se borra**, se compensa. Un operario solo puede
anular los suyos; un supervisor, cualquiera.

Es a propósito. Un almacén en el que se pueden borrar conteos no tiene
trazabilidad, y los KPI que salgan de ahí no valen para reclamar nada.

---

### Las fotos se reducen antes de subir

La cámara de un handheld entrega entre 3 y 8 MB por foto, y codificarla para
mandarla por el proxy la infla un tercio más. El proxy de Apps Script se
quedaba sin tiempo antes de terminar, y el operario veía *«el proxy tardó
demasiado»* justo al documentar un producto dañado.

La app ahora reduce cada foto a 1600 px de lado mayor antes de subirla: entre
200 y 400 KB, veinte veces menos, y el golpe o la caja mojada se ven igual. El
aviso muestra el antes y el después mientras sube.

No hay nada que configurar. Si alguna vez vuelve a aparecer el mensaje, ya es
el WiFi del almacén: acercarse a un punto con mejor señal. **El conteo no se
pierde** — lo que falló fue la foto.

---

### 9.6 Indicadores y trazabilidad

**KPIs**, en el menú de inicio, para supervisores y administradores.

Todo sale del libro mayor y del agregado por SKU. No hay una segunda base con
cifras precalculadas: un número que no se puede rastrear hasta el conteo que lo
originó no sirve para discutir con nadie. Cada cifra de la pantalla se puede
abrir hasta el SKU, la recepción, la fecha y el operario.

Cinco vistas, con filtro por fechas, cliente y estado:

| Vista | Para qué |
|---|---|
| **Recepciones** | Una fila por recepción, con exactitud y productividad |
| **Referencias** | Qué productos fallan más, ordenados por **cuántas veces**, no por cuánto |
| **Operarios** | Conteos, unidades, PNC y anulaciones de cada uno |
| **Tendencia** | Unidades y exactitud por día |
| **Trazabilidad** | Todo lo que le ha pasado a una referencia en el periodo |

Cualquiera se exporta a CSV con el botón, y se abre en Excel con las tildes
bien.

#### Las dos cifras que hay que entender

**Exactitud** es el porcentaje de referencias que cuadraron a la primera. Es lo
que se reclama al proveedor.

**Verificado** es qué parte de lo declarado ya se comprobó físicamente. El tope
se aplica **por referencia**, no al total, y esto importa: comparando totales,
contar de más en un producto tapaba lo que faltaba en otro. Con 221 unidades
declaradas, 385 contadas y 20 referencias faltantes, la barra marcaba 100%
cuando lo que quedaba por buscar era justo lo que había que ver.

#### Por qué «Referencias» ordena por veces y no por unidades

Una referencia que falló 40 unidades una vez es un incidente. Una que falla 2
unidades en cinco recepciones seguidas es un problema del proveedor o del
proceso. La segunda es la que hay que llevar a la reunión, y es la que sale
arriba.

---

### 9.0 La pantalla de inicio

Lo primero que ve cualquiera al entrar son las **recepciones de los últimos 15
días**, con su estado y un buscador por código o cliente. Es a lo que viene.

Quince días porque lo de hace tres semanas ya está cerrado y entregado, y una
lista larga en un handheld no se lee.

Debajo, plegado, **qué puede hacer** con su rol. Y la comprobación de la
instalación solo la ve un ADMIN.

---

## 10. Instalar en los handheld

Solo el enlace. No hay instalador.

### Android (Zebra, Honeywell o teléfono)

1. Chrome → `https://iv-itsanet.web.app`
2. Entrar con la cuenta corporativa
3. Menú **⋮** → **Añadir a pantalla de inicio**

### iPhone / iPad

1. **Safari** — en Chrome no aparece la opción
2. **Compartir** → **Añadir a pantalla de inicio**

### La pistola

Las pistolas USB y Bluetooth emulan un teclado. No hay nada que configurar, solo
verificar en el lector:

- Sufijo en **Enter (CR)**, no en Tab
- Sin modo "teclado numérico" si los códigos llevan letras

### Sin conexión

Firestore guarda los conteos en el dispositivo y los envía al reconectar. El
operario ve un aviso y **sigue trabajando**.

> Si cierra el navegador con conteos sin enviar y no vuelve a abrirlo en ese
> mismo dispositivo, esos conteos se quedan ahí. Antes de cerrar una recepción,
> la app comprueba que no quede nada pendiente.

---

## 11. Errores frecuentes

### Despliegue

| Error | Causa | Solución |
|---|---|---|
| `Cloud Functions requires Blaze` | Desplegaste `functions` | En Spark no se despliegan; usa Apps Script |
| `This API method requires billing`, precedido de `Creating the new Firestore database` | La base no existe y el CLI intentó crearla | Créala desde la consola (paso 2.1) y repite el despliegue. **No hace falta plan de pago** |
| Entra, pero `permission-denied` al leer o escribir | El id de la base no coincide | Compara `firebase.json`, `config.js` y la consola (paso 2.1, punto 4) |
| `option '--only <targets>' argument missing` | Faltó indicar qué desplegar | `firebase deploy --only hosting` |
| `HTTP Error: 403` | Sesión vencida | `firebase logout && firebase login` |
| `Failed to get Firebase project` | Mal vinculado | `firebase use --add` |
| `The query requires an index` | Índices construyéndose | Espera 5 min; el error trae un enlace que lo crea |

### Login

| Síntoma | Causa | Solución |
|---|---|---|
| `auth/unauthorized-domain` | Dominio sin autorizar | Paso 3, "Autorizar el dominio" |
| Entra pero no ve nada | Falta su documento en `usuarios` | Que recargue; si sigue, revisa las reglas |
| No ve el menú de administración | Su rol es `OPERADOR` | Cámbialo en Firestore y recarga |
| `auth/popup-blocked` | El navegador bloqueó la ventana | Permitir ventanas emergentes del sitio |

### Depot

| Síntoma | Causa | Solución |
|---|---|---|
| Todos los SKU salen inexistentes | Catálogo sin cargar | Ejecuta el precalentado desde el panel |
| `Sesión no válida` desde la app | `FIREBASE_API_KEY` mal | Paso 5.3; tiene que ser la del paso 2.2 |
| `Solo cuentas de itsanet.com` | Entró con cuenta personal | Que use la corporativa |
| Funciona en el editor pero no desde la app | Publicado como "Solo yo" | Paso 5.4, punto 5 |
| Cambié el código y sigue igual | Apps Script sirve la versión publicada | **Implementar → Administrar → editar → Nueva versión** |

> El último es el que más tiempo hace perder. Editar el código **no** actualiza
> la app publicada: hay que crear una versión nueva.

### Ver qué pasó

Apps Script: **Ejecuciones** en el menú lateral. Muestra cada llamada, su
duración y el error si lo hubo.

Hosting, volver atrás:

```bash
firebase hosting:rollback
```

---

## 12. Vigilar las cuotas

En Spark, pasarse de una cuota **apaga ese producto hasta el mes siguiente**. No
se cobra nada, pero deja de funcionar. Conviene saber dónde estás.

| Recurso | Límite diario | Lo que consume una recepción de 150 líneas |
|---|---|---|
| Lecturas de Firestore | 50.000 | ~1.500 |
| Escrituras de Firestore | 20.000 | ~800 |
| Almacenamiento | 1 GiB | Unos pocos MB al año |
| `UrlFetchApp` (Apps Script) | 20.000 | ~5 |
| `MailApp` (Apps Script) | 100 en cuenta de Google, 1.500 en Workspace | 1 por cierre |

Caben del orden de **20 recepciones diarias** con holgura. El límite que se toca
primero son las escrituras de Firestore.

**Dónde mirar:** consola de Firebase → **Uso y facturación**.

### Si te quedas corto

1. Baja la frecuencia del precalentado: el catálogo cambia poco.
2. Archiva recepciones cerradas de más de un año.
3. Si aun así no alcanza, **ahí sí** conviene Blaze: con este volumen seguiría
   costando cero o casi, y recuperas Cloud Functions y Storage.

---

## Resumen

```bash
# Preparar
npm install -g firebase-tools
firebase login
git clone -b pr_bep/serene-thompson-10qlxd https://github.com/brantos102/IV_ITSANET.git
cd IV_ITSANET/firebase
firebase use --add
node ../pruebas.js

# Desplegar (en Spark: NUNCA functions ni storage)
firebase deploy --only firestore:rules,firestore:indexes
firebase deploy --only hosting

# Apps Script: pegar Proxy.gs, poner las propiedades, publicar,
# y guardar la URL en config/proxy de Firestore.
```

---

## Validar antes de entregar

El protocolo de pruebas está en **[ENTREGA.md](ENTREGA.md)**: lista de
comprobación con el resultado esperado de cada punto, desde los tres
interruptores de consola hasta una recepción completa con dos operarios a la
vez. Imprímela y márcala.

---

## Actualizar después de un cambio

Esto es lo que hay que correr cada vez que llega código nuevo:

```bash
cd IV_ITSANET
git pull origin pr_bep/serene-thompson-10qlxd
cd firebase
firebase deploy --only hosting,firestore:rules
```

Si el cambio toca el proxy, además: abrir el Apps Script, pegar de nuevo
`Proxy.gs` y `Clientes.gs`, y **publicar una versión nueva** (Implementar →
Gestionar implementaciones → ✏️ → Versión: *Nueva versión*). Editar el código no
cambia lo que sirve la URL; hace falta la versión nueva.

> **Si un handheld sigue viendo la pantalla vieja:** los `.html`, `.js` y `.css`
> se sirven con `no-cache`, así que basta recargar. Si se instaló como app,
> cerrarla del todo y volver a abrirla. El service worker se reemplaza solo en
> la siguiente carga.

---

## Qué está construido

**208 pruebas automáticas** en verde, con un solo comando:

```powershell
node pruebas.js        # desde la raíz del proyecto
node ..\pruebas.js     # desde la carpeta firebase
```

Las rutas se resuelven desde el propio archivo, así que da igual en qué carpeta
estés. Y no necesita `npm install`: ninguna prueba usa dependencias externas.

| Suite | Qué cubre |
|---|---|
| `apps-script/test/run-tests.js` | 25 — lógica de la app anterior |
| `apps-script/test/clientes.test.js` | 34 — credenciales y token por cliente |
| `apps-script/test/proxy.test.js` | 9 — contrato real de Depot |
| `firebase/test/app.test.mjs` | 29 — acceso, alias, imágenes, informe |
| `firebase/test/paginas.test.mjs` | 14 — sintaxis, imports y referencias de cada página |
| `firebase/functions/test/*` | 77 — motor de referencia |

Completo y conectado: acceso con Google corporativo, importación del packing
list, catálogo precalentado desde Depot, pantalla de escaneo con el flujo de 9
pasos, conteo concurrente con libro mayor, adicionales aparte, fotos a Drive,
cierre con `.xlsx` de tres hojas por correo, y el panel de credenciales por
cliente.

---

## Lo único que sigue abierto: el EAN

`/getstock` **no devuelve código de barras**. Lo comprobé campo por campo contra
lo que extrae tu Centro de Mando: trae `COD. PRODUCTO`, `DESCRIPCION`,
`UNIDAD`, `CANTIDAD`, `NAVE/CALLE/COLUMNA/NIVEL`, lotes, series y familia. EAN,
no.

Entonces «registrar el código EAN para la subida al sistema» no se puede
resolver leyendo Depot. Hay dos caminos:

1. **Que exista otro endpoint** en el WMS que relacione EAN con SKU. Si lo hay,
   dime la ruta y lo conecto; es media hora.
2. **Mantener la equivalencia aquí.** Ya está construido: la primera vez que un
   operario escanea un EAN que Depot no resuelve, elige el SKU en el buscador y
   queda guardado. El segundo escaneo de ese EAN ya entra directo, y en cualquier
   recepción. Se arma solo con el uso.

Mientras no me confirmes el endpoint, la app funciona por el camino 2.

---

## Dos cosas que conviene resolver con el área correspondiente

**La cuenta.** `bespinoza@itsanet.com` es una cuenta de Google con correo
corporativo, no una cuenta gestionada por Google Workspace. El Apps Script, la
carpeta de evidencias en Drive y las credenciales de Depot cuelgan de ella: si
esa cuenta se pierde, la empresa no puede recuperarlos. Comparte el proyecto de
Apps Script y la carpeta de Drive con un segundo responsable **hoy**. Tiene
además un efecto práctico: la cuota de correo es de 100 al día en vez de 1.500.

**Las 22 filas.** La regla que fijaste contradice el packing list de VW que
entregaron: ese archivo trae el sobrante como fila 73 con Cantidad 0. La app
sigue tu regla —22 filas entran, 22 filas salen, adicionales aparte—, pero
conviene avisar al ejecutivo de cuenta antes de la primera entrega, para que no
lo reciba como un formato distinto al que esperaba.
