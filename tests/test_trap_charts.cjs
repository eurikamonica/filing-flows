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
// roll-view: the words and the X card are built from the data alone (a DOM-free check of the pure functions)
global.window = {}; require('../disclosures/docs/roll-view.js');
const RV = global.window.RollView;
const P = { kind: 'q', start: '2025-06-30', end: '2025-09-30', label: 'Q3', explained_share: 0.9, totals: {}, accounts: [
  { k: 'ar', side: 'a', name: 'Receivables', open: 200e6, close: 230e6, delta: 30e6, flows: [['d_ar', 'Change in receivables (cash flow statement)', 30e6]], residual: 0, tags: ['AccountsReceivableNetCurrent'] },
  { k: 'eq', side: 'e', name: 'Equity', open: 400e6, close: 460e6, delta: 60e6, flows: [['ni', 'Net income', 80e6], ['buyback', 'Share buybacks', -25e6], ['sbc', 'Share-based compensation', 5e6]], residual: 0, tags: [] },
  { k: 'gw', side: 'a', name: 'Goodwill and intangibles', open: 100e6, close: 112e6, delta: 12e6, flows: [], residual: 12e6, tags: ['Goodwill'] }] };
const w = RV.words(P, 3);
eq(w.map((x) => x.k), ['eq', 'ar', 'gw'], 'largest movements first');
eq(w[0].text, 'Equity up $60M: +$80M net income, −$25M buybacks, +$5M stock compensation.', 'flows in words, largest first');
eq(w[2].text, 'Goodwill and intangibles up $12M: +$12M not explained by the statements.', 'a residual is said, not hidden');
const svg = RV.card(P, { ticker: 'AAA', name: 'Alpha Inc.' });
assert(/^<svg /.test(svg) && svg.includes('AAA Alpha Inc.') && svg.includes('filing-flows.com') && svg.includes('url(#xh)') && svg.includes('Not investment advice'), 'card'); n++;
P.cf = { ni: 80e6, ocf: 90e6, noncash: [['da', 'Depreciation and amortization', 30e6]], wc: [['d_ar', 'Receivables', -30e6]], op_other: 10e6, inv: [['capex', 'Capital expenditure', -50e6]], inv_total: -50e6, inv_other_gap: 0, fin: [], fin_total: 0, fin_other_gap: 0, fx: null, dcash: 40e6 };
P.accounts.push({ k: 'cash', side: 'a', name: 'Cash and equivalents', open: 100e6, close: 140e6, delta: 40e6, flows: [['ocf', 'Operating cash flow', 90e6], ['inv', 'Investing cash flow', -50e6]], residual: 0, tags: [] });
const det = RV.cardDetailed(P, { ticker: 'AAA', name: 'Alpha Inc.' });
assert(det.includes('1 · The cash flow statement') && det.includes('Operating lines not itemised') && det.includes('2 · Every balance-sheet account') && det.includes('3 · Each movement in words') && /viewBox="0 0 1200 \d+"/.test(det), 'detailed card'); n++;
console.log(n + ' checks with the roll-view words and cards');
// the three-column Sankey: conservation per account (open − out + in = close), the kept band, the middle nodes
RV.setLabels({ d_ar: 'Change in receivables', ni: 'Net income', buyback: 'Share buybacks', sbc: 'Share-based compensation', ocf: 'Operating cash flow', inv: 'Investing', capex: 'Capital expenditure' });
P.accounts.push({ k: 'ppe', side: 'a', name: 'PP&E', open: 400e6, close: 420e6, delta: 20e6, flows: [['capex', '', 50e6], ['da', '', -30e6]], residual: 0, tags: [] });
P.cf.inv = [['capex', 'Capital expenditure', -50e6]];
const sk = RV.sankey(P, P.accounts, {});
assert(/^<svg /.test(sk) && sk.includes('Balance sheet 2025-06-30') && sk.includes('Balance sheet 2025-09-30'), 'sankey frame'); n++;
assert(sk.includes('Capital expenditure: +$50M into pp&amp;e') && sk.includes('Capital expenditure: −$50M out of cash and equivalents'), 'capex runs cash → PP&E through one node'); n++;
assert(sk.includes('Share buybacks: −$25M out of equity') && sk.includes('Equity: kept $375M'), 'equity keeps open − out: 400 − 25'); n++;
assert(sk.includes('Not explained: goodwill and intangibles: +$12M into goodwill and intangibles'), 'the residual is a band of its own'); n++;
console.log(n + ' checks with the roll-view Sankey');
