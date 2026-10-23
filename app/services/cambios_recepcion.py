"""Avisos de cambios confirmados: lecturas compartidas, sin reservas ni datos del conteo.

Cada proceso observa solo las recepciones con suscriptores. Las conexiones SSE
comparten una consulta por recepción; no mantienen una transacción abierta.
La firma persistida detecta también cambios realizados por otros workers.
"""
import asyncio
import hashlib
import json
import time
from contextlib import suppress
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import (AppRecepcion, AppEvento, AppSku, AppConfig, Operador,
                        AppEvidencia, AppCopiaDrive, AppAuditoriaGeneral)

INTERVALO = .75


def firma(valor):
    return hashlib.sha256(json.dumps(valor, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def equipo_sku(db, codigo):
    prefijo='sku:'+hashlib.sha256(codigo.encode()).hexdigest()[:12]+':' if codigo else 'sku:'
    ahora=time.time()
    filas=list(db.scalars(select(AppConfig).where(AppConfig.clave.like(prefijo+'%'),AppConfig.datos['vence'].as_float()>ahora)))
    ids={f.datos.get('operadorId') for f in filas if (f.datos or {}).get('vence',0)>ahora and f.datos.get('operadorId')}
    personas={p.id:p for p in db.execute(select(Operador.id,Operador.nombre,Operador.activo).where(Operador.id.in_(ids),Operador.activo.is_(True)))} if ids else {}
    salida=[]
    for f in filas:
        d=f.datos or {};persona=personas.get(d.get('operadorId'))
        if d.get('vence',0)<=ahora or not persona or not persona.activo:continue
        salida.append({'recepcion':d.get('recepcion',codigo),'sku':d.get('sku',''),'nombre':persona.nombre,'actividad':d.get('actividad','REVISANDO'),
                       'operadorId':persona.id,'dispositivo':d.get('dispositivo',f.clave)})
    return sorted(salida,key=lambda x:(x['sku'],x['nombre'],x['dispositivo']))


def leer_estado(codigo=''):
    """Una firma sin conteos, notas privadas, correo, tokens ni sesiones."""
    with SessionLocal() as db:
        if not codigo:
            # Agrupar por el índice recepción/fecha permite localizar incluso un
            # commit creado antes de la última fecha visible. No se leen JSON.
            eventos=list(db.execute(select(AppEvento.recepcion,func.count(AppEvento.id),func.max(AppEvento.creado_en)).group_by(AppEvento.recepcion)))
            versiones={r:firma([n,fecha]) for r,n,fecha in eventos}
            auditoria=list(db.execute(select(func.count(AppAuditoriaGeneral.id),func.max(AppAuditoriaGeneral.creado_en))).one())
            catalogo=list(db.execute(select(func.count(AppAuditoriaGeneral.id),func.max(AppAuditoriaGeneral.creado_en)).where(AppAuditoriaGeneral.accion=='CATALOGO_CARGADO')).one())
            equipo=equipo_sku(db,'')
            secciones={'operacion':firma([versiones,auditoria]),'catalogo':firma(catalogo),'presencia':firma(equipo)}
            return {'recepcion':'','recepciones':[],'versionesRecepcion':versiones,'revision':firma(secciones),'secciones':secciones,'equipoSku':equipo,'existe':True}
        r=db.get(AppRecepcion,codigo)
        if not r:return {'recepcion':codigo,'revision':firma(['eliminada',codigo]),'secciones':{'recepcion':'eliminada'},'equipoSku':[],'existe':False}
        ev=list(db.execute(select(func.count(AppEvento.id),func.max(AppEvento.creado_en)).where(AppEvento.recepcion==codigo)).one())
        sk=list(db.execute(select(func.count(AppSku.sku),func.max(AppSku.actualizado_en)).where(AppSku.recepcion==codigo)).one())
        fotos=list(db.execute(select(func.count(AppEvidencia.id),func.max(AppEvidencia.creado_en),func.max(AppEvidencia.eliminado_en)).where(AppEvidencia.recepcion==codigo)).one())
        copias=list(db.execute(select(AppCopiaDrive.archivo_id,AppCopiaDrive.estado,AppCopiaDrive.intentos).where(AppCopiaDrive.recepcion==codigo).order_by(AppCopiaDrive.archivo_id)))
        equipo=equipo_sku(db,codigo)
        secciones={'conteos':firma([ev,sk]),'recepcion':firma([r.estado,r.bultos,r.totales,r.origenes,r.lineas_por_origen,r.embarques,r.formatos,r.cliente,r.descripcion]),
                   'imagenes':firma([fotos,[list(x) for x in copias]]),'presencia':firma(equipo)}
        return {'recepcion':codigo,'revision':firma(secciones),'secciones':secciones,'equipoSku':equipo,'existe':True}


class Canal:
    """Un observador de BD para todos los navegadores de esta recepción."""
    def __init__(self,codigo):
        self.codigo=codigo;self.colas=set();self.ultimo=None;self.tarea=None

    async def observar(self):
        try:
            while self.colas:
                try:
                    estado=await asyncio.to_thread(leer_estado,self.codigo)
                    if not self.ultimo or estado['revision']!=self.ultimo['revision']:
                        anterior=(self.ultimo or {}).get('secciones',{})
                        aviso={**estado,'secciones':[k for k,v in estado['secciones'].items() if anterior.get(k)!=v]}
                        if not self.codigo:
                            anteriores=(self.ultimo or {}).get('versionesRecepcion',{})
                            actuales=estado.get('versionesRecepcion',{})
                            aviso['recepciones']=[r for r in set(anteriores)|set(actuales) if anteriores.get(r)!=actuales.get(r)]
                        self.ultimo=estado
                        for cola in list(self.colas):
                            pendiente=cola.get_nowait() if cola.full() else None
                            ultimo=aviso
                            if pendiente:
                                ultimo={**aviso,'secciones':sorted(set(pendiente['secciones'])|set(aviso['secciones']))}
                                if not self.codigo:ultimo['recepciones']=sorted(set(pendiente.get('recepciones',[]))|set(aviso.get('recepciones',[])))
                            cola.put_nowait(ultimo)
                except asyncio.CancelledError:raise
                except Exception:
                    # Cerrar provoca reconexión autenticada; el navegador conserva
                    # sus datos y activa la consulta de respaldo.
                    for cola in list(self.colas):
                        if cola.full():cola.get_nowait()
                        cola.put_nowait(None)
                    return
                await asyncio.sleep(INTERVALO)
        finally:
            if _canales.get(self.codigo) is self:_canales.pop(self.codigo,None)

    def suscribir(self):
        cola=asyncio.Queue(maxsize=1);self.colas.add(cola)
        if self.ultimo:cola.put_nowait({**self.ultimo,'secciones':list(self.ultimo['secciones'])})
        if not self.tarea or self.tarea.done():self.tarea=asyncio.create_task(self.observar())
        return cola

    async def retirar(self,cola):
        self.colas.discard(cola)
        if not self.colas and self.tarea:
            self.tarea.cancel()
            with suppress(asyncio.CancelledError):await self.tarea


_canales={}


def canal(codigo):
    actual=_canales.get(codigo)
    if not actual or actual.tarea and actual.tarea.done():
        actual=Canal(codigo);_canales[codigo]=actual
    return actual
