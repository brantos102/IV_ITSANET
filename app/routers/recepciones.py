"""Recepciones: alta, carga del packing list, consulta y cierre."""
from __future__ import annotations

import json
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.db import get_db
from app.models import (
    Auditoria, EstadoRecepcion, Operador, PackingItem, Pallet, Recepcion, ScanEvent,
    SkuPendiente, utcnow,
)
from app.schemas import MotivoIn, PendienteIn, RecepcionIn
from app.security import requiere_supervisor, usuario_actual
from app.services import validation as val
from app.services.exporter import exportar_packing_final
from app.services.importer import leer_packing_list
from app.services.normalize import entero_si_aplica, limpiar
from app.services.validation import ErrorValidacion

router = APIRouter(prefix="/api/recepciones", tags=["recepciones"])


def obtener(db: Session, recepcion_id: int) -> Recepcion:
    rec = db.get(Recepcion, recepcion_id)
    if not rec:
        raise HTTPException(404, "Recepcion no encontrada")
    return rec


@router.get("")
def listar(estado: str | None = None, db: Session = Depends(get_db),
           _: Operador = Depends(usuario_actual)):
    q = select(Recepcion).order_by(Recepcion.creado_en.desc())
    if estado:
        try:
            q = q.where(Recepcion.estado == EstadoRecepcion(estado.upper()))
        except ValueError:
            raise HTTPException(400, "Estado invalido") from None
    salida = []
    for r in db.execute(q).scalars().all():
        esp = val.esperado_por_sku(db, r.id)
        cont = val.contado_por_sku(db, r.id)
        te, tc = sum(esp.values()), sum(cont.values())
        salida.append({
            "id": r.id, "codigo": r.codigo, "cliente": r.cliente,
            "estado": r.estado.value, "creado_en": r.creado_en.isoformat(),
            "skus": len(esp), "unidades_sistema": entero_si_aplica(te),
            "unidades_fisicas": entero_si_aplica(tc),
            "avance_pct": round(100 * min(tc, te) / te, 1) if te else 0.0,
        })
    return salida


@router.post("", status_code=201)
def crear(datos: RecepcionIn, db: Session = Depends(get_db),
          op: Operador = Depends(usuario_actual)):
    codigo = limpiar(datos.codigo).upper()
    if db.execute(select(Recepcion).where(Recepcion.codigo == codigo)).scalar_one_or_none():
        raise HTTPException(409, f"Ya existe una recepcion con codigo '{codigo}'")
    rec = Recepcion(
        codigo=codigo, cliente=limpiar(datos.cliente).upper() or "VENTURA",
        descripcion=limpiar(datos.descripcion) or None,
        bultos_declarados=datos.bultos_declarados, creado_por_id=op.id,
    )
    db.add(rec)
    db.commit()
    return {"id": rec.id, "codigo": rec.codigo, "estado": rec.estado.value}


