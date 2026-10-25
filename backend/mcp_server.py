#!/usr/bin/env python3
"""
Servidor MCP para el editor LaTeX local.
Expone herramientas de compilación y gestión de archivos a agentes de IA.

Instalación:
    pip install mcp

Configuración en Claude Code (~/.claude.json o claude_desktop_config.json):
    {
      "mcpServers": {
        "latex-local": {
          "command": "python",
          "args": ["/ruta/a/latex-local/backend/mcp_server.py"]
        }
      }
    }
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP
from compiler import compile_latex
from projects import ProjectManager

PROJECTS_DIR = Path(os.environ.get('LATEX_PROJECTS_DIR', Path(__file__).resolve().parent.parent / 'projects')).expanduser()
pm = ProjectManager(PROJECTS_DIR)

mcp = FastMCP("latex-local", instructions=(
    "Servidor MCP para compilar y editar proyectos LaTeX locales. "
    "Usa compile_project para generar PDFs y read_file/write_file para editar fuentes."
))


@mcp.tool()
def list_projects() -> str:
    """Lista todos los proyectos LaTeX disponibles con su configuración."""
    projects = pm.list_projects()
    if not projects:
        return "No hay proyectos disponibles."
    lines = []
    for p in projects:
        linked = f" → {p['linked_path']}" if p.get("linked") else ""
        cfg = p.get("config", {})
        lines.append(
            f"• {p['name']}  ({p['file_count']} archivos){linked}\n"
            f"  engine={cfg.get('engine','pdflatex')}  "
            f"mode={cfg.get('mode','final')}  "
            f"passes={cfg.get('passes',1)}  "
            f"main={cfg.get('main_file','main.tex')}"
        )
    return "\n".join(lines)


@mcp.tool()
def compile_project(
    project: str,
    engine: str = "pdflatex",
    mode: str = "final",
    passes: int = 1,
    main_file: str = "main.tex",
) -> str:
    """
    Compila un proyecto LaTeX y devuelve el resultado.

    Args:
        project:   Nombre del proyecto (ver list_projects).
        engine:    Motor LaTeX: pdflatex | xelatex | lualatex.
        mode:      final (genera PDF) | draft (sin PDF, más rápido).
        passes:    Número de pasadas (2-3 para resolver referencias cruzadas).
        main_file: Archivo .tex principal (relativo a la raíz del proyecto).
    """
    project_dir = pm._effective_dir(project)
    if not project_dir.exists():
        return f"Error: proyecto '{project}' no encontrado."

    result = asyncio.run(compile_latex(project_dir, main_file, engine, mode, passes))

    if result.success:
        return (
            f"✓ Compilado en {result.duration:.1f}s\n"
            f"PDF: {result.pdf_path or '(draft — sin PDF)'}"
        )

    lines = result.log.splitlines()
    bang_idx = next((i for i, l in enumerate(lines) if l.startswith("!")), None)
    if bang_idx is not None:
        context = "\n".join(lines[bang_idx: bang_idx + 8])
    else:
        context = "\n".join(lines[-20:])
    return f"✗ Error de compilación:\n\n{context}"


@mcp.tool()
def read_file(project: str, file_path: str) -> str:
    """
    Lee el contenido de un archivo en el proyecto.

    Args:
        project:   Nombre del proyecto.
        file_path: Ruta relativa al archivo (ej: 'main.tex', 'sections/intro.tex').
    """
    try:
        return pm.read_file(project, file_path)
    except FileNotFoundError:
        return f"Error: archivo '{file_path}' no encontrado en '{project}'."


@mcp.tool()
def write_file(project: str, file_path: str, content: str) -> str:
    """
    Escribe o reemplaza el contenido de un archivo en el proyecto.

    Args:
        project:   Nombre del proyecto.
        file_path: Ruta relativa al archivo.
        content:   Contenido completo a escribir.
    """
    try:
        pm.write_file(project, file_path, content)
        return f"ok — '{file_path}' guardado en '{project}'."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def list_files(project: str) -> str:
    """
    Lista todos los archivos de un proyecto (lista plana, sin carpetas).

    Args:
        project: Nombre del proyecto.
    """
    try:
        files = pm.list_files(project)
        if not files:
            return "El proyecto no tiene archivos."
        return "\n".join(f["path"] for f in files)
    except FileNotFoundError:
        return f"Error: proyecto '{project}' no encontrado."


@mcp.tool()
def list_dir(project: str, path: str = "") -> str:
    """
    Lista el contenido inmediato de un directorio dentro del proyecto.

    Args:
        project: Nombre del proyecto.
        path:    Subdirectorio relativo (vacío = raíz del proyecto).
    """
    try:
        entries = pm.list_dir(project, path)
        if not entries:
            return "Directorio vacío."
        lines = []
        for e in entries:
            if e["type"] == "dir":
                lines.append(f"📁  {e['path']}/")
            else:
                size_kb = e.get("size", 0) / 1024
                lines.append(f"📄  {e['path']}  ({size_kb:.1f} KB)")
        return "\n".join(lines)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: {e}"


@mcp.tool()
def get_project_config(project: str) -> str:
    """
    Devuelve la configuración actual del proyecto (motor, modo, pasadas, archivo principal).

    Args:
        project: Nombre del proyecto.
    """
    import json
    cfg = pm.get_config(project)
    return json.dumps(cfg, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
