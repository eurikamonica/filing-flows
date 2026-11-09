// momentum-view.js: the factors pinned to the same numbers as tests/test_momentum.py (the browser and the build agree),
// no look-ahead, Yahoo's Monday bars moved to their Friday as app/momentum.py on_grid does, the monthly ranks put on the
// week grid from m0, and the view drawn from small files with the shapes the builds write. No network.
const assert = require('node:assert/strict');
const path = require('node:path');
let n = 0;
const near = (a, b, tol, m) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };
const ok = (v, m) => { assert.ok(v, m); n++; };
global.window = global;
const MV = require(path.join(__dirname, '..', 'docs', 'momentum-view.js'));

const C = Array.from({ length: 200 }, (_, t) => 100 * Math.exp(0.004 * t + 0.03 * Math.sin(t / 5)));
C[60] = null;
const B = Array.from({ length: 200 }, (_, t) => 100 * Math.exp(0.002 * t));
const S = Array.from({ length: 200 }, (_, t) => 100 * Math.exp(0.003 * t + 0.01 * Math.cos(t / 7)));
const PINNED = { m12_1: 0.15901493112293696, m6_1: 0.07662205144700773, m3_1: -0.01092402959835781, m1: 0.010383231119272196,
  hi52: -0.0006542252031591644, vol: 0.029017317337332402, ra12: 5.480001106730682, comp: 2.764996195310579,
  rel_b: 0.051570447038167266, rel_s: 0.009168154964303454, rs: 105.5379209548509, rcomp: 0.34307782922918933 };
const F = MV.factors(C, B, S);
for (const [k, v] of Object.entries(PINNED)) near(F[150][k], v, 1e-10 * Math.max(1, Math.abs(v)), 'pinned ' + k);
ok(F[60] === null, 'no close, no reading');
// a cash-like fund: the weekly volatility floor of 0.4% (tests/test_momentum.py test_volatility_floor: the same numbers)
const T = Array.from({ length: 120 }, (_, t) => 100 * Math.exp(0.0008 * t + 0.0002 * Math.sin(t)));
const fT = MV.factors(T)[100];
ok(fT.vol < 0.002, 'its own volatility is tiny');
near(fT.comp, 0.9958144998789363, 1e-10, 'the composite on the floor');
near(fT.ra12, 1.3697959597944076, 1e-10, 'the vol-scaled 12-1 on the floor');
ok(F[112].m12_1 === null, 'P[t−52] missing');
ok(F[100].comp != null, '50 of 52 weekly returns are enough');
ok(MV.factors(C)[150].rel_b === null, 'no benchmark, no relative momentum');
// no look-ahead: the series cut at 120 gives the same readings up to 119
const part = MV.factors(C.slice(0, 120), B.slice(0, 120), S.slice(0, 120));
for (let t = 0; t < 120; t++) {
  if (!part[t]) { ok(F[t] === null, 'same gaps ' + t); continue; }
  for (const k of Object.keys(part[t])) { if (part[t][k] == null) ok(F[t][k] == null, `look-ahead ${t} ${k}`); else near(part[t][k], F[t][k], 1e-9 * Math.max(1, Math.abs(F[t][k])), `look-ahead ${t} ${k}`); }
}
// month ends and the 10-month rule
const weeks = MV.grid({ start: '2024-01-05', weeks: '2024-03-29' });
const me = MV.monthEnds(weeks);
assert.deepEqual(me.map((i) => weeks[i]), ['2024-01-26', '2024-02-23']); n++;
const ts = MV.tenMonth(Array.from({ length: 60 }, (_, i) => i + 1), Array.from({ length: 13 }, (_, i) => 4 * i));
assert.deepEqual(Object.keys(ts).map(Number), [36, 40, 44, 48]); n++;
// the ETF price file: Monday bars and the week's last bar, as on_grid (tests/test_momentum.py: the same rows)
const grid = MV.grid({ start: '2024-01-05', weeks: '2024-03-01' }), wk = Object.fromEntries(grid.map((w, i) => [w, i]));
const day = (d) => Math.round((Date.parse(d) - Date.parse('2024-01-08')) / 864e5);
const px = { d0: '2024-01-08', t: ['2024-01-08', '2024-01-15', '2024-01-19', '2024-02-05', '2024-02-26'].map(day), a: [10, 11, 11.5, 12, 13] };
const g = MV.fromPx(px, wk, grid.length);
assert.deepEqual(g, [null, 10, 11.5, 11.5, 11.5, 12, 12, 12, 13]); n++;
// the ranks file: one row per month end from m0, carried through the weeks
const G2 = MV.grid({ start: '2024-01-05', weeks: '2024-06-28' });
const R = MV.rankLines({ fields: ['m12_1', 'm6_1', 'hi52', 'ra12', 'comp'], m0: '2024-02-23', rows: [[10, 20, 30, 40, 50], null, [11, 21, 31, 41, 60]], group: 'Equity', group_comp: [55, null, 65] }, G2, G2.length - 2);
const iFeb = G2.indexOf('2024-02-23'), iApr = G2.indexOf('2024-04-26');
ok(R.lines.comp[iFeb] === 50 && R.lines.comp[iFeb + 1] === 50 && R.lines.comp[iApr] === 60, 'monthly ranks on the week grid');
ok(R.lines.comp[iFeb - 1] === null, 'nothing before m0');
ok(R.last.comp === 60 && R.lastGroup === 65 && R.month === '2024-04', 'the latest month (from m0 and the row count)');
ok(MV.rankLines({ fields: ['comp'], m0: '1999-01-29', rows: [[1]] }, G2, 10) === null, 'an m0 off the grid: no lines');
// the chart
const svg = MV.lineChart([{ name: 'a', values: F.map((f) => (f ? f.comp : null)), color: '#000' }], Array.from({ length: 200 }, (_, i) => new Date(Date.UTC(2020, 0, 3) + 7 * i * 864e5).toISOString().slice(0, 10)), 52, 199, { fmt: 'sigma', zero: true });
ok(svg.startsWith('<svg') && svg.includes('σ'), 'a σ chart');

