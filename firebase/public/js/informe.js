/**
 * Informe final de la recepción.
 *
 * Regla del cliente, textual: «si tenemos 22 filas debemos entregar 22 filas».
 * Por eso el archivo se construye desde la subcolección `lineas`, que conserva
 * el orden y el número de fila del archivo original, y NO desde el agregado por
 * SKU. El informe ampliado permite ordenar columnas; no añade ni quita filas.
 *
 * Lo que llegó sin estar en el packing list va en su propia hoja ADICIONALES, y
 * los conteos uno a uno en BITACORA, para que Depot reciba la tabla limpia y el
 * auditor tenga el detalle en el mismo archivo.
 */
import { collection, getDocs, query, orderBy } from '../vendor/firebase-sdk.js?v=20261022-64';
import { nombreInformeOperativo, carpetaDeRecepcion, carpetaDeMes } from './nombres.js?v=20261022-64';
import { db } from './auth.js?v=20261022-64';
import * as local from './local.js?v=20261022-64';
import {eventosActivos} from './conteo.js?v=20261022-64';
import {fechaDe} from './fechas.js?v=20261022-64';
import { aNumero, decodificarPallets, prefijoInforme } from './datos.js?v=20261022-64';
import {CAMPOS_AMPLIADOS,prepararFormatoInforme,columnasDeSalida,organizarHojaInforme} from './orden-informe.js?v=20261022-64';
import {repartirRegistrosEnFilas} from './detalle-registros.js?v=20261022-64';

const aFechaMs = v => fechaDe(v)?.getTime()||0;

