// odds-view.js and odds.js: one company's odds and the hub's market, leaders and track-record views render from an
// odds file (the hub's helpers stubbed; no browser, no network).
const assert = require('node:assert/strict');
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
global.kpi = (l, v, c = '') => `<div class="metric"><label>${esc(l)}</label><strong>${esc(v)}</strong><small>${esc(c)}</small></div>`;
global.table = (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.state = {};
global.window = {};
const V = require('../docs/odds-view.js');
const H = require('../docs/odds.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const card = (base, auc, skill) => ({ n: 5000, base, brier: 0.1, brier_base: 0.11, skill, auc, calib: [[0.1, 0.09, 2000], [0.3, 0.32, 2000], [0.6, 0.55, 1000]] });
const d = {
  generated_at: '2026-10-31T00:00:00+00:00', asof: '2026-10-23', counts: { stocks: 2287 }, survivorship: "Today's companies only.",
  market: {
    recession: { p: 0.12, month: '2026-09', for_month: '2027-09', spread: 1.01, sahm: 0.1, coef: [-0.5333, -0.633], scored_to: '2024-10',
      history: [['2007-01', 0.4, -0.2], ['2008-06', 0.2, 1.5], ['2026-09', 0.12, 1.01]], card: card(0.08, 0.73, -0.19), card_oos: card(0.09, 0.65, -0.36) },
    regime: { p_stress: 0.04, p_down13: 0.32, week: '2026-10-23', states: { calm: { mean_a_year: 0.19, vol_a_year: 0.11, stay: 0.97 }, stressed: { mean_a_year: -0.14, vol_a_year: 0.28, stay: 0.92 } },
      history: [['2025-01-03', 0.1, 0.3], ['2026-10-23', 0.04, 0.32]], card: card(0.31, 0.46, -0.04) },
    spy: { dn10_4: 0.003, up10_4: 0.003, dn20_13: 0.004, up20_13: 0.002, vol: 0.1 },
  },
  models: { dn20_13: { card: card(0.17, 0.71, 0.086) }, sp500_12m: { card: card(0.012, 0.94, 0.05), features: ['log market value'] }, beat13: { card: card(0.48, 0.51, -0.001) } },
  leaders: { sp500_12m: [['ALAB', 0.23], ['NET', 0.22]], divcut_12m: [['IEP', 0.76]], dn20_13: [], up20_13: [], merton_1y: [] },
  live: { since: '2026-10-23', weeks: 1, cards: {} },
};
const s = { asof: '2026-10-23', fields: ['dn10_4', 'up10_4', 'dn20_13', 'up20_13', 'beat13', 'beat52', 'sp500_12m', 'divcut_12m', 'merton_1y', 'vol'],
  rows: { NET: [0.2, 0.22, 0.18, 0.24, 0.49, 0.46, 0.22, null, 0.0, 0.45] } };
const one = V._html('NET', d, s, 'disclosures/');
ok(/Odds · NET/.test(one) && /Falls 20% within 13 weeks/.test(one), 'the price moves');
ok(/Added to the S&amp;P 500 within a year/.test(one) && /22%/.test(one), 'the S&P 500 odds');
ok(!/Cuts or skips/.test(one), 'no dividend line for a non-payer');
ok(/&lt;0\.1%/.test(one), 'tiny odds shown as under 0.1%');
ok(/href="disclosures\/#odds\/NET"/.test(one), 'link to the hub');
const m = H.odMarket(d);
ok(/Chance of recession in 2027-09/.test(m) && /12%/.test(m), 'the recession odds');
ok(/Stressed regime now/.test(m) && /<svg/.test(m), 'the regime and its chart');
ok(/coin flip/.test(m), 'the regime model owns its record');
const L = H.odLeaders(d);
ok(/data-odco="ALAB"/.test(L) && /76%/.test(L), 'the leaders');
const R = H.odRecord(d);
ok(/US recession 12 months out/.test(R) && /<circle/.test(R), 'the calibration charts');
ok(!/NaN|undefined/.test(one + m + L + R), 'no NaN or undefined');
console.log(`odds-view: ${n} checks passed`);
