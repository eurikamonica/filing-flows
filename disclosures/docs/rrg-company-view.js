/* Rotation (RRG) — one company's two Relative Rotation Graphs on its own page: against the S&P 500 (SPY) and against
   its industry without itself (the dual RRG's second layer), each with
   · the price that moves it next week: the close at which RS-Ratio and RS-Momentum cross 100, solved exactly from the
     chart's formula (the benchmark held flat), so every quadrant becomes a price interval;
   · the replayed ranges: every 13-week run of the stock's weekly moves against the benchmark in the last 156 weeks,
     replayed from today's state through the same formula — the trajectory fan on the chart and the price and position
     ranges 1, 4 and 13 weeks on, each with the coverage it reached walk-forward since 2012 (transition_rrg.band_check);
   · the Markov matrix: quadrant-to-quadrant shares h weeks on, smoothed, fitted on every pair whose outcome is known
     (by the industry's quadrant for the industry chart), with the label it earned out of sample;
   · the dynamic transition model: the weekly chain over (quadrant, direction of the last step) — (industry quadrant,
     company quadrant) for the industry chart — stepped week by week: each quadrant's probability for weeks 1–13 and the
     most common paths.
   Data: data/market/history/rrg.json, t/<T>.json, rrg-transition-model.json (branch rotation-history). Self-contained:
   used by the main site's company page (views.json) with colours from the host's CSS variables.
   window.RRGCompanyView.render(el, {ticker, hub}). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? '$' + num(v, v >= 1000 ? 0 : v >= 1 ? 2 : 4) : '—');
  const pc = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spc = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const QN = ['Leading', 'Weakening', 'Lagging', 'Improving'];
  const QC = ['var(--mk-profit, #17734a)', 'var(--q-warm, #c98a00)', 'var(--mk-cost, #d4553c)', 'var(--slate, #5b7fa6)'];
  const LBL = { calibrated: ['Calibrated', 'beat both baselines out of sample, intervals above zero, calibration error at most 2 points'],
    experimental: ['Experimental', 'beat both baselines out of sample, but an interval touches zero or the calibration error is above 2 points'],
    descriptive_only: ['History only', 'did not beat a baseline out of sample: history, not a forecast'],
    insufficient_data: ['Too little data', 'fewer than 50 test origins or 2,000 test predictions'] };
  const BLBL = { calibrated: ['Calibrated', 'the 80% and 50% ranges held 77–83% and 47–53% of outcomes walk-forward since 2012'],
    experimental: ['Experimental', 'the ranges held more or less than nominal walk-forward: read the coverage beside them'],
    insufficient_data: ['Too little data', 'too few test weeks'] };
  const shown = (l) => l === 'calibrated' || l === 'experimental';
  const H = [1, 4, 13];
  const store = {};
  const get = (url) => store[url] || (store[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .catch((e) => { delete store[url]; throw e; }));
  const ui = {};                                        // per page: horizon, tail
  let CLIP = 0;

  function css() {
    if (typeof document === 'undefined' || document.getElementById('rc-css')) return;
    const s = document.createElement('style'); s.id = 'rc-css';
    s.textContent = `.rc h3{margin:24px 0 4px;font-size:17px}.rc h4{margin:16px 0 4px;font-size:14px}.rc .rc-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.5;max-width:82ch}
.rc svg{display:block;width:100%;height:auto}.rc .rc-chart{max-width:820px}.rc .rc-ax{stroke:var(--muted,#888);stroke-width:1}.rc .rc-grid{stroke:var(--line,#e3e3e3)}
.rc .rc-t{fill:var(--muted,#777);font-size:11px}.rc .rc-l{fill:var(--ink,#222);font-size:12px;font-weight:600;paint-order:stroke;stroke:var(--surface,#fff);stroke-width:3px}
.rc .rc-q{font-size:13px;font-weight:600}.rc-ctl{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 4px;align-items:center;font-size:12px;color:var(--muted,#777)}
.rc-tog{font:inherit;font-size:12px;border:1px solid var(--line,#ddd);background:none;border-radius:8px;padding:3px 9px;cursor:pointer;color:var(--muted,#666)}.rc-tog.on{color:var(--ink,#222);border-color:var(--ink,#222);font-weight:600}
.rc-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.rc-tbl th,.rc-tbl td{padding:5px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.rc-tbl td.n,.rc-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.rc-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}.rc-tbl tr.on td{background:color-mix(in srgb,var(--accent,#17734a) 10%,transparent);font-weight:600}
.rc-wrap{overflow-x:auto}.rc-tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line,#ddd);white-space:nowrap}
.rc-tag.calibrated{border-color:var(--accent,#17734a);color:var(--accent,#17734a)}.rc-tag.experimental{border-color:var(--slate,#5b7fa6);color:var(--slate,#5b7fa6)}
.rc-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin:6px 0 8px}.rc-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 10px}
.rc-card span{display:block;font-size:12px;color:var(--muted,#777)}.rc-card b{font-size:18px;font-variant-numeric:tabular-nums}.rc-card i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777)}
.rc-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.rc-legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.rc-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:12px;max-width:90ch}.rc-sec{border-top:1px solid var(--line,#e5e5e5);margin-top:22px;padding-top:4px}`;
    document.head.appendChild(s);
  }

  /* ---------- the weekly grid and the RRG formula (transition_rrg.rrg_states, rrg.js rrgCalc) ---------- */
  function grid(D) {
    const t0 = Date.parse(D.start + 'T00:00:00Z'), n = Math.round((Date.parse(D.weeks + 'T00:00:00Z') - t0) / 6048e5) + 1;
    return { t0, n, days: Array.from({ length: n }, (_, i) => new Date(t0 + i * 6048e5).toISOString().slice(0, 10)) };
  }
  function place(G, start, arr, scale = 1) {
    const a = new Array(G.n).fill(NaN), o = Math.round((Date.parse(start + 'T00:00:00Z') - G.t0) / 6048e5);
    (arr || []).forEach((v, i) => { if (o + i >= 0 && o + i < G.n && v != null) a[o + i] = v * scale; });
    return a;
  }
  const ratio = (A, B) => A.map((v, i) => (Number.isFinite(v) && Number.isFinite(B[i]) && B[i] > 0 && v > 0 ? 100 * v / B[i] : NaN));
  function ema(a, span) {
    const al = 2 / (span + 1), need = Math.min(span, 6), out = new Array(a.length).fill(NaN);
    let m = 0, c = 0;
    for (let i = 0; i < a.length; i++) {
      if (!Number.isFinite(a[i])) { m = 0; c = 0; continue; }
      m = c === 0 ? a[i] : m + al * (a[i] - m); c++;
      if (c >= need) out[i] = m;
    }
    return out;
  }
  function states(rs, n = 14) {
    const sh = 4, long = Math.max(52, 3 * n);
    const s = ema(rs, sh), t = ema(s, n);
    const dev = s.map((v, i) => (Number.isFinite(v) && Number.isFinite(t[i]) && t[i] !== 0 ? 100 * (v / t[i] - 1) : NaN));
    const roc = ema(dev.map((v, i) => (i && Number.isFinite(v) && Number.isFinite(dev[i - 1]) ? v - dev[i - 1] : NaN)), sh);
    const norm = (A) => A.map((v, k) => {
      if (!Number.isFinite(v)) return NaN;
      let s2 = 0, m = 0;
      for (let i = Math.max(0, k - long + 1); i <= k; i++) if (Number.isFinite(A[i])) { s2 += A[i] * A[i]; m++; }
      return m >= Math.min(long, 26) && s2 > 0 ? 100 + v / Math.sqrt(s2 / m) : NaN;
    });
    const x = norm(dev), y = norm(roc).map((v, i) => (Number.isFinite(x[i]) ? v : NaN));
    return { s, t, dev, roc, x, y, sh, n, long };
  }
  const quad = (x, y) => (x >= 100 ? (y >= 100 ? 0 : 1) : (y < 100 ? 2 : 3));
  // paths of weekly relative log moves P[path][step] stepped forward from week k (transition_rrg.step_paths)
  function stepPaths(S, rel, k, P) {
    const a1 = 2 / (S.sh + 1), a2 = 2 / (S.n + 1), L = S.long;
    const tail = (A, j) => { let s2 = 0, m = 0; for (let i = Math.max(0, k - L + 1 + j); i <= k; i++) if (Number.isFinite(A[i])) { s2 += A[i] * A[i]; m++; } return [s2, m]; };
    const TD = [], TR = [];
    for (let j = 1; j <= 13; j++) { TD[j] = tail(S.dev, j); TR[j] = tail(S.roc, j); }
    return P.map((p) => {
      let s = S.s[k], t = S.t[k], roc = S.roc[k], dprev = S.dev[k], c = 0, dq = 0, rq = 0;
      const out = { cum: [], x: [], y: [] };
      p.forEach((r, j) => {
        c += r;
        const rs = rel[k] * Math.exp(c);
        s += a1 * (rs - s); t += a2 * (s - t);
        const dev = 100 * (s / t - 1);
        roc += a1 * ((dev - dprev) - roc); dprev = dev;
        dq += dev * dev; rq += roc * roc;
        const [bd, nd] = TD[j + 1], [br, nr] = TR[j + 1], md = nd + j + 1, mr = nr + j + 1;
        out.cum.push(c);
        out.x.push(md >= Math.min(L, 26) && bd + dq > 0 ? 100 + dev / Math.sqrt((bd + dq) / md) : NaN);
        out.y.push(mr >= Math.min(L, 26) && br + rq > 0 ? 100 + roc / Math.sqrt((br + rq) / mr) : NaN);
      });
      return out;
    });
  }
  // every 13-week run of weekly relative moves in the 156 weeks to k (transition_rrg.replay)
  function replay(S, rel, k, window = 156, steps = 13) {
    const LR = rel.map((v, i) => (i && Number.isFinite(v) && Number.isFinite(rel[i - 1]) ? Math.log(v / rel[i - 1]) : NaN));
    const P = [];
    for (let st = k - window + 1; st <= k - steps + 1; st++) {
      if (st < 1) continue;
      const p = LR.slice(st, st + steps);
      if (p.length === steps && p.every(Number.isFinite)) P.push(p);
    }
    return P.length ? stepPaths(S, rel, k, P) : [];
  }
  // next week's relative level at which RS-Ratio (dev = 0) and RS-Momentum (roc = 0) cross 100: exact from the formula
  function thresholds(S, rel, k) {
    const a1 = 2 / (S.sh + 1), a2 = 2 / (S.n + 1), s = S.s[k], t = S.t[k];
    const rsFor = (g) => { const s1 = g * t * (1 - a2) / (1 - g * a2); return s + (s1 - s) / a1; };   // s'/t' = g
    const gx = 1, gy = 1 + (S.dev[k] + S.roc[k] * (1 - 1 / a1)) / 100;
    const mx = rsFor(gx) / rel[k], my = gy * a2 < 1 ? rsFor(gy) / rel[k] : NaN;
    return { mx: mx > 0 ? mx : NaN, my: my > 0 ? my : NaN };
  }
  const qtl = (a, p) => { const s = a.filter(Number.isFinite).sort((u, v) => u - v); if (!s.length) return NaN; const i = (s.length - 1) * p, lo = Math.floor(i); return s[lo] + (s[Math.min(s.length - 1, lo + 1)] - s[lo]) * (i - lo); };

  /* ---------- the Markov matrix and the weekly chain (transition_rrg, rrg-odds.js) ---------- */
  function odds(M, g, st, h) {
    const G = M.groups && M.groups[g]; if (!G) return null;
    const head = G.primary === 'iq' && st.iq >= 0 ? 'iq' : 'q', X = (G.heads[head] || {})[h]; if (!X) return null;
    const row = head === 'iq' ? 4 * st.iq + st.q : st.q, cnt = X.counts[row] || [], n = cnt.reduce((a, b) => a + b, 0);
    return { head, label: X.label, ev: X.eval || {}, p: X.P[row], hist: n ? cnt.map((v) => v / n) : null, n, X, rows: head === 'iq' ? [0, 1, 2, 3].map((q) => 4 * st.iq + q) : [0, 1, 2, 3] };
  }
  function rng(seed) { let a = seed >>> 0; return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function chain(M, g, st, sims = 20000) {
    const G = M.groups && M.groups[g]; if (!G || !G.chain) return null;
    const joint = G.chain.joint, s0 = joint ? (st.iq >= 0 ? 4 * st.iq + st.q : -1) : (st.hd >= 0 ? 4 * st.q + st.hd : -1);
    if (s0 < 0) return null;
    const P = G.chain.P1.map((r) => { const t = r.reduce((a, b) => a + b, 0); return r.map((v) => v / t); }), qof = (s) => (joint ? s % 4 : Math.floor(s / 4));
    let v = new Array(16).fill(0); v[s0] = 1; const marg = [];
    for (let k = 1; k <= 13; k++) {
      const w = new Array(16).fill(0); for (let i = 0; i < 16; i++) if (v[i]) for (let j = 0; j < 16; j++) w[j] += v[i] * P[i][j];
      v = w; const q = [0, 0, 0, 0]; w.forEach((p, j) => { q[qof(j)] += p; }); marg.push(q);
    }
    const cum = P.map((r) => { let c = 0; return r.map((p) => (c += p)); }), rnd = rng(20261023 + s0), cnt = new Map();
    for (let n = 0; n < sims; n++) {
      let s = s0; const seq = [qof(s)];
      for (let k = 0; k < 13; k++) { const u = rnd(), c = cum[s]; let j = 0; while (j < 15 && u > c[j]) j++; s = j; if (qof(s) !== seq[seq.length - 1]) seq.push(qof(s)); }
      const key = seq.join(''); cnt.set(key, (cnt.get(key) || 0) + 1);
    }
    const lab = (k) => G.chain.labels[k <= 1 ? '1' : k <= 4 ? '4' : '13'];
    return { marg, labels: marg.map((_, i) => lab(i + 1)), pathLabel: lab(13), joint,
      paths: [...cnt.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, c]) => ({ q: [...k].map(Number), p: c / sims })) };
  }

  /* ---------- one line, one benchmark: everything the section draws ---------- */
  function analyse(G, C, V, B, opt) {
    const rel = ratio(C, B), S = states(rel);
    let k = S.x.length - 1; while (k >= 0 && !(Number.isFinite(S.x[k]) && Number.isFinite(S.y[k]))) k--;
    if (k < 1) return null;
    const hd = Number.isFinite(S.x[k - 1]) ? (S.x[k] - S.x[k - 1] >= 0 ? (S.y[k] - S.y[k - 1] >= 0 ? 0 : 1) : (S.y[k] - S.y[k - 1] < 0 ? 2 : 3)) : -1;
    let iq = -1;
    if (opt.IND) { const I = states(opt.IND); if (Number.isFinite(I.x[k]) && Number.isFinite(I.y[k])) iq = quad(I.x[k], I.y[k]); }
    let liquid = !!opt.always;                           // transition_rrg.liquid: ≥ $3 and ≥ $10M a week over 13 weeks
    if (V && !opt.always) { let s = 0, m = 0; for (let j = Math.max(0, k - 12); j <= k; j++) if (Number.isFinite(C[j]) && Number.isFinite(V[j])) { s += C[j] * V[j]; m++; } liquid = C[k] >= 3 && m >= 10 && s / m >= 10e6; }
    const paths = replay(S, rel, k), th = thresholds(S, rel, k);
    return { rel, S, k, close: C[k], st: { q: quad(S.x[k], S.y[k]), hd, iq }, liquid, paths, th, day: G.days[k] };
  }

  /* ---------- drawing ---------- */
  function chart(A, o) {
    const W = o.W || 760, Hh = Math.max(300, Math.round(W * 0.66)), Lm = W < 500 ? 40 : 50, R = 10, T = 14, Bm = 40, S = A.S, k = A.k, tail = o.tail;
    const pts = [];
    for (let i = Math.max(0, k - tail + 1); i <= k; i++) if (Number.isFinite(S.x[i])) pts.push([S.x[i], S.y[i], i]);
    const ctx = o.ctx ? (() => { const r = []; for (let i = Math.max(0, k - tail + 1); i <= k; i++) if (Number.isFinite(o.ctx.x[i])) r.push([o.ctx.x[i], o.ctx.y[i]]); return r; })() : [];
    const fx = [], fy = [];
    A.paths.forEach((p) => p.x.forEach((v, j) => { if (Number.isFinite(v) && Number.isFinite(p.y[j])) { fx.push(v); fy.push(p.y[j]); } }));
    const xs = pts.map((p) => p[0]).concat(ctx.map((p) => p[0]), [qtl(fx, 0.03), qtl(fx, 0.97)]).filter(Number.isFinite);
    const ys = pts.map((p) => p[1]).concat(ctx.map((p) => p[1]), [qtl(fy, 0.03), qtl(fy, 0.97)]).filter(Number.isFinite);
    const mx = Math.max(1.5, ...xs.map((v) => Math.abs(v - 100))) * 1.08, my = Math.max(1.5, ...ys.map((v) => Math.abs(v - 100))) * 1.08;
    const sx = (v) => Lm + (v - (100 - mx)) / (2 * mx) * (W - Lm - R);       // unclamped: the plot area clips
    const sy = (v) => T + ((100 + my) - v) / (2 * my) * (Hh - T - Bm);
    const clip = 'rc-clip-' + (++CLIP);
    const X0 = sx(100), Y0 = sy(100), f = (v) => v.toFixed(1);
    let s = `<svg class="rc-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(o.title)}"><defs><clipPath id="${clip}"><rect x="${Lm}" y="${T}" width="${W - R - Lm}" height="${Hh - Bm - T}"/></clipPath></defs>`;
    const fill = (x, y, w, h, c) => `<rect x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h)}" style="fill:${c};opacity:.08"/>`;
    s += fill(X0, T, W - R - X0, Y0 - T, QC[0]) + fill(X0, Y0, W - R - X0, Hh - Bm - Y0, QC[1]) + fill(Lm, Y0, X0 - Lm, Hh - Bm - Y0, QC[2]) + fill(Lm, T, X0 - Lm, Y0 - T, QC[3]);
    const ticks = (lo, hi) => { const st = (hi - lo) / 6, p = Math.pow(10, Math.floor(Math.log10(st))), u = [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= st) || st; const r = []; for (let v = Math.ceil(lo / u) * u; v <= hi; v += u) r.push(+v.toFixed(6)); return r; };
    ticks(100 - mx, 100 + mx).forEach((v) => { s += `<line class="rc-grid" x1="${f(sx(v))}" x2="${f(sx(v))}" y1="${T}" y2="${Hh - Bm}"/><text class="rc-t" x="${f(sx(v))}" y="${Hh - Bm + 15}" text-anchor="middle">${num(v, 1)}</text>`; });
    ticks(100 - my, 100 + my).forEach((v) => { s += `<line class="rc-grid" x1="${Lm}" x2="${W - R}" y1="${f(sy(v))}" y2="${f(sy(v))}"/><text class="rc-t" x="${Lm - 6}" y="${f(sy(v) + 4)}" text-anchor="end">${num(v, 1)}</text>`; });
    s += `<line class="rc-ax" x1="${f(X0)}" x2="${f(X0)}" y1="${T}" y2="${Hh - Bm}"/><line class="rc-ax" x1="${Lm}" x2="${W - R}" y1="${f(Y0)}" y2="${f(Y0)}"/>`;
    s += `<text class="rc-t" x="${(Lm + W - R) / 2}" y="${Hh - 6}" text-anchor="middle">RS-Ratio → (relative trend vs ${esc(o.bench)})</text><text class="rc-t" transform="translate(12 ${(T + Hh - Bm) / 2}) rotate(-90)" text-anchor="middle">RS-Momentum →</text>`;
    // quadrant names, and the Markov odds h weeks on in each corner
    const corner = [[W - R - 8, T + 16, 'end'], [W - R - 8, Hh - Bm - 10, 'end'], [Lm + 8, Hh - Bm - 10, 'start'], [Lm + 8, T + 16, 'start']];
    corner.forEach(([x, y, an], q) => {
      const d = o.odds, show = d && shown(d.label) && A.liquid, v = d ? (show ? d.p[q] : d.hist && d.hist[q]) : null;
      const line = d && fin(v) ? (show ? ` · ${pc(v)} in ${o.h} wk` : ` · ${pc(v)} hist.`) : '';
      s += `<text class="rc-q" x="${x}" y="${y}" text-anchor="${an}" style="fill:${QC[q]}">${QN[q]}${esc(line)}</text>`;
    });
    // the replays: every path faint, the median path dashed, the 80% box at 4 and 13 weeks
    const P = A.paths, p0 = [sx(S.x[k]), sy(S.y[k])];
    s += `<g clip-path="url(#${clip})">`;
    P.forEach((p) => { const d = [p0].concat(p.x.map((v, j) => [sx(v), sy(p.y[j])]).filter((q) => Number.isFinite(q[0]) && Number.isFinite(q[1]))); s += `<path d="M${d.map((q) => f(q[0]) + ',' + f(q[1])).join('L')}" style="fill:none;stroke:${o.col};stroke-width:.7;opacity:.12"/>`; });
    if (P.length) {
      const med = [p0]; for (let j = 0; j < 13; j++) med.push([sx(qtl(P.map((p) => p.x[j]), 0.5)), sy(qtl(P.map((p) => p.y[j]), 0.5))]);
      s += `<path d="M${med.map((q) => f(q[0]) + ',' + f(q[1])).join('L')}" style="fill:none;stroke:${o.col};stroke-width:2;stroke-dasharray:6 4;opacity:.85"/>`;
      [4, 13].forEach((h) => {
        const xs1 = P.map((p) => p.x[h - 1]), ys1 = P.map((p) => p.y[h - 1]), a = [sx(qtl(xs1, 0.1)), sy(qtl(ys1, 0.9))], b = [sx(qtl(xs1, 0.9)), sy(qtl(ys1, 0.1))];
        const lx = Math.min(b[0] - 4, W - R - 6), ly = h === 4 ? Math.max(a[1] + 14, T + 30) : Math.min(b[1] - 6, Hh - Bm - 26);
        s += `<rect x="${f(a[0])}" y="${f(a[1])}" width="${f(b[0] - a[0])}" height="${f(b[1] - a[1])}" rx="6" style="fill:none;stroke:${o.col};stroke-width:1.2;stroke-dasharray:3 3;opacity:.8"/><text class="rc-l" x="${f(lx)}" y="${f(ly)}" text-anchor="end">${h} wk · 80%</text>`;
      });
    }
    s += '</g>';
    s += `<g clip-path="url(#${clip})">`;
    if (ctx.length > 1) s += `<path d="M${ctx.map((q) => f(sx(q[0])) + ',' + f(sy(q[1]))).join('L')}" style="fill:none;stroke:var(--muted,#888);stroke-width:1.5;opacity:.7"/><circle cx="${f(sx(ctx[ctx.length - 1][0]))}" cy="${f(sy(ctx[ctx.length - 1][1]))}" r="4" style="fill:var(--muted,#888)"/><text class="rc-l" x="${f(sx(ctx[ctx.length - 1][0]) + 7)}" y="${f(sy(ctx[ctx.length - 1][1]) + 4)}">${esc(o.ctxName)}</text>`;
    if (pts.length > 1) s += `<path d="M${pts.map((q) => f(sx(q[0])) + ',' + f(sy(q[1]))).join('L')}" style="fill:none;stroke:${o.col};stroke-width:2.2"/>`;
    pts.forEach((q, i) => { s += `<circle cx="${f(sx(q[0]))}" cy="${f(sy(q[1]))}" r="${i === pts.length - 1 ? 6 : 2.2}" style="fill:${o.col};opacity:${i === pts.length - 1 ? 1 : (0.3 + 0.6 * i / pts.length).toFixed(2)}"><title>${esc(A.day && i === pts.length - 1 ? 'Week of ' + A.day : '')}</title></circle>`; });
    s += `<text class="rc-l" x="${f(p0[0] + 9)}" y="${f(p0[1] - 8)}">${esc(o.name)}</text></g>`;
    return s + '</svg>';
  }
  function ladder(A, o) {                                    // next week's close and the quadrant it lands in
    const { mx, my } = A.th, c = A.close, F = o.fmt || usd, W0 = o.closeWord || 'close';
    if (!fin(mx) || !fin(my) || !fin(c)) return '<p class="rc-sub">The thresholds cannot be solved this week.</p>';
    const lo = Math.min(mx, my), hi = Math.max(mx, my), mid = mx < my ? 1 : 3;     // between: Weakening (x first) or Improving
    const span = (base, a, b, f) => (a == null ? `below ${f(base * b)}` : b == null ? `at or above ${f(base * a)}` : `${f(base * a)} – ${f(base * b)}`);
    const rows = [[2, null, lo, `under ${spc(lo - 1)}`], [mid, lo, hi, `${spc(lo - 1)} to ${spc(hi - 1)}`], [0, hi, null, `${spc(hi - 1)} or more`]];
    const mem = (o.members || []).filter((m) => fin(m.c));
    const w1 = A.paths.map((p) => p.cum[0]), r10 = Math.exp(qtl(w1, 0.1)), r90 = Math.exp(qtl(w1, 0.9));
    return `<h4>Next week — the ${esc(W0)} that puts it in each quadrant</h4><p class="rc-sub">Solved exactly from the chart's formula with ${esc(o.bench)} flat next week (a move of the benchmark shifts every price by the same %). Last ${esc(W0)} ${F(c)} (${esc(A.day)}). RS-Ratio crosses 100 at ${F(c * mx)} (${spc(mx - 1)}), RS-Momentum at ${F(c * my)} (${spc(my - 1)}). The replayed one-week range: ${F(c * r10)}–${F(c * r90)} (80%).${mem.length ? ` ${esc(o.membersWhat || '')}` : ''}</p>` +
      `<div class="rc-wrap"><table class="rc-tbl"><tr><th>Lands in</th><th class="n">${esc(W0[0].toUpperCase() + W0.slice(1))} next week</th><th class="n">Move vs ${esc(o.bench)}</th>${mem.map((m) => `<th class="n">${esc(m.t)}<br><span style="font-weight:400">now ${usd(m.c)}</span></th>`).join('')}</tr>${rows.map(([q, a, b, mv]) => `<tr${q === A.st.q ? ' class="on"' : ''}><td style="color:${QC[q]}">${QN[q]}${q === A.st.q ? ' (now)' : ''}</td><td class="n">${span(c, a, b, F)}</td><td class="n">${mv}</td>${mem.map((m) => `<td class="n">${span(m.c, a, b, usd)}</td>`).join('')}</tr>`).join('')}</table></div>`;
  }
  function ranges(A, o, B) {                                 // replayed price and position ranges, with the check
    const P = A.paths, c = A.close, F = o.fmt || usd;
    if (P.length < 30) return '<p class="rc-sub">Fewer than 30 complete 13-week runs in the last three years: no replayed ranges.</p>';
    const row = (h) => {
      const r = P.map((p) => p.cum[h - 1]), b = (B || {})[String(h)] || {}, cv = b.coverage || {};
      const q = [0.1, 0.25, 0.5, 0.75, 0.9].map((p) => Math.exp(qtl(r, p)));
      const xq = [0.1, 0.9].map((p) => qtl(P.map((x) => x.x[h - 1]), p)), yq = [0.1, 0.9].map((p) => qtl(P.map((x) => x.y[h - 1]), p));
      return `<tr><td>${h} week${h > 1 ? 's' : ''}</td>${q.map((m, i) => `<td class="n"${i === 2 ? ' style="font-weight:600"' : ''}>${F(c * m)}<br><span class="rc-t" style="font-size:11px;color:var(--muted,#888)">${spc(m - 1)}</span></td>`).join('')}<td class="n">${num(xq[0], 1)}–${num(xq[1], 1)}</td><td class="n">${num(yq[0], 1)}–${num(yq[1], 1)}</td><td><span class="rc-tag ${esc(b.label || '')}" title="${esc((BLBL[b.label] || ['', ''])[1])}">${esc((BLBL[b.label] || ['not checked'])[0])}</span><br><span style="font-size:11px;color:var(--muted,#888)">held ${pc(cv.p80)} / ${pc(cv.p50)}</span></td></tr>`;
    };
    return `<h4>Replayed ranges — price and position 1, 4 and 13 weeks on</h4><p class="rc-sub">Each of the ${P.length} 13-week runs of ${esc(o.name)}'s weekly moves against ${esc(o.bench)} in the last three years, replayed from this week through the chart's formula (the faint paths on the chart; dashed: the median path; boxes: 80% of positions). Prices assume ${esc(o.bench)} flat. “Held”: how often the actual outcome fell inside the 80% / 50% price range walk-forward since 2012 (${esc(o.kind)}${o.pct ? '' : ', liquid companies'}).</p>` +
      `<div class="rc-wrap"><table class="rc-tbl"><tr><th>Horizon</th><th class="n">10%</th><th class="n">25%</th><th class="n">Median</th><th class="n">75%</th><th class="n">90%</th><th class="n">RS-Ratio 80%</th><th class="n">RS-Momentum 80%</th><th>Check</th></tr>${H.map(row).join('')}</table></div>`;
  }
  function matrix(A, o) {
    const d = o.odds; if (!d) return '';
    const X = d.X, show = shown(d.label) && A.liquid;
    const rows = d.rows.map((r, i) => {
      const cnt = X.counts[r] || [], n = cnt.reduce((a, b) => a + b, 0), p = show ? X.P[r] : (n ? cnt.map((v) => v / n) : null);
      return `<tr${i === A.st.q ? ' class="on"' : ''}><td style="color:${QC[i]}">${QN[i]}${i === A.st.q ? ' (now)' : ''}</td>${[0, 1, 2, 3].map((j) => `<td class="n" title="${esc(num(cnt[j]) + ' of ' + num(n) + ' line-weeks')}">${p ? pc(p[j]) : '—'}</td>`).join('')}<td class="n">${num(n)}</td></tr>`;
    }).join('');
    const ev = d.ev || {}, sk = (a) => (Array.isArray(a) ? `${num(100 * a[0], 1)}% [${num(100 * a[1], 1)}, ${num(100 * a[2], 1)}]` : '—');
    return `<h4>Markov matrix — where lines in each quadrant stood ${o.h} week${o.h > 1 ? 's' : ''} later <span class="rc-tag ${esc(d.label)}" title="${esc((LBL[d.label] || ['', ''])[1])}">${esc((LBL[d.label] || [d.label])[0])}</span></h4>` +
      `<p class="rc-sub">${esc(o.matrixWhat)} Rows: now; columns: ${o.h} week${o.h > 1 ? 's' : ''} later; smoothed toward the overall shares (λ = 10). Out of sample since 2012 it beat “stays in its quadrant” by ${sk(ev.brier_skill_vs_stay)} and “the usual shares” by ${sk(ev.brier_skill_vs_freq)} (Brier score), calibration error ${fin(ev.ece) ? num(100 * ev.ece, 1) + ' points' : '—'}.${show ? '' : A.liquid ? ' Shown as history: the head did not pass its check.' : ' Shown as history: the model counts companies only while liquid ($3, $10M a week), and this one is not.'}</p>` +
      `<div class="rc-wrap"><table class="rc-tbl"><tr><th>Now ↓ · later →</th>${QN.map((q, j) => `<th class="n" style="color:${QC[j]}">${q}</th>`).join('')}<th class="n">Line-weeks</th></tr>${rows}</table></div>`;
  }
  function dynamic(A, o) {
    const ch = o.chain; if (!ch) return '<p class="rc-sub">No week-by-week path this week (its last step or its industry point is missing).</p>';
    const Wd = 640, Ht = 170, L = 34, R = 8, T = 8, B = 24, bw = (Wd - L - R) / 13;
    let s = `<svg viewBox="0 0 ${Wd} ${Ht}" style="max-width:${Wd}px" role="img" aria-label="Each quadrant's probability for weeks 1 to 13">`;
    [0, 0.5, 1].forEach((v) => { const y = T + (1 - v) * (Ht - T - B); s += `<line class="rc-grid" x1="${L}" x2="${Wd - R}" y1="${y}" y2="${y}"/><text class="rc-t" x="${L - 5}" y="${y + 4}" text-anchor="end">${pc(v)}</text>`; });
    ch.marg.forEach((q, i) => {
      const x = L + i * bw + 2; let y = Ht - B;
      if (shown(ch.labels[i]) && A.liquid) q.forEach((p, j) => { const hh = p * (Ht - T - B); y -= hh; s += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${Math.max(0, hh).toFixed(1)}" style="fill:${QC[j]};opacity:.8"><title>Week ${i + 1}: ${QN[j]} ${pc(p)}</title></rect>`; });
      else s += `<rect x="${x.toFixed(1)}" y="${T}" width="${(bw - 4).toFixed(1)}" height="${Ht - T - B}" style="fill:none;stroke:var(--line,#ddd);stroke-dasharray:3 3"/>`;
      s += `<text class="rc-t" x="${(x + bw / 2 - 2).toFixed(1)}" y="${Ht - 7}" text-anchor="middle">${i + 1}</text>`;
    });
    const lb = (l) => (LBL[l] || [l])[0];
    return `<h4>Dynamic transition model — week by week, the weekly chain</h4><p class="rc-sub">The chain steps one week at a time from ${ch.joint ? 'where the company and its industry stand together' : 'its quadrant and the direction of its last weekly step'}, so the odds change with each step (checked: week 1 ${esc(lb(ch.labels[0]))}, 2–4 ${esc(lb(ch.labels[3]))}, 5–13 ${esc(lb(ch.labels[12]))}). At 1, 4 and 13 weeks the Markov matrix above was checked on its own and is the figure to use.</p>${s}</svg>` +
      `<div class="rc-legend">${QN.map((n, j) => `<span><b style="background:${QC[j]}"></b>${n}</span>`).join('')}<span>weeks ahead →</span></div>` +
      (shown(ch.pathLabel) && A.liquid ? `<div class="rc-wrap"><table class="rc-tbl"><tr><th>Most common paths over 13 weeks (quadrants in order)</th><th class="n">Share of 20,000 simulated</th></tr>${ch.paths.map((p) => `<tr><td>${p.q.map((q) => `<span style="color:${QC[q]}">${QN[q]}</span>`).join(' → ')}${p.q.length === 1 ? ' (stays)' : ''}</td><td class="n">${pc(p.p)}</td></tr>`).join('')}</table></div>` : '<p class="rc-sub">Paths are not shown: the chain did not pass its 13-week check, or the company is below the liquidity floor.</p>');
  }
  function section(A, o) {
    if (!A) return `<div class="rc-sec"><h3>${esc(o.title)}</h3><p class="rc-sub">${esc(o.missing)}</p></div>`;
    const qn = QN[A.st.q], d = o.odds;
    const cards = `<div class="rc-cards"><div class="rc-card"><span>Now (${esc(A.day)})</span><b style="color:${QC[A.st.q]}">${qn}</b><i>RS-Ratio ${num(A.S.x[A.k], 2)} · RS-Momentum ${num(A.S.y[A.k], 2)}</i></div>` +
      (d ? `<div class="rc-card"><span>Most likely in ${o.h} week${o.h > 1 ? 's' : ''}</span>${shown(d.label) && A.liquid ? (() => { const j = d.p.indexOf(Math.max(...d.p)); return `<b style="color:${QC[j]}">${QN[j]} ${pc(d.p[j])}</b><i>${esc((LBL[d.label] || [''])[0])} (Markov matrix)</i>`; })() : `<b>—</b><i>${A.liquid ? 'history only' : 'below the liquidity floor'}</i>`}</div>` : '') +
      (() => { const m = Math.max(A.th.mx, A.th.my), ok = fin(A.th.mx) && fin(A.th.my), F = o.fmt || usd;
        return `<div class="rc-card"><span>Into Leading next week</span><b>${ok ? (o.pct ? spc(m - 1) : F(A.close * m)) : '—'}</b><i>${o.pct ? (ok ? `index ${F(A.close * m)}, ` : '') + esc(o.bench) + ' flat' : 'close needed, ' + esc(o.bench) + ' flat'}</i></div></div>`; })();
    return `<div class="rc-sec"><h3>${esc(o.title)}</h3><p class="rc-sub">${esc(o.sub)}</p>${cards}${chart(A, o)}<div class="rc-legend"><span><b style="background:${o.col}"></b>${esc(o.name)}, last ${o.tail} weeks</span>${o.ctx ? `<span><b style="background:var(--muted,#888)"></b>${esc(o.ctxName)}</span>` : ''}<span>faint: replayed paths · dashed: median · boxes: 80% at 4 and 13 weeks</span></div>` +
      ladder(A, o) + ranges(A, o, o.bands) + matrix(A, o) + dynamic(A, o) + '</div>';
  }

  async function render(el, ctx) {
    css();
    const hub = (ctx && ctx.hub != null ? ctx.hub : ''), base = hub + 'data/market/history/';
    const T = String((ctx && ctx.ticker) || '').toUpperCase().replace(/\./g, '-');
    if (!T) { el.innerHTML = '<p class="muted">No ticker: the RRG needs a share price.</p>'; return; }
    el.innerHTML = '<p class="muted">Loading the rotation history…</p>';
    let D, t, M;
    try { [D, t, M] = await Promise.all([get(base + 'rrg.json'), get(base + 't/' + T + '.json').catch(() => null), get(base + 'rrg-transition-model.json').catch(() => null)]); } catch (e) {
      el.innerHTML = `<p class="muted">The rotation history could not load (${esc(e.message)}).</p>`; return;
    }
    if (ctx && ctx.here && !ctx.here()) return;
    if (!t || !t.c) { el.innerHTML = `<p class="muted">${esc(T)} is not in the weekly rotation history yet: the collector adds the site's companies largest first, a batch every few hours.</p>`; return; }
    const U = ui[T] || (ui[T] = { h: 4, tail: 13 });
    const G = grid(D), SPY = place(G, D.bench.start, D.bench.c), C = place(G, t.start, t.c), V = t.v ? place(G, t.start, t.v, 1000) : null;
    const BX = t.bx ? place(G, t.start, t.bx) : null, BI = t.bi ? place(G, t.start, t.bi) : null;
    const IND = BI ? ratio(BI, SPY) : null;
    const Am = analyse(G, C, V, SPY, {}), Ai = BX ? analyse(G, C, V, BX, { IND }) : null;
    const Ind = IND ? states(IND) : null;
    const Aind = BI ? analyse(G, BI, null, SPY, { always: true }) : null;      // the industry's own line, the industry RRG
    const draw = () => {
      const h = U.h, gm = M && M.groups || {}, cw = el.clientWidth || 760, Wc = Math.max(340, Math.min(760, cw));   // text stays legible on a phone
      const om = { title: `${T} against the S&P 500`, name: T, bench: 'SPY', col: 'var(--accent, #17734a)', tail: U.tail, h, W: Wc, kind: 'companies vs the S&P 500',
        sub: `The standard RRG: ${T}'s weekly close ÷ SPY, smoothed (4 weeks) against its own 14-week trend → RS-Ratio; that gap's weekly change → RS-Momentum; both in standard deviations of their own last year, around 100. Grey: its industry${t.bl ? ' (' + t.bl + ', all ' + (t.bn || '') + ' companies)' : ''} against SPY.`,
        missing: 'Not enough weekly history for the RRG yet (about 40 weeks of closes are needed).',
        ctx: Ind, ctxName: t.bl ? t.bl.replace(/ · .*/, '') + ' vs SPY' : 'Industry',
        bands: (gm.company_vs_market || {}).bands, matrixWhat: 'Companies against the S&P 500, every liquid company-week since 2002.' };
      om.odds = Am && M ? odds(M, 'company_vs_market', Am.st, String(h)) : null;
      om.chain = Am && M ? chain(M, 'company_vs_market', Am.st) : null;
      const oi = { title: `${T} against its industry (without itself)`, name: T, bench: 'its industry', col: 'var(--slate, #5b7fa6)', tail: U.tail, h, W: Wc, kind: 'companies vs their industry',
        sub: `The dual RRG's second layer: ${T} against ${t.bl || 'its industry'} without ${T} (up to ${(t.bn || 1) - 1} other companies, each counted while liquid), so a large company does not define its own peers. Where the industry stands against SPY: ${Ind && Ai && Ai.st.iq >= 0 ? QN[Ai.st.iq] : '—'} — the Markov matrix below is the one for that industry quadrant.`,
        missing: t.bx ? 'Not enough weekly history against the industry yet.' : 'No industry benchmark: fewer than five other companies with prices in its SIC group or sector.',
        bands: (gm.company_vs_industry || {}).bands, matrixWhat: `Companies against their industry while the industry was ${Ai && Ai.st.iq >= 0 ? QN[Ai.st.iq] : '—'} against the S&P 500, every liquid company-week since 2002.` };
      oi.odds = Ai && M ? odds(M, 'company_vs_industry', Ai.st, String(h)) : null;
      oi.chain = Ai && M ? chain(M, 'company_vs_industry', Ai.st) : null;
      const iname = t.bl ? t.bl.replace(/ · .*/, '') : 'Its industry';
      const ox = Object.assign(industryOpts(h, U.tail, Wc, iname, t.bl || iname, t.bn, gm), {
        title: `${t.bl || 'Its industry'} against the S&P 500 — the industry's own RRG`,
        members: Aind ? [{ t: T, c: C[Aind.k] }] : [],
        membersWhat: `The ${T} column: ${T}'s close if it moved exactly with its industry (same % move).` });
      ox.odds = Aind && M ? odds(M, 'industry_vs_market', Aind.st, String(h)) : null;
      ox.chain = Aind && M ? chain(M, 'industry_vs_market', Aind.st) : null;
      const tog = (key, vals, cur, f) => vals.map((v) => `<button type="button" class="rc-tog${v === cur ? ' on' : ''}" data-rc="${key}" data-v="${v}">${f(v)}</button>`).join('');
      el.innerHTML = `<div class="rc"><p class="rc-sub">Two Relative Rotation Graphs for ${esc(t.n || T)}: against the market and against its own industry. Each shows the close that would move it into each quadrant next week, the price and position ranges its own past moves give when replayed from today, the Markov matrix of where lines in its spot stood later, and the week-by-week transition chain. Every probability carries the label it earned walk-forward since 2012. History-based, not investment advice.</p>` +
        `<div class="rc-ctl">Markov horizon ${tog('h', H, h, (v) => v + (v > 1 ? ' weeks' : ' week'))}<span style="width:12px"></span>Tail ${tog('tail', [13, 26, 52], U.tail, (v) => v + ' weeks')}</div>` +
        section(Am, om) + section(Ai, oi) + (BI ? section(Aind, ox) : '') +
        `<p class="rc-note">${M ? esc(M.note || '') : 'The transition model has not been published yet: Markov odds and paths are missing.'} ${M && M.replay ? 'Replays: ' + esc(M.replay.method) + '; ' + esc(M.replay.labels) + '.' : ''} The full weekly RRG of sectors, ETFs and any companies is in the Disclosure Hub → Rotation; every industry's own RRG in Rotation → <a href="${esc(hub)}#rotation/ind~${esc(t.bid || '')}">Industry RRG</a>.</p></div>`;
      el.querySelectorAll('[data-rc]').forEach((b) => b.addEventListener('click', () => { U[b.dataset.rc] = +b.dataset.v; draw(); }));
    };
    draw();
  }

  /* ---------- the industry RRG: every industry's own line against SPY (industries.json, group industry_vs_market) ---------- */
  const lvl = (v) => (fin(v) ? num(v, v >= 1000 ? 0 : 2) : '—');
  function industryOpts(h, tail, W, name, label, members, gm) {
    return { title: `${label} against the S&P 500`, name, bench: 'SPY', col: 'var(--q-warm, #c98a00)', tail, h, W, kind: 'industries vs the S&P 500',
      fmt: lvl, pct: true, closeWord: 'index level',
      sub: `The industry's own index${members ? ' (' + members + ' companies on the site, weekly returns weighted by the log of revenue, each counted while liquid)' : ''} ÷ SPY, through the standard RRG formula. The index starts at 100; what matters is the % move: an equal move of every member moves the index by the same %.`,
      missing: 'Not enough weekly history for this industry yet (about 40 weeks of the index are needed).',
      bands: (gm.industry_vs_market || {}).bands, matrixWhat: 'Industries against the S&P 500, every industry-week since 2002 (each industry a company on the site is benchmarked against).' };
  }
  const indName = (r) => r.label + (r.level !== 'sic4' && r.ind ? ` (mostly ${r.ind})` : '');
  async function renderIndustries(el, ctx) {
    css();
    const hub = (ctx && ctx.hub != null ? ctx.hub : ''), base = hub + 'data/market/history/';
    const U = ui.__ind || (ui.__ind = { h: 4, tail: 13, sort: 'members', q: -1, id: (ctx && ctx.id) || '' });
    if (ctx && ctx.id && !U.seen) { U.id = ctx.id; U.seen = 1; }
    if (!el.innerHTML) el.innerHTML = '<p class="muted">Loading the industry indices…</p>';
    let D, I, M;
    try { [D, I, M] = await Promise.all([get(base + 'rrg.json'), get(base + 'industries.json'), get(base + 'rrg-transition-model.json').catch(() => null)]); } catch (e) {
      el.innerHTML = `<p class="muted">The industry indices are not published yet (${esc(e.message)}): the “Rotation history” workflow writes them on its next build.</p>`; return;
    }
    const G = grid(D), SPY = place(G, D.bench.start, D.bench.c), gm = (M && M.groups) || {}, rows = I.rows || [];
    const cache = ui.__indA || (ui.__indA = {});
    const A = (r) => cache[r.id] || (cache[r.id] = analyse(G, place(G, r.start, r.c), null, SPY, { always: true }) || false);
    const tog = (key, vals, cur, f) => vals.map((v) => `<button type="button" class="rc-tog${v === cur ? ' on' : ''}" data-ri-${key}="${v}">${f(v)}</button>`).join('');
    const bindAll = () => {
      el.querySelectorAll('[data-ri]').forEach((b) => b.addEventListener('click', () => { U.id = b.dataset.ri; draw(); if (el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
      ['h', 'tail', 'q'].forEach((k) => el.querySelectorAll(`[data-ri-${k}]`).forEach((b) => b.addEventListener('click', () => { U[k] = +b.getAttribute(`data-ri-${k}`); draw(); })));
      el.querySelectorAll('[data-ri-sort]').forEach((b) => b.addEventListener('click', () => { U.sort = b.getAttribute('data-ri-sort'); draw(); }));
    };
    const draw = async () => {
      const h = U.h, cw = el.clientWidth || 760, Wc = Math.max(340, Math.min(760, cw));
      const ctl = `<div class="rc-ctl">Markov horizon ${tog('h', H, h, (v) => v + (v > 1 ? ' weeks' : ' week'))}<span style="width:12px"></span>Tail ${tog('tail', [13, 26, 52], U.tail, (v) => v + ' weeks')}</div>`;
      const r = U.id && rows.find((x) => x.id === U.id);
      if (r) {
        const a = A(r) || null, o = industryOpts(h, U.tail, Wc, r.label.replace(/ · .*/, ''), indName(r), r.members, gm);
        o.odds = a && M ? odds(M, 'industry_vs_market', a.st, String(h)) : null;
        o.chain = a && M ? chain(M, 'industry_vs_market', a.st) : null;
        const top = (r.tickers || []).slice(0, 6), files = await Promise.all(top.map((t) => get(base + 't/' + t + '.json').catch(() => null)));
        o.members = a ? files.map((f, i) => { if (!f || !f.c) return null; const c = place(G, f.start, f.c)[a.k]; return { t: top[i], c }; }).filter(Boolean) : [];
        o.membersWhat = 'The company columns: each of the largest members\' close if it moved exactly with the industry (same % move) — what the industry\'s quadrant asks of its companies.';
        el.innerHTML = `<div class="rc"><p class="rc-sub"><button type="button" class="rc-tog" data-ri="">← Every industry</button> ${esc(indName(r))} · ${num(r.members)} companies on the site${top.length ? ' · largest: ' + top.map(esc).join(', ') : ''}</p>${ctl}${section(a, o)}<p class="rc-note">${esc(I.note || '')} ${M ? esc(M.note || '') : 'The transition model has not been published yet: Markov odds and paths are missing.'}</p></div>`;
        bindAll(); return;
      }
      U.id = '';
      const list = rows.map((x) => {
        const a = A(x); if (!a) return null;
        const d = M ? odds(M, 'industry_vs_market', a.st, String(h)) : null, show = d && shown(d.label);
        const pv = d ? (show ? d.p : d.hist) : null, best = pv ? pv.indexOf(Math.max(...pv)) : -1;
        const lead = fin(a.th.mx) && fin(a.th.my) ? Math.max(a.th.mx, a.th.my) - 1 : NaN, lag = fin(a.th.mx) && fin(a.th.my) ? Math.min(a.th.mx, a.th.my) - 1 : NaN;
        const cum = a.paths.map((p) => p.cum[h - 1]);
        return { x, a, show, pv, best, lead, lag, med: Math.exp(qtl(cum, 0.5)) - 1, lo: Math.exp(qtl(cum, 0.1)) - 1, hi: Math.exp(qtl(cum, 0.9)) - 1, label: d && d.label };
      }).filter(Boolean).filter((z) => U.q < 0 || z.a.st.q === U.q);
      const key = { members: (z) => -z.x.members, lead: (z) => (fin(z.lead) ? (z.a.st.q === 0 ? 1e3 : 0) + z.lead : 1e9), p: (z) => -(z.pv ? z.pv[0] : -1), lag: (z) => -(z.pv ? z.pv[2] : -1) }[U.sort] || ((z) => -z.x.members);
      list.sort((u, v) => key(u) - key(v));
      const labs = [...new Set(list.map((z) => z.label).filter(Boolean))];
      const counts = [0, 1, 2, 3].map((q) => rows.filter((x) => A(x) && A(x).st.q === q).length);
      const sorts = [['members', 'Most companies'], ['lead', 'Closest to Leading'], ['p', `Most likely Leading in ${h} wk`], ['lag', `Most likely Lagging in ${h} wk`]];
      el.innerHTML = `<div class="rc"><p class="rc-sub">Every industry a company on the site is benchmarked against (${num(rows.length)}; the most specific SIC group with at least six companies with prices), each as its own line against the S&P 500: where it stands, the Markov odds ${h} week${h > 1 ? 's' : ''} on (industries' own matrix, ${labs.map((l) => (LBL[l] || [l])[0]).join(' / ') || 'not published yet'} walk-forward since 2012), the % move of the industry index next week that puts it into Leading or Lagging (solved exactly from the chart's formula, SPY flat), and its replayed range ${h} week${h > 1 ? 's' : ''} on. Pick one for the chart, the matrix, the week-by-week chain and what its largest companies would have to close at.</p>${ctl}` +
        `<div class="rc-ctl">Quadrant <button type="button" class="rc-tog${U.q < 0 ? ' on' : ''}" data-ri-q="-1">All</button>${QN.map((n, q) => `<button type="button" class="rc-tog${U.q === q ? ' on' : ''}" data-ri-q="${q}" style="color:${QC[q]}">${n} (${counts[q]})</button>`).join('')}<span style="width:12px"></span>Sort ${sorts.map(([k, l]) => `<button type="button" class="rc-tog${U.sort === k ? ' on' : ''}" data-ri-sort="${k}">${esc(l)}</button>`).join('')}</div>` +
        `<div class="rc-wrap"><table class="rc-tbl"><tr><th>Industry</th><th class="n">Companies</th><th>Now</th><th class="n">Most likely in ${h} wk</th><th class="n">Into Leading next week</th><th class="n">Into Lagging next week</th><th class="n">Replayed ${h} wk: median [80%]</th></tr>` +
        list.map((z) => `<tr><td><button type="button" data-ri="${esc(z.x.id)}" style="font:inherit;font-weight:600;color:var(--ink,#222);background:none;border:0;padding:0;text-align:left;cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px">${esc(indName(z.x))}</button><br><span style="font-size:11px;color:var(--muted,#888)">${(z.x.tickers || []).slice(0, 4).map(esc).join(' · ')}</span></td><td class="n">${num(z.x.members)}</td>` +
          `<td style="color:${QC[z.a.st.q]}">${QN[z.a.st.q]}<br><span style="font-size:11px;color:var(--muted,#888)">${num(z.a.S.x[z.a.k], 1)} · ${num(z.a.S.y[z.a.k], 1)}</span></td>` +
          `<td class="n">${z.best >= 0 ? `<span style="color:${QC[z.best]}">${QN[z.best]} ${pc(z.pv[z.best])}</span>${z.show ? '' : '<br><span style="font-size:11px;color:var(--muted,#888)">history only</span>'}` : '—'}</td>` +
          `<td class="n">${z.a.st.q === 0 ? 'already · stays above ' + spc(z.lead) : spc(z.lead)}</td><td class="n">${z.a.st.q === 2 ? 'already · stays below ' + spc(z.lag) : 'under ' + spc(z.lag)}</td>` +
          `<td class="n">${spc(z.med)}<br><span style="font-size:11px;color:var(--muted,#888)">${spc(z.lo)} to ${spc(z.hi)}</span></td></tr>`).join('') + '</table></div>' +
        `<p class="rc-note">Moves are of the industry index relative to SPY (SPY flat); an equal % move of every member moves the index by the same %. ${esc(I.note || '')} History-based, not investment advice.</p></div>`;
      bindAll();
    };
    await draw();
  }

  const api = { render, renderIndustries, _t: { states, stepPaths, replay, thresholds, odds, chain, grid, place, ratio, quad, qtl, analyse } };
  if (typeof window !== 'undefined') window.RRGCompanyView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
