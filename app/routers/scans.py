"""Escaneo y conteo fisico: el corazon operativo de la app."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Operador, Recepcion, ScanEvent, TipoEvento
from app.schemas import AjusteIn, AnularIn, LookupIn, ScanIn
from app.security import requiere_supervisor, usuario_actual
from app.services import validation as val
from app.services.normalize import entero_si_aplica
from app.services.validation import ErrorValidacion

router = APIRouter(prefix="/api/recepciones/{recepcion_id}", tags=["escaneo"])

# Errores de negocio que el front debe tratar como confirmacion, no como fallo.
_CONFLICTO = {"CONFIRMAR_SOBRANTE", "RECEPCION_CERRADA", "YA_ANULADO", "YA_CERRADA"}


def _rec(db: Session, recepcion_id: int) -> Recepcion:
    rec = db.get(Recepcion, recepcion_id)
    if not rec:
        raise HTTPException(404, "Recepcion no encontrada")
    return rec


def _error(exc: ErrorValidacion):
    estado = 409 if exc.codigo in _CONFLICTO else 400
    return HTTPException(estado, detail={"codigo": exc.codigo, "mensaje": str(exc)})


@router.post("/lookup")
def lookup(recepcion_id: int, datos: LookupIn, db: Session = Depends(get_db),
           _: Operador = Depends(usuario_actual)):
    """Paso 1 del escaneo: valida existencia en Depot y sugiere el pallet."""
    try:
        return val.lookup(db, _rec(db, recepcion_id), datos.codigo).to_dict()
    except ErrorValidacion as exc:
        raise _error(exc) from exc


@router.post("/scans", status_code=201)
def crear_scan(recepcion_id: int, datos: ScanIn, db: Session = Depends(get_db),
               op: Operador = Depends(usuario_actual)):
    """Paso 2: registra la cantidad fisica encontrada (INSERT en el libro mayor)."""
    try:
        return val.registrar_scan(
            db, _rec(db, recepcion_id), op,
            codigo=datos.codigo, cantidad=datos.cantidad, pallet=datos.pallet,
            estado_fisico=datos.estado_fisico, ean=datos.ean,
            observacion=datos.observacion, confirmar_sobrante=datos.confirmar_sobrante,
            idempotency_key=datos.idempotency_key, dispositivo=datos.dispositivo,
        )
    except ErrorValidacion as exc:
        raise _error(exc) from exc


@router.post("/ajustes", status_code=201)
def crear_ajuste(recepcion_id: int, datos: AjusteIn, db: Session = Depends(get_db),
                 op: Operador = Depends(requiere_supervisor)):
    """Ajuste manual (+/-) de supervisor. Queda registrado como evento aparte."""
    try:
        return val.registrar_scan(
            db, _rec(db, recepcion_id), op,
            codigo=datos.codigo, cantidad=datos.cantidad, pallet=datos.pallet,
            observacion=f"AJUSTE: {datos.motivo}", tipo=TipoEvento.AJUSTE,
            confirmar_sobrante=True,
        )
    except ErrorValidacion as exc:
        raise _error(exc) from exc


@router.post("/scans/{evento_id}/anular")
def anular(recepcion_id: int, evento_id: int, datos: AnularIn,
           db: Session = Depends(get_db), op: Operador = Depends(usuario_actual)):
    """Reversa un conteo. El evento original nunca se borra."""
    rec = _rec(db, recepcion_id)
    evento = db.get(ScanEvent, evento_id)
    if evento and evento.operador_id != op.id and not op.es_supervisor:
        raise HTTPException(403, "Solo un supervisor puede anular conteos de otro operador")
    try:
        return val.anular_scan(db, rec, op, evento_id, datos.motivo)
    except ErrorValidacion as exc:
        raise _error(exc) from exc


@router.get("/scans")
def listar_scans(recepcion_id: int, sku: str | None = None, pallet: str | None = None,
                 limite: int = 200, db: Session = Depends(get_db),
                 _: Operador = Depends(usuario_actual)):
    from app.services.normalize import normalizar_pallet, normalizar_sku

    q = select(ScanEvent).where(ScanEvent.recepcion_id == recepcion_id)
    if sku:
        q = q.where(ScanEvent.sku == normalizar_sku(sku))
    if pallet:
        q = q.where(ScanEvent.pallet == normalizar_pallet(pallet))
    filas = db.execute(q.order_by(ScanEvent.creado_en.desc()).limit(limite)).scalars().all()
    return [
        {
            "id": e.id, "sku": e.sku, "pallet": e.pallet,
            "cantidad": entero_si_aplica(e.cantidad),
            "estado_fisico": e.estado_fisico.value, "tipo": e.tipo.value,
            "observacion": e.observacion, "ean": e.ean,
            "operador": e.operador.nombre if e.operador else None,
            "anulado": bool(
                db.scalar(select(ScanEvent.id).where(ScanEvent.evento_ref_id == e.id))
            ),
            "hora": e.creado_en.isoformat(),
        }
        for e in filas
    ]


@router.get("/sku/{sku}")
def detalle_sku(recepcion_id: int, sku: str, db: Session = Depends(get_db),
                _: Operador = Depends(usuario_actual)):
    """Estado de un SKU: esperado, contado y en que pallets quedo."""
    try:
        return val.lookup(db, _rec(db, recepcion_id), sku).to_dict()
    except ErrorValidacion as exc:
        raise _error(exc) from exc
