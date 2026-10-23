"""Canal autenticado de invalidación; nunca transmite el contenido de un correo."""
import asyncio
import json
import time
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.security import usuario_actual
from app.services import app_modelo as m, cambios_recepcion as cambios, ajustes

router=APIRouter(prefix='/api/operacion',tags=['actualizacion'])


def _validar(db,codigo):
    if codigo:return m.obtener(db,codigo).codigo
    return ''


def _visible(datos,codigo,operador_id,ver_equipo):
    datos={k:v for k,v in datos.items() if k!='versionesRecepcion'}
    if ver_equipo:return datos
    if codigo:
        propios={p['sku'] for p in datos.get('equipoSku',[]) if p['operadorId']==operador_id}
        return {**datos,'equipoSku':[p for p in datos.get('equipoSku',[]) if p['sku'] in propios]}
    secciones=datos['secciones']
    return {**datos,'equipoSku':[],'secciones':{k:v for k,v in secciones.items() if k!='presencia'} if isinstance(secciones,dict) else [k for k in secciones if k!='presencia']}


@router.get('/cambios/estado')
@router.get('/recepciones/{codigo}/cambios/estado')
def estado(codigo:str='',db:Session=Depends(get_db),op=Depends(usuario_actual)):
    codigo=_validar(db,codigo)
    ver_equipo=bool(ajustes.permisos(db,op).get('verEquipo'))
    datos=cambios.leer_estado(codigo)
    return _visible(datos,codigo,op.id,ver_equipo)


@router.get('/cambios')
@router.get('/recepciones/{codigo}/cambios')
async def escuchar(request:Request,codigo:str='',db:Session=Depends(get_db),op=Depends(usuario_actual)):
    codigo=_validar(db,codigo)
    ver_equipo=bool(ajustes.permisos(db,op).get('verEquipo'));operador_id=op.id
    # La dependencia autentica primero. Ninguna conexión del pool permanece
    # ocupada mientras el navegador espera; se revalida al reconectar.
    db.close()
    async def transmitir():
        c=cambios.canal(codigo);cola=c.suscribir();limite=time.monotonic()+50
        try:
            yield 'retry: 1000\n\n'
            while time.monotonic()<limite and not await request.is_disconnected():
                try:aviso=await asyncio.wait_for(cola.get(),timeout=10)
                except asyncio.TimeoutError:
                    yield ': conexion activa\n\n';continue
                if aviso is None:return
                aviso=_visible(aviso,codigo,operador_id,ver_equipo)
                yield 'event: cambio\ndata: '+json.dumps(aviso,ensure_ascii=False,separators=(',',':'))+'\n\n'
                if not aviso['existe']:return
        finally:await c.retirar(cola)
    return StreamingResponse(transmitir(),media_type='text/event-stream',headers={
        'Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no'})
