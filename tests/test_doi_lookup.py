import json
import re
import sys
from pathlib import Path
from unittest.mock import patch
import httpx
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import doi_lookup as dl
from references import add, parse_bib, entry_doi
from safety import SafeStore

DOI='10.4321/brand-new'
BIB='@article{Original_2026, title={A newly registered scientific article}, author={Apellido, Nombre}, year={2026}, journal={Research}, doi={10.4321/brand-new}}'

@pytest.fixture(autouse=True)
def clear_cache():
    dl._CACHE.clear()
    yield
    dl._CACHE.clear()

@pytest.fixture
def store(tmp_path):
    (tmp_path/'main.tex').write_text(r'''\documentclass{article}\begin{document}
\cite{Original}\bibliographystyle{IEEEtran}\bibliography{refs}\end{document}''')
    (tmp_path/'refs.bib').write_text('@article{Original, title={Existing study}, doi={10.4321/EXISTING}, author={Autor, Nombre}, year={2020}}\n')
    return SafeStore(tmp_path)

@pytest.mark.parametrize('value',['10.4321/Brand-New','doi: 10.4321/BRAND-NEW','https://doi.org/10.4321%2FBRAND-NEW','http://dx.doi.org/10.4321/Brand-New','10.4321/brand-new.'])
def test_normalize_inputs(value):assert dl.normalize_doi(value)==DOI

@pytest.mark.parametrize('value',[None,'','1234/abc','https://evil.test/10.4321/abc','10.4321/a b','https://doi.org@evil.test/10.4321/a','10.4321/a\nother'])
def test_reject_invalid_input(value):
    with pytest.raises(ValueError):dl.normalize_doi(value)


def test_duplicate_detected_locally_with_citation_location_without_network(store):
    with patch.object(dl,'fetch_bibtex',side_effect=AssertionError('No consultar red')):
        result=dl.lookup(store,'main.tex','https://doi.org/10.4321/existing')
    assert result['present_key']=='Original'
    assert result['source']=='Bibliografía local'
    assert result['cite']==r'\cite{Original}'
    assert result['citations'][0]['path']=='main.tex'
    assert result['matches'][0]['active'] is True
    assert len(parse_bib(store.read('refs.bib')['content']))==1


def test_inactive_bib_detected_and_reused_without_network(store):
    (store.root/'otra.bib').write_text(BIB)
    result=dl.lookup(store,'main.tex',DOI,False)
    assert result['matches']==[dict(key='Original_2026',path='otra.bib',active=False)]
    assert result['present_key'] is None and result['source']=='Bibliografía local'
    assert result['key']=='Original_2026'


def test_catalog_lookup_operates_offline(store):
    with patch.object(dl,'fetch_bibtex',side_effect=AssertionError('No red')):
        result=dl.lookup(store,'main.tex','10.4321/catalog',False)
    assert result['key']=='Catalog2026' and result['source'].startswith('Catálogo local')
    assert entry_doi(parse_bib(result['bibtex'])[0])=='10.4321/catalog'


def test_offline_unknown_doi_does_not_use_api(store):
    with patch.object(dl,'fetch_bibtex',side_effect=AssertionError('No red')):
        with pytest.raises(dl.LookupError) as error:dl.lookup(store,'main.tex',DOI,False)
    assert error.value.status==404


def test_crossref_lookup_generates_key_without_writing_and_then_safe_add(store):
    calls=[]
    def handler(request):calls.append(str(request.url));return httpx.Response(200,text=BIB)
    before=store.read('refs.bib')
    result=dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(handler))
    assert result['source']=='Crossref' and result['key']=='Apellido2026'
    assert len(calls)==1 and 'api.crossref.org' in calls[0]
    assert store.read('refs.bib')==before
    saved=add(store,'main.tex',dict(bib_path='refs.bib',revision=before['revision'],bibtex=result['bibtex']))
    assert saved['added'] and saved['key']=='Apellido2026'
    assert len(store.history('refs.bib'))==2
    assert dl.lookup(store,'main.tex',DOI,False)['present_key']=='Apellido2026'


def test_datacite_fallback(store):
    calls=[]
    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(404) if request.url.host=='api.crossref.org' else httpx.Response(200,text=BIB)
    result=dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(handler))
    assert result['source']=='DataCite'
    assert calls==['api.crossref.org','data.datacite.org']


