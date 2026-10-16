#!/usr/bin/env bash
# Ejecutar en el servidor real, después de avisar la pausa a los operadores.
# bash /ruta/actualizar_produccion.sh /ruta/IV_ITSANET COMMIT_PROBADO
set -Eeuo pipefail
umask 077

repo="$(realpath "${1:?Falta la carpeta del repositorio}")"
revision="${2:?Falta el commit probado}"
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || { echo 'Usar el hash completo del commit probado.'; exit 1; }
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
recuperar() {
  codigo=$?
  trap - EXIT
  if (( codigo != 0 && detenido )); then
    echo 'El pase no terminó. Recuperando el código anterior sin restaurar ni reemplazar la base.'
    if sudo systemctl stop iv-itsanet; then
      if [[ "$(git rev-parse HEAD)" != "$anterior" ]]; then git switch --detach "$anterior" || true; fi
      sudo systemctl start iv-itsanet || true
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
git merge --ff-only "$revision"
.venv/bin/python -m pip install --no-index --find-links "$temporal/dependencias" -r requirements.txt
sudo systemctl start iv-itsanet
salud_itsanet="$(curl --fail --silent --show-error --retry 12 --retry-connrefused --retry-delay 1 \
  --connect-timeout 3 --max-time 5 http://127.0.0.1:3002/health)"
.venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); assert d.get("ok") is True, "Salud no confirmada"; print(json.dumps(d))' <<< "$salud_itsanet"
systemctl is-active --quiet iv-itsanet
detenido=0
printf '\nCódigo instalado: %s\nRespaldo privado: %s\n' "$revision" "$respaldo"
echo 'Verificar sesión, recepción existente, conteos y Drive. Recargar las pantallas con Ctrl+F5.'
echo 'No se copiaron recepciones, usuarios, credenciales ni volúmenes de desarrollo.'