export function metadatosDelGrupo(meta,tipo,id){
 const mapa=meta[tipo==='EMBARQUE'?'carpetasPorEmbarque':'carpetasPorOrigen'];
 return mapa===undefined?meta:{...meta,carpetas:mapa[id]?.carpetas||{},carpetasCategoria:mapa[id]?.carpetasCategoria||{}};
}
function enlaceDeFila(l,meta){const categoria=Number(l.cantidadPnc)>0?'PNC':l.diferencia<0?'FALTANTE':l.diferencia>0?'SOBRANTE':'VALIDACION';return (meta.carpetasCategoria?.[l.sku]?.[categoria]||meta.carpetas?.[l.sku]||[]).filter(u=>/^https:\/\/drive\.google\.com\//.test(u)).join(' | ');}

function evidenciasDeFila(l,meta){return {...l,evidencia:enlaceDeFila(l,meta),evidenciaSobrante:enlaceDeFila({...l,cantidadPnc:0},meta)};}

function adicionalesDelDocumento(datos,grupo,origen,origenes){
 return (datos.adicionales||[]).filter(a=>{
  if(datos.porGrupo&&!a.grupo)throw Error('Asigna el adicional '+a.sku+' a su embarque antes de preparar los documentos.');
  const destino=a.grupo||a.origen||(origenes.length===1?grupo:'');
  if(!destino)throw Error('Asigna el adicional '+a.sku+' a su embarque antes de preparar los documentos.');
  if(destino!==grupo)return false;
  if(!datos.porGrupo&&a.grupo&&a.origen&&a.grupo!==a.origen)throw Error('La asignación del adicional '+a.sku+' contradice el packing list de su conteo.');
  if(a.origen&&origenes.includes(a.origen))return a.origen===origen;
  if(a.origen)throw Error('El packing list del adicional '+a.sku+' no pertenece al embarque elegido. Revisa su asignación.');
  if(origenes.length!==1)throw Error('Indica el packing list del conteo adicional '+a.sku+' para no repetirlo en varios archivos.');
  return true;
 });
}

async function leerColeccion(recepcionId, nombre) {
  // El informe lee las cinco subcolecciones por aquí, así que es el único sitio
  // donde hay que elegir destino: contra el servidor de la red local o contra
  // Firestore. Lo que devuelve tiene la misma forma en los dos casos.
  if (local.modoLocal()) return local.leerColeccion(recepcionId, nombre);
  const snap = await getDocs(collection(db, 'recepciones', recepcionId, nombre));
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

/**
 * Reparte el conteo físico de un SKU entre sus líneas del packing list.
 *
 * Un mismo SKU puede venir en varias líneas (distinta factura o embarque). El
 * conteo es por SKU, así que hay que decidir dónde va cada unidad: se llenan las
 * líneas en orden hasta su cantidad declarada, y el excedente —si lo hay— se
 * acumula en la última línea de ese SKU, que es donde el sobrante queda visible.
 */
export function repartirPorLinea(lineas, totalPorSku) {
  const restante = { ...totalPorSku };
  const ultima = {};
  lineas.forEach((l) => { ultima[l.sku] = l.linea; });

  return lineas.map((l) => {
    const declarada = aNumero(l.cantidad, 0);
    const disponible = aNumero(restante[l.sku], 0);
    const fisica = ultima[l.sku] === l.linea
      ? disponible                              // la última se queda con todo lo que sobre
      : Math.max(Math.min(disponible, declarada), 0);
    restante[l.sku] = disponible - fisica;
    return { ...l, fisica, diferencia: fisica - declarada };
  });
}

export function repartirPorListas(lineas,totales,explicitos={}) {
  const filas=lineas.map(l=>({...l,fisica:0}));
  for(const [origen,conteos] of Object.entries(explicitos)) {
    const indices=filas.map((l,i)=>(l.origen||'PRINCIPAL')===origen?i:-1).filter(i=>i>=0);
    const partes=repartirPorLinea(indices.map(i=>filas[i]),conteos);
    partes.forEach((l,i)=>{filas[indices[i]].fisica=l.fisica;});
  }
  for(const [sku,total] of Object.entries(totales)) {
    const indices=filas.map((l,i)=>l.sku===sku?i:-1).filter(i=>i>=0);
    let restante=Number(total)-indices.reduce((n,i)=>n+filas[i].fisica,0);
    for(const i of indices) {const n=Math.min(Math.max(Number(filas[i].cantidad)-filas[i].fisica,0),Math.max(restante,0));filas[i].fisica+=n;restante-=n;}
    if(restante>0 && indices.length)filas[indices.at(-1)].fisica+=restante;
  }
  return filas.map(l=>({...l,diferencia:l.fisica-Number(l.cantidad||0)}));
}

// Las ubicaciones y observaciones de una lista nunca completan otra lista vacía.
export function completarRegistrosPorLista(filas,eventos) {
  if(filas.every(f=>Number.isFinite(f.fisica)))return repartirRegistrosEnFilas(filas,eventos);
  const origenes=new Map(),registros=new Map();
  for(const f of filas){if(!origenes.has(f.sku))origenes.set(f.sku,new Set());origenes.get(f.sku).add(f.origen||'PRINCIPAL');}
  const clave=(sku,origen)=>JSON.stringify([sku,origen]);
  for(const e of eventosActivos(eventos)){
    if(e.tipo&&!['CONTEO','NO_ENCONTRADO'].includes(e.tipo))continue;
    const k=clave(e.sku,e.origen||'');if(!registros.has(k))registros.set(k,[]);registros.get(k).push(e);
  }
  return filas.map(f=>{
    const multiple=origenes.get(f.sku).size>1;
    const activos=[...(registros.get(clave(f.sku,f.origen||'PRINCIPAL'))||[]),...(!multiple?(registros.get(clave(f.sku,''))||[]):[])];
    if(!activos.length&&!multiple)return f;
    const fisicos=activos.filter(e=>Number(e.cantidad)>0),pallets={};
    for(const e of fisicos)pallets[e.pallet||'']=(pallets[e.pallet||'']||0)+Number(e.cantidad);
    return {...f,observacion:[...new Set(activos.map(e=>e.observacion).filter(Boolean))].join(' | '),
      palletsSimple:[...new Set(fisicos.map(e=>e.pallet).filter(Boolean))].join('-'),
      pallets:Object.entries(pallets).map(([p,n])=>p+'('+n+')').join('-'),
      posicionReal:[...new Set(fisicos.map(e=>e.posicionReal).filter(Boolean))].join(' / ')};
  });
}

const etiquetaEstado = (declarada, fisica) => {
  if (fisica === declarada) return declarada === 0 ? 'SIN CANTIDAD' : 'OK';
  if (fisica === 0) return 'NO LLEGO';
  return fisica < declarada ? 'FALTANTE' : 'SOBRANTE';
};

/** Reúne todo lo necesario para el informe con 4 lecturas de colección. */
export async function reunirInforme(recepcionId, recepcion) {
  const [lineas, skus, adicionales, eventos] = await Promise.all([
    leerColeccion(recepcionId, 'lineas'),
    leerColeccion(recepcionId, 'skus'),
    leerColeccion(recepcionId, 'adicionales'),
    leerColeccion(recepcionId, 'eventos').then((eventos) => {
      return eventos.sort((a, b) => aFechaMs(a.creadoEn) - aFechaMs(b.creadoEn) || String(a.id).localeCompare(String(b.id)));
    }),
  ]);

  // Orden global estable: primero por el orden de carga, y dentro de cada lista
  // por su número de línea original.
  lineas.sort((a, b) => aNumero(a.orden, a.linea) - aNumero(b.orden, b.linea));

  const meta=local.modoLocal()?await local.pedir('/recepciones/'+encodeURIComponent(recepcionId)+'/informe-metadatos',{base:'/api/operacion'}):{};
  const porSku = {};
  const palletsPorSku = {};
  const palletsSimplePorSku = {};
  const pncPorSku = {},pncPendientePorSku={};
  for (const s of skus) {
    porSku[s.sku] = aNumero(s.contado, 0);
    const mapa = decodificarPallets(s.pallets);
    // Dos formas del mismo dato, y cada una va donde sirve:
    //   · la hoja original lleva SOLO nombres —«A1-B04»—, que es lo que admite
    //     el sistema al dar el alta;
    //   · la de detalle lleva las cantidades, que es lo que hace falta para
    //     entender cómo quedó repartido.
    palletsSimplePorSku[s.sku] = soloPallets(mapa);
    palletsPorSku[s.sku] = Object.entries(mapa)
      .sort((a, b) => b[1] - a[1])
      .map(([p, c]) => `${p}(${c})`)
      .join('-');
    pncPorSku[s.sku] = s.tienePnc === true;
    pncPendientePorSku[s.sku]=s.tienePnc&&s.cantidadPnc==null;
  }

  // Observaciones del operario, por SKU y sin repetir.
  const obsPorSku = {};
  // Dónde quedó físicamente. Va en su propia columna: el pallet es cómo se
  // movió, la posición real es dónde está, y para buscarlo después vale la
  // segunda.
  const posPorSku = {};
  /**
   * Desglose de dónde quedó cada unidad.
   *
   * De lo validado puede que solo unas unidades sueltas vayan a su posición
   * definitiva y el resto se quede en un pallet. Son destinos distintos de un
   * mismo SKU, y el que recibe el archivo necesita los dos para dar el alta.
   *
   * Va en UNA celda, no en filas nuevas: el archivo entrega las mismas filas
   * que entraron, vengan 22 o 300.
   */
  const destinoPorSku = {};
  for (const e of eventosActivos(eventos)) {
    if (e.tipo === 'ANULACION') continue;
    if (e.observacion) {
      const set = (obsPorSku[e.sku] = obsPorSku[e.sku] || new Set());
      set.add(e.observacion);
    }
    if (e.posicionReal) {
      const set = (posPorSku[e.sku] = posPorSku[e.sku] || new Set());
      set.add(e.posicionReal);
    }
    if (!aNumero(e.cantidad, 0)) continue;

    const clave = `${e.pallet || '—'}|${e.posicionReal || ''}`;
    const d = (destinoPorSku[e.sku] = destinoPorSku[e.sku] || {});
    d[clave] = (d[clave] || 0) + aNumero(e.cantidad, 0);
  }

  const destinoTexto = (sku) => Object.entries(destinoPorSku[sku] || {})
    .filter(([, n]) => n !== 0)
    .sort((a, b) => b[1] - a[1])
    .map(([clave, n]) => {
      const [pallet, posicion] = clave.split('|');
      return posicion ? `${pallet}→${posicion}(${n})` : `${pallet}(${n})`;
    })
    .join('-');

  /**
   * El reparto se hace POR LISTA, con lo que el operario imputó a cada una.
   *
   * Cuando eligió la lista al registrar, la atribución es un dato y no hay nada
   * que adivinar. Para lo registrado antes de que existiera esa pregunta —o en
   * recepciones de una sola lista— se cae al reparto por orden de líneas, que
   * es lo que había.
   */
  const contadoPorOrigen = {};
  for (const e of eventosActivos(eventos)) {
    if (e.tipo === 'ANULACION' || !e.origen) continue;
    const m = (contadoPorOrigen[e.origen] = contadoPorOrigen[e.origen] || {});
    m[e.sku] = (m[e.sku] || 0) + aNumero(e.cantidad, 0);
  }

  const listasDeLineas = [...new Set(lineas.map((l) => l.origen || 'PRINCIPAL'))];
  const repartido = repartirPorListas(lineas,porSku,contadoPorOrigen);

  const detalleBase = repartido.map((l) => ({
    ...l,
    pallets: palletsPorSku[l.sku] || '',
    palletsSimple: palletsSimplePorSku[l.sku] || '',
    estado: etiquetaEstado(aNumero(l.cantidad, 0), l.fisica),
    pnc: pncPorSku[l.sku] ? 'PNC' : '',
    calidadPorRevisar: !!pncPendientePorSku[l.sku],
    posicionReal: [...(posPorSku[l.sku] || [])].join(' / ').slice(0, 120),
    destino: destinoTexto(l.sku).slice(0, 180),
    observacion: [...(obsPorSku[l.sku] || [])].join(' | ').slice(0, 300),
  }));

  const detalle=completarIncidencias(completarRegistrosPorLista(detalleBase,eventos),eventos,meta);

  const adicionalesDetalle = adicionales.flatMap((a) => {
    const s = skus.find((x) => x.sku === a.sku);
    const base={
      sku: a.sku,
      descripcion: a.descripcion || s?.descripcion || '',
      fisica: aNumero(s?.contado, 0),
      pallets: palletsPorSku[a.sku] || '',
      motivo: a.motivo || '',
      detectadoPor: a.detectadoPorEmail || '',
      observacion: [...(obsPorSku[a.sku] || [])].join(' | ').slice(0, 300),
      origen:Object.keys(s?.porOrigen||{}).filter(o=>Object.values(s.porOrigen[o]||{}).some(n=>Number(n)>0)).length===1?Object.keys(s.porOrigen).find(o=>Object.values(s.porOrigen[o]||{}).some(n=>Number(n)>0)):'',
      grupo:meta.agrupacionCorreos?.configuracion?.asignaciones?.[a.sku]||'',
    };
    const porLista=new Map();
    for(const e of eventosActivos(eventos)){
      if(e.sku!==a.sku||!e.origen||e.tipo&&e.tipo!=='CONTEO'||!(Number(e.cantidad)>0))continue;
      if(!porLista.has(e.origen))porLista.set(e.origen,[]);porLista.get(e.origen).push(e);
    }
    if(!porLista.size)return [base];
    const partes=[...porLista].map(([origen,es])=>({...base,origen,fisica:es.reduce((n,e)=>n+Number(e.cantidad),0),
      pallets:[...new Set(es.map(e=>e.pallet).filter(Boolean))].join('-'),observacion:[...new Set(es.map(e=>e.observacion).filter(Boolean))].join(' | ')}));
    const restante=base.fisica-partes.reduce((n,a)=>n+a.fisica,0);
    if(restante < -1e-7)throw Error('Cambió el conteo del adicional '+a.sku+'. Actualiza antes de preparar el informe.');
    if(restante>1e-7)partes.push({...base,origen:'',fisica:restante});
    return partes;
  }).filter((a) => a.fisica !== 0 || a.motivo);
  for(const a of adicionalesDetalle){
    const g=meta.agrupacionCorreos?.grupos?.find(g=>g.id===a.grupo);
    a.embarque=g?.tipo==='EMBARQUE'?g.nombre:'';
    const propia=g?.tipo==='RECEPCION'?meta:metadatosDelGrupo(meta,a.embarque?'EMBARQUE':'PACKING_LIST',a.embarque||a.grupo||a.origen);
    a.evidencia=(propia.carpetas?.[a.sku]||[]).filter(u=>/^https:\/\/drive\.google\.com\//.test(u)).join(' | ');
  }

  /**
   * Una entrada por packing list, con SUS líneas.
   *
   * Consolidar varias listas en una validación ahorra recorrer el almacén dos
   * veces, pero el informe tiene que respetar cada lista como llegó: si una
   * trajo 22 filas y la otra 7, salen 22 y 7, nunca 29 mezcladas. Quien recibe
   * cada archivo espera el suyo.
   */
  const formatos = recepcion?.formatos || {};
  const origenes = [...new Set(detalle.map((l) => l.origen || 'PRINCIPAL'))];
  const porOrigen = origenes.map((origen) => ({
    origen,
    formato: (()=>{const f=formatos[origen] || formatos[origen.replace(/\./g, '~')] || null;
      const protegidas=Object.fromEntries(Object.entries(f?.columnas||{}).filter(([k])=>!Object.hasOwn(CAMPOS_AMPLIADOS,k)));
      return f?{...f,columnas:f.salida?{...protegidas,...f.salida}:{...f.columnas,...meta.columnas}}:null;})(),
    detalle: detalle.filter((l) => (l.origen || 'PRINCIPAL') === origen).map(l=>evidenciasDeFila(l,metadatosDelGrupo(meta,'PACKING_LIST',origen))),
  }));

  const agrupacion=meta.agrupacionCorreos;
  const porGrupo=agrupacion?.modo==='EMBARQUE'?agrupacion.grupos.map(g=>({id:g.id,nombre:g.nombre,
    porOrigen:g.packingLists.map(o=>{
      const lista=porOrigen.find(l=>l.origen===o),resultados=agrupacion.resultados.filter(x=>x.grupo===g.id&&x.origen===o);
      const filas=lista.detalle.filter(l=>String(l.embarque||agrupacion.configuracion.embarquesPorLinea[l.id||o+'-'+l.linea]||'').trim().toUpperCase()===g.nombre);
      const eventosGrupo=resultados.flatMap(x=>{
       const embs=new Set(lineas.filter(l=>l.sku===x.sku&&(l.origen||'PRINCIPAL')===o).map(l=>String(l.embarque||agrupacion.configuracion.embarquesPorLinea[l.id||o+'-'+l.linea]||'').trim().toUpperCase()).filter(Boolean));
       const origenesSku=new Set(lineas.filter(l=>l.sku===x.sku).map(l=>l.origen||'PRINCIPAL'));
       const propios=eventos.filter(e=>e.sku===x.sku&&(e.origen===o||!e.origen&&origenesSku.size===1));
       if(embs.size===1)return propios;
       return [{id:'reparto-'+o+'-'+x.sku,tipo:'CONTEO',sku:x.sku,origen:o,cantidad:x.contado,pallet:'',observacion:x.observacion,incidencias:x.incidencias,sinDetalleUbicacion:true}];
      });
      const base=repartirPorLinea(filas,Object.fromEntries(resultados.map(x=>[x.sku,x.contado]))).map(l=>({...l,formulas:{},estado:etiquetaEstado(Number(l.cantidad),l.fisica),pnc:'',calidadPorRevisar:false}));
      const propia=metadatosDelGrupo(meta,'EMBARQUE',g.nombre);
      return {...lista,detalle:completarIncidencias(completarRegistrosPorLista(base,eventosGrupo),eventosGrupo,propia).map(l=>evidenciasDeFila(l,propia))};
    })})):null;
  return {
    recepcion, detalle, porOrigen, contenedores:meta.contenedores||[], validacionDepot:meta.validacionDepot,
    adicionales: adicionalesDetalle, eventos, skus,porGrupo,modoAgrupacion:agrupacion?.modo||'PACKING_LIST',enlacesArchivos:meta.enlacesArchivos||{},
  };
}

/**
 * El vocabulario del cliente, no el mío.
 *
 * En sus archivos la columna «Validación» dice Ok, Faltante o Sobrante. Emitir
 * NO_ENCONTRADO o PENDIENTE obligaría a quien recibe el informe a traducir, y
 * a la primera lo haría mal.
 */
const VALIDACION = {
  OK: 'Ok',
  FALTANTE: 'Faltante',
  NO_ENCONTRADO: 'Faltante',
  SOBRANTE: 'Sobrante',
  PENDIENTE: '',
};

/**
 * Solo los nombres de pallet, separados por guion medio: `A1-A2-B04.1`.
 *
 * Sin cantidades ni paréntesis: el sistema no admite ese formato al dar el
 * alta, así que escribirlo ahí obliga a limpiarlo a mano fila por fila. El
 * desglose con cantidades existe, pero vive en la hoja de detalle.
 */
export function soloPallets(mapa) {
  return Object.entries(mapa || {})
    .filter(([, n]) => n !== 0)
    .sort((a, b) => b[1] - a[1])
    .map(([p]) => p)
    .join('-');
}

/**
 * Devuelve el packing list como llegó, con las columnas de validación llenas.
 *
 * Mismas columnas, mismas posiciones, mismos encabezados. El archivo que se
 * envía a validar ya trae `Cantidad Física`, `Validación`, `DESFACE`, `PALLET`
 * y `OBSERVACION` en blanco; el informe las rellena **en su sitio**. Devolver
 * otro formato obliga a rehacer el archivo a mano antes de subirlo.
 */
function hojaOriginal(filas, formato, ampliado=false, validacionDepot=null) {
  const orden=columnasDeSalida(formato,{ampliado});
  formato=prepararFormatoInforme(formato,ampliado);
  const enc = (formato?.encabezados || []).slice();
  const col = {...formato?.columnas};
  if(col.posicion===undefined){const j=enc.findIndex(v=>/^(?:POSICION(?:FINAL(?:SUGERIDA)?|REAL(?:ASIGNADA)?)?|UBICACIONFINAL(?:SUGERIDA)?)$/.test(String(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z]/g,'')));if(j>=0)col.posicion=j;}
  const ancho = enc.length;
  const salida=new Set(['marca','cliente','fisica','validacion','desface','pallet','posicion','codigoBarra','cantidadIncidencia','incidencia','observacion','evidencia','depot']);
  for(const [rol,i] of Object.entries(col))if(salida.has(rol)&&(!Number.isInteger(i)||i<0||i>=ancho))throw Error('La columna de '+rol+' no existe en este packing list. Revisa Columnas del informe.');

  const prefijo=prefijoInforme(formato).map(f=>f.celdas||f);
  const matriz = [...prefijo,enc];
  for (const l of filas) {
    const fila = (l.cruda || []).slice(0, ancho);
    while (fila.length < ancho) fila.push('');

    const poner = (rol, valor) => {
      if (col[rol] !== undefined && col[rol] < ancho) fila[col[rol]] = valor;
    };
    poner('fisica', l.fisica);
    poner('validacion', VALIDACION[l.estado] ?? l.estado ?? '');
    poner('desface', l.diferencia);
    if(l.depot!==undefined)poner('depot',l.depot);
    poner('pallet', l.palletsSimple || '');
    poner('observacion', l.observacion || '');
    if(l.evidencia!==undefined)poner('evidencia',l.evidencia||'');
    for(const rol of ['marca','cliente','posicion','codigoBarra','cantidadIncidencia','incidencia','evidencia']){
      const valor=rol==='posicion'?l.posicionReal:l[rol];
      if(valor!==undefined&&valor!==null&&(valor!==''||rol==='posicion')&&(!['marca','cliente'].includes(rol)||!fila[col[rol]]))poner(rol,valor);
    }

    matriz.push(fila);
  }

  const hoja = XLSX.utils.aoa_to_sheet(matriz);
  filas.forEach((l,i)=>{const r=i+1+prefijo.length,j=col.evidencia,url=String(l.evidencia||'').split(' | ')[0];if(Number.isInteger(j)&&/^https:\/\/drive\.google\.com\//.test(url)){const cell=hoja[XLSX.utils.encode_cell({r,c:j})];if(cell)cell.l={Target:url,Tooltip:'Carpeta del SKU '+l.sku};}
    for(const [c,formula] of Object.entries(l.formulas||{}))if(!Object.entries(col).some(([rol,j])=>salida.has(rol)&&j===Number(c))&&!/[!\[\]]/.test(formula)){
      const celda=hoja[XLSX.utils.encode_cell({r,c:Number(c)})];
      const delta=r+1-Number(l.filaOriginal||r+1);
      if(celda)celda.f=String(formula).replace(/("(?:[^"]|"")*")|(?<![A-Za-z0-9_])(\$?[A-Z]{1,3})(\$?)([1-9][0-9]*)/g,(m,txt,columna,fija,fila)=>txt||columna+fija+(fija?fila:Math.max(1,Number(fila)+delta)));
    }
  });
  hoja['!cols'] = enc.map((c) => ({ wch: Math.min(Math.max(String(c).length + 3, 10), 40) }));
  if (ancho) {
    hoja['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: prefijo.length, c: 0 },
      e: { r: filas.length+prefijo.length, c: ancho - 1 } }) };
  }
  return ampliado?organizarHojaInforme(hoja,orden):hoja;
}

/** Excel limita el nombre de hoja a 31 caracteres y prohíbe : \ / ? * [ ] */
export function nombreDeHoja(origen) {
  return String(origen || 'LISTA').replace(/[:\\/?*[\]]/g, '-').slice(0, 31);
}

/**
 * Hoja de detalle: lo que la validación añade y el formato original no tiene.
 *
 * Va aparte justamente para que la hoja original siga siendo el archivo que
 * esperan. Aquí caben la posición real, el desglose con cantidades y de qué
 * lista salió cada unidad.
 *
 * Nunca añade ni quita filas. Es la regla que más fácil se rompe sin darse
 * cuenta, y por eso vive en un solo sitio.
 */
function hojaValidada(filas) {
  const datos = filas.map((l) => ({
    'ITEM': l.sku,
    'DESCRIPCION': l.descripcion || '',
    'REFERENCIA PEDIDO': l.referencia || '',
    'FACTURA': l.factura || '',
    'EMBARQUE': l.embarque || '',
    'CANTIDAD': aNumero(l.cantidad, 0),
    'CANTIDAD FISICA': l.fisica,
    'DIFERENCIA': l.diferencia,
    'VALIDACION': l.estado,
    'PALLET': l.pallets,
    'POSICION REAL ASIGNADA': l.posicionReal,
    'DESGLOSE PALLET → POSICION': l.destino,
    'PACKING LIST': l.origen || '',
    'ESTADO MERCADERIA': l.pnc || 'BUENO',
    'UNIDADES CONFORMES':l.cantidadConforme??'', 'UNIDADES PNC':l.cantidadPnc??'',
    'TIPO DE INCIDENCIA':l.incidencia||'', 'CANT CON INCIDENCIA':l.cantidadIncidencia??'',
    'CODIGO DE BARRAS':l.codigoBarra||'', 'CARPETA DRIVE':l.evidencia||'',
    'OBSERVACION': l.observacion,
  }));

  const hoja = XLSX.utils.json_to_sheet(datos);
  hoja['!cols'] = [{ wch: 18 }, { wch: 40 }, { wch: 16 }, { wch: 14 }, { wch: 14 },
    { wch: 10 }, { wch: 14 }, { wch: 11 }, { wch: 13 }, { wch: 22 }, { wch: 24 },
    { wch: 30 }, { wch: 14 }, { wch: 17 }, { wch: 38 }];
  hoja['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 },
    e: { r: datos.length, c: 14 } }) };
  return hoja;
}

