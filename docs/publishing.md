# Publicar la versión inicial

La carpeta está preparada para crear un repositorio llamado, por ejemplo, `latex-local`. No hace falta incluir los documentos que editas con la aplicación.

1. Revisa `git status --short` y el contenido que vas a publicar. `projects/`, `workspace.json`, `.venv/` y `.latex-local/` están excluidos.
2. Crea en GitHub un repositorio vacío con el nombre y la visibilidad que prefieras. No añadas otro README o licencia desde GitHub.
3. Desde esta carpeta, conecta el remoto y publica:

```bash
git remote add origin https://github.com/TU_USUARIO/latex-local.git
git push -u origin main
```

Si descargaste un ZIP sin historial de Git, ejecuta primero:

```bash
git init -b main
git add .
git commit -m "Initial release: LaTeX Local 0.1.0"
```

Después de pasar las verificaciones, puedes crear una etiqueta y una release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

El proyecto incluye licencia MIT y los avisos de CodeMirror y PDF.js. No elimines esas licencias. El catálogo de referencias incluido está vacío; los datos de las pruebas y los ejemplos están identificados como sintéticos.

`.gitignore` previene incorporaciones accidentales comunes; no puede detectar archivos personales que copies manualmente con otro nombre. Revisa siempre el contenido antes de publicar.
