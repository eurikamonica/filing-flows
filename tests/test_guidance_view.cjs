// web/guidance.js: the Sankey's "Show guidance" view — guided lines at their midpoint with a range, the rest at the base
// period's shares, flows that add up, its own colours, change words, and no drawing when the guidance cannot be used.
const assert = require('assert');
const FG = require('../web/guidance.js');

const L = (name, v, share) => [['name', name], ['val', `$${v}B${share ? ' · ' + share : ''}`]];
const base = {
  label: 'Q2 FY27', end: '2026-07-26', period: 'q',
  nodes: [
    { id: 'L:a', col: 0, color: 'rev', v: 60, name: 'Data Center', lines: L('Data Center', 60) },
    { id: 'L:b', col: 0, color: 'rev', v: 40, name: 'Gaming', lines: L('Gaming', 40) },
    { id: 'revenue', col: 1, color: 'rev', v: 100, name: 'Revenue', lines: [['big', 'Revenue'], ['val', '$100B']] },
    { id: 'gp', col: 2, color: 'profit', v: 70, name: 'Gross profit', lines: L('Gross profit', 70, '70% of revenue') },
    { id: 'cor', col: 2, color: 'cost', v: 30, name: 'Cost of revenue', lines: L('Cost of revenue', 30, '30% of revenue') },
    { id: 'nonop_in', col: 3, color: 'profit', v: 2, name: 'Other income, net', lines: L('Other income, net', 2) },
    { id: 'oi', col: 3, color: 'profit', v: 50, name: 'Operating profit', lines: L('Operating profit', 50, '71% of gross profit') },
    { id: 'opex', col: 3, color: 'cost', v: 20, name: 'Operating expenses', lines: L('Operating expenses', 20, '29% of gross profit') },
    { id: 'pretax', col: 4, color: 'profit', v: 52, name: 'Pre-tax earnings', lines: L('Pre-tax earnings', 52) },
    { id: 'I:rd', col: 4, color: 'cost', v: 15, name: 'R&D', lines: L('R&D', 15, '75% of opex') },
    { id: 'I:sga', col: 4, color: 'cost', v: 5, name: 'SG&A', lines: L('SG&A', 5, '25% of opex') },
    { id: 'net', col: 5, color: 'profit', v: 44, name: 'Net earnings', lines: L('Net earnings', 44, '85% of pre-tax') },
    { id: 'tax', col: 5, color: 'cost', v: 8, name: 'Income tax', lines: L('Income tax', 8, '15% of pre-tax') },
    { id: 'ocf', col: 6, color: 'profit', v: 40, name: 'Operating cash flow', lines: L('Operating cash flow', 40) },
    { id: 'wc_out', col: 6, color: 'noncash', v: 4, name: 'Working capital', lines: L('Working capital', 4) },
  ],
  links: [['L:a', 'revenue', 60, 'rev'], ['L:b', 'revenue', 40, 'rev'], ['revenue', 'gp', 70, 'profit'], ['revenue', 'cor', 30, 'cost'],
    ['gp', 'oi', 50, 'profit'], ['gp', 'opex', 20, 'cost'], ['oi', 'pretax', 50, 'profit'], ['nonop_in', 'pretax', 2, 'profit'],
    ['opex', 'I:rd', 15, 'cost'], ['opex', 'I:sga', 5, 'cost'], ['pretax', 'net', 44, 'profit'], ['pretax', 'tax', 8, 'cost'],
    ['net', 'ocf', 40, 'profit'], ['net', 'wc_out', 4, 'noncash']].map(([s, t, v, color]) => ({ s, t, v, color, q: v * 0.9, y: v * 0.6 })),
};
const company = { periods: { q: [{ end: '2026-07-26', label: 'Q2 FY27', q: 2, fy: 2027 }] }, quarters: [base] };
const g = {
  filed: '2026-08-26', form: '8-K', tags: ['raised', 'narrowed'], label: 'raised', items: [
    { metric: 'revenue', basis: '', period: 'Q3 FY2027', unit: 'usd', lo: 108, hi: 112, change: 'raised', range: 'narrowed', prior: { lo: 100, hi: 108, src: 'release' }, quote: 'Revenue is expected to be $110 billion.' },
    { metric: 'gross_margin', basis: 'GAAP', period: 'Q3 FY2027', unit: 'pct', lo: 74, hi: 76, change: 'reaffirmed', range: 'widened' },
    { metric: 'gross_margin', basis: 'non-GAAP', period: 'Q3 FY2027', unit: 'pct', lo: 90, hi: 92 },
    { metric: 'opex', basis: 'GAAP', period: 'Q3 FY2027', unit: 'usd', lo: 22, hi: 22, approx: true, change: 'lowered', prior: { lo: 24, hi: 24, src: 'earlier release', filed: '2026-05-20' } },
    { metric: 'tax_rate', basis: 'GAAP', period: 'FY2027', unit: 'pct', lo: 14, hi: 16, change: 'reaffirmed' },
    { metric: 'eps', basis: 'non-GAAP', period: 'FY2027', unit: 'ps', lo: 7.1, hi: 7.3, change: 'raised' },
    { metric: 'revenue', basis: '', period: 'Q3 FY2027', unit: 'usd', lo: 50, hi: 50, scope: 'segment' },
  ],
};

