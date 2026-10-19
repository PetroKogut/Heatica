import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Content-level fixes applied to source locales (root EN, pl, uk); language and
country locales are regenerated from them. Every step is idempotent."""
import json, re, sys
from urllib.parse import quote
from bs4 import BeautifulSoup, NavigableString, Comment
from lib import ROOT, DATA, NBSP, all_pages, locale_of_page, lang_of, rel_root, load, save, clean_url, set_cfg
from strings import s

SOCIAL_HTML = (DATA / 'social.html').read_text(encoding='utf-8')
LEGAL = ['privacy-policy', 'terms-of-service', 'cookie-policy', 'acceptable-use-policy']
DROP_SCRIPTS = ('product-info.js', 'product-form.js', 'search-form.js', 'predictive-search.js',
                'quick-add.js', 'quick-order-list.js', 'cart.js', 'cart-notification.js', 'cart-drawer.js')
A11Y = {
    'en': ('Link copied to clipboard', '[count] countries/regions found'),
    'pl': ('Link skopiowany do schowka', 'Znaleziono krajów/regionów: [count]'),
    'uk': ('Посилання скопійовано', 'Знайдено країн/регіонів: [count]'),
    'cs': ('Odkaz zkopírován do schránky', 'Nalezeno zemí/oblastí: [count]'),
    'sk': ('Odkaz skopírovaný do schránky', 'Nájdených krajín/regiónov: [count]'),
    'hu': ('A link a vágólapra másolva', '[count] ország/régió található'),
    'bg': ('Връзката е копирана', 'Намерени държави/региони: [count]'),
}

def shim_js(lang):
    share, count = A11Y.get(lang, A11Y['en'])
    return ("window.shopUrl=location.origin;"
            "window.accessibilityStrings=window.accessibilityStrings||{imageAvailable:'Image {{ index }} is now available in gallery view',"
            f"shareSuccess:{json.dumps(share, ensure_ascii=False)},pauseSlideshow:'Pause slideshow',playSlideshow:'Play slideshow',"
            f"countrySelectorSearchCount:{json.dumps(count, ensure_ascii=False)}}};"
            "window.variantStrings=window.variantStrings||{addToCart:'',soldOut:'Sold out',unavailable:'Unavailable',unavailable_with_option:'[value] - Unavailable'};"
            "window.quickOrderListStrings=window.quickOrderListStrings||{};")

CONTACT_JS = r"""(function(){var f=document.getElementById('ContactForm');if(!f)return;
var ok=f.getAttribute('data-success'),fb=f.getAttribute('data-fallback'),to=f.getAttribute('data-mailto'),qt=f.getAttribute('data-quote');
function banner(text,good){var d=document.createElement('div');d.className='form__message mirror-form-message';d.setAttribute('role','status');d.setAttribute('tabindex','-1');
d.style.cssText='margin:0 0 2rem;padding:1.2rem 1.6rem;border:0.1rem solid '+(good?'#1a7f37':'#b3261e')+';border-radius:0.4rem;font-size:1.5rem;line-height:1.5';d.textContent=text;f.parentNode.insertBefore(d,f);d.focus();return d;}
var q=new URLSearchParams(location.search);
if(q.get('contact_posted')==='true'){banner(ok,true);f.style.display='none';}else if(q.get('contact_error')){banner(fb,false);}
var p=q.get('product');var c=f.querySelector('[name="contact[Comment]"]');
if(p&&c&&!c.value){c.value=qt.replace('{product}',p)+'\n';var lbl=c.parentNode.querySelector('label');if(lbl){lbl.classList.add('field__label--filled');}}
f.addEventListener('submit',function(e){e.preventDefault();
var old=f.parentNode.querySelector('.mirror-form-message');if(old)old.remove();
var fd=new FormData(f);var btn=f.querySelector('[type=submit]');if(btn)btn.disabled=true;
fetch(f.action,{method:'POST',body:fd,headers:{'Accept':'application/json'}}).then(function(r){return r.ok?r.json():Promise.reject(r);})
.then(function(){f.style.display='none';banner(ok,true);})
.catch(function(){if(btn)btn.disabled=false;banner(fb,false);
var cm=fd.get('contact[Comment]')||'';var subj=encodeURIComponent((cm.split('\n')[0]||'Heatica').slice(0,90));
var body=encodeURIComponent('Name: '+(fd.get('contact[Name]')||'')+'\nEmail: '+(fd.get('contact[email]')||'')+'\nPhone: '+(fd.get('contact[Phone number]')||'')+'\n\n'+cm);
window.location.href='mailto:'+to+'?subject='+subj+'&body='+body;});});})();"""

def locale_dir_href(page, prefix, sub):
    """relative href from `page` to `sub` (e.g. 'pages/contact-us.html') of the SAME locale,
    expressed locale-internally so that cloned country variants keep pointing inside themselves."""
    _, page_sub = locale_of_page(page)
    if not page_sub:                       # locale homepage sits at the repo root
        return (prefix + '/' if prefix else '') + sub
    depth = len(page_sub.split('/')) - 1
    return '../' * depth + sub

def strip_theme_scripts(soup):
    n = 0
    for sc in soup.find_all('script', src=True):
        if any(x in sc['src'] for x in DROP_SCRIPTS):
            sc.decompose(); n += 1
    return n

def ensure_shim(soup, lang):
    old = soup.find('script', id='mirror-shim')
    if old: old.decompose()
    tag = soup.new_tag('script', id='mirror-shim'); tag.string = shim_js(lang)
    head = soup.head or soup
    first_script = head.find('script')
    (first_script.insert_before(tag) if first_script else head.append(tag))

def remove_facets(soup):
    n = 0
    for el in soup.select('.facets-container, facet-filters-form, .facets-wrapper'):
        el.decompose(); n += 1
    return n

def remove_atom(soup):
    n = 0
    for l in soup.find_all('link', attrs={'type': 'application/atom+xml'}):
        l.decompose(); n += 1
    return n

def fix_currency_labels(soup):
    n = 0
    for form in soup.find_all('localization-form'):
        for f in form.find_all('form'):
            f['action'] = '/localization'   # no-JS fallback handled by the Worker
        for node in form.find_all(string=re.compile(r'PLN')):
            if isinstance(node, Comment): continue
            node.replace_with(re.sub(r'(PLN|EUR)(\s+)zł', r'EUR\2€', str(node)).replace('PLN', 'EUR')); n += 1
    return n

DEFAULT_COUNTRY = 'PL'   # the shop is in Krakow; the crawl's primary market was Germany

def default_country(soup):
    """source locales (no country in the URL) present Poland as the selected country."""
    from clone_locale import select_country
    select_country(soup, DEFAULT_COUNTRY)

def youtube_privacy(soup):
    n = 0
    for fr in soup.find_all('iframe', src=re.compile(r'youtube\.com/embed')):
        fr['src'] = fr['src'].replace('www.youtube.com/embed', 'www.youtube-nocookie.com/embed').replace('youtube.com/embed', 'www.youtube-nocookie.com/embed')
        fr['loading'] = 'lazy'; n += 1
    return n

def footer_blocks(soup, page, prefix, lang):
    footer = soup.find('footer')
    if not footer: return 0
    top = footer.select_one('.footer__content-top')
    if top is None: return 0
    old = top.select_one('[data-mirror-footer]')
    if old: old.decompose()
    wrap = soup.new_tag('div', attrs={'class': 'footer__blocks-wrapper grid grid--1-col grid--2-col grid--4-col-tablet scroll-trigger animate--slide-in', 'data-mirror-footer': ''})
    # legal menu
    block = soup.new_tag('div', attrs={'class': 'footer-block grid__item footer-block--menu'})
    h = soup.new_tag('h2', attrs={'class': 'footer-block__heading inline-richtext'}); h.string = s('legal_heading', lang); block.append(h)
    ul = soup.new_tag('ul', attrs={'class': 'footer-block__details-content list-unstyled'})
    for key in LEGAL:
        li = soup.new_tag('li')
        a = soup.new_tag('a', attrs={'class': 'link link--text list-menu__item list-menu__item--link', 'href': locale_dir_href(page, prefix, f'pages/{key}.html')})
        a.string = s(key, lang); li.append(a); ul.append(li)
    block.append(ul); wrap.append(block)
    # social
    sb = soup.new_tag('div', attrs={'class': 'footer-block grid__item footer-block--social'})
    sb.append(BeautifulSoup(SOCIAL_HTML, 'html.parser'))
    wrap.append(sb)
    top.append(wrap)
    return 1

def cta_home(soup, page, prefix, lang):
    n = 0
    for a in soup.select('.banner__buttons a.button--secondary'):
        href = a.get('href', '')
        if 'products/' not in href and not a.has_attr('data-mirror-cta'): continue
        box = a.find_parent(class_='banner__box')
        heading = box.select_one('.banner__heading') if box else None
        title = heading.get_text(' ', strip=True) if heading else ''
        a.string = s('quote_cta', lang)
        a['href'] = locale_dir_href(page, prefix, 'pages/contact-us.html') + '?product=' + quote(title)
        a['data-mirror-cta'] = ''
        n += 1
    return n

def cta_product(soup, page, prefix, lang):
    info = soup.select_one('.product__info-container')
    if info is None: return 0
    old = info.select_one('[data-mirror-cta]')
    if old: old.decompose()
    title_el = soup.select_one('.product__title h1, .product__title h2, h1.product__title')
    title = title_el.get_text(' ', strip=True) if title_el else ''
    div = soup.new_tag('div', attrs={'class': 'product-form__buttons', 'data-mirror-cta': ''})
    a = soup.new_tag('a', attrs={'class': 'button button--full-width button--primary',
                                 'href': locale_dir_href(page, prefix, 'pages/contact-us.html') + '?product=' + quote(title)})
    a.string = s('quote_cta', lang); div.append(a)
    anchor = info.select_one('variant-selects') or info.select_one('[id^="price-"]')
    if anchor is None: return 0
    # the empty div right after variant-selects is where Shopify's buy form lived
    nxt = anchor.find_next_sibling('div')
    if nxt is not None and not nxt.get_text(strip=True) and not nxt.find(True):
        nxt.replace_with(div)
    else:
        anchor.insert_after(div)
    return 1

def collection_cards(prefix):
    """handle -> (card li html, collections it belongs to) for one locale."""
    base = ROOT / prefix if prefix else ROOT
    cards, membership = {}, {}
    for coll in sorted((base / 'collections').glob('*.html')):
        soup = load(coll)
        for li in soup.select('li.grid__item'):
            a = li.select_one('a[href*="products/"]')
            if not a: continue
            m = re.search(r'products/([a-z0-9-]+)', a['href'])
            if not m: continue
            handle = m.group(1)
            cards.setdefault(handle, str(li))
            membership.setdefault(handle, []).append(coll.stem)
    return cards, membership

def related_products(soup, page, prefix, lang, cards, membership):
    el = soup.find('product-recommendations') or soup.select_one('[data-mirror-related]')
    if el is None: return 0
    handle = page.stem
    my = membership.get(handle, [])
    order = []
    for h, cols in membership.items():
        if h == handle: continue
        score = 0 if any(c in my and c != 'spa-with-massage-jets' for c in cols) else 1
        order.append((score, list(membership).index(h), h))
    picks = [h for _, _, h in sorted(order)][:4]
    if not picks: return 0
    el.name = 'div'
    for attr in ('data-url', 'data-section-id', 'data-product-id'):
        el.attrs.pop(attr, None)
    el['data-mirror-related'] = ''
    el.clear()
    inner = soup.new_tag('div', attrs={'class': 'product-recommendations'})
    h2 = soup.new_tag('h2', attrs={'class': 'related-products__heading inline-richtext h2'}); h2.string = s('related_heading', lang)
    ul = soup.new_tag('ul', attrs={'class': 'grid product-grid grid--2-col grid--4-col-desktop', 'role': 'list'})
    for i, h in enumerate(picks, 1):
        frag = BeautifulSoup(cards[h], 'html.parser'); li = frag.find('li')
        li['style'] = f'--animation-order: {i};'
        ul.append(li)
    inner.append(h2); inner.append(ul); el.append(inner)
    # cards need the card stylesheet, which collection pages link in head
    if not soup.find('link', href=re.compile(r'component-card\.')):
        for coll in (ROOT / (prefix or '.') / 'collections').glob('*.html'):
            l = load(coll).find('link', href=re.compile(r'component-card\.'))
            if l:
                tag = soup.new_tag('link', rel='stylesheet', type='text/css', media='all', href=l['href'])
                soup.head.append(tag)
                break
    return 1

PHONE_RE = re.compile(r'\+48\s?570\s?909\s?091')
MAIL_RE = re.compile(r'shop@heatica\.com|delivery@heatica\.com')

def contact_page(soup, page, prefix, lang):
    form = soup.find('form', id='ContactForm')
    if form is None: return 0
    form['action'] = '/contact'
    form['method'] = 'post'
    form['data-success'] = s('contact_success', lang)
    form['data-fallback'] = s('contact_fallback', lang)
    form['data-quote'] = s('quote_subject', lang)
    form['data-mailto'] = 'shop@heatica.com'
    for name, val in (('lang', lang), ('page', clean_url(prefix, locale_of_page(page)[1]))):
        inp = form.find('input', attrs={'name': name})
        if inp is None:
            inp = soup.new_tag('input', type='hidden', attrs={'name': name}); form.insert(0, inp)
        inp['value'] = val
    if form.find('input', attrs={'name': 'website'}) is None:
        hp = soup.new_tag('div', attrs={'class': 'visually-hidden', 'aria-hidden': 'true'})
        hp.append(soup.new_tag('input', type='text', attrs={'name': 'website', 'tabindex': '-1', 'autocomplete': 'off'}))
        form.insert(1, hp)
    old = soup.find('script', attrs={'data-mirror-contact': True})
    if old: old.decompose()
    sc = soup.new_tag('script', attrs={'data-mirror-contact': ''}); sc.string = CONTACT_JS
    soup.body.append(sc)
    # tappable phone / e-mail in the page body
    main = soup.find('main') or soup
    for node in list(main.find_all(string=True)):
        if isinstance(node, Comment) or node.parent.name in ('script', 'style', 'a', 'textarea', 'option'): continue
        txt = str(node)
        if not (PHONE_RE.search(txt) or MAIL_RE.search(txt)): continue
        frag = BeautifulSoup('', 'html.parser')
        pos = 0
        for m in sorted(list(PHONE_RE.finditer(txt)) + list(MAIL_RE.finditer(txt)), key=lambda x: x.start()):
            frag.append(txt[pos:m.start()])
            a = soup.new_tag('a', href=('mailto:' + m.group(0)) if '@' in m.group(0) else ('tel:' + re.sub(r'\s', '', m.group(0))))
            a.string = m.group(0); frag.append(a); pos = m.end()
        frag.append(txt[pos:])
        node.replace_with(frag)
    return 1

MONEY_SPACE_RE = re.compile(r'^€(\d{1,3}(?: \d{3})+),(\d{2}) EUR$')

def strip_editor_attrs(soup):
    n = 0
    for el in soup.find_all(True):
        for a in [a for a in el.attrs if a.startswith('data-mce-')]:
            del el[a]; n += 1
    return n

def money_nbsp(soup, lang):
    """non-English locales format 1 850,00 with a no-break space; fix pages where a plain space slipped in."""
    if lang == 'en': return 0
    n = 0
    for m in soup.select('span.money'):
        txt = m.get_text()
        mm = MONEY_SPACE_RE.match(txt)
        if mm:
            m.string = f"€{mm.group(1).replace(' ', NBSP)},{mm.group(2)} EUR"; n += 1
    d = soup.find('script', id='mirror-variant-data')
    if d and d.string and '"th": " "' in d.string:
        d.string = d.string.replace('"th": " "', f'"th": "{NBSP}"'); n += 1
    return n

def fix_head_prologue(soup):
    """the theme emitted a <meta google-site-verification> before <head>; keep only the one inside <head>."""
    n = 0
    html = soup.html
    if html is None: return 0
    for child in list(html.children):
        if getattr(child, 'name', None) == 'head': break
        if getattr(child, 'name', None) == 'meta':
            child.decompose(); n += 1
    return n

def localize_internal_links(soup, page, prefix):
    """rich-text links that point at the English (root) version of a page which also
    exists in this locale -> point at the locale's own copy."""
    if not prefix: return 0
    from urllib.parse import unquote
    _, page_sub = locale_of_page(page)
    depth = len(page_sub.split('/')) - 1 if page_sub else 0
    main = soup.find('main') or soup
    n = 0
    for a in main.find_all('a', href=True):
        href = a['href']
        if href.startswith(('http', '//', '#', 'mailto:', 'tel:', 'data:', 'javascript:', '/')): continue
        path, _, tail = href.partition('#')
        path, _, query = path.partition('?')
        if not path: continue
        try:
            rel = (page.parent / unquote(path)).resolve().relative_to(ROOT)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) != 2 or parts[0] not in ('products', 'collections', 'pages'): continue
        sub = '/'.join(parts)
        if not sub.endswith('.html'): sub += '.html'
        if not (ROOT / prefix / sub).exists(): continue
        new = ('../' * depth + sub) if page_sub else f'{prefix}/{sub}'
        a['href'] = new + ('?' + query if query else '') + ('#' + tail if tail else '')
        n += 1
    return n

