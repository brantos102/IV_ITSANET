/** Solicitudes y aprobaciones en el mismo destino donde entra el operario. */
import { collection, getDocs, doc, onSnapshot, runTransaction }
  from '../vendor/firebase-sdk.js?v=20261019-55';
import { db } from './auth.js?v=20261019-55';
import * as local from './local.js?v=20261019-55';

const filasDe = (snap) => snap.docs.map((d) => ({ ...d.data(), id: d.id, uid: d.id }));

export async function listarUsuarios() {
  if (local.modoLocal()) return local.listarUsuarios();
  return filasDe(await getDocs(collection(db, 'usuarios')));
}

export function observarUsuarios(alCambiar, alFallar) {
  if (local.modoLocal()) return local.escucharUsuarios(alCambiar, alFallar);
  return onSnapshot(collection(db, 'usuarios'), (snap) => alCambiar(filasDe(snap)), alFallar);
}

export async function actualizarUsuario(u, cambio) {
  if (local.modoLocal()) return local.actualizarUsuario(u, cambio);
  // Alias y ficha se mueven juntos. Las reglas siguen decidiendo quien puede
  // aprobar, cambiar roles y modificar a un administrador.
  return runTransaction(db, async (tx) => {
    const nuevo = cambio.usuario && cambio.usuario !== u.usuario
      ? doc(db, 'alias', cambio.usuario) : null;
    if (nuevo) {
      const ocupado = await tx.get(nuevo);
      if (ocupado.exists() && ocupado.data().uid !== u.uid) {
        throw new Error('Ese usuario ya esta tomado. Elige otro.');
      }
    }
    tx.update(doc(db, 'usuarios', u.uid), cambio);
    if (nuevo) {
      tx.set(nuevo, { email: u.email, uid: u.uid, tipoAcceso: u.tipoAcceso || 'CLAVE' });
      if (u.usuario) tx.delete(doc(db, 'alias', u.usuario));
    }
  });
}
