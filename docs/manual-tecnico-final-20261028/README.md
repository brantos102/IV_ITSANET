# IV ITSANET (Ingreso & Validación Itsanet)

Fecha: 28/10/2026 · America/Guayaquil.
Revisión documental: 1.1.

## Descargas

- [Descargar paquete completo ZIP](https://github.com/brantos102/IV_ITSANET/raw/refs/heads/desarrollo-local/docs/manual-tecnico-final-20261028/ITSANET-Documentacion-tecnica-final-20261028.zip)
- [Abrir manual técnico PDF](Manual-tecnico-ITSANET-20261028.pdf)
- [Abrir presentación PDF](Presentacion-tecnica-ITSANET-20261028.pdf)
- [Archivo de presentación HTML](Presentacion-tecnica-ITSANET-20261028.html)
- [Descargar diagramas editables draw.io](https://github.com/brantos102/IV_ITSANET/raw/refs/heads/desarrollo-local/docs/manual-tecnico-final-20261028/IV-ITSANET-Arquitectura-y-flujos.drawio)

Para utilizar la presentación, descargar el ZIP, extraer su contenido y abrir
`Presentacion-tecnica-ITSANET-20261028.html` en Chrome o Edge. GitHub muestra el
código de los HTML; la presentación se ejecuta al abrir el archivo descargado.
Si se solicita, iniciar sesión con una cuenta que tenga acceso al repositorio.

## Contenido

- Manual técnico: arquitectura, lenguajes, infraestructura, datos, evidencias,
  Drive, Google, configuración, mantenimiento, recuperación y diagnóstico.
- Diccionario extraído estáticamente: 30 tablas y 266 campos.
- Presentación HTML: 12 diapositivas; navegación por botones y teclado,
  recorrido interactivo del flujo, vistas ejecutivo/auditoría, carga local de
  mediciones y cálculo de tiempos comparables. Pantalla completa, impresión,
  descarga y uso sin conexión. No controla ni consulta producción.
- Diagramas draw.io: arquitectura, flujo operativo, modelo relacional de 30
  tablas, estructura del código y evidencias/carpetas. Para editarlos, abrir
  app.diagrams.net y elegir Archivo → Abrir desde → Dispositivo.
- Inventario JSON: tablas/campos/referencias y dependencias declaradas.

Generador: `scripts/generar_manual_tecnico_final.py`.
Presentación operativa y diagramas: `scripts/generar_presentacion_operativa_final.py`.

Los tiempos de la presentación se calculan con datos cargados por el expositor.
Sin registros del monitor no se muestran latencias productivas. El monitor
registra `duracionMs` de intentos de copia/organización de fotos, no el tiempo
total de captura ni la espera completa en cola. La comparación del flujo usa
mediciones ingresadas manualmente y no acredita un ahorro sin estudio.

Código funcional de referencia: v69, commit
`cda9187ea125aa710fdd29c093ddf2c16f2bc5fa`.
Infraestructura: evidencia de terminal compartida el 27/10/2026, incluido
MySQL local 8.0.46. El esquema y la revisión instalada se cotejan en el servidor.

La generación no conecta con producción ni modifica el aplicativo. Los valores
privados, los datos operativos y las credenciales no forman parte del paquete.
