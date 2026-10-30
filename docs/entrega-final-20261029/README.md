# IV ITSANET · Ingreso & Validación Itsanet

Entrega documental del 29/10/2026 · revisión 1.2 · código funcional v69.

Entrega posterior: [informe final, manuales ilustrados y correo del 30/10](../entrega-directivos-20261030/README.md).

## Descargas

- [Paquete completo ZIP](https://github.com/brantos102/IV_ITSANET/raw/refs/heads/desarrollo-local/docs/entrega-final-20261029/IV-ITSANET-Entrega-final-20261029.zip)
- [Manual técnico PDF](Manual-tecnico-IV-ITSANET-20261029.pdf)
- [Guía de demostración y mediciones PDF](Guia-demostracion-y-mediciones-IV-ITSANET.pdf)
- [Protección de datos personales, Ecuador PDF](Proteccion-datos-Ecuador-IV-ITSANET.pdf)
- [Presentación HTML](Presentacion-IV-ITSANET-20261029.html)
- [Presentación PDF](Presentacion-IV-ITSANET-20261029.pdf)
- [Diagramas editables draw.io](https://github.com/brantos102/IV_ITSANET/raw/refs/heads/desarrollo-local/docs/entrega-final-20261029/IV-ITSANET-Arquitectura-y-flujos-20261029.drawio)

Descomprimir el ZIP y abrir el HTML con Chrome/Edge. GitHub muestra el código
HTML y no ejecuta la presentación. Todos los recursos de la presentación están
integrados; funciona sin conexión.

## Cómo cargar los tiempos

1. Seguir la guía: exportar la respuesta del monitor autenticado como ADMIN o
   ejecutar el exportador SQL de solo lectura para un periodo delimitado.
2. Descargar el JSON desde el servidor al PC del expositor.
3. En «Rendimiento observado», seleccionar el JSON. Se calcula mediana/P95
   de intentos FOTO COPIADA que contienen `duracionMs` válido.
4. En «Tiempo del flujo operativo», cargar la plantilla CSV completada con
   mediciones comparables o introducir registros/minutos manualmente.

No se recibió un JSON de producción ni tiempos históricos. No se incluyen
resultados reales inventados. La métrica de fotos excluye captura y espera en
cola; no mide el ciclo completo de conteo. El JSON se procesa localmente y no
se publica. La descarga desde la presentación limpia datos cargados en la sesión.

El exportador no importa la aplicación, inicia SQL READ ONLY y exporta una
lista cerrada de fecha/proceso/estado/duración. No incluye usuarios, correos,
SKU, recepción, referencias ni contenido de fotos. Usar periodos pequeños y
conservar el archivo como información interna. No hay actualización/reinicio
de iv-itsanet, Apache o MySQL.

## Capturas y demostración

Las tres capturas incorporadas corresponden a la interfaz probada en v64/v69
con datos sintéticos. No son capturas de la producción del 29/10. La galería
permite cargar capturas actuales previamente revisadas; permanecen en memoria
y no se incluyen en la descarga del HTML.

La guía explica cómo mostrar un móvil/handheld real, lector físico, cámara y
registro de fotos. La presentación abre la URL real en otra pestaña; no registra
datos automáticamente. Utilizar pruebas o una recepción DEMO autorizada y no
enviar correos a clientes durante la exposición.

Los diagramas draw.io tienen siete páginas: arquitectura, flujo operativo,
modelo relacional, código, evidencias, flujo del operario y flujo del supervisor.
Abrir el archivo desde app.diagrams.net → Archivo → Abrir desde → Dispositivo.

## Protección de datos

El documento distingue controles de código y obligaciones organizativas por
acreditar. Drive/Gmail son tratamiento externo: no se afirma residencia exclusiva
en Ecuador. Se citan Constitución, LOPDP y Reglamento General. El entorno bloqueó
la consulta de portales oficiales; verificar resoluciones SPDP vigentes y textos
consolidados antes de la aprobación normativa. No es certificación de cumplimiento.

## Reproducción

Generador: `scripts/generar_cierre_documental_20261029.py`, que reutiliza los
generadores técnicos anteriores. El código funcional documentado permanece en
`cda9187ea125aa710fdd29c093ddf2c16f2bc5fa`. Esta entrega no modifica la aplicación.
