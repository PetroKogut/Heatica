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
npx wrangler deploy            # uploads ~2.1k files, ~0.6 GB (largest file ~5 MB)
```

This publishes the Worker **heatica-static** at
`https://heatica-static.<account-subdomain>.workers.dev` (the subdomain is
shown under Workers & Pages → heatica-static → Settings → Domains & Routes).
The Worker is connected to this GitHub repository through Workers Builds, so
every push to `main` already runs the same deployment automatically (build
command empty, deploy command `npx wrangler deploy`); the manual command is
only needed to deploy a branch by hand. There is exactly one Worker and one
environment; the custom domain is attached to this same Worker in §4, so
nothing about the deployment changes at cut-over.

`wrangler.jsonc` sets the compatibility flag `assets_navigation_has_no_effect`.
Do not remove it: without it Cloudflare answers browser navigations that
miss an asset with the 404 page directly and the Worker (legacy redirects,
no-JS contact form, no-JS language picker) never runs. The `ratelimits`
binding throttles the contact form to 5 submissions per minute per IP.

Smoke-test on the workers.dev URL (`curl -sI -H 'Sec-Fetch-Mode: navigate' …`
and a real browser; the assets layer answers 307/308 for its own redirects,
the Worker answers 301/302):

- `/` , `/pl`, `/uk/products/drop-sauna`, `/cs/pages/privacy-policy` → 200
- `/products/drop-fire.html` → 3xx to `/products/drop-fire`; `/pl/` → 3xx to `/pl`
- `/en-ch/products/drop-x` → 301 to `/products/drop-x`
- `/cart`, `/account`, `/search` → 302 to `/`; `/products`, `/collections` → 301 to `/collections/drop-spa`
- `/collections/drop-spa/products/drop-x` → 301 to `/products/drop-x`
- `/policies/privacy-policy` → 301 to `/pages/privacy-policy`, `/pages/cookie-declaration` → 301 to `/pages/cookie-policy`
- `/sitemap_products_1.xml` → 301 to `/sitemap.xml`; `/favicon.ico`, `/apple-touch-icon.png` → 200
- `/does-not-exist` → the branded 404 page, HTTP 404
- a product page: pick a variant → price and photo change, URL gains `?variant=`; open that URL directly
- `/cs` (and `/hu`, `/bg`): the header shows Polsko/Lengyelország/Полша; tapping that already-selected
  country stays on the page, tapping Austria goes to `/en-at`, picking a language keeps the page
- the contact page in two locales (see §3 for the two modes); the response headers on `/` include the `_headers` security headers
- the workers.dev host sends `X-Robots-Tag: noindex` (the `_headers` rule), so the preview is never indexed

## 3. Contact form e-mail (Resend) — do this BEFORE the DNS change

