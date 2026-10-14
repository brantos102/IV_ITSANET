"""Rutas que sirven la interfaz web (server-rendered + JS ligero)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_NAME, APP_VERSION, BASE_DIR
from app.db import get_db
from app.models import Operador, Recepcion
from app.security import usuario_opcional

router = APIRouter(tags=["ui"], include_in_schema=False)
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
templates.env.globals.update(APP_NAME=APP_NAME, APP_VERSION=APP_VERSION)


def _ctx(op: Operador | None, **extra) -> dict:
    """Lo que ve la plantilla.

    La peticion ya NO va aqui: desde Starlette 1.0 se pasa como primer
    argumento de TemplateResponse. Con la firma antigua
    —TemplateResponse(nombre, contexto)— la libreria toma el nombre por la
    peticion y el diccionario por el nombre de la plantilla, y responde un 500
    con «unhashable type: dict», que no se parece en nada a lo que pasa.
    """
    return {"operador": op, **extra}


@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "recepciones.html", _ctx(op))


@router.get("/login", response_class=HTMLResponse)
def login(request: Request, op: Operador | None = Depends(usuario_opcional)):
    if op:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", _ctx(None))


@router.get("/recepciones/{recepcion_id}", response_class=HTMLResponse)
def recepcion(recepcion_id: int, request: Request, db: Session = Depends(get_db),
              op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    rec = db.get(Recepcion, recepcion_id)
    if not rec:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "recepcion.html", _ctx(op, rec=rec))


@router.get("/recepciones/{recepcion_id}/escanear", response_class=HTMLResponse)
def escanear(recepcion_id: int, request: Request, db: Session = Depends(get_db),
             op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    rec = db.get(Recepcion, recepcion_id)
    if not rec:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "escanear.html", _ctx(op, rec=rec))


@router.get("/kpi", response_class=HTMLResponse)
def kpi(request: Request, op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "kpi.html", _ctx(op))
