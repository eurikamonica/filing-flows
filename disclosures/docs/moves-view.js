/* Move odds — how rare an asset's latest move is in its own history, and what followed moves like it over the next
   day, week and month: the days in a band of percentiles around it, the days at least as extreme, and every day.
   A company can be switched to its industry (an equal-weighted SIC composite), its sector ETF and the market (SPY).
   The move can be one day, a week or a month, measured as a % change, against the asset's own recent volatility, or
   beyond what the market's move implied (beta-adjusted); any past day or a "what if" move can be looked at instead, and
   older days can count less (each day's weight halving every 10, 5, 2 years or every year away from the day looked at).
   Shared by every company page of the Sankey site (views.json: window.MovesView.render(el, {cik, ticker, hub, here}))
   and the hub's Move odds tab (moves.js: MovesView.render(el, {key, hub})). Data: data/research/paths/moves/a/<KEY>.json
   (app/moves.py, branch research-paths): trading days and daily log returns; everything else is worked out here, with
   the same arithmetic as app/moves.py. No dependencies. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const sgn = (v, d = 1, unit = '%') => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v), d) + unit : '—');
  const sp = (v, d = 1) => (fin(v) ? sgn(100 * v, d) : '—');                       // a simple return as a signed percent
  const share = (v) => (fin(v) ? num(100 * v, 0) + '%' : '—');
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mdy = (e) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(e || ''); return m ? `${MON[+m[2] - 1]} ${+m[3]}, ${m[1]}` : String(e || ''); };
  const my = (e) => { const m = /^(\d{4})-(\d{2})/.exec(e || ''); return m ? `${MON[+m[2] - 1]} ${m[1]}` : String(e || ''); };
  const tk = (t) => String(t || '').trim().toUpperCase().replace(/[./]/g, '-');
  const COL = { up: 'var(--mk-profit, #17734a)', down: 'var(--mk-cost, #c0392b)', band: 'var(--rot-1, #2a78d6)', ink: 'var(--ink, #222)',
    mute: 'var(--muted, #888)', line: 'var(--line, #e3e3e3)', all: 'var(--muted, #9a9a9a)', warn: 'var(--q-warm, #d9822b)', calm: '#5b7fa6' };
  const QS = [5, 10, 25, 50, 75, 90, 95];
  const H = [[1, 'Next day'], [5, 'Next week'], [10, 'Next 2 weeks'], [21, 'Next month'], [63, 'Next quarter']];
  const RGRID = [5, 10, 21, 63, 126, 252, 504];                                  // a week, two, a month, 3 and 6 months, a year, two
  const WIN = [[1, '1 day'], [5, '1 week'], [21, '1 month']];
  const BANDS = [0.25, 0.5, 1, 2.5, 5, 10];                                     // presets; the slider steps by 0.1
  const PATH_D = 63, PATH_MARKS = [[1, '1 day'], [5, '1 week'], [10, '2 weeks'], [21, '1 month'], [63, '1 quarter']];
  const fb = (b) => { const v = +b; return Number.isInteger(v) ? String(v) : v.toFixed(v < 1 ? 2 : 1).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, ''); };
  const HLS = [[0, 'the same'], [10, '½ every 10 yrs'], [5, '½ every 5 yrs'], [2, '½ every 2 yrs'], [1, '½ every year']];   // older days count …
  const hlWords = (hl) => (hl === 1 ? 'every year' : `every ${hl} years`);
  const HERE = (typeof document !== 'undefined' && document.currentScript && document.currentScript.src) ? document.currentScript.src.replace(/[^/]*$/, '') : '';
  const store = {};
  const get = (u) => store[u] || (store[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .catch((e) => { delete store[u]; throw e; }));

  /* ---------- the arithmetic (as app/moves.py) ---------- */
  function decode(doc) {
    let days;
    if (Array.isArray(doc.dates)) days = doc.dates.slice();
    else {
      days = [doc.d0];
      let t = Date.parse(doc.d0 + 'T00:00:00Z');
      for (const ch of doc.gaps || '') { t += parseInt(ch, 36) * 864e5; days.push(new Date(t).toISOString().slice(0, 10)); }
    }
    return { days, r: Float64Array.from(doc.r || [], (x) => x / 1e4) };
  }
  function cum(r) { const c = new Float64Array(r.length + 1); for (let i = 0; i < r.length; i++) c[i + 1] = c[i] + r[i]; return c; }
  function moves(c, w) { const m = new Float64Array(c.length).fill(NaN); for (let j = w; j < c.length; j++) m[j] = c[j] - c[j - w]; return m; }
  function ahead(c, h) { const f = new Float64Array(c.length).fill(NaN); for (let j = 0; j + h < c.length; j++) f[j] = c[j + h] - c[j]; return f; }
  function lower(s, v) { let lo = 0, hi = s.length; while (lo < hi) { const m = (lo + hi) >> 1; if (s[m] < v) lo = m + 1; else hi = m; } return lo; }
  function upper(s, v) { let lo = 0, hi = s.length; while (lo < hi) { const m = (lo + hi) >> 1; if (s[m] <= v) lo = m + 1; else hi = m; } return lo; }
  // a value's mid-rank percentile (0–100) among the sorted values s
  function pctOf(s, v) { if (!s.length || !Number.isFinite(v)) return NaN; const lo = lower(s, v), hi = upper(s, v); return 100 * (lo + 0.5 * (hi - lo)) / s.length; }
  function quantile(s, q) { const n = s.length; if (!n) return NaN; const p = (n - 1) * q / 100, lo = Math.floor(p), hi = Math.ceil(p); return s[lo] + (s[hi] - s[lo]) * (p - lo); }
  /* Older days counting less (o.hl: the years over which a day's weight halves; worked out here only, the hub's summary
     counts every day the same). Weighted, a value's mid-rank percentile among sorted values s whose weights' running
     sums are cw (cw[0] = 0, cw[i]: the first i weights), and quantiles that put each sorted value at the middle of its
     weight on a 0–1 scale from the first to the last: with equal weights, exactly pctOf() and quantile(). */
  function pctW(s, cw, v) { if (!s.length || !Number.isFinite(v)) return NaN; const lo = lower(s, v), hi = upper(s, v); return 100 * (cw[lo] + 0.5 * (cw[hi] - cw[lo])) / cw[s.length]; }
  function wquant(s, sw) {
    const n = s.length;
    if (!n) return () => NaN;
    if (n === 1) return () => s[0];
    const pos = new Float64Array(n); let acc = 0;
    for (let i = 0; i < n; i++) { pos[i] = acc + sw[i] / 2; acc += sw[i]; }
    const a = pos[0], b = pos[n - 1] - a;
    for (let i = 0; i < n; i++) pos[i] = b > 0 ? (pos[i] - a) / b : i / (n - 1);
    return (q) => {
      const p = q / 100; let lo = 0, hi = n - 1;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pos[m] <= p) lo = m; else hi = m; }
      const d = pos[hi] - pos[lo];
      return d > 0 ? s[lo] + (s[hi] - s[lo]) * Math.min(1, Math.max(0, (p - pos[lo]) / d)) : s[lo];
    };
  }
  // each trading day's weight: a half for every hl years between it and the day looked at (before or after it)
  function ageWeights(A, ref, hl) {
    const ts = A.ts || (A.ts = Float64Array.from(A.days, (d) => Date.parse(d))), k = Math.LN2 / (hl * 365.25 * 864e5);
    return Float64Array.from(ts, (v) => Math.exp(-Math.abs(ref - v) * k));
  }
  // how many days of equal weight the weights of the days in mask are worth: (Σw)² / Σw²
  function neffOf(wt, mask) { let a = 0, b = 0; for (let j = 0; j < wt.length; j++) if (mask[j]) { a += wt[j]; b += wt[j] * wt[j]; } return b > 0 ? a * a / b : 0; }
  // each w-day move over the standard deviation of the n daily returns before it began, scaled to w days
  function volScaled(r, w, n = 63) {
    const c = cum(r), m = moves(c, w), s1 = cum(r), s2 = cum(Float64Array.from(r, (x) => x * x)), z = new Float64Array(c.length).fill(NaN);
    for (let j = w + n; j < c.length; j++) {
      const a = j - w - n, b = j - w, t1 = s1[b] - s1[a], t2 = s2[b] - s2[a], sd = Math.sqrt(Math.max((t2 - t1 * t1 / n) / (n - 1), 0));
      if (sd > 0) z[j] = m[j] / (sd * Math.sqrt(w));
    }
    return z;
  }
  // each w-day move less beta × the market's move over the same days, beta from the n trading days before the move
  function residual(A, Mk, w, n = 252) {
    const at = new Map(Mk.days.map((d, i) => [d, i])), cM = cum(Mk.r), cA = cum(A.r), N = A.days.length;
    const mi = A.days.map((d) => (at.has(d) ? at.get(d) : -1));
    const S = [new Float64Array(N), new Float64Array(N), new Float64Array(N), new Float64Array(N), new Float64Array(N)];   // prefix sums: a, m, a·m, m², count
    for (let k = 1; k < N; k++) {
      const ok = mi[k] >= 0 && mi[k - 1] >= 0, a = A.r[k - 1], m = ok ? cM[mi[k]] - cM[mi[k - 1]] : 0;
      const add = [ok ? a : 0, m, ok ? a * m : 0, m * m, ok ? 1 : 0];
      for (let q = 0; q < 5; q++) S[q][k] = S[q][k - 1] + add[q];
    }
    const e = new Float64Array(N).fill(NaN);
    for (let j = w + n; j < N; j++) {
      if (mi[j] < 0 || mi[j - w] < 0) continue;
      const a0 = j - w - n, b0 = j - w, cnt = S[4][b0] - S[4][a0];
      if (cnt < 0.8 * n) continue;
      const sa = S[0][b0] - S[0][a0], sm = S[1][b0] - S[1][a0], sam = S[2][b0] - S[2][a0], smm = S[3][b0] - S[3][a0];
      const vm = smm - sm * sm / cnt;
      if (!(vm > 0)) continue;
      const beta = (sam - sa * sm / cnt) / vm;
      e[j] = (cA[j] - cA[j - w]) - beta * (cM[mi[j]] - cM[mi[j - w]]);
    }
    return e;
  }
  // the forward returns f on the days of mask: simple returns' summary, and episodes (days within `gap` of the
  // previous chosen day belong to its episode). With weights wt (older days counting less): weighted mean, standard
  // deviation, quantiles and share up, sw (the weights in the order of s) and neff (the equal days they are worth).
  function stats(f, mask, gap, wt) {
    const idx = [], v = [];
    for (let j = 0; j < f.length; j++) if (mask[j] && Number.isFinite(f[j])) { idx.push(j); v.push(Math.expm1(f[j])); }
    if (!v.length) return null;
    let ep = 0, last = -Infinity;
    for (const j of idx) { if (j - last > gap) ep++; last = j; }
    const n = v.length;
    if (wt) {
      const ord = v.map((_, i) => i).sort((a, b) => v[a] - v[b]), s = Float64Array.from(ord, (i) => v[i]), sw = Float64Array.from(ord, (i) => wt[idx[i]]);
      let W = 0, W2 = 0, m1 = 0, upW = 0;
      for (let i = 0; i < n; i++) { W += sw[i]; W2 += sw[i] * sw[i]; m1 += sw[i] * s[i]; if (s[i] > 0) upW += sw[i]; }
      const mean = m1 / W, den = W - W2 / W;
      let ss = 0; for (let i = 0; i < n; i++) ss += sw[i] * (s[i] - mean) * (s[i] - mean);
      const Q = wquant(s, sw);
      return { n, ep, neff: W * W / W2, mean, sd: n > 1 && den > 0 ? Math.sqrt(ss / den) : 0, median: Q(50), up: upW / W, q: QS.map(Q), min: s[0], max: s[n - 1], s, sw, idx };
    }
    const s = Float64Array.from(v).sort(), mean = v.reduce((a, b) => a + b, 0) / n;
    const sd = n > 1 ? Math.sqrt(v.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (n - 1)) : 0;
    return { n, ep, mean, sd, median: quantile(s, 50), up: v.filter((x) => x > 0).length / n, q: QS.map((q) => quantile(s, q)), min: s[0], max: s[n - 1], s, idx };
  }
  // the first trading day after j, up to end, whose level c is at or above v (up) or at or below it: a sparse table of
  // maxima (of −c for "at or below") searched block by block, so each question costs about log2(days) steps
  function sparse(c) {
    const P = [Float64Array.from(c)];
    for (let p = 1; (1 << p) <= c.length; p++) {
      const prev = P[p - 1], half = 1 << (p - 1), cur = new Float64Array(c.length - (1 << p) + 1);
      for (let i = 0; i < cur.length; i++) cur[i] = Math.max(prev[i], prev[i + half]);
      P.push(cur);
    }
    return P;
  }
  function firstAt(P, from, v, end) {                       // smallest k in [from, end] with level ≥ v, or −1
    if (from > end) return -1;
    let k = from;
    for (let p = P.length - 1; p >= 0; p--) {
      if (k + (1 << p) - 1 <= end && P[p][k] < v) k += 1 << p;
      if (k > end) return -1;
    }
    return P[0][k] >= v ? k : -1;
  }
  // Kaplan–Meier over recovery times (censored at the last day observed), as app/moves.py's km(): the share recovered
  // by any day, the median (null when half never recovered). With weights wts, each day counts by its weight.
  function km(times, events, wts) {
    const ix = times.map((_, i) => i).sort((a, b) => times[a] - times[b] || events[b] - events[a]);
    let risk = wts ? wts.reduce((a, b) => a + b, 0) : times.length, S = 1, i = 0, median = null;
    const steps = [];
    while (i < ix.length) {
      const t0 = times[ix[i]]; let d = 0, gone = 0, j = i;
      while (j < ix.length && times[ix[j]] === t0) { const u = wts ? wts[ix[j]] : 1; if (events[ix[j]]) d += u; gone += u; j++; }
      if (d) { S = Math.max(0, S * (1 - d / risk)); steps.push([t0, S]); if (median === null && S <= 0.5) median = t0; }
      risk -= gone; i = j;
    }
    const by = (g) => { let v = 1; for (const [t0, sv] of steps) { if (t0 <= g) v = sv; else break; } return 1 - v; };
    return { n: times.length, events: events.filter(Boolean).length, median, by, steps };
  }
  // for the chosen days idx: trading days until the close got back to the close before the w-day move (side < 0:
  // climbed back; side > 0: gave the rise back) and until a new high (the highest close on file up to the day)
  function recovery(c, idx, w, side, end, T, wt) {
    const back = [[], []], high = [[], []], ws = [];
    for (const j of idx) {
      if (j - w < 0 || j >= end) continue;
      const kb = side < 0 ? firstAt(T.up, j + 1, c[j - w], end) : firstAt(T.dn, j + 1, -c[j - w], end);
      back[0].push((kb >= 0 ? kb : end) - j); back[1].push(kb >= 0);
      const kh = firstAt(T.up, j + 1, T.peak[j], end);
      high[0].push((kh >= 0 ? kh : end) - j); high[1].push(kh >= 0);
      if (wt) ws.push(wt[j]);
    }
    return { back: km(back[0], back[1], wt ? ws : undefined), high: km(high[0], high[1], wt ? ws : undefined) };
  }

  /* The whole analysis. A: a decoded asset; Mk: the market's (for the beta measure); o: {w, measure: raw | vol | beta,
     mode: latest | date | whatif, date, whatif (% or σ), band, before (only the history before the day)}. */
  // the annualized standard deviation of the n daily log returns ending at each day (NaN before): realized volatility
  function realized(r, n) {
    const c1 = cum(r), c2 = cum(Float64Array.from(r, (v) => v * v)), out = new Float64Array(r.length + 1).fill(NaN);
    for (let j = n; j <= r.length; j++) { const t1 = c1[j] - c1[j - n], t2 = c2[j] - c2[j - n]; out[j] = Math.sqrt(Math.max((t2 - t1 * t1 / n) / (n - 1), 0) * 252); }
    return out;
  }
  /* The whole analysis. A: a decoded asset (A.last: its last close); Mk: the market's (for the beta measure); Out: the
     outcome's (a volatility index is judged by what the S&P 500 did next); o: {w, measure: raw | vol | beta | rv |
     level, mode: latest | date | whatif, date, whatif (%, σ or a level), band, before (only the history before the
     day), vreg (similar: only days whose volatility before the move ranked within ±15 points of this one's), hl (older
     days count less: a day's weight halves for every hl years between it and the day looked at; 0: all the same)}. */
  function analyze(A, o, Mk, Out) {
    const lvl = o.measure === 'level', rvm = o.measure === 'rv';
    const w = lvl || rvm ? 1 : (o.w || 1), c = cum(A.r), N = c.length - 1;
    o._lv = { last: A.last || 1, cN: c[N] };
    const x = o.measure === 'vol' ? volScaled(A.r, w) : o.measure === 'beta' && Mk ? residual(A, Mk, w) : lvl ? Float64Array.from(c) : rvm ? realized(A.r, 21) : moves(c, w);
    let t = N, value;
    if (o.mode === 'date' && o.date) {
      t = -1;
      for (let j = N; j >= 0; j--) if (A.days[j] <= o.date && Number.isFinite(x[j])) { t = j; break; }
      if (t < 0) return { error: 'There is nothing to look at on or before ' + mdy(o.date) + '.' };
    } else if (o.mode !== 'whatif') {
      while (t >= 0 && !Number.isFinite(x[t])) t--;
      if (t < 0) return { error: 'Not enough history for this measure.' };
    }
    if (o.mode === 'whatif') {
      if (!fin(o.whatif)) return { error: 'Type a move to look at.' };
      value = o.measure === 'vol' ? +o.whatif : lvl ? Math.log(+o.whatif / (A.last || 1)) + c[N] : rvm ? +o.whatif / 100 : Math.log1p(+o.whatif / 100);
      if (!Number.isFinite(value)) return { error: lvl ? 'Type a level above zero.' : 'That move is not possible.' };
      t = -1;
    } else value = x[t];
    const before = o.before && t >= 0;
    const inS = new Uint8Array(N + 1);
    const vals = [];
    for (let j = 0; j <= N; j++) if (Number.isFinite(x[j]) && (!before || j <= t)) { inS[j] = 1; vals.push(x[j]); }
    if (vals.length < 60) return { error: 'Not enough history before this day for this measure.' };
    // older days counting less: each day's weight, the values sorted with their weights and the weights' running sums
    const hl = +o.hl > 0 ? +o.hl : 0, wt = hl ? ageWeights(A, Date.parse(A.days[t >= 0 ? t : N]), hl) : null;
    let s, sw = null, cw = null;
    if (wt) {
      const ids = []; for (let j = 0; j <= N; j++) if (inS[j]) ids.push(j);
      ids.sort((a, b) => x[a] - x[b]);
      s = Float64Array.from(ids, (j) => x[j]); sw = Float64Array.from(ids, (j) => wt[j]); cw = new Float64Array(s.length + 1);
      for (let i = 0; i < s.length; i++) cw[i + 1] = cw[i] + sw[i];
    } else s = Float64Array.from(vals).sort();
    const rank = (v) => (wt ? pctW(s, cw, v) : pctOf(s, v));
    const at = rank(value), side = at >= 50 ? 1 : -1;
    const p = new Float64Array(N + 1).fill(NaN);
    for (let j = 0; j <= N; j++) if (inS[j]) p[j] = rank(x[j]);
    // the volatility then: the 63 days before each move, as a percentile, when only similar regimes are to be compared
    let reg = null, regAt = null;
    if (o.vreg === 'similar' && !lvl) {
      const v63 = realized(A.r, 63), pre = new Float64Array(N + 1).fill(NaN), pv = [];
      for (let j = w; j <= N; j++) { pre[j] = v63[j - w]; if (Number.isFinite(pre[j]) && inS[j]) pv.push(pre[j]); }
      const ps = Float64Array.from(pv).sort();
      reg = new Float64Array(N + 1).fill(NaN);
      for (let j = 0; j <= N; j++) if (Number.isFinite(pre[j])) reg[j] = pctOf(ps, pre[j]);
      regAt = reg[t >= 0 ? t : N];
      if (!Number.isFinite(regAt)) reg = null;
    }
    const sim = new Uint8Array(N + 1), ext = new Uint8Array(N + 1), all = new Uint8Array(N + 1);
    let k = 0, kw = 0, lastAs = null;
    for (let j = 0; j <= N; j++) {
      if (!inS[j]) continue;
      const far = side > 0 ? p[j] >= at : p[j] <= at;
      if (far) { k++; kw += wt ? wt[j] : 1; if (j < (t >= 0 ? t : N + 1)) lastAs = j; }
      if (j === t || (reg && !(Math.abs(reg[j] - regAt) <= 15))) continue;
      all[j] = 1;
      if (Math.abs(p[j] - at) <= o.band) sim[j] = 1;
      if (far) ext[j] = 1;
    }
    const wi = o.mode === 'whatif' ? 1 : 0;                         // the move looked at counts itself, as today does
    k += wi; kw += wi;
    let kEp = 0, prev = -Infinity;                                   // separate episodes of such moves (overlapping windows once)
    for (let j = 0; j <= N; j++) if (inS[j] && (side > 0 ? p[j] >= at : p[j] <= at)) { if (j - prev > w) kEp++; prev = j; }
    const years = Math.max((Date.parse(A.days[N]) - Date.parse(A.days[0])) / (365.25 * 864e5), 0.1);
    const out = { A, x, t, value, at, side, n: s.length, every: k ? ((wt ? cw[s.length] : s.length) + wi) / kw : null, k, kEp, years, lastAs, sim, ext, all, h: {}, actual: {}, s, p,
      raw: t >= w && !lvl && !rvm ? Math.expm1(c[t] - c[t - w]) : null, reg: reg ? regAt : null, out: Out ? Out.name || 'the S&P 500' : null };
    if (wt) Object.assign(out, { hl, wt, sw, ref: A.days[t >= 0 ? t : N], neff: neffOf(wt, inS), neffSim: neffOf(wt, sim) });
    // what came next: the asset's own returns, or the outcome's on the same days
    const oAt = Out ? new Map(Out.days.map((d, i) => [d, i])) : null, co = Out ? cum(Out.r) : null;
    out.c = c;
    if (Out) { out.oc = co; out.oq = Int32Array.from(A.days, (d) => { const q = oAt.get(d); return q == null ? -1 : q; }); }
    const ahead2 = (h) => {
      if (!Out) return ahead(c, h);
      const f = new Float64Array(N + 1).fill(NaN);
      for (let j = 0; j <= N; j++) { const q = oAt.get(A.days[j]); if (q != null && q + h < co.length) f[j] = co[q + h] - co[q]; }
      return f;
    };
    for (const [h] of H) {
      const f = ahead2(h);
      if (before) for (let j = 0; j <= N; j++) if (j + h > t) f[j] = NaN;   // only what was known on the day
      const gap = Math.max(h, w);
      out.h[h] = { sim: stats(f, sim, gap, wt), ext: stats(f, ext, gap, wt), all: stats(f, all, gap, wt), f };
      if (t >= 0) {
        if (!Out && t + h <= N) out.actual[h] = Math.expm1(c[t + h] - c[t]);
        if (Out) { const q = oAt.get(A.days[t]); if (q != null && q + h < co.length) out.actual[h] = Math.expm1(co[q + h] - co[q]); }
      }
    }
    if (!Out && !lvl) {                                  // the volatility of the month after: shocks come in clusters
      const rv = realized(A.r, 21), fv = new Float64Array(N + 1).fill(NaN);
      for (let j = 0; j + 21 <= N; j++) if (!before || j + 21 <= t) fv[j] = rv[j + 21];
      const med = (mask) => {
        const ids = []; for (let j = 0; j <= N; j++) if (mask[j] && Number.isFinite(fv[j])) ids.push(j);
        if (!ids.length) return null;
        if (!wt) return { n: ids.length, median: quantile(Float64Array.from(ids, (j) => fv[j]).sort(), 50) };
        ids.sort((a, b) => fv[a] - fv[b]);
        return { n: ids.length, median: wquant(Float64Array.from(ids, (j) => fv[j]), Float64Array.from(ids, (j) => wt[j]))(50) };
      };
      out.fvol = { sim: med(sim), ext: med(ext), all: med(all), now: rv[t >= 0 ? t : N], next: t >= 0 && t + 21 <= N ? rv[t + 21] : null };
    }
    if (Out || lvl || rvm) return out;                   // how long it took: for moves of a price only
    // how long it took: days like it, at least as extreme, and every day that moved the same way (the raw move's sign)
    const T = { up: sparse(c), dn: sparse(Array.from(c, (v) => -v)), peak: new Float64Array(N + 1) };
    for (let j = 0, m = -Infinity; j <= N; j++) { m = Math.max(m, c[j]); T.peak[j] = m; }
    const rs = (o.mode === 'whatif' ? Math.sign(value) : Math.sign(c[t] - c[t - w])) || -1, end = before ? t : N;
    const ids = (mask) => { const a = []; for (let j = 0; j <= N; j++) if (mask[j]) a.push(j); return a; };
    const same = new Uint8Array(N + 1);
    for (let j = w; j <= N; j++) if (all[j] && Math.sign(c[j] - c[j - w]) === rs) same[j] = 1;
    out.rec = { side: rs, sim: recovery(c, ids(sim), w, rs, end, T, wt), ext: recovery(c, ids(ext), w, rs, end, T, wt), base: recovery(c, ids(same), w, rs, end, T, wt) };
    if (t >= w) {                                        // the day looked at: how far to go, and how long it took when known
      let pk = 0; for (let j = 1; j <= t; j++) if (c[j] > c[pk]) pk = j;
      const kb = rs < 0 ? firstAt(T.up, t + 1, c[t - w], N) : firstAt(T.dn, t + 1, -c[t - w], N), kh = firstAt(T.up, t + 1, T.peak[t], N);
      out.rec.now = { pre: t - w, peak: pk, back: Math.expm1(c[t - w] - c[t]), high: Math.expm1(T.peak[t] - c[t]),
        backIn: kb >= 0 ? kb - t : null, highIn: kh >= 0 ? kh - t : null, since: N - t };
    }
    return out;
  }

  /* ---------- formatting ---------- */
  const unit = (o) => (o.measure === 'vol' ? 'σ' : o.measure === 'level' ? '' : '%');
  const disp = (o, v) => (o.measure === 'vol' ? v : o.measure === 'level' ? (o._lv ? o._lv.last * Math.exp(v - o._lv.cN) : Math.exp(v))
    : o.measure === 'rv' ? v * 100 : Math.expm1(v) * 100);                                    // the measure as shown
  const fmtX = (o, v, d) => {
    if (o.measure === 'vol') return sgn(v, d == null ? 1 : d, 'σ');
    if (o.measure === 'level') { const l = disp(o, v); return num(l, d == null ? (l < 10 ? 2 : 1) : d); }
    if (o.measure === 'rv') return num(v * 100, d == null ? 0 : d) + '%';
    return sgn(Math.expm1(v) * 100, d == null ? 1 : d);
  };
  const tickFmt = (o, v) => (o.measure === 'level' || o.measure === 'rv' ? num(v, Math.abs(v) < 10 && v % 1 ? 1 : 0) + unit(o) : sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0, unit(o)));
  // the side's colour: for a price, up green and down red; for a level of volatility (an index's level, a stock's own
  // volatility), high orange and low slate — high volatility is no good news, low no bad
  const lvlm = (o) => o.measure === 'level' || o.measure === 'rv';
  const sideCol = (R, o) => (lvlm(o) ? (R.side > 0 ? COL.warn : COL.calm) : R.side > 0 ? COL.up : COL.down);
  const sideCls = (R, o) => (lvlm(o) ? (R.side > 0 ? 'mv-warn' : 'mv-calm') : R.side > 0 ? 'mv-up' : 'mv-down');
  const sidePC = (R, o) => (lvlm(o) ? (R.side > 0 ? PC.warn : PC.calm) : R.side > 0 ? PC.up : PC.down);
  const rankWords = (at) => (at >= 50 ? `top ${num(Math.max(100 - at, 0.05), 100 - at < 1 ? 2 : 1)}%` : `bottom ${num(Math.max(at, 0.05), at < 1 ? 2 : 1)}%`);
  const measureName = (o) => (o.measure === 'vol' ? 'against its own recent volatility' : o.measure === 'beta' ? 'beyond what the market\'s move implied' : o.measure === 'level' ? 'its level' : o.measure === 'rv' ? 'its own volatility over the last month' : '% change');
  const what = (o) => (o.measure === 'level' ? 'level' : o.measure === 'rv' ? 'one-month volatility' : `${win(o.w)} move`);
  const whats = (o) => (o.measure === 'level' ? 'daily levels' : o.measure === 'rv' ? 'readings of its one-month volatility' : `${win(o.w)} moves`);
  const win = (w) => (w === 1 ? 'one-day' : w === 5 ? 'one-week (5-day)' : 'one-month (21-day)');
  const tone = (v) => (fin(v) ? (v > 0 ? 'mv-up' : v < 0 ? 'mv-down' : '') : '');

  function css() {
    if (typeof document === 'undefined' || !document.head || document.getElementById('mv-css')) return;
    const s = document.createElement('style'); s.id = 'mv-css';
    s.textContent = `.mv svg{display:block;width:100%;height:auto}.mv svg.mv-chart{max-width:860px;margin:4px 0}.mv h3{margin:22px 0 6px;font-size:17px}.mv h4{margin:14px 0 4px;font-size:14.5px}
.mv .mv-sub{color:var(--muted,#777);font-size:13px;line-height:1.55;margin:0 0 10px;max-width:92ch}
.mv-head{font-size:18px;line-height:1.45;margin:6px 0 10px;max-width:70ch}.mv-head b{font-weight:650}
.mv-bar{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:flex-end;margin:6px 0 10px}.mv-bar>div{display:flex;flex-direction:column;gap:3px}
.mv-bar label{font-size:11.5px;color:var(--muted,#777);text-transform:uppercase;letter-spacing:.04em}
.mv-pills{display:flex;flex-wrap:wrap;gap:6px}.mv-pill{font:inherit;font-size:12.5px;border:1px solid var(--line,#ddd);background:none;border-radius:999px;padding:3px 10px;cursor:pointer;color:var(--muted,#666)}
.mv-pill.on{color:var(--ink,#222);border-color:var(--ink,#222);font-weight:600}.mv-pill:disabled{opacity:.45;cursor:default}
.mv-in{font:inherit;font-size:13px;padding:3px 8px;border:1px solid var(--line,#ccc);border-radius:8px;background:var(--surface,#fff);color:var(--ink,#222);width:9.5em}
.mv-assets{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 10px}.mv-asset{font:inherit;font-size:13px;border:1px solid var(--line,#ddd);background:var(--surface,#fff);border-radius:10px;padding:5px 11px;cursor:pointer;color:var(--ink,#222);text-align:left}
.mv-asset small{display:block;font-size:11px;color:var(--muted,#777)}.mv-asset.on{border-color:var(--ink,#222);box-shadow:inset 0 0 0 1px var(--ink,#222)}
.mv-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin:6px 0 12px}.mv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 10px;min-width:0}
.mv-card span{display:block;font-size:12px;color:var(--muted,#777)}.mv-card b{font-size:19px;font-variant-numeric:tabular-nums}.mv-card i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777);line-height:1.4}
.mv-wrap{overflow-x:auto;max-width:100%}.mv-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.mv-tbl th,.mv-tbl td{padding:5px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:middle;white-space:nowrap}
.mv-tbl .n{text-align:right;font-variant-numeric:tabular-nums}.mv-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}.mv-tbl td.box{padding:2px 6px;width:220px;min-width:160px}
.mv-tbl tr.grp td{font-weight:650;background:color-mix(in srgb,var(--ink,#222) 4%,transparent)}.mv-tbl td.box svg{width:100%;height:22px}
.mv-up{color:var(--mk-profit,#17734a)}.mv-down{color:var(--mk-cost,#c0392b)}.mv-warn{color:var(--q-warm,#d9822b)}.mv-calm{color:#5b7fa6}
.mv-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.mv-legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.mv-g{stroke:var(--line,#e3e3e3);stroke-width:1}.mv-t{fill:var(--muted,#777);font-size:12px}.mv-l{fill:var(--ink,#222);font-size:12.5px;paint-order:stroke;stroke:var(--surface,#fff);stroke-width:3px}
.mv-note{font-size:12px;color:var(--muted,#777);line-height:1.55;margin-top:10px;max-width:92ch}.mv-apx{border:1px solid var(--line,#ddd);border-radius:10px;padding:6px 12px;margin:10px 0;max-width:980px}
.mv-apx summary{cursor:pointer;font-size:13.5px}.mv-apx p{font-size:13px;line-height:1.55;margin:6px 0;max-width:92ch}.mv-err{color:var(--mk-cost,#c0392b);font-size:13px}.mv-range{width:200px;accent-color:var(--ink,#222);vertical-align:middle}.mv-cases{max-height:620px;overflow:auto;border:1px solid var(--line,#e5e5e5);border-radius:10px}.mv-cases .mv-tbl{margin:0}.mv-cases th{position:sticky;top:0;background:var(--surface,#fff);z-index:1}.mv-cases td.news{white-space:normal;min-width:260px;max-width:520px;font-size:12.5px;line-height:1.45}.mv-news{margin:0 0 6px}.mv-news:last-child{margin:0}.mv-chip{display:inline-block;font-size:11px;border:1px solid var(--line,#ddd);border-radius:999px;padding:0 7px;margin:0 4px 2px 0;color:var(--muted,#666)}.mv-chip.hot{border-color:var(--q-warm,#d9822b);color:var(--q-warm,#b5651d)}.mv-news a{color:inherit}.mv-news .q{color:var(--muted,#777);display:block}.mv-cases tr.now td{background:color-mix(in srgb,var(--q-warm,#d9822b) 10%,transparent)}
.mv-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}@media (max-width:860px){.mv-two{grid-template-columns:minmax(0,1fr)}}
.mv-png{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;margin:4px 0 12px;padding:8px 10px;border:1px dashed var(--line,#ccc);border-radius:10px;font-size:13px}
.mv-png-l{font-weight:600}.mv-png label{display:inline-flex;gap:4px;align-items:center;cursor:pointer}.mv-png-out img{display:block;max-width:min(100%,900px);height:auto;border:1px solid var(--line,#ddd);border-radius:10px;margin:6px 0}
.mv-png-out .mv-png-acts{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 14px}.mv-png-out a,.mv-png-out button{font:inherit;font-size:13px;padding:4px 12px;border-radius:8px;border:1px solid var(--line,#ccc);background:var(--surface,#fff);color:var(--ink,#222);cursor:pointer;text-decoration:none}
@media (max-width:640px){.mv-head{font-size:16px}.mv-card b{font-size:17px}.mv-in{width:8em}}`;
    document.head.appendChild(s);
  }

  /* ---------- charts ---------- */
  function ticks(lo, hi, n = 5) {
    const raw = (hi - lo) / n || 1, p = 10 ** Math.floor(Math.log10(raw)), st = [1, 2, 2.5, 5, 10].map((m) => m * p).find((v) => v >= raw);
    const out = []; for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(6)); return out;
  }
  // the years to label on a time axis from y0 to y1: a round step (1, 2, 5, 10, 20, 25 or 50 years) for about n labels
  function yearTicks(y0, y1, n) {
    const st = [1, 2, 5, 10, 20, 25, 50].find((s) => s >= (y1 - y0) / n) || 100, out = [];
    for (let y = Math.ceil((y0 + 1) / st) * st; y <= y1; y += st) out.push(y);
    return out;
  }
  // where the move ranks: every day's move as a histogram, the move looked at marked, the tail beyond it shaded
  function rankSvg(R, o) {
    const W = o.narrow ? 440 : 720;
    const vals = Array.from(R.s, (v) => disp(o, v)), tv = disp(o, R.value), u = unit(o);
    let lo = quantile(Float64Array.from(vals), 0.4), hi = quantile(Float64Array.from(vals), 99.6);
    lo = Math.min(lo, tv); hi = Math.max(hi, tv);
    const pad = (hi - lo) * 0.04; lo -= pad; hi += pad;
    const nb = 56, bw = (hi - lo) / nb, cnt = new Array(nb).fill(0), bin = (v) => Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / bw)));
    const eq = R.sw ? new Array(nb).fill(0) : null;                   // weighted: each bar its share of the weight; dashed, every day the same
    if (eq) { const Wt = R.sw.reduce((a, b) => a + b, 0); vals.forEach((v, i) => { cnt[bin(v)] += R.sw[i] / Wt; eq[bin(v)] += 1 / vals.length; }); }
    else vals.forEach((v) => { cnt[bin(v)]++; });
    const Hh = o.narrow ? 220 : 230, L = 14, Rr = 14, T = 26, B = 34, mx = Math.max(...cnt, ...(eq || [])) || 1;
    const sx = (v) => L + (v - lo) / (hi - lo) * (W - L - Rr), sy = (n) => T + (1 - n / mx) * (Hh - T - B);
    const tb = Math.min(nb - 1, Math.max(0, Math.floor((tv - lo) / bw)));
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Every ${esc(what(o))} on file, with the one looked at marked">`;
    ticks(lo, hi, o.narrow ? 4 : 7).forEach((v) => { g += `<line class="mv-g" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${Hh - B}"/><text class="mv-t" x="${sx(v)}" y="${Hh - B + 16}" text-anchor="middle">${esc(tickFmt(o, v))}</text>`; });
    cnt.forEach((n, i) => {
      if (!n) return;
      const x0 = sx(lo + i * bw), x1 = sx(lo + (i + 1) * bw), mid = lo + (i + 0.5) * bw;
      const tail = R.side > 0 ? mid >= tv : mid <= tv;
      const col = i === tb ? COL.ink : tail ? sideCol(R, o) : COL.all;
      g += `<rect x="${(x0 + 0.5).toFixed(1)}" y="${sy(n).toFixed(1)}" width="${Math.max(0.8, x1 - x0 - 1).toFixed(1)}" height="${(Hh - B - sy(n)).toFixed(1)}" style="fill:${col};opacity:${i === tb ? 1 : tail ? 0.75 : 0.45}"/>`;
    });
    if (eq) g += `<path d="${eq.map((n, i) => `${i ? 'L' : 'M'}${sx(lo + i * bw).toFixed(1)},${sy(n).toFixed(1)}L${sx(lo + (i + 1) * bw).toFixed(1)},${sy(n).toFixed(1)}`).join('')}" style="fill:none;stroke:${COL.ink};stroke-width:1.2;stroke-dasharray:4 3;opacity:.7"/>`;
    const xt = sx(tv);
    g += `<line x1="${xt}" x2="${xt}" y1="${T - 8}" y2="${Hh - B}" style="stroke:${COL.ink};stroke-width:1.5;stroke-dasharray:4 3"/>`;
    const lab = `${o.mode === 'whatif' ? 'what if' : esc(mdy(R.A.days[R.t]))}: ${esc(fmtX(o, R.value))} · ${rankWords(R.at)}`;
    g += `<text class="mv-l" x="${Math.min(Math.max(xt, L + 110), W - Rr - 110)}" y="${T - 12}" text-anchor="middle" style="font-weight:600">${lab}</text>`;
    g += `<text class="mv-t" x="${L}" y="${Hh - 4}">${esc(num(R.n))} ${esc(whats(o))} since ${esc(my(R.A.days[0]))}</text></svg>`;
    return g;
  }
  // what came next, for one horizon: the chosen days' returns and every day's, as share-of-days histograms
  function nextSvg(R, o, h, which) {
    const S = R.h[h][which], A = R.h[h].all;
    if (!S || !A) return '<p class="mv-sub">No days to show.</p>';
    const pool = Float64Array.from([...S.s, ...A.s]).sort();
    let lo = Math.min(quantile(pool, 1), 0), hi = Math.max(quantile(pool, 99), 0);
    if (fin(R.actual[h])) { lo = Math.min(lo, R.actual[h]); hi = Math.max(hi, R.actual[h]); }
    const pad = (hi - lo) * 0.05; lo -= pad; hi += pad;
    const nb = 40, bw = (hi - lo) / nb;
    const hist = (s, w) => {                                         // each bin's share of the days (of their weight, when weighted)
      const c = new Array(nb).fill(0); let tot = 0;
      s.forEach((v, i) => { const u = w ? w[i] : 1; c[Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / bw)))] += u; tot += u; });
      return c.map((n) => n / (tot || 1));
    };
    const E = R.eq && R.eq.h[h] && R.eq.h[h][which];                 // the days like it with every day the same: dashed
    const hs = hist(S.s, S.sw), ha = hist(A.s, A.sw), he = E ? hist(E.s) : null, mx = Math.max(...hs, ...ha, ...(he || [])) || 1;
    const W = o.narrow ? 440 : 720, Hh = 220, L = 14, Rr = 14, T = 22, B = 34;
    const sx = (v) => L + (v - lo) / (hi - lo) * (W - L - Rr), sy = (n) => T + (1 - n / mx) * (Hh - T - B);
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Returns over the ${esc(H.find((x) => x[0] === h)[1].toLowerCase())} after the chosen days and after every day">`;
    ticks(lo * 100, hi * 100, o.narrow ? 4 : 7).forEach((v) => { g += `<line class="mv-g" x1="${sx(v / 100)}" x2="${sx(v / 100)}" y1="${T}" y2="${Hh - B}"/><text class="mv-t" x="${sx(v / 100)}" y="${Hh - B + 16}" text-anchor="middle">${esc(sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0))}</text>`; });
    g += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${Hh - B}" style="stroke:${COL.mute};stroke-width:1"/>`;
    hs.forEach((n, i) => { if (n) g += `<rect x="${(sx(lo + i * bw) + 0.6).toFixed(1)}" y="${sy(n).toFixed(1)}" width="${Math.max(0.8, sx(lo + (i + 1) * bw) - sx(lo + i * bw) - 1.2).toFixed(1)}" height="${(Hh - B - sy(n)).toFixed(1)}" style="fill:${lo + (i + 0.5) * bw >= 0 ? COL.up : COL.down};opacity:.6"/>`; });
    let path = '';
    ha.forEach((n, i) => { const x0 = sx(lo + i * bw), x1 = sx(lo + (i + 1) * bw); path += `${i ? 'L' : 'M'}${x0.toFixed(1)},${sy(n).toFixed(1)}L${x1.toFixed(1)},${sy(n).toFixed(1)}`; });
    g += `<path d="${path}" style="fill:none;stroke:${COL.ink};stroke-width:1.4;opacity:.7"/>`;
    if (he) g += `<path d="${he.map((n, i) => `${i ? 'L' : 'M'}${sx(lo + i * bw).toFixed(1)},${sy(n).toFixed(1)}L${sx(lo + (i + 1) * bw).toFixed(1)},${sy(n).toFixed(1)}`).join('')}" style="fill:none;stroke:${COL.band};stroke-width:1.5;stroke-dasharray:5 3"/>`;
    const mark = (v, lab, col, y) => { g += `<line x1="${sx(v)}" x2="${sx(v)}" y1="${T - 4}" y2="${Hh - B}" style="stroke:${col};stroke-width:1.6;stroke-dasharray:5 3"/><text class="mv-l" x="${Math.min(Math.max(sx(v), L + 70), W - Rr - 70)}" y="${y}" text-anchor="middle">${lab}</text>`; };
    mark(S.median, `median ${esc(sp(S.median))}`, COL.band, T - 8);
    if (fin(R.actual[h])) mark(R.actual[h], `what happened: ${esc(sp(R.actual[h]))}`, COL.warn, Hh - B - 6);
    g += '</svg>';
    return g;
  }
  // one row's box: 5–95% whiskers, 25–75% box, median tick, on a shared axis
  function boxSvg(S, lo, hi, col, actual) {
    if (!S) return '';
    const W = 220, sx = (v) => 4 + (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo || 1) * (W - 8), q = S.q;
    let g = `<svg viewBox="0 0 ${W} 22" preserveAspectRatio="none" aria-hidden="true"><line x1="${sx(0)}" x2="${sx(0)}" y1="1" y2="21" style="stroke:${COL.mute};stroke-width:1;stroke-dasharray:2 2"/>`;
    g += `<line x1="${sx(q[0])}" x2="${sx(q[6])}" y1="11" y2="11" style="stroke:${col};stroke-width:1.4"/><rect x="${sx(q[2])}" y="5" width="${Math.max(1.5, sx(q[4]) - sx(q[2]))}" height="12" rx="2" style="fill:${col};opacity:.35;stroke:${col}"/>`;
    g += `<line x1="${sx(q[3])}" x2="${sx(q[3])}" y1="3" y2="19" style="stroke:${COL.ink};stroke-width:2"/>`;
    if (fin(actual)) g += `<circle cx="${sx(actual)}" cy="11" r="3.5" style="fill:${COL.warn};stroke:#fff;stroke-width:1"/>`;
    return g + '</svg>';
  }
  // when moves like this happened: every day's move over time, the chosen days coloured
  function timeSvg(R, o) {
    const A = R.A, N = A.days.length - 1;
    const t0 = Date.parse(A.days[0]), t1 = Date.parse(A.days[o.before && o.mode === 'date' && R.t >= 0 ? R.t : N]);
    const vs = Float64Array.from(R.s, (v) => disp(o, v));
    if (!vs.length) return '';
    let lo = Math.min(quantile(vs, 0.15), disp(o, R.value)), hi = Math.max(quantile(vs, 99.85), disp(o, R.value));
    const W = o.narrow ? 440 : 720, Hh = 210, L = 46, Rr = 12, T = 12, B = 26, pad = (hi - lo) * 0.05; lo -= pad; hi += pad;
    const sx = (d) => L + (Date.parse(d) - t0) / (t1 - t0 || 1) * (W - L - Rr), sy = (v) => T + (hi - Math.min(hi, Math.max(lo, v))) / (hi - lo) * (Hh - T - B);
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Every ${esc(what(o))} over time, the days like the one looked at coloured">`;
    ticks(lo, hi, 4).forEach((v) => { g += `<line class="mv-g" x1="${L}" x2="${W - Rr}" y1="${sy(v)}" y2="${sy(v)}"/><text class="mv-t" x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${esc(tickFmt(o, v))}</text>`; });
    yearTicks(+A.days[0].slice(0, 4), new Date(t1).getUTCFullYear(), o.narrow ? 5 : 10).forEach((y) => { g += `<text class="mv-t" x="${sx(`${y}-01-01`)}" y="${Hh - 8}" text-anchor="middle">${y}</text>`; });
    let grey = '', hot = '';
    for (let j = 0; j <= N; j++) {
      if (!R.all[j]) continue;
      const v = disp(o, R.x[j]), cx = sx(A.days[j]).toFixed(1), cy = sy(v).toFixed(1), fade = R.wt ? 0.12 + 0.88 * R.wt[j] : 1;   // weighted: older days fainter
      if (R.sim[j] || R.ext[j]) hot += `<circle cx="${cx}" cy="${cy}" r="${R.sim[j] ? 2.6 : 2}" style="fill:${sideCol(R, o)};opacity:${((R.sim[j] ? 0.95 : 0.55) * fade).toFixed(2)}"/>`;
      else if (j % (N > 6000 ? 3 : 1) === 0) grey += `<circle cx="${cx}" cy="${cy}" r="1.2" style="fill:${COL.all};opacity:${(0.35 * fade).toFixed(2)}"/>`;
    }
    g += grey + hot;
    if (R.t >= 0) g += `<circle cx="${sx(A.days[R.t])}" cy="${sy(disp(o, R.value))}" r="5" style="fill:none;stroke:${COL.ink};stroke-width:2"/>`;
    return g + '</svg>';
  }

  /* ---------- sections ---------- */
  function headline(R, o, doc) {
    const name = esc(doc.ticker || doc.name), A = R.A, span = o.w === 1 ? '' : o.w === 5 ? ' over a week (5 trading days)' : ' over a month (21 trading days)';
    const lv = o.measure === 'level', rv = o.measure === 'rv';
    let lead;
    if (o.mode === 'whatif') {
      lead = lv ? `If ${name} stood at ${esc(fmtX(o, R.value))}` : rv ? `If ${name}'s volatility over a month were ${esc(fmtX(o, R.value))} a year`
        : `If ${name} moved ${esc(fmtX(o, R.value))}${o.measure === 'vol' ? ' of its own recent volatility' : o.measure === 'beta' ? " beyond what the market's move implied" : ''} in ${o.w === 1 ? 'a day' : o.w === 5 ? 'a week' : 'a month'}`;
    } else if (lv) {
      lead = `${esc(mdy(A.days[R.t]))}: ${name} closed at ${esc(fmtX(o, R.value))}`;
    } else if (rv) {
      lead = `${esc(mdy(A.days[R.t]))}: ${name}'s volatility over the last month was ${esc(fmtX(o, R.value))} a year`;
    } else {
      const raw = R.raw, verb = !fin(raw) || raw === 0 ? 'was flat' : raw > 0 ? 'rose' : 'fell';
      lead = `${esc(mdy(A.days[R.t]))}: ${name} ${verb}${fin(raw) && raw !== 0 ? ' ' + esc(num(Math.abs(raw) * 100, 1)) + '%' : ''}${span}`
        + (o.measure === 'vol' ? `, ${esc(fmtX(o, R.value))} against its own recent volatility` : o.measure === 'beta' ? `, ${esc(fmtX(o, R.value))} beyond what the market's move implied` : '');
    }
    const p = R.side > 0 ? 100 - R.at : R.at, noun = lv || rv ? 'level' : o.w === 1 ? 'day' : 'move';
    if (R.hl) {
      return `<p class="mv-head">${lead}: a <b class="${sideCls(R, o)}">${rankWords(R.at)}</b> ${noun} with older days counting less (half ${esc(hlWords(R.hl))}) — `
        + `${R.eq ? `${rankWords(R.eq.at)} unweighted, of` : 'among'} the ${num(R.n)} ${esc(whats(o))} since ${esc(mdy(A.days[0]))}.</p>`;
    }
    return `<p class="mv-head">${lead}: a <b class="${sideCls(R, o)}">${rankWords(R.at)}</b> ${noun} — `
      + `of the ${num(R.n)} ${esc(whats(o))} since ${esc(mdy(A.days[0]))}, ${num(p, p < 1 ? 2 : 1)}% were this ${R.side > 0 ? 'high' : 'low'} or ${R.side > 0 ? 'higher' : 'lower'}.</p>`;
  }
  // with older days counting less: how the weights fall, and how many equal days they are worth
  function weightNote(R, o) {
    if (!R.hl || R.error) return '';
    const f = (y) => num(100 * Math.pow(0.5, y / R.hl), y / R.hl > 4 ? 1 : 0) + '%';
    const yrs = [R.hl, 2 * R.hl, 4 * R.hl].filter((y) => y <= Math.max(R.years, R.hl));
    return `<p class="mv-sub" style="color:var(--ink,#222)">Older days count less: a day's weight halves ${esc(hlWords(R.hl))} between it and ${esc(mdy(R.ref))}`
      + ` (${yrs.map((y) => `${y} year${y === 1 ? '' : 's'} away: ${f(y)}`).join(', ')}). The ${num(R.n)} ${esc(whats(o))} together count like about ${num(R.neff)} of full weight`
      + `${R.neffSim ? `, the days like it like about ${num(R.neffSim)}` : ''}. The dashed lines and "unweighted" figures count every day the same.</p>`;
  }
  function cards(R, o) {
    const every = R.every, a = R.side > 0 ? 'rise' : 'fall', lv = o.measure === 'level' || o.measure === 'rv';
    const perYear = o.w === 1 ? (R.hl ? R.n / R.years / every : R.k / R.years) : R.kEp / R.years;     // weighted: at the recent pace
    const card = (l, v, note, cls) => `<div class="mv-card"><span>${l}</span><b class="${cls || ''}">${v}</b>${note ? `<i>${note}</i>` : ''}</div>`;
    const sim = R.h[21].sim, all = R.h[21].all, then = R.out ? ` (${esc(R.out)})` : '', E = R.eq, eSim = E && E.h[21].sim;
    return `<div class="mv-cards">${card('Percentile', num(R.at, R.at < 1 || R.at > 99 ? 2 : 1), R.hl ? `${rankWords(R.at)}, older days counting less${E ? ` · unweighted: ${num(E.at, E.at < 1 || E.at > 99 ? 2 : 1)}` : ''}` : `${rankWords(R.at)} of ${num(R.n)} ${lv ? 'days' : 'moves'}`, sideCls(R, o))}`
      + (lv ? card(`A level this ${R.side > 0 ? 'high' : 'low'} or ${R.side > 0 ? 'higher' : 'lower'}`, fin(every) ? `1 in ${num(every, every < 10 ? 1 : 0)}` : '—', `days${R.hl ? ', weighted' : ''} · in ${num(R.kEp)} separate stretches`)
        : o.w === 1 ? card(`A ${a} this large or larger`, fin(every) ? `1 in ${num(every, every < 10 ? 1 : 0)}` : '—', `trading days · about ${num(perYear, perYear < 10 ? 1 : 0)} a year${R.hl ? ' lately' : ''}`)
        : card(`${o.w === 5 ? 'Weeks' : 'Months'} with a ${a} this large`, num(R.kEp), `separate episodes in ${num(R.years, 0)} years · about ${num(perYear, perYear < 10 ? 1 : 0)} a year`))
      + card('Last time before', R.lastAs != null ? esc(mdy(R.A.days[R.lastAs])) : 'never', R.lastAs != null ? ((d) => `${num(d)} day${d === 1 ? '' : 's'} earlier`)(Math.round((Date.parse(R.A.days[R.t >= 0 ? R.t : R.A.days.length - 1]) - Date.parse(R.A.days[R.lastAs])) / 864e5)) : 'not on file')
      + card(`Next month after days like it${then}`, sim ? sp(sim.median) : '—', sim ? `median · ${share(sim.up)} rose · every day: ${sp(all && all.median)}, ${share(all && all.up)}${eSim ? ` · unweighted: ${sp(eSim.median)}, ${share(eSim.up)}` : ''}` : '', sim ? tone(sim.median) : '')
      + (R.fvol && R.fvol.sim ? card('Volatility the month after', `${num(R.fvol.sim.median * 100, 0)}%`, `a year, median after days like it · every day: ${num(R.fvol.all && R.fvol.all.median * 100, 0)}% · now ${num(R.fvol.now * 100, 0)}%`) : '')
      + '</div>';
  }
  function verdict(S, A) {
    if (!S || !A || S.n < 2) return '';
    const ep = S.neff ? S.ep * S.neff / S.n : S.ep;                  // weighted: the episodes scaled to the equal days they are worth
    const se = S.sd / Math.sqrt(Math.max(1, ep)), z = se > 0 ? (S.mean - A.mean) / se : 0;
    if (ep < 8) return `<span class="mv-sub" style="display:inline">too few episodes to tell</span>`;
    return Math.abs(z) >= 2 ? `<b class="${z > 0 ? 'mv-up' : 'mv-down'}">${z > 0 ? 'better' : 'worse'} than usual</b>` : '<span class="mv-sub" style="display:inline">within chance</span>';
  }
  function nextTable(R, o) {
    const label = { sim: `Days like it (±${fb(o.band)} pts)`, ext: `At least as ${R.side > 0 ? 'high' : 'low'}`, all: 'Every day' };
    const col = { sim: COL.band, ext: sideCol(R, o), all: COL.all };
    let h = '<div class="mv-wrap"><table class="mv-tbl"><thead><tr><th></th><th class="n">Median</th><th class="n">Rose</th><th>Range: 5–95% (line), 25–75% (box), median</th><th class="n">Mean</th><th class="n">5% worst</th><th class="n">5% best</th><th class="n">Days</th><th class="n">Episodes</th><th>vs every day</th></tr></thead><tbody>';
    for (const [hz, hl] of H) {
      const g = R.h[hz], qs = ['sim', 'ext', 'all'].map((k) => g[k]).filter(Boolean);
      if (!qs.length) continue;
      const act = fin(R.actual[hz]) ? [R.actual[hz]] : [];
      const lo = Math.min(0, ...act, ...qs.map((S) => S.q[0])), hi = Math.max(0, ...act, ...qs.map((S) => S.q[6]));
      h += `<tr class="grp"><td colspan="10">${hl}${R.out ? ` · ${esc(R.out)}` : ''}${fin(R.actual[hz]) ? ` · <span style="font-weight:500">what happened: <span class="${tone(R.actual[hz])}">${sp(R.actual[hz])}</span></span>` : ''}</td></tr>`;
      for (const k of ['sim', 'ext', 'all']) {
        const S = g[k];
        if (!S) { h += `<tr><td>${label[k]}</td><td colspan="9" class="mv-sub">none</td></tr>`; continue; }
        h += `<tr><td>${label[k]}</td><td class="n ${tone(S.median)}">${sp(S.median)}</td><td class="n">${share(S.up)}</td><td class="box">${boxSvg(S, lo, hi, col[k], R.actual[hz])}</td><td class="n">${sp(S.mean)}</td>`
          + `<td class="n">${sp(S.q[0])}</td><td class="n">${sp(S.q[6])}</td><td class="n">${num(S.n)}${S.neff ? ` <span class="mv-sub" style="display:inline">≈${num(S.neff)}</span>` : ''}</td><td class="n">${k === 'all' ? '—' : num(S.ep)}</td><td>${k === 'all' ? '' : verdict(S, g.all)}</td></tr>`;
      }
    }
    return h + '</tbody></table></div>';
  }
  function recentTable(R, o, which) {
    const mask = R[which], A = R.A, c = cum(A.r), N = A.days.length - 1, rows = [];
    for (let j = N; j >= 0 && rows.length < 12; j--) if (mask[j]) rows.push(j);
    if (!rows.length) return '<p class="mv-sub">No such days.</p>';
    const end = o.before && o.mode === 'date' && R.t >= 0 ? R.t : N;      // only what was known on the day, when asked
    const fwd = (j, h) => (j + h <= end ? Math.expm1(c[j + h] - c[j]) : null);
    return `<div class="mv-wrap"><table class="mv-tbl"><thead><tr><th>Day</th><th class="n">Move</th><th class="n">Percentile</th><th class="n">Next day</th><th class="n">Next week</th><th class="n">Next month</th></tr></thead><tbody>${rows.map((j) => {
      const nd = fwd(j, 1), nw = fwd(j, 5), nm = fwd(j, 21);
      return `<tr><td>${esc(mdy(A.days[j]))}</td><td class="n ${tone(R.x[j])}">${esc(fmtX(o, R.x[j]))}</td><td class="n">${num(R.p && Number.isFinite(R.p[j]) ? R.p[j] : pctOf(R.s, R.x[j]), 1)}</td><td class="n ${tone(nd)}">${sp(nd)}</td><td class="n ${tone(nw)}">${sp(nw)}</td><td class="n ${tone(nm)}">${sp(nm)}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }
  function controls(st, doc) {
    const pill = (k, v, l, on, dis) => `<button type="button" class="mv-pill${on ? ' on' : ''}" data-mv="${k}" data-v="${esc(v)}"${dis ? ' disabled' : ''}>${esc(l)}</button>`;
    const volIdx = doc.kind === 'volatility', beta = !volIdx && doc.key !== 'SPY' && doc.kind !== 'index' && doc.kind !== 'market';
    const lv = st.measure === 'level' || st.measure === 'rv';
    const measures = volIdx ? pill('measure', 'level', 'its level', st.measure === 'level') + pill('measure', 'raw', '% change', st.measure === 'raw')
      : pill('measure', 'raw', '% change', st.measure === 'raw') + pill('measure', 'vol', 'vs own volatility (σ)', st.measure === 'vol')
        + (beta ? pill('measure', 'beta', 'beyond the market', st.measure === 'beta') : '') + pill('measure', 'rv', 'its volatility (1 month)', st.measure === 'rv');
    const unitIn = st.measure === 'vol' ? 'σ' : st.measure === 'level' ? 'level' : st.measure === 'rv' ? '% a year' : '%';
    const eg = st.measure === 'vol' ? 'e.g. -3' : st.measure === 'level' ? 'e.g. 30' : st.measure === 'rv' ? 'e.g. 60' : 'e.g. -5';
    return `<div class="mv-bar"><div><label>Move</label><div class="mv-pills">${WIN.map(([w, l]) => pill('w', w, l, st.w === w && !lv, lv)).join('')}</div></div>`
      + `<div><label>Measured as</label><div class="mv-pills">${measures}</div></div>`
      + `<div><label>Days like it: within <b data-mvbl style="color:var(--ink,#222)">±${esc(fb(st.band))}</b> pts</label><div class="mv-pills">${BANDS.map((b) => pill('band', b, '±' + fb(b), Math.abs(st.band - b) < 1e-9)).join('')}`
      + `<input class="mv-range" type="range" min="0.1" max="10" step="0.1" value="${esc(st.band)}" data-mvband aria-label="Days like it: within this many percentile points"></div></div>`
      + (volIdx ? `<div><label>Then</label><div class="mv-pills">${pill('outcome', 'spx', 'the S&P 500', st.outcome !== 'self')}${pill('outcome', 'self', 'the index itself', st.outcome === 'self')}</div></div>`
        : `<div><label>Volatility then</label><div class="mv-pills">${pill('vreg', 'any', 'any', st.vreg !== 'similar')}${pill('vreg', 'similar', 'similar (±15 pts)', st.vreg === 'similar')}</div></div>`) + '</div>'
      + `<div class="mv-bar"><div><label>Look at</label><div class="mv-pills">${pill('mode', 'latest', lv ? 'the latest' : 'the latest move', st.mode === 'latest')}${pill('mode', 'date', 'a past day', st.mode === 'date')}${pill('mode', 'whatif', 'what if…', st.mode === 'whatif')}</div></div>`
      + `<div><label>Older days count</label><div class="mv-pills">${HLS.map(([v, l]) => pill('hl', v, l, (+st.hl || 0) === v)).join('')}</div></div>`
      + (st.mode === 'date' ? `<div><label>Day</label><input class="mv-in" type="date" data-mvin="date" value="${esc(st.date || '')}" min="${esc(doc.d0)}" max="${esc(doc.as_of)}"></div><div><label>History used</label><div class="mv-pills">${pill('before', '0', 'all days', !st.before)}${pill('before', '1', 'only before that day', st.before)}</div></div>` : '')
      + (st.mode === 'whatif' ? `<div><label>${lv ? 'Level' : 'Move'} (${unitIn})</label><input class="mv-in" type="number" step="0.1" data-mvin="whatif" value="${esc(st.whatif)}" placeholder="${eg}"></div>` : '')
      + '</div>';
  }

  /* ---------- each day like it: the path after it, and what the company filed ---------- */
  // the cases: every chosen day (a move longer than a day counts once: chosen days within its length of the one before
  // belong to it), with the path of simple returns from its close over the next PATH_D trading days (as far as known)
  // what followed day j: the simple returns over the next H trading days (as far as day `end` of the asset's own) of the
  // asset, or of the asset it is judged by (a volatility index: the S&P 500)
  function pathFrom(R, j, H, end) {
    const p = [];
    if (R.oc) {
      const q = R.oq[j];
      if (q >= 0) for (let h = 0; h <= H && j + h <= end && q + h < R.oc.length; h++) p.push(Math.expm1(R.oc[q + h] - R.oc[q]));
      return p;
    }
    const c = R.c || (R.c = cum(R.A.r));
    for (let h = 0; h <= H && j + h <= end; h++) p.push(Math.expm1(c[j + h] - c[j]));
    return p;
  }
  function cases(R, o, which) {
    const mask = R[which], N = R.A.days.length - 1, w = o.w || 1;
    const end = o.before && o.mode === 'date' && R.t >= 0 ? R.t : N;
    const out = [];
    let last = -Infinity;
    for (let j = 0; j <= N; j++) {
      if (!mask[j]) continue;
      const join = j - last < w;
      last = j;
      if (join) continue;
      const path = pathFrom(R, j, PATH_D, end);
      if (path.length) out.push({ j, path });
    }
    return out;
  }
  // the expected path (the mean of the cases' returns at each day after), the median and the middle half; with weights
  // (one per case: older days counting less), each weighted
  function expectedOf(cs, wts) {
    const mean = [], med = [], q25 = [], q75 = [], n = [];
    for (let h = 0; h <= PATH_D; h++) {
      if (wts) {
        const ids = []; cs.forEach((x, i) => { if (Number.isFinite(x.path[h])) ids.push(i); });
        if (ids.length < 2) break;
        ids.sort((a, b) => cs[a].path[h] - cs[b].path[h]);
        const v = Float64Array.from(ids, (i) => cs[i].path[h]), u = Float64Array.from(ids, (i) => wts[i]), Q = wquant(v, u);
        let W = 0, m1 = 0; for (let k = 0; k < v.length; k++) { W += u[k]; m1 += u[k] * v[k]; }
        n.push(v.length); mean.push(m1 / W); med.push(Q(50)); q25.push(Q(25)); q75.push(Q(75));
        continue;
      }
      const v = Float64Array.from(cs.map((x) => x.path[h]).filter(Number.isFinite)).sort();
      if (v.length < 2) break;
      n.push(v.length); mean.push(v.reduce((a, b) => a + b, 0) / v.length); med.push(quantile(v, 50)); q25.push(quantile(v, 25)); q75.push(quantile(v, 75));
    }
    return { mean, med, q25, q75, n };
  }
  const caseW = (R, cs) => (R.wt ? cs.map((x) => R.wt[x.j]) : null);
  const upShare = (cs, cw, h) => { let a = 0, b = 0; cs.forEach((x, i) => { const v = x.path[Math.min(h, x.path.length - 1)], u = cw ? cw[i] : 1; if (fin(v)) { b += u; if (v > 0) a += u; } }); return a / Math.max(b, 1e-12); };
  // the path of the day looked at, as far as it is known
  function nowPath(R) {
    if (R.t < 0) return null;
    const p = pathFrom(R, R.t, PATH_D, R.A.days.length - 1);
    return p.length > 1 ? p : null;
  }
  const px = (h) => Math.sqrt(h / PATH_D);                                   // the days after on a square-root scale
  function pathsSvg(R, o, cs, E) {
    const W = o.narrow ? 440 : 760, Hh = o.narrow ? 300 : 340, L = 48, Rr = o.narrow ? 54 : 70, T = 18, B = 34;
    const pts = [];
    cs.forEach((x) => x.path.forEach((v) => pts.push(v)));
    const now = nowPath(R);
    if (!pts.length) return '<p class="mv-sub">No days to draw.</p>';
    const sv = Float64Array.from(pts).sort();
    let lo = Math.min(quantile(sv, 1.5), 0, ...E.mean), hi = Math.max(quantile(sv, 98.5), 0, ...E.mean);
    if (now) { lo = Math.min(lo, ...now); hi = Math.max(hi, ...now); }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const sx = (h) => L + px(h) * (W - L - Rr), sy = (v) => T + (hi - v) / (hi - lo) * (Hh - T - B);
    const line = (p) => p.map((v, h) => `${h ? 'L' : 'M'}${sx(h).toFixed(1)},${sy(v).toFixed(1)}`).join('');
    const clip = 'mvc' + Math.random().toString(36).slice(2, 8);       // lines beyond the axis are cut at its edge, not flattened
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="The path after each day like it (dashed), and the expected path"><defs><clipPath id="${clip}"><rect x="${L}" y="${T}" width="${W - L - Rr + 2}" height="${Hh - T - B}"/></clipPath></defs>`;
    ticks(lo * 100, hi * 100, 6).forEach((v) => { g += `<line class="mv-g" x1="${L}" x2="${W - Rr}" y1="${sy(v / 100)}" y2="${sy(v / 100)}"/><text class="mv-t" x="${L - 6}" y="${sy(v / 100) + 4}" text-anchor="end">${esc(sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0))}</text>`; });
    g += `<line x1="${L}" x2="${W - Rr}" y1="${sy(0)}" y2="${sy(0)}" style="stroke:${COL.mute};stroke-width:1"/>`;
    PATH_MARKS.forEach(([h, l]) => { g += `<line class="mv-g" x1="${sx(h)}" x2="${sx(h)}" y1="${T}" y2="${Hh - B}" style="stroke-dasharray:2 3"/><text class="mv-t" x="${sx(h)}" y="${Hh - B + 16}" text-anchor="middle">${esc(o.narrow && h === 10 ? '2w' : l)}</text>`; });
    // the middle half of the cases, then each case dashed, the median dotted, the expected path, the day looked at
    g += `<g clip-path="url(#${clip})">`;
    if (E.mean.length > 1) {
      const up = E.q75.map((v, h) => `${h ? 'L' : 'M'}${sx(h).toFixed(1)},${sy(v).toFixed(1)}`).join(''), dn = E.q25.map((v, h) => `L${sx(h).toFixed(1)},${sy(v).toFixed(1)}`).reverse().join('');
      g += `<path d="${up}${dn}Z" style="fill:${COL.band};opacity:.10"/>`;
    }
    const op = Math.max(0.12, Math.min(0.75, 2.6 / Math.sqrt(cs.length)));
    cs.forEach((x) => {
      if (x.path.length < 2) return;
      const f = x.path[x.path.length - 1];
      g += `<path d="${line(x.path)}" style="fill:none;stroke:${f >= 0 ? COL.up : COL.down};stroke-width:1.1;stroke-dasharray:4 3;opacity:${(op * (R.wt ? 0.15 + 0.85 * R.wt[x.j] : 1)).toFixed(2)}"><title>${esc(mdy(R.A.days[x.j]))}: ${esc(fmtX(o, R.x[x.j]))} · then ${PATH_MARKS.filter(([h]) => h < x.path.length).map(([h, l]) => `${l} ${sp(x.path[h])}`).join(', ')}</title></path>`;
    });
    if (E.med.length > 1) g += `<path d="${line(E.med)}" style="fill:none;stroke:${COL.ink};stroke-width:1.4;stroke-dasharray:1.5 3;opacity:.8"/>`;
    if (E.mean.length > 1) g += `<path d="${line(E.mean)}" style="fill:none;stroke:${COL.band};stroke-width:3"/>`;
    if (now) g += `<path d="${line(now)}" style="fill:none;stroke:${COL.warn};stroke-width:2.4"/>`;
    g += '</g>';
    PATH_MARKS.forEach(([h]) => {
      if (h >= E.mean.length) return;
      const v = E.mean[h], y = sy(v);
      g += `<circle cx="${sx(h)}" cy="${y}" r="3.6" style="fill:${COL.band};stroke:#fff;stroke-width:1.2"/>`;
      if (h === PATH_D || h === E.mean.length - 1 || !o.narrow) g += `<text class="mv-l" x="${sx(h) + (h === PATH_D ? 7 : 0)}" y="${y - 8}" text-anchor="${h === PATH_D ? 'start' : 'middle'}" style="font-weight:650;fill:${COL.band}">${esc(sp(v))}</text>`;
    });
    g += `<text class="mv-t" x="${L}" y="${Hh - 4}">trading days after the day (square-root scale) · ${esc(num(cs.length))} case${cs.length === 1 ? '' : 's'}</text>`;
    return g + '</svg>';
  }
  // the filings that could move a day: filed that day before the close (16:00 New York time), or after the close of the
  // trading day before (and over a weekend or holiday)
  const ITEM_WORD = { '1.01': 'material agreement', '1.02': 'agreement ended', '1.03': 'bankruptcy', '1.05': 'cybersecurity incident', '2.01': 'acquisition or sale completed',
    '2.02': 'earnings', '2.03': 'new debt', '2.05': 'restructuring', '2.06': 'impairment', '3.01': 'listing notice', '3.02': 'unregistered share sale',
    '4.01': 'auditor change', '4.02': 'restatement', '5.01': 'change in control', '5.02': 'executive or board change', '5.03': 'bylaws or fiscal year',
    '5.07': 'shareholder vote', '7.01': 'Reg FD disclosure', '8.01': 'other events' };
  const FORM_WORD = (f) => (/^10-Q/.test(f) ? 'quarterly report (10-Q)' : /^10-K/.test(f) ? 'annual report (10-K)' : /^(20|40)-F/.test(f) ? 'annual report (' + f + ')'
    : /^424B|^S-|^F-[134]/.test(f) ? 'offering prospectus (' + f + ')' : /13D/.test(f) ? 'a 5%+ stake (Schedule 13D)' : /^SC TO/.test(f) ? 'tender offer'
      : /14D9/.test(f) ? 'response to a tender offer' : /M14A/.test(f) ? 'merger proxy' : /^25-NSE/.test(f) ? 'a listed security removed (Form 25)' : /^15-12B/.test(f) ? 'registration ended (Form 15)' : /^NT 10/.test(f) ? 'late filing notice' : /^6-K/.test(f) ? 'foreign issuer report (6-K)' : f);
  const HOT = new Set(['2.02', '1.05', '2.05', '2.06', '4.02', '3.01', '1.03', '5.01']);
  function newsIndex(news, days) {
    const by = new Map();
    if (!news || !news.events) return by;
    for (const e of news.events) {
      const [d, hm] = e;
      let k = lower(days, d);
      if (k < days.length && days[k] === d && hm && hm >= '16:00') k++;
      if (k >= days.length) continue;
      if (!by.has(k)) by.set(k, []);
      by.get(k).push(e);
    }
    return by;
  }
  function newsCell(list, cik) {
    if (!list || !list.length) return '';
    return list.slice(0, 4).map(([d, hm, form, items, head, q, topics, acc, g]) => {
      const its = String(items || '').split(',').filter((x) => x && x !== '9.01');
      const chips = (form.startsWith('8-K') ? its.map((x) => `<span class="mv-chip${HOT.has(x) ? ' hot' : ''}">${esc(ITEM_WORD[x] || 'Item ' + x)}</span>`) : [`<span class="mv-chip">${esc(FORM_WORD(form))}</span>`])
        .concat((topics || []).filter((t) => t !== 'earnings' && !(g && t === 'guidance')).map((t) => `<span class="mv-chip hot">${esc(String(t).replace(/_/g, ' '))}</span>`))
        .concat(g ? [`<span class="mv-chip hot">guidance ${esc(g)}</span>`] : []).join('');
      const url = cik && acc ? `https://www.sec.gov/Archives/edgar/data/${+cik}/${String(acc).replace(/-/g, '')}/` : '';
      const when = `${mdy(d)}${hm ? ' ' + hm + ' ET' : ''}`;
      return `<p class="mv-news">${chips}${head ? `<a href="${esc(url)}" target="_blank" rel="noopener"><b>${esc(head)}</b></a>` : url ? `<a href="${esc(url)}" target="_blank" rel="noopener">the filing ↗</a>` : ''}`
        + ` <span class="mv-sub" style="display:inline">${esc(when)}</span>${q ? `<span class="q">${esc(q)}</span>` : ''}</p>`;
    }).join('') + (list.length > 4 ? `<span class="mv-sub">+${list.length - 4} more filings</span>` : '');
  }
  function casesTable(R, o, cs, news, doc) {
    const by = newsIndex(news, R.A.days), cols = PATH_MARKS;
    const rows = cs.slice().sort((a, b) => b.j - a.j);
    const hasNews = doc.kind === 'stock';
    let h = `<div class="mv-cases"><table class="mv-tbl"><thead><tr><th>Day</th><th class="n">Move</th><th class="n">Pct</th>${cols.map(([, l]) => `<th class="n">${esc(l)}</th>`).join('')}${hasNews ? '<th>What the company filed (that day, or after the close before it)</th>' : ''}</tr></thead><tbody>`;
    const nowRow = R.t >= 0 && o.mode !== 'whatif' ? { j: R.t, path: nowPath(R) || [0] } : null;
    for (const x of (nowRow ? [nowRow] : []).concat(rows)) {
      const isNow = nowRow && x === nowRow;
      h += `<tr${isNow ? ' class="now"' : ''}><td>${esc(mdy(R.A.days[x.j]))}${isNow ? ' <span class="mv-chip hot">this day</span>' : ''}</td><td class="n ${tone(R.x[x.j])}">${esc(fmtX(o, R.x[x.j]))}</td><td class="n">${num(R.p && Number.isFinite(R.p[x.j]) ? R.p[x.j] : pctOf(R.s, R.x[x.j]), 1)}</td>`
        + cols.map(([hz]) => { const v = x.path[hz]; return `<td class="n ${tone(v)}">${fin(v) ? sp(v) : '—'}</td>`; }).join('')
        + (hasNews ? `<td class="news">${newsCell(by.get(x.j), doc.cik) || `<span class="mv-sub">${news ? 'no filing that day' : '…'}</span>`}</td>` : '') + '</tr>';
    }
    return h + '</tbody></table></div>';
  }
  function casesSection(R, o, doc, news) {
    const which = o.set === 'ext' ? 'ext' : 'sim';
    const cs = cases(R, o, which), cw = caseW(R, cs), E = expectedOf(cs, cw);
    const lab = which === 'sim' ? `day${cs.length === 1 ? '' : 's'} like it (within ±${fb(o.band)} percentile points)` : `day${cs.length === 1 ? '' : 's'} at least as ${R.side > 0 ? 'high' : 'low'}`;
    const many = cs.length === 1 ? 'The one' : `Each of the ${num(cs.length)}`;
    let h = `<h3>Each day like it, and the path after it</h3>`;
    h += `<p class="mv-sub">${many} ${esc(lab)}${o.w > 1 ? ' (overlapping days of one move counted once)' : ''} is a dashed line (green when it ended up, red when down), from its close over the next day, week, two weeks, month and quarter; the thick blue line is the expected path (the average of the cases at each day after), the dotted one the median, the shaded band the middle half${R.t >= 0 && o.mode !== 'whatif' ? `; orange: what followed ${esc(mdy(R.A.days[R.t]))}` : ''}. Move the slider above to take a narrower or wider band of days.</p>`;
    if (E.mean.length > 1) {
      h += `<p class="mv-head" style="font-size:15.5px">Expected after a day like it: ${PATH_MARKS.filter(([hz]) => hz < E.mean.length).map(([hz, l]) => `${esc(l)} <b class="${tone(E.mean[hz])}">${sp(E.mean[hz])}</b>`).join(' · ')}`
        + ` <span class="mv-sub" style="display:inline">(${share(upShare(cs, cw, 21))} up after a month${R.hl ? ', older days counting less' : ''})</span></p>`;
    }
    h += pathsSvg(R, o, cs, E);
    h += `<div class="mv-legend"><span><b style="background:none;border-top:2px dashed ${COL.up};height:0;width:14px;border-radius:0"></b><b style="background:none;border-top:2px dashed ${COL.down};height:0;width:14px;border-radius:0"></b>each case</span><span><b style="background:${COL.band}"></b>expected (average)</span><span><b style="background:none;border-top:2px dotted ${COL.ink};height:0;width:14px;border-radius:0"></b>median</span><span><b style="background:${COL.band};opacity:.25"></b>middle half</span>${R.t >= 0 && o.mode !== 'whatif' ? `<span><b style="background:${COL.warn}"></b>this day</span>` : ''}</div>`;
    h += `<p class="mv-sub">${doc.kind === 'stock' ? 'Each case with what the company filed with the SEC that could have moved it: 8-K items (the press release\'s headline and key sentences, read for the days of its biggest moves), quarterly and annual reports, offerings and stakes. Filings are read a batch at a time, the largest companies and most extreme days first; a day may show its filing before its headline.' : 'Company filings are shown for a company: switch to “this company” above.'}</p>`;
    return h + casesTable(R, o, cs, news, doc);
  }

  /* ---------- similar stretches: the past stretches most like the last weeks, what followed, a simulation ---------- */
  const ALEN = [[21, '1 month'], [63, '3 months'], [126, '6 months'], [252, '1 year']];
  const AKS = [5, 10, 20, 30];
  const AMARKS = [[5, '1 week'], [21, '1 month'], [63, '3 months'], [126, '6 months'], [252, '1 year']];
  const SIMS = 2000, BLOCK = 5;                                     // simulated paths; trading days drawn together
  const words = (n, one) => `${num(n)} ${one}${n === 1 ? '' : 's'}`;
  const tdWords = (d) => (ALEN.find(([v]) => v === d) || [d, `${d} trading days`])[1];
  // the K stretches of L trading days most like the L days up to the day looked at (t), each ending at least F + L
  // days before t — what followed it is known and shares no day with the stretch looked at — and no two overlapping.
  // match 'size': the root mean square gap between the two paths of log closes from their first day (the size and the
  // shape of the moves); 'shape': between the two paths each less its mean over its spread (the shape alone). Each with
  // its path from L days before to F days after, in log closes from its last day; weights: older days counting less.
  function analogs(R, o) {
    const A = R.A, c = R.c || (R.c = cum(A.r)), N = A.days.length - 1, t = R.t >= 0 ? R.t : N;
    const L = +o.alen || 63, F = +o.afwd || 63, K = +o.ak || 10, shape = o.amatch === 'shape', n1 = L + 1, last = t - L - F;
    const base = { L, F, K, shape, t };
    if (last < L) return Object.assign(base, { error: `Not enough history before ${mdy(A.days[t])} for stretches of ${tdWords(L)} and the ${tdWords(F)} after them.` });
    const S1 = new Float64Array(N + 2), S2 = new Float64Array(N + 2);   // running sums of c and c², for each stretch's mean and spread
    for (let i = 0; i <= N; i++) { S1[i + 1] = S1[i] + c[i]; S2[i + 1] = S2[i] + c[i] * c[i]; }
    const ms = (j) => { const s1 = S1[j + 1] - S1[j - L], m = s1 / n1; return [m, Math.sqrt(Math.max((S2[j + 1] - S2[j - L]) / n1 - m * m, 0)) || 1]; };
    const q = new Float64Array(n1);
    if (shape) { const [m, sd] = ms(t); for (let k = 0; k < n1; k++) q[k] = (c[t - L + k] - m) / sd; } else for (let k = 0; k < n1; k++) q[k] = c[t - L + k] - c[t - L];
    const D = new Float64Array(last + 1).fill(Infinity);
    for (let j = L; j <= last; j++) {
      const b = j - L; let ss = 0;
      if (shape) { const [m, sd] = ms(j); for (let k = 0; k < n1; k++) { const d = (c[b + k] - m) / sd - q[k]; ss += d * d; } }
      else { const c0 = c[b]; for (let k = 0; k < n1; k++) { const d = c[b + k] - c0 - q[k]; ss += d * d; } }
      D[j] = Math.sqrt(ss / n1);
    }
    const order = []; for (let j = L; j <= last; j++) order.push(j);
    order.sort((a, b) => D[a] - D[b]);
    const pick = [];
    for (const j of order) { if (pick.length >= K) break; if (pick.every((i) => Math.abs(i - j) >= L)) pick.push(j); }
    const corr = (j) => {                                          // how alike the two shapes are, −1 to 1
      let sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
      for (let k = 0; k < n1; k++) { const a = c[j - L + k], b = c[t - L + k]; sa += a; sb += b; saa += a * a; sbb += b * b; sab += a * b; }
      const va = saa - sa * sa / n1, vb = sbb - sb * sb / n1;
      return va > 0 && vb > 0 ? (sab - sa * sb / n1) / Math.sqrt(va * vb) : 0;
    };
    const items = pick.map((j) => {
      const back = Float64Array.from({ length: n1 }, (_, k) => c[j - L + k] - c[j]), fwd = Float64Array.from({ length: F + 1 }, (_, h) => c[j + h] - c[j]);
      let lo = 0, hi = 0; for (const v of fwd) { if (v < lo) lo = v; if (v > hi) hi = v; }
      return { j, d: D[j], corr: corr(j), move: Math.expm1(c[j] - c[j - L]), back, fwd, worst: Math.expm1(lo), best: Math.expm1(hi), w: R.wt ? R.wt[j] : 1 };
    });
    const now = Float64Array.from({ length: n1 }, (_, k) => c[t - L + k] - c[t]);
    const actual = [];                                               // what followed the day looked at, when known
    if (R.t >= 0) for (let h = 0; h <= F && t + h <= N; h++) actual.push(c[t + h] - c[t]);
    // what to expect: at each day after, the analogs' weighted average, median and middle half (simple returns)
    const E = { mean: [], med: [], q25: [], q75: [], q10: [], q90: [] }, W = items.reduce((a, x) => a + x.w, 0);
    for (let h = 0; h <= F && items.length; h++) {
      const ids = items.map((_, i) => i).sort((a, b) => items[a].fwd[h] - items[b].fwd[h]);
      const v = Float64Array.from(ids, (i) => Math.expm1(items[i].fwd[h])), u = Float64Array.from(ids, (i) => items[i].w), Q = wquant(v, u);
      let m1 = 0; for (let k = 0; k < v.length; k++) m1 += u[k] * v[k];
      E.mean.push(m1 / W); E.med.push(Q(50)); E.q25.push(Q(25)); E.q75.push(Q(75)); E.q10.push(Q(10)); E.q90.push(Q(90));
    }
    const upF = items.reduce((a, x) => a + (x.fwd[F] > 0 ? x.w : 0), 0) / (W || 1);
    // every day before the stretch looked at, for comparison: the returns over each mark ahead (weighted, when older days count less)
    const every = {};
    for (const [h] of AMARKS.concat([[F, '']])) {
      if (h > F || every[h]) continue;
      const ids = []; for (let j = 0; j + h <= t; j++) ids.push(j);
      if (ids.length < 30) continue;
      ids.sort((a, b) => (c[a + h] - c[a]) - (c[b + h] - c[b]));
      const v = Float64Array.from(ids, (j) => Math.expm1(c[j + h] - c[j])), u = R.wt ? Float64Array.from(ids, (j) => R.wt[j]) : new Float64Array(ids.length).fill(1), Q = wquant(v, u);
      let a = 0, b = 0, up = 0; for (let k = 0; k < v.length; k++) { a += u[k] * v[k]; b += u[k]; if (v[k] > 0) up += u[k]; }
      every[h] = { mean: a / b, med: Q(50), q5: Q(5), q95: Q(95), up: up / b };
    }
    return Object.assign(base, { items, now, actual, E, upF, every, W, n: last - L + 1, from: A.days[0] });
  }
  // a seeded random number (the same picture on every visit), and a string's seed
  function rng32(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let x = Math.imul(a ^ (a >>> 15), 1 | a); x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x; return ((x ^ (x >>> 14)) >>> 0) / 4294967296; }; }
  const seedOf = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };
  // the simulation: M paths over the F days ahead, each built a week (BLOCK trading days in a row) at a time, every week
  // drawn at random from the days after the stretches like it — a stretch by weight, then any week of the F days after
  // it — so a few odd weeks spread over every day ahead instead of all falling on the day they came. The bands of the
  // paths at each day (5, 25, 50, 75, 95%), the end, the chance of ending higher and of touching −10% / +10% on the way.
  function simulate(AN, M, seed) {
    const it = AN.items, F = AN.F;
    if (!it || !it.length) return null;
    const rnd = rng32(seed), cw = []; let acc = 0;
    for (const x of it) { acc += x.w; cw.push(acc); }
    const pickI = () => { const u = rnd() * acc; let lo = 0, hi = cw.length - 1; while (lo < hi) { const m = (lo + hi) >> 1; if (cw[m] < u) lo = m + 1; else hi = m; } return lo; };
    const P = new Float32Array(M * (F + 1)), mins = new Float64Array(M), maxs = new Float64Array(M);
    for (let m = 0; m < M; m++) {
      let lv = 0, mn = 0, mx = 0;
      for (let h = 0; h < F; h += BLOCK) {
        const f = it[pickI()].fwd, b = Math.min(BLOCK, F - h), s0 = Math.floor(rnd() * (F - b + 1));   // a week of its days after
        for (let d = 0; d < b; d++) { lv += f[s0 + d + 1] - f[s0 + d]; P[m * (F + 1) + h + d + 1] = lv; if (lv < mn) mn = lv; if (lv > mx) mx = lv; }
      }
      mins[m] = mn; maxs[m] = mx;
    }
    const band = { q5: [], q25: [], q50: [], q75: [], q95: [] }, col = new Float64Array(M);
    for (let d = 0; d <= F; d++) {
      for (let m = 0; m < M; m++) col[m] = P[m * (F + 1) + d];
      col.sort();
      band.q5.push(Math.expm1(quantile(col, 5))); band.q25.push(Math.expm1(quantile(col, 25))); band.q50.push(Math.expm1(quantile(col, 50)));
      band.q75.push(Math.expm1(quantile(col, 75))); band.q95.push(Math.expm1(quantile(col, 95)));
    }
    let up = 0, d10 = 0, u10 = 0, mean = 0;
    for (let m = 0; m < M; m++) {
      const e = P[m * (F + 1) + F]; if (e > 0) up++; mean += Math.expm1(e);
      if (mins[m] <= Math.log(0.9)) d10++; if (maxs[m] >= Math.log(1.1)) u10++;
    }
    const samples = [];
    for (let m = 0; m < Math.min(M, 40); m++) samples.push(Array.from({ length: F + 1 }, (_, d) => Math.expm1(P[m * (F + 1) + d])));
    return { M, F, band, up: up / M, down10: d10 / M, up10: u10 / M, mean: mean / M, samples };
  }
  const aMarks = (F) => AMARKS.filter(([h]) => h <= F);
  const spanWords = (d) => (AMARKS.find(([v]) => v === d) || ALEN.find(([v]) => v === d) || [d, `${d} trading days`])[1];
  const dayX = (h) => (h === 0 ? 'today' : `${h < 0 ? '−' : '+'}${spanWords(Math.abs(h))}`);
  // axis labels [x, text, anchor, keep first] with none closer than `gap` pixels to one already placed
  function spaced(labels, gap) {
    const out = [];
    for (const lb of labels.slice().sort((a, b) => (b[3] ? 1 : 0) - (a[3] ? 1 : 0))) if (out.every((o) => Math.abs(o[0] - lb[0]) >= gap)) out.push(lb);
    return out;
  }
  // the stretches drawn: each analog's path into its last day and on after it, the expected path, the middle half,
  // every day's range for comparison, the stretch looked at and what followed it
  function analogSvg(R, o, AN) {
    const W = o.narrow ? 440 : 760, Hh = o.narrow ? 300 : 340, Lm = 48, Rr = o.narrow ? 54 : 74, T = 18, B = 34, L = AN.L, F = AN.F, E = AN.E;
    const ex = (v) => Math.expm1(v), pts = [];
    AN.items.forEach((x) => { x.back.forEach((v) => pts.push(ex(v))); x.fwd.forEach((v) => pts.push(ex(v))); });
    AN.now.forEach((v) => pts.push(ex(v))); AN.actual.forEach((v) => pts.push(ex(v)));
    const sv = Float64Array.from(pts).sort();
    let lo = Math.min(quantile(sv, 1), 0, ...E.q25), hi = Math.max(quantile(sv, 99), 0, ...E.q75);
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const sx = (h) => Lm + (h + L) / (L + F) * (W - Lm - Rr), sy = (v) => T + (hi - Math.min(hi, Math.max(lo, v))) / (hi - lo) * (Hh - T - B);
    const line = (arr, off) => Array.from(arr, (v, k) => `${k ? 'L' : 'M'}${sx(k + off).toFixed(1)},${sy(ex(v)).toFixed(1)}`).join('');
    const lineS = (arr) => arr.map((v, h) => `${h ? 'L' : 'M'}${sx(h).toFixed(1)},${sy(v).toFixed(1)}`).join('');
    const clip = 'mva' + Math.random().toString(36).slice(2, 8);
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="The stretches most like the one looked at, and what followed them"><defs><clipPath id="${clip}"><rect x="${Lm}" y="${T}" width="${W - Lm - Rr + 2}" height="${Hh - T - B}"/></clipPath></defs>`;
    ticks(lo * 100, hi * 100, 6).forEach((v) => { g += `<line class="mv-g" x1="${Lm}" x2="${W - Rr}" y1="${sy(v / 100)}" y2="${sy(v / 100)}"/><text class="mv-t" x="${Lm - 6}" y="${sy(v / 100) + 4}" text-anchor="end">${esc(sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0))}</text>`; });
    g += `<line x1="${Lm}" x2="${W - Rr}" y1="${sy(0)}" y2="${sy(0)}" style="stroke:${COL.mute};stroke-width:1"/><line x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${Hh - B}" style="stroke:${COL.ink};stroke-width:1;stroke-dasharray:3 3"/>`;
    spaced([[sx(-L), dayX(-L), 'start', 1], [sx(0), R.t >= 0 ? mdy(R.A.days[AN.t]) : 'today', 'middle', 1], [sx(F), dayX(F), 'end', 1], ...aMarks(F).filter(([h]) => h < F).map(([h]) => [sx(h), dayX(h), 'middle'])], o.narrow ? 70 : 84)
      .forEach(([x, l, an]) => { g += `<text class="mv-t" x="${x}" y="${Hh - B + 16}" text-anchor="${an}">${esc(l)}</text>`; });
    g += `<g clip-path="url(#${clip})">`;
    const evs = aMarks(F).map(([h]) => h).filter((h) => AN.every[h]);
    if (evs.length) g += `<path d="M${sx(0)},${sy(0)}${evs.map((h) => `L${sx(h).toFixed(1)},${sy(AN.every[h].q95).toFixed(1)}`).join('')}${evs.slice().reverse().map((h) => `L${sx(h).toFixed(1)},${sy(AN.every[h].q5).toFixed(1)}`).join('')}Z" style="fill:${COL.all};opacity:.10"/>`;
    if (E.mean.length > 1) g += `<path d="${lineS(E.q75)}${E.q25.map((v, h) => `L${sx(h).toFixed(1)},${sy(v).toFixed(1)}`).reverse().join('')}Z" style="fill:${COL.band};opacity:.12"/>`;
    const op = Math.max(0.2, Math.min(0.8, 2.4 / Math.sqrt(AN.items.length)));
    AN.items.forEach((x, i) => {
      const f = x.fwd[F], col = f >= 0 ? COL.up : COL.down, fade = R.wt ? 0.15 + 0.85 * x.w : 1;
      g += `<path d="${line(x.back, -L)}" style="fill:none;stroke:${COL.all};stroke-width:1;opacity:${(op * 0.8 * fade).toFixed(2)}"/>`
        + `<path d="${line(x.fwd, 0)}" style="fill:none;stroke:${col};stroke-width:1.2;opacity:${(op * fade).toFixed(2)}"><title>${i + 1}. ${esc(mdy(R.A.days[x.j - L]))} – ${esc(mdy(R.A.days[x.j]))}: ${esc(sp(x.move))}, then ${esc(sp(Math.expm1(f)))}</title></path>`;
    });
    if (E.med.length > 1) g += `<path d="${lineS(E.med)}" style="fill:none;stroke:${COL.ink};stroke-width:1.4;stroke-dasharray:1.5 3;opacity:.8"/>`;
    if (E.mean.length > 1) g += `<path d="${lineS(E.mean)}" style="fill:none;stroke:${COL.band};stroke-width:3"/>`;
    g += `<path d="${line(AN.now, -L)}" style="fill:none;stroke:${COL.ink};stroke-width:2.4"/>`;
    if (AN.actual.length > 1) g += `<path d="${line(AN.actual, 0)}" style="fill:none;stroke:${COL.warn};stroke-width:2.4"/>`;
    g += '</g>';
    const shown = spaced(aMarks(F).filter(([h]) => h < E.mean.length).map(([h]) => [sx(h), h, '', h === F]).concat([[sx(0), -1, '', true]]), o.narrow ? 64 : 56).map((v) => v[1]);
    aMarks(F).forEach(([h]) => {
      if (h >= E.mean.length) return;
      const y = sy(E.mean[h]);
      g += `<circle cx="${sx(h)}" cy="${y}" r="3.6" style="fill:${COL.band};stroke:#fff;stroke-width:1.2"/>`;
      if (shown.includes(h)) g += `<text class="mv-l" x="${sx(h) + (h === F ? 7 : 0)}" y="${y - 8}" text-anchor="${h === F ? 'start' : 'middle'}" style="font-weight:650;fill:${COL.band}">${esc(sp(E.mean[h]))}</text>`;
    });
    return g + '</svg>';
  }
  // the simulation drawn in prices: the bands of the paths, a few of them, the median, every day's median for comparison
  function simSvg(R, o, AN, S, last) {
    const W = o.narrow ? 440 : 760, Hh = o.narrow ? 280 : 310, Lm = o.narrow ? 56 : 64, Rr = o.narrow ? 92 : 96, T = 16, B = 30, F = S.F;
    const pv = (v) => last * (1 + v);
    let lo = Math.min(...S.band.q5, 0), hi = Math.max(...S.band.q95, 0);
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const sx = (h) => Lm + h / F * (W - Lm - Rr), sy = (v) => T + (hi - Math.min(hi, Math.max(lo, v))) / (hi - lo) * (Hh - T - B);
    const lineS = (arr) => arr.map((v, h) => `${h ? 'L' : 'M'}${sx(h).toFixed(1)},${sy(v).toFixed(1)}`).join('');
    const area = (a, b) => `${lineS(a)}${b.map((v, h) => `L${sx(h).toFixed(1)},${sy(v).toFixed(1)}`).reverse().join('')}Z`;
    const dp = last >= 1000 ? 0 : last >= 100 ? 1 : 2;
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${num(S.M)} simulated paths of the price over the ${esc(tdWords(F))} ahead">`;
    ticks(pv(lo), pv(hi), 5).forEach((v) => { const y = sy(v / last - 1); g += `<line class="mv-g" x1="${Lm}" x2="${W - Rr}" y1="${y}" y2="${y}"/><text class="mv-t" x="${Lm - 6}" y="${y + 4}" text-anchor="end">${esc(num(v, dp))}</text>`; });
    spaced([[sx(0), R.t >= 0 ? mdy(R.A.days[AN.t]) : 'today', 'start', 1], [sx(F), dayX(F), 'end', 1], ...aMarks(F).filter(([h]) => h < F).map(([h]) => [sx(h), dayX(h), 'middle'])], o.narrow ? 76 : 90)
      .forEach(([x, l, an]) => { g += `<text class="mv-t" x="${x}" y="${Hh - B + 16}" text-anchor="${an}">${esc(l)}</text>`; });
    g += `<line x1="${Lm}" x2="${W - Rr}" y1="${sy(0)}" y2="${sy(0)}" style="stroke:${COL.mute};stroke-width:1;stroke-dasharray:3 3"/>`;
    g += `<path d="${area(S.band.q95, S.band.q5)}" style="fill:${COL.band};opacity:.12"/><path d="${area(S.band.q75, S.band.q25)}" style="fill:${COL.band};opacity:.2"/>`;
    S.samples.forEach((p) => { g += `<path d="${lineS(p)}" style="fill:none;stroke:${COL.band};stroke-width:.7;opacity:.18"/>`; });
    const ev = AN.every[F];
    if (ev) g += `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(F)}" y2="${sy(ev.med)}" style="stroke:${COL.all};stroke-width:1.5;stroke-dasharray:5 4"/>`;
    g += `<path d="${lineS(S.band.q50)}" style="fill:none;stroke:${COL.band};stroke-width:2.6"/>`;
    if (AN.actual.length > 1) g += `<path d="${AN.actual.map((v, h) => `${h ? 'L' : 'M'}${sx(h).toFixed(1)},${sy(Math.expm1(v)).toFixed(1)}`).join('')}" style="fill:none;stroke:${COL.warn};stroke-width:2.2"/>`;
    g += `<circle cx="${sx(0)}" cy="${sy(0)}" r="4.5" style="fill:${COL.ink};stroke:#fff;stroke-width:1.5"/>`;
    const lab = (v, txt, bold) => { g += `<text class="mv-l" x="${sx(F) + 6}" y="${sy(v) + 4}" style="${bold ? 'font-weight:650;fill:' + COL.band : ''}">${esc(txt)}</text>`; };
    lab(S.band.q95[F], `${num(pv(S.band.q95[F]), dp)} (95%)`); lab(S.band.q50[F], `${num(pv(S.band.q50[F]), dp)}`, true); lab(S.band.q5[F], `${num(pv(S.band.q5[F]), dp)} (5%)`);
    return g + '</svg>';
  }
  // "May 25 – Aug 24, 2017", or both years when they differ
  const spanDates = (a, b) => (a.slice(0, 4) === b.slice(0, 4) ? `${mdy(a).replace(/, \d{4}$/, '')} – ${mdy(b)}` : `${mdy(a)} – ${mdy(b)}`);
  function analogTable(R, o, AN) {
    const L = AN.L, marks = aMarks(AN.F), shape = AN.shape, D = R.A.days;
    let h = `<div class="mv-wrap"><table class="mv-tbl"><thead><tr><th>The stretch</th><th class="n">Its move</th><th class="n">Alike: r${shape ? '' : ' · gap'}</th>${marks.map(([, l]) => `<th class="n">${esc(l)} after</th>`).join('')}<th class="n">Worst · best on the way</th></tr></thead><tbody>`;
    h += `<tr class="now"><td><b>${esc(spanDates(D[AN.t - L], D[AN.t]))}</b> <span class="mv-chip hot">looked at</span></td><td class="n ${tone(-AN.now[0])}">${sp(Math.expm1(-AN.now[0]))}</td><td></td>`
      + marks.map(([hz]) => { const v = AN.actual[hz]; return `<td class="n ${tone(v)}">${v != null ? sp(Math.expm1(v)) : '—'}</td>`; }).join('') + '<td></td></tr>';
    AN.items.forEach((x, i) => {
      h += `<tr><td><span class="mv-sub" style="display:inline">${i + 1}.</span> ${esc(spanDates(D[x.j - L], D[x.j]))}</td><td class="n ${tone(x.move)}">${sp(x.move)}</td><td class="n">${num(x.corr, 2)}${shape ? '' : ` · ${num(x.d * 100, 1)}%`}</td>`
        + marks.map(([hz]) => { const v = Math.expm1(x.fwd[hz]); return `<td class="n ${tone(v)}">${sp(v)}</td>`; }).join('') + `<td class="n"><span class="mv-down">${sp(x.worst)}</span> · <span class="mv-up">${sp(x.best)}</span></td></tr>`;
    });
    const row = (lab, f, cls) => `<tr class="grp"><td>${lab}</td><td></td><td></td>${marks.map(([hz]) => { const v = f(hz); return `<td class="n ${cls === true ? tone(v) : ''}">${v == null ? '—' : cls === 'share' ? share(v) : sp(v)}</td>`; }).join('')}<td></td></tr>`;
    h += row(`Expected (average${R.hl ? ', older days counting less' : ''})`, (hz) => AN.E.mean[hz], true) + row('Median', (hz) => AN.E.med[hz], true)
      + row('Higher', (hz) => AN.items.reduce((a, x) => a + (x.fwd[hz] > 0 ? x.w : 0), 0) / (AN.W || 1), 'share')
      + row('Every day: average', (hz) => (AN.every[hz] ? AN.every[hz].mean : null), true) + row('Every day: higher', (hz) => (AN.every[hz] ? AN.every[hz].up : null), 'share');
    return h + '</tbody></table></div>';
  }
  function analogSection(R, o, doc) {
    const AN = R.an;
    if (!AN) return '';
    const pill = (k, v, l, on) => `<button type="button" class="mv-pill${on ? ' on' : ''}" data-mv="${k}" data-v="${esc(v)}">${esc(l)}</button>`;
    let h = `<h3>Similar stretches in its history</h3>`;
    h += `<div class="mv-bar"><div><label>Stretch: the last</label><div class="mv-pills">${ALEN.map(([v, l]) => pill('alen', v, l, AN.L === v)).join('')}</div></div>`
      + `<div><label>Then</label><div class="mv-pills">${ALEN.map(([v, l]) => pill('afwd', v, l, AN.F === v)).join('')}</div></div>`
      + `<div><label>How many</label><div class="mv-pills">${AKS.map((v) => pill('ak', v, String(v), AN.K === v)).join('')}</div></div>`
      + `<div><label>Alike in</label><div class="mv-pills">${pill('amatch', 'size', 'size and shape', !AN.shape)}${pill('amatch', 'shape', 'shape only', AN.shape)}</div></div></div>`;
    if (AN.error) return h + `<p class="mv-sub">${esc(AN.error)}</p>`;
    const name = esc(doc.ticker || doc.name), L = AN.L, F = AN.F, E = AN.E, nI = AN.items.length, upN = AN.items.filter((x) => x.fwd[F] > 0).length;
    const ev = AN.every[F], cN = R.c[R.c.length - 1], last = (R.A.last || doc.last) * Math.exp(R.c[AN.t] - cN);
    h += `<p class="mv-sub">The ${words(nI, 'stretch')} of ${esc(tdWords(L))} in ${name}'s history since ${esc(my(AN.from))} whose path was most like the ${esc(tdWords(L))} to ${esc(mdy(R.A.days[AN.t]))}${AN.shape ? ' in shape (each scaled to its own swings)' : ' in size and shape'}, none overlapping, each ended before that stretch began, and what followed each over the next ${esc(tdWords(F))}: green when higher at the end, red when lower; the thick blue line is the expected path (their average${R.hl ? ', older days counting less' : ''}), the dotted one the median, the blue band the middle half; grey, the range of every ${esc(tdWords(F))} in its history (5–95%).${AN.actual.length > 1 ? ` Orange: what followed ${esc(mdy(R.A.days[AN.t]))}.` : ''}</p>`;
    h += `<p class="mv-head" style="font-size:16px">${num(upN)} of ${num(nI)} were higher ${esc(tdWords(F))} later. Expected after a stretch like this: ${aMarks(F).filter(([hz]) => hz < E.mean.length).map(([hz, l]) => `${esc(l)} <b class="${tone(E.mean[hz])}">${sp(E.mean[hz])}</b>`).join(' · ')}`
      + `${ev ? ` <span class="mv-sub" style="display:inline">(every ${esc(tdWords(F))}: ${sp(ev.mean)} on average, ${share(ev.up)} higher)</span>` : ''}.</p>`;
    h += analogSvg(R, o, AN);
    h += `<div class="mv-legend"><span><b style="background:${COL.ink}"></b>the stretch looked at</span><span><b style="background:${COL.up}"></b><b style="background:${COL.down}"></b>what followed each stretch like it</span><span><b style="background:${COL.band}"></b>expected (average)</span><span><b style="background:none;border-top:2px dotted ${COL.ink};height:0;width:14px;border-radius:0"></b>median</span><span><b style="background:${COL.band};opacity:.3"></b>middle half</span><span><b style="background:${COL.all};opacity:.3"></b>every ${esc(tdWords(F))}, 5–95%</span>${AN.actual.length > 1 ? `<span><b style="background:${COL.warn}"></b>what followed this day</span>` : ''}</div>`;
    h += analogTable(R, o, AN);
    const S = AN.sim;
    if (S && fin(last)) {
      const pv = (v) => last * (1 + v), dp = last >= 1000 ? 0 : last >= 100 ? 1 : 2;
      h += `<h3>A simulation of the ${esc(tdWords(F))} ahead</h3>`;
      h += `<p class="mv-sub">${num(S.M)} paths, each built a week at a time: every week is one drawn at random from the ${esc(tdWords(F))} after one of the ${words(nI, 'stretch')} above${R.hl ? ' (a stretch by its weight)' : ''}, so their good and bad weeks are mixed into many more paths than the ${num(nI)} alone. The bands hold the middle 50% and 90% of the paths at each day; a few of them are drawn thin; the dashed grey line is the median of every ${esc(tdWords(F))} in its history; prices from the close of ${esc(mdy(R.A.days[AN.t]))} (${esc(num(last, dp))}).</p>`;
      h += `<p class="mv-head" style="font-size:16px">In ${esc(tdWords(F))}: median <b class="${tone(S.band.q50[F])}">${esc(num(pv(S.band.q50[F]), dp))}</b> (${sp(S.band.q50[F])}); 90% of the paths between ${esc(num(pv(S.band.q5[F]), dp))} and ${esc(num(pv(S.band.q95[F]), dp))}. Higher than today in <b>${share(S.up)}</b> of them; on the way, ${share(S.down10)} fell 10% or more at some point and ${share(S.up10)} rose 10% or more.</p>`;
      h += simSvg(R, o, AN, S, last);
      h += `<div class="mv-legend"><span><b style="background:${COL.band}"></b>median path</span><span><b style="background:${COL.band};opacity:.35"></b>middle half</span><span><b style="background:${COL.band};opacity:.15"></b>90% of the paths</span><span><b style="background:none;border-top:2px dashed ${COL.all};height:0;width:14px;border-radius:0"></b>every ${esc(tdWords(F))}: median</span>${AN.actual.length > 1 ? `<span><b style="background:${COL.warn}"></b>what happened</span>` : ''}</div>`;
    }
    return h;
  }

  /* ---------- how long it took: climbing back, a new high ---------- */
  const RLAB = (rs, kind) => (kind === 'high' ? (rs < 0 ? 'back to a new high' : 'the next new high') : (rs < 0 ? 'back to the close before the move' : 'gave the rise back'));
  const dayWords = (d) => (d == null ? '—' : d <= 1 ? `${d} day` : `${num(d)} days`);
  function recSets(R, o) {
    const rs = R.rec.side;
    return [['sim', COL.band, `Days like it (±${fb(o.band)} pts)`], ['ext', R.side > 0 ? COL.up : COL.down, `At least as ${R.side > 0 ? 'high' : 'low'}`],
      ['base', COL.all, `Every ${rs < 0 ? 'down' : 'up'} ${o.w === 1 ? 'day' : o.w === 5 ? 'week' : 'month'}`]];
  }
  function recoverySvg(R, o, kind) {
    const D = kind === 'high' ? 504 : 252, W = o.narrow ? 440 : 720, Hh = 230, L = 44, Rr = 16, T = 14, B = 30;
    const sx = (d) => L + Math.min(d, D) / D * (W - L - Rr), sy = (v) => T + (1 - v) * (Hh - T - B);
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Share of the chosen days ${esc(RLAB(R.rec.side, kind))}, by trading days after">`;
    [0, 0.25, 0.5, 0.75, 1].forEach((v) => { g += `<line class="mv-g" x1="${L}" x2="${W - Rr}" y1="${sy(v)}" y2="${sy(v)}"/><text class="mv-t" x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${v * 100}%</text>`; });
    [[0, '0'], [21, '1 mo'], [63, '3 mo'], [126, '6 mo'], [252, '1 yr'], [504, '2 yr']].filter(([d]) => d <= D).forEach(([d, l]) => {
      g += `<line class="mv-g" x1="${sx(d)}" x2="${sx(d)}" y1="${T}" y2="${Hh - B}"/><text class="mv-t" x="${sx(d)}" y="${Hh - B + 16}" text-anchor="middle">${l}</text>`; });
    for (const [k, col] of recSets(R, o).reverse()) {
      const K = R.rec[k][kind];
      if (!K || !K.n) continue;
      let d = `M${sx(0).toFixed(1)},${sy(0).toFixed(1)}`, y = 0;
      for (const [t0, S] of K.steps) { if (t0 > D) break; d += `L${sx(t0).toFixed(1)},${sy(y).toFixed(1)}L${sx(t0).toFixed(1)},${sy(1 - S).toFixed(1)}`; y = 1 - S; }
      d += `L${sx(D).toFixed(1)},${sy(y).toFixed(1)}`;
      g += `<path d="${d}" style="fill:none;stroke:${col};stroke-width:${k === 'base' ? 1.6 : 2.2};opacity:${k === 'base' ? 0.8 : 1}"/>`;
      if (k === 'sim' && K.median != null && K.median <= D) g += `<line x1="${sx(K.median)}" x2="${sx(K.median)}" y1="${sy(0.5)}" y2="${Hh - B}" style="stroke:${col};stroke-dasharray:4 3"/>`;
    }
    const nw = R.rec.now, act = nw && (kind === 'high' ? nw.highIn : nw.backIn);
    if (o.mode === 'date' && act != null) g += `<circle cx="${sx(act)}" cy="${sy(0)}" r="5" style="fill:${COL.warn};stroke:#fff;stroke-width:1.5"/>`;
    return g + '</svg>';
  }
  function recoveryTable(R, o, kind) {
    const marks = kind === 'high' ? [[21, '1 month'], [63, '3 months'], [126, '6 months'], [252, '1 year'], [504, '2 years']] : [[5, '1 week'], [10, '2 weeks'], [21, '1 month'], [63, '3 months'], [252, '1 year']];
    let h = `<div class="mv-wrap"><table class="mv-tbl"><thead><tr><th></th><th class="n">Median</th>${marks.map(([, l]) => `<th class="n">Within ${l}</th>`).join('')}<th class="n">Days</th><th class="n">Not back on file</th></tr></thead><tbody>`;
    for (const [k, col, lab] of recSets(R, o)) {
      const K = R.rec[k][kind];
      if (!K || !K.n) { h += `<tr><td>${esc(lab)}</td><td colspan="${marks.length + 3}" class="mv-sub">none</td></tr>`; continue; }
      h += `<tr><td><b style="display:inline-block;width:10px;height:3px;background:${col};vertical-align:middle;margin-right:6px"></b>${esc(lab)}</td><td class="n">${K.median == null ? 'over half never' : dayWords(K.median)}</td>`
        + marks.map(([d]) => `<td class="n">${share(K.by(d))}</td>`).join('') + `<td class="n">${num(K.n)}</td><td class="n">${num(K.n - K.events)}</td></tr>`;
    }
    return h + '</tbody></table></div>';
  }
  function recoveryNow(R, o, doc) {
    const nw = R.rec.now, rs = R.rec.side, A = R.A, name = esc(doc.ticker || doc.name);
    if (!nw) return '';
    const pre = esc(mdy(A.days[nw.pre])), pk = esc(mdy(A.days[nw.peak]));
    if (o.mode === 'date') {
      const b = nw.backIn != null ? `${rs < 0 ? 'climbed back to' : 'gave the rise back to'} ${pre}'s close after <b>${dayWords(nw.backIn)}</b>` : `${rs < 0 ? 'had not climbed back to' : 'had not given the rise back to'} ${pre}'s close by the last day on file`;
      const hh = nw.high <= 1e-9 ? 'closed at a new high that day' : nw.highIn != null ? `was back at a new high after <b>${dayWords(nw.highIn)}</b>` : 'has not been back to its high since';
      return `<p class="mv-sub" style="font-size:14px;color:var(--ink,#222)">After ${esc(mdy(A.days[R.t]))}, ${name} ${b}, and ${hh}.</p>`;
    }
    if (rs < 0) return `<p class="mv-sub" style="font-size:14px;color:var(--ink,#222)">To climb back to ${pre}'s close, ${name} needs <b class="mv-up">${sp(nw.back)}</b>; to a new high (its highest close on file, ${pk}) <b class="mv-up">${sp(nw.high)}</b>.</p>`;
    return `<p class="mv-sub" style="font-size:14px;color:var(--ink,#222)">A fall of <b class="mv-down">${sp(nw.back)}</b> would give the rise back to ${pre}'s close${nw.high <= 1e-9 ? `; ${name} closed at a new high` : `; a new high (${pk}) is ${sp(nw.high)} away`}.</p>`;
  }
  function recoverySection(R, o, doc) {
    if (!R.rec) return '';
    const rs = R.rec.side, kind = o.rk === 'high' ? 'high' : 'back', S = R.rec.sim[kind], E = R.rec.base[kind];
    const pill = (k, l) => `<button type="button" class="mv-pill${kind === k ? ' on' : ''}" data-mv="rk" data-v="${k}">${esc(l)}</button>`;
    let h = `<h3>${rs < 0 ? 'How long it took to climb back' : 'How long the rise held'}</h3>`;
    h += recoveryNow(R, o, doc);
    h += `<p class="mv-sub">After each chosen day, the trading days until the close was ${rs < 0 ? 'back at the close before the move, and back at a new high' : 'back down at the close before the move (the rise given back), and at a new high'} (the highest close on file up to that day). Days whose recovery had not come by the last day on file count for as long as they were watched (Kaplan–Meier), not as failures.</p>`;
    h += `<div class="mv-bar"><div><label>Measure</label><div class="mv-pills">${pill('back', rs < 0 ? 'Back to the close before the move' : 'Gave the rise back')}${pill('high', rs < 0 ? 'Back to a new high' : 'Next new high')}</div></div></div>`;
    if (S && S.n) h += `<p class="mv-head" style="font-size:16px">Days like it: half were ${esc(RLAB(rs, kind))} within <b>${S.median == null ? 'never (over half not yet)' : dayWords(S.median)}</b>; ${share(S.by(21))} within a month${E && E.n ? ` — every ${rs < 0 ? 'down' : 'up'} ${o.w === 1 ? 'day' : 'move'}: ${E.median == null ? 'over half never' : dayWords(E.median)}, ${share(E.by(21))}` : ''}.</p>`;
    h += recoverySvg(R, o, kind) + `<div class="mv-legend">${recSets(R, o).map(([k, col, lab]) => `<span><b style="background:${col}"></b>${esc(lab)}</span>`).join('')}${o.mode === 'date' && R.rec.now ? `<span><b style="background:${COL.warn}"></b>this day</span>` : ''}</div>`;
    return h + recoveryTable(R, o, kind);
  }


  /* ---------- volatility: realized over the whole history, and the VIX next to the market ---------- */
  function volData(R) {
    const A = R.A, N = A.days.length - 1, t = R.t >= 0 ? R.t : N, rv = realized(A.r, 21), r3 = realized(A.r, 63);
    const vs = Float64Array.from(Array.from(rv).filter(Number.isFinite)).sort();
    const out = { rv, r3, t, now: rv[t], now3: r3[t], pct: pctOf(vs, rv[t]), med: quantile(vs, 50), hi: quantile(vs, 99.5), vix: null };
    if (R.vix) {
      const V = R.vix, cv = cum(V.r), at = new Map(V.days.map((d, i) => [d, i])), lv = (k) => (V.last || 1) * Math.exp(cv[k] - cv[cv.length - 1]) / 100;
      out.vix = new Float64Array(N + 1).fill(NaN);
      for (let j = 0; j <= N; j++) { const k = at.get(A.days[j]); if (k != null) out.vix[j] = lv(k); }
      out.vixNow = out.vix[t];
      const vv = Float64Array.from(V.days, (_, k) => lv(k)).sort();         // ranked in the VIX's own history, as on its page
      out.vixPct = pctOf(vv, out.vixNow);
      out.vixSince = V.days[0];
    }
    return out;
  }
  function volSvg(R, o, V) {
    const A = R.A, N = A.days.length - 1, W = o.narrow ? 440 : 720, Hh = 230, L = 44, Rr = 14, T = 12, B = 26;
    const top = Math.max(V.hi, Number.isFinite(V.now) ? V.now : 0, V.vix && Number.isFinite(V.vixNow) ? V.vixNow : 0) * 1.08;
    const t0 = Date.parse(A.days[0]), t1 = Date.parse(A.days[N]);
    const sx = (j) => L + (Date.parse(A.days[j]) - t0) / (t1 - t0 || 1) * (W - L - Rr), sy = (v) => T + (1 - Math.min(v, top) / top) * (Hh - T - B);
    const step = Math.max(1, Math.floor(N / 1400));
    const line = (arr, col, wd, op) => { let d = '', on = false; for (let j = 0; j <= N; j += step) { const v = arr[j]; if (!Number.isFinite(v)) { on = false; continue; } d += `${on ? 'L' : 'M'}${sx(j).toFixed(1)},${sy(v).toFixed(1)}`; on = true; } return `<path d="${d}" style="fill:none;stroke:${col};stroke-width:${wd};opacity:${op}"/>`; };
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Realized volatility over one month, every day on file${V.vix ? ', with the VIX' : ''}">`;
    ticks(0, top, 4).forEach((v) => { g += `<line class="mv-g" x1="${L}" x2="${W - Rr}" y1="${sy(v)}" y2="${sy(v)}"/><text class="mv-t" x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${num(v * 100, 0)}%</text>`; });
    yearTicks(+A.days[0].slice(0, 4), +A.days[N].slice(0, 4), o.narrow ? 5 : 10).forEach((y) => { const x = L + (Date.parse(`${y}-01-01`) - t0) / (t1 - t0 || 1) * (W - L - Rr); g += `<text class="mv-t" x="${x}" y="${Hh - 8}" text-anchor="middle">${y}</text>`; });
    g += `<line x1="${L}" x2="${W - Rr}" y1="${sy(V.med)}" y2="${sy(V.med)}" style="stroke:${COL.mute};stroke-dasharray:3 3"/>`;
    if (V.vix) g += line(V.vix, COL.warn, 1.2, 0.85);
    g += line(V.rv, COL.band, 1.3, 0.95);
    if (Number.isFinite(V.now)) g += `<circle cx="${sx(V.t)}" cy="${sy(V.now)}" r="4.5" style="fill:${COL.band};stroke:#fff;stroke-width:1.5"/>`;
    return g + '</svg>';
  }
  function volSection(R, o, doc) {
    if (R.volIdx) return '';
    const V = volData(R), A = R.A, name = esc(doc.ticker || doc.name);
    if (!Number.isFinite(V.now)) return '';
    let h = `<h3>Volatility</h3><p class="mv-head" style="font-size:16px">${name}'s volatility over the last month: <b>${num(V.now * 100, 0)}% a year</b> — ${rankWords(V.pct)} of its days since ${esc(my(A.days[0]))} (the typical day: ${num(V.med * 100, 0)}%); over three months ${num(V.now3 * 100, 0)}%.`
      + (V.vix && Number.isFinite(V.vixNow) ? ` The VIX, what options expect of the S&P 500 over the next month: <b>${num(V.vixNow * 100, 1)}</b> (${rankWords(V.vixPct)} since ${esc(my(V.vixSince))}).` : '') + '</p>';
    h += `<p class="mv-sub">The standard deviation of the 21 daily returns up to each day, annualized${V.vix ? '; the orange line is the VIX on the same days' : ''}. "Measured as: its volatility" ranks it like a move, and "Volatility then: similar" compares only days that came in a similar stretch.</p>`;
    h += volSvg(R, o, V) + `<div class="mv-legend"><span><b style="background:${COL.band}"></b>realized, one month</span>${V.vix ? `<span><b style="background:${COL.warn}"></b>VIX (implied)</span>` : ''}<span><b style="background:none;border-top:2px dashed ${COL.mute};height:0"></b>the typical day</span></div>`;
    return h;
  }

  /* ---------- a picture to share: the chosen panels in one PNG ---------- */
  const PANELS = [['now', 'Now'], ['paths', 'Each case'], ['analog', 'Similar stretches'], ['sim', 'Simulation'], ['1', 'Next day'], ['5', '1 week'], ['10', '2 weeks'], ['21', '1 month'], ['63', '1 quarter'], ['back', 'Climb back'], ['high', 'New high'], ['vol', 'Volatility']];
  const canDraw = (R, k) => ((k !== 'back' && k !== 'high') || !!R.rec) && (k !== 'vol' || !R.volIdx)
    && (k !== 'analog' || !!(R.an && !R.an.error && R.an.items.length)) && (k !== 'sim' || !!(R.an && R.an.sim));
  const PC = { bg: '#fcfcfb', card: '#ffffff', ink: '#1d1d1b', ink2: '#3d3c39', muted: '#6b6a66', line: '#e3e1dc', up: '#17734a', down: '#c0392b', band: '#2a78d6', warn: '#d9822b', calm: '#5b7fa6', grey: '#9a9893' };
  // a Gaussian kernel density of sorted values over n points from lo to hi (Silverman's bandwidth); with weights wts
  // (in the order of vals), each value counts by its weight and the bandwidth goes by the equal days they are worth
  function kde(vals, lo, hi, n = 180, wts) {
    const m = vals.length; if (m < 3) return null;
    let W = m, mean, sd, iqr, ne = m;
    if (wts) {
      let W2 = 0, m1 = 0; W = 0;
      for (let j = 0; j < m; j++) { W += wts[j]; W2 += wts[j] * wts[j]; m1 += wts[j] * vals[j]; }
      mean = m1 / W; let ss = 0; for (let j = 0; j < m; j++) ss += wts[j] * (vals[j] - mean) * (vals[j] - mean);
      sd = Math.sqrt(ss / Math.max(W - W2 / W, 1e-12)); const Q = wquant(vals, wts); iqr = Q(75) - Q(25); ne = W * W / W2;
    } else {
      mean = vals.reduce((a, b) => a + b, 0) / m; sd = Math.sqrt(vals.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (m - 1));
      iqr = quantile(vals, 75) - quantile(vals, 25);
    }
    const bw = 0.9 * Math.min(sd, (iqr / 1.34) || sd) * Math.pow(Math.max(ne, 2), -0.2) || sd || 1;
    const xs = [], ys = [], k = 1 / (W * bw * Math.sqrt(2 * Math.PI));
    for (let i = 0; i < n; i++) {
      const x = lo + (hi - lo) * i / (n - 1); let y = 0;
      for (let j = lower(vals, x - 5 * bw), e = upper(vals, x + 5 * bw); j < e; j++) { const u = (x - vals[j]) / bw; y += (wts ? wts[j] : 1) * Math.exp(-0.5 * u * u); }
      xs.push(x); ys.push(y * k);
    }
    return { xs, ys, bw };
  }
  function pngFont(px, wt) { return `${wt || 400} ${px}px "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif`; }
  function rrect(x, X, Y, w, h, r) { x.beginPath(); x.moveTo(X + r, Y); x.arcTo(X + w, Y, X + w, Y + h, r); x.arcTo(X + w, Y + h, X, Y + h, r); x.arcTo(X, Y + h, X, Y, r); x.arcTo(X, Y, X + w, Y, r); x.closePath(); }
  function card(x, X, Y, w, h, title, sub) {
    x.fillStyle = PC.card; rrect(x, X, Y, w, h, 12); x.fill(); x.strokeStyle = PC.line; x.lineWidth = 1; x.stroke();
    x.fillStyle = PC.ink; x.font = pngFont(17, 600); x.textBaseline = 'alphabetic'; x.fillText(title, X + 16, Y + 28);
    if (sub) { x.fillStyle = PC.muted; x.font = pngFont(12.5); x.fillText(sub, X + 16, Y + 47); }
    return { x: X + 16, y: Y + (sub ? 62 : 46), w: w - 32, h: h - (sub ? 62 : 46) - 14 };
  }
  function axisX(x, P, lo, hi, fmt, n) {
    x.strokeStyle = PC.line; x.lineWidth = 1; x.fillStyle = PC.muted; x.font = pngFont(12); x.textAlign = 'center';
    const sx = (v) => P.x + (v - lo) / (hi - lo) * P.w;
    ticks(lo, hi, n || 6).forEach((v) => { x.beginPath(); x.moveTo(sx(v), P.y); x.lineTo(sx(v), P.y + P.h - 18); x.stroke(); x.fillText(fmt(v), sx(v), P.y + P.h - 2); });
    x.textAlign = 'left';
    return sx;
  }
  function curve(x, K, sx, sy, fill, stroke, alpha, lw) {
    x.beginPath(); K.xs.forEach((v, i) => { const X = sx(v), Y = sy(K.ys[i]); if (i) x.lineTo(X, Y); else x.moveTo(X, Y); });
    if (fill) { const b = sy(0); x.lineTo(sx(K.xs[K.xs.length - 1]), b); x.lineTo(sx(K.xs[0]), b); x.closePath(); x.globalAlpha = alpha; x.fillStyle = fill; x.fill(); x.globalAlpha = 1;
      x.beginPath(); K.xs.forEach((v, i) => { const X = sx(v), Y = sy(K.ys[i]); if (i) x.lineTo(X, Y); else x.moveTo(X, Y); }); }
    if (stroke) { x.strokeStyle = stroke; x.lineWidth = lw || 2; x.stroke(); }
  }
  function vline(x, X, y0, y1, col, dash) { x.save(); x.strokeStyle = col; x.lineWidth = 1.6; if (dash) x.setLineDash(dash); x.beginPath(); x.moveTo(X, y0); x.lineTo(X, y1); x.stroke(); x.restore(); }
  function label(x, text, X, Y, col, font, align) {
    x.font = font || pngFont(13, 600); x.textAlign = align || 'left'; x.lineWidth = 4; x.strokeStyle = PC.card; x.lineJoin = 'round';
    x.strokeText(text, X, Y); x.fillStyle = col || PC.ink; x.fillText(text, X, Y); x.textAlign = 'left';
  }
  function drawNow(x, box, R, o) {
    const vals = Array.from(R.s, (v) => disp(o, v)), tv = disp(o, R.value), u = unit(o), sv = Float64Array.from(vals);
    let lo = Math.min(quantile(sv, 0.3), tv), hi = Math.max(quantile(sv, 99.7), tv); const pad = (hi - lo) * 0.05; lo -= pad; hi += pad;
    const P = card(x, box.x, box.y, box.w, box.h, `Now: where the ${what(o)} ranks`, `${num(R.n)} ${whats(o)} since ${my(R.A.days[0])}${o.measure === 'raw' ? '' : ' · ' + measureName(o, 'stock')} · the coloured tail: moves at least as ${R.side > 0 ? 'high' : 'low'}`);
    const K = kde(vals, lo, hi, 180, R.sw), K0 = R.sw ? kde(vals, lo, hi) : null; if (!K) return;      // weighted; dashed, every day the same
    const top = P.y + 26, bot = P.y + P.h - 22, mx = Math.max(...K.ys, ...(K0 ? K0.ys : [])) || 1;
    const sx = axisX(x, P, lo, hi, (v) => tickFmt(o, v), 8), sy = (v) => bot - v / mx * (bot - top);
    curve(x, K, sx, sy, PC.grey, PC.grey, 0.28, 1.6);
    if (K0) { x.save(); x.setLineDash([5, 4]); curve(x, K0, sx, sy, null, PC.ink2, 1, 1.3); x.restore(); }
    const tail = { xs: [], ys: [] };
    K.xs.forEach((v, i) => { if (R.side > 0 ? v >= tv : v <= tv) { tail.xs.push(v); tail.ys.push(K.ys[i]); } });
    if (tail.xs.length > 1) curve(x, tail, sx, sy, sidePC(R, o), sidePC(R, o), 0.7, 2);
    vline(x, sx(tv), top - 8, bot, PC.ink, [5, 4]);
    const lab = `${o.mode === 'whatif' ? 'What if' : mdy(R.A.days[R.t])}: ${fmtX(o, R.value)} · ${rankWords(R.at)}`;
    x.font = pngFont(15, 650); const lw = x.measureText(lab).width;
    label(x, lab, Math.min(Math.max(sx(tv) - lw / 2, P.x), P.x + P.w - lw), top - 12, sidePC(R, o), pngFont(15, 650));
    const rare = R.every ? `a ${R.side > 0 ? 'rise' : 'fall'} this large or larger: 1 in ${num(R.every, R.every < 10 ? 1 : 0)} ${o.w === 1 ? 'trading days' : 'days'}` : '';
    label(x, rare, P.x + P.w, P.y + 8, PC.muted, pngFont(12.5), 'right');
  }
  function drawHorizon(x, box, R, o, hz, which) {
    const S = R.h[hz][which], A = R.h[hz].all, hl = H.find((v) => v[0] === hz)[1];
    const P = card(x, box.x, box.y, box.w, box.h, `${hl}${hz === 1 ? '' : ` (${hz} trading days)`}`, `after the ${which === 'sim' ? `days like it (±${fb(o.band)} pts)` : `days at least as ${R.side > 0 ? 'high' : 'low'}`} · after every day`);
    if (!S || !A || S.s.length < 3) { x.fillStyle = PC.muted; x.font = pngFont(13); x.fillText('Too few days to draw.', P.x, P.y + 40); return; }
    const sv = Array.from(S.s, (v) => v * 100), av = Array.from(A.s, (v) => v * 100), pool = Float64Array.from([...sv, ...av]).sort();
    let lo = Math.min(quantile(pool, 1), 0), hi = Math.max(quantile(pool, 99), 0);
    const act = fin(R.actual[hz]) ? R.actual[hz] * 100 : null; if (act != null) { lo = Math.min(lo, act); hi = Math.max(hi, act); }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const Ks = kde(sv, lo, hi, 180, S.sw), Ka = kde(av, lo, hi, 180, A.sw); if (!Ks || !Ka) return;
    const E = R.eq && R.eq.h[hz] && R.eq.h[hz][which], Ke = E && E.s.length >= 3 ? kde(Array.from(E.s, (v) => v * 100), lo, hi) : null;   // every day the same
    const top = P.y + (Ke ? 66 : 46), bot = P.y + P.h - 22, mx = Math.max(...Ks.ys, ...Ka.ys, ...(Ke ? Ke.ys : [])) || 1;
    const sx = axisX(x, P, lo, hi, (v) => sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0), 6), sy = (v) => bot - v / mx * (bot - top);
    vline(x, sx(0), top, bot, PC.line);
    const col = which === 'sim' ? PC.band : sidePC(R, o);
    curve(x, Ka, sx, sy, null, PC.grey, 1, 1.8);
    curve(x, Ks, sx, sy, col, col, 0.3, 2.2);
    if (Ke) { x.save(); x.setLineDash([5, 4]); curve(x, Ke, sx, sy, null, col, 1, 1.5); x.restore(); }
    vline(x, sx(S.median * 100), top, bot, col, [5, 4]); vline(x, sx(A.median * 100), top, bot, PC.grey, [2, 3]);
    if (act != null) { vline(x, sx(act), top - 4, bot, PC.warn); label(x, `what happened ${sp(act / 100)}`, Math.min(sx(act) + 6, P.x + P.w - 150), bot - 8, PC.warn, pngFont(12.5, 600)); }
    const line = (y, c, t1, t2) => { x.fillStyle = c; x.fillRect(P.x, y - 9, 12, 4); x.font = pngFont(13, 600); x.fillStyle = PC.ink; x.fillText(t1, P.x + 18, y - 4); const w1 = x.measureText(t1).width; x.font = pngFont(13); x.fillStyle = PC.ink2; x.fillText(t2, P.x + 18 + w1 + 6, y - 4); };
    line(P.y + 14, col, `${which === 'sim' ? 'days like it' : 'at least as ' + (R.side > 0 ? 'high' : 'low')}: median ${sp(S.median)}`, `· ${share(S.up)} rose · ${num(S.n)} days${S.neff ? ` (worth ≈${num(S.neff)})` : ''}`);
    line(P.y + 34, PC.grey, `every day: median ${sp(A.median)}`, `· ${share(A.up)} rose`);
    if (Ke) {                                                       // a dashed swatch: the same days with every day counting the same
      x.save(); x.strokeStyle = col; x.lineWidth = 2; x.setLineDash([4, 3]); x.beginPath(); x.moveTo(P.x, P.y + 47); x.lineTo(P.x + 12, P.y + 47); x.stroke(); x.restore();
      x.font = pngFont(13, 600); x.fillStyle = PC.ink; const t1 = `unweighted: median ${sp(E.median)}`; x.fillText(t1, P.x + 18, P.y + 50);
      const w1 = x.measureText(t1).width; x.font = pngFont(13); x.fillStyle = PC.ink2; x.fillText(`· ${share(E.up)} rose · ${num(E.n)} days`, P.x + 18 + w1 + 6, P.y + 50);
    }
  }
  function drawRecovery(x, box, R, o, kind, doc) {
    const rs = R.rec.side, D = kind === 'high' ? 504 : 252;
    const P = card(x, box.x, box.y, box.w, box.h, kind === 'high' ? (rs < 0 ? 'How long to a new high' : 'How long to the next new high') : (rs < 0 ? 'How long to climb back' : 'How long the rise held'),
      kind === 'high' ? 'share back at the highest close on file up to the day, by trading days after' : rs < 0 ? 'share back at the close before the move, by trading days after' : 'share that gave the rise back, by trading days after');
    const nw = R.rec.now;
    const top = P.y + 66, bot = P.y + P.h - 22, L = P.x + 34, Wd = P.w - 34;
    const sx = (d) => L + Math.min(d, D) / D * Wd, sy = (v) => bot - v * (bot - top);
    x.font = pngFont(12); x.fillStyle = PC.muted; x.strokeStyle = PC.line; x.lineWidth = 1;
    [0, 0.5, 1].forEach((v) => { x.beginPath(); x.moveTo(L, sy(v)); x.lineTo(L + Wd, sy(v)); x.stroke(); x.textAlign = 'right'; x.fillText(v * 100 + '%', L - 6, sy(v) + 4); });
    x.textAlign = 'center';
    [[0, '0'], [21, '1 mo'], [63, '3 mo'], [126, '6 mo'], [252, '1 yr'], [504, '2 yr']].filter(([d]) => d <= D).forEach(([d, l]) => x.fillText(l, sx(d), P.y + P.h - 2));
    x.textAlign = 'left';
    const sets = recSets(R, o).map(([k, , lab]) => [k, k === 'sim' ? PC.band : k === 'ext' ? (R.side > 0 ? PC.up : PC.down) : PC.grey, lab]);
    for (const [k, col] of sets.slice().reverse()) {
      const K = R.rec[k][kind]; if (!K || !K.n) continue;
      x.beginPath(); x.moveTo(sx(0), sy(0)); let y = 0;
      for (const [t0, S] of K.steps) { if (t0 > D) break; x.lineTo(sx(t0), sy(y)); x.lineTo(sx(t0), sy(1 - S)); y = 1 - S; }
      x.lineTo(sx(D), sy(y)); x.strokeStyle = col; x.lineWidth = k === 'base' ? 1.6 : 2.4; x.stroke();
    }
    const S = R.rec.sim[kind], E = R.rec.base[kind];
    const t1 = S && S.n ? `days like it: half ${S.median == null ? 'not yet' : 'within ' + dayWords(S.median)} · ${share(S.by(21))} within a month` : 'days like it: none';
    const t2 = E && E.n ? `every ${rs < 0 ? 'down' : 'up'} ${o.w === 1 ? 'day' : 'move'}: half ${E.median == null ? 'not yet' : 'within ' + dayWords(E.median)} · ${share(E.by(21))} within a month` : '';
    x.fillStyle = PC.band; x.fillRect(P.x, P.y + 5, 12, 4); x.font = pngFont(13, 600); x.fillStyle = PC.ink; x.fillText(t1, P.x + 18, P.y + 10);
    const X = R.rec.ext[kind];
    const t3 = X && X.n ? `at least as ${R.side > 0 ? 'high' : 'low'}: half ${X.median == null ? 'not yet' : 'within ' + dayWords(X.median)} · ${share(X.by(21))} within a month` : '';
    if (t3) { x.fillStyle = R.side > 0 ? PC.up : PC.down; x.fillRect(P.x, P.y + 25, 12, 4); x.font = pngFont(13); x.fillStyle = PC.ink2; x.fillText(t3, P.x + 18, P.y + 30); }
    if (t2) { x.fillStyle = PC.grey; x.fillRect(P.x, P.y + 45, 12, 4); x.font = pngFont(13); x.fillStyle = PC.ink2; x.fillText(t2, P.x + 18, P.y + 50); }
    if (nw && o.mode !== 'whatif') {
      const need = kind === 'high' ? nw.high : nw.back, done = kind === 'high' ? nw.highIn : nw.backIn;
      const txt = o.mode === 'date' ? (done != null ? `this day: ${dayWords(done)}` : 'this day: not yet')
        : kind === 'high' ? (need <= 1e-9 ? 'at a new high now' : `needs ${sp(need)} for a new high`) : rs < 0 ? `needs ${sp(need)} to get back` : `a ${sp(need)} fall gives it back`;
      label(x, txt, P.x + P.w, P.y + 10, PC.warn, pngFont(13, 650), 'right');
    }
  }
  function drawVol(x, box, R, o, doc) {
    const V = volData(R), A = R.A, N = A.days.length - 1;
    const P = card(x, box.x, box.y, box.w, box.h, 'Volatility over a month, every day on file', `realized: the standard deviation of 21 daily returns, annualized${V.vix ? ' · orange: the VIX (implied)' : ''}`);
    if (!Number.isFinite(V.now)) return;
    const top = Math.max(V.hi, V.now, V.vix && Number.isFinite(V.vixNow) ? V.vixNow : 0) * 1.08, L = P.x + 40, Wd = P.w - 40, y0 = P.y + 30, y1 = P.y + P.h - 22;
    const t0 = Date.parse(A.days[0]), t1 = Date.parse(A.days[N]);
    const sx = (j) => L + (Date.parse(A.days[j]) - t0) / (t1 - t0 || 1) * Wd, sy = (v) => y1 - Math.min(v, top) / top * (y1 - y0);
    x.font = pngFont(12); x.fillStyle = PC.muted; x.strokeStyle = PC.line; x.lineWidth = 1;
    ticks(0, top, 4).forEach((v) => { x.beginPath(); x.moveTo(L, sy(v)); x.lineTo(L + Wd, sy(v)); x.stroke(); x.textAlign = 'right'; x.fillText(num(v * 100, 0) + '%', L - 6, sy(v) + 4); });
    x.textAlign = 'center';
    yearTicks(+A.days[0].slice(0, 4), +A.days[N].slice(0, 4), 8).forEach((y) => x.fillText(String(y), L + (Date.parse(`${y}-01-01`) - t0) / (t1 - t0 || 1) * Wd, P.y + P.h - 2));
    x.textAlign = 'left';
    const step = Math.max(1, Math.floor(N / 1600));
    const path = (arr, col, wd) => { x.beginPath(); let on = false; for (let j = 0; j <= N; j += step) { const v = arr[j]; if (!Number.isFinite(v)) { on = false; continue; } if (on) x.lineTo(sx(j), sy(v)); else x.moveTo(sx(j), sy(v)); on = true; } x.strokeStyle = col; x.lineWidth = wd; x.stroke(); };
    x.save(); x.setLineDash([3, 3]); x.strokeStyle = PC.grey; x.beginPath(); x.moveTo(L, sy(V.med)); x.lineTo(L + Wd, sy(V.med)); x.stroke(); x.restore();
    if (V.vix) path(V.vix, PC.warn, 1.2);
    path(V.rv, PC.band, 1.4);
    x.beginPath(); x.arc(sx(V.t), sy(V.now), 4.5, 0, 2 * Math.PI); x.fillStyle = PC.band; x.fill(); x.strokeStyle = '#fff'; x.lineWidth = 1.5; x.stroke();
    label(x, `now ${num(V.now * 100, 0)}% a year · ${rankWords(V.pct)} · typical ${num(V.med * 100, 0)}%${V.vix && Number.isFinite(V.vixNow) ? ` · VIX ${num(V.vixNow * 100, 1)}` : ''}`, P.x + P.w, P.y + 10, PC.band, pngFont(13, 650), 'right');
  }
  function drawPaths(x, box, R, o) {
    const which = o.set === 'ext' ? 'ext' : 'sim', cs = cases(R, o, which), E = expectedOf(cs, caseW(R, cs)), now = nowPath(R);
    const P = card(x, box.x, box.y, box.w, box.h, `Each ${which === 'sim' ? 'day like it' : 'day at least as ' + (R.side > 0 ? 'high' : 'low')} and the path after it`,
      `${num(cs.length)} cases, dashed (green ended up, red down) · thick blue: the expected path (average) · dotted: median${now ? ' · orange: this day' : ''}`);
    const pts = []; cs.forEach((c) => c.path.forEach((v) => pts.push(v)));
    if (pts.length < 3) { x.fillStyle = PC.muted; x.font = pngFont(13); x.fillText('Too few days to draw.', P.x, P.y + 40); return; }
    const sv = Float64Array.from(pts).sort();
    let lo = Math.min(quantile(sv, 1.5), 0, ...E.mean), hi = Math.max(quantile(sv, 98.5), 0, ...E.mean);
    if (now) { lo = Math.min(lo, ...now); hi = Math.max(hi, ...now); }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const L = P.x + 46, Wd = P.w - 46 - 70, top = P.y + 8, bot = P.y + P.h - 22;
    const sx = (h) => L + px(h) * Wd, sy = (v) => bot - (v - lo) / (hi - lo) * (bot - top);
    x.font = pngFont(12); x.fillStyle = PC.muted; x.strokeStyle = PC.line; x.lineWidth = 1;
    ticks(lo * 100, hi * 100, 5).forEach((v) => { x.beginPath(); x.moveTo(L, sy(v / 100)); x.lineTo(L + Wd, sy(v / 100)); x.stroke(); x.textAlign = 'right'; x.fillText(sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0), L - 6, sy(v / 100) + 4); });
    x.textAlign = 'center';
    PATH_MARKS.forEach(([h, l]) => { x.save(); x.setLineDash([2, 3]); x.beginPath(); x.moveTo(sx(h), top); x.lineTo(sx(h), bot); x.stroke(); x.restore(); x.fillText(l, sx(h), P.y + P.h - 4); });
    x.textAlign = 'left';
    const path = (p) => { x.beginPath(); p.forEach((v, h) => { if (h) x.lineTo(sx(h), sy(v)); else x.moveTo(sx(h), sy(v)); }); };
    const op = Math.max(0.12, Math.min(0.75, 2.6 / Math.sqrt(cs.length)));
    x.save(); x.beginPath(); x.rect(L, top, Wd + 2, bot - top); x.clip();
    x.save(); x.setLineDash([4, 3]); x.lineWidth = 1.1;
    cs.forEach((c) => { if (c.path.length < 2) return; x.globalAlpha = op * (R.wt ? 0.15 + 0.85 * R.wt[c.j] : 1); x.strokeStyle = c.path[c.path.length - 1] >= 0 ? PC.up : PC.down; path(c.path); x.stroke(); });
    x.restore();
    if (E.med.length > 1) { x.save(); x.setLineDash([1.5, 3]); x.strokeStyle = PC.ink; x.lineWidth = 1.4; path(E.med); x.stroke(); x.restore(); }
    if (E.mean.length > 1) { x.strokeStyle = PC.band; x.lineWidth = 3; path(E.mean); x.stroke(); }
    if (now) { x.strokeStyle = PC.warn; x.lineWidth = 2.4; path(now); x.stroke(); }
    x.restore();
    PATH_MARKS.forEach(([h]) => {
      if (h >= E.mean.length) return;
      const X = sx(h), Y = sy(E.mean[h]);
      x.beginPath(); x.arc(X, Y, 4, 0, Math.PI * 2); x.fillStyle = PC.band; x.fill();
      label(x, sp(E.mean[h]), h === PATH_D ? X + 8 : X, Y - 9, PC.band, pngFont(13, 650), h === PATH_D ? 'left' : 'center');
    });
  }
  // the picture's similar stretches and simulation (as the view draws them)
  function drawAnalog(x, box, R, o) {
    const AN = R.an, L = AN.L, F = AN.F, E = AN.E;
    const P = card(x, box.x, box.y, box.w, box.h, `The ${words(AN.items.length, 'stretch')} most like the last ${tdWords(L)}, and the ${tdWords(F)} after`,
      `black: the last ${tdWords(L)} · green / red: what followed each · thick blue: expected (average) · dotted: median · grey: every ${tdWords(F)}, 5–95%${AN.actual.length > 1 ? ' · orange: what happened' : ''}`);
    const ex = Math.expm1, pts = [];
    AN.items.forEach((it) => { it.back.forEach((v) => pts.push(ex(v))); it.fwd.forEach((v) => pts.push(ex(v))); }); AN.now.forEach((v) => pts.push(ex(v)));
    const sv = Float64Array.from(pts).sort();
    let lo = Math.min(quantile(sv, 1), 0, ...E.q25), hi = Math.max(quantile(sv, 99), 0, ...E.q75); const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const Lx = P.x + 46, Wd = P.w - 46 - 76, top = P.y + 8, bot = P.y + P.h - 22;
    const sx = (h) => Lx + (h + L) / (L + F) * Wd, sy = (v) => bot - (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo) * (bot - top);
    x.font = pngFont(12); x.fillStyle = PC.muted; x.strokeStyle = PC.line; x.lineWidth = 1;
    ticks(lo * 100, hi * 100, 5).forEach((v) => { x.beginPath(); x.moveTo(Lx, sy(v / 100)); x.lineTo(Lx + Wd, sy(v / 100)); x.stroke(); x.textAlign = 'right'; x.fillText(sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0), Lx - 6, sy(v / 100) + 4); });
    spaced([[sx(-L), dayX(-L), 'left', 1], [sx(0), R.t >= 0 ? mdy(R.A.days[AN.t]) : 'today', 'center', 1], [sx(F), dayX(F), 'right', 1], ...aMarks(F).filter(([h]) => h < F).map(([h]) => [sx(h), dayX(h), 'center'])], 96)
      .forEach(([X, l, an]) => { x.textAlign = an; x.fillText(l, X, P.y + P.h - 4); });
    x.textAlign = 'left';
    vline(x, sx(0), top, bot, PC.ink, [3, 3]);
    x.save(); x.beginPath(); x.rect(Lx, top, Wd + 2, bot - top); x.clip();
    const ev = AN.every[F];
    if (ev) { x.beginPath(); x.moveTo(sx(0), sy(0)); x.lineTo(sx(F), sy(ev.q95)); x.lineTo(sx(F), sy(ev.q5)); x.closePath(); x.globalAlpha = 0.12; x.fillStyle = PC.grey; x.fill(); x.globalAlpha = 1; }
    if (E.mean.length > 1) { x.beginPath(); E.q75.forEach((v, h) => (h ? x.lineTo(sx(h), sy(v)) : x.moveTo(sx(h), sy(v)))); for (let h = E.q25.length - 1; h >= 0; h--) x.lineTo(sx(h), sy(E.q25[h])); x.closePath(); x.globalAlpha = 0.14; x.fillStyle = PC.band; x.fill(); x.globalAlpha = 1; }
    const path = (arr, off, log) => { x.beginPath(); Array.from(arr).forEach((v, k) => { const y = sy(log ? ex(v) : v); if (k) x.lineTo(sx(k + off), y); else x.moveTo(sx(k + off), y); }); };
    const op = Math.max(0.2, Math.min(0.8, 2.4 / Math.sqrt(AN.items.length)));
    AN.items.forEach((it) => {
      const fade = R.wt ? 0.15 + 0.85 * it.w : 1;
      x.globalAlpha = op * 0.8 * fade; x.strokeStyle = PC.grey; x.lineWidth = 1; path(it.back, -L, true); x.stroke();
      x.globalAlpha = op * fade; x.strokeStyle = it.fwd[F] >= 0 ? PC.up : PC.down; x.lineWidth = 1.3; path(it.fwd, 0, true); x.stroke();
    });
    x.globalAlpha = 1;
    if (E.med.length > 1) { x.save(); x.setLineDash([1.5, 3]); x.strokeStyle = PC.ink; x.lineWidth = 1.4; path(E.med, 0, false); x.stroke(); x.restore(); }
    if (E.mean.length > 1) { x.strokeStyle = PC.band; x.lineWidth = 3; path(E.mean, 0, false); x.stroke(); }
    x.strokeStyle = PC.ink; x.lineWidth = 2.4; path(AN.now, -L, true); x.stroke();
    if (AN.actual.length > 1) { x.strokeStyle = PC.warn; x.lineWidth = 2.4; path(AN.actual, 0, true); x.stroke(); }
    x.restore();
    aMarks(F).forEach(([h]) => {
      if (h >= E.mean.length) return;
      const X = sx(h), Y = sy(E.mean[h]);
      x.beginPath(); x.arc(X, Y, 4, 0, Math.PI * 2); x.fillStyle = PC.band; x.fill();
      if (h === F || h >= 21) label(x, sp(E.mean[h]), h === F ? X + 8 : X, Y - 9, PC.band, pngFont(13, 650), h === F ? 'left' : 'center');
    });
  }
  function drawSim(x, box, R, o, doc) {
    const AN = R.an, S = AN.sim, F = S.F, cN = R.c[R.c.length - 1], last = (R.A.last || doc.last) * Math.exp(R.c[AN.t] - cN), dp = last >= 1000 ? 0 : last >= 100 ? 1 : 2;
    const pv = (v) => last * (1 + v);
    const P = card(x, box.x, box.y, box.w, box.h, `A simulation: ${num(S.M)} paths over the next ${tdWords(F)}, from what followed the stretches like it`,
      `median ${num(pv(S.band.q50[F]), dp)} (${sp(S.band.q50[F])}) · 90% of paths ${num(pv(S.band.q5[F]), dp)}–${num(pv(S.band.q95[F]), dp)} · higher in ${share(S.up)} · fell 10% on the way in ${share(S.down10)}, rose 10% in ${share(S.up10)}`);
    let lo = Math.min(...S.band.q5, 0), hi = Math.max(...S.band.q95, 0); const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const Lx = P.x + 60, Wd = P.w - 60 - 100, top = P.y + 8, bot = P.y + P.h - 22;
    const sx = (h) => Lx + h / F * Wd, sy = (v) => bot - (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo) * (bot - top);
    x.font = pngFont(12); x.fillStyle = PC.muted; x.strokeStyle = PC.line; x.lineWidth = 1;
    ticks(pv(lo), pv(hi), 5).forEach((v) => { const Y = sy(v / last - 1); x.beginPath(); x.moveTo(Lx, Y); x.lineTo(Lx + Wd, Y); x.stroke(); x.textAlign = 'right'; x.fillText(num(v, dp), Lx - 6, Y + 4); });
    spaced([[sx(0), R.t >= 0 ? mdy(R.A.days[AN.t]) : 'today', 'left', 1], [sx(F), dayX(F), 'right', 1], ...aMarks(F).filter(([h]) => h < F).map(([h]) => [sx(h), dayX(h), 'center'])], 100)
      .forEach(([X, l, an]) => { x.textAlign = an; x.fillText(l, X, P.y + P.h - 4); });
    x.textAlign = 'left';
    const band = (a, b, al) => { x.beginPath(); a.forEach((v, h) => (h ? x.lineTo(sx(h), sy(v)) : x.moveTo(sx(h), sy(v)))); for (let h = b.length - 1; h >= 0; h--) x.lineTo(sx(h), sy(b[h])); x.closePath(); x.globalAlpha = al; x.fillStyle = PC.band; x.fill(); x.globalAlpha = 1; };
    band(S.band.q95, S.band.q5, 0.13); band(S.band.q75, S.band.q25, 0.22);
    x.lineWidth = 0.7; x.strokeStyle = PC.band;
    S.samples.forEach((p) => { x.globalAlpha = 0.18; x.beginPath(); p.forEach((v, h) => (h ? x.lineTo(sx(h), sy(v)) : x.moveTo(sx(h), sy(v)))); x.stroke(); });
    x.globalAlpha = 1;
    const ev = AN.every[F];
    if (ev) { x.save(); x.setLineDash([5, 4]); x.strokeStyle = PC.grey; x.lineWidth = 1.5; x.beginPath(); x.moveTo(sx(0), sy(0)); x.lineTo(sx(F), sy(ev.med)); x.stroke(); x.restore(); }
    x.strokeStyle = PC.band; x.lineWidth = 2.8; x.beginPath(); S.band.q50.forEach((v, h) => (h ? x.lineTo(sx(h), sy(v)) : x.moveTo(sx(h), sy(v)))); x.stroke();
    if (AN.actual.length > 1) { x.strokeStyle = PC.warn; x.lineWidth = 2.4; x.beginPath(); AN.actual.forEach((v, h) => (h ? x.lineTo(sx(h), sy(Math.expm1(v))) : x.moveTo(sx(h), sy(Math.expm1(v))))); x.stroke(); }
    x.beginPath(); x.arc(sx(0), sy(0), 4.5, 0, Math.PI * 2); x.fillStyle = PC.ink; x.fill();
    label(x, `${num(pv(S.band.q95[F]), dp)} (95%)`, sx(F) + 6, sy(S.band.q95[F]) + 4, PC.ink2, pngFont(12.5));
    label(x, num(pv(S.band.q50[F]), dp), sx(F) + 6, sy(S.band.q50[F]) + 4, PC.band, pngFont(13.5, 650));
    label(x, `${num(pv(S.band.q5[F]), dp)} (5%)`, sx(F) + 6, sy(S.band.q5[F]) + 4, PC.ink2, pngFont(12.5));
  }
  async function picture(R, o, doc, picks, hub) {
    if (typeof document === 'undefined') return null;
    if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) { /* draw with what is loaded */ } }
    const order = PANELS.map(([k]) => k).filter((k) => picks.includes(k) && canDraw(R, k));
    if (!order.length) return null;
    const Wd = 1200, M = 32, G = 22, full = Wd - 2 * M, half = (full - G) / 2, ph = 300;
    const rows = []; let rest = order.slice();
    for (const wide of ['now', 'paths', 'analog', 'sim']) if (rest[0] === wide) { rows.push([wide]); rest = rest.slice(1); }
    while (rest.length) { rows.push(rest.length === 1 ? [rest[0]] : [rest[0], rest[1]]); rest = rest.slice(2); }
    const headH = R.hl ? 124 : 104, footH = 64, Hh = headH + rows.length * (ph + G) + footH;
    const c = document.createElement('canvas'), sc = 2; c.width = Wd * sc; c.height = Hh * sc;
    const x = c.getContext('2d'); x.scale(sc, sc);
    x.fillStyle = PC.bg; x.fillRect(0, 0, Wd, Hh);
    const name = doc.ticker || doc.name;
    const raw = R.raw, verb = o.mode === 'whatif' ? 'If it moved' : raw > 0 ? 'rose' : raw < 0 ? 'fell' : 'was flat';
    const lv = o.measure === 'level', rvm = o.measure === 'rv', when = o.mode === 'whatif' ? '' : ` on ${mdy(R.A.days[R.t])}`;
    const title = lv ? `${o.mode === 'whatif' ? `What if ${name} stood at` : `${name} closed at`} ${fmtX(o, R.value)}${when}: a ${rankWords(R.at)} level`
      : rvm ? `${name}'s volatility over a month${o.mode === 'whatif' ? ' at' : ':'} ${fmtX(o, R.value)} a year${when}: a ${rankWords(R.at)} level`
      : o.mode === 'whatif' ? `What if ${name} moved ${fmtX(o, R.value)} in ${o.w === 1 ? 'a day' : o.w === 5 ? 'a week' : 'a month'}? A ${rankWords(R.at)} ${o.w === 1 ? 'day' : 'move'}`
      : `${name} ${verb} ${num(Math.abs(raw) * 100, 1)}%${o.w === 1 ? '' : o.w === 5 ? ' in a week' : ' in a month'}${when}: a ${rankWords(R.at)} ${o.w === 1 ? 'day' : 'move'}`;
    x.fillStyle = PC.ink; x.font = pngFont(27, 650); x.fillText(title, M, 46);
    x.fillStyle = PC.muted; x.font = pngFont(14.5);
    x.fillText(`${doc.name || name}${doc.members ? ` · equal-weighted, ${num(doc.members)} companies` : ''} · ${what(o)}${o.measure === 'raw' || o.measure === 'level' || o.measure === 'rv' ? '' : ', ' + measureName(o, doc.kind)}${R.out ? ` · then: ${R.out}` : ''} · ranked among ${num(R.n)} since ${mdy(R.A.days[0])} · days like it: within ±${fb(o.band)} percentile points`, M, 74);
    if (R.hl) {                                              // older days counting less: say so, and what the dashed lines are
      x.fillStyle = PC.band; x.font = pngFont(14.5, 600);
      x.fillText(`Older days count less: a day's weight halves ${hlWords(R.hl)} away from ${mdy(R.ref)}${R.eq ? ` (unweighted: ${rankWords(R.eq.at)})` : ''} · dashed lines: unweighted`, M, 98);
    }
    let y = headH;
    for (const row of rows) {
      row.forEach((k, i) => {
        const box = { x: M + i * (half + G), y, w: row.length === 1 ? full : half, h: ph };
        if (k === 'now') drawNow(x, box, R, o);
        else if (k === 'paths') drawPaths(x, box, R, o);
        else if (k === 'analog') drawAnalog(x, box, R, o);
        else if (k === 'sim') drawSim(x, box, R, o, doc);
        else if (k === 'back' || k === 'high') drawRecovery(x, box, R, o, k, doc);
        else if (k === 'vol') drawVol(x, box, R, o, doc);
        else drawHorizon(x, box, R, o, +k, o.set === 'ext' ? 'ext' : 'sim');
      });
      y += ph + G;
    }
    x.strokeStyle = PC.line; x.beginPath(); x.moveTo(M, Hh - footH + 8); x.lineTo(Wd - M, Hh - footH + 8); x.stroke();
    x.fillStyle = PC.muted; x.font = pngFont(12.5);
    x.fillText(`Move odds · daily closes ${mdy(R.A.days[0])} – ${mdy(doc.as_of || R.A.days[R.A.days.length - 1])}, ${['index', 'volatility'].includes(doc.kind) ? 'price only' : 'adjusted for dividends and splits'} · returns close to close after each chosen day`, M, Hh - footH + 32);
    x.fillText('What followed similar moves in the past — history, not a forecast. Not investment advice.', M, Hh - footH + 50);
    let lx = Wd - M;
    x.textAlign = 'right'; x.fillStyle = PC.ink; x.font = pngFont(19, 700); x.fillText('Filing Flows', lx, Hh - footH + 36);
    const ww = x.measureText('Filing Flows').width; x.fillStyle = PC.muted; x.font = pngFont(12.5); x.fillText('filing-flows.com', lx, Hh - footH + 53); x.textAlign = 'left';
    try {                                                    // the logo, when the site's icon loads
      const img = await new Promise((ok, bad) => { const im = new Image(); im.onload = () => ok(im); im.onerror = bad; im.src = (hub || '') + '../favicon.svg'; setTimeout(bad, 2500); });
      x.drawImage(img, lx - ww - 34, Hh - footH + 16, 26, 26);
    } catch (e) { /* the wordmark alone */ }
    return c;
  }
  function pngBar(st, R) {
    const on = (k) => (st.png || []).includes(k);
    return `<div class="mv-png"><span class="mv-png-l">Picture to share (PNG):</span>${PANELS.filter(([k]) => canDraw(R, k)).map(([k, l]) => `<label><input type="checkbox" data-mvp="${k}"${on(k) ? ' checked' : ''}> ${esc(l)}</label>`).join('')}`
      + `<button type="button" class="mv-pill on" data-mvpng="1">Make the picture</button><span class="mv-sub" data-mvmsg style="margin:0"></span></div><div class="mv-png-out"></div>`;
  }

  function body(R, st, doc, news) {
    if (R.error) return `<p class="mv-err">${esc(R.error)}</p>`;
    const which = st.set === 'ext' ? 'ext' : 'sim';
    let h = headline(R, st, doc) + weightNote(R, st) + cards(R, st) + pngBar(st, R);
    h += `<h3>Where it ranks</h3><p class="mv-sub">Every ${esc(what(st))} ${st.measure === 'raw' || st.measure === 'level' || st.measure === 'rv' ? '' : esc(measureName(st, doc.kind)) + ' '}on file. The coloured bars are the ${st.measure === 'level' || st.measure === 'rv' ? 'days' : 'moves'} at least as ${R.side > 0 ? 'high' : 'low'}; the dashed line is the one looked at.${st.before && st.mode === 'date' ? ' Only the days up to it are counted.' : ''}</p>${rankSvg(R, st)}`;
    h += `<h3>What came next${R.out ? ` for ${esc(R.out)}` : ''}</h3><p class="mv-sub">${R.out ? `${esc(R.out)}'s close-to-close returns from each day:` : 'Close-to-close returns from the day of each move:'} after the days whose ${st.measure === 'level' ? 'level' : st.measure === 'rv' ? 'volatility' : 'move'} ranked within ±${fb(st.band)} percentile points of this one, after the days at least as ${R.side > 0 ? 'high' : 'low'}, and after every day. An episode groups chosen days that fall within the horizon of each other: they are the independent tries, and what "within chance" is judged on.${R.hl ? ` With older days counting less, the medians, shares and ranges are weighted; ≈ is how many days of full weight the days are worth, and the episodes are scaled by it.` : ''}</p>`;
    h += nextTable(R, st);
    h += `<div class="mv-bar"><div><label>Distribution</label><div class="mv-pills">${H.map(([hz, l]) => `<button type="button" class="mv-pill${st.h === hz ? ' on' : ''}" data-mv="h" data-v="${hz}">${esc(l)}</button>`).join('')}</div></div>`
      + `<div><label>Compared with every day</label><div class="mv-pills"><button type="button" class="mv-pill${which === 'sim' ? ' on' : ''}" data-mv="set" data-v="sim">days like it</button><button type="button" class="mv-pill${which === 'ext' ? ' on' : ''}" data-mv="set" data-v="ext">at least as ${R.side > 0 ? 'high' : 'low'}</button></div></div></div>`;
    h += nextSvg(R, st, st.h, which) + `<div class="mv-legend"><span><b style="background:${COL.up};opacity:.6"></b><b style="background:${COL.down};opacity:.6"></b>after the ${which === 'sim' ? 'days like it' : 'more extreme days'} (share of those days)</span><span><b style="background:none;border:1.5px solid ${COL.ink}"></b>after every day</span>${R.eq ? `<span><b style="background:none;border-top:2px dashed ${COL.band};height:0"></b>${which === 'sim' ? 'days like it' : 'the more extreme days'}, unweighted</span>` : ''}${fin(R.actual[st.h]) ? `<span><b style="background:${COL.warn}"></b>what happened after this day</span>` : ''}</div>`;
    h += casesSection(R, st, doc, news);
    h += analogSection(R, st, doc);
    h += recoverySection(R, st, doc);
    h += volSection(R, st, doc);
    h += `<h3>When ${st.measure === 'level' ? 'levels' : st.measure === 'rv' ? 'volatility' : 'moves'} like this happened</h3><p class="mv-sub">Every ${esc(what(st))} over time; the coloured dots are the days like this one (larger) and the days at least as ${R.side > 0 ? 'high' : 'low'}. Big moves come in clusters, in volatile years.</p>${timeSvg(R, st)}`;
    h += `<details class="mv-apx"><summary>How this is worked out</summary>`
      + `<p><b>The move.</b> The close-to-close change over one day, a week (5 trading days) or a month (21), on prices adjusted for dividends and splits (the indices: price only). Measured against its own volatility, it is divided by the standard deviation of the 63 daily returns before the move began (scaled to its length), so a 3% day counts for more in a calm stretch than in a wild one. Beyond the market, it is the move less beta times the S&P 500's move over the same days, beta from the year of daily returns before it.</p>`
      + `<p><b>The percentile.</b> Its mid-rank among every move of the same length on file: 2.5 means 2.5% of moves were lower. "Days like it" are those within the chosen number of percentile points of it; "at least as high / low" those as far out or further on the same side.</p>`
      + `<p><b>What came next.</b> The returns over the next 1, 5, 10 and 21 trading days from the close of each chosen day. Moves longer than a day overlap, and big days cluster, so neighbouring days are not independent tries: the episodes count each cluster once, and "better / worse than usual" asks whether the mean differs from every day's by more than twice its standard error over the episodes. With "only before that day", a past day is judged only on the history known then.</p>`
      + `<p><b>Similar stretches.</b> The path of log closes over the last 1, 3 or 6 months or year is set against every stretch as long in the asset's history that ended, with the months after it, before that one began: the gap is the root mean square distance between the two paths from their first day (size and shape), or between the two paths each less its mean over its spread (shape only, so a calm year can match a wild one). The closest, no two overlapping, are the stretches like it; "r" is the correlation of the two paths. What to expect is their average path after (weighted when older days count less), against every stretch's.</p>`
      + `<p><b>The simulation.</b> ${num(SIMS)} paths over the months ahead, each built a week (five trading days in a row) at a time: for each week, one of the stretches like it is drawn at random (by weight, when older days count less) and then any week of the months after it. Their weeks are mixed into many more paths than the few analogs alone, and an odd week (a crash in one of them) spreads over every day ahead rather than falling on the day it came. The bands are the 25–75% and 5–95% of the paths at each day; a past day is simulated only from the stretches before it, and what happened is drawn in orange. Seeded, so the same day gives the same paths.</p>`
      + `<p><b>How long it took.</b> From each chosen day, the trading days until the close was back at the close before the move (for a rise: back down to it), and until it was back at the highest close on file up to that day. Days still waiting on the last day on file count for as long as they were watched (the Kaplan–Meier estimate), so recent days do not look like failures; "not back on file" counts them.</p>`
      + `<p><b>Older days counting less.</b> Markets change, so the recent past may say more. With a half-life of 5 years, a day 5 years from the one looked at counts half as much, 10 years a quarter, 20 years a sixteenth. Every number is then weighted: the percentile (the share of weight below the move), the days like it (within the band of weighted percentiles), the medians, shares and ranges of what followed, how long it took (a weighted Kaplan–Meier) and the volatility after. "Worth ≈" is how many days of full weight the weights add up to, (Σw)² / Σw²: the fewer, the noisier. The dashed lines and "unweighted" figures count every day the same.</p>`
      + `<p><b>Limits.</b> Each company's and ETF's daily history from its first trading day on file (1962 for the oldest), the S&P 500 index from 1928. Industry composites are equal-weighted and hold today's companies only, which flatters their past. History rhymes rather than repeats; this describes what followed, it does not forecast. Not investment advice.</p></details>`;
    return h;
  }

  async function render(el, opts) {
    if (!el) return;
    css();
    opts = opts || {};
    const hub = opts.hub != null ? opts.hub : (HERE || '');
    const home = opts.key ? tk(opts.key) : tk(opts.ticker);
    const here = typeof opts.here === 'function' ? opts.here : () => true;
    if (!home) { el.innerHTML = '<p class="mv-sub">No ticker for this company.</p>'; return; }
    const url = (k) => `${hub}data/research/paths/moves/a/${encodeURIComponent(k)}.json`;
    el.innerHTML = '<p class="mv-sub">Loading the daily history…</p>';
    let homeDoc;
    try { homeDoc = await get(url(home)); } catch (e) {
      if (here()) el.innerHTML = `<p class="mv-sub">No daily price history for ${esc(home)} yet: it is collected for the valued companies, the market, its sectors and industries (refreshed after every US close).</p>`;
      return;
    }
    const st = Object.assign({ key: home, w: 1, measure: homeDoc.kind === 'volatility' ? 'level' : 'raw', mode: 'latest', date: '', whatif: '', band: 2.5, before: false,
      h: 21, set: 'sim', rk: 'back', outcome: 'spx', vreg: 'any', hl: 0, alen: 63, afwd: 63, ak: 10, amatch: 'size', png: ['now', 'paths', '5', '21', '63', 'back'] }, opts.state || {});
    const egOf = (m) => (m === 'vol' ? -3 : m === 'level' ? 30 : m === 'rv' ? 60 : -5);
    const docs = { [home]: homeDoc }, dec = {};
    const assets = [[home, homeDoc.kind === 'stock' ? homeDoc.ticker || home : homeDoc.name, homeDoc.kind === 'stock' ? 'this company' : homeDoc.kind]];
    const ln = homeDoc.links || {};
    if (ln.industry) assets.push([ln.industry, null, 'its industry']);
    if (ln.sector) assets.push([ln.sector, null, 'its sector']);
    if (ln.market && ln.market !== home) assets.push([ln.market, 'S&P 500 (SPY)', 'the market']);
    const draw = async () => {
      if (!here()) return;
      let doc = docs[st.key];
      if (!doc) { try { doc = docs[st.key] = await get(url(st.key)); } catch (e) { doc = null; } }
      if (!here()) return;
      if (!doc) { st.key = home; doc = homeDoc; }
      const A = dec[st.key] || (dec[st.key] = Object.assign(decode(doc), { last: doc.last }));
      const volIdx = doc.kind === 'volatility';
      if (volIdx && !['level', 'raw'].includes(st.measure)) st.measure = 'level';
      if (!volIdx && st.measure === 'level') st.measure = 'raw';
      if (st.measure === 'beta' && (doc.key === 'SPY' || doc.kind === 'index' || doc.kind === 'market')) st.measure = 'raw';
      const load = async (k) => { try { const m = docs[k] || (docs[k] = await get(url(k))); return dec[k] || (dec[k] = Object.assign(decode(m), { last: m.last, name: m.name })); } catch (e) { return null; } };
      let Mk = null, Out = null, Vix = null;
      if (st.measure === 'beta') { Mk = await load('SPY'); if (!Mk) st.measure = 'raw'; }
      if (volIdx && st.outcome !== 'self' && doc.links && doc.links.outcome) Out = await load(doc.links.outcome);
      if (!volIdx && (doc.kind === 'market' || (doc.kind === 'index' && (!doc.group || doc.group === 'us')))) Vix = await load('IDX-VIX');      // the S&P 500's implied next to US realized
      if (!here()) return;
      st.narrow = (el.clientWidth || 800) < 600;
      const R = analyze(A, st, Mk, Out);
      R.vix = Vix;
      R.volIdx = volIdx;
      if (R.hl && !R.error) { const E = analyze(A, Object.assign({}, st, { hl: 0 }), Mk, Out); if (!E.error) R.eq = E; }   // every day the same, to compare
      if (!R.error) {                                   // similar stretches and the simulation from what followed them
        R.an = analogs(R, st);
        if (!R.an.error && R.an.items.length) R.an.sim = simulate(R.an, SIMS, seedOf(`${st.key}|${R.A.days[R.an.t]}|${R.an.L}|${R.an.F}|${R.an.K}|${st.amatch}|${st.hl}`));
      }
      const names = assets.map(([k, l, role]) => [k, l || (homeDoc.names || {})[k] || (docs[k] && docs[k].name) || k, role]);
      let h = '<div class="mv">';
      if (names.length > 1) h += `<div class="mv-assets" role="group" aria-label="What to look at">${names.map(([k, l, role]) => `<button type="button" class="mv-asset${k === st.key ? ' on' : ''}" data-mva="${esc(k)}"><small>${esc(role)}</small>${esc(l)}</button>`).join('')}</div>`;
      h += `<p class="mv-sub">${esc(doc.name || doc.key)} · daily closes ${esc(mdy(doc.d0))} – ${esc(mdy(doc.as_of))}${doc.members ? ` · equal-weighted, ${num(doc.members)} companies` : ''}${doc.kind === 'index' ? (doc.group === 'world' ? ' · price only, in its own currency' : ' · price only') : ''}</p>`;
      let news = null;
      if (doc.kind === 'stock') { try { news = await get(`${hub}data/research/paths/moves/n/${encodeURIComponent(st.key)}.json`); } catch (e) { news = null; } }
      if (!here()) return;
      h += controls(st, doc) + body(R, st, doc, news) + '</div>';
      el.innerHTML = h;
      el.querySelectorAll('[data-mva]').forEach((b) => { b.onclick = () => { st.key = b.dataset.mva; if (st.mode === 'whatif') st.whatif = egOf(st.measure); draw(); }; });
      el.querySelectorAll('[data-mv]').forEach((b) => {
        b.onclick = () => {
          const k = b.dataset.mv, v = b.dataset.v;
          st[k] = ['w', 'h', 'band', 'hl', 'alen', 'afwd', 'ak'].includes(k) ? +v : k === 'before' ? v === '1' : v;
          if (k === 'mode' && v === 'date' && !st.date) st.date = (dec[st.key] || A).days[Math.max(0, (dec[st.key] || A).days.length - 22)];
          if (k === 'mode' && v === 'whatif' && !fin(st.whatif)) st.whatif = egOf(st.measure);
          if (k === 'measure' && st.mode === 'whatif') st.whatif = egOf(v);
          draw();
        };
      });
      el.querySelectorAll('[data-mvin]').forEach((inp) => { inp.onchange = () => { st[inp.dataset.mvin] = inp.value; draw(); }; });
      const rg = el.querySelector('[data-mvband]'), rl = el.querySelector('[data-mvbl]');
      if (rg) {
        rg.oninput = () => { if (rl) rl.textContent = '±' + fb(rg.value); };
        rg.onchange = () => { st.band = Math.round(+rg.value * 10) / 10; draw(); };
      }
      el.querySelectorAll('[data-mvp]').forEach((cb) => { cb.onchange = () => { const k = cb.dataset.mvp; st.png = PANELS.map(([q]) => q).filter((q) => (q === k ? cb.checked : st.png.includes(q))); }; });
      const mk = el.querySelector('[data-mvpng]'), out = el.querySelector('.mv-png-out'), msg = el.querySelector('[data-mvmsg]');
      if (mk && out && !R.error) mk.onclick = async () => {
        if (!st.png.length) { if (msg) msg.textContent = 'Pick at least one panel.'; return; }
        if (msg) msg.textContent = 'Drawing…';
        try {
          const c = await picture(R, st, doc, st.png, hub);
          const blob = c && await new Promise((res) => c.toBlob(res, 'image/png'));
          if (!blob) throw new Error('the picture could not be made');
          const href = URL.createObjectURL(blob), fn = `filing-flows-move-odds-${String(doc.key).toLowerCase()}-${(st.mode === 'date' ? R.A.days[R.t] : doc.as_of) || 'today'}.png`;
          out.innerHTML = `<img alt="Move odds picture of ${esc(doc.ticker || doc.name)}" src="${href}"><div class="mv-png-acts"><a href="${href}" download="${esc(fn)}">Download PNG</a>${typeof ClipboardItem !== 'undefined' && navigator.clipboard && navigator.clipboard.write ? '<button type="button" data-mvcopy>Copy image</button>' : ''}<button type="button" data-mvclose>Close</button></div>`;
          if (msg) msg.textContent = '';
          const cp = out.querySelector('[data-mvcopy]');
          if (cp) cp.onclick = async () => { try { await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]); cp.textContent = 'Copied'; } catch (e) { cp.textContent = 'Copy failed'; } };
          out.querySelector('[data-mvclose]').onclick = () => { out.innerHTML = ''; };
        } catch (e) { if (msg) msg.textContent = 'Could not draw the picture (' + e.message + ').'; }
      };
      if (typeof opts.onState === 'function') opts.onState(Object.assign({}, st));
    };
    await draw();
  }

  const api = { render, decode, cum, moves, ahead, pctOf, quantile, pctW, wquant, ageWeights, volScaled, residual, realized, volData, stats, analyze, sparse, firstAt, km, recovery, kde, picture, PANELS, canDraw, cases, expectedOf, newsIndex, casesSection, fb, analogs, simulate, rng32, seedOf };
  if (typeof window !== 'undefined') window.MovesView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
