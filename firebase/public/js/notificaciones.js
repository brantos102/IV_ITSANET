/** Aviso persistente en la página y copia visible sin desplazar al operario. */
export function mostrarAviso(contenedor, texto, tipo = 'info', titulo = '') {
  const focoAnterior = document.activeElement;
  const aviso = document.createElement('div');
  aviso.className = 'msg ' + tipo;
  if (titulo) {
    const b = document.createElement('b'); b.textContent = titulo; aviso.append(b);
  }
  aviso.append(document.createTextNode(String(texto ?? '')));
  contenedor.append(aviso);

  const flotante = document.createElement('div');
  flotante.className = 'notificacion-flotante msg ' + tipo;
  flotante.setAttribute('role', tipo === 'err' ? 'alert' : 'status');
  flotante.setAttribute('aria-atomic', 'true');
  flotante.setAttribute('popover', 'manual');
  const contenido = document.createElement('div');
  contenido.append(...[...aviso.childNodes].map(n => n.cloneNode(true)));
  const cerrar = document.createElement('button');
  cerrar.type = 'button'; cerrar.textContent = '✕'; cerrar.setAttribute('aria-label', 'Cerrar notificación');
  flotante.append(contenido, cerrar);
  // Un solo aviso visible; el historial completo permanece en su sección.
  document.querySelectorAll('.notificacion-flotante').forEach(n => n.remove());
  const dialogo = [...document.querySelectorAll('dialog[open]')].at(-1);
  (dialogo || document.body).append(flotante);
  try { flotante.showPopover?.(); } catch { /* Visible como elemento fijo en navegadores anteriores. */ }

  const viewport = globalThis.visualViewport;
  const colocar = () => {
    flotante.style.top = Math.max(12, (viewport?.offsetTop || 0) + 12) + 'px';
    flotante.style.maxHeight = Math.max(80, Math.min(260, (viewport?.height || innerHeight) * .45)) + 'px';
  };
  colocar(); viewport?.addEventListener('resize', colocar); viewport?.addEventListener('scroll', colocar);
  const observador = new MutationObserver(() => { if (!aviso.isConnected || !flotante.isConnected) retirar(); });
  observador.observe(document.body, { childList: true, subtree: true });
  let temporizador;
  function retirar() {
    const restaurarFoco = document.activeElement === cerrar;
    clearTimeout(temporizador); observador.disconnect();
    viewport?.removeEventListener('resize', colocar); viewport?.removeEventListener('scroll', colocar);
    flotante.remove();
    if (restaurarFoco && focoAnterior?.isConnected) focoAnterior.focus({preventScroll:true});
  }
  cerrar.onclick = retirar;
  // Errores y advertencias esperan a que el usuario los descarte.
  if (tipo === 'ok') temporizador = setTimeout(retirar, 7000);
  return aviso;
}
