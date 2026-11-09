// rrg-flow.js: the money-flow files placed on the RRG's weekly grid, the readings over 1 / 4 / 13 weeks (dollars and
// shares of turnover), the quadrants in the RRG's order, the fixed domain, the arrows and rings on the RRG, the
// quadrant chart, the guide with what followed each quadrant, the table and its reading. Offline; no browser.
const assert = require('node:assert/strict');
const path = require('node:path');
global.window = {};
const F = require(path.join(__dirname, '..', 'docs', 'rrg-flow.js'));
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const near = (a, b, m, tol = 1e-9) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };

// a weekly grid of Fridays from 2018-06-01, as rrgGrid(D) makes it
const t0 = Date.parse('2018-06-01T00:00:00Z'), N = 120;
const G = { t0, n: N, days: Array.from({ length: N }, (_, i) => new Date(t0 + i * 6048e5).toISOString().slice(0, 10)) };
G.w = { idx: G.days.map((_, i) => i), labels: G.days };

// a flow file from 2018-08-03 (week 9 of the grid): $10M traded a week, money flow +$1M; off-exchange 200,000 shares a
// week with a short share 1 point over its own normal from week 26 (big money +$0.2M a week)
const start = '2018-08-03', K = 100, off = 9;
const doc = { t: 'XLK', start, dv: Array(K).fill(10000), mf: Array(K).fill(1000), ox: Array(K).fill(200), dp: Array.from({ length: K }, (_, i) => (i < 26 ? null : 200)),
  r: Array(K).fill(4200), b: Array.from({ length: K }, (_, i) => (i < 26 ? null : 4100)) };
doc.mf[60] = -3000;                                    // one week of outflow
const A = F.onGrid(doc, G);
ok(A.dv[off - 1] === null && A.dv[off] === 10000 && A.dv[off + K - 1] === 10000, 'placed on the grid at its start');
ok(A.dp[off + 25] === null && A.dp[off + 26] === 200, 'the big-money figure from its 27th week');

{ // the readings
  const r1 = F.reading(A, off + 30, 4);
  near(r1.y, 10, 'money flow: 4 × $1M of 4 × $10M = 10% of turnover');
  near(r1.x, 2, 'big money: 2 × 1 point of the off-exchange volume = 2%');
  near(r1.dv, 40e6, 'dollars (the files are in thousands)');
  near(r1.mf, 4e6, 'money flow in dollars');
  near(r1.r, 0.42, 'the week’s short share');
  near(r1.dp, 0.8e6, 'its dollars: 4 × $0.2M');
  const A2 = F.onGrid({ ...doc, dp: doc.dp.map((v, i) => (i === 31 ? null : v)) }, G);
  ok(F.reading(A2, off + 32, 4).dp === null && Math.abs(F.reading(A2, off + 32, 4).x - 2) < 1e-9, 'a week without dollars: the share still reads');
  near(r1.b, 0.41, 'its last 52 weeks');
  ok(F.reading(A, off + 2, 4) === null, 'not four weeks on file yet: no reading');
  const r0 = F.reading(A, off + 27, 4);
  ok(r0 && r0.x === null && r0.dp === null && Math.abs(r0.y - 10) < 1e-9, 'a window reaching before the 27th week: money flow only');
  const r13 = F.reading(A, off + 61, 13);
  near(r13.y, 100 * (12 * 1000 - 3000) / (13 * 10000), '13 weeks with one week out');
  ok(F.reading(A, off + 60, 1).y < 0 && F.reading(A, off + 61, 1).y > 0, 'one week: that week alone');
}

ok([F.quad(1, 1), F.quad(1, -1), F.quad(-1, -1), F.quad(-1, 1)].join() === '0,1,2,3', 'quadrants in the RRG order');
ok(F.FQ.map((q) => q[1]).join() === 'Accumulation,Quiet buying,Outflow,Distribution', 'their names');
ok(F.fid({ id: 'XLK' }) === 'XLK' && F.fid({ id: 'NVDA|ix' }) === 'NVDA' && F.fid({ id: 's:technology' }) === null && F.fid({ id: 'th:ai' }) === null && F.fid({ id: 'BRK-B' }) === 'BRK-B', 'which lines have a ticker');

