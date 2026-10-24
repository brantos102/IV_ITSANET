/** Fotografía en la misma página: evita perder la ficha al abrir otra app. */
import {camaraDisponible,motivoNoDisponible,errorDeCamara} from './camara.js?v=20261024-69';
import {fotografiarVideo} from './bultos.js?v=20261024-69';
export function tomarFotoEnPagina({titulo='Fotografiar evidencia',alUsarNativa=null}={}){
 const d=document.createElement('dialog');d.className='modal-operativa captura-foto-dialogo';
 d.innerHTML='<header class="acciones"><h2></h2><button type="button" class="b-sec" data-cerrar>Cancelar foto</button></header><div class="captura-video"><video playsinline muted data-video></video></div><footer class="captura-controles"><p data-estado role="status">La foto se añade a la ficha; después guarda el conteo o las evidencias.</p><div class="acciones"><button type="button" class="b-primario" data-capturar disabled>Tomar y usar foto</button><button type="button" class="b-sec" data-activar>Activar cámara</button><button type="button" class="b-sec" data-nativa>Cámara del dispositivo</button></div></footer>';
 d.querySelector('h2').textContent=titulo;document.body.append(d);d.showModal();
 const $=s=>d.querySelector(s),video=$('[data-video]');let flujo=null,ocupado=false,solicitud=0,resolver;
 const resultado=new Promise(r=>resolver=r);$('[data-nativa]').hidden=!alUsarNativa;
 // Respaldo para navegadores Android sin dvh y barras que reducen el área útil.
 const ajustar=()=>{const alto=Math.floor(window.visualViewport?.height||window.innerHeight);d.style.height=Math.max(180,alto-16)+'px';d.style.maxHeight=Math.max(180,alto-16)+'px';};
 ajustar();window.addEventListener('resize',ajustar);window.visualViewport?.addEventListener('resize',ajustar);
 function apagar(){solicitud++;if(flujo)flujo.getTracks().forEach(p=>p.stop());flujo=null;video.srcObject=null;$('[data-capturar]').disabled=true;$('[data-activar]').hidden=false;}
 async function activar(){const id=++solicitud;let nuevo;$('[data-activar]').disabled=true;$('[data-estado]').textContent='Esperando permiso de cámara…';try{
  if(!camaraDisponible())throw new Error(motivoNoDisponible());
  nuevo=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false});
  if(!d.open||id!==solicitud||document.hidden){nuevo.getTracks().forEach(p=>p.stop());return;}
  flujo=nuevo;const pista=flujo.getVideoTracks()[0];try{if(pista.getCapabilities?.().focusMode?.includes('continuous'))await pista.applyConstraints({advanced:[{focusMode:'continuous'}]});}catch{}
  if(!d.open||id!==solicitud){nuevo.getTracks().forEach(p=>p.stop());return;}
  video.srcObject=flujo;await video.play();if(!d.open||id!==solicitud)return;
  $('[data-capturar]').disabled=false;$('[data-activar]').hidden=true;$('[data-estado]').textContent='Enfoca la evidencia y pulsa Tomar y usar foto. Después guarda la ficha.';
 }catch(e){if(id===solicitud&&d.open){apagar();$('[data-estado]').textContent=camaraDisponible()?errorDeCamara(e):motivoNoDisponible();}}finally{if(d.open)$('[data-activar]').disabled=false;}}
 $('[data-activar]').onclick=activar;
 $('[data-capturar]').onclick=async()=>{if(ocupado)return;ocupado=true;$('[data-capturar]').disabled=true;try{const f=await fotografiarVideo(video);resolver(f);d.close();}catch(e){$('[data-estado]').textContent=e.message;}finally{ocupado=false;if(d.open)$('[data-capturar]').disabled=false;}};
 $('[data-nativa]').onclick=()=>{if(ocupado)return;apagar();alUsarNativa?.();d.close();};
 $('[data-cerrar]').onclick=()=>{if(!ocupado)d.close();};d.addEventListener('cancel',e=>{if(ocupado)e.preventDefault();});
 const ocultar=()=>{if(document.hidden&&d.open){apagar();$('[data-estado]').textContent='Cámara pausada. La ficha se conserva; pulsa Activar cámara para continuar.';}};
 document.addEventListener('visibilitychange',ocultar);window.addEventListener('pagehide',apagar);
 d.addEventListener('close',()=>{apagar();document.removeEventListener('visibilitychange',ocultar);window.removeEventListener('pagehide',apagar);window.removeEventListener('resize',ajustar);window.visualViewport?.removeEventListener('resize',ajustar);resolver(null);d.remove();},{once:true});
 activar();return resultado;
}
