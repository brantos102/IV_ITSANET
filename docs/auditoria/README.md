# Informe técnico y captura de servidor · 18/10/2026

[Descargar paquete completo](https://github.com/brantos102/IV_ITSANET/raw/refs/tags/itsanet-20261018-informe-servidor/docs/descargas/ITSANET-informe-servidor-20261018.zip).

Extraer todo el ZIP y abrir `informe-tecnico.html`. Incluye el documento en
Markdown, el HTML autónomo, los dos helpers Python y el wrapper Linux de captura.
Permite buscar, filtrar por evidencia, expandir, imprimir/PDF, estimar el buffer
de fotos e importar capturas locales. No contacta la API ni sube esos archivos.
Admite tanto el JSON del nuevo helper como el formato 1 de `estado_produccion.py`.
Las cifras no disponibles se muestran como pendientes, nunca como cero.

La captura de terminal aportada por el usuario confirmó el checkout empresarial
46, `iv-itsanet` activo/running, NRestarts=0, /health correcto, filesystem de 73G
con 53G disponibles y uso del 25 %, RAM disponible 9,8 GiB y swap sin uso.
La medición de las 17:38:45 de Ecuador confirma 13,14 MiB de datos e índices en
30 tablas MySQL y 5,59 MiB de archivos locales. Las 69 fotos registradas tienen
ID de Drive; ese ID no comprueba hoy la existencia remota. Hay una entrega en
REVISION y 20 archivos de informe sin ID, que no equivalen a 20 correos pendientes.
No acredita crecimiento diario ni disco exclusivo de toda la aplicación.
El informe distingue código publicado, HEAD del checkout y proceso realmente
cargado, y conserva las limitaciones de una captura puntual.

La edición documental **no cambia la versión 48 de la aplicación**, el servidor
empresarial ni el enlace del piloto. No ejecutar `publicar_pruebas.ps1` para
consultar este paquete si se quiere conservar el túnel actual sin reiniciarlo.

Para capturar más métricas, extraer los scripts juntos fuera del checkout y,
en Linux `@apps`, ejecutar desde la carpeta extraída:

```bash
bash revisar_servidor_lectura.sh "$HOME/bryan/IV_ITSANET"
```

Usa una unidad temporal distinta de `iv-itsanet`, el EnvironmentFile privado
existente y la `.venv` instalada. MySQL se consulta en READ ONLY con límites de
tiempo. No ejecuta migraciones, limpiezas, cambios de código, reenvíos, creación
de carpetas Drive o reinicios. Solo escribe informes privados fuera del repo.
Los valores de claves y el contenido de fotos no forman parte del resultado.
Las consultas consumen recursos: es una captura puntual, no un monitor continuo.

El diagnóstico no importa `app.main`, `app.db` ni la configuración de la app.
Lee el certificado con validación TLS; la confianza de esa máquina no sustituye
la comprobación del certificado en cada móvil. No abre archivos de clave TLS.
La captura no acredita una restauración, permisos actuales de todos los archivos
Drive ni una prueba de carga. Las carpetas se cuentan por archivos inmediatos,
con límite; no es un recorrido recursivo de backups.

Para regenerar los descargables desde estas fuentes:

```bash
python3 scripts/generar_informe_servidor.py
```

El ZIP tiene fecha fija y SHA-256 reproducible. La fuente es
`informe-servidor-20261018.json`, con estilos e interacción en esta carpeta.

Validación de esta entrega: 10 pruebas Python aprobadas y una MySQL condicionada
omitida, wrapper probado con sudo simulado y salida privada, y navegador Chromium
con búsqueda, filtros, datos locales, comparación por identidad de base/fecha,
texto seguro, impresión de todas las secciones, móvil y descarga offline sin API.
La medición sobre el servidor real se obtiene únicamente del usuario; no se
confunde con los contenedores de desarrollo de esta nube.
