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
    from app.services.drive import carpeta_sku
    r=m.obtener(db,codigo)
    ingreso=db.scalar(select(AppIngreso).where(AppIngreso.recepcion==r.codigo).with_for_update().execution_options(populate_existing=True))
    skus=select(AppSku.sku).where(AppSku.recepcion==r.codigo)
    barras={}
    for b in db.scalars(select(ProductoCodigo).where(ProductoCodigo.sku.in_(skus),ProductoCodigo.exportar.is_(True))
            .order_by(ProductoCodigo.creado_en,ProductoCodigo.codigo).with_for_update()):
        barras[b.sku]=b.valor
    carpetas={};categorias={};pendientes=set()
    for j,e in db.execute(select(AppCopiaDrive,AppEvidencia).select_from(AppEvidencia).outerjoin(AppCopiaDrive,AppCopiaDrive.archivo_id==AppEvidencia.archivo_id)
            .where(AppEvidencia.recepcion==r.codigo,AppEvidencia.eliminado_en.is_(None)).with_for_update().execution_options(populate_existing=True)):
        if not e.sku:continue
        url=carpeta_sku(j,e)
        if url:
            carpetas.setdefault(e.sku,set()).add(url)
            categorias.setdefault(e.sku,{}).setdefault(e.categoria,set()).add(url)
        else:pendientes.add(e.archivo_id)
    from app.services.validacion_depot import validar
    validacion=validar(db,r.cliente,list(db.scalars(skus)))
    depot={sku:d['estado']=='OK' for sku,d in validacion['porSku'].items()}
    return {'marca':(ingreso.datos or {}).get('marca','') if ingreso else '', 'cliente':r.cliente,
        'columnas':ajustes.cliente(db,r.cliente)['columnas'],'barras':barras,'formatos':r.formatos or {},
        'evidenciasPendientes':len(pendientes),
        'versionFormatos':hashlib.sha256(json.dumps(r.formatos or {},sort_keys=True).encode()).hexdigest(),
        'depot':depot,'validacionDepot':validacion,'carpetasCategoria':{s:{c:sorted(us) for c,us in cs.items()} for s,cs in categorias.items()},
        'carpetas':{s:sorted(urls) for s,urls in carpetas.items()}}


