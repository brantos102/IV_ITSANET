"""Catalogo de productos (espejo del maestro Depot)."""
from __future__ import annotations

import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.db import get_db
from app.models import Operador, Producto
from app.security import requiere_supervisor, usuario_actual
from app.services import depot as depot_svc
from app.services.importer import leer_maestro
from app.services.normalize import normalizar_sku

router = APIRouter(prefix="/api/catalogo", tags=["catalogo"])


@router.get("/estado")
def estado(db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    return depot_svc.estado_integracion(db)


@router.get("/buscar")
def buscar(q: str, limite: int = 20, db: Session = Depends(get_db),
           _: Operador = Depends(usuario_actual)):
    termino = normalizar_sku(q)
    if len(termino) < 3:
        raise HTTPException(400, "Ingrese al menos 3 caracteres")
    filas = db.execute(
        select(Producto)
        .where(or_(Producto.sku.like(f"{termino}%"), Producto.ean == termino))
        .limit(limite)
    ).scalars().all()
    return [
        {"sku": p.sku, "descripcion": p.descripcion, "ean": p.ean,
         "unidad": p.unidad, "inactivo": p.inactivo}
        for p in filas
    ]


@router.post("/maestro")
async def cargar_maestro(
    archivo: UploadFile = File(...),
    hoja: str | None = Form(None),
    db: Session = Depends(get_db),
    _: Operador = Depends(requiere_supervisor),
):
    """Carga/actualiza el espejo local del maestro de productos de Depot."""
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = UPLOAD_DIR / f"MAESTRO_{marca}_{archivo.filename}"
    with destino.open("wb") as fh:
        shutil.copyfileobj(archivo.file, fh)
    try:
        n = cargar_maestro_desde(db, destino, hoja)
    except Exception as exc:
        destino.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    total = db.scalar(select(func.count()).select_from(Producto)) or 0
    return {"procesados": n, "total_en_cache": total, "archivo": destino.name}


def cargar_maestro_desde(db: Session, ruta, hoja: str | None = None, lote: int = 2000) -> int:
    """Carga masiva con upsert por lotes. Reutilizable desde scripts."""
    from app.models import utcnow

    ahora = utcnow().replace(tzinfo=None)
    n = 0
    buffer = []
    for reg in leer_maestro(ruta, hoja):
        reg.update(existe_depot=True, origen="MAESTRO", actualizado_en=ahora)
        buffer.append(reg)
        if len(buffer) >= lote:
            _upsert(db, buffer)
            n += len(buffer)
            buffer.clear()
    if buffer:
        _upsert(db, buffer)
        n += len(buffer)
    db.commit()
    return n


def _upsert(db: Session, registros: list[dict]) -> None:
    # El maestro real trae SKU repetidos (distinta descripcion, mismo producto_id).
    # Dentro de un lote gana el ultimo: un INSERT con duplicados reventaria la PK.
    unicos: dict[str, dict] = {r["sku"]: r for r in registros}
    registros = list(unicos.values())

    existentes = {
        p
        for p in db.execute(
            select(Producto.sku).where(Producto.sku.in_(list(unicos)))
        ).scalars()
    }
    nuevos = [r for r in registros if r["sku"] not in existentes]
    viejos = [r for r in registros if r["sku"] in existentes]
    if nuevos:
        db.bulk_insert_mappings(Producto, nuevos)
    if viejos:
        db.bulk_update_mappings(Producto, viejos)
    db.flush()
