import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Generate sitemap.xml, robots.txt, 404.html and _headers for the static host."""
import datetime, re
from xml.sax.saxutils import escape
from bs4 import BeautifulSoup
from lib import ROOT, SITE, PREFIXES, LANG_PREFIXES, LANG_NAMES, all_pages, locale_of_page, clean_url, page_file, hreflang_of, load
from strings import s

def sitemap(today):
    pages = all_pages()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for p in pages:
        prefix, sub = locale_of_page(p)
        out.append('  <url>')
        out.append(f'    <loc>{escape(SITE + clean_url(prefix, sub))}</loc>')
        out.append(f'    <lastmod>{today}</lastmod>')
        for q in PREFIXES:
            if page_file(q, sub).exists():
                out.append(f'    <xhtml:link rel="alternate" hreflang="{hreflang_of(q)}" href="{escape(SITE + clean_url(q, sub))}"/>')
        if page_file('', sub).exists():
            out.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{escape(SITE + clean_url("", sub))}"/>')
        out.append('  </url>')
    out.append('</urlset>')
    (ROOT / 'sitemap.xml').write_text('\n'.join(out) + '\n', encoding='utf-8')
    return len(pages)

def robots():
    (ROOT / 'robots.txt').write_text(
        'User-agent: *\nAllow: /\nDisallow: /contact\n\n'
        f'Sitemap: {SITE}/sitemap.xml\n', encoding='utf-8')

def not_found():
    soup = load(ROOT / 'index.html')
    # absolute URLs: the 404 page is served at arbitrary paths
    for attr in ('href', 'src', 'action', 'data-src'):
        for tag in soup.find_all(attrs={attr: True}):
            v = tag[attr]
            if v and not v.startswith(('http', '//', '#', 'mailto:', 'tel:', 'data:', 'javascript:', '/')):
                tag[attr] = '/' + re.sub(r'^(\./)+', '', v)
    for tag in soup.find_all(attrs={'srcset': True}):
        ents = []
        for ent in tag['srcset'].split(','):
            e = ent.strip()
            if not e: continue
            bits = e.split(' ', 1)
            if not bits[0].startswith(('http', '//', '/')): bits[0] = '/' + re.sub(r'^(\./)+', '', bits[0])
            ents.append(' '.join(bits))
        tag['srcset'] = ', '.join(ents)
    main = soup.find('main')
    main.clear()
    sec = soup.new_tag('section', attrs={'class': 'section page-width page-width--narrow', 'style': 'padding:6rem 0 8rem;text-align:center'})
    h1 = soup.new_tag('h1', attrs={'class': 'h0'}); h1.string = '404'; sec.append(h1)
    p = soup.new_tag('p', attrs={'class': 'h2', 'style': 'margin:0 0 2.5rem'}); p.string = s('nf_title', 'en'); sec.append(p)
    ul = soup.new_tag('ul', attrs={'class': 'list-unstyled', 'style': 'display:flex;flex-wrap:wrap;gap:1rem 2rem;justify-content:center'})
    for lp in LANG_PREFIXES:
        lang = lp or 'en'
        li = soup.new_tag('li')
        a = soup.new_tag('a', attrs={'class': 'button button--secondary', 'href': clean_url(lp, '')})
        a.string = f"{LANG_NAMES[lp]}: {s('nf_home', lang)}"
        li.append(a); ul.append(li)
    sec.append(ul); main.append(sec)
    soup.title.string = f"{s('nf_title', 'en')} – Heatica"
    for l in soup.head.find_all('link', rel=re.compile('canonical|alternate')): l.decompose()
    for m in soup.head.find_all('meta', attrs={'property': re.compile('^og:')}): m.decompose()
    robots_meta = soup.new_tag('meta', attrs={'name': 'robots', 'content': 'noindex'}); soup.head.append(robots_meta)
    cfg = soup.find('script', id='mirror-locale-cfg')
    if cfg:
        import json
        d = json.loads(cfg.string); d.update(cur='', sub='', root='/'); cfg.string = json.dumps(d, ensure_ascii=False)
    (ROOT / '404.html').write_text(str(soup), encoding='utf-8')

def headers():
    (ROOT / '_headers').write_text('''/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Content-Security-Policy: frame-ancestors 'none'
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=31536000; includeSubDomains

/cdn/*
  Cache-Control: public, max-age=31536000, immutable

/sitemap.xml
  Cache-Control: public, max-age=3600
''', encoding='utf-8')

def run(today=None):
    today = today or datetime.date.today().isoformat()
    n = sitemap(today); robots(); not_found(); headers()
    print(f'site files: sitemap.xml ({n} urls), robots.txt, 404.html, _headers')

if __name__ == '__main__':
    run()
