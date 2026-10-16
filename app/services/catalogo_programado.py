"""Stock por cliente/posición y sincronización con arrendamiento persistente."""
import asyncio
from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import AppConfig, AppStockDepot, utcnow
from app.services import operacion

log = logging.getLogger(__name__)


def guardar_posiciones(db, filas, cliente=None):
    grupos = {}
    for f in filas:
        c = str(f.get('cliente') or cliente or '').upper()[:60]
        grupos.setdefault((f['sku'], c), []).append({
            'posicion': f.get('posicion') or '', 'stock': f.get('stock', 0),
            'lote': f.get('lote'), 'serie': f.get('serie'), 'partida': f.get('partida'),
            'estado': f.get('estado_mercaderia'), 'cliente': c})
    ahora = utcnow()
    clientes = {c for _, c in grupos}
    if cliente: clientes.add(cliente.upper()[:60])
    # Solo clientes confirmados por esta respuesta; nunca vaciar otros clientes.
    if clientes:
        db.execute(update(AppStockDepot).where(AppStockDepot.cliente.in_(clientes))
            .values(posiciones=[], actualizado_en=ahora))
    registros = [{'sku': sku, 'cliente': c, 'posiciones': ps, 'actualizado_en': ahora}
                 for (sku, c), ps in grupos.items()]
    dialecto = db.get_bind().dialect.name
    if dialecto == 'mysql':
        from sqlalchemy.dialects.mysql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    for i in range(0, len(registros), 1000):
        s = insert(AppStockDepot).values(registros[i:i+1000])
        if dialecto == 'mysql':
            s = s.on_duplicate_key_update(posiciones=s.inserted.posiciones, actualizado_en=s.inserted.actualizado_en)
        else:
            s = s.on_conflict_do_update(index_elements=['sku', 'cliente'],
                set_={'posiciones': s.excluded.posiciones, 'actualizado_en': s.excluded.actualizado_en})
        db.execute(s)


def posiciones_de(db, sku, cliente=None):
    q = select(AppStockDepot).where(AppStockDepot.sku == sku)
    if cliente:
        from app.services.integraciones import credenciales
        nombres = {cliente.upper()}
        for c in credenciales(db):
            if cliente.upper() in (c['id'].upper(), c['cliente'].upper()):
                nombres.update([c['id'].upper(), c['cliente'].upper()])
        q = q.where(AppStockDepot.cliente.in_(nombres))
    filas = list(db.scalars(q))
    if not filas or (not cliente and len(filas) > 1):
        return {'posiciones': [], 'stock': None, 'stockDisponible': False, 'actualizadoStock': None}
    ps = [p for f in filas for p in f.posiciones if p.get('posicion')]
    return {'posiciones': ps, 'stock': sum(p.get('stock', 0) for f in filas for p in f.posiciones),
        'cliente': cliente or filas[0].cliente, 'stockDisponible': True,
        'actualizadoStock': operacion.m._iso(max(f.actualizado_en for f in filas))}


def turno_pendiente(ahora, configuracion):
    if not configuracion.get('activo'): return None
    local = ahora.astimezone(ZoneInfo(configuracion['zona']))
    horas = [h for h in configuracion['horas'] if h <= local.hour]
    return f'catalogo:{local.date().isoformat()}:{max(horas):02d}' if horas else None


def sincronizar_turno(ahora=None):
    from app.services import depot
    from app.services.integraciones import credenciales
    ahora = ahora or utcnow()
    with SessionLocal() as db:
        c = operacion.configuracion(db)['catalogo']
        clave = turno_pendiente(ahora, c)
        if not clave: return False
        registros = credenciales(db)
        apis = [depot.DepotAPI.desde_db(db, p['id']) for p in registros] if registros else [depot.DepotAPI()]
        apis = [a for a in apis if a and a.configurada]
        if not apis: return False
        t = db.get(AppConfig, clave)
        if t and (t.datos.get('estado') == 'COMPLETADA' or t.datos.get('hasta', '') > ahora.isoformat()):
            return False
        if not t:
            t = AppConfig(clave=clave, datos={})
            db.add(t)
            try: db.flush()
            except IntegrityError:
                db.rollback(); return False
        else:
            t = db.scalar(select(AppConfig).where(AppConfig.clave == clave).with_for_update().execution_options(populate_existing=True))
            if t.datos.get('estado') == 'COMPLETADA' or t.datos.get('hasta', '') > ahora.isoformat(): return False
        t.datos = {'estado': 'PROCESANDO', 'hasta': (ahora + timedelta(minutes=15)).isoformat()}
        db.commit()
        errores, total = [], 0
        for i, api in enumerate(apis):
            try:
                r = depot.sincronizar_maestro(db, api=api, evitar_conflictos=True)
                total += r['productos']
            except Exception:
                db.rollback(); errores.append(i)
        t = db.get(AppConfig, clave)
        t.datos = {'estado': 'PENDIENTE' if errores else 'COMPLETADA', 'productos': total,
            'clientesConError': len(errores), 'hasta': (ahora + timedelta(minutes=15)).isoformat() if errores else '',
            'ejecutadoEn': utcnow().isoformat()}
        db.commit()
        return True


async def trabajador():
    from app.services.drive import procesar_uno
    siguiente_catalogo = 0.0
    while True:
        try:
            ocupado = await asyncio.to_thread(procesar_uno)
            reloj = asyncio.get_running_loop().time()
            if reloj >= siguiente_catalogo:
                await asyncio.to_thread(sincronizar_turno)
                siguiente_catalogo = reloj + 30
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning('Revisión de tareas operativas pendiente; se reintentará')
            ocupado = False
        await asyncio.sleep(1 if ocupado else 10)
