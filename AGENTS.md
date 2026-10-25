# Instrucciones de desarrollo

Consulta README.md y CONTRIBUTING.md antes de modificar el editor.

- No editar documentos del usuario ni sus registros para probar funciones. Utilizar carpetas temporales.
- Todas las escrituras de proyectos pasan por SafeStore; mantener respaldo verificado, reemplazo atómico y control de conflictos.
- No borrar ni modificar manualmente .latex-local/ de proyectos reales.
- Mantener el enlace a la carpeta original: si no está disponible, detener la operación.
- Compilar el archivo principal configurado; no sustituirlo por el capítulo abierto.
- Conservar las licencias de frontend/vendor y evitar dependencias CDN.
- Ejecutar ./scripts/test.sh con Python, Node y TeX disponibles.
- No incorporar proyectos personales, secretos, rutas absolutas de usuarios ni catálogos de investigación.
