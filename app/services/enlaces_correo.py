"""Índice acotado de carpetas contenedoras; no enumera fotos ni carpetas SKU."""
import hashlib
import re
import time
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AppConfig, AppCopiaDrive, AppEvento
from app.services import app_modelo as m

CATEGORIAS={'SOBRANTES':'Sobrantes','FALTANTES':'Faltantes','PNC':'PNC'}


def carpeta_url(valor):
    encontrado=re.fullmatch(r'https://drive\.google\.com/(?:drive/)?folders/([A-Za-z0-9_-]{5,128})(?:\?[^#\s]*)?',str(valor or ''))
    return 'https://drive.google.com/drive/folders/'+encontrado[1] if encontrado else ''


def clave(codigo):return 'drive:mail:'+hashlib.sha256(codigo.encode()).hexdigest()[:28]


def base_embarque(emb):
    from app.services.fotos_identidad import componente
    carpeta=componente(emb,90)
    if carpeta!=emb or emb=='POR-ASIGNAR':carpeta+='-'+hashlib.sha256(emb.encode()).hexdigest()[:10]
    return (carpeta,)


def raiz(db,codigo):
    evento=db.scalar(select(AppEvento).where(AppEvento.recepcion==codigo,AppEvento.tipo=='AUDITORIA',
        AppEvento.motivo=='CARPETA_DRIVE_VERIFICADA').order_by(AppEvento.creado_en.desc(),AppEvento.id.desc()).limit(1))
    if evento and carpeta_url((evento.datos or {}).get('carpeta')):return carpeta_url(evento.datos['carpeta'])
    for copia in db.scalars(select(AppCopiaDrive).where(AppCopiaDrive.recepcion==codigo,AppCopiaDrive.estado=='COPIADA').order_by(AppCopiaDrive.archivo_id)):
        url=carpeta_url(copia.datos.get('carpetaRecepcionUrl'))
        if url:return url
    return ''


def rutas(db,codigo):
    from app.services.fotos_embarques import informacion
    _,_,_,embarques=informacion(db,codigo)
    bases=[()]+[base_embarque(e) for e in embarques]
    salida=list(dict.fromkeys(bases+[b+(categoria,) for b in bases for categoria in CATEGORIAS]))
    if len(salida)>512:raise HTTPException(422,'Hay demasiados embarques para comprobar sus enlaces en una consulta.')
    return salida


def actualizar(db,codigo,usuario):
    """Una consulta explícita: solo carpetas existentes, sin mover ni subir fotos."""
    from app.services import entregas,integraciones,remitentes
    codigo=m.obtener(db,codigo).codigo
    principal=raiz(db,codigo)
    if not principal:raise HTTPException(409,'Primero verifica la carpeta de recepción. Después podrás actualizar sus enlaces de embarques y novedades.')
    solicitadas=rutas(db,codigo)
    correo,_=remitentes.elegir(db,codigo,{'modoRemitente':'RESPONSABLE'},usuario)
    conexion=integraciones.google(db,correo)
    f=db.get(AppConfig,clave(codigo));anterior=f.datos if f else {}
    if anterior.get('raiz')==principal and anterior.get('rutas')==[list(r) for r in solicitadas] and time.time()-anterior.get('comprobado',0)<30:
        return {'mensaje':'Enlaces comprobados recientemente. Se conserva el índice vigente.','cantidad':len(anterior.get('carpetas',[]))}
    db.rollback()
    try:
        respuesta=entregas.llamar_conexion('carpetasCorreo',uuid4().hex,{'usuario':correo,
            'carpetaRecepcionId':principal.rsplit('/',1)[-1],'rutas':[list(r) for r in solicitadas]},conexion)
    except RuntimeError as exc:raise HTTPException(502,str(exc)+' Actualiza Servidor.gs y publica una Nueva versión del mismo /exec si todavía no reconoce esta consulta.') from None
    except Exception:raise HTTPException(502,'Drive no confirmó los enlaces. Se conservan las fotos y los enlaces anteriores; puedes volver a comprobarlos.') from None
    carpetas=respuesta.get('carpetas')
    if carpeta_url(respuesta.get('carpeta'))!=principal or not isinstance(carpetas,list) or len(carpetas)>len(solicitadas):
        raise HTTPException(502,'Drive no confirmó las carpetas de esta recepción.')
    validas={}
    for fila in carpetas:
        if not isinstance(fila,dict) or not isinstance(fila.get('ruta'),list) or any(not isinstance(p,str) for p in fila['ruta']):raise HTTPException(502,'Drive devolvió una ruta de carpeta inválida.')
        ruta=tuple(fila['ruta']);url=carpeta_url(fila.get('url'))
        if ruta not in solicitadas or not url or ruta in validas or not ruta and url!=principal:raise HTTPException(502,'Drive devolvió una carpeta que no corresponde a esta consulta.')
        validas[ruta]=url
    db.rollback();m.obtener(db,codigo,bloquear=True)
    if raiz(db,codigo)!=principal or rutas(db,codigo)!=solicitadas or integraciones.google(db,correo)!=conexion:
        raise HTTPException(409,'La recepción o su conexión cambió durante la consulta. Actualiza antes de volver a comprobar.')
    f=db.get(AppConfig,clave(codigo)) or AppConfig(clave=clave(codigo))
    f.datos={'raiz':principal,'rutas':[list(r) for r in solicitadas],'comprobado':time.time(),
        'carpetas':[{'ruta':list(r),'url':url} for r,url in validas.items()]}
    f.usuario=usuario;db.add(f);db.commit()
    return {'mensaje':'Enlaces de Drive actualizados. Solo se incluyen carpetas existentes; las fotografías no se modificaron.','cantidad':len(validas)}


def enlaces(db,codigo,lineas,config,origen):
    from app.services.agrupacion_correo import embarque,grupo_id
    principal=raiz(db,codigo)
    f=db.get(AppConfig,clave(codigo));datos=f.datos if f else {}
    mapa={tuple(v['ruta']):carpeta_url(v.get('url')) for v in datos.get('carpetas',[])} if datos.get('raiz')==principal else {}
    propias=[l for l in lineas if not origen or config.get('modo')=='RECEPCION' or
        (config.get('modo')=='EMBARQUE' and grupo_id(embarque(l,config))==origen) or
        (config.get('modo') not in ('EMBARQUE','RECEPCION') and (l.get('origen') or 'PRINCIPAL')==origen)]
    embarques=list(dict.fromkeys(embarque(l,config) for l in propias if embarque(l,config)))
    base=base_embarque(embarques[0]) if len(embarques)==1 and origen and config.get('modo')!='RECEPCION' else ()
    url_principal=mapa.get(base) or principal
    salida=[];vistos=set()
    def agregar(url,texto):
        if url and url not in vistos:salida.append({'url':url,'texto':texto});vistos.add(url)
    agregar(url_principal,'Carpeta del embarque '+embarques[0] if base and mapa.get(base) else 'Carpeta de la recepción '+codigo)
    if base:
        for categoria,texto in CATEGORIAS.items():agregar(mapa.get(base+(categoria,)),texto)
    else:
        if not origen or config.get('modo')=='RECEPCION' or len(propias)==len(lineas):
            for categoria,texto in CATEGORIAS.items():agregar(mapa.get((categoria,)),('Recepción · ' if embarques else '')+texto)
        for emb in embarques:
            for categoria,texto in CATEGORIAS.items():agregar(mapa.get(base_embarque(emb)+(categoria,)),emb+' · '+texto)
    return salida
