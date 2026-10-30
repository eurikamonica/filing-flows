// disclosures/docs/lbo-model.js and disclosures/app/lbo_board.cjs
'use strict';
const assert = require('assert');
const M = require('../disclosures/docs/lbo-model.js');
const { board } = require('../disclosures/app/lbo_board.cjs');

const rates = { base: 4, spread_b: 3.5 };                     // loan rate 4 + 3.5 + 0.5 = 8%
// a steady business: $1B revenue, 25% EBITDA margin, 5× EBITDA trading value
const co = { revenue: 1e9, ebitda: 2.5e8, da: 4e7, capex: 3e7, tax_rate: 0.21, g0: 0.03, price: 10, shares: 1e8, debt: 3e8, cash: 5e7, claims: 0 };
const r = M.run(co, {}, rates);
assert.ok(r.ok);
assert.ok(Math.abs(r.rate - 0.08) < 1e-12);
assert.ok(Math.abs(r.price - 13) < 1e-9);                     // +30%
assert.ok(Math.abs(r.entry.ev - (1.3e9 + 3e8 - 5e7)) < 1);
assert.ok(Math.abs(r.entry.debt - Math.min(5.5 * 2.5e8, 0.65 * r.entry.ev, 2.5e8 / (2 * 0.08))) < 1);   // the least of the three caps
assert.ok(Math.abs(r.entry.debt - 0.65 * r.entry.ev) < 1);    // here, 65% of the price
assert.ok(Math.abs(r.todayMultiple - (1e9 + 2.5e8) / 2.5e8) < 1e-9);
assert.strictEqual(r.years.length, 5);
assert.ok(r.years[4].debt < r.entry.debt);                    // free cash flow repays debt
assert.ok(r.irr > 0.10 && r.irr < 0.6, 'a cheap steady business makes a buyer money: ' + r.irr);
assert.deepStrictEqual(r.flags, []);
// a higher premium lowers the IRR; cost cuts raise it
assert.ok(M.run(co, { premium: 0.6 }, rates).irr < r.irr);
assert.ok(M.run(co, { marginUp: 0.03 }, rates).irr > r.irr);
// the most a buyer could pay for 20%: the IRR there is 20%
const mp = M.maxPrice(co, {}, rates);
assert.ok(mp.price > 0);
assert.ok(Math.abs(M.run(co, { price: mp.price }, rates).irr - 0.2) < 1e-3);
// coverage caps the debt when rates are high
const hi = M.run(co, {}, { base: 12, spread_b: 6 });
assert.ok(Math.abs(hi.entry.debt - 2.5e8 / (2 * 0.185)) < 1);   // 2× interest coverage binds
// no LBO without positive EBITDA; flags for a levered or a giant company
assert.strictEqual(M.run(Object.assign({}, co, { ebitda: -1 }), {}, rates).ok, false);
assert.ok(M.run(Object.assign({}, co, { debt: 2e9 }), {}, rates).flags.includes('levered'));
assert.ok(M.run(Object.assign({}, co, { shares: 1e10 }), {}, rates).flags.includes('too big'));

// the board: results added, a score from the three angles
const doc = { generated_at: 'x', rates, fields: ['cik', 'ticker', 'name', 'sector', 'inputs', 'p_acquired', 'decile', 'p_private', 'rumor', 'rumor_date', 'rumor_kind', 'rumor_text', 'revenue'],
  rows: [[1, 'AAA', 'A', 'industrials', co, 0.08, 9, 0.01, 5, '2026-10-29', 'news', 'A explores a sale', 1e9],
    [2, 'BBB', 'B', 'industrials', Object.assign({}, co, { price: 40 }), 0.03, 3, 0.002, 0, null, null, null, 1e9],
    [3, 'CCC', 'C', 'financials', null, null, null, null, 2, '2026-10-01', '13D', 'x', 1e9]] };
const b = board(doc);
const F = b.fields, row = (t) => b.rows.find((x) => x[F.indexOf('ticker')] === t);
assert.ok(row('AAA')[F.indexOf('irr')] > row('BBB')[F.indexOf('irr')]);
assert.ok(row('AAA')[F.indexOf('score')] > row('BBB')[F.indexOf('score')]);
assert.strictEqual(row('CCC')[F.indexOf('irr')], null);
assert.ok(row('CCC')[F.indexOf('score')] != null);              // rumors alone still score
console.log('lbo model: ok');
