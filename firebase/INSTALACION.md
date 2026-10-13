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
9. [Instalar en los handheld](#9-instalar-en-los-handheld)
10. [Errores frecuentes](#10-errores-frecuentes)
11. [Vigilar las cuotas](#11-vigilar-las-cuotas)

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

```bash
cd functions && npm install && npm test && cd ..
```

Debe terminar con `0 falladas` en todos los bloques. Si no, **no despliegues**.

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

1. Entra a [script.google.com](https://script.google.com) **con la cuenta
   corporativa**
2. **Nuevo proyecto** → nómbralo `VAL VENTURA — Proxy Depot`
3. Borra el contenido de `Código.gs`
4. Pega entero el archivo `apps-script/proxy/Proxy.gs` del repositorio
5. Guarda (Ctrl+S)

### 5.2 Carpeta de Drive para las fotos

1. En Drive, crea una carpeta `VAL VENTURA — Evidencias`
2. Ábrela y copia el id de la URL:
   `https://drive.google.com/drive/folders/`**`1a2B3c4D5e6F7g8H`**

### 5.3 Las propiedades

En el editor de Apps Script: **Configuración del proyecto** (engranaje) →
**Propiedades de la secuencia de comandos** → **Agregar propiedad**.

| Propiedad | Valor | Obligatoria |
|---|---|---|
| `DEPOT_BASE_URL` | `http://dominio.com/apidepot` | Sí |
| `FIREBASE_API_KEY` | La `apiKey` del paso 2.2 | Sí |
| `DOMINIO_PERMITIDO` | `itsanet.com` | Sí |
| `CARPETA_EVIDENCIAS` | El id del paso 5.2 | Para fotos |
| `DEPOT_USUARIO` | Usuario del cliente | Si `/gettoken/` lo pide |
| `DEPOT_CLAVE` | Contraseña del cliente | Si `/gettoken/` lo pide |
| `DEPOT_CLIENTE` | `VENTURA` | Si el WMS separa por cliente |
| `DEPOT_TTL_HORAS` | `12` | No (12 por defecto) |

> **Aquí van las credenciales, y solo aquí.** No en el repositorio, no en el
> chat, no en el código. Las propiedades del script solo las ve quien es dueño
> del proyecto de Apps Script.

Para los clientes que vas a ir agregando (BELIA, VENTURA…), lo que cambia es
`DEPOT_USUARIO`, `DEPOT_CLAVE` y `DEPOT_CLIENTE`. Si cada cliente necesita
credenciales distintas **al mismo tiempo**, dímelo: cambia el diseño a un mapa
de credenciales por cliente, y prefiero construirlo bien desde el principio.

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

## 9. Instalar en los handheld

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

## 10. Errores frecuentes

### Despliegue

| Error | Causa | Solución |
|---|---|---|
| `Cloud Functions requires Blaze` | Desplegaste `functions` | En Spark no se despliegan; usa Apps Script |
| `This API method requires billing`, precedido de `Creating the new Firestore database` | La base no existe y el CLI intentó crearla | Créala desde la consola (paso 2.1) y repite el despliegue. **No hace falta plan de pago** |
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

## 11. Vigilar las cuotas

En Spark, pasarse de una cuota **apaga ese producto hasta el mes siguiente**. No
se cobra nada, pero deja de funcionar. Conviene saber dónde estás.

| Recurso | Límite diario | Lo que consume una recepción de 150 líneas |
|---|---|---|
| Lecturas de Firestore | 50.000 | ~1.500 |
| Escrituras de Firestore | 20.000 | ~800 |
| Almacenamiento | 1 GiB | Unos pocos MB al año |
| `UrlFetchApp` (Apps Script) | 20.000 | ~5 |
| `MailApp` (Apps Script) | 1.500 | 1 por cierre |

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
cd functions && npm install && npm test && cd ..

# Desplegar (en Spark: NUNCA functions ni storage)
firebase deploy --only firestore:rules,firestore:indexes
firebase deploy --only hosting

# Apps Script: pegar Proxy.gs, poner las propiedades, publicar,
# y guardar la URL en config/proxy de Firestore.
```

---

## Qué falta y qué necesito de ti

**Construido y probado** (95 pruebas): modelo de datos, reglas de seguridad,
registro de conteos, administración, adaptador de Depot contra tu contrato real,
y el proxy de Apps Script.

**Pendiente:** el cliente web (las pantallas que ve el operario), el importador
del packing list en el navegador y el cierre con informe.

**Lo que destraba el resto**, y sale de ejecutar `probarDepot()` en el paso 7:

1. La línea **"Campos que devuelve"** del registro. Con eso fijo el mapeo exacto
   en lugar de aceptar diez variantes de nombre.
2. Si `/gettoken/` pide usuario y contraseña, o responde sin más.
3. **Si la API responde desde fuera de la red de Itsanet.** Es lo primero que
   conviene comprobar.
