"""Presentación offline y diagramas draw.io; no consulta ni modifica producción."""
from pathlib import Path
import importlib.util
import xml.etree.ElementTree as X
import json
import argparse

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('manual',ROOT/'scripts/generar_manual_tecnico_final.py')
M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
K,T,C=M.B.caja,M.T,M.C


def slides():
    return [
    ('IV ITSANET','Ingreso &amp; Validación Itsanet', '<h1>Del ingreso a la entrega</h1><p class="grande">Conteo, ubicación, evidencia y reporte desde PC y handheld.</p><div class="grid">'+K('Operación','Registro por recepción, embarque, SKU y pallet.')+K('Control','Cantidad, PNC, autoría y evidencia vinculada.')+K('Entrega','Informe revisado, adjuntos seleccionados y confirmación del correo.')+'</div><p class="mini">Funcionamiento según código v69 e infraestructura informada. Recorrido demostrativo sin conexión a producción.</p>'),
    ('Recorrido operativo','Selecciona una etapa para conocer su registro',
     '<div class="pasos-demo">'+''.join('<button class="etapa" data-etapa="'+str(i)+'">'+str(i+1)+'. '+t+'</button>' for i,t in enumerate(['Recepción','Packing','Conteo','Evidencia','Informe','Entrega']))+'</div><div class="banda" id="detalle-etapa" aria-live="polite"></div><div class="grid dos">'+K('Una misma información','Datos centrales para operarios, supervisores y administrador.')+K('Origen conservado','Las líneas del packing mantienen su orden; los registros justifican el resultado.')+'</div>'),
    ('Registro desde handheld','Validaciones antes de guardar', '<div class="grid">'+K('Identificar','Escanear el SKU, elegir origen y revisar cantidad esperada.')+K('Registrar','Cantidad, pallet/posición y condición. Cero explícito con observación.')+K('Justificar','Fotografía de la novedad y autoría del registro.')+'</div><div class="banda">La presencia informa si alguien más trabaja en el SKU. La idempotencia reconoce los reintentos y los controles de versión detectan conflictos.</div><p>El registro queda disponible en la bitácora; las correcciones conservan motivo y trazabilidad.</p>'),
    ('Cantidad y condición por pallet','Ejemplo operativo: 10 unidades recibidas', T(['Pallet / ubicación ilustrativa','Cantidad','Condición'],[['A01 · UB-01','2','PNC, con evidencia asociada.'],['A01 · UB-01','4','Conforme.'],['A02 · UB-02','4','Conforme.']])+'<div class="pasos-demo"><button id="ver-ejecutivo">Vista ejecutivo</button><button id="ver-auditoria">Vista auditoría</button></div><div class="banda" id="detalle-pallet">Ejecutivo: PALLET A01-A02. El desglose de unidades/PNC se añade al final, sin alterar las columnas originales.</div><p class="mini">Caso ilustrativo del flujo; no son datos de una recepción productiva.</p>'),
    ('Evidencia con seguimiento','Del archivo guardado al enlace confirmado','<div class="flujo">'+''.join('<div class="paso"><b>'+n+'</b><span>'+t+'</span></div>' for n,t in [('01','Capturar / clasificar'),('02','Guardar en servidor'),('03','Cola pendiente'),('04','Copiar a Drive'),('05','Confirmar enlace')])+'</div><div class="grid dos">'+K('Reintento controlado','ID estable, estado persistente y comprobación del contenido.')+K('Carpeta utilizada','Se crea la ruta de la evidencia al subir; una carga interrumpida puede dejar una ruta vacía.')+'</div><div class="banda">Miniatura visible ≠ copia confirmada. Los pendientes requieren seguimiento antes de entregar el informe.</div>'),
    ('Documentos y correo','Revisión y entrega al ejecutivo', '<div class="grid">'+K('Preparar','Generar informes con cantidades numéricas y vínculos de evidencia.')+K('Revisar','Descargar, seleccionar adjuntos y conservar el nombre final de cada archivo.')+K('Enviar','Usar Gmail autorizado; verificar confirmación o revisar la entrega pendiente.')+'</div><div class="banda">La cola distingue trabajo pendiente, proceso y resultado. Ante una respuesta interrumpida, consultar estado y Enviados antes de repetir.</div><p>La vía Google central evita una implementación individual de Apps Script por supervisor.</p>'),
    ('Actualización y supervisión','La vista acompaña el trabajo de la bodega', '<div class="grid">'+K('Recepción','Eventos de cambio por SSE y consulta alternativa configurada en 4 segundos.')+K('Supervisión','Presencia, diferencias, PNC y evidencias registradas o pendientes.')+K('Administración','Monitor de procesos, intentos, errores y actualización del catálogo.')+'</div><div class="banda">Los 4 segundos son el intervalo de respaldo configurado, no una latencia medida ni una promesa de actualización máxima.</div><p>La bitácora permite revisar quién registró cada operación y reconstruir indicadores por ítem.</p>'),
    ('Rendimiento observado','Cargar una muestra real del monitor de procesos', '<label class="carga">Seleccionar JSON del monitor <input id="mediciones" type="file" accept="application/json,.json"></label><div class="grid metricas">'+K('Intentos FOTO COPIADA','<strong id="met-n">—</strong>')+K('Mediana del intento','<strong id="met-p50">—</strong>')+K('Percentil 95 del intento','<strong id="met-p95">—</strong>')+'</div><p id="met-estado" role="status">Sin mediciones productivas cargadas.</p><p class="mini">Fuente: campo duracionMs del monitor; incluye verificación/copia/organización del intento exitoso. No mide captura, espera en cola ni la recepción completa. Muestra limitada a los eventos exportados; puede incluir reubicaciones y reintentos del mismo archivo.</p><details><summary>Cómo obtener la muestra</summary><p>ADMIN puede guardar la respuesta JSON autenticada de <code>/api/operacion/procesos?limite=100</code> desde el monitor o las herramientas de red del navegador. El archivo se procesa localmente en esta presentación; no se sube a ningún servidor.</p></details>'),
    ('Tiempo del flujo operativo','Comparación con mediciones ingresadas', '<div class="grid">'+K('Unidades de trabajo','<label>Registros completados <input id="registros" type="number" min="1" step="1" placeholder="Sin dato"></label>')+K('Proceso anterior','<label>Minutos observados <input id="min-antes" type="number" min="0.01" step="any" placeholder="Sin dato"></label>')+K('IV ITSANET','<label>Minutos observados <input id="min-ahora" type="number" min="0.01" step="any" placeholder="Sin dato"></label>')+'</div><div class="banda" id="resultado-tiempo" aria-live="polite">Ingresa mediciones comparables para calcular tiempo por registro y diferencia porcentual.</div><p class="mini">Cálculo ilustrativo con datos ingresados por el expositor; no es una lectura del servidor. Comparar la misma tarea, volumen, personal y condiciones. Eliminar reprocesos y automatizar validaciones es el mecanismo esperado; el ahorro requiere medición.</p>'),
    ('Arquitectura en operación','Componentes y comunicación',M.B.arquitectura()+'<div class="grid dos">'+K('Persistencia','MySQL local 8.0.46; modelo de 30 tablas declaradas. SQLAlchemy + PyMySQL.')+K('Integraciones','Drive para evidencia, Gmail para entrega y Depot para consulta habilitada.')+'</div><p class="mini">Servidor apps · HTTPS 8443 · Uvicorn 3002. Evidencia de infraestructura recibida el 27/10/2026.</p>'),
    ('Continuidad del aplicativo','Mantenimiento y datos protegidos',T(['Frecuencia recomendada','Control'],[['Diaria','Disponibilidad, catálogo, pendientes y respaldo.'],['Semanal','Capacidad y errores recurrentes.'],['Mensual','Accesos, permisos Drive, TLS y dependencias.'],['Trimestral','Restauración aislada.'],['Cada cambio','Pruebas, commit, respaldo y verificación funcional.']])+'<div class="banda">Respaldo: MySQL + archivos + clave + configuración. Drive requiere retención propia. Mantener la operación de los servicios compartidos.</div>'),
    ('Evolución V2','Otros clientes de la bodega', '<div class="grid">'+K('Separar','Permisos, identidad del SKU, catálogos y evidencias por cliente.')+K('Parametrizar','Reglas, formatos, responsables y destinatarios de cada operación.')+K('Validar','Piloto controlado y mediciones antes de habilitación gradual.')+'</div><div class="banda">Línea actual estable; V2 en un entorno separado. El manual técnico y los diagramas editables documentan la estructura de referencia.</div>')]


