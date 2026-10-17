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
  /**
   * Dominio donde Google resuelve el acceso.
   *
   * Tiene que ser uno de los URI de redirección registrados en el cliente
   * OAuth del proyecto. Firebase registra `…firebaseapp.com` al crear el
   * proyecto; `iv-itsanet.web.app` NO viene registrado, y apuntando ahí sin
   * añadirlo Google responde `Error 400: redirect_uri_mismatch` y no deja
   * entrar a nadie.
   *
   * Por eso se queda el que viene de fábrica: funciona sin tocar ninguna
   * consola.
   *
   * El inconveniente conocido es que el acceso por redirección —el de los
   * móviles— guarda un dato en este dominio y lo recoge al volver; como no es
   * el de la app, los navegadores móviles lo aíslan y la sesión no cuaja. No
   * bloquea a nadie: el operario entra con usuario y contraseña, que no pasa
   * por aquí, y supervisores y administradores entran con Google desde su
   * equipo, donde la ventana emergente sí funciona.
   *
   * Para habilitar además Google en el móvil: registrar
   * `https://iv-itsanet.web.app/__/auth/handler` como URI de redirección
   * autorizado en Google Cloud Console → Credenciales → cliente OAuth web, y
   * cambiar aquí a `iv-itsanet.web.app`. Está detallado en INSTALACION.md.
   */
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

/**
 * Identificador de la base de datos de Firestore.
 *
 * El proyecto usa una base NOMBRADA, no la `(default)`. Tanto el SDK como el
 * CLI apuntan a `(default)` si no se les dice otra cosa, así que este valor
 * tiene que coincidir con tres sitios:
 *
 *   - el nombre que aparece en la consola de Firebase,
 *   - el campo `database` de firebase.json,
 *   - el segundo argumento de getFirestore() en auth.js.
 *
 * Si no coinciden, la app no falla al arrancar: falla al leer o escribir, con
 * un error de permisos que hace pensar en las reglas. Por eso vive aquí solo.
 */
export const DATABASE_ID = 'bd-iv-itsanet';

/** Versión del SDK de Firebase que carga la app. */
export const SDK = '10.14.1';