const f = FG.future(base, g, { company, name: 'Example' });
assert.ok(!f.error, f.error);
const N = new Map(f.nodes.map((n) => [n.id, n]));
const near = (a, b, m) => assert.ok(Math.abs(a - b) < 1e-6, `${m}: ${a} vs ${b}`);
near(N.get('revenue').v, 110, 'revenue at the guided midpoint');
near(N.get('gp').v, 82.5, 'GAAP gross margin 75% × revenue, not the adjusted 91%');
near(N.get('cor').v, 27.5, 'cost of revenue is the rest');
near(N.get('opex').v, 22, 'guided operating expenses');
near(N.get('oi').v, 60.5, 'operating profit = gross profit − opex');
near(N.get('I:rd').v, 16.5, 'R&D keeps its 75% of opex');
near(N.get('L:a').v, 66, 'segments keep their mix');
near(N.get('nonop_in').v, 2, 'other income not guided: as in the base period');
near(N.get('tax').v, 62.5 * 0.15, 'the full-year tax rate applied to the quarter');
near(N.get('net').v, 62.5 * 0.85, 'net earnings = pre-tax − tax');
assert.ok(!N.has('ocf') && !N.has('wc_out'), 'the cash-flow part is not guided: left out');
// flows add up at every node
const sum = (id, k) => f.links.filter((l) => l[k] === id).reduce((a, l) => a + l.v, 0);
f.nodes.forEach((n) => {
  const i = sum(n.id, 't'), o = sum(n.id, 's');
  if (i) near(i, n.v, `inflows of ${n.id}`);
  if (o) near(o, n.v, `outflows of ${n.id}`);
});
near(f.links.find((l) => l.s === 'revenue' && l.t === 'gp').q, 70, 'each band carries its size in the reported quarter (the comparison strips)');
// colours: only the guided lines change colour (violet / indigo / plum); the rest keep the standard grey, green and red
assert.strictEqual(N.get('revenue').color, 'f_rev');
assert.strictEqual(N.get('gp').color, 'f_profit');
assert.strictEqual(N.get('opex').color, 'f_cost');
assert.strictEqual(N.get('I:rd').color, 'cost');
assert.strictEqual(N.get('oi').color, 'profit');
assert.strictEqual(N.get('L:a').color, 'rev');
assert.ok(f.nodes.every((n) => (n.gnote.guided ? /^f_/ : /^(rev|profit|cost|noncash)$/).test(n.color)), 'guided lines violet, the rest standard');
assert.strictEqual(f.links.find((l) => l.t === 'gp').color, 'f_profit');
assert.strictEqual(f.links.find((l) => l.t === 'oi').color, 'profit');
assert.strictEqual(f.bg, '#fbfaff');
// ranges and change words
assert.deepStrictEqual(N.get('revenue').range, [108, 112]);
near(N.get('gp').range[0], 74 / 100 * 110, 'gross profit range from the margin range');
const rl = N.get('revenue').lines.map((l) => l[1]).join(' | ');
assert.ok(/guided \$108K?/.test(rl) || /guided/.test(rl), rl);
assert.ok(rl.includes('▲ raised') && rl.includes('→← narrowed') && rl.includes('from'), rl);
const gl = (n) => n.lines.find((l) => /^g(up|dn|nt)$/.test(l[0])), al = (n) => n.lines.find((l) => l[0] === 'gas');
assert.strictEqual(gl(N.get('revenue'))[0], 'gup');
assert.strictEqual(gl(N.get('opex'))[0], 'gdn');
assert.ok(gl(N.get('gp'))[1].includes('←→ widened') && gl(N.get('gp'))[1].includes('midpoint kept'), gl(N.get('gp'))[1]);
assert.ok(al(N.get('I:rd'))[1].startsWith('assumed: 75% of opex in Q2 FY27'), al(N.get('I:rd'))[1]);
assert.ok(f.footer.join(' ').includes('adj. EPS (FY2027) $7.10–$7.30 ▲ raised'), 'non-GAAP figures are listed, not drawn');
assert.ok(f.footer.join(' ').includes('Revenue, a segment (Q3 FY2027)'), 'a segment figure is listed as such, not drawn');
assert.ok(f.title.includes('Q3 FY2027'), f.title);
assert.ok(FG.noteHTML(N.get('revenue'), g).includes('Revenue is expected to be $110 billion.'));
assert.ok(FG.noteHTML(N.get('I:rd'), g).includes('Not guided'));

