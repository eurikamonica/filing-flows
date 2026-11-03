/* Fair value — one company's valuation & credit page, shared by the Disclosure Hub (Valuation tab → one company) and the
   main site's company page ("Fair value" view, listed in views.json). Data: data/research/valuation/c/<cik>.json
   (app/valuation.py, branch research-valuation). window.FairValueView.render(el, {cik, ticker, hub}) loads and draws;
   draw(el, doc, fits) draws a loaded document. Self-contained: colours from the host's CSS variables with fallbacks. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, 1) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const pct = (v, d = 1) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 0) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const C = { good: 'var(--mk-profit, #2e8b57)', bad: 'var(--mk-cost, #c0392b)', warn: 'var(--q-warm, #d9822b)', acc: 'var(--accent, #2a78d6)', mute: 'var(--muted, #888)', ink: 'var(--ink, #222)', line: 'var(--line, #ddd)' };
  const store = {};
  // markov-view.js (the regime-switching section) sits next to this file; it is loaded only for a document that has one
  const HERE = (typeof document !== 'undefined' && document.currentScript && document.currentScript.src) ? document.currentScript.src.replace(/[^/]*$/, '') : '';
  let mvLoad = null;
  const loadMarkov = () => mvLoad || (mvLoad = (typeof window !== 'undefined' && window.MarkovView) ? Promise.resolve(window.MarkovView) : new Promise((ok, bad) => {
    const sc = document.createElement('script');
    sc.src = HERE + 'markov-view.js';
    sc.onload = () => ok(window.MarkovView);
    sc.onerror = () => { mvLoad = null; bad(new Error('markov-view.js did not load')); };
    document.head.appendChild(sc);
  }));
  // sim-view.js (the pipeline rNPV and the Schwartz–Moon simulation) likewise, only for a document that has them
  let svLoad = null;
  const loadSim = () => svLoad || (svLoad = (typeof window !== 'undefined' && window.SimView) ? Promise.resolve(window.SimView) : new Promise((ok, bad) => {
    const sc = document.createElement('script');
    sc.src = HERE + 'sim-view.js';
    sc.onload = () => ok(window.SimView);
    sc.onerror = () => { svLoad = null; bad(new Error('sim-view.js did not load')); };
    document.head.appendChild(sc);
  }));
  // valuation-guide.json (next to this file): the appendix's plain-language guide — valuation from zero, start-ups, the
  // glossary, each method's what / why / fits / watch and each stage's meaning. The appendix draws without it, then again.
  let guide = null, gLoad = null;
  const loadGuide = () => gLoad || (gLoad = (typeof fetch === 'function' ? fetch(HERE + 'valuation-guide.json', { cache: 'no-cache' })
    .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }) : Promise.reject(new Error('no fetch')))
    .then((g) => (guide = g)).catch((e) => { gLoad = null; throw e; }));
  const setGuide = (g) => { guide = g; };

  function css() {
    if (typeof document === 'undefined' || document.getElementById('fv-css')) return;
    const s = document.createElement('style'); s.id = 'fv-css';
    s.textContent = `.fv h3{margin:22px 0 6px;font-size:16px}.fv .fv-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45;max-width:78ch}
.fv-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:8px 0 6px}
.fv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 12px}.fv-card b{display:block;font-size:20px;font-variant-numeric:tabular-nums;margin-top:2px}
.fv-card span{font-size:12px;color:var(--muted,#777)}.fv-card i{display:block;font-style:normal;font-size:12px;margin-top:2px;color:var(--muted,#777)}
.fv-epv{display:grid;grid-template-columns:130px 1fr 90px;align-items:center;gap:8px;font-size:13px;margin:4px 0}.fv-epv i{display:block;height:12px;border-radius:3px}.fv-epv b{font-variant-numeric:tabular-nums;text-align:right}
.fv-good{color:${C.good}}.fv-bad{color:${C.bad}}.fv-warn{color:${C.warn}}
/* the view's own charts only: Plotly's layers (the 3D charts) keep their own sizes, or a wide page shrinks its hover layer and the labels drift off */.fv svg:not(.js-plotly-plot svg){display:block;width:100%;max-width:860px;height:auto;overflow:visible}.fv svg:not(.js-plotly-plot svg) text{font-size:11px;fill:var(--muted,#777)}
.fv svg .fv-lbl{fill:var(--ink,#222);font-size:12px}.fv .fv-grid{stroke:var(--line,#e3e3e3)}
.fv-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.fv-tbl th,.fv-tbl td{padding:6px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.fv-tbl td.n,.fv-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.fv-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}
.fv-wrap{overflow-x:auto}.fv-two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
.fv-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:14px;max-width:90ch}.fv-tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line,#ddd);margin-left:6px;color:var(--muted,#777)}
.fv-stack{display:flex;height:22px;border-radius:6px;overflow:hidden;border:1px solid var(--line,#ddd);max-width:640px}.fv-stack i{display:block;height:100%}
.fv-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 6px}.fv-legend span::before{content:'';display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px;background:var(--k)}
.fv-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:8px 0 10px}
.fv-tile{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 10px;display:flex;flex-direction:column;gap:2px;min-height:112px}
.fv-tile em{font-style:normal;font-size:11px;color:var(--muted,#777);line-height:1.3;min-height:28px}.fv-tile b{font-size:19px;font-variant-numeric:tabular-nums}
.fv-tile .fv-p{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;border-top:1px dashed var(--line,#ddd);padding-top:4px;margin-top:auto}
.fv-tile small{font-size:11px;color:var(--muted,#777)}.fv h4{margin:14px 0 4px;font-size:14px}
.fv-apx{border:1px solid var(--line,#ddd);border-radius:10px;padding:6px 12px;margin:6px 0;max-width:980px}.fv-apx summary{cursor:pointer;font-size:13.5px;line-height:1.6}
.fv-apx[open]{padding-bottom:10px}.fv-f{font-family:var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace);font-size:12.5px;background:color-mix(in srgb,var(--ink,#222) 5%,transparent);border-radius:8px;padding:8px 10px;margin:8px 0;line-height:1.5;white-space:pre-wrap}
.fv-steps{margin:6px 0 8px 18px;padding:0;font-size:13px;line-height:1.6;font-variant-numeric:tabular-nums}.fv-tile.fv-exp{border-color:var(--ink,#222)}
.fv-bar{height:5px;border-radius:3px;background:var(--line,#e5e5e5);overflow:hidden}.fv-bar i{display:block;height:100%;background:var(--accent,#2a78d6)}
.fv-heat td.n{min-width:64px}.fv-tog{font:inherit;font-size:12px;border:1px solid var(--line,#ddd);background:none;border-radius:8px;padding:3px 9px;cursor:pointer;color:var(--muted,#666);margin-right:6px}.fv-tog.on{color:var(--ink,#222);border-color:var(--ink,#222)}
.fv-x{margin:6px 0 4px;max-width:82ch}.fv-x p{margin:5px 0;font-size:13.5px;line-height:1.55}.fv-x p b{font-weight:600}.fv-x .fv-here{border-left:3px solid var(--accent,#2a78d6);padding-left:8px}.fv-terms{font-size:12.5px;color:var(--muted,#666);line-height:1.6}.fv-terms b{color:var(--ink,#222)}.fv-prose p{font-size:13.5px;line-height:1.6;margin:6px 0;max-width:82ch}.fv-gl td:first-child{font-weight:600;white-space:nowrap}.fv-gl .fv-tbl td,.fv-gl .fv-tbl th{white-space:normal;vertical-align:top;line-height:1.45}.fv-gl .fv-tbl td:first-child{white-space:nowrap}.fv-gl .fv-tbl td:not(:first-child){min-width:14em}.fv-apx.fv-guide>summary b{color:var(--accent,#2a78d6)}
.fv-sotp td small{white-space:normal;display:inline-block;max-width:220px}.fv-px-bar{display:flex;flex-wrap:wrap;gap:8px 14px;margin:8px 0}.fv-px-f{font-size:12.5px;color:var(--muted,#666);display:flex;flex-direction:column;gap:2px}.fv-px-f select{font:inherit;font-size:13px;padding:3px 6px}
.fv-px-pre{font-size:12.5px;color:var(--muted,#666);margin:4px 0 8px}.fv-head2{font-size:14.5px;margin:8px 0}.fv-px-t td{font-size:12.5px}.fv-px-out{opacity:.72}.fv-px-own{background:var(--surface-2,#f3f2ee)}
@media (max-width:640px){.fv table.fv-tbl{display:block;overflow-x:auto;max-width:100%}}`;
    document.head.appendChild(s);
  }
  const pp = (v) => (fin(v) ? (v > 0 && v < 0.005 ? '<1%' : v < 1 && v > 0.995 ? '>99%' : num(100 * v, 0) + '%') : '—');
  const card = (label, value, cls = '', note = '') => `<div class="fv-card"><span>${esc(label)}</span><b class="${cls}">${value}</b>${note ? `<i>${note}</i>` : ''}</div>`;

  // ---------- the peer tiers and the peer explorer (app/peer_tiers.py, data/research/valuation/peers-list.json) ----------
  let BASE = 'data/research/valuation/';
  const TIERS = [['plain', 'Broad (tier 1)'], ['weighted', 'Weighted'], ['matched', 'Matched (tier 2)'], ['selected', 'Selected (tier 3)'], ['adjusted', 'Fitted']];
  const MET = { pe: 'P/E', ev_ebitda: 'EV/EBITDA', ev_sales: 'EV/Sales' };
  const WIN = { tight: 'tight: same 3-digit SIC and stage, revenue ¼–4×, growth and margin ±10 pts', medium: 'medium: same 3-digit SIC, same side of break-even, 1/10–10×, ±15 pts',
    wide: 'wide: same 2-digit SIC, same side of break-even, 1/30–30×, ±25 pts' };
  const valueOf = (k, m, b) => {
    if (!fin(m) || !b) return null;
    if (k === 'pe') return fin(b.eps) && b.eps > 0 ? m * b.eps : null;
    const base = k === 'ev_ebitda' ? b.ebitda : b.revenue;
    return fin(base) && base > 0 && fin(b.shares) && b.shares > 0 ? (m * base - (b.net_debt || 0)) / b.shares : null;
  };
  function tiersHtml(d) {
    const P = d.peers || {}, b = d.peer_base, ks = Object.keys(MET).filter((k) => P[k]);
    if (!ks.length) return '';
    const x = (v) => (fin(v) ? num(v, 1) + '×' : '—');
    const cell = (k, t) => {
      const p = P[k], T = t === 'plain' ? p : p[t];
      if (T && T.weak) return `<td class="n"><small>fit too weak<br>(r² ${num(T.r2, 2)})</small></td>`;
      if (!T || !fin(T.p50)) {
        const why = t === 'matched' && T && T.tried ? `none like it: ${T.tried.map(([w, n]) => `${w} ${n}`).join(', ')} peers` : t === 'selected' && T ? `${num(T.n)} on file, needs 3` : t === 'selected' ? 'no selected list' : t === 'adjusted' ? 'too few peers to fit' : '—';
        return `<td class="n"><small>${esc(why)}</small></td>`;
      }
      const n = t === 'plain' ? `${num(p.n)} peers` : t === 'weighted' ? `${num(T.n_eff, 1)} effective` : t === 'matched' ? `${num(T.n)} · ${esc(T.window)} window` : t === 'selected' ? `${num(T.n)} chosen` : `${num(T.n)} peers, r² ${num(T.r2, 2)}`;
      return `<td class="n"><b>${x(T.p50)}</b> → ${esc(usd(valueOf(k, T.p50, b)))}<br><small>${n}</small></td>`;
    };
    let h = `<h3>Peer multiples — four ways to pick and weigh the peers</h3><p class="fv-sub">Each cell: the peers' multiple and the value per share it gives this company. <b>Broad</b>: the median of its SIC industry (every peer alike). <b>Weighted</b>: the same peers weighted by market value, revenue and trading value (none above 20%) and their quarters since 2022 by recency. <b>Matched</b>: only peers like it — the same industry and stage, a similar size, revenue growth and operating margin (${esc(Object.values(WIN).join('; '))}). <b>Selected</b>: companies chosen by business model, each with its reason. <b>Fitted</b>: how much its peers' multiple rises with growth (and, for EV/Sales, margin), read at its own figures. All but the broad median are lenses: the ledger scores them before any counts in the stage-weighted value. Explore and re-filter every peer below.</p>`;
    h += `<div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Multiple</th>${TIERS.map(([, l]) => `<th class="n">${esc(l)}</th>`).join('')}</tr></thead><tbody>${ks.map((k) => `<tr><td>${MET[k]}<br><small>own ${x(P[k].own)}</small></td>${TIERS.map(([t]) => cell(k, t)).join('')}</tr>`).join('')}</tbody></table></div>`;
    const sel = ks.map((k) => P[k].selected).find((s) => s && (s.comps || []).length);
    if (sel) h += `<p class="fv-sub">Selected companies: ${sel.comps.map(([t, why]) => `<b>${esc(t)}</b> (${esc(why)})`).join('; ')}${(sel.missing || []).length ? `. Not on file: ${esc(sel.missing.join(', '))}` : ''}. The list lives in config/peer-map.json.</p>`;
    const ad = P.ev_sales && P.ev_sales.adjusted;
    if (ad && ad.per10) h += `<p class="fv-sub">Fit across ${num(ad.n)} peers: ${Object.entries(ad.per10).map(([k, v]) => `every 10 points of ${k === 'growth' ? 'revenue growth' : 'operating margin'} ${spct(v, 0)} on EV/Sales`).join(', ')} (r² ${num(ad.r2, 2)}); at its own ${Object.entries(ad.x || {}).map(([k, v]) => `${k} ${pct(v, 0)}`).join(', ')}${ad.clamped ? ' (held inside the peers\' range)' : ''} the fitted EV/Sales is ${x(ad.p50)}.</p>`;
    h += `<div data-fvtiersc></div>`;
    h += `<details class="fv-apx" data-fvpx-open><summary><b>Explore the peers</b> — every company, your filters and windows</summary><div data-fvpx><p class="fv-sub">Opening the peer list…</p></div></details>`;
    return h;
  }
  const PX = { data: null, loading: null };
  const PX_OPTS = {
    metric: [['ev_sales', 'EV/Sales'], ['pe', 'P/E'], ['ev_ebitda', 'EV/EBITDA']],
    group: [['sic4', 'SIC, 4 digits'], ['sic3', 'SIC, 3 digits'], ['sic2', 'SIC, 2 digits'], ['sector', 'sector'], ['all', 'every company']],
    stage: [['any', 'any stage'], ['profit', 'same side of break-even'], ['same', 'same stage']],
    size: [['0', 'any size'], ['30', 'revenue 1/30–30×'], ['10', 'revenue 1/10–10×'], ['4', 'revenue ¼–4×'], ['2', 'revenue ½–2×']],
    growth: [['0', 'any growth'], ['0.25', 'growth ±25 pts'], ['0.15', 'growth ±15 pts'], ['0.10', 'growth ±10 pts'], ['0.05', 'growth ±5 pts']],
    margin: [['0', 'any margin'], ['0.25', 'margin ±25 pts'], ['0.15', 'margin ±15 pts'], ['0.10', 'margin ±10 pts'], ['0.05', 'margin ±5 pts']],
    hist: [['0', 'today only'], ['1', 'today and the last year'], ['5', 'today and every quarter since 2022']],
    weight: [['equal', 'every peer alike'], ['mcap', 'by market value'], ['revenue', 'by revenue'], ['dvol', 'by trading value'], ['all', 'market value × revenue × trading value']],
    trim: [['0', 'keep every peer'], ['0.05', 'drop the top and bottom 5%'], ['0.10', 'drop the top and bottom 10%']],
  };
  const PX_LABEL = { metric: 'Multiple', group: 'Industry', stage: 'Stage', size: 'Size', growth: 'Revenue growth', margin: 'Operating margin', hist: 'History window', weight: 'Weights', trim: 'Outliers' };
  function wq(vals, ws, q) {   // weighted quantile: linear between weight midpoints (equal weights: the plain percentile), as app/peer_weights.py
    const p = vals.map((v, i) => [v, ws[i]]).filter(([v, w]) => fin(v) && fin(w) && w > 0).sort((a, b) => a[0] - b[0]);
    if (!p.length) return null;
    if (p.length === 1) return p[0][0];
    const tot = p.reduce((s, [, w]) => s + w, 0), w0 = p[0][1], wl = p[p.length - 1][1], span = tot - (w0 + wl) / 2;
    let c = 0;
    const pos = p.map(([, w]) => { const x = (c + w / 2 - w0 / 2) / span; c += w; return x; });
    if (q <= 0) return p[0][0];
    if (q >= 1) return p[p.length - 1][0];
    for (let i = 1; i < p.length; i++) if (pos[i] >= q) { const a = pos[i - 1], b = pos[i]; return p[i - 1][0] + (b > a ? (q - a) / (b - a) : 0) * (p[i][0] - p[i - 1][0]); }
    return p[p.length - 1][0];
  }
  function capW(w, cap = 0.2) {
    const keys = Object.keys(w), tot = keys.reduce((s, k) => s + w[k], 0);
    if (!tot) return w;
    let x = {};
    keys.forEach((k) => { x[k] = w[k] / tot; });
    if (keys.length * cap < 1) return x;
    const fixed = new Set();
    for (let it = 0; it < keys.length; it++) {
      const over = keys.filter((k) => x[k] > cap + 1e-12 && !fixed.has(k));
      if (!over.length) break;
      over.forEach((k) => fixed.add(k));
      const free = keys.filter((k) => !fixed.has(k)), rest = 1 - cap * fixed.size, ft = free.reduce((s, k) => s + x[k], 0);
      const y = {};
      keys.forEach((k) => { y[k] = fixed.has(k) ? cap : ft ? x[k] / ft * rest : rest / Math.max(1, free.length); });
      x = y;
    }
    return x;
  }
  function sizeW(rows, how) {   // geometric mean of each peer's shares of the measures most peers have, capped at 20%
    const parts = how === 'all' ? ['mcap', 'revenue', 'dvol'] : [how];
    const sh = {};
    for (const k of parts) {
      const have = rows.filter((r) => fin(r[k]) && r[k] > 0);
      if (have.length < Math.max(2, Math.ceil(rows.length / 2))) continue;
      const tot = have.reduce((s, r) => s + r[k], 0);
      sh[k] = {};
      have.forEach((r) => { sh[k][r.cik] = r[k] / tot; });
    }
    const used = Object.keys(sh), w = {};
    if (!used.length) { rows.forEach((r) => { w[r.cik] = 1; }); return [capW(w), used]; }
    rows.forEach((r) => { const xs = used.map((k) => sh[k][r.cik]).filter(fin); w[r.cik] = xs.length ? Math.exp(xs.reduce((s, v) => s + Math.log(v), 0) / xs.length) : null; });
    const mn = Math.min(...Object.values(w).filter(fin));
    Object.keys(w).forEach((k) => { if (!fin(w[k])) w[k] = mn; });
    return [capW(w), used];
  }
  function pxRun(D, d, o) {
    const F = D.fields, ix = Object.fromEntries(F.map((f, i) => [f, i]));
    const rows = D.rows.map((r) => Object.fromEntries(F.map((f, i) => [f, r[i]])));
    const own = rows.find((r) => String(r.cik) === String(d.cik)) || Object.assign({ cik: d.cik }, d.peer_base || {});
    const b = d.peer_base || {}, sic = String(own.sic || b.sic || ''), k = o.metric, H = { pe: 'pe_hist', ev_sales: 'evs_hist' }[k];
    const pre = o.group === 'sic4' ? sic.slice(0, 4) : o.group === 'sic3' ? sic.slice(0, 3) : o.group === 'sic2' ? sic.slice(0, 2) : null;
    const inc = [], exc = [];
    for (const r of rows) {
      if (String(r.cik) === String(own.cik)) continue;
      let why = null;
      if (pre != null && !String(r.sic || '').startsWith(pre)) continue;                        // outside the industry: not listed at all
      if (o.group === 'sector' && r.sector !== own.sector) continue;
      if (!fin(r[k])) why = `no ${MET[k]} (negative or out of range)`;
      else if (o.stage === 'same' && own.stage && r.stage !== own.stage) why = `stage: ${String(r.stage || '—').replace('_', ' ')}`;
      else if (o.stage === 'profit' && fin(own.margin) && fin(r.margin) && (own.margin > 0) !== (r.margin > 0)) why = r.margin > 0 ? 'profitable (it is not)' : 'loss-making';
      else if (+o.size && fin(own.revenue) && own.revenue > 0 && !(fin(r.revenue) && r.revenue >= own.revenue / +o.size && r.revenue <= own.revenue * +o.size)) why = 'size outside the window';
      else if (+o.growth && fin(own.growth) && !(fin(r.growth) && Math.abs(r.growth - own.growth) <= +o.growth + 1e-9)) why = 'growth outside the window';
      else if (+o.margin && fin(own.margin) && !(fin(r.margin) && Math.abs(r.margin - own.margin) <= +o.margin + 1e-9)) why = 'margin outside the window';
      (why ? exc : inc).push(why ? [r, why] : r);
    }
    if (+o.trim && inc.length >= 10) {
      const vs = inc.map((r) => r[k]).sort((a, c) => a - c), lo = wq(vs, vs.map(() => 1), +o.trim), hi = wq(vs, vs.map(() => 1), 1 - +o.trim);
      for (let i = inc.length - 1; i >= 0; i--) if (inc[i][k] < lo || inc[i][k] > hi) exc.push([inc.splice(i, 1)[0], 'outlier, trimmed']);
    }
    const [sw, used] = o.weight === 'equal' ? [Object.fromEntries(inc.map((r) => [r.cik, 1 / Math.max(1, inc.length)])), []] : sizeW(inc, o.weight);
    const vals = [], ws = [];
    for (const r of inc) {
      const obs = [[r[k], 0]];
      if (+o.hist && H && r[H]) r[H].forEach((v, i) => { const a = D.ages[i]; if (fin(v) && a > 0 && a <= +o.hist) obs.push([v, a]); });
      const t = obs.map(([, a]) => Math.pow(0.5, a / (D.half_life || 1))), tt = t.reduce((s, v) => s + v, 0);
      obs.forEach(([v], i) => { vals.push(v); ws.push(sw[r.cik] * t[i] / tt); });
    }
    const q = (p) => wq(vals, ws, p);
    const neff = 1 / Object.values(sw).reduce((s, v) => s + v * v, 0);
    return { own, inc, exc, sw, used, n_obs: vals.length, p25: q(0.25), p50: q(0.5), p75: q(0.75), neff, k, b };
  }
  function pxHtml(D, d, o) {
    const R = pxRun(D, d, o), k = R.k, x = (v) => (fin(v) ? num(v, 1) + '×' : '—');
    const sel = (key) => `<label class="fv-px-f">${esc(PX_LABEL[key])} <select data-fvpxo="${key}">${PX_OPTS[key].map(([v, l]) => `<option value="${esc(v)}"${String(o[key]) === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
    const P = (d.peers || {})[k] || {}, mt = P.matched || {};
    let h = `<div class="fv-px-bar">${Object.keys(PX_OPTS).map(sel).join('')}</div><div class="fv-px-pre">Presets: <button type="button" class="fv-tog" data-fvpxp="broad">Broad (tier 1)</button><button type="button" class="fv-tog" data-fvpxp="weighted">Broad, weighted</button>${mt.window ? `<button type="button" class="fv-tog" data-fvpxp="matched">Matched (${esc(mt.window)})</button>` : ''}</div>`;
    h += R.inc.length ? `<p class="fv-head2"><b>${num(R.inc.length)} peers</b>${o.weight !== 'equal' ? ` (${num(R.neff, 1)} effective)` : ''}${R.n_obs > R.inc.length ? `, ${num(R.n_obs)} observations` : ''}: median ${MET[k]} <b>${x(R.p50)}</b>, middle half ${x(R.p25)} – ${x(R.p75)} → <b>${esc(usd(valueOf(k, R.p50, R.b)))}</b> a share (${esc(usd(valueOf(k, R.p25, R.b)))} – ${esc(usd(valueOf(k, R.p75, R.b)))}); its own ${MET[k]} ${x(R.own[k])}, price ${esc(usd(d.price))}.${R.inc.length < 6 ? ' <span class="fv-tag">fewer than 6 peers</span>' : ''}</p>` : '<p class="fv-sub">No peer passes these filters.</p>';
    const head = ['Company', 'SIC', 'Stage', 'Market value', 'Enterprise value', 'Revenue', 'Growth', 'Op. margin', MET[k], 'Weight', 'Data date'];
    const line = (r, w, why) => `<tr${why ? ' class="fv-px-out"' : ''}><td><b>${esc(r.ticker)}</b> <small>${esc(String(r.name || '').slice(0, 28))}</small></td><td>${esc(r.sic)}</td><td><small>${esc(String(r.stage || '—').replace('_', ' '))}</small></td><td class="n">${big(r.mcap)}</td><td class="n">${big(r.ev)}</td><td class="n">${big(r.revenue)}</td><td class="n">${spct(r.growth)}</td><td class="n">${pct(r.margin, 0)}</td><td class="n">${x(r[k])}</td><td class="n">${why ? `<small>${esc(why)}</small>` : pct(w, 1)}</td><td><small>${esc(r.date || '')}</small></td></tr>`;
    const inc = R.inc.slice().sort((a, c) => (R.sw[c.cik] || 0) - (R.sw[a.cik] || 0) || (c.mcap || 0) - (a.mcap || 0));
    const own = R.own;
    h += `<div class="fv-wrap"><table class="fv-tbl fv-px-t"><thead><tr>${head.map((c, i) => `<th${i >= 3 && i <= 9 ? ' class="n"' : ''}>${esc(c)}</th>`).join('')}</tr></thead><tbody><tr class="fv-px-own"><td><b>${esc(own.ticker || d.ticker)}</b> <small>this company</small></td><td>${esc(own.sic || '')}</td><td><small>${esc(String(own.stage || '—').replace('_', ' '))}</small></td><td class="n">${big(own.mcap)}</td><td class="n">${big(own.ev)}</td><td class="n">${big(own.revenue)}</td><td class="n">${spct(own.growth)}</td><td class="n">${pct(own.margin, 0)}</td><td class="n">${x(own[k])}</td><td class="n"><small>excluded: itself</small></td><td><small>${esc(own.date || '')}</small></td></tr>${inc.slice(0, o.all ? 1e9 : 40).map((r) => line(r, R.sw[r.cik])).join('')}</tbody></table></div>`;
    if (inc.length > 40 && !o.all) h += `<button type="button" class="fv-tog" data-fvpxall="1">Show all ${num(inc.length)} peers</button>`;
    if (R.exc.length) h += `<details class="fv-apx"><summary>Left out by these filters: ${num(R.exc.length)} — and why</summary><div class="fv-wrap"><table class="fv-tbl fv-px-t"><thead><tr>${head.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${R.exc.slice(0, 300).map(([r, why]) => line(r, null, why)).join('')}</tbody></table></div></details>`;
    h += `<p class="fv-sub">Figures as the build used them (${esc(D.as_of || '')}): revenue and growth over four quarters, operating margin = operating income ÷ revenue, trading value = the median daily close × volume over 63 sessions. Weights: each peer's share of the group's market value, revenue and trading value (their geometric mean for "all three"), none above 20%; with a history window, each peer's quarters count with a one-year half-life. Every number can be checked against the company's own page.</p>`;
    return h;
  }
  const TIER_KEYS = { plain: 'Broad', weighted: 'Weighted', matched: 'Matched', selected: 'Selected', adjusted: 'Fitted' };
  function scoresHtml(L) {   // the ledger's rank correlation (IC) of each tier's gap to the price with the return that followed
    const S = (L && L.scores) || [];
    const avg = (key, h) => { const xs = S.filter((s) => s.horizon_months === h && fin(s['ic_' + key]) && (s['n_' + key] || 0) >= 30); return xs.length ? [xs.reduce((a, s) => a + s['ic_' + key], 0) / xs.length, xs.length] : null; };
    const rows = [];
    for (const [m, lab] of [['evs', 'EV/Sales'], ['pe', 'P/E'], ['evebitda', 'EV/EBITDA']]) {
      for (const [t, tl] of Object.entries(TIER_KEYS)) {
        const c = [3, 6, 12].map((h) => avg(`${m}_${t}_gap`, h));
        if (c.some(Boolean)) rows.push(`<tr><td>${lab} · ${tl}</td>${c.map((x) => `<td class="n">${x ? `${num(x[0], 3)}<br><small>${x[1]} month${x[1] === 1 ? '' : 's'}</small>` : '—'}</td>`).join('')}</tr>`);
      }
    }
    if (!rows.length) return `<p class="fv-sub"><b>Track record:</b> every tier's value is now frozen in the monthly ledger (${esc((L && L.snapshots || []).slice(-1)[0] || 'this month')} on); the first scores come three months after the first snapshot that holds them, then 6 and 12 months. Until a tier has been scored it stays a lens.</p>`;
    return `<h4>Track record of the tiers (the ledger)</h4><p class="fv-sub">Rank correlation between each tier's value-to-price gap and the return over the next 3, 6 and 12 months, across every company, averaged over the monthly snapshots scored so far (higher is better; 0 = no information).</p><div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Tier</th><th class="n">3 months</th><th class="n">6 months</th><th class="n">12 months</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  }
  function bindPx(el, d) {
    const sc = el.querySelector('[data-fvtiersc]');
    if (sc) get(BASE + 'ledger.json').then((L) => { sc.innerHTML = scoresHtml(L); }).catch(() => { sc.innerHTML = ''; });
    const box = el.querySelector('[data-fvpx]'), det = el.querySelector('[data-fvpx-open]');
    if (!box || !det) return;
    const P = d.peers || {}, first = ['ev_sales', 'pe', 'ev_ebitda'].find((k) => P[k]) || 'ev_sales', g0 = String((P[first] || {}).group || 'sic');
    const broad = { metric: first, group: /^sic\d{4}$/.test(g0) ? 'sic4' : /^sic\d{3}$/.test(g0) ? 'sic3' : /^sic\d{2}$/.test(g0) ? 'sic2' : g0.startsWith('sec:') ? 'sector' : 'sic4', stage: 'any', size: '0', growth: '0', margin: '0', hist: '0', weight: 'equal', trim: '0' };
    let o = Object.assign({}, broad);
    const draw_ = () => {
      box.innerHTML = pxHtml(PX.data, d, o);
      box.querySelectorAll('[data-fvpxo]').forEach((s) => s.addEventListener('change', () => { o[s.dataset.fvpxo] = s.value; draw_(); }));
      box.querySelectorAll('[data-fvpxall]').forEach((bt) => bt.addEventListener('click', () => { o.all = true; draw_(); }));
      box.querySelectorAll('[data-fvpxp]').forEach((bt) => bt.addEventListener('click', () => {
        const p = bt.dataset.fvpxp, m = (P[o.metric] || {}).matched || {}, c = m.criteria || {};
        o = Object.assign({}, broad, { metric: o.metric }, p === 'weighted' ? { weight: 'all', hist: '5' } : p === 'matched' && c.key ? { group: 'sic' + c.sic, stage: c.stage, size: String(c.size), growth: c.growth.toFixed(2), margin: c.margin.toFixed(2) } : {});
        draw_();
      }));
    };
    det.addEventListener('toggle', () => {
      if (!det.open || PX.data) { if (det.open && PX.data) draw_(); return; }
      (PX.loading || (PX.loading = get(BASE + 'peers-list.json'))).then((D) => { PX.data = D; draw_(); }).catch((e) => { PX.loading = null; box.innerHTML = `<p class="fv-sub">The peer list could not load (${esc(e.message)}).</p>`; });
    });
  }

  // ---------- the peer multiples, plain and weighted (app/peer_weights.py) ----------
  const W_LAB = { pe: 'P/E', ev_ebitda: 'EV/EBITDA', ev_sales: 'EV/Sales', p_ffo: 'P/FFO (REITs)' };
  function weightedHtml(d) {
    const P = Object.assign({}, d.peers || {});
    if (d.sector_model && d.sector_model.peers && d.sector_model.peers.weighted) P.p_ffo = d.sector_model.peers;
    const rows = Object.keys(W_LAB).filter((k) => P[k] && P[k].weighted);
    if (!rows.length) return '';
    const x = (v) => (fin(v) ? num(v, 1) + '×' : '—');
    return `<h4>Plain and weighted, by each weight alone</h4><p class="fv-sub">The plain median counts every peer alike and only today's price. The weighted one gives each peer a weight from its share of the group's market value, revenue and trading value (none above 20%), and counts each peer's multiple at every quarter since 2022 with a one-year half-life — so small, thinly traded peers and old quarters move it less. "Effective peers": how many equal peers the weights amount to. The weighted rows on the football field are lenses: shown, not yet part of the stage-weighted value.</p>
      <div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Multiple</th><th class="n">Plain median</th><th class="n">By market value</th><th class="n">By revenue</th><th class="n">By trading value</th><th class="n">By recency</th><th class="n">Weighted (all)</th><th class="n">Weighted middle half</th><th class="n">Peers · effective</th><th>Largest weights</th></tr></thead><tbody>${rows.map((k) => {
        const p = P[k], w = p.weighted, b = w.by || {};
        return `<tr><td>${W_LAB[k]}</td><td class="n">${x(p.p50)}</td><td class="n">${x(b.mcap)}</td><td class="n">${x(b.revenue)}</td><td class="n">${x(b.dvol)}</td><td class="n">${w.timed ? x(b.time) : '<small>today only</small>'}</td><td class="n"><b>${x(w.p50)}</b></td><td class="n">${x(w.p25)} – ${x(w.p75)}</td><td class="n">${num(w.n)} · ${num(w.n_eff, 1)}</td><td><small>${esc((w.top || []).map(([t, v]) => `${t} ${num(100 * v)}%`).join(', '))}</small></td></tr>`;
      }).join('')}</tbody></table></div>`;
  }

  // ---------- each method against the price, and the present value of growth in it (valuation.growth_split) ----------
  function splitChart(rows, sp) {
    const ng = sp.no_growth, price = sp.price;
    const all = [{ method: "Today's share price", point: price, price: true }].concat(rows);
    const cap = fin(price) ? price * 4 : Math.max(...all.map((r) => r.point));
    const hi = Math.min(cap, Math.max(...all.map((r) => r.point), fin(ng) ? ng : 0)) * 1.06, lo = Math.min(0, fin(ng) ? ng : 0, ...all.map((r) => r.point));
    const W = 860, L = 250, R = 30, T = 16, rowH = 24, H = T + all.length * rowH + 26;
    const X = (v) => L + (Math.min(Math.max(v, lo), hi) - lo) / ((hi - lo) || 1) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Each method's value split into the no-growth value and the present value of growth">`;
    for (let k = 0; k <= 5; k++) { const v = lo + (hi - lo) * k / 5; s += `<line class="fv-grid" x1="${X(v)}" x2="${X(v)}" y1="${T - 6}" y2="${H - 22}"/><text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(usd(v))}</text>`; }
    all.forEach((r, i) => {
      const y = T + i * rowH, base = fin(ng) ? Math.max(0, Math.min(ng, r.point)) : 0;
      s += `<text class="fv-lbl" x="${L - 10}" y="${y + 15}" text-anchor="end"${r.price ? ' font-weight="600"' : ''}>${esc(r.method.length > 40 ? r.method.slice(0, 39) + '…' : r.method)}</text>`;
      if (fin(ng) && base > 0) s += `<rect x="${X(0)}" y="${y + 5}" width="${Math.max(1, X(base) - X(0))}" height="14" fill="${C.mute}" opacity="0.45"><title>no-growth value ${esc(usd(ng))}</title></rect>`;
      if (r.point > base) s += `<rect x="${X(base)}" y="${y + 5}" width="${Math.max(1, X(r.point) - X(base))}" height="14" fill="${r.price ? C.ink : C.acc}" opacity="${r.price ? 0.55 : 0.6}"><title>${esc(r.method)}: ${esc(usd(r.point))}${fin(ng) ? `, of which growth ${esc(usd(r.point - ng))}` : ''}</title></rect>`;
      if (r.point > hi) s += `<text x="${W - R + 4}" y="${y + 16}">→</text>`;
    });
    if (fin(price)) s += `<line x1="${X(price)}" x2="${X(price)}" y1="${T - 8}" y2="${H - 22}" stroke="${C.ink}" stroke-width="1.2" stroke-dasharray="4 3"/>`;
    if (fin(ng) && ng > lo) s += `<line x1="${X(ng)}" x2="${X(ng)}" y1="${T - 8}" y2="${H - 22}" stroke="${C.mute}" stroke-width="1" stroke-dasharray="2 3"/><text x="${X(ng)}" y="${T - 9}" text-anchor="middle" class="fv-lbl">no growth ${esc(usd(ng))}</text>`;
    return s + '</svg>';
  }
  function splitHtml(d) {
    const sp = d.growth_split, price = d.price;
    if (!sp || !fin(price)) return '';
    const rows = (d.football || []).filter((r) => fin(r.point) && fin(r.vs_price)).slice().sort((a, b) => b.point - a.point);
    if (!rows.length) return '';
    const ng = sp.no_growth, share = (v) => (!fin(v) ? '—' : v > 1 ? 'more than all of it' : v < 0 ? 'none (below the no-growth value)' : pct(v, 0));
    const g = (v) => (fin(v) ? spct(v, 1) + ' a year' : '—');
    let h = `<h3>What each method says about the share price — and how much of it is growth</h3><p class="fv-sub">For every method: the value per share it gives, how far that is from today's price, and how much of it is the <b>present value of growth</b>${fin(ng) ? ` — everything above the <b>no-growth value</b> of ${esc(usd(ng))} a share (${esc(sp.basis || '')}: ${esc(big(sp.earnings))} a year at ${pct(sp.rate, 1)}, today's earnings as if they never grew)` : ''}. The last column turns each value into the growth it requires: the constant revenue growth for five years (then the terminal rate) at which this page's DCF, with its margins and cost of capital, gives that value${sp.dcf ? '' : ' (no DCF for this company, so not shown)'}.</p>`;
    h += `<div class="fv-wrap">${splitChart(rows.filter((r) => r.point > 0), sp)}</div><div class="fv-legend"><span style="--k:${C.mute}">no-growth value</span><span style="--k:${C.acc}">present value of growth (a method)</span><span style="--k:${C.ink}">present value of growth in today's price</span></div>`;
    const line = (name, v, vs, pg, ps, ig, strong) => `<tr${strong ? ' class="fv-px-own"' : ''}><td>${strong ? `<b>${esc(name)}</b>` : esc(name)}</td><td class="n">${strong ? `<b>${esc(usd(v))}</b>` : esc(usd(v))}</td><td class="n">${vs == null ? '—' : `<span class="${vs > 0.15 ? 'fv-good' : vs < -0.15 ? 'fv-bad' : ''}">${spct(vs)}</span>`}</td><td class="n">${fin(ng) ? esc(usd(ng)) : '—'}</td><td class="n">${fin(pg) ? esc(usd(pg)) : '—'}</td><td class="n">${share(ps)}</td><td class="n">${g(ig)}</td></tr>`;
    h += `<div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Method</th><th class="n">Value per share</th><th class="n">vs today's price</th><th class="n">No-growth value</th><th class="n">Present value of growth</th><th class="n">Growth's share of the value</th><th class="n">Revenue growth it requires (5 years)</th></tr></thead><tbody>`
      + line("Today's share price", price, null, sp.price_pv_growth, sp.price_growth_share, sp.price_growth, true)
      + rows.map((r) => line(r.method, r.point, r.vs_price, r.pv_growth, r.pv_growth_share, r.implied_growth)).join('') + `</tbody></table></div>`;
    if (fin(sp.history_growth) && fin(sp.price_growth)) h += `<p class="fv-sub">Its revenue grew ${spct(sp.history_growth, 1)} over the last four quarters; today's price requires ${spct(sp.price_growth, 1)} a year for five years. A method's value above the price requires more growth than the price does, below it less. The no-growth value is the same for every method: it values the earnings the company makes today, not a forecast.</p>`;
    return h;
  }

  // ---------- football field: one bar per method, the price as a line ----------
  function football(rows, price) {
    rows = rows.filter((r) => fin(r.low) && fin(r.high));
    if (!rows.length) return '<p class="fv-sub">No method has enough data for this company yet.</p>';
    const vals = rows.flatMap((r) => [r.low, r.high]).concat(fin(price) ? [price] : []);
    const lo0 = Math.min(...vals), hi0 = Math.max(...vals);
    const cap = fin(price) ? price * 4 : hi0;                // a far-off bar is clipped and marked, not allowed to squash the rest
    const x0 = Math.max(0, Math.min(lo0, fin(price) ? price * 0.5 : lo0) * 0.92), x1 = Math.min(hi0, cap) * 1.06;
    const W = 860, L = 250, R = 30, T = 18, rowH = 26, H = T + rows.length * rowH + 26;
    const X = (v) => L + (Math.min(Math.max(v, x0), x1) - x0) / ((x1 - x0) || 1) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Valuation methods against the share price">`;
    for (let k = 0; k <= 5; k++) { const v = x0 + (x1 - x0) * k / 5; s += `<line class="fv-grid" x1="${X(v)}" x2="${X(v)}" y1="${T - 6}" y2="${H - 22}"/><text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(usd(v))}</text>`; }
    rows.forEach((r, i) => {
      const y = T + i * rowH, ctx = r.method === '52-week trading range';
      const col = ctx ? C.mute : fin(price) && r.high < price ? C.bad : fin(price) && r.low > price ? C.good : C.acc;
      s += `<text class="fv-lbl" x="${L - 10}" y="${y + 15}" text-anchor="end">${esc(r.method.length > 40 ? r.method.slice(0, 39) + '…' : r.method)}</text>`;
      s += `<rect x="${X(r.low)}" y="${y + 5}" width="${Math.max(2, X(r.high) - X(r.low))}" height="14" rx="4" fill="${col}" opacity="${ctx ? 0.35 : 0.55}"><title>${esc(r.method)}: ${esc(usd(r.low))} – ${esc(usd(r.high))}${fin(r.point) ? ' · ' + esc(usd(r.point)) : ''}${r.note ? ' — ' + esc(r.note) : ''}</title></rect>`;
      if (fin(r.point)) s += `<rect x="${X(r.point) - 1.5}" y="${y + 2}" width="3" height="20" fill="${C.ink}"/>`;
      if (r.high > x1) s += `<text x="${W - R + 4}" y="${y + 16}">→</text>`;
    });
    if (fin(price)) s += `<line x1="${X(price)}" x2="${X(price)}" y1="${T - 10}" y2="${H - 22}" stroke="${C.ink}" stroke-width="1.5" stroke-dasharray="4 3"/><text x="${X(price)}" y="${T - 12}" text-anchor="middle" class="fv-lbl">price ${esc(usd(price))}</text>`;
    return s + '</svg>';
  }

  function histogram(mc, price, base) {
    const h = mc.hist || {}, cs = h.counts || [];
    if (!cs.length || !(h.hi > h.lo)) return '';
    const W = 640, H = 200, L = 40, R = 12, T = 16, B = 26, mx = Math.max(...cs, 1), bw = (W - L - R) / cs.length;
    const X = (v) => L + (v - h.lo) / (h.hi - h.lo) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Monte Carlo distribution of value per share">`;
    cs.forEach((c, i) => { const v = h.lo + (h.hi - h.lo) * (i + 0.5) / cs.length, above = fin(price) && v > price;
      s += `<rect x="${L + i * bw + 0.5}" y="${T + (1 - c / mx) * (H - T - B)}" width="${bw - 1}" height="${c / mx * (H - T - B)}" fill="${above ? C.good : C.mute}" opacity="0.6"><title>${esc(usd(v))}: ${c} scenarios</title></rect>`; });
    for (let k = 0; k <= 4; k++) { const v = h.lo + (h.hi - h.lo) * k / 4; s += `<text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(usd(v))}</text>`; }
    const mark = (v, label, dash) => (fin(v) && v >= h.lo && v <= h.hi ? `<line x1="${X(v)}" x2="${X(v)}" y1="${T - 4}" y2="${H - B}" stroke="${C.ink}" ${dash ? 'stroke-dasharray="4 3"' : ''}/><text x="${X(v)}" y="${T - 6}" text-anchor="middle" class="fv-lbl">${esc(label)}</text>` : '');
    return s + mark(price, 'price', true) + mark(base, 'base', false) + '</svg>';
  }

  function bandsChart(b, key) {
    const idx = key === 'pe' ? 1 : 2, st = b[key], pts = (b.series || []).filter((r) => fin(r[idx]));
    if (!st || pts.length < 10) return '<p class="fv-sub">Not enough history for this measure.</p>';
    const W = 640, H = 220, L = 46, R = 50, T = 12, B = 24;
    const ys = pts.map((r) => r[idx]), y0 = Math.min(...ys, st.p10) * 0.95, y1 = Math.max(...ys, st.p90) * 1.05;
    const t0 = Date.parse(pts[0][0]), t1 = Date.parse(pts[pts.length - 1][0]);
    const X = (d) => L + (Date.parse(d) - t0) / ((t1 - t0) || 1) * (W - L - R), Y = (v) => T + (y1 - v) / ((y1 - y0) || 1) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${key === 'pe' ? 'P/E' : 'EV/Sales'} history with percentile bands">`;
    s += `<rect x="${L}" y="${Y(st.p90)}" width="${W - L - R}" height="${Y(st.p10) - Y(st.p90)}" fill="${C.acc}" opacity="0.08"/><rect x="${L}" y="${Y(st.p75)}" width="${W - L - R}" height="${Y(st.p25) - Y(st.p75)}" fill="${C.acc}" opacity="0.14"/>`;
    for (const [k, lbl] of [['p10', '10th'], ['p50', 'median'], ['p90', '90th']]) s += `<line x1="${L}" x2="${W - R}" y1="${Y(st[k])}" y2="${Y(st[k])}" stroke="${C.acc}" stroke-dasharray="3 3" opacity="0.7"/><text x="${W - R + 4}" y="${Y(st[k]) + 4}">${lbl} ${num(st[k], 1)}</text>`;
    s += `<path d="${pts.map((r, i) => (i ? 'L' : 'M') + X(r[0]).toFixed(1) + ',' + Y(r[idx]).toFixed(1)).join('')}" fill="none" stroke="${C.ink}" stroke-width="1.5"/>`;
    const yr0 = new Date(t0).getUTCFullYear(), yr1 = new Date(t1).getUTCFullYear();
    for (let y = yr0 + 1; y <= yr1; y++) { const d = `${y}-01-01`; s += `<text x="${X(d)}" y="${H - 6}" text-anchor="middle">${y}</text>`; }
    for (let k = 0; k <= 3; k++) { const v = y0 + (y1 - y0) * k / 3; s += `<text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${num(v, 1)}</text>`; }
    return s + '</svg>';
  }

  function scatter(fit, own, xl, yl) {
    const P = (fit && fit.points) || [];
    if (P.length < 5) return '';
    const W = 420, H = 260, L = 44, R = 12, T = 12, B = 30;
    const xs = P.map((p) => p[0]).concat(own ? [own[0]] : []), ys = P.map((p) => p[1]).concat(own ? [own[1]] : []);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys, 0), y1 = Math.max(...ys);
    const X = (v) => L + (v - x0) / ((x1 - x0) || 1) * (W - L - R), Y = (v) => T + (y1 - v) / ((y1 - y0) || 1) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(yl)} against ${esc(xl)}">`;
    P.forEach((p) => { s += `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3" fill="${C.mute}" opacity="0.6"><title>${esc(p[2])}: ${esc(xl)} ${pct(p[0])}, ${esc(yl)} ${num(p[1], 2)}×</title></circle>`; });
    s += `<line x1="${X(x0)}" x2="${X(x1)}" y1="${Y(fit.a + fit.b * x0)}" y2="${Y(fit.a + fit.b * x1)}" stroke="${C.acc}" stroke-width="1.5"/>`;
    if (own) s += `<circle cx="${X(own[0])}" cy="${Y(own[1])}" r="6" fill="${C.ink}"><title>this company</title></circle>`;
    s += `<text x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">${esc(xl)}</text><text x="12" y="${T + 10}">${esc(yl)}</text>`;
    return s + '</svg>';
  }

  // ---------- the outside view (app/base_rates.py) ----------
  function tilesHtml(d) {
    const br = d.base_rates || {}, T = br.tiles || [], ex = br.expected, price = d.price;
    if (!T.length && !ex) return '';
    const pcol = (p) => (!fin(p) ? '' : p < 0.2 ? 'fv-bad' : p < 0.4 ? 'fv-warn' : 'fv-good');
    const why = (t) => (t.basis === 'growth' ? (t.status === 'below' ? 'needs no growth' : t.status === 'above' ? 'needs over 100% a year' : `needs ${spct(t.required, 1)} a year for 5 years`)
      : t.basis === 'pe' ? `needs a P/E of ${num(t.required, 1)}` : '');
    let h = '<div class="fv-tiles">';
    if (ex) h += `<div class="fv-tile fv-exp"><em>Expected price — outside view (peers' base rates)</em><b>${usd(ex.price)}</b><small>80% range ${usd(ex.p10)}–${usd(ex.p90)}</small><span class="fv-p ${pcol(ex.p_above)}">${pp(ex.p_above)}<small> of draws above the price</small></span><div class="fv-bar"><i style="width:${fin(ex.p_above) ? (100 * ex.p_above).toFixed(0) : 0}%"></i></div></div>`;
    for (const t of T) {
      const gap = fin(price) && fin(t.price) ? spct(t.price / price - 1) + ' vs price' : '';
      h += `<div class="fv-tile" title="${esc(t.method)}${fin(t.p_mc) ? ' · ' + pp(t.p_mc) + ' of the outside-view Monte Carlo draws reach this price' : ''}"><em>${esc(t.method)}</em><b>${usd(t.price)}</b><small>${esc(gap)}</small>
        <span class="fv-p ${pcol(t.p)}">${pp(t.p)}<small> ${t.basis === 'pe' ? 'of peer quarters traded there' : 'of peers did it'}</small></span><div class="fv-bar"><i style="width:${fin(t.p) ? (100 * t.p).toFixed(0) : 0}%"></i></div><small>${esc(why(t))}</small></div>`;
    }
    const byGrowth = T.some((t) => t.basis === 'growth'), g = byGrowth ? br.growth_group : br.pe_group;
    return h + `</div><p class="fv-sub">Top: the price each method gives. Below: how often companies like this one achieved what that price requires — ${byGrowth && g ? `the share of ${num(g.n)} five-year windows of ${esc(g.label)} (${num(g.companies)} companies) whose revenue CAGR reached the growth the DCF needs for that price, with today's margins and cost of capital` : g ? `the share of ${num(g.n)} peer quarters (${esc(g.label)}) that traded at the P/E that price implies` : ''}. A base rate is a starting point, not a forecast: survivors only, and the company's own history is in its group.</p>`;
  }

  function oddsHtml(co) {
    const rows = ['market', 'street_eps', 'street_rev', 'street_margin', 'street_target', 'pm_eps', 'pm_price'].map((k) => co && co[k]).filter(Boolean);
    if (!rows.length) return '';
    const req = (r) => (r.what && r.what.startsWith('net-margin') ? (fin(r.required) ? (r.required >= 0 ? '+' : '−') + num(Math.abs(100 * r.required), 1) + ' pts' : '—')
      : r.status === 'below' ? 'no growth needed' : r.status === 'above' ? '> 100% a year' : spct(r.required, 1));
    const what = (r) => (fin(r.estimate) ? `${r.label.includes('revenue') ? big(r.estimate) : r.what.startsWith('net-margin') ? pct(r.estimate) : usd(r.estimate)} vs ${r.label.includes('revenue') ? big(r.year_ago) : r.what.startsWith('net-margin') ? pct(r.year_ago) : usd(r.year_ago)} a year earlier`
      : fin(r.strike) ? `line ${usd(r.strike)} vs ${usd(r.year_ago)} a year earlier` : fin(r.price) ? `${usd(r.price)} a share` : '');
    return `<h3>Three consensus views — how often peers got there</h3><p class="fv-sub">What each view requires, and how often it happened: <b>outside</b> = the share of peer observations at or above it (${esc((rows.find((r) => r.group_label) || {}).group_label || 'peer group')}); <b>inside</b> = the company's own history (its quarters since 2020; for 5-year growth, its own Monte Carlo spread). Polymarket's own price for the EPS line is shown beside it.</p>
      <div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>View</th><th>What it says</th><th>Requires</th><th class="n">Outside (peers)</th><th class="n">Inside (own)</th><th class="n">Market's odds</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.label)}</td><td>${esc(what(r))}${r.note ? `<br><small>${esc(r.note)}</small>` : ''}</td><td>${esc(r.what || '')}: <b>${esc(req(r))}</b></td><td class="n">${pp(r.p_outside)}${fin(r.n) ? `<br><small>of ${num(r.n)}</small>` : ''}</td><td class="n">${pp(r.p_inside)}${fin(r.n_inside) ? `<br><small>of ${num(r.n_inside)}</small>` : ''}</td><td class="n">${fin(r.p_market) ? pp(r.p_market) : ''}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function insideOutsideHtml(ov) {
    if (!ov || !(ov.rows || []).length) return '';
    const f = (v, fmt) => (fmt === 'x' ? (fin(v) ? num(v, 1) + '×' : '—') : pct(v));
    let h = `<h3>Inside view vs outside view</h3><p class="fv-sub">Left: this company's own figures. Right: what peers (${esc(ov.size_label || 'all sizes')}, narrowest SIC group with 40+ observations from 5+ companies) actually did — median and middle 80%. "Rank" is where the company's figure sits among the peers' observations.</p>
      <div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Input</th><th class="n">Inside (own)</th><th class="n">Outside: median</th><th class="n">10th–90th</th><th class="n">Rank</th><th>Peer group</th></tr></thead><tbody>`;
    for (const r of ov.rows) {
      const o = r.outside;
      h += `<tr><td>${esc(r.input)}${r.inside_note ? `<br><small>${esc(r.inside_note)}</small>` : ''}</td><td class="n">${f(r.inside, r.fmt)}</td><td class="n">${o ? f(o.p50, r.fmt) : '—'}</td><td class="n">${o ? f(o.p10, r.fmt) + ' – ' + f(o.p90, r.fmt) : '—'}</td><td class="n">${fin(r.inside_pct) ? num(100 * r.inside_pct) + 'th' : '—'}</td><td>${o ? `${esc(o.label)} <small>${num(o.n)} obs., ${num(o.companies)} cos.</small>` : '<small>too few peers</small>'}</td></tr>`;
    }
    h += '</tbody></table></div>';
    const a = ov.inside_mc, b = ov.mc;
    if (a || b) h += `<div class="fv-cards">${a ? card('Inside view: value > price', pp(a.p_above), '', `own-history Monte Carlo; median ${usd(a.p50)}`) : ''}${b ? card('Outside view: value > price', pp(b.p_above), '', `peers' base rates; median ${usd(b.p50)}, mean ${usd(b.mean)}`) : ''}${b ? card('Outside view 80% range', `${usd(b.p10)}–${usd(b.p90)}`, '', `${num(b.n)} DCFs from ${num(b.n_windows)} peer windows`) : ''}</div>`;
    return h;
  }

  function stageHtml(st) {
    if (!st) return '';
    const m = st.metrics || {}, items = [];
    if (fin(m.rule_of_40)) items.push(['Rule of 40 (growth % + FCF margin %)', num(m.rule_of_40, 0)]);
    if (fin(m.fcf_margin)) items.push(['Free-cash-flow margin', pct(m.fcf_margin)]);
    if (fin(m.cash_runway_years)) items.push(['Cash runway at today\'s burn', num(m.cash_runway_years, 1) + ' years']);
    if (fin(m.cagr3)) items.push(['Revenue CAGR, 3 years', pct(m.cagr3)]);
    if (fin(m.margin_sigma)) items.push(['σ of the quarterly operating margin', num(100 * m.margin_sigma, 1) + ' pts']);
    if (fin(m.mid_cycle_margin)) items.push(['Mid-cycle operating margin (median since 2020)', pct(m.mid_cycle_margin)]);
    if (fin(m.normalized_eps)) items.push(['Normalized EPS', usd(m.normalized_eps)]);
    if (fin(m.owner_earnings)) items.push(['Owner earnings (NI + D&A − capex)', big(m.owner_earnings)]);
    if (fin(m.shareholder_yield)) items.push(['Shareholder yield (dividends + buybacks)', pct(m.shareholder_yield)]);
    if (fin(m.tangible_book_ps)) items.push(['Tangible book per share', usd(m.tangible_book_ps)]);
    if (fin(m.fcf_to_debt)) items.push(['Free cash flow ÷ debt', pct(m.fcf_to_debt)]);
    if (fin(m.target_margin)) items.push(['Target margin (peer median)', pct(m.target_margin)]);
    let h = `<h3>Stage: ${esc(st.label)}<span class="fv-tag">${esc(st.why || '')}</span></h3><p class="fv-sub">Rule: ${esc(st.rule)}. What matters at this stage: ${esc(st.what_matters)}. The stage picks and weights the methods below; the weighted value is a row of the football field.</p><div class="fv-two"><div><table class="fv-tbl"><tbody>${items.map(([a, b]) => `<tr><td>${esc(a)}</td><td class="n">${b}</td></tr>`).join('')}</tbody></table></div>`;
    h += `<div><table class="fv-tbl"><thead><tr><th>Method</th><th class="n">Weight</th><th class="n">Value</th></tr></thead><tbody>${(st.used || []).map((u) => `<tr><td>${esc(u.method)}</td><td class="n">${pct(u.weight, 0)}</td><td class="n">${usd(u.point)}</td></tr>`).join('')}${fin(st.value) ? `<tr><td><b>Stage-weighted value</b></td><td></td><td class="n"><b>${usd(st.value)}</b></td></tr>` : '<tr><td colspan="3"><small>none of this stage\'s methods has enough data</small></td></tr>'}</tbody></table></div></div>`;
    return h;
  }

  function tornado(bars, base, price) {
    if (!(bars || []).length) return '';
    // the axis spans the bars; a price far outside them (Waters: $457 against a $68 base) would squeeze every bar into a
    // corner, so it is marked at the edge with its value instead of stretching the scale
    const span = bars.flatMap((b) => [b.low, b.high]).concat([base]).filter(fin);
    const lo = Math.min(...span), hi = Math.max(...span), wide = (hi - lo) || Math.abs(hi) || 1;
    const near = fin(price) && price >= lo - wide && price <= hi + wide;
    const vals = span.concat(near ? [price] : []);
    const x0 = Math.min(...vals) - 0.05 * Math.abs(Math.min(...vals)), x1 = Math.max(...vals) + 0.05 * Math.abs(Math.max(...vals));
    const W = 860, L = 300, R = 70, T = 16, rh = 24, H = T + bars.length * rh + 26, P0 = L + 64;
    const X = (v) => P0 + (v - x0) / ((x1 - x0) || 1) * (W - P0 - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tornado: value per share as each input moves">`;
    bars.forEach((b, i) => {
      const y = T + i * rh;
      s += `<text class="fv-lbl" x="${L - 8}" y="${y + 15}" text-anchor="end">${esc(b.input)} <tspan fill="${C.mute}">${esc(b.how)}</tspan></text>`;
      s += `<rect x="${X(b.low)}" y="${y + 4}" width="${Math.max(0, X(base) - X(b.low))}" height="14" fill="${C.bad}" opacity="0.55"><title>${esc(usd(b.low))}</title></rect>`;
      s += `<rect x="${X(base)}" y="${y + 4}" width="${Math.max(0, X(b.high) - X(base))}" height="14" fill="${C.good}" opacity="0.55"><title>${esc(usd(b.high))}</title></rect>`;
      s += `<text x="${X(b.low) - 3}" y="${y + 15}" text-anchor="end">${esc(usd(b.low))}</text><text x="${X(b.high) + 3}" y="${y + 15}">${esc(usd(b.high))}</text>`;
    });
    s += `<line x1="${X(base)}" x2="${X(base)}" y1="${T - 4}" y2="${H - 20}" stroke="${C.ink}"/><text x="${X(base)}" y="${H - 6}" text-anchor="middle" class="fv-lbl">base ${esc(usd(base))}</text>`;
    if (near) s += `<line x1="${X(price)}" x2="${X(price)}" y1="${T - 4}" y2="${H - 20}" stroke="${C.ink}" stroke-dasharray="4 3"/><text x="${X(price)}" y="${T - 4}" text-anchor="middle">price ${esc(usd(price))}</text>`;
    else if (fin(price)) {
      const right = price > hi, x = right ? W - 4 : P0 - 4;
      s += `<text x="${x}" y="${T - 4}" text-anchor="${right ? 'end' : 'start'}" class="fv-lbl">${right ? '' : '← '}price ${esc(usd(price))}${right ? ' →' : ''} <tspan fill="${C.mute}">(off this scale)</tspan></text>`;
    }
    return s + '</svg>';
  }

  function gridHtml(g, price, fmtRow, fmtCol) {
    if (!g || !(g.values || []).length) return '';
    const cap = `<p class="fv-sub">Rows: ${esc(g.row_label)}. Columns: ${esc(g.col_label)}.</p>`;
    const cell = (v) => { if (!fin(v) || !fin(price)) return `<td class="n">${usd(v)}</td>`; const r = v / price - 1, a = Math.min(0.5, Math.abs(r)) / 0.5 * 0.35;
      return `<td class="n" style="background:color-mix(in srgb, ${r >= 0 ? C.good : C.bad} ${(a * 100).toFixed(0)}%, transparent)" title="${esc(spct(r))} vs price">${usd(v)}</td>`; };
    return cap + `<div class="fv-wrap"><table class="fv-tbl fv-heat"><thead><tr><th>↓ · →</th>${g.cols.map((c) => `<th class="n">${fmtCol(c)}</th>`).join('')}</tr></thead><tbody>${g.values.map((row, i) => `<tr><th>${fmtRow(g.rows[i])}</th>${row.map(cell).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  function sensHtml(se, price) {
    if (!se) return '';
    let h = `<h3>Sensitivity — ${esc(se.method)}</h3><p class="fv-sub">How the value per share moves when one input moves (others held): the inputs are sorted by how much they swing the value. ${se.driver ? `<b>${esc(se.driver)}</b> moves it most (${spct(se.driver_swing)} of the base value across its range).` : ''} Cells: green above today's price, red below.</p><div class="fv-wrap">${tornado(se.tornado, se.base_value, price)}</div>`;
    const P = (v) => pct(v, 1);
    h += `<div class="fv-two"><div>${gridHtml(se.grid_growth_wacc, price, P, P)}</div>`;
    if (se.grid_margin_multiple) h += `<div>${gridHtml(se.grid_margin_multiple, price, P, (c) => num(c, 1) + '×')}<p class="fv-sub">Next year's revenue × operating margin × (1 − tax) × P/E, per share.</p></div>`;
    return h + '</div>';
  }

  function riverChart(rv, key) {
    const m = rv && rv.metrics && rv.metrics[key];
    if (!m) return '<p class="fv-sub">Not enough history for this multiple.</p>';
    const W = 680, H = 260, L = 50, R = 56, T = 12, B = 24, n = rv.weeks.length;
    const S = rv.steps || {}, st = rv.step || [];
    const line = (lv, i) => { const x = (S[key] || [])[st[i]]; if (!fin(x) || x <= 0) return null; const nd = key === 'ev_ebitda' ? (S.nd || [])[st[i]] : 0; const v = lv * x - (fin(nd) ? nd : 0); return v > 0 ? v : null; };
    const ys = rv.price.filter(fin);
    m.levels.forEach((lv) => { for (let i = 0; i < n; i++) { const v = line(lv, i); if (fin(v)) ys.push(v); } });
    const y0 = 0, y1 = Math.max(...ys) * 1.05;
    const t0 = Date.parse(rv.weeks[0]), t1 = Date.parse(rv.weeks[n - 1]);
    const X = (i) => L + (Date.parse(rv.weeks[i]) - t0) / ((t1 - t0) || 1) * (W - L - R), Y = (v) => T + (y1 - v) / ((y1 - y0) || 1) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Price river: price against fixed ${esc(m.label)} multiples">`;
    m.levels.forEach((lv, k) => {
      let d = '', pen = false, last = null;
      for (let i = 0; i < n; i++) { const v = line(lv, i); if (!fin(v)) { pen = false; continue; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(Math.min(v, y1)).toFixed(1); pen = true; last = [i, v]; }
      if (d) s += `<path d="${d}" fill="none" stroke="${C.acc}" stroke-width="1.2" opacity="${(0.35 + 0.5 * k / Math.max(1, m.levels.length - 1)).toFixed(2)}"/>`;
      if (last && last[1] <= y1) s += `<text x="${W - R + 4}" y="${Y(last[1]) + 4}">${num(lv, lv < 10 ? 1 : 0)}×</text>`;
    });
    s += `<path d="${rv.price.map((v, i) => (fin(v) ? (i ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(v).toFixed(1) : '')).join('')}" fill="none" stroke="${C.ink}" stroke-width="1.8"/>`;
    const yr0 = new Date(t0).getUTCFullYear(), yr1 = new Date(t1).getUTCFullYear();
    for (let y = yr0 + 1; y <= yr1; y++) { const t = Date.parse(`${y}-01-01`); s += `<text x="${L + (t - t0) / ((t1 - t0) || 1) * (W - L - R)}" y="${H - 6}" text-anchor="middle">${y}</text>`; }
    for (let k = 0; k <= 3; k++) { const v = y1 * k / 3; s += `<text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${esc(usd(v))}</text>`; }
    return s + '</svg>';
  }

  function riverHtml(rv) {
    if (!rv || !rv.metrics) return '';
    const keys = ['pe', 'ps', 'pb', 'ev_ebitda'].filter((k) => rv.metrics[k]);
    if (!keys.length) return '';
    const m0 = rv.metrics[keys[0]];
    return `<h3>River charts</h3><p class="fv-sub">The share price (black) against the price it would have had at fixed multiples (blue lines, darker = higher) of the trailing figure. ${esc(rv.note || '')}. Now: ${keys.map((k) => `${esc(rv.metrics[k].label)} ${num(rv.metrics[k].current, 1)}× (${num(100 * rv.metrics[k].pct)}th percentile of its history)`).join(' · ')}.</p>
      <div>${keys.map((k, i) => `<button type="button" class="fv-tog${i ? '' : ' on'}" data-fvr="${k}">${esc(rv.metrics[k].label)}</button>`).join('')}</div><div class="fv-wrap" data-fvriver>${riverChart(rv, keys[0])}</div>${m0 ? '' : ''}`;
  }

  // the return a buyer at today's price earns if each model is right (app/valuation_extra.py implied_return)
  function impliedHtml(ir) {
    if (!ir || !(ir.rows || []).length) return '';
    return `<h3>The return today's price implies</h3><p class="fv-sub">${esc(ir.note || '')}</p><table class="fv-tbl"><thead><tr><th>Model</th><th class="n">Implied return a year</th><th>How</th></tr></thead><tbody>${ir.rows.map((r) => `<tr><td>${esc(r.method)}</td><td class="n">${pct(r.r, 1)}</td><td>${esc(r.how)} <span class="fv-tag">vs ${esc(r.vs)}</span></td></tr>`).join('')}<tr><td><b>Median</b></td><td class="n"><b>${pct(ir.median, 1)}</b></td><td>cost of equity ${pct(ir.ke, 1)} · WACC ${pct(ir.wacc, 1)}${fin(ir.spread) ? ` · <b class="${ir.spread > 0 ? 'fv-good' : 'fv-bad'}">${ir.spread >= 0 ? '+' : '−'}${pct(Math.abs(ir.spread), 1)}</b> ${ir.spread >= 0 ? 'above' : 'below'} the cost of equity` : ''}</td></tr></tbody></table>`;
  }
  // Greenwald's split: the business as it is (EPV) against the price and the assets (tangible book)
  function epvHtml(e, price) {
    if (!e || !fin(e.epv_ps) || !fin(price) || price <= 0) return '';
    const hi = Math.max(price, e.epv_ps, fin(e.tangible_book_ps) ? e.tangible_book_ps : 0) * 1.08, w = (v) => `${Math.max(0, Math.min(100, v / hi * 100)).toFixed(1)}%`;
    const row = (label, v, col) => `<div class="fv-epv"><span>${esc(label)}</span><i style="width:${w(v)};background:${col}"></i><b>${usd(v)}</b></div>`;
    return `<h3>Earnings power: the business as it is vs growth</h3><p class="fv-sub">Earnings power value (EPV) values today's business as if it never grew (normalized margin ${pct(e.margin_used, 1)}). ${fin(e.growth_share) ? (e.growth_share > 0 ? `The other <b>${pct(e.growth_share, 0)}</b> of the price is paid for growth.` : 'The price is below EPV: it pays nothing for growth and prices in a decline.') : ''} ${e.franchise === true ? 'EPV is above tangible book: the business earns more than its assets would cost to rebuild — a sign of a moat.' : e.franchise === false ? 'EPV is below tangible book: the assets earn less than their cost.' : ''}</p>
      ${row('Price', price, C.mute)}${row('EPV (no growth)', e.epv_ps, C.acc)}${fin(e.tangible_book_ps) && e.tangible_book_ps > 0 ? row('Tangible book', e.tangible_book_ps, C.warn) : ''}`;
  }
  function combinedHtml(cb) {
    if (!cb) return '';
    const w = cb.weights || {};
    return `<p class="fv-sub"><b>Combined forecast (3 months):</b> ${usd(cb.price)} (${spct(cb.ret)}), 80% range ${usd(cb.low)}–${usd(cb.high)}. Weights learned walk-forward on standardized signals — ${Object.entries(w).filter(([k]) => k !== 'intercept').map(([k, v]) => `${esc(k.replace('_', ' '))} ${(v >= 0 ? '+' : '−') + num(Math.abs(100 * v), 1)}%/σ`).join(', ')}; range from earlier out-of-sample errors (conformal). ${cb.replaces_rotation ? 'It beat the Rotation forecast out of sample on the same companies and quarters, so it is "Our model" here.' : 'Shown beside the Rotation forecast: it has not beaten it on the same companies and quarters (or no paired test exists yet). Scores: Valuation tab → Models.'}</p>`;
  }

  // ---------- the appendix: every method's algebra with this company's numbers, every input's source, every assumption ----------
  // the guide's entry for a football row: exact name, an alias prefix ("Rotation forecast" → "Our model"), then a key prefix
  function explainer(name) {
    const M = (guide && guide.methods) || {};
    if (M[name]) return M[name];
    for (const [pre, key] of Object.entries((guide && guide.aliases) || {})) if (name.startsWith(pre) && M[key]) return M[key];
    for (const key of Object.keys(M)) if (name.startsWith(key)) return M[key];
    return null;
  }
  // abbreviations used in a text, written out in full: "WACC = weighted average cost of capital"
  const reEsc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  function termsIn(text) {
    const out = [];
    for (const g of (guide && guide.glossary) || []) {
      const hit = (g.abbr || []).some((tok) => {
        const pre = /^[A-Za-z0-9]/.test(tok) ? '(^|[^A-Za-z0-9_])' : '', post = /[A-Za-z0-9²ₑₜ₆]$/.test(tok) ? '(?![A-Za-z0-9_])' : '';
        return new RegExp(pre + reEsc(tok) + post).test(text);
      });
      if (hit) out.push(g);
    }
    return out;
  }
  const lower1 = (x) => (/^[A-Z][a-z]/.test(x) ? x[0].toLowerCase() + x.slice(1) : x);
  function guideHtml(A, tbl) {
    if (!guide) return '';
    const st = A.stage || {};
    const P = guide.primer, S = guide.startups;
    const young = ['pre_revenue', 'pre_profit'].includes(st.key);
    let h = `<details class="fv-apx fv-guide"><summary><b>${esc(P.title)}</b> — start here if valuation is new to you</summary><div class="fv-prose">${P.paras.map((x) => `<p>${esc(x)}</p>`).join('')}</div></details>`;
    h += `<details class="fv-apx fv-guide"${young ? ' open' : ''}><summary><b>${esc(S.title)}</b>${young ? ' <span class="fv-tag">this company\'s stage</span>' : ''}</summary><div class="fv-prose">${S.paras.map((x) => `<p>${esc(x)}</p>`).join('')}</div>`
      + `<div class="fv-gl">${tbl(['Approach', 'How it works', 'On this site'], S.classic || [])}</div></details>`;
    if (guide.peers) h += `<details class="fv-apx fv-guide"><summary><b>${esc(guide.peers.title)}</b></summary><div class="fv-prose">${guide.peers.paras.map((x) => `<p>${esc(x)}</p>`).join('')}</div></details>`;
    const G = guide.glossary || [];
    h += `<details class="fv-apx fv-guide"><summary><b>Glossary</b> — every term and abbreviation in full (${G.length})</summary>`
      + `<div class="fv-gl">${tbl(['Term', 'In full', 'What it means'], G.map((g) => [g.term, g.full, g.plain]))}</div></details>`;
    return h;
  }
  function stageHtml(st) {
    if (!st.label) return '';
    const g = guide && guide.stages ? (guide.stages[st.key] || Object.values(guide.stages).find((x) => x.label === st.label)) : null;
    return `<h4>The stage and its weights</h4><p class="fv-sub"><b>${esc(st.label)}</b> — ${esc(st.why || '')}. Rule: ${esc(st.rule || '')}.</p>`
      + (g ? `<div class="fv-x"><p><b>What this stage means.</b> ${esc(g.means)}</p><p><b>Why these methods and weights.</b> ${esc(g.why)}</p></div>` : '')
      + `<p class="fv-sub">Weights, fixed before any result is seen and renormalized over the methods this company has: ${(st.weights || []).map(([m, w]) => `${esc(m)} ${num(100 * w, 0)}%`).join(' · ')}.</p>`;
  }
  function methodGuide(m) {
    const x = explainer(m.method);
    if (!x && !m.fit) return '';
    const text = [x && x.what, m.formula, ...(m.steps || []), m.fit, ...(m.assumptions || []).map((a) => a[0])].filter(Boolean).join(' ');
    const T = termsIn(text);
    return `<div class="fv-x">${x ? `<p><b>What it is.</b> ${esc(x.what)}</p><p><b>Why it works.</b> ${esc(x.why)}</p><p><b>Fits.</b> ${esc(x.fits)}</p>` : ''}`
      + (m.fit ? `<p class="fv-here"><b>Why it applies here.</b> ${esc(m.fit)}</p>` : '')
      + (x ? `<p><b>Watch out.</b> ${esc(x.watch)}</p>` : '')
      + (T.length ? `<p class="fv-terms"><b>Terms.</b> ${T.map((g) => `${esc(g.term)} = ${esc(lower1(g.full))}`).join(' · ')}</p>` : '') + '</div>';
  }
  function appendixHtml(A) {
    if (!A || !(A.methods || []).length) return '';
    const tbl = (head, rows) => rows.length ? `<div class="fv-wrap"><table class="fv-tbl"><thead><tr>${head.map((x) => `<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i === 1 && head.length === 3 && head[1] === 'Value' ? ' class="n"' : ''}>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '';
    const kindTag = { model: 'model', blend: 'blend of the methods above', reference: 'reference, not a valuation' };
    const st = A.stage || {};
    let h = `<h3 id="fv-appendix">Appendix — every method, its algebra and where each number comes from</h3><p class="fv-sub">For each method on the football field: what it is and why it applies to this company, its formula, the same formula with this company's figures in it, the inputs it used (and where each came from) and the assumptions it makes (and why). Then the methods this company does not get, and why. New to valuation? Open “${esc((guide && guide.primer && guide.primer.title) || 'Valuation from zero')}” first; every abbreviation is in the glossary. <button type="button" class="fv-tog" data-fvapx="open">Open all</button><button type="button" class="fv-tog" data-fvapx="close">Close all</button></p>`;
    h += guideHtml(A, tbl);
    h += stageHtml(st);
    h += `<details class="fv-apx"><summary><b>Inputs and their sources</b> (${(A.inputs || []).length})</summary>${tbl(['Input', 'Value', 'Source'], A.inputs || [])}</details>`;
    h += `<details class="fv-apx"><summary><b>Assumptions and their basis</b> (${(A.assumptions || []).length})</summary>${tbl(['Assumption', 'Value', 'Basis'], A.assumptions || [])}</details>`;
    if (A.wacc) {
      const T = termsIn([A.wacc.formula, ...(A.wacc.steps || [])].join(' '));
      h += `<details class="fv-apx"><summary><b>Cost of capital, step by step</b></summary>${guide ? `<div class="fv-x"><p><b>What it is.</b> The weighted average cost of capital (WACC) is the yearly return the company must earn to satisfy everyone who funds it: shareholders, through the cost of equity from the capital asset pricing model (CAPM), and lenders, through the interest rate after tax, each weighted by its share of the funding at market values. Cash flows that belong to the whole company are discounted at this rate.</p>${T.length ? `<p class="fv-terms"><b>Terms.</b> ${T.map((g) => `${esc(g.term)} = ${esc(lower1(g.full))}`).join(' · ')}</p>` : ''}</div>` : ''}<p class="fv-f">${esc(A.wacc.formula)}</p><ol class="fv-steps">${A.wacc.steps.map((x) => `<li>${esc(x)}</li>`).join('')}</ol></details>`;
    }
    h += A.methods.map((m) => {
      const x = explainer(m.method);
      return `<details class="fv-apx"><summary><b>${esc(m.method)}</b> · ${fin(m.point) ? usd(m.point) : '—'}${fin(m.low) && fin(m.high) ? ` <span class="fv-tag">${usd(m.low)} – ${usd(m.high)}</span>` : ''}${fin(m.weight) ? ` <span class="fv-tag">stage weight ${num(100 * m.weight, 0)}%</span>` : ''}${m.kind && m.kind !== 'model' ? ` <span class="fv-tag">${esc(kindTag[m.kind] || m.kind)}</span>` : x && x.family ? ` <span class="fv-tag">${esc(x.family.toLowerCase())}</span>` : ''}</summary>`
        + methodGuide(m)
        + (fin(m.vs_price) ? `<p class="fv-sub"><b>Against the price:</b> ${spct(m.vs_price)} vs today's price${fin(m.pv_growth) ? `; present value of growth ${esc(usd(m.pv_growth))} a share (${m.pv_growth_share > 1 ? 'more than all' : m.pv_growth_share < 0 ? 'none' : pct(m.pv_growth_share, 0)} of the value; the rest is today's earnings as if they never grew)` : ''}${fin(m.implied_growth) ? `; it requires revenue growth of ${spct(m.implied_growth, 1)} a year for five years in this page's DCF` : ''}.</p>` : '')
        + (m.formula ? `<p class="fv-f">${esc(m.formula)}</p>` : '') + ((m.steps || []).filter(Boolean).length ? `<ol class="fv-steps">${m.steps.filter(Boolean).map((y) => `<li>${esc(y)}</li>`).join('')}</ol>` : '')
        + tbl(['Input', 'Value', 'Source'], m.inputs || []) + tbl(['Assumption', 'Value', 'Basis'], m.assumptions || []) + '</details>';
    }).join('');
    if ((A.not_used || []).length) h += `<details class="fv-apx"><summary><b>Methods not used for this company</b> (${A.not_used.length})</summary>${tbl(['Method', 'Why not', 'What it is'], A.not_used.map((x) => { const e = explainer(x.method); return [x.method, x.why, e ? e.what.split(/(?<=\.)\s/)[0] : '']; }))}</details>`;
    return h + (A.note ? `<p class="fv-note">${esc(A.note)}</p>` : '');
  }
  function draw(el, d, fits) {
    css();
    const price = d.price, W = d.wacc || {}, mc = d.mc, pv = d.pvgo, cr = d.credit || {}, dist = cr.distress, dc = d.dcf;
    const tone = (v) => (!fin(v) ? '' : v > 0.15 ? 'fv-good' : v < -0.15 ? 'fv-bad' : '');
    let h = `<div class="fv"><p class="fv-sub">Many ways to value ${esc(d.name || d.ticker)}, side by side, against the share price ${esc(usd(price))}${d.price_date ? ` (${esc(d.price_date)})` : ''}. Every assumption is shown below and every method has known blind spots — the spread between them is the point. Not investment advice.</p>`;
    h += `<div class="fv-cards">${card('Cost of capital (WACC)', pct(W.wacc), '', W.beta ? `beta ${num(W.beta, 2)} · debt ${pct(W.kd)}` : '')}
      ${card('DCF base case', usd(dc && dc.value), dc ? tone(dc.value / price - 1) : '', dc && fin(price) ? spct(dc.value / price - 1) + ' vs price' : 'no DCF for this company')}
      ${card('Monte Carlo: value > price', mc ? pct(mc.p_above, 0) : '—', '', mc ? `${num(mc.n)} scenarios` : '')}
      ${card('Price paid for growth', pv ? pct(pv.growth_share, 0) : '—', '', pv ? 'PVGO share of market value' : '')}
      ${card('Distress (1 year, model blend)', dist ? pct(dist.pd, dist.pd < 0.01 ? 2 : 1) : '—', dist ? (dist.pd > 0.05 ? 'fv-bad' : dist.pd > 0.01 ? 'fv-warn' : 'fv-good') : '', cr.rating_band ? `spread-implied ${esc(cr.rating_band)}` : '')}
      ${d.implied_return ? card('Return the price implies', pct(d.implied_return.median, 1), fin(d.implied_return.spread) ? (d.implied_return.spread > 0.01 ? 'fv-good' : d.implied_return.spread < -0.01 ? 'fv-bad' : '') : '', fin(d.implied_return.ke) ? `a year, vs ${pct(d.implied_return.ke, 1)} cost of equity` : 'a year') : ''}</div>`;
    h += `<h3>Valuation football field</h3><p class="fv-sub">Each bar is one method's range, the black tick its central value, the dashed line today's price. Green: the whole range above the price; red: below.</p><div class="fv-wrap">${football(d.football || [], price)}</div>`;
    h += `<div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Method</th><th class="n">Low</th><th class="n">Central</th><th class="n">High</th><th class="n">vs price</th><th>How</th></tr></thead><tbody>${(d.football || []).map((r) => `<tr><td>${esc(r.method)}${r.lens ? '<span class="fv-tag" title="Shown with its algebra in the appendix; not part of the stage-weighted value or the headline range until the ledger has scored it">lens</span>' : ''}</td><td class="n">${usd(r.low)}</td><td class="n">${usd(r.point)}</td><td class="n">${usd(r.high)}</td><td class="n">${fin(r.vs_price) ? `<span class="${r.vs_price > 0.15 ? 'fv-good' : r.vs_price < -0.15 ? 'fv-bad' : ''}">${spct(r.vs_price)}</span>` : '—'}</td><td>${esc(r.note || '')}</td></tr>`).join('')}</tbody></table></div>`;
    h += splitHtml(d);
    h += tiersHtml(d) + weightedHtml(d) + tilesHtml(d) + combinedHtml(d.combined);
    if (d.reverse && d.reverse.status === 'ok') h += `<p><b>Reverse DCF:</b> today's price needs revenue growth of <b>${pct(d.reverse.implied_growth)}</b> a year for five years (then ${pct((dc && dc.assumptions.g) || 0.025)}), with the margins and cost of capital below. The last four quarters grew ${pct(d.reverse.history_growth)} on the four before.</p>`;
    else if (d.reverse) h += `<p class="fv-sub">Reverse DCF: no single growth rate between −30% and 60% gives today's price with these assumptions.</p>`;
    if (pv) {
      const ng = Math.max(0, Math.min(1, 1 - pv.growth_share));
      h += `<h3>What the price pays for: today's earnings vs growth</h3><p class="fv-sub">No-growth value = ${esc(pv.basis)} (${esc(big(pv.earnings))} at ${pct(pv.rate)}) = ${esc(usd(pv.per_share))} a share. ${pv.growth_share >= 0 ? `The other <b>${pct(pv.growth_share, 0)}</b> of the market value is the present value of growth opportunities (PVGO).` : 'The price is below the no-growth value: the market prices in a decline.'}</p>
        <div class="fv-stack" role="img" aria-label="No-growth value vs growth share"><i style="width:${(ng * 100).toFixed(1)}%;background:${C.acc}"></i><i style="width:${((1 - ng) * 100).toFixed(1)}%;background:${C.warn}"></i></div>
        <div class="fv-legend"><span style="--k:${C.acc}">no-growth value ${pct(ng, 0)}</span><span style="--k:${C.warn}">growth ${pct(1 - ng, 0)}</span></div>`;
    }
    h += impliedHtml(d.implied_return) + epvHtml(d.epv, price);
    h += oddsHtml(d.consensus_odds) + insideOutsideHtml(d.outside_view) + stageHtml(d.stage) + sensHtml(d.sensitivity, price);
    if (mc) h += `<h3>Monte Carlo DCF</h3><p class="fv-sub">${num(mc.n)} scenarios: revenue growth ~ N(${pct(mc.assumptions.growth[0])}, ${pct(mc.assumptions.growth[1])}), EBIT margin ~ N(${pct(mc.assumptions.margin[0])}, ${pct(mc.assumptions.margin[1])}), WACC ~ N(${pct(mc.assumptions.wacc[0])}, 1 pt), terminal growth 1.5–3%. The spreads come from the company's own history. Median ${esc(usd(mc.p50))}, middle 80% ${esc(usd(mc.p10))}–${esc(usd(mc.p90))}; <b>${pct(mc.p_above, 0)}</b> of scenarios are worth more than the price.</p><div class="fv-wrap">${histogram(mc, price, dc && dc.value)}</div>`;
    if (d.markov) h += '<div data-fvmk><p class="fv-sub">Loading the regime-switching model…</p></div>';
    if (d.rnpv || d.schwartz_moon || d.rnpv_why) h += '<div data-fvsim><p class="fv-sub">Loading the simulations…</p></div>';
    h += `<div class="fv-two"><div><h3>Cost of capital</h3><table class="fv-tbl"><tbody>
      <tr><td>10-year Treasury</td><td class="n">${pct(W.rf, 2)}</td></tr><tr><td>Beta (weekly vs SPY, ${num(W.beta_weeks)} weeks; Blume-adjusted)</td><td class="n">${num(W.beta_raw, 2)} → ${num(W.beta, 2)}</td></tr>
      <tr><td>Equity risk premium (assumption)</td><td class="n">${pct(W.erp, 1)}</td></tr><tr><td><b>Cost of equity</b></td><td class="n"><b>${pct(W.ke, 2)}</b></td></tr>
      <tr><td>Cost of debt <span class="fv-tag">${esc(W.kd_how || '')}</span></td><td class="n">${pct(W.kd, 2)}</td></tr><tr><td>After tax at ${pct(W.tax, 0)}</td><td class="n">${pct(W.kd_after_tax, 2)}</td></tr>
      <tr><td>Weights: equity / debt (market values)</td><td class="n">${pct(W.w_equity, 0)} / ${pct(W.w_debt, 0)}</td></tr><tr><td><b>WACC</b></td><td class="n"><b>${pct(W.wacc, 2)}</b></td></tr></tbody></table>${W.beta_note ? `<p class="fv-sub">${esc(W.beta_note)}</p>` : ''}</div>`;
    h += `<div><h3>Credit</h3><table class="fv-tbl"><tbody><tr><td>Distance to default (Merton)</td><td class="n">${num(cr.distance_to_default, 1)}</td></tr><tr><td>Merton 1-year default probability</td><td class="n">${pct(cr.merton_pd_1y, 2)}</td></tr>
      <tr><td>5-year spread, bond-calibrated</td><td class="n">${fin(cr.cds_5y_bps) ? num(cr.cds_5y_bps, 0) + ' bp' : '—'}</td></tr><tr><td>Altman Z</td><td class="n">${num(cr.altman_z, 2)}</td></tr><tr><td>Debt cushion score (0–100)</td><td class="n">${num(cr.cushion_score)}</td></tr>
      ${dist ? dist.parts.map((p) => `<tr><td>· ${esc(p.name)} (weight ${pct(p.weight, 0)})</td><td class="n">${pct(p.pd, 2)}</td></tr>`).join('') + `<tr><td><b>Distress probability, 1 year</b></td><td class="n"><b>${pct(dist.pd, 2)}</b></td></tr>` : ''}</tbody></table><p class="fv-sub">${esc(cr.note || '')}</p></div></div>`;
    if (d.bands) {
      h += `<h3>Valuation bands</h3><p class="fv-sub">Weekly since ${esc(d.bands.from || '')}, trailing figures counted 60 days after each quarter ends. Shaded: middle 50% and 80% of the history.${d.bands.pe ? ` P/E now ${num(d.bands.pe.current, 1)} — the ${num(100 * d.bands.pe.pct)}th percentile of its range.` : ''}${d.bands.evs ? ` EV/Sales ${num(d.bands.evs.current, 2)} — the ${num(100 * d.bands.evs.pct)}th percentile.` : ''}</p>
        <div><button type="button" class="fv-tog on" data-fvb="pe">P/E</button><button type="button" class="fv-tog" data-fvb="evs">EV/Sales</button></div><div class="fv-wrap" data-fvbands>${bandsChart(d.bands, d.bands.pe ? 'pe' : 'evs')}</div>`;
    }
    h += riverHtml(d.river);
    const sm = d.sector_model;
    if (sm) {
      h += `<h3>${esc(sm.model)}</h3>`;
      if (sm.model.startsWith('P/TBV')) h += `<p class="fv-sub">Tangible book ${esc(big(sm.tbv))}; ROTCE ${pct(sm.rotce)}; P/TBV ${num(sm.ptbv, 2)}× vs ${num(sm.fitted_ptbv, 2)}× fitted across ${num(sm.fit && sm.fit.n)} banks (r² ${num(sm.fit && sm.fit.r2, 2)}).</p>${scatter(fits && fits.bank, fin(sm.rotce) && fin(sm.ptbv) ? [sm.rotce, sm.ptbv] : null, 'ROTCE', 'P/TBV')}`;
      else if (sm.model.startsWith('P/B')) h += `<p class="fv-sub">${fin(sm.combined_ratio) ? `Combined ratio ${pct(sm.combined_ratio)} (claims + acquisition and other underwriting costs ÷ premiums earned, trailing four quarters). ` : 'Combined ratio: not tagged in XBRL. '}${fin(sm.roe) ? `ROE ${pct(sm.roe)}; P/B ${num(sm.pb, 2)}× vs ${num(sm.fitted_pb, 2)}× fitted across ${num(sm.fit && sm.fit.n)} insurers.` : ''}</p>${scatter(fits && fits.insurer, fin(sm.roe) && fin(sm.pb) ? [sm.roe, sm.pb] : null, 'ROE', 'P/B')}`;
      else h += `<p class="fv-sub">FFO ${esc(big(sm.ffo))}${fin(sm.p_ffo) ? `; P/FFO ${num(sm.p_ffo, 1)}×` : ''}${sm.peers ? ` vs a REIT median of ${num(sm.peers.p50, 1)}×` : ''}. ${esc(sm.note || '')}</p>`;
    }
    if (d.sotp) {
      const sw = d.sotp.weighted, ss = d.sotp.selected, wc = d.sotp.parts.some((p) => fin(p.ev_sales_w)), sc = d.sotp.parts.some((p) => fin(p.ev_sales_s));
      const priced = (p) => `${esc(p.tag_short || p.tag_label || String(p.group).replace(/^sic/, 'SIC ').replace(/^sec:/, 'sector '))}<br><small>${esc(p.how || '')}${fin(p.n) ? ` · ${num(p.n)} peers` : ''}</small>`;
      const mv = (m, v, extra) => (fin(m) ? `${num(m, 1)}× → ${big(v)}${extra ? `<br><small>${extra}</small>` : ''}` : '<small>—</small>');
      h += `<h3>Sum of the parts</h3><p class="fv-sub">Each segment is priced by the peers of its business model: the company's own mapping first (config/peer-map.json), then rules on the segment's name; a generic name such as "Services" or "Products" is priced like the company itself rather than guessed from one word. Each cell: EV/Sales → the segment's value.</p><div class="fv-wrap"><table class="fv-tbl fv-sotp"><thead><tr><th>Segment</th><th class="n">Revenue (annualised)</th><th>Priced like</th><th class="n">Broad median</th>${wc ? '<th class="n">Weighted</th>' : ''}${sc ? '<th class="n">Selected companies</th>' : ''}</tr></thead><tbody>${d.sotp.parts.map((p) => `<tr><td>${esc(p.segment)}</td><td class="n">${big(p.revenue)}</td><td>${priced(p)}</td><td class="n">${mv(p.ev_sales, p.ev)}</td>${wc ? `<td class="n">${mv(p.ev_sales_w, p.ev_w, esc((p.top || []).map(([t, w]) => `${t} ${num(100 * w)}%`).join(', ')))}</td>` : ''}${sc ? `<td class="n">${fin(p.ev_sales_s) ? mv(p.ev_sales_s, p.ev_s, esc((p.comps || []).slice(0, 4).map(([t, , m]) => `${t} ${num(m, 1)}×`).join(', ') + ((p.comps || []).length > 4 ? ` +${p.comps.length - 4} more` : ''))) : '<small>no list: the broad median</small>'}</td>` : ''}</tr>`).join('')}<tr><td><b>Per share</b></td><td></td><td><small>after net debt, ÷ diluted shares</small></td><td class="n"><b>${esc(usd(d.sotp.point))}</b><br><small>${esc(usd(d.sotp.low))}–${esc(usd(d.sotp.high))}</small></td>${wc ? `<td class="n"><b>${esc(usd(sw && sw.point))}</b>${sw ? `<br><small>${esc(usd(sw.low))}–${esc(usd(sw.high))}</small>` : ''}</td>` : ''}${sc ? `<td class="n"><b>${esc(usd(ss && ss.point))}</b>${ss ? `<br><small>${esc(usd(ss.low))}–${esc(usd(ss.high))}</small>` : ''}</td>` : ''}</tr></tbody></table></div><p class="fv-sub">${esc(d.sotp.note)}.${sw ? ` Weighted: ${esc(sw.note)}.` : ''}${ss ? ` Selected: ${esc(ss.note)}.` : ''}</p>`;
    }
    if ((d.notes || []).length) h += `<p class="fv-note">${d.notes.map(esc).join('<br>')}</p>`;
    h += `<div data-fvapxwrap>${appendixHtml(d.appendix)}</div>`;
    const src = Object.entries(d.sources || {}).map(([k, v]) => `${k}: ${v}`).join(' · ');
    h += `<p class="fv-note">Figures from: ${esc(src || '—')}. Built ${esc((d.generated_at || '').slice(0, 10))} by app/valuation.py from SEC filings (XBRL), the hub's daily prices, the Debt & rates and Consensus modules. Peer groups are SIC industries; a group needs six peers.</p></div>`;
    el.innerHTML = h;
    const mkEl = el.querySelector('[data-fvmk]');
    if (mkEl) loadMarkov().then((MV) => MV.mount(mkEl, d)).catch((e) => { mkEl.innerHTML = `<p class="fv-sub">The regime-switching model could not load (${esc(e.message)}).</p>`; });
    const svEl = el.querySelector('[data-fvsim]');
    if (svEl) loadSim().then((SV) => SV.mount(svEl, d)).catch((e) => { svEl.innerHTML = `<p class="fv-sub">The simulations could not load (${esc(e.message)}).</p>`; });
    const bindApx = () => el.querySelectorAll('[data-fvapx]').forEach((b) => b.addEventListener('click', () => { el.querySelectorAll('details.fv-apx').forEach((x) => { x.open = b.dataset.fvapx === 'open'; }); }));
    bindApx();
    bindPx(el, d);
    if (!guide && d.appendix && typeof window !== 'undefined') loadGuide().then(() => {      // the guide arrived after the page: redraw the appendix
      const w = el.querySelector('[data-fvapxwrap]');
      if (w && el.isConnected !== false) { w.innerHTML = appendixHtml(d.appendix); bindApx(); }
    }).catch(() => {});
    el.querySelectorAll('[data-fvb]').forEach((b) => b.addEventListener('click', () => {
      el.querySelectorAll('[data-fvb]').forEach((x) => x.classList.toggle('on', x === b));
      el.querySelector('[data-fvbands]').innerHTML = bandsChart(d.bands, b.dataset.fvb);
    }));
    el.querySelectorAll('[data-fvr]').forEach((b) => b.addEventListener('click', () => {
      el.querySelectorAll('[data-fvr]').forEach((x) => x.classList.toggle('on', x === b));
      el.querySelector('[data-fvriver]').innerHTML = riverChart(d.river, b.dataset.fvr);
    }));
  }

  function get(url) {
    if (!store[url]) store[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).catch((e) => { delete store[url]; throw e; });
    return store[url];
  }

  async function render(el, ctx) {
    const base = (ctx && ctx.hub != null ? ctx.hub : '') + 'data/research/valuation/';
    BASE = base;
    el.innerHTML = '<p class="muted">Loading the valuation…</p>';
    let d;
    const gReady = loadGuide().catch(() => null);                       // in parallel with the company's data
    try { d = await get(base + `c/${Number(ctx.cik)}.json`); } catch (e) {
      el.innerHTML = `<p class="muted">No fair-value page for this company yet (${esc(e.message)}). It is built every day after the US close for companies with a share price and filed figures.</p>`;
      return;
    }
    if (ctx.here && !ctx.here()) return;
    const fits = {};
    if (d.kind === 'bank') fits.bank = (await get(base + 'banks.json').catch(() => ({}))).fit;
    if (d.kind === 'insurer') fits.insurer = (await get(base + 'insurers.json').catch(() => ({}))).fit;
    await gReady;
    if (ctx.here && !ctx.here()) return;
    draw(el, d, fits);
  }

  const api = { render, draw, appendixHtml, explainer, termsIn, setGuide, football, histogram, bandsChart, riverChart, tornado, tilesHtml, oddsHtml, usd, pct, pp, weightedHtml, tiersHtml, pxRun, pxHtml, wq, capW, scoresHtml, splitHtml, splitChart };
  if (typeof window !== 'undefined') window.FairValueView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
