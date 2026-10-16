/** Zebra ZD421, 203 dpi. La plantilla 10 X 5 de Windows se conserva. */
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function validarEtiqueta(d) {
  if (!/^[\x21-\x7e]{1,42}$/.test(String(d.sku || ''))) throw new Error('El código necesita de 1 a 42 caracteres imprimibles.');
  if (!Number.isFinite(Number(d.cantidad)) || Number(d.cantidad) <= 0) throw new Error('La cantidad debe ser mayor que cero.');
  if (d.serie && !/^[\x21-\x7e]{1,42}$/.test(String(d.serie))) throw new Error('La serie necesita hasta 42 caracteres imprimibles, sin espacios.');
  return {...d, sku:String(d.sku), cantidad:Number(d.cantidad), cliente:d.cliente || 'ITSANET', estado:d.estado || 'NUV',unidad:d.unidad ?? 'CS',categoria:d.estado === 'PNC' ? 'CUARENTENA' : (d.categoria || 'DISPONIBLE')};
}
/** Mismo mapeo B,C,D,E,G,H,I,J,L,M de la macro; no escribe en MySQL. */
export function etiquetaDesdeStock(fila) {
  return validarEtiqueta({cliente:fila[1],sku:fila[2],descripcion:fila[3],serie:fila[4],
    despacho:fila[6],responsable:fila[7],categoria:fila[8],estado:fila[9],unidad:fila[11],cantidad:fila[12]});
}
export function filasDeStock(libro) {
  const nombres=libro.SheetNames.filter(n=>['CONSOLIDADO','IMPRIMIR'].includes(n.toUpperCase()));
  if(!nombres.length) throw new Error('No hay hoja CONSOLIDADO o IMPRIMIR.');
  return nombres.flatMap(n=>XLSX.utils.sheet_to_json(libro.Sheets[n],{header:1,defval:''}).slice(1)
    .map((fila,i)=>({hoja:n,fila:i+2,datos:fila})).filter(r=>r.datos[2] !== ''));
}
const hex = valor => [...new TextEncoder().encode(String(valor ?? ''))].map(b => '\\' + b.toString(16).padStart(2,'0').toUpperCase()).join('');
export function generarZpl(datos) {
  const d = validarEtiqueta(datos);
  const copias=Number(datos.copias ?? 1);
  if(!Number.isInteger(copias) || copias<1 || copias>5000)throw new Error('Copias: de 1 a 5000.');
  const texto = (x,y,h,w,valor,ancho,lineas=1) => `^FO${x},${y}^A0N,${h},${w}^FB${ancho},${lineas},2,L,0^FH\\^FD${hex(valor)}^FS`;
  return ['^XA','^CI28','^PW800','^LL400','^LH0,0',
    texto(22,22,34,30,d.cliente.toUpperCase(),485),texto(22,68,19,17,'CODIGO:',480),
    `^FO36,101^BY${d.sku.length > 20 ? 1 : 2},2,70^BCN,70,N,N,N,A^FH\\^FD${hex(d.sku)}^FS`,
    texto(70,180,24,20,d.sku,440),texto(22,216,18,16,'DESCRIPCION:',480),
    texto(22,241,20,17,String(d.descripcion || '').slice(0,100),480,2),
    texto(22,300,19,17,'SERIE:',480),
    ...(d.serie ? [`^FO36,326^BY${String(d.serie).length > 20 ? 1 : 2},2,32^BCN,32,N,N,N,A^FH\\^FD${hex(d.serie)}^FS`,texto(22,367,18,15,d.serie,480)] : []),
    texto(534,27,28,22,String(d.categoria).slice(0,18),245),
    texto(534,62,17,14,String(d.despacho || '').slice(0,28),245),
    texto(532,139,23,21,'QTY',112),texto(662,139,23,19,'ESTADO',120),
    texto(538,185,38,28,d.cantidad,108),texto(605,226,17,13,String(d.unidad).slice(0,5),40),
    texto(667,194,29,25,d.estado,110),texto(533,280,23,17,'RESPONSABLE',245),
    texto(534,318,20,15,String(d.responsable || '').slice(0,48),245,2),'^PQ'+copias,'^XZ'].join('\n');
}
export const ESTILO_ETIQUETA = `
@page{size:100mm 50mm;margin:0}*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#000;font-family:Arial,sans-serif}
.etiqueta{width:100mm;height:50mm;padding:1.3mm;display:grid;grid-template-columns:65% 35%;font-size:9pt;break-after:page;break-inside:avoid;overflow:hidden}
.izq{border:0;padding:1mm;display:flex;flex-direction:column;min-width:0;min-height:0}.empresa{font-size:17pt;font-weight:900;white-space:nowrap;overflow:hidden}
.codigo-titulo{font-size:9pt;font-weight:800}.barras{height:10mm;width:100%;display:block;flex-shrink:0}.codigo{font-size:10pt;font-weight:700;text-align:center}
.descripcion{border-top:0;font-size:8pt;line-height:1.15;margin-top:.5mm;padding-top:.5mm;height:8mm;flex-shrink:0;overflow:hidden}.serie{font-size:8pt;margin-top:auto;overflow:hidden}.serie .barras{height:4mm}.serie .numero-serie{font-size:7pt;text-align:center}
.der{border:0;display:grid;grid-template-rows:9mm 21mm 1fr;min-width:0}.disponible{font-weight:900;font-size:13pt;text-align:center;padding-top:2mm;border-bottom:0}
.qty-estado{display:grid;grid-template-columns:1fr 1fr;text-align:center;align-items:center}.qty-estado>div+div{border-left:0}.qty-estado b{display:block;font-size:10.5pt}.qty-estado strong{display:block;font-size:19pt;margin-top:2mm}.qty-estado small{font-size:8pt}
.valor-unidad{display:flex;justify-content:center;align-items:baseline;gap:1mm}.responsable{border-top:0;padding:1.5mm;font-size:8pt;overflow:hidden}.responsable b{display:block;font-size:10pt;margin-bottom:1mm}
@media print{.etiqueta{position:fixed;top:0;left:0;break-after:auto;print-color-adjust:exact;-webkit-print-color-adjust:exact}}
`;
export function htmlEtiqueta(datos, barras, barrasSerie='') {
  const d = validarEtiqueta(datos);
  return `<div class="etiqueta"><div class="izq"><div class="empresa">${esc(d.cliente)}</div><div class="codigo-titulo">CODIGO:</div>${barras}<div class="codigo">${esc(d.sku)}</div><div class="descripcion"><b>DESCRIPCION:</b><br>${esc(d.descripcion)}</div><div class="serie"><b>SERIE:</b>${barrasSerie}<div class="numero-serie">${esc(d.serie)}</div></div></div><div class="der"><div class="disponible">${esc(d.categoria)}${d.despacho ? `<small style="display:block;font-size:8pt">${esc(d.despacho)}</small>` : ''}</div><div class="qty-estado"><div><b>QTY</b><div class="valor-unidad"><strong>${d.cantidad}</strong><small>${esc(d.unidad)}</small></div></div><div><b>ESTADO</b><strong>${esc(d.estado)}</strong></div></div><div class="responsable"><b>RESPONSABLE</b>${esc(d.responsable)}</div></div></div>`;
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
  let base={...datos,cantidad:1};
  const dialogo = document.createElement('dialog'); dialogo.className = 'etiqueta-dialogo';
  dialogo.innerHTML = `<h2>Etiqueta · Zebra 100 × 50 mm</h2><details><summary>Tomar datos de stock Excel (opcional)</summary><p class="mini">Hojas CONSOLIDADO o IMPRIMIR. Solo lectura para esta etiqueta; no importa existencias.</p><input type="file" data-stock accept=".xlsx,.xls"><select data-fila aria-label="Fila de stock" hidden></select></details><p class="mini">Formato existente «10 X 5», escala 100 %, márgenes y encabezados desactivados.</p><form method="dialog" class="rejilla">
    <label class="campo"><span>Unidades por etiqueta</span><input name="cantidad" type="number" value="1" readonly></label>
    <label class="campo"><span>Número de copias</span><input name="copias" type="number" min="1" max="5000" value="1" required></label>
    <label class="campo"><span>Estado</span><input name="estado" list="estadosEtiqueta" maxlength="15"><datalist id="estadosEtiqueta"><option value="NUV"><option value="PNC"></datalist></label>
    <label class="campo"><span>Unidad</span><input name="unidad" maxlength="5"></label>
    <label class="campo"><span>Categoría lógica</span><input name="categoria" maxlength="18"></label>
    <label class="campo"><span>Despacho</span><input name="despacho" maxlength="28"></label>
    <label class="campo"><span>Serie</span><input name="serie" maxlength="42"></label>
    <label class="campo"><span>Responsable</span><input name="responsable" maxlength="80"></label></form>
    <div class="etiqueta-preview" title="Vista previa a escala"><iframe id="etiquetaVista" title="Vista previa de etiqueta" sandbox></iframe></div><p class="mini" id="errorEtiqueta" role="alert"></p>
    <label class="campo"><span>Estación de impresión en red</span><select data-estacion><option value="">Sin estación configurada</option></select></label>
    <div class="acciones"><button class="b-primario" data-imprimir>Imprimir / PDF</button><button class="b-sec" data-puente disabled>Enviar al puente</button><button class="b-sec" data-zpl>Descargar ZPL</button><button class="b-sec" data-cerrar>Cerrar</button></div>`;
  document.body.append(dialogo); dialogo.querySelector('[name=serie]').value = datos.serie || ''; dialogo.querySelector('[name=estado]').value = datos.estado || 'NUV';
  for(const campo of ['responsable','unidad','categoria','despacho']) dialogo.querySelector(`[name=${campo}]`).value=datos[campo] ?? ({unidad:'CS',categoria:'DISPONIBLE'}[campo] || '');
  const movil=matchMedia('(pointer:coarse)').matches && matchMedia('(max-width:1024px)').matches;
  if(movil) {dialogo.querySelector('[data-imprimir]').disabled=true;dialogo.querySelector('[data-imprimir]').title='Imprime desde la PC que tiene instalada la Zebra.';}
  const nota=document.createElement('p');nota.className='mini';nota.textContent='Impresión opcional desde la PC con el controlador Zebra. No hace falta imprimir para guardar o finalizar.';dialogo.append(nota);
  if(Number.isInteger(Number(datos.unidadesReferencia)) && Number(datos.unidadesReferencia)>1){const b=document.createElement('button');b.className='chip';b.textContent=`Usar ${datos.unidadesReferencia} copias de 1 unidad`;b.onclick=()=>{dialogo.querySelector('[name=copias]').value=Math.min(5000,Number(datos.unidadesReferencia));actualizar();};dialogo.append(b);}
  let actual, dibujo, dibujoSerie;
  function actualizar() {
    try { actual = validarEtiqueta({...base,...Object.fromEntries(new FormData(dialogo.querySelector('form'))),cantidad:1});
      actual.copias=Number(dialogo.querySelector('[name=copias]').value);
      if(!Number.isInteger(actual.copias)||actual.copias<1||actual.copias>5000)throw new Error('Número de copias inválido.');
      dibujo = barrasDe(actual.sku);dibujoSerie=actual.serie ? barrasDe(actual.serie) : '';
      const contenedor = dialogo.querySelector('#etiquetaVista'); contenedor.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><style>${ESTILO_ETIQUETA}</style></head><body>${htmlEtiqueta(actual,dibujo,dibujoSerie)}</body></html>`;
      dialogo.querySelector('#errorEtiqueta').textContent = ''; return true;
    } catch(e) { dialogo.querySelector('#errorEtiqueta').textContent = e.message; return false; }
  }
  let filas=[];
  const elegirFila=()=>{try {base=etiquetaDesdeStock(filas[Number(dialogo.querySelector('[data-fila]').value)].datos);
    base.cantidad=1;
    for(const campo of ['cantidad','estado','serie','responsable','unidad','categoria','despacho']) dialogo.querySelector(`[name=${campo}]`).value=base[campo] ?? '';
    actualizar();}catch(e){dialogo.querySelector('#errorEtiqueta').textContent=e.message;}};
  dialogo.querySelector('[data-stock]').onchange=async ev=>{try {
    const archivo=ev.target.files[0];if(!archivo)return;
    filas=filasDeStock(XLSX.read(await archivo.arrayBuffer(),{type:'array'}));
    if(!filas.length)throw new Error('La hoja no contiene productos.');
    const selector=dialogo.querySelector('[data-fila]');selector.replaceChildren();
    filas.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${r.hoja} · fila ${r.fila} · ${r.datos[2]} · ${r.datos[3]}`;selector.append(o);});
    selector.hidden=false;elegirFila();
  }catch(e){dialogo.querySelector('#errorEtiqueta').textContent=e.message;}};
  dialogo.querySelector('[data-fila]').onchange=elegirFila;
  dialogo.addEventListener('input',actualizar); dialogo.addEventListener('change',actualizar);
  dialogo.querySelector('[data-cerrar]').onclick = () => dialogo.close();
  dialogo.addEventListener('close',()=>dialogo.remove());
  dialogo.querySelector('[data-zpl]').onclick = () => { if (!actualizar()) return;
    const url=URL.createObjectURL(new Blob([generarZpl(actual)],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='etiqueta-'+actual.sku.replace(/[^A-Za-z0-9_-]/g,'_')+'.zpl';a.click();setTimeout(()=>URL.revokeObjectURL(url),4000); };
  dialogo.querySelector('[data-imprimir]').onclick = () => { if (!actualizar()) return;
    const ventana = window.open('','_blank','width=850,height=500');
    if (!ventana) { dialogo.querySelector('#errorEtiqueta').textContent='Permite abrir la ventana de impresión.'; return; }
    ventana.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Etiqueta ${esc(actual.sku)}</title><style>${ESTILO_ETIQUETA}\n@media print{.etiqueta{position:relative;break-after:page}.etiqueta:last-child{break-after:auto}}</style></head><body>${Array(actual.copias).fill(htmlEtiqueta(actual,dibujo,dibujoSerie)).join('')}</body></html>`);
    ventana.document.close(); ventana.addEventListener('load',()=>{ventana.focus();ventana.print();},{once:true}); };
  dialogo.showModal(); actualizar();
  let pedirPuente=null,claveTrabajo=null;
  if(globalThis.location?.pathname?.startsWith('/app/')) import('./local.js?v=20261015-26').then(async({pedir})=>{
    pedirPuente=pedir;
    const p=await pedir('/preferencias',{base:'/api/operacion'});
    const lista=dialogo.querySelector('[data-estacion]');lista.replaceChildren();
    for(const estacion of p.impresoras){const o=document.createElement('option');o.value=estacion.id;o.textContent=estacion.nombre;lista.append(o);}
    dialogo.querySelector('[data-puente]').disabled=!p.impresoras.length;
    dialogo.querySelector('[name=copias]').max=p.maxCopias;
    if(p.impresoras.length)nota.textContent='Cada etiqueta indica 1 unidad. El puente enviará las copias elegidas a la Zebra de red.';
  }).catch(()=>{nota.textContent='No se pudo consultar la impresión en red. Puedes imprimir desde la PC.';});
  dialogo.querySelector('[data-puente]').onclick=async()=>{
    if(!actualizar()||!pedirPuente)return;
    const b=dialogo.querySelector('[data-puente]');b.disabled=true;
    try{
      claveTrabajo=claveTrabajo || (crypto.randomUUID ? crypto.randomUUID() : 'print-'+Date.now()+'-'+Math.random().toString(36).slice(2));
      const r=await pedirPuente('/trabajos',{base:'/api/impresion',cuerpo:{clave:claveTrabajo,
        estacion:dialogo.querySelector('[data-estacion]').value,recepcion:datos.recepcion,copias:actual.copias,etiqueta:actual}});
      dialogo.querySelector('#errorEtiqueta').textContent=`Solicitud ${r.id.slice(0,8)} · ${r.estado}. Una respuesta perdida no duplica la solicitud.`;
      let intentos=0;const ver=async()=>{if(!dialogo.isConnected||++intentos>60)return;
        try{const t=await pedirPuente('/trabajos/'+r.id,{base:'/api/impresion'});
          dialogo.querySelector('#errorEtiqueta').textContent=`${t.copias} copia(s) de 1 unidad · ${t.estado==='ENVIADA' ? 'Enviadas a la impresora' : t.estado}`;
          if(!['ENVIADA','REVISION'].includes(t.estado))setTimeout(ver,2000);
        }catch{setTimeout(ver,3000);}
      };ver();
    }catch(e){dialogo.querySelector('#errorEtiqueta').textContent=e.message;b.disabled=false;}
  };
}
