# Guías de usuario por función

Los paquetes HTML y PDF contienen seis documentos:

- Manual de usuario completo, con navegación por función.
- Guía rápida del operador y del supervisor: una página en PDF.
- Guía del operador, con sus procedimientos y capturas.
- Guía del supervisor, desde el packing list hasta el informe y el correo.
- Guía de ayuda: diez situaciones frecuentes y tres páginas en PDF.
- Glosario de 42 términos con explicaciones sencillas.

La guía completa conserva los 38 procedimientos y las 67 imágenes originales
(incluido el logo). Las capturas mantienen su contenido; las guías muestran una
tarea a la vez y tienen búsqueda. Las indicaciones de acceso se refieren al
trabajo en la bodega y al equipo asignado.

## Descargar y abrir

1. Descarga el ZIP del formato que necesites y descomprímelo.
2. Abre `Descargar-guias-HTML.html` o `Descargar-guias-PDF.html` en Chrome o Edge.
3. Introduce la misma clave documental utilizada en la entrega anterior.
4. Descarga `Manual-usuario-IV-ITSANET.html` para consultar todas las guías desde
   una sola página. También puedes descargar únicamente el documento de tu rol.

El HTML principal incluye sus imágenes y funciona sin recursos externos. Para
seguir los enlaces de un HTML separado al manual completo, guarda los HTML de
la entrega en una misma carpeta. Cada PDF se puede consultar por separado.

Los paquetes están cifrados porque contienen las capturas reales aprobadas. El
HTML descargado es el documento legible para distribuir en el ámbito interno.
La clave documental no es una credencial de acceso al aplicativo.

## Publicar en el servidor del sistema

`scripts/instalar_guias_usuario.py` obtiene los paquetes de una revisión fija de
Git, solicita la clave sin mostrarla, valida las huellas y publica el HTML/PDF
del manual principal. Conserva la versión anterior y el manual técnico privado.
No actualiza el código del aplicativo, reinicia servicios ni modifica SQL.

Acceso con sesión del aplicativo:

- `/api/app/manuales/usuario/html`
- `/api/app/manuales/usuario/html?descargar=true`
- `/api/app/manuales/usuario/pdf?descargar=true`

La publicación se realiza después de ejecutar el instalador en el servidor.
Los paquetes descargables de esta carpeta ya contienen los documentos nuevos.
