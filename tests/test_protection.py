import asyncio
import hashlib
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from safety import SafeStore, ConflictError, digest
from projects import ProjectManager
from compiler import compile_latex
import main
from fastapi.testclient import TestClient


@pytest.fixture
def store(tmp_path):
    return SafeStore(tmp_path)


def test_save_conflict_and_recover_exact_original(store):
    path = store.root / 'capítulo.tex'
    original = b'primera\r\nversi\xc3\xb3n\r\n'
    path.write_bytes(original)
    revision = digest(original)
    store.write('capítulo.tex', 'edición nueva', revision)
    with pytest.raises(ConflictError):
        store.write('capítulo.tex', 'pérdida', revision)
    old = next(h for h in store.history('capítulo.tex') if h['reason'].startswith('antes'))
    store.restore('capítulo.tex', old['id'], digest(path.read_bytes()))
    assert path.read_bytes() == original


def test_failed_backup_blocks_mutation(store):
    path = store.root / 'cap.tex'
    path.write_text('único original')
    with patch.object(store, '_record', side_effect=OSError('disco lleno')):
        with pytest.raises(OSError):
            store.write('cap.tex', 'NO', digest(path.read_bytes()))
        with pytest.raises(OSError):
            store.delete('cap.tex')
    assert path.read_text() == 'único original'


def test_deleted_file_is_restorable(store):
    store.write('cap.tex', 'no perder')
    store.delete('cap.tex')
    assert not (store.root / 'cap.tex').exists()
    v = next(v for v in store.history('cap.tex') if v['reason']=='eliminación')
    store.restore('cap.tex', v['id'], 'missing')
    assert store.read('cap.tex')['content'] == 'no perder'


def test_snapshot_includes_pdf_assets_and_verifies_every_byte(store):
    (store.root / 'figura.pdf').write_bytes(b'PDF de figura')
    store.write('main.tex', 'fuente')
    (store.root / 'main.aux').write_text('generado')
    meta = store.snapshot()
    with zipfile.ZipFile(meta['path']) as z:
        assert 'figura.pdf' in z.namelist()
        assert 'main.aux' not in z.namelist()
        assert not any('.latex-local' in n for n in z.namelist())
        manifest = json.loads(z.read('RESPALDO_MANIFIESTO.json'))['manifest']
        for name, item in manifest.items():
            assert digest(z.read(name)) == item['sha256']
    assert store.snapshot()['unchanged']


def test_no_boundary_or_symlink_escape(store, tmp_path):
    sibling = tmp_path.parent / (tmp_path.name + '-other')
    sibling.mkdir()
    (sibling/'secret.tex').write_text('no tocar')
    (tmp_path/'link').symlink_to(sibling, target_is_directory=True)
    for rel in ['../'+sibling.name+'/secret.tex', 'link/secret.tex', '/tmp/a.tex', '.latex-local/storage.lock', '.git/config']:
        with pytest.raises(ValueError):
            store.write(rel, 'NO')
    assert (sibling/'secret.tex').read_text()=='no tocar'


def test_parallel_saves_one_wins_without_losing_original(store):
    store.write('a.tex', 'inicial')
    revision = store.read('a.tex')['revision']
    def save(i):
        try:
            store.write('a.tex', str(i), revision)
            return True
        except ConflictError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(save, range(8))) == 1
    assert any(store.version('a.tex', item['id'])[1] == b'inicial' for item in store.history('a.tex'))


def test_binary_text_overwrite_rejected(store):
    (store.root/'figura.png').write_bytes(b'\x89PNG')
    with pytest.raises(ValueError):
        store.write('figura.png','')
    assert (store.root/'figura.png').read_bytes()==b'\x89PNG'


def test_missing_link_never_falls_back(tmp_path):
    pm=ProjectManager(tmp_path/'registry')
    d=pm.root/'documento';d.mkdir()
    (d/'config.json').write_text(json.dumps({'linked_path':str(tmp_path/'missing')}))
    with pytest.raises(FileNotFoundError):pm.write_file('documento','cap.tex','NO')
    assert not (d/'cap.tex').exists()


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    pm=ProjectManager(tmp_path/'registry')
    pm.create_project('prueba')
    monkeypatch.setattr(main, 'project_manager', pm)
    monkeypatch.setattr(main, 'active', set())
    with TestClient(main.app) as client:
        yield client, pm