// compared with the quarter just reported and with the same quarter a year earlier — in the historical comparison's
// grammar: links carry q (reported quarter) and y (year-ago quarter) for the dark strips and hatching, nodes a Δ line
// (Δ = scale + mix) with a coloured ● (teal higher, orange lower), and an "As guided vs …" callout
const K = 1e9;
const scaled = (spec) => Object.assign(JSON.parse(JSON.stringify(spec)), {
  nodes: spec.nodes.map((n) => Object.assign({}, n, { v: n.v * K })), links: spec.links.map((l) => Object.assign({}, l, { v: l.v * K })) });
const bB = scaled(base);
const ago = scaled(base);
ago.label = 'Q3 FY26'; ago.end = '2025-10-26';
ago.nodes.forEach((n) => { n.v = n.v / 2; });
ago.links.forEach((l) => { l.v = l.v / 2; });
ago.nodes.find((n) => n.id === 'opex').v = 30 * K;                // a line that was bigger a year ago
const gB = JSON.parse(JSON.stringify(g));
gB.items.forEach((it) => { if (it.unit === 'usd') { it.lo *= K; it.hi *= K; if (it.prior) { it.prior.lo *= K; it.prior.hi *= K; } } });
const co3 = { periods: { q: [{ end: '2026-07-26', q: 2, fy: 2027 }, { end: '2025-10-26', q: 3, fy: 2026 }] }, quarters: [bB, ago] };
const fc = FG.future(bB, gB, { company: co3, name: 'Example' });
assert.ok(!fc.error, fc.error);
const C = new Map(fc.nodes.map((n) => [n.id, n]));
assert.strictEqual(fc.compare.vs, 'Q2 FY27');
assert.strictEqual(fc.compare_y.vs, 'Q3 FY26');
assert.strictEqual(fc.compare.title, 'Example: Q3 FY2027 as guided vs Q2 FY27');
assert.strictEqual(fc.compare_y.heading, 'As guided vs Q3 FY26 (a year earlier)');
const rg = fc.links.find((l) => l.s === 'revenue' && l.t === 'gp');
near(rg.q, 70 * K, 'reported-quarter band');
near(rg.y, 35 * K, 'year-ago band');
assert.deepStrictEqual(C.get('revenue').cmp, ['cup', '● Δ +$10.0B']);
assert.deepStrictEqual(C.get('gp').cmp, ['cup', '● Δ +$12.5B · scale +7.0 · mix +5.5'], 'Δ = scale + mix against the parent, as in history');
assert.deepStrictEqual(C.get('opex').cmp_y, ['cdn', '● Δ −$8.0B · scale +40.7 · mix −48.7'], 'opex 22 vs 30 a year ago: lower, in orange');
assert.ok(C.get('revenue').lines.some((l) => l[0] === 'mut' && l[1] === 'Y/Y +120% · Q/Q +10%'), 'the Y/Y · Q/Q line of the standard charts');
assert.strictEqual(C.get('gp').lines[1][1], '$82.5B · 75% of revenue');
assert.deepStrictEqual(fc.compare.bullets.slice(0, 2), ['Revenue $110.0B as guided vs $100.0B in Q2 FY27: +$10.0B (+10%).',
  'Gross margin 75.0% vs 70.0% in Q2 FY27 (+5.0 pts), from the guided margin.']);
