"""Varios códigos de barras para un producto, sin crear otro SKU."""
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.models import Producto, ProductoCodigo
from app.services.normalize import limpiar, normalizar_sku


def buscar(db, codigo):
    normal = normalizar_sku(codigo)
    alias = db.get(ProductoCodigo, normal)
    productos = list(db.scalars(select(Producto).where(or_(
        Producto.sku == normal, Producto.ean.in_([normal, limpiar(codigo)]),
        Producto.codigo_alternativo == normal,
        Producto.sku == (alias.sku if alias else normal)))))
    if len(productos) > 1:
        raise HTTPException(409, 'El código corresponde a varios productos. Solicita revisión al supervisor.')
    return productos[0] if productos else None


def guardar(db, codigo, sku, usuario, confirmar=True, exportar=True):
    valor, normal = limpiar(codigo), normalizar_sku(codigo)
    sku = normalizar_sku(sku)
    if not valor or len(valor) > 80 or not normal or len(normal) > 80:
        raise HTTPException(422, 'Código de barras: entre 1 y 80 caracteres')
    prod = db.scalar(select(Producto).where(Producto.sku == sku).with_for_update())
    if prod is None:
        raise HTTPException(404, f'{sku} no está en el maestro local. No se creó ningún producto.')
    encontrado = buscar(db, normal)
    if encontrado and encontrado.sku != sku:
        raise HTTPException(409, f'El código de barras ya pertenece a {encontrado.sku}. No se reasignó.')
    existente = db.get(ProductoCodigo, normal)
    if existente:
        if exportar:
            existente.exportar = True
        if confirmar:
            db.commit()
        return existente
    nuevo = ProductoCodigo(codigo=normal, valor=valor, sku=sku, registrado_por=usuario, exportar=exportar)
    db.add(nuevo)
    try:
        db.flush()
        if confirmar:
            db.commit()
    except IntegrityError:
        db.rollback()
        # Carrera entre dos lectores: mismo destino es idempotente; otro, conflicto.
        existente = db.get(ProductoCodigo, normal)
        if confirmar and existente and existente.sku == sku:
            return existente
        raise HTTPException(409, 'El código cambió durante el registro. Actualiza y revisa su producto.') from None
    return nuevo
