const { test } = require('node:test'), assert = require('node:assert/strict');
require('../web/bs-blocks.js');
const B = globalThis.FFBSBlocks;

// a classified balance sheet (pipeline/reform.py with "cur" and "cv"): two year ends
const line = (k, side, cls, v, cur, extra) => ({ k, side, cls, name: k, why: '', v, ev: [[], []], cur, ...(extra || {}) });
const R = {
  ends: ['2024-12-31', '2025-12-31'], labels: ['FY2024', 'FY2025'],
  totals: { assets: [180, 200], ca: [60, 80], liab: [105, 115], cl: [40, 45], cse: [75, 85] },
  lines: [
    line('cash', 'a', 'fin', [20, 30], 1), line('sti', 'a', 'fin', [10, null], 1), line('ar', 'a', 'op', [30, 40], 1),
    line('ppe', 'a', 'op', [100, 110], 0),
    line('ap', 'l', 'op', [30, 35], 1), line('ocl', 'l', 'op', [3, 4], 1), line('accr', 'l', 'op', [6, 6], 1),
    line('ltd', 'l', 'fin', [50, 50], 0), line('olease', 'l', 'op', [12, 12], 0, { cv: [2, 2] }), line('oncl', 'l', 'op', [25, 30], 0),
    // what the lines leave: current assets 80 − 70 = 10 (short-term investments went untagged); current liabilities
    // 45 − (35 + 4 + 6 + 2) = −2 (counted twice); non-current 70 − (50 + 10 + 30) = −20 (leases inside "other")
    line('oth_ca', 'a', 'op', [0, 10], 1, { derived: 'ca' }), line('oth_nca', 'a', 'op', [20, 10], 0, { derived: 'nca' }),
    line('oth_cl', 'l', 'op', [-1, -2], 1, { derived: 'cl' }), line('oth_ncl', 'l', 'op', [-20, -20], 0, { derived: 'ncl' }),
  ],
  flows: [{ end: '2025-12-31', revenue: 100, oi: 14, ni: 10, ev: { ni: [0, 'fy', [0]] } }],
};

test('every column adds up to the filing’s totals; a rest counted twice comes out of the section’s “other” lines', () => {
  const m = B.model(R, 1, {});
  assert.equal(m.sumA, 200);
  assert.equal(m.sumL, 115 + 85);
  const l = Object.fromEntries(m.blocks.l.map((b) => [b.k, b]));
  assert.equal(l.ocl.v, 2);                                  // −2 current: from "other current liabilities" first
  assert.equal(l.ocl.less, 2);
  assert.equal(l.accr.v, 6);                                 // accrued untouched while "other" can take it
  assert.equal(l.oncl.v, 10);                                // −20 non-current: out of "other non-current"
  assert.equal(l['olease:c'].v, 2);                          // the lease's current part is a block of its own
  assert.equal(l['olease:c'].cur, 1);
  assert.equal(l.olease.v, 10);
  assert.ok(!m.blocks.l.some((b) => b.derived));             // the negative rests drew nothing
  const cur = m.blocks.l.filter((b) => b.cur === 1).reduce((s, b) => s + b.v, 0);
  assert.equal(cur, 45);                                     // the current section is the tagged current total
  assert.deepEqual(m.notes.map((n) => n.v), [2, 20]);
});

test('a rest that is positive is a hatched block and names the line tagged last year but not this year', () => {
  const m = B.model(R, 1, {});
  const rest = m.blocks.a.find((b) => b.k === 'oth_ca');
  assert.equal(rest.v, 10);
  assert.equal(rest.derived, true);
  assert.deepEqual(rest.gone.map((g) => [g.name, g.v]), [['sti', 10]]);
  assert.equal(B.model(R, 0, {}).blocks.a.find((b) => b.k === 'oth_nca').gone.length, 0);   // no year before
});

test('as filed: current, non-current, equity; operating / financing: operating first; the reader’s classes count', () => {
  const m = B.model(R, 1, {});
  const filed = B.ordered(m, 'filed');
  assert.deepEqual(filed.a.map((b) => b.k), ['cash', 'ar', 'oth_ca', 'ppe', 'oth_nca']);
  assert.deepEqual(filed.l.map((b) => b.k), ['ap', 'ocl', 'accr', 'olease:c', 'ltd', 'olease', 'oncl', 'cse']);
  const op = B.ordered(m, 'opfin');
  assert.deepEqual(op.a.map((b) => b.k), ['ar', 'oth_ca', 'ppe', 'oth_nca', 'cash']);
  const moved = B.ordered(B.model(R, 1, { olease: 'fin' }), 'opfin');
  assert.ok(moved.l.findIndex((b) => b.k === 'olease') > moved.l.findIndex((b) => b.k === 'oncl'));
});

