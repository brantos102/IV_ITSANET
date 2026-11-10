#!/usr/bin/env bash
# Instancia y enlace HTTPS de pruebas. No carga /etc/iv-itsanet.env ni toca iv-itsanet.
set -Eeuo pipefail
umask 077
repositorio=$(realpath "${1:-.}")
revision=${2:?Indica el commit completo probado}
accion=${3:-publicar}
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || { echo 'Se necesita un commit completo.' >&2; exit 1; }
[[ "$accion" == publicar || "$accion" == preparar || "$accion" == detener || "$accion" == estado ]] || { echo 'Acción: publicar, preparar, detener o estado.' >&2; exit 1; }
command -v docker >/dev/null
command -v flock >/dev/null
docker compose version >/dev/null
docker info >/dev/null
git -C "$repositorio" cat-file -e "$revision^{commit}"
base_pruebas="$(dirname "$repositorio")/itsanet-pruebas-publicas"
mkdir -p "$base_pruebas"
chmod 755 "$base_pruebas"
exec 9>"$base_pruebas/.pase.lock"
flock -n 9 || { echo 'Ya hay otra actualización de pruebas en curso.' >&2; exit 1; }
privado="$base_pruebas/.privado"
if [[ ! -f "$privado/entorno.env" ]] && docker volume inspect iv-itsanet-pruebas-publicas_mysql_pruebas >/dev/null 2>&1; then
  echo 'Ya existen datos de pruebas pero falta su configuración privada. Recupera el archivo; no se regeneraron contraseñas.' >&2
  exit 1
fi
release="$base_pruebas/versiones/$revision"
if [[ ! -f "$release/compose.pruebas-publicas.yaml" ]]; then
  mkdir -p "$release"
  git -C "$repositorio" archive "$revision" | tar -x -C "$release"
  find "$base_pruebas/versiones" -type d -exec chmod 755 {} +
  find "$release" -type f -exec chmod 644 {} +
fi
python3 "$release/scripts/preparar_pruebas_publicas.py" "$privado"
export ITSANET_LOCAL_PORT=3003
componer=(docker compose --project-name iv-itsanet-pruebas-publicas --project-directory "$release" --env-file "$privado/entorno.env" -f "$release/compose.local.yaml" -f "$release/compose.pruebas-publicas.yaml")
"${componer[@]}" config --quiet
if [[ "$accion" == detener ]]; then
  "${componer[@]}" stop enlace-https
  echo 'Enlace público de pruebas detenido. Producción y datos conservados.'
  exit
fi
if [[ "$accion" == estado ]]; then
  "${componer[@]}" ps
  test ! -f "$base_pruebas/url-publica.txt" || cat "$base_pruebas/url-publica.txt"
  exit
fi
propia=$("${componer[@]}" ps --quiet app)
if [[ -z "$propia" ]]; then
  python3 - <<'PY'
import socket
with socket.socket() as s:
    try:s.bind(('127.0.0.1',3003))
    except OSError:raise SystemExit('El puerto 3003 está ocupado por otro servicio. No se modificó.')
PY
fi
"${componer[@]}" up --detach --build --wait --wait-timeout 300 mysql app
curl --retry 8 --retry-connrefused --retry-delay 1 --max-time 5 --fail --silent http://127.0.0.1:3003/health >/dev/null
if [[ "$accion" == preparar ]]; then
  echo 'Instancia aislada de pruebas comprobada en el puerto local 3003. Todavía no se abrió un enlace público.'
  exit
fi
inicio_enlace=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [[ -n "$("${componer[@]}" ps --quiet enlace-https)" ]]; then
  "${componer[@]}" restart enlace-https
else
  "${componer[@]}" up --detach enlace-https
fi
for intento in $(seq 1 20); do
  url_publica=$("${componer[@]}" logs --since "$inicio_enlace" --no-color --tail 200 enlace-https 2>&1 | python3 -c 'import re,sys; r=re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com",sys.stdin.read()); print(r[-1] if r else "")')
  if [[ -n "$url_publica" ]] && curl --max-time 5 --fail --silent "$url_publica/api/auth/entorno" | python3 -c 'import json,sys; assert json.load(sys.stdin)["pruebasPublicas"] is True' 2>/dev/null; then
    printf '%s/app/\n' "$url_publica" > "$base_pruebas/url-publica.txt"
    printf 'Pruebas: %s/app/\n' "$url_publica"
    printf 'Accesos iniciales privados: %s/accesos-iniciales.txt\n' "$privado"
    echo 'Comparte únicamente la cuenta individual de prueba. El supervisor entra desde cualquier red sin VPN ni SSH.'
    echo 'El enlace es temporal y depende de este servicio. Producción 3002 permanece independiente.'
    exit
  fi
  sleep 2
done
echo 'La instancia local de pruebas funciona, pero el proveedor no confirmó un enlace público. Revisa los logs de enlace-https; producción no fue modificada.' >&2
exit 1