assert.ok(fc.compare.bullets.some((b) => b.startsWith('Operating profit $60.5B vs $50.0B: +$10.5B (+21%)')), fc.compare.bullets.join(' / '));
assert.ok(fc.compare.bullets.some((b) => b.startsWith('Largest guided change after revenue: Gross profit +$12.5B')), fc.compare.bullets.join(' / '));
assert.ok(!FG.future(base, g, { company }).compare_y, 'no year-ago quarter on file: only vs current');
assert.strictEqual(FG.future(base, g, { company }).links.every((l) => l.y == null), true);

// words for every change kind
assert.deepStrictEqual(FG.words({ change: 'raised', range: 'narrowed' }), ['▲ raised', '→← narrowed']);
assert.deepStrictEqual(FG.words({ change: 'lowered', range: 'widened' }), ['▼ lowered', '←→ widened']);
assert.deepStrictEqual(FG.words({ change: 'reaffirmed', range: 'narrowed' }), ['→← narrowed', 'midpoint kept']);
assert.deepStrictEqual(FG.words({ change: 'initiated' }), ['✦ initiated']);
assert.deepStrictEqual(FG.words({ change: 'new' }), []);
assert.strictEqual(FG.range({ unit: 'usd', lo: 290e6, hi: 290e6, bound: 'min' }), 'at least $290M');
assert.strictEqual(FG.range({ unit: 'usd', lo: 9.2e9, hi: 9.2e9, approx: true }), '≈ $9.20B');

// implied fourth quarter: full-year guidance minus three reported quarters
const q3 = Object.assign({}, base, { label: 'Q3 FY27', end: '2026-10-25' });
const co2 = { periods: { q: [{ end: '2026-10-25', q: 3, fy: 2027 }, { end: '2026-07-26', q: 2, fy: 2027 }, { end: '2026-04-26', q: 1, fy: 2027 }] },
  quarters: [q3, Object.assign({}, base, { end: '2026-07-26' }), Object.assign({}, base, { end: '2026-04-26' })] };
const fy = FG.future(q3, { filed: '2026-11-20', items: [{ metric: 'revenue', basis: '', period: 'FY2027', unit: 'usd', lo: 400, hi: 420, change: 'raised' }] }, { company: co2 });
assert.ok(!fy.error, fy.error);
near(fy.nodes.find((n) => n.id === 'revenue').v, 110, 'implied Q4 = 410 − 3 × 100');
assert.strictEqual(fy.kind, 'implied');
assert.ok(fy.footer.some((x) => x.includes('minus the three reported quarters')));

