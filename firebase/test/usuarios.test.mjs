import { cargar, test, eq, ok, resumen } from './cargador.mjs';

const auth = await cargar('auth.js');
const usuarios = await cargar('usuarios.js');
const local = await cargar('local.js');
const registro = { nombre: 'Ana', apellido: 'Torres', usuario: 'atorres',
  correo: 'Ana@Itsanet.COM', clave: 'segura123' };

await test('registro Firebase no cambia la sesion que dispara el observador', async () => {
  globalThis.__documentos = {}; globalThis.__sets = []; globalThis.__altasAuth = [];
  const anterior = { uid: 'supervisor' };
  auth.auth.currentUser = anterior;
  await auth.registrarse(registro);
  ok(globalThis.__altasAuth[0].auth !== auth.auth, 'el alta en la sesion principal dispara asegurarPerfil demasiado pronto');
  eq(auth.auth.currentUser, anterior, 'no cierra ni cambia la sesion principal');
  const ficha = globalThis.__documentos['usuarios/nuevo'];
  eq(ficha.activo, false); eq(ficha.rol, 'OPERADOR');
  eq(ficha.usuario, 'atorres'); eq(ficha.email, 'ana@itsanet.com');
  eq(globalThis.__documentos['alias/atorres'].uid, ficha.uid);
});

await test('fallo del lote no deja alias o ficha escritos parcialmente', async () => {
  globalThis.__documentos = {}; globalThis.__sets = []; globalThis.__fallarLote = true;
  let error;
  try { await auth.registrarse(registro); } catch (e) { error = e; }
  finally { globalThis.__fallarLote = false; }
  ok(error); eq(globalThis.__sets.length, 0);
  eq(auth.auth.currentUser.uid, 'supervisor');
});

await test('la cola Firebase recibe nuevos registros sin recargar', async () => {
  globalThis.__listeners = [];
  let filas = null;
  const cancelar = usuarios.observarUsuarios((u) => { filas = u; });
  const listener = globalThis.__listeners.at(-1);
  eq(listener.ref.ruta, 'usuarios');
  listener.cambiar({ docs: [{ id: 'pendiente', data: () => ({ activo: false, nombre: 'Ana' }) }] });
  eq(filas[0].uid, 'pendiente'); eq(filas[0].activo, false);
  cancelar(); ok(listener.cerrado);
});

await test('aprobar escribe activo sin modificar el rol ni la identidad', async () => {
  await usuarios.actualizarUsuario({ uid: 'ana' }, { activo: true });
  eq(globalThis.__escrituras, [{ tipo: 'update', ruta: 'usuarios/ana', datos: { activo: true } }]);
});

await test('cambiar un alias ocupado no modifica la ficha', async () => {
  globalThis.__documentos = { 'alias/ocupado': { uid: 'otro' } };
  let error;
  try { await usuarios.actualizarUsuario({ uid: 'ana', usuario: 'ana' }, { usuario: 'ocupado' }); }
  catch (e) { error = e; }
  ok(error); eq(globalThis.__escrituras.length, 0);
});

await test('el modo servidor usa API para registro, lista y aprobacion', async () => {
  globalThis.localStorage = { getItem: () => 'local' };
  const peticiones = [];
  globalThis.fetch = async (url, opciones) => {
    peticiones.push({ url, opciones });
    return { ok: true, status: 200, json: async () => ({ id: 7, nombre: 'Ana Torres', activo: false }) };
  };
  await auth.registrarse(registro);
  await usuarios.listarUsuarios();
  await usuarios.actualizarUsuario({ id: 7, uid: 'atorres' }, { activo: true });
  eq(peticiones.map((p) => p.url), ['/api/auth/registro', '/api/auth/operadores', '/api/auth/operadores/7']);
  eq(JSON.parse(peticiones[0].opciones.body).email, 'ana@itsanet.com');
  eq(peticiones[2].opciones.method, 'PATCH');
  delete globalThis.localStorage;
});

await test('el mensaje de aprobacion pendiente sobrevive al error HTTP 403', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 403, json: async () => ({
    detail: { codigo: 'PENDIENTE_APROBACION', mensaje: 'Espera a un supervisor' },
  }) });
  let error;
  try { await local.entrarConClave('ana', '123456'); } catch (e) { error = e; }
  eq(error.codigo, 'PENDIENTE_APROBACION'); eq(error.message, 'Espera a un supervisor');
});

resumen();
