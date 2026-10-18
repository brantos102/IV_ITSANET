"""Autenticacion y gestion de operadores."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import SESSION_HOURS
from app.db import get_db
from app.models import AppPresencia, Operador, Rol, Sesion
from app.schemas import CambioClaveIn, LoginIn, OperadorCambio, OperadorIn, RegistroIn
from app.security import (
    COOKIE, cerrar_sesion, crear_sesion, hash_pin, requiere_supervisor,
    usuario_actual, verify_pin,
)
from app.services import ajustes

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(datos: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    entrada = datos.usuario.strip().lower()
    campo = func.lower(Operador.email) if "@" in entrada else func.lower(Operador.usuario)
    candidatos = db.scalars(select(Operador).where(campo == entrada).limit(2)).all()
    if len(candidatos) > 1:
        raise HTTPException(409, "Ese correo pertenece a varias fichas. Entra con tu usuario y avisa al supervisor.")
    op = candidatos[0] if candidatos else None
    if op:
        # Bloquear por PK únicamente esta cuenta: LOWER(usuario/email) puede
        # provocar un recorrido amplio en MySQL y bloquear otros operarios.
        op = db.scalar(select(Operador).where(Operador.id == op.id).with_for_update()
                       .execution_options(populate_existing=True))
    identificador = (op.email if "@" in entrada else op.usuario) if op else None
    if not op or (identificador or '').lower() != entrada or not verify_pin(datos.pin, op.pin_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contrasena incorrectos")
    if not op.activo:
        raise HTTPException(403, {"codigo": "PENDIENTE_APROBACION",
                                 "mensaje": "Tu cuenta esta desactivada o espera aprobacion de un supervisor."})
    token = crear_sesion(db, op)
    response.set_cookie(
        COOKIE, token, httponly=True, secure=request.url.scheme == "https", samesite="lax", max_age=SESSION_HOURS * 3600
    )
    return {"token": token, "operador": {"id": op.id, "nombre": op.nombre, "rol": op.rol.value}}


@router.post("/logout")
def logout(request: Request, response: Response,
           op: Operador = Depends(usuario_actual), db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if not token:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if token:
        import hashlib
        from app.models import AppPresencia
        db.query(AppPresencia).filter(AppPresencia.sesion_hash == hashlib.sha256(token.encode()).hexdigest()).delete()
        cerrar_sesion(db, token)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/yo")
def yo(op: Operador = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Quien esta dentro, en el vocabulario de la aplicacion de los operarios.

    `uid`, `email` y `tipoAcceso` estan porque es lo que las pantallas leen del
    perfil: las mismas que funcionaban contra Firebase tienen que funcionar aqui
    sin cambiar una linea. Aqui el identificador es el usuario, que es lo que
    firma los eventos cuando no hay correo.
    """
    return {
        "id": op.id,
        "uid": op.usuario,
        "usuario": op.usuario,
        "email": op.email or op.usuario,
        "nombre": op.nombre,
        "rol": op.rol.value,
        "activo": op.activo,
        "tipoAcceso": "CLAVE",
        'permisos': ajustes.permisos(db, op),
    }


@router.post("/clave")
def cambiar_clave(datos: CambioClaveIn, request: Request, op: Operador = Depends(usuario_actual),
                  db: Session = Depends(get_db)):
    """Cambiar la contrasena de uno mismo.

    Hace falta la actual: una sesion abierta en un handheld compartido que se
    quedo encima de una mesa no puede servir para dejar fuera a su dueno.
    """
    op = db.scalar(select(Operador).where(Operador.id == op.id).with_for_update()
                   .execution_options(populate_existing=True))
    if not verify_pin(datos.actual, op.pin_hash):
        raise HTTPException(401, {"codigo": "CLAVE_ACTUAL_INVALIDA",
                                  "mensaje": "La contraseña actual no es correcta. Revísala e intenta de nuevo."})
    if datos.actual == datos.nueva:
        raise HTTPException(422, "La contraseña nueva debe ser diferente de la actual")
    import hashlib
    token = request.cookies.get(COOKIE) or request.headers.get("Authorization", "").removeprefix("Bearer ")
    otras = db.query(Sesion).filter(Sesion.operador_id == op.id, Sesion.token != token).delete()
    db.query(AppPresencia).filter(AppPresencia.operador_id == op.id,
        AppPresencia.sesion_hash != hashlib.sha256(token.encode()).hexdigest()).delete()
    op.pin_hash = hash_pin(datos.nueva)
    ajustes.auditar(db, op.usuario, 'CAMBIO_CLAVE_PROPIA', op.id, {'sesionesCerradas': otras})
    db.commit()
    return {"ok": True, "sesionesCerradas": otras}


def _ficha(op: Operador) -> dict:
    return {"id": op.id, "uid": op.usuario, "usuario": op.usuario, "nombre": op.nombre,
            "email": op.email or "", "rol": op.rol.value, "activo": op.activo,
            "tipoAcceso": "CLAVE"}


