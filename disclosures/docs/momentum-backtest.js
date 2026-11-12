/* Momentum → Back-test (the hub's Momentum tab, "Universe: Back-test"): what buying the stocks that rose most — or least
   — over a ranking period and holding them for a holding period would have returned since 2000. Data:
   data/research/paths/backtest/momentum.json (app/momentum_backtest.py, the nightly research-paths build): the valued
   companies' daily adjusted closes, the top and bottom tenths (equal weight) and long-short, Jegadeesh & Titman's
   overlapping portfolios, SPY and the equal-weight universe; month-end values, statistics on daily returns, turnover.
   Here: the grid of annual returns (ranking period × holding period), the growth of $1, the statistics and the years,
   with trading costs and the period chosen in the browser — costs are the strategy's daily turnover × the cost of a
   trade, taken off every day; a period rebases the values at its first month-end. */
const MOB_R = [['1', 'The last day'], ['5', 'The last week (5 days)'], ['10', 'The last 2 weeks (10 days)'], ['21', 'The last month (21 days)'],
  ['63', 'The last quarter (63 days)'], ['12-1', '12-1: a year, less the latest month']];
const MOB_RS = { 1: 'Day', 5: 'Week', 10: '2 weeks', 21: 'Month', 63: 'Quarter', '12-1': '12-1' };
const MOB_RN = { 1: 'Day', 5: 'Week', 10: '2 wks', 21: 'Month', 63: 'Qtr', '12-1': '12-1' };      // a phone's grid
const MOB_H = [['1', '1 day'], ['5', '1 week'], ['10', '2 weeks'], ['21', '1 month'], ['63', '1 quarter']];
const MOB_S = [['top', 'Top tenth: the biggest risers'], ['bottom', 'Bottom tenth: the biggest fallers'], ['ls', 'Long-short: top less bottom']];
const MOB_C = [['0', 'None (theoretical)'], ['5', '0.05% a trade'], ['10', '0.10% a trade'], ['25', '0.25% a trade']];
const MOB_P = [['all', 'Since 2000'], ['10y', 'The last 10 years'], ['5y', 'The last 5 years']];
const mobStore = {};
const mobFin = v => v != null && Number.isFinite(+v);
const mobPc = (v, d = 1) => (mobFin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—');
const mobTone = (v, s) => (mobFin(v) && v !== 0 ? `<span class="${v > 0 ? 'positive' : 'negative'}">${s}</span>` : s);
const mobAbs = (v, d = 1) => (mobFin(v) ? (100 * v).toFixed(d) + '%' : '—');
const mobNarrow = () => typeof innerWidth === 'number' && innerWidth < 560;
function mobData() {
  const m = mobStore.bt || (mobStore.bt = {});
  if (m.data || m.err || m.loading) return m;
  if (typeof fetch !== 'function') { m.err = 'this browser cannot load data files'; return m }
  m.loading = fetch((globalThis.FF_HUB_ROOT || '') + 'data/research/paths/backtest/momentum.json', { cache: 'no-cache' })
    .then(r => { if (!r.ok) throw Error(r.status === 404 ? 'not built yet' : 'HTTP ' + r.status); return r.json() })
    .then(d => { if (!d || d.schema !== 'momentum-backtest.v1') throw Error('an unexpected file'); m.data = d })
    .catch(e => { m.err = e.message })
    .finally(() => { m.loading = null; if (typeof state === 'object' && state.tab === 'momentum' && typeof render === 'function') render() });
  return m;
}
// a strategy's month-end values after costs (each day: 1 − cost × turnover), rebased at the period's start
function mobLine(d, key, cost, period) {
  const s = (d.series || {})[key];
  if (!s) return null;
  const turn = (d.turn || {})[key] || 0, f = Math.max(0, 1 - cost * turn), t0 = Date.parse(d.start);
  const p0 = (d.periods || {})[period] || d.start;
  const days = m => Math.max(0, (Date.parse(m) - t0) / 864e5 * 252 / 365.25);
  const net = s.map((v, i) => (mobFin(v) ? v * Math.pow(f, days(d.months[i])) : null));
  // the base: the last month-end before the period's start (or the start itself, at 1)
  let b = -1;
  for (let i = 0; i < d.months.length; i++) if (d.months[i] < p0) b = i;
  const base = b >= 0 ? net[b] : 1, from = b >= 0 ? d.months[b] : d.start;
  const pts = [[from, 1]];
  for (let i = b + 1; i < d.months.length; i++) if (mobFin(net[i]) && net[i] > 0 && base > 0) pts.push([d.months[i], net[i] / base]);
  return { pts, f, turn };
}
// dollars: $140k, $1,234, $8.06, $0.000016
function mobUsd(v) {
  if (!mobFin(v)) return '—';
  return v >= 1e6 ? '$' + (v / 1e6).toFixed(v >= 1e7 ? 0 : 1) + 'M' : v >= 1e4 ? '$' + Math.round(v / 1e3) + 'k' : v >= 100 ? '$' + Math.round(v).toLocaleString('en-US')
    : v >= 0.01 ? '$' + v.toFixed(2) : '$' + v.toPrecision(2);
}
// a log axis's ticks between e^lo and e^hi: 1-2-5 a decade, every decade on a wide range, finer on a narrow one
function mobTicks(lo, hi) {
  const dec = (hi - lo) / Math.LN10, ms = dec > 3.2 ? [1] : dec > 0.8 ? [1, 2, 5] : [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8], out = [];
  for (let e = Math.floor(lo / Math.LN10) - 1; e <= Math.ceil(hi / Math.LN10); e++)
    for (const m of ms) { const v = +(m * Math.pow(10, e)).toPrecision(6); if (Math.log(v) >= lo && Math.log(v) <= hi) out.push(v) }
  return out;
}
const mobTick = v => (v >= 1e6 ? `$${+(v / 1e6).toPrecision(3)}M` : v >= 1e3 ? `$${+(v / 1e3).toPrecision(3)}k` : v >= 0.001 ? `$${+v.toPrecision(3)}` : `$${v.toExponential(0)}`);
// the annual return after costs for a period: the gross one from the file, the daily drag taken off over a year
function mobCagr(d, key, cost, period) {
  const st = (((d.stats || {})[key] || {})[period]) || null;
  if (!st || !mobFin(st.cagr)) return null;
  const f = Math.max(0, 1 - cost * ((d.turn || {})[key] || 0));
  return (1 + st.cagr) * Math.pow(f, 252) - 1;
}
// calendar years from the month-end values: each December to the next, the first year from the start, this year to date
function mobYears(pts) {
  const out = [];
  let prev = pts[0];
  for (let i = 1; i < pts.length; i++) {
    const [m, v] = pts[i], y = m.slice(0, 4), last = i === pts.length - 1 || pts[i + 1][0].slice(0, 4) !== y;
    if (last) { out.push([y, v / prev[1] - 1, i === pts.length - 1 && m.slice(5, 7) !== '12']); prev = pts[i] }
  }
  return out;
}
// the grid's colours: against the equal-weight average of the same companies (it shares their survivorship, so the gap
// is what the ranking added), long-short against zero
function mobGrid(d, side, cost, period, narrow) {
  const bench = side === 'ls' ? 0 : mobCagr(d, 'ew', 0, period);
  const cell = (r, h) => {
    const v = mobCagr(d, `${r}|${h}|${side}`, cost, period), on = String(state.mobr) === r && String(state.mobh) === h;
    if (!mobFin(v)) return `<td class="num">—</td>`;
    const x = v - (bench || 0), a = Math.min(1, Math.abs(x) / 0.15), col = x >= 0 ? 'var(--mk-profit)' : 'var(--mk-cost)';
    return `<td class="num mob-cell${on ? ' mob-on' : ''}" style="background:color-mix(in srgb, ${col} ${Math.round(8 + 42 * a)}%, transparent)"><button type="button" class="text-button" data-mob="${r}|${h}" aria-pressed="${on}" title="Ranked by ${esc(MOB_RS[r])}, held ${esc((MOB_H.find(z => z[0] === h) || [])[1])}: ${mobPc(v)} a year">${mobPc(v, narrow ? 0 : 1)}</button></td>`;
  };
  return `<div class="tablebox"><table class="mob-grid"><thead><tr><th>${narrow ? 'Rank ↓<br>Hold →' : 'Ranked by ↓ · held →'}</th>${MOB_H.map(([h, l]) => `<th class="num">${esc(narrow ? MOB_RN[h] : l)}</th>`).join('')}</tr></thead><tbody>`
    + MOB_R.map(([r]) => `<tr><th scope="row">${esc((narrow ? MOB_RN : MOB_RS)[r])}</th>${MOB_H.map(([h]) => cell(r, h)).join('')}</tr>`).join('') + '</tbody></table></div>';
}
// the growth of $1 on a log scale: the strategy after costs, SPY and the equal-weight universe
// a line that loses 99% (below a cent on the dollar) stops there: the floor of the scale, marked ×
const MOB_FLOOR = 0.01;
const mobCut = pts => { const k = pts.findIndex(p => p[1] < MOB_FLOOR); return k < 0 ? null : pts[k][0] };
function mobChart(lines, narrow) {
  const W = narrow ? 380 : 760, H = narrow ? 250 : 300, L = narrow ? 42 : 54, R = narrow ? 64 : 70, T = 12, B = 28;
  const drawn = lines.map(l => { const k = l.pts.findIndex(p => p[1] < MOB_FLOOR); return k < 0 ? l.pts : l.pts.slice(0, k + 1).map((p, i) => (i === k ? [p[0], MOB_FLOOR] : p)) });
  const all = drawn.flat();
  if (all.length < 3) return '';
  const xs = all.map(p => Date.parse(p[0])), x0 = Math.min(...xs), x1 = Math.max(...lines.flatMap(l => l.pts.map(p => Date.parse(p[0]))));
  const ys = all.map(p => p[1]), lo = Math.log(Math.min(...ys, 1) * 0.92), hi = Math.log(Math.max(...ys, 1) * 1.08);
  const sx = t => L + (t - x0) / ((x1 - x0) || 1) * (W - L - R), sy = v => T + (hi - Math.log(Math.max(v, MOB_FLOOR))) / ((hi - lo) || 1) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="The growth of one dollar, ${esc(lines.map(l => l.name).join(', '))}" style="display:block;width:100%;height:auto">`;
  for (const v of mobTicks(lo, hi)) s += `<line x1="${L}" x2="${W - R}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}" stroke="var(--line)" stroke-width="1"${v === 1 ? '' : ' stroke-dasharray="2 4"'}/><text x="${L - 6}" y="${(sy(v) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="var(--muted)">${mobTick(v)}</text>`;
  const y0 = new Date(x0).getUTCFullYear(), y1 = new Date(x1).getUTCFullYear(), step = y1 - y0 > (narrow ? 8 : 15) ? 5 : y1 - y0 > (narrow ? 3 : 6) ? 2 : 1;
  for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) { const x = sx(Date.UTC(y, 0, 1)); if (x >= L && x <= W - R) s += `<text x="${x.toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="var(--muted)">${y}</text>` }
  const labels = [];
  lines.forEach((l, j) => {
    const pts = drawn[j], cut = l.pts.some(p => p[1] < MOB_FLOOR);
    const d = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(Date.parse(p[0])).toFixed(1)},${sy(p[1]).toFixed(1)}`).join('');
    s += `<path d="${d}" fill="none" stroke="${l.col}" stroke-width="${l.w || 2}"${l.dash ? ` stroke-dasharray="${l.dash}"` : ''} stroke-linejoin="round"/>`;
    const e = pts[pts.length - 1];
    if (cut) s += `<text x="${sx(Date.parse(e[0])).toFixed(1)}" y="${(sy(e[1]) + 5).toFixed(1)}" text-anchor="middle" font-size="15" font-weight="700" fill="${l.col}">×</text>`;
    labels.push({ y: sy(cut ? MOB_FLOOR : e[1]), t: cut ? '−99%+' : mobUsd(e[1]), col: l.col });
  });
  labels.sort((a, b) => a.y - b.y).forEach((a, i, arr) => { if (i && a.y - arr[i - 1].y < 13) a.y = arr[i - 1].y + 13 });
  for (const a of labels) s += `<text x="${W - R + 6}" y="${(a.y + 4).toFixed(1)}" font-size="12" fill="var(--ink)"><tspan fill="${a.col}">●</tspan> ${a.t}</text>`;
  // hover: a band around each month-end with every line's value there
  const P = lines[0].pts, at = lines.map(l => new Map(l.pts));
  for (let i = 0; i < P.length; i++) {
    const x = sx(Date.parse(P[i][0])), xa = i ? (x + sx(Date.parse(P[i - 1][0]))) / 2 : x, xb = i < P.length - 1 ? (x + sx(Date.parse(P[i + 1][0]))) / 2 : x;
    const rows = [[P[i][0].slice(0, 7), 'growth of $1']].concat(lines.map((l, j) => [mobUsd(at[j].get(P[i][0])), l.name]));
    s += `<rect x="${xa.toFixed(1)}" y="${T}" width="${Math.max(1, xb - xa).toFixed(1)}" height="${H - T - B}" fill="transparent" data-tip="${typeof tip === 'function' ? tip(rows) : ''}"/>`;
  }
  return s + '</svg>';
}
// year by year: the strategy's bar beside SPY's
function mobYearBars(ya, yb, nameA, nameB, narrow) {
  const yrs = ya.map(r => r[0]);
  if (!yrs.length) return '';
  const vb = Object.fromEntries(yb.map(r => [r[0], r[1]]));
  const vals = ya.map(r => r[1]).concat(yb.map(r => r[1])).filter(mobFin);
  const W = narrow ? 380 : 760, H = narrow ? 200 : 220, L = narrow ? 40 : 46, R = 6, T = 10, B = 26;
  const every = yrs.length <= (narrow ? 7 : 14) ? 1 : narrow ? 4 : 2;
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), sy = v => T + (hi - v) / ((hi - lo) || 1) * (H - T - B), bw = (W - L - R) / yrs.length;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Each calendar year's return, ${esc(nameA)} beside ${esc(nameB)}" style="display:block;width:100%;height:auto">`;
  const raw = Math.max(0.05, (hi - lo) / 5), p10 = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 5, 10].map(k => k * p10).find(k => k >= raw - 1e-12);
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) s += `<line x1="${L}" x2="${W - R}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}" stroke="var(--line)"${Math.abs(v) < 1e-9 ? '' : ' stroke-dasharray="2 4"'}/><text x="${L - 5}" y="${(sy(v) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="var(--muted)">${Math.round(100 * v)}%</text>`;
  ya.forEach(([y, v, part], i) => {
    const x = L + i * bw, b = vb[y], w = Math.max(1, bw / 2 - 2);
    const bar = (val, dx, col) => mobFin(val) ? `<rect x="${(x + dx).toFixed(1)}" y="${Math.min(sy(val), sy(0)).toFixed(1)}" width="${w.toFixed(1)}" height="${Math.max(1, Math.abs(sy(val) - sy(0))).toFixed(1)}" rx="1.5" fill="${col}"/>` : '';
    s += `<g data-tip="${typeof tip === 'function' ? tip([[y + (part ? ' to date' : ''), 'calendar year'], [mobPc(v), nameA], [mobPc(b), nameB]]) : ''}">${bar(v, 1, 'var(--accent)')}${bar(b, bw / 2, 'var(--muted)')}<rect x="${x.toFixed(1)}" y="${T}" width="${bw.toFixed(1)}" height="${H - T - B}" fill="transparent"/></g>`;
    if (i % every === 0) s += `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="10.5" fill="var(--muted)">${every > 1 || narrow ? "'" + y.slice(2) : y}</text>`;
  });
  return s + '</svg>';
}
function mobView() {
  const m = mobData();
  if (m.err) return `<div class="empty">The back-test is built every night after the close (the research build) and is not on file yet (${esc(m.err)}).</div>`;
  if (!m.data) return empty('Reading the back-test…');
  const d = m.data;
  for (const [k, list, def] of [['mobr', MOB_R, '12-1'], ['mobh', MOB_H, '21'], ['mobs', MOB_S, 'top'], ['mobc', MOB_C, '10'], ['mobp', MOB_P, 'all']])
    if (!list.some(x => x[0] === String(state[k]))) state[k] = def;
  const r = String(state.mobr), h = String(state.mobh), side = state.mobs, cost = +state.mobc / 1e4, period = state.mobp;
  const key = `${r}|${h}|${side}`, sname = (MOB_S.find(x => x[0] === side) || [])[1].split(':')[0];
  const rl = (MOB_R.find(x => x[0] === r) || [])[1], hl = (MOB_H.find(x => x[0] === h) || [])[1], narrow = mobNarrow();
  const cl = (MOB_C.find(x => x[0] === String(state.mobc)) || [])[1];
  let out =`<div class="toolbar">${field('mobr', 'Ranked by the return over', MOB_R, r)}${field('mobh', 'Held for', MOB_H, h)}${field('mobs', 'Portfolio', MOB_S, side)}${field('mobc', 'Trading costs', MOB_C, String(state.mobc))}${field('mobp', 'Period', MOB_P, period)}</div>`;
  out += `<p class="muted">${fmt(d.stocks)} valued companies with daily adjusted closes (${fmt((d.traded || [])[0])} trading at the start, ${fmt((d.traded || []).slice(-1)[0])} now), ${esc(d.start)} to ${esc(d.as_of)} · a tenth of the ranked stocks in each portfolio, equal weight · built ${esc(String(d.generated_at || '').replace('T', ' ').slice(0, 16))} UTC</p>`;
  // the grid
  const p0 = (d.periods || {})[period] || d.start, spyC = mobCagr(d, 'spy', 0, period), ewC = mobCagr(d, 'ew', 0, period);
  out += `<div class="mob-wrap"><div class="panel"><h3>Annual return, every ranking and holding period · ${esc(sname.toLowerCase())}${cost ? `, after ${esc(cl)}` : ', before costs'}</h3><p class="sub">From ${esc(p0)}. ${side === 'ls' ? 'Green above zero, red below' : `Green above the equal-weight average of the same companies (${mobPc(ewC)} a year — it shares their survivorship, so the gap is what the ranking added), red below`}; the stronger the colour, the wider the gap. SPY: ${mobPc(spyC)} a year. Click a cell to draw it below.</p>${mobGrid(d, side, cost, period, narrow)}</div>`;
  // the chosen strategy
  const line = mobLine(d, key, cost, period), spy = mobLine(d, 'spy', 0, period), ew = mobLine(d, 'ew', 0, period);
  if (!line) return out + empty('No values for this combination.') + '</div>';
  const gone = mobCut(line.pts);
  const name = `${sname} by ${MOB_RS[r] === '12-1' ? '12-1' : 'the last ' + MOB_RS[r].toLowerCase()}, held ${hl}`;
  out += `<div class="panel"><h3>${esc(name)}: the growth of $1${cost ? ' after costs' : ''}</h3><p class="sub">Ranked at each close by ${esc(rl.toLowerCase())}; ${side === 'ls' ? 'bought the top tenth and sold short the bottom tenth' : `bought the ${side === 'top' ? 'top' : 'bottom'} tenth`} and held ${esc(hl)} — a new portfolio every day, each held ${esc(hl)}, an equal share of the money in each (Jegadeesh &amp; Titman's overlapping portfolios). Log scale; month-end values.${gone ? ` It had lost more than 99% by ${esc(gone.slice(0, 7))}; its line stops there (×).` : ''}</p>`
    + mobChart([{ name, pts: line.pts, col: 'var(--accent)', w: 2.4 }, { name: 'SPY', pts: spy.pts, col: 'var(--ink)', w: 1.6 }, { name: 'Equal-weight universe', pts: ew.pts, col: 'var(--muted)', w: 1.4, dash: '5 4' }], narrow)
    + `<div class="mk-legend"><span><i class="mk-key" style="background:var(--accent)"></i>${esc(name)}</span><span><i class="mk-key" style="background:var(--ink)"></i>SPY</span><span><i class="mk-key" style="background:var(--muted)"></i>Equal-weight universe (dashed)</span></div></div>`;
  // the statistics
  const st = k => (((d.stats || {})[k] || {})[period]) || {};
  const S = st(key), SP = st('spy'), EW = st('ew'), net = mobCagr(d, key, cost, period);
  const row = (label, a, b, c) => `<tr><td>${label}</td><td class="num">${a}</td><td class="num">${b}</td><td class="num">${c}</td></tr>`;
  out += `<div class="panel"><h3>Statistics · ${esc((MOB_P.find(x => x[0] === period) || [])[1].toLowerCase())}</h3><div class="tablebox"><table class="mob-stats"><thead><tr><th></th><th class="num">${esc(sname)}</th><th class="num">SPY</th><th class="num">${narrow ? 'Equal weight' : 'Equal-weight universe'}</th></tr></thead><tbody>`
    + row('Annual return, before costs', mobTone(S.cagr, mobPc(S.cagr)), mobTone(SP.cagr, mobPc(SP.cagr)), mobTone(EW.cagr, mobPc(EW.cagr)))
    + (cost ? row(`Annual return, after ${esc(cl)}`, mobTone(net, mobPc(net)), '—', '—') : '')
    + row('Volatility (a year)', mobAbs(S.vol), mobAbs(SP.vol), mobAbs(EW.vol))
    + row('Return ÷ volatility', mobFin(S.ratio) ? S.ratio.toFixed(2) : '—', mobFin(SP.ratio) ? SP.ratio.toFixed(2) : '—', mobFin(EW.ratio) ? EW.ratio.toFixed(2) : '—')
    + row('Maximum drawdown', mobPc(S.mdd), mobPc(SP.mdd), mobPc(EW.mdd))
    + row('Months up', pct(S.up, 0), pct(SP.up, 0), pct(EW.up, 0))
    + row('Months ahead of SPY', pct(S.ahead, 0), '—', pct(EW.ahead, 0))
    + row('Beta to SPY', mobFin(S.beta) ? S.beta.toFixed(2) : '—', '1.00', mobFin(EW.beta) ? EW.beta.toFixed(2) : '—')
    + row('Alpha (a year, before costs)', mobTone(S.alpha, mobPc(S.alpha)), '—', mobTone(EW.alpha, mobPc(EW.alpha)))
    + row('Turnover (traded a year, both ways)', mobFin(line.turn) ? Math.round(100 * 252 * line.turn) + '%' : '—', '—', '—')
    + (cost ? row('Costs a year at this rate', mobPc(-(1 - Math.pow(line.f, 252))), '—', '—') : '')
    + row('Stocks held per portfolio', fmt((d.held || {})[key]), '—', '—')
    + '</tbody></table></div></div>';
  // year by year
  const ya = mobYears(line.pts), yb = mobYears(spy.pts);
  out += `<div class="panel"><h3>Year by year</h3><p class="sub">Each calendar year's return${cost ? ' after costs' : ''}, the strategy beside SPY; the first year from ${esc(line.pts[0][0])}, this year to date.</p>${mobYearBars(ya, yb, name, 'SPY', narrow)}`
    + `<div class="mk-legend"><span><i class="mk-key" style="background:var(--accent);border-radius:2px"></i>${esc(name)}</span><span><i class="mk-key" style="background:var(--muted);border-radius:2px"></i>SPY</span></div></div></div>`;
  exported = MOB_R.flatMap(([rr]) => MOB_H.map(([hh]) => { const k = `${rr}|${hh}|${side}`, x = st(k); return { ranked_by: MOB_RS[rr], held: (MOB_H.find(z => z[0] === hh) || [])[1], portfolio: side, period, from: p0,
    annual_return: x.cagr, annual_return_after_costs: mobCagr(d, k, cost, period), cost_per_trade: cost, volatility: x.vol, max_drawdown: x.mdd, months_up: x.up, months_ahead_of_spy: x.ahead, beta: x.beta, alpha: x.alpha,
    turnover_a_year: mobFin((d.turn || {})[k]) ? 252 * d.turn[k] : null, stocks_held: (d.held || {})[k] } }));
  out += `<div class="section-head"><h3>Every combination as CSV</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out += `<details class="panel"><summary>How it is computed, and what it leaves out</summary><p class="sub">Each trading day since 2000 the valued companies are ranked by their return over the ranking period (12-1: the last 252 days skipping the latest 21, the classic momentum signal of Jegadeesh &amp; Titman 1993); the top tenth (the biggest risers) and the bottom tenth (the biggest fallers) are bought at that close, equal weight, and held for the holding period; the strategy holds the latest of these portfolios, an equal share of the money each, so it does not depend on the day it began. Long-short: the top's return less the bottom's, without financing, borrow fees or short rebates. A day's return counts at most −50% / +100%, so a bad print moves no portfolio.</p><p class="sub"><b>Survivorship:</b> these are today's companies; those that failed, were bought or delisted since are not in them. That flatters every long portfolio, and the fallers most (their survivors are the ones that recovered) — the equal-weight average of these companies, ${mobPc(ewC)} a year against SPY's ${mobPc(spyC)}, shows how much. <b>Short periods</b> reverse more than they persist (the one-week and one-month reversals, Jegadeesh 1990, Lehmann 1990), partly from the bid-ask bounce of closing prices — a one-day ranking trades its whole portfolio about once a day, so its costs decide it. <b>Costs</b> here are the turnover × the cost of a trade; no taxes, no market impact. History, not a forecast; not investment advice.</p><p class="sub">The <a href="#strategies">Strategies</a> tab runs published rules — momentum among them — on weekly closes since 1995, with cash, borrowing and the tests for overfitting.</p></details>`;
  return out;
}
function bindMobGrid() {
  if (typeof document === 'undefined') return;
  document.querySelectorAll('#workspace [data-mob]').forEach(b => b.onclick = () => { const [r, h] = b.dataset.mob.split('|'); state.mobr = r; state.mobh = h; render() });
  if (typeof bindTips === 'function') bindTips();
}
if (typeof document !== 'undefined' && !document.getElementById('mob-css')) {
  const st = document.createElement('style'); st.id = 'mob-css';
  // :is(#hub-root, body): the hub's own rules carry #hub-root inside the main site's shell (an id's weight), so these do too
  const H = ':is(#hub-root,body) ';
  st.textContent = `${H}.mob-wrap{display:grid;gap:14px;margin-top:4px}${H}.mob-wrap>.panel{min-width:0}${H}.mob-grid th[scope=row]{white-space:nowrap}${H}.mob-cell .text-button{font:inherit;font-variant-numeric:tabular-nums;color:var(--ink);text-decoration:none;width:100%;text-align:right;padding:0;margin:0}${H}.mob-cell.mob-on{outline:2px solid var(--ink);outline-offset:-2px}${H}.mob-grid th.num,${H}.mob-stats th.num,${H}.mob-stats td.num{text-align:right}`
    + `@media (max-width:560px){${H}.mob-wrap>.panel{padding:14px}${H}.mob-grid,${H}.mob-stats{min-width:0}${H}.mob-grid th,${H}.mob-grid td{padding:7px 5px;font-size:12px}${H}.mob-stats th,${H}.mob-stats td{padding:7px 6px}${H}.mob-stats td:first-child{min-width:0;width:42%;white-space:normal;font-size:12.5px}${H}.mob-stats td.num{font-size:12px}}`;
  document.head.appendChild(st);
}
if (typeof module !== 'undefined') module.exports = { mobData, mobLine, mobCagr, mobYears, mobGrid, mobChart, mobYearBars, mobView, bindMobGrid, mobUsd, mobTicks, mobTick, mobCut, mobStore, MOB_R, MOB_H, MOB_S, MOB_C, MOB_P, MOB_FLOOR };
