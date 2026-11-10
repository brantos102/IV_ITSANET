# Actualizar registro, correo y aprobacion

Esta actualizacion conserva el historico ya migrado. No se vuelve a importar
Firestore ni se recrea la base. Los usuarios existentes conservan su ID, su
contrasena, su rol y su estado activo/inactivo.

## Servidor empresarial, puerto 3002

Con un respaldo recuperable de la base disponible, desde la terminal remota de
VS Code:

```bash
cd ~/bryan/IV_ITSANET
git status --short
git pull --ff-only origin pr_bep/serene-thompson-10qlxd
sudo systemctl restart iv-itsanet
curl --retry 8 --retry-connrefused --retry-delay 1 --max-time 5 -fsS \
  http://127.0.0.1:3002/health
```

Si hay cambios locales, conservarlos y revisarlos antes de actualizar. No usar
`git reset --hard`. La aplicacion se abre en `/app/`, no en la raiz del servidor.

Al arrancar, se comprueba `operadores.email`. Si falta en una instalacion
anterior, se agrega como `VARCHAR(160) NULL`, con su indice, sin rellenar ni
reescribir los datos existentes. La cuenta MySQL del servicio debe tener
permiso `ALTER` e `INDEX` sobre su propia base, como indica `mysql/01-crear-base.sql`.
Esta comprobacion es repetible. `create_all()` por si solo no actualiza columnas.

systemd carga `/etc/iv-itsanet.env`. No hay que leer ese archivo desde la
terminal del usuario ni cambiarle los permisos. Tampoco es necesario reinstalar
el servicio, modificar SSH, nginx, MySQL global o los puertos 3000 y 8080.

## Firebase operativo

La guia original `firebase/INSTALACION.md` ejecuta el despliegue desde la
terminal del computador. Tambien se puede publicar desde VS Code conectado por
SSH: el inicio de sesion debe usar `--no-localhost`.

Si aparece `firebase: command not found`, usar la CLI con `npx`, sin instalarla
globalmente ni cambiar las herramientas de los otros proyectos. Requiere Node
20 o superior y npm; comprobarlos con `node --version` y `npm --version`. Si esa
version no esta disponible en el servidor, ejecutar el despliegue desde el
computador con el repositorio actualizado, sin sustituir el Node del servidor.

Desde el servidor por SSH:

```bash
cd ~/bryan/IV_ITSANET/firebase
npx --yes --package=firebase-tools@15.34.0 firebase login --no-localhost
npx --yes --package=firebase-tools@15.34.0 firebase deploy --project iv-itsanet --only hosting,firestore:rules
```

Abrir en el navegador la URL que muestre la terminal y autorizar una cuenta
con permisos de despliegue en `iv-itsanet`. Completar la autorizacion en esa
terminal, nunca pegar codigos o tokens en el chat. No necesita `sudo`.
Esperar `Deploy complete!` antes de considerar publicado el cambio.

En el computador se usan los mismos comandos desde su carpeta `firebase` y
puede omitirse `--no-localhost`. No ejecutar `firebase init`: el repositorio ya
contiene el proyecto y la configuracion que deben conservarse.

Las reglas se publican junto al hosting porque el supervisor necesita permiso
para aprobar. El destino es la base nombrada `bd-iv-itsanet` de `firebase.json`.
No desplegar Functions ni sobrescribir datos para esta actualizacion.

El registro por formulario utiliza una sesion Firebase separada. Guarda la ficha
pendiente y el alias en un lote, antes de cerrar esa sesion: el observador del
acceso principal no puede interrumpir la escritura ni aprobarla por su cuenta.
Los usuarios nuevos aparecen en Usuarios sin recargar la pantalla.

## Comprobacion operativa

1. En el destino elegido, registrarse con un alias y un correo nuevos.
2. Antes de aprobar, el usuario no puede acceder a las recepciones.
3. Un SUPERVISOR entra en Usuarios, ve la solicitud y pulsa Aprobar.
4. El operario entra con el alias o el correo y la contrasena registrada.
5. Desactivarlo impide utilizar tambien su sesion anterior. Sus conteos se conservan.

Un supervisor no asigna roles ni modifica administradores. Un ADMIN puede
asignar roles, pero no quitarse su propio acceso. No se cambian estas reglas
desde el navegador: la API y Firestore las hacen cumplir.

El alta directa por un supervisor en el servidor equivale a su aprobacion y
crea un OPERADOR activo. Las cuentas importadas desactivadas necesitan ademas
una contrasena local utilizable: aprobar no convierte hashes de Firebase.
Si un correo aparece en varias fichas antiguas, se pide entrar por alias;
no se elige una cuenta ni se modifica automaticamente el historico.

## El corte entre Firebase y MySQL sigue pendiente

El hosting `https://iv-itsanet.web.app/` utiliza Firestore. El servidor bajo
`http://192.168.4.94:3002/app/` utiliza su base configurada. Aprobar en un destino
no sincroniza el otro. Publicar archivos de hosting no cambia donde escribe el
navegador, ni transfiere usuarios o conteos.

Para que el enlace HTTPS de Firebase escriba en MySQL hace falta una ruta HTTPS
alcanzable y una estrategia de autenticacion del mismo origen. `localhost` es
el dispositivo del operario, y una IP interna HTTP no sustituye esa ruta.
TI debe proporcionar esa entrada sin modificar los servicios de otros proyectos.
Antes del corte, identificar donde se siguen registrando datos y conciliarlos;
el historico ya migrado no debe reimportarse a ciegas.

La cola de escaneos sin WiFi, los KPI y las fotos/correos del proxy de Apps Script
siguen fuera de esta correccion de accesos. El proxy todavia requiere una sesion
Firebase; no se considera validado con la cookie local.
