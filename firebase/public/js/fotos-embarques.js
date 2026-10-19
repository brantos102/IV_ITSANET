import {pedir} from './local.js?v=20261019-54';
import {pedirDatos} from './modal.js?v=20261019-54';

export async function contextoFotos(recepcion,datos={}){
 const q=new URLSearchParams({sku:datos.sku||'',origen:datos.origen||'',unidadId:datos.unidadId||''});
 return pedir('/recepciones/'+encodeURIComponent(recepcion)+'/fotos/embarques?'+q,{base:'/api/operacion'});
}

/** La elección queda dentro del trabajo local recuperable de cada foto. */
export async function elegirEmbarqueFotos(recepcion,datos){
 if(Object.hasOwn(datos,'embarqueFoto'))return datos;
 const p=await contextoFotos(recepcion,datos);
 if(!p.embarques.length)return datos;
 if(p.sugerido)return {...datos,embarqueFoto:p.sugerido};
 const opciones=[...(p.permiteGeneral?[{valor:'',titulo:'Recepción completa · carpeta GENERALES'}]:[]),...p.candidatos.map(v=>({valor:v,titulo:v}))];
 const r=await pedirDatos({titulo:'¿A qué embarque pertenecen estas fotos?',texto:'Cada embarque tendrá su carpeta y conservará las clasificaciones Sobrante, Faltante y PNC. Esta elección se aplica a las fotos seleccionadas; carga otro lote para otro embarque.',campos:[{clave:'embarqueFoto',etiqueta:'Destino de las fotos',tipo:'lista',valor:p.permiteGeneral?'':p.candidatos[0],opciones}],aceptar:'Usar este destino'});
 if(!r)throw new Error('Carga cancelada. Las fotos seleccionadas se conservan para elegir su embarque.');
 return {...datos,embarqueFoto:r.embarqueFoto};
}
