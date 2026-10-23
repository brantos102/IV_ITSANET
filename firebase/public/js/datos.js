/**
 * Modelo de datos y lectura del packing list.
 *
 * El archivo se analiza EN EL NAVEGADOR y se escribe a Firestore. Sin Cloud
 * Functions no hay dónde hacerlo del lado servidor, y además así el operario
 * ve el resultado al instante en vez de esperar a un disparador.
 */
import {
  collection, doc, getDoc, getDocs, setDoc, updateDoc, deleteDoc, query, where,
  orderBy, limit, writeBatch, serverTimestamp, onSnapshot,
} from '../vendor/firebase-sdk.js?v=20261023-68';
import { db } from './auth.js?v=20261023-68';
import { resumenDe, comparar, nombreLimpio } from './huella.js?v=20261023-68';
import * as local from './local.js?v=20261023-68';

/**
 * Dónde se guardan los datos.
 *
 * Cuando la aplicación se sirve desde el servidor de la red local, cada función
 * de aquí abajo delega en `local.js`, que habla con él por HTTP. Cuando se sirve
 * desde iv-itsanet.web.app, hace lo de siempre contra Firestore.
 *
 * La delegación va en la PRIMERA línea de cada función y devuelve los mismos
 * documentos: así el resto del archivo —y, sobre todo, las pantallas— no sabe
 * con qué está hablando, que es lo que permite migrar sin reescribirlas.
 */
export const modoLocal = local.modoLocal;

// --------------------------------------------------------------------------- //
// Normalización — la misma que usa el proxy, para que los cruces coincidan
// --------------------------------------------------------------------------- //
const INVISIBLES = /[ ​‌‍﻿\t\r\n]/g;

export function limpiar(v) {
  if (v === null || v === undefined) return '';
  return String(v).replace(INVISIBLES, ' ').replace(/\s+/g, ' ').trim();
}

/** Clave canónica de cualquier código: SKU, EAN o alterno. */
export function normalizarCodigo(v) {
  return limpiar(v).toUpperCase().replace(/[\s\-_.]/g, '');
}

export function normalizarPallet(v) {
  return limpiar(v).toUpperCase().replace(/\s/g, '');
}

/**
 * Posición del almacén: `A-01-03-2`.
 *
 * NO vale `normalizarPallet` aquí: la posición tiene su propia validación: los guiones son el
 * separador de nave, calle, columna y nivel. Pasar una posición por él la
 * convertía en `A01032`, que no se puede buscar en Depot ni leer de un vistazo.
 */
export function normalizarPosicion(v) {
  return limpiar(v).toUpperCase().replace(/\s+/g, '').slice(0, 40);
}

export function palletValido(c) {
  const p = normalizarPallet(c);
  return !!p && p.length <= 40 && /^[A-Z0-9]+(?:\.[A-Z0-9]+)*(?:-[A-Z0-9]+(?:\.[A-Z0-9]+)*)*$/.test(p);
}

/**
 * Convierte a número tolerando cómo se escriben las cantidades aquí.
 *
 * «1.234,50» y «1,234.50» son el mismo número con los separadores invertidos.
 * Se toma como decimal el ÚLTIMO punto o coma que aparezca, y todo lo anterior
 * se trata como separador de miles. Sin esto, «1.234,50» se leía como 1,234:
 * mil unidades menos en el informe que se sube a Depot.
 */
export function aNumero(v, def = 0) {
  if (v === null || v === undefined || v === '') return def;
  if (typeof v === 'number') return Number.isFinite(v) ? v : def;

  let t = limpiar(v).replace(/[^0-9.,\-]/g, '');
  const negativo = t.startsWith('-');
  t = t.replace(/-/g, '');

  const corte = Math.max(t.lastIndexOf('.'), t.lastIndexOf(','));
  if (corte > -1) {
    const decimales = t.slice(corte + 1);
    // Tres dígitos tras el separador y sin otro separador antes: son miles.
    const esMiles = decimales.length === 3 && !/[.,]/.test(t.slice(0, corte));
    t = esMiles
      ? t.replace(/[.,]/g, '')
      : t.slice(0, corte).replace(/[.,]/g, '') + '.' + decimales;
  }

  const n = parseFloat(t);
  if (Number.isNaN(n)) return def;
  return negativo ? -n : n;
}

/**
 * Clave segura para usar un pallet dentro de un mapa de Firestore.
 *
 * Firestore trata el punto como separador de ruta: `pallets.B04.1` crearía
 * `pallets → B04 → 1`, no la clave "B04.1". Los subpallets son justo los que
 * llevan punto. Se usa `~`, que el validador de pallets no admite y por tanto
 * no puede colisionar con uno real.
 */
export const clavePallet = (p) => normalizarPallet(p).replace(/\./g, '~');
export const palletDesdeClave = (k) => String(k || '').replace(/~/g, '.');

/**
 * Clave de mapa para algo que NO es un pallet: el nombre de un packing list.
 *
 * `clavePallet` no sirve aquí porque normaliza como un pallet y borra los
 * guiones: «PL-A» quedaba como «PLA», y entonces lo imputado a una lista no se
 * podía volver a encontrar por su nombre. Lo único que hay que proteger es el
 * punto, que Firestore trata como separador de ruta.
 */
export const claveMapa = (v) => limpiar(v).toUpperCase().replace(/\./g, '~');

export function decodificarPallets(mapa) {
  const out = {};
  for (const [k, v] of Object.entries(mapa || {})) {
    if (v !== 0) out[palletDesdeClave(k)] = v;
  }
  return out;
}

