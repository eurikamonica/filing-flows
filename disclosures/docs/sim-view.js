/* Simulations for the companies a regular DCF cannot value — the "rnpv" and "schwartz_moon" blocks of a Fair value
   document (app/valuation_sim.py), drawn inside fairvalue-view.js: the pipeline rNPV solved from the price (drug
   developers) and the Schwartz–Moon simulation (companies losing money or burning cash). Static SVG in the host's colours.
   window.SimView = { mount(el, doc) }. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, 2) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 0) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const C = { good: 'var(--mk-profit, #2e8b57)', bad: 'var(--mk-cost, #c0392b)', acc: 'var(--accent, #2a78d6)', mute: 'var(--muted, #888)', ink: 'var(--ink, #222)', grey: 'var(--mk-rev, #8a8f98)' };
  const card = (label, value, cls = '', note = '') => `<div class="fv-card"><span>${esc(label)}</span><b class="${cls}">${value}</b>${note ? `<i>${note}</i>` : ''}</div>`;
  const tbl = (head, rows, numeric = []) => rows.length ? `<div class="fv-wrap"><table class="fv-tbl"><thead><tr>${head.map((x, i) => `<th${numeric.includes(i) ? ' class="n"' : ''}>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${numeric.includes(i) ? ' class="n"' : ' style="white-space:normal"'}>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '';
  const calcHtml = (c, title) => (c ? `<details class="fv-apx"><summary><b>${esc(title)}</b> — the formula with this company's numbers, every input and assumption</summary><p class="fv-f">${esc(c.formula)}</p>`
    + `<ol class="fv-steps">${(c.steps || []).filter(Boolean).map((x) => `<li>${esc(x)}</li>`).join('')}</ol>`
    + tbl(['Input', 'Value', 'Source'], (c.inputs || []).map((r) => r.map(esc))) + tbl(['Assumption', 'Value', 'Basis'], (c.assumptions || []).map((r) => r.map(esc))) + '</details>' : '');

  // ---------- charts ----------
  // lines over years 0..T on a 0–100% scale: [{name, values (years 1..T), colour, start}]
  function shareLines(series, T, label) {
    const W = 640, H = 210, L = 40, R = 14, Tp = 12, B = 26;
    const X = (t) => L + t / T * (W - L - R), Y = (v) => Tp + (1 - v) * (H - Tp - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
    for (let k = 0; k <= 4; k++) { const v = k / 4; s += `<line class="fv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${pct(v)}</text>`; }
    for (let t = 0; t <= T; t++) s += `<text x="${X(t)}" y="${H - 8}" text-anchor="middle">${t}</text>`;
    series.forEach((sr) => {
      const pts = [[0, sr.start]].concat(sr.values.map((v, i) => [i + 1, v]));
      s += `<polyline fill="none" stroke="${sr.colour}" stroke-width="2.2"${sr.dash ? ' stroke-dasharray="6 4"' : ''} points="${pts.map(([t, v]) => `${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')}"/>`;
      pts.forEach(([t, v]) => { s += `<circle cx="${X(t).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="2.6" fill="${sr.colour}"><title>${esc(sr.name)}, year ${t}: ${pct(v)}</title></circle>`; });
    });
    return s + '</svg>';
  }
  // a fan: [[p10, p50, p90]] by year 1..T with the starting value at year 0
  function fan(rows, start, fmt, label, zero) {
    const W = 310, H = 180, L = 52, R = 10, Tp = 10, B = 24, T = rows.length;
    if (!T) return '';
    const vals = rows.flat().concat([start]).filter(fin);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (!(hi > lo)) hi = lo + 1;
    const X = (t) => L + t / T * (W - L - R), Y = (v) => Tp + (hi - v) / (hi - lo) * (H - Tp - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">`;
    for (let k = 0; k <= 3; k++) { const v = lo + (hi - lo) * k / 3; s += `<line class="fv-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 4}" y="${Y(v) + 4}" text-anchor="end">${esc(fmt(v))}</text>`; }
    if (zero && lo < 0 && hi > 0) s += `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="${C.ink}" stroke-width="1"/><text x="${W - R}" y="${Y(0) - 3}" text-anchor="end">break-even</text>`;
    const s0 = fin(start) ? start : rows[0][1];
    const up = [[0, s0]].concat(rows.map((r, i) => [i + 1, r[2]])), dn = [[0, s0]].concat(rows.map((r, i) => [i + 1, r[0]])).reverse();
    s += `<polygon fill="${C.acc}" opacity="0.18" points="${up.concat(dn).map(([t, v]) => `${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')}"/>`;
    s += `<polyline fill="none" stroke="${C.acc}" stroke-width="2" points="${[[0, s0]].concat(rows.map((r, i) => [i + 1, r[1]])).map(([t, v]) => `${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')}"/>`;
    rows.forEach((r, i) => { s += `<rect x="${X(i + 1) - 6}" y="${Tp}" width="12" height="${H - Tp - B}" fill="transparent"><title>Year ${i + 1}: ${esc(fmt(r[0]))} – ${esc(fmt(r[2]))}, median ${esc(fmt(r[1]))}</title></rect>`; });
    for (let t = 0; t <= T; t += 2) s += `<text x="${X(t)}" y="${H - 8}" text-anchor="middle">${t}</text>`;
    return s + '</svg>';
  }
  function histogram(b, price) {
    const h = b.hist || {}, cs = h.counts || [];
    if (!cs.length || !(h.hi > h.lo)) return '';
    const W = 640, H = 190, L = 40, R = 12, T = 16, B = 26, mx = Math.max(...cs, 1), bw = (W - L - R) / cs.length;
    const X = (v) => L + (v - h.lo) / (h.hi - h.lo) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Schwartz–Moon: value per share across the paths">`;
    cs.forEach((c, i) => { const v = h.lo + (h.hi - h.lo) * (i + 0.5) / cs.length;
      s += `<rect x="${L + i * bw + 0.5}" y="${T + (1 - c / mx) * (H - T - B)}" width="${Math.max(1, bw - 1)}" height="${c / mx * (H - T - B)}" fill="${fin(price) && v > price ? C.good : C.mute}" opacity="0.6"><title>${esc(usd(v))}: ${c} paths</title></rect>`; });
    for (let k = 0; k <= 4; k++) { const v = h.lo + (h.hi - h.lo) * k / 4; s += `<text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(usd(v))}</text>`; }
    const mark = (v, label, dash) => (fin(v) && v >= h.lo && v <= h.hi ? `<line x1="${X(v)}" x2="${X(v)}" y1="${T - 4}" y2="${H - B}" stroke="${C.ink}" ${dash ? 'stroke-dasharray="4 3"' : ''}/><text x="${X(v)}" y="${T - 6}" text-anchor="middle" class="fv-lbl">${esc(label)}</text>` : '');
    return s + mark(price, 'price', true) + mark(b.mean, 'mean', false) + '</svg>';
  }
  // catalysts: a bar to the left for a failure, to the right for a success, as a share of the price
  function catalystRows(cats) {
    const m = Math.max(0.05, ...cats.map((c) => Math.max(Math.abs(c.up_pct || 0), Math.abs(c.down_pct || 0))));
    const bar = (v, col) => `<i style="display:inline-block;height:10px;width:${Math.min(100, Math.abs(v) / m * 100).toFixed(1)}%;background:${col};border-radius:2px;vertical-align:middle"></i>`;
    return cats.map((c) => [esc(c.date), esc(c.drug), 'phase ' + esc(c.phase), pct(c.p_success),
      `<span style="display:flex;gap:6px;align-items:center;min-width:220px"><span style="flex:1;text-align:right">${bar(c.down_pct, C.bad)}</span><span style="width:46px;text-align:right" class="fv-bad">${spct(c.down_pct)}</span><span style="width:46px" class="fv-good">${spct(c.up_pct)}</span><span style="flex:1">${bar(c.up_pct, C.good)}</span></span>`]);
  }

  // ---------- the sections ----------
  function smHtml(d) {
    const b = d.schwartz_moon, price = d.price, I = b.inputs || {}, T = b.years || 10;
    const it = (d.football || []).find((x) => x.method && x.method.startsWith('Schwartz–Moon')) || {};
    const tone = fin(price) ? (b.mean > price * 1.15 ? 'fv-good' : b.mean < price * 0.85 ? 'fv-bad' : '') : '';
    let h = `<h3>Schwartz–Moon simulation: does the cash last?</h3><p class="fv-sub">A company that loses money is a race between its cash and its path to profit. Here revenue growth and the operating margin wander from today's figures — growth fading toward the economy's pace, the margin pulled toward what peers earn — and the company carries its cash balance year by year. On a path where the cash runs out before profits arrive, the shares are worth nothing (Schwartz and Moon's rule); on the others, the cash flows are discounted as in a DCF. ${num(b.n)} paths over ${T} years. Every input is from the filings or estimated across the covered companies; the appendix has the algebra. Shown as a lens: not in the stage-weighted value until the ledger has scored it.</p>`;
    h += `<div class="fv-cards">${card('Mean value', usd(b.mean), tone, fin(price) ? spct(b.mean / price - 1) + ' vs the price' : '')}
      ${card('Middle 80% of paths', `${usd(b.p10)} – ${usd(b.p90)}`, '', `median ${usd(b.p50)}`)}
      ${card('Cash runs out by year 5', pct(b.p_fail5), b.p_fail5 > 0.3 ? 'fv-bad' : b.p_fail5 > 0.1 ? 'fv-warn' : 'fv-good', `by year ${T}: ${pct(b.p_fail10)}${fin(b.runway_years) ? ` · runway today ${num(b.runway_years, 1)} years` : ''}`)}
      ${card('Operating profit by year 5', pct((b.profit_by || [])[4]), '', `by year ${T}: ${pct((b.profit_by || [])[T - 1])}`)}
      ${card('If shortfalls are raised in shares', usd((b.dilution || {}).mean_value), '', `median dilution ${pct((b.dilution || {}).median_new_shares)} at today's price`)}</div>`;
    h += `<div class="fv-wrap">${shareLines([{ name: 'Still has cash', values: b.survival || [], colour: C.ink, start: 1 }, { name: 'Has reached operating profit', values: b.profit_by || [], colour: C.good, start: fin(I.m0) && I.m0 > 0 ? 1 : 0, dash: true }], T, 'Share of paths that still have cash, and that have reached operating profit, by year')}</div>
      <div class="fv-legend"><span style="--k:${C.ink}">still has cash</span><span style="--k:${C.good}">has reached operating profit, dashed (and not failed first)</span><span>x-axis: years from today</span></div>`;
    const rv = (d.inputs || {}).revenue;
    h += `<div class="fv-two"><div><h4 style="margin:10px 0 2px;font-size:14px">Revenue, middle 80% of paths</h4><div class="fv-wrap">${fan((b.fan || {}).revenue || [], rv, big, 'Revenue by year: 10th to 90th percentile and median', false)}</div></div>
      <div><h4 style="margin:10px 0 2px;font-size:14px">Operating margin, middle 80% of paths</h4><div class="fv-wrap">${fan((b.fan || {}).margin || [], I.m0, (v) => pct(v), 'Operating margin by year: 10th to 90th percentile and median', true)}</div></div></div>`;
    h += `<h4 style="margin:12px 0 2px;font-size:14px">Value per share across the paths</h4><p class="fv-sub">${pct(b.p_zero)} of paths end at zero (the cash ran out, or nothing is left after debt). The mean, not the median, is the value of a share that can go to zero: it is the average of all the outcomes.</p><div class="fv-wrap">${histogram(b, price)}</div>`;
    h += tbl(['Input', 'Value', 'Where it comes from'], [
      ['Starting growth', spct(I.g0, 1), I.consensus ? "analysts' consensus, next fiscal year" : 'last four quarters vs the four before'],
      ['Growth persistence φ', num(I.phi, 2), 'how much of this year\'s growth carries into next year, across the covered companies (pooled regression)'],
      ['Growth it fades toward', pct(I.g_bar, 1), 'what companies of its industry and size have grown over five years (the outside view)'],
      ['Growth spread σ', pct(I.sg, 1), 'its own variability of growth, else the panel\'s'],
      ['Operating margin: today → peers\' median', `${pct(I.m0, 1)} → ${pct(I.target_margin, 1)}`, 'the filings; the peer median of its industry and size'],
      ['Margin pace while losing money', `κ ${num(I.kappa_loss, 2)} a year; surprise ${pct((I.sd_loss || [])[0], 1)} + ${num((I.sd_loss || [])[1], 2)} × the loss`, 'how fast loss-making companies\' margins have actually closed the gap since 2010, and how much they jumped around'],
      ['Margin pace once profitable', `κ ${num(I.kappa, 2)} a year; surprise ${pct(I.sd_profit, 1)}`, 'profitable companies across the panel'],
      ['D&A, capex', `${pct(I.da, 1)}, ${pct(I.capex, 1)} of revenue`, 'the filings; capex above D&A moves halfway to it by year 5, as in the base DCF'],
      ['Growth–margin shock correlation ρ', num(I.rho, 2), 'across the covered companies'],
      ['Cash, debt', `${big(I.cash)}, ${big(I.debt)}`, 'latest balance sheet'],
      ['Interest earned on cash / paid on debt', `${pct(I.r_cash, 2)} / ${pct(I.kd, 2)}`, '1-year Treasury / its cost of debt'],
      ['Discount rate (WACC)', pct(I.wacc, 2), 'the cost-of-capital build-up above']].map((r) => [esc(r[0]), esc(r[1]), esc(r[2])]));
    if (it.note) h += `<p class="fv-sub">On the football field: ${esc(it.note)}.</p>`;
    return h;
  }
  function rnpvHtml(d) {
    const r = d.rnpv, price = d.price;
    let h = `<h3>Pipeline: what the price asks the drugs to sell</h3><p class="fv-sub">A drug developer is worth its cash plus a bet on its drug programs. Each program in phase 1, 2 or 3 reaches the market with the industry's historical chance from that phase (the likelihood of approval, LOA — lower for cancer drugs), and an approved drug earns sales that ramp up to a peak, hold, and fall away when its patents expire. No filing says what those peak sales would be, so this runs the risk-adjusted net present value (rNPV) backwards: the yearly peak sales each program would need for today's price to be fair. Compare them with what drugs for the same diseases sell.</p>`;
    h += `<div class="fv-cards">${card('The price pays for the pipeline', big(r.ev), r.ev <= 0 ? 'fv-good' : '', `market value − net cash ${big(r.net_cash)}`)}
      ${card('Peak sales needed, per program', big(r.required_peak) + ' a year', '', `discount rate ±2 points: ${big(r.required_peak_lo)} – ${big(r.required_peak_hi)}`)}
      ${card('…or from the lead program alone', big(r.required_peak_lead) + ' a year', '', esc(r.lead || ''))}
      ${card('Chance no program is approved', pct(r.p_none), r.p_none > 0.6 ? 'fv-bad' : '', `expected approvals ${num(r.expected_approvals, 2)}`)}
      ${card('Net cash per share (floor)', usd(r.net_cash_ps), '', fin(price) ? `${pct(r.net_cash_ps / price)} of the price` : '')}</div>`;
    h += `<h4 style="margin:12px 0 2px;font-size:14px">Programs (${(r.programs || []).length}) — ClinicalTrials.gov, sponsor “${esc(r.sponsor || '')}”</h4><p class="fv-sub">Value / share: what each program adds at the peak sales the price needs, already weighted by its chance of approval and discounted.</p>`;
    h += tbl(['Drug', 'Phase', 'Conditions', 'Next readout', 'Chance of approval', 'Launch in', 'Value / share'], (r.programs || []).map((p) => [
      `${esc(p.drug)}${(p.other_names || []).length ? `<br><span class="fv-sub">also ${esc(p.other_names.join(', '))}</span>` : ''}`, esc(p.phase) + (p.oncology ? ' <span class="fv-tag">oncology</span>' : ''),
      esc(p.conditions || ''), p.active ? esc(p.readout || '—') : 'between phases', pct(p.loa, 1), `${num(p.years_to_launch, 1)} years`, usd(p.value_ps)]), [4, 5, 6]);
    if ((r.catalysts || []).length) {
      h += `<h4 style="margin:12px 0 2px;font-size:14px">Readouts due in the next 18 months</h4><p class="fv-sub">At the peak sales the price implies, a successful readout raises the program's chance of approval and a failure ends it. The two moves are weighted by the chance of success, so the expected move is zero: the price already holds the bet. A large up-move against a small down-move means a long shot; the reverse, a result the price already expects.</p>`;
      h += tbl(['Primary completion', 'Drug', 'Phase', 'Chance of success', 'If it fails · if it succeeds (share of the price)'], catalystRows(r.catalysts), [3]);
    }
    h += calcHtml(r.calc, 'How it is calculated');
    if (r.note) h += `<p class="fv-note">${esc(r.note)}</p>`;
    return h;
  }
  function mount(el, d) {
    let h = '';
    if (d.rnpv) h += rnpvHtml(d);
    else if (d.rnpv_why) h += `<h3>Pipeline: what the price asks the drugs to sell</h3><p class="fv-sub">Not shown for this company: ${esc(d.rnpv_why)}.</p>`;
    if (d.schwartz_moon) h += smHtml(d);
    el.innerHTML = h;
  }

  const api = { mount, shareLines, fan, histogram };
  if (typeof window !== 'undefined') window.SimView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
