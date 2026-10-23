"""Búsqueda de todas las recepciones; métricas solo para la página visible."""
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
import re
import unicodedata
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppRecepcion,AppIngreso,AppEvento
from app.services import app_modelo as m


def normalizar(v):return ''.join(c for c in unicodedata.normalize('NFD',str(v or '')) if not unicodedata.combining(c)).casefold()


def buscar(db,*,usuario=None,texto='',estado='',desde=None,hasta=None,orden='RECIENTES',offset=0,limite=50):
    if estado and estado not in ('ABIERTA','EN_VALIDACION','CERRADA'):raise HTTPException(422,'Estado de recepción no válido.')
    if orden not in ('RECIENTES','ANTIGUAS','CODIGO'):raise HTTPException(422,'Orden no válido.')
    if desde and hasta and desde>hasta:raise HTTPException(422,'La fecha Desde debe ser anterior o igual a Hasta.')
    q=select(AppRecepcion.codigo,AppRecepcion.cliente,AppRecepcion.descripcion,AppRecepcion.origenes,
        AppRecepcion.creado_en,AppIngreso.datos['marca'].as_string().label('marca')).outerjoin(AppIngreso,AppIngreso.recepcion==AppRecepcion.codigo)
    if usuario:q=q.where(AppRecepcion.codigo.in_(select(AppEvento.recepcion).where(AppEvento.usuario==usuario)))
    if estado:q=q.where(AppRecepcion.estado==estado)
    zona=ZoneInfo('America/Guayaquil')
    def utc(d):return datetime.combine(d,time.min,zona).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
    if desde:q=q.where(AppRecepcion.creado_en>=utc(desde))
    if hasta:
        q=q.where(AppRecepcion.creado_en<=datetime.max) if hasta==datetime.max.date() else q.where(AppRecepcion.creado_en<utc(hasta)+timedelta(days=1))
    q=q.order_by(AppRecepcion.creado_en.asc() if orden=='ANTIGUAS' else AppRecepcion.creado_en.desc(),AppRecepcion.codigo)
    filas=list(db.execute(q));texto=normalizar(texto).strip()
    if texto:
        nombres=m.nombres_listas(db,[r.codigo for r in filas])
        filas=[r for r in filas if texto in normalizar(' '.join(str(v or '') for v in
            [r.codigo,r.cliente,r.marca,r.descripcion,*(r.origenes or []),*nombres.get(r.codigo,{}).values()]))]
    if orden=='CODIGO':
        filas.sort(key=lambda r:[(0,int(p)) if p.isdigit() else (1,normalizar(p)) for p in re.split(r'(\d+)',r.codigo)])
    total=len(filas);offset=min(offset,((total-1)//limite)*limite) if total else 0
    codigos=[r.codigo for r in filas[offset:offset+limite]]
    documentos={r['codigo']:r for r in m.listar_recepciones(db,len(codigos) or 1,codigos=codigos)}
    return {'recepciones':[documentos[c] for c in codigos],'total':total,'offset':offset,'limite':limite}
