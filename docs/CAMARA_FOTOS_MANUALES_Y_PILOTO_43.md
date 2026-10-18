# Entrega 43: cámara, fotografías, manuales y piloto desde una PC

Fecha: 18 de octubre de 2026. Interfaz `20261018-43`.
Etiqueta: `itsanet-20261018-camara-fotos-manuales-43`.

## Acceso empresarial que ya funciona

**https://apps.flexnetuio.com:8443/app/**

El usuario comprobó `/health` desde Windows con VPN y confirmó que funcionan
el escaneo en vivo y la toma de fotografías. Apache ya sirve esta app en 8443,
con `/etc/apache2/sites-enabled/itsanet-app-8443.conf`. El sitio de 443 usa
`itsanet-data-sync-ssl.conf`. Esta entrega conserva ambos sitios; no requiere
comprar otro certificado ni instalar otro proxy.

En cada móvil se necesita acceso a la red empresarial, certificado confiable y
permiso de Cámara. Una prueba exitosa en Windows no instala la CA corporativa
en los teléfonos. Para supervisores desde casa sin VPN, usar el piloto de PC
descrito abajo.

Una comprobación de lectura, en **PowerShell de Windows**:

```powershell
curl.exe --fail --silent --show-error --connect-timeout 5 --max-time 15 https://apps.flexnetuio.com:8443/health
```

## Cambios operativos

- Cámara: detector nativo cada 90 ms; respaldo ZXing cada 110 ms, alternando
  zona central y encuadre completo. Evita reprocesar una imagen congelada y
  procesar fotogramas en paralelo. Solicita cámara trasera, resolución ideal
  1920 × 1080 y enfoque continuo cuando el dispositivo lo permite. Conserva
  los caracteres, la pausa de repetición y la revisión del SKU antes de contar.
- Visor: muestra todo el encuadre y una guía central; controles de ingreso
  adaptados al ancho móvil. Las restricciones de cámara son preferencias,
  salvo el límite de 30 fps: un equipo de menor resolución puede funcionar.
- Ingreso: antes del primer bulto se ofrecen **panorámicas**, **fotos de bultos**
  y **cargar packing list**. Las panorámicas pertenecen a la recepción completa,
  sin crear ni asignar el primer bulto. Saltar al packing conserva el protocolo
  y sus reglas de cumplimiento; no equivale a declarar SIN_FOTOS.
- Fotos: se intenta guardar una copia comprimida en IndexedDB antes del POST.
  Si falla el envío, puede recuperarse explícitamente desde la misma cuenta,
  recepción, navegador y dirección. Al recibir confirmación del servidor se
  retira la copia temporal. Una sesión cambiada durante el envío se rechaza.
- Persistencia del servidor: contenido privado sincronizado con disco antes
  de confirmar metadatos; SHA-256 evita duplicar el archivo al reintentar. El
  reintento puede reparar una copia local ausente o dañada todavía sin respaldo
  confirmado en Drive. La copia a Drive mantiene su propia confirmación.
- Compresión: panorámicas hasta 2048 px / calidad 0,82; fotos con texto de
  packing o etiquetas hasta 2400 px / 0,85; otras evidencias conservan 1600 px /
  0,72. No amplía imágenes menores. Conservar originales hasta comprobar las
  imágenes guardadas y su legibilidad.

Seleccionar una foto todavía no la guarda. Cerrar con selección pendiente
ofrece guardarla y conserva el diálogo si falla. La recuperación local depende
del espacio del navegador: no sustituye los originales ni el respaldo del
servidor, no cruza dispositivos/orígenes y desaparece al borrar los datos del
sitio. No se promete ausencia absoluta de pérdidas físicas.

## Manuales descargables y código

Descarga el ZIP, extráelo y abre los HTML con Chrome, Edge o Firefox. Incluyen
estilos, imágenes y lógica de las prácticas; pueden utilizarse sin conexión.

