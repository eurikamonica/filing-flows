// rrg-intraday.js: the intraday RRG's file decoded (closes, today's flow added up), RS-Ratio and RS-Momentum with the RRG's
// own formula (rrg-lab.js) on five-minute bars, the money-inflow screen's rows, filters, sorts and tags, and the view drawn
// with the hub's helpers stubbed — no browser, no network.
const assert = require('node:assert/strict');
require('../docs/rrg-lab.js');                                          // RRGLab on globalThis
const V = require('../docs/rrg-intraday.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const near = (a, b, tol, m) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };

// a file: SPY and three lines over five sessions and today's first 30 bars; UP gains on SPY all day today, DN loses,
// FL follows SPY; today UP closes its bars near the highs (money in), DN near the lows (money out)
const slots = [78, 78, 78, 78, 78, 30], N = slots.reduce((a, b) => a + b, 0), off = N - 30;
let seed = 7;
const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 - 0.5; };
const spy = [], lines = { UP: [], DN: [], FL: [] };
let p = 500, q = { UP: 50, DN: 80, FL: 30 };
for (let i = 0; i < N; i++) {
  const m = 0.0008 * rnd();
  p *= Math.exp(m); spy.push(p);
  for (const t of Object.keys(lines)) {
    const extra = i >= off ? (t === 'UP' ? 0.0006 : t === 'DN' ? -0.0006 : 0) : 0.0004 * rnd();
    q[t] *= Math.exp(m + extra); lines[t].push(q[t]);
  }
}
const code = (c) => { const c0 = c[0], qs = c.map((x) => Math.round(1e5 * Math.log(x / c0))); return { c0, c: qs.map((x, i) => (i ? x - qs[i - 1] : 0)) }; };
const flow = (sign) => ({ dv: Array(30).fill(100), nf: Array(30).fill(60 * sign) });
const asset = (c, name, sign, now) => ({ name, price: c[N - 1], prev: c[off - 1], ...code(c), ...flow(sign), now });
const d = {
  schema: 'intraday-rotation.v1', generated_at: new Date().toISOString(), bench: 'SPY', bar: 5, source: 'test',
  session: { date: '2026-11-11', open: true, k: 30, kf: 29, short: false, last: '12:00' },
  days: ['2026-11-04', '2026-11-05', '2026-11-06', '2026-11-09', '2026-11-10', '2026-11-11'], slots,
  groups: [['sectors', 'Sector ETFs (SPDR)', ['UP', 'DN', 'FL']], ['bonds', 'Bonds', ['FL']]],
  assets: {
    SPY: asset(spy, 'S&P 500', 0, { k: 29, share: 0.01, net: 1e6, dv: 1e8, rvol: 1, rank: 0.5, z: 0, n: 20 }),
    UP: asset(lines.UP, 'Up sector', 1, { k: 29, share: 0.6, net: 6e5, dv: 1e6, h1: 0.5, m30: 0.4, rvol: 2.4, rank: 0.97, z: 2.6, n: 20, vwap: lines.UP[N - 1] * 0.99 }),
    DN: asset(lines.DN, 'Down sector', -1, { k: 29, share: -0.6, net: -6e5, dv: 1e6, rvol: 0.8, rank: 0.03, z: -2.2, n: 20 }),
    FL: asset(lines.FL, 'Flat sector', 1, { k: 29, share: 0.2, net: 2e4, dv: 1e5, rvol: 1.6, rank: 0.6, z: 0.4, n: 20 }),
  },
};
d.assets.FL.prev *= 1.001;                                              // FL: a little behind SPY today, with money in
// decoded: the closes within a tenth of a basis point, the flow added up bar by bar
const D = V.rrgiDecode(d);
ok(D.N === N && D.off === off, 'the grid');
near(D.C.UP[N - 1] / lines.UP[N - 1], 1, 1e-5, 'closes decoded');
ok(D.F.UP.dv[29] === 3000 && D.F.UP.nf[29] === 1800 && D.F.DN.nf[29] === -1800, 'today’s flow added up');
// the RRG: UP ahead of SPY all day — RS-Ratio above 100 by the last bar; DN under it; FL near it
const up = V.rrgiCalc(D, 'UP', 24), dn = V.rrgiCalc(D, 'DN', 24), fl = V.rrgiCalc(D, 'FL', 24);
ok(up.x[N - 1] > 101 && dn.x[N - 1] < 99, `RS-Ratio: ${up.x[N - 1].toFixed(2)} and ${dn.x[N - 1].toFixed(2)}`);
ok(Math.abs(fl.x[N - 1] - 100) < up.x[N - 1] - 100, 'the line that follows SPY stays nearer 100');
ok(up.x[100] == null && up.x[200] != null, 'standard units once 156 bars of the gap are on file');
ok(V.rrgiCalc(D, 'UP', 24) === up, 'cached per line and window');
ok(V.rrgiQuad(up.x[N - 1], up.y[N - 1]) <= 1, 'UP is Leading or Weakening');
// the screen
const rows = V.rrgiRows(d, D, 24, ['SPY', 'UP', 'DN', 'FL']);
const r = Object.fromEntries(rows.map((x) => [x.t, x]));
ok(r.UP.rs > 0 && r.DN.rs < 0 && r.SPY.rs == null, 'the move against SPY');
near(r.UP.vw, 1 / 0.99 - 1, 1e-9, 'the price against VWAP');
ok(r.UP.q != null && r.SPY.q == null, 'the RRG quadrant (none for SPY)');
ok(r.UP.groups.join() === 'sectors' && r.FL.groups.join() === 'sectors,bonds', 'the groups of each line');
ok(V.rrgiFilter(rows, 'in').map((x) => x.t).sort().join() === 'FL,SPY,UP', 'money flowing in');
ok(V.rrgiFilter(rows, 'unusual').map((x) => x.t).join() === 'UP' && V.rrgiFilter(rows, 'unusualout').map((x) => x.t).join() === 'DN', 'unusual inflow and outflow');
ok(V.rrgiFilter(rows, 'heavy').map((x) => x.t).sort().join() === 'FL,UP', 'heavy volume');
ok(V.rrgiFilter(rows, 'outstrong').length === 0, 'no outflow while beating SPY here');
ok(V.rrgiSort(rows, 'share').map((x) => x.t).join() === 'UP,FL,SPY,DN', 'sorted by inflow share');
ok(V.rrgiSort(rows, 'shareasc')[0].t === 'DN' && V.rrgiSort(rows, 'unusual')[0].t === 'UP' && V.rrgiSort(rows, 'unusualasc')[0].t === 'DN', 'and the other ways');
ok(V.rrgiTags(r.UP, 0.01).map((x) => x[1]).includes('Unusual inflow') && V.rrgiTags(r.UP, 0.01).map((x) => x[1]).includes('Heavy volume'), 'tags');
ok(!V.rrgiTags(r.UP, 0.7).map((x) => x[1]).includes('Unusual inflow'), 'not when the market’s own flow is stronger');
ok(V.rrgiTags(r.DN, 0.01).map((x) => x[1]).join() === 'Unusual outflow', 'tags: out');
ok(V.rrgiHm(1) === '9:35 am' && V.rrgiHm(30) === '12:00 pm' && V.rrgiHm(78) === '4:00 pm' && V.rrgiDay('2026-11-11') === 'Wed, Nov 11', 'times');

