/**
 * Heatica static mirror — Cloudflare Worker.
 *
 * Static pages/assets are served by the Workers Assets layer (see wrangler.jsonc);
 * this script only runs for requests that do not match an asset:
 *   - POST /contact (and /<locale>/contact): the contact form (e-mail via Resend)
 *   - legacy Shopify URLs: 301/302 to their static equivalents
 *   - everything else: the assets layer's 404 page
 */

const LOCALE = '(?:pl|uk|cs|sk|hu|bg|[a-z]{2}-[a-z]{2})';
const LEGAL = 'privacy-policy|terms-of-service|cookie-policy|acceptable-use-policy';

const REDIRECTS = [
  // Switzerland locales were retired
  [new RegExp('^/en-ch(?:/(.*))?$'), (m) => '/' + (m[1] || ''), 301],
  [new RegExp('^/uk-ch(?:/(.*))?$'), (m) => '/uk' + (m[1] ? '/' + m[1] : ''), 301],
  // Shopify-only surfaces -> locale home
  [new RegExp(`^(/${LOCALE})?/(?:cart|checkout|checkouts|account|customer_authentication|orders|apps|services|tools|admin|search)(?:/.*)?$`), (m) => (m[1] || '/'), 302],
  // collection-scoped product URLs
  [new RegExp(`^(/${LOCALE})?/collections/[^/]+/products/([^/?#]+)/?$`), (m) => `${m[1] || ''}/products/${m[2]}`, 301],
  [new RegExp(`^(/${LOCALE})?/collections/all/?$`), (m) => `${m[1] || ''}/collections/drop-spa`, 301],
  [new RegExp(`^(/${LOCALE})?/collections/frontpage/?$`), (m) => (m[1] || '/'), 301],
  [new RegExp(`^(/${LOCALE})?/blogs(?:/.*)?$`), (m) => (m[1] || '/'), 301],
  // Shopify policy routes -> our pages
  [new RegExp(`^(/${LOCALE})?/policies/(${LEGAL})/?$`), (m) => `${m[1] || ''}/pages/${m[2]}`, 301],
  [new RegExp(`^(/${LOCALE})?/policies/(?:refund-policy|shipping-policy|legal-notice|subscription-policy)/?$`), (m) => `${m[1] || ''}/pages/terms-of-service`, 301],
  [new RegExp(`^(/${LOCALE})?/policies/contact-information/?$`), (m) => `${m[1] || ''}/pages/contact-us`, 301],
  // product JSON endpoints
  [new RegExp(`^(/${LOCALE})?/products/([^/?#]+)\\.js(?:on)?$`), (m) => `${m[1] || ''}/products/${m[2]}`, 301],
  // Shopify listing/vendor/type pages -> the main collection
  [new RegExp(`^(/${LOCALE})?/(?:products|collections|collections/vendors|collections/types)/?$`), (m) => `${m[1] || ''}/collections/drop-spa`, 301, false],
  // pages that exist in Shopify's sitemap but have no static equivalent
  [new RegExp(`^(/${LOCALE})?/pages/cookie-declaration/?$`), (m) => `${m[1] || ''}/pages/cookie-policy`, 301],
  [new RegExp(`^(/${LOCALE})?/products/krazek-p2500-d-34-mm-kwiatka-psa/?$`), (m) => `${m[1] || ''}/collections/accessories`, 301],
  [new RegExp(`^(/${LOCALE})?/sitemap_[a-z_]+(?:_\\d+)?\\.xml$`), () => '/sitemap.xml', 301, false],
];

const PREFIXES = ['', 'pl', 'uk', 'cs', 'sk', 'hu', 'bg', 'en-at', 'uk-at', 'en-fr', 'uk-fr', 'en-nl', 'uk-nl', 'en-it', 'uk-it',
  'pl-pl', 'en-pl', 'uk-pl', 'en-dk', 'uk-dk', 'en-bg', 'uk-bg', 'bg-bg', 'en-hr', 'uk-hr', 'en-hu', 'uk-hu', 'hu-hu',
  'en-ie', 'uk-ie', 'en-lt', 'uk-lt', 'en-si', 'uk-si', 'en-sk', 'uk-sk', 'sk-sk'];
const LANGS = ['en', 'pl', 'uk', 'cs', 'sk', 'hu', 'bg'];
const DEFAULT_COUNTRY = 'pl';   // country presented by the source locales (tools/content.py DEFAULT_COUNTRY)

const SAFE_PATH = /^\/[A-Za-z0-9\-._~\/]*$/;
const SEC_HEADERS = {
  'x-content-type-options': 'nosniff',
  'x-frame-options': 'DENY',
  'referrer-policy': 'strict-origin-when-cross-origin',
  'cache-control': 'no-store',
};