// the view: two lines with files, one basket without
F.S.t.XLK = { data: doc };
const doc2 = { ...doc, t: 'XLE', mf: doc.mf.map((v) => -v), dp: doc.dp.map((v) => (v == null ? null : -v)), r: Array(K).fill(4000) };
F.S.t.XLE = { data: doc2 };
F.S.idx = { data: { stats: { L: 4, h: [4, 13], from: '2019-02-01', to: '2026-08-07', pools: {
  stocks: { tickers: 900, all: { 4: { n: 1000, beat: 0.47, med: -0.3, mean: 0.1 }, 13: { n: 1000, beat: 0.45, med: -0.8, mean: 0.2 } },
    q: [0, 1, 2, 3].map((q) => ({ 4: { n: 250, beat: 0.5 - q / 100, med: 0.1 * q, mean: 0 }, 13: { n: 240, beat: 0.48, med: -0.2, mean: 0 } })),
    fifths: { 13: { x: { top: { n: 99, beat: 0.5, med: 0.4 }, bottom: { n: 99, beat: 0.44, med: -1.1 } }, y: { top: { n: 99, beat: 0.47, med: -0.2 }, bottom: { n: 99, beat: 0.46, med: -0.5 } } } } },
  etfs: { tickers: 40, all: {}, q: [0, 1, 2, 3].map(() => ({ 4: { n: 30, beat: 0.6, med: 0.5 }, 13: { n: 30, beat: 0.55, med: 0.6 } })) } } } } };
const calc = (fx, fy) => ({ x: G.days.map((_, k) => 100 + fx(k)), y: G.days.map((_, k) => 100 + fy(k)) });
const o = { lines: [{ e: { id: 'XLK', name: 'XLK' }, col: '#2a78d6', calc: calc((k) => 1 + k / 100, () => 0.5) },
  { e: { id: 'XLE', name: 'XLE' }, col: '#eb6834', calc: calc(() => -1, () => -0.5) },
  { e: { id: 'th:ai', name: 'AI basket' }, col: '#1baf7a', calc: calc(() => 0.2, () => 0.2) }],
  Q: G.days, firstK: 0, lastK: N - 1, freq: 'w', mode: '2d', tail: 4, pick: new Set() };
