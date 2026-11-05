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
console.log(`ma-hybrid view: ${n} checks passed`);
