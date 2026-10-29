/* Quality — one company's scores with every part shown (shared by the Disclosure Hub's Quality tab and the "Quality" view
   of each company page on the Sankey site, listed in views.json):
     Piotroski F (nine pass / fail checks), Altman Z or Z'' with its weighted parts, Beneish M (eight indices; a statistical
     screen, not an accusation), shareholder yield, FCF yield before and after stock compensation, owner earnings,
     ROIC / incremental ROIC against a WACC, operating leverage with the fixed / variable cost regression, margin mean
     reversion and the sector's growth-adjusted EV/Sales line; Quality Minus Junk, the Dechow F-score, Montier's C-score,
     discretionary accruals, the stability and persistence of earnings, taxes, goodwill and the non-GAAP gap.
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
.qv .qv-zbar{display:inline-block;position:relative;width:100%;height:8px;background:var(--line,#e4e7ec);border-radius:4px;vertical-align:middle}.qv .qv-zbar i{position:absolute;top:0;bottom:0;border-radius:4px}
.qv details summary{cursor:pointer;margin:6px 0}.qv td,.qv th{white-space:normal;overflow-wrap:anywhere}.qv td.n,.qv th.n{white-space:nowrap;overflow-wrap:normal;padding-left:8px}.qv .zone-safe{color:#17734a}.qv .zone-grey{color:#b54708}.qv .zone-distress{color:#b42318}.qv svg{max-width:100%;height:auto}.qv .muted{opacity:.75}`;
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
  // ---- quality_more.py: Quality Minus Junk, manipulation screens, stability and persistence, taxes, goodwill, non-GAAP
  const pc = (v) => Math.min(99, Math.max(1, Math.round(100 * v)));
  const ord = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
  const sgn = (v, d = 2) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(+v).toFixed(d) : '—');
  const zbar = (z) => {
    if (!fin(z)) return '';
    const w = Math.min(Math.abs(z), 3) / 3 * 50;
    return `<span class="qv-zbar"><i style="${z >= 0 ? 'left:50%' : `left:${50 - w}%`};width:${w}%;background:${z >= 0 ? '#17734a' : '#b42318'}"></i></span>`;
  };
  const QMJ_L = {
    gpoa: 'Gross profit / assets', roe: 'Return on equity', roa: 'Return on assets', cfoa: 'Operating cash flow / assets', gmar: 'Gross margin', acc: 'Accruals / assets (low is better)',
    d_gpoa: 'Change in gross profit / assets', d_roe: 'Change in ROE', d_roa: 'Change in ROA', d_cfoa: 'Change in cash flow / assets', d_gmar: 'Change in gross margin',
    beta: 'Beta (low is safer)', ivol: 'Idiosyncratic volatility (low is safer)', lev: 'Debt / assets (low is safer)', evol: 'Volatility of ROE (low is safer)', z: 'Altman Z (high is safer)',
    eiss: 'Net share issuance (low is better)', diss: 'Net debt issuance / assets (low is better)', npop: 'Net payout / profits, five years',
  };
  const QMJ_P = { profitability: ['gpoa', 'roe', 'roa', 'cfoa', 'gmar', 'acc'], growth: ['d_gpoa', 'd_roe', 'd_roa', 'd_cfoa', 'd_gmar'], safety: ['beta', 'ivol', 'lev', 'evol', 'z'], payout: ['eiss', 'diss', 'npop'] };
  const PILLAR = { profitability: 'Profitability', growth: 'Growth', safety: 'Safety', payout: 'Payout' };
  function qmjCard(mo) {
    const q = mo.qmj, x = mo.qmj_inputs || {};
    if (!q) return '<div class="qv-card"><h3>Quality Minus Junk</h3><p class="muted">Not enough figures for three of the four pillars.</p></div>';
    const fmtv = (k, v) => (['beta', 'z', 'npop'].includes(k) ? num(v, 2) : k === 'eiss' ? pct(v, 1) : pct(v, 1));
    return `<div class="qv-card"><h3>Quality Minus Junk</h3><p><span class="qv-big">${fin(q.rank) ? ord(pc(q.rank)) : '—'}</span>percentile of all companies${fin(q.sector_rank) ? ` · ${ord(pc(q.sector_rank))} in its sector` : ''} <span class="muted">(z ${sgn(q.qmj)})</span></p>
      <table><tbody>${Object.keys(PILLAR).map((p) => `<tr><td><b>${PILLAR[p]}</b></td><td class="n">${sgn(q[p])}</td><td style="width:40%">${zbar(q[p])}</td></tr>`).join('')}</tbody></table>
      <details><summary>The ${Object.values(QMJ_P).flat().length} measures behind it</summary><table><tbody>${Object.entries(QMJ_P).map(([p, ks]) => `<tr><td colspan="2" class="muted">${PILLAR[p]}${p === 'growth' && x.growth_years ? ` (a year, over ${x.growth_years} years)` : ''}</td></tr>`
        + ks.map((k) => `<tr><td>${QMJ_L[k]}</td><td class="n">${fin(x[k]) ? fmtv(k, x[k]) : '—'}</td></tr>`).join('')).join('')}</tbody></table></details>
      <p class="muted">Asness, Frazzini &amp; Pedersen (2019): each measure ranked across every company over $300M and turned into a z-score; a pillar averages its measures, QMJ averages the pillars (three of four needed). Quality stocks have tended to earn more than junk ones over long periods, not every year.</p></div>`;
  }
  const BAND = { normal: 'ok', 'above normal': '', substantial: 'bad', high: 'bad' };
  function manipCard(mo) {
    const d = mo.dechow, c = mo.cscore, j = mo.jones;
    const DL = { rsst_acc: 'RSST accruals (working capital, long-term operating and financial assets, change / assets)', ch_rec: 'Change in receivables / assets', ch_inv: 'Change in inventory / assets',
      soft_assets: 'Soft assets (not PP&amp;E or cash) / assets', ch_cs: 'Change in cash sales', ch_roa: 'Change in return on assets', issue: 'Shares or debt issued this year (1 = yes)' };
    const dh = d ? `<p><span class="qv-big ${BAND[d.band] || ''}">${num(d.f, 2)}</span>${esc(d.band)} risk · probability ${pct(d.prob, 2)}</p>
      <table><thead><tr><th>Input</th><th class="n">Value</th><th class="n">Weight</th></tr></thead><tbody>${Object.keys(DL).map((k) => `<tr><td>${DL[k]}</td><td class="n">${num(d.x[k], 3)}</td><td class="n">${d.w[k]}</td></tr>`).join('')}</tbody></table>
      ${(d.assumed || []).length ? `<p class="muted">Not tagged, assumed: ${esc(d.assumed.join('; '))}.</p>` : ''}`
      : '<p class="muted">Not computed (financial companies, or receivables, PP&amp;E or liabilities not tagged for two years).</p>';
    const ch = c ? `<p><span class="qv-big ${c.score >= 4 ? 'bad' : c.score <= 1 ? 'ok' : ''}">${c.score}/${c.n}</span>warning signs present</p>
      <table><tbody>${c.signs.map((s) => `<tr><td>${s.on === true ? '<span class="bad">●</span>' : s.on === false ? '<span class="ok">○</span>' : '<span class="na">—</span>'}</td><td>${esc(s.label)}</td><td class="n">${esc(Array.isArray(s.detail) ? s.detail.map((v) => (fin(v) ? (Math.abs(v) >= 1e5 ? big(v) : num(v, 2)) : '—')).join(' → ') : fin(s.detail) ? pct(s.detail) : '—')}</td></tr>`).join('')}</tbody></table>`
      : '<p class="muted">Fewer than four of the six signs can be read from the tags.</p>';
    const jl = j && j.latest;
    const jh = jl ? `<p><span class="qv-big ${fin(j.sector_pct) && j.sector_pct >= 0.9 ? 'bad' : ''}">${sgn(jl.da, 3)}</span>of last year's assets · larger in size than ${fin(j.sector_pct) ? pc(j.sector_pct) + '%' : '—'} of its sector</p>
      <table><tbody><tr><td>Total accruals (net income − operating cash flow) / assets</td><td class="n">${num(jl.ta, 3)}</td></tr><tr><td>Expected by the model (revenue, receivables, PP&amp;E, ROA)</td><td class="n">${num(jl.na, 3)}</td></tr>
      <tr><td><b>Discretionary (the rest)</b></td><td class="n"><b>${num(jl.da, 3)}</b></td></tr><tr><td class="muted">Fit: ${esc(String(jl.group).replace('|', ', fiscal '))} · ${jl.n} companies · R²</td><td class="n muted">${num(jl.r2, 2)}</td></tr></tbody></table>
      ${(j.history || []).length > 1 ? `<p class="muted">By year: ${j.history.map((h) => `${esc(String(h[0]).slice(0, 4))} ${sgn(h[1], 3)}`).join(' · ')}</p>` : ''}`
      : '<p class="muted">Not computed (financial companies, or too few peers in its sector and year).</p>';
    return `<div class="qv-grid"><div class="qv-card"><h3>Dechow F-score</h3>${dh}<p class="muted">Dechow, Ge, Larson &amp; Sloan (2011), model 1, fitted on companies the SEC charged with misstating: the predicted chance of a misstatement over the 0.37% base rate. 1 = average; above 1.85 substantial, above 2.45 high. A screen, not an accusation.</p></div>
      <div class="qv-card"><h3>Montier C-score</h3>${ch}<p class="muted">Montier (2008): six common signs of "cooking the books", each read on the latest fiscal year against the one before. Four or more deserve a closer look at the notes.</p></div>
      <div class="qv-card"><h3>Discretionary accruals</h3>${jh}<p class="muted">Modified Jones model (Dechow, Sloan &amp; Sweeney 1995) with ROA added (Kothari, Leone &amp; Wasley 2005), fitted on the company's sector and fiscal year. Large values either way: profit that the business's growth and assets do not explain.</p></div></div>`;
  }
  function stableCard(mo) {
    const s = mo.stability, p = mo.persistence;
    if (!s && !p) return '';
    return `<div class="qv-card"><h3>Stability and persistence of earnings</h3><table><tbody>
      ${s ? `<tr><td>Volatility of ROA (${s.years} fiscal years)</td><td class="n">${pct(s.sd_roa, 2)}</td></tr><tr><td>Volatility of operating cash flow / assets</td><td class="n">${pct(s.sd_cfoa, 2)}</td></tr>
      <tr><td>Smoothness: σ(ROA) / σ(cash flow / assets)</td><td class="n">${num(s.smooth, 2)}</td></tr><tr><td>Volatility of gross margin · operating margin</td><td class="n">${pct(s.sd_gm, 2)} · ${pct(s.sd_om, 2)}</td></tr>
      ${fin(s.sd_ttm_om) ? `<tr><td>Volatility of the trailing-four-quarter operating margin</td><td class="n">${pct(s.sd_ttm_om, 2)}</td></tr>` : ''}<tr><td>Years with a loss · with negative operating cash flow</td><td class="n">${s.loss_years} · ${s.neg_ocf_years}</td></tr>` : ''}
      ${p ? `<tr><td>This year's ROA: from cash · from accruals</td><td class="n">${pct(p.cash_roa)} · ${pct(p.acc_roa)}</td></tr>
      <tr><td>In its sector, carried into next year: of cash ROA · of accrual ROA</td><td class="n">${fin(p.b_cash) ? Math.round(100 * p.b_cash) + '%' : '—'} · ${fin(p.b_acc) ? Math.round(100 * p.b_acc) + '%' : '—'}</td></tr>
      <tr><td colspan="2" class="muted">Pooled over ${p.n} company-years of its sector: next year's ROA regressed on this year's cash and accrual parts (R² ${num(p.r2, 2)}).</td></tr>` : ''}
      </tbody></table><p class="muted">Smoothness well below 1: reported profit moves much less than cash flow — steady by nature, or smoothed (Leuz, Nanda &amp; Wysocki 2003). Accrual profit usually persists less than cash profit (Sloan 1996): the same ROA built on accruals tends to fall back.</p></div>`;
  }
  function otherCard(mo, c) {
    const t = mo.taxes, g = mo.goodwill, n = mo.nongaap;
    if (!t && !g && !n) return '';
    const tax = t ? `<tr><td colspan="2"><b>Taxes</b> <span class="muted">(${t.years} fiscal years summed)</span></td></tr><tr><td>Cash taxes paid / tax expense</td><td class="n">${num(t.cash_to_book, 2)}</td></tr>
      <tr><td>Cash tax rate · book tax rate (of pre-tax profit)</td><td class="n">${pct(t.cash_etr)} · ${pct(t.book_etr)}</td></tr>` : '';
    const gw = g ? `<tr><td colspan="2"><b>Goodwill and intangibles</b></td></tr><tr><td>Goodwill · other intangibles</td><td class="n">${big(g.gw)} · ${big(g.intang)}</td></tr>
      <tr><td>Their share of assets · of equity</td><td class="n">${pct(g.gw_assets)} · ${fin(g.gw_equity) ? pct(g.gw_equity, 0) : '—'}</td></tr><tr><td>Tangible equity</td><td class="n">${big(g.tangible_equity)}</td></tr>
      ${(g.impairments || []).length ? `<tr><td>Impairments</td><td class="n">${g.impairments.map((x) => `${esc(String(x[0]).slice(0, 4))} ${big(x[1])}`).join(' · ')}</td></tr>` : ''}
      ${(g.signs || []).map((s) => `<tr><td colspan="2" class="bad">${esc(s)}</td></tr>`).join('')}` : '';
    const ng = n ? `<tr><td colspan="2"><b>Non-GAAP earnings</b></td></tr><tr><td>Analysts' "actual" EPS, last four quarters</td><td class="n">${num(n.street_ttm, 2)}</td></tr>
      <tr><td>GAAP EPS, same quarters (net income / diluted shares)</td><td class="n">${num(n.gaap_ttm, 2)}</td></tr><tr><td><b>Gap (adjusted above GAAP)</b></td><td class="n"><b class="${fin(n.gap) && n.gap > 0.25 ? 'bad' : ''}">${pct(n.gap, 0)}</b></td></tr>` : '';
    return `<div class="qv-card"><h3>Taxes, goodwill and non-GAAP</h3><table><tbody>${tax}${gw}${ng}</tbody></table>
      <p class="muted">Cash taxes well under the expense: profit taxed later (or never) — deferrals, credits, timing. Goodwill above equity or a market value under book: a write-down is more likely. A wide, lasting gap between adjusted and GAAP earnings: "one-off" costs that keep coming back.</p></div>`;
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
      ${c.more ? `<div class="qv-grid">${qmjCard(c.more)}${stableCard(c.more)}${otherCard(c.more, c)}</div>` : ''}
      <div class="qv-grid">${piotroski(c.metrics)}${altman(c.metrics)}${beneish(c.metrics)}</div>
      ${c.more ? manipCard(c.more) : ''}
      <div class="qv-grid">${yields(c)}${roic(c)}${leverage(c)}</div>
      <div class="qv-grid">${margins(c)}${line(c)}</div>${records(c)}
      <div class="qv-card"><h3>Revenue Quality / Cookie Jar screening</h3>
      <p class="muted">Receivable-versus-sales growth, contract assets, deferred revenue changes, cash conversion and recognition-policy filing leads. Independent SEC evidence, not a fraud allegation. No missing value is treated as zero.</p>
      <a href="${hub}#hidden/${encodeURIComponent(t)}">View original SEC evidence and review flags →</a></div>
      <p class="muted">Companies' own XBRL tags via the SEC frames API; prices: daily closes. Research, not investment advice.${hub ? ` <a href="${hub}#quality">All companies →</a>` : ''}</p></div>`;
  }
  window.QualityView = { render };
})();