/**
 * Estado de un SKU. Cinco, no cuatro, y la diferencia importa.
 *
 * «Nadie lo ha buscado todavía» y «se buscó y no apareció» son cosas
 * distintas: la primera es trabajo pendiente, la segunda es un faltante
 * confirmado que hay que reclamar. Mezcladas en PENDIENTE, el operario no sabe
 * qué le queda por hacer y el supervisor no sabe qué reclamar.
 *
 * `verificado` se marca cuando alguien registra algo de ese SKU, incluido un
 * cero explícito.
 */
export function estadoDe(esperado, contado, verificado = contado !== 0) {
  if (!verificado) return esperado > 0 ? 'PENDIENTE' : 'OK';
  if (contado === esperado) return 'OK';
  if (contado === 0) return esperado > 0 ? 'NO_ENCONTRADO' : 'OK';
  return contado < esperado ? 'FALTANTE' : 'SOBRANTE';
}

/** Lo que se le muestra al operario, en su idioma. */
export const ETIQUETA_ESTADO = {
  OK: 'Completo',
  FALTANTE: 'Faltan unidades',
  NO_ENCONTRADO: 'No apareció',
  SOBRANTE: 'Sobran unidades',
  PENDIENTE: 'Sin buscar',
};

// --------------------------------------------------------------------------- //
// Lectura del packing list
// --------------------------------------------------------------------------- //

/** Alias de encabezado → campo. Se compara sin acentos y en mayúsculas. */
const ALIAS = {
  ITEM: 'sku', SKU: 'sku', CODIGO: 'sku', PARTE: 'sku', PRODUCTO: 'sku',
  NUMERODEPIEZA:'sku', 'NUMERO DE PIEZA':'sku',
  'NUMERO DE PARTE': 'sku', 'PART NUMBER': 'sku', 'COD PRODUCTO': 'sku',
  DESCRIPCION: 'descripcion', DESCRIPTION: 'descripcion', DETALLE: 'descripcion',
  REFERENCIAPEDIDO: 'referencia', 'REFERENCIA PEDIDO': 'referencia',
  REFERENCIA: 'referencia', PEDIDO: 'referencia',
  FACTURA: 'factura', INVOICE: 'factura',
  CANTIDAD: 'cantidad', QTY: 'cantidad', QUANTITY: 'cantidad', CANT: 'cantidad',
  EMBARQUE: 'embarque', SHIPMENT: 'embarque', BL: 'embarque',
  'NOMBRE CONTENEDOR': 'contenedor', NOMBRECONTENEDOR:'contenedor', CONTENEDOR:'contenedor', 'NUMERO CONTENEDOR':'contenedor', CONTAINER:'contenedor',
  PRECIOUNIT: 'precioUnit', 'PRECIO UNIT': 'precioUnit',
  PRECIOTOTAL: 'precioTotal', 'PRECIO TOTAL': 'precioTotal',
};

/**
 * Columnas que RELLENA la validación.
 *
 * El packing list que llega ya las trae vacías: `Cantidad Física`,
 * `Validación`, `DESFACE`, `PALLET`, `OBSERVACION`… El informe final tiene que
 * devolver el archivo con esas mismas columnas, en la misma posición y con el
 * mismo encabezado, solo que llenas. Por eso aquí no se descartan: se marcan,
 * para saber dónde escribir cada cosa al exportar.
 */
export const ROL_COLUMNA = {
  'OK':'depot','EXISTE EN DEPOT':'depot','ESTADO DEPOT':'depot',
  'CANTIDAD FISICA': 'fisica', 'CANTIDADFISICA': 'fisica',
  'CANT FISICA': 'fisica', 'CANTIDAD VALIDADA': 'fisica',
  'VALIDACION': 'validacion', 'ESTADO': 'validacion',
  'DESFACE': 'desface', 'DESFASE': 'desface', 'DIFERENCIA': 'desface',
  'PALLET': 'pallet', 'PALETA': 'pallet',
  'CODIGO BARRA': 'codigoBarra', 'CODIGOBARRA': 'codigoBarra',
  'MARCA':'marca','CLIENTE':'cliente','TIPO DE INCIDENCIA':'incidencia','TIPO INCIDENCIA':'incidencia','INCIDENCIA':'incidencia','INCIDENCIAS':'incidencia',
  'CANT CON INCIDENCIA':'cantidadIncidencia','CANT CON INCIDENCIA DIFERENCIA':'cantidadIncidencia','CANTIDAD CON INCIDENCIA':'cantidadIncidencia','CANT. CON INCIDENCIA':'cantidadIncidencia',
  'EVIDENCIA FOTOGRAFICA : DIR, URL (DRIVE)':'evidencia','EVIDENCIA FOTOGRAFICA DIR URL DRIVE':'evidencia','CARPETA DRIVE':'evidencia','CARPETA DRIVE DEL SKU':'evidencia',
  'OK DEPOT':'depot','POSICION':'posicion','POSICION REAL':'posicion',
  'CODIGO DE BARRAS':'codigoBarra','CODIGO BARRAS':'codigoBarra',
  'OBSERVACION': 'observacion', 'OBSERVACIONES': 'observacion',
};

