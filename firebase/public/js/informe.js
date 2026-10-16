/**
 * Informe final de la recepción.
 *
 * Regla del cliente, textual: «si tenemos 22 filas debemos entregar 22 filas».
 * Por eso el archivo se construye desde la subcolección `lineas`, que conserva
 * el orden y el número de fila del archivo original, y NO desde el agregado por
 * SKU. Se añaden columnas a la derecha; no se añade ni se quita ninguna fila.
 *
 * Lo que llegó sin estar en el packing list va en su propia hoja ADICIONALES, y
 * los conteos uno a uno en BITACORA, para que Depot reciba la tabla limpia y el
 * auditor tenga el detalle en el mismo archivo.
 */
import { collection, getDocs, query, orderBy } from '../vendor/firebase-sdk.js?v=20261016-34';
import { nombreDeInforme, carpetaDeRecepcion, carpetaDeMes } from './nombres.js?v=20261016-34';
import { db } from './auth.js?v=20261016-34';
import * as local from './local.js?v=20261016-34';
import { aNumero, decodificarPallets } from './datos.js?v=20261016-34';

const aFechaMs = (v) => (v?.toDate ? v.toDate().getTime() : 0);

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

const etiquetaEstado = (declarada, fisica) => {
  if (fisica === declarada) return declarada === 0 ? 'SIN CANTIDAD' : 'OK';
  if (fisica === 0) return 'NO LLEGO';
  return fisica < declarada ? 'FALTANTE' : 'SOBRANTE';
};

