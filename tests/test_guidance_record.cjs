// web/guidance.js record(): each guided period against what the company then reported (above / within / below the
// range, met for a floor), the moves of a guide between releases, the hit rate per metric, and its HTML and footer line.
const assert = require('assert');
const FG = require('../web/guidance.js');

const B = 1e9;
const spec = (label, end, filed, rev, gp, opex, tax, pretax) => ({
  label, end, filed, nodes: [
    { id: 'revenue', v: rev * B }, { id: 'gp', v: gp * B }, { id: 'opex', v: opex * B }, { id: 'oi', v: (gp - opex) * B },
    { id: 'pretax', v: pretax * B }, { id: 'tax', v: tax * B }, { id: 'net', v: (pretax - tax) * B }],
  links: [],
});
// a calendar-year company: Q1–Q3 2026 on file, FY2025 as a year
const q3 = spec('Q3 2026', '2026-09-30', '2026-10-28', 11.0, 5.5, 2.0, 0.6, 4.0);
const q2 = spec('Q2 2026', '2026-06-30', '2026-07-29', 10.0, 5.2, 2.1, 0.5, 3.4);
const q1 = spec('Q1 2026', '2026-03-31', '2026-04-29', 9.0, 4.4, 2.0, 0.4, 2.6);
const fy25 = spec('FY25', '2025-12-31', '2026-02-20', 36.0, 18.0, 8.0, 1.6, 10.5);
const company = {
  quarters: [q3, q2, q1], years: [fy25],
  periods: { q: [{ end: '2026-09-30', q: 3, fy: 2026 }, { end: '2026-06-30', q: 2, fy: 2026 }, { end: '2026-03-31', q: 1, fy: 2026 },
    { end: '2025-12-31', q: 4, fy: 2025 }], fy: [{ end: '2025-12-31', fy: 2025 }] },
};
const it = (metric, basis, period, unit, lo, hi, x) => Object.assign({ metric, basis, period, unit, lo, hi }, x || {});
const history = { complete: true, releases: [
  { filed: '2026-10-28', url: 'u4', label: 'raised', tags: ['raised', 'narrowed'], items: [
    it('revenue', '', 'Q4 2026', 'usd', 11.5 * B, 12.0 * B), it('revenue', '', 'FY2026', 'usd', 41.5 * B, 42.0 * B, { said: 'raised' })] },
  { filed: '2026-07-29', url: 'u3', tags: ['raised'], items: [
    it('revenue', '', 'Q3 2026', 'usd', 10.4 * B, 10.8 * B),                     // reported 11.0: above
    it('gross_margin', 'GAAP', 'Q3 2026', 'pct', 49.5, 50.5),                    // reported 50.0: within
    it('gross_margin', 'non-GAAP', 'Q3 2026', 'pct', 52, 53),                    // no adjusted figure: moves only
    it('gross_margin', '', 'Q3 2026', 'pct', 70, 70),                            // a remark beside the bases: ignored
    it('opex', 'GAAP', 'Q3 2026', 'usd', 2.1 * B, 2.1 * B, { approx: true }),   // reported 2.0: −4.8%, below the ±1% band
    it('revenue', '', 'FY2026', 'usd', 41.0 * B, 42.0 * B)] },
  { filed: '2026-04-29', url: 'u2', items: [
    it('revenue', '', 'Q2 2026', 'usd', 10.0 * B, 10.4 * B),                     // reported 10.0: within (the low end)
    it('tax_rate', 'GAAP', 'Q2 2026', 'pct', 15, 16),                            // reported 14.7%: below
    it('revenue', '', 'FY2026', 'usd', 40.0 * B, 42.0 * B)] },
  { filed: '2026-02-20', url: 'u1', items: [
    it('revenue', '', 'Q1 2026', 'usd', 9.2 * B, 9.6 * B),                       // reported 9.0: below
    it('revenue', '', 'FY2026', 'usd', 40.0 * B, 42.0 * B, { said: 'initiated' }),
    it('revenue', '', 'Q4 2025', 'usd', 9.9 * B, 9.9 * B)] },                    // a result quoted after Q4 2025 was reported
] };