const normalizarEncabezadoInforme=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]+/g,' ').trim();
export function destinosInforme(formato,rol){
  const protegidas=new Set(Object.entries(formato.columnas||{}).filter(([k])=>!Object.values(ROL_COLUMNA).includes(k)).map(([,i])=>i));
  return (formato.encabezados||[]).flatMap((e,i)=>{
    const clave=normalizarEncabezadoInforme(e),salida=ROL_COLUMNA[clave];
    if(ALIAS[clave]||protegidas.has(i))return [];
    return (salida===rol||!salida&&formato.columnas?.[rol]===i)?[i]:[];
  });
}
export function columnasSegurasInforme(formato,columnas){
  const resultado={};
  for(const [rol,i] of Object.entries(columnas||{})){
    if(!Object.values(ROL_COLUMNA).includes(rol)){resultado[rol]=i;continue;}
    const destinos=destinosInforme(formato,rol);
    if(destinos.includes(i))resultado[rol]=i;
    else if(destinos.length)resultado[rol]=destinos[0];
  }
  return resultado;
}
export const prefijoInforme=formato=>(formato.prefijo||[]).filter(f=>!(f.celdas||f).some(c=>/espacio que llena/i.test(String(c||''))));

const COLUMNAS_RESULTADO = new Set(Object.keys(ROL_COLUMNA));

/** Selección explícita de contenedores recibidos; conserva las filas originales. */
export function seleccionarContenedoresPacking(resultado,numeros){
  if(!Array.isArray(numeros))throw Error('Selecciona los contenedores recibidos.');
  const elegidos=new Set(numeros),disponibles=new Set(resultado.lineas.map(l=>l.contenedor||''));
  if([...elegidos].some(n=>!disponibles.has(n)))throw Error('Un contenedor seleccionado no pertenece al archivo.');
  const seleccionadas=resultado.lineas.filter(l=>elegidos.has(l.contenedor||''));
  const lineas=seleccionadas.map(l=>seleccionadas.length<resultado.lineas.length&&Object.keys(l.formulas||{}).length
    ?{...l,formulasOrigen:l.formulas,formulas:{}}:l);
  if(!lineas.length)throw Error('Selecciona al menos un contenedor con productos.');
  const porSku={};for(const l of lineas)porSku[l.sku]=(porSku[l.sku]||0)+l.cantidad;
  return {...resultado,lineas,porSku,skusUnicos:Object.keys(porSku).length,unidades:lineas.reduce((n,l)=>n+l.cantidad,0),
    embarques:[...new Set(lineas.map(l=>l.embarque).filter(Boolean))]};
}

const sinAcentos = (t) => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '');
const clave = (t) => sinAcentos(limpiar(t)).toUpperCase();

function mapearEncabezado(fila) {
  const mapa = {};
  fila.forEach((celda, i) => {
    const k = clave(celda);
    if (!k || COLUMNAS_RESULTADO.has(k)) return;
    const campo = ALIAS[k] || ALIAS[k.replace(/\./g, '')] || ALIAS[k.replace(/\s/g, '')];
    if (campo) mapa[i] = campo;
  });
  // ITEM a veces es solo el numero de fila. Si existe un codigo explicito,
  // ese identifica el producto y ITEM se conserva como columna original.
  const explicita = Object.keys(mapa).some((i) => mapa[i] === 'sku' && clave(fila[i]) !== 'ITEM');
  if (explicita) for (const i of Object.keys(mapa)) {
    if (mapa[i] === 'sku' && clave(fila[i]) === 'ITEM') delete mapa[i];
  }
  return priorizarColumnas(mapa,fila);
}
function priorizarColumnas(mapa,fila){
  // Una tabla lateral puede repetir FACTURA, DETALLE o BL. Nunca sobrescribir
  // las columnas de la tabla de productos con un resumen independiente.
  const prioridad=(i,c)=>c==='embarque'&&['EMBARQUE','SHIPMENT'].includes(clave(fila[i]))?2:
    c==='descripcion'&&['DESCRIPCION','DESCRIPTION'].includes(clave(fila[i]))?2:1;
  const elegidas={};
  for(const [i,c] of Object.entries(mapa))if(elegidas[c]===undefined||prioridad(i,c)>prioridad(elegidas[c],c))elegidas[c]=i;
  for(const i of Object.keys(mapa))if(elegidas[mapa[i]]!==i)delete mapa[i];
  return mapa;
}

/**
 * Lee un .xlsx y devuelve las líneas.
 *
 * Busca la fila de encabezados en las primeras 25, así que tolera archivos con
 * títulos o logos encima de la tabla.
 */
