// ma-hybrid-view.js: Moving averages+ renders from published files (no browser, no network): the hybrid line's weights,
// the chart and its guidance marks, a company's cards and what its weights have been worth, the hub's tables and lists.
const assert = require('node:assert/strict');
const V = require('../docs/ma-hybrid-view.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const P = ['2016–2026', '2016–2018', '2019–2026'];
const S_ = (m, t) => ({ mean: m, t, pos: 0.6, weeks: 500 });
const per = (a, b, c) => Object.fromEntries(P.map((p, i) => [p, { ic: S_([a, b, c][i] / 10, 1.5), net: S_([a, b, c][i], 1.2), gross: S_([a, b, c][i] + 0.005, 1.4) }]));
const lines = {};
for (const h of ['13', '26']) { lines[h] = {}; for (const w of [0, 0.25, 0.5, 0.75, 1]) for (const g of [0, 0.05, 0.1]) lines[h][`${w}|${g}`] = per(0.0136 - 0.006 * w, -0.0103, 0.0234 - 0.01 * w); }
const d = {
  asof: '2026-10-30', test_from: 2016, now: 1880, weights: { w: [0, 0.25, 0.5, 0.75, 1], g: [0, 0.05, 0.1], default: [0.5, 0.05] },
  models: { ma: { name: 'Moving averages alone' }, ma_fund: { name: 'Moving averages + fundamentals' }, hybrid: { name: 'Moving averages + fundamentals + guidance' } },
  features: { tr40: 'Price vs its 40-week average', guid: 'Guidance raised / lowered' }, costs_bp: [[500e6, 5], [50e6, 15], [5e6, 40], [0, 100]],
  scores: {
    models: { 13: { ma: per(0.0152, -0.0095, 0.0251), ma_fund: per(0.0044, -0.023, 0.0155), hybrid: per(0.0058, -0.023, 0.0174) },
      26: { ma: per(0.0352, -0.0053, 0.0518), ma_fund: per(0.01, -0.0318, 0.0269), hybrid: per(0.0101, -0.0318, 0.027) } },
    rules: { 13: { above40: per(0.003, -0.0091, 0.0078), cross: per(0.0053, -0.0081, 0.0106) }, 26: { above40: per(0.0136, -0.0103, 0.0234), cross: per(0.015, -0.0118, 0.0259) } },
    lines, picks: { 13: { by_year: { 2025: { w: 0, g: 0, reading: 'trend' }, 2026: { w: 0, g: 0, reading: 'trend' } }, oos: { [P[0]]: { net: S_(0.0034, 0.5) } } },
      26: { by_year: { 2026: { w: 0, g: 0, reading: 'trend' } }, oos: { [P[0]]: { net: S_(0.0074, 0.6) } } } },
    guidance_events: { 4: { raised: { n: 1077, mean: 0.0032, t: 1.06, beat: 0.465 } }, 13: { raised: { n: 856, mean: 0.0231, t: 3.6, beat: 0.535 }, lowered: { n: 83, mean: 0.0239, t: 1.24, beat: 0.566 } }, years: ['2023', '2026'] },
    coefs: { 26: { hybrid: { 2026: { tr40: 0.0047, guid: 0.0545 } } } },
  },
  ledger: { 'ma:13': { resolved_weeks: 0, pending_weeks: 1 }, 'ma:26': { resolved_weeks: 0, pending_weeks: 1 } },
};
const N = 60, p = Array.from({ length: N }, (_, k) => 100 * Math.exp(0.004 * k + 0.05 * Math.sin(k / 5)));
const avg = (k, m) => (k + 1 < m ? null : p.slice(k + 1 - m, k + 1).reduce((a, b) => a + b, 0) / m);
const s = { id: 'XYZ', name: 'XYZ Corp', start: '2025-09-05', p, ma10: p.map((_, k) => avg(k, 10)), ma40: p.map((_, k) => avg(k, 40)),
  el: p.map((v, k) => (k < 45 ? null : v * 0.8)), g: p.map((_, k) => (k >= 50 && k < 63 ? 1 : null)), guidance: [['2026-08-19', 'raised'], ['2026-03-04', 'lowered']],
  now: { pe: 24.1, pe_med: 19.3, pct_ma: 0.62, pct_hybrid: 0.71 } };

// the hybrid line
const h0 = V._hybrid(s, 0, 0), h1 = V._hybrid(s, 1, 0), hg = V._hybrid(s, 0.5, 0.1);
const near = (a, b) => Math.abs(a / b - 1) < 1e-12;
ok(near(h0[50], s.ma40[50]) && near(h1[50], s.el[50]) && near(h1[42], s.ma40[42]) && h0[20] === null, 'w = 0 is the 40-week average, w = 1 the earnings line where there is one');
ok(Math.abs(hg[55] / Math.exp(0.5 * Math.log(s.ma40[55]) + 0.5 * Math.log(s.el[55])) - 1.1) < 1e-12, 'a raised guidance lifts the line by g');
// the chart
const svg = V._chart(s, 0.5, 0.05, 760);
ok(svg.startsWith('<svg') && (svg.match(/<path d="M/g) || []).length >= 5, 'five lines on the chart');
ok(/guidance raised/.test(svg) && /guidance lowered/.test(svg), 'the guidance releases are marked');
// one company
const c = V._company(s, d, s.now, 0.5, 0.05, 760, 'mh-t');
const bad = (h) => /undefined|NaN|Infinity|\[object/.test(h.replace(/<[^>]+>/g, ''));
ok(/vs 40-week average/.test(c) && /vs hybrid line/.test(c) && /P\/E 24\.1 vs its median 19\.3/.test(c) && /71%/.test(c), 'the cards');
ok(/Hybrid line \(50% \/ 5%\), 13 weeks/.test(c) && /40-week average alone, 26 weeks/.test(c) && /\+2\.34%/.test(c), 'what the weights have been worth');
ok(/26 weeks 0% \/ 0%, read as trend/.test(c), 'the pick made this year');
ok(!bad(c), 'no undefined / NaN in the company view');
// the hub
const H = V._hub(d);
ok(/The models, 26 weeks ahead/.test(H) && /Moving averages \+ fundamentals \+ guidance/.test(H) && /\+3\.52%/.test(H), 'the models');
ok(/Every weight on the grid, 26 weeks/.test(H) && /100% earnings line/.test(H) && /class="on"/.test(H), 'the grid, the best weight marked');
ok(/What followed each kind of guidance release \(2023–2026\)/.test(H) && /\+2\.31%/.test(H), 'the guidance releases');
ok(/Frozen record/.test(H) && !bad(H), 'the ledger, no undefined / NaN');
const L = V._list([{ id: 'AAA', name: 'A', close: 10, ma40: 8, el: 9, gap40: 0.22, gap_hybrid: 0.3, pct_hybrid: 0.9 }, { id: 'BBB', name: 'B', close: 10, ma40: 12, gap40: -0.18, gap_hybrid: -0.2, guid_last: ['2026-10-01', 'lowered'], pct_hybrid: 0.1 }], 0.5, 0.05);
ok(L.indexOf('AAA') < L.indexOf('Furthest below') && L.lastIndexOf('BBB') > L.indexOf('Furthest below') && /lowered/.test(L), 'the lists, furthest above first');
// the valuation, odds and MD&A numbers: shown, marked on the chart, the record's tests in the hub
const sv = Object.assign({}, s, { now: Object.assign({}, s.now, { val: { dcf_value: 150, mc_p10: 110, mc_p90: 190, mc_p_above: 0.58, p_implied: 0.31, kind: 'operating' },
  mdna: { filed: '2026-08-05', form: '10-Q', tone: 0.333, n: 9, positive: 4, negative: 1, hedged: 2 } }) });
const cv = V._company(sv, d, sv.now, 0.5, 0.05, 760, 'mh-v');
ok(/vs DCF value/.test(cv) && /\$150\.00/.test(cv) && /58%/.test(cv) && /MD&amp;A tone|MD&A tone/.test(cv) && /\+0\.33/.test(cv) && /too short to test them/.test(cv) && !bad(cv), 'the DCF, its odds and the MD&A tone on the cards');
ok(/DCF value this week: \$150\.00/.test(V._chart(sv, 0.5, 0.05, 760)), 'the DCF value marked on the chart');
const dv = Object.assign({}, d, { _valuationModels: { combined: { horizons: { '3m': { feature_ic: { dcf_gap: { ic_mean: 0.0023, origins: 15 }, pe_gap: { ic_mean: 0.0256, origins: 15 } } }, '12m': { feature_ic: { dcf_gap: { ic_mean: -0.0249, origins: 9 } } } } } },
  scores: Object.assign({}, d.scores, { mdna_events: { 4: { 'positive (above 0.2)': { n: 144, mean: 0.0118, t: 1.74 } }, 13: { 'positive (above 0.2)': { n: 98, mean: 0.0259, t: 1.75 } }, years: ['2024', '2026'], filings: 1006 } }) });
const Hv = V._hub(dv);
ok(/recorded each week, not yet in the line/.test(Hv) && /0\.002/.test(Hv) && /−0\.025|-0\.025/.test(Hv) && /\+2\.59%/.test(Hv) && /1,006 filings/.test(Hv), 'the record\'s own tests of valuation and MD&A in the hub');
const ld = V._lead(d);
ok(/\+3\.5% over 26 weeks/.test(ld) && /\+2\.3% \(t 3\.6, 856 releases\)/.test(ld), 'the lead says what the tests found');

// ------------------------------------------------------------------ the daily chart, any N-day average
const ND = 420, dp = Array.from({ length: ND }, (_, k) => 50 * Math.exp(0.0015 * k + 0.04 * Math.sin(k / 9)));
const gaps = Array.from({ length: ND - 1 }, (_, k) => ((k % 5) === 4 ? 3 : 1));                     // weekdays: Friday to Monday is 3 days
const dd = { id: 'XYZ', start: '2025-03-03', gap: gaps, p: dp, asof: null };
const D = V._dailyOf(dd);
ok(D.d.length === ND && D.d[0] === '2025-03-03' && D.d[5] === '2025-03-10', 'the dates come back from the start and the day gaps');
const a20 = V._sma(dp, 20);
ok(a20[18] === null && near(a20[19], dp.slice(0, 20).reduce((x, y) => x + y, 0) / 20) && near(a20[ND - 1], dp.slice(ND - 20).reduce((x, y) => x + y, 0) / 20), 'the N-day average');
const sd = Object.assign({}, s, { start: '2024-03-01' });                                         // the weekly lines cover the daily file
const h0d = V._dailyHybrid(D, sd, 200, 0, 0), a200 = V._sma(dp, 200);
ok(near(h0d[ND - 1], a200[ND - 1]) && h0d[198] === null, 'w = 0: the hybrid line is the base average');
const opt = { nd: [20, 50, 200], xx: 89, range: 252, base: 200, w: 0.5, g: 0.05 };
const dsvg = V._dailyChart(D, sd, opt, 760);
ok(dsvg.startsWith('<svg') && (dsvg.match(/<path d="M/g) || []).length === 6 && /stroke-dasharray:6 3/.test(dsvg) && />89</.test(dsvg) && />H</.test(dsvg), 'price, three averages, the XX-day (dashed) and H, each labelled');
const ui = V._ui; Object.assign(ui, { nd: [5, 20, 200], xx: 89, range: 126, base: 200 });
const cd = V._company(sd, dn(), sd.now, 0.5, 0.05, 760, 'mh-d', dd);
function dn() {
  const per3 = (a) => Object.fromEntries(['2017–2026', '2017–2018', '2019–2026'].map((p, i) => [p, { net: S_(a + 0.001 * i, -1.3 + i * 0.1), gross: S_(a, 1) }]));
  const daily = { from: '2017-10-13', companies: 1332, periods: ['2017–2026', '2017–2018', '2019–2026'], to: { 13: '2026-07-31', 26: '2026-05-01' } };
  const weekly = {};
  for (const h of ['13', '26']) {
    daily[h] = {}; weekly[h] = {};
    for (const N of [5, 10, 20, 30, 50, 60, 120, 200, 250]) {
      daily[h][`above:${N}`] = { periods: per3(N < 120 ? -0.009 : 0.0045), weekly_form: N === 5 ? null : S_(N < 120 ? -0.0088 : 0.0042, -1) };
      if (N > 5) weekly[h][`above:${N}`] = per(N < 120 ? -0.0038 : 0.0128, -0.01, 0.02);
    }
    for (const c of ['5/20', '10/60', '20/60', '50/200', '60/250']) { daily[h][`cross:${c}`] = { periods: per3(0.0066), weekly_form: c === '5/20' ? null : S_(0.006, 0.4) }; if (c !== '5/20') weekly[h][`cross:${c}`] = per(0.0144, -0.0119, 0.0252); }
  }
  const fund = (cagr, dd_) => Object.fromEntries(['1996–2026', '1996–2015', '2016–2026'].map((p) => [p, { cagr, vol: 0.15, maxdd: dd_, invested: 0.9, switches: 18, from: p.slice(0, 4) + '-01-05', years: 10 }]));
  const rules = { hold: 'Hold the fund', above40: 'Hold it while above its 40-week average, else cash', trend_unemployment: '40-week average, out only if unemployment is also above its 12-month average', trend_sahm: '40-week average, out only if the Sahm rule is also on' };
  const F = { start: '1996-04-26', rules: { hold: fund(0.102, -0.546), above40: fund(0.081, -0.351), trend_unemployment: fund(0.112, -0.318), trend_sahm: fund(0.118, -0.318) },
    now: { close: 755.7, ma40: 726.8, gap40: 0.039, in: { hold: true, above40: true, trend_unemployment: true, trend_sahm: false } } };
  const cell = (m, t) => ({ mean: m, t, pos: 0.6, weeks: 120 });
  const regimes = { period: '2016–2026', tests: 70, readings: { vix: { label: 'VIX', unit: '' }, credit: { label: 'Credit spread (Baa − 10y)', unit: 'pts' }, cpi: { label: 'CPI inflation, year on year', unit: '%' } },
    now: { vix: { value: 16.46, third: 1, cut: [15.5, 21.4], z: -0.4 }, credit: { value: 1.44, third: 0, cut: [1.88, 2.57], z: -1.2 }, cpi: { value: 3.72, third: 2, cut: [1.9, 2.9], z: 0.7 } } };
  for (const h of ['13', '26']) regimes[h] = { all: cell(0.0136, 1.0), vix: [cell(0.0209, 1.3), cell(0.0304, 1.6), cell(-0.0235, -0.7)], credit: [cell(0.0355, 2.5), null, cell(-0.048, -1.4)], cpi: [cell(-0.0315, -1.1), cell(0.0206, 1.2), cell(0.038, 2.2)] };
  return Object.assign({}, d, { daily: { companies: 1481, cross_recent: 10 },
    scores: Object.assign({}, d.scores, { ndays: { n: [5, 10, 20, 30, 50, 60, 120, 200, 250], crosses: [[5, 20], [10, 60], [20, 60], [50, 200], [60, 250]], weekly, daily },
      models: Object.assign({}, d.scores.models, { 26: Object.assign({}, d.scores.models['26'], { ma_macro: per(0.0486, 0.0023, 0.0676), ma_macro_09: per(0.032, -0.0007, 0.0454) }) }),
      net_by_year: { 26: { ma: { 2020: -0.046 }, ma_macro: { 2020: 0.0719 } } }, ic_by_year: { 26: { ma: { 2020: -0.05 }, ma_macro: { 2020: 0.111 } } },
      macro: { index: { rules, periods: ['1996–2026', '1996–2015', '2016–2026'], switch_bp: 5, sahm_on: 0.5, funds: { SPY: F, QQQ: Object.assign({}, F, { start: '1999-12-10' }) },
        now: { asof: '2026-10-30', unrate: 4.2, unrate12: 4.294, unemp_up: false, sahm3: 0, sahm_on: false, ff: 3.75 } }, regimes } }) });
}
const dz = dn();
ok(/Daily — any N-day average/.test(cd) && /data-mh-xx/.test(cd) && /89-day/.test(cd) && /not one of the lengths tested/.test(cd), 'the daily section, the XX-day line in its table');
ok(/<b style="color:#d4a017">5-day<\/b>/.test(cd) && /needs daily closes/.test(cd) && /50-day vs the 200-day/.test(cd), 'the 5-day line (daily closes only) and the 50/200 row');
ok(/50-day vs 200-day/.test(cd) && /(golden|death) cross of \d{4}-\d{2}-\d{2}|all through the file/.test(cd), 'the 50/200-day card');
ok(!bad(cd), 'no undefined / NaN with the daily chart');
const cz = V._company(sd, dz, sd.now, 0.5, 0.05, 760, 'mh-z', dd);
ok(/−0\.90% \(t −1\.3\)/.test(cz.replace(/<[^>]+>/g, '')) && /class="n cur"/.test(cz) && /Macro now/.test(cz) && /\+ Sahm rule: <b>out<\/b>/.test(cz) && !bad(cz), 'what each length paid, the macro now with today\'s third outlined');
const cn = V._company(sd, dz, sd.now, 0.5, 0.05, 760, 'mh-n', null);
ok(/No daily bars on file for this company/.test(cn) && /1,481/.test(cn) && !bad(cn), 'a company without daily bars');
// the hub's new tables
const Hz = V._hub(dz);
ok(/Daily averages, 26 weeks/.test(Hz) && /Weekly form 2016–26/.test(Hz) && /Daily 2017–26/.test(Hz) && /needs daily closes/.test(Hz) && /came within 0\.\d\d points/.test(Hz), 'the daily lengths, weekly form against daily closes');
ok(/SPY, from 1996-04-26/.test(Hz) && /\+ unemployment/.test(Hz) && /2016–2026 is their fair test/.test(Hz) && /11\.8%/.test(Hz), 'the fund rules');
ok(/each third of twelve readings, 26 weeks/.test(Hz) && /class="n cur"/.test(Hz) && /70 comparisons/.test(Hz), 'the macro thirds, today\'s outlined');
ok(/Moving averages × macro/.test(Hz) && /mostly 2020: \+7\.2% against −4\.6%/.test(Hz) && !bad(Hz), 'the macro model and where its lead came from');
const Lx = V._list([{ id: 'AAA', name: 'A', close: 10, ma40: 8, gap_hybrid: 0.1, x50_200: ['2026-11-03', 1, 0], d_close: 10.2, d50: 0.03, d200: 0.04 },
  { id: 'BBB', name: 'B', close: 10, ma40: 12, gap_hybrid: -0.2, x50_200: ['2026-10-01', -1, 25], d_close: 9, d50: -0.1, d200: -0.1 }], 0.5, 0.05, 10);
ok(/Golden crosses/.test(Lx) && /2026-11-03/.test(Lx) && !/2026-10-01/.test(Lx) && /Death crosses[^<]*\(0\)/.test(Lx), 'the latest crosses, only the recent ones');
const l2 = V._lead(dz);
ok(/Daily averages, on daily closes 2017–2026/.test(l2) && /holding made 10\.2% a year/.test(l2) && /nearly all of it in 2020/.test(l2), 'the lead sums up the daily lengths and the macro');

// ------------------------------------------------------------------ the distance to the line and the calendar
let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
const NW = 260, x = [0]; for (let k = 1; k < NW; k += 1) x.push(0.9 * x[k - 1] + 0.03 * gauss());      // a distance that halves in ~6.6 weeks
const s3 = { id: 'DST', name: 'Dist Co', start: '2021-11-05', p: x.map((v) => 100 * Math.exp(v)), ma10: x.map(() => 100), ma40: x.map(() => 100), el: x.map(() => null), g: x.map(() => null),
  guidance: [], now: { seas13: 0.021 }, season: { m: [0.03, -0.01, 0.0, 0.01, -0.02, 0.005, 0.01, -0.004, -0.03, 0.02, 0.012, 0.018], up: Array(12).fill(0.6), n: Array(12).fill(20), from: '2000' } };
const bk = (a) => Array.from({ length: 10 }, (_, j) => a(j));
const byH = { n: bk(() => 50000), d: bk((j) => -0.25 + 0.05 * j), back: bk((j) => (j < 2 || j > 7 ? 0.55 : 0.4)), q10: bk((j) => -0.3 + 0.04 * j), q50: bk((j) => -0.1 + 0.02 * j), q90: bk((j) => 0.1 + 0.04 * j),
  ret: bk((j) => 0.004 - 0.001 * j), ret_t: bk(() => -1.2), spread: S_(-0.006, -0.8) };
const dd3 = Object.assign({}, dz, { scores: Object.assign({}, dz.scores, {
  distance: { buckets: 10, window: 259, min_weeks: 104, period: '2016–2026', by: { '0|0': { 13: byH, 26: byH }, '0.5|0.05': { 13: byH, 26: byH } },
    regression: { '0.5|0.05': { 13: { dist_slope: 0.52, ret_slope: S_(-0.021, -1.4) }, 26: { dist_slope: 0.31, ret_slope: S_(-0.035, -1.1) } }, '0|0': { 13: { dist_slope: 0.58, random_walk_slope: 0.6, ret_slope: S_(-0.01, -0.5) } } } },
  calendar: { spy: { periods: ['1993–2026', '1993–2015', '2016–2026'], months: Object.fromEntries(['1993–2026', '1993–2015', '2016–2026'].map((p) => [p, Object.fromEntries(Array.from({ length: 12 }, (_, j) => [String(j + 1), { mean: 0.01 - 0.002 * (j % 4), up: 0.62, t: 1.4, n: 33 }]))])) },
    sell_in_may: { rule: { '1993–2026': { hold: { cagr: 0.102, maxdd: -0.52 }, nov_apr: { cagr: 0.071, maxdd: -0.31 } }, '2003–2026': { hold: { cagr: 0.108, maxdd: -0.52 }, nov_apr: { cagr: 0.069, maxdd: -0.29 } } },
      halves: { nov_apr: { mean: 0.061, up: 0.74, t: 3.1, n: 33 }, may_oct: { mean: 0.035, up: 0.66, t: 1.9, n: 33 } }, paper: 2002, cash: true },
    signals: { periods: ['2000–2026', '2016–2026'], by_month: { above40: Object.fromEntries(['2000–2026', '2016–2026'].map((p) => [p, Object.fromEntries(Array.from({ length: 12 }, (_, j) => [String(j + 1), S_(j === 0 ? -0.012 : 0.002, j === 0 ? -1.9 : 0.4)]))])),
      dip4: Object.fromEntries(['2000–2026', '2016–2026'].map((p) => [p, Object.fromEntries(Array.from({ length: 12 }, (_, j) => [String(j + 1), S_(0.003, 0.6)]))])) } } },
  seasonal: { 13: per(0.0042, 0.001, 0.006), 26: per(0.006, 0.002, 0.008) },
  models: Object.assign({}, dz.scores.models, { 26: Object.assign({}, dz.scores.models['26'], { ma_time: per(0.031, 0.002, 0.045) }) }) }) });
const cdx = V._company(s3, dd3, s3.now, 0, 0, 760, 'mh-x', null);
const hl = Number((cdx.match(/<span>Half-life<\/span><b>([\d.]+) weeks/) || [])[1]);
ok(hl > 4.5 && hl < 9.5, `the half-life from the weekly changes (ρ = 0.9: 6.6 weeks; got ${hl})`);
ok(/percentile<\/b>/.test(cdx) && /(\d+)(st|nd|rd|th) percentile/.test(cdx) && /10–90%: /.test(cdx) && /weeks? (above|below)/.test(cdx) && /its longest stretch \d+ weeks above, \d+ below/.test(cdx), 'the own percentile, range and stretches');
ok(/weeks at each distance, 259 weeks/.test(cdx) && (cdx.match(/<svg/g) || []).length >= 4, 'the distance chart and its histogram');
ok(/From its own \d+–\d+% band/.test(cdx) && /13 weeks later/.test(cdx) && /26 weeks later/.test(cdx) && /random walk/.test(cdx), 'what followed from the same band, and the random walk beside it');
ok(/Own season, next 13 weeks/.test(cdx) && /\+2\.1%/.test(cdx) && /This company against SPY by month, since 2000/.test(cdx) && /SPY by month, 1993–2026/.test(cdx) && !bad(cdx), 'the calendar section');
const Hd = V._hub(dd3);
ok(/Distance to the hybrid line/.test(Hd) && /90–100%/.test(Hd) && /… 26 weeks later/.test(Hd) && /The top band against the bottom one/.test(Hd), 'the hub\'s distance bands');
ok(/SPY in each month of the year/.test(Hd) && /Sell in May/.test(Hd) && /2003–2026/.test(Hd) && /by the month it is read in: the next 4 weeks/.test(Hd) && /a dip/.test(Hd) && /Heston & Sadka/.test(Hd) && !bad(Hd), 'the hub\'s calendar tables');
console.log(`ma-hybrid view: ${n} checks passed`);
