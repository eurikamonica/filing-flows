// market-models.js: every view of the Market models tab renders from a market-models file (the hub's helpers stubbed;
// no browser, no network) and says plainly when a model has no demonstrated skill.
const assert = require('node:assert/strict');
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
global.kpi = (l, v, c = '') => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.table = (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.state = {};
const V = require('../docs/market-models.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const rot = (ids) => ({
  rows: ids.map((id, i) => ({ id, name: id + ' fund', h4: { rel: 0, rel_model: 0.001, p_beat: 0.49, p_lead: 0.2 }, h13: { rel: 0, rel_model: -0.004 * i, p_beat: 0.49, p_lead: 1 / ids.length },
    signals: { mom52_4: 0.05, mom13: -0.01, rev4: 0.002, vol: 0.1 }, ranked: { mom52_4: 0.5 } })),
  scores: { 4: { h: 4, origins: 300, ic: -0.01, ic_t: -0.3, ic_momentum: -0.05, brier_skill: -0.0002, brier_skill_raw: -0.06, best_minus_worst: -0.003, best_minus_worst_momentum: -0.005, beta_now: 0 },
    13: { h: 13, origins: 95, ic: 0.022, ic_t: 0.39, ic_momentum: -0.007, brier_skill: -0.0001, brier_skill_raw: -0.12, best_minus_worst: 0.003, best_minus_worst_momentum: -0.004, beta_now: 0 } },
});
const d = {
  generated_at: '2026-11-02T22:45:00+00:00', asof: '2026-10-30', first_test: 2003,
  vol: { vix: 16.5, vix_term: 0.92, assets: [{ id: 'SPY', h4: { vol: 0.134, hist_vol: 0.104, range: [-0.04, 0.045], uses_implied: true }, h13: { vol: 0.142, range: [-0.058, 0.094] }, implied_vol: 0.165, vrp: 0.0119 },
    { id: 'QQQ', h4: { vol: 0.227, hist_vol: 0.2, range: [-0.07, 0.077] }, h13: { vol: 0.225, range: [-0.11, 0.16] } }],
  scores: [{ id: 'SPY', h: 4, gain_vs_hist_used: 0.39, coverage80: 0.82 }, { id: 'SPY', h: 13, gain_vs_hist_used: 0.4, coverage80: 0.83 }, { id: 'QQQ', h: 4, gain_vs_hist_used: 0.09, coverage80: 0.82 }] },
  regime: { now: [0.99, 0.01, 0], p_down10_13w: 0.063, base_down10_13w: 0.063, score: { down10_13w_brier_skill: -0.0007, down10_13w_brier_skill_raw: -0.238, independent: 94 },
    states: [{ name: 'Calm', ret_year: 0.19, vol_year: 0.096, vix: 13.9, credit_4w: -0.025, stay: 0.97, weeks: 36 }, { name: 'Normal', ret_year: 0.085, vol_year: 0.168, vix: 21.5, credit_4w: 0, stay: 0.94, weeks: 16 },
      { name: 'Stressed', ret_year: -0.22, vol_year: 0.34, vix: 34, credit_4w: 0.107, stay: 0.9, weeks: 10 }],
    by_state: [{ name: 'Calm', weeks: 595, spy_13w: 0.02, spy_13w_vol: 0.14, down10_share: 0.037 }, { name: 'Stressed', weeks: 191, spy_13w: 0.03, spy_13w_vol: 0.27, down10_share: 0.12 }],
    leaders_by_state: [{ id: 'QQQ', kind: 'index', Calm: 0.01, Normal: 0.005, Stressed: 0.015 }],
    history: { start: '2000-01-07', p: Array.from({ length: 60 }, (_, i) => (i < 30 ? [0.8, 0.15, 0.05] : [0.1, 0.2, 0.7])) } },
  indices: { ...rot(['SPY', 'QQQ', 'DIA', 'MDY', 'IWM', 'IJR']), conditions: { credit_13w: -0.2, curve: 0.83, vrp: 0.012, stress: 0 },
    fundamentals: { IJR: { members: 601, covered: 504, earnings_yield: 0.027, revenue_growth: 0.077, earnings_growth: 0.22, loss_share: 0.18 }, IWM: { members: 1831, covered: 1332, earnings_yield: 0.006, revenue_growth: 0.095, earnings_growth: null, loss_share: 0.41 } } },
  sectors: rot(['XLK', 'XLE', 'XLU']),
  spreads: [{ id: 'IWM/SPY', name: 'Small caps vs the S&P 500', kind: 'log', now: -0.99, z_3y: -0.53, history: { start: '2016-11-04', x: Array.from({ length: 50 }, (_, i) => -0.8 - i / 250) },
    h4: { chosen: 'ou', forecast: 0.0004, range: [-0.03, 0.04] }, h13: { chosen: 'ou', forecast: 0, range: [-0.04, 0.07], half_life_weeks: 189, r2_ou: -0.04, r2_trend: -0.05, coverage80: 0.76 } },
  { id: 'credit', name: 'Credit spread', kind: 'level', now: 1.44, z_3y: -1.4, history: { start: '2016-11-04', x: [1, 2, null, 1.5, 1.4, 1.3, 1.2, 1.3, 1.4, 1.5, 1.44] }, h4: { chosen: 'trend' }, h13: { chosen: 'rw', forecast: 0, range: [-0.33, 0.38], coverage80: 0.84 } }],
  market: { predictors: [{ id: 'vrp', name: 'Variance risk premium', now: 0.012 }, { id: 'curve', name: 'Yield curve', now: 0.83 }],
    h: { 13: { score: { r2_published: -0.037, r2_combination: -0.037, r2_combination_ct: 0.002, up_brier_skill: -0.037, coverage80: 0.81, independent: 94, r2_each: { vrp: -0.22, curve: -0.016 } },
      now: { excess: 0.019, combination: 0.018, p_up: 0.72, base_up: 0.72, range: [-0.055, 0.08], history_mean: 0.019, each: { vrp: 0.017, curve: 0.022 } } },
    52: { score: { r2_published: 0, independent: 22 }, now: { excess: 0.075, p_up: 0.79, base_up: 0.79, range: [-0.12, 0.2], history_mean: 0.075, each: {} } } } },
  ledger: { vol: { resolved: 0, pending: 40 }, index: { resolved: 12, pending: 10, skill: 0.004 }, sector: { resolved: 0, pending: 22 }, spread: { resolved: 0, pending: 18 }, market: { resolved: 0, pending: 2 }, regime: { resolved: 0, pending: 1 } },
};
const bad = (h) => /undefined|NaN|\[object/.test(h.replace(/<[^>]+>/g, ''));
const o = V.mmOverview(d);
ok(/Calm 99%/.test(o) && /13\.4%/.test(o), 'the headline numbers');
ok(/No demonstrated skill/.test(o) && /hardly predictable/.test(o), 'honest verdicts');
const v = V.mmVol(d);
ok(/SPY/.test(v) && /\+ implied/.test(v) && /\+119 %²/.test(v) && /\+39%/.test(v), 'the volatility table');
const i = V.mmIndices(d);
ok(/IJR/.test(i) && /S&amp;P SmallCap 600|SmallCap 600/.test(i) && /41%/.test(i), 'the six indices and their members');
ok(/Trust now/.test(i), 'how far the model is used');
const g = V.mmRegime(d);
ok(/<svg/.test(g) && /Stressed/.test(g) && /calm going into 2008/.test(g), 'the regime chart and its record');
const s = V.mmSpreads(d);
ok(/mean reversion/.test(s) && /random walk/.test(s) && /<svg/.test(s), 'the spreads');
const m = V.mmMarket(d);
ok(/Goyal and Welch/.test(m) && /72%/.test(m), 'the market direction');
const r = V.mmRecord(d);
ok(/Frozen forecasts/.test(r) && /\+0\.4%/.test(r), 'the ledger');
for (const h of [o, v, i, g, s, m, r, V.mmSectors(d)]) ok(!bad(h), 'no undefined / NaN');
ok(V.mmStack({ start: '2000-01-07', p: [[1, 0, 0]] }) === '', 'too short a history draws nothing');
console.log(`market-models view: ${n} checks passed`);
