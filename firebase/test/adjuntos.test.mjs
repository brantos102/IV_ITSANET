import {cargar,test,eq,ok,resumen} from './cargador.mjs';
const {documentosDelCorreo,agregarDocumentos,etiquetaFormato}=await cargar('documentos-correo.js');
await test('65: preparar el segundo formato conserva el primer nombre y ambos adjuntos elegidos',()=>{
 const anteriores=[{id:'cliente',nombre:'Cliente_VENTURA_final.xlsx'}],nuevos=[{id:'ejecutivo',nombre:'Validacion_R0002.xlsx'}];
 const disponibles=[{...anteriores[0],formato:'envio-ampliado'},{...nuevos[0],formato:'envio'}];
 const mezcla=agregarDocumentos(anteriores,nuevos,disponibles,{ejecutivo:'Ejecutivo_RB56223.xlsx'});
 eq(mezcla.adjuntos,[{id:'cliente',nombre:'Cliente_VENTURA_final.xlsx'},{id:'ejecutivo',nombre:'Ejecutivo_RB56223.xlsx'}]);eq(mezcla.retirados,[]);
 eq(anteriores,[{id:'cliente',nombre:'Cliente_VENTURA_final.xlsx'}]);eq(nuevos,[{id:'ejecutivo',nombre:'Validacion_R0002.xlsx'}]);
});
await test('65: un formato reutilizado no recupera el nombre original ni duplica el adjunto',()=>{
 const elegidos=[{id:'a',nombre:'Nombre_final.xlsx'}];eq(agregarDocumentos(elegidos,[{id:'a',nombre:'Original_R0001.xlsx'}],[{id:'a'}]).adjuntos,elegidos);
});
await test('65: los nombres desmarcados se conservan sin adjuntar el archivo',()=>{
 const v={archivos:[{id:'a',nombre:'Final_A.xlsx'}],documentosDisponibles:[{id:'a',nombre:'Original_A.xlsx',formato:'envio-ampliado',revision:1},{id:'b',nombre:'Original_B.xlsx',formato:'envio',revision:2}],nombresDocumentos:{b:'Solo_descarga.xlsx'}};
 const ds=documentosDelCorreo(v);eq(ds.map(a=>[a.id,a.nombre,a.seleccionado,a.formato]),[['a','Final_A.xlsx',true,'envio-ampliado'],['b','Solo_descarga.xlsx',false,'envio']]);eq(v.documentosDisponibles[0].nombre,'Original_A.xlsx');ok(etiquetaFormato(ds[0].formato).includes('organizado'));
});
await test('65: adjuntos de datos anteriores se identifican y no vuelven a seleccionarse silenciosamente',()=>{
 const viejo={id:'viejo',nombre:'Revisado_anterior.xlsx'},nuevo={id:'nuevo',nombre:'Actual.xlsx'};
 eq(documentosDelCorreo({archivos:[viejo],documentosDisponibles:[nuevo]})[1].vigente,false);
 const r=agregarDocumentos([viejo],[nuevo],[nuevo]);eq(r.retirados,[viejo]);eq(r.adjuntos,[nuevo]);
});
resumen();
