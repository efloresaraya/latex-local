"""DOI: bibliografía y catálogo locales primero; metadatos públicos como respaldo."""
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urljoin
import httpx
from references import CATALOG, KEY, comments, entry_doi, inspect, parse_bib, source_graph

ALLOWED_HOSTS={'api.crossref.org','data.datacite.org','data.crosscite.org'}
_CACHE={}
_CACHE_LOCK=threading.Lock()
_NETWORK_SLOTS=threading.BoundedSemaphore(2)
MAX_BYTES=100000

class LookupError(Exception):
    def __init__(self,message,status=502):self.status=status;super().__init__(message)


def normalize_doi(value):
    if not isinstance(value,str) or len(value)>2000:raise ValueError('Introduce un DOI o un enlace https://doi.org/… válido.')
    value=value.strip()
    if re.match(r'^https?://',value,re.I):
        parsed=urlsplit(value)
        if parsed.hostname not in {'doi.org','dx.doi.org','www.doi.org'} or parsed.username or parsed.password:raise ValueError('Usa el DOI o su enlace en doi.org; no una URL de otra página.')
        value=unquote(parsed.path.lstrip('/'))
    else:value=unquote(re.sub(r'^doi\s*:\s*','',value,flags=re.I))
    value=value.strip().rstrip('.,;')
    if not re.fullmatch(r'10\.\d{4,9}/[^\s<>"{}\\]+',value,re.I) or any(ord(c)<32 for c in value):raise ValueError('El DOI debe tener la forma 10.1234/identificador.')
    return value.lower()


def local_entries(store,main):
    info=inspect(store,main);active={b['path'] for b in info['bibs']};result=[];warnings=[]
    paths=set(active)
    for directory, folders, files in os.walk(store.root, followlinks=False):
        folders[:]=[name for name in folders if not name.startswith('.')]
        for name in files:
            if name.lower().endswith('.bib') and not name.startswith('.'):
                paths.add((Path(directory)/name).relative_to(store.root).as_posix())
    for rel in sorted(paths):
        try:
            text=store.read(rel)['content']
            result.extend(dict(e,path=rel,active=rel in active) for e in parse_bib(text))
        except FileNotFoundError:continue
        except (ValueError,UnicodeError) as error:
            warnings.append(f'No se pudo revisar {rel}: {error}')
    return info,result,warnings


def citation_locations(store,main,keys):
    locations=[]
    for rel,text in source_graph(store,main).items():
        for match in re.finditer(r'\\(?:[Cc]ite\w*|nocite)\*?\s*(?:\[[^]]*\]\s*)*\{([^}]+)\}',text):
            cited=set(k.strip() for k in match[1].split(','))
            if cited & keys:locations.append(dict(path=rel,line=text.count('\n',0,match.start())+1,keys=sorted(cited & keys)))
    return locations


def _download(client,url):
    for _ in range(4):
        target=urlsplit(url)
        if target.scheme!='https' or target.hostname not in ALLOWED_HOSTS or target.username or target.password or target.port not in (None,443):raise LookupError('El servicio bibliográfico redirigió a un destino no admitido.')
        with client.stream('GET',url,headers={'Accept':'application/x-bibtex','User-Agent':'LaTeXLocal/0.1.0 (DOI metadata lookup)'}) as response:
            if response.status_code in {301,302,303,307,308}:
                url=urljoin(url,response.headers.get('location',''));continue
            if response.status_code in {404,406}:return None
            if response.status_code==429:raise LookupError('El servicio alcanzó su límite de consultas. Espera un momento y vuelve a intentar.',429)
            if response.status_code!=200:raise LookupError('El servicio bibliográfico no está disponible en este momento. Intenta más tarde.')
            data=bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>MAX_BYTES:raise LookupError('La respuesta bibliográfica es demasiado grande para una referencia.')
            try:return bytes(data).decode('utf-8-sig')
            except UnicodeError as error:raise LookupError('El servicio devolvió una referencia con codificación inválida.') from error
    raise LookupError('El servicio bibliográfico devolvió demasiadas redirecciones.')


