import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""One-time: Shopify served PNG/JPEG bytes under .webp names for some renditions;
re-encode those files as real WebP (same file names) so the extension is honest
and pages get lighter."""
from pathlib import Path
from PIL import Image
from lib import ROOT

def run():
    n = before = after = 0
    for f in ROOT.glob('cdn/**/*.webp'):
        h = f.read_bytes()[:12]
        if h[:4] == b'RIFF' and h[8:12] == b'WEBP':
            continue
        size0 = f.stat().st_size
        with Image.open(f) as im:
            im.load()
            has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
            im = im.convert('RGBA' if has_alpha else 'RGB')
            im.save(f, 'WEBP', quality=82, method=6)
        n += 1; before += size0; after += f.stat().st_size
    print(f'webp: re-encoded {n} files, {before // 1024} KiB -> {after // 1024} KiB')

if __name__ == '__main__':
    run()