/** Construye el .xlsx y lo devuelve en base64, listo para el correo. */
/**
 * Dos versiones del mismo informe, y la diferencia importa.
 *
 * `envio`: packing list y adicionales en hoja separada, con el formato que espera quien lo
 * recibe. Es lo que se manda por correo y lo que se sube al sistema. Adjuntar
 * cuatro hojas más obliga a quien da el alta a buscar la buena, y a la primera
 * se equivoca.
 *
 * `auditable`: detalle, adicionales y bitácora con fecha de Ecuador.
 * Es para analizar, transferir datos y responder a una reclamación.
 */
export function construirLibro({ recepcion, detalle, porOrigen, adicionales,
                                 eventos, validacionDepot, contenedores=[], enlacesArchivos={} }, opciones = {}) {
  if (typeof XLSX === 'undefined') {
    throw new Error('No se cargó la librería de Excel. Recarga la página.');
  }
  const soloEnvio = ['envio','envio-ampliado'].includes(opciones.version);
  const libro = XLSX.utils.book_new();
  const ubicaciones=[];
  libro.Props={Company:'ITSANET',Author:recepcion.informe?.usuario||'ITSANET',Title:recepcion.codigo,Subject:(recepcion.informe?'Informe '+recepcion.informe.numero+' · '+recepcion.informe.id:'Validación de recepción')+' · Listas: '+(porOrigen||[]).map(l=>l.origen).join(', ')};
  if(opciones.embarque)libro.Props.Subject+=' · Embarque: '+opciones.embarque;
  if(opciones.embarque)libro.Props.Comments=(libro.Props.Comments||'')+' Revisión por embarque: conserva valores de las filas de origen; las fórmulas se presentan como valores para evitar referencias a filas de otros embarques.';

  // --- Una hoja por packing list, con SU formato y SUS filas --- //
  const listas = (porOrigen && porOrigen.length)
    ? porOrigen
    : [{ origen: 'VALIDADA', detalle, formato: null }];

  for (const lista of listas) {
    const base = soloEnvio&&lista.formato?.hoja?nombreDeHoja(lista.formato.hoja):listas.length === 1 ? 'VALIDADA' : nombreDeHoja(recepcion.nombresListas?.[lista.origen]||lista.origen);

    // Primero el archivo tal como llegó, con sus columnas rellenas. Si no se
    // guardó el formato original —recepciones anteriores a esto— se cae a las
    // columnas propias, que es lo que había.
    const hoja=lista.formato?.encabezados?.length
        ? hojaOriginal(lista.detalle, lista.formato,opciones.version==='envio-ampliado',validacionDepot)
        : hojaValidada(lista.detalle);
    if(base.toUpperCase()==='REV'){
      const matriz=XLSX.utils.sheet_to_json(hoja,{header:1,defval:''}),cabecera=matriz.findIndex(f=>f.some(v=>/^(?:ITEM|SKU|CODIGO)$/i.test(String(v).trim()))),indice=cabecera>=0?cabecera:0;
      if(!matriz[indice]?.some(v=>/POSICION|UBICACION/i.test(String(v)))){
        const col=XLSX.utils.decode_range(hoja['!ref']||'A1').e.c+1;
        XLSX.utils.sheet_add_aoa(hoja,[['POSICION FINAL SUGERIDA'],...lista.detalle.map(l=>[l.posicionReal||''])],{origin:{r:indice,c:col}});
        hoja['!cols']=[...(hoja['!cols']||[]),{wch:32}];
      }
    }
    XLSX.utils.book_append_sheet(libro,hoja,base);
    lista.detalle.forEach((l,i)=>{for(const p of l.registrosAsignados||[]){ubicaciones.push({
     'HOJA':base,'FILA DEL INFORME':prefijoInforme(lista.formato||{}).length+i+2,'FILA ORIGINAL':l.filaOriginal||'', 'LINEA':l.linea||i+1,'PACKING LIST':l.origen||lista.origen,'EMBARQUE':l.embarque||opciones.embarque||'',
     'ITEM':l.sku,'DESCRIPCION':l.descripcion||'','CANTIDAD ASIGNADA':p.cantidad,'CONDICION':p.estado,'INCIDENCIA':p.tipo||'',
     'PALLET':p.pallet||'Sin pallet registrado','POSICION FINAL SUGERIDA':p.posicionReal||'Sin posición registrada',
     'OBSERVACION DEL CONTEO':p.observacion||'','ID CONTEO':p.eventoId||'',
     'ASIGNACION A FILA':p.sinDetalleUbicacion?'Por revisar':'Por orden de filas del packing list',
     'EVIDENCIAS':l.evidencia||''});}});

    // Y aparte, lo que la validación añade.
    if (!soloEnvio && lista.formato?.encabezados?.length) {
      XLSX.utils.book_append_sheet(
        libro, hojaValidada(lista.detalle), nombreDeHoja(base + ' DET'));
    }
  }

  if(ubicaciones.length){
   const hoja=XLSX.utils.json_to_sheet(ubicaciones),cabecera=Object.keys(ubicaciones[0]);hoja['!cols']=cabecera.map(k=>({wch:/OBSERVACION|ASIGNACION|EVIDENCIAS/.test(k)?55:/DESCRIPCION|POSICION|ID CONTEO/.test(k)?34:22}));hoja['!autofilter']={ref:hoja['!ref']};
   ubicaciones.forEach((p,i)=>{const fila=hoja[XLSX.utils.encode_cell({r:i+1,c:cabecera.indexOf('FILA DEL INFORME')})];if(fila)fila.l={Target:"#'"+p.HOJA.replace(/'/g,"''")+"'!A"+p['FILA DEL INFORME'],Tooltip:'Ir a la fila del packing list validado'};const url=String(p.EVIDENCIAS||'').split(' | ')[0],celda=hoja[XLSX.utils.encode_cell({r:i+1,c:cabecera.indexOf('EVIDENCIAS')})];if(celda&&/^https:\/\/drive\.google\.com\//.test(url))celda.l={Target:url,Tooltip:'Evidencias confirmadas del SKU '+p.ITEM};});
   let nombre='UBICACIONES';while(libro.SheetNames.includes(nombre))nombre+=' 2';XLSX.utils.book_append_sheet(libro,hoja,nombre);
   libro.Props.Comments=(libro.Props.Comments||'')+' UBICACIONES muestra unidades por conteo y condición. La asignación a filas repetidas es secuencial dentro de su packing list; no acredita una factura física que no se registró.';
  }

  // Un sobrante declarado ya está en el packing validado: nunca duplicarlo como adicional.
  const declarados=new Set((detalle||[]).map(l=>l.sku));
  const extras=(adicionales||[]).filter(a=>!declarados.has(a.sku)).map(a=>({...a,tipo:'ADICIONAL NO DECLARADO'}));
  if(!soloEnvio||extras.length){
  // --- Adicionales, aparte para no alterar el conteo de filas --- //
  const h2 = XLSX.utils.json_to_sheet(extras.length ? extras.map((a) => ({
    'TIPO':a.tipo,
    'ITEM': a.sku,
    'DESCRIPCION': a.descripcion,
    'CANTIDAD FISICA': a.fisica,
    'PALLET': a.pallets,
    'MOTIVO': a.motivo,
    'OBSERVACION': a.observacion,
    'DETECTADO POR': a.detectadoPor,
    'PACKING LIST':a.origen||'', 'EMBARQUE':a.embarque||opciones.embarque||'', 'EVIDENCIAS':a.evidencia||'Sin enlace Drive confirmado',
  })) : [{ 'ITEM': '', 'DESCRIPCION': 'Sin adicionales en esta recepción.' }]);
  h2['!cols'] = [28,18,40,18,22,60,48,28,28,24,65].map(wch=>({wch}));
  h2['!autofilter']={ref:h2['!ref']};
  const cabExtras=XLSX.utils.sheet_to_json(h2,{header:1})[0]||[],colLink=cabExtras.indexOf('EVIDENCIAS');
  extras.forEach((a,i)=>{const url=String(a.evidencia||'').split(' | ')[0],cell=h2[XLSX.utils.encode_cell({r:i+1,c:colLink})];if(cell&&/^https:\/\/drive\.google\.com\//.test(url))cell.l={Target:url,Tooltip:'Evidencias de '+a.sku};});
  let nombreAdicionales='ADICIONALES';while(libro.SheetNames.includes(nombreAdicionales))nombreAdicionales+=' 2';
  XLSX.utils.book_append_sheet(libro, h2, nombreAdicionales);

  }

  const embarquesDocumento=new Set(detalle.map(l=>l.embarque).filter(Boolean));
  const distribucion=contenedores.filter(c=>opciones.embarque?c.embarques.includes(opciones.embarque):c.embarques.some(b=>embarquesDocumento.has(b))||!embarquesDocumento.size&&!c.embarques.length);
  if(distribucion.length){const hoja=XLSX.utils.json_to_sheet(distribucion.map(c=>({'IDENTIFICADOR':c.id,'CONTENEDOR':c.numero,'EMBARQUES':c.embarques.join(', '),'DESDE EL BULTO':c.desde,'HASTA EL BULTO':c.hasta,'TOTAL BULTOS':c.total??'','POSICION FINAL':c.posicion})));hoja['!cols']=[15,22,30,20,20,18,40].map(wch=>({wch}));let nombre='CONTENEDORES';while(libro.SheetNames.includes(nombre))nombre+=' 2';XLSX.utils.book_append_sheet(libro,hoja,nombre);}
  if (soloEnvio) {
    return {
      base64: XLSX.write(libro, { bookType: 'xlsx', type: 'base64', compression:true }),
      nombre: nombreArchivo(recepcion, 'validacion'),
      filas: detalle.length,
      version: 'envio',
    };
  }

  const resumenListas=listas.map(l=>({'PACKING LIST':recepcion.nombresListas?.[l.origen]||l.origen,'EMBARQUES':[...new Set(l.detalle.map(f=>f.embarque).filter(Boolean))].join(', '),'REFERENCIAS / FILAS':l.detalle.length,'DECLARADO':l.detalle.reduce((n,f)=>n+Number(f.cantidad||0),0),'CONTADO':l.detalle.reduce((n,f)=>n+Number(f.fisica||0),0),'VALIDACION':l.detalle.some(f=>Number(f.diferencia||0)!==0)?'Con diferencias':'Sin diferencias'}));
  const resumen=XLSX.utils.json_to_sheet(resumenListas);resumen['!cols']=[35,35,22,18,18,24].map(wch=>({wch}));let tituloResumen='RESUMEN';while(libro.SheetNames.includes(tituloResumen))tituloResumen+=' 2';XLSX.utils.book_append_sheet(libro,resumen,tituloResumen);

  // --- Hoja 3: la bitácora, el respaldo de cada unidad contada --- //
  const h3 = XLSX.utils.json_to_sheet(eventos.map((e) => ({
    'FECHA': fechaDe(e.creadoEn)?.toLocaleString('es-EC',{timeZone:'America/Guayaquil'}) || 'Fecha no registrada',
    'ITEM': e.sku,
    'CODIGO ESCANEADO': e.codigoEscaneado || e.sku,
    'CANTIDAD': aNumero(e.cantidad, 0),
    'PALLET': e.pallet || '',
    'POSICION REAL': e.posicionReal || '',
    'PACKING LIST': e.origen || '',
    'ESTADO': e.estadoFisico || '',
    'TIPO': e.tipo || 'CONTEO',
    'OPERARIO': e.operadorNombre || e.operadorEmail || e.usuario || '',
    'OBSERVACION': e.observacion || '',
    'FOTOS': (e.fotos || []).map(u=>/^https:\/\//.test(u)?u:enlacesArchivos[String(u).split('/api/app/archivos/').at(-1)?.split('?')[0]]||'Copia Drive pendiente').join(' '),
  })));
  h3['!cols'] = [{ wch: 20 }, { wch: 18 }, { wch: 18 }, { wch: 10 }, { wch: 12 },
    { wch: 16 }, { wch: 14 }, { wch: 9 }, { wch: 11 }, { wch: 28 }, { wch: 34 },
    { wch: 40 }];
  XLSX.utils.book_append_sheet(libro, h3, 'BITACORA');

  return {
    base64: XLSX.write(libro, { bookType: 'xlsx', type: 'base64', compression:true }),
    nombre: nombreArchivo(recepcion, 'auditable'),
    filas: detalle.length,
    version: 'auditable',
  };
}

const nombreArchivo = (recepcion, sufijo) =>
  nombreVersionado(nombreInformeOperativo(recepcion, { auditable: sufijo === 'auditable' }),recepcion);
function nombreVersionado(nombre,rec,lista=''){
  if(!rec.informe)return nombre;
  const final=lista+rec.informe.sufijo+'.xlsx';
  return nombre.slice(0,190-final.length)+final;
}

/**
 * Un archivo POR PACKING LIST cuando la recepción consolida varios.
 *
 * Consolidar ahorra recorrer el almacén dos veces, pero cada lista vuelve a su
 * destinatario tal como llegó: si entraron 22 filas y 7, salen un archivo de 22
 * y otro de 7. Mandar un solo libro con dos hojas obliga a quien lo recibe a
 * separarlas a mano, y a la primera manda la hoja equivocada.
 *
 * La versión auditable no se parte: es para analizar la validación entera, y
 * repartir la bitácora entre dos archivos solo la haría más difícil de leer.
 */
/** Misma hoja que recibe el generador XLSX; sin reservar ni archivar un informe. */
export function previsualizarLista(lista,columnas,{ampliado=false,offset=0,limite=12}={}) {
  const formato={...lista.formato,columnas};
  if(!formato.encabezados?.length)throw Error('Esta lista no conserva encabezados. Carga el packing list con su formato antes de asignar columnas.');
  let filas=lista.detalle||[],ejemplo=!filas.length;
  if(ejemplo){
    const f={sku:'EJEMPLO001',descripcion:'Producto de ejemplo',cantidad:10,fisica:8,estado:'FALTANTE',diferencia:-2,
      palletsSimple:'P01',posicionReal:'A-01',codigoBarra:'000123456789',cantidadIncidencia:2,
      incidencia:'FALTANTE (2)',observacion:'Ejemplo: faltan 2 unidades',evidencia:'',depot:'ok',marca:'MARCA',cliente:'CLIENTE'};
    f.cruda=Array(formato.encabezados.length).fill('');
    for(const [rol,i] of Object.entries(formato.columnas||{}))if(['sku','descripcion','cantidad'].includes(rol))f.cruda[i]=f[rol];
    filas=[f];
  }
  const hoja=hojaOriginal(filas,formato,ampliado,lista.validacionDepot),filaCabecera=prefijoInforme(formato).length;
  const ancho=XLSX.utils.decode_range(hoja['!ref']).e.c+1;
  const celda=(r,c)=>hoja[XLSX.utils.encode_cell({r,c})]||{};
  return {ejemplo,total:filas.length,columnas:columnasDeSalida(formato,{ampliado}),encabezados:Array.from({length:ancho},(_,c)=>String(celda(filaCabecera,c).v??'')),
    filas:filas.slice(offset,offset+limite).map((_,i)=>({numero:offset+i+filaCabecera+2,
      celdas:Array.from({length:ancho},(_,c)=>{const v=celda(offset+i+filaCabecera+1,c);return {
        texto:String(v.w??v.v??(v.f?'='+v.f:'')),formula:v.f||'',url:v.l?.Target||'',comentario:(v.c||[]).map(c=>c.t).join('\n')};})}))};
}

export function construirLibros(datos, opciones = {}) {
  if(datos.modoAgrupacion==='RECEPCION'&&['envio','envio-ampliado'].includes(opciones.version)){const l=construirLibro(datos,opciones);return [{...l,origen:'RECEPCION',grupo:'RECEPCION'}];}
  if(datos.porGrupo&&['envio','envio-ampliado'].includes(opciones.version))return datos.porGrupo.flatMap(g=>g.porOrigen.map((lista,indice)=>{
    const adicionales=adicionalesDelDocumento(datos,g.id,lista.origen,g.porOrigen.map(l=>l.origen));
    const libro=construirLibro({...datos,porOrigen:[lista],detalle:lista.detalle,adicionales},{...opciones,embarque:g.nombre});
    return {...libro,origen:lista.origen,grupo:g.id,nombre:nombreVersionado(nombreInformeOperativo(datos.recepcion,{origen:g.porOrigen.length>1?lista.origen:'',embarque:g.nombre}),datos.recepcion,g.porOrigen.length>1?'_PL'+String(indice+1).padStart(2,'0'):'')};
  }));
  const listas = datos.porOrigen || [];
  if (!['envio','envio-ampliado'].includes(opciones.version) || listas.length <= 1) {
    return [{...construirLibro(datos, opciones),origen:listas.length===1?listas[0].origen:undefined}];
  }

  return listas.map((lista,indice) => {
    const libro = construirLibro(
      { ...datos, porOrigen: [lista], detalle: lista.detalle,adicionales:adicionalesDelDocumento(datos,lista.origen,lista.origen,listas.map(l=>l.origen)) }, opciones);
    return {
      ...libro,
      origen: lista.origen,
      nombre: nombreVersionado(nombreInformeOperativo(datos.recepcion, { origen: lista.origen }),datos.recepcion,'_L'+String(indice+1).padStart(2,'0')),
    };
  });
}

/** Dónde va esto en Drive. Lo decide aquí, que es donde está probado. */
export const destinoEnDrive = (recepcion) => ({
  carpetaMes: carpetaDeMes(recepcion),
  carpetaRecepcion: carpetaDeRecepcion(recepcion),
});

/** Descarga local del mismo archivo, por si el correo falla o no se quiere enviar. */
export function descargarLibro(libro) {
  const bytes = Uint8Array.from(atob(libro.base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes],
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = /\.xlsx$/i.test(libro.nombre)?libro.nombre:libro.nombre+'.xlsx';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/** Fotos de PNC para incrustar en el correo. */
export function fotosDe(eventos, max = 12) {
  const out = [];
  for (const e of eventosActivos(eventos)) {
    for (const url of e.fotos || []) {
      if (out.length >= max) return out;
      out.push({ url, enlace: url, sku: e.sku });
    }
  }
  return out;
}

/** Asigna unidades con incidencia a las filas y listas del conteo que las originó. */
export function completarIncidencias(filas,eventos,meta={}){
 const anulados=new Set(eventos.filter(e=>e.tipo==='ANULACION').map(e=>e.anulaA||String(e.id).replace(/^anula-/,'')));
 const correcciones=new Map(eventos.filter(e=>e.tipo==='CALIDAD'&&e.eventoId&&!anulados.has(e.id)).map(e=>[e.eventoId,e.incidencias]));
 const grupos=new Map();
 for(const e of eventos){if(anulados.has(e.id)||e.anulado||e.tipo==='ANULACION'||!(Number(e.cantidad)>0))continue;
  const fs=correcciones.get(e.id)||e.incidencias||(e.estadoFisico==='PNC'?[{tipo:'MAL_ESTADO',nombre:'MAL ESTADO',cantidad:Number(e.cantidad),pnc:true}]:[]);
  const clave=JSON.stringify([e.sku,e.origen||'']);if(!grupos.has(clave))grupos.set(clave,[]);
  for(const f of fs)grupos.get(clave).push({...f,cantidad:Number(f.cantidad)});
 }
 return filas.map(l=>{let disponible=Number(l.fisica)||0,pnc=0,novedad=0;const tipos=[];
  if(l.registrosAsignados){
   for(const p of l.incidenciasAsignadas||[]){novedad+=p.cantidad;if(p.pnc)pnc+=p.cantidad;const nombre=p.tipo+' ('+p.cantidad+' u.)'+(p.pallet?' · Pallet '+p.pallet:'');if(!tipos.includes(nombre))tipos.push(nombre);}
  }else{
  for(const origen of [l.origen||'PRINCIPAL','']){const gs=grupos.get(JSON.stringify([l.sku,origen]))||[];
   for(const f of gs){const n=Math.min(disponible,f.cantidad);if(n<=0)continue;f.cantidad-=n;disponible-=n;novedad+=n;if(f.pnc)pnc+=n;const nombre=(f.nombre||f.tipo)+(f.pallet?' · Pallet '+f.pallet:'');if(!tipos.includes(nombre))tipos.push(nombre);}
  }
  }
  if(l.diferencia)tipos.push(l.diferencia<0?'FALTANTE':'SOBRANTE');
  const sinDesglose=l.calidadPorRevisar&&pnc===0;if(sinDesglose)tipos.push('PNC · cantidad por revisar');
  const depot=meta.validacionDepot?.porSku?.[l.sku],observacion=l.observacion||'';
  return {...l,observacion,pnc:pnc?'PNC ('+pnc+')':sinDesglose?'PNC · cantidad por revisar':'',cantidadPnc:sinDesglose?null:pnc,cantidadConforme:sinDesglose?null:Number(l.fisica)-pnc,
   cantidadIncidencia:sinDesglose?null:novedad||Math.abs(l.diferencia||0),incidencia:tipos.join(' / ')||'OK',
   depot:depot?.valor??(meta.depot?.[l.sku]===undefined?undefined:meta.depot[l.sku]?'ok':'N/D'),depotNota:depot?depot.nota+'\nFuente: '+depot.fuente+' · Actualización: '+(depot.fechaActualizacion||depot.actualizadoEn||'sin confirmar'):undefined,
   marca:meta.marca||undefined,cliente:meta.cliente||undefined,codigoBarra:meta.barras?.[l.sku],evidencia:(meta.carpetasCategoria?.[l.sku]?.[pnc?'PNC':l.diferencia<0?'FALTANTE':l.diferencia>0?'SOBRANTE':'VALIDACION']||meta.carpetas?.[l.sku])?.join(' | ')};
 });
}
