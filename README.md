# Heatica — static site

Static version of [heatica.com](https://heatica.com) (outdoor spas and saunas, Kraków),
built from a crawl of the Shopify storefront and maintained as plain HTML.
It is designed to **replace** the Shopify site: hosting on Cloudflare Workers
(static assets + a tiny Worker), see [`DEPLOY.md`](DEPLOY.md).

## Layout

| path | what |
|------|------|
| `index.html`, `products/`, `collections/`, `pages/` | English (default) locale — a **source** locale |
| `pl/`, `uk/`, `cs/`, `sk/`, `hu/`, `bg/` + `pl.html` … | the other six language **source** locales |
| `en-at/`, `uk-pl/`, `bg-bg/`, … + `en-at.html` … | 30 country variants, generated from the sources (do not edit by hand) |
| `cdn/` | theme assets and images (`name.v<version>.w<width>.ext`) |
| `sitemap.xml`, `robots.txt`, `404.html`, `_headers` | generated host files |
| `worker/index.js`, `wrangler.jsonc`, `.assetsignore` | Cloudflare Workers deployment |
| `tools/` | reproducible build pipeline, see [`tools/README.md`](tools/README.md) |
| `.github/workflows/deploy-pages.yml` | preview deployment to GitHub Pages (not for production) |

37 locales, 25 pages each: home, 11 products, 4 collections, 9 info/legal pages.

## What works without Shopify

Catalogue, variant picker (price + photo, `?variant=` deep links), galleries,
language/country switcher, "Request a quote" flow into the contact form,
contact form (Worker → e-mail via Resend, with a mailto fallback), related
products, legal pages, sitemap/hreflang/canonical, clean URLs, 404 page,
legacy-URL redirects. There is no cart, checkout, customer account, search
or newsletter — the site is a catalogue with a quote request.

## Editing content

Edit a source locale page, then

```
python3 tools/build.py content pages countries metadata links site check
```

and commit. Prices/variants can be refreshed from Shopify while it is still
online with `python3 tools/build.py variants`.
