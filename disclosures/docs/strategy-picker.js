/* Momentum → Strategy picker (#momentum/picker): momentum × RRG strategies on the valued companies, back-tested week by
   week since 2000 (app/combo_backtest.py, the nightly research build: data/research/paths/backtest/combo.json) — which
   one is best both lately and over the long run (strategies fade), what it holds today, since when, how long its
   positions have lasted, when and on what condition each is sold, how each strategy has done lately against before, and
   whether picking the recent leader each January has paid. The values after costs, the growth chart and the years come
   from momentum-backtest.js (mobLine, mobCagr, mobChart, mobYearBars, mobPc …). */
const SP_RULES = {
  mom: { name: 'Momentum alone', short: 'Momentum alone' },
  'imp-fade': { name: 'Buy the turn (Improving), sell when RS-Momentum fades', short: 'Improving → fades' },
  'imp-fail': { name: 'Buy the turn (Improving), sell if it falls back to Lagging', short: 'Improving → Lagging' },
  'lead-fade': { name: 'Buy in Leading, sell when RS-Momentum fades', short: 'Leading → fades' },
  'lead-trend': { name: 'Buy in Leading, sell when it loses its trend (RS-Ratio below 100)', short: 'Leading → below trend' },
  'up-fade': { name: 'Buy while gaining (Leading or Improving), sell when RS-Momentum fades', short: 'Gaining → fades' },
  'up-fail': { name: 'Buy while gaining (Leading or Improving), sell in Lagging', short: 'Gaining → Lagging' },
  'dip-ride': { name: 'Buy the dip (a winner in Lagging), sell when it reaches Weakening', short: 'Dip → Weakening' }
};
const SP_M = { '12-1': ['12-1', '12-1 momentum (the last year less the latest month)'], '6-1': ['6-1', '6-1 momentum (the last 6 months less the latest month)'], '3m': ['3-month', '3-month momentum'] };
const SP_Q = ['Leading', 'Weakening', 'Lagging', 'Improving'], SP_QC = ['lead', 'weak', 'lag', 'imp'];
const SP_W = [['3y', 'The last 3 years'], ['1y', 'The last year']];
const SP_C = [['0', 'None (theoretical)'], ['5', '0.05% a trade'], ['10', '0.10% a trade'], ['25', '0.25% a trade']];
const SP_P = [['all', 'Since 2000'], ['10y', '10 years'], ['5y', '5 years'], ['3y', '3 years'], ['1y', '1 year']];
const spStore = {};
function spData() {
  const m = spStore.d || (spStore.d = {});
  if (m.data || m.err || m.loading) return m;
  if (typeof fetch !== 'function') { m.err = 'this browser cannot load data files'; return m }
  m.loading = fetch((globalThis.FF_HUB_ROOT || '') + 'data/research/paths/backtest/combo.json', { cache: 'no-cache' })
    .then(r => { if (!r.ok) throw Error(r.status === 404 ? 'not built yet' : 'HTTP ' + r.status); return r.json() })
    .then(d => { if (!d || d.schema !== 'combo-backtest.v1') throw Error('an unexpected file'); m.data = d })
    .catch(e => { m.err = e.message })
    .finally(() => { m.loading = null; if (typeof state === 'object' && state.tab === 'momentum' && typeof render === 'function') render() });
  return m;
}
const spParts = k => { const [rule, measure, band] = String(k).split('|'); return { rule, measure, band: +band } };
const spName = (k, short) => { const p = spParts(k), r = SP_RULES[p.rule] || { name: p.rule, short: p.rule }; return `${short ? r.short : r.name} · ${(SP_M[p.measure] || [p.measure])[0]} · top ${p.band}%` };
const spQs = qs => (qs || []).map(q => SP_Q[q]).join(qs && qs.length === 2 ? ' or ' : ', ');
// the strategy's rule in words: what buys a company and what sells it
function spRule(d, k) {
  const p = spParts(k), rq = (d.rule_quadrants || {})[p.rule] || {}, band = (d.bands || []).find(b => b[0] === p.band) || [p.band, p.band * 2], m = (SP_M[p.measure] || [p.measure, p.measure])[1];
  return { enter: `It buys a company in the top ${band[0]}% of those ranked by ${m}${rq.enter ? `, when its weekly RRG against SPY is in ${spQs(rq.enter)}` : ''}.`,
    exit: `It sells when the company drops out of the top ${band[1]}% by the same momentum${rq.exit ? `, or when its RRG reaches ${spQs(rq.exit)}` : ''} — checked at each week's last close.`, out: band[1], exitQ: rq.exit || [] };
}
// the weeks a position has left, from the lengths of the strategy's closed trades longer than the weeks it has run
function spLeft(hist, h) {
  if (!hist || !hist.length) return null;
  const from = Math.max(0, Math.min(hist.length - 1, h));
  let tot = 0;
  for (let i = from; i < hist.length; i++) tot += hist[i];
  if (tot < 20) return null;
  const q = f => { let c = 0; for (let i = from; i < hist.length; i++) { c += hist[i]; if (c >= f * tot) return Math.max(1, i + 1 - h) } return hist.length - h };
  return { lo: q(0.25), med: q(0.5), hi: q(0.75), n: tot };
}
const spOrd = n => { const v = Math.round(n), t = v % 100; return v + (t >= 11 && t <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][v % 10] || 'th') };
const spAdd = (date, weeks) => new Date(Date.parse(date) + weeks * 7 * 864e5).toISOString().slice(0, 10);
const spWeeks = (a, b) => Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / (7 * 864e5)));
// the gap to the equal weight a year after costs, and its 95% interval from the t-statistic
function spGap(d, k, period, cost) {
  const s = (((d.stats || {})[k] || {})[period]) || null;
  if (!s || !mobFin(s.excess)) return null;
  const g = s.excess - cost * (s.turn_w || 0) * 52, se = mobFin(s.t) && s.t !== 0 ? Math.abs(s.excess / s.t) : null;
  return { gap: g, lo: se != null ? g - 1.96 * se : null, hi: se != null ? g + 1.96 * se : null, t: s.t };
}
// each calendar year's gap to the equal weight, after costs, as tiny bars
function spSpark(d, k, cost) {
  const a = (d.years || {})[k] || [], e = Object.fromEntries(((d.years || {}).ew || []).map(r => [r[0], r[1]])), tw = ((((d.stats || {})[k] || {}).all) || {}).turn_w || 0;
  const v = a.map(([y, r]) => [y, mobFin(r) && mobFin(e[y]) ? r - e[y] - cost * tw * 52 : null]);
  if (!v.length) return '';
  const W = 132, H = 26, bw = W / v.length, mx = 0.2;                        // ±20% a year fills the height; more is clipped
  let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Each year's gap to the equal weight" class="sp-spark">`;
  s += `<line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="var(--line)"/>`;
  v.forEach(([y, g], i) => { if (g == null) return; const h = Math.max(1, Math.min(1, Math.abs(g) / mx) * (H / 2 - 1)); s += `<rect x="${(i * bw + 0.5).toFixed(1)}" y="${(g >= 0 ? H / 2 - h : H / 2).toFixed(1)}" width="${Math.max(1, bw - 1).toFixed(1)}" height="${h.toFixed(1)}" fill="${g >= 0 ? 'var(--mk-profit)' : 'var(--mk-cost)'}" data-tip="${typeof tip === 'function' ? tip([[String(y), 'calendar year'], [mobPc(g), 'gap to the equal weight']]) : ''}"/>` });
  return s + '</svg>';
}
// how long positions lasted: weeks 1 … 52 and longer, the median marked
function spHist(hist, med, narrow) {
  if (!hist || !hist.length) return '';
  const b = hist.slice(0, 52).concat([hist.slice(52).reduce((a, x) => a + x, 0)]), tot = b.reduce((a, x) => a + x, 0) || 1, mx = Math.max(...b) / tot;
  const W = narrow ? 360 : 760, H = 160, L = 34, R = 8, T = 10, B = 26, bw = (W - L - R) / b.length;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="How many weeks the strategy's positions lasted" style="display:block;width:100%;height:auto">`;
  for (const f of [0, 0.5, 1]) { const y = T + (1 - f) * (H - T - B); s += `<line x1="${L}" x2="${W - R}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--line)"${f ? ' stroke-dasharray="2 4"' : ''}/><text x="${L - 4}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="10.5" fill="var(--muted)">${Math.round(100 * f * mx)}%</text>` }
  b.forEach((c, i) => {
    const h = c / tot / (mx || 1) * (H - T - B), x = L + i * bw;
    s += `<rect x="${(x + 0.5).toFixed(1)}" y="${(H - B - h).toFixed(1)}" width="${Math.max(1, bw - 1).toFixed(1)}" height="${Math.max(0, h).toFixed(1)}" rx="1" fill="${i + 1 === Math.round(med) ? 'var(--accent)' : 'color-mix(in srgb, var(--accent) 45%, transparent)'}" data-tip="${typeof tip === 'function' ? tip([[i === 52 ? 'over 52 weeks' : `${i + 1} week${i ? 's' : ''}`, 'held'], [pct(c / tot, 1), 'of the positions']]) : ''}"/>`;
    if (i === 0 || (i + 1) % (narrow ? 13 : 4) === 0 || i === 52) s += `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--muted)">${i === 52 ? '52+' : i + 1}</text>`;
  });
  return s + '</svg>';
}
function spView() {
  const m = spData();
  if (m.err) return `<div class="empty">The strategy picker is built every night after the close (the research build) and is not on file yet (${esc(m.err)}).</div>`;
  if (!m.data) return empty('Reading the strategies…');
  const d = m.data, keys = Object.keys(d.trades || {});
  for (const [k, list, def] of [['spw', SP_W, '3y'], ['spc', SP_C, '10'], ['spp', SP_P, 'all']]) if (!list.some(x => x[0] === String(state[k]))) state[k] = def;
  const win = state.spw, cost = +state.spc / 1e4, period = state.spp, W = (d.walk || {})[win] || {}, F = W.fields || [], at = Object.fromEntries(F.map((f, i) => [f, i]));
  const ranked = W.now || [], pick = (ranked.find(r => r[at.eligible]) || ranked[0] || [keys[0]])[0];
  if (state.spk && !keys.includes(state.spk)) state.spk = '';
  const k = state.spk || pick, narrow = typeof mobNarrow === 'function' && mobNarrow(), rule = spRule(d, k), tr = (d.trades || {})[k] || {}, isPick = k === pick;
  const wl = (SP_W.find(x => x[0] === win) || [])[1].toLowerCase(), cl = (SP_C.find(x => x[0] === String(state.spc)) || [])[1];
  let out = `<div class="toolbar">${field('spw', 'Judge by', SP_W, win)}${field('spc', 'Trading costs', SP_C, String(state.spc))}${field('spk', 'Strategy', ranked.map(r => [r[0], spName(r[0], true) + (r[at.eligible] ? '' : ' (holds too few)')]), k)}</div>`;
  out += `<p class="muted">${fmt(d.companies)} valued companies, weekly since ${esc(d.start)} to ${esc(d.as_of)} · ${keys.length} strategies · built ${esc(String(d.generated_at || '').replace('T', ' ').slice(0, 16))} UTC</p>`;
  // the strategy now
  const row = ranked.find(r => r[0] === k) || [], gA = spGap(d, k, 'all', cost), gW = spGap(d, k, win, cost), net = mobCagr(d, k, cost, 'all'), netW = mobCagr(d, k, cost, win);
  const S = (d.walk || {})[win] ? W.summary || {} : {};
  const kp = (l, v, c) => (typeof kpi === 'function' ? kpi(l, v, c) : `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`);
  out += `<div class="mob-wrap"><div class="panel sp-hero"><h3>${isPick ? 'The strategy that fits now' : 'The strategy you chose'}: ${esc(spName(k))}</h3>`
    + (isPick ? '' : `<p><button type="button" class="action" data-spk="">← Back to the pick: ${esc(spName(pick, true))}</button></p>`)
    + `<p class="sub">${isPick ? `Of the strategies holding ${fmt(S.min_held || 20)} companies or more, the one whose record against the equal weight is best both over ${esc(wl)} and since 2000 — the lower of its two information ratios (the gap's mean over its spread), so one that has faded scores low and so does one on a lucky run.` : `The pick by that measure is ${esc(spName(pick))}.`}</p>`
    + `<p><b>Buy:</b> ${esc(rule.enter)}<br><b>Sell:</b> ${esc(rule.exit)}</p>`
    + `<div class="metrics">${kp(`A year, ${wl}`, mobPc(netW), `the equal weight ${mobPc(mobCagr(d, 'ew', 0, win))} · SPY ${mobPc(mobCagr(d, 'spy', 0, win))}`)}`
    + `${kp('A year since 2000', mobPc(net), `${gA ? `${mobPc(gA.gap)} a year ahead of the equal weight${gA.lo != null ? ` (95%: ${mobPc(gA.lo)} to ${mobPc(gA.hi)})` : ''}` : ''}`)}`
    + `${kp('A position lasts', tr.weeks_median != null ? `${fmt(tr.weeks_median)} weeks` : '—', `the median of ${fmt(tr.n)} trades; the mean ${fmt(tr.weeks_mean, 1)}`)}`
    + `${kp('A trade earns', mobPc(tr.mean, 1), `median ${mobPc(tr.median, 1)} · up ${pct(tr.win, 0)} · ahead of the equal weight ${pct(tr.beat_ew, 0)}`)}</div>`
    + `<p class="muted">${costs(cl)} Score ${row[at.score] != null ? row[at.score].toFixed(2) : '—'} (${esc(wl)} ${row[at.ir] != null ? row[at.ir].toFixed(2) : '—'}, since 2000 ${row[at.ir_all] != null ? row[at.ir_all].toFixed(2) : '—'}) · ${fmt((d.now[k] || []).length)} companies held now, ${fmt((d.held || {})[k], 0)} on average · ${fmt(tr.a_year, 0)} trades a year.${(gW && gA && gW.gap < gA.gap - 0.03) ? ' <b>Fading:</b> its gap lately is below its long-run one.' : ''}</p></div>`;
  function costs(c) { return cost ? `Returns after ${esc(c)}.` : 'Returns before costs.' }
  // what it holds now
  const cn = d.companies_now || {}, ci = Object.fromEntries((cn.fields || []).map((f, i) => [f, i])), p = spParts(k), hist = tr.hist;
  const holds = (d.now[k] || []).map(([key, since, ret]) => {
    const c = (cn.rows || {})[key] || [], h = spWeeks(since, d.as_of), left = spLeft(hist, h), pc = c[ci['pct_' + p.measure]], q = c[ci.q];
    return { key, since, ret, h, left, pc, x: c[ci.x], y: c[ci.y], q, exit: left ? spAdd(d.as_of, left.med) : null };
  }).sort((a, b) => (a.since < b.since ? 1 : a.since > b.since ? -1 : a.key < b.key ? -1 : 1));
  const thr = 1 - rule.out / 100;
  out += `<div class="panel"><h3>What it holds at the close of ${esc(d.as_of)}: ${fmt(holds.length)} companies, equal weight</h3><p class="sub">Each with the week it was bought and its return since. <b>Expected sale</b>: the date by which half of the strategy's past positions that had lasted as long were sold, and under it the span of the middle half — a guide, not a schedule: a company is sold the week its momentum drops out of the top ${rule.out}%${rule.exitQ.length ? ` or its RRG reaches ${esc(spQs(rule.exitQ))}` : ''}. <b>Momentum, margin</b>: its ${esc((SP_M[p.measure] || [p.measure])[0])} percentile among the companies, and how many points it stands above the sale line.</p>`;
  if (holds.length) {
    const tk = s => (typeof tkLink === 'function' ? tkLink(s) : `<b>${esc(s)}</b>`);
    const badge = r => (r.q != null && r.q >= 0 ? `<span class="badge rrg-b-${SP_QC[r.q]}">${SP_Q[r.q]}</span>` : '—');
    const sale = r => (r.left ? `${esc(r.exit)}<br><span class="muted">${esc(spAdd(d.as_of, r.left.lo).slice(5))} – ${esc(spAdd(d.as_of, r.left.hi))}</span>` : '—');
    const margin = r => (r.pc != null ? `${spOrd(100 * r.pc)} <span class="muted">+${Math.round(100 * (r.pc - thr))}</span>` : '—');
    out += '<div class="sp-holds">' + (narrow
      ? table(['Company', 'Return', 'Momentum, margin', 'RRG', 'Expected sale'], holds.map(r => [`${tk(r.key)}<br><span class="muted">${r.h} wk · ${esc(r.since.slice(5))}</span>`, mobTone(r.ret, mobPc(r.ret)), margin(r), badge(r), sale(r)]))
      : table(['Company', 'Bought', 'Weeks', 'Return since', 'Momentum, margin', 'RS-Ratio', 'RS-Momentum', 'RRG now', 'Expected sale'],
        holds.map(r => [tk(r.key), esc(r.since), String(r.h), mobTone(r.ret, mobPc(r.ret)), margin(r), r.x != null ? r.x.toFixed(2) : '—', r.y != null ? r.y.toFixed(2) : '—', badge(r), sale(r)]))) + '</div>';
    exported = holds.map(r => ({ strategy: spName(k), company: r.key, bought: r.since, weeks_held: r.h, return_since: r.ret, momentum_measure: p.measure, momentum_percentile: r.pc, sold_below_percentile: thr,
      rs_ratio: r.x, rs_momentum: r.y, rrg_quadrant: r.q != null && r.q >= 0 ? SP_Q[r.q] : null, expected_sale: r.exit, expected_sale_early: r.left ? spAdd(d.as_of, r.left.lo) : null, expected_sale_late: r.left ? spAdd(d.as_of, r.left.hi) : null }));
    out += `<div class="section-head"><h3>These holdings as CSV</h3><button class="action" id="csv">Export CSV ↓</button></div>`;
  } else out += empty('It holds nothing at this close: no company meets its rule.');
  out += `<h4>How long its positions lasted</h4>${spHist(hist, tr.weeks_median, narrow)}</div>`;
  // every strategy, lately against the long run
  const tw = ['Strategy', 'Score', `Ratio, ${win === '3y' ? '3 years' : '1 year'}`, 'Ratio since 2000', `Gap a year, ${win === '3y' ? '3 years' : '1 year'}`, 'Gap since 2000', 'Holds', 'Lasts', 'Each year against the equal weight'];
  out += `<div class="panel"><h3>Every strategy: lately against the long run</h3><p class="sub">Ordered by the score (the lower of the two ratios, at 0.10% a trade); the gaps to the equal weight a year at the costs chosen above. The bars: each calendar year since 2000, green ahead of the equal weight, red behind — a strategy that has faded shows red to the right. Tap one to see it.</p><div class="tablebox"><table class="sp-t"><thead><tr>${tw.map((h, i) => `<th${i && i < 8 ? ' class="num"' : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>`
    + ranked.map(r => {
      const kk = r[0], a = spGap(d, kk, 'all', cost), w = spGap(d, kk, win, cost), t2 = (d.trades || {})[kk] || {};
      return `<tr class="${kk === k ? 'sp-on' : ''}${r[at.eligible] ? '' : ' sp-few'}"><td><button type="button" class="text-button sp-k" data-spk="${esc(kk)}">${esc(spName(kk, true))}</button>${r[at.eligible] ? '' : '<br><span class="muted">holds too few to pick</span>'}</td>`
        + `<td class="num">${r[at.score] != null ? r[at.score].toFixed(2) : '—'}</td><td class="num">${r[at.ir] != null ? r[at.ir].toFixed(2) : '—'}</td><td class="num">${r[at.ir_all] != null ? r[at.ir_all].toFixed(2) : '—'}</td>`
        + `<td class="num">${w ? mobTone(w.gap, mobPc(w.gap)) : '—'}</td><td class="num">${a ? mobTone(a.gap, mobPc(a.gap)) : '—'}</td><td class="num">${fmt((d.held || {})[kk], 0)}</td><td class="num">${t2.weeks_median != null ? fmt(t2.weeks_median) + ' wk' : '—'}</td><td>${spSpark(d, kk, cost)}</td></tr>`;
    }).join('') + '</tbody></table></div></div>';
  // the walk-forward record
  if (W.records && W.records.length) {
    const lines = ['pick', 'avg', 'ew', 'spy'].map((s, i) => ({ name: ['The pick, switched each January', 'Every strategy averaged', 'Equal weight of the companies', 'SPY'][i], col: ['var(--accent)', 'var(--rot-1)', 'var(--muted)', 'var(--ink)'][i], w: [2.4, 1.6, 1.4, 1.4][i], dash: i === 2 ? '5 4' : '',
      pts: [[W.start, 1]].concat((W.months || []).map((mo, j) => [mo, W.series[s][j]]).filter(x => mobFin(x[1]) && x[1] > 0)) }));
    const full = W.records.filter(x => !x.partial);
    out += `<div class="panel"><h3>Does picking the recent leader pay? Each January since ${esc(String((W.records[0] || {}).year || ''))}</h3><p class="sub">Each January the strategy with the best score at that date (judged over ${esc(wl)} and since 2000, at 0.10% a trade, among those holding ${fmt(S.min_held)} or more) is held for the year. It beat the average strategy in <b>${fmt(S.pick_ahead_of_avg)} of ${fmt(S.years)}</b> years (${mobPc(S.pick_mean)} a year against ${mobPc(S.avg_mean)}, both as gaps to the equal weight) and the equal weight in ${fmt(S.pick_ahead_of_ew)}; its median rank among the ${fmt(S.strategies)} the next year: ${fmt(S.median_rank)}. The rule was chosen among a dozen tried on this data — all beat the average strategy by between 0 and 4% a year — so take the edge as small.</p>`
      + mobChart(lines, narrow) + `<div class="mk-legend">${lines.map(l => `<span><i class="mk-key" style="background:${l.col}"></i>${esc(l.name)}${l.dash ? ' (dashed)' : ''}</span>`).join('')}</div>`
      + `<details><summary>Year by year</summary><div class="tablebox"><table class="sp-t"><thead><tr><th>Year</th><th>The pick</th><th class="num">Its gap that year</th><th class="num">The average's</th><th class="num">Its rank</th></tr></thead><tbody>`
      + W.records.slice().reverse().map(x => `<tr><td>${x.year}${x.partial ? ' (to date)' : ''}</td><td><button type="button" class="text-button sp-k" data-spk="${esc(x.pick)}">${esc(spName(x.pick, true))}</button></td><td class="num">${mobTone(x.pick_next, mobPc(x.pick_next))}</td><td class="num">${mobTone(x.avg_next, mobPc(x.avg_next))}</td><td class="num">${fmt(x.rank)} of ${fmt(S.strategies)}</td></tr>`).join('')
      + `</tbody></table></div></details><p class="muted">${fmt(full.length)} full years.</p></div>`;
  }
  // the chosen strategy over time
  const line = mobLine(d, k, cost, period), spy = mobLine(d, 'spy', 0, period), ew = mobLine(d, 'ew', 0, period), nm = spName(k, true);
  if (line) {
    out += `<div class="panel"><h3>${esc(nm)}: the growth of $1${cost ? ' after costs' : ''}</h3><div class="toolbar">${field('spp', 'Period', SP_P, period)}</div>`
      + mobChart([{ name: nm, pts: line.pts, col: 'var(--accent)', w: 2.4 }, { name: 'SPY', pts: spy.pts, col: 'var(--ink)', w: 1.6 }, { name: 'Equal weight of the companies', pts: ew.pts, col: 'var(--muted)', w: 1.4, dash: '5 4' }], narrow)
      + `<div class="mk-legend"><span><i class="mk-key" style="background:var(--accent)"></i>${esc(nm)}</span><span><i class="mk-key" style="background:var(--ink)"></i>SPY</span><span><i class="mk-key" style="background:var(--muted)"></i>Equal weight of the companies (dashed)</span></div>`;
    const P = SP_P.map(x => x[0]), st = (kk, pp) => (((d.stats || {})[kk] || {})[pp]) || {};
    const r4 = (l, f) => `<tr><td>${l}</td>${P.map(pp => `<td class="num">${f(pp)}</td>`).join('')}</tr>`;
    out += `<div class="tablebox"><table class="mob-stats sp-p"><thead><tr><th></th>${SP_P.map(x => `<th class="num">${esc(x[1])}</th>`).join('')}</tr></thead><tbody>`
      + r4(`A year${cost ? ', after costs' : ''}`, pp => mobTone(mobCagr(d, k, cost, pp), mobPc(mobCagr(d, k, cost, pp))))
      + r4('The equal weight', pp => mobPc(mobCagr(d, 'ew', 0, pp))) + r4('SPY', pp => mobPc(mobCagr(d, 'spy', 0, pp)))
      + r4('Gap to the equal weight', pp => { const g = spGap(d, k, pp, cost); return g ? mobTone(g.gap, mobPc(g.gap)) : '—' })
      + r4('Its t-statistic', pp => (mobFin(st(k, pp).t) ? st(k, pp).t.toFixed(1) : '—'))
      + r4('Maximum drawdown', pp => mobPc(st(k, pp).mdd, 0)) + r4('Months ahead of SPY', pp => pct(st(k, pp).ahead, 0))
      + '</tbody></table></div>';
    const yrs = ((d.years || {})[k] || []).map(([y, v]) => [String(y), mobFin(v) ? (1 + v) * Math.pow(1 - cost * ((st(k, 'all').turn_w) || 0), 52) - 1 : null, String(y) === d.as_of.slice(0, 4)]);
    const ye = ((d.years || {}).ew || []).map(([y, v]) => [String(y), v]);
    out += `<h4>Year by year, against the equal weight</h4>${mobYearBars(yrs, ye, nm, 'Equal weight', narrow)}<div class="mk-legend"><span><i class="mk-key" style="background:var(--accent);border-radius:2px"></i>${esc(nm)}</span><span><i class="mk-key" style="background:var(--muted);border-radius:2px"></i>Equal weight of the companies</span></div></div>`;
  }
  out += '</div>';
  out += `<details class="panel"><summary>How it is computed, and what it leaves out</summary><p class="sub">Each week, at its last close, the valued companies (daily closes adjusted for dividends and splits, the Move odds data) are ranked by their momentum — 12-1, 6-1 or the last 3 months — and placed on the weekly RRG against SPY (the chart's own formula). A strategy buys a company that enters the top 10% or 20% while its RRG stands in the rule's quadrants, and holds it — equal weight, rebalanced each week — until it drops out of a wider band (the top 20% or 40%) or its RRG reaches the rule's exit quadrants. Costs are the turnover times the cost of a trade. <b>Today's companies only:</b> firms that failed or were bought since are missing, which flatters buying dips most; compare with the equal weight of the same companies, which carries the same bias. <b>Strategies fade:</b> the score asks for a record both lately and since 2000, and the January test above shows how little the recent leader's lead has carried into the next year. History, not a forecast; not investment advice. See also the <a href="#momentum/backtest">momentum back-test</a> and the <a href="#rotation/rrgbt">RRG portfolios</a>.</p></details>`;
  return out;
}
function bindSp() {
  if (typeof document === 'undefined') return;
  document.querySelectorAll('#workspace [data-spk]').forEach(b => b.onclick = () => { state.spk = b.dataset.spk; state.page = 0; render(); if (typeof scrollTo === 'function') scrollTo({ top: 0, behavior: 'smooth' }) });
  if (typeof bindTips === 'function') bindTips();
}
if (typeof document !== 'undefined' && !document.getElementById('sp-css')) {
  const st = document.createElement('style'); st.id = 'sp-css';
  const H = ':is(#hub-root,body) ';
  st.textContent = `${H}.sp-t{min-width:0}${H}.sp-t td:first-child{min-width:0}${H}.sp-t th{white-space:normal;vertical-align:bottom}${H}.sp-t th.num,${H}.sp-t td.num{text-align:right}${H}.sp-k{text-align:left;padding:0;margin:0;color:var(--ink);font-weight:600;white-space:normal}`
    + `${H}tr.sp-on{outline:2px solid var(--ink);outline-offset:-2px}${H}tr.sp-few{opacity:.62}${H}.sp-spark{display:block}${H}.sp-p{min-width:0}${H}.sp-holds table{min-width:0}${H}.sp-holds td:first-child{min-width:0}${H}.sp-holds th{white-space:normal;vertical-align:bottom}${H}.sp-hero h3{font-size:17px}`
    + `@media (max-width:560px){${H}.sp-t th,${H}.sp-t td,${H}.sp-holds th,${H}.sp-holds td{padding:7px 6px;font-size:12.5px}${H}.sp-p th{white-space:normal}}`;
  document.head.appendChild(st);
}
if (typeof module !== 'undefined') module.exports = { spData, spView, bindSp, spName, spRule, spLeft, spGap, spSpark, spHist, spStore, SP_RULES };
