/* 4.6 RRG — money flows (rrg.js: the 2-D chart, weekly and monthly). Data: data/research/flows/index.json and
   t/<TICKER>.json (app/flows.py, branch research-flows), loaded for the lines on the chart.
   US markets publish no large-order ("main force") figures, so both measures are estimates:
   · big-money net buying — FINRA's off-exchange short sale volume: a dealer filling a client's buy order from its own
     book reports a short sale, so a week whose off-exchange short share is above the ticker's own last 52 weeks had more
     buying there than usual (the "dark index" idea): 2 × that excess, as a share of the off-exchange volume (and in
     dollars, × the off-exchange dollars, where FINRA's shares and the split-adjusted bars fit);
   · net money inflow — Chaikin's money flow from the daily bars: each day's dollars weighted by where it closed in its
     range (+1 at the high, −1 at the low), as a share of the dollars traded.
   Both over the weeks chosen (1, 4 or 13), so lines of any size read on one scale. On the RRG: an arrow from each line's head (→ big-money buying, ↑ money inflow; its colour: the line's flow
   quadrant), or each week's dot ringed by that week's money flow. Under the RRG, the money-flow quadrants for the same
   lines and the same frame — Accumulation, Quiet buying, Outflow, Distribution — and their guide: what each means, how it
   reads with the RRG quadrant, and what followed it in the past (every ticker-week pooled, 4 and 13 weeks on, against
   SPY; index.json's stats). Self-contained; in the hub it reads rrg.js's helpers through the `H` object it is given. */
