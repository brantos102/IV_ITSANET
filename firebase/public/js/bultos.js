/** Etiquetas logísticas y fotografía desde el mismo video en vivo. */
export function interpretarEtiquetaMadre(valor) {
  const raw=String(valor || '').trim().replace(/^\][A-Za-z][0-9]/,'');
  if(!raw || raw.length>2048)throw new Error('Etiqueta vacía o demasiado larga. Escanea su código de bulto.');
  const clave=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z]/g,'');
  let codigo='',pallet='';
  const extraer=entradas=>{for(const [k,v] of entradas){if(typeof v!=='string' && typeof v!=='number')continue;
    if(['codigomadre','cajamadre','bulto','sscc','codigobulto','codigo'].includes(clave(k)) && !codigo)codigo=String(v);
    if(['pallet','paleta','posicion','ubicacion'].includes(clave(k)) && !pallet)pallet=String(v);
  }};
  try{const d=JSON.parse(raw);if(d && typeof d==='object' && !Array.isArray(d))extraer(Object.entries(d));}catch{}
  try{const u=new URL(raw);if(['http:','https:'].includes(u.protocol))extraer(u.searchParams.entries());}catch{}
  if(!codigo){const m=raw.match(/(?:CAJA[ _]MADRE|CODIGO[ _]BULTO|BULTO|SSCC|CODIGO)\s*[:=]\s*([A-Z0-9_.\/-]+)/i);if(m)codigo=m[1];}
  if(!pallet){const m=raw.match(/(?:PALLET|PALETA|UBICACION|POSICION)\s*[:=]\s*([A-Z0-9_.\/-]+)/i);if(m)pallet=m[1];}
  if(!codigo && /^\(00\)\d{18}$/.test(raw))codigo=raw.slice(4);
  if(!codigo && /^[A-Za-z0-9][A-Za-z0-9_.\/-]{0,79}$/.test(raw))codigo=raw;
  codigo=(codigo || pallet).trim();pallet=pallet.trim();
  if(!codigo || codigo.length>80 || pallet.length>80)throw new Error('El QR no identifica un bulto. Escanea el código madre o usa «Escribir código».');
  return {codigo,pallet,lecturaOriginal:raw}; // Un código madre no inventa una ubicación.
}

/** La etiqueta interna identifica una unidad exacta sin reemplazar la del proveedor. */
export function interpretarEtiquetaDeBulto(valor,unidadId){
  const interna=String(valor || '').trim().replace(/^\][A-Za-z][0-9]/,'').match(/^LB([0-9a-f]{32})$/i);
  if(!interna)return interpretarEtiquetaMadre(valor);
  if(interna[1].toLowerCase()!==String(unidadId).toLowerCase())throw new Error('Esta etiqueta corresponde a otro bulto. Abre ese bulto antes de registrar sus fotos.');
  return {interna:true};
}

export async function fotografiarVideo(video) {
  if(video.readyState<2 || !video.videoWidth)throw new Error('Espera a que la cámara muestre la imagen.');
  const canvas=document.createElement('canvas');
  const escala=Math.min(1,1600/Math.max(video.videoWidth,video.videoHeight));
  canvas.width=Math.round(video.videoWidth*escala);canvas.height=Math.round(video.videoHeight*escala);
  canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.85));
  canvas.width=0;canvas.height=0;
  if(!blob)throw new Error('No se pudo capturar la foto. Inténtalo de nuevo.');
  return new File([blob],'bulto-'+crypto.randomUUID()+'.jpg',{type:'image/jpeg'});
}