// not drawn: nothing on file, only non-GAAP revenue, another period, a misread scale
assert.ok(FG.future(base, null).error);
assert.ok(FG.future(base, { items: [{ metric: 'revenue', basis: 'non-GAAP', period: 'Q3 FY2027', unit: 'usd', lo: 108, hi: 112 }] }, { company }).error);
assert.ok(FG.future(base, { items: [{ metric: 'revenue', basis: '', period: 'Q1 FY2028', unit: 'usd', lo: 108, hi: 112 }] }, { company }).error);
assert.ok(FG.future(base, { items: [{ metric: 'revenue', basis: '', period: 'Q3 FY2027', unit: 'usd', lo: 1080, hi: 1120 }] }, { company }).error);

// "vs guidance" on a reported quarter: Q3 FY27 as reported against the guidance given in the Q2 release (Aug 26, before
// the quarter ended); the guided figures projected from Q2 as the guidance view does; only the lines guidance fixes
{
  const act = JSON.parse(JSON.stringify(base));
  Object.assign(act, { label: 'Q3 FY27', end: '2026-10-25' });
  const V = { 'L:a': 70, 'L:b': 44, revenue: 114, gp: 84, cor: 30, oi: 61, opex: 23, nonop_in: 2, pretax: 63, 'I:rd': 17, 'I:sga': 6, net: 54, tax: 9, ocf: 50, wc_out: 4 };
  act.nodes.forEach((n) => { n.v = V[n.id]; });
  act.links.forEach((l) => { l.v = l.t in V && ['revenue', 'opex', 'net'].includes(l.s) || l.s.startsWith('L:') ? (l.s.startsWith('L:') ? V[l.s] : V[l.t]) : V[l.t]; });
  act.links.find((l) => l.s === 'oi').v = 61; act.links.find((l) => l.s === 'nonop_in').v = 2;
  const co3 = { periods: { q: [{ end: '2026-10-25', q: 3, fy: 2027 }, { end: '2026-07-26', q: 2, fy: 2027 }] }, quarters: [act, base] };
  const later = { filed: '2026-11-19', accession: 'later', items: [{ metric: 'revenue', basis: '', period: 'Q3 FY2027', unit: 'usd', lo: 114, hi: 114 }] };   // the result, after the quarter: not a guide
  const r = FG.versus(act, { g: later, hist: { releases: [later, Object.assign({ accession: 'g' }, g)] } }, { company: co3, name: 'Example' });
  assert.ok(!r.error, r.error);
  const M = new Map(r.nodes.map((n) => [n.id, n]));
  near(M.get('revenue').g, 110, 'held to the guided midpoint of the release before the quarter ended');
  assert.deepStrictEqual(M.get('revenue').grange, [108, 112]);
  near(M.get('gp').g, 82.5, 'gross profit: guided GAAP margin × guided revenue');
  near(M.get('cor').g, 27.5, 'cost of revenue follows from the two guided lines');
  near(M.get('opex').g, 22, 'guided operating expenses');
  near(M.get('oi').g, 60.5, 'operating profit follows: gross profit − opex');
  assert.ok(!M.get('I:rd').g && !M.get('L:a').g && !M.get('nonop_in').g, 'lines guidance does not fix stay plain');
  assert.ok(M.get('pretax').g == null && M.get('tax').g == null && M.get('net').g == null, 'pre-tax depends on unguided other income: not compared, nor tax');
  const lk = (s, t) => r.links.find((l) => l.s === s && l.t === t);
  near(lk('revenue', 'gp').g, 82.5, 'the band into gross profit carries its guided size');
  near(lk('gp', 'oi').g, 60.5, 'the remainder band');
  assert.ok(lk('L:a', 'revenue').g == null && lk('opex', 'I:rd').g == null, 'segment and opex-split bands are not fixed by guidance');
  assert.strictEqual(M.get('revenue').cmp_g[0], 'cup', 'revenue above the range: better');
  assert.ok(/above the range/.test(M.get('revenue').cmp_g[1]) && /\+3\.6%/.test(M.get('revenue').cmp_g[1]), M.get('revenue').cmp_g[1]);
  assert.strictEqual(M.get('opex').cmp_g[0], 'cdn', 'opex above its guide: worse (a cost)');
  assert.strictEqual(M.get('cor').cmp_g[0], 'cnt', 'a cost guidance only implies moves with revenue: neutral');
  assert.ok(r.compare_g.vs.includes('Aug 26, 2026') && /Q3 FY27 vs guidance/.test(r.compare_g.title), r.compare_g.title);
  assert.ok(/^Revenue .*\(\+3\.6%\) — above the range/.test(r.compare_g.bullets[0]) && r.compare_g.bullets.some((b) => /Gross margin 73\.7% vs guided 74%–76%/.test(b)), r.compare_g.bullets.join(' | '));
  assert.ok(/dense-dot/.test(r.compare_g.footer));
  // the bridge from guidance to the result: down to operating profit (pre-tax rests on other income nobody guided), in
  // steps that add up: revenue at the expected 75% gross margin, the margin on the reported revenue, operating expenses
  const br = r.compare_g.bridge;
  assert.ok(br && br.end === 'oi', JSON.stringify(br));
  near(br.start, 60.5, 'expected operating profit');
  near(br.fin, 61, 'reported operating profit');
  const st = Object.fromEntries(br.steps.map((x) => [x.id, x.v]));
  near(st.revenue, 4 * 0.75, 'revenue: 4 more at the expected gross margin');
  near(st.gp, 84 - 114 * 0.75, 'gross margin 73.7% vs 75% on the reported revenue');
  near(st.opex, -1, 'operating expenses 1 above their guide');
  assert.deepStrictEqual(br.guided, ['revenue', 'gross margin', 'operating expenses'], 'the tax rate is not part of a bridge to operating profit');
  // not held: no guide for it before it ended, or no base period
  assert.ok(FG.versus(act, { hist: { releases: [later] } }, { company: co3 }).error);
  assert.ok(FG.versus(act, { g: Object.assign({ accession: 'g' }, g) }, { company: { periods: co3.periods, quarters: [act] } }).error);
}
// scenarios: the low case takes the end of every range that leaves less profit, the high case the other end
{
  assert.strictEqual(FG.pointOf({ lo: 1, hi: 3 }, 'revenue'), 2);
  assert.strictEqual(FG.pointOf({ lo: 1, hi: 3 }, 'revenue', 'low'), 1);
  assert.strictEqual(FG.pointOf({ lo: 1, hi: 3 }, 'opex', 'low'), 3);
  assert.strictEqual(FG.pointOf({ lo: 1, hi: 3 }, 'capex', 'high'), 1);
  assert.strictEqual(FG.pointOf({ lo: 5, hi: null }, 'revenue', 'high'), 5);
  const lo = FG.future(base, g, { company, name: 'Example', case: 'low' }), hi = FG.future(base, g, { company, name: 'Example', case: 'high' });
  const NL = new Map(lo.nodes.map((n) => [n.id, n])), NH = new Map(hi.nodes.map((n) => [n.id, n]));
  near(NL.get('revenue').v, 108, 'low case: revenue at the low end');
  near(NL.get('gp').v, 108 * 0.74, 'low case: the low gross margin');
  near(NL.get('tax').v, (108 * 0.74 - 22 + 2) * 0.16, 'low case: the high tax rate');
  near(NH.get('revenue').v, 112, 'high case: revenue at the high end');
  near(NH.get('gp').v, 112 * 0.76, 'high case: the high gross margin');
  near(NH.get('tax').v, (112 * 0.76 - 22 + 2) * 0.14, 'high case: the low tax rate');
  assert.ok(/\(low case\)/.test(lo.title) && lo.case === 'low' && /less profitable end/.test(lo.subtitle), lo.title);
  assert.ok(/leaves less profit/.test(lo.footer[0]) && /at its midpoint/.test(f.footer[0]));
}
console.log('guidance view: ok');
