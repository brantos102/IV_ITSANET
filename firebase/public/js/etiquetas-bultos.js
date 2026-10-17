import {pedir,nuevoIdentificador} from './local.js?v=20261016-35';
import {esc} from './evidencias.js?v=20261016-35';

const api=(ruta,opciones={})=>pedir(ruta,{...opciones,base:'/api/impresion'});
function barras(serie){
  if(!globalThis.JsBarcode)throw new Error('Recarga la página para cargar el generador de etiquetas.');
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  JsBarcode(svg,serie,{format:'CODE128',displayValue:false,height:65,width:1,margin:8});
  svg.setAttribute('viewBox',`0 0 ${parseFloat(svg.getAttribute('width'))} ${parseFloat(svg.getAttribute('height'))}`);
  svg.style.width='100%';svg.style.height='100%';return svg.outerHTML;
}

export function htmlEtiquetasBultos(lote,dibujar=barras){
  const alto=lote.formato==='100x150'?150:50;
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Bultos ${esc(lote.recepcion)} · L${lote.lote}</title><style>
    @page{size:100mm ${alto}mm;margin:0}*{box-sizing:border-box}html,body{margin:0;color:#000;background:white;font-family:Arial,sans-serif}
    .etiqueta-bulto{width:100mm;height:${alto}mm;padding:${alto===150?3:2}mm;overflow:hidden;break-after:page;break-inside:avoid;display:flex;flex-direction:column;text-align:center;gap:${alto===150?1:0.5}mm}
    .etiqueta-bulto>*{flex-shrink:0}.etiqueta-bulto:last-child{break-after:auto}.cliente{font-size:${alto===150?17:10}pt;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.recepcion{font-size:${alto===150?10:8}pt;overflow-wrap:anywhere}
    .rotulo{font-size:${alto===150?48:26}pt;font-weight:bold;margin:${alto===150?15:0}mm 0 0}.numero{font-size:${alto===150?27:14}pt;font-weight:bold}
    .marca,.madre{font-size:${alto===150?10:8}pt;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.codigo{height:${alto===150?28:11}mm;width:100%;margin-top:auto}.id{font-size:${alto===150?6:5.5}pt}
    @media print{body{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
    </style></head><body>${lote.etiquetas.map(e=>`<article class="etiqueta-bulto"><div class="cliente">${esc(lote.cliente)}</div><div class="recepcion">${esc(lote.recepcion)}</div><div class="rotulo">${esc(e.rotulo)}</div><div class="numero">BULTO ${e.numero} DE ${e.total}</div><div class="marca">${esc(lote.marca)}</div>${alto===150&&e.codigoMadre?`<div class="madre">Caja madre: ${esc(e.codigoMadre)}</div>`:''}<div class="codigo">${dibujar(e.serie)}</div><div class="id">ID ${esc(e.unidadId)} · Lote ${lote.lote}</div></article>`).join('')}</body></html>`;
}

export async function abrirEtiquetasBultos(codigo){
  const ruta='/recepciones/'+encodeURIComponent(codigo)+'/bultos';
  let [estado,preferencias]=await Promise.all([api(ruta),pedir('/preferencias',{base:'/api/operacion'})]);
  let pendiente=null,ocupado=false,ultimo=null;
  const d=document.createElement('dialog');d.className='dialogo-operativo';
  d.innerHTML=`<header class="acciones"><h2>Etiquetas de bultos</h2><button class="b-sec" data-cerrar>Cerrar</button></header><p>${esc(codigo)}</p>
    <div class="rejilla"><label class="campo"><span>Literal</span><input data-literal maxlength="8" pattern="[A-Za-z0-9]{1,8}" placeholder="B, P, CAJA…"></label>
    <label class="campo"><span>Total confirmado de bultos</span><input data-total type="number" min="1" max="1000" step="1"></label>
    <label class="campo"><span>Tamaño</span><select data-formato><option value="100x150">10 × 15 cm</option><option value="100x50">10 × 5 cm</option></select></label>
    <label class="campo"><span>Destino</span><select data-destino><option value="NAVEGADOR">Imprimir / PDF en esta PC</option><option value="ZPL">Descargar ZPL</option>${preferencias.impresoras.length?'<option value="ESTACION">Impresora mediante PC puente</option>':''}</select></label>
    <label class="campo" data-elegir-estacion hidden><span>Estación</span><select data-estacion>${preferencias.impresoras.map(p=>`<option value="${esc(p.id)}">${esc(p.nombre)}</option>`).join('')}</select></label></div>
    <p data-resumen></p><p class="mini">Una etiqueta por bulto. Si corriges el total, reemplaza las etiquetas anteriores para que todas indiquen el mismo total.</p>
    <details><summary>Solicitudes anteriores</summary><div data-historial></div></details>
    <p data-estado role="status" aria-live="polite"></p><div class="acciones"><button class="b-primario" data-generar>Confirmar e imprimir</button><button class="b-sec" data-nuevo>Actualizar / nueva solicitud</button><button class="b-sec" data-ver-estado hidden>Consultar envío</button></div>
    <details><summary>Vista previa del último lote</summary><iframe data-vista title="Etiquetas de bultos" sandbox style="width:100%;height:340px;border:0"></iframe></details>`;
  document.body.append(d);d.showModal();const $=s=>d.querySelector(s);
  const controles=()=>[...d.querySelectorAll('input,select')];
  const resumen=()=>{$('[data-resumen]').textContent=`${$('[data-literal]').value.toUpperCase() || 'B'}-001 → ${$('[data-literal]').value.toUpperCase() || 'B'}-${String($('[data-total]').value || 0).padStart(3,'0')} · ${$('[data-total]').value || 0} etiquetas`;
    $('[data-elegir-estacion]').hidden=$('[data-destino]').value!=='ESTACION';};
  const pintar=()=>{$('[data-literal]').value=estado.literal;$('[data-total]').value=estado.total || 1;$('[data-formato]').value=estado.formato;
    $('[data-historial]').innerHTML=estado.anteriores.length?estado.anteriores.map(j=>`<p>L${j.lote} · ${esc(j.usuario)} · ${esc(new Date(j.fecha).toLocaleString('es-EC',{timeZone:'America/Guayaquil'}))} · ${j.total} etiquetas · ${esc(j.estado)}</p>`).join(''):'Sin solicitudes anteriores.';
    $('[data-estado]').textContent=estado.cerrada?'Recepción cerrada. Reabre si necesitas emitir etiquetas.':estado.anteriores.length?'Ya existen lotes generados: una nueva solicitud se registrará como reimpresión.':'';
    controles().forEach(e=>e.disabled=estado.cerrada);$('[data-generar]').disabled=estado.cerrada;resumen();};
  controles().forEach(e=>e.addEventListener('input',resumen));pintar();
  $('[data-generar]').onclick=async()=>{
    if(ocupado)return;
    const total=Number($('[data-total]').value),literal=$('[data-literal]').value.trim().toUpperCase();
    if(!Number.isInteger(total)||total<1||total>1000||!/^[A-Z0-9]{1,8}$/.test(literal)){$('[data-estado]').textContent='Confirma un total entero de 1 a 1000 y un literal de 1 a 8 letras o números.';return;}
    const destino=$('[data-destino]').value;
    const ventana=destino==='NAVEGADOR'?window.open('','_blank'):null;
    if(destino==='NAVEGADOR'&&!ventana){$('[data-estado]').textContent='Permite ventanas emergentes para imprimir o elige Descargar ZPL.';return;}
    ocupado=true;controles().forEach(e=>e.disabled=true);$('[data-generar]').disabled=true;$('[data-nuevo]').disabled=true;$('[data-cerrar]').disabled=true;
    pendiente=pendiente || {clave:nuevoIdentificador(),version:estado.version,cantidadAnterior:estado.total,total,literal,
      formato:$('[data-formato]').value,destino,estacion:destino==='ESTACION'?$('[data-estacion]').value:null};
    try{
      const lote=await api(ruta,{cuerpo:pendiente});ultimo=lote;
      const html=htmlEtiquetasBultos(lote);$('[data-vista]').srcdoc=html;
      if(destino==='NAVEGADOR'){ventana.document.write(html);ventana.document.close();ventana.focus();ventana.print();}
      if(destino==='ZPL'){const url=URL.createObjectURL(new Blob([lote.zpl],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`bultos-${codigo.replace(/[^A-Za-z0-9_-]/g,'_')}-L${lote.lote}.zpl`;a.click();setTimeout(()=>URL.revokeObjectURL(url),4000);}
      $('[data-estado]').textContent=`Lote ${lote.lote} · ${total} etiquetas correlativas · ${lote.estado==='PENDIENTE'?'Pendiente de envío por el puente':'Generadas; confirma el resultado en la impresora'}.`;
      $('[data-ver-estado]').hidden=destino!=='ESTACION';pendiente=null;
    }catch(e){ventana?.close();if([401,403,404,409,422].includes(e.estado)){pendiente=null;$('[data-estado]').textContent=e.message+' Usa Actualizar para revisar los datos.';}else{$('[data-estado]').textContent=e.message+' Usa Reintentar para conservar el mismo identificador.';}$('[data-generar]').textContent='Reintentar misma solicitud';$('[data-generar]').disabled=false;}
    finally{ocupado=false;$('[data-cerrar]').disabled=false;$('[data-nuevo]').disabled=!!pendiente;}
  };
  $('[data-ver-estado]').onclick=async()=>{try{const j=await api('/trabajos/'+ultimo.id);$('[data-estado]').textContent=`Lote ${ultimo.lote} · ${j.copias} etiquetas · ${j.estado}`;}catch(e){$('[data-estado]').textContent=e.message;}};
  $('[data-nuevo]').onclick=async()=>{try{estado=await api(ruta);pendiente=null;$('[data-generar]').textContent='Confirmar e imprimir';pintar();}catch(e){$('[data-estado]').textContent=e.message;}};
  $('[data-cerrar]').onclick=()=>d.close();d.addEventListener('cancel',e=>{if(ocupado)e.preventDefault();});d.addEventListener('close',()=>d.remove());return d;
}
