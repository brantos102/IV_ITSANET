"""Diagnóstico de lectura, sin ignorar TLS: python scripts/comprobar_https.py."""
import argparse
import json
import socket
import ssl
import urllib.request
from urllib.parse import urlsplit


def comprobar(url,ca=None):
    u=urlsplit(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise ValueError('Usa una dirección HTTPS raíz, sin usuario, rutas ni parámetros.')
    puerto=u.port or 443
    ctx=ssl.create_default_context(cafile=ca)
    resultado={'servidor':u.hostname,'puerto':puerto,'correcto':False,'comprobaciones':[]}
    def anotar(paso,detalle):resultado['comprobaciones'].append({'paso':paso,'detalle':detalle})
    try:
        ips=sorted({d[4][0] for d in socket.getaddrinfo(u.hostname,puerto,type=socket.SOCK_STREAM)})
        anotar('DNS',', '.join(ips))
        with socket.create_connection((u.hostname,puerto),timeout=6) as sock:
            with ctx.wrap_socket(sock,server_hostname=u.hostname) as tls:
                cert=tls.getpeercert()
                anotar('TLS','Cadena confiable y nombre validado; '+str(tls.version()))
                anotar('Certificado',{'vence':cert.get('notAfter'),'nombres':[v for tipo,v in cert.get('subjectAltName',[]) if tipo in ('DNS','IP Address')]})
        for ruta in ('/health','/app/'):
            with urllib.request.urlopen(url.rstrip('/')+ruta,context=ctx,timeout=12) as r:
                if urlsplit(r.url).scheme!='https':raise ValueError('El servidor redirige hacia HTTP.')
                if ruta=='/health' and json.load(r).get('ok') is not True:raise ValueError('La salud no corresponde a una app lista.')
                anotar(ruta,'HTTP '+str(r.status))
        resultado['correcto']=True
    except Exception as exc:
        resultado['error']=str(exc)
    return resultado


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='https://apps.flexnetuio.com:8443')
    p.add_argument('--ca',help='CA corporativa en PEM, solo si TI la proporcionó.')
    args=p.parse_args()
    try:r=comprobar(args.url,args.ca)
    except ValueError as e:p.error(str(e))
    print(json.dumps(r,ensure_ascii=False,indent=2))
    raise SystemExit(0 if r['correcto'] else 1)
