# Comprobar las mejoras en desarrollo

Esta entrega corresponde a `desarrollo-local`. El servidor operativo continúa
en `pr_bep/serene-thompson-10qlxd`. La base y los archivos de Docker son propios
del desarrollo. No copiar las tablas de configuración ni las colas de producción.

## Actualizar la PC que ya funciona

Abrir **PowerShell de Windows**, sin conexión SSH, en la carpeta existente:

```powershell
Set-Location "$HOME\source\IV_ITSANET-desarrollo"
git status --short
git branch --show-current
git pull --ff-only origin desarrollo-local
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1
```

La rama debe ser `desarrollo-local`. Si hay modificaciones propias, conservarlas
antes de actualizar; no ejecutar `reset --hard`. Abrir `http://localhost:3003/app/`
y recargar con Ctrl+F5. El script conserva los volúmenes, las contraseñas y los
usuarios existentes. Docker Desktop debe indicar **Engine running**. El script
también encuentra Docker en su ubicación habitual si falta en PATH.

Para revisar la presentación móvil sin conectar un teléfono, abrir Chrome en
esa dirección, pulsar **F12 → Ctrl+Shift+M** y escoger un dispositivo de 390 px
de ancho. Recorrer ingreso y conteo. Esta vista comprueba el diseño; la cámara
del handheld se verifica después en el dispositivo real por HTTPS.

## Recorrido de recepción

1. SUPERVISOR/ADMIN crea la recepción e ingresa cliente, descripción y bultos.
   **Ingreso** permite completar marca, embarque, supervisor responsable y
   protocolo fotográfico. Se puede volver mediante **Bultos / evidencias**.
2. Cada bulto físico recibe un número independiente. Se permiten códigos de
   caja madre repetidos. **Editar código / listas** relaciona una unidad con
   varios packing lists. **＋ Caja madre** registra una caja interior vinculada
   a su bulto. Es preferible identificar primero la unidad física y después
   seleccionar esa unidad al cargar las fotos del producto.
3. **Registrar evidencias** permite cámara para fotos y galería con selección
   múltiple. Esta cámara de evidencia es independiente del escáner de códigos
   en video en vivo. Elegir clasificación, tipo, bulto/caja y lista vinculada.
   No existe máximo de fotos por producto; cada archivo admite hasta 12 MB antes
   de la compresión del navegador. Las cargas son secuenciales, con progreso y
   reintento de los archivos pendientes.
4. Las recomendaciones reglamentarias son 3 exteriores por bulto, objetivo 6,
   1 packing inicial por recepción y 2 de cada bulto abierto con lista visible.
   En protocolo general se recomiendan 6 panorámicas. **No bloquean el avance**.
   ADMIN puede ajustar los valores y, si posteriormente lo decide, activar la
   exigencia. No hay máximo de imágenes.
5. Continuar a packing lists. Se conserva la importación y consolidación
   existentes, accesibles a supervisión. Si el archivo varía, desplegar
   **Ajustar hoja y columnas**: hoja, fila real del encabezado y letras de
   columnas. Vista previa antes de guardar. ADMIN puede guardar el modelo por
   cliente; se reaplica solo cuando los encabezados coinciden. Cada packing
   mantiene sus propias columnas para el informe final. Cantidades negativas
   o no numéricas se rechazan; cero es válido. Códigos con ceros iniciales se
   conservan; los números demasiado largos deben venir como texto en Excel.

## Conteo y novedades

La ficha muestra accesos a **Código**, **Historial** y **Evidencias**. Tras un
faltante, sobrante o PNC aparece además una acción opcional para documentarlo.
Se pueden asociar fotos reglamentarias de caja cerrada, etiqueta de caja madre,
caja abierta y detalle, o usar registro general. La galería del SKU incorpora
las evidencias de su bulto/caja, lista vinculada y packing inicial, cuando esas
relaciones existen. No incorpora las fotos de otro SKU solo por compartir caja.

Los productos validados más recientemente aparecen primero. Bitácora e historial
muestran fecha y hora de Ecuador. Las fotos y cambios de ingreso generan eventos
de auditoría y no incrementan cantidades.

El escáner extrae SKU de QR con claves reconocidas, URL, GS1 o contenido que
coincida con un producto existente. Normaliza separadores. No convierte en
equivalentes dos números de pieza con dígitos distintos: `2GJ-823-302-A` y
`2GJ823308A` requieren confirmación. Prefijos P/1 y ceros de relleno se sugieren,
sin eliminar ceros que ya pertenezcan a un SKU existente. Se conserva la lectura
original y el motivo de interpretación en el registro. Un QR arbitrario de un
proveedor puede requerir ajustar su formato; no se interpreta como certeza.

