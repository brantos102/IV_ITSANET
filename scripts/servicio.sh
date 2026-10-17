#!/usr/bin/env bash
# Deja la aplicación arrancando sola al encender el servidor.
#
#     cd ~/bryan/IV_ITSANET
#     export VAL_DATABASE_URL="mysql+pymysql://..."     # si no está ya
#     bash scripts/servicio.sh
#
# Genera el archivo del servicio a partir de lo que YA está configurado —la
# carpeta real, el usuario real, el entorno real— en vez de pedir que se copie
# una plantilla y se sustituyan los huecos a mano. Es donde se cuelan los
# errores: una ruta mal escrita, la contraseña a medias, el usuario equivocado.
#
# Pide sudo una vez, para escribir en /etc. Antes de tocar nada enseña lo que va
# a instalar.
set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICIO="iv-itsanet"
UNIDAD="/etc/systemd/system/${SERVICIO}.service"
ENTORNO="/etc/${SERVICIO}.env"

morir() { echo; echo "   ✗ $1"; echo; [ $# -gt 1 ] && echo "   $2"; exit 1; }

echo "=================================================="
echo " SERVICIO ${SERVICIO}"
echo "=================================================="

# --------------------------------------------------------------------------- #
[ -x "$RAIZ/.venv/bin/uvicorn" ] \
  || morir "No existe $RAIZ/.venv/bin/uvicorn" \
           "Ejecuta antes: bash scripts/instalar.sh"

[ -n "${VAL_DATABASE_URL:-}" ] \
  || morir "VAL_DATABASE_URL no está definida en esta terminal." \
"El servicio necesita saber a qué base hablar. Defínela y vuelve a ejecutar:
     export VAL_DATABASE_URL=\"mysql+pymysql://itsanet:LA-CLAVE@127.0.0.1:3306/iv_itsanet?charset=utf8mb4\""

case "$VAL_DATABASE_URL" in
  mysql*|mariadb*) : ;;
  *) morir "VAL_DATABASE_URL no apunta a MySQL." \
           "Un servicio que escriba en la base de pruebas no lo nota nadie hasta que falta todo." ;;
esac

# El 8000 es lo habitual, pero en un servidor compartido suele estar tomado.
# Se cambia con: PUERTO=3002 bash scripts/servicio.sh
PUERTO="${PUERTO:-8000}"

if ss -ltn 2>/dev/null | grep -q ":${PUERTO} "; then
  quien=$(ss -ltnp 2>/dev/null | grep ":${PUERTO} " | grep -o 'users:(("[^"]*"' | head -1 | tr -d '"' | sed 's/users:((//')
  echo
  echo "   AVISO: el puerto ${PUERTO} ya esta ocupado${quien:+ por $quien}."
  echo "   Si no es esta misma aplicacion, elige otro:  PUERTO=3002 bash scripts/servicio.sh"
fi
USUARIO="$(whoami)"

# --------------------------------------------------------------------------- #
echo
echo "Se va a instalar:"
echo "  Servicio   : ${SERVICIO}"
echo "  Usuario    : ${USUARIO}"
echo "  Carpeta    : ${RAIZ}"
echo "  Puerto     : ${PUERTO}"
echo "  Base       : ${VAL_DATABASE_URL%%:*}://…@${VAL_DATABASE_URL##*@}"
echo
echo "  La contraseña NO va dentro del servicio: va en ${ENTORNO}, que queda"
echo "  solo legible por root. Un archivo de servicio lo puede leer cualquier"
echo "  usuario del servidor, y ahí dentro estaría en texto plano."
echo
read -r -p "¿Seguir? [s/N] " respuesta
case "$respuesta" in s|S|si|SI|sí|Sí) : ;; *) echo "Cancelado."; exit 0 ;; esac

# --------------------------------------------------------------------------- #
echo
echo "── Archivo de entorno (solo root puede leerlo)"
sudo install -m 600 /dev/null "$ENTORNO" || morir "No se pudo crear $ENTORNO"
printf 'VAL_DATABASE_URL=%s\n' "$VAL_DATABASE_URL" | sudo tee "$ENTORNO" >/dev/null

# Las credenciales del WMS, si estan definidas en esta terminal, se guardan aqui
# mismo: es el unico sitio del servidor que solo lee root. Si no estan, el
# servicio arranca igual y trabaja contra el espejo local; se pueden anadir
# despues editando este archivo y reiniciando.
PUESTAS=0
for V in DEPOT_BASE_URL DEPOT_USUARIO DEPOT_CLAVE DEPOT_CLIENTE \
         DEPOT_RUTA_TOKEN DEPOT_RUTA_STOCK DEPOT_CABECERA_TOKEN; do
  eval "VALOR=\${$V:-}"
  if [ -n "$VALOR" ]; then
    printf '%s=%s\n' "$V" "$VALOR" | sudo tee -a "$ENTORNO" >/dev/null
    PUESTAS=$((PUESTAS + 1))
  fi
done
echo "   ✓ $ENTORNO"
if [ "$PUESTAS" -gt 0 ]; then
  echo "   ✓ $PUESTAS variable(s) de Depot guardadas (la clave no se imprime)"
else
  echo "   · sin credenciales de Depot: el maestro se carga por Excel."
  echo "     Para la API, anade a $ENTORNO:"
  echo "       DEPOT_BASE_URL=https://ec.itsanet.com/q_apidepot"
  echo "       DEPOT_USUARIO=...   DEPOT_CLAVE=..."
  echo "     y despues: sudo systemctl restart ${SERVICIO}"
fi

echo
echo "── Archivo del servicio"
sudo tee "$UNIDAD" >/dev/null <<UNIDAD_FIN
[Unit]
Description=ITSANET IMS - validacion fisica de recepciones
After=network.target mysql.service
Wants=mysql.service

[Service]
User=${USUARIO}
WorkingDirectory=${RAIZ}
EnvironmentFile=${ENTORNO}
ExecStart=${RAIZ}/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PUERTO}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIDAD_FIN
echo "   ✓ $UNIDAD"

echo
echo "── Arrancando"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICIO" >/dev/null 2>&1

sleep 3
if systemctl is-active --quiet "$SERVICIO"; then
  echo "   ✓ en marcha"
else
  echo "   ✗ no arrancó. Lo que dice:"
  echo
  sudo journalctl -u "$SERVICIO" -n 15 --no-pager | sed 's/^/   /'
  exit 1
fi

# --------------------------------------------------------------------------- #
# Que el servicio esté «activo» no significa que responda: puede estar
# levantandose y cayendo en bucle, que es justo lo que hace Restart=always.
echo
echo "── ¿Responde?"
if curl -s -o /dev/null -m 10 "http://127.0.0.1:${PUERTO}/login"; then
  echo "   ✓ sí"
else
  echo "   ✗ el servicio está activo pero no contesta. Mira: journalctl -u ${SERVICIO} -f"
  exit 1
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "=================================================="
echo " LISTO. Sobrevive a cerrar la sesión y a reiniciar."
echo
echo "   http://${IP}:${PUERTO}"
echo
echo " Para el día a día:"
echo "   git pull && sudo systemctl restart ${SERVICIO}"
echo "   journalctl -u ${SERVICIO} -f        # ver qué pasa, en vivo (Ctrl+C sale)"
echo "   sudo systemctl stop ${SERVICIO}     # pararla"
echo
echo " Si cambias la contraseña de MySQL, se edita en ${ENTORNO}"
echo " y después: sudo systemctl restart ${SERVICIO}"
echo "=================================================="
