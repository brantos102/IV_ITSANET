import {pedir} from './local.js?v=20261020-60';
import {pintarEntregas} from './admin-entregas.js?v=20261020-60';

export async function abrirEntregas(aviso,recepcion='',{pendientes=false}={}) {
  const d=document.createElement('dialog');d.className='modal-operativa entregas-dialogo';
  d.innerHTML='<header><h2>Entregas de informes</h2><button data-cerrar class="b-sec">Cerrar</button></header><p class="guia-modal">Revisa el correo y sus documentos antes de enviar. Si ya lo enviaste desde Gmail u Outlook, registra el envío manual para resolver el pendiente.</p><div class="acciones"><label class="campo"><span>Mostrar</span><select data-filtro><option value="pendientes">Cerradas con envío pendiente</option><option value="todas">Todas las entregas</option><option value="archivadas">Incluir historial archivado</option></select></label><button data-actualizar class="b-sec">↻ Actualizar</button></div><div data-entregas role="status"></div>';
  d.querySelector('[data-filtro]').value=pendientes?'pendientes':'todas';
  document.body.append(d);d.showModal();let ocupado=false,anterior='';
  async function cargar(){if(ocupado||!d.open)return;ocupado=true;try{
    const filtro=d.querySelector('[data-filtro]').value;
    const datos=await pedir('/entregas'+(filtro==='archivadas'?'?archivadas=true':'')),filas=datos.filter(e=>(!recepcion||e.recepcion===recepcion)&&(filtro!=='pendientes'||e.esUltima&&e.recepcionEstado==='CERRADA'&&(['PENDIENTE','PROCESANDO','REVISION'].includes(e.estado)||e.correoManual?.estado==='PREPARADO')));
    const texto=JSON.stringify(filas);if(texto!==anterior){pintarEntregas(d.querySelector('[data-entregas]'),filas,{aviso,actualizar:async()=>{anterior='';await cargar();},operativo:true});anterior=texto;}
  }catch(e){aviso(e.message,'err');}finally{ocupado=false;}}
  d.querySelector('[data-actualizar]').onclick=()=>{anterior='';cargar();};d.querySelector('[data-cerrar]').onclick=()=>d.close();
  d.querySelector('[data-filtro]').onchange=()=>{anterior='';cargar();};
  const timer=setInterval(cargar,5000);d.addEventListener('close',()=>{clearInterval(timer);d.remove();},{once:true});await cargar();
}
