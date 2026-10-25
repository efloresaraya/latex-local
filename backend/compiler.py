import asyncio
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from safety import SafeStore, atomic_write
from pdf_sync import source_revisions, cache_success


def _latex_env():
    env = os.environ.copy()
    env['PATH'] = '/Library/TeX/texbin:' + env.get('PATH', '')
    return env


@dataclass
class CompileResult:
    success: bool
    log: str
    pdf_path: str | None
    duration: float
    diagnostics: list = field(default_factory=list)


def diagnostics(log):
    import re
    result = []
    for line in log.splitlines():
        match = re.match(r'(?:\./)?([^:\n]+\.(?:tex|sty|cls|bib)):(\d+):\s*(.+)', line)
        if match:
            result.append(dict(file=match[1], line=int(match[2]), message=match[3], severity='error'))
        elif line.startswith('!'):
            result.append(dict(message=line[1:].strip(), severity='error'))
        elif 'Warning:' in line:
            result.append(dict(message=line.strip(), severity='warning'))
    return result[:100]


async def compile_latex(project_dir: Path, main_file: str, engine='pdflatex', mode='final', passes=2):
    start = time.monotonic()
    if engine not in {'pdflatex', 'xelatex', 'lualatex', 'latex-dvips'} or mode not in {'final', 'draft'}:
        raise ValueError('Configuración de compilación inválida')
    store = SafeStore(project_dir)
    main = store.path(main_file)
    if main.suffix != '.tex' or not main.is_file():
        raise ValueError('Selecciona un archivo principal .tex existente')
    build = store.home / 'build' / main.stem
    build.mkdir(parents=True, exist_ok=True)
    env = _latex_env()
    latexmk = shutil.which('latexmk', path=env['PATH'])
    if not latexmk:
        return CompileResult(False, 'No se encontró latexmk. Instala MacTeX o TeX Live con latexmk y revisa PATH.', None, 0)
    output = main.with_suffix('.pdf')
    # Do not reuse a failed or stale PDF from an earlier build.
    built_pdf = build / output.name
    built_pdf.unlink(missing_ok=True)
    options = {'pdflatex': '-pdf', 'xelatex': '-xelatex', 'lualatex': '-lualatex', 'latex-dvips': '-pdfps'}
    command = [latexmk, options[engine], '-norc', '-interaction=nonstopmode', '-halt-on-error',
               '-file-line-error', '-synctex=1', '-no-shell-escape', f'-outdir={build}', main.name]
    revisions = source_revisions(store)
    process = None
    try:
        process = await asyncio.create_subprocess_exec(*command, cwd=str(main.parent), env=env,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                            start_new_session=True)
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=180)
        log = stdout.decode('utf-8', errors='replace')
        success = process.returncode == 0 and built_pdf.is_file()
        if success and mode == 'final':
            # A valid previous PDF is kept intact on any failed compilation.
            store.write_bytes(str(output.relative_to(store.root)), built_pdf.read_bytes(), reason='PDF compilado')
            try:
                cache_success(store, main_file, built_pdf, revisions)
            except (OSError, ValueError) as error:
                log += '\nAviso: no se pudo conservar SyncTeX para este PDF: ' + str(error) + '\n'
        elif success:
            log += '\nModo borrador: el PDF final anterior se conserva.\n'
        return CompileResult(success, log, str(output) if output.exists() else None,
                             time.monotonic()-start, diagnostics(log))
    except (asyncio.TimeoutError, asyncio.CancelledError) as error:
        if process and process.returncode is None:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
            await process.communicate()
        if isinstance(error, asyncio.CancelledError):
            raise
        log = 'La compilación superó 180 segundos y fue detenida. Se conserva el último PDF correcto.'
        return CompileResult(False, log, str(output) if output.exists() else None, time.monotonic()-start)