test('negative equity: a deficit block on the assets side, so both columns are the liabilities', () => {
  const N = JSON.parse(JSON.stringify(R));
  N.totals = { assets: [50, 60], liab: [70, 80], cse: [-20, -20] };
  N.lines = [line('ppe', 'a', 'op', [50, 60]), line('ltd', 'l', 'fin', [70, 80])];
  N.lines.forEach((x) => { delete x.cur; });
  const m = B.model(N, 1, {});
  assert.equal(m.deficit, 20);
  assert.equal(m.sumA, 80);
  assert.equal(m.sumL, 80);
  assert.equal(B.ordered(m, 'filed').a.slice(-1)[0].kind, 'deficit');
  assert.equal(m.equity.length, 0);
});

test('an unclassified balance sheet takes a negative rest from any “other” line', () => {
  const U = { ends: ['a', 'b'], labels: ['A', 'B'], totals: { assets: [10, 10], liab: [8, 8], cse: [2, 2] },
    lines: [line('cash', 'a', 'fin', [4, 4]), line('loans', 'a', 'op', [6, 6]), line('deposits', 'l', 'op', [7, 7]), line('oncl', 'l', 'op', [3, 3]),
      line('oth_a', 'a', 'op', [0, 0], undefined, { derived: 'assets' }), line('oth_l', 'l', 'op', [-2, -2], undefined, { derived: 'liab' })] };
  U.lines.forEach((x) => { if (x.cur === undefined) delete x.cur; });
  const m = B.model(U, 1, {});
  assert.equal(m.classified.l, false);
  assert.equal(m.blocks.l.find((b) => b.k === 'oncl').v, 1);
  assert.equal(m.sumL, 10);
});

test('the income statement on the same scale: costs above net income; a loss puts the costs past revenue', () => {
  const c = { quality: { reform: R, drivers: { fy: [{ end: '2025-12-31', cur: { revenue: 100, cor: 60, oi: 14, ni: 10 } }] },
    fy: [{ end: '2025-12-31', wc: { dso: 45.2, dio: 30, dpo: 50 } }] } };
  const inc = B.incomeOf(c, '2025-12-31');
  assert.deepEqual(inc.parts.map((p) => [p.k, p.v]), [['cor', 60], ['opex', 26], ['below', 4], ['ni', 10]]);
  assert.equal(inc.total, 100);
  const loss = B.incomeOf({ quality: { drivers: { fy: [{ end: 'x', cur: { revenue: 50, cor: 35, oi: -10, ni: -18 } }] } } }, 'x');
  assert.equal(loss.loss, true);
  assert.equal(loss.total, 68);
  assert.deepEqual(loss.parts.map((p) => [p.k, p.v]), [['cor', 35], ['opex', 25], ['below', 8]]);
  const big = B.incomeOf({ quality: { drivers: { fy: [{ end: 'x', cur: { revenue: 100, cor: 40, oi: 30, ni: 45 } }] } } }, 'x');
  assert.deepEqual(big.parts.map((p) => p.k), ['cor', 'rest', 'ni']);   // other income above the tax: no negative block
  assert.equal(B.incomeOf({ quality: {} }, 'x'), null);
  const d = B.dupont(R, 1, inc);
  assert.ok(Math.abs(d.turnover * d.margin * d.leverage - d.roe) < 1e-12);
  assert.equal(d.roe, 10 / 80);
});

test('the equity bridge adds up: opening equity + net income − payouts + share-based pay + other = closing equity', () => {
  const c = { quality: { reform: R,
    cap: { fy: [{ end: '2025-12-31', items: { div: -2, buyback: -3, withhold: -0.5, stock: 0.25 }, ev: { div: [[-2, [1, 'fy', [0]]]] } }] },
    fy: [{ end: '2025-12-31', bridge: { items: [['sbc', 1, [2, 'fy', [0]]]] } }] } };
  const b = B.equityBridge(c, 1);
  assert.deepEqual(b.rows.map((r) => r.key), ['ni', 'div', 'buyback', 'sbc', 'stock', 'withhold', 'other']);
  assert.equal(b.open + b.rows.reduce((s, r) => s + r.v, 0), b.close);
  assert.equal(b.rows.find((r) => r.key === 'other').v, 85 - 75 - (10 - 2 - 3 + 1 + 0.25 - 0.5));
  assert.equal(B.equityBridge(c, 0), null);
});

