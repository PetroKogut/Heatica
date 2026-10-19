import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Variant picker data: fetch live variant data per source locale and embed it
with the runtime that swaps price/photo, supports ?variant= deep links and
keeps the URL in sync."""
import json, os, re, time, urllib.request
from pathlib import Path
from lib import ROOT, all_pages, locale_of_page, save

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
      'Accept': '*/*', 'Accept-Language': 'en'}
IMGDIR = ROOT / 'cdn' / 'files'

RUNTIME_JS = r"""(function(){var d=document.getElementById('mirror-variant-data');if(!d)return;var cfg=JSON.parse(d.textContent);
var vs=document.querySelector('variant-selects');if(!vs)return;var injected=null;
function fmt(c){var n=(c/100).toFixed(cfg.fmt.dec),p=n.split('.');var ip=p[0].replace(/\B(?=(\d{3})+(?!\d))/g,cfg.fmt.th);return cfg.fmt.pre+ip+(cfg.fmt.dec>0?cfg.fmt.ds+p[1]:'')+cfg.fmt.suf;}
function selected(){var sel=[];vs.querySelectorAll('fieldset').forEach(function(fs){var c=fs.querySelector('input:checked');if(c)sel.push(c.value.trim());});return sel;}
function find(sel){for(var i=0;i<cfg.variants.length;i++){var x=cfg.variants[i];if(x.opts.length===sel.length&&x.opts.every(function(o,j){return o===sel[j];}))return x;}return null;}
function apply(v,push){var pb=document.getElementById('price-'+vs.dataset.section);if(pb)pb.querySelectorAll('.money').forEach(function(m){m.textContent=fmt(v.price);});
if((v.media||v.img)&&injected){injected.remove();injected=null;}
if(v.media){var s=document.querySelector('[data-media-id$="-'+v.media+'"]');if(s&&s.parentElement&&s.parentElement.firstElementChild!==s){s.parentElement.insertBefore(s,s.parentElement.firstElementChild);}}
else if(v.img){var list=document.querySelector('media-gallery ul,.product__media-list');if(list&&list.firstElementChild){var c=list.firstElementChild.cloneNode(true);c.removeAttribute('id');c.removeAttribute('data-media-id');c.querySelectorAll('[id]').forEach(function(e){e.removeAttribute('id');});c.querySelectorAll('[data-media-id]').forEach(function(e){e.removeAttribute('data-media-id');});var im=c.querySelector('img');if(im){im.src=v.img;im.removeAttribute('srcset');im.alt=v.alt||'';}list.insertBefore(c,list.firstElementChild);injected=c;}}
if(push&&v.id&&window.history&&history.replaceState){try{var u=new URL(location.href);u.searchParams.set('variant',v.id);history.replaceState(null,'',u.pathname+u.search+u.hash);}catch(e){}}}
vs.addEventListener('change',function(){var v=find(selected());if(v)apply(v,true);});
var q=null;try{q=new URLSearchParams(location.search).get('variant');}catch(e){}
if(q){for(var i=0;i<cfg.variants.length;i++){if(String(cfg.variants[i].id)===q){var v=cfg.variants[i];var fss=vs.querySelectorAll('fieldset');fss.forEach(function(fs,j){fs.querySelectorAll('input').forEach(function(inp){if(inp.value.trim()===v.opts[j])inp.checked=true;});});apply(v,false);break;}}}
})();"""

_cache = {}
def get(url, binary=False):
    last = None
    for wait in (0, 2, 4, 8, 16):
        if wait: time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read() if binary else json.loads(r.read())
        except Exception as e:
            last = e
    raise RuntimeError(f'fetch failed {url}: {last}')

LIVE_LOCALES = {'', 'pl', 'uk'}   # locales that exist on the Shopify site; others use English option values
def product_json(prefix, handle):
    prefix = prefix if prefix in LIVE_LOCALES else ''
    key = (prefix, handle)
    if key not in _cache:
        saved = ROOT / 'tools' / 'data' / 'products' / f'{handle}.json'   # captured while Shopify was online
        try:
            _cache[key] = get(f'https://heatica.com/{prefix + "/" if prefix else ""}products/{handle}.js')
            time.sleep(0.3)
            if prefix == '':
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_text(json.dumps(_cache[key], ensure_ascii=False, indent=1), encoding='utf-8')
        except RuntimeError:
            if not saved.exists():
                raise
            print(f'variants: live fetch failed for {handle}, using {saved.relative_to(ROOT)}')
            _cache[key] = json.loads(saved.read_text(encoding='utf-8'))
    return _cache[key]

def variant_image(media):
    mid = media['id']
    src = media['preview_image']['src']
    ext = os.path.splitext(src.split('?')[0])[1] or '.jpg'
    target = IMGDIR / f'variant-{mid}{ext}'
    if not target.exists():
        url = ('https:' + src if src.startswith('//') else src) + ('&' if '?' in src else '?') + 'width=1445'
        target.write_bytes(get(url, binary=True))
    return target

def inject(page):
    prefix, sub = locale_of_page(page)
    html = page.read_text(encoding='utf-8')
    m = re.search(r'<script id="mirror-variant-data" type="application/json">(.*?)</script>', html, re.S)
    if not m or '<variant-selects' not in html:
        return False
    old = json.loads(m.group(1))
    data = product_json(prefix, page.stem)
    # radio values present on the page, per option position (proofreading may have changed spellings)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    page_values = [[(i.get('value') or '').strip() for i in fs.find_all('input')] for fs in soup.select('variant-selects fieldset')]
    live_values = [[(x or '').strip() for x in o.get('values', [])] for o in data.get('options', [])]
    def to_page(j, val):
        val = val.strip()
        if j < len(page_values) and val in page_values[j]:
            return val
        if j < len(live_values) and j < len(page_values) and val in live_values[j]:
            k = live_values[j].index(val)
            if k < len(page_values[j]) and len(live_values[j]) == len(page_values[j]):
                return page_values[j][k]
        norm = re.sub(r'Car(?:ittii|itii)\b', 'Cariitti', val)
        return norm if j < len(page_values) and norm in page_values[j] else val
    variants = []
    for v in data['variants']:
        opts = [to_page(j, o) for j, o in enumerate((v.get('option1'), v.get('option2'), v.get('option3'))) if o is not None]
        fm = v.get('featured_media') or {}
        media = fm.get('id')
        entry = {'id': v['id'], 'opts': opts, 'price': v['price'], 'media': media}
        if media and f'-{media}"' not in html:
            entry['media'] = None
            if fm.get('preview_image'):
                img = variant_image(fm)
                entry['img'] = os.path.relpath(img, page.parent)
                entry['alt'] = v.get('title') or ''
        variants.append(entry)
    payload = json.dumps({'variants': variants, 'fmt': old['fmt']}, ensure_ascii=False)
    html = re.sub(r'<script id="mirror-variant-data" type="application/json">.*?</script>\s*<script data-mirror-variants[^>]*>.*?</script>',
                  lambda _: f'<script id="mirror-variant-data" type="application/json">{payload}</script>\n<script data-mirror-variants="">{RUNTIME_JS}</script>',
                  html, count=1, flags=re.S)
    save(page, html)
    return True

def run(prefixes=('', 'pl', 'uk', 'cs', 'sk', 'hu', 'bg')):
    n = 0
    for page in all_pages():
        prefix, sub = locale_of_page(page)
        if prefix in prefixes and sub.startswith('products/') and inject(page):
            n += 1
    print(f'variants: {n} product pages re-injected, {len(_cache)} live fetches')

if __name__ == '__main__':
    run()