(function (root) {
  'use strict';
  // the flow quadrants in the RRG's order (top-right, bottom-right, bottom-left, top-left) and the RRG fills they reuse
  const FQ = [
    ['acc', 'Accumulation', 'var(--flow-buy)', 'lead', 'big money buying and money flowing in'],
    ['quiet', 'Quiet buying', 'var(--rot-1)', 'imp', 'big money buying while the money flow is out'],
    ['out', 'Outflow', 'var(--flow-sell)', 'lag', 'big money selling and money flowing out'],
    ['dist', 'Distribution', 'var(--rot-sun)', 'weak', 'money flowing in while big money sells'],
  ];
  const MODES = [['arrows', 'Arrows: → big-money buying · ↑ money inflow'], ['rings', 'Each week ringed by its money flow'], ['off', 'Off']];
  const WINS = [['1', '1 week'], ['4', '4 weeks'], ['13', '13 weeks']];
  const GUIDE = [
    'Both measures agree: buying off-exchange, and closes near the day’s highs on volume. With the RRG, a line moving into or through Leading with this behind it has buyers on both sides.',
    'Big money buys off-exchange while the day-to-day flow is out — closes near the lows on volume. Typical of weak stretches being bought; on the RRG, look at Lagging and Improving lines.',
    'Selling off-exchange and money flowing out. Lagging lines with this have not found buyers yet; Leading ones are losing them.',
    'Money flows in on the tape while big money sells off-exchange: strength that large holders are selling into. With the RRG, watch Leading and Weakening lines.',
  ];
  // how a line reads: its RRG quadrant (rrgQuad: Leading, Weakening, Lagging, Improving) with its flow quadrant
  const READ = [
    ['Leading, with money behind it', 'Leading; big money still buying as the tape cools', 'Leading, but money is leaving', 'Leading on inflows while big money sells'],
    ['Losing speed, yet money still coming in', 'Losing speed; big money buying the dip', 'Losing speed and money is leaving', 'Losing speed while big money sells into strength'],
    ['Lagging, but money is coming in', 'Lagging while big money buys quietly', 'Lagging and still being sold', 'Lagging; inflows not backed by big money'],
    ['Improving, with money behind it', 'Improving; big money buying ahead of the tape', 'Improving without money behind it', 'Improving on inflows while big money sells'],
  ];
  const S = { idx: null, t: {} };
  const hub = () => (root.FF_HUB_ROOT || '') + 'data/research/flows/';
  const redraw = () => { if (typeof root.render === 'function') root.render(); };
  function get(m, url) {
    if (typeof fetch !== 'function') { m.err = 'no fetch'; return; }
    m.loading = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json(); })
      .then((d) => { m.data = d; m.loading = null; redraw(); }).catch((e) => { m.err = e.message; m.loading = null; redraw(); });
  }
  function index() { const m = S.idx || (S.idx = {}); if (!m.data && !m.err && !m.loading) get(m, hub() + 'index.json'); return m; }
  function doc(id) { const m = S.t[id] || (S.t[id] = {}); if (!m.data && !m.err && !m.loading) get(m, hub() + 't/' + encodeURIComponent(id) + '.json'); return m; }
  // a line's ticker: ETFs and companies (a dual RRG's company too); baskets, site sectors and industries have none
  const fid = (e) => { const id = String((e && e.id) || '').replace(/\|ix$/, ''); return /^[A-Z][A-Z0-9-]{0,9}$/.test(id) ? id : null; };
  const quad = (x, y) => (x >= 0 ? (y >= 0 ? 0 : 1) : (y < 0 ? 2 : 3));

  // the file's weekly arrays (thousands of dollars; the short shares × 10,000) on the RRG's weekly grid
  function onGrid(d, G) {
    const off = Math.round((Date.parse(d.start + 'T00:00:00Z') - G.t0) / 6048e5), out = {};
    for (const k of ['dv', 'mf', 'ox', 'r', 'b', 'dp', 'pb', 'ps']) {
      const a = d[k] || [], o = (out[k] = new Array(G.n).fill(null));
      for (let i = 0; i < a.length; i++) { const g = off + i; if (g >= 0 && g < G.n) o[g] = a[i]; }
    }
    return out;
  }
  // the reading at week gi over the L weeks to it: every week needs its dollars traded and money flow; the big-money
  // figure needs every week's short share and its own normal too (the first 26 weeks of a ticker have none): x, 2 × the
  // excess short share weighted by each week's off-exchange shares (% of the off-exchange volume); dp its dollars where
  // every week has them
  function reading(A, gi, L) {
    if (gi == null || gi - L + 1 < 0) return null;
    let dv = 0, mf = 0, dp = 0, nd = 0, sx = 0, so = 0, nx = 0;
    for (let j = gi - L + 1; j <= gi; j++) {
      if (A.dv[j] == null || A.mf[j] == null || !(A.dv[j] > 0)) return null;
      dv += A.dv[j]; mf += A.mf[j];
      if (A.r[j] != null && A.b[j] != null && A.ox[j] > 0) { sx += 2 * (A.r[j] - A.b[j]) / 1e4 * A.ox[j]; so += A.ox[j]; nx++; }
      if (A.dp[j] != null) { dp += A.dp[j]; nd++; }
    }
    const big = nx === L && so > 0;
    // the experiment: taker buy and sell on crypto exchanges' perpetuals of the stock, every week of the window traded
    let pb = 0, ps = 0, np = 0;
    for (let j = gi - L + 1; j <= gi; j++) if (A.pb[j] != null && A.ps[j] != null && A.pb[j] + A.ps[j] > 0) { pb += A.pb[j]; ps += A.ps[j]; np++; }
    return { x: big ? 100 * sx / so : null, y: 100 * mf / dv, dp: big && nd === L ? dp * 1e3 : null, mf: mf * 1e3, dv: dv * 1e3, L,
      r: A.r[gi] == null ? null : A.r[gi] / 1e4, b: A.b[gi] == null ? null : A.b[gi] / 1e4,
      cp: np === L ? { buy: pb * 1e3, sell: ps * 1e3, net: (pb - ps) * 1e3, pct: 100 * (pb - ps) / (pb + ps) } : null };
  }
  const qtl = (a, p) => { if (!a.length) return null; const s = a.slice().sort((u, v) => u - v); return s[Math.min(s.length - 1, Math.floor(p * (s.length - 1)))]; };
  // fixed for the whole history, symmetric around 0, so play does not rescale
  function domain(per, k0, k1) {
    const xs = [], ys = [];
    for (const p of per) if (p.R) for (let k = Math.max(0, k0); k <= k1 && k < p.R.length; k++) { const r = p.R[k]; if (!r) continue; ys.push(Math.abs(r.y)); if (r.x != null) xs.push(Math.abs(r.x)); }
    return { x: [-Math.max(0.5, (qtl(xs, 0.97) || 0.5) * 1.15), Math.max(0.5, (qtl(xs, 0.97) || 0.5) * 1.15)],
      y: [-Math.max(2, (qtl(ys, 0.97) || 2) * 1.15), Math.max(2, (qtl(ys, 0.97) || 2) * 1.15)] };
  }
  /* The flow side of the chart: o (rrg.js's view: lines, Q, firstK, lastK, freq, mode), G (rrgGrid(D)), idx (each
     frame's week on the grid), opts {mode, L}. Starts loading what it needs; draws what has arrived. */
  function prep(o, G, idx, opts) {
    const L = Math.max(1, +opts.L || 4), mode = opts.mode || 'arrows';
    index();
    const per = o.lines.map((l) => {
      const id = fid(l.e);
      if (!id) return { l, id: null, none: true };
      const m = doc(id);
      const p = { l, id, m };
      if (m.data) { p.A = onGrid(m.data, G); p.R = idx.map((gi) => reading(p.A, gi, L)); }
      return p;
    });
    const F = { L, mode, per, idx, loading: per.some((p) => p.m && p.m.loading && !p.m.data),
      missing: per.filter((p) => p.none || (p.m && p.m.err)).map((p) => p.l.e.name) };
    F.dom = domain(per, o.firstK || 0, o.lastK != null && o.lastK >= 0 ? o.lastK : o.Q.length - 1);
    F.any = per.some((p) => p.R && p.R.some(Boolean));
    return F;
  }

  // ---------------------------------------------------------------- words and numbers
  const pc = (v, d = 1) => { if (v == null || !Number.isFinite(v)) return '—'; const a = Math.abs(v).toFixed(d); return (+a === 0 ? '' : v > 0 ? '+' : '−') + a + '%'; };
  function usd(v) {
    if (v == null || !Number.isFinite(v)) return '—';
    const a = Math.abs(v), s = v > 0 ? '+' : v < 0 ? '−' : '';
    return s + '$' + (a >= 1e12 ? (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? (a / 1e9).toFixed(2) + 'B' : a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : a.toFixed(0));
  }
  const wk = (L) => (L === 1 ? 'the week' : `${L} weeks`);
  function tipRows(p, r, day) {
    const q = r.x == null ? null : quad(r.x, r.y);
    return [[p.l.e.name + ' · ' + day, q == null ? 'money flow (big-money figure from its 27th week)' : FQ[q][1] + ': ' + FQ[q][4]],
      [r.x == null ? '—' : r.dp == null ? `${pc(r.x)} of off-exchange volume` : `${usd(r.dp)} (${pc(r.x)} of off-exchange volume)`, `Big-money net buying, ${wk(r.L)}`],
      [`${usd(r.mf)} (${pc(r.y)} of turnover)`, `Net money inflow, ${wk(r.L)}`],
      ...(r.r != null && r.b != null ? [[`${(100 * r.r).toFixed(1)}% vs ${(100 * r.b).toFixed(1)}%`, 'Off-exchange short share this week vs its last 52']] : []),
      [usd(r.dv).replace(/^\+/, ''), `Turnover, ${wk(r.L)}`],
      ...(r.cp ? [[`${usd(r.cp.net)} (${pc(r.cp.pct)} of ${usd(r.cp.buy + r.cp.sell).replace(/^\+/, '')})`, 'Crypto perpetuals: taker buy − sell (experiment)']] : [])];
  }

  // ---------------------------------------------------------------- on the RRG: arrows, or each week ringed
  function overlay(o, F, f, sx, sy, H) {
    if (!F || F.mode === 'off') return { under: '', over: '' };
    let under = '', over = '';
    const kz = o.dom ? Math.max(0.55, Math.min(1, Math.abs(sx(o.dom.x[1]) - sx(o.dom.x[0])) / 640)) : 1;   // smaller on a phone
    for (const p of F.per) {
      if (!p.R || (o.pick && o.pick.size && !o.pick.has(p.l.e.id))) continue;
      const c = p.l.calc;
      if (F.mode === 'rings') {
        for (let k = Math.max(0, f - o.tail + 1); k <= f; k++) {
          const r = p.R[k];
          if (!r || c.x[k] == null || c.y[k] == null) continue;
          const m = Math.min(1, Math.abs(r.y) / F.dom.y[1]), hd = k === f;
          under += `<circle cx="${sx(c.x[k]).toFixed(1)}" cy="${sy(c.y[k]).toFixed(1)}" r="${(hd ? 9 : 4) + (hd ? 6 : 4) * m}" style="fill:${r.y >= 0 ? 'var(--flow-buy)' : 'var(--flow-sell)'};opacity:${(0.18 + 0.35 * m).toFixed(2)}"/>`;
          if (hd && r.x != null) over += `<circle cx="${sx(c.x[k]).toFixed(1)}" cy="${sy(c.y[k]).toFixed(1)}" r="9" class="rrgf-ring" style="stroke:${r.x >= 0 ? 'var(--flow-buy)' : 'var(--flow-sell)'}"/>`;
        }
        continue;
      }
      const r = p.R[f];
      if (!r || c.x[f] == null || c.y[f] == null) continue;
      const nx = r.x == null ? 0 : Math.max(-1, Math.min(1, r.x / F.dom.x[1])), ny = Math.max(-1, Math.min(1, r.y / F.dom.y[1]));
      const mag = Math.min(1, Math.hypot(nx, ny)), a = Math.atan2(-ny, nx), len = kz * (16 + 34 * mag);
      const x0 = sx(c.x[f]), y0 = sy(c.y[f]), u = Math.cos(a), v = Math.sin(a);
      const ax = x0 + u * 9, ay = y0 + v * 9, bx = x0 + u * (9 + len), by = y0 + v * (9 + len);
      const col = r.x == null ? 'var(--muted)' : FQ[quad(r.x, r.y)][2];
      const hx = (t) => (bx + 2 * u - 10 * kz * Math.cos(a + t)).toFixed(1), hy = (t) => (by + 2 * v - 10 * kz * Math.sin(a + t)).toFixed(1);
      const seg = `x1="${ax.toFixed(1)}" y1="${ay.toFixed(1)}" x2="${bx.toFixed(1)}" y2="${by.toFixed(1)}"`;
      over += `<g class="mk-hit rrgf-arrow" data-tip="${H.tip(tipRows(p, r, H.day(o.Q[f])))}"><line class="rrgf-halo" ${seg}/><line ${seg} style="stroke:${col}"${r.x == null ? ' stroke-dasharray="4 3"' : ''}/>`
        + `<path class="rrgf-head" d="M${hx(0.6)},${hy(0.6)} L${(bx + 2 * u).toFixed(1)},${(by + 2 * v).toFixed(1)} L${hx(-0.6)},${hy(-0.6)}" style="stroke:${col}"/></g>`;   // an open head: not the RRG's own arrow
    }
    return { under, over };
  }
  function legend(F) {
    if (!F || F.mode === 'off') return '';
    return F.mode === 'rings'
      ? `<span><i class="mk-key" style="background:var(--flow-buy);opacity:.5"></i><i class="mk-key" style="background:var(--flow-sell);opacity:.5"></i>each week ringed by its net money inflow (green in, red out) · the latest dot’s outline: big-money buying (green) or selling (red), ${esc(wk(F.L))}</span>`
      : `<span><b style="font-weight:600">↗</b> money-flow arrow, ${esc(wk(F.L))}: → big-money net buying, ← selling · ↑ net money inflow, ↓ outflow · its colour: the flow quadrant below (dashed: no big-money figure yet)</span>`;
  }

  // ---------------------------------------------------------------- the money-flow quadrants
  function chart(o, F, f, H) {
    const [W, Ht] = H.size(0.52, 340, 540), Lm = 58, R = 18, T = 16, B = 44, xd = F.dom.x, yd = F.dom.y;
    const cx = (v) => Math.max(xd[0], Math.min(xd[1], v)), cy = (v) => Math.max(yd[0], Math.min(yd[1], v));
    const sx = (v) => Lm + (cx(v) - xd[0]) / (xd[1] - xd[0]) * (W - Lm - R), sy = (v) => T + (yd[1] - cy(v)) / (yd[1] - yd[0]) * (Ht - T - B);
    const X0 = sx(0), Y0 = sy(0), day = H.day(o.Q[f]);
    let s = `<svg class="plot mk-plot rrg rrgf" viewBox="0 0 ${W} ${Ht}" role="img" aria-label="Money-flow quadrants for ${esc(day)}: big-money net buying across, net money inflow up; the table below lists every value">`;
    s += `<rect class="rrg-lead" x="${X0}" y="${T}" width="${W - R - X0}" height="${Y0 - T}"/><rect class="rrg-imp" x="${X0}" y="${Y0}" width="${W - R - X0}" height="${Ht - B - Y0}"/>`;
    s += `<rect class="rrg-lag" x="${Lm}" y="${Y0}" width="${X0 - Lm}" height="${Ht - B - Y0}"/><rect class="rrg-weak" x="${Lm}" y="${T}" width="${X0 - Lm}" height="${Y0 - T}"/>`;
    s += `<text class="rot-watermark" x="${W - R - 10}" y="${Ht - B - 14}" text-anchor="end">${esc(day)}</text>`;
    H.ticks(yd[0], yd[1], 6).forEach((v) => { s += `<line class="mk-grid" x1="${Lm}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="axis" x="${Lm - 8}" y="${sy(v) + 4}" text-anchor="end">${esc(pc(v, Math.abs(v) < 1 && v ? 1 : 0))}</text>`; });
    H.ticks(xd[0], xd[1], 7).forEach((v) => { s += `<line class="mk-grid" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${Ht - B}"/><text class="axis" x="${sx(v)}" y="${Ht - B + 16}" text-anchor="middle">${esc(pc(v, Math.abs(v) < 1 && v ? 1 : 0))}</text>`; });
    s += `<line class="mk-axis" x1="${X0}" x2="${X0}" y1="${T}" y2="${Ht - B}"/><line class="mk-axis" x1="${Lm}" x2="${W - R}" y1="${Y0}" y2="${Y0}"/>`;
    s += `<text class="rrg-qt rrg-t-lead" x="${W - R - 8}" y="${T + 16}" text-anchor="end">${FQ[0][1]}</text><text class="rrg-qt rrg-t-imp" x="${W - R - 8}" y="${Ht - B - 10}" text-anchor="end">${FQ[1][1]}</text>`;
    s += `<text class="rrg-qt rrg-t-lag" x="${Lm + 8}" y="${Ht - B - 10}">${FQ[2][1]}</text><text class="rrg-qt rrg-t-weak" x="${Lm + 8}" y="${T + 16}">${FQ[3][1]}</text>`;
    const nar = W < 560;                                  // a phone: the short titles
    s += `<text class="axis" x="${(Lm + W - R) / 2}" y="${Ht - 8}" text-anchor="middle">${nar ? 'Big-money buying → (% off-exchange)' : `Big-money net buying → (% of off-exchange volume, ${esc(wk(F.L))})`}</text>`;
    s += `<text class="axis" transform="translate(13 ${(T + Ht - B) / 2}) rotate(-90)" text-anchor="middle">${nar ? 'Money inflow → (% traded)' : 'Net money inflow → (% of turnover)'}</text>`;
    const boxes = [];
    let marks = '', labels = '';
    for (const p of F.per) {
      if (!p.R || (o.pick && o.pick.size && !o.pick.has(p.l.e.id))) continue;
      const ks = [], tl = Math.min(o.tail, 5);           // a short tail: the readings move a lot from week to week
      for (let k = Math.max(0, f - tl + 1); k <= f; k++) if (p.R[k] && p.R[k].x != null) ks.push(k);
      if (!ks.length) continue;
      const pts = ks.map((k) => [sx(p.R[k].x), sy(p.R[k].y)]);
      if (pts.length > 1) marks += `<path class="rot-line rrg-tail" style="stroke:${p.l.col}" d="${H.curve(pts, true)}"/>`;
      ks.forEach((k, i) => {
        const hd = i === ks.length - 1 && k === f, q = pts[i];
        marks += `<g data-tip="${H.tip(tipRows(p, p.R[k], H.day(o.Q[k])))}" tabindex="${hd ? 0 : -1}" class="mk-hit"><circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="${hd ? 10 : 6}" fill="transparent"/><circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="${hd ? 6 : 2.4}" class="rot-dot" style="fill:${p.l.col};opacity:${hd ? 1 : (0.3 + 0.6 * i / Math.max(1, ks.length - 1)).toFixed(2)}"/></g>`;
      });
      const h = pts[pts.length - 1], kl = ks[ks.length - 1], text = p.l.e.name + (kl === f ? '' : ' ' + H.day(o.Q[kl]));
      const w = text.length * 6.8, right = h[0] + 12 + w < W - R, low = h[1] - 22 < T, ly = low ? h[1] + 18 : h[1] - 9;
      const b = [right ? h[0] + 9 : h[0] - 9 - w, ly - 11, right ? h[0] + 9 + w : h[0] - 9, ly + 3];
      if (!boxes.some((q) => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])) { boxes.push(b); labels += `<text class="mk-label mk-halo" x="${right ? h[0] + 9 : h[0] - 9}" y="${ly}" text-anchor="${right ? 'start' : 'end'}">${esc(text)}</text>`; }
    }
    return s + marks + labels + '</svg>';
  }

  // ---------------------------------------------------------------- the guide and the table
  function statLine(st, h) {
    const a = st && st[String(h)];
    return a && a.n ? `${h} weeks on: beat SPY ${(100 * a.beat).toFixed(0)}% of the time, median ${pc(a.med)}` : '';
  }
  function guide(F) {
    const m = index(), st = m.data && m.data.stats, P = st && st.pools, sp = P && P.stocks, ep = P && P.etfs;
    const n = (x) => (x && x['13'] && x['13'].n ? Number(x['13'].n).toLocaleString('en-US') : '0');
    let h = `<div class="rrgf-cards">`;
    FQ.forEach(([k, name, col, cls, what], q) => {
      const s4 = sp && sp.q[q], e4 = ep && ep.q[q];
      h += `<div class="rrgf-card"><b><i class="mk-key rrg-k-${cls}"></i>${esc(name)}</b><span class="sub" style="margin:2px 0 6px">${esc(what[0].toUpperCase() + what.slice(1))}.</span>`
        + `<p>${esc(GUIDE[q])}</p>`
        + (s4 && s4['4'] && s4['4'].n ? `<p class="sub">Stocks: ${esc(statLine(s4, 4))}; ${esc(statLine(s4, 13))} (${esc(n(s4))} stock-weeks).</p>` : '')
        + (e4 && e4['4'] && e4['4'].n ? `<p class="sub">ETFs: ${esc(statLine(e4, 4))}; ${esc(statLine(e4, 13))} (${esc(n(e4))} ETF-weeks).</p>` : '')
        + `</div>`;
    });
    h += `</div>`;
    if (sp && sp.all) {
      const fx = sp.fifths && sp.fifths['13'], line = (k, lab) => (fx && fx[k] && fx[k].top.n ? `the top fifth by ${lab} beat SPY ${(100 * fx[k].top.beat).toFixed(0)}% of the time 13 weeks on (median ${pc(fx[k].top.med)}), the bottom fifth ${(100 * fx[k].bottom.beat).toFixed(0)}% (median ${pc(fx[k].bottom.med)})` : '');
      h += `<p class="sub">For comparison, every stock-week: ${esc(statLine(sp.all, 4))}; ${esc(statLine(sp.all, 13))}. Ranked within each week, ${esc([line('x', 'big-money buying'), line('y', 'money inflow')].filter(Boolean).join('; '))}. Readings over ${esc(wk(st.L))}, ${esc(st.from || '')} to ${esc(st.to || '')}, ${esc(String(sp.tickers))} stocks and ${esc(String((ep && ep.tickers) || 0))} ETFs that traded $5M a week or more, against SPY with dividends. The weeks overlap, so the counts are not independent tries: history, not a forecast, and not investment advice.</p>`;
    } else if (m.loading) h += `<p class="sub">Loading what followed each quadrant…</p>`;
    return h;
  }
  function table(o, F, f, H) {
    const rows = [];
    for (const p of F.per) {
      const r = p.R && p.R[f], c = p.l.calc;
      if (!r) continue;
      const rq = c.x[f] != null && c.y[f] != null ? H.rrgQuad(c.x[f], c.y[f]) : null, q = r.x == null ? null : quad(r.x, r.y);
      rows.push({ p, r, q, rq });
    }
    rows.sort((a, b) => (b.r.x == null ? -1e9 : b.r.x) - (a.r.x == null ? -1e9 : a.r.x));
    if (!rows.length) return '';
    const cp = rows.some(({ r }) => r.cp);              // the experiment's column, when a line has perpetuals
    return H.table(['Line', 'Money flow', 'With the RRG', `Big-money net buying, ${wk(F.L)}`, `Net money inflow, ${wk(F.L)}`, 'Off-exchange short share: week · last 52', ...(cp ? ['Crypto perpetuals: taker buy − sell (experiment)'] : [])], rows.map(({ p, r, q, rq }) => [
      `<i class="mk-key" style="background:${p.l.col}"></i> <b>${esc(p.l.e.name)}</b>`,
      q == null ? '<span class="muted">—</span>' : `<span class="badge rrg-b-${FQ[q][3]}">${esc(FQ[q][1])}</span>`,
      rq == null ? '—' : `<span class="badge rrg-b-${H.RRG_Q[rq][0]}">${esc(H.RRG_Q[rq][1])}</span>${q == null ? '' : `<br><span class="rrgf-read">${esc(READ[rq][q])}</span>`}`,
      r.x == null ? '—' : r.dp == null ? `<span class="${r.x >= 0 ? 'positive' : 'negative'}">${esc(pc(r.x))}</span><br><span class="muted">of off-exchange volume</span>`
        : `<span class="${r.dp >= 0 ? 'positive' : 'negative'}">${esc(usd(r.dp))}</span><br><span class="muted">${esc(pc(r.x))} of off-exchange volume</span>`,
      `<span class="${r.y >= 0 ? 'positive' : 'negative'}">${esc(usd(r.mf))}</span><br><span class="muted">${esc(pc(r.y))} of turnover</span>`,
      r.r != null && r.b != null ? `${(100 * r.r).toFixed(1)}% · ${(100 * r.b).toFixed(1)}%` : '—',
      ...(cp ? [r.cp ? `<span class="${r.cp.net >= 0 ? 'positive' : 'negative'}">${esc(usd(r.cp.net))}</span><br><span class="muted">${esc(pc(r.cp.pct))} of ${esc(usd(r.cp.buy + r.cp.sell).replace(/^\+/, ''))}</span>` : '<span class="muted">—</span>'] : [])]));
  }
  // what the experiment shows so far (index.json's perps.stats): words built from its numbers
  function experiment() {
    const m = index(), P = m.data && m.data.perps, S = P && P.stats;
    let h = `<p>OKX and Bitget, two crypto exchanges, list perpetual futures on US stocks and ETFs and publish how much of each traded on the buyer’s initiative (a taker lifting the offer) and on the seller’s — the “active buy, active sell” split Chinese stock apps build their money-flow figures from. The column above adds up that split, taker buy − taker sell, over the same weeks; OKX gives about the last 100 days, Bitget 30 days and only for a few contracts, so the history grows a day at a time from August 2026. It is the flow of those exchanges’ own traders — offshore, leveraged, trading around the clock — not the stock market’s: for Nvidia about 1% of the stock’s own dollar volume, far less for most. Binance, the largest of these venues, does not serve US addresses.</p>`;
    if (S && S.n) {
      const rho = (k) => (S[k] && S[k].rho != null ? (S[k].rho > 0 ? '+' : S[k].rho < 0 ? '−' : '') + Math.abs(S[k].rho).toFixed(2) : '—');
      h += `<p>So far — ${esc(String(S.tickers))} tickers, ${esc(S.from)} to ${esc(S.to)}, ${esc(Number(S.n).toLocaleString('en-US'))} ticker-weeks with $5M or more of perpetuals traded — the week’s net taker buying ranks with the stock’s return against SPY that same week at ${rho('rel')} (rank correlation), with its money flow at ${rho('y')} and with its big-money buying at ${rho('x')}; with the next week’s return against SPY at ${rho('next')}${S.ic ? ` (week by week ${S.ic.mean > 0 ? '+' : S.ic.mean < 0 ? '−' : ''}${Math.abs(S.ic.mean).toFixed(2)}, above zero in ${S.ic.positive} of ${S.ic.weeks} weeks)` : ''}; and with its own next week at ${rho('persist')}. It moves with the stock in the same week and keeps its direction for a while; it has not said anything about the next week. Too few weeks yet to rest anything on.</p>`;
    } else if (m.loading) h += `<p class="sub">Loading the experiment’s numbers…</p>`;
    return h;
  }
  // under the RRG: the quadrant chart, its notes, the guide and the table (or why there is nothing to draw)
  function panel(o, F, f, H) {
    if (!F) return '';
    const head = `<h3 style="margin-top:22px">Money flow: big-money net buying × net money inflow</h3>`;
    const sub = `<p class="sub">The same lines and ${o.freq === 'm' ? 'month' : 'week'} as the RRG, read over ${esc(wk(F.L))}. → big-money net buying: FINRA’s off-exchange short volume against the line’s own last 52 weeks (a dealer filling a buy order from its book reports a short sale), as a share of the off-exchange volume. ↑ net money inflow: Chaikin’s money flow, each day’s dollars weighted by where it closed in its range, as a share of the dollars traded. Estimates — the US publishes no large-order figures. ${F.missing.length ? 'No flows for ' + esc(F.missing.join(', ')) + ' (baskets, site sectors and industries have no ticker of their own; a ticker needs daily bars).' : ''}</p>`;
    if (!F.any) return head + sub + (F.loading ? H.empty('Loading the money flows…') : H.empty('No money flows on file for these lines yet: they are built every trading day from FINRA’s files, from August 2018.'));
    return head + sub + `<div id="rrgf-plot">${chart(o, F, f, H)}</div>`
      + `<div class="mk-legend rrg-legend">${FQ.map(([k, name, , cls, what]) => `<span><i class="mk-key rrg-k-${cls}"></i>${esc(name)} <span class="muted">${esc(what)}</span></span>`).join('')}</div>`
      + table(o, F, f, H)
      + `<details open><summary>How to read the money-flow quadrants</summary>${guide(F)}</details>`
      + (F.per.some((p) => p.R && p.R.some((r) => r && r.cp)) ? `<details><summary>Experiment: crypto exchanges’ stock perpetuals</summary>${experiment()}</details>` : '')
      + `<details><summary>How the money flows are estimated</summary><p>Big-money net buying: FINRA publishes, every trading day, how many shares of each stock traded off the exchanges (the trade reporting facilities, where dark pools and block trades report) and how many of those were short sales. A dealer that fills a client’s buy order from its own book reports a short sale, so the short share rises when buyers dominate off-exchange — the idea behind the “dark index” (DIX). Each line is read against itself: the week’s short share minus its average over the 52 weeks before (26 at least), doubled — the share of the off-exchange volume bought beyond the usual, averaged over the weeks chosen by their off-exchange shares; times the off-exchange dollars, the dollars. FINRA counts shares as traded, the daily bars are split-adjusted: splits are found where the two volumes step against each other and taken out of the dollars, and a symbol FINRA used for another security earlier (Meta’s before June 2022) is read only from its change. Net money inflow: Chaikin’s money flow, each day’s dollar volume × ((close − low) − (high − close)) ÷ (high − low), added up over the weeks chosen and divided by the dollars traded in them. Neither is a count of real orders: short sales also come from market making and hedging, and a close near the day’s high is not proof of buying. FINRA’s consolidated files begin on August 1, 2018, so the big-money figure starts in early 2019.</p></details>`;
  }

  const api = { FQ, MODES, WINS, READ, S, fid, quad, onGrid, reading, domain, prep, overlay, legend, chart, guide, table, panel, experiment, usd, pc };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  root.RRGFlow = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
