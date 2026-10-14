#!/usr/bin/env bash
# Qué hay en el servidor, antes de tocar nada.
#
#   bash diagnostico-servidor.sh
#
# No instala, no cambia y no borra: solo mira y cuenta. Se puede pegar entero en
# PuTTY sin pedirle permiso a nadie.
#
# Las cuatro respuestas que decide todo lo demás son: si hay sudo, si hay
# internet, si MySQL ya está, y cuánto disco queda. Sin ellas, cualquier plan de
# migración es una suposición.

si_no() { [ "$1" -eq 0 ] && echo "SI" || echo "NO"; }
titulo() { echo; echo "--- $1 ---"; }

echo "========================================================"
echo " DIAGNOSTICO DEL SERVIDOR   $(date '+%Y-%m-%d %H:%M')"
echo "========================================================"

titulo "Maquina"
echo "Host      : $(hostname)"
echo "Usuario   : $(whoami)"
echo "Sistema   : $( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || uname -s )"
echo "Nucleo    : $(uname -r)"
echo "Arquit.   : $(uname -m)"

titulo "Permisos"
# -n: no pregunta contrasena. Si pide, el usuario TIENE sudo pero hace falta
# teclearla, que es distinto de no tenerlo.
if sudo -n true 2>/dev/null; then
  echo "sudo      : SI, sin contrasena"
elif sudo -v 2>/dev/null </dev/null; then
  echo "sudo      : SI, pidiendo contrasena"
else
  echo "sudo      : NO (hara falta que lo haga alguien de sistemas una vez)"
fi

titulo "Red"
for destino in github.com pypi.org script.google.com ec.itsanet.com; do
  if timeout 6 bash -c "echo > /dev/tcp/$destino/443" 2>/dev/null; then
    echo "$destino: alcanzable"
  else
    echo "$destino: NO alcanzable"
  fi
done
echo "IP        : $(hostname -I 2>/dev/null | awk '{print $1}')"

titulo "Lo que ya esta instalado"
for p in python3 pip3 git mysql mariadb systemctl nginx node; do
  if command -v "$p" >/dev/null 2>&1; then
    v=$("$p" --version 2>&1 | head -1)
    printf "%-10s: %s\n" "$p" "$v"
  else
    printf "%-10s: no esta\n" "$p"
  fi
done
command -v python3 >/dev/null && python3 -c "import venv" 2>/dev/null \
  && echo "venv      : SI" || echo "venv      : NO (hace falta python3-venv)"

titulo "Base de datos"
if command -v mysql >/dev/null 2>&1 || command -v mariadb >/dev/null 2>&1; then
  mysql --version 2>/dev/null || mariadb --version
  if systemctl is-active --quiet mysql 2>/dev/null || \
     systemctl is-active --quiet mariadb 2>/dev/null; then
    echo "Servicio  : en marcha"
  else
    echo "Servicio  : instalado pero PARADO (o sin permiso para consultarlo)"
  fi
else
  echo "No hay MySQL ni MariaDB. Hay que instalarlo (requiere sudo)."
fi

titulo "Espacio y memoria"
df -h "$HOME" 2>/dev/null | awk 'NR==1 || NR==2'
free -h 2>/dev/null | awk 'NR==1 || NR==2'

titulo "Puertos"
for puerto in 80 443 3306 8000; do
  if (command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":$puerto ") || \
     (command -v netstat >/dev/null && netstat -ltn 2>/dev/null | grep -q ":$puerto "); then
    echo "$puerto      : OCUPADO"
  else
    echo "$puerto      : libre"
  fi
done

titulo "Carpeta de trabajo"
echo "Destino   : $HOME/bryan/IV_ITSANET"
if [ -d "$HOME/bryan" ]; then
  echo "bryan/    : existe, $(ls -1A "$HOME/bryan" | wc -l) elementos"
  echo "Permisos  : $(stat -c '%A %U:%G' "$HOME/bryan" 2>/dev/null)"
else
  echo "bryan/    : NO existe todavia"
fi

echo
echo "========================================================"
echo " Copia TODO esto y pegalo en la conversacion."
echo "========================================================"
