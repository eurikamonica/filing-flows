// highs-view.js: one asset at its highs (headline, the state tiles, what followed the similar high days, the curves, its
// own runs) and the hub view (every asset at its highs, the research by state, the CSV rows), from small files with the
// shape app/highs.py writes. No browser, no network.
const assert = require('node:assert/strict');
const path = require('node:path');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const GRID = Array.from({ length: 37 }, (_, i) => i * 7);
const curve = (k) => GRID.map((d) => Math.round(1000 * Math.exp(-d / k)) / 1000);
const km = (med, k) => ({ n: 250, events: 240, median: med, p: { 21: 0.4, 63: 0.74, 126: 0.91, 252: 0.99 }, curve: curve(k) });
const qs = (p50) => ({ n: 250, p10: p50 * 2.5, p25: p50 * 1.5, p50, p75: p50 * 0.7, p90: p50 * 0.4, mean: p50, up: 0.7 });
const A = { features: ['age', 'highs63', 'dd', 'pe_pct'], days: 250, runs: 190, assets: 139, t5: km(26, 40), t10: km(86, 120), t20: km(307, 400), run_left: km(57, 90),
  more_highs: 0.9, highs_left: { n: 250, p50: 12 }, gain_left: qs(0.11), pullback: qs(-0.168), pullback_open: 0.03, days_back: { n: 240, p25: 60, p50: 129, p75: 260, p90: 560 },
  fwd21: qs(0.012), fwd63: qs(0.043), fwd126: qs(0.06), fwd252: qs(0.121), mdd63: qs(-0.09), mdd252: qs(-0.17),
  nearest: [{ key: 'ROST', date: '2019-07-30', age: 29, highs63: 7, run_left: 141, t10: 147, pullback: -0.514, fwd252: -0.162 }, { key: 'DPZ', date: '2016-09-08', age: 34, highs63: 5, run_left: null, t10: null, pullback: null, fwd252: 0.262 }] };
const state = { date: '2026-10-30', close: 344.63, ath_date: '2026-10-29', ath: 348.9, dd: -0.0122, high: true, age: 25, highs63: 7, ext200: 0.1628, ext_pct: 65.9, mom: 0.2283, mom_pct: 50.3,
  vol: 0.1414, vol_pct: 3.2, pe: 39.57, pe_pct: 98.7, volu: 0.86, run_start: '2026-09-25', run_gain: 0.0105, run_highs: 7, mom_xs: 68.7 };
const own = { runs: 45, run_days: { n: 45, p25: 10, p50: 26, p75: 58 }, pullback: { n: 45, p25: -0.309, p50: -0.166, p75: -0.123 }, days_back: { n: 45, p50: 67 },
  last: [{ start: '2026-07-09', peak: '2026-07-28', days: 13, pullback: -0.111, days_back: 42 }, { start: '2026-05-06', peak: '2026-06-02', days: 18, pullback: -0.127, days_back: null }] };
const block = { state, own, analogues: A };
const base = { days: 1042406, runs: 23022, assets: 1600, t5: km(15, 25), t10: km(54, 80), t20: km(211, 300), run_left: km(33, 60), pullback: qs(-0.172) };
const bucket = (lab, d, t10) => ({ label: lab, days: d, runs: d / 10, assets: 50, t5_median: 15, t10_median: t10, t10_p63: 0.5, t10_p252: 0.9, run_left_median: 30, more_highs: 0.8, pullback_median: -0.17, fwd63: 0.02, fwd63_up: 0.6, fwd252: 0.11, fwd252_up: 0.68, mdd252: -0.18 });
const lite = JSON.parse(JSON.stringify(A)); delete lite.nearest; for (const k of ['t5', 't10', 't20', 'run_left']) delete lite[k].curve;
const DOC = { schema: 'highs.v1', params: { grid: GRID }, note: 'History, not a forecast.',
  groups: { companies: { label: 'Companies', from: '1962-01-02', base, buckets: { ext200: { title: 'Above the 200-day average', rows: [bucket('under 5%', 16677, 117), bucket('50% or more', 56862, 16), { label: 'empty', days: 0 }] } } },
    indices: { label: 'Indices', from: '1927-12-30', base, buckets: {} } },
  now: [{ key: 'AAPL', name: 'Apple Inc.', kind: 'stock', group: 'companies', state, analogues: lite }, { key: 'HALO', name: 'Halozyme', kind: 'stock', group: 'companies', state: { ...state, highs63: 24, dd: 0, pe: null, pe_pct: null }, analogues: lite },
    { key: 'IDX-GSPC', name: 'S&P 500 index', kind: 'index', group: 'indices', state, analogues: lite }] };
