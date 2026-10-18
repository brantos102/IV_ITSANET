"""Cambios supervisados sin alterar informes emitidos ni perder líneas de origen."""
import hashlib
import json
import re
from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_
from app.models import AppRecepcion,AppLinea,AppSku,AppEvento,AppHuella,AppEvidencia,utcnow
from app.services import app_modelo as m,operacion,ajustes


def version(r):
    d={k:getattr(r,k) for k in ('cliente','descripcion','bultos','embarques','origenes','formatos','totales','estado')}
    return hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()


def obtener(db,codigo):
    r=m.obtener(db,codigo)
    return {**m.doc_recepcion(r),'versionEdicion':version(r)}


def bloquear(db,codigo,datos):
    r=m.obtener(db,codigo,bloquear=True)
    if r.estado not in m.ABIERTAS:raise HTTPException(409,'Reabre la recepción antes de editarla; sus informes emitidos se conservan.')
    if datos.get('version')!=version(r):raise HTTPException(409,'Otro supervisor cambió esta recepción. Actualiza antes de guardar.')
    return r


def editar(db,codigo,datos,usuario):
    r=bloquear(db,codigo,datos)
    descripcion=str(datos.get('descripcion') or '').strip()
    embarques=datos.get('embarques')
    if len(descripcion)>300 or not isinstance(embarques,list) or len(embarques)>100 or any(not isinstance(e,str) or not 1<=len(e.strip())<=80 for e in embarques):raise HTTPException(422,'Descripción: máximo 300 caracteres. Embarques: separa cada código con una coma (máximo 80 caracteres por código).')
    n=datos.get('bultos')
    if type(n)is not int or not 0<=n<=1000:raise HTTPException(422,'Bultos: indica un número entero de 0 a 1000.')
    anterior={'descripcion':r.descripcion,'embarques':r.embarques,'bultos':r.bultos}
    if n==0 and r.bultos:raise HTTPException(422,'Bultos: conserva al menos uno; usa Corregir total para revisar las unidades registradas.')
    if n!=(r.bultos or 0):operacion.ajustar_bultos(db,r.codigo,{'cantidad':n,'cantidadAnterior':r.bultos},usuario,confirmar=False)
    r.descripcion=descripcion;r.embarques=list(dict.fromkeys(e.strip().upper() for e in embarques))
    ajustes.auditar(db,usuario,'RECEPCION_EDITADA',codigo,{'antes':anterior,'despues':{'descripcion':descripcion,'embarques':r.embarques,'bultos':n}})
    db.commit();return obtener(db,codigo)


