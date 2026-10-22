"""Redacción libre con bloques calculados y fotos registradas, sin HTML ejecutable."""
from html import escape
from html.parser import HTMLParser
import re
from fastapi import HTTPException

TAGS=set('div p br span strong b em i u s ul ol li h1 h2 h3 h4 blockquote hr table thead tbody tr td th a section small'.split())
VOID={'br','hr','img'}
ESTILOS=set('color background background-color font-family font-size font-weight font-style text-align text-decoration line-height margin margin-top margin-bottom margin-left margin-right padding border border-top border-bottom border-left border-radius width max-width height display vertical-align overflow-wrap'.split())

class Nodo:
    def __init__(self,tag='',attrs=(),texto=''):
        self.tag=tag;self.attrs=dict(attrs);self.hijos=[];self.texto=texto
    def html(self):
        if not self.tag:return escape(self.texto)
        a=''.join(' '+k+'="'+escape(v or '',quote=True)+'"' for k,v in self.attrs.items())
        return '<'+self.tag+a+'>'+('' if self.tag in VOID else ''.join(n.html() for n in self.hijos)+'</'+self.tag+'>')

class Arbol(HTMLParser):
    def __init__(self,html):
        super().__init__(convert_charrefs=True);self.raiz=Nodo('div');self.pila=[self.raiz];self.feed(html)
    def handle_starttag(self,tag,attrs):
        if len(self.pila)>80:raise HTTPException(422,'El formato del correo tiene demasiados niveles. Pega el texto y vuelve a darle formato.')
        n=Nodo(tag,attrs);self.pila[-1].hijos.append(n)
        if tag not in VOID:self.pila.append(n)
    def handle_endtag(self,tag):
        for i in range(len(self.pila)-1,0,-1):
            if self.pila[i].tag==tag:self.pila=self.pila[:i];return
    def handle_data(self,data):self.pila[-1].hijos.append(Nodo(texto=data))


def bloques(html):
    salida={}
    def visitar(n):
        if n.attrs.get('data-correo-bloque'):salida[n.attrs['data-correo-bloque']]=n.html()
        for h in n.hijos:visitar(h)
    visitar(Arbol(html).raiz);return salida


def limpiar(html,base):
    if not isinstance(html,str) or len(html)>300000:raise HTTPException(422,'El cuerpo del correo admite hasta 300.000 caracteres.')
    protegidos=bloques(base);vistos=set();enlaces=set()
    def enlazar(n):
        if n.tag=='a' and n.attrs.get('href'):enlaces.add(n.attrs['href'])
        for h in n.hijos:enlazar(h)
    enlazar(Arbol(base).raiz)
    def nodo(n):
        if not n.tag:return escape(n.texto)
        k=n.attrs.get('data-correo-bloque')
        if k:
            if k.startswith('foto:') and k not in protegidos:return ''
            if k not in protegidos or k in vistos:raise HTTPException(409,'Un bloque o una foto cambió. Actualiza el correo y revisa su selección.')
            vistos.add(k);return '<div data-correo-bloque="'+escape(k,quote=True)+'"></div>'
        if n.tag in ('script','style','iframe','object','svg','math','form','input','button','video','audio'):return ''
        if n.tag=='img':raise HTTPException(422,'Registra las imágenes con Agregar fotos. Así se confirma su carpeta y se incluyen como miniaturas reales.')
        hijos=''.join(nodo(h) for h in n.hijos)
        if n.tag not in TAGS:return hijos
        attrs={}
        if n.tag=='a':
            href=n.attrs.get('href','')
            if re.fullmatch(r'https://[^\s<>"\x00-\x1f]+',href):
                # Los vínculos de Drive se eligen desde los bloques comprobados.
                if re.match(r'https://(?:drive|docs)\.google\.com/',href) and href not in enlaces:raise HTTPException(422,'Ese enlace Drive no está confirmado para este correo. Usa las carpetas verificadas.')
                attrs['href']=href;attrs['rel']='noopener noreferrer'
        if n.attrs.get('data-correo-seccion') in ('prerecepcion','observaciones'):attrs['data-correo-seccion']=n.attrs['data-correo-seccion']
        if 'style' in n.attrs:
            estilos=[]
            for regla in n.attrs['style'].split(';'):
                k,sep,v=regla.partition(':');k=k.strip().lower();v=v.strip()
                if sep and k in ESTILOS and re.fullmatch(r"[A-Za-z0-9#%., ()_+/'\"-]{1,160}",v) and not re.search(r'url|expression|import',v,re.I):estilos.append(k+':'+v)
            if estilos:attrs['style']=';'.join(estilos)
        for k in ('colspan','rowspan'):
            if re.fullmatch(r'[1-9][0-9]?',n.attrs.get(k,'')):attrs[k]=n.attrs[k]
        a=''.join(' '+k+'="'+escape(v,quote=True)+'"' for k,v in attrs.items())
        return '<'+n.tag+a+'>'+('' if n.tag in VOID else hijos+'</'+n.tag+'>')
    salida=''.join(nodo(h) for h in Arbol(html).raiz.hijos)
    if not salida.strip():raise HTTPException(422,'Escribe el contenido del correo antes de guardarlo.')
    return salida


def aplicar(cuerpo,base):
    # Revalidar ante cambios de fotos o tablas, y sustituir siempre con datos SQL actuales.
    limpio=limpiar(cuerpo,base);valores=bloques(base)
    ids=set(re.findall(r'data-correo-bloque="([^"]+)"',limpio))
    salida=re.sub(r'<div data-correo-bloque="([^"]+)"></div>',lambda m:valores[m[1]],limpio)
    # Al agregar nuevas evidencias, incorporarlas aunque ya existiera redacción libre.
    nuevas=[v for k,v in valores.items() if k.startswith('foto:') and k not in ids]
    previas=[v for v in nuevas if 'Prerecepción · descarga' in v];otras=[v for v in nuevas if v not in previas]
    if previas:
        contenido='<section><h3>Prerecepción · descarga del contenedor</h3>'+''.join(previas)+'</section>'
        marca='<section data-correo-seccion="observaciones"'
        if marca in salida:salida=salida.replace(marca,contenido+marca,1)
        elif valores.get('cabecera') in salida:salida=salida.replace(valores['cabecera'],valores['cabecera']+contenido,1)
        else:salida=contenido+salida
    if otras:salida+='<section><h3>Evidencias seleccionadas</h3>'+''.join(otras)+'</section>'
    return salida
