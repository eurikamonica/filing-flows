/* Rotation → RRG portfolios (#rotation/rrgbt): what holding the lines that stand in chosen quadrants of the Relative
   Rotation Graph — Leading, Weakening, Lagging, Improving or any mix of them — returned since 2000, against SPY and the
   group's equal weight, with trading costs and a period chosen here; what a portfolio bought at a close returned over
   the holding period after it (the expected return of buying now, as history has it); and which lines stand in those
   quadrants now. Data: data/research/paths/backtest/rrg/index.json and <clock>-<group>.json (app/rrg_backtest.py, the
   nightly research build) — the momentum back-test's shape, so the values after costs, the growth chart and the years
   come from momentum-backtest.js (mobLine, mobCagr, mobYears, mobChart, mobYearBars, mobPc …). */
const RRGB_Q = [['leading', 'Leading', 'lead'], ['weakening', 'Weakening', 'weak'], ['lagging', 'Lagging', 'lag'], ['improving', 'Improving', 'imp']];
const RRGB_COL = { leading: 'var(--flow-buy)', weakening: 'var(--rot-sun)', lagging: 'var(--flow-sell)', improving: 'var(--rot-1)' };
const RRGB_NOTE = { 'leading+weakening': 'the right half: above its trend against SPY', 'lagging+improving': 'the left half: below its trend',
  'leading+improving': 'the top half: gaining on SPY', 'weakening+lagging': 'the bottom half: losing ground', 'leading+lagging': 'the diagonal',
  'weakening+improving': 'the other diagonal', 'leading+weakening+lagging+improving': 'every line: the equal weight' };
