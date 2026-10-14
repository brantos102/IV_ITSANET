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
from app.routers import auth, catalogo, kpi, recepciones, scans, ui
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

app.include_router(ui.router)
app.include_router(auth.router)
app.include_router(recepciones.router)
app.include_router(scans.router)
app.include_router(catalogo.router)
app.include_router(kpi.router)


@app.exception_handler(ErrorValidacion)
async def _error_validacion(_request: Request, exc: ErrorValidacion):
    return JSONResponse(status_code=400, content={"codigo": exc.codigo, "mensaje": str(exc)})


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION}