export function leerPackingList(arrayBuffer, opciones = {}) {
  if (typeof XLSX === 'undefined') {
    throw new Error('No se cargó la librería de Excel. Revisa la conexión y recarga.');
  }
  const libro = XLSX.read(arrayBuffer, { type: 'array', cellNF: true });
  if(opciones.encabezado && (!Number.isInteger(opciones.encabezado)||opciones.encabezado<1||opciones.encabezado>1000))throw new Error('Fila de encabezado: de 1 a 1000.');
  if(opciones.columnas){const campos=Object.values(opciones.columnas);
    if(!campos.includes('sku')||!campos.includes('cantidad')||Object.keys(opciones.columnas).some(k=>!/^\d+$/.test(k)||Number(k)>1000))throw new Error('Selecciona columnas distintas para SKU y cantidad.');}

  // Lo que se fue mirando, por si al final no se reconoce nada: sin esto el
  // error dice «no se encontró la tabla» y deja a quien carga un cliente nuevo
  // sin saber si el problema es la hoja, la fila o el nombre de una columna.
  const miradas = [];

  for (const nombreHoja of libro.SheetNames) {
    if(opciones.hoja && nombreHoja!==opciones.hoja)continue;
    const hoja = libro.Sheets[nombreHoja];
    const filas = XLSX.utils.sheet_to_json(hoja, { header: 1, blankrows: true, range:0, defval: '' });

    for (let i = 0; i < Math.min(filas.length, opciones.encabezado || 25); i++) {
      if(opciones.encabezado && i!==opciones.encabezado-1)continue;
      const automatico=mapearEncabezado(filas[i]);
      const mapa = opciones.columnas ? priorizarColumnas({...opciones.columnas},filas[i]) : automatico;
      if(!Object.values(mapa).includes('contenedor')){
        const indice=Object.keys(automatico).find(k=>automatico[k]==='contenedor');
        if(indice!==undefined&&!mapa[indice])mapa[indice]='contenedor';
      }
      const campos = new Set(Object.values(mapa));
      if (!campos.has('sku') || !campos.has('cantidad')) {
        // La fila con más celdas con texto es la que más se parece a una
        // cabecera, aunque sus nombres no sean los que se esperan.
        const llenas = (filas[i] || []).filter((c) => limpiar(c)).length;
        if (llenas >= 3 && miradas.length < 4) {
          miradas.push({
            hoja: nombreHoja,
            fila: i + 1,
            llenas,
            columnas: (filas[i] || []).map((c) => limpiar(c)).filter(Boolean).slice(0, 12),
            reconocidas: [...campos],
          });
        }
        continue;
      }

      // Los encabezados TAL CUAL. El informe final devuelve el archivo con
      // estas mismas columnas, en este mismo orden: quien lo recibe lo abre
      // esperando el suyo, no uno parecido.
      const encabezados = filas[i].map((c) => (c === null || c === undefined ? '' : String(c)));
      const anchoReal = encabezados.length;

      // Dónde está cada columna que la validación rellena.
      const columnas = {};
      encabezados.forEach((c, idx) => {
        const rol = ROL_COLUMNA[clave(c)] || ROL_COLUMNA[clave(c).replace(/\s/g, '')];
        if (rol && columnas[rol] === undefined) columnas[rol] = idx;
      });

      // Encontrada la cabecera: todo lo de abajo son datos.
      const lineas = [];
      let descartadas = 0;
      for (let j = i + 1; j < filas.length; j++) {
        const cruda = filas[j];
        if (!cruda || cruda.every((c) => c === '' || c === null)) continue;

        const d = {};
        for (const [idx, campo] of Object.entries(mapa)) d[campo] = cruda[idx];

        const indiceSku=Number(Object.entries(mapa).find(([,campo])=>campo==='sku')[0]);
        if(typeof d.sku==='number') {
          if(!Number.isSafeInteger(d.sku)||String(Math.abs(d.sku)).length>15)throw new Error(`Fila ${j+1}: guarda el SKU como texto para conservar todos sus dígitos.`);
          const celda=typeof XLSX.utils.encode_cell==='function' ? hoja[XLSX.utils.encode_cell({r:j,c:indiceSku})] : null;
          if(/^0[0-9]+$/.test(celda?.w || ''))d.sku=celda.w;
        }

        const sku = normalizarCodigo(d.sku);
        if (!sku) { descartadas++; continue; }
        const cantidad=aNumero(d.cantidad,NaN);
        if(!Number.isFinite(cantidad)||cantidad<0)throw new Error(`Fila ${j+1}: la cantidad debe ser numérica y mayor o igual a cero.`);

        lineas.push({
          linea: lineas.length + 1,
          sku,
          // La fila completa, para poder devolverla igual. Se normaliza a texto
          // y al ancho de la cabecera: Firestore no admite arrays irregulares
          // con huecos, y al exportar tiene que cuadrar columna por columna.
          cruda: [...Array(anchoReal)].map((_, k) => {
            const v = cruda[k];
            if(k===indiceSku && typeof v==='number' && typeof d.sku==='string')return d.sku;
            return v === null || v === undefined ? '' : String(v);
          }),
          formulas: Object.fromEntries([...Array(anchoReal)].flatMap((_,k)=>{
            const f=hoja[XLSX.utils.encode_cell({r:j,c:k})]?.f;
            return f ? [[k,f]] : [];
          })),
          // Tipos y formatos de origen, separados de cruda (que sigue siendo texto
          // para compatibilidad). Permiten restaurar fechas/números al exportar.
          tiposCelda:Object.fromEntries([...Array(anchoReal)].flatMap((_,k)=>{
            const c=hoja[XLSX.utils.encode_cell({r:j,c:k})];
            return c&&['n','b'].includes(c.t)?[[k,c.t]]:[];
          })),
          formatosCelda:Object.fromEntries([...Array(anchoReal)].flatMap((_,k)=>{
            const c=hoja[XLSX.utils.encode_cell({r:j,c:k})];
            return c?.z&&c.z!=='General'?[[k,c.z]]:[];
          })),
          filaOriginal:j+1,
          descripcion: limpiar(d.descripcion).slice(0, 300),
          referencia: limpiar(d.referencia).slice(0, 80),
          factura: limpiar(d.factura).slice(0, 80),
          embarque: limpiar(d.embarque).slice(0, 80),
          contenedor: limpiar(d.contenedor).toUpperCase().slice(0,20),
          cantidad,
          precioUnit: aNumero(d.precioUnit) || null,
          precioTotal: aNumero(d.precioTotal) || null,
        });
      }

      if (!lineas.length) continue;

      const porSku = {};
      lineas.forEach((l) => { porSku[l.sku] = (porSku[l.sku] || 0) + l.cantidad; });

      return {
        hoja: nombreHoja,
        filaEncabezado: i+1,
        mapaEntrada: {...mapa},
        encabezados,
        prefijo:filas.slice(0,i).map(f=>({celdas:[...Array(anchoReal)].map((_,k)=>f?.[k]??'')})),
        columnas,
        lineas,
        descartadas,
        skusUnicos: Object.keys(porSku).length,
        unidades: lineas.reduce((a, l) => a + l.cantidad, 0),
        embarques: [...new Set(lineas.map((l) => l.embarque).filter(Boolean))],
        porSku,
      };
    }
  }

  // El error dice QUE trae el archivo, no solo que no sirve. Con un cliente
  // nuevo es la diferencia entre «no funciona» y «ah, la columna se llama
  // CODIGO y no ITEM».
  const mejor = miradas.sort((a, b) => b.llenas - a.llenas)[0];
  if (!mejor) {
    throw new Error(
      'El archivo no tiene ninguna fila con varias columnas de texto. ' +
      '¿Es el archivo correcto, o está la tabla en otra hoja?',
    );
  }

  const falta = ['sku', 'cantidad'].filter((c) => !mejor.reconocidas.includes(c));
  const NOMBRE = { sku: 'el código del producto', cantidad: 'la cantidad' };

  throw new Error(
    `No se reconoció la tabla. Lo más parecido a una cabecera está en la hoja ` +
    `«${mejor.hoja}», fila ${mejor.fila}, y trae: ${mejor.columnas.join(' · ')}. ` +
    `De ahí no se identifica ${falta.map((c) => NOMBRE[c]).join(' ni ')}. ` +
    'Usa «Ajustar hoja y columnas» para seleccionar el formato sin modificar el código.',
  );
}

