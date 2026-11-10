# URL operativa y publicador HTTPS · 23/10/2026

El usuario confirmó como URL final de trabajo:

`https://apps.flexnetuio.com:8443/app/`

Esta dirección determina protocolo, nombre, puerto y ruta; no identifica el
software que termina TLS o sirve de intermediario. La referencia histórica a
Apache del 18/10/2026 se contrastó con nueva evidencia aportada por el usuario.

## Evidencia actual recibida

- `apache2` escucha en `*:8443`.
- `uvicorn` escucha en `0.0.0.0:3002`.
- La petición HEAD a `/app/` responde `HTTP/1.1 200 OK` con contenido HTML.
- La respuesta conserva `Server: uvicorn`, compatible con el reenvío por Apache.
- La hora HTTP `Fri, 23 Oct 2026 17:13:15 GMT` corresponde a las 12:13:15 de Ecuador.

Se confirma Apache como receptor del puerto 8443 y Uvicorn como proceso del
backend en 3002. La cabecera HTTP del backend no permite descartar el uso de
Apache. Las directivas de reenvío y el upstream exacto deben contrastarse con la
configuración, sin inferirlos únicamente desde la cabecera.

La salida compartida no incluye el resultado DNS ni la respuesta de `/health`.
El 200 de HTML no certifica el commit desplegado, SQL, autenticación o Google.

## Prueba externa y comprobaciones de lectura

Desde el entorno de revisión, DNS devolvió un error de resolución y la petición
HTTPS falló porque el proxy rechazó el túnel con 403. No fue una respuesta de
ITSANET; no permite concluir que la aplicación esté caída ni identificar Apache.

En la terminal corporativa, consultar sin reiniciar ni modificar servicios:

```bash
getent hosts apps.flexnetuio.com
sudo ss -ltnp '( sport = :8443 or sport = :3002 )'
curl --connect-timeout 5 --max-time 15 -sS -I https://apps.flexnetuio.com:8443/app/
curl --connect-timeout 5 --max-time 15 -fsS https://apps.flexnetuio.com:8443/health
```

Para completar el inventario, TI debe contrastar las directivas del virtual
host y upstream, la resolución DNS, `/health` y el certificado utilizado. Una
cabecera HTTP Server aislada es solo indicativa. Los bindings confirmados no
permiten deducir las reglas de firewall ni exposición desde otras redes.

Esta revisión cambia únicamente documentación. No modifica la aplicación,
DNS, certificados, puertos, proxy ni servicio corporativo.