UK_SAUNA_INTRO = ('Сауна Drop — ідеальне доповнення як для літніх будиночків, так і для домашніх терас, як і інші культові '
                  'продукти Drop. Ця сауна «під ключ» готова змінити ваш простір без зусиль. Усе, що потрібно, — електрик і '
                  'рівний майданчик для встановлення.')

def self_identity(soup, prefix, sub):
    """every page names itself in the no-JS picker forms; locale cfg is enforced on serialization."""
    own = clean_url(prefix, sub)
    for rt in soup.find_all('input', attrs={'name': 'return_to'}):
        rt['value'] = own
    head = soup.head
    if head is not None and not head.find('link', rel='apple-touch-icon'):
        head.append(soup.new_tag('link', rel='apple-touch-icon', href='/apple-touch-icon.png'))

def fix_untranslated_copy(soup, prefix, sub):
    """collection copy that the live site left in English on the Ukrainian locale."""
    if prefix != 'uk' or sub != 'collections/sauna.html': return 0
    n = 0
    hero = soup.select_one('.collection-hero__description')
    if hero and 'Drop sauna is a perfect addition' in hero.get_text():
        hero.clear(); p = soup.new_tag('p'); p.string = UK_SAUNA_INTRO; hero.append(p); n += 1
    for m in soup.find_all('meta'):
        k = (m.get('name') or m.get('property') or '')
        if k in ('description', 'og:description', 'twitter:description') and 'Drop sauna is a perfect addition' in (m.get('content') or ''):
            m['content'] = UK_SAUNA_INTRO; n += 1
    return n

