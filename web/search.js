/* Global search: Ctrl/⌘+K (or "/") opens a palette over everything the site knows — the companies on the site and
   every SEC-registered company with a ticker (data/index.json, data/companies.json), 13F managers, officials and ETFs
   from the Disclosure Hub (data/search.json, written by scripts/hub_extras.py at build time), and the site's pages.
   The header search box shows the hub's people and funds under its company results (app.js setupSearch calls
   FFSearch.moreHTML). Matching: exact ticker, ticker prefix, word prefixes, then a fuzzy in-order match. */
(function (root) {
  'use strict';
  const U = root.FFUx;
  let IX = null, loading = null;
  const PAGES = [['Latest filings', '#home'], ['Sectors', '#sectors'], ['Follow feed', '#feed'], ['Custom charts', '#chart'], ['Alerts & account', '#account'],
    ['Method', '#method'], ['Disclosures: signals', 'disclosures/#signals'], ['Disclosures: 13F flows', 'disclosures/#flows'],
    ["Disclosures: officials' trades", 'disclosures/#trades'], ['Disclosures: insider trades', 'disclosures/#insiders'], ['Disclosures: 8-K events', 'disclosures/#events'],
    ['Disclosures: smart money', 'disclosures/#smart'], ['Disclosures: all flows', 'disclosures/#allflows'], ['Disclosures: ETFs', 'disclosures/#etf'],
    ['Disclosures: consensus', 'disclosures/#consensus'], ['Disclosures: options', 'disclosures/#options'], ['Disclosures: rotation', 'disclosures/#rotation'],
    ['Disclosures: short interest', 'disclosures/#shorts'], ['Disclosures: 13D / 13G stakes', 'disclosures/#stakes'], ['Disclosures: debt & rates', 'disclosures/#debt']];

  function load() {
    if (IX) return Promise.resolve(IX);
    if (!loading) {
      loading = Promise.all([U.site('index.json'), U.site('search.json'), U.site('companies.json')]).then(([ix, sx, all]) => {
        const site = ((ix && ix.companies) || []).map((c) => ({ k: 'company', id: +c.cik, tk: c.ticker || '', name: U.dec(c.name), rev: c.revenue || 0, href: `#c-${c.cik}` }));
        const have = new Set(site.map((c) => c.id));
        const sec = ((all && all.companies) || []).filter((r) => !have.has(+r[0])).map((r, i) => ({ k: 'company', id: +r[0], tk: r[1] || '', name: r[2] || '', rev: -i, off: true, href: `#c-${r[0]}` }));
        const sxx = sx || {};
        const mgr = (sxx.managers || []).map((r) => ({ k: 'manager', id: r[0], tk: '', name: r[2] || r[1], sub: r[2] && r[1] !== r[2] ? r[1] : '', w: r[3] || 0, href: `disclosures/#holdings/${r[0]}` }));
        const off = (sxx.officials || []).map((r) => ({ k: 'official', id: r[0], tk: '', name: r[0], sub: [r[1], r[2] ? `${r[2]} trades` : ''].filter(Boolean).join(' · '), w: r[2] || 0, href: `disclosures/#trades/${encodeURIComponent(r[0])}` }));
        const etf = (sxx.etfs || []).map((r) => ({ k: 'etf', id: r[0], tk: r[0], name: r[1] || r[0], w: r[2] || 0, href: `disclosures/#etf/${encodeURIComponent(r[0])}` }));
        const pages = PAGES.map(([n, h]) => ({ k: 'page', id: h, tk: '', name: n, href: h }));
        IX = { site, sec, mgr, off, etf, pages };
        return IX;
      });
    }
    return loading;
  }

  // a match score (higher is better), 0 = no match
  function score(e, q) {
    if (!q) return 0;
    const tk = (e.tk || '').toLowerCase(), name = (e.name || '').toLowerCase();
    if (tk && tk === q) return 1000;
    if (tk && tk.replace(/[.-]/g, '') === q.replace(/[.-]/g, '')) return 950;
    if (tk && tk.startsWith(q)) return 800 - tk.length;
    if (name === q) return 900;
    if (name.startsWith(q)) return 700;
    const words = name.split(/[^a-z0-9&]+/).filter(Boolean);
    const parts = q.split(/\s+/).filter(Boolean);
    if (parts.every((p) => words.some((w) => w.startsWith(p)))) return 600 - words.length;
    if (name.includes(q)) return 400;
    let i = 0;                                          // fuzzy: every character, in order
    for (const ch of name) { if (ch === q[i]) i++; if (i === q.length) break; }
    return i === q.length && q.length >= 3 ? 100 - (name.length - q.length) * 0.1 : 0;
  }
  function find(q, per = 6) {
    q = String(q || '').trim().toLowerCase();
    if (!IX || !q) return [];
    const pick = (list, n, tie) => list.map((e) => [score(e, q), e]).filter((x) => x[0] > 0)
      .sort((a, b) => b[0] - a[0] || tie(b[1]) - tie(a[1])).slice(0, n).map((x) => x[1]);
    const co = pick(IX.site, per, (e) => e.rev);
    const more = co.length < per ? pick(IX.sec, per - co.length, (e) => e.rev) : [];
    return [['Companies', co.concat(more)], ['13F managers', pick(IX.mgr, 4, (e) => e.w)], ['Officials', pick(IX.off, 4, (e) => e.w)],
      ['ETFs', pick(IX.etf, 4, (e) => e.w)], ['Pages', pick(IX.pages, 3, () => 0)]].filter((g) => g[1].length);
  }
  const KIND = { company: '', manager: '13F', official: 'Official', etf: 'ETF', page: 'Page' };
  const row = (e, i, hi) => `<a href="${U.esc(e.href)}" class="${i === hi ? 'hi' : ''}${e.off ? ' off' : ''}" data-i="${i}">${e.tk ? `<span class="mono">${U.esc(e.tk)}</span>` : `<span class="fx-kind">${KIND[e.k]}</span>`}<span>${U.esc(e.name)}${e.sub ? ` <small class="muted">${U.esc(e.sub)}</small>` : ''}</span>${e.off ? '<span class="tag">no chart yet</span>' : ''}</a>`;

  // the header box: hub people and funds under the company results (never companies: app.js lists those)
  function moreHTML(q) {
    if (!IX) { load(); return ''; }
    const groups = find(q, 0).filter((g) => g[0] !== 'Companies' && g[0] !== 'Pages');
    return groups.map(([h, list]) => `<div class="fx-sg">${U.esc(h)}</div>` + list.map((e) => row(e, -1, -2)).join('')).join('');
  }

  // ---------- the palette ----------
  let dlg = null;
  function open(initial) {
    if (dlg) { dlg.querySelector('input').focus(); return; }
    dlg = document.createElement('div');
    dlg.className = 'fx-palette';
    dlg.setAttribute('role', 'dialog');
    dlg.setAttribute('aria-modal', 'true');
    dlg.setAttribute('aria-label', 'Search everything');
    dlg.innerHTML = `<div class="fx-pal-box"><input type="search" class="fx-pal-in" placeholder="Company, ticker, 13F manager, official, ETF or page" aria-label="Search everything" autocomplete="off">
      <div class="fx-pal-list" role="listbox"><div class="muted fx-pal-hint">Type to search companies, 13F managers, officials and ETFs. ↑↓ to move, Enter to open, Esc to close.</div></div>
      <div class="fx-pal-foot muted">Ctrl/⌘ K anywhere · data: SEC EDGAR via this site and the Disclosure Hub</div></div>`;
    document.body.appendChild(dlg);
    const input = dlg.querySelector('input'), list = dlg.querySelector('.fx-pal-list');
    let flat = [], hi = 0;
    const draw = () => {
      const groups = find(input.value, 6);
      flat = groups.flatMap((g) => g[1]);
      hi = Math.min(hi, Math.max(0, flat.length - 1));
      let i = 0;
      list.innerHTML = groups.map(([h, l]) => `<div class="fx-sg">${U.esc(h)}</div>` + l.map((e) => row(e, i++, hi)).join('')).join('') ||
        (input.value.trim() ? '<div class="muted fx-pal-hint">Nothing found.</div>' : '<div class="muted fx-pal-hint">Type to search companies, 13F managers, officials and ETFs.</div>');
    };
    load().then(draw);
    input.addEventListener('input', () => { hi = 0; load().then(draw); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!flat.length) return;
        hi = (hi + (e.key === 'ArrowDown' ? 1 : flat.length - 1)) % flat.length;
        list.querySelectorAll('a').forEach((a) => a.classList.toggle('hi', +a.dataset.i === hi));
        const cur = list.querySelector('a.hi'); if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (flat[hi]) { go(flat[hi].href); }
      } else if (e.key === 'Escape') close();
    });
    list.addEventListener('click', (e) => { if (e.target.closest('a')) close(); });
    dlg.addEventListener('mousedown', (e) => { if (e.target === dlg) close(); });
    if (initial) input.value = initial;
    input.focus();
  }
  function go(href) {
    close();
    if (/^#/.test(href)) location.hash = href.slice(1); else location.href = href;
  }
  function close() { if (dlg) { dlg.remove(); dlg = null; } }

  function setup() {
    if (typeof document === 'undefined') return;
    document.addEventListener('keydown', (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || '') || (e.target && e.target.isContentEditable);
      if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) { e.preventDefault(); open(); }
      else if (e.key === '/' && !typing && !dlg) { e.preventDefault(); open(); }
    });
    const b = document.getElementById('palette-btn');
    if (b) b.addEventListener('click', () => open());
    const q = document.getElementById('q');
    if (q) q.addEventListener('focus', () => load(), { once: true });
  }
  root.FFSearch = { load, find, score, moreHTML, open, close, _setIndex: (ix) => { IX = ix; } };
  if (typeof module !== 'undefined') module.exports = root.FFSearch;
  else setup();
})(typeof globalThis !== 'undefined' ? globalThis : this);
