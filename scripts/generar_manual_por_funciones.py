"""Reorganiza el manual aprobado: conserva sus 38 procedimientos y capturas.

La fuente y los HTML con datos de las capturas permanecen fuera de Git.
"""
import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re


class Fragmentos(HTMLParser):
    def __init__(self, fuente):
        super().__init__(convert_charrefs=False)
        self.fuente=fuente;self.lineas=[0];self.fragmentos={};self.nivel=0;self.actual=None
        for m in re.finditer('\n',fuente):self.lineas.append(m.end())
    def pos(self):
        l,c=self.getpos();return self.lineas[l-1]+c
    def handle_starttag(self,t,a):
        d=dict(a)
        if t=='section':
            if self.actual:self.nivel+=1
            elif d.get('id')=='portada' or 'step' in d.get('class','').split():
                self.actual=d['id'];self.inicio=self.pos();self.nivel=1
    def handle_endtag(self,t):
        if t=='section' and self.actual:
            self.nivel-=1
            if not self.nivel:
                fin=self.fuente.index('>',self.pos())+1
                self.fragmentos[self.actual]=self.fuente[self.inicio:fin];self.actual=None


class Texto(HTMLParser):
    def __init__(self):super().__init__();self.textos=[]
    def handle_data(self,d):self.textos.append(d)


def texto(h):
    p=Texto();p.feed(h);return ' '.join(' '.join(p.textos).split())


def sin_instrucciones_remotas(h):
    # Solo texto HTML. Nunca modificar cadenas base64 de las capturas.
    class Sustituir(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=False);self.salida=[]
        def handle_starttag(self,t,a):self.salida.append(self.get_starttag_text())
        def handle_startendtag(self,t,a):self.salida.append(self.get_starttag_text())
        def handle_endtag(self,t):self.salida.append('</'+t+'>')
        def handle_entityref(self,n):self.salida.append('&'+n+';')
        def handle_charref(self,n):self.salida.append('&#'+n+';')
        def handle_data(self,d):
            d=d.replace('red autorizada de la bodega o VPN institucional','red autorizada de la bodega')
            d=re.sub(r'\bVPN\b(?:\s+(?:corporativa|institucional))?','red autorizada de la bodega',d,flags=re.I)
            self.salida.append(d)
    p=Sustituir();p.feed(h);return ''.join(p.salida)


