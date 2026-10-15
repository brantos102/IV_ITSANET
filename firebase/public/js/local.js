/**
 * La capa de datos contra el servidor propio.
 *
 * Misma aplicación, otro destino. Las pantallas no cambian: `datos.js`,
 * `conteo.js` e `informe.js` llaman a estas funciones cuando la aplicación se
 * sirve desde el servidor de la red local, y a Firestore cuando se sirve desde
 * iv-itsanet.web.app. Los documentos que devuelven son los mismos —mismos
 * nombres de campo, mismas formas—, que es lo único que permite cambiar de sitio
 * sin reescribir nada de lo que ya funciona.
 *
 * Cómo se decide: el servidor sirve la aplicación bajo `/app/`, el hosting de
 * Firebase la sirve en la raíz. No hace falta configurar nada ni acordarse de
 * cambiar un interruptor al desplegar; la dirección ya lo dice.
 *
 * Lo que NO está aquí y no puede estar: el tiempo real entre operarios. En
 * Firestore `onSnapshot` lo daba la base; sobre HTTP hay que preguntar. Se
 * pregunta cada pocos segundos, se avisa solo cuando algo cambió de verdad, y
 * la pantalla no nota la diferencia salvo en el retardo.
 */

/** Dónde vive la API. Mismo origen que la página: no hay CORS que configurar. */
export const BASE = '/api/app';
/** La sesión cuelga de otra rama: la comparte con las pantallas del servidor. */
export const BASE_SESION = '/api/auth';

const CLAVE_MODO = 'itsanet.modo';

/**
 * ¿Hablamos con el servidor propio?
 *
 * La regla es la ruta. `localStorage` permite forzarlo para probar los dos
 * destinos desde el mismo sitio —escribiendo `local` o `nube`—, que es lo que
 * hace falta durante la transición.
 */
export function modoLocal() {
  // La ruta operativa siempre escribe en el servidor, incluso si quedo una
  // preferencia antigua de pruebas en el navegador.
  if (typeof location !== 'undefined' && String(location.pathname || '').startsWith('/app/')) return true;
  try {
    const forzado = localStorage.getItem(CLAVE_MODO);
    if (forzado === 'local') return true;
    if (forzado === 'nube') return false;
  } catch { /* navegador sin almacenamiento: manda la ruta */ }
  // Sin `location` no hay página: es una prueba o un script. Ahí no se decide
  // nada, y lo que no se puede decidir no puede mandar peticiones a ningún
  // servidor.
  return typeof location !== 'undefined'
      && String(location.pathname || '').startsWith('/app/');
}

/** Error con el código que manda el servidor: la pantalla decide con él. */
export class ErrorServidor extends Error {
  constructor(mensaje, codigo = 'ERROR', estado = 0) {
    super(mensaje);
    this.codigo = codigo;
    this.estado = estado;
  }
}

/**
 * Una llamada a la API.
 *
 * Tres cosas que un `fetch` suelto no hace y aquí hacen falta:
 * la cookie de sesión viaja (`credentials`), el código del error se conserva
 * —el handheld abre un diálogo distinto según cuál sea—, y un servidor caído se
 * distingue de un dato rechazado. «No se pudo guardar» sin decir cuál de las dos
 * cosas pasó deja al operario sin saber si repetir o avisar.
 */
export async function pedir(ruta, opciones = {}) {
  let r;
  try {
    r = await fetch((opciones.base || BASE) + ruta, {
      credentials: 'same-origin',
      headers: opciones.cuerpo ? { 'Content-Type': 'application/json' } : {},
      method: opciones.metodo || (opciones.cuerpo ? 'POST' : 'GET'),
      body: opciones.cuerpo ? JSON.stringify(opciones.cuerpo) : undefined,
    });
  } catch (e) {
    throw new ErrorServidor(
      'No hay conexión con el servidor. Comprueba la red del almacén.',
      'SIN_RED',
    );
  }

  let cuerpo = null;
  try { cuerpo = await r.json(); } catch { /* 204 o respuesta vacia */ }
  if (!r.ok && cuerpo?.detail && typeof cuerpo.detail === 'object' && cuerpo.detail.codigo) {
    throw new ErrorServidor(cuerpo.detail.mensaje || 'Error del servidor', cuerpo.detail.codigo, r.status);
  }
  if (r.status === 401 || r.status === 403) {
    throw new ErrorServidor(
      r.status === 401 ? 'Tu sesión caducó: vuelve a entrar.'
                       : 'Tu usuario no tiene permiso para esto.',
      r.status === 401 ? 'SIN_SESION' : 'SIN_PERMISO', r.status,
    );
  }


  if (!r.ok) {
    const d = cuerpo?.detail;
    if (d && typeof d === 'object') {
      throw new ErrorServidor(d.mensaje || 'Error del servidor', d.codigo, r.status);
    }
    const validacion = Array.isArray(d) ? d.map(e => String(e.msg || '').replace(/^Value error, /, '')).join('. ') : null;
    throw new ErrorServidor(
      validacion || (typeof d === 'string' ? d : `El servidor respondió ${r.status}.`),
      'ERROR', r.status,
    );
  }
  return cuerpo;
}

