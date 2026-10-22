/** Copia local del correo: miniaturas pequeñas; originales y MySQL intactos. */
import {leerMiniatura} from './miniaturas.js?v=20261022-63';
async function reducir(blob){
 const url=URL.createObjectURL(blob);try{const img=new Image();img.src=url;await img.decode();const escala=Math.min(1,320/img.naturalWidth,240/img.naturalHeight),c=document.createElement('canvas');c.width=Math.max(1,Math.round(img.naturalWidth*escala));c.height=Math.max(1,Math.round(img.naturalHeight*escala));const ctx=c.getContext('2d');ctx.fillStyle='#ffffff';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);return c.toDataURL('image/jpeg',.78);}finally{URL.revokeObjectURL(url);}
}
export async function prepararCorreoMiniaturas(html,alAvanzar=()=>{}){
 const d=new DOMParser().parseFromString(html,'text/html'),imagenes=[...d.querySelectorAll('img[data-archivo]')];
 const ids=[...new Set(imagenes.map(i=>i.dataset.archivo))];if(ids.length>12)throw Error('El correo admite hasta 12 miniaturas.');
 const archivos=[],faltantes=[],datos=new Map();let hechas=0;
 await Promise.all(ids.map(async(id,i)=>{try{const dato=await reducir(await leerMiniatura('/api/app/archivos/'+id));datos.set(id,dato);const b64=dato.split(',')[1],bin=atob(b64),bytes=Uint8Array.from(bin,c=>c.charCodeAt(0));archivos.push({nombre:'Evidencia_'+String(i+1).padStart(2,'0')+'_mini.jpg',bytes});}catch{faltantes.push(id);}finally{alAvanzar(++hechas,ids.length);}}));
 for(const img of imagenes){const dato=datos.get(img.dataset.archivo);if(dato){img.src=dato;img.removeAttribute('loading');if(img.nextElementSibling?.hasAttribute('data-copia-pendiente'))img.nextElementSibling.remove();}else{const enlace=d.createElement('a');enlace.href=new URL('/api/app/archivos/'+img.dataset.archivo,location.origin).href;enlace.textContent=(img.alt||'Foto')+' · abrir original desde ITSANET';img.replaceWith(enlace);}}
 archivos.sort((a,b)=>a.nombre.localeCompare(b.nombre));return {html:d.body.innerHTML,archivos,faltantes,total:ids.length};
}
// ZIP sin compresión: evita dependencias y conserva los JPEG ya comprimidos.
export function zipMiniaturas(archivos){
 const partes=[],indice=[];let offset=0;const encoder=new TextEncoder();
 const crc=bytes=>{let c=0xffffffff;for(const b of bytes){c^=b;for(let i=0;i<8;i++)c=c&1?(c>>>1)^0xedb88320:c>>>1;}return (c^0xffffffff)>>>0;};
 for(const a of archivos){const nombre=encoder.encode(a.nombre.replace(/[\\/]/g,'_')),bytes=a.bytes,check=crc(bytes),h=new Uint8Array(30),v=new DataView(h.buffer);v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint16(12,33,true);v.setUint32(14,check,true);v.setUint32(18,bytes.length,true);v.setUint32(22,bytes.length,true);v.setUint16(26,nombre.length,true);partes.push(h,nombre,bytes);
  const z=new Uint8Array(46),q=new DataView(z.buffer);q.setUint32(0,0x02014b50,true);q.setUint16(4,20,true);q.setUint16(6,20,true);q.setUint16(8,0x800,true);q.setUint16(14,33,true);q.setUint32(16,check,true);q.setUint32(20,bytes.length,true);q.setUint32(24,bytes.length,true);q.setUint16(28,nombre.length,true);q.setUint32(42,offset,true);indice.push(z,nombre);offset+=30+nombre.length+bytes.length;
 }
 const tam=indice.reduce((a,b)=>a+b.length,0),fin=new Uint8Array(22),v=new DataView(fin.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,archivos.length,true);v.setUint16(10,archivos.length,true);v.setUint32(12,tam,true);v.setUint32(16,offset,true);return new Blob([...partes,...indice,fin],{type:'application/zip'});
}
export function descargarMiniaturas(preparado,asunto){
 const texto='En Gmail: abre el correo original, pulsa Responder, pega el texto revisado y usa Insertar foto para incluir estos JPEG en el cuerpo. Revisa las imágenes, los destinatarios y adjunta los informes finales antes de enviar.\n';
 const archivos=[...preparado.archivos,{nombre:'Como_insertar_las_fotos.txt',bytes:new TextEncoder().encode(texto)},{nombre:'Correo_con_miniaturas.html',bytes:new TextEncoder().encode('<!doctype html><meta charset="utf-8"><title>Correo de recepción</title>'+preparado.html)}];
 const url=URL.createObjectURL(zipMiniaturas(archivos)),a=document.createElement('a');a.href=url;a.download='Miniaturas_'+String(asunto).replace(/[^A-Za-z0-9_-]/g,'_').slice(0,110)+'.zip';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
