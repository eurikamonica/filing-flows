'use strict';
// The quarterly ETF history (etf/weights/<SYM>.json "quarterly" block from app/actual_weights.py) and the sector weights
// the ETF build computes over every long equity line; 13F reports read where the Hub publishes them (data/remote.json)
// and named through the CUSIP map when a report carries no tickers. Offline; no browser.
const assert = require('node:assert/strict');
const A = require('../web/actual-weights.js');
let n = 0;
const eq = (a, b, m) => { assert.deepEqual(a, b, m); n++; };
const near = (a, b, m, tol = 1e-9) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };

const block = {
  unit: 1e-5, dates: ['2025-12-31', '2026-03-31'], acc: ['x1', 'x2'], eq: [0.99, 0.98], n: [500, 498],
  names: ['NVDA', 'AAPL'], w: [[30000, 20000], [35000, 0]],
  sectors: ['technology', 'energy', 'other'], sw: [[50000, 0, 49000], [40000, 10000, 48000]]
};

(async () => {
  // the columns back into snapshots: names not held that quarter left out, sector weights kept, reported dates
  const q = A.quarterlySnapshots(block);
  eq(q.map((s) => s.date), ['2025-12-31', '2026-03-31'], 'quarter-end dates');
  eq(q[0].positions, [['NVDA', 0.3], ['AAPL', 0.2]], 'weights in hundred-thousandths');
  eq(q[1].positions, [['NVDA', 0.35]], 'a name not held is left out');
  near(q[1].sector_weights.energy, 0.1, 'sector weights');
  eq([q[0].partial, q[0].date_basis, q[0].accession], [true, 'reported', 'x1'], 'partial, reported, accession');
  near(q[0].equity_weight_covered, 0.99, 'the whole portfolio\'s equity weight, not just the names listed');
  eq(A.quarterlySnapshots(null), [], 'no block');

  // a kept full snapshot on a quarter-end: its own positions, the quarter's sector weights and a reported date
  const hist = { quarterly: block, snapshots: [{ date: '2026-03-31', date_basis: 'unknown', source: 'SEC N-PORT', accession: 'x2',
    positions: [['NVDA', 0.35], ['XOM', 0.1], ['JPM', 0.05]], sector_weights: { technology: 0.35, energy: 0.1, financials: 0.05 } }] };
  const all = A.snapshots(hist, null);
  eq(all.length, 2, 'one snapshot a date');
  eq(all[1].positions.map((p) => p[0]), ['NVDA', 'XOM', 'JPM'], 'the full snapshot\'s names');
  near(all[1].sector_weights.other, 0.48, 'the quarter\'s sector weights (every line), not the kept snapshot\'s');
  eq(all[1].date_basis, 'reported', 'the N-PORT report date is a reported date');

  // the studio's views on it: sector areas from the sector weights, company areas from the names with Other the rest
  const meta = { cos: [['NVDA', 'NVIDIA', 'technology'], ['AAPL', 'Apple', 'technology']] };
  const api = { hub: 'h/', rankMeta: async () => meta, json: async (u) => (u.endsWith('/weights/IVV.json') ? { quarterly: block, snapshots: [] } : null) };
  const out = () => ({ notes: new Set(), series: [] });
  const sec = out();
  await A.build({ aw: 'etf', ah: 'IVV', style: 'stack', an: '12' }, sec, api);
  eq(sec.kind, 'sectors', 'sector areas');
  near(sec.series.find((s) => s.key === 'technology').v[0], 0.5, 'technology from the sector weights');
  near(sec.series.find((s) => s.key === 'other').v[1], 0.48 + 0.02, 'other: unclassified lines plus what is not equity');
  near(sec.series.reduce((a, s) => a + s.v[1], 0), 1, 'a 100% area each date');
  ok([...sec.notes].some((x) => /N-PORT reports/.test(x)), 'the quarterly source is named');
  const co = out();
  await A.build({ aw: 'etf', ah: 'IVV', style: 'companies', an: '12' }, co, api);
  near(co.series.find((s) => s.key === 'AAPL').v[1], 0, 'not held: zero, not missing');
  near(co.series.find((s) => s.key === 'other').v[0], 0.5, 'Other: everything but the names');
  const ch = out();
  await A.build({ aw: 'etf', ah: 'IVV', style: 'changes', ag: 'sector', an: '12' }, ch, api);
  near(ch.series.find((s) => s.key === 'energy').v[0], 0.1, 'sector change in points');

  // a report whose equity lines add to a little over its net assets: scaled for the 100% chart, with a note
  const over = { ...block, sw: [[50000, 0, 50030], [40000, 10000, 48000]] };
  const oapi = { ...api, json: async (u) => (u.endsWith('/weights/IVV.json') ? { quarterly: over, snapshots: [] } : null) };
  const o = out();
  await A.build({ aw: 'etf', ah: 'IVV', style: 'stack', an: '12' }, o, oapi);
  near(o.series.reduce((a, s) => a + s.v[0], 0), 1, 'scaled to 100%', 1e-9);
  ok([...o.notes].some((x) => /more than their net assets/.test(x)), 'the scaling is noted');
  const far = { ...block, sw: [[90000, 0, 20000], [40000, 10000, 48000]] };
  await assert.rejects(A.build({ aw: 'etf', ah: 'IVV', style: 'stack' }, out(), { ...api, json: async (u) => (u.endsWith('/weights/IVV.json') ? { quarterly: far, snapshots: [] } : null) }), /exceed 100%/);
  n++;

  // a sponsor file's '-' is no sector: the site's companies, then the ETF build's sector map
  const spy = { snapshots: [{ date: '2026-10-30', date_basis: 'observed', source: 'sponsor holdings file', positions: [['NVDA', 0.08], ['FITB', 0.01]], sectors: { NVDA: '-', FITB: '-' } }] };
  const sapi = { hub: 'h/', rankMeta: async () => meta, json: async (u) => (u.endsWith('/weights/SPY.json') ? spy : u.endsWith('etf/sectors.json') ? { sectors: { FITB: 'financials' } } : null) };
  const s2 = out();
  await A.build({ aw: 'etf', ah: 'SPY', style: 'bars', an: '5' }, s2, sapi);
  eq(s2.series.find((s) => s.key === 'NVDA').sec, 'technology', 'NVDA from the site\'s companies');
  eq(s2.series.find((s) => s.key === 'FITB').sec, 'financials', 'FITB from the ETF build\'s map');

  // 13F: the shards where data/remote.json says, positions without tickers named through the CUSIP map
  const seen = [];
  const mapi = { hub: 'd/', rankMeta: async () => meta, json: async (u) => {
    seen.push(u);
    if (u === 'd/remote.json') return { base: 'https://raw.example/x/', prefixes: ['shards/holdings/', 'shards/npx/'] };
    if (u === 'd/market/cusip-tickers.json') return { '037833100': 'AAPL' };
    if (u.endsWith('shards/holdings/1067983.json')) return { name: 'Berkshire', snapshots: [{ period: '2026-06-30', complete: true, total_usd: 100, positions_shard: 'shards/holdings/1067983-2026-06-30.json' },
      { period: '2026-03-31', complete: true, total_usd: 100, positions_shard: '../../etc/passwd.json' }] };
    if (u.endsWith('1067983-2026-06-30.json')) return [{ cusip: '037833100', value_usd: 60, put_call: 'NONE' }, { cusip: '999999999', value_usd: 40, put_call: 'NONE' }];
    return null;
  } };
  await assert.rejects(A.build({ aw: '13f', ac: '1067983', style: 'bars' }, out(), mapi), /Missing positions for 2026-03-31/);
  n++;
  ok(seen.includes('https://raw.example/x/shards/holdings/1067983.json'), 'the manager file read where remote.json says');
  ok(!seen.some((u) => u.includes('passwd')), 'a positions path that leaves the folder is not read');
  const mapi2 = { ...mapi, json: async (u) => (u.endsWith('shards/holdings/1067983.json') ? { name: 'Berkshire', snapshots: [{ period: '2026-06-30', complete: true, total_usd: 100, positions_shard: 'shards/holdings/1067983-2026-06-30.json' }] } : mapi.json(u)) };
  const m = out();
  await A.build({ aw: '13f', ac: '1067983', style: 'bars', an: '5' }, m, mapi2);
  near(m.series.find((s) => s.key === 'AAPL').v[0], 0.6, 'AAPL named by its CUSIP');
  ok(!m.sub.includes('date basis unverified'), 'a 13F report period is a reported date');
  console.log(`Quarterly ETF history and 13F weights: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
function ok(v, m) { assert.ok(v, m); n++; }
