"""Políticas administrativas y coordinación de la operación actual."""
import hashlib
import re
from uuid import uuid4
from fastapi import APIRouter, Depends, Body, HTTPException, Request, Query
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import AppPresencia, AppEvento, AppSku, utcnow
from app.security import usuario_actual, COOKIE
from app.routers.integraciones import admin
from app.services import ajustes, calidad, app_modelo as m

router=APIRouter(prefix='/api/operacion',tags=['gestion'])

@router.get('/recepciones/{codigo}/correo')
def correo_vista(codigo:str,entregaId:str='',origen:str='',db:Session=Depends(get_db),op=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.correo_redactado import vista
    return vista(db,codigo,op.email or op.usuario,entregaId,origen)

@router.get('/recepciones/{codigo}/correos-embarques')
def plan_correos(codigo:str,db:Session=Depends(get_db),_=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.agrupacion_correo import vista
    return vista(db,codigo)

@router.post('/recepciones/{codigo}/correos-embarques/vista')
def vista_plan_correos(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),_=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.agrupacion_correo import vista
    return vista(db,codigo,datos)

@router.put('/recepciones/{codigo}/correos-embarques')
def guardar_plan_correos(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.agrupacion_correo import guardar
    return guardar(db,codigo,datos,op.email or op.usuario)

@router.put('/recepciones/{codigo}/correo')
def correo_guardar(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.correo_redactado import guardar
    return guardar(db,codigo,datos,op.email or op.usuario)

@router.post('/recepciones/{codigo}/correo/manual')
def correo_manual(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.correo_redactado import manual
    return manual(db,codigo,datos,op.email or op.usuario)

@router.get('/almacenamiento')
def almacenamiento(db:Session=Depends(get_db),_=Depends(admin)):
    from sqlalchemy import func, cast, Text
    from app.models import AppEntrega, AppArchivo
    return {'bytesInstantaneas':db.scalar(select(func.coalesce(func.sum(func.length(cast(AppEntrega.datos,Text))),0))),
        'entregas':db.scalar(select(func.count()).select_from(AppEntrega)),
        'fotosPendientes':db.scalar(select(func.count()).select_from(AppArchivo).where(AppArchivo.tipo=='foto',AppArchivo.drive_id.is_(None))),
        'bytesFotosPendientes':db.scalar(select(func.coalesce(func.sum(AppArchivo.bytes),0)).where(AppArchivo.tipo=='foto',AppArchivo.drive_id.is_(None)))}

@router.post('/almacenamiento/compactar')
def compactar_entregas(db:Session=Depends(get_db),op=Depends(admin)):
    import json
    from app.models import AppEntrega
    from app.services.instantaneas import compactar,expandir
    filas=list(db.scalars(select(AppEntrega).where(AppEntrega.estado!='PROCESANDO',
        AppEntrega.datos['instantaneaGzip'].as_string().is_(None),AppEntrega.datos['skus'].as_string().is_not(None))
        .order_by(AppEntrega.id).limit(20).with_for_update(skip_locked=True)))
    antes=despues=cantidad=0
    for e in filas:
        original=dict(e.datos);nuevo=compactar(original)
        if expandir(nuevo)!=original:raise HTTPException(409,'No coincide la verificación de la instantánea; no se modificó el lote.')
        antes+=len(json.dumps(original).encode());despues+=len(json.dumps(nuevo).encode());e.datos=nuevo;cantidad+=1
    ajustes.auditar(db,op.email or op.usuario,'INSTANTANEAS_COMPACTADAS','almacenamiento',{'entregas':cantidad,'antes':antes,'despues':despues});db.commit()
    return {'compactadas':cantidad,'bytesAntes':antes,'bytesDespues':despues,'mensaje':'Instantáneas verificadas y comprimidas. Se conservan conteos, informes, fotos y auditoría.'}

@router.get('/clientes-operacion')
def clientes_operacion(db:Session=Depends(get_db),_=Depends(usuario_actual)):
    from app.models import AppRecepcion, Producto, AppConfig
    nombres=set(ajustes.configuracion(db)['clientes'])
    nombres.update(n for n in db.scalars(select(AppRecepcion.cliente).distinct()) if n)
    nombres.update(n for n in db.scalars(select(Producto.cliente).distinct()) if n)
    f=db.get(AppConfig,'clientes_fichas');fichas=f.datos if f else {}
    return [{'id':n,'reglas':ajustes.cliente(db,n),'nombre':fichas.get(n,{}).get('nombre',n),
             'unificarCon':fichas.get(n,{}).get('unificarCon',''),
             'oculto':fichas.get(n,{}).get('oculto',False),'version':fichas.get(n,{}).get('version',0)} for n in sorted(nombres)]

@router.put('/clientes-fichas')
def editar_cliente_ficha(datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('gestionarClientes'))):
    from app.models import AppConfig
    ident=str(datos.get('id') or '').strip().upper()
    nombre=str(datos.get('nombre') or '').strip()
    destino=str(datos.get('unificarCon') or '').strip().upper()
    nombres={c['id'] for c in clientes_operacion(db,op)}
    if ident not in nombres or not 1<=len(nombre)<=60 or destino and (destino not in nombres or destino==ident):
        raise HTTPException(422,'Selecciona un cliente existente y un nombre de 1 a 60 caracteres; el destino debe ser otro cliente.')
    if type(datos.get('oculto',False)) is not bool:raise HTTPException(422,'Estado del cliente inválido')
    f=db.scalar(select(AppConfig).where(AppConfig.clave=='clientes_fichas').with_for_update().execution_options(populate_existing=True))
    fichas=dict(f.datos) if f else {}
    anterior=fichas.get(ident,{})
    if datos.get('version')!=anterior.get('version',0):raise HTTPException(409,'Otro supervisor modificó este cliente. Actualiza antes de guardar.')
    if destino and (fichas.get(destino,{}).get('unificarCon') or fichas.get(destino,{}).get('oculto')):
        raise HTTPException(422,'Elige un cliente destino activo, sin otra unificación.')
    if (destino or datos.get('oculto')) and any(c.get('unificarCon')==ident for c in fichas.values()):
        raise HTTPException(409,'Otros clientes apuntan a este destino. Corrige esas unificaciones primero.')
    fichas[ident]={'nombre':nombre,'unificarCon':destino,'oculto':datos.get('oculto',False),'version':anterior.get('version',0)+1}
    f=f or AppConfig(clave='clientes_fichas');f.datos=fichas;f.usuario=op.email or op.usuario;db.add(f)
    ajustes.auditar(db,f.usuario,'CLIENTE_FICHA_EDITADA',ident,{'anterior':anterior,'actual':fichas[ident],'historicosModificados':False})
    db.commit()
    return fichas[ident]

@router.put('/clientes-operacion/{nombre:path}')
def guardar_cliente_operativo(nombre:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('gestionarClientes'))):
    from app.models import AppConfig
    if set(datos)-{'palletRequerido','posicionRequerida','columnas'}:
        raise HTTPException(422,'Solo puedes editar reglas operativas del cliente.')
    db.scalar(select(AppConfig).where(AppConfig.clave=='politicas').with_for_update().execution_options(populate_existing=True))
    actuales=ajustes.configuracion(db)['clientes']
    nombre=nombre.strip().upper()
    actuales[nombre]={**ajustes.cliente(db,nombre),**datos}
    ajustes.guardar(db,{'clientes':actuales},op.email or op.usuario)
    return {'id':nombre,'reglas':ajustes.cliente(db,nombre)}

@router.post('/recepciones/{codigo}/eventos/{ident}/corregir')
def corregir_conteo(codigo:str,ident:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.correcciones import corregir
    return corregir(db,codigo,ident,datos,op.email or op.usuario)

@router.post('/recepciones/{codigo}/conteos-repartidos')
def repartir_conteo(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(usuario_actual)):
    from app.services.correcciones import repartir
    return repartir(db,codigo,datos,op.email or op.usuario)

@router.get('/politicas')
def politicas(db:Session=Depends(get_db),_=Depends(admin)):
    return {'acciones':ajustes.ACCIONES,**ajustes.configuracion(db)}

@router.put('/politicas')
def guardar(datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(admin)):
    return ajustes.guardar(db,datos,op.email or op.usuario)

# El identificador comercial puede contener barras (p. ej. VENTURA/VW).
# ASGI decodifica %2F antes del enrutamiento: debe capturarse el nombre entero.
@router.get('/reglas/{cliente:path}')
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


@router.get('/recepciones/{codigo}/pendientes-cierre')
def pendientes_cierre(codigo: str, offset: int = Query(0, ge=0), limite: int = Query(30, ge=1, le=100),
                      db: Session = Depends(get_db), _=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.drive import pendientes_cierre
    return pendientes_cierre(db, codigo, offset, limite)


@router.post('/recepciones/{codigo}/drive/reintentar')
def reintentar_drive(codigo: str, db: Session = Depends(get_db), op=Depends(ajustes.requiere('cerrarRecepciones'))):
    from app.services.drive import reintentar_pendientes
    return reintentar_pendientes(db, codigo, op.email or op.usuario)

@router.get('/recepciones/{codigo}/informes')
def historial_informes(codigo:str,db:Session=Depends(get_db),_=Depends(ajustes.requiere('exportarInformes'))):
    from app.services.informes import historial
    return historial(db,codigo)

@router.get('/recepciones/{codigo}/informe-actual')
def informe_actual(codigo:str,formato:str='envio-ampliado',db:Session=Depends(get_db),_=Depends(ajustes.requiere('exportarInformes'))):
    from app.services.informes import actual
    return actual(db,codigo,formato)

@router.get('/informes/{ident}/descarga')
def descargar_conjunto(ident:str,origen:str='',db:Session=Depends(get_db),op=Depends(ajustes.requiere('exportarInformes'))):
    from app.services.descarga_informes import descargar
    return descargar(db,ident,origen,op.email or op.usuario)

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
    permitidas={'marca','cliente','fisica','validacion','desface','pallet','posicion','codigoBarra','cantidadIncidencia','incidencia','observacion','evidencia','depot'}
    if not isinstance(columnas,dict) or set(columnas)-permitidas or any(type(v)is not int or not 0<=v<len(f.get('encabezados',[])) for v in columnas.values()) or len(set(columnas.values()))!=len(columnas):raise HTTPException(422,'Selecciona columnas distintas dentro del packing list')
    from app.services.formato_informe import validar_columnas, validar_orden_salida
    validar_columnas(f,columnas)
    if 'ordenSalida' in datos:
        validar_orden_salida(f,datos['ordenSalida'])
        if datos['ordenSalida'] is None:f.pop('ordenSalida',None)
        else:f['ordenSalida']=datos['ordenSalida']
    f['salida']=columnas;formatos[origen]=f;r.formatos=formatos
    ajustes.auditar(db,op.email or op.usuario,'COLUMNAS_INFORME',r.codigo,{'origen':origen,'columnas':columnas,'ordenSalida':f.get('ordenSalida')})
    db.commit();return {'ok':True}

@router.get('/recepciones/{codigo}/edicion')
def edicion_recepcion(codigo:str,db:Session=Depends(get_db),op=Depends(ajustes.requiere('gestionarClientes'))):
    from app.services.recepcion_edicion import obtener
    return obtener(db,codigo)

@router.put('/recepciones/{codigo}/edicion')
def editar_recepcion(codigo:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('gestionarClientes'))):
    from app.services.recepcion_edicion import editar
    return editar(db,codigo,datos,op.email or op.usuario)

@router.post('/recepciones/{codigo}/embarques/{origen}/retirar')
def retirar_embarque(codigo:str,origen:str,datos:dict=Body(...),db:Session=Depends(get_db),op=Depends(ajustes.requiere('gestionarClientes'))):
    from app.services.recepcion_edicion import retirar
    return retirar(db,codigo,origen,datos,op.email or op.usuario)
