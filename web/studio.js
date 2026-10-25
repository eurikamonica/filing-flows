/* Video studio (#studio): animated market videos made in the browser and saved as MP4.
   Kinds of video
     growth    $X put into two or more tickers on a date: distributions reinvested, the price as traded only, or the two
               split (the price's value plus the distributions taken as cash), as a line race, a bar race, areas or
               counters.
     rrg       the Relative Rotation Graph of any tickers against a benchmark, replayed week by week (the chart's own
               formula: rrg.js / rrg-company-view.js).
     momentum  trailing return against a benchmark (13, 26 or 52 weeks) as a racing ranking or lines.
     fund      a company's own figures quarter by quarter — revenue, operating profit, net earnings, operating cash flow,
               margins, growth — as growing columns, lines or a ranking (data/c/<cik>.json: ten years from the filings).
     formula   any arithmetic on the series: + − × ÷ ^, log, exp, sqrt, abs, rebase, ma, ema, pct, chg, lag, min, max,
               on tickers' prices, total returns, distributions, yields and company figures (NVDA.revenue_ttm …).
   Styles: line race, bar race, areas, counters, columns, the RRG; themes; 16:9, 9:16 and 1:1; 30 or 60 frames a second.
   Export: every frame drawn on a canvas and encoded with WebCodecs (H.264, else VP9) into an MP4 (mp4-muxer); a browser
   without WebCodecs records the preview as it plays (MediaRecorder).
   Data: disclosures/data/etf/px/<SYM>.json (ten years of weekly closes as traded and with distributions reinvested,
   app/etf.py), disclosures/data/market/history/t/<SYM>.json and rrg.json (weekly closes since 2000, adjusted for splits
   and distributions, app/rotation_history.py), data/index.json and data/c/<cik>.json (company figures).
   The address keeps every setting (#studio/k=growth&t=QQQ,SPY&from=2016-01-01…), so a video can be shared. */