const rec = FG.record(history, company);
assert.ok(rec, 'a record');
assert.strictEqual(rec.releases, 4);
const rev = rec.metrics.find((m) => m.metric === 'revenue');
assert.strictEqual(rec.metrics[0], rev, 'revenue first');
const row = (m, label) => m.rows.find((r) => r.label === label);
assert.strictEqual(row(rev, 'Q3 2026').outcome, 'above');
assert.strictEqual(row(rev, 'Q2 2026').outcome, 'within');
assert.strictEqual(row(rev, 'Q1 2026').outcome, 'below');
assert.ok(Math.abs(row(rev, 'Q3 2026').vsMid - (11 / 10.6 - 1) * 100) < 1e-9, 'vs the guided midpoint');
assert.ok(row(rev, 'Q4 2026').pending && !row(rev, 'Q4 2026').outcome, 'the next quarter: to be reported');
assert.deepStrictEqual({ n: rev.hits.n, above: rev.hits.above, within: rev.hits.within, below: rev.hits.below, hitOrBeat: rev.hits.hitOrBeat },
  { n: 3, above: 1, within: 1, below: 1, hitOrBeat: 2 });
// the full year's guide release after release: initiated, reaffirmed, narrowed (midpoint up), raised and narrowed
const fy = row(rev, 'FY2026');
assert.deepStrictEqual(fy.guides.map((g) => [g.change, g.range || null]),
  [['initiated', null], ['reaffirmed', null], ['raised', 'narrowed'], ['raised', 'narrowed']]);
assert.ok(fy.pending, 'the year is still running');
assert.deepStrictEqual(rev.moves, { raised: 2, lowered: 0, reaffirmed: 1, narrowed: 2, widened: 0 });
assert.strictEqual(FG.movesLine(rev), '▲ raised 2× · = reaffirmed 1× · →← narrowed 2×');
assert.ok(!rev.rows.some((r) => r.label === 'Q4 2025'), 'a figure for a period already reported is not a guide');
const gm = rec.metrics.find((m) => m.metric === 'gross_margin' && m.basis === 'GAAP');
assert.strictEqual(row(gm, 'Q3 2026').outcome, 'within');
assert.ok(!rec.metrics.some((m) => m.metric === 'gross_margin' && m.basis === ''), 'a basis-less remark beside GAAP and adjusted figures is left out');
const adj = rec.metrics.find((m) => m.metric === 'gross_margin' && m.basis === 'non-GAAP');
assert.strictEqual(adj.hits.n, 0, 'adjusted guidance is never held to GAAP figures');
const ox = rec.metrics.find((m) => m.metric === 'opex');
assert.strictEqual(row(ox, 'Q3 2026').outcome, 'below');
assert.strictEqual(ox.hits.better, 'lower');
assert.strictEqual(ox.hits.hitOrBeat, 1, 'opex below its guide counts as met or better');
const tx = rec.metrics.find((m) => m.metric === 'tax_rate');
assert.strictEqual(row(tx, 'Q2 2026').outcome, 'below');
assert.ok(Math.abs(row(tx, 'Q2 2026').actual - 0.5 / 3.4 * 100) < 1e-9, 'tax rate = tax / pre-tax');
assert.strictEqual(FG.summaryLine(rev), 'Revenue: in or above the guided range 2 of 3 periods (1 above, 1 within, 1 below) · on average −0.8% vs the midpoint');   // (+3.8 − 2.0 − 4.3) / 3

