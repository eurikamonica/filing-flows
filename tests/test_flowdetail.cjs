// web/flowdetail.js build(): the ultra-detailed canvas's flows on a small made-up company (disclosures/app/flowdetail.py
// writes the same structure): the default view, the segments' own income statements, the cash flows by use, + / −
'use strict';
const assert = require('assert');
const F = require('../web/flowdetail.js');

const G = 'us-gaap:';
const SEG = 'us-gaap:StatementBusinessSegmentsAxis', P = 'srt:ProductOrServiceAxis';
const k = (c, ax, m) => `${G}${c}|${ax}=x:${m}`;
const u = {
  root: G + 'NetIncomeLoss', cash_root: 'cf>' + G + 'CashPeriodIncreaseDecrease', cash_ni: G + 'NetIncomeLoss', axis: P,
  J: {
    [G + 'NetIncomeLoss']: [[G + 'IncomeLossBeforeIncomeTaxes', 1], [G + 'IncomeTaxExpenseBenefit', -1]],
    [G + 'IncomeLossBeforeIncomeTaxes']: [[G + 'OperatingIncomeLoss', 1], [G + 'NonoperatingIncomeExpense', 1]],
    [G + 'OperatingIncomeLoss']: [[G + 'GrossProfit', 1], [G + 'OperatingExpenses', -1]],
    [G + 'GrossProfit']: [[G + 'Revenues', 1], [G + 'CostOfRevenue', -1]],
    [G + 'OperatingExpenses']: [[G + 'ResearchAndDevelopmentExpense', 1], [G + 'SellingGeneralAndAdministrativeExpense', 1], [G + 'TinyA', 1], [G + 'TinyB', 1]],
    [G + 'Revenues']: [[k('Revenues', P, 'Hw'), 1], [k('Revenues', P, 'Sw'), 1]],
    ['cf>' + G + 'CashPeriodIncreaseDecrease']: [['cf>' + G + 'NetCashProvidedByUsedInOperatingActivities', 1], ['cf>' + G + 'NetCashProvidedByUsedInInvestingActivities', 1], ['cf>' + G + 'NetCashProvidedByUsedInFinancingActivities', 1]],
    ['cf>' + G + 'NetCashProvidedByUsedInOperatingActivities']: [[G + 'NetIncomeLoss', 1], ['cf>' + G + 'DepreciationDepletionAndAmortization', 1], ['cf>' + G + 'IncreaseDecreaseInAccountsReceivable', -1]],
    ['cf>' + G + 'NetCashProvidedByUsedInInvestingActivities']: [['cf>' + G + 'PaymentsToAcquirePropertyPlantAndEquipment', -1]],
    ['cf>' + G + 'NetCashProvidedByUsedInFinancingActivities']: [['cf>' + G + 'PaymentsForRepurchaseOfCommonStock', -1], ['cf>' + G + 'PaymentsOfDividends', -1]],
  },
  via: { [G + 'Revenues']: 'dims:' + P },
  default: [G + 'NetIncomeLoss', G + 'IncomeLossBeforeIncomeTaxes', G + 'OperatingIncomeLoss', G + 'GrossProfit', G + 'OperatingExpenses', G + 'Revenues',
    'cf>' + G + 'CashPeriodIncreaseDecrease', 'cf>' + G + 'NetCashProvidedByUsedInOperatingActivities', 'cf>' + G + 'NetCashProvidedByUsedInInvestingActivities',
    'cf>' + G + 'NetCashProvidedByUsedInFinancingActivities'],
  alt: { [P]: { [G + 'Revenues']: [[k('Revenues', P, 'Hw'), 1], [k('Revenues', P, 'Sw'), 1]] },
    [SEG]: { [G + 'Revenues']: [[k('Revenues', SEG, 'East'), 1], [k('Revenues', SEG, 'West'), 1]] } },
  seg: {
    profit: G + 'OperatingIncomeLoss', rev: 'seg>' + G + 'Revenues', src: G + 'Revenues', members: ['x:East', 'x:West'],
    J: {
      [G + 'OperatingIncomeLoss']: [[k('OperatingIncomeLoss', SEG, 'East'), 1], [k('OperatingIncomeLoss', SEG, 'West'), 1], ['#gap:seg', 1]],
      [k('OperatingIncomeLoss', SEG, 'East')]: [[k('Revenues', SEG, 'East'), 1], [k('CostOfRevenue', SEG, 'East'), -1]],
      [k('OperatingIncomeLoss', SEG, 'West')]: [[k('Revenues', SEG, 'West'), 1], [k('CostOfRevenue', SEG, 'West'), -1]],
      ['seg>' + G + 'Revenues']: [[k('Revenues', SEG, 'East'), 1], [k('Revenues', SEG, 'West'), 1]],
    },
  },
  cash_uses: {
    order: ['capex', 'buyback', 'dividend'],
    J: {
      '#cat:capex': [['cf>' + G + 'PaymentsToAcquirePropertyPlantAndEquipment', -1]],
      '#cat:buyback': [['cf>' + G + 'PaymentsForRepurchaseOfCommonStock', -1]],
      '#cat:dividend': [['cf>' + G + 'PaymentsOfDividends', -1]],
      '#cat:fcf': [['cf>' + G + 'NetCashProvidedByUsedInOperatingActivities', 1], ['#cat:capex', 1]],
      ['cf>' + G + 'CashPeriodIncreaseDecrease']: [['#cat:fcf', 1], ['#cat:buyback', 1], ['#cat:dividend', 1]],
    },
  },
  of: { [G + 'ResearchAndDevelopmentExpense']: { sbc: `${G}ShareBasedCompensation|${G}IncomeStatementLocationAxis=${G}ResearchAndDevelopmentExpenseMember` } },
  labels: { [k('Revenues', SEG, 'East')]: 'East', [k('OperatingIncomeLoss', SEG, 'East')]: 'East · segment profit' },
};
const now = {
  [G + 'Revenues']: 100, [k('Revenues', P, 'Hw')]: 60, [k('Revenues', P, 'Sw')]: 40, [G + 'CostOfRevenue']: 40, [G + 'GrossProfit']: 60,
  [G + 'ResearchAndDevelopmentExpense']: 15, [G + 'SellingGeneralAndAdministrativeExpense']: 9.9, [G + 'TinyA']: 0.06, [G + 'TinyB']: 0.04, [G + 'OperatingExpenses']: 25,
  [G + 'OperatingIncomeLoss']: 35, [G + 'NonoperatingIncomeExpense']: 2, [G + 'IncomeLossBeforeIncomeTaxes']: 37, [G + 'IncomeTaxExpenseBenefit']: 7, [G + 'NetIncomeLoss']: 30,
  ['cf>' + G + 'DepreciationDepletionAndAmortization']: 5, ['cf>' + G + 'IncreaseDecreaseInAccountsReceivable']: 3, ['cf>' + G + 'NetCashProvidedByUsedInOperatingActivities']: 32,
  ['cf>' + G + 'PaymentsToAcquirePropertyPlantAndEquipment']: 12, ['cf>' + G + 'NetCashProvidedByUsedInInvestingActivities']: -12,
  ['cf>' + G + 'PaymentsForRepurchaseOfCommonStock']: 10, ['cf>' + G + 'PaymentsOfDividends']: 4, ['cf>' + G + 'NetCashProvidedByUsedInFinancingActivities']: -14,
  ['cf>' + G + 'CashPeriodIncreaseDecrease']: 6,
  [k('Revenues', SEG, 'East')]: 70, [k('Revenues', SEG, 'West')]: 30, [k('CostOfRevenue', SEG, 'East')]: 30, [k('CostOfRevenue', SEG, 'West')]: 20,
  [k('OperatingIncomeLoss', SEG, 'East')]: 40, [k('OperatingIncomeLoss', SEG, 'West')]: 10, '#gap:seg': -15, ['seg>' + G + 'Revenues']: 100,
  '#cat:capex': -12, '#cat:buyback': -10, '#cat:dividend': -4, '#cat:fcf': 20,
  [`${G}ShareBasedCompensation|${G}IncomeStatementLocationAxis=${G}ResearchAndDevelopmentExpenseMember`]: 3,
};
const scale = (o, f) => Object.fromEntries(Object.entries(o).map(([a, b]) => [a, b * f]));
u.now = scale(now, 1e9); u.y = scale(now, 0.8e9); u.q = scale(now, 0.95e9);

