"""Revisión MySQL de solo lectura; no inicia la aplicación ni ejecuta migraciones."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import unicodedata


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD',str(texto or '').upper()) if not unicodedata.combining(c)).strip()


def clasificar_operativa(r,excluir=()):
    """No adivina por un SKU ni por una palabra dentro de una descripción real."""
    codigo=normalizar(r['codigo']);cliente=normalizar(r.get('cliente'));descripcion=normalizar(r.get('descripcion'))
    if codigo in {normalizar(x) for x in excluir}:return 'EXCLUSION_EXPLICITA'
    if normalizar(r.get('estado')) in ('ELIMINADA','BORRADA'):return 'ESTADO_ELIMINADO'
    marca=r'(^|[^A-Z0-9])(DEMO|PRUEBAS?|TEST|TESTING|SIMULACION|DEMOSTRACION|CAPACITACION)(?=$|[^A-Z])'
    if re.search(marca,codigo):return 'CODIGO_MARCADO_PRUEBA'
    if cliente in {'DEMO','PRUEBA','PRUEBAS','TEST','TESTING','CLIENTE DE PRUEBA','CLIENTE PRUEBA'}:return 'CLIENTE_MARCADO_PRUEBA'
    if descripcion in {'DEMO','PRUEBA','PRUEBAS','TEST','TESTING','PRUEBA DEL SISTEMA','PRUEBA DEL APLICATIVO','PRUEBA APP','RECEPCION DE PRUEBA','RECEPCION DEMO'}:return 'DESCRIPCION_MARCADA_PRUEBA'
    return None


def fecha_utc(valor):
    fecha = datetime.fromisoformat(valor.replace('Z', '+00:00'))
    if fecha.tzinfo is None:
        raise ValueError('La fecha debe incluir zona horaria, por ejemplo -05:00.')
    return fecha.astimezone(timezone.utc).replace(tzinfo=None)


def serializar(valor):
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    raise TypeError(type(valor).__name__)


def revisar(url, desde, hasta, historial_completo=False, solo_operativas=False, excluir=()):
    import pymysql
    from sqlalchemy.engine import make_url
    u = make_url(url)
    if not u.drivername.startswith(('mysql', 'mariadb')) or not u.database:
        raise ValueError('La revisión requiere la conexión MySQL configurada.')
    ssl = {k: v for k, v in u.query.items() if k in
           ('ssl_ca', 'ssl_cert', 'ssl_key', 'unix_socket')}
    for k in ('ssl_verify_cert', 'ssl_verify_identity'):
        if k in u.query:
            ssl[k] = str(u.query[k]).lower() in ('true', '1', 'yes')
    con = pymysql.connect(host=u.host or 'localhost', port=u.port or 3306,
        user=u.username, password=u.password, database=u.database, charset='utf8mb4',
        connect_timeout=5, read_timeout=10, write_timeout=5, autocommit=True,
        cursorclass=pymysql.cursors.DictCursor, **ssl)
    try:
        with con.cursor() as c:
            c.execute('SELECT VERSION() AS version')
            version = c.fetchone()['version']
            c.execute('SET SESSION time_zone = \'+00:00\'')
            c.execute('SET SESSION max_statement_time=5' if 'mariadb' in version.lower()
                      else 'SET SESSION MAX_EXECUTION_TIME=5000')
            c.execute('START TRANSACTION READ ONLY')
            sql = '''SELECT r.codigo, r.cliente, r.descripcion, r.estado, r.creado_en, r.cerrada_en
                FROM app_recepciones r
                WHERE (r.creado_en >= %s AND r.creado_en < %s)
                OR (r.cerrada_en >= %s AND r.cerrada_en < %s)
                OR EXISTS (SELECT 1 FROM app_eventos e WHERE e.recepcion=r.codigo
                    AND e.creado_en >= %s AND e.creado_en < %s)
                OR EXISTS (SELECT 1 FROM app_archivos a WHERE a.recepcion=r.codigo
                    AND a.creado_en >= %s AND a.creado_en < %s)
                OR EXISTS (SELECT 1 FROM app_entregas t WHERE t.recepcion=r.codigo
                    AND t.creado_en >= %s AND t.creado_en < %s)
                ORDER BY r.creado_en, r.codigo LIMIT 1001'''
            if historial_completo:
                c.execute('''SELECT codigo, cliente, descripcion, estado, creado_en, cerrada_en
                    FROM app_recepciones ORDER BY creado_en, codigo LIMIT 1001''')
            else:
                c.execute(sql, (desde, hasta)*5)
            filas = list(c.fetchall())
            if len(filas) > 1000:
                raise ValueError('Más de 1000 recepciones: reducir el período de revisión.')
            registros_consultados=len(filas);excluidas=[];por_revisar=[]
            if solo_operativas:
                operativas=[]
                for r in filas:
                    motivo=clasificar_operativa(r,excluir)
                    if motivo:
                        excluidas.append({**{k:r.get(k) for k in ('codigo','cliente','descripcion','estado')},'motivo':motivo})
                    else:
                        operativas.append(r)
                        if re.search(r'\b(DEMO|PRUEBAS?|TEST|TESTING|SIMULACION|DEMOSTRACION|CAPACITACION)\b',normalizar(r.get('descripcion'))):
                            por_revisar.append({k:r.get(k) for k in ('codigo','cliente','descripcion')})
                filas=operativas
            por_codigo = {r['codigo']: {**r, 'drive': [], 'correos': []} for r in filas}
            if por_codigo:
                codigos = tuple(por_codigo)
                marcas = ','.join(['%s']*len(codigos))
                consultas = {
                    'productos': f'''SELECT recepcion, COUNT(*) referencias,
                        COALESCE(SUM(esperado),0) unidades_declaradas,
                        COALESCE(SUM(contado),0) unidades_contadas,
                        SUM(CASE WHEN verificado THEN 1 ELSE 0 END) referencias_revisadas,
                        SUM(CASE WHEN tiene_pnc THEN 1 ELSE 0 END) referencias_con_pnc
                        FROM app_skus WHERE recepcion IN ({marcas}) GROUP BY recepcion''',
                    'actividad_periodo': f'''SELECT recepcion, COUNT(*) eventos,
                        SUM(CASE WHEN tipo='CONTEO' THEN 1 ELSE 0 END) registros_conteo,
                        MIN(creado_en) primera_actividad, MAX(creado_en) ultima_actividad
                        FROM app_eventos WHERE recepcion IN ({marcas})
                        AND creado_en >= %s AND creado_en < %s GROUP BY recepcion''',
                    'archivos': f'''SELECT recepcion, COUNT(*) archivos,
                        SUM(CASE WHEN drive_id IS NOT NULL AND drive_id<>'' THEN 1 ELSE 0 END)
                        con_referencia_drive FROM app_archivos
                        WHERE recepcion IN ({marcas}) GROUP BY recepcion''',
                    'drive': f'''SELECT recepcion, estado, COUNT(*) cantidad
                        FROM app_copias_drive WHERE recepcion IN ({marcas})
                        GROUP BY recepcion, estado''',
                    'correos': f'''SELECT recepcion, estado, COUNT(*) cantidad
                        FROM app_entregas WHERE recepcion IN ({marcas})
                        GROUP BY recepcion, estado''',
                }
                for grupo, sql in consultas.items():
                    c.execute(sql, codigos + ((desde, hasta) if grupo == 'actividad_periodo' else ()))
                    for fila in c.fetchall():
                        codigo = fila.pop('recepcion')
                        if grupo in ('drive', 'correos'):
                            por_codigo[codigo][grupo].append(fila)
                        else:
                            por_codigo[codigo][grupo] = fila
            for recepcion in por_codigo.values():
                productos = recepcion.get('productos', {})
                total = productos.get('referencias', 0)
                recepcion['revisionFisicaCompleta'] = bool(total and
                    productos.get('referencias_revisadas', 0) == total)
                recepcion['cerradaOEntregada'] = recepcion['estado'] in ('CERRADA','ENTREGADA')
            return {'consultadoEn': datetime.now(timezone.utc).isoformat(),
                'historialCompleto': historial_completo,
                'desdeInclusiveUTC': desde.replace(tzinfo=timezone.utc).isoformat(),
                'hastaExclusivaUTC': hasta.replace(tzinfo=timezone.utc).isoformat(),
                'soloLectura': True, 'totalRecepciones': len(filas),
                'soloOperativas':solo_operativas,'registrosConsultados':registros_consultados,
                'excluidasPruebaOEliminadas':excluidas,'descripcionesPorRevisar':por_revisar,
                'criterioExclusion': 'Solo filas existentes de app_recepciones; las eliminadas físicamente no se consultan. En modo operativo se excluyen etiquetas explícitas de prueba en código, cliente o descripción y exclusiones solicitadas. Las descripciones ambiguas se muestran para revisión y no se descartan automáticamente.',
                'criterio': ('Todo el historial disponible; los agregados de actividad usan el período indicado.'
                    if historial_completo else 'Recepciones con alta, cierre, conteo, archivo o entrega en el período.'),
                'totalRevisionFisicaCompleta': sum(r['revisionFisicaCompleta'] for r in por_codigo.values()),
                'totalCerradasOEntregadas': sum(r['cerradaOEntregada'] for r in por_codigo.values()),
                'alcance': 'Estado SQL en la consulta. No prueba accesibilidad remota de cada imagen ni confirma destinatarios de correo; no mide rendimiento.',
                'recepciones': list(por_codigo.values())}
    finally:
        try:
            con.rollback()
        finally:
            con.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--desde', default='2026-10-30T11:00:00-05:00')
    p.add_argument('--hasta', default=datetime.now(timezone.utc).isoformat())
    p.add_argument('--todo-historial', action='store_true', help='Incluye todas las recepciones de la base, independientemente de su fecha.')
    p.add_argument('--solo-operativas',action='store_true',help='Excluye registros marcados explícitamente como demo/prueba y estados eliminados; informa casos ambiguos.')
    p.add_argument('--excluir',action='append',default=[],help='Código exacto confirmado como prueba; se puede repetir. No elimina datos.')
    p.add_argument('--salida', type=Path, required=True)
    a = p.parse_args()
    try:
        desde, hasta = fecha_utc(a.desde), fecha_utc(a.hasta)
        if desde >= hasta:
            raise ValueError('El período no es válido.')
        resultado = revisar(os.environ['VAL_DATABASE_URL'], desde, hasta, a.todo_historial,a.solo_operativas,a.excluir)
        texto = json.dumps(resultado, default=serializar, ensure_ascii=False, indent=2)
        a.salida.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(os.open(a.salida, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
            f.write(texto + '\n')
        print(texto)
        print('Archivo privado:', a.salida)
    except Exception as exc:
        p.exit(1, 'No se completó la revisión. Tipo: ' + type(exc).__name__ +
               '. Revisar conexión, período y archivo de salida; no se modificó la base.\n')


if __name__ == '__main__':
    main()
