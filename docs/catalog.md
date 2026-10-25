# Catálogo opcional de referencias

El archivo `backend/reference_catalog.json` empieza vacío. Puedes apuntar `LATEX_REFERENCE_CATALOG` a un JSON propio fuera del repositorio. Se lee al consultar o incorporar referencias; no requiere base de datos.

Cada elemento tiene esta forma (datos de prueba, no una publicación real):

```json
[
  {
    "id": "Ejemplo:Demo2026",
    "key": "Demo2026",
    "aliases": ["Demo2026"],
    "sources": ["Mi catálogo"],
    "title": "Referencia sintética de demostración",
    "description": "Solo ejemplo de formato",
    "dois": [],
    "bibtex": "@misc{Demo2026, title={Referencia sintética de demostración}, year={2026}}",
    "format": "BibTeX proporcionado por el usuario"
  }
]
```

Usa identificadores únicos y entradas BibTeX válidas; conserva la clave declarada en `key`. Los DOI de `dois` se escriben normalizados, sin URL y en minúsculas. La interfaz genera los filtros a partir de `sources`.

El editor comprueba la entrada contra la bibliografía activa antes de incorporarla y muestra la clave de cita existente cuando detecta un duplicado. No verifiques una referencia únicamente por su presencia en el catálogo: revisa siempre sus datos y procedencia.
