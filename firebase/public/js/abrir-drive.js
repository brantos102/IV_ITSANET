import {pedir} from './local.js?v=20261018-47';
import {revisarDrive} from './admin-entregas.js?v=20261018-47';

// Una recepción abierta puede tener fotos antes de generar su primera entrega.
// Sin enlace confirmado se muestra el diagnóstico y la vista previa local.
export async function abrirDriveRecepcion(codigo,aviso){
  const ventana=window.open('','_blank');
  if(ventana)ventana.opener=null;
  try{
    const datos=await pedir('/recepciones/'+encodeURIComponent(codigo)+'/drive',{base:'/api/operacion'});
    const url=(datos.carpetas||[]).find(u=>/^https:\/\/drive\.google\.com\//.test(u));
    if(url){
      if(ventana)ventana.location=url;
      else aviso('Permite abrir una ventana para revisar la carpeta Drive.','warn');
    }else{
      ventana?.close();
      await revisarDrive(codigo,aviso);
    }
  }catch(e){ventana?.close();throw e;}
}
