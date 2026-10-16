# Cámara en vivo en el servidor

Firebase Hosting ya ofrecía HTTPS. El mismo permiso de cámara se necesita al
servir la aplicación desde la bodega. `http://localhost:3002` es una excepción
segura en el propio computador; `localhost` en el móvil apunta al teléfono.
`http://192.168.4.94:3002` no es un origen seguro para la cámara.

El botón Cámara utiliza video continuo: detector nativo, o ZXing local sobre
los fotogramas si el navegador no tiene `BarcodeDetector`. El lector no sube
video, no toma una foto para buscar y no registra unidades automáticamente.
Se pausa al abrir la ficha para no reemplazar los datos que se están editando.
Las fotos opcionales de evidencia se conservan por separado.

## Cámara de la PC sobre los registros de producción

La captura de desarrollo muestra `localhost:3003`, que Chrome considera seguro.
Para usar esa excepción en una PC autorizada con acceso SSH al servidor, abrir
**PowerShell de Windows en la PC**, fuera de la sesión SSH existente, y ejecutar:

```powershell
ssh -N -L 127.0.0.1:3004:127.0.0.1:3002 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 enicolalde@192.168.4.94
```

Conservar la comprobación de identidad SSH habitual y utilizar el acceso del
servidor. Cuando termine la autenticación, el comando queda esperando: mantener
esa ventana abierta. Abrir `http://localhost:3004/app/` e iniciar sesión con la
cuenta habitual de producción. La cámara solicita permiso para localhost.
El túnel solo escucha en esa PC y transmite al mismo servicio real; no ejecuta
Docker ni copia bases, y no requiere reiniciar `iv-itsanet`. El puerto 3003 sigue
siendo desarrollo; el 3004 se reserva aquí para el acceso a producción.
Cerrar con Ctrl+C al terminar. Si el puerto está ocupado, usar otro libre; si SSH
rechaza el reenvío, TI debe autorizarlo o habilitar HTTPS. Este acceso sirve para
PCs con SSH autorizado; los teléfonos necesitan su dirección HTTPS confiable.

## Fotos mediante la cámara del sistema

En bultos, **Cámara del equipo** utiliza un selector de imagen con captura nativa
(`capture="environment"`). Android/iOS pueden abrir su cámara y devolver la foto
a la recepción, sin depender del visor de video de la página. La imagen utiliza
la misma compresión, vinculación al bulto/packing list, control de versión y cola
Drive de las demás evidencias. La selección no registra unidades ni modifica el
conteo. Si no hay cámara web disponible, **Tomar foto** ofrece esta captura.

En Windows se ofrece **Cámara de Windows**, que solicita abrir la aplicación
del sistema mediante su enlace registrado. Tomar la foto y seleccionarla desde **Galería**, normalmente
en Imágenes → Álbum de cámara. Una página no puede leer automáticamente esa
carpeta ni recuperar archivos sin selección o autorización del usuario. El
selector nativo es para fotos de evidencia; el escaneo continuo permanece en
el visor de video. Abrir ITSANET como PWA no cambia el requisito de origen seguro.

## Habilitar el acceso seguro sin cambiar otros proyectos

Si la empresa ya ofrece una URL HTTPS para esta aplicación, utilizarla. Debe
dirigir todas las rutas `/app/` y `/api/` al mismo servicio; no apuntar el frontend
HTTPS a una API HTTP desde el navegador. Conservar la configuración de los
otros sitios del servidor.

### Solicitud concreta para TI

La URL operativa actual es `http://192.168.4.94:3002/app/`. Proporcionar un
nombre DNS interno que resuelva a ese servidor y un certificado válido para ese
nombre. Los teléfonos deben confiar en la CA emisora. Si es una CA corporativa,
distribuirla a los dispositivos; omitir la advertencia del navegador no basta.
El certificado no lo puede instalar ni hacer confiable la aplicación web.

