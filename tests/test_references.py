import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import main
from references import add, inspect, parse_bib, CATALOG
from safety import SafeStore, ConflictError
from projects import ProjectManager
from compiler import compile_latex

OLD='@article{Old, title={An existing article about filters}, author={Autor, Nombre}, journal={Journal}, year={2020}, doi={10.1234/old}}\n'
NEW='@article{New, title={Another article about filters}, author={Otro, Autor}, journal={Journal}, year={2026}, doi={10.1234/new}}'

@pytest.fixture
def project(tmp_path):
    (tmp_path/'main.tex').write_text(r'''\documentclass{article}
\usepackage{hyperref}
\begin{document}Primera \cite{Old}. Nueva \cite{New}.
\bibliographystyle{IEEEtran}\bibliography{refs}\end{document}''')
    (tmp_path/'refs.bib').write_bytes(OLD.encode())
    return SafeStore(tmp_path)

def payload(store,bibtex=NEW):
    return dict(bib_path='refs.bib',revision=store.read('refs.bib')['revision'],bibtex=bibtex)

def test_graph_and_comments_only_active_citations(project):
    (project.root/'section.tex').write_text(r'% \cite{Comment}'+'\n'+r'\cite[ver][p. 2]{Missing,Old}')
    with (project.root/'main.tex').open('a') as f:f.write('\n'+r'\input{section}')
    (project.root/'unused.tex').write_text(r'\cite{Unused}')
    result=inspect(project,'main.tex')
    assert result['style']=='IEEEtran'
    assert [r['key'] for r in result['missing_citations']]==['New','Missing']
    assert result['bibs'][0]['count']==1

def test_safe_append_and_history_restore(project):
    before=(project.root/'refs.bib').read_bytes()
    result=add(project,'main.tex',payload(project))
    assert result['added'] and result['cite']==r'\cite{New}'
    assert (project.root/'refs.bib').read_bytes().startswith(before)
    assert len(parse_bib(project.read('refs.bib')['content']))==2
    history=project.history('refs.bib')
    old=next(v for v in history if v['reason'].startswith('antes'))
    project.restore('refs.bib',old['id'],result['revision'])
    assert (project.root/'refs.bib').read_bytes()==before

def test_duplicate_doi_reuses_actual_key(project):
    result=add(project,'main.tex',payload(project,OLD.replace('{Old,','{OtherKey,')))
    assert result['added'] is False and result['key']=='Old'
    assert project.read('refs.bib')['content']==OLD

def test_key_collision_is_not_silent(project):
    with pytest.raises(ValueError,match='otro DOI'):
        add(project,'main.tex',payload(project,NEW.replace('{New,','{Old,')))
    assert project.read('refs.bib')['content']==OLD

def test_stale_revision_preserves_external_changes(project):
    request=payload(project)
    external=OLD+'\n% cambio externo\n';(project.root/'refs.bib').write_text(external)
    with pytest.raises(ConflictError):add(project,'main.tex',request)
    assert project.read('refs.bib')['content']==external

def test_backup_failure_cannot_change_bibliography(project):
    with patch.object(SafeStore,'_record',side_effect=OSError('respaldo falló')):
        with pytest.raises(OSError):add(project,'main.tex',payload(project))
    assert project.read('refs.bib')['content']==OLD

@pytest.mark.parametrize('invalid',[NEW+NEW,'texto suelto\n'+NEW,'@article{New,title={sin cierre}', '@article{New,title="sin cierre}', '@article{New,title={A} author={B}}', '@article{New,year={2026}}'])
def test_bad_bibtex_rejected_without_writes(project,invalid):
    with pytest.raises(ValueError):add(project,'main.tex',payload(project,invalid))
    assert project.read('refs.bib')['content']==OLD

def test_manual_key_must_match_missing_citation(project):
    request=dict(payload(project),requested_key='Wrong')
    with pytest.raises(ValueError,match='coincidir'):add(project,'main.tex',request)

def test_all_catalog_entries_parse_and_shared_doi_is_unique():
    catalog=json.loads(CATALOG.read_text());assert len(catalog)==2
    ids=set()
    for row in catalog:
        assert row['id'] not in ids;ids.add(row['id'])
        assert len(parse_bib(row['bibtex']))==1
        assert row['sources'] and row['format']
    assert len([r for r in catalog if '10.4321/catalog' in r['dois']])==1

