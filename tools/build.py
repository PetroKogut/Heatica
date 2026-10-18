import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
"""Reproducible build of the Heatica static mirror.

    python3 tools/build.py            # everything
    python3 tools/build.py countries srcset rename metadata links site check

Stages (in order):
  content   content fixes on the 7 language source locales (footer, CTA, related products, contact form, ...)
  pages     legal/extra pages from tools/data/extra_pages_en.json (+ per-language translations)
  variants  re-fetch live variant data for product pages (needs network to heatica.com)
  countries regenerate the 30 country variants from their language sources
  srcset    rebuild responsive images from on-disk renditions
  rename    rename 'name.ext@v=..&width=..' assets to 'name.v...w....ext' and rewrite references
  metadata  canonical / hreflang / og / JSON-LD
  links     extension-less internal links + switcher runtime
  site      sitemap.xml, robots.txt, 404.html, _headers
  check     broken-link audit
"""
import sys
from lib import COUNTRY_VARIANTS, LANG_PREFIXES

STAGES = ['content', 'pages', 'variants', 'countries', 'srcset', 'rename', 'metadata', 'links', 'site', 'check']

def main(stages):
    for st in stages:
        print(f'== {st}')
        if st == 'content':
            import content; content.run(LANG_PREFIXES)
        elif st == 'pages':
            import new_pages; new_pages.run()
        elif st == 'variants':
            import variants; variants.run()
        elif st == 'countries':
            import clone_locale
            for dst, (src, cc) in COUNTRY_VARIANTS.items():
                clone_locale.build_country(src, dst, cc)
        elif st == 'srcset':
            import srcset; srcset.run()
        elif st == 'rename':
            import rename_assets; rename_assets.run()
        elif st == 'metadata':
            import metadata; metadata.run()
        elif st == 'links':
            import links_clean; links_clean.run()
        elif st == 'site':
            import site_files; site_files.run()
        elif st == 'check':
            import check_links
            if check_links.run():
                sys.exit(1)
        else:
            sys.exit(f'unknown stage {st}')

if __name__ == '__main__':
    main(sys.argv[1:] or STAGES)
