"""Evidencia del catálogo por cliente. Ausencia de stock no prueba ausencia del maestro."""
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from app.models import Producto, AppStockDepot, AppConfig
from app.services import app_modelo as m

NOTA_MAESTRO = ('No se adjunta la hoja MAESTRO del packing list. La columna de validación se calcula '
    'con el catálogo disponible en ITSANET, indicando su fuente y actualización, sin depender de '
    'fórmulas ni copiar el maestro completo en cada informe.')


def fecha_legible(valor):
    return datetime.fromisoformat(valor.replace('Z','+00:00')).astimezone(ZoneInfo('America/Guayaquil')).strftime('%d/%m/%Y %H:%M (Ecuador)') if valor else 'sin confirmar'


def validar(db, cliente, skus):
    nombres={str(cliente or '').strip().upper()}
    for config in db.scalars(select(AppConfig).where(AppConfig.clave.like('depot:%'))):
        if not config.datos.get('activo',True):continue
        alias={config.clave[6:].upper(),str(config.datos.get('cliente') or '').strip().upper()}
        if nombres.intersection(alias):nombres.update(alias)
    nombres.discard('')
    codigos=sorted(set(skus))
    productos={p.sku:p for p in db.scalars(select(Producto).where(Producto.sku.in_(codigos)))}
    stock={p.sku:p for p in db.scalars(select(AppStockDepot).where(AppStockDepot.sku.in_(codigos),AppStockDepot.cliente.in_(nombres)))}
    fuentes=list(db.execute(select(Producto.origen,func.max(Producto.actualizado_en)).where(
        Producto.cliente.in_(nombres),Producto.origen.in_(['API','MAESTRO'])).group_by(Producto.origen)))
    fecha_stock=db.scalar(select(func.max(AppStockDepot.actualizado_en)).where(AppStockDepot.cliente.in_(nombres)))
    fechas=[fecha for _,fecha in fuentes if fecha]+([fecha_stock] if fecha_stock else [])
    actualizado=max((m._iso(f) for f in fechas),default=None)
    api=fecha_stock is not None or any(origen=='API' for origen,_ in fuentes)
    maestro=any(origen=='MAESTRO' for origen,_ in fuentes)
    metodo=('Catálogo sincronizado mediante la API de stock de Depot. No es una consulta en vivo del maestro completo.' if api else
        'Catálogo importado del maestro de Depot.' if maestro else 'No hay catálogo de Depot confirmado para este cliente.')
    resultado={}
    for sku in codigos:
        p=productos.get(sku);propio=p is not None and p.cliente.strip().upper() in nombres
        confiable=propio and p.origen in ('API','MAESTRO')
        if confiable and p.inactivo:
            estado,valor,nota='INACTIVO','INACTIVO','Producto inactivo en el catálogo de Depot: solicitar revisión y habilitación antes de cargar cantidades en Depot.'
        elif confiable and not p.existe_depot:
            estado,valor,nota='NO_REGISTRADO','N/D','Producto marcado como no registrado en el catálogo de Depot: solicitar su creación antes de cargar cantidades en Depot.'
        elif (confiable and p.existe_depot) or sku in stock:
            estado,valor,nota='OK','ok','Producto encontrado para este cliente en el catálogo disponible de Depot.'
        elif p and not propio:
            estado,valor,nota='OTRO_CLIENTE','N/D','El código está asociado a otro cliente en el catálogo. Verificar su registro para el cliente de esta recepción antes de cargar cantidades en Depot.'
        elif fechas:
            estado,valor,nota='NO_ENCONTRADO','N/D','No encontrado en el catálogo consultado. Verificar en Depot y, si no está registrado, solicitar su creación antes de cargar cantidades en Depot.'
        else:
            estado,valor,nota='SIN_VALIDAR','PENDIENTE','Validación Depot pendiente: actualizar el catálogo de este cliente y volver a validar antes de cargar cantidades en Depot.'
        registro=stock.get(sku)
        fecha=m._iso(p.actualizado_en) if confiable else m._iso(registro.actualizado_en) if registro else actualizado
        fuente=p.origen if confiable else 'API' if registro else 'CATALOGO' if fechas else 'SIN_FUENTE'
        resultado[sku]={'estado':estado,'valor':valor,'observacion':'' if estado=='OK' else nota,
            'nota':nota+(' Ausencia en stock no confirma inexistencia en el maestro.' if estado=='NO_ENCONTRADO' else ''),'fuente':fuente,'actualizadoEn':fecha,'fechaActualizacion':fecha_legible(fecha)}
    return {'metodo':metodo,'actualizadoEn':actualizado,'fechaActualizacion':fecha_legible(actualizado),
        'notaMaestro':NOTA_MAESTRO,'porSku':resultado}
