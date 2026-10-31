const assert=require('node:assert/strict');
const fs=require('node:fs');
require('../web/quality-ipo.js');
const q=globalThis.FFQualityIPO;
const data=JSON.parse(fs.readFileSync('pipeline/data/ipo/2130357.json','utf8'));
for(const p of data.periods) {
  const specs=q.charts(p);assert.equal(specs.length,4);
  for(const s of specs) {
    assert(s.links.every(l=>Number.isFinite(l.v)&&l.v>0));
    const incoming=s.links.filter(l=>l.t==='pool').reduce((v,l)=>v+l.v,0);
    const outgoing=s.links.filter(l=>l.s==='pool').reduce((v,l)=>v+l.v,0);
    assert(Math.abs(incoming-outgoing)<1);
  }
}
assert.equal(q.flow('bad',[['A',10]],50,'result',{}),null);
assert.equal(q.flow('missing',[['A',null]],0,'result',{}),null);
assert.equal(q.charts({values:{revenue:100,oi:10},label:'FY'}).length,1);
assert(!q.metricTable([{label:'<img src=x>',value:null,formula:'<script>'}]).includes('<img'));
console.log('IPO signed-flow conservation, missing data and escaping checks passed');

// The company page's pieces (web/quality-ipo.js) and the prospectus reader (web/ipo-reader.js), without a browser.
globalThis.window = globalThis;
require('../web/ipo-reader.js');
const T = q._t, R = globalThis.FFIPOReader;
const period = (key, label, months, end, revenue, parts, extra = {}) => ({
  key, label, months, end, vs: null,
  headline: { revenue, rev_fmt: '$' + (revenue / 1e9).toFixed(1) + 'B', prior: null, oi: -1e9, oi_fmt: '−$1.0B', om: -10, ni: -2e9, ni_fmt: '−$2.0B', nm: -20 },
  nodes: [{ id: 'revenue', name: 'Revenue', v: revenue }, ...parts.map(([k, v]) => ({ id: 'I:' + k, name: k === 'rd' ? 'Research &amp; development' : 'Selling <b>', v }))],
  ...extra });
const list = [period('2026-01-01_2026-06-30', 'H1 2026', 6, '2026-06-30', 16e9, [['rd', 9e9], ['sm', 8e9]], { vs: 'H1 2025' }),
  period('2025-01-01_2025-12-31', 'FY 2025', 12, '2025-12-31', 4.6e9, [['rd', 7e9], ['sm', 6e9]]),
  period('2025-01-01_2025-06-30', 'H1 2025', 6, '2025-06-30', 1.2e9, [['rd', 2e9], ['sm', 1.4e9]]),
  period('2024-01-01_2024-12-31', 'FY 2024', 12, '2024-12-31', 0.4e9, [['rd', 2.5e9], ['sm', 1e9]])];
// periods grouped by length, the group of the open period first, newest first inside a group
const groups = T.periodGroups(list, '2026-01-01_2026-06-30');
assert.deepEqual(groups.map((g) => [g.name, g.items.map((p) => p.label)]), [['Half years', ['H1 2026', 'H1 2025']], ['Years', ['FY 2025', 'FY 2024']]]);
assert.equal(T.periodGroups(list, '2024-01-01_2024-12-31')[0].name, 'Years');
// money, growth and tiles
assert.equal(T.usd(-80.748e9), '−$80.7B');
assert.equal(T.usd(-693e6, '−$0.69B'), '−$0.69B');               // the unit of the chart it sits beside
assert.equal(T.usd(386e6), '$386.0M');
assert.equal(T.signed(T.growth(16.286e9, 1.163e9)), '+1,300%');
assert.equal(T.signed(T.growth(5, -1)), 'n/m');
const tiles = T.tiles({ ...list[0], headline: { ...list[0].headline, prior: { revenue: 1.2e9, oi: -2.1e9, ni: -13e9, ocf: -1.5e9 }, ocf_fmt: '$3.9B', fcf_fmt: '$3.4B' } });
assert(tiles.includes('+1,233% vs H1 2025') && tiles.includes('H1 2025: −$13.0B') && tiles.includes('Operating loss') && tiles.includes('$3.4B'), tiles);
// costs per $1 of revenue: every line, the break-even line, bars past $3 cut, escaped names, a table view
assert.deepEqual(T.costParts(list[0]).map((x) => [x.key, x.name, +x.per.toFixed(4)]), [['rd', 'Research & development', 0.5625], ['sm', 'Selling <b>', 0.5]]);
const cost = T.costSVG(list, '2026-01-01_2026-06-30');
assert(cost.capped, 'FY 2024 spends $8.75 per $1: the bar is cut');
assert(cost.svg.includes('break-even') && cost.svg.includes('$8.75') && cost.svg.includes('$1.06'));
assert(!cost.svg.includes('<b>') && !cost.legend.includes('<b>') && !cost.tableView.includes('<b>'));
assert(!/NaN|undefined/.test(cost.svg + cost.tableView));
assert.equal((cost.svg.match(/class="ipo-crow/g) || []).length, 4, 'one row per period');
const rev = T.revenueSVG(list, '2026-01-01_2026-06-30');
assert.equal((rev.match(/class="ipo-col/g) || []).length, 4);
assert(rev.includes('aria-pressed="true"') && rev.includes('$16.0B') && !/NaN|undefined/.test(rev));
assert.deepEqual(T.ticks(16.3e9), [0, 5e9, 10e9, 15e9, 20e9]);
// the reader: a table as printed (spanning headings, a group row, figures to the right), escaped; the cover chips
const tbl = R._t.table([['', ['Before the offering', 2], ['After the offering', 2]], ['Name of beneficial owner', 'Number', '%', 'Number', '%'],
  ['Directors and officers:'], ['Jane <script>', '1,000,000', '40.0', '900,000', '30.0']]);
assert(tbl.includes('<th colspan="2">Before the offering</th>') && (tbl.match(/<thead>/g) || []).length === 1);
assert(tbl.includes('<tr class="ipo-rgroup"><td colspan="5">Directors and officers:</td></tr>') && tbl.includes('<td class="num">1,000,000</td>'));
assert(!tbl.includes('<script>'));
const chips = R.chips({ symbol: 'ANT', exchange: 'Nasdaq Global Select Market', range: [17, 19], shares: 25000000, flags: ['emerging growth company', 'public benefit corporation'] });
assert(chips.includes('<b>ANT</b>') && chips.includes('$17.00–$19.00 per share') && chips.includes('25,000,000 shares offered') && chips.includes('Public benefit corporation'));
assert.equal(R._t.at('https://www.sec.gov/x.htm', 'i1_79'), 'https://www.sec.gov/x.htm#i1_79');
assert.equal(R._t.at('https://www.sec.gov/x.htm', 'bad"anchor'), 'https://www.sec.gov/x.htm');
assert.equal(R._t.sec('javascript:alert(1)'), '');
const sv = R._t.sectionView({ title: 'Use <of> Proceeds', anchor: 'u', page: '80', words: 900, text: ['We intend <x>.', '• A bullet'], heads: ['Overview'] }, 'https://www.sec.gov/x.htm');
assert(sv.includes('Use &lt;of&gt; Proceeds') && sv.includes('x.htm#u') && sv.includes('class="ipo-bullet"') && sv.includes('900-word section'));
console.log('IPO company page pieces and prospectus reader checks passed');
