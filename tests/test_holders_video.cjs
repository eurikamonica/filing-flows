// The "Major holders" video (web/holders-video.js through web/studio.js): who held a company or an ETF quarter by
// quarter, from the holders history files (disclosures/app/holders_history.py), its share of the company (13F value ÷
// market value, the rank panel) or of the fund (÷ its N-PORT net assets), in every style, the end card and the table.
const assert = require('node:assert/strict');
const files = {};
globalThis.FFUx = { json: async (u) => (u in files ? JSON.parse(JSON.stringify(files[u])) : null) };
const HV = require('../web/holders-video.js');
const S = require('../web/studio.js')._t;
let n = 0;
const ok = (c, m) => { assert.ok(c, m); n++; };
const near = (a, b, m) => ok(Math.abs(a - b) < 1e-9, `${m}: ${a} ≠ ${b}`);

const HUB = 'disclosures/data/', B = 'https://raw.githubusercontent.com/o/r/holders-history/public/', R = HUB + 'market/history/rank/';
files[HUB + 'remote.json'] = { base: 'https://raw.githubusercontent.com/o/r/sha/disclosures/docs/data/', prefixes: ['shards/holdings/'], holders: B };
files[B + 'status.json'] = { tickers: 3 };
// the rank panel: Apple's market value, $3T at every month-end from 2023 ($ millions)
const mi = (d) => (+d.slice(0, 4) - 1990) * 12 + (+d.slice(5, 7) - 1);
files[R + 'meta.json'] = { months: { start: '1990-01', n: 443 }, quarters: [], cos: [['AAPL', 'Apple Inc.', 'technology']], cap_now: [3e6] };
files[R + 'm-cap.json'] = { rows: [[mi('2023-01-31'), ...Array.from({ length: 443 - mi('2023-01-31') }, () => 3e6)]] };
const P = ['2024-03-31', '2024-06-30', '2024-09-30', '2024-12-31'];
const who = [['f:vanguard', 'Vanguard', 'Vanguard', [102909, 2100119]], ['f:blackrock', 'BlackRock', 'BlackRock', [1364742, 2012383]],
  ['c1067983', 'Berkshire Hathaway', 'Berkshire', [1067983]], ['c93751', 'State Street', 'State Street', [93751]], ['c1', 'Small Fund', 'Small', [1]]];
files[B + 'c/AAPL.json'] = { ticker: 'AAPL', name: 'Apple Inc.', cusips: ['037833100'], classes: ['AAPL'], periods: P, filers: [5000, 7100, 7200, 7300], open: ['2024-12-31'],
  total: [[5000, 10e9, 1.8e12], [5100, 10e9, 1.86e12], [5200, 10e9, 1.95e12], [5300, 10e9, 2.1e12]], who,
  top: [[[0, 1.3e9, 2.7e11], [1, 1.0e9, 2.1e11], [2, 9e8, 1.8e11], [3, 6e8, 1.2e11]],
    [[0, 1.3e9, 2.85e11], [1, 1.0e9, 2.16e11], [3, 6e8, 1.2e11], [2, 4e8, 0.9e11]],
    [[0, 1.4e9, 3.0e11], [1, 1.0e9, 2.2e11], [3, 6e8, 1.25e11], [2, 3e8, 0.6e11]],
    [[0, 1.4e9, 3.15e11], [1, 1.1e9, 2.4e11], [3, 6e8, 1.3e11], [4, 1e8, 0.3e11]]] };
