/**
 * Cómo se llama cada cosa, en un solo sitio.
 *
 * «Unid. sistema» no le dice nada a quien está delante de un pallet. El que
 * escribe la app sabe que es «lo que declara el packing list», pero esa
 * traducción vive en su cabeza y no en la pantalla.
 *
 * Aquí está el vocabulario y su explicación. Las pantallas tiran de esto, así
 * que cambiar un nombre lo cambia en todas a la vez y no quedan dos palabras
 * para lo mismo.
 */

export const TERMINOS = {
  recepcion: {
    titulo: 'Recepción',
    corto: 'Recepción',
    ayuda: 'Una llegada de mercadería que se valida de una vez. Puede juntar ' +
           'varios packing lists si llegaron el mismo día.',
  },
  codigoRecepcion: {
    titulo: 'Código de recepción',
    corto: 'Código',
    ayuda: 'El nombre corto con el que la buscarás después. Conviene que lleve ' +
           'el cliente y la fecha: VW-29-06-2026, GAC-01-06. Sin espacios ni ' +
           'caracteres raros, y no se puede repetir.',
  },
  packingList: {
    titulo: 'Packing list',
    corto: 'Lista',
    ayuda: 'El archivo que manda el cliente con lo que dice que envió. Es la ' +
           'versión del sistema contra la que se compara lo que de verdad llegó.',
  },
  declarado: {
    titulo: 'Declarado',
    corto: 'Declarado',
    ayuda: 'Las unidades que dice el packing list. No se tocan nunca: es lo que ' +
           'el cliente afirma haber enviado.',
  },
  contado: {
    titulo: 'Contado',
    corto: 'Contado',
    ayuda: 'Las unidades que aparecieron físicamente, sumando lo que registró ' +
           'cada operario.',
  },
  diferencia: {
    titulo: 'Diferencia',
    corto: 'Dif.',
    ayuda: 'Contado menos declarado. En negativo falta mercadería; en positivo ' +
           'llegó de más.',
  },
  verificado: {
    titulo: 'Verificado',
    corto: 'Verificado',
    ayuda: 'Qué parte de lo declarado ya se comprobó físicamente. El tope se ' +
           'aplica por referencia, así que contar de más en un producto no tapa ' +
           'lo que falta en otro.',
  },
  exactitud: {
    titulo: 'Exactitud',
    corto: 'Exactitud',
    ayuda: 'Porcentaje de referencias que cuadraron a la primera. Es lo que se ' +
           'reclama al proveedor.',
  },
  pallet: {
    titulo: 'Pallet',
    corto: 'Pallet',
    ayuda: 'Dónde se dejó la mercadería mientras se valida: A1, B04, B04.1 para ' +
           'un subpallet. Para lo que va directo a su ubicación sin armar ' +
           'pallet, DP.',
  },
  posicionReal: {
    titulo: 'Posición real asignada',
    corto: 'Posición',
    ayuda: 'La ubicación del almacén donde quedó de verdad: A-01-03-2. Es la que ' +
           'sirve para buscarlo después. El pallet dice cómo se movió; la ' +
           'posición, dónde está.',
  },
  pnc: {
    titulo: 'PNC — producto no conforme',
    corto: 'PNC',
    ayuda: 'Llegó dañado, mojado, abierto o incompleto. Exige una nota y conviene ' +
           'una foto: sin evidencia no se le puede reclamar a nadie.',
  },
  adicional: {
    titulo: 'Adicional',
    corto: 'Adicional',
    ayuda: 'Algo que llegó físicamente sin estar en el packing list. No se añade ' +
           'a la lista: va en una hoja aparte del informe.',
  },
  sinBuscar: {
    titulo: 'Sin buscar',
    corto: 'Sin buscar',
    ayuda: 'Nadie ha tocado esa referencia todavía. Es trabajo pendiente, no un ' +
           'faltante: no se puede cerrar la recepción dejando ninguna así.',
  },
  noAparecio: {
    titulo: 'No apareció',
    corto: 'No apareció',
    ayuda: 'Se buscó y no estaba, y alguien lo declaró con su nota. Eso sí es un ' +
           'faltante confirmado, y se puede reclamar.',
  },
  sobrante: {
    titulo: 'Sobran unidades',
    corto: 'Sobrante',
    ayuda: 'Llegó más de lo declarado. Hay que confirmarlo al registrarlo, para ' +
           'que no entre por un escaneo de más.',
  },
  catalogo: {
    titulo: 'Catálogo de Depot',
    corto: 'Catálogo',
    ayuda: 'Una copia del stock del cliente, descargada de una vez. Con ella cada ' +
           'escaneo es instantáneo en lugar de una consulta al WMS. Conviene ' +
           'bajarlo una vez al día.',
  },
};

/** Marca un elemento para que al tocarlo explique el término. */
export function ayudaDe(clave) {
  const t = TERMINOS[clave];
  if (!t) return '';
  return ` <button type="button" class="ayuda" data-termino="${clave}"
            aria-label="Qué significa ${t.titulo}" title="${t.ayuda}">?</button>`;
}

/**
 * Conecta la ayuda de la página.
 *
 * Un solo oyente en el documento: los términos aparecen y desaparecen al
 * repintar tablas, y reconectarlos uno a uno acaba olvidando alguno.
 */
export function conectarAyuda(mostrar) {
  document.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-termino]');
    if (!b) return;
    const t = TERMINOS[b.dataset.termino];
    if (t) mostrar(t.titulo, t.ayuda);
  });
}

/** Todo el glosario, para la pantalla de ayuda. */
export const listaGlosario = () => Object.values(TERMINOS);
