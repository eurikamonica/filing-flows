// strategy-picker.js (the Hub's Momentum tab → Strategy picker): the file app/combo_backtest.py writes, read in the
// browser — the load (pending, missing, another file), the pick and how it follows the window until a strategy is
// chosen, the rule in words, the holdings (bought, weeks, the margin above the sale line, the expected sale from the
// lengths of past positions), the CSV rows, every strategy lately against the long run, the January record, the chosen
// strategy over periods, a phone's layout, and the Momentum tab's wiring. Charts from momentum-backtest.js.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
global.window = global;
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
global.pct = (v, d = 1) => (v == null ? '—' : fmt(v * 100, d) + '%');
global.uniq = (a) => [...new Set(a)];
global.kpi = (l, v, c = '') => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.field = (id, label, items, v) => `<select id="${id}">${items.map((x) => `<option value="${esc(x[0])}"${String(x[0]) === String(v) ? ' selected' : ''}>${esc(x[1])}</option>`).join('')}</select>`;
global.table = (h, rows) => `<table class="lb"><thead><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.head = (t, s, tag) => `<h2>${t}</h2><p class="sub">${s}</p><span>${tag}</span>`;
global.state = { tab: 'momentum', mou: 'picker' };
global.exported = [];
const tips = [];
global.tip = (rows) => { tips.push(rows); return tips.length - 1; };
let renders = 0;
global.render = () => { renders++; };
const FILES = {};
global.fetch = async (u) => (FILES[u] ? { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(FILES[u])) } : { ok: false, status: 404, json: async () => null });
const MB = require(path.join(__dirname, '..', 'docs', 'momentum-backtest.js'));
for (const k of ['mobLine', 'mobCagr', 'mobYears', 'mobChart', 'mobYearBars', 'mobUsd', 'mobCut', 'mobFin', 'mobPc', 'mobTone', 'mobAbs', 'mobNarrow']) global[k] = MB[k];
const M = require(path.join(__dirname, '..', 'docs', 'momentum.js'));
const SP = require(path.join(__dirname, '..', 'docs', 'strategy-picker.js'));
Object.assign(global, { spView: SP.spView, spStore: SP.spStore, bindSp: SP.bindSp });
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const eq = (a, b, m) => { assert.deepEqual(a, b, m); n++; };
const near = (a, b, m, tol = 1e-9) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };
const tick = () => new Promise((r) => setTimeout(r, 0));
const count = (s, sub) => s.split(sub).length - 1;

// ------------------------------------------------------------------ the file (app/combo_backtest.py build())
const months = [];
for (let y = 2016; y <= 2026; y++) for (let m = 0; m < 12 && !(y === 2026 && m > 9); m++) {
  const d = new Date(Date.UTC(y, m + 1, 0)); while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1); months.push(d.toISOString().slice(0, 10));
}
const growth = (g) => months.map((_, i) => +Math.pow(1 + g, (i + 1) / 12).toPrecision(4));
const st = (g, x, t) => ({ cagr: g, vol: 0.2, ratio: 1, mdd: -0.4, up: 0.6, ahead: 0.55, beta: 1, alpha: 0, total: 1, excess: x, t, turn_w: 0.1 });
const KEYS = ['dip-ride|12-1|10', 'mom|6-1|10', 'imp-fail|3m|10', 'up-fail|6-1|10'];
const hist = Array(157).fill(0); hist[3] = 50; hist[6] = 100; hist[9] = 50; hist[19] = 20;      // lasted 4, 7, 10, 20 weeks
const DOC = { schema: 'combo-backtest.v1', generated_at: '2026-10-31T01:00:00+00:00', as_of: '2026-10-30', start: '2016-01-08', formed_from: '2016-01-01', companies: 1888, cost: 0.001, min_ranked: 200,
  measures: ['12-1', '6-1', '3m'], bands: [[10, 20], [20, 40]], rules: ['mom', 'imp-fade', 'imp-fail', 'lead-fade', 'lead-trend', 'up-fade', 'up-fail', 'dip-ride'],
  rule_quadrants: { mom: { enter: null, exit: null }, 'imp-fail': { enter: [3], exit: [2] }, 'up-fail': { enter: [0, 3], exit: [2] }, 'dip-ride': { enter: [2], exit: [1] } },
  months, periods: { all: '2016-01-08', '10y': '2016-11-04', '5y': '2021-11-05', '3y': '2023-11-03', '1y': '2025-11-07' },
  series: {}, stats: {}, turn: {}, held: { 'dip-ride|12-1|10': 63, 'mom|6-1|10': 180, 'imp-fail|3m|10': 2.2, 'up-fail|6-1|10': 108 }, years: {}, trades: {}, now: {},
  companies_now: { fields: ['pct_12-1', 'pct_6-1', 'pct_3m', 'x', 'y', 'q'], rows: { AMD: [0.97, 0.9, 0.8, 99.1, 98.2, 2], MU: [0.93, 0.95, 0.85, 98.5, 99.0, 2], NVDA: [0.99, 0.99, 0.95, 103, 101, 0] } } };
for (const [i, k] of KEYS.entries()) {
  DOC.series[k] = growth(0.15 + 0.01 * i); DOC.stats[k] = { all: st(0.15, 0.04 - 0.01 * i, 2), '10y': st(0.16, 0.05, 2), '5y': st(0.14, 0.03, 1), '3y': st(0.3, 0.12 - 0.02 * i, 1.5), '1y': st(0.1, -0.02 + 0.02 * i, 0.5) };
  DOC.turn[k] = 0.02; DOC.years[k] = [[2016, 0.1], [2017, 0.2], [2026, 0.05]];
  DOC.trades[k] = { n: 220, a_year: 20, weeks_median: 7, weeks_mean: 8.2, mean: 0.043, median: 0.032, win: 0.6, beat_ew: 0.53, beat_spy: 0.56, excess: 0.012, hist };
  DOC.now[k] = [];
}
DOC.now['dip-ride|12-1|10'] = [['AMD', '2026-10-30', 0], ['MU', '2026-10-09', -0.0755]];
DOC.now['mom|6-1|10'] = [['NVDA', '2025-03-07', 0.8]];
DOC.series.spy = growth(0.1); DOC.stats.spy = Object.fromEntries(Object.keys(DOC.periods).map((p) => [p, { ...st(0.1, -0.05, -1), turn_w: 0 }]));
DOC.series.ew = growth(0.12); DOC.stats.ew = Object.fromEntries(Object.keys(DOC.periods).map((p) => [p, { ...st(0.12, 0, null), turn_w: 0 }]));
DOC.years.ew = [[2016, 0.08], [2017, 0.1], [2026, 0.04]]; DOC.years.spy = DOC.years.ew;
const walk = (order) => ({ weeks: 156, start: '2019-01-04', months: months.slice(36), series: { pick: months.slice(36).map(() => 1.1), avg: months.slice(36).map(() => 1.05), ew: months.slice(36).map(() => 1.08), spy: months.slice(36).map(() => 1.07) },
  records: [{ year: 2019, pick: 'mom|6-1|10', pick_score: 0.3, pick_ir: 0.4, pick_ir_all: 0.3, pick_gap: 0.05, pick_next: 0.04, avg_next: -0.01, best: 'dip-ride|12-1|10', best_next: 0.2, rank: 6, partial: false },
    { year: 2026, pick: 'dip-ride|12-1|10', pick_score: 0.48, pick_ir: 1, pick_ir_all: 0.48, pick_gap: 0.12, pick_next: -0.02, avg_next: 0.03, best: 'imp-fail|3m|10', best_next: 0.9, rank: 3, partial: true }],
  summary: { years: 1, pick_mean: 0.04, avg_mean: -0.01, pick_ahead_of_avg: 1, pick_ahead_of_ew: 1, median_rank: 6, strategies: 4, min_held: 20 },
  fields: ['key', 'score', 'ir', 'ir_all', 'gap', 'held', 'eligible'], now: order });
DOC.walk = { '3y': walk([['imp-fail|3m|10', 0.93, 0.93, 1.2, 0.21, 2.2, false], ['dip-ride|12-1|10', 0.46, 0.9, 0.46, 0.14, 100, true], ['mom|6-1|10', 0.33, 0.38, 0.33, 0.05, 250, true], ['up-fail|6-1|10', 0.12, 0.12, 0.15, 0.02, 145, true]]),
  '1y': walk([['mom|6-1|10', 0.33, 0.33, 0.33, 0.05, 250, true], ['dip-ride|12-1|10', 0.2, 0.2, 0.46, 0.03, 100, true], ['up-fail|6-1|10', 0.1, 0.1, 0.15, 0.02, 145, true], ['imp-fail|3m|10', 0.05, 1.5, 0.05, 0.4, 2, false]]) };
const URL = 'data/research/paths/backtest/combo.json';

(async () => {
  // ------------------------------------------------------------------ helpers
  eq(SP.spName('dip-ride|12-1|10'), 'Buy the dip (a winner in Lagging), sell when it reaches Weakening · 12-1 · top 10%', 'a name');
  eq(SP.spName('mom|3m|20', true), 'Momentum alone · 3-month · top 20%', 'a short name');
  const rule = SP.spRule(DOC, 'up-fail|6-1|10');
  eq(rule.enter, 'It buys a company in the top 10% of those ranked by 6-1 momentum (the last 6 months less the latest month), when its weekly RRG against SPY is in Leading or Improving.', 'the entry in words');
  eq(rule.exit, "It sells when the company drops out of the top 20% by the same momentum, or when its RRG reaches Lagging — checked at each week's last close.", 'the exit in words');
  ok(!SP.spRule(DOC, 'mom|6-1|10').enter.includes('RRG'), 'momentum alone: no RRG');
  // the weeks left: closed positions lasted 4 (50), 7 (100), 10 (50), 20 (20) weeks
  eq(SP.spLeft(hist, 0), { lo: 7, med: 7, hi: 10, n: 220 }, 'a new position: the lengths themselves');
  eq(SP.spLeft(hist, 5), { lo: 2, med: 2, hi: 5, n: 170 }, 'five weeks in: the 7-week ones have 2 left');
  eq(SP.spLeft(hist, 12), { lo: 8, med: 8, hi: 8, n: 20 }, 'twelve weeks in: only the 20-week ones are left');
  eq(SP.spLeft(hist, 25), null, 'past every length: too few to say');
  const g = SP.spGap(DOC, 'dip-ride|12-1|10', 'all', 0.001);
  near(g.gap, 0.04 - 0.001 * 0.1 * 52, 'the gap after costs'); near(g.hi - g.lo, 2 * 1.96 * 0.04 / 2, 'its interval from the t-statistic');
  ok(SP.spSpark(DOC, 'dip-ride|12-1|10', 0).includes('<rect') && count(SP.spSpark(DOC, 'dip-ride|12-1|10', 0), '<rect') === 3, 'a bar a year');
  ok(SP.spHist(hist, 7, false).includes('fill="var(--accent)"'), 'the median length marked');

  // ------------------------------------------------------------------ the load
  ok(/Reading the strategies/.test(SP.spView()), 'pending');
  await tick(); await tick();
  ok(/not on file yet \(not built yet\)/.test(SP.spView()) && renders > 0, 'missing');
  delete SP.spStore.d; FILES[URL] = { schema: 'other.v1' }; SP.spView(); await tick(); await tick();
  ok(/an unexpected file/.test(SP.spView()), 'another file');
  delete SP.spStore.d; FILES[URL] = DOC; SP.spView(); await tick(); await tick();

  // ------------------------------------------------------------------ the pick now
  Object.assign(state, { spw: 'x', spc: '7', spp: '?', spk: 'nope' });
  tips.length = 0;
  let out = SP.spView();
  eq([state.spw, state.spc, state.spp, state.spk], ['3y', '10', 'all', ''], 'unknown choices back to the defaults; no strategy chosen');
  ok(out.includes('The strategy that fits now: Buy the dip (a winner in Lagging), sell when it reaches Weakening · 12-1 · top 10%'), 'the pick: the best eligible score, not the lucky one that holds two');
  ok(out.includes('<b>Buy:</b> It buys a company in the top 10% of those ranked by 12-1 momentum') && out.includes('<b>Sell:</b> It sells when the company drops out of the top 20%'), 'the rule');
  ok(out.includes('<label>A position lasts</label><strong>7 weeks</strong>') && out.includes('<label>A trade earns</label><strong>+4.3%</strong>'), 'how long and how much');
  ok(out.includes('+3.5% a year ahead of the equal weight (95%: −0.4% to +7.4%)'), 'the long-run gap after costs, its interval from the t-statistic');
  ok(out.includes('Score 0.46 (the last 3 years 0.90, since 2000 0.46)'), 'the score');
  // the holdings: newest first, the margin, the expected sale
  ok(out.includes('What it holds at the close of 2026-10-30: 2 companies, equal weight'), 'the holdings\' title');
  const rows = [...out.matchAll(/<tr><td><b>(\w+)<\/b><\/td><td>([\d-]+)<\/td><td>(\d+)<\/td>/g)].map((m) => [m[1], m[2], m[3]]);
  eq(rows, [['AMD', '2026-10-30', '0'], ['MU', '2026-10-09', '3']], 'newest first, with the weeks held');
  ok(out.includes('97th <span class="muted">+17</span>') && out.includes('93rd <span class="muted">+13</span>'), 'the percentile and its margin above the top 20%');
  ok(out.includes('2026-12-18<br><span class="muted">12-18 – 2027-01-08</span>'), 'a new position: sold around 7 weeks on');
  ok(out.includes('2026-11-27<br><span class="muted">11-27 – 2026-12-18</span>'), 'three weeks in: 4 more weeks, the middle half 4 to 7');
  eq(exported.length, 2, 'the holdings as CSV');
  eq([exported[1].company, exported[1].weeks_held, exported[1].momentum_percentile, exported[1].sold_below_percentile, exported[1].rrg_quadrant, exported[1].expected_sale], ['MU', 3, 0.93, 0.8, 'Lagging', '2026-11-27'], 'a CSV row');
  // every strategy: the score's order, the one that holds too few marked
  ok(out.includes('Every strategy: lately against the long run'), 'the table');
  eq([...out.matchAll(/<tr class="[^"]*"><td><button type="button" class="text-button sp-k" data-spk="([^"]+)"/g)].map((m) => m[1]), ['imp-fail|3m|10', 'dip-ride|12-1|10', 'mom|6-1|10', 'up-fail|6-1|10'], 'in the file\'s order');
  ok(/<tr class=" sp-few"><td><button[^>]*data-spk="imp-fail\|3m\|10"[^>]*>[^<]*<\/button><br><span class="muted">holds too few to pick/.test(out), 'too few to pick');
  // the January record
  ok(out.includes('Does picking the recent leader pay? Each January since 2019') && out.includes('beat the average strategy in <b>1 of 1</b> years'), 'the record');
  ok(out.includes('2026 (to date)'), 'this year marked');
  // the chosen strategy over periods
  ok(out.includes('Dip → Weakening · 12-1 · top 10%: the growth of $1 after costs') && out.includes('<th class="num">Since 2000</th><th class="num">10 years</th>'), 'the chart and the periods');
  ok(out.includes('Year by year, against the equal weight'), 'the years');
  ok(tips.length > 10, 'tooltips');

  // the window: the pick follows it while no strategy is chosen
  state.spw = '1y';
  out = SP.spView();
  ok(out.includes('The strategy that fits now: Momentum alone · 6-1 · top 10%'), 'the last year\'s pick');
  ok(out.includes('What it holds at the close of 2026-10-30: 1 companies') || out.includes('1 companies'), 'its holdings');
  // a strategy chosen: it stays, with the way back
  state.spk = 'up-fail|6-1|10'; state.spw = '3y';
  out = SP.spView();
  ok(out.includes('The strategy you chose: Buy while gaining (Leading or Improving), sell in Lagging · 6-1 · top 10%'), 'chosen');
  ok(out.includes('data-spk="">← Back to the pick: Dip → Weakening · 12-1 · top 10%'), 'the way back');
  ok(out.includes('It holds nothing at this close'), 'nothing held');
  const btn = [];
  global.document = { querySelectorAll: (sel) => (sel.includes('data-spk') ? btn : []), getElementById: () => null };
  btn.push({ dataset: { spk: '' } }); SP.bindSp(); btn[0].onclick();
  eq(state.spk, '', 'back to the pick');
  delete global.document;
  // costs off
  state.spc = '0';
  ok(SP.spView().includes('Returns before costs.'), 'before costs');
  state.spc = '10';
  // a phone
  global.innerWidth = 390;
  out = SP.spView();
  ok(out.includes('<th>Momentum, margin</th><th>RRG</th><th>Expected sale</th>') && !out.includes('<th>RS-Ratio</th>'), 'fewer columns');
  ok(out.includes('<b>MU</b><br><span class="muted">3 wk · 10-09</span>') && !out.includes('<th>Bought</th>'), 'the weeks and the day bought under the name');
  global.innerWidth = 1280;

  // ------------------------------------------------------------------ the Momentum tab
  Object.assign(state, { mou: 'picker', mot: '' });
  out = M.momentumView();
  ok(out.includes('<option value="picker" selected>Strategy picker: momentum × RRG, now</option>'), 'the universe menu');
  ok(out.includes('Derived · weekly closes since 2000') && out.includes('The strategy that fits now'), 'the picker in the tab');
  state.mot = 'NVDA';
  ok(M.momentumView().includes('← The strategy picker</button>'), 'a ticker typed: the way back');
  state.mot = '';
  state.mou = 'stocks'; M.momentumDeepLink('picker'); eq(state.mou, 'picker', '#momentum/picker');
  eq(M.momentumNotice().text, 'Derived view · Strategy picker · weekly closes 2016-01-08 to 2026-10-30 · built 2026-10-31 01:00 UTC', 'the notice');
  const html = fs.readFileSync(path.join(__dirname, '..', 'docs', 'index.html'), 'utf8');
  ok(html.indexOf('src="strategy-picker.js"') > html.indexOf('src="momentum-backtest.js"'), 'loaded after the charts it uses');
  console.log(`strategy picker: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
