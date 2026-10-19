# Build tooling

The site is a static mirror of the Shopify store heatica.com. It was
crawled with `wget --mirror --page-requisites --convert-links` on
2026-07-26, stripped of every commerce/Shopify dependency, translated into
four more languages (cs, sk, hu, bg) on top of the crawled en/pl/uk, and
expanded with country variants. The one-off crawl
post-processing scripts are not kept; everything that has to be
re-runnable lives here.

```
python3 tools/build.py              # all stages
python3 tools/build.py countries srcset metadata links site check
node tools/worker_test.mjs          # Worker: redirects, no-JS pickers, contact form (no network)
```

`tools/data/products/<handle>.json` is Shopify's product JSON captured while the
store was online (prices, variants, featured image); `metadata` uses it for the
product og:image and `variants` can fall back to it once Shopify is gone.

| stage      | module             | what it does |
|------------|--------------------|--------------|
| content    | `content.py`       | footer legal links + social icons, "Request a quote" CTAs, static "You may also like", contact form (Worker endpoint, honeypot, mailto fallback, tel:/mailto: links), removal of Shopify-only theme scripts/facets/atom links, theme-global shim |
| pages      | `new_pages.py`     | legal pages, chemical starter kit and the massage-jets collection, built from `data/extra_pages_en.json` + `data/segments_legal_<lang>.json` |
| variants   | `variants.py`      | fetches `/products/<handle>.js` from Shopify and embeds variant ids/prices/photos + the picker runtime (`?variant=` deep links) |
| countries  | `clone_locale.py`  | clones the 7 language sources into the 30 country variants (`lib.COUNTRY_VARIANTS`) |
| srcset     | `srcset.py`        | rebuilds `srcset`/`sizes` from the width renditions on disk |
| rename     | `rename_assets.py` | one-time rename of `name.ext@v=…&width=…` files to `name.v….w….ext` (map in `data/asset_renames.json`) |
| metadata   | `metadata.py`      | absolute self-canonical, hreflang cluster from existing files, og:url/og:image, JSON-LD cleanup |
| links      | `links_clean.py`   | extension-less internal links, locale-switcher runtime |
| site       | `site_files.py`    | `sitemap.xml`, `robots.txt`, `404.html`, `_headers` |
| check      | `check_links.py`   | fails if any internal reference is broken |

Source locales: `index.html` + `products/ collections/ pages/` (English),
and `pl/ uk/ cs/ sk/ hu/ bg/` with their `<lang>.html` homepages. Edit
those; never edit a country variant by hand (it is overwritten by
`countries`). UI strings that the mirror adds are in `strings.py`.

`devserver.py` mimics Workers Static Assets locally (clean URLs, 404.html).
