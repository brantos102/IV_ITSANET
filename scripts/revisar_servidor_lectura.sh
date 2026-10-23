#!/usr/bin/env bash
# Ejecutar en Linux @apps. Crea solo informes, sin actualizar ni reiniciar la app.
set -euo pipefail
umask 077
herramientas="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(realpath "${1:-$HOME/bryan/IV_ITSANET}")"
salida_dir="${2:-$HOME/bryan/reportes-itsanet}"
[[ -x "$repo/.venv/bin/python" ]] || { echo 'No se encontró la .venv del servidor.'; exit 1; }
[[ -f "$herramientas/estado_produccion.py" && -f "$herramientas/auditar_servidor_lectura.py" ]] || { echo 'Extrae todo el paquete de auditoría antes de ejecutar.'; exit 1; }
set +e
salida="$(sudo systemd-run --quiet --wait --pipe --collect \
  --unit="iv-itsanet-auditoria-$(date +%s)-$$" --uid="$(id -un)" \
  --property="WorkingDirectory=$repo" --property=EnvironmentFile=/etc/iv-itsanet.env \
  "$repo/.venv/bin/python" "$herramientas/auditar_servidor_lectura.py" \
  --repo "$repo" --salida "$salida_dir")"
codigo=$?
set -e
printf '%s\n' "$salida"
informe="$(printf '%s\n' "$salida" | tail -n 1)"
if [[ "$informe" == "$salida_dir"/auditoria-*.md && -f "$informe" ]]; then cat -- "$informe"; fi
exit "$codigo"