function balanced(sp) {
  return sp.nodes.filter((n) => {
    const i = sp.links.filter((l) => l.t === n.id).reduce((a, l) => a + l.v, 0), o = sp.links.filter((l) => l.s === n.id).reduce((a, l) => a + l.v, 0);
    return i && o && Math.abs(i - o) > 1e-6 * Math.max(i, o);
  }).map((n) => n.id);
}
const L = (sp) => new Map(sp.links.map((l) => [`${l.s}>${l.t}`, l.v / 1e9]));
const id = (sp, key) => (sp.nodes.find((n) => n.key === key) || {}).id;

// the default view: the detailed chart's lines; the two tiny costs summed as Other, with a + to open them
let sp = F.build(u, {});
assert.deepStrictEqual(balanced(sp), []);
let l = L(sp);
assert.strictEqual(l.get('revenue>gp'), 60);
assert.strictEqual(l.get('gp>opex'), 25);
assert.strictEqual(l.get('net>ocf'), 27);
const other = sp.nodes.find((n) => /^o:/.test(n.id));
assert.ok(other && /Other \(2 items\)/.test(other.name), 'tiny parts summed');
assert.strictEqual(sp.toggles.get(other.id), '+');
// stock pay inside R&D: a label line and the band into it lined
const rd = sp.nodes.find((n) => n.key === G + 'ResearchAndDevelopmentExpense');
assert.ok(rd.lines.some((x) => /stock pay \$3\.0B \(20%\) inside/.test(x[1])));
assert.ok(Math.abs(sp.links.find((x) => x.t === rd.id).of - 0.2) < 1e-9);
// opening Other: its parts flow out of it
sp = F.build(u, { opened: new Set([other.key]) });
assert.deepStrictEqual(balanced(sp), []);
assert.ok(sp.nodes.some((n) => n.key === G + 'TinyA'));
assert.strictEqual(sp.toggles.get(other.id), '−');