Preferir un proxy HTTPS del mismo servidor en el puerto 443, manteniendo Uvicorn
en HTTP/3002 para conservar las comprobaciones y el procedimiento de actualización
actuales. Enrutar **toda** la aplicación, incluidas `/app/`, `/api/`, las descargas
y las fotos; no cambiar solo el enlace del botón Cámara. El proxy debe reenviar
`Host`, `X-Forwarded-Proto` y la dirección de origen. Permitir cargas del tamaño
admitido por la app (incluido base64); el límite de 1 MB de algunos proxies
rechaza fotos. Revisar DNS y acceso desde la WiFi real de bodega. No requiere
abrir la aplicación a Internet ni modificar Drive, MySQL o las credenciales de Google.

TI debe comprobar `https://DOMINIO/health` y `https://DOMINIO/app/` sin errores de
certificado. Después probar con un móvil real: permitir Cámara para ese sitio,
leer un código del packing list en video continuo y cerrar el visor para comprobar
que se apaga la cámara. El operador confirma cada conteo como hasta ahora.
Si también se usa login Google, registrar la URI OAuth HTTPS exacta del dominio.

### Alternativa: TLS directamente en Uvicorn

Si solo existe la IP interna, TI puede emitir un certificado para la IP
`192.168.4.94` (Subject Alternative Name de tipo IP) mediante una CA corporativa
confiable en los teléfonos, o proporcionar un dominio con certificado válido.
Una advertencia por certificado no confiable no equivale a una instalación
correcta. No desactivar la seguridad del navegador para operar.

El servicio Uvicorn instalado admite TLS directamente en su puerto 3002. Para
activarlo cuando ya estén disponibles el certificado y la clave correspondiente,
un administrador agrega en `/etc/iv-itsanet.env` mediante `sudoedit`:

```dotenv
UVICORN_SSL_CERTFILE=/ruta/privada/certificado-fullchain.pem
UVICORN_SSL_KEYFILE=/ruta/privada/clave-privada.pem
```

Los archivos deben ser legibles por el usuario del servicio. La clave privada
no se publica en Git ni en la carpeta web. Conservar el resto de las variables.
Esta configuración cambia **solo IV_ITSANET en el 3002** a HTTPS: los dispositivos
deben abrir la nueva dirección y volver a iniciar sesión. Elegir el momento del
cambio, ya que la URL HTTP de ese puerto deja de servir la aplicación.

El procedimiento actual `actualizar_produccion.sh` verifica HTTP/3002. Antes de
elegir TLS directo se debe adaptar esa comprobación a la URL HTTPS y a su CA;
el proxy en 443 evita ese cambio. No habilitar TLS directo y ejecutar después
el procedimiento HTTP sin adaptarlo, porque no confirmaría el arranque.

```bash
sudo systemctl restart iv-itsanet
curl --cacert /ruta/ca-corporativa.pem --retry 8 --retry-connrefused \
  --retry-delay 1 --max-time 5 -fsS https://192.168.4.94:3002/health
```

Con un certificado emitido por una CA pública ya reconocida, usar el dominio
autorizado y omitir `--cacert`. No usar `curl -k`. Los puertos 3000, 8080 y SSH
no se cambian. No es necesario modificar MySQL ni instalar otro servidor web.

## Comprobación desde el teléfono

1. Conectarse a la WiFi de bodega y abrir `https://192.168.4.94:3002/app/` o el
   dominio autorizado, sin advertencias de certificado.
2. Entrar, abrir una recepción y tocar Cámara. Permitir el acceso a la cámara.
3. Enfocar un código: se abre su ficha. Revisarla y confirmar el conteo.
4. Apagar la cámara o cambiar de pestaña: el indicador del teléfono debe apagarse.

La cámara en vivo no necesita Client ID/Client secret de Google ni el puente
de Drive. Esas credenciales corresponden al login y al envío de informes.
