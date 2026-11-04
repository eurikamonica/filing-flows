// rrg-hybrid.js: the Hybrid RRG view renders from a published file (the hub's helpers stubbed; no browser, no network):
// the chart in both modes, the tables, the scores against the classic RRG and the descriptive findings.
const assert = require('node:assert/strict');
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
global.table = (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
const V = require('../docs/rrg-hybrid.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const row = (id, x, y, e13, vol) => ({ id, name: id + ' fund', group: 'sector-etf', close: 100, classic: [100.5, 99.2], hybrid: [x, y], volume_x: vol, cost_bp: 5,
  h1: { rel: 0.001, p: 0.51 }, h4: { rel: 0.004, p: 0.52 }, h13: { rel: e13, p: 0.55, lo: -0.08, hi: 0.1, price: 103, price_lo: 94.2, price_hi: 112.1 },
  mix13: { rrg: 0.001, momentum: 0.006, volume: -0.002 },
  tail: { hybrid: [[99, 99.5, 100.4], [98.8, 99.9, 100.6]], classic: [[100.1, 100.3, 100.5], [100.2, 99.8, 99.2]] } });
const sc = (h) => ({ h, ic: { hybrid: { ic: 0.0665, t: 3.15, pos: 0.7, weeks: 59 }, classic: { ic: 0.0279, t: 2.31 }, momentum_12_1: { ic: 0.027, t: 1.7 }, rrg: { ic: 0.025, t: 1 }, momentum: { ic: 0.065, t: 3 }, volume: { ic: 0.025, t: 2 } },
  ic_by_year: { 2019: [0.1, 0.02], 2020: [-0.16, 0.04], 2021: [0.24, 0.01] }, best_minus_worst: { mean: 0.0485, t: 3.7, per_year: 0.19, hit: 0.68, worst: -0.2, periods: 59 },
  best_minus_worst_classic: { mean: 0.0126 }, top_fifth_vs_spy: { mean: -0.0116, share_beating: 0.473 }, deciles: Array.from({ length: 10 }, (_, k) => ({ decile: k + 1, rel: -0.09 + k * 0.009, beat: 0.41 + k * 0.007 })),
  beat_spy: { brier_skill: 0.0028, base_rate: 0.459, calibration: [] }, range80: 0.797 });
const d = {
  asof: '2026-10-30', volume_week: '2026-10-23', test_from: 2012, costs_bp: [[500e6, 5], [50e6, 15], [5e6, 40], [0, 100]],
  panels: {
    funds: { lines: 29, now: 3, rows: [row('XLK', 101.2, 100.8, 0.012, 1.1), row('XLE', 98.9, 101.1, -0.01, 2.4), row('XLU', 99.5, 98.7, 0.002, 0.5)],
      scores: { 13: sc(13) }, weights_now: { 13: { rrg: 0.21, momentum: 0.23, volume: 0.2 } }, spy_drift_week: 0.0025, describe: [] },
    companies: { lines: 3400, now: 2154, rows: [row('NVDA', 102, 101, 0.03, 1.0)], scores: { 13: sc(13) }, weights_now: { 13: { rrg: 0.2, momentum: 1.1, volume: 0.97 } },
      describe: [{ kind: 'quadrant', group: 'Improving', h: 13, rel: -0.0105, t: -3.07, weeks: 59, share_of_weeks: 0.196 }, { kind: 'quadrant', group: 'Weakening', h: 13, rel: 0.0118, t: 3.61, share_of_weeks: 0.19 },
        { kind: 'volume', group: 'Volume ≥ 2× its 13-week average', h: 4, rel: -0.0154, t: -5.5, share_of_weeks: 0.061 }, { kind: 'quadrant_volume', group: 'Improving on ≥ 2× volume', h: 13, rel: -0.0674, t: -4.8, share_of_weeks: 0.0075 }] },
  },
  ledger: { 'companies:13': { resolved_weeks: 0, pending_weeks: 1 } },
};
V._state.d = d;
const bad = (h) => /undefined|NaN|\[object/.test(h.replace(/<[^>]+>/g, ''));
const h = V._html();
ok(/<svg/.test(h) && /XLK/.test(h) && /Leading/.test(h) && /Improving/.test(h), 'the hybrid chart and its quadrants');
ok(/0\.028/.test(h) && /0\.067/.test(h), 'the classic and hybrid rank correlations in the lead text');
ok(/stroke="#111"/.test(h), 'a fund with a volume spike is ringed');
ok(/Volume, week ending 2026-10-23/.test(h) && /volume in the week ending 2026-10-23: 2\.4×/.test(h), 'the volume column and the ring name their week');
ok(/\$94\.20 – \$112\.10/.test(h), 'the 13-week price range');
ok(/Best − worst fifth/.test(h) && /beat SPY/.test(h), 'the portfolio scores');
ok(/Improving on ≥ 2× volume/.test(h) && /−6\.74%/.test(h), 'the volume findings');
ok(/Frozen record/.test(h), 'the ledger');
ok(!bad(h), 'no undefined / NaN');
V._state.mode = 'classic';
const c = V._html();
ok(/JdK RS-Ratio/.test(c) && !bad(c), 'the classic chart');
ok(V._chart([], 'hybrid').startsWith('<svg'), 'an empty panel still draws its axes');
console.log(`rrg-hybrid view: ${n} checks passed`);
