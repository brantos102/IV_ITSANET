"""Autenticacion por usuario + PIN y control de roles.

PIN hasheado con PBKDF2-HMAC-SHA256 (stdlib, sin dependencias externas).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import SESSION_HOURS
from app.db import get_db
from app.models import Operador, Rol, Sesion, utcnow

_ITER = 120_000
COOKIE = "val_session"


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${dk.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        _, it, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), int(it))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def crear_sesion(db: Session, operador: Operador) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        Sesion(
            token=token,
            operador_id=operador.id,
            expira_en=utcnow().replace(tzinfo=None) + timedelta(hours=SESSION_HOURS),
        )
    )
    db.commit()
    return token


def cerrar_sesion(db: Session, token: str) -> None:
    db.query(Sesion).filter(Sesion.token == token).delete()
    db.commit()


def _operador_de_request(request: Request, db: Session) -> Operador | None:
    token = request.cookies.get(COOKIE)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    ses = db.get(Sesion, token)
    if not ses or ses.expira_en < utcnow().replace(tzinfo=None):
        return None
    op = db.get(Operador, ses.operador_id)
    return op if op and op.activo else None


def usuario_actual(request: Request, db: Session = Depends(get_db)) -> Operador:
    op = _operador_de_request(request, db)
    if not op:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesion no valida o expirada")
    return op


def usuario_opcional(request: Request, db: Session = Depends(get_db)) -> Operador | None:
    return _operador_de_request(request, db)


def requiere_supervisor(op: Operador = Depends(usuario_actual)) -> Operador:
    if op.rol not in (Rol.SUPERVISOR, Rol.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol SUPERVISOR o ADMIN")
    return op
