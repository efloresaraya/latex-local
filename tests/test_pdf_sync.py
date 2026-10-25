import asyncio
import json
import sys
from pathlib import Path
import fitz
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from compiler import compile_latex
from pdf_sync import locate, parse_results, SyncError, source_revisions
from safety import SafeStore, digest


@pytest.fixture(scope='module')
def compiled(tmp_path_factory):
    root=tmp_path_factory.mktemp('pdf sync con espacios')
    (root/'main.tex').write_text(r'\documentclass{article}'+'\n'+r'\begin{document}'+'\n'+r'Primera pagina antes del capitulo.\newpage'+'\n'+r'\input{chapter}'+'\n'+r'\newpage Segunda pagina.'+'\n'+r'\end{document}')
    (root/'chapter.tex').write_text('% Comentario\n'+r'\section{Prueba de sincronizacion}'+'\n\nTexto reconocible para localizar la fuente.\n')
    result=asyncio.run(compile_latex(root,'main.tex'))
    assert result.success,result.log
    pdf=root/'main.pdf'
    with fitz.open(pdf) as document:
        box=document[1].search_for('Texto reconocible')[0]
    request=dict(page=2,x=(box.x0+box.x1)/2,y=(box.y0+box.y1)/2,pdf_revision=digest(pdf.read_bytes()))
    return SafeStore(root),request


def test_real_synctex_locates_included_file_with_spaces(compiled):
    store,request=compiled
    result=asyncio.run(locate(store,'main.tex',request))
    assert result['path']=='chapter.tex' and result['line']==4
    assert result['revision']==store.read('chapter.tex')['revision']
    import gzip
    sync=store.home/'synctex'/request['pdf_revision']/'main.synctex.gz'
    data=gzip.open(sync,'rt').read()
    chapter_record=next(line for line in data.splitlines() if line.startswith('Input:') and 'chapter.tex' in line)
    assert data.index(chapter_record)>data.index('Content:')


@pytest.mark.parametrize('field,value',[('page',0),('page',True),('page',1.5),('x',-1),('y',float('nan')),('x','10'),('y',float('inf')),('pdf_revision','../escape')])
def test_invalid_requests_rejected(compiled,field,value):
    store,request=compiled
    with pytest.raises(ValueError):asyncio.run(locate(store,'main.tex',{**request,field:value}))


def test_missing_bundle_requests_compile(compiled):
    store,request=compiled
    with pytest.raises(SyncError,match='Compila una vez'):
        asyncio.run(locate(store,'main.tex',{**request,'pdf_revision':'0'*64}))


def test_changed_source_never_navigates_to_wrong_line(compiled):
    store,request=compiled
    before=store.read('chapter.tex')
    store.write('chapter.tex','Nueva línea\n'+before['content'],before['revision'])
    try:
        with pytest.raises(SyncError,match='fuente cambió'):
            asyncio.run(locate(store,'main.tex',request))
    finally:
        store.write('chapter.tex',before['content'])


def test_failed_compile_retains_sync_of_last_good_pdf(compiled):
    store,request=compiled
    before=store.read('main.tex')
    pdf_before=(store.root/'main.pdf').read_bytes()
    store.write('main.tex',r'\documentclass{article}\begin{document}\UndefinedCommand\end{document}')
    try:
        result=asyncio.run(compile_latex(store.root,'main.tex'))
        assert not result.success
        assert (store.root/'main.pdf').read_bytes()==pdf_before
        assert asyncio.run(locate(store,'main.tex',request))['path']=='chapter.tex'
    finally:
        store.write('main.tex',before['content'])


def test_changed_main_configuration_rejected(compiled):
    store,request=compiled
    with pytest.raises(SyncError,match='documento principal'):
        asyncio.run(locate(store,'chapter.tex',request))


def test_corrupted_map_rejected(compiled):
    store,request=compiled
    path=store.home/'synctex'/request['pdf_revision']/'main.synctex.gz'
    original=path.read_bytes()
    try:
        path.write_bytes(b'corrupt')
        with pytest.raises(SyncError,match='incompleta'):
            asyncio.run(locate(store,'main.tex',request))
    finally:
        path.write_bytes(original)


def test_external_paths_and_generated_bibliography_rejected(compiled):
    store,_=compiled
    for path in ['/etc/passwd','../outside.tex',str(store.home/'build/main/main.bbl')]:
        output='Output:main.pdf\nInput:'+path+'\nLine:2\nColumn:-1\n'
        with pytest.raises(SyncError):parse_results(output,store,'main.tex',source_revisions(store))


def test_api_has_inverse_route_and_validation(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from projects import ProjectManager
    import main
    pm=ProjectManager(tmp_path/'registry');pm.create_project('Sync')
    monkeypatch.setattr(main,'project_manager',pm)
    with TestClient(main.app) as client:
        url='/api/projects/Sync/synctex/inverse'
        assert client.post(url,json={'page':0,'x':0,'y':0,'pdf_revision':'0'*64}).status_code==400
        response=client.post(url,json={'page':1,'x':0,'y':0,'pdf_revision':'0'*64})
        assert response.status_code==409 and 'Compila una vez' in response.json()['detail']
