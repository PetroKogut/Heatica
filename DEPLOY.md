# Deploying heatica.com as a static site on Cloudflare Workers

The repository root is the website. `wrangler.jsonc` serves it through
Workers Static Assets; `worker/index.js` only handles the contact form and
legacy-URL redirects. Everything else (clean URLs, 404 page, caching
headers) is configured declaratively.

## 1. Before switching Shopify off

Do this while the Shopify admin is still available. Once the store is
closed, nothing below can be recovered.

- Export from Shopify admin: theme (Online Store → Themes → ⋯ → Download
  theme file), products CSV, customers/orders CSV, Translate & Adapt CSV,
  the URL redirect list (Online Store → Navigation → URL redirects).
- Note every app that currently sends e-mail on your behalf (contact-form
  notifications, Shopify Email). After the cut-over the only sender is
  the Worker (see §3).
- If Google Merchant Center / Facebook Shop pull feeds from Shopify,
  pause those channels; they break when the store closes.
- In Google Search Console, export the list of indexed URLs and the
  top-traffic pages so you can prioritise redirects if anything is missed.

## 2. First deployment (workers.dev, no custom domain)

```
npm install -g wrangler        # or: npx wrangler ...
npx wrangler login
npx wrangler deploy            # uploads ~1.3k assets, ~0.55 GB
```

This publishes to `https://heatica-static.<account>.workers.dev`.
If the Worker is connected to GitHub (Workers Builds), every push to
`main` does the same automatically: build command empty, deploy command
`npx wrangler deploy`.

Smoke-test on the workers.dev URL:

- `/` , `/pl`, `/uk/products/drop-sauna`, `/cs/pages/privacy-policy` → 200
- `/products/drop-fire.html` → 301 to `/products/drop-fire`
- `/en-ch/products/drop-x` → 301 to `/products/drop-x`
- `/cart`, `/account`, `/search` → 302 to `/`
- `/collections/drop-spa/products/drop-x` → 301 to `/products/drop-x`
- `/does-not-exist` → the branded 404 page, HTTP 404
- a product page: pick a variant → price and photo change, URL gains `?variant=`
- the contact page: submit the form (see §3 for the two modes)

## 3. Contact form e-mail (Resend)

The form posts to `/contact`, which the Worker turns into an e-mail via
[Resend](https://resend.com) (free tier: 3 000 e-mails/month).

1. Create a Resend account, add the domain `heatica.com` and publish the
   DNS records it asks for (SPF/DKIM TXT records; they do not interfere
   with your MX records).
2. Create an API key and store it as a Worker secret:
   `npx wrangler secret put RESEND_API_KEY` (and again with
   `--env production` once that environment exists).
3. Optional: change `CONTACT_TO` / `CONTACT_FROM` in `wrangler.jsonc`.

Until the key is configured the Worker answers 503 and the page falls
back to opening the visitor's e-mail client with the message prefilled,
so the form is never a dead end.

## 4. Custom domain cut-over

DNS for heatica.com is already on Cloudflare, so the switch is a DNS
change inside the same account.

1. Make sure `wrangler deploy` to workers.dev is green and smoke-tested.
2. In Cloudflare DNS delete the records that point to Shopify:
   the `A heatica.com → 23.227.38.x` record(s), the
   `CNAME www → shops.myshopify.com` record and the
   `CNAME account → shops.myshopify.com` record. **Leave MX, TXT (SPF,
   DKIM, DMARC, site verification) and any other records untouched.**
3. Attach the domain to the Worker:
   `npx wrangler deploy --env production` (the `production` environment
   in `wrangler.jsonc` declares `heatica.com` as a custom domain; Cloudflare
   creates the DNS record and the certificate automatically). Add the
   same secret to this environment: `npx wrangler secret put RESEND_API_KEY --env production`.
4. `www.heatica.com`: create a proxied placeholder record
   (`A www → 192.0.2.1`, orange cloud) and a Redirect Rule
   (Rules → Redirect Rules → *Create*): when
   `http.host eq "www.heatica.com"` → dynamic
   `concat("https://heatica.com", http.request.uri.path)` , status 301,
   preserve query string. The Worker also redirects `www` for any request
   that reaches it, but the zone-level rule is faster.
5. SSL/TLS → set the encryption mode to **Full (strict)** and enable
   **Always Use HTTPS**. HSTS is sent by `_headers` (1 year, includeSubDomains);
   only enable HSTS preload in the dashboard once you are sure every
   subdomain you still use has HTTPS.
6. In Shopify, remove heatica.com as the store domain and only then close
   the store. Keep the Shopify plan running for a day after cut-over in
   case you need to export something you forgot.
7. Google Search Console: submit `https://heatica.com/sitemap.xml`,
   request indexing of the homepage; the hreflang cluster now covers all
   37 locales, the Swiss locales redirect, Shopify-only URLs redirect.

## 5. Running the site afterwards

- Content lives in the HTML files; the seven language locales
  (`index.html`+root, `pl/`, `uk/`, `cs/`, `sk/`, `hu/`, `bg/`) are the sources.
  After editing a source page run `python3 tools/build.py countries metadata links site check`
  to regenerate the 30 country variants and the sitemap, then commit.
- Prices/variants were last synchronised with Shopify on the build date in
  `sitemap.xml`; `python3 tools/build.py variants` refreshes them while the
  store is still online.
- Limits: Workers Static Assets allows 20 000 files and 25 MiB per file;
  the site uses ~1 300 files, largest ~5 MiB.
- `tools/devserver.py 8123` serves the repository locally with the same
  URL behaviour as Workers (clean URLs, 404 page) for testing.
