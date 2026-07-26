# Heatica — static mirror

Static mirror of [heatica.com](https://heatica.com) (Shopify storefront), captured on 2026-07-26 with `wget --mirror --page-requisites --adjust-extension --convert-links`.

## Contents

- `index.html` — homepage (default English locale)
- `products/`, `collections/`, `pages/` — product, collection, and info pages
- `pl/`, `uk/`, `en-at/`, `uk-at/`, … — 17 additional locale/region variants
- `cdn/` — theme assets and images served from the site's own CDN path

Internal links and asset references are rewritten to relative local paths, so the mirror can be served by any static file server (e.g. `python3 -m http.server`) or GitHub Pages.

## Not included

- Cart, checkout, account, and order pages (transactional, excluded from the crawl)
- Third-party externals loaded at runtime (Google Tag Manager, Cookiebot, shop.app scripts) — these still point to their original URLs
- Server-side features (search, cart AJAX, checkout) — the mirror is content-only
