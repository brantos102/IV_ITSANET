"""Crea secretos exclusivos de una instancia nueva de pruebas, nunca producción."""
import os
from pathlib import Path
import secrets
import sys


def preparar(carpeta):
    carpeta=Path(carpeta);carpeta.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(carpeta,0o700)
    entorno=carpeta/'entorno.env'
    if entorno.exists():
        valores=dict(l.split('=',1) for l in entorno.read_text().splitlines() if '=' in l)
        requeridas=('ITSANET_LOCAL_MYSQL_PASSWORD','ITSANET_LOCAL_ROOT_PASSWORD','ITSANET_LOCAL_SESSION_KEY',
                    'ITSANET_LOCAL_ADMIN_PASSWORD','ITSANET_PRUEBAS_SUP_PASSWORD','ITSANET_PRUEBAS_OP_PASSWORD')
        if any(len(valores.get(k,''))<16 for k in requeridas):raise ValueError('Configuración previa incompleta. Conserva el archivo privado y revisa sus claves antes de continuar.')
        return
    valores={k:secrets.token_hex(24) for k in ('ITSANET_LOCAL_MYSQL_PASSWORD','ITSANET_LOCAL_ROOT_PASSWORD',
        'ITSANET_LOCAL_SESSION_KEY','ITSANET_LOCAL_ADMIN_PASSWORD','ITSANET_PRUEBAS_SUP_PASSWORD','ITSANET_PRUEBAS_OP_PASSWORD')}
    fd=os.open(entorno,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write('\n'.join(k+'='+v for k,v in valores.items())+'\n')
    acceso=carpeta/'accesos-iniciales.txt'
    fd=os.open(acceso,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write('SOLO PRUEBAS. Comparte individualmente por un canal privado. Cambia la contraseña desde Mi cuenta.\n')
        for usuario,k in [('admin','ITSANET_LOCAL_ADMIN_PASSWORD'),('supervisor.prueba','ITSANET_PRUEBAS_SUP_PASSWORD'),('operario.prueba','ITSANET_PRUEBAS_OP_PASSWORD')]:f.write(usuario+' : '+valores[k]+'\n')


if __name__=='__main__':preparar(sys.argv[1])
