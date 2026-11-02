// rrg-lab.js: the RRG formula for every frequency, the next period's crossing prices, the forecast path with dates and
// prices (stepping the real moves reproduces the chart), the daily files (decoding, trading days, weeks), the in-browser
// research and the line-now odds. Offline; no browser.
const assert = require('node:assert/strict');
const path = require('node:path');
const L = require(path.join(__dirname, '..', 'docs', 'rrg-lab.js'));
const RV = require(path.join(__dirname, '..', 'docs', 'rrg-company-view.js'))._t;
let n = 0;
const ok = (v, m) => { assert.ok(v, m); n++; };
const near = (a, b, m, tol = 1e-9) => { assert.ok(Math.abs(a - b) <= tol, `${m}: ${a} vs ${b}`); n++; };
const series = (N, f) => Array.from({ length: N }, (_, i) => f(i));

// 1. weekly states equal the company view's (the formula the server's transition model was tested against)
const N = 400, rs = series(N, (i) => 100 * Math.exp(0.001 * i + 0.05 * Math.sin(i / 8) + 0.02 * Math.cos(i / 3)));
const W = L.states(rs, 4, 14, Math.max(52, 42), 26), C = RV.states(rs, 14);
for (let k = 0; k < N; k++) {
  const a = W.x[k], b = C.x[k];
  assert.ok((a == null && !Number.isFinite(b)) || Math.abs(a - b) < 1e-12, 'weekly RS-Ratio differs from the company view at ' + k);
  const c = W.y[k], d = C.y[k];
  assert.ok((c == null && !Number.isFinite(d)) || Math.abs(c - d) < 1e-12, 'weekly RS-Momentum differs at ' + k);
}
n++;

// 2. every frequency: stepping the real moves forward reproduces the chart; the thresholds are where x / y cross 100
for (const fq of ['w', 'm', 'd']) {
  const P = L.PAR[fq], nn = fq === 'd' ? 21 : fq === 'w' ? 14 : 10, M = fq === 'd' ? 900 : 400;
  const r = series(M, (i) => 100 * Math.exp(0.0005 * i + 0.04 * Math.sin(i / (fq === 'd' ? 17 : 7)) + 0.015 * Math.cos(i / 2.3)));
  const S = L.states(r, P.sh, nn, P.long(nn), P.minNorm), k = M - P.steps - 1;
  const moves = [series(P.steps, (j) => Math.log(r[k + 1 + j] / r[k + j]))], st = L.stepPaths(S, r, k, moves, P.steps)[0];
  for (let j = 0; j < P.steps; j++) { near(st.x[j], S.x[k + 1 + j], `${fq}: stepped RS-Ratio`, 1e-8); near(st.y[j], S.y[k + 1 + j], `${fq}: stepped RS-Momentum`, 1e-8); }
  const kl = M - 1, th = L.thresholds(S, r, kl);
  near(L.stepPaths(S, r, kl, [[Math.log(th.mx)]], 1)[0].x[0], 100, `${fq}: RS-Ratio crosses 100 at the threshold`, 1e-8);
  near(L.stepPaths(S, r, kl, [[Math.log(th.my)]], 1)[0].y[0], 100, `${fq}: RS-Momentum crosses 100 at the threshold`, 1e-8);
  // the ladder: just below the lower cut both coordinates under 100 (Lagging), just above the higher one Leading
  const lad = L.ladder(50, th), lo = Math.min(th.mx, th.my), hi = Math.max(th.mx, th.my);
  const at = (m) => { const p = L.stepPaths(S, r, kl, [[Math.log(m)]], 1)[0]; return L.quad(p.x[0], p.y[0]); };
  ok(at(lo * 0.999) === 2 && at(hi * 1.001) === 0 && at((lo + hi) / 2) === lad.bands[1][0], `${fq}: the ladder's quadrants`);
  near(lad.ratio, 50 * th.mx, `${fq}: the RS-Ratio price`);
}

// 3. the forecast path: closes and benchmark on one grid; replays, dates, prices, shares
{
  const M = 600, B = series(M, (i) => 300 * Math.exp(0.0004 * i + 0.01 * Math.sin(i / 5))), Cl = series(M, (i) => B[i] * 0.5 * Math.exp(0.05 * Math.sin(i / 9) + 0.02 * Math.cos(i / 2.7)));
  const r = Cl.map((v, i) => 100 * v / B[i]), S = L.states(r, 4, 14, 52, 26), calc = { ...S, rs: r, c: Cl, b: B };
  const F = L.forecast(calc, M - 1, 'w');
  ok(F && F.n === 156 - 13 + 1 && F.steps.length === 13, 'one replay per 13-week run of the last 156 weeks');
  ok(F.steps.every((s) => s.p10 <= s.p25 && s.p25 <= s.p50 && s.p50 <= s.p75 && s.p75 <= s.p90), 'price ranges in order');
  near(F.steps[0].q.reduce((a, b) => a + b, 0), 1, 'quadrant shares add to 1');
  ok(F.steps[12].left >= F.steps[0].left, 'the share that left today\'s quadrant only grows');
  near(F.close, Cl[M - 1], 'the close the path starts from');
  ok(L.forecast(calc, 100, 'w') === null || L.forecast(calc, 100, 'w').n < 156, 'fewer replays early on');
  ok(L.forecast({ ...calc, c: null }, M - 1, 'w') === null, 'no closes: no path');
}