ADMIN configura **Catálogo programado**: por defecto 08:00, 10:00 y 15:00,
zona `America/Guayaquil`. No hay trigger SQL que llame a una API. El worker hace
las consultas fuera del conteo y conserva la última consulta correcta si falla
Depot. Al arrancar tarde ejecuta el último turno pendiente del día, sin lanzar
todos los atrasados. También se mantiene la sincronización manual. Las posiciones
y existencias se separan por cliente; si no hay consulta confirmada se muestra
que no hay dato, sin inventar existencia cero.

## Conectar Drive desde ADMIN

Se requiere una autorización inicial de Google; un login en la app no concede
permiso para escribir en Drive ni enviar desde Gmail. Seguir los pasos de
[Google y formatos](GOOGLE_Y_FORMATOS.md), usando cuentas y carpetas de prueba
en este entorno. No escribir secretos en el código o en el chat.

1. En un **puente de pruebas**, copiar la versión actual de `Servidor.gs`, junto
   con `Proxy.gs` y `Clientes.gs`. Publicar una nueva versión del despliegue web
   que se ejecuta como el supervisor. El puente debe informar `versionPuente: 2`.
   Guardar en propiedades `SERVIDOR_HMAC` y `CARPETA_EVIDENCIAS`. La clave
   aleatoria ya generada sirve como HMAC si se copia exactamente en ambos lados;
   no es una clave de API de Drive. No modificar el puente operativo compartido
   durante estas pruebas.
2. ADMIN → **Drive y envío de correo**: registrar correo del supervisor,
   `/exec` y HMAC. **Verificar remitente y Drive**. Cada supervisor que cierre
   reportes necesita un puente autorizado que se ejecute como su propia cuenta.
3. ADMIN → **Operación → Repositorios de Drive**: añadir uno o varios, con
   nombre, enlace/ID, cliente y marca opcionales. **Guardar configuración** y
   **Verificar acceso** con el supervisor correspondiente. No crea ni envía
   correo en esa prueba. La coincidencia de cliente y marca más específica tiene
   prioridad; con igual especificidad se usa el primero de la lista. Sin regla
   aplicable se utiliza la raíz del puente.
4. Compartir la raíz con los supervisores como editores y con el ejecutivo según
   sus permisos. Subir una evidencia de prueba y comprobar la carpeta mediante
   **Abrir carpeta en Drive**. Las credenciales y el diagnóstico solo son ADMIN.

La carpeta previamente indicada, `1spPbedhG4y5FfQso1yJTV_aixPv0KWAr`, es una
opción para la configuración operativa futura. No se activa automáticamente
como destino de este desarrollo.

La jerarquía queda así:

```text
Raíz / CLIENTE / MARCA (opcional) / RECEPCIÓN /
  RECEPCION / BULTO_n_código / LISTA_origen / tipo de evidencia /
  FALTANTE / BULTO_n_código / CAJA_MADRE_n_código / LISTA_origen / SKU / tipo /
  SOBRANTE / ...
  PNC / ...
  GENERAL / ...
  INFORMES /
  entregas / acuses del envío
```

Los segmentos de bulto, caja y lista se incorporan cuando están registrados.
FALTANTE, SOBRANTE y PNC se crean por recepción. Las fotos se copian durante
la operación. MySQL guarda metadatos, relaciones y enlaces, **sin binarios**.
Se mantiene una copia temporal durable en disco mientras Drive no confirme;
se elimina del disco tras confirmación. Eso evita perder fotos por una caída
de Google. En desarrollo sin puente quedan pendientes y consumen disco local.

Al finalizar, el manifiesto numera las fotos por SKU/carpeta como
`SKU_01_de_03.jpg`; la galería muestra `1/3`. Si una misma imagen tiene varios
vínculos se crean accesos directos en las otras carpetas, sin duplicar el binario.
**Excel de trazabilidad** descarga desde SQL los vínculos de SKU, unidad, lista,
fecha, usuario y Drive con logo de la empresa. Se adjunta también al cierre,
además del packing final conservado con sus encabezados.

SUPERVISOR/ADMIN puede retirar evidencia desde la galería mientras la recepción
esté abierta. Se advierte que afecta todos sus vínculos; se conserva auditoría
y se envía a la papelera de Drive. Una imagen retirada no reaparece al reintentar
el mismo archivo. Evitar borrar imágenes directamente en Drive: la aplicación
no sincroniza cambios manuales externos. Los permisos de Drive siguen aplicando
al abrir o previsualizar las fotos privadas.

