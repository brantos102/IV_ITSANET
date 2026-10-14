/**
 * Diálogos propios, en lugar de confirm() y prompt() del navegador.
 *
 * En el handheld los del navegador son el peor sitio posible para una decisión
 * que no se puede deshacer: salen diminutos, sin contexto, se cierran de un
 * toque accidental, y en algunos navegadores de Android prompt() está
 * directamente desactivado — el operario pulsa «Anular» y no pasa nada.
 *
 * Además no caben: cerrar una recepción enseña siete cifras, y un confirm()
 * las mete todas en un párrafo gris sin jerarquía, con «Aceptar» y «Cancelar»
 * que no dicen qué va a pasar.
 *
 * Se usa <dialog> nativo: trae Escape, el fondo y el foco atrapado sin
 * reimplementarlos. Todas las funciones devuelven una promesa y ninguna lanza:
 * cancelar es una respuesta, no un error.
 */

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** El <dialog>, creado una vez y reutilizado. */
function caja() {
  let d = document.getElementById('modal');
  if (!d) {
    d = document.createElement('dialog');
    d.id = 'modal';
    d.className = 'modal';
    document.body.appendChild(d);
  }
  return d;
}

/**
 * Abre el diálogo y espera. `armar` recibe el elemento y una función para
 * responder; lo que le pase es lo que devuelve la promesa.
 */
function abrir(html, armar) {
  const d = caja();
  d.innerHTML = html;

  return new Promise((resolver) => {
    let respuesta;                       // undefined = se cerró sin elegir
    const cerrar = (valor) => { respuesta = valor; d.close(); };

    d.addEventListener('close', () => {
      d.innerHTML = '';
      resolver(respuesta);
    }, { once: true });

    // Tocar fuera del recuadro cierra sin elegir, como el fondo de cualquier
    // modal. No vale con escuchar el click del <dialog>: ese también salta
    // desde dentro.
    d.addEventListener('click', (ev) => { if (ev.target === d) cerrar(undefined); });

    armar(d, cerrar);

    if (typeof d.showModal === 'function') d.showModal();
    else d.setAttribute('open', '');     // navegador antiguo: al menos se ve
  });
}

/**
 * ¿Hay un diálogo abierto ahora mismo?
 *
 * Lo necesita quien escucha teclas globales: con un diálogo abierto, Escape es
 * del diálogo. Sin esto, cancelar una confirmación también reseteaba la ficha
 * del operario y le borraba lo que había escrito.
 */
export const modalAbierto = () => !!document.getElementById('modal')?.open;

const cabecera = (titulo, texto) =>
  `<h3 class="modal-titulo">${esc(titulo)}</h3>` +
  (texto ? `<div class="modal-texto">${texto}</div>` : '');

/**
 * Sí o no. Devuelve true solo si se pulsó el botón de aceptar: cerrar con
 * Escape, tocar fuera o cancelar devuelven false.
 *
 * `peligro` pinta el botón de aceptar en rojo, para lo que no se deshace.
 */
export function confirmar({ titulo, texto = '', aceptar = 'Aceptar',
                            cancelar = 'Cancelar', peligro = false } = {}) {
  return abrir(
    `${cabecera(titulo, texto)}
     <div class="modal-acciones">
       <button type="button" class="b-sec" data-no>${esc(cancelar)}</button>
       <button type="button" class="${peligro ? 'b-peligro-lleno' : 'b-primario'}" data-si>
         ${esc(aceptar)}</button>
     </div>`,
    (d, cerrar) => {
      d.querySelector('[data-no]').onclick = () => cerrar(false);
      d.querySelector('[data-si]').onclick = () => cerrar(true);
      d.querySelector('[data-si]').focus();
    },
  ).then((r) => r === true);
}

/**
 * Pide un texto. Devuelve null si se canceló —distinto de '' — para que quien
 * llama pueda separar «no quiso» de «lo dejó vacío».
 *
 * Con `obligatorio`, el botón no deja seguir hasta que haya algo escrito: el
 * motivo de una anulación en blanco no sirve para nada seis meses después.
 */