// the view, the hub's helpers stubbed
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, dd = 0) => (v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: dd, minimumFractionDigits: dd }));
global.compact = (v) => (Math.abs(v) >= 1e9 ? fmt(v / 1e9, 2) + 'B' : Math.abs(v) >= 1e6 ? fmt(v / 1e6, 2) + 'M' : Math.abs(v) >= 1e3 ? fmt(v / 1e3, 1) + 'K' : fmt(v, 1));
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.field = (id, l, items, v) => `<select id="${id}">${items.map(([a, b]) => `<option value="${a}"${a === v ? ' selected' : ''}>${b}</option>`).join('')}</select>`;
global.table = (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((c) => `<tr>${c.map((x) => `<td>${x}</td>`).join('')}</tr>`).join('')}</table>`;
const tips = []; global.tip = (rows) => { tips.push(rows); return tips.length - 1; };
global.curve = (pts) => 'M' + pts.map((p) => p.join(',')).join('L');
global.rotSize = () => [900, 560];
global.niceTicks = (lo, hi, k) => Array.from({ length: k }, (_, i) => +(lo + (hi - lo) * i / (k - 1)).toFixed(2));
global.rotPlayer = (Q) => `<div class="rot-player">${Q.length} frames</div>`;
global.ROT = {}; global.ROT_VIEWS = [['rrg', 'RRG'], ['rrgi', 'Intraday RRG']];
global.RRG_COL = ['#111', '#222', '#333']; global.RRG_Q = [['lead', 'Leading', ''], ['weak', 'Weakening', ''], ['lag', 'Lagging', ''], ['imp', 'Improving', '']];
global.state = { tab: 'rotation', rview: 'rrgi', rrgu: 'sectors' };
global.window = {};
global.fetch = undefined;
global.setInterval = () => 0;                                           // no refresh timer in a test
global.exported = [];
V.RRGI.store = { data: d, at: Date.now() };
const out = V.rrgIntradayView();
ok(out.includes('Intraday Relative Rotation Graph') && out.includes('Money-inflow screen · 4 of 4 lines'), 'the chart and the screen');
ok(out.includes('Where the money flows today') && (out.match(/class="rrgi-bin"/g) || []).length === 2 && (out.match(/class="rrgi-bout"/g) || []).length === 1, 'the bars: two in, one out');
ok((out.match(/class="rrgi-ring /g) || []).length === 3 && out.includes('rrgi-ring rrgi-out'), 'every head ringed by its flow');
ok(!/NaN|undefined|Infinity/.test(out), 'no broken numbers');
ok(state.rf === 29 && ROT.ctx && ROT.ctx.Q.length === 30, 'the frame: the last bar; 30 to play');
ok(exported.length === 4 && exported[0].line === 'UP' && exported[0].inflow_share_pct === 60, 'the screen as CSV, most in first');
state.rrgisf = 'inweak'; state.rrgiss = 'shareasc';
const o2 = V.rrgIntradayView();
const weak = rows.filter((x) => x.share > 0 && x.move < 0).map((x) => x.t);
ok(o2.includes(`Money-inflow screen · ${weak.length} of 4 lines`) && exported.map((x) => x.line).join() === weak.join(), 'buying into weakness: money in, the price down');
ok(V.rrgiFilter(rows.map((x) => (x.t === 'FL' ? { ...x, move: -0.004 } : x)), 'inweak').map((x) => x.t).join() === 'FL', 'money in while the price falls');
state.rrgisf = 'all'; state.rrgisg = 'bonds';
ok(V.rrgIntradayView().includes('Money-inflow screen · 1 of 1 lines'), 'one group');
state.rrgsolo = 'UP'; state.rrgisg = 'all';
ok((V.rrgIntradayView().match(/class="rrgi-ring /g) || []).length === 1, 'one line picked: one line drawn');
state.rrgsolo = ''; state.rrgu = 'indices';
ok(V.rrgIntradayView().includes('<option value="sectors" selected>'), 'a universe the day has not: the sectors');
console.log(`rrg-intraday: ${n} checks passed`);