// the view, end to end, from files with the builds' shapes (rotation history and the ETF build)
(async () => {
  const start = '2018-01-05', N = 300;
  const W = Array.from({ length: N }, (_, i) => new Date(Date.parse(start) + 7 * i * 864e5).toISOString().slice(0, 10));
  const close = (mu, a) => Array.from({ length: N }, (_, t) => +(100 * Math.exp(mu * t + a * Math.sin(t / 6))).toFixed(4));
  const rrg = { start, weeks: W[N - 1], benchmark: 'SPY', bench: { id: 'SPY', start, c: close(0.002, 0.01) },
    series: [{ id: 'XLK', name: 'Technology (XLK)', group: 'sector-etf', sector: 'technology', start, c: close(0.003, 0.02) },
      { id: 's:technology', name: 'Technology · site companies', group: 'site-sector', sector: 'technology', start, c: close(0.0035, 0.025) }] };
  const t = { t: 'AAA', n: 'Alpha Inc.', s: 'technology', start: W[20], c: close(0.004, 0.03).slice(20) };
  const meAll = MV.monthEnds(W);
  const ranks = { v: 1, t: 'AAA', universe: 'momentum', n: 1500, fields: ['m12_1', 'm6_1', 'hi52', 'ra12', 'comp'], m0: W[meAll[20]], rows: meAll.slice(20).map((_, j) => [50 + (j % 40), 40, 60, 55, 70 + (j % 25)]) };
  const etfRanks = { v: 1, t: 'ZZZ', universe: 'momentum', n: 3800, fields: ranks.fields, m0: W[meAll[30]], rows: meAll.slice(30).map(() => [80, 70, 90, 85, 88]), group: 'Equity', group_comp: meAll.slice(30).map(() => 91) };
  const d0 = Date.parse('2019-01-07');
  const pxZ = { symbol: 'ZZZ', name: 'Zed Momentum ETF', d0: '2019-01-07', t: Array.from({ length: 200 }, (_, i) => 7 * i), a: close(0.005, 0.04).slice(0, 200), c: [] };
  const files = { 'h/rrg.json': rrg, 'h/t/AAA.json': t, 'h/momentum/AAA.json': ranks, 'data/etf/px/ZZZ.json': pxZ, 'data/etf/momentum/ZZZ.json': etfRanks };
  const asked = [];
  global.fetch = async (u) => { asked.push(u); return files[u] ? { ok: true, json: async () => JSON.parse(JSON.stringify(files[u])) } : { ok: false, status: 404, json: async () => ({}) }; };
  const el = { innerHTML: '', isConnected: true, querySelectorAll: () => [] };
  global.document = { head: { appendChild() {} }, createElement: () => ({}) };
  await MV.render(el, { ticker: 'AAA', hub: '', base: 'h/' });
  ok(el.innerHTML.includes('Momentum factors: AAA') && el.innerHTML.includes('Alpha Inc.'), 'a company');
  ok(el.innerHTML.includes('of 1500 companies') && el.innerHTML.includes('Relative 12-1 vs SPY') && el.innerHTML.includes('vs XLK'), 'ranks, SPY and the sector ETF');
  ok(el.innerHTML.includes('Composite momentum rank') && el.innerHTML.includes('Relative composite'), 'the composite and the relative composite');
  ok((el.innerHTML.match(/<svg/g) || []).length >= 6, 'six charts');
  const e2 = { innerHTML: '', isConnected: true, querySelectorAll: () => [] };
  await MV.render(e2, { ticker: 'ZZZ', hub: '', base: 'h/' });
  ok(e2.innerHTML.includes('Zed Momentum ETF') && e2.innerHTML.includes('an ETF') && e2.innerHTML.includes('of 3800 ETFs') && e2.innerHTML.includes('91st inside Equity'), 'an ETF from its price file, ranked inside its class');
  const e3 = { innerHTML: '', isConnected: true, querySelectorAll: () => [] };
  await MV.render(e3, { ticker: 'XLK', hub: '', base: 'h/' });
  ok(e3.innerHTML.includes('Technology (XLK)') && e3.innerHTML.includes('not ranked'), 'an ETF of rrg.json without a ranks file');
  const e4 = { innerHTML: '', isConnected: true, querySelectorAll: () => [] };
  await MV.render(e4, { ticker: 'NOPE', hub: '', base: 'h/' });
  ok(e4.innerHTML.includes('no weekly closes for NOPE'), 'an unknown ticker says so');
  // the ranks are asked where the kind keeps them: a company's with the rotation history, an ETF's with the ETF build
  ok(asked.includes('h/momentum/AAA.json') && !asked.includes('data/etf/momentum/AAA.json'), 'a company: the companies\' ranks only');
  ok(asked.includes('data/etf/momentum/ZZZ.json') && !asked.includes('h/momentum/ZZZ.json') && asked.includes('data/etf/momentum/XLK.json'), 'an ETF: the ETFs\' ranks only');
  // a sector index of the site's companies (rrg.json s:<sector>): its name, no ranks asked
  const e5 = { innerHTML: '', isConnected: true, querySelectorAll: () => [] };
  const before = asked.length;
  await MV.render(e5, { ticker: 's:technology', hub: '', base: 'h/' });
  ok(e5.innerHTML.includes('Momentum factors: Technology · site companies') && e5.innerHTML.includes('an index of the site') && e5.innerHTML.includes('Technology · site companies ÷ SPY'), 'a site index by its name');
  ok(!asked.slice(before).some((u) => /momentum\//.test(u)) && e5.innerHTML.includes('an index is not ranked'), 'an index: no ranks asked');
  console.log(`${n} momentum view checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
