/* Quality — one company's scores with every part shown (shared by the Disclosure Hub's Quality tab and the "Quality" view
   of each company page on the Sankey site, listed in views.json):
     Piotroski F (nine pass / fail checks), Altman Z or Z'' with its weighted parts, Beneish M (eight indices; a statistical
     screen, not an accusation), shareholder yield, FCF yield before and after stock compensation, owner earnings,
     ROIC / incremental ROIC against a WACC, operating leverage with the fixed / variable cost regression, margin mean
     reversion and the sector's growth-adjusted EV/Sales line.
   Data: data/research/quality/c/<TICKER>.json (app/quality.py, branch research-quality).
   window.QualityView.render(el, {ticker, hub}) — hub: the path to the hub ('disclosures/' on the Sankey site, '' inside it). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 2) => (fin(v) ? (v < 0 ? '−' : '') + Math.abs(+v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const pct = (v, d = 1) => (fin(v) ? (v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? '$' + (a / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(0) + 'M' : '$' + Math.round(a).toLocaleString('en-US')); };
  const tk = (t) => String(t || '').toUpperCase().replace(/\./g, '-');
  const cache = {};
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.qv{display:grid;gap:14px}.qv .qv-card{border:1px solid var(--line,#d0d5dd);border-radius:8px;padding:12px 14px}
.qv h3{margin:0 0 6px;font-size:1rem}.qv .qv-big{font-size:1.6rem;font-weight:600;margin-right:8px}.qv .qv-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.qv table{border-collapse:collapse;width:100%;min-width:0!important;font-size:.86rem;table-layout:auto}.qv .qv-card{min-width:0;overflow:hidden}.qv td:first-child{min-width:0;font-weight:400}.qv th{position:static;white-space:normal}.qv td,.qv th{padding:3px 6px;border-bottom:1px solid var(--line,#e4e7ec);text-align:left;vertical-align:top}
.qv td.n,.qv th.n{text-align:right;font-variant-numeric:tabular-nums}.qv .ok{color:#17734a}.qv .bad{color:#b42318}.qv .na{color:#98a2b3}
.qv .zone-safe{color:#17734a}.qv .zone-grey{color:#b54708}.qv .zone-distress{color:#b42318}.qv svg{max-width:100%;height:auto}.qv .muted{opacity:.75}`;
    document.head.appendChild(s);
  }
  function load(hub, t) {
    const key = hub + t;
    if (!cache[key]) cache[key] = fetch(`${hub}data/research/quality/c/${encodeURIComponent(t)}.json`, { cache: 'no-cache' }).then((r) => {
      if (!r.ok) { const e = new Error(r.status === 404 ? 'No published Quality research file for this company. The reason is not reported; this does not establish a market-cap exclusion' : 'Quality research is temporarily unavailable (HTTP ' + r.status + ')'); e.status = r.status; throw e; }
      return r.json();
    }).catch((e) => { delete cache[key]; throw e; });
    return cache[key];
  }
  const mark = (p) => (p === true ? '<span class="ok">✓</span>' : p === false ? '<span class="bad">✗</span>' : '<span class="na">—</span>');
  function detail(d) {
    if (Array.isArray(d)) return d.map((x) => (fin(x) ? (Math.abs(x) >= 1e5 ? big(x).replace('$', '') : num(x, 3)) : '—')).join(' → ');
    return fin(d) ? num(d, 3) : '—';
  }
  function piotroski(m) {
    const f = m.piotroski;
    if (!f) return '<div class="qv-card"><h3>Piotroski F-score</h3><p class="muted">Needs two fiscal years of figures (not computed for banks, insurers and REITs).</p></div>';
    return `<div class="qv-card"><h3>Piotroski F-score</h3><p><span class="qv-big">${f.score}/9</span>${f.n < 9 ? `<span class="muted">${f.n} of 9 checks could be made</span>` : 'all nine checks made'}</p>
      <table><tbody>${f.signals.map((s) => `<tr><td>${mark(s.pass)}</td><td>${esc(s.label)}</td><td class="n">${esc(detail(s.detail))}</td></tr>`).join('')}</tbody></table>
      <p class="muted">Piotroski (2000): profitability (4), leverage and liquidity (3), efficiency (2); the latest fiscal year against the one before.</p></div>`;
  }
  function altman(m) {
    const z = m.altman;
    if (!z) return '<div class="qv-card"><h3>Altman Z-score</h3><p class="muted">Not computed (financial companies, or a balance-sheet figure missing).</p></div>';
    const W = z.model === 'Z' ? { wc_ta: 1.2, re_ta: 1.4, ebit_ta: 3.3, mve_tl: 0.6, sales_ta: 1.0 } : { wc_ta: 6.56, re_ta: 3.26, ebit_ta: 6.72, bve_tl: 1.05 };
    const L = { wc_ta: 'Working capital / assets', re_ta: 'Retained earnings / assets', ebit_ta: 'Operating income / assets', mve_tl: 'Market cap / liabilities', sales_ta: 'Sales / assets', bve_tl: 'Book equity / liabilities' };
    return `<div class="qv-card"><h3>Altman ${esc(z.model)}</h3><p><span class="qv-big zone-${esc(z.zone)}">${num(z.z)}</span><span class="zone-${esc(z.zone)}">${esc(z.zone)} zone</span></p>
      <table><thead><tr><th>Part</th><th class="n">Value</th><th class="n">Weight</th><th class="n">Adds</th></tr></thead><tbody>${Object.keys(W).map((k) => `<tr><td>${L[k]}</td><td class="n">${num(z.parts[k], 3)}</td><td class="n">${W[k]}</td><td class="n">${num(z.parts[k] * W[k], 2)}</td></tr>`).join('')}</tbody></table>
      <p class="muted">${z.model === 'Z' ? 'Manufacturers (Altman 1968): safe above 2.99, distress below 1.81.' : "Other companies (Altman's Z'', 1995): safe above 2.6, distress below 1.1."} A statistical model of distress, not a forecast.</p></div>`;
  }
  function beneish(m) {
    const b = m.beneish;
    if (!b) return '<div class="qv-card"><h3>Beneish M-score</h3><p class="muted">Not computed (financial companies, or receivables, PP&amp;E or current assets not tagged).</p></div>';
    const W = { dsri: 0.92, gmi: 0.528, aqi: 0.404, sgi: 0.892, depi: 0.115, sgai: -0.172, lvgi: -0.327, tata: 4.679 };
    const L = { dsri: 'Receivables vs sales (DSRI)', gmi: 'Gross margin (GMI)', aqi: 'Asset quality (AQI)', sgi: 'Sales growth (SGI)', depi: 'Depreciation (DEPI)', sgai: 'SG&A (SGAI)', lvgi: 'Leverage (LVGI)', tata: 'Accruals / assets (TATA)' };
    return `<div class="qv-card"><h3>Beneish M-score</h3><p><span class="qv-big ${b.flag ? 'bad' : 'ok'}">${num(b.m)}</span>${b.flag ? 'above −1.78: screens as a possible earnings manipulator' : 'below −1.78: no flag'}</p>
      <table><thead><tr><th>Index</th><th class="n">Value</th><th class="n">Weight</th></tr></thead><tbody>${Object.keys(W).map((k) => `<tr><td>${L[k]}${(b.neutral || []).includes(k) ? ' <span class="muted">(not tagged: set to 1)</span>' : ''}</td><td class="n">${num(b.idx[k], 3)}</td><td class="n">${W[k]}</td></tr>`).join('')}</tbody></table>
      <p class="muted">Beneish (1999), eight indices; M = −4.84 + Σ weight × index. A statistical screen, not an accusation.</p></div>`;
  }
  function yields(c) {
    const y = c.metrics.yields || {}, o = c.metrics.owner, mc = (c.row || {}).mcap;
    return `<div class="qv-card"><h3>Cash returned and cash earned</h3><table><tbody>
      <tr><td>Dividend yield</td><td class="n">${pct(y.div_y)}</td></tr><tr><td>Net buyback yield (buybacks − stock sold)</td><td class="n">${pct(y.bb_y)}</td></tr>
      <tr><td><b>Shareholder yield</b></td><td class="n"><b>${pct(y.sy)}</b></td></tr>
      <tr><td>Free-cash-flow yield</td><td class="n">${pct(y.fcf_y)}</td></tr><tr><td>… after stock-based compensation</td><td class="n">${pct(y.fcf_sbc_y)}</td></tr>
      ${o ? `<tr><td>Owner earnings (NI + D&amp;A − maintenance capex)</td><td class="n">${big(o.oe)}${mc ? ' · ' + pct(o.oe / mc) : ''}</td></tr>
      <tr><td class="muted">Maintenance capex (Greenwald: capex − PP&amp;E/sales × sales growth)</td><td class="n muted">${big(o.maint_capex)}</td></tr>` : ''}
      </tbody></table><p class="muted">Yields over the market cap ${big(mc)}; flows of the latest fiscal year.</p></div>`;
  }
  function roic(c) {
    const r = c.metrics.roic, w = c.metrics.wacc;
    if (!r && !w) return '';
    return `<div class="qv-card"><h3>Return on invested capital</h3><table><tbody>
      <tr><td>ROIC (NOPAT / average invested capital)</td><td class="n">${pct(r && r.roic)}</td></tr>
      <tr><td>Incremental ROIC${r && r.inc_years ? ` (over ${r.inc_years} years)` : ''}</td><td class="n">${pct(r && r.roic_inc)}</td></tr>
      <tr><td>WACC${w ? ` (${w.source === 'capm' ? `CAPM: β ${num(w.beta)}, equity ${pct(w.ke)}, debt ${pct(w.kd)}` : 'company WACC, Valuation research'})` : ''}</td><td class="n">${pct(w && w.wacc)}</td></tr>
      <tr><td><b>ROIC − WACC</b></td><td class="n"><b class="${fin(c.metrics.spread) ? (c.metrics.spread >= 0 ? 'ok' : 'bad') : ''}">${pct(c.metrics.spread)}</b></td></tr>
      </tbody></table><p class="muted">Invested capital: equity + debt − cash. NOPAT: operating income × (1 − tax rate).</p></div>`;
  }
  function scatter(points, f, v) {
    if (!points || points.length < 4) return '';
    const W = 300, H = 170, L = 46, B = 26, T = 8, R = 8;
    const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys, f + v * x0), y1 = Math.max(...ys, f + v * x1);
    const X = (x) => L + (x - x0) / ((x1 - x0) || 1) * (W - L - R), Y = (y) => T + (y1 - y) / ((y1 - y0) || 1) * (H - T - B);
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Quarterly operating cost against revenue with the fitted line">
      <line x1="${X(x0)}" y1="${Y(f + v * x0)}" x2="${X(x1)}" y2="${Y(f + v * x1)}" stroke="currentColor" stroke-opacity=".5"/>
      ${points.map((p) => `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3" fill="#1d4ed8"/>`).join('')}
      <text x="${L}" y="${H - 6}" font-size="10">revenue a quarter →</text><text x="2" y="${T + 10}" font-size="10">cost</text></svg>`;
  }
  function leverage(c) {
    const s = c.cost;
    if (!s) return '';
    return `<div class="qv-card"><h3>Operating leverage</h3><p><span class="qv-big">${s.dol != null ? num(s.dol, 1) + 'x' : '—'}</span>${s.reliable ? '' : '<span class="muted">fit not reliable</span>'}</p>
      <table><tbody><tr><td>Fixed costs a quarter</td><td class="n">${big(s.fixed_q)}</td></tr><tr><td>Variable cost per revenue dollar</td><td class="n">${pct(s.var_ratio)}</td></tr>
      <tr><td>Fit (R², quarters)</td><td class="n">${num(s.r2, 2)} · ${s.n}</td></tr></tbody></table>
      ${scatter(s.points, s.fixed_q, s.var_ratio)}<p class="muted">Operating cost (revenue − operating income) regressed on revenue; DOL = contribution margin / operating income at the latest quarter.</p></div>`;
  }
  function margins(c) {
    const m = c.margins;
    if (!m) return '';
    const hist = m.history || [], path = m.path || [];
    const vals = hist.map((h) => h[1]).concat(path, [m.sector_median]).filter(fin);
    const lo = Math.min(...vals), hi = Math.max(...vals), W = 300, H = 150, L = 40, T = 8, B = 20;
    const n = hist.length + path.length, X = (i) => L + i / Math.max(n - 1, 1) * (W - L - 8), Y = (v) => T + (hi - v) / ((hi - lo) || 1) * (H - T - B);
    const line = (arr, off) => arr.map((v, i) => `${i ? 'L' : 'M'}${X(i + off)},${Y(v)}`).join(' ');
    return `<div class="qv-card"><h3>Operating margin: mean reversion</h3><p>Trailing four quarters ${pct(m.margin)} · sector median ${pct(m.sector_median)} · four quarters out ${pct(path[path.length - 1])}</p>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Operating margin history and the reversion path">
      <line x1="${L}" x2="${W - 8}" y1="${Y(m.sector_median)}" y2="${Y(m.sector_median)}" stroke="currentColor" stroke-dasharray="3 3" stroke-opacity=".5"/>
      <path d="${line(hist.map((h) => h[1]), 0)}" fill="none" stroke="#1d4ed8" stroke-width="2"/>
      <path d="${line([hist.length ? hist[hist.length - 1][1] : m.margin].concat(path), hist.length - 1)}" fill="none" stroke="#b54708" stroke-width="2" stroke-dasharray="5 3"/></svg>
      <p class="muted">The gap to the sector median shrinks by a factor φ = ${num(m.phi, 3)} a quarter (pooled, estimated walk-forward). Dashed: the expected path.</p></div>`;
  }
  function line(c) {
    const r = c.row || {}, l = c.line;
    if (!fin(r.ev_s) || !l) return '';
    return `<div class="qv-card"><h3>Against the ${esc(c.sector_name || r.sector)} line</h3><table><tbody>
      <tr><td>EV / sales (trailing four quarters)</td><td class="n">${num(r.ev_s, 1)}x</td></tr>
      <tr><td>Growth + operating margin</td><td class="n">${num(r.r40, 0)} (${pct(r.growth)} + ${pct(r.margin)})</td></tr>
      <tr><td>The sector line at that score</td><td class="n">${num(r.line_ev_s, 1)}x</td></tr>
      <tr><td>Residual (log)</td><td class="n">${num(r.resid, 2)}</td></tr></tbody></table>
      <p class="muted">log(EV/Sales) = a + b × (growth % + margin %), all ${esc(c.sector_name || r.sector)} companies over $300M (R² ${num(l.r2, 2)}, ${l.n} companies). Below the line: cheaper than peers with the same growth and margin.</p></div>`;
  }
  function records(c) {
    const R = c.records || [];
    if (!R.length) return '';
    const K = [['rev', 'Revenue'], ['gp', 'Gross profit'], ['oi', 'Operating income'], ['ni', 'Net income'], ['ocf', 'Operating cash flow'], ['capex', 'Capex'], ['sbc', 'Stock comp'], ['buyback', 'Buybacks'], ['div', 'Dividends'], ['assets', 'Assets'], ['eq', 'Equity'], ['ltd', 'Long-term debt'], ['cash', 'Cash']];
    return `<div class="qv-card"><h3>The figures (fiscal years, from XBRL)</h3><div style="overflow-x:auto"><table><thead><tr><th></th>${R.map((r) => `<th class="n">${esc(r.end)}</th>`).join('')}</tr></thead>
      <tbody>${K.map(([k, l]) => `<tr><td>${l}</td>${R.map((r) => `<td class="n">${big(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`;
  }
  async function render(el, opt) {
    css();
    const hub = (opt && opt.hub) || '', t = tk(opt && opt.ticker);
    if (!t) { el.innerHTML = '<p class="muted">No ticker for this company.</p>'; return; }
    el.innerHTML = '<p class="muted">Reading the Quality research…</p>';
    let c;
    try { c = await load(hub, t); } catch (e) {
      if ((opt && opt.here && !opt.here()) || !el.isConnected) return;
      el.innerHTML = `<div class="qv-card"><h3>Quality research · ${esc(t)}</h3><p class="muted">${esc(e.message)}.</p><p>Piotroski, Altman and Beneish scores are unavailable in this view. The independent disclosure screen below does not replace these scores.</p><button type="button" data-quality-retry>Retry Quality research</button></div>`;
      el.querySelector('[data-quality-retry]').onclick = () => render(el, opt);
      if (opt && /^\d{1,10}$/.test(String(opt.cik)) && window.FFCompanyDisclosures) {
        const panel = document.createElement('div');
        el.appendChild(panel);
        await window.FFCompanyDisclosures.mount(panel, { cik: opt.cik, here: opt.here });
      } else {
        const link = document.createElement('a');
        link.href = `${hub}#hidden/${encodeURIComponent(t)}`;
        link.textContent = 'View independent Hidden Leverage & revenue-quality evidence →';
        el.appendChild(link);
      }
      return;
    }
    if (opt && opt.here && !opt.here()) return;
    const r = c.row || {};
    el.innerHTML = `<div class="qv"><div class="qv-card"><h3>${esc(r.name || t)} <span class="muted">${esc(t)} · ${esc(c.sector_name || r.sector || '')}</span></h3>
      <p class="muted">Fiscal year ended ${esc(r.fy_end || '—')} · market cap ${big(r.mcap)} · composite rank ${fin(r.comp_rank) ? Math.round(100 * r.comp_rank) + 'th percentile' : '—'}</p></div>
      <div class="qv-grid">${piotroski(c.metrics)}${altman(c.metrics)}${beneish(c.metrics)}</div>
      <div class="qv-grid">${yields(c)}${roic(c)}${leverage(c)}</div>
      <div class="qv-grid">${margins(c)}${line(c)}</div>${records(c)}
      <div class="qv-card"><h3>Revenue Quality / Cookie Jar screening</h3>
      <p class="muted">Receivable-versus-sales growth, contract assets, deferred revenue changes, cash conversion and recognition-policy filing leads. Independent SEC evidence, not a fraud allegation. No missing value is treated as zero.</p>
      <a href="${hub}#hidden/${encodeURIComponent(t)}">View original SEC evidence and review flags →</a></div>
      <p class="muted">Companies' own XBRL tags via the SEC frames API; prices: daily closes. Research, not investment advice.${hub ? ` <a href="${hub}#quality">All companies →</a>` : ''}</p></div>`;
  }
  window.QualityView = { render };
})();
