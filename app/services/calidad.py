"""Unidades con incidencia: proyección del libro mayor, sin alterar el total físico."""
import math
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppCalidadSku, AppEvento
from app.services import ajustes

DIFERENCIAS={'OK','FALTANTE','SOBRANTE'}


def validar(db,p,cantidad):
    filas=p.get('incidencias')
    if filas is None:
        filas=[{'tipo':'MAL_ESTADO','cantidad':cantidad,'pnc':True}] if p.get('estadoFisico')=='PNC' and cantidad else []
    if not isinstance(filas,list) or len(filas)>20:raise HTTPException(422,'Incidencias inválidas')
    tipos={i['codigo']:i for i in ajustes.configuracion(db)['incidencias']}
    salida=[]
    for f in filas:
        if not isinstance(f,dict) or f.get('tipo') not in tipos or not tipos[f['tipo']]['activo']:raise HTTPException(422,'Tipo de incidencia no habilitado')
        t=tipos[f['tipo']]
        if f['tipo'] in DIFERENCIAS:raise HTTPException(422,'Faltantes y sobrantes se calculan con lo declarado y contado')
        n=f.get('cantidad');pnc=f.get('pnc',t['pnc'])
        if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or n<=0 or type(pnc)is not bool:
            raise HTTPException(422,'Indica una cantidad positiva por incidencia')
        detalle={'tipo':f['tipo'],'cantidad':n,'pnc':pnc,'nombre':t['nombre']}
        if 'pallet' in f:
            from app.services.app_modelo import normalizar_pallet
            import re
            pallet=normalizar_pallet(f['pallet'])
            if not re.fullmatch(r'[A-Z0-9]+(?:\.[A-Z0-9]+)*',pallet) or len(pallet)>40:raise HTTPException(422,'Indica el pallet específico de la novedad, sin agrupar varios pallets.')
            principal=normalizar_pallet(p.get('pallet'))
            if principal and pallet not in principal.split('-'):raise HTTPException(422,'El pallet de la novedad debe pertenecer a este conteo. Registra por separado las unidades de otro pallet.')
            detalle['pallet']=pallet
        salida.append(detalle)
    if sum(f['cantidad'] for f in salida)>cantidad:raise HTTPException(422,'Las unidades con incidencia no pueden superar las contadas; cada unidad se clasifica una sola vez')
    return salida


def actualizar(db,s):
    db.flush()
    # Lecturas actuales tras bloquear la recepción: MySQL REPEATABLE READ puede
    # conservar una instantánea anterior al turno de otro operario.
    es=list(db.scalars(select(AppEvento).where(AppEvento.recepcion==s.recepcion,AppEvento.sku==s.sku).order_by(AppEvento.creado_en,AppEvento.id).with_for_update().execution_options(populate_existing=True)))
    anulados={e.anula_a for e in es if e.tipo=='ANULACION'}
    corregidos={e.datos['eventoId']:e.datos['incidencias'] for e in es if e.tipo=='CALIDAD' and e.id not in anulados and (e.datos or {}).get('eventoId')}
    grupos={};pnc=0;total=0
    for e in es:
        if e.id in anulados or e.anula_a or float(e.cantidad or 0)<=0:continue
        fs=corregidos.get(e.id,(e.datos or {}).get('incidencias'))
        if fs is None:fs=[{'tipo':'MAL_ESTADO','cantidad':float(e.cantidad),'pnc':True,'nombre':'PNC (registro anterior)'}] if (e.datos or {}).get('estadoFisico')=='PNC' else []
        for f in fs:
            n=float(f['cantidad']);total+=n;pnc+=n if f['pnc'] else 0
            g=grupos.setdefault(f['tipo'],{'tipo':f['tipo'],'nombre':f.get('nombre',f['tipo']),'cantidad':0,'pnc':0})
            g['cantidad']+=n;g['pnc']+=n if f['pnc'] else 0
            if f.get('pallet'):g.setdefault('pallets',{})[f['pallet']]=g.get('pallets',{}).get(f['pallet'],0)+n
    q=db.scalar(select(AppCalidadSku).where(AppCalidadSku.sku_id==s.id).with_for_update().execution_options(populate_existing=True)) or AppCalidadSku(sku_id=s.id)
    q.datos={'cantidadPnc':pnc,'cantidadConIncidencia':total,'incidencias':list(grupos.values())}
    db.add(q);s.calidad=q;s.tiene_pnc=pnc>0


def documento(s):
    d=dict(s.calidad.datos) if s.calidad else {'cantidadPnc':None if s.tiene_pnc else 0,'cantidadConIncidencia':None if s.tiene_pnc else 0,'incidencias':[]}
    d['cantidadConforme']=max(float(s.contado or 0)-d['cantidadPnc'],0) if d['cantidadPnc'] is not None else None
    return d
