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
  console.log(`Highs view: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
