import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Rename crawled assets from 'name.ext@v=1&width=2' to 'name.v1.w2.ext' so that
static hosts infer the right Content-Type and URLs carry no '@'/'&', then rewrite
every reference in HTML and CSS."""
import html as H, json, re
from pathlib import Path
from lib import ROOT, DATA, all_pages

MAP_FILE = DATA / 'asset_renames.json'

def new_name(old):
    if '@' not in old:
        return old
    base, query = old.split('@', 1)
    stem, dot, ext = base.rpartition('.')
    if not dot:
        stem, ext = base, ''
    # wget -E appended .css/.js after the query for stylesheets/scripts
    if ext in ('css', 'js') and query.endswith('.' + ext):
        query = query[: -len(ext) - 1]
    parts = []
    for kv in query.split('&'):
        k, _, v = kv.partition('=')
        parts.append((k[:1] + re.sub(r'[^A-Za-z0-9]', '', v)) if v else re.sub(r'[^A-Za-z0-9]', '', k))
    return f"{stem}.{'.'.join(parts)}" + (f'.{ext}' if ext else '')

def build_map():
    m = {}
    for f in ROOT.glob('cdn/**/*'):
        if f.is_file() and '@' in f.name:
            m[f.name] = new_name(f.name)
    assert len(set(m.values())) == len(m), 'rename collision'
    return m

def run():
    m = build_map()
    if not m:
        print('rename: nothing to do'); return
    # 1. rename files
    for f in list(ROOT.glob('cdn/**/*')):
        if f.is_file() and f.name in m:
            f.rename(f.with_name(m[f.name]))
    # 2. rewrite references (raw and HTML-escaped forms) in html + css
    pairs = {}
    for old, new in m.items():
        pairs[old] = new
        pairs[H.escape(old, quote=False)] = new          # &amp; form
        pairs[old.replace('&', '%26')] = new             # percent-encoded form
    rx = re.compile('|'.join(re.escape(k) for k in sorted(pairs, key=len, reverse=True)))
    files = all_pages() + [p for p in ROOT.glob('cdn/**/*.css')] + [p for p in ROOT.glob('*.html') if p.name == '404.html']
    touched = 0
    for p in files:
        t = p.read_text(encoding='utf-8', errors='replace')
        t2 = rx.sub(lambda mm: pairs[mm.group(0)], t)
        if t2 != t:
            p.write_text(t2, encoding='utf-8'); touched += 1
    json.dump(m, open(MAP_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(f'rename: {len(m)} files renamed, references rewritten in {touched} files; map saved to {MAP_FILE.relative_to(ROOT)}')

if __name__ == '__main__':
    run()
