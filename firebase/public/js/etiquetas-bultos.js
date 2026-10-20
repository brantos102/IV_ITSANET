import {pedir,nuevoIdentificador} from './local.js?v=20261020-60';
import {esc} from './evidencias.js?v=20261020-60';
import {tecladoDialogo} from './modal.js?v=20261020-60';

const api=(ruta,opciones={})=>pedir(ruta,{...opciones,base:'/api/impresion'});
function barras(serie){
  if(!globalThis.JsBarcode)throw new Error('Recarga la página para cargar el generador de etiquetas.');
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  JsBarcode(svg,serie,{format:'CODE128',displayValue:false,height:65,width:1,margin:8});
  svg.setAttribute('viewBox',`0 0 ${parseFloat(svg.getAttribute('width'))} ${parseFloat(svg.getAttribute('height'))}`);
  svg.setAttribute('preserveAspectRatio','none');
  svg.style.width='100%';svg.style.height='100%';return svg.outerHTML;
}

export function htmlEtiquetasBultos(lote,dibujar=barras){
  const alto=lote.formato==='100x150'?150:50;
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Bultos ${esc(lote.recepcion)} · L${lote.lote}</title><style>
    @page{size:100mm ${alto}mm;margin:0}*{box-sizing:border-box}html,body{margin:0;color:#000;background:white;font-family:Arial,sans-serif}
    .etiqueta-bulto{width:100mm;height:${alto}mm;padding:${alto===150?6:4}mm;overflow:hidden;break-after:page;break-inside:avoid;display:flex;flex-direction:column;justify-content:center;text-align:center;gap:${alto===150?10:3}mm}
    .etiqueta-bulto>*{flex-shrink:0}.etiqueta-bulto:last-child{break-after:auto}.cliente{font-size:${alto===150?17:10}pt;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.recepcion{font-size:${alto===150?10:8}pt;overflow-wrap:anywhere}
    .rotulo{font-size:${alto===150?88:56}pt;line-height:1.05;font-weight:800;margin:0;letter-spacing:1mm}.rotulo-largo{font-size:${alto===150?72:44}pt}.numero{font-size:${alto===150?27:14}pt;font-weight:bold}
    .marca,.madre{font-size:${alto===150?10:8}pt;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.codigo{height:${alto===150?44:17}mm;width:100%}.codigo svg{display:block;width:100%;height:100%}.id{font-size:${alto===150?6:5.5}pt}
    @media print{body{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
    </style></head><body>${lote.etiquetas.map(e=>`<article class="etiqueta-bulto"><div class="rotulo${e.rotulo.length>4?' rotulo-largo':''}">${esc(e.rotulo)}</div><div class="codigo">${dibujar(e.rotulo)}</div></article>`).join('')}</body></html>`;
}

export async function abrirEtiquetasBultos(codigo){
  const ruta='/recepciones/'+encodeURIComponent(codigo)+'/bultos';
  let [estado,preferencias]=await Promise.all([api(ruta),pedir('/preferencias',{base:'/api/operacion'})]);
  let pendiente=null,ocupado=false,ultimo=null;
  const d=document.createElement('dialog');d.className='dialogo-operativo bultos-dialogo';
  d.innerHTML=`<header class="acciones"><h2>Etiquetas de bultos</h2><button class="b-sec" data-cerrar>Cerrar</button></header><p>${esc(codigo)}</p>
    <div class="rejilla"><label class="campo"><span>Literal</span><input data-literal maxlength="1" pattern="[A-Za-z]" placeholder="A, B, C…"></label>
    <label class="campo"><span>Total confirmado de bultos</span><input data-total type="number" min="1" max="1000" step="1"></label>
    <label class="campo"><span>Tamaño</span><select data-formato><option value="100x150">10 × 15 cm</option><option value="100x50">10 × 5 cm</option></select></label>
    <label class="campo"><span>Destino</span><select data-destino><option value="NAVEGADOR">Imprimir / PDF en esta PC</option><option value="ZPL">Descargar ZPL</option>${preferencias.impresoras.length?'<option value="ESTACION">Impresora mediante PC puente</option>':''}</select></label>
    <label class="campo" data-elegir-estacion hidden><span>Estación</span><select data-estacion>${preferencias.impresoras.map(p=>`<option value="${esc(p.id)}">${esc(p.nombre)}</option>`).join('')}</select></label></div>
    <p data-resumen class="bultos-resumen"></p><p class="mini">1. Confirma literal y cantidad. 2. Revisa la etiqueta. 3. Imprime al 100 %, sin márgenes ni encabezados. El código de barras contiene exactamente el número de bulto.</p>
    <details><summary>Solicitudes anteriores</summary><div data-historial></div></details>
    <p data-estado role="status" aria-live="polite"></p><div class="acciones"><button class="b-primario" data-generar>Confirmar e imprimir</button><button class="b-sec" data-nuevo>Actualizar / nueva solicitud</button><button class="b-sec" data-ver-estado hidden>Consultar envío</button></div>
    <details open><summary>Vista previa · mismo diseño que se imprime</summary><p class="mini">Se muestran hasta 3 etiquetas. La impresión incluye el total solicitado.</p><div data-vista class="vista-etiquetas"></div></details>`;
  document.body.append(d);d.showModal();const $=s=>d.querySelector(s);
  const controles=()=>[...d.querySelectorAll('input,select')];
  function pintarVista(lote){const html=htmlEtiquetasBultos({...lote,etiquetas:lote.etiquetas.slice(0,3)}),doc=new DOMParser().parseFromString(html,'text/html'),vista=$('[data-vista]');vista.replaceChildren();const host=document.createElement('div');host.className='bulto-preview';vista.append(host);const raiz=host.attachShadow({mode:'open'}),css=document.createElement('style');css.textContent=doc.querySelector('style').textContent+' .etiqueta-bulto{max-width:100%;height:auto;aspect-ratio:100/'+(lote.formato==='100x150'?150:50)+';padding:'+(lote.formato==='100x150'?6:4)+'cqw;gap:'+(lote.formato==='100x150'?10:3)+'cqw;margin:10px auto;border:1px solid #a3afbe;box-shadow:0 3px 10px #0002;background:white;color:black} .rotulo{font-size:'+(lote.formato==='100x150'?31:19.75)+'cqw} .rotulo-largo{font-size:'+(lote.formato==='100x150'?25.4:15.5)+'cqw} .codigo{height:'+(lote.formato==='100x150'?44:17)+'cqw}';raiz.append(css,...[...doc.body.children].map(e=>document.importNode(e,true)));}
  const resumen=()=>{const literal=$('[data-literal]').value.trim().toUpperCase(),total=Number($('[data-total]').value);if(/^[A-Z]$/.test(literal)&&Number.isInteger(total)&&total>0&&total<=1000){pintarVista({...estado,lote:'vista previa',formato:$('[data-formato]').value,etiquetas:Array.from({length:Math.min(total,3)},(_,i)=>({rotulo:literal+String(i+1).padStart(2,'0')}))});}else{$('[data-vista]').textContent='Escribe un literal y un total válido para ver la etiqueta.';}$('[data-resumen]').textContent=`${$('[data-literal]').value.toUpperCase() || 'B'}01 → ${$('[data-literal]').value.toUpperCase() || 'B'}${String($('[data-total]').value || 0).padStart(2,'0')} · ${$('[data-total]').value || 0} etiquetas`;
    $('[data-elegir-estacion]').hidden=$('[data-destino]').value!=='ESTACION';};
  const pintar=()=>{$('[data-literal]').value=estado.literal;$('[data-total]').value=estado.total || 1;$('[data-formato]').value=estado.formato;
    $('[data-historial]').innerHTML=estado.anteriores.length?estado.anteriores.map(j=>`<p>L${j.lote} · ${esc(j.usuario)} · ${esc(new Date(j.fecha).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}))} · ${j.total} etiquetas · ${esc(j.estado)}</p>`).join(''):'Sin solicitudes anteriores.';
    $('[data-estado]').textContent=estado.cerrada?'Recepción cerrada. Reabre si necesitas emitir etiquetas.':estado.anteriores.length?'Ya existen lotes generados: una nueva solicitud se registrará como reimpresión.':'';
    controles().forEach(e=>e.disabled=estado.cerrada);$('[data-generar]').disabled=estado.cerrada;resumen();};
  controles().forEach(e=>e.addEventListener('input',resumen));pintar();
  $('[data-generar]').onclick=async()=>{
    if(ocupado)return;
    const total=Number($('[data-total]').value),literal=$('[data-literal]').value.trim().toUpperCase();
    if(!Number.isInteger(total)||total<1||total>1000||!/^[A-Z]$/.test(literal)){$('[data-estado]').textContent='Confirma un total entero de 1 a 1000 y un literal de una letra (A–Z).';return;}
    const destino=$('[data-destino]').value;
    const ventana=destino==='NAVEGADOR'?window.open('','_blank'):null;
    if(destino==='NAVEGADOR'&&!ventana){$('[data-estado]').textContent='Permite ventanas emergentes para imprimir o elige Descargar ZPL.';return;}
    ocupado=true;controles().forEach(e=>e.disabled=true);$('[data-generar]').disabled=true;$('[data-nuevo]').disabled=true;$('[data-cerrar]').disabled=true;
    pendiente=pendiente || {clave:nuevoIdentificador(),version:estado.version,cantidadAnterior:estado.total,total,literal,
      formato:$('[data-formato]').value,destino,estacion:destino==='ESTACION'?$('[data-estacion]').value:null};
    try{
      const lote=await api(ruta,{cuerpo:pendiente});ultimo=lote;
      const html=htmlEtiquetasBultos(lote);pintarVista(lote);
      if(destino==='NAVEGADOR'){ventana.document.write(html);ventana.document.close();ventana.focus();ventana.print();}
      if(destino==='ZPL'){const url=URL.createObjectURL(new Blob([lote.zpl],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`bultos-${codigo.replace(/[^A-Za-z0-9_-]/g,'_')}-L${lote.lote}.zpl`;a.click();setTimeout(()=>URL.revokeObjectURL(url),4000);}
      $('[data-estado]').textContent=`Lote ${lote.lote} · ${total} etiquetas correlativas · ${lote.estado==='PENDIENTE'?'Pendiente de envío por el puente':'Generadas; confirma el resultado en la impresora'}.`;
      $('[data-ver-estado]').hidden=destino!=='ESTACION';pendiente=null;
    }catch(e){ventana?.close();if([401,403,404,409,422].includes(e.estado)){pendiente=null;$('[data-estado]').textContent=e.message+' Usa Actualizar para revisar los datos.';}else{$('[data-estado]').textContent=e.message+' Usa Reintentar para conservar el mismo identificador.';}$('[data-generar]').textContent='Reintentar misma solicitud';$('[data-generar]').disabled=false;}
    finally{ocupado=false;$('[data-cerrar]').disabled=false;$('[data-nuevo]').disabled=!!pendiente;}
  };
  $('[data-ver-estado]').onclick=async()=>{try{const j=await api('/trabajos/'+ultimo.id);$('[data-estado]').textContent=`Lote ${ultimo.lote} · ${j.copias} etiquetas · ${j.estado}`;}catch(e){$('[data-estado]').textContent=e.message;}};
  $('[data-nuevo]').onclick=async()=>{try{estado=await api(ruta);pendiente=null;$('[data-generar]').textContent='Confirmar e imprimir';pintar();}catch(e){$('[data-estado]').textContent=e.message;}};
  tecladoDialogo(d,{accion:'[data-generar]'});
  $('[data-cerrar]').onclick=()=>d.close();d.addEventListener('cancel',e=>{if(ocupado)e.preventDefault();});d.addEventListener('close',()=>d.remove());return d;
}
