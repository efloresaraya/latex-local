import asyncio
import json
import os
import re
import sys
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware
from compiler import compile_latex
from projects import ProjectManager
from safety import ConflictError, TEXT_EXTENSIONS
from references import inspect as inspect_references, add as add_reference
from doi_lookup import lookup as lookup_doi, LookupError as DoiLookupError
from bibliography_order import preview as preview_bibliography, organize as organize_bibliography
from pdf_sync import locate as locate_pdf_source, SyncError

APP_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = Path(os.environ.get('LATEX_PROJECTS_DIR', APP_DIR / 'projects')).expanduser()
project_manager = ProjectManager(PROJECTS_DIR)
connections = {}
active = set()
compile_locks = {}
settings_path = Path(os.environ.get('LATEX_CONFIG_FILE', APP_DIR / 'workspace.json')).expanduser()


def settings():
    return json.loads(settings_path.read_text()) if settings_path.exists() else {}


async def periodic_backups():
    while True:
        await asyncio.sleep(600)
        for name in list(active):
            try:
                await asyncio.to_thread(project_manager.store(name).snapshot, 'automático cada 10 minutos')
                await broadcast(name, dict(type='backup_ready'))
            except Exception as error:
                await broadcast(name, dict(type='backup_error', message=str(error)))


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(periodic_backups())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title='LaTeX Local', lifespan=lifespan)
app.mount('/vendor', StaticFiles(directory=APP_DIR / 'frontend/vendor'), name='vendor')
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])