GLOSARIO=[
('Aplicativo','El sistema que utilizas para registrar y revisar la recepción de mercadería.'),
('Operador u operario','Persona que revisa físicamente la mercadería y registra lo que encuentra con su propia cuenta.'),
('Supervisor','Persona que prepara la recepción, coordina al equipo, revisa diferencias y entrega el informe.'),
('Administrador','Responsable que autoriza cuentas, equipos y configuraciones del sistema.'),
('Rol','La función asignada a tu cuenta; determina las acciones que tienes disponibles.'),
('Sesión','El período durante el que estás dentro del sistema con tu cuenta.'),
('Recepción','El trabajo de recibir y revisar una entrega de mercadería. Tiene un código que la identifica.'),
('Packing list','La lista de mercadería enviada: indica productos y cantidades esperadas.'),
('Embarque','La entrega o envío al que pertenece la mercadería. Una recepción puede reunir varios embarques.'),
('SKU o referencia','El código con el que el sistema identifica un producto. Comprueba también su descripción.'),
('Código de barras','Las barras impresas que el lector convierte en un código para consultar el producto.'),
('EAN-13','Un código de barras de 13 números. Cuando está relacionado en el catálogo, el sistema muestra el código del producto correspondiente.'),
('Catálogo','La lista de productos y códigos que el sistema utiliza para reconocerlos.'),
('Unidades por empaque','La cantidad de piezas que contiene un empaque. Comprueba la equivalencia antes de registrar el conteo.'),
('Declarado','La cantidad que figura en el packing list.'),
('Contado','La cantidad que el equipo ya registró después de revisar físicamente la mercadería.'),
('Conteo','Un registro de unidades revisadas. Escanear el código consulta el producto; guardar el conteo registra las unidades.'),
('Faltante','La diferencia que indica que se contaron menos unidades de las esperadas.'),
('Sobrante','La diferencia que indica que se contaron más unidades de las esperadas.'),
('PNC','Producto no conforme: una pieza con daño u otra condición que debe quedar informada.'),
('Novedad o incidencia','Una situación que requiere explicación, como un faltante, un sobrante, un daño o una diferencia de código.'),
('Bulto','Una unidad física de recepción, como una caja o un paquete identificado.'),
('Subbulto','Una división de un bulto. Por ejemplo, A01.1 pertenece al bulto A01.'),
('Pallet','La plataforma donde se agrupa la mercadería. Registra el identificador del pallet real.'),
('Posición','El lugar físico de la bodega donde queda la mercadería.'),
('Evidencia','La fotografía o el dato que permite comprobar qué se recibió y en qué condición.'),
('Prerecepción','Las fotografías del arribo y la descarga, antes de validar los productos.'),
('Panorámica','Una foto general que muestra el conjunto de mercadería y su entorno.'),
('Foto final','La imagen que muestra cómo queda la mercadería al terminar el trabajo.'),
('Drive','El lugar de almacenamiento de las fotografías y documentos, organizado en carpetas.'),
('Compartidas','La carpeta de fotos que se aplican a varios embarques. Si la foto pertenece a uno solo, selecciona ese embarque.'),
('Seleccionada','Una foto elegida en la pantalla. Todavía debes confirmar su guardado.'),
('Registrada','Una foto o un dato cuyo guardado ya confirmó el sistema.'),
('Sincronizar','Enviar al servidor los registros que quedaron pendientes en el equipo y recibir su confirmación.'),
('Pendiente local','Un registro respaldado en ese equipo que todavía no ha sido confirmado por el servidor.'),
('Bitácora o historial','La lista de acciones registradas, con su fecha y la cuenta que las realizó.'),
('Trazabilidad','La posibilidad de reconstruir qué se hizo, cuándo y con qué cuenta se registró.'),
('Etiqueta','La identificación que se imprime para un producto, bulto o subbulto.'),
('Informe','El documento que resume lo recibido, lo contado y las novedades encontradas.'),
('Adjunto','Un archivo que acompaña al correo, por ejemplo un informe o un packing list.'),
('Correo consolidado','Un correo que reúne la información de toda la recepción.'),
('Cierre','La confirmación del supervisor de que terminó la revisión. Una recepción cerrada limita las modificaciones.')]

OPERADOR=[
('Recibe la recepción abierta','Comprueba con el supervisor el código, el cliente y la mercadería que vas a revisar.',4),
('Abre tu cuenta y la recepción correcta','Revisa que la pantalla muestre tu nombre. Cada persona trabaja con su propia cuenta.',2),
('Escanea y comprueba el producto','Lee el código y compara la referencia y descripción con la pieza física. Escanear no suma unidades.',5),
('Cuenta y registra lo real','Escribe cantidad, pallet y posición. Declara las novedades y adjunta las fotos necesarias.',8),
('Guarda y espera la confirmación','Pulsa Guardar conteo. Si falta conexión, comprueba el respaldo local y sincroniza al recuperarla.',12),
('Revisa y continúa','Consulta la bitácora y las cantidades registradas. Coordina con los demás para no contar las mismas unidades dos veces.',16),
('Entrega tu avance y cierra tu sesión','Sincroniza los pendientes, informa al supervisor y cierra tu sesión al terminar el turno.',18)]

SUPERVISOR=[
('Recibe y revisa el packing list','Confirma cliente, embarque, referencias y cantidades del archivo recibido.',21),
('Crea y prepara la recepción','Registra su código y cliente. Carga el packing list, revisa las columnas y habilita el trabajo.',20),
('Registra la recepción física','Guarda las fotos de arribo y descarga, eligiendo el embarque y el tipo de fotografía.',30),
('Comprueba bultos y etiquetas','Revisa el total físico e imprime el lote, los números necesarios o los subbultos registrados.',26),
('Coordina y monitorea','Asigna el trabajo al equipo y revisa el avance. Si vas a contar, sigue también la guía del operador.',27),
('Revisa y corrige las novedades','Verifica cantidades, evidencias y registros. Las correcciones autorizadas deben conservar su motivo e historial.',29),
('Prepara informes y correo','Comprueba los datos, decide cómo agrupar los correos y revisa destinatarios, texto y adjuntos.',33),
('Confirma la entrega y el cierre','Comprueba los registros pendientes, las evidencias y el estado del envío antes de dar por terminada la recepción.',37)]

