/* Momentum factors for one stock or ETF — the history of absolute, relative and composite momentum, computed in the
   browser from weekly total-return closes by the formulas of app/momentum.py, with the monthly cross-sectional ranks the
   builds publish.
     closes   data/market/history/rrg.json (the Friday grid, SPY, the sector and style ETFs), history/t/<T>.json (a company,
              branch rotation-history); any other ETF from data/etf/px/<T>.json (Yahoo's weekly bars, moved to their Friday)
     ranks    history/momentum/<T>.json (a company among the site's companies), data/etf/momentum/<T>.json (an ETF among
              the ETFs that are neither leveraged nor inverse, and inside its asset class): one row per month end from m0
   Shared by the Hub's Momentum tab (momentum.js), the company page's "Momentum factors" view (views.json) and the ETF
   page (etf.js). window.MomentumView.render(el, {ticker, hub, here}) — hub: the path to the hub ('disclosures/' on the
   Sankey site, '' inside it). The pure functions are exported for tests/test_momentum_view.cjs. */
(function (root) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const pct = (v, d) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d == null ? 1 : d) + '%' : '—');
  const ord = (k) => { const v = Math.round(k), t = v % 100; return v + (t >= 11 && t <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][v % 10] || 'th'); };
  const sig = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2) + 'σ' : '—');
  const W_MONTH = 4, W_QUARTER = 13, W_HALF = 26, W_YEAR = 52, HORIZONS = [13, 26, 52];
  const VOL_FLOOR = 0.004;          // the weekly volatility floor of the composite and the vol-scaled 12-1 (app/momentum.py)
  /* ---- the factors (app/momentum.py: Prep, composite, factor_at) ---- */
  const ln = (x) => (x != null && x > 0 ? Math.log(x) : null);
  function prep(c) {
    const n = c.length, logs = c.map(ln), s1 = new Float64Array(n + 1), s2 = new Float64Array(n + 1), cnt = new Int32Array(n + 1);
    for (let i = 0; i < n; i++) {
      const r = i && logs[i] != null && logs[i - 1] != null ? logs[i] - logs[i - 1] : null;
      s1[i + 1] = s1[i] + (r != null ? r : 0); s2[i + 1] = s2[i] + (r != null ? r * r : 0); cnt[i + 1] = cnt[i] + (r != null ? 1 : 0);
    }
    return { c, logs, wsd(t) { const a = Math.max(1, t - W_YEAR + 1), k = cnt[t + 1] - cnt[a]; if (k < 40) return null; const x = s1[t + 1] - s1[a], y = s2[t + 1] - s2[a], v = (y - x * x / k) / (k - 1); return v > 0 ? Math.sqrt(v) : null; } };
  }
  function composite(P, t) {
    if (!P || t >= P.c.length || t < W_YEAR || P.c[t] == null) return null;
    const s0 = P.wsd(t), l4 = P.logs[t - W_MONTH];
    if (!s0 || l4 == null) return null;
    const sw = Math.max(s0, VOL_FLOOR);
    let z = 0;
    for (const w of HORIZONS) { const lw = P.logs[t - w]; if (lw == null) return null; z += (l4 - lw) / (sw * Math.sqrt(w - W_MONTH)); }
    return z / HORIZONS.length;
  }
  function factorAt(P, t, B, S, Q) {
    const c = P.c, lg = P.logs;
    if (t >= c.length || c[t] == null) return null;
    const f = {}, p0 = c[t], p4 = t >= W_MONTH ? c[t - W_MONTH] : null;
    [['m12_1', W_YEAR], ['m6_1', W_HALF], ['m3_1', W_QUARTER]].forEach(([k, w]) => { const pw = t >= w ? c[t - w] : null; f[k] = p4 && pw ? p4 / pw - 1 : null; });
    f.m1 = p4 ? p0 / p4 - 1 : null;
    const win = c.slice(Math.max(0, t - W_YEAR), t + 1).filter((x) => x);
    f.hi52 = win.length >= 26 ? p0 / Math.max(...win) - 1 : null;
    const sw = P.wsd(t);
    f.vol = sw ? sw * Math.sqrt(52) : null;
    f.ra12 = f.m12_1 != null && f.vol ? f.m12_1 / Math.max(f.vol, VOL_FLOOR * Math.sqrt(52)) : null;
    f.comp = composite(P, t);
    [['rel_b', B], ['rel_s', S]].forEach(([k, X]) => {
      f[k] = null;
      if (X && t >= W_YEAR && t < X.c.length) { const a = lg[t - W_MONTH], b = lg[t - W_YEAR], x = X.logs[t - W_MONTH], y = X.logs[t - W_YEAR]; if (a != null && b != null && x != null && y != null) f[k] = (a - b) - (x - y); }
    });
    f.rs = null;
    if (B && t >= W_YEAR && t < B.c.length) { const a = lg[t], b = lg[t - W_YEAR], x = B.logs[t], y = B.logs[t - W_YEAR]; if (a != null && b != null && x != null && y != null) f.rs = 100 * Math.exp((a - x) - (b - y)); }
    f.rcomp = Q ? composite(Q, t) : null;
    return f;
  }
  const ratio = (c, b) => c.map((x, i) => (x && b[i] ? x / b[i] : null));
  function factors(c, b, s) { const P = prep(c), B = b ? prep(b) : null, S = s ? prep(s) : null, Q = b ? prep(ratio(c, b)) : null; return c.map((_, t) => factorAt(P, t, B, S, Q)); }
  function monthEnds(weeks) { const out = []; for (let i = 0; i < weeks.length - 1; i++) if (weeks[i].slice(0, 7) !== weeks[i + 1].slice(0, 7)) out.push(i); return out; }
  function tenMonth(c, me) {
    const out = {};
    me.forEach((i, j) => { if (j < 9 || i >= c.length || c[i] == null) return; const cl = me.slice(j - 9, j + 1).map((k) => c[k]).filter((x) => x != null); if (cl.length === 10) out[i] = c[i] > cl.reduce((a, x) => a + x, 0) / 10; });
    return out;
  }
  /* ---- the grid and the closes ---- */
  const DAY = 864e5;
  const iso = (ms) => new Date(ms).toISOString().slice(0, 10);
  function grid(D) { const a = Date.parse(D.start + 'T00:00:00Z'), b = Date.parse(D.weeks + 'T00:00:00Z'), out = []; for (let x = a; x <= b; x += 7 * DAY) out.push(iso(x)); return out; }
  function fullOf(ent, wk, n) { const a = new Array(n).fill(null); if (!ent || !ent.c) return a; const o = wk[ent.start]; if (o == null) return a; ent.c.forEach((v, i) => { if (o + i < n) a[o + i] = v; }); return a; }
  const fridayOf = (ms) => { const d = new Date(ms).getUTCDay(); return ms + (d === 0 ? -2 : 5 - d) * DAY; };   // the Friday of the date's week, Monday to Sunday (app/momentum.py friday)
  function fromPx(px, wk, n) {
    // data/etf/px: d0 + t (days) with a (the total-return close); the last bar of a week wins; a gap of up to two weeks
    // inside the history is carried, as on_grid does
    const a = new Array(n).fill(null);
    if (!px || !px.t || !px.a) return a;
    const d0 = Date.parse(px.d0 + 'T00:00:00Z');
    let lo = Infinity, hi = -Infinity;
    px.t.forEach((d, k) => { const i = wk[iso(fridayOf(d0 + d * DAY))], v = px.a[k]; if (i != null && v > 0) { a[i] = v; lo = Math.min(lo, i); hi = Math.max(hi, i); } });
    let last = null, gap = 0;
    for (let i = lo; i <= hi && Number.isFinite(lo); i++) { if (a[i] == null && last != null && gap < 2) { a[i] = last; gap++; } else if (a[i] != null) { gap = 0; last = a[i]; } }
    return a;
  }
  const cache = {};
  const get = (url) => cache[url] || (cache[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).catch((e) => { delete cache[url]; throw e; }));
  /* ---- charts ---- */
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return; styled = true;
    const s = document.createElement('style');
    s.textContent = `.mv{font-size:14px}.mv h3{margin:18px 0 4px;font-size:16px}.mv .muted{color:var(--muted,#777)}.mv .sm{font-size:12.5px}.mv .mv-bar{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;margin:6px 0 10px}
.mv button{font:inherit;font-size:13px;padding:4px 9px;border:1px solid var(--line,#ddd);border-radius:8px;background:var(--surface,transparent);color:inherit;cursor:pointer}.mv button.on{border-color:var(--accent,#2a78d6);color:var(--accent,#2a78d6)}
.mv .mv-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:8px 0}.mv .mv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 12px;background:var(--surface,transparent)}.mv .mv-card b{font-size:18px;display:block;margin:2px 0}.mv .mv-card .pr{font-size:12px;color:var(--muted,#777);display:block}
.mv .mv-card.grp{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px 18px;align-items:baseline}.mv svg{display:block;width:100%;height:auto}.mv svg text{font-size:11px;fill:var(--ink,#222)}.mv svg text.mu{fill:var(--muted,#777)}
.mv table{border-collapse:collapse;font-size:13px;width:100%}.mv td,.mv th{padding:3px 6px;border-bottom:1px solid var(--line,#eee);text-align:left;vertical-align:top}.mv details summary{cursor:pointer;color:var(--accent,#2a78d6)}
.mv .mv-leg{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted,#777)}.mv .mv-leg i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}`;
    document.head.appendChild(s);
  }
  const PAL = { green: '#17734a', blue: '#2a78d6', orange: '#d9822b', grey: '#7a7974', violet: '#6a4fd1', red: '#ea6a52' };
  function lineChart(series, weeks, from, to, opt) {
    // series: [{name, short, values (per week), color, dash, width, opacity}]; opt: {fmt: 'pct' | 'sigma' | 'plain', zero,
    // yMin, yMax, hline, bands: [[lo, hi, color]], height, label, width (900; a phone's 380 keeps the labels legible)}
    opt = opt || {};
    const W = opt.width || 900, narrow = W < 600, H = opt.height || 220, L = narrow ? 40 : 52, R = narrow ? 58 : 98, T = 12, B = 24;
    const vals = [];
    series.forEach((s) => { for (let i = from; i <= to; i++) if (fin(s.values[i])) vals.push(s.values[i]); });
    if (!vals.length) return '<p class="muted sm">Not enough history for this chart yet (it needs a year of weekly closes).</p>';
    let lo = opt.yMin != null ? opt.yMin : Math.min(...vals), hi = opt.yMax != null ? opt.yMax : Math.max(...vals);
    if (opt.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (opt.hline != null) { lo = Math.min(lo, opt.hline); hi = Math.max(hi, opt.hline); }
    if (hi === lo) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.06; if (opt.yMin == null) lo -= pad; if (opt.yMax == null) hi += pad;
    const x = (i) => L + (i - from) / Math.max(1, to - from) * (W - L - R), y = (v) => T + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * (H - T - B);
    const fmt = (v) => (opt.fmt === 'pct' ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(Math.round(100 * v)) + '%' : opt.fmt === 'sigma' ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1) + 'σ' : String(Math.round(v)));
    let o = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.label || '')}">`;
    (opt.bands || []).forEach(([a, b, col]) => { o += `<rect x="${L}" y="${y(b)}" width="${W - L - R}" height="${Math.max(0, y(a) - y(b))}" fill="${col}"/>`; });
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; o += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line,#e6e6e6)"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="mu">${esc(fmt(v))}</text>`; }
    if (opt.zero && lo < 0 && hi > 0) o += `<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="var(--muted,#999)" stroke-width="1.2"/>`;
    if (opt.hline != null) o += `<line x1="${L}" x2="${W - R}" y1="${y(opt.hline)}" y2="${y(opt.hline)}" stroke="var(--muted,#999)" stroke-dasharray="4 3"/>`;
    // the years: every one, or every 2nd, 5th or 10th as the width allows; the window's first year only when it is not a
    // few weeks from the next (its label would sit on the next one's)
    let lastY = ''; const span = to - from, pxYear = (W - L - R) / Math.max(1, span / 52), step = pxYear >= 34 ? 1 : pxYear >= 16 ? 2 : pxYear >= 6 ? 5 : 10;
    for (let i = from; i <= to; i++) { const yr = weeks[i].slice(0, 4); if (yr !== lastY) { lastY = yr; if (i > from + 3) o += `<line x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${H - B}" stroke="var(--line,#eee)"/>`; if (+yr % step === 0 && !(i === from && weeks[i].slice(5, 7) >= '10')) o += `<text x="${x(i) + 2}" y="${H - 7}" class="mu">${esc(yr)}</text>`; } }
    const ends = [];
    series.forEach((s) => {
      let d = '', pen = false;
      for (let i = from; i <= to; i++) { const v = s.values[i]; if (fin(v)) { d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(v).toFixed(1); pen = true; } else pen = false; }
      if (d) o += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 1.6}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ''} opacity="${s.opacity || 1}" stroke-linejoin="round"><title>${esc(s.name)}</title></path>`;
      for (let i = to; i >= from; i--) if (fin(s.values[i])) { ends.push({ s, v: s.values[i], y: y(s.values[i]) }); break; }
    });
    ends.sort((a, b) => a.y - b.y);
    let prev = -1e9;
    ends.forEach((e) => { const yy = Math.max(e.y + 4, prev + 13); prev = yy; o += `<text x="${W - R + 6}" y="${Math.min(H - B, yy)}" fill="${e.s.color}" font-weight="600">${narrow ? '' : esc(e.s.short || e.s.name) + ' '}${esc(opt.fmt === 'pct' ? pct(e.v, 0) : opt.fmt === 'sigma' ? sig(e.v) : Math.round(e.v))}</text>`; });
    return o + '</svg>';
  }
  const legend = (series) => `<div class="mv-leg">${series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}</div>`;
  /* ---- loading ---- */
  async function load(T, hub, base) {
    const D = await get(base + 'rrg.json');
    const weeks = grid(D), wk = Object.fromEntries(weeks.map((w, i) => [w, i])), n = weeks.length;
    const benchId = D.benchmark || 'SPY';
    const ser = (D.series || []).find((x) => String(x.id).toUpperCase() === T);     // a sector or style ETF, or s:<sector> (the site's companies)
    let c = null, name = T, kind = 'stock', tdoc = null, sector = null, etfName = null;
    if (T === benchId) { c = fullOf(D.bench, wk, n); kind = 'etf'; name = 'S&P 500 (SPY)'; }
    else if (ser) { c = fullOf(ser, wk, n); kind = ser.group === 'site-sector' ? 'index' : 'etf'; name = ser.name || T; }
    else {
      tdoc = await get(base + 't/' + encodeURIComponent(T) + '.json').catch(() => null);
      if (tdoc) { c = fullOf(tdoc, wk, n); name = tdoc.n || T; sector = (D.series || []).find((x) => x.group === 'sector-etf' && x.sector === tdoc.s) || null; }
      else {
        const px = await get(hub + 'data/etf/px/' + encodeURIComponent(T) + '.json').catch(() => null);
        if (!px) throw new Error(`no weekly closes for ${T} (neither a company of the site nor an ETF with a price file)`);
        c = fromPx(px, wk, n); kind = 'etf'; etfName = px.name; name = px.name || T;
      }
    }
    // the ranks: a company among the companies (rotation history), an ETF among the ETFs (the ETF build); none for an index
    const ranks = kind === 'index' ? null : await get((kind === 'etf' ? hub + 'data/etf/' : base) + 'momentum/' + encodeURIComponent(T) + '.json').catch(() => null);
    return { D, weeks, wk, n, benchId, c, bench: T === benchId ? null : fullOf(D.bench, wk, n), sector, sec: sector ? fullOf(sector, wk, n) : null, name, kind, ranks, etfName };
  }
  /* ---- the ranks on the week grid: each month's value carried through its weeks ---- */
  function rankLines(ranks, weeks, lastI) {
    if (!ranks || !ranks.rows || !ranks.m0) return null;
    const me = monthEnds(weeks), j0 = me.findIndex((i) => weeks[i] === ranks.m0);
    if (j0 < 0) return null;
    const n = weeks.length, F = ranks.fields || [], lines = {};
    const put = (key, get) => { const a = new Array(n).fill(null); ranks.rows.forEach((r, j) => { const i = me[j0 + j]; if (i != null) a[i] = get(r, j); }); let v = null; for (let i = 0; i <= lastI; i++) { if (a[i] != null) v = a[i]; else if (v != null && i > me[j0]) a[i] = v; } lines[key] = a; };
    F.forEach((k, q) => put(k, (r) => (r ? r[q] : null)));
    if (ranks.group_comp) put('group', (r, j) => ranks.group_comp[j]);
    const last = ranks.rows[ranks.rows.length - 1];
    // the month of the last row from m0 (one row a month), so a ranks file a month ahead of this grid still reads right
    const k = +ranks.m0.slice(0, 4) * 12 + +ranks.m0.slice(5, 7) - 1 + ranks.rows.length - 1, month = Math.floor(k / 12) + '-' + String(k % 12 + 1).padStart(2, '0');
    return { lines, last: last ? Object.fromEntries(F.map((k, q) => [k, last[q]])) : null, lastGroup: ranks.group_comp ? ranks.group_comp[ranks.group_comp.length - 1] : null, month };
  }
  /* ---- render ---- */
  async function render(el, opt) {
    css();
    opt = opt || {};
    const hub = opt.hub != null ? opt.hub : '';
    const base = opt.base || hub + 'data/market/history/';
    const here = () => el.isConnected && (typeof opt.here !== 'function' || opt.here());
    const T = String(opt.ticker || '').toUpperCase().replace(/[./]/g, '-');
    el.innerHTML = '<p class="muted">Reading the weekly closes…</p>';
    let X;
    try { X = await load(T, hub, base); } catch (e) { if (here()) el.innerHTML = `<div class="mv"><p class="muted">Momentum factors: ${esc(e.message)}.</p></div>`; return; }
    if (!here()) return;
    const { weeks, n, c } = X;
    const F = factors(c, X.bench, X.sec);
    const me = monthEnds(weeks), ts = tenMonth(c, me);
    let lastI = -1; for (let i = n - 1; i >= 0; i--) if (F[i]) { lastI = i; break; }
    if (lastI < 0) { el.innerHTML = '<div class="mv"><p class="muted">No weekly closes for this ticker yet.</p></div>'; return; }
    const R = rankLines(X.ranks, weeks, lastI);
    const firstFull = (() => { for (let i = 0; i < n; i++) if (F[i] && F[i].m12_1 != null) return i; return 0; })();
    const state = { years: 5 };
    const col = (k) => F.map((f) => (f ? f[k] : null));
    const draw = () => {
      const from = Math.max(firstFull, state.years ? lastI - 52 * state.years : 0), last = F[lastI];
      const cw = (el.clientWidth || 900) < 560 ? 380 : 900, chart = (s, w, f, t, o) => lineChart(s, w, f, t, Object.assign({ width: cw }, o));
      const tsKeys = Object.keys(ts).map(Number).filter((i) => i <= lastI).sort((a, b) => a - b), lastTs = tsKeys.length ? ts[tsKeys[tsKeys.length - 1]] : null;
      const uni = X.kind === 'etf' ? 'ETFs' : 'companies', lab = X.kind === 'index' ? X.name : T;
      const pr = (k) => (R && R.last && R.last[k] != null ? `<span class="pr">${ord(R.last[k])} percentile of ${X.ranks.n || ''} ${uni}</span>` : '');
      const abs = [{ name: '12 months, skipping the latest', short: '12-1', values: col('m12_1'), color: PAL.green, width: 2.2 }, { name: '6 months, skipping the latest', short: '6-1', values: col('m6_1'), color: PAL.blue }, { name: '3 months, skipping the latest', short: '3-1', values: col('m3_1'), color: PAL.orange }, { name: 'The latest month (reversal; in no score)', short: '1m', values: col('m1'), color: PAL.grey, dash: '3 3', opacity: 0.85 }];
      const comp = [{ name: 'Composite score: 3-, 6- and 12-month trends in σ', short: 'composite', values: col('comp'), color: PAL.green, width: 2.4 }].concat(X.bench ? [{ name: `Relative composite: the same on the line ${lab} ÷ ${X.benchId}`, short: 'relative', values: col('rcomp'), color: PAL.violet, width: 1.8 }] : []);
      const rel = X.bench ? [{ name: `12-1 against ${X.benchId} (log difference)`, short: 'vs ' + X.benchId, values: col('rel_b'), color: PAL.blue, width: 2.2 }].concat(X.sec ? [{ name: `12-1 against ${X.sector.id} (its sector ETF)`, short: 'vs ' + X.sector.id, values: col('rel_s'), color: PAL.orange }] : []) : [];
      const rs = X.bench ? [{ name: `RS ratio: ${lab} ÷ ${X.benchId} against a year before (100 = kept pace)`, short: 'RS', values: col('rs'), color: PAL.violet, width: 2 }] : [];
      const hi = [{ name: 'Below the 52-week high', short: '52w high', values: col('hi52'), color: PAL.red, width: 2 }];
      const rk = R ? [{ name: 'Composite momentum rank', short: 'composite', values: R.lines.comp, color: PAL.green, width: 2.6 }, { name: '12-1 rank (relative strength)', short: '12-1', values: R.lines.m12_1, color: PAL.blue, opacity: 0.75 }, { name: '52-week high rank', short: '52w', values: R.lines.hi52, color: PAL.red, opacity: 0.6 }].concat(R.lines.group ? [{ name: `Composite rank inside ${X.ranks.group || 'its asset class'}`, short: 'in class', values: R.lines.group, color: PAL.violet, dash: '5 3' }] : []) : null;
      const absOn = last.m12_1 != null && last.m12_1 > 0, relOn = last.rel_b != null && last.rel_b > 0;
      const dual = last.m12_1 == null || (X.bench && last.rel_b == null) ? '—' : !X.bench ? (absOn ? 'Absolute up' : 'Absolute down') : absOn && relOn ? 'Both up' : absOn ? 'Absolute only' : relOn ? 'Relative only' : 'Neither';
      el.innerHTML = `<div class="mv"><h3>Momentum factors: ${X.kind === 'index' ? esc(X.name) : `${esc(T)} <span class="muted">${esc(X.name)}</span>`}</h3>
