# Protocolo de validación y entrega

Lo que hay que comprobar antes de entregar, en orden. Cada punto tiene un
resultado esperado concreto: si no sale eso, no sigas al siguiente.

Lleva esta hoja impresa o en el móvil y marca cada casilla. Al final hay una
tabla para firmar.

---

## 0. Desplegar la versión que se va a probar

```bash
cd IV_ITSANET
git pull origin pr_bep/serene-thompson-10qlxd
cd firebase
firebase deploy --only hosting,firestore:rules
```

- [ ] Termina con **Deploy complete!**

---

## 1. Lo que falta configurar una sola vez

Tres interruptores en consolas de Google. Sin ellos nada de lo de abajo
funciona, y ninguno se puede activar desde el código.

### 1.1 Acceso con correo y contraseña

Consola de Firebase → **Authentication** → **Sign-in method** →
**Correo electrónico/contraseña** → activar el primer interruptor (el de
«Correo electrónico/contraseña»; el de «Vínculo de correo» se deja apagado).

- [ ] Aparece **Habilitado** en la lista de proveedores

### 1.2 Dominio autorizado

Misma sección → **Settings** → **Authorized domains**.

- [ ] Está `iv-itsanet.web.app`

Esto ya suele venir puesto. Importa porque la app ahora resuelve el acceso de
Google en su propio dominio, no en `iv-itsanet.firebaseapp.com`: es lo que
arregla el acceso en los handheld.

### 1.3 El despliegue del Apps Script, abierto

Apps Script → **Implementar** → **Gestionar implementaciones** → ✏️ →
**Quién tiene acceso: Cualquier usuario** → **Versión: Nueva versión** →
Implementar.

> Hay dos opciones parecidas y solo una sirve:
>
> | Opción | ¿Funciona? |
> |---|---|
> | **Cualquier usuario** | **Sí** |
> | Cualquier usuario con cuenta de Google | No |
> | Solo yo / solo el dominio | No |
>
> Las tres últimas redirigen al acceso de Google. Eso funciona si abres la URL
> en una pestaña (llevas la sesión puesta), pero no desde la app: una llamada
> entre dominios no manda cookies, y el navegador bloquea la redirección. Por
> eso la URL «funciona» al probarla a mano y aun así la app dice que no puede
> contactar al proxy.

- [ ] En `/admin.html` → **Probar conexión** sale
      **«El proxy responde»**

**Si la opción «Cualquier usuario» no aparece en la lista**, está desactivada
para todo el dominio por política de Workspace. Lo levanta el administrador de
Google Workspace de Itsanet en
**admin.google.com → Apps → Servicios adicionales de Google → Apps Script →
Configuración**, permitiendo publicar aplicaciones web accesibles para
cualquier usuario. No hay forma de rodearlo desde la app: avísame si te lo
niegan y cambiamos el enfoque.

---

## 2. Usuarios

### 2.1 Crear el primer operario

Entra como ADMIN → **Usuarios** → Dar de alta:

| Campo | Valor de prueba |
|---|---|
| Usuario | `prueba1` |
| Nombre | `Operario Prueba` |
| Contraseña | el botón **Sugerir contraseña** |
| Rol | OPERADOR |

- [ ] Sale el recuadro verde con el enlace, el usuario y la contraseña
- [ ] Aparece en la tabla como `prueba1@itsanet.com`, acceso **CLAVE**, activo
- [ ] **Tu sesión de administrador sigue abierta** (no te echó al crear)

### 2.2 Entrar como ese operario

En otro navegador, o en una ventana de incógnito:

- [ ] Escribiendo solo `prueba1` (sin el `@itsanet.com`) y la contraseña, entra
- [ ] Ve **Recepciones** y **Validar**, y **no** ve Usuarios ni Administración
- [ ] Con la contraseña mal, dice *«Usuario o contraseña incorrectos»*, no un
      código de error

### 2.3 Desactivar

Como ADMIN, desactiva `prueba1`. En la ventana del operario, recarga:

- [ ] Lo saca y dice que la cuenta está desactivada

Vuelve a activarlo para seguir probando.

---

## 3. El handheld

Esta es la prueba que decide si se puede entregar. Hazla en el **equipo real**,
no en un teléfono de escritorio.

- [ ] Abre `https://iv-itsanet.web.app` en el navegador del handheld
- [ ] Entra con `prueba1` y su contraseña — **sin pasar por el selector de
      cuentas de Google**
- [ ] **⋮ → Añadir a pantalla de inicio**; el icono queda en el escritorio
- [ ] Abriendo desde ese icono, entra igual
- [ ] El campo de escaneo tiene el cursor puesto al abrir `/validar.html`
- [ ] La pistola dispara el código y salta sola al siguiente paso (sufijo
      **Enter/CR**, no Tab)

> Si el acceso con Google seguía fallando en el handheld, con usuario y
> contraseña ya no aplica: ese camino no toca el selector de cuentas ni depende
> del almacenamiento compartido entre dominios que los navegadores móviles
> aíslan.