AYUDA=[
('No puedo entrar','Comprueba tu usuario y tu contraseña del aplicativo. Si la cuenta o el equipo requiere autorización, solicita ayuda al administrador. Trabaja con la cuenta que lleva tu nombre.',2),
('El lector no encuentra el producto','Pon el cursor en Escanear, vuelve a leer y compara el código. Busca también por referencia o descripción; comunica al supervisor una relación de códigos que falte.',14),
('Se perdió la conexión','Conserva la ventana y el equipo. Guarda cada conteo de los productos ya descargados y verifica su respaldo local. Al volver la conexión, sincroniza con la misma cuenta y revisa los rechazos con el supervisor.',38),
('Seleccioné fotos y no aparecen en Drive','Seleccionar no confirma el guardado. Elige el embarque y pulsa Guardar fotos seleccionadas. Lee el mensaje de resultado, que puede aparecer debajo de las miniaturas. Un rechazo al guardar debe resolverse antes de que la foto pueda copiarse a Drive.',30),
('La foto está en otra carpeta','Comprueba el embarque y la clasificación. Una foto compartida puede estar en COMPARTIDAS. El supervisor puede revisar su vínculo antes de volver a cargarla.',31),
('La barra muestra todas las fotos confirmadas','El contador corresponde a las fotos registradas. Las imágenes que aún están seleccionadas necesitan confirmar su guardado; no las des por registradas solo porque veas la barra completa.',31),
('El conteo tiene una diferencia','Vuelve a comprobar las unidades físicas, la referencia, el empaque y la lista de origen. El supervisor revisa y autoriza una corrección; no añadas un segundo conteo para ocultar un error anterior.',29),
('El avance llegó al 100 %','Significa que se revisaron las referencias según los indicadores. Aun así puede haber faltantes, sobrantes o PNC que deben quedar informados.',27),
('La etiqueta no se puede leer','Comprueba el tamaño físico del papel y utiliza tamaño real o 100 % al imprimir. Prueba una etiqueta y su lectura antes de emitir todo el lote. Comunica al supervisor una impresión borrosa o recortada.',26),
('El correo no está confirmado','Revisa el estado de la entrega, los destinatarios y sus adjuntos. Conserva la entrega existente para revisarla; consulta al supervisor antes de generar otro envío.',37)]

