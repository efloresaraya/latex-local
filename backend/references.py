"""Bibliografía local: lectura, detección de duplicados e incorporación protegida."""
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit
from safety import ConflictError

KEY = re.compile(r'^[A-Za-z0-9_:.+/-]+$')
CATALOG = Path(os.environ.get('LATEX_REFERENCE_CATALOG', Path(__file__).with_name('reference_catalog.json'))).expanduser()


def comments(text):
    text = re.sub(r'\\begin\{comment\}.*?\\end\{comment\}', lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)
    return re.sub(r'(?<!\\)%[^\n]*', lambda m: ' ' * len(m[0]), text)


def group(text, start, opener='{'):
    closer = '}' if opener == '{' else ')'
    depth, quoted, brace_depth, i = 1, False, 0, start + 1
    while i < len(text):
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if opener == '{':
            if c == '{': depth += 1
            elif c == '}': depth -= 1
        else:
            if c == '{': brace_depth += 1
            elif c == '}': brace_depth -= 1
            elif brace_depth == 0:
                if c == '"': quoted = not quoted
                elif not quoted and c == '(': depth += 1
                elif not quoted and c == ')': depth -= 1
        i += 1
        if depth == 0: return text[start+1:i-1], i
    raise ValueError('BibTeX incompleto: hay llaves, comillas o paréntesis sin cerrar.')


def fields(body):
    result, pos = {}, 0
    while pos < len(body):
        skip = re.match(r'[\s,]*', body[pos:]); pos += skip.end()
        if pos == len(body): break
        match = re.match(r'([A-Za-z][\w-]*)\s*=\s*', body[pos:])
        if not match: raise ValueError('Campo BibTeX inválido cerca de: ' + body[pos:pos+50])
        name = match[1].lower(); pos += match.end(); values=[]
        while True:
            if pos >= len(body): raise ValueError('Campo BibTeX sin valor: ' + name)
            if body[pos] == '{':
                value, pos = group(body, pos)
            elif body[pos] == '"':
                start=pos+1;pos=start;depth=0
                while pos<len(body):
                    c=body[pos]
                    if c=='\\':pos+=2;continue
                    if c=='{':depth+=1
                    elif c=='}':depth-=1
                    elif c=='"' and depth==0:break
                    pos+=1
                if pos==len(body):raise ValueError('Comillas BibTeX sin cerrar.')
                value=body[start:pos];pos+=1
            else:
                match=re.match(r'[^\s,#{}()"]+', body[pos:])
                if not match:raise ValueError('Valor BibTeX inválido.')
                value=match[0];pos+=match.end()
            values.append(value)
            while pos<len(body) and body[pos].isspace():pos+=1
            if pos<len(body) and body[pos]=='#':
                pos+=1
                while pos<len(body) and body[pos].isspace():pos+=1
                continue
            break
        if name in result:raise ValueError('Campo BibTeX duplicado: '+name)
        result[name]=''.join(values)
        if pos<len(body) and body[pos]!=',':raise ValueError('Falta una coma entre campos BibTeX.')
    return result


def bib_comments(text):
    # Percent signs in BibTeX values (e.g. percent-encoded DOI URLs) are data.
    chars=list(text);i=0;depth=0;root=None;quoted=False
    while i<len(text):
        c=text[i]
        if c=='\\':i+=2;continue
        if root is None and c=='@':
            match=re.match(r'@[A-Za-z]+\s*([({])',text[i:])
            if match:root=match[1];depth=1 if root=='{' else 0;i+=match.end();continue
        threshold=1 if root=='{' else 0
        if c=='%' and depth<=threshold and not quoted:
            end=text.find('\n',i);end=len(text) if end<0 else end
            chars[i:end]=[' ']*(end-i);i=end;continue
        if root:
            if c=='"' and depth==threshold:quoted=not quoted
            elif c=='{':depth+=1
            elif c=='}':
                depth-=1
                if root=='{' and depth==0:root=None;quoted=False
            elif root=='(' and c==')' and depth==0 and not quoted:root=None
        i+=1
    return ''.join(chars)


def parse_bib(text):
    clean=bib_comments(text); entries=[];pos=0
    while True:
        match=re.search(r'@([A-Za-z]+)\s*([({])', clean[pos:])
        if not match:break
        start=pos+match.start(); opening=pos+match.end()-1
        body,end=group(clean,opening,match[2]);kind=match[1].lower()
        if kind not in {'comment','string','preamble'}:
            if ',' not in body:raise ValueError('Entrada BibTeX sin campos.')
            key,rest=body.split(',',1);key=key.strip()
            if not KEY.fullmatch(key):raise ValueError('Clave BibTeX inválida: '+key)
            data=fields(rest)
            entries.append(dict(key=key,fields=data,raw=text[start:end],start=start,end=end))
        pos=end
    return entries


def doi(value):
    value=re.sub(r'\\([_%&#])', r'\1', value or '')
    if re.match(r'^https?://(?:dx\.)?doi\.org/',value,re.I):value=urlsplit(value).path.lstrip('/')
    value=unquote(value)
    match=re.search(r'10\.\d{4,9}/[^\s{}<>"\\]+', value, re.I)
    return match[0].lower().rstrip('.,;:') if match else ''


def entry_doi(entry):
    f=entry['fields']
    return doi(f.get('doi','')) or doi(f.get('url','')) or doi(f.get('note',''))


def norm(value):
    value=unicodedata.normalize('NFKD',value.lower())
    return re.sub(r'[^a-z0-9]', '', value)


