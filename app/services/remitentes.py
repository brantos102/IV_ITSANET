"""Separar al autor del cierre de la cuenta Google que envía el informe."""
from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.models import Operador, Rol
from app.services.integraciones import google, puentes_publicos
from app.services.operacion import configuracion, destino_drive


def _disponible(db, correo):
    if not correo:
        return False
    perfiles = db.scalars(select(Operador).where(func.lower(Operador.email) == correo,
        Operador.activo.is_(True), Operador.rol.in_([Rol.ADMIN, Rol.SUPERVISOR])).limit(2)).all()
    if len(perfiles) != 1:
        return False
    puente = google(db, correo)
    return bool(puente['url'] and len(puente['secreto']) >= 32
                and str(puente.get('supervisor') or correo).lower() == correo)


def responsable(db, codigo, propuesto=None):
    politica = configuracion(db)['correo']
    correo = politica['responsable']
    if not correo:
        propuesto = str(propuesto if propuesto is not None else destino_drive(db, codigo).get('supervisor') or '').strip().lower()
        if '@' in propuesto:
            correo = propuesto
        else:
            puentes = {p['supervisor'].lower() for p in puentes_publicos(db) if p.get('supervisor')}
            if len(puentes) == 1:
                correo = next(iter(puentes))
    return correo


def opciones(db, codigo, usuario):
    politica = configuracion(db)['correo']
    correo_responsable = responsable(db, codigo)
    perfiles = db.scalars(select(Operador).where(or_(func.lower(Operador.email) == usuario.lower(),
        func.lower(Operador.usuario) == usuario.lower())).limit(2)).all()
    personal = (perfiles[0].email or '').lower() if len(perfiles) == 1 else ''
    return {'predeterminado': 'PERSONAL' if personal else 'RESPONSABLE', 'opciones': [
        {'modo': 'RESPONSABLE', 'correo': correo_responsable, 'disponible': _disponible(db, correo_responsable)},
        {'modo': 'PERSONAL', 'correo': personal,
         'disponible': politica['permitirPersonal'] and _disponible(db, personal)}]}


def elegir(db, codigo, datos, usuario):
    disponibles = opciones(db, codigo, usuario)
    modo = datos.get('modoRemitente')
    if modo is None:
        # Las peticiones anteriores siguen siendo compatibles; cuando existe
        # un responsable configurado ya se utiliza también desde esas pantallas.
        personal = disponibles['opciones'][1]
        responsable = disponibles['opciones'][0]
        if personal['correo']:
            modo = 'PERSONAL'
        elif responsable['correo']:
            modo = 'RESPONSABLE'
        else:
            return usuario, 'SESION_ANTERIOR'
    if modo not in ('RESPONSABLE', 'PERSONAL'):
        raise HTTPException(422, 'Selecciona correo responsable o mi correo autorizado')
    if str(datos.get('destinatarios') or '').strip() and disponibles['opciones'][1]['correo'] and modo != 'PERSONAL':
        raise HTTPException(422,'El correo debe enviarse desde la cuenta autorizada del supervisor que solicita el envío. Selecciona Mi correo.')
    opcion = next(o for o in disponibles['opciones'] if o['modo'] == modo)
    if not opcion['disponible']:
        raise HTTPException(409, 'El correo ' + ('responsable' if modo == 'RESPONSABLE' else 'personal')
            + ' no está listo. ADMIN debe vincularlo a un supervisor activo y configurar su puente Google en Administración → Drive y envío de correo. No se envió el informe.')
    confirmado = datos.get('remitenteConfirmado')
    if confirmado is not None and str(confirmado).strip().lower() != opcion['correo']:
        raise HTTPException(409, 'Cambió el correo remitente mientras preparabas el cierre. Actualiza y confirma la cuenta antes de enviar.')
    return opcion['correo'], modo
