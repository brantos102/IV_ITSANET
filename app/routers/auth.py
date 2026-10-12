"""Autenticacion y gestion de operadores."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SESSION_HOURS
from app.db import get_db
from app.models import Operador, Rol
from app.schemas import LoginIn, OperadorIn
from app.security import (
    COOKIE, cerrar_sesion, crear_sesion, hash_pin, requiere_supervisor,
    usuario_actual, verify_pin,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(datos: LoginIn, response: Response, db: Session = Depends(get_db)):
    op = db.execute(
        select(Operador).where(Operador.usuario == datos.usuario.strip().lower())
    ).scalar_one_or_none()
    if not op or not op.activo or not verify_pin(datos.pin, op.pin_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o PIN incorrecto")
    token = crear_sesion(db, op)
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_HOURS * 3600
    )
    return {"token": token, "operador": {"id": op.id, "nombre": op.nombre, "rol": op.rol.value}}


@router.post("/logout")
def logout(response: Response, request_token: str | None = None,
           op: Operador = Depends(usuario_actual), db: Session = Depends(get_db)):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/yo")
def yo(op: Operador = Depends(usuario_actual)):
    return {"id": op.id, "usuario": op.usuario, "nombre": op.nombre, "rol": op.rol.value}


@router.get("/operadores")
def listar(db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    ops = db.execute(select(Operador).order_by(Operador.nombre)).scalars().all()
    return [
        {"id": o.id, "usuario": o.usuario, "nombre": o.nombre,
         "rol": o.rol.value, "activo": o.activo}
        for o in ops
    ]


@router.post("/operadores", status_code=201)
def crear(datos: OperadorIn, db: Session = Depends(get_db),
          _: Operador = Depends(requiere_supervisor)):
    usuario = datos.usuario.strip().lower()
    if db.execute(select(Operador).where(Operador.usuario == usuario)).scalar_one_or_none():
        raise HTTPException(409, f"El usuario '{usuario}' ya existe")
    try:
        rol = Rol(datos.rol.upper())
    except ValueError:
        raise HTTPException(400, "Rol invalido") from None
    op = Operador(usuario=usuario, nombre=datos.nombre.strip(),
                  pin_hash=hash_pin(datos.pin), rol=rol)
    db.add(op)
    db.commit()
    return {"id": op.id, "usuario": op.usuario, "rol": op.rol.value}
