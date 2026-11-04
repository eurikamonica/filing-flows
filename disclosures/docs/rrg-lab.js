/* 4.6c RRG lab — the parts of the hub's RRG (rrg.js) that go beyond the standard chart, and the Rotation research view.
   · The RRG formula for every frequency (weekly, monthly, daily) in one place: RS = 100 × close ÷ benchmark, smoothed
     (4 weeks / 2 months / 5 trading days), its n-period trend, the gap and its smoothed change, each in standard units of
     its own last year or more (52 weeks, 24 months, 252 trading days; at least 26 / 26 / 126 periods on file).
   · Daily lines: the move-odds files (data/research/paths/moves/a/<KEY>.json: each asset's adjusted daily closes since
     its first day) against SPY's, on SPY's trading days; the same files give the weekly chart the countries, regions,
     bonds, commodities and industry ETFs the weekly history does not carry (the last close of each week).
   · The price at every point, the next period's prices that would move RS-Ratio or RS-Momentum through 100 (exact from
     the formula, the benchmark held flat), and a forecast path: every run of the line's own and its benchmark's moves in
     the last three years replayed from the date shown through the formula (the server's replay, transition_rrg), drawn
     as the median position each period with dates and the replayed prices (median, 50% and 80% ranges), and the share
     of replays in each quadrant.
   · Research on the lines of the chart, in the browser (rrg_research.py's numbers): how often a line near a quadrant line
     and moving toward it crossed within h periods or turned back, whether Lagging lines rebounded, how long lines stay,
     which way they turn, how long a loop takes; and, for the line now, the same counted over the history of lines in a
     similar spot. The Rotation research view reads the server's numbers for the whole universe (sectors, index ETFs,
     styles, countries, bonds and commodities, industries and companies; weekly and daily).
   Pure functions exported for Node (tests); the hub's helpers (state, esc, fmt, table, field, tip, curve, rrgDay…) are
   used only by the view functions. Rotation history, not investment advice. */
