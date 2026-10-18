import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Verify every internal reference resolves to a file (extension-less page links
resolve to <path>.html, locale homepages to <prefix>.html)."""
import html as H, re
from urllib.parse import unquote
from lib import ROOT, all_pages

def resolve(page, u):
    path = unquote(u.split('#')[0].split('?')[0])
    if not path: return True
    if path.startswith('/'):
        base = ROOT / path.lstrip('/')
    else:
        base = page.parent / path
    cands = [base]
    if path.endswith('/'):
        cands += [base / 'index.html', base.with_name(base.name + '.html') if base.name else base]
    else:
        cands += [base.with_name(base.name + '.html'), base / 'index.html']
    return any(c.exists() for c in cands)

def run():
    broken = {}
    pages = all_pages() + [ROOT / '404.html']
    for p in pages:
        t = p.read_text(encoding='utf-8', errors='replace')
        refs = re.findall(r'(?:href|src|action|data-src|poster)="([^"]+)"', t)
        for ss in re.findall(r'srcset="([^"]+)"', t):
            refs += [e.strip().split(' ')[0] for e in H.unescape(ss).split(',') if e.strip()]
        for raw in refs:
            u = H.unescape(raw).strip()
            if not u or u.startswith(('http', '//', '#', 'mailto:', 'tel:', 'data:', 'javascript:')): continue
            if u in ('/contact',): continue
            if not resolve(p, u):
                broken.setdefault(u[:100], set()).add(str(p.relative_to(ROOT)))
    print(f'links: {len(broken)} broken targets' + ('' if not broken else ':'))
    for u, ps in sorted(broken.items(), key=lambda x: -len(x[1]))[:15]:
        print(f'  {len(ps):4} pages -> {u}')
    return len(broken)

if __name__ == '__main__':
    raise SystemExit(1 if run() else 0)
