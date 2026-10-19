/**
 * Indicadores y trazabilidad.
 *
 * Todo sale del libro mayor (`eventos`) y del agregado por SKU. No hay una
 * segunda base con cifras precalculadas: un número que no se puede rastrear
 * hasta el conteo que lo originó no sirve para discutir con nadie.
 *
 * Por eso cada cifra de aquí tiene su detalle: el SKU, la recepción, la fecha,
 * el operario. Lo que se ve en la tabla es lo mismo que está en Firestore.
 */
import { collection, getDocs, query, orderBy, limit }
  from '../vendor/firebase-sdk.js?v=20261019-52';
import { db } from './auth.js?v=20261019-52';
import * as local from './local.js?v=20261019-52';
import { aNumero, listarRecepciones } from './datos.js?v=20261019-52';

/** Fecha de un campo de Firestore, venga como Timestamp o como texto. */
export function aFecha(v) {
  if (!v) return null;
  if (typeof v.toDate === 'function') return v.toDate();
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

export const soloDia = f => f ? new Intl.DateTimeFormat('en-CA',{timeZone:'America/Guayaquil',year:'numeric',month:'2-digit',day:'2-digit'}).format(f) : '';

/** Recepciones del periodo pedido, ya con sus totales. */
export async function recepcionesDesde(desde, hasta) {
  if(local.modoLocal()) {
    const todas=[];let total=0;
    do {const params=new URLSearchParams({offset:todas.length,limite:500});if(desde)params.set('desde',desde);if(hasta)params.set('hasta',hasta);const r=await local.pedir('/reportes/recepciones?'+params);
      total=r.total;todas.push(...r.recepciones);if(!r.recepciones.length)break;
    }while(todas.length<total);
    return todas;
  }
  const todas = await listarRecepciones(500);
  return todas.filter((r) => {
    const f = aFecha(r.creadoEn);
    if (!f) return false;
    const d = soloDia(f);
    return (!desde || d >= desde) && (!hasta || d <= hasta);
  });
}

/** SKU y eventos de una recepción. Dos lecturas de colección. */
export async function detalleDe(recepcionId) {
  if (local.modoLocal()) {
    const [skus, eventos] = await Promise.all([
      local.leerColeccion(recepcionId, 'skus'), local.leerColeccion(recepcionId, 'eventos'),
    ]);
    eventos.sort((a, b) => (aFecha(a.creadoEn)?.getTime() || 0) - (aFecha(b.creadoEn)?.getTime() || 0));
    return { skus, eventos };
  }
  const [skus, eventos] = await Promise.all([
    getDocs(collection(db, 'recepciones', recepcionId, 'skus'))
      .then((s) => s.docs.map((d) => ({ id: d.id, ...d.data() }))),
    getDocs(query(collection(db, 'recepciones', recepcionId, 'eventos'),
                  orderBy('creadoEn', 'asc'), limit(3000)))
      .then((s) => s.docs.map((d) => ({ id: d.id, ...d.data() }))),
  ]);
  return { skus, eventos };
}

/** Los filtros de producto/etiquetas recortan SKU y sus eventos antes de sumar. */
export function filtrarDetalles(todos,{codigo='',cliente='',estado='',producto='',etiqueta=''}={}) {
  const texto=producto.trim().toUpperCase(),cod=codigo.trim().toUpperCase();
  return todos.filter(d=>(!cod || d.recepcion.codigo.toUpperCase().includes(cod)) &&
    (!cliente || d.recepcion.cliente===cliente) && (!estado || d.recepcion.estado===estado)).map(d=>{
    const skus=d.skus.filter(s=>{
      if(texto && !`${s.sku} ${s.descripcion || ''}`.toUpperCase().includes(texto))return false;
      const e=Number(s.esperado)||0,f=Number(s.contado)||0;
      return !etiqueta || ({PNC:!!s.tienePnc,COMPLETO:!!s.verificado && f===e && !s.tienePnc,
        PENDIENTE:!s.verificado,FALTANTE:!!s.verificado && f<e,SOBRANTE:!!s.verificado && f>e,
        ADICIONAL:s.enPackingList===false}[etiqueta] || false);
    });
    const ids=new Set(skus.map(s=>s.sku));
    return {...d,skus,eventos:d.eventos.filter(e=>ids.has(e.sku))};
  }).filter(d=>!texto && !etiqueta || d.skus.length);
}

export function referenciasDe(detalles) {
  return detalles.flatMap(d=>d.skus.map(s=>({sku:s.sku,descripcion:s.descripcion || '',recepcion:d.recepcion.codigo,
    esperado:Number(s.esperado)||0,contado:Number(s.contado)||0,diferencia:(Number(s.contado)||0)-(Number(s.esperado)||0),
    estado:s.verificado ? (s.estado || '') : 'PENDIENTE',pnc:!!s.tienePnc})));
}

/**
 * Indicadores de una recepción.
 *
 * `exactitud` es el porcentaje de SKU que cuadraron a la primera, que es lo que
 * se reclama al proveedor. `avance` cuenta unidades verificadas, con el tope
 * aplicado por SKU: contar de más en un producto no puede tapar lo que falta
 * en otro.
 */
export function indicadoresDe({ recepcion, skus, eventos }) {
  let ok = 0, faltante = 0, sobrante = 0, sinContar = 0, conPnc = 0;
  let esperadas = 0, fisicas = 0, cubiertas = 0, verificadas=0;
  const adicionales = [];

  for (const s of skus) {
    const e = aNumero(s.esperado, 0);
    const f = aNumero(s.contado, 0);
    if(s.verificado===true||f!==0)verificadas++;
    esperadas += e;
    fisicas += f;
    cubiertas += Math.min(f, e);
    if (s.tienePnc) conPnc++;
    if (s.enPackingList === false) adicionales.push(s);

    if (f === e) ok++;
    else if (f < e) { faltante++; if (f === 0) sinContar++; }
    else sobrante++;
  }

  // Los eventos de anulación no son trabajo: son corrección de trabajo.
  const anulados=new Set(eventos.filter(e=>e.tipo==='ANULACION').map(e=>e.anulaA||String(e.id).replace(/^anula-/,'')));
  const conteos = eventos.filter(e=>!['ANULACION','CIERRE','REAPERTURA','AUDITORIA','EXPORT','AJUSTE','CALIDAD'].includes(e.tipo) && !e.anulado && !anulados.has(e.id));
  const anulaciones = eventos.filter((e) => e.tipo === 'ANULACION');

  const fechas = eventos.map((e) => aFecha(e.creadoEn)).filter(Boolean);
  const inicio = fechas.length ? fechas[0] : null;
  const fin = fechas.length ? fechas[fechas.length - 1] : null;
  const minutos = inicio && fin ? Math.max(Math.round((fin - inicio) / 60000), 0) : 0;

  const operarios = new Set(eventos.map((e) => e.operadorEmail).filter(Boolean));

  return {
    id: recepcion.id,
    codigo: recepcion.codigo,
    cliente: recepcion.cliente || '',
    estado: recepcion.estado,
    fecha: soloDia(aFecha(recepcion.creadoEn)),
    skus: skus.length,
    ok, faltante, sobrante, sinContar, conPnc,
    adicionales: adicionales.length,
    esperadas, fisicas, cubiertas, verificadas,
    diferencia: fisicas - esperadas,
    exactitud: skus.length ? Math.round((ok / skus.length) * 1000) / 10 : 0,
    avance: skus.length ? Math.round(100*verificadas/skus.length) : 0,
    coberturaUnidades: esperadas ? Math.round((cubiertas / esperadas) * 100) : 0,
    conteos: conteos.length,
    anulaciones: anulaciones.length,
    // Lo que de verdad mide la productividad: unidades por hora de trabajo.
    minutos,
    unidadesHora: minutos > 0 ? Math.round((fisicas / minutos) * 60) : 0,
    operarios: operarios.size,
    inicio, fin,
  };
}

/** Suma de varias recepciones, con las medias ponderadas bien hechas. */
export function consolidar(lista) {
  const base = {
    recepciones: lista.length, skus: 0, ok: 0, faltante: 0, sobrante: 0,
    sinContar: 0, conPnc: 0, adicionales: 0, esperadas: 0, fisicas: 0,
    cubiertas: 0, verificadas:0, conteos: 0, anulaciones: 0, minutos: 0,
  };
  for (const r of lista) {
    for (const k of Object.keys(base)) {
      if (k !== 'recepciones') base[k] += r[k] || 0;
    }
  }
  return {
    ...base,
    diferencia: base.fisicas - base.esperadas,
    // Promediar los porcentajes de cada recepción daría el mismo peso a una de
    // 3 líneas que a una de 300. Se recalculan sobre los totales.
    exactitud: base.skus ? Math.round((base.ok / base.skus) * 1000) / 10 : 0,
    avance: base.skus ? Math.round(100*base.verificadas/base.skus) : 0,
    coberturaUnidades: base.esperadas ? Math.round((base.cubiertas / base.esperadas) * 100) : 0,
    unidadesHora: base.minutos > 0 ? Math.round((base.fisicas / base.minutos) * 60) : 0,
  };
}

/** Productividad por operario, a partir de los eventos. */
export function porOperario(eventos) {
  const mapa = {};
  const anulados=new Set(eventos.filter(e=>e.tipo==='ANULACION').map(e=>e.anulaA||String(e.id).replace(/^anula-/,'')));
  for (const e of eventos) {
    if(['CIERRE','REAPERTURA','AUDITORIA','EXPORT','AJUSTE','CALIDAD'].includes(e.tipo))continue;
    const clave = e.operadorEmail || '—';
    const o = (mapa[clave] = mapa[clave] || {
      email: clave, nombre: e.operadorNombre || clave,
      conteos: 0, unidades: 0, anulaciones: 0, pnc: 0,
      skus: new Set(), pallets: new Set(), primera: null, ultima: null,
    });
    const f = aFecha(e.creadoEn);
    if (f) {
      if (!o.primera || f < o.primera) o.primera = f;
      if (!o.ultima || f > o.ultima) o.ultima = f;
    }
    if (e.tipo === 'ANULACION') { o.anulaciones++; continue; }
    if(e.anulado || anulados.has(e.id))continue;
    o.conteos++;
    o.unidades += aNumero(e.cantidad, 0);
    if (e.estadoFisico === 'PNC') o.pnc++;
    if (e.sku) o.skus.add(e.sku);
    if (e.pallet) o.pallets.add(e.pallet);
  }

  return Object.values(mapa).map((o) => {
    const min = o.primera && o.ultima
      ? Math.max(Math.round((o.ultima - o.primera) / 60000), 0) : 0;
    return {
      ...o,
      skus: o.skus.size,
      pallets: o.pallets.size,
      minutos: min,
      unidadesHora: min > 0 ? Math.round((o.unidades / min) * 60) : 0,
    };
  }).sort((a, b) => b.unidades - a.unidades);
}

/**
 * SKU que más problemas dan, de todas las recepciones del periodo.
 *
 * Es el indicador que sirve para hablar con el proveedor: no «hubo faltantes»,
 * sino «esta referencia falló en 4 de las 6 últimas recepciones».
 */
export function skusProblematicos(detalles, max = 25) {
  const mapa = {};
  for (const { recepcion, skus } of detalles) {
    for (const s of skus) {
      const e = aNumero(s.esperado, 0);
      const f = aNumero(s.contado, 0);
      if (f === e && !s.tienePnc) continue;

      const r = (mapa[s.sku] = mapa[s.sku] || {
        sku: s.sku, descripcion: s.descripcion || '',
        veces: 0, faltante: 0, sobrante: 0, pnc: 0, unidades: 0, recepciones: [],
      });
      r.veces++;
      if (f < e) r.faltante++;
      else if (f > e) r.sobrante++;
      if (s.tienePnc) r.pnc++;
      r.unidades += f - e;
      r.recepciones.push(recepcion.codigo);
    }
  }
  return Object.values(mapa)
    .sort((a, b) => b.veces - a.veces || Math.abs(b.unidades) - Math.abs(a.unidades))
    .slice(0, max);
}

/** Serie por día, para ver la tendencia. */
export function porDia(lista) {
  const mapa = {};
  for (const r of lista) {
    const d = r.fecha;
    if (!d) continue;
    const x = (mapa[d] = mapa[d] || {
      fecha: d, recepciones: 0, esperadas: 0, fisicas: 0, cubiertas: 0,
      skus: 0, ok: 0,
    });
    x.recepciones++;
    x.esperadas += r.esperadas;
    x.fisicas += r.fisicas;
    x.cubiertas += r.cubiertas;
    x.skus += r.skus;
    x.ok += r.ok;
  }
  return Object.values(mapa)
    .map((d) => ({ ...d, exactitud: d.skus ? Math.round((d.ok / d.skus) * 1000) / 10 : 0 }))
    .sort((a, b) => a.fecha.localeCompare(b.fecha));
}

/** Historial de un SKU a lo largo de las recepciones: la traza por producto. */
export function historialDe(sku, detalles) {
  const filas = [];
  for (const { recepcion, skus, eventos } of detalles) {
    const s = skus.find((x) => x.sku === sku);
    if (!s) continue;
    const propios = eventos.filter((e) => e.sku === sku);
    filas.push({
      recepcion: recepcion.codigo,
      fecha: soloDia(aFecha(recepcion.creadoEn)),
      esperado: aNumero(s.esperado, 0),
      contado: aNumero(s.contado, 0),
      diferencia: aNumero(s.contado, 0) - aNumero(s.esperado, 0),
      estado: s.estado || '',
      pnc: !!s.tienePnc,
      conteos: propios.length,
      operarios: [...new Set(propios.map((e) => e.operadorNombre || e.operadorEmail))]
        .filter(Boolean),
    });
  }
  return filas.sort((a, b) => (b.fecha || '').localeCompare(a.fecha || ''));
}

/**
 * Exporta lo que se esté viendo.
 *
 * Excel y PDF, no CSV. El CSV está reservado a los formatos de alta masiva
 * hacia Depot: si los indicadores salieran también en CSV, acabarían subiéndose
 * como si fueran uno de esos archivos.
 *
 * El PDF es para leer y adjuntar a un correo; el Excel, para seguir
 * trabajándolo.
 */
export async function aExcel(filas, columnas, titulo, nombre, contexto={}) {
  if(local.modoLocal()) {
    const r=await fetch('/api/app/reportes/excel',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({titulo,filtros:contexto.filtros || '',resumen:contexto.resumen || '',columnas:columnas.map(c=>c.titulo),filas:filas.map(f=>columnas.map(c=>c.valor(f) ?? ''))})});
    if(!r.ok) {const e=await r.json();throw new Error(typeof e.detail==='string' ? e.detail : 'No se pudo crear el Excel con logo.');}
    const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=nombre+'.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),4000);return;
  }
  if (typeof XLSX === 'undefined') {
    throw new Error('No se cargó la librería de Excel. Recarga la página.');
  }
  const datos = filas.map((f) => {
    const o = {};
    for (const c of columnas) o[c.titulo] = c.valor(f);
    return o;
  });

  const hoja = XLSX.utils.json_to_sheet(datos);
  hoja['!cols'] = columnas.map((c) => ({ wch: Math.min(Math.max(c.titulo.length + 4, 12), 40) }));
  if (datos.length) {
    hoja['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 },
      e: { r: datos.length, c: columnas.length - 1 } }) };
  }

  const libro = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(libro, hoja, (titulo || 'KPI').slice(0, 31));
  XLSX.writeFile(libro, nombre.endsWith('.xlsx') ? nombre : nombre + '.xlsx');
}

