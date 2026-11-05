/* web/trap-charts.js: the bridge adds up (Q01), a missing working-capital part is declared rather than drawn as zero
   (Q02), the readings leave the figures alone (Q03), and the cash margin matrix (Q04). */
const assert = require('assert');
const C = require('../web/trap-charts.js');
let n = 0;
const eq = (a, b, m) => { assert.deepStrictEqual(a, b, m); n++; };
// Q01: G01's demo (40 → 110: working capital +30, capex cut +40, other 0)
let b = C.bridge({ prior_fcf: 40, current_fcf: 110, capex_reduction: 40, wc_cash_change: 30 });
eq([b.prior, b.other, b.wc, b.capex, b.current, b.covered], [40, 0, 30, 40, 110, true], 'G01 demo');
eq(b.prior + b.other + b.wc + b.capex, b.current, 'the steps add to the end');
// any inputs: the residual takes what the parts do not explain
b = C.bridge({ prior_fcf: 100, current_fcf: 90, capex_reduction: -20, wc_cash_change: 5 });
eq(b.prior + b.other + b.wc + b.capex, b.current, 'conservation with a capex rise and a fall in FCF');
eq(b.other, 5, 'other = Δ − capex − wc');
// Q02: no working-capital figure → not covered, nothing invented
b = C.bridge({ prior_fcf: 40, current_fcf: 110, capex_reduction: 40 });
eq([b.wc, b.covered, b.other], [null, false, 30], 'missing working capital stays null and its part sits in other');
// Q03: the readings are text; none changes the arithmetic
eq(C.READINGS.map((r) => r[0]), ['expansion', 'deferred', 'unknown'], 'three readings');
// Q04: G04's demo (cash 30, floor 10, due 40, receivable 50 as the realisable inflow)
const m = (rate, fac) => C.margin(30, 50, rate, fac, 40, 10);
eq([m(0.2, 0), m(0.4, 0), m(0.8, 20), m(0.6, 10)], [-10, 0, 40, 20], 'G04 matrix cells');
eq(C.margin(30, -50, 1, 0, 40, 10), -20, 'negative FCF counts as zero inflow');
eq(C.money(-1.5e9), '−$1.50B', 'money');
console.log(n + ' trap chart checks passed');
