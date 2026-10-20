/** Ampliación dentro de la sesión; Drive privado no depende de una URL pública. */
import {cargarMiniatura,limpiarMiniaturas} from './miniaturas.js?v=20261020-60';
export function verImagen({url,nombre='',driveUrl=''}){
 if(!/^\/api\/app\/archivos\/[A-Za-z0-9_-]+$/.test(url||''))return;
 const d=document.createElement('dialog');d.className='modal-operativa visor-imagen';
 const barra=document.createElement('header');barra.className='acciones';const titulo=document.createElement('h2');titulo.textContent=nombre||'Fotografía';const cerrar=document.createElement('button');cerrar.className='b-sec';cerrar.textContent='Cerrar imagen';cerrar.onclick=()=>d.close();barra.append(titulo,cerrar);
 const imagen=document.createElement('img');cargarMiniatura(imagen,url,{inmediata:true});imagen.alt=nombre;imagen.style.cssText='width:100%;height:auto;max-height:72dvh;object-fit:contain';
 d.append(barra,imagen);const a=document.createElement('a');a.href=/^https:\/\/drive\.google\.com\//.test(driveUrl)?driveUrl:url;a.target='_blank';a.rel='noopener';a.className='b-sec';a.textContent='Abrir foto original';d.append(a);const estado=document.createElement('p');estado.setAttribute('role','status');imagen.onerror=()=>{imagen.hidden=true;estado.textContent='La vista previa no está disponible ahora. Abre la foto original con tu cuenta autorizada. No necesitas adjuntarla de nuevo por este aviso.';};d.append(estado);
 document.body.append(d);d.showModal();d.addEventListener('close',()=>{imagen.src='';limpiarMiniaturas(d);d.remove();},{once:true});
}
