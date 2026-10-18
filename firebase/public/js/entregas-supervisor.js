import {pedir} from './local.js?v=20261018-41';
import {pintarEntregas} from './admin-entregas.js?v=20261018-41';

export async function abrirEntregas(aviso,recepcion='') {
  const d=document.createElement('dialog');d.className='modal';
  d.innerHTML='<h3>Entregas de informes</h3><p>El estado ENTREGADA requiere confirmación de Google. Autoriza tu propia cuenta una sola vez en Mi cuenta y correo. Un envío pausado requiere revisar y confirmar los documentos finales.</p><button data-actualizar class="b-sec">Actualizar</button><button data-cerrar class="b-sec">Cerrar</button><div data-entregas role="status"></div>';
  document.body.append(d);d.showModal();let ocupado=false,anterior='';
  async function cargar(){if(ocupado||!d.open)return;ocupado=true;try{
    const datos=await pedir('/entregas'),filas=recepcion?datos.filter(e=>e.recepcion===recepcion):datos;
    const texto=JSON.stringify(filas);if(texto!==anterior){pintarEntregas(d.querySelector('[data-entregas]'),filas,{aviso,actualizar:async()=>{anterior='';await cargar();},operativo:true});anterior=texto;}
  }catch(e){aviso(e.message,'err');}finally{ocupado=false;}}
  d.querySelector('[data-actualizar]').onclick=()=>{anterior='';cargar();};d.querySelector('[data-cerrar]').onclick=()=>d.close();
  const timer=setInterval(cargar,5000);d.addEventListener('close',()=>{clearInterval(timer);d.remove();},{once:true});await cargar();
}