// --------------------------------------------------------------------------- //
// Recepciones
// --------------------------------------------------------------------------- //

export async function crearRecepcion({ codigo, cliente, descripcion, bultos }, usuario) {
  if (modoLocal()) return local.crearRecepcion({ codigo, cliente, descripcion, bultos });
  const id = normalizarCodigo(codigo);
  if (!id) throw new Error('El código de la recepción es obligatorio.');

  const ref = doc(db, 'recepciones', id);
  if ((await getDoc(ref)).exists()) {
    throw new Error(`Ya existe una recepción con el código ${id}.`);
  }

  await setDoc(ref, {
    codigo: id,
    cliente: limpiar(cliente).toUpperCase() || null,
    descripcion: limpiar(descripcion) || null,
    bultos: aNumero(bultos) || null,
    estado: 'ABIERTA',
    totales: { lineas: 0, skus: 0, unidades: 0 },
    creadoPorUid: usuario.uid,
    creadoPorEmail: usuario.email,
    creadoEn: serverTimestamp(),
  });
  return id;
}

/**
 * Guarda las líneas y el agregado por SKU.
 *
 * Una recepción puede consolidar VARIOS packing lists. Pasa cuando llegan dos
 * embarques cortos el mismo día, o cuando uno se parte. Validarlos por separado
 * obliga a recorrer el almacén dos veces para la misma mercadería.
 *
 * Cada línea guarda de qué lista viene (`origen`), y el informe final se genera
 * por lista: cada una entrega exactamente las filas que trajo. El agregado por
 * SKU sí es común —se cuenta una vez— y por eso se SUMA en vez de sobrescribir.
 *
 * Firestore admite 500 operaciones por lote, así que se parte en tandas. Las
 * líneas son inmutables: son la versión del sistema contra la que se compara.
 */
/**
 * ¿Este packing list ya está cargado en otra recepción?
 *
 * Un archivo reenviado por correo, renombrado con la fecha o guardado dos veces
 * acaba validándose dos veces: dos operarios contando lo mismo, dos informes que
 * no cuadran y nadie sabiendo cuál mandar al cliente.
 *
 * Se mira por tres caminos, porque un duplicado se disfraza de formas distintas:
 * el contenido exacto, las cifras del archivo (líneas, productos y unidades) y
 * el nombre. Tres consultas pequeñas, una sola vez al cargar.
 *
 * Avisa; no bloquea. Recibir dos veces la misma mercancía existe, y el que está
 * delante lo sabe y la máquina no.
 */
export async function buscarPackingListParecido(resultado, archivo, opciones = {}) {
  if (modoLocal()) {
    // El servidor devuelve los candidatos; el parecido se calcula aquí, con la
    // MISMA función que en la nube. Si el criterio viviera en los dos lados,
    // dos operarios podrían ver avisos distintos del mismo archivo.
    const mio = resumenDe(resultado, archivo);
    const excluir = opciones.excluirRecepcion || '';
    const ORDEN = { identico: 3, probable: 2, revisar: 1, distinto: 0 };
    return (await local.buscarPackingListParecido(mio, opciones))
      .map((h) => ({ ...h, recepcionId: h.recepcion || h.recepcionId }))
      .filter((h) => h.recepcionId && h.recepcionId !== excluir)
      .map((h) => ({ ...h, ...comparar(mio, h) }))
      .filter((h) => h.nivel !== 'distinto')
      .sort((a, b) => ORDEN[b.nivel] - ORDEN[a.nivel])
      .slice(0, 5);
  }
  const mio = resumenDe(resultado, archivo);
  const excluir = opciones.excluirRecepcion || '';
  const col = collection(db, 'huellas');

  const consultas = [
    query(col, where('huella', '==', mio.huella), limit(5)),
    query(col, where('lineas', '==', mio.lineas), limit(25)),
  ];
  if (mio.archivo) consultas.push(query(col, where('archivo', '==', mio.archivo), limit(10)));

  const vistos = new Map();
  for (const q of consultas) {
    let snap;
    try {
      snap = await getDocs(q);
    } catch {
      // Sin el índice o sin permiso, cargar tiene que seguir funcionando: esto
      // es un aviso, no un requisito.
      continue;
    }
    snap.docs.forEach((d) => vistos.set(d.id, { id: d.id, ...d.data() }));
  }

  const ORDEN = { identico: 3, probable: 2, revisar: 1, distinto: 0 };
  return [...vistos.values()]
    .filter((h) => h.recepcionId && h.recepcionId !== excluir)
    .map((h) => ({ ...h, ...comparar(mio, h) }))
    .filter((h) => h.nivel !== 'distinto')
    .sort((a, b) => ORDEN[b.nivel] - ORDEN[a.nivel])
    .slice(0, 5);
}

