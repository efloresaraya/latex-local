from safety import SafeStore, atomic_write, TEXT_EXTENSIONS, GENERATED
import json
import shutil
from pathlib import Path
from typing import Any

TEMPLATES: dict[str, str] = {
    "basic": r"""\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath}
\usepackage{graphicx}

\title{Mi Documento}
\author{Autor}
\date{\today}

\begin{document}

\maketitle

\section{Introducción}
Escribe tu contenido aquí.

\end{document}
""",
    "article": r"""\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage[margin=2.5cm]{geometry}

\title{Título del Artículo}
\author{Nombre Apellido}
\date{\today}

\begin{document}

\maketitle

\begin{abstract}
Resumen del artículo.
\end{abstract}

\section{Introducción}

\section{Metodología}

\section{Resultados}

\section{Conclusiones}

\end{document}
""",
    "beamer": r"""\documentclass{beamer}
\usepackage[utf8]{inputenc}
\usepackage[spanish]{babel}

\title{Mi Presentación}
\author{Autor}
\date{\today}

\begin{document}

\begin{frame}
\titlepage
\end{frame}

\begin{frame}{Contenido}
\tableofcontents
\end{frame}

\section{Introducción}
\begin{frame}{Introducción}
\begin{itemize}
    \item Punto 1
    \item Punto 2
    \item Punto 3
\end{itemize}
\end{frame}

\end{document}
""",
    "blank": "",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "engine": "pdflatex",
    "mode": "final",
    "passes": 1,
    "main_file": "main.tex",
    "linked_path": "",  # vacío = proyecto local copiado; ruta = vinculado al disco
}

SKIP_EXTENSIONS = {
    ".aux", ".log", ".out", ".toc", ".fls",
    ".fdb_latexmk", ".synctex.gz", ".bbl", ".blg",
    ".idx", ".ilg", ".ind", ".lof", ".lot",
}
SKIP_NAMES = {"config.json"}


class ProjectManager:
    def __init__(self, projects_dir: Path):
        self.root = projects_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, name):
        if not name or name in {'.', '..'} or '/' in name or '\\' in name or name.startswith('.'):
            raise ValueError('Nombre de proyecto inválido')
        p = (self.root / name).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError('Proyecto fuera del registro')
        return p

    def _effective_dir(self, name):
        stub = self._project_dir(name)
        if not stub.is_dir():
            raise FileNotFoundError(f'Proyecto no encontrado: {name}')
        linked = self.get_config(name).get('linked_path', '')
        if linked:
            p = Path(linked).resolve()
            if not p.is_dir():
                raise FileNotFoundError(f'La carpeta vinculada no está disponible: {p}. No se guardará en otra ubicación.')
            return p
        return stub

    def store(self, name):
        return SafeStore(self._effective_dir(name))

    def list_projects(self):
        result = []
        for d in sorted(self.root.iterdir()):
            if not d.is_dir() or d.name.startswith('.'):
                continue
            try:
                cfg = self.get_config(d.name)
                linked = cfg.get('linked_path', '')
                available = not linked or Path(linked).is_dir()
                result.append(dict(name=d.name, linked=bool(linked), linked_path=linked,
                                   available=available, config=cfg))
            except (ValueError, OSError):
                continue
        return result

    def create_project(self, name, template='basic'):
        safe = ''.join(c for c in name if c.isalnum() or c in '_ -').strip()
        project_dir = self._project_dir(safe)
        if project_dir.exists():
            raise ValueError('Ese proyecto ya existe. Ábrelo para continuar.')
        project_dir.mkdir()
        atomic_write(project_dir / 'config.json', json.dumps(DEFAULT_CONFIG).encode())
        self.write_file(safe, 'main.tex', TEMPLATES.get(template, TEMPLATES['basic']))
        return dict(name=safe, config=DEFAULT_CONFIG.copy())

    def delete_project(self, name):
        # Unregister only. A linked thesis must never be removed by deleting its project card.
        self.store(name).snapshot('antes de archivar proyecto', force=True)
        folder = self.root / '.archived'
        folder.mkdir(exist_ok=True)
        import uuid
        shutil.move(str(self._project_dir(name)), str(folder / (name + '-' + uuid.uuid4().hex[:8])))

    def get_config(self, name):
        path = self._project_dir(name) / 'config.json'
        if not path.exists():
            return DEFAULT_CONFIG.copy()
        config = json.loads(path.read_text())
        return {**DEFAULT_CONFIG, **config}

    def save_config(self, name, config):
        project_dir = self._project_dir(name)
        if not project_dir.is_dir():
            raise FileNotFoundError(f'Proyecto {name} no encontrado')
        merged = {**self.get_config(name), **config}
        if merged['engine'] not in {'pdflatex', 'xelatex', 'lualatex', 'latex-dvips'}:
            raise ValueError('Motor de compilación inválido')
        if merged['mode'] not in {'draft', 'final'}:
            raise ValueError('Modo inválido')
        if Path(merged['main_file']).is_absolute() or '..' in Path(merged['main_file']).parts:
            raise ValueError('Archivo principal inválido')
        if merged.get('linked_path'):
            target = Path(merged['linked_path']).expanduser().resolve()
            if not target.is_dir():
                raise FileNotFoundError('Carpeta vinculada no disponible')
            merged['linked_path'] = str(target)
        atomic_write(project_dir/'config.json', json.dumps(merged, ensure_ascii=False, indent=2).encode())

    def list_dir(self, name, subpath=''):
        store = self.store(name)
        target = store.path(subpath) if subpath else store.root
        if not target.is_dir():
            raise FileNotFoundError('Carpeta no encontrada')
        result = []
        for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if item.name.startswith('.') or item.is_symlink() or item.name in SKIP_NAMES or item.suffix in GENERATED or item.name.endswith('.synctex.gz'):
                continue
            result.append(dict(type='dir' if item.is_dir() else 'file', name=item.name,
                               path=str(item.relative_to(store.root)), size=item.stat().st_size))
        return result

    def list_files(self, name):
        store = self.store(name)
        return [dict(name=p.name, path=str(p.relative_to(store.root)), size=p.stat().st_size) for p in store.files()]

    def read_file(self, name, file_path):
        return self.store(name).read(file_path)['content']

    def write_file(self, name, file_path, content, expected=None):
        return self.store(name).write(file_path, content, expected)

    def create_file(self, name, file_path):
        return self.store(name).write(file_path, '', expected='missing', reason='creación')

    def delete_file(self, name, file_path, expected=None):
        return self.store(name).delete(file_path, expected)

    def _safe_path(self, name, file_path):
        return self.store(name).path(file_path)
