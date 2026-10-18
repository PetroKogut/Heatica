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

PAGE_URL_RE = re.compile(r'^https?://heatica\.com(?:/[a-z]{2}(?:-[a-z]{2})?)?(/(?:products|collections|pages)/[^/?#]+?)(?:\.html)?([?#].*)?$')

def localize_url(v, page_url, own_path):
    """a heatica.com page URL inside JSON-LD -> the same page in THIS locale (if it is this page)."""
    m = PAGE_URL_RE.match(v)
    if m and m.group(1) == own_path:
        return page_url + (m.group(2) or '')
    return re.sub(r'\.html(?=[?#]|$)', '', v)

def rewrite_jsonld(obj, page_url, own_path=None):
    if isinstance(obj, dict):
        obj.pop('potentialAction', None)
        if isinstance(obj.get('sameAs'), list):
            obj['sameAs'] = [s for s in obj['sameAs'] if isinstance(s, str) and s.strip()]
            if not obj['sameAs']: del obj['sameAs']
        for k, v in list(obj.items()):
            if isinstance(v, str):
                if '/cdn/shop/' in v:
                    la = local_asset(v, 1946)
                    if la: obj[k] = la
                elif 'heatica.com' in v and k in ('url', '@id', 'sameAs', 'item'):
                    obj[k] = localize_url(v, page_url, own_path)
            else:
                rewrite_jsonld(v, page_url, own_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and '/cdn/shop/' in v:
                la = local_asset(v, 1946)
                if la: obj[i] = la
            elif isinstance(v, str) and 'heatica.com' in v:
                obj[i] = localize_url(v, page_url, own_path)
            else:
                rewrite_jsonld(v, page_url, own_path)
    return obj

def image_dims(url):
    """(width, height) of a local asset URL, if Pillow is available."""
    try:
        from PIL import Image
        rel = url.replace(SITE + '/', '')
        with Image.open(ROOT / rel) as im:
            return im.size
    except Exception:
        return None

def usable_local_image(url):
    """the URL itself when it is a local asset big enough for a social preview."""
    if not url.startswith(SITE + '/'):
        return None
    rel = unquote(url[len(SITE) + 1:]).split('?')[0]
    if not (ROOT / rel).is_file():
        return None
    dims = image_dims(f'{SITE}/{rel}')
    if not dims or dims[0] < 600 or dims[1] < 315:
        return None
    return f'{SITE}/{rel}'

def first_gallery_image(soup, page, want=1200):
    """absolute URL of the page's lead image, preferring the smallest rendition >= want px."""
    img = soup.select_one('.product__media img, .banner__media img, main img')
    if not img: return None
    cands = []
    for ent in (img.get('srcset') or '').split(','):
        bits = ent.strip().split()
        if len(bits) == 2 and bits[1].endswith('w') and bits[1][:-1].isdigit():
            cands.append((int(bits[1][:-1]), bits[0]))
    src = img.get('src') or ''
    pick = None
    if cands:
        ge = sorted(c for c in cands if c[0] >= want)
        pick = (ge[0] if ge else max(cands))[1]
    else:
        pick = src
    if not pick or pick.startswith(('http', '//')): return None
    try:
        rel = (page.parent / unquote(pick)).resolve().relative_to(ROOT)
    except ValueError:
        return None
    dims = image_dims(f'{SITE}/{rel.as_posix()}')
    if dims and (dims[0] < 600 or dims[1] < 315):
        return None                       # tiny inline graphics are useless as social previews
    return f'{SITE}/{rel.as_posix()}'

_site_default = {}
def site_default_image():
    if 'v' not in _site_default:
        home = load(ROOT / 'index.html')
        _site_default['v'] = first_gallery_image(home, ROOT / 'index.html')
    return _site_default['v']

_home_desc = {}
def home_description(prefix):
    if prefix not in _home_desc:
        hp = page_file(prefix, '')
        d = load(hp).find('meta', attrs={'name': 'description'}) if hp.exists() else None
        _home_desc[prefix] = (d.get('content') or '').strip() if d else ''
    return _home_desc[prefix]

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
            c = m.get('content', '')
            la = local_asset(c) if '/cdn/shop/' in c else None
            if la is None and c.startswith(('http://', 'https://')) and 'heatica.com' in c:
                la = usable_local_image(c) or first_gallery_image(soup, page)
            if la:
                m['content'] = la; og_img = la
            else:
                m.decompose()            # tiny/unknown image: the site default is appended below
    if not og_img:
        fg = first_gallery_image(soup, page) or site_default_image()
        if fg:
            og_img = fg
            head.append(soup.new_tag('meta', property='og:image', content=fg))
            head.append(soup.new_tag('meta', property='og:image:secure_url', content=fg))
    for m in head.find_all('meta', property=re.compile(r'^og:image:(width|height)$')):
        m.decompose()
    if og_img:
        dims = image_dims(og_img)
        if dims:
            head.append(soup.new_tag('meta', property='og:image:width', content=str(dims[0])))
            head.append(soup.new_tag('meta', property='og:image:height', content=str(dims[1])))
        if not head.find('meta', attrs={'name': 'twitter:image'}):
            head.append(soup.new_tag('meta', attrs={'name': 'twitter:image', 'content': og_img}))
    for m in head.find_all('meta'):
        k = (m.get('name') or m.get('property') or '')
        if k in ('description', 'og:description', 'twitter:description') and m.get('content'):
            m['content'] = re.sub(r'\s+', ' ', m['content'].replace('&nbsp;', ' ').replace('\xa0', ' ')).strip()
    old_desc = head.find('meta', attrs={'name': 'description'})
    if old_desc is not None and re.match(r'^[^\s:]{3,15}:\s', old_desc.get('content') or '') and '€' in (old_desc.get('content') or ''):
        old_desc.decompose()          # placeholder generated from card text by an earlier build
    if not head.find('meta', attrs={'name': 'description'}):
        h1 = soup.select_one('main h1')
        h1t = re.sub(r'\s+', ' ', h1.get_text(' ', strip=True)) if h1 else ''
        h1t = re.sub(r'^[^:]{1,20}:\s*', '', h1t)            # drop the visually-hidden "Collection:" label
        site_desc = home_description(prefix)
        txt = f'{h1t} – {site_desc}' if h1t and site_desc else (h1t or site_desc)
        if txt:
            head.append(soup.new_tag('meta', attrs={'name': 'description', 'content': txt[:300]}))
    own_path = clean_url('', sub)
    for sc in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(sc.string or '')
        except Exception:
            continue
        sc.string = json.dumps(rewrite_jsonld(data, url, own_path), ensure_ascii=False)
    save(page, soup)

def run():
    pages = all_pages()
    for p in pages:
        process(p)
    print(f'metadata: canonical/hreflang/og/JSON-LD rebuilt on {len(pages)} pages')

if __name__ == '__main__':
    run()
