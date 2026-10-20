/**
 * Cómo se llaman las cosas en Drive.
 *
 * Un archivo que se llama «validacion.xlsx» es inencontrable a los tres meses, y
 * lo que se guarda aquí es justo lo que hay que sacar cuando alguien reclama:
 * meses después, por teléfono, sin saber el código de memoria.
 *
 * Las reglas, en orden de importancia:
 *
 *  1. **La fecha primero.** Drive ordena por nombre, así que empezar por
 *     AAAA-MM-DD es lo único que hace que la carpeta se recorra como un
 *     calendario en vez de como un montón.
 *  2. **El cliente después.** Dos clientes el mismo día quedan separados y
 *     juntos entre sí; buscar «VENTURA» los encuentra todos.
 *  3. **El código al final.** Es lo único único de verdad: dos recepciones del
 *     mismo cliente el mismo día se distinguen por él y por nada más.
 *
 * Y lo mismo en el nombre del archivo, aunque dentro de su carpeta parezca
 * repetido: el archivo viaja. Se adjunta a un correo, se descarga, se reenvía.
 * Fuera de la carpeta, el nombre es todo lo que queda.
 */

/** Sin lo que Drive, Windows o un correo tratan de forma especial. */
export function limpiarNombre(v) {
  return String(v ?? '')
    .replace(/[\\/:*?"<>|#%{}~\[\]]/g, '')   // prohibidos o problemáticos
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\s/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

/** AAAA-MM-DD de una fecha de Firestore, un Date o un texto. */
export function soloFecha(valor) {
  if (!valor) return new Date().toISOString().slice(0, 10);
  const d = typeof valor?.toDate === 'function' ? valor.toDate()
    : valor instanceof Date ? valor
      : new Date(valor);
  return Number.isNaN(d.getTime())
    ? new Date().toISOString().slice(0, 10)
    : d.toISOString().slice(0, 10);
}

/**
 * La fecha de la recepción es la de su creación, no la de hoy.
 *
 * Una recepción que se abre el viernes y se cierra el lunes pertenece al
 * viernes: es cuando llegó la mercadería. Si se usara la fecha del cierre, el
 * archivo caería en otro mes que el de su propia carpeta.
 */
export const fechaDeRecepcion = (rec) => soloFecha(rec?.creadoEn);

/** El mes al que pertenece, para no dejar cientos de carpetas al mismo nivel. */
export const carpetaDeMes = (rec) => fechaDeRecepcion(rec).slice(0, 7);

/** «2026-03-01_VENTURA_REC0260002» */
export function carpetaDeRecepcion(rec) {
  const partes = [
    fechaDeRecepcion(rec),
    limpiarNombre(rec?.cliente) || 'SIN-CLIENTE',
    limpiarNombre(rec?.codigo) || 'SIN-CODIGO',
  ];
  return partes.join('_');
}

/** Dentro de cada recepción, las fotos aparte de los documentos. */
export const CARPETA_IMAGENES = 'imagenes';

/**
 * El nombre de un informe.
 *
 * `origen` es el packing list cuando la recepción consolida varios: entonces
 * sale un archivo por lista, y cada uno tiene que decir cuál es. Quien recibe
 * dos adjuntos no puede estar abriéndolos para saber cuál es cuál.
 *
 * `version` numera los cierres: una recepción reabierta y vuelta a cerrar genera
 * otro informe, y el anterior no se pisa porque puede que ya se haya entregado.
 * Se escribe v2, v3… en vez de «(2)», que es lo que pone el explorador cuando
 * algo se duplicó sin querer y aquí no es el caso.
 */
export function nombreDeInforme(rec, opciones = {}) {
  const { origen = '', version = 1, auditable = false } = opciones;
  const partes = [carpetaDeRecepcion(rec)];
  if (origen && origen !== 'PRINCIPAL') partes.push(limpiarNombre(origen));
  if (auditable) partes.push('AUDITABLE');
  if (version > 1) partes.push('v' + version);
  return partes.join('_');
}

/** Archivos nuevos: propósito, cliente, recepción y grupo, sin repetir el embarque. */
export function nombreInformeOperativo(rec,{origen='',embarque='',auditable=false}={}){
  const codigo=limpiarNombre(rec?.codigo)||'SIN-CODIGO';
  const partes=[auditable?'Auditoria':'Validacion',(limpiarNombre(rec?.cliente)||'SIN-CLIENTE').slice(0,24),codigo];
  for(const [prefijo,valor] of [['EMB',embarque],['PL',origen]]){
    const limpio=limpiarNombre(valor);
    if(limpio&&limpio!=='PRINCIPAL'&&!partes.some(p=>p.toUpperCase().includes(limpio.toUpperCase())))partes.push(prefijo+'-'+limpio);
  }
  return partes.join('_');
}

/**
 * El nombre de una foto: el código y su número.
 *
 * El código va delante para poder comprobar de un vistazo que la evidencia es
 * del producto que dice ser, que es justo lo que se mira en una reclamación.
 * Dos fotos del mismo producto se numeran; nunca se pisa una.
 */
export function nombreDeFoto(sku, numero = 1, tipo = 'image/jpeg') {
  const ext = String(tipo).includes('png') ? 'png' : 'jpg';
  return `${limpiarNombre(sku) || 'SIN-CODIGO'}-${numero}.${ext}`;
}

/**
 * El siguiente número libre para las fotos de un producto.
 *
 * `existentes` son los nombres que ya hay en la carpeta. Se mira el número real
 * de cada uno en vez de contar archivos: si se borró la 1, la siguiente tiene
 * que ser la 3 y no otra 2 que pisaría a la que queda.
 */
export function siguienteFoto(sku, existentes = []) {
  const base = limpiarNombre(sku) || 'SIN-CODIGO';
  const patron = new RegExp(`^${base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}-(\\d+)\\.`, 'i');
  const usados = existentes
    .map((n) => (String(n).match(patron) || [])[1])
    .filter(Boolean)
    .map(Number);
  return usados.length ? Math.max(...usados) + 1 : 1;
}
