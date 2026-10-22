/* Regime-switching Monte Carlo — the "markov" block of a Fair value document (app/markov.py), drawn inside
   fairvalue-view.js. The engine below is the same model as app/markov.py, with the same random draws (mulberry32, seed
   20251027, Box–Muller), so the browser reproduces the published numbers and can re-run them for the sensitivity
   surfaces. The 3D charts load Plotly from cdnjs only when the reader asks for them.
   window.MarkovView = { simulate, draws, mount(el, doc) }. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), Math.abs(v) >= 1000 ? 0 : 2) : '—');
  const pct = (v, d = 1) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const NAMES = ['High growth', 'Steady', 'Decline'];
  // cdnjs stops at 2.35.0 in the 2.35 line (2.35.2 is a 404 there); jsDelivr's npm build is the fallback
  const PLOTLY = ['https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.0/plotly.min.js',
    'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js'];
  const SEED = 20251027;

  // ---------- the engine (mirrors app/markov.py) ----------
  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  const DRAWS = {};
  function draws(n, years, seed = SEED) {
    const key = n + ':' + years + ':' + seed;
    if (DRAWS[key]) return DRAWS[key];
    const r = mulberry32(seed), N = n * years, U = new Float64Array(N), Zg = new Float64Array(N), Zm = new Float64Array(N);
    const nrm = () => { let u = 0; while (u === 0) u = r(); const v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
    for (let k = 0; k < N; k++) { U[k] = r(); Zg[k] = nrm(); Zm[k] = nrm(); }
    return (DRAWS[key] = { U, Zg, Zm });
  }
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  function simulate(p, o = {}) {
    const n = o.n || 2000, T = p.years, D = draws(n, T), dg = o.dg || 0, w = o.wacc != null ? o.wacc : p.wacc, P = o.P || p.P;
    const cum = P.map((r) => [r[0], r[0] + r[1]]), gT = p.g_term, cap = Math.max(w - gT, 0.01), reinv = 1 - gT / p.roic, tax = p.tax;
    const cons = p.cons || [], csd = p.cons_sd || 0, capex = Array.isArray(p.capex) ? p.capex : [p.capex];
    const claims = p.debt + p.claims - p.cash, out = new Float64Array(n);
    const hv = o.track ? Array.from({ length: T }, () => new Float64Array(n)) : null;
    for (let i = 0; i < n; i++) {
      let s = p.start, rev = p.rev0, m = p.m0, pv = 0, df = 1;
      for (let t = 0; t < T; t++) {
        const k = i * T + t, u = D.U[k], c = cum[s];
        s = u < c[0] ? 0 : (u < c[1] ? 1 : 2);
        let gr = t < cons.length ? cons[t] + dg + csd * D.Zg[k] : p.g[s] + dg + p.g_sd[s] * D.Zg[k];
        gr = clamp(gr, -0.5, 1.0);
        const prev = rev;
        rev = prev * (1 + gr);
        m = clamp(m + p.dm[s] + p.kappa * (p.m0 - m) + p.m_sd * D.Zm[k], -0.5, 0.7);
        const ebit = rev * m, nopat = ebit > 0 ? ebit * (1 - tax) : ebit;
        const fcff = nopat + rev * (p.da - capex[Math.min(t, capex.length - 1)] - p.sbc) - (rev - prev) * p.wc;
        df /= 1 + w; pv += fcff * df;
        if (hv || t === T - 1) {
          const nxt = rev * (1 + gT), e1 = nxt * m;
          const tv = ((e1 > 0 ? e1 * (1 - tax) : e1) * reinv - nxt * p.sbc) / cap;
          const v = (pv + tv * df - claims) / p.shares;
          if (hv) hv[t][i] = v;
          if (t === T - 1) out[i] = v;
        }
      }
    }
    return o.track ? { out, hv } : out;
  }
  const sorted = (a) => Float64Array.from(a).sort();
  const q = (s, p) => { const k = (s.length - 1) * p, lo = Math.floor(k), hi = Math.ceil(k); return s[lo] + (s[hi] - s[lo]) * (k - lo); };
  const median = (a) => q(sorted(a), 0.5);

  // ---------- static parts (SVG, drawn with the host's colours) ----------
  const C = { good: 'var(--mk-profit, #2e8b57)', bad: 'var(--mk-cost, #c0392b)', steady: 'var(--mk-rev, #8a8f98)', acc: 'var(--accent, #2a78d6)', mute: 'var(--muted, #888)', ink: 'var(--ink, #222)' };
  const SC = [C.good, C.steady, C.bad];
  function histogram(mk, price) {
    const h = mk.hist || {}, cs = h.counts || [];
    if (!cs.length || !(h.hi > h.lo)) return '';
    const W = 640, H = 200, L = 40, R = 12, T = 16, B = 26, mx = Math.max(...cs, 1), bw = (W - L - R) / cs.length;
    const X = (v) => L + (v - h.lo) / (h.hi - h.lo) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Regime model: distribution of value per share">`;
    cs.forEach((c, i) => { const v = h.lo + (h.hi - h.lo) * (i + 0.5) / cs.length;
      s += `<rect x="${L + i * bw + 0.5}" y="${T + (1 - c / mx) * (H - T - B)}" width="${bw - 1}" height="${c / mx * (H - T - B)}" fill="${fin(price) && v > price ? C.good : C.mute}" opacity="0.6"><title>${esc(usd(v))}: ${c} paths</title></rect>`; });
    for (let k = 0; k <= 4; k++) { const v = h.lo + (h.hi - h.lo) * k / 4; s += `<text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(usd(v))}</text>`; }
    const mark = (v, label, dash) => (fin(v) && v >= h.lo && v <= h.hi ? `<line x1="${X(v)}" x2="${X(v)}" y1="${T - 4}" y2="${H - B}" stroke="${C.ink}" ${dash ? 'stroke-dasharray="4 3"' : ''}/><text x="${X(v)}" y="${T - 6}" text-anchor="middle" class="fv-lbl">${esc(label)}</text>` : '');
    return s + mark(price, 'price', true) + mark(mk.p50, 'median', false) + '</svg>';
  }
  function occupancy(rows) {
    if (!rows || !rows.length) return '';
    const W = 640, H = 120, L = 40, R = 12, T = 8, B = 22, bw = (W - L - R) / rows.length;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Regime probabilities by year">`;
    rows.forEach((pi, t) => {
      let y = T;
      pi.forEach((v, j) => { const h = v * (H - T - B); s += `<rect x="${L + t * bw + 1}" y="${y}" width="${bw - 2}" height="${h}" fill="${SC[j]}" opacity="0.7"><title>Year ${t}: ${NAMES[j]} ${pct(v, 0)}</title></rect>`; y += h; });
      s += `<text x="${L + t * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${t}</text>`;
    });
    return s + `<text x="4" y="${T + 10}">100%</text><text x="4" y="${H - B}">0</text></svg>`;
  }

  // ---------- 3D (Plotly, loaded on demand) ----------
  let plotlyLoad = null;
  const loadFrom = (src) => new Promise((ok, bad) => {
    const sc = document.createElement('script');
    sc.src = src; sc.async = true; sc.crossOrigin = 'anonymous';
    sc.onload = () => (window.Plotly ? ok(window.Plotly) : bad(new Error('no Plotly')));
    sc.onerror = () => { sc.remove(); bad(new Error('the chart library did not load')); };
    document.head.appendChild(sc);
  });
  const loadPlotly = () => plotlyLoad || (plotlyLoad = window.Plotly ? Promise.resolve(window.Plotly)
    : PLOTLY.reduce((p, src) => p.catch(() => loadFrom(src)), Promise.reject(new Error('start')))
      .catch(() => { plotlyLoad = null; throw new Error('the chart library did not load'); }));
  function colors(el) {
    const cs = getComputedStyle(el), v = (n, f) => (cs.getPropertyValue(n) || '').trim() || f;
    return { good: v('--mk-profit', '#2e8b57'), bad: v('--mk-cost', '#c0392b'), steady: v('--mk-rev', '#8a8f98'), acc: v('--accent', '#2a78d6'),
      mute: v('--muted', '#888'), ink: v('--ink', '#222'), line: v('--line', '#ddd'), bg: v('--bg', '#fff') };
  }
  function grids(mk) {
    const p = mk.model, NG = 1000;
    const ex = []; for (let v = -6; v <= 6; v++) ex.push(v);
    const w0 = p.wacc, ey = []; for (let d = -2.5; d <= 2.51; d += 0.5) ey.push(+(w0 + d / 100).toFixed(4));
    const ez = ey.map((w) => ex.map((dg) => (w - p.g_term > 0.005 ? median(simulate(p, { n: NG, dg: dg / 100, wacc: w })) : null)));
    const tx = [], ty = [];
    for (let a = 0; a <= 0.5001; a += 0.05) { tx.push(+a.toFixed(2)); ty.push(+a.toFixed(2)); }
    const tz = ty.map((d) => tx.map((u) => {
      if (u + d > 0.95) return null;
      const P = p.P.map((r) => r.slice()), fx = p.start;
      P[fx] = fx === 0 ? [1 - u - d, u, d] : fx === 1 ? [u, 1 - u - d, d] : [u, 1 - u - d, d];
      return median(simulate(p, { n: NG, P }));
    }));
    const tr = simulate(p, { n: 2000, track: true }), last = sorted(tr.hv[p.years - 1]);
    const lo = Math.max(0, q(last, 0.01)) * 0.9, hi = q(last, 0.99), B = 45, step = (hi - lo) / B || 1;
    const ys = Array.from({ length: B }, (_, i) => lo + step * (i + 0.5)), rz = ys.map(() => new Array(p.years).fill(0));
    tr.hv.forEach((arr, t) => { for (const v of arr) { const b = Math.floor((v - lo) / step); if (b >= 0 && b < B) rz[b][t] += 1 / arr.length; } });
    return { el: { x: ex, y: ey, z: ez }, tp: { x: tx, y: ty, z: tz, rowName: NAMES[p.start] }, ridge: { x: Array.from({ length: p.years }, (_, i) => i + 1), y: ys, z: rz, p50: tr.hv.map(median) } };
  }
  function draw3d(box, mk, price, G, mode) {
    const P = window.Plotly, K = colors(box), p = mk.model;
    const cfg = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['toImage', 'lasso2d', 'select2d'] };
    const scale = [[0, K.bad], [0.5, K.steady], [1, K.good]];
    // hover labels in the page's own colours (card background, ink text, a hairline border), readable in light and dark
    // themes alike; Plotly's default is white text on the colour of the point, which vanishes on a light page
    const solid = /^#|^rgb\(/.test(K.bg) ? K.bg : '#ffffff';
    const hoverlabel = { bgcolor: solid, bordercolor: K.mute, font: { color: K.ink, size: 12 }, align: 'left' };
    const lay = (extra) => Object.assign({ paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { size: 11, color: K.ink }, hoverlabel,
      margin: { l: 56, r: 16, t: 8, b: 44 }, xaxis: { gridcolor: K.line, color: K.mute }, yaxis: { gridcolor: K.line, color: K.mute } }, extra);
    const ax = (title, fmt) => ({ title: { text: title, font: { size: 11 } }, gridcolor: K.line, zerolinecolor: K.line, color: K.mute, backgroundcolor: 'rgba(0,0,0,0)', tickformat: fmt || '' });
    const scene = (xt, yt, zt, xf, yf) => ({ margin: { l: 0, r: 0, t: 0, b: 0 }, scene: { xaxis: ax(xt, xf), yaxis: ax(yt, yf), zaxis: ax(zt),
      camera: { eye: { x: 1.6, y: -1.6, z: 0.9 } }, aspectmode: 'manual', aspectratio: { x: 1, y: 1, z: 0.7 } } });
    const hm = (D, xt, yt, xf, yf, marks) => P.react(box.querySelector(`[data-mk3="${D.id}"]`), [{ type: 'heatmap', x: D.x, y: D.y, z: D.z, colorscale: scale,
      colorbar: { thickness: 10, tickprefix: '$', tickfont: { color: K.mute } }, hovertemplate: `${xt} %{x}<br>${yt} %{y}<br>$%{z:.2f}<extra></extra>` },
      ...(fin(price) ? [{ type: 'contour', x: D.x, y: D.y, z: D.z, contours: { start: price, end: price, size: 1, coloring: 'none' }, line: { color: K.ink, width: 2, dash: 'dot' }, showscale: false, hoverinfo: 'skip' }] : []),
      ...marks], lay({ xaxis: { title: { text: xt }, color: K.mute, tickformat: xf || '' }, yaxis: { title: { text: yt }, color: K.mute, tickformat: yf || '' } }), cfg);
    const sf = (D, xt, yt, xf, yf, extra) => P.react(box.querySelector(`[data-mk3="${D.id}"]`), [{ type: 'surface', x: D.x, y: D.y, z: D.z, colorscale: scale, showscale: false,
      contours: { z: { show: true, usecolormap: true } }, hovertemplate: `${xt} %{x}<br>${yt} %{y}<br>$%{z:.2f}<extra></extra>` },
      ...(fin(price) ? [{ type: 'surface', x: D.x, y: D.y, z: D.y.map(() => D.x.map(() => price)), opacity: 0.3, showscale: false, colorscale: [[0, K.acc], [1, K.acc]], hoverinfo: 'skip' }] : []),
      ...extra], lay(scene(xt, yt, 'Value per share ($)', xf, yf)), cfg);
    const el = { id: 'el', ...G.el }, tp = { id: 'tp', ...G.tp };
    const ptEl = { x: [0], y: [p.wacc], z: [mk.p50] }, row = p.P[p.start];
    const ptTp = { x: [p.start === 0 ? row[1] : row[0]], y: [row[2]], z: [mk.p50] };
    const dot3 = (pt, label) => ({ type: 'scatter3d', mode: 'markers', ...pt, marker: { size: 5, color: K.ink }, hovertemplate: label + '<extra></extra>' });
    const dot2 = (pt, label) => ({ type: 'scatter', mode: 'markers', x: pt.x, y: pt.y, marker: { size: 10, color: K.ink, symbol: 'circle-open', line: { width: 2 } }, hovertemplate: label + '<extra></extra>' });
    const upName = p.start === 0 ? 'P(→ steady)' : 'P(→ high growth)';
    if (mode.el === '3d') sf(el, 'Growth shift (pts)', 'WACC', '+d', '.1%', [dot3(ptEl, 'model as published')]);
    else hm(el, 'Growth shift (pts)', 'WACC', '+d', '.1%', [dot2(ptEl, 'model as published')]);
    if (mode.tp === '3d') sf(tp, upName, 'P(→ decline)', '.0%', '.0%', [dot3(ptTp, 'estimated matrix')]);
    else hm(tp, upName, 'P(→ decline)', '.0%', '.0%', [dot2(ptTp, 'estimated matrix')]);
    const R = G.ridge, rbox = box.querySelector('[data-mk3="ridge"]');
    if (mode.ridge === '3d') P.react(rbox, [{ type: 'surface', x: R.x, y: R.y, z: R.z, colorscale: [[0, K.bg], [0.2, K.steady], [1, K.acc]], showscale: false,
      hovertemplate: 'Year %{x}<br>$%{y:.2f}<br>share %{z:.3f}<extra></extra>' },
    ...(fin(price) ? [{ type: 'scatter3d', mode: 'lines', x: R.x, y: R.x.map(() => price), z: R.x.map(() => 0), line: { color: K.bad, width: 4 }, hovertemplate: 'price<extra></extra>' }] : [])],
    lay(scene('Years of forecast', 'Value per share ($)', 'Share of paths')), cfg);
    else P.react(rbox, [{ type: 'heatmap', x: R.x, y: R.y, z: R.z, colorscale: [[0, K.bg], [1, K.acc]], showscale: false, hovertemplate: 'Year %{x}<br>$%{y:.2f}<br>share %{z:.3f}<extra></extra>' },
      { type: 'scatter', mode: 'lines', x: R.x, y: R.p50, line: { color: K.ink, width: 2 }, name: 'median', hoverinfo: 'skip' },
      ...(fin(price) ? [{ type: 'scatter', mode: 'lines', x: [1, p.years], y: [price, price], line: { color: K.bad, width: 1.5, dash: 'dot' }, name: 'price', hoverinfo: 'skip' }] : [])],
    lay({ showlegend: false, xaxis: { title: { text: 'Years of forecast' }, color: K.mute, dtick: 1 }, yaxis: { title: { text: 'Value per share ($)' }, color: K.mute, tickprefix: '$' } }), cfg);
  }

  // ---------- the section ----------
  function mount(el, d) {
    const mk = d && d.markov;
    if (!mk || !mk.model) { el.innerHTML = ''; return; }
    const p = mk.model, price = d.price, S = mk.sources || {}, own = mk.own_counts || [[0, 0, 0], [0, 0, 0], [0, 0, 0]], pr = (mk.prior || {}).P || [];
    const occ = mk.occupancy || [], ss = occ[occ.length - 1] || [];
    const tone = fin(mk.p_above) ? (mk.p_above >= 0.6 ? 'fv-good' : mk.p_above <= 0.4 ? 'fv-bad' : '') : '';
    const card = (label, value, cls = '', note = '') => `<div class="fv-card"><span>${esc(label)}</span><b class="${cls}">${value}</b>${note ? `<i>${note}</i>` : ''}</div>`;
    const cell = (i, j) => `<td class="n" title="own transitions ${own[i][j]} of ${own[i].reduce((a, b) => a + b, 0)}; panel prior ${pct(pr[i] && pr[i][j], 0)}">${pct(p.P[i][j], 0)}</td>`;
    let h = `<h3>Regime-switching Monte Carlo</h3><p class="fv-sub">Revenue growth moves between three regimes (high growth ≥ 10% a year, steady 0–10%, decline below 0) by a Markov chain: next year's regime depends only on this year's. ${num(mk.n)} paths over ${p.years} years from today's regime, <b>${esc(NAMES[p.start])}</b>. Every input below is estimated from filings, the whole covered panel, analysts' consensus or the cost-of-capital build-up; none is typed in.</p>
      <div class="fv-cards">${card('Median value', usd(mk.p50), '', fin(price) ? (mk.p50 >= price ? '+' : '−') + pct(Math.abs(mk.p50 / price - 1), 0) + ' vs price' : '')}
      ${card('Middle 80%', `${usd(mk.p10)} – ${usd(mk.p90)}`)}
      ${card('Paths worth more than the price', pct(mk.p_above, 0), tone)}
      ${card('Long-run regime mix', ss.length ? `${pct(ss[0], 0)} / ${pct(ss[1], 0)} / ${pct(ss[2], 0)}` : '—', '', 'high / steady / decline, year ' + p.years)}</div>
      <div class="fv-wrap">${histogram(mk, price)}</div>
      <div class="fv-two"><div><h4 style="margin:10px 0 4px;font-size:14px">Transition probabilities (row: this year → column: next year)</h4><div class="fv-wrap"><table class="fv-tbl"><thead><tr><th></th>${NAMES.map((n) => `<th class="n">${n}</th>`).join('')}<th class="n">Own years</th></tr></thead><tbody>
      ${NAMES.map((n, i) => `<tr><td>${i === p.start ? '<b>' + n + '</b> (now)' : n}</td>${[0, 1, 2].map((j) => cell(i, j)).join('')}<td class="n">${own[i].reduce((a, b) => a + b, 0)}</td></tr>`).join('')}</tbody></table></div>
      <p class="fv-sub">${esc(S.matrix || '')}.${S.thin ? ' ' + esc(S.thin) + '.' : ''} Hover a cell for the company's own count and the panel's rate.</p></div>
      <div><h4 style="margin:10px 0 4px;font-size:14px">Regime probabilities, year by year</h4><div class="fv-wrap">${occupancy(occ)}</div>
      <div class="fv-legend">${NAMES.map((n, j) => `<span style="--k:${SC[j]}">${n}</span>`).join('')}</div></div></div>
      <div class="fv-wrap"><table class="fv-tbl"><thead><tr><th>Input</th><th class="n">Value</th><th>Source</th></tr></thead><tbody>
      <tr><td>Growth by regime (mean ± σ)</td><td class="n">${[0, 1, 2].map((s) => `${pct(p.g[s], 0)}±${pct(p.g_sd[s], 0)}`).join(' / ')}</td><td>${esc(S.growth || '')}</td></tr>
      <tr><td>Years 1–2</td><td class="n">${p.cons && p.cons.length ? p.cons.map((g) => pct(g)).join(', ') : 'regime model'}</td><td>${esc(S.years_1_2 || '')}</td></tr>
      <tr><td>EBIT margin drift by regime; pull-back κ; σ</td><td class="n">${p.dm.map((v) => (v >= 0 ? '+' : '−') + num(Math.abs(v) * 100, 1)).join(' / ')} pts; ${num(p.kappa, 2)}; ${pct(p.m_sd)}</td><td>${esc(S.margin || '')}; σ: ${esc(S.margin_sd || '')}</td></tr>
      <tr><td>Stock-based compensation</td><td class="n">${pct(p.sbc)} of revenue</td><td>${esc(S.sbc || '')}</td></tr>
      <tr><td>Discount rate</td><td class="n">${pct(p.wacc, 2)}</td><td>${esc(S.wacc || '')}</td></tr>
      <tr><td>Terminal value</td><td class="n">${pct(p.g_term)}</td><td>${esc(S.terminal || '')}</td></tr></tbody></table></div>
      <p><button type="button" class="fv-tog" data-mk-open>Show 3D sensitivity</button><span class="fv-sub" data-mk-status style="margin-left:6px">Re-runs the same model in your browser and loads a 3.5 MB chart library.</span></p>
      <div data-mk-3d hidden>
        <h4 style="margin:12px 0 2px;font-size:14px">Value surface: growth × cost of capital</h4><p class="fv-sub">Every regime's growth shifted together (x) against the WACC (y); height is the median value. The flat sheet is today's price: where the surface is above it, the price is covered. The dot is the model as published.</p>
        <div><button type="button" class="fv-tog on" data-mk-mode="el:3d">3D</button><button type="button" class="fv-tog" data-mk-mode="el:2d">Flat</button></div><div data-mk3="el" style="height:420px"></div>
        <h4 style="margin:12px 0 2px;font-size:14px">Value surface: the regime switches themselves</h4><p class="fv-sub">Only today's row of the matrix changes (${esc(NAMES[p.start])}): the chance of moving up (x) and of falling into decline (y). This shows how much the value rests on the regime assumptions rather than on growth or the discount rate.</p>
        <div><button type="button" class="fv-tog on" data-mk-mode="tp:3d">3D</button><button type="button" class="fv-tog" data-mk-mode="tp:2d">Flat</button></div><div data-mk3="tp" style="height:420px"></div>
        <h4 style="margin:12px 0 2px;font-size:14px">How the range opens up with the horizon</h4><p class="fv-sub">For each year t, the value if the forecast stopped there (cash flows to t plus a terminal value at t): the share of paths at each value. The red line is the price.</p>
        <div><button type="button" class="fv-tog on" data-mk-mode="ridge:3d">3D</button><button type="button" class="fv-tog" data-mk-mode="ridge:2d">Flat</button></div><div data-mk3="ridge" style="height:420px"></div>
      </div>`;
    el.innerHTML = h;
    const box = el.querySelector('[data-mk-3d]'), status = el.querySelector('[data-mk-status]'), mode = { el: '3d', tp: '3d', ridge: '3d' };
    let G = null;
    el.querySelector('[data-mk-open]').addEventListener('click', async (e) => {
      const b = e.currentTarget;
      if (!box.hidden) { box.hidden = true; b.textContent = 'Show 3D sensitivity'; return; }
      status.textContent = 'Loading…';
      try {
        await loadPlotly();
        box.hidden = false; b.textContent = 'Hide 3D sensitivity';
        await new Promise((r) => setTimeout(r, 20));
        const t0 = performance.now();
        G = G || grids(mk);
        draw3d(box, mk, price, G, mode);
        status.textContent = `${Math.round(performance.now() - t0)} ms in your browser.`;
      } catch (err) { status.textContent = `The 3D charts could not load (${err.message}).`; }
    });
    el.querySelectorAll('[data-mk-mode]').forEach((b) => b.addEventListener('click', () => {
      const [k, m] = b.dataset.mkMode.split(':');
      mode[k] = m;
      el.querySelectorAll(`[data-mk-mode^="${k}:"]`).forEach((x) => x.classList.toggle('on', x === b));
      if (G && window.Plotly) draw3d(box, mk, price, G, mode);
    }));
  }

  const api = { simulate, draws, mulberry32, mount, grids };
  if (typeof window !== 'undefined') window.MarkovView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
