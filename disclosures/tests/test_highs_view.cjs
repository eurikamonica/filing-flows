// highs-view.js: one asset at its highs (headline, the state tiles, what followed the similar high days, the curves, its
// own runs), at a low and in a range, and the hub views (every asset in the regime, the research by state, the CSV
// rows), from small files with the shape app/highs.py and app/regimes.py write. No browser, no network.
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
// at a 52-week low and in a narrow range (app/regimes.py)
const lowA = { features: ['age', 'lows63', 'dist', 'dd_ath'], days: 250, runs: 120, assets: 115, next_low: km(71, 110), r10: km(12, 15), r20: km(40, 50), trough_days: { n: 250, p50: 5 }, fall: qs(-0.0507),
  lows_left: { n: 250, p50: 0 }, more_lows: 0.247, bounce: { n: 250, p10: 0.03, p25: 0.1849, p50: 0.3449, p75: 0.6874, p90: 0.9 }, bounce_open: 0.36, fwd21: qs(0.01), fwd63: qs(0.008), fwd126: qs(0.05), fwd252: qs(0.0068),
  fall63: qs(-0.1055), fall252: qs(-0.297), nearest: [{ key: 'FOXF', date: '2024-06-07', age: 643, dd_ath: -0.76, r10: 12, fall: -0.05, bounce: 0.2, fwd252: -0.38 }, { key: 'SAM', date: '2025-07-30', age: 1074, dd_ath: -0.84, r10: null, fall: null, bounce: null, fwd252: null, seen: 40 },
  { key: 'OLDL', date: '2009-03-02', age: 300, dd_ath: -0.9, r10: null, fall: null, bounce: null, fwd252: -0.2, seen: 252 }] };
const lowS = { dd_ath: -0.7608, ext200: -0.1478, ext_pct: 11.2, mom: -0.4443, mom_pct: 1.87, vol: 0.3022, vol_pct: 56.3, pe: 18.59, pe_pct: 16.1, volu: 1.41, mom_xs: 6.04, dist: 0.1417, lows63: 12, age: 1250, low: 33.87,
  low_date: '2026-10-02', since: '2021-11-05', date: '2026-10-30', close: 38.67 };
const lowBase = { days: 519412, runs: 9752, assets: 1717, next_low: km(19, 30), r10: km(18, 25), r20: km(47, 70), bounce: { p50: 0.294 }, fwd252: qs(0.12), fall252: qs(-0.18) };
const lowBucket = (lab, d, m) => ({ label: lab, days: d, runs: d / 50, assets: 40, next_low_median: m, next_low_p63: 0.6, r10_median: 18, r10_p63: 0.8, r20_median: m ? 47 : null, fall_median: -0.06, bounce_median: 0.29, fwd63: 0.02, fwd63_up: 0.55,
  fwd252: 0.12, fwd252_up: 0.63, fall252: -0.18 });
const lowLite = JSON.parse(JSON.stringify(lowA)); delete lowLite.nearest; for (const k of ['next_low', 'r10', 'r20']) delete lowLite[k].curve;
const LOWS_DOC = { schema: 'lows.v1', params: { grid: GRID }, note: 'History, not a forecast.', regimes: { '52w': { label: 'At a 52-week low', groups: { companies: { label: 'Companies', base: lowBase,
  buckets: { dd_ath: { title: 'Under its all-time high', rows: [lowBucket('80% or more', 40000, 25), lowBucket('under 20%', 90000, null), { label: 'empty', days: 0 }] } } } } } },
  now: { '52w': [{ key: 'NKE', name: 'NIKE, Inc.', kind: 'stock', group: 'companies', state: lowS, analogues: lowLite }, { key: 'PFE', name: 'Pfizer', kind: 'stock', group: 'companies', state: { ...lowS, dd_ath: -0.6, dist: 0.02 }, analogues: lowLite }] } };
const rngA = { features: ['width', 'width_pct', 'age', 'pos'], days: 250, runs: 140, assets: 120, breakout: km(10, 14), up_first: 0.55, within21: { up: 0.4, down: 0.33, n: 250 }, within63: { up: 0.52, down: 0.43, n: 250 },
  within126: { up: 0.54, down: 0.45, n: 250 }, within252: { up: 0.55, down: 0.45, n: 250 }, after21_up: qs(0.02), after63_up: qs(0.04), after21_down: qs(-0.01), after63_down: qs(0.012), failed_up: 0.23, failed_down: 0.32,
  fwd21: qs(0.01), fwd63: qs(0.032), fwd126: qs(0.05), fwd252: qs(0.09), rise63: qs(0.1), fall63: qs(-0.07),
  nearest: [{ key: 'KO', date: '2019-03-01', width: 0.05, age: 12, brk: 8, up: true, after63: 0.04, fwd252: 0.1 }, { key: 'PG', date: '2018-03-01', width: 0.06, age: 3, brk: null, up: null, after63: null, fwd252: null }] };
