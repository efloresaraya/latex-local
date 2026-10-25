import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from bibliography_order import preview, organize, usage
from references import parse_bib
from safety import SafeStore, ConflictError


def entry(key):
    return '@article{' + key + ', title={Artículo ' + key + '}, author={Autor, Nombre}, journal={Journal}, year={2026}}'


@pytest.fixture
def store(tmp_path):
    (tmp_path/'main.tex').write_text(r'\cite{a}\input{chapter}\cite{c}\bibliographystyle{IEEEtran}\bibliography{refs}')
    (tmp_path/'chapter.tex').write_text(r'\cite{b,a}')
    (tmp_path/'unused.tex').write_text(r'\cite{u}')
    (tmp_path/'refs.bib').write_text('% Cabecera\n'+entry('u')+'\n\n% Nota de b\n'+entry('b')+'\n\n'+entry('c')+'\n\n'+entry('a')+'\n% Fin\n')
    return SafeStore(tmp_path)


def test_inline_order_and_no_preview_writes(store):
    before=store.read('refs.bib')
    plan=preview(store,'main.tex','refs.bib')
    assert plan['used']==['a','b','c'] and plan['unused']==['u']
    assert plan['sources']==['main.tex','chapter.tex']
    assert [e['key'] for e in parse_bib(plan['after'])]==['a','b','c','u']
    assert store.read('refs.bib')==before and not store.home.exists()
    assert '% Cabecera' in plan['after'] and '% Nota de b\n'+entry('b') in plan['after'] and plan['after'].endswith('% Fin\n')


def test_apply_backup_restore_and_idempotence(store):
    before=store.read('refs.bib')
    plan=preview(store,'main.tex','refs.bib')
    result=organize(store,'main.tex',dict(bib_path='refs.bib',token=plan['token']))
    assert result['changed'] and store.read('refs.bib')['content']==plan['after']
    assert {e['key']:e['raw'] for e in parse_bib(before['content'])}=={e['key']:e['raw'] for e in parse_bib(plan['after'])}
    next_plan=preview(store,'main.tex','refs.bib')
    assert not next_plan['changed']
    count=len(store.history('refs.bib'))
    assert not organize(store,'main.tex',dict(bib_path='refs.bib',token=next_plan['token']))['changed']
    assert len(store.history('refs.bib'))==count
    original=next(v for v in store.history('refs.bib') if v['reason'].startswith('antes'))
    store.restore('refs.bib',original['id'],result['revision'])
    assert store.read('refs.bib')==before


@pytest.mark.parametrize('file,addition',[('main.tex',r'\cite{u}'),('chapter.tex',r'\cite{c}'),('refs.bib','\n'+entry('new'))])
def test_stale_preview_does_not_write(store,file,addition):
    plan=preview(store,'main.tex','refs.bib')
    p=store.root/file;p.write_text(p.read_text()+addition)
    before=store.read('refs.bib')
    with pytest.raises(ConflictError):organize(store,'main.tex',dict(bib_path='refs.bib',token=plan['token']))
    assert store.read('refs.bib')==before


def test_nocite_and_missing(store):
    (store.root/'chapter.tex').write_text(r'\nocite{u}\cite{b,missing}')
    p=preview(store,'main.tex','refs.bib')
    assert p['used']==['a','u','b','c'] and p['missing']==['missing']


def test_nocite_star_protects_numbering(store):
    (store.root/'chapter.tex').write_text(r'\nocite{*}')
    p=preview(store,'main.tex','refs.bib')
    assert p['wildcard'] and not p['unused'] and not p['changed']


def test_comments_examples_and_end_document(store):
    (store.root/'chapter.tex').write_text('% \\cite{u}\n'+r'\verb|\cite{u}| \begin{verbatim}\cite{u}\end{verbatim} \cite{b}')
    p=store.root/'main.tex';p.write_text(p.read_text()+r'\end{document}\cite{u}')
    assert preview(store,'main.tex','refs.bib')['unused']==['u']


def test_literal_percent_and_commented_verbatim(store):
    (store.root/'chapter.tex').write_text('% \\begin{verbatim}\n'+r'\verb|% \cite{u}|\cite{b}')
    assert preview(store,'main.tex','refs.bib')['used']==['a','b','c']


