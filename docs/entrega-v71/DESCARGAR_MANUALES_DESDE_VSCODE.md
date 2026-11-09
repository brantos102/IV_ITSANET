# Obtener los manuales con las imágenes del Word

Este procedimiento genera los documentos en una carpeta privada del servidor y permite descargarlos con VS Code. No reinicia ni actualiza la aplicación de producción; no conecta con MySQL o Google.

1. En VS Code conectado por SSH a `apps`, abre la carpeta `/home/enicolalde/bryan`.
2. Arrastra desde tu computador el archivo **Manual-usuario-completo-IV-ITSANET V2.docx** al Explorador de esa carpeta. Debe quedar en `/home/enicolalde/bryan/Manual-usuario-completo-IV-ITSANET V2.docx`, fuera del repositorio.
3. Abre una terminal remota de VS Code y pega el bloque completo:

```bash
(
  set -euo pipefail
  umask 077
  cd "$HOME/bryan/IV_ITSANET"
  git fetch origin desarrollo-local
  iv_revision=ddd0b1b12c89432e228c5dddcb71e7501adb24b3
  iv_fuente=$(mktemp -d "$HOME/bryan/iv-manuales-fuente-71.XXXXXX")
  git archive "$iv_revision" | tar -x -C "$iv_fuente"
  python3 "$iv_fuente/scripts/preparar_manuales_desde_word.py" \
    --word "$HOME/bryan/Manual-usuario-completo-IV-ITSANET V2.docx" \
    --salida "$HOME/bryan/documentacion-IV-ITSANET" \
    --revision "$iv_revision"
)
```

4. En el Explorador de VS Code, actualiza la lista de carpetas y abre **documentacion-IV-ITSANET**.
5. Haz clic derecho sobre **IV-ITSANET-manuales-privados-v71.zip → Descargar** y elige Descargas de tu computador. Se utiliza la conexión SSH ya abierta, sin necesitar `scp` en PowerShell.
6. Extrae el ZIP y abre los HTML con Chrome o Edge. Incluyen las imágenes. Puedes ampliarlas, buscar pasos y añadir capturas pendientes. Para guardar un PDF, pulsa **Imprimir / PDF** y selecciona **Guardar como PDF**.

El archivo incluye el manual de usuario de 40 pasos, el manual técnico y la guía de continuidad sin conexión. Las capturas operativas provienen de tu Word; las referencias de pruebas están identificadas. Los documentos completos no se publican en GitHub.

Si el nombre o ubicación del Word es diferente, corrige únicamente el valor de `--word`. Un mensaje de archivo no encontrado se resuelve subiendo el Word a la carpeta indicada, sin tocar permisos del servicio ni de la base.

## Aplicar la mejora al aplicativo

La generación documental anterior no instala v71. Para instalar el candidato probado, comunicar la pausa operativa y utilizar el actualizador con respaldo:

```bash
(
  set -euo pipefail
  cd "$HOME/bryan/IV_ITSANET"
  git fetch origin desarrollo-local
  iv_revision=ddd0b1b12c89432e228c5dddcb71e7501adb24b3
  iv_pase=$(mktemp /tmp/iv-itsanet-pase-71.XXXXXX)
  git show "$iv_revision:scripts/actualizar_produccion.sh" > "$iv_pase"
  bash "$iv_pase" "$PWD" "$iv_revision"
)
```

El actualizador comprueba carpeta, servicio, cambios locales y compatibilidad de la revisión, prepara dependencias, respalda y verifica el arranque. Si informa un conflicto, conservar ese mensaje y revisarlo; no usar `reset --hard`, reemplazar la base ni reinstalar MySQL.

Después del pase: Ctrl+F5, abrir una recepción con conexión, comprobar la descarga de lecturas, registrar un conteo controlado, revisar su confirmación y probar la recuperación sin red con registros autorizados. Conservar borradores y pendientes existentes de cada navegador. Apache y MySQL no se reconfiguran en este pase.
