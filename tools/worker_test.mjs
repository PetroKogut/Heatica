// Worker behaviour test: node tools/worker_test.mjs   (no network, no Cloudflare account needed)
import worker from '../worker/index.js';
const env = { ASSETS: { fetch: async (req) => new Response('ASSET ' + new URL(req.url).pathname, { status: 200 }) } };
const O = 'https://heatica.com';
let fails = 0;
const check = (ok, label, got) => { if (!ok) fails++; console.log((ok ? 'ok  ' : 'FAIL') + ' ' + label + ' -> ' + got); };

const redirects = [
  ['GET', '/cart', 302, '/'],
  ['GET', '/pl/account/login', 302, '/pl'],
  ['GET', '/en-ch/products/drop-x', 301, '/products/drop-x'],
  ['GET', '/uk-ch', 301, '/uk'],
  ['GET', '/uk-pl/collections/sauna/products/drop-x', 301, '/uk-pl/products/drop-x'],
  ['GET', '/collections/all', 301, '/collections/drop-spa'],
  ['GET', '/collections', 301, '/collections/drop-spa'],
  ['GET', '/policies/refund-policy', 301, '/pages/terms-of-service'],
  ['GET', '/cs/policies/privacy-policy', 301, '/cs/pages/privacy-policy'],
  ['GET', '/products/drop-fire.js', 301, '/products/drop-fire'],
  ['GET', '/pages/cookie-declaration', 301, '/pages/cookie-policy'],
  ['GET', '/hu/products/krazek-p2500-d-34-mm-kwiatka-psa', 301, '/hu/collections/accessories'],
  ['GET', '/sitemap_products_1.xml?from=1&to=2', 301, '/sitemap.xml'],
  ['GET', '/contact', 302, '/pages/contact-us'],
  ['GET', '/uk-at/contact', 302, '/uk-at/pages/contact-us'],
  ['GET', '/blogs/news/post', 301, '/'],
  ['GET', '/products/drop-fire', 200, 'ASSET'],
  ['GET', '/pl/collections/drop-spa', 200, 'ASSET'],
];
for (const [method, path, status, expect] of redirects) {
  const res = await worker.fetch(new Request(O + path, { method }), env);
  const loc = res.headers.get('location') || '';
  const ok = res.status === status && (expect === 'ASSET' ? (await res.text()).startsWith('ASSET') : loc === O + expect);
  check(ok, `${method} ${path}`, `${res.status} ${loc}`);
}
let r = await worker.fetch(new Request('https://www.heatica.com/pl/products/drop-x?variant=1'), env);
check(r.status === 301 && r.headers.get('location') === O + '/pl/products/drop-x?variant=1', 'www -> apex', r.headers.get('location'));

// no-JS language/country picker (POST /localization)
const loc = async (returnTo, fields) => {
  const fd = new FormData(); fd.set('return_to', returnTo);
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  const res = await worker.fetch(new Request(O + '/localization', { method: 'POST', body: fd }), env);
  return `${res.status} ${(res.headers.get('location') || '').replace(O, '')}`;
};
const picks = [
  ['/', { country_code: 'PL' }, '303 /'],                      // the presented country is a no-op
  ['/cs', { country_code: 'PL' }, '303 /cs'],
  ['/hu/pages/contact-us', { country_code: 'PL' }, '303 /hu/pages/contact-us'],
  ['/en-at', { country_code: 'AT' }, '303 /en-at'],
  ['/sk-sk/products/drop-x', { country_code: 'SK' }, '303 /sk-sk/products/drop-x'],
  ['/', { country_code: 'AT' }, '303 /en-at'],
  ['/cs', { country_code: 'AT' }, '303 /en-at'],                // no cs-at locale: English for Austria
  ['/cs', { country_code: 'DE' }, '303 /cs'],                   // no locale for Germany: stay
  ['/uk-at/products/drop-fire', { country_code: 'PL' }, '303 /uk-pl/products/drop-fire'],
  ['/', { locale_code: 'cs' }, '303 /cs'],
  ['/en-pl/products/drop-x', { locale_code: 'uk' }, '303 /uk-pl/products/drop-x'],
  ['/en-at', { locale_code: 'cs' }, '303 /cs'],                 // no cs-at: language wins
];
for (const [ret, fields, expect] of picks) {
  const got = await loc(ret, fields);
  check(got === expect, `localization ${ret} ${JSON.stringify(fields)}`, got);
}

// contact form
const fd = new FormData(); fd.set('contact[Name]', 'T'); fd.set('contact[email]', 'a@b.co'); fd.set('contact[Comment]', 'Hi\r\nthere'); fd.set('page', '/pl/pages/contact-us');
r = await worker.fetch(new Request(O + '/contact', { method: 'POST', body: fd, headers: { accept: 'application/json' } }), env);
check(r.status === 503, 'contact json without key', `${r.status} ${await r.text()}`);
r = await worker.fetch(new Request(O + '/contact', { method: 'POST', body: fd }), env);
check(r.status === 303 && r.headers.get('location') === O + '/pl/pages/contact-us?contact_error=not_configured#ContactForm', 'contact no-js without key', r.headers.get('location'));
const bad = new FormData(); bad.set('contact[email]', 'nope'); bad.set('page', '//evil.com/x');
r = await worker.fetch(new Request(O + '/contact', { method: 'POST', body: bad }), env);
check(r.status === 303 && r.headers.get('location') === O + '/pages/contact-us?contact_error=invalid#ContactForm', 'contact invalid + unsafe page', r.headers.get('location'));
const hp = new FormData(); hp.set('contact[email]', 'a@b.co'); hp.set('contact[Comment]', 'x'); hp.set('website', 'spam');
r = await worker.fetch(new Request(O + '/contact', { method: 'POST', body: hp, headers: { accept: 'application/json' } }), env);
check(r.status === 200, 'honeypot pretends success', String(r.status));

console.log(fails ? `${fails} FAILURE(S)` : 'all cases pass');
process.exit(fails ? 1 : 0);
