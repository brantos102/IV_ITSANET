"""Diagnóstico de lectura, exclusivamente en el contenedor de pruebas públicas.

No muestra contraseñas, claves, /exec ni respuestas originales de Google.
Solo permite la operación Google `estado`: sin correos ni cambios en Drive.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4


def diagnosticar(db, *, red=True):
    from sqlalchemy import select
    from app import config
    from app.models import AppConfig, AppCopiaDrive, Operador, Rol
    from app.services import entregas, integraciones

    raiz = Path(__file__).resolve().parents[1]
    fuente = (raiz / 'firebase/public/recepciones.html').read_text(encoding='utf-8')
    version = re.search(r'20\d{6}-\d+', fuente)
    salida = {'entorno': 'PRUEBAS', 'frontendEnDisco': version.group() if version else 'Sin identificar',
              'operacionesGooglePermitidas': ['estado'], 'perfiles': [], 'conexiones': [],
              'colaFotos': dict(Counter(db.scalars(select(AppCopiaDrive.estado))))}
    perfiles = list(db.scalars(select(Operador).where(Operador.activo.is_(True),
        Operador.rol.in_([Rol.ADMIN, Rol.SUPERVISOR]))))
    emails = Counter(str(email).strip().lower() for email in db.scalars(
        select(Operador.email).where(Operador.activo.is_(True), Operador.email.is_not(None))) if email)
    for op in perfiles:
        email = (op.email or '').strip().lower()
        salida['perfiles'].append({'usuario': op.usuario, 'rol': op.rol.value,
            'correoRegistrado': bool(email), 'correoRepetido': bool(email and emails[email] > 1)})
    conexiones = list(db.scalars(select(AppConfig).where(AppConfig.clave.like('g:%'))))
    general = db.get(AppConfig, 'google')
    if general: conexiones.append(general)
    salida['conexionesRegistradas'] = len(conexiones)
    if len(conexiones) > 3:
        salida['limite'] = 'Se revisan hasta tres conexiones por ejecución para limitar el tiempo de diagnóstico.'
    for numero, f in enumerate(conexiones[:3], 1):
        datos = f.datos or {}
        supervisor = str(datos.get('supervisor') or '').strip().lower()
        fila = {'conexion': numero, 'tipo': 'Personal' if supervisor else 'General',
                'urlRegistrada': bool(datos.get('url')), 'claveCifradaRegistrada': bool(datos.get('credencial')),
                'archivoCifradoDisponible': (config.DATA_DIR / 'secretos/integraciones.key').is_file(),
                'fichaActivaCoincide': emails[supervisor] == 1 if supervisor else False}
        if not red:
            fila['verificacion'] = 'Omitida por --sin-red'
        elif not fila['fichaActivaCoincide']:
            fila['verificacion'] = 'Completa un correo único en la ficha activa y vincula su conexión personal antes de verificar.'
        else:
            destino = {}
            try:
                # URL y clave permanecen dentro del proceso y no forman parte del informe.
                destino = integraciones.google(db, supervisor)
                r = entregas.llamar_conexion('estado', uuid4().hex, {'usuario': supervisor}, destino)
                fila.update(verificacion='Confirmada' if str(r.get('remitente') or '').lower() == supervisor else 'Cuenta ejecutora diferente',
                            carpetaConfirmada=bool(r.get('carpeta')), fotosAuditables='fotosAuditables' in r.get('capacidades', []))
            except RuntimeError as exc:
                # El servicio traduce estos errores a mensajes controlados, sin cuerpos externos.
                mensaje = str(exc)
                for campo in ('secreto', 'url'):
                    if destino.get(campo): mensaje = mensaje.replace(destino[campo], '[reservado]')
                fila['verificacion'] = mensaje
            except Exception as exc:
                fila['verificacion'] = 'No se completó la comprobación (' + type(exc).__name__ + '). Revisa configuración privada y conectividad.'
        salida['conexiones'].append(fila)
    if not conexiones:
        salida['accion'] = 'Este piloto no tiene un puente Google registrado. Configura la ficha y Mi correo de informes con una carpeta de pruebas.'
    salida['alcance'] = 'Solo lectura: no envía correos, no copia fotos, no crea carpetas ni modifica registros.'
    return salida


def main():
    if os.getenv('ITSANET_PRUEBAS_PUBLICAS') != '1':
        print('Diagnóstico rechazado: solo se permite en PRUEBAS públicas.', file=sys.stderr)
        return 2
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sin-red', action='store_true')
    args = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db import SessionLocal
    try:
        with SessionLocal() as db:
            resultado = diagnosticar(db, red=not args.sin_red)
            db.rollback()
        print(json.dumps(resultado, ensure_ascii=True, indent=2))
    except Exception as exc:
        print(json.dumps({'error': 'No se pudo leer el estado del piloto', 'tipo': type(exc).__name__}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