const RRGB_C = [['0', 'None (theoretical)'], ['5', '0.05% a trade'], ['10', '0.10% a trade'], ['25', '0.25% a trade']];
const RRGB_P = [['all', 'Since 2000'], ['10y', 'The last 10 years'], ['5y', 'The last 5 years']];
const RRGB_S = [['ret', 'Annual return'], ['exp', 'Expected return'], ['mix', 'Quadrants']];
const rrgbStore = {};
function rrgbGet(name) {
  const m = rrgbStore[name] || (rrgbStore[name] = {});
  if (m.data || m.err || m.loading) return m;
  if (typeof fetch !== 'function') { m.err = 'this browser cannot load data files'; return m }
  m.loading = fetch((globalThis.FF_HUB_ROOT || '') + 'data/research/paths/backtest/rrg/' + name, { cache: 'no-cache' })
    .then(r => { if (!r.ok) throw Error(r.status === 404 ? 'not built yet' : 'HTTP ' + r.status); return r.json() })
    .then(d => { if (!d || !/^rrg-backtest(-index)?\.v1$/.test(String(d.schema))) throw Error('an unexpected file'); m.data = d })
    .catch(e => { m.err = e.message })
    .finally(() => { m.loading = null; if (typeof state === 'object' && state.tab === 'rotation' && state.rview === 'rrgbt' && typeof render === 'function') render() });
  return m;
}
const rrgbName = k => String(k).split('+').map(q => (RRGB_Q.find(x => x[0] === q) || [q, q])[1]).join(' + ');
const rrgbShort = k => String(k).split('+').map(q => ({ leading: 'Lead', weakening: 'Weak', lagging: 'Lag', improving: 'Imp' })[q] || q).join(' + ');
const rrgbDots = k => String(k).split('+').map(q => `<i class="mk-key" style="background:${RRGB_COL[q] || 'var(--muted)'}"></i>`).join('');
const rrgbHl = (clock, K) => (clock === 'w' ? (+K === 1 ? '1 week' : K + ' weeks') : (+K === 1 ? '1 trading day' : K + ' trading days'));
const rrgbBadge = q => (RRGB_Q[q] ? `<span class="badge rrg-b-${RRGB_Q[q][2]}">${RRGB_Q[q][1]}</span>` : '—');
// the lines now: {key, name, x, y, q, periods}
function rrgbNow(d) {
  const N = d.now || {}, at = Object.fromEntries((N.fields || []).map((f, i) => [f, i]));
  return (N.rows || []).map(r => ({ k: r[at.key], n: at.name != null ? r[at.name] : r[at.key], x: r[at.x], y: r[at.y], q: r[at.q], p: r[at.periods] }));
}
// where the group stands now, on the RRG: the mix's lines in their quadrant's colour, the others faint
function rrgbScatter(pts, on, unit, narrow) {
  if (!pts.length) return '';
  const W = narrow ? 360 : 560, H = narrow ? 300 : 380, L = 44, R = 14, T = 14, B = 34;
  const q97 = a => { const s = a.slice().sort((p, q) => p - q); return s[Math.min(s.length - 1, Math.floor(0.97 * s.length))] || 0 };
  const dx = Math.max(1.5, q97(pts.map(p => Math.abs(p.x - 100))) * 1.12), dy = Math.max(1.5, q97(pts.map(p => Math.abs(p.y - 100))) * 1.12);
  const cl = (v, d) => Math.max(-d, Math.min(d, v - 100));
  const sx = v => L + (cl(v, dx) + dx) / (2 * dx) * (W - L - R), sy = v => T + (dy - cl(v, dy)) / (2 * dy) * (H - T - B);
  const cx = sx(100), cy = sy(100);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Where each line stands on the RRG now; the lines in the chosen quadrants in colour" style="display:block;width:100%;max-width:${W}px;height:auto">`;
  for (const [q, x0, y0, x1, y1] of [[0, cx, T, W - R, cy], [1, cx, cy, W - R, H - B], [2, L, cy, cx, H - B], [3, L, T, cx, cy]]) {
    const k = RRGB_Q[q][0];
    s += `<rect x="${x0.toFixed(1)}" y="${y0.toFixed(1)}" width="${(x1 - x0).toFixed(1)}" height="${(y1 - y0).toFixed(1)}" fill="${RRGB_COL[k]}" opacity="${on.has(k) ? 0.1 : 0.03}"/>`;
    s += `<text x="${(q === 0 || q === 1 ? x1 - 6 : x0 + 6).toFixed(1)}" y="${(q === 0 || q === 3 ? y0 + 15 : y1 - 7).toFixed(1)}" text-anchor="${q === 0 || q === 1 ? 'end' : 'start'}" font-size="12" font-weight="600" class="rrg-t-${RRGB_Q[q][2]}">${RRGB_Q[q][1]}</text>`;
  }
  s += `<line x1="${cx.toFixed(1)}" x2="${cx.toFixed(1)}" y1="${T}" y2="${H - B}" stroke="var(--line)"/><line x1="${L}" x2="${W - R}" y1="${cy.toFixed(1)}" y2="${cy.toFixed(1)}" stroke="var(--line)"/>`;
  for (const v of [100 - dx * 0.66, 100, 100 + dx * 0.66]) s += `<text x="${sx(v).toFixed(1)}" y="${H - B + 14}" text-anchor="middle" font-size="10.5" fill="var(--muted)">${v.toFixed(1)}</text>`;
  for (const v of [100 - dy * 0.66, 100, 100 + dy * 0.66]) s += `<text x="${L - 5}" y="${(sy(v) + 4).toFixed(1)}" text-anchor="end" font-size="10.5" fill="var(--muted)">${v.toFixed(1)}</text>`;
  s += `<text x="${W - R}" y="${H - 4}" text-anchor="end" font-size="11" fill="var(--muted)">RS-Ratio →</text><text x="${L - 36}" y="${T + 2}" font-size="11" fill="var(--muted)" transform="rotate(-90 ${L - 36} ${T + 2})" text-anchor="end">RS-Momentum →</text>`;
  const many = pts.length > 60, few = pts.length <= 24, label = few || pts.filter(p => on.has(RRGB_Q[p.q][0])).length <= 24, placed = [];
  const order = pts.slice().sort((a, b) => on.has(RRGB_Q[a.q][0]) - on.has(RRGB_Q[b.q][0]));          // the chosen ones drawn on top
  for (const p of order) {
    const k = RRGB_Q[p.q][0], hit = on.has(k), X = sx(p.x), Y = sy(p.y);
    const t = typeof tip === 'function' ? tip([[p.n, RRGB_Q[p.q][1]], [p.x.toFixed(2), 'RS-Ratio'], [p.y.toFixed(2), 'RS-Momentum'], [String(p.p), (p.p === 1 ? unit.one : unit.many) + ' in this quadrant']]) : '';
    s += `<circle cx="${X.toFixed(1)}" cy="${Y.toFixed(1)}" r="${hit ? (many ? 3 : 5) : (many ? 2 : 3.5)}" fill="${hit ? RRGB_COL[k] : 'var(--muted)'}" opacity="${hit ? 0.9 : 0.35}" stroke="var(--surface)" stroke-width="${many ? 0.5 : 1.5}" data-tip="${t}"/>`;
    if (label && (hit || few)) {
      let ly = Y + 4;
      for (let n = 0; n < 6 && placed.some(([a, b]) => Math.abs(a - X) < 34 && Math.abs(b - ly) < 11); n++) ly += 11;
      placed.push([X, ly]);
      s += `<text x="${(X + 7).toFixed(1)}" y="${ly.toFixed(1)}" font-size="11" fill="${hit ? 'var(--ink)' : 'var(--muted)'}">${esc(p.k)}</text>`;
    }
  }
  return s + '</svg>';
}
function rrgBacktestView() {
  if (typeof mobChart !== 'function') return `<div class="toolbar">${field('rview', 'Chart', ROT_VIEWS, state.rview)}</div>` + empty('The back-test charts did not load; refresh the page.');
  const idx = rrgbGet('index.json');
  let out = `<div class="toolbar">${field('rview', 'Chart', ROT_VIEWS, state.rview)}`;
  if (idx.err) return out + `</div><div class="empty">The RRG portfolios are built every night after the close (the research build) and are not on file yet (${esc(idx.err)}).</div>`;
  if (!idx.data) return out + '</div>' + empty('Reading the RRG portfolios…');
  const I = idx.data, groups = (I.groups || []).filter(g => g.clocks && Object.keys(g.clocks).length);
  if (!groups.length) return out + '</div>' + empty('No groups in the file yet.');
  if (!groups.some(g => g.key === state.rrgbg)) state.rrgbg = groups.some(g => g.key === 'sectors') ? 'sectors' : groups[0].key;
  const G = groups.find(g => g.key === state.rrgbg), clocks = Object.keys(G.clocks);
  if (!clocks.includes(state.rrgbc)) state.rrgbc = clocks.includes('w') ? 'w' : clocks[0];
  const clock = state.rrgbc, holds = (((I.clocks || {})[clock] || {}).holds || []).map(String);
  if (!holds.includes(String(state.rrgbh))) state.rrgbh = holds[Math.min(1, holds.length - 1)];
  for (const [k, list, def] of [['rrgbcost', RRGB_C, '10'], ['rrgbp', RRGB_P, 'all'], ['rrgbs', RRGB_S, 'ret']]) if (!list.some(x => x[0] === String(state[k]))) state[k] = def;
  const mixes = I.mixes || [];
  if (!mixes.includes(state.rrgbx)) state.rrgbx = 'improving';
  const K = +state.rrgbh, cost = +state.rrgbcost / 1e4, period = state.rrgbp, mix = state.rrgbx, narrow = typeof mobNarrow === 'function' && mobNarrow();
  const cl = (RRGB_C.find(x => x[0] === String(state.rrgbcost)) || [])[1], unit = clock === 'w' ? { one: 'week', many: 'weeks' } : { one: 'day', many: 'days' };
  out += field('rrgbg', 'Lines', groups.map(g => [g.key, g.label]), G.key) + field('rrgbc', 'RRG', clocks.map(c => [c, ((I.clocks || {})[c] || {}).label || c]), clock)
    + field('rrgbh', 'Held for', holds.map(h => [h, rrgbHl(clock, h)]), String(K)) + field('rrgbcost', 'Trading costs', RRGB_C, String(state.rrgbcost)) + field('rrgbp', 'Period', RRGB_P, period) + field('rrgbs', 'Order the mixes by', RRGB_S, String(state.rrgbs)) + '</div>';
  const on = new Set(mix.split('+'));
  out += `<div class="toolbar rrgb-quads" role="group" aria-label="The quadrants to buy"><span class="rrgb-lab">Buy the lines in</span>${RRGB_Q.map(([q, l]) => `<button type="button" class="rrgb-q${on.has(q) ? ' on' : ''}" data-rrgbq="${q}" aria-pressed="${on.has(q)}"><i class="mk-key" style="background:${RRGB_COL[q]}"></i>${l}</button>`).join('')}<span class="muted rrgb-note">${esc(RRGB_NOTE[mix] || '')}</span></div>`;
  const f = rrgbGet(G.clocks[clock].file);
  if (f.err) return out + `<div class="empty">This group's back-test is not on file yet (${esc(f.err)}).</div>`;
  if (!f.data) return out + empty('Reading the back-test of the ' + G.label.replace(/ against.*/, '').toLowerCase() + '…');
  const d = f.data, py = d.per_year || 52, p0 = (d.periods || {})[period] || d.start, hl = rrgbHl(clock, K);
  const st = k => (((d.stats || {})[k] || {})[period]) || {}, ex = k => (((d.expect || {})[k] || {})[period]) || null;
  const ewC = mobCagr(d, 'ew', 0, period), spyC = mobCagr(d, 'spy', 0, period);
  out += `<p class="muted">${fmt(d.lines)} lines · ${esc(d.clock_label || '')} · portfolios formed from ${esc(d.formed_from)}, counted from ${esc(d.start)} to ${esc(d.as_of)} · built ${esc(String(d.generated_at || '').replace('T', ' ').slice(0, 16))} UTC</p>`;
  // every mix
  let rows = (d.mixes || mixes).map(mk => { const key = `${mk}|${K}`; return { mk, key, net: mobCagr(d, key, cost, period), s: st(key), e: ex(key), held: (d.held || {})[key], inv: (d.invested || {})[key] } });
  const sk = state.rrgbs;
  if (sk === 'ret') rows.sort((a, b) => (b.net ?? -9) - (a.net ?? -9));
  else if (sk === 'exp') rows.sort((a, b) => ((b.e || {}).mean ?? -9) - ((a.e || {}).mean ?? -9));
  const tint = v => { if (!mobFin(v) || !mobFin(ewC)) return ''; const x = v - ewC, a = Math.min(1, Math.abs(x) / 0.08); return ` style="background:color-mix(in srgb, ${x >= 0 ? 'var(--mk-profit)' : 'var(--mk-cost)'} ${Math.round(6 + 40 * a)}%, transparent)"` };
  const head2 = narrow ? ['Quadrants', 'A year', 'Next ' + hl, 'Beat equal weight']
    : ['Quadrants', 'Annual return', 'vs equal weight', 'Worst fall', `Next ${hl}: mean, 95% interval`, 'Beat the equal weight', 'Lines held', 'Invested'];
  const ALL = 'leading+weakening+lagging+improving';
  const exC = e => (e ? `${mobTone(e.mean, mobPc(e.mean, 2))}${narrow ? '' : `<br><span class="muted">${mobPc(e.lo, 2)} to ${mobPc(e.hi, 2)}</span>`}` : '—');
  out += `<div class="mob-wrap"><div class="panel"><h3>Every mix of quadrants · held ${esc(hl)}${cost ? `, after ${esc(cl)}` : ', before costs'}</h3><p class="sub">From ${esc(p0)}. Green above the equal weight of the same lines (${mobPc(ewC)} a year — it shares their survivorship, so the gap is what the quadrants added), red below; SPY: ${mobPc(spyC)} a year. "Next ${esc(hl)}": what a portfolio bought at a close returned over the ${esc(hl)} after it — its mean, with a 95% interval. Tap a mix to draw it.</p>`
    + `<div class="tablebox"><table class="rrgb-t"><thead><tr>${head2.map((h, i) => `<th${i ? ' class="num"' : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>`
    + rows.map(r => {
      const a = r.mk === mix, e = r.e || {};
      const first = `<button type="button" class="text-button rrgb-m" data-rrgbm="${esc(r.mk)}" aria-pressed="${a}">${rrgbDots(r.mk)} ${esc(narrow ? rrgbShort(r.mk) : rrgbName(r.mk))}</button>${narrow || !RRGB_NOTE[r.mk] ? '' : `<br><span class="muted">${esc(RRGB_NOTE[r.mk])}</span>`}`;
      const beat = r.mk === ALL ? '—' : pct(e.beat_ew, 0);                    // the equal weight against itself
      const cells = narrow ? [`<td class="num"${tint(r.net)}>${mobPc(r.net)}</td>`, `<td class="num">${exC(r.e)}</td>`, `<td class="num">${beat}</td>`]
        : [`<td class="num"${tint(r.net)}>${mobPc(r.net)}</td>`, `<td class="num">${mobFin(r.net) && mobFin(ewC) ? mobTone(r.net - ewC, mobPc(r.net - ewC)) : '—'}</td>`,
          `<td class="num">${mobPc(r.s.mdd, 0)}</td>`, `<td class="num">${exC(r.e)}</td>`, `<td class="num">${beat}</td>`, `<td class="num">${fmt(r.held, 1)}</td>`, `<td class="num">${pct(r.inv, 0)}</td>`];
      return `<tr class="${a ? 'rrgb-on' : ''}"><td>${first}</td>${cells.join('')}</tr>`;
    }).join('') + '</tbody></table></div></div>';
  // the chosen mix
  const key = `${mix}|${K}`, line = mobLine(d, key, cost, period), spy = mobLine(d, 'spy', 0, period), ew = mobLine(d, 'ew', 0, period);
  if (!line) return out + empty('No values for this mix.') + '</div>';
  const name = `${rrgbName(mix)}, held ${hl}`, S = st(key), E = ex(key) || {};
  const gone = typeof mobCut === 'function' ? mobCut(line.pts) : null;
  out += `<div class="panel"><h3>${esc(name)}: the growth of $1${cost ? ' after costs' : ''}</h3><p class="sub">At each ${clock === 'w' ? 'week\'s last close' : 'close'}, the lines in ${esc(rrgbName(mix))} bought equal weight and held ${esc(hl)} — a new portfolio every ${unit.one}, each held ${esc(hl)}, an equal share of the money in each; cash when no line stands there. Log scale; month-end values.${gone ? ` It had lost more than 99% by ${esc(gone.slice(0, 7))}; its line stops there (×).` : ''}</p>`
    + mobChart([{ name, pts: line.pts, col: 'var(--accent)', w: 2.4 }, { name: 'SPY', pts: spy.pts, col: 'var(--ink)', w: 1.6 }, { name: 'Equal weight of the group', pts: ew.pts, col: 'var(--muted)', w: 1.4, dash: '5 4' }], narrow)
    + `<div class="mk-legend"><span><i class="mk-key" style="background:var(--accent)"></i>${esc(name)}</span><span><i class="mk-key" style="background:var(--ink)"></i>SPY</span><span><i class="mk-key" style="background:var(--muted)"></i>Equal weight of the group (dashed)</span></div>`;
  const net = mobCagr(d, key, cost, period), sp = st('spy'), ewS = st('ew');
  const r3 = (l, a, b, c) => `<tr><td>${l}</td><td class="num">${a}</td><td class="num">${b}</td><td class="num">${c}</td></tr>`;
  out += `<div class="tablebox"><table class="mob-stats"><thead><tr><th></th><th class="num">${esc(rrgbName(mix))}</th><th class="num">SPY</th><th class="num">${narrow ? 'Equal weight' : 'Equal weight of the group'}</th></tr></thead><tbody>`
    + r3('Annual return, before costs', mobTone(S.cagr, mobPc(S.cagr)), mobTone(sp.cagr, mobPc(sp.cagr)), mobTone(ewS.cagr, mobPc(ewS.cagr)))
    + (cost ? r3(`Annual return, after ${esc(cl)}`, mobTone(net, mobPc(net)), '—', '—') : '')
    + r3('Volatility (a year)', mobAbs(S.vol), mobAbs(sp.vol), mobAbs(ewS.vol))
    + r3('Return ÷ volatility', mobFin(S.ratio) ? S.ratio.toFixed(2) : '—', mobFin(sp.ratio) ? sp.ratio.toFixed(2) : '—', mobFin(ewS.ratio) ? ewS.ratio.toFixed(2) : '—')
    + r3('Maximum drawdown', mobPc(S.mdd), mobPc(sp.mdd), mobPc(ewS.mdd))
    + r3('Months up', pct(S.up, 0), pct(sp.up, 0), pct(ewS.up, 0))
    + r3('Months ahead of SPY', pct(S.ahead, 0), '—', pct(ewS.ahead, 0))
    + r3('Beta to SPY', mobFin(S.beta) ? S.beta.toFixed(2) : '—', '1.00', mobFin(ewS.beta) ? ewS.beta.toFixed(2) : '—')
    + r3('Turnover (traded a year, both ways)', mobFin(line.turn) ? Math.round(100 * 252 * line.turn) + '%' : '—', '—', '—')
    + (cost ? r3('Costs a year at this rate', mobPc(-(1 - Math.pow(line.f, 252))), '—', '—') : '')
    + r3('Lines held (average) · time invested', `${fmt((d.held || {})[key], 1)} · ${pct((d.invested || {})[key], 0)}`, '—', '—')
    + '</tbody></table></div></div>';
  // bought now: what history says, and the lines it would buy
  const pts = rrgbNow(d), inMix = pts.filter(p => on.has((RRGB_Q[p.q] || [])[0])).sort((a, b) => a.q - b.q || b.y - a.y);
  const yr = v => (mobFin(v) ? Math.pow(1 + v, py / K) - 1 : null);
  const kp = (l, v, c) => (typeof kpi === 'function' ? kpi(l, v, c) : `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`);
  out += `<div class="panel"><h3>Buying ${esc(rrgbName(mix))} now: what history says about the next ${esc(hl)}</h3><p class="sub">Every portfolio of these quadrants bought at a close since ${esc(p0)}, ${fmt(E.n)} of them (${fmt(E.n_indep)} that do not overlap give the interval), and what each was worth ${esc(hl)} later — before costs. History, not a forecast: the interval says how sure the average is, not where the next one lands.</p>`;
  out += E.mean != null ? `<div class="metrics">${kp(`Mean over ${hl}`, mobPc(E.mean, 2), `95% interval ${mobPc(E.lo, 2)} to ${mobPc(E.hi, 2)} · ≈ ${mobPc(yr(E.mean))} a year`)}${kp('Median', mobPc(E.median, 2), `up ${pct(E.up, 0)} of the time`)}${mix === ALL ? '' : kp('Ahead of the equal weight', pct(E.beat_ew, 0), `its mean ${mobPc(E.ew, 2)} · the gap ${mobPc(E.excess_ew, 2)}`)}${kp('Ahead of SPY', pct(E.beat, 0), `SPY's mean ${mobPc(E.spy, 2)} · the gap ${mobPc(E.excess, 2)}`)}</div>` : empty('Too few portfolios in this period.');
  out += `<h4>In ${esc(rrgbName(mix))} at the close of ${esc((d.now || {}).date || d.as_of)}: ${fmt(inMix.length)} of ${fmt(pts.length)} lines</h4>`;
  out += `<div class="rrgb-now"><div>${rrgbScatter(pts, on, unit, narrow)}</div><div>`;
  const shown = inMix.slice(0, 40), co = d.group === 'companies';
  const there = unit.many[0].toUpperCase() + unit.many.slice(1) + ' there';
  out += inMix.length ? `<div class="tablebox"><table class="rrgb-m-t"><thead><tr><th>Line</th><th>Quadrant</th>${narrow ? '' : '<th class="num">RS-Ratio</th><th class="num">RS-Momentum</th>'}<th class="num">${there}</th></tr></thead><tbody>`
    + shown.map(p => `<tr><td>${co && typeof tkLink === 'function' ? tkLink(p.k) : `<b>${esc(p.k)}</b>${p.n !== p.k ? `<br><span class="muted">${esc(p.n)}</span>` : ''}`}</td><td>${rrgbBadge(p.q)}${narrow ? `<br><span class="muted">${p.x.toFixed(2)} · ${p.y.toFixed(2)}</span>` : ''}</td>${narrow ? '' : `<td class="num">${p.x.toFixed(2)}</td><td class="num">${p.y.toFixed(2)}</td>`}<td class="num">${fmt(p.p)}</td></tr>`).join('')
    + '</tbody></table></div>' + (inMix.length > shown.length ? `<p class="muted">… and ${fmt(inMix.length - shown.length)} more in the CSV below.</p>` : '') : empty('No line stands in these quadrants now: the strategy would hold cash.');
  out += '</div></div>';
  rrgbStore.members = inMix.map(p => ({ date: (d.now || {}).date, group: d.group, clock: d.clock, line: p.k, name: p.n, quadrant: RRGB_Q[p.q][1], rs_ratio: p.x, rs_momentum: p.y, periods_in_quadrant: p.p }));
  out += `<p><button type="button" class="action" id="rrgbcsv">These lines as CSV ↓</button></p></div>`;
  // the years
  const ya = mobYears(line.pts), yb = mobYears(spy.pts);
  out += `<div class="panel"><h3>Year by year</h3><p class="sub">Each calendar year's return${cost ? ' after costs' : ''}, the mix beside SPY; the first year from ${esc(line.pts[0][0])}, this year to date.</p>${mobYearBars(ya, yb, name, 'SPY', narrow)}`
    + `<div class="mk-legend"><span><i class="mk-key" style="background:var(--accent);border-radius:2px"></i>${esc(name)}</span><span><i class="mk-key" style="background:var(--muted);border-radius:2px"></i>SPY</span></div></div></div>`;
  exported = rows.map(r => ({ group: d.group, rrg: d.clock, held: hl, quadrants: rrgbName(r.mk), period, from: p0, annual_return: r.s.cagr, annual_return_after_costs: r.net, cost_per_trade: cost,
    vs_equal_weight: mobFin(r.net) && mobFin(ewC) ? r.net - ewC : null, volatility: r.s.vol, max_drawdown: r.s.mdd, next_mean: (r.e || {}).mean, next_lo: (r.e || {}).lo, next_hi: (r.e || {}).hi,
    next_median: (r.e || {}).median, next_ahead_of_equal_weight: (r.e || {}).beat_ew, next_ahead_of_spy: (r.e || {}).beat, lines_held: r.held, invested: r.inv }));
  out += `<div class="section-head"><h3>Every mix as CSV</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  out += `<details class="panel"><summary>How it is computed, and what it leaves out</summary><p class="sub">The RRG is the chart's (RS = the line's close ÷ SPY's; RS-Ratio its gap to its ${clock === 'w' ? '14-week' : '21-day'} trend, RS-Momentum that gap's change, each scaled by its own spread over the last ${clock === 'w' ? '52 weeks' : '252 days'}), on daily closes adjusted for dividends and splits (the Move odds data, from 1998). At each ${clock === 'w' ? 'week\'s last close' : 'close'} the lines in the chosen quadrants are bought equal weight and held ${esc(hl)}; the strategy holds the latest of these portfolios, an equal share of the money in each (Jegadeesh &amp; Titman's overlapping portfolios), so it does not depend on the ${unit.one} it began. Costs: the turnover × the cost of a trade, taken off every day; no taxes, no fund fees beyond those in the prices.</p><p class="sub"><b>Survivorship:</b> these are today's lines — funds closed and companies gone since are not in them, which flatters the companies and industries most (their equal weight beat SPY by far). Compare a mix with the equal weight of the same lines, not only with SPY. <b>Quadrants describe where a line has been</b>, not where it goes: across most groups no mix beats the equal weight by much once costs are counted, and a short hold trades often. History, not a forecast; not investment advice. The <a href="#rotation/research" data-rview="research">Rotation research</a> view counts how lines move between quadrants.</p></details>`;
  return out;
}
function bindRrgbt() {
  if (typeof document === 'undefined') return;
  document.querySelectorAll('#workspace [data-rrgbq]').forEach(b => b.onclick = () => {
    const q = b.dataset.rrgbq, cur = new Set(String(state.rrgbx || '').split('+').filter(Boolean));
    if (cur.has(q)) { if (cur.size > 1) cur.delete(q) } else cur.add(q);
    state.rrgbx = RRGB_Q.map(x => x[0]).filter(x => cur.has(x)).join('+');
    render();
  });
  document.querySelectorAll('#workspace [data-rrgbm]').forEach(b => b.onclick = () => { state.rrgbx = b.dataset.rrgbm; render() });
  const c = document.getElementById('rrgbcsv');
  if (c) c.onclick = () => { const keep = exported; exported = rrgbStore.members || []; if (typeof downloadCSV === 'function') downloadCSV(); exported = keep };
  if (typeof bindTips === 'function') bindTips();
}
if (typeof document !== 'undefined' && !document.getElementById('rrgb-css')) {
  const st = document.createElement('style'); st.id = 'rrgb-css';
  const H = ':is(#hub-root,body) ';
  st.textContent = `${H}.rrgb-quads{align-items:center;gap:8px}${H}.rrgb-lab{font-size:13px;color:var(--muted)}${H}.rrgb-note{font-size:12.5px}`
    + `${H}.rrgb-q{display:inline-flex;align-items:center;gap:6px;font:inherit;font-size:13px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);cursor:pointer}`
    + `${H}.rrgb-q.on{border-color:var(--ink);color:var(--ink);font-weight:600;background:color-mix(in srgb, var(--ink) 6%, var(--surface))}`
    + `${H}.rrgb-t td:first-child{min-width:0}${H}.rrgb-t td.num,${H}.rrgb-t th.num,${H}.rrgb-m-t td.num,${H}.rrgb-m-t th.num{text-align:right}${H}.rrgb-m{text-align:left;padding:0;margin:0;color:var(--ink);font-weight:600}`
    + `${H}.rrgb-m .mk-key{margin-right:2px}${H}tr.rrgb-on{outline:2px solid var(--ink);outline-offset:-2px}${H}.rrgb-t{min-width:0}`
    + `${H}.rrgb-t th{white-space:normal;vertical-align:bottom}${H}.rrgb-m{white-space:normal}`
    + `${H}.rrgb-now{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}${H}.rrgb-now svg{margin:0 auto}${H}.rrgb-m-t{min-width:0}${H}.rrgb-m-t td:first-child{min-width:0}`
    + `@media (max-width:560px){${H}.rrgb-t th,${H}.rrgb-t td,${H}.rrgb-m-t th,${H}.rrgb-m-t td{padding:7px 6px;font-size:12.5px}${H}.rrgb-note{flex-basis:100%}${H}.mob-stats th{white-space:normal}}`;
  document.head.appendChild(st);
}
if (typeof module !== 'undefined') module.exports = { rrgbGet, rrgbName, rrgbNow, rrgbScatter, rrgBacktestView, bindRrgbt, rrgbStore, RRGB_Q };
