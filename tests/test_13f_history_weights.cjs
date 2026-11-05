// A 13F manager's weights video (web/actual-weights.js, kind "actual", source "13f"): the long equity book as 100%
// (options left out, with a note), every line named — by its ticker, through either CUSIP map, else by its issuer —
// and the quarters before the Hub's own from SEC's 13F data sets (holders_history.py: public/m/<CIK>.json).
'use strict';
const assert = require('node:assert/strict');
const A = require('../web/actual-weights.js');
const HUB = 'disclosures/data/', RAW = 'https://raw.example/x/', HH = 'https://raw.example/h/';
const files = {
  [HUB + 'remote.json']: { base: RAW, prefixes: ['shards/holdings/'], holders: HH },
  [HUB + 'market/cusip-tickers.json']: { '037833100': 'AAPL' },
  [HH + 'cusips.json']: { cusips: { G5960L103: 'MDT' } },
  [RAW + 'shards/holdings/1423053.json']: { name: 'CITADEL ADVISORS LLC', snapshots: [
    { period: '2024-12-31', filed: '2025-02-14', complete: true, total_usd: 1000, positions_shard: 'shards/holdings/1423053-2024-12-31.json' },
    { period: '2025-03-31', filed: '2025-05-15', complete: true, total_usd: 1000, positions_shard: 'shards/holdings/1423053-2025-03-31.json' }] },
  [RAW + 'shards/holdings/1423053-2024-12-31.json']: [
    { cusip: '037833100', issuer: 'APPLE INC', value_usd: 100, put_call: 'NONE', share_type: 'SH' },
    { cusip: 'G5960L103', issuer: 'MEDTRONIC PLC', value_usd: 50, put_call: 'NONE', share_type: 'SH' },
    { cusip: '42809H107', issuer: 'HESS CORP', value_usd: 50, put_call: 'NONE', share_type: 'SH' },
    { cusip: '037833100', issuer: 'APPLE INC', value_usd: 500, put_call: 'CALL', share_type: 'SH' },
    { cusip: '037833100', issuer: 'APPLE INC', value_usd: 290, put_call: 'PUT', share_type: 'SH' },
    { cusip: '037833AB6', issuer: 'APPLE INC NOTE', value_usd: 10, put_call: 'NONE', share_type: 'PRN' }],
  [RAW + 'shards/holdings/1423053-2025-03-31.json']: [
    { cusip: '037833100', issuer: 'APPLE INC', value_usd: 120, put_call: 'NONE', share_type: 'SH' },
    { cusip: '42809H107', issuer: 'HESS CORP', value_usd: 80, put_call: 'NONE', share_type: 'SH' },
    { cusip: '037833100', issuer: 'APPLE INC', value_usd: 800, put_call: 'CALL', share_type: 'SH' }],
  [HH + 'm/1423053.json']: { cik: 1423053, name: 'Citadel Advisors', filer: 'CITADEL ADVISORS LLC', periods: ['2024-06-30', '2024-09-30', '2024-12-31'],
    usd: [400, 500, 999], lines: [3000, 3100, 3200], options: [[1, 2], [3, 4], [5, 6]],
    sectors: [{ technology: 200, health: 80 }, { technology: 250, health: 100 }, { technology: 1 }],
    unit: 1e-5, top: [[['AAPL', 50000], ['~G5960L', 20000]], [['AAPL', 50000], ['GOOG', 10000], ['~G5960L', 20000]], [['AAPL', 100000]]],
    names: { AAPL: 'Apple Inc.', '~G5960L': 'Medtronic' } },
};
const api = { hub: HUB, json: async (u) => (u in files ? JSON.parse(JSON.stringify(files[u])) : null),
  rankMeta: async () => ({ cos: [['AAPL', 'Apple', 'technology'], ['MDT', 'Medtronic', 'health'], ['GOOGL', 'Alphabet', 'technology']] }) };
