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

# SQLite por defecto (WAL). Para Postgres: VAL_DATABASE_URL=postgresql+psycopg://...
DATABASE_URL = os.getenv("VAL_DATABASE_URL", f"sqlite:///{DATA_DIR / 'ventura.db'}")

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

APP_NAME = "VAL VENTURA"
APP_VERSION = "1.0.0"
