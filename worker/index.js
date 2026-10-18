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
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });
}

async function handleContact(request, env, url) {
  let form;
  try { form = await request.formData(); } catch (e) { return json({ ok: false, error: 'bad_request' }, 400); }
  const f = (k) => (form.get(k) || '').toString().trim();
  const wantsJson = (request.headers.get('accept') || '').includes('application/json');
  const page = f('page').startsWith('/') ? f('page') : '/pages/contact-us';
  const done = () => wantsJson ? json({ ok: true }) : Response.redirect(`${url.origin}${page}?contact_posted=true#ContactForm`, 303);

  if (f('website')) return done();                       // honeypot: pretend success
  const name = f('contact[Name]'), email = f('contact[email]'), phone = f('contact[Phone number]'), comment = f('contact[Comment]');
  if (!email || !EMAIL_RE.test(email) || (!comment && !name)) return json({ ok: false, error: 'invalid' }, 422);
  if (comment.length > 5000) return json({ ok: false, error: 'too_long' }, 422);

  if (!env.RESEND_API_KEY) return json({ ok: false, error: 'not_configured' }, 503);

  const to = (env.CONTACT_TO || 'shop@heatica.com').split(',').map((s) => s.trim());
  const subject = `[heatica.com] ${(comment.split('\n')[0] || 'Contact form').slice(0, 90)}`;
  const text = [`Name: ${name}`, `E-mail: ${email}`, `Phone: ${phone}`, `Language: ${f('lang')}`, `Page: ${page}`, '', comment].join('\n');
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, 'content-type': 'application/json' },
    body: JSON.stringify({ from: env.CONTACT_FROM || 'Heatica Website <onboarding@resend.dev>', to, reply_to: email, subject, text }),
  });
  if (!res.ok) return json({ ok: false, error: 'send_failed', status: res.status }, 502);
  return done();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (url.hostname.startsWith('www.')) {
      url.hostname = url.hostname.slice(4);
      return Response.redirect(url.toString(), 301);
    }

    const contact = new RegExp(`^(/${LOCALE})?/contact/?$`).exec(path);
    if (contact) {
      if (request.method === 'POST') return handleContact(request, env, url);
      return Response.redirect(`${url.origin}${contact[1] || ''}/pages/contact-us`, 302);
    }

    for (const [re, target, status] of REDIRECTS) {
      const m = re.exec(path);
      if (m) {
        const dest = target(m).replace(/\/{2,}/g, '/');
        return Response.redirect(`${url.origin}${dest}${url.search}`, status);
      }
    }

    return env.ASSETS.fetch(request);
  },
};
