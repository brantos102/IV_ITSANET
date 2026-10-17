import {pedir} from './local.js?v=20261017-37';
import {pedirDatos} from './modal.js?v=20261017-37';
const api=(ruta,op={})=>pedir(ruta,{...op,base:'/api/operacion'});
export async function configurarClientes(select,boton,puedeEditar,alError=console.error) {
  async function cargar(elegido=select.value){
    const clientes=await api('/clientes-operacion');select.replaceChildren();
    const vacio=document.createElement('option');vacio.value='';vacio.textContent='Selecciona el cliente';select.append(vacio);
    for(const c of clientes){const o=document.createElement('option');o.value=c.id;o.textContent=c.id;select.append(o);}
    select.value=elegido;
  }
  await cargar();boton.hidden=!puedeEditar;
  const editar=async()=>{
    const clientes=await api('/clientes-operacion'),actual=clientes.find(c=>c.id===select.value);
    const d=await pedirDatos({titulo:'Cliente y reglas operativas',texto:'Puedes agregar un cliente o ajustar sus requisitos de pallet y posición. Las conexiones y permisos generales los administra ADMIN.',campos:[
      {clave:'cliente',etiqueta:'Identificador del cliente',valor:select.value,obligatorio:true},
      {clave:'palletRequerido',etiqueta:'Exigir pallet',tipo:'interruptor',valor:actual?.reglas.palletRequerido??true},
      {clave:'posicionRequerida',etiqueta:'Exigir posición real',tipo:'interruptor',valor:actual?.reglas.posicionRequerida??false}],aceptar:'Guardar cliente'});
    if(!d)return;const id=d.cliente.trim().toUpperCase();
    await api('/clientes-operacion/'+encodeURIComponent(id),{metodo:'PUT',cuerpo:{palletRequerido:d.palletRequerido,posicionRequerida:d.posicionRequerida}});await cargar(id);
  };
  boton.onclick=()=>editar().catch(alError);
}
