# Trabajar desde el servidor de la bodega

`http://192.168.4.94:3002/app/`

Esa dirección sirve la **misma aplicación** que `iv-itsanet.web.app`. Lo que
cambia es dónde van los datos: a MySQL en el servidor, no a Firestore.

## Cómo decide la aplicación a quién hablarle

Por la dirección. El servidor la sirve bajo `/app/`; el hosting de Firebase la
sirve en la raíz. No hay nada que configurar ni ningún interruptor del que
acordarse al desplegar.

Para probar los dos destinos desde el mismo sitio, en la consola del navegador:

```js
localStorage.setItem('itsanet.modo', 'local');  // al servidor
localStorage.setItem('itsanet.modo', 'nube');   // a Firestore
localStorage.removeItem('itsanet.modo');        // que decida la dirección
```

## Qué cambia para el operario

Nada en la pantalla de validación: el escáner, el packing list, los pallets, los
duplicados, el informe y los CSV son el mismo código.

En el acceso, dos cosas:

- **No hay botón de Google.** Entrar con Google necesita Internet, que es justo
  de lo que el servidor nos libera. Se entra con usuario y contraseña.
- **No hay registro abierto.** Contra el servidor, a los operarios los da de
  alta un supervisor.

Y una que se nota en el reloj: lo que varios operarios cuentan en la misma
recepción tarda unos segundos en aparecer en la pantalla de los demás. Firestore
lo empujaba; sobre HTTP hay que preguntar, y se pregunta cada cuatro segundos
—solo cuando la pestaña está a la vista, para no gastar batería consultando para
nadie—. Se avisa únicamente cuando algo cambió de verdad: repintar la tabla
entera cada cuatro segundos le haría perder el sitio a quien está mirando.

## Qué NO se ha perdido

Las cuatro reglas que costó descubrir siguen puestas, y cada una está probada
rompiéndola a propósito:

1. **22 filas = 22 filas.** Lo que llega sin estar en el packing list no añade
   filas: vive aparte, como adicional.
2. **El reparto por lista.** Dos packing lists con el mismo SKU no se mezclan:
   lo contado se imputa a la lista que dice el operario.
3. **La clave de idempotencia.** Repetir un escaneo tras un corte de red no
   cuenta dos veces.
4. **Nada se edita ni se borra.** Una anulación es otro evento, compensatorio.

Y una quinta que el modelo nuevo permite afirmar: el total de un SKU existe por
velocidad, pero la verdad son los eventos. `recalcular_sku` lo rearma desde el
libro mayor y una prueba comprueba que no discrepaban.

## Dar de alta a los operarios en el servidor

```bash
cd ~/bryan/IV_ITSANET
set -a && . /etc/iv-itsanet.env && set +a
.venv/bin/python scripts/crear_operador.py        # pregunta usuario, nombre y rol
```

O importando lo que ya hay en Firestore:

```bash
.venv/bin/python scripts/importar_firestore.py --ensayo   # mira, no escribe
.venv/bin/python scripts/importar_firestore.py
```

Las contraseñas de Firebase **no se pueden exportar**: son hashes de Google. A
quien se importe hay que darle una contraseña nueva, y la cambia al entrar.

## Comprobar que las dos mitades hablan el mismo idioma

```bash
bash scripts/probar-extremo-a-extremo.sh
```

Levanta el servidor con una base de pruebas —nunca toca la de producción— y
ejecuta contra él el mismo `js/local.js` que corre en el handheld. Es lo que
cubre el hueco entre las otras dos suites: que las rutas, los verbos y los
nombres de campo coincidan. Un `/conteos` donde el servidor espera `/conteo`, o
un `porOrigen` que allí se llame `por_origen`, pasa las dos suites y falla en el
almacén.

Las comprobaciones estáticas cuidan lo mismo por el otro lado: si alguien añade
una función de datos y no la enseña al servidor, `paginas.test.mjs` lo dice
—«esa pantalla se queda muda»— en vez de dejar que se descubra en la bodega.

## Lo que todavía va por la nube

El **Apps Script** sigue haciendo tres cosas que el servidor no hace: guardar
los informes y las fotos en Drive, mandar el correo del cierre y hablar con
Depot para el panel del supervisor. Eso necesita Internet.

En el handheld, sin Internet, se puede validar y cerrar; subir la evidencia a
Drive y mandar el correo se quedan esperando a que haya red. No bloquea el
conteo, que es lo que no puede parar.

## Lo que falta

- **Cola sin conexión.** Si la red del almacén se cae a mitad de un conteo, la
  aplicación avisa pero no guarda el escaneo para mandarlo después. Si la
  evaluación con los handhelds encuentra zonas sin cobertura, esto pasa a ser lo
  primero; si no, no hace falta.
- **Los KPI** siguen leyendo de Firestore. La pantalla del supervisor se migra
  después de que los operarios estén validando contra el servidor.