def process(page, cards_cache):
    prefix, sub = locale_of_page(page); lang = lang_of(prefix)
    soup = load(page)
    stats = {}
    stats['copy'] = fix_untranslated_copy(soup, prefix, sub)
    self_identity(soup, prefix, sub)
    stats['xlocale'] = localize_internal_links(soup, page, prefix)
    stats['mce'] = strip_editor_attrs(soup)
    stats['nbsp'] = money_nbsp(soup, lang)
    stats['prologue'] = fix_head_prologue(soup)
    stats['scripts'] = strip_theme_scripts(soup)
    ensure_shim(soup, lang)
    stats['facets'] = remove_facets(soup)
    stats['atom'] = remove_atom(soup)
    stats['pln'] = fix_currency_labels(soup)
    default_country(soup)
    stats['yt'] = youtube_privacy(soup)
    stats['footer'] = footer_blocks(soup, page, prefix, lang)
    if sub == '':
        stats['cta_home'] = cta_home(soup, page, prefix, lang)
    if sub.startswith('products/'):
        stats['cta_product'] = cta_product(soup, page, prefix, lang)
        if prefix not in cards_cache:
            cards_cache[prefix] = collection_cards(prefix)
        stats['related'] = related_products(soup, page, prefix, lang, *cards_cache[prefix])
    if sub == 'pages/contact-us.html':
        stats['contact'] = contact_page(soup, page, prefix, lang)
    out = set_cfg(str(soup), cur=prefix, sub=re.sub(r'\.html$', '', sub), root=rel_root(page))
    save(page, out)
    return stats

def run(prefixes):
    from collections import Counter
    total = Counter(); cache = {}
    for page in all_pages():
        prefix, _ = locale_of_page(page)
        if prefix not in prefixes: continue
        for k, v in process(page, cache).items():
            total[k] += v
        total['pages'] += 1
    print('content:', dict(total))

if __name__ == '__main__':
    run(sys.argv[1:] if len(sys.argv) > 1 else ['', 'pl', 'uk', 'cs', 'sk', 'hu', 'bg'])
