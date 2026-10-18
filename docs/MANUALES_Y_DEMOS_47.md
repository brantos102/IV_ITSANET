# Guías y demos 47 · acceso al estado de fotos y Drive

Edición del 18/10/2026. Interfaz `20261018-47`.
Etiqueta: `itsanet-20261018-guias-drive-47`.

## Descargar y usar

[Descargar el ZIP completo desde GitHub](https://github.com/brantos102/IV_ITSANET/raw/refs/tags/itsanet-20261018-guias-drive-47/docs/descargas/ITSANET-manuales-v47.zip).
Extraer todo el contenido y abrir uno de estos archivos con un navegador:

| Archivo | Contenido |
| --- | --- |
| `operario.html` | Práctica de consulta y conteo, pallets, novedades, fotos y ayuda por tarea. |
| `supervisor.html` | Recepción, revisión de informe/correo, cierre, pendientes, fotos y organización. |
| `instalacion-supervisor.html` | Incorporación de cada persona, dispositivos, autorización Google, actualización del puente y lista individual exportable. |
| `tecnico.html` | Arquitectura, seguridad, servicios, evidencia y condiciones para revisión de TI. |

Cada HTML incluye su CSS, JavaScript y logo. Las prácticas y preguntas funcionan
sin Internet y no hacen llamadas a la API ni modifican recepciones. Los enlaces
a la aplicación, Google o GitHub sí requieren conexión. El progreso y las listas
se conservan en el navegador cuando permite almacenamiento local. No se solicitan
contraseñas o claves en las demos.

El banco contiene **67 preguntas únicas**: 36 aplicables al operario y 67 al
supervisor, incorporación y revisión TI. Se puede buscar sin distinguir tildes,
filtrar por tema, expandir respuestas y abrir ayuda relacionada desde las tareas.
La impresión incluye todas las preguntas aunque hubiera un filtro activo.

La práctica de fotografías reproduce 355 → 356 unidades con 1 PNC: una imagen
histórica FALTANTE y solo una nueva PNC. Un explorador ilustra los nombres y
carpetas por recepción, embarques y bulto. Las reglas reales siguen descritas en
[Fotos auditables 46](FOTOS_AUDITORIA_Y_CARPETAS_46.md).

## Incorporar a cada supervisor

1. ADMIN confirma su ficha, correo, rol y aprobación en el entorno correcto.
2. La persona abre el HTTPS empresarial completo `https://apps.flexnetuio.com:8443/app/`
   con conectividad empresarial/VPN, o el enlace vigente del piloto con cuenta de pruebas.
3. Usa navegador actualizado, configura perfil y contraseña inicial cuando corresponda,
   y verifica cámara/fotos en su dispositivo real. Puede crear un acceso directo.
4. Si enviará automáticamente, ADMIN habilita el envío personal. El propietario
   autoriza su propio Apps Script con `Proxy.gs`, `Clientes.gs` y `Servidor.gs`,
   carpeta compartida y clave privada. Publica como su propia cuenta y obtiene `/exec`.
5. En **Mi cuenta → Mi correo de informes**, registra su `/exec` y la misma
   `SERVIDOR_HMAC` una sola vez y pulsa **Verificar y guardar mi conexión**.
   No se utiliza la contraseña de Gmail. La identidad ejecutora debe coincidir.
6. Si ya estaba configurado, conserva proyecto, carpeta, clave y `/exec`.
   Actualiza el código y publica **Nueva versión de la implementación existente**.
7. Realiza aceptación con datos ficticios, carpeta y destinatarios de prueba.
   Revisa correo manual y automático, cierre y declaración manual antes de producción.
8. Descarga la lista individual de la guía y reiníciala para la siguiente persona.

**Cada supervisor utiliza el navegador; no instala Docker, MySQL ni FastAPI.**
El anfitrión del piloto sí mantiene su PC y Docker encendidos. Esta publicación
no habilita facturación de Google ni reemplaza el Firebase histórico.

Los pasos detallados y la lista están en el HTML de instalación. Las propiedades
y permisos de Google se documentan también en [Google y formatos](GOOGLE_Y_FORMATOS.md).

## Corrección de «La carpeta aún no está confirmada»

Antes, **Gestionar → Drive** solo avisaba que faltaba la carpeta y remitía a
Entregas. Una recepción abierta puede tener fotos pero no haber generado una
entrega, por lo que esa ruta no permitía llegar al diagnóstico.

Ahora, si existe un enlace confirmado, conserva la apertura directa. Si no
existe, abre **Fotos y carpetas** de esa recepción. Muestra conteos de fotos,
cuenta responsable, errores de copia, vista previa autenticada y acceso a
**Configurar mi conexión Google**. Consultar no crea carpetas, envía correos ni
modifica conteos. Verificar carpetas o copiar pendientes requiere pulsar la
acción correspondiente, con validación de permisos del servidor.

La falta del enlace no demuestra un rechazo de permisos Google. Puede haber
pendientes de conexión, permisos, clave o versión del puente, o todavía no haber
fotos. Revisar el mensaje concreto antes de reintentar y usar una carpeta de
pruebas separada. No volver a adjuntar fotos para forzar Drive.

No se accedió a la PC del usuario ni a su Drive. La consulta desde esta nube al
túnel compartido se bloqueó con `CONNECT 403`; el diagnóstico específico del
piloto sigue requiriendo el estado mostrado en ese entorno.

## Actualizar solo el piloto en Windows

En **PowerShell de Windows**, desde el repositorio de la PC anfitriona:

```powershell
git pull --ff-only origin desarrollo-local; if ($LASTEXITCODE -eq 0) { .\scripts\publicar_pruebas.ps1 }
```

El lanzador conserva volúmenes y claves y recrea el contenedor de aplicación
para cargar el código actualizado. No reinicia MySQL ni actualiza producción.
Esperar la URL pública confirmada; puede cambiar. Recargar la pantalla con
Ctrl+F5. Después, en la recepción, usar **Gestionar → Drive** y leer el estado.

El pase empresarial continúa mediante `scripts/actualizar_produccion.sh` con
commit completo, respaldo y comprobaciones; publicar en GitHub no ejecuta ese pase.

## Generación y validación

Fuentes editables: `docs/manuales/contenido.json`, `faq.json`, `manual.js` y
`manual.css`. Generador: `python3 scripts/generar_manuales.py`.
Genera cuatro HTML, ZIP reproducible y SHA-256; conserva el ZIP histórico 43.

Comprobaciones realizadas para esta edición:

- Navegador Chromium: cuatro guías con navegación, búsqueda, progreso, tema,
  descarga, impresión y anchos móviles de 360 y 390 px sin desbordamiento global.
- FAQ: búsquedas con/sin tildes, filtros, ausencia de resultados, teclado,
  expandir/cerrar, ayuda contextual e impresión de respuestas filtradas.
- Prácticas: conteo, pallet inválido, sobrante explícito, correo/PNC y cierres;
  evidencia histórica y nombres/rutas; lista individual persistente, exportación
  y reinicio; revisión técnica exportable.
- Los bytes de los cuatro HTML descargados se ejecutaron sin red ni llamadas API.
  El navegador automatizado bloquea `file://`; la comprobación offline utilizó
  el contenido descargado con `setContent` sin desactivar esa política.
- Drive con API simulada: recepción sin carpeta ni entrega abre diagnóstico y
  vista previa; cero POST al consultar, enlace confirmado conserva apertura,
  y un rechazo de permisos cierra la ventana vacía y comunica el error.
- FastAPI y MySQL de desarrollo: recepción abierta sintética, fotografía real
  pendiente y ninguna entrega. Desde la lista, Gestionar → Drive abrió el
  diagnóstico y la ampliación autenticada de esa foto. Se comprobó móvil sin
  desbordamiento y conservación de movimientos y entregas. Solo se eliminó
  la recepción sintética de esta comprobación.
- 63 pruebas Python de recuperación Drive, operación, fotografías y conexiones;
  226 JavaScript de páginas/imports, gestión, operación y acceso: aprobadas.
- ZIP regenerado con SHA idéntico, revisión de enlaces locales y fuentes.

Estas comprobaciones no acreditan correo real, permisos de Drive del usuario,
impresión física ni Safari real. La aceptación de campo sigue siendo necesaria.
