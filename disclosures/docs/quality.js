/* Quality — Piotroski F, Altman Z, Beneish M, shareholder yield, FCF after stock comp, ROIC − WACC, operating leverage
   and the factor research for every US company over $300M: a screener, the growth-adjusted EV/Sales line per sector,
   walk-forward factor backtests, the frozen monthly ranking and margin mean reversion; Quality Minus Junk, manipulation
   screens (Dechow F, Montier C, discretionary accruals), earnings stability and persistence, taxes, goodwill and the
   non-GAAP gap. One company: QualityView.
   Data: data/research/quality/{index,scatter,factors,ledger,margins,persistence}.json (app/quality.py, branch research-quality). */
const qStore = {};
function qData(name) {
  const m = qStore[name] || (qStore[name] = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/research/quality/' + name + '.json').then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(d => { m.data = d; render() }).catch(e => { m.err = e.message; render() });
  return m;
}
const Q_VIEWS = [['screen', 'Screener'], ['more', 'QMJ, red flags & stability'], ['persist', 'Earnings persistence by sector'], ['scatter', 'Growth-adjusted EV/Sales'], ['factors', 'Factor backtests'], ['ledger', 'Monthly ranking (frozen)'], ['margins', 'Margin mean reversion']];
const Q_PRESETS = [['all', 'Every company'], ['f9', 'Piotroski 9/9'], ['distress', 'Altman distress zone'], ['beneish', 'Beneish flag (screen)'],
  ['sy', 'Shareholder yield ≥ 5%'], ['sbc', 'Stock comp ≥ 30% of FCF'], ['spread', 'ROIC above WACC'], ['cheap', 'Below the sector line'], ['top', 'Composite top tenth']];
const Q_SORT = [['mcap', 'Market cap'], ['composite', 'Composite'], ['f_score', 'Piotroski F'], ['z', 'Altman Z (low first)'], ['m_score', 'Beneish M (high first)'],
  ['sy', 'Shareholder yield'], ['fcf_sbc_y', 'FCF yield after SBC'], ['spread', 'ROIC − WACC'], ['dol', 'Operating leverage'], ['resid', 'Residual vs line (low first)'],
  ['accruals', 'Accruals (low first)'], ['gp_a', 'Gross profit / assets'], ['net_iss', 'Net issuance (low first)']];
const Q_ASC = new Set(['z', 'resid', 'accruals', 'net_iss']);
const qPct = (v, d = 1) => v == null || !Number.isFinite(+v) ? '—' : (v < 0 ? '−' : '') + Math.abs(v * 100).toFixed(d) + '%';
const qNum = (v, d = 2) => v == null || !Number.isFinite(+v) ? '—' : (v < 0 ? '−' : '') + Math.abs(+v).toFixed(d);
const qCap = v => v == null ? '—' : '$' + compact(v);
function qRows(d) { const F = d.fields; return (d.rows || []).map(r => { const o = {}; F.forEach((k, i) => o[k] = r[i]); return o }) }
function qPreset(r, p) {
  return p === 'f9' ? r.f_score === 9 : p === 'distress' ? r.z_zone === 'distress' : p === 'beneish' ? !!r.m_flag : p === 'sy' ? (r.sy || 0) >= 0.05
    : p === 'sbc' ? r.fcf_y > 0 && r.fcf_sbc_y != null && (r.fcf_y - r.fcf_sbc_y) / r.fcf_y >= 0.3 : p === 'spread' ? (r.spread || 0) > 0
    : p === 'cheap' ? (r.resid || 0) < 0 : p === 'top' ? (r.comp_rank || 0) >= 0.9 : true;
}
function qScreen(d) {
  const rows = qRows(d), secs = [...new Set(rows.map(r => r.sector))].sort(), names = d.sector_names || {};
  state.qp = state.qp || 'all'; state.qs = state.qs || 'mcap'; state.qm = state.qm || '0';
  let out = `<div class="toolbar">${field('qp', 'Show', Q_PRESETS, state.qp)}${field('qsec', 'Sector', [['', 'All sectors']].concat(secs.map(s => [s, names[s] || s])), state.qsec || '')}
    ${field('qm', 'Market cap', [['0', 'Over $300M'], ['1e9', 'Over $1B'], ['5e9', 'Over $5B'], ['1e10', 'Over $10B'], ['5e10', 'Over $50B']], state.qm)}
    ${field('qs', 'Sort', Q_SORT, state.qs)}<div class="field"><label for="qq">Ticker or name</label><input id="qq" value="${esc(state.qq || '')}" placeholder="e.g. MSFT"></div></div>`;
  const q = (state.qq || '').trim().toUpperCase();
  let L = rows.filter(r => qPreset(r, state.qp) && (!state.qsec || r.sector === state.qsec) && (r.mcap || 0) >= +state.qm
    && (!q || r.ticker.includes(q) || String(r.name || '').toUpperCase().includes(q)));
  const k = state.qs, asc = Q_ASC.has(k);
  L.sort((a, b) => (a[k] == null) - (b[k] == null) || (asc ? a[k] - b[k] : b[k] - a[k]));
  exported = L;
  const page = state.page || 0, per = 50, slice = L.slice(page * per, page * per + per);
  out += `<div class="explain">${esc(d.note || '')} Prices as of ${esc(d.asof || '—')}; risk-free rate ${qPct(d.rf, 2)}, equity risk premium ${qPct(d.erp, 0)}. Click a ticker for every part of its scores.</div>`;
  out += `<div id="q-detail"></div><div class="tablebox"><table><thead><tr><th>Company</th><th>Mkt cap</th><th title="Piotroski F-score (of 9)">F</th><th title="Altman Z or Z''">Z</th><th title="Beneish M-score; above −1.78 is a statistical flag">M</th>
    <th title="Dividends + net buybacks over market cap">Sh. yield</th><th title="Free-cash-flow yield → after stock comp">FCF → after SBC</th><th>ROIC</th><th title="ROIC − WACC">Spread</th><th title="Degree of operating leverage">DOL</th>
    <th>Accruals</th><th title="Gross profit / assets">GP/A</th><th>Net iss.</th><th>EV/S</th><th title="log residual against the sector's growth-adjusted line">vs line</th><th title="Composite percentile">Comp.</th></tr></thead><tbody>
    ${slice.map(r => `<tr><td><button class="text-button" data-qt="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button><br><span class="sub">${esc(r.name || '')}</span></td><td>${qCap(r.mcap)}</td>
      <td>${r.f_score == null ? '—' : r.f_score}</td><td class="${r.z_zone === 'distress' ? 'negative' : r.z_zone === 'safe' ? 'positive' : ''}">${qNum(r.z)}${r.z_model ? `<br><span class="sub">${esc(r.z_model)}</span>` : ''}</td>
      <td class="${r.m_flag ? 'negative' : ''}">${qNum(r.m_score)}</td><td>${qPct(r.sy)}</td><td>${qPct(r.fcf_y)} → ${qPct(r.fcf_sbc_y)}</td><td>${qPct(r.roic)}</td>
      <td class="${(r.spread || 0) >= 0 ? 'positive' : 'negative'}">${qPct(r.spread)}</td><td>${r.dol == null ? '—' : qNum(r.dol, 1) + 'x'}</td><td>${qPct(r.accruals)}</td><td>${qPct(r.gp_a)}</td>
      <td>${qPct(r.net_iss)}</td><td>${r.ev_s == null ? '—' : qNum(r.ev_s, 1) + 'x'}</td><td>${qNum(r.resid)}</td><td>${r.comp_rank == null ? '—' : Math.round(100 * r.comp_rank)}</td></tr>`).join('')}
    </tbody></table></div><div class="pager"><span>${fmt(L.length)} companies · page ${page + 1} of ${Math.max(1, Math.ceil(L.length / per))}</span><button class="action" data-qpage="-1" ${page ? '' : 'disabled'}>Previous</button>
    <button class="action" data-qpage="1" ${(page + 1) * per < L.length ? '' : 'disabled'}>Next</button></div>`;
  return out;
}
const QM_PRESETS = [['all', 'Every company'], ['qtop', 'QMJ top tenth'], ['qbot', 'QMJ bottom tenth (junk)'], ['dechow', 'Dechow F substantial or high'],
  ['cscore', 'C-score 4 or more'], ['da', 'Discretionary accruals: top tenth of the sector'], ['ng', 'Non-GAAP 25%+ above GAAP'], ['gw', 'Goodwill + intangibles above equity'],
  ['tax', 'Cash taxes under half the expense']];
const QM_SORT = [['qmj', 'QMJ'], ['qmj_prof', 'Profitability'], ['qmj_growth', 'Growth'], ['qmj_safety', 'Safety'], ['qmj_payout', 'Payout'], ['dechow_f', 'Dechow F (high first)'],
  ['c_score', 'C-score (high first)'], ['da_pct', 'Discretionary accruals (size in sector)'], ['sd_roa', 'Volatility of ROA'], ['smooth', 'Smoothness (low first)'],
  ['ng_gap', 'Non-GAAP gap'], ['gw_equity', 'Goodwill / equity'], ['cash_tax', 'Cash / book taxes (low first)'], ['mcap', 'Market cap']];
const QM_ASC = new Set(['smooth', 'cash_tax']);
function qmPreset(r, p) {
  return p === 'qtop' ? (r.qmj_rank || 0) >= 0.9 : p === 'qbot' ? r.qmj_rank != null && r.qmj_rank <= 0.1 : p === 'dechow' ? ['substantial', 'high'].includes(r.dechow_band)
    : p === 'cscore' ? (r.c_score || 0) >= 4 : p === 'da' ? (r.da_pct || 0) >= 0.9 : p === 'ng' ? (r.ng_gap || 0) >= 0.25 : p === 'gw' ? (r.gw_equity || 0) > 1
    : p === 'tax' ? r.cash_tax != null && r.cash_tax < 0.5 : true;
}
const qOrd = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
const qPc = v => Math.min(99, Math.max(1, Math.round(100 * v)));          /* a percentile, 1–99 */
const qZ = v => v == null || !Number.isFinite(+v) ? '—' : `<span class="${v >= 0 ? 'positive' : 'negative'}">${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}</span>`;
function qMore(d) {
  const rows = qRows(d), secs = [...new Set(rows.map(r => r.sector))].sort(), names = d.sector_names || {};
  state.qmp = state.qmp || 'all'; state.qms = state.qms || 'qmj'; state.qm = state.qm || '0';
  let out = `<div class="toolbar">${field('qmp', 'Show', QM_PRESETS, state.qmp)}${field('qsec', 'Sector', [['', 'All sectors']].concat(secs.map(s => [s, names[s] || s])), state.qsec || '')}
    ${field('qm', 'Market cap', [['0', 'Over $300M'], ['1e9', 'Over $1B'], ['5e9', 'Over $5B'], ['1e10', 'Over $10B'], ['5e10', 'Over $50B']], state.qm)}
    ${field('qms', 'Sort', QM_SORT, state.qms)}<div class="field"><label for="qq">Ticker or name</label><input id="qq" value="${esc(state.qq || '')}" placeholder="e.g. MSFT"></div></div>`;
  const q = (state.qq || '').trim().toUpperCase();
  const L = rows.filter(r => qmPreset(r, state.qmp) && (!state.qsec || r.sector === state.qsec) && (r.mcap || 0) >= +state.qm
    && (!q || r.ticker.includes(q) || String(r.name || '').toUpperCase().includes(q)));
  const k = state.qms, asc = QM_ASC.has(k);
  L.sort((a, b) => (a[k] == null) - (b[k] == null) || (asc ? a[k] - b[k] : b[k] - a[k]));
  exported = L;
  const page = state.page || 0, per = 50, slice = L.slice(page * per, page * per + per);
  out += `<div class="explain"><b>QMJ</b>: Asness, Frazzini &amp; Pedersen's Quality Minus Junk — profitability, growth, safety and payout, each a z-score across every company over $300M (percentile shown).
    <b>Dechow F</b>: the chance of a misstatement over the 0.37% base rate (above 1.85 substantial). <b>C-score</b>: Montier's six warning signs. <b>Disc. accruals</b>: the part of accruals the modified Jones model (with ROA) cannot explain, and how large it is within the sector.
    <b>Smooth</b>: σ(ROA) / σ(cash flow / assets). <b>Non-GAAP gap</b>: analysts' adjusted EPS over GAAP EPS, last four quarters. Screens and research, not accusations or advice. Click a ticker for every part.</div>`;
  out += `<div id="q-detail"></div><div class="tablebox"><table><thead><tr><th>Company</th><th>Mkt cap</th><th title="QMJ percentile">QMJ</th><th>Prof.</th><th>Growth</th><th>Safety</th><th>Payout</th>
    <th title="Dechow F-score">F (Dechow)</th><th title="Montier C-score">C</th><th title="Discretionary accruals / assets (size percentile in sector)">Disc. acc.</th><th title="Volatility of ROA">σ ROA</th><th>Smooth</th>
    <th title="Analysts' adjusted EPS vs GAAP">Non-GAAP gap</th><th title="Goodwill + intangibles / equity">GW / equity</th><th title="Cash taxes paid / tax expense, 3 years">Cash / book tax</th></tr></thead><tbody>
    ${slice.map(r => `<tr><td><button class="text-button" data-qt="${esc(r.ticker)}"><b>${esc(r.ticker)}</b></button><br><span class="sub">${esc(r.name || '')}</span></td><td>${qCap(r.mcap)}</td>
      <td>${r.qmj_rank == null ? '—' : `<b>${qPc(r.qmj_rank)}</b>`}</td><td>${qZ(r.qmj_prof)}</td><td>${qZ(r.qmj_growth)}</td><td>${qZ(r.qmj_safety)}</td><td>${qZ(r.qmj_payout)}</td>
      <td class="${['substantial', 'high'].includes(r.dechow_band) ? 'negative' : ''}">${qNum(r.dechow_f)}${r.dechow_band && r.dechow_band !== 'normal' ? `<br><span class="sub">${esc(r.dechow_band)}</span>` : ''}</td>
      <td class="${(r.c_score || 0) >= 4 ? 'negative' : ''}">${r.c_score == null ? '—' : r.c_score + '/' + r.c_n}</td>
      <td class="${(r.da_pct || 0) >= 0.9 ? 'negative' : ''}">${qNum(r.da, 3)}${r.da_pct == null ? '' : `<br><span class="sub">${qOrd(qPc(r.da_pct))} pct</span>`}</td>
      <td>${qPct(r.sd_roa)}</td><td>${qNum(r.smooth)}</td><td class="${(r.ng_gap || 0) >= 0.25 ? 'negative' : ''}">${qPct(r.ng_gap, 0)}</td><td>${qPct(r.gw_equity, 0)}</td><td>${qNum(r.cash_tax)}</td></tr>`).join('')}
    </tbody></table></div><div class="pager"><span>${fmt(L.length)} companies · page ${page + 1} of ${Math.max(1, Math.ceil(L.length / per))}</span><button class="action" data-qpage="-1" ${page ? '' : 'disabled'}>Previous</button>
    <button class="action" data-qpage="1" ${(page + 1) * per < L.length ? '' : 'disabled'}>Next</button></div>`;
  return out;
}
function qPersist(d) {
  const S = d.sectors || {}, names = d.sector_names || {}, keys = Object.keys(S).sort((a, b) => (S[b].n || 0) - (S[a].n || 0));
  if (!keys.length) return empty('Not enough company-years per sector yet.');
  return `<div class="explain">${esc(d.note || '')} b_cash above b_acc: profit backed by cash carries into next year more than profit made of accruals (Sloan 1996). b_ROA: the same with profit as one number.</div>
    <div class="tablebox"><table><thead><tr><th>Sector</th><th>Company-years</th><th>Intercept</th><th>b cash ROA</th><th>b accrual ROA</th><th>R²</th><th>b ROA (one number)</th><th>R²</th></tr></thead><tbody>
    ${keys.map(k => { const s = S[k]; return `<tr><td>${esc(names[k] || k)}</td><td>${fmt(s.n)}</td><td>${qNum(s.a, 3)}</td><td><b>${qNum(s.b_cash)}</b></td><td><b>${qNum(s.b_acc)}</b></td><td>${qNum(s.r2)}</td><td>${qNum(s.b_roa)}</td><td>${qNum(s.r2_roa)}</td></tr>` }).join('')}
    </tbody></table></div>`;
}
function qScatter(d) {
  const secs = Object.keys(d.points || {}).filter(s => (d.points[s] || []).length >= 8).sort(), names = d.sector_names || {};
  if (!secs.length) return empty('No sector has enough companies for a line yet.');
  state.qsec2 = secs.includes(state.qsec2) ? state.qsec2 : secs[0];
  const P = d.points[state.qsec2], ln = (d.lines || {})[state.qsec2];
  const W = 760, H = 420, L = 56, R = 16, T = 16, B = 40;
  const xs = P.map(p => Math.max(-100, Math.min(150, p[1]))), ys = P.map(p => Math.log(p[2]));
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const X = x => L + (x - x0) / ((x1 - x0) || 1) * (W - L - R), Y = y => T + (y1 - y) / ((y1 - y0) || 1) * (H - T - B);
  const maxc = Math.max(...P.map(p => p[4] || 0)) || 1;
  const lab = [...P].sort((a, b) => a[3] - b[3]).slice(0, 6).concat([...P].sort((a, b) => b[3] - a[3]).slice(0, 4)).map(p => p[0]);
  let svg = `<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="EV/Sales against growth plus margin, ${esc(names[state.qsec2] || state.qsec2)}">`;
  [0.5, 1, 2, 5, 10, 20, 50].forEach(v => { const y = Math.log(v); if (y >= y0 && y <= y1) svg += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${Y(y)}" y2="${Y(y)}"/><text class="axis" x="${L - 6}" y="${Y(y) + 4}" text-anchor="end">${v}x</text>` });
  if (ln) svg += `<line x1="${X(x0)}" y1="${Y(ln.a + ln.b * x0)}" x2="${X(x1)}" y2="${Y(ln.a + ln.b * x1)}" stroke="currentColor" stroke-opacity=".55" stroke-width="2"/>`;
  P.forEach((p, i) => { const r = 3 + 9 * Math.sqrt((p[4] || 0) / maxc); svg += `<circle cx="${X(xs[i])}" cy="${Y(ys[i])}" r="${r.toFixed(1)}" fill="${p[3] < 0 ? '#17734a' : '#b42318'}" fill-opacity=".55"><title>${esc(p[0])}: ${qNum(p[2], 1)}x sales, growth + margin ${qNum(p[1], 0)}, residual ${qNum(p[3])}</title></circle>` });
  P.forEach((p, i) => { if (lab.includes(p[0])) svg += `<text class="axis" x="${X(xs[i]) + 6}" y="${Y(ys[i]) - 6}">${esc(p[0])}</text>` });
  svg += `<text class="axis" x="${(L + W) / 2}" y="${H - 8}" text-anchor="middle">revenue growth % + operating margin % (trailing four quarters)</text></svg>`;
  const cheap = [...P].sort((a, b) => a[3] - b[3]).slice(0, 10);
  return `<div class="toolbar">${field('qsec2', 'Sector', secs.map(s => [s, (names[s] || s) + ' (' + d.points[s].length + ')']), state.qsec2)}</div>
    <div class="explain">Each dot is a company over $300M (size: market cap): its EV / sales against its revenue growth plus operating margin. The line: log(EV/Sales) = a + b × score${ln ? ` (b = ${qNum(ln.b, 4)}, R² ${qNum(ln.r2)}, ${ln.n} companies)` : ''}. Green: below the line — cheaper than peers with the same growth and margin; red: above. Not investment advice.</div>${svg}
    <h3>Furthest below the line</h3><div class="tablebox"><table><thead><tr><th>Company</th><th>EV/S</th><th>Growth + margin</th><th>Residual</th></tr></thead><tbody>
    ${cheap.map(p => `<tr><td><button class="text-button" data-qt="${esc(p[0])}"><b>${esc(p[0])}</b></button></td><td>${qNum(p[2], 1)}x</td><td>${qNum(p[1], 0)}</td><td>${qNum(p[3])}</td></tr>`).join('')}</tbody></table></div>`;
}
function qLine(series, idx, label) {
  if (!series || series.length < 2) return '';
  const W = 760, H = 220, L = 56, R = 16, T = 12, B = 28, vals = series.map(s => s[idx]);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), X = i => L + i / (series.length - 1) * (W - L - R), Y = v => T + (hi - v) / ((hi - lo) || 1) * (H - T - B);
  return `<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}"><line class="gridline" x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}"/>
    <text class="axis" x="${L - 6}" y="${Y(hi) + 4}" text-anchor="end">${qPct(hi, 0)}</text><text class="axis" x="${L - 6}" y="${Y(lo) + 4}" text-anchor="end">${qPct(lo, 0)}</text>
    <path class="chartline" d="${series.map((s, i) => `${i ? 'L' : 'M'}${X(i)},${Y(s[idx])}`).join(' ')}"/>
    <text class="axis" x="${L}" y="${H - 8}">${esc(series[0][0])}</text><text class="axis" x="${W - R}" y="${H - 8}" text-anchor="end">${esc(series[series.length - 1][0])}</text></svg>`;
}
function qFactors(d) {
  const F = d.factors || {}, keys = Object.keys(F);
  if (!keys.length) return empty('No factor history yet.');
  state.qf = keys.includes(state.qf) ? state.qf : 'composite';
  const f = F[state.qf] || {};
  return `<div class="explain">${esc(d.note || '')} Universe: ${esc(d.universe || '')}. Each factor is signed so that higher is better; the composite averages the percentiles with equal weights fixed in advance.</div>
    <div class="tablebox"><table><thead><tr><th>Factor</th><th>Months</th><th>Mean rank IC</th><th>t</th><th>IC &gt; 0</th><th>Mean top − bottom fifth</th><th>Cumulative</th></tr></thead><tbody>
    ${keys.map(k => { const x = F[k]; return `<tr><td><button class="text-button" data-qf="${esc(k)}"><b>${esc(x.label || k)}</b></button></td><td>${fmt(x.months)}</td><td>${qNum(x.mean_ic, 3)}</td><td>${qNum(x.t)}</td><td>${qPct(x.hit, 0)}</td><td class="${(x.mean_spread || 0) >= 0 ? 'positive' : 'negative'}">${qPct(x.mean_spread, 2)}</td><td>${qPct(x.cum_spread)}</td></tr>` }).join('')}
    </tbody></table></div><h3>${esc(f.label || state.qf)}: cumulative top − bottom fifth</h3>${qLine(f.series, 3, 'cumulative spread')}<h3>Monthly rank IC</h3>${qLine(f.series, 1, 'rank IC by month')}`;
}
function qLedger(d) {
  const M = Object.values(d.months || {}).sort((a, b) => a.month < b.month ? 1 : -1);
  if (!M.length) return empty('The first monthly ranking is frozen on the next build.');
  return `<div class="explain">${esc(d.note || '')} ${d.scored ? `${d.scored} month(s) scored: mean rank IC ${qNum(d.mean_ic, 3)}, mean top − bottom tenth ${qPct(d.mean_spread, 2)}.` : 'No month scored yet.'}</div>
    <div class="tablebox"><table><thead><tr><th>Month</th><th>Frozen</th><th>Companies</th><th>Top of the ranking</th><th>Result (next month)</th></tr></thead><tbody>
    ${M.map(m => `<tr><td><b>${esc(m.month)}</b></td><td>${esc(String(m.frozen_at || '').slice(0, 10))}</td><td>${fmt(m.n)}</td><td>${(m.top || []).slice(0, 10).map(x => `<button class="text-button" data-qt="${esc(x[0])}">${esc(x[0])}</button>`).join(' ')}</td>
      <td>${m.result ? `top ${qPct(m.result.top, 2)} · bottom ${qPct(m.result.bottom, 2)} · spread <b class="${m.result.spread >= 0 ? 'positive' : 'negative'}">${qPct(m.result.spread, 2)}</b> · IC ${qNum(m.result.ic, 3)}` : '<span class="sub">waiting for the month-end close</span>'}</td></tr>`).join('')}
    </tbody></table></div>`;
}
function qMargins(d) {
  const S = d.sectors || {}, names = d.sector_names || {};
  return `<div class="explain">Operating margins (trailing four quarters) against the sector median: the gap shrinks by φ a quarter (pooled pairs; a sector with fewer than 150 pairs uses the market's). Walk-forward: each quarter's φ from earlier quarters only, its error against assuming no change.</div>
    <div class="tablebox"><table><thead><tr><th>Sector</th><th>φ a quarter</th><th>Half-life</th><th>Pairs</th><th>Out-of-sample error</th><th>"No change" error</th></tr></thead><tbody>
    ${Object.entries(S).map(([k, s]) => `<tr><td>${esc(k === '_all' ? 'All companies' : names[k] || k)}${s.own_pairs || k === '_all' ? '' : ' <span class="sub">(market φ)</span>'}</td><td>${qNum(s.phi, 3)}</td><td>${s.half_life_q == null ? '—' : qNum(s.half_life_q, 1) + ' quarters'}</td><td>${fmt(s.pairs)}</td><td>${qPct(s.oos_mae, 2)}</td><td>${qPct(s.naive_mae, 2)}</td></tr>`).join('')}
    </tbody></table></div>`;
}
function qualityView() {
  state.qv = Q_VIEWS.some(v => v[0] === state.qv) ? state.qv : 'screen';
  let out = `<div class="toolbar">${field('qv', 'View', Q_VIEWS, state.qv)}</div>`;
  const name = { screen: 'index', more: 'index', persist: 'persistence', scatter: 'scatter', factors: 'factors', ledger: 'ledger', margins: 'margins' }[state.qv];
  const m = qData(name);
  if (m.err) return out + empty(`The Quality research could not load (${m.err}). It is rebuilt daily by the research-quality workflow.`);
  if (!m.data) return out + empty('Loading the Quality research…');
  out += ({ screen: qScreen, more: qMore, persist: qPersist, scatter: qScatter, factors: qFactors, ledger: qLedger, margins: qMargins })[state.qv](m.data);
  return out;
}
function bindQuality() {
  if (state.tab !== 'quality') return;
  ['qv', 'qp', 'qsec', 'qm', 'qs', 'qsec2', 'qmp', 'qms'].forEach(id => { if ($(id)) $(id).onchange = e => { state[id] = e.target.value; state.page = 0; render() } });
  if ($('qq')) $('qq').onchange = e => { state.qq = e.target.value; state.page = 0; render() };
  document.querySelectorAll('#workspace [data-qpage]').forEach(b => b.onclick = () => { state.page = Math.max(0, (state.page || 0) + +b.dataset.qpage); render() });
  document.querySelectorAll('#workspace [data-qf]').forEach(b => b.onclick = () => { state.qf = b.dataset.qf; render() });
  document.querySelectorAll('#workspace [data-qt]').forEach(b => b.onclick = () => {
    state.qt = b.dataset.qt;
    let box = $('q-detail');
    if (!box) { box = document.createElement('div'); box.id = 'q-detail'; $('workspace').prepend(box); }
    if (window.QualityView) window.QualityView.render(box, { ticker: state.qt, hub: '' });
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  if (state.qt && $('q-detail') && window.QualityView && !$('q-detail').innerHTML) window.QualityView.render($('q-detail'), { ticker: state.qt, hub: '' });
}
function qualityDeepLink(arg) {                  /* #quality/more, #quality/persist, #quality/MSFT */
  const v = decodeURIComponent(arg || '').trim();
  if (Q_VIEWS.some(x => x[0] === v)) state.qv = v;
  else if (v) { state.qv = 'screen'; state.qt = v.toUpperCase(); }
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { quality: qualityView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { quality: bindQuality });
