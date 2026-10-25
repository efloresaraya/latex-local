# Contribuir

Trabaja sobre una rama y ejecuta `./scripts/test.sh` antes de proponer cambios. Instala `requirements-dev.txt`, Node.js 18+ y TeX Live/MacTeX con IEEEtran.

- Mantén todos los guardados, importaciones y restauraciones dentro de `SafeStore`.
- Conserva las comprobaciones de revisión y las pruebas de concurrencia; un conflicto no debe provocar una sobrescritura automática.
- Usa proyectos temporales y datos sintéticos en las pruebas.
- No añadas documentos, rutas de usuario, proyectos vinculados ni respaldos al repositorio.
- Conserva las licencias y sirve las dependencias de interfaz localmente.
- Describe el comportamiento cambiado y la validación realizada en cada propuesta.

La aplicación usa módulos Python del directorio `backend/` y JavaScript sin proceso de empaquetado. No necesita npm para ejecutarse.
