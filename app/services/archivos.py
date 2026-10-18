"""Almacen local de fotos e informes: UUID, checksum y descarga autenticada."""
import base64
import binascii
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import DATA_DIR
from app.models import AppArchivo, AppRecepcion, AppArchivoSku
from app.services.normalize import normalizar_sku

LIMITE = 12 * 1024 * 1024


def ruta(archivo: AppArchivo) -> Path:
    return DATA_DIR / 'app_archivos' / archivo.id


def guardar(db, codigo: str, tipo: str, datos: dict, usuario: str, confirmar=True) -> AppArchivo:
    codigo = str(codigo).strip().upper()
    if db.get(AppRecepcion, codigo) is None:
        raise HTTPException(404, 'La recepcion no existe')
    if tipo not in ('foto', 'informe'):
        raise HTTPException(422, 'Tipo de archivo no permitido')
    contenido = datos.get('base64')
    if not isinstance(contenido, str) or len(contenido) > (LIMITE * 4 // 3 + 4):
        raise HTTPException(413, 'El archivo supera los 12 MB')
    try:
        bruto = base64.b64decode(contenido, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, 'Archivo base64 invalido') from None
    if not bruto or len(bruto) > LIMITE:
        raise HTTPException(422, 'Archivo vacio o demasiado grande')
    if tipo == 'foto':
        if bruto.startswith(b'\xff\xd8\xff'):
            mime, extension = 'image/jpeg', '.jpg'
        elif bruto.startswith(b'\x89PNG\r\n\x1a\n'):
            mime, extension = 'image/png', '.png'
        elif bruto.startswith(b'RIFF') and bruto[8:12] == b'WEBP':
            mime, extension = 'image/webp', '.webp'
        else:
            raise HTTPException(422, 'La foto debe ser JPEG, PNG o WebP')
    else:
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(bruto)) as libro:
                if 'xl/workbook.xml' not in libro.namelist():
                    raise ValueError('sin libro')
        except (zipfile.BadZipFile, ValueError):
            raise HTTPException(422, 'El informe debe ser un archivo XLSX') from None
        mime, extension = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'
    sha = hashlib.sha256(bruto).hexdigest()
    sku = normalizar_sku(datos.get('sku')) if tipo == 'foto' else ''
    if len(sku) > 80:
        raise HTTPException(422, 'SKU demasiado largo')
    def vincular(a):
        if sku and db.get(AppArchivoSku, (a.id, sku)) is None:
            db.add(AppArchivoSku(archivo_id=a.id, sku=sku))
            try:
                db.commit() if confirmar else db.flush()
            except IntegrityError:
                db.rollback()
                if db.get(AppArchivoSku, (a.id, sku)) is None:
                    raise
    def existente():
        return db.scalar(select(AppArchivo).where(AppArchivo.recepcion == codigo,
            AppArchivo.tipo == tipo, AppArchivo.sha256 == sha))
    anterior = existente()
    if anterior is not None:
        if tipo == 'foto':
            from app.models import AppCopiaDrive
            copia = db.get(AppCopiaDrive, anterior.id)
            if copia and (copia.estado == 'ELIMINADA' or copia.datos.get('accion') == 'papelera'):
                raise HTTPException(409, 'Esta imagen fue retirada por supervisión. Selecciona una nueva evidencia.')
        vincular(anterior)
        return anterior
    nombre = str(datos.get('nombre') or (str(datos.get('sku') or 'foto') + extension))
    nombre = nombre.replace('\\', '/').rsplit('/', 1)[-1]
    nombre = ''.join(c for c in nombre if ord(c) >= 32 and ord(c) != 127)[:190]
    if not nombre.lower().endswith(extension):
        nombre += extension
    archivo = AppArchivo(id=uuid4().hex, recepcion=codigo, tipo=tipo,
        nombre=nombre, mime=mime, sha256=sha, bytes=len(bruto), usuario=usuario)
    destino = ruta(archivo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destino.open('xb') as f:
            os.chmod(destino, 0o600)
            f.write(bruto)
        db.add(archivo)
        if sku:
            db.add(AppArchivoSku(archivo_id=archivo.id, sku=sku))
        db.commit() if confirmar else db.flush()
    except IntegrityError:
        db.rollback()
        destino.unlink(missing_ok=True)
        anterior = existente()
        if anterior is not None:
            vincular(anterior)
            return anterior
        raise
    except Exception:
        db.rollback()
        destino.unlink(missing_ok=True)
        raise
    return archivo


def miniatura_drive(db, archivo):
    """Miniaturas privadas y acotadas en disco; los originales viven en Drive."""
    from app.models import AppCopiaDrive
    from app.services import entregas
    carpeta=DATA_DIR / 'app_miniaturas'
    destino=carpeta / archivo.id
    if destino.is_file():return destino.read_bytes()
    copia=db.get(AppCopiaDrive,archivo.id)
    if not copia or not archivo.drive_id:raise HTTPException(404,'Imagen sin copia confirmada en Drive')
    try:
        respuesta=entregas.llamar('miniatura',archivo.id,{'usuario':copia.usuario,'fileId':archivo.drive_id})
        contenido=respuesta.get('base64') or ''
        if len(contenido)>400000:raise ValueError('miniatura demasiado grande')
        bruto=base64.b64decode(contenido,validate=True)
        if not (bruto.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')) or bruto.startswith(b'RIFF') and bruto[8:12]==b'WEBP'):raise ValueError('formato de miniatura no válido')
    except (RuntimeError,ValueError,binascii.Error):
        raise HTTPException(502,'No se pudo cargar la vista previa privada. Actualiza el puente Google o abre la imagen en Drive.') from None
    carpeta.mkdir(parents=True,exist_ok=True)
    temporal=carpeta / (archivo.id+'.'+uuid4().hex+'.tmp')
    try:
        with temporal.open('xb') as f:os.chmod(temporal,0o600);f.write(bruto)
        temporal.replace(destino)
    finally:temporal.unlink(missing_ok=True)
    archivos=[]
    for p in carpeta.iterdir():
        try:
            if len(p.name)==32:archivos.append((p.stat().st_mtime,p))
        except FileNotFoundError:pass
    total=0
    for _,p in sorted(archivos,reverse=True):
        try:
            total+=p.stat().st_size
            if total>20*1024*1024:p.unlink(missing_ok=True)
        except FileNotFoundError:pass
    return bruto
