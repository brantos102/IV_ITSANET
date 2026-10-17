import {operacion, abrirEvidencias, TIPOS_EVIDENCIA, esc} from './evidencias.js?v=20261016-35';

/** Guía del cierre: distingue una foto por tomar de una copia todavía pendiente. */
export async function abrirAyudaCierre({recepcion, alFinalizar, alDescargar}) {
  const existente = document.querySelector('dialog.cierre-ayuda[open]');
  if (existente) return existente;
  const d = document.createElement('dialog'); d.className = 'dialogo-operativo cierre-ayuda';
  d.innerHTML = `<div class="acciones"><h2 style="flex:1">Completar envío a Drive</h2><button type="button" class="b-sec" data-cerrar>Cerrar</button></div>
    <p data-resumen role="status">Consultando las fotos de esta recepción…</p>
    <p class="mini">Estas fotos ya están guardadas: no necesitas tomarlas otra vez. Las recomendaciones fotográficas no bloquean el avance.</p>
    <div data-fotos class="cierre-fotos"></div>
    <div class="acciones"><button type="button" class="b-sec" data-anterior>Anterior</button><span data-pagina class="mini"></span><button type="button" class="b-sec" data-siguiente>Siguiente</button></div>
    <p data-pasos></p><p data-estado role="status"></p>
    <div class="acciones"><button type="button" class="b-primario" data-reintentar>Reintentar copia</button><button type="button" class="b-sec" data-actualizar>Actualizar estado</button></div>
    <div class="acciones"><button type="button" class="b-sec" data-avance>Descargar avance</button><button type="button" class="b-ok" data-finalizar hidden>Continuar con el cierre</button></div>`;
  document.body.append(d); d.showModal();
  const $ = s => d.querySelector(s);
  $('[data-avance]').hidden = !alDescargar;
  let pagina = 0, consultando = false, ocupado = false, temporizador;
  const base = '/recepciones/' + encodeURIComponent(recepcion);
  async function actualizar() {
    if (consultando || !d.open) return;
    consultando = true;
    try {
      const r = await operacion(base + `/pendientes-cierre?offset=${pagina * 30}&limite=30`);
      if (!d.open) return;
      if (pagina && pagina * 30 >= r.total) { pagina = 0; consultando = false; return actualizar(); }
      $('[data-resumen]').textContent = r.total
        ? `${r.total} foto(s) pendientes de confirmación · ${r.procesando} en proceso.`
        : 'Las fotos de los productos tienen sus carpetas confirmadas en Drive.';
      if(r.sincronizacion){const s=r.sincronizacion;
        $('[data-resumen]').textContent=`${s.guardadas} fotos guardadas · ${s.copiadas} confirmadas en Drive · ${s.pendientes} pendientes (${s.procesando} en proceso).`+
          (r.total?` ${r.total} foto(s) de productos requieren confirmar su carpeta.`:'');}
      $('[data-pasos]').textContent = r.total
        ? '1. Revisa abajo cuáles son. 2. Espera la copia o pulsa «Reintentar copia». 3. '+(alFinalizar?'Cuando se confirme Drive, continúa con el cierre para enviar el informe.':'Cuando se confirme Drive, vuelve a Entrega del informe y reintenta la misma entrega pendiente.') +
          (r.requierenAyuda ? ' Hubo intentos sin confirmar: si persiste, avisa al administrador para revisar la conexión. Tus fotos se conservan.' : '')
        : alFinalizar ? 'Puedes continuar con el cierre y confirmar los destinatarios. Esta revisión no ha enviado ningún correo.'
          : 'Revisa el estado de la entrega y reintenta la entrega pendiente cuando Drive esté listo. Esta revisión no ha enviado ningún correo.';
      $('[data-fotos]').innerHTML = r.archivos.map((f, i) => `<article><b>${esc(f.nombre)}</b>
        ${f.vinculos.map(v => `<p class="mini">${esc(v.sku)} · ${esc(TIPOS_EVIDENCIA[v.tipo] || v.tipo)}${v.unidad ? ' · ' + esc(v.unidad) : ''}${v.origen ? ' · ' + esc(v.origen) : ''}</p>`).join('')}
        <p class="mini">${f.estado === 'PROCESANDO' ? 'Copiando a Drive' : f.estado === 'COPIADA' ? 'Falta confirmar el enlace de la carpeta: solicita revisión al administrador' : f.requiereAyuda ? 'Copia sin confirmar; se conserva la foto y se reintentará' : 'Esperando copia a Drive'}</p>
        <button type="button" class="chip" data-ver="${i}">Ver fotos del producto</button></article>`).join('');
      d.querySelectorAll('[data-ver]').forEach(b => { b.onclick = async () => {
        const sku = r.archivos[Number(b.dataset.ver)].vinculos[0]?.sku || '';
        d.close();
        try { await abrirEvidencias({recepcion, sku, supervisor: true}); }
        catch (e) { await import('./modal.js?v=20261016-35').then(m => m.avisarModal({titulo:'No se pudieron abrir las fotos',texto:esc(e.message)})); }
      }; });
      $('[data-pagina]').textContent = r.total ? `${pagina * 30 + 1}–${Math.min((pagina + 1) * 30, r.total)} de ${r.total}` : '';
      $('[data-anterior]').hidden = !pagina;
      $('[data-siguiente]').hidden = !r.hayMas;
      $('[data-reintentar]').hidden = !r.total;
      if(r.sincronizacion?.pendientes)$('[data-reintentar]').hidden=false;
      $('[data-finalizar]').hidden = !alFinalizar || r.bloqueaCierre;
      if (!r.total) $('[data-estado]').textContent = '';
    } catch (e) { if (d.open) $('[data-estado]').textContent = e.message + ' Puedes seguir validando; el informe no se ha enviado.'; }
    finally { consultando = false; }
  }
  $('[data-reintentar]').onclick = async () => {
    if (ocupado) return;
    ocupado = true; $('[data-reintentar]').disabled = true;
    try { const r = await operacion(base + '/drive/reintentar', {cuerpo:{}}); if (d.open) $('[data-estado]').textContent = r.mensaje; await actualizar(); }
    catch (e) { if (d.open) $('[data-estado]').textContent = e.message; }
    finally { ocupado = false; if (d.open) $('[data-reintentar]').disabled = false; }
  };
  $('[data-actualizar]').onclick = actualizar;
  $('[data-anterior]').onclick = () => { pagina--; actualizar(); };
  $('[data-siguiente]').onclick = () => { pagina++; actualizar(); };
  $('[data-cerrar]').onclick = () => d.close();
  $('[data-avance]').onclick = () => { d.close(); alDescargar?.(); };
  $('[data-finalizar]').onclick = () => { d.close(); alFinalizar?.(); };
  d.addEventListener('close', () => { clearInterval(temporizador); d.remove(); }, {once:true});
  temporizador = setInterval(actualizar, 5000);
  await actualizar();
  return d;
}
