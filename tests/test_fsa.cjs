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
