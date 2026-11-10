# Versión 67 · carpetas, Recepciones y entrega técnica

## Carpetas utilizadas por archivos reales

Crear una recepción o agregar listas/embarques ya no programa la creación masiva
de directorios. La preparación de Drive consulta las carpetas existentes sin
materializar categorías. El primer archivo crea su ruta; un informe utiliza
INFORMES aunque no haya fotografías. Las categorías sin fotos no se precrean.

Se retiran las preparaciones antiguas que seguían pendientes, sin eliminar
archivos ni cambiar los reintentos de fotos. Con un Apps Script anterior el
servidor evita el preparador masivo; la vía Google central aplica el cambio al
actualizar el servidor, sin una implementación nueva por supervisor.

La primera copia confirmada fija la carpeta madre para seguir reutilizando su
ID ante cambios descriptivos de marca. Se conservan registros, referencias y
carpetas históricas: esta revisión no ejecuta una limpieza retroactiva ni traslada
evidencias. Una retirada/reclasificación o una copia interrumpida puede dejar una
ruta vacía; requiere revisión, no borrado masivo por nombre.

Los botones de Drive, galería y correo explican el estado previo al primer
archivo. Comprobar un correo sin carpeta no intenta actualizar un enlace vacío.
La copia de archivos sigue indicando estados y confirmaciones por separado.

## Recepciones y registro original

La lista incluye fecha y hora originales, presentadas en America/Guayaquil.
Permite buscar por código, cliente, marca, descripción, lista o embarque; combinar
estado y rango de fechas; ordenar por registro o código y limpiar los filtros.
El rango incluye las jornadas completas de Ecuador, independientemente de la
zona del navegador. No se cambia ni se deduce la fecha guardada.

La búsqueda del servidor revisa todo el histórico y devuelve páginas de 50
recepciones; las métricas se calculan para esa página. No queda limitada a las
50 más recientes. Se preserva el listado anterior usado por otras pantallas y
el recorte de Mis validaciones. La alternativa Firestore mantiene su consulta
existente y muestra cuántos documentos se cargaron.

## Manuales HTML autónomos

Abrir [entrega-v67/index.html](entrega-v67/index.html). Contiene:

- Informe técnico: arquitectura, infraestructura, conexiones, datos, seguridad,
  continuidad, dependencias y criterios de aceptación TI/Reingeniería.
- Manual operativo: operario y supervisor, ubicación, PNC, evidencia, informes,
  correo al ejecutivo y manejo de excepciones.
- Manual de administración: usuarios, Google central, monitor, diagnóstico,
  actualización, respaldo/restauración y transferencia de responsables.
- Inventario JSON generado del modelo y rutas del backend, sin importar la app,
  leer credenciales o conectarse a SQL/Google.

Cada HTML incluye búsqueda, navegación, tema, impresión/PDF y descarga. Las
listas de revisión exportan JSON local; no equivalen a una firma o aceptación
institucional. Se generan con `python scripts/generar_entrega_ti.py`.

La evidencia de recursos del 18/10/2026 se identifica como histórica. No se
certifica la versión instalada, capacidad actual, certificado, restauración ni
envío corporativo desde un entorno de desarrollo. El acta de aceptación recoge
esas comprobaciones.

## Aplicar

Usar el actualizador con respaldo y el commit completo publicado en la entrega.
Avisar pausa de registros y recargar los dispositivos para `20261023-67`.
V67 no requiere migración destructiva, reimportar recepciones ni recrear usuarios.