El correo final sale de la cuenta real del supervisor autenticado que cierra,
comprobada contra el ejecutor del puente. Solo se solicitan destinatarios y se
recuerdan los últimos del cliente. No se suplanta el remitente con Reply-To.
El responsable de ingreso guía la copia anticipada; si cierra otro supervisor,
ambas cuentas deben tener acceso al repositorio. Sheets no es registro operativo.

## Acceso con Google

ADMIN configura cliente OAuth web, secreto y callback exacto. En este desarrollo:
`http://localhost:3003/api/auth/google/callback`. Se obtienen en Google Cloud →
Google Auth Platform → Clients → Web application, con audiencia/usuarios de prueba
autorizados. Véase la [guía](GOOGLE_Y_FORMATOS.md). El botón se muestra solo si
la conexión está habilitada. No se solicita contraseña de Gmail; los usuarios
nuevos siguen necesitando aprobación y rol local.

## Etiquetas y puente de impresión

Se conserva el diseño de 100 × 50 mm, Zebra ZD421 203 dpi, con código, descripción,
serie, categoría, QTY, estado y responsable. **Cada etiqueta es de una unidad**.
El operario elige copias; si contó 7, puede pulsar **Usar 7 copias de 1 unidad**.
Imprimir es opcional y no bloquea el conteo o el cierre.

En PC, imprimir desde el navegador con formato Windows **10 X 5**, 100 %,
márgenes cero y sin encabezados/pies, o descargar ZPL.

Para móvil, ADMIN → **Operación → Estaciones de impresión**:

1. Registrar ID y nombre visible, nombre/IP/dominio de la PC puente, IP/dominio
   de la Zebra y puerto ZPL (habitualmente 9100). Se pueden añadir varias estaciones
   o desactivarlas sin editar código. La PC debe poder alcanzar la impresora.
2. Guardar y **Generar archivo del agente**. Esta acción rota su token. Para
   el agente en el mismo Docker local, indicar servidor `http://app:3002`.
   Guardar el JSON descargado como `.local\puente.json` en la copia de desarrollo.
   Este archivo es privado, está excluido de Git y no debe compartirse.
3. En esa PC con Docker encendido:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\local.ps1 -Accion impresora
   ```

   Como alternativa, una PC con Python y `httpx` puede ejecutar:

   ```powershell
   python scripts\agente_impresion.py --config .local\puente.json --registro .local\registro-impresion
   ```

   En otra PC, el JSON debe indicar una URL del servidor alcanzable desde esa
   máquina. No usar `localhost` para referirse a un servidor en otra computadora.
   Esta copia publica solo loopback; el acceso desde otros equipos necesita
   configurar un acceso HTTPS de pruebas con su responsable de red.
4. En móvil seleccionar la estación en la etiqueta y **Enviar al puente**.
   El agente consulta la cola y envía ZPL a la impresora por TCP. No requiere
   instalar controladores Zebra en el teléfono ni abrir un puerto HTTP en la PC.
   Los controladores existentes siguen sirviendo a la impresión del navegador.

**ENVIADA** confirma el envío por socket, no que el papel salió físicamente.
Si una operación queda **REVISION**, comprobar la impresora y el papel antes
de solicitar otra impresión: no se reenvía automáticamente un resultado incierto.
El registro durable evita repetir el socket tras perder una respuesta del servidor.
No borrar ese registro para forzar una reimpresión.

La app en el teléfono y el escáner en vivo requieren un origen HTTPS confiable
para usar cámara; Google OAuth también requiere un dominio autorizado en móvil.
El localhost del PC sirve para las comprobaciones de escritorio. No cambiar
esta condición desactivando la seguridad del navegador.

## Antes de llevarlo a producción

Probar con el supervisor: ingreso, consolidación, evidencia por bulto/SKU,
escaneo real de los proveedores, conteos simultáneos, posiciones por cliente,
exportación y cierre. Completar una copia real a un Drive de pruebas y un correo
de prueba desde el supervisor, y una etiqueta física en la Zebra. Estas tres
conexiones necesitan las cuentas y equipos reales; las pruebas automatizadas
usan servicios simulados y no prueban permisos externos ni calidad de impresión.

La creación de tablas es aditiva. La promoción exige respaldo, comparación con
la versión operativa y una ventana acordada, con operadores fuera del proceso.
Esta entrega no ejecuta despliegue, migración de datos ni reinicio en producción.