def test_requested_missing_key_and_existing_key_collision(store):
    transport=httpx.MockTransport(lambda _:httpx.Response(200,text=BIB))
    assert dl.lookup(store,'main.tex',DOI,requested_key='Faltante2026',transport=transport)['key']=='Faltante2026'
    original=store.read('refs.bib');store.write('refs.bib',original['content']+'\n'+BIB.replace('Original_2026','Apellido2026').replace(DOI,'10.4321/different'),original['revision'])
    assert dl.lookup(store,'main.tex',DOI,transport=transport)['key']=='Apellido20262'


def test_cache_does_not_bypass_fresh_local_duplicate_check(store):
    transport=httpx.MockTransport(lambda _:httpx.Response(200,text=BIB))
    first=dl.lookup(store,'main.tex',DOI,transport=transport)
    assert dl.lookup(store,'main.tex',DOI,transport=transport)['cached']
    cur=store.read('refs.bib');store.write('refs.bib',cur['content']+'\n'+BIB,cur['revision'])
    assert dl.lookup(store,'main.tex',DOI,transport=transport)['present_key']=='Original_2026'

@pytest.mark.parametrize('status,message',[(429,'límite'),(503,'disponible')])
def test_service_error_does_not_write(store,status,message):
    before=store.read('refs.bib')
    with pytest.raises(dl.LookupError,match=message):dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(lambda _:httpx.Response(status)))
    assert store.read('refs.bib')==before

@pytest.mark.parametrize('body',[BIB.replace(DOI,'10.4321/wrong'),'<html>Error</html>',BIB+BIB,'@article{Bad,title={no cierre}'])
def test_wrong_or_invalid_metadata_never_added(store,body):
    with pytest.raises(dl.LookupError):dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(lambda _:httpx.Response(200,text=body)))
    assert len(parse_bib(store.read('refs.bib')['content']))==1


def test_redirects_cannot_target_local_or_unapproved_hosts(store):
    with pytest.raises(dl.LookupError,match='destino no admitido'):
        dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(lambda _:httpx.Response(302,headers={'location':'http://127.0.0.1/secret'})))


def test_not_found_or_timeout_are_clear(store):
    with pytest.raises(dl.LookupError) as error:dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(lambda _:httpx.Response(404)))
    assert error.value.status==404
    def timeout(request):raise httpx.ReadTimeout('timeout',request=request)
    with pytest.raises(dl.LookupError) as error:dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(timeout))
    assert error.value.status==504


def test_large_responses_are_bounded(store):
    with pytest.raises(dl.LookupError,match='demasiado grande'):dl.lookup(store,'main.tex',DOI,transport=httpx.MockTransport(lambda _:httpx.Response(200,text='x'*100001)))


def test_hidden_backups_are_not_scanned_and_escaped_doi_matches(store):
    hidden=store.root/'.latex-local';hidden.mkdir();(hidden/'old.bib').write_text(BIB)
    (store.root/'extra.bib').write_text(BIB.replace('brand-new',r'brand\_new'))
    result=dl.lookup(store,'main.tex','10.4321/brand_new',False)
    assert result['matches'][0]['path']=='extra.bib'
    with pytest.raises(dl.LookupError):dl.lookup(store,'main.tex',DOI,False)


def test_api_doi_route_and_local_only_option(tmp_path,monkeypatch):
    import main
    from projects import ProjectManager
    from fastapi.testclient import TestClient
    manager=ProjectManager(tmp_path/'registry');manager.create_project('Prueba')
    project=manager.store('Prueba');project.write('main.tex',r'\bibliography{refs}')
    project.write('refs.bib',BIB)
    monkeypatch.setattr(main,'project_manager',manager)
    with TestClient(main.app) as client:
        result=client.post('/api/projects/Prueba/references/doi',json=dict(doi=DOI,allow_external=False))
        assert result.status_code==200 and result.json()['present_key']=='Original_2026'
        assert client.post('/api/projects/Prueba/references/doi',json=dict(doi='invalid')).status_code==400
        assert client.post('/api/projects/Prueba/references/doi',json=dict(doi=DOI,allow_external='false')).status_code==400
        missing=client.post('/api/projects/Prueba/references/doi',json=dict(doi='10.4321/no-such-doi',allow_external=False))
        assert missing.status_code==404 and 'catálogo local' in missing.json()['detail']


def test_percent_encoded_doi_urls_are_detected():
    entry=parse_bib('@article{X,title={Test},url={https://doi.org/10.4321%2FEXISTING?download=1}}')[0]
    assert entry_doi(entry)=='10.4321/existing'