const out = () => ({ notes: new Set(), series: [] });
(async () => {
  const src = await A.disclosedSource({ aw: '13f', ac: '1423053' }, api);
  assert.deepEqual(src.snapshots.map((s) => s.date), ['2024-06-30', '2024-09-30', '2024-12-31', '2025-03-31'], 'the data sets before the Hub\'s first quarter, the Hub\'s after');
  const q4 = src.snapshots[2];
  assert.equal(q4.source, 'SEC 13F');
  const w = Object.fromEntries(q4.positions);
  assert.equal(w.AAPL, 0.5, 'Apple: 100 of the 200 in shares — not of the 1,000 reported with the options');
  assert.equal(w.MDT, 0.25, 'Medtronic named through the data sets\' CUSIP map');
  assert.equal(w['~42809H'], 0.25, 'Hess: no ticker in either map — kept, under its issuer');
  assert.equal(src.labels['~42809H'], 'Hess');
  const h2 = Object.fromEntries(src.snapshots[1].positions);
  assert.equal(h2.AAPL, 0.5);
  assert.equal(h2.GOOGL, 0.1, 'a class of share as its company (GOOG as GOOGL)');
  assert.equal(src.snapshots[1].sector_weights.health, 0.2);
  assert.match(src.note, /2024-06-30 to 2024-09-30 \(2 quarters\): SEC's Form 13F data sets — each quarter's 100 largest[^;]*; from 2024-12-31: each 13F as filed/);
  assert.match(src.note, /Options in its 2025-03-31 13F: puts \$0M and calls \$0M[^.]*80% of the reported/);
  assert.equal(src.basis, 'Share of the long equity book (13F)');

  // company areas: the issuer's band named, the rest "All other holdings"
  const area = out();
  await A.build({ aw: '13f', ac: '1423053', style: 'companies', an: '3' }, area, api);
  assert.equal(area.kind, 'sectors');
  assert.equal(area.grid.length, 4);
  const hess = area.series.find((s) => s.key === '~42809H');
  assert.ok(hess && hess.label === 'Hess' && hess.name === 'Hess', 'the issuer\'s band: ' + JSON.stringify(hess && [hess.label, hess.name]));
  assert.equal(area.series.find((s) => s.key === 'other').label, 'All other holdings');
  for (let i = 0; i < 4; i++) assert.ok(Math.abs(area.series.reduce((a, s) => a + s.v[i], 0) - 1) < 1e-9, 'every quarter adds up to 100%');

  // sector areas: the data sets' quarters by their sectors over every line, the Hub's by each line's company
  const sec = out();
  await A.build({ aw: '13f', ac: '1423053', style: 'stack' }, sec, api);
  const tech = sec.series.find((s) => s.key === 'technology'), health = sec.series.find((s) => s.key === 'health');
  assert.equal(tech.v[0], 0.5);
  assert.equal(health.v[0], 0.2);
  assert.equal(health.v[2], 0.25, 'the Hub\'s quarter: Medtronic\'s line');
  assert.equal(sec.series.find((s) => s.key === 'other').v[2], 0.25, 'Hess: no sector');

  // a range on the Hub's quarters alone; a manager the Hub does not follow: the data sets alone
  const recent = await A.disclosedSource({ aw: '13f', ac: '1423053', from: '2025-01-01' }, api);
  assert.deepEqual(recent.snapshots.map((s) => s.date), ['2025-03-31']);
  assert.ok(!/data sets/.test(recent.note));
  // an older layout ([key, shares, usd]) still reads
  files[HH + 'm/999.json'] = Object.assign({}, files[HH + 'm/1423053.json'], { cik: 999, unit: undefined,
    top: [[['AAPL', 10, 200], ['~G5960L', 5, 80]], [['AAPL', 11, 250], ['GOOG', 2, 50], ['~G5960L', 5, 100]], [['AAPL', 1, 999]]] });
  const only = await A.disclosedSource({ aw: '13f', ac: '999' }, api);
  assert.deepEqual(only.snapshots.map((s) => s.date), ['2024-06-30', '2024-09-30', '2024-12-31']);
  assert.equal(Object.fromEntries(only.snapshots[0].positions).AAPL, 0.5);
  assert.equal(only.name, 'CITADEL ADVISORS LLC');
  await assert.rejects(A.disclosedSource({ aw: '13f', ac: '12345' }, api), /not published yet/);
  // a book of thousands of lines: its 12 largest (here 24%) drawn on their own scale, still as shares of the book
  const thin = (i) => Array.from({ length: 30 }, (_, j) => ['T' + String.fromCharCode(65 + (j % 26)) + (j >= 26 ? 'X' : ''), 1, 2 + (j === 0 ? i : 0)]);
  files[HH + 'm/888.json'] = { cik: 888, name: 'Market Maker', filer: 'MARKET MAKER LLC', periods: ['2020-03-31', '2020-06-30'], usd: [100, 100], lines: [4000, 4100],
    options: [[0, 0], [0, 0]], sectors: [{}, {}], unit: 0.01, top: [thin(0), thin(1)].map((q) => q.map(([k, , v]) => [k, v])), names: {} };
  const z = out();
  await A.build({ aw: '13f', ac: '888', style: 'companies', an: '12' }, z, api);
  assert.equal(z.kind, 'sectors');
  assert.equal(z.stack.share, false, 'its own scale');
  assert.equal(z.stack.pct, true, 'its axis in percent of the book');
  assert.ok(!z.series.some((x) => x.key === 'other'), 'the rest not drawn');
  assert.ok(Math.abs(z.stack.total[0] - 0.24) < 1e-9 && Math.abs(z.stack.total[1] - 0.25) < 1e-9, 'the 12 largest: ' + z.stack.total);
  assert.match([...z.notes].join(' '), /The 12 largest on average are 25\.00% of the long equity book at 2020-06-30[^:]*: drawn on their own scale[^;]*; the other 4,088 holdings \(75\.00%\) are left out/);
  const full = out();
  await A.build({ aw: '13f', ac: '888', style: 'companies', an: '12', az: 'full' }, full, api);
  assert.equal(full.stack.share, true, 'az=full: the whole book');
  console.log('13F weights with the data sets\' history: long equity book, names, quarters before the Hub\'s passed');
})().catch((e) => { console.error(e); process.exit(1); });
