#!/usr/bin/env python3
"""CLI para el editor LaTeX local. No requiere el servidor web en ejecución."""
import argparse
import asyncio
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from compiler import compile_latex
from projects import ProjectManager

PROJECTS_DIR = Path(os.environ.get('LATEX_PROJECTS_DIR', Path(__file__).resolve().parent.parent / 'projects')).expanduser()
pm = ProjectManager(PROJECTS_DIR)


def cmd_list(args):
    projects = pm.list_projects()
    if not projects:
        print("No hay proyectos.")
        return
    for p in projects:
        linked = f"  →  {p['linked_path']}" if p.get("linked") else ""
        print(f"{p['name']}  ({p['file_count']} archivos){linked}")


def cmd_compile(args):
    try:
        project_dir = pm._effective_dir(args.project)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not project_dir.exists():
        print(f"Error: proyecto '{args.project}' no encontrado.", file=sys.stderr)
        sys.exit(1)

    cfg = pm.get_config(args.project)
    args.main = args.main or cfg['main_file']
    args.engine = args.engine or cfg['engine']
    pm.store(args.project).snapshot('antes de compilar desde CLI')
    print(f"Compilando {args.project}/{args.main} [{args.engine}, {args.mode}, {args.passes}×]…")
    result = asyncio.run(compile_latex(project_dir, args.main, args.engine, args.mode, args.passes))

    if result.success:
        print(f"✓  Listo en {result.duration:.1f}s  —  {result.pdf_path}")
    else:
        lines = result.log.splitlines()
        err = next((l for l in lines if l.startswith("!")), None) or lines[-1] if lines else "sin detalle"
        print(f"✗  {err.strip()}", file=sys.stderr)
        if args.log:
            print("\n--- Log ---", file=sys.stderr)
            print("\n".join(lines[-40:]), file=sys.stderr)
        sys.exit(1)


def cmd_read(args):
    try:
        content = pm.read_file(args.project, args.file)
        print(content, end="")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_write(args):
    content = args.content if args.content is not None else sys.stdin.read()
    try:
        pm.write_file(args.project, args.file, content)
        print("ok")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_files(args):
    try:
        files = pm.list_files(args.project)
        for f in files:
            print(f["path"])
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tree(args):
    try:
        entries = pm.list_dir(args.project, args.path or "")
        for e in entries:
            icon = "📁" if e["type"] == "dir" else "📄"
            print(f"{icon}  {e['path']}")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config(args):
    cfg = pm.get_config(args.project)
    print(json.dumps(cfg, indent=2, ensure_ascii=False))


def cmd_link(args):
    """Vincula o desvincula la carpeta real de un proyecto."""
    folder = Path(args.folder).expanduser().resolve() if args.folder else None

    if args.folder and not folder.is_dir():
        print(f"Error: '{args.folder}' no es una carpeta válida.", file=sys.stderr)
        sys.exit(1)

    proj_dir = pm._project_dir(args.project)
    if not proj_dir.exists():
        # Crear stub si no existe
        proj_dir.mkdir(parents=True, exist_ok=True)

    cfg = pm.get_config(args.project)
    cfg["linked_path"] = str(folder) if folder else ""
    if args.main:
        cfg["main_file"] = args.main

    pm.save_config(args.project, cfg)

    if folder:
        file_count = sum(
            1 for f in folder.rglob("*")
            if f.is_file() and not f.name.startswith(".")
            and f.suffix not in {".pdf", ".aux", ".log", ".out"}
        )
        print(f"✓  '{args.project}' → {folder}  ({file_count} archivos)")
        if args.main:
            print(f"   main: {args.main}")
    else:
        print(f"✓  '{args.project}' desvinculado (usa carpeta local en projects/)")