/** La ficha que deja un packing list cargado, para reconocerlo la próxima vez. */
async function anotarHuella(recepcionId, codigo, origen, resumen) {
  try {
    await setDoc(doc(db, 'huellas', `${recepcionId}__${claveMapa(origen)}`), {
      ...resumen,
      recepcionId,
      codigo: codigo || recepcionId,
      origen,
      cargadoEn: serverTimestamp(),
    });
  } catch {
    // Que no se pueda anotar no puede tumbar una carga que ya se hizo. Lo único
    // que se pierde es el aviso de duplicado la próxima vez.
  }
}

export async function guardarPackingList(recepcionId, resultado, alAvanzar, opciones = {}) {
  if (modoLocal()) {
    return local.guardarPackingList(recepcionId, resultado, alAvanzar, {
      ...opciones, resumen: resumenDe(resultado, opciones.archivo),
    });
  }
  const refRec = doc(db, 'recepciones', recepcionId);
  const origen = limpiar(opciones.origen).toUpperCase().slice(0, 40) || 'PRINCIPAL';
  const previo = (await getDoc(refRec)).data() || {};
  const yaHabia = previo.totales || { lineas: 0, skus: 0, unidades: 0 };
  const origenes = previo.origenes || [];

  if (origenes.includes(origen)) {
    throw new Error(
      `Ya se cargó un packing list con el nombre «${origen}» en esta recepción. ` +
      'Usa otro nombre para distinguirlos en el informe.',
    );
  }

  // El número de línea lleva el origen delante: así dos listas con una línea 1
  // no se pisan, y el orden dentro de cada una se conserva.
  const operaciones = resultado.lineas.map((l) => ({
    ref: doc(db, 'recepciones', recepcionId, 'lineas', `${origen}-${l.linea}`),
    datos: { ...l, origen, orden: yaHabia.lineas + l.linea, creadoEn: serverTimestamp() },
  }));

  // Lo esperado se acumula: el mismo SKU en dos listas se cuenta una sola vez,
  // contra la suma de las dos.
  const existentes = {};
  if (origenes.length) {
    const snap = await getDocs(collection(db, 'recepciones', recepcionId, 'skus'));
    snap.docs.forEach((d) => { existentes[d.id] = d.data(); });
  }

  Object.entries(resultado.porSku).forEach(([sku, esperado]) => {
    const primera = resultado.lineas.find((l) => l.sku === sku);
    const antes = existentes[sku];
    const total = aNumero(antes?.esperado, 0) + esperado;
    operaciones.push({
      ref: doc(db, 'recepciones', recepcionId, 'skus', sku),
      datos: {
        sku,
        descripcion: antes?.descripcion || primera?.descripcion || '',
        esperado: total,
        contado: aNumero(antes?.contado, 0),
        pallets: antes?.pallets || {},
        verificado: antes?.verificado === true,
        estado: estadoDe(total, aNumero(antes?.contado, 0), antes?.verificado === true),
        enPackingList: true,
        tienePnc: antes?.tienePnc === true,
        // En qué listas aparece: es lo que avisa de un SKU compartido.
        origenes: [...new Set([...(antes?.origenes || []), origen])],
        // Y cuánto declara cada una, para que el operario elija sabiendo.
        esperadoPorOrigen: {
          ...(antes?.esperadoPorOrigen || {}),
          [claveMapa(origen)]: esperado,
        },
        creadoEn: antes?.creadoEn || serverTimestamp(),
      },
    });
  });

  const TANDA = 450;
  for (let i = 0; i < operaciones.length; i += TANDA) {
    const lote = writeBatch(db);
    operaciones.slice(i, i + TANDA).forEach((o) => lote.set(o.ref, o.datos, { merge: true }));
    await lote.commit();
    if (alAvanzar) alAvanzar(Math.min(i + TANDA, operaciones.length), operaciones.length);
  }

  const skusTotales = new Set([
    ...Object.keys(existentes),
    ...Object.keys(resultado.porSku),
  ]).size;

  await updateDoc(refRec, {
    totales: {
      lineas: yaHabia.lineas + resultado.lineas.length,
      skus: skusTotales,
      unidades: aNumero(yaHabia.unidades, 0) + resultado.unidades,
    },
    origenes: [...origenes, origen],
    // Cuántas líneas trajo cada lista. Sin esto, que una consolidación haya
    // salido mal —una lista que piso a la otra, una que no llegó a guardarse—
    // no se nota hasta que falta media hoja en el informe.
    lineasPorOrigen: {
      ...(previo.lineasPorOrigen || {}),
      [claveMapa(origen)]: resultado.lineas.length,
    },
    // La cabecera original de cada lista, para devolver el archivo igual.
    formatos: {
      ...(previo.formatos || {}),
      [claveMapa(origen)]: {
        encabezados: resultado.encabezados || [],
        prefijo:resultado.prefijo||[],
        columnas: resultado.columnas || {},
        hoja: resultado.hoja || '',
        // Con qué archivo se cargó y qué traía: es lo que permite reconocerlo
        // si vuelve a subirse en otra recepción.
        ...resumenDe(resultado, opciones.archivo),
      },
    },
    hoja: resultado.hoja,
    embarques: [...new Set([...(previo.embarques || []), ...resultado.embarques])],
    packingListEn: serverTimestamp(),
  });

  // SKU que ya venían de otra lista: la atribución de lo contado entre listas
  // es una convención, no un hecho, y quien carga tiene que saberlo.
  const compartidos = Object.keys(resultado.porSku).filter((sku) => existentes[sku]);

  await anotarHuella(recepcionId, previo.codigo, origen,
                     resumenDe(resultado, opciones.archivo));

  return { origen, lineas: resultado.lineas.length, compartidos };
}

