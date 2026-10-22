"""Drive API con IDs reservados antes de subir: un reintento no duplica archivos."""
import base64
import hashlib
import io
import json
import re
from uuid import uuid4
from PIL import Image, ImageOps
from sqlalchemy import select
from app.db import SessionLocal
from app.models import AppConfig
from app.services import google_cuentas as g

CARPETA='application/vnd.google-apps.folder'
ATAJO='application/vnd.google-apps.shortcut'


def url(ident):return 'https://drive.google.com/drive/folders/'+ident


def validar_id(ident):
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,128}',str(ident or '')):raise RuntimeError('DRIVE_IDENTIFICADOR: Falta un identificador de Drive válido.')
    return ident


def nombre(texto):
    return re.sub(r'[\\/\x00-\x1f]','_',str(texto or '')).strip()[:180]


def listar(cuenta,q):
    salida=[];pagina=None
    while True:
        r=g.peticion(cuenta,'drive','GET','files',params={'q':'trashed = false and ('+q+')',
            'fields':'files(id,name,mimeType,parents,shortcutDetails,appProperties),nextPageToken',
            'supportsAllDrives':'true','includeItemsFromAllDrives':'true','pageSize':100,**({'pageToken':pagina} if pagina else {})}).json()
        salida.extend(r.get('files',[]));pagina=r.get('nextPageToken')
        if not pagina:return salida


def ficha(cuenta,ident):
    return g.peticion(cuenta,'drive','GET','files/'+validar_id(ident),params={
        'fields':'id,name,mimeType,parents,trashed,appProperties,md5Checksum','supportsAllDrives':'true'}).json()


def escapar(texto):return texto.replace('\\','\\\\').replace("'","\\'")


def buscar_carpeta(cuenta,padre,n):
    fs=listar(cuenta,"'"+validar_id(padre)+"' in parents and mimeType = '"+CARPETA+"' and name = '"+escapar(nombre(n))+"'")
    if len(fs)>1:raise RuntimeError('DRIVE_CARPETA_DUPLICADA: Hay carpetas con el mismo nombre. ADMIN debe revisar la ruta antes de continuar.')
    return fs[0]['id'] if fs else None


def reservado(cuenta,clave,crear):
    ident='gd:'+hashlib.sha256((cuenta+'|'+clave).encode()).hexdigest()[:32]
    with SessionLocal() as db:
        # La fila persiste antes de cualquier carga; la PK resuelve la carrera inicial.
        if not db.get(AppConfig,ident):
            from sqlalchemy.exc import IntegrityError
            db.add(AppConfig(clave=ident,usuario=cuenta,datos={}))
            try:db.commit()
            except IntegrityError:db.rollback()
        f=db.scalar(select(AppConfig).where(AppConfig.clave==ident).with_for_update())
        if f.datos.get('id'):return f.datos['id']
        valor=crear()
        f.datos={'id':validar_id(valor)};db.commit();return valor


def generar(cuenta):
    return g.peticion(cuenta,'drive','GET','files/generateIds',params={'count':1,'space':'drive'}).json()['ids'][0]


def carpeta(cuenta,padre,n):
    n=nombre(n)
    if not n or n in ('.','..'):raise RuntimeError('DRIVE_RUTA: Nombre de carpeta inválido.')
    # Mantener el bloqueo hasta resolver o reservar la identidad de esta ruta.
    def elegir():return buscar_carpeta(cuenta,padre,n) or generar(cuenta)
    ident=reservado(cuenta,'carpeta:'+padre+'/'+n,elegir)
    try:
        f=ficha(cuenta,ident)
        if f.get('trashed') or f.get('name')!=n or padre not in f.get('parents',[]):raise RuntimeError('DRIVE_RUTA_CAMBIO: La carpeta fue movida o renombrada. ADMIN debe revisar el destino.')
    except RuntimeError as exc:
        if not str(exc).startswith('GOOGLE_NO_ENCONTRADO:'):raise
        try:g.peticion(cuenta,'drive','POST','files',params={'supportsAllDrives':'true'},json={'id':ident,'name':n,'mimeType':CARPETA,'parents':[padre]})
        except RuntimeError:
            f=ficha(cuenta,ident)
            if f.get('name')!=n or padre not in f.get('parents',[]):raise
    return ident