@app.middleware('http')
async def local_requests(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
        return JSONResponse({'detail': 'Solo se permiten solicitudes desde el editor local'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(ConflictError)
async def conflict(request, error):
    return JSONResponse({'detail': str(error)}, status_code=409)


@app.exception_handler(ValueError)
async def invalid(request, error):
    return JSONResponse({'detail': str(error)}, status_code=400)


@app.exception_handler(FileNotFoundError)
async def missing(request, error):
    return JSONResponse({'detail': str(error)}, status_code=404)


@app.exception_handler(OSError)
async def io_error(request, error):
    return JSONResponse({'detail': 'No se pudo completar la operación en disco: ' + str(error)}, status_code=507)


@app.get('/')
async def root():
    return FileResponse(APP_DIR / 'frontend/index.html', headers={'Cache-Control': 'no-store'})


@app.get('/app.js')
async def javascript():
    return FileResponse(APP_DIR / 'frontend/app.js', media_type='application/javascript', headers={'Cache-Control': 'no-store'})


@app.get('/style.css')
async def stylesheet():
    return FileResponse(APP_DIR / 'frontend/style.css', media_type='text/css', headers={'Cache-Control': 'no-store'})


@app.get('/api/workspace')
async def workspace():
    return settings()


@app.get('/api/projects')
async def list_projects():
    return await asyncio.to_thread(project_manager.list_projects)


@app.post('/api/projects')
async def create_project(data: dict):
    return await asyncio.to_thread(project_manager.create_project, data.get('name', ''), data.get('template', 'article'))


@app.post('/api/projects/from-path')
async def from_path(data: dict):
    folder = Path(data.get('path', '')).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError('La carpeta no existe')
    name = ''.join(c for c in folder.name if c.isalnum() or c in '_ -').strip()
    stub = project_manager._project_dir(name)
    if stub.exists():
        existing = project_manager.get_config(name)
        if existing.get('linked_path') != str(folder):
            raise ValueError('Ya existe un proyecto con ese nombre y otra ubicación')
    stub.mkdir(exist_ok=True)
    mains = [p for p in folder.glob('*.tex') if re.search(r'\\documentclass', p.read_text(errors='replace'))]
    main = data.get('main_file') or (mains[0].name if len(mains)==1 else 'main.tex')
    cfg = dict(linked_path=str(folder), main_file=main, engine='pdflatex', mode='final', passes=2)
    project_manager.save_config(name, cfg)
    await asyncio.to_thread(project_manager.store(name).snapshot, 'al vincular carpeta')
    return dict(name=name, config=project_manager.get_config(name))


@app.delete('/api/projects/{name}')
async def delete_project(name: str):
    await asyncio.to_thread(project_manager.delete_project, name)
    return {'ok': True}


@app.get('/api/projects/{name}/config')
async def config(name: str):
    root = project_manager._effective_dir(name)
    return dict(**project_manager.get_config(name), resolved_path=str(root))


@app.put('/api/projects/{name}/config')
async def put_config(name: str, data: dict):
    # Linking is a separate explicit operation; a settings update cannot move the thesis.
    if 'linked_path' in data:
        raise ValueError('La ubicación se cambia únicamente vinculando una carpeta')
    project_manager.save_config(name, data)
    return {'ok': True}


@app.post('/api/projects/{name}/session')
async def session(name: str):
    snapshot = await asyncio.to_thread(project_manager.store(name).snapshot, 'al abrir el proyecto')
    active.add(name)
    return dict(snapshot=snapshot, root=str(project_manager._effective_dir(name)),
                backup_path=str(project_manager.store(name).home), history_policy='Sin borrado automático de versiones')


@app.get('/api/projects/{name}/tree')
async def tree(name: str, path: str = ''):
    return project_manager.list_dir(name, path)


@app.get('/api/projects/{name}/files')
async def files(name: str):
    return await asyncio.to_thread(project_manager.list_files, name)


@app.get('/api/projects/{name}/files/{file_path:path}')
async def read(name: str, file_path: str):
    return project_manager.store(name).read(file_path)


@app.put('/api/projects/{name}/files/{file_path:path}')
async def write(name: str, file_path: str, data: dict):
    if not isinstance(data.get('content'), str) or not isinstance(data.get('revision'), str):
        raise ValueError('Se requieren el contenido y la revisión leída. Recarga el archivo antes de guardar.')
    result = await asyncio.to_thread(project_manager.write_file, name, file_path, data['content'], data['revision'])
    await broadcast(name, dict(type='file_changed', path=file_path, revision=result['revision']))
    return result


@app.post('/api/projects/{name}/files/{file_path:path}')
async def new_file(name: str, file_path: str):
    return await asyncio.to_thread(project_manager.create_file, name, file_path)


@app.delete('/api/projects/{name}/files/{file_path:path}')
async def delete_file(name: str, file_path: str, revision: str):
    return await asyncio.to_thread(project_manager.delete_file, name, file_path, revision)


@app.get('/api/projects/{name}/raw/{file_path:path}')
async def raw(name: str, file_path: str):
    path = project_manager._safe_path(name, file_path)
    if not path.is_file():
        raise FileNotFoundError('Archivo no encontrado')
    # HTML/SVG are downloads, not same-origin executable documents.
    return FileResponse(path, filename=path.name if path.suffix in {'.html', '.svg', '.js'} else None)


@app.get('/api/projects/{name}/file-state')
async def file_state(name: str, file: str):
    from safety import digest
    path = project_manager.store(name).path(file)
    if not path.exists():
        return dict(revision='missing', content='', exists=False)
    data = path.read_bytes()
    return dict(revision=digest(data), content=data.decode('utf-8') if path.suffix.lower() in TEXT_EXTENSIONS else f'[Archivo binario: {len(data):,} bytes]', exists=True)


@app.get('/api/projects/{name}/references')
async def references(name: str):
    store = project_manager.store(name)
    main_file = project_manager.get_config(name)['main_file']
    return await asyncio.to_thread(inspect_references, store, main_file)


@app.post('/api/projects/{name}/references/organize/preview')
async def bibliography_preview(name: str, data: dict):
    path = data.get('bib_path')
    if not isinstance(path, str):
        raise ValueError('Selecciona una bibliografía.')
    store = project_manager.store(name)
    main_file = project_manager.get_config(name)['main_file']
    return await asyncio.to_thread(preview_bibliography, store, main_file, path)


@app.post('/api/projects/{name}/references/organize')
async def bibliography_organize(name: str, data: dict):
    store = project_manager.store(name)
    main_file = project_manager.get_config(name)['main_file']
    result = await asyncio.to_thread(organize_bibliography, store, main_file, data)
    if result['changed']:
        await broadcast(name, dict(type='file_changed', path=result['path'], revision=result['revision']))
    return result


@app.post('/api/projects/{name}/references/doi')
async def reference_from_doi(name: str, data: dict):
    store = project_manager.store(name)
    main_file = project_manager.get_config(name)['main_file']
    if not isinstance(data.get('allow_external', True), bool):
        raise ValueError('La opción de consulta externa debe ser verdadera o falsa.')
    if data.get('requested_key') is not None and not isinstance(data['requested_key'], str):
        raise ValueError('Clave de cita inválida.')
    try:
        return await asyncio.to_thread(lookup_doi, store, main_file, data.get('doi'), data.get('allow_external', True), data.get('requested_key'))
    except DoiLookupError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


@app.post('/api/projects/{name}/references')
async def incorporate_reference(name: str, data: dict):
    store = project_manager.store(name)
    main_file = project_manager.get_config(name)['main_file']
    result = await asyncio.to_thread(add_reference, store, main_file, data)
    if result['added']:
        await broadcast(name, dict(type='file_changed', path=result['path'], revision=result['revision']))
    return result


@app.post('/api/projects/{name}/assets')
async def upload_asset(name: str, path: str, file: UploadFile = File(...)):
    store = project_manager.store(name)
    target = store.path(path)
    if target.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.pdf', '.svg', '.webp', '.eps', '.tex', '.bib', '.sty', '.cls', '.bst', '.csv'}:
        raise ValueError('Formato no admitido para el proyecto LaTeX')
    data = await file.read(50_000_001)
    if len(data) > 50_000_000:
        raise ValueError('El archivo excede 50 MB')
    return await asyncio.to_thread(store.write_bytes, path, data, 'missing', 'archivo incorporado')


@app.get('/api/projects/{name}/history-files')
async def history_files(name: str):
    store = project_manager.store(name)
    paths = set()
    for folder in (store.home / 'history').glob('*'):
        entries = sorted(folder.glob('*.json'))
        if entries:
            paths.add(json.loads(entries[-1].read_text())['path'])
    return sorted(paths)


@app.get('/api/projects/{name}/history')
async def history(name: str, file: str):
    return project_manager.store(name).history(file)


@app.get('/api/projects/{name}/version')
async def version(name: str, file: str, version: str):
    meta, data = project_manager.store(name).version(file, version)
    return dict(meta=meta, content=data.decode('utf-8') if Path(file).suffix.lower() in TEXT_EXTENSIONS else f'[Archivo binario: {len(data):,} bytes]', binary=Path(file).suffix.lower() not in TEXT_EXTENSIONS)


@app.post('/api/projects/{name}/restore')
async def restore(name: str, data: dict):
    if not isinstance(data.get('revision'), str):
        raise ValueError('Revisión actual requerida')
    return await asyncio.to_thread(project_manager.store(name).restore, data['file'], data['version'], data['revision'])


@app.get('/api/projects/{name}/snapshots')
async def snapshots(name: str):
    return project_manager.store(name).snapshots()


@app.post('/api/projects/{name}/snapshots')
async def snapshot(name: str):
    return await asyncio.to_thread(project_manager.store(name).snapshot, 'respaldo manual', True)


@app.get('/api/projects/{name}/snapshot-file/{version}')
async def snapshot_file(name: str, version: str):
    if not re.fullmatch(r'[0-9TZ.a-f-]+\.zip', version):
        raise ValueError('Respaldo inválido')
    path = project_manager.store(name).home / 'snapshots' / version
    if not path.is_file():
        raise FileNotFoundError('Respaldo no encontrado')
    return FileResponse(path, filename=f'{name}-{version}')


@app.post('/api/projects/{name}/compile')
async def compile_project(name: str, data: dict):
    cfg = project_manager.get_config(name)
    lock = compile_locks.setdefault(name, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, 'Este proyecto ya se está compilando')
    async with lock:
        await asyncio.to_thread(project_manager.store(name).snapshot, 'antes de compilar')
        main = cfg['main_file']
        # Always compile the configured root, regardless of the chapter displayed.
        result = await compile_latex(project_manager._effective_dir(name), main,
                        data.get('engine', cfg['engine']), data.get('mode', cfg['mode']), cfg.get('passes', 2))
        return dict(success=result.success, log=result.log, has_pdf=result.pdf_path is not None,
                    duration=result.duration, diagnostics=result.diagnostics, main_file=main)


@app.post('/api/projects/{name}/synctex/inverse')
async def pdf_source(name: str, data: dict):
    store = project_manager.store(name)
    main_file = project_manager.get_config(name)['main_file']
    try:
        return await locate_pdf_source(store, main_file, data)
    except SyncError as error:
        raise HTTPException(error.status, str(error)) from error


@app.get('/api/projects/{name}/pdf')
async def pdf(name: str, main_file: str = ''):
    cfg = project_manager.get_config(name)
    main = project_manager._safe_path(name, main_file or cfg['main_file'])
    path = main.with_suffix('.pdf')
    if not path.is_file():
        raise FileNotFoundError('Aún no hay un PDF compilado')
    return FileResponse(path, media_type='application/pdf')


@app.get('/api/projects/{name}/export')
async def export(name: str):
    # A full verified backup includes linked sources and PDF figures, not only the registry stub.
    meta = await asyncio.to_thread(project_manager.store(name).snapshot, 'exportación', True)
    return FileResponse(meta['path'], filename=f'{name}.zip')


@app.post('/api/projects/{name}/import')
async def import_zip(name: str, file: UploadFile = File(...)):
    store = project_manager.store(name)
    payload = await file.read()
    import io
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if sum(i.file_size for i in infos) > 500_000_000:
            raise ValueError('El ZIP excede 500 MB descomprimidos')
        staged = []
        for info in infos:
            if info.filename == 'RESPALDO_MANIFIESTO.json':
                continue
            store.path(info.filename)  # Validate everything before any mutation.
            staged.append((info.filename, archive.read(info)))
        await asyncio.to_thread(store.snapshot, 'antes de importar ZIP', True)
        for rel, data in staged:
            await asyncio.to_thread(store.write_bytes, rel, data, None, 'importación ZIP')
    return dict(ok=True, files=len(staged))


async def broadcast(name, message):
    for ws in list(connections.get(name, set())):
        try:
            await ws.send_json(message)
        except Exception:
            connections.get(name, set()).discard(ws)


@app.websocket('/ws/{name}')
async def websocket(ws: WebSocket, name: str):
    origin = ws.headers.get('origin')
    if origin and origin not in {f'http://{ws.headers.get("host")}', f'https://{ws.headers.get("host")}'}:
        await ws.close(code=1008)
        return
    project_manager._effective_dir(name)
    await ws.accept()
    connections.setdefault(name, set()).add(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), 25)
            except asyncio.TimeoutError:
                await ws.send_json(dict(type='ping'))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        connections.get(name, set()).discard(ws)
