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

## Habilitar el acceso seguro sin cambiar otros proyectos

Si la empresa ya ofrece una URL HTTPS para esta aplicación, utilizarla. Debe
dirigir todas las rutas `/app/` y `/api/` al mismo servicio; no apuntar el frontend
HTTPS a una API HTTP desde el navegador. Conservar la configuración de los
otros sitios del servidor.

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
