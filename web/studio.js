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
     rank      a leaderboard of every company of the site, ranked again each month, quarter or week: market value,
               revenue, gross / operating / net income, margins, revenue growth, P/E, P/B, P/S, dollar volume, total
               return — within a sector and a market-value range (rank_panel.py's files).
     drawdown  how far below its highest close each ticker stood, week by week.
     calendar  one ticker's monthly returns as a heatmap that fills in month by month.
     dist      the spread of every company's return each year, as a histogram that morphs from year to year.
   Growth races take a lump sum and/or the same amount bought every n trading days, weeks, months or years (the money put
   in drawn as a dashed line; the end card gives each ticker's money-weighted return a year). Stocks get dividends
   (split out or left out) from the weekly history's dividend list (t/<SYM>.json: d, p). Whichever way they are used,
   the dividends and interest paid are counted in dollars as paid (the shares then held × the amount per share; with
   dividends reinvested, the shares are the total-return value over the price as traded): on the labels, on a panel of
   their own if asked (a running total, or each calendar year as bars), on the end card and in the caption.
   Adjustments: a tax on dividends (only the rest is reinvested: the total return is rebuilt from the price and the
   net dividends); a cash line (the same money on the same dates at a fixed rate or the 3-month Treasury bill, its
   future value), and the dividends taken as cash earning it; inflation as a line that keeps up with prices, or every
   value in dollars of the start (a fixed rate or the CPI: market/history/macro.json, levels — or, until those are
   published, the CPI rebuilt from its year-on-year rates and cash at the Fed funds rate); a discount rate for the
   present value of each end value and the NPV of the plan.
   Under the video, the results: its figures as a table (for a growth race: the money put in, the end value, the gain,
   the money-weighted return a year, the dividends paid and those of the last 12 months, the worst drop, the best and
   worst calendar years, and with the adjustments the rate after inflation, the gap to cash and the present value),
   the dividends paid each calendar year, the caption, the notes; copied as text, the weekly series as a CSV, the
   frame as a PNG. The dividend snowball's report: the money in, the shares, the dividends received, a month now and in
   year one, the income's growth, the yield on cost, and its dividends month by month (CSV).
   Styles: line race, bar race, areas, counters, columns, the RRG, leaderboard, heatmap, histogram; themes; 16:9, 9:16
   and 1:1; any length, five paces and the pause at the end; 30 or 60 frames a second.
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
      // a stock (or a fund with a longer history there): dividends and the close as traded from the weekly history
      const hp = th && Array.isArray(th.d) ? historyPx(th) : null;
      if (hp && (!out.px || hp.t[0] < out.px.t[0] - 30 * DAY)) out.px = hp;
      if (long) {
        const s0 = Date.parse(long.start + 'T00:00:00Z'), t = [], v = [];
        long.c.forEach((x, i) => { if (fin(x) && x > 0) { t.push(s0 + i * WEEK); v.push(+x); } });
        if (t.length) out.long = { t, v };
      }
      return out;
    })());
    return PRICES.get(sym);
  }
  // t/<SYM>.json with dividends: {t, c (as traded), a (adjusted), div [[friday, per share]]}. Without the close as traded
  // (p) it is rebuilt from the adjusted closes going back from the latest week: P(i−1) = A(i−1) / m(i) + D(i), where m
  // is the adjustment factor after week i and D the dividends that went ex in week i
  function historyPx(th) {
    const s0 = Date.parse(th.start + 'T00:00:00Z'), A = th.c || [], n = A.length, D = new Array(n).fill(0);
    for (const [i, v] of th.d) if (i >= 0 && i < n && fin(v)) D[i] += +v;
    let P = Array.isArray(th.p) && th.p.some(fin) ? A.map((x, i) => (fin(th.p[i]) ? +th.p[i] : null)) : null;
    if (!P) {
      P = new Array(n).fill(null); let m = 1;
      for (let i = n - 1; i >= 0; i--) {
        if (!fin(A[i])) continue;
        if (i < n - 1 && D[i + 1]) { const p = A[i] / m + D[i + 1]; m = A[i] / p; P[i] = p; } else P[i] = A[i] / m;
      }
    }
    const t = [], c = [], a = [];
    for (let i = 0; i < n; i++) if (fin(A[i]) && A[i] > 0) { t.push(s0 + i * WEEK); a.push(+A[i]); c.push(fin(P[i]) ? P[i] : null); }
    if (!t.length) return null;
    return { t, c, a, div: th.d.filter(([i, v]) => fin(v) && v > 0).map(([i, v]) => [s0 + i * WEEK, +v]), history: true };
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
  /* ---------- data: consumer prices and the cash rate (market/history/macro.json, from FRED) ---------- */
  // month by month: the CPI index and the 3-month Treasury bill's yield, by the month described (levels); until those
  // are published, the CPI rebuilt from its year-on-year rates and cash at the Fed funds rate (both approximate)
  let MACRO = null;
  const macro = () => MACRO || (MACRO = json(HUB + 'market/history/macro.json').then((d) => {
    if (!d) return null;
    const ym = (x) => [+x.slice(0, 4), +x.slice(5, 7) - 1], Lv = d.levels;
    if (Lv && Lv.start && Array.isArray(Lv.cpi) && Lv.cpi.some(fin)) { const [y0, m0] = ym(Lv.start); return { y0, m0, cpi: Lv.cpi, bill: Lv.bill3m || [], exact: true }; }
    const M = d.monthly || {}, months = M.months || [], D = M.data || {}, yoy = D.cpi || [];
    if (!months.length) return null;
    const [y0, m0] = ym(months[0]), cpi = []; let v = 100;
    months.forEach((_, i) => { if (i) v *= fin(yoy[i]) ? Math.pow(1 + yoy[i] / 100, 1 / 12) : 1; cpi.push(v); });
    return { y0, m0, cpi, bill: D.ff || [], exact: false };
  }));
  // a month's figure for each week: the last on file for the weeks after it, the first for those before
  function monthlyOn(Mc, arr, G) {
    if (!Mc || !Array.isArray(arr)) return null;
    const a = arr.findIndex(fin); let b = arr.length - 1; while (b >= 0 && !fin(arr[b])) b--;
    if (a < 0) return null;
    return G.map((g) => { const d = new Date(g); let j = clamp((d.getUTCFullYear() - Mc.y0) * 12 + d.getUTCMonth() - Mc.m0, a, b); while (j > a && !fin(arr[j])) j--; return +arr[j]; });
  }
  // $1 week by week at a fixed rate a year, or at each week's rate (%), compounded
  function growIdx(G, rates, fixed) {
    const out = [1];
    for (let i = 1; i < G.length; i++) { const r = fixed != null ? fixed : rates ? rates[i - 1] : 0; out.push(out[i - 1] * Math.pow(1 + (fin(r) ? r : 0) / 100, (G[i] - G[i - 1]) / (365.25 * DAY))); }
    return out;
  }
  // the total return with the dividends after a tax: each close plus the (net) dividends that went ex since the last
  // close, over that close
  function netTR(pr, dv, i0) {
    const out = pr.map(() => null); let v = null, last = null, pend = 0;
    for (let i = i0; i < pr.length; i++) {
      pend += (dv && dv[i]) || 0;
      if (!fin(pr[i]) || pr[i] <= 0) { out[i] = v; continue; }
      v = v == null ? +pr[i] : v * (pr[i] + pend) / last;
      pend = 0; last = +pr[i]; out[i] = v;
    }
    return out;
  }
  const rateOf = (x) => (x !== '' && x != null && fin(+x) ? +x : null);

  /* ---------- recurring buys and the money-weighted return ---------- */
  const UNITS = { d: ['trading day', 'trading days'], w: ['week', 'weeks'], m: ['month', 'months'], y: ['year', 'years'] };
  // the amount bought in each grid week: `amt` every n trading days (five a week), weeks, months or years, from the start
  // (a month: the same day of the month as the start; a buy uses the close of the week it falls in)
  function buySchedule(G, amt, n, unit, start) {
    const out = G.map(() => 0);
    if (!(amt > 0) || !G.length) return out;
    n = Math.max(1, Math.round(+n || 1));
    if (unit === 'd') { for (let w = 0; w < G.length; w++) out[w] = (Math.floor((5 * w + 4) / n) - Math.floor((5 * w - 1) / n)) * amt; return out; }
    if (unit === 'w') { for (let w = 0; w < G.length; w += n) out[w] = amt; return out; }
    const step = unit === 'y' ? 12 * n : n, d0 = new Date(Math.min(start || G[0], G[0]));
    for (let k = 0; k < 2000; k++) {
      const y = d0.getUTCFullYear(), m = d0.getUTCMonth() + k * step, dim = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
      const w = Math.round((friday(Date.UTC(y, m, Math.min(d0.getUTCDate(), dim))) - G[0]) / WEEK);
      if (w >= G.length) break;
      if (w >= 0) out[w] += amt;
    }
    return out;
  }
  // the yearly rate that makes the money put in worth the end value (XIRR): flows [[ms, amount]], paid in < 0, value > 0
  function xirr(flows) {
    const f = flows.filter(([, a]) => fin(a) && a !== 0);
    if (f.length < 2 || !f.some(([, a]) => a > 0) || !f.some(([, a]) => a < 0)) return null;
    const t0 = Math.min(...f.map(([t]) => t)), Y = 365.25 * DAY;
    const npv = (r) => f.reduce((s, [t, a]) => s + a / Math.pow(1 + r, (t - t0) / Y), 0);
    let lo = -0.9999, hi = 20, flo = npv(lo);
    if (flo * npv(hi) > 0) return null;
    for (let i = 0; i < 200; i++) { const mid = (lo + hi) / 2, fm = npv(mid); if (Math.abs(fm) < 1e-7) return mid; if (fm * flo > 0) { lo = mid; flo = fm; } else hi = mid; }
    return (lo + hi) / 2;
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
      const out = { sym, cik: row.cik, name: (c.profile && c.profile.name) || row.name || sym, q: {}, lab: new Map() };
      const H = (c.quality || {}).hist, derived = new Set();
      if (H && H.periods && H.v) {
        for (const [k, rows] of Object.entries(H.v)) {
          const m = new Map(), fy = [];
          for (const [pi, vals] of rows || []) {
            const p = H.periods[pi]; if (!p || !vals || !vals[0] || !fin(vals[0][0])) continue;
            if (p[3]) out.lab.set(p[1], p[2] === 'fy' ? String(p[3]).replace(/^FY/, 'Q4 FY') : p[3]);      // the company's own quarter names
            if (p[2] === 'q') m.set(p[1], +vals[0][0]); else if (p[2] === 'fy') fy.push([p[1], +vals[0][0]]);
          }
          // a 10-K reports the year, not its fourth quarter: the year less its first three quarters
          for (const [end, v] of fy) {
            if (m.has(end)) continue;
            const e = Date.parse(end + 'T00:00:00Z'), three = [...m.entries()].filter(([q]) => { const d = (e - Date.parse(q + 'T00:00:00Z')) / DAY; return d > 45 && d < 300; });
            if (three.length !== 3) continue;
            const q4 = v - three.reduce((a, x) => a + x[1], 0);
            if (k === 'revenue' && !(q4 > 0)) continue;
            m.set(end, q4); derived.add(k + '|' + end);
          }
          out.q[k] = m;
        }
      }
      for (const q of c.quarters || []) {                     // the latest quarters on the page fill the newest ends
        const h = q.headline || {};
        if (q.end && q.label && /^Q/i.test(q.label)) out.lab.set(q.end, q.label);
        if (q.end && /^Q/i.test(String(q.label || 'Q'))) for (const k of ['revenue', 'oi', 'ni', 'ocf']) if (fin(h[k])) { out.q[k] = out.q[k] || new Map(); if (!out.q[k].has(q.end) || derived.has(k + '|' + q.end)) out.q[k].set(q.end, +h[k]); }
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
    title: '', sub: '', bench: 'SPY', tail: '10', n: '14', lb: '26', m: 'revenue', ttm: '1', expr: 'QQQ/SPY', scale: 'lin', end: '1',
    rec: '0', ri: '1', ru: 'm', pace: 'steady', hold: 'auto', bx: 'growth', by: 'ret', bs: 'cap', bn: '25', bt: '', tn: '50', tc: 'ret', sa: 'share', sm: 'detail', aw: 'index', at: 'dji', ah: 'SPY', ac: '1067983', ap: 'Nancy Pelosi', ao: 'all', ag: 'company', an: '12', hsrc: '13f', hid: '', hv: 'company', scf: 'monthly', sgoal: '', sunit: 'monthly', ssolve: 'lump', yb: '2000',
    rm: 'cap', top: '10', cmin: '', cmax: '', capby: 'then', sec: '', step: 'm', ord: 'desc', win: '12', minrev: '1', idx: '', idxw: 'then',
    goal: '', solve: 'rec', yrs: '', sw: 'index', sf: 'DIA', dinc: 'label', dview: 'total', dtax: '', cashl: '0', cashr: '', infl: 'none', inflr: '', dint: '0', disc: '' };
  const KINDS = [['growth', 'Growth race'], ['rank', 'Leaderboard'], ['rrg', 'RRG replay'], ['momentum', 'Momentum race'], ['fund', 'Company figures'], ['formula', 'Formula & ratios'],
    ['drawdown', 'Drawdowns'], ['calendar', 'Monthly returns'], ['dist', 'Return spread'], ['bubble', 'Bubbles'], ['treemap', 'Market map'], ['sectors', 'Sector weights'], ['actual', 'ETF / 13F / officials history'], ['holdings', '13F / Officials latest mix'],
    ['sankey', 'Earnings flow'], ['snowball', 'Dividend snowball'], ['timing', 'Timing']];
  const STYLES = { growth: [['line', 'Line race'], ['bars', 'Bar race'], ['area', 'Areas'], ['tiles', 'Counters']], rrg: [['rrg', 'RRG']], momentum: [['bars', 'Bar race'], ['line', 'Lines']],
    fund: [['columns', 'Columns'], ['line', 'Lines'], ['bars', 'Bar race'], ['tiles', 'Counters']], formula: [['line', 'Lines'], ['area', 'Areas'], ['tiles', 'Counters'], ['bars', 'Bar race']],
    rank: [['bars', 'Bar race']], drawdown: [['area', 'Underwater areas'], ['line', 'Lines'], ['bars', 'Bar race'], ['tiles', 'Counters']], calendar: [['heat', 'Heatmap']], dist: [['hist', 'Histogram']],
    bubble: [['bubble', 'Bubbles']], treemap: [['treemap', 'Treemap']], sectors: [['stack', 'Stacked areas']], actual: [['bars', 'Holdings bar race'], ['stack', 'Sector share areas'], ['companies', 'Company share areas'], ['changes', 'Weight changes (pp)']], holdings: [['bars', 'Actual holdings bars']], sankey: [['sankey', 'Flow']], snowball: [['snow', 'Shares and income']],
    timing: [['line', 'Line race'], ['bars', 'Bar race'], ['tiles', 'Counters']] };
  const LOOK = ['theme', 'ar', 'dur', 'fps', 'q', 'style', 'scale', 'end', 'pace', 'hold', 'dinc', 'dview'];        // redrawn, not rebuilt
  const tickers = (st) => [...new Set(String(st.t || '').split(/[\s,;]+/).map(norm).filter(Boolean))].slice(0, 10);

  /* ---------- leaderboards: every company of the site, month by month (app/rank_panel.py) ---------- */
  const RANKP = HUB + 'market/history/rank/';
  // [name, unit ($ money, %m a margin, % a change, x a multiple), files]
  const RANK = {
    cap: ['Market value', '$', ['m-cap']], rev: ['Revenue, last 12 months', '$', ['q-rev']], gp: ['Gross profit, last 12 months', '$', ['q-gp']],
    oi: ['Operating income, last 12 months', '$', ['q-oi']], ni: ['Net income, last 12 months', '$', ['q-ni']], om: ['Operating margin', '%m', ['q-oi', 'q-rev']],
    nm: ['Net margin', '%m', ['q-ni', 'q-rev']], growth: ['Revenue growth, year on year', '%', ['q-rev']], pe: ['Price / earnings', 'x', ['m-cap', 'q-ni', 'q-rev']],
    pb: ['Price / book', 'x', ['m-cap', 'q-eq']], ps: ['Price / sales', 'x', ['m-cap', 'q-rev']], dv: ['Dollar volume traded', '$', ['m-dv']], ret: ['Total return', '%', ['m-px']],
  };
  const SECTORS = { technology: 'Technology', communication: 'Communication', 'consumer-disc': 'Consumer discretionary', 'consumer-staples': 'Consumer staples',
    health: 'Health care', financials: 'Financials', 'real-estate': 'Real estate', energy: 'Energy', materials: 'Materials', industrials: 'Industrials', utilities: 'Utilities', other: 'Other' };
  const secCol = (th, sec) => { const i = Object.keys(SECTORS).indexOf(sec); return i < 0 || sec === 'other' ? (th.text === '#1d1d1b' ? '#8d8a84' : '#a9b3c1') : i === 10 ? (th.text === '#1d1d1b' ? '#8a6a3a' : '#e3c79f') : th.pal[i % th.pal.length]; };
  const PANEL = new Map();
  const panel = (name) => { if (!PANEL.has(name)) PANEL.set(name, json(RANKP + name + '.json').then((d) => (d && Array.isArray(d.rows) ? d.rows : d))); return PANEL.get(name); };
  const at = (row, i) => (row && row.length > 1 && i >= row[0] && i < row[0] + row.length - 1 ? row[1 + i - row[0]] : null);
  const fmtFor = (unit) => (unit === '$' ? (v) => money(v) : unit === 'x' ? (v) => (fin(v) ? v.toFixed(v >= 100 ? 0 : 1) + '×' : '—') : unit === '%m' ? (v) => (fin(v) ? (100 * v).toFixed(1) + '%' : '—') : (v) => pctf(v, 1));
  async function rankMeta() {
    const meta = await panel('meta');
    if (!meta || !Array.isArray(meta.cos) || !meta.months) throw new Error('The leaderboard data is not published yet — it is built with the weekly price history');
    const m0 = { y: +meta.months.start.slice(0, 4), m: +meta.months.start.slice(5, 7) - 1 };
    meta._m0 = m0;
    meta._Q = (meta.quarters || []).map((q) => { const y = +q.slice(0, 4), k = +q.slice(5); return { label: q, end: Date.UTC(y, 3 * k, 0), mi: (y - m0.y) * 12 + 3 * k - 1 - m0.m }; });
    return meta;
  }
  const mIndex = (ms, m0) => { const d = new Date(ms); return (d.getUTCFullYear() - m0.y) * 12 + d.getUTCMonth() - m0.m; };
  const mEnd = (i, m0) => Date.UTC(m0.y, m0.m + i + 1, 0);
  // index membership (disclosures/app/index_members.py): now from the tracking ETFs' holdings, before from Wikipedia's
  // S&P 500 changes and the Dow's history; the other indices only from when the site began keeping them
  const IDX = { sp500: 'S&P 500', ndx: 'Nasdaq-100', dji: 'Dow 30', sp400: 'S&P MidCap 400', sp600: 'S&P SmallCap 600', r1000: 'Russell 1000', r2000: 'Russell 2000' };
  const members = () => json(HUB + 'etf/members.json');
  function isMember(MB, ticker, key, day, now) {
    const r = MB && MB.rows && MB.rows[ticker]; if (!r) return false;
    const iv = (r.was || {})[key];
    if (now || !iv || !iv.length) return (r.now || []).includes(key);
    return iv.some(([a, b]) => (!a || a <= day) && (!b || day < b));
  }
  // the universe filter: a sector, an index, a market-value range ($B) by the value at each step or today's
  function universe(st, meta, F, MB) {
    const sec = st.sec && SECTORS[st.sec] ? st.sec : '', capF = String(st.cmin).trim() !== '' || String(st.cmax).trim() !== '';
    const lo = capF && String(st.cmin).trim() !== '' && fin(+st.cmin) ? +st.cmin * 1e3 : -Infinity, hi = capF && String(st.cmax).trim() !== '' && fin(+st.cmax) ? +st.cmax * 1e3 : Infinity;
    const byNow = st.capby === 'now' || !F['m-cap'];
    const ix = st.idx && IDX[st.idx] && MB ? st.idx : '', ixNow = st.idxw === 'now';
    const ok = (ci, mi) => {
      if (sec && meta.cos[ci][2] !== sec) return false;
      if (ix && !isMember(MB, meta.cos[ci][0], ix, iso(mEnd(mi, meta._m0)), ixNow)) return false;
      if (!capF) return true;
      const c = byNow ? meta.cap_now[ci] : at(F['m-cap'][ci], mi);
      return fin(c) && c >= lo && c <= hi;
    };
    const capTxt = !capF ? '' : `market value ${fin(lo) ? money(lo * 1e6) : '$0'}–${fin(hi) ? money(hi * 1e6) : 'any'}${byNow ? ' (today)' : ''}`;
    return { ok, sec, capF, capTxt, ix, scope: [ix ? IDX[ix] + ' members' + (ixNow ? ' (today)' : '') : '', sec ? SECTORS[sec] : '', capTxt].filter(Boolean).join(' · ') };
  }
  const ttmOf = (row, q) => { if (q < 3) return null; let s = 0; for (let j = q - 3; j <= q; j++) { const v = at(row, j); if (!fin(v)) return null; s += v; } return s; };
  // one measure of one company at the end of month mi (qk: the quarter whose figures count then), in dollars or a ratio;
  // o: {m0, step, minrev ($M), win (months or 'ytd')}
  function makeMeasure(key, F, o) {
    const need = RANK[key][2], base = need.find((f) => f.startsWith('q-'));
    return (ci, mi, qk) => {
      if (key === 'cap') { const v = at(F['m-cap'][ci], mi); return fin(v) ? v * 1e6 : null; }
      if (key === 'dv') {
        let s2 = 0, any = false;
        for (let j = o.step === 'q' ? mi - 2 : mi; j <= mi; j++) { const v = at(F['m-dv'][ci], j); if (fin(v)) { s2 += v; any = true; } }
        return any ? s2 * 1e6 : null;
      }
      if (key === 'ret') { const w = o.win === 'ytd' ? ((o.m0.m + mi) % 12) + 1 : o.win, a = at(F['m-px'][ci], mi), b = at(F['m-px'][ci], mi - w); return fin(a) && fin(b) && b > 0 ? a / b - 1 : null; }
      if (qk < 0) return null;
      // a company that has not filed the quarter yet (a late 10-K, a fiscal year ending in January) keeps its last four
      // quarters on file, for up to two quarters
      for (let back = 0; back <= 2 && qk - back >= 3; back++) if (fin(base === 'q-eq' ? at(F[base][ci], qk - back) : ttmOf(F[base][ci], qk - back))) { qk -= back; break; }
      const R = (f) => ttmOf(F[f][ci], qk);
      if (key === 'rev' || key === 'gp' || key === 'oi' || key === 'ni') { const v = R('q-' + key); return fin(v) ? v * 1e6 : null; }
      if (key === 'om' || key === 'nm') { const r = R('q-rev'), x = R(key === 'om' ? 'q-oi' : 'q-ni'); return fin(r) && fin(x) && r > 0 && r >= o.minrev ? x / r : null; }
      if (key === 'growth') { const r = R('q-rev'), r0 = qk >= 4 ? ttmOf(F['q-rev'][ci], qk - 4) : null; return fin(r) && fin(r0) && r0 > 0 && r0 >= o.minrev ? r / r0 - 1 : null; }
      const c = at(F['m-cap'][ci], mi); if (!fin(c) || c <= 0) return null;
      if (key === 'pe') { const x = R('q-ni'), r = F['q-rev'] ? R('q-rev') : null; return fin(x) && x > 0 && (!fin(r) || x >= 0.02 * r) ? c / x : null; }
      if (key === 'ps') { const x = R('q-rev'); return fin(x) && x > 0 ? c / x : null; }
      if (key === 'pb') { const e = at(F['q-eq'][ci], qk); return fin(e) && e > 0 && c / e <= 200 ? c / e : null; }
      return null;
    };
  }
  const qForOf = (Q, m0, step) => (mi) => { const me = mEnd(mi, m0); let k = -1; for (let j = 0; j < Q.length; j++) if (step === 'q' ? Q[j].mi <= mi : Q[j].end + 46 * DAY <= me) k = j; return k; };
  async function buildRank(st, out) {
    const meta = await rankMeta(), m0 = meta._m0, Q = meta._Q;
    const key = RANK[st.rm] ? st.rm : 'cap', [mname, unit, need] = RANK[key];
    const capF = String(st.cmin).trim() !== '' || String(st.cmax).trim() !== '';
    const files = new Set(need); if (capF && st.capby !== 'now') files.add('m-cap');
    const F = {};
    await Promise.all([...files].map(async (f) => { F[f] = await panel(f); }));
    for (const f of files) if (!Array.isArray(F[f])) throw new Error('A leaderboard file is missing (' + f + ')');
    const MB = st.idx ? await members() : null;
    if (st.idx && !MB) out.notes.add('Index membership is not published yet: every company is ranked');
    if (MB && st.idx && st.idxw !== 'now' && !['sp500', 'dji'].includes(st.idx)) out.notes.add(`${IDX[st.idx]}: membership history only from ${((MB.history || {}).others || 'now').replace(/^from /, '')} — before that, today's members`);
    const N = clamp(Math.round(+st.top || 10), 3, 25), desc = st.ord !== 'asc', fundamental = need.some((f) => f.startsWith('q-'));
    const step = st.step === 'w' && !fundamental ? 'w' : st.step === 'q' ? 'q' : 'm';
    if (st.step === 'w' && fundamental) out.notes.add('Company figures change once a quarter, so the steps are monthly');
    const U = universe(st, meta, F, MB), NC = meta.cos.length, lastM = meta.months.n - 1;
    const capLike = key === 'cap' || key === 'pe' || key === 'pb' || key === 'ps';
    const fromMs = st.from ? Date.parse(st.from + 'T00:00:00Z') : Date.UTC(capLike || fundamental ? 2010 : 2005, 0, 31);
    const toMs = st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now();
    const i0 = clamp(mIndex(fromMs, m0), 1, lastM), i1 = clamp(mIndex(toMs, m0), i0, lastM);
    const months = [];
    for (let i = i0; i <= i1; i++) if (step !== 'q' || (m0.m + i) % 3 === 2) months.push(i);
    if (months.length < 2) throw new Error('Fewer than two steps in that range');
    // the quarter whose figures count at the end of month mi: public 46 days after it ended; quarterly steps: the quarter itself
    const qFor = (mi) => { const me = mEnd(mi, m0); let k = -1; for (let j = 0; j < Q.length; j++) if (step === 'q' ? Q[j].mi <= mi : Q[j].end + 46 * DAY <= me) k = j; return k; };
    const minrev = Math.max(0, +st.minrev || 0) * 1e3, qks = months.map(qFor);
    const win = st.win === 'ytd' ? 'ytd' : Math.max(1, Math.round(+st.win || 12));
    const val = makeMeasure(key, F, { m0, step, minrev, win });
    if (step === 'q' && fundamental) {                    // the newest quarter, before most companies have filed it
      const base = need.find((f) => f.startsWith('q-')), cnt = (q) => F[base].reduce((a, row) => a + (fin(at(row, q)) ? 1 : 0), 0);
      while (months.length > 2) { const q = qks[months.length - 1]; if (q < 1 || cnt(q) >= 0.8 * cnt(q - 1)) break; months.pop(); qks.pop(); }
    }
    const sorter = (a, b) => (desc ? b[1] - a[1] : a[1] - b[1]);
    const pick = new Set(), extra = step === 'w' ? 6 : 0;
    months.forEach((mi, j) => {
      const list = [];
      for (let ci = 0; ci < NC; ci++) if (U.ok(ci, mi)) { const v = val(ci, mi, qks[j]); if (fin(v)) list.push([ci, v]); }
      list.sort(sorter).slice(0, N + extra).forEach(([ci]) => pick.add(ci));
    });
    if (!pick.size) throw new Error('No company fits those settings in that range');
    const tick = (ci) => meta.cos[ci][0];
    if (step === 'w') {                                   // weekly: the candidates' own weekly closes and volume
      const G = weeklyGrid(iso(mEnd(i0 - 1, m0) + DAY), iso(Math.min(toMs, mEnd(i1, m0))));
      const TH = new Map();
      await Promise.all([...pick].map(async (ci) => { const th = await json(HUB + 'market/history/t/' + tick(ci) + '.json'); if (th && th.c) TH.set(ci, th); }));
      const wv = (ci, g) => {
        const th = TH.get(ci); if (!th) return null;
        const s0 = Date.parse(th.start + 'T00:00:00Z'), i = Math.round((g - s0) / WEEK), A = th.c, Pp = th.p && th.p.length ? th.p : th.c;
        if (i < 0 || i >= A.length || !fin(A[i])) return null;
        if (key === 'ret') { const w = win === 'ytd' ? Math.round((g - Date.UTC(new Date(g).getUTCFullYear() - 1, 11, 31)) / WEEK) : Math.round(win * 52 / 12); return i - w >= 0 && fin(A[i - w]) && A[i - w] > 0 ? A[i] / A[i - w] - 1 : null; }
        if (key === 'dv') return fin(th.v && th.v[i]) && fin(Pp[i]) ? th.v[i] * 1000 * Pp[i] : null;
        const mi = mIndex(g, m0) - 1, c = at(F['m-cap'][ci], mi), j = Math.floor((mEnd(mi, m0) - s0) / WEEK);
        return fin(c) && j >= 0 && fin(Pp[j]) && fin(Pp[i]) ? c * 1e6 * Pp[i] / Pp[j] : null;
      };
      out.series = [...pick].map((ci) => ({ key: tick(ci), label: tick(ci), name: meta.cos[ci][1], sec: meta.cos[ci][2], v: G.map((g) => (U.ok(ci, mIndex(g, m0) - 1) ? wv(ci, g) : null)) }));
      let end = G.length;                                 // the newest weeks, before most of the candidates have a close
      while (end > 2 && out.series.filter((x) => fin(x.v[end - 1])).length < Math.min(N, out.series.length) * 0.8) end--;
      out.grid = G.slice(0, end); out.series.forEach((x) => { x.v = x.v.slice(0, end); });
    } else {
      out.grid = months.map((mi) => mEnd(mi, m0));
      out.quarterly = step === 'q';
      out.series = [...pick].map((ci) => ({ key: tick(ci), label: tick(ci), name: meta.cos[ci][1], sec: meta.cos[ci][2], v: months.map((mi, j) => (U.ok(ci, mi) ? val(ci, mi, qks[j]) : null)) }));
    }
    out.kind = 'rank'; out.rankN = N; out.order = desc ? 'desc' : 'asc'; out.fmt = fmtFor(unit); out.unit = unit === '$' ? '$' : '%'; out.metric = mname;
    const lowest = !desc, sc = U.scope ? ' · ' + U.scope : '';
    const TT = { cap: lowest ? `The ${N} smallest companies by market value` : `The ${N} most valuable companies`, rev: `The ${N} ${lowest ? 'smallest' : 'biggest'} companies by revenue`,
      gp: `The ${N} ${lowest ? 'lowest' : 'biggest'} gross profits`, oi: `The ${N} ${lowest ? 'lowest' : 'biggest'} operating profits`, ni: `The ${N} ${lowest ? 'biggest losses' : 'biggest earners'}`,
      om: `The ${N} ${lowest ? 'lowest' : 'highest'} operating margins`, nm: `The ${N} ${lowest ? 'lowest' : 'highest'} net margins`, growth: `The ${N} ${lowest ? 'slowest' : 'fastest'}-growing companies`,
      pe: `The ${N} ${lowest ? 'cheapest' : 'most expensive'} stocks by P/E`, pb: `The ${N} ${lowest ? 'lowest' : 'highest'} price-to-book ratios`, ps: `The ${N} ${lowest ? 'lowest' : 'highest'} price-to-sales ratios`,
      dv: `The ${N} most traded stocks`, ret: `The ${N} ${lowest ? 'worst' : 'best'} stocks: ${win === 'ytd' ? 'year to date' : win + '-month total return'}` };
    out.title = out.title || TT[key] + sc;
    const G = out.grid, L = G.length - 1;
    out.sub = out.sub || `${out.quarterly ? quarterLabel(G[0]) : monthYear(G[0])} → ${out.quarterly ? quarterLabel(G[L]) : monthYear(G[L])} · ${mname}` + (fundamental ? ' · SEC filings' : ' · weekly closes') + ' · US-listed companies on the site';
    out.foot = "Today's companies only: those delisted, merged or bankrupt are missing from earlier years";
    out.notes.add(out.foot + '.');
    if (fundamental && step !== 'q') out.notes.add('A quarter\'s figures count from 46 days after it ended, when they were public.');
    if (key === 'pe') out.notes.add('P/E = market value ÷ net income of the last four quarters; companies with losses, or earning under 2% of revenue (P/E in the thousands), are left out.');
    if (key === 'pb') out.notes.add('P/B = market value ÷ stockholders\' equity at the latest quarter; negative equity and P/B above 200 are left out.');
    if ((key === 'om' || key === 'nm' || key === 'growth') && minrev) out.notes.add(`Only companies with at least ${money(minrev * 1e6)} of revenue a year.`);
    if (capLike || (capF && st.capby !== 'now')) {
      const ap = new Set(meta.approx_cap || []), shown = out.series.filter((x) => ap.has(x.key)).map((x) => x.key);
      if (shown.length) out.notes.add(`${shown.join(', ')}: no SEC share count, so market value uses today's count held back up to five years (approximate).`);
      out.notes.add('Market value = the month-end price × the shares outstanding then (10-Q / 10-K cover pages), from 2009 on.');
    }
    out.series = out.series.filter((x) => x.v.some(fin));
    return out;
  }

  /* ---------- drawdowns: how far below its highest close each ticker stood, week by week ---------- */
  async function buildDrawdown(st, out, T) {
    if (!T.length) throw new Error('Add tickers');
    const P = new Map();
    await Promise.all(T.map(async (s) => { const p = await price(s); if (p) P.set(s, p); }));
    T.filter((s) => !P.has(s)).forEach((s) => out.notes.add(s + ': no weekly prices on file'));
    if (!P.size) throw new Error('No prices on file for ' + T.join(', '));
    const have = [...P.values()], to = Math.min(st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now(), ...have.map(last));
    const from = st.from ? Date.parse(st.from + 'T00:00:00Z') : to - 10 * 365.25 * DAY;
    const GA = weeklyGrid(iso(Math.min(...have.map(first))), iso(to)), G = GA.filter((g) => g >= from - 3 * DAY), cut = GA.length - G.length;
    if (G.length < 4) throw new Error('Fewer than four weeks in that range');
    for (const s of T) {
      const p = P.get(s); if (!p) continue;
      const long = p.long && p.long.t[0] < (p.px ? p.px.t[0] : Infinity) ? { t: p.long.t, v: p.long.v } : { t: p.px.t, v: p.px.a };
      let peak = -Infinity;
      const dd = GA.map((g) => { const v = asof(long.t, long.v, g); if (!fin(v)) return null; peak = Math.max(peak, v); return v / peak - 1; });
      out.series.push({ key: s, label: s, name: p.name, v: dd.slice(cut) });
    }
    out.grid = G; out.zero = true; out.unit = '%'; out.dd = true;
    out.fmt = (v) => (fin(v) ? (v > -0.0005 ? 'at the high' : pctf(v, 1)) : '—');
    out.title = out.title || `How far below the high: ${out.series.map((x) => x.key).join(' vs ')}`;
    out.sub = out.sub || `${dayLabel(G[0])} → ${dayLabel(G[G.length - 1])} · total return · each week against the highest close before it`;
    return out;
  }

  /* ---------- monthly returns: one ticker, a calendar heatmap that fills in month by month ---------- */
  async function buildCalendar(st, out, T) {
    const sym = T[0]; if (!sym) throw new Error('Add a ticker');
    const p = await price(sym); if (!p) throw new Error('No weekly prices on file for ' + sym);
    if (T.length > 1) out.notes.add('Monthly returns show one ticker: ' + sym);
    const to = Math.min(st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now(), last(p));
    const from = Math.max(st.from ? Date.parse(st.from + 'T00:00:00Z') : to - 10 * 365.25 * DAY, first(p) + 35 * DAY);
    const long = p.long && p.long.t[0] < (p.px ? p.px.t[0] : Infinity) ? { t: p.long.t, v: p.long.v } : { t: p.px.t, v: p.px.a };
    const d0 = new Date(from), d1 = new Date(to), cells = [], G = [], vals = [];
    let prev = asof(long.t, long.v, Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), 0), 12);
    for (let y = d0.getUTCFullYear(), m = d0.getUTCMonth(); y < d1.getUTCFullYear() || (y === d1.getUTCFullYear() && m <= d1.getUTCMonth()); m === 11 ? (y++, m = 0) : m++) {
      const end = Math.min(Date.UTC(y, m + 1, 0), to), v = asof(long.t, long.v, end, 12);
      const r = fin(v) && fin(prev) && prev > 0 ? v / prev - 1 : null;
      if (fin(v)) prev = v;
      cells.push([y, m, r]); G.push(end); vals.push(r);
    }
    if (G.length < 3) throw new Error('Fewer than three months in that range');
    const years = [...new Set(cells.map((c) => c[0]))];
    out.grid = G; out.cal = { years, cells }; out.unit = '%'; out.fmt = (v) => pctf(v, 1); out.zero = true;
    out.series = [{ key: sym, label: sym, name: p.name, v: vals }];
    out.title = out.title || `${sym}: every month since ${MON[d0.getUTCMonth()]} ${d0.getUTCFullYear()}`;
    out.sub = out.sub || `${p.name} · monthly total return (dividends reinvested) · ${monthYear(G[0])} → ${monthYear(G[G.length - 1])}`;
    return out;
  }

  /* ---------- the spread of returns: every company's return each year, as a histogram ---------- */
  const EDGES = (() => { const e = []; for (let x = -0.8; x <= 1.5 + 1e-9; x += 0.1) e.push(+x.toFixed(2)); return e; })();     // tails below −80% and from +150%
  async function buildDist(st, out) {
    const meta = await rankMeta(), m0 = meta._m0;
    const capF = String(st.cmin).trim() !== '' || String(st.cmax).trim() !== '';
    const F = { 'm-px': await panel('m-px') };
    if (capF && st.capby !== 'now') F['m-cap'] = await panel('m-cap');
    if (!Array.isArray(F['m-px'])) throw new Error('A leaderboard file is missing (m-px)');
    const MB = st.idx ? await members() : null;
    const U = universe(st, meta, F, MB), lastM = meta.months.n - 1;
    const y0 = Math.max(m0.y + 1, st.from ? +st.from.slice(0, 4) : 2001), now = new Date(mEnd(lastM, m0)), y1 = Math.min(now.getUTCFullYear(), st.to ? +st.to.slice(0, 4) : 9999);
    const spyP = await price('SPY'), spy = spyP && (spyP.long || (spyP.px && { t: spyP.px.t, v: spyP.px.a }));
    const yrs = [];
    for (let y = y0; y <= y1; y++) {
      const a = (y - 1 - m0.y) * 12 + 11 - m0.m, b = Math.min(lastM, (y - m0.y) * 12 + 11 - m0.m);
      const rs = [];
      for (let ci = 0; ci < meta.cos.length; ci++) { if (!U.ok(ci, a)) continue; const p0 = at(F['m-px'][ci], a), p1 = at(F['m-px'][ci], b); if (fin(p0) && fin(p1) && p0 > 0) rs.push([ci, p1 / p0 - 1]); }
      if (rs.length < 20) continue;                       // fewer than twenty companies: no year
      const counts = new Array(EDGES.length + 1).fill(0);
      for (const [, r] of rs) { let k = 0; while (k < EDGES.length && r >= EDGES[k]) k++; counts[k]++; }
      const sorted = rs.map((x) => x[1]).sort((u, v) => u - v), med = sorted[Math.floor(sorted.length / 2)];
      // the best and the worst named: above +1,000% is nearly always a bad close in the source, so not named
      const sane = rs.filter((x) => x[1] <= 10), best = (sane.length ? sane : rs).reduce((m, x) => (x[1] > m[1] ? x : m)), worst = rs.reduce((m, x) => (x[1] < m[1] ? x : m));
      const s0 = spy ? asof(spy.t, spy.v, mEnd(a, m0), 12) : null, s1 = spy ? asof(spy.t, spy.v, mEnd(b, m0), 12) : null;
      yrs.push({ y, ytd: b < (y - m0.y) * 12 + 11 - m0.m, n: rs.length, shares: counts.map((c) => c / rs.length), median: med, up: rs.filter((x) => x[1] > 0).length / rs.length,
        best: [meta.cos[best[0]][0], best[1]], worst: [meta.cos[worst[0]][0], worst[1]], spy: fin(s0) && fin(s1) ? s1 / s0 - 1 : null });
    }
    if (yrs.length < 2) throw new Error('Fewer than two years with enough companies (twenty or more)');
    out.kind = 'dist'; out.yearly = true; out.grid = yrs.map((x) => Date.UTC(x.y, 11, 31)); out.hist = { edges: EDGES, yrs };
    out.unit = '%'; out.fmt = (v) => pctf(v, 1);
    out.series = [{ key: 'median', label: 'Median stock', name: 'the middle company', v: yrs.map((x) => x.median) }];
    out.title = out.title || `Every stock's year, ${yrs[0].y}–${yrs[yrs.length - 1].y}` + (U.scope ? ' · ' + U.scope : '');
    out.sub = out.sub || `How each year's returns spread across the companies on the site · total return, December to December` + (yrs[yrs.length - 1].ytd ? ' (this year: so far)' : '');
    out.foot = "Today's companies only: those that went bust or were bought are missing, so the left tail is too thin";
    out.notes.add(out.foot + '.');
    return out;
  }

  /* ---------- six more: bubble, treemap, sector weights, the earnings flow, the dividend snowball, timing ---------- */
  async function panelFiles(names) {
    const F = {};
    await Promise.all([...new Set(names)].map(async (f) => { F[f] = await panel(f); }));
    for (const f of Object.keys(F)) if (!Array.isArray(F[f])) throw new Error('A leaderboard file is missing (' + f + ')');
    return F;
  }
  function monthRange(st, meta, defFrom) {
    const m0 = meta._m0, lastM = meta.months.n - 1;
    const fromMs = st.from ? Date.parse(st.from + 'T00:00:00Z') : defFrom, toMs = st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now();
    const i0 = clamp(mIndex(fromMs, m0), 13, lastM), i1 = clamp(mIndex(toMs, m0), i0, lastM), out = [];
    for (let i = i0; i <= i1; i++) out.push(i);
    if (out.length < 2) throw new Error('Fewer than two months in that range');
    return out;
  }
  // a fixed axis for the whole video: the 3rd–97th percentile of every value shown, a little room around it (beyond: at the edge)
  function domain(vals, log) {
    const v = vals.filter((x) => fin(x) && (!log || x > 0)).map((x) => (log ? Math.log(x) : x)).sort((a, b) => a - b);
    if (!v.length) return [0, 1];
    let lo = v[Math.floor(0.03 * (v.length - 1))], hi = v[Math.ceil(0.97 * (v.length - 1))];
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    return [lo - pad, hi + pad];
  }
  const BUB_SIZE = { cap: 'Market value', rev: 'Revenue, last 12 months', ni: 'Net income, last 12 months', dv: 'Dollar volume' };
  async function buildBubble(st, out) {
    const meta = await rankMeta(), m0 = meta._m0, Q = meta._Q;
    const kx = RANK[st.bx] ? st.bx : 'growth', ky = RANK[st.by] ? st.by : 'ret', ks = BUB_SIZE[st.bs] ? st.bs : 'cap';
    const F = await panelFiles([...RANK[kx][2], ...RANK[ky][2], ...RANK[ks][2], 'm-cap']);
    const MB = st.idx ? await members() : null, U = universe(st, meta, F, MB);
    const months = monthRange(st, meta, Date.UTC(2012, 0, 31)), qFor = qForOf(Q, m0, 'm'), qks = months.map(qFor);
    const o = { m0, step: 'm', minrev: Math.max(0, +st.minrev || 0) * 1e3, win: st.win === 'ytd' ? 'ytd' : Math.max(1, Math.round(+st.win || 12)) };
    const mx = makeMeasure(kx, F, o), my = makeMeasure(ky, F, o), ms = makeMeasure(ks, F, o), cap = makeMeasure('cap', F, o);
    const typed = tickers({ t: st.bt }), N = clamp(Math.round(+st.bn || 25), 5, 80), L = months.length - 1;
    let pick;
    if (typed.length) pick = typed.map((t) => meta.cos.findIndex((c) => c[0] === t)).filter((i) => i >= 0);
    else {                                                // the largest at the end, followed back in time
      const list = [];
      for (let ci = 0; ci < meta.cos.length; ci++) if (U.ok(ci, months[L])) { const v = cap(ci, months[L], qks[L]); if (fin(v)) list.push([ci, v]); }
      pick = list.sort((a, b) => b[1] - a[1]).slice(0, N).map((x) => x[0]);
    }
    if (!pick.length) throw new Error('No company fits those settings');
    out.series = pick.map((ci) => ({ key: meta.cos[ci][0], label: meta.cos[ci][0], name: meta.cos[ci][1], sec: meta.cos[ci][2],
      x: months.map((mi, j) => mx(ci, mi, qks[j])), y: months.map((mi, j) => my(ci, mi, qks[j])), s: months.map((mi, j) => ms(ci, mi, qks[j])) }))
      .filter((r) => r.x.some(fin) && r.y.some(fin));
    if (!out.series.length) throw new Error('Nothing to draw for those measures');
    out.series.forEach((r) => { r.v = r.s; });
    const logx = ['pe', 'ps', 'pb'].includes(kx), logy = ['pe', 'ps', 'pb'].includes(ky);
    out.kind = 'bubble'; out.grid = months.map((mi) => mEnd(mi, m0));
    out.bub = { kx, ky, ks, fx: fmtFor(RANK[kx][1]), fy: fmtFor(RANK[ky][1]), fs: fmtFor('$'), logx, logy,
      dx: domain(out.series.flatMap((r) => r.x), logx), dy: domain(out.series.flatMap((r) => r.y), logy), smax: Math.max(...out.series.flatMap((r) => r.s.filter(fin)), 1) };
    out.fmt = fmtFor('$'); out.unit = '$'; out.metric = BUB_SIZE[ks];
    const rl = (k) => (k === 'ret' ? (o.win === 'ytd' ? 'return this year' : o.win + '-month return') : RANK[k][0].toLowerCase());
    out.bub.lx = rl(kx).replace(/^./, (c) => c.toUpperCase()); out.bub.ly = rl(ky).replace(/^./, (c) => c.toUpperCase());
    out.title = out.title || `${RANK[ky][0] === 'Total return' ? (o.win === 'ytd' ? 'Return this year' : o.win + '-month return') : RANK[ky][0]} against ${rl(kx)}` + (typed.length ? '' : `: the ${N} largest companies`) + (U.scope ? ' · ' + U.scope : '');
    out.sub = out.sub || `${monthYear(out.grid[0])} → ${monthYear(out.grid[L])} · bubble size: ${BUB_SIZE[ks].toLowerCase()} · colour: sector · month by month`;
    out.foot = typed.length ? '' : "Today's largest companies, followed back in time";
    return out;
  }
  async function buildTreemap(st, out) {
    const meta = await rankMeta(), m0 = meta._m0;
    const F = await panelFiles(['m-cap', 'm-px']), MB = st.idx ? await members() : null, U = universe(st, meta, F, MB);
    const months = monthRange(st, meta, Date.UTC(2012, 0, 31)), N = clamp(Math.round(+st.tn || 50), 10, 150);
    const top = months.map((mi) => {
      const list = [];
      for (let ci = 0; ci < meta.cos.length; ci++) if (U.ok(ci, mi)) { const v = at(F['m-cap'][ci], mi); if (fin(v) && v > 0) list.push([ci, v]); }
      return new Map(list.sort((a, b) => b[1] - a[1]).slice(0, N));
    });
    const pick = [...new Set(top.flatMap((m) => [...m.keys()]))];
    if (!pick.length) throw new Error('No market values for those settings yet');
    out.series = pick.map((ci) => ({ key: meta.cos[ci][0], label: meta.cos[ci][0], name: meta.cos[ci][1], sec: meta.cos[ci][2],
      v: months.map((mi, j) => (top[j].has(ci) ? top[j].get(ci) * 1e6 : 0)),
      r: months.map((mi) => { const a = at(F['m-px'][ci], mi), b = at(F['m-px'][ci], mi - 12); return fin(a) && fin(b) && b > 0 ? a / b - 1 : null; }) }));
    const mean = (r) => r.v.reduce((a, x) => a + x, 0) / r.v.length, secTot = {};
    out.series.forEach((r) => { r.avg = mean(r); secTot[r.sec] = (secTot[r.sec] || 0) + r.avg; });
    out.kind = 'treemap'; out.grid = months.map((mi) => mEnd(mi, m0)); out.fmt = fmtFor('$'); out.unit = '$'; out.metric = 'Market value';
    out.tm = { N, color: st.tc === 'sector' ? 'sector' : 'ret', secOrder: Object.keys(secTot).sort((a, b) => secTot[b] - secTot[a]) };
    out.title = out.title || `The ${N} most valuable companies, as a map` + (U.scope ? ' · ' + U.scope : '');
    out.sub = out.sub || `${monthYear(out.grid[0])} → ${monthYear(out.grid[out.grid.length - 1])} · area: market value · grouped by sector · colour: ${out.tm.color === 'ret' ? '12-month total return' : 'sector'}`;
    out.foot = "Today's companies only: those delisted, merged or bankrupt are missing from earlier years";
    return out;
  }
  // the Nasdaq-100's modified market-value weights, roughly: no company above 24% (cut to 20%), and the companies above 4.5%
  // together at most 48% (cut to 40%), the rest spread over the others in proportion
  function ndxWeights(w) {
    let a = w.slice();
    const spread = (big, freed) => { const rest = a.reduce((s2, x, i) => s2 + (big.has(i) ? 0 : x), 0); if (rest > 0) a = a.map((x, i) => (big.has(i) ? x : x * (1 + freed / rest))); };
    for (let it = 0; it < 20; it++) {
      const big = new Set(a.map((x, i) => (x > 0.24 ? i : -1)).filter((i) => i >= 0)); if (!big.size) break;
      let freed = 0; big.forEach((i) => { freed += a[i] - 0.2; a[i] = 0.2; }); spread(big, freed);
    }
    const big = new Set(a.map((x, i) => (x > 0.045 ? i : -1)).filter((i) => i >= 0)), agg = [...big].reduce((s2, i) => s2 + a[i], 0);
    if (agg > 0.48) { const f = 0.4 / agg; a = a.map((x, i) => (big.has(i) ? x * f : x)); spread(big, agg - 0.4); }
    return a;
  }
  // a share price as it traded at the end of month mi, from a weekly history (split-adjusted closes and the splits after)
  function tradedAt(th, mi, m0) {
    if (!th || !th.start) return null;
    const P = th.p && th.p.length ? th.p : th.c, s0 = Date.parse(th.start + 'T00:00:00Z');
    let j = Math.floor((mEnd(mi, m0) - s0) / WEEK);
    if (j >= P.length && mEnd(mi, m0) - (s0 + (P.length - 1) * WEEK) <= 31 * DAY) j = P.length - 1;   // this month, still running
    if (j < 0 || j >= P.length) return null;
    let k = j; while (k >= 0 && j - k < 3 && !fin(P[k])) k--;
    if (k < 0 || !fin(P[k])) return null;
    let f = 1; for (const [i, r] of th.sp || []) if (i > k && fin(r) && r > 0) f *= r;
    return P[k] * f;
  }
  const IDX_W = { dji: 'price', ndx: 'ndx' };                // every other index: market value
  async function buildSectors(st, out) {
    const meta = await rankMeta(), m0 = meta._m0;
    if (st.sw === 'fund') return buildFundSectors(st, out, meta);
    const F = await panelFiles(['m-cap']), MB = st.idx ? await members() : null, U = universe(Object.assign({}, st, { sec: '' }), meta, F, MB);
    const months = monthRange(st, meta, Date.UTC(2012, 0, 31));
    const how = U.ix && st.sw !== 'cap' ? IDX_W[U.ix] || 'cap' : 'cap';
    let share = st.sa !== 'abs';
    if (!share && how === 'price') { share = true; out.notes.add('A price-weighted index has no dollar size to show: shares of the index instead'); }
    const secs = [...new Set(meta.cos.map((c) => c[2]))], tot = months.map(() => ({})), NC = meta.cos.length;
    let TH = null;
    if (how === 'price') {                                // the Dow: each member's share price as traded, every month
      const cand = []; for (let ci = 0; ci < NC; ci++) if (months.some((mi) => U.ok(ci, mi))) cand.push(ci);
      TH = new Map();
      await Promise.all(cand.map(async (ci) => { const th = await json(HUB + 'market/history/t/' + meta.cos[ci][0] + '.json'); if (th) TH.set(ci, th); }));
    }
    const short = new Map();                              // members a month could not price: how many, the worst month
    months.forEach((mi, j) => {
      const list = [];
      for (let ci = 0; ci < NC; ci++) {
        if (!U.ok(ci, mi)) continue;
        const v = how === 'price' ? tradedAt(TH.get(ci), mi, m0) : at(F['m-cap'][ci], mi);
        if (fin(v) && v > 0) list.push([ci, v]);
      }
      if (how === 'price' && U.ix === 'dji' && list.length < 30) short.set(j, list.length);
      let w = list.map((x) => x[1]);
      if (how === 'ndx' && share) { const t0 = w.reduce((a, x) => a + x, 0); w = ndxWeights(w.map((x) => x / t0)).map((x) => x * t0); }
      list.forEach(([ci], k) => { const sc = meta.cos[ci][2]; tot[j][sc] = (tot[j][sc] || 0) + w[k] * (how === 'price' ? 1 : 1e6); });
    });
    const all = tot.map((t) => Object.values(t).reduce((a, x) => a + x, 0));
    if (!all.some((x) => x > 0)) throw new Error('No market values for those settings yet');
    const L = months.length - 1, ixName = U.ix ? IDX[U.ix] : '';
    out.series = secs.map((sc) => ({ key: sc, label: SECTORS[sc] || sc, name: SECTORS[sc] || sc, sec: sc, v: months.map((_, j) => (all[j] > 0 ? (share ? (tot[j][sc] || 0) / all[j] : tot[j][sc] || 0) : null)) }))
      .filter((r) => r.v.some((x) => x > 0)).sort((a, b) => (b.v[L] || 0) - (a.v[L] || 0));
    out.kind = 'sectors'; out.grid = months.map((mi) => mEnd(mi, m0)); out.stack = { share, total: all };
    out.fmt = share ? (v) => (fin(v) ? (100 * v).toFixed(1) + '%' : '—') : fmtFor('$'); out.unit = share ? '%' : '$';
    const wt = { price: 'weighted by share price, as the Dow is', ndx: 'modified market-value weights, as the Nasdaq-100 caps them (approximate)', cap: U.ix ? 'weighted by market value, as the index is' : 'by market value' }[how];
    out.metric = share ? (U.ix && st.sw !== 'cap' ? 'Weight in the ' + ixName : 'Share of market value') : 'Market value';
    out.weighting = how;
    out.title = out.title || (U.ix && st.sw !== 'cap' && share ? `What the ${ixName} is made of: each sector's weight in the index`
      : (share ? 'Who owns the market: each sector\'s share of market value' : 'Market value by sector') + (U.ix ? ' · ' + ixName : ''));
    out.sub = out.sub || `${monthYear(out.grid[0])} → ${monthYear(out.grid[L])} · ${U.ix ? (st.idxw === 'now' ? 'today\'s members' : 'the members of each month') + ' · ' + wt : 'US-listed companies on the site'}${U.capTxt ? ' · ' + U.capTxt : ''} · month by month`;
    out.foot = U.ix ? 'Members the site has no prices for are left out of their months' : "Today's companies only: those delisted, merged or bankrupt are missing from earlier years";
    if (how === 'price') {
      out.notes.add('The Dow adds up its 30 share prices: a $400 stock counts four times a $100 stock, whatever the size of the company. Each sector\'s weight here is the sum of its members\' prices as traded (not adjusted for later splits) over the sum of all thirty.');
      if (short.size) { const lo = Math.min(...short.values()); out.notes.add(`${short.size} of ${months.length} months price fewer than 30 members (as few as ${lo}): a former member the site has no prices for (delisted or taken over) is left out and the rest share its weight.`); }
    } else if (how === 'ndx') out.notes.add('The Nasdaq-100 caps its largest members each quarter; the caps here (24% → 20%, the members above 4.5% together 48% → 40%) are applied every month and are an approximation of the published weights.');
    else if (U.ix && st.sw !== 'cap') out.notes.add(`The ${ixName} weights its members by the market value of the shares that trade freely; this uses every share outstanding, so a company with a large founder or government stake counts a little more here.`);
    return out;
  }
  // a fund's sectors: today's holdings (N-PORT, or the sponsor's file) held back in time — each weight moved with its
  // stock's price since the report, the rest renormalized
  async function buildFundSectors(st, out, meta) {
    const m0 = meta._m0, sym = norm(st.sf || 'DIA'), e = await json(HUB + 'etf/e/' + sym + '.json');
    const h = e && e.holdings, top = (h && h.top) || [];
    if (!top.length) throw new Error(`No holdings on file for ${sym || 'that fund'} — try an ETF ticker such as DIA, QQQ, XLK or SCHD`);
    const F = await panelFiles(['m-px']), months = monthRange(st, meta, Date.UTC(2012, 0, 31)), lastM = meta.months.n - 1;
    // holdings without a ticker (iShares reports CUSIPs only) are matched by name
    const nameKey = (n) => String(n || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/\b(the|inc|corp|corporation|co|company|class [a-z]|ltd|plc|holdings?|group)\b/g, ' ').replace(/\s+/g, ' ').trim();
    const byT = new Map(meta.cos.map((c, i) => [c[0], i])), byN = new Map();
    meta.cos.forEach((c, i) => { const k = nameKey(c[1]); if (k && !byN.has(k)) byN.set(k, i); });
    const hm = clamp(h.date ? mIndex(Date.parse(h.date + 'T00:00:00Z'), m0) : lastM, 0, lastM);
    let all = 0, cov = 0;
    const held = new Map();
    for (const x of top) {
      const w = +x[6]; if (!(w > 0) || (x[7] && x[7] !== 'EC')) continue;
      all += w;
      const t = norm(String(x[4] || '').replace('.', '-')), ci = byT.has(t) ? byT.get(t) : byN.get(nameKey(x[0]));
      if (ci == null) continue;
      let p0 = null; for (let m = hm; m >= hm - 2 && !fin(p0); m--) p0 = at(F['m-px'][ci], m);
      if (!fin(p0) || p0 <= 0) continue;
      held.set(ci, (held.get(ci) || 0) + w / p0); cov += w;          // a number of "units": the weight over the price then
    }
    if (!held.size) throw new Error(`None of ${sym}'s holdings are companies the site draws`);
    const secs = [...new Set(meta.cos.map((c) => c[2]))], tot = months.map(() => ({}));
    months.forEach((mi, j) => { for (const [ci, u] of held) { const p = at(F['m-px'][ci], mi); if (fin(p) && p > 0) { const sc = meta.cos[ci][2]; tot[j][sc] = (tot[j][sc] || 0) + u * p; } } });
    const sums = tot.map((t) => Object.values(t).reduce((a, x) => a + x, 0)), L = months.length - 1;
    out.series = secs.map((sc) => ({ key: sc, label: SECTORS[sc] || sc, name: SECTORS[sc] || sc, sec: sc, v: months.map((_, j) => (sums[j] > 0 ? (tot[j][sc] || 0) / sums[j] : null)) }))
      .filter((r) => r.v.some((x) => x > 0)).sort((a, b) => (b.v[L] || 0) - (a.v[L] || 0));
    out.kind = 'sectors'; out.grid = months.map((mi) => mEnd(mi, m0)); out.stack = { share: true, total: sums }; out.weighting = 'fund';
    out.fmt = (v) => (fin(v) ? (100 * v).toFixed(1) + '%' : '—'); out.unit = '%'; out.metric = 'Weight in ' + sym;
    const shown = h.n && h.n > top.length ? `its ${top.length} largest of ${h.n} holdings` : `its ${top.length} holdings`;
    out.title = out.title || `Inside ${sym}: each sector's weight`;
    out.sub = out.sub || `${monthYear(out.grid[0])} → ${monthYear(out.grid[L])} · the holdings of ${h.date || 'the latest report'}, held back in time · month by month`;
    out.foot = `${sym}'s holdings of ${h.date || 'the latest report'}, each moved with its own price`;
    out.notes.add(`${sym} (${e.name || sym}): ${shown}, ${(100 * cov / (all || 1)).toFixed(0)}% of their weight in companies the site draws; the rest is left out and the weights renormalized.`);
    out.notes.add(`Funds report what they hold now, not a history: before ${h.date || 'the report'}, each holding's weight is moved back with its own price (total return), as if the fund had held the same shares all along — not the fund's real past portfolio.`);
    return out;
  }
  // the earnings flow (the site's Sankey: revenue → costs and profit → cash), morphing from quarter to quarter
  const CO_RAW = new Map();
  async function companyRaw(sym) {
    sym = norm(sym);
    if (!CO_RAW.has(sym)) CO_RAW.set(sym, (async () => {
      const ix = await json(SITE + 'index.json');
      const row = ((ix && ix.companies) || []).find((c) => norm(c.ticker) === sym);
      return row ? json(SITE + 'c/' + row.cik + '.json') : null;
    })());
    return CO_RAW.get(sym);
  }
  async function buildSankey(st, out, T) {
    const sym = T[0]; if (!sym) throw new Error('Add a company ticker');
    const c = await companyRaw(sym); if (!c) throw new Error('No company figures on file for ' + sym);
    const name = (c.profile && c.profile.name) || sym;
    let frames = [];
    if (st.sm !== 'long') {
      frames = (c.quarters || []).filter((q) => q.nodes && q.links && q.end && /^Q/i.test(q.label || '')).map((q) => ({ end: Date.parse(q.end + 'T00:00:00Z'), label: q.label, nodes: q.nodes, links: q.links, head: q.headline || {} })).sort((a, b) => a.end - b.end);
      if (frames.length < 2) out.notes.add('Fewer than two detailed quarters on file: ten years of revenue, profit and earnings instead');
    }
    if (frames.length < 2) {                              // ten years from the filings: revenue → costs and operating profit → earnings
      const C = await company(sym), get = (k) => new Map([...((C && C.q[k]) || new Map()).entries()]);
      const R = get('revenue'), OI = get('oi'), NI = get('ni');
      frames = [...R.keys()].filter((e) => OI.has(e) && NI.has(e)).sort().map((e) => {
        const rev = R.get(e), oi = OI.get(e), ni = NI.get(e), nodes = [{ id: 'revenue', col: 0, color: 'rev', name: 'Revenue', v: rev }], links = [];
        if (oi > 0) {
          nodes.push({ id: 'oi', col: 1, color: 'profit', name: 'Operating profit', v: oi }, { id: 'opcost', col: 1, color: 'cost', name: 'Operating costs', v: rev - oi });
          links.push({ s: 'revenue', t: 'oi', v: oi, color: 'profit' }, { s: 'revenue', t: 'opcost', v: rev - oi, color: 'cost' });
          if (ni > 0) {
            nodes.push({ id: 'net', col: 2, color: 'profit', name: 'Net earnings', v: ni });
            links.push({ s: 'oi', t: 'net', v: Math.min(ni, oi), color: 'profit' });
            if (oi > ni) { nodes.push({ id: 'tax', col: 2, color: 'cost', name: 'Tax, interest and other', v: oi - ni }); links.push({ s: 'oi', t: 'tax', v: oi - ni, color: 'cost' }); }
            else if (ni > oi) { nodes.push({ id: 'other', col: 1, color: 'profit', name: 'Other income', v: ni - oi }); links.push({ s: 'other', t: 'net', v: ni - oi, color: 'profit' }); }
          } else { nodes.push({ id: 'tax', col: 2, color: 'cost', name: 'Tax, interest and other', v: oi - ni }); links.push({ s: 'oi', t: 'tax', v: oi, color: 'cost' }); }
        } else {
          nodes.push({ id: 'opcost', col: 1, color: 'cost', name: 'Operating costs', v: rev - oi });
          links.push({ s: 'revenue', t: 'opcost', v: rev, color: 'cost' });
        }
        const d = new Date(Date.parse(e + 'T00:00:00Z'));
        return { end: Date.parse(e + 'T00:00:00Z'), label: 'Quarter to ' + monthYear(d.getTime()), nodes, links, head: { revenue: rev, oi, ni }, simple: true };
      });
      const from = st.from ? Date.parse(st.from + 'T00:00:00Z') : -Infinity;
      frames = frames.filter((f) => f.end >= from);
    }
    if (frames.length < 2) throw new Error('Fewer than two quarters on file for ' + sym);
    out.kind = 'sankey'; out.grid = frames.map((f) => f.end); out.quarterly = true; out.sk = { frames, simple: !!frames[0].simple };
    out.sk.max = Math.max(...frames.flatMap((f) => f.nodes.map((n) => Math.abs(n.v || 0))));
    out.series = [{ key: sym, label: sym, name, v: frames.map((f) => f.head.revenue ?? null) }];
    out.fmt = (v) => money(v); out.unit = '$'; out.metric = 'Revenue';
    out.title = out.title || `${name.replace(/,? (INC|CORP|CORPORATION|LTD|PLC|CO)\.?$/i, '')}: where the money goes, quarter by quarter`;
    const span = out.sk.simple ? `quarters to ${monthYear(frames[0].end)} → ${monthYear(frames[frames.length - 1].end)}` : `${frames[0].label} → ${frames[frames.length - 1].label}`;
    out.sub = out.sub || `${span} · ${out.sk.simple ? 'revenue → costs and operating profit → net earnings' : 'revenue → costs and profit → cash'} · GAAP, from SEC filings`;
    return out;
  }
  // the dividend snowball: dividends buying more shares, which pay more dividends
  // Realized historical dividend income (not a forward-yield promise).
  // 52 observed weekly periods form the terminal annual dividend window.
  const snowIncome = paid => paid.slice(-52).reduce((sum, x) => sum + (x || 0), 0);
  // payments week by week → {year: dollars}; and whether the window holds the whole of a calendar year
  function byYear(G, paid) { const out = {}; G.forEach((g, i) => { if (paid[i]) { const y = new Date(g).getUTCFullYear(); out[y] = (out[y] || 0) + paid[i]; } }); return out; }
  function fullYears(G) {
    if (!G.length) return () => false;
    const a = new Date(G[0]), b = new Date(G[G.length - 1]);
    const y0 = a.getUTCFullYear() + (a.getUTCMonth() === 0 && a.getUTCDate() <= 7 ? 0 : 1), y1 = b.getUTCFullYear() - (b.getUTCMonth() === 11 && b.getUTCDate() >= 24 ? 0 : 1);
    return (y) => y >= y0 && y <= y1;
  }
  async function buildSnowball(st, out, T) {
    if (!T.length) throw new Error('Add a dividend payer, e.g. SCHD or KO');
    const P = new Map();
    await Promise.all(T.slice(0, 3).map(async s => {
      const p = await price(s);
      if (p && p.px && p.px.div && p.px.div.length) P.set(s, p);
    }));
    T.slice(0, 3).filter(s => !P.has(s)).forEach(s =>
      out.notes.add(s + ': no dividend history found; excluded'));
    if (!P.size) throw new Error('None of these has dividends on file');
    const have = [...P.values()];
    const to = Math.min(st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now(),
      ...have.map(p => p.px.t[p.px.t.length - 1]));
    let from = st.from ? Date.parse(st.from + 'T00:00:00Z') : to - 15 * 365.25 * DAY;
    from = Math.max(from, ...have.map(p => p.px.t[0]));
    const G = weeklyGrid(iso(from), iso(to));
    if (G.length < 30) throw new Error('Less than half a year of usable price history');
    const initial = Number.isFinite(+st.amt) ? Math.max(0, +st.amt) : 10000;
    const recurring = Number.isFinite(+st.rec) ? Math.max(0, +st.rec) : 0;
    const unit = UNITS[st.ru] ? st.ru : 'm', every = Math.max(1, Math.round(+st.ri || 1));
    // The schedule is computed once at $1 per buy. Simulation is linear
    // in starting capital and contributions, including compounded DRIP units.
    const unitBuys = buySchedule(G, 1, every, unit, from);
    const tax = clamp(+st.dtax || 0, 0, 95) / 100;
    const target = +st.sgoal || 0, reverse = target > 0;
    if (reverse && (!Number.isFinite(target) || target > 1e12))
      throw Error('Enter a finite positive terminal dividend goal below $1 trillion');
    if (reverse && G.length < 52)
      throw Error('Backward income calculation requires at least 52 weekly observations for the terminal 12-month dividend estimate.');
    const targetAnnual = reverse ? target * (st.sunit === 'annual' ? 1 : 12) : null;
    const solveFor = st.ssolve === 'rec' ? 'rec' : 'lump';
    out.snowGoal = reverse ? { requested: target, unit: st.sunit === 'annual' ? 'annual' : 'monthly',
      annual: targetAnnual, solveFor, results: [] } : null;
    for (const [sym, p] of P) {
      const pr = priceOn(p, G), dv = divsOn(p, G), i0 = pr.findIndex(fin);
      if (i0 < 0) continue;
      // Dividend payment happens before new purchases in this weekly slot.
      function simulate(lump, perBuy) {
        let shares = 0, bought = 0, fromDiv = 0, last = null, firstShares = null, put = 0;
        const v = [], sh = [], inc = [], paid = G.map(() => 0);
        for (let i = 0; i < G.length; i++) {
          const px = fin(pr[i]) ? pr[i] : last;
          if (fin(px) && px > 0) last = px;
          if (i < i0 || !last) { v.push(null); sh.push(null); inc.push(null); continue; }
          if (i > i0 && dv[i]) {
            const cash = shares * dv[i] * (1 - tax);
            paid[i] = cash;
            const added = cash / last;
            shares += added; fromDiv += added;
          }
          const contribution = (i === i0 ? lump : 0) + unitBuys[i] * perBuy;
          if (contribution) { shares += contribution / last; bought += contribution / last; put += contribution; }
          if (i === i0) firstShares = shares;
          v.push(shares * last); sh.push(shares);
          inc.push(i - i0 >= 51 ? snowIncome(paid.slice(0, i + 1)) : null);
        }
        const annualIncome = snowIncome(paid);
        const firstAnnual = G.length - 1 - i0 >= 103 ? paid.slice(i0 + 1, i0 + 53).reduce((a, x) => a + x, 0) : null;   // the first 52 weeks, when there are two years
        return { v, sh, inc, paid, bought, fromDiv, initialShares: firstShares, put, firstAnnual,
          finalShares: sh[sh.length - 1], annualIncome, monthlyIncome: annualIncome / 12 };
      }
      let lump = initial, perBuy = recurring;
      if (reverse) {
        const base = solveFor === 'lump' ? simulate(0, recurring).annualIncome :
          simulate(initial, 0).annualIncome;
        const perDollar = solveFor === 'lump' ? simulate(1, 0).annualIncome :
          simulate(0, 1).annualIncome;
        if (!(perDollar > 1e-15)) {
          out.notes.add(sym + ': no dividend-producing purchases in the selected period; cannot solve this target.');
          continue;
        }
        const needed = Math.max(0, (targetAnnual - base) / perDollar);
        if (solveFor === 'lump') lump = needed;
        else perBuy = needed;
        if (base >= targetAnnual) out.notes.add(sym +
          ': fixed contributions already meet or exceed the dividend goal; solved amount is zero.');
      }
      const r = simulate(lump, perBuy), yearly = {};
      G.forEach((g, i) => { const y = new Date(g).getUTCFullYear(); yearly[y] = (yearly[y] || 0) + r.paid[i]; });
      out.series.push({ key: sym, label: sym, name: p.name, v:r.v, sh:r.sh, inc:r.inc,
        paid:r.paid, yearly, bought:r.bought, fromDiv:r.fromDiv, sh0:r.initialShares,
        initialShares:r.initialShares, finalShares:r.finalShares, annualIncome:r.annualIncome,
        monthlyIncome:r.monthlyIncome, initialCash:lump, perBuy, purchases:unitBuys.filter(Boolean).length, put:r.put, firstAnnual:r.firstAnnual });
      if (reverse) out.snowGoal.results.push({ticker:sym, initialCash:lump, perBuy,
        annualIncome:r.annualIncome, monthlyIncome:r.monthlyIncome, initialShares:r.initialShares,
        finalShares:r.finalShares, annualGoal:targetAnnual, achieved:r.annualIncome >= targetAnnual - .01});
    }
    if (!out.series.length) throw Error('No eligible dividend series could be calculated for this target and date range');
    let contrib = 0;
    const sample = out.series[0];
    out.contrib = G.map((_, i) => (contrib += (i === 0 ? sample.initialCash : 0) +
      unitBuys[i] * sample.perBuy));
    out.kind = 'snowball'; out.scf = st.scf === 'annual' ? 'annual' : 'monthly';
    out.grid = G; out.fmt = v => money(v); out.unit = '$';
    const names = out.series.map(s => s.key).join(' vs ');
    const interval = every > 1 ? every + ' ' + UNITS[unit][1] : UNITS[unit][0];
    out.title = reverse ? 'The dividends needed: ' + names : 'The dividend snowball: ' + names;
    out.sub = reverse ?
      money(target, 0) + (st.sunit === 'annual' ? '/year' : '/month') +
      ' terminal dividend target · reverse-calculated ' + (solveFor === 'lump' ? 'starting capital' : 'scheduled buy') +
      ' · dividends reinvested · ' + dayLabel(G[0]) + ' → ' + dayLabel(G[G.length - 1]) :
      money(initial, 0) + ' to start' + (recurring ? ' + ' + money(recurring, 0) + ' every ' + interval : '') +
      ' · every dividend buys more shares at that week’s price' + (tax ? ` (after a ${Math.round(tax * 100)}% tax)` : '') + ' · ' +
      dayLabel(G[0]) + ' → ' + dayLabel(G[G.length - 1]);
    if (tax) out.notes.add(`Dividends are counted after a ${Math.round(tax * 100)}% tax: only the rest buys shares.`);
    if (reverse) out.notes.add('Backward calculation is an IN-SAMPLE historical scenario, NOT a future forecast. Terminal income is actual gross distributions received over the final 52 weekly observations; monthly equivalent = annual / 12, even if payments are quarterly. Dividends are reinvested.');
    return out;
  }
  // bought at the top every year, at the bottom, on the first day, or a little every month — the same money each year
  async function buildTiming(st, out, T) {
    const sym = T[0] || 'SPY', p = await price(sym); if (!p) throw new Error('No weekly prices on file for ' + sym);
    if (T.length > 1) out.notes.add('Timing compares strategies on one ticker: ' + sym);
    const to = Math.min(st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now(), last(p));
    const y0 = Math.max(new Date(st.from ? Date.parse(st.from + 'T00:00:00Z') : to - 20 * 365.25 * DAY).getUTCFullYear(), new Date(first(p) + 7 * DAY).getUTCFullYear() + 1);
    const G = weeklyGrid(`${y0}-01-01`, iso(to)), tr = trOn(p, G), budget = Math.max(1, +st.yb || 2000);
    const years = [...new Set(G.map((g) => new Date(g).getUTCFullYear()))];
    const yr = G.map((g) => new Date(g).getUTCFullYear()), idx = (y) => G.map((_, i) => i).filter((i) => yr[i] === y && fin(tr[i]));
    const plans = { worst: {}, best: {}, first: {}, monthly: {} };
    for (const y of years) {
      const I = idx(y); if (!I.length) continue;
      const hi = I.reduce((a, i) => (tr[i] > tr[a] ? i : a), I[0]), lo = I.reduce((a, i) => (tr[i] < tr[a] ? i : a), I[0]);
      plans.worst[hi] = (plans.worst[hi] || 0) + budget; plans.best[lo] = (plans.best[lo] || 0) + budget; plans.first[I[0]] = (plans.first[I[0]] || 0) + budget;
      const byM = {}; I.forEach((i) => { const m = new Date(G[i]).getUTCMonth(); if (byM[m] == null) byM[m] = i; });
      const ms = Object.values(byM); ms.forEach((i) => { plans.monthly[i] = (plans.monthly[i] || 0) + budget / ms.length; });
    }
    const label = { worst: 'Bought at the top', best: 'Bought at the bottom', first: 'Bought on day one', monthly: 'A little every month' };
    const yearOf = (i) => yr[i];
    for (const k of ['best', 'first', 'monthly', 'worst']) {
      let units = 0; const v = [], flows = [];
      for (let i = 0; i < G.length; i++) {
        if (plans[k][i]) { units += plans[k][i] / tr[i]; flows.push([G[i], -plans[k][i]]); }
        // money of the year not invested yet waits as cash (the same budget arrives on the year's first week)
        const y = yearOf(i), cashWaiting = Object.entries(plans[k]).filter(([j]) => yearOf(+j) === y && +j > i).reduce((a, [, x]) => a + x, 0);
        v.push(fin(tr[i]) ? units * tr[i] + cashWaiting : null);
      }
      out.series.push({ key: k, label: label[k], name: label[k], v, flows });
    }
    let put = 0; out.contrib = G.map((g, i) => { if (i === 0 || yearOf(i) !== yearOf(i - 1)) put += budget; return put; });
    out.kind = 'timing'; out.grid = G; out.fmt = (v) => money(v); out.unit = '$'; out.timing = { sym, budget, years: years.length };
    out.title = out.title || `${money(budget, 0)} a year into ${sym}: perfect timing, worst timing, or no timing`;
    out.sub = out.sub || `${years[0]} → ${years[years.length - 1]} · each year's money at that year's lowest close, highest close, first week, or spread over the months · dividends reinvested · hindsight, to show what timing is worth`;
    return out;
  }

  async function buildRaw(st) {
    const notes = new Set(), T = tickers(st), k = st.k;
    const today = iso(Date.now());
    const out = { kind: k, series: [], notes, fmt: (v) => money(v), title: '', sub: '', unit: '$' };
    if (k === 'rank') return buildRank(st, out);
    if (k === 'dist') return buildDist(st, out);
    if (k === 'drawdown') return buildDrawdown(st, out, T);
    if (k === 'calendar') return buildCalendar(st, out, T);
    if (k === 'bubble') return buildBubble(st, out);
    if (k === 'treemap') return buildTreemap(st, out);
    if (k === 'sectors') return buildSectors(st, out);
    if (k === 'actual') return root.FFActual.build(st, out, { json, hub: HUB, rankMeta });
    if (k === 'holdings') return root.FFHoldingsVideo.build(st, out, { json, hub: HUB, rankMeta });
    if (k === 'sankey') return buildSankey(st, out, T);
    if (k === 'snowball') return buildSnowball(st, out, T);
    if (k === 'timing') return buildTiming(st, out, T);
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
      // one company: its own fiscal quarter names (Q2 FY27); several: the month each quarter ended
      const lab = cos.length === 1 ? cos[0].lab : null;
      out.qlabel = (g) => (lab ? lab.get(iso(g)) || quarterLabel(g) : monthYear(g));
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
      // a lump sum on the first week, and (optionally) the same amount bought again on a schedule; or, with an end value
      // to reach, the lump sum or the amount each time that reaches it (worked back for each ticker: the value at the
      // end is linear in the money put in, so one run with $1 gives the answer)
      const goal = Math.max(0, +st.goal || 0), solve = goal > 0 ? (st.solve === 'lump' ? 'lump' : 'rec') : '';
      const recIn = Math.max(0, +st.rec || 0), dca = solve === 'rec' || (solve !== 'lump' && recIn > 0) || (solve === 'lump' && recIn > 0);
      const rec = solve === 'rec' ? 1 : recIn;
      const lumpIn = solve ? Math.max(0, +st.amt || 0) : dca ? Math.max(0, +st.amt || 0) : Math.max(1, +st.amt || 10000);
      const nEv = Math.max(1, Math.round(+st.ri || 1)), unit = UNITS[st.ru] ? st.ru : 'm';
      const buys1 = buySchedule(G, 1, nEv, unit, st.from ? Date.parse(st.from + 'T00:00:00Z') : G[0]);
      const L = G.length - 1;
      // adjustments: a tax on dividends; a cash line at a fixed rate or the 3-month bill (and the dividends taken as cash
      // earning it); inflation as a line that keeps up with prices, or every value in dollars of the start
      const tax = clamp(+st.dtax || 0, 0, 95) / 100, cashR = rateOf(st.cashr), inflR = rateOf(st.inflr);
      const wantCash = st.cashl === '1' && !solve, wantInt = st.dint === '1' && st.div === 'split', wantInfl = (st.infl === 'line' || st.infl === 'real') && !solve;
      const Mc = ((wantCash || wantInt) && cashR == null) || (wantInfl && inflR == null) ? await macro() : null;
      let cashIdx = null, cpiIdx = null;
      if (wantCash || wantInt) {
        const bill = cashR == null ? monthlyOn(Mc, Mc && Mc.bill, G) : null;
        if (cashR != null || bill) cashIdx = growIdx(G, bill, cashR);
        else notes.add('Cash: the interest-rate history did not load, so cash is left out');
      }
      if (wantInfl) {
        const c = inflR == null ? monthlyOn(Mc, Mc && Mc.cpi, G) : null;
        if (inflR != null) cpiIdx = growIdx(G, null, inflR); else if (c) cpiIdx = c.map((x) => x / c[0]);
        else notes.add('Inflation: the consumer-price history did not load, so nothing is adjusted for it');
      }
      const cashG = wantInt && cashIdx ? cashIdx.map((x, i) => (i ? x / cashIdx[i - 1] : 1)) : null;
      // one ticker, a lump of `lump` and `each` on every scheduled buy: the value, the price-only value and the cash, week by
      // week; and the distributions paid in dollars (shares held × the amount per share that went ex that week) whichever
      // way they are used: taken as cash, reinvested (the total-return line holds them already) or left out. The shares
      // held are the units themselves on the price as traded, and the total-return value over the price as traded (pr)
      const run = (base, dv, mode, i0, lump, each, pr) => {
        const inflow = G.map((_, i) => (i < i0 ? 0 : (i === i0 ? lump : 0) + each * buys1[i]));
        let units = 0, cash = 0, last = null, sh = null, paid = 0, known = -1;
        const v = [], pv = [], cv = [], dc = [], pd = [], shs = [];
        for (let i = 0; i < G.length; i++) {
          if (i < i0) { v.push(null); pv.push(null); cv.push(null); dc.push(null); pd.push(null); shs.push(null); continue; }
          const px = fin(base[i]) ? base[i] : last;
          const d = i > i0 && dv ? dv[i] || 0 : 0;                 // paid on the shares held before this week's buy
          const now = d && sh ? sh * d : 0;
          paid += now;
          if (mode !== 'tr') cash = (cashG && i > i0 ? cash * cashG[i] : cash) + units * d;
          if (px) units += inflow[i] / px;
          last = px;
          const val = px ? units * px : null;
          if (mode !== 'tr') sh = units;
          else if (val != null && pr && fin(pr[i]) && pr[i] > 0) sh = val / pr[i];
          if (known < 0 && sh) known = i;
          pv.push(val); cv.push(cash); dc.push(paid); pd.push(now); shs.push(sh);
          v.push(val == null ? null : mode === 'split' ? val + cash : val);
        }
        return { v, pv, cv, inflow, dc, pd, sh: shs, known };
      };
      out.amt = lumpIn;
      let contrib = null, flows = null;
      const need = [];
      for (const s of T) {
        const p = P.get(s); if (!p) continue;
        const tr = trOn(p, G), pr = priceOn(p, G), dv = divsOn(p, G);
        let mode = st.div;
        if ((mode === 'price' || mode === 'split') && (!pr || !pr.some(fin))) { notes.add(`${s}: dividends are not on file yet for this ticker — shown with dividends reinvested (total return)`); mode = 'tr'; }
        let base = mode === 'tr' ? tr : pr;
        const i0 = base.findIndex(fin);
        if (i0 < 0) continue;
        const dvN = dv && tax ? dv.map((x) => x * (1 - tax)) : dv;
        if (tax && mode === 'tr') {
          if (pr && fin(pr[i0])) base = netTR(pr, dvN, i0);
          else notes.add(`${s}: no price as traded on file at the start, so the tax is not taken off its dividends`);
        }
        let lump = lumpIn, each = rec;
        if (solve) {
          const endOf = (a, b) => { const r = run(base, dvN, mode, i0, a, b, pr).v[L]; return fin(r) ? r : 0; };
          if (solve === 'lump') {
            const fromBuys = recIn > 0 ? endOf(0, recIn) : 0, perDollar = endOf(1, 0);
            if (!(perDollar > 0)) continue;
            lump = Math.max(0, (goal - fromBuys) / perDollar); each = recIn;
            if (fromBuys >= goal) notes.add(`${s}: the scheduled buys alone end above ${money(goal, 0)}, so no money is needed at the start`);
          } else {
            const fromLump = lumpIn > 0 ? endOf(lumpIn, 0) : 0, perBuy = endOf(0, 1);
            if (!(perBuy > 0)) continue;
            each = Math.max(0, (goal - fromLump) / perBuy); lump = lumpIn;
            if (fromLump >= goal) notes.add(`${s}: the money at the start alone ends above ${money(goal, 0)}, so no further buys are needed`);
          }
        }
        const r = run(base, dvN, mode, i0, lump, each, pr);
        let c = 0;
        const sc = r.inflow.map((x, i) => (i < i0 ? null : (c += x))), sf = r.inflow.map((x, i) => [G[i], -x]).filter(([, a]) => a);
        if (!contrib) { contrib = sc; flows = sf; }
        const row = { key: s, label: s, name: p.name, v: r.v, price: mode === 'tr' ? null : r.pv, cash: mode === 'split' ? r.cv : null, mode, idx: base };
        // the distributions paid, in dollars as paid: in all, the last 52 weeks, and (reinvested) what the shares they
        // bought are worth at the end — the total-return value less the same money in the price alone
        if (dv && r.known >= 0) {
          const paid52 = L - i0 >= 51 ? r.pd.slice(L - 51).reduce((a, x) => a + (x || 0), 0) : null;
          row.dist = r.dc; row.paid = r.pd;
          row.inc = { total: r.dc[L], last12: paid52, shares: r.sh[L], from: r.known, mode, years: byYear(G, r.pd) };
          if (mode === 'tr' && pr && fin(pr[i0]) && r.known <= i0 + 2) {
            const po = run(pr, dvN, 'price', i0, lump, each, pr).v[L];
            if (fin(po) && fin(r.v[L])) row.inc.worth = r.v[L] - po;
          }
          if (r.known > i0 + 2) notes.add(`${s}: distributions are on file from ${dayLabel(G[r.known])}; those paid before then are not counted`);
        }
        if (solve) { Object.assign(row, { contrib: sc, flows: sf, put: sc[L], lump, each }); need.push(row); }
        out.series.push(row);
      }
      const lead = out.series[0], i0b = lead ? lead.v.findIndex(fin) : 0;
      if (lead && !solve) {                                     // the same money in cash, or keeping up with prices
        const line = (key, label, name, idx, kind) => { const r = run(idx, null, 'price', i0b, lumpIn, rec, idx); out.series.push({ key, label, name, v: r.v, price: null, cash: null, mode: 'price', idx, bench: kind }); };
        if (wantCash && cashIdx) line('CASH', 'Cash', cashR != null ? `Cash at ${cashR}% a year` : Mc && Mc.exact ? 'Cash in 3-month Treasury bills' : 'Cash at the Fed funds rate', cashIdx, 'cash');
        if (st.infl === 'line' && cpiIdx) line('CPI', 'Inflation', inflR != null ? `Prices rising ${inflR}% a year` : 'Keeping up with consumer prices (CPI)', cpiIdx, 'infl');
      }
      const md = { tr: 'dividends reinvested', price: 'price only (dividends left out)', split: 'price + dividends taken as cash' }[st.div]
        + (tax ? ` after a ${Math.round(tax * 100)}% tax` : '') + (cashG ? ', earning the cash rate' : '');
      const names = out.series.filter((x) => !x.bench).map((x) => x.key).join(' vs ');
      const nb = Math.round(buys1.reduce((a, x) => a + x, 0));
      const per = `every ${nEv > 1 ? nEv + ' ' + UNITS[unit][1] : UNITS[unit][0]}`, every = `${money(rec, 0)} ${per}`;
      if (solve) {
        // each ticker's own amount: the label carries it, the end card ranks the smallest first
        const amt = (x) => (solve === 'lump' ? money(x.lump, 0) + ' at the start' : money(x.each, 0) + ' ' + per);
        out.series.forEach((x) => { x.need = amt(x); });
        out.goal = { value: goal, solve, per, recIn, lumpIn, buys: nb };
        out.title = out.title || `What it took to reach ${money(goal, 0)}: ${names}`;
        out.sub = out.sub || `${dayLabel(G[0])} → ${dayLabel(G[L])} · ${md} · ` + (solve === 'lump' ? (recIn > 0 ? `the money at the start, with ${money(recIn, 0)} ${per} on top` : 'one sum at the start')
          : `the same amount ${per} (${nb} buys)` + (lumpIn > 0 ? `, ${money(lumpIn, 0)} to start` : ''));
        out.base = null; out.contrib = null; out.flows = null; out.dca = null;
        notes.add(`Worked back from the end value: each ticker gets the amount that would have ended at exactly ${money(goal, 0)} on ${dayLabel(G[L])} — hindsight, not a plan.`);
      } else {
        const put = contrib ? contrib[L] : 0, nbR = rec ? nb : 0;
        out.title = out.title || (dca ? `${every} into ${names}` + (lumpIn ? ` (${money(lumpIn, 0)} to start)` : '') : `${money(lumpIn, 0)} invested in ${names}`);
        out.sub = out.sub || `${dayLabel(G[0])} → ${dayLabel(G[L])} · ${md} · ` + (dca ? `${money(put, 0)} put in over ${nbR} buys` : 'weekly closes');
        out.base = dca ? null : lumpIn; out.contrib = dca ? contrib : null; out.flows = flows;
        out.dca = dca ? { every, buys: nbR, put } : null;
      }
      out.split = st.div === 'split' && out.series.some((x) => x.cash);
      out.div = st.div;
      const df = cpiIdx ? cpiIdx.map((x) => cpiIdx[i0b] / x) : null;   // a week's dollars in dollars of the start
      out.adj = { tax, cash: cashIdx ? { rate: cashR, src: cashR != null ? 'fixed' : Mc && Mc.exact ? 'bill' : 'ff' } : null,
        infl: cpiIdx ? { mode: st.infl, rate: inflR, src: inflR != null ? 'fixed' : Mc && Mc.exact ? 'cpi' : 'cpi-yoy', df, rise: cpiIdx[L] / cpiIdx[i0b] - 1 } : null,
        disc: rateOf(st.disc), interest: !!cashG, flowsNom: out.flows };
      if (st.infl === 'real' && df) {
        const dfl = (a) => (a ? a.map((x, i) => (fin(x) ? x * df[i] : x)) : a), at = new Map(G.map((g, i) => [g, i]));
        for (const x of out.series) {
          x.nom = x.v; x.v = dfl(x.v); x.price = dfl(x.price); x.cash = dfl(x.cash); x.idx = dfl(x.idx);
          if (x.paid) {
            x.paid = dfl(x.paid); let c = 0; x.dist = x.dist.map((d, i) => (d == null ? null : (c += x.paid[i] || 0)));
            Object.assign(x.inc, { total: x.dist[L], years: byYear(G, x.paid), last12: fin(x.inc.last12) ? x.paid.slice(L - 51).reduce((a, y) => a + (y || 0), 0) : null, worth: fin(x.inc.worth) ? x.inc.worth * df[L] : x.inc.worth });
          }
        }
        if (out.contrib) { let c = 0; const raw = out.contrib; out.contrib = raw.map((x, i) => (x == null ? null : (c += (x - (i && raw[i - 1] != null ? raw[i - 1] : 0)) * df[i]))); }
        if (out.flows) out.flows = out.flows.map(([t, a]) => [t, a * df[at.get(t)]]);
        if (out.dca) out.dca.put = out.contrib[L];
        out.real = true;
        out.sub = out.sub + ` · after inflation, in ${monthYear(G[i0b])} dollars`;
        notes.add(`After inflation: every value in dollars of ${monthYear(G[i0b])} (${inflR != null ? `prices rising ${inflR}% a year` : 'the consumer price index'}); prices rose ${pctf(out.adj.infl.rise, 1).replace('+', '')} over the window.`);
      }
      if (cpiIdx && inflR == null && !(Mc && Mc.exact)) notes.add('Consumer prices are rebuilt from the year-on-year CPI rates month by month (approximate) until the CPI index itself is published.');
      if (cashIdx && cashR == null) notes.add(Mc && Mc.exact ? 'Cash earns the 3-month Treasury bill yield of each month (FRED DGS3MO), compounded weekly.' : 'Cash earns the Fed funds rate of each month (FRED FEDFUNDS), compounded weekly, until the 3-month bill history is published.');
      if (tax) notes.add(`Dividends are counted after a ${Math.round(tax * 100)}% tax${st.div === 'tr' ? ': only the rest is reinvested (the total return is rebuilt from the price and the dividends)' : ''}.`);
      if ((dca || solve === 'rec') && unit === 'd') notes.add('Prices are weekly closes: buys on the trading days of a week all use that week\'s close');
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
    appearance: { name: 'Appearance settings / 外观设置' },
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
  const benchCol = (th, kind) => { const light = luminance(th.text) < 0.4; return kind === 'cash' ? (light ? '#6b6a66' : '#cfd8e3') : (light ? '#9c4f2e' : '#f2b39b'); };
  const upDown = (th, up) => (th.text === '#1d1d1b' || luminance(th.text) < 0.4 ? (up ? '#17734a' : '#c0392b') : (up ? '#3ee39a' : '#ff6b6b'));
  // distributions reinvested, in dollars as paid, beside each ticker: shown with dividends reinvested unless turned off,
  // and left off the chart whose own panel draws them
  const reinvOn = (V) => V.kind === 'growth' && V.div === 'tr' && V.dinc !== 'off' && !V.divPanel && !V.divAbove && V.series.some((s) => s.inc && s.inc.total > 0);
  function reinvNote(V, s, f, short) {
    if (!s.dist) return '';
    const d = valAt(s.dist, f);
    return fin(d) && d > 0 ? (short ? `+${money(d)} dividends` : `${money(d)} dividends reinvested`) : '';
  }
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  const alpha = (hex, a) => { if (!/^#/.test(hex)) return hex; const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };

  // the timeline: a short intro, the run, the hold on the last week (with the end card). o: the options ({dur, pace,
  // hold}) or the length in seconds
  function timing(V, o) {
    const op = o && typeof o === 'object' ? o : { dur: o };
    const D = Math.max(4, +op.dur || 20), intro = Math.min(0.8, D * 0.06);
    const auto = V.endCard ? Math.min(3.2, D * 0.18) : Math.min(1.2, D * 0.06);
    const hold = op.hold != null && op.hold !== '' && op.hold !== 'auto' && fin(+op.hold) ? clamp(+op.hold, 0, D * 0.45) : auto;
    return { D, intro, hold, run: Math.max(0.5, D - intro - hold), pace: op.pace || 'steady' };
  }
  const PACES = [['steady', 'Steady'], ['linear', 'Even'], ['ease', 'Ease in and out'], ['finale', 'Slow-motion finish'], ['build', 'Speeds up']];
  function frameIndex(V, tm, t) {                          // steady: a gentle start and stop around an even pace
    const n = V.grid.length - 1, u = clamp((t - tm.intro) / tm.run, 0, 1), sm = u * u * (3 - 2 * u);
    const e = tm.pace === 'linear' ? u : tm.pace === 'ease' ? sm : tm.pace === 'finale' ? 1 - Math.pow(1 - u, 1.8) : tm.pace === 'build' ? Math.pow(u, 1.7) : 0.82 * u + 0.18 * sm;
    return n * e;
  }

  function draw(ctx, W, H, V, opt, t) {
    const th = (opt.theme === 'appearance' ? (opt.appearanceTheme || root.FFAppearance?.videoTheme()) : THEMES[opt.theme]) || THEMES.bull, S = Math.min(W, H) / 1080, tm = timing(V, opt), f = frameIndex(V, tm, t);
    const portrait = H > W * 1.2, square = !portrait && H > W * 0.8;
    const pal = (i) => { const x = V.series && V.series[i]; return x && x.bench ? benchCol(th, x.bench) : th.pal[i % th.pal.length]; };
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
    let banded = false;
    if ((portrait || square) && (style === 'line' || style === 'area') && V.kind !== 'rrg' && V.kind !== 'calendar') {
      top = counters(ctx, V, f, top, W, S, th, F, pal, portrait ? 2 : Math.min(4, V.series.length)) + 26 * S;
      banded = true;                                          // the band shows the reinvested dividends: the line labels need not
    }
    const flat = style === 'bars' || V.kind === 'rank' || style === 'hist' || ['treemap', 'sankey'].includes(V.kind);
    const box = { x: pad + (flat ? 0 : 70 * S), y: top, w: W - 2 * pad - (flat ? 0 : 70 * S) - (style === 'line' || style === 'area' ? (portrait ? 150 : 210) * S : 0), h: bottom - top };
    if (V.kind === 'rank') rankRace(ctx, V, f, box, S, th, F);
    else if (V.kind === 'bubble') bubbleChart(ctx, V, f, { x: box.x, y: box.y, w: box.w + 30 * S, h: box.h - 40 * S }, S, th, F);
    else if (V.kind === 'treemap') treemapChart(ctx, V, f, box, S, th, F);
    else if (V.kind === 'sectors') stackChart(ctx, V, f, { x: box.x, y: box.y, w: box.w - 150 * S, h: box.h - 40 * S }, S, th, F);
    else if (V.kind === 'sankey') sankeyChart(ctx, V, f, box, S, th, F);
    else if (V.kind === 'snowball') snowballChart(ctx, V, f, box, S, th, F, pal);
    else if (style === 'heat') heatmap(ctx, V, f, box, S, th, F);
    else if (style === 'hist') histChart(ctx, V, f, { x: box.x + 60 * S, y: box.y, w: box.w - 60 * S, h: box.h }, S, th, F);
    else if (style === 'rrg') rrgChart(ctx, V, f, box, S, th, F, pal);
    else if (style === 'bars') barRace(ctx, V, f, box, S, th, F, pal);
    else if (style === 'tiles') tiles(ctx, V, f, box, S, th, F, pal, t, tm);
    else if (style === 'columns') columns(ctx, V, f, box, S, th, F, pal);
    else if ((V.split || (V.dinc === 'panel' && reinvOn(V))) && style === 'line') {   // distributions on their own lines, on their own scale below
      const gap = 70 * S, h1 = (box.h - gap) * 0.64, h2 = box.h - gap - h1, cashPanel = V.split;
      lineRace(ctx, cashPanel ? V : Object.assign({}, V, { divAbove: true }), f, { x: box.x, y: box.y, w: box.w, h: h1 }, S, th, F, pal, false, true);
      const D = Object.assign({}, V, { series: V.series.map((s) => ({ key: s.key + ' dist', label: s.label + (cashPanel ? ' distributions' : ' dividends'), name: s.name, v: cashPanel ? s.cash : s.dist || s.v.map(() => null) })), base: null, split: false, zero: true, divPanel: true });
      const yearly = V.dview === 'year';
      ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'; ctx.font = F(600, 22); ctx.fillStyle = th.muted;
      ctx.fillText(cashPanel ? (yearly ? 'Distributions received each year — cash, not reinvested · * part of a year' : 'Distributions received — cumulative cash, not reinvested') : (yearly ? 'Dividends & interest paid each year — reinvested' : 'Dividends & interest paid — reinvested, in dollars as paid'), box.x, box.y + h1 + gap - 12 * S, box.w * (cashPanel ? 0.55 : 0.62));
      ctx.textAlign = 'right'; ctx.fillText(cashPanel ? 'solid: price + distributions · dashed: price only' : yearly ? 'in dollars as paid · * a part year' : 'cumulative, each paid on the shares then held', box.x + box.w, box.y + h1 + gap - 12 * S, box.w * (cashPanel ? 0.42 : 0.36));
      if (yearly) cashBars(ctx, V, f, { x: box.x, y: box.y + h1 + gap, w: box.w, h: h2 }, S, th, F, pal, false);
      else lineRace(ctx, D, f, { x: box.x, y: box.y + h1 + gap, w: box.w, h: h2 }, S, th, F, pal, false, false);
    }
    else if (V.panels && (style === 'line' || style === 'area')) {
      const n = V.series.length, gap = 54 * S, ph = (box.h - gap * (n - 1)) / n;
      V.series.forEach((s, i) => { const sub = Object.assign({}, V, { series: [s], zero: s.v.some((x) => x < 0) && s.v.some((x) => x > 0) }); lineRace(ctx, sub, f, { x: box.x, y: box.y + i * (ph + gap), w: box.w, h: ph }, S, th, F, (j) => pal(i + j), style === 'area', i < n - 1); });
    } else lineRace(ctx, banded ? Object.assign({}, V, { divAbove: true }) : V, f, box, S, th, F, pal, style === 'area');
    // the date, large and faint; the brand mark; the progress hairline
    const k = clamp(Math.round(f), 0, V.grid.length - 1);
    ctx.textAlign = 'right'; ctx.fillStyle = alpha(th.text === '#1d1d1b' ? '#1d1d1b' : '#ffffff', opt.theme === 'clean' ? 0.10 : 0.12);
    ctx.font = F(700, portrait ? 120 : 110);
    if (!V.yearly && style !== 'heat' && !['sankey', 'treemap', 'bubble'].includes(V.kind)) ctx.fillText(V.actual ? dayLabel(V.grid[k]) : V.quarterly ? (V.qlabel || quarterLabel)(V.grid[k]) : monthYear(V.grid[k]), W - pad, bottom - (flat ? (V.kind === 'rank' ? 70 : 10) : 24) * S);
    if (V.kind === 'treemap') { ctx.font = F(800, 64); ctx.fillStyle = th.text; ctx.textAlign = 'right'; ctx.textBaseline = 'alphabetic'; ctx.fillText(monthYear(V.grid[k]), W - pad, top - 10 * S); }
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
      const ref = V.base || (V.contrib ? valAt(V.contrib, f) : s.contrib ? valAt(s.contrib, f) : null);
      if (ref && fin(v)) { ctx.textAlign = 'right'; ctx.font = F(600, 24); ctx.fillStyle = upDown(th, v >= ref); ctx.fillText(pctf(v / ref - 1), x + cw - 18 * S, y + 40 * S); }
      const dn = reinvOn(V) ? reinvNote(V, s, f, true) : '';
      if (dn) { ctx.textAlign = 'right'; ctx.font = F(500, 20); ctx.fillStyle = th.muted; ctx.fillText(dn, x + cw - 18 * S, y + 84 * S, cw * 0.45); }
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
    if (V.goal) { lo = Math.min(lo, 0); hi = Math.max(hi, V.goal.value); }
    if (V.contrib && !V.divPanel) { for (let i = 0; i <= n && i < V.contrib.length; i++) if (fin(V.contrib[i])) { lo = Math.min(lo, V.contrib[i]); hi = Math.max(hi, V.contrib[i]); } }
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
    for (const v of ticks) { const y = Y(v); if (y < b.y - 2 || y > b.y + b.h + 2) continue; ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText(V.tickFmt ? V.tickFmt(v) : V.unit === '$' ? money(v) : V.unit === '%' ? (V.kind === 'fund' ? (100 * v).toFixed(0) + '%' : pctf(v, 0)) : plain(v), b.x - 14 * S, y); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const years = []; for (let y = new Date(G[0]).getUTCFullYear() + 1; y <= new Date(xMax).getUTCFullYear(); y++) years.push(y);
    const every = Math.max(1, Math.ceil(years.length / (b.w / (110 * S))));
    years.forEach((yr, i) => { if (i % every) return; const x = X(Date.UTC(yr, 0, 1)); if (x < b.x + 20 * S || x > b.x + b.w) return; ctx.fillStyle = th.axis; if (!noYears) ctx.fillText(String(yr), x, b.y + b.h + 12 * S); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(x, b.y); ctx.lineTo(x, b.y + b.h); ctx.stroke(); });
    if (V.base) { const y = Y(V.base); ctx.setLineDash([8 * S, 8 * S]); ctx.strokeStyle = th.axis; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.setLineDash([]); ctx.textAlign = 'right'; ctx.textBaseline = 'top'; ctx.font = F(500, 20); ctx.fillStyle = th.muted; ctx.fillText(money(V.base, 0) + ' invested', b.x + b.w - 8 * S, y + 8 * S); }
    if (V.goal) { const y = Y(V.goal.value); ctx.save(); ctx.setLineDash([12 * S, 8 * S]); ctx.strokeStyle = th.text; ctx.globalAlpha = 0.55; ctx.lineWidth = 2.5 * S; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.restore(); ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'; ctx.font = F(700, 22); ctx.fillStyle = th.text; ctx.fillText('Goal ' + money(V.goal.value, 0), b.x + 10 * S, y - 8 * S); }
    if (V.zero && !V.base && lo < 0 && hi > 0) { const y = Y(0); ctx.strokeStyle = th.axis; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); }
    if (V.contrib && !V.divPanel) {                                       // the money put in so far: a dashed staircase
      ctx.save(); ctx.setLineDash([9 * S, 7 * S]); ctx.strokeStyle = th.axis; ctx.lineWidth = 3 * S; ctx.beginPath(); let st0 = false;
      for (let i = 0; i <= Math.floor(f) && i < n; i++) if (fin(V.contrib[i])) { const x = X(G[i]), y = Y(V.contrib[i]); if (!st0) { ctx.moveTo(x, y); st0 = true; } else ctx.lineTo(x, y); }
      const cv = valAt(V.contrib, f); if (fin(cv) && st0) ctx.lineTo(X(tCur), Y(cv));
      ctx.stroke(); ctx.restore();
      if (fin(cv)) { ctx.textAlign = 'right'; ctx.textBaseline = 'top'; ctx.font = F(600, 21); ctx.fillStyle = th.muted; ctx.fillText(`${money(cv)} put in`, Math.max(b.x + 180 * S, X(tCur) - 14 * S), Y(cv) + 10 * S); }
    }
    // the lines, drawn up to this frame; the newest point between two weeks
    const heads = [];
    ctx.save(); ctx.beginPath(); ctx.rect(b.x - 4 * S, b.y - 40 * S, b.w + 8 * S, b.h + 44 * S); ctx.clip();
    V.series.forEach((s, k) => {
      const col = pal(k), pts = [];
      for (let i = 0; i <= Math.floor(f) && i < n; i++) if (fin(s.v[i])) pts.push([X(G[i]), Y(s.v[i]), i]);
      const hv = valAt(s.v, f); if (fin(hv)) pts.push([X(tCur), Y(hv), f]);
      if (pts.length < 1) return;
      if (!s.bench && (area || (k === 0 && V.series.length <= 3))) {      // a soft fill under the line
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
      ctx.strokeStyle = col; ctx.lineWidth = (s.bench ? 3.5 : 5) * S; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      if (th.glow && !s.bench) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * S; }
      if (s.bench) ctx.setLineDash([12 * S, 8 * S]);
      ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.stroke();
      ctx.shadowBlur = 0; ctx.setLineDash([]);
      const h = pts[pts.length - 1];
      heads.push({ x: h[0], y: h[1], col, s, v: hv, k });
    });
    ctx.restore();
    // heads: a dot with a halo; labels to the right, pushed apart so they never overlap
    heads.forEach((h) => { ctx.fillStyle = alpha(h.col, 0.25); ctx.beginPath(); ctx.arc(h.x, h.y, 16 * S, 0, 7); ctx.fill(); ctx.fillStyle = h.col; ctx.beginPath(); ctx.arc(h.x, h.y, 8 * S, 0, 7); ctx.fill(); });
    const rv = reinvOn(V) && V.series.length <= 4, lh = ((V.split && area) || rv ? 76 : 50) * S, sorted = heads.slice().sort((a, c) => a.y - c.y);
    sorted.forEach((h, i) => { h.ly = Math.max(h.y, i ? sorted[i - 1].ly + lh : b.y + lh / 2); });
    for (let i = sorted.length - 1; i >= 0; i--) { const lim = i === sorted.length - 1 ? b.y + b.h - lh / 2 : sorted[i + 1].ly - lh; if (sorted[i].ly > lim) sorted[i].ly = lim; }
    sorted.forEach((h) => {
      ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
      const txt = `${h.s.label}${h.s.need ? ' · ' + h.s.need : ''}  ${V.fmt(h.v)}`;
      // a second line under the label: the distributions taken as cash (areas) or reinvested, kept inside the frame too
      const sub = V.split && area && h.s.cash ? `${money(valAt(h.s.cash, f))} from distributions` : rv ? reinvNote(V, h.s, f) : '';
      ctx.font = F(500, 19); const sw = sub ? ctx.measureText(sub).width + 8 * S : 0;
      ctx.font = F(700, 26);
      const w = ctx.measureText(txt).width + 24 * S, x = Math.min(h.x + 22 * S, ctx.canvas.width - 24 * S - Math.max(w, sw));
      ctx.fillStyle = alpha(h.col, 0.92); roundRect(ctx, x, h.ly - 20 * S, w, 40 * S, 12 * S); ctx.fill();
      ctx.fillStyle = luminance(h.col) > 0.55 ? '#0b1220' : '#ffffff'; ctx.fillText(txt, x + 12 * S, h.ly + 1 * S);
      if (sub) { ctx.font = F(500, 19); ctx.fillStyle = th.muted; ctx.fillText(sub, x + 4 * S, h.ly + 32 * S); }
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
    ctx.font = F(700, 30);                                                // room for the longest label (up to a third)
    const lab = neg ? 0 : clamp(Math.max(...V.series.map((s) => ctx.measureText(String(s.label)).width)) + 30 * S, 150 * S, b.w / 3), room = b.w - lab - (neg ? 300 : V.split || V.goal || reinvOn(V) ? 270 : 140) * S;
    const share = neg ? clamp(negm / ((negm + pos) || 1), pos > 0 ? 0.18 : 0.8, pos > 0 ? 0.82 : 0.8) : 0;
    const x0 = b.x + lab + (neg ? 150 * S + room * share : 0), unit = room / Math.max(1e-9, neg ? (pos > 0 ? Math.max(negm / share, pos / (1 - share)) : negm / share) : pos), wMax = null;
    if (neg) { ctx.strokeStyle = th.axis; ctx.lineWidth = 2 * S; ctx.beginPath(); ctx.moveTo(x0, b.y); ctx.lineTo(x0, b.y + b.h); ctx.stroke(); }
    const cIn = V.contrib && !neg ? valAt(V.contrib, f) : null;
    if (fin(cIn)) {                                                       // the money put in so far, across every bar
      const xc = x0 + cIn * unit; ctx.save(); ctx.setLineDash([8 * S, 7 * S]); ctx.strokeStyle = th.axis; ctx.lineWidth = 2.5 * S; ctx.beginPath(); ctx.moveTo(xc, b.y - 8 * S); ctx.lineTo(xc, b.y + b.h); ctx.stroke(); ctx.restore();
      ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.font = F(600, 21); ctx.fillStyle = th.muted; ctx.fillText(`${money(cIn)} put in`, xc, b.y - 12 * S);
    }
    V.series.forEach((s, k) => {
      const r = lerp(r0.get(k), r1.get(k), easeIO(fr)), y = b.y + r * slot + (slot - bh) / 2, v = vals[k];
      if (!fin(v)) return;
      const w = Math.abs(v) * unit, x = v >= 0 ? x0 : x0 - w, col = pal(k);
      const gr = ctx.createLinearGradient(x, 0, x + w, 0); gr.addColorStop(0, alpha(col, s.bench ? 0.18 : 0.75)); gr.addColorStop(1, alpha(col, s.bench ? 0.32 : 1));
      ctx.fillStyle = gr; if (th.glow && !s.bench) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * 0.8 * S; }
      roundRect(ctx, x, y, Math.max(w, 6 * S), bh, Math.min(14 * S, bh / 3)); ctx.fill(); ctx.shadowBlur = 0;
      if (s.bench) { ctx.save(); ctx.setLineDash([8 * S, 6 * S]); ctx.strokeStyle = col; ctx.lineWidth = 2.5 * S; ctx.stroke(); ctx.restore(); }
      const cash = V.split && s.cash ? valAt(s.cash, f) : null;
      if (fin(cash) && cash > 0 && v > 0) {                   // the distributions: their own segment at the end of the bar
        const cw = Math.min(w, cash * unit);
        ctx.save(); roundRect(ctx, x, y, Math.max(w, 6 * S), bh, Math.min(14 * S, bh / 3)); ctx.clip();
        ctx.fillStyle = 'rgba(255,255,255,0.34)'; ctx.fillRect(x + w - cw, y, cw, bh);
        ctx.strokeStyle = 'rgba(255,255,255,0.65)'; ctx.lineWidth = 2 * S; ctx.setLineDash([6 * S, 5 * S]); ctx.beginPath(); ctx.moveTo(x + w - cw, y); ctx.lineTo(x + w - cw, y + bh); ctx.stroke(); ctx.setLineDash([]);
        ctx.restore();
      }
      ctx.textBaseline = 'middle'; ctx.font = F(700, 30); ctx.fillStyle = th.text;
      if (neg) { ctx.textAlign = v >= 0 ? 'right' : 'left'; ctx.fillText(s.label, v >= 0 ? x0 - 14 * S : x0 + 14 * S, y + bh / 2); }
      else { ctx.textAlign = 'right'; ctx.fillText(s.label, b.x + lab - 18 * S, y + bh / 2); }
      const dn = !(fin(cash) && cash > 0) && v > 0 && reinvOn(V) ? reinvNote(V, s, f) : '';
      ctx.textAlign = v >= 0 ? 'left' : 'right'; ctx.font = F(700, 28); ctx.fillStyle = th.text;
      ctx.fillText(V.fmt(v), v >= 0 ? x + w + 14 * S : x - 14 * S, y + bh / 2 - ((fin(cash) && cash > 0) || dn ? 12 * S : 0));
      if (fin(cash) && cash > 0) { ctx.font = F(500, 20); ctx.fillStyle = th.muted; ctx.fillText(`incl. ${money(cash)} distributions`, x + w + 14 * S, y + bh / 2 + 18 * S); }
      else if (dn) { ctx.font = F(500, 20); ctx.fillStyle = th.muted; ctx.fillText(dn, x + w + 14 * S, y + bh / 2 + 18 * S); }
      else if (s.need && v >= 0) { ctx.font = F(600, 20); ctx.fillStyle = th.muted; ctx.fillText(s.need, x + w + 14 * S, y + bh / 2 + 24 * S); }
      if (s.name && s.name !== s.label && bh > 54 * S && w > 260 * S && (ctx.font = F(500, 20), ctx.measureText(String(s.name).slice(0, 34)).width < w - 28 * S)) { ctx.textAlign = 'left'; ctx.font = F(500, 20); ctx.fillStyle = s.bench ? th.muted : luminance(col) > 0.55 ? 'rgba(10,18,32,0.75)' : 'rgba(255,255,255,0.85)'; ctx.fillText(String(s.name).slice(0, 34), x + 14 * S, y + bh / 2); }
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
      const sc = V.contrib || s.contrib, v0 = sc ? valAt(sc, f) : s.v.find(fin);
      if (fin(v) && fin(v0) && v0 !== 0 && V.unit !== '%') { ctx.font = F(700, 30); ctx.fillStyle = upDown(th, v >= v0); ctx.fillText(pctf(v / v0 - 1), x + 28 * S, y + ch * 0.55 + 46 * S); }
      const extra = [sc && fin(v0) ? `on ${money(v0)} put in` + (s.need ? ' · ' + s.need : '') : '',
        V.split && s.cash ? `incl. ${money(valAt(s.cash, f))} distributions` : reinvOn(V) ? reinvNote(V, s, f) : ''].filter(Boolean).join(' · ');
      if (extra) { ctx.font = F(600, 22); ctx.fillStyle = th.muted; ctx.fillText(extra, x + 170 * S, y + ch * 0.55 + 46 * S, cw - 198 * S); }
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
    G.forEach((g, i) => { if (i % every === 0 && n - 1 - i >= Math.ceil(every * 0.6) || i === n - 1) { ctx.fillStyle = th.axis; ctx.font = F(500, 20); ctx.fillText((V.qlabel || quarterLabel)(g), b.x + (i + 0.5) * slot, b.y + b.h + 12 * S); } });
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
  // a leaderboard: N slots, bars sliding as ranks change, coloured by sector, entering from below and leaving downwards
  function rankRace(ctx, V, f, b, S, th, F) {
    const N = V.rankN, i0 = Math.floor(f), i1 = Math.min(V.grid.length - 1, i0 + 1), e = easeIO(f - i0);
    const order = (i) => { const arr = V.series.map((s, k) => ({ k, v: s.v[i] })).filter((x) => fin(x.v)); arr.sort((a, c) => (V.order === 'abs' ? Math.abs(c.v) - Math.abs(a.v) : V.order === 'asc' ? a.v - c.v : c.v - a.v)); return new Map(arr.map((x, r) => [x.k, r])); };
    const r0 = order(i0), r1 = order(i1);
    const top = (m, i) => { let mx = 0; for (const [k, r] of m) if (r < N) mx = Math.max(mx, Math.abs(V.series[k].v[i])); return mx || 1; };
    const vmax = lerp(top(r0, i0), top(r1, i1), e);
    const legendH = 50 * S, footH = V.foot ? 30 * S : 0, area = b.h - legendH - footH, slot = area / N, bh = Math.min(slot * 0.76, 120 * S);
    const lab = 230 * S, room = Math.max(100 * S, b.w - lab - 250 * S), x0 = b.x + lab;
    const rows = [];
    V.series.forEach((s, k) => {
      const a = r0.has(k) ? r0.get(k) : N + 1.5, c = r1.has(k) ? r1.get(k) : N + 1.5, r = lerp(a, c, e);
      if (r > N + 0.6) return;
      let v = valAt(s.v, f); if (!fin(v)) v = fin(s.v[i1]) ? s.v[i1] : s.v[i0];
      if (fin(v)) rows.push({ s, k, r, v, rank: (e < 0.5 ? a : c) + 1 });
    });
    ctx.save(); ctx.beginPath(); ctx.rect(b.x - 20 * S, b.y - 6 * S, b.w + 40 * S, area + 6 * S); ctx.clip();
    rows.sort((p, q) => q.r - p.r).forEach(({ s, r, v, rank }) => {
      const y = b.y + r * slot + (slot - bh) / 2, w = Math.max(6 * S, Math.min(1.08, Math.abs(v) / vmax) * room), col = secCol(th, s.sec);
      ctx.globalAlpha = clamp(N - r + 0.15, 0, 1);
      const gr = ctx.createLinearGradient(x0, 0, x0 + w, 0); gr.addColorStop(0, alpha(col, 0.72)); gr.addColorStop(1, col);
      ctx.fillStyle = v < 0 ? alpha('#ff6b6b', 0.85) : gr; if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * 0.7 * S; }
      roundRect(ctx, x0, y, w, bh, Math.min(12 * S, bh / 3)); ctx.fill(); ctx.shadowBlur = 0;
      ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
      ctx.font = F(600, Math.min(24, bh / S * 0.42)); ctx.fillStyle = th.muted; ctx.fillText(rank > N ? '' : String(Math.round(rank)), b.x + 40 * S, y + bh / 2);
      ctx.font = F(700, Math.min(30, bh / S * 0.5)); ctx.fillStyle = th.text; ctx.fillText(s.label, x0 - 16 * S, y + bh / 2);
      const nm = String(s.name || '').replace(/\s*\/[A-Z]{2,3}\/?$/, '').replace(/,? (INC|CORP|CORPORATION|LTD|PLC|CO|HOLDINGS|GROUP)\.?$/i, '').replace(/[\s,&/]+$/, '');
      ctx.textAlign = 'left'; ctx.font = F(700, Math.min(28, bh / S * 0.46)); ctx.fillStyle = th.text;
      const vt = V.fmt(v), vw = ctx.measureText(vt).width; ctx.fillText(vt, x0 + w + 14 * S, y + bh / 2);
      if (bh > 30 * S) {
        ctx.font = F(500, Math.min(20, bh / S * 0.34));
        const tw = ctx.measureText(nm.slice(0, 30)).width;
        if (w > tw + 30 * S) { ctx.fillStyle = luminance(col) > 0.55 && v >= 0 ? 'rgba(10,18,32,0.78)' : 'rgba(255,255,255,0.88)'; ctx.fillText(nm.slice(0, 30), x0 + 14 * S, y + bh / 2); }
        else { ctx.fillStyle = th.muted; ctx.fillText(nm.slice(0, 26), x0 + w + 30 * S + vw, y + bh / 2); }
      }
    });
    ctx.restore(); ctx.globalAlpha = 1;
    // sectors on screen
    const secs = [...new Set(rows.filter((x) => x.r < N - 0.5).map((x) => x.s.sec))];
    let lx = b.x; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.font = F(600, 20);
    const ly = b.y + area + legendH / 2;
    for (const sc of secs) { const t = SECTORS[sc] || sc, w = ctx.measureText(t).width; if (lx + w + 40 * S > b.x + b.w) break; ctx.fillStyle = secCol(th, sc); ctx.beginPath(); ctx.arc(lx + 8 * S, ly, 8 * S, 0, 7); ctx.fill(); ctx.fillStyle = th.muted; ctx.fillText(t, lx + 22 * S, ly); lx += w + 46 * S; }
    if (V.foot) { ctx.font = F(400, 17); ctx.fillStyle = alpha(th.text === '#1d1d1b' ? '#1d1d1b' : '#ffffff', 0.45); ctx.fillText(V.foot, b.x, b.y + area + legendH + footH / 2); }
  }
  // monthly returns: years down, months across, each month lighting up as the video reaches it; the year's total at the right
  function heatmap(ctx, V, f, b, S, th, F) {
    const C = V.cal, ys = C.years, ny = ys.length, x00 = b.x - 70 * S, W0 = b.w + 70 * S, labW = 86 * S, headH = 40 * S;
    const cw = (W0 - labW) / 13, ch = Math.min((b.h - headH) / ny, cw * 0.82), y0 = b.y + headH, X = (m) => x00 + labW + m * cw;
    const light = th.text === '#1d1d1b', G = light ? '23,115,74' : '56,242,162', R = light ? '192,57,43' : '255,107,107';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.font = F(600, Math.min(22, cw / S * 0.3)); ctx.fillStyle = th.muted;
    MON.forEach((m, i) => ctx.fillText(m, X(i) + cw / 2, b.y + headH / 2)); ctx.fillText('Year', X(12) + cw / 2, b.y + headH / 2);
    const fs = Math.min(22, ch / S * 0.42), yr = new Map();
    C.cells.forEach(([y, m, r], k) => {
      const a = clamp(f - k + 1, 0, 1); if (a <= 0 || !fin(r)) return;
      const row = ys.indexOf(y), x = X(m) + 2 * S, yy = y0 + row * ch + 2 * S, w = cw - 4 * S, h = ch - 4 * S, int = clamp(Math.abs(r) / 0.1, 0.12, 1);
      ctx.globalAlpha = a; ctx.fillStyle = `rgba(${r >= 0 ? G : R},${0.18 + 0.72 * int})`; roundRect(ctx, x, yy, w, h, Math.min(8 * S, h / 3)); ctx.fill();
      if (k === Math.round(f)) { ctx.strokeStyle = th.accent; ctx.lineWidth = 3 * S; ctx.stroke(); }
      if (h > 16 * S) { ctx.font = F(600, fs); ctx.fillStyle = int > 0.6 && !light ? '#06101f' : th.text; ctx.fillText((r >= 0 ? '+' : '−') + Math.abs(100 * r).toFixed(Math.abs(r) >= 0.1 ? 0 : 1), x + w / 2, yy + h / 2); }
      ctx.globalAlpha = 1;
      if (a >= 0.5) yr.set(y, (yr.get(y) || 1) * (1 + r));
    });
    ys.forEach((y, row) => {
      const yy = y0 + row * ch + ch / 2;
      ctx.textAlign = 'right'; ctx.font = F(700, Math.min(24, ch / S * 0.5)); ctx.fillStyle = th.text; ctx.fillText(String(y), x00 + labW - 14 * S, yy);
      if (yr.has(y)) { const r = yr.get(y) - 1; ctx.textAlign = 'center'; ctx.font = F(800, fs); ctx.fillStyle = r >= 0 ? (light ? '#17734a' : '#3ee39a') : (light ? '#c0392b' : '#ff6b6b'); ctx.fillText(pctf(r, 0), X(12) + cw / 2, yy); }
    });
  }
  // the spread of one year's returns across companies; bars morph from year to year
  function histChart(ctx, V, f, b, S, th, F) {
    const H = V.hist, E = H.edges, nb = E.length + 1, i0 = Math.floor(f), i1 = Math.min(H.yrs.length - 1, i0 + 1), e = easeIO(f - i0), A = H.yrs[i0], B = H.yrs[i1];
    if (!H._max) H._max = Math.max(...H.yrs.flatMap((x) => x.shares)) * 1.12;
    const light = th.text === '#1d1d1b', top = b.y + 70 * S, h = b.h - 70 * S - 54 * S, bw = b.w / nb, Y = (v) => top + h - v / H._max * h;
    const xOf = (r) => { if (r < E[0]) return b.x + bw / 2; if (r >= E[E.length - 1]) return b.x + (nb - 0.5) * bw; let k = 0; while (k < E.length - 1 && r >= E[k + 1]) k++; return b.x + (k + 1 + (r - E[k]) / (E[k + 1] - E[k])) * bw; };
    ctx.lineWidth = 1.2 * S; ctx.font = F(500, 20); ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const v of niceTicks(0, H._max, 4)) { const y = Y(v); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText((100 * v).toFixed(0) + '%', b.x - 12 * S, y); }
    for (let k = 0; k < nb; k++) {
      const v = lerp(A.shares[k], B.shares[k], e), mid = k === 0 ? -1 : k === nb - 1 ? 2 : (E[k - 1] + E[k]) / 2, col = mid < 0 ? (light ? '#c0392b' : '#ff6b8e') : (light ? '#17734a' : '#38f2a2');
      const x = b.x + k * bw + bw * 0.08, y = Y(v);
      ctx.fillStyle = alpha(col, k === 0 || k === nb - 1 ? 0.55 : 0.88); if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * 0.5 * S; }
      roundRect(ctx, x, y, bw * 0.84, Math.max(1, top + h - y), Math.min(6 * S, bw * 0.2)); ctx.fill(); ctx.shadowBlur = 0;
    }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = th.axis; ctx.font = F(500, 19);
    [[-0.8, '≤ −80%'], [-0.4, '−40%'], [0, '0'], [0.4, '+40%'], [0.8, '+80%'], [1.2, '+120%']].forEach(([r, t]) => ctx.fillText(t, r <= -0.8 ? b.x + bw / 2 : xOf(r), top + h + 10 * S));
    ctx.fillText('≥ +150%', b.x + (nb - 0.5) * bw, top + h + 10 * S);
    const mark = (r, col, label, dy) => { if (!fin(r)) return; const x = xOf(r); ctx.strokeStyle = col; ctx.lineWidth = 3 * S; ctx.setLineDash([10 * S, 7 * S]); ctx.beginPath(); ctx.moveTo(x, top - 10 * S); ctx.lineTo(x, top + h); ctx.stroke(); ctx.setLineDash([]); ctx.font = F(700, 22); ctx.textAlign = x > b.x + b.w * 0.7 ? 'right' : 'left'; ctx.textBaseline = 'bottom'; ctx.fillStyle = col; ctx.fillText(label, x + (ctx.textAlign === 'left' ? 10 : -10) * S, top - 12 * S + dy); };
    const med = lerp(A.median, B.median, e), spy = fin(A.spy) && fin(B.spy) ? lerp(A.spy, B.spy, e) : null, cur = e < 0.5 ? A : B;
    mark(med, th.text, `Median stock ${pctf(med, 0)}`, 0);
    if (fin(spy)) mark(spy, th.accent, `S&P 500 (SPY) ${pctf(spy, 0)}`, Math.abs(xOf(spy) - xOf(med)) < 260 * S ? 30 * S : 0);
    ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.font = F(800, 46); ctx.fillStyle = th.text; ctx.fillText(String(cur.y) + (cur.ytd ? ' so far' : ''), b.x, b.y);
    ctx.font = F(600, 24); ctx.fillStyle = th.muted;
    ctx.fillText(`${cur.n.toLocaleString('en-US')} companies · ${Math.round(100 * cur.up)}% rose · best ${cur.best[0]} ${pctf(cur.best[1], 0)} · worst ${cur.worst[0]} ${pctf(cur.worst[1], 0)}`, b.x + 230 * S, b.y + 14 * S);
    if (V.foot) { ctx.font = F(400, 17); ctx.fillStyle = alpha(light ? '#1d1d1b' : '#ffffff', 0.45); ctx.fillText(V.foot, b.x, top + h + 36 * S); }
  }
  // bubbles: x and y measures, area = the size measure, colour = sector; the largest labelled, a short trail behind them
  function bubbleChart(ctx, V, f, b, S, th, F) {
    const B = V.bub, tx = (v) => (B.logx ? Math.log(Math.max(v, 1e-9)) : v), ty = (v) => (B.logy ? Math.log(Math.max(v, 1e-9)) : v);
    const X = (v) => b.x + (clamp(tx(v), B.dx[0], B.dx[1]) - B.dx[0]) / (B.dx[1] - B.dx[0]) * b.w;
    const Y = (v) => b.y + b.h - (clamp(ty(v), B.dy[0], B.dy[1]) - B.dy[0]) / (B.dy[1] - B.dy[0]) * b.h;
    const ticks = (d, log) => (log ? [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].filter((v) => Math.log(v) >= d[0] && Math.log(v) <= d[1]) : niceTicks(d[0], d[1], 5));
    ctx.lineWidth = 1.2 * S; ctx.font = F(500, 21);
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const v of ticks(B.dy, B.logy)) { const y = Y(v); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText(B.fy(v), b.x - 12 * S, y); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (const v of ticks(B.dx, B.logx)) { const x = X(v); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(x, b.y); ctx.lineTo(x, b.y + b.h); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText(B.fx(v), x, b.y + b.h + 10 * S); }
    ctx.strokeStyle = th.axis; ctx.lineWidth = 2 * S;
    if (!B.logx && B.dx[0] < 0 && B.dx[1] > 0) { const x = X(0); ctx.beginPath(); ctx.moveTo(x, b.y); ctx.lineTo(x, b.y + b.h); ctx.stroke(); }
    if (!B.logy && B.dy[0] < 0 && B.dy[1] > 0) { const y = Y(0); ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); }
    const mk = clamp(Math.round(f), 0, V.grid.length - 1);            // the month, large and faint behind the bubbles
    ctx.font = F(800, 100); const mw = ctx.measureText(monthYear(V.grid[mk])).width || 1;
    ctx.font = F(800, Math.min(100 * 0.85 * b.w / mw, b.h / 2.4 / S)); ctx.fillStyle = alpha(th.text === '#1d1d1b' ? '#1d1d1b' : '#ffffff', 0.07); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(monthYear(V.grid[mk]), b.x + b.w / 2, b.y + b.h / 2);
    ctx.font = F(600, 21); ctx.fillStyle = th.muted; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
    ctx.fillText((B.lx || RANK[B.kx][0]) + ' →', b.x + b.w, b.y + b.h - 8 * S);
    ctx.save(); ctx.translate(b.x + 18 * S, b.y + 6 * S); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'right'; ctx.textBaseline = 'top'; ctx.fillText((B.ly || RANK[B.ky][0]) + ' →', 0, 0); ctx.restore();
    const rMax = Math.min(b.w, b.h) * 0.085, i0 = Math.floor(f);
    const pts = V.series.map((s) => ({ s, x: valAt(s.x, f), y: valAt(s.y, f), z: valAt(s.s, f) })).filter((p) => fin(p.x) && fin(p.y) && fin(p.z) && p.z > 0)
      .map((p) => Object.assign(p, { r: Math.max(3 * S, rMax * Math.sqrt(p.z / B.smax)) })).sort((a, c) => c.r - a.r);
    pts.slice(0, 5).forEach((p) => {                     // trails of the five largest
      for (let j = Math.max(0, i0 - 8); j < i0; j++) { const x = p.s.x[j], y = p.s.y[j]; if (!fin(x) || !fin(y)) continue; ctx.fillStyle = alpha(secCol(th, p.s.sec), 0.08 + 0.04 * (j - i0 + 9)); ctx.beginPath(); ctx.arc(X(x), Y(y), 4 * S, 0, 7); ctx.fill(); }
    });
    pts.forEach((p) => { p.cx = clamp(X(p.x), b.x + p.r, b.x + b.w - p.r); p.cy = clamp(Y(p.y), b.y + p.r, b.y + b.h - p.r); });   // beyond the axis: whole, at its edge
    ctx.save(); ctx.beginPath(); ctx.rect(b.x, b.y, b.w, b.h); ctx.clip();
    pts.forEach((p) => {
      const col = secCol(th, p.s.sec); ctx.fillStyle = alpha(col, 0.72); ctx.strokeStyle = alpha(th.text === '#1d1d1b' ? '#1d1d1b' : '#ffffff', 0.55); ctx.lineWidth = 1.5 * S;
      if (th.glow) { ctx.shadowColor = col; ctx.shadowBlur = th.glow * 0.5 * S; }
      ctx.beginPath(); ctx.arc(p.cx, p.cy, p.r, 0, 7); ctx.fill(); ctx.shadowBlur = 0; ctx.stroke();
    });
    const boxes = [];                                    // the largest labelled first; a label that would cover another is left out
    pts.slice(0, 16).forEach((p) => {
      const fs = clamp(p.r / S * 0.55, 15, 28); ctx.font = F(700, fs); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const inside = p.r > 22 * S && ctx.measureText(p.s.label).width < 1.9 * p.r, cx = clamp(p.cx, b.x + 30 * S, b.x + b.w - 30 * S), cy = p.cy + (inside ? 0 : p.cy - p.r - 24 * S < b.y ? p.r + 12 * S : -p.r - 12 * S), w = ctx.measureText(p.s.label).width / 2 + 3 * S, h = fs * S * 0.6;
      if (boxes.some(([x0, y0, x1, y1]) => cx - w < x1 && cx + w > x0 && cy - h < y1 && cy + h > y0)) return;
      boxes.push([cx - w, cy - h, cx + w, cy + h]);
      ctx.fillStyle = inside ? (luminance(secCol(th, p.s.sec)) > 0.55 ? '#0b1220' : '#ffffff') : th.text;
      ctx.fillText(p.s.label, cx, cy);
    });
    ctx.restore();
    const secs = [...new Set(pts.map((p) => p.s.sec))];
    let lx = b.x + 40 * S; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.font = F(600, 19);
    for (const sc of secs) { const t = SECTORS[sc] || sc, w = ctx.measureText(t).width; if (lx + w + 40 * S > b.x + b.w) break; ctx.fillStyle = secCol(th, sc); ctx.beginPath(); ctx.arc(lx + 7 * S, b.y + 16 * S, 7 * S, 0, 7); ctx.fill(); ctx.fillStyle = th.muted; ctx.fillText(t, lx + 20 * S, b.y + 16 * S); lx += w + 40 * S; }
  }
  // squarified treemap (Bruls, Huizing, van Wijk): values in the order given → [x, y, w, h] each
  function squarify(vals, x, y, w, h) {
    const out = vals.map(() => [x, y, 0, 0]), idx = vals.map((v, i) => i).filter((i) => vals[i] > 0), total = idx.reduce((a, i) => a + vals[i], 0);
    if (!(total > 0) || w <= 0 || h <= 0) return out;
    const sc = {}; idx.forEach((i) => { sc[i] = vals[i] / total * w * h; });
    const worst = (row, side) => { const s = row.reduce((a, i) => a + sc[i], 0), mx = Math.max(...row.map((i) => sc[i])), mn = Math.min(...row.map((i) => sc[i])); return Math.max(side * side * mx / (s * s), s * s / (side * side * mn)); };
    let k = 0, rx = x, ry = y, rw = w, rh = h;
    while (k < idx.length) {
      const side = Math.min(rw, rh); let row = [idx[k]], best = worst(row, side), j = k + 1;
      while (j < idx.length) { const cand = row.concat(idx[j]), wv = worst(cand, side); if (wv > best) break; row = cand; best = wv; j++; }
      const sum = row.reduce((a, i) => a + sc[i], 0);
      if (rw >= rh) { const cw = sum / rh; let yy = ry; row.forEach((i) => { const hh = sc[i] / cw; out[i] = [rx, yy, cw, hh]; yy += hh; }); rx += cw; rw -= cw; }
      else { const ch = sum / rw; let xx = rx; row.forEach((i) => { const ww = sc[i] / ch; out[i] = [xx, ry, ww, ch]; xx += ww; }); ry += ch; rh -= ch; }
      k = j;
    }
    return out;
  }
  function retCol(r, light) {                           // red ↔ grey ↔ green by 12-month return, ±50% at full strength
    if (!fin(r)) return light ? '#c8c6c0' : '#3a4250';
    const k = clamp(r / 0.5, -1, 1), a = Math.abs(k);
    const base = light ? [200, 198, 192] : [58, 66, 80], to = k >= 0 ? (light ? [23, 140, 80] : [32, 190, 110]) : (light ? [200, 60, 50] : [225, 70, 80]);
    return `rgb(${base.map((c, i) => Math.round(c + (to[i] - c) * (0.25 + 0.75 * a))).join(',')})`;
  }
  function treemapChart(ctx, V, f, b, S, th, F) {
    const T = V.tm, light = th.text === '#1d1d1b', gap = 3 * S;
    const W = b.w + 70 * S, x0 = b.x - 70 * S, cur = V.series.map((s) => ({ s, v: Math.max(0, valAt(s.v, f) || 0), r: valAt(s.r, f) }));
    const bySec = T.secOrder.map((sc) => { const items = cur.filter((c) => c.s.sec === sc && c.v > 0).sort((a, c) => c.s.avg - a.s.avg); return { sc, items, tot: items.reduce((a, c) => a + c.v, 0) }; }).filter((g) => g.tot > 0);
    const rects = squarify(bySec.map((g) => g.tot), x0, b.y, W, b.h - 30 * S);
    bySec.forEach((g, gi) => {
      const [sx, sy, sw, sh] = rects[gi]; if (sw < 2 || sh < 2) return;
      const head = sh > 90 * S && sw > 120 * S ? 26 * S : 0;
      const inner = squarify(g.items.map((c) => c.v), sx + gap, sy + head + gap, sw - 2 * gap, sh - head - 2 * gap);
      ctx.fillStyle = alpha(secCol(th, g.sc), light ? 0.25 : 0.35); ctx.fillRect(sx, sy, sw, sh);
      if (head) {
        ctx.font = F(700, 18); ctx.fillStyle = th.text; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
        let t = (SECTORS[g.sc] || g.sc).toUpperCase() + '  ' + money(g.tot);
        if (ctx.measureText(t).width > sw - 16 * S) t = (SECTORS[g.sc] || g.sc).toUpperCase();
        while (t.length > 3 && ctx.measureText(t).width > sw - 16 * S) t = t.slice(0, -2) + '…';
        ctx.fillText(t, sx + 8 * S, sy + head / 2 + 2 * S);
      }
      g.items.forEach((c, ci) => {
        const [x, y, w, h] = inner[ci]; if (w < 1.5 || h < 1.5) return;
        ctx.fillStyle = T.color === 'ret' ? retCol(c.r, light) : secCol(th, c.s.sec);
        ctx.fillRect(x + 1, y + 1, w - 2, h - 2);
        const fs = clamp(Math.min(w / (c.s.label.length * 0.62), h * 0.42) / S, 0, 44);
        if (fs >= 11) {
          ctx.fillStyle = T.color === 'ret' || luminance(secCol(th, c.s.sec)) < 0.55 ? '#ffffff' : '#0b1220'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.font = F(800, fs); ctx.fillText(c.s.label, x + w / 2, y + h / 2 - (h > fs * S * 2.6 ? fs * S * 0.45 : 0));
          if (h > fs * S * 2.6) { ctx.font = F(600, fs * 0.5); ctx.fillText(money(c.v) + (T.color === 'ret' && fin(c.r) ? '  ' + pctf(c.r, 0) : ''), x + w / 2, y + h / 2 + fs * S * 0.55); }
        }
      });
    });
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.font = F(500, 18); ctx.fillStyle = th.muted;
    const tot = cur.reduce((a, c) => a + c.v, 0);
    ctx.fillText(`Together ${money(tot)}` + (T.color === 'ret' ? ' · colour: 12-month total return, red −50% … green +50%' : '') + (V.foot ? ' · ' + V.foot : ''), x0, b.y + b.h - 10 * S);
  }
  // sector weights: stacked areas drawn up to the frame, each band labelled at its right end
  function stackChart(ctx, V, f, b, S, th, F) {
    const G = V.grid, n = G.length, share = V.stack.share, i0 = Math.floor(f), tCur = lerp(G[i0], G[Math.min(n - 1, i0 + 1)], f - i0);
    const X = (t) => b.x + (t - G[0]) / ((G[n - 1] - G[0]) || 1) * b.w;
    const hiAbs = share ? 1 : Math.max(...V.stack.total.slice(0, Math.min(n, i0 + 2)).filter(fin)) * 1.08 || 1;
    const Y = (v) => b.y + b.h - v / hiAbs * b.h;
    ctx.lineWidth = 1.2 * S; ctx.font = F(500, 21); ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const v of share ? [0, 0.25, 0.5, 0.75, 1] : niceTicks(0, hiAbs, 5)) { const y = Y(v); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(b.x, y); ctx.lineTo(b.x + b.w, y); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText(share ? (100 * v).toFixed(0) + '%' : money(v), b.x - 12 * S, y); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let y = new Date(G[0]).getUTCFullYear() + 1; y <= new Date(G[n - 1]).getUTCFullYear(); y += Math.max(1, Math.ceil((new Date(G[n - 1]).getUTCFullYear() - new Date(G[0]).getUTCFullYear()) / 9))) { const x = X(Date.UTC(y, 0, 1)); ctx.fillStyle = th.axis; ctx.fillText(String(y), x, b.y + b.h + 10 * S); }
    const base = G.map(() => 0), heads = [];
    V.series.forEach((s, band) => {
      const top = s.v.map((v, i) => base[i] + (fin(v) ? v : 0)), col = V.actual && V.group === 'companies' && s.key !== 'other' ? th.pal[band % th.pal.length] : secCol(th, s.sec);
      ctx.beginPath();
      for (let i = 0; i <= i0 && i < n; i++) (i ? ctx.lineTo(X(G[i]), Y(top[i])) : ctx.moveTo(X(G[i]), Y(top[i])));
      const tv = valAt(top, f), bv = valAt(base, f); ctx.lineTo(X(tCur), Y(tv)); ctx.lineTo(X(tCur), Y(bv));
      for (let i = Math.min(i0, n - 1); i >= 0; i--) ctx.lineTo(X(G[i]), Y(base[i]));
      ctx.closePath(); ctx.fillStyle = alpha(col, 0.86); ctx.fill();
      heads.push({ s, col, y: Y((tv + bv) / 2), v: valAt(s.v, f) });
      for (let i = 0; i < n; i++) base[i] = top[i];
    });
    ctx.strokeStyle = th.text; ctx.globalAlpha = 0.5; ctx.lineWidth = 2 * S; ctx.beginPath(); ctx.moveTo(X(tCur), b.y); ctx.lineTo(X(tCur), b.y + b.h); ctx.stroke(); ctx.globalAlpha = 1;
    const lh = 30 * S, sorted = heads.filter((h) => fin(h.v) && h.v > (share ? 0.004 : 0)).sort((a, c) => a.y - c.y);
    sorted.forEach((h, i) => { h.ly = Math.max(h.y, i ? sorted[i - 1].ly + lh : b.y + lh / 2); });
    for (let i = sorted.length - 1; i >= 0; i--) { const lim = i === sorted.length - 1 ? b.y + b.h - lh / 2 : sorted[i + 1].ly - lh; if (sorted[i].ly > lim) sorted[i].ly = lim; }
    const lx = Math.min(X(tCur) + 16 * S, b.x + b.w + 14 * S);
    sorted.forEach((h) => { ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.font = F(700, 21); ctx.fillStyle = h.col; ctx.fillText(`${h.s.label}  ${V.fmt(h.v)}`, lx, h.ly); });
  }
  // the earnings flow: the site's Sankey (its colours: grey revenue, green profit, red costs, slate non-cash) laid out
  // the same way every quarter on one scale, so it grows and shrinks; nodes and bands move from quarter to quarter
  const SK_COL = { rev: ['#7a7974', '#d9d8d3'], profit: ['#17734a', '#a8d1b9'], cost: ['#ea6a52', '#f6c3b8'], noncash: ['#5b7fa6', '#cdd8e6'] };
  // a narrow picture (portrait, square) keeps the income statement, revenue to net earnings: no segments, no cash
  const SK_CASH = new Set(['da', 'sbc', 'wc_out', 'wc_in', 'ocf', 'fcf', 'fcf_neg', 'capex', 'bridge', 'loss_abs']);
  function sankeyNarrow(SK) {
    if (SK._nar) return SK._nar;
    const frames = SK.frames.map((f) => {
      const r = f.nodes.find((n) => n.id === 'revenue'), c0 = r ? r.col : 0, cc = f.nodes.filter((n) => SK_CASH.has(n.id)).map((n) => n.col), cut = cc.length ? Math.min(...cc) : Infinity;
      const nodes = f.nodes.filter((n) => n.col >= c0 && n.col < cut).map((n) => Object.assign({}, n, { col: n.col - c0 })), ids = new Set(nodes.map((n) => n.id));
      return Object.assign({}, f, { nodes, links: f.links.filter((l) => ids.has(l.s) && ids.has(l.t)) });
    });
    SK._nar = { frames, max: Math.max(...frames.flatMap((f) => f.nodes.map((n) => Math.abs(n.v || 0))), 1), _lay: {} };
    return SK._nar;
  }
  function sankeyLayout(V, k, b, S, SK) {
    SK = SK || V.sk; SK._lay = SK._lay || {};
    const key = k + '|' + Math.round(b.w) + '|' + Math.round(b.h); if (SK._lay[key]) return SK._lay[key];
    const fr = SK.frames[k], nodes = fr.nodes.map((n, i) => ({ ...n, i, ins: [], outs: [] })), by = new Map(nodes.map((n) => [n.id, n]));
    const links = fr.links.filter((l) => by.has(l.s) && by.has(l.t) && l.v > 0).map((l) => ({ ...l, S: by.get(l.s), T: by.get(l.t) }));
    links.forEach((l) => { l.S.outs.push(l); l.T.ins.push(l); });
    const maxCol = Math.max(...SK.frames.flatMap((q) => q.nodes.map((n) => n.col)), 1), nw = 16 * S, lab = 250 * S;
    const K = (b.h * 0.6) / SK.max, gap = 22 * S;
    nodes.forEach((n) => { n.h = Math.max(2 * S, Math.abs(n.v || 0) * K); n.x = b.x + n.col / maxCol * (b.w - nw - lab); });
    for (let c = 0; c <= maxCol; c++) {
      const col = nodes.filter((n) => n.col === c); if (!col.length) continue;
      const H = col.reduce((a, n) => a + n.h, 0) + gap * (col.length - 1); let y = b.y + (b.h - H) / 2;
      col.forEach((n) => { n.y = y; y += n.h + gap; });
    }
    nodes.forEach((n) => { let o = 0; n.outs.sort((a, c) => a.T.y - c.T.y).forEach((l) => { l.y0 = n.y + o; o += l.v * K; }); let p = 0; n.ins.sort((a, c) => a.S.y - c.S.y).forEach((l) => { l.y1 = n.y + p; p += l.v * K; }); });
    const out = { nodes: new Map(nodes.map((n) => [n.id, n])), links: new Map(links.map((l) => [l.s + '>' + l.t, l])), K, nw };
    SK._lay[key] = out;
    return out;
  }
  function sankeyChart(ctx, V, f, b, S, th, F) {
    const SK = b.w / S < 1500 ? sankeyNarrow(V.sk) : V.sk, n = SK.frames.length, k0 = Math.floor(f), k1 = Math.min(n - 1, k0 + 1), e = easeIO(f - k0), light = th.text === '#1d1d1b';
    const A = sankeyLayout(V, k0, b, S, SK), B = sankeyLayout(V, k1, b, S, SK), nw = A.nw;
    const ids = new Set([...A.links.keys(), ...B.links.keys()]);
    for (const id of ids) {                               // bands first, under the nodes
      const a = A.links.get(id), c = B.links.get(id), any = a || c;
      const S0 = (m, l, side) => (l ? l : null);
      const pos = (L, l) => (l ? { x0: l.S.x + nw, x1: l.T.x, y0: l.y0, y1: l.y1, t: l.v * L.K } : null);
      let pa = pos(A, a), pb = pos(B, c);
      if (!pa) pa = Object.assign({}, pb, { t: 0 }); if (!pb) pb = Object.assign({}, pa, { t: 0 });
      const x0 = lerp(pa.x0, pb.x0, e), x1 = lerp(pa.x1, pb.x1, e), y0 = lerp(pa.y0, pb.y0, e), y1 = lerp(pa.y1, pb.y1, e), t = lerp(pa.t, pb.t, e);
      if (t < 0.5) continue;
      const col = (SK_COL[any.color] || SK_COL.rev)[1], xm = (x0 + x1) / 2;
      ctx.fillStyle = light ? col : alpha(col, 0.45);
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.bezierCurveTo(xm, y0, xm, y1, x1, y1); ctx.lineTo(x1, y1 + t); ctx.bezierCurveTo(xm, y1 + t, xm, y0 + t, x0, y0 + t); ctx.closePath(); ctx.fill();
    }
    const nid = new Set([...A.nodes.keys(), ...B.nodes.keys()]), show = e < 0.5 ? A : B, frame = SK.frames[e < 0.5 ? k0 : k1];
    const rev = (frame.head && frame.head.revenue) || (show.nodes.get('revenue') || {}).v;
    const maxCol = Math.max(...SK.frames.flatMap((q) => q.nodes.map((n) => n.col)), 1), colGap = (b.w - nw - 250 * S) / maxCol, cand = [];
    for (const id of nid) {
      const a = A.nodes.get(id), c = B.nodes.get(id), any = a || c;
      const pa = a || Object.assign({}, c, { h: 0 }), pb = c || Object.assign({}, a, { h: 0 });
      const x = lerp(pa.x, pb.x, e), y = lerp(pa.y, pb.y, e), h = lerp(pa.h, pb.h, e);
      if (h < 0.5) continue;
      ctx.fillStyle = (SK_COL[any.color] || SK_COL.rev)[0]; ctx.fillRect(x, y, nw, h);
      const nn = show.nodes.get(id); if (nn && h >= 6 * S) cand.push({ nn, x, y, h });
    }
    // labels right of each node, fitted to the room before the next column, the biggest first, none on top of another
    const fit = (text, w, size, room, min) => { let sz = size; ctx.font = F(w, sz); while (sz > min && ctx.measureText(text).width > room) { sz -= 1; ctx.font = F(w, sz); } if (ctx.measureText(text).width <= room) return text; let t = text; while (t.length > 4 && ctx.measureText(t + '…').width > room) t = t.slice(0, -1); return t + '…'; };
    const placed = {};
    cand.sort((p, q) => q.h - p.h).forEach(({ nn, x, y, h }) => {
      const lines = nn.lines || [], valLine = (lines.find((l) => l[0] === 'val') || [])[1], mut = (lines.find((l) => l[0] === 'mut') || [])[1];
      const name = unent((lines.find((l) => l[0] === 'name' || l[0] === 'big') || [])[1] || nn.name);
      const room = (nn.col >= maxCol ? 250 * S : colGap) - nw - 18 * S, roomy = room > 190 * S;
      let val = valLine ? unent(valLine) : money(nn.v) + (rev && nn.id !== 'revenue' ? ' · ' + (100 * Math.abs(nn.v) / rev).toFixed(0) + '% of revenue' : '');
      if (!roomy) val = val.split(' · ')[0];
      const big = h > 60 * S && roomy, rows = big && mut ? 3 : 2, lh = (big ? 23 : 18) * S, top = y + h / 2 - rows * lh / 2 - 4 * S, bot = top + rows * lh + 8 * S;
      const P = placed[nn.col] || (placed[nn.col] = []);
      if (P.some(([a, c]) => top < c && bot > a)) return;
      P.push([top, bot]);
      const lx = x + nw + 10 * S; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.fillStyle = th.text; ctx.fillText(fit(name, 700, big ? 23 : 18, room, 12), lx, top + lh / 2 + 4 * S);
      ctx.fillStyle = th.muted; ctx.fillText(fit(val, 500, big ? 19 : 15, room, 11), lx, top + 1.5 * lh + 4 * S);
      if (rows === 3) ctx.fillText(fit(unent(mut), 500, 17, room, 11), lx, top + 2.5 * lh + 4 * S);
    });
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.font = F(800, 40); ctx.fillStyle = th.text; ctx.fillText(frame.label, b.x, b.y + 30 * S);
    const hd = frame.head || {};
    ctx.font = F(600, 22); ctx.fillStyle = th.muted;
    ctx.fillText([hd.revenue != null ? 'Revenue ' + money(hd.revenue) + (fin(hd.yoy) ? ` (${hd.yoy >= 0 ? '+' : '−'}${Math.abs(hd.yoy).toFixed(0)}% Y/Y)` : '') : '', hd.ni != null ? 'net earnings ' + money(hd.ni) : ''].filter(Boolean).join(' · '), b.x, b.y + 62 * S);
  }
  const unent = (s) => String(s).replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  // the dividend snowball: shares owned (and those bought with your own money, dashed) above, each year's dividends below
  function snowballChart(ctx, V, f, b, S, th, F, pal) {
    const gap = 70 * S, h1 = (b.h - gap) * 0.6, h2 = b.h - gap - h1;
    const D = Object.assign({}, V, { series: V.series.map(s =>
      ({ key:s.key, label:s.label + ' shares', name:s.name, v:s.sh })),
      base:null, contrib:null, split:false, zero:false,
      fmt:v=>fin(v)?Number(v).toLocaleString('en-US',{maximumFractionDigits:1}):'—', unit:'',
      tickFmt:v=>Number(v).toLocaleString('en-US',{maximumFractionDigits:Math.abs(v)>=10?0:1}) });
    lineRace(ctx, D, f, {x:b.x,y:b.y,w:b.w,h:h1}, S, th, F, pal, false, true);
    const monthly = V.scf !== 'annual';
    ctx.textAlign='left';ctx.textBaseline='bottom';ctx.font=F(600,22);ctx.fillStyle=th.muted;
    ctx.fillText(monthly?'Dividends received each month (reinvested) · last 24 months · dashed: last 12 months ÷ 12':
      'Dividends received each year (reinvested)',b.x,b.y+h1+gap-12*S,b.w);
    cashBars(ctx, V, f, {x:b.x,y:b.y+h1+gap,w:b.w,h:h2}, S, th, F, pal, monthly);
  }
  // dividends paid as bars, month by month (the last 24 months) or year by year, up to this frame, in dollars as paid.
  // Months carry the last twelve months ÷ 12 as a dashed line (a quarterly payer leaves two months in three empty); a
  // year the window does not hold whole (the first, or the one still running) is drawn lighter
  function cashBars(ctx, V, f, yb, S, th, F, pal, monthly) {
    const G = V.grid, upto = clamp(Math.floor(f), 0, G.length - 1);
    const key = (ms) => { const d = new Date(ms); return monthly ? d.toISOString().slice(0, 7) : String(d.getUTCFullYear()); };
    const keys = [...new Set(G.slice(0, upto + 1).map(key))];
    const periods = monthly ? keys.slice(-24) : keys, whole = fullYears(G.slice(0, upto + 1));
    const totals = V.series.map((s) => { const m = new Map(); for (let i = 0; i <= upto; i++) { const v = s.paid && s.paid[i]; if (v) m.set(key(G[i]), (m.get(key(G[i])) || 0) + v); } return m; });
    const rates = monthly ? V.series.map((s) => {                 // the trailing 52 weeks ÷ 12 at the end of each month
      const out = new Map(), i0 = (s.v || []).findIndex(fin); let run = 0;
      for (let i = 0; i <= upto; i++) { run += (s.paid && s.paid[i]) || 0; if (i >= 52) run -= (s.paid && s.paid[i - 52]) || 0; if (i0 >= 0 && i - i0 >= 51) out.set(key(G[i]), run / 12); }
      return out;
    }) : null;
    const m = V.series.length, slot = yb.w / Math.max(1, periods.length), bw = slot * 0.8 / Math.max(1, m);
    const hi = Math.max(1, ...totals.flatMap((t) => periods.map((p) => t.get(p) || 0)), ...(rates || []).flatMap((r) => periods.map((p) => r.get(p) || 0))) * 1.16;
    const Y = (v) => yb.y + yb.h - Math.min(v / hi, 1) * yb.h;
    ctx.lineWidth = 1.2 * S; ctx.font = F(500, 18); ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const t of niceTicks(0, hi / 1.16, 3)) { if (t <= 0) continue; const y = Y(t); ctx.strokeStyle = th.grid; ctx.beginPath(); ctx.moveTo(yb.x, y); ctx.lineTo(yb.x + yb.w, y); ctx.stroke(); ctx.fillStyle = th.axis; ctx.fillText(money(t), yb.x - 14 * S, y); }
    const every = Math.max(1, Math.ceil(periods.length / (monthly ? 8 : 12)));
    periods.forEach((p, j) => {
      const part = !monthly && !whole(+p);
      V.series.forEach((s, k) => {
        const v = totals[k].get(p) || 0; if (v <= 0) return;
        const x = yb.x + j * slot + slot * 0.1 + k * bw, w = Math.max(1 * S, bw * 0.88), r = Math.min(5 * S, bw * 0.23);
        ctx.fillStyle = alpha(pal(k), part ? 0.4 : 0.85); roundRect(ctx, x, Y(v), w, yb.y + yb.h - Y(v), r); ctx.fill();
        if (part) { ctx.save(); ctx.setLineDash([5 * S, 4 * S]); ctx.strokeStyle = alpha(pal(k), 0.9); ctx.lineWidth = 1.5 * S; roundRect(ctx, x, Y(v), w, yb.y + yb.h - Y(v), r); ctx.stroke(); ctx.restore(); }
        if ((j === periods.length - 1 || (!monthly && periods.length <= 14)) && bw > 22 * S) { ctx.font = F(700, bw > 44 * S ? 15 : 13); ctx.fillStyle = th.text; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillText(money(v, v >= 10 ? 0 : 2), x + w / 2, Y(v) - 4 * S, bw * (m > 1 ? 1 : 1.6)); }
      });
      if (j % every === 0 || j === periods.length - 1) {
        const d = monthly ? new Date(p + '-01T00:00:00Z') : null;
        ctx.font = F(500, 16); ctx.fillStyle = th.axis; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        ctx.fillText(monthly ? `${MON[d.getUTCMonth()]} '${String(d.getUTCFullYear()).slice(2)}` : p + (part ? '*' : ''), yb.x + j * slot + slot / 2, yb.y + yb.h + 5 * S, slot * every);
      }
    });
    if (rates) V.series.forEach((s, k) => {                          // the monthly rate, dashed, with its value at the end
      const pts = periods.map((p, j) => [yb.x + j * slot + slot / 2, rates[k].get(p)]).filter((q) => fin(q[1]));
      if (pts.length < 2) return;
      ctx.save(); ctx.setLineDash([9 * S, 6 * S]); ctx.strokeStyle = pal(k); ctx.lineWidth = 3 * S; ctx.beginPath();
      pts.forEach(([x, v], i) => (i ? ctx.lineTo(x, Y(v)) : ctx.moveTo(x, Y(v)))); ctx.stroke(); ctx.restore();
      const [lx, lv] = pts[pts.length - 1], txt = `${money(lv)}/mo`, rx = Math.min(lx + slot * 0.45, yb.x + yb.w), ty = Y(lv) - 8 * S - k * 26 * S;
      ctx.font = F(700, 17); const tw = ctx.measureText(txt).width;
      ctx.fillStyle = th.panel; roundRect(ctx, rx - tw - 10 * S, ty - 21 * S, tw + 12 * S, 24 * S, 6 * S); ctx.fill();
      ctx.fillStyle = pal(k); ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'; ctx.fillText(txt, rx - 4 * S, ty);
    });
  }

  // Avoid overlapping value/change columns on small canvases and long descriptions.
  // The dedicated snowball card keeps all three requested metrics visible.
  function endCard(ctx, V, W, H, S, th, F, pal, a, portrait) {
    const snow = V.kind === 'snowball' && Array.isArray(V.snowballSummary) && V.snowballSummary.length;
    const rows = snow ? V.snowballSummary : V.final.slice(0, portrait ? 10 : V.kind === 'rank' ? 8 : 6);
    const pad = 34 * S, capW = (portrait ? 920 : 1100) * S;
    const w = Math.min(W - 64 * S, capW);
    const availableH = H - 72 * S, headerH = snow ? 164 * S : 145 * S;
    const subOf = (r) => (r.sub && !(r.subTr && V.dinc === 'off') ? r.sub : ''), hasSub = !snow && rows.some(subOf);
    const rh = Math.max(38 * S, Math.min(snow ? 126 * S : hasSub ? 98 * S : 78 * S,
      (availableH - headerH - 32 * S) / Math.max(1, rows.length)));
    const two = hasSub && rh >= 72 * S;
    const h = Math.min(availableH, headerH + rows.length * rh + 24 * S);
    const x = (W - w) / 2, y = (H - h) / 2 + (1 - a) * 36 * S;
    ctx.fillStyle = 'rgba(0,0,0,' + (0.45 * a) + ')'; ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.globalAlpha = a;
    ctx.fillStyle = th.panel; roundRect(ctx, x, y, w, h, 24 * S); ctx.fill();
    ctx.strokeStyle = alpha(th.accent, 0.6); ctx.lineWidth = 2 * S; ctx.stroke();
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.fillStyle = th.accent; ctx.font = F(700, 32);
    ctx.fillText(String(V.endTitle || ''), x + pad, y + 52 * S, w - 2 * pad);
    ctx.font = F(500, snow ? 18 : 21); ctx.fillStyle = th.muted;
    ctx.fillText(String(V.endSub || ''), x + pad, y + 84 * S, w - 2 * pad);
    if (snow) {
      const cw = (w - 2 * pad) / 3, base = y + 137 * S;
      ['INITIAL SHARES', 'MONTHLY CASH FLOW', 'FINAL SHARES'].forEach((label, j) => {
        ctx.font = F(600, 16); ctx.fillStyle = th.muted; ctx.textAlign = 'left';
        ctx.fillText(label, x + pad + j * cw, base, cw - 9 * S);
      });
      rows.forEach((r, i) => {
        const yy = y + headerH + i * rh;
        if (i) { ctx.strokeStyle = alpha(th.muted, .2); ctx.beginPath(); ctx.moveTo(x + pad, yy); ctx.lineTo(x + w - pad, yy); ctx.stroke(); }
        ctx.font = F(700, 23); ctx.fillStyle = pal(r.k); ctx.textAlign = 'left';
        ctx.fillText(r.ticker, x + pad, yy + 25 * S, cw - 9 * S);
        ctx.font = F(500, 16); ctx.fillStyle = th.muted;
        ctx.fillText(r.investment, x + pad + cw, yy + 25 * S, 2 * cw - 12 * S);
        [r.initial, r.monthly, r.final].forEach((v, j) => {
          ctx.font = F(700, 26); ctx.fillStyle = th.text;
          ctx.fillText(v, x + pad + j * cw, yy + 69 * S, cw - 9 * S);
        });
        ctx.font = F(500, 16); ctx.fillStyle = th.muted;
        ctx.fillText(r.monthlyNote, x + pad + cw, yy + 92 * S, cw - 9 * S);
      });
    } else {
      const usable = w - 2 * pad;
      rows.forEach((r, i) => {
        const yy = y + headerH + i * rh + rh * (two ? .46 : .60);
        const change = String(r.change || '');
        const changeW = change ? Math.min(usable * .25, 186 * S) : 0;
        const valueW = Math.min(usable * .30, 235 * S);
        const labelW = Math.max(70 * S, usable - valueW - changeW - 22 * S);
        const right = x + w - pad;
        ctx.fillStyle = r.sec ? secCol(th, r.sec) : pal(r.k || 0);
        ctx.beginPath(); ctx.arc(x + pad + 8 * S, yy - 8 * S, 7 * S, 0, Math.PI * 2); ctx.fill();
        ctx.font = F(700, 27); ctx.fillStyle = th.text; ctx.textAlign = 'left';
        ctx.fillText(String(r.label || ''), x + pad + 22 * S, yy, labelW - 18 * S);
        ctx.textAlign = 'right';
        ctx.fillText(String(r.value || ''), right - changeW - (changeW ? 10 * S : 0), yy, valueW);
        if (change) {
          ctx.font = F(650, 24); ctx.fillStyle = upDown(th, r.up);
          ctx.fillText(change, right, yy, changeW);
        }
        const sub = two ? subOf(r) : '';
        if (sub) { ctx.font = F(500, 19); ctx.fillStyle = th.muted; ctx.textAlign = 'left'; ctx.fillText(sub, x + pad + 22 * S, yy + 31 * S, usable - 22 * S); }
      });
    }
    ctx.restore();
  }

  // the end card's rows and headline, from the last week
  function finish(V, st) {
    const L = V.grid.length - 1, G = V.grid, span = `${dayLabel(G[0])} → ${dayLabel(G[L])}`;
    if (V.kind === 'rank') {
      const ord = V.series.map((s, k) => ({ k, v: s.v[L] })).filter((x) => fin(x.v)).sort((a, c) => (V.order === 'abs' ? Math.abs(c.v) - Math.abs(a.v) : V.order === 'asc' ? a.v - c.v : c.v - a.v)).slice(0, V.rankN);
      V.final = ord.map((x, i) => ({ k: x.k, label: `${i + 1}. ${V.series[x.k].label}`, value: V.fmt(x.v), change: '', v: x.v, sec: V.series[x.k].sec }));
      V.endTitle = V.actual ? `${V.metric} · ${dayLabel(G[L])}` : `${V.metric} · ${V.quarterly ? quarterLabel(G[L]) : monthYear(G[L])}`;
      V.endSub = V.title;
      V.caption = `${V.title} (${V.actual ? dayLabel(G[L]) : V.quarterly ? quarterLabel(G[L]) : monthYear(G[L])}): ` + V.final.map((r) => `${r.label} ${r.value}`).join(' · ');
      return;
    }
    if (V.kind === 'bubble') {
      const B = V.bub, rows = V.series.map((s, k) => ({ k, s, x: s.x[L], y: s.y[L], z: s.s[L] })).filter((r) => fin(r.z)).sort((a, c) => c.z - a.z).slice(0, 8);
      V.final = rows.map((r) => ({ k: r.k, sec: r.s.sec, label: r.s.label, value: `${B.fx(r.x)} · ${B.fy(r.y)}`, change: '' }));
      V.endTitle = `${monthYear(G[L])}: ${RANK[B.kx][0].toLowerCase()} · ${RANK[B.ky][0] === 'Total return' ? 'return' : RANK[B.ky][0].toLowerCase()}`; V.endSub = V.title;
      V.caption = `${V.title} (${monthYear(G[L])}): ` + V.final.map((r) => `${r.label} ${r.value}`).join(' · ');
      return;
    }
    if (V.kind === 'treemap') {
      const rows = V.series.map((s, k) => ({ k, s, v: s.v[L], r: s.r[L] })).filter((r) => r.v > 0).sort((a, c) => c.v - a.v).slice(0, 8);
      V.final = rows.map((r, i) => ({ k: r.k, sec: r.s.sec, label: `${i + 1}. ${r.s.label}`, value: money(r.v), change: fin(r.r) ? pctf(r.r, 0) : '', up: (r.r || 0) >= 0 }));
      V.endTitle = `The largest, ${monthYear(G[L])}`; V.endSub = 'market value · 12-month total return';
      V.caption = `${V.title} (${monthYear(G[L])}): ` + V.final.map((r) => `${r.label} ${r.value}`).join(' · ');
      return;
    }
    if (V.kind === 'sectors') {
      const share = V.stack.share;
      V.final = V.series.map((s, k) => ({ k, sec: s.sec, label: s.label, v: s.v[L], v0: s.v.find(fin) })).sort((a, c) => (c.v || 0) - (a.v || 0)).slice(0, 8)
        .map((r) => ({ k: r.k, sec: r.sec, label: r.label, value: V.fmt(r.v), change: share && fin(r.v0) ? `${r.v >= r.v0 ? '+' : '−'}${Math.abs(100 * (r.v - r.v0)).toFixed(1)} pts` : (fin(r.v0) && r.v0 > 0 ? pctf(r.v / r.v0 - 1, 0) : ''), up: r.v >= (r.v0 || 0) }));
      V.endTitle = V.actual ? `${V.metric}, ${dayLabel(G[L])}` : `${share ? V.metric || 'Share of market value' : 'Market value'}, ${monthYear(G[L])}`; V.endSub = V.actual ? `reported observations since ${dayLabel(G[0])}` : `change since ${monthYear(G[0])}`;
      V.caption = `${V.title}, ${monthYear(G[0])} → ${monthYear(G[L])}: ` + V.final.map((r) => `${r.label} ${r.value} (${r.change})`).join(' · ');
      return;
    }
    if (V.kind === 'sankey') {
      const fr = V.sk.frames[L], f0 = V.sk.frames[0], h = fr.head || {}, h0 = f0.head || {};
      const row = (label, v, v0) => ({ k: 0, label, value: money(v), change: fin(v) && fin(v0) && v0 > 0 && v > 0 ? pctf(v / v0 - 1, 0) : '', up: (v || 0) >= (v0 || 0) });
      V.final = [row('Revenue', h.revenue, h0.revenue)];
      if (fin(h.oi)) V.final.push(row('Operating profit', h.oi, h0.oi));
      if (fin(h.ni)) V.final.push(row('Net earnings', h.ni, h0.ni));
      if (fin(h.ocf)) V.final.push(row('Operating cash flow', h.ocf, h0.ocf));
      if (fin(h.oi) && h.revenue) V.final.push({ k: 0, label: 'Operating margin', value: (h.oi < 0 ? '−' : '') + Math.abs(100 * h.oi / h.revenue).toFixed(1) + '%', change: fin(h0.oi) && h0.revenue ? `${h.oi / h.revenue >= h0.oi / h0.revenue ? '+' : '−'}${Math.abs(100 * (h.oi / h.revenue - h0.oi / h0.revenue)).toFixed(1)} pts` : '', up: true });
      V.endTitle = `${V.series[0].label} ${fr.label}`; V.endSub = `change since ${f0.label}`;
      V.caption = `${V.series[0].name.replace(/,? (INC|CORP|CORPORATION|LTD|PLC|CO)\.?$/i, '')}, ${f0.label} → ${fr.label}: ` + V.final.map((r) => `${r.label.toLowerCase()} ${r.value}${r.change ? ' (' + r.change + ')' : ''}`).join(', ');
      return;
    }
    if (V.kind === 'snowball') {
      V.final = [];
      V.snowballSummary = [];
      V.series.forEach((s, k) => {
        const initialShares = s.initialShares == null ? s.sh.find(fin) : s.initialShares;
        const finalShares = s.finalShares == null ? s.sh[L] : s.finalShares;
        const annual = s.annualIncome == null ? snowIncome(s.paid) : s.annualIncome;
        const monthly = annual / 12, monthAmounts = {};
        G.forEach((g, i) => {
          const month = new Date(g).toISOString().slice(0, 7);
          monthAmounts[month] = (monthAmounts[month] || 0) + (s.paid[i] || 0);
        });
        const shfmt = v => fin(v) ? Number(v).toLocaleString('en-US', {maximumFractionDigits:2}) : '—';
        const reverse = Boolean(V.snowGoal);
        const investment = (reverse ? (V.snowGoal.solveFor === 'lump' ? 'Required start ' : 'Required buy ') : 'Start ') +
          money(V.snowGoal && V.snowGoal.solveFor === 'rec' ? s.perBuy : s.initialCash, 0) +
          (reverse && V.snowGoal.solveFor === 'rec' ? ' each scheduled purchase' :
            s.perBuy > 0 ? ' + ' + money(s.perBuy, 0) + ' per scheduled purchase' : '');
        V.snowballSummary.push({
          k, ticker:s.label, initial:shfmt(initialShares), final:shfmt(finalShares),
          monthly:money(monthly), annual:money(annual),
          monthlyNote: fin(s.firstAnnual) && s.firstAnnual > 0 ? 'Year one ' + money(s.firstAnnual / 12) + ' · last 52 weeks ÷ 12' : 'Trailing 52-week gross / 12',
          investment, initialCash:s.initialCash, perBuy:s.perBuy,
          monthly_cashflow_usd:monthAmounts, initial_shares:initialShares,
          final_shares:finalShares, annualIncome:annual, monthlyIncome:monthly
        });
        V.final.push({k, label:s.label + ' final shares', value:shfmt(finalShares),
          change:'+' + (100 * s.fromDiv / Math.max(1e-9,s.bought)).toFixed(0) + '% from DRIP', up:true});
      });
      V.endTitle = V.snowGoal ? 'Dividend income target · backward solve' : 'The dividend snowball';
      V.endSub = V.snowGoal ?
        'Goal ' + money(V.snowGoal.requested) + (V.snowGoal.unit === 'annual' ? '/yr' : '/mo') +
          ' · historical 52-week paid dividends · reinvested' :
        dayLabel(G[0]) + ' → ' + dayLabel(G[L]) +
          ' · monthly equivalent = gross trailing 52-week dividends / 12';
      V.caption = V.title + ': ' + V.snowballSummary.map(r =>
        r.ticker + ' · ' + r.investment + ' · ' + r.initial + ' initial shares → ' +
        r.final + ' final shares · terminal dividends ' + r.monthly + '/month equivalent (' +
        r.annual + '/year), gross and reinvested').join(' | ');
      V.notes.add('Terminal monthly income is the gross realized dividend amount from the last 52 weekly observations divided by 12. Actual cash payments may be quarterly, seasonal or irregular; it is NOT cash withdrawn or a forward dividend forecast.');
      return;
    }
    if (V.kind === 'timing') {
      const put = V.contrib[L];
      V.final = V.series.map((s, k) => { const v = s.v[L], r = xirr(s.flows.concat([[G[L], v]])); return { k, name: s.label, label: s.label + (fin(r) ? ` · ${(100 * r).toFixed(1)}%/yr` : ''), value: money(v), change: pctf(v / put - 1, 0), up: v >= put, v, irr: r }; }).sort((a, c) => c.v - a.v);
      const best = V.final.find((r) => r.name === 'Bought at the bottom'), worst = V.final.find((r) => r.name === 'Bought at the top');
      V.endTitle = worst && best ? `Worst timing: ${worst.value} · perfect: ${best.value}` : 'The result'; V.endSub = `${money(put, 0)} put in · ${V.timing.years} years · ${V.timing.sym}, dividends reinvested`;
      V.caption = `${V.title}: ` + V.final.map((r) => `${r.name} ${r.value}${fin(r.irr) ? ' (' + (100 * r.irr).toFixed(1) + '%/yr)' : ''}`).join(' · ') + ` · ${money(put, 0)} put in`;
      return;
    }
    if (V.kind === 'calendar') {
      const cells = V.cal.cells.filter((c) => fin(c[2])), lab = (c) => `${MON[c[1]]} ${c[0]}`;
      const best = cells.reduce((m, c) => (c[2] > m[2] ? c : m)), worst = cells.reduce((m, c) => (c[2] < m[2] ? c : m)), up = cells.filter((c) => c[2] > 0).length / cells.length;
      const yrs = V.cal.years.map((y) => [y, cells.filter((c) => c[0] === y).reduce((a, c) => a * (1 + c[2]), 1) - 1, cells.filter((c) => c[0] === y).length]).filter((x) => x[2] >= 12);
      const tot = cells.reduce((a, c) => a * (1 + c[2]), 1) - 1, yrsN = cells.length / 12;
      V.final = [{ k: 0, label: 'Best month', value: lab(best), change: pctf(best[2], 1), up: true }, { k: 0, label: 'Worst month', value: lab(worst), change: pctf(worst[2], 1), up: false },
        { k: 0, label: 'Months up', value: `${Math.round(100 * up)}%`, change: '' }];
      if (yrs.length) { const by = yrs.reduce((m, x) => (x[1] > m[1] ? x : m)), wy = yrs.reduce((m, x) => (x[1] < m[1] ? x : m)); V.final.push({ k: 0, label: 'Best year', value: String(by[0]), change: pctf(by[1], 0), up: true }, { k: 0, label: 'Worst year', value: String(wy[0]), change: pctf(wy[1], 0), up: false }); }
      if (yrsN >= 1) V.final.push({ k: 0, label: 'A year, on average', value: '', change: pctf(Math.pow(1 + tot, 1 / yrsN) - 1, 1), up: tot >= 0 });
      V.endTitle = `${V.series[0].label}: ${pctf(tot, 0)} in all`; V.endSub = `${monthYear(G[0])} → ${monthYear(G[L])} · monthly total return`;
      V.caption = `${V.series[0].label} month by month: best ${lab(best)} ${pctf(best[2], 1)}, worst ${lab(worst)} ${pctf(worst[2], 1)}, up in ${Math.round(100 * up)}% of months`;
      return;
    }
    if (V.kind === 'dist') {
      const Y = V.hist.yrs, full = Y.filter((x) => !x.ytd), srt = full.slice().sort((a, c) => c.median - a.median);
      const pickY = srt.slice(0, 3).concat(srt.slice(-3).reverse()).filter((x, i, arr) => arr.indexOf(x) === i);
      V.final = pickY.map((x) => ({ k: 0, label: `${x.y}${x === srt[0] ? ' (best)' : x === srt[srt.length - 1] ? ' (worst)' : ''}`, value: `median ${pctf(x.median, 0)}`, change: `${Math.round(100 * x.up)}% up`, up: x.median >= 0 }));
      V.endTitle = 'The middle company, by year'; V.endSub = `${Y[0].y}–${Y[Y.length - 1].y} · total return · today's companies on the site`;
      V.caption = `${V.title}: ` + pickY.map((x) => `${x.y} median ${pctf(x.median, 0)} (${Math.round(100 * x.up)}% rose)`).join(' · ');
      return;
    }
    const yrs = (G[L] - G[0]) / (365.25 * DAY);
    // the distributions paid, in dollars as paid: under each row of the end card and in the caption
    const divTxt = (s) => (V.kind === 'growth' && s.inc && s.inc.total > 0 && s.inc.mode !== 'price' ? `${money(s.inc.total, 0)} dividends ${s.inc.mode === 'tr' ? 'reinvested' : 'taken as cash'}` : '');
    const divSub = (s) => { const t = divTxt(s); if (!t) return ''; const l = s.inc.last12; return `Paid ${t.replace(' dividends', ' in dividends,')}` + (fin(l) && l > 0 ? ` · ${money(l, 0)} in the last 12 months` : ''); };
    if (V.kind === 'growth' && V.goal) {                      // an end value to reach: the amount each ticker needed, smallest first
      const g = V.goal, mode = V.split ? ' · price + dividends as cash' : st.div === 'price' ? ' · price only' : ' · dividends reinvested';
      V.final = V.series.map((s, k) => {
        const r = yrs >= 1 ? xirr(s.flows.concat([[G[L], s.v[L]]])) : null, amt = g.solve === 'lump' ? s.lump : s.each;
        return { k, name: s.label, label: s.label + (fin(r) ? ` · ${(100 * r).toFixed(1)}%/yr` : ''), value: s.need, change: `${money(s.put, 0)} put in`, up: true, irr: r, amt, v: -amt, sub: divSub(s), subTr: s.mode === 'tr', div: divTxt(s) };
      }).sort((a, c) => a.amt - c.amt);
      const f0 = V.final[0];
      V.endTitle = f0 ? `${money(g.value, 0)} by ${dayLabel(G[L])}: ${f0.name} needed ${f0.value}` : '';
      V.endSub = `${span}${mode}` + (g.solve === 'lump' && g.recIn > 0 ? ` · plus ${money(g.recIn, 0)} ${g.per}` : g.solve === 'rec' && g.lumpIn > 0 ? ` · plus ${money(g.lumpIn, 0)} to start` : '');
      V.caption = `To reach ${money(g.value, 0)} (${span}): ` + V.final.map((r) => `${r.name} ${r.value} (${r.change}${fin(r.irr) ? ', ' + (100 * r.irr).toFixed(1) + '%/yr' : ''}${r.div ? ', ' + r.div : ''})`).join(' vs ');
      return;
    }
    const rows = V.series.map((s, k) => {
      if (V.kind === 'rrg') { const x = s.x[L], y = s.y[L]; const q = fin(x) && fin(y) ? (x >= 100 ? (y >= 100 ? 'Leading' : 'Weakening') : (y < 100 ? 'Lagging' : 'Improving')) : '—'; return { k, label: s.label, value: q, v: fin(x) ? x : -Infinity }; }
      const v = s.v[L], v0 = s.v.find(fin);
      if (V.kind === 'drawdown') { const lo = Math.min(...s.v.filter(fin)); return { k, label: s.label, value: V.fmt(v), change: pctf(lo, 1), up: false, v: fin(v) ? v : -Infinity }; }
      const ref = V.base || (V.contrib ? V.contrib[L] : null);
      const change = ref ? pctf(v / ref - 1) : (fin(v0) && v0 !== 0 && V.unit !== '%' && V.kind !== 'formula' ? pctf(v / v0 - 1) : '');
      const irr = V.kind === 'growth' && V.flows && yrs >= 1 && fin(v) ? xirr(V.flows.concat([[G[L], v]])) : null;
      return { k, label: s.label + (fin(irr) ? ` · ${(100 * irr).toFixed(1)}%/yr` : ''), name: s.label, value: V.fmt(v), change, irr, up: ref ? v >= ref : v >= v0, v: fin(v) ? v : -Infinity, sub: divSub(s), subTr: s.mode === 'tr', div: divTxt(s) };
    }).sort((a, b) => b.v - a.v);
    V.final = rows;
    if (V.kind === 'formula' && V.series.length > 1) {          // lines of very different sizes get a panel each
      const mags = V.series.map((s) => Math.max(...s.v.filter(fin).map(Math.abs), 1e-12));
      V.panels = Math.max(...mags) / Math.min(...mags) > 8;
    }
    const mode = V.split ? ' · price + dividends as cash' : st.div === 'price' ? ' · price only' : ' · dividends reinvested';
    if (V.kind === 'growth' && V.dca) {
      V.endTitle = rows[0] ? `${rows[0].name} ${rows[0].value} from ${money(V.dca.put, 0)} put in` : '';
      V.endSub = `${V.dca.every} · ${V.dca.buys} buys · ${span}${mode}`;
    } else {
      V.endTitle = V.kind === 'rrg' ? 'Where they stand' : V.kind === 'drawdown' ? 'Below the high: now · worst' : V.kind === 'growth' ? (rows[0] ? `${rows[0].name} ${rows[0].value} (${rows[0].change})` : '') : (V.metric || V.title);
      V.endSub = span + (V.kind === 'growth' ? mode + (yrs >= 1 ? ' · a year, money-weighted' : '') : '');
    }
    const yr = (r) => (fin(r.irr) ? `, ${(100 * r.irr).toFixed(1)}%/yr` : '') + (r.div ? ', ' + r.div : '');
    V.caption = V.kind === 'growth' ? (V.dca ? `${V.dca.every}, ${span}: ` : '') + rows.map((r) => `${r.name} ${r.value} (${r.change}${yr(r)})`).join(' vs ') + (V.dca ? ` · ${money(V.dca.put, 0)} put in` : '')
      : V.kind === 'rrg' ? rows.map((r) => `${r.label}: ${r.value}`).join(' · ')
        : V.kind === 'drawdown' ? rows.map((r) => `${r.label} ${r.value} now, worst ${r.change}`).join(' · ')
          : rows.map((r) => `${r.label} ${r.value}${r.change ? ' (' + r.change + ')' : ''}`).join(' · ');
  }

  /* ---------- the report under the video: its figures as a table, as text to copy and as a CSV ---------- */
  // the worst fall from a high, and each full calendar year's return, of the line a ticker follows (total return or price)
  function worstDrop(a, G) {
    let peak = -Infinity, pk = -1, worst = 0, at = -1, from = -1;
    for (let i = 0; i < a.length; i++) {
      const x = a[i]; if (!fin(x) || x <= 0) continue;
      if (x > peak) { peak = x; pk = i; }
      if (x / peak - 1 < worst) { worst = x / peak - 1; at = i; from = pk; }
    }
    return at < 0 ? { v: 0, at: null, from: null } : { v: worst, at: G[at], from: G[from] };
  }
  function calYears(a, G) {                                  // [[year, return]], from the last close of the year before
    const end = new Map(), out = [];
    for (let i = 0; i < G.length; i++) if (fin(a[i]) && a[i] > 0) end.set(new Date(G[i]).getUTCFullYear(), [G[i], +a[i]]);
    for (const [y, [t, v]] of end) { const p = end.get(y - 1), d = new Date(t); if (p && d.getUTCMonth() === 11 && d.getUTCDate() >= 24) out.push([y, v / p[1] - 1]); }
    return out;
  }
  // {title, sub, cols [[key, label, help]], rows [{k, label, name, sec, cells {key: [text, small, number]}}], caption, notes, foot}
  function report(V) {
    const R = reportOf(V);
    R.cols = R.cols.filter(([k]) => R.rows.some((r) => r.cells[k] && r.cells[k][0] !== '—'));
    return R;
  }
  function reportOf(V) {
    const G = V.grid || [], L = G.length - 1;
    const R = { kind: V.kind, title: V.title || '', sub: V.sub || '', cols: [], rows: [], caption: V.caption || '', notes: [...(V.notes || [])], foot: '' };
    const cell = (t, small, n) => [t == null || t === '' ? '—' : String(t), small || '', fin(n) ? +n : null];
    if (V.kind === 'growth') {
      const yrs = L > 0 ? (G[L] - G[0]) / (365.25 * DAY) : 0, mode = V.div || 'tr', A = V.adj || {}, I = A.infl, C = A.cash;
      const anyDiv = V.series.some((s) => s.inc && s.inc.total > 0), whole = fullYears(G), taxed = A.tax ? `, after ${Math.round(A.tax * 100)}% tax` : '';
      const cashRow = V.series.find((s) => s.bench === 'cash'), t0 = G[Math.max(0, (V.series[0] && V.series[0].v.findIndex(fin)) || 0)];
      const growth = (years) => { const ys = Object.keys(years || {}).map(Number).filter((y) => whole(y) && years[y] > 0).sort((a, b) => a - b); if (ys.length < 2) return null; const a = ys[0], b = ys[ys.length - 1]; return { a, b, r: Math.pow(years[b] / years[a], 1 / (b - a)) - 1 }; };
      const anyGrowth = V.series.some((s) => s.inc && growth(s.inc.years));
      R.cols = [
        ...(V.goal ? [['need', 'Needed', 'The amount worked back from the end value']] : []),
        ['put', 'Put in', 'All the money put in' + (V.real ? ', in dollars of the start' : '')], ['end', 'End value', dayLabel(G[L]) + (V.real ? ', in dollars of the start' : '')], ['gain', 'Gain', 'The end value against the money put in'],
        ['yr', V.real ? 'A year, after inflation' : 'A year', 'The money-weighted return a year (XIRR)' + (V.real ? ' in dollars of the start' : '')],
        ...(I && !V.real ? [['real', 'A year, after inflation', 'The money-weighted return a year with every amount in dollars of the start']] : []),
        ...(cashRow ? [['vsc', 'Against cash', 'The end value less the same money kept in cash']] : []),
        ...(A.disc != null ? [['pv', `Present value at ${A.disc}%`, `The end value discounted to ${dayLabel(t0)} at ${A.disc}% a year; NPV: the same, less every amount put in discounted alike`]] : []),
        ...(anyDiv ? [['div', ({ tr: 'Dividends paid, reinvested', split: 'Dividends paid, as cash', price: 'Dividends left out' }[mode] || 'Dividends paid') + taxed, 'In dollars as paid: each payment is the shares then held × the amount per share' + (V.real ? ', then in dollars of the start' : '')],
          ['l12', 'Last 12 months', 'Dividends paid in the last 52 weeks, and that as a share of the money put in']] : []),
        ...(anyGrowth ? [['ig', 'Dividend income growth', 'A year, between the first and the last full calendar year of dividends paid']] : []),
        ['dd', 'Worst drop', 'The largest fall from a high of the ' + (mode === 'tr' ? 'total-return' : 'price') + ' line'],
        ['cy', 'Best · worst year', 'Full calendar years in the window'],
      ];
      const irrOf = (flows, v) => (flows && yrs >= 1 && fin(v) ? xirr(flows.concat([[G[L], v]])) : null);
      const cashIrr = cashRow ? irrOf(cashRow.flows || V.flows, cashRow.v[L]) : null;
      R.rows = V.series.map((s, k) => {
        const v = s.v[L], put = s.put != null ? s.put : V.contrib ? V.contrib[L] : V.base, flows = s.flows || V.flows;
        const irr = irrOf(flows, v);
        const dd = worstDrop(s.idx || s.v, G), cy = calYears(s.idx || s.v, G);
        const best = cy.length ? cy.reduce((m, x) => (x[1] > m[1] ? x : m)) : null, worst = cy.length ? cy.reduce((m, x) => (x[1] < m[1] ? x : m)) : null;
        const inc = s.inc, ig = inc ? growth(inc.years) : null, c = {
          put: cell(money(put, 0), '', put), end: cell(V.fmt(v), V.real && s.nom ? `${money(s.nom[L], 0)} as paid then` : '', v),
          gain: cell(fin(v) && put ? pctf(v / put - 1) : '', fin(v) && fin(put) ? (v >= put ? '+' : '') + money(v - put, 0) : '', fin(v) && put ? v / put - 1 : null),
          yr: cell(fin(irr) ? pct1(irr) : '', V.real && s.nom ? (() => { const n = irrOf(A.flowsNom, s.nom[L]); return fin(n) ? `${pct1(n)} before inflation` : ''; })() : '', irr),
          dd: cell(dd.at ? pctf(dd.v, 1) : (s.idx || s.v).some(fin) ? 'None' : '', dd.at ? monthYear(dd.at) : '', dd.at ? dd.v : 0),
          cy: cell(best ? `${best[0]} ${pctf(best[1], 1)}` : '', worst && worst !== best ? `${worst[0]} ${pctf(worst[1], 1)}` : '', best ? best[1] : null),
        };
        if (I && !V.real) {                                     // every amount in dollars of the start, then the rate
          const df = I.df, at = new Map(G.map((g, i) => [g, i]));
          const rr = flows && fin(v) && yrs >= 1 ? xirr(flows.map(([t, a]) => [t, a * df[at.get(t)]]).concat([[G[L], v * df[L]]])) : null;
          c.real = cell(fin(rr) ? pct1(rr) : '', fin(v) ? `${money(v * df[L], 0)} in ${new Date(t0).getUTCFullYear()} dollars` : '', rr);
        }
        if (cashRow) c.vsc = s === cashRow ? cell('') : cell(fin(v) ? (v >= cashRow.v[L] ? '+' : '−') + money(Math.abs(v - cashRow.v[L]), 0) : '', fin(irr) && fin(cashIrr) ? `${irr >= cashIrr ? '+' : '−'}${Math.abs(100 * (irr - cashIrr)).toFixed(1)} pts a year` : '', fin(v) ? v - cashRow.v[L] : null);
        if (A.disc != null && fin(v)) {
          const pvf = (t) => Math.pow(1 + A.disc / 100, -(t - t0) / (365.25 * DAY)), pv = v * pvf(G[L]);
          const npv = flows ? flows.reduce((a2, [t, a]) => a2 + a * pvf(t), pv) : null;
          c.pv = cell(money(pv, 0), fin(npv) ? `NPV ${npv >= 0 ? '+' : '−'}${money(Math.abs(npv), 0)}` : '', pv);
        }
        if (V.goal) c.need = cell(s.need, '', V.goal.solve === 'lump' ? s.lump : s.each);
        if (anyDiv) {
          const kept = inc && inc.mode === 'split' && A.interest && s.cash ? s.cash[L] : null;
          c.div = inc ? cell(money(inc.total, 0), inc.mode === 'tr' && fin(inc.worth) ? `worth ${money(inc.worth, 0)} now` : fin(kept) ? `${money(kept, 0)} with interest` : inc.mode === 'price' ? 'not in the value' : '', inc.total) : cell('');
          c.l12 = inc && fin(inc.last12) ? cell(money(inc.last12, 0), put > 0 ? `${(100 * inc.last12 / put).toFixed(1)}% on cost` : '', inc.last12) : cell('');
        }
        if (anyGrowth) c.ig = ig ? cell(pctf(ig.r, 1), `${ig.a} → ${ig.b}`, ig.r) : cell('');
        return { k, label: s.label, name: s.name, bench: s.bench, cells: c };
      });
      // dividends year by year, in dollars as paid (or of the start): the cash each ticker paid
      const ys = [...new Set(V.series.flatMap((s) => (s.inc ? Object.keys(s.inc.years || {}) : [])))].map(Number).sort((a, b) => a - b), payers = V.series.filter((s) => s.inc && s.inc.total > 0);
      if (ys.length && payers.length) R.years = { title: `Dividends paid each year${V.real ? ', in dollars of the start' : ', in dollars as paid'}${taxed} — ${({ tr: 'reinvested', split: 'taken as cash', price: 'left out of the value' })[mode] || ''}`,
        cols: payers.map((s) => ({ label: s.label, k: V.series.indexOf(s) })), rows: ys.map((y) => ({ y, part: !whole(y), v: payers.map((s) => s.inc.years[y] || 0) })) };
      const src = (x) => ({ fixed: '', bill: '3-month Treasury bills (FRED DGS3MO)', ff: 'the Fed funds rate (FRED FEDFUNDS) until the 3-month bill history is published', cpi: 'the consumer price index (FRED CPIAUCSL)', 'cpi-yoy': 'consumer prices rebuilt from the year-on-year CPI rates (approximate)' })[x] || '';
      R.foot = (anyDiv ? 'Dividends and interest in dollars as paid' + (A.tax ? `, after a ${Math.round(A.tax * 100)}% tax` : ', before tax') + ': each payment is the shares then held × the amount per share'
        + (mode === 'tr' ? '; reinvested, it bought more shares that week, and “worth now” is what those shares are worth at the end (the total-return value less the same money in the price alone)' : mode === 'split' ? (A.interest ? '; taken as cash, which then earns the cash rate' : '; taken as cash, kept beside the shares (not reinvested)') : '; the price-only line leaves them out') + '. ' : '')
        + 'A year: the money-weighted return a year (XIRR), which for one sum at the start is the yearly growth rate. '
        + (C ? `Cash: the same money put in on the same dates, earning ${C.rate != null ? C.rate + '% a year' : src(C.src)} — its future value. ` : '')
        + (I ? (V.real ? `After inflation: every amount in dollars of ${monthYear(t0)}, by ${I.rate != null ? 'prices rising ' + I.rate + '% a year' : src(I.src)}; prices rose ${pctf(I.rise, 1).replace('+', '')} over the window. ` : `Inflation: the money put in, rising with ${I.rate != null ? 'prices at ' + I.rate + '% a year' : src(I.src)} (prices rose ${pctf(I.rise, 1).replace('+', '')}) — what keeps its buying power. `) : '')
        + (A.disc != null ? `Present value: the end value discounted to ${dayLabel(t0)} at ${A.disc}% a year; NPV adds every amount put in, discounted alike (above zero: better than ${A.disc}% a year). ` : '')
        + 'Weekly closes.';
      return R;
    }
    if (V.kind === 'snowball' && Array.isArray(V.snowballSummary)) {
      R.title = V.endTitle || R.title; R.sub = V.endSub || R.sub;
      const whole = fullYears(G);
      R.cols = [['inv', 'Money in'], ['put', 'Put in'], ['sh', 'Shares', 'At the start → at the end, and the share of the end bought by dividends'], ['all', 'Dividends received', 'In all, in dollars as paid — every one reinvested'],
        ['mo', 'A month now', 'The last 52 weeks ÷ 12 (payments may come quarterly)'], ['one', 'Year one', 'The first 52 weeks ÷ 12'], ['ig', 'Income growth', 'A year, between the first and the last full calendar year'], ['yoc', 'On cost', 'A year of dividends now, as a share of the money put in'], ['end', 'End value']];
      R.rows = V.snowballSummary.map((r) => {
        const s = V.series[r.k] || {}, ys = Object.keys(s.yearly || {}).map(Number).filter((y) => whole(y) && s.yearly[y] > 0).sort((a, b) => a - b);
        const ig = ys.length >= 2 ? Math.pow(s.yearly[ys[ys.length - 1]] / s.yearly[ys[0]], 1 / (ys[ys.length - 1] - ys[0])) - 1 : null, all = (s.paid || []).reduce((a, x) => a + (x || 0), 0);
        return { k: r.k, label: r.ticker, name: s.name, cells: {
          inv: cell(r.investment), put: cell(money(s.put, 0), '', s.put), sh: cell(`${r.initial} → ${r.final}`, s.bought ? `+${(100 * s.fromDiv / s.bought).toFixed(0)}% from dividends` : '', r.final_shares),
          all: cell(money(all, 0), 'reinvested', all), mo: cell(r.monthly, `${r.annual} a year`, r.monthlyIncome), one: cell(fin(s.firstAnnual) ? money(s.firstAnnual / 12) : '', fin(s.firstAnnual) ? `${money(s.firstAnnual, 0)} a year` : '', fin(s.firstAnnual) ? s.firstAnnual / 12 : null),
          ig: cell(fin(ig) ? pctf(ig, 1) : '', fin(ig) ? `${ys[0]} → ${ys[ys.length - 1]}` : '', ig), yoc: cell(s.put > 0 ? (100 * r.annualIncome / s.put).toFixed(1) + '%' : '', '', s.put > 0 ? r.annualIncome / s.put : null),
          end: cell(money(s.v ? s.v[L] : null, 0), '', s.v ? s.v[L] : null) } };
      });
      const ys = [...new Set(V.series.flatMap((s) => Object.keys(s.yearly || {})))].map(Number).sort((a, b) => a - b);
      if (ys.length) R.years = { title: 'Dividends received each year, in dollars as paid — every one reinvested', cols: V.series.map((s, k) => ({ label: s.label, k })), rows: ys.map((y) => ({ y, part: !whole(y), v: V.series.map((s) => (s.yearly || {})[y] || 0) })) };
      R.foot = 'Dividends in dollars as paid: the shares then held × the amount per share, each buying more shares at that week’s close. A month now: the last 52 weeks ÷ 12. Weekly closes.';
      return R;
    }
    R.title = V.endTitle || R.title; R.sub = V.endSub || R.sub;
    R.cols = [['value', 'Value'], ['change', 'Change']];
    R.rows = (V.final || []).map((r) => ({ k: r.k || 0, sec: r.sec, label: r.label, cells: { value: cell(r.value, '', fin(r.v) ? r.v : null), change: cell(r.change) } }));
    return R;
  }
  const pct1 = (x) => (x < 0 ? '−' : '') + Math.abs(100 * x).toFixed(1) + '%';
  const tsv = (x) => String(x == null ? '' : x).replace(/[\t\n]+/g, ' ');
  function reportText(R, link) {                             // the report as plain text: a table with tabs, then the caption
    const head = [''].concat(R.cols.map((c) => c[1])).map(tsv).join('\t');
    const rows = R.rows.map((r) => [r.label].concat(R.cols.map(([k]) => { const c = r.cells[k] || ['—', '']; return c[0] + (c[1] ? ` (${c[1]})` : ''); })).map(tsv).join('\t'));
    const Y = R.years, years = Y && Y.rows.length ? ['', Y.title, ['Year'].concat(Y.cols.map((c) => c.label)).map(tsv).join('\t'), ...Y.rows.map((r) => [r.y + (r.part ? ' (part)' : '')].concat(r.v.map((v) => (v > 0 ? money(v, 0) : '—'))).map(tsv).join('\t'))] : [];
    return [R.title, R.sub, '', head, ...rows, ...years, '', R.caption, ...(R.notes.length ? ['', ...R.notes.map((n) => '• ' + n)] : []), ...(R.foot ? ['', R.foot] : []), '', 'filing-flows.com' + (link ? ' · ' + link : '')]
      .filter((x, i, a) => !(x === '' && (i === 0 || a[i - 1] === ''))).join('\n').trim();
  }
  const csvCell = (x) => { const s = x == null ? '' : typeof x === 'number' ? (Number.isFinite(x) ? String(+x.toFixed(6)) : '') : String(x); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  // the series behind the video, one row a week (a month, a quarter); without such series, the report's table
  function csvOf(V, R) {
    const G = V.grid || [], rows = [];
    if (V.kind === 'snowball' && V.series && V.series.length) {   // month by month: the dividends received and the shares at the month's end
      const mk = (g) => iso(g).slice(0, 7), months = [...new Set(G.map(mk))];
      rows.push(['month', ...V.series.flatMap((s) => [s.label + ' dividends', s.label + ' shares'])]);
      months.forEach((m) => { const idx = G.map((g, i) => (mk(g) === m ? i : -1)).filter((i) => i >= 0), lastI = idx[idx.length - 1];
        rows.push([m, ...V.series.flatMap((s) => [idx.reduce((a, i) => a + ((s.paid || [])[i] || 0), 0), (s.sh || [])[lastI]])]); });
      return rows.map((r) => r.map(csvCell).join(',')).join('\n') + '\n';
    }
    const lined = V.series && V.series.length && V.series.every((s) => (Array.isArray(s.v) && s.v.length === G.length) || (Array.isArray(s.x) && s.x.length === G.length));
    if (lined && !['sankey', 'snowball', 'calendar', 'dist', 'treemap', 'bubble'].includes(V.kind)) {
      const head = ['date'], get = [];
      if (V.kind === 'growth' && (V.contrib || V.base)) { head.push('put in'); get.push((i) => (V.contrib ? V.contrib[i] : V.base)); }
      V.series.forEach((s) => {
        if (s.x) { head.push(s.label + ' RS-ratio', s.label + ' RS-momentum'); get.push((i) => s.x[i], (i) => s.y[i]); return; }
        head.push(V.kind === 'growth' ? s.label + ' value' : s.label); get.push((i) => s.v[i]);
        if (V.kind === 'growth' && s.price) { head.push(s.label + ' price only'); get.push((i) => s.price[i]); }
        if (V.kind === 'growth' && s.dist) { head.push(s.label + ' dividends paid (cumulative)'); get.push((i) => s.dist[i]); }
        if (V.kind === 'growth' && s.contrib) { head.push(s.label + ' put in'); get.push((i) => s.contrib[i]); }
      });
      rows.push(head);
      G.forEach((g, i) => rows.push([iso(g), ...get.map((f) => f(i))]));
    } else {
      rows.push([''].concat(R.cols.map((c) => c[1])));
      R.rows.forEach((r) => rows.push([r.label].concat(R.cols.map(([k]) => { const c = r.cells[k]; return c ? (c[2] != null ? c[2] : c[0]) : ''; }))));
    }
    return rows.map((r) => r.map(csvCell).join(',')).join('\n') + '\n';
  }

  const yearsCSV = (R) => { const Y = R.years; if (!Y) return ''; return [['year', 'part of the year', ...Y.cols.map((c) => c.label)], ...Y.rows.map((r) => [r.y, r.part ? 'yes' : '', ...r.v])].map((r) => r.map(csvCell).join(',')).join('\n') + '\n'; };

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
    const N = Math.round(timing(V, opt).D * fps);
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
  function recordPreview(canvas, V, opt, onProgress, cancel) {   // the fallback: record the canvas while it plays in real time
    return new Promise((ok, bad) => {
      if (!canvas.captureStream || typeof MediaRecorder === 'undefined') { bad(new Error('this browser cannot record video')); return; }
      const fps = +opt.fps === 60 ? 60 : 30, stream = canvas.captureStream(fps);
      const type = ['video/mp4;codecs=avc1', 'video/webm;codecs=vp9', 'video/webm'].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      const rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 8e6 } : undefined), parts = [];
      rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };
      let stopped = false;
      rec.onstop = () => ok(stopped ? 'cancelled' : { blob: new Blob(parts, { type: type.split(';')[0] || 'video/webm' }), codec: type || 'default', recorded: true });
      const ctx = canvas.getContext('2d'), D = timing(V, opt).D, t0 = performance.now();
      rec.start(250);
      (function tick() {
        if (cancel && cancel()) { stopped = true; rec.stop(); return; }
        const t = (performance.now() - t0) / 1000; draw(ctx, canvas.width, canvas.height, V, opt, Math.min(t, D)); onProgress(Math.min(1, t / D));
        if (t < D) requestAnimationFrame(tick); else setTimeout(() => rec.stop(), 120);
      })();
    });
  }

  /* ---------- the page ---------- */
  function fileStem(V) {
    const slug = (x) => String(x || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const what = V.actual ? `actual-weights-${V.actual.fund}-${V.kind === 'sectors' ? 'sectors' : 'holdings'}` : V.kind === 'rank' ? `top-${V.rankN}-${slug(V.metric)}` : V.kind === 'dist' ? 'return-spread' : V.kind === 'calendar' ? V.series[0].key + '-monthly-returns'
      : V.series.map((s) => s.key).join('-').replace(/[^A-Za-z0-9-]+/g, '').slice(0, 40) + (V.kind === 'drawdown' ? '-drawdowns' : V.dca ? '-monthly-buys' : '');
    return 'filing-flows-' + (what.slice(0, 60) || 'video');
  }
  function download(blob, name) {
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  }
  function yearsTable(R, esc2, colK) {                          // dividends by year: rows of years, a column a ticker, the change on the year before
    const Y = R.years; if (!Y || !Y.rows.length) return '';
    const tot = Y.cols.map((_, j) => Y.rows.reduce((a, r) => a + (r.v[j] || 0), 0));
    return `<div class="st-yh"><h3>${esc2(Y.title)}</h3><button class="btn small" type="button" data-rep="ycsv">CSV ↓</button></div><div class="tbl-wrap st-years"><table class="st-tbl"><thead><tr><th scope="col">Year</th>${Y.cols.map((c) => `<th scope="col" class="num"><i style="background:${esc2(colK(c.k))}"></i>${esc2(c.label)}</th>`).join('')}</tr></thead><tbody>`
      + Y.rows.map((r, i) => `<tr><th scope="row">${r.y}${r.part ? '<small>part of the year</small>' : ''}</th>${r.v.map((v, j) => { const p = i ? Y.rows[i - 1] : null, g = p && !p.part && !r.part && p.v[j] > 0 && v > 0 ? v / p.v[j] - 1 : null; return `<td class="num">${v > 0 ? esc2(money(v, v >= 100 ? 0 : 2)) : '—'}${fin(g) ? `<small>${esc2(pctf(g, 0))} on the year</small>` : ''}</td>`; }).join('')}</tr>`).join('')
      + `<tr class="st-tot"><th scope="row">In all</th>${tot.map((v) => `<td class="num">${esc2(money(v, 0))}</td>`).join('')}</tr></tbody></table></div>`;
  }
  function reportHTML(R, th) {
    const col = (r) => (r.bench ? benchCol(th, r.bench) : r.sec ? secCol(th, r.sec) : th.pal[(r.k || 0) % th.pal.length]);
    const cls = (k, c) => (k === 'gain' && c[2] != null ? (c[2] >= 0 ? 'num up' : 'num down') : 'num');
    const head = `<tr><th scope="col"><span class="st-sr">Series</span></th>${R.cols.map(([, l, help]) => `<th scope="col" class="num"${help ? ` title="${esc(help)}"` : ''}>${esc(l)}</th>`).join('')}</tr>`;
    const body = R.rows.map((r) => `<tr><th scope="row"><i style="background:${esc(col(r))}"></i>${esc(r.label)}${r.name && r.name !== r.label ? `<small>${esc(String(r.name).slice(0, 38))}</small>` : ''}</th>`
      + R.cols.map(([k]) => { const c = r.cells[k] || ['—', '']; return `<td class="${cls(k, c)}">${esc(c[0])}${c[1] ? `<small>${esc(c[1])}</small>` : ''}</td>`; }).join('') + '</tr>').join('');
    return `<div class="st-rep-head"><div><div class="st-rep-k">Results</div><h2>${esc(R.title)}</h2>${R.sub ? `<div class="st-rep-sub">${esc(R.sub)}</div>` : ''}</div>`
      + `<div class="st-rep-act"><button class="btn small" type="button" data-rep="copy" title="The table, the caption and the notes as text">Copy text</button><button class="btn small" type="button" data-rep="csv" title="The figures behind the video, week by week">CSV ↓</button><button class="btn small" type="button" data-rep="png" title="This frame as a picture, at the size of the video">Image ↓</button></div></div>`
      + (R.rows.length ? `<div class="tbl-wrap st-wide"><table class="st-tbl"><thead>${head}</thead><tbody>${body}</tbody></table></div>` : '')
      // on a phone the same figures turned around: a row for each figure, a column for each series
      + (R.rows.length ? `<div class="tbl-wrap st-tall"><table class="st-tbl"><thead><tr><th scope="col"><span class="st-sr">Figure</span></th>${R.rows.map((r) => `<th scope="col" class="num"><i style="background:${esc(col(r))}"></i>${esc(r.label)}</th>`).join('')}</tr></thead><tbody>`
        + R.cols.map(([k, l, help]) => `<tr><th scope="row"${help ? ` title="${esc(help)}"` : ''}>${esc(l)}</th>${R.rows.map((r) => { const c = r.cells[k] || ['—', '']; return `<td class="${cls(k, c)}">${esc(c[0])}${c[1] ? `<small>${esc(c[1])}</small>` : ''}</td>`; }).join('')}</tr>`).join('') + '</tbody></table></div>' : '')
      + yearsTable(R, esc, (k) => th.pal[(k || 0) % th.pal.length])
      + (R.caption ? `<div class="st-capbox"><div class="st-caph"><span>Caption to post</span><button class="btn small" type="button" data-rep="cap">Copy</button></div><div class="st-cap" id="st-cap">${esc(R.caption)}</div></div>` : '')
      + (R.notes.length ? `<ul class="st-notes" id="st-notes">${R.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : '')
      + (R.foot ? `<p class="st-rep-foot">${esc(R.foot)}</p>` : '');
  }
  const TEMPLATES = [
    { name: '$10,000: QQQ vs SPY', note: 'Ten years, distributions reinvested', s: { k: 'growth', t: 'QQQ,SPY', from: '2016-10-28', amt: '10000', div: 'tr', style: 'line', theme: 'bull' } },
    { name: 'Dividend ETFs, split out', note: 'SCHD vs VYM vs SPY: price + cash', s: { k: 'growth', t: 'SCHD,VYM,SPY', from: '2016-10-28', amt: '10000', div: 'split', style: 'line', theme: 'bull' } },
    { name: 'Nasdaq · S&P · Russell · Dow', note: 'A bar race since 2015', s: { k: 'growth', t: 'QQQ,SPY,IWM,DIA', from: '2015-01-02', amt: '10000', div: 'tr', style: 'bars', theme: 'sunset' } },
    { name: 'Sector rotation', note: 'The RRG of the sector ETFs, two years', s: { k: 'rrg', t: 'XLK,XLF,XLE,XLV,XLY,XLP,XLI,XLU', from: iso(Date.now() - 730 * DAY), bench: 'SPY', tail: '8', style: 'rrg', theme: 'bull' } },
    { name: 'Momentum ranking', note: '26-week return vs SPY of eight ETFs', s: { k: 'momentum', t: 'QQQ,IWM,DIA,SMH,XLE,GLD,TLT,EEM', from: '2020-01-03', lb: '26', bench: 'SPY', style: 'bars', theme: 'terminal' } },
    { name: 'Nvidia revenue', note: 'Quarter by quarter from its filings', s: { k: 'fund', t: 'NVDA', m: 'revenue', ttm: '0', style: 'columns', theme: 'bull' } },
    { name: 'Big Tech earnings race', note: 'Net earnings, trailing four quarters', s: { k: 'fund', t: 'AAPL,MSFT,GOOGL,AMZN,META,NVDA', m: 'ni', ttm: '1', style: 'bars', theme: 'clean' } },
    { name: 'Growth vs value ratio', note: 'IWF ÷ IWD and QQQ ÷ SPY, rebased', s: { k: 'formula', expr: 'Growth ÷ value: rebase(IWF/IWD)\nNasdaq ÷ S&P: rebase(QQQ/SPY)', from: '2010-01-01', style: 'line', theme: 'clean' } },
    { name: '$500 a month: QQQ vs SPY', note: 'Bought every month for ten years', s: { k: 'growth', t: 'QQQ,SPY', from: '2016-01-04', amt: '0', rec: '500', ri: '1', ru: 'm', div: 'tr', style: 'line', theme: 'bull' } },
    { name: 'Dividend stocks, cash on the side', note: 'KO vs PEP vs JNJ: price + dividends', s: { k: 'growth', t: 'KO,PEP,JNJ', from: '2016-01-04', amt: '10000', div: 'split', style: 'line', theme: 'clean' } },
    { name: 'The most valuable companies', note: 'Top 10 by market value since 2010', s: { k: 'rank', rm: 'cap', top: '10', from: '2010-01-31', step: 'm', style: 'bars', theme: 'bull', dur: '45' } },
    { name: 'Biggest by revenue', note: 'Top 10, quarter by quarter', s: { k: 'rank', rm: 'rev', top: '10', from: '2010-06-30', step: 'q', style: 'bars', theme: 'sunset', dur: '40' } },
    { name: 'Most traded stocks', note: 'Dollar volume, month by month', s: { k: 'rank', rm: 'dv', top: '10', from: '2015-01-31', step: 'm', style: 'bars', theme: 'terminal', dur: '40' } },
    { name: 'Priciest giants by P/E', note: 'Market value over $200B', s: { k: 'rank', rm: 'pe', top: '10', cmin: '200', from: '2016-01-31', step: 'm', style: 'bars', theme: 'bull', dur: '40' } },
    { name: 'Best 12-month runs', note: 'Companies over $10B, total return', s: { k: 'rank', rm: 'ret', win: '12', top: '10', cmin: '10', from: '2016-01-31', step: 'm', style: 'bars', theme: 'sunset', dur: '40' } },
    { name: 'Drawdowns since 2007', note: 'QQQ · SPY · TLT below their highs', s: { k: 'drawdown', t: 'QQQ,SPY,TLT', from: '2007-01-05', style: 'area', theme: 'bull', dur: '30' } },
    { name: 'Nvidia, month by month', note: 'A heatmap of every monthly return', s: { k: 'calendar', t: 'NVDA', from: '2016-01-01', style: 'heat', theme: 'bull', dur: '30' } },
    { name: "Every stock's year", note: 'How returns spread, 2005 to now', s: { k: 'dist', from: '2005-01-01', style: 'hist', theme: 'clean', dur: '30' } },
    { name: 'Growth vs return, in bubbles', note: 'The 25 largest companies, month by month', s: { k: 'bubble', bx: 'growth', by: 'ret', bs: 'cap', bn: '25', from: '2014-01-31', style: 'bubble', theme: 'bull', dur: '40' } },
    { name: 'The market as a map', note: 'Top 50 by market value since 2012', s: { k: 'treemap', tn: '50', tc: 'ret', from: '2012-01-31', style: 'treemap', theme: 'bull', dur: '40' } },
    { name: 'Who owns the market', note: 'Each sector\'s share of market value', s: { k: 'sectors', sa: 'share', from: '2012-01-31', style: 'stack', theme: 'clean', dur: '30' } },
    { name: 'Actual Dow tracking basket', note: 'DIA holdings · price-weighted tracker proxy · reported snapshots only', s: { k: 'actual', aw: 'index', at: 'dji', style: 'bars', from: '', dur: '20' } },
    { name: 'ETF actual holdings by report date', note: 'SPY disclosed positions, no backfilled history', s: { k: 'actual', aw: 'etf', ah: 'SPY', style: 'bars', from: '', dur: '20' } },
    { name: 'ETF company weight history', note: 'Actual disclosed company weights · Top N + Other', s: { k: 'actual', aw: 'etf', ah: 'SPY', style: 'companies', from: '', theme: 'clean', dur: '30' } },
    { name: 'Berkshire: reported portfolio', note: '13F company weights by quarter · not current holdings', s: { k: 'actual', aw: '13f', ac: '1067983', style: 'companies', from: '', theme: 'clean', dur: '30' } },
    { name: 'ETF allocation changes', note: 'Company or sector changes in percentage points', s: { k: 'actual', aw: 'etf', ah: 'SPY', style: 'changes', from: '', dur: '20' } },
    { name: 'Official transaction composition', note: 'Disclosed lower-bound amounts · NOT actual holdings', s: { k: 'actual', aw: 'official', ap: 'Nancy Pelosi', style: 'stack', from: '', theme: 'clean', dur: '30' } },
    { name: 'What the Dow is made of', note: 'Sector weights by share price, as the index counts', s: { k: 'sectors', idx: 'dji', sw: 'index', from: '2012-01-31', style: 'stack', theme: 'clean', dur: '30' } },
    { name: 'What it took to reach $1M', note: 'QQQ vs SPY: the monthly amount, worked back', s: { k: 'growth', t: 'QQQ,SPY', goal: '1000000', solve: 'rec', amt: '0', from: '2016-10-28', style: 'line', theme: 'bull' } },
    { name: 'Nvidia: where the money goes', note: 'The earnings flow, quarter by quarter', s: { k: 'sankey', t: 'NVDA', sm: 'detail', style: 'sankey', theme: 'clean', dur: '20' } },
    { name: 'The dividend snowball', note: 'SCHD vs KO, dividends buying shares', s: { k: 'snowball', t: 'SCHD,KO', amt: '10000', from: '2012-01-06', style: 'snow', theme: 'bull', dur: '30' } },
    { name: 'Bought at the top every year', note: '$2,000 a year into SPY: timing vs none', s: { k: 'timing', t: 'SPY', yb: '2000', from: '2006-01-01', style: 'line', theme: 'sunset', dur: '30' } },
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
    s.textContent = `.st-wrap{display:grid;grid-template-columns:minmax(280px,360px) 1fr;gap:22px;align-items:start}.st-main{min-width:0}@media(max-width:900px){.st-wrap{grid-template-columns:1fr}.st-main{order:-1}}
.st-side{border:1px solid var(--line);border-radius:14px;padding:14px 16px;background:var(--surface)}.st-side h3{margin:14px 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.st-side h3:first-child{margin-top:2px}.st-side label{display:block;font-size:12.5px;color:var(--muted);margin:8px 0 3px}.st-side .input,.st-side select,.st-side textarea{width:100%;box-sizing:border-box;font:inherit;font-size:14px;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.st-side textarea{min-height:84px;font-family:var(--mono);font-size:13px}.st-row{display:flex;gap:8px}.st-row>*{flex:1}.st-pills{display:flex;flex-wrap:wrap;gap:6px}.st-pills .pill{font-size:12.5px;padding:5px 10px}
.st-stage{background:#0b1220;border-radius:14px;overflow:hidden;display:flex;justify-content:center;align-items:center;box-shadow:var(--shadow)}.st-stage canvas{display:block;max-width:100%;max-height:72vh;height:auto}
.st-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 6px}.st-bar .sp{flex:1}.st-status{font-size:13px;color:var(--muted)}.st-prog{height:6px;border-radius:3px;background:var(--line);overflow:hidden;margin:6px 0}.st-prog i{display:block;height:100%;background:var(--accent);width:0}
.st-notes{font-size:12.5px;color:var(--muted);line-height:1.5;margin:8px 0 0;padding-left:18px}.st-notes li{margin:2px 0}
.st-tpl-bar{display:flex;align-items:center;gap:10px;margin:16px 0 8px}.st-tpl-bar>span{font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}.st-tpl-bar .sp{flex:1}
.st-tpl{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(196px,228px);gap:10px;overflow-x:auto;scroll-snap-type:x proximity;padding:2px 2px 10px;margin:0 0 6px;-webkit-mask-image:linear-gradient(90deg,#000 90%,transparent);mask-image:linear-gradient(90deg,#000 90%,transparent)}
.st-tpl.all{grid-auto-flow:row;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));grid-auto-columns:auto;overflow:visible;-webkit-mask-image:none;mask-image:none}
.st-tpl button{scroll-snap-align:start;text-align:left;font:inherit;border:1px solid var(--line);border-radius:12px;padding:10px 12px;background:var(--surface);cursor:pointer;color:var(--ink)}.st-tpl button:hover{border-color:var(--ink-2)}.st-tpl b{display:block;font-size:14px}.st-tpl span{font-size:12px;color:var(--muted)}
.st-rep{margin-top:14px;border:1px solid var(--line);border-radius:14px;background:var(--surface);padding:14px 16px}.st-rep-head{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start;justify-content:space-between;margin-bottom:10px}
.st-rep-k{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}.st-rep h2{font-size:17px;margin:2px 0;line-height:1.3}.st-rep-sub{font-size:13px;color:var(--muted)}.st-rep-act{display:flex;gap:6px;flex-wrap:wrap}
.st-rep .tbl-wrap{margin:2px 0 10px}.st-rep td small,.st-rep tbody th small{display:block;font-size:11.5px;color:var(--muted);font-weight:400;margin-top:1px}.st-rep thead th{white-space:normal;min-width:76px;vertical-align:bottom}
.st-rep tbody th{position:sticky;left:0;z-index:1;background:var(--surface);text-transform:none;letter-spacing:0;font-size:14px;color:var(--ink);font-weight:600}.st-rep tbody th i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:1px}
.st-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.st-tall{display:none}@media(max-width:640px){.st-wide{display:none}.st-tall{display:block}.st-tall th,.st-tall td{padding:8px 7px}.st-tall tbody th{font-size:12.5px;font-weight:500;color:var(--muted);white-space:normal;min-width:80px;max-width:100px}.st-tall thead th{text-transform:none;letter-spacing:0;font-size:13px;color:var(--ink);font-weight:600}.st-tall thead th i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}.st-rep{padding:12px}}
.st-yh{display:flex;align-items:center;gap:10px;margin:6px 0 6px}.st-yh h3{font-size:13.5px;margin:0;font-weight:600;color:var(--ink-2)}.st-years{max-height:420px;overflow:auto;width:max-content;max-width:100%}.st-years table{width:auto}.st-years td{min-width:96px}.st-years tbody th{min-width:0}.st-rep tr.st-tot th,.st-rep tr.st-tot td{font-weight:600;border-top:1px solid var(--line)}
.st-rep td.up{color:var(--accent-ink)}.st-rep td.down{color:var(--neg)}.st-capbox{margin-top:4px}.st-caph{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);margin-bottom:4px}.st-rep-foot{font-size:12px;color:var(--muted);line-height:1.5;margin:8px 0 0}
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
    const originalTheme = st.theme === 'appearance' ? DEF.theme : st.theme;
    if (root.FFAppearance?.get().video !== 'default' && root.FFAppearance?.videoTheme()) st.theme = 'appearance';
    const sel = (id, items, v) => `<select id="${id}">${items.map(([k, l]) => `<option value="${esc(k)}"${k === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    app.innerHTML = `<div class="page-head"><div class="eyebrow"><a href="#chart">← Charts</a> · Videos</div><h1>Make a market video</h1>
      <p class="muted" style="max-width:76ch">Growth races of any ETFs or stocks — a lump sum or the same amount bought every few days, weeks or months, with dividends reinvested, taken as cash on their own line, or left out — leaderboards of every company by market value, revenue, profit, P/E, P/B, volume or return, drawdowns, monthly-return heatmaps, the spread of every stock's year, RRG and momentum replays, companies' own figures and any formula. Animated in four looks and three shapes, at the length and pace you set, saved as an MP4 to post. Everything is drawn from the site's own data in your browser.</p></div>
      <div class="st-tpl-bar"><span>Start from a template</span><span class="sp"></span><button class="btn small" id="st-tpl-all" type="button" aria-expanded="false" aria-controls="st-tpl">All ${TEMPLATES.length} ▾</button></div>
      <div class="st-tpl" id="st-tpl">${TEMPLATES.map((x, i) => `<button type="button" data-tpl="${i}"><b>${esc(x.name)}</b><span>${esc(x.note)}</span></button>`).join('')}</div>
      <div class="st-wrap"><div class="st-side" id="st-side"></div><div class="st-main">
        <div class="st-stage"><canvas id="st-canvas" width="1280" height="720" aria-label="Video preview"></canvas></div>
        <div class="st-bar"><button class="btn primary" id="st-play" type="button">▶ Play</button><button class="btn" id="st-restart" type="button">⟲ Restart</button><span class="sp"></span>
          <button class="btn primary" id="st-export" type="button">Export MP4 ↓</button><button class="btn" id="st-link" type="button">Copy link</button></div>
        <div class="st-prog" id="st-prog" hidden><i></i></div><div class="st-status" id="st-status"></div>
        <section class="st-rep" id="st-rep" aria-label="Results" hidden></section>
      </div></div>`;
    const $ = (s) => app.querySelector(s), canvas = $('#st-canvas'), ctx = canvas.getContext('2d');
    let V = null, playing = false, t0 = 0, tNow = 0, raf = 0, token = 0, exporting = false, cancelReq = false;
    const opt = () => ({ appearanceTheme: st.theme === 'appearance' ? root.FFAppearance?.videoTheme() : null, theme: st.theme, ar: st.ar, q: st.q, fps: st.fps, dur: clamp(+st.dur || 20, 4, 300), pace: st.pace, hold: st.hold });
    function rankSide(k) {
      let h = '';
      if (k === 'rank') {
        h += `<label for="st-rm">Rank by</label>${sel('st-rm', Object.entries(RANK).map(([kk, v]) => [kk, v[0]]), st.rm)}`;
        h += `<div class="st-row"><div><label for="st-top">How many</label>${sel('st-top', [['5', 'Top 5'], ['10', 'Top 10'], ['15', 'Top 15'], ['20', 'Top 20']], st.top)}</div><div><label for="st-ord">Order</label>${sel('st-ord', [['desc', 'Highest first'], ['asc', 'Lowest first']], st.ord)}</div></div>`;
        h += `<label for="st-step">Steps</label>${sel('st-step', [['m', 'Month by month'], ['q', 'Quarter by quarter'], ['w', 'Week by week (prices only)']], st.step)}`;
        if (st.rm === 'ret') h += `<label for="st-win">Return over</label>${sel('st-win', [['1', '1 month'], ['3', '3 months'], ['6', '6 months'], ['12', '12 months'], ['36', '3 years'], ['ytd', 'Year to date']], st.win)}`;
        if (['om', 'nm', 'growth'].includes(st.rm)) h += `<label for="st-minrev">Minimum revenue a year ($B)</label><input class="input" id="st-minrev" inputmode="decimal" value="${esc(st.minrev)}">`;
      }
      h += `<label for="st-sec">Sector</label>${sel('st-sec', [['', 'Every sector']].concat(Object.entries(SECTORS)), st.sec)}`;
      h += `<div class="st-row"><div><label for="st-idx">Index</label>${sel('st-idx', [['', 'Any company on the site']].concat(Object.entries(IDX)), st.idx)}</div><div><label for="st-idxw">Members</label>${sel('st-idxw', [['then', 'At each step'], ['now', 'Today\'s']], st.idxw)}</div></div>`;
      h += `<label>Market value range ($B, blank = any)</label><div class="st-row"><div><input class="input" id="st-cmin" inputmode="decimal" placeholder="from" value="${esc(st.cmin)}" aria-label="Market value from"></div><div><input class="input" id="st-cmax" inputmode="decimal" placeholder="to" value="${esc(st.cmax)}" aria-label="Market value to"></div></div>`;
      h += `<label for="st-capby">Measured</label>${sel('st-capby', [['then', 'At each step (from 2009)'], ['now', 'Today']], st.capby)}`;
      h += `<div class="st-help">Every US-listed company the site draws, ranked again at each step. Today's companies only: those delisted, merged or bankrupt are missing from earlier years. “At each step” uses the S&P 500's and the Dow's membership history; the other indices keep theirs from when the site began.</div>`;
      return h;
    }
    function actualSide() {
      let h = `<label for="st-aw">Weight source</label>${sel('st-aw', [['index', 'Index (tracking ETF proxy)'], ['etf', 'ETF disclosed holdings'], ['13f', '13F manager holdings'], ['official', 'Officials: transaction composition']], st.aw)}`;
      if (st.aw === 'etf') h += `<label for="st-ah">ETF ticker</label><input class="input" id="st-ah" list="st-list" autocomplete="off" placeholder="SPY, QQQ, DIA" value="${esc(st.ah)}"><datalist id="st-list"></datalist>`;
      else if (st.aw === '13f') h += `<label for="st-ac">Manager CIK</label><input class="input" id="st-ac" value="${esc(st.ac)}"><div class="st-help">Berkshire: 1067983 · Bridgewater: 1350694 · Scion: 1649339</div>`;
      else if (st.aw === 'official') h += `<label for="st-ap">Official name (as disclosed)</label><input class="input" id="st-ap" value="${esc(st.ap)}"><label for="st-ao">Transactions</label>${sel('st-ao', [['all','All gross activity'],['buy','Purchases'],['sell','Sales']], st.ao)}`;
      else h += `<label for="st-at">Index</label>${sel('st-at', Object.entries(root.FFActual.TRACKERS).map(([k, v]) => [k, v[0] + ' · ' + v[1]]), st.at)}`;
      if (st.style === 'changes') h += `<label for="st-ag">Group changes</label>${sel('st-ag', [['company','Company'],['sector','Sector']], st.ag)}`;
      h += `<label for="st-an">Top holdings shown</label>${sel('st-an', [['5', '5'], ['10', '10'], ['12', '12'], ['15', '15'], ['20', '20']], st.an)}`;
      return h + '<div class="st-help">ETF NAV weights; 13F reported-value weights; officials show monthly transaction lower-bound shares, NOT holdings. Source dates are retained; official transaction charts use month-end buckets. Index mode uses a TRACKING ETF PROXY, not licensed official index files. Dow 30 is price-weighted, never market-cap-weighted. Dates before the first actual snapshot cannot be animated.</div>';
    }
    function holdingsSide() {
      let h = '<label for="st-hsrc">Disclosure source</label>' +
        sel('st-hsrc', [['13f', 'Popular SEC 13F managers'], ['officials', 'Public officials / PTR transactions']], st.hsrc);
      h += '<label for="st-hid">' + (st.hsrc === 'officials' ? 'Official (name or slug)' : '13F manager (name or CIK)') + '</label>' +
        '<input class="input" id="st-hid" value="' + esc(st.hid) + '" list="st-hlist" placeholder="Blank = featured filer" autocomplete="off"><datalist id="st-hlist"></datalist>';
      h += '<label for="st-hv">Weights</label>' +
        sel('st-hv', st.hsrc === 'officials' ?
          [['company', 'Estimated company trade-size mix'], ['sector', 'Estimated sector trade-size mix']] :
          [['company', 'Actual company weights (13F)'], ['sector', 'Actual sector weights (13F)']], st.hv);
      h += '<label for="st-an">Top rows shown</label>' +
        sel('st-an', [['5','5'],['10','10'],['12','12'],['15','15'],['20','20']], st.an);
      h += '<div class="st-help">' + (st.hsrc === '13f' ?
        'SEC 13F: actual reported position values divided by the ENTIRE disclosed 13F total, never rescaled to top holdings. Missing holdings remain uncovered; reports lag quarter end.' :
        'Officials: PTR trades are ranges, not a current portfolio. Finite range midpoints give an ESTIMATED transaction mix, not actual portfolio weights.') +
        ' One reported date only: no invented price, history or share counts.</div>';
      return h;
    }
    function moreSide(k) {
      const meas = Object.entries(RANK).filter(([kk]) => !['gp', 'oi', 'ni'].includes(kk)).map(([kk, v]) => [kk, v[0]]);
      let h = '';
      if (k === 'bubble') {
        h += `<div class="st-row"><div><label for="st-bx">Across (x)</label>${sel('st-bx', meas, st.bx)}</div><div><label for="st-by">Up (y)</label>${sel('st-by', meas, st.by)}</div></div>`;
        h += `<div class="st-row"><div><label for="st-bs">Bubble size</label>${sel('st-bs', Object.entries(BUB_SIZE), st.bs)}</div><div><label for="st-bn">How many</label>${sel('st-bn', [['10', '10'], ['25', '25'], ['50', '50']], st.bn)}</div></div>`;
        h += `<label for="st-bt">Or these companies (tickers, blank = the largest)</label><input class="input" id="st-bt" value="${esc(st.bt)}" placeholder="AAPL, MSFT, NVDA">`;
        if (st.bx === 'ret' || st.by === 'ret') h += `<label for="st-win">Return over</label>${sel('st-win', [['3', '3 months'], ['6', '6 months'], ['12', '12 months'], ['36', '3 years'], ['ytd', 'Year to date']], st.win)}`;
      }
      if (k === 'treemap') h += `<div class="st-row"><div><label for="st-tn">How many</label>${sel('st-tn', [['25', '25'], ['50', '50'], ['100', '100']], st.tn)}</div><div><label for="st-tc">Colour</label>${sel('st-tc', [['ret', '12-month return'], ['sector', 'Sector']], st.tc)}</div></div>`;
      if (k === 'sectors') {
        h += `<label for="st-sw">Weights</label>${sel('st-sw', [['index', 'As the index weights them (Dow: by share price)'], ['cap', 'By market value'], ['fund', 'A fund\'s actual holdings']], st.sw)}`;
        if (st.sw === 'fund') return h + `<label for="st-sf">Fund (ETF ticker)</label><input class="input" id="st-sf" value="${esc(st.sf)}" placeholder="DIA, QQQ, XLK, SCHD">`
          + `<div class="st-help">The fund's latest reported holdings and their weights; earlier months move each holding with its own price, as if the fund had kept the same shares.</div>`;
        h += `<label for="st-sa">Show</label>${sel('st-sa', [['share', 'Each sector\'s share (100%)'], ['abs', 'Market value in dollars']], st.sa)}`;
      }
      if (k !== 'sectors') h += `<label for="st-sec">Sector</label>${sel('st-sec', [['', 'Every sector']].concat(Object.entries(SECTORS)), st.sec)}`;
      h += `<div class="st-row"><div><label for="st-idx">Index</label>${sel('st-idx', [['', 'Any company on the site']].concat(Object.entries(IDX)), st.idx)}</div><div><label for="st-idxw">Members</label>${sel('st-idxw', [['then', 'At each step'], ['now', 'Today\'s']], st.idxw)}</div></div>`;
      h += `<label>Market value range ($B, blank = any)</label><div class="st-row"><div><input class="input" id="st-cmin" inputmode="decimal" placeholder="from" value="${esc(st.cmin)}" aria-label="Market value from"></div><div><input class="input" id="st-cmax" inputmode="decimal" placeholder="to" value="${esc(st.cmax)}" aria-label="Market value to"></div></div>`;
      return h + `<div class="st-help">From the site's month-by-month data on every company it draws. Market values start with each company's first XBRL filing (2009–2011: every filer from mid-2011), so a market-value video is best started in 2012. Today's companies only: those delisted, merged or bankrupt are missing from earlier years.</div>`;
    }
    function side() {
      const k = st.k, styles = STYLES[k];
      let h = `<h3>Video</h3><div class="st-pills">${KINDS.map(([v, l]) => `<button type="button" class="pill${v === k ? ' on' : ''}" data-kind="${v}">${esc(l)}</button>`).join('')}</div>`;
      if (k === 'rank' || k === 'dist') h += rankSide(k);
      else if (k === 'bubble' || k === 'treemap' || k === 'sectors') h += moreSide(k);
      else if (k === 'actual') h += actualSide();
      else if (k === 'holdings') h += holdingsSide();
      else if (k !== 'formula') {
        const one = k === 'calendar' || k === 'sankey' || k === 'timing';
        const lbl = { fund: 'Companies (tickers)', sankey: 'Company (ticker)', calendar: 'Ticker — an ETF or a stock', timing: 'Ticker — an index fund or a stock', snowball: 'Dividend payers (up to three)' }[k] || 'Tickers — ETFs or stocks, two or more';
        const ph = { fund: 'NVDA, AMD', sankey: 'NVDA', calendar: 'NVDA', timing: 'SPY', snowball: 'SCHD, KO' }[k] || 'QQQ, SPY, SCHD';
        h += `<label for="st-t">${lbl}</label><input class="input" id="st-t" value="${esc(one ? tickers(st)[0] || '' : st.t)}" placeholder="${ph}" list="st-list" autocomplete="off"><datalist id="st-list"></datalist>`;
        if (k === 'sankey') h += `<label for="st-sm">Quarters</label>${sel('st-sm', [['detail', 'The detailed flow (the latest quarters on file)'], ['long', 'Ten years: revenue → profit → earnings']], st.sm)}`;
        if (k === 'timing') h += `<label for="st-yb">Money each year ($)</label><input class="input" id="st-yb" inputmode="numeric" value="${esc(st.yb)}"><div class="st-help">Each year's money goes in at that year's highest close (bought at the top), its lowest (perfect timing), its first week, or spread over its months — with hindsight, to show what timing is worth.</div>`;
        if (k === 'snowball') {
          const solving = +st.sgoal > 0, solveLump = st.ssolve !== 'rec';
          h += '<label for="st-amt">' + (solving && solveLump ? 'Starting amount (calculated from goal)' : 'Amount to start with ($)') +
            '</label><input class="input" id="st-amt" inputmode="decimal" value="' +
            (solving && solveLump ? '' : esc(st.amt)) + '" placeholder="' +
            (solving && solveLump ? 'Calculated separately for each ticker' : '10000') + '"' + (solving && solveLump ? ' disabled' : '') + '>';
          h += '<label for="st-rec">' + (solving && !solveLump ? 'Scheduled buy (calculated from goal)' : 'Buy again on a schedule (optional)') +
            '</label><div class="st-row"><div><input class="input" id="st-rec" inputmode="decimal" placeholder="' +
            (solving && !solveLump ? 'Calculated per ticker' : '$ each time') + '" value="' +
            (solving && !solveLump ? '' : (+st.rec > 0 ? esc(st.rec) : '')) +
            '" aria-label="Amount each time"' + (solving && !solveLump ? ' disabled' : '') +
            '></div><div style="flex:.7"><input class="input" id="st-ri" type="number" min="1" max="60" value="' +
            esc(st.ri) + '" aria-label="Every how many"></div><div>' +
            sel('st-ru', [['w', 'weeks'], ['m', 'months'], ['y', 'years']], st.ru) + '</div></div>';
        }
      }
      else h += `<label for="st-expr">Formulas — one per line, “Label: expression”</label><textarea id="st-expr" spellcheck="false">${esc(st.expr)}</textarea><div class="st-help">Operators <code>+ − × ÷ ^</code> and <code>( )</code>; functions <code>log exp sqrt abs rebase(x) ma(x,n) ema(x,n) pct(x,n) chg(x,n) lag(x,n) min(a,b) max(a,b)</code>. Series: a ticker (<code>QQQ</code> = total return) or <code>QQQ.price</code>, <code>.div</code>, <code>.yield</code>, company figures <code>NVDA.revenue</code>, <code>.ni_ttm</code>, <code>.margin</code>… Example: <code>rebase(QQQ/SPY)</code>, <code>SCHD.yield*100</code>, <code>NVDA.ni_ttm/NVDA.revenue_ttm</code>.</div>`;
      if (k !== 'holdings') h += `<div class="st-row"><div><label for="st-from">From</label><input class="input" type="date" id="st-from" value="${esc(st.from)}"></div><div><label for="st-to">To</label><input class="input" type="date" id="st-to" value="${esc(st.to)}"></div></div>`;
      h += `<div class="st-row" style="margin-top:6px;align-items:center"><div class="st-pills" style="flex:2">${[['1y', 1], ['3y', 3], ['5y', 5], ['10y', 10], ['Max', 30]].map(([l, y]) => `<button type="button" class="pill" data-yrs="${y}">${l}</button>`).join('')}</div>`
        + `<div><input class="input" id="st-yrs" inputmode="decimal" placeholder="or N years" value="${+st.yrs > 0 ? esc(st.yrs) : ''}" aria-label="The last N years (any number, e.g. 7 or 2.5)"></div></div>`;
      if (k === 'snowball') {
        const reverse = +st.sgoal > 0, solveLump = st.ssolve !== 'rec';
        h += '<label for="st-sgoal">Terminal dividend income goal ($, optional)</label>' +
          '<input class="input" id="st-sgoal" type="number" min="0" step="1" inputmode="decimal" value="' +
          esc(st.sgoal) + '" placeholder="e.g. 1000">';
        h += '<label for="st-sunit">Income target frequency</label>' +
          sel('st-sunit', [['monthly','Monthly income equivalent ($/month)'], ['annual','Annual gross dividends ($/year)']], st.sunit);
        h += '<label for="st-ssolve">Reverse-calculate</label>' +
          sel('st-ssolve', [['lump','Required starting investment'], ['rec','Required amount at each scheduled buy']], st.ssolve);
        h += '<div class="st-help">' + (reverse ?
          (solveLump ? 'The starting amount is calculated; scheduled buys remain fixed.' :
            'The scheduled buy amount is calculated; starting capital remains fixed.') :
          'Leave the target blank to simulate using your selected starting capital and recurring buys.') +
          ' Uses actual historical distributions, reinvested, with final 52 weeks of dividends / 12 as monthly equivalent. Not a guaranteed forward dividend.</div>';
      }
      if (k === 'snowball') h += '<label for="st-scf">Dividend cash-flow chart</label>' + sel('st-scf', [['monthly', 'Monthly (trailing 24 months)'], ['annual', 'Annual (full history)']], st.scf);
      if (k === 'growth') {
        const L = growthLabels(st);
        h += `<label for="st-goal">End value to reach ($, optional)</label><input class="input" id="st-goal" inputmode="numeric" placeholder="e.g. 1000000 — works out what it took" value="${+st.goal > 0 ? esc(st.goal) : ''}">`
          + `<label for="st-solve">With an end value, work out</label>${sel('st-solve', [['rec', 'The amount each time (on the schedule below)'], ['lump', 'The amount at the start']], st.solve)}`;
        h += `<label for="st-amt">${L.amt}</label><input class="input" id="st-amt" inputmode="numeric" value="${esc(st.amt)}">`;
        h += `<label for="st-rec">${L.rec}</label><div class="st-row"><div><input class="input" id="st-rec" inputmode="numeric" placeholder="$ each time" value="${+st.rec > 0 ? esc(st.rec) : ''}" aria-label="Amount each time"></div>`
          + `<div style="flex:.7"><input class="input" id="st-ri" type="number" min="1" max="60" value="${esc(st.ri)}" aria-label="Every how many"></div><div>${sel('st-ru', [['d', 'trading days'], ['w', 'weeks'], ['m', 'months'], ['y', 'years']], st.ru)}</div></div>`
          + `<div class="st-help" id="st-goal-help">${L.help}</div>`;
        h += `<label for="st-div">Dividends</label>${sel('st-div', [['tr', 'Reinvested (total return)'], ['split', 'Taken as cash: their own line'], ['price', 'Left out (price only)']], st.div)}`;
        if (st.div === 'tr') h += `<label for="st-dinc">Dividends paid, in dollars as paid</label>${sel('st-dinc', [['label', 'On the labels and the end card'], ['panel', 'Also their own panel (line race)'], ['off', 'Not on the video (in the results only)']], st.dinc)}`;
        if (st.div === 'split' || (st.div === 'tr' && st.dinc === 'panel')) h += `<label for="st-dview">The dividends panel (line race) shows</label>${sel('st-dview', [['total', 'The running total'], ['year', 'Each calendar year, as bars']], st.dview)}`;
        h += `<label for="st-scale">Scale</label>${sel('st-scale', [['lin', 'Linear'], ['log', 'Logarithmic']], st.scale)}`;
        // adjustments: a tax on dividends, cash, inflation, a discount rate for present values
        h += `<h3>Adjust</h3><label for="st-dtax">Tax on dividends (%)</label><input class="input" id="st-dtax" inputmode="decimal" value="${esc(st.dtax)}" placeholder="0 — before tax">`
          + `<div class="st-row"><div><label for="st-cashl">Compare with cash</label>${sel('st-cashl', [['0', 'No'], ['1', 'Yes: a cash line']], st.cashl)}</div><div><label for="st-cashr">Cash rate, %/yr</label><input class="input" id="st-cashr" inputmode="decimal" value="${esc(st.cashr)}" placeholder="T-bills, actual"></div></div>`
          + (st.div === 'split' ? `<label for="st-dint">Dividends taken as cash</label>${sel('st-dint', [['0', 'Kept as cash, no interest'], ['1', 'Earn interest at the cash rate']], st.dint)}` : '')
          + `<div class="st-row"><div><label for="st-infl">Inflation</label>${sel('st-infl', [['none', 'Not adjusted'], ['line', 'A line keeping up with prices'], ['real', 'Every value after inflation']], st.infl)}</div><div><label for="st-inflr">Inflation, %/yr</label><input class="input" id="st-inflr" inputmode="decimal" value="${esc(st.inflr)}" placeholder="CPI, actual"></div></div>`
          + `<label for="st-disc">Discount rate for present value, %/yr</label><input class="input" id="st-disc" inputmode="decimal" value="${esc(st.disc)}" placeholder="blank: none (shown in the results)">`
          + `<div class="st-help">A blank rate uses history: the 3-month Treasury bill for cash, the consumer price index for inflation. Cash and inflation take the same money on the same dates, grown at that rate (its future value); after inflation, every value is in dollars of the start; present value discounts each end value back to the start.</div>`;
      }
      if (k === 'snowball') h += `<label for="st-dtax">Tax on dividends (%)</label><input class="input" id="st-dtax" inputmode="decimal" value="${esc(st.dtax)}" placeholder="0 — before tax">`;
      if (k === 'rrg') h += `<div class="st-row"><div><label for="st-bench">Benchmark</label><input class="input" id="st-bench" value="${esc(st.bench)}"></div><div><label for="st-tail">Tail (weeks)</label>${sel('st-tail', [['5', '5'], ['8', '8'], ['10', '10'], ['13', '13'], ['26', '26']], st.tail)}</div></div><label for="st-n">RS window</label>${sel('st-n', [['10', '10 weeks'], ['14', '14 weeks'], ['26', '26 weeks']], st.n)}`;
      if (k === 'momentum') h += `<div class="st-row"><div><label for="st-bench">Against</label><input class="input" id="st-bench" value="${esc(st.bench)}"></div><div><label for="st-lb">Look-back</label>${sel('st-lb', [['13', '13 weeks'], ['26', '26 weeks'], ['52', '52 weeks']], st.lb)}</div></div>`;
      if (k === 'fund') h += `<label for="st-m">Figure</label>${sel('st-m', Object.entries(FIG), st.m)}<label for="st-ttm">Periods</label>${sel('st-ttm', [['0', 'Each quarter'], ['1', 'Trailing four quarters']], st.ttm)}`;
      h += `<h3>Look</h3><label for="st-style">Style</label>${sel('st-style', styles, st.style)}<label for="st-theme">Theme</label>${sel('st-theme', Object.entries(THEMES).map(([kk, v]) => [kk, v.name]), st.theme)}`;
      h += `<div class="st-row"><div><label for="st-ar">Shape</label>${sel('st-ar', [['16x9', '16:9 landscape'], ['9x16', '9:16 phone'], ['1x1', '1:1 square']], st.ar)}</div><div><label for="st-q">Size</label>${sel('st-q', [['1080', '1080p'], ['720', '720p (faster)']], st.q)}</div></div>`;
      h += `<label for="st-dur">Length and speed</label><div class="st-row"><div><input class="input" id="st-dur" type="number" min="4" max="300" step="1" value="${esc(st.dur)}" aria-label="Length in seconds"></div><div class="st-pills" style="flex:1.6;align-items:center">`
        + [['0.5', 'Slower'], ['2', 'Faster']].map(([v, l]) => `<button type="button" class="pill" data-speed="${v}">${l}</button>`).join('') + `</div></div>`
        + `<div class="st-help" id="st-pace-note"></div>`
        + `<div class="st-row"><div><label for="st-pace">Pace</label>${sel('st-pace', PACES, st.pace)}</div><div><label for="st-hold">Pause at the end</label>${sel('st-hold', [['auto', 'Auto'], ['0', 'None'], ['2', '2 s'], ['4', '4 s'], ['6', '6 s']], st.hold)}</div></div>`
        + `<label for="st-fps">Smoothness</label>${sel('st-fps', [['30', '30 fps'], ['60', '60 fps']], st.fps)}`;
      h += `<label for="st-title">Title (blank: written for you)</label><input class="input" id="st-title" value="${esc(st.title)}" placeholder="${esc((V && V.title) || '')}"><label for="st-sub">Subtitle</label><input class="input" id="st-sub" value="${esc(st.sub)}" placeholder="${esc((V && V.sub) || '')}">`;
      h += `<label for="st-end">End card</label>${sel('st-end', [['1', 'The result, ranked'], ['0', 'None']], st.end)}`;
      $('#st-side').innerHTML = h;
    }
    function relabel() {
      const L = growthLabels(st), a = app.querySelector('label[for="st-amt"]'), r = app.querySelector('label[for="st-rec"]'), hp = $('#st-goal-help');
      if (a) a.textContent = L.amt; if (r) r.textContent = L.rec; if (hp) hp.textContent = L.help;
    }
    function save() { try { history.replaceState(null, '', '#' + serialize(st)); } catch (e) { /* file:// */ } }
    function status() {
      if (!V) return;
      const tm = timing(V, opt()), per = (V.grid.length - 1) / tm.run, unit = V.yearly ? 'years' : V.quarterly ? 'quarters' : V.kind === 'rank' && st.step === 'm' || ['calendar', 'bubble', 'treemap', 'sectors'].includes(V.kind) ? 'months' : 'weeks';
      const what = V.actual ? (' ' + (V.group || 'holdings')) : ['rank', 'bubble', 'treemap'].includes(V.kind) ? ' companies' : V.kind === 'sectors' ? ' sectors' : V.kind === 'timing' ? ' plans' : ' series';
      $('#st-status').textContent = V.actual && V.actual.fallback === 'single-disclosure'
        ? 'Only one real disclosure available · showing dated holdings, NOT weight changes · ' + V.series.length + what + ' · ' + tm.D + ' s'
        : V.actual ? `${V.series.length + what} · ${V.grid.length} actual dated snapshot${V.grid.length === 1 ? '' : 's'} · ${tm.D} s${V.grid.length === 1 ? ' (single-date card)' : ' (transitions illustrative)'}`
        : `${V.series.length + what} · ${V.grid.length} ${unit} · ${tm.D} s (${per >= 10 ? Math.round(per) : per.toFixed(1)} ${unit} a second)`;
      const pn = $('#st-pace-note'); if (pn) pn.textContent = V.actual ? (V.grid.length === 1 ? 'One disclosed/observed date · no invented historical movement.' : 'Transitions between observed dates are visual only, not daily observations.') : `About ${per >= 10 ? Math.round(per) : per.toFixed(1)} ${unit} a second.`;
    }
    function sizeCanvas() {
      const dim = { '16x9': [1280, 720], '9x16': [720, 1280], '1x1': [960, 960] }[st.ar] || [1280, 720];
      if (canvas.width !== dim[0] || canvas.height !== dim[1]) { canvas.width = dim[0]; canvas.height = dim[1]; }
    }
    function paint() { if (V) draw(ctx, canvas.width, canvas.height, V, opt(), tNow); }
    const appearanceChanged = () => {
      if (!document.body.contains(canvas)) { root.removeEventListener('ff:appearancechange', appearanceChanged); return; }
      if (exporting) return;
      if (root.FFAppearance?.videoTheme()) st.theme = 'appearance';
      else if (st.theme === 'appearance') st.theme = originalTheme;
      const picker = $('#st-theme'); if(picker)picker.value=st.theme;
      if (!exporting) { paint(); if (V) showReport(); }
    };
    root.addEventListener('ff:appearancechange', appearanceChanged);
    function loop(ts) {
      if (!playing) return;
      tNow = (ts - t0) / 1000;
      const D = timing(V, opt()).D;
      if (tNow >= D) { tNow = D; playing = false; $('#st-play').textContent = '▶ Play'; }
      paint();
      if (playing) raf = requestAnimationFrame(loop);
    }
    function play() { if (!V) return; if (tNow >= timing(V, opt()).D - 0.01) tNow = 0; playing = true; t0 = performance.now() - tNow * 1000; $('#st-play').textContent = '❚❚ Pause'; cancelAnimationFrame(raf); raf = requestAnimationFrame(loop); }
    function pause() { playing = false; cancelAnimationFrame(raf); $('#st-play').textContent = '▶ Play'; }
    async function rebuild(autoplay) {
      const my = ++token;
      save(); sizeCanvas();
      $('#st-status').textContent = 'Loading the data…';
      try {
        const v = await build(st);
        if (my !== token || !here()) return;
        v.style = st.style; v.scale = st.scale; v.endCard = st.end === '1'; v.dinc = st.dinc; v.dview = st.dview;
        finish(v, st);
        V = v;
        status();
        showReport();
        const ti = $('#st-title'), su = $('#st-sub'); if (ti) ti.placeholder = V.title; if (su) su.placeholder = V.sub;
        tNow = autoplay ? 0 : timing(V, opt()).D * 0.62;
        paint();
        if (autoplay) play();
      } catch (e) {
        if (my !== token) return;
        V = null; pause();
        ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#e8eef7'; ctx.font = '600 28px "IBM Plex Sans", Arial'; ctx.textAlign = 'center'; ctx.fillText(e.message, canvas.width / 2, canvas.height / 2);
        $('#st-status').textContent = e.message; const rp = $('#st-rep'); rp.hidden = true; rp.innerHTML = '';
      }
    }
    const themeOf = () => (st.theme === 'appearance' ? root.FFAppearance?.videoTheme() : THEMES[st.theme]) || THEMES.bull;
    function showReport() {
      const box = $('#st-rep');
      let R = null;
      try { R = report(V); } catch (e) { console.error('studio report', e); }
      V._report = R;
      if (!R) { box.hidden = true; return; }
      box.innerHTML = reportHTML(R, themeOf());
      box.hidden = false;
    }
    const linkOf = () => location.href.split('#')[0] + '#' + serialize(st);
    function copyText(text, btn) {
      const done = () => { const was = btn.textContent; btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = was; }, 1600); };
      const fallback = () => { const ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;left:-9999px;top:0'; document.body.appendChild(ta); ta.select(); let okc = false; try { okc = document.execCommand('copy'); } catch (e) { /* none */ } ta.remove(); if (okc) done(); else prompt('Copy this', text.length > 2000 ? text.slice(0, 2000) : text); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
    }
    $('#st-rep').addEventListener('click', (e) => {
      const b = e.target.closest('[data-rep]'); if (!b || !V || !V._report) return;
      const R = V._report, what = b.dataset.rep;
      if (what === 'copy') copyText(reportText(R, linkOf()), b);
      else if (what === 'cap') copyText(R.caption, b);
      else if (what === 'csv') download(new Blob([csvOf(V, R)], { type: 'text/csv;charset=utf-8' }), fileStem(V) + '.csv');
      else if (what === 'ycsv') download(new Blob([yearsCSV(R)], { type: 'text/csv;charset=utf-8' }), fileStem(V) + '-dividends-by-year.csv');
      else if (what === 'png') {                              // this frame, at the size of the video
        const dim = { '16x9': [1920, 1080], '9x16': [1080, 1920], '1x1': [1080, 1080] }[st.ar] || [1920, 1080], c = document.createElement('canvas');
        c.width = dim[0]; c.height = dim[1];
        draw(c.getContext('2d'), c.width, c.height, V, opt(), tNow);
        c.toBlob((blob) => { if (blob) download(blob, fileStem(V) + '.png'); }, 'image/png');
      }
    });
    async function suggest() {
      const list = $('#st-list'); if (!list || list.dataset.done) return; list.dataset.done = '1';
      const [ix, ex] = await Promise.all([json(SITE + 'index.json'), st.k === 'fund' ? null : json(HUB + 'etf/index.json')]);
      const opts = [];
      if (ex && ex.rows) { const F = ex.fields, si = F.indexOf('symbol'), ni = F.indexOf('name'), ai = F.indexOf('aum'); ex.rows.slice().sort((a, b) => (b[ai] || 0) - (a[ai] || 0)).slice(0, 1500).forEach((r) => opts.push([r[si], r[ni]])); }
      ((ix && ix.companies) || []).slice().sort((a, b) => (b.revenue || 0) - (a.revenue || 0)).slice(0, 1500).forEach((c) => c.ticker && opts.push([c.ticker, c.name]));
      list.innerHTML = opts.map(([s, n]) => `<option value="${esc(s)}">${esc(n || '')}</option>`).join('');
    }
    async function suggestHoldings() {
      const list = $('#st-hlist');
      if (!list) return;
      const doc = await json(HUB + 'research/people/' + (st.hsrc === 'officials' ? 'officials' : 'managers') + '.json');
      if (!list.isConnected || !doc || !Array.isArray(doc.rows)) return;
      const rows = st.hsrc === 'officials' ?
        root.FFHoldingsVideo.popularOfficials(doc) : root.FFHoldingsVideo.popularManagers(doc);
      list.innerHTML = rows.slice(0, 150).map(r =>
        '<option value="' + esc(st.hsrc === 'officials' ? r.slug : r.cik) + '">' + esc(r.name) + '</option>').join('');
    }
    const box = app.querySelector('.st-wrap');
    let tmr = 0;
    const later = (f) => { clearTimeout(tmr); tmr = setTimeout(f, 450); };
    box.addEventListener('click', (e) => {
      const kb = e.target.closest('[data-kind]');
      if (kb) {
        st.k = kb.dataset.kind; st.style = STYLES[st.k][0][0]; st.title = ''; st.sub = '';
        if ((st.k === 'fund' || st.k === 'calendar' || st.k === 'sankey') && !/^[A-Z]/.test(st.t)) st.t = 'NVDA';
        if (st.k === 'snowball' && st.t === DEF.t) st.t = 'SCHD';
        if (st.k === 'timing' && st.t === DEF.t) st.t = 'SPY';
        if (st.k === 'sankey') st.theme = 'clean';
        if (st.k === 'actual' || st.k === 'holdings') { st.style = 'bars'; st.from = ''; st.to = ''; st.yrs = ''; }
        side(); rebuild(); return;
      }
      const yb = e.target.closest('[data-yrs]');
      if (yb) { st.from = iso(Date.now() - (+yb.dataset.yrs) * 365.25 * DAY); st.to = ''; st.yrs = ''; side(); rebuild(); }
      const sb = e.target.closest('[data-speed]');
      if (sb) { st.dur = String(clamp(Math.round((+st.dur || 20) / +sb.dataset.speed), 4, 300)); const d = $('#st-dur'); if (d) d.value = st.dur; if (V) { paint(); save(); status(); } }
    });
    box.addEventListener('focusin', (e) => { if (e.target.id === 'st-t' || e.target.id === 'st-ah') suggest(); if (e.target.id === 'st-hid') suggestHoldings(); });
    box.addEventListener('input', (e) => {
      const id = e.target.id; if (!id || !id.startsWith('st-') || e.target.tagName === 'SELECT') return;
      const key = id.slice(3); if (!(key in DEF)) return;
      st[key] = e.target.value;
      if (key === 'title' || key === 'sub') { if (V) { V.title = st.title || V._title; V.sub = st.sub || V._sub; paint(); save(); } return; }
      if (LOOK.includes(key)) { if (V) { paint(); save(); status(); } return; }
      if (['rec', 'goal'].includes(key)) relabel();
      if (key === 'yrs' && +st.yrs > 0) { st.from = ''; const d = $('#st-from'); if (d) d.value = ''; }
      later(() => rebuild());
    });
    box.addEventListener('change', (e) => {
      const id = e.target.id; if (!id || !id.startsWith('st-')) return;
      const key = id.slice(3); if (!(key in DEF) || e.target.tagName === 'INPUT' && e.target.type !== 'date') return;
      st[key] = e.target.value;
      if (key === 'hsrc') { st.hid = ''; }
      if (key === 'from') { st.yrs = ''; const y = $('#st-yrs'); if (y) y.value = ''; }
      if (key === 'solve') relabel();
      // Actual weight bars and sector areas require distinct portfolios, not just a repaint.
      if (key === 'style' && st.k === 'actual') { side(); rebuild(); return; }
      if (LOOK.includes(key)) {
        if (V) { V.style = st.style; V.scale = st.scale; V.endCard = st.end === '1'; V.dinc = st.dinc; V.dview = st.dview; delete V._dom; sizeCanvas(); paint(); save(); status(); if (key === 'theme') showReport(); if (key === 'dinc') side(); }
        else rebuild();
        return;
      }
      if (key === 'rm' || key === 'bx' || key === 'by' || key === 'sw' || key === 'aw' || key === 'hsrc' || key === 'ssolve' || key === 'sgoal' || key === 'div') side();
      rebuild();
    });
    const tplAll = (on) => { const g = $('#st-tpl'), b = $('#st-tpl-all'); g.classList.toggle('all', on); b.setAttribute('aria-expanded', String(on)); b.textContent = on ? 'Fewer ▴' : `All ${TEMPLATES.length} ▾`; };
    $('#st-tpl-all').addEventListener('click', () => tplAll(!$('#st-tpl').classList.contains('all')));
    app.querySelector('#st-tpl').addEventListener('click', (e) => {
      const b = e.target.closest('[data-tpl]'); if (!b) return;
      Object.assign(st, DEF, TEMPLATES[+b.dataset.tpl].s); side(); rebuild(true);
      tplAll(false);
      app.querySelector('.st-stage').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    $('#st-play').addEventListener('click', () => (playing ? pause() : play()));
    $('#st-restart').addEventListener('click', () => { tNow = 0; play(); });
    $('#st-link').addEventListener('click', () => copyText(linkOf(), $('#st-link')));
    $('#st-export').addEventListener('click', async () => {
      if (exporting) { cancelReq = true; $('#st-status').textContent = 'Cancelling…'; return; }
      if (!V) return;
      exporting = true; cancelReq = false; pause();
      const btn = $('#st-export'), prog = $('#st-prog'), began = performance.now(); btn.textContent = 'Cancel'; btn.classList.remove('primary'); prog.hidden = false;
      const set = (p) => {
        prog.firstElementChild.style.width = (100 * p).toFixed(1) + '%';
        const spent = (performance.now() - began) / 1000, left = p > 0.03 ? spent * (1 - p) / p : null;
        $('#st-status').textContent = `Rendering ${Math.round(100 * p)}%` + (left != null && left >= 2 && p < 1 ? ` · about ${left < 90 ? Math.ceil(left) + ' s' : Math.round(left / 60) + ' min'} left` : '') + '…';
      };
      const stop = () => !here() || cancelReq;
      try {
        let r = await exportMp4(V, opt(), set, stop);
        if (!r) { $('#st-status').textContent = 'Recording the preview in real time (this browser has no video encoder)…'; r = await recordPreview(canvas, V, opt(), set, stop); }
        if (r === 'cancelled') { if (here()) $('#st-status').textContent = 'Export cancelled'; return; }
        const name = fileStem(V) + '.' + (r.blob.type.includes('mp4') ? 'mp4' : 'webm');
        download(r.blob, name);
        $('#st-status').textContent = `Saved ${name} · ${(r.blob.size / 1e6).toFixed(1)} MB${r.w ? ` · ${r.w}×${r.h}, ${r.fps} fps, ${r.codec}` : ''} · made in ${Math.round((performance.now() - began) / 1000)} s`;
        root.FFStudio._last = r;
      } catch (err) {
        $('#st-status').textContent = 'The video could not be made: ' + err.message;
      } finally { exporting = false; cancelReq = false; btn.textContent = 'Export MP4 ↓'; btn.classList.add('primary'); prog.hidden = true; }
    });
    side();
    await rebuild(false);
  }

  // the growth form's labels: what each amount means with and without an end value to reach
  function growthLabels(st) {
    const goal = +st.goal > 0, lump = st.solve === 'lump', dca = +st.rec > 0;
    if (goal && lump) return { amt: 'Amount to start with — worked out from the end value', rec: 'Also buy on a schedule (optional, kept as typed)', help: `The sum at the start that would have ended at ${money(+st.goal, 0)}, for each ticker — with the scheduled buys, if any, on top.` };
    if (goal) return { amt: 'Amount to start with ($, can be 0, kept as typed)', rec: 'Buy on a schedule — the amount each time is worked out', help: `The same amount every time, on the schedule here, that would have ended at ${money(+st.goal, 0)}, for each ticker. Set how often (every 1 month, 2 weeks…).` };
    return { amt: dca ? 'Amount to start with ($, can be 0)' : 'Amount invested ($)', rec: 'Buy again on a schedule (optional)', help: 'e.g. $500 every 1 month: the same amount bought at that week\'s close, from the start date on. Or set an end value above to work out the amount.' };
  }
  // titles typed by the reader replace the written ones; the written ones stay to fall back on; "the last N years" sets the start
  async function build(st) {
    if (+st.yrs > 0) { const end = st.to ? Date.parse(st.to + 'T00:00:00Z') : Date.now(); st = Object.assign({}, st, { from: iso(end - (+st.yrs) * 365.25 * DAY) }); }
    const V = await buildRaw(st); V._title = V.title; V._sub = V.sub; if (st.title) V.title = st.title; if (st.sub) V.sub = st.sub; return V; }

  root.FFStudio = { render, _t: { tokenize, parse, evaluate, formulas, ids, figure, weeklyGrid, asof, divsOn, divTTM, trOn, priceOn, rrgXY, build, finish, draw, timing, frameIndex, parseState, serialize, exportMp4, money, THEMES, TEMPLATES, buySchedule, xirr, historyPx, squarify, report, reportText, csvOf, yearsCSV, worstDrop, calYears, netTR, growIdx, monthlyOn, resetMacro: () => { MACRO = null; }, resetPanel: () => PANEL.clear() } };
  if (typeof module !== 'undefined') module.exports = root.FFStudio;
})(typeof globalThis !== 'undefined' ? globalThis : this);
