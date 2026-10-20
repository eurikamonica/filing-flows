/* Fair value — one company's valuation & credit page, shared by the Disclosure Hub (Valuation tab → one company) and the
   main site's company page ("Fair value" view, listed in views.json). Data: data/research/valuation/c/<cik>.json
   (app/valuation.py, branch research-valuation). window.FairValueView.render(el, {cik, ticker, hub}) loads and draws;
   draw(el, doc, fits) draws a loaded document. Self-contained: colours from the host's CSS variables with fallbacks. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, 1) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const pct = (v, d = 1) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 0) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const C = { good: 'var(--mk-profit, #2e8b57)', bad: 'var(--mk-cost, #c0392b)', warn: 'var(--q-warm, #d9822b)', acc: 'var(--accent, #2a78d6)', mute: 'var(--muted, #888)', ink: 'var(--ink, #222)', line: 'var(--line, #ddd)' };
  const store = {};

  function css() {
    if (typeof document === 'undefined' || document.getElementById('fv-css')) return;
    const s = document.createElement('style'); s.id = 'fv-css';
    s.textContent = `.fv h3{margin:22px 0 6px;font-size:16px}.fv .fv-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45;max-width:78ch}
.fv-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:8px 0 6px}
.fv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 12px}.fv-card b{display:block;font-size:20px;font-variant-numeric:tabular-nums;margin-top:2px}
.fv-card span{font-size:12px;color:var(--muted,#777)}.fv-card i{display:block;font-style:normal;font-size:12px;margin-top:2px;color:var(--muted,#777)}
.fv-good{color:${C.good}}.fv-bad{color:${C.bad}}.fv-warn{color:${C.warn}}
.fv svg{display:block;width:100%;max-width:860px;height:auto;overflow:visible}.fv svg text{font-size:11px;fill:var(--muted,#777)}
.fv svg .fv-lbl{fill:var(--ink,#222);font-size:12px}.fv .fv-grid{stroke:var(--line,#e3e3e3)}
.fv-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.fv-tbl th,.fv-tbl td{padding:6px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.fv-tbl td.n,.fv-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.fv-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}
.fv-wrap{overflow-x:auto}.fv-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
.fv-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:14px;max-width:90ch}.fv-tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line,#ddd);margin-left:6px;color:var(--muted,#777)}
.fv-stack{display:flex;height:22px;border-radius:6px;overflow:hidden;border:1px solid var(--line,#ddd);max-width:640px}.fv-stack i{display:block;height:100%}
.fv-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 6px}.fv-legend span::before{content:'';display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px;background:var(--k)}
.fv-tog{font:inherit;font-size:12px;border:1px solid var(--line,#ddd);background:none;border-radius:8px;padding:3px 9px;cursor:pointer;color:var(--muted,#666);margin-right:6px}.fv-tog.on{color:var(--ink,#222);border-color:var(--ink,#222)}`;
    document.head.appendChild(s);
  }
  const card = (label, value, cls = '', note = '') => `<div class="fv-card"><span>${esc(label)}</span><b class="${cls}">${value}</b>${note ? `<i>${note}</i>` : ''}</div>`;

  // ---------- football field: one bar per method, the price as a line ----------
  function football(rows, price) {
    rows = rows.filter((r) => fin(r.low) && fin(r.high));
    if (!rows.length) return '<p class="fv-sub">No method has enough data for this company yet.</p>';
    const vals = rows.flatMap((r) => [r.low, r.high]).concat(fin(price) ? [price] : []);
    const lo0 = Math.min(...vals), hi0 = Math.max(...vals);
    const cap = fin(price) ? price * 4 : hi0;                // a far-off bar is clipped and marked, not allowed to squash the rest
    const x0 = Math.max(0, Math.min(lo0, fin(price) ? price * 0.5 : lo0) * 0.92), x1 = Math.min(hi0, cap) * 1.06;
    const W = 860, L = 250, R = 30, T = 18, rowH = 26, H = T + rows.length * rowH + 26;
    const X = (v) => L + (Math.min(Math.max(v, x0), x1) - x0) / ((x1 - x0) || 1) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Valuation methods against the share price">`;
    for (let k = 0; k <= 5; k++) { const v = x0 + (x1 - x0) * k / 5; s += `<line class="fv-grid" x1="${X(v)}" x2="${X(v)}" y1="${T - 6}" y2="${H - 22}"/><text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(usd(v))}</text>`; }
    rows.forEach((r, i) => {
      const y = T + i * rowH, ctx = r.method === '52-week trading range';
      const col = ctx ? C.mute : fin(price) && r.high < price ? C.bad : fin(price) && r.low > price ? C.good : C.acc;
      s += `<text class="fv-lbl" x="${L - 10}" y="${y + 15}" text-anchor="end">${esc(r.method.length > 40 ? r.method.slice(0, 39) + '…' : r.method)}</text>`;
      s += `<rect x="${X(r.low)}" y="${y + 5}" width="${Math.max(2, X(r.high) - X(r.low))}" height="14" rx="4" fill="${col}" opacity="${ctx ? 0.35 : 0.55}"><title>${esc(r.method)}: ${esc(usd(r.low))} – ${esc(usd(r.high))}${fin(r.point) ? ' · ' + esc(usd(r.point)) : ''}${r.note ? ' — ' + esc(r.note) : ''}</title></rect>`;
      if (fin(r.point)) s += `<rect x="${X(r.point) - 1.5}" y="${y + 2}" width="3" height="20" fill="${C.ink}"/>`;
      if (r.high > x1) s += `<text x="${W - R + 4}" y="${y + 16}">→</text>`;
    });
    if (fin(price)) s += `<line x1="${X(price)}" x2="${X(price)}" y1="${T - 10}" y2="${H - 22}" stroke="${C.ink}" stroke-width="1.5" stroke-dasharray="4 3"/><text x="${X(price)}" y="${T - 12}" text-anchor="middle" class="fv-lbl">price ${esc(usd(price))}</text>`;
    return s + '</svg>';
  }

  function histogram(mc, price, base) {
    const h = mc.hist || {}, cs = h.counts || [];
    if (!cs.length || !(h.hi > h.lo)) return '';
    const W = 640, H = 200, L = 40, R = 12, T = 16, B = 26, mx = Math.max(...cs, 1), bw = (W - L - R) / cs.length;
    const X = (v) => L + (v - h.lo) / (h.hi - h.lo) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Monte Carlo distribution of value per share">`;
    cs.forEach((c, i) => { const v = h.lo + (h.hi - h.lo) * (i + 0.5) / cs.length, above = fin(price) && v > price;
      s += `<rect x="${L + i * bw + 0.5}" y="${T + (1 - c / mx) * (H - T - B)}" width="${bw - 1}" height="${c / mx * (H - T - B)}" fill="${above ? C.good : C.mute}" opacity="0.6"><title>${esc(usd(v))}: ${c} scenarios</title></rect>`; });
    for (let k = 0; k <= 4; k++) { const v = h.lo + (h.hi - h.lo) * k / 4; s += `<text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(usd(v))}</text>`; }
    const mark = (v, label, dash) => (fin(v) && v >= h.lo && v <= h.hi ? `<line x1="${X(v)}" x2="${X(v)}" y1="${T - 4}" y2="${H - B}" stroke="${C.ink}" ${dash ? 'stroke-dasharray="4 3"' : ''}/><text x="${X(v)}" y="${T - 6}" text-anchor="middle" class="fv-lbl">${esc(label)}</text>` : '');
    return s + mark(price, 'price', true) + mark(base, 'base', false) + '</svg>';
  }

  function bandsChart(b, key) {
    const idx = key === 'pe' ? 1 : 2, st = b[key], pts = (b.series || []).filter((r) => fin(r[idx]));
    if (!st || pts.length < 10) return '<p class="fv-sub">Not enough history for this measure.</p>';
    const W = 640, H = 220, L = 46, R = 50, T = 12, B = 24;
    const ys = pts.map((r) => r[idx]), y0 = Math.min(...ys, st.p10) * 0.95, y1 = Math.max(...ys, st.p90) * 1.05;
    const t0 = Date.parse(pts[0][0]), t1 = Date.parse(pts[pts.length - 1][0]);
    const X = (d) => L + (Date.parse(d) - t0) / ((t1 - t0) || 1) * (W - L - R), Y = (v) => T + (y1 - v) / ((y1 - y0) || 1) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${key === 'pe' ? 'P/E' : 'EV/Sales'} history with percentile bands">`;
    s += `<rect x="${L}" y="${Y(st.p90)}" width="${W - L - R}" height="${Y(st.p10) - Y(st.p90)}" fill="${C.acc}" opacity="0.08"/><rect x="${L}" y="${Y(st.p75)}" width="${W - L - R}" height="${Y(st.p25) - Y(st.p75)}" fill="${C.acc}" opacity="0.14"/>`;
    for (const [k, lbl] of [['p10', '10th'], ['p50', 'median'], ['p90', '90th']]) s += `<line x1="${L}" x2="${W - R}" y1="${Y(st[k])}" y2="${Y(st[k])}" stroke="${C.acc}" stroke-dasharray="3 3" opacity="0.7"/><text x="${W - R + 4}" y="${Y(st[k]) + 4}">${lbl} ${num(st[k], 1)}</text>`;
    s += `<path d="${pts.map((r, i) => (i ? 'L' : 'M') + X(r[0]).toFixed(1) + ',' + Y(r[idx]).toFixed(1)).join('')}" fill="none" stroke="${C.ink}" stroke-width="1.5"/>`;
    const yr0 = new Date(t0).getUTCFullYear(), yr1 = new Date(t1).getUTCFullYear();
    for (let y = yr0 + 1; y <= yr1; y++) { const d = `${y}-01-01`; s += `<text x="${X(d)}" y="${H - 6}" text-anchor="middle">${y}</text>`; }
    for (let k = 0; k <= 3; k++) { const v = y0 + (y1 - y0) * k / 3; s += `<text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${num(v, 1)}</text>`; }
    return s + '</svg>';
  }

  function scatter(fit, own, xl, yl) {
    const P = (fit && fit.points) || [];
    if (P.length < 5) return '';
    const W = 420, H = 260, L = 44, R = 12, T = 12, B = 30;
    const xs = P.map((p) => p[0]).concat(own ? [own[0]] : []), ys = P.map((p) => p[1]).concat(own ? [own[1]] : []);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys, 0), y1 = Math.max(...ys);
    const X = (v) => L + (v - x0) / ((x1 - x0) || 1) * (W - L - R), Y = (v) => T + (y1 - v) / ((y1 - y0) || 1) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(yl)} against ${esc(xl)}">`;
    P.forEach((p) => { s += `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3" fill="${C.mute}" opacity="0.6"><title>${esc(p[2])}: ${esc(xl)} ${pct(p[0])}, ${esc(yl)} ${num(p[1], 2)}×</title></circle>`; });
    s += `<line x1="${X(x0)}" x2="${X(x1)}" y1="${Y(fit.a + fit.b * x0)}" y2="${Y(fit.a + fit.b * x1)}" stroke="${C.acc}" stroke-width="1.5"/>`;
    if (own) s += `<circle cx="${X(own[0])}" cy="${Y(own[1])}" r="6" fill="${C.ink}"><title>this company</title></circle>`;
    s += `<text x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">${esc(xl)}</text><text x="12" y="${T + 10}">${esc(yl)}</text>`;
    return s + '</svg>';
  }

  function draw(el, d, fits) {
    css();
    const price = d.price, W = d.wacc || {}, mc = d.mc, pv = d.pvgo, cr = d.credit || {}, dist = cr.distress, dc = d.dcf;
    const tone = (v) => (!fin(v) ? '' : v > 0.15 ? 'fv-good' : v < -0.15 ? 'fv-bad' : '');
    let h = `<div class="fv"><p class="fv-sub">Many ways to value ${esc(d.name || d.ticker)}, side by side, against the share price ${esc(usd(price))}${d.price_date ? ` (${esc(d.price_date)})` : ''}. Every assumption is shown below and every method has known blind spots — the spread between them is the point. Not investment advice.</p>`;
    h += `<div class="fv-cards">${card('Cost of capital (WACC)', pct(W.wacc), '', W.beta ? `beta ${num(W.beta, 2)} · debt ${pct(W.kd)}` : '')}
      ${card('DCF base case', usd(dc && dc.value), dc ? tone(dc.value / price - 1) : '', dc && fin(price) ? spct(dc.value / price - 1) + ' vs price' : 'no DCF for this company')}
      ${card('Monte Carlo: value > price', mc ? pct(mc.p_above, 0) : '—', '', mc ? `${num(mc.n)} scenarios` : '')}
      ${card('Price paid for growth', pv ? pct(pv.growth_share, 0) : '—', '', pv ? 'PVGO share of market value' : '')}
      ${card('Distress (1 year, model blend)', dist ? pct(dist.pd, dist.pd < 0.01 ? 2 : 1) : '—', dist ? (dist.pd > 0.05 ? 'fv-bad' : dist.pd > 0.01 ? 'fv-warn' : 'fv-good') : '', cr.rating_band ? `spread-implied ${esc(cr.rating_band)}` : '')}</div>`;
    h += `<h3>Valuation football field</h3><p class="fv-sub">Each bar is one method's range, the black tick its central value, the dashed line today's price. Green: the whole range above the price; red: below.</p><div class="fv-wrap">${football(d.football || [], price)}</div>`;
    h += `<div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Method</th><th class="n">Low</th><th class="n">Central</th><th class="n">High</th><th>How</th></tr></thead><tbody>${(d.football || []).map((r) => `<tr><td>${esc(r.method)}</td><td class="n">${usd(r.low)}</td><td class="n">${usd(r.point)}</td><td class="n">${usd(r.high)}</td><td>${esc(r.note || '')}</td></tr>`).join('')}</tbody></table></div>`;
    if (d.reverse && d.reverse.status === 'ok') h += `<p><b>Reverse DCF:</b> today's price needs revenue growth of <b>${pct(d.reverse.implied_growth)}</b> a year for five years (then ${pct((dc && dc.assumptions.g) || 0.025)}), with the margins and cost of capital below. The last four quarters grew ${pct(d.reverse.history_growth)} on the four before.</p>`;
    else if (d.reverse) h += `<p class="fv-sub">Reverse DCF: no single growth rate between −30% and 60% gives today's price with these assumptions.</p>`;
    if (pv) {
      const ng = Math.max(0, Math.min(1, 1 - pv.growth_share));
      h += `<h3>What the price pays for: today's earnings vs growth</h3><p class="fv-sub">No-growth value = ${esc(pv.basis)} (${esc(big(pv.earnings))} at ${pct(pv.rate)}) = ${esc(usd(pv.per_share))} a share. ${pv.growth_share >= 0 ? `The other <b>${pct(pv.growth_share, 0)}</b> of the market value is the present value of growth opportunities (PVGO).` : 'The price is below the no-growth value: the market prices in a decline.'}</p>
        <div class="fv-stack" role="img" aria-label="No-growth value vs growth share"><i style="width:${(ng * 100).toFixed(1)}%;background:${C.acc}"></i><i style="width:${((1 - ng) * 100).toFixed(1)}%;background:${C.warn}"></i></div>
        <div class="fv-legend"><span style="--k:${C.acc}">no-growth value ${pct(ng, 0)}</span><span style="--k:${C.warn}">growth ${pct(1 - ng, 0)}</span></div>`;
    }
    if (mc) h += `<h3>Monte Carlo DCF</h3><p class="fv-sub">${num(mc.n)} scenarios: revenue growth ~ N(${pct(mc.assumptions.growth[0])}, ${pct(mc.assumptions.growth[1])}), EBIT margin ~ N(${pct(mc.assumptions.margin[0])}, ${pct(mc.assumptions.margin[1])}), WACC ~ N(${pct(mc.assumptions.wacc[0])}, 1 pt), terminal growth 1.5–3%. The spreads come from the company's own history. Median ${esc(usd(mc.p50))}, middle 80% ${esc(usd(mc.p10))}–${esc(usd(mc.p90))}; <b>${pct(mc.p_above, 0)}</b> of scenarios are worth more than the price.</p><div class="fv-wrap">${histogram(mc, price, dc && dc.value)}</div>`;
    h += `<div class="fv-two"><div><h3>Cost of capital</h3><table class="fv-tbl"><tbody>
      <tr><td>10-year Treasury</td><td class="n">${pct(W.rf, 2)}</td></tr><tr><td>Beta (weekly vs SPY, ${num(W.beta_weeks)} weeks; Blume-adjusted)</td><td class="n">${num(W.beta_raw, 2)} → ${num(W.beta, 2)}</td></tr>
      <tr><td>Equity risk premium (assumption)</td><td class="n">${pct(W.erp, 1)}</td></tr><tr><td><b>Cost of equity</b></td><td class="n"><b>${pct(W.ke, 2)}</b></td></tr>
      <tr><td>Cost of debt <span class="fv-tag">${esc(W.kd_how || '')}</span></td><td class="n">${pct(W.kd, 2)}</td></tr><tr><td>After tax at ${pct(W.tax, 0)}</td><td class="n">${pct(W.kd_after_tax, 2)}</td></tr>
      <tr><td>Weights: equity / debt (market values)</td><td class="n">${pct(W.w_equity, 0)} / ${pct(W.w_debt, 0)}</td></tr><tr><td><b>WACC</b></td><td class="n"><b>${pct(W.wacc, 2)}</b></td></tr></tbody></table>${W.beta_note ? `<p class="fv-sub">${esc(W.beta_note)}</p>` : ''}</div>`;
    h += `<div><h3>Credit</h3><table class="fv-tbl"><tbody><tr><td>Distance to default (Merton)</td><td class="n">${num(cr.distance_to_default, 1)}</td></tr><tr><td>Merton 1-year default probability</td><td class="n">${pct(cr.merton_pd_1y, 2)}</td></tr>
      <tr><td>5-year spread, bond-calibrated</td><td class="n">${fin(cr.cds_5y_bps) ? num(cr.cds_5y_bps, 0) + ' bp' : '—'}</td></tr><tr><td>Altman Z</td><td class="n">${num(cr.altman_z, 2)}</td></tr><tr><td>Debt cushion score (0–100)</td><td class="n">${num(cr.cushion_score)}</td></tr>
      ${dist ? dist.parts.map((p) => `<tr><td>· ${esc(p.name)} (weight ${pct(p.weight, 0)})</td><td class="n">${pct(p.pd, 2)}</td></tr>`).join('') + `<tr><td><b>Distress probability, 1 year</b></td><td class="n"><b>${pct(dist.pd, 2)}</b></td></tr>` : ''}</tbody></table><p class="fv-sub">${esc(cr.note || '')}</p></div></div>`;
    if (d.bands) {
      h += `<h3>Valuation bands</h3><p class="fv-sub">Weekly since ${esc(d.bands.from || '')}, trailing figures counted 60 days after each quarter ends. Shaded: middle 50% and 80% of the history.${d.bands.pe ? ` P/E now ${num(d.bands.pe.current, 1)} — the ${num(100 * d.bands.pe.pct)}th percentile of its range.` : ''}${d.bands.evs ? ` EV/Sales ${num(d.bands.evs.current, 2)} — the ${num(100 * d.bands.evs.pct)}th percentile.` : ''}</p>
        <div><button type="button" class="fv-tog on" data-fvb="pe">P/E</button><button type="button" class="fv-tog" data-fvb="evs">EV/Sales</button></div><div class="fv-wrap" data-fvbands>${bandsChart(d.bands, d.bands.pe ? 'pe' : 'evs')}</div>`;
    }
    const sm = d.sector_model;
    if (sm) {
      h += `<h3>${esc(sm.model)}</h3>`;
      if (sm.model.startsWith('P/TBV')) h += `<p class="fv-sub">Tangible book ${esc(big(sm.tbv))}; ROTCE ${pct(sm.rotce)}; P/TBV ${num(sm.ptbv, 2)}× vs ${num(sm.fitted_ptbv, 2)}× fitted across ${num(sm.fit && sm.fit.n)} banks (r² ${num(sm.fit && sm.fit.r2, 2)}).</p>${scatter(fits && fits.bank, fin(sm.rotce) && fin(sm.ptbv) ? [sm.rotce, sm.ptbv] : null, 'ROTCE', 'P/TBV')}`;
      else if (sm.model.startsWith('P/B')) h += `<p class="fv-sub">${fin(sm.combined_ratio) ? `Combined ratio ${pct(sm.combined_ratio)} (claims + acquisition and other underwriting costs ÷ premiums earned, trailing four quarters). ` : 'Combined ratio: not tagged in XBRL. '}${fin(sm.roe) ? `ROE ${pct(sm.roe)}; P/B ${num(sm.pb, 2)}× vs ${num(sm.fitted_pb, 2)}× fitted across ${num(sm.fit && sm.fit.n)} insurers.` : ''}</p>${scatter(fits && fits.insurer, fin(sm.roe) && fin(sm.pb) ? [sm.roe, sm.pb] : null, 'ROE', 'P/B')}`;
      else h += `<p class="fv-sub">FFO ${esc(big(sm.ffo))}${fin(sm.p_ffo) ? `; P/FFO ${num(sm.p_ffo, 1)}×` : ''}${sm.peers ? ` vs a REIT median of ${num(sm.peers.p50, 1)}×` : ''}. ${esc(sm.note || '')}</p>`;
    }
    if (d.sotp) h += `<h3>Sum of the parts</h3><table class="fv-tbl"><thead><tr><th>Segment</th><th class="n">Revenue (annualised)</th><th>Priced like</th><th class="n">EV/Sales</th><th class="n">Value</th></tr></thead><tbody>${d.sotp.parts.map((p) => `<tr><td>${esc(p.segment)}</td><td class="n">${big(p.revenue)}</td><td>${esc(String(p.group).replace(/^sic/, 'SIC ').replace(/^sec:/, 'sector '))}</td><td class="n">${num(p.ev_sales, 1)}×</td><td class="n">${big(p.ev)}</td></tr>`).join('')}</tbody></table><p class="fv-sub">${esc(d.sotp.note)}</p>`;
    if ((d.notes || []).length) h += `<p class="fv-note">${d.notes.map(esc).join('<br>')}</p>`;
    const src = Object.entries(d.sources || {}).map(([k, v]) => `${k}: ${v}`).join(' · ');
    h += `<p class="fv-note">Figures from: ${esc(src || '—')}. Built ${esc((d.generated_at || '').slice(0, 10))} by app/valuation.py from SEC filings (XBRL), the hub's daily prices, the Debt & rates and Consensus modules. Peer groups are SIC industries; a group needs six peers.</p></div>`;
    el.innerHTML = h;
    el.querySelectorAll('[data-fvb]').forEach((b) => b.addEventListener('click', () => {
      el.querySelectorAll('[data-fvb]').forEach((x) => x.classList.toggle('on', x === b));
      el.querySelector('[data-fvbands]').innerHTML = bandsChart(d.bands, b.dataset.fvb);
    }));
  }

  function get(url) {
    if (!store[url]) store[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).catch((e) => { delete store[url]; throw e; });
    return store[url];
  }

  async function render(el, ctx) {
    const base = (ctx && ctx.hub != null ? ctx.hub : '') + 'data/research/valuation/';
    el.innerHTML = '<p class="muted">Loading the valuation…</p>';
    let d;
    try { d = await get(base + `c/${Number(ctx.cik)}.json`); } catch (e) {
      el.innerHTML = `<p class="muted">No fair-value page for this company yet (${esc(e.message)}). It is built every weekday after the close for companies with a share price and filed figures.</p>`;
      return;
    }
    if (ctx.here && !ctx.here()) return;
    const fits = {};
    if (d.kind === 'bank') fits.bank = (await get(base + 'banks.json').catch(() => ({}))).fit;
    if (d.kind === 'insurer') fits.insurer = (await get(base + 'insurers.json').catch(() => ({}))).fit;
    draw(el, d, fits);
  }

  const api = { render, draw, football, histogram, bandsChart, usd, pct };
  if (typeof window !== 'undefined') window.FairValueView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