// ========================================================================== //
// Recepciones
// ========================================================================== //
export const listarRecepciones = (max = 50) => pedir(`/recepciones?max=${max}`);

export const listarMisRecepciones = (_uid, max = 60) =>
  pedir(`/recepciones?max=${max}&mias=true`);

export const obtenerRecepcion = (id) => pedir(`/recepciones/${encodeURIComponent(id)}`);

export async function crearRecepcion({ codigo, cliente, descripcion, bultos }) {
  const doc = await pedir('/recepciones', {
    cuerpo: { codigo, cliente, descripcion, bultos },
  });
  return doc.codigo;
}

export async function borrarRecepcion(recepcionId, alAvanzar) {
  const r = await pedir(`/recepciones/${encodeURIComponent(recepcionId)}`,
                        { metodo: 'DELETE' });
  // El servidor lo borra todo de una vez; el aviso de avance existe porque en
  // Firestore había que recorrer cada subcolección y tardaba.
  const total = Object.values(r.borrado || {}).reduce((a, b) => a + b, 0);
  if (alAvanzar) alAvanzar(total, total);
  return r;
}

export const cerrarRecepcion = (id) =>
  pedir(`/recepciones/${encodeURIComponent(id)}/cerrar`, { cuerpo: {} });

export const reabrirRecepcion = (id, motivo = '') =>
  pedir(`/recepciones/${encodeURIComponent(id)}/reabrir`, { cuerpo: { motivo } });

/** Las subcolecciones: lineas, skus, adicionales, eventos, auditoria. */
export const leerColeccion = (recepcionId, nombre, max = 0) =>
  pedir(`/recepciones/${encodeURIComponent(recepcionId)}/${nombre}`
        + (max ? `?max=${max}` : ''));

// ========================================================================== //
// Packing list
// ========================================================================== //
export function guardarPackingList(recepcionId, resultado, alAvanzar, opciones = {}) {
  // El archivo lo lee el navegador —con la rutina que conoce los formatos de
  // cada cliente— y se manda el resultado ya traducido. El servidor no vuelve a
  // abrir el Excel: dos lectores serían dos cosas que pueden discrepar sobre
  // cuántas unidades declara una fila.
  if (alAvanzar) alAvanzar(0, resultado.lineas?.length || 0);
  return pedir(`/recepciones/${encodeURIComponent(recepcionId)}/packing-list`, {
    cuerpo: {
      resultado: { ...resultado, resumen: opciones.resumen || null },
      origen: opciones.origen || 'PRINCIPAL',
      archivo: opciones.archivo || null,
    },
  }).then((r) => {
    if (alAvanzar) alAvanzar(r.lineas, r.lineas);
    return r;
  });
}

export const buscarPackingListParecido = (resumen, opciones = {}) =>
  pedir('/packing-lists/parecidos', {
    cuerpo: { resumen, excluirRecepcion: opciones.excluirRecepcion || null },
  });

// ========================================================================== //
// Conteo
// ========================================================================== //
export const registrarConteo = (recepcionId, usuario, p) =>
  pedir(`/recepciones/${encodeURIComponent(recepcionId)}/conteos`, {
    cuerpo: { ...p, id: p.idempotencyKey || p.id },
  });

export const declararNoEncontrado = (recepcionId, usuario, p) =>
  pedir(`/recepciones/${encodeURIComponent(recepcionId)}/no-encontrado`, {
    cuerpo: { ...p, id: p.idempotencyKey || p.id },
  });

export const anularConteo = (recepcionId, usuario, eventoId, motivo) =>
  pedir(`/recepciones/${encodeURIComponent(recepcionId)}/conteos/`
        + `${encodeURIComponent(eventoId)}/anular`, { cuerpo: { motivo } });

export const registrarAuditoria = (recepcionId, usuario, tipo, detalle = {}) =>
  pedir(`/recepciones/${encodeURIComponent(recepcionId)}/auditoria`,
        { cuerpo: { tipo, detalle } });

export const leerAuditoria = (recepcionId, max = 40) =>
  leerColeccion(recepcionId, 'auditoria', max);

export const leerBitacora = (recepcionId, max = 60) =>
  leerColeccion(recepcionId, 'eventos', max);