CSS=r'''
:root{--ink:#17324d;--blue:#225de2;--line:#dce5ef;--soft:#edf4ff;--muted:#526781}*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:var(--ink);font:16px/1.6 system-ui,Arial,sans-serif}a{color:var(--blue)}button,input{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #e0a900;outline-offset:3px}[hidden]{display:none!important}.cabecera{background:#fff;border-bottom:1px solid var(--line);padding:22px max(20px,calc((100vw - 1300px)/2));display:flex;align-items:center;gap:24px;flex-wrap:wrap}.cabecera img{width:210px;max-width:45vw;height:auto}.cabecera h1{margin:0;font-size:26px;line-height:1.2}.cabecera p{margin:6px 0 0;color:var(--muted);font-size:14px}.estructura{max-width:1300px;margin:25px auto;display:grid;grid-template-columns:240px minmax(0,1fr);gap:28px;padding:0 20px}.menu{position:sticky;top:15px;align-self:start;background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px;max-height:95vh;overflow:auto}.menu button{display:block;width:100%;text-align:left;padding:11px 12px;border:0;border-radius:8px;background:transparent;color:var(--ink);margin:3px 0;font-weight:650}.menu button[aria-current=page]{background:var(--blue);color:#fff}.menu small{display:block;padding:12px;color:var(--muted)}main{min-width:0}h2{font-size:28px;line-height:1.25;margin:8px 0 14px}h3{line-height:1.35}.intro{color:var(--muted);max-width:72ch}.tarjetas{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.tarjeta{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px}.tarjeta h3{margin:0 0 8px}.tarjeta p{margin:8px 0}.boton,.acciones button{display:inline-block;padding:10px 14px;border:1px solid var(--line);border-radius:9px;color:var(--blue);background:#fff;font-weight:650;text-decoration:none}.principal{background:var(--blue)!important;color:#fff!important;border-color:var(--blue)!important}.acciones{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.orientacion{background:#e9f2ff;border-left:4px solid var(--blue);padding:14px 18px;border-radius:0 10px 10px 0;margin:20px 0}.flujo{list-style:none;padding:0;counter-reset:paso}.flujo li{counter-increment:paso;position:relative;padding:0 0 20px 46px;margin:0}.flujo li:before{content:counter(paso);position:absolute;left:0;top:0;background:var(--blue);color:#fff;width:31px;height:31px;display:grid;place-items:center;border-radius:50%;font-weight:700}.flujo b{display:block}.flujo p{margin:3px 0 7px}.flujo a{font-size:14px}.busqueda{background:#fff;padding:14px;border:1px solid var(--line);border-radius:12px;margin:18px 0}.busqueda label{display:block;font-weight:650}.busqueda input{width:100%;margin-top:7px;padding:11px;border:1px solid #aabacf;border-radius:8px}.busqueda p{margin:7px 0 0;color:var(--muted);font-size:14px}.paso-detalle{background:#fff;border:1px solid var(--line);border-radius:12px;margin:12px 0;scroll-margin-top:20px}.paso-detalle>summary{cursor:pointer;font-weight:700;padding:18px}.paso-detalle[open]>summary{border-bottom:1px solid var(--line)}.paso-detalle .step{padding:20px}.step h2{font-size:24px}.tag{font-size:13px;color:var(--muted);font-weight:700}.screen{background:var(--soft);padding:12px;border-radius:8px}.result,.attention,.cambio{padding:14px;margin:16px 0;background:#edf8f2;border-left:4px solid #2c8050;border-radius:0 8px 8px 0}.attention{background:#fff6e6;border-left-color:#d29b00}.cambio{background:var(--soft);border-left-color:var(--blue)}.galeria-real{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.galeria-real img{display:block;width:100%;height:auto;max-height:600px;object-fit:contain;cursor:zoom-in}.visual{margin:18px 0}.visual figcaption{font-size:13px;color:var(--muted)}.ayuda details{margin:12px 0;background:#fff;border:1px solid var(--line);border-radius:12px;padding:15px}.ayuda summary{cursor:pointer;font-weight:700}.glosario{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.termino{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px}.termino dt{font-weight:750;color:var(--blue)}.termino dd{margin:7px 0 0}.cover{padding:18px;background:#fff;border:1px solid var(--line);border-radius:12px}.cover .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.pie{font-size:13px;color:var(--muted);margin:35px 0}dialog{border:1px solid var(--line);border-radius:14px;max-width:96vw;max-height:96vh;padding:14px}dialog::backdrop{background:#001a35b8}dialog img{display:block;max-width:90vw;max-height:82vh;object-fit:contain}dialog button{margin-bottom:10px}.solo-impresion{display:none}@media(max-width:850px){.estructura{grid-template-columns:1fr}.menu{position:static;max-height:none;display:flex;flex-wrap:wrap;gap:5px}.menu button{width:auto;flex:1 1 145px;text-align:center}.menu small{flex-basis:100%;padding:5px}.cabecera h1{font-size:23px}.tarjetas,.glosario{grid-template-columns:1fr}}@media print{body{background:#fff;font-size:10pt;color:#111}.cabecera{padding:0 0 8mm}.cabecera img{width:42mm}.cabecera h1{font-size:20pt}.estructura{display:block;padding:0;margin:0}.menu,.acciones,.busqueda,.no-imprimir,dialog{display:none!important}.tarjetas{grid-template-columns:repeat(2,minmax(0,1fr))}.tarjeta{break-inside:avoid;padding:4mm}.paso-detalle{break-inside:auto}.paso-detalle>summary{font-size:12pt;break-after:avoid}.paso-detalle .step{padding:3mm}.step h2{font-size:15pt}.galeria-real{grid-template-columns:repeat(2,minmax(0,1fr));gap:3mm}.galeria-real img{height:80mm;max-height:80mm;break-inside:avoid}.galeria-real.unica{grid-template-columns:1fr}.galeria-real.unica img{height:100mm;max-height:100mm}.visual{break-inside:auto}.visual figcaption{break-before:avoid}.flujo li{break-inside:avoid;padding-bottom:3mm}.glosario{grid-template-columns:repeat(2,minmax(0,1fr))}.termino{break-inside:avoid}.pie{display:none}.solo-impresion{display:block}[data-seccion="rapida"] .flujo a{display:none}[data-seccion="rapida"] .flujo p{font-size:9pt;line-height:1.4}[data-seccion="rapida"] .flujo li{padding-bottom:2mm}h2,h3{break-after:avoid}}
'''