def test_api_requires_revision_and_preserves_conflict(api_client):
    client,pm=api_client
    endpoint='/api/projects/prueba/files/main.tex'
    data=client.get(endpoint).json()
    assert client.put(endpoint,json={'content':'NO'}).status_code==400
    assert client.put(endpoint,json={'content':'correcto','revision':data['revision']}).status_code==200
    assert client.put(endpoint,json={'content':'obsoleto','revision':data['revision']}).status_code==409
    assert pm.read_file('prueba','main.tex')=='correcto'


def test_cross_origin_mutation_rejected(api_client):
    client,pm=api_client
    assert client.post('/api/projects',json={'name':'mal'},headers={'origin':'https://otro.sitio'}).status_code==403
    assert not (pm.root/'mal').exists()


def test_export_linked_project_has_sources_and_figures(api_client,tmp_path):
    client,pm=api_client
    linked=tmp_path/'linked';linked.mkdir()
    (linked/'main.tex').write_text('documento de prueba')
    (linked/'fig.pdf').write_bytes(b'figura')
    pm.save_config('prueba',{'linked_path':str(linked)})
    response=client.get('/api/projects/prueba/export')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert z.read('main.tex')==b'documento de prueba'
        assert z.read('fig.pdf')==b'figura'


def test_zip_traversal_validated_before_changes(api_client):
    client,pm=api_client
    before=pm.read_file('prueba','main.tex')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        z.writestr('main.tex','NO')
        z.writestr('../escaped.tex','NO')
    response=client.post('/api/projects/prueba/import',files={'file':('bad.zip',buffer.getvalue(),'application/zip')})
    assert response.status_code==400
    assert pm.read_file('prueba','main.tex')==before


def test_compile_api_uses_root_even_with_chapter_request(api_client,monkeypatch):
    from compiler import CompileResult
    client,pm=api_client
    seen=[]
    async def fake(folder, main_file, *args):
        seen.append(main_file)
        return CompileResult(False,'test',None,0)
    monkeypatch.setattr(main,'compile_latex',fake)
    response=client.post('/api/projects/prueba/compile',json={'main_file':'capitulo.tex'})
    assert response.status_code==200
    assert seen==['main.tex']


def test_real_compile_bibliography_and_failed_build_preserves_pdf(store):
    root=store.root
    (root/'main.tex').write_text(r'''\documentclass{article}
\begin{document}Documento \cite{prueba}.
\bibliographystyle{plain}\bibliography{refs}\end{document}''')
    (root/'refs.bib').write_text('@book{prueba, title={Libro}, author={Autor, Nombre}, year={2026}, publisher={Editorial}}')
    result=asyncio.run(compile_latex(root,'main.tex'))
    assert result.success,result.log
    assert (root/'.latex-local/build/main/main.bbl').exists()
    pdf=(root/'main.pdf').read_bytes()
    assert pdf.startswith(b'%PDF')
    (root/'main.tex').write_text(r'\documentclass{article}\begin{document}\invalidcommandhere\end{document}')
    failed=asyncio.run(compile_latex(root,'main.tex'))
    assert not failed.success
    assert (root/'main.pdf').read_bytes()==pdf
    assert failed.diagnostics


def test_opening_snapshot_indexes_initial_versions(store):
    (store.root/'cap.tex').write_bytes(b'original')
    store.snapshot('al abrir')
    versions=store.history('cap.tex')
    assert len(versions)==1
    assert store.version('cap.tex', versions[0]['id'])[1]==b'original'
    store.snapshot('sin cambios')
    assert len(store.history('cap.tex'))==1


def test_upload_never_overwrites_and_binary_history_is_viewable(api_client):
    client,pm=api_client
    url='/api/projects/prueba/assets?path=imagenes/fig.png'
    assert client.post(url,files={'file':('fig.png',b'\x89PNG\x00original','image/png')}).status_code==200
    assert client.post(url,files={'file':('fig.png',b'NO','image/png')}).status_code==409
    history=client.get('/api/projects/prueba/history',params={'file':'imagenes/fig.png'}).json()
    version=client.get('/api/projects/prueba/version',params={'file':'imagenes/fig.png','version':history[0]['id']})
    assert version.status_code==200
    assert version.json()['binary']
    state=client.get('/api/projects/prueba/file-state',params={'file':'imagenes/fig.png'}).json()
    assert state['exists']
    assert state['revision']==digest(b'\x89PNG\x00original')
