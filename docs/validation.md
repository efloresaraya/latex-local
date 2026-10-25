# Verificación de la distribución 0.1.0

Validada localmente en macOS sobre Apple Silicon con un entorno virtual nuevo,
instalando únicamente `requirements-dev.txt`.

- 108 pruebas Python aprobadas, incluidas compilaciones reales y SyncTeX.
- Cinco suites JavaScript aprobadas: citas, acentos, coordenadas del PDF,
  etiquetas y diferencias de versiones (incluyen 1000 casos aleatorios).
- CLI probado desde otra carpeta, con rutas que contienen espacios.
- Ejemplo mínimo compilado con bibliografía y capítulo externo.
- Interfaz y PDF comprobados en Chromium sin errores de JavaScript;
  catálogo vacío y filtros genéricos verificados.
- Dependencias coherentes según `pip check`; sintaxis de los lanzadores
  comprobada con `bash -n`.
- Privacidad del paquete y los metadatos: [revisión](privacy.md).
- Código distribuido revisado para excluir rutas personales, registro de
  proyectos, bibliografías privadas, respaldos y experimentos.

Las pruebas emiten avisos de deprecación de componentes de terceros, sin fallos.
El workflow para Ubuntu y Python 3.10/3.12 está incluido; su ejecución en GitHub
queda pendiente de publicar el repositorio. Windows nativo no está soportado.

## Entorno probado

- Python 3.10.19
- Node.js 24.22.1
- fastapi 0.162.0
- uvicorn 0.54.0
- httpx 0.28.1
- python-multipart 0.0.32
- pytest 9.1.1
- PyMuPDF 1.28.2