def test_catalog_incorporation_uses_source_not_client_text(project):
    row=json.loads(CATALOG.read_text())[0]
    result=add(project,'main.tex',dict(payload(project),catalog_id=row['id'],bibtex='invalid'))
    assert result['added'] and result['key']==row['key']

def test_missing_bib_can_be_created(project):
    (project.root/'refs.bib').unlink()
    result=add(project,'main.tex',dict(bib_path='refs.bib',revision='missing',bibtex=NEW))
    assert result['added']

def test_only_declared_bibliography_allowed(project):
    with pytest.raises(ValueError,match='utilizado'):
        add(project,'main.tex',dict(payload(project),bib_path='../escape.bib'))

def test_preserve_crlf_bytes(project):
    old=OLD.replace('\n','\r\n').encode();(project.root/'refs.bib').write_bytes(old)
    add(project,'main.tex',payload(project))
    assert (project.root/'refs.bib').read_bytes().startswith(old)

def test_real_ieeetran_numbers_by_citation_not_bib_position(project):
    add(project,'main.tex',payload(project))
    # New is physically last in .bib; cite it FIRST in TeX.
    path=project.root/'main.tex';path.write_text(path.read_text().replace(r'Primera \cite{Old}. Nueva \cite{New}.',r'Primera \cite{New}. Nueva \cite{Old}.'))
    result=asyncio.run(compile_latex(project.root,'main.tex'));assert result.success,result.log
    bbl=(project.root/'.latex-local/build/main/main.bbl').read_text()
    assert bbl.index(r'\bibitem{New}')<bbl.index(r'\bibitem{Old}')

def test_literal_catalog_reference_compiles_without_invented_fields(project):
    row=next(r for r in json.loads(CATALOG.read_text()) if r['format'].startswith('Transcripción'))
    add(project,'main.tex',dict(payload(project),catalog_id=row['id']))
    path=project.root/'main.tex';path.write_text(path.read_text().replace(r'\cite{New}',r'\cite{'+row['key']+'}'))
    result=asyncio.run(compile_latex(project.root,'main.tex'));assert result.success,result.log
    assert '\\bibitem{'+row['key']+'}' in (project.root/'.latex-local/build/main/main.bbl').read_text()

def test_api_end_to_end_and_conflict(tmp_path,monkeypatch):
    pm=ProjectManager(tmp_path/'registry');pm.create_project('Test')
    store=pm.store('Test');store.write('main.tex',r'\bibliographystyle{IEEEtran}\bibliography{refs}')
    store.write('refs.bib',OLD);monkeypatch.setattr(main,'project_manager',pm)
    with TestClient(main.app) as client:
        info=client.get('/api/projects/Test/references').json();assert info['bibs'][0]['count']==1
        request=payload(store)
        result=client.post('/api/projects/Test/references',json=request);assert result.status_code==200,result.text
        assert result.json()['cite']==r'\cite{New}'
        assert client.post('/api/projects/Test/references',json=request).status_code==409
        assert len(parse_bib(store.read('refs.bib')['content']))==2

def test_parallel_incorporations_never_lose_a_reference(project):
    from concurrent.futures import ThreadPoolExecutor
    request=payload(project)
    def run(key):
        try:return add(project,'main.tex',dict(request,bibtex=NEW.replace('New',key).replace('10.1234/new','10.1234/'+key)))
        except ConflictError:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['First','Second']))
    assert sum(isinstance(r,dict) and r['added'] for r in results)==1
    assert results.count('conflict')==1
    assert len(parse_bib(project.read('refs.bib')['content']))==2
    assert project.read('refs.bib')['content'].startswith(OLD)


def test_entire_local_catalog_is_usable_with_ieeetran(tmp_path):
    catalog=json.loads(CATALOG.read_text())
    (tmp_path/'refs.bib').write_text('\n\n'.join(row['bibtex'] for row in catalog))
    (tmp_path/'main.tex').write_text(r'''\documentclass{article}
\usepackage[T1]{fontenc}\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb,hyperref}
\begin{document}\nocite{*}\bibliographystyle{IEEEtran}\bibliography{refs}\end{document}''')
    result=asyncio.run(compile_latex(tmp_path,'main.tex'));assert result.success,result.log
    bbl=(tmp_path/'.latex-local/build/main/main.bbl').read_text()
    assert len(__import__('re').findall(r'\\bibitem\{',bbl))==len(catalog)
