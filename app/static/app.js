/* Utilidades compartidas por las vistas. */
const API = {
  async req(metodo, url, cuerpo) {
    const opts = { method: metodo, headers: {}, credentials: 'same-origin' };
    if (cuerpo !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(cuerpo);
    }
    const r = await fetch(url, opts);
    const texto = await r.text();
    let datos = null;
    try { datos = texto ? JSON.parse(texto) : null; } catch { datos = { detail: texto }; }
    if (!r.ok) {
      const d = datos && datos.detail !== undefined ? datos.detail : datos;
      const err = new Error(
        typeof d === 'string' ? d : (d && d.mensaje) || `Error ${r.status}`
      );
      err.status = r.status;
      err.codigo = (d && d.codigo) || null;
      throw err;
    }
    return datos;
  },
  get: (u) => API.req('GET', u),
  post: (u, b) => API.req('POST', u, b),
  patch: (u, b) => API.req('PATCH', u, b),
};

function $(sel, raiz = document) { return raiz.querySelector(sel); }
function $$(sel, raiz = document) { return [...raiz.querySelectorAll(sel)]; }

function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function tag(valor) { return `<span class="tags t-${esc(valor)}">${esc(valor)}</span>`; }

function aviso(contenedor, texto, tipo = 'info', titulo = '') {
  const div = document.createElement('div');
  div.className = `msg ${tipo}`;
  div.innerHTML = (titulo ? `<b>${esc(titulo)}</b>` : '') + esc(texto);
  contenedor.prepend(div);
  return div;
}

function limpiarAvisos(contenedor) { $$('.msg', contenedor).forEach((n) => n.remove()); }

/* Sonido corto para confirmar/avisar sin mirar la pantalla. */
const Audio_ = (() => {
  let ctx = null;
  return (frecuencia = 880, ms = 110) => {
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.frequency.value = frecuencia; o.type = 'sine';
      o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(0.08, ctx.currentTime);
      o.start();
      o.stop(ctx.currentTime + ms / 1000);
    } catch { /* sin audio disponible */ }
  };
})();

const bipOk = () => { Audio_(950, 90); if (navigator.vibrate) navigator.vibrate(40); };
const bipError = () => { Audio_(240, 240); if (navigator.vibrate) navigator.vibrate([60, 50, 60]); };

/* Clave de idempotencia: evita que un doble disparo del lector sume dos veces. */
function claveIdem() {
  return (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())).slice(0, 36);
}

function nombreDispositivo() {
  let d = localStorage.getItem('val_dispositivo');
  if (!d) {
    d = 'disp-' + Math.random().toString(36).slice(2, 8);
    localStorage.setItem('val_dispositivo', d);
  }
  return d;
}

function num(v) { return (v === null || v === undefined) ? '' : v; }