export function pedirTexto({ titulo, texto = '', etiqueta = '', valor = '',
                             marcador = '', obligatorio = false,
                             aceptar = 'Aceptar', cancelar = 'Cancelar',
                             lineas = 1 } = {}) {
  const campo = lineas > 1
    ? `<textarea id="modalCampo" rows="${lineas}" placeholder="${esc(marcador)}">${esc(valor)}</textarea>`
    : `<input id="modalCampo" value="${esc(valor)}" placeholder="${esc(marcador)}"
              autocomplete="off" enterkeyhint="done">`;

  return abrir(
    `${cabecera(titulo, texto)}
     <label class="campo">${etiqueta ? `<span>${esc(etiqueta)}</span>` : ''}${campo}</label>
     <div class="modal-acciones">
       <button type="button" class="b-sec" data-no>${esc(cancelar)}</button>
       <button type="button" class="b-primario" data-si>${esc(aceptar)}</button>
     </div>`,
    (d, cerrar) => {
      const campoEl = d.querySelector('#modalCampo');
      const si = d.querySelector('[data-si]');
      const revisar = () => { si.disabled = obligatorio && !campoEl.value.trim(); };

      campoEl.addEventListener('input', revisar);
      campoEl.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && lineas === 1) { ev.preventDefault(); si.click(); }
      });
      d.querySelector('[data-no]').onclick = () => cerrar(null);
      si.onclick = () => { if (!si.disabled) cerrar(campoEl.value); };

      revisar();
      campoEl.focus();
      campoEl.select?.();
    },
  ).then((r) => (r === undefined ? null : r));
}

/**
 * Elegir entre varias opciones, cada una con su explicación.
 *
 * Es lo que un confirm() no puede hacer: «Aceptar = auditable / Cancelar = solo
 * el packing list» obliga a traducir mentalmente dos botones genéricos a dos
 * cosas distintas, y se elige mal.
 *
 * `opciones`: [{ valor, titulo, detalle }]. Devuelve el valor, o null.
 */
export function elegir({ titulo, texto = '', opciones = [],
                         cancelar = 'Cancelar' } = {}) {
  return abrir(
    `${cabecera(titulo, texto)}
     <div class="modal-opciones">
       ${opciones.map((o, i) => `
         <button type="button" class="modal-opcion" data-valor="${i}">
           <b>${esc(o.titulo)}</b>
           ${o.detalle ? `<span>${esc(o.detalle)}</span>` : ''}
         </button>`).join('')}
     </div>
     <div class="modal-acciones">
       <button type="button" class="b-sec" data-no>${esc(cancelar)}</button>
     </div>`,
    (d, cerrar) => {
      d.querySelectorAll('[data-valor]').forEach((b) => {
        b.onclick = () => cerrar(opciones[Number(b.dataset.valor)].valor);
      });
      d.querySelector('[data-no]').onclick = () => cerrar(null);
      d.querySelector('[data-valor]')?.focus();
    },
  ).then((r) => (r === undefined ? null : r));
}

/**
 * Enseñar algo y esperar a que se cierre.
 *
 * Para la novedad que no se puede pasar por alto —un sobrante registrado, una
 * referencia que no apareció—: el aviso en la página se va de la vista en
 * cuanto se escanea lo siguiente, y en el handheld eso es un segundo después.
 */
export function avisarModal({ titulo, texto = '', tono = 'info',
                              aceptar = 'Entendido' } = {}) {
  return abrir(
    `<div class="modal-tono ${esc(tono)}"></div>
     ${cabecera(titulo, texto)}
     <div class="modal-acciones">
       <button type="button" class="b-primario" data-si>${esc(aceptar)}</button>
     </div>`,
    (d, cerrar) => {
      d.querySelector('[data-si]').onclick = () => cerrar(true);
      d.querySelector('[data-si]').focus();
    },
  ).then(() => undefined);
}

/**
 * Confirmación escribiendo algo exacto, para lo irreversible.
 *
 * Un «¿seguro?» se acepta sin leer. Escribir el código obliga a mirar cuál es.
 * Lo que hay que escribir va en su propia línea y al final: cuando estaba
 * arriba, se escribía la descripción que venía después.
 */
export function confirmarEscribiendo({ titulo, texto = '', exacto,
                                       etiqueta = 'Escríbelo para confirmar',
                                       aceptar = 'Borrar' } = {}) {
  return abrir(
    `${cabecera(titulo, texto)}
     <p class="modal-exacto">${esc(exacto)}</p>
     <label class="campo"><span>${esc(etiqueta)}</span>
       <input id="modalCampo" autocomplete="off" autocapitalize="characters"
              spellcheck="false"></label>
     <div class="modal-acciones">
       <button type="button" class="b-sec" data-no>Cancelar</button>
       <button type="button" class="b-peligro-lleno" data-si disabled>${esc(aceptar)}</button>
     </div>`,
    (d, cerrar) => {
      const campoEl = d.querySelector('#modalCampo');
      const si = d.querySelector('[data-si]');
      const igual = () =>
        campoEl.value.trim().toUpperCase() === String(exacto).trim().toUpperCase();

      campoEl.addEventListener('input', () => { si.disabled = !igual(); });
      campoEl.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') { ev.preventDefault(); if (igual()) si.click(); }
      });
      d.querySelector('[data-no]').onclick = () => cerrar(false);
      si.onclick = () => { if (igual()) cerrar(true); };
      campoEl.focus();
    },
  ).then((r) => r === true);
}