const FILES = { 'h/data/research/paths/moves/a/AAPL.json': { key: 'AAPL', ticker: 'AAPL', name: 'Apple Inc.', kind: 'stock', highs: block },
  'h/data/research/paths/moves/a/OLD.json': { key: 'OLD', ticker: 'OLD', name: 'Old Co', kind: 'stock' }, 'h/data/research/paths/moves/highs.json': DOC };
global.fetch = (u) => Promise.resolve(FILES[u] ? { ok: true, json: async () => JSON.parse(JSON.stringify(FILES[u])) } : { ok: false, status: 404 });
const HV = require(path.join(__dirname, '..', 'docs', 'highs-view.js'));
const clean = (h, m) => ok(!/NaN|undefined|Infinity|\[object/.test(h), m + ' shows NaN/undefined');

(async () => {
  // one asset: the headline, the tiles, the facts, the curves, the odds against the group, the nearest days, its own runs
  const h = HV.block(block, 'AAPL (Apple Inc.)', 'stock', base, 'companies', { params: { grid: GRID } });
  for (const want of ['closed at <b>$344.63</b>', '−1.2%</b> from its all-time high of $348.90 (Oct 29)', 'began Sep 25, 2026: 25 trading days, 7 new highs, +1.1% since',
    '66th percentile of its own history', '99th percentile of its own', '3rd percentile (calm)', '69th among companies', 'median <b>26 trading days</b>', 'median <b>86 trading days</b>',
    '90% made at least one more new high', 'median <b>−16.8%</b> from the run', '<polyline', 'dashed: every high day of companies', 'ROST', 'not yet', "45 completed runs", 'median <b>26 trading days</b> from first high'])
    ok(h.includes(want), `the asset block lacks “${want}”`);
  clean(h, 'the asset block');
  ok((h.match(/<polyline/g) || []).length === 5, 'three curves and two for the group');
  // not at its highs: the headline says so, no analogues
  const off = HV.block({ state: { ...state, high: false, dd: -0.2, run_start: null }, own }, 'X', 'stock', null, 'companies');
  ok(off.includes('not running at its highs now') && !off.includes('most similar high days'), 'an asset off its highs');
  clean(off, 'off its highs');
  // the hub: the group's summary, the list sorted, the CSV rows, the research by state
  const o = { state: { mvhg: 'companies', mvhs: 'highs63' }, pick: 'AAPL' };
  const hub = HV.hub(DOC, o);
  ok(hub.indexOf('data-hvk="HALO"') < hub.indexOf('data-hvk="AAPL"'), 'the most new highs first');
  ok(!hub.includes('data-hvk="IDX-GSPC"'), 'the other groups are not listed');
  ok(hub.includes('1,042,406 high days in 23,022 runs of 1,600 assets since 1962'), 'the group summary');
  ok(hub.includes('Above the 200-day average') && hub.includes('hv-bar') && hub.includes('id="hv-one" data-k="AAPL"'), 'the research table and the detail slot');
  ok(o.exported.length === 2 && o.exported[0].key === 'HALO' && o.exported[1].analog_days_to_10pct === 86 && o.exported[1].pe === 39.57, 'the CSV rows');
  clean(hub, 'the hub view');
  const o2 = { state: { mvhg: 'companies', mvhs: 'risk' } };
  HV.hub(DOC, o2);
  ok(o2.exported.length === 2, 'another sort');
  const o3 = { state: { mvhg: 'indices' } };
  ok(HV.hub(DOC, o3).includes('data-hvk="IDX-GSPC"') && o3.exported.length === 1, 'the indices');
  // render from the files: the asset's block with the group for comparison; an asset whose file has no block yet
  const el = { innerHTML: '' };
  await HV.render(el, { ticker: 'aapl', hub: 'h/' });
  ok(el.innerHTML.includes('At the highs') && el.innerHTML.includes('AAPL (Apple Inc.)') && el.innerHTML.includes('dashed: every high day of companies'), 'the company page view');
  clean(el.innerHTML, 'the company page view');
  await HV.render(el, { ticker: 'OLD', hub: 'h/' });
  ok(el.innerHTML.includes('built with the move odds'), 'no block yet');
  await HV.render(el, { ticker: 'NONE', hub: 'h/' });
  ok(el.innerHTML.includes('No daily history for NONE'), 'no file');
  console.log(`Highs view: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
