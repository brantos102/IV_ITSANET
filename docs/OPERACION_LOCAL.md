# Operacion completa en el servidor (3002)

La interfaz para credenciales, Google y validacion movil se documenta en
[MEJORAS_MOVIL.md](MEJORAS_MOVIL.md). El panel ADMIN ahora permite configurar
las conexiones sin editar el archivo de entorno; sus valores prevalecen
sobre las variables cuando hay configuracion guardada.

Para la versión actual: [GOOGLE_Y_FORMATOS.md](GOOGLE_Y_FORMATOS.md) detalla
el remitente por supervisor, OAuth, los modelos Depot y la dependencia Pillow.

La aplicacion existente se conserva. `/` abre `/app/`; el prototipo anterior
queda disponible en `/prototipo`. La ruta `/app/` usa la sesion y la API local,
aunque el navegador conserve una antigua preferencia `itsanet.modo=nube`.

## Destino de cada dato

- MySQL: usuarios, aprobaciones, recepciones, lineas originales, conteos,
  anulaciones, auditoria, preferencias CSV e instantaneas de entrega.
- Drive: fotos de novedades, carpeta por recepcion y copias de informes para el
  ejecutivo. MySQL solo guarda metadatos, ID y enlace de los archivos; nunca BLOB.
- Disco del servicio: informes y fotos pendientes de copiar a Drive. La foto
  temporal se elimina solo despues de persistir en MySQL el ID confirmado de
  Drive. Si Google falla, el archivo permanece disponible en el servidor.
- Sheets: ninguna escritura operativa ni actualizacion del Sheet anterior.
  Solo se crea un libro nuevo si el supervisor solicita expresamente esa
  exportacion al finalizar una recepcion. La fuente es la instantanea de MySQL.

Excel conserva las filas y el formato del packing list recibido. Los KPI se
exportan a Excel/PDF desde los datos de la API local. El paquete incluye las
bibliotecas del navegador: no se descargan SDK, Excel, PDF ni fuentes de un CDN.
Para regenerarlas durante desarrollo: `npm ci && npm run build:frontend`.
No hace falta ejecutar npm en el servidor para desplegar estos archivos.

El cierre local guarda los informes antes de cerrar y confirma la recepcion y
su entrega pendiente en una misma transaccion. Si otro operario registra un
movimiento mientras se genera el informe, se rechaza el cierre para regenerar
la version actual. Los conteos concurrentes bloquean el agregado por recepcion
con lecturas actuales de InnoDB, incluso despues de la lectura de autenticacion.

## 1. Actualizar solo IV_ITSANET

En la terminal **SSH de VS Code**, dentro del servidor:

```bash
cd ~/bryan/IV_ITSANET
git status --short
git pull --ff-only origin pr_bep/serene-thompson-10qlxd
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart iv-itsanet
curl --retry 8 --retry-connrefused --retry-delay 1 --max-time 5 -fsS \
  http://127.0.0.1:3002/health
```

No se reimporta ningun historico. No ejecutar scripts que creen otra base ni
`git reset --hard`. Conservar el cambio local existente en
`mysql/01-crear-base.sql`. Los cambios nuevos no modifican ese archivo.
`init_db()` crea las nuevas tablas `app_archivos`, `app_config`, `app_entregas`
sin borrar las existentes. El usuario MySQL necesita CREATE/INDEX en su propia
base y los permisos de actualizacion de esquema ya documentados.

Se conserva el servicio instalado, `/etc/iv-itsanet.env`, el puerto 3002,
los demas proyectos, los puertos 3000/8080 y SSH. No reinstalar el servicio con
`scripts/servicio.sh`: el servicio actual ya esta funcionando. systemd lee el
archivo protegido; no ejecutar `. /etc/iv-itsanet.env` ni hacerlo publico.

Computador con reenvio SSH: `http://localhost:3002/`.
Handheld conectado a la LAN: `http://192.168.4.94:3002/`.
`localhost` en el telefono apunta al propio telefono. Escaner fisico, teclado
y seleccion de fotos funcionan por HTTP; la camara en vivo con getUserMedia
requiere HTTPS, o un navegador que considere seguro ese origen.

## 2. Activar Drive/correo conservando el Apps Script actual

El despliegue `/exec` existente autentica usuarios de Firebase. Una sesion
local no se puede usar como token de Firebase. El puente nuevo autentica
exclusivamente las entregas del servidor mediante HMAC-SHA256 y caducidad de
cinco minutos. La clave nunca se envia al navegador ni se guarda en GitHub.
No permite administrar clientes ni llamar al WMS por esa ruta.

