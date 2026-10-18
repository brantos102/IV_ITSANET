"""Avatares pequeños, privados y saneados; incluidos en el respaldo MySQL."""
import base64
import binascii
import hashlib
import io
import warnings
from fastapi import HTTPException
from sqlalchemy import select
from PIL import Image, ImageOps, UnidentifiedImageError
from app.models import AppConfig, Operador
from app.services import ajustes


def clave(ident):
    return 'perfil:foto:'+str(ident)


def url(db,ident):
    f=db.get(AppConfig,clave(ident))
    return f'/api/auth/operadores/{ident}/foto?v='+f.datos['sha256'][:16] if f else ''


def guardar(db,ident,datos,actor):
    op=db.scalar(select(Operador).where(Operador.id==ident).with_for_update().execution_options(populate_existing=True))
    if not op:raise HTTPException(404,'Usuario no encontrado')
    bruto=datos.get('base64')
    if not isinstance(bruto,str) or len(bruto)>3_000_000:raise HTTPException(413,'Foto de perfil: máximo 2 MB. Elige una imagen más pequeña.')
    try:
        contenido=base64.b64decode(bruto,validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contenido)) as imagen:
                if imagen.format not in ('JPEG','PNG','WEBP') or imagen.width*imagen.height>20_000_000:
                    raise ValueError('imagen no admitida')
                imagen=ImageOps.fit(ImageOps.exif_transpose(imagen).convert('RGB'),(256,256))
                salida=io.BytesIO();imagen.save(salida,'JPEG',quality=82,optimize=True)
    except (ValueError,binascii.Error,UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'Elige una fotografía JPEG, PNG o WebP válida.') from None
    contenido=salida.getvalue();sha=hashlib.sha256(contenido).hexdigest()
    f=db.get(AppConfig,clave(ident)) or AppConfig(clave=clave(ident))
    f.datos={'base64':base64.b64encode(contenido).decode(),'sha256':sha};f.usuario=actor;db.add(f)
    ajustes.auditar(db,actor,'FOTO_PERFIL_ACTUALIZADA',op.usuario,{'sha256':sha});db.commit()
    return {'photoURL':url(db,ident),'mensaje':'Foto de perfil actualizada.'}
