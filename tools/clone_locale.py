import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Clone the English root locale into language locales (with translation) and
language locales into country variants (same page set, country selected)."""
import json, re
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Comment, Doctype, ProcessingInstruction
from lib import ROOT, NBSP, PREFIXES, LANG_PREFIXES, LANG_NAMES, page_set, set_cfg, load_segments, clean_url
from strings import ui_tmap

MONEY_RE = re.compile(r'(<span class="money">)€([\d,]+)\.(\d{2})( EUR</span>)')
LOCALE_STEMS = [p for p in PREFIXES if p]

def eu_money(text):
    def conv(m):
        n = f'{int(m.group(2).replace(",", "")):,}'.replace(',', NBSP)
        return f'{m.group(1)}€{n},{m.group(3)}{m.group(4)}'
    return MONEY_RE.sub(conv, text)

def set_fmt_eu(text):
    def fix(m):
        d = json.loads(m.group(2)); d['fmt']['th'] = NBSP; d['fmt']['ds'] = ','
        return m.group(1) + json.dumps(d, ensure_ascii=False) + m.group(3)
    return re.sub(r'(<script id="mirror-variant-data" type="application/json">)(.*?)(</script>)', fix, text, flags=re.S)

def fix_path(v, is_home, lang, tag_name):
    """root-locale page -> {lang}/ page: deepen asset/locale refs, keep locale-internal refs."""
    if not v or v.startswith(('http', '//', '#', 'mailto:', 'tel:', 'data:', 'javascript:', '/')):
        return v
    if v.startswith('./'):
        v = v[2:] or 'index.html'
    if is_home:
        if v.startswith(('products/', 'collections/', 'pages/')):
            return f'{lang}/{v}'
        if v == 'index.html' or v.startswith(('index.html#', 'index.html?')) or v in ('./', '.'):
            return v if tag_name == 'link' else v.replace('index.html', f'{lang}.html', 1).replace('./', f'{lang}.html', 1) if v != '.' else f'{lang}.html'
        return v
    if v.startswith('../'):
        rest = v[3:]
        if rest.startswith('cdn/'):
            return '../../' + rest
        first = rest.split('/')[0]
        stem = re.split(r'[.#?]', first)[0]
        if first.startswith('index.html') or rest in ('', './'):
            return '../../' + rest if tag_name == 'link' else f'../../{lang}.html'
        if stem in LOCALE_STEMS:
            return '../../' + rest
        return v
    return v

def fix_links(soup, is_home, lang):
    for attr in ('href', 'src', 'action', 'data-src', 'poster'):
        for tag in soup.find_all(attrs={attr: True}):
            tag[attr] = fix_path(tag[attr], is_home, lang, tag.name)
    for tag in soup.find_all(attrs={'srcset': True}):
        ents = []
        for ent in tag['srcset'].split(','):
            e = ent.strip()
            if not e: continue
            bits = e.split(' ', 1); bits[0] = fix_path(bits[0], is_home, lang, tag.name)
            ents.append(' '.join(bits))
        tag['srcset'] = ', '.join(ents)

def retarget_locale_links(soup, src, dst, is_home):
    """language-locale page -> country variant: links that name the source locale
    (its homepage or its directory) must name the variant instead."""
    rx_dir = re.compile(rf'^((?:\.\./)*|\./)?{re.escape(src)}/(.*)$')
    rx_home = re.compile(rf'^((?:\.\./)*|\./)?{re.escape(src)}(\.html)?([?#].*)?$')
    for attr in ('href', 'src', 'action', 'data-src'):
        for tag in soup.find_all(attrs={attr: True}):
            v = tag[attr]
            if not v or v.startswith(('http', '//', '#', 'mailto:', 'tel:', 'data:', 'javascript:', '/')):
                continue
            m = rx_dir.match(v)
            if m:
                tag[attr] = f"{m.group(1) or ''}{dst}/{m.group(2)}"; continue
            m = rx_home.match(v)
            if m:
                tag[attr] = f"{m.group(1) or ''}{dst}{m.group(2) or ''}{m.group(3) or ''}"

def select_lang(soup, lang, native, prev='en', prev_label='English'):
    for a in soup.select(f'a[data-value="{prev}"][hreflang]'):
        a.attrs.pop('aria-current', None)
        sp = a.find('span')
        if sp and 'visibility-hidden' not in (sp.get('class') or []):
            sp['class'] = (sp.get('class') or []) + ['visibility-hidden']
    for a in soup.select(f'a[data-value="{lang}"][hreflang]'):
        a['aria-current'] = 'true'
        sp = a.find('span')
        if sp and 'visibility-hidden' in (sp.get('class') or []):
            sp['class'] = [c for c in sp['class'] if c != 'visibility-hidden']
    for form in soup.find_all('localization-form'):
        if not form.select_one('a[hreflang]'): continue
        for btn in form.select('button.disclosure__button span'):
            if btn.get_text(strip=True) == prev_label:
                btn.string = native

def first_text(a):
    return next((s.strip() for s in a.find_all(string=True) if s.strip()), None)

def select_country(soup, cc, prev_cc='DE'):
    src_disp = dst_disp = None
    for a in soup.select(f'localization-form a[data-value="{prev_cc}"]'):
        src_disp = src_disp or first_text(a)
        a.attrs.pop('aria-current', None)
        sp = a.find('span')
        if sp and 'visibility-hidden' not in (sp.get('class') or []):
            sp['class'] = (sp.get('class') or []) + ['visibility-hidden']
    for a in soup.select(f'localization-form a[data-value="{cc}"]'):
        dst_disp = dst_disp or first_text(a)
        a['aria-current'] = 'true'
        sp = a.find('span')
        if sp and 'visibility-hidden' in (sp.get('class') or []):
            sp['class'] = [c for c in sp['class'] if c != 'visibility-hidden']
    if src_disp and dst_disp:
        for form in soup.find_all('localization-form'):
            if form.select_one('a[hreflang]'): continue
            for span in form.select('button.disclosure__button span'):
                txt = span.get_text()
                if src_disp in txt:
                    span.string = txt.replace(src_disp, dst_disp)

def translate(soup, tmap):
    n = 0
    for node in soup.find_all(string=True):
        if (not isinstance(node, NavigableString) or isinstance(node, (Comment, Doctype, ProcessingInstruction))
                or node.parent.name in ('script', 'style')):
            continue
        key = re.sub(r'\s+', ' ', str(node)).strip()
        if key and key in tmap:
            raw = str(node)
            node.replace_with(raw.replace(node.strip(), tmap[key]) if node.strip() in raw else tmap[key]); n += 1
    for m in soup.find_all('meta'):
        k = (m.get('name') or m.get('property') or '')
        if k in ('description', 'og:description', 'twitter:description', 'og:title', 'twitter:title'):
            key = re.sub(r'\s+', ' ', m.get('content') or '').strip()
            if key in tmap: m['content'] = tmap[key]; n += 1
    for attr in ('alt', 'aria-label', 'placeholder', 'title', 'data-success', 'data-fallback', 'data-quote', 'data-heading'):
        for el in soup.find_all(attrs={attr: True}):
            key = re.sub(r'\s+', ' ', el[attr]).strip()
            if key in tmap: el[attr] = tmap[key]; n += 1
    if soup.title and soup.title.string:
        key = re.sub(r'\s+', ' ', soup.title.get_text()).strip()
        if key in tmap: soup.title.string = tmap[key]; n += 1
    return n

def full_tmap(lang):
    tmap = load_segments(lang)
    tmap.update(ui_tmap(lang))
    return tmap

def build_language(lang, native=None):
    native = native or LANG_NAMES[lang]
    tmap = full_tmap(lang)
    total = 0
    pages = [''] + page_set('')
    for rel in pages:
        is_home = rel == ''
        src = ROOT / ('index.html' if is_home else rel)
        dst = ROOT / (f'{lang}.html' if is_home else f'{lang}/{rel}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        soup = BeautifulSoup(src.read_text(encoding='utf-8'), 'html.parser')
        if soup.html: soup.html['lang'] = lang
        total += translate(soup, tmap)
        fix_links(soup, is_home, lang)
        select_lang(soup, lang, native)
        out = str(soup)
        out = set_cfg(out, cur=lang, sub=rel, root='./' if is_home else '../../')
        out = eu_money(out); out = set_fmt_eu(out)
        dst.write_text(out, encoding='utf-8')
    print(f'{lang}: {len(pages)} pages, {total} strings translated')

def build_country(src_prefix, dst_prefix, cc, eu_format=None):
    if eu_format is None:
        eu_format = src_prefix != ''   # English keeps 1,850.00; other languages 1 850,00
    pages = [''] + page_set(src_prefix)
    for rel in pages:
        is_home = rel == ''
        if src_prefix == '':
            src = ROOT / ('index.html' if is_home else rel)
        else:
            src = ROOT / (f'{src_prefix}.html' if is_home else f'{src_prefix}/{rel}')
        dst = ROOT / (f'{dst_prefix}.html' if is_home else f'{dst_prefix}/{rel}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        soup = BeautifulSoup(src.read_text(encoding='utf-8'), 'html.parser')
        if src_prefix == '':
            fix_links(soup, is_home, dst_prefix)
        else:
            retarget_locale_links(soup, src_prefix, dst_prefix, is_home)
        select_country(soup, cc)
        own = clean_url(dst_prefix, re.sub(r'\.html$', '', rel))
        pg = soup.find('input', attrs={'name': 'page'})
        if pg is not None:
            pg['value'] = own
        for rt in soup.find_all('input', attrs={'name': 'return_to'}):
            rt['value'] = own
        out = str(soup)
        if src_prefix == '' and not is_home:
            # the variant JSON carries relative photo paths; the clone sits one directory deeper
            out = re.sub(r'(<script id="mirror-variant-data"[^>]*>)(.*?)(</script>)',
                         lambda m: m.group(1) + m.group(2).replace('"img": "../cdn/', '"img": "../../cdn/') + m.group(3), out, flags=re.S)
        out = set_cfg(out, cur=dst_prefix, sub=rel, root='./' if is_home else '../../')
        if eu_format:
            out = eu_money(out); out = set_fmt_eu(out)
        dst.write_text(out, encoding='utf-8')
    print(f'{dst_prefix}: {len(pages)} pages (from {src_prefix or "en"}, {cc})')
