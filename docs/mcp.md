# Servidor MCP opcional

Instala las dependencias adicionales en el mismo entorno:

```bash
source .venv/bin/activate
python -m pip install -r requirements-mcp.txt
```

Añade a la configuración de tu cliente MCP un servidor por `stdio`, sustituyendo ambas rutas por las de tu instalación:

```json
{
  "mcpServers": {
    "latex-local": {
      "command": "/ruta/a/latex-local/.venv/bin/python",
      "args": ["/ruta/a/latex-local/backend/mcp_server.py"],
      "env": {"LATEX_PROJECTS_DIR": "/ruta/a/mi-registro-local"}
    }
  }
}
```

Para compartir proyectos con la interfaz, utiliza el mismo `LATEX_PROJECTS_DIR` en ambos procesos; si lo omites en ambos, comparten `projects/` del repositorio. Incluye los binarios de TeX en el `PATH` del cliente; en macOS suele ser `/Library/TeX/texbin`.

El servidor ofrece lectura, escritura, compilación y gestión de proyectos. Las escrituras utilizan el almacenamiento protegido. Dale acceso solo a los proyectos que quieras editar desde ese cliente.
