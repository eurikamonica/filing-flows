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
  ok(V.PANELS.map((p) => p[0]).join() === 'now,paths,analog,sim,1,5,10,21,63,back,high,vol', 'the panels a picture can hold');
  // each case and the expected path after it: one line per chosen day, the mean of the cases at each day after
  const cs = V.cases(R, { w: 1, band: 5 }, 'sim');
  let nSim = 0; for (let j = 0; j < R.sim.length; j++) if (R.sim[j]) nSim++;
  ok(cs.length === nSim, 'a one-day move: every chosen day is a case');
  const E = V.expectedOf(cs);
  const at5 = cs.map((x) => x.path[5]).filter(Number.isFinite);
  near(E.mean[5], at5.reduce((a, b) => a + b, 0) / at5.length, 'the expected path is the average of the cases', 1e-12);
  ok(cs.every((x) => x.path[0] === 0 && x.path.length <= 64), 'each path starts at the day and runs a quarter at most');
  near(cs[0].path[21], Math.expm1(cc[cs[0].j + 21] - cc[cs[0].j]), 'a case a month on', 1e-12);
  const R5 = V.analyze(A, { w: 5, measure: 'raw', mode: 'latest', band: 10 });
  const c5 = V.cases(R5, { w: 5, band: 10 }, 'sim');
  ok(c5.every((x, i) => i === 0 || x.j - c5[i - 1].j >= 1) && c5.length <= R5.h[5].sim.n, 'a five-day move: overlapping days count once');
  // the filings that could move a day: after the close, the next trading day
  const ix = V.newsIndex({ events: [[A.days[100], '16:05', '8-K', '2.02'], [A.days[100], '09:00', '8-K', '8.01'], [A.days[100], '', '10-Q', '']] }, A.days);
  ok(ix.get(101).f.length === 1 && ix.get(100).f.length === 2, 'a release after the close moves the next day');
  // the headlines the same way, beside the filings; the days searched
  const hx = V.newsIndex({ events: [], checked: [A.days[100]], headlines: [[A.days[101], A.days[100], '20:15', 'Reuters', 'Acme beats estimates', 'https://news.google.com/rss/articles/x'],
    [A.days[100], A.days[100], '10:02', 'CNBC', 'Acme falls as <b>chip</b> demand slows', 'https://news.google.com/rss/articles/y'], ['1999-01-01', '1999-01-01', '', 'X', 'off the history', 'u']] }, A.days);
  ok(hx.get(101).h.length === 1 && hx.get(100).h[0][2] === 'CNBC' && hx.checked.has(A.days[100]), 'headlines under the move day they were found for');
  // the cases table: filings, then headlines (escaped, linked, with their source); the searched days that had none say so
  const Rc = V.analyze(A, { w: 1, measure: 'raw', mode: 'latest', band: 50 });
  const jc = V.cases(Rc, { w: 1, band: 50 }, 'sim')[0].j, dc = A.days[jc];
  const news = { events: [[dc, '09:00', '8-K', '2.02', 'Acme reports', '', [], '0000-1']], checked: [dc, A.days[120]],
    headlines: [[dc, dc, '10:02', 'CNBC', 'Acme falls as <b>chip</b> demand slows', 'https://news.google.com/rss/articles/y'], [dc, dc, '', 'WSJ', 'Acme dated only', 'u2']] };
  const html = V.casesSection(Rc, { w: 1, band: 50, set: 'sim', mode: 'latest' }, { kind: 'stock', cik: 1 }, news);
  ok(html.includes('and the headlines') && html.includes('mv-chip news">CNBC') && html.includes('Acme falls as &lt;b&gt;chip&lt;/b&gt;') && !html.includes('<b>chip</b>'), 'headlines in the cases table, escaped');
  ok(html.includes('Acme dated only') && !/Acme dated only<\/a> <span class="mv-sub" style="display:inline">[^<]* ET/.test(html), 'a headline dated only: no time');
  ok(html.includes('no filing that day (headlines not searched yet)') || html.includes('no filing or headline that day'), 'the empty cells say what was searched');
  const mk = V.casesSection(Rc, { w: 1, band: 50, set: 'sim', mode: 'latest' }, { kind: 'market', key: 'SPY' }, { headlines: news.headlines, checked: news.checked });
  ok(mk.includes('The headlines (that day') && mk.includes("the market's headlines"), 'the market: its headlines only');
  ok(V.fb(2.5) === '2.5' && V.fb(0.25) === '0.25' && V.fb('1.30') === '1.3' && V.fb(5) === '5', 'band labels');
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
  // the VIX beside a market with a shorter history: ranked in the VIX's own whole history, as on the VIX's page
  const vx = []; for (let i = 0; i < 600; i++) vx.push((i < 300 ? 0.06 : 0.01) * normal());
  const VX2 = Object.assign(V.decode(doc(vx).doc), { last: 19 });
  const mk = []; for (let i = 0; i < 299; i++) mk.push(0.01 * normal());
  const MK = Object.assign(V.decode(doc(mk, VX2.days[301]).doc), { last: 100 });
  const VD = V.volData({ A: MK, t: -1, vix: VX2 });
  const cvx = V.cum(VX2.r), lvAll = Float64Array.from(cvx, (c) => 19 * Math.exp(c - cvx[600]) / 100).sort();
  near(VD.vixNow, 0.19, 'the VIX on the latest day', 1e-12);
  near(VD.vixPct, V.pctOf(lvAll, 0.19), "the VIX ranked among all its days, not only the market's", 1e-12);
  ok(VD.vixSince === VX2.days[0] && MK.days[MK.days.length - 1] === VX2.days[600], 'since its first day');
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
  // a past day: every asset's move that day, ranked among its days up to then, and what actually followed
  const day = { date: '2026-10-15', fields: ['key', 'move', 'pct', 'z', 'move5', 'move21', 'next1', 'next5', 'next21'], breadth: { stocks: 2, down5: 0.5, up5: 0 },
    rows: [['NVDA', -0.061, 1.2, -3.1, -0.08, -0.1, 0.02, 0.045, 0.12], ['SPY', -0.021, 2.0, -2.5, -0.03, -0.02, 0.01, 0.02, 0.05], ['GONE', 0.1, 99, 3, 0, 0, 0, 0, 0]] };
  const past = H.mvPast(rows, day);
  ok(past.length === 2 && past.every((r) => r.past && r.as_of === '2026-10-15'), 'a past day joins the day file to the names, unknown keys left out');
  state.mvd = '2026-10-15'; state.mvs = 'falls';
  const ps = H.mvStocks(past, { as_of: '2026-10-15', breadth: day.breadth, past: true });
  ok(ps.includes('Oct 15, 2026') && ps.includes('Then: next day') && ps.includes('+12.0%') && ps.includes('−6.1%'), 'stocks on a past day with what followed');
  state.mvk = 'SPY';
  const pm = H.mvMarket(past, { as_of: '2026-10-15', breadth: day.breadth, past: true });
  ok(pm.includes('up to then') && pm.includes('data-d="2026-10-15"'), 'market cards on a past day, the analysis opened on that day');
  state.mvd = ''; H.movesDeepLink('stocks/2026-10-01'); ok(state.mvv === 'stocks' && state.mvd === '2026-10-01', 'deep link to a past day');
}

