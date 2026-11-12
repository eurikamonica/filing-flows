// momentum-backtest.js (the Hub's Momentum tab, "Universe: Back-test"): the file app/momentum_backtest.py writes, read
// in the browser — the values after costs and rebased to a period, the annual return after costs, the calendar years,
// the grid (coloured against the equal-weight universe; long-short against zero), the chart (a line that loses 99%
// stops at the floor, marked ×), the statistics, the CSV rows, the phone layout, the load (pending, missing, another
// file), and the tab's dispatch, deep link and notice. The hub's helpers and fetch stubbed; no browser, no network.
const assert = require('node:assert/strict');
const path = require('node:path');
global.window = global;
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
global.pct = (v, d = 1) => (v == null ? '—' : fmt(v * 100, d) + '%');
global.uniq = (a) => [...new Set(a)];
global.kpi = (l, v, c = '') => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.field = (id, label, items, v) => `<select id="${id}">${items.map((x) => `<option value="${esc(x[0])}"${String(x[0]) === String(v) ? ' selected' : ''}>${esc(x[1])}</option>`).join('')}</select>`;
global.table = (h, rows) => `<table class="lb"><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.head = (t, s, tag) => `<h2>${t}</h2><p class="sub">${s}</p><span>${tag}</span>`;
global.state = { tab: 'momentum' };
global.exported = [];
const tips = [];
global.tip = (rows) => { tips.push(rows); return tips.length - 1; };
let renders = 0;
global.render = () => { renders++; };
const FILES = {};
global.fetch = async (u) => (FILES[u] ? { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(FILES[u])) } : { ok: false, status: 404, json: async () => null });
const M = require(path.join(__dirname, '..', 'docs', 'momentum.js'));
const B = require(path.join(__dirname, '..', 'docs', 'momentum-backtest.js'));
// in the page the scripts share one global scope; here the tab finds the back-test's functions on the global object
Object.assign(global, { mobView: B.mobView, mobStore: B.mobStore, bindMobGrid: B.bindMobGrid });
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const eq = (a, b, m) => { assert.deepEqual(a, b, m); n++; };
const near = (a, b, m, tol = 1e-9) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };
const tick = () => new Promise((r) => setTimeout(r, 0));
const count = (s, sub) => s.split(sub).length - 1;

// ------------------------------------------------------------------ the file (app/momentum_backtest.py build())
// month-ends (the last weekday) from January 2016 to October 2026; the back-test starts on 2016-01-04
const months = [];
for (let y = 2016; y <= 2026; y++) for (let m = 0; m < 12 && !(y === 2026 && m > 9); m++) {
  const d = new Date(Date.UTC(y, m + 1, 0));
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1);
  months.push(d.toISOString().slice(0, 10));
}
const RANKS = ['1', '5', '10', '21', '63', '12-1'], HOLDS = [1, 5, 10, 21, 63];
// annual returns before costs: momentum persists at the longer rankings, short rankings reverse
const CAGR = { '1': -0.3, '5': -0.1, '10': 0.02, '21': 0.08, '63': 0.14, '12-1': 0.2 };
const growth = (g) => months.map((_, i) => +Math.pow(1 + g, (i + 1) / 12).toPrecision(4));
const st = (g, extra = {}) => ({ cagr: g, vol: 0.2, ratio: +(g / 0.2).toFixed(2), mdd: -0.35, up: 0.6, ahead: 0.55, beta: 1.05, alpha: 0.02, total: 1, from: '2016-01-04', ...extra });
const DOC = { schema: 'momentum-backtest.v1', generated_at: '2026-10-30T23:40:00+00:00', as_of: months[months.length - 1], start: '2016-01-04', stocks: 1888, share: 0.1, min_ranked: 200,
  ranks: RANKS, holds: HOLDS, months, periods: { all: '2016-01-04', '10y': '2016-11-01', '5y': '2021-11-01' }, traded: months.map((_, i) => 932 + i * 7),
  series: {}, stats: {}, turn: {}, held: {} };
for (const r of RANKS) for (const K of HOLDS) for (const side of ['top', 'bottom', 'ls']) {
  const k = `${r}|${K}|${side}`, g = side === 'top' ? CAGR[r] : side === 'bottom' ? -CAGR[r] / 2 : CAGR[r] * 1.5;
  DOC.series[k] = growth(g);
  DOC.stats[k] = { all: st(g), '10y': st(g), '5y': st(g + 0.01) };
  DOC.turn[k] = side === 'ls' ? 2 * (1 / K) : 1 / K;
  DOC.held[k] = 134;
}
// the one-day long-short loses everything: a cent on the dollar within two years, 1e-5 at the end
DOC.series['1|1|ls'] = months.map((_, i) => +Math.max(1e-5, Math.pow(0.75, i + 1)).toPrecision(4));
DOC.series.spy = growth(0.1); DOC.stats.spy = { all: st(0.1, { beta: 1, alpha: 0 }), '10y': st(0.1, { beta: 1, alpha: 0 }), '5y': st(0.12, { beta: 1, alpha: 0 }) };
DOC.series.ew = growth(0.15); DOC.stats.ew = { all: st(0.15), '10y': st(0.15), '5y': st(0.13) };
const URL = 'data/research/paths/backtest/momentum.json';

(async () => {
  // ------------------------------------------------------------------ pure helpers
  eq([B.mobUsd(152000), B.mobUsd(2.5e6), B.mobUsd(1234.4), B.mobUsd(88.934), B.mobUsd(8.061), B.mobUsd(0.05), B.mobUsd(1.6e-5), B.mobUsd(null)],
    ['$152k', '$2.5M', '$1,234', '$88.93', '$8.06', '$0.05', '$0.000016', '—'], 'dollars');
  eq(B.mobTicks(Math.log(0.5), Math.log(120)), [0.5, 1, 2, 5, 10, 20, 50, 100], '1-2-5 a decade over two decades');
  eq(B.mobTicks(Math.log(0.01), Math.log(200)), [0.01, 0.1, 1, 10, 100], 'every decade over four');
  eq(B.mobTicks(Math.log(0.79), Math.log(2.2)), [0.8, 1, 1.25, 1.5, 2], 'finer under a decade');
  eq([B.mobTick(1e-5), B.mobTick(1e5), B.mobTick(2e6), B.mobTick(0.5), B.mobTick(1.25)], ['$1e-5', '$100k', '$2M', '$0.5', '$1.25'], 'tick labels');

  // the values after costs: each trading day 1 − cost × turnover; days counted from the start at 252 a year
  const d = DOC, key = '12-1|21|top', c = 0.001, f = 1 - c * d.turn[key];
  const l0 = B.mobLine(d, key, 0, 'all'), l1 = B.mobLine(d, key, c, 'all');
  eq(l0.pts[0], ['2016-01-04', 1], 'the line starts at $1 on the first day');
  eq(l0.pts.length, months.length + 1, 'every month-end');
  near(l0.pts[12][1], d.series[key][11], 'before costs: the file\'s values');
  const days = (Date.parse(months[11]) - Date.parse(d.start)) / 864e5 * 252 / 365.25;
  near(l1.pts[12][1], d.series[key][11] * Math.pow(f, days), 'after costs: the daily drag compounded');
  near(l1.f, f, 'the daily factor'); near(l1.turn, d.turn[key], 'the turnover');
  // a period: rebased at the last month-end before its first day
  const l5 = B.mobLine(d, key, 0, '5y');
  eq(l5.pts[0], ['2021-10-29', 1], 'rebased at the month-end before 2021-11-01');
  near(l5.pts[1][1], d.series[key][months.indexOf('2021-11-30')] / d.series[key][months.indexOf('2021-10-29')], 'the next month relative to it');
  eq(l5.pts[l5.pts.length - 1][0], d.as_of, 'to the latest month-end');
  eq(B.mobLine(d, 'nope|1|top', 0, 'all'), null, 'a line not in the file');
  // annual returns after costs
  near(B.mobCagr(d, key, 0, 'all'), 0.2, 'before costs: the file\'s');
  near(B.mobCagr(d, key, c, 'all'), 1.2 * Math.pow(f, 252) - 1, 'after costs: a year of the daily drag');
  near(B.mobCagr(d, key, 0, '5y'), 0.21, 'a period\'s own');
  eq(B.mobCagr(d, 'nope', 0, 'all'), null, 'none');
  // calendar years: December to December, the first from the start, this year to date
  const yrs = B.mobYears([['2019-12-31', 1], ['2020-06-30', 1.1], ['2020-12-31', 1.2], ['2021-06-30', 1.5], ['2021-12-31', 1.8], ['2022-03-31', 1.62]]);
  eq(yrs.map((y) => y[0]), ['2020', '2021', '2022'], 'three years');
  near(yrs[0][1], 0.2, '2020'); near(yrs[1][1], 0.5, '2021'); near(yrs[2][1], -0.1, '2022 to date');
  eq(yrs.map((y) => y[2]), [false, false, true], 'only the last is partial');
  eq(B.mobCut(B.mobLine(d, '1|1|ls', 0, 'all').pts), '2017-05-31', 'the month the one-day long-short fell below a cent (0.75^17)');
  eq(B.mobCut(l0.pts), null, 'the 12-1 never did');

  // ------------------------------------------------------------------ the load
  delete B.mobStore.bt;
  let m = B.mobData();
  ok(m.loading && !m.data && !m.err, 'pending');
  ok(/Reading the back-test/.test(B.mobView()), 'a pending load says so');
  await tick(); await tick();
  ok(m.err === 'not built yet' && !m.data, 'a missing file: not built yet');
  ok(/built every night after the close/.test(B.mobView()) && /not built yet/.test(B.mobView()), 'and the view says when it comes');
  ok(renders > 0, 'the tab redrawn when the load ends');
  delete B.mobStore.bt;
  FILES[URL] = { schema: 'something-else.v1' };
  m = B.mobData(); await tick(); await tick();
  eq(m.err, 'an unexpected file', 'another file at that path');
  delete B.mobStore.bt;
  FILES[URL] = DOC;
  m = B.mobData(); await tick(); await tick();
  ok(m.data && m.data.as_of === '2026-10-30' && !m.err, 'the file loaded');
  const before = renders; B.mobData(); await tick();
  eq(renders, before, 'loaded once');

  // ------------------------------------------------------------------ the view
  Object.assign(state, { mou: 'backtest', mot: '', mobr: 'nonsense', mobh: '7', mobs: 'x', mobc: '3', mobp: '20y' });
  tips.length = 0;
  let out = B.mobView();
  eq([state.mobr, state.mobh, state.mobs, state.mobc, state.mobp], ['12-1', '21', 'top', '10', 'all'], 'unknown choices back to the defaults');
  ok(out.includes('Annual return, every ranking and holding period · top tenth, after 0.10% a trade'), 'the grid\'s title');
  ok(out.includes('1,888 valued companies') && out.includes('932 trading at the start') && out.includes(`${fmt(d.traded[d.traded.length - 1])} now`), 'the universe');
  eq(count(out, 'data-mob="'), 30, 'six rankings × five holding periods');
  eq(count(out, 'mob-on'), 1, 'one cell chosen');
  ok(/mob-on"[^>]*><button[^>]*data-mob="12-1\|21"/.test(out), 'the chosen one');
  // colours against the equal-weight universe (15% a year): 12-1 top (20% less costs) above, the one-day top (−30%) below
  const cellOf = (html, k) => html.match(new RegExp(`<td class="num mob-cell[^"]*" style="([^"]*)"><button[^>]*data-mob="${k.replace('|', '\\|')}"`))[1];
  ok(cellOf(out, '12-1|21').includes('--mk-profit'), 'above the equal-weight universe: green');
  ok(cellOf(out, '1|1').includes('--mk-cost'), 'below: red');
  ok(cellOf(out, '63|63').includes('--mk-cost'), '14% a year is below 15%: red, though above SPY');
  ok(/Green above the equal-weight average of the same companies \(\+15\.0% a year/.test(out) && out.includes('SPY: +10.0% a year'), 'what the colours compare with');
  ok(out.includes('Top tenth by 12-1, held 1 month: the growth of $1 after costs'), 'the chart\'s title');
  ok(out.includes('<svg') && out.includes('Equal-weight universe (dashed)'), 'the chart and its legend');
  ok(!out.includes('lost more than 99%') && !out.includes('>×<'), 'nothing wiped out');
  // the statistics: volatility without a sign, the costs rows with a cost
  ok(/Volatility \(a year\)<\/td><td class="num">20\.0%/.test(out), 'volatility unsigned');
  ok(/Annual return, before costs<\/td><td class="num"><span class="positive">\+20\.0%/.test(out), 'before costs');
  ok(out.includes('Annual return, after 0.10% a trade') && out.includes('Costs a year at this rate'), 'after costs');
  ok(/Turnover \(traded a year, both ways\)<\/td><td class="num">1200%/.test(out), 'turnover: 1/21 a day × 252');
  ok(out.includes('Stocks held per portfolio</td><td class="num">134'), 'holdings');
  ok(out.includes('Year by year') && out.includes('mk-legend'), 'the years and their legend');
  ok(out.includes('href="#strategies"'), 'the Strategies tab linked');
  ok(tips.length > months.length, 'a tooltip for every month-end and year');
  const t0 = tips.find((r) => r[0][0] === '2020-06');
  ok(t0 && t0.length === 4 && t0[1][1].startsWith('Top tenth') && t0[2][1] === 'SPY', 'a month\'s tooltip: the date, then each line');
  // the CSV: every combination for the chosen portfolio and period
  eq(exported.length, 30, 'thirty rows');
  const x = exported.find((r) => r.ranked_by === '12-1' && r.held === '1 month');
  near(x.annual_return, 0.2, 'csv annual return'); near(x.annual_return_after_costs, 1.2 * Math.pow(f, 252) - 1, 'csv after costs');
  near(x.turnover_a_year, 12, 'csv turnover'); eq([x.portfolio, x.period, x.from, x.stocks_held], ['top', 'all', '2016-01-04', 134], 'csv labels');

  // no costs: the after-costs rows go, the titles say so
  state.mobc = '0';
  out = B.mobView();
  ok(out.includes('top tenth, before costs') && !out.includes('Costs a year at this rate') && !out.includes('Annual return, after'), 'no costs');
  ok(out.includes('the growth of $1</h3>'), 'no "after costs" in the chart title');

  // the one-day long-short: green or red against zero, the line stops at the floor, the subtitle says when
  Object.assign(state, { mobs: 'ls', mobr: '1', mobh: '1' });
  out = B.mobView();
  ok(out.includes('long-short, before costs'), 'long-short');
  ok(/From 2016-01-04\. Green above zero, red below/.test(out), 'against zero');
  ok(cellOf(out, '12-1|21').includes('--mk-profit') && cellOf(out, '1|1').includes('--mk-cost'), '30% a year above zero, −45% below');
  ok(out.includes('It had lost more than 99% by 2017-05; its line stops there (×).'), 'the wipe-out told');
  ok(out.includes('>×</text>') && out.includes('−99%+'), 'and marked');
  ok(!/\$1e-/.test(out), 'no ticks under a cent');

  // a period
  Object.assign(state, { mobs: 'top', mobr: '12-1', mobh: '21', mobp: '5y' });
  out = B.mobView();
  ok(out.includes('From 2021-11-01.') && out.includes('Statistics · the last 5 years'), 'the last five years');
  ok(out.includes('the first year from 2021-10-29'), 'the years from its first month-end');
  eq(exported[0].period, '5y', 'the csv follows');

  // a phone: short labels, whole percents, the smaller charts
  global.innerWidth = 390;
  out = B.mobView();
  ok(out.includes('Rank ↓<br>Hold →') && out.includes('>2 wks<') && out.includes('>Qtr<'), 'short labels');
  ok(/data-mob="12-1\|21"[^>]*>\+21%<\/button>/.test(out), 'whole percents');
  ok(out.includes('viewBox="0 0 380 250"') && out.includes('viewBox="0 0 380 200"'), 'phone-sized charts');
  ok(out.includes('>Equal weight<'), 'a shorter column');
  global.innerWidth = 1280;
  ok(B.mobView().includes('viewBox="0 0 760 300"'), 'desktop-sized again');

  // ------------------------------------------------------------------ the tab
  Object.assign(state, { mou: 'backtest', mot: '', mobp: 'all' });
  out = M.momentumView();
  ok(out.includes('<option value="backtest" selected>Back-test: portfolios since 2000</option>'), 'the universe menu');
  ok(out.includes('Derived · daily closes since 2000') && out.includes('since 2000: each trading day'), 'the back-test\'s heading');
  ok(out.includes('Annual return, every ranking and holding period'), 'the back-test in the tab');
  state.mot = 'NVDA';
  out = M.momentumView();
  ok(out.includes('← The back-test</button>') && out.includes('id="mo-one" data-k="NVDA"'), 'a ticker typed: its history, and the way back');
  state.mot = '';
  state.mou = 'stocks'; M.momentumDeepLink('backtest'); eq([state.mou, state.mot], ['backtest', ''], '#momentum/backtest');
  state.mou = 'stocks'; M.momentumDeepLink('back-test'); eq(state.mou, 'backtest', '#momentum/back-test');
  eq(M.momentumNotice().text, 'Derived view · Momentum back-test · daily closes 2016-01-04 to 2026-10-30 · built 2026-10-30 23:40 UTC', 'the notice');
  B.mobStore.bt = { err: 'not built yet' };
  eq(M.momentumNotice().text, 'Derived view · Momentum back-test · not on file yet (not built yet)', 'the notice without the file');
  B.mobStore.bt = {};
  eq(M.momentumNotice(), null, 'no notice while loading');
  state.mou = 'stocks';
  ok(!M.momentumView().includes('Annual return, every ranking'), 'the other universes untouched');

  console.log(`momentum back-test view: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