<p class="muted sm">Weekly total-return closes (distributions reinvested, splits adjusted) to ${esc(weeks[lastI])}${X.kind === 'etf' ? ' · an ETF' : X.kind === 'index' ? ' · an index of the site\u2019s companies in the sector (weekly log returns weighted by the log of revenue)' : ''}. Every figure at a week uses the closes up to that week only. A reading of the factors, not a forecast and not advice.</p>
<div class="mv-bar"><span class="muted sm">Window</span>${[3, 5, 10, 0].map((y) => `<button type="button" data-y="${y}" class="${state.years === y ? 'on' : ''}">${y ? y + ' years' : 'All'}</button>`).join('')}</div>
<div class="mv-cards">
<div class="mv-card"><span class="muted sm">12-month momentum (skip 1)</span><b>${esc(pct(last.m12_1))}</b>${pr('m12_1')}</div>
<div class="mv-card"><span class="muted sm">6-month (skip 1)</span><b>${esc(pct(last.m6_1))}</b>${pr('m6_1')}</div>
<div class="mv-card"><span class="muted sm">Composite score</span><b>${esc(sig(last.comp))}</b><span class="pr">3-, 6-, 12-month trends in their own σ</span></div>
<div class="mv-card"><span class="muted sm">Composite momentum rank</span><b>${R && R.last && R.last.comp != null ? ord(R.last.comp) + ' <small>percentile</small>' : '—'}</b><span class="pr">${R ? `of ${X.ranks.n || ''} ${uni}, ${esc(R.month)}${R.lastGroup != null ? ` · ${ord(R.lastGroup)} inside ${esc(X.ranks.group || 'its class')}` : ''}` : X.kind === 'etf' ? 'not ranked: leveraged and inverse ETFs, cash-like funds (under 3% a year of volatility) and those with under a year of closes are left out; the rest come with the ETF data\u2019s next build' : X.kind === 'index' ? 'an index is not ranked: its sector\u2019s place is in the Momentum tab\u2019s sectors and styles' : 'the monthly ranks come with the rotation history\u2019s next build'}</span></div>
${X.bench ? `<div class="mv-card"><span class="muted sm">Relative 12-1 vs ${esc(X.benchId)}</span><b>${esc(pct(last.rel_b))}</b>${X.sec ? `<span class="pr">vs ${esc(X.sector.id)} ${esc(pct(last.rel_s))}</span>` : ''}<span class="pr">RS ratio ${fin(last.rs) ? Math.round(last.rs) : '—'} · relative composite ${esc(sig(last.rcomp))}</span></div>` : ''}
<div class="mv-card"><span class="muted sm">From the 52-week high</span><b>${esc(pct(last.hi52))}</b>${pr('hi52')}</div>
<div class="mv-card"><span class="muted sm">Vol-scaled 12-1</span><b>${fin(last.ra12) ? (last.ra12 < 0 ? '−' : '') + Math.abs(last.ra12).toFixed(2) : '—'}</b><span class="pr">volatility ${fin(last.vol) ? Math.round(100 * last.vol) + '%' : '—'} a year</span>${pr('ra12')}</div>
<div class="mv-card"><span class="muted sm">Dual momentum</span><b>${esc(dual)}</b><span class="pr">absolute: 12-1 above zero${X.bench ? `; relative: ahead of ${esc(X.benchId)}` : ''} · 10-month rule: ${lastTs == null ? '—' : lastTs ? 'above' : 'below'}</span></div>
</div>
<h3>Absolute momentum</h3><p class="muted sm">The past return over 12, 6 and 3 months, each skipping the latest month (the skip leaves out the one-month reversal); the latest month dashed.</p>${chart(abs, weeks, from, lastI, { fmt: 'pct', zero: true, label: 'absolute momentum' })}${legend(abs)}
<h3>Composite momentum</h3><p class="muted sm">Each horizon's return (13, 26, 52 weeks, skipping the latest 4) divided by its own standard deviation (the weekly σ × √(weeks − 4)), averaged: a t-statistic of the trend, so a calm and a volatile ticker read on one scale. Above +1σ: a strong uptrend on all three horizons; below −1σ: a strong downtrend.${X.bench ? ` The relative composite is the same score computed on the line ${esc(lab)} ÷ ${esc(X.benchId)}.` : ''}</p>${chart(comp, weeks, from, lastI, { fmt: 'sigma', zero: true, bands: [[1, 99, 'rgba(23,115,74,.07)'], [-99, -1, 'rgba(234,106,82,.07)']], label: 'composite momentum' })}${legend(comp)}
${X.bench ? `<h3>Relative momentum</h3><p class="muted sm">The 12-1 return minus ${esc(X.benchId)}'s${X.sec ? ` and minus its sector ETF's (${esc(X.sector.id)})` : ''}, as a log difference: above zero, ${esc(lab)} beat it over the window. Below: the RS ratio, the relative line against a year before.</p>${chart(rel, weeks, from, lastI, { fmt: 'pct', zero: true, label: 'relative momentum' })}${legend(rel)}${chart(rs, weeks, from, lastI, { fmt: 'plain', hline: 100, height: 160, label: 'RS ratio' })}${legend(rs)}` : ''}
<h3>Cross-sectional rank</h3>${rk ? `<p class="muted sm">Each month end's percentile among ${X.ranks.n || ''} ${uni} of the site's universe (today's tickers: the early years leave out those that no longer trade). The composite rank orders the composite score; shaded: the top and bottom fifth.</p>${chart(rk, weeks, from, lastI, { fmt: 'plain', yMin: 0, yMax: 100, bands: [[80, 100, 'rgba(23,115,74,.10)'], [0, 20, 'rgba(234,106,82,.10)']], label: 'momentum ranks' })}${legend(rk)}` : `<p class="muted sm">${X.kind === 'etf' ? 'No cross-sectional rank for this ETF: leveraged and inverse ETFs (their momentum is a multiple of another fund’s), cash-like funds (under 3% a year of volatility: their trend is their yield) and ETFs with under a year of closes are left out; the others are ranked with the ETF data’s builds.' : X.kind === 'index' ? 'An index of the site’s companies has no cross-sectional rank of its own; the Momentum tab ranks the sectors and styles against each other.' : 'The monthly ranks among the site’s companies are published with the rotation history’s next build.'}</p>`}
<h3>Distance from the 52-week high</h3>${chart(hi, weeks, from, lastI, { fmt: 'pct', zero: true, height: 150, label: '52-week high' })}
<details><summary>Definitions, sources and limits</summary><table><tbody>
<tr><td>12-1, 6-1, 3-1</td><td>P[t−4w] ÷ P[t−52w] − 1, P[t−4w] ÷ P[t−26w] − 1, P[t−4w] ÷ P[t−13w] − 1 — Jegadeesh &amp; Titman (1993); the one-month skip after Jegadeesh (1990)</td></tr>
<tr><td>Composite score</td><td>mean over w = 13, 26, 52 of ln(P[t−4]/P[t−w]) ÷ (σ × √(w−4)), σ the weekly standard deviation of the last 52 weekly log returns, floored at 0.4% a week (≈ 2.9% a year: a cash-like fund's steady yield is not an extreme trend) — volatility-scaled time-series momentum as in Moskowitz, Ooi &amp; Pedersen (2012), over three horizons</td></tr>
<tr><td>Relative</td><td>ln(P[t−4]/P[t−52]) − ln(B[t−4]/B[t−52]) against SPY and the sector SPDR; RS ratio = 100 × (P/B)[t] ÷ (P/B)[t−52]; relative composite = the composite score of P/B</td></tr>
<tr><td>Ranks</td><td>the percentile (0–100) of 12-1, 6-1, the 52-week high, vol-scaled 12-1 and the composite score among the universe at each month end (app/momentum.py): companies of the site; ETFs that are neither leveraged nor inverse, and inside their asset class. Asness, Moskowitz &amp; Pedersen (2013): momentum across asset classes</td></tr>
<tr><td>52-week high</td><td>P ÷ the highest close of the last 52 weeks − 1 — George &amp; Hwang (2004)</td></tr>
<tr><td>Vol-scaled 12-1</td><td>12-1 ÷ the annualised volatility (the same floor) — Barroso &amp; Santa-Clara (2015); Daniel &amp; Moskowitz (2016) on momentum crashes after market lows</td></tr>
<tr><td>Dual momentum</td><td>absolute (12-1 above zero) and relative (ahead of SPY over 12-1) together — after Antonacci (2014), who uses the excess over Treasury bills for the absolute leg; the 10-month rule: the close above the mean of the last ten month-end closes (Faber 2007)</td></tr>
<tr><td>Limits</td><td>weekly closes (a month = 4 weeks); today's tickers only; no costs, borrow or taxes — a reading of a factor, not a strategy's return. Momentum has crashed after bear-market lows (2009, 2020).</td></tr>
</tbody></table></details>
<p class="muted sm">Data: Yahoo Finance weekly closes (Stooq as the fallback), branches rotation-history and etf-history. Not investment advice.</p></div>`;
      el.querySelectorAll('button[data-y]').forEach((b) => { b.onclick = () => { state.years = +b.dataset.y; draw(); }; });
    };
    draw();
  }
  const api = { render, factors, factorAt, prep, composite, tenMonth, monthEnds, fromPx, rankLines, lineChart, grid, fullOf };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.MomentumView = api;
})(typeof window !== 'undefined' ? window : globalThis);