def equivalent(candidate, entries):
    key=candidate['key']; cd=entry_doi(candidate)
    same_key=next((e for e in entries if e['key'].casefold()==key.casefold()), None)
    if same_key:
        ed=entry_doi(same_key)
        if cd and ed and cd!=ed:raise ValueError(f'La clave {key} ya corresponde a otro DOI. Usa una clave distinta.')
        ct=norm(candidate['fields'].get('title',''));et=norm(same_key['fields'].get('title',''))
        if not (cd and cd==ed) and ct and et and ct!=et:raise ValueError(f'La clave {key} ya corresponde a otro título. Usa una clave distinta.')
        return same_key
    if cd:
        hit=next((e for e in entries if entry_doi(e)==cd),None)
        if hit:return hit
    ct=norm(candidate['fields'].get('title',''))
    if len(ct)>=30:
        hit=next((e for e in entries if norm(e['fields'].get('title',''))==ct and not (cd and entry_doi(e) and cd!=entry_doi(e))),None)
        if hit:return hit
    return None


def source_graph(store, main):
    sources={}
    def visit(rel):
        path=store.path(rel); rel=path.relative_to(store.root).as_posix()
        if rel in sources:return
        text=comments(path.read_text());sources[rel]=text
        for match in re.finditer(r'\\(?:input|include)\s*\{([^}]+)\}',text):
            child=Path(rel).parent/match[1]
            if not child.suffix:child=child.with_suffix('.tex')
            if store.path(child.as_posix()).exists():visit(child.as_posix())
    visit(main)
    return sources


def inspect(store, main):
    sources=source_graph(store,main);paths=[];cited=[]
    for rel,text in sources.items():
        for match in re.finditer(r'\\(?:bibliography|addbibresource)\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}',text):
            for name in match[1].split(','):
                path=Path(name.strip())
                if not path.suffix:path=path.with_suffix('.bib')
                # BibTeX resolves paths from the main document's directory.
                path=(Path(main).parent/path).as_posix()
                store.path(path)
                if path not in paths:paths.append(path)
        for match in re.finditer(r'\\(?:[Cc]ite\w*|nocite)\*?\s*(?:\[[^]]*\]\s*)*\{([^}]+)\}',text):
            for key in match[1].split(','):
                key=key.strip()
                if key and key!='*':cited.append(dict(key=key,path=rel,line=text.count('\n',0,match.start())+1))
    bibs=[];entries=[]
    for path in paths:
        try:current=store.read(path)
        except FileNotFoundError:current=dict(content='',revision='missing')
        parsed=parse_bib(current['content']);entries.extend(parsed)
        bibs.append(dict(path=path,revision=current['revision'],count=len(parsed)))
    keys={e['key'] for e in entries}
    missing=[c for c in cited if c['key'] not in keys]
    catalog=json.loads(CATALOG.read_text()) if CATALOG.exists() else []
    rows=[]
    for item in catalog:
        candidate=parse_bib(item['bibtex'])[0]
        try:
            hit=equivalent(candidate,entries);conflict=None
        except ValueError as error:
            hit=None;conflict=str(error)
        rows.append(dict(item,present_key=hit['key'] if hit else None,conflict=conflict))
    return dict(bibs=bibs,catalog=rows,missing_citations=missing,keys=sorted(keys),
                style='IEEEtran' if any(re.search(r'\\bibliographystyle\s*\{IEEEtran\}',s) for s in sources.values()) else None)


def add(store, main, data):
    path=data.get('bib_path');revision=data.get('revision')
    if not isinstance(path,str) or not isinstance(revision,str):raise ValueError('Selecciona la bibliografía y su revisión antes de incorporar.')
    info=inspect(store,main)
    if path not in {b['path'] for b in info['bibs']}:raise ValueError('Selecciona un .bib utilizado por el documento principal.')
    text=data.get('bibtex')
    if data.get('catalog_id'):
        item=next((r for r in info['catalog'] if r['id']==data['catalog_id']),None)
        if not item:raise ValueError('Referencia local no encontrada.')
        text=item['bibtex']
    if not isinstance(text,str) or len(text)>100000:raise ValueError('Pega una entrada BibTeX válida (máximo 100 KB).')
    candidates=parse_bib(text)
    if len(candidates)!=1:raise ValueError('Incorpora una sola entrada BibTeX cada vez.')
    candidate=candidates[0]
    if comments(text[:candidate['start']]+text[candidate['end']:]).strip():raise ValueError('La entrada contiene texto ajeno a BibTeX.')
    if not any(candidate['fields'].get(k) for k in ('title','note')):raise ValueError('La referencia necesita título o una transcripción bibliográfica en note.')
    requested=data.get('requested_key')
    if requested and candidate['key']!=requested:raise ValueError('La clave debe coincidir con la cita pendiente: '+requested)
    # Read again, then commit with CAS. A concurrent save never gets overwritten.
    try:current=store.read(path)
    except FileNotFoundError:current=dict(content='',revision='missing')
    if current['revision']!=revision:raise ConflictError('La bibliografía cambió. Reabre el módulo para revisar la versión actual.')
    all_entries=[]
    for b in info['bibs']:
        try:all_entries.extend(parse_bib(store.read(b['path'])['content']))
        except FileNotFoundError:pass
    hit=equivalent(candidate,all_entries)
    if hit:return dict(added=False,key=hit['key'],requested_key=candidate['key'],cite='\\cite{'+hit['key']+'}',path=path,revision=current['revision'])
    original=current['content'];newline='\r\n' if '\r\n' in original else '\n'
    separator='' if not original else (newline if original.endswith('\n') else newline*2)
    appended=candidate['raw'].replace('\r\n','\n').replace('\n',newline)
    result=store.write(path,original+separator+appended+newline,revision,reason='incorporar referencia '+candidate['key'])
    return dict(result,added=True,key=candidate['key'],requested_key=candidate['key'],cite='\\cite{'+candidate['key']+'}',path=path)
