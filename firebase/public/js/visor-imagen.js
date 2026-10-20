/** Ampliación dentro de la sesión; Drive privado no depende de una URL pública. */
export function verImagen({url,nombre='',driveUrl=''}){
 if(!/^\/api\/app\/archivos\/[A-Za-z0-9_-]+$/.test(url||''))return;
 const d=document.createElement('dialog');d.className='modal-operativa visor-imagen';
 const barra=document.createElement('header');barra.className='acciones';const titulo=document.createElement('h2');titulo.textContent=nombre||'Fotografía';const cerrar=document.createElement('button');cerrar.className='b-sec';cerrar.textContent='Cerrar imagen';cerrar.onclick=()=>d.close();barra.append(titulo,cerrar);
 const imagen=document.createElement('img');imagen.src=url+'?miniatura=1';imagen.alt=nombre;imagen.style.cssText='width:100%;height:auto;max-height:72dvh;object-fit:contain';
 d.append(barra,imagen);if(/^https:\/\/drive\.google\.com\//.test(driveUrl)){const a=document.createElement('a');a.href=driveUrl;a.target='_blank';a.rel='noopener';a.className='b-sec';a.textContent='Abrir original en Drive';d.append(a);}const estado=document.createElement('p');estado.setAttribute('role','status');imagen.onerror=()=>{imagen.hidden=true;estado.textContent=driveUrl?'La foto está guardada en Drive. La miniatura no está disponible en esta sesión; abre el original con tu cuenta autorizada de Google. No necesitas subirla otra vez.':'La foto está guardada; la vista previa no está disponible ahora. Actualiza la vista antes de reintentar.';};d.append(estado);
 document.body.append(d);d.showModal();d.addEventListener('close',()=>{imagen.src='';d.remove();},{once:true});
}
