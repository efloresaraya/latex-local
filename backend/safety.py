"""Durable local storage. No write/delete proceeds unless its backup succeeds."""
import fcntl
import hashlib
import json
import os
import tempfile
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TEXT_EXTENSIONS = {'.tex', '.bib', '.sty', '.cls', '.txt', '.md', '.cfg', '.def', '.ins', '.dtx', '.tikz', '.csv', '.json', '.bst', '.bbl'}
GENERATED = {'.aux', '.log', '.out', '.toc', '.fls', '.fdb_latexmk', '.blg', '.idx', '.ilg', '.ind', '.lof', '.lot', '.nav', '.snm', '.vrb', '.dvi', '.ps', '.spl'}
_locks = {}
_locks_guard = threading.Lock()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.saving-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ConflictError(Exception):
    pass


class SafeStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f'Carpeta no disponible: {self.root}')
        self.home = self.root / '.latex-local'
        # Never follow an internal backup symlink into an unrelated directory.
        if self.home.is_symlink():
            raise ValueError('La carpeta de respaldo no puede ser un enlace simbólico')

    def path(self, rel):
        p = Path(rel)
        if not rel or p.is_absolute() or any(part.startswith('.') for part in p.parts):
            raise ValueError('Ruta no permitida')
        result = (self.root / p).resolve()
        if not result.is_relative_to(self.root) or result == self.root:
            raise ValueError('Ruta fuera del proyecto')
        return result

    @contextmanager
    def locked(self):
        with _locks_guard:
            lock = _locks.setdefault(str(self.root), threading.RLock())
        with lock:
            self.home.mkdir(exist_ok=True)
            with (self.home / 'storage.lock').open('a') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)

    def read(self, rel):
        data = self.path(rel).read_bytes()
        # A decoding failure must never become a lossy rewrite.
        return dict(content=data.decode('utf-8'), revision=digest(data))

    def _record(self, rel, data, reason):
        fingerprint = digest(data)
        blob = self.home / 'blobs' / fingerprint
        if not blob.exists():
            atomic_write(blob, data)
        if digest(blob.read_bytes()) != fingerprint:
            raise OSError('El respaldo no pasó la verificación de integridad')
        version = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:8]
        record = dict(id=version, path=rel, sha256=fingerprint, size=len(data), reason=reason,
                      created_at=datetime.now(timezone.utc).isoformat())
        index = self.home / 'history' / digest(rel.encode()) / (version + '.json')
        atomic_write(index, json.dumps(record, ensure_ascii=False).encode())
        return record

    def write(self, rel, content, expected=None, reason='guardado'):
        if self.path(rel).suffix.lower() not in TEXT_EXTENSIONS:
            raise ValueError('Este archivo no se puede sobrescribir como texto')
        if not isinstance(content, str):
            raise ValueError('Contenido de texto requerido')
        return self.write_bytes(rel, content.encode('utf-8'), expected, reason)

    def write_bytes(self, rel, data, expected=None, reason='importación'):
        path = self.path(rel)
        with self.locked():
            old = path.read_bytes() if path.exists() else None
            current = digest(old) if old is not None else 'missing'
            if expected is not None and expected != current:
                raise ConflictError('El archivo cambió en disco. Conservamos tu borrador; revisa ambas versiones antes de guardar.')
            if old == data:
                return dict(ok=True, revision=current, changed=False)
            if old is not None:
                self._record(rel, old, 'antes de ' + reason)
            saved = self._record(rel, data, reason)
            atomic_write(path, data)
            return dict(ok=True, revision=saved['sha256'], changed=True, backup=saved['id'])

    def delete(self, rel, expected=None):
        path = self.path(rel)
        with self.locked():
            data = path.read_bytes()
            if expected is not None and expected != digest(data):
                raise ConflictError('El archivo cambió antes de eliminarlo')
            saved = self._record(rel, data, 'eliminación')
            path.unlink()
            return dict(ok=True, backup=saved['id'])

    def history(self, rel):
        self.path(rel)
        folder = self.home / 'history' / digest(rel.encode())
        if not folder.exists():
            return []
        return [json.loads(p.read_text()) for p in sorted(folder.glob('*.json'), reverse=True)]

    def version(self, rel, version):
        if not version or any(c not in '0123456789TZ.-abcdef' for c in version):
            raise ValueError('Versión inválida')
        index = self.home / 'history' / digest(rel.encode()) / (version + '.json')
        item = json.loads(index.read_text())
        if item['path'] != rel:
            raise ValueError('Versión de otro archivo')
        data = (self.home / 'blobs' / item['sha256']).read_bytes()
        if digest(data) != item['sha256']:
            raise OSError('Respaldo dañado; restauración detenida')
        return item, data

    def restore(self, rel, version, expected):
        _, data = self.version(rel, version)
        return self.write_bytes(rel, data, expected, 'restauración')

    def files(self):
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(directory)/d).is_symlink() and d != '__pycache__')
            for name in sorted(names):
                p = Path(directory) / name
                if name.startswith('.') or p.is_symlink() or p.suffix in GENERATED or name.endswith('.synctex.gz'):
                    continue
                if p == self.root / 'config.json':
                    continue
                yield p

    def snapshot(self, reason='manual', force=False):
        with self.locked():
            paths = list(self.files())
            # Hold bytes, not a stat signature: manifest and archive must describe the same data.
            payload = [(str(p.relative_to(self.root)), p.read_bytes()) for p in paths]
            manifest = {rel: dict(sha256=digest(data), size=len(data)) for rel, data in payload}
            for rel, data in payload:
                folder = self.home / 'history' / digest(rel.encode())
                latest = sorted(folder.glob('*.json'))
                if not latest or json.loads(latest[-1].read_text())['sha256'] != digest(data):
                    self._record(rel, data, 'punto de respaldo: ' + reason)
            fingerprint = digest(json.dumps(manifest, sort_keys=True).encode())
            state = self.home / 'snapshot-state.json'
            if not force and state.exists():
                previous = json.loads(state.read_text())
                if previous.get('fingerprint') == fingerprint:
                    return dict(**previous, unchanged=True)
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:8] + '.zip'
            folder = self.home / 'snapshots'
            folder.mkdir(exist_ok=True)
            temp = folder / ('.' + name + '.tmp')
            dest = folder / name
            meta = dict(id=name, created_at=datetime.now(timezone.utc).isoformat(), reason=reason,
                        fingerprint=fingerprint, files=len(payload), path=str(dest))
            try:
                with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for rel, data in payload:
                        archive.writestr(rel, data)
                    archive.writestr('RESPALDO_MANIFIESTO.json', json.dumps(dict(**meta, manifest=manifest), ensure_ascii=False, indent=2))
                with zipfile.ZipFile(temp) as archive:
                    if archive.testzip() is not None:
                        raise OSError('El ZIP de respaldo no pasó su verificación')
                    for rel, data in manifest.items():
                        if digest(archive.read(rel)) != data['sha256']:
                            raise OSError('Contenido de respaldo inconsistente')
                with temp.open('rb') as stream:
                    os.fsync(stream.fileno())
                os.replace(temp, dest)
                atomic_write(state, json.dumps(meta, ensure_ascii=False).encode())
            finally:
                temp.unlink(missing_ok=True)
            return meta

    def snapshots(self):
        result = []
        for p in sorted((self.home/'snapshots').glob('*.zip'), reverse=True):
            result.append(dict(id=p.name, size=p.stat().st_size, modified=p.stat().st_mtime))
        return result
