/* LBO & takeover (company page → Valuation & expectations; also the hub's Buyouts → One company).
   1. what a private buyer could pay: the LBO (lbo-model.js) at today's price plus a premium — IRR, the most a buyer
      could pay for its target return — with sliders for every assumption, the five years of debt paydown;
   2. what history says: the chance companies with its figures were bought within a year (research/lbo history.json:
      a logistic model on every merger proxy, tender-offer response and going-private statement since 2011), what
      drives it, where it sits on each figure, and the premiums buyers paid (merger proxies) applied to its price;
   3. what is being said: headlines, 8-Ks, 13Ds and announced deals.
   Data: data/research/lbo/c/<cik>.json, history.json (disclosures/app/lbo.py). */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const pc = (v, d = 0) => (fin(v) ? `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(100 * v).toFixed(d)}%` : '—');
  const pct = (v, d = 1) => (fin(v) ? `${(100 * v).toFixed(d)}%` : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? '$' + (a / 1e9).toFixed(1) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(0) + 'M' : '$' + Math.round(a)); };
  const usd = (v) => (fin(v) ? '$' + (+v).toFixed(v >= 100 ? 0 : 2) : '—');
  const KIND = { news: 'News', '8-K': '8-K', '8-K deal': '8-K deal', '13D': '13D', deal: 'Agreed deal', 'SC 13E3': 'Going private', DEFM14A: 'Merger proxy', 'SC 14D9': 'Tender offer' };
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.lbv{display:grid;gap:14px}.lbv .lb-card{border:1px solid var(--line,#d0d5dd);border-radius:8px;padding:12px 14px;min-width:0;overflow:hidden}
.lbv h3{margin:0 0 6px;font-size:1rem}.lbv .muted{opacity:.75;font-size:.82rem}.lbv .kpis{display:flex;flex-wrap:wrap;gap:10px 22px;margin:6px 0}
.lbv .kpi b{display:block;font-size:1.35rem;font-weight:600}.lbv .kpi span{font-size:.8rem;opacity:.75}.lbv .up{color:#17734a}.lbv .down{color:#b42318}
.lbv .grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px 18px}.lbv label.sl{display:grid;grid-template-columns:1fr auto;gap:2px 8px;font-size:.84rem;align-items:center}
.lbv label.sl input{grid-column:1/-1;width:100%}.lbv label.sl output{font-variant-numeric:tabular-nums;font-weight:600}
.lbv table{border-collapse:collapse;width:100%;min-width:0!important;font-size:.85rem}.lbv td,.lbv th{padding:4px 6px;border-bottom:1px solid var(--line,#e4e7ec);text-align:left;vertical-align:top;overflow-wrap:anywhere}
.lbv th{white-space:nowrap;position:static}.lbv td.n,.lbv th.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.lbv td.d{white-space:nowrap}
.lbv .tag{display:inline-block;font-size:.72rem;border-radius:999px;padding:0 7px;margin-right:4px;border:1px solid currentColor;opacity:.85;white-space:nowrap}
.lbv svg{display:block;width:100%;height:auto;max-width:760px}.lbv .flag{background:#fef0c7;color:#7a4a00;border-radius:6px;padding:6px 9px;font-size:.84rem;margin:6px 0}
.lbv button.reset{font:inherit;font-size:.8rem;border:1px solid var(--line,#d0d5dd);background:transparent;border-radius:999px;padding:2px 10px;cursor:pointer;color:inherit}
.lbv .bar{display:flex;align-items:center;gap:8px;font-size:.84rem;margin:3px 0}.lbv .bar span:first-child{min-width:150px}.lbv .bar b{display:inline-block;height:10px;border-radius:3px;background:#7a5af8}`;
    document.head.appendChild(s);
  }
  const cache = {};
  const getJSON = (u) => (cache[u] = cache[u] || fetch(u, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  const loadScript = (src) => new Promise((ok) => { const sc = document.createElement('script'); sc.src = src; sc.onload = ok; sc.onerror = ok; document.head.appendChild(sc); });

  const SLIDERS = [
    ['premium', 'Premium paid over today’s price', 0, 0.8, 0.01, (v) => pct(v, 0)],
    ['leverage', 'New debt, × EBITDA (at most)', 1, 8, 0.25, (v) => v.toFixed(2) + '×'],
    ['ratePct', 'Loan rate', 3, 14, 0.05, (v) => v.toFixed(2) + '%'],
    ['exitMultiple', 'Exit multiple, EV / EBITDA', 3, 30, 0.1, (v) => v.toFixed(1) + '×'],
    ['marginUp', 'EBITDA margin added by year 5 (cost cuts)', 0, 0.08, 0.0025, (v) => '+' + (100 * v).toFixed(2) + ' pts'],
    ['growth', 'Revenue growth a year', -0.05, 0.12, 0.0025, (v) => pc(v, 1)],
    ['target', 'Target IRR', 0.10, 0.30, 0.01, (v) => pct(v, 0)],
  ];

  function chart(res) {
    const Y = res.years, W = 620, H = 180, L = 52, B = 24, T = 10;
    const hi = Math.max(res.entry.debt, res.exit.equity, res.entry.equity, ...Y.map((y) => y.debt)) || 1;
    const bw = (W - L - 10) / (Y.length + 1) * 0.6, X = (k) => L + (k + 0.5) * (W - L - 10) / (Y.length + 1);
    const h = (v) => Math.max(0, v) / hi * (H - T - B);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Debt and equity over the holding period">`;
    const cols = [{ t: 0, debt: res.entry.debt, eq: res.entry.equity }, ...Y.map((y, k) => ({ t: y.t, debt: y.debt, eq: k === Y.length - 1 ? res.exit.equity : null }))];
    cols.forEach((c, k) => {
      const x = X(k) - bw / 2;
      svg += `<rect x="${x.toFixed(1)}" y="${(H - B - h(c.debt)).toFixed(1)}" width="${bw.toFixed(1)}" height="${h(c.debt).toFixed(1)}" fill="#d9480f" opacity=".75"><title>Debt ${big(c.debt)}</title></rect>`;
      if (c.eq != null) svg += `<rect x="${(x + bw * 0.55).toFixed(1)}" y="${(H - B - h(c.eq)).toFixed(1)}" width="${(bw * 0.45).toFixed(1)}" height="${h(c.eq).toFixed(1)}" fill="#3a9d6a"><title>Equity ${big(c.eq)}</title></rect>`;
      svg += `<text x="${X(k).toFixed(1)}" y="${H - 7}" font-size="11" text-anchor="middle">${c.t === 0 ? 'Buy' : 'Y' + c.t}</text>`;
    });
    svg += `<text x="${L - 6}" y="${T + 9}" font-size="10" text-anchor="end">${big(hi)}</text><text x="${L - 6}" y="${H - B}" font-size="10" text-anchor="end">0</text></svg>`;
    return svg + '<p class="muted"><span style="color:#d9480f">■</span> debt, paid down from free cash flow · <span style="color:#3a9d6a">■</span> the buyer’s equity, put in and taken out at the exit</p>';
  }

  function modelCard(d, M) {
    const i = d.inputs;
    if (!i) return `<div class="lb-card"><h3>What a private buyer could pay</h3><p class="muted">No LBO for ${esc(d.ticker)}: ${d.kind && /bank|insurer|reit/.test(d.kind) ? 'banks, insurers and REITs are not bought with borrowed money against EBITDA' : 'the trailing figures it needs are not on file'}.</p></div>`;
    const base = M.run(i, {}, d.rates);
    if (!base.ok) return `<div class="lb-card"><h3>What a private buyer could pay</h3><p class="muted">No LBO for ${esc(d.ticker)}: ${esc(base.why)}.</p></div>`;
    const init = { premium: M.DEFAULTS.premium, leverage: M.DEFAULTS.leverage, ratePct: +(100 * base.rate).toFixed(2), exitMultiple: +base.todayMultiple.toFixed(1),
      marginUp: 0, growth: +base.growth.toFixed(4), target: M.DEFAULTS.target };
    return `<div class="lb-card" data-lbo='${esc(JSON.stringify(init))}'><h3>What a private buyer could pay <span class="muted">a leveraged buyout, by fixed rules</span></h3>
      <div data-out></div>
      <details open><summary>Assumptions <button type="button" class="reset" data-reset>Reset</button></summary><div class="grid2">${SLIDERS.map(([k, l, lo, hi, st]) => {
        const v = Math.min(hi, Math.max(lo, init[k]));
        return `<label class="sl"><span>${esc(l)}</span><output data-o="${k}"></output><input type="range" min="${lo}" max="${hi}" step="${st}" value="${v}" data-k="${k}"></label>`;
      }).join('')}</div>
      <p class="muted">Today: ${usd(i.price)} a share · enterprise value ${big(i.price * i.shares + (i.debt || 0) - (i.cash || 0) + (i.claims || 0))} · trailing EBITDA ${big(i.ebitda)} (${pct(i.ebitda / i.revenue, 1)} of revenue) · debt ${big(i.debt)}, cash ${big(i.cash)}. Loan rate: SOFR ${fin(d.rates.base) ? d.rates.base.toFixed(2) + '%' : '—'} + high-yield B spread ${fin(d.rates.spread_b) ? d.rates.spread_b.toFixed(2) + '%' : '—'} + 0.50%.</p></details></div>`;
  }

  function outHTML(d, M, a) {
    const i = d.inputs, opts = { premium: a.premium, leverage: a.leverage, rate: a.ratePct / 100, exitMultiple: a.exitMultiple, marginUp: a.marginUp, growth: a.growth, target: a.target };
    const r = M.run(i, opts, d.rates), mp = M.maxPrice(i, opts, d.rates, a.target);
    if (!r.ok) return `<p class="muted">${esc(r.why)}</p>`;
    const good = r.irr >= a.target;
    const flags = (r.flags || []).map((f) => f === 'levered' ? 'Already carries more than 6× EBITDA in net debt: little room to borrow more (a finance arm or a past buyout).' : 'Larger than any leveraged buyout on record (enterprise value over $60 billion): the arithmetic works, a deal of this size is not likely.');
    return `${flags.map((f) => `<div class="flag">${esc(f)}</div>`).join('')}
      <div class="kpis"><div class="kpi"><b class="${good ? 'up' : 'down'}">${pct(r.irr, 1)}</b><span>buyer’s IRR at ${usd(r.price)} (${pc(r.premium)})</span></div>
        <div class="kpi"><b>${fin(r.moic) ? r.moic.toFixed(2) + '×' : '—'}</b><span>money multiple in ${r.years.length} years</span></div>
        <div class="kpi"><b class="${mp && mp.price > i.price ? 'up' : ''}">${mp && mp.price ? usd(mp.price) : '—'}</b><span>the most a share for ${pct(a.target, 0)} ${mp && mp.price ? `(${pc(mp.vsPrice)} vs today)` : mp ? '— ' + esc(mp.why || '') : ''}</span></div>
        <div class="kpi"><b>${r.entry.multiple.toFixed(1)}×</b><span>entry EV / EBITDA</span></div>
        <div class="kpi"><b>${pct(r.entry.equityShare, 0)}</b><span>paid in equity (${r.entry.leverage.toFixed(1)}× debt)</span></div>
        <div class="kpi"><b>${fin(r.paidDown) ? pct(r.paidDown, 0) : '—'}</b><span>of the debt repaid by year ${r.years.length}</span></div></div>
      ${chart(r)}
      <div style="overflow-x:auto"><table><thead><tr><th>Year</th><th class="n">Revenue</th><th class="n">EBITDA</th><th class="n">Interest</th><th class="n">Free cash flow</th><th class="n">Debt left</th></tr></thead><tbody>
      ${r.years.map((y) => `<tr><td>${y.t}</td><td class="n">${big(y.revenue)}</td><td class="n">${big(y.ebitda)}</td><td class="n">${big(y.interest)}</td><td class="n ${y.fcf < 0 ? 'down' : ''}">${big(y.fcf)}</td><td class="n">${big(y.debt)}</td></tr>`).join('')}</tbody></table></div>
      <p class="muted">${mp && mp.price && mp.price > i.price ? `A buyer could pay up to ${usd(mp.price)} and still make ${pct(a.target, 0)}: a floor under today’s ${usd(i.price)} if the market believes a buyer would come.` : `At these assumptions a financial buyer would not pay today’s price: the stock is valued above what borrowed money can carry.`} Real buyers add cost cuts, sales of assets and dividends paid out of new debt; the defaults leave them out, so this is a cautious estimate.</p>`;
  }

  function historyCard(d, H) {
    const h = d.history, m = H && H.models && H.models.acquired;
    if (!h || !h.acquired || !m) return '';
    const a = h.acquired, pv = h.private;
    const F = (H && H.features) || {};
    const dr = (a.drivers || []).map(([k, v]) => `<div class="bar"><span>${esc(F[k] || k)}</span><b style="width:${Math.min(160, Math.abs(v) * 90)}px;background:${v > 0 ? '#3a9d6a' : '#d9480f'}"></b>${v > 0 ? 'raises' : 'lowers'} the odds</div>`).join('');
    const where = Object.entries(H.lifts || {}).map(([k, qs]) => {
      const x = (h.features || {})[k];
      if (!fin(x)) return '';
      const qi = qs.findIndex((q) => x <= q[1]);
      const q = qs[qi < 0 ? qs.length - 1 : qi];
      const fmt = (v) => k === 'size' ? big(Math.pow(10, v)) : k === 'net_lev' ? v.toFixed(1) + '×' : pct(v, 0);
      return `<tr><td>${esc(F[k] || k)}</td><td class="n">${fmt(x)}</td><td class="n">${(qi < 0 ? 5 : qi + 1)} of 5</td><td class="n">${pct(q[2], 1)}</td></tr>`;
    }).join('');
    const P = H.premiums || {}, sec = (P.by_sector || []).find((s) => s[0] === d.sector);
    const lo = sec ? sec[3] : P.p25, hi = sec ? sec[4] : P.p75, md = sec ? sec[2] : P.median;
    const price = d.inputs && d.inputs.price;
    return `<div class="lb-card"><h3>What history says <span class="muted">every deal filing on EDGAR since 2011, against each company’s figures the year before</span></h3>
      <div class="kpis"><div class="kpi"><b>${pct(a.p, 1)}</b><span>chance of being bought within a year (companies like it, history)</span></div>
        <div class="kpi"><b>${fin(a.lift) ? a.lift.toFixed(1) + '×' : '—'}</b><span>the average company (${pct(m.base, 1)} a year)</span></div>
        <div class="kpi"><b>${a.decile} of 10</b><span>decile among all company-years</span></div>
        ${pv ? `<div class="kpi"><b>${pct(pv.p, 2)}</b><span>chance of a going-private deal</span></div>` : ''}</div>
      ${dr ? `<p class="muted">What moves its odds most:</p>${dr}` : ''}
      ${where ? `<div style="overflow-x:auto"><table><thead><tr><th>Figure (fiscal ${esc(h.year)})</th><th class="n">${esc(d.ticker)}</th><th class="n">Quintile</th><th class="n">Bought within a year, that quintile</th></tr></thead><tbody>${where}</tbody></table></div>` : ''}
      ${fin(md) ? `<p>Premiums buyers paid${sec ? ` in ${esc(d.sector)}` : ''}: median <b>${md.toFixed(0)}%</b>, middle half ${lo.toFixed(0)}–${hi.toFixed(0)}% (${sec ? sec[1] : P.n} merger proxies)${fin(price) ? ` — on today’s ${usd(price)}, a bid of about <b>${usd(price * (1 + lo / 100))}–${usd(price * (1 + hi / 100))}</b>` : ''}.</p>` : ''}
      <p class="muted">Tested out of time: trained on ${esc((m.train_years || []).join('–'))}, it ranked ${esc((m.test_years || []).join('–'))} with an AUC of ${fin(m.auc_test) ? m.auc_test.toFixed(2) : '—'} (0.5 is a coin toss); the top tenth was bought ${fin(m.top_decile_rate) && fin(m.base_test) ? (m.top_decile_rate / m.base_test).toFixed(1) + '× as often as the average' : '—'}. A base rate, not a forecast: most companies with high odds are never bought.</p></div>`;
  }

  function rumorCard(d) {
    const R = d.rumors || [];
    if (!R.length) return `<div class="lb-card"><h3>What is being said</h3><p class="muted">Nothing on file: no headline about a sale or an approach, no 8-K about strategic alternatives or a proposal, no 13D seeking a sale, no deal filing in the last year.</p></div>`;
    return `<div class="lb-card"><h3>What is being said <span class="muted">signal score ${fin(d.rumor_score) ? d.rumor_score.toFixed(1) : '—'} (recent weigh more)</span></h3><div style="overflow-x:auto"><table><tbody>
      ${R.slice(0, 15).map((x) => `<tr><td class="d">${esc(x.date || '')}</td><td><span class="tag">${esc(KIND[x.kind] || x.kind)}</span>${x.role === 'buyer' ? '<span class="tag">as the buyer</span>' : ''}${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.text)}</a>` : esc(x.text)}${x.source && x.kind === 'news' ? ` <span class="muted">— ${esc(x.source)}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>
      <p class="muted">Headlines from news searches for sales, approaches and take-private offers (the headline and a link only), the company’s 8-Ks about strategic alternatives, proposals or special committees, 13Ds whose purpose speaks of a sale or a proposal, and deal filings. A headline is not a deal; most reported talks end without one.</p></div>`;
  }

  function bind(el, d, M) {
    const card = el.querySelector('[data-lbo]');
    if (!card) return;
    const init = JSON.parse(card.dataset.lbo);
    const out = card.querySelector('[data-out]');
    const read = () => { const a = {}; card.querySelectorAll('input[data-k]').forEach((x) => { a[x.dataset.k] = +x.value; }); return a; };
    const draw = () => {
      const a = read();
      SLIDERS.forEach(([k, , , , , f]) => { const o = card.querySelector(`[data-o="${k}"]`); if (o) o.textContent = f(a[k]); });
      out.innerHTML = outHTML(d, M, a);
    };
    card.querySelectorAll('input[data-k]').forEach((x) => { x.oninput = draw; });
    card.querySelector('[data-reset]').onclick = (e) => { e.preventDefault(); card.querySelectorAll('input[data-k]').forEach((x) => { x.value = init[x.dataset.k]; }); draw(); };
    draw();
  }

  async function render(el, opt) {
    css();
    const o = opt || {}, hub = o.hub || '', cik = String(o.cik || '').replace(/^0+/, '');
    el.innerHTML = '<p class="muted">Working out what a buyer could pay…</p>';
    if (!global.FFLbo) await loadScript(`${hub}lbo-model.js`);
    const [d, H] = await Promise.all([getJSON(`${hub}data/research/lbo/c/${cik}.json`), getJSON(`${hub}data/research/lbo/history.json`)]);
    if ((o.here && !o.here()) || !el.isConnected) return;
    const M = global.FFLbo;
    if (!d || !M) { el.innerHTML = '<div class="lbv"><div class="lb-card"><h3>LBO & takeover</h3><p class="muted">Nothing on file for this company yet: no figures for a buyout model, no history score, no rumors.</p></div></div>'; return; }
    const head = `<div class="lb-card"><h3>${esc(d.name)} <span class="muted">${esc(d.ticker)} · LBO & takeover</span></h3><p class="muted">Three angles on a takeover: what a private-equity buyer could pay with borrowed money, how often companies like it were bought in the past, and what is being said now. Fixed rules, no language model. ${hub ? `<a href="${hub}#buyouts">Every company →</a>` : ''}</p></div>`;
    el.innerHTML = `<div class="lbv">${head}${modelCard(d, M)}${historyCard(d, H)}${rumorCard(d)}</div>`;
    bind(el, d, M);
  }
  global.LBOView = { render };
})(typeof window !== 'undefined' ? window : globalThis);