def cmd_new(args):
    """Crea un proyecto nuevo vinculado a una carpeta o local."""
    folder = Path(args.folder).expanduser().resolve() if args.folder else None

    if folder and not folder.is_dir():
        print(f"Error: '{args.folder}' no es una carpeta válida.", file=sys.stderr)
        sys.exit(1)

    name = args.name or (folder.name if folder else None)
    if not name:
        print("Error: especifica --name o una carpeta.", file=sys.stderr)
        sys.exit(1)

    safe = "".join(c for c in name if c.isalnum() or c in "_ -").strip()
    if not safe:
        print("Error: nombre de proyecto inválido.", file=sys.stderr)
        sys.exit(1)

    if folder:
        # Proyecto vinculado
        proj_dir = pm._project_dir(safe)
        proj_dir.mkdir(parents=True, exist_ok=True)
        cfg = {
            "engine": args.engine,
            "mode": "final",
            "passes": 1,
            "main_file": args.main,
            "linked_path": str(folder),
        }
        pm.save_config(safe, cfg)
        file_count = sum(
            1 for f in folder.rglob("*")
            if f.is_file() and not f.name.startswith(".")
            and f.suffix not in {".pdf", ".aux", ".log", ".out"}
        )
        print(f"✓  Proyecto '{safe}' creado  →  {folder}  ({file_count} archivos)")
    else:
        result = pm.create_project(safe, args.template)
        print(f"✓  Proyecto '{safe}' creado  (projects/{safe}/main.tex)")

    print(f"   Compila con: ./latex-cli compile {safe}")


def main():
    parser = argparse.ArgumentParser(
        prog="latex-cli",
        description="CLI para el editor LaTeX local",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # list
    sub.add_parser("list", help="Listar proyectos disponibles")

    # compile
    p = sub.add_parser("compile", help="Compilar un proyecto")
    p.add_argument("project", help="Nombre del proyecto")
    p.add_argument("--main",   default=None,  help="Archivo principal (por defecto: configuración del proyecto)")
    p.add_argument("--engine", default=None, choices=["pdflatex", "xelatex", "lualatex", "latex-dvips"])
    p.add_argument("--mode",   default="final",     choices=["final", "draft"])
    p.add_argument("--passes", default=1, type=int, help="Número de pasadas (default: 1)")
    p.add_argument("--log",    action="store_true",  help="Mostrar log completo en caso de error")

    # read
    p = sub.add_parser("read", help="Leer un archivo del proyecto")
    p.add_argument("project")
    p.add_argument("file", help="Ruta relativa del archivo")

    # write
    p = sub.add_parser("write", help="Escribir un archivo (contenido desde argumento o stdin)")
    p.add_argument("project")
    p.add_argument("file", help="Ruta relativa del archivo")
    p.add_argument("content", nargs="?", default=None, help="Contenido (si se omite, se lee de stdin)")

    # files
    p = sub.add_parser("files", help="Listar todos los archivos del proyecto (plano)")
    p.add_argument("project")

    # tree
    p = sub.add_parser("tree", help="Listar hijos directos de un directorio")
    p.add_argument("project")
    p.add_argument("path", nargs="?", default="", help="Subdirectorio (vacío = raíz)")

    # config
    p = sub.add_parser("config", help="Mostrar configuración del proyecto")
    p.add_argument("project")

    # link — cambiar carpeta vinculada
    p = sub.add_parser("link", help="Vincular proyecto a una carpeta del disco")
    p.add_argument("project", help="Nombre del proyecto")
    p.add_argument("folder",  nargs="?", default=None,
                   help="Ruta de la carpeta (omitir para desvincular)")
    p.add_argument("--main",  default=None, help="Archivo principal (ej: main.tex)")

    # new — crear proyecto
    p = sub.add_parser("new", help="Crear un proyecto nuevo (local o vinculado a carpeta)")
    p.add_argument("folder",    nargs="?", default=None,
                   help="Carpeta existente a vincular (opcional)")
    p.add_argument("--name",    default=None, help="Nombre del proyecto")
    p.add_argument("--main",    default="main.tex", help="Archivo principal")
    p.add_argument("--engine",  default="pdflatex",
                   choices=["pdflatex", "xelatex", "lualatex", "latex-dvips"])
    p.add_argument("--template", default="basic",
                   choices=["basic", "article", "beamer", "blank"],
                   help="Plantilla (solo para proyectos locales)")

    args = parser.parse_args()
    {
        "list":    cmd_list,
        "compile": cmd_compile,
        "read":    cmd_read,
        "write":   cmd_write,
        "files":   cmd_files,
        "tree":    cmd_tree,
        "config":  cmd_config,
        "link":    cmd_link,
        "new":     cmd_new,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
