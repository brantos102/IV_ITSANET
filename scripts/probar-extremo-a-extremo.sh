#!/usr/bin/env bash
# Levanta el servidor con una base de pruebas y lanza contra él la capa de datos
# del navegador: el mismo js/local.js que corre en el handheld.
#
#     bash scripts/probar-extremo-a-extremo.sh
#
# Es la prueba que cubre el hueco entre las otras dos: que las rutas, los verbos
# y los nombres de campo coincidan. Nunca toca la base de produccion —se fabrica
# un SQLite temporal— y deja el servidor parado al terminar.
set -u
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUERTO="${PUERTO:-8099}"
TMP="$(mktemp -d)"
trap 'kill ${PID:-0} 2>/dev/null; rm -rf "$TMP"' EXIT

cd "$RAIZ"
export VAL_DATABASE_URL="sqlite:///$TMP/e2e.db"
export VAL_DATA_DIR="$TMP"

echo "── Preparando la base de pruebas en $TMP"
.venv/bin/python - <<'PY'
from app.db import Base, engine, SessionLocal
import app.models as M
from app.security import hash_pin
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    db.add(M.Operador(usuario="sup", nombre="Supervisora", email="sup@itsanet.com",
                      pin_hash=hash_pin("1111"), rol=M.Rol.SUPERVISOR))
    db.commit()
print("   ✓ base lista, con un supervisor de prueba")
PY

echo "── Levantando el servidor en el puerto $PUERTO"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PUERTO" --log-level warning &
PID=$!

for _ in $(seq 1 40); do
  curl -s -o /dev/null "http://127.0.0.1:$PUERTO/health" && break
  sleep 0.25
done
curl -s -o /dev/null "http://127.0.0.1:$PUERTO/health" || { echo "   ✗ no arrancó"; exit 1; }
echo "   ✓ responde"

echo "── La aplicación de los operarios contra él"
SERVIDOR="http://127.0.0.1:$PUERTO" node firebase/test/servidor.test.mjs
