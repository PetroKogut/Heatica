import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Rebuild responsive srcset/sizes for images whose srcset was lost, from the
width renditions that exist on disk next to the src file."""
import html as H, re
from urllib.parse import unquote
from lib import all_pages, load, save

RENDITION_RE = re.compile(r'^(?P<base>.+?)(?:&width=(?P<w>\d+))?$')

def renditions(dir_, src_name):
    """all files that are width renditions of the same image as src_name."""
    m = re.match(r'^(.+?@v=\d+)(?:&width=\d+)?$', src_name) or re.match(r'^(.+?\.[A-Za-z0-9]+)$', src_name)
    if not m: return []
    base = m.group(1)
    out = []
    for f in dir_.iterdir():
        n = f.name
        if n == base:
            continue
        mm = re.match(re.escape(base) + r'&width=(\d+)$', n)
        if mm:
            out.append((int(mm.group(1)), n))
    return sorted(out)

def sizes_for(img):
    anc = [c for p in img.parents for c in (p.get('class') or [])]
    if any(c.startswith('product__media') for c in anc):
        return '(min-width: 1200px) 715px, (min-width: 990px) calc(65.0vw - 10rem), (min-width: 750px) calc((100vw - 11.5rem) / 2), calc(100vw / 1 - 4rem)'
    if any(c.startswith('card') for c in anc):
        return '(min-width: 990px) calc((100vw - 130px) / 4), (min-width: 750px) calc((100vw - 120px) / 3), calc((100vw - 35px) / 2)'
    if any(c.startswith('banner') for c in anc) or any(c == 'image-with-text__media' for c in anc):
        return '100vw'
    return '(min-width: 990px) 60vw, 100vw'

def fix_page(page):
    soup = load(page); n = 0
    for img in soup.find_all('img', src=True):
        if img.get('srcset'):
            continue
        src = H.unescape(img['src'])
        if src.startswith(('http', '//', 'data:')) or '/cdn/' not in src and not src.startswith('cdn/'):
            continue
        path = page.parent / unquote(src)
        if not path.exists():
            continue
        rends = renditions(path.parent, path.name)
        if len(rends) < 2:
            continue
        prefix = src.rsplit('/', 1)[0] + '/'
        img['srcset'] = ', '.join(f'{prefix}{name} {w}w' for w, name in rends)
        if not img.get('sizes'):
            img['sizes'] = sizes_for(img)
        n += 1
    if n:
        save(page, soup)
    return n

def run():
    total = pages = 0
    for page in all_pages():
        k = fix_page(page)
        if k: pages += 1; total += k
    print(f'srcset: rebuilt on {total} images in {pages} pages')

if __name__ == '__main__':
    run()