EXTRA_JS=r'''
const etapas=[
'Recepción: cabecera, cliente, bultos y embarques en app_recepciones. Interfaz y API de recepciones.',
'Packing: app_lineas conserva orden y columnas originales; app_skus mantiene el esperado. app_huellas reconoce cargas repetidas.',
'Conteo: app_eventos registra autoría, cantidad, pallet y posición; app_skus materializa el resultado y app_calidad_skus conserva calidad.',
'Evidencia: archivos.py guarda contenido; app_evidencias lo vincula al ítem. drive.py procesa app_copias_drive y google_drive_api.py confirma la copia.',
'Informe: app_informes identifica versión y huella; el formato ejecutivo conserva columnas originales y agrega detalle final de unidades/PNC.',
'Entrega: gestion.py recibe la acción de enviar; entregas.py conserva la cola app_entregas y Google Gmail API confirma el resultado.'
];
document.querySelectorAll('[data-etapa]').forEach(b=>b.onclick=()=>{document.querySelector('#detalle-etapa').textContent=etapas[Number(b.dataset.etapa)];document.querySelectorAll('[data-etapa]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));});document.querySelector('[data-etapa="0"]').click();
document.querySelector('#ver-ejecutivo').onclick=()=>document.querySelector('#detalle-pallet').textContent='Ejecutivo: PALLET A01-A02. Detalle final: A01, 6 unidades (2 PNC); A02, 4 unidades conformes. Evidencia asociada a las 2 PNC.';
document.querySelector('#ver-auditoria').onclick=()=>document.querySelector('#detalle-pallet').textContent='Auditoría: registro 1 → A01 / UB-01 / 2 PNC; registro 2 → A01 / UB-01 / 4 conformes; registro 3 → A02 / UB-02 / 4 conformes. Cada registro conserva autoría y evidencia vinculada cuando corresponde.';
const fmt=n=>new Intl.NumberFormat('es-EC',{maximumFractionDigits:2}).format(n);
document.querySelector('#mediciones').onchange=async e=>{
 ['met-n','met-p50','met-p95'].forEach(id=>document.getElementById(id).textContent='—');
 try{const f=e.target.files[0];if(!f)return;if(f.size>10*1024*1024)throw Error('El JSON excede 10 MB.');const j=JSON.parse(await f.text());if(!Array.isArray(j.eventos))throw Error('Se requiere la respuesta del monitor con la lista eventos.');
 const a=j.eventos.filter(x=>x.proceso==='FOTO'&&x.estado==='COPIADA'&&typeof x.duracionMs==='number'&&Number.isFinite(x.duracionMs)&&x.duracionMs>=0).map(x=>x.duracionMs).sort((a,b)=>a-b);
 if(!a.length)throw Error('La muestra no contiene intentos FOTO COPIADA con duracionMs válido.');const p=q=>a[Math.max(0,Math.ceil(q*a.length)-1)]/1000;
 document.querySelector('#met-n').textContent=String(a.length);document.querySelector('#met-p50').textContent=fmt(p(.5))+' s';document.querySelector('#met-p95').textContent=fmt(p(.95))+' s';
 document.querySelector('#met-estado').textContent='Muestra cargada: '+a.length+' intentos exitosos de '+j.eventos.length+' eventos. Percentiles por rango más próximo; archivo procesado localmente.';
 }catch(err){document.querySelector('#met-estado').textContent=err.message;}
};
function calcular(){const n=Number(document.querySelector('#registros').value),a=Number(document.querySelector('#min-antes').value),b=Number(document.querySelector('#min-ahora').value),out=document.querySelector('#resultado-tiempo');if(!Number.isInteger(n)||n<=0||!Number.isFinite(a)||!Number.isFinite(b)||a<=0||b<=0){out.textContent='Ingresa registros enteros positivos y tiempos positivos comparables.';return;}out.textContent='Antes: '+fmt(a*60/n)+' s/registro · IV ITSANET: '+fmt(b*60/n)+' s/registro · '+(b<=a?'Reducción: ':'Incremento: ')+fmt(Math.abs((a-b)/a*100))+' %. Valores calculados a partir de entradas del expositor.';}
['registros','min-antes','min-ahora'].forEach(id=>document.getElementById(id).oninput=calcular);
'''


