// moves-view.js and moves.js: the move odds arithmetic (decode, percentiles, the similar and more extreme days, returns
// ahead, episodes, a past day judged on its own history, a what-if move, moves against volatility and beyond the market)
// and the hub's market, industries and stocks views from an index file (the hub's helpers stubbed; no browser, no network).
const assert = require('node:assert/strict');
global.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.fmt = (v, d = 0) => (v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
global.table = (h, rows) => `<table><tr>${h.map((x) => `<th>${x}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
global.empty = (t) => `<div class="empty">${esc(t)}</div>`;
global.state = {};
global.window = {};
const V = require('../docs/moves-view.js');
const H = require('../docs/moves.js');
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const near = (a, b, m, tol = 1e-9) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };

// a doc as app/moves.py writes it: weekdays, returns in whole basis points
function doc(rets, d0 = '2024-01-01') {
  let t = Date.parse(d0 + 'T00:00:00Z'), gaps = '';
  const days = [d0];
  for (let i = 0; i < rets.length; i++) {
    let g = 1; const wd = new Date(t + 864e5).getUTCDay(); if (wd === 6) g = 3; else if (wd === 0) g = 2;
    t += g * 864e5; gaps += g.toString(36); days.push(new Date(t).toISOString().slice(0, 10));
  }
  return { doc: { key: 'X', ticker: 'X', name: 'X CORP', kind: 'stock', d0, gaps, r: rets.map((x) => Math.round(x * 1e4)), links: {} }, days };
}
let seed = 5;
const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
const normal = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());

// 1. decode
{
  const { doc: d, days } = doc([0.01, -0.02, 0.005, 0.0, 0.03]);
  const A = V.decode(d);
  assert.deepEqual(A.days, days); n++;
  near(A.r[1], -0.02, 'returns back as fractions');
  const B = V.decode({ dates: ['2026-01-02', '2026-03-02'], r: [100] });
  assert.deepEqual(B.days, ['2026-01-02', '2026-03-02']); n++;
}

// 2. percentiles and the chosen days on a known series: 400 small days, then a −8% day last
{
  const rets = [];
  for (let i = 0; i < 400; i++) rets.push(0.0004 + 0.01 * normal());
  rets.push(-0.08);
  const A = V.decode(doc(rets).doc);
  const R = V.analyze(A, { w: 1, measure: 'raw', mode: 'latest', band: 2.5 });
  near(R.at, 100 * 0.5 / 401, 'the lowest of 401 days: mid-rank');
  ok(R.side === -1, 'a fall');
  ok(R.every === 401 && R.k === 1, 'once in the whole history');
  ok(R.lastAs === null, 'never before');
  // the similar days: within 2.5 points of 0.12 → the lowest ~2.6% of days (today left out); none has today's index
  const sims = [...R.sim].reduce((a, b) => a + b, 0);
  ok(sims >= 8 && sims <= 12, `about 10 days like it (${sims})`);
  ok(R.sim[A.days.length - 1] === 0 && R.all[A.days.length - 1] === 0, 'the day itself is never among them');
  ok(R.h[1].ext === null, 'nothing as low before it');
  // next-day returns after the similar days: by hand
  const c = V.cum(A.r), f = [];
  for (let j = 0; j < A.days.length; j++) if (R.sim[j] && j + 1 < A.days.length) f.push(Math.expm1(c[j + 1] - c[j]));
  f.sort((a, b) => a - b);
  const S = R.h[1].sim;
  ok(S.n === f.length, 'every similar day with a known next day');
  near(S.median, f.length % 2 ? f[(f.length - 1) / 2] : (f[f.length / 2 - 1] + f[f.length / 2]) / 2, 'median of the next days', 1e-12);
  near(S.up, f.filter((x) => x > 0).length / f.length, 'share up');
  ok(R.h[21].all.n === A.days.length - 1 - 21 || R.h[21].all.n === A.days.length - 2 - 21 + 1, 'every day with 21 known days ahead');
  // episodes: chosen days within the horizon of each other count once
  const T = V.stats(Float64Array.from([0.01, 0.02, 0.01, 0.03, 0.01, 0.02, 0.01]), Uint8Array.from([1, 1, 0, 0, 0, 1, 0]), 2);
  ok(T.n === 3 && T.ep === 2, 'days 0 and 1 one episode, day 5 another');
}