/** no-JS fallback for the language/country picker forms (the page JS normally intercepts clicks). */
async function handleLocalization(request, url) {
  let form;
  try { form = await request.formData(); } catch (e) { form = new FormData(); }
  const ret = (form.get('return_to') || '/').toString();
  const m = ret.match(new RegExp(`^/(${LOCALE})(?=/|$)`));
  const cur = m ? m[1] : '';
  const sub = ret.replace(new RegExp(`^/(${LOCALE})(?=/|$)`), '').replace(/^\//, '').replace(/\.html$/, '');
  const lang = cur ? cur.split('-')[0] : 'en';
  const cc = cur.includes('-') ? cur.split('-')[1] : '';
  const pick = (c) => c.find((x) => PREFIXES.includes(x)) ?? '';
  let p;
  const lc = (form.get('locale_code') || '').toString().toLowerCase();
  const country = (form.get('country_code') || '').toString().toLowerCase();
  if (lc && LANGS.includes(lc)) p = pick([...(cc ? [`${lc}-${cc}`] : []), lc === 'en' ? '' : lc, '']);
  else if (country) p = country === (cc || DEFAULT_COUNTRY) ? cur : pick([`${lang}-${country}`, `en-${country}`, lang === 'en' ? '' : lang, '']);
  else p = cur;
  const dest = sub ? `/${p ? p + '/' : ''}${sub}` : `/${p}`;
  return redirect(`${url.origin}${dest}`, 303);
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;


function redirect(location, status) {
  return new Response(null, { status, headers: { location, ...SEC_HEADERS } });
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', ...SEC_HEADERS } });
}

async function handleContact(request, env, url) {
  let form;
  try { form = await request.formData(); } catch (e) { return json({ ok: false, error: 'bad_request' }, 400); }
  const f = (k) => (form.get(k) || '').toString().trim();
  const wantsJson = (request.headers.get('accept') || '').includes('application/json');
  const page = SAFE_PATH.test(f('page')) && !f('page').startsWith('//') ? f('page') : '/pages/contact-us';
  const back = (q) => redirect(`${url.origin}${page}?${q}#ContactForm`, 303);
  const done = () => wantsJson ? json({ ok: true }) : back('contact_posted=true');
  const fail = (error, status) => wantsJson ? json({ ok: false, error }, status) : back(`contact_error=${error}`);

  if (f('website')) return done();                       // honeypot: pretend success
  if (env.CONTACT_LIMITER) {                              // 5 submissions / minute / IP (Workers rate-limit binding)
    try {
      const { success } = await env.CONTACT_LIMITER.limit({ key: request.headers.get('cf-connecting-ip') || 'unknown' });
      if (!success) return fail('rate_limited', 429);
    } catch (e) { /* limiter unavailable: let the request through */ }
  }
  const clean = (s) => s.replace(/[\r\n]+/g, ' ').trim();
  const name = clean(f('contact[Name]')), email = clean(f('contact[email]')), phone = clean(f('contact[Phone number]')), comment = f('contact[Comment]');
  if (!email || !EMAIL_RE.test(email) || email.length > 254 || (!comment && !name)) return fail('invalid', 422);
  if (comment.length > 5000 || name.length > 200) return fail('too_long', 422);

  if (!env.RESEND_API_KEY) return fail('not_configured', 503);

  const to = (env.CONTACT_TO || 'shop@heatica.com').split(',').map((s) => s.trim());
  const subject = `[heatica.com] ${(comment.split(/\r?\n/)[0].trim() || 'Contact form').slice(0, 90)}`;
  const text = [`Name: ${name}`, `E-mail: ${email}`, `Phone: ${phone}`, `Language: ${clean(f('lang'))}`, `Page: ${page}`, '', comment].join('\n');
  try {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, 'content-type': 'application/json' },
      body: JSON.stringify({ from: env.CONTACT_FROM || 'Heatica Website <onboarding@resend.dev>', to, reply_to: email, subject, text }),
    });
    if (!res.ok) return fail('send_failed', 502);
  } catch (e) {
    return fail('send_failed', 502);
  }
  return done();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (url.hostname.startsWith('www.')) {
      url.hostname = url.hostname.slice(4);
      return redirect(url.toString(), 301);
    }

    const contact = new RegExp(`^(/${LOCALE})?/contact/?$`).exec(path);
    if (contact) {
      if (request.method === 'POST') return handleContact(request, env, url);
      return redirect(`${url.origin}${contact[1] || ''}/pages/contact-us`, 302);
    }
    if (new RegExp(`^(/${LOCALE})?/localization/?$`).test(path)) {
      if (request.method === 'POST') return handleLocalization(request, url);
      return redirect(`${url.origin}/`, 302);
    }

    for (const [re, target, status, keepQuery = true] of REDIRECTS) {
      const m = re.exec(path);
      if (m) {
        const dest = target(m).replace(/\/{2,}/g, '/');
        return redirect(`${url.origin}${dest}${keepQuery ? url.search : ''}`, status);
      }
    }

    return env.ASSETS.fetch(request);
  },
};
