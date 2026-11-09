# IV ITSANET · Descarga alternativa de manuales y correo

Se preparó esta vía para evitar el visor de artefactos de la conversación. Los documentos están cifrados: las capturas operativas y el manual técnico no se publican en texto claro. La clave se entrega por separado al responsable, nunca en el repositorio.

- [Descargar PDF y correo](https://github.com/brantos102/IV_ITSANET/raw/refs/heads/desarrollo-local/docs/descargas/IV-ITSANET-PDF-y-correo-38.zip).
- [Descargar manuales HTML](https://github.com/brantos102/IV_ITSANET/raw/refs/heads/desarrollo-local/docs/descargas/IV-ITSANET-HTML-38.zip).

1. Descarga el ZIP desde GitHub usando tu navegador.
2. En Windows, clic derecho → **Extraer todo**.
3. Abre el HTML extraído con Chrome o Edge. Introduce la clave entregada por el canal privado y pulsa **Mostrar archivos**.
4. Descarga cada documento con su botón. No utiliza el visor de archivos del chat.

El paquete PDF permite descargar además un borrador `.eml` con los dos PDF adjuntos. Completa destinatarios y firma antes de enviar. Para Gmail web, copia el texto mostrado y adjunta los dos PDF descargados.

El manual de usuario contiene **38 pasos**. El manual técnico describe Apache, FastAPI/Uvicorn, MySQL, las integraciones de Google, el mantenimiento y el diccionario de 31 tablas, 274 campos y 33 claves externas. Distingue las relaciones físicas de los vínculos resueltos por la aplicación. Las imágenes de referencia se identifican en el manual de usuario.

Todo el desbloqueo y la descarga se ejecutan localmente en el navegador. La clave no se envía por red. Los archivos descargados verifican su SHA-256. Se utiliza AES-256-GCM y PBKDF2-SHA256 con sal y nonce independientes por paquete.

El correo es un borrador con destinatarios y firma por completar. La documentación se basa en el código y la evidencia técnica fechada del servidor. La verificación funcional se ejecuta en un entorno aislado; las mediciones de carga se presentan por separado. La publicación en el servidor sigue el [procedimiento documentado](../entrega-v72/README.md).