// 3. a past day, judged only on the days before it; a what-if move
{
  const rets = [];
  for (let i = 0; i < 500; i++) rets.push(0.01 * normal());
  rets[300] = -0.07;
  const { doc: d, days } = doc(rets);
  const A = V.decode(d);
  const R = V.analyze(A, { w: 1, measure: 'raw', mode: 'date', date: days[301], band: 2.5, before: true });
  ok(R.t === 301, 'the day picked');
  ok(R.n === 301, 'only the 301 moves up to it are ranked');
  ok(Math.abs(R.actual[1] - Math.expm1(A.r[301])) < 1e-12, 'what happened the next day');
  for (const h of [1, 5, 21]) for (const k of ['sim', 'ext', 'all']) { const S = R.h[h][k]; if (S) ok(S.idx.every((j) => j + h <= 301), `${k}, ${h} days: only returns known on the day`); }
  const W = V.analyze(A, { w: 1, measure: 'raw', mode: 'whatif', whatif: -10, band: 2.5 });
  ok(W.t === -1 && W.at === 0 && W.lastAs === null, 'a −10% day would be lower than any on file');
  const W6 = V.analyze(A, { w: 1, measure: 'raw', mode: 'whatif', whatif: -6, band: 2.5 });
  ok(A.days[W6.lastAs] === days[301] && W6.k === 2, 'a −6% day: the −7% day was at least as low, the last time');
  const E = V.analyze(A, { w: 1, measure: 'raw', mode: 'whatif', whatif: 'x', band: 2.5 });
  ok(E.error, 'a move that is not a number');
}

// 4. against its own volatility, and beyond the market
{
  const mk = [], st = [];
  for (let i = 0; i < 700; i++) { const m = 0.01 * normal(); mk.push(m); st.push(2 * m + 0.004 * normal()); }
  st[699] = 2 * mk[699] - 0.06;                       // a stock-specific −6% on the last day
  const M = V.decode(doc(mk).doc), A = V.decode(doc(st).doc);
  const e = V.residual(A, M, 1);
  near(e[700], -0.06, 'the stock-specific part of the last move (beta about 2)', 0.006);
  ok(Number.isNaN(e[100]), 'a year of returns before the first one');
  const z = V.volScaled(A.r, 1);
  ok(Number.isNaN(z[63]) && Number.isFinite(z[64]), '63 returns before the first');
  const R = V.analyze(A, { w: 1, measure: 'beta', mode: 'latest', band: 2.5 }, M);
  ok(R.at < 1, 'beyond the market it is a record low');
  const R5 = V.analyze(A, { w: 5, measure: 'raw', mode: 'latest', band: 5 });
  ok(R5.kEp >= 1 && R5.kEp <= R5.k, 'weeks counted as episodes');
}

