/**
 * Configuración del proyecto de Firebase.
 *
 * Estos valores NO son secretos: identifican al proyecto y viajan dentro del
 * JavaScript que descarga cualquier visitante. Lo que protege los datos son
 * las reglas de Firestore, no esta clave.
 *
 * Lo que sí es secreto (las credenciales de Depot) vive en las propiedades del
 * Apps Script, del lado servidor, y nunca llega al dispositivo.
 */
export const firebaseConfig = {
  apiKey: 'AIzaSyBCfPBE9YryYl8EX0vOVIgKQv2ZVro8ziM',
  authDomain: 'iv-itsanet.firebaseapp.com',
  projectId: 'iv-itsanet',
  storageBucket: 'iv-itsanet.firebasestorage.app',
  messagingSenderId: '601300841441',
  appId: '1:601300841441:web:645ba094384a5b619018a0',
};

/**
 * Dominio corporativo.
 *
 * Quien protege de verdad son las reglas de Firestore: rechazan toda lectura
 * y escritura de un correo que no sea de este dominio. El cliente además
 * cierra la sesión de inmediato, para que nadie quede en un estado raro.
 */
export const DOMINIO = 'itsanet.com';

/**
 * Pista `hd` para el selector de cuentas de Google.
 *
 * APAGADO A PROPÓSITO. `hd` filtra el selector a las cuentas **gestionadas por
 * Google Workspace**: Google compara el dominio con el campo `hd` del token,
 * que solo tienen esas cuentas.
 *
 * Si el correo corporativo no está en Workspace sino que es una cuenta de
 * Google normal creada con una dirección `@itsanet.com`, activarlo la **oculta
 * del selector** y el operario no puede entrar, sin ningún error que explique
 * por qué. Es un fallo caro de diagnosticar.
 *
 * Como `hd` es solo comodidad —se puede saltar, no protege nada— no vale la
 * pena arriesgarse. Actívalo únicamente si confirmaste que el dominio está en
 * Workspace y quieres que el selector muestre menos cuentas.
 */
export const USAR_PISTA_HD = false;

/** Versión del SDK de Firebase que carga la app. */
export const SDK = '10.14.1';
