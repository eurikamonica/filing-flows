// Valuation math (web/fsa.js): the acceptance cases of fsa-beta/planning/03_VALUATION.md and the solver's failure states.
const assert = require('node:assert/strict');
const F = require('../web/fsa.js');
const near = (a, b, tol = 1e-9) => assert.ok(Math.abs(a - b) <= tol, `${a} is not ${b}`);

// a zero-growth perpetuity from next year: FCFF 10, WACC 10% → EV 100; − debt 20 + cash 5 → equity 85; 10 shares → 8.5
const base = { rev0: 100, years: 5, growth: 0, margin: 0.1, tax: 0, da: 0, capex: 0, wc: 0, wacc: 0.10, g: 0,
  terminal: 'simple', debt: 20, cash: 5, claims: 0, nonop: 0, shares: 10 };
let r = F.dcf(base);
near(r.ev, 100); near(r.equity, 85); near(r.perShare, 8.5);
r.rows.forEach((x) => near(x.fcff, 10));
// five explicit years + terminal equals the same perpetuity; the ROIC terminal with g = 0 needs no reinvestment
near(F.dcf({ ...base, terminal: 'roic', roic: 0.2 }).ev, 100);
// cash is added once: a separate nonoperating asset is not the same as cash
near(F.dcf({ ...base, cash: 0, nonop: 5 }).equity, 85);
near(F.dcf({ ...base, cash: 5, nonop: 5 }).equity, 90);
// growth with ROIC reinvestment: FCFF[N+1] = NOPAT[N+1] × (1 − g / ROIC)
r = F.dcf({ ...base, g: 0.02, terminal: 'roic', roic: 0.1 });
near(r.fcffNext, 100 * 1.02 * 0.1 * (1 - 0.2));
// losses: no tax benefit unless asked
r = F.dcf({ ...base, margin: -0.05, tax: 0.25 });
near(r.rows[0].nopat, -5);
near(F.dcf({ ...base, margin: -0.05, tax: 0.25, lossTax: 'symmetric' }).rows[0].nopat, -3.75);
assert.ok(F.dcf({ ...base, margin: -0.05 }).flags.some((f) => /negative/.test(f)));
// invalid inputs are rejected, not computed
assert.equal(F.dcf({ ...base, wacc: 0.03, g: 0.03 }).ok, false);
assert.equal(F.dcf({ ...base, wacc: -1 }).ok, false);
assert.equal(F.dcf({ ...base, shares: 0 }).ok, false);
assert.equal(F.dcf({ ...base, shares: -5 }).ok, false);
assert.equal(F.dcf({ ...base, rev0: NaN }).ok, false);
assert.equal(F.dcf({ ...base, terminal: 'roic', roic: 0.01, g: 0.02, wacc: 0.1 }).ok, false);

// reverse: a price made from a hidden growth rate is recovered
const hidden = { ...base, growth: 0.07, g: 0.02, terminal: 'roic', roic: 0.15, tax: 0.21, da: 0.03, capex: 0.04, wc: 0.1 };
const price = F.value(hidden);
let s = F.solve(hidden, 'growth', price, -0.2, 0.4);
assert.equal(s.status, 'ok'); near(s.value, 0.07, 1e-6); near(s.residual, 0, 1e-6);
s = F.solve(hidden, 'margin', price, -0.1, 0.6);
assert.equal(s.status, 'ok'); near(s.value, 0.1, 1e-6);
// an impossible price inside the bounds: said, not clamped
s = F.solve(hidden, 'growth', price * 100, -0.2, 0.4);
assert.equal(s.status, 'none'); assert.equal(s.value, undefined);
// zero shares: the model is undefined, the solver says so
assert.equal(F.solve({ ...hidden, shares: 0 }, 'growth', price, -0.2, 0.4).status, 'none');
// more than one solution and no convergence are reported, never collapsed into one number
const two = F.root1((v) => (v - 1) * (v - 3), 0, 4);
assert.equal(two.status, 'multiple'); assert.equal(two.brackets.length, 2);
assert.equal(F.root1((v) => v * v + 1, -2, 2).status, 'none');
near(F.root1((v) => v - 0.25, 0, 1).value, 0.25, 1e-6);
// sensitivity grid has the right shape
const gr = F.grid(base, 'wacc', [0.08, 0.1, 0.12], 'g', [0, 0.01]);
assert.equal(gr.length, 3); assert.equal(gr[0].length, 2); near(gr[1][0], 8.5);
console.log('valuation math: all checks passed');

