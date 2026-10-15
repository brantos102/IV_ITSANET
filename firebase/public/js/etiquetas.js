/** Zebra ZD421, 203 dpi. La plantilla 10 X 5 de Windows se conserva. */
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function validarEtiqueta(d) {
  if (!/^[\x21-\x7e]{1,42}$/.test(String(d.sku || ''))) throw new Error('El código necesita de 1 a 42 caracteres imprimibles.');
  if (!Number.isFinite(Number(d.cantidad)) || Number(d.cantidad) <= 0) throw new Error('La cantidad debe ser mayor que cero.');
  return {...d, sku:String(d.sku), cantidad:Number(d.cantidad), cliente:d.cliente || 'ITSANET', estado:d.estado || 'NUV'};
}
const hex = valor => [...new TextEncoder().encode(String(valor ?? ''))].map(b => '\\' + b.toString(16).padStart(2,'0').toUpperCase()).join('');
export function generarZpl(datos) {
  const d = validarEtiqueta(datos);
  const texto = (x,y,h,w,valor,ancho,lineas=1) => `^FO${x},${y}^A0N,${h},${w}^FB${ancho},${lineas},2,L,0^FH\\^FD${hex(valor)}^FS`;
  return ['^XA','^CI28','^PW800','^LL400','^LH0,0','^FO10,10^GB779,380,2^FS','^FO520,10^GB2,380,2^FS',
    '^FO520,86^GB269,2,2^FS','^FO648,86^GB2,180,2^FS','^FO520,266^GB269,2,2^FS',
    texto(22,22,34,30,d.cliente.toUpperCase(),485),texto(22,68,19,17,'CODIGO:',480),
    `^FO36,101^BY${d.sku.length > 20 ? 1 : 2},2,70^BCN,70,N,N,N,A^FH\\^FD${hex(d.sku)}^FS`,
    texto(70,180,24,20,d.sku,440),texto(22,216,18,16,'DESCRIPCION:',480),
    texto(22,241,20,17,String(d.descripcion || '').slice(0,100),480,2),
    texto(22,322,19,17,'SERIE: ' + (d.serie || ''),480,2),
    texto(534,27,28,22,d.estado === 'PNC' ? 'CUARENTENA' : 'DISPONIBLE',245),
    texto(532,139,23,21,'QTY',112),texto(662,139,23,19,'ESTADO',120),
    texto(538,185,38,28,d.cantidad,108),texto(610,212,17,13,'CS',32),
    texto(667,194,29,25,d.estado,110),texto(533,280,23,17,'RESPONSABLE',245),
    texto(534,318,20,15,String(d.responsable || '').slice(0,48),245,2),'^PQ1','^XZ'].join('\n');
}
export const ESTILO_ETIQUETA = `
@page{size:100mm 50mm;margin:0}*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#000;font-family:Arial,sans-serif}
.etiqueta{width:100mm;height:50mm;padding:1.3mm;display:grid;grid-template-columns:65% 35%;font-size:9pt;break-after:page}
.izq{border:1px solid #000;padding:1.3mm;display:flex;flex-direction:column;min-width:0}.empresa{font-size:19pt;font-weight:900;white-space:nowrap;overflow:hidden}
.codigo-titulo{font-size:9pt;font-weight:800}.barras{height:13mm;width:100%;display:block}.codigo{font-size:12pt;font-weight:700;text-align:center}
.descripcion{border-top:1px solid #000;font-size:8pt;line-height:1.15;margin-top:1mm;padding-top:.7mm;height:12mm;overflow:hidden}.serie{font-size:9pt;margin-top:auto;overflow:hidden}
.der{border:1px solid #000;border-left:0;display:grid;grid-template-rows:9mm 21mm 1fr;min-width:0}.disponible{font-weight:900;font-size:13pt;text-align:center;padding-top:2mm;border-bottom:1px solid #000}
.qty-estado{display:grid;grid-template-columns:1fr 1fr;text-align:center;align-items:center}.qty-estado>div+div{border-left:1px solid #000}.qty-estado b{display:block;font-size:10.5pt}.qty-estado strong{display:block;font-size:19pt;margin-top:2mm}.qty-estado small{font-size:8pt}
.responsable{border-top:1px solid #000;padding:1.5mm;font-size:8pt;overflow:hidden}.responsable b{display:block;font-size:10pt;margin-bottom:1mm}
@media print{.etiqueta{position:fixed;top:0;left:0;break-after:auto;print-color-adjust:exact;-webkit-print-color-adjust:exact}}
`;
export function htmlEtiqueta(datos, barras) {
  const d = validarEtiqueta(datos);
  return `<div class="etiqueta"><div class="izq"><div class="empresa">${esc(d.cliente)}</div><div class="codigo-titulo">CODIGO:</div>${barras}<div class="codigo">${esc(d.sku)}</div><div class="descripcion"><b>DESCRIPCION:</b><br>${esc(d.descripcion)}</div><div class="serie"><b>SERIE:</b> ${esc(d.serie)}</div></div><div class="der"><div class="disponible">${d.estado === 'PNC' ? 'CUARENTENA' : 'DISPONIBLE'}</div><div class="qty-estado"><div><b>QTY</b><strong>${d.cantidad}</strong><small>CS</small></div><div><b>ESTADO</b><strong>${esc(d.estado)}</strong></div></div><div class="responsable"><b>RESPONSABLE</b>${esc(d.responsable)}</div></div></div>`;
}
function barrasDe(sku) {
  if (!globalThis.JsBarcode) throw new Error('No se cargó el generador de código de barras. Recarga la página.');
  const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
  JsBarcode(svg, sku, {format:'CODE128',displayValue:false,height:65,width:2,margin:8});
  svg.setAttribute('viewBox', `0 0 ${parseFloat(svg.getAttribute('width'))} ${parseFloat(svg.getAttribute('height'))}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.classList.add('barras'); return svg.outerHTML;
}
export function abrirEtiqueta(datos) {
  const dialogo = document.createElement('dialog'); dialogo.className = 'etiqueta-dialogo';
  dialogo.innerHTML = `<h2>Etiqueta · Zebra 100 × 50 mm</h2><p class="mini">Formato existente «10 X 5», escala 100 %, márgenes y encabezados desactivados.</p><form method="dialog" class="rejilla">
    <label class="campo"><span>Cantidad física</span><input name="cantidad" type="number" step="any" min="0.001" value="${Number(datos.cantidad)||1}" required></label>
    <label class="campo"><span>Estado</span><select name="estado"><option>NUV</option><option>PNC</option></select></label>
    <label class="campo"><span>Serie</span><input name="serie" maxlength="80"></label>
    <label class="campo"><span>Responsable</span><input name="responsable" maxlength="80"></label></form>
    <div class="etiqueta-preview" title="Vista previa a escala"><iframe id="etiquetaVista" title="Vista previa de etiqueta" sandbox></iframe></div><p class="mini" id="errorEtiqueta" role="alert"></p>
    <div class="acciones"><button class="b-primario" data-imprimir>Imprimir / PDF</button><button class="b-sec" data-zpl>Descargar ZPL</button><button class="b-sec" data-cerrar>Cerrar</button></div>`;
  document.body.append(dialogo); dialogo.querySelector('[name=serie]').value = datos.serie || ''; dialogo.querySelector('[name=estado]').value = datos.estado || 'NUV';
  dialogo.querySelector('[name=responsable]').value = datos.responsable || '';
  let actual, dibujo;
  function actualizar() {
    try { actual = validarEtiqueta({...datos,...Object.fromEntries(new FormData(dialogo.querySelector('form')))}); dibujo = barrasDe(actual.sku);
      const contenedor = dialogo.querySelector('#etiquetaVista'); contenedor.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><style>${ESTILO_ETIQUETA}</style></head><body>${htmlEtiqueta(actual,dibujo)}</body></html>`;
      dialogo.querySelector('#errorEtiqueta').textContent = ''; return true;
    } catch(e) { dialogo.querySelector('#errorEtiqueta').textContent = e.message; return false; }
  }
  dialogo.addEventListener('input',actualizar); dialogo.addEventListener('change',actualizar);
  dialogo.querySelector('[data-cerrar]').onclick = () => dialogo.close();
  dialogo.addEventListener('close',()=>dialogo.remove());
  dialogo.querySelector('[data-zpl]').onclick = () => { if (!actualizar()) return;
    const url=URL.createObjectURL(new Blob([generarZpl(actual)],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='etiqueta-'+actual.sku.replace(/[^A-Za-z0-9_-]/g,'_')+'.zpl';a.click();setTimeout(()=>URL.revokeObjectURL(url),4000); };
  dialogo.querySelector('[data-imprimir]').onclick = () => { if (!actualizar()) return;
    const ventana = window.open('','_blank','width=850,height=500');
    if (!ventana) { dialogo.querySelector('#errorEtiqueta').textContent='Permite abrir la ventana de impresión.'; return; }
    ventana.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Etiqueta ${esc(actual.sku)}</title><style>${ESTILO_ETIQUETA}</style></head><body>${htmlEtiqueta(actual,dibujo)}</body></html>`);
    ventana.document.close(); ventana.addEventListener('load',()=>{ventana.focus();ventana.print();},{once:true}); };
  dialogo.showModal(); actualizar();
}