// 4. dates ahead: Fridays, months, trading days (weekends skipped)
ok(L.ahead('2026-10-30', 'w', 13) === '2027-01-29', '13 weeks after a Friday');
ok(L.ahead('2026-10', 'm', 3) === '2027-01', 'three months on');
ok(L.ahead('2026-10-30', 'd', 1) === '2026-11-02' && L.ahead('2026-10-30', 'd', 5) === '2026-11-06' && L.ahead('2026-10-30', 'd', 21) === '2026-11-30', 'trading days skip weekends');
ok(L.ahead('2026-10-30', 'w', -1) === '2026-10-23', 'a week back');

// 5. the daily files: decoding (gaps in base 36, returns in bp), SPY's days, forward fill, the last close of each week
{
  const doc = { key: 'XLK', name: 'Technology sector (XLK)', kind: 'sector', group: 'sector', last: 110, d0: '2026-10-19', gaps: '1113', r: [100, -50, 200, 0] };
  const d = L.decodeMoves(doc);
  assert.deepEqual(d.days, ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-25']); n++;
  near(d.c[4], 110, 'ends at the raw last close');
  near(d.c[1] / d.c[0], Math.exp(0.01), 'a 100 bp day');
  const spy = L.decodeMoves({ key: 'SPY', last: 500, d0: '2026-10-19', gaps: '11113111', r: [0, 0, 0, 0, 0, 0, 0, 0] });
  const G = L.makeGrid(spy);
  ok(G.n === 9 && G.spy.every((v) => v === 500), 'SPY\'s days are the grid');
  const hole = L.decodeMoves({ key: 'X', last: 10, d0: '2026-10-19', gaps: '21', r: [10, 20] }), on = L.onDays(G, hole);
  ok(on[0] != null && on[1] === on[0] && on[2] != null && on[3] != null && on[4] == null, 'a missing day filled from the day before, nothing past the last day');
  const wk = L.toWeekly(['2026-10-16', '2026-10-23', '2026-10-30'], d);
  ok(wk[0] == null && Math.abs(wk[1] - d.c[3]) < 1e-12 && wk[2] != null, 'the last close of each week (Thursday when Friday is missing)');
  near(wk[2], d.c[4], 'a Sunday close counts in the week to the next Friday');
}

// 6. research on lines that rotate clockwise like clockwork, and the line-now odds
{
  const M = 520, days = series(M, (i) => new Date(Date.UTC(2010, 0, 1) + i * 6048e5).toISOString().slice(0, 10));
  const mk = (ph) => { const x = series(M, (i) => 100 + 1.5 * Math.cos(2 * Math.PI * i / 20 + ph)), y = series(M, (i) => 100 - 1.5 * Math.sin(2 * Math.PI * i / 20 + ph));
    const b = series(M, (i) => 100 * Math.exp(0.001 * i)), c = series(M, (i) => b[i] * Math.exp(0.02 * Math.sin(2 * Math.PI * i / 20 + ph))); return { x, y, c, b }; };
  const lines = [mk(0), mk(1), mk(2.5)];
  const R = L.research(lines, days, [1, 4, 13, 26], 'weeks');
  ok(R.lines === 3 && R.from === days[0] && R.to === days[M - 1], 'three lines over the whole grid');
  ok(R.direction.clockwise === 1 && R.direction.counter_clockwise === 0, 'every change clockwise');
  ok(R.cycles.median === 20, 'a loop every 20 weeks');
  ok(['leading', 'weakening', 'lagging', 'improving'].every((q) => R.dwell[q].median === 5), 'five weeks in each quadrant');
  const lag = R.lagging;
  ok(lag.entries > 70 && lag.improving['13'].share === 1 && lag.improving['1'].share === 0 && lag.periods_to_improving.median === 5, 'out of Lagging after about five weeks, every time');
  ok(R.boundaries.find((b) => b.key === 'improving_to_leading').crossed['4'].share === 1, 'every approach to Leading crossed');
  ok(R.boundaries.find((b) => b.key === 'weakening_to_leading').episodes === 0, 'no re-acceleration in a clean loop');
  const T = R.transitions['1'];
  ok(T[0][1] > 0 && T[0][3] === 0 && T[2][1] === 0, 'transitions only to the next quadrant clockwise');
  // the line now: in Lagging, heading for Improving; odds counted from similar line-weeks
  const f = M - 1 - 6;
  const now = L.nowOdds(lines, f, [4, 13]);
  ok(now.length === 3 && now.every((r) => r && r.bounds.length >= 1), 'a row per line');
  const g = now.find((r) => r.q === 2);
  ok(!g || (g.lag && g.lag.by[13].improving === 1 && g.lag.by[13].n > 0), 'a lagging line: all similar lines reached Improving within 13 weeks');
  ok(now.every((r) => r.bounds.every((b) => Object.values(b.by).every((v) => v.share == null || (v.share >= 0 && v.share <= 1)))), 'shares between 0 and 1');
}
console.log(`RRG lab: ${n} checks passed`);
