"""Navegación PDF → fuente mediante SyncTeX, vinculada al PDF compilado."""
import asyncio
import gzip
import json
import math
import re
import shutil
from pathlib import Path
from safety import atomic_write, digest


class SyncError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def source_revisions(store):
    return {path.relative_to(store.root).as_posix(): digest(path.read_bytes()) for path in store.files()
            if path.suffix.lower() in {'.tex', '.sty', '.cls', '.bib'}}


def cache_success(store, main, built_pdf, revisions):
    sync = built_pdf.with_suffix('.synctex.gz')
    if not sync.exists():
        return
    # Read the source paths recorded by TeX, retaining only project-local files.
    inputs = {}
    with gzip.open(sync, 'rt', encoding='utf-8', errors='replace') as stream:
        for line in stream:
            # TeX may register a newly opened chapter after Content: (and
            # between shipped pages), so inspect the entire SyncTeX stream.
            if not line.startswith('Input:'):
                continue
            name = line.rstrip('\r\n').split(':', 2)[2]
            path = Path(name)
            path = (store.path(main).parent / path).resolve() if not path.is_absolute() else path.resolve()
            try:
                rel = path.relative_to(store.root).as_posix()
                store.path(rel)
            except ValueError:
                continue
            if rel in revisions:
                inputs[rel] = revisions[rel]
    pdf = built_pdf.read_bytes()
    revision = digest(pdf)
    folder = store.home / 'synctex' / revision
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink():
        raise ValueError('Carpeta SyncTeX inválida.')
    atomic_write(folder / built_pdf.name, pdf)
    sync_data = sync.read_bytes()
    atomic_write(folder / sync.name, sync_data)
    # Commit metadata last; incomplete bundles are never used.
    meta = dict(main=main, pdf_revision=revision, sync_revision=digest(sync_data), inputs=inputs)
    atomic_write(folder / 'metadata.json', json.dumps(meta).encode())


def parse_results(output, store, main, inputs):
    candidates = re.split(r'(?m)^Output:', output)
    for block in candidates[1:]:
        source = re.search(r'(?m)^Input:(.*)$', block)
        line = re.search(r'(?m)^Line:(\d+)\s*$', block)
        if not source or not line:
            continue
        path = Path(source[1].strip())
        path = (store.path(main).parent / path).resolve() if not path.is_absolute() else path.resolve()
        try:
            rel = path.relative_to(store.root).as_posix()
            store.path(rel)
        except ValueError:
            continue
        if rel not in inputs or path.suffix.lower() not in {'.tex', '.sty', '.cls'} or not path.is_file():
            continue
        current = store.read(rel)
        if current['revision'] != inputs[rel]:
            raise SyncError('El archivo fuente cambió desde la compilación. Guarda y compila para sincronizar el PDF con el texto actual.')
        count = max(1, len(current['content'].splitlines()))
        return dict(path=rel, line=min(max(1, int(line[1])), count), column=0, revision=current['revision'])
    raise SyncError('No se encontró una línea editable para ese punto. Prueba sobre el texto cercano.', 404)


async def locate(store, main, data):
    page, x, y, revision = data.get('page'), data.get('x'), data.get('y'), data.get('pdf_revision')
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100000:
        raise ValueError('Página PDF inválida.')
    for value in (x, y):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100000:
            raise ValueError('Coordenadas PDF inválidas.')
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{64}', revision):
        raise ValueError('Revisión PDF inválida.')
    folder = store.home / 'synctex' / revision
    metadata = folder / 'metadata.json'
    if not metadata.is_file():
        raise SyncError('Compila una vez para activar la navegación entre este PDF y sus archivos LaTeX.')
    meta = json.loads(metadata.read_text())
    if meta.get('main') != main or meta.get('pdf_revision') != revision:
        raise SyncError('Cambió el documento principal. Compila y vuelve a abrir el PDF.')
    pdf = folder / Path(main).with_suffix('.pdf').name
    sync = pdf.with_suffix('.synctex.gz')
    if not pdf.is_file() or digest(pdf.read_bytes()) != revision or not sync.is_file() or digest(sync.read_bytes()) != meta['sync_revision']:
        raise SyncError('La información de sincronización está incompleta. Vuelve a compilar.')
    executable = shutil.which('synctex', path='/Library/TeX/texbin:/usr/local/bin:/usr/bin:/bin')
    if not executable:
        raise SyncError('No se encontró SyncTeX en la instalación de LaTeX.', 503)
    process = await asyncio.create_subprocess_exec(executable, 'edit', '-o', f'{page}:{x:.5f}:{y:.5f}:{pdf}',
        cwd=str(store.path(main).parent), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=8)
    except (asyncio.TimeoutError, asyncio.CancelledError) as error:
        if process.returncode is None:
            process.kill()
            await process.communicate()
        if isinstance(error, asyncio.CancelledError):
            raise
        raise SyncError('SyncTeX tardó demasiado. Vuelve a intentarlo.', 504) from error
    if process.returncode:
        raise SyncError('No se pudo localizar ese punto del PDF. Prueba sobre el texto cercano.', 404)
    return parse_results(stdout.decode('utf-8', errors='replace'), store, main, meta['inputs'])
