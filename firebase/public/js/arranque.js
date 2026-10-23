/* Aviso independiente de los modulos: un import fallido no deja la pagina vacia. */
(() => {
  try {const tema=localStorage.getItem('itsanet.tema');if(['light','dark'].includes(tema))document.documentElement.dataset.theme=tema;} catch {}
  let terminado=false, fallo=false, temporizador;
  function panel() {
    let caja=document.getElementById('estadoArranque');
    if(!caja) {
      caja=document.createElement('div');caja.id='estadoArranque';caja.setAttribute('role','status');
      caja.style.cssText='margin:16px auto;padding:16px;max-width:900px;border:1px solid #cbd5e1;border-radius:12px;background:#fff;color:#0f172a;font:14px system-ui';
      const lugar=document.querySelector('.envoltorio,.caja') || document.body;
      const cabecera=lugar.querySelector('header');
      if(cabecera)cabecera.after(caja);else lugar.prepend(caja);
    }
    return caja;
  }
  function mostrar() {
    if(terminado || !document.body)return;
    const caja=panel();caja.replaceChildren();
    const texto=document.createElement('p');texto.style.margin='0 0 10px';
    texto.textContent=fallo ? 'No se pudo iniciar esta pantalla. Recarga para obtener la version actual; tus datos permanecen en el servidor.' : 'Abriendo la pantalla y comprobando tu sesion…';
    caja.append(texto);
    if(fallo) {
      const b=document.createElement('button');b.type='button';b.textContent='Volver a cargar';b.onclick=()=>location.reload();caja.append(b);
      const inicio=document.createElement('a');inicio.href='./';inicio.textContent=' Ir a Inicio';caja.append(inicio);
      const estado=document.getElementById('redOperacion');if(estado)estado.textContent='No se pudo iniciar la pantalla';
    }
  }
  globalThis.itsanetArranque={
    listo(){terminado=true;clearTimeout(temporizador);document.getElementById('estadoArranque')?.remove();},
    error(){if(terminado)return;fallo=true;mostrar();},
  };
  addEventListener('error',()=>globalThis.itsanetArranque.error(),true);
  addEventListener('unhandledrejection',()=>globalThis.itsanetArranque.error());
  addEventListener('DOMContentLoaded',mostrar,{once:true});
  temporizador=setTimeout(()=>globalThis.itsanetArranque.error(),12000);
})();
// Identificación visible del entorno independiente de pruebas, también al entrar.
addEventListener('DOMContentLoaded',()=>{if(!location.pathname.startsWith('/app/'))return;fetch('/api/auth/entorno',{credentials:'same-origin'}).then(r=>r.ok?r.json():null).then(r=>{if(!r?.pruebasPublicas)return;const b=document.createElement('aside');b.className='pruebas-publicas';b.textContent='PRUEBAS · Datos independientes. Utiliza documentos y destinatarios de prueba.';const c=document.querySelector('.envoltorio,.caja')||document.body;c.prepend(b);}).catch(()=>{});},{once:true});
