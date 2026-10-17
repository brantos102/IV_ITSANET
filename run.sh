#!/usr/bin/env bash
# Arranque de ITSANET IMS en la red local de bodega.
set -euo pipefail
cd "$(dirname "$0")"
PUERTO="${PORT:-8000}"
echo "ITSANET IMS -> http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PUERTO}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PUERTO}" "$@"
