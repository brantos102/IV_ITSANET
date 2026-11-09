# IV ITSANET · Manuales de 38 pasos y publicación en el servidor

Esta entrega elimina los pasos 39 y 40 del manual de usuario, su índice y referencias. Conserva las capturas del Word V2 y permite reemplazar las imágenes del selector de correos en el paso 33. No vuelve a crear los apartados eliminados.

El manual de usuario se distribuye desde el servidor con sesión del aplicativo. El técnico queda solamente en disco dentro del sistema; no tiene ruta web. La generación documental y la publicación de archivos no cambian conteos, recepciones, credenciales ni correos. La instalación del código sí requiere la pausa del servicio indicada al final.

## 1. Captura del selector de correos

1. Entra como supervisor y abre una recepción autorizada con varios packing lists o embarques.
2. En Validar → Informes, abre **Correo final editable**.
3. Si ves la lista de correos, pulsa **Elegir: por packing list o por embarque**. Si se abre el editor individual, utiliza **Elegir embarque / packing list**; no cambies el contenido. Ese editor puede guardar el borrador al abrir el selector, pero no envía el correo.
4. En **Organizar correos de la recepción**, despliega **Preparar y revisar**. Deben verse: un correo por packing list, un correo por embarque y un correo consolidado de toda la recepción.
5. En Windows, abre Recortes y elige un retardo de cinco segundos; inicia el recorte y despliega el selector durante la espera. Recorta solo el cuadro con sus opciones, manteniendo el texto legible. Puedes tomar otra imagen con la vista previa del modo elegido.
6. No pulses **Confirmar agrupación y continuar** ni **Enviar correo** para tomar la captura. Usa **Volver a la recepción** cuando termines.
7. Guarda `selector-correos.png`. En el manual HTML, ve al paso 33 y usa **Reemplazar capturas del paso**. Selecciona una o varias imágenes. **Añadir capturas adicionales** conserva las anteriores.
8. Pulsa **Descargar HTML con capturas**. Abre ese archivo descargado y usa **Imprimir / PDF → Guardar como PDF**, papel A4. El PDF anterior no cambia cuando editas el HTML: genera ambos de la misma versión antes de publicarlos.

Las referencias de pruebas están identificadas; no se presentan como capturas productivas. Al reemplazarlas se actualiza la leyenda del paso. La edición del HTML es local y no sube imágenes al aplicativo.

## 2. Obtener el código de esta entrega sin cambiar el servicio

En VS Code conectado por SSH al servidor, abre la carpeta `/home/enicolalde/bryan` para ver también la carpeta de preparación de documentos. Después abre una terminal remota:

```bash
(
  set -euo pipefail
  cd "$HOME/bryan/IV_ITSANET"
  git fetch origin desarrollo-local tag iv-itsanet-20261109-72.1
  iv_revision=$(git rev-parse 'iv-itsanet-20261109-72.1^{commit}')
  iv_fuente=$(mktemp -d "$HOME/bryan/iv-manuales-fuente-72.XXXXXX")
  git archive "$iv_revision" | tar -x -C "$iv_fuente"
  printf '%s\n' "$iv_fuente" > "$HOME/bryan/.iv-manuales-fuente-72"
  printf 'Copia para generar documentos: %s\nRevisión: %s\n' "$iv_fuente" "$iv_revision"
)
```

La copia tiene sus propios scripts. No se reemplaza el código que está ejecutando el servicio. Su ruta queda guardada para los siguientes comandos.

## 3. Generar los manuales desde el Word

Arrastra desde tu computador al Explorador remoto de VS Code el Word V2 y la captura. Ejemplo de ubicaciones, fuera del repositorio:

```text
/home/enicolalde/bryan/Manual-usuario-completo-IV-ITSANET V2.docx
/home/enicolalde/bryan/selector-correos.png
```

Si ya tienes el ZIP completo de la entrega, puedes omitir la generación desde Word: copia sus cuatro documentos a la carpeta de preparación y sustituye la captura desde el HTML. Para regenerarlos desde tu Word:

```bash
iv_fuente=$(cat "$HOME/bryan/.iv-manuales-fuente-72")
python3 "$iv_fuente/scripts/preparar_manuales_desde_word.py" \
  --word "$HOME/bryan/Manual-usuario-completo-IV-ITSANET V2.docx" \
  --salida "$HOME/bryan/manuales-IV-ITSANET-38" \
  --revision "$(git -C "$HOME/bryan/IV_ITSANET" rev-parse 'iv-itsanet-20261109-72.1^{commit}')" \
  --captura-correos "$HOME/bryan/selector-correos.png"
```

Si todavía no tienes la captura, omite únicamente `--captura-correos`; el paso 33 conservará una referencia identificada que puedes reemplazar en el HTML.