def fetch_bibtex(doi,transport=None):
    with _CACHE_LOCK:
        cached=_CACHE.get(doi)
        if cached and time.monotonic()-cached[0]<21600:return dict(cached[1],cached=True)
    if not _NETWORK_SLOTS.acquire(blocking=False):raise LookupError('Ya hay dos búsquedas en curso. Espera a que terminen.',429)
    try:
        with httpx.Client(timeout=httpx.Timeout(15,connect=5),follow_redirects=False,transport=transport) as client:
            encoded=quote(doi,safe='')
            for service,url in [('Crossref',f'https://api.crossref.org/works/{encoded}/transform/application/x-bibtex'),('DataCite',f'https://data.datacite.org/application/x-bibtex/{encoded}')]:
                text=_download(client,url)
                if text is None:continue
                try:entries=parse_bib(text)
                except ValueError as error:raise LookupError('El servicio devolvió BibTeX incompleto o inválido.') from error
                if len(entries)!=1 or entry_doi(entries[0])!=doi:raise LookupError('La referencia recibida no coincide con el DOI solicitado. No se incorporó.')
                entry=entries[0]
                if comments(text[:entry['start']]+text[entry['end']:]).strip():raise LookupError('La respuesta contiene contenido ajeno a la referencia.')
                if not entry['fields'].get('title'):raise LookupError('El registro no tiene título; revisa los datos en la publicación.')
                result=dict(bibtex=entry['raw'],source=service,source_url=url,retrieved_at=datetime.now(timezone.utc).isoformat(),cached=False)
                with _CACHE_LOCK:
                    if len(_CACHE)>=256:_CACHE.pop(next(iter(_CACHE)))
                    _CACHE[doi]=(time.monotonic(),result)
                return result
    except httpx.TimeoutException as error:raise LookupError('La búsqueda tardó demasiado. La comprobación local sigue disponible; intenta más tarde.',504) from error
    except httpx.RequestError as error:raise LookupError('No se pudo conectar al servicio de metadatos. Revisa tu conexión; tus archivos no cambiaron.',503) from error
    finally:_NETWORK_SLOTS.release()
    raise LookupError('DOI no encontrado en Crossref ni DataCite. Verifica el identificador o pega el BibTeX de la publicación.',404)


def propose_key(entry,existing,requested=None):
    if requested:
        if not KEY.fullmatch(requested):raise ValueError('La clave pendiente no es una clave BibTeX válida.')
        if requested.casefold() not in {k.casefold() for k in existing}:return requested
    fields=entry['fields'];author=fields.get('author','').split(' and ')[0]
    surname=author.split(',')[0] if ',' in author else (author.split()[-1] if author.split() else 'Referencia')
    surname=re.sub(r'[^A-Za-z0-9]','',unicodedata.normalize('NFKD',surname)) or 'Referencia'
    year=re.search(r'\b(?:19|20)\d{2}\b',fields.get('year',''))
    base=surname[:35]+(year[0] if year else '')
    key=base;i=2;used={k.casefold() for k in existing}
    while key.casefold() in used:key=base+str(i);i+=1
    return key


def lookup(store,main,value,allow_external=True,requested_key=None,transport=None):
    normalized=normalize_doi(value)
    info,entries,warnings=local_entries(store,main)
    hits=[e for e in entries if entry_doi(e)==normalized]
    matches=[dict(key=e['key'],path=e['path'],active=e['active']) for e in hits]
    locations=citation_locations(store,main,{e['key'] for e in hits})
    active_hit=next((e for e in hits if e['active']),None)
    if hits:
        chosen=active_hit or hits[0];data=dict(bibtex=chosen['raw'],source='Bibliografía local',source_url=None,retrieved_at=None,cached=False)
    else:
        catalog=json.loads(CATALOG.read_text()) if CATALOG.exists() else []
        item=next((r for r in catalog if normalized in r['dois']),None)
        if item:data=dict(bibtex=item['bibtex'],source='Catálogo local · '+' / '.join(item['sources']),source_url=None,retrieved_at=None,cached=False)
        elif allow_external:data=fetch_bibtex(normalized,transport)
        else:raise LookupError('DOI no encontrado en tus archivos ni en el catálogo local. Activa la consulta de metadatos públicos o pega el BibTeX.',404)
    candidate=parse_bib(data['bibtex'])[0]
    if active_hit:key=active_hit['key']
    else:
        key=propose_key(candidate,[e['key'] for e in entries],requested_key)
        # Prefer the catalog's established key if free; keep an explicitly requested citation key.
        if not requested_key and (hits or data['source'].startswith('Catálogo local')) and candidate['key'].casefold() not in {e['key'].casefold() for e in entries}:key=candidate['key']
        elif hits and not requested_key:key=candidate['key']
    data['bibtex']=re.sub(r'^(@\w+\s*[({]\s*)[^,]+',lambda m:m[1]+key,candidate['raw'],count=1)
    f=candidate['fields']
    title=f.get('title')
    if not title and CATALOG.exists():
        title=next((r['title'] for r in json.loads(CATALOG.read_text()) if normalized in r['dois']),None)
    return dict(data,doi=normalized,key=key,cite='\\cite{'+key+'}',title=title or f.get('note',''),author=f.get('author',''),year=f.get('year',''),present_key=active_hit['key'] if active_hit else None,matches=matches,citations=locations,warnings=warnings)
