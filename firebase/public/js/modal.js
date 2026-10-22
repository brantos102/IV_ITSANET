import {agregarDesglosePosicion} from './posiciones.js?v=20261021-62';
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

/** Enter avanza por los campos; al final ejecuta la acción indicada.
 * Textareas conservan saltos de línea (Ctrl+Enter confirma). Los botones y
 * selectores mantienen su teclado nativo; nunca se elige una acción destructiva
 * por deducirla de su color o posición.
 */
export function tecladoDialogo(d, {accion, campos='input:not([type=hidden]):not([type=file]),select,textarea'}={}) {
  d.addEventListener('keydown', ev=>{
    if(ev.key!=='Enter'||ev.defaultPrevented||ev.isComposing||ev.repeat||ev.altKey||ev.metaKey||ev.shiftKey)return;
    const e=ev.target;
    if(e.closest('button,a,[contenteditable=true]')||e.tagName==='SELECT'&&!ev.ctrlKey)return;
    if(e.tagName==='TEXTAREA'&&!ev.ctrlKey)return;
    if(!e.matches(campos))return;
    ev.preventDefault();ev.stopPropagation();
    if(!e.reportValidity())return;
    const entradas=[...d.querySelectorAll(campos)].filter(x=>!x.disabled&&!x.readOnly&&x.getClientRects().length);
    const siguiente=entradas[entradas.indexOf(e)+1];
    if(siguiente&&!ev.ctrlKey){siguiente.focus();siguiente.select?.();return;}
    const invalido=entradas.find(x=>!x.checkValidity());
    if(invalido){invalido.focus();invalido.reportValidity();return;}
    const b=typeof accion==='string'?d.querySelector(accion):accion;
    if(b&&!b.disabled&&!b.hidden)b.click();
  });
}

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
    d.onclick = (ev) => { if (ev.target === d) cerrar(undefined); };

    if (typeof d.showModal === 'function') d.showModal();
    else d.setAttribute('open', '');     // navegador antiguo: al menos se ve
    // El foco se asigna después de mostrar: un elemento de un dialog cerrado
    // no puede recibirlo y Enter acababa en el botón Cancelar.
    armar(d, cerrar);
  });
}

/**
 * ¿Hay un diálogo abierto ahora mismo?
 *
 * Lo necesita quien escucha teclas globales: con un diálogo abierto, Escape es
 * del diálogo. Sin esto, cancelar una confirmación también reseteaba la ficha
 * del operario y le borraba lo que había escrito.
 */
export const modalAbierto = () => !!document.querySelector('dialog[open]');

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
 * Con `seleccion` añade una lista y devuelve {texto, seleccion}; sin ella
 * mantiene el resultado de texto. Una opción deshabilitada no permite aceptar.
 */
export function pedirTexto({ titulo, texto = '', etiqueta = '', valor = '',
                             marcador = '', obligatorio = false,
                             aceptar = 'Aceptar', cancelar = 'Cancelar',
                             lineas = 1, sugerencias = [], seleccion = null } = {}) {
  const campo = lineas > 1
    ? `<textarea id="modalCampo" rows="${lineas}" placeholder="${esc(marcador)}">${esc(valor)}</textarea>`
    : `<input id="modalCampo" value="${esc(valor)}" placeholder="${esc(marcador)}"
              autocomplete="off" enterkeyhint="done">`;

  return abrir(
    `${cabecera(titulo, texto)}
     ${seleccion ? `<label class="campo"><span>${esc(seleccion.etiqueta)}</span><select id="modalSeleccion">
       ${seleccion.opciones.map(o=>`<option value="${esc(o.valor)}"${o.valor===seleccion.valor?' selected':''}${o.disabled?' disabled':''}>${esc(o.titulo)}</option>`).join('')}
     </select></label>` : ''}
     <label class="campo">${etiqueta ? `<span>${esc(etiqueta)}</span>` : ''}${campo}</label>
     ${sugerencias.length ? `<div class="modal-sugerencias"><span class="mini">Destinatarios recientes de este cliente</span>
       ${sugerencias.map((s, i) => `<button type="button" class="b-sec" data-sugerencia="${i}">${esc(s)}</button>`).join('')}
       </div>` : ''}
     <div class="modal-acciones">
       <button type="button" class="b-sec" data-no>${esc(cancelar)}</button>
       <button type="button" class="b-primario" data-si>${esc(aceptar)}</button>
     </div>`,
    (d, cerrar) => {
      const campoEl = d.querySelector('#modalCampo');
      const si = d.querySelector('[data-si]');
      const lista = d.querySelector('#modalSeleccion');
      const revisar = () => { si.disabled = (obligatorio && !campoEl.value.trim()) || !!lista?.selectedOptions[0]?.disabled; };
      lista?.addEventListener('change', revisar);

      campoEl.addEventListener('input', revisar);
      d.querySelectorAll('[data-sugerencia]').forEach(b => {
        b.onclick = () => { campoEl.value = sugerencias[Number(b.dataset.sugerencia)]; revisar(); campoEl.focus(); };
      });
      campoEl.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && !ev.isComposing && !ev.repeat && (lineas === 1 || ev.ctrlKey)) { ev.preventDefault(); si.click(); }
      });
      d.querySelector('[data-no]').onclick = () => cerrar(null);
      si.onclick = () => { if (!si.disabled) cerrar(seleccion ? {texto:campoEl.value,seleccion:lista.value} : campoEl.value); };

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

