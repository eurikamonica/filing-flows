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

// 5. the hub tab from an index file
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