JS=r'''
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const limpiar=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const permitidas=JSON.parse(document.body.dataset.vistas);let vista=document.body.dataset.inicio||'inicio';
function filtrar(){const q=limpiar($('#buscar').value.trim());let n=0;
 for(const d of $$('.paso-detalle')){const corresponde=d.dataset.vistas.split(' ').includes(vista),coincide=!q||limpiar(d.textContent).includes(q);d.hidden=!corresponde||!coincide;if(!d.hidden){n++;if(q)d.open=true;}}
 for(const d of $$('.termino'))d.hidden=!!q&&!limpiar(d.textContent).includes(q);
 for(const d of $$('.consulta-ayuda')){d.hidden=!!q&&!limpiar(d.textContent).includes(q);if(q&&!d.hidden)d.open=true;}
 $('#resultado').textContent=vista==='glosario'?`${$$('.termino:not([hidden])').length} términos`:vista==='ayuda'?`${$$('.consulta-ayuda:not([hidden])').length} temas de ayuda`:`${n} procedimientos de esta guía`;
}
function mostrar(v,ancla){if(!permitidas.includes(v))return;vista=v;$('#buscar').value='';
 $$('[data-seccion]').forEach(e=>e.hidden=e.dataset.seccion!==v);$$('[data-vista]').forEach(e=>e.setAttribute('aria-current',e.dataset.vista===v?'page':'false'));
 $('#biblioteca').hidden=!['operador','supervisor','ayuda','completo'].includes(v);$('#herramientas').hidden=!['operador','supervisor','ayuda','completo','glosario'].includes(v);
 $('#titulo-vista').textContent=({inicio:'Elige lo que necesitas',rapida:'Guía rápida',operador:'Guía del operador',supervisor:'Guía del supervisor',ayuda:'Guía de ayuda',glosario:'Glosario de términos',completo:'Guía completa · 38 pasos'})[v];
 filtrar();try{history.replaceState(null,'','#'+v);}catch{}if(ancla){const e=document.getElementById(ancla);if(e){e.closest('details')?.setAttribute('open','');e.scrollIntoView({behavior:'smooth',block:'start'});}}else window.scrollTo({top:0});
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-vista]');if(b){e.preventDefault();mostrar(b.dataset.vista,b.dataset.paso);}});
$('#buscar').addEventListener('input',filtrar);
$('#abrir-todos').onclick=()=>$$('.paso-detalle:not([hidden])').forEach(d=>d.open=true);
$('#cerrar-todos').onclick=()=>$$('.paso-detalle').forEach(d=>d.open=false);
let abiertos=[],ayudaAbierta=[],imprimiendo=false;function prepararImpresion(){if(imprimiendo)return;imprimiendo=true;abiertos=$$('.paso-detalle[open]');ayudaAbierta=$$('[data-seccion="ayuda"] details[open]');$$('.paso-detalle:not([hidden])').forEach(d=>d.open=true);$$('[data-seccion="ayuda"] details').forEach(d=>d.open=true);}
function terminarImpresion(){$$('.paso-detalle').forEach(d=>d.open=abiertos.includes(d));$$('[data-seccion="ayuda"] details').forEach(d=>d.open=ayudaAbierta.includes(d));imprimiendo=false;}
window.addEventListener('beforeprint',prepararImpresion);window.addEventListener('afterprint',terminarImpresion);$('#imprimir').onclick=()=>{prepararImpresion();window.print();};
$('#descargar').onclick=()=>{const copia=document.documentElement.cloneNode(true);copia.querySelector('body').dataset.inicio=vista;copia.querySelector('#buscar').setAttribute('value','');copia.querySelector('#zoom').removeAttribute('open');copia.querySelector('#vista-img').removeAttribute('src');
 const u=URL.createObjectURL(new Blob(['<!doctype html>\n'+copia.outerHTML],{type:'text/html;charset=utf-8'})),a=document.createElement('a');a.href=u;a.download=document.body.dataset.archivo||'Manual-usuario-IV-ITSANET.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),5000);};
$$('.galeria-real img').forEach(i=>{i.loading='lazy';i.onclick=()=>{$('#vista-img').src=i.src;$('#zoom').showModal();};});$('#cerrar-zoom').onclick=()=>$('#zoom').close();
const [fragmento,ancla]=location.hash.slice(1).split('/');mostrar(permitidas.includes(fragmento)?fragmento:vista,ancla);
'''