/**
 * PDF con la tabla, para adjuntar o imprimir.
 *
 * Se arma con jsPDF, que carga la página. Si no llegó —red del almacén— se dice
 * en vez de dejar un botón que no hace nada.
 */
export async function aPdf(filas, columnas, { titulo, subtitulo, nombre, resumen }) {
  const logo=await fetch(new URL('../icono.png',import.meta.url));
  if(!logo.ok)throw new Error('No se pudo cargar el logo del reporte.');
  const blob=await logo.blob();
  const imagen=await new Promise((resolve,reject)=>{const lector=new FileReader();lector.onload=()=>resolve(lector.result);lector.onerror=reject;lector.readAsDataURL(blob);});
  const jsPDFCtor = window.jspdf?.jsPDF;
  if (!jsPDFCtor) {
    throw new Error('No se cargó la librería de PDF. Revisa la conexión y recarga.');
  }

  // Apaisado: estas tablas tienen más columnas que alto.
  const doc = new jsPDFCtor({ orientation: 'landscape', unit: 'pt', format: 'a4', compress:true });
  const ancho = doc.internal.pageSize.getWidth();

  doc.addImage(imagen,'PNG',40,16,24,24,'logo','FAST');
  doc.setFontSize(17);doc.setTextColor(30,85,214);doc.text('ITSANET',72,35);
  doc.setTextColor(0);
  doc.setFontSize(15);
  doc.setFont(undefined, 'bold');
  doc.text(titulo || 'Indicadores', 40, 64);

  doc.setFontSize(9);
  doc.setFont(undefined, 'normal');
  doc.setTextColor(110);
  const lineasFiltros=doc.splitTextToSize(subtitulo || '',ancho-80);
  doc.text(lineasFiltros, 40, 82);
  doc.text(`ITSANET · ${new Date().toLocaleString('es-EC',{timeZone:'America/Guayaquil'})}`, ancho - 40, 35,
           { align: 'right' });

  const finFiltros=82+lineasFiltros.length*12;
  if (resumen) {
    doc.setTextColor(30);
    doc.setFontSize(10);
    doc.text(resumen, 40, finFiltros+16, { maxWidth: ancho - 80 });
  }

  doc.autoTable({
    startY: finFiltros+(resumen ? 44 : 16),
    head: [columnas.map((c) => c.titulo)],
    body: filas.map((f) => columnas.map((c) => {
      const v = c.valor(f);
      return v === null || v === undefined ? '' : String(v);
    })),
    styles: { fontSize: 7.5, cellPadding: 3, overflow: 'linebreak' },
    headStyles: { fillColor: [15, 23, 42], fontSize: 7.5, fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [244, 247, 249] },
    margin: { left: 40, right: 40 },
    didDrawPage: (d) => {
      const alto = doc.internal.pageSize.getHeight();
      doc.setFontSize(8);
      doc.setTextColor(140);
      doc.text(`Página ${d.pageNumber}`, ancho - 40, alto - 20, { align: 'right' });
    },
  });

  doc.save(nombre.endsWith('.pdf') ? nombre : nombre + '.pdf');
}

/** Exporta lo que se esté viendo, para seguir trabajándolo fuera. */
export function aCsv(filas, columnas) {
  const esc = (v) => {
    const t = v === null || v === undefined ? '' : String(v);
    return /[",;\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
  };
  const lineas = [columnas.map((c) => esc(c.titulo)).join(';')];
  for (const f of filas) lineas.push(columnas.map((c) => esc(c.valor(f))).join(';'));
  // El BOM es lo que hace que Excel en español abra las tildes bien.
  return '﻿' + lineas.join('\r\n');
}
