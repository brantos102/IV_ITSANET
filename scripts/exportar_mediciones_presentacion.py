"""Exportación MySQL de solo lectura, sin importar ni iniciar la aplicación."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo


def periodo(desde, hasta):
    zona=ZoneInfo('America/Guayaquil')
    a=datetime.fromisoformat(desde).replace(tzinfo=zona)
    b=datetime.fromisoformat(hasta).replace(tzinfo=zona)
    if b<=a or b-a>timedelta(days=31): raise ValueError('El periodo debe ser positivo y de hasta 31 días.')
    return a.astimezone(timezone.utc).replace(tzinfo=None),b.astimezone(timezone.utc).replace(tzinfo=None)


def sanear(filas):
    eventos=[]
    for f in filas:
        # Lista cerrada: no exportar usuarios, referencias, recepción ni datos JSON completos.
        e={'proceso':str(f.get('proceso') or ''),'estado':str(f.get('estado') or ''),
           'fecha':f['fecha'].isoformat(timespec='seconds')+'Z'}
        try:
            d=float(f.get('duracionMs'))
            if 0<=d<86400000 and d==d:e['duracionMs']=d
        except (TypeError,ValueError,OverflowError):pass
        eventos.append(e)
    return eventos


def exportar(desde,hasta,limite):
    import pymysql
    from sqlalchemy.engine import make_url
    a,b=periodo(desde,hasta)
    u=make_url(os.environ.get('VAL_DATABASE_URL',''))
    if not u.drivername.startswith(('mysql','mariadb')) or not u.database:
        raise ValueError('No se recibió una conexión MySQL de la aplicación.')
    opciones={k:v for k,v in u.query.items() if k in {'ssl_ca','ssl_cert','ssl_key','ssl_verify_cert','ssl_verify_identity','unix_socket'}}
    for k in ('ssl_verify_cert','ssl_verify_identity'):
        if k in opciones:opciones[k]=str(opciones[k]).lower() in ('true','1','yes')
    con=pymysql.connect(host=u.host or 'localhost',port=u.port or 3306,user=u.username,password=u.password,
        database=u.database,charset='utf8mb4',connect_timeout=5,read_timeout=12,write_timeout=5,autocommit=True,**opciones)
    try:
        with con.cursor(pymysql.cursors.DictCursor) as c:
            c.execute("SET SESSION time_zone='+00:00'")
            c.execute('SELECT VERSION() AS version');v=c.fetchone()['version']
            c.execute('SET SESSION max_statement_time=8' if 'mariadb' in v.lower() else 'SET SESSION MAX_EXECUTION_TIME=8000')
            c.execute('START TRANSACTION READ ONLY')
            c.execute('''SELECT creado_en AS fecha,
                JSON_UNQUOTE(JSON_EXTRACT(datos,'$.proceso')) AS proceso,
                JSON_UNQUOTE(JSON_EXTRACT(datos,'$.estado')) AS estado,
                JSON_UNQUOTE(JSON_EXTRACT(datos,'$.duracionMs')) AS duracionMs
                FROM app_auditoria_general
                WHERE creado_en >= %s AND creado_en < %s
                  AND accion IN ('PROCESO_FOTO','PROCESO_CORREO')
                ORDER BY creado_en,id LIMIT %s''',(a,b,limite+1))
            filas=c.fetchall()
            return {'formato':'IV-ITSANET-mediciones-1','generadoEn':datetime.now(timezone.utc).isoformat(),
                'periodo':{'desde':desde,'hastaExclusivo':hasta,'zona':'America/Guayaquil'},
                'fuente':'app_auditoria_general: PROCESO_FOTO / PROCESO_CORREO',
                'limite':limite,'truncado':len(filas)>limite,'eventos':sanear(filas[:limite]),
                'alcance':'duracionMs mide el intento FOTO exitoso; no incluye espera en cola ni captura. No mide el ciclo completo de conteo.'}
    finally:
        con.rollback();con.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--desde',required=True,help='Fecha y hora local Ecuador, inclusiva: 2026-10-28T08:00')
    p.add_argument('--hasta',required=True,help='Fecha y hora local Ecuador, exclusiva: 2026-10-28T18:00')
    p.add_argument('--limite',type=int,default=10000)
    p.add_argument('--salida',type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.limite<=10000:p.error('Límite permitido: 1 a 10000.')
    try:
        datos=exportar(a.desde,a.hasta,a.limite)
        a.salida.parent.mkdir(parents=True,exist_ok=True)
        # Evita sobrescribir cualquier archivo existente y crea con permiso 0600.
        fd=os.open(a.salida,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(datos,f,ensure_ascii=False,indent=2)
        print(str(a.salida))
    except Exception as exc:
        # No imprimir mensajes del driver: pueden contener host, usuario o URI.
        print('No se generó el JSON. Tipo: '+type(exc).__name__+'. Revisar periodo, permisos, conexión y tablas con el administrador.')
        raise SystemExit(1) from None


if __name__=='__main__':main()