---

## 4. Depot

En `/admin.html`, con un cliente ya cargado:

- [ ] **Probar la conexión** → sale el token y la lista de campos reales
- [ ] La línea **«Campos que devuelve»** incluye `COD. PRODUCTO` y `CANTIDAD`

En `/recepciones.html`:

- [ ] **Descargar catálogo** termina y dice cuántos productos trajo

---

## 5. Una recepción de principio a fin

Usa el packing list real de VW, el de 22 filas.

### 5.1 Importar

- [ ] **Crear recepción** con código `PRUEBA-01`
- [ ] Subir el `.xlsx`: la vista previa muestra las primeras líneas con el ITEM
      y la cantidad correctos
- [ ] **Guardar packing list**: el total de SKU y de unidades coincide con el
      archivo

### 5.2 Contar

- [ ] Escanear un código del packing list: sale descripción, unidad y stock
- [ ] Registrar 1 unidad en el pallet `A1`
- [ ] Escanear **el mismo código**: aparece el botón **📦 A1** con la cantidad
      ya guardada *(la sugerencia de dónde está)*
- [ ] Escribir `5` en **Cantidad** y escanear una vez: registra 5 de golpe
- [ ] Registrar el mismo SKU en `A1.1`: salen las dos ubicaciones por separado
      *(el subpallet no se mezcla con el pallet)*
- [ ] Contar más de lo declarado: pide confirmar el **sobrante**
- [ ] Marcar **PNC** sin observación: no deja, la exige
- [ ] Marcar **PNC** con observación y una foto: registra, y la foto aparece en
      la carpeta de Drive

### 5.3 Dos operarios a la vez

Con la recepción abierta en el handheld y en un PC, con **usuarios distintos**:

- [ ] Lo que registra uno aparece en la pantalla del otro **sin recargar**
- [ ] Los dos cuentan el mismo SKU: el total es la suma, no el último valor
- [ ] En **Bitácora** cada conteo aparece con el nombre de quien lo hizo

### 5.4 Códigos que no existen

- [ ] Escanear algo que no está: sale el modal con el buscador
- [ ] Buscar por parte de la descripción encuentra la línea
- [ ] **Registrar como adicional**: avisa de que irá en una pestaña aparte

### 5.5 Anular

- [ ] **Bitácora → Anular** pide motivo
- [ ] El total del SKU baja, y el conteo original sigue en la lista, tachado

### 5.6 Sin conexión

- [ ] Apagar el WiFi del handheld y registrar 2 conteos: los acepta
- [ ] Volver a encender: aparecen en el PC del supervisor

### 5.7 Cerrar

- [ ] Un OPERADOR no puede cerrar (el botón lo rechaza)
- [ ] Un SUPERVISOR cierra: pide confirmación con el resumen
- [ ] Se descarga el `.xlsx`
- [ ] Llega el correo con el archivo adjunto
- [ ] **La hoja VALIDADA tiene exactamente las mismas filas que el archivo
      original** — con el packing list de VW, 22 filas si entraron 22
- [ ] Los adicionales están en la hoja **ADICIONALES**, no mezclados
- [ ] La hoja **BITACORA** tiene todos los conteos con autor y hora
- [ ] Después de cerrar, la pantalla de validación ya no deja escanear

---

## 6. Pruebas automáticas

Un solo comando. Si estás en `firebase`, usa la segunda línea; da igual, las
rutas se resuelven solas:

```powershell
node pruebas.js        # desde la raíz del proyecto
node ..\pruebas.js     # desde la carpeta firebase
```

No hace falta `npm install`: las pruebas no usan ninguna dependencia externa.

- [ ] Termina en **177 pruebas, todas en verde**

---

## 7. Antes de dar por entregado

- [ ] El Apps Script está **compartido con un segundo responsable**
      (Compartir → añadir correo → Editor)
- [ ] La carpeta de evidencias de Drive, también
- [ ] Hay **al menos dos ADMIN** en la pantalla de Usuarios
- [ ] El usuario `prueba1` está borrado o desactivado
- [ ] La recepción `PRUEBA-01` está cerrada
- [ ] El ejecutivo de cuenta sabe que el informe entrega las mismas filas que
      recibe, con los adicionales en pestaña aparte

---

## Lo que queda explícitamente fuera

**El código EAN.** `/getstock` no devuelve código de barras: lo verifiqué campo
por campo contra lo que extrae el Centro de Mando. Mientras no haya un endpoint
del WMS que relacione EAN con SKU, la equivalencia se construye con el uso: la
primera vez que un operario escanea un EAN desconocido lo asocia al SKU desde
el buscador, y a partir de ahí entra directo en cualquier recepción.

---

## Firmas

| | Nombre | Fecha | Firma |
|---|---|---|---|
| Probado por | | | |
| Recibido por | | | |