/**
 * Pide varios datos a la vez: un formulario dentro del diálogo.
 *
 * Nace de editar un usuario. Con `pedirTexto` harían falta tres diálogos
 * seguidos —nombre, usuario, rol— y quien los contesta no ve en ningún momento
 * la ficha completa que está cambiando; además, cancelar el tercero dejaría los
 * dos primeros ya guardados. Aquí se ve todo junto y se guarda una sola vez.
 *
 * `campos`: [{ clave, etiqueta, valor, pista, obligatorio, tipo, opciones }]
 *   tipo 'lista'   -> <select> con `opciones`: [{ valor, titulo }]
 *   tipo 'interruptor' -> casilla; el valor viaja como booleano
 *   cualquier otro -> <input> de texto
 *
 * Devuelve un objeto { clave: valor } o null si se canceló. Las claves son las
 * que se pasaron: quien llama no tiene que volver a leer el DOM.
 */
export function pedirDatos({ titulo, texto = '', campos = [],
                             aceptar = 'Guardar', cancelar = 'Cancelar' } = {}) {
  const dibujar = (c) => {
    const id = `modalC_${c.clave}`;
    if (c.tipo === 'lista') {
      const ops = (c.opciones || []).map((o) =>
        `<option value="${esc(o.valor)}"${o.valor === c.valor ? ' selected' : ''}>${esc(o.titulo ?? o.valor)}</option>`).join('');
      return `<label class="campo"><span>${esc(c.etiqueta)}</span>
                <select id="${id}" data-clave="${esc(c.clave)}">${ops}</select>
                ${c.pista ? `<span class="mini">${esc(c.pista)}</span>` : ''}</label>`;
    }
    if (c.tipo === 'interruptor') {
      return `<label class="campo"><span>${esc(c.etiqueta)}</span>
                <select id="${id}" data-clave="${esc(c.clave)}" data-bool>
                  <option value="si"${c.valor ? ' selected' : ''}>Sí</option>
                  <option value="no"${c.valor ? '' : ' selected'}>No</option>
                </select>
                ${c.pista ? `<span class="mini">${esc(c.pista)}</span>` : ''}</label>`;
    }
    return `<label class="campo"><span>${esc(c.etiqueta)}</span>
              <input id="${id}" type="${c.tipo==='password'?'password':c.tipo==='email'?'email':c.tipo==='numero'?'number':'text'}" data-clave="${esc(c.clave)}" value="${esc(c.valor ?? '')}"
                     placeholder="${esc(c.marcador || '')}" autocomplete="off"
                     ${c.sugerencias?.length?'list="'+id+'_opciones"':''}
                     ${c.obligatorio ? 'data-obligatorio required' : ''}
                     autocapitalize="none" spellcheck="false">
              ${c.sugerencias?.length?'<datalist id="'+id+'_opciones">'+c.sugerencias.map(v=>'<option value="'+esc(v)+'"></option>').join('')+'</datalist>':''}
              ${c.pista ? `<span class="mini">${esc(c.pista)}</span>` : ''}</label>`;
  };

  return abrir(
    `${cabecera(titulo, texto)}
     <div class="rejilla">${campos.map(dibujar).join('')}</div>
     <div class="modal-acciones">
       <button type="button" class="b-sec" data-no>${esc(cancelar)}</button>
       <button type="button" class="b-primario" data-si>${esc(aceptar)}</button>
     </div>`,
    (d, cerrar) => {
      const entradas = Array.from(d.querySelectorAll('[data-clave]'));
      for(const c of campos)if(c.desglosarPosicion)agregarDesglosePosicion(d.querySelector('[data-clave="'+c.clave+'"]'));
      const si = d.querySelector('[data-si]');
      const revisar = () => {
        si.disabled = entradas.some((e) =>
          e.hasAttribute('data-obligatorio') && !e.value.trim());
      };

      entradas.forEach((e) => e.addEventListener('input', revisar));
      const teclado = ev=>{
        if(ev.key!=='Enter'||ev.isComposing||ev.repeat||ev.target.tagName!=='INPUT')return;
        ev.preventDefault();ev.stopPropagation();
        const indice=entradas.indexOf(ev.target),siguiente=entradas.slice(indice+1).find(e=>!e.disabled);
        if(siguiente){siguiente.focus();return;}
        revisar();if(!si.disabled)si.click();
        else entradas.find(e=>e.hasAttribute('data-obligatorio')&&!e.value.trim())?.focus();
      };
      entradas.forEach(e=>e.addEventListener('keydown',teclado));
      si.onclick = () => {
        if (si.disabled) return;
        const invalida=entradas.find(e=>!e.checkValidity());
        if(invalida){invalida.focus();invalida.reportValidity();return;}
        const datos = {};
        entradas.forEach((e) => {
          datos[e.dataset.clave] = e.hasAttribute('data-bool')
            ? e.value === 'si'
            : (e.value ?? '').trim();
        });
        cerrar(datos);
      };
      d.querySelector('[data-no]').onclick = () => cerrar(null);

      revisar();
      entradas[0]?.focus();
    },
  ).then((r) => (r === undefined ? null : r));
}
