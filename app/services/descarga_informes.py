"""Una petición, un archivo o ZIP temporal; nunca genera ni envía un informe."""
from tempfile import SpooledTemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED
from urllib.parse import quote
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from app.models import AppInforme, AppArchivo, utcnow
from app.services import archivos, ajustes, app_modelo as m


def descargar(db, ident, origen, usuario):
    f=db.get(AppInforme,ident)
    if not f:raise HTTPException(404,'Informe no encontrado')
    m.obtener(db,f.recepcion,bloquear=True)
    db.refresh(f,with_for_update=True)
    seleccion=[a for a in f.datos.get('archivos',[]) if not origen or a.get('origen')==origen]
    if not seleccion:raise HTTPException(404,'No hay un documento para ese packing list')
    documentos=[db.get(AppArchivo,a['id']) for a in seleccion]
    if any(not a or a.recepcion!=f.recepcion or not archivos.ruta(a).is_file() for a in documentos):
        raise HTTPException(409,'Falta un archivo del informe. Genera el informe actualizado; los demás documentos se conservan.')
    nombres=[a.nombre for a in documentos]
    if len(set(nombres))!=len(nombres) or any('/' in n or '\\' in n or n in ('.','..') for n in nombres):
        raise HTTPException(409,'Los nombres de documentos requieren revisión antes de crear el ZIP.')
    registro={'usuario':usuario,'fecha':m._iso(utcnow()),'origen':origen or 'TODOS'}
    f.datos={**f.datos,'descargas':[*f.datos.get('descargas',[]),registro][-100:]}
    ajustes.auditar(db,usuario,'DESCARGA_SOLICITADA',f.recepcion,{'informeId':f.id,'origen':origen or 'TODOS'})
    db.commit()
    if len(documentos)==1:
        a=documentos[0]
        return FileResponse(archivos.ruta(a),media_type=a.mime,filename=a.nombre,headers={'Cache-Control':'private, no-store'})
    temporal=SpooledTemporaryFile(max_size=8*1024*1024)
    try:
        with ZipFile(temporal,'w',compression=ZIP_DEFLATED) as z:
            for a in documentos:z.write(archivos.ruta(a),a.nombre)
        temporal.seek(0)
    except Exception:
        temporal.close();raise
    nombre='Informes_'+f.recepcion+'_R'+str(f.numero).zfill(4)+'.zip'
    return StreamingResponse(iter(lambda:temporal.read(65536),b''),media_type='application/zip',
        headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(nombre,safe=''),'Cache-Control':'private, no-store'},
        background=BackgroundTask(temporal.close))
