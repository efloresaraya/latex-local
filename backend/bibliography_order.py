"""Vista previa y reorganización reversible de una bibliografía activa."""
import json
import re
from pathlib import Path
from references import parse_bib, bib_comments
from safety import ConflictError, digest


def source_text(text):
    # Lex in document order: a comment cannot open a verbatim block, and a
    # percent sign inside a literal example cannot hide its closing delimiter.
    pattern = (r'(?<!\\)%[^\n]*|'
               r'\\begin\{(verbatim\*?|Verbatim|lstlisting|minted|comment)\}.*?\\end\{\1\}|'
               r'\\verb\*?([^\w\s]).*?\2')
    return re.sub(pattern, lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)


def usage(store, main):
    revisions, citations, bibs = {}, [], []
    wildcard = False
    stopped = False
    root = Path(main).parent
    includeonly = None
    first = source_text(store.read(main)['content'])
    only = re.search(r'\\includeonly\s*\{([^}]*)\}', first)
    if only is not None:
        includeonly = {n.strip().removesuffix('.tex') for n in only[1].split(',')}
    token = re.compile(r'\\(?:input|include)(?![A-Za-z])\s*(?:\{[^}]+\}|[^\s{}%]+)|'
                       r'\\(?:bibliography|addbibresource)\s*(?:\[[^]]*\]\s*)?\{[^}]+\}|'
                       r'\\(?:[Cc]ite\w*|[A-Za-z]*cite\w*)\*?\s*(?:\[[^]]*\]\s*)*\{[^}]*\}|'
                       r'\\end\s*\{document\}')

    def visit(rel, stack):
        nonlocal wildcard, stopped
        if rel in stack:
            raise ValueError('Inclusión circular de archivos: ' + rel)
        if len(stack) > 100:
            raise ValueError('Demasiados niveles de archivos incluidos.')
        try:
            current = store.read(rel)
        except FileNotFoundError as error:
            raise ValueError('Falta un archivo incluido; no se puede organizar con seguridad: ' + rel) from error
        revisions[rel] = current['revision']
        text = source_text(current['content'])
        for match in token.finditer(text):
            if stopped:
                break
            command = re.match(r'\\([A-Za-z]+)', match[0])[1]
            if command == 'end':
                stopped = True
                break
            arg = re.search(r'\{([^}]*)\}\s*$', match[0])
            value = arg[1] if arg else match[0].split(None, 1)[1]
            if command in {'input', 'include'}:
                name = value.strip()
                if command == 'include' and includeonly is not None and name.removesuffix('.tex') not in includeonly:
                    continue
                child = root / name
                if not child.suffix:
                    child = child.with_suffix('.tex')
                child = store.path(child.as_posix()).relative_to(store.root).as_posix()
                visit(child, stack + [rel])
            elif command in {'bibliography', 'addbibresource'}:
                for name in value.split(','):
                    path = root / name.strip()
                    if not path.suffix:
                        path = path.with_suffix('.bib')
                    path = store.path(path.as_posix()).relative_to(store.root).as_posix()
                    if path not in bibs:
                        bibs.append(path)
            else:
                for key in value.split(','):
                    key = key.strip()
                    if key == '*' and command == 'nocite':
                        wildcard = True
                    elif key and key not in citations:
                        citations.append(key)
    visit(main, [])
    return dict(revisions=revisions, citations=citations, bibs=bibs, wildcard=wildcard)


def preview(store, main, path):
    graph = usage(store, main)
    if path not in graph['bibs']:
        raise ValueError('Selecciona un .bib utilizado por el documento principal.')
    documents = {p: store.read(p) for p in graph['bibs']}
    current = documents[path]
    entries = parse_bib(current['content'])
    all_entries = [e for doc in documents.values() for e in parse_bib(doc['content'])]
    all_keys = [e['key'] for e in all_entries]
    if len(set(all_keys)) != len(all_keys):
        raise ValueError('Hay claves duplicadas en las bibliografías activas. Corrígelas antes de organizar.')
    # Preserve semantics of macro declarations and cross-referenced entries.
    # These uncommon cases need manual review rather than a potentially unsafe permutation.
    if any(e['fields'].get('crossref') or e['fields'].get('xdata') for e in all_entries):
        raise ValueError('Hay entradas con crossref o xdata. Revisa sus dependencias antes de reorganizar.')
    if entries and re.search(r'@(?:string|preamble)\s*[({]', bib_comments(current['content'])[entries[0]['end']:], re.I):
        raise ValueError('Hay declaraciones @string o @preamble entre las entradas. Colócalas al principio antes de organizar.')
    original = [e['key'] for e in entries]
    known = set(original)
    used = [key for key in graph['citations'] if key in known]
    # nocite{*} follows the existing database order. Keep it unchanged so that
    # physically moving entries cannot change IEEEtran's wildcard numbering.
    if graph['wildcard']:
        used = original[:]
    unused = [key for key in original if key not in set(used)]
    ordered = used + unused
    after = current['content']
    if ordered != original:
        blocks = {}
        for i, entry in enumerate(entries):
            start = entries[i-1]['end'] if i else entry['start']
            blocks[entry['key']] = current['content'][start:entry['end']]
        after = current['content'][:entries[0]['start']]
        newline = '\r\n' if '\r\n' in after or '\r\n' in current['content'] else '\n'
        for key in ordered:
            block = blocks[key]
            if after and not after.endswith(('\n', '\r')) and not block.startswith(('\n', '\r')):
                after += newline * 2
            after += block
        after += current['content'][entries[-1]['end']:]
        reparsed = parse_bib(after)
        if [e['key'] for e in reparsed] != ordered or {e['key']: e['raw'] for e in reparsed} != {e['key']: e['raw'] for e in entries}:
            raise ValueError('No se pudo verificar la conservación de todas las entradas. No se guardó ningún cambio.')
    fingerprint = dict(main=main, path=path, sources=graph['revisions'], bibs={p: d['revision'] for p, d in documents.items()}, after=digest(after.encode()))
    return dict(path=path, revision=current['revision'], token=digest(json.dumps(fingerprint, sort_keys=True).encode()),
                before=current['content'], after=after, changed=after != current['content'],
                used=used, unused=unused, wildcard=graph['wildcard'],
                missing=[k for k in graph['citations'] if k not in set(all_keys)],
                sources=list(graph['revisions']),
                order=[dict(key=k, old=original.index(k)+1, new=i+1, used=k in set(used)) for i, k in enumerate(ordered)])


def organize(store, main, data):
    path, expected = data.get('bib_path'), data.get('token')
    if not isinstance(path, str) or not isinstance(expected, str):
        raise ValueError('Genera primero la vista previa de la bibliografía.')
    plan = preview(store, main, path)
    if plan['token'] != expected:
        raise ConflictError('El documento o su bibliografía cambió desde la vista previa. Revísala de nuevo antes de aplicar.')
    result = store.write(path, plan['after'], plan['revision'], reason='organizar bibliografía: citadas primero y sin citar al final')
    return dict(result, path=path, used=len(plan['used']), unused=len(plan['unused']))