const rngS = { dd_ath: -0.02, ext200: 0.03, ext_pct: 50, mom: 0.1, mom_pct: 40, vol: 0.11, vol_pct: 4, pe: null, pe_pct: null, volu: 0.8, width: 0.052, width_pct: 6.5, pos: 0.72, age: 14, hi: 101.2, lo: 96.2, since: '2026-10-10',
  date: '2026-10-30', close: 99.8 };
const RANGES_DOC = { schema: 'ranges.v1', params: { grid: GRID }, note: 'History.', regimes: { narrow: { label: 'In a narrow range', groups: { companies: { label: 'Companies', base: { days: 257749, runs: 9000, assets: 1700, breakout: km(10, 14), up_first: 0.55,
  after63_up: qs(0.04), after63_down: qs(0.01), failed_up: 0.23, failed_down: 0.32 }, buckets: { width: { title: 'The range’s width', rows: [{ label: 'under 5%', days: 900, runs: 30, assets: 20, breakout_median: 8, breakout_p63: 0.9, up_first: 0.56,
  after63_up: 0.04, after63_down: 0.01, failed_up: 0.2, failed_down: 0.3, fwd252: 0.08, fwd252_up: 0.6 }, { label: 'none', days: 0 }] } } } } } },
  now: { narrow: [{ key: 'KO', name: 'Coca-Cola', kind: 'stock', group: 'companies', state: rngS, analogues: { days: 250, breakout: { median: 10, p: { 63: 0.9 } }, up_first: 0.55, after63_up: { p50: 0.04 }, after63_down: { p50: 0.01 }, fwd252: { p50: 0.09, up: 0.6 } } },
    { key: 'PG', name: 'P&G', kind: 'stock', group: 'companies', state: { ...rngS, width: 0.03, width_pct: 1 }, analogues: {} }] } };
