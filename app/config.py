"""Configuracion central de la aplicacion (todo por variables de entorno)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("VAL_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
PHOTO_DIR = DATA_DIR / "fotos"

for _d in (DATA_DIR, UPLOAD_DIR, EXPORT_DIR, PHOTO_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# SQLite por defecto (WAL): no hay nada que instalar y para una maquina sobra.
#
# En el servidor de la empresa, MySQL:
#   VAL_DATABASE_URL=mysql+pymysql://itsanet:CLAVE@127.0.0.1:3306/iv_itsanet?charset=utf8mb4
#
# El ?charset=utf8mb4 no es opcional: sin el, MySQL negocia latin1 y las tildes
# y las enes de las descripciones se guardan rotas. Los pasos completos estan en
# docs/MYSQL.md.
DATABASE_URL = os.getenv("VAL_DATABASE_URL", f"sqlite:///{DATA_DIR / 'itsanet.db'}")

# Reciclar las conexiones antes de que MySQL las cierre por su cuenta
# (wait_timeout, 8 h por defecto). Una hora deja margen de sobra.
DB_POOL_RECYCLE = int(os.getenv("VAL_DB_POOL_RECYCLE", "3600"))
# Un handheld por operario mas la pantalla del supervisor: cinco conexiones
# fijas y otras cinco de desahogo cubren un turno entero.
DB_POOL_SIZE = int(os.getenv("VAL_DB_POOL_SIZE", "5"))

SECRET_KEY = os.getenv("VAL_SECRET_KEY", "cambiar-esta-clave-en-produccion")
SESSION_HOURS = int(os.getenv("VAL_SESSION_HOURS", "12"))

# --- Integracion sistema Depot -------------------------------------------------
DEPOT_BASE_URL = os.getenv("DEPOT_BASE_URL", "").rstrip("/")
DEPOT_TOKEN = os.getenv("DEPOT_TOKEN", "")
DEPOT_CLIENTE = os.getenv("DEPOT_CLIENTE", "VENTURA")
DEPOT_TIMEOUT = float(os.getenv("DEPOT_TIMEOUT", "6"))
DEPOT_CACHE_TTL = int(os.getenv("DEPOT_CACHE_TTL", "86400"))  # segundos
DEPOT_ENABLED = bool(DEPOT_BASE_URL)

# --- Reglas de negocio (flujo de validacion fisica) ---------------------------
# Regla del diagrama: "No caracteres especiales" en las celdas exportadas.
SANITIZE_EXPORT = os.getenv("VAL_SANITIZE_EXPORT", "1") == "1"
# Regla: "No anadir filas" -> los sobrantes de SKU fuera del packing list
# se agregan SIEMPRE al final, nunca intercalados.
SOBRANTES_AL_FINAL = os.getenv("VAL_SOBRANTES_AL_FINAL", "1") == "1"
# Regla: "1 SKU en dos pallets se puede misma celda"
PALLET_SEPARADOR = os.getenv("VAL_PALLET_SEPARADOR", " / ")

APP_NAME = "ITSANET IMS"
APP_VERSION = "1.0.0"