@router.post("/{recepcion_id}/packing-list")
async def cargar_packing_list(
    recepcion_id: int,
    archivo: UploadFile = File(...),
    hoja: str | None = Form(None),
    reemplazar: bool = Form(False),
    db: Session = Depends(get_db),
    op: Operador = Depends(usuario_actual),
):
    """Sube el packing list inicial. Es la version del sistema: se carga una sola vez."""
    rec = obtener(db, recepcion_id)
    if not rec.abierta:
        raise HTTPException(409, "La recepcion esta cerrada")

    existentes = db.scalar(
        select(PackingItem.id).where(PackingItem.recepcion_id == rec.id).limit(1)
    )
    if existentes and not reemplazar:
        raise HTTPException(
            409,
            "Esta recepcion ya tiene un packing list cargado. "
            "Use reemplazar=true (solo si aun no hay conteos).",
        )
    if existentes and reemplazar:
        hay_scans = db.scalar(
            select(ScanEvent.id).where(ScanEvent.recepcion_id == rec.id).limit(1)
        )
        if hay_scans:
            raise HTTPException(
                409, "No se puede reemplazar el packing list: ya existen conteos registrados."
            )
        db.query(PackingItem).filter(PackingItem.recepcion_id == rec.id).delete()

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = UPLOAD_DIR / f"{rec.codigo}_{marca}_{archivo.filename}"
    with destino.open("wb") as fh:
        shutil.copyfileobj(archivo.file, fh)

    try:
        res = leer_packing_list(destino, hoja)
    except Exception as exc:
        destino.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    for f in res.filas:
        db.add(PackingItem(
            recepcion_id=rec.id, linea=f.linea, sku=f.sku, descripcion=f.descripcion,
            referencia_pedido=f.referencia_pedido, factura=f.factura, cantidad=f.cantidad,
            precio_unit=f.precio_unit, precio_total=f.precio_total,
            num_pieza_reemplazo=f.num_pieza_reemplazo, embarque=f.embarque,
            extra=json.dumps(f.extra, ensure_ascii=False) if f.extra else None,
        ))
    rec.archivo_origen = destino.name
    rec.hash_archivo = res.hash_archivo
    db.add(Auditoria(
        recepcion_id=rec.id, operador_id=op.id, accion="CARGAR_PACKING_LIST",
        detalle=json.dumps({"archivo": destino.name, "lineas": res.total_lineas,
                            "hash": res.hash_archivo}),
    ))
    db.commit()

    return {
        "recepcion_id": rec.id, "hoja": res.hoja, "lineas": res.total_lineas,
        "skus_unicos": res.skus_unicos,
        "unidades": entero_si_aplica(res.total_unidades),
        "embarques": res.embarques, "filas_descartadas": res.descartadas,
        "advertencias": res.advertencias, "hash": res.hash_archivo,
    }


@router.get("/{recepcion_id}")
def detalle(recepcion_id: int, db: Session = Depends(get_db),
            _: Operador = Depends(usuario_actual)):
    return val.resumen_recepcion(db, obtener(db, recepcion_id))


@router.get("/{recepcion_id}/items")
def items(recepcion_id: int, db: Session = Depends(get_db),
          _: Operador = Depends(usuario_actual)):
    rec = obtener(db, recepcion_id)
    filas = db.execute(
        select(PackingItem).where(PackingItem.recepcion_id == rec.id)
        .order_by(PackingItem.linea)
    ).scalars().all()
    return [
        {"linea": i.linea, "sku": i.sku, "descripcion": i.descripcion,
         "cantidad": entero_si_aplica(i.cantidad), "embarque": i.embarque,
         "factura": i.factura, "referencia_pedido": i.referencia_pedido}
        for i in filas
    ]


@router.get("/{recepcion_id}/pallets")
def pallets(recepcion_id: int, db: Session = Depends(get_db),
            _: Operador = Depends(usuario_actual)):
    rec = obtener(db, recepcion_id)
    filas = db.execute(
        select(Pallet).where(Pallet.recepcion_id == rec.id).order_by(Pallet.codigo)
    ).scalars().all()
    salida = []
    for p in filas:
        total = db.scalar(
            select(__import__("sqlalchemy").func.sum(ScanEvent.cantidad)).where(
                ScanEvent.recepcion_id == rec.id, ScanEvent.pallet == p.codigo
            )
        ) or 0
        salida.append({
            "codigo": p.codigo, "padre": p.padre, "es_subpallet": p.es_subpallet,
            "unidades": entero_si_aplica(float(total)),
        })
    return salida