- [Descargar los tres manuales en ZIP](https://github.com/brantos102/IV_ITSANET/raw/refs/tags/itsanet-20261018-camara-fotos-manuales-43/docs/descargas/ITSANET-manuales-v43.zip)
- [HTML del operario](../firebase/public/manuales/operario.html)
- [HTML del supervisor](../firebase/public/manuales/supervisor.html)
- [Informe técnico para TI](../firebase/public/manuales/tecnico.html)
- [Contenido editable](manuales/contenido.json), [estilos](manuales/manual.css) y
  [interacciones](manuales/manual.js).

Cada HTML permite descargar su código completo e imprimir todos los temas
en PDF. Contienen búsqueda, navegación por tareas, progreso personal,
ejercicios de conteo y novedades, correo de ejemplo, decisiones de cierre y
evaluación. El informe TI añade arquitectura por entorno, controles reales,
límites transaccionales, evidencias, responsabilidades y una revisión
exportable; esa revisión local no sustituye la aprobación formal de TI.

Para reconstruir los HTML y el ZIP reproducible desde su código:

```bash
python3 scripts/generar_manuales.py
```

Los tres HTML también se sirven en `/app/manuales/`. El diagnóstico de cámara
está en `/app/diagnostico-camara.html`: requiere pulsar un botón, abre/apaga el
video y permite descargar información de soporte; no registra fotografías ni
conteos.

## Instalar en producción 3002

Ejecutar en la **terminal Linux del servidor empresarial**, desde la sesión
`enicolalde@apps`, en una pausa comunicada a los usuarios. Este actualizador
realiza respaldo verificado de base y archivos, conserva el SQL local permitido,
actualiza sin forzar el historial, comprueba servicio y página y recupera el
código anterior si falla el arranque. Un fallo de respaldo detiene el pase.

Una sola línea completa:

```bash
cd ~/bryan/IV_ITSANET && git fetch origin tag itsanet-20261018-camara-fotos-manuales-43 && VERSION_ITSANET=$(git rev-parse 'itsanet-20261018-camara-fotos-manuales-43^{commit}') && git show "${VERSION_ITSANET}:scripts/actualizar_produccion.sh" > /tmp/actualizar-itsanet-43.sh && bash /tmp/actualizar-itsanet-43.sh "$PWD" "$VERSION_ITSANET"
```

Después abre el acceso HTTPS 8443 y recarga la pantalla. No iniciar el pase con
conteos en curso ni selecciones de fotos sin guardar. Si hay cambios locales
adicionales el actualizador se detiene para revisión; no usar `reset --hard` ni
`clean` para continuar. `/health` informa salud, no identifica por sí solo la
versión de interfaz.

## Pruebas desde casa sin facturación: PC Windows

La versión empresarial actual requiere FastAPI y MySQL. Publicar solo HTML en
Firebase Hosting no instala ese backend. **Se conserva
https://iv-itsanet.web.app/**; esta entrega no despliega Firebase, Cloud Run ni
Cloud SQL ni habilita facturación de Google.

La alternativa elegida por el usuario es su PC, Docker Desktop y un enlace
HTTPS temporal gratuito de Cloudflare. El supervisor externo necesita solamente
el enlace y una cuenta de prueba: no necesita VPN ni acceso SSH al servidor.

Requisitos de la PC: Git, Docker Desktop iniciado con contenedores Linux,
espacio para otra base MySQL, PowerShell con permiso corporativo para ejecutar
el script y salida de Internet a Cloudflare (HTTPS y TCP 7844). Mantener la PC y
Docker encendidos durante la prueba. El enlace temporal puede cambiar y no
tiene un SLA.

Abre **PowerShell en la PC**, en la carpeta de tu clon de IV_ITSANET. No ejecutar
este `.ps1` dentro de la conexión SSH al servidor.

Una sola línea para actualizar sin forzar cambios y arrancar el piloto:

```powershell
git pull --ff-only origin desarrollo-local; if ($LASTEXITCODE -eq 0) { .\scripts\publicar_pruebas.ps1 }
```

La primera ejecución construye la imagen y puede tardar varios minutos. Solo
anuncia `PRUEBAS HTTPS: https://...trycloudflare.com/app/` después de comprobar la
marca de pruebas desde el enlace público. Si no lo confirma, muestra un error
y conserva la instancia local para revisar la conexión.

Características del aislamiento:

- Proyecto Docker `iv-itsanet-pruebas-publicas-pc`, MySQL, archivos y claves
  propios. Las claves iniciales se generan una vez y se reutilizan.
- Usa 3003 si está libre; si hay otro servidor en 3003, lo conserva y elige
  3005. El puerto se guarda para siguientes arranques. Un conflicto posterior
  detiene la acción: puede elegirse otro puerto libre mediante `-Puerto`.
- El servicio HTTP de pruebas se enlaza solo a loopback; el túnel se conecta al
  contenedor de la app. La sesión pública utiliza cookie Secure / HttpOnly.
- Datos ficticios, clientes y usuarios de prueba. No copiar `/etc/iv-itsanet.env`,
  bases, credenciales Depot, conexiones Google ni carpetas de producción.

Las cuentas `admin`, `supervisor.prueba` y `operario.prueba` tienen sus claves
en `.local\pruebas-publicas\accesos-iniciales.txt`. Abre ese archivo localmente;
comparte una cuenta individual por canal privado. El administrador puede crear
cuentas adicionales. No publicar ese archivo ni sus claves en GitHub.

Para preparar sin abrir acceso externo:

```powershell
.\scripts\publicar_pruebas.ps1 -Accion preparar
```

Para revisar un problema:

```powershell
.\scripts\publicar_pruebas.ps1 -Accion logs
```

Para cerrar el enlace al terminar, conservando datos y contenedores locales:

```powershell
.\scripts\publicar_pruebas.ps1 -Accion detener
```

El enlace público todavía necesita ser generado desde la PC del usuario. La
nube de desarrollo no puede crearlo: su proxy bloquea `api.trycloudflare.com`.
No se ha eludido ese bloqueo ni se ha anunciado una URL de prueba como lista.

### Corrección del lanzador para Windows PowerShell (entrega 44)

Si la primera ejecución se detuvo con `NativeCommandError` al consultar
`iv-itsanet-pruebas-publicas-pc_mysql_pruebas: no such volume`, actualiza el
repositorio de la PC y vuelve a ejecutar la misma línea de arranque. La ausencia
del volumen es normal antes de preparar la base. La consulta anterior mediante
`docker volume inspect` escribía en stderr y Windows PowerShell 5.1 detenía el
script antes de comprobar el código de salida.

La corrección consulta `docker volume ls` con el nombre exacto y comprueba su
resultado: un listado vacío permite preparar; un fallo del daemon detiene la
acción; un volumen existente sin su archivo privado sigue bloqueando cualquier
regeneración de claves. También se corrige la consulta opcional de imagen y se
aclaran los errores de Docker Desktop / Compose. No se cambian aplicación,
recepciones ni configuración del servidor empresarial. No es necesario volver
a ejecutar el pase de producción por esta corrección del lanzador.

Etiqueta de la corrección: `itsanet-20261018-piloto-windows-44`. La interfaz de
la aplicación permanece en `20261018-43`.

Las 12 pruebas del lanzador simulan primera ejecución, errores nativos,
protección de datos existentes, repetición, consulta de imagen, fallo de
arranque y confirmación del enlace. Se ejecutan sin instalar Pester ni Docker:

```powershell
powershell.exe -NoProfile -File .\tests\probar_lanzador_windows.ps1
```

La corrección se verificó con PowerShell 7.4 en Linux, simulando la excepción
nativa observada en Windows PowerShell 5.1, y preparando la instancia aislada
con Docker real. La apertura del enlace y la aceptación en Windows se
completarán al ejecutar el lanzador en la PC.

### Lectura de claves en Windows PowerShell 5.1 (entrega 45)

La ejecución desde Windows detectó otra incompatibilidad: .NET Framework
seleccionaba una sobrecarga distinta de `String.Split` y trataba `2` como
`StringSplitOptions`. El lanzador ahora utiliza `IndexOf` y `Substring` para
separar el nombre del valor por el primer `=`. Ambos métodos tienen las firmas
necesarias en .NET Framework y .NET actual; se conservan los demás signos `=`
del valor. La prueba del lanzador también elimina esa llamada ambigua.

El archivo `.local\pruebas-publicas\entorno.env` ya generado se reutiliza.
No hay que borrarlo ni regenerar claves. Actualiza con la misma línea de
PowerShell y vuelve a iniciar. El cambio pertenece al lanzador de la PC y no
requiere repetir el pase del servidor empresarial.

Para comprobar la compatibilidad en Windows PowerShell antes de reanudar,
ejecuta esta única línea desde el repositorio de la PC. Las pruebas usan
carpetas temporales y Docker / HTTP simulados; solo si terminan correctamente
se ejecuta el lanzador real:

```powershell
git pull --ff-only origin desarrollo-local; if ($LASTEXITCODE -eq 0) { powershell.exe -NoProfile -File .\tests\probar_lanzador_windows.ps1; if ($LASTEXITCODE -eq 0) { .\scripts\publicar_pruebas.ps1 } }
```

Etiqueta: `itsanet-20261018-piloto-powershell-45`. Pasaron **14 pruebas del
lanzador** con PowerShell 7.4 / Linux, incluyendo reanudación con archivo
existente, conservación de claves con `=`, rechazo de archivos incompletos y
las protecciones anteriores. Se verificó además la preparación con Docker
real y que se mantienen las claves persistidas. Windows PowerShell 5.1 debe
confirmarse al reanudar en la PC del usuario; no se ejecuta desde esta nube.

## Comprobaciones de la entrega

Resultados de la versión final:

- **1.126 pruebas generales aprobadas**: 650 Python y 476 JavaScript.
- **51 pruebas MySQL 8.4 aprobadas** en una base desechable: fotos, cierre,
  idempotencia, documentos grandes y concurrencia.
- Chromium: CODE128 en video sintético (centro, borde, pequeño y ceros),
  consulta real sin conteo, apagado y galerías en tamaños táctiles
  360 × 800, 390 × 844 y 844 × 390.
- Fotografías: corte antes del POST, recarga / recuperación, respuesta perdida
  después del guardado y reintento sin duplicación; separación por cuenta.
- Los tres manuales: búsqueda, navegación, progreso, tema, ejercicios, descarga,
  contenido descargado ejecutado sin red, impresión completa y ancho móvil.
- PowerShell 7.4.19 / Linux y Docker: arranque aislado, repetición sin cambiar
  claves, restauración de variables, tres roles y cookies Secure / HttpOnly.
  Publicación de URL comprobada con respuestas simuladas; túnel real pendiente
  de iniciar desde la PC.

Se prueban bases desechables, archivos sintéticos y navegadores automatizados; no se envía
correo real ni se imprime físicamente en una Zebra desde esta nube. La
aceptación en dispositivos móviles reales y Windows/Docker Desktop pertenece
al piloto; emular un iPhone en Chromium no equivale a probar Safari de iOS.
