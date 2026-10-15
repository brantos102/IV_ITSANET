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


# --------------------------------------------------------------------------- #
# Depot: el maestro directo del WMS, sin pasar por un Excel
# --------------------------------------------------------------------------- #
@router.get("/depot/probar")
def probar_depot(db: Session = Depends(get_db), _: Operador = Depends(requiere_supervisor)):
    """¿Valen las credenciales? Pide solo el token, no baja el inventario.

    Es la primera cosa que hay que poder contestar al instalar en un servidor
    nuevo, y la única que distingue tres cosas que desde fuera se parecen: que
    no haya credenciales puestas, que estén mal, y que el WMS no conteste.
    """
    api = depot_svc.DepotAPI.desde_db(db)
    if not api.configurada:
        return {"ok": False, "motivo": "SIN CREDENCIALES",
                "detalle": "Faltan DEPOT_USUARIO y DEPOT_CLAVE en /etc/iv-itsanet.env"}
    try:
        token = api.token(forzar=True)
    except depot_svc.DepotRechazado as exc:
        return {"ok": False, "motivo": "CREDENCIALES RECHAZADAS", "detalle": str(exc)}
    except depot_svc.DepotNoDisponible as exc:
        return {"ok": False, "motivo": "WMS NO RESPONDE", "detalle": str(exc)}
    # El token no se devuelve nunca: con él se consulta el inventario entero.
    return {"ok": True, "motivo": "TOKEN OBTENIDO", "largo_token": len(token),
            "base_url": api.base_url}


@router.post("/depot/sincronizar")
def sincronizar_depot(
    cliente: str | None = None,
    db: Session = Depends(get_db),
    _: Operador = Depends(requiere_supervisor),
):
    """Baja el maestro de productos desde Depot y actualiza el espejo local.

    Lo que antes exigía exportar un Excel del WMS y subirlo a mano. El Excel
    sigue valiendo —no se quita nada— pero ya no es el único camino.
    """
    try:
        from app.services.integraciones import credenciales
        registros = credenciales(db)
        if not registros:
            return depot_svc.sincronizar_maestro(db, cliente=cliente)
        resultados, errores = [], []
        for c in registros:
            try:
                resultados.append(depot_svc.sincronizar_maestro(db, api=depot_svc.DepotAPI.desde_db(db, c['id']), cliente=cliente, evitar_conflictos=True))
            except (depot_svc.DepotRechazado, depot_svc.DepotNoDisponible):
                db.rollback()
                errores.append(c['id'])
        if not resultados:
            raise HTTPException(503, 'Ningun cliente respondio. Revisa las conexiones en Administracion')
        return {'productos': sum(r['productos'] for r in resultados), 'clientes': len(resultados), 'errores': errores, 'ambiguos': sorted({sku for r in resultados for sku in r.get('ambiguos', [])})}
    except depot_svc.DepotRechazado as exc:
        raise HTTPException(502, f"Depot rechazó las credenciales: {exc}") from exc
    except depot_svc.DepotNoDisponible as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/depot/clientes")
def clientes_depot(db: Session = Depends(get_db), _: Operador = Depends(usuario_actual)):
    """De qué clientes hay data en el espejo, y de cuándo.

    Con una sola credencial el WMS puede devolver varios clientes. Esto no lo
    adivina: cuenta lo que vino.
    """
    return {"clientes": depot_svc.clientes_en_espejo(db)}
