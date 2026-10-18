"""Shared helpers for the Heatica static-mirror build."""
import json, re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'tools' / 'data'
SITE = 'https://heatica.com'
NBSP = ' '

# language source locales (prefix '' = English, default market)
LANG_PREFIXES = ['', 'pl', 'uk', 'cs', 'sk', 'hu', 'bg']
# country variants: prefix -> (language prefix it is cloned from, ISO country)
COUNTRY_VARIANTS = {
    'en-at': ('', 'AT'), 'uk-at': ('uk', 'AT'),
    'en-fr': ('', 'FR'), 'uk-fr': ('uk', 'FR'),
    'en-nl': ('', 'NL'), 'uk-nl': ('uk', 'NL'),
    'en-it': ('', 'IT'), 'uk-it': ('uk', 'IT'),
    'pl-pl': ('pl', 'PL'), 'en-pl': ('', 'PL'), 'uk-pl': ('uk', 'PL'),
    'en-dk': ('', 'DK'), 'uk-dk': ('uk', 'DK'),
    'en-bg': ('', 'BG'), 'uk-bg': ('uk', 'BG'), 'bg-bg': ('bg', 'BG'),
    'en-hr': ('', 'HR'), 'uk-hr': ('uk', 'HR'),
    'en-hu': ('', 'HU'), 'uk-hu': ('uk', 'HU'), 'hu-hu': ('hu', 'HU'),
    'en-ie': ('', 'IE'), 'uk-ie': ('uk', 'IE'),
    'en-lt': ('', 'LT'), 'uk-lt': ('uk', 'LT'),
    'en-si': ('', 'SI'), 'uk-si': ('uk', 'SI'),
    'en-sk': ('', 'SK'), 'uk-sk': ('uk', 'SK'), 'sk-sk': ('sk', 'SK'),
}
PREFIXES = LANG_PREFIXES + list(COUNTRY_VARIANTS)
LANG_NAMES = {'': 'English', 'pl': 'Polski', 'uk': 'Українська', 'cs': 'Čeština',
              'sk': 'Slovenčina', 'hu': 'Magyar', 'bg': 'Български'}

def lang_of(prefix):
    if prefix in COUNTRY_VARIANTS:
        return lang_of(COUNTRY_VARIANTS[prefix][0])
    return prefix or 'en'

def hreflang_of(prefix):
    if prefix in COUNTRY_VARIANTS:
        return f'{lang_of(prefix)}-{COUNTRY_VARIANTS[prefix][1]}'
    return prefix or 'en'

def locale_of_page(page):
    """(prefix, sub) of a page; sub '' means the locale homepage."""
    rel = Path(page).resolve().relative_to(ROOT)
    parts = rel.parts
    if len(parts) == 1:
        stem = Path(page).stem
        return (stem if stem in PREFIXES else ''), ''
    if parts[0] in PREFIXES:
        return parts[0], '/'.join(parts[1:])
    return '', '/'.join(parts)

def clean_url(prefix, sub):
    if not sub:
        return f'/{prefix}' if prefix else '/'
    path = sub[:-5] if sub.endswith('.html') else sub
    return f'/{prefix}/{path}' if prefix else f'/{path}'

def page_file(prefix, sub):
    if not sub:
        return ROOT / (f'{prefix}.html' if prefix else 'index.html')
    return ROOT / prefix / sub if prefix else ROOT / sub

def all_pages():
    return sorted(p for p in ROOT.rglob('*.html')
                  if '.git' not in p.parts and 'tools' not in p.parts and 'worker' not in p.parts
                  and p.name != '404.html')

def page_set(prefix=''):
    base = ROOT / prefix if prefix else ROOT
    subs = []
    for d in ('products', 'collections', 'pages'):
        subs += [f'{d}/{p.name}' for p in sorted((base / d).glob('*.html'))]
    return subs

def rel_root(page):
    rel = Path(page).resolve().relative_to(ROOT)
    return '../' * (len(rel.parts) - 1) or './'

def load(page):
    return BeautifulSoup(Path(page).read_text(encoding='utf-8', errors='replace'), 'html.parser')

def save(page, soup_or_text):
    Path(page).write_text(str(soup_or_text), encoding='utf-8')

def set_cfg(text, **fields):
    def fix(m):
        d = json.loads(m.group(2)); d.update(fields)
        return m.group(1) + json.dumps(d, ensure_ascii=False) + m.group(3)
    return re.sub(r'(<script id="mirror-locale-cfg" type="application/json">)(.*?)(</script>)', fix, text, flags=re.S)

def load_segments(lang):
    """EN -> lang text map built from every tools/data/segments*_en.json that has a
    matching *_<lang>.json (currently the legal-page segments)."""
    tmap = {}
    for en in DATA.glob('segments*_en.json'):
        tr = DATA / en.name.replace('_en.json', f'_{lang}.json')
        if tr.exists():
            e = json.load(open(en, encoding='utf-8')); t = json.load(open(tr, encoding='utf-8'))
            tmap.update({e[k]: t[k] for k in e if k in t and t[k].strip()})
    return tmap