// outcomes: a range, a point guide (±1%), a floor
assert.strictEqual(FG.outcome(105, { unit: 'usd', lo: 100, hi: 104 }), 'above');
assert.strictEqual(FG.outcome(100.5, { unit: 'usd', lo: 100, hi: 100 }), 'within');
assert.strictEqual(FG.outcome(98.5, { unit: 'usd', lo: 100, hi: 100 }), 'below');
assert.strictEqual(FG.outcome(300, { unit: 'usd', lo: 290, hi: 290, bound: 'min' }), 'met');
assert.strictEqual(FG.outcome(74.2, { unit: 'pct', lo: 74, hi: 74 }), 'within');

// HTML: the chips, a strip of dots per metric, the table of moves; the first metric open
const html = FG.recordHTML(rec);
assert.ok(html.includes('Guidance record') && html.includes('Met or beat 2 of 3') && html.includes('<svg class="gr-strip"'), 'summary and dots');
assert.ok(html.includes('▲ raised →← narrowed'), 'the moves in the table');
assert.ok(html.includes('to be reported'), 'the guided period still to come');
assert.ok(/<details class="gr-metric" open>/.test(html) && (html.match(/<details class="gr-metric">/g) || []).length >= 1, 'later metrics folded');

// the guidance view carries the record: in its footer (exports too) and on its notes
const base = Object.assign({}, q3, { label: 'Q3 2026', period: 'q', nodes: [
  { id: 'revenue', col: 0, color: 'rev', v: 11 * B, name: 'Revenue', lines: [['big', 'Revenue'], ['val', '$11.0B']] },
  { id: 'gp', col: 1, color: 'profit', v: 5.5 * B, name: 'Gross profit', lines: [['name', 'Gross profit'], ['val', '$5.5B · 50% of revenue']] },
  { id: 'cor', col: 1, color: 'cost', v: 5.5 * B, name: 'Cost of revenue', lines: [['name', 'Cost of revenue'], ['val', '$5.5B · 50% of revenue']] }],
links: [{ s: 'revenue', t: 'gp', v: 5.5 * B, color: 'profit' }, { s: 'revenue', t: 'cor', v: 5.5 * B, color: 'cost' }] });
const f = FG.future(base, { filed: '2026-10-28', items: history.releases[0].items }, { company, history, name: 'Example' });
assert.ok(!f.error, f.error);
assert.ok(f.record && f.footer.some((x) => x.startsWith('Guidance record (4 releases since Feb 20, 2026') && x.includes('Revenue: in or above the guided range 2 of 3')), f.footer.join(' / '));
const note = FG.noteHTML(f.nodes.find((n) => n.id === 'revenue'), null, null, f.record);
assert.ok(note.includes('Track record:') && note.includes('2 of 3'), note);
const none = FG.future(base, null, { company, history });
assert.ok(none.error && none.record, 'no current guidance: the record still shows');
// drawn: the guide path (a bar per release per period, the reported dot) and where the results landed
const path = FG.pathHTML(rec);
assert.ok(path.includes('<svg class="gr-path"') && path.includes('Revenue: how the guidance moved'), 'a path chart for revenue');
assert.strictEqual((path.split('<svg class="gr-path"')[1].split('</svg>')[0].match(/<rect /g) || []).length, 3 + 4, 'Q1–Q3 one bar each, FY2026 four');
assert.ok(/FY2026[\s\S]*4 guides/.test(path) && path.includes('>?</text>'), 'the year guided four times, still to report');
const land = FG.landingHTML(rec);
// revenue: Q3 above (better), Q2 at the low end (worse third), Q1 below (worse); GAAP gross margin 50.0 in 49.5–50.5 (middle);
// opex 2.0 vs ≈2.1 (below the ±1% band: better for a cost); tax 14.7% vs 15–16% (below: better)
assert.ok(land.includes('<svg class="gr-land"') && /The company lands around the middle|guides conservatively|optimistic/.test(land), land);
assert.ok(/held to a reported one \(6\)/.test(land), 'six figures held to their results');
assert.strictEqual(FG.pathHTML(null), '');
assert.strictEqual(FG.record({ releases: [] }, company), null);
console.log('guidance record: ok');