// SPY: no market value (a fund), net assets in its N-PORT reports from Q2 2024
files[HUB + 'etf/weights/SPY.json'] = { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', quarterly: { dates: ['2024-06-30', '2024-09-30', '2024-12-31'], na: [5e11, 5.5e11, 6e11] } };
files[B + 'c/SPY.json'] = { ticker: 'SPY', name: 'SPDR S&P 500 ETF TR', periods: P, filers: [7000, 7100, 7200, 7300], total: P.map(() => [4000, 6e8, 3e11]),
  who: [['c1595888', 'Jane Street', 'Jane Street', [1595888]], ['c895421', 'Morgan Stanley', 'Morgan Stanley', [895421]]],
  top: P.map((_, i) => [[0, 4e7 + 1e6 * i, 2.5e10], [1, 3e7, 2e10]]) };
// a security with neither: shares of the 13F total
files[B + 'c/XYZ.json'] = { ticker: 'XYZ', name: 'XYZ CORP', periods: P.slice(0, 2), filers: [1, 1], total: [[10, 1000, 5e7], [10, 2000, 6e7]],
  who: [['c7', 'Seven', 'Seven', [7]]], top: [[[0, 250, 1e7]], [[0, 1000, 3e7]]] };

const ctx = new Proxy({ canvas: { width: 1920, height: 1080 } }, {
  get(o, k) {
    if (k in o) return o[k];
    if (k === 'measureText') return (s) => ({ width: String(s).length * 12 });
    if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => ({ addColorStop() {} });
    return () => {};
  },
  set(o, k, v) { o[k] = v; return true; },
});
const build = (s) => S.build(Object.assign(S.parseState('k=holders'), s));

(async () => {
  ok(S.parseState('k=holders').style === 'bars' && S.parseState('k=holders&hm=usd&hn=5').hm === 'usd', 'the kind, its first style and its settings in the address');
  ok(S.serialize(Object.assign(S.parseState('k=holders'), { t: 'SPY', hn: '15' })).includes('hn=15'), 'the address keeps how many holders');
  // a company: the share of its market value; families together; the bar race
  let V = await build({ t: 'AAPL' });
  ok(V.kind === 'rank' && V.rankN === 10 && V.grid.length === 4 && V.quarterly && V.noLegend, 'a bar race of the quarters');
  ok(V.series[0].label === 'Vanguard' && V.series[0].pal === 0 && /filers together/.test(V.series[0].name), 'the largest holder first, one colour each: ' + V.series[0].name);
  near(V.series[0].v[0], 0.09, 'Vanguard: its 13F value ÷ the market value');
  ok(V.title === 'Who owns Apple' && V.metric === 'Share of Apple' && V.fmt(0.09) === '9.0%', 'title and measure: ' + V.title + ' · ' + V.metric);
  const notes = [...V.notes].join(' | ');
  ok(/one holder, whichever of their companies filed: Vanguard, BlackRock/.test(notes) && /Q4 2024: late amendments/.test(notes) && /more managers crossed/.test(notes), 'the notes: ' + notes);
  ok(V.series.find((s) => s.label === 'Small').v.slice(0, 3).every((x) => x == null), 'a holder outside a quarter\'s largest has no bar then');
  V.style = 'bars'; V.endCard = true; S.finish(V, Object.assign(S.parseState('k=holders'), { t: 'AAPL' }));
  ok(V.final[0].label === '1. Vanguard' && V.final[0].value === '10.5%' && /Share of Apple · Q4 2024/.test(V.endTitle), 'the end card: ' + V.final.map((r) => r.label + ' ' + r.value).join(', '));
  let Rp = S.report(V);
  ok(Rp.cols.map((c) => c[1]).join() === 'Q1 2024,Q4 2024,Change,Shares,Value' && Rp.rows[0].cells.chg[0] === '+1.50 pp' && Rp.rows[Rp.rows.length - 1].label === 'Every 13F holder', 'the table: ' + Rp.rows.map((r) => r.label + ' ' + r.cells.chg[0]).join(', '));
  ok(Rp.rows[0].cells.usd[1] === 'fund family' && Rp.rows[Rp.rows.length - 1].cells.v[1] === '5,300 managers', 'the table names the families and the managers');
  ok(S.csvOf(V, Rp).split('\n')[0].startsWith('date,Vanguard,BlackRock'), 'the CSV: each holder a column');
  // the whole ownership as areas: the largest, every other 13F holder, the rest, adding up to 100%
  V = await build({ t: 'AAPL', style: 'stack', hn: '3' });
  ok(V.kind === 'sectors' && V.stack.share && V.series.map((s) => s.key).join() === 'f:vanguard,f:blackrock,c1067983,other,rest', 'areas: ' + V.series.map((s) => s.key));
  for (let j = 0; j < 4; j++) near(V.series.reduce((a, s) => a + s.v[j], 0), 1, 'every quarter adds up to 100%');
  near(V.series[4].v[0], 1 - 0.6, 'what no 13F reports: 1 − all 13F holdings ÷ market value');
  ok(V.series[4].col && V.series[3].sec === 'other', 'the rest drawn apart from the other 13F holders');
  // lines: the end card gives the change in points
  V = await build({ t: 'AAPL', style: 'line', hn: '3' });
  V.style = 'line'; V.endCard = true; S.finish(V, {});
  ok(V.kind === 'holders' && V.series.length === 3 && V.final[0].change === '+1.50 pp' && V.endSub === 'change since Q1 2024', 'lines and their end card: ' + JSON.stringify(V.final[0]));
  // changes: one quarter to the next, in points, the largest moves first
  V = await build({ t: 'AAPL', style: 'changes' });
  ok(V.kind === 'rank' && V.order === 'abs' && V.grid.length === 3 && V.fmt(0.005) === '+0.50 pp', 'changes');
  near(V.series.find((s) => s.label === 'Berkshire').v[0], 0.03 - 0.06, 'Berkshire\'s cut');
  // the value held, and a range of dates
  V = await build({ t: 'AAPL', hm: 'usd', from: '2024-06-30', to: '2024-09-30' });
  ok(V.grid.length === 2 && V.fmt(2.85e11) === '$285B' && V.metric === 'Value held (13F)', 'value held, two quarters: ' + V.fmt(2.85e11));
  // an ETF: the share of its net assets, the quarters before its first N-PORT report left out
  V = await build({ t: 'SPY' });
  ok(V.title === 'Who owns SPY' && V.grid.length === 3 && /Share of SPY's net assets/.test(V.metric), 'an ETF: ' + V.title + ' · ' + V.metric);
  near(V.series[0].v[0], (4e7 + 1e6) * 0 + 2.5e10 / 5e11, 'Jane Street: its 13F value ÷ the fund\'s net assets');
  ok([...V.notes].some((x) => /on file from Q2 2024/.test(x)), 'says which quarters it leaves out');
  // neither a market value nor net assets: the share of the 13F holdings
  V = await build({ t: 'XYZ' });
  ok(V.metric === 'Share of all 13F holdings' && V.series[0].v[1] === 0.5 && [...V.notes].some((x) => /not of the company/.test(x)), 'the fallback: ' + V.metric);
  // none on file
  await assert.rejects(build({ t: 'NOPE' }), /No 13F holders on file for NOPE/); n++;
  delete files[B + 'status.json'];
  await assert.rejects(build({ t: 'NOPE' }), /still being built/); n++;
  files[B + 'status.json'] = { tickers: 3 };
  await assert.rejects(build({ t: 'AAPL', from: '2030-01-01' }), /no quarter on file/); n++;
  // every style drawn, in every shape, along the way
  for (const style of ['bars', 'line', 'stack', 'changes']) {
    const W = await build({ t: 'AAPL', style });
    W.style = style; W.endCard = true; S.finish(W, {});
    for (const [w, h] of [[1920, 1080], [1080, 1920], [1080, 1080]]) for (const t of [0, 3, 9.5, 19.9]) { S.draw(ctx, w, h, W, { theme: 'bull', dur: 20 }, t); n++; }
    for (const th of ['clean', 'terminal', 'sunset']) { S.draw(ctx, 1920, 1080, W, { theme: th, dur: 20 }, 12); n++; }
  }
  ok(typeof HV.qLabel === 'function' && HV.qLabel('2024-09-30') === 'Q3 2024', 'quarter labels');
  console.log(`Holders video: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