/** Reúne todo lo necesario para el informe con 4 lecturas de colección. */
export async function reunirInforme(recepcionId, recepcion) {
  const [lineas, skus, adicionales, eventos, auditoria] = await Promise.all([
    leerColeccion(recepcionId, 'lineas'),
    leerColeccion(recepcionId, 'skus'),
    leerColeccion(recepcionId, 'adicionales'),
    leerColeccion(recepcionId, 'eventos').then((eventos) => {
      const ms = (v) => v?.toMillis ? v.toMillis() : (new Date(v || 0).getTime() || 0);
      return eventos.sort((a, b) => ms(a.creadoEn) - ms(b.creadoEn));
    }),
    leerColeccion(recepcionId, 'auditoria').catch(() => []),
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
  for (const e of eventos) {
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
  for (const e of eventos) {
    if (e.tipo === 'ANULACION' || !e.origen) continue;
    const m = (contadoPorOrigen[e.origen] = contadoPorOrigen[e.origen] || {});
    m[e.sku] = (m[e.sku] || 0) + aNumero(e.cantidad, 0);
  }

  const listasDeLineas = [...new Set(lineas.map((l) => l.origen || 'PRINCIPAL'))];
  const repartido = listasDeLineas.length > 1
    ? listasDeLineas.flatMap((origen) => {
        const suyas = lineas.filter((l) => (l.origen || 'PRINCIPAL') === origen);
        const imputado = contadoPorOrigen[origen];
        if (imputado) return repartirPorLinea(suyas, imputado);
        // Sin imputación explícita: lo no asignado se reparte entre sus líneas.
        const sinAsignar = {};
        for (const l of suyas) {
          if (sinAsignar[l.sku] !== undefined) continue;
          const total = aNumero(porSku[l.sku], 0);
          const yaImputado = Object.values(contadoPorOrigen)
            .reduce((a, m) => a + aNumero(m[l.sku], 0), 0);
          sinAsignar[l.sku] = Math.max(total - yaImputado, 0);
        }
        return repartirPorLinea(suyas, sinAsignar);
      })
    : repartirPorLinea(lineas, porSku);

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

  const detalle=completarIncidencias(detalleBase,eventos,meta);

  const adicionalesDetalle = adicionales.map((a) => {
    const s = skus.find((x) => x.sku === a.sku);
    return {
      sku: a.sku,
      descripcion: a.descripcion || s?.descripcion || '',
      fisica: aNumero(s?.contado, 0),
      pallets: palletsPorSku[a.sku] || '',
      motivo: a.motivo || '',
      detectadoPor: a.detectadoPorEmail || '',
      observacion: [...(obsPorSku[a.sku] || [])].join(' | ').slice(0, 300),
    };
  }).filter((a) => a.fisica !== 0 || a.motivo);

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
    formato: (()=>{const f=formatos[origen] || formatos[origen.replace(/\./g, '~')] || null;return f?{...f,columnas:f.salida||{...f.columnas,...meta.columnas}}:null;})(),
    detalle: detalle.filter((l) => (l.origen || 'PRINCIPAL') === origen),
  }));

  return {
    recepcion, detalle, porOrigen,
    adicionales: adicionalesDetalle, eventos, skus, auditoria,
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
function hojaOriginal(filas, formato) {
  const enc = (formato?.encabezados || []).slice();
  const col = formato?.columnas || {};
  const ancho = enc.length;
  const salida=new Set(['marca','cliente','fisica','validacion','desface','pallet','posicion','codigoBarra','cantidadIncidencia','incidencia','observacion','evidencia']);
  for(const [rol,i] of Object.entries(col))if(salida.has(rol)&&(!Number.isInteger(i)||i<0||i>=ancho))throw Error('La columna de '+rol+' no existe en este packing list. Revisa Columnas del informe.');

  const matriz = [enc];
  for (const l of filas) {
    const fila = (l.cruda || []).slice(0, ancho);
    while (fila.length < ancho) fila.push('');

    const poner = (rol, valor) => {
      if (col[rol] !== undefined && col[rol] < ancho) fila[col[rol]] = valor;
    };
    poner('fisica', l.fisica);
    poner('validacion', VALIDACION[l.estado] ?? l.estado ?? '');
    poner('desface', l.diferencia);
    poner('pallet', l.palletsSimple || '');
    poner('observacion', l.observacion || '');
    for(const rol of ['marca','cliente','posicion','codigoBarra','cantidadIncidencia','incidencia','evidencia']){
      const valor=rol==='posicion'?l.posicionReal:l[rol];
      if(valor!==undefined&&valor!==null&&valor!=='')poner(rol,valor);
    }

    matriz.push(fila);
  }

  const hoja = XLSX.utils.aoa_to_sheet(matriz);
  hoja['!cols'] = enc.map((c) => ({ wch: Math.min(Math.max(String(c).length + 3, 10), 40) }));
  if (ancho) {
    hoja['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 },
      e: { r: filas.length, c: ancho - 1 } }) };
  }
  return hoja;
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
 * `envio`: solo las hojas del packing list, con el formato que espera quien lo
 * recibe. Es lo que se manda por correo y lo que se sube al sistema. Adjuntar
 * cuatro hojas más obliga a quien da el alta a buscar la buena, y a la primera
 * se equivoca.
 *
 * `auditable`: todo —el detalle, los adicionales, la bitácora y la auditoría—.
 * Es para analizar, transferir datos y responder a una reclamación.
 */
export function construirLibro({ recepcion, detalle, porOrigen, adicionales,
                                 eventos, auditoria }, opciones = {}) {
  if (typeof XLSX === 'undefined') {
    throw new Error('No se cargó la librería de Excel. Recarga la página.');
  }
  const soloEnvio = opciones.version === 'envio';
  const libro = XLSX.utils.book_new();
  libro.Props={Company:'ITSANET',Author:recepcion.informe?.usuario||'ITSANET',Title:recepcion.codigo,Subject:recepcion.informe?'Informe '+recepcion.informe.numero+' · '+recepcion.informe.id:'Validación de recepción'};

  // --- Una hoja por packing list, con SU formato y SUS filas --- //
  const listas = (porOrigen && porOrigen.length)
    ? porOrigen
    : [{ origen: 'VALIDADA', detalle, formato: null }];

  for (const lista of listas) {
    const base = listas.length === 1 ? 'VALIDADA' : nombreDeHoja(lista.origen);

    // Primero el archivo tal como llegó, con sus columnas rellenas. Si no se
    // guardó el formato original —recepciones anteriores a esto— se cae a las
    // columnas propias, que es lo que había.
    XLSX.utils.book_append_sheet(
      libro,
      lista.formato?.encabezados?.length
        ? hojaOriginal(lista.detalle, lista.formato)
        : hojaValidada(lista.detalle),
      base);

    // Y aparte, lo que la validación añade.
    if (!soloEnvio && lista.formato?.encabezados?.length) {
      XLSX.utils.book_append_sheet(
        libro, hojaValidada(lista.detalle), nombreDeHoja(base + ' DET'));
    }
  }

  if (soloEnvio) {
    return {
      base64: XLSX.write(libro, { bookType: 'xlsx', type: 'base64' }),
      nombre: nombreArchivo(recepcion, 'validacion'),
      filas: detalle.length,
      version: 'envio',
    };
  }

  // --- Adicionales, aparte para no alterar el conteo de filas --- //
  const h2 = XLSX.utils.json_to_sheet(adicionales.length ? adicionales.map((a) => ({
    'ITEM': a.sku,
    'DESCRIPCION': a.descripcion,
    'CANTIDAD FISICA': a.fisica,
    'PALLET': a.pallets,
    'MOTIVO': a.motivo,
    'OBSERVACION': a.observacion,
    'DETECTADO POR': a.detectadoPor,
  })) : [{ 'ITEM': '', 'DESCRIPCION': 'Sin adicionales en esta recepción.' }]);
  h2['!cols'] = [{ wch: 18 }, { wch: 40 }, { wch: 14 }, { wch: 22 }, { wch: 34 },
    { wch: 34 }, { wch: 26 }];
  XLSX.utils.book_append_sheet(libro, h2, 'ADICIONALES');

  // --- Hoja 3: la bitácora, el respaldo de cada unidad contada --- //
  const h3 = XLSX.utils.json_to_sheet(eventos.map((e) => ({
    'FECHA': e.creadoEn?.toDate ? e.creadoEn.toDate().toLocaleString('es-EC') : '',
    'ITEM': e.sku,
    'CODIGO ESCANEADO': e.codigoEscaneado || e.sku,
    'CANTIDAD': aNumero(e.cantidad, 0),
    'PALLET': e.pallet || '',
    'POSICION REAL': e.posicionReal || '',
    'PACKING LIST': e.origen || '',
    'ESTADO': e.estadoFisico || '',
    'TIPO': e.tipo || 'CONTEO',
    'OPERARIO': e.operadorNombre || e.operadorEmail || '',
    'OBSERVACION': e.observacion || '',
    'FOTOS': (e.fotos || []).join(' '),
  })));
  h3['!cols'] = [{ wch: 20 }, { wch: 18 }, { wch: 18 }, { wch: 10 }, { wch: 12 },
    { wch: 16 }, { wch: 14 }, { wch: 9 }, { wch: 11 }, { wch: 28 }, { wch: 34 },
    { wch: 40 }];
  XLSX.utils.book_append_sheet(libro, h3, 'BITACORA');

  // --- Hoja 4: cierres y exportaciones --- //
  // Quién cerró, cuándo y qué archivo salió. El agregado se puede volver a
  // calcular; lo que se entregó aquel día, no.
  const h4 = XLSX.utils.json_to_sheet((auditoria || []).length
    ? [...auditoria]
        .sort((a, b) => (aFechaMs(a.creadoEn) - aFechaMs(b.creadoEn)))
        .map((a) => ({
          'FECHA': a.creadoEn?.toDate ? a.creadoEn.toDate().toLocaleString('es-EC') : '',
          'ACCION': a.tipo || '',
          'USUARIO': a.usuarioNombre || a.usuarioEmail || '',
          'ARCHIVO': a.detalle?.archivo || '',
          'DESTINO': a.detalle?.destinatarios || a.detalle?.destino || '',
          'DETALLE': JSON.stringify(a.detalle || {}).slice(0, 300),
        }))
    : [{ 'FECHA': '', 'ACCION': 'Primera exportación de esta recepción.' }]);
  h4['!cols'] = [{ wch: 20 }, { wch: 14 }, { wch: 28 }, { wch: 34 }, { wch: 34 },
    { wch: 60 }];
  XLSX.utils.book_append_sheet(libro, h4, 'AUDITORIA');

  return {
    base64: XLSX.write(libro, { bookType: 'xlsx', type: 'base64' }),
    nombre: nombreArchivo(recepcion, 'auditable'),
    filas: detalle.length,
    version: 'auditable',
  };
}

const nombreArchivo = (recepcion, sufijo) =>
  nombreVersionado(nombreDeInforme(recepcion, { auditable: sufijo === 'auditable' }),recepcion);
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
export function construirLibros(datos, opciones = {}) {
  const listas = datos.porOrigen || [];
  if (opciones.version !== 'envio' || listas.length <= 1) {
    return [construirLibro(datos, opciones)];
  }

  return listas.map((lista,indice) => {
    const libro = construirLibro(
      { ...datos, porOrigen: [lista], detalle: lista.detalle }, opciones);
    return {
      ...libro,
      origen: lista.origen,
      nombre: nombreVersionado(nombreDeInforme(datos.recepcion, { origen: lista.origen }),datos.recepcion,'_L'+String(indice+1).padStart(2,'0')),
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
  for (const e of eventos) {
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
  for(const origen of [l.origen||'PRINCIPAL','']){const gs=grupos.get(JSON.stringify([l.sku,origen]))||[];
   for(const f of gs){const n=Math.min(disponible,f.cantidad);if(n<=0)continue;f.cantidad-=n;disponible-=n;novedad+=n;if(f.pnc)pnc+=n;tipos.push((f.nombre||f.tipo)+' ('+n+')');}
  }
  if(l.diferencia)tipos.push((l.diferencia<0?'FALTANTE':'SOBRANTE')+' ('+Math.abs(l.diferencia)+')');
  const sinDesglose=l.calidadPorRevisar&&pnc===0;if(sinDesglose)tipos.push('PNC · cantidad por revisar');
  return {...l,pnc:pnc?'PNC ('+pnc+')':sinDesglose?'PNC · cantidad por revisar':'',cantidadPnc:sinDesglose?null:pnc,cantidadConforme:sinDesglose?null:Number(l.fisica)-pnc,
   cantidadIncidencia:sinDesglose?null:novedad||Math.abs(l.diferencia||0),incidencia:tipos.join(' / ')||'OK',
   marca:meta.marca||undefined,cliente:meta.cliente||undefined,codigoBarra:meta.barras?.[l.sku],evidencia:meta.carpetas?.[l.sku]?.join(' | ')};
 });
}
