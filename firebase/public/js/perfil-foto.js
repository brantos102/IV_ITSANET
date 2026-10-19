import {pedir} from './local.js?v=20261019-54';
import {comprimir} from './imagen.js?v=20261019-54';
export function iniciarFotoPerfil(panel,usuario,aviso){
 const titulo=document.createElement('h2');titulo.textContent='Mi foto de perfil';
 const imagen=document.createElement('img');imagen.className='foto-perfil-grande';imagen.alt='Foto de perfil';imagen.src=usuario.photoURL||'';imagen.hidden=!usuario.photoURL;
 const texto=document.createElement('p');texto.textContent='Elige una fotografía. Se recorta a un cuadrado y se guarda en tu cuenta.';
 const archivo=document.createElement('input');archivo.type='file';archivo.accept='image/jpeg,image/png,image/webp';archivo.setAttribute('aria-label','Seleccionar foto de perfil');
 const boton=document.createElement('button');boton.className='b-primario';boton.textContent='Guardar mi fotografía';boton.disabled=true;
 const estado=document.createElement('p');estado.setAttribute('role','status');let seleccion=null,url='';
 archivo.onchange=()=>{if(url)URL.revokeObjectURL(url);seleccion=archivo.files[0]||null;boton.disabled=!seleccion;if(seleccion){url=URL.createObjectURL(seleccion);imagen.src=url;imagen.hidden=false;}estado.textContent='';};
 boton.onclick=async()=>{if(!seleccion||boton.disabled)return;boton.disabled=true;archivo.disabled=true;try{const foto=await comprimir(seleccion);const r=await pedir('/perfil/foto',{base:'/api/auth',metodo:'PUT',cuerpo:{base64:foto.base64}});imagen.src=r.photoURL;usuario.photoURL=r.photoURL;document.dispatchEvent(new CustomEvent('itsanet:perfil-foto',{detail:r.photoURL}));estado.textContent=r.mensaje;seleccion=null;archivo.value='';aviso(r.mensaje,'ok');}catch(e){estado.textContent=e.message;boton.disabled=false;}finally{archivo.disabled=false;}};
 panel.append(titulo,texto,imagen,archivo,boton,estado);panel.hidden=false;
}
