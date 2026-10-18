import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Create the pages the crawl missed (legal pages, chemical starter kit, the
'spa with massage jets' collection) for the source locales from existing templates."""
import json, re
from bs4 import BeautifulSoup
from lib import ROOT, DATA, page_file, load, save, load_segments
from strings import s, ui_tmap
from clone_locale import translate

EXTRA = json.load(open(DATA / 'extra_pages_en.json', encoding='utf-8'))
LEGAL_KEYS = ['privacy-policy', 'terms-of-service', 'cookie-policy', 'acceptable-use-policy', 'chemical-starter-kit']
MASSAGE = ['drop-x', 'drop-vuolle', 'drop-vuolle-compact', 'drop-s']
SOURCES = {'en': '', 'pl': 'pl', 'uk': 'uk', 'cs': 'cs', 'sk': 'sk', 'hu': 'hu', 'bg': 'bg'}

def build_page(prefix, lang, key, tmap):
    data = EXTRA[key]
    tpl = page_file(prefix, 'pages/maintenance.html')
    soup = load(tpl)
    h1 = soup.select_one('main h1')
    title = s(key, lang)
    h1.string = title
    rte = soup.select_one('main .rte')
    frag = BeautifulSoup(data['html'], 'html.parser')
    translate(frag, tmap)
    rte.clear()
    for child in list(frag.children):
        rte.append(child)
    soup.title.string = f'{title} – Heatica'
    desc = tmap.get(data['desc'], data['desc']) if data['desc'] else re.sub(r'\s+', ' ', rte.get_text(' ', strip=True))[:155]
    for m in soup.find_all('meta'):
        k = (m.get('name') or m.get('property') or '')
        if k in ('description', 'og:description', 'twitter:description'): m['content'] = desc
        if k in ('og:title', 'twitter:title'): m['content'] = title
    out = page_file(prefix, f'pages/{key}.html')
    save(out, soup)
    return out

def build_collection(prefix, lang):
    tpl = page_file(prefix, 'collections/drop-spa.html')
    soup = load(tpl)
    title, desc = s('collection_massage_title', lang), s('collection_massage_desc', lang)
    h1 = soup.select_one('.collection-hero__title, main h1')
    if h1:
        texts = [t for t in h1.find_all(string=True) if t.strip()]
        texts[-1].replace_with(title)
    d = soup.select_one('.collection-hero__description')
    if d:
        d.clear(); p = soup.new_tag('p'); p.string = desc; d.append(p)
    else:
        wrapper = soup.select_one('.collection-hero__text-wrapper')
        if wrapper:
            dd = soup.new_tag('div', attrs={'class': 'collection-hero__description rte'}); p = soup.new_tag('p'); p.string = desc; dd.append(p); wrapper.append(dd)
    grid = soup.select_one('#ProductGridContainer ul')
    for li in list(grid.select('li.grid__item')):
        a = li.select_one('a[href*="products/"]')
        handle = re.search(r'products/([a-z0-9-]+)', a['href']).group(1) if a else ''
        if handle not in MASSAGE:
            li.decompose()
    for i, li in enumerate(grid.select('li.grid__item'), 1):
        li['style'] = f'--animation-order: {i};'
    soup.title.string = f'{title} – Heatica'
    for m in soup.find_all('meta'):
        k = (m.get('name') or m.get('property') or '')
        if k in ('description', 'og:description', 'twitter:description'): m['content'] = desc
        if k in ('og:title', 'twitter:title'): m['content'] = title
    out = page_file(prefix, 'collections/spa-with-massage-jets.html')
    save(out, soup)
    return out

def run():
    for lang, prefix in SOURCES.items():
        tmap = load_segments(lang) if lang != 'en' else {}
        tmap.update(ui_tmap(lang) if lang != 'en' else {})
        made = [build_page(prefix, lang, k, tmap).relative_to(ROOT) for k in LEGAL_KEYS]
        made.append(build_collection(prefix, lang).relative_to(ROOT))
        print(f'{lang or "en"}: ' + ', '.join(str(m) for m in made))

if __name__ == '__main__':
    run()
