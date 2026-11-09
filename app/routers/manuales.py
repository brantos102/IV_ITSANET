"""Publicación autenticada del manual de usuario. El técnico no tiene ruta HTTP."""
import json
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app import config
from app.security import usuario_actual

router=APIRouter(prefix='/api/app/manuales',tags=['manuales'])
VERSION=re.compile(r'\d{8}T\d{6}Z-[a-f0-9]{12}')
CSP="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-scripts allow-modals allow-downloads allow-top-navigation-by-user-activation"


@router.get('/usuario/{formato}')
def manual_usuario(formato:str,version:str|None=None,descargar:bool=False,_=Depends(usuario_actual)):
    if formato not in ('html','pdf'):raise HTTPException(404,'Formato de manual no disponible.')
    raiz=config.MANUALES_DIR/'usuario'
    try:
        if version is None:version=json.loads((raiz/'actual.json').read_text())['version']
        if not isinstance(version,str) or not VERSION.fullmatch(version):raise ValueError('Versión inválida')
        carpeta=raiz/'versiones'/version
        archivo=carpeta/('Manual-usuario-IV-ITSANET.'+formato)
        # No seguir enlaces que permitan publicar otro documento del servidor.
        if carpeta.is_symlink() or archivo.is_symlink() or archivo.resolve().parent!=carpeta.resolve():raise ValueError('Ruta inválida')
        if not archivo.is_file():raise FileNotFoundError()
    except FileNotFoundError:
        raise HTTPException(404,'El manual de usuario todavía no está publicado. Solicita al responsable su publicación.') from None
    except (OSError,ValueError,KeyError,TypeError):
        raise HTTPException(503,'No se pudo verificar la versión publicada del manual. Solicita revisión al administrador.') from None
    cabeceras={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}
    if formato=='html':cabeceras['Content-Security-Policy']=CSP
    return FileResponse(archivo,media_type='text/html' if formato=='html' else 'application/pdf',
        filename=archivo.name,content_disposition_type='attachment' if descargar else 'inline',headers=cabeceras)