1. En el mismo proyecto Apps Script de la captura, sustituir **Codigo.gs**
   con el contenido actualizado de `apps-script/proxy/Proxy.gs`.
   `apps-script/proxy/Clientes.gs` corresponde a **Clientes.gs** y se conserva.
   Agregar **Servidor.gs** con `apps-script/proxy/Servidor.gs`. No eliminar
   propiedades existentes como `CARPETA_EVIDENCIAS` ni credenciales de Depot.
2. En SSH, generar/configurar la clave solo para este servicio:

   ```bash
   cd ~/bryan/IV_ITSANET
   sudo .venv/bin/python scripts/configurar_google.py
   ```

   El comando conserva las otras variables y permisos privados de
   `/etc/iv-itsanet.env`. Repetirlo conserva la misma clave. La clave se muestra
   **solo en esa terminal** para copiarla en las propiedades del script como
   **SERVIDOR_HMAC**. No pegar esa salida en el chat. La URL configurada es:

   `https://script.google.com/macros/s/AKfycbzFIs_s0B83ZqmayIVoOXi1SEJox_McRxHSmFEDcWHGy3kG5C6Rs20qRKD5MASZjEoG/exec`

3. Apps Script: **Implementar → Administrar implementaciones → Editar → Nueva
   version → Implementar** sobre el despliegue existente, conservando su URL.
   Ejecutar como el propietario y conservar el acceso que usa el proxy actual.
   Autorizar Drive/correo y, si se requiere la exportacion opcional, Sheets.
4. Reiniciar solamente `sudo systemctl restart iv-itsanet`. En Administracion
   aparecera el puente configurado y la lista de **Entregas al ejecutivo**.

No hay que configurar FIREBASE_API_KEY para la ruta del servidor. La ruta
Firebase anterior mantiene su autenticacion para no romperla durante la prueba.
El Sheet compartido anteriormente no se utiliza ni se modifica.

## 3. Comprobacion operativa con una recepcion nueva

1. Entrar como administrador y comprobar que Administracion muestra **MYSQL**
   y el maestro esperado. Crear un usuario de prueba: permanece pendiente
   hasta que un supervisor lo apruebe en Usuarios.
2. Crear una recepcion de prueba y cargar un packing list conocido. Comprobar
   numero de filas, codigos y cantidades, incluso si hay ITEM y COD. PRODUCTO.
3. Abrir la misma recepcion en dos dispositivos. Contar en pallets distintos,
   verificar que la suma incluya ambos operarios y repetir una peticion para
   comprobar que no duplica el movimiento. Probar una anulacion con motivo.
4. Registrar una novedad PNC y foto. Verificar que se puede volver a consultar.
5. Completar todas las referencias (o declarar No aparecio con motivo).
   Finalizar, elegir informe y destinatario de prueba. Continuar **sin Sheets**
   para comprobar que no depende de el. Revisar la descarga de Excel.
6. Administracion → Entregas: esperar **ENTREGADA** y abrir la carpeta Drive.
   Revisar informes, subcarpeta `imagenes`, correo recibido, adjuntos y enlaces.
   **PENDIENTE** significa que no se confirmo la entrega: permite reintentar y
   conserva los archivos. **REVISION** exige comprobar el correo del remitente:
   no se reenvia automaticamente un mensaje cuya confirmacion se interrumpio.
7. Abrir Indicadores y exportar Excel/PDF. Si se necesita presentar en Sheets,
   probar esa opcion con otra recepcion nueva: debe crear un libro nuevo,
   sin escribir en el documento usado por el sistema anterior.

La app local puede contar y cerrar aunque Google no este configurado; en ese
caso muestra la entrega pendiente, nunca un correo falsamente enviado.
Los enlaces Drive conservan los permisos de la carpeta de la empresa: el
puente no convierte las fotos en publicas. Confirmar que el ejecutivo tiene
acceso con su cuenta.

## 4. Retirar Firebase despues de la prueba

Este cambio no apaga ni borra Firebase. Tras comprobar acceso de los operarios,
conteos, aprobacion, fotos e informe recibido, distribuir la URL LAN y retirar
el enlace anterior. Detener solo Hosting evita dos puntos de entrada:

```bash
cd ~/bryan/IV_ITSANET/firebase
npx --yes --package=firebase-tools@15.34.0 firebase hosting:disable --project iv-itsanet
```

Ese ultimo comando necesita una sesion CLI autorizada y deja de servir el
sitio Firebase. No ejecutarlo antes de completar la comprobacion. No elimina
Firestore, usuarios ni archivos: se podra resolver su retirada por separado.
No se requiere publicar en Firebase para actualizar la aplicacion LAN.
