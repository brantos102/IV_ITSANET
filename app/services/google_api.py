"""Adaptador directo compatible con las colas y acuses existentes."""
import base64
from app.services import google_cuentas as g, google_drive_api as drive, google_gmail_api as gmail

CAPACIDADES=['correoEditable','correoVerificado','gmailHilos','fotosSkuSimples','fotosAuditables','carpetasRecepcion62','carpetasBajoDemanda67','prepararCarpeta']


def llamar(operacion,clave,p,destino):
    p={**p,'carpetaRaiz':p.get('carpetaRaiz') or destino.get('carpetaRaiz','')}
    cuenta=destino.get('supervisor') or p.get('usuario','')
    if p.get('usuario') and cuenta!=p['usuario']:raise RuntimeError('GOOGLE_CUENTA: La operación pertenece a otra cuenta.')
    almacenamiento=g.cuenta_drive(destino)
    if operacion.startswith('gmail'):return gmail.consultar(cuenta,operacion,p)
    if operacion=='estado':
        if p.get('verificarGmail'):gmail.perfil(cuenta)
        if p.get('carpetaRaiz'):
            carpeta=drive.ficha(almacenamiento,p['carpetaRaiz'])
            if carpeta.get('trashed') or carpeta.get('mimeType')!=drive.CARPETA:raise RuntimeError('DRIVE_REPOSITORIO: El repositorio no es una carpeta activa.')
        return {'exito':True,'remitente':cuenta,'versionPuente':63,'capacidades':CAPACIDADES,
            'carpetaId':p.get('carpetaRaiz',''),'carpeta':drive.url(p['carpetaRaiz']) if p.get('carpetaRaiz') else '',
            'modo':'GOOGLE_API','cuentaDrive':almacenamiento}
    if operacion=='prepararCarpeta':return drive.preparar(almacenamiento,p)
    if operacion=='archivo':return drive.subir(almacenamiento,clave,p)
    if operacion=='miniatura':return {'exito':True,'base64':base64.b64encode(drive.miniatura(almacenamiento,p['fileId'])).decode()}
    if operacion=='papelera':
        g.peticion(almacenamiento,'drive','PATCH','files/'+drive.validar_id(p['fileId']),params={'supportsAllDrives':'true'},json={'trashed':True})
        return {'exito':True}
    if operacion=='carpetasCorreo':
        raiz=drive.validar_id(p.get('carpetaRecepcionId'));drive.ficha(almacenamiento,raiz)
        carpetas=[]
        for r in p['rutas']:
            ident=drive.ruta(almacenamiento,raiz,r,crear=False)
            if ident:carpetas.append({'ruta':r,'url':drive.url(ident)})
        return {'exito':True,'carpeta':drive.url(raiz),'carpetas':carpetas}
    if operacion=='finalizar':
        if p.get('exportarSheet'):
            # La exportación histórica opcional se mantiene con el puente que
            # ya la implementaba; no se degrada a un correo sin ese documento.
            from app.db import SessionLocal
            from app.services import integraciones,entregas
            with SessionLocal() as db:legado=integraciones.google(db,cuenta,legado=True)
            if integraciones.conexion_lista(legado):return entregas.llamar_conexion(operacion,clave,p,legado)
        return gmail.finalizar(cuenta,almacenamiento,clave,p)
    raise RuntimeError('GOOGLE_OPERACION: Esta operación requiere el puente anterior o una API compatible.')
