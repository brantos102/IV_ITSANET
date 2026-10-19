import {pedir} from './local.js?v=20261019-51';
import {pedirDatos} from './modal.js?v=20261019-51';
const api=(ruta,op={})=>pedir(ruta,{...op,base:'/api/operacion'});
export async function configurarClientes(select,boton,puedeEditar,alError=console.error) {
  async function cargar(elegido=select.value){
    const clientes=await api('/clientes-operacion');select.replaceChildren();
    const vacio=document.createElement('option');vacio.value='';vacio.textContent='Selecciona el cliente';select.append(vacio);
    for(const c of clientes.filter(c=>!c.oculto&&!c.unificarCon||c.id===elegido)){const o=document.createElement('option');o.value=c.id;o.textContent=c.nombre||c.id;select.append(o);}
    select.value=elegido;
  }
  await cargar();boton.hidden=!puedeEditar;
  const editar=async()=>{
    const clientes=await api('/clientes-operacion');
    const accion=await pedirDatos({titulo:'Gestionar clientes',campos:[{clave:'id',etiqueta:'Cliente que deseas corregir',tipo:'lista',valor:select.value||'',opciones:[{valor:'',titulo:'Agregar cliente nuevo'},...clientes.map(c=>({valor:c.id,titulo:(c.nombre||c.id)+' · '+c.id+(c.unificarCon?' → '+c.unificarCon:'')}))]}],aceptar:'Continuar'});
    if(!accion)return;const actual=clientes.find(c=>c.id===accion.id);
    const d=await pedirDatos({titulo:actual?'Corregir cliente · '+actual.id:'Nuevo cliente',texto:'Puedes corregir el nombre visible, ocultar duplicados o elegir el cliente que se usará en recepciones nuevas. Los registros anteriores y los identificadores de Depot se conservan. Revisa si VENTURA/VW identifica una marca antes de unificarlo.',campos:[
      ...(!actual?[{clave:'cliente',etiqueta:'Identificador del cliente',obligatorio:true}]:[{clave:'nombre',etiqueta:'Nombre que se muestra',valor:actual.nombre||actual.id,obligatorio:true},
      {clave:'unificarCon',etiqueta:'Usar otro cliente en recepciones nuevas',tipo:'lista',valor:actual.unificarCon||'',opciones:[{valor:'',titulo:'Conservar como cliente independiente'},...clientes.filter(c=>c.id!==actual.id&&!c.oculto&&!c.unificarCon).map(c=>({valor:c.id,titulo:c.nombre||c.id}))]},
      {clave:'oculto',etiqueta:'Ocultar en nuevas recepciones',tipo:'interruptor',valor:actual.oculto}]),
      {clave:'palletRequerido',etiqueta:'Exigir pallet',tipo:'interruptor',valor:actual?.reglas.palletRequerido??true},
      {clave:'posicionRequerida',etiqueta:'Exigir posición real',tipo:'interruptor',valor:actual?.reglas.posicionRequerida??false}],aceptar:'Guardar cliente'});
    if(!d)return;const id=actual?.id||d.cliente.trim().toUpperCase();
    if(actual)await api('/clientes-fichas',{metodo:'PUT',cuerpo:{id,nombre:d.nombre,unificarCon:d.unificarCon,oculto:d.oculto,version:actual.version}});
    await api('/clientes-operacion/'+encodeURIComponent(id),{metodo:'PUT',cuerpo:{palletRequerido:d.palletRequerido,posicionRequerida:d.posicionRequerida}});await cargar(d.unificarCon||id);
  };
  boton.onclick=()=>editar().catch(alError);
}