// costs by segment: revenue → the segments → each segment's costs and profit → operating profit, the unallocated out
sp = F.build(u, { costs: 'segments' });
assert.deepStrictEqual(balanced(sp), []);
l = L(sp);
const east = id(sp, k('Revenues', SEG, 'East')), eastP = id(sp, k('OperatingIncomeLoss', SEG, 'East'));
assert.strictEqual(l.get(`revenue>${east}`), 70);
assert.strictEqual(l.get(`${east}>${eastP}`), 40);
assert.strictEqual(l.get(`${east}>${id(sp, k('CostOfRevenue', SEG, 'East'))}`), 30);
assert.ok(sp.nodes.some((n) => n.key === '#gap:seg'), 'what the segments do not carry');
assert.ok(!sp.nodes.some((n) => n.id === 'gp'), 'no company-level gross profit in the segment view');
assert.strictEqual(sp.nodes.find((n) => n.id === east).color, 'rev');
const col = (i) => sp.nodes.find((n) => n.id === i).col;
assert.ok(col('revenue') < col(east) && col(east) < col(eastP) && col(eastP) < col('oi'));
assert.ok(sp.nodes.some((n) => n.key === k('Revenues', P, 'Hw')), 'revenue still by products on the left');

// cash by use: operating cash flow → capital spending + free cash flow → buybacks, dividends, cash kept; groups open with +
sp = F.build(u, { cash: 'uses' });
assert.deepStrictEqual(balanced(sp), []);
l = L(sp);
assert.strictEqual(l.get(`ocf>${id(sp, '#cat:capex')}`), 12);
assert.strictEqual(l.get(`ocf>${id(sp, '#cat:fcf')}`), 20);
assert.strictEqual(sp.toggles.get(id(sp, '#cat:capex')), '+');
sp = F.build(u, { cash: 'uses', opened: new Set(['#cat:capex']) });
assert.ok(sp.nodes.some((n) => n.key === 'cf>' + G + 'PaymentsToAcquirePropertyPlantAndEquipment'));
assert.deepStrictEqual(balanced(sp), []);

// revenue by the other dimension
sp = F.build(u, { revAxis: SEG });
assert.ok(sp.nodes.some((n) => n.key === k('Revenues', SEG, 'West')) && !sp.nodes.some((n) => n.key === k('Revenues', P, 'Hw')));
// comparisons carried on every node and link
sp = F.build(u, {});
assert.ok(sp.nodes.every((n) => n.y != null) && sp.links.every((x) => x.y != null && x.q != null));
assert.ok(/^Δ \+\$5\.0B/.test(sp.nodes.find((n) => n.id === 'revenue').cmp));
const v = F.views(u);
assert.deepStrictEqual([v.rev.length, v.seg, v.cash], [2, true, true]);
// the next period as guided: the projection carried into every line, the guided capital spending set, the totals summed
// again and the flows built anew — free cash flow turns into a gap and the cash is drawn down to fill it
const FG = require('../web/guidance.js');
global.FFGuidance = FG;
const g = { filed: '2026-10-20', form: '8-K', items: [
  { metric: 'revenue', name: 'Revenue', period: 'Q4 2026', unit: 'usd', lo: 108e9, hi: 112e9 },
  { metric: 'operating_income', name: 'Operating income', period: 'Q4 2026', unit: 'usd', lo: 40e9, hi: 40e9 },
  { metric: 'capex', name: 'Capital expenditures', period: 'Q4 2026', unit: 'usd', lo: 45e9, hi: 45e9, approx: true }] };
