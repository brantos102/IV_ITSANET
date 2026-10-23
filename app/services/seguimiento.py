"""Avance agregado y presencia reciente; los autores históricos no son usuarios conectados."""
from datetime import timedelta
from sqlalchemy import select, func, case
from app.models import AppSku, AppPresencia, Operador, utcnow


def resumenes(db, codigos):
    if not codigos:return {}
    q=select(AppSku.recepcion,func.count(),func.sum(AppSku.contado),
        func.sum(case((AppSku.verificado.is_(True),1),else_=0)),func.sum(AppSku.esperado)).where(
        AppSku.recepcion.in_(codigos)).group_by(AppSku.recepcion)
    salida={c:{'seguimiento':{'referencias':n,'contado':float(f or 0),'verificadas':int(v or 0),
        'declarado':float(e or 0),'avance':round(100*int(v or 0)/n) if n else 0},'equipoActivo':[]} for c,n,f,v,e in db.execute(q)}
    recientes=select(AppPresencia,Operador).join(Operador,Operador.id==AppPresencia.operador_id).where(
        AppPresencia.recepcion.in_(codigos),AppPresencia.visto_en>=utcnow().replace(tzinfo=None)-timedelta(seconds=120),Operador.activo.is_(True))
    vistos=set()
    for p,o in db.execute(recientes):
        if (p.recepcion,o.id) in vistos:continue
        vistos.add((p.recepcion,o.id))
        d=salida.setdefault(p.recepcion,{'equipoActivo':[]})
        d['equipoActivo'].append({'usuario':o.usuario,'nombre':o.nombre,'rol':o.rol.value,
            'actividad':p.actividad,'vistoEn':p.visto_en.isoformat()+'Z'})
    return salida