// 8. older days counting less: the weighted percentile, days like it, what followed and how long it took, against a
// plain reference written here; equal weights give back the unweighted numbers exactly
{
  const s = Float64Array.from({ length: 301 }, () => normal()).sort(), ones = new Float64Array(301).fill(1), cw = Float64Array.from({ length: 302 }, (_, i) => i);
  const Q = V.wquant(s, ones);
  ok([0, 5, 25, 50, 75, 95, 100, 37.3].every((q) => Math.abs(Q(q) - V.quantile(s, q)) < 1e-12), 'equal weights: the plain quantiles');
  ok([s[0], s[150], 0.1, s[300]].every((v) => Math.abs(V.pctW(s, cw, v) - V.pctOf(s, v)) < 1e-12), 'equal weights: the plain mid-rank percentile');
  const one = V.stats(Float64Array.from(s), new Uint8Array(301).fill(1), 1), oneW = V.stats(Float64Array.from(s), new Uint8Array(301).fill(1), 1, ones);
  ok(Math.abs(one.median - oneW.median) < 1e-12 && Math.abs(one.up - oneW.up) < 1e-12 && Math.abs(one.sd - oneW.sd) < 1e-12 && Math.abs(oneW.neff - 301) < 1e-9, 'equal weights: the plain summary');
  // a weighted Kaplan–Meier worked by hand: weights 1, 2, 1, 1
  const K = V.km([2, 3, 5, 5], [true, false, true, true], [1, 2, 1, 1]);
  ok(Math.abs(K.by(2) - 0.2) < 1e-12 && Math.abs(K.by(4) - 0.2) < 1e-12 && K.by(5) === 1 && K.median === 5 && K.n === 4, 'a weighted Kaplan–Meier');
  // a calm recent stretch after a wild one: with older days counting less, a −2.5% day is rarer
  const rets = [];
  for (let i = 0; i < 1500; i++) rets.push((i < 750 ? 0.03 : 0.008) * normal());
  rets.push(-0.025);
  const A = V.decode(doc(rets, '2015-01-05').doc);
  const o = { w: 1, measure: 'raw', mode: 'latest', band: 5, hl: 1 }, R = V.analyze(A, o), R0 = V.analyze(A, Object.assign({}, o, { hl: 0 }));
  const N = A.days.length - 1, c = V.cum(A.r), ref = Date.parse(A.days[N]);
  const wt = A.days.map((d) => Math.pow(0.5, Math.abs(ref - Date.parse(d)) / (365.25 * 864e5)));
  const x = (j) => c[j] - c[j - 1], v = x(N);
  let W = 0, Wb = 0; for (let j = 1; j <= N; j++) { W += wt[j]; if (x(j) < v) Wb += wt[j]; else if (x(j) === v) Wb += wt[j] / 2; }
  near(R.at, 100 * Wb / W, 'the weighted percentile', 1e-9);
  ok(R.at < R0.at && R.hl === 1 && Number.isFinite(R0.at) && R0.hl === undefined, 'rarer against the calm recent years than against all of them');
  const pw = (val) => { let b = 0; for (let j = 1; j <= N; j++) { if (x(j) < val) b += wt[j]; else if (x(j) === val) b += wt[j] / 2; } return 100 * b / W; };
  let simOk = true; const sim = [];
  for (let j = 1; j < N; j++) { const inn = Math.abs(pw(x(j)) - R.at) <= 5; if (inn !== !!R.sim[j]) simOk = false; if (inn) sim.push(j); }
  ok(simOk && sim.length > 20, 'days like it: within ±5 points of weighted percentile');
  let a = 0, b = 0, up = 0; const f = [];
  for (const j of sim) if (j + 21 <= N) { const r = Math.expm1(c[j + 21] - c[j]); a += wt[j]; b += wt[j] * wt[j]; if (r > 0) up += wt[j]; f.push([r, wt[j]]); }
  const S = R.h[21].sim;
  near(S.up, up / a, 'the weighted share that rose a month later', 1e-12);
  near(S.neff, a * a / b, 'how many days of full weight they are worth', 1e-9);
  f.sort((p, q) => p[0] - q[0]);                                     // the weighted median by hand: half the weight on each side
  let acc = 0, below = 0; for (const [r, ww] of f) { if (r < S.median) below += ww; acc += ww; }
  ok(Math.abs(below / acc - 0.5) < 0.5 * Math.max(...f.map((p) => p[1])) / acc + 1e-9, 'the weighted median splits the weight in half');
  let Wf = 0; for (let j = 1; j <= N; j++) if (R.side > 0 ? pw(x(j)) >= R.at - 1e-9 : pw(x(j)) <= R.at + 1e-9) Wf += wt[j];   // the day itself included
  near(R.every, W / Wf, 'a fall this large or larger: 1 in (all the weight ÷ the weight of such days)', 1e-9);
  ok(R.rec && R.rec.sim.back.n === R0.rec.sim.back.n || R.rec.sim.back.n > 0, 'how long it took, weighted');
  const D = V.kde(Float64Array.from(S.s), -0.5, 0.5, 401, S.sw);
  near(D.ys.reduce((p, q) => p + q, 0) * (1 / 400), 1, 'the weighted density integrates to one', 0.02);
  const Same = V.analyze(A, Object.assign({}, o, { hl: 0 }));
  ok(Same.at === R0.at && Same.h[21].sim.median === R0.h[21].sim.median && Same.sw === undefined, 'half-life 0: every day the same, as before');
}
// 9. similar stretches: the closest past paths (an exact copy found first), none overlapping, each ending with its months
// after before the stretch looked at; what to expect is their average; the simulation keeps a lone analog's path
{
  const rets = [];
  for (let i = 0; i < 1400; i++) rets.push(0.0003 + 0.012 * normal());
  const seg = rets.slice(300, 363);                                   // 63 days copied at the end: the stretch looked at
  for (const v of seg) rets.push(v);
  const A = V.decode(doc(rets, '2015-01-05').doc), N = A.days.length - 1, c = V.cum(A.r);
  const R = V.analyze(A, { w: 1, measure: 'raw', mode: 'latest', band: 5 });
  const AN = V.analogs(R, { alen: 63, afwd: 63, ak: 10, amatch: 'size' });
  ok(!AN.error && AN.items.length === 10 && AN.t === N, 'ten stretches like it');
  // the copy: the stretch ending on day 363 of the returns, i.e. close 363 (returns 300..362 lead from close 300 to 363)
  ok(AN.items[0].j === 363 && AN.items[0].d < 1e-3 && AN.items[0].corr > 0.999, 'the exact copy first, with no gap (whole basis points aside)');
  ok(AN.items.every((x, i) => i === 0 || x.d >= AN.items[i - 1].d - 1e-12), 'closest first');
  ok(AN.items.every((x) => x.j + 63 <= N - 63) && AN.items.every((x, i) => AN.items.every((y, k) => k === i || Math.abs(x.j - y.j) >= 63)), 'each ends with its months after before the stretch; none overlap');
  const mean63 = AN.items.reduce((a, x) => a + Math.expm1(c[x.j + 63] - c[x.j]), 0) / 10;
  near(AN.E.mean[63], mean63, 'what to expect: the average of what followed them', 1e-12);
  ok(AN.every[63] && AN.every[21] && AN.every[5] && !AN.every[126], 'every stretch, for comparison, at the marks within three months');
  // brute force: the gap of a few stretches from their definition
  const gap = (j) => { let ss = 0; for (let k = 0; k <= 63; k++) { const d = (c[j - 63 + k] - c[j - 63]) - (c[N - 63 + k] - c[N - 63]); ss += d * d; } return Math.sqrt(ss / 64); };
  ok(AN.items.every((x) => Math.abs(x.d - gap(x.j)) < 1e-12), 'the gap as defined');
  // shape only: a copy of the stretch at twice the size is alike in shape, not in size
  const r2 = rets.slice(0, 1400).concat(seg.map((v) => 2 * v));        // the stretch looked at: the copy at twice the size
  const A2 = V.decode(doc(r2, '2015-01-05').doc), R2 = V.analyze(A2, { w: 1, measure: 'raw', mode: 'latest', band: 5 });
  const S2 = V.analogs(R2, { alen: 63, afwd: 21, ak: 5, amatch: 'shape' }), Z2 = V.analogs(R2, { alen: 63, afwd: 21, ak: 5, amatch: 'size' });
  ok(S2.items[0].j === 363 && S2.items[0].d < 0.01, 'shape only: twice the size, the same shape');
  ok(Z2.items[0].j !== 363 || Z2.items[0].d > 0.01, 'size and shape: twice the size is not alike');
  // the simulation: seeded, ordered bands, and with one analog every path is that analog's path
  const sim = V.simulate(AN, 500, 42), sim2 = V.simulate(AN, 500, 42);
  ok(sim.band.q50[63] === sim2.band.q50[63] && sim.up === sim2.up, 'the same seed, the same paths');
  ok(sim.band.q5.every((v, d) => v <= sim.band.q25[d] + 1e-12 && sim.band.q25[d] <= sim.band.q50[d] + 1e-12 && sim.band.q50[d] <= sim.band.q75[d] + 1e-12 && sim.band.q75[d] <= sim.band.q95[d] + 1e-12), 'the bands in order');
  ok(sim.up >= 0 && sim.up <= 1 && sim.down10 >= 0 && sim.up10 <= 1 && sim.band.q50[0] === 0, 'shares between 0 and 1, every path from today');
  // a lone stretch that rose 0.1% every day after it: every week drawn from it is the same, so is every path
  const one = { F: 21, items: [{ fwd: Float64Array.from({ length: 22 }, (_, h) => 0.001 * h), w: 1 }] }, s1 = V.simulate(one, 50, 7);
  near(s1.band.q5[21], Math.expm1(0.021), 'a steady lone stretch: every path the same', 1e-6);
  near(s1.band.q95[13], Math.expm1(0.013), 'on every day', 1e-6);
  ok(s1.up === 1 && s1.down10 === 0, 'all of them higher, none down 10%');
  // weeks from anywhere in the months after: a crash on day 10 in three stretches can show in the first week too
  const crash = { F: 20, items: Array.from({ length: 10 }, (_, i) => ({ fwd: Float64Array.from({ length: 21 }, (_, h) => (i < 3 && h >= 10 ? Math.log(0.8) : 0)), w: 1 })) };
  const sc = V.simulate(crash, 4000, 3);
  ok(sc.band.q5[5] < -0.1 && sc.down10 > 0.05 && sc.down10 < 0.5, 'a crash week can come in the first week too');
  // not enough history: said, not drawn
  const As = V.decode(doc(rets.slice(0, 650), '2015-01-05').doc), Rs = V.analyze(As, { w: 1, measure: 'raw', mode: 'latest', band: 5 });
  const short = V.analogs(Rs, { alen: 252, afwd: 252, ak: 10 });
  ok(!!short.error, 'stretches longer than the history allows: an error');
  ok(V.canDraw({ an: AN, rec: {} }, 'analog') && !V.canDraw({ an: short, rec: {} }, 'analog') && !V.canDraw({ an: short, rec: {} }, 'sim'), 'the picture holds them only when there are stretches');
}
// 10. the hub's Indices & ETFs view: every index and ETF by group, the stocks and industries left out, a deep link to an index
{
  const fields = ['key', 'ticker', 'name', 'kind', 'as_of', 'd0', 'move', 'pct', 'every', 'sim21', 'rv21', 'rvpct', 'level', 'lpct', 'out21', 'group'];
  const row = (o) => fields.map((f) => (f in o ? o[f] : null));
  const ix = { as_of: '2026-10-30', fields, rows: [
    row({ key: 'SPY', ticker: 'SPY', name: 'S&P 500 (SPY)', kind: 'market', group: 'market', as_of: '2026-10-30', d0: '1993-01-29', move: -0.0177, pct: 4.2, every: 23, sim21: [126, 0.033, 0.69], rv21: 0.12, rvpct: 40 }),
    row({ key: 'IDX-N225', name: 'Nikkei 225 (Japan)', kind: 'index', group: 'world', as_of: '2026-10-30', d0: '1965-01-05', move: 0.012, pct: 80, every: 5, sim21: [300, 0.01, 0.6] }),
    row({ key: 'EWJ', ticker: 'EWJ', name: 'Japan (EWJ)', kind: 'etf', group: 'country', as_of: '2026-10-30', d0: '1996-03-18', move: 0.004, pct: 60 }),
    row({ key: 'IDX-VIX', name: 'CBOE Volatility Index (VIX)', kind: 'volatility', group: 'volatility', as_of: '2026-10-30', level: 19.4, lpct: 60, move: 0.13, out21: [500, 0.011, 0.59] }),
    row({ key: 'NVDA', ticker: 'NVDA', name: 'NVIDIA CORP', kind: 'stock', as_of: '2026-10-30', move: -0.04, pct: 6 }),
  ] };
  state.mvk = 'IDX-N225';
  const h = H.mvAll(H.mvRows(ix), ix);
  ok(h.includes('World indices') && h.includes('Country ETFs') && h.includes('Volatility indices') && h.includes('Nikkei 225 (Japan)') && h.includes('19.4'), 'grouped tables');
  ok(!h.includes('NVIDIA') && h.includes('id="mv-one" data-k="IDX-N225"') && h.includes('>1965<'), 'no stocks; the one picked analysed below; history from');
  H.movesDeepLink('IDX-N225'); ok(state.mvv === 'all' && state.mvk === 'IDX-N225', 'deep link to a world index');
  H.movesDeepLink('IDX-VIX'); ok(state.mvv === 'market', 'the VIX stays with the market');
  H.movesDeepLink('all'); ok(state.mvv === 'all', 'deep link to the view');
}
console.log(`moves view: ${n} checks passed`);