def retirar(db,codigo,origen,datos,usuario):
    r=bloquear(db,codigo,datos)
    if origen not in (r.origenes or []):raise HTTPException(404,'El embarque ya no está en esta recepción. Actualiza el listado.')
    motivo=str(datos.get('motivo') or '').strip()
    if not motivo:raise HTTPException(422,'Indica el motivo de retirar este embarque.')
    lineas=list(db.scalars(select(AppLinea).where(AppLinea.recepcion==codigo,AppLinea.origen==origen).with_for_update()))
    skus={l.sku for l in lineas}
    eventos=list(db.scalars(select(AppEvento).where(AppEvento.recepcion==codigo,AppEvento.sku.in_(skus)).with_for_update()))
    anulados={e.anula_a for e in eventos if e.tipo=='ANULACION'}
    activos=[e for e in eventos if e.tipo in ('CONTEO','CERO','NO_ENCONTRADO') and e.id not in anulados and (e.origen==origen or not e.origen)]
    if activos:raise HTTPException(409,'Este embarque tiene conteos vigentes: '+', '.join(sorted({e.sku for e in activos})[:10])+'. Abre Bitácora y corrige o anula esos conteos antes de retirarlo. Ningún registro fue eliminado.')
    otros_skus=set(db.scalars(select(AppLinea.sku).where(AppLinea.recepcion==codigo,AppLinea.origen!=origen)))
    exclusivos=skus-otros_skus
    evidencias=list(db.scalars(select(AppEvidencia.id).where(AppEvidencia.recepcion==codigo,or_(AppEvidencia.origen==origen,and_(AppEvidencia.sku.in_(exclusivos),or_(AppEvidencia.origen.is_(None),AppEvidencia.origen==''))),AppEvidencia.eliminado_en.is_(None))))
    if evidencias:raise HTTPException(409,f'Este embarque tiene {len(evidencias)} evidencias vinculadas. Abre las fotos y usa Editar vínculo para corregir el SKU o embarque antes de retirarlo; las imágenes se conservan.')
    nuevo=str(datos.get('nuevaRecepcion') or '').strip().upper()
    if nuevo and (len(nuevo)>100 or not re.fullmatch(r'[A-Z0-9][A-Z0-9_.-]*',nuevo)):raise HTTPException(422,'Nueva recepción: usa un código de hasta 100 letras, números, puntos o guiones.')
    if nuevo and db.get(AppRecepcion,nuevo):raise HTTPException(409,'Ya existe la recepción destino. Usa un código nuevo.')
    formato=(r.formatos or {}).get(m.clave_mapa(origen),{})
    archivo=[m.doc_linea(l) for l in lineas]
    if nuevo:
        destino=AppRecepcion(codigo=nuevo,cliente=r.cliente,descripcion='Embarque '+origen+' separado de '+codigo,bultos=0,estado='ABIERTA',creado_por=usuario,origenes=[origen],lineas_por_origen={m.clave_mapa(origen):len(lineas)},formatos={m.clave_mapa(origen):formato},embarques=sorted({str((l.extra or {}).get('embarque')) for l in lineas if (l.extra or {}).get('embarque')}),hoja=formato.get('hoja'),packing_list_en=utcnow())
        db.add(destino);db.flush()
        for i,l in enumerate(lineas):l.recepcion=nuevo;l.orden=i+1
        por_sku={}
        for l in lineas:por_sku[l.sku]=por_sku.get(l.sku,0)+float(l.cantidad)
        for sku,n in por_sku.items():db.add(AppSku(recepcion=nuevo,sku=sku,descripcion=next(l.descripcion for l in lineas if l.sku==sku),esperado=n,contado=0,verificado=False,en_packing_list=True,estado='PENDIENTE',origenes=[origen],esperado_por_origen={m.clave_mapa(origen):n},pallets={},por_origen={}))
        destino.totales={'lineas':len(lineas),'skus':len(por_sku),'unidades':sum(por_sku.values())}
    else:
        for l in lineas:db.delete(l)
    huella=db.scalar(select(AppHuella).where(AppHuella.recepcion==codigo,AppHuella.origen==origen))
    if huella:
        if nuevo:huella.id=f"{nuevo}__{m.clave_mapa(origen)}";huella.recepcion=nuevo;huella.codigo=nuevo
        else:db.delete(huella)
    r.origenes=[o for o in r.origenes if o!=origen];r.lineas_por_origen={k:v for k,v in (r.lineas_por_origen or {}).items() if k!=m.clave_mapa(origen)};r.formatos={k:v for k,v in (r.formatos or {}).items() if k!=m.clave_mapa(origen)}
    db.flush()
    restantes=list(db.scalars(select(AppLinea).where(AppLinea.recepcion==codigo)))
    por_sku={}
    for l in restantes:por_sku[l.sku]=por_sku.get(l.sku,0)+float(l.cantidad)
    for s in db.scalars(select(AppSku).where(AppSku.recepcion==codigo).with_for_update()):
        s.esperado=por_sku.get(s.sku,0);s.origenes=[o for o in (s.origenes or []) if o!=origen];s.esperado_por_origen={k:v for k,v in (s.esperado_por_origen or {}).items() if k!=m.clave_mapa(origen)};s.en_packing_list=s.sku in por_sku
        s.estado=m.estado_de(s.esperado,s.contado,s.verificado)
        if s.sku in skus and not s.en_packing_list and not s.contado:db.delete(s)
    r.totales={'lineas':len(restantes),'skus':len(por_sku),'unidades':sum(por_sku.values())}
    r.embarques=sorted({str((l.extra or {}).get('embarque')) for l in restantes if (l.extra or {}).get('embarque')})
    ajustes.auditar(db,usuario,'EMBARQUE_SEPARADO' if nuevo else 'EMBARQUE_RETIRADO',codigo,{'origen':origen,'destino':nuevo,'motivo':motivo[:300],'lineasOriginales':archivo,'formatoOriginal':formato})
    if nuevo:ajustes.auditar(db,usuario,'EMBARQUE_RECIBIDO',nuevo,{'origen':origen,'desde':codigo,'motivo':motivo[:300]})
    db.commit();return {'ok':True,'nuevaRecepcion':nuevo,'recepcion':obtener(db,codigo)}