def diagramas(destino):
    file=X.Element('mxfile',host='app.diagrams.net',type='device',version='24.7.17')
    def pagina(nombre):
        d=X.SubElement(file,'diagram',name=nombre,id='p'+str(len(file)));g=X.SubElement(d,'mxGraphModel',dx='1600',dy='1000',grid='1',gridSize='10',page='1',pageWidth='2200',pageHeight='2200');r=X.SubElement(g,'root');X.SubElement(r,'mxCell',id='0');X.SubElement(r,'mxCell',id='1',parent='0');return r
    def nodo(r,i,text,x,y,w=260,h=100,style=''):
        c=X.SubElement(r,'mxCell',id=i,value=text,vertex='1',parent='1',style='rounded=1;whiteSpace=wrap;html=0;fillColor=#eef4ff;strokeColor=#225de2;fontColor=#172b45;fontSize=14;spacing=12;'+style);X.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
    def edge(r,a,b,label=''):
        c=X.SubElement(r,'mxCell',id='e'+str(len(r)),value=label,edge='1',parent='1',source=a,target=b,style='edgeStyle=orthogonalEdgeStyle;rounded=0;endArrow=block;html=0;strokeColor=#6b8199;fontSize=11;');X.SubElement(c,'mxGeometry',relative='1',**{'as':'geometry'})
    def titulo(r,t,sub):nodo(r,'title',t+'\n'+sub,30,20,1800,75,'fillColor=#102b46;fontColor=#ffffff;fontSize=20;')
    r=pagina('01 Arquitectura');titulo(r,'IV ITSANET · Ingreso & Validación Itsanet','Arquitectura lógica de referencia · código v69 · infraestructura recibida el 27/10/2026')
    for i,t,x,y in [('web','PC / handheld\nHTML · CSS · JavaScript\n/app/',40,180),('apache','Apache2\nHTTPS 8443\nVirtual host itsanet-app-8443.conf',370,180),('api','Uvicorn :3002\nFastAPI / Python\nServicio iv-itsanet',700,180),('db','SQLAlchemy + PyMySQL\nMySQL local 8.0.46\n127.0.0.1:3306',1050,180),('files','VAL_DATA_DIR\nOriginales / miniaturas\nClave externa protegida',700,420),('google','Google OAuth central\nPKCE / tokens cifrados\nAutorización de cuenta',1050,420),('drive','Google Drive API\nEvidencias / informes\nEnlaces confirmados',1400,330),('gmail','Gmail API\nCuenta remitente autorizada\nResultado de envío',1400,530),('depot','Depot HTTPS (si habilitado)\nConsulta catálogo / stock\nMaestro y caché local',370,420)]:nodo(r,i,t,x,y)
    for a,b,l in [('web','apache','HTTPS'),('apache','api','Publicación / API'),('api','db','Transacciones'),('api','files','Archivo operativo'),('api','google','OAuth'),('google','drive','HTTPS'),('google','gmail','HTTPS'),('api','depot','Consulta')]:edge(r,a,b,l)
    r=pagina('02 Flujo operativo');titulo(r,'Flujo de trabajo implementado','Ramas de validación y pendientes · diagrama funcional, no transacción única')
    textos=[('inicio','Acceso / roles\noperadores + sesiones'),('rec','Recepción / embarques / bultos\napp_recepciones + unidades'),('packing','Cargar packing y conservar líneas\napp_lineas / app_huellas'),('sku','Escanear SKU / revisar presencia\napp_skus / app_presencias'),('val','Validar cantidad / versión / origen\nCero con observación; PNC con cantidad'),('count','Persistir evento idempotente\napp_eventos → proyección app_skus'),('photo','Guardar evidencia\narchivos.py / app_evidencias'),('queue','Cola de copia\napp_copias_drive / drive.py'),('confirm','¿Drive confirmó contenido y destino?'),('report','Preparar / revisar informes\napp_informes · versión y huella'),('send','Seleccionar nombres y adjuntos\ngestion.py → entregas.py'),('sent','¿Gmail confirmó la entrega?'),('fin','Resultado / auditoría / actualización\napp_entregas · app_auditoria_general')]
    for j,(i,t) in enumerate(textos):nodo(r,i,t,100+(j//7)*650,130+(j%7)*180,430,100,'shape=rhombus;' if i in ('confirm','sent','val') else '')
    for a,b in zip(textos,textos[1:]):edge(r,a[0],b[0],'Sí / continuar' if a[0] in ('confirm','sent','val') else '')
    nodo(r,'retry','Pendiente / revisión\nConservar identidad, revisar error\nReintento controlado',1370,350,350,120);edge(r,'confirm','retry','No');edge(r,'retry','queue','Tras resolver')
    nodo(r,'mailretry','Sin confirmación\nRevisar entrega y Enviados\nEvitar duplicación',1370,820,350,120);edge(r,'sent','mailretry','No')
    nodo(r,'conflict','Error / conflicto\nRevisar versión y corregir datos\nNo aceptar una escritura obsoleta',750,1500,430,110);edge(r,'val','conflict','No');edge(r,'conflict','sku','Revisar')
    r=pagina('03 Modelo relacional');titulo(r,'30 tablas declaradas','Claves externas extraídas de app/models.py · no es inspección del esquema productivo')
    ts=M.diccionario()
    for j,t in enumerate(ts):
        keys=[f['nombre'] for f in t['campos'] if f['opciones'].get('primary_key')=='True']
        fks=[f['nombre']+' → '+','.join(f['referencias']) for f in t['campos'] if f['referencias']]
        nodo(r,t['tabla'],t['tabla']+'\nPK: '+', '.join(keys)+'\n'+t['uso']+'\n'+'\n'.join(fks),30+(j%5)*400,130+(j//5)*330,360,280,'fontSize=12;align=left;fillColor='+('#f0faf4;' if t['tabla'].startswith('app_') else '#fff4dc;'))
    for t in ts:
        for f in t['campos']:
            for ref in f['referencias']:edge(r,t['tabla'],ref.split('.')[0],f['nombre'])
    r=pagina('04 Estructura del código');titulo(r,'Código y responsabilidades','Estructura principal del repositorio · rutas verificadas en código')
    groups=[('app/main.py\nArranque FastAPI y /app/','app/config.py + db.py\nConfiguración / motor / sesiones','app/models.py\nModelo relacional de 30 tablas'),('app/routers/\nAPI, autenticación y autorización','app/services/app_modelo.py\nProyección de operación','app/services/calidad.py\nClasificación PNC'),('app/services/archivos.py\nBytes, metadatos y miniaturas','app/services/drive.py\nCola durable y recuperación','google_drive_api.py\nIdentidad remota y checksum'),('google_cuentas.py\nOAuth / tokens','google_gmail_api.py\nConsulta / envío autorizado','app/services/entregas.py\nInstantánea y cola de entrega'),('firebase/public/\nHTML / CSS / JS / service worker','scripts/\nActualizador / respaldo / diagnóstico','tests/\nVerificación en entorno aislado')]
    for j,row in enumerate(groups):
        for k,t in enumerate(row):nodo(r,'src'+str(j)+str(k),t,60+k*520,150+j*200,440,130)
    r=pagina('05 Evidencias y carpetas');titulo(r,'Evidencias: servidor y Drive','Segmentos opcionales y rutas materializadas al subir · conservar referencias históricas')
    nodo(r,'local','VAL_DATA_DIR\napp_archivos/ID\napp_miniaturas/ID\nsecretos/integraciones.key',40,140,350,170)
    nodo(r,'metadata','MySQL\napp_archivos / app_evidencias\napp_archivo_skus / identidades\napp_copias_drive',470,140,400,170);edge(r,'local','metadata','Identidad y estado')
    nodo(r,'tree','CARPETA_RAIZ / CLIENTE / MARCA / RECEPCION\n\nINFORMES\nEMBARQUE (si aplica)\n  PRE-INGRESO\n  PANORAMICAS\n  FOTOS-FINALES\n  BULTOS / Bulto… / Caja…\n  PRODUCTOS / SKU\n  PNC / SKU\n  SOBRANTES / SKU\n  FALTANTES / SKU\n\nCOMPARTIDAS / POR-ASIGNAR según asignación\nOTRAS-EVIDENCIAS como categoría alternativa',1000,140,700,600,'align=left;');edge(r,'metadata','tree','OAuth → copiar → confirmar')
    nodo(r,'rules','La preparación consulta; la subida crea la ruta utilizada.\nUna carga fallida puede dejar una ruta vacía.\nMulti-SKU / multi-destino: accesos directos al archivo.\nEl nombre de la carpeta no sustituye cantidad/PNC/pallet.\nRespaldo local no sustituye retención de Drive.',40,430,800,230,'fillColor=#fff4dc;')
    X.indent(file);X.ElementTree(file).write(destino,encoding='utf-8',xml_declaration=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--salida',type=Path,required=True);a=p.parse_args();a.salida.mkdir(parents=True,exist_ok=True)
    M.slides=slides
    import base64
    html=M.presentacion('data:image/png;base64,'+base64.b64encode((ROOT/'firebase/public/logo-itsa.png').read_bytes()).decode())
    html=html.replace('Arquitectura y mantenimiento','Funcionamiento y rendimiento').replace('IV ITSANET · Arquitectura técnica','IV ITSANET · Funcionamiento y rendimiento')
    css='.pasos-demo{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}.etapa[aria-pressed=true]{background:#225de2;color:white}.carga{display:block;padding:15px;background:#eef4ff;border-radius:10px}.metricas strong{font-size:30px;color:#176b79}.slide input[type=number]{display:block;max-width:100%;padding:10px;border:1px solid #a7b9d1;border-radius:8px;font:inherit;width:100%;margin-top:8px}.slide details{font-size:13px}.slide .mini{line-height:1.45}@media print{.slide .pasos-demo button{display:inline-block}.slide details{font-size:8pt}.slide details>p{display:block}.slide .metricas strong{font-size:22px}.slide input{font-size:10pt}}'
    html=html.replace('</style>',css+'</style>').replace('</body>','<script>'+EXTRA_JS+'</script></body>')
    (a.salida/'Presentacion-tecnica-ITSANET-20261028.html').write_text(html)
    diagramas(a.salida/'IV-ITSANET-Arquitectura-y-flujos.drawio')
    print(json.dumps({'diapositivas':len(slides()),'paginasDrawio':5,'salida':str(a.salida)}))


if __name__=='__main__':main()
