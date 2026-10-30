// strategies.js: the hub's Strategies tab renders every rule, one rule and the overfitting view from a strategies file
// (the hub's helpers stubbed; no browser, no network).
const assert = require('node:assert/strict');
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
global.kpi = (l, v, c = '') => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.table = (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.state = {};
global.exported = null;
global.window = {};
const V = require('../docs/strategies.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const m = (o) => Object.assign({ from: '1995-01-06', to: '2026-10-23', cagr: 0.1, vol: 0.12, sharpe: 0.64, maxdd: -0.23, maxdd_at: '2009-03-06', beta: 0.5, alpha: 0.02, psr: 0.99 }, o);
const d = {
  generated_at: '2026-10-31T00:00:00+00:00', asof: '2026-10-23', trials: 71, sr0_annual: 0.49,
  assumptions: { cost: '5 bp …', cash: 'Fed funds rate', borrow: 0.005 }, survivorship: "Today's companies only.",
  rows: [
    { id: 'spy', name: 'S&P 500 (SPY), bought and held', group: 'Benchmarks', paper: '—', bench: true, rules: 'SPY held.', full: m({ sharpe: 0.55 }), yearly: { 2008: -0.37, 2009: 0.26 } },
    { id: 'trend', name: 'Trend: S&P 500 above its 10-month average', group: 'Trend & momentum', paper: 'Faber (2007)', year: 2007, params: { ma: 40 },
      rules: 'At each month-end, hold SPY if it closed above its 40-week average, else cash.', full: m({}), pre: m({ sharpe: 0.66 }), post: m({ sharpe: 0.63 }),
      spy_same: m({ cagr: 0.11, sharpe: 0.55, maxdd: -0.55 }), dsr: 0.8, yearly: { 2008: 0.02, 2009: 0.1 }, turnover: 1.5, cost_drag: 0.0008, exposure: 0.8, gross_cagr: 0.101,
      pbo: { pbo: 0.84, splits: 252, from: '1995-02-03', to: '2026-10-23', variants: [{ params: { ma: 20 }, sharpe: 0.45 }, { params: { ma: 40 }, sharpe: 0.64 }] },
      holdings: [['SPY', 1]], n_holdings: 1, cash: 0, live: { since: '2026-10-23', weeks: 2, ret: 0.012, curve: [['2026-10-30', 1.005], ['2026-11-06', 1.012]] } },
  ],
};
const cv = { start: '1990-01-05', curves: { spy: { i0: 260, eq: [1, 1.1, 1.05, 1.2] }, trend: { i0: 261, eq: [1, 1.02, 1.04] } } };
const all = V.stAll(d, cv);
ok(/Settings tried/.test(all) && /71/.test(all), 'the trial count');
ok(/<svg/.test(all), 'the growth chart');
ok(/data-stid="trend"/.test(all) && /Faber \(2007\)/.test(all), 'every rule listed with its paper');
ok(/0\.66 → 0\.63/.test(all), 'before and after publication');
ok(/84%/.test(all), 'the PBO');
ok(Array.isArray(global.exported) && global.exported.length === 2, 'the CSV rows');
const one = V.stOne(d, cv, 'trend');
ok(/Growth of \$1/.test(one) && /Drawdown/.test(one), 'the rule\'s charts');
ok(/Nearby settings/.test(one) && /the paper's/.test(one), 'the settings around the paper\'s');
ok(/What it holds now/.test(one) && /SPY/.test(one), 'its holdings');
ok(/Live paper record/.test(one) && /2 weeks live/.test(one), 'the live record');
ok(!/NaN|undefined/.test(one), 'no NaN or undefined');
const of = V.stOverfit(d);
ok(/luck/.test(of) && /stroke-dasharray|dashed/.test(of), 'the luck bar');
console.log(`strategies-view: ${n} checks passed`);
