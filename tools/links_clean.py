import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Use extension-less URLs in internal links (the host maps /x to /x.html), and
teach the locale switcher the same, so navigation never bounces through a
redirect."""
import json, re
from lib import all_pages, load, save

LOCALE_JS = r"""(function(){var d=document.getElementById('mirror-locale-cfg');if(!d)return;var cfg=JSON.parse(d.textContent);var P=cfg.prefixes;
function nav(p){var url=cfg.sub?cfg.root+(p?p+'/':'')+cfg.sub:cfg.root+(p||'');if(!url)url='./';location.href=url;}
function pick(c){for(var i=0;i<c.length;i++){if(P.indexOf(c[i])>-1)return c[i];}return '';}
document.addEventListener('click',function(e){var a=e.target.closest?e.target.closest('localization-form a[data-value]'):null;if(!a)return;e.preventDefault();e.stopPropagation();
var v=a.getAttribute('data-value');var lang=cfg.cur?cfg.cur.split('-')[0]:'en';var cc=cfg.cur.indexOf('-')>-1?cfg.cur.split('-')[1]:'';
if(['en','pl','uk','cs','sk','hu','bg'].indexOf(v)>-1){var c=cc?[v+'-'+cc]:[];c.push(v==='en'?'':v);c.push('');nav(pick(c));}
else{var low=v.toLowerCase();nav(pick([lang+'-'+low,'en-'+low,lang==='en'?'':lang,'']));}},true);})();"""

SKIP = ('http://', 'https://', '//', '#', 'mailto:', 'tel:', 'data:', 'javascript:')

def clean_href(v):
    if not v or v.startswith(SKIP):
        return v
    m = re.match(r'^([^?#]*?)(\.html)([?#].*)?$', v)
    if not m:
        return v
    path, _, tail = m.group(1), m.group(2), m.group(3) or ''
    if path.endswith('index'):
        path = path[:-5] or './'
    return path + tail

def process(page):
    soup = load(page)
    n = 0
    for a in soup.find_all(['a', 'area'], href=True):
        nv = clean_href(a['href'])
        if nv != a['href']: a['href'] = nv; n += 1
    # locale switcher config + runtime
    cfg = soup.find('script', id='mirror-locale-cfg')
    if cfg and cfg.string:
        d = json.loads(cfg.string)
        d['sub'] = re.sub(r'\.html$', '', d.get('sub', ''))
        cfg.string = json.dumps(d, ensure_ascii=False)
    rt = soup.find('script', attrs={'data-mirror-locale': True})
    if rt is not None:
        rt.string = LOCALE_JS
    save(page, soup)
    return n

def run():
    total = 0
    pages = all_pages()
    for p in pages:
        total += process(p)
    print(f'links: {total} internal links made extension-less on {len(pages)} pages')

if __name__ == '__main__':
    run()
