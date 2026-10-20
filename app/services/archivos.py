"""Almacen local de fotos e informes: UUID, checksum y descarga autenticada."""
import base64
import binascii
import hashlib
import os
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import DATA_DIR
from app.models import AppArchivo, AppRecepcion, AppArchivoSku
from app.services.normalize import normalizar_sku

LIMITE = 12 * 1024 * 1024
_miniaturas_en_curso = threading.BoundedSemaphore(2)
_fallos_miniaturas = OrderedDict()
_bloqueo_miniaturas = threading.Lock()


def _miniatura_en_pausa(clave):
    with _bloqueo_miniaturas:
        return _fallos_miniaturas.get(clave, 0) > time.monotonic()


def _pausar_miniatura(clave):
    with _bloqueo_miniaturas:
        _fallos_miniaturas[clave] = time.monotonic() + 30
        _fallos_miniaturas.move_to_end(clave)
        while len(_fallos_miniaturas) > 256: _fallos_miniaturas.popitem(last=False)


def ruta(archivo: AppArchivo) -> Path:
    return DATA_DIR / 'app_archivos' / archivo.id


def escribir_durable(destino,bruto,*,reemplazar=False):
    """Confirma contenido y entrada de directorio antes de confirmar metadatos."""
    temporal=destino.with_name(destino.name+'.'+uuid4().hex+'.tmp') if reemplazar else destino
    try:
        with temporal.open('xb') as f:
            os.chmod(temporal,0o600)
            f.write(bruto);f.flush();os.fsync(f.fileno())
        if reemplazar:os.replace(temporal,destino)
        if hasattr(os,'O_DIRECTORY'):
            fd=os.open(destino.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
    finally:
        if reemplazar:temporal.unlink(missing_ok=True)


def comprobar_copia(archivo,bruto):
    """Un reintento no confirma una copia local ausente sin respaldo Drive."""
    destino=ruta(archivo)
    if archivo.drive_id:return
    if not destino.is_file() or hashlib.sha256(destino.read_bytes()).hexdigest()!=archivo.sha256:
        destino.parent.mkdir(parents=True,exist_ok=True)
        escribir_durable(destino,bruto,reemplazar=True)


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
        comprobar_copia(anterior,bruto)
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
        escribir_durable(destino,bruto)
        db.add(archivo)
        if sku:
            db.add(AppArchivoSku(archivo_id=archivo.id, sku=sku))
        db.commit() if confirmar else db.flush()
    except IntegrityError:
        db.rollback()
        destino.unlink(missing_ok=True)
        anterior = existente()
        if anterior is not None:
            comprobar_copia(anterior,bruto)
            vincular(anterior)
            return anterior
        raise
    except Exception:
        db.rollback()
        destino.unlink(missing_ok=True)
        raise
    return archivo


def conservar_miniatura(archivo):
    """Vista privada local antes de liberar el original confirmado en Drive."""
    from PIL import Image,ImageOps
    import io
    original=ruta(archivo)
    destino=DATA_DIR/'app_miniaturas'/archivo.id
    if destino.is_file() or not original.is_file():return
    try:
        with Image.open(original) as imagen:
            imagen=ImageOps.exif_transpose(imagen);imagen.thumbnail((960,960))
            salida=io.BytesIO();imagen.convert('RGB').save(salida,format='JPEG',quality=76,optimize=True)
        guardar_miniatura(archivo.id,salida.getvalue())
    except (OSError,ValueError,Image.DecompressionBombError):
        # El original ya está confirmado en Drive. Una miniatura no cambia el
        # acuse de guardado ni provoca otra subida de la misma evidencia.
        return


def guardar_miniatura(ident,bruto):
    carpeta=DATA_DIR/'app_miniaturas';carpeta.mkdir(parents=True,exist_ok=True)
    destino=carpeta/ident
    escribir_durable(destino,bruto,reemplazar=True)
    total=0
    filas=[]
    for p in carpeta.iterdir():
        try:
            if len(p.name)==32:filas.append((p.stat().st_mtime,p))
        except FileNotFoundError:pass
    for _,p in sorted(filas,reverse=True):
        try:
            total+=p.stat().st_size
            if total>20*1024*1024:p.unlink(missing_ok=True)
        except FileNotFoundError:pass


def miniatura_drive(db, archivo):
    """Miniaturas privadas y acotadas en disco; los originales viven en Drive."""
    from app.models import AppCopiaDrive
    from app.services import entregas
    carpeta=DATA_DIR / 'app_miniaturas'
    destino=carpeta / archivo.id
    if destino.is_file():return destino.read_bytes()
    if ruta(archivo).is_file():
        conservar_miniatura(archivo)
        if destino.is_file():return destino.read_bytes()
    copia=db.get(AppCopiaDrive,archivo.id)
    if not copia or not archivo.drive_id:raise HTTPException(404,'Imagen sin copia confirmada en Drive')
    # Conservar solo valores simples y devolver la conexión MySQL antes de
    # esperar a Google. Una vista previa no puede bloquear conteos ni Gmail.
    ident, usuario, file_id = archivo.id, copia.usuario, archivo.drive_id
    clave=(str(DATA_DIR),ident); puente=(str(DATA_DIR),'puente',usuario)
    db.rollback()
    if _miniatura_en_pausa(clave) or _miniatura_en_pausa(puente):
        raise HTTPException(503,'Vista previa temporalmente no disponible. Abre el original en Drive.')
    if not _miniaturas_en_curso.acquire(blocking=False):
        raise HTTPException(503,'Las vistas previas están ocupadas. Abre el original en Drive.')
    try:
        respuesta=entregas.llamar('miniatura',ident,{'usuario':usuario,'fileId':file_id})
        contenido=respuesta.get('base64') or ''
        if len(contenido)>400000:raise ValueError('miniatura demasiado grande')
        bruto=base64.b64decode(contenido,validate=True)
        if not (bruto.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')) or bruto.startswith(b'RIFF') and bruto[8:12]==b'WEBP'):raise ValueError('formato de miniatura no válido')
    except Exception as exc:
        import httpx
        if not isinstance(exc,(RuntimeError,ValueError,binascii.Error,httpx.HTTPError)):raise
        _pausar_miniatura(clave)
        if isinstance(exc,httpx.HTTPError) or isinstance(exc,RuntimeError) and any(p in str(exc).lower() for p in ('puente','despliegue','hmac','clave compartida','no autoriz')):
            _pausar_miniatura(puente)
        logging.getLogger('iv_itsanet.miniaturas').warning('Vista previa no disponible archivo=%s causa=%s; el original no se modifica',ident,type(exc).__name__)
        raise HTTPException(503,'Vista previa temporalmente no disponible. Abre el original en Drive; no vuelvas a subir la foto.') from None
    finally:
        _miniaturas_en_curso.release()
    guardar_miniatura(ident,bruto)
    return bruto