(function (root) {
  'use strict';
  const U = root.FFUx || {};
  const esc = U.esc || ((s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
  const fin = (v) => v != null && Number.isFinite(+v);
  const DAY = 864e5, WEEK = 7 * DAY;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const iso = (ms) => new Date(ms).toISOString().slice(0, 10);
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthYear = (ms) => { const d = new Date(ms); return MON[d.getUTCMonth()] + ' ' + d.getUTCFullYear(); };
  const dayLabel = (ms) => { const d = new Date(ms); return MON[d.getUTCMonth()] + ' ' + d.getUTCDate() + ', ' + d.getUTCFullYear(); };
  const json = (url) => (U.json ? U.json(url) : fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  const HUB = 'disclosures/data/', SITE = (root.FF_DATA || 'data/');
  const norm = (s) => String(s || '').trim().toUpperCase().replace(/\./g, '-');
  const friday = (ms) => ms + ((5 - new Date(ms).getUTCDay() + 7) % 7) * DAY;   // the Friday that ends a date's week

  /* ---------- number formats ---------- */
  function money(v, dp) {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 1e12) return s + '$' + (a / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return s + '$' + (a / 1e9).toFixed(a >= 1e11 ? 0 : a >= 1e10 ? 1 : 2) + 'B';
    if (a >= 1e7) return s + '$' + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + 'M';
    if (a === 0) return '$0';
    return s + '$' + a.toLocaleString('en-US', { maximumFractionDigits: dp == null ? (a >= 100 ? 0 : 2) : dp, minimumFractionDigits: dp == null ? (a >= 100 ? 0 : 2) : dp });
  }
  const pctf = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—');
  const plain = (v) => { if (!fin(v)) return '—'; if (v === 0) return '0'; const a = Math.abs(v); return a >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : a >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : a >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 0 }) : a >= 10 ? v.toFixed(1) : a >= 1 ? v.toFixed(2) : v.toFixed(3); };

  /* ---------- data: weekly prices ---------- */
  const PRICES = new Map();
  // {sym, name, px: {t, c, a, div}|null (ten years: close as traded, total-return close, distributions), long: {t, v}|null
  // (since 2000, total return)}; dates are each week's Friday (Yahoo dates a weekly bar on its Monday)
  function price(sym) {
    sym = norm(sym);
    if (!PRICES.has(sym)) PRICES.set(sym, (async () => {
      const [px, th, D] = await Promise.all([json(HUB + 'etf/px/' + sym + '.json'), json(HUB + 'market/history/t/' + sym + '.json'), json(HUB + 'market/history/rrg.json')]);
      let long = th;
      if (!long && D) {
        const s = (D.series || []).find((x) => x.id === sym);
        if (s) long = { start: s.start, c: s.c, n: s.name };
        else if (sym === 'SPY' && D.bench) long = { start: D.bench.start, c: D.bench.c, n: 'SPDR S&P 500 ETF' };
      }
      if (!px && !long) return null;
      const out = { sym, name: (px && px.name) || (long && long.n) || sym, px: null, long: null };
      if (px) {
        const d0 = Date.parse(px.d0 + 'T00:00:00Z');
        out.px = { t: px.t.map((x) => friday(d0 + x * DAY)), c: px.c, a: px.a, div: (px.div || []).map(([d, v]) => [friday(Date.parse(d + 'T00:00:00Z')), v]) };
      }
      if (long) {
        const s0 = Date.parse(long.start + 'T00:00:00Z'), t = [], v = [];
        long.c.forEach((x, i) => { if (fin(x) && x > 0) { t.push(s0 + i * WEEK); v.push(+x); } });
        if (t.length) out.long = { t, v };
      }
      return out;
    })());
    return PRICES.get(sym);
  }
  // the value at (or the last before) day g, if it is no more than `stale` days old
  function asof(t, v, g, stale = 10) {
    let lo = 0, hi = t.length - 1, k = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (t[m] <= g + 2 * DAY) { k = m; lo = m + 1; } else hi = m - 1; }
    return k >= 0 && g - t[k] <= stale * DAY ? v[k] : null;
  }
  const first = (P) => Math.min(P.px ? P.px.t[0] : Infinity, P.long ? P.long.t[0] : Infinity);
  const last = (P) => Math.max(P.px ? P.px.t[P.px.t.length - 1] : -Infinity, P.long ? P.long.t[P.long.t.length - 1] : -Infinity);
  // total return on the grid: the ten-year file when it reaches back far enough (the same basis as the price-only line)
  function trOn(P, G) {
    const usePx = P.px && P.px.t[0] <= G[0] + 14 * DAY;
    const src = usePx || !P.long ? { t: P.px.t, v: P.px.a } : P.long;
    return G.map((g) => asof(src.t, src.v, g));
  }
  const priceOn = (P, G) => (P.px ? G.map((g) => asof(P.px.t, P.px.c, g)) : null);
  function divsOn(P, G) {                                  // distributions per share paid in each grid week
    if (!P.px) return null;
    const out = G.map(() => 0); let j = 0;
    const D = P.px.div;
    for (let i = 0; i < G.length; i++) {
      const lo = i ? G[i - 1] : -Infinity;
      while (j < D.length && D[j][0] <= G[i] + 2 * DAY) { if (D[j][0] > lo + 2 * DAY || !i) out[i] += D[j][1]; j++; }
    }
    if (G.length) out[0] = 0;
    return out;
  }
  // distributions of the last twelve months at day g: the last N payments, N = the fund's usual number a year (from its
  // last three years), so a payment that comes a week later than a year before is not missed for a week
  function divTTM(P, g) {
    if (!P.px) return null;
    const D = P.px.div.filter((d) => d[0] <= g + 2 * DAY);
    if (P.px.t[0] > g - 360 * DAY) return null;               // less than a year on file
    const y3 = D.filter((d) => d[0] > g - 3 * 365.25 * DAY), long3 = P.px.t[0] <= g - 3 * 365 * DAY;
    const n = long3 ? Math.max(1, Math.round(y3.length / 3)) : D.filter((d) => d[0] > g - 365 * DAY).length;
    const last = D.slice(-n);
    if (!last.length) return 0;
    return last[last.length - 1][0] > g - 400 * DAY ? last.reduce((a, d) => a + d[1], 0) : 0;
  }
  function weeklyGrid(from, to) {                          // every Friday from → to
    const a = Date.parse(from + 'T00:00:00Z'), b = Date.parse(to + 'T00:00:00Z');
    const d = new Date(a), shift = (5 - d.getUTCDay() + 7) % 7;
    const out = [];
    for (let t = a + shift * DAY; t <= b + 6 * DAY; t += WEEK) out.push(t);
    return out;
  }

  /* ---------- data: company figures (data/c/<cik>.json, quality.hist: ten years from the filings) ---------- */
  const FIG = { revenue: 'Revenue', oi: 'Operating profit', ni: 'Net earnings', ocf: 'Operating cash flow', om: 'Operating margin', nm: 'Net margin', growth: 'Revenue growth, Y/Y' };
  const COS = new Map();
  async function company(sym) {
    sym = norm(sym);
    if (!COS.has(sym)) COS.set(sym, (async () => {
      const ix = await json(SITE + 'index.json');
      const row = ((ix && ix.companies) || []).find((c) => norm(c.ticker) === sym);
      if (!row) return null;
      const c = await json(SITE + 'c/' + row.cik + '.json');
      if (!c) return null;
      const out = { sym, cik: row.cik, name: (c.profile && c.profile.name) || row.name || sym, q: {} };
      const H = (c.quality || {}).hist;
      if (H && H.periods && H.v) {
        for (const [k, rows] of Object.entries(H.v)) {
          const m = new Map();
          for (const [pi, vals] of rows || []) { const p = H.periods[pi]; if (p && p[2] === 'q' && vals && vals[0] && fin(vals[0][0])) m.set(p[1], +vals[0][0]); }
          out.q[k] = m;
        }
      }
      for (const q of c.quarters || []) {                     // the latest quarters on the page fill the newest ends
        const h = q.headline || {};
        if (q.end && /^Q/i.test(String(q.label || 'Q'))) for (const k of ['revenue', 'oi', 'ni', 'ocf']) if (fin(h[k])) { out.q[k] = out.q[k] || new Map(); if (!out.q[k].has(q.end)) out.q[k].set(q.end, +h[k]); }
      }
      return out;
    })());
    return COS.get(sym);
  }
  // [[end ms, value]] of one figure: quarterly or trailing four quarters; margins and growth derived
  function figure(C, key, ttm) {
    const base = (k) => [...((C.q[k] || new Map()).entries())].map(([e, v]) => [Date.parse(e + 'T00:00:00Z'), v]).sort((a, b) => a[0] - b[0]);
    const roll = (rows) => {                                 // four consecutive quarters (about a year between the first and last)
      if (!ttm) return rows;
      const out = [];
      for (let i = 3; i < rows.length; i++) { const span = (rows[i][0] - rows[i - 3][0]) / DAY; if (span > 240 && span < 300) out.push([rows[i][0], rows[i - 3][1] + rows[i - 2][1] + rows[i - 1][1] + rows[i][1]]); }
      return out;
    };
    if (key === 'om' || key === 'nm') {
      const num = new Map(roll(base(key === 'om' ? 'oi' : 'ni'))), den = roll(base('revenue'));
      return den.filter(([e, v]) => v > 0 && num.has(e)).map(([e, v]) => [e, num.get(e) / v]);
    }
    if (key === 'growth') {
      const r = roll(base('revenue')), m = new Map(r), out = [];
      for (const [e, v] of r) { const p = [...m.entries()].find(([e0]) => Math.abs((e - e0) / DAY - 364) < 20); if (p && p[1] > 0) out.push([e, v / p[1] - 1]); }
      return out;
    }
    return roll(base(key));
  }
  const figFmt = (key) => (key === 'om' || key === 'nm' || key === 'growth' ? (v) => (fin(v) ? (100 * v).toFixed(1) + '%' : '—') : (v) => money(v));

  /* ---------- formulas: + − × ÷ ^ and functions over the weekly series ---------- */
  const FUNCS = {
    log: 1, ln: 1, log10: 1, exp: 1, sqrt: 1, abs: 1, rebase: [1, 2], ma: 2, ema: 2, pct: 2, chg: 2, lag: 2, min: 2, max: 2,
  };
  function tokenize(s) {
    const out = []; let i = 0;
    while (i < s.length) {
      const c = s[i];
      if (/\s/.test(c)) { i++; continue; }
      if (/[0-9.]/.test(c)) { let j = i; while (j < s.length && /[0-9.eE]/.test(s[j]) && !(/[eE]/.test(s[j]) && !/[0-9]/.test(s[j + 1] || ''))) j++; out.push({ k: 'num', v: parseFloat(s.slice(i, j)) }); i = j; continue; }
      if (/[A-Za-z_$]/.test(c)) { let j = i; while (j < s.length && /[A-Za-z0-9_\-.$]/.test(s[j]) && !(s[j] === '-' && !/[A-Za-z0-9]/.test(s[j + 1] || ''))) j++; out.push({ k: 'id', v: s.slice(i, j) }); i = j; continue; }
      if ('+-*/^(),×÷'.includes(c)) { out.push({ k: 'op', v: c === '×' ? '*' : c === '÷' ? '/' : c }); i++; continue; }
      throw new Error('Unexpected “' + c + '” in the formula');
    }
    return out;
  }
  // recursive descent: expr = term (± term)*; term = unary (×÷ unary)*; unary = −unary | pow; pow = atom (^ unary)?
  function parse(src) {
    const T = tokenize(src); let p = 0;
    const peek = () => T[p], take = (v) => { const t = T[p]; if (!t || (v && t.v !== v)) throw new Error('Expected ' + (v || 'more') + ' in the formula'); p++; return t; };
    function expr() { let n = term(); while (peek() && (peek().v === '+' || peek().v === '-') && peek().k === 'op') { const o = take().v; n = { op: o, a: n, b: term() }; } return n; }
    function term() { let n = unary(); while (peek() && (peek().v === '*' || peek().v === '/') && peek().k === 'op') { const o = take().v; n = { op: o, a: n, b: unary() }; } return n; }
    function unary() { if (peek() && peek().k === 'op' && peek().v === '-') { take(); return { op: 'neg', a: unary() }; } if (peek() && peek().k === 'op' && peek().v === '+') { take(); return unary(); } return pow(); }
    function pow() { const a = atom(); if (peek() && peek().v === '^') { take(); return { op: '^', a, b: unary() }; } return a; }
    function atom() {
      const t = take();
      if (t.k === 'num') return { num: t.v };
      if (t.k === 'op' && t.v === '(') { const n = expr(); take(')'); return n; }
      if (t.k === 'id') {
        const f = t.v.toLowerCase();
        if (peek() && peek().v === '(' && FUNCS[f]) {
          take('('); const args = [expr()];
          while (peek() && peek().v === ',') { take(','); args.push(expr()); }
          take(')');
          const want = FUNCS[f], ok = Array.isArray(want) ? args.length >= want[0] && args.length <= want[1] : args.length === want;
          if (!ok) throw new Error(f + '() takes ' + (Array.isArray(want) ? want.join(' or ') : want) + ' argument' + (want === 1 ? '' : 's'));
          return { fn: f, args };
        }
        const [sym, field] = t.v.split('.');
        return { id: norm(sym), field: (field || 'tr').toLowerCase() };
      }
      throw new Error('Unexpected “' + t.v + '” in the formula');
    }
    const n = expr();
    if (p < T.length) throw new Error('Unexpected “' + T[p].v + '” in the formula');
    return n;
  }
  function ids(n, out = []) { if (!n) return out; if (n.id) out.push(n); if (n.a) ids(n.a, out); if (n.b) ids(n.b, out); if (n.args) n.args.forEach((x) => ids(x, out)); return out; }
  const FIELDS = { tr: 'total return (distributions reinvested)', price: 'price as traded', div: 'distributions per share, last 52 weeks', yield: 'distribution yield, last 52 weeks',
    revenue: 'revenue (quarter)', oi: 'operating profit (quarter)', ni: 'net earnings (quarter)', ocf: 'operating cash flow (quarter)', revenue_ttm: 'revenue, trailing four quarters',
    oi_ttm: 'operating profit, trailing four quarters', ni_ttm: 'net earnings, trailing four quarters', ocf_ttm: 'operating cash flow, trailing four quarters', margin: 'operating margin (trailing)', netmargin: 'net margin (trailing)' };
  async function fieldOn(sym, field, G, notes) {
    if (['tr', 'price', 'div', 'yield'].includes(field)) {
      const P = await price(sym);
      if (!P) throw new Error('No weekly prices on file for ' + sym);
      if (field === 'tr') return trOn(P, G);
      if (!P.px) { notes.add(sym + ': only total return is on file (no price as traded or distributions)'); return field === 'price' ? trOn(P, G) : G.map(() => null); }
      const pr = priceOn(P, G);
      if (field === 'price') return pr;
      return G.map((g, i) => { const s = divTTM(P, g); return s == null ? null : field === 'div' ? s : (pr[i] ? s / pr[i] : null); });
    }
    const C = await company(sym);
    if (!C) throw new Error('No company figures on file for ' + sym);
    const map = { revenue: ['revenue', 0], oi: ['oi', 0], ni: ['ni', 0], ocf: ['ocf', 0], revenue_ttm: ['revenue', 1], oi_ttm: ['oi', 1], ni_ttm: ['ni', 1], ocf_ttm: ['ocf', 1], margin: ['om', 1], netmargin: ['nm', 1] }[field];
    if (!map) throw new Error('Unknown field .' + field + ' (try ' + Object.keys(FIELDS).join(', ') + ')');
    const rows = figure(C, map[0], map[1]);
    return G.map((g) => { let v = null; for (const [e, x] of rows) { if (e <= g) v = x; else break; } return v; });   // as of each quarter's end
  }
  function evaluate(n, env, len) {
    const E = (x) => evaluate(x, env, len);
    if (n.num != null) return new Array(len).fill(n.num);
    if (n.id) return env.get(n.id + '.' + n.field);
    const map2 = (a, b, f) => a.map((x, i) => (fin(x) && fin(b[i]) ? f(x, b[i]) : null));
    if (n.op) {
      const a = E(n.a);
      if (n.op === 'neg') return a.map((x) => (fin(x) ? -x : null));
      const b = E(n.b);
      if (n.op === '+') return map2(a, b, (x, y) => x + y);
      if (n.op === '-') return map2(a, b, (x, y) => x - y);
      if (n.op === '*') return map2(a, b, (x, y) => x * y);
      if (n.op === '/') return map2(a, b, (x, y) => (y !== 0 ? x / y : null));
      if (n.op === '^') return map2(a, b, (x, y) => { const r = Math.pow(x, y); return Number.isFinite(r) ? r : null; });
    }
    const A = n.args.map(E), x = A[0], k = A[1] ? Math.max(1, Math.round(A[1].find(fin) || 1)) : 1;
    const one = (f) => x.map((v) => { if (!fin(v)) return null; const r = f(v); return Number.isFinite(r) ? r : null; });
    switch (n.fn) {
      case 'log': case 'ln': return one(Math.log);
      case 'log10': return one(Math.log10);
      case 'exp': return one(Math.exp);
      case 'sqrt': return one(Math.sqrt);
      case 'abs': return one(Math.abs);
      case 'rebase': { const b0 = x.find(fin), base = A[1] ? (A[1].find(fin) || 100) : 100; return x.map((v) => (fin(v) && b0 ? v / b0 * base : null)); }
      case 'ma': return x.map((_, i) => { let s = 0, m = 0; for (let j = Math.max(0, i - k + 1); j <= i; j++) if (fin(x[j])) { s += x[j]; m++; } return m === k ? s / m : null; });
      case 'ema': { const al = 2 / (k + 1); let m = null; return x.map((v) => { if (!fin(v)) return m; m = m == null ? v : m + al * (v - m); return m; }); }
      case 'pct': return x.map((v, i) => (i >= k && fin(v) && fin(x[i - k]) && x[i - k] !== 0 ? 100 * (v / x[i - k] - 1) : null));
      case 'chg': return x.map((v, i) => (i >= k && fin(v) && fin(x[i - k]) ? v - x[i - k] : null));
      case 'lag': return x.map((_, i) => (i >= k ? x[i - k] : null));
      case 'min': return map2(x, A[1], Math.min);
      case 'max': return map2(x, A[1], Math.max);
    }
    throw new Error('Unknown function ' + n.fn);
  }
  // "Label: expression" lines (or "Label = expression"), separated by new lines or semicolons
  function formulas(text) {
    return String(text || '').split(/[\n;]+/).map((l) => l.trim()).filter(Boolean).slice(0, 8).map((l) => {
      const m = /^([^:=]{1,40}?)\s*[:=]\s*(.+)$/.exec(l);
      return m && !/[()+\-*/^]/.test(m[1]) ? { label: m[1].trim(), src: m[2].trim() } : { label: l, src: l };
    });
  }

  /* ---------- the RRG formula (transition_rrg.rrg_states, rrg-company-view.js) ---------- */
  function ema(a, span) {
    const al = 2 / (span + 1), need = Math.min(span, 6), out = new Array(a.length).fill(null); let m = 0, c = 0;
    for (let i = 0; i < a.length; i++) { if (!fin(a[i])) { m = 0; c = 0; continue; } m = c === 0 ? a[i] : m + al * (a[i] - m); c++; if (c >= need) out[i] = m; }
    return out;
  }
  function rrgXY(rs, n = 14) {
    const sh = 4, long = Math.max(52, 3 * n), s = ema(rs, sh), t = ema(s, n);
    const dev = s.map((v, i) => (fin(v) && fin(t[i]) && t[i] !== 0 ? 100 * (v / t[i] - 1) : null));
    const roc = ema(dev.map((v, i) => (i && fin(v) && fin(dev[i - 1]) ? v - dev[i - 1] : null)), sh);
    const norm2 = (A) => A.map((v, k) => { if (!fin(v)) return null; let s2 = 0, m = 0; for (let i = Math.max(0, k - long + 1); i <= k; i++) if (fin(A[i])) { s2 += A[i] * A[i]; m++; } return m >= Math.min(long, 26) && s2 > 0 ? 100 + v / Math.sqrt(s2 / m) : null; });
    const x = norm2(dev), y = norm2(roc).map((v, i) => (fin(x[i]) ? v : null));
    return { x, y };
  }

  /* ---------- building a video: the series on the grid, labels and formats ---------- */
  const DEF = { k: 'growth', t: 'QQQ,SPY', from: '', to: '', amt: '10000', div: 'tr', style: 'line', theme: 'bull', ar: '16x9', q: '1080', fps: '30', dur: '20',
    title: '', sub: '', bench: 'SPY', tail: '10', n: '14', lb: '26', m: 'revenue', ttm: '1', expr: 'QQQ/SPY', scale: 'lin', end: '1' };
  const KINDS = [['growth', 'Growth race'], ['rrg', 'RRG replay'], ['momentum', 'Momentum race'], ['fund', 'Company figures'], ['formula', 'Formula & ratios']];
  const STYLES = { growth: [['line', 'Line race'], ['bars', 'Bar race'], ['area', 'Areas'], ['tiles', 'Counters']], rrg: [['rrg', 'RRG']], momentum: [['bars', 'Bar race'], ['line', 'Lines']],
    fund: [['columns', 'Columns'], ['line', 'Lines'], ['bars', 'Bar race'], ['tiles', 'Counters']], formula: [['line', 'Lines'], ['area', 'Areas'], ['tiles', 'Counters'], ['bars', 'Bar race']] };
  const tickers = (st) => [...new Set(String(st.t || '').split(/[\s,;]+/).map(norm).filter(Boolean))].slice(0, 10);

  async function buildRaw(st) {
    const notes = new Set(), T = tickers(st), k = st.k;
    const today = iso(Date.now());
    const out = { kind: k, series: [], notes, fmt: (v) => money(v), title: '', sub: '', unit: '$' };
    if (k === 'fund') {
      if (!T.length) throw new Error('Add a company ticker');
      const cos = (await Promise.all(T.map(company))).filter(Boolean);
      T.filter((s, i) => !cos.find((c) => c.sym === s)).forEach((s) => notes.add(s + ': no company figures on file (the site draws companies that file 10-Qs and 10-Ks)'));
      if (!cos.length) throw new Error('None of these companies has figures on file');
      const key = st.m in FIG ? st.m : 'revenue', ttm = st.ttm === '1' || key === 'growth' || key === 'om' || key === 'nm';
      const from = st.from ? Date.parse(st.from + 'T00:00:00Z') : -Infinity, to = st.to ? Date.parse(st.to + 'T00:00:00Z') : Infinity;
      const rows = cos.map((C) => ({ C, r: figure(C, key, ttm).filter(([e]) => e >= from && e <= to) }));
      const ends = [...new Set(rows.flatMap((x) => x.r.map((p) => p[0])))].sort((a, b) => a - b);
      // quarters of different fiscal calendars: put each company's figure on the nearest common end (within 45 days)
      const G = []; for (const e of ends) if (!G.length || e - G[G.length - 1] > 45 * DAY) G.push(e); else G[G.length - 1] = e;
      if (G.length < 2) throw new Error('Fewer than two quarters on file for that range');
      out.grid = G; out.quarterly = true; out.fmt = figFmt(key); out.unit = key === 'om' || key === 'nm' || key === 'growth' ? '%' : '$';
      out.metric = FIG[key] + (ttm && key !== 'om' && key !== 'nm' && key !== 'growth' ? ', trailing four quarters' : key === 'om' || key === 'nm' ? ' (trailing four quarters)' : '');
      out.series = rows.map(({ C, r }) => ({ key: C.sym, label: C.sym, name: C.name, v: G.map((g) => { const p = r.find(([e]) => Math.abs(e - g) <= 45 * DAY); return p ? p[1] : null; }) }));
      out.title = out.title || (cos.length === 1 ? `${cos[0].name.replace(/,? (INC|CORP|CORPORATION|LTD|PLC|CO)\.?$/i, '')}: ${FIG[key].toLowerCase()}` : `${FIG[key]}: ${cos.map((c) => c.sym).join(' vs ')}`);
      out.sub = out.sub || `${out.metric} · ${dayLabel(G[0])} – ${dayLabel(G[G.length - 1])} · from SEC filings`;
      return out;
    }
    let need = T.slice();
    let tree = [];
    if (k === 'formula') {
      const F = formulas(st.expr);
      if (!F.length) throw new Error('Write a formula, e.g. QQQ/SPY');
      tree = F.map((f) => ({ ...f, ast: parse(f.src) }));
      need = [...new Set(tree.flatMap((f) => ids(f.ast).map((x) => x.id)))];
    }
    const bench = norm(st.bench || 'SPY');
    if (k === 'rrg' || k === 'momentum') need = [...new Set(need.concat(bench))];
    if (!need.length) throw new Error('Add tickers');
    const P = new Map();
    await Promise.all(need.map(async (s) => { const p = await price(s); if (p) P.set(s, p); }));
    const isFund = (x) => !['tr', 'price', 'div', 'yield'].includes(x.field);
    const missing = need.filter((s) => !P.has(s) && !(k === 'formula' && tree.every((f) => ids(f.ast).filter((x) => x.id === s).every(isFund))));
    missing.forEach((s) => notes.add(s + ': no weekly prices on file (the site keeps every ETF and the companies it draws)'));
    const have = [...P.values()];
    if (!have.length && k !== 'formula') throw new Error('No prices on file for ' + need.join(', '));
    // the window: from the requested date (or the latest common start), to the latest common week
    const starts = (k === 'rrg' || k === 'momentum' ? have : have.filter((p) => T.includes(p.sym) || k === 'formula')).map(first).filter(Number.isFinite);
    const ends = have.map(last).filter(Number.isFinite);
    let from = st.from ? Date.parse(st.from + 'T00:00:00Z') : Date.now() - 5 * 365 * DAY;
    const common = starts.length ? Math.max(...starts) : from;
    if (common > from + 10 * DAY && k === 'growth') { notes.add(`Starts ${dayLabel(common)}, when every ticker has prices`); from = common; }
    const to = Math.min(st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now(), ends.length ? Math.min(...ends) : Date.now());
    const warm = k === 'rrg' ? 130 * WEEK : k === 'momentum' ? (+st.lb + 2) * WEEK : 0;
    const GW = weeklyGrid(iso(from - warm), iso(to)), G = GW.filter((g) => g >= from - 3 * DAY);
    if (G.length < 4) throw new Error('Fewer than four weeks in that range');
    out.grid = G;
    const cut = GW.length - G.length;
    if (k === 'growth') {
      const amt = Math.max(1, +st.amt || 10000);
      out.amt = amt;
      for (const s of T) {
        const p = P.get(s); if (!p) continue;
        const tr = trOn(p, G), pr = priceOn(p, G), dv = divsOn(p, G);
        let mode = st.div;
        if ((mode === 'price' || mode === 'split') && !pr) { notes.add(`${s}: price as traded and distributions are on file for ETFs only — total return shown`); mode = 'tr'; }
        const i0 = (mode === 'tr' ? tr : pr).findIndex(fin);
        if (i0 < 0) continue;
        if (mode === 'tr') out.series.push({ key: s, label: s, name: p.name, v: tr.map((v, i) => (i >= i0 && fin(v) ? amt * v / tr[i0] : null)) });
        else {
          const sh = amt / pr[i0]; let cash = 0;
          const pv = [], cv = [];
          for (let i = 0; i < G.length; i++) { if (i > i0) cash += sh * (dv[i] || 0); pv.push(i >= i0 && fin(pr[i]) ? sh * pr[i] : null); cv.push(i >= i0 ? cash : null); }
          out.series.push({ key: s, label: s, name: p.name, v: mode === 'split' ? pv.map((v, i) => (fin(v) ? v + cv[i] : null)) : pv, price: pv, cash: mode === 'split' ? cv : null });
        }
      }
      const md = { tr: 'distributions reinvested', price: 'price as traded (no distributions)', split: 'price + distributions taken as cash' }[st.div];
      out.title = out.title || `${money(amt, 0)} invested in ${out.series.map((s) => s.key).join(' vs ')}`;
      out.sub = out.sub || `${dayLabel(G[0])} → ${dayLabel(G[G.length - 1])} · ${md} · weekly closes`;
      out.base = amt; out.split = st.div === 'split';
    } else if (k === 'momentum') {
      const B = P.get(bench); if (!B) throw new Error('No prices for the benchmark ' + bench);
      const lb = +st.lb || 26, bt = trOn(B, GW);
      for (const s of T) {
        if (s === bench && T.length > 1) continue;
        const p = P.get(s); if (!p) continue;
        const tr = trOn(p, GW);
        const v = tr.map((x, i) => (i >= lb && fin(x) && fin(tr[i - lb]) && fin(bt[i]) && fin(bt[i - lb]) ? (x / tr[i - lb]) / (bt[i] / bt[i - lb]) - 1 : null)).slice(cut);
        out.series.push({ key: s, label: s, name: p.name, v });
      }
      out.fmt = (v) => pctf(v); out.unit = '%';
      out.title = out.title || `Momentum: ${lb}-week return vs ${bench}`;
      out.sub = out.sub || `${out.series.map((s) => s.key).join(' · ')} · ${dayLabel(G[0])} → ${dayLabel(G[G.length - 1])} · total return, weekly`;
      out.zero = true;
    } else if (k === 'rrg') {
      const B = P.get(bench); if (!B) throw new Error('No prices for the benchmark ' + bench);
      const bt = trOn(B, GW);
      for (const s of T) {
        if (s === bench) continue;
        const p = P.get(s); if (!p) continue;
        const tr = trOn(p, GW), rs = tr.map((x, i) => (fin(x) && fin(bt[i]) && bt[i] > 0 ? 100 * x / bt[i] : null));
        const { x, y } = rrgXY(rs, +st.n || 14);
        out.series.push({ key: s, label: s, name: p.name, x: x.slice(cut), y: y.slice(cut) });
      }
      out.bench = bench; out.tail = Math.max(2, +st.tail || 10);
      out.title = out.title || `Relative Rotation Graph vs ${bench}`;
      out.sub = out.sub || `${out.series.map((s) => s.key).join(' · ')} · weekly, ${st.n || 14}-week window · ${dayLabel(G[0])} → ${dayLabel(G[G.length - 1])}`;
    } else if (k === 'formula') {
      const env = new Map();
      for (const f of tree) for (const x of ids(f.ast)) { const key = x.id + '.' + x.field; if (!env.has(key)) env.set(key, await fieldOn(x.id, x.field, G, notes)); }
      out.series = tree.map((f) => ({ key: f.label, label: f.label, name: f.src, v: evaluate(f.ast, env, G.length) }));
      const vals = out.series.flatMap((s) => s.v).filter(fin);
      out.fmt = plain; out.unit = '';
      out.title = out.title || tree.map((f) => f.label).join(' · ');
      out.sub = out.sub || `${dayLabel(G[0])} → ${dayLabel(G[G.length - 1])} · weekly · ${tree.map((f) => f.src).join(' ; ')}`;
      out.zero = vals.some((v) => v < 0) && vals.some((v) => v > 0);
    }
    out.series = out.series.filter((s) => (s.v || s.x || []).some(fin));
    if (!out.series.length) throw new Error('Nothing to draw for those settings');
    return out;
  }

  /* ---------- themes ---------- */
  const THEMES = {
    bull: { name: 'Bull (dark)', bg: ['#06101f', '#0b1f3a', '#0f2b4f'], grid: 'rgba(160,190,230,0.10)', axis: 'rgba(200,215,235,0.55)', text: '#eef4fb', muted: 'rgba(214,226,240,0.70)',
      accent: '#ffd25e', glow: 18, panel: 'rgba(8,20,40,0.72)', font: '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
      pal: ['#38f2a2', '#ffd25e', '#5ab0ff', '#ff6b8e', '#b993ff', '#ffa24c', '#3fe0f0', '#c8f07a', '#ff8ad8', '#9ad0ff'], q: ['#38f2a2', '#ffd25e', '#ff6b8e', '#5ab0ff'] },
    clean: { name: 'Clean (light)', bg: ['#fbfaf7', '#f3f2ee', '#ebe9e3'], grid: 'rgba(29,29,27,0.08)', axis: 'rgba(29,29,27,0.45)', text: '#1d1d1b', muted: 'rgba(61,60,57,0.75)',
      accent: '#17734a', glow: 0, panel: 'rgba(252,252,251,0.86)', font: '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
      pal: ['#2a78d6', '#d9822b', '#17734a', '#8a4fd6', '#c0392b', '#16a085', '#7a7974', '#b5446e', '#3b5bdb', '#e67700'], q: ['#17734a', '#c98a00', '#c0392b', '#2a78d6'] },
    terminal: { name: 'Terminal', bg: ['#020604', '#04100a', '#061a10'], grid: 'rgba(80,255,150,0.08)', axis: 'rgba(120,255,170,0.45)', text: '#c6ffd9', muted: 'rgba(150,230,180,0.7)',
      accent: '#ffb000', glow: 12, panel: 'rgba(2,12,6,0.78)', font: '"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace',
      pal: ['#39ff88', '#ffb000', '#4dd2ff', '#ff5f6d', '#d78bff', '#f0f06a', '#7dffcf', '#ff9e57', '#9fb4ff', '#ffffff'], q: ['#39ff88', '#ffb000', '#ff5f6d', '#4dd2ff'] },
    sunset: { name: 'Sunset', bg: ['#1a0f2e', '#33163f', '#4a1d3f'], grid: 'rgba(255,200,220,0.09)', axis: 'rgba(255,215,230,0.5)', text: '#fff2f6', muted: 'rgba(255,225,235,0.72)',
      accent: '#ffcf70', glow: 16, panel: 'rgba(30,12,40,0.72)', font: '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
      pal: ['#ffcf70', '#ff6f91', '#7ad7ff', '#a0ff9d', '#d6a2ff', '#ff9a5a', '#5effe0', '#ffe3a3', '#ffa7d1', '#b3c7ff'], q: ['#a0ff9d', '#ffcf70', '#ff6f91', '#7ad7ff'] },
  };

  /* ---------- drawing ---------- */
  function niceTicks(lo, hi, n = 5) {
    if (!(hi > lo)) return [lo];
    const step0 = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(step0))), m = [1, 2, 2.5, 5, 10].find((x) => x * p >= step0) * p;
    const out = []; for (let v = Math.ceil(lo / m) * m; v <= hi + 1e-9; v += m) out.push(+v.toPrecision(12));
    return out;
  }
  const valAt = (arr, f) => {                              // linear between weeks, null where a week is missing
    const i = Math.floor(f), j = Math.min(arr.length - 1, i + 1), a = arr[clamp(i, 0, arr.length - 1)], b = arr[j];
    if (!fin(a)) return fin(b) && f - i > 0.5 ? b : null;
    return fin(b) ? lerp(a, b, f - i) : a;
  };
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  const alpha = (hex, a) => { if (!/^#/.test(hex)) return hex; const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };

  // the timeline: a short intro, the run, the hold on the last week (with the end card)
  function timing(V, dur) {
    const D = Math.max(4, dur), intro = Math.min(0.8, D * 0.06), hold = V.endCard ? Math.min(3.2, D * 0.18) : Math.min(1.2, D * 0.06);
    return { D, intro, hold, run: D - intro - hold };
  }
  function frameIndex(V, tm, t) {                          // a gentle start and stop around a steady pace
    const n = V.grid.length - 1, u = clamp((t - tm.intro) / tm.run, 0, 1);
    const e = 0.82 * u + 0.18 * (u * u * (3 - 2 * u));
    return n * e;
  }

  function draw(ctx, W, H, V, opt, t) {
    const th = THEMES[opt.theme] || THEMES.bull, S = Math.min(W, H) / 1080, tm = timing(V, opt.dur), f = frameIndex(V, tm, t);
    const portrait = H > W * 1.2, square = !portrait && H > W * 0.8;
    const pal = (i) => th.pal[i % th.pal.length];
    const F = (w, px) => `${w} ${Math.round(px * S)}px ${th.font}`;
    // background: a deep gradient, a soft light, a faint grid of dots
    const g = ctx.createLinearGradient(0, 0, W * 0.4, H);
    g.addColorStop(0, th.bg[0]); g.addColorStop(0.55, th.bg[1]); g.addColorStop(1, th.bg[2]);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    const rg = ctx.createRadialGradient(W * 0.78, H * 0.18, 10, W * 0.78, H * 0.18, Math.max(W, H) * 0.75);
    rg.addColorStop(0, alpha(th.accent, opt.theme === 'clean' ? 0.08 : 0.16)); rg.addColorStop(1, alpha(th.accent, 0));
    ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
    // the layout: title on top, the chart below; on a phone-shaped frame the live values get their own band
    const pad = 64 * S, titleY = (portrait ? 150 : 92) * S;
    const intro = clamp(t / Math.max(0.01, tm.intro), 0, 1), ein = 1 - Math.pow(1 - intro, 3);
    ctx.globalAlpha = ein; ctx.fillStyle = th.text; ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
    ctx.font = F(700, portrait ? 60 : 54);
    wrap(ctx, V.title, pad, titleY - (1 - ein) * 30 * S, W - 2 * pad, (portrait ? 70 : 62) * S, 2);
    ctx.font = F(400, portrait ? 30 : 26); ctx.fillStyle = th.muted;
    const titleLines = lines(ctx, V.title, W - 2 * pad, F(700, portrait ? 60 : 54));
    const subY = titleY + (titleLines - 1) * (portrait ? 70 : 62) * S + (portrait ? 54 : 44) * S;
    wrap(ctx, V.sub, pad, subY, W - 2 * pad, (portrait ? 38 : 32) * S, 2);
    ctx.globalAlpha = 1;
    let top = subY + (portrait ? 70 : 54) * S;
    const bottom = H - (portrait ? 230 : 96) * S;
    // live values band (counters) for line / area styles on tall or square frames
    const style = V.style;
    if ((portrait || square) && (style === 'line' || style === 'area') && V.kind !== 'rrg') {
      top = counters(ctx, V, f, top, W, S, th, F, pal, portrait ? 2 : Math.min(4, V.series.length)) + 26 * S;
    }
    const box = { x: pad + (style === 'bars' ? 0 : 70 * S), y: top, w: W - 2 * pad - (style === 'bars' ? 0 : 70 * S) - (style === 'line' || style === 'area' ? (portrait ? 150 : 210) * S : 0), h: bottom - top };
    if (style === 'rrg') rrgChart(ctx, V, f, box, S, th, F, pal);
    else if (style === 'bars') barRace(ctx, V, f, box, S, th, F, pal);
    else if (style === 'tiles') tiles(ctx, V, f, box, S, th, F, pal, t, tm);
    else if (style === 'columns') columns(ctx, V, f, box, S, th, F, pal);
    else if (V.panels && (style === 'line' || style === 'area')) {
      const n = V.series.length, gap = 54 * S, ph = (box.h - gap * (n - 1)) / n;
      V.series.forEach((s, i) => { const sub = Object.assign({}, V, { series: [s], zero: s.v.some((x) => x < 0) && s.v.some((x) => x > 0) }); lineRace(ctx, sub, f, { x: box.x, y: box.y + i * (ph + gap), w: box.w, h: ph }, S, th, F, (j) => pal(i + j), style === 'area', i < n - 1); });
    } else lineRace(ctx, V, f, box, S, th, F, pal, style === 'area');
    // the date, large and faint; the brand mark; the progress hairline
    const k = clamp(Math.round(f), 0, V.grid.length - 1);
    ctx.textAlign = 'right'; ctx.fillStyle = alpha(th.text === '#1d1d1b' ? '#1d1d1b' : '#ffffff', opt.theme === 'clean' ? 0.10 : 0.12);
    ctx.font = F(700, portrait ? 120 : 110);
    ctx.fillText(V.quarterly ? quarterLabel(V.grid[k]) : monthYear(V.grid[k]), W - pad, bottom - (style === 'bars' ? 10 : 24) * S);
    brand(ctx, W, H, S, th, F, portrait);
    ctx.fillStyle = alpha(th.accent, 0.9); ctx.fillRect(0, H - 6 * S, W * clamp(t / tm.D, 0, 1), 6 * S);
    if (V.endCard && t > tm.D - tm.hold) endCard(ctx, V, W, H, S, th, F, pal, clamp((t - (tm.D - tm.hold)) / 0.6, 0, 1), portrait);
  }
  const quarterLabel = (ms) => { const d = new Date(ms); return 'Q' + (Math.floor(d.getUTCMonth() / 3) + 1) + ' ' + d.getUTCFullYear(); };
  function lines(ctx, text, maxW, font) { ctx.save(); ctx.font = font; let n = 1, line = ''; for (const w of String(text || '').split(' ')) { const tt = line ? line + ' ' + w : w; if (ctx.measureText(tt).width > maxW && line) { n++; line = w; } else line = tt; } ctx.restore(); return Math.min(n, 2); }
  function wrap(ctx, text, x, y, maxW, lh, max) {
    let line = '', n = 0; const words = String(text || '').split(' ');
    for (let i = 0; i < words.length; i++) {
      const tt = line ? line + ' ' + words[i] : words[i];
      if (ctx.measureText(tt).width > maxW && line) {
        if (n === max - 1) { let s = line; while (ctx.measureText(s + '…').width > maxW && s.length) s = s.slice(0, -1); ctx.fillText(s + '…', x, y + n * lh); return; }
        ctx.fillText(line, x, y + n * lh); n++; line = words[i];
      } else line = tt;
    }
    if (line) ctx.fillText(line, x, y + n * lh);
  }
  function brand(ctx, W, H, S, th, F, portrait) {
    const x = W - 64 * S, y = H - (portrait ? 120 : 34) * S;
    ctx.textAlign = 'right'; ctx.font = F(600, 24); ctx.fillStyle = th.muted;
    ctx.fillText('filing-flows.com', x, y);
    const w = ctx.measureText('filing-flows.com').width, bx = x - w - 46 * S, by = y - 22 * S;
    ctx.fillStyle = '#9b9a95'; ctx.fillRect(bx, by, 8 * S, 24 * S);
    ctx.fillStyle = '#38c88a'; ctx.fillRect(bx + 11 * S, by + 4 * S, 8 * S, 20 * S);
    ctx.fillStyle = '#ef6b55'; ctx.fillRect(bx + 22 * S, by + 10 * S, 8 * S, 14 * S);
  }
  function counters(ctx, V, f, top, W, S, th, F, pal, per) {
    const pad = 64 * S, gap = 18 * S, n = V.series.length, cols = Math.min(per, n), rows = Math.ceil(n / cols), cw = (W - 2 * pad - gap * (cols - 1)) / cols, ch = 104 * S;
    V.series.forEach((s, i) => {
      const r = Math.floor(i / cols), c = i % cols, x = pad + c * (cw + gap), y = top + r * (ch + gap), v = valAt(s.v, f);
      ctx.fillStyle = th.panel; roundRect(ctx, x, y, cw, ch, 16 * S); ctx.fill();
      ctx.fillStyle = pal(i); ctx.fillRect(x, y + 14 * S, 6 * S, ch - 28 * S);
      ctx.textAlign = 'left'; ctx.font = F(700, 28); ctx.fillStyle = pal(i); ctx.fillText(s.label, x + 22 * S, y + 40 * S);
      ctx.font = F(700, 40); ctx.fillStyle = th.text; ctx.fillText(V.fmt(v), x + 22 * S, y + 86 * S);
      if (V.base && fin(v)) { ctx.textAlign = 'right'; ctx.font = F(600, 24); ctx.fillStyle = v >= V.base ? '#3ee39a' : '#ff6b6b'; ctx.fillText(pctf(v / V.base - 1), x + cw - 18 * S, y + 40 * S); }
    });
    return top + rows * (ch + gap) - gap;
  }
  function yRange(V, f, area) {
    let lo = Infinity, hi = -Infinity;
    const n = Math.floor(f);
    for (const s of V.series) {
      for (let i = 0; i <= n && i < s.v.length; i++) if (fin(s.v[i])) { lo = Math.min(lo, s.v[i]); hi = Math.max(hi, s.v[i]); }
      const v = valAt(s.v, f); if (fin(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      if (area && s.price) for (let i = 0; i <= n; i++) if (fin(s.price[i])) lo = Math.min(lo, s.price[i]);
    }
    if (V.base) { lo = Math.min(lo, V.base); hi = Math.max(hi, V.base); }
    if (V.zero || area) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (!Number.isFinite(lo)) return [0, 1];
    if (hi - lo < 1e-9) { hi += Math.abs(hi) * 0.05 || 1; lo -= Math.abs(lo) * 0.05 || 1; }
    const span = hi - lo;
    return [lo - span * (V.zero || area || lo === 0 ? 0.04 : 0.08), hi + span * 0.1];
  }
  function lineRace(ctx, V, f, b, S, th, F, pal, area, noYears) {
    const G = V.grid, n = G.length, tEnd = G[n - 1], tCur = lerp(G[Math.floor(f)], G[Math.min(n - 1, Math.floor(f) + 1)], f - Math.floor(f));
    const xMax = Math.max(tCur, G[0] + (tEnd - G[0]) * 0.12), X = (t) => b.x + (t - G[0]) / ((xMax - G[0]) || 1) * b.w;
    const log = V.scale === 'log' && V.series.every((s) => s.v.every((v) => !fin(v) || v > 0));
    let [lo, hi] = yRange(V, f, area);
    if (log) { lo = Math.log(Math.max(lo, 1e-9)); hi = Math.log(hi); }
    const Y = (v) => b.y + b.h - ((log ? Math.log(Math.max(v, 1e-9)) : v) - lo) / ((hi - lo) || 1) * b.h;
    // grid and axes
    ctx.lineWidth = 1.2 * S; ctx.font = F(500, 22); ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    const ticks = log ? niceTicks(Math.exp(lo), Math.exp(hi), 5) : niceTicks(lo, hi, 5);
    for (const v of ticks) { const y = Y(v); if (y < b.y - 2 || y > b.y + b.h + 2) continue; ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText(V.unit === '$' ? money(v) : V.unit === '%' ? (V.kind === 'fund' ? (100 * v).toFixed(0) + '%' : pctf(v, 0)) : plain(v), b.x - 14 * S, y); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const years = []; for (let y = new Date(G[0]).getUTCFullYear() + 1; y <= new Date(xMax).getUTCFullYear(); y++) years.push(y);
    const every = Math.max(1, Math.ceil(years.length / (b.w / (110 * S))));
    years.forEach((yr, i) => { if (i % every) return; const x = X(Date.UTC(yr, 0, 1)); if (x < b.x + 20 * S || x > b.x + b.w) return; ctx.fillStyle = th.axis; if (!noYears) ctx.fillText(String(yr), x, b.y + b.h + 12 * S); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(x, b.y); ctx.lineTo(x, b.y + b.h); ctx.stroke(); });
    if (V.base) { const y = Y(V.base); ctx.setLineDash([8 * S, 8 * S]); ctx.strokeStyle = th.axis; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.setLineDash([]); ctx.textAlign = 'right'; ctx.textBaseline = 'top'; ctx.font = F(500, 20); ctx.fillStyle = th.muted; ctx.fillText(money(V.base, 0) + ' invested', b.x + b.w - 8 * S, y + 8 * S); }
    if (V.zero && !V.base && lo < 0 && hi > 0) { const y = Y(0); ctx.strokeStyle = th.axis; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); }
    // the lines, drawn up to this frame; the newest point between two weeks
    const heads = [];
    ctx.save(); ctx.beginPath(); ctx.rect(b.x - 4 * S, b.y - 40 * S, b.w + 8 * S, b.h + 44 * S); ctx.clip();
    V.series.forEach((s, k) => {
      const col = pal(k), pts = [];
      for (let i = 0; i <= Math.floor(f) && i < n; i++) if (fin(s.v[i])) pts.push([X(G[i]), Y(s.v[i]), i]);
      const hv = valAt(s.v, f); if (fin(hv)) pts.push([X(tCur), Y(hv), f]);
      if (pts.length < 1) return;
      if (area || (k === 0 && V.series.length <= 3)) {                    // a soft fill under the line
        const band = area && V.split && s.price, fillTo = band ? null : (V.zero && !log && lo < 0 ? Y(0) : b.y + b.h);
        const gr = ctx.createLinearGradient(0, b.y, 0, b.y + b.h); gr.addColorStop(0, alpha(col, area ? 0.30 : 0.18)); gr.addColorStop(1, alpha(col, 0));
        ctx.fillStyle = gr; ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
        if (fillTo != null) { ctx.lineTo(pts[pts.length - 1][0], fillTo); ctx.lineTo(pts[0][0], fillTo); }
        else {                                                            // distributions: the band between price and price + cash
          for (let j = pts.length - 1; j >= 0; j--) { const i = pts[j][2], pv = j === pts.length - 1 ? valAt(s.price, f) : s.price[i]; ctx.lineTo(pts[j][0], Y(fin(pv) ? pv : 0)); }
        }
        ctx.closePath(); ctx.fill();
      }
      if (s.price && V.split) {                                          // the price alone, dashed
        ctx.setLineDash([10 * S, 8 * S]); ctx.strokeStyle = alpha(col, 0.8); ctx.lineWidth = 3 * S; ctx.beginPath();
        let started = false;
        for (let i = 0; i <= Math.floor(f); i++) if (fin(s.price[i])) { const x = X(G[i]), y = Y(s.price[i]); if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y); }
        const pv = valAt(s.price, f); if (fin(pv)) ctx.lineTo(X(tCur), Y(pv));
        ctx.stroke(); ctx.setLineDash([]);
      }
      ctx.strokeStyle = col; ctx.lineWidth = 5 * S; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * S; }
      ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.stroke();
      ctx.shadowBlur = 0;
      const h = pts[pts.length - 1];
      heads.push({ x: h[0], y: h[1], col, s, v: hv, k });
    });
    ctx.restore();
    // heads: a dot with a halo; labels to the right, pushed apart so they never overlap
    heads.forEach((h) => { ctx.fillStyle = alpha(h.col, 0.25); ctx.beginPath(); ctx.arc(h.x, h.y, 16 * S, 0, 7); ctx.fill(); ctx.fillStyle = h.col; ctx.beginPath(); ctx.arc(h.x, h.y, 8 * S, 0, 7); ctx.fill(); });
    const lh = (V.split ? 76 : 54) * S, sorted = heads.slice().sort((a, c) => a.y - c.y);
    sorted.forEach((h, i) => { h.ly = Math.max(h.y, i ? sorted[i - 1].ly + lh : b.y + lh / 2); });
    for (let i = sorted.length - 1; i >= 0; i--) { const lim = i === sorted.length - 1 ? b.y + b.h - lh / 2 : sorted[i + 1].ly - lh; if (sorted[i].ly > lim) sorted[i].ly = lim; }
    sorted.forEach((h) => {
      ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
      const txt = `${h.s.label}  ${V.fmt(h.v)}`; ctx.font = F(700, 26);
      const w = ctx.measureText(txt).width + 24 * S, x = Math.min(h.x + 22 * S, ctx.canvas.width - 24 * S - w);
      ctx.fillStyle = alpha(h.col, 0.92); roundRect(ctx, x, h.ly - 20 * S, w, 40 * S, 12 * S); ctx.fill();
      ctx.fillStyle = luminance(h.col) > 0.55 ? '#0b1220' : '#ffffff'; ctx.fillText(txt, x + 12 * S, h.ly + 1 * S);
      if (V.split && h.s.cash) { const c = valAt(h.s.cash, f); ctx.font = F(500, 19); ctx.fillStyle = th.muted; ctx.fillText(`${money(c)} from distributions`, x + 4 * S, h.ly + 32 * S); }
    });
  }
  function luminance(hex) { if (!/^#/.test(hex)) return 0.5; const n = parseInt(hex.slice(1), 16); return (0.299 * (n >> 16 & 255) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255; }
  function barRace(ctx, V, f, b, S, th, F, pal) {
    const i0 = Math.floor(f), i1 = Math.min(V.grid.length - 1, i0 + 1), fr = f - i0;
    const rank = (i) => V.series.map((s, k) => ({ k, v: s.v[i] })).sort((a, c) => (fin(c.v) ? c.v : -Infinity) - (fin(a.v) ? a.v : -Infinity)).map((x, r) => [x.k, r]);
    const r0 = new Map(rank(i0)), r1 = new Map(rank(i1));
    const n = V.series.length, slot = b.h / Math.max(n, 4), bh = slot * 0.72;
    const vals = V.series.map((s) => valAt(s.v, f)), finite = vals.filter(fin);
    const pos = Math.max(0, ...finite), negm = Math.max(0, ...finite.map((v) => -v)), neg = negm > 0;
    // with values below zero the axis moves right in proportion, and each ticker sits on the far side of its bar's start
    const lab = neg ? 0 : 150 * S, room = b.w - lab - (neg ? 300 : 140) * S;
    const share = neg ? clamp(negm / ((negm + pos) || 1), pos > 0 ? 0.18 : 0.8, pos > 0 ? 0.82 : 0.8) : 0;
    const x0 = b.x + lab + (neg ? 150 * S + room * share : 0), unit = room / Math.max(1e-9, neg ? (pos > 0 ? Math.max(negm / share, pos / (1 - share)) : negm / share) : pos), wMax = null;
    if (neg) { ctx.strokeStyle = th.axis; ctx.lineWidth = 2 * S; ctx.beginPath(); ctx.moveTo(x0, b.y); ctx.lineTo(x0, b.y + b.h); ctx.stroke(); }
    V.series.forEach((s, k) => {
      const r = lerp(r0.get(k), r1.get(k), easeIO(fr)), y = b.y + r * slot + (slot - bh) / 2, v = vals[k];
      if (!fin(v)) return;
      const w = Math.abs(v) * unit, x = v >= 0 ? x0 : x0 - w, col = pal(k);
      const gr = ctx.createLinearGradient(x, 0, x + w, 0); gr.addColorStop(0, alpha(col, 0.75)); gr.addColorStop(1, col);
      ctx.fillStyle = gr; if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * 0.8 * S; }
      roundRect(ctx, x, y, Math.max(w, 6 * S), bh, Math.min(14 * S, bh / 3)); ctx.fill(); ctx.shadowBlur = 0;
      ctx.textBaseline = 'middle'; ctx.font = F(700, 30); ctx.fillStyle = th.text;
      if (neg) { ctx.textAlign = v >= 0 ? 'right' : 'left'; ctx.fillText(s.label, v >= 0 ? x0 - 14 * S : x0 + 14 * S, y + bh / 2); }
      else { ctx.textAlign = 'right'; ctx.fillText(s.label, b.x + lab - 18 * S, y + bh / 2); }
      ctx.textAlign = v >= 0 ? 'left' : 'right'; ctx.font = F(700, 28); ctx.fillStyle = th.text;
      ctx.fillText(V.fmt(v), v >= 0 ? x + w + 14 * S : x - 14 * S, y + bh / 2);
      if (s.name && s.name !== s.label && bh > 54 * S && w > 260 * S) { ctx.textAlign = 'left'; ctx.font = F(500, 20); ctx.fillStyle = luminance(col) > 0.55 ? 'rgba(10,18,32,0.75)' : 'rgba(255,255,255,0.85)'; ctx.fillText(String(s.name).slice(0, 34), x + 14 * S, y + bh / 2); }
    });
  }
  const easeIO = (u) => u * u * (3 - 2 * u);
  function tiles(ctx, V, f, b, S, th, F, pal) {
    const n = V.series.length, cols = n <= 2 ? n : n <= 4 ? 2 : 3, rows = Math.ceil(n / cols), gap = 22 * S;
    const cw = (b.w + 70 * S - gap * (cols - 1)) / cols, ch = Math.min((b.h - gap * (rows - 1)) / rows, cw * 0.9), x00 = b.x - 70 * S;
    V.series.forEach((s, k) => {
      const c = k % cols, r = Math.floor(k / cols), x = x00 + c * (cw + gap), y = b.y + r * (ch + gap), col = pal(k), v = valAt(s.v, f);
      ctx.fillStyle = th.panel; roundRect(ctx, x, y, cw, ch, 22 * S); ctx.fill();
      ctx.strokeStyle = alpha(col, 0.55); ctx.lineWidth = 2 * S; ctx.stroke();
      ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.font = F(700, 34); ctx.fillStyle = col; ctx.fillText(s.label, x + 28 * S, y + 58 * S);
      ctx.font = F(500, 20); ctx.fillStyle = th.muted; ctx.fillText(String(s.name || '').slice(0, 40), x + 28 * S, y + 88 * S);
      ctx.font = F(700, Math.min(84, ch / S * 0.26)); ctx.fillStyle = th.text; ctx.fillText(V.fmt(v), x + 28 * S, y + ch * 0.55);
      const v0 = s.v.find(fin);
      if (fin(v) && fin(v0) && v0 !== 0 && V.unit !== '%') { ctx.font = F(700, 30); ctx.fillStyle = v >= v0 ? '#3ee39a' : '#ff6b6b'; ctx.fillText(pctf(v / v0 - 1), x + 28 * S, y + ch * 0.55 + 46 * S); }
      // a sparkline, drawn up to this frame
      const sx = x + 28 * S, sw = cw - 56 * S, sy = y + ch * 0.68, sh = ch * 0.24, vs = s.v.filter(fin);
      if (vs.length > 1) {
        const lo = Math.min(...vs), hi = Math.max(...vs), N = s.v.length - 1;
        ctx.strokeStyle = col; ctx.lineWidth = 3.5 * S; if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * 0.6 * S; }
        ctx.beginPath(); let st0 = false;
        for (let i = 0; i <= Math.floor(f); i++) if (fin(s.v[i])) { const px = sx + i / N * sw, py = sy + sh - (s.v[i] - lo) / ((hi - lo) || 1) * sh; if (!st0) { ctx.moveTo(px, py); st0 = true; } else ctx.lineTo(px, py); }
        ctx.stroke(); ctx.shadowBlur = 0;
      }
    });
  }
  function columns(ctx, V, f, b, S, th, F, pal) {
    const G = V.grid, n = G.length, m = V.series.length, slot = b.w / n, gw = slot * 0.78, bw = gw / m;
    let hi = 0, lo = 0;
    for (const s of V.series) for (let i = 0; i <= Math.min(n - 1, Math.ceil(f)); i++) if (fin(s.v[i])) { hi = Math.max(hi, s.v[i]); lo = Math.min(lo, s.v[i]); }
    hi = hi * 1.12 || 1; lo = lo * 1.12;
    const Y = (v) => b.y + b.h - (v - lo) / ((hi - lo) || 1) * b.h;
    ctx.font = F(500, 22); ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.lineWidth = 1.2 * S;
    for (const v of niceTicks(lo, hi, 5)) { const y = Y(v); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText(V.fmt(v), b.x - 14 * S, y); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const every = Math.max(1, Math.ceil(n / (b.w / (120 * S))));
    G.forEach((g, i) => { if (i % every === 0 || i === n - 1) { ctx.fillStyle = th.axis; ctx.font = F(500, 20); ctx.fillText(quarterLabel(g), b.x + (i + 0.5) * slot, b.y + b.h + 12 * S); } });
    for (let i = 0; i < n; i++) {
      const grow = clamp(f - i + 1, 0, 1); if (grow <= 0) continue;
      const e = 1 - Math.pow(1 - grow, 3);
      V.series.forEach((s, k) => {
        const v = s.v[i]; if (!fin(v)) return;
        const x = b.x + i * slot + (slot - gw) / 2 + k * bw, y0 = Y(0), y1 = Y(v * e), col = pal(k);
        const gr = ctx.createLinearGradient(0, y1, 0, y0); gr.addColorStop(0, col); gr.addColorStop(1, alpha(col, 0.55));
        ctx.fillStyle = gr; if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * 0.5 * S; }
        roundRect(ctx, x + bw * 0.06, Math.min(y0, y1), bw * 0.88, Math.max(2 * S, Math.abs(y1 - y0)), Math.min(8 * S, bw * 0.2)); ctx.fill(); ctx.shadowBlur = 0;
        if (i === Math.min(n - 1, Math.floor(f + 0.999)) && grow > 0.3) { ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.font = F(700, m > 2 ? 20 : 26); ctx.fillStyle = th.text; ctx.fillText(V.fmt(v * e), x + bw / 2, Math.min(y0, y1) - 8 * S); }
      });
    }
    if (m > 1) { ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; let lx = b.x; V.series.forEach((s, k) => { ctx.fillStyle = pal(k); ctx.fillRect(lx, b.y - 30 * S, 22 * S, 22 * S); ctx.fillStyle = th.text; ctx.font = F(600, 24); ctx.fillText(s.label, lx + 30 * S, b.y - 19 * S); lx += ctx.measureText(s.label).width + 70 * S; }); }
  }
  function rrgChart(ctx, V, f, b, S, th, F, pal) {
    if (!V._dom) {                                          // one fixed domain for the whole video, so it never rescales
      const xs = [], ys = [];
      for (const s of V.series) s.x.forEach((v, i) => { if (fin(v) && fin(s.y[i])) { xs.push(Math.abs(v - 100)); ys.push(Math.abs(s.y[i] - 100)); } });
      const q = (a) => { const s = a.sort((u, w) => u - w); return s.length ? s[Math.floor(0.985 * (s.length - 1))] : 1; };
      V._dom = { mx: Math.max(1.2, q(xs) * 1.1), my: Math.max(1.2, q(ys) * 1.1) };
    }
    const { mx, my } = V._dom, side = Math.min(b.w + 70 * S, b.h), x0 = b.x - 70 * S + (b.w + 70 * S - side) / 2, y0 = b.y;
    const X = (v) => x0 + (clamp(v, 100 - mx, 100 + mx) - (100 - mx)) / (2 * mx) * side, Y = (v) => y0 + side - (clamp(v, 100 - my, 100 + my) - (100 - my)) / (2 * my) * side;
    const cx = X(100), cy = Y(100), Q = th.q;
    [[cx, y0, x0 + side - cx, cy - y0, Q[0]], [cx, cy, x0 + side - cx, y0 + side - cy, Q[1]], [x0, cy, cx - x0, y0 + side - cy, Q[2]], [x0, y0, cx - x0, cy - y0, Q[3]]]
      .forEach(([x, y, w, h, c]) => { ctx.fillStyle = alpha(c, 0.09); ctx.fillRect(x, y, w, h); });
    ctx.strokeStyle = th.axis; ctx.lineWidth = 1.6 * S; ctx.beginPath(); ctx.moveTo(cx, y0); ctx.lineTo(cx, y0 + side); ctx.moveTo(x0, cy); ctx.lineTo(x0 + side, cy); ctx.stroke();
    ctx.font = F(700, 30); ctx.textBaseline = 'top';
    [['Leading', x0 + side - 16 * S, y0 + 14 * S, 'right', Q[0]], ['Weakening', x0 + side - 16 * S, y0 + side - 48 * S, 'right', Q[1]], ['Lagging', x0 + 16 * S, y0 + side - 48 * S, 'left', Q[2]], ['Improving', x0 + 16 * S, y0 + 14 * S, 'left', Q[3]]]
      .forEach(([tx, x, y, a, c]) => { ctx.textAlign = a; ctx.fillStyle = alpha(c, 0.9); ctx.fillText(tx, x, y); });
    ctx.font = F(500, 20); ctx.fillStyle = th.muted; ctx.textAlign = 'center'; ctx.fillText('RS-Ratio → (relative trend vs ' + V.bench + ')', x0 + side / 2, y0 + side + 10 * S);
    const tail = V.tail, labels = [];
    V.series.forEach((s, k) => {
      const col = pal(k), pts = [];
      for (let i = Math.max(0, Math.floor(f) - tail + 1); i <= Math.floor(f); i++) if (fin(s.x[i]) && fin(s.y[i])) pts.push([X(s.x[i]), Y(s.y[i])]);
      const hx = valAt(s.x, f), hy = valAt(s.y, f); if (fin(hx) && fin(hy)) pts.push([X(hx), Y(hy)]);
      if (!pts.length) return;
      for (let i = 1; i < pts.length; i++) { ctx.strokeStyle = alpha(col, 0.15 + 0.85 * i / pts.length); ctx.lineWidth = (2 + 4 * i / pts.length) * S; ctx.beginPath(); ctx.moveTo(pts[i - 1][0], pts[i - 1][1]); ctx.lineTo(pts[i][0], pts[i][1]); ctx.stroke(); }
      pts.slice(0, -1).forEach((p, i) => { ctx.fillStyle = alpha(col, 0.2 + 0.6 * i / pts.length); ctx.beginPath(); ctx.arc(p[0], p[1], 4 * S, 0, 7); ctx.fill(); });
      const h = pts[pts.length - 1];
      if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * S; }
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(h[0], h[1], 13 * S, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
      labels.push({ x: h[0], y: h[1], t: s.label, col });
    });
    ctx.font = F(700, 26); ctx.textBaseline = 'middle';
    labels.sort((a, c) => a.y - c.y).forEach((l, i, arr) => { if (i && Math.abs(l.y - arr[i - 1].ly) < 30 * S && Math.abs(l.x - arr[i - 1].x) < 160 * S) l.ly = arr[i - 1].ly + 30 * S; else l.ly = l.y; ctx.textAlign = 'left'; ctx.fillStyle = th.text; ctx.fillText(l.t, l.x + 20 * S, l.ly); });
  }
  function endCard(ctx, V, W, H, S, th, F, pal, a, portrait) {
    const rows = V.final.slice(0, portrait ? 8 : 6);
    ctx.fillStyle = `rgba(0,0,0,${0.45 * a})`; ctx.fillRect(0, 0, W, H);
    const w = Math.min(W - 120 * S, (portrait ? 920 : 1100) * S), rh = 74 * S, h = 150 * S + rows.length * rh, x = (W - w) / 2, y = (H - h) / 2 + (1 - a) * 40 * S;
    ctx.globalAlpha = a; ctx.fillStyle = th.panel; roundRect(ctx, x, y, w, h, 28 * S); ctx.fill();
    ctx.strokeStyle = alpha(th.accent, 0.6); ctx.lineWidth = 2 * S; ctx.stroke();
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.fillStyle = th.accent; ctx.font = F(700, 34);
    ctx.fillText(V.endTitle, x + 40 * S, y + 70 * S);
    ctx.font = F(500, 22); ctx.fillStyle = th.muted; ctx.fillText(V.endSub, x + 40 * S, y + 108 * S);
    rows.forEach((r, i) => {
      const yy = y + 150 * S + i * rh + rh / 2;
      ctx.fillStyle = pal(r.k); ctx.beginPath(); ctx.arc(x + 54 * S, yy - 10 * S, 12 * S, 0, 7); ctx.fill();
      ctx.font = F(700, 34); ctx.fillStyle = th.text; ctx.textAlign = 'left'; ctx.fillText(r.label, x + 84 * S, yy);
      ctx.textAlign = 'right'; ctx.fillText(r.value, x + w - (r.change ? 210 : 40) * S, yy);
      if (r.change) { ctx.fillStyle = r.up ? '#3ee39a' : '#ff6b6b'; ctx.fillText(r.change, x + w - 40 * S, yy); }
    });
    ctx.globalAlpha = 1;
  }
  // the end card's rows and headline, from the last week
  function finish(V, st) {
    const L = V.grid.length - 1;
    const rows = V.series.map((s, k) => {
      if (V.kind === 'rrg') { const x = s.x[L], y = s.y[L]; const q = fin(x) && fin(y) ? (x >= 100 ? (y >= 100 ? 'Leading' : 'Weakening') : (y < 100 ? 'Lagging' : 'Improving')) : '—'; return { k, label: s.label, value: q, v: fin(x) ? x : -Infinity }; }
      const v = s.v[L], v0 = s.v.find(fin);
      const change = V.base ? pctf(v / V.base - 1) : (fin(v0) && v0 !== 0 && V.unit !== '%' && V.kind !== 'formula' ? pctf(v / v0 - 1) : '');
      return { k, label: s.label, value: V.fmt(v), change, up: V.base ? v >= V.base : v >= v0, v: fin(v) ? v : -Infinity };
    }).sort((a, b) => b.v - a.v);
    V.final = rows;
    if (V.kind === 'formula' && V.series.length > 1) {          // lines of very different sizes get a panel each
      const mags = V.series.map((s) => Math.max(...s.v.filter(fin).map(Math.abs), 1e-12));
      V.panels = Math.max(...mags) / Math.min(...mags) > 8;
    }
    V.endTitle = V.kind === 'rrg' ? 'Where they stand' : V.kind === 'growth' ? (rows[0] ? `${rows[0].label} ${rows[0].value} (${rows[0].change})` : '') : (V.metric || V.title);
    V.endSub = `${dayLabel(V.grid[0])} → ${dayLabel(V.grid[L])}` + (V.kind === 'growth' ? (V.split ? ' · price + distributions as cash' : st.div === 'price' ? ' · price only' : ' · distributions reinvested') : '');
    V.caption = V.kind === 'growth' ? rows.map((r) => `${r.label} ${r.value} (${r.change})`).join(' vs ') : V.kind === 'rrg' ? rows.map((r) => `${r.label}: ${r.value}`).join(' · ') : rows.map((r) => `${r.label} ${r.value}${r.change ? ' (' + r.change + ')' : ''}`).join(' · ');
  }

  /* ---------- export: WebCodecs + mp4-muxer, or MediaRecorder ---------- */
  const MUXER = 'https://cdn.jsdelivr.net/npm/mp4-muxer@5.1.5/build/mp4-muxer.js';
  let muxLoad = null;
  const loadMuxer = () => muxLoad || (muxLoad = root.Mp4Muxer ? Promise.resolve(root.Mp4Muxer) : new Promise((ok, bad) => {
    const s = document.createElement('script'); s.src = MUXER; s.onload = () => ok(root.Mp4Muxer); s.onerror = () => { muxLoad = null; bad(new Error('the MP4 writer did not load')); }; document.head.appendChild(s);
  }));
  async function pickCodec(w, h, fps) {
    if (typeof VideoEncoder === 'undefined') return null;
    const avc = fps > 30 ? ['avc1.640033', 'avc1.64002A', 'avc1.4D4033', 'avc1.42E033'] : ['avc1.640028', 'avc1.640033', 'avc1.4D4028', 'avc1.42E028', 'avc1.42E033'];
    for (const codec of avc) { try { const r = await VideoEncoder.isConfigSupported({ codec, width: w, height: h, bitrate: 8e6, framerate: fps, avc: { format: 'avc' } }); if (r.supported) return { codec, mux: 'avc' }; } catch (e) { /* next */ } }
    for (const codec of ['vp09.00.40.08', 'vp09.00.31.08']) { try { const r = await VideoEncoder.isConfigSupported({ codec, width: w, height: h, bitrate: 8e6, framerate: fps }); if (r.supported) return { codec, mux: 'vp9' }; } catch (e) { /* next */ } }
    return null;
  }
  async function exportMp4(V, opt, onProgress, cancel) {
    const dim = { '16x9': [1920, 1080], '9x16': [1080, 1920], '1x1': [1080, 1080] }[opt.ar] || [1920, 1080];
    const k = opt.q === '720' ? 2 / 3 : 1, w = Math.round(dim[0] * k / 2) * 2, h = Math.round(dim[1] * k / 2) * 2, fps = +opt.fps === 60 ? 60 : 30;
    const pick = await pickCodec(w, h, fps);
    if (!pick) return null;                                 // no WebCodecs: the caller records the preview instead
    const M = await loadMuxer();
    const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d');
    const muxer = new M.Muxer({ target: new M.ArrayBufferTarget(), video: { codec: pick.mux, width: w, height: h, frameRate: fps }, fastStart: 'in-memory' });
    let failed = null;
    const enc = new VideoEncoder({ output: (chunk, meta) => muxer.addVideoChunk(chunk, meta), error: (e) => { failed = e; } });
    enc.configure({ codec: pick.codec, width: w, height: h, bitrate: Math.round((fps > 30 ? 12e6 : 9e6) * k * k), framerate: fps, ...(pick.mux === 'avc' ? { avc: { format: 'avc' } } : {}) });
    const N = Math.round(timing(V, opt.dur).D * fps);
    for (let i = 0; i < N; i++) {
      if (failed) throw failed;
      if (cancel && cancel()) { enc.close(); return 'cancelled'; }
      draw(ctx, w, h, V, opt, i / fps);
      const frame = new VideoFrame(canvas, { timestamp: Math.round(i * 1e6 / fps), duration: Math.round(1e6 / fps) });
      enc.encode(frame, { keyFrame: i % (fps * 2) === 0 }); frame.close();
      if (enc.encodeQueueSize > 6) await new Promise((r) => setTimeout(r, 0));
      while (enc.encodeQueueSize > 12) await new Promise((r) => setTimeout(r, 4));
      if (i % 6 === 0) { onProgress(i / N); await new Promise((r) => setTimeout(r, 0)); }
    }
    await enc.flush(); enc.close();
    if (failed) throw failed;
    muxer.finalize();
    onProgress(1);
    return { blob: new Blob([muxer.target.buffer], { type: 'video/mp4' }), codec: pick.codec, w, h, fps, frames: N };
  }
  function recordPreview(canvas, V, opt, onProgress) {           // the fallback: record the canvas while it plays in real time
    return new Promise((ok, bad) => {
      if (!canvas.captureStream || typeof MediaRecorder === 'undefined') { bad(new Error('this browser cannot record video')); return; }
      const fps = +opt.fps === 60 ? 60 : 30, stream = canvas.captureStream(fps);
      const type = ['video/mp4;codecs=avc1', 'video/webm;codecs=vp9', 'video/webm'].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      const rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 8e6 } : undefined), parts = [];
      rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };
      rec.onstop = () => ok({ blob: new Blob(parts, { type: type.split(';')[0] || 'video/webm' }), codec: type || 'default', recorded: true });
      const ctx = canvas.getContext('2d'), D = timing(V, opt.dur).D, t0 = performance.now();
      rec.start(250);
      (function tick() { const t = (performance.now() - t0) / 1000; draw(ctx, canvas.width, canvas.height, V, opt, Math.min(t, D)); onProgress(Math.min(1, t / D)); if (t < D) requestAnimationFrame(tick); else setTimeout(() => rec.stop(), 120); })();
    });
  }

  /* ---------- the page ---------- */
  const TEMPLATES = [
    { name: '$10,000: QQQ vs SPY', note: 'Ten years, distributions reinvested', s: { k: 'growth', t: 'QQQ,SPY', from: '2016-10-28', amt: '10000', div: 'tr', style: 'line', theme: 'bull' } },
    { name: 'Dividend ETFs, split out', note: 'SCHD vs VYM vs SPY: price + cash', s: { k: 'growth', t: 'SCHD,VYM,SPY', from: '2016-10-28', amt: '10000', div: 'split', style: 'line', theme: 'bull' } },
    { name: 'Nasdaq · S&P · Russell · Dow', note: 'A bar race since 2015', s: { k: 'growth', t: 'QQQ,SPY,IWM,DIA', from: '2015-01-02', amt: '10000', div: 'tr', style: 'bars', theme: 'sunset' } },
    { name: 'Sector rotation', note: 'The RRG of the sector ETFs, two years', s: { k: 'rrg', t: 'XLK,XLF,XLE,XLV,XLY,XLP,XLI,XLU', from: iso(Date.now() - 730 * DAY), bench: 'SPY', tail: '8', style: 'rrg', theme: 'bull' } },
    { name: 'Momentum ranking', note: '26-week return vs SPY of eight ETFs', s: { k: 'momentum', t: 'QQQ,IWM,DIA,SMH,XLE,GLD,TLT,EEM', from: '2020-01-03', lb: '26', bench: 'SPY', style: 'bars', theme: 'terminal' } },
    { name: 'Nvidia revenue', note: 'Quarter by quarter from its filings', s: { k: 'fund', t: 'NVDA', m: 'revenue', ttm: '0', style: 'columns', theme: 'bull' } },
    { name: 'Big Tech earnings race', note: 'Net earnings, trailing four quarters', s: { k: 'fund', t: 'AAPL,MSFT,GOOGL,AMZN,META,NVDA', m: 'ni', ttm: '1', style: 'bars', theme: 'clean' } },
    { name: 'Growth vs value ratio', note: 'IWF ÷ IWD and QQQ ÷ SPY, rebased', s: { k: 'formula', expr: 'Growth ÷ value: rebase(IWF/IWD)\nNasdaq ÷ S&P: rebase(QQQ/SPY)', from: '2010-01-01', style: 'line', theme: 'clean' } },
  ];
  const dec = (v) => { try { return decodeURIComponent(v.replace(/\+/g, ' ')); } catch (e) { return v; } };
  function parseState(arg) {                               // arg: the address after #studio/, still encoded
    const st = { ...DEF }, given = new Set();
    for (const part of String(arg || '').split('&')) { const i = part.indexOf('='); if (i > 0) { const k = part.slice(0, i); if (k in DEF) { st[k] = dec(part.slice(i + 1)); given.add(k); } } }
    if (!STYLES[st.k]) st.k = 'growth';
    if (!given.has('style') || !STYLES[st.k].some((x) => x[0] === st.style)) st.style = STYLES[st.k][0][0];
    return st;
  }
  const serialize = (st) => 'studio/' + Object.keys(DEF).filter((k) => st[k] !== DEF[k] || k === 'k' || k === 't').map((k) => k + '=' + encodeURIComponent(st[k])).join('&');

  function css() {
    if (document.getElementById('st-css')) return;
    const s = document.createElement('style'); s.id = 'st-css';
    s.textContent = `.st-wrap{display:grid;grid-template-columns:minmax(280px,360px) 1fr;gap:22px;align-items:start}@media(max-width:900px){.st-wrap{grid-template-columns:1fr}}
.st-side{border:1px solid var(--line);border-radius:14px;padding:14px 16px;background:var(--surface)}.st-side h3{margin:14px 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.st-side h3:first-child{margin-top:2px}.st-side label{display:block;font-size:12.5px;color:var(--muted);margin:8px 0 3px}.st-side .input,.st-side select,.st-side textarea{width:100%;box-sizing:border-box;font:inherit;font-size:14px;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.st-side textarea{min-height:84px;font-family:var(--mono);font-size:13px}.st-row{display:flex;gap:8px}.st-row>*{flex:1}.st-pills{display:flex;flex-wrap:wrap;gap:6px}.st-pills .pill{font-size:12.5px;padding:5px 10px}
.st-stage{background:#0b1220;border-radius:14px;overflow:hidden;display:flex;justify-content:center;align-items:center;box-shadow:var(--shadow)}.st-stage canvas{display:block;max-width:100%;max-height:72vh;height:auto}
.st-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 6px}.st-bar .sp{flex:1}.st-status{font-size:13px;color:var(--muted)}.st-prog{height:6px;border-radius:3px;background:var(--line);overflow:hidden;margin:6px 0}.st-prog i{display:block;height:100%;background:var(--accent);width:0}
.st-notes{font-size:12.5px;color:var(--muted);line-height:1.5}.st-notes li{margin:2px 0}.st-tpl{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:18px 0 6px}
.st-tpl button{text-align:left;font:inherit;border:1px solid var(--line);border-radius:12px;padding:10px 12px;background:var(--surface);cursor:pointer;color:var(--ink)}.st-tpl button:hover{border-color:var(--ink-2)}.st-tpl b{display:block;font-size:14px}.st-tpl span{font-size:12px;color:var(--muted)}
.st-help{font-size:12px;color:var(--muted);line-height:1.5;margin-top:6px}.st-help code{font-family:var(--mono);font-size:11.5px;background:var(--surface-2);padding:0 4px;border-radius:4px}.st-cap{font-family:var(--mono);font-size:12.5px;background:var(--surface-2);border-radius:8px;padding:8px 10px;margin-top:8px;word-break:break-word}`;
    document.head.appendChild(s);
  }

  async function render(app, A, arg) {
    const here = A && A.here ? A.here : () => true;
    if (A && A.setNav) A.setNav('studio');
    css();
    // the address as typed, still encoded (the router decodes it, and a formula can hold % or &)
    const raw = (/^#\/?studio\/?(.*)$/.exec(location.hash || '') || [])[1];
    const st = parseState(raw != null ? raw : arg);
    const sel = (id, items, v) => `<select id="${id}">${items.map(([k, l]) => `<option value="${esc(k)}"${k === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Video studio</div><h1>Make a market video</h1>
      <p class="muted" style="max-width:76ch">Growth races of any ETFs or stocks (with distributions reinvested, left out, or split out as cash), RRG and momentum replays, companies' own figures and any formula — animated, in four looks and three shapes, saved as an MP4 to post. Everything is drawn from the site's own data in your browser.</p></div>
      <div class="st-tpl" id="st-tpl">${TEMPLATES.map((x, i) => `<button type="button" data-tpl="${i}"><b>${esc(x.name)}</b><span>${esc(x.note)}</span></button>`).join('')}</div>
      <div class="st-wrap"><div class="st-side" id="st-side"></div><div class="st-main">
        <div class="st-stage"><canvas id="st-canvas" width="1280" height="720" aria-label="Video preview"></canvas></div>
        <div class="st-bar"><button class="btn primary" id="st-play" type="button">▶ Play</button><button class="btn" id="st-restart" type="button">⟲ Restart</button><span class="sp"></span>
          <button class="btn primary" id="st-export" type="button">Export MP4 ↓</button><button class="btn" id="st-link" type="button">Copy link</button></div>
        <div class="st-prog" id="st-prog" hidden><i></i></div><div class="st-status" id="st-status"></div>
        <div id="st-cap"></div><ul class="st-notes" id="st-notes"></ul>
      </div></div>`;
    const $ = (s) => app.querySelector(s), canvas = $('#st-canvas'), ctx = canvas.getContext('2d');
    let V = null, playing = false, t0 = 0, tNow = 0, raf = 0, token = 0, exporting = false;
    const opt = () => ({ theme: st.theme, ar: st.ar, q: st.q, fps: st.fps, dur: +st.dur || 20 });
    function side() {
      const k = st.k, styles = STYLES[k];
      let h = `<h3>Video</h3><div class="st-pills">${KINDS.map(([v, l]) => `<button type="button" class="pill${v === k ? ' on' : ''}" data-kind="${v}">${esc(l)}</button>`).join('')}</div>`;
      if (k !== 'formula') h += `<label for="st-t">${k === 'fund' ? 'Companies (tickers)' : 'Tickers — ETFs or stocks, two or more'}</label><input class="input" id="st-t" value="${esc(st.t)}" placeholder="${k === 'fund' ? 'NVDA, AMD' : 'QQQ, SPY, SCHD'}" list="st-list" autocomplete="off"><datalist id="st-list"></datalist>`;
      else h += `<label for="st-expr">Formulas — one per line, “Label: expression”</label><textarea id="st-expr" spellcheck="false">${esc(st.expr)}</textarea><div class="st-help">Operators <code>+ − × ÷ ^</code> and <code>( )</code>; functions <code>log exp sqrt abs rebase(x) ma(x,n) ema(x,n) pct(x,n) chg(x,n) lag(x,n) min(a,b) max(a,b)</code>. Series: a ticker (<code>QQQ</code> = total return) or <code>QQQ.price</code>, <code>.div</code>, <code>.yield</code>, company figures <code>NVDA.revenue</code>, <code>.ni_ttm</code>, <code>.margin</code>… Example: <code>rebase(QQQ/SPY)</code>, <code>SCHD.yield*100</code>, <code>NVDA.ni_ttm/NVDA.revenue_ttm</code>.</div>`;
      h += `<div class="st-row"><div><label for="st-from">From</label><input class="input" type="date" id="st-from" value="${esc(st.from)}"></div><div><label for="st-to">To</label><input class="input" type="date" id="st-to" value="${esc(st.to)}"></div></div>`;
      h += `<div class="st-pills" style="margin-top:6px">${[['1y', 1], ['3y', 3], ['5y', 5], ['10y', 10], ['Max', 30]].map(([l, y]) => `<button type="button" class="pill" data-yrs="${y}">${l}</button>`).join('')}</div>`;
      if (k === 'growth') h += `<label for="st-amt">Amount invested ($)</label><input class="input" id="st-amt" inputmode="numeric" value="${esc(st.amt)}"><label for="st-div">Distributions</label>${sel('st-div', [['tr', 'Reinvested (total return)'], ['price', 'Left out (price as traded)'], ['split', 'Split out: price + cash']], st.div)}<label for="st-scale">Scale</label>${sel('st-scale', [['lin', 'Linear'], ['log', 'Logarithmic']], st.scale)}`;
      if (k === 'rrg') h += `<div class="st-row"><div><label for="st-bench">Benchmark</label><input class="input" id="st-bench" value="${esc(st.bench)}"></div><div><label for="st-tail">Tail (weeks)</label>${sel('st-tail', [['5', '5'], ['8', '8'], ['10', '10'], ['13', '13'], ['26', '26']], st.tail)}</div></div><label for="st-n">RS window</label>${sel('st-n', [['10', '10 weeks'], ['14', '14 weeks'], ['26', '26 weeks']], st.n)}`;
      if (k === 'momentum') h += `<div class="st-row"><div><label for="st-bench">Against</label><input class="input" id="st-bench" value="${esc(st.bench)}"></div><div><label for="st-lb">Look-back</label>${sel('st-lb', [['13', '13 weeks'], ['26', '26 weeks'], ['52', '52 weeks']], st.lb)}</div></div>`;
      if (k === 'fund') h += `<label for="st-m">Figure</label>${sel('st-m', Object.entries(FIG), st.m)}<label for="st-ttm">Periods</label>${sel('st-ttm', [['0', 'Each quarter'], ['1', 'Trailing four quarters']], st.ttm)}`;
      h += `<h3>Look</h3><label for="st-style">Style</label>${sel('st-style', styles, st.style)}<label for="st-theme">Theme</label>${sel('st-theme', Object.entries(THEMES).map(([kk, v]) => [kk, v.name]), st.theme)}`;
      h += `<div class="st-row"><div><label for="st-ar">Shape</label>${sel('st-ar', [['16x9', '16:9 landscape'], ['9x16', '9:16 phone'], ['1x1', '1:1 square']], st.ar)}</div><div><label for="st-q">Size</label>${sel('st-q', [['1080', '1080p'], ['720', '720p (faster)']], st.q)}</div></div>`;
      h += `<div class="st-row"><div><label for="st-dur">Length</label>${sel('st-dur', [['10', '10 s'], ['15', '15 s'], ['20', '20 s'], ['30', '30 s'], ['45', '45 s'], ['60', '60 s']], st.dur)}</div><div><label for="st-fps">Smoothness</label>${sel('st-fps', [['30', '30 fps'], ['60', '60 fps']], st.fps)}</div></div>`;
      h += `<label for="st-title">Title (blank: written for you)</label><input class="input" id="st-title" value="${esc(st.title)}" placeholder="${esc((V && V.title) || '')}"><label for="st-sub">Subtitle</label><input class="input" id="st-sub" value="${esc(st.sub)}" placeholder="${esc((V && V.sub) || '')}">`;
      h += `<label for="st-end">End card</label>${sel('st-end', [['1', 'The result, ranked'], ['0', 'None']], st.end)}`;
      $('#st-side').innerHTML = h;
    }
    function save() { try { history.replaceState(null, '', '#' + serialize(st)); } catch (e) { /* file:// */ } }
    function sizeCanvas() {
      const dim = { '16x9': [1280, 720], '9x16': [720, 1280], '1x1': [960, 960] }[st.ar] || [1280, 720];
      if (canvas.width !== dim[0] || canvas.height !== dim[1]) { canvas.width = dim[0]; canvas.height = dim[1]; }
    }
    function paint() { if (V) draw(ctx, canvas.width, canvas.height, V, opt(), tNow); }
    function loop(ts) {
      if (!playing) return;
      tNow = (ts - t0) / 1000;
      const D = timing(V, opt().dur).D;
      if (tNow >= D) { tNow = D; playing = false; $('#st-play').textContent = '▶ Play'; }
      paint();
      if (playing) raf = requestAnimationFrame(loop);
    }
    function play() { if (!V) return; if (tNow >= timing(V, opt().dur).D - 0.01) tNow = 0; playing = true; t0 = performance.now() - tNow * 1000; $('#st-play').textContent = '❚❚ Pause'; cancelAnimationFrame(raf); raf = requestAnimationFrame(loop); }
    function pause() { playing = false; cancelAnimationFrame(raf); $('#st-play').textContent = '▶ Play'; }
    async function rebuild(autoplay) {
      const my = ++token;
      save(); sizeCanvas();
      $('#st-status').textContent = 'Loading the data…';
      try {
        const v = await build(st);
        if (my !== token || !here()) return;
        v.style = st.style; v.scale = st.scale; v.endCard = st.end === '1';
        finish(v, st);
        V = v;
        $('#st-status').textContent = `${V.series.length} series · ${V.grid.length} ${V.quarterly ? 'quarters' : 'weeks'} · ${opt().dur} s`;
        $('#st-notes').innerHTML = [...V.notes].map((n) => `<li>${esc(n)}</li>`).join('');
        $('#st-cap').innerHTML = V.caption ? `<div class="st-cap" title="A caption to post with the video">${esc(V.caption)}</div>` : '';
        const ti = $('#st-title'), su = $('#st-sub'); if (ti) ti.placeholder = V.title; if (su) su.placeholder = V.sub;
        tNow = autoplay ? 0 : timing(V, opt().dur).D * 0.62;
        paint();
        if (autoplay) play();
      } catch (e) {
        if (my !== token) return;
        V = null; pause();
        ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#e8eef7'; ctx.font = '600 28px "IBM Plex Sans", Arial'; ctx.textAlign = 'center'; ctx.fillText(e.message, canvas.width / 2, canvas.height / 2);
        $('#st-status').textContent = e.message; $('#st-notes').innerHTML = ''; $('#st-cap').innerHTML = '';
      }
    }
    async function suggest() {
      const list = $('#st-list'); if (!list || list.dataset.done) return; list.dataset.done = '1';
      const [ix, ex] = await Promise.all([json(SITE + 'index.json'), st.k === 'fund' ? null : json(HUB + 'etf/index.json')]);
      const opts = [];
      if (ex && ex.rows) { const F = ex.fields, si = F.indexOf('symbol'), ni = F.indexOf('name'), ai = F.indexOf('aum'); ex.rows.slice().sort((a, b) => (b[ai] || 0) - (a[ai] || 0)).slice(0, 1500).forEach((r) => opts.push([r[si], r[ni]])); }
      ((ix && ix.companies) || []).slice().sort((a, b) => (b.revenue || 0) - (a.revenue || 0)).slice(0, 1500).forEach((c) => c.ticker && opts.push([c.ticker, c.name]));
      list.innerHTML = opts.map(([s, n]) => `<option value="${esc(s)}">${esc(n || '')}</option>`).join('');
    }
    const box = app.querySelector('.st-wrap');
    let tmr = 0;
    const later = (f) => { clearTimeout(tmr); tmr = setTimeout(f, 450); };
    box.addEventListener('click', (e) => {
      const kb = e.target.closest('[data-kind]');
      if (kb) { st.k = kb.dataset.kind; st.style = STYLES[st.k][0][0]; if (st.k === 'fund' && !/^[A-Z]/.test(st.t)) st.t = 'NVDA'; st.title = ''; st.sub = ''; side(); rebuild(); return; }
      const yb = e.target.closest('[data-yrs]');
      if (yb) { st.from = iso(Date.now() - (+yb.dataset.yrs) * 365.25 * DAY); st.to = ''; side(); rebuild(); }
    });
    box.addEventListener('focusin', (e) => { if (e.target.id === 'st-t') suggest(); });
    box.addEventListener('input', (e) => {
      const id = e.target.id; if (!id || !id.startsWith('st-') || e.target.tagName === 'SELECT') return;
      const key = id.slice(3); if (!(key in DEF)) return;
      st[key] = e.target.value;
      if (key === 'title' || key === 'sub') { if (V) { V.title = st.title || V._title; V.sub = st.sub || V._sub; paint(); save(); } return; }
      later(() => rebuild());
    });
    box.addEventListener('change', (e) => {
      const id = e.target.id; if (!id || !id.startsWith('st-')) return;
      const key = id.slice(3); if (!(key in DEF) || e.target.tagName === 'INPUT' && e.target.type !== 'date') return;
      st[key] = e.target.value;
      if (['theme', 'ar', 'dur', 'fps', 'q', 'style', 'scale', 'end'].includes(key)) {
        if (V) { V.style = st.style; V.scale = st.scale; V.endCard = st.end === '1'; delete V._dom; sizeCanvas(); paint(); save(); $('#st-status').textContent = `${V.series.length} series · ${V.grid.length} ${V.quarterly ? 'quarters' : 'weeks'} · ${opt().dur} s`; }
        else rebuild();
        return;
      }
      rebuild();
    });
    app.querySelector('#st-tpl').addEventListener('click', (e) => {
      const b = e.target.closest('[data-tpl]'); if (!b) return;
      Object.assign(st, DEF, TEMPLATES[+b.dataset.tpl].s); side(); rebuild(true);
      app.querySelector('.st-stage').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    $('#st-play').addEventListener('click', () => (playing ? pause() : play()));
    $('#st-restart').addEventListener('click', () => { tNow = 0; play(); });
    $('#st-link').addEventListener('click', () => { const u = location.href.split('#')[0] + '#' + serialize(st); (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(() => { $('#st-link').textContent = 'Copied'; setTimeout(() => { $('#st-link').textContent = 'Copy link'; }, 1600); }).catch(() => prompt('Copy this link', u)); });
    $('#st-export').addEventListener('click', async () => {
      if (!V || exporting) return;
      exporting = true; pause();
      const btn = $('#st-export'), prog = $('#st-prog'); btn.disabled = true; prog.hidden = false;
      const set = (p) => { prog.firstElementChild.style.width = (100 * p).toFixed(1) + '%'; $('#st-status').textContent = `Rendering ${Math.round(100 * p)}%…`; };
      try {
        let r = await exportMp4(V, opt(), set, () => !here());
        if (r === 'cancelled') return;
        if (!r) { $('#st-status').textContent = 'Recording the preview in real time (this browser has no video encoder)…'; r = await recordPreview(canvas, V, opt(), set); }
        const ext = r.blob.type.includes('mp4') ? 'mp4' : 'webm';
        const name = 'filing-flows-' + (V.series.map((s) => s.key).join('-').replace(/[^A-Za-z0-9-]+/g, '').slice(0, 40) || 'video') + '.' + ext;
        const a = document.createElement('a'); a.href = URL.createObjectURL(r.blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 60000);
        $('#st-status').textContent = `Saved ${name} · ${(r.blob.size / 1e6).toFixed(1)} MB${r.w ? ` · ${r.w}×${r.h}, ${r.fps} fps, ${r.codec}` : ''}`;
        root.FFStudio._last = r;
      } catch (err) {
        $('#st-status').textContent = 'The video could not be made: ' + err.message;
      } finally { exporting = false; btn.disabled = false; prog.hidden = true; }
    });
    side();
    await rebuild(false);
  }

  // titles typed by the reader replace the written ones; the written ones stay to fall back on
  async function build(st) { const V = await buildRaw(st); V._title = V.title; V._sub = V.sub; if (st.title) V.title = st.title; if (st.sub) V.sub = st.sub; return V; }

  root.FFStudio = { render, _t: { tokenize, parse, evaluate, formulas, ids, figure, weeklyGrid, asof, divsOn, divTTM, trOn, priceOn, rrgXY, build, finish, draw, timing, frameIndex, parseState, serialize, exportMp4, money, THEMES, TEMPLATES } };
  if (typeof module !== 'undefined') module.exports = root.FFStudio;
})(typeof globalThis !== 'undefined' ? globalThis : this);
