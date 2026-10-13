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
 * Se usa en tres capas, porque una sola no basta:
 *   1. Aquí, como pista `hd` para que el selector de cuentas de Google solo
 *      ofrezca las corporativas. Es comodidad, NO seguridad: se puede saltar.
 *   2. En el cliente, para cerrar la sesión de inmediato si el correo no es
 *      del dominio. Evita que alguien quede en un estado raro.
 *   3. En las reglas de Firestore, que es la única que de verdad protege.
 *      Un usuario de Gmail puede completar el login y no podrá leer ni
 *      escribir absolutamente nada.
 */
export const DOMINIO = 'itsanet.com';

/** Versión del SDK de Firebase que carga la app. */
export const SDK = '10.14.1';
