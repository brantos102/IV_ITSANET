/**
 * Cliente del proxy de Depot.
 *
 * El navegador nunca habla con el WMS directamente: lo hace a través del Apps
 * Script, que es quien guarda las credenciales de cada cliente. Este módulo
 * solo sabe pedirle cosas.
 */
import { doc, getDoc } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js';
import { auth, db } from './auth.js';

let urlProxy = null;

/**
 * URL del Apps Script, guardada en `config/proxy` de Firestore.
 *
 * Vive ahí y no en el código para poder cambiar el despliegue del proxy sin
 * volver a publicar la aplicación web.
 */
export async function obtenerUrlProxy(forzar = false) {
  if (urlProxy && !forzar) return urlProxy;
  const snap = await getDoc(doc(db, 'config', 'proxy'));
  if (!snap.exists() || !snap.get('url')) {
    throw new Error(
      'El proxy de Depot no está configurado. Cree el documento config/proxy ' +
      'en Firestore con el campo "url" (paso 5 de la instalación).',
    );
  }
  urlProxy = snap.get('url');
  return urlProxy;
}

/**
 * Llama a una acción del proxy.
 *
 * Se manda `Content-Type: text/plain` a propósito: así la petición es "simple"
 * y el navegador no hace preflight. Apps Script no permite responder cabeceras
 * CORS propias, de modo que con preflight la llamada fallaría siempre.
 */
export async function llamarProxy(accion, datos = {}, { timeoutMs = 120000 } = {}) {
  const url = await obtenerUrlProxy();
  const usuario = auth.currentUser;
  if (!usuario) throw new Error('No hay sesión iniciada.');

  // Token fresco: el del proxy se verifica contra Google en cada llamada nueva.
  const idToken = await usuario.getIdToken();

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify({ accion, idToken, ...datos }),
      redirect: 'follow',
      signal: ctrl.signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') {
      throw new Error(
        'El proxy tardó demasiado. Si estabas descargando catálogos, ' +
        'prueba con menos clientes a la vez.',
      );
    }
    throw new Error(
      'No se pudo contactar al proxy. Revisa que esté publicado como ' +
      '"Cualquier usuario" y que la URL de config/proxy sea la del despliegue.',
    );
  } finally {
    clearTimeout(t);
  }

  const texto = await res.text();
  let cuerpo;
  try {
    cuerpo = JSON.parse(texto);
  } catch {
    // Apps Script devuelve HTML cuando falla la autorización del despliegue.
    throw new Error(
      'El proxy respondió algo que no es JSON. Suele significar que el ' +
      'despliegue no está autorizado o la URL apunta a otra cosa.',
    );
  }

  if (cuerpo.exito === false) {
    const err = new Error(cuerpo.mensaje || 'Error en el proxy');
    err.detalle = cuerpo;
    throw err;
  }
  return cuerpo;
}

// --------------------------------------------------------------------------- //
// Acciones
// --------------------------------------------------------------------------- //
export const Proxy = {
  listarClientes: () => llamarProxy('listarClientes'),

  guardarCliente: (cliente) => llamarProxy('guardarCliente', cliente),

  borrarCliente: (id) => llamarProxy('borrarCliente', { id }),

  /** Prueba gettoken y getstock de un cliente, informando cada paso. */
  probarCliente: (id, codigo) => llamarProxy('probarCliente', { id, codigo }),

  /** Busca un código en los clientes indicados, o en todos si se omiten. */
  producto: (codigo, clientes) => llamarProxy('producto', { codigo, clientes }),

  /** Catálogo combinado. Una llamada al WMS por cliente, no por SKU. */
  catalogo: (clientes) => llamarProxy('catalogo', { clientes }, { timeoutMs: 300000 }),

  estadoToken: () => llamarProxy('estadoToken'),

  subirFoto: (datos) => llamarProxy('subirFoto', datos),

  enviarInforme: (datos) => llamarProxy('enviarInforme', datos),
};
