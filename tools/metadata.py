import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Rebuild SEO metadata for the production host: absolute self-canonical,
hreflang cluster from the files that actually exist, og:url, local og:image,
JSON-LD images/urls, no Shopify search action."""
import json, re
from urllib.parse import urlsplit, parse_qs, unquote
from lib import ROOT, SITE, PREFIXES, all_pages, locale_of_page, clean_url, page_file, hreflang_of, load, save

ASSET_DIRS = {d.name: d for d in (ROOT / 'cdn' / 'shop').iterdir() if d.is_dir()}
_index = {}

def _dir_index(dirname):
    """name stem -> list of (version, width, filename) for one cdn/shop/<dir>."""
    if dirname not in _index:
        idx = {}
        d = ASSET_DIRS.get(dirname)
        if d:
            for f in d.iterdir():
                m = re.match(r'^(?P<stem>.+?)\.(?:[a-z]+\d*\.)*?v(?P<v>\d+)(?:\.w(?P<w>\d+))?(?:\.[a-z]\w*)*\.(?P<ext>[A-Za-z0-9]+)$', f.name)
                if not m:
                    continue
                key = f"{m.group('stem')}.{m.group('ext')}"
                idx.setdefault(key, []).append((m.group('v'), int(m.group('w') or 0), f.name))
        _index[dirname] = idx
    return _index[dirname]

def local_asset(url, want=1200):
    """map a Shopify image URL (.../cdn/shop/<dir>/<name>?v=..&width=..) to a local absolute URL."""
    if not url or '/cdn/shop/' not in url:
        return None
    u = urlsplit(url if '//' in url else 'https:' + url)
    m = re.match(r'^/cdn/shop/([^/]+)/([^/]+)$', u.path)
    if not m:
        return None
    dirname, name = m.group(1), unquote(m.group(2))
    q = parse_qs(u.query)
    v = (q.get('v') or [None])[0]
    want = int((q.get('width') or [want])[0])
    cands = _dir_index(dirname).get(name, [])
    if v:
        cands = [c for c in cands if c[0] == v] or cands
    if not cands:
        return None
    ge = sorted([c for c in cands if c[1] >= want], key=lambda c: c[1])
    pick = ge[0] if ge else max(cands, key=lambda c: c[1])
    return f'{SITE}/cdn/shop/{dirname}/{pick[2]}'

def rewrite_jsonld(obj, page_url):
    if isinstance(obj, dict):
        obj.pop('potentialAction', None)
        for k, v in list(obj.items()):
            if isinstance(v, str):
                if '/cdn/shop/' in v:
                    la = local_asset(v, 1946)
                    if la: obj[k] = la
                elif v.startswith('https://heatica.com/') and k in ('url', '@id'):
                    obj[k] = re.sub(r'\.html(?=[?#]|$)', '', v)
            else:
                rewrite_jsonld(v, page_url)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and '/cdn/shop/' in v:
                la = local_asset(v, 1946)
                if la: obj[i] = la
            else:
                rewrite_jsonld(v, page_url)
    return obj

def first_gallery_image(soup, page):
    img = soup.select_one('.product__media img, .banner__media img, main img')
    if not img: return None
    src = img.get('src') or ''
    if src.startswith(('http', '//')): return None
    rel = (page.parent / src).resolve().relative_to(ROOT)
    return f'{SITE}/{rel.as_posix()}'

def process(page):
    prefix, sub = locale_of_page(page)
    soup = load(page)
    head = soup.head
    url = SITE + clean_url(prefix, sub)
    for l in head.find_all('link', rel='canonical'): l.decompose()
    head.append(soup.new_tag('link', rel='canonical', href=url))
    for l in head.find_all('link', rel='alternate'):
        if l.get('hreflang'): l.decompose()
    for p in PREFIXES:
        if page_file(p, sub).exists():
            head.append(soup.new_tag('link', rel='alternate', hreflang=hreflang_of(p), href=SITE + clean_url(p, sub)))
    if page_file('', sub).exists():
        head.append(soup.new_tag('link', rel='alternate', hreflang='x-default', href=SITE + clean_url('', sub)))
    og_img = None
    for m in head.find_all('meta'):
        k = m.get('property') or m.get('name') or ''
        if k == 'og:url':
            m['content'] = url
        elif k in ('og:image', 'og:image:secure_url', 'twitter:image'):
            la = local_asset(m.get('content', '')) if '/cdn/shop/' in m.get('content', '') else None
            if la is None and m.get('content', '').startswith(('http://', 'https://')) and 'heatica.com' in m['content']:
                la = first_gallery_image(soup, page)
            if la:
                m['content'] = la; og_img = la
    if og_img:
        for m in head.find_all('meta', property=re.compile(r'^og:image:(width|height)$')):
            m.decompose()
    for sc in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(sc.string or '')
        except Exception:
            continue
        sc.string = json.dumps(rewrite_jsonld(data, url), ensure_ascii=False)
    save(page, soup)

def run():
    pages = all_pages()
    for p in pages:
        process(p)
    print(f'metadata: canonical/hreflang/og/JSON-LD rebuilt on {len(pages)} pages')

if __name__ == '__main__':
    run()