// ---- cash collected from customers against revenue
const period = (rev, items) => ({ wc: { rev }, bridge: { items } });
// Microsoft-like quarter: receivables up 21.1B (cash effect −), deferred revenue up 22.4B (+): collected 101% of revenue
let cl = F.collections(period(90.007e9, [['da', 5e9, [0]], ['d_ar', -21.084e9, [1]], ['d_contract', 22.428e9, [2]]]));
near(cl.cash, 91.351e9, 1); near(cl.rate, 91.351 / 90.007, 1e-9); assert.equal(cl.parts.length, 2); assert.equal(cl.broad, false);
// NVIDIA-like quarter: receivables up 22.3B on 96.2B of revenue: about 77% collected
near(F.collections(period(96.221e9, [['d_ar', -22.347e9, [1]]])).rate, 73.874 / 96.221, 1e-9);
// contract assets up: earned, not billed or collected yet
near(F.collections(period(100, [['d_ar', 5, [1]], ['d_casset', -10, [3]]])).cash, 95);
// no receivables change tagged, no revenue, or a loss of revenue: no estimate rather than revenue = cash
assert.equal(F.collections(period(100, [['d_contract', 5, [2]]])), null);
assert.equal(F.collections(period(null, [['d_ar', 5, [1]]])), null);
assert.equal(F.collections(period(0, [['d_ar', 5, [1]]])), null);
assert.equal(F.collections({}), null);
// receivables tagged together with other operating assets: flagged as broad
const concepts = ['IncreaseDecreaseInAccountsReceivableAndOtherOperatingAssets'];
assert.equal(F.collections(period(100, [['d_ar', -5, [0]]]), (ref) => concepts[ref[0]]).broad, true);
// four quarters add up; one missing estimate → none
const four = [period(100, [['d_ar', -10, [1]]]), period(100, [['d_ar', 5, [1]]]), period(120, [['d_ar', -20, [1]]]), period(80, [['d_ar', 25, [1]]])];
const s4 = F.collectionsSum(four);
near(s4.rev, 400); near(s4.cash, 400); near(s4.rate, 1);
assert.equal(F.collectionsSum(four.concat([period(100, [])])), null);
assert.equal(F.collectionsSum([]), null);

// ---- reserve signals across fiscal years
const yrs = [{ end: '2023-12-31', ni: 100, wc: { rev: 1000 } }, { end: '2024-12-31', ni: 100, wc: { rev: 1000 } },
  { end: '2025-12-31', ni: 80, wc: { rev: 1100 } }];
const rows = [
  { id: 'warranty', label: 'FY2025', end: '2025-12-31', opening: 40, additions: 10, releases: 8, utilization: 20, closing: 22 },
  { id: 'warranty', label: 'FY2023', end: '2023-12-31', opening: 45, additions: 30, releases: 0, utilization: 25, closing: 50 },
  { id: 'warranty', label: 'FY2024', end: '2024-12-31', opening: 50, additions: 32, releases: 2, utilization: 40, closing: 40 },
];
const tr = F.reserveTrend(rows, yrs);
assert.deepEqual(tr.map((x) => x.label), ['FY2023', 'FY2024', 'FY2025']);               // oldest first
near(tr[0].ratio, 0.05); near(tr[1].ratio, 0.04); near(tr[2].ratio, 0.02);
// FY2024: ratio down 20% (under 25%), releases 2% of net income (under 5%), charged ÷ used exactly 0.8: no flags
assert.deepEqual(tr[0].flags, []); assert.deepEqual(tr[1].flags, []);
near(tr[1].relNi, 0.02); near(tr[1].cover, 0.8);
// FY2025: 8 released on 80 of net income (10%), 4% → 2% of revenue, 10 charged against 20 used while the balance fell
assert.deepEqual(tr[2].flags.map((f) => f.kind), ['release', 'drop', 'under']);
near(tr[2].flags[0].value, 0.1); near(tr[2].flags[1].from, 0.04); near(tr[2].flags[2].value, 0.5);
// a missing year in between: the fall in the share of revenue is not compared across the gap
const gap = F.reserveTrend([rows[1], rows[0]], yrs);
assert.deepEqual(gap.map((x) => x.label), ['FY2023', 'FY2025']);
assert.deepEqual(gap[1].flags.map((f) => f.kind), ['release', 'under']);
// a loss year: releases are not a share of net income; loan allowances are not compared with revenue
assert.equal(F.reserveTrend([{ ...rows[0] }], [{ ...yrs[2], ni: -5 }])[0].relNi, null);
assert.equal(F.reserveTrend([{ ...rows[0], id: 'loans' }], yrs)[0].ratio, null);
// no matching fiscal year: figures kept, ratios empty, nothing flagged
const lone = F.reserveTrend([{ ...rows[0], end: '2019-12-31' }], yrs)[0];
assert.equal(lone.ratio, null); assert.equal(lone.relNi, null); assert.deepEqual(lone.flags.map((f) => f.kind), ['under']);
console.log('cash collected and reserve signals: all checks passed');