/**
 * Borra una recepción entera, con todo lo que cuelga de ella.
 *
 * Existe porque subir el archivo equivocado pasa, y una recepción vacía o de
 * demostración en el listado no es inofensiva: el operario no sabe cuál es la
 * buena, y acaba contando contra la que no era.
 *
 * Firestore no borra en cascada: hay que recorrer cada subcolección. Se hace en
 * lotes de 400 porque el límite es 500 operaciones.
 *
 * Es irreversible y se lleva por delante la bitácora y la auditoría. Por eso lo
 * puede hacer solo un administrador, y la pantalla exige escribir el código.
 */
export async function borrarRecepcion(recepcionId, alAvanzar) {
  if (modoLocal()) return local.borrarRecepcion(recepcionId, alAvanzar);
  // Qué listas trajo, ANTES de borrar el documento. Es lo único que se necesita
  // saber de él después, y sirve para borrar sus huellas por identificador
  // exacto en vez de buscarlas: borrar un documento que se nombra no necesita
  // permiso para listar la colección, y una consulta sí.
  let origenes = [];
  try {
    origenes = (await getDoc(doc(db, 'recepciones', recepcionId))).data()?.origenes || [];
  } catch { /* si no se puede leer, abajo queda la búsqueda como respaldo */ }

  // La recepción PRIMERO.
  //
  // Lo que el supervisor quiere es que desaparezca de la lista y que nadie
  // pueda entrar a contar en ella. Si se limpiaran antes las subcolecciones y
  // algo fallara a mitad, la recepción seguiría ahí, accesible, y con parte de
  // sus datos ya borrados: lo peor de los dos mundos.
  //
  // Borrando el documento primero, un fallo posterior solo deja registros
  // huérfanos, que no estorban a nadie y se informan.
  await deleteDoc(doc(db, 'recepciones', recepcionId));

  const subcolecciones = ['eventos', 'lineas', 'skus', 'adicionales', 'auditoria'];
  let borrados = 0;
  const huerfanas = [];

  for (const nombre of subcolecciones) {
    try {
      const snap = await getDocs(collection(db, 'recepciones', recepcionId, nombre));
      for (let i = 0; i < snap.docs.length; i += 400) {
        const lote = writeBatch(db);
        snap.docs.slice(i, i + 400).forEach((d) => lote.delete(d.ref));
        await lote.commit();
        borrados += Math.min(400, snap.docs.length - i);
        if (alAvanzar) alAvanzar(borrados, nombre);
      }
    } catch {
      huerfanas.push(nombre);
    }
  }

  // Las huellas de sus packing lists se van con ella: si la recepción se borró
  // porque el archivo estaba mal, volver a subirlo bien no puede saltar como
  // «ya validado en» una recepción que ya no existe.
  let huellasSueltas = false;
  for (const origen of origenes) {
    try {
      await deleteDoc(doc(db, 'huellas', `${recepcionId}__${claveMapa(origen)}`));
      borrados++;
    } catch { huellasSueltas = true; }
  }

  // Respaldo para lo que no se pueda nombrar: una recepción cuyo documento ya no
  // se pudo leer, o una huella de antes de que se guardaran los orígenes.
  try {
    const snap = await getDocs(query(collection(db, 'huellas'),
                                     where('recepcionId', '==', recepcionId)));
    if (snap.docs.length) {
      const lote = writeBatch(db);
      snap.docs.forEach((d) => lote.delete(d.ref));
      await lote.commit();
      borrados += snap.docs.length;
    }
  } catch {
    // Solo es un problema si quedó algo de verdad. Si las huellas ya se
    // borraron una por una, que la búsqueda no esté permitida da igual.
    if (huellasSueltas || !origenes.length) huerfanas.push('huellas');
  }

  return { borrados, huerfanas };
}