En el Explorador de VS Code: clic derecho en el ZIP → **Descargar**. Los HTML incluyen sus imágenes; no requieren la carpeta de capturas para visualizarse. Para obtener los PDF, ábrelos en Chrome/Edge y utiliza Imprimir / PDF. Después vuelve a subir los HTML completados y PDF a la carpeta de preparación con estos nombres:

```text
Manual-usuario-final-IV-ITSANET.html
Manual-usuario-final-IV-ITSANET.pdf
Manual-tecnico-final-IV-ITSANET.html
Manual-tecnico-final-IV-ITSANET.pdf
```

La exportación automática es opcional: requiere Node.js 18+, `npm ci` en la copia y un Chrome/Chromium/Edge instalado. El script `exportar_pdf_manuales.py --carpeta CARPETA` genera los dos PDF y su registro de integridad. No instala navegadores. La generación repetida conserva los archivos anteriores en `_anteriores`; no incluye un PDF antiguo junto a un HTML nuevo.

## 4. Publicar los documentos en la carpeta del sistema

Ejecuta desde la copia del código, con los cuatro archivos ya revisados:

```bash
iv_fuente=$(cat "$HOME/bryan/.iv-manuales-fuente-72")
python3 "$iv_fuente/scripts/publicar_manuales.py" \
  --usuario-html "$HOME/bryan/manuales-IV-ITSANET-38/Manual-usuario-final-IV-ITSANET.html" \
  --usuario-pdf "$HOME/bryan/manuales-IV-ITSANET-38/Manual-usuario-final-IV-ITSANET.pdf" \
  --tecnico-html "$HOME/bryan/manuales-IV-ITSANET-38/Manual-tecnico-final-IV-ITSANET.html" \
  --tecnico-pdf "$HOME/bryan/manuales-IV-ITSANET-38/Manual-tecnico-final-IV-ITSANET.pdf" \
  --destino "$HOME/bryan/IV_ITSANET/documentacion/manuales" \
  --revision "$(git -C "$HOME/bryan/IV_ITSANET" rev-parse 'iv-itsanet-20261109-72.1^{commit}')"
```

El publicador valida los 38 pasos, conserva las versiones anteriores y activa el par completo. El HTML enlaza al PDF de su misma versión. Si editas sus capturas después, retira el enlace al PDF anterior en esa copia local para que no se confundan versiones.

```text
IV_ITSANET/documentacion/manuales/
├── usuario/
│   ├── actual.json
│   └── versiones/<version>/     HTML, PDF e integridad
└── tecnico/
    ├── actual.json
    └── versiones/<version>/     Archivos locales privados
```

Los documentos publicados están excluidos de Git y se incorporan al respaldo del sistema. La cuenta del servicio debe tener lectura sobre la carpeta del usuario; el técnico conserva permisos privados de mantenimiento.

## 5. Actualizar el aplicativo con respaldo

Después de comunicar la pausa a los operarios:

```bash
(
  set -euo pipefail
  cd "$HOME/bryan/IV_ITSANET"
  git fetch origin desarrollo-local tag iv-itsanet-20261109-72.1
  iv_revision=$(git rev-parse 'iv-itsanet-20261109-72.1^{commit}')
  iv_pase=$(mktemp /tmp/iv-itsanet-pase-72.XXXXXX)
  git show "$iv_revision:scripts/actualizar_produccion.sh" > "$iv_pase"
  bash "$iv_pase" "$PWD" "$iv_revision"
)
```

El procedimiento respalda base, archivos, claves y manuales, verifica el árbol de trabajo y aplica avance lineal. Si informa un conflicto, conservar el mensaje y revisarlo; no usar `reset --hard`, reemplazar la base ni reinstalar MySQL. No requiere cambios de Apache ni nuevas tablas para la publicación de manuales.

## 6. Comprobar antes de la entrega

- Entrar, recargar con Ctrl+F5 y abrir Menú → **Manual de usuario · HTML y PDF**. Se abre en otra pestaña.
- Confirmar 38 pasos, la captura correcta del paso 33 y la descarga de su PDF. Sin sesión, el acceso debe rechazarse.
- Revisar el técnico desde la carpeta local. No existe un enlace público a ese documento.
- Comprobar una recepción existente, la recuperación de pendientes, un informe y las integraciones operativas.
- Si aún no se importó `RELACION_CODIGOS.xlsx`, cargarlo desde Recepciones → Catálogo → Importar códigos de barras. El archivo corporativo no se carga automáticamente al actualizar.
- Registrar la revisión instalada y el resultado del pase. La preparación de este código no acredita por sí sola que el servidor haya sido actualizado.

Con estos puntos completos se puede redactar el correo de entrega con los enlaces definitivos. El correo no se envía ni se programa con este procedimiento.
