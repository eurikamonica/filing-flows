/* Move odds — how rare an asset's latest move is in its own history, and what followed moves like it over the next
   day, week and month: the days in a band of percentiles around it, the days at least as extreme, and every day.
   A company can be switched to its industry (an equal-weighted SIC composite), its sector ETF and the market (SPY).
   The move can be one day, a week or a month, measured as a % change, against the asset's own recent volatility, or
   beyond what the market's move implied (beta-adjusted); any past day or a "what if" move can be looked at instead.
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
    mute: 'var(--muted, #888)', line: 'var(--line, #e3e3e3)', all: 'var(--muted, #9a9a9a)', warn: 'var(--q-warm, #d9822b)' };
  const QS = [5, 10, 25, 50, 75, 90, 95];
  const H = [[1, 'Next day'], [5, 'Next week'], [10, 'Next 2 weeks'], [21, 'Next month']];
  const RGRID = [5, 10, 21, 63, 126, 252, 504];                                  // a week, two, a month, 3 and 6 months, a year, two
  const WIN = [[1, '1 day'], [5, '1 week'], [21, '1 month']];
  const BANDS = [1, 2.5, 5, 10];
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
  // previous chosen day belong to its episode)
  function stats(f, mask, gap) {
    const idx = [], v = [];
    for (let j = 0; j < f.length; j++) if (mask[j] && Number.isFinite(f[j])) { idx.push(j); v.push(Math.expm1(f[j])); }
    if (!v.length) return null;
    const s = Float64Array.from(v).sort(), n = s.length, mean = v.reduce((a, b) => a + b, 0) / n;
    const sd = n > 1 ? Math.sqrt(v.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (n - 1)) : 0;
    let ep = 0, last = -Infinity;
    for (const j of idx) { if (j - last > gap) ep++; last = j; }
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
  // by any day, the median (null when half never recovered)
  function km(times, events) {
    const ix = times.map((_, i) => i).sort((a, b) => times[a] - times[b] || events[b] - events[a]);
    let risk = times.length, S = 1, i = 0, median = null;
    const steps = [];
    while (i < ix.length) {
      const t0 = times[ix[i]]; let d = 0, j = i;
      while (j < ix.length && times[ix[j]] === t0) { if (events[ix[j]]) d++; j++; }
      if (d) { S *= 1 - d / risk; steps.push([t0, S]); if (median === null && S <= 0.5) median = t0; }
      risk -= j - i; i = j;
    }
    const by = (g) => { let v = 1; for (const [t0, sv] of steps) { if (t0 <= g) v = sv; else break; } return 1 - v; };
    return { n: times.length, events: events.filter(Boolean).length, median, by, steps };
  }
  // for the chosen days idx: trading days until the close got back to the close before the w-day move (side < 0:
  // climbed back; side > 0: gave the rise back) and until a new high (the highest close on file up to the day)
  function recovery(c, idx, w, side, end, T) {
    const back = [[], []], high = [[], []];
    for (const j of idx) {
      if (j - w < 0 || j >= end) continue;
      const kb = side < 0 ? firstAt(T.up, j + 1, c[j - w], end) : firstAt(T.dn, j + 1, -c[j - w], end);
      back[0].push((kb >= 0 ? kb : end) - j); back[1].push(kb >= 0);
      const kh = firstAt(T.up, j + 1, T.peak[j], end);
      high[0].push((kh >= 0 ? kh : end) - j); high[1].push(kh >= 0);
    }
    return { back: km(back[0], back[1]), high: km(high[0], high[1]) };
  }

  /* The whole analysis. A: a decoded asset; Mk: the market's (for the beta measure); o: {w, measure: raw | vol | beta,
     mode: latest | date | whatif, date, whatif (% or σ), band, before (only the history before the day)}. */
  function analyze(A, o, Mk) {
    const w = o.w || 1, c = cum(A.r), N = c.length - 1;
    const x = o.measure === 'vol' ? volScaled(A.r, w) : o.measure === 'beta' && Mk ? residual(A, Mk, w) : moves(c, w);
    let t = N, value;
    if (o.mode === 'date' && o.date) {
      t = -1;
      for (let j = N; j >= 0; j--) if (A.days[j] <= o.date && Number.isFinite(x[j])) { t = j; break; }
      if (t < 0) return { error: 'There is no move of this length on or before ' + mdy(o.date) + '.' };
    } else if (o.mode !== 'whatif') {
      while (t >= 0 && !Number.isFinite(x[t])) t--;
      if (t < 0) return { error: 'Not enough history for this measure.' };
    }
    if (o.mode === 'whatif') {
      if (!fin(o.whatif)) return { error: 'Type a move to look at.' };
      value = o.measure === 'vol' ? +o.whatif : Math.log1p(+o.whatif / 100);
      if (!Number.isFinite(value)) return { error: 'That move is not possible.' };
      t = -1;
    } else value = x[t];
    const before = o.before && t >= 0;
    const inS = new Uint8Array(N + 1);
    const vals = [];
    for (let j = 0; j <= N; j++) if (Number.isFinite(x[j]) && (!before || j <= t)) { inS[j] = 1; vals.push(x[j]); }
    const s = Float64Array.from(vals).sort();
    if (s.length < 60) return { error: 'Not enough history before this day for this measure.' };
    const at = pctOf(s, value), side = at >= 50 ? 1 : -1;
    const p = new Float64Array(N + 1).fill(NaN);
    for (let j = 0; j <= N; j++) if (inS[j]) p[j] = pctOf(s, x[j]);
    const sim = new Uint8Array(N + 1), ext = new Uint8Array(N + 1), all = new Uint8Array(N + 1);
    let k = 0, lastAs = null;
    for (let j = 0; j <= N; j++) {
      if (!inS[j]) continue;
      const far = side > 0 ? p[j] >= at : p[j] <= at;
      if (far) { k++; if (j < (t >= 0 ? t : N + 1)) lastAs = j; }
      if (j === t) continue;
      all[j] = 1;
      if (Math.abs(p[j] - at) <= o.band) sim[j] = 1;
      if (far) ext[j] = 1;
    }
    if (o.mode === 'whatif') k++;                                    // the move looked at counts itself, as today does
    let kEp = 0, prev = -Infinity;                                   // separate episodes of such moves (overlapping windows once)
    for (let j = 0; j <= N; j++) if (inS[j] && (side > 0 ? p[j] >= at : p[j] <= at)) { if (j - prev > w) kEp++; prev = j; }
    const years = Math.max((Date.parse(A.days[N]) - Date.parse(A.days[0])) / (365.25 * 864e5), 0.1);
    const out = { A, x, t, value, at, side, n: s.length, every: k ? (s.length + (o.mode === 'whatif' ? 1 : 0)) / k : null, k, kEp, years, lastAs, sim, ext, all, h: {}, actual: {}, s,
      raw: t >= w ? Math.expm1(c[t] - c[t - w]) : null };
    for (const [h] of H) {
      const f = ahead(c, h);
      if (before) for (let j = 0; j <= N; j++) if (j + h > t) f[j] = NaN;   // only what was known on the day
      const gap = Math.max(h, w);
      out.h[h] = { sim: stats(f, sim, gap), ext: stats(f, ext, gap), all: stats(f, all, gap), f };
      if (t >= 0 && t + h <= N) out.actual[h] = Math.expm1(c[t + h] - c[t]);
    }
    // how long it took: days like it, at least as extreme, and every day that moved the same way (the raw move's sign)
    const T = { up: sparse(c), dn: sparse(Array.from(c, (v) => -v)), peak: new Float64Array(N + 1) };
    for (let j = 0, m = -Infinity; j <= N; j++) { m = Math.max(m, c[j]); T.peak[j] = m; }
    const rs = (o.mode === 'whatif' ? Math.sign(value) : Math.sign(c[t] - c[t - w])) || -1, end = before ? t : N;
    const ids = (mask) => { const a = []; for (let j = 0; j <= N; j++) if (mask[j]) a.push(j); return a; };
    const same = new Uint8Array(N + 1);
    for (let j = w; j <= N; j++) if (all[j] && Math.sign(c[j] - c[j - w]) === rs) same[j] = 1;
    out.rec = { side: rs, sim: recovery(c, ids(sim), w, rs, end, T), ext: recovery(c, ids(ext), w, rs, end, T), base: recovery(c, ids(same), w, rs, end, T) };
    if (t >= w) {                                        // the day looked at: how far to go, and how long it took when known
      let pk = 0; for (let j = 1; j <= t; j++) if (c[j] > c[pk]) pk = j;
      const kb = rs < 0 ? firstAt(T.up, t + 1, c[t - w], N) : firstAt(T.dn, t + 1, -c[t - w], N), kh = firstAt(T.up, t + 1, T.peak[t], N);
      out.rec.now = { pre: t - w, peak: pk, back: Math.expm1(c[t - w] - c[t]), high: Math.expm1(T.peak[t] - c[t]),
        backIn: kb >= 0 ? kb - t : null, highIn: kh >= 0 ? kh - t : null, since: N - t };
    }
    return out;
  }

  /* ---------- formatting ---------- */
  const unit = (o) => (o.measure === 'vol' ? 'σ' : '%');
  const disp = (o, v) => (o.measure === 'vol' ? v : Math.expm1(v) * 100);            // the measure as shown: σ, or %
  const fmtX = (o, v, d) => (o.measure === 'vol' ? sgn(v, d == null ? 1 : d, 'σ') : sgn(Math.expm1(v) * 100, d == null ? 1 : d));
  const rankWords = (at) => (at >= 50 ? `top ${num(Math.max(100 - at, 0.05), 100 - at < 1 ? 2 : 1)}%` : `bottom ${num(Math.max(at, 0.05), at < 1 ? 2 : 1)}%`);
  const measureName = (o, kind) => (o.measure === 'vol' ? 'against its own recent volatility' : o.measure === 'beta' ? (kind === 'stock' ? 'beyond what the market\'s move implied' : 'beyond what the market\'s move implied') : '% change');
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
.mv-up{color:var(--mk-profit,#17734a)}.mv-down{color:var(--mk-cost,#c0392b)}
.mv-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.mv-legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.mv-g{stroke:var(--line,#e3e3e3);stroke-width:1}.mv-t{fill:var(--muted,#777);font-size:12px}.mv-l{fill:var(--ink,#222);font-size:12.5px;paint-order:stroke;stroke:var(--surface,#fff);stroke-width:3px}
.mv-note{font-size:12px;color:var(--muted,#777);line-height:1.55;margin-top:10px;max-width:92ch}.mv-apx{border:1px solid var(--line,#ddd);border-radius:10px;padding:6px 12px;margin:10px 0;max-width:980px}
.mv-apx summary{cursor:pointer;font-size:13.5px}.mv-apx p{font-size:13px;line-height:1.55;margin:6px 0;max-width:92ch}.mv-err{color:var(--mk-cost,#c0392b);font-size:13px}
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
  // where the move ranks: every day's move as a histogram, the move looked at marked, the tail beyond it shaded
  function rankSvg(R, o) {
    const W = o.narrow ? 440 : 720;
    const vals = Array.from(R.s, (v) => disp(o, v)), tv = disp(o, R.value), u = unit(o);
    let lo = quantile(Float64Array.from(vals), 0.4), hi = quantile(Float64Array.from(vals), 99.6);
    lo = Math.min(lo, tv); hi = Math.max(hi, tv);
    const pad = (hi - lo) * 0.04; lo -= pad; hi += pad;
    const nb = 56, bw = (hi - lo) / nb, cnt = new Array(nb).fill(0);
    vals.forEach((v) => { cnt[Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / bw)))]++; });
    const Hh = o.narrow ? 220 : 230, L = 14, Rr = 14, T = 26, B = 34, mx = Math.max(...cnt) || 1;
    const sx = (v) => L + (v - lo) / (hi - lo) * (W - L - Rr), sy = (n) => T + (1 - n / mx) * (Hh - T - B);
    const tb = Math.min(nb - 1, Math.max(0, Math.floor((tv - lo) / bw)));
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Every ${esc(win(o.w))} move on file, with the move looked at marked">`;
    ticks(lo, hi, o.narrow ? 4 : 7).forEach((v) => { g += `<line class="mv-g" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${Hh - B}"/><text class="mv-t" x="${sx(v)}" y="${Hh - B + 16}" text-anchor="middle">${esc(sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0, u))}</text>`; });
    cnt.forEach((n, i) => {
      if (!n) return;
      const x0 = sx(lo + i * bw), x1 = sx(lo + (i + 1) * bw), mid = lo + (i + 0.5) * bw;
      const tail = R.side > 0 ? mid >= tv : mid <= tv;
      const col = i === tb ? COL.ink : tail ? (R.side > 0 ? COL.up : COL.down) : COL.all;
      g += `<rect x="${(x0 + 0.5).toFixed(1)}" y="${sy(n).toFixed(1)}" width="${Math.max(0.8, x1 - x0 - 1).toFixed(1)}" height="${(Hh - B - sy(n)).toFixed(1)}" style="fill:${col};opacity:${i === tb ? 1 : tail ? 0.75 : 0.45}"/>`;
    });
    const xt = sx(tv);
    g += `<line x1="${xt}" x2="${xt}" y1="${T - 8}" y2="${Hh - B}" style="stroke:${COL.ink};stroke-width:1.5;stroke-dasharray:4 3"/>`;
    const lab = `${o.mode === 'whatif' ? 'what if' : esc(mdy(R.A.days[R.t]))}: ${esc(fmtX(o, R.value))} · ${rankWords(R.at)}`;
    g += `<text class="mv-l" x="${Math.min(Math.max(xt, L + 110), W - Rr - 110)}" y="${T - 12}" text-anchor="middle" style="font-weight:600">${lab}</text>`;
    g += `<text class="mv-t" x="${L}" y="${Hh - 4}">${esc(num(R.n))} ${esc(win(o.w))} moves since ${esc(my(R.A.days[0]))}</text></svg>`;
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
    const hist = (s) => { const c = new Array(nb).fill(0); s.forEach((v) => { c[Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / bw)))]++; }); return c.map((n) => n / s.length); };
    const hs = hist(S.s), ha = hist(A.s), mx = Math.max(...hs, ...ha) || 1;
    const W = o.narrow ? 440 : 720, Hh = 220, L = 14, Rr = 14, T = 22, B = 34;
    const sx = (v) => L + (v - lo) / (hi - lo) * (W - L - Rr), sy = (n) => T + (1 - n / mx) * (Hh - T - B);
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Returns over the ${esc(H.find((x) => x[0] === h)[1].toLowerCase())} after the chosen days and after every day">`;
    ticks(lo * 100, hi * 100, o.narrow ? 4 : 7).forEach((v) => { g += `<line class="mv-g" x1="${sx(v / 100)}" x2="${sx(v / 100)}" y1="${T}" y2="${Hh - B}"/><text class="mv-t" x="${sx(v / 100)}" y="${Hh - B + 16}" text-anchor="middle">${esc(sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0))}</text>`; });
    g += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${Hh - B}" style="stroke:${COL.mute};stroke-width:1"/>`;
    hs.forEach((n, i) => { if (n) g += `<rect x="${(sx(lo + i * bw) + 0.6).toFixed(1)}" y="${sy(n).toFixed(1)}" width="${Math.max(0.8, sx(lo + (i + 1) * bw) - sx(lo + i * bw) - 1.2).toFixed(1)}" height="${(Hh - B - sy(n)).toFixed(1)}" style="fill:${lo + (i + 0.5) * bw >= 0 ? COL.up : COL.down};opacity:.6"/>`; });
    let path = '';
    ha.forEach((n, i) => { const x0 = sx(lo + i * bw), x1 = sx(lo + (i + 1) * bw); path += `${i ? 'L' : 'M'}${x0.toFixed(1)},${sy(n).toFixed(1)}L${x1.toFixed(1)},${sy(n).toFixed(1)}`; });
    g += `<path d="${path}" style="fill:none;stroke:${COL.ink};stroke-width:1.4;opacity:.7"/>`;
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
    let g = `<svg class="mv-chart" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Every ${esc(win(o.w))} move over time, the days like the one looked at coloured">`;
    ticks(lo, hi, 4).forEach((v) => { g += `<line class="mv-g" x1="${L}" x2="${W - Rr}" y1="${sy(v)}" y2="${sy(v)}"/><text class="mv-t" x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${esc(sgn(v, 0, unit(o)))}</text>`; });
    const y0 = +A.days[0].slice(0, 4), y1 = new Date(t1).getUTCFullYear(), step = Math.max(1, Math.ceil((y1 - y0) / (o.narrow ? 5 : 10)));
    for (let y = y0 + 1; y <= y1; y += step) { const x = sx(`${y}-01-01`); g += `<text class="mv-t" x="${x}" y="${Hh - 8}" text-anchor="middle">${y}</text>`; }
    let grey = '', hot = '';
    for (let j = 0; j <= N; j++) {
      if (!R.all[j]) continue;
      const v = disp(o, R.x[j]), cx = sx(A.days[j]).toFixed(1), cy = sy(v).toFixed(1);
      if (R.sim[j] || R.ext[j]) hot += `<circle cx="${cx}" cy="${cy}" r="${R.sim[j] ? 2.6 : 2}" style="fill:${R.side > 0 ? COL.up : COL.down};opacity:${R.sim[j] ? 0.95 : 0.55}"/>`;
      else if (j % (N > 6000 ? 3 : 1) === 0) grey += `<circle cx="${cx}" cy="${cy}" r="1.2" style="fill:${COL.all};opacity:.35"/>`;
    }
    g += grey + hot;
    if (R.t >= 0) g += `<circle cx="${sx(A.days[R.t])}" cy="${sy(disp(o, R.value))}" r="5" style="fill:none;stroke:${COL.ink};stroke-width:2"/>`;
    return g + '</svg>';
  }

  /* ---------- sections ---------- */
  function headline(R, o, doc) {
    const name = esc(doc.ticker || doc.name), A = R.A, span = o.w === 1 ? '' : o.w === 5 ? ' over a week (5 trading days)' : ' over a month (21 trading days)';
    let lead;
    if (o.mode === 'whatif') {
      lead = `If ${name} moved ${esc(fmtX(o, R.value))}${o.measure === 'vol' ? ' of its own recent volatility' : o.measure === 'beta' ? " beyond what the market's move implied" : ''} in ${o.w === 1 ? 'a day' : o.w === 5 ? 'a week' : 'a month'}`;
    } else {
      const raw = R.raw, verb = !fin(raw) || raw === 0 ? 'was flat' : raw > 0 ? 'rose' : 'fell';
      lead = `${esc(mdy(A.days[R.t]))}: ${name} ${verb}${fin(raw) && raw !== 0 ? ' ' + esc(num(Math.abs(raw) * 100, 1)) + '%' : ''}${span}`
        + (o.measure === 'vol' ? `, ${esc(fmtX(o, R.value))} against its own recent volatility` : o.measure === 'beta' ? `, ${esc(fmtX(o, R.value))} beyond what the market's move implied` : '');
    }
    const p = R.side > 0 ? 100 - R.at : R.at;
    return `<p class="mv-head">${lead}: a <b class="${R.side > 0 ? 'mv-up' : 'mv-down'}">${rankWords(R.at)}</b> ${o.w === 1 ? 'day' : 'move'} — `
      + `of the ${num(R.n)} ${esc(win(o.w))} moves since ${esc(mdy(A.days[0]))}, ${num(p, p < 1 ? 2 : 1)}% were this ${R.side > 0 ? 'high' : 'low'} or ${R.side > 0 ? 'higher' : 'lower'}.</p>`;
  }
  function cards(R, o) {
    const every = R.every, a = R.side > 0 ? 'rise' : 'fall';
    const perYear = (o.w === 1 ? R.k : R.kEp) / R.years;
    const card = (l, v, note, cls) => `<div class="mv-card"><span>${l}</span><b class="${cls || ''}">${v}</b>${note ? `<i>${note}</i>` : ''}</div>`;
    const sim = R.h[21].sim, all = R.h[21].all;
    return `<div class="mv-cards">${card('Percentile', num(R.at, R.at < 1 || R.at > 99 ? 2 : 1), `${rankWords(R.at)} of ${num(R.n)} moves`, R.side > 0 ? 'mv-up' : 'mv-down')}`
      + (o.w === 1 ? card(`A ${a} this large or larger`, fin(every) ? `1 in ${num(every, every < 10 ? 1 : 0)}` : '—', `trading days · about ${num(perYear, perYear < 10 ? 1 : 0)} a year`)
        : card(`${o.w === 5 ? 'Weeks' : 'Months'} with a ${a} this large`, num(R.kEp), `separate episodes in ${num(R.years, 0)} years · about ${num(perYear, perYear < 10 ? 1 : 0)} a year`))
      + card('Last time before', R.lastAs != null ? esc(mdy(R.A.days[R.lastAs])) : 'never', R.lastAs != null ? `${num(Math.round((Date.parse(R.A.days[R.t >= 0 ? R.t : R.A.days.length - 1]) - Date.parse(R.A.days[R.lastAs])) / 864e5))} days earlier` : 'not on file')
      + card('Next month after days like it', sim ? sp(sim.median) : '—', sim ? `median · ${share(sim.up)} rose · every day: ${sp(all && all.median)}, ${share(all && all.up)}` : '', sim ? tone(sim.median) : '')
      + '</div>';
  }
  function verdict(S, A) {
    if (!S || !A || S.n < 2) return '';
    const se = S.sd / Math.sqrt(Math.max(1, S.ep)), z = se > 0 ? (S.mean - A.mean) / se : 0;
    if (S.ep < 8) return `<span class="mv-sub" style="display:inline">too few episodes to tell</span>`;
    return Math.abs(z) >= 2 ? `<b class="${z > 0 ? 'mv-up' : 'mv-down'}">${z > 0 ? 'better' : 'worse'} than usual</b>` : '<span class="mv-sub" style="display:inline">within chance</span>';
  }
  function nextTable(R, o) {
    const label = { sim: `Days like it (±${o.band} pts)`, ext: `At least as ${R.side > 0 ? 'high' : 'low'}`, all: 'Every day' };
    const col = { sim: COL.band, ext: R.side > 0 ? COL.up : COL.down, all: COL.all };
    let h = '<div class="mv-wrap"><table class="mv-tbl"><thead><tr><th></th><th class="n">Median</th><th class="n">Rose</th><th>Range: 5–95% (line), 25–75% (box), median</th><th class="n">Mean</th><th class="n">5% worst</th><th class="n">5% best</th><th class="n">Days</th><th class="n">Episodes</th><th>vs every day</th></tr></thead><tbody>';
    for (const [hz, hl] of H) {
      const g = R.h[hz], qs = ['sim', 'ext', 'all'].map((k) => g[k]).filter(Boolean);
      if (!qs.length) continue;
      const act = fin(R.actual[hz]) ? [R.actual[hz]] : [];
      const lo = Math.min(0, ...act, ...qs.map((S) => S.q[0])), hi = Math.max(0, ...act, ...qs.map((S) => S.q[6]));
      h += `<tr class="grp"><td colspan="10">${hl}${fin(R.actual[hz]) ? ` · <span style="font-weight:500">what happened: <span class="${tone(R.actual[hz])}">${sp(R.actual[hz])}</span></span>` : ''}</td></tr>`;
      for (const k of ['sim', 'ext', 'all']) {
        const S = g[k];
        if (!S) { h += `<tr><td>${label[k]}</td><td colspan="9" class="mv-sub">none</td></tr>`; continue; }
        h += `<tr><td>${label[k]}</td><td class="n ${tone(S.median)}">${sp(S.median)}</td><td class="n">${share(S.up)}</td><td class="box">${boxSvg(S, lo, hi, col[k], R.actual[hz])}</td><td class="n">${sp(S.mean)}</td>`
          + `<td class="n">${sp(S.q[0])}</td><td class="n">${sp(S.q[6])}</td><td class="n">${num(S.n)}</td><td class="n">${k === 'all' ? '—' : num(S.ep)}</td><td>${k === 'all' ? '' : verdict(S, g.all)}</td></tr>`;
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
      return `<tr><td>${esc(mdy(A.days[j]))}</td><td class="n ${tone(R.x[j])}">${esc(fmtX(o, R.x[j]))}</td><td class="n">${num(pctOf(R.s, R.x[j]), 1)}</td><td class="n ${tone(nd)}">${sp(nd)}</td><td class="n ${tone(nw)}">${sp(nw)}</td><td class="n ${tone(nm)}">${sp(nm)}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }
  function controls(st, doc) {
    const pill = (k, v, l, on, dis) => `<button type="button" class="mv-pill${on ? ' on' : ''}" data-mv="${k}" data-v="${esc(v)}"${dis ? ' disabled' : ''}>${esc(l)}</button>`;
    const beta = doc.key !== 'SPY' && doc.kind !== 'index' && doc.kind !== 'market';
    return `<div class="mv-bar"><div><label>Move</label><div class="mv-pills">${WIN.map(([w, l]) => pill('w', w, l, st.w === w)).join('')}</div></div>`
      + `<div><label>Measured as</label><div class="mv-pills">${pill('measure', 'raw', '% change', st.measure === 'raw')}${pill('measure', 'vol', 'vs own volatility (σ)', st.measure === 'vol')}${beta ? pill('measure', 'beta', 'beyond the market', st.measure === 'beta') : ''}</div></div>`
      + `<div><label>Days like it: within</label><div class="mv-pills">${BANDS.map((b) => pill('band', b, '±' + b + ' pts', st.band === b)).join('')}</div></div></div>`
      + `<div class="mv-bar"><div><label>Look at</label><div class="mv-pills">${pill('mode', 'latest', 'the latest move', st.mode === 'latest')}${pill('mode', 'date', 'a past day', st.mode === 'date')}${pill('mode', 'whatif', 'what if…', st.mode === 'whatif')}</div></div>`
      + (st.mode === 'date' ? `<div><label>Day</label><input class="mv-in" type="date" data-mvin="date" value="${esc(st.date || '')}" min="${esc(doc.d0)}" max="${esc(doc.as_of)}"></div><div><label>History used</label><div class="mv-pills">${pill('before', '0', 'all days', !st.before)}${pill('before', '1', 'only before that day', st.before)}</div></div>` : '')
      + (st.mode === 'whatif' ? `<div><label>Move (${st.measure === 'vol' ? 'σ' : '%'})</label><input class="mv-in" type="number" step="0.1" data-mvin="whatif" value="${esc(st.whatif)}" placeholder="${st.measure === 'vol' ? 'e.g. -3' : 'e.g. -5'}"></div>` : '')
      + '</div>';
  }

  /* ---------- how long it took: climbing back, a new high ---------- */
  const RLAB = (rs, kind) => (kind === 'high' ? (rs < 0 ? 'back to a new high' : 'the next new high') : (rs < 0 ? 'back to the close before the move' : 'gave the rise back'));
  const dayWords = (d) => (d == null ? '—' : d <= 1 ? `${d} day` : `${num(d)} days`);
  function recSets(R, o) {
    const rs = R.rec.side;
    return [['sim', COL.band, `Days like it (±${o.band} pts)`], ['ext', R.side > 0 ? COL.up : COL.down, `At least as ${R.side > 0 ? 'high' : 'low'}`],
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

  /* ---------- a picture to share: the chosen panels in one PNG ---------- */
  const PANELS = [['now', 'Now'], ['1', 'Next day'], ['5', '1 week'], ['10', '2 weeks'], ['21', '1 month'], ['back', 'Climb back'], ['high', 'New high']];
  const PC = { bg: '#fcfcfb', card: '#ffffff', ink: '#1d1d1b', ink2: '#3d3c39', muted: '#6b6a66', line: '#e3e1dc', up: '#17734a', down: '#c0392b', band: '#2a78d6', warn: '#d9822b', grey: '#9a9893' };
  // a Gaussian kernel density of sorted values over n points from lo to hi (Silverman's bandwidth)
  function kde(vals, lo, hi, n = 180) {
    const m = vals.length; if (m < 3) return null;
    const mean = vals.reduce((a, b) => a + b, 0) / m, sd = Math.sqrt(vals.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (m - 1));
    const iqr = quantile(vals, 75) - quantile(vals, 25), bw = 0.9 * Math.min(sd, (iqr / 1.34) || sd) * Math.pow(m, -0.2) || sd || 1;
    const xs = [], ys = [], k = 1 / (m * bw * Math.sqrt(2 * Math.PI));
    for (let i = 0; i < n; i++) {
      const x = lo + (hi - lo) * i / (n - 1); let y = 0;
      for (let j = lower(vals, x - 5 * bw), e = upper(vals, x + 5 * bw); j < e; j++) { const u = (x - vals[j]) / bw; y += Math.exp(-0.5 * u * u); }
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
    const P = card(x, box.x, box.y, box.w, box.h, `Now: where the ${win(o.w)} move ranks`, `${num(R.n)} ${win(o.w)} moves since ${my(R.A.days[0])}${o.measure === 'raw' ? '' : ' · ' + measureName(o, 'stock')} · the coloured tail: moves at least as ${R.side > 0 ? 'high' : 'low'}`);
    const K = kde(vals, lo, hi); if (!K) return;
    const top = P.y + 26, bot = P.y + P.h - 22, mx = Math.max(...K.ys) || 1;
    const sx = axisX(x, P, lo, hi, (v) => sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0, u), 8), sy = (v) => bot - v / mx * (bot - top);
    curve(x, K, sx, sy, PC.grey, PC.grey, 0.28, 1.6);
    const tail = { xs: [], ys: [] };
    K.xs.forEach((v, i) => { if (R.side > 0 ? v >= tv : v <= tv) { tail.xs.push(v); tail.ys.push(K.ys[i]); } });
    if (tail.xs.length > 1) curve(x, tail, sx, sy, R.side > 0 ? PC.up : PC.down, R.side > 0 ? PC.up : PC.down, 0.7, 2);
    vline(x, sx(tv), top - 8, bot, PC.ink, [5, 4]);
    const lab = `${o.mode === 'whatif' ? 'What if' : mdy(R.A.days[R.t])}: ${fmtX(o, R.value)} · ${rankWords(R.at)}`;
    x.font = pngFont(15, 650); const lw = x.measureText(lab).width;
    label(x, lab, Math.min(Math.max(sx(tv) - lw / 2, P.x), P.x + P.w - lw), top - 12, R.side > 0 ? PC.up : PC.down, pngFont(15, 650));
    const rare = R.every ? `a ${R.side > 0 ? 'rise' : 'fall'} this large or larger: 1 in ${num(R.every, R.every < 10 ? 1 : 0)} ${o.w === 1 ? 'trading days' : 'days'}` : '';
    label(x, rare, P.x + P.w, P.y + 8, PC.muted, pngFont(12.5), 'right');
  }
  function drawHorizon(x, box, R, o, hz, which) {
    const S = R.h[hz][which], A = R.h[hz].all, hl = H.find((v) => v[0] === hz)[1];
    const P = card(x, box.x, box.y, box.w, box.h, `${hl}${hz === 1 ? '' : ` (${hz} trading days)`}`, `after the ${which === 'sim' ? `days like it (±${o.band} pts)` : `days at least as ${R.side > 0 ? 'high' : 'low'}`} · after every day`);
    if (!S || !A || S.s.length < 3) { x.fillStyle = PC.muted; x.font = pngFont(13); x.fillText('Too few days to draw.', P.x, P.y + 40); return; }
    const sv = Array.from(S.s, (v) => v * 100), av = Array.from(A.s, (v) => v * 100), pool = Float64Array.from([...sv, ...av]).sort();
    let lo = Math.min(quantile(pool, 1), 0), hi = Math.max(quantile(pool, 99), 0);
    const act = fin(R.actual[hz]) ? R.actual[hz] * 100 : null; if (act != null) { lo = Math.min(lo, act); hi = Math.max(hi, act); }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const Ks = kde(sv, lo, hi), Ka = kde(av, lo, hi); if (!Ks || !Ka) return;
    const top = P.y + 46, bot = P.y + P.h - 22, mx = Math.max(...Ks.ys, ...Ka.ys) || 1;
    const sx = axisX(x, P, lo, hi, (v) => sgn(v, Math.abs(v) < 1 && v !== 0 ? 1 : 0), 6), sy = (v) => bot - v / mx * (bot - top);
    vline(x, sx(0), top, bot, PC.line);
    const col = which === 'sim' ? PC.band : (R.side > 0 ? PC.up : PC.down);
    curve(x, Ka, sx, sy, null, PC.grey, 1, 1.8);
    curve(x, Ks, sx, sy, col, col, 0.3, 2.2);
    vline(x, sx(S.median * 100), top, bot, col, [5, 4]); vline(x, sx(A.median * 100), top, bot, PC.grey, [2, 3]);
    if (act != null) { vline(x, sx(act), top - 4, bot, PC.warn); label(x, `what happened ${sp(act / 100)}`, Math.min(sx(act) + 6, P.x + P.w - 150), bot - 8, PC.warn, pngFont(12.5, 600)); }
    const line = (y, c, t1, t2) => { x.fillStyle = c; x.fillRect(P.x, y - 9, 12, 4); x.font = pngFont(13, 600); x.fillStyle = PC.ink; x.fillText(t1, P.x + 18, y - 4); const w1 = x.measureText(t1).width; x.font = pngFont(13); x.fillStyle = PC.ink2; x.fillText(t2, P.x + 18 + w1 + 6, y - 4); };
    line(P.y + 14, col, `${which === 'sim' ? 'days like it' : 'at least as ' + (R.side > 0 ? 'high' : 'low')}: median ${sp(S.median)}`, `· ${share(S.up)} rose · ${num(S.n)} days`);
    line(P.y + 34, PC.grey, `every day: median ${sp(A.median)}`, `· ${share(A.up)} rose`);
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
  async function picture(R, o, doc, picks, hub) {
    if (typeof document === 'undefined') return null;
    if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) { /* draw with what is loaded */ } }
    const order = PANELS.map(([k]) => k).filter((k) => picks.includes(k) && (k !== 'back' && k !== 'high' || R.rec));
    if (!order.length) return null;
    const Wd = 1200, M = 32, G = 22, full = Wd - 2 * M, half = (full - G) / 2, ph = 300;
    const rows = []; let rest = order.slice();
    if (rest[0] === 'now') { rows.push(['now']); rest = rest.slice(1); }
    while (rest.length) { rows.push(rest.length === 1 ? [rest[0]] : [rest[0], rest[1]]); rest = rest.slice(2); }
    const headH = 104, footH = 64, Hh = headH + rows.length * (ph + G) + footH;
    const c = document.createElement('canvas'), sc = 2; c.width = Wd * sc; c.height = Hh * sc;
    const x = c.getContext('2d'); x.scale(sc, sc);
    x.fillStyle = PC.bg; x.fillRect(0, 0, Wd, Hh);
    const name = doc.ticker || doc.name;
    const raw = R.raw, verb = o.mode === 'whatif' ? 'If it moved' : raw > 0 ? 'rose' : raw < 0 ? 'fell' : 'was flat';
    const title = o.mode === 'whatif' ? `What if ${name} moved ${fmtX(o, R.value)} in ${o.w === 1 ? 'a day' : o.w === 5 ? 'a week' : 'a month'}? A ${rankWords(R.at)} ${o.w === 1 ? 'day' : 'move'}`
      : `${name} ${verb} ${num(Math.abs(raw) * 100, 1)}%${o.w === 1 ? '' : o.w === 5 ? ' in a week' : ' in a month'} on ${mdy(R.A.days[R.t])}: a ${rankWords(R.at)} ${o.w === 1 ? 'day' : 'move'}`;
    x.fillStyle = PC.ink; x.font = pngFont(27, 650); x.fillText(title, M, 46);
    x.fillStyle = PC.muted; x.font = pngFont(14.5);
    x.fillText(`${doc.name || name}${doc.members ? ` · equal-weighted, ${num(doc.members)} companies` : ''} · ${win(o.w)} move${o.measure === 'raw' ? '' : ', ' + measureName(o, doc.kind)} · ranked among ${num(R.n)} since ${mdy(R.A.days[0])} · days like it: within ±${o.band} percentile points`, M, 74);
    let y = headH;
    for (const row of rows) {
      row.forEach((k, i) => {
        const box = { x: M + i * (half + G), y, w: row.length === 1 ? full : half, h: ph };
        if (k === 'now') drawNow(x, box, R, o);
        else if (k === 'back' || k === 'high') drawRecovery(x, box, R, o, k, doc);
        else drawHorizon(x, box, R, o, +k, o.set === 'ext' ? 'ext' : 'sim');
      });
      y += ph + G;
    }
    x.strokeStyle = PC.line; x.beginPath(); x.moveTo(M, Hh - footH + 8); x.lineTo(Wd - M, Hh - footH + 8); x.stroke();
    x.fillStyle = PC.muted; x.font = pngFont(12.5);
    x.fillText(`Move odds · daily closes ${mdy(R.A.days[0])} – ${mdy(doc.as_of || R.A.days[R.A.days.length - 1])}, adjusted for dividends and splits · returns close to close after each chosen day`, M, Hh - footH + 32);
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
  function pngBar(st) {
    const on = (k) => (st.png || []).includes(k);
    return `<div class="mv-png"><span class="mv-png-l">Picture to share (PNG):</span>${PANELS.map(([k, l]) => `<label><input type="checkbox" data-mvp="${k}"${on(k) ? ' checked' : ''}> ${esc(l)}</label>`).join('')}`
      + `<button type="button" class="mv-pill on" data-mvpng="1">Make the picture</button><span class="mv-sub" data-mvmsg style="margin:0"></span></div><div class="mv-png-out"></div>`;
  }

  function body(R, st, doc) {
    if (R.error) return `<p class="mv-err">${esc(R.error)}</p>`;
    const which = st.set === 'ext' ? 'ext' : 'sim';
    let h = headline(R, st, doc) + cards(R, st) + pngBar(st);
    h += `<h3>Where it ranks</h3><p class="mv-sub">Every ${esc(win(st.w))} move ${st.measure === 'raw' ? '' : esc(measureName(st, doc.kind)) + ' '}on file. The coloured bars are the moves at least as ${R.side > 0 ? 'high' : 'low'}; the dashed line is the move looked at.${st.before && st.mode === 'date' ? ' Only the days up to it are counted.' : ''}</p>${rankSvg(R, st)}`;
    h += `<h3>What came next</h3><p class="mv-sub">Close-to-close returns from the day of each move: after the days whose move ranked within ±${st.band} percentile points of this one, after the days at least as ${R.side > 0 ? 'high' : 'low'}, and after every day. An episode groups chosen days that fall within the horizon of each other: they are the independent tries, and what "within chance" is judged on.</p>`;
    h += nextTable(R, st);
    h += `<div class="mv-bar"><div><label>Distribution</label><div class="mv-pills">${H.map(([hz, l]) => `<button type="button" class="mv-pill${st.h === hz ? ' on' : ''}" data-mv="h" data-v="${hz}">${esc(l)}</button>`).join('')}</div></div>`
      + `<div><label>Compared with every day</label><div class="mv-pills"><button type="button" class="mv-pill${which === 'sim' ? ' on' : ''}" data-mv="set" data-v="sim">days like it</button><button type="button" class="mv-pill${which === 'ext' ? ' on' : ''}" data-mv="set" data-v="ext">at least as ${R.side > 0 ? 'high' : 'low'}</button></div></div></div>`;
    h += nextSvg(R, st, st.h, which) + `<div class="mv-legend"><span><b style="background:${COL.up};opacity:.6"></b><b style="background:${COL.down};opacity:.6"></b>after the ${which === 'sim' ? 'days like it' : 'more extreme days'} (share of those days)</span><span><b style="background:none;border:1.5px solid ${COL.ink}"></b>after every day</span>${fin(R.actual[st.h]) ? `<span><b style="background:${COL.warn}"></b>what happened after this day</span>` : ''}</div>`;
    h += recoverySection(R, st, doc);
    h += `<h3>When moves like this happened</h3><p class="mv-sub">Every ${esc(win(st.w))} move over time; the coloured dots are the days like this one (larger) and the days at least as ${R.side > 0 ? 'high' : 'low'}. Big moves come in clusters, in volatile years.</p>${timeSvg(R, st)}`;
    h += `<h3>The latest days like it</h3><p class="mv-sub">${which === 'sim' ? `Moves within ±${st.band} percentile points of this one` : `Moves at least as ${R.side > 0 ? 'high' : 'low'}`}, most recent first, and what followed.</p>${recentTable(R, st, which)}`;
    h += `<details class="mv-apx"><summary>How this is worked out</summary>`
      + `<p><b>The move.</b> The close-to-close change over one day, a week (5 trading days) or a month (21), on prices adjusted for dividends and splits (the indices: price only). Measured against its own volatility, it is divided by the standard deviation of the 63 daily returns before the move began (scaled to its length), so a 3% day counts for more in a calm stretch than in a wild one. Beyond the market, it is the move less beta times the S&P 500's move over the same days, beta from the year of daily returns before it.</p>`
      + `<p><b>The percentile.</b> Its mid-rank among every move of the same length on file: 2.5 means 2.5% of moves were lower. "Days like it" are those within the chosen number of percentile points of it; "at least as high / low" those as far out or further on the same side.</p>`
      + `<p><b>What came next.</b> The returns over the next 1, 5, 10 and 21 trading days from the close of each chosen day. Moves longer than a day overlap, and big days cluster, so neighbouring days are not independent tries: the episodes count each cluster once, and "better / worse than usual" asks whether the mean differs from every day's by more than twice its standard error over the episodes. With "only before that day", a past day is judged only on the history known then.</p>`
      + `<p><b>How long it took.</b> From each chosen day, the trading days until the close was back at the close before the move (for a rise: back down to it), and until it was back at the highest close on file up to that day. Days still waiting on the last day on file count for as long as they were watched (the Kaplan–Meier estimate), so recent days do not look like failures; "not back on file" counts them.</p>`
      + `<p><b>Limits.</b> About ten years of daily history for companies and ETFs (the S&P 500, Nasdaq and Dow indices since 1970 where on file). Industry composites are equal-weighted and hold today's companies only, which flatters their past. History rhymes rather than repeats; this describes what followed, it does not forecast. Not investment advice.</p></details>`;
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
    const st = Object.assign({ key: home, w: 1, measure: 'raw', mode: 'latest', date: '', whatif: '', band: 2.5, before: false, h: 21, set: 'sim', rk: 'back',
      png: ['now', '5', '10', '21', 'back', 'high'] }, opts.state || {});
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
      const A = dec[st.key] || (dec[st.key] = decode(doc));
      if (st.measure === 'beta' && (doc.key === 'SPY' || doc.kind === 'index' || doc.kind === 'market')) st.measure = 'raw';
      let Mk = null;
      if (st.measure === 'beta') {
        try { const m = docs.SPY || (docs.SPY = await get(url('SPY'))); Mk = dec.SPY || (dec.SPY = decode(m)); } catch (e) { st.measure = 'raw'; }
      }
      if (!here()) return;
      st.narrow = (el.clientWidth || 800) < 600;
      const R = analyze(A, st, Mk);
      const names = assets.map(([k, l, role]) => [k, l || (homeDoc.names || {})[k] || (docs[k] && docs[k].name) || k, role]);
      let h = '<div class="mv">';
      if (names.length > 1) h += `<div class="mv-assets" role="group" aria-label="What to look at">${names.map(([k, l, role]) => `<button type="button" class="mv-asset${k === st.key ? ' on' : ''}" data-mva="${esc(k)}"><small>${esc(role)}</small>${esc(l)}</button>`).join('')}</div>`;
      h += `<p class="mv-sub">${esc(doc.name || doc.key)} · daily closes ${esc(mdy(doc.d0))} – ${esc(mdy(doc.as_of))}${doc.members ? ` · equal-weighted, ${num(doc.members)} companies` : ''}${doc.kind === 'index' ? ' · price only' : ''}</p>`;
      h += controls(st, doc) + body(R, st, doc) + '</div>';
      el.innerHTML = h;
      el.querySelectorAll('[data-mva]').forEach((b) => { b.onclick = () => { st.key = b.dataset.mva; draw(); }; });
      el.querySelectorAll('[data-mv]').forEach((b) => {
        b.onclick = () => {
          const k = b.dataset.mv, v = b.dataset.v;
          st[k] = k === 'w' || k === 'h' ? +v : k === 'band' ? +v : k === 'before' ? v === '1' : v;
          if (k === 'mode' && v === 'date' && !st.date) st.date = (dec[st.key] || A).days[Math.max(0, (dec[st.key] || A).days.length - 22)];
          if (k === 'mode' && v === 'whatif' && !fin(st.whatif)) st.whatif = st.measure === 'vol' ? -3 : -5;
          if (k === 'measure' && st.mode === 'whatif') st.whatif = v === 'vol' ? -3 : -5;
          draw();
        };
      });
      el.querySelectorAll('[data-mvin]').forEach((inp) => { inp.onchange = () => { st[inp.dataset.mvin] = inp.value; draw(); }; });
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

  const api = { render, decode, cum, moves, ahead, pctOf, quantile, volScaled, residual, stats, analyze, sparse, firstAt, km, recovery, kde, picture, PANELS };
  if (typeof window !== 'undefined') window.MovesView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
