"""ITSANET IMS - Validacion fisica de recepciones.

Arranque:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import APP_NAME, APP_VERSION, BASE_DIR
from app.db import SessionLocal, init_db
from app.models import Operador, Rol
from app.routers import app_api, auth, catalogo, kpi, recepciones, scans, ui
from app.security import hash_pin
from app.services.validation import ErrorValidacion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("iv_itsanet")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Crea el esquema y el usuario inicial al arrancar."""
    init_db()
    with SessionLocal() as db:
        if db.execute(select(Operador).limit(1)).scalar_one_or_none() is None:
            db.add(Operador(
                usuario="admin", nombre="Administrador",
                pin_hash=hash_pin("1234"), rol=Rol.ADMIN,
            ))
            db.commit()
            log.warning("Usuario inicial creado: admin / PIN 1234 -- CAMBIELO.")
    log.info("%s v%s iniciado", APP_NAME, APP_VERSION)
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Validacion fisica de recepciones con trazabilidad por evento.",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

# La aplicación de validación completa, servida desde este mismo servidor.
#
# Es la que usan los operarios: el escáner, el informe con el formato del
# packing list, los duplicados, los CSV para Depot. Ocho mil líneas que ya
# funcionan y que NO se reescriben.
#
# Hoy sus datos siguen viniendo de Firestore, así que el handheld necesita
# internet igual que ahora. Lo que cambia es que se sirve desde la red local y
# bajo una sola dirección: la misma que seguirá valiendo cuando la capa de datos
# pase a hablar con este servidor. Los operarios no verán el cambio.
_APP_OPERARIOS = BASE_DIR / "firebase" / "public"
if _APP_OPERARIOS.is_dir():
    app.mount("/app", StaticFiles(directory=str(_APP_OPERARIOS), html=True), name="operarios")

app.include_router(ui.router)
app.include_router(auth.router)
app.include_router(recepciones.router)
app.include_router(scans.router)
app.include_router(catalogo.router)
app.include_router(kpi.router)
app.include_router(app_api.router)


@app.exception_handler(ErrorValidacion)
async def _error_validacion(_request: Request, exc: ErrorValidacion):
    return JSONResponse(status_code=400, content={"codigo": exc.codigo, "mensaje": str(exc)})


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION}
