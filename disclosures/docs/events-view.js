/* Events — one stock's price with every disclosed event marked on it: insider purchases and sales (Form 4), 13F
   managers' new positions, adds, cuts and exits (by filing date), officials' trades (House, Senate), 8-Ks, the
   company's earnings filings and analysts' rating changes. Who did what, at what price, when.
   A shared view: window.EventsView.render(el, {cik, ticker, company, here, hub}) — the main site's company page
   (views.json → "Events") and anywhere in the hub. Data: holders/<TICKER>.json (the hub's per-ticker join),
   consensus/c/<cik>.json (daily prices, analysts' actions), market/history/t/<TICKER>.json (weekly closes) when there
   are no daily prices, and the site's company file for the earnings dates. CSS prefix ev2-. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v, d = 2) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), d) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v); return (v < 0 ? '−' : '') + (a >= 1e9 ? '$' + num(a / 1e9, 2) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 1) + 'M' : a >= 1e3 ? '$' + num(a / 1e3, 0) + 'K' : '$' + num(a, 0)); };
  const fileT = (t) => String(t || '').toUpperCase().replace(/\./g, '-');
  const ts = (s) => Date.parse(String(s).slice(0, 10) + 'T00:00:00Z');
  const day = (s) => (s ? String(s).slice(0, 10) : '—');
  const KINDS = { buy: ['Insider purchase', '#17734a'], sell: ['Insider sale', '#c0392b'], f13: ['13F managers', '#2a78d6'], off: ["Official's trade", '#8a4fd6'],
    k8: ['8-K', '#6b6a66'], earn: ['Earnings filing', '#d9822b'], rating: ['Rating change', '#b5446e'] };
  const get = (base, p) => fetch(base + p).then((r) => (r.ok ? r.json() : null)).catch(() => null);

  function css() {
    if (document.getElementById('ev2-css')) return;
    const s = document.createElement('style'); s.id = 'ev2-css';
    s.textContent = `.ev2 h3{margin:18px 0 6px;font-size:16px}.ev2-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45}
.ev2-svg{width:100%;height:auto;display:block;background:var(--surface,#fcfcfb);border:1px solid var(--line,#ddd);border-radius:10px}
.ev2-svg .g{stroke:var(--line,#e3e1db);stroke-width:1}.ev2-svg .ax{font:11.5px var(--sans,'IBM Plex Sans',Arial,sans-serif);fill:var(--muted,#777)}
.ev2-svg .px{fill:none;stroke:var(--ink,#222);stroke-width:1.6}.ev2-svg .mk{cursor:pointer}.ev2-svg .mk:hover{opacity:.75}
.ev2-keys{display:flex;flex-wrap:wrap;gap:6px 14px;margin:8px 0;font-size:13px}.ev2-keys label{display:inline-flex;gap:6px;align-items:center;cursor:pointer}
.ev2-keys i{width:10px;height:10px;border-radius:2px;display:inline-block}
.ev2-tbl{width:100%;border-collapse:collapse;font-size:13.5px}.ev2-tbl td,.ev2-tbl th{padding:6px 8px;border-bottom:1px solid var(--line,#e3e1db);text-align:left;vertical-align:top}
.ev2-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.ev2-wrap{overflow-x:auto}.ev2-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}`;
    document.head.appendChild(s);
  }

  // every event: {date, k, who, what, price, value, url}
  function events(H, cons, company) {
    const E = [];
    const add = (o) => { if (o.date) E.push(o); };
    for (const x of (H && H.insiders) || []) add({ date: day(x.date), k: x.code === 'P' ? 'buy' : x.code === 'S' ? 'sell' : 'sell', who: `${x.insider} (${x.title || x.role || 'insider'})`, what: `${x.code === 'P' ? 'bought' : 'sold'} ${num(x.shares)} shares${x.plan_10b5_1 ? ' · 10b5-1 plan' : ''}`, price: x.price, value: x.value, url: x.url });
    const by = new Map();                                     // 13F: one marker per filing date, every manager in it
    for (const x of (H && H.institutional) || []) if (x.filed && ['NEW', 'INCREASE', 'DECREASE'].includes(x.status)) { const g = by.get(x.filed) || []; g.push(x); by.set(x.filed, g); }
    for (const x of (H && H.exits) || []) if (x.filed) { const g = by.get(x.filed) || []; g.push(Object.assign({ status: 'EXIT' }, x)); by.set(x.filed, g); }
    for (const [d, g] of by) {
      const c = (s) => g.filter((x) => x.status === s).length;
      add({ date: day(d), k: 'f13', who: g.slice(0, 3).map((x) => x.manager).join(', ') + (g.length > 3 ? ` +${g.length - 3}` : ''),
        what: `13F: ${[c('NEW') ? c('NEW') + ' new' : '', c('INCREASE') ? c('INCREASE') + ' added' : '', c('DECREASE') ? c('DECREASE') + ' cut' : '', c('EXIT') ? c('EXIT') + ' sold out' : ''].filter(Boolean).join(', ')} (quarter ended ${day(g[0].period)})`,
        url: (g[0] || {}).source_url });
    }
    for (const o of (H && H.officials) || []) add({ date: day(o.date), k: 'off', who: `${o.person}${o.jurisdiction ? ' · ' + o.jurisdiction : ''}`, what: `${o.transaction_type || o.kind || 'transaction'}${o.amount_min != null ? ` · ${usd(o.amount_min, 0)}${o.amount_max ? '–' + usd(o.amount_max, 0) : '+'}` : ''}${o.filed_date ? ` · reported ${day(o.filed_date)}` : ''}`, url: o.source_url });
    for (const e of (H && H.events8k) || []) add({ date: day(e.filed), k: 'k8', who: '8-K', what: e.label || (e.items || []).join(', '), url: e.url });
    for (const q of (company && company.quarters) || []) add({ date: day(q.filed), k: 'earn', who: `${q.form} ${String(q.label || '').replace(/&amp;/g, '&')}`, what: `revenue ${big((q.headline || {}).revenue)}, net ${big((q.headline || {}).ni)}`, url: q.doc_url || q.index_url });
    for (const a of (((cons || {}).analysts || {}).actions) || []) add({ date: day(a.date), k: 'rating', who: a.firm, what: `${a.from && a.from !== a.to ? a.from + ' → ' : ''}${a.to || ''}${a.action ? ' (' + a.action + ')' : ''}${fin(a.target) ? ` · target ${usd(a.target, 0)}` : ''}`, price: null });
    return E.sort((a, b) => b.date.localeCompare(a.date));
  }

  function prices(cons, hist) {
    const P = ((cons && cons.prices) || []).filter((p) => p && fin(p[1])).map((p) => [ts(p[0]), +p[1]]);
    if (P.length >= 20) return { pts: P, kind: 'daily close' };
    if (hist && (hist.c || []).length && hist.start) {
      const t0 = ts(hist.start);
      return { pts: hist.c.map((v, i) => [t0 + i * 7 * 864e5, v]).filter((p) => fin(p[1])), kind: 'weekly close' };
    }
    return { pts: [], kind: '' };
  }

  function chart(px, E, on) {
    const W = 900, H = 340, L = 56, R = 16, T = 16, B = 34;
    if (px.pts.length < 2) return '<p class="ev2-sub">No price history on file for this stock: the events are listed below.</p>';
    const t0 = px.pts[0][0], t1 = px.pts[px.pts.length - 1][0];
    const vals = px.pts.map((p) => p[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
    const x = (t) => L + (t - t0) / Math.max(1, t1 - t0) * (W - L - R), y = (v) => T + (hi - v) / (hi - lo) * (H - T - B);
    const at = (t) => { let best = px.pts[0]; for (const p of px.pts) { if (p[0] <= t) best = p; else break; } return best[1]; };
    let g = '';
    for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4; g += `<line class="g" x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text class="ax" x="${L - 6}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${esc(usd(v, v >= 100 ? 0 : 2))}</text>`; }
    for (let i = 0; i <= 5; i++) { const t = t0 + (t1 - t0) * i / 5; g += `<text class="ax" x="${x(t).toFixed(1)}" y="${H - 12}" text-anchor="middle">${new Date(t).toISOString().slice(0, 7)}</text>`; }
    g += `<path class="px" d="${px.pts.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')}"/>`;
    E.forEach((e, i) => {
      const t = ts(e.date);
      if (!on.has(e.k) || t < t0 || t > t1) return;
      const cx = x(t), col = KINDS[e.k][1], tip = `${e.date} · ${e.who} · ${e.what}${fin(e.price) ? ' at ' + usd(e.price) : ''}`;
      if (e.k === 'k8' || e.k === 'earn' || e.k === 'rating') {                 // corporate events: a tick on the axis band
        const yy = e.k === 'earn' ? H - B - 6 : e.k === 'k8' ? T + 4 : T + 14;
        g += `<g class="mk" data-ev="${i}"><line x1="${cx.toFixed(1)}" x2="${cx.toFixed(1)}" y1="${yy - 5}" y2="${yy + 5}" stroke="${col}" stroke-width="2.4"/><title>${esc(tip)}</title></g>`;
      } else {
        const cy = y(fin(e.price) && e.price >= lo && e.price <= hi ? +e.price : at(t)), r = 5.5;
        const shape = e.k === 'buy' ? `M${cx},${cy - r} L${cx + r},${cy + r * 0.8} L${cx - r},${cy + r * 0.8} Z` : e.k === 'sell' ? `M${cx},${cy + r} L${cx + r},${cy - r * 0.8} L${cx - r},${cy - r * 0.8} Z`
          : e.k === 'off' ? `M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z` : null;
        g += `<g class="mk" data-ev="${i}">${shape ? `<path d="${shape}" fill="${col}" stroke="#fff" stroke-width="1"/>` : `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r}" fill="${col}" stroke="#fff" stroke-width="1"/>`}<title>${esc(tip)}</title></g>`;
      }
    });
    return `<svg class="ev2-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Price with disclosed events; the full list is in the table below">${g}</svg>`;
  }

  async function render(el, doc) {
    css();
    const hub = doc.hub || '', T = fileT(doc.ticker), cik = doc.cik;
    el.innerHTML = '<div class="ev2"><p class="ev2-sub">Reading the disclosures…</p></div>';
    const [H, cons, hist] = await Promise.all([T ? get(hub, `data/holders/${encodeURIComponent(String(doc.ticker).toUpperCase())}.json`) : null,
      cik ? get(hub, `data/consensus/c/${+cik}.json`) : null, T ? get(hub, `data/market/history/t/${T}.json`) : null]);
    if (doc.here && !doc.here()) return;
    const E = events(H, cons, doc.company), px = prices(cons, hist);
    const on = new Set(Object.keys(KINDS));
    const box = el.querySelector('.ev2');
    const draw = () => {
      const shown = E.filter((e) => on.has(e.k));
      box.innerHTML = `<h3>Who traded ${esc(doc.ticker || '')}, and when</h3>
        <p class="ev2-sub">${esc(px.kind ? `The ${px.kind}` : 'Price not on file')} with every disclosed event: insiders (Form 4, at their reported price), 13F managers (at the filing date — the trades happened during the quarter), officials (House and Senate reports, at the trade date), 8-Ks, earnings filings and analysts' rating changes. Hover a mark for the detail.</p>
        <div class="ev2-keys">${Object.entries(KINDS).map(([k, [l, c]]) => `<label><input type="checkbox" data-k="${k}"${on.has(k) ? ' checked' : ''}><i style="background:${c}"></i>${esc(l)} (${E.filter((e) => e.k === k).length})</label>`).join('')}</div>
        ${chart(px, E, on)}
        <h3>${num(shown.length)} events</h3>
        <div class="ev2-wrap"><table class="ev2-tbl"><thead><tr><th>Date</th><th>Who</th><th>What</th><th class="num">Price</th><th class="num">Value</th><th></th></tr></thead><tbody>
        ${shown.slice(0, 200).map((e) => `<tr><td>${esc(e.date)}</td><td><span class="ev2-dot" style="background:${KINDS[e.k][1]}"></span>${esc(e.who)}</td><td>${esc(e.what)}</td><td class="num">${fin(e.price) ? usd(e.price) : ''}</td><td class="num">${fin(e.value) ? big(e.value) : ''}</td><td>${/^https:\/\//.test(e.url || '') ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">Source ↗</a>` : ''}</td></tr>`).join('') || '<tr><td colspan="6">No disclosed events on file.</td></tr>'}
        </tbody></table></div>
        <p class="ev2-sub">Insider and official prices are the ones reported in the filings; 13F holdings are quarter-end positions, so their marks sit at the filing date, not at the trades. Not investment advice.</p>`;
      box.querySelectorAll('[data-k]').forEach((c) => c.addEventListener('change', () => { c.checked ? on.add(c.dataset.k) : on.delete(c.dataset.k); draw(); }));
    };
    draw();
  }
  window.EventsView = { render, events, prices };
})();