def boton(v,t,paso=None):
    return '<a class="boton" href="#'+v+'" data-vista="'+v+'"'+(' data-paso="paso-'+str(paso)+'"' if paso else '')+'>'+escape(t)+'</a>'


def flujo(items,rol):
    return '<ol class="flujo">'+''.join('<li><b>'+escape(t)+'</b><p>'+escape(d)+'</p>'+boton(rol,'Ver cómo hacerlo',p)+'</li>' for t,d,p in items)+'</ol>'


def generar(fuente,salida):
    h=Path(fuente).read_text();parser=Fragmentos(h);parser.feed(h);partes=parser.fragmentos
    assert [k for k in partes if k.startswith('paso-')]==['paso-'+str(i) for i in range(1,39)]
    logo=re.search(r'<img\b[^>]*>',partes['portada']).group()
    portada=partes['portada'].replace(logo,'',1)
    grupos={'operador':set(range(1,19))|{38},'supervisor':{1,2,3}|set(range(19,38)),
            'ayuda':{38},'completo':set(range(1,39))}
    biblioteca='';inventario=[]
    for i in range(1,39):
        s=sin_instrucciones_remotas(partes['paso-'+str(i)]).replace('<img ','<img loading="lazy" ')
        titulo=texto(re.search(r'<h2>(.*?)</h2>',s,re.S).group(1))
        roles=' '.join(k for k,ids in grupos.items() if i in ids)
        biblioteca+='<details class="paso-detalle" data-vistas="'+roles+'"><summary>'+str(i).zfill(2)+' · '+escape(titulo)+'</summary>'+s+'</details>'
        inventario.append({'paso':i,'titulo':titulo,'vistas':roles.split()})
    rapida='<section data-seccion="rapida" hidden><p class="intro">Este es el recorrido de cada función. Para aprender una tarea o revisar una captura, abre su guía.</p><div class="tarjetas"><article class="tarjeta"><h3>Operador</h3>'+flujo(OPERADOR,'operador')+'</article><article class="tarjeta"><h3>Supervisor</h3>'+flujo(SUPERVISOR,'supervisor')+'</article></div></section>'
    inicio='<section data-seccion="inicio"><p class="intro">Empieza por tu función. Consulta una tarea a la vez y abre sus capturas cuando las necesites. La guía completa permanece disponible.</p><div class="tarjetas">'+''.join('<article class="tarjeta"><h3>'+t+'</h3><p>'+d+'</p>'+boton(v,b)+'</article>' for v,t,d,b in [
      ('rapida','Voy a empezar','El recorrido resumido del operador y del supervisor.','Ver guía rápida'),
      ('operador','Voy a contar mercadería','Recepción abierta, lectura de códigos, conteos, fotos y revisión de tus registros.','Abrir guía del operador'),
      ('supervisor','Voy a coordinar la recepción','Packing list, apertura, bultos, etiquetas, revisión del equipo, informes y correo.','Abrir guía del supervisor'),
      ('ayuda','Necesito resolver una duda','Ayuda sobre acceso, códigos, conexión, fotos, cantidades, etiquetas y envío.','Buscar ayuda'),
      ('glosario','No conozco un término','Explicaciones sencillas de las palabras que aparecen en el sistema.','Consultar glosario'),
      ('completo','Quiero consultar todo','Los 38 procedimientos y sus imágenes finales, conservados para consulta detallada.','Abrir guía completa')])+'</div><div class="orientacion"><b>Antes de registrar:</b> trabaja en la bodega con el equipo asignado, entra con tu cuenta y comprueba que tu nombre aparezca en la pantalla.</div></section>'
    operador='<section data-seccion="operador" hidden><p class="intro">Tu tarea es revisar la mercadería de una recepción que el supervisor ya preparó. Abre solo el procedimiento que necesitas.</p><div class="orientacion"><b>Tu recorrido:</b> recepción asignada → producto → cantidad y ubicación → novedad y fotos → guardar → revisar. La apertura, las correcciones autorizadas y el envío del informe corresponden al supervisor.</div><div class="acciones">'+boton('operador','Buscar la recepción',4)+boton('operador','Registrar un conteo',8)+boton('operador','Guardar y confirmar',12)+boton('operador','Revisar tu trabajo',16)+boton('ayuda','Necesito ayuda')+'</div></section>'
    supervisor='<section data-seccion="supervisor" hidden><p class="intro">Prepara el trabajo, coordina a los operarios y revisa los resultados antes de entregar el informe. Si también vas a contar, utiliza la guía del operador.</p><div class="orientacion"><b>Tu recorrido:</b> packing list → recepción y embarques → fotos y bultos → etiquetas → seguimiento → correcciones → informes → revisión y envío.</div><div class="acciones">'+boton('supervisor','Crear y preparar',20)+boton('supervisor','Bultos y etiquetas',25)+boton('supervisor','Monitorear y corregir',27)+boton('supervisor','Preparar el correo',33)+boton('operador','También voy a contar')+'</div></section>'
    ayuda='<section data-seccion="ayuda" class="ayuda" hidden><p class="intro">Busca tu situación y sigue la indicación. Para una corrección de datos o un cambio de permisos, solicita la revisión del responsable.</p>'+''.join('<details class="consulta-ayuda"><summary>'+escape(t)+'</summary><p>'+escape(d)+'</p>'+boton('ayuda' if p==38 else 'completo','Abrir el procedimiento',p)+'</details>' for t,d,p in AYUDA)+'</section>'
    glosario='<section data-seccion="glosario" hidden><p class="intro">Palabras del sistema explicadas con ejemplos del trabajo diario.</p><dl class="glosario">'+''.join('<div class="termino"><dt>'+escape(t)+'</dt><dd>'+escape(d)+'</dd></div>' for t,d in GLOSARIO)+'</dl></section>'
    completo='<section data-seccion="completo" hidden><p class="intro">Aquí están los 38 pasos de la guía detallada. Abre un procedimiento o utiliza «Abrir procedimientos» para revisarlos todos.</p>'+portada+'</section>'
    nav=[('inicio','Inicio'),('rapida','Guía rápida'),('operador','Guía del operador'),('supervisor','Guía del supervisor'),('ayuda','Guía de ayuda'),('glosario','Glosario'),('completo','Guía completa')]
    nombres={'rapida':'Guia-rapida','operador':'Guia-operador','supervisor':'Guia-supervisor','ayuda':'Guia-ayuda','glosario':'Glosario'}
    def pagina(inicial='inicio',solo=False):
        vistas=[inicial] if solo else [v for v,_ in nav]
        menu=''.join('<button type="button" data-vista="'+v+'">'+t+'</button>' for v,t in nav if v in vistas)
        cuerpo=''.join([inicio,rapida,operador,supervisor,ayuda,glosario,completo])
        doc='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IV ITSANET · Manual de usuario por funciones</title><style>'+CSS+'</style></head><body data-inicio="'+inicial+'" data-vistas="'+escape(json.dumps(vistas))+'"><header class="cabecera">'+logo+'<div><h1>Ingreso &amp; Validación Itsanet</h1><p>Manual de usuario · ITSANET Ecuador, Quito · Uso en bodega</p></div></header><div class="estructura"><nav class="menu" aria-label="Guías del manual">'+menu+'<small>Elige tu función y abre una tarea a la vez.</small></nav><main><h2 id="titulo-vista">Elige lo que necesitas</h2><div class="acciones no-imprimir"><button id="descargar">Descargar HTML</button><button id="imprimir">Imprimir esta guía / PDF</button></div>'+cuerpo+'<div id="herramientas" class="busqueda" hidden><label for="buscar">Buscar en esta guía</label><input id="buscar" type="search" placeholder="Ej.: fotos, cantidades, etiquetas"><p id="resultado" role="status"></p><div class="acciones"><button id="abrir-todos">Abrir procedimientos</button><button id="cerrar-todos">Cerrar procedimientos</button></div></div><div id="biblioteca" hidden>'+biblioteca+'</div><footer class="pie">Cuenta individual · datos reales · evidencias verificables. Si tu pantalla no muestra una acción, consulta al supervisor.</footer></main></div><dialog id="zoom"><button id="cerrar-zoom">Cerrar imagen</button><img id="vista-img" alt="Captura ampliada"></dialog><script>'+JS+'</script></body></html>'
        archivo=(nombres[inicial]+'-IV-ITSANET.html') if solo else 'Manual-usuario-IV-ITSANET.html'
        doc=doc.replace('<body data-inicio=', '<body data-archivo="'+archivo+'" data-inicio=',1)
        # El buscador siempre aparece antes del contenido de la vista.
        inicio_herramientas=doc.index('<div id="herramientas"')
        fin_herramientas=doc.index('<div id="biblioteca"',inicio_herramientas)
        herramientas=doc[inicio_herramientas:fin_herramientas]
        doc=doc[:inicio_herramientas]+doc[fin_herramientas:]
        doc=doc.replace(cuerpo,herramientas+cuerpo,1)
        if solo:
            # Extraer únicamente las secciones elegidas sin volver a incrustar
            # capturas de otros roles. Los enlaces de consulta se conservan en
            # el portal completo, incluido en el mismo paquete de entrega.
            for v,fragmento in [('inicio',inicio),('rapida',rapida),('operador',operador),('supervisor',supervisor),('ayuda',ayuda),('glosario',glosario),('completo',completo)]:
                if v!=inicial:doc=doc.replace(fragmento,'')
            if inicial in grupos:
                for i in range(1,39):
                    if i not in grupos[inicial]:
                        patron=r'<details class="paso-detalle" data-vistas="[^"]*"><summary>'+str(i).zfill(2)+r' · .*?</details>'
                        doc=re.sub(patron,'',doc,count=1,flags=re.S)
            else:
                doc=doc.replace(biblioteca,'')
            # En un archivo separado, los atajos a otros roles abren la guía
            # completa que lo acompaña. No hay botones sin destino.
            doc=re.sub(r'<a class="boton" href="#([^"]+)" data-vista="([^"]+)"(?: data-paso="([^"]+)")?>',lambda m: '<a class="boton" href="Manual-usuario-IV-ITSANET.html#'+m[1]+('/'+m[3] if m[3] else '')+'">' if m[1] not in vistas else m[0],doc)
        return doc
    salida=Path(salida);salida.mkdir(parents=True,exist_ok=True)
    principal=pagina();(salida/'Manual-usuario-IV-ITSANET.html').write_text(principal)
    for v,n in nombres.items():(salida/(n+'-IV-ITSANET.html')).write_text(pagina(v,True))
    src=lambda s:re.findall(r'<img\b[^>]*\bsrc="(data:[^"]+)"',s)
    origen=sorted(hashlib.sha256(x.encode()).hexdigest() for x in src(h))
    destino=sorted(hashlib.sha256(x.encode()).hexdigest() for x in src(principal))
    assert origen==destino,'Se alteró o perdió una captura original'
    assert not re.search(r'\bVPN\b',texto(principal),re.I)
    informe={'fuenteSHA256':hashlib.sha256(h.encode()).hexdigest(),'pasosConservados':len(inventario),'imagenesOriginalesConservadas':len(origen),'glosario':len(GLOSARIO),'procedimientosPorGuia':{k:len(v) for k,v in grupos.items()},'archivos':[p.name for p in salida.glob('*.html')],'inventario':inventario}
    (salida/'Validacion-contenido.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in informe.items() if k!='inventario'},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fuente',type=Path,required=True);p.add_argument('--salida',type=Path,required=True);a=p.parse_args();generar(a.fuente,a.salida)
