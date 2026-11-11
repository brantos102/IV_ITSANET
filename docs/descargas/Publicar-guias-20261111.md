# Actualizar el manual en el mismo servidor

Este bloque publica únicamente los documentos nuevos. Conserva las versiones
anteriores y el manual técnico privado; no instala el control de equipos ni
reinicia el aplicativo. Ejecútalo en la terminal SSH de VS Code del servidor.
Cuando lo solicite, introduce la clave documental de la entrega anterior.

```bash
(
  set -euo pipefail
  cd "$HOME/bryan/IV_ITSANET"
  git fetch origin desarrollo-local
  revision_guias=8648cc9ecb2a8cf0ab9e3dc72a5c6cc0f2f04ad0
  publicador_guias=$(mktemp --suffix=.py)
  trap 'rm -f "$publicador_guias"' EXIT
  git show "$revision_guias:scripts/instalar_guias_usuario.py" > "$publicador_guias"
  "$PWD/.venv/bin/python" "$publicador_guias" \
    --repo "$PWD" --revision "$revision_guias"
)
```

Después de confirmar la publicación, comparte el acceso que ya utiliza el
aplicativo:

- Ver el manual: https://apps.flexnetuio.com:8443/api/app/manuales/usuario/html
- Descargar HTML: https://apps.flexnetuio.com:8443/api/app/manuales/usuario/html?descargar=true
- Descargar PDF: https://apps.flexnetuio.com:8443/api/app/manuales/usuario/pdf?descargar=true

Cada persona entra con su cuenta habitual. Los HTML descargados contienen las
imágenes y no requieren credenciales de conectividad para leerlos.

El control de equipos se instala y activa por separado, después de preparar
el móvil y la laptop autorizados de cada usuario. Su procedimiento está en
[CONTROL_EQUIPOS_USUARIO.md](../CONTROL_EQUIPOS_USUARIO.md).