def test_includeonly_and_root_relative_input(store):
    (store.root/'sub').mkdir()
    (store.root/'sub'/'part.tex').write_text(r'\input{chapter}')
    (store.root/'main.tex').write_text(r'\includeonly{sub/part}\cite{a}\include{sub/part}\include{missing}\cite{c}\bibliography{refs}')
    assert preview(store,'main.tex','refs.bib')['used']==['a','b','c']


@pytest.mark.parametrize('content',[r'\input{main}',r'\input{missing}'])
def test_incomplete_graph_rejected(store,content):
    (store.root/'chapter.tex').write_text(content)
    with pytest.raises(ValueError):preview(store,'main.tex','refs.bib')
    assert not store.home.exists()


def test_other_active_bib_revision_is_checked(store):
    p=store.root/'main.tex';p.write_text(p.read_text().replace('{refs}','{refs,other}'))
    (store.root/'other.bib').write_text(entry('other'))
    plan=preview(store,'main.tex','refs.bib')
    (store.root/'other.bib').write_text(entry('different'))
    with pytest.raises(ConflictError):organize(store,'main.tex',dict(bib_path='refs.bib',token=plan['token']))


def test_duplicates_dependencies_and_interspersed_macros_rejected(store):
    original=store.read('refs.bib')['content']
    for text in [original+entry('a'),original.replace('title={Artículo a}', 'crossref={u}, title={Artículo a}'),original+'\n@string{venue="Journal"}']:
        (store.root/'refs.bib').write_text(text)
        with pytest.raises(ValueError):preview(store,'main.tex','refs.bib')


def test_preamble_macros_parentheses_crlf_and_percent_preserved(store):
    text='@string{venue="Journal"}\r\n@preamble{"Texto"}\r\n'+entry('u').replace('@article{u,','@article(u,')[:-1]+')\r\n'+entry('a').replace('Journal','https://example.org/a%20b')+'\r\n'
    (store.root/'refs.bib').write_bytes(text.encode())
    p=preview(store,'main.tex','refs.bib')
    assert p['after'].startswith('@string{venue="Journal"}\r\n@preamble{"Texto"}')
    assert 'a%20b' in p['after'] and '\r\n' in p['after']
    assert [e['key'] for e in parse_bib(p['after'])]==['a','u']


def test_inactive_bib_rejected(store):
    (store.root/'inactive.bib').write_text(entry('x'))
    with pytest.raises(ValueError):preview(store,'main.tex','inactive.bib')


def test_api_preview_apply_and_conflict(store,monkeypatch,tmp_path):
    import main
    from projects import ProjectManager
    pm=ProjectManager(tmp_path/'registry')
    pm.create_project('Ordering')
    target=pm.store('Ordering')
    for name in ['main.tex','chapter.tex','refs.bib']:
        target.write(name,store.read(name)['content'])
    monkeypatch.setattr(main,'project_manager',pm)
    with TestClient(main.app) as client:
        url='/api/projects/Ordering/references/organize'
        response=client.post(url+'/preview',json={'bib_path':'refs.bib'})
        assert response.status_code==200,response.text
        token=response.json()['token']
        response=client.post(url,json={'bib_path':'refs.bib','token':token})
        assert response.status_code==200 and response.json()['changed']
        assert client.post(url,json={'bib_path':'refs.bib','token':token}).status_code==409


def test_ieeetran_bibliography_unchanged_after_ordering(tmp_path):
    import asyncio
    from compiler import compile_latex
    (tmp_path/'main.tex').write_text(r'\documentclass{article}\begin{document}Primera \cite{b}. Segunda \cite{a}.\bibliographystyle{IEEEtran}\bibliography{refs}\end{document}')
    (tmp_path/'refs.bib').write_text(entry('u')+'\n'+entry('a')+'\n'+entry('b')+'\n')
    store=SafeStore(tmp_path)
    first=asyncio.run(compile_latex(tmp_path,'main.tex'))
    assert first.success,first.log
    bbl=tmp_path/'.latex-local/build/main/main.bbl'
    before=bbl.read_bytes()
    plan=preview(store,'main.tex','refs.bib')
    organize(store,'main.tex',dict(bib_path='refs.bib',token=plan['token']))
    second=asyncio.run(compile_latex(tmp_path,'main.tex'))
    assert second.success,second.log
    assert bbl.read_bytes()==before