(function (root) {
  'use strict';
  const isF = (v) => typeof v === 'number' && Number.isFinite(v);
  const PAR = {
    w: { sh: 4, long: (n) => Math.max(52, 3 * n), minNorm: 26, steps: 13, window: 156, marks: [1, 2, 4, 8, 13], H: [1, 4, 13, 26], one: 'week', many: 'weeks', ab: 'w', lag: 52, hiN: 52, hiMin: 45, vN: 13, vMin: 10 },
    m: { sh: 2, long: (n) => Math.max(24, 3 * n), minNorm: 26, steps: 6, window: 60, marks: [1, 2, 3, 6], H: [1, 3, 6, 12], one: 'month', many: 'months', ab: 'mo', lag: 12, hiN: 52, hiMin: 45, vN: 13, vMin: 10 },
    d: { sh: 5, long: (n) => Math.max(252, 3 * n), minNorm: 126, steps: 21, window: 756, marks: [1, 2, 5, 10, 21], H: [1, 5, 21, 63], one: 'trading day', many: 'trading days', ab: 'd', lag: 252, hiN: 252, hiMin: 230, vN: 63, vMin: 55 },
  };
  // the path as drawn: the median positions smoothed over three steps (¼ · ½ · ¼, the ends kept), so the line reads as
  // a path and not as the jitter of medians taken step by step; the tips keep each step's own medians
  function smoothPath(steps) {
    const P = steps.map((st) => (isF(st.x50) && isF(st.y50) ? [st.x50, st.y50] : null));
    return P.map((p, i) => {
      if (!p) return null;
      const a = i > 0 ? P[i - 1] : null, b = i < P.length - 1 ? P[i + 1] : null;
      if (!a || !b) return p;
      return [0.25 * a[0] + 0.5 * p[0] + 0.25 * b[0], 0.25 * a[1] + 0.5 * p[1] + 0.25 * b[1]];
    });
  }
  const NEAR = 1, SPEED = [0.25, 0.5], DEPTH = [1, 2], CAP = 1300;
  const QN = ['leading', 'weakening', 'lagging', 'improving'];
  const QT = ['Leading', 'Weakening', 'Lagging', 'Improving'];
  // key, from, to, axis, +1 when the coordinate rises through 100 (rrg_research.BOUNDS)
  const BOUNDS = [['improving_to_leading', 3, 0, 'x', 1], ['leading_to_weakening', 0, 1, 'y', -1], ['weakening_to_lagging', 1, 2, 'x', -1],
    ['lagging_to_improving', 2, 3, 'y', 1], ['weakening_to_leading', 1, 0, 'y', 1], ['improving_to_lagging', 3, 2, 'y', -1]];
  const quad = (x, y) => (x >= 100 ? (y >= 100 ? 0 : 1) : (y < 100 ? 2 : 3));

  /* ---------- the formula ---------- */
  function ema(a, span) {                               // rrg.js's: a missing value restarts the average
    const al = 2 / (span + 1), o = new Array(a.length).fill(null);
    let m = null, c = 0;
    for (let k = 0; k < a.length; k++) {
      if (!isF(a[k])) { m = null; c = 0; continue; }
      m = m == null ? a[k] : m + al * (a[k] - m); c++;
      o[k] = c >= Math.min(span, 6) ? m : null;
    }
    return o;
  }
  function states(rs, sh, n, long, minNorm) {
    const s = ema(rs, sh), t = ema(s, n), dev = s.map((v, k) => (v != null && t[k] ? 100 * (v / t[k] - 1) : null));
    const roc = ema(dev.map((v, k) => (k && v != null && dev[k - 1] != null ? v - dev[k - 1] : null)), sh);
    const mn = Math.min(long, minNorm);
    const norm = (a) => a.map((v, k) => {
      if (v == null) return null;
      let s2 = 0, m = 0;
      for (let i = Math.max(0, k - long + 1); i <= k; i++) if (a[i] != null) { s2 += a[i] * a[i]; m++; }
      return m >= mn && s2 > 0 ? 100 + v / Math.sqrt(s2 / m) : null;
    });
    const x = norm(dev), y = norm(roc).map((v, k) => (x[k] == null ? null : v));
    return { s, t, dev, roc, x, y, sh, n, long, minNorm };
  }
  // next period's relative level (× today's) at which RS-Ratio (dev = 0) and RS-Momentum (roc = 0) cross 100
  function thresholds(S, rs, k) {
    const a1 = 2 / (S.sh + 1), a2 = 2 / (S.n + 1), s = S.s[k], t = S.t[k];
    if (![s, t, S.dev[k], S.roc[k], rs[k]].every(isF)) return { mx: NaN, my: NaN };
    const rsFor = (g) => { const s1 = g * t * (1 - a2) / (1 - g * a2); return s + (s1 - s) / a1; };
    const gy = 1 + (S.dev[k] + S.roc[k] * (1 - 1 / a1)) / 100;
    const mx = rsFor(1) / rs[k], my = gy * a2 < 1 ? rsFor(gy) / rs[k] : NaN;
    return { mx: mx > 0 ? mx : NaN, my: my > 0 ? my : NaN };
  }
  // the quadrant next period as a function of the close (benchmark flat): the cut points and the four ranges
  function ladder(close, th) {
    const { mx, my } = th;
    if (!isF(close) || !isF(mx) || !isF(my)) return null;
    const lo = Math.min(mx, my), hi = Math.max(mx, my), mid = mx < my ? 1 : 3;
    return { ratio: close * mx, momentum: close * my, bands: [[2, null, close * lo], [mid, close * lo, close * hi], [0, close * hi, null]] };
  }
  // relative moves P[path][step] stepped forward from period k (transition_rrg.step_paths, any frequency)
  function stepPaths(S, rs, k, P, steps) {
    const a1 = 2 / (S.sh + 1), a2 = 2 / (S.n + 1), L = S.long, mn = Math.min(L, S.minNorm);
    const tail = (A, j) => { let s2 = 0, m = 0; for (let i = Math.max(0, k - L + 1 + j); i <= k; i++) if (isF(A[i])) { s2 += A[i] * A[i]; m++; } return [s2, m]; };
    const TD = [], TR = [];
    for (let j = 1; j <= steps; j++) { TD[j] = tail(S.dev, j); TR[j] = tail(S.roc, j); }
    return P.map((p) => {
      let s = S.s[k], t = S.t[k], roc = S.roc[k], dprev = S.dev[k], c = 0, dq = 0, rq = 0;
      const out = { cum: [], x: [], y: [] };
      p.forEach((r, j) => {
        c += r;
        const v = rs[k] * Math.exp(c);
        s += a1 * (v - s); t += a2 * (s - t);
        const dev = 100 * (s / t - 1);
        roc += a1 * ((dev - dprev) - roc); dprev = dev;
        dq += dev * dev; rq += roc * roc;
        const [bd, nd] = TD[j + 1], [br, nr] = TR[j + 1], md = nd + j + 1, mr = nr + j + 1;
        out.cum.push(c);
        out.x.push(md >= mn && bd + dq > 0 ? 100 + dev / Math.sqrt((bd + dq) / md) : NaN);
        out.y.push(mr >= mn && br + rq > 0 ? 100 + roc / Math.sqrt((br + rq) / mr) : NaN);
      });
      return out;
    });
  }
  const qtl = (a, p) => { const s = a.filter(isF).sort((u, v) => u - v); if (!s.length) return NaN; const i = (s.length - 1) * p, lo = Math.floor(i); return s[lo] + (s[Math.min(s.length - 1, lo + 1)] - s[lo]) * (i - lo); };
  const lr = (A, i) => (i > 0 && A[i] > 0 && A[i - 1] > 0 ? Math.log(A[i] / A[i - 1]) : NaN);
  /* the forecast path from period k: every `steps`-long run of the line's own and its benchmark's moves in the last
     `window` periods, replayed through the formula; the median position each step, the replayed prices, the shares of
     replays in each quadrant and that have left today's quadrant. calc: rrgCalc's output (closes c, benchmark b, states). */
  function forecast(calc, k, fq, opt = {}) {
    const p = PAR[fq], steps = opt.steps || p.steps, win = opt.window || p.window;
    if (!calc || !(k >= 1) || !isF(calc.x[k]) || !isF(calc.y[k]) || !calc.c || !calc.b) return null;
    if (![calc.s[k], calc.t[k], calc.dev[k], calc.roc[k], calc.rs[k], calc.c[k]].every(isF)) return null;
    const Pr = [], Po = [], s0 = Math.max(1, k - win + 1), n0 = k - s0 + 1;
    const LO = new Float64Array(n0), LB = new Float64Array(n0);      // the moves once, then every window of them
    for (let i = 0; i < n0; i++) { LO[i] = lr(calc.c, s0 + i); LB[i] = lr(calc.b, s0 + i); }
    let bad = -1;                                                     // the last missing move before the window's end
    for (let e = 0; e < n0; e++) {
      if (!isF(LO[e]) || !isF(LB[e])) bad = e;
      const st = e - steps + 1;
      if (st < 0 || bad >= st) continue;
      const r = new Array(steps), o = new Array(steps);
      for (let j = 0; j < steps; j++) { o[j] = LO[st + j]; r[j] = LO[st + j] - LB[st + j]; }
      Pr.push(r); Po.push(o);
    }
    if (Pr.length < (opt.min || 30)) return null;
    const paths = stepPaths(calc, calc.rs, k, Pr, steps), close = calc.c[k], q0 = quad(calc.x[k], calc.y[k]);
    const own = Po.map((o) => { let c = 0; return o.map((r) => (c += r)); });
    const left = new Uint8Array(paths.length), seen = paths.map(() => [0, 0, 0, 0]);
    const sq = (a, m, p) => { if (!m) return NaN; const i = (m - 1) * p, lo = Math.floor(i), hi = Math.min(m - 1, lo + 1); return a[lo] + (a[hi] - a[lo]) * (i - lo); };
    const out = [], NP = paths.length, xs = new Float64Array(NP), ys = new Float64Array(NP), cs = new Float64Array(NP);
    for (let j = 0; j < steps; j++) {
      const qs = [0, 0, 0, 0];
      let m = 0, up = 0;
      for (let i = 0; i < NP; i++) {
        const P = paths[i], x = P.x[j], y = P.y[j], c = own[i][j];
        cs[i] = c; if (c > 0) up++;
        if (!isF(x) || !isF(y)) continue;
        xs[m] = x; ys[m] = y; m++;
        const q = quad(x, y);
        qs[q]++; seen[i][q] = 1;
        if (q !== q0) left[i] = 1;
      }
      const X = xs.subarray(0, m).sort(), Y = ys.subarray(0, m).sort(), Cs = cs.slice().sort();
      const px = (pp) => close * Math.exp(sq(Cs, NP, pp));
      let nl = 0; for (let i = 0; i < NP; i++) nl += left[i];
      out.push({ j: j + 1, n: m, x50: sq(X, m, 0.5), y50: sq(Y, m, 0.5), x10: sq(X, m, 0.1), x90: sq(X, m, 0.9), y10: sq(Y, m, 0.1), y90: sq(Y, m, 0.9),
        p10: px(0.1), p25: px(0.25), p50: px(0.5), p75: px(0.75), p90: px(0.9), up: up / NP,
        q: qs.map((v) => (m ? v / m : NaN)), left: nl / NP,
        reached: [0, 1, 2, 3].map((q) => { let c = 0; for (let i = 0; i < NP; i++) c += seen[i][q]; return c / NP; }) });
    }
    return { k, n: paths.length, close, q0, th: thresholds(calc, calc.rs, k), steps: out, window: win };
  }
  // the date `j` periods after `day` (Fridays a week apart; month labels; weekdays for trading days, holidays ignored)
  function ahead(day, fq, j) {
    const s = String(day || '');
    if (fq === 'm') { const [y, m] = s.split('-').map(Number); const t = y * 12 + (m - 1) + j; return `${Math.floor(t / 12)}-${String(t % 12 + 1).padStart(2, '0')}`; }
    const d = new Date(s.slice(0, 10) + 'T00:00:00Z');
    if (!Number.isFinite(d.getTime())) return '';
    if (fq === 'w') d.setUTCDate(d.getUTCDate() + 7 * j);
    else for (let left = j; left > 0;) { d.setUTCDate(d.getUTCDate() + 1); const w = d.getUTCDay(); if (w !== 0 && w !== 6) left--; }
    return d.toISOString().slice(0, 10);
  }

  /* ---------- the daily files ---------- */
  function decodeMoves(doc) {                         // moves.py's format: d0 + base-36 day gaps (or dates), returns in bp
    let days;
    if (doc.dates) days = doc.dates.slice();
    else {
      days = [doc.d0];
      let t = Date.parse(doc.d0 + 'T00:00:00Z');
      for (const ch of doc.gaps || '') { t += parseInt(ch, 36) * 864e5; days.push(new Date(t).toISOString().slice(0, 10)); }
    }
    const r = doc.r || [], cum = [0];
    for (let i = 0; i < r.length; i++) cum.push(cum[i] + r[i] / 1e4);
    const N = cum.length - 1, last = isF(doc.last) && doc.last > 0 ? doc.last : null, base = last || 100;
    return { key: doc.key, ticker: doc.ticker, name: doc.name, kind: doc.kind, group: doc.group, sector: doc.sector, links: doc.links || {},
      days: days.slice(0, cum.length), c: cum.map((v) => base * Math.exp(v - cum[N])), last, level: !last };
  }
  // closes on another set of trading days: forward-filled for up to 5 days inside the asset's own range
  function onDays(grid, md, fill = 5) {
    const out = new Array(grid.days.length).fill(null);
    if (!md || !md.days.length) return out;
    for (let i = 0; i < md.days.length; i++) { const g = grid.pos.get(md.days[i]); if (g != null) out[g] = md.c[i]; }
    const a = grid.pos.get(md.days[0]) ?? out.findIndex((v) => v != null), b = out.length - 1 - [...out].reverse().findIndex((v) => v != null);
    let gap = 0;
    for (let i = Math.max(1, a); i <= b && a >= 0; i++) {
      if (out[i] == null) { if (out[i - 1] != null && gap < fill) { out[i] = out[i - 1]; gap++; } }
      else gap = 0;
    }
    return out;
  }
  // the last close of each week on the weekly grid (Fridays): the last trading day in (Friday − 7, Friday]
  function toWeekly(gridDays, md) {
    const out = new Array(gridDays.length).fill(null);
    if (!md) return out;
    let i = 0;
    for (let g = 0; g < gridDays.length; g++) {
      const fri = gridDays[g], lo = ahead(fri, 'w', -1);
      while (i < md.days.length && md.days[i] <= fri) i++;
      if (i > 0 && md.days[i - 1] > lo) out[g] = md.c[i - 1];
    }
    return out;
  }
  function makeGrid(spy) {
    const days = spy.days.slice(), pos = new Map(days.map((d, i) => [d, i]));
    const g = { days, pos, n: days.length };
    g.idx = days.map((_, i) => i);
    g.spy = onDays(g, spy);
    return g;
  }

  /* ---------- research on a set of lines (rrg_research.Research, the same numbers) ---------- */
  const rint = (v) => { const f = Math.floor(v), d = v - f; return d > 0.5 || (d === 0.5 && f % 2 !== 0) ? f + 1 : f; };
  class Hist {
    constructor() { this.c = new Array(CAP + 1).fill(0); }
    add(v) { if (v >= 0) this.c[Math.min(v, CAP)]++; }
    summary() {
      const n = this.c.reduce((a, b) => a + b, 0);
      if (!n) return { n: 0 };
      const cum = []; let s = 0, w = 0;
      this.c.forEach((v, i) => { s += v; cum.push(s); w += v * i; });
      const q = (p) => cum.findIndex((v) => v >= p * n);
      return { n, median: q(0.5), p25: q(0.25), p75: q(0.75), mean: Math.round((w / n) * 100) / 100 };
    }
  }
  class RHist {
    constructor() { this.W = 0.001; this.LIM = 1; this.nb = Math.round(2 * this.LIM / this.W) + 1; this.c = new Array(this.nb).fill(0); this.n = 0; this.s = 0; this.up = 0; }
    add(v) { if (!isF(v)) return; const b = Math.min(this.nb - 1, Math.max(0, rint((v + this.LIM) / this.W))); this.c[b]++; this.n++; this.s += v; if (v > 0) this.up++; }
    summary() {
      if (!this.n) return { n: 0 };
      const cum = []; let s = 0;
      for (const v of this.c) { s += v; cum.push(s); }
      const q = (p) => Math.expm1(cum.findIndex((v) => v >= p * this.n) * this.W - this.LIM);
      const r4 = (v) => Math.round(v * 1e4) / 1e4;
      return { n: this.n, median: r4(q(0.5)), p25: r4(q(0.25)), p75: r4(q(0.75)), mean: r4(Math.expm1(this.s / this.n)), up: r4(this.up / this.n) };
    }
  }
  const pr = (c) => ({ hits: c[0], n: c[1], share: c[1] ? Math.round((c[0] / c[1]) * 1e4) / 1e4 : null });
  // research over lines [{x, y, c, b}] on one grid (days: the dates); H the horizons in periods
  function research(lines, days, H, unit) {
    const Hm = Math.max(...H), hm = H[Math.floor(H.length / 2)], hs = H.length > 1 ? H[1] : H[0];
    const R = { lines: 0, first: null, last: null, trans: Object.fromEntries(H.map((h) => [h, [0, 1, 2, 3].map(() => [0, 0, 0, 0])])) };
    const B = Object.fromEntries(BOUNDS.map((b) => [b[0], { episodes: 0, crossed: Object.fromEntries(H.map((h) => [h, [0, 0]])), landed: [0, 0], time: new Hist(), speed: [[0, 0, 0], [0, 0, 0], [0, 0, 0]] }]));
    const hz = () => Object.fromEntries(H.map((h) => [h, [0, 0]]));
    const G = { entries: 0, improving: hz(), leading: hz(), weakening: hz(), time: new Hist(), depth: new RHist(),
      rel: Object.fromEntries(H.map((h) => [h, new RHist()])), abs: Object.fromEntries(H.map((h) => [h, new RHist()])), states: [] };
    for (let d = 0; d < 3; d++) for (let u = 0; u < 2; u++) G.states.push({ d, u, n: 0, improving: hz(), rel: new RHist() });
    const QR = [0, 1, 2, 3, 4].map(() => Object.fromEntries(H.map((h) => [h, new RHist()]))), QA = [0, 1, 2, 3, 4].map(() => Object.fromEntries(H.map((h) => [h, new RHist()])));
    const dwell = [0, 1, 2, 3].map(() => new Hist()), dirn = [0, 0, 0], cycle = new Hist();
    for (const L of lines) {
      const W = L.x.length, x = L.x.map((v) => (isF(v) ? v : NaN)), y = L.y.map((v) => (isF(v) ? v : NaN));
      const q = x.map((v, t) => (isF(v) && isF(y[t]) ? quad(v, y[t]) : -1)), D = q.map((v) => v >= 0);
      if (!D.some(Boolean)) continue;
      R.lines++;
      const f0 = days[D.indexOf(true)], l0 = days[D.lastIndexOf(true)];
      R.first = R.first == null || f0 < R.first ? f0 : R.first; R.last = R.last == null || l0 > R.last ? l0 : R.last;
      const LC = L.c.map((v) => (v > 0 ? Math.log(v) : NaN)), LB = L.b.map((v) => (v > 0 ? Math.log(v) : NaN)), LR = LC.map((v, i) => v - LB[i]);
      const fwd = (A, h, t) => (t + h < W ? A[t + h] - A[t] : NaN);
      const end = new Array(W).fill(-1);
      for (let t = W - 1, e = -1; t >= 0; t--) { if (!D[t]) { e = -1; continue; } if (e < 0 || !D[t + 1]) e = t; end[t] = e; }
      const INF = W + 1e6;
      const nextTrue = (cond, def) => { const o = new Array(W).fill(INF); let nx = INF; for (let t = W - 1; t >= 0; t--) { nx = def[t] ? (cond[t] ? t : nx) : INF; o[t] = nx; } return o; };
      const nq = [0, 1, 2, 3].map((k) => nextTrue(q.map((v) => v === k), D));
      for (const h of H) {
        for (let t = 0; t + h < W; t++) {
          if (!D[t]) continue;
          if (q[t + h] >= 0 && end[t] >= t + h) R.trans[h][q[t]][q[t + h]]++;
          const fr = fwd(LR, h, t), fa = fwd(LC, h, t);
          QR[q[t]][h].add(fr); QA[q[t]][h].add(fa); QR[4][h].add(fr); QA[4][h].add(fa);
        }
      }
      for (const [name, src, dst, ax, sg] of BOUNDS) {
        const c = ax === 'x' ? x : y, side = c.map((v) => (sg > 0 ? v >= 100 : v < 100)), nxt = nextTrue(side, c.map(isF)), Bk = B[name];
        let prevEv = false;
        for (let t = 0; t < W; t++) {
          const dist = sg * (100 - c[t]), step = t ? sg * (c[t] - c[t - 1]) : NaN;
          const ev = q[t] === src && dist > 0 && dist <= NEAR && step > 0;
          const start = ev && !prevEv && D[t];
          prevEv = ev;
          if (!start) continue;
          Bk.episodes++;
          const fst = t < W - 1 ? nxt[t + 1] : 1e9, tc = fst - t, obs = end[t] - t;
          for (const h of H) { const cr = tc <= h; if (cr || obs >= h) { Bk.crossed[h][1]++; if (cr) Bk.crossed[h][0]++; } }
          if (tc <= Hm) { Bk.time.add(tc); const land = q[Math.min(fst, W - 1)]; Bk.landed[1]++; if (land === dst) Bk.landed[0]++; }
          const sp = Math.abs(step), band = sp < SPEED[0] ? 0 : sp < SPEED[1] ? 1 : 2, cm = tc <= hs, sm = cm || obs >= hs;
          Bk.speed[band][0]++; if (cm && sm) Bk.speed[band][1]++; if (sm) Bk.speed[band][2]++;
        }
      }
      for (let t = 1; t < W; t++) {
        if (!(q[t] === 2 && q[t - 1] >= 0 && q[t - 1] !== 2)) continue;
        G.entries++;
        const obs = end[t] - t;
        for (const [key, k] of [['improving', 3], ['leading', 0], ['weakening', 1]]) {
          const tk = nq[k][t] - t;
          for (const h of H) { const hit = tk <= h; if (hit || obs >= h) { G[key][h][1]++; if (hit) G[key][h][0]++; } }
          if (key === 'improving' && tk <= Hm) G.time.add(tk);
        }
        const ext = Math.min(nq[0][t], nq[1][t], nq[3][t]), lim = Math.min(ext - 1, end[t], t + Hm);
        let low = NaN;
        for (let i = t; i <= lim; i++) if (isF(x[i]) && !(low <= x[i])) low = x[i];
        G.depth.add(Math.log(low / 100));
        for (const h of H) { G.rel[h].add(fwd(LR, h, t)); G.abs[h].add(fwd(LC, h, t)); }
      }
      for (let t = 1; t < W; t++) {
        if (q[t] !== 2 || !isF(y[t - 1])) continue;
        const d = 100 - x[t] < DEPTH[0] ? 0 : 100 - x[t] < DEPTH[1] ? 1 : 2, u = y[t] >= y[t - 1] ? 1 : 0, S = G.states[d * 2 + u];
        S.n++;
        const ti = nq[3][t] - t, obs = end[t] - t;
        for (const h of H) { const hit = ti <= h; if (hit || obs >= h) { S.improving[h][1]++; if (hit) S.improving[h][0]++; } }
        S.rel.add(fwd(LR, hm, t));
      }
      const idx = []; D.forEach((v, i) => { if (v) idx.push(i); });
      if (idx.length < 2) continue;
      const segs = []; let cur = [idx[0]];
      for (let i = 1; i < idx.length; i++) { if (idx[i] - idx[i - 1] > 1) { segs.push(cur); cur = []; } cur.push(idx[i]); }
      segs.push(cur);
      for (const s of segs) {
        const qs = s.map((i) => q[i]), ch = [];
        for (let i = 0; i + 1 < qs.length; i++) if (qs[i + 1] !== qs[i]) ch.push(i);
        if (ch.length) {
          for (const i of ch) { const dd = ((qs[i + 1] - qs[i]) % 4 + 4) % 4; if (dd === 1) dirn[0]++; else if (dd === 3) dirn[1]++; else dirn[2]++; }
          const bnd = [0, ...ch.map((i) => i + 1), qs.length];
          for (let i = 1; i + 2 < bnd.length; i++) dwell[qs[bnd[i]]].add(bnd[i + 1] - bnd[i]);
        }
        const ent = [];
        for (let j = 1; j < qs.length; j++) if (qs[j] === 0 && qs[j - 1] !== 0) ent.push(s[0] + j);
        for (let i = 0; i + 1 < ent.length; i++) { let lag = false; for (let t = ent[i]; t < ent[i + 1]; t++) if (q[t] === 2) { lag = true; break; } if (lag) cycle.add(ent[i + 1] - ent[i]); }
      }
    }
    const Hs = H.map(String), out = { lines: R.lines, from: R.first, to: R.last, unit, horizons: H.slice(), transitions: Object.fromEntries(H.map((h) => [String(h), R.trans[h]])) };
    out.boundaries = BOUNDS.map(([name, src, dst, ax, sg]) => {
      const b = B[name];
      return { key: name, from: QN[src], to: QN[dst], axis: ax === 'x' ? 'RS-Ratio' : 'RS-Momentum', rising: sg > 0, episodes: b.episodes,
        crossed: Object.fromEntries(H.map((h) => [String(h), pr(b.crossed[h])])), landed_in_target: pr(b.landed), periods_to_cross: b.time.summary(),
        by_speed: ['slow', 'medium', 'fast'].map((s, i) => ({ speed: s, episodes: b.speed[i][0], crossed: pr(b.speed[i].slice(1)), horizon: hs })) };
    });
    let dep = G.depth.summary();
    if (dep.n) dep = { n: dep.n, median: Math.round(100 * (1 + dep.median) * 1e3) / 1e3, p25: Math.round(100 * (1 + dep.p25) * 1e3) / 1e3, p75: Math.round(100 * (1 + dep.p75) * 1e3) / 1e3, mean: Math.round(100 * (1 + dep.mean) * 1e3) / 1e3 };
    out.lagging = { entries: G.entries, improving: Object.fromEntries(H.map((h) => [String(h), pr(G.improving[h])])), leading: Object.fromEntries(H.map((h) => [String(h), pr(G.leading[h])])),
      weakening: Object.fromEntries(H.map((h) => [String(h), pr(G.weakening[h])])), periods_to_improving: G.time.summary(), lowest_rs_ratio: dep,
      forward_vs_benchmark: Object.fromEntries(H.map((h) => [String(h), G.rel[h].summary()])), forward_own: Object.fromEntries(H.map((h) => [String(h), G.abs[h].summary()])),
      states: G.states.map((S) => ({ depth: ['under 1', '1 to 2', '2 or more'][S.d], momentum: ['falling', 'rising'][S.u], n: S.n,
        improving: Object.fromEntries(H.map((h) => [String(h), pr(S.improving[h])])), forward_vs_benchmark: { [String(hm)]: S.rel.summary() } })) };
    const qk = [...QN, 'any'];
    out.quadrants = { forward_vs_benchmark: Object.fromEntries(qk.map((k, i) => [k, Object.fromEntries(Hs.map((h) => [h, QR[i][+h].summary()]))])),
      forward_own: Object.fromEntries(qk.map((k, i) => [k, Object.fromEntries(Hs.map((h) => [h, QA[i][+h].summary()]))])) };
    out.dwell = Object.fromEntries(QN.map((k, i) => [k, dwell[i].summary()]));
    const tot = dirn[0] + dirn[1] + dirn[2], r4 = (v) => Math.round(v * 1e4) / 1e4;
    out.direction = { changes: tot, clockwise: tot ? r4(dirn[0] / tot) : null, counter_clockwise: tot ? r4(dirn[1] / tot) : null, across: tot ? r4(dirn[2] / tot) : null };
    out.cycles = cycle.summary();
    return out;
  }
  /* the line now, against the history of lines in a similar spot (every line-period of `lines` whose outcome h periods
     on was known by period f): for the boundary it is heading for, the share that crossed within h; in Lagging, the share
     that reached Improving and Leading within h and the return against the benchmark over h */
  function nowOdds(lines, f, H) {
    const pool = lines.map((L) => {
      const W = L.x.length, x = L.x.map((v) => (isF(v) ? v : NaN)), y = L.y.map((v) => (isF(v) ? v : NaN)), q = x.map((v, t) => (isF(v) && isF(y[t]) ? quad(v, y[t]) : -1));
      const LR = L.c.map((v, i) => (v > 0 && L.b[i] > 0 ? Math.log(v / L.b[i]) : NaN));
      return { x, y, q, LR, W };
    });
    const cross = (P, t, ax, sg, h) => { const c = ax === 'x' ? P.x : P.y; for (let j = 1; j <= h; j++) { const v = c[t + j]; if (!isF(v)) return null; if (sg > 0 ? v >= 100 : v < 100) return true; } return false; };
    const reach = (P, t, k, h) => { for (let j = 1; j <= h; j++) { const v = P.q[t + j]; if (v < 0) return null; if (v === k) return true; } return false; };
    const match = (test, need = 40) => {        // widen the spot until enough line-periods match (0.25 → 1 unit)
      for (const w of [0.25, 0.5, 1]) { const m = []; pool.forEach((P, i) => { for (let t = 1; t < P.W; t++) if (test(P, t, w)) m.push([i, t]); }); if (m.length >= need || w === 1) return { m, w }; }
      return { m: [], w: 1 };
    };
    return lines.map((L, li) => {
      const P = pool[li], x = P.x[f], y = P.y[f], q0 = P.q[f];
      if (q0 < 0) return null;
      const res = { q: q0, bounds: [], lag: null };
      for (const [name, src, , ax, sg] of BOUNDS) {
        if (src !== q0) continue;
        const c = ax === 'x' ? P.x : P.y, d0 = sg * (100 - c[f]), st0 = f ? sg * (c[f] - c[f - 1]) : NaN;
        if (!isF(st0)) continue;
        const appr = st0 > 0;
        const row = { key: name, dist: d0, approaching: appr, by: {} };
        for (const h of H) {
          const { m, w } = match((Q, t, ww) => { if (Q.q[t] !== src || t + h > f) return false; const cc = ax === 'x' ? Q.x : Q.y, d = sg * (100 - cc[t]), s = sg * (cc[t] - cc[t - 1]); return isF(s) && (s > 0) === appr && Math.abs(d - d0) <= ww; });
          let hit = 0, n = 0;
          for (const [i, t] of m) { const r = cross(pool[i], t, ax, sg, h); if (r == null) continue; n++; if (r) hit++; }
          row.by[h] = { hits: hit, n, share: n ? hit / n : null, width: w };
        }
        res.bounds.push(row);
      }
      if (q0 === 2 && isF(P.y[f - 1])) {
        const up = y >= P.y[f - 1], lag = { depth: 100 - x, rising: up, by: {} };
        for (const h of H) {
          const { m, w } = match((Q, t, ww) => Q.q[t] === 2 && t + h <= f && isF(Q.y[t - 1]) && (Q.y[t] >= Q.y[t - 1]) === up && Math.abs((100 - Q.x[t]) - (100 - x)) <= ww);
          let imp = 0, lead = 0, n = 0;
          const rets = [];
          for (const [i, t] of m) { const a = reach(pool[i], t, 3, h), b = reach(pool[i], t, 0, h); if (a == null) continue; n++; if (a) imp++; if (b) lead++; const r = pool[i].LR[t + h] - pool[i].LR[t]; if (isF(r)) rets.push(r); }
          lag.by[h] = { n, improving: n ? imp / n : null, leading: n ? lead / n : null, rel: rets.length ? Math.expm1(qtl(rets, 0.5)) : null, up: rets.length ? rets.filter((v) => v > 0).length / rets.length : null, width: w };
        }
        res.lag = lag;
      }
      return res;
    });
  }

  const api = { PAR, BOUNDS, QN, QT, NEAR, SPEED, DEPTH, quad, ema, states, thresholds, ladder, stepPaths, forecast, smoothPath, ahead, qtl, decodeMoves, onDays, toWeekly, makeGrid, research, nowOdds, Hist, RHist };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.RRGLab = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);

/* ---------- the hub: daily files, the chart's layers and panels, the Rotation research view ---------- */
const RRGL={moves:{},grid:null,fc:new Map(),srv:{},redraw:null,now:new Map()};
function rrglRedraw(){if(RRGL.redraw)return;RRGL.redraw=setTimeout(()=>{RRGL.redraw=null;if(typeof render==='function')render()},40)}
function rrglMoves(k){                                 // one asset's daily file (move odds), decoded
 const m=RRGL.moves[k]||(RRGL.moves[k]={});
 if(m.data||m.err||m.loading)return m;
 if(typeof fetch!=='function'){m.err='no fetch';return m}
 m.loading=fetch('data/research/paths/moves/a/'+encodeURIComponent(k)+'.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
  .then(d=>{m.data=RRGLab.decodeMoves(d);rrglRedraw()}).catch(e=>{m.err=e.message;rrglRedraw()});
 return m;
}
function rrglGrid(){                                   // SPY's trading days: the daily chart's grid and its benchmark
 const m=rrglMoves('SPY');
 if(m.data&&(!RRGL.grid||RRGL.grid.src!==m.data)){RRGL.grid=RRGLab.makeGrid(m.data);RRGL.grid.src=m.data}
 return m.data?{grid:RRGL.grid}:m.err?{err:m.err}:{loading:true};
}
const RRGL_UNI={
 idxetf:['Index ETFs against the S&P 500 (QQQ · DIA · IWM · MDY · IJR · RSP)',['QQQ','DIA','IWM','MDY','IJR','RSP']],
 regions:['World regions (ETFs in dollars)',['VTI','ACWI','VEA','EFA','VWO','EEM']],
 countries:['Countries (ETFs in dollars)',['EWJ','FXI','MCHI','KWEB','EWZ','INDA','EWG','EWU','EWC','EWA','EWT','EWY','EWW','EWH']],
 bonds:['Bonds (Treasuries, credit, inflation-linked)',['SHY','IEF','TLT','TIP','AGG','LQD','HYG','EMB','MUB']],
 commod:['Commodities and gold miners',['GLD','SLV','USO','UNG','DBC','DBA','GDX']],
 indcyc:['Industry ETFs · cyclical',['KBE','KRE','XHB','ITB','XRT','XOP','OIH','XME','ITA','IYT','JETS','VNQ']],
 indgro:['Industry ETFs · growth and themes',['IGV','SMH','IBB','XBI','ARKK','TAN','ICLN','URA']]};
const RRGL_DAILY_OK=u=>['sectors','styles','indices','tickers'].includes(u)||!!RRGL_UNI[u]||String(u).startsWith('top:');
// a line from its daily file: daily closes on SPY's days, or (weekly / monthly chart) the last close of each week
function rrglEnt(D,id,freq,ent){
 const m=rrglMoves(id);
 if(!m.data)return m.err?{id,missing:true}:{id,loading:true};
 const md=m.data,base={...(ent||{}),id,name:(ent&&ent.name)||id,full:(ent&&ent.full)||md.name||id,level:md.level,dkind:md.kind,dgroup:md.group,daily:true};
 if(freq==='d'){const g=rrglGrid();if(!g.grid)return g.err?{id,missing:true}:{id,loading:true};const dc=RRGLab.onDays(g.grid,md);return {...base,dc,c:dc}}
 const s=rrglMoves('SPY');if(!s.data)return s.err?{id,missing:true}:{id,loading:true};
 const G=rrgGrid(D);
 return {...base,start:G.days[0],c:RRGLab.toWeekly(G.days,md),benchC:RRGLab.toWeekly(G.days,s.data),labBench:true};
}
function rrglUniverse(D,uni,freq){const u=RRGL_UNI[uni];return u?u[1].map(t=>rrglEnt(D,t,freq)):null}
// the daily chart's lines for a universe of the weekly chart: the same tickers, from their daily files
function rrglDaily(D,ents){return ents.map(e=>{if(e.loading||e.missing)return e;const id=String(e.id);
 if(/^(s:|th:|ch:|ind:|ix:)/.test(id)||e.benchC&&!e.labBench)return {id,missing:true,why:'weekly only'};
 return rrglEnt(D,id,'d',{name:e.name,full:e.full})})}
const rrglIsPrice=e=>!(e.level||e.group==='site-sector'||/^(th:|ch:|ind:|ix:centre|s:)/.test(String(e.id))||/^SIC-/.test(String(e.id)));
const rrglMoney=(e,v)=>!isFinite(v)||v==null?'—':rrglIsPrice(e)?'$'+fmt(v,v>=1000?0:2):fmt(v,v>=1000?0:2);
const rrglPct=v=>{if(v==null||!isFinite(v))return '—';const a=Math.round(Math.abs(1000*v))/10;return (a===0?'':v>0?'+':'−')+fmt(a,1)+'%'};
const rrglSh=v=>v==null||!isFinite(v)?'—':fmt(100*v,0)+'%';
function rrglFc(o,l,f,peek){                           // the forecast path from period f, cached per line and frame
 const key=l.e.id+'|'+o.freq+'|'+o.n+'|'+f+'|'+(l.calc.x.length);
 if(RRGL.fc.has(key))return RRGL.fc.get(key);
 if(peek)return null;                                   // dragging the slider: only paths already worked out
 if(RRGL.fc.size>400)RRGL.fc.clear();
 const F=RRGLab.forecast(l.calc,f,o.freq);
 if(F)F.steps.forEach(s=>{s.date=RRGLab.ahead(o.Q[f],o.freq,s.j)});
 RRGL.fc.set(key,F);return F;
}
const RRGL_FP=o=>[['','Off'],['all','Every line (median paths)'],...o.lines.map(l=>[l.e.id,l.e.name+' — path, dates, prices, ranges'])];
function rrglFpState(o){const ok=RRGL_FP(o).map(x=>x[0]);if(state.rrgfp===undefined)state.rrgfp='all';if(!ok.includes(state.rrgfp))state.rrgfp=ok.includes(String(state.rrgfp))?state.rrgfp:'all';return state.rrgfp}
// the chart layer: each line's forecast path (median position each period), the marked periods with date and price
function rrglLayer(o,f,sx,sy){
 // a line shown alone (rrg.js, state.rrgsolo) gets its path with dates, prices and ranges, as if picked here
 const mode=state.rrgfp&&o.solo?o.solo:state.rrgfp;if(!mode||!o.lines)return '';   // a line shown alone: its path, whatever line was picked
 const P=RRGLab.PAR[o.freq],one=mode!=='all',U=P.ab;
 let s='';const labels=[];
 for(const l of o.lines){
  if(one&&l.e.id!==mode)continue;
  if(!one&&o.solo&&l.e.id!==o.solo)continue;
  const c=l.calc;if(!c||c.x[f]==null||c.y[f]==null||!c.c)continue;
  const F=rrglFc(o,l,f,typeof ROT!=='undefined'&&ROT.drag);if(!F)continue;
  const sm=RRGLab.smoothPath(F.steps),at=j=>sm[j-1]?[sx(sm[j-1][0]),sy(sm[j-1][1])]:null;   // step j on the drawn (smoothed) path
  const p0=[sx(c.x[f]),sy(c.y[f])],pts=[p0,...sm.filter(Boolean).map(q=>[sx(q[0]),sy(q[1])])];
  if(pts.length<2)continue;
  s+=`<path class="rot-line rrgl-path" d="${curve(pts,true)}" style="stroke:${l.col}"/>`;
  if(one&&f<o.lastK){const ak=[p0];for(let j=1;j<=P.steps&&f+j<=o.lastK;j++)if(c.x[f+j]!=null&&c.y[f+j]!=null)ak.push([sx(c.x[f+j]),sy(c.y[f+j])]);
   if(ak.length>1)s+=`<path class="rot-line rrgl-actual" d="${curve(ak,true)}" style="stroke:${l.col}"/>`}
  const marks=P.marks.filter(j=>F.steps[j-1]);
  for(let j=1;j<=F.steps.length;j++){const q=at(j);if(q&&!marks.includes(j))s+=`<circle class="rrgl-step" cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="${one?1.9:1.4}" style="fill:${l.col}"/>`}   // every step, small
  for(const j of marks){const st=F.steps[j-1],p=at(j);if(!p)continue;
   const last=j===marks[marks.length-1],act=f+j<=o.lastK&&c.c[f+j]!=null?c.c[f+j]:null;
   if(one&&(last||j===marks[Math.floor(marks.length/2)]))s+=`<rect class="rrgl-box" x="${Math.min(sx(st.x10),sx(st.x90)).toFixed(1)}" y="${Math.min(sy(st.y10),sy(st.y90)).toFixed(1)}" width="${Math.abs(sx(st.x90)-sx(st.x10)).toFixed(1)}" height="${Math.abs(sy(st.y10)-sy(st.y90)).toFixed(1)}" style="stroke:${l.col}"/>`;
   const rows=[[l.e.name+' · +'+j+' '+(j===1?P.one:P.many)+' → '+rrgDay(st.date),'forecast path from '+rrgDay(o.Q[f])+' ('+fmt(F.n)+' replays of the last '+fmt(F.window)+' '+P.many+')'],
    [rrglMoney(l.e,st.p50)+' ('+rrglPct(st.p50/F.close-1)+')','median replayed close'],[rrglMoney(l.e,st.p25)+' – '+rrglMoney(l.e,st.p75),'50% of replays'],[rrglMoney(l.e,st.p10)+' – '+rrglMoney(l.e,st.p90),'80% of replays'],
    [st.q.map((v,i)=>RRGLab.QT[i][0]+' '+rrglSh(v)).join(' · '),'quadrant shares (L W G I = Leading, Weakening, laGging, Improving)'],[rrglSh(st.left),'have left '+RRGLab.QT[F.q0]+' at some point'],
    [fmt(st.x50,2)+' / '+fmt(st.y50,2),'median RS-Ratio / RS-Momentum (the dot sits on the path smoothed over three steps)'],
    ...(act!=null?[[rrglMoney(l.e,act)+(act>=st.p10&&act<=st.p90?' · inside the 80% range':' · outside the 80% range'),'what happened']]:[])];
   s+=`<g data-tip="${tip(rows)}" class="mk-hit" tabindex="-1"><circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="9" fill="transparent"/><circle class="rrgl-mark" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${last?4.2:2.9}" style="fill:${l.col}"/></g>`;
   if(one||last)labels.push({x:p[0],y:p[1],pri:last?0:j,t:(one?'+'+j+U+' ':'')+rrgDay(st.date).replace(/, \d{4}$/,'')+' · '+rrglMoney(l.e,st.p50)+(one&&last?' (80%: '+rrglMoney(l.e,st.p10)+'–'+rrglMoney(l.e,st.p90)+')':''),col:l.col});
  }
 }
 const boxes=[];
 labels.sort((a,b)=>a.pri-b.pri);                                  // the last mark (its price range) placed first, then +1, +2 …
 for(const b of labels){const w=b.t.length*6.2;                  // above right, below right, above left, below left: the first free spot
  const at=[[b.x+7,b.y-7,'start'],[b.x+7,b.y+15,'start'],[b.x-7,b.y-7,'end'],[b.x-7,b.y+15,'end']].map(([x,y,a])=>({x,y,a,r:a==='start'?[x,y-10,x+w,y+3]:[x-w,y-10,x,y+3]}));
  const c=at.find(p=>!boxes.some(q=>p.r[0]<q[2]&&p.r[2]>q[0]&&p.r[1]<q[3]&&p.r[3]>q[1]));if(!c)continue;boxes.push(c.r);
  s+=`<text class="mk-label mk-halo rrgl-label" x="${c.x.toFixed(1)}" y="${c.y.toFixed(1)}" text-anchor="${c.a}" style="fill:${b.col}">${esc(b.t)}</text>`}
 return s;
}
// the server's research for a frequency: weekly (rotation history) or daily (move odds)
function rrglServer(fq){
 if(fq==='w')return typeof marketData==='function'?marketData('history/rrg-research'):{err:'no data'};
 if(fq!=='d')return {err:'not computed for this frequency'};
 const m=RRGL.srv.d||(RRGL.srv.d={});
 if(m.data||m.err||m.loading)return m;
 if(typeof fetch!=='function'){m.err='no fetch';return m}
 m.loading=fetch('data/research/paths/moves/rrg-research-daily.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{m.data=d;rrglRedraw()}).catch(e=>{m.err=e.message;rrglRedraw()});
 return m;
}
const RRGL_IDX=new Set(['QQQ','DIA','IWM','MDY','IJR','RSP']);
function rrglGroupOf(o,e){                             // which of the server's groups a line belongs to
 const id=String(e.id);
 if(o.freq==='d'){const k=e.dkind,g=e.dgroup;
  if(k==='sector')return 'sectors';if(RRGL_IDX.has(id))return 'index_etfs';if(g==='style')return 'styles';if(g==='broad'||g==='country')return 'world';
  if(g==='bonds'||g==='commodities')return 'bonds_commodities';if(g==='industry')return 'industry_etfs';if(k==='industry'&&id.length===8)return 'industries';if(k==='stock')return 'companies';return null}
 if(o.freq!=='w'||o.ix)return null;
 if(e.labBench)return null;
 if(id.startsWith('ind:'))return 'industries';
 if(e.benchC)return e.bx?'companies_vs_industry':null;
 const s=(o.D.series||[]).find(x=>x.id===id);
 if(s)return s.group==='sector-etf'?'sectors':s.group==='site-sector'?'site_sectors':s.group==='style-etf'?(RRGL_IDX.has(id)?'index_etfs':'styles'):null;
 return /^(th:|ch:)/.test(id)?null:'companies';
}
const RRGL_BN={improving_to_leading:'Improving → Leading (RS-Ratio up through 100)',leading_to_weakening:'Leading → Weakening (RS-Momentum down through 100)',weakening_to_lagging:'Weakening → Lagging (RS-Ratio down through 100)',
 lagging_to_improving:'Lagging → Improving (RS-Momentum up through 100)',weakening_to_leading:'Weakening → Leading (momentum turns back up: re-acceleration)',improving_to_lagging:'Improving → Lagging (momentum turns back down: a failed rebound)'};
const RRGL_BS={improving_to_leading:'Improving → Leading',leading_to_weakening:'Leading → Weakening',weakening_to_lagging:'Weakening → Lagging',lagging_to_improving:'Lagging → Improving',weakening_to_leading:'Weakening → Leading',improving_to_lagging:'Improving → Lagging'};
const rrglH=fq=>{const H=RRGLab.PAR[fq].H,h=H.map(String).includes(String(state.rrgrh))?+state.rrgrh:H[1];return {H,h}};
const rrglHl=(fq,h)=>h+' '+(h===1?RRGLab.PAR[fq].one:RRGLab.PAR[fq].many);
const rrglCell=(c,n0=30)=>!c||!c.n?'—':`<span title="${esc(fmt(c.hits)+' of '+fmt(c.n))}"${c.n<n0?' class="muted"':''}>${rrglSh(c.share)}</span>`;
// the boundary a line is heading for: the nearest one it is moving toward, else its quadrant's clockwise exit
const rrglPick=N=>{const t=N.bounds.filter(b=>b.approaching).sort((u,v)=>u.dist-v.dist);return t[0]||N.bounds[0]||null};
// the research panel under the chart: every line now (prices that cross the lines, the odds of the next crossing,
// lagging rebounds) and these lines' own history
function rrglPanel(o){
 if(!o||o.mode!=='2d')return '';
 const f=state.rf,P=RRGLab.PAR[o.freq],{H,h}=rrglH(o.freq),U=P.many,hl=rrglHl(o.freq,h),hk=String(h);
 const lines=o.lines.filter(l=>l.calc&&l.calc.c&&l.calc.b);
 if(!lines.length)return '';
 const sv=rrglServer(o.freq),SV=sv.data&&sv.data.rrg&&sv.data.rrg.n===o.n?sv.data:null;
 const nkey=lines.map(l=>l.e.id).join(',')+'|'+o.freq+'|'+o.n+'|'+f+'|'+h;
 let now=RRGL.now.get(nkey);
 if(!now){if(RRGL.now.size>40)RRGL.now.clear();now=RRGLab.nowOdds(lines.map(l=>({x:l.calc.x,y:l.calc.y,c:l.calc.c,b:l.calc.b})),f,[h]);RRGL.now.set(nkey,now)}
 const rows=[],csv=[];
 lines.forEach((l,i)=>{const c=l.calc,N=now[i];if(!N)return;
  const th=RRGLab.thresholds(c,c.rs,f),L=RRGLab.ladder(c.c[f],th),grp=rrglGroupOf(o,l.e),G=SV&&grp&&SV.groups[grp];
  const B=rrglPick(N),bs=B&&B.by[h],gb=G&&B&&(G.boundaries||[]).find(x=>x.key===B.key);
  const near=B&&B.dist>0&&B.dist<=RRGLab.NEAR&&B.approaching,gc=near&&gb&&gb.crossed[hk]&&gb.crossed[hk].n?gb.crossed[hk]:null;
  let odds=bs&&bs.n?`<b>${rrglSh(bs.share)}</b> crossed <span class="muted">(${fmt(bs.n)} similar)</span>${gc?`<br><span class="muted">whole group: ${rrglSh(gc.share)} (${fmt(gc.n)})</span>`:''}`:'—';
  if(N.lag){const a=N.lag.by[h],st=G&&G.lagging&&G.lagging.states.find(s=>s.depth===(N.lag.depth<1?'under 1':N.lag.depth<2?'1 to 2':'2 or more')&&s.momentum===(N.lag.rising?'rising':'falling')),gs=st&&st.improving[hk]&&st.improving[hk].n?st.improving[hk]:null;
   odds+=`<br>Rebound: <b>${rrglSh(a.improving)}</b> → Improving · ${rrglSh(a.leading)} → Leading <span class="muted">(${fmt(a.n)})</span>${gs?`<br><span class="muted">whole group: ${rrglSh(gs.share)} → Improving (${fmt(gs.n)})</span>`:''}<br><span class="muted">vs benchmark: ${rrglPct(a.rel)} median · ${rrglSh(a.up)} up</span>`}
  rows.push([`<i class="mk-key" style="background:${l.col}"></i> <b>${esc(l.e.name)}</b> ${rrglMoney(l.e,c.c[f])}<br><span class="badge rrg-b-${RRG_Q[N.q][0]}">${RRG_Q[N.q][1]}</span>`,
   L?`${rrglMoney(l.e,L.ratio)} <span class="muted">(${rrglPct(L.ratio/c.c[f]-1)})</span><br>${rrglMoney(l.e,L.momentum)} <span class="muted">(${rrglPct(L.momentum/c.c[f]-1)})</span>`:'—',
   B?`${esc(RRGL_BS[B.key])}<br><span class="muted">${fmt(Math.abs(B.dist),2)} away · ${B.approaching?'moving toward it':'moving away'}</span>`:'—',odds]);
  csv.push({date:o.Q[f],line:l.e.name,close:c.c[f],quadrant:RRG_Q[N.q][1],rs_ratio_100_at:L?+L.ratio.toFixed(4):null,rs_momentum_100_at:L?+L.momentum.toFixed(4):null,
   next_line:B?RRGL_BS[B.key]:null,distance:B?+Math.abs(B.dist).toFixed(3):null,approaching:B?B.approaching:null,horizon:h,crossed_share:bs&&bs.share!=null?+bs.share.toFixed(4):null,similar:bs?bs.n:null,
   group_crossed_share:gc?gc.share:null,lagging_to_improving:N.lag&&N.lag.by[h].improving!=null?+N.lag.by[h].improving.toFixed(4):null,lagging_to_leading:N.lag&&N.lag.by[h].leading!=null?+N.lag.by[h].leading.toFixed(4):null});
 });
 RRGL.csv=csv;
 let out=`<div class="panel" id="rrg-lab"><div class="section-head"><h3>Crossing odds, resistance and rebounds — ${esc(rrgDay(o.Q[f]))}</h3><button class="action" id="rrglcsv" type="button">Export CSV ↓</button></div>`;
 out+=`<p class="sub">Price levels: the closes next ${esc(P.one)} that would put RS-Ratio and RS-Momentum exactly at 100 (the benchmark unchanged; exact from the formula). Below the lower one the line lands in Lagging, above the higher one in Leading. Odds: how often lines in a similar spot crossed the line within ${esc(hl)} — counted over the lines on this chart, only where the outcome was known by the date shown (similar: same quadrant, moving the same way, within ±0.25 of the same distance, widened to 1 when fewer than 40 match); “whole group”: the server's count over every line of its group. Lagging lines: how often lines at the same depth, with momentum moving the same way, reached Improving and Leading, and what they did against the benchmark. History, not a forecast.</p>`;
 out+=`<div class="toolbar">${field('rrgrh','Within',H.map(x=>[String(x),rrglHl(o.freq,x)]),String(h))}</div>`;
 out+=rrglT(table(['Line, close, quadrant',`Next ${P.one}: RS-Ratio · RS-Momentum at 100`,'Heading for',`Within ${hl}`],rows));
 // these lines' own history: the in-browser research
 const rk=lines.map(l=>l.e.id).join(',')+'|'+o.freq+'|'+o.n;
 if(state.rrglopen&&(!RRGL.res||RRGL.res.k!==rk))RRGL.res={k:rk,r:RRGLab.research(lines.map(l=>({x:l.calc.x,y:l.calc.y,c:l.calc.c,b:l.calc.b})),o.Q,H,U)};
 const R=state.rrglopen&&RRGL.res&&RRGL.res.k===rk?RRGL.res.r:null;      // worked out when opened: every period of every line
 out+=`<details class="fc-score" id="rrgl-hist"${R?' open':''}><summary>These ${fmt(lines.length)} lines' history: crossings, resistance, lagging rebounds${R?` (${esc(rrgDay(R.from))} – ${esc(rrgDay(R.to))})`:' — open to count'}</summary>${R?rrglTables(R,o.freq,h):''}</details>`;
 out+=`<p class="sub">The whole universe — every sector, index ETF, country, bond and commodity ETF, industry and company, weekly and daily — is in <a href="#rotation/research" data-rview="research">Rotation research</a>.</p></div>`;
 return out;
}
// a share per row as a bar: the part that crossed (or rebounded) solid, the rest faint — resistance at a glance
function rrglBars(rows,legend){
 const W=720,rh=24,L=232,bw=W-L-64,H=rows.length*rh+30;
 let s=`<svg class="plot rrgl-bars" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(legend)}">`;
 rows.forEach(([label,c],i)=>{const y=6+i*rh;if(!c||!c.n||c.share==null)return;const w=bw*c.share;
  s+=`<g data-tip="${tip([[label,legend],[rrglSh(c.share),fmt(c.hits)+' of '+fmt(c.n)]])}" class="mk-hit"><text class="axis" x="${L-8}" y="${y+13}" text-anchor="end">${esc(label)}</text><rect class="rrgl-bar-x" x="${L}" y="${y}" width="${w.toFixed(1)}" height="17" rx="2"/><rect class="rrgl-bar-r" x="${(L+w).toFixed(1)}" y="${y}" width="${(bw-w).toFixed(1)}" height="17" rx="2"/><text class="axis" x="${L+bw+6}" y="${y+13}">${rrglSh(c.share)}</text></g>`});
 return s+`<text class="axis" x="${L}" y="${H-6}">${esc(legend)}</text></svg>`;
}
const rrglCap=t=>String(t).charAt(0).toUpperCase()+String(t).slice(1);
const rrglT=t=>`<div class="rrgl-t">${t}</div>`;
// the research tables (one group): crossings and resistance, lagging rebounds, lagging by depth and momentum
function rrglTables(R,fq,h){
 const P=RRGLab.PAR[fq],H=R.horizons,H3=H.slice(1),hs=String(H[1]||H[0]),hm=String(H[Math.floor(H.length/2)]),hk=String(h);
 const med=s=>!s||!s.n?'—':`${fmt(s.median)} <span class="muted">(${fmt(s.p25)}–${fmt(s.p75)})</span>`;
 const ret=s=>!s||!s.n?'—':`${rrglPct(s.median)} <span class="muted">· up ${rrglSh(s.up)}</span>`;
 let out=`<h4>Crossing the 100 lines — and turning back (resistance)</h4><p class="sub">An approach: a line in the quadrant before the line, within 1 standard unit of 100 and moving toward it (the first ${esc(P.one)} of each such run). Crossed: the coordinate passed 100 within the horizon; the rest turned back first. By speed: how far it moved toward the line that ${esc(P.one)} (slow under 0.25, fast 0.5 or more), crossed within ${esc(rrglHl(fq,+hs))}. Hover a share for its counts.</p>`;
 out+=rrglBars(R.boundaries.map(b=>[RRGL_BS[b.key],b.crossed[hk]]),`solid: crossed within ${rrglHl(fq,h)} · faint: turned back first (resistance)`);
 out+=rrglT(table(['Line to cross',...H3.map(x=>'Crossed within '+rrglHl(fq,x)),'Turned back within '+rrglHl(fq,+hs),`${rrglCap(P.many)} to cross (median, 25–75%)`,'Crossed by speed: slow · medium · fast'],R.boundaries.map(b=>[
  `${esc(RRGL_BN[b.key])}<br><span class="muted">${fmt(b.episodes)} approaches</span>`,...H3.map(x=>rrglCell(b.crossed[String(x)])),b.crossed[hs]&&b.crossed[hs].n?rrglSh(1-b.crossed[hs].share):'—',med(b.periods_to_cross),
  b.by_speed.map(s=>s.crossed.n?rrglSh(s.crossed.share):'—').join(' · ')])));
 const L=R.lagging;
 out+=`<h4>Lagging: does it rebound?</h4><p class="sub">${fmt(L.entries)} entries into Lagging. Reached: the line stood in that quadrant at some ${esc(P.one)} within the horizon. Returns from the ${esc(P.one)} of entry: against the benchmark and the line's own (median; up: the share above zero). ${esc(P.many[0].toUpperCase()+P.many.slice(1))} from entry to Improving: ${med(L.periods_to_improving)} · lowest RS-Ratio of the spell: ${med(L.lowest_rs_ratio)}.</p>`;
 out+=rrglBars(H.map(x=>['Improving within '+rrglHl(fq,x),L.improving[String(x)]]).concat(H.map(x=>['Leading within '+rrglHl(fq,x),L.leading[String(x)]])),'solid: Lagging lines that reached the quadrant within the horizon');
 out+=table(['Within',...H.map(x=>rrglHl(fq,x))],[['Reached Improving',...H.map(x=>rrglCell(L.improving[String(x)]))],['Reached Leading',...H.map(x=>rrglCell(L.leading[String(x)]))],
  ['Back up to Weakening',...H.map(x=>rrglCell(L.weakening[String(x)]))],['Vs benchmark',...H.map(x=>ret(L.forward_vs_benchmark[String(x)]))],['Own return',...H.map(x=>ret(L.forward_own[String(x)]))]]);
 out+=`<h4>Lagging lines by depth and momentum</h4><p class="sub">Every ${esc(P.one)} a line spent in Lagging, by how far RS-Ratio was below 100 and which way RS-Momentum moved that ${esc(P.one)}.</p>`+rrglT(table(['Depth · RS-Momentum',...H3.map(x=>'To Improving within '+rrglHl(fq,x)),'Vs benchmark after '+rrglHl(fq,+hm)],L.states.map(s=>[`${esc(s.depth)} · ${esc(s.momentum)}<br><span class="muted">${fmt(s.n)} line-${esc(P.many)}</span>`,...H3.map(x=>rrglCell(s.improving[String(x)])),ret(s.forward_vs_benchmark[hm])])));
 const Qf=(R.quadrants||{}).forward_vs_benchmark||{},dw=R.dwell||{},dr=R.direction||{};
 out+=`<h4>After each quadrant, and how lines rotate</h4>`+rrglT(table(['From',...H3.map(x=>'Vs benchmark after '+rrglHl(fq,x)),`Stay (${P.many})`],[...RRGLab.QN.map((k,i)=>[`<span class="badge rrg-b-${RRG_Q[i][0]}">${RRG_Q[i][1]}</span>`,...H3.map(x=>ret((Qf[k]||{})[String(x)])),med(dw[k])]),['Any',...H3.map(x=>ret((Qf.any||{})[String(x)])),'']]));
 out+=`<p class="sub">Quadrant changes: ${fmt(dr.changes)} — clockwise ${rrglSh(dr.clockwise)}, counter-clockwise ${rrglSh(dr.counter_clockwise)}, across the centre ${rrglSh(dr.across)}. A full loop (Leading to Leading through Lagging): ${med(R.cycles)} ${esc(P.many)}.</p>`;
 const T=(R.transitions||{})[hk];
 if(T)out+=`<h4>Where lines stood ${esc(rrglHl(fq,h))} later</h4>`+table(['Now ↓ · later →','Line-'+P.many,...RRGLab.QT],T.map((r,i)=>{const n=r.reduce((a,b)=>a+b,0);return [`<b>${RRGLab.QT[i]}</b>`,fmt(n),...r.map(v=>n?rrglSh(v/n):'—')]}));
 return out;
}
const RRGL_GORD={w:['sectors','index_etfs','styles','site_sectors','industries','companies','companies_vs_industry'],d:['sectors','index_etfs','styles','world','bonds_commodities','industry_etfs','industries','companies']};
// the Rotation research view: the server's numbers for every group, weekly and daily
function rrgResearchView(){
 state.rrsf=state.rrsf==='d'?'d':'w';
 const fq=state.rrsf,m=rrglServer(fq),P=RRGLab.PAR[fq];
 let out=`<div class="toolbar">${field('rview','Chart',ROT_VIEWS,state.rview)}${field('rrsf','Frequency',[['w','Weekly (14-week RRG, since 1999)'],['d','Daily (21-day RRG, since 2005)']],fq)}`;
 if(!m.data){return out+'</div>'+(m.err?empty('The rotation research is not published yet ('+m.err+'). It is built with the '+(fq==='w'?'weekly rotation history':'daily move odds')+'; check back after the next run.'):empty('Loading the rotation research…'))}
 const Dd=m.data,gs=RRGL_GORD[fq].filter(g=>Dd.groups&&Dd.groups[g]);
 if(!gs.length)return out+'</div>'+empty('No groups in the research file yet.');
 state.rrsg=gs.includes(state.rrsg)?state.rrsg:gs[0];
 const {H}=rrglH(fq),h=H.map(String).includes(String(state.rrsh))?+state.rrsh:H[1];
 out+=`${field('rrsg','Group',gs.map(g=>[g,Dd.groups[g].label]),state.rrsg)}${field('rrsh','Horizon',H.map(x=>[String(x),rrglHl(fq,x)]),String(h))}</div>`;
 const hk=String(h);
 out+=`<div class="panel"><h3>Rotation research — every group, ${fq==='w'?'weekly':'daily'}</h3><p class="sub">How lines moved around the RRG (${esc(fq==='w'?'weekly, 14-week window':'daily, 21-day window')}, against the S&amp;P 500 unless stated): how often a line near a quadrant line and moving toward it crossed within ${esc(rrglHl(fq,h))}, and how often a line that fell into Lagging reached Improving and Leading. ${esc(Dd.note||'')}</p>`;
 const g4=['improving_to_leading','leading_to_weakening','weakening_to_lagging','lagging_to_improving'];
 const gl=g=>{const G=Dd.groups[g];return `<b>${esc(G.label)}</b><br><span class="muted">${fmt(G.lines)} lines · ${esc(rrgDay(G.from))} – ${esc(rrgDay(G.to))}</span>`};
 const bx=(G,k)=>((G.boundaries||[]).find(x=>x.key===k)||{crossed:{}}).crossed[hk];
 exported=gs.map(g=>{const G=Dd.groups[g],L=G.lagging||{};
  return {frequency:fq,group:g,label:G.label,lines:G.lines,from:G.from,to:G.to,horizon:h,...Object.fromEntries(g4.map(k=>['crossed_'+k,(bx(G,k)||{}).share])),
   lagging_entries:L.entries,lagging_to_improving:((L.improving||{})[hk]||{}).share,lagging_to_leading:((L.leading||{})[hk]||{}).share,median_periods_to_improving:(L.periods_to_improving||{}).median,
   lagging_dwell_median:((G.dwell||{}).lagging||{}).median,cycle_median:(G.cycles||{}).median,clockwise:(G.direction||{}).clockwise}});
 out+=`<div class="section-head"><h4>Compare the groups: crossing each line within ${esc(rrglHl(fq,h))} (from within 1 unit, moving toward it)</h4><button class="action" id="csv">Export CSV ↓</button></div>`;
 out+=rrglT(table(['Group',...g4.map(k=>RRGL_BS[k])],gs.map(g=>[gl(g),...g4.map(k=>rrglCell(bx(Dd.groups[g],k)))])));
 out+=`<h4>Compare the groups: lagging rebounds and the rotation</h4>`;
 out+=rrglT(table(['Group',`Lagging → Improving within ${rrglHl(fq,h)}`,`Lagging → Leading within ${rrglHl(fq,h)}`,`${rrglCap(P.many)} to Improving · stay in Lagging (medians)`,'Full loop (median) · clockwise turns'],gs.map(g=>{const G=Dd.groups[g],L=G.lagging||{};
  return [gl(g),rrglCell((L.improving||{})[hk]),rrglCell((L.leading||{})[hk]),`${fmt((L.periods_to_improving||{}).median)} · ${fmt(((G.dwell||{}).lagging||{}).median)}`,`${fmt((G.cycles||{}).median)} ${esc(P.many)} · ${rrglSh((G.direction||{}).clockwise)}`]})))+'</div>';
 const G=Dd.groups[state.rrsg];
 out+=`<div class="panel"><h3>${esc(G.label)}</h3><p class="sub">${fmt(G.lines)} lines, ${esc(rrgDay(G.from))} – ${esc(rrgDay(G.to))}. Crossed: share of approaches that passed 100 within the horizon (hover for the counts; grey when fewer than 30). Every share counts an approach or a line-${esc(P.one)} only when its outcome was seen (no gap and not past the end of the data).</p>${rrglTables(G,fq,h)}</div>`;
 out+=`<details><summary>How the research is counted</summary><p class="sub">The RRG is the chart's formula (RS = 100 × close ÷ benchmark, smoothed over ${fq==='w'?'4 weeks':'5 trading days'}; RS-Ratio its gap to its ${fq==='w'?'14-week':'21-day'} trend, RS-Momentum the change of that gap, both in standard units of their own last ${fq==='w'?'year or more':'252 trading days'}). Quadrants at 100 / 100. Built by app/rrg_research.py ${fq==='w'?'with the weekly rotation history':'with the daily move odds, on SPY\'s trading days from 2005'}. Companies and industries are today's (survivors), which flatters what came after weak spells; companies in the weekly file count only while liquid (≥ $3 and ≥ $10M a week). Generated ${esc(Dd.generated_at||'')}.</p></details>`;
 return out;
}