const FILES = { 'h/data/research/paths/moves/a/AAPL.json': { key: 'AAPL', ticker: 'AAPL', name: 'Apple Inc.', kind: 'stock', highs: block },
  'h/data/research/paths/moves/a/NKE.json': { key: 'NKE', ticker: 'NKE', name: 'NIKE, Inc.', kind: 'stock', highs: { state: { ...state, high: false, dd: -0.76 }, own },
    lows: { '52w': { state: lowS, analogues: lowA }, '3m': { state: lowS, analogues: lowA } } },
  'h/data/research/paths/moves/a/KO.json': { key: 'KO', ticker: 'KO', name: 'Coca-Cola', kind: 'stock', highs: { state: { ...state, high: false, dd: -0.02 }, own }, ranges: { narrow: { state: rngS, analogues: rngA } } },
  'h/data/research/paths/moves/lows.json': LOWS_DOC, 'h/data/research/paths/moves/ranges.json': RANGES_DOC,
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
  // at a 52-week low: the asset's block (headline, tiles, the facts, the curves, the nearest days)
  const lb = HV.lowBlock({ state: lowS, analogues: lowA }, 'NKE (NIKE, Inc.)', 'stock', lowBase, 'companies', '52w', { params: { grid: GRID } });
  for (const want of ['closed at <b>$38.67</b>', '<b>+14.2%</b> above its 52-week low of $33.87 (Oct 2)', '76% under its all-time high', '12 new 52-week lows in the last 63 trading days', 'Nov 5, 2021 (1,250 trading days)',
    'median <b>71 trading days</b> away', 'median <b>12 trading days</b>', 'median <b>40 trading days</b>', '25% made another new 52-week low', 'median <b>+34.5%</b>', '−29.7%', '6th among companies', 'FOXF', 'not yet', 'none in a year', 'dashed: every low day of companies'])
    ok(lb.includes(want), `the low block lacks “${want}”`);
  clean(lb, 'the low block');
  ok((lb.match(/<polyline/g) || []).length === 5, 'three curves and two for the group');
  // in a narrow range
  const rb = HV.rangeBlock({ state: rngS, analogues: rngA }, 'KO (Coca-Cola)', 'stock', null, 'companies', 'narrow', { params: { grid: GRID } });
  for (const want of ['<b>in a narrow range</b>', 'between $96.20 and $101.20 (5.2% wide, the 7th percentile', 'in the top third', 'median <b>10 trading days</b>', '<b>55% up first</b>', '23% fell back', 'KO', 'not yet'])
    ok(rb.includes(want), `the range block lacks “${want}”`);
  clean(rb, 'the range block');
  // the hubs: the lists sorted, the CSV rows, the research by state
  const lo = { state: { mvhg: 'companies', mvhs: 'dist' }, pick: 'NKE' };
  const lh = HV.lowsHub(LOWS_DOC, '52w', lo);
  ok(lh.indexOf('data-hvk="PFE"') < lh.indexOf('data-hvk="NKE"'), 'the closest to its low first');
  ok(lh.includes('519,412 days at a 52-week low in 9,752 slides of 1,717 assets') && lh.includes('id="hv-one" data-k="NKE" data-r="52w"') && lh.includes('252+'), 'the lows hub');
  ok(lo.exported.length === 2 && lo.exported[1].analog_days_to_new_low === 71 && lo.exported[1].low_date === '2026-10-02', 'the lows CSV rows');
  clean(lh, 'the lows hub');
  const ro = { state: { mvhg: 'companies' }, pick: 'KO' };
  const rh = HV.rangesHub(RANGES_DOC, 'narrow', ro);
  ok(rh.indexOf('data-hvk="PG"') < rh.indexOf('data-hvk="KO"') && rh.includes('$96.20–$101.20') && rh.includes('id="hv-one" data-k="KO" data-r="narrow"'), 'the ranges hub, the narrowest first');
  ok(ro.exported.length === 2 && ro.exported[1].analog_up_first === 0.55, 'the ranges CSV rows');
  clean(rh, 'the ranges hub');
  ok(HV.lowsHub(LOWS_DOC, 'atl', { state: {} }).includes('None at an all-time low on the last day'), 'an empty regime reads well');
  // the asset's tab: every regime it is in, the lows first when it is not at its highs; a regime asked for
  await HV.render(el, { ticker: 'NKE', hub: 'h/' });
  ok(el.innerHTML.includes('At a 52-week low — how long until the next low') && el.innerHTML.includes('data-hvr="3m"') && el.innerHTML.includes('data-hvr="highs"') && el.innerHTML.includes('every low day of companies'), 'the asset at its lows');
  clean(el.innerHTML, 'the asset at its lows');
  await HV.render(el, { ticker: 'NKE', hub: 'h/', regime: 'highs' });
  ok(el.innerHTML.includes('At the highs —') && el.innerHTML.includes('not running at its highs now'), 'its highs on request');
  await HV.render(el, { ticker: 'KO', hub: 'h/' });
  ok(el.innerHTML.includes('In a narrow range — when it breaks out') && el.innerHTML.includes('dashed: every day in a narrow range of companies'), 'the asset in a range');
  await HV.render(el, { ticker: 'AAPL', hub: 'h/', regime: 'atl' });
  ok(el.innerHTML.includes('At the highs —') && !el.innerHTML.includes('data-hvr'), 'a regime it is not in: its highs, no chips');
  ok(HV.pickRegime({ highs: { state: { high: true } }, lows: { '3m': {} } }) === 'highs' && HV.pickRegime({ highs: { state: {} }, ranges: { wide: {} } }) === 'wide', 'the regime shown first');
  // the spread of what followed, the odds given each condition alone and together, the walk-forward test (app/regime_odds.py)
  const E = { fwd21: [-0.2, -0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15, 0.2], fwd63: [-0.4, -0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4], fwd252: [-0.5, -0.3, -0.15, 0, 0.15, 0.3, 0.5, 1.0],
    fall63: [-0.5, -0.4, -0.3, -0.2, -0.15, -0.1, -0.05, -0.02], bounce: [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0] };
  const cnt = (k, a) => [...E[k].map((_, i) => a + i), 4];
  const fan = { n: GRID.map(() => 250), p10: GRID.map((d) => -0.001 * d), p25: GRID.map((d) => -0.0004 * d), p50: GRID.map((d) => 0.0002 * d), p75: GRID.map((d) => 0.0008 * d), p90: GRID.map((d) => 0.0015 * d) };
  const dist = (a) => Object.fromEntries(Object.keys(E).map((k) => [k, cnt(k, a)]));
  const A2 = { ...lowA, fwd63: qs(0.03), dist: dist(10), fan };
  const cal = Array.from({ length: 10 }, (_, i) => [0.4 + 0.02 * i, 0.42 + 0.015 * i, 300]);
  const by = Array.from({ length: 30 }, (_, i) => [1995 + i, 150, (i % 3 - 1) * 0.01, 0.55]);
  const bt = { days: 4500, years: [1995, 2024], per_year: 150, pool_max: 40000, k: 250, spread: { years: 30, top: 0.031, bottom: 0.012, all: 0.02, diff: 0.019, t: 2.4, pos: 0.7 },
    outcomes: { up63: { n: 4500, rate: 0.56, skill: -0.012, auc: 0.53, verdict: 'none', calibration: cal, by_year: by }, low63: { n: 4400, rate: 0.62, skill: 0.041, auc: 0.66, verdict: 'useful', calibration: cal, by_year: by } } };
  const G2 = { base: { ...lowBase, fwd63: qs(0.02), r10: km(18, 25) }, dist: dist(20), fan: { ...fan, p50: GRID.map((d) => 0.0001 * d) }, backtest: bt,
    buckets: { pe_pct: { title: 'Trailing P/E, percentile of its own history', edges: [0, 1, 5, 20, 50, 80, 101], rows: [lowBucket('under 1 (lowest)', 9000, 20), lowBucket('1–5', 8000, 22), lowBucket('5–20', 30000, 19),
      { ...lowBucket('20–50', 60000, 18), fwd63_up: 0.62, fwd252_up: 0.64, next_low_p63: 0.5, r10_p63: 0.7 }, lowBucket('50–80', 50000, 18), lowBucket('80 or more', 20000, 17)] },
      dd_ath: { title: 'Under its all-time high', edges: [-1.01, -0.8, -0.6, -0.4, -0.2, 0.001], rows: [{ ...lowBucket('80% or more', 40000, 25), fwd63_up: 0.5 }, { ...lowBucket('60–80%', 30000, 22), fwd63_up: 0.4 }, lowBucket('40–60%', 20000, 21), lowBucket('20–40%', 20000, 20), lowBucket('under 20%', 90000, 19)] },
      volu: { title: 'Volume', rows: [] } } };
  const lb2 = HV.lowBlock({ state: lowS, analogues: A2 }, 'NKE (NIKE, Inc.)', 'stock', G2.base, 'companies', '52w', { params: { grid: GRID, edges: E, fan_grid: GRID }, group: G2 });
  clean(lb2, 'the low block with the new sections');
  ok(lb2.includes('The spread of what followed') && (lb2.match(/class="hv-chart hv-hist"/g) || []).length >= 5 + 2, 'the fan, five histograms and two calibration charts');
  ok(lb2.includes('dashed: the median of every day at a 52-week low') && lb2.includes('the middle half (25–75%)'), 'the fan with every day beside it');
  ok(lb2.includes('3 months on') && lb2.includes('median <span class="hv-up">+3%</span>, 70% up') && lb2.includes('under −40%: ') && lb2.includes('40% or more: '), 'a histogram titled with its median and share up, its open-ended bands');
  ok(lb2.includes('The odds given its conditions') && lb2.includes('All its conditions together') && lb2.includes('Every day at a 52-week low'), 'the conditional table: every day, all together, one at a time');
  ok(lb2.includes('Trailing P/E, percentile of its own history: <b>5–20</b>') && lb2.includes('(it: the 16th percentile)'), 'its own band of each condition (P/E at the 16th percentile)');
  ok(lb2.includes('Under its all-time high: <b>60–80%</b>') && lb2.includes('(it: −76%)'), 'a distance band: −76% falls in 60–80%');
  ok(!lb2.includes('Volume:'), 'a condition without bands is left out');
  ok(lb2.indexOf('Under its all-time high: <b>') < lb2.indexOf('Trailing P/E, percentile of its own history: <b>'), 'sorted by how much the condition moves the 3-month odds');
  ok(/\+\d+ pts<\/span>|−\d+ pts<\/span>/.test(lb2), 'the points against every day');
  ok(lb2.includes('Has it worked?') && lb2.includes('known before that year began') && lb2.includes('4,500 days in all') && lb2.includes('none: no better than the base rate') && lb2.includes('>useful<'), 'the walk-forward test, verdicts');
  ok(lb2.includes('−1.2%') && lb2.includes('+4.1%') && lb2.includes('t 2.4 over 30 years') && lb2.includes('before trading costs'), 'skills and the spread');
  ok(lb2.includes('Brier skill of the 3-month odds, year by year'), 'the skill by year');
  const gh = HV.groupOdds(G2, { grid: GRID, edges: E, fan_grid: GRID }, 'lows', 'day at a 52-week low', 'companies', ['fall63', 'bounce']);
  ok(gh.includes('The spread of what followed') && gh.includes('Has it worked?') && !gh.includes('dark ticks'), 'the hub: every day, no comparison');
  clean(gh, 'the hub odds');
  ok(HV.lowBlock({ state: lowS, analogues: lowA }, 'X', 'stock', lowBase, 'companies', '52w', { params: { grid: GRID } }).indexOf('Has it worked?') < 0, 'an older file: no new sections, no errors');
  ok(HV.histChart([1, 2], [0], null, 'x') .includes('<rect') && HV.histChart([0, 0], [0], null, 'x') === '' && HV.histChart([1, 2, 3], [0], null, 'x') === '', 'a histogram needs counts for every band');
  // where it stands: the close rebuilt from the daily log returns (basis points, dates from d0 by the gaps), the window,
  // the levels and the marks of each regime; the chart at its width; the clip of a range
  const rr = Array.from({ length: 400 }, (_, i) => (i < 300 ? 8 : -40));
  const tdoc = { key: 'TST', ticker: 'TST', name: 'Test Inc.', kind: 'stock', d0: '2025-01-02', gaps: '1'.repeat(400), r: rr, last: 50 };
  const P0 = HV.series(tdoc);
  ok(P0.days.length === 401 && P0.days[1] === '2025-01-03' && Math.abs(P0.close[400] - 50) < 1e-9 && Math.abs(P0.close[300] / P0.close[0] - Math.exp(0.24)) < 1e-9, 'the close from the returns, ending at the last close');
  ok(HV.series({ ...tdoc, r: [] }) === null && HV.series({ ...tdoc, last: null }) === null, 'no returns or no last close: none');
  const top = Math.max(...P0.close), hS = { high: true, run_start: P0.days[250], ath: top, ath_date: P0.days[300], dd: 50 / top - 1, close: 50, date: P0.days[400] };
  const Mh = HV.standModel(tdoc, 'highs', hS);
  ok(Mh.from === 401 - 253 && Mh.lv[0].v === top && Math.abs(Mh.lv[1].v - 0.9 * top) < 1e-9 && Mh.shade.i0 === 250, 'at the highs: a year, the high and 10% under it, the run shaded');
  ok(Mh.marks.length > 100 && Mh.marks.every((i) => i <= 300) && Mh.label[1] === 'from its high', 'the new all-time highs marked; the words for the last close');
  const Mlong = HV.standModel(tdoc, 'highs', { ...hS, run_start: P0.days[40] });
  ok(Mlong.from === 40 - 21, 'a long run: back to its start');
  const lS = { low: 50, low_date: P0.days[400], since: P0.days[300], dist: 0, lows63: 30, close: 50, date: P0.days[400] };
  const Ml = HV.standModel(tdoc, '52w', lS);
  ok(Ml.lv.map((l) => +l.v.toFixed(2)).join() === '50,55,60' && Ml.shade.i0 === 300 && Ml.marks.length > 10 && Ml.marks.every((i) => i > 300) && Ml.label.join(' ') === 'a new 52-week low', 'at a low: the low, 10% and 20% above, the slide, the new lows');
  const rS = { lo: 49, hi: 52, pos: 0.33, width: 0.06, since: P0.days[380], close: 50, date: P0.days[400] };
  const Mr = HV.standModel(tdoc, 'narrow', rS);
  ok(Mr.from === 401 - 127 && Mr.clip && Mr.shade.box.join() === '49,52' && Mr.lo < 49 && Mr.hi > 52, 'in a range: half a year, the range filling the middle, the earlier closes cut');
  const sh = HV.standChart(Mh), sn = HV.standChart(Mh, 360), sr = HV.standChart(Mr);
  ok(sh.includes('viewBox="0 0 720 280"') && sh.includes('all-time high $') && sh.includes('the pullback that ends a run') && (sh.match(/class="hv-hit"/g) || []).length === Math.ceil(253 / 5), 'the chart: the levels in words, a hover column a week');
  ok(sh.includes('$50.00') && sh.includes('from its high') && /<title>[A-Z][a-z]{2} \d+, 20\d\d: \$\d/.test(sh), 'the last close in words; a week in a tooltip');
  ok(sn.includes('viewBox="0 0 360 250"') && sn.includes('>high $') && !sn.includes('the pullback that ends a run'), 'on a phone: the chart at its width, the short words');
  ok(sr.includes('clipPath') && sr.includes('earlier closes off the scale: as high as $') && sr.includes('top $52.00'), 'a range: clipped, said so');
  clean(sh + sn + sr, 'the stand charts');
  ok(HV.standBlock(Mh).includes('<h3>Where it stands</h3>') && HV.standBlock(Mlong).includes('the last year') && HV.standBlock(Mr).includes('the last six months'), 'its heading and words');
  // the restyled charts: the median in the histogram, the median waits on the curves, the hover
  const hh = HV.histChart(dist(10).fwd63, E.fwd63, dist(20).fwd63, '3 months on', '', 'fwd63', 0.03);
  ok(hh.includes('median +3%') && /stroke-dasharray:4 3/.test(hh) && (hh.match(/<path d="M/g) || []).length >= 10 && hh.includes('of every day'), 'a histogram: the median dashed and said, rounded bars, every day outlined, its tooltips');
  const kk = HV.kmChart([{ label: 'no 10% pullback yet', curve: curve(80), col: 'red' }, { dash: true, label: 'no 10% pullback yet', curve: curve(60), col: 'red', who: 'companies' }], GRID);
  ok((kk.match(/<circle/g) || []).length === 1 && kk.includes('half the days by about 56 trading days') && kk.includes('63 trading days on (about 3 months)') && kk.includes('— every high day of companies'), 'the curves: the median wait marked, every week in a tooltip');
  // the picture: its panels, rows, title and line (the drawing itself needs a browser)
  const PA = { ...A, dist: { fwd21: dist(10).fwd21, fwd63: dist(10).fwd63, fwd252: dist(10).fwd252 }, fan };
  const PX = { doc: { key: 'AAPL', ticker: 'AAPL', name: 'Apple Inc.', kind: 'stock' }, reg: 'highs', kind: 'highs', gk: 'companies', S: state, A: PA, own, base, G: { dist: dist(20), fan }, params: { grid: GRID, edges: E, fan_grid: GRID }, M: Mh };
  ok(['now', 'odds', 'fan', 'fwd21', 'fwd63', 'fwd252', 'own'].every((k) => HV.canPic(PX, k)) && !HV.canPic(PX, 'mdd63') && !HV.canPic({ ...PX, M: null }, 'now'), 'the panels it can draw');
  ok(JSON.stringify(HV.picRows(PX, ['now', 'odds', 'fwd63', 'fwd252'])) === '[["now"],["odds"],["fwd63","fwd252"]]' && JSON.stringify(HV.picRows(PX, ['fwd21', 'own', 'fan', 'mdd63'])) === '[["fan"],["fwd21","own"]]', 'the wide panels alone, the rest two to a row; what it cannot draw left out');
  ok(HV.picTitle(PX) === 'AAPL 1.2% under its all-time high, 25 trading days into a run of highs' && HV.picTitle({ ...PX, S: { ...state, dd: 0 } }).startsWith('AAPL at an all-time high: 25 trading days into a run, 7 new highs'), 'the title');
  ok(HV.picSub(PX).includes('closed $344.63 on Oct 30, 2026') && HV.picSub(PX).includes('what followed the 250 most similar high days of companies (139 assets)'), 'the line under it');
  ok(HV.picTitle({ ...PX, reg: '52w', kind: 'lows', S: lowS }) === 'AAPL 14.2% above its 52-week low, 12 new lows in 63 days' && HV.picTitle({ ...PX, reg: 'narrow', kind: 'ranges', S: { width: 0.031, pos: 0.8 } }).includes('in a narrow range: 3.1% wide over 63 trading days, in the top third'), 'the title at a low and in a range');
  const pb = HV.pngBar(PX);
  ok(pb.includes('Picture to share (PNG):') && pb.includes('data-hvp="now" checked') && pb.includes('data-hvp="own"') && !pb.includes('data-hvp="own" checked') && !pb.includes('data-hvp="mdd63"') && pb.includes('Make the picture'), 'the bar: the panels it can draw, the default ones ticked');
  ok(HV.pngBar({ ...PX, A: null, M: null, own: null }) === '', 'nothing to draw: no bar');
  // valuation beside the price (app/ratios.py → doc.ratios): the weeks, the rolling band, the words, the table, the chart
  const wk = (d0, n, f) => Array.from({ length: n }, (_, i) => f(i));
  const N0 = 600, pe = wk('2015-01-02', N0, (i) => +(15 + 10 * Math.sin(i / 60) + (i > 560 ? 12 : 0)).toFixed(2)), ind = wk('2015-01-02', N0, (i) => (i < 30 ? null : 20));
  pe[200] = 400;                                            // a spike far past its usual range: off the top
  const RT = { as_of: '2026-07-31', w: { d0: '2015-01-02', n: N0, pe, pe_ind: ind, ps: wk('2015-01-02', N0, (i) => 2 + i / 300) },
    pe: { now: 37, date: '2026-07-31', from: '2015-01-02', days: 2900, hi: [400, '2018-11-02'], lo: [5.1, '2015-11-20'], q: [8, 12, 18, 24, 30], at_hi: false, at_lo: false, pct: 94.3, off_hi: -0.9075, y5: { from: '2021-08-02', q: [20, 26, 34], pct: 85.5, hi: [42, '2024-12-26'], lo: [20, '2023-01-05'] },
      split: [{ k: 'run', from: '2026-05-01', price: 0.2, per: 0.1, ratio: 0.0909 }, { k: '1y', from: '2025-07-31', price: 0.2276, per: 0.2024, ratio: 0.0209 }],
      ind: { level: 'industry group', key: 'SIC-357', name: 'Computer and office equipment', n: 24, mid: 26.7, p25: 21, p75: 33, rank: 66.7, rel: 1.39, rel_pct: 79.2, rel_mid: 1.04, rel_weeks: 500, top: [['CSCO', 30.8]] } },
    ps: { now: 3.99, date: '2026-07-31', from: '2015-01-02', days: 2900, hi: [3.99, '2026-07-31'], lo: [2, '2015-01-02'], q: [2.2, 2.5, 3, 3.5, 3.8], at_hi: true, at_lo: false, pct: 100, y5: { from: '2021-08-02', q: [3, 3.5, 3.9], pct: 100 } },
    more: { from: '2022-06-03', rows: [{ k: 'pb', label: 'P/B', now: 46.9, mid: 46, pct: 58.6, weeks: 232, peer: null }, { k: 'ev_ebitda', label: 'EV/EBITDA', now: 30.1, mid: 24.1, pct: 97, weeks: 232, peer: { mid: 16.6, p25: 8.9, p75: 27.4, n: 22, group: 'sic357' } }],
      peer_pe: { mid: 24.4, p25: 14.5, p75: 38.9, n: 24, group: 'sic357', own: 38.1 } } };
  const W0 = HV.rWeeks(RT);
  ok(W0.n === N0 && W0.date(0) === '2015-01-02' && W0.date(1) === '2015-01-09' && HV.rWeeks({}) === null, 'the weeks: Fridays from d0');
  const rbd = HV.rolling(Array.from({ length: 300 }, (_, i) => i));
  ok(rbd.lo[102] === null && rbd.lo[103] !== null && Math.abs(rbd.lo[299] - (40 + 0.1 * 259)) < 1e-9 && Math.abs(rbd.hi[299] - (40 + 0.9 * 259)) < 1e-9, 'the rolling band: two years at least, the 10–90% of the five years before');
  const vdoc = { ...tdoc, d0: '2015-01-02', gaps: '1'.repeat(2000), r: Array.from({ length: 2000 }, (_, i) => (i % 50 < 30 ? 15 : -10)), ratios: RT };
  const aw = HV.athWeeks(HV.series(vdoc), W0);
  ok(aw.size > 20 && [...aw].every((k) => k >= 0 && k < N0), 'the weeks with a new all-time high in price');
  const vw = HV.ratioWords(RT, { ...state, dd: -0.02 }, 'highs', 'highs');
  ok(vw.includes('<b>P/E 37.0</b> is <b>the 94th percentile</b> of the days since 2015 (the 86th percentile of the last five years), 91% under its own high of 400') && vw.includes('<b>P/S 3.99</b> is <b>at its all-time high</b>'), 'the words: where each ratio stands');
  ok(vw.includes('Since this run began (May 1, 2026) the price rose <b>20.0%</b>: EPS +10.0% and the P/E +9.1% — both played a part'), 'the price split into earnings and the multiple');
  ok(vw.includes('Against its industry group (Computer and office equipment, 24 other companies)') && vw.includes('median <b>1.04×</b> their median since 2015, <b>1.39×</b> now (the 79th percentile of its premium)'), 'against its industry');
  ok(HV.ratioWords({ pe: { now: null, why: 'loss' } }, state, 'highs', 'highs').includes('P/E none today: the last four quarters lost money'), 'no P/E today, said why');
  const vt = HV.ratioTable(RT);
  ok(vt.includes('its all-time high') && vt.includes('top 1%') && vt.includes('Its industry group: Computer and office equipment') && vt.includes('above 67% of them') && vt.includes('1.39× their median, usually 1.04×'), 'the table');
  const vc = HV.ratioChart(RT, 'pe', HV.series(vdoc), 900);
  ok(vc.includes('↑ high 400') && /weeks above [\d.]+ drawn at the edge \(as high as 400\)/.test(vc) && vc.includes('stroke-dasharray:6 4') && vc.includes('a new all-time high in price that week'), 'the chart: the spike off the top and said, the industry dashed, the new price highs');
  ok((vc.match(/class="hv-hit"/g) || []).length === Math.ceil(N0 / Math.ceil(N0 / 160)) && /<title>week of [A-Z][a-z]{2} \d+, 20\d\d: P\/E [\d.]+ · its industry group&#39;s median 20/.test(vc), 'a tooltip a column of weeks');
  ok(HV.ratioChart(RT, 'pe', null, 360).includes('viewBox="0 0 360 256"') && HV.ratioChart({ ...RT, w: { ...RT.w, pe: pe.slice(0, 10), n: 10 } }, 'pe', null, 900) === '', 'on a phone; too few weeks: none');
  const vb = HV.valBlock(vdoc, { ...state, dd: -0.02 }, 'highs', 'highs', 900);
  ok(vb.includes('<h3>Valuation beside the price</h3>') && vb.includes('data-hvv="pe"') && vb.includes('data-hvvbox="ps" hidden') && vb.includes('<h4>More multiples</h4>') && vb.includes('(22 · SIC 357)'), 'the section: the ratio chips, a chart each, more multiples');
  ok(HV.valBlock(tdoc, state, 'highs', 'highs', 900) === '', 'no ratios: no section');
  clean(vw + vt + vc + vb, 'the valuation section');
  const PXv = { ...PX, doc: { ...PX.doc, ...vdoc, kind: 'stock' } };
  ok(HV.canPic(PXv, 'pe') && HV.canPic(PXv, 'ps') && !HV.canPic(PX, 'pe') && JSON.stringify(HV.picRows(PXv, ['now', 'pe', 'ps', 'fwd63'])) === '[["now"],["pe"],["ps"],["fwd63"]]', 'the picture: a P/E and a P/S panel, each wide');
  // the key days and the news: the filings and headlines on the day they could move, how often the highs came on results
  const days = HV.series(vdoc).days, ev = (d, hm, items, head) => [d, hm, '8-K', items, head, '', items.includes('2.02') ? ['earnings'] : [], '0000-' + d];
  const resDays = [days[100], days[400], days[700], days[1000], days[1300], days[1600], days[1900]];
  const NEWS = { events: [...resDays.map((d) => ev(d, '08:00', '2.02,9.01', 'Results')), ev(days[1999], '17:00', '5.02', 'A new CFO')].reverse(),
    headlines: [[days[1990], days[1990], '10:00', 'Reuters', 'Test Inc. shares jump', 'https://example.com/a']], checked: [days[1990]] };
  const byN = HV.newsOn(NEWS, days);
  ok(byN.get(100).f.length === 1 && !byN.has(1999) && byN.get(1990).h[0][3] === 'Test Inc. shares jump' && byN.checked.has(days[1990]), 'the news on its trading day: after the close, the next (past the last day: none)');
  const est = HV.eventStats(HV.series(vdoc), byN, NEWS, 'highs', 'highs');
  ok(est && est.from === days[100] && est.n > 50 && est.eDays === 7 && est.on >= 0 && est.week >= est.on && Number.isFinite(est.base), 'how often the new highs came on a reporting day, from the first filing on file (newest first in the file)');
  const kds = HV.keyDays(HV.series(vdoc), { ath_date: days[1990], high: true, run_start: days[1950], dd: 0 }, 'highs', 'highs', { last: [{ start: days[1500], peak: days[1520], days: 20, pullback: -0.12 }] });
  ok(kds[0].what === 'the new all-time high' && kds.some((x) => x.what === "this run's first high") && kds.some((x) => x.what.startsWith("a run's peak (then −12.0%)")) && kds.every((x, i) => !i || kds[i - 1].i > x.i), 'the key days, newest first');
  const nb = HV.newsBlock({ ...vdoc, cik: 1 }, { ath_date: days[1990], high: true, run_start: days[1950], dd: 0 }, 'highs', 'highs', NEWS);
  ok(nb.includes('<h3>Its highs and the news</h3>') && nb.includes('Test Inc. shares jump') && nb.includes('new all-time highs</b> since') && nb.includes('came on a day it reported results'), 'the section: the stat, the days with their headlines');
  ok(HV.newsBlock({ ...vdoc, kind: 'etf' }, { ath_date: days[1990], dd: 0 }, 'highs', 'highs', null).includes('The headlines'), 'a fund: headlines only');
  clean(nb, 'the news section');
  // the lists: P/S beside P/E, sorted by it
  const DOC2 = JSON.parse(JSON.stringify(DOC));
  DOC2.now[0].state = { ...DOC2.now[0].state, ps: 10.2, ps_all: 98.4, ps_5y: 94.6, ps_ind: 88.9, ps_ath: true, pe_ind: 66.7 };
  const oPs = { state: { mvhs: 'ps_all' } };
  const hh2 = HV.hub(DOC2, oPs);
  ok(hh2.includes('<th>P/S</th>') && hh2.includes('10.2 <span class="hv-tag">own high</span>') && hh2.includes('98th own · 89th in industry') && oPs.exported[0].ps === 10.2 && oPs.exported[0].ps_pct_industry === 88.9 && oPs.exported[0].ps_at_own_high === true, 'the list: P/S, its percentiles, its own high; in the CSV');
  ok(hh2.indexOf('AAPL') < hh2.indexOf('HALO'), 'sorted by P/S against its own');
  console.log(`Highs view: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
