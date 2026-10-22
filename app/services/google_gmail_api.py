"""Lectura propia y envío MIME con miniaturas, adjuntos y confirmación durable."""
import base64
import hashlib
import re
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
from html import escape
from sqlalchemy import select
from app.db import SessionLocal
from app.models import AppConfig, utcnow
from app.services import google_cuentas as g, google_drive_api as drive


def ficha(m):
    hs={h['name'].lower():str(h['value']).replace('\r',' ').replace('\n',' ')[:3000] for h in m.get('payload',{}).get('headers',[])}
    return {'id':m['id'],'threadId':m['threadId'],'asunto':hs.get('subject',''),'de':hs.get('from',''),
        'para':hs.get('to',''),'cc':hs.get('cc',''),'replyTo':hs.get('reply-to',''),'fecha':hs.get('date',''),
        'messageId':hs.get('message-id',''),'references':hs.get('references',''),'resumen':m.get('snippet','')[:500]}


def perfil(cuenta):
    p=g.peticion(cuenta,'gmail','GET','profile').json()
    if str(p.get('emailAddress','')).lower()!=cuenta.lower():raise RuntimeError('GMAIL_CUENTA: El buzón no corresponde a la cuenta autorizada.')
    return p


def mensaje(cuenta,ident,formato='metadata'):
    if not re.fullmatch(r'[a-f0-9]{8,64}',str(ident or '')):raise RuntimeError('GMAIL_MENSAJE: Identificador inválido.')
    return g.peticion(cuenta,'gmail','GET','messages/'+ident,params={'format':formato}).json()


def consultar(cuenta,operacion,p):
    perfil(cuenta)
    if operacion=='gmailEstado':return {'exito':True,'cuentaGmail':cuenta,'lecturaConfirmada':True,'versionGmail':'63'}
    if operacion=='gmailBuscar':
        busqueda=str(p.get('busqueda','')).strip()
        if not busqueda or len(busqueda)>250:raise RuntimeError('GMAIL_BUSQUEDA: Escribe una búsqueda de hasta 250 caracteres.')
        r=g.peticion(cuenta,'gmail','GET','messages',params={'q':busqueda+' -in:trash -in:spam','maxResults':15}).json()
        return {'exito':True,'cuentaGmail':cuenta,'mensajes':[ficha(mensaje(cuenta,m['id'])) for m in r.get('messages',[])],'hayMas':bool(r.get('nextPageToken'))}
    m=mensaje(cuenta,p.get('mensajeId'),'full');f=ficha(m);textos=[];adjuntos=[]
    def leer(p,nivel=0):
        if nivel>15:return
        if p.get('filename'):adjuntos.append(p['filename'][:200])
        if p.get('mimeType')=='text/plain' and p.get('body',{}).get('data'):
            data=p['body']['data'];textos.append(base64.urlsafe_b64decode(data+'='*(-len(data)%4)).decode(errors='replace')[:60000])
        for parte in p.get('parts',[])[:30]:leer(parte,nivel+1)
    leer(m.get('payload',{}));f.update(texto='\n'.join(textos)[:60000] or f['resumen'],adjuntos=adjuntos[:100])
    return {'exito':True,'cuentaGmail':cuenta,'mensaje':f}


