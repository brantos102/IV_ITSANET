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


def _ctx(request: Request, op: Operador | None, **extra) -> dict:
    return {"request": request, "operador": op, **extra}


@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("recepciones.html", _ctx(request, op))


@router.get("/login", response_class=HTMLResponse)
def login(request: Request, op: Operador | None = Depends(usuario_opcional)):
    if op:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", _ctx(request, None))


@router.get("/recepciones/{recepcion_id}", response_class=HTMLResponse)
def recepcion(recepcion_id: int, request: Request, db: Session = Depends(get_db),
              op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    rec = db.get(Recepcion, recepcion_id)
    if not rec:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("recepcion.html", _ctx(request, op, rec=rec))


@router.get("/recepciones/{recepcion_id}/escanear", response_class=HTMLResponse)
def escanear(recepcion_id: int, request: Request, db: Session = Depends(get_db),
             op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    rec = db.get(Recepcion, recepcion_id)
    if not rec:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("escanear.html", _ctx(request, op, rec=rec))


@router.get("/kpi", response_class=HTMLResponse)
def kpi(request: Request, op: Operador | None = Depends(usuario_opcional)):
    if not op:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("kpi.html", _ctx(request, op))