The form posts to `/contact`; the Worker turns it into an e-mail via
[Resend](https://resend.com) (free tier: 100 e-mails/day, 3 000/month).
The sender is `noreply@heatica.com`, which Resend accepts only after the
domain is verified — so verification is a prerequisite of the cut-over.

1. Create a Resend account (use `shop@heatica.com` as the account e-mail),
   add the domain `heatica.com` and publish the DNS records it shows: a
   DKIM TXT record (`resend._domainkey`) and the Return-Path records on
   `send.heatica.com`. Create the `send` MX/TXT records explicitly — the zone
   has a wildcard MX pointing at Fastmail that would otherwise answer for that
   name. Your own MX/SPF/DMARC records stay untouched. Wait for **Verified**.
2. Store the API key as a Worker secret: `npx wrangler secret put RESEND_API_KEY`
   (or Worker → Settings → Variables and Secrets in the dashboard).
3. Optional: change `CONTACT_TO` / `CONTACT_FROM` in `wrangler.jsonc`.
4. Submit one test from the workers.dev URL and confirm it arrives in
   `shop@heatica.com` with the visitor's address as Reply-To.

Until the key is configured (or if Resend rejects a message) the Worker
answers 503/502 and the page falls back to opening the visitor's e-mail
client with the message prefilled, so the form is never a dead end.

## 4. Custom domain cut-over

DNS for heatica.com is already on Cloudflare, so the switch happens inside
the same account. Prepare a rollback first: note the current Shopify records
(`A heatica.com → 23.227.38.65`, `CNAME www → shops.myshopify.com`); putting
them back and detaching the custom domain restores the Shopify site within
minutes as long as the store is still open.

1. `npx wrangler deploy` to workers.dev is green and §2/§3 are done.
2. Dashboard → Workers & Pages → **heatica-static** → Settings → Domains &
   Routes → *Add* → **Custom domain** → `heatica.com`. Cloudflare replaces the
   conflicting `A` record itself and issues the certificate (a few minutes;
   no gap because the swap is atomic). Do not add `www` here.
3. DNS: delete `CNAME www → shops.myshopify.com` and
   `CNAME account → shops.myshopify.com`. **Leave MX, TXT (SPF, DKIM, DMARC,
   site verification, Resend) and every other record untouched.**
4. `www.heatica.com`: create a proxied placeholder record
   (`A www → 192.0.2.1`, orange cloud) and a Redirect Rule
   (Rules → Redirect Rules → *Create*): when
   `http.host eq "www.heatica.com"` → dynamic
   `concat("https://heatica.com", http.request.uri.path)`, status 301,
   preserve query string. (The Worker is not attached to `www`; this zone
   rule is the only thing that serves it.)
5. SSL/TLS → encryption mode **Full (strict)**, enable **Always Use HTTPS**.
   HSTS is sent by `_headers` for the apex only (1 year, no subdomains, so
   mail/other subdomains are unaffected); do not enable HSTS preload.
6. Verify from outside: `curl -I https://heatica.com/` → 200 with the security
   headers; `curl -I https://www.heatica.com/pl` → 301 to `https://heatica.com/pl`;
   repeat the §2 smoke list on the real domain; send one contact form.
7. In Shopify, remove heatica.com as the store domain, keep the plan alive
   for a day or two for forgotten exports, then close the store. Links in old
   e-mails to `account.heatica.com` stop working; update any marketing
   e-mails or social bios that still point at Shopify-only URLs (`/cart`,
   `/account`, `/collections/all`). Merge the URL-redirect list exported in
   §1 into `REDIRECTS` in `worker/index.js` if it contains anything the table
   does not cover.
8. Google Search Console: submit `https://heatica.com/sitemap.xml`, remove the
   old `sitemap_*.xml` entries (they now redirect), keep both
   `google-site-verification` tokens (meta tag and DNS TXT); expect many
   "new" locale URLs and watch the 404 report for the first weeks. Optionally
   disable the workers.dev route in the dashboard once the domain works.

## 5. Analytics and cookies

The live Shopify theme loaded Google Tag Manager (GTM-KP2CD9F → GA4) and the
Cookiebot consent banner. The static site deliberately ships **no tracking
and no banner** (the only third parties are the YouTube no-cookie player and
the Typeform on the B2B page, both loaded on demand). Consequences: GA4
reporting for heatica.com ends on cut-over day, and the Cookiebot
subscription can be cancelled. If you ever want analytics back, add a
privacy-friendly, cookieless tool (Cloudflare Web Analytics, Plausible) via
`tools/content.py` rather than re-enabling GTM.

## 6. Running the site afterwards

- Content lives in the HTML files; the seven language locales
  (`index.html`+root, `pl/`, `uk/`, `cs/`, `sk/`, `hu/`, `bg/`) are the sources.
  After editing a source page run `python3 tools/build.py content countries metadata links site check`
  to regenerate the 30 country variants and the sitemap, then commit; Workers
  Builds deploys `main` automatically (or run `npx wrangler deploy`).
- Prices/variants were last synchronised with Shopify on the build date in
  `sitemap.xml`; `python3 tools/build.py variants` refreshes them while the
  store is still online.
- Limits: Workers Static Assets allows 20 000 files and 25 MiB per file;
  the site uses ~2 100 files, largest ~5 MiB.
- Secrets never live in the repo: `.dev.vars`, `.env*` and `.wrangler/` are
  git-ignored and excluded from the asset upload (`.assetsignore`).
- `tools/devserver.py 8123` serves the repository locally with the same
  URL behaviour as Workers (clean URLs, 404 page) for testing.
