#!/usr/bin/env bash
# Ejecutar en el servidor real, después de avisar la pausa a los operadores.
# bash /ruta/actualizar_produccion.sh /ruta/IV_ITSANET COMMIT_PROBADO
set -Eeuo pipefail
umask 077

repo="$(realpath "${1:?Falta la carpeta del repositorio}")"
revision="${2:?Falta el commit probado}"
espera_arranque="${ESPERA_ARRANQUE_ITSANET:-90}"
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || { echo 'Usar el hash completo del commit probado.'; exit 1; }
[[ "$espera_arranque" =~ ^[1-9][0-9]*$ ]] && (( espera_arranque <= 300 )) || { echo 'Espera de arranque: de 1 a 300 segundos.'; exit 1; }
cd "$repo"
[[ -x .venv/bin/python ]] || { echo 'No se encuentra la .venv operativa.'; exit 1; }
[[ "$(systemctl show iv-itsanet -p WorkingDirectory --value)" == "$repo" ]] || { echo 'Esta carpeta no coincide con el servicio iv-itsanet.'; exit 1; }
systemctl is-active --quiet iv-itsanet || { echo 'El servicio no está activo; diagnosticar antes de actualizar.'; exit 1; }
exec 9> .git/itsanet-pase.lock
flock -n 9 || { echo 'Ya hay otro pase en ejecución.'; exit 1; }
git cat-file -e "$revision^{commit}"
anterior="$(git rev-parse HEAD)"
git merge-base --is-ancestor "$anterior" "$revision" || { echo 'El commit operativo no es antecesor del candidato; no se forzará el cambio.'; exit 1; }
while IFS= read -r -d '' ruta; do
  [[ "$ruta" == 'mysql/01-crear-base.sql' ]] || { echo "Hay un cambio local que necesita revisión: $ruta"; exit 1; }
  git diff --quiet "$anterior" "$revision" -- "$ruta" || { echo 'El candidato cambia el SQL modificado localmente; no se sobrescribe.'; exit 1; }
done < <(git diff HEAD --name-only -z)
base_respaldo="$(dirname "$repo")/respaldos-itsanet"
mkdir -p "$base_respaldo"
respaldo="$(mktemp -d "$base_respaldo/pase-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
temporal="$(mktemp -d)"
git show "$revision:scripts/respaldo_produccion.py" > "$temporal/respaldo.py"
git show "$revision:requirements.txt" > "$temporal/requirements.txt"
git diff --binary HEAD -- mysql/01-crear-base.sql > "$respaldo/sql-local.patch"
printf '%s\n' "$anterior" > "$respaldo/commit-anterior.txt"
printf '%s\n' "$revision" > "$respaldo/commit-nuevo.txt"
# Descargar primero evita detener el servicio por una caída de PyPI.
.venv/bin/python -m pip wheel --wheel-dir "$temporal/dependencias" -r "$temporal/requirements.txt"
sudo -v
sudo test -f /etc/iv-itsanet.env
ejecutar_respaldo() {
  sudo systemd-run --quiet --wait --pipe --collect --unit="iv-itsanet-respaldo-$$-$1" \
    --uid="$(id -un)" --property="WorkingDirectory=$repo" \
    --property=EnvironmentFile=/etc/iv-itsanet.env \
    "$repo/.venv/bin/python" "$temporal/respaldo.py" --repo "$repo" \
    --salida "$respaldo" --revision "$anterior" "${@:2}"
}
ejecutar_respaldo requisitos --comprobar
detenido=0
marca_arranque=''
esperar_arranque() {
  local inicio_espera=$SECONDS estado_actual
  while :; do
    if curl --fail --silent --connect-timeout 1 --max-time 2 \
        http://127.0.0.1:3002/health --output "$temporal/salud.json" 2> "$temporal/salud-http.log" \
        && .venv/bin/python -c 'import json,sys; assert json.load(open(sys.argv[1])).get("ok") is True' "$temporal/salud.json" 2>/dev/null; then
      if curl --fail --silent --connect-timeout 1 --max-time 2 \
          http://127.0.0.1:3002/app/index.html --output "$temporal/acceso.html" 2>> "$temporal/salud-http.log" \
          && cmp --silent firebase/public/index.html "$temporal/acceso.html"; then
        echo 'Servicio y página de acceso confirmados.'
        return 0
      fi
    fi
    estado_actual="$(systemctl show iv-itsanet -p ActiveState --value || true)"
    [[ "$estado_actual" != 'failed' ]] || return 1
    (( SECONDS - inicio_espera < espera_arranque )) || return 1
    sleep 1
  done
}
guardar_diagnostico() {
  if [[ -n "$marca_arranque" ]]; then
    sudo journalctl -u iv-itsanet --since "$marca_arranque" -n 300 --no-pager \
      > "$respaldo/arranque-nuevo.log" 2>&1 || true
  else
    printf '%s\n' 'El pase falló antes de iniciar el código nuevo; revisar la fase de respaldo o instalación.' > "$respaldo/arranque-nuevo.log"
  fi
  for nombre in salud.json salud-http.log; do
    [[ ! -f "$temporal/$nombre" ]] || cp -- "$temporal/$nombre" "$respaldo/$nombre"
  done
  echo "Diagnóstico del intento guardado en: $respaldo/arranque-nuevo.log"
}
recuperar() {
  codigo=$?
  trap - EXIT
  if (( codigo != 0 && detenido )); then
    guardar_diagnostico
    echo 'El pase no terminó. Recuperando el código anterior sin restaurar ni reemplazar la base.'
    if sudo systemctl stop iv-itsanet; then
      if [[ "$(git rev-parse HEAD)" != "$anterior" ]]; then (umask 022; git switch --detach "$anterior") || true; fi
      if [[ "$(git rev-parse HEAD)" == "$anterior" ]] && sudo systemctl start iv-itsanet && esperar_arranque; then
        echo 'La versión anterior volvió a responder. Los registros operativos se conservaron.'
      else
        echo 'No se confirmó la recuperación; revisar el servicio antes de retomar la operación.'
      fi
    else
      echo 'No se confirmó la parada del servicio; revisar su estado antes de cambiar código o retomar la operación.'
    fi
  fi
  rm -rf -- "$temporal"
  exit "$codigo"
}
trap recuperar EXIT
echo 'Se pausa únicamente iv-itsanet para obtener una copia consistente de base y archivos.'
detenido=1
sudo systemctl stop iv-itsanet
ejecutar_respaldo datos
sudo install -m 600 -o "$(id -un)" -g "$(id -gn)" /etc/iv-itsanet.env "$respaldo/iv-itsanet.env"
# Los respaldos son privados; el código nuevo debe poder leerlo el usuario del servicio.
(umask 022; git merge --ff-only "$revision")
.venv/bin/python -m pip install --no-index --find-links "$temporal/dependencias" -r requirements.txt
marca_arranque="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
sudo systemctl start iv-itsanet
echo "Esperando el servicio y la interfaz, hasta $espera_arranque segundos…"
if ! esperar_arranque; then
  echo 'El servicio o la página de acceso no confirmaron el arranque de esta versión.'
  false
fi
systemctl is-active --quiet iv-itsanet
detenido=0
printf '\nCódigo instalado: %s\nRespaldo privado: %s\n' "$revision" "$respaldo"
echo 'Verificar sesión, recepción existente, conteos y Drive. Recargar las pantallas con Ctrl+F5.'
echo 'No se copiaron recepciones, usuarios, credenciales ni volúmenes de desarrollo.'