export async function listarRecepciones(max = 50) {
  if (modoLocal()) return local.listarRecepciones(max);
  const q = query(collection(db, 'recepciones'), orderBy('creadoEn', 'desc'), limit(max));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

/**
 * Las recepciones en las que ha trabajado este operario.
 *
 * Sale de la lista que la recepción guarda, no de recorrer la bitácora: eso
 * costaría una lectura por conteo de la jornada.
 *
 * Se ordena aquí y no en la consulta para no obligar a crear un índice
 * compuesto en Firestore: son pocas decenas de recepciones y el orden en el
 * navegador es gratis.
 */
export async function listarMisRecepciones(uid, max = 60) {
  if (modoLocal()) return local.listarMisRecepciones(uid, max);
  if (!uid) return [];
  const snap = await getDocs(query(
    collection(db, 'recepciones'),
    where('operarios', 'array-contains', uid),
    limit(max),
  ));
  return snap.docs
    .map((d) => ({ id: d.id, ...d.data() }))
    .sort((a, b) => (b.creadoEn?.toMillis?.() || 0) - (a.creadoEn?.toMillis?.() || 0));
}

export async function obtenerRecepcion(id) {
  if (modoLocal()) return local.obtenerRecepcion(id);
  const snap = await getDoc(doc(db, 'recepciones', id));
  if (!snap.exists()) throw new Error('La recepción no existe.');
  return { id: snap.id, ...snap.data() };
}

/** Escucha los SKU en tiempo real: lo que cuenta un operario lo ven los demás. */
export function escucharSkus(recepcionId, alCambiar, alFallar) {
  if (modoLocal()) return local.escucharSkus(recepcionId, alCambiar, alFallar);
  return onSnapshot(
    collection(db, 'recepciones', recepcionId, 'skus'),
    (snap) => alCambiar(snap.docs.map((d) => ({ id: d.id, ...d.data() }))),
    (e) => alFallar && alFallar(e),
  );
}

export async function cerrarRecepcion(recepcionId) {
  if (modoLocal()) return local.cerrarRecepcion(recepcionId);
  await updateDoc(doc(db, 'recepciones', recepcionId), {
    estado: 'CERRADA',
    cerradoEn: serverTimestamp(),
  });
}

/**
 * Reabre una recepción cerrada.
 *
 * Cerrar por error, o descubrir al día siguiente que faltó contar un pallet,
 * pasa. La alternativa —crear una recepción nueva con el mismo packing list—
 * parte el historial en dos y deja dos informes del mismo embarque.
 *
 * No borra nada: los conteos siguen donde estaban y el cierre anterior queda
 * en la auditoría. Lo que cambia es que vuelve a admitir conteos.
 */
export async function reabrirRecepcion(recepcionId) {
  if (modoLocal()) return local.reabrirRecepcion(recepcionId);
  await updateDoc(doc(db, 'recepciones', recepcionId), {
    estado: 'EN_VALIDACION',
    reabiertoEn: serverTimestamp(),
  });
}

// --------------------------------------------------------------------------- //
// Catálogo
// --------------------------------------------------------------------------- //

/**
 * Guarda el catálogo del WMS en Firestore.
 *
 * Esto es el precalentado: se hace una vez por recepción y convierte cada
 * escaneo en la lectura de un documento, en vez de una llamada al WMS.
 */
export async function guardarCatalogo(productos, alAvanzar) {
  if (modoLocal()) return local.guardarCatalogo(productos, alAvanzar);
  const TANDA = 200;   // cada producto son 2 escrituras: producto + código
  for (let i = 0; i < productos.length; i += TANDA) {
    const lote = writeBatch(db);
    for (const p of productos.slice(i, i + TANDA)) {
      if (!p.sku) continue;
      lote.set(doc(db, 'productos', p.sku), {
        sku: p.sku,
        descripcion: p.descripcion || '',
        unidad: p.unidad || null,
        stock: p.stock ?? null,
        posicion: p.posicion || null,
        // Todas las ubicaciones donde el WMS tiene existencia de este producto.
        // Se recorta a 20: un SKU repartido en más sitios ya no se decide
        // mirando una lista, y veinte ya llenan la pantalla de un handheld.
        posiciones: (p.posiciones || []).slice(0, 30).map((u) => ({
          posicion: u.posicion || '',
          stock: aNumero(u.stock, 0),
          lote: u.lote || null,
          serie: u.serie || null,
          partida: u.partida || null,
          estado: u.estado || null,
        })),
        familia: p.familia || null,
        cliente: p.cliente || p.codCliente || null,
        actualizadoEn: serverTimestamp(),
      }, { merge: true });

      lote.set(doc(db, 'codigos', p.sku), {
        sku: p.sku, tipo: 'SKU', vigente: true, actualizadoEn: serverTimestamp(),
      }, { merge: true });
    }
    await lote.commit();
    if (alAvanzar) alAvanzar(Math.min(i + TANDA, productos.length), productos.length);
  }
}

/**
 * Las ubicaciones de un producto, venga como venga del catálogo.
 *
 * El catálogo guardaba UNA sola posición por SKU hasta hace poco. Un catálogo
 * descargado antes de ese cambio no trae el array `posiciones`, solo `posicion`
 * y `stock`: leyendo únicamente el array, la ficha decía «sin existencia en
 * bodega» mientras la línea de arriba mostraba la posición. Dos afirmaciones
 * contrarias en la misma pantalla, y el operario sin saber a cuál hacer caso.
 */
export function ubicacionesDepot(producto) {
  const nuevas = (producto?.posiciones || []).filter((u) => u && u.posicion);
  if (nuevas.length) return nuevas;
  return producto?.posicion
    ? [{ posicion: producto.posicion, stock: aNumero(producto.stock, 0) }]
    : [];
}

/** Resuelve un código contra el catálogo local. Una lectura, sin red al WMS. */
export async function buscarEnCatalogo(codigo) {
  if (modoLocal()) return local.buscarEnCatalogo(codigo);
  const c = normalizarCodigo(codigo);
  if (!c) return null;

  const idx = await getDoc(doc(db, 'codigos', c));
  const sku = idx.exists() ? idx.get('sku') : c;

  const prod = await getDoc(doc(db, 'productos', sku));
  if (!prod.exists()) return null;
  return { sku, ...prod.data(), codigoVigente: idx.exists() ? idx.get('vigente') !== false : true };
}

/** Equivalencia código escaneado → SKU, cuando el WMS no la conoce. */
export async function registrarEquivalencia(codigo, sku, usuario) {
  if (modoLocal()) return local.registrarEquivalencia(codigo, sku, usuario);
  const c = normalizarCodigo(codigo);
  if (!c || !sku) return;
  await setDoc(doc(db, 'codigos', c), {
    sku: normalizarCodigo(sku),
    tipo: 'EAN',
    vigente: true,
    registradoPorUid: usuario.uid,
    registradoPorEmail: usuario.email,
    actualizadoEn: serverTimestamp(),
  }, { merge: true });
}