test('IFRS: only the profit for the year (ProfitLoss) is tagged — it is the net income, unless minorities share it', () => {
  const I = JSON.parse(JSON.stringify(R));
  I.flows = [{ end: '2025-12-31', revenue: 100, oi: 14, pl: 10, ev: { pl: [3, 'fy', [0]] } }];
  const c = { quality: { reform: I, drivers: { fy: [{ end: '2025-12-31', cur: { revenue: 100, cor: 60, oi: 14 } }] } } };
  const inc = B.incomeOf(c, '2025-12-31');
  assert.equal(inc.ni, 10);
  assert.equal(inc.basis, 'pl');
  assert.equal(B.dupont(I, 1, inc).roe, 10 / 80);
  const b = B.equityBridge(c, 1);
  assert.equal(b.rows[0].key, 'ni');
  assert.equal(b.rows[0].v, 10);
  assert.deepEqual(b.rows[0].ev.ref, [3, 'fy', [0]]);
  const M = JSON.parse(JSON.stringify(I));
  M.totals.nci = [5, 5];                                     // a minority's share is inside the profit: not the owners'
  const cm = { quality: { reform: M, drivers: c.quality.drivers } };
  assert.ok(!B.equityBridge(cm, 1).rows.some((r) => r.key === 'ni'));
  assert.equal(B.dupont(M, 1, B.incomeOf(cm, '2025-12-31')).roe, 10 / 85);   // profit for the year ÷ all equity
});

test('no “other” line to take a detail counted twice: the lease liabilities give it up before the debt does', () => {
  // Novo Nordisk: IFRS 16 leases tagged on their own and inside borrowings too; the non-current rest is −5
  const N = JSON.parse(JSON.stringify(R));
  N.lines = N.lines.filter((x) => x.k !== 'oncl' && x.k !== 'olease');
  N.lines.push(line('lease', 'l', 'fin', [9, 9], 0, { cv: [1, 1] }));
  N.lines.find((x) => x.k === 'oth_ncl').v = [-5, -5];
  const m = B.model(N, 1, {});
  const l = Object.fromEntries(m.blocks.l.map((b) => [b.k, b]));
  assert.equal(l.ltd.v, 50);                                 // the debt as filed
  assert.equal(l.lease.v, 3);                                // 8 non-current − 5
  assert.equal(l.lease.inside, true);
  assert.equal(l['lease:c'].v, 1);                           // the current part is another section's
  assert.deepEqual(m.notes.find((n) => n.cur === 0).took, [['lease', 5]]);
});

test('blocks too thin to see join one “smaller lines” block of their kind; a hatched rest never does', () => {
  const list = [{ k: 'a', side: 'a', cls: 'op', v: 1, cur: 1 }, { k: 'b', side: 'a', cls: 'op', v: 1, cur: 1 }, { k: 'c', side: 'a', cls: 'fin', v: 1, cur: 1 },
    { k: 'd', side: 'a', cls: 'op', v: 100, cur: 1 }, { k: 'e', side: 'a', cls: 'op', v: 1, cur: 1, derived: true }];
  const out = B.merge(list, 1, 4);
  assert.deepEqual(out.map((b) => b.k), ['small:a', 'c', 'd', 'e']);
  assert.equal(out[0].v, 2);
  assert.equal(out[0].merged.length, 2);
});

test('the Balance sheet tab mounts the blocks before the workbench, which tells them when a class changes', () => {
  const fs = require('fs'), app = fs.readFileSync('web/app.js', 'utf8'), index = fs.readFileSync('web/index.html', 'utf8');
  assert.match(app, /window\.FFBSBlocks\.mount\(body, c, \{ money, evBtn \}\);\s*reformSection\(body, c\);/);
  assert.match(app, /new CustomEvent\('ff:reform'/);
  assert.match(index, /src="bs-blocks.js"/);
  assert.match(index, /href="bs-blocks.css"/);
  assert.ok(index.indexOf('bs-blocks.js') < index.indexOf('src="app.js"'));
});