def huella(db,r):
    eventos=list(db.scalars(select(AppEvento.id).where(AppEvento.recepcion==r.codigo).order_by(AppEvento.id).with_for_update()))
    d={'eventos':eventos,'formatos':r.formatos,'estado':r.estado,'metadatos':metadatos(db,r.codigo)}
    return hashlib.sha256(json.dumps(d,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def documento(f):
    return {'id':f.id,'numero':f.numero,'tipo':f.tipo,'estado':f.estado,'usuario':f.usuario,
        'creadoEn':m._iso(f.creado_en),'sufijo':f.datos.get('sufijo'),'archivos':f.datos.get('archivos',[]),
        'confirmadoEn':f.datos.get('confirmadoEn'),'destinatarios':f.datos.get('destinatarios'),
        'entregaId':f.datos.get('entregaId'),'descargas':f.datos.get('descargas',[]),'formato':f.datos.get('formato')}


def historial(db,codigo):
    r=m.obtener(db,codigo)
    return [documento(f) for f in db.scalars(select(AppInforme).where(AppInforme.recepcion==r.codigo)
        .order_by(AppInforme.numero.desc()).limit(100))]


def requiere_enlaces(meta):
    return any('evidencia' in (f.get('salida') if f.get('salida') is not None else
        {**f.get('columnas', {}), **meta['columnas']}) for f in meta['formatos'].values())


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
    if datos.get('reutilizarId'):
        if not ultimo or ultimo.id!=datos['reutilizarId'] or ultimo.usuario!=usuario:
            raise HTTPException(409,'Esta generación pertenece a otro supervisor o ya no es la más reciente.')
        if ultimo.estado!='GENERADO' or ultimo.huella!=huella(db,r) or ultimo.datos.get('formato')!=datos.get('formato'):
            raise HTTPException(409,'El informe anterior ya no corresponde a los datos actuales. Revisa y genera una nueva versión.')
        if datos.get('tipo')=='CORREO' and ultimo.tipo!='CORREO':
            raise HTTPException(409,'Este informe se preparó para descarga manual. Genera el informe de correo o conserva el envío manual.')
        return documento(ultimo)
    tipo=datos.get('tipo')
    if tipo not in ('DESCARGA','CORREO'):raise HTTPException(422,'Tipo de generación inválido')
    formato=datos.get('formato')
    if formato not in (None,'envio','envio-ampliado','auditable'):raise HTTPException(422,'Formato de informe inválido')
    meta=metadatos(db,r.codigo)
    if tipo=='CORREO':
        compartidos={s['sku'] for s in m.leer_coleccion(db,r.codigo,'skus',actual=True) if len(s.get('origenes',[]))>1}
        eventos=m.leer_coleccion(db,r.codigo,'eventos',actual=True)
        anulados={e.get('anulaA') for e in eventos if e['tipo']=='ANULACION'}
        pendientes={e['sku'] for e in eventos if e['sku'] in compartidos and e['id'] not in anulados
            and e['tipo']=='CONTEO' and e['cantidad']>0 and not e.get('origen')}
        if pendientes:raise HTTPException(409,'Asigna el packing list de los conteos anteriores antes de enviar. Usa Editar conteo para: '+', '.join(sorted(pendientes)[:10]))
    if tipo=='CORREO' and (formato=='envio-ampliado' or requiere_enlaces(meta)) and meta['evidenciasPendientes']:
        n = meta['evidenciasPendientes']
        raise HTTPException(409, {'codigo': 'EVIDENCIAS_PENDIENTES', 'pendientes': n,
            'mensaje': f'{n} foto(s) ya guardadas esperan confirmación de Drive. No necesitas tomarlas otra vez. Revisa las fotos pendientes o descarga un avance mientras se completa la copia.'})
    ahora=datetime.now(ZoneInfo('America/Guayaquil'))
    numero=ultimo.numero+1 if ultimo else 1
    f=AppInforme(id=uuid4().hex,clave=clave,recepcion=r.codigo,numero=numero,tipo=tipo,estado='RESERVADO',
        usuario=usuario,huella=huella(db,r),datos={'sufijo':f'_R{numero:04d}_{ahora:%Y%m%d-%H%M%S}','formato':formato})
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
    if f.datos.get('formato') in ('envio','envio-ampliado'):
        origenes=[l.get('origen') for l in libros]
        if len(origenes)!=len(set(origenes)) or set(origenes)!=set(r.origenes or []):
            raise HTTPException(422,'Se requiere exactamente un archivo por packing list, identificado con su origen.')
    guardados=[]
    for libro in libros:
        nombre=str(libro.get('nombre') or '')
        if not nombre.endswith(f.datos['sufijo']+'.xlsx'):raise HTTPException(422,'El nombre debe incluir la secuencia asignada')
        a=archivos.guardar(db,r.codigo,'informe',libro,usuario,confirmar=False)
        if a.nombre != nombre:
            raise HTTPException(409,'El contenido corresponde a una generación anterior. Vuelve a generar el libro con la secuencia actual.')
        guardados.append({'id':a.id,'nombre':a.nombre,'sha256':a.sha256,'origen':libro.get('origen'),'url':f'/api/operacion/informes/{f.id}/archivos/{a.id}'})
    f.estado='GENERADO';f.datos={**f.datos,'archivos':guardados}
    ajustes.auditar(db,usuario,'INFORME_GENERADO',r.codigo,{'informeId':f.id,'numero':f.numero,'archivos':guardados})
    db.commit();return documento(f)
