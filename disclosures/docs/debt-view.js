/* Debt & rates — one company's page, shared by the Disclosure Hub (Debt & rates tab) and the main site's company page
   ("Debt & rates" tab). Self-contained: window.DebtView.render(element, doc, {base, compact}) draws everything from
   data/debt/c/<cik>.json (app/debt.py). Colours come from the host's CSS variables with fallbacks; tooltips are SVG
   <title>s so either page can host it. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const pct = (v, d = 1) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const x = (v, d = 1) => (fin(v) ? num(v, d) + '×' : '—');
  const bp = (v) => (fin(v) ? num(v, 0) + ' bp' : '—');
  const day = (s) => (s ? String(s).slice(0, 10) : '—');
  const C = { good: 'var(--mk-profit, #2e8b57)', bad: 'var(--mk-cost, #c0392b)', warn: 'var(--q-warm, #d9822b)', acc: 'var(--accent, #2a78d6)', mute: 'var(--muted, #888)', ink: 'var(--ink, #222)', line: 'var(--line, #ddd)', prev: '#8a4fd6' };
  const KIND = { notes: 'Notes / bonds', convertible: 'Convertible', revolver: 'Revolving credit', loan: 'Loan', commercial_paper: 'Commercial paper', abs: 'Asset-backed / securitised', lease: 'Finance lease', mortgage: 'Mortgage', other: 'Other' };
  const COV = { leverage: 'Leverage (debt ÷ EBITDA)', interest_coverage: 'Interest coverage', fixed_charge: 'Fixed-charge coverage', debt_to_cap: 'Debt to capitalisation', liquidity: 'Minimum liquidity', net_worth: 'Net worth', collateral_coverage: 'Collateral coverage' };

  function css() {
    if (document.getElementById('dv-css')) return;
    const s = document.createElement('style'); s.id = 'dv-css';
    s.textContent = `.dv{--dv-good:${C.good};--dv-bad:${C.bad}}
.dv h3{margin:22px 0 6px;font-size:16px}.dv .dv-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45}
.dv-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:8px 0 6px}
.dv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 12px;background:var(--surface,transparent)}
.dv-card b{display:block;font-size:20px;font-variant-numeric:tabular-nums;margin-top:2px}.dv-card span{font-size:12px;color:var(--muted,#777)}
.dv-card i{display:block;font-style:normal;font-size:12px;margin-top:2px}
.dv-good{color:var(--dv-good)}.dv-bad{color:var(--dv-bad)}.dv-warn{color:${C.warn}}
.dv-score{display:flex;align-items:center;gap:14px;margin:6px 0 4px}.dv-score .dv-bar{flex:1;height:10px;border-radius:6px;background:linear-gradient(90deg,var(--dv-bad),${C.warn},var(--dv-good));position:relative}
.dv-score .dv-pin{position:absolute;top:-5px;width:4px;height:20px;border-radius:2px;background:var(--ink,#222)}
.dv-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.dv-tbl th,.dv-tbl td{padding:6px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.dv-tbl td.n,.dv-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.dv-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}
.dv-wrap{overflow-x:auto}.dv svg{display:block;width:100%;max-width:820px;height:auto;overflow:visible}.dv svg text{font-size:11px;fill:var(--muted,#777)}
.dv .dv-grid{stroke:var(--line,#e3e3e3)}.dv .dv-axis{stroke:var(--muted,#999);stroke-width:1}
.dv-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
.dv details{margin:4px 0}.dv summary{cursor:pointer;color:var(--accent,#2a78d6);font-size:13px}.dv q{display:block;font-size:12px;color:var(--muted,#777);margin:4px 0 0}
.dv-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:14px}.dv-tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line,#ddd);margin-left:6px;color:var(--muted,#777)}
.dv-moneybar{position:relative;height:8px;border-radius:5px;background:var(--line,#e5e5e5);min-width:90px}.dv-moneybar i{position:absolute;top:0;bottom:0;left:0;border-radius:5px}
.dv-show{margin:2px 0 8px;font:inherit;font-size:13px;color:var(--accent,#2a78d6);background:none;border:1px solid var(--line,#ddd);border-radius:8px;padding:4px 10px;cursor:pointer}
.dv-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:2px 0 6px}.dv-legend span::before{content:'';display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px;background:var(--k)}`;
    document.head.appendChild(s);
  }
  const tone = (v, goodHigh, lo, hi) => (!fin(v) ? '' : goodHigh ? (v >= hi ? 'dv-good' : v <= lo ? 'dv-bad' : 'dv-warn') : (v <= lo ? 'dv-good' : v >= hi ? 'dv-bad' : 'dv-warn'));
  const card = (label, value, cls = '', note = '') => `<div class="dv-card"><span>${esc(label)}</span><b class="${cls}">${value}</b>${note ? `<i>${note}</i>` : ''}</div>`;
  const link = (u, t) => (u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>` : esc(t));

  // ---------- charts ----------
  function lineChart(series, opt) {
    const W = opt.w || 640, H = opt.h || 220, L = 52, R = opt.r || 14, T = 12, B = 26;
    const pts = series.flatMap((s) => s.pts.filter((p) => fin(p[1])));
    if (pts.length < 2) return '';
    const xs = pts.map((p) => p[0]), x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = opt.y0 != null ? opt.y0 : Math.min(...pts.map((p) => p[1])), y1 = Math.max(...pts.map((p) => p[1]));
    if (opt.dots) for (const d of opt.dots) { y0 = Math.min(y0, d[1]); y1 = Math.max(y1, d[1]); }
    if (y1 === y0) y1 = y0 + 1; const pad = (y1 - y0) * 0.06; y1 += pad; if (opt.y0 == null) y0 -= pad;
    const X = (v) => L + (v - x0) / ((x1 - x0) || 1) * (W - L - R), Y = (v) => T + (y1 - v) / (y1 - y0) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.title || 'chart')}">`;
    for (let k = 0; k <= 4; k++) { const v = y0 + (y1 - y0) * k / 4; s += `<line class="dv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${esc(opt.fy ? opt.fy(v) : num(v, 1))}</text>`; }
    const yr0 = new Date(x0).getUTCFullYear(), yr1 = new Date(x1).getUTCFullYear(), step = Math.max(1, Math.ceil((yr1 - yr0 + 1) / 8));
    for (let yv = yr0; yv <= yr1; yv += step) { const t = Date.UTC(yv, 0, 1); if (t < x0 || t > x1) continue; s += `<text x="${X(t)}" y="${H - 6}" text-anchor="middle">${yv}</text>`; }
    for (const sr of series) {
      const p = sr.pts.filter((q) => fin(q[1])); if (p.length < 2) continue;
      s += `<path d="${p.map((q, i) => (i ? 'L' : 'M') + X(q[0]).toFixed(1) + ',' + Y(q[1]).toFixed(1)).join('')}" fill="none" stroke="${sr.col}" stroke-width="${sr.w || 1.8}"${sr.dash ? ` stroke-dasharray="${sr.dash}"` : ''}/>`;
      const last = p[p.length - 1]; s += `<text x="${X(last[0]) + 4}" y="${Y(last[1]) + 4}" style="fill:${sr.col}">${esc(sr.label || '')}</text>`;
    }
    if (opt.dots) for (const d of opt.dots) s += `<circle cx="${X(d[0])}" cy="${Y(d[1])}" r="${d[3] || 3.5}" fill="${d[4] || C.prev}" fill-opacity=".75"><title>${esc(d[2])}</title></circle>`;
    return s + '</svg>';
  }
  function barChart(bars, opt) {
    const W = opt.w || 560, H = opt.h || 200, L = 56, R = 10, T = 14, B = 34, n = bars.length;
    const mx = Math.max(1, ...bars.map((b) => b.v || 0), opt.ref || 0) * 1.1, bw = (W - L - R) / n;
    const Y = (v) => T + (mx - v) / mx * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.title || 'chart')}">`;
    for (let k = 0; k <= 4; k++) { const v = mx * k / 4; s += `<line class="dv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${esc(big(v))}</text>`; }
    bars.forEach((b, i) => { if (!fin(b.v)) return; const xx = L + i * bw + bw * 0.15; s += `<rect x="${xx}" y="${Y(b.v)}" width="${bw * 0.7}" height="${Math.max(0, H - B - Y(b.v))}" rx="3" fill="${b.col || C.acc}"><title>${esc(b.label + ': ' + big(b.v))}</title></rect><text x="${xx + bw * 0.35}" y="${H - 18}" text-anchor="middle">${esc(b.label)}</text>`; });
    if (opt.ref) s += `<line x1="${L}" x2="${W - R}" y1="${Y(opt.ref)}" y2="${Y(opt.ref)}" stroke="${C.good}" stroke-dasharray="5 3" stroke-width="1.6"/><text x="${W - R}" y="${Y(opt.ref) - 5}" text-anchor="end" style="fill:${C.good}">${esc(opt.refLabel || '')}</text>`;
    return s + '</svg>';
  }
  const t = (s) => Date.parse(String(s).length === 7 ? s + '-15' : s);

  // ---------- sections ----------
  function summary(d) {
    const A = d.analysis || {}, I = A.implied || {}, s = d.snapshot || {};
    let h = `<div class="dv-cards">`;
    h += card('Total debt', big(A.total_debt), '', s.balance_date ? 'at ' + day(s.balance_date) : '');
    h += card('Net debt', big(A.net_debt), A.net_debt < 0 ? 'dv-good' : '', 'debt − cash − short-term investments');
    h += card('Net debt ÷ EBITDA', x(A.net_leverage), tone(A.net_leverage, false, 2, 4), 'gross ' + x(A.leverage));
    h += card('Interest coverage', x(A.interest_coverage), tone(A.interest_coverage, true, 2, 6), 'EBIT ÷ interest (12 months)');
    h += card('Liquidity ÷ debt due in 12 months', x(A.liquidity_to_due12), tone(A.liquidity_to_due12, true, 1, 2.5), big(A.liquidity) + ' vs ' + big(A.due_12m));
    h += card('Average rate paid', pct(A.effective_rate, 2), '', 'interest ÷ debt');
    h += card('Implied 5-year CDS', fin(I.calibrated_5y_bps) ? bp(I.calibrated_5y_bps) : bp(I.spread_5y_bps), tone(I.calibrated_5y_bps || I.spread_5y_bps, false, 120, 400),
      (I.rating_band ? 'spread like ' + esc(I.rating_band) + ' bonds · ' : '') + 'DD ' + num(I.dd, 1));
    h += `</div>`;
    if (A.bank) h += `<p class="dv-sub">A bank borrows mostly from depositors, so the industrial measures (coverage, leverage, the stock-implied spread, the cushion score) are left out; see deposits and CDs below.</p>`;
    if (fin(A.cushion_score)) h += `<div class="dv-score"><span>Debt safety cushion <b>${A.cushion_score}</b>/100</span><div class="dv-bar"><div class="dv-pin" style="left:calc(${A.cushion_score}% - 2px)"></div></div><span class="dv-sub" style="margin:0">riskier ← → safer</span></div>`;
    return h;
  }
  function cushion(d) {
    const A = d.analysis || {};
    const rows = [
      ['Interest coverage (EBIT ÷ interest)', x(A.interest_coverage), tone(A.interest_coverage, true, 2, 6), 'below 2× is thin, above 6× comfortable'],
      ['EBITDA ÷ interest', x(A.ebitda_coverage), tone(A.ebitda_coverage, true, 3, 8), ''],
      ['Cash coverage ((operating cash flow + interest paid) ÷ interest paid)', x(A.cash_coverage), tone(A.cash_coverage, true, 2, 6), ''],
      ['Debt ÷ EBITDA', x(A.leverage), tone(A.leverage, false, 2.5, 4.5), ''],
      ['Net debt ÷ EBITDA', x(A.net_leverage), tone(A.net_leverage, false, 2, 4), ''],
      ['Free cash flow ÷ debt', pct(A.fcf_to_debt), tone(A.fcf_to_debt, true, 0.05, 0.2), 'free cash flow ' + big(A.fcf)],
      ['Liquidity (cash, investments, undrawn revolver)', big(A.liquidity), '', 'undrawn revolver ' + big(A.revolver_available)],
      ['Liquidity ÷ debt due in 12 months', x(A.liquidity_to_due12), tone(A.liquidity_to_due12, true, 1, 2.5), 'due: ' + big(A.due_12m)],
      ['Liquidity ÷ debt due in 24 months', x(A.liquidity_to_due24), tone(A.liquidity_to_due24, true, 0.7, 1.5), 'due: ' + big(A.due_24m)],
      ['Debt ÷ enterprise value', pct(A.debt_to_ev), tone(A.debt_to_ev, false, 0.25, 0.5), 'market cap ' + big(A.market_cap)],
      ['Floating-rate share of debt', pct(A.floating_share), '', 'a +1 percentage point rate move costs ' + big(A.plus100bp_interest) + ' a year' + (fin(A.plus100bp_share_of_ebit) ? ' (' + pct(A.plus100bp_share_of_ebit) + ' of EBIT)' : '')],
      ['Refinancing what is due in 24 months at today’s rate', fin(A.refi_extra_interest) ? (A.refi_extra_interest >= 0 ? '+' : '') + big(A.refi_extra_interest) + ' a year' : '—', fin(A.refi_extra_interest) ? (A.refi_extra_interest > 0 ? 'dv-warn' : 'dv-good') : '',
        fin(A.market_rate_5y) ? 'today ≈ ' + pct(A.market_rate_5y, 2) + ' (5-year Treasury + implied spread) vs ' + pct(A.effective_rate, 2) + ' paid now' : ''],
      ['Altman Z-score', num(A.altman_z, 2), tone(A.altman_z, true, 1.8, 3), 'below 1.8 distress zone, above 3 safe (manufacturers’ formula; not for banks)'],
    ];
    let h = `<h3>Debt safety cushion</h3><p class="dv-sub">How much room the company has before its debt becomes a problem: earnings against interest, debt against earnings, cash against what falls due, and the market’s view through the stock.</p>`;
    h += `<div class="dv-wrap"><table class="dv-tbl"><thead><tr><th>Measure</th><th class="n">Now</th><th>Context</th></tr></thead><tbody>${rows.filter((r) => r[1] !== '—').map((r) => `<tr><td>${esc(r[0])}</td><td class="n ${r[2]}">${r[1]}</td><td>${esc(r[3])}</td></tr>`).join('')}</tbody></table></div>`;
    const cov = A.covenants || [];
    if (cov.length) {
      h += `<h3>Covenant headroom</h3><p class="dv-sub">Financial covenants of the credit agreements against today’s reported figures. The agreements define EBITDA and debt their own way (add-backs, netted cash), so this is an approximation; the cushion is how far earnings (or liquidity) could fall before the limit is reached.</p>`;
      h += `<div class="dv-wrap"><table class="dv-tbl"><thead><tr><th>Covenant</th><th class="n">Limit</th><th class="n">Now ≈</th><th class="n">Cushion</th><th>Agreement</th></tr></thead><tbody>${cov.map((c) => {
        const lim = c.unit === 'usd' ? big(c.limit) : num(c.limit, 2) + '×', act = c.unit === 'usd' ? big(c.actual) : (fin(c.actual) ? num(c.actual, 2) + '×' : '—');
        return `<tr><td>${esc(COV[c.type] || c.type)} <span class="dv-tag">${c.direction === 'max' ? 'at most' : 'at least'}</span><details><summary>wording</summary><q>${esc(c.text || '')}</q></details></td><td class="n">${lim}</td><td class="n">${act}</td><td class="n ${tone(c.cushion, true, 0.1, 0.3)}">${pct(c.cushion, 0)}</td><td>${esc(c.agreement || '')}${c.dated ? ' · ' + day(c.dated) : ''}</td></tr>`;
      }).join('')}</tbody></table></div>`;
    }
    return h;
  }
  function implied(d) {
    const A = d.analysis || {}, I = A.implied || {}, H = d.implied_history || [], F = d.implied_fields || [];
    if (!H.length && !fin(I.dd)) return '';
    const ic = F.indexOf('calibrated_5y_bps'), im = F.indexOf('model_5y_bps');
    const ser = [];
    if (ic >= 0) ser.push({ pts: H.map((r) => [t(r[0]), r[ic]]), col: C.acc, label: 'implied 5-year CDS' });
    else ser.push({ pts: H.map((r) => [t(r[0]), r[im]]), col: C.acc, label: 'Merton 5-year spread' });
    const dots = (d.issues || []).filter((s) => fin(s.spread_bps) && !s.convertible && s.currency === 'USD').map((s) => [t(s.date), s.spread_bps, `${s.title || ''} · ${day(s.date)} · ${bp(s.spread_bps)} over Treasuries`, 3 + Math.min(5, Math.sqrt((s.principal || 0) / 5e8)), C.prev]);
    let h = `<h3>Credit risk priced by the market</h3><p class="dv-sub">No free CDS quotes exist, so the spread is implied from the stock (Merton model: equity as an option on the company’s assets, debt as the strike) and calibrated on the spreads real bonds were priced at. Distance to default <b>${num(I.dd, 2)}</b> standard deviations; one-year risk-neutral default probability ${pct(I.pd_1y, 2)}; model spread ${bp(I.spread_5y_bps)}, calibrated ${bp(I.calibrated_5y_bps)}${I.rating_band ? ', in line with ' + esc(I.rating_band) + '-rated bonds today' : ''}. Purple dots: this company’s bonds at pricing (spread over Treasuries).</p>`;
    h += lineChart(ser, { title: 'Implied CDS history', fy: (v) => num(v, 0) + ' bp', y0: 0, dots });
    const ifc = A.if_converted;
    if (ifc) h += convertedPanel(d);
    return h;
  }
  function convertedPanel(d) {
    const A = d.analysis || {}, I = A.implied || {}, c = A.if_converted;
    return `<div class="dv-two"><div><h3>As debt</h3><table class="dv-tbl"><tbody><tr><td>Total debt</td><td class="n">${big(A.total_debt)}</td></tr><tr><td>Debt ÷ EBITDA</td><td class="n">${x(A.leverage)}</td></tr><tr><td>Interest coverage</td><td class="n">${x(A.interest_coverage)}</td></tr><tr><td>Implied 5-year CDS</td><td class="n">${bp(I.calibrated_5y_bps || I.spread_5y_bps)}</td></tr></tbody></table></div>
      <div><h3>If the in-the-money convertibles convert</h3><table class="dv-tbl"><tbody><tr><td>Total debt</td><td class="n">${big(c.total_debt)}</td></tr><tr><td>Debt ÷ EBITDA</td><td class="n">${x(c.leverage)}</td></tr><tr><td>Interest coverage</td><td class="n">${x(c.interest_coverage)}</td></tr><tr><td>Implied 5-year CDS</td><td class="n">${bp(c.implied_5y_bps)}</td></tr><tr><td>New shares (dilution)</td><td class="n">${num(c.shares_added / 1e6, 1)}M (${pct(c.dilution)})</td></tr></tbody></table></div></div>`;
  }
  function maturities(d) {
    const s = d.snapshot || {}, M = s.maturities, A = d.analysis || {};
    if (!M) return '';
    const yr = M.as_of ? +M.as_of.slice(0, 4) : null;
    const bars = [['next12m', 'next 12m'], ['rest_of_year', 'rest of year'], ['y2', 'year 2'], ['y3', 'year 3'], ['y4', 'year 4'], ['y5', 'year 5'], ['after5', 'later']]
      .filter(([k]) => fin(M[k])).map(([k, l]) => ({ label: l, v: M[k], col: k === 'next12m' || k === 'rest_of_year' ? C.warn : C.acc }));
    return `<h3>Maturity wall</h3><p class="dv-sub">Principal falling due each year (as of ${day(M.as_of)}), against today’s liquidity (cash, short-term investments and the undrawn revolver, dashed).</p>` + barChart(bars, { ref: A.liquidity, refLabel: 'liquidity ' + big(A.liquidity), title: 'Maturities' });
  }
  function instruments(d) {
    const L = d.instruments || [];
    if (!L.length) return '';
    const rate = (i) => fin(i.coupon) ? pct(i.coupon, 3) : fin(i.coupon_min) ? pct(i.coupon_min, 2) + '–' + pct(i.coupon_max, 2) : i.reference || fin(i.spread) || fin(i.spread_min) ? `${esc(i.reference || 'floating')} + ${fin(i.spread) ? pct(i.spread, 2) : pct(i.spread_min, 2) + '–' + pct(i.spread_max, 2)}` : fin(i.rate_now) ? pct(i.rate_now, 2) + ' now' : '—';
    const amt = (i) => i.kind === 'revolver' && fin(i.capacity) ? `${big(i.capacity)} line${fin(i.drawn) ? ', drawn ' + big(i.drawn) : ''}${fin(i.available) ? ', available ' + big(i.available) : ''}` : big(i.carrying != null ? i.carrying : i.face);
    return `<h3>What it owes — instrument by instrument</h3><p class="dv-sub">From the XBRL of the ${esc((d.instruments_from || {}).form || '')} for ${day((d.instruments_from || {}).date)}: each bond, loan and facility tagged on its own (some companies tag only groups, with coupon ranges).</p><div class="dv-wrap"><table class="dv-tbl"><thead><tr><th>Instrument</th><th>Type</th><th class="n">Rate</th><th class="n">Amount</th><th class="n">Effective rate</th><th class="n">Matures</th><th class="n">Fair value</th></tr></thead><tbody>${L.map((i, k) => `<tr${k >= 15 ? ' class="dv-more" hidden' : ''}><td>${esc(i.name)}${i.from_10k ? '<span class="dv-tag">10-K</span>' : ''}</td><td>${esc(KIND[i.kind] || i.kind)}${i.floating ? '<span class="dv-tag">floating</span>' : ''}</td><td class="n">${rate(i)}</td><td class="n">${amt(i)}</td><td class="n">${fin(i.effective) ? pct(i.effective, 2) : fin(i.effective_min) ? pct(i.effective_min, 2) + '–' + pct(i.effective_max, 2) : '—'}</td><td class="n">${esc(i.maturity || i.maturity_year || '—')}</td><td class="n">${big(i.fair_value)}</td></tr>`).join('')}</tbody></table></div>${L.length > 15 ? `<button type="button" class="dv-show" onclick="this.previousElementSibling.querySelectorAll('.dv-more').forEach(r=>r.hidden=false);this.remove()">Show all ${L.length} instruments</button>` : ''}`;
  }
  function issues(d) {
    const L = d.issues || [];
    if (!L.length) return '';
    const shown = L.slice(0, 60);
    return `<h3>Bonds it has sold — priced terms</h3><p class="dv-sub">${L.length} tranches from pricing term sheets (FWP) and prospectus covers: coupon, size, price, yield and the spread over Treasuries the market charged on the day. Newer issues first.</p><div class="dv-wrap"><table class="dv-tbl"><thead><tr><th>Priced</th><th>Security</th><th class="n">Size</th><th class="n">Coupon</th><th class="n">Price</th><th class="n">Yield</th><th class="n">Treasury</th><th class="n">Spread</th><th>Matures</th><th>Ratings</th></tr></thead><tbody>${shown.map((s) => `<tr><td>${day(s.date)}</td><td>${link(s.url, s.title || 'term sheet')}${s.convertible ? `<span class="dv-tag">convertible${fin(s.conv_price) ? ' @ $' + num(s.conv_price, 2) : ''}</span>` : ''}${s.floating ? '<span class="dv-tag">floating</span>' : ''}${s.currency && s.currency !== 'USD' ? `<span class="dv-tag">${esc(s.currency)}</span>` : ''}</td><td class="n">${s.currency === 'USD' || !s.currency ? big(s.principal) : num((s.principal || 0) / 1e6, 0) + 'M ' + esc(s.currency)}</td><td class="n">${s.floating ? (fin(s.margin_bps) ? esc(s.reference || 'SOFR') + ' + ' + num(s.margin_bps, 0) + ' bp' : 'floating') : fin(s.coupon) ? num(s.coupon, 3) + '%' : '—'}</td><td class="n">${fin(s.price) ? num(s.price, 3) : '—'}</td><td class="n">${fin(s.yield) ? num(s.yield, 3) + '%' : '—'}</td><td class="n">${fin(s.bench_yield) ? num(s.bench_yield, 3) + '%' : '—'}</td><td class="n">${bp(s.spread_bps)}</td><td>${esc(s.maturity || s.maturity_year || '')}</td><td>${esc((s.ratings || '').slice(0, 60))}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function facilities(d) {
    const L = d.agreements || [];
    if (!L.length) return '';
    const sofr = (d.market || {}).sofr;
    return `<h3>Bank loans and credit facilities</h3><p class="dv-sub">Read from the credit agreements filed as exhibits: size, pricing over the benchmark (the margin usually moves with ratings or leverage), fees and financial covenants. SOFR today ${pct(sofr, 2)}.</p>` + L.map((a) => {
      const cov = (a.covenants || []);
      return `<div class="dv-card" style="margin:8px 0"><b style="font-size:15px">${link(a.url, a.title || 'Credit agreement')}</b><i>${esc(a.agreement_kind === 'amendment' ? 'Amendment' : 'Agreement')} dated ${day(a.dated || a.date)}${a.size ? ' · ' + big(a.size) : ''}${a.facility ? ' · ' + esc(a.facility) : ''}${a.maturity ? ' · matures ' + day(a.maturity) : ''}</i>
        <table class="dv-tbl" style="margin-top:6px"><tbody>${a.benchmarks ? `<tr><td>Benchmarks</td><td>${esc(a.benchmarks.join(', '))}</td></tr>` : ''}${a.margin_pct ? `<tr><td>Margin over the benchmark</td><td>${num(a.margin_pct[0], 3)}%${a.margin_pct[1] !== a.margin_pct[0] ? ' – ' + num(a.margin_pct[1], 3) + '%' : ''}${a.grid_by ? ' (grid by ' + esc(a.grid_by) + ')' : ''}${a.all_in_pct ? ' · all-in today ≈ ' + num(a.all_in_pct[0], 2) + '–' + num(a.all_in_pct[1], 2) + '%' : ''}</td></tr>` : ''}${fin(a.fee_pct) ? `<tr><td>Commitment / facility fee</td><td>${num(a.fee_pct, 3)}%</td></tr>` : ''}${fin(a.floor_pct) ? `<tr><td>Benchmark floor</td><td>${num(a.floor_pct, 2)}%</td></tr>` : ''}
        ${cov.map((c) => `<tr><td>${esc(COV[c.type] || c.type)} <span class="dv-tag">${c.maintenance ? 'maintenance' : 'incurrence test'}</span></td><td>${c.direction === 'max' ? 'at most ' : 'at least '}${c.unit === 'usd' ? big(c.limit) : num(c.limit, 2) + '×'}<details><summary>wording</summary><q>${esc(c.text || '')}</q></details></td></tr>`).join('')}</tbody></table></div>`;
    }).join('');
  }
  function converts(d) {
    const c = (d.analysis || {}).convertibles;
    if (!c || !c.notes || !c.notes.length) return '';
    return `<h3>Convertible notes — debt that may become shares</h3><p class="dv-sub">Above its conversion price a convertible behaves like equity: holders convert, the debt goes away and shares are added. Stock at ${fin(d.price) ? '$' + num(d.price, 2) : '—'}${d.price_date ? ' (' + day(d.price_date) + ')' : ''}. In the money: ${big(c.in_the_money_face)} of ${big(c.total_face)}${fin(c.dilution) ? ', ' + pct(c.dilution) + ' dilution if converted' : ''}.</p>
      <div class="dv-wrap"><table class="dv-tbl"><thead><tr><th>Note</th><th class="n">Face</th><th class="n">Coupon</th><th class="n">Conversion price</th><th>Stock ÷ conversion price</th><th class="n">Shares if converted</th></tr></thead><tbody>${c.notes.map((n) => {
        const m = n.moneyness, w = fin(m) ? Math.min(100, m * 50) : 0;
        return `<tr><td>${esc(n.name)}</td><td class="n">${big(n.face)}</td><td class="n">${fin(n.coupon) ? pct(n.coupon, 3) : '—'}</td><td class="n">${fin(n.conv_price) ? '$' + num(n.conv_price, 2) : '—'}</td><td><div class="dv-moneybar" title="${fin(m) ? num(m, 2) + '× — ' + (m >= 1 ? 'in the money' : 'out of the money') : ''}"><i style="width:${w}%;background:${m >= 1 ? C.good : C.mute}"></i><i style="left:50%;width:2px;background:${C.ink}"></i></div><small>${fin(m) ? num(m, 2) + '×' : ''}</small></td><td class="n">${fin(n.shares) ? num(n.shares / 1e6, 2) + 'M' : '—'}</td></tr>`;
      }).join('')}</tbody></table></div>` + (c.in_the_money_face ? '' : '<p class="dv-sub">None is in the money now, so the analysis treats them as debt; the as-converted view appears when the stock passes a conversion price.</p>');
  }
  function bank(d) {
    const b = d.bank;
    if (!b) return '';
    const L = b.latest || {}, S = b.series || [];
    const comp = [['Time deposits under $100k', L.time_small, '#5b8def'], ['Time deposits $100k–$250k', L.time_100_250k, '#3a63c4'], ['Time deposits over $250k (large CDs)', L.time_over_250k, '#22408f'], ['Money market', L.money_market, '#6bbf8a'], ['Other deposits', (L.deposits || 0) - (L.time || 0) - (L.money_market || 0), '#b9c2cc']];
    const tot = comp.reduce((a, c) => a + Math.max(0, c[1] || 0), 0) || 1;
    let h = `<h3>Deposits and CDs — ${esc(b.bank)}</h3><p class="dv-sub">The holding company’s largest bank (FDIC call report, ${day(L.date)}). Certificates of deposit are the bank’s own fixed-rate borrowing from savers; large CDs (over $250k) are uninsured and quickest to leave.</p>`;
    h += `<div class="dv-cards">${card('Deposits', big(L.deposits))}${card('Share in CDs (time deposits)', pct(b.cd_share), '', big(L.time))}${card('Uninsured deposits', pct(b.uninsured_share), tone(b.uninsured_share, false, 0.3, 0.5), big(L.uninsured))}${card('Brokered deposits', big(L.brokered))}${card('Deposit cost (annualised)', pct(L.deposit_cost, 2))}${card('Cost of funds', pct(L.cost_of_funds, 2))}${card('Net interest margin', pct(L.nim, 2))}</div>`;
    h += `<svg viewBox="0 0 600 34" role="img" aria-label="Deposit mix">${(() => { let x0 = 0, s = ''; for (const [l, v, col] of comp) { const w = 600 * Math.max(0, v || 0) / tot; s += `<rect x="${x0}" y="4" width="${w}" height="22" fill="${col}"><title>${esc(l)}: ${big(v)} (${pct((v || 0) / tot)})</title></rect>`; x0 += w; } return s; })()}</svg><div class="dv-legend">${comp.map(([l, , col]) => `<span style="--k:${col}">${esc(l)}</span>`).join('')}</div>`;
    const ser = [{ pts: S.map((r) => [t(r.date), fin(r.deposit_cost) ? 100 * r.deposit_cost : null]), col: C.acc, label: 'deposit cost' }, { pts: S.map((r) => [t(r.date), fin(r.cost_of_funds) ? 100 * r.cost_of_funds : null]), col: C.warn, label: 'cost of funds', dash: '4 3' }];
    if ((d.market_series || {}).fedfunds) ser.push({ pts: d.market_series.fedfunds.map((r) => [t(r[0]), r[1]]), col: C.mute, label: 'fed funds', dash: '2 3' });
    h += lineChart(ser, { title: 'Deposit cost', fy: (v) => num(v, 1) + '%', y0: 0 });
    const cd = [{ pts: S.map((r) => [t(r.date), r.domestic ? 100 * (r.time || 0) / r.domestic : null]), col: '#22408f', label: 'CDs % of deposits' }, { pts: S.map((r) => [t(r.date), r.deposits ? 100 * (r.uninsured || 0) / r.deposits : null]), col: C.bad, label: 'uninsured %', dash: '4 3' }];
    h += lineChart(cd, { title: 'CD share', fy: (v) => num(v, 0) + '%', y0: 0 });
    return h;
  }
  function historyChart(d) {
    const H = d.history || [];
    if (H.length < 3) return '';
    const debt = { pts: H.map((r) => [t(r[0]), fin(r[1]) ? r[1] / 1e9 : null]), col: C.acc, label: 'debt' };
    const cash = { pts: H.map((r) => [t(r[0]), fin(r[2]) ? r[2] / 1e9 : null]), col: C.good, label: 'cash + investments', dash: '4 3' };
    const ebitda = { pts: H.map((r) => [t(r[0]), fin(r[4]) ? r[4] / 1e9 : null]), col: C.warn, label: 'EBITDA (12m)', dash: '2 3' };
    const rate = H.map((r) => [t(r[0]), fin(r[6]) ? 100 * r[6] : null]);
    const cov = H.map((r) => [t(r[0]), fin(r[3]) && fin(r[5]) && r[3] > 0 ? r[5] / r[3] : null]);
    let h = `<h3>Since 2009</h3><p class="dv-sub">Quarter-end figures as filed: debt, cash and twelve-month EBITDA ($ billions); the average rate paid (interest ÷ debt) and interest coverage.</p>`;
    h += lineChart([debt, cash, ebitda], { title: 'Debt history', fy: (v) => '$' + num(v, 0) + 'B', y0: 0 });
    h += `<div class="dv-two"><div>${lineChart([{ pts: rate, col: C.acc, label: 'rate paid' }], { title: 'Average rate', fy: (v) => num(v, 1) + '%', y0: 0, w: 420, h: 180 })}</div><div>${lineChart([{ pts: cov, col: C.good, label: 'EBIT ÷ interest' }], { title: 'Coverage', fy: (v) => num(v, 0) + '×', y0: 0, w: 420, h: 180 })}</div></div>`;
    return h;
  }
  function events(d) {
    const L = d.events || [];
    if (!L.length) return '';
    const it = { '1.01': 'material agreement', '2.03': 'new financial obligation', '2.04': 'acceleration / trigger event' };
    return `<details><summary>Financing events in 8-Ks (${L.length})</summary><table class="dv-tbl"><tbody>${L.slice(0, 40).map((e) => `<tr><td>${day(e.date)}</td><td>${(e.items || '').split(',').filter((k) => it[k]).map((k) => esc(it[k])).join(', ')}</td><td>${link(`https://www.sec.gov/Archives/edgar/data/${d.cik}/${String(e.acc).replace(/-/g, '')}/${e.doc}`, e.desc || '8-K')}</td></tr>`).join('')}</tbody></table></details>`;
  }
  function sources(d) {
    const S = d.sources || {};
    const keys = Object.keys(S);
    return `<p class="dv-note">Sources: the company’s XBRL (SEC companyfacts and the ${esc((d.instruments_from || {}).form || '10-K')} instance), pricing term sheets and prospectus covers, credit agreements and 8-Ks on EDGAR${d.bank ? ', the FDIC call reports' : ''}, Treasury and SOFR rates from FRED, weekly closes for the stock. Implied CDS is a model estimate, not a traded quote. Covenant headroom uses reported figures, not the agreements’ own definitions. Collected ${day(d.fetched_at)}.${keys.length ? `<details><summary>XBRL tags used</summary>${keys.map((k) => `${esc(k)}: <code>${esc(S[k])}</code>`).join('<br>')}</details>` : ''}</p>`;
  }

  function render(el, d, opt = {}) {
    css();
    if (!d) { el.innerHTML = '<p class="dv-sub">No debt data for this company yet.</p>'; return; }
    el.classList.add('dv');
    const parts = [summary(d), cushion(d), implied(d), maturities(d), converts(d), instruments(d), facilities(d), issues(d), bank(d), historyChart(d), events(d), sources(d)];
    el.innerHTML = parts.join('');
  }
  window.DebtView = { render, big, pct, bp, x, esc };
})();