// ========================================================================== //
// Catálogo
// ========================================================================== //
export const buscarEnCatalogo = async (codigo) => {
  const producto = await pedir(`/catalogo/${encodeURIComponent(codigo)}`);
  return producto.existe ? producto : null;
};

// ========================================================================== //
// Lo que en Firestore daba la base y aquí hay que preguntar
// ========================================================================== //
/**
 * Avisa de los cambios en los SKU de una recepción.
 *
 * `onSnapshot` empujaba; esto pregunta. Dos decisiones que se notan en el
 * handheld:
 *
 * - Solo avisa cuando algo cambió de verdad. Repintar la tabla entera cada
 *   cuatro segundos pierde el sitio donde estaba mirando el operario.
 * - Se para cuando la pestaña no está a la vista. Un handheld en el bolsillo
 *   consultando el servidor toda la mañana gasta batería para nadie.
 *
 * Devuelve la función de cancelar, igual que `onSnapshot`.
 */
function observarConsulta(consulta, alCambiar, alFallar, cada = 4000) {
  let vivo = true;
  let anterior = '';
  let reloj = null;
  let consultando = false;

  const mirar = async () => {
    if (!vivo || consultando) return;
    if (document.visibilityState === 'hidden') return;
    consultando = true;
    try {
      const skus = await consulta();
      if (!vivo) return;
      const firma = JSON.stringify(skus);
      if (firma !== anterior) {
        anterior = firma;
        alCambiar(skus);
      }
    } catch (e) {
      if (vivo && alFallar) alFallar(e);
    } finally {
      consultando = false;
    }
  };

  mirar();
  reloj = setInterval(mirar, cada);
  document.addEventListener('visibilitychange', mirar);

  return () => {
    vivo = false;
    clearInterval(reloj);
    document.removeEventListener('visibilitychange', mirar);
  };
}

export const escucharSkus = (recepcionId, alCambiar, alFallar, cada = 4000) =>
  observarConsulta(() => leerColeccion(recepcionId, 'skus'), alCambiar, alFallar, cada);

export const listarUsuarios = () => pedir('/operadores', { base: BASE_SESION });
export const escucharUsuarios = (alCambiar, alFallar) =>
  observarConsulta(listarUsuarios, alCambiar, alFallar);
export const actualizarUsuario = (u, cambio) =>
  pedir(`/operadores/${encodeURIComponent(u.id)}`, { base: BASE_SESION, metodo: 'PATCH', cuerpo: cambio });

export const registrarse = async ({ nombre, apellido, usuario, correo, clave }) => {
  const ficha = await pedir('/registro', { base: BASE_SESION, cuerpo: {
    nombre: `${nombre || ''} ${apellido || ''}`.trim(),
    usuario: String(usuario || '').trim().toLowerCase(),
    email: String(correo || '').trim().toLowerCase(), pin: clave,
  } });
  return { ...ficha, nombre: ficha.nombre };
};

export const crearOperario = ({ usuario, correo, clave, nombre, rol = 'OPERADOR' }) =>
  pedir('/operadores', { base: BASE_SESION, cuerpo: {
    usuario: String(usuario || '').trim().toLowerCase(), nombre, pin: clave,
    email: String(correo || '').trim().toLowerCase(), rol,
  } });

/**
 * El catálogo no se sube desde el navegador.
 *
 * En la nube, precalentar el catálogo era escribir miles de productos desde la
 * pantalla del supervisor, porque no había dónde más. Aquí el maestro ya vive en
 * el servidor: lo baja de Depot `scripts/sincronizar_depot.py` o lo carga el
 * Excel en Administración. Mandarlo otra vez desde un handheld serían miles de
 * peticiones para dejar lo que ya está.
 *
 * Devuelve el recuento de lo que hay, que es lo que la pantalla enseña.
 */
export async function guardarCatalogo(productos, alAvanzar) {
  const n = productos?.length || 0;
  if (alAvanzar) alAvanzar(n, n);
  return { guardados: 0, enServidor: true,
           mensaje: 'El maestro se carga en el servidor, no desde el handheld.' };
}

/** Un código de etiqueta que corresponde a un SKU del maestro. */
export const registrarEquivalencia = (codigo, sku) =>
  pedir(`/catalogo/${encodeURIComponent(codigo)}/equivalencia`, { cuerpo: { sku } });

// ========================================================================== //
// La sesión, cuando no hay Firebase
// ========================================================================== //
/**
 * En el servidor la sesión es una cookie, no un token de Google.
 *
 * Firebase avisaba de los cambios de sesión con `onAuthStateChanged`. Aquí no
 * hay quien avise, así que se avisa a mano: entrar y salir notifican a quien
 * esté escuchando. Las pantallas siguen llamando a `observarSesion` y no notan
 * la diferencia.
 *
 * El botón de Google no existe en este modo, y no es una carencia: entrar con
 * Google necesita Internet, y la razón de tener el servidor en la red local es
 * poder trabajar sin depender de él.
 */
