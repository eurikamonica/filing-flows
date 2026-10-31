// disclosures/docs/outlook-view.js merge() / hitRate() and scripts/guidance_board.cjs on a small stand-in site
'use strict';
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const OV = require('../disclosures/docs/outlook-view.js');
const { board } = require('../scripts/guidance_board.cjs');

// merge (web/guidance.js sources): the 10-Q / 10-K MD&A outlook counts as guidance too; a figure it only repeats from a
// release of the three weeks before is left out
const hist = { releases: [{ filed: '2026-07-30', url: 'r', items: [{ metric: 'revenue', basis: '', unit: 'usd', period: 'FY2026', lo: 1, hi: 2 }] }], complete: true };
const ol = { docs: [
  { kind: 'mdna', form: '10-Q', filed: '2026-08-05', accn: 'A', url: 'q', items: [
    { metric: 'revenue', unit: 'usd', period: 'FY2026', lo: 1, hi: 2 },
    { metric: 'capex', unit: 'usd', period: 'FY2026', lo: 3, hi: 3 }] },
  { kind: 'release', form: '8-K', filed: '2026-07-30', accn: 'R', items: [{ metric: 'tax_rate', unit: 'pct', period: 'FY2026', lo: 20, hi: 21 }] }] };
const m = OV.merge(hist, ol);
assert.strictEqual(m.releases.length, 2);
assert.deepStrictEqual(m.releases[0].items.map((x) => x.metric), ['capex'], 'newest first; the repeated revenue left out');
assert.strictEqual(m.releases[0].src, '10-Q');
assert.strictEqual(m.releases[1].src, '8-K');
// a company that guides only in its 10-Q outlook, and a 10-Q that updates a release's range: both count
const upd = OV.merge(hist, { docs: [{ kind: 'mdna', form: '10-Q', filed: '2026-08-05', accn: 'A', items: [{ metric: 'revenue', unit: 'usd', period: 'FY2026', lo: 1.2, hi: 2 }] }] });
assert.deepStrictEqual(upd.releases[0].items.map((x) => x.lo), [1.2]);
const late = OV.merge(hist, { docs: [{ kind: 'mdna', form: '10-Q', filed: '2026-11-05', accn: 'B', items: [{ metric: 'revenue', unit: 'usd', period: 'FY2026', lo: 1, hi: 2 }] }] });
assert.strictEqual(late.releases.length, 2, 'repeated months later: a reaffirmation of its own');
assert.strictEqual(m.complete, true);
assert.strictEqual(OV.merge(null, null), null);
assert.strictEqual(OV.merge(null, ol).releases.length, 1);

// hitRate: periods met or beaten over periods judged, across metrics; beaten and missed by the metric's better side
const rec = { metrics: [
  { name: 'Revenue', hits: { n: 4, hitOrBeat: 3, above: 2, within: 1, below: 1, met: 0, better: 'higher' } },
  { name: 'Operating expenses', hits: { n: 2, hitOrBeat: 2, above: 0, within: 1, below: 1, met: 0, better: 'lower' } },
  { name: 'Adjusted EPS', hits: { n: 0, hitOrBeat: 0, above: 0, within: 0, below: 0, met: 0, better: 'higher' } }] };
const hr = OV.hitRate(rec);
assert.deepStrictEqual([hr.n, hr.hit, hr.beat, hr.miss], [6, 5, 3, 1]);
assert.ok(Math.abs(hr.rate - 5 / 6) < 1e-9);
assert.strictEqual(hr.metrics.length, 2);
assert.strictEqual(OV.hitRate({ metrics: [] }), null);

// the board on a stand-in site: a company with a record, one with statements only, one with nothing
const site = fs.mkdtempSync(path.join(os.tmpdir(), 'gb-'));
const w = (p, o) => { fs.mkdirSync(path.dirname(path.join(site, p)), { recursive: true }); fs.writeFileSync(path.join(site, p), JSON.stringify(o)); };
w('data/index.json', { companies: [{ cik: 1, ticker: 'AAA', name: 'A Co', sector: 'industrials' }, { cik: 2, ticker: 'BBB', name: 'B Co' }, { cik: 3, ticker: 'CCC', name: 'C Co' }] });
w('disclosures/data/holders/AAA.json', { guidance_history: hist, guidance: { label: 'raised', filed: '2026-07-30' } });
w('data/c/1.json', { profile: { cik: 1 }, quarters: [], years: [] });
w('data/outlook/2.json', { cik: 2, docs: [{ kind: 'mdna', form: '10-K', filed: '2026-02-20', counts: { n: 9, new: 4, updated: 1, dropped: 2, tone: 0.3, hedged: 3 }, items: [] },
  { kind: 'mdna', form: '10-Q', filed: '2025-11-01', counts: { n: 8, tone: -0.1 }, items: [] }] });
w('disclosures/data/market/events8k.json', { rows: [{ filed: '2026-10-29', ticker: 'AAA', cik: '1', guidance: 'raised', headline: 'A Co results', url: 'u' }, { filed: '2026-10-29', ticker: 'ZZZ', guidance: null }] });
const b = board(site);
assert.strictEqual(b.companies, 2);
assert.strictEqual(b.with_record, 1);
const a = b.rows.find((r) => r.t === 'AAA'), bb = b.rows.find((r) => r.t === 'BBB');
assert.deepStrictEqual(a.g, ['raised', '2026-07-30']);
assert.strictEqual(a.n, 0);                                  // nothing reported yet for FY2026
assert.deepStrictEqual(bb.fls, ['10-K', '2026-02-20', 9, 4, 1, 2, 0.3, 3]);
assert.deepStrictEqual(b.recent, [['2026-10-29', 'AAA', '1', 'raised', 'A Co results', 'u']]);
assert.strictEqual(bb.tone0, -0.1, 'the MD&A before: the tone it turned from (the screens)');
assert.strictEqual(a.land, null, 'nothing held to a result yet: no landing bins');
console.log('guidance board: ok');