const V = F.prep(o, G, G.w.idx, { mode: 'arrows', L: 4 });
ok(V.any && !V.loading && V.per.length === 3 && V.missing.join() === 'AI basket', 'two lines read, the basket has no ticker');
ok(V.dom.x[1] > 0 && V.dom.x[0] === -V.dom.x[1] && V.dom.y[1] >= 10, 'a symmetric domain that holds the readings');
const f = off + 40;
const tips = [];
const H = { size: () => [700, 380], ticks: (a, b, k) => { const s = (b - a) / k, out = []; for (let v = Math.ceil(a / s) * s; v <= b; v += s) out.push(+v.toFixed(6)); return out; },
  curve: (pts) => 'M' + pts.map((p) => p.join(',')).join('L'), tip: (rows) => { tips.push(rows); return tips.length - 1; }, day: (s) => s,
  table: (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`,
  empty: (t) => `<div class="empty">${t}</div>`, rrgQuad: (x, y) => (x >= 100 ? (y >= 100 ? 0 : 1) : (y < 100 ? 2 : 3)),
  RRG_Q: [['lead', 'Leading'], ['weak', 'Weakening'], ['lag', 'Lagging'], ['imp', 'Improving']] };
const sx = (v) => 300 + 20 * (v - 100), sy = (v) => 200 - 20 * (v - 100);

{ // arrows on the RRG: up and to the right for XLK (both buying), down and to the left for XLE
  const L = F.overlay(o, V, f, sx, sy, H);
  const lines = [...L.over.matchAll(/<line x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)" style="stroke:([^"]+)"/g)].map((m) => m.slice(1).map((x, i) => (i < 4 ? +x : x)));
  ok(lines.length === 2, 'one arrow per line with a ticker');
  const [k, e] = lines;
  ok(k[2] > k[0] && k[3] < k[1] && k[4] === 'var(--flow-buy)', 'XLK: → and ↑ (Accumulation, green)');
  ok(e[2] < e[0] && e[3] > e[1] && e[4] === 'var(--flow-sell)', 'XLE: ← and ↓ (Outflow, red)');
  near(Math.hypot(k[0] - sx(o.lines[0].calc.x[f]), k[1] - sy(o.lines[0].calc.y[f])), 9, 'the arrow starts at the edge of the head dot', 0.15);
  ok(tips.some((r) => /Big-money net buying/.test(r[1][1]) && r[1][0] === '+$800K (+2.0% of off-exchange volume)'), 'a tooltip with dollars and the share of the off-exchange volume');
  const R = F.overlay(o, { ...V, mode: 'rings' }, f, sx, sy, H);
  ok((R.under.match(/<circle /g) || []).length === 8 && (R.over.match(/rrgf-ring/g) || []).length === 2, 'rings: every week of the 4-week tail, an outline on the latest');
  ok(F.overlay(o, { ...V, mode: 'off' }, f, sx, sy, H).over === '', 'off: nothing drawn');
  ok(F.overlay({ ...o, pick: new Set(['XLE']) }, V, f, sx, sy, H).over.split('<g ').length === 2, 'only the lines picked');
}

{ // the quadrant chart, the guide, the table
  const s = F.chart(o, V, f, H);
  ok(s.startsWith('<svg') && s.endsWith('</svg>') && /Accumulation/.test(s) && /Distribution/.test(s), 'the four quadrants named');
  ok((s.match(/class="rot-dot"/g) || []).length === 8, 'four weeks of tail for each line with a reading');
  ok(/>XLK</.test(s) && /XLE/.test(s) && !/AI basket/.test(s), 'labelled heads; the basket left out');
  const p = F.panel(o, V, f, H);
  ok(/Money flow: big-money net buying × net money inflow/.test(p) && /id="rrgf-plot"/.test(p), 'the panel: heading and the chart to redraw');
  ok(/Stocks: 4 weeks on: beat SPY 50% of the time, median 0\.0%; 13 weeks on: beat SPY 48% of the time, median −0\.2% \(240 stock-weeks\)/.test(p), 'what followed each quadrant');
  ok(/the top fifth by big-money buying beat SPY 50% of the time 13 weeks on \(median \+0\.4%\), the bottom fifth 44% \(median −1\.1%\)/.test(p), 'the top and bottom fifths');
  ok(/ETFs: 4 weeks on: beat SPY 60% of the time/.test(p), 'ETFs apart');
  ok(/Leading, with money behind it/.test(p) && /Lagging and still being sold/.test(p), 'the table reads each line with its RRG quadrant');
  ok(/No flows for AI basket/.test(p), 'says which lines have no flows');
  const T = p.slice(p.indexOf('<table>'), p.indexOf('</table>'));
  ok(T.indexOf('XLK') < T.indexOf('XLE'), 'the most big-money buying first');
  ok(F.legend(V).includes('→ big-money net buying') && F.legend({ ...V, mode: 'rings' }).includes('ringed'), 'the legend line of each mode');
  const none = F.prep({ ...o, lines: [o.lines[2]] }, G, G.w.idx, { mode: 'arrows', L: 4 });
  ok(!none.any && /No money flows on file for these lines yet/.test(F.panel(o, none, f, H)), 'nothing to draw: says so');
}

ok(F.usd(1.234e9) === '+$1.23B' && F.usd(-2.5e6) === '−$2.5M' && F.pc(-0.123, 2) === '−0.12%', 'dollars and percents');
console.log(`rrg flow: ${n} checks passed`);