def recepcion(cuenta,p):
    n=nombre(p.get('carpetaRecepcion') or p.get('recepcion') or p.get('codigo'))
    if p.get('carpetaRecepcionId'):
        f=ficha(cuenta,p['carpetaRecepcionId'])
        if f.get('trashed') or f.get('mimeType')!=CARPETA or f.get('name')!=n:raise RuntimeError('DRIVE_RECEPCION: La carpeta no corresponde a esta recepción.')
        return f['id']
    raiz=validar_id(p.get('carpetaRaiz'))
    for x in (p.get('cliente'),p.get('marca'),n):
        if x:raiz=carpeta(cuenta,raiz,x)
    return raiz


def ruta(cuenta,raiz,partes,crear=True):
    if not isinstance(partes,list) or len(partes)>8:raise RuntimeError('DRIVE_RUTA: Ruta inválida.')
    for p in partes:
        if not isinstance(p,str) or not p.strip() or p in ('.','..'):raise RuntimeError('DRIVE_RUTA: Segmento inválido.')
        raiz=carpeta(cuenta,raiz,p) if crear else buscar_carpeta(cuenta,raiz,p)
        if not raiz:return None
    return raiz


def preparar(cuenta,p):
    r=recepcion(cuenta,p)
    for embarque in p.get('embarques',[]):
        e=carpeta(cuenta,r,embarque)
        for c in ('SOBRANTES','FALTANTES','PNC','BULTOS','PRE-INGRESO','FOTOS-FINALES','PANORAMICAS','PRODUCTOS'):carpeta(cuenta,e,c)
    return {'exito':True,'carpeta':url(r)}


def atajo(cuenta,padre,archivo,n,clave):
    existentes=listar(cuenta,"'"+padre+"' in parents and mimeType = '"+ATAJO+"'")
    if any(x.get('shortcutDetails',{}).get('targetId')==archivo for x in existentes):return
    g.peticion(cuenta,'drive','POST','files',params={'supportsAllDrives':'true'},json={
        'name':nombre(n),'mimeType':ATAJO,'parents':[padre],'shortcutDetails':{'targetId':archivo},'appProperties':{'itsanetClave':clave}})


