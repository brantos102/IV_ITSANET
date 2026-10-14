#!/usr/bin/env bash
# Instala la aplicación en el servidor: entorno, librerías, tablas y pruebas.
#
#     cd ~/bryan/IV_ITSANET
#     bash scripts/instalar.sh
#
# Lo que NO hace: nada que necesite sudo. MySQL se instala aparte, una vez, y
# ese paso está en la guía. Aquí no hay ninguna orden que pueda romper el
# servidor ni tocar otra aplicación que esté corriendo.
#
# Se puede ejecutar las veces que haga falta. Si algo ya está hecho, lo dice y
# sigue; si algo falla, para ahí y explica qué hacer, porque seguir con un paso
# a medias solo cambia el error por otro más difícil de leer.
set -u

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ" || exit 1

paso()  { echo; echo "── $1"; }
bien()  { echo "   ✓ $1"; }
morir() { echo; echo "   ✗ $1"; echo; [ $# -gt 1 ] && echo "   $2"; exit 1; }

echo "=================================================="
echo " INSTALACION DE ITSANET IMS"
echo " Carpeta: $RAIZ"
echo "=================================================="

# --------------------------------------------------------------------------- #
paso "1/5  Python y el entorno aislado"

command -v python3 >/dev/null || morir "No hay python3." "sudo apt install -y python3"

# `import venv` NO basta: ese módulo está en la biblioteca estándar y se importa
# aunque falte el paquete python3-venv. Lo que falta entonces es ensurepip, y el
# fallo no sale hasta crear el entorno, con un mensaje que no dice qué instalar.
python3 -c "import ensurepip" 2>/dev/null \
  || morir "Falta el paquete python3-venv." "sudo apt install -y python3-venv python3-pip"

if [ -d .venv ]; then
  bien "el entorno ya existe"
else
  python3 -m venv .venv || morir "No se pudo crear el entorno."
  bien "entorno creado en .venv"
fi

# A partir de aquí se usa el python DEL ENTORNO por su ruta, sin «activate».
# Activar solo vale en la terminal donde se escribe, y olvidarlo es el origen de
# la mitad de los errores de los primeros días.
PY="$RAIZ/.venv/bin/python"
[ -x "$PY" ] || morir "El entorno está a medias. Borra .venv y vuelve a ejecutar esto."

# --------------------------------------------------------------------------- #
paso "2/5  Librerías"

"$PY" -m pip install --quiet --upgrade pip 2>/dev/null
if "$PY" -m pip install --quiet -r requirements.txt; then
  bien "instaladas"
else
  morir "No se pudieron descargar las librerías." \
        "Sin internet: en tu PC 'pip download -r requirements.txt -d paquetes',
   copia esa carpeta aquí y ejecuta
   .venv/bin/python -m pip install --no-index --find-links paquetes -r requirements.txt"
fi

"$PY" -c "import fastapi, sqlalchemy, pymysql" 2>/dev/null \
  || morir "Las librerías no quedaron bien instaladas."
bien "fastapi, sqlalchemy y pymysql responden"

# --------------------------------------------------------------------------- #
paso "3/5  A qué base de datos se va a hablar"

if [ -z "${VAL_DATABASE_URL:-}" ]; then
  echo "   VAL_DATABASE_URL no está definida."
  echo
  echo "   Sin ella la aplicación escribe en un archivo de pruebas, no en MySQL,"
  echo "   y eso no se nota hasta que falta todo lo contado. Defínela así, con tu"
  echo "   contraseña, y vuelve a ejecutar:"
  echo
  echo "     export VAL_DATABASE_URL=\"mysql+pymysql://itsanet:LA-CLAVE@127.0.0.1:3306/iv_itsanet?charset=utf8mb4\""
  echo
  exit 1
fi

case "$VAL_DATABASE_URL" in
  mysql*|mariadb*) bien "apunta a MySQL" ;;
  *) morir "VAL_DATABASE_URL no apunta a MySQL sino a: ${VAL_DATABASE_URL%%:*}" \
           "Revisa que empiece por mysql+pymysql:// y termine en ?charset=utf8mb4" ;;
esac

case "$VAL_DATABASE_URL" in
  *charset=utf8mb4*) bien "con utf8mb4" ;;
  *) morir "Falta ?charset=utf8mb4 al final." \
           "Sin eso el conector negocia latin1 y las tildes se guardan rotas." ;;
esac

# --------------------------------------------------------------------------- #
paso "4/5  Las tablas"

"$PY" scripts/preparar_base.py || morir "No se pudieron crear las tablas." \
  "El mensaje de arriba dice por qué. Lo más común: la contraseña no coincide
   con la del archivo mysql/01-crear-base.sql, o MySQL no está arrancado
   (sudo systemctl start mysql)."

# --------------------------------------------------------------------------- #
paso "5/5  Las pruebas"

if "$PY" -m pytest tests -q 2>&1 | tail -3; then
  bien "en verde"
else
  echo
  echo "   Alguna prueba falla. La aplicación puede arrancar igual, pero antes"
  echo "   de usarla conviene mirar por qué: pásale la salida de arriba a quien"
  echo "   lleve el proyecto."
fi

# --------------------------------------------------------------------------- #
echo
echo "=================================================="
echo " LISTO. Lo que queda:"
echo
echo " 1. Crear tu usuario administrador:"
echo "      .venv/bin/python scripts/crear_operador.py TUUSUARIO \"Tu Nombre\" 1234 --rol ADMIN"
echo
echo " 2. Arrancar para probar:"
echo "      .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo
echo " 3. Abrir desde otro equipo de la red:"
echo "      http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000"
echo
echo " Para que arranque sola al encender el servidor, el Paso 8 de la guía."
echo "=================================================="