def preparar_mime(cuenta,cuenta_drive,clave,p):
    final=p.get('correoFinal') or {};html=final.get('html') or '<p>Informe de la recepción '+escape(p.get('codigo',''))+'.</p>'
    asunto=final.get('asunto') or 'Informe de recepción '+p.get('codigo','')
    seleccion=final.get('respuestaGmail');original=None
    if seleccion:
        if seleccion.get('cuenta')!=cuenta:raise RuntimeError('GMAIL_CUENTA: El hilo pertenece a otra cuenta.')
        original=ficha(mensaje(cuenta,seleccion['id']))
        if original['threadId']!=seleccion.get('threadId') or not re.fullmatch(r'<[^<>\s]+>',original['messageId']):raise RuntimeError('GMAIL_HILO: No se confirmó el mensaje original.')
        if asunto!='Re: '+re.sub(r'^(re:\s*)+','',original['asunto'],flags=re.I):raise RuntimeError('GMAIL_ASUNTO: La respuesta debe conservar el asunto original.')
    m=EmailMessage(policy=SMTP);m['From']=cuenta;m['To']=p['destinatarios'];m['Subject']=asunto;m['Date']=formatdate(localtime=False)
    mid='<itsanet.'+hashlib.sha256((cuenta+'|'+clave).encode()).hexdigest()+'@itsanet.local>'
    m['Message-ID']=mid
    if original:
        m['In-Reply-To']=original['messageId'];m['References']=' '.join(re.findall(r'<[^<>\s]{1,200}>',original['references'])[-10:]+[original['messageId']])
    permitidos={a['fileId']:a for a in p.get('archivos',[])}
    fotos={f['archivoId']:f['fileId'] for f in p.get('manifiesto',[]) if f.get('fileId') in permitidos}
    imagenes={};total=0
    def imagen(match):
        nonlocal total
        tag=match.group();ident=re.search(r'data-archivo=["\']([^"\']+)',tag)
        if not ident or ident[1] not in fotos:raise RuntimeError('CORREO_IMAGEN: Una imagen no tiene evidencia y enlace confirmados en esta entrega.')
        fid=fotos[ident[1]];cid='foto_'+ident[1]
        if cid not in imagenes:
            bruto=drive.miniatura(cuenta_drive,fid);total+=len(bruto)
            if total>3*1024*1024:raise RuntimeError('CORREO_TAMANO: Las miniaturas superan el límite del correo.')
            imagenes[cid]=bruto
        # La miniatura viaja dentro del mensaje y enlaza al archivo real confirmado.
        limpio=re.sub(r'\s+src=["\'][^"\']*["\']','',tag,flags=re.I)
        limpio=limpio[:-1]+' src="cid:'+cid+'">'
        return '<a href="https://drive.google.com/file/d/'+fid+'/view">'+limpio+'</a>'
    html=re.sub(r'<img\b[^>]*>',imagen,html,flags=re.I)
    if 'data-copia-pendiente' in html or re.search(r'href=["\']\s*["\']',html,re.I):raise RuntimeError('CORREO_ENLACE: Actualiza el borrador; quedan enlaces o imágenes sin confirmar.')
    m.set_content(final.get('texto') or 'Se adjunta el informe de recepción. Consulta la versión HTML para ver las imágenes.')
    m.add_alternative(html,subtype='html')
    for cid,bruto in imagenes.items():m.get_payload()[1].add_related(bruto,maintype='image',subtype='jpeg',cid='<'+cid+'>',filename=cid+'.jpg',disposition='inline')
    for a in p.get('archivos',[]):
        if a.get('tipoArchivo')!='informe':continue
        bruto=drive.contenido(cuenta_drive,a['fileId']);total+=len(bruto)
        if total>18*1024*1024:raise RuntimeError('CORREO_TAMANO: Los adjuntos superan 18 MiB. Selecciona menos informes.')
        m.add_attachment(bruto,maintype='application',subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',filename=a['nombre'])
    return m,original,mid


def finalizar(cuenta,cuenta_drive,clave,p):
    from app.services.entregas import RevisionEntrega
    perfil(cuenta)
    ident='gm:'+hashlib.sha256((cuenta+'|'+clave).encode()).hexdigest()[:32]
    carpeta=drive.recepcion(cuenta_drive,p)
    acuse={'exito':True,'id':clave,'carpeta':drive.url(carpeta),'carpetaFotos':drive.url(carpeta),
        'enviadoA':p.get('destinatarios',''),'remitente':cuenta,'estado':'ENTREGADA','sheet':'','confirmadoEn':utcnow().isoformat()}
    if not p.get('destinatarios'):return acuse
    # Sheets explícitos conservan una vía compatible; nunca omitir silenciosamente.
    if p.get('exportarSheet'):raise RuntimeError('GOOGLE_SHEETS: Desactiva la copia opcional a Sheets y usa los informes Excel, o conserva el puente anterior para esa exportación.')
    with SessionLocal() as db:
        f=db.get(AppConfig,ident)
        if f and f.datos.get('estado')=='ENTREGADA':return f.datos['acuse']
        if f and f.datos.get('estado')=='ENVIANDO':
            # Un reinicio o timeout puede ocurrir después de entregar a Google.
            raise RevisionEntrega('Envío Google sin acuse local. Comprueba Enviados antes de repetir; la API no vuelve a enviar automáticamente.')
    m,original,mid=preparar_mime(cuenta,cuenta_drive,clave,p)
    with SessionLocal() as db:
        from sqlalchemy.exc import IntegrityError
        if not db.get(AppConfig,ident):
            db.add(AppConfig(clave=ident,usuario=cuenta,datos={'estado':'PREPARADA'}))
            try:db.commit()
            except IntegrityError:db.rollback()
        f=db.scalar(select(AppConfig).where(AppConfig.clave==ident).with_for_update())
        if f.datos.get('estado')=='ENTREGADA':return f.datos['acuse']
        if f.datos.get('estado')=='ENVIANDO':raise RevisionEntrega('Esta entrega ya tiene un envío en curso. Revisa su confirmación; no se repite.')
        f.datos={'estado':'ENVIANDO','messageId':mid};db.commit()
    try:
        resultado=g.peticion(cuenta,'gmail','POST','messages/send',json={
            'raw':base64.urlsafe_b64encode(m.as_bytes()).decode().rstrip('='),
            **({'threadId':original['threadId']} if original else {})}).json()
    except RuntimeError as exc:
        # Un rechazo explícito de autorización/cuota acredita que Google no
        # aceptó el envío. Puede recuperarse tras corregirlo. Un timeout sigue
        # siendo ambiguo y mantiene el bloqueo contra duplicados.
        if re.search(r'\(HTTP (?:400|401|403|413|429)\)',str(exc)) or str(exc).startswith(('GOOGLE_AUTORIZACION:','GOOGLE_PERMISOS:')):
            with SessionLocal() as db:
                f=db.get(AppConfig,ident);f.datos={'estado':'PREPARADA','messageId':mid};db.commit()
            raise
        raise RevisionEntrega('Gmail no confirmó el envío. Revisa Enviados y el registro de procesos antes de repetir; no se reenvía automáticamente.') from None
    except Exception:
        raise RevisionEntrega('Gmail no confirmó el envío. Revisa Enviados y el registro de procesos antes de repetir; no se reenvía automáticamente.') from None
    if not resultado.get('id') or original and resultado.get('threadId')!=original['threadId']:
        raise RevisionEntrega('Google no confirmó el mensaje o hilo esperado. Revisa Enviados antes de reintentar.')
    acuse['gmail']={'mensajeId':resultado['id'],'threadId':resultado.get('threadId')}
    acuse['confirmadoEn']=utcnow().isoformat()
    with SessionLocal() as db:
        f=db.get(AppConfig,ident);f.datos={'estado':'ENTREGADA','acuse':acuse};db.commit()
    return acuse