@router.post('/operadores/{operador_id}/restablecer-clave')
def restablecer_clave(operador_id: int, datos: dict = Body(...), db: Session = Depends(get_db),
                     autor: Operador = Depends(usuario_actual)):
    if autor.rol != Rol.ADMIN:
        raise HTTPException(403, 'Solo ADMIN restablece la contraseña de otra cuenta.')
    op = db.scalar(select(Operador).where(Operador.id == operador_id).with_for_update())
    if not op: raise HTTPException(404, 'Usuario no encontrado')
    if op.id == autor.id:
        raise HTTPException(409, 'Cambia tu propia contraseña desde Mi cuenta con tu clave actual.')
    nueva = datos.get('nueva')
    if not isinstance(nueva, str) or not 6 <= len(nueva) <= 128:
        raise HTTPException(422, 'La contraseña nueva requiere de 6 a 128 caracteres.')
    op.pin_hash = hash_pin(nueva)
    cerradas = db.query(Sesion).filter(Sesion.operador_id == op.id).delete()
    db.query(AppPresencia).filter(AppPresencia.operador_id == op.id).delete()
    ajustes.auditar(db, autor.email or autor.usuario, 'CLAVE_RESTABLECIDA_ADMIN', op.id,
                   {'sesionesCerradas': cerradas})
    db.commit()
    return {'ok': True, 'sesionesCerradas': cerradas, 'mensaje': 'Contraseña reemplazada. Entrega la nueva clave por un canal privado; la anterior no se puede recuperar.'}


def _comprobar_duplicado(db: Session, usuario: str, email: str | None, excluir: int | None = None) -> None:
    consulta = select(Operador.id).where(func.lower(Operador.usuario) == usuario)
    if excluir is not None:
        consulta = consulta.where(Operador.id != excluir)
    if db.scalar(consulta) is not None:
        raise HTTPException(409, "Ese usuario ya existe. Elige otro.")
    correo = select(Operador.id).where(func.lower(Operador.email) == email)
    if excluir is not None:
        correo = correo.where(Operador.id != excluir)
    if email and db.scalar(correo) is not None:
        raise HTTPException(409, "Ese correo ya tiene una cuenta. Entra con ella o pide ayuda al supervisor.")


def _guardar(db: Session, op: Operador) -> dict:
    db.add(op)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese usuario ya existe. Elige otro.") from None
    return _ficha(op)


@router.post("/registro", status_code=201)
def registro(datos: RegistroIn, db: Session = Depends(get_db)):
    _comprobar_duplicado(db, datos.usuario, datos.email)
    op = Operador(usuario=datos.usuario, nombre=datos.nombre.strip(), email=datos.email,
                  pin_hash=hash_pin(datos.pin), rol=Rol.OPERADOR, activo=False)
    return _guardar(db, op)


@router.get("/operadores")
def listar(db: Session = Depends(get_db), _: Operador = Depends(ajustes.requiere('gestionarUsuarios'))):
    return [_ficha(op) for op in db.scalars(select(Operador).order_by(Operador.id))]


@router.post("/operadores", status_code=201)
def crear(datos: OperadorIn, db: Session = Depends(get_db),
          autor: Operador = Depends(ajustes.requiere('gestionarUsuarios'))):
    _comprobar_duplicado(db, datos.usuario, datos.email)
    try:
        rol = Rol(datos.rol.upper())
    except ValueError:
        raise HTTPException(400, "Rol invalido") from None
    if autor.rol != Rol.ADMIN and (rol == Rol.ADMIN or rol == Rol.SUPERVISOR and not ajustes.permisos(db, autor).get('asignarSupervisor')):
        raise HTTPException(403, "Solo un administrador asigna roles.")
    op = Operador(usuario=datos.usuario, nombre=datos.nombre.strip(), email=datos.email,
                  pin_hash=hash_pin(datos.pin), rol=rol, activo=True)
    ajustes.auditar(db, autor.email or autor.usuario, 'USUARIO_CREADO', datos.usuario, {'rol': rol.value})
    return _guardar(db, op)


@router.patch("/operadores/{operador_id}")
def actualizar(operador_id: int, datos: OperadorCambio, db: Session = Depends(get_db),
               autor: Operador = Depends(ajustes.requiere('gestionarUsuarios'))):
    op = db.get(Operador, operador_id)
    if op is None:
        raise HTTPException(404, "Usuario no encontrado")
    cambios = datos.model_dump(exclude_unset=True)
    if any(v is None for v in cambios.values()):
        raise HTTPException(422, "Los campos no pueden quedar vacios")
    if autor.rol != Rol.ADMIN and (op.rol == Rol.ADMIN or cambios.get('rol', '').upper() == 'ADMIN'
            or 'rol' in cambios and not ajustes.permisos(db, autor).get('asignarSupervisor')):
        raise HTTPException(403, "Solo un administrador modifica administradores o asigna roles.")
    if "rol" in cambios:
        try:
            cambios["rol"] = Rol(cambios["rol"].upper())
        except ValueError:
            raise HTTPException(400, "Rol invalido") from None
    if autor.id == op.id and (cambios.get("activo") is False or cambios.get("rol", op.rol) != op.rol):
        raise HTTPException(400, "No puedes desactivarte ni cambiar tu propio rol.")
    if "usuario" in cambios:
        _comprobar_duplicado(db, cambios["usuario"], None, excluir=op.id)
    if 'email' in cambios and autor.rol != Rol.ADMIN:
        raise HTTPException(403, 'Solo ADMIN vincula el correo responsable de Google')
    if 'email' in cambios:
        _comprobar_duplicado(db, op.usuario, cambios['email'], excluir=op.id)
    ajustes.auditar(db, autor.email or autor.usuario, 'USUARIO_ACTUALIZADO', op.usuario,
        {k: v.value if isinstance(v, Rol) else v for k, v in cambios.items()})
    for campo, valor in cambios.items():
        setattr(op, campo, valor)
    return _guardar(db, op)