// 5. how long it took: the block search against a plain scan, Kaplan–Meier with waiting days, recovery times
{
  const c = [0];
  for (let i = 0; i < 600; i++) c.push(c[i] + 0.02 * normal());
  const P = V.sparse(c), Q = V.sparse(c.map((v) => -v));
  const scan = (from, v, end, up) => { for (let k = from; k <= end; k++) if (up ? c[k] >= v : c[k] <= v) return k; return -1; };
  let agree = true;
  for (let q = 0; q < 400; q++) {
    const from = Math.floor(rnd() * 600), end = Math.min(600, from + Math.floor(rnd() * 650)), v = c[Math.floor(rnd() * 600)] + 0.05 * normal();
    if (V.firstAt(P, from, v, end) !== scan(from, v, end, true) || V.firstAt(Q, from, -v, end) !== scan(from, v, end, false)) agree = false;
  }
  ok(agree, 'the block search finds the same first day as a plain scan (400 questions)');
  const K = V.km([2, 3, 5, 5], [true, false, true, true]);
  ok(K.median === 5 && Math.abs(K.by(3) - 0.25) < 1e-12 && K.by(21) === 1, 'Kaplan–Meier as app/moves.py');
  const K2 = V.km([10, 10, 10], [false, false, true]);
  ok(K2.median === null && Math.abs(K2.by(21) - 1 / 3) < 1e-12, 'half never back: no median');
  const T = { up: P, dn: Q, peak: Float64Array.from(c.reduce((a, v, i) => { a.push(i ? Math.max(a[i - 1], v) : v); return a; }, [])) };
  const idx = []; for (let j = 1; j < 600; j++) if (c[j] < c[j - 1] - 0.03) idx.push(j);
  const Rr = V.recovery(c, idx, 1, -1, 600, T);
  const times = idx.map((j) => { const k = scan(j + 1, c[j - 1], 600, true); return k < 0 ? 600 - j : k - j; });
  ok(Rr.back.n === idx.length && Rr.back.median === V.km(times, idx.map((j) => scan(j + 1, c[j - 1], 600, true) >= 0)).median, 'recovery times as a plain scan');
  // the analysis carries it, with the day looked at
  const rets = []; for (let i = 0; i < 500; i++) rets.push(0.0003 + 0.01 * normal());
  rets.push(-0.06);
  const A = V.decode(doc(rets).doc), R = V.analyze(A, { w: 1, measure: 'raw', mode: 'latest', band: 5 });
  const cc = V.cum(A.r), N = A.days.length - 1;
  ok(R.rec && R.rec.side === -1 && R.rec.sim.back.n > 0 && R.rec.base.high.n > 0, 'climb back and new high for days like it and every down day');
  near(R.rec.now.back, Math.expm1(cc[N - 1] - cc[N]), 'how far to climb back', 1e-12);
  ok(R.h[10] && R.h[10].sim, 'two weeks ahead');
  // the bell: a kernel density that adds up to about one
  const vals = Float64Array.from({ length: 2000 }, () => normal()).sort();
  const D = V.kde(vals, -6, 6, 241);
  near(D.ys.reduce((a, y) => a + y, 0) * (12 / 240), 1, 'the density integrates to one', 0.01);
  ok(V.PANELS.map((p) => p[0]).join() === 'now,1,5,10,21,back,high,vol', 'the panels a picture can hold');
}

// 6. volatility: realized, a stock ranked by its own volatility, a similar-volatility filter, an index judged by the S&P 500
{
  const rets = [];
  for (let i = 0; i < 700; i++) rets.push((i > 600 ? 0.03 : 0.01) * normal());
  const A = Object.assign(V.decode(doc(rets).doc), { last: 50 });
  const rv = V.realized(A.r, 21);
  const sd = (a) => { const m = a.reduce((x, y) => x + y, 0) / a.length; return Math.sqrt(a.reduce((x, y) => x + (y - m) * (y - m), 0) / (a.length - 1)); };
  near(rv[700], sd(Array.from(A.r).slice(679, 700)) * Math.sqrt(252), 'realized volatility of the last 21 days', 1e-9);
  ok(Number.isNaN(rv[20]) && Number.isFinite(rv[21]), '21 returns before the first');
  const R = V.analyze(A, { w: 1, measure: 'rv', mode: 'latest', band: 2.5 });
  near(R.value, rv[700], 'ranked by its own volatility', 1e-12);
  ok(R.at > 85 && R.rec === undefined && R.fvol && R.fvol.sim, 'a volatile stretch ranks high; no recovery for a level; the month after measured');
  const st = { w: 1, measure: 'raw', mode: 'latest', band: 10 };
  const Any = V.analyze(A, st), Sim = V.analyze(A, Object.assign({}, st, { vreg: 'similar' }));
  ok(Number.isFinite(Sim.reg) && Sim.h[1].all.n < Any.h[1].all.n && Sim.h[1].all.n > 0, 'similar volatility: fewer days, every one from a like stretch');
  // a volatility index: its level, and the S&P 500's returns on the same days
  const lv = [], sp = [];
  for (let i = 0; i < 500; i++) { lv.push(0.05 * normal()); sp.push(0.0005 + 0.01 * normal()); }
  const VX = Object.assign(V.decode(doc(lv).doc), { last: 20 }), SP = Object.assign(V.decode(doc(sp).doc), { name: 'S&P 500 index' });
  const L = V.analyze(VX, { w: 1, measure: 'level', mode: 'latest', band: 5 }, null, SP);
  const cv = V.cum(VX.r), cs = V.cum(SP.r), sorted = Float64Array.from(cv).sort();
  near(L.at, V.pctOf(sorted, cv[500]), 'the level ranked among every day');
  ok(L.out === 'S&P 500 index' && L.rec === undefined && L.fvol === undefined, 'judged by the S&P 500; no recovery, no volatility of the index');
  const f = []; for (let j = 0; j < 500; j++) if (L.sim[j] && j + 21 <= 500) f.push(Math.expm1(cs[j + 21] - cs[j]));
  ok(L.h[21].sim.n === f.length, 'the S&P 500 a month after each day at a like level');
  const W = V.analyze(VX, { w: 1, measure: 'level', mode: 'whatif', whatif: 40, band: 5 }, null, SP);
  near(W.value, Math.log(40 / 20) + cv[500], 'a what-if level', 1e-12);
  ok(!V.canDraw({ volIdx: true, rec: null }, 'vol') && !V.canDraw({ rec: null }, 'back') && V.canDraw({ rec: {} }, 'high') && V.canDraw({}, 'now'), 'a picture holds only the panels that apply');
}