const near = (a, b, tol) => Math.abs(a - b) <= (tol || 0.01);
for (const cash of ['uses', 'statement']) {
  const opts = { cash };
  const sp0 = F.build(u, opts);
  const spec = { nodes: sp0.nodes, links: sp0.links, end: '2026-09-30', label: 'Q3 2026' };
  const company = { quarters: [Object.assign({}, spec)], years: [] };
  const r = FG.future(spec, g, { company, name: 'Made-up', full: true });
  assert.ok(!r.error, r.error);
  const tg = FG.target(g, spec, company);
  const { vals, guided } = F.guidedValues({ ...u }, opts, sp0, r, g.items, tg.period);
  const B = (key) => vals[key] / 1e9;
  assert.ok(near(B(G + 'Revenues'), 110) && near(B(k('Revenues', P, 'Hw')), 66), 'revenue and its parts');
  assert.ok(near(B(G + 'OperatingIncomeLoss'), 40), 'guided operating profit');
  assert.ok(near(B('cf>' + G + 'PaymentsToAcquirePropertyPlantAndEquipment'), 45), 'guided capital spending');
  assert.ok(near(B('cf>' + G + 'PaymentsForRepurchaseOfCommonStock'), 10), 'cash lines not guided stay');
  const ni = B(G + 'NetIncomeLoss');
  assert.ok(near(B('cf>' + G + 'NetCashProvidedByUsedInOperatingActivities'), ni + 5 - 3), 'operating cash flow from the projected earnings');
  assert.ok(near(B('cf>' + G + 'CashPeriodIncreaseDecrease'), ni + 2 - 45 - 14), 'the cash change is the balance');
  assert.ok(guided['cf>' + G + 'PaymentsToAcquirePropertyPlantAndEquipment']);
  const nx = F.guidedFlows({ u, end: '2026-09-30' }, opts, sp0, r, g, tg.period, null);
  assert.deepStrictEqual(balanced(nx.sp), []);
  const capex = nx.sp.nodes.find((n) => n.id === 'capex');
  assert.ok(capex && capex.color === 'f_cost' && near(capex.v / 1e9, 45) && capex.lines.some((x) => /guided ≈ \$45/.test(x[1])), 'capital spending drawn as guided');
  const chg = nx.sp.nodes.find((n) => n.id === 'cash_chg');
  assert.ok(chg && chg.name === 'Drawn from cash' && chg.lines.some((x) => /the balance/.test(x[1])), 'cash drawn down');
  assert.ok(/3 guided lines/.test(nx.spec.subtitle), nx.spec.subtitle);
  assert.ok(nx.sp.nodes.find((n) => n.id === 'revenue').lines.some((x) => /guided \$108B–\$112B/.test(x[1])));
  if (cash === 'uses') assert.ok(nx.sp.links.some((x) => x.s === 'fcf' && x.t === 'capex'), 'free cash flow is now a gap flowing into capital spending');
}
// the low case: revenue at the low end of its range, carried into every line
{
  const opts = { cash: 'uses' };
  const sp0 = F.build(u, opts);
  const spec = { nodes: sp0.nodes, links: sp0.links, end: '2026-09-30', label: 'Q3 2026' };
  const company = { quarters: [Object.assign({}, spec)], years: [] };
  const r = FG.future(spec, g, { company, name: 'Made-up', full: true, case: 'low' });
  const { vals } = F.guidedValues(u, opts, sp0, r, g.items, 'Q4 2026', 'low');
  assert.ok(near(vals[G + 'Revenues'] / 1e9, 108) && near(vals[k('Revenues', P, 'Hw')] / 1e9, 108 * 0.6), 'low case revenue and its parts');
  assert.ok(near(vals['cf>' + G + 'PaymentsToAcquirePropertyPlantAndEquipment'] / 1e9, 45), 'a point guide stays');
}
console.log('flowdetail canvas: ok');