def subir(cuenta,clave,p):
    raiz=recepcion(cuenta,p)
    padre=ruta(cuenta,raiz,p.get('ruta',[]) or ['imagenes']) if p['tipoArchivo']=='foto' else carpeta(cuenta,raiz,'INFORMES')
    huella=hashlib.sha256(clave.encode()).hexdigest()
    original=nombre(p.get('nombre')) or 'archivo'
    ident=p.get('fileId') or reservado(cuenta,'archivo:'+clave,lambda:generar(cuenta))
    existe=None
    try:existe=ficha(cuenta,ident)
    except RuntimeError as exc:
        if not str(exc).startswith('GOOGLE_NO_ENCONTRADO:'):raise
    if existe and existe.get('trashed'):raise RuntimeError('DRIVE_PAPELERA: El archivo fue retirado de Drive. Revisa la evidencia antes de continuar.')
    if existe and existe.get('appProperties',{}).get('itsanetClave',huella)!=huella:raise RuntimeError('DRIVE_IDENTIDAD: El archivo pertenece a otro registro.')
    if existe and not p.get('fileId') and p.get('base64'):
        bruto=base64.b64decode(p['base64'],validate=True)
        if existe.get('md5Checksum')!=hashlib.md5(bruto).hexdigest():raise RuntimeError('DRIVE_CHECKSUM: El ID reservado no confirmó el contenido original. Se conserva la foto local.')
    meta={'name':original,'description':'ITSANET '+clave+' | Recepcion '+str(p.get('recepcion','')),
        'appProperties':{'itsanetClave':huella,'recepcion':str(p.get('recepcion',''))}}
    if not existe:
        bruto=base64.b64decode(p.get('base64',''),validate=True)
        if not bruto or len(bruto)>16*1024*1024:raise RuntimeError('DRIVE_TAMANO: Archivo vacío o mayor al límite.')
        meta.update(id=ident,parents=[padre]);frontera='itsanet_'+uuid4().hex
        contenido=('--'+frontera+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+json.dumps(meta)+'\r\n--'+frontera+'\r\nContent-Type: '+p.get('tipo','application/octet-stream')+'\r\n\r\n').encode()+bruto+('\r\n--'+frontera+'--\r\n').encode()
        # No seguir intentando POST ciegamente: siempre reutilizar el ID reservado.
        g.peticion(cuenta,'upload','POST','files',params={'uploadType':'multipart','supportsAllDrives':'true'},content=contenido,headers_extra={'Content-Type':'multipart/related; boundary='+frontera})
        confirmado=ficha(cuenta,ident)
        if confirmado.get('md5Checksum')!=hashlib.md5(bruto).hexdigest():raise RuntimeError('DRIVE_CHECKSUM: Google no confirmó el contenido íntegro del archivo.')
    else:
        padres=existe.get('parents',[])
        if p.get('conservarAccesosPrevios',True):
            for previo in padres:
                if previo!=padre:atajo(cuenta,previo,ident,original,huella)
        g.peticion(cuenta,'drive','PATCH','files/'+ident,params={'supportsAllDrives':'true',
            **({'addParents':padre,'removeParents':','.join(x for x in padres if x!=padre)} if padre not in padres else {})},json=meta)
    vinculos={};por_evidencia={};activos={padre}
    for v in p.get('rutasVinculadas',[]):
        destino=ruta(cuenta,raiz,v['ruta']);activos.add(destino)
        if destino!=padre:atajo(cuenta,destino,ident,v.get('nombre') or original,huella)
        sku=url(ruta(cuenta,raiz,v.get('rutaSku') or v['ruta'][:-1])) if v.get('sku') else ''
        dato={'carpeta':url(destino),'carpetaSkuUrl':sku}
        vinculos[v.get('categoria','')+'|'+v.get('sku','')]=dato
        if v.get('evidenciaId'):por_evidencia[v['evidenciaId']]=dato
    if p.get('conservarAccesosPrevios') is False:
        for anterior in p.get('rutasAnteriores',[]):
            viejo=ruta(cuenta,raiz,anterior,crear=False)
            if viejo and viejo not in activos:
                for a in listar(cuenta,"'"+viejo+"' in parents and mimeType = '"+ATAJO+"'"):
                    if a.get('shortcutDetails',{}).get('targetId')==ident and a.get('appProperties',{}).get('itsanetClave')==huella:
                        g.peticion(cuenta,'drive','PATCH','files/'+a['id'],params={'supportsAllDrives':'true'},json={'trashed':True})
    return {'exito':True,'fileId':ident,'nombre':original,'tipoArchivo':p['tipoArchivo'],
        'enlace':'https://drive.google.com/file/d/'+ident+'/view','carpeta':url(padre),'carpetaRecepcionUrl':url(raiz),
        'carpetaSkuUrl':url(ruta(cuenta,raiz,p.get('rutaSku') or p.get('ruta',[])[:-1])) if p.get('sku') else '',
        'vinculosDrive':vinculos,'vinculosPorEvidencia':por_evidencia}


def contenido(cuenta,ident):
    # Los archivos admitidos por ITSANET tienen límite previo de 16 MiB.
    return g.peticion(cuenta,'drive','GET','files/'+validar_id(ident),params={'alt':'media','supportsAllDrives':'true'}).content


def miniatura(cuenta,ident):
    with Image.open(io.BytesIO(contenido(cuenta,ident))) as im:
        im=ImageOps.exif_transpose(im);im.thumbnail((640,480));out=io.BytesIO();im.convert('RGB').save(out,format='JPEG',quality=78)
    return out.getvalue()