// 7. the hub tab from an index file
{
  const fields = ['key', 'ticker', 'name', 'kind', 'sector', 'industry', 'cik', 'members', 'as_of', 'd0', 'n', 'last', 'move', 'pct', 'z', 'zpct', 'every', 'last_as', 'move5', 'pct5', 'move21', 'pct21',
    'sim1', 'sim5', 'sim21', 'ext1', 'ext5', 'ext21', 'all1', 'all5', 'all21'];
  const row = (o) => fields.map((f) => (f in o ? o[f] : null));
  const ix = { generated_at: '2026-10-31T00:00:00+00:00', as_of: '2026-10-30', breadth: { stocks: 1259, down5: 0.18, up5: 0.06 }, fields, rows: [
    row({ key: 'SPY', ticker: 'SPY', name: 'S&P 500 (SPY)', kind: 'market', as_of: '2026-10-30', move: -0.0177, pct: 4.24, every: 23.1, sim21: [126, 0.0332, 0.6984] }),
    row({ key: 'XLK', ticker: 'XLK', name: 'Technology sector (XLK)', kind: 'sector', as_of: '2026-10-30', move: -0.0489, pct: 0.5, every: 194, sim21: [74, 0.031, 0.64] }),
    row({ key: 'SIC-3674', name: 'Semiconductors & Related Devices (SIC 3674)', kind: 'industry', members: 43, as_of: '2026-10-30', move: -0.0647, pct: 0.61, move5: -0.0056, sim21: [76, 0.0496, 0.684] }),
    row({ key: 'NVDA', ticker: 'NVDA', name: 'NVIDIA CORP', kind: 'stock', sector: 'technology', as_of: '2026-10-30', move: -0.0422, pct: 6.16, z: -1.97, every: 16.2, sim21: [125, 0.0555, 0.64] }),
    row({ key: 'OLD', ticker: 'OLD', name: 'STALE INC', kind: 'stock', as_of: '2026-10-29', move: -0.3, pct: 0.01 }),
  ] };
  const rows = H.mvRows(ix);
  state.mvk = 'SPY';
  const m = H.mvMarket(rows, ix);
  ok(m.includes('S&amp;P 500 (SPY)') && m.includes('−1.8%') && m.includes('bottom 4.2%') && m.includes('18%'), 'market cards and breadth');
  ok(m.includes('data-mvk="XLK"') && m.includes('id="mv-one" data-k="SPY"'), 'sector cards and the analysis of the one picked');
  const i = H.mvIndustries(rows, ix);
  ok(i.includes('Semiconductors') && i.includes('>43<') && i.includes('bottom 0.61%'), 'industries table');
  state.mvs = 'falls';
  const s = H.mvStocks(rows, ix);
  ok(s.includes('NVDA') && !s.includes('STALE'), 'stocks with a close on the latest day only');
  ok(H.mvRank(99.5) === 'top 0.50%' && H.mvRank(3) === 'bottom 3.0%', 'rank words');
  H.movesDeepLink('SIC-3674'); ok(state.mvv === 'industries' && state.mvk === 'SIC-3674', 'deep link to an industry');
  H.movesDeepLink('nvda'); ok(state.mvv === 'one' && state.mvt === 'NVDA', 'deep link to a company');
  H.movesDeepLink('XLK'); ok(state.mvv === 'market' && state.mvk === 'XLK', 'deep link to a sector');
}
console.log(`moves view: ${n} checks passed`);