@router.get("/{recepcion_id}/pendientes")
def pendientes(recepcion_id: int, db: Session = Depends(get_db),
               _: Operador = Depends(usuario_actual)):
    rec = obtener(db, recepcion_id)
    filas = db.execute(
        select(SkuPendiente).where(SkuPendiente.recepcion_id == rec.id)
        .order_by(SkuPendiente.creado_en)
    ).scalars().all()
    return [
        {"id": p.id, "sku": p.sku, "descripcion": p.descripcion, "ean": p.ean,
         "estado": p.estado.value, "estado_depot": p.estado_depot.value,
         "candidatos": json.loads(p.candidatos) if p.candidatos else [],
         "notas": p.notas}
        for p in filas
    ]


@router.patch("/{recepcion_id}/pendientes/{pendiente_id}")
def actualizar_pendiente(recepcion_id: int, pendiente_id: int, datos: PendienteIn,
                         db: Session = Depends(get_db),
                         op: Operador = Depends(requiere_supervisor)):
    from app.models import EstadoCreacion
    from app.services.normalize import normalizar_ean

    p = db.get(SkuPendiente, pendiente_id)
    if not p or p.recepcion_id != recepcion_id:
        raise HTTPException(404, "Pendiente no encontrado")
    try:
        p.estado = EstadoCreacion(datos.estado.upper())
    except ValueError:
        raise HTTPException(400, "Estado invalido") from None
    if datos.ean:
        p.ean = normalizar_ean(datos.ean)
    if datos.notas is not None:
        p.notas = limpiar(datos.notas)[:300]
    if p.estado is EstadoCreacion.CREADO:
        p.resuelto_en = utcnow().replace(tzinfo=None)
        from app.models import Producto
        db.merge(Producto(
            sku=p.sku, cliente="VENTURA", descripcion=p.descripcion, ean=p.ean,
            existe_depot=True, origen="LOCAL",
            actualizado_en=utcnow().replace(tzinfo=None),
        ))
    db.add(Auditoria(recepcion_id=recepcion_id, operador_id=op.id,
                     accion="RESOLVER_SKU_PENDIENTE",
                     detalle=json.dumps({"sku": p.sku, "estado": p.estado.value})))
    db.commit()
    return {"id": p.id, "sku": p.sku, "estado": p.estado.value}


@router.post("/{recepcion_id}/cerrar")
def cerrar(recepcion_id: int, db: Session = Depends(get_db),
           op: Operador = Depends(requiere_supervisor)):
    rec = obtener(db, recepcion_id)
    try:
        return val.cerrar_recepcion(db, rec, op)
    except ErrorValidacion as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{recepcion_id}/reabrir")
def reabrir(recepcion_id: int, datos: MotivoIn, db: Session = Depends(get_db),
            op: Operador = Depends(requiere_supervisor)):
    rec = obtener(db, recepcion_id)
    try:
        val.reabrir_recepcion(db, rec, op, datos.motivo)
    except ErrorValidacion as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "estado": rec.estado.value}


@router.get("/{recepcion_id}/export")
def exportar(recepcion_id: int, db: Session = Depends(get_db),
             op: Operador = Depends(usuario_actual)):
    """Genera y descarga el PACKING LIST FINAL."""
    rec = obtener(db, recepcion_id)
    ruta = exportar_packing_final(db, rec)
    db.add(Auditoria(recepcion_id=rec.id, operador_id=op.id, accion="EXPORTAR_PACKING_FINAL",
                     detalle=json.dumps({"archivo": ruta.name})))
    db.commit()
    return FileResponse(
        ruta, filename=ruta.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/{recepcion_id}/auditoria")
def auditoria(recepcion_id: int, db: Session = Depends(get_db),
              _: Operador = Depends(requiere_supervisor)):
    filas = db.execute(
        select(Auditoria, Operador.nombre)
        .outerjoin(Operador, Operador.id == Auditoria.operador_id)
        .where(Auditoria.recepcion_id == recepcion_id)
        .order_by(Auditoria.creado_en.desc())
    ).all()
    return [
        {"accion": a.accion, "operador": nombre, "detalle": a.detalle,
         "fecha": a.creado_en.isoformat()}
        for a, nombre in filas
    ]
