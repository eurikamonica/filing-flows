// rrg-backtest.js (the Hub's Rotation tab → RRG portfolios): the files app/rrg_backtest.py writes, read in the browser
// — the load (pending, missing, another file), the choices and their defaults, the table of every quadrant mix (after
// costs, against the group's equal weight, ordered), the quadrant toggles, the chosen mix's chart and statistics, what
// a portfolio bought now earned in history, the lines in the mix now, the CSV rows, a phone's layout, the clocks, and
// the Rotation tab's wiring. The charts come from momentum-backtest.js. The hub's helpers and fetch stubbed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
global.window = global;
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
global.pct = (v, d = 1) => (v == null ? '—' : fmt(v * 100, d) + '%');
global.kpi = (l, v, c = '') => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.field = (id, label, items, v) => `<select id="${id}">${items.map((x) => `<option value="${esc(x[0])}"${String(x[0]) === String(v) ? ' selected' : ''}>${esc(x[1])}</option>`).join('')}</select>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.ROT_VIEWS = [['rrg', 'RRG'], ['rrgbt', 'RRG portfolios']];
global.state = { tab: 'rotation', rview: 'rrgbt' };
global.exported = [];
const tips = [];
global.tip = (rows) => { tips.push(rows); return tips.length - 1; };
let renders = 0;
global.render = () => { renders++; };
const FILES = {};
global.fetch = async (u) => (FILES[u] ? { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(FILES[u])) } : { ok: false, status: 404, json: async () => null });
const MB = require(path.join(__dirname, '..', 'docs', 'momentum-backtest.js'));
// in the page the scripts share one global scope; here the RRG view finds the chart helpers on the global object
for (const k of ['mobLine', 'mobCagr', 'mobYears', 'mobChart', 'mobYearBars', 'mobUsd', 'mobCut', 'mobFin', 'mobPc', 'mobTone', 'mobAbs', 'mobNarrow']) global[k] = MB[k];
const R = require(path.join(__dirname, '..', 'docs', 'rrg-backtest.js'));
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const eq = (a, b, m) => { assert.deepEqual(a, b, m); n++; };
const tick = () => new Promise((r) => setTimeout(r, 0));
const count = (s, sub) => s.split(sub).length - 1;

// ------------------------------------------------------------------ the files (app/rrg_backtest.py build())
const QN = ['leading', 'weakening', 'lagging', 'improving'];
const MIXES = [];
for (let size = 1; size <= 4; size++) {
  const go = (start, cur) => { if (cur.length === size) { MIXES.push(cur.map((i) => QN[i]).join('+')); return; } for (let i = start; i < 4; i++) go(i + 1, cur.concat(i)); };
  go(0, []);
}
const months = [];
for (let y = 2016; y <= 2026; y++) for (let m = 0; m < 12 && !(y === 2026 && m > 9); m++) {
  const d = new Date(Date.UTC(y, m + 1, 0)); while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1); months.push(d.toISOString().slice(0, 10));
}
const growth = (g) => months.map((_, i) => +Math.pow(1 + g, (i + 1) / 12).toPrecision(4));
const st = (g) => ({ cagr: g, vol: 0.18, ratio: +(g / 0.18).toFixed(2), mdd: -0.4, up: 0.6, ahead: 0.5, beta: 0.95, alpha: 0.01, total: 1 });
// annual returns by mix: Lagging alone best, Improving a little ahead, Leading behind (a hair less down the file's
// order, so no two tie); the equal weight 8%
const G = (mk) => 0.08 + (mk === 'lagging' ? 0.03 : 0) + (mk.includes('improving') ? 0.01 : 0) - (mk.includes('leading') ? 0.015 : 0) - 0.0005 * MIXES.indexOf(mk);
const BY_G = MIXES.slice().sort((a, b) => G(b) - G(a));
function groupDoc(clock, holds, extra = {}) {
  const d = { schema: 'rrg-backtest.v1', generated_at: '2026-10-30T23:50:00+00:00', as_of: months[months.length - 1], clock, clock_label: clock === 'w' ? "Weekly RRG (each week's last close)" : 'Daily RRG (every close)',
    group: 'sectors', label: 'Sector ETFs against the S&P 500', lines: 11, start: '2016-01-04', formed_from: '2015-10-02', holds, per_year: clock === 'w' ? 52 : 252, quadrants: QN, mixes: MIXES,
    months, periods: { all: '2016-01-04', '10y': '2016-11-01', '5y': '2021-11-01' }, traded: months.map(() => 11), series: {}, stats: {}, turn: {}, held: {}, invested: {}, expect: {}, ...extra };
  for (const mk of MIXES) for (const K of holds) {
    const k = `${mk}|${K}`, g = G(mk);
    d.series[k] = growth(g); d.stats[k] = { all: st(g), '10y': st(g), '5y': st(g + 0.02) }; d.turn[k] = 0.02 / K; d.held[k] = mk.split('+').length * 2.5; d.invested[k] = mk === 'leading' ? 0.8 : 1;
    const mean = 0.002 * K * (1 + (mk.includes('improving') ? 0.2 : 0)), ewm = 0.002 * K;
    d.expect[k] = { all: { n: 500, n_indep: 500 / K, mean, lo: mean - 0.004, hi: mean + 0.004, median: mean * 1.2, up: 0.6, beat: 0.5, spy: 0.0018 * K, excess: mean - 0.0018 * K, beat_ew: mk === 'leading+weakening+lagging+improving' ? 0 : 0.53, ew: ewm, excess_ew: mean - ewm }, '10y': null, '5y': null };
  }
  d.series.spy = growth(0.1); d.stats.spy = { all: { ...st(0.1), beta: 1, alpha: 0 }, '10y': { ...st(0.1), beta: 1, alpha: 0 }, '5y': { ...st(0.12), beta: 1, alpha: 0 } };
  d.series.ew = growth(0.08); d.stats.ew = { all: st(0.08), '10y': st(0.08), '5y': st(0.1) };
  d.now = { date: d.as_of, fields: ['key', 'name', 'x', 'y', 'q', 'periods'], rows: [['XLB', 'Materials sector (XLB)', 100.75, 101.17, 0, 3], ['XLC', 'Communication Services sector (XLC)', 99.38, 101.29, 3, 2],
    ['XLE', 'Energy sector (XLE)', 100.38, 98.93, 1, 2], ['XLF', 'Financials sector (XLF)', 101.23, 101.79, 0, 3], ['XLI', 'Industrials sector (XLI)', 99.44, 101.23, 3, 3], ['XLK', 'Technology sector (XLK)', 98.94, 98.49, 2, 3],
    ['XLP', 'Consumer Staples sector (XLP)', 101.64, 101.32, 0, 4], ['XLRE', 'Real Estate sector (XLRE)', 100.79, 102.07, 0, 2], ['XLU', 'Utilities sector (XLU)', 100.47, 101.21, 0, 2],
    ['XLV', 'Health Care sector (XLV)', 102.22, 101.22, 0, 5], ['XLY', 'Consumer Discretionary sector (XLY)', 101.21, 103.08, 0, 1]] };
  return d;
}
const INDEX = { schema: 'rrg-backtest-index.v1', generated_at: '2026-10-30T23:50:00+00:00', as_of: '2026-10-30', quadrants: QN, mixes: MIXES,
  clocks: { w: { holds: [1, 4, 13], label: "Weekly RRG (each week's last close)" }, d: { holds: [1, 5, 21], label: 'Daily RRG (every close)' } },
  groups: [{ key: 'world', label: 'Countries and regions (ETFs in dollars) against the S&P 500', lines: 20, clocks: { w: { file: 'w-world.json' } } },
    { key: 'sectors', label: 'Sector ETFs against the S&P 500', lines: 11, clocks: { w: { file: 'w-sectors.json' }, d: { file: 'd-sectors.json' } } }] };
const URL = (f) => 'data/research/paths/backtest/rrg/' + f;

(async () => {
  // ------------------------------------------------------------------ helpers
  eq(R.rrgbName('lagging+improving'), 'Lagging + Improving', 'names');
  const pts = R.rrgbNow(groupDoc('w', [1, 4, 13]));
  eq(pts.length, 11, 'the lines now'); eq(pts[1], { k: 'XLC', n: 'Communication Services sector (XLC)', x: 99.38, y: 101.29, q: 3, p: 2 }, 'one line');
  const sc = R.rrgbScatter(pts, new Set(['improving']), { one: 'week', many: 'weeks' }, false);
  eq(count(sc, '<circle'), 11, 'every line a dot'); eq(count(sc, 'var(--rot-1)" opacity="0.9"'), 2, 'the two Improving ones in colour');
  ok(sc.includes('>XLC</text>') && sc.includes('>XLK</text>'), 'a small group: every line labelled');
  const many = Array.from({ length: 300 }, (_, i) => ({ k: 'T' + i, n: 'T' + i, x: 95 + (i % 10), y: 95 + Math.floor(i / 30), q: i % 4, p: 1 }));
  const sc2 = R.rrgbScatter(many, new Set(['leading']), { one: 'day', many: 'days' }, true);
  ok(!sc2.includes('>T1</text>') && sc2.includes('viewBox="0 0 360 300"'), 'many lines: no labels, a phone-sized chart');

  // ------------------------------------------------------------------ the load
  let out = R.rrgBacktestView();
  ok(/Reading the RRG portfolios/.test(out), 'pending');
  await tick(); await tick();
  out = R.rrgBacktestView();
  ok(/built every night after the close/.test(out) && /not built yet/.test(out), 'no index yet: when it comes');
  ok(renders > 0, 'redrawn when the load ends');
  delete R.rrgbStore['index.json'];
  FILES[URL('index.json')] = { schema: 'something.v1' };
  R.rrgBacktestView(); await tick(); await tick();
  ok(/an unexpected file/.test(R.rrgBacktestView()), 'another file');
  delete R.rrgbStore['index.json'];
  FILES[URL('index.json')] = INDEX;
  R.rrgBacktestView(); await tick(); await tick();
  out = R.rrgBacktestView();
  ok(/Reading the back-test of the sector etfs/.test(out), 'the index in, the group loading');
  ok(out.includes('<option value="sectors" selected>'), 'sectors by default, though listed second');
  await tick(); await tick();
  out = R.rrgBacktestView();
  ok(/not on file yet \(not built yet\)/.test(out), 'the group file missing');
  delete R.rrgbStore['w-sectors.json'];
  FILES[URL('w-sectors.json')] = groupDoc('w', [1, 4, 13]);
  FILES[URL('d-sectors.json')] = groupDoc('d', [1, 5, 21]);
  R.rrgBacktestView(); await tick(); await tick();

  // ------------------------------------------------------------------ the view
  Object.assign(state, { rrgbg: 'nope', rrgbc: 'x', rrgbh: '99', rrgbcost: '3', rrgbp: '20y', rrgbs: '?', rrgbx: 'nothing' });
  tips.length = 0;
  out = R.rrgBacktestView();
  eq([state.rrgbg, state.rrgbc, state.rrgbh, state.rrgbcost, state.rrgbp, state.rrgbs, state.rrgbx], ['sectors', 'w', '4', '10', 'all', 'ret', 'improving'], 'unknown choices back to the defaults');
  ok(out.includes('<option value="4" selected>4 weeks</option>') && out.includes('<option value="d">Daily RRG (every close)</option>'), 'the holding periods and clocks');
  ok(out.includes('11 lines · Weekly RRG') && out.includes('portfolios formed from 2015-10-02, counted from 2016-01-04 to 2026-10-30'), 'the summary');
  // the toggles
  eq(count(out, 'data-rrgbq="'), 4, 'four quadrant toggles');
  ok(out.includes('data-rrgbq="improving" aria-pressed="true"') && out.includes('data-rrgbq="leading" aria-pressed="false"'), 'Improving on');
  // the table: every mix, after costs, ordered by the annual return
  ok(out.includes('Every mix of quadrants · held 4 weeks, after 0.10% a trade'), 'its title');
  eq(count(out, 'data-rrgbm="'), 15, 'fifteen mixes');
  const order = [...out.matchAll(/data-rrgbm="([^"]+)"/g)].map((m) => m[1]);
  eq(order, BY_G, 'the best first');
  eq([order[0], order[order.length - 1]], ['lagging', 'leading+weakening+lagging'], 'Lagging alone first, a Leading mix last');
  ok(/<tr class="rrgb-on"><td><button[^>]*data-rrgbm="improving"/.test(out), 'the chosen mix marked');
  ok(/data-rrgbm="leading\+weakening\+lagging\+improving"[\s\S]*?<\/tr>/.exec(out)[0].includes('<td class="num">—</td>'), 'the equal weight not judged against itself');
  ok(out.includes('Green above the equal weight of the same lines (+8.0% a year') && out.includes('SPY: +10.0% a year'), 'what the colours compare with');
  ok(out.includes('the left half: below its trend'), 'a mix explained');
  // the chosen mix
  ok(out.includes('Improving, held 4 weeks: the growth of $1 after costs'), 'the chart\'s title');
  ok(out.includes('Equal weight of the group (dashed)') && out.includes('<svg'), 'the chart');
  ok(/Volatility \(a year\)<\/td><td class="num">18\.0%/.test(out), 'volatility unsigned');
  ok(/Turnover \(traded a year, both ways\)<\/td><td class="num">126%/.test(out), 'turnover: 0.005 a day × 252');
  ok(out.includes('Lines held (average) · time invested</td><td class="num">2.5 · 100%'), 'holdings');
  // bought now
  ok(out.includes('Buying Improving now: what history says about the next 4 weeks'), 'the expectation\'s title');
  ok(out.includes('<label>Mean over 4 weeks</label><strong>+0.96%</strong>'), 'the mean');
  ok(out.includes('95% interval +0.56% to +1.36%'), 'its interval');
  ok(out.includes('<label>Ahead of the equal weight</label><strong>53%</strong>') && out.includes('<label>Ahead of SPY</label><strong>50%</strong>'), 'ahead of the equal weight and SPY');
  ok(out.includes('In Improving at the close of 2026-10-30: 2 of 11 lines'), 'the lines now');
  ok(out.includes('<b>XLC</b><br><span class="muted">Communication Services sector (XLC)</span>') && out.includes('<b>XLI</b>') && !out.includes('<b>XLK</b>'), 'only the mix\'s lines listed');
  eq(R.rrgbStore.members.map((m) => m.line), ['XLC', 'XLI'], 'the lines\' CSV');
  eq(R.rrgbStore.members[0].quadrant, 'Improving', 'with the quadrant');
  ok(out.includes('Year by year') && out.includes('href="#rotation/research"'), 'the years and the research linked');
  ok(tips.length > months.length, 'tooltips for the chart, the dots and the years');
  // the CSV
  eq(exported.length, 15, 'every mix as CSV');
  const x = exported.find((r) => r.quadrants === 'Improving');
  eq([x.group, x.rrg, x.held, x.period, x.from], ['sectors', 'w', '4 weeks', 'all', '2016-01-04'], 'csv labels');
  ok(Math.abs(x.annual_return_after_costs - ((1 + G('improving')) * Math.pow(1 - 0.001 * 0.005, 252) - 1)) < 1e-12, 'csv after costs');
  ok(Math.abs(x.vs_equal_weight - (x.annual_return_after_costs - 0.08)) < 1e-12, 'csv against the equal weight');

  // a mix of two, no costs, ordered by the expected return
  Object.assign(state, { rrgbx: 'lagging+improving', rrgbcost: '0', rrgbs: 'exp' });
  out = R.rrgBacktestView();
  ok(out.includes('data-rrgbq="lagging" aria-pressed="true"') && out.includes('data-rrgbq="improving" aria-pressed="true"'), 'two on');
  ok(out.includes('held 4 weeks, before costs') && !out.includes('Costs a year at this rate'), 'no costs');
  ok(out.includes('In Lagging + Improving at the close of 2026-10-30: 3 of 11 lines'), 'three lines now');
  eq(R.rrgbStore.members.map((m) => m.line), ['XLK', 'XLC', 'XLI'], 'Lagging before Improving, then by RS-Momentum');
  eq([...out.matchAll(/data-rrgbm="([^"]+)"/g)].map((m) => m[1]).slice(0, 1)[0].includes('improving'), true, 'by the expected return: an Improving mix first');
  state.rrgbs = 'mix';
  eq([...R.rrgBacktestView().matchAll(/data-rrgbm="([^"]+)"/g)].map((m) => m[1]), MIXES, 'by the quadrants: the file\'s order');
  // the equal weight chosen: no "ahead of itself"
  state.rrgbx = 'leading+weakening+lagging+improving';
  ok(!R.rrgBacktestView().includes('<label>Ahead of the equal weight</label>'), 'the equal weight not judged against itself');

  // the toggles' clicks
  const buttons = [];
  global.document = { querySelectorAll: (sel) => (sel.includes('data-rrgbq') ? buttons : []), getElementById: () => null };
  state.rrgbx = 'improving';
  for (const q of QN) buttons.push({ dataset: { rrgbq: q } });
  R.bindRrgbt();
  buttons[2].onclick(); eq(state.rrgbx, 'lagging+improving', 'Lagging added, in the clock\'s order');
  buttons[0].onclick(); eq(state.rrgbx, 'leading+lagging+improving', 'Leading added');
  buttons[3].onclick(); buttons[2].onclick(); eq(state.rrgbx, 'leading', 'two taken away');
  buttons[0].onclick(); eq(state.rrgbx, 'leading', 'the last one stays');
  delete global.document;

  // a phone
  Object.assign(state, { rrgbx: 'improving', rrgbs: 'ret', rrgbcost: '10' });
  global.innerWidth = 390;
  out = R.rrgBacktestView();
  ok(out.includes('Lag + Imp</button>') && out.includes('>Beat equal weight<'), 'short names and columns');
  ok(out.includes('Improving</span><br><span class="muted">99.38 · 101.29</span>'), 'the RS values under the quadrant');
  ok(out.includes('viewBox="0 0 380 250"') && out.includes('viewBox="0 0 360 300"'), 'phone-sized charts');
  global.innerWidth = 1280;

  // the daily clock: its own holding periods
  Object.assign(state, { rrgbc: 'd', rrgbh: '13' });
  R.rrgBacktestView(); await tick(); await tick();                   // its file read
  out = R.rrgBacktestView();
  eq(state.rrgbh, '5', 'a holding period the clock has');
  ok(out.includes('held 5 trading days') && out.includes('Daily RRG (every close)'), 'the daily clock');
  // a group with one clock
  Object.assign(state, { rrgbg: 'world', rrgbc: 'd' });
  R.rrgBacktestView();
  eq(state.rrgbc, 'w', 'the clock it has');

  // ------------------------------------------------------------------ the Rotation tab's wiring
  const rot = fs.readFileSync(path.join(__dirname, '..', 'docs', 'rotation.js'), 'utf8');
  ok(/\['rrgbt','RRG portfolios — buy by quadrant/.test(rot), 'listed among the charts');
  ok(rot.includes("if(state.rview==='rrgbt')return out+(typeof rrgBacktestView==='function'?rrgBacktestView()"), 'drawn');
  ok(/'rrgbg','rrgbc','rrgbh','rrgbcost','rrgbp','rrgbs'\]\)if\(\$\(k\)\)/.test(rot) && rot.includes("state.rview==='rrgbt'&&typeof bindRrgbt==='function')bindRrgbt()"), 'bound');
  const html = fs.readFileSync(path.join(__dirname, '..', 'docs', 'index.html'), 'utf8');
  ok(html.indexOf('src="rrg-backtest.js"') > html.indexOf('src="momentum-backtest.js"'), 'loaded after the charts it uses');

  console.log(`rrg backtest view: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
