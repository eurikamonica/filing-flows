/* Moving averages+ — the usual moving averages of a share price, daily and weekly, with the company's earnings, its own
   guidance and the macro mixed in or set beside them, and what each has been worth (app/ma_hybrid.py, branch rotation-history).
   · A company: its daily closes with any N-day averages (5 … 250 days, or a length typed in: "XX-day") and the hybrid line
     on a chosen base; what being above each average has paid; its weekly close of the last five years, the 10- and 40-week
     averages, the earnings line (trailing EPS × its own five-year median P/E) and the hybrid line H = MA^(1−w) × earnings
     line^w × (1 + g × guidance) — w and g picked here; guidance releases marked (▲ raised, ▼ lowered, ● kept); what "above
     the line" paid for the chosen weights since 2016; the models' rank of the company this week; the macro now, and what
     the 40-week trend paid in the same third of each reading.
   · The hub (Rotation → Chart → Moving averages+): the tests — the models (moving averages alone, + fundamentals, +
     guidance, × macro), the classic rules, every daily length and cross, every weight on the grid and the pick made each
     year, what followed each kind of guidance release, the index funds' 40-week rule with and without a macro filter, the
     trend by macro third — the companies furthest from the line, the latest 50/200-day crosses and any ticker's charts.
   Data: data/market/history/ma-hybrid.json, ma-hybrid-rows.json, ma/<TICKER>.json, ma-daily/<TICKER>.json. Self-contained:
   the main site's company page (views.json "mahybrid") and the hub use it, colours from the host's CSS variables; the
   daily chart's choices are kept in this browser when it allows.
   window.MAHybridView.render(el, {ticker, hub}) · .renderHub(el, {hub}). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? '$' + num(v, v >= 1000 ? 0 : v >= 1 ? 2 : 4) : '—');
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const gap = (lp) => (fin(lp) ? spct(Math.exp(lp) - 1) : '—');                 // a log distance as a percentage
  const store = {};
  const get = (u) => store[u] || (store[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .catch((e) => { delete store[u]; throw e; }));
  const COL = { ink: 'var(--ink, #222)', p: 'var(--ink, #222)', m10: 'var(--rot-1, #2a78d6)', m40: 'var(--slate, #5b7fa6)', el: 'var(--q-warm, #d9822b)', h: 'var(--accent, #17734a)',
    up: 'var(--mk-profit, #17734a)', down: 'var(--mk-cost, #c0392b)', mute: 'var(--muted, #888)', line: 'var(--line, #e3e3e3)' };
  const WS = [0, 0.25, 0.5, 0.75, 1], GS = [0, 0.05, 0.1];
  const MODEL_ORDER = ['ma', 'ma_fund', 'hybrid', 'ma_macro', 'ma_macro_09'];
  const GLAB = { raised: 'raised', lowered: 'lowered', withdrawn: 'withdrawn', reaffirmed: 'kept', updated: 'updated', initiated: 'first given', narrowed: 'narrowed', mixed: 'mixed', widened: 'widened' };
  const GDIR = { raised: 1, lowered: -1, withdrawn: -1 };
  // the daily chart: the N-day averages offered (each its own colour), a custom "XX-day" one, the range, the hybrid's base
  const NDAYS = [5, 10, 20, 30, 50, 60, 120, 200, 250], BASES = [20, 50, 60, 120, 200, 250];
  const NCOL = { 5: '#d4a017', 10: '#d81b60', 20: '#1e88e5', 30: '#00acc1', 50: '#8e24aa', 60: '#43a047', 120: '#8d6e63', 200: '#f4511e', 250: '#78909c' };
  const XCOL = '#26a69a', MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const RANGES = [[63, '3M'], [126, '6M'], [252, '1Y'], [504, '2Y'], [756, '3Y']];
  const ui = { w: null, g: null, nd: [20, 50, 200], xx: null, range: 252, base: 200 };
  const RULE_SHORT = { hold: 'Hold', above40: '40-week rule', trend_unemployment: '+ unemployment', trend_sahm: '+ Sahm rule' };
  const SAVE = 'mh-daily-v1';
  try { const v = JSON.parse(localStorage.getItem(SAVE) || 'null');            // this viewer's last choice, when kept
    if (v && Array.isArray(v.nd)) Object.assign(ui, { nd: v.nd.filter((x) => NDAYS.includes(x)), xx: Number.isInteger(v.xx) ? v.xx : null,
      range: RANGES.some((r) => r[0] === v.range) ? v.range : 252, base: BASES.includes(v.base) ? v.base : 200 }); } catch (e) { /* no storage */ }
  const keep = () => { try { localStorage.setItem(SAVE, JSON.stringify({ nd: ui.nd, xx: ui.xx, range: ui.range, base: ui.base })); } catch (e) { /* no storage */ } };

  function css() {
    if (typeof document === 'undefined' || document.getElementById('mh-css')) return;
    const s = document.createElement('style'); s.id = 'mh-css';
    s.textContent = `.mh h3{margin:22px 0 4px;font-size:17px}.mh h4{margin:14px 0 4px;font-size:14px}.mh .mh-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.5;max-width:86ch}
.mh svg{display:block;width:100%;height:auto}.mh .mh-chart{max-width:860px}.mh .mh-t{fill:var(--muted,#777);font-size:11px}.mh .mh-grid{stroke:var(--line,#e3e3e3)}
.mh-ctl{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 6px;align-items:center;font-size:13px;color:var(--muted,#666)}.mh-ctl select,.mh-ctl input{font:inherit;font-size:13px;padding:3px 6px;border:1px solid var(--line,#ccc);border-radius:6px;background:var(--surface,#fff);color:var(--ink,#222)}
.mh-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.mh-tbl th,.mh-tbl td{padding:5px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.mh-tbl td.n,.mh-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.mh-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}.mh-tbl tr.on td{background:color-mix(in srgb,var(--accent,#17734a) 10%,transparent);font-weight:600}
.mh-wrap{overflow-x:auto}.mh-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(165px,1fr));gap:8px;margin:6px 0 8px}.mh-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 10px}
.mh-card span{display:block;font-size:12px;color:var(--muted,#777)}.mh-card b{font-size:18px;font-variant-numeric:tabular-nums}.mh-card i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777)}
.mh-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.mh-legend b{display:inline-block;width:14px;height:3px;margin-right:5px;vertical-align:3px}
.mh-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:10px;max-width:92ch}.mh-sec{border-top:1px solid var(--line,#e5e5e5);margin-top:22px;padding-top:4px}
.mh .pos{color:var(--mk-profit,#17734a)}.mh .neg{color:var(--mk-cost,#c0392b)}.mh .muted{color:var(--muted,#777)}
.mh-nd{display:inline-flex;align-items:center;gap:3px;white-space:nowrap}.mh-nd input{margin:0}.mh-nd b{display:inline-block;width:12px;height:3px;border-radius:2px}
.mh-seg{display:inline-flex;border:1px solid var(--line,#ccc);border-radius:7px;overflow:hidden}.mh-seg button{font:inherit;font-size:12px;padding:3px 9px;border:0;background:transparent;color:var(--ink,#222);cursor:pointer}
.mh-seg button+button{border-left:1px solid var(--line,#ccc)}.mh-seg button.on{background:color-mix(in srgb,var(--accent,#17734a) 16%,transparent);font-weight:600}
.mh-ctl input[type=number]{width:5.5em}.mh details{margin:8px 0}.mh summary{cursor:pointer;font-size:13px;color:var(--ink,#222)}.mh-tbl td.cur{outline:2px solid color-mix(in srgb,var(--accent,#17734a) 55%,transparent);outline-offset:-2px}`;
    document.head.appendChild(s);
  }
  const tbl = (head, rows, numeric) => `<div class="mh-wrap"><table class="mh-tbl"><tr>${head.map((h, j) => `<th${numeric && numeric[j] ? ' class="n"' : ''}>${h}</th>`).join('')}</tr>${rows.map((r) => `<tr${r.on ? ' class="on"' : ''}>${(r.cells || r).map((c, j) => `<td${numeric && numeric[j] ? ' class="n"' : ''}>${c}</td>`).join('')}</tr>`).join('')}</table></div>`;
  const sgn = (v, txt) => `<span class="${fin(v) ? (v > 0 ? 'pos' : v < 0 ? 'neg' : '') : ''}">${txt}</span>`;
  const tn = (v) => (fin(v) ? (v < 0 ? '−' : '') + num(Math.abs(v), 1) : '—');           // a t-statistic, with a real minus
  const st = (s, d = 2) => (s && fin(s.mean) ? `${sgn(s.mean, spct(s.mean, d))} <span class="muted">(t ${tn(s.t)})</span>` : '—');
  const icTxt = (s) => (s && fin(s.mean) ? `${s.mean < 0 ? '−' : ''}${num(Math.abs(s.mean), 3)} <span class="muted">(t ${tn(s.t)})</span>` : '—');
  const key = (w, g) => `${w}|${g}`;

  // ------------------------------------------------------------------ the lines
  function hybrid(s, w, g) {
    return s.ma40.map((m, k) => {
      if (!fin(m) || m <= 0) return null;
      const e = s.el[k], dir = s.g[k];
      const base = fin(e) && e > 0 ? Math.exp((1 - w) * Math.log(m) + w * Math.log(e)) : m;
      return base * (1 + g * (fin(dir) ? dir : 0));
    });
  }
  function weekDate(s, k) {
    const d = new Date(s.start + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 7 * k); return d.toISOString().slice(0, 10);
  }
  function chart(s, w, g, width) {
    const V = ((s.now || {}).val) || {}, dcf = fin(V.dcf_value) && V.dcf_value > 0 ? V.dcf_value : null;
    const Wd = Math.max(340, Math.min(860, width || 760)), Ht = Wd < 500 ? 300 : 340, L = 52, R = dcf ? 46 : 10, T = 12, B = 26;
    const H = hybrid(s, w, g), n = s.p.length;
    const series = [['p', s.p], ['m10', s.ma10], ['m40', s.ma40], ['el', s.el], ['h', H], ['dcf', dcf ? [dcf] : []]];
    const vals = series.flatMap(([, a]) => a.filter((v) => fin(v) && v > 0));
    if (!vals.length || n < 2) return '<p class="muted">Not enough weekly history to draw.</p>';
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pmin = Math.min(...s.p.filter(fin)), pmax = Math.max(...s.p.filter(fin));
    lo = Math.max(lo, pmin / 3); hi = Math.min(hi, pmax * 3);                    // a far-off earnings line is clipped, not the price
    const ly = (v) => Math.log(v), y0 = ly(lo) - 0.03 * (ly(hi) - ly(lo)), y1 = ly(hi) + 0.03 * (ly(hi) - ly(lo));
    const sx = (k) => L + (Wd - L - R) * k / (n - 1), sy = (v) => T + (Ht - T - B) * (1 - (ly(Math.min(Math.max(v, lo), hi)) - y0) / (y1 - y0));
    const f = (v) => v.toFixed(1);
    let out = `<svg viewBox="0 0 ${Wd} ${Ht}" role="img" aria-label="${esc(s.id)}: weekly close, 10- and 40-week averages, earnings line and hybrid line">`;
    const ticks = [];
    const span = Math.log10(hi / lo), step = Math.pow(10, Math.floor(Math.log10(hi - lo))) * (span > 0.6 ? 1 : 0.5);
    for (let v = Math.ceil(lo / step) * step; v <= hi && ticks.length < 9; v += step) ticks.push(v);
    ticks.forEach((v) => { out += `<line class="mh-grid" x1="${L}" x2="${Wd - R}" y1="${f(sy(v))}" y2="${f(sy(v))}"/><text class="mh-t" x="${L - 5}" y="${f(sy(v) + 4)}" text-anchor="end">${esc(usd(v))}</text>`; });
    for (let k = 0; k < n; k += 1) {
      const d = weekDate(s, k);
      if (d.slice(5, 7) === '01' && Number(d.slice(8, 10)) <= 7) out += `<line class="mh-grid" x1="${f(sx(k))}" x2="${f(sx(k))}" y1="${T}" y2="${Ht - B}"/><text class="mh-t" x="${f(sx(k))}" y="${Ht - 8}" text-anchor="middle">${d.slice(0, 4)}</text>`;
    }
    const path = (a, col, wdt, dash) => {
      let d = '', pen = false;
      a.forEach((v, k) => { if (fin(v) && v > 0) { d += (pen ? 'L' : 'M') + f(sx(k)) + ',' + f(sy(v)); pen = true; } else pen = false; });
      return d ? `<path d="${d}" style="fill:none;stroke:${col};stroke-width:${wdt};${dash ? 'stroke-dasharray:' + dash + ';' : ''}stroke-linejoin:round"/>` : '';
    };
    out += path(s.el, COL.el, 1.6, '') + path(s.ma10, COL.m10, 1.3, '5 3') + path(s.ma40, COL.m40, 1.6, '') + path(H, COL.h, 2.6, '') + path(s.p, COL.p, 1.4, '');
    (s.guidance || []).forEach(([d, lab]) => {                                      // guidance releases on the price line
      const k = Math.floor((Date.parse(d + 'T00:00:00Z') - Date.parse(s.start + 'T00:00:00Z')) / (7 * 864e5)) + 1;   // the first weekly close after it
      if (k < 0 || k >= n || !fin(s.p[k])) return;
      const x = sx(k), y = sy(s.p[k]), dir = GDIR[lab], col = dir > 0 ? COL.up : dir < 0 ? COL.down : COL.mute;
      const shape = dir > 0 ? `M${f(x)},${f(y - 13)}l5,8h-10z` : dir < 0 ? `M${f(x)},${f(y + 13)}l5,-8h-10z` : '';
      out += shape ? `<path d="${shape}" style="fill:${col}"><title>${esc(d)}: guidance ${esc(GLAB[lab] || lab)}</title></path>`
        : `<circle cx="${f(x)}" cy="${f(y - 9)}" r="3.5" style="fill:${col}"><title>${esc(d)}: guidance ${esc(GLAB[lab] || lab)}</title></circle>`;
    });
    if (dcf) {                                                                       // the Fair value page's DCF, this week only
      const x = Wd - R + 14, lo_ = fin(V.mc_p10) && V.mc_p10 > 0 ? V.mc_p10 : null, hi_ = fin(V.mc_p90) && V.mc_p90 > 0 ? V.mc_p90 : null;
      if (lo_ && hi_) out += `<line x1="${f(x)}" x2="${f(x)}" y1="${f(sy(hi_))}" y2="${f(sy(lo_))}" style="stroke:${COL.mute};stroke-width:6;opacity:.35"><title>DCF Monte Carlo, 10%–90%: ${esc(usd(lo_))}–${esc(usd(hi_))}</title></line>`;
      out += `<path d="M${f(x - 7)},${f(sy(dcf))}h14" style="stroke:${COL.ink || '#222'};stroke-width:2.5"><title>DCF value this week: ${esc(usd(dcf))}</title></path><text class="mh-t" x="${f(x)}" y="${f(Math.min(Ht - B - 2, sy(dcf) + 14))}" text-anchor="middle">DCF</text>`;
    }
    return out + '</svg>';
  }
  const legend = (w, g) => `<div class="mh-legend"><span><b style="background:${COL.p}"></b>weekly close</span><span><b style="background:${COL.m10}"></b>10-week average (≈ 50-day)</span>
    <span><b style="background:${COL.m40}"></b>40-week average (≈ 200-day)</span><span><b style="background:${COL.el}"></b>earnings line</span>
    <span><b style="background:${COL.h};height:4px"></b>hybrid line (${pct(w)} earnings line, ${pct(g)} per guidance change)</span><span>▲ guidance raised · ▼ lowered · ● kept</span></div>`;

  // ------------------------------------------------------------------ the daily chart
  function dailyOf(dd) {                                                          // {d: dates, p: closes} from start + day gaps
    const d = [dd.start]; let t = Date.parse(dd.start + 'T00:00:00Z');
    (dd.gap || []).forEach((g) => { t += g * 864e5; d.push(new Date(t).toISOString().slice(0, 10)); });
    return { d, p: dd.p || [], asof: dd.asof || d[d.length - 1] };
  }
  function sma(p, n) {                                                            // simple average of the last n closes
    const out = new Array(p.length).fill(null); let s = 0, bad = 0;
    for (let i = 0; i < p.length; i += 1) {
      if (fin(p[i])) s += p[i]; else bad += 1;
      if (i >= n) { if (fin(p[i - n])) s -= p[i - n]; else bad -= 1; }
      if (i >= n - 1 && !bad) out[i] = s / n;
    }
    return out;
  }
  function weeklyOnDays(s, dates, arr) {                                          // a weekly line on each day: its latest Friday
    const out = new Array(dates.length).fill(null); if (!s || !arr) return out;
    const wd = arr.map((_, k) => weekDate(s, k)); let k = -1;
    dates.forEach((day, i) => { while (k + 1 < wd.length && wd[k + 1] <= day) k += 1; out[i] = k >= 0 ? arr[k] : null; });
    return out;
  }
  function dailyHybrid(D, s, base, w, g) {
    const m = sma(D.p, base), el = weeklyOnDays(s, D.d, s && s.el), gg = weeklyOnDays(s, D.d, s && s.g);
    return m.map((v, i) => { if (!fin(v) || v <= 0) return null; const e = el[i], dir = gg[i];
      const b = fin(e) && e > 0 ? Math.exp((1 - w) * Math.log(v) + w * Math.log(e)) : v; return b * (1 + g * (fin(dir) ? dir : 0)); });
  }
  const lensOf = (opt, n) => [...new Set([...(opt.nd || []), ...(fin(opt.xx) ? [Math.round(opt.xx)] : [])])].filter((x) => x >= 2 && x <= n).sort((a, b) => a - b);
  const colOf = (L, opt) => (NCOL[L] ? NCOL[L] : XCOL);
  function dailyChart(D, s, opt, width) {
    const n = D.p.length, k0 = Math.max(0, n - opt.range), m = n - k0;
    if (m < 5) return '<p class="muted">Not enough daily closes to draw.</p>';
    const Wd = Math.max(340, Math.min(860, width || 760)), Ht = Wd < 500 ? 300 : 340, L = 52, R = 34, T = 12, B = 26;
    const lens = lensOf(opt, n), H = dailyHybrid(D, s, opt.base, opt.w, opt.g);
    const lines = lens.map((N) => ({ N, a: sma(D.p, N).slice(k0), col: colOf(N, opt), dash: NCOL[N] ? '' : '6 3' }));
    const P = D.p.slice(k0), Hv = H.slice(k0), dates = D.d.slice(k0);
    const vals = [P, Hv, ...lines.map((x) => x.a)].flatMap((a) => a.filter((v) => fin(v) && v > 0));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pmin = Math.min(...P.filter(fin)), pmax = Math.max(...P.filter(fin));
    lo = Math.max(lo, pmin / 2); hi = Math.min(hi, pmax * 2);
    const ly = Math.log, y0 = ly(lo) - 0.03 * (ly(hi) - ly(lo)), y1 = ly(hi) + 0.03 * (ly(hi) - ly(lo));
    const sx = (k) => L + (Wd - L - R) * k / Math.max(1, m - 1), sy = (v) => T + (Ht - T - B) * (1 - (ly(Math.min(Math.max(v, lo), hi)) - y0) / (y1 - y0));
    const f = (v) => v.toFixed(1);
    let out = `<svg viewBox="0 0 ${Wd} ${Ht}" role="img" aria-label="${esc(s ? s.id : '')}: daily close and its ${esc(lens.join(', '))}-day averages">`;
    const ticks = [], span = Math.log10(hi / lo), step = Math.pow(10, Math.floor(Math.log10(Math.max(hi - lo, 1e-9)))) * (span > 0.6 ? 1 : 0.5);
    for (let v = Math.ceil(lo / step) * step; v <= hi && ticks.length < 9; v += step) ticks.push(v);
    ticks.forEach((v) => { out += `<line class="mh-grid" x1="${L}" x2="${Wd - R}" y1="${f(sy(v))}" y2="${f(sy(v))}"/><text class="mh-t" x="${L - 5}" y="${f(sy(v) + 4)}" text-anchor="end">${esc(usd(v))}</text>`; });
    const starts = []; dates.forEach((d, k) => { if (k > 0 && d.slice(0, 7) !== dates[k - 1].slice(0, 7)) starts.push(k); });
    const maxL = Math.max(2, Math.floor((Wd - L - R) / 46)), stp = [1, 2, 3, 6, 12].find((q) => starts.length / q <= maxL) || 12;
    starts.forEach((k) => { const y = +dates[k].slice(0, 4), mo = +dates[k].slice(5, 7); if (((y * 12) + mo - 1) % stp) return;
      out += `<line class="mh-grid" x1="${f(sx(k))}" x2="${f(sx(k))}" y1="${T}" y2="${Ht - B}"/><text class="mh-t" x="${f(sx(k))}" y="${Ht - 8}" text-anchor="middle">${mo === 1 ? y : MON[mo - 1]}</text>`; });
    const path = (a, col, wdt, dash) => {
      let d = '', pen = false;
      a.forEach((v, k) => { if (fin(v) && v > 0) { d += (pen ? 'L' : 'M') + f(sx(k)) + ',' + f(sy(v)); pen = true; } else pen = false; });
      return d ? `<path d="${d}" style="fill:none;stroke:${col};stroke-width:${wdt};${dash ? 'stroke-dasharray:' + dash + ';' : ''}stroke-linejoin:round"/>` : '';
    };
    lines.slice().reverse().forEach((x) => { out += path(x.a, x.col, 1.4, x.dash); });
    if (opt.hybrid !== false) out += path(Hv, COL.h, 2.4, '');
    out += path(P, COL.p, 1.3, '');
    const tags = lines.map((x) => ({ y: fin(x.a[m - 1]) ? sy(x.a[m - 1]) : null, t: String(x.N), col: x.col })).filter((x) => x.y != null)
      .concat(opt.hybrid !== false && fin(Hv[m - 1]) ? [{ y: sy(Hv[m - 1]), t: 'H', col: COL.h }] : []).sort((a, b) => a.y - b.y);
    for (let i = 1; i < tags.length; i += 1) if (tags[i].y - tags[i - 1].y < 11) tags[i].y = tags[i - 1].y + 11;   // labels kept apart
    tags.forEach((x) => { out += `<text class="mh-t" x="${Wd - R + 4}" y="${f(Math.min(Ht - B, x.y + 4))}" style="fill:${x.col};font-weight:600">${esc(x.t)}</text>`; });
    return out + '</svg>';
  }
  function dailyControls(opt, n) {
    const boxes = NDAYS.map((N) => `<label class="mh-nd"><input type="checkbox" data-mh-nd="${N}"${(opt.nd || []).includes(N) ? ' checked' : ''}${N > n ? ' disabled' : ''}><b style="background:${NCOL[N]}"></b>${N}</label>`).join('');
    return `<div class="mh-ctl"><span class="mh-seg">${RANGES.map(([r, lab]) => `<button type="button" data-mh-range="${r}" class="${r === opt.range ? 'on' : ''}">${lab}</button>`).join('')}</span>
      <span>Daily averages (days):</span>${boxes}<label>XX-day <input type="number" min="2" max="${Math.min(n, 750)}" step="1" data-mh-xx value="${fin(opt.xx) ? Math.round(opt.xx) : ''}" placeholder="e.g. 89"></label>
      <label>Hybrid line on the <select data-mh-base>${BASES.map((b) => `<option value="${b}"${b === opt.base ? ' selected' : ''}>${b}-day</option>`).join('')}</select> average</label></div>`;
  }
  const dailyLegend = (opt, lens) => `<div class="mh-legend"><span><b style="background:${COL.p}"></b>daily close</span>${lens.map((N) => `<span><b style="background:${colOf(N, opt)}${NCOL[N] ? '' : ';height:2px'}"></b>${N}-day average${NCOL[N] ? '' : ' (yours)'}</span>`).join('')}
    <span><b style="background:${COL.h};height:4px"></b>hybrid line H: the ${opt.base}-day average with ${pct(opt.w)} earnings line and ${pct(opt.g)} per guidance change</span></div>`;
  function ndayCell(d, kind, N, h, src) {                                        // what "above" has paid for one length
    const nd = (d.scores || {}).ndays || {};
    if (src === 'daily') { const D = nd.daily || {}, p0 = (D.periods || [])[0]; return st(((((D[h] || {})[`${kind}:${N}`] || {}).periods || {})[p0] || {}).net); }
    const W = (nd.weekly || {})[h] || {}, p0 = periodsOf(d)[0]; return st((((W[`${kind}:${N}`] || {})[p0]) || {}).net);
  }
  function dailyTable(d, D, opt) {
    const n = D.p.length, P = D.p[n - 1], nd = (d.scores || {}).ndays || {}, Dy = nd.daily || {}, dp = (Dy.periods || [])[0] || 'daily', wp = periodsOf(d)[0] || '';
    const tested = (N) => NDAYS.includes(N);
    const rows = lensOf(opt, n).map((N) => { const a = sma(D.p, N), v = a[n - 1];
      return [`<b style="color:${colOf(N, opt)}">${N}-day</b>${tested(N) ? '' : ' <span class="muted">(yours)</span>'}`, usd(v), gap(fin(v) ? Math.log(P / v) : null),
        ...(tested(N) ? [ndayCell(d, 'above', N, '13', 'daily'), ndayCell(d, 'above', N, '26', 'daily'), N === 5 ? '<span class="muted">needs daily closes</span>' : ndayCell(d, 'above', N, '26', 'weekly')]
          : ['<span class="muted">not one of the lengths tested</span>', '', '']) ]; });
    const m50 = sma(D.p, 50)[n - 1], m200 = sma(D.p, 200)[n - 1];
    if (fin(m50) && fin(m200)) rows.push([`50-day vs the 200-day`, `${usd(m50)} / ${usd(m200)}`, gap(Math.log(m50 / m200)), ndayCell(d, 'cross', '50/200', '13', 'daily'), ndayCell(d, 'cross', '50/200', '26', 'daily'), ndayCell(d, 'cross', '50/200', '26', 'weekly')]);
    return tbl(['Average', 'Now', 'Price vs it', `Above − below: 13 weeks, ${esc(dp)}`, '26 weeks', `26 weeks, weekly form, ${esc(wp)}`], rows, [0, 1, 1, 1, 1, 1]) +
      `<p class="mh-note">Every company with daily bars each Friday: those above the average against those below it, simple returns against SPY over the next 13 or 26 weeks, after trading costs. ${Dy.companies ? `About ${num(Dy.companies)} companies a week from ${esc(Dy.from)}` : ''}; the last column is every company from ${esc(d.test_from)}, with the average in its weekly form (the N/5-week average of weekly closes). Negative: being above the average was followed by doing worse — a short average read as a turning point, not a trend.</p>`;
  }
  function dailySection(D, s, d, opt, width) {
    if (!D) return `<p class="muted">No daily bars on file for this company (research-paths keeps them for ${num(((d.daily || {}).companies) || 0)} of this week's ${num(d.now)} companies).</p>`;
    const n = D.p.length, lens = lensOf(opt, n);
    return dailyControls(opt, n) + `<div class="mh-chart" data-mh-daily>${dailyChart(D, s, opt, width)}</div>` + dailyLegend(opt, lens) +
      `<p class="mh-note">Daily closes through ${esc(D.asof)} (Yahoo, split-adjusted, research-paths' daily bars). Pick any of the lengths or type your own; the earnings line and guidance in H are the weekly ones, each day using its latest Friday's.</p>` + dailyTable(d, D, opt);
  }

  // ------------------------------------------------------------------ the macro
  const fmtM = (v, unit) => (fin(v) ? (v < 0 ? '−' : '') + (unit === '%' ? num(Math.abs(v), Math.abs(v) < 10 ? 1 : 0) + '%' : unit === 'pts' ? num(Math.abs(v), 2) + ' pts' : num(Math.abs(v), Math.abs(v) < 10 ? 2 : 1)) : '—');
  const THIRD = ['low third', 'middle third', 'high third'];
  function macroRegimes(d, h, keys) {
    const R = (((d.scores || {}).macro || {}).regimes) || null; if (!R || !R[h]) return '';
    const ks = (keys || Object.keys(R.readings || {})).filter((k) => R[h][k]);
    const rows = ks.map((k) => { const nw = (R.now || {})[k] || {}, rd = (R.readings || {})[k] || {}, cells = R[h][k] || [];
      return { cells: [esc(rd.label || k), `${fmtM(nw.value, rd.unit)} <span class="muted">${nw.third >= 0 ? THIRD[nw.third] : ''}</span>`, ...[0, 1, 2].map((j) => (j === nw.third ? `<span data-cur>${st(cells[j])}</span>` : st(cells[j])))] }; });
    const html = tbl(['Reading', 'Now', 'Low third', 'Middle third', 'High third'], rows, [0, 0, 1, 1, 1]);
    return html.replace(/<td class="n"><span data-cur>/g, '<td class="n cur"><span>');
  }
  function macroNow(d) {
    const M = (d.scores || {}).macro; if (!M || !M.index) return '';
    const I = M.index, n = I.now || {}, spy = ((I.funds || {}).SPY || {}).now;
    const rules = Object.keys(I.rules || {}).filter((r) => r !== 'hold');
    return `${spy ? `SPY ${gap(spy.gap40)} vs its 40-week average · ` : ''}unemployment ${fmtM(n.unrate, '%')} vs its 12-month average ${fmtM(n.unrate12, '%')} (${n.unemp_up ? 'rising' : 'not rising'}) · Sahm rule ${num(n.sahm3, 2)} (${n.sahm_on ? 'on' : 'off'}; on at ${num(I.sahm_on, 1)})` +
      (spy ? ` → SPY under ${rules.map((r) => `${esc(RULE_SHORT[r] || r)}: ${spy.in[r] ? 'in' : '<b>out</b>'}`).join(' · ')}` : '');
  }
  function macroSection(d) {
    const M = (d.scores || {}).macro; if (!M) return '';
    const R = M.regimes || {}, all = ((R['26'] || {}).all);
    return `<details><summary><b>Macro now</b> — ${macroNow(d)}</summary><p class="mh-sub">What "price above its 40-week average" paid (above − below, 26 weeks, after costs) in each third of each reading's own history since 1995, ${esc(R.period || '')}; today's third is outlined. In all weeks: ${st(all)}.</p>${macroRegimes(d, '26', ['vix', 'credit', 'dcredit', 'curve', 'claims', 'cpi'])}
      <p class="mh-note">${num(R.tests)} comparisons across the readings: by chance alone a few would show |t| above 2, so read a single cell as a hint, not a rule. The hub has all twelve readings and the 13-week view.</p></details>`;
  }

  // ------------------------------------------------------------------ one company
  function periodsOf(d) { const m = (((d.scores || {}).models || {})['26'] || {}).ma || {}; return Object.keys(m); }
  function controls(id, w, g) {
    return `<div class="mh-ctl"><label>Earnings line in the mix <select data-mh="w" id="${id}-w">${WS.map((v) => `<option value="${v}"${v === w ? ' selected' : ''}>${pct(v)}</option>`).join('')}</select></label>
      <label>Guidance moves the line by <select data-mh="g" id="${id}-g">${GS.map((v) => `<option value="${v}"${v === g ? ' selected' : ''}>${pct(v)}</option>`).join('')}</select></label></div>`;
  }
  function weightScores(d, w, g) {
    const P = periodsOf(d), Lw = (d.scores || {}).lines || {};
    const row = (h, k) => { const s = (Lw[h] || {})[k] || {}; return P.map((p) => st((s[p] || {}).net)); };
    const pick = (h) => { const by = ((((d.scores || {}).picks || {})[h] || {}).by_year) || {}; const ys = Object.keys(by).sort(); const p = ys.length ? by[ys[ys.length - 1]] : null;
      return p ? `${pct(p.w)} / ${pct(p.g)}, read as ${p.reading === 'trend' ? 'trend (above the line paid)' : 'value (below the line paid)'}` : '—'; };
    const rows = [];
    for (const h of ['13', '26']) {
      rows.push({ on: true, cells: [`Hybrid line (${pct(w)} / ${pct(g)}), ${h} weeks`, ...row(h, key(w, g))] });
      rows.push([`40-week average alone, ${h} weeks`, ...row(h, key(0, 0))]);
    }
    return tbl(['Above − below the line, after costs', ...P.map(esc)], rows, [0, 1, 1, 1]) +
      `<p class="mh-note">Every liquid company each week: those above the line against those below it, simple returns against SPY over the next 13 or 26 weeks, after trading costs, from ${esc(d.test_from)}. Positive: being above the line paid (a trend reading); negative: being below it did (a value reading). The weights picked this year from the years before: 13 weeks ${pick('13')}; 26 weeks ${pick('26')}.</p>`;
  }
  function companyHtml(s, d, row, w, g, width, id, dd) {
    const n = s.p.length, k = n - 1, H = hybrid(s, w, g), P = s.p[k];
    const lg = (a, b) => (fin(a) && fin(b) && a > 0 && b > 0 ? Math.log(a / b) : null);
    const gl = (s.guidance || []).slice(-1)[0];
    const D = dd && dd.p && dd.p.length > 1 ? dailyOf(dd) : null;
    const opt = { nd: ui.nd, xx: ui.xx, range: ui.range, base: ui.base, w, g };
    const cards = [];
    if (D) {
      const nD = D.p.length, m50 = sma(D.p, 50)[nD - 1], m200 = sma(D.p, 200)[nD - 1];
      let cross = null;                                                           // the latest 50/200-day cross in the file
      const a50 = sma(D.p, 50), a200 = sma(D.p, 200);
      for (let i = nD - 1; i > 0 && !cross; i -= 1) if (fin(a50[i]) && fin(a200[i]) && fin(a50[i - 1]) && fin(a200[i - 1]) && Math.sign(a50[i] - a200[i]) !== Math.sign(a50[i - 1] - a200[i - 1])) cross = [D.d[i], a50[i] > a200[i] ? 1 : -1];
      cards.push(['Daily close', usd(D.p[nD - 1]), `${esc(D.asof)}`]);
      if (fin(m50) && fin(m200)) cards.push(['50-day vs 200-day', gap(Math.log(m50 / m200)), cross ? `${cross[1] > 0 ? 'above since the golden cross' : 'below since the death cross'} of ${esc(cross[0])}` : (m50 > m200 ? 'above' : 'below') + ' all through the file']);
    }
    cards.push(
      ['Weekly close', usd(P), `week ending ${esc(weekDate(s, k))}`],
      ['vs 40-week average', gap(lg(P, s.ma40[k])), usd(s.ma40[k]) + ' (≈ 200-day)'],
      ['vs 10-week average', gap(lg(P, s.ma10[k])), usd(s.ma10[k]) + ' (≈ 50-day)'],
      ['vs earnings line', fin(s.el[k]) ? gap(lg(P, s.el[k])) : '—', fin(s.el[k]) ? `${usd(s.el[k])}${row && fin(row.pe) ? ` · P/E ${num(row.pe, 1)} vs its median ${num(row.pe_med, 1)}` : ''}` : 'no line: earnings not positive or under 3 years of P/E'],
      ['vs hybrid line', gap(lg(P, H[k])), usd(H[k])],
      ['Guidance', gl ? esc(GLAB[gl[1]] || gl[1]) : '—', gl ? `latest release ${esc(gl[0])}` : 'none in the hub\'s record']);
    if (row && fin(row.pct_hybrid)) cards.push(['Models\' rank, 26 weeks', pct(row.pct_hybrid), `moving averages + fundamentals + guidance · alone: ${pct(row.pct_ma)}${fin(row.pct_macro) ? ` · × macro: ${pct(row.pct_macro)}` : ''}`]);
    const V = (row && row.val) || null, MD = (row && row.mdna) || null;            // recorded each week, not in the line
    if (V) {
      const dcf = fin(V.dcf_value) && V.dcf_value > 0 ? V.dcf_value : null;
      cards.push(['vs DCF value (Fair value page)', dcf ? gap(lg(P, dcf)) : '—', dcf ? `${usd(dcf)}${fin(V.mc_p10) ? ` · Monte Carlo 10–90%: ${usd(V.mc_p10)}–${usd(V.mc_p90)}` : ''}` : `no DCF for this kind of company${V.kind ? ' (' + esc(V.kind) + ')' : ''}`]);
      if (fin(V.mc_p_above) || fin(V.p_implied)) cards.push(['Odds', fin(V.mc_p_above) ? pct(V.mc_p_above) : pct(V.p_implied), fin(V.mc_p_above) ? `the DCF's chance that value exceeds the price${fin(V.p_implied) ? ` · the growth the price implies has been reached ${pct(V.p_implied)} of the time` : ''}` : 'how often companies reached the growth the price implies']);
    }
    if (MD) cards.push(['MD&A tone', `${MD.tone > 0 ? '+' : MD.tone < 0 ? '−' : ''}${num(Math.abs(MD.tone), 2)}`, `${num(MD.n)} forward-looking statements, ${num(MD.positive)} positive, ${num(MD.negative)} negative · ${esc(MD.form || '')} ${esc(MD.filed)}`]);
    let out = `<div class="mh-cards">${cards.map(([a, b, c]) => `<div class="mh-card"><span>${a}</span><b>${b}</b><i>${c}</i></div>`).join('')}</div>`;
    out += controls(id, w, g);
    out += `<h4>Daily — any N-day average</h4>` + dailySection(D, s, d, opt, width);
    out += `<h4>Weekly — the hybrid line</h4><div class="mh-chart" data-mh-chart>${chart(s, w, g, width)}</div>` + legend(w, g);
    out += `<h4>What these weights have been worth</h4>` + weightScores(d, w, g);
    if (V || MD) out += `<p class="mh-note">The DCF value, its odds and the MD&A tone are this week's numbers from the Fair value page and the company's latest 10-Q / 10-K; their history is too short to test them as part of the line (the Fair value page's own walk-forward starts in 2022, the MD&A record in 2024), so they are shown and frozen every week, and scored as the record grows.</p>`;
    out += macroSection(d);
    return out;
  }
  function bindDaily(el, redraw) {                                                // the daily chart's controls
    el.querySelectorAll('[data-mh-nd]').forEach((x) => { x.onchange = () => { const N = Number(x.dataset.mhNd);
      ui.nd = x.checked ? [...new Set([...ui.nd, N])] : ui.nd.filter((v) => v !== N); keep(); redraw(); }; });
    el.querySelectorAll('[data-mh-range]').forEach((b) => { b.onclick = () => { ui.range = Number(b.dataset.mhRange); keep(); redraw(); }; });
    const xx = el.querySelector('[data-mh-xx]');
    if (xx) xx.onchange = () => { const v = Math.round(Number(xx.value)); ui.xx = xx.value !== '' && Number.isFinite(v) && v >= 2 ? Math.min(v, 750) : null; keep(); redraw(); };
    const bs = el.querySelector('[data-mh-base]');
    if (bs) bs.onchange = () => { ui.base = Number(bs.value); keep(); redraw(); };
  }
  function lead(d) {
    const M = ((d.scores || {}).models || {})['26'] || {}, P = periodsOf(d), all = P[0], late = P[2];
    const a = (M.ma || {})[all] || {}, h = (M.hybrid || {})[all] || {}, al = (M.ma || {})[late] || {}, ae = (M.ma || {})[P[1]] || {};
    const ge = ((d.scores || {}).guidance_events || {})['13'] || {}, gr = ge.raised;
    return `<p class="mh-sub">The usual moving averages read as a trend: a price above its 40-week (≈ 200-day) average is said to be in an uptrend. Here the company's earnings (its earnings line, at its own usual P/E) and its guidance are mixed into the line, weighted, and every mix is tested walk-forward from ${esc(d.test_from)} on ${num(d.now)} liquid companies this week. ` +
      (a.net ? `Ranked by the moving averages alone, the best fifth of companies beat the worst by ${spct(a.net.mean, 1)} over 26 weeks after trading costs (t ${num(a.net.t, 1)}) — ${ae.net ? spct(ae.net.mean, 1) : '—'} in ${esc(P[1])}, ${al.net ? spct(al.net.mean, 1) : '—'} from ${esc(late.slice(0, 4))}. ` : '') +
      (h.net ? `With fundamentals and guidance added the rank correlation hardly moved (${num((h.ic || {}).mean, 3)} against ${num((a.ic || {}).mean, 3)}) and the basket did worse: ${spct(h.net.mean, 1)}. ` : '') +
      (gr ? `Guidance itself, ${esc(((d.scores || {}).guidance_events || {}).years ? d.scores.guidance_events.years.join('–') : '')} only: in the 13 weeks after a raise the company beat the average company by ${spct(gr.mean, 1)} (t ${num(gr.t, 1)}, ${num(gr.n)} releases). ` : '') +
      'Simple returns against SPY; history and models, not investment advice.</p>' + lead2(d);
  }
  function lead2(d) {                                                              // the daily averages and the macro, in one paragraph
    const S = d.scores || {}, nd = S.ndays || {}, Dy = nd.daily || {}, p0 = (Dy.periods || [])[0], cell = (h, k) => (((((Dy[h] || {})[k] || {}).periods || {})[p0] || {}).net);
    const I = (S.macro || {}).index || {}, spy = (I.funds || {}).SPY, P = I.periods || [], all = P[0], late = P[2];
    const MM = ((S.models || {})['26'] || {}), mm = ((MM.ma_macro || {})[periodsOf(d)[0]] || {}).net, ma = ((MM.ma || {})[periodsOf(d)[0]] || {}).net;
    const y20 = ((S.net_by_year || {})['26'] || {});
    const parts = [];
    if (p0 && cell('13', 'above:20')) parts.push(`Daily averages, on daily closes ${esc(p0)}: being above a short one was followed by doing worse — above the 20-day ${spct(cell('13', 'above:20').mean, 1)} over 13 weeks against those below it (t ${num(cell('13', 'above:20').t, 1)}) — and only the long ones leaned to trend: the 200-day ${spct((cell('26', 'above:200') || {}).mean, 1)} over 26 weeks, the 50/200 golden cross ${spct((cell('26', 'cross:50/200') || {}).mean, 1)}, neither reliable.`);
    if (spy && spy.rules && spy.rules.hold && spy.rules.hold[all]) {
      const r = spy.rules, c = (k, p) => ((r[k] || {})[p] || {});
      parts.push(`The macro, for SPY ${esc(all)}: holding made ${pct(c('hold', all).cagr, 1)} a year (worst fall ${spct(c('hold', all).maxdd, 0)}); the 40-week rule ${pct(c('above40', all).cagr, 1)} (${spct(c('above40', all).maxdd, 0)}); out only when unemployment was also rising ${pct(c('trend_unemployment', all).cagr, 1)} (${spct(c('trend_unemployment', all).maxdd, 0)}) — but from ${esc(String(late || '').slice(0, 4))}, after these rules were published, ${pct(c('trend_unemployment', late).cagr, 1)} against ${pct(c('hold', late).cagr, 1)} for holding.`);
    }
    if (mm && ma) parts.push(`Letting each company's trend weigh more or less with the macro ranked better (best − worst fifth ${spct(mm.mean, 1)} over 26 weeks against ${spct(ma.mean, 1)}), nearly all of it in 2020 (${spct((y20.ma_macro || {})['2020'], 1)} against ${spct((y20.ma || {})['2020'], 1)}) and not when the readings are scaled on 2009 on only — recorded, not in the line.`);
    return parts.length ? `<p class="mh-sub">${parts.join(' ')}</p>` : '';
  }

  async function render(el, ctx) {
    css();
    const hub = (ctx && ctx.hub != null ? ctx.hub : ''), base = hub + 'data/market/history/';
    const T = String((ctx && ctx.ticker) || '').toUpperCase().replace(/\./g, '-');
    if (!T) { el.innerHTML = '<p class="muted">No ticker: the moving averages need a share price.</p>'; return; }
    el.innerHTML = '<p class="muted">Loading the moving averages…</p>';
    let s, d, dd;
    try { [s, d, dd] = await Promise.all([get(base + 'ma/' + T + '.json').catch(() => null), get(base + 'ma-hybrid.json'), get(base + 'ma-daily/' + T + '.json').catch(() => null)]); } catch (e) {
      el.innerHTML = `<p class="muted">Moving averages+ could not load (${esc(e.message)}).</p>`; return;
    }
    if (ctx && ctx.here && !ctx.here()) return;
    if (!s) { el.innerHTML = `<p class="muted">${esc(T)} is not in this week's set: it needs weekly prices and first-filed quarterly figures, a close of at least $3 and $10M traded a week.</p>`; return; }
    const row = s.now || null;
    const draw = () => {
      const w = ui.w != null ? ui.w : (d.weights || {}).default ? d.weights.default[0] : 0.5, g = ui.g != null ? ui.g : (d.weights || {}).default ? d.weights.default[1] : 0.05;
      const keepOpen = !!el.querySelector('.mh details[open]');
      el.innerHTML = `<div class="mh"><h3>${esc(T)} — moving averages, daily and weekly, with earnings, guidance and the macro</h3>${lead(d)}${companyHtml(s, d, row, w, g, el.clientWidth || 760, 'mh-' + T, dd)}</div>`;
      if (keepOpen) el.querySelectorAll('.mh details').forEach((x) => { x.open = true; });
      el.querySelectorAll('select[data-mh]').forEach((x) => { x.onchange = () => { ui[x.dataset.mh] = Number(x.value); draw(); }; });
      bindDaily(el, draw);
    };
    draw();
  }

  // ------------------------------------------------------------------ the hub
  function hubTables(d) {
    const S = d.scores || {}, P = periodsOf(d), out = [];
    const mods = (h) => MODEL_ORDER.map((m) => { const r = ((S.models || {})[h] || {})[m] || {};
      return [esc(((d.models || {})[m] || {}).name || m), ...P.map((p) => icTxt((r[p] || {}).ic)), ...P.map((p) => st((r[p] || {}).net))]; });
    for (const h of ['13', '26']) {
      out.push(`<h4>The models, ${h} weeks ahead</h4>` + tbl(['Model', ...P.map((p) => 'Rank corr. ' + esc(p)), ...P.map((p) => 'Best − worst fifth, net, ' + esc(p))], mods(h), [0, 1, 1, 1, 1, 1, 1]));
    }
    const nby = (S.net_by_year || {})['26'] || {}, iby = (S.ic_by_year || {})['26'] || {};
    if (((S.models || {})['26'] || {}).ma_macro && nby.ma_macro && nby.ma) {
      out.push(`<p class="mh-note">Moving averages × macro: the moving-average inputs, plus the 40-week and the 10-week trend each multiplied by five macro readings (VIX, the credit spread and its 13-week change, jobless claims year on year, the yield curve), each scaled on its own history since 1995 as known each week — so the trend can count more, less or the other way round as the macro moves. Its lead over the averages alone is mostly 2020: ${spct(nby.ma_macro['2020'], 1)} against ${spct(nby.ma['2020'], 1)} over 26 weeks (rank correlation ${num(iby.ma_macro['2020'], 3)} against ${num(iby.ma['2020'], 3)}), when it turned to the panic's losers, which rebounded — the trend's well-known crash after a market fall. Scaled on 2009 on only (the last row) the same model did no better than the averages alone. So it is recorded and frozen every week as a model of its own, and the line has no macro in it.</p>`);
    }
    out.push(ndayTables(d));
    const rules = (h) => [['above40', 'Price above its 40-week average'], ['cross', '10-week average above the 40-week']].map(([k, n]) => {
      const r = ((S.rules || {})[h] || {})[k] || {}; return [esc(n) + `, ${h} weeks`, ...P.map((p) => st((r[p] || {}).net))]; });
    out.push('<h4>The classic rules</h4>' + tbl(['Above − below, after costs', ...P.map(esc)], rules('13').concat(rules('26')), [0, 1, 1, 1]));
    for (const h of ['13', '26']) {
      const Lw = (S.lines || {})[h] || {}, all = P[0];
      let best = null;
      WS.forEach((w) => GS.forEach((g) => { const v = ((Lw[key(w, g)] || {})[all] || {}).net; if (v && fin(v.mean) && (!best || v.mean > best[0])) best = [v.mean, w, g]; }));
      const rows = WS.map((w) => ({ on: best && best[1] === w, cells: [pct(w) + ' earnings line', ...GS.map((g) => st(((Lw[key(w, g)] || {})[all] || {}).net))] }));
      out.push(`<h4>Every weight on the grid, ${h} weeks, ${esc(all)}: above − below the hybrid line, after costs</h4>` + tbl(['', ...GS.map((g) => 'guidance ' + pct(g))], rows, [0, 1, 1, 1]));
      const pk = ((S.picks || {})[h] || {}), by = pk.by_year || {};
      out.push(`<p class="mh-note">Picked each year from the years before (weight, guidance, reading): ${Object.entries(by).map(([y, p]) => `${y} ${pct(p.w)}/${pct(p.g)} ${p.reading}`).join(' · ')}. Out of sample, the picks made ${st((((pk.oos || {})[all]) || {}).net)}.</p>`);
    }
    const ge = S.guidance_events || {};
    const labs = Object.keys(ge['13'] || {});
    if (labs.length) {
      out.push(`<h4>What followed each kind of guidance release (${esc((ge.years || []).join('–'))})</h4>` + tbl(['Release', 'Releases', '4 weeks vs the average company', '13 weeks', 'Beat the average, 13 weeks'],
        labs.map((l) => { const a = (ge['4'] || {})[l] || {}, b = ge['13'][l] || {}; return [esc(GLAB[l] || l), num(b.n), st(a), st(b), pct(b.beat)]; }), [0, 1, 1, 1, 1]) +
        '<p class="mh-note">From the first weekly close after the release (the day\'s reaction is not in it), simple returns against SPY less the average company\'s that week; the t treats releases as independent although many fall in the same weeks. The hub\'s guidance record starts in 2023 and is thin before 2024.</p>');
    }
    const cf = (((S.coefs || {})['26'] || {}).hybrid || {}), yrs = Object.keys(cf).sort(), last = yrs[yrs.length - 1];
    if (last) out.push(`<h4>The 26-week model's weights now (fitted on the years to ${esc(last - 1)})</h4>` + tbl(['Input', 'Return against the average company, 26 weeks'], Object.entries(cf[last]).map(([k, v]) => [esc((d.features || {})[k] || k), sgn(v, spct(v, 2))]), [0, 1]) +
      '<p class="mh-note">Per standard deviation of each input across the companies that week (log returns, before costs); guidance per raise (a cut counts −1), so its weight comes only from the years the guidance record covers (from 2023, thin before 2024).</p>');
    const me = S.mdna_events, vm = d._valuationModels;
    if ((me && me['13'] && Object.keys(me['13']).length) || vm) {
      let part = `<h4>Valuation, odds and MD&A — recorded each week, not yet in the line</h4>`;
      if (vm) {
        const fi = (h) => ((((vm.combined || {}).horizons || {})[h] || {}).feature_ic) || {};
        const names = { dcf_gap: 'DCF value vs price', pe_gap: 'Peer-median P/E × EPS vs price', p_implied: 'Chance of the growth the price implies', target_gap: 'Analysts\' target vs price' };
        const ks = Object.keys(names).filter((k) => fi('3m')[k] || fi('12m')[k]);
        if (ks.length) part += tbl(['The Fair value page\'s own walk-forward', 'Rank corr., 3 months', '12 months', 'Quarters'], ks.map((k) => [esc(names[k]), fin((fi('3m')[k] || {}).ic_mean) ? num(fi('3m')[k].ic_mean, 3) : '—', fin((fi('12m')[k] || {}).ic_mean) ? num(fi('12m')[k].ic_mean, 3) : '—', num((fi('3m')[k] || {}).origins)]), [0, 1, 1, 1]);
      }
      if (me && me['13']) {
        const labs = Object.keys(me['13']);
        part += tbl([`After an MD&A, by its tone (${esc((me.years || []).join('–'))}, ${num(me.filings)} filings)`, 'Filings with 13 weeks since', '4 weeks vs the average company', '13 weeks'],
          labs.map((l) => [esc(l), num(me['13'][l].n), st((me['4'] || {})[l]), st(me['13'][l])]), [0, 1, 1, 1]);
      }
      out.push(part + '<p class="mh-note">Tone: positive − negative over the forward-looking statements read from the MD&A (pipeline/outlook.py, no language model). Too few seasons to lean on; the frozen record scores the DCF gap, the odds and the tone week by week from here.</p>');
    }
    out.push(fundTables(d), regimeTables(d));
    const Lg = d.ledger;
    out.push('<h4>Frozen record</h4>' + (Lg ? tbl(['Horizon', 'Weeks scored', 'Waiting', 'Rank corr.', 'Best − worst fifth', 'Above − below the 40-week'],
      Object.entries(Lg).map(([k, s]) => [esc(k.replace('ma:', '') + ' weeks'), num(s.resolved_weeks), num(s.pending_weeks), fin(s.ic) ? num(s.ic, 3) : '—', fin(s.best_minus_worst) ? spct(s.best_minus_worst, 2) : '—', fin(s.above_minus_below40) ? spct(s.above_minus_below40, 2) : '—']), [0, 1, 1, 1, 1, 1])
      : '<p class="muted">The record starts with the first closed week after this page went live.</p>'));
    out.push(`<p class="mh-note">Rank correlation: between the model's forecast and the next return against SPY across the companies, every week, averaged; the t counts weeks ÷ horizon as independent. Baskets: simple returns (what an equal-weighted basket earns), trading costs one way by weekly dollar volume (${(d.costs_bp || []).map((c) => `${num(c[1])} bp above $${num(c[0] / 1e6)}M`).join(', ')}), both legs in and out, no borrow fee. The earnings line counts a quarter from the first weekly close after its first filing; companies without positive earnings or three years of P/E use the 40-week average alone. Today's companies only: delisted names are missing.</p>`);
    return out.join('');
  }
  function listHtml(rows, w, g, recent) {
    const R = (rows || []).filter((r) => fin(r.gap_hybrid));
    const top = R.slice().sort((a, b) => b.gap_hybrid - a.gap_hybrid).slice(0, 15), bot = R.slice().sort((a, b) => a.gap_hybrid - b.gap_hybrid).slice(0, 15);
    const who = (r) => `<a href="#" data-mh-t="${esc(r.id)}">${esc(r.id)}</a> <span class="muted">${esc(r.name || '')}</span>`;
    const cells = (r) => [who(r), usd(r.close), gap(r.gap40), r.el ? gap(Math.log(r.close / r.el)) : '—', gap(r.gap_hybrid), r.guid_last ? esc(GLAB[r.guid_last[1]] || r.guid_last[1]) : '—', pct(r.pct_hybrid)];
    const head = ['Company', 'Close', 'vs 40-week', 'vs earnings line', 'vs hybrid line', 'Latest guidance', 'Models\' rank, 26w'];
    let out = `<h4>Furthest above the hybrid line (${pct(w)} / ${pct(g)})</h4>` + tbl(head, top.map(cells), [0, 1, 1, 1, 1, 0, 1]) + `<h4>Furthest below it</h4>` + tbl(head, bot.map(cells), [0, 1, 1, 1, 1, 0, 1]);
    const lim = fin(recent) ? recent : 10, X = (rows || []).filter((r) => Array.isArray(r.x50_200) && r.x50_200[2] <= lim);
    const xc = (r) => [who(r), usd(r.d_close), esc(r.x50_200[0]), gap(r.d50), gap(r.d200), gap(r.gap_hybrid)];
    const xh = ['Company', 'Daily close', 'Crossed', 'vs 50-day', 'vs 200-day', 'vs hybrid line'];
    for (const [dir, name] of [[1, 'Golden crosses: the 50-day average crossed above the 200-day'], [-1, 'Death crosses: the 50-day crossed below the 200-day']]) {
      const L = X.filter((r) => r.x50_200[1] === dir).sort((a, b) => a.x50_200[2] - b.x50_200[2] || (b.d200 || 0) - (a.d200 || 0)).slice(0, 20);
      out += `<h4>${name}, last ${num(lim)} trading days (${num(X.filter((r) => r.x50_200[1] === dir).length)})</h4>` + (L.length ? tbl(xh, L.map(xc), [0, 1, 0, 1, 1, 1]) : '<p class="muted">None.</p>');
    }
    return out;
  }
  function ndayTables(d) {
    const nd = (d.scores || {}).ndays; if (!nd) return '';
    const P = periodsOf(d), Dy = nd.daily || {}, DP = (Dy.periods || []).filter((_, i, a) => a.length < 3 || i !== 1);   // the daily test's first year or so alone adds little
    const names = [...(nd.n || []).map((N) => [`above:${N}`, `Above its ${N}-day`]), ...(nd.crosses || []).map(([a, b]) => [`cross:${a}/${b}`, `${a}-day above the ${b}-day`])];
    const yy = (p) => String(p).replace(/^(\d{4})–\d{2}(\d{2})$/, '$1–$2');
    let out = '', tmax = 0, gmax = 0, cmp = 0;
    for (const h of ['13', '26']) {
      const W = (nd.weekly || {})[h] || {}, Dh = Dy[h] || {};
      const rows = names.map(([k, lab]) => [esc(lab), ...P.map((p) => (W[k] ? st((W[k][p] || {}).net) : '<span class="muted">needs daily closes</span>')), ...DP.map((p) => st((((Dh[k] || {}).periods || {})[p] || {}).net))]);
      names.forEach(([k]) => { [(W[k] || {})[P[0]], (((Dh[k] || {}).periods || {})[DP[0]])].forEach((c) => { if (c && c.net && fin(c.net.t)) tmax = Math.max(tmax, Math.abs(c.net.t)); });
        const v = Dh[k], N = Number(k.split(':')[1].split('/')[0]), a = v && ((v.periods || {})[DP[0]] || {}).net;
        if (v && v.weekly_form && a && N >= 20 && fin(a.mean) && fin(v.weekly_form.mean)) { gmax = Math.max(gmax, Math.abs(a.mean - v.weekly_form.mean)); cmp += 1; } });
      out += `<h4>Daily averages, ${h} weeks: price above the average (or the shorter average above the longer) − below, after costs</h4>` + tbl(['', ...P.map((p) => `Weekly form ${esc(yy(p))}`), ...DP.map((p) => `Daily ${esc(yy(p))}`)], rows, [0, ...P.map(() => 1), ...DP.map(() => 1)]);
    }
    return out + `<p class="mh-note">Weekly form: every company from ${esc(d.test_from)}, each N-day average taken as the N/5-week average of weekly closes (none for 5 days). Daily closes: the ${num(Dy.companies)} or so companies a week with daily bars (research-paths), from ${esc(Dy.from || '')}, each Friday's last close against its averages. On the same companies and weeks the weekly form came within ${num(100 * gmax, 2)} points of the daily figure for every length of 20 days and more (${num(cmp)} comparisons). A cross: the shorter average above the longer against below it. Short averages read as turning points — being above them was followed by doing worse — and long ones lean to trend; the largest |t| in these tables is ${num(tmax, 1)}, so none is reliable on its own.</p>`;
  }
  function fundTables(d) {
    const I = ((d.scores || {}).macro || {}).index; if (!I || !I.funds) return '';
    const P = I.periods || [], rules = Object.keys(I.rules || {}), spy = I.funds.SPY, fs = Object.keys(I.funds);
    let out = `<h4>The macro, for the index funds: the 40-week rule with and without a macro filter</h4><p class="mh-sub">Now: ${macroNow(d)}</p>`;
    if (spy) out += tbl([`SPY, from ${esc(spy.start)}`, ...P.map((p) => 'A year, ' + esc(p)), 'Volatility', 'Worst fall', 'Invested', 'Switches'],
      rules.map((r) => { const a = (spy.rules[r] || {})[P[0]] || {}; return [esc(I.rules[r]), ...P.map((p) => pct(((spy.rules[r] || {})[p] || {}).cagr, 1)), pct(a.vol, 1), spct(a.maxdd, 1), pct(a.invested), num(a.switches)]; }), [0, 1, 1, 1, 1, 1, 1, 1]);
    for (const p of [P[0], P[2]].filter(Boolean)) {
      out += tbl([`A year and the worst fall, ${esc(p)}`, ...rules.map((r) => esc(RULE_SHORT[r] || r))],
        fs.map((f) => { const F = I.funds[f]; return [`${esc(f)} <span class="muted">from ${esc(String(((F.rules.hold || {})[p] || {}).from || F.start).slice(0, 4))}</span>`, ...rules.map((r) => { const a = (F.rules[r] || {})[p]; return a ? `${pct(a.cagr, 1)} <span class="muted">(${spct(a.maxdd, 0)})</span>` : '—'; })]; }), [0, 1, 1, 1, 1]);
    }
    return out + `<p class="mh-note">Decided at each Friday's close on the fund's total-return close and the macro as known that day (each figure from its publication day; the unemployment rate is revised little), held the next week; out of the fund means cash at the fed funds rate, ${num(I.switch_bp)} bp a switch. "+ unemployment": out only when below the 40-week average and the unemployment rate is above its own 12-month average (the growth-trend rule, Philosophical Economics, 2016). "+ Sahm rule": out only when below it and the 3-month average unemployment rate is ${num(I.sahm_on, 1)} points or more above its low of the last 12 months (Sahm, 2019). Both rules were published after most of this history, so ${esc(P[2] || '')} is their fair test.</p>`;
  }
  function regimeTables(d) {
    const R = ((d.scores || {}).macro || {}).regimes; if (!R) return '';
    return `<h4>The macro, for companies: the 40-week trend in each third of twelve readings, 26 weeks</h4>` + macroRegimes(d, '26') + `<h4>The same, 13 weeks</h4>` + macroRegimes(d, '13') +
      `<p class="mh-note">Each week every company above its 40-week average against those below it, simple returns against SPY after costs, ${esc(R.period || '')}, split by where each reading stood within its own history up to that week (thirds of its values since 1995, at least three years of them; the weekly figures from 2009, month-end ones before). Today's third is outlined. ${num(R.tests)} comparisons: about ${num(R.tests * 0.05)} would show |t| above 2 by chance alone, and the readings move together (inflation and the fed funds rate were both high in 2022–2023) — a cell is a hint about the past, not a rule.</p>`;
  }
  async function renderHub(el, ctx) {
    css();
    const hub = (ctx && ctx.hub != null ? ctx.hub : ''), base = hub + 'data/market/history/';
    el.innerHTML = '<p class="muted">Loading Moving averages+…</p>';
    let d, rows;
    try { [d, rows] = await Promise.all([get(base + 'ma-hybrid.json'), get(base + 'ma-hybrid-rows.json').catch(() => null)]);
      d._valuationModels = await get(hub + 'data/research/valuation/models.json').catch(() => null); } catch (e) {
      el.innerHTML = `<p class="muted">Moving averages+ has not been published yet (${esc(e.message)}).</p>`; return;
    }
    const st_ = { t: (ctx && ctx.ticker) || '' };
    const draw = async () => {
      const dw = (d.weights || {}).default || [0.5, 0.05], w = ui.w != null ? ui.w : dw[0], g = ui.g != null ? ui.g : dw[1];
      let one = '';
      if (st_.t) {
        const T = st_.t.toUpperCase().replace(/\./g, '-');
        const [s, dd] = await Promise.all([get(base + 'ma/' + T + '.json').catch(() => null), get(base + 'ma-daily/' + T + '.json').catch(() => null)]);
        const row = (s && s.now) || (rows && (rows.rows || []).find((r) => r.id === T));
        one = s ? `<h3>${esc(T)} <span class="muted" style="font-weight:400">${esc(s.name || '')}</span></h3>` + companyHtml(s, d, row, w, g, el.clientWidth || 760, 'mh-hub', dd)
          : `<p class="muted">${esc(T)} is not in this week's set (weekly prices and first-filed quarters, ≥ $3 and $10M traded a week).</p>`;
      }
      const keepOpen = !!el.querySelector('.mh details[open]');
      el.innerHTML = `<div class="mh"><h3>Moving averages+ — daily and weekly averages with earnings, guidance and the macro</h3>${lead(d)}
        <div class="mh-ctl"><label>Ticker <input id="mh-q" value="${esc(st_.t)}" placeholder="e.g. NVDA · Enter" size="12"></label></div>${one}
        ${one ? '' : controls('mh-hub', w, g)}${rows ? listHtml(rows.rows, w, g, (d.daily || {}).cross_recent) : ''}<div class="mh-sec"><h3>How it has done</h3>${hubTables(d)}</div></div>`;
      if (keepOpen) el.querySelectorAll('.mh details').forEach((x) => { x.open = true; });
      el.querySelectorAll('select[data-mh]').forEach((x) => { x.onchange = () => { ui[x.dataset.mh] = Number(x.value); refresh(rows); draw(); }; });
      bindDaily(el, draw);
      const q = el.querySelector('#mh-q');
      if (q) q.onkeydown = (e) => { if (e.key === 'Enter') { st_.t = q.value.trim(); draw(); } };
      el.querySelectorAll('[data-mh-t]').forEach((a) => { a.onclick = (e) => { e.preventDefault(); st_.t = a.dataset.mhT; draw(); }; });
    };
    const refresh = (R) => {                                         // the list's gaps for the weights picked here
      const dw = (d.weights || {}).default || [0.5, 0.05], w = ui.w != null ? ui.w : dw[0], g = ui.g != null ? ui.g : dw[1];
      ((R || {}).rows || []).forEach((r) => {
        if (!fin(r.ma40) || !fin(r.close)) return;
        const base_ = fin(r.el) && r.el > 0 ? Math.exp((1 - w) * Math.log(r.ma40) + w * Math.log(r.el)) : r.ma40;
        const Hn = base_ * (1 + g * (fin(r.guid) ? r.guid : 0));
        r.hybrid = Hn; r.gap_hybrid = Math.log(r.close / Hn);
      });
    };
    refresh(rows);
    await draw();
  }

  const api = { render, renderHub, _chart: chart, _hybrid: hybrid, _company: companyHtml, _hub: hubTables, _list: listHtml, _lead: lead,
    _sma: sma, _dailyOf: dailyOf, _dailyChart: dailyChart, _dailyHybrid: dailyHybrid, _macroNow: macroNow, _ui: ui };
  if (typeof window !== 'undefined') window.MAHybridView = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