const oyentes = new Set();

export async function sesionLocal() {
  try {
    return await pedir('/yo', { base: BASE_SESION });
  } catch (e) {
    if (e.codigo === 'SIN_SESION' || e.codigo === 'SIN_PERMISO') return null;
    throw e;
  }
}

/** Convierte lo que devuelve el servidor en el perfil que leen las pantallas. */
const aPerfil = (yo) => (yo ? {
  uid: yo.uid || yo.usuario,
  email: yo.email || yo.usuario,
  usuario: yo.usuario,
  nombre: yo.nombre,
  rol: yo.rol,
  activo: yo.activo !== false,
  tipoAcceso: 'CLAVE',
} : null);

async function avisar() {
  let estado = { usuario: null, perfil: null };
  try {
    const yo = await sesionLocal();
    if (yo) {
      const perfil = aPerfil(yo);
      // La aplicación espera dos cosas: el «usuario» de la sesión y su perfil.
      // Contra el servidor son el mismo dato, así que se entrega dos veces en
      // vez de inventar una diferencia que aquí no existe.
      estado = { usuario: { uid: perfil.uid, email: perfil.email,
                            displayName: perfil.nombre }, perfil };
    }
  } catch (e) {
    estado = { usuario: null, perfil: null, error: e.message };
  }
  oyentes.forEach((f) => f(estado));
}

export function observarSesion(alCambiar) {
  oyentes.add(alCambiar);
  avisar();
  return () => oyentes.delete(alCambiar);
}

export async function entrarConClave(usuario, clave) {
  const u = String(usuario || '').trim().toLowerCase();
  if (!u || !clave) throw new ErrorServidor('Escribe tu usuario y tu contraseña.', 'FALTAN_DATOS');
  try {
    await pedir('/login', { base: BASE_SESION, cuerpo: { usuario: u, pin: clave } });
  } catch (e) {
    // El servidor responde 401 a una contraseña mal puesta, igual que a una
    // sesión caducada. Dicho así, el operario no sabe si volver a escribirla o
    // avisar a alguien.
    if (e.codigo === 'SIN_SESION') {
      throw new ErrorServidor('Usuario o contraseña incorrectos.', 'CREDENCIALES');
    }
    throw e;
  }
  await avisar();
  return u;
}

export async function salir() {
  try { await pedir('/logout', { base: BASE_SESION, cuerpo: {} }); } catch { /* ya estaba fuera */ }
  await avisar();
}

/** Cambiar la propia contraseña. Hace falta la actual, también aquí. */
export const cambiarClave = (claveActual, claveNueva) =>
  pedir('/clave', { base: BASE_SESION, cuerpo: { actual: claveActual, nueva: claveNueva } });

/** Archivos y preferencias de la instalacion local. */
export const estadoServidor = () => pedir('/estado');
export const leerFormatosCsv = () => pedir('/config/csv');
export const guardarFormatosCsv = (formatos) => pedir('/config/csv', { metodo: 'PUT', cuerpo: { formatos } });
export async function proxyLocal(accion, datos = {}) {
  if (accion === 'producto') return { exito: true, producto: await buscarEnCatalogo(datos.codigo) };
  if (accion === 'subirFoto' || accion === 'guardarInforme') {
    const tipo = accion === 'subirFoto' ? 'foto' : 'informe';
    const r = await pedir(`/recepciones/${encodeURIComponent(datos.recepcion)}/archivos/${tipo}`, { cuerpo: datos });
    const origen = typeof location !== 'undefined' ? location.origin : null;
    if (origen) { r.url = new URL(r.url, origen).href; r.enlace = r.url; }
    return r;
  }
  throw new ErrorServidor('Esta opcion requiere configuracion adicional del servidor. El conteo y los archivos locales siguen disponibles.', 'NO_CONFIGURADO');
}


export const entregasServidor = () => pedir('/entregas');
export const reintentarEntrega = (id) => pedir(`/entregas/${encodeURIComponent(id)}/reintentar`, { cuerpo: {} });
export const finalizarConEntrega = (codigo, datos) => pedir(`/recepciones/${encodeURIComponent(codigo)}/entrega`, { cuerpo: datos });
export const destinatariosRecientes = (codigo) => pedir(`/recepciones/${encodeURIComponent(codigo)}/destinatarios-recientes`);
export const entregasRecepcion = (codigo) => pedir(`/recepciones/${encodeURIComponent(codigo)}/entregas`);

export const consultarSku = (codigo, sku) => pedir(`/recepciones/${encodeURIComponent(codigo)}/estado-sku/${encodeURIComponent(sku)}`);
