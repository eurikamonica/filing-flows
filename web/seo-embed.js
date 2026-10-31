/* The interactive charts on the search pages (scripts/seo_charts.py → <section class="seo-live" data-kind=…>): each is
   drawn when it scrolls into view, by the same code as the app — the money flow lab (flowlab.js), the Asian customers
   and suppliers (asia-links.js), the Disclosure Hub's company views (disclosures/views.json: rotation, quality, fair
   value, outlook …) and the industry's money flow. A view that cannot draw removes its section. */
(function () {
  'use strict';
  const BASE = window.FF_BASE || '';
  const loaded = {};
  const load = (src) => loaded[src] || (loaded[src] = new Promise((ok, bad) => {
    const s = document.createElement('script');
    s.src = src; s.onload = ok; s.onerror = () => bad(new Error(src));
    document.head.appendChild(s);
  }));
  let views = null;
  const getViews = () => views || (views = fetch(BASE + 'disclosures/views.json').then((r) => (r.ok ? r.json() : [])).catch(() => []));
  let company = {};
  const getCompany = (cik) => company[cik] || (company[cik] = fetch(BASE + 'data/c/' + cik + '.json').then((r) => (r.ok ? r.json() : null)).catch(() => null));
  const gone = (el) => el.remove();
  async function draw(el) {
    const d = el.dataset, kind = d.kind, body = document.createElement('div');
    const live = () => document.body.contains(el);
    try {
      if (kind === 'flowlab') {
        if (!window.FFFlowLab) return gone(el);
        el.innerHTML = ''; el.appendChild(body);
        await window.FFFlowLab.company(body, { cik: d.cik, ticker: d.ticker, here: live });
        if (!body.querySelector('svg')) gone(el);
      } else if (kind === 'asia') {
        if (!window.FFAsia) return gone(el);
        body.hidden = true; el.innerHTML = ''; el.appendChild(body);
        await window.FFAsia.company(body, d.cik, document.querySelector('h1') ? document.querySelector('h1').textContent.split(' (')[0] : '');
        if (body.hidden) gone(el);
      } else if (kind === 'industry') {
        if (!window.FFFlowLab) return gone(el);
        const h = el.querySelector('h2');
        el.innerHTML = ''; if (h) el.appendChild(h); el.appendChild(body);
        window.FFFlowLab.industry(body, { sic: d.sic, sector: d.sector, here: live });
      } else if (kind.startsWith('hub:')) {
        const v = (await getViews()).find((x) => x.id === kind.slice(4));
        if (!v) return gone(el);
        await load(BASE + 'disclosures/' + v.script);
        const V = window[v.global];
        if (!V || !V.render) return gone(el);
        const c = await getCompany(d.cik);
        const h = el.querySelector('h2');
        el.innerHTML = ''; if (h) el.appendChild(h); el.appendChild(body);
        await V.render(body, { cik: +d.cik, ticker: d.ticker, company: c, here: live, hub: BASE + 'disclosures/', quiet: true });
        if (!body.textContent.trim()) gone(el);
      }
    } catch (e) { gone(el); }
  }
  function start() {
    const els = Array.from(document.querySelectorAll('.seo-live'));
    if (!('IntersectionObserver' in window)) { els.forEach(draw); return; }
    const io = new IntersectionObserver((ents) => ents.forEach((en) => { if (en.isIntersecting) { io.unobserve(en.target); draw(en.target); } }), { rootMargin: '400px' });
    els.forEach((el) => io.observe(el));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
