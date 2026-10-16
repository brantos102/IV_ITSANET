"""Políticas administrativas y coordinación de la operación actual."""
import hashlib
import re
from uuid import uuid4
from fastapi import APIRouter, Depends, Body, HTTPException, Request
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import AppPresencia, AppEvento, AppSku, utcnow
from app.security import usuario_actual, COOKIE
from app.routers.integraciones import admin
from app.services import ajustes, calidad, app_modelo as m

router=APIRouter(prefix='/api/operacion',tags=['gestion'])

@router.get('/politicas')
def politicas(db:Session=Depends(get_db),_=Depends(admin)):
    return {'acciones':ajustes.ACCIONES,**ajustes.configuracion(db)}

@router.put('/politicas')
def guardar(datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(admin)):
    return ajustes.guardar(db,datos,op.email or op.usuario)

@router.get('/reglas/{cliente}')
def reglas(cliente:str,db:Session=Depends(get_db),op=Depends(usuario_actual)):
    return {**ajustes.cliente(db,cliente),'incidencias':ajustes.configuracion(db)['incidencias']}

def token(request):
    return hashlib.sha256((request.cookies.get(COOKIE) or request.headers.get('Authorization','').removeprefix('Bearer ')).encode()).hexdigest()

@router.put('/recepciones/{codigo}/presencia')
def presencia(codigo:str,request:Request,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(usuario_actual)):
    r=m.obtener(db,codigo,bloquear=True)
    dispositivo=str(datos.get('dispositivo') or '')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',dispositivo):raise HTTPException(422,'Dispositivo inválido')
    p=db.get(AppPresencia,(r.codigo,dispositivo))
    if p and p.sesion_hash!=token(request):raise HTTPException(409,'Esta pestaña pertenece a otra sesión; recarga para identificarla')
    p=p or AppPresencia(recepcion=r.codigo,dispositivo=dispositivo)
    p.operador_id=op.id;p.sesion_hash=token(request);p.actividad=str(datos.get('actividad') or 'VALIDANDO')[:30];p.visto_en=utcnow().replace(tzinfo=None)
    db.add(p);db.commit();return {'ok':True}

@router.get('/recepciones/{codigo}/equipo')
def equipo(codigo:str,db:Session=Depends(get_db),_=Depends(ajustes.requiere('verEquipo'))):
    from app.services.seguimiento import resumenes
    r=m.obtener(db,codigo)
    return resumenes(db,[r.codigo]).get(r.codigo,{'equipoActivo':[]})

@router.post('/recepciones/{codigo}/eventos/{ident}/calidad')
def corregir_calidad(codigo:str,ident:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('cerrarRecepciones'))):
    r=m.obtener(db,codigo,bloquear=True)
    if r.estado not in m.ABIERTAS:raise HTTPException(409,'Reabre la recepción para corregir su clasificación')
    e=db.get(AppEvento,ident)
    if not e or e.recepcion!=r.codigo or float(e.cantidad or 0)<=0 or e.anula_a:raise HTTPException(422,'Elige un conteo físico activo')
    if db.scalar(select(AppEvento.id).where(AppEvento.anula_a==ident)):raise HTTPException(409,'El conteo está anulado')
    motivo=str(datos.get('motivo') or '').strip()
    if len(motivo)<3:raise HTTPException(422,'Indica el motivo de la corrección')
    filas=calidad.validar(db,datos,float(e.cantidad))
    db.add(AppEvento(id=uuid4().hex,recepcion=r.codigo,tipo='CALIDAD',sku=e.sku,cantidad=0,
        usuario=op.email or op.usuario,motivo=motivo[:300],datos={'eventoId':e.id,'incidencias':filas}))
    s=db.scalar(select(AppSku).where(AppSku.recepcion==r.codigo,AppSku.sku==e.sku).with_for_update())
    calidad.actualizar(db,s);db.commit();return m.doc_sku(s)

@router.get('/recepciones/{codigo}/informe-metadatos')
def metadatos_informe(codigo:str,db:Session=Depends(get_db),_=Depends(ajustes.requiere('exportarInformes'))):
    from app.services.informes import metadatos
    return metadatos(db,codigo)

@router.get('/recepciones/{codigo}/informes')
def historial_informes(codigo:str,db:Session=Depends(get_db),_=Depends(ajustes.requiere('exportarInformes'))):
    from app.services.informes import historial
    return historial(db,codigo)

@router.post('/recepciones/{codigo}/informes')
def reservar_informe(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('exportarInformes'))):
    from app.services.informes import reservar
    return reservar(db,codigo,datos,op.email or op.usuario)

@router.put('/recepciones/{codigo}/informes/{ident}')
def archivar_informe(codigo:str,ident:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('exportarInformes'))):
    from app.services.informes import archivar
    return archivar(db,codigo,ident,datos,op.email or op.usuario)

@router.get('/informes/{ident}/archivos/{archivo_id}')
def descargar_informe(ident:str,archivo_id:str,db:Session=Depends(get_db),op=Depends(ajustes.requiere('exportarInformes'))):
    from app.models import AppInforme,AppArchivo
    from app.services import archivos
    from fastapi.responses import FileResponse
    f=db.scalar(select(AppInforme).where(AppInforme.id==ident).with_for_update())
    if not f or archivo_id not in [a['id'] for a in f.datos.get('archivos',[])]:raise HTTPException(404,'Archivo del informe no encontrado')
    a=db.get(AppArchivo,archivo_id)
    if not a or not archivos.ruta(a).is_file():raise HTTPException(404,'Archivo no disponible')
    registro={'usuario':op.email or op.usuario,'fecha':m._iso(utcnow())}
    f.datos={**f.datos,'descargas':[*f.datos.get('descargas',[]),registro][-100:]}
    ajustes.auditar(db,op.email or op.usuario,'DESCARGA_SOLICITADA',f.recepcion,{'informeId':f.id,'archivoId':a.id})
    db.commit()
    return FileResponse(archivos.ruta(a),media_type=a.mime,filename=a.nombre,headers={'Cache-Control':'private, no-store'})

@router.put('/recepciones/{codigo}/columnas-informe')
def columnas_informe(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('exportarInformes'))):
    import json
    r=m.obtener(db,codigo,bloquear=True)
    if r.estado not in m.ABIERTAS:raise HTTPException(409,'Reabre la recepción antes de cambiar sus columnas; los informes anteriores se conservan')
    anterior=hashlib.sha256(json.dumps(r.formatos or {},sort_keys=True).encode()).hexdigest()
    if datos.get('version')!=anterior:raise HTTPException(409,'Otro supervisor cambió el formato. Actualiza antes de guardar')
    origen=datos.get('origen');formatos=dict(r.formatos or {})
    if origen not in formatos:raise HTTPException(422,'Packing list no encontrado')
    f=dict(formatos[origen]);columnas=datos.get('columnas')
    permitidas={'marca','cliente','fisica','validacion','desface','pallet','posicion','codigoBarra','cantidadIncidencia','incidencia','observacion','evidencia'}
    if not isinstance(columnas,dict) or set(columnas)-permitidas or any(type(v)is not int or not 0<=v<len(f.get('encabezados',[])) for v in columnas.values()) or len(set(columnas.values()))!=len(columnas):raise HTTPException(422,'Selecciona columnas distintas dentro del packing list')
    f['salida']=columnas;formatos[origen]=f;r.formatos=formatos
    ajustes.auditar(db,op.email or op.usuario,'COLUMNAS_INFORME',r.codigo,{'origen':origen,'columnas':columnas})
    db.commit();return {'ok':True}
