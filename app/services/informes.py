"""Generaciones numeradas e inmutables, separadas del acuse real del correo."""
import hashlib
import json
import re
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from app.models import (AppInforme,AppEvento,AppIngreso,AppCopiaDrive,AppEvidencia,
    ProductoCodigo,AppSku)
from app.services import app_modelo as m, ajustes, archivos


def metadatos(db,codigo):
    r=m.obtener(db,codigo)
    ingreso=db.scalar(select(AppIngreso).where(AppIngreso.recepcion==r.codigo).with_for_update().execution_options(populate_existing=True))
    skus=select(AppSku.sku).where(AppSku.recepcion==r.codigo)
    barras={}
    for b in db.scalars(select(ProductoCodigo).where(ProductoCodigo.sku.in_(skus),ProductoCodigo.exportar.is_(True))
            .order_by(ProductoCodigo.creado_en,ProductoCodigo.codigo).with_for_update()):
        barras[b.sku]=b.valor
    carpetas={};pendientes=set()
    for j,e in db.execute(select(AppCopiaDrive,AppEvidencia).select_from(AppEvidencia).outerjoin(AppCopiaDrive,AppCopiaDrive.archivo_id==AppEvidencia.archivo_id)
            .where(AppEvidencia.recepcion==r.codigo,AppEvidencia.eliminado_en.is_(None)).with_for_update().execution_options(populate_existing=True)):
        if not e.sku:continue
        url=(j.datos.get('carpetaSkuUrl') or j.datos.get('carpeta')) if j and j.estado=='COPIADA' else None
        if url:carpetas.setdefault(e.sku,set()).add(url)
        else:pendientes.add(e.archivo_id)
    return {'marca':(ingreso.datos or {}).get('marca','') if ingreso else '', 'cliente':r.cliente,
        'columnas':ajustes.cliente(db,r.cliente)['columnas'],'barras':barras,'formatos':r.formatos or {},
        'evidenciasPendientes':len(pendientes),
        'versionFormatos':hashlib.sha256(json.dumps(r.formatos or {},sort_keys=True).encode()).hexdigest(),
        'carpetas':{s:sorted(urls) for s,urls in carpetas.items()}}


def huella(db,r):
    eventos=list(db.scalars(select(AppEvento.id).where(AppEvento.recepcion==r.codigo).order_by(AppEvento.id).with_for_update()))
    d={'eventos':eventos,'formatos':r.formatos,'estado':r.estado,'metadatos':metadatos(db,r.codigo)}
    return hashlib.sha256(json.dumps(d,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def documento(f):
    return {'id':f.id,'numero':f.numero,'tipo':f.tipo,'estado':f.estado,'usuario':f.usuario,
        'creadoEn':m._iso(f.creado_en),'sufijo':f.datos.get('sufijo'),'archivos':f.datos.get('archivos',[]),
        'confirmadoEn':f.datos.get('confirmadoEn'),'destinatarios':f.datos.get('destinatarios'),
        'entregaId':f.datos.get('entregaId'),'descargas':f.datos.get('descargas',[])}


def historial(db,codigo):
    r=m.obtener(db,codigo)
    return [documento(f) for f in db.scalars(select(AppInforme).where(AppInforme.recepcion==r.codigo)
        .order_by(AppInforme.numero.desc()).limit(100))]


def reservar(db,codigo,datos,usuario):
    r=m.obtener(db,codigo,bloquear=True)
    clave=str(datos.get('clave') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',clave):raise HTTPException(422,'Identificador de generación inválido')
    anterior=db.scalar(select(AppInforme).where(AppInforme.clave==clave).with_for_update())
    if anterior:
        if anterior.recepcion!=r.codigo or anterior.usuario!=usuario:raise HTTPException(409,'El identificador corresponde a otra generación')
        return documento(anterior)
    ultimo=db.scalar(select(AppInforme).where(AppInforme.recepcion==r.codigo).order_by(AppInforme.numero.desc()).limit(1).with_for_update())
    if (ultimo.id if ultimo else None)!=datos.get('ultimoVisto'):
        raise HTTPException(409,'Otro supervisor generó un informe. Revisa el historial antes de continuar.')
    tipo=datos.get('tipo')
    if tipo not in ('DESCARGA','CORREO'):raise HTTPException(422,'Tipo de generación inválido')
    meta=metadatos(db,r.codigo)
    formatos=r.formatos or {}
    necesita_enlaces=any('evidencia' in (f.get('salida') if f.get('salida') is not None else {**f.get('columnas',{}),**meta['columnas']}) for f in formatos.values())
    if tipo=='CORREO' and necesita_enlaces and meta['evidenciasPendientes']:
        raise HTTPException(409,'La columna de evidencia requiere carpetas confirmadas: hay fotos pendientes de Drive. Puedes descargar un avance y continuar contando; finaliza cuando la copia esté confirmada.')
    ahora=datetime.now(ZoneInfo('America/Guayaquil'))
    numero=ultimo.numero+1 if ultimo else 1
    f=AppInforme(id=uuid4().hex,clave=clave,recepcion=r.codigo,numero=numero,tipo=tipo,estado='RESERVADO',
        usuario=usuario,huella=huella(db,r),datos={'sufijo':f'_R{numero:04d}_{ahora:%Y%m%d-%H%M%S}'})
    db.add(f);ajustes.auditar(db,usuario,'INFORME_RESERVADO',r.codigo,{'informeId':f.id,'numero':numero,'tipo':tipo});db.commit()
    return documento(f)


def archivar(db,codigo,ident,datos,usuario):
    r=m.obtener(db,codigo,bloquear=True)
    f=db.get(AppInforme,ident)
    if not f or f.recepcion!=r.codigo:raise HTTPException(404,'Informe no encontrado')
    if f.usuario!=usuario:raise HTTPException(403,'Esta generación pertenece a otro supervisor')
    if f.estado!='RESERVADO':return documento(f)
    if f.huella!=huella(db,r):raise HTTPException(409,'La recepción cambió mientras se preparaba el informe; genera una versión actualizada.')
    libros=datos.get('adjuntos')
    if not isinstance(libros,list) or not 1<=len(libros)<=30:raise HTTPException(422,'Se requiere un informe por packing list')
    guardados=[]
    for libro in libros:
        nombre=str(libro.get('nombre') or '')
        if not nombre.endswith(f.datos['sufijo']+'.xlsx'):raise HTTPException(422,'El nombre debe incluir la secuencia asignada')
        a=archivos.guardar(db,r.codigo,'informe',libro,usuario,confirmar=False)
        if a.nombre != nombre:
            raise HTTPException(409,'El contenido corresponde a una generación anterior. Vuelve a generar el libro con la secuencia actual.')
        guardados.append({'id':a.id,'nombre':a.nombre,'sha256':a.sha256,'url':f'/api/operacion/informes/{f.id}/archivos/{a.id}'})
    f.estado='GENERADO';f.datos={**f.datos,'archivos':guardados}
    ajustes.auditar(db,usuario,'INFORME_GENERADO',r.codigo,{'informeId':f.id,'numero':f.numero,'archivos':guardados})
    db.commit();return documento(f)
