/* Supply chains and trading themes as money flows (#chains, #chain-<id>): data/chains/*.json from pipeline/chains.py.
 *
 * Each chain is drawn as a multi-column Sankey laid out here (the same display list as sankey.js, so it is drawn with
 * Sankey.toSVG and saved with Sankey.exportScene). A band's shade says how much of it the filings state outright:
 * dark = named in a filing or reported as such, light = estimated (an assumed share, balanced across buyers).
 * Views: the money flow; the profit pool (gross profit kept by each company); cash in and out (where the companies'
 * cash came from and went). Spend chains can add a column for how the buyers paid (pro rata to their cash sources)
 * and the suppliers' own suppliers. The market's money (13F managers, insiders, officials — the Disclosures hub's
 * combined flows) can be laid over the companies, and recent 8-Ks of the chain's companies are listed.
 */
(function (global) {
  'use strict';
  const S = global.Sankey;
  const FONT = "'IBM Plex Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif";
  const BG = '#fcfcfb', INK = '#1d1d1b', INK2 = '#3d3c39', INK3 = '#6b6a66', GREY = '#9a9893';
  const KIND = { spend: 'Spending flow', customers: 'Who pays', geo: 'By country', basket: 'Theme' };
  const VIEWS = [['flow', 'Money flow'], ['forecast', 'Next 4 quarters (forecast)'], ['profit', 'Profit pool'], ['cash', 'Cash in & out']];
  const hasModel = (d) => !!(d.model && d.model.suppliers && d.model.suppliers.length);
  const viewsFor = (d) => VIEWS.filter(([k]) => k !== 'forecast' || hasModel(d));
  const SCEN_L = { base: 'Base case', down: 'Buyers spend 20% less', up: 'Buyers spend 20% more' };
  const HUB = 'disclosures/data/';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hubCache = new Map();
  function hub(path) {                               // the Disclosures hub's data (absent in a local preview: null)
    if (!hubCache.has(path)) hubCache.set(path, fetch(HUB + path).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    return hubCache.get(path);
  }
  function usd(v, d) {
    if (v == null || isNaN(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 0.95e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9) return `${s}$${(a / 1e9).toFixed(a >= 100e9 ? 0 : 1)}B`;
    if (a >= 0.95e6) return `${s}$${(a / 1e6).toFixed(d == null ? (a >= 100e6 ? 0 : 1) : d)}M`;
    return `${s}$${(a / 1e3).toFixed(0)}K`;
  }
  const pct = (x, d) => (x == null || isNaN(x) ? '—' : `${(100 * x).toFixed(d == null ? 0 : d)}%`);
  const sgn = (x, d) => (x == null || isNaN(x) ? '—' : `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(100 * x).toFixed(d == null ? 0 : d)}%`);
  const fdate = (s) => {
    if (!s) return '—';
    const d = new Date(s.length <= 10 ? s + 'T00:00:00Z' : s);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  };
  function rgba(hex, a) {
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || '');
    if (!m) return `rgba(154,152,147,${a})`;
    return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a.toFixed(3)})`;
  }
  let mctx = null;
  function textW(s, size, weight) {
    if (!mctx) mctx = document.createElement('canvas').getContext('2d');
    mctx.font = `${weight || 400} ${size}px ${FONT}`;
    return mctx.measureText(s).width;
  }
  function fit(s, size, weight, maxW) {               // shorten a label to the room there is
    if (textW(s, size, weight) <= maxW) return s;
    let t = s;
    while (t.length > 3 && textW(t + '…', size, weight) > maxW) t = t.slice(0, -1);
    return t + '…';
  }

  // ---------------------------------------------------------------- the layout
  function bandPath(x0, y0, x1, y1, th) {
    const mx = (x0 + x1) / 2;
    return `M${x0.toFixed(2)} ${y0.toFixed(2)}C${mx.toFixed(2)} ${y0.toFixed(2)} ${mx.toFixed(2)} ${y1.toFixed(2)} ${x1.toFixed(2)} ${y1.toFixed(2)}` +
      `L${x1.toFixed(2)} ${(y1 + th).toFixed(2)}C${mx.toFixed(2)} ${(y1 + th).toFixed(2)} ${mx.toFixed(2)} ${(y0 + th).toFixed(2)} ${x0.toFixed(2)} ${(y0 + th).toFixed(2)}Z`;
  }

  /* view: {cols, nodes [{id, col, label, v, color, est, t, sub}], links [{s, t, v, k}]}; o: {title, subtitle, footer,
     overlay: {ticker: {net, label}}, layerOrder}. Returns a scene for Sankey.toSVG / exportScene plus hit data. */
  function layout(view, o) {
    const W = 1240, NW = 12, TOP = (o.back && o.back.length) ? 96 + 14 + 18 * Math.min(o.back.length, 8) : 96, BOTTOM = 92;
    const cols = view.cols.length;
    const byCol = Array.from({ length: cols }, () => []);
    view.nodes.forEach((n) => { if (n.col < cols) byCol[n.col].push(n); });
    const order = o.layerOrder || [];
    const lrank = (n) => { const i = order.indexOf(n.layer); return i < 0 ? 99 : i; };
    byCol.forEach((list, c) => list.sort((a, b) => {
      const ea = a.est ? 1 : 0, eb = b.est ? 1 : 0;
      if (ea !== eb) return ea - eb;                                   // estimates (not traced, others) at the bottom
      if (a.layer && b.layer && a.layer !== b.layer && (c > 0)) return lrank(a) - lrank(b);
      return b.v - a.v;
    }));
    // the left column's labels sit left of their bars: make room for the longest one-line label ("Investments sold  $452M")
    const LEFT = Math.round(Math.min(260, Math.max(150, 24 + Math.max(0, ...byCol[0].map((n) =>
      Math.max(textW(`${n.t || n.label}  ${usd(n.v)}`, 11.5, 600), textW(n.t || n.label, 13, 600)))))));
    const RIGHT = 200;
    const xs = byCol.map((_, c) => LEFT + c * ((W - LEFT - RIGHT - NW) / Math.max(cols - 1, 1)));
    const MINSLOT = 15, VALUE_PX = 560;
    const gapOf = (n) => (n > 24 ? 3 : n > 12 ? 5 : 9);
    const tot = byCol.map((l) => l.reduce((a, n) => a + n.v, 0));
    // the largest column's money fills about VALUE_PX; small nodes still get a slot their label fits in, so a long
    // column (forty suppliers) makes the chart taller rather than every band thinner
    let k = VALUE_PX / Math.max(...tot, 1);
    const need = () => Math.max(...byCol.map((l) => l.reduce((a, n) => a + Math.max(n.v * k, MINSLOT), 0) + Math.max(l.length - 1, 0) * gapOf(l.length)));
    for (let it = 0; it < 12 && need() > VALUE_PX * 1.9; it++) k *= 0.85;
    const H = Math.round(TOP + BOTTOM + Math.max(need(), 420));
    const avail = () => H - TOP - BOTTOM;
    const pos = new Map();
    byCol.forEach((list, c) => {
      const g = gapOf(list.length);
      const used = list.reduce((a, n) => a + Math.max(n.v * k, MINSLOT), 0) + (list.length - 1) * g;
      let y = TOP + Math.max(0, (avail() - used) / 2);
      list.forEach((n) => {
        const h = Math.max(n.v * k, 1.5), slot = Math.max(h, MINSLOT);
        pos.set(n.id, { x: xs[c], y, h, slot, n, outY: y, inY: y });
        y += slot + g;
      });
    });
    const shapes = [];
    // bands, stacked in the order of the nodes at the other end
    const links = view.links.filter((l) => pos.has(l.s) && pos.has(l.t));
    const out = new Map(), inn = new Map();
    links.forEach((l) => { (out.get(l.s) || out.set(l.s, []).get(l.s)).push(l); (inn.get(l.t) || inn.set(l.t, []).get(l.t)).push(l); });
    out.forEach((ls) => ls.sort((a, b) => pos.get(a.t).y - pos.get(b.t).y));
    inn.forEach((ls) => ls.sort((a, b) => pos.get(a.s).y - pos.get(b.s).y));
    const y0 = new Map(), y1 = new Map();
    out.forEach((ls, id) => { let y = pos.get(id).y; ls.forEach((l) => { y0.set(l, y); y += l.v * k; }); });
    inn.forEach((ls, id) => { let y = pos.get(id).y; ls.forEach((l) => { y1.set(l, y); y += l.v * k; }); });
    const colorOf = (n) => n.color || (n.est ? GREY : '#7a7974');
    links.forEach((l) => {
      const a = pos.get(l.s), b = pos.get(l.t);
      const th = Math.max(l.v * k, 0.6);
      const base = l.c || (b.n.est ? GREY : a.n.est ? GREY : (b.n.color || a.n.color || '#7a7974'));
      const alpha = 0.15 + 0.37 * Math.min(Math.max(l.k || 0, 0), 1);
      shapes.push({ band: true, t: 'path', d: bandPath(a.x + NW, y0.get(l), b.x, y1.get(l), th), fill: rgba(base, alpha), ls: l.s, lt: l.t });
    });
    // money flowing back: a company's stake in another one of the chain (its 13F), drawn as an arc over the chart
    let arcs = 0;
    (o.back || []).forEach((b) => {
      const a = pos.get(b.from), t = pos.get(b.to);
      if (!a || !t || arcs >= 8) return;
      // drawn with right angles out of the holder's right side, along a lane above the columns, into the held
      // company's right side (thin rectangles, so the line prints and saves like the rest of the chart)
      const C = '#8a4fbf', w = 2, off = 7 + arcs * 4, lane = TOP - 30 - arcs * 18;
      const xs0 = a.x + NW, ys0 = a.y + 3 + arcs * 3, xt0 = t.x + NW, yt0 = t.y + 3 + arcs * 3;
      const xa = xs0 + off, xb = xt0 + off;
      const seg = (x, y, ww, hh) => shapes.push({ t: 'rect', x: Math.min(x, x + ww), y: Math.min(y, y + hh), w: Math.max(Math.abs(ww), w), h: Math.max(Math.abs(hh), w), fill: C });
      seg(xs0, ys0, xa - xs0, w);
      seg(xa, lane, w, ys0 - lane + w);
      seg(Math.min(xa, xb), lane, Math.abs(xb - xa) + w, w);
      seg(xb, lane, w, yt0 - lane);
      seg(xt0 + 5, yt0, xb - xt0 - 5, w);
      shapes.push({ t: 'path', d: `M${xt0} ${yt0 + w / 2}L${xt0 + 7} ${yt0 - 3}L${xt0 + 7} ${yt0 + w + 3}Z`, fill: C });
      shapes.push({ t: 'text', x: (xa + xb) / 2, y: lane - 4, text: `${b.from} holds ${usd(b.v)} of ${b.to} (13F)`, size: 11, weight: 600, fill: '#6b3d99', anchor: 'middle' });
      arcs++;
    });
    // node bars and labels
    const grand = tot.map((x) => x || 1);
    const seenT = new Map();
    view.nodes.forEach((n) => { if (n.t) { const k = `${n.col}|${n.t}`; seenT.set(k, (seenT.get(k) || 0) + 1); } });
    const dupT = new Set([...seenT].filter(([, k]) => k > 1).map(([k]) => k));
    pos.forEach((p, id) => {
      const n = p.n, c = n.col, left = c === 0;
      const bar = { t: 'rect', x: p.x, y: p.y, w: NW, h: p.h, fill: colorOf(n), group: id };
      if (n.est) bar.hatch = GREY;
      shapes.push(bar);
      shapes.push({ t: 'rect', x: p.x - 4, y: p.y - 2, w: NW + 8, h: Math.max(p.slot, 12) + 4, fill: 'rgba(0,0,0,0)', group: id, hit: true, ui: true });
      const name = n.t && dupT.has(`${n.col}|${n.t}`) && n.label && n.label !== n.t ? `${n.t} ${n.label.split(' ').slice(-1)[0]}` : (n.t || n.label);
      const share = n.v / grand[c];
      const val = `${usd(n.v)}${share < 0.995 ? ` · ${(100 * share).toFixed(share < 0.1 ? 1 : 0)}%` : ''}`;
      const ov = o.overlay && n.t ? o.overlay[n.t] : null;
      const room = left ? LEFT - 18 : (c === cols - 1 ? RIGHT - 16 : Math.min(220, (xs[c + 1] || W) - xs[c] - NW - 26));
      const tx = left ? p.x - 7 : p.x + NW + 7, anchor = left ? 'end' : 'start';
      const mid = p.y + Math.max(p.h, 12) / 2;
      const two = p.slot >= 30 || p.h >= 30;
      if (two) {
        shapes.push({ t: 'text', x: tx, y: mid - 2, text: fit(name, 13, 600, room), size: 13, weight: 600, fill: INK, anchor, group: id });
        shapes.push({ t: 'text', x: tx, y: mid + 13, text: fit(val + (n.t && n.label && n.label !== n.t && n.col !== 0 ? ` · ${n.label}` : ''), 11.5, 400, room),
          size: 11.5, weight: 400, fill: INK3, anchor, group: id });
      } else {
        shapes.push({ t: 'text', x: tx, y: mid + 4, text: fit(`${name}  ${usd(n.v)}`, 11.5, 600, room), size: 11.5, weight: 600, fill: INK2, anchor, group: id });
      }
      if (ov && ov.net) {
        const w0 = Math.min(textW(two ? name : `${name}  ${usd(n.v)}`, two ? 13 : 11.5, 600), room);
        const chip = `${ov.net > 0 ? '▲' : '▼'} ${usd(Math.abs(ov.net))}`;
        shapes.push({ t: 'text', x: left ? tx - w0 - 6 : tx + w0 + 6, y: two ? mid - 2 : mid + 4, text: chip, size: 11, weight: 600,
          fill: ov.net > 0 ? '#17734a' : '#b8432f', anchor, group: id });
      }
    });
    // column heads, title, footer
    byCol.forEach((list, c) => {
      if (!list.length) return;
      shapes.push({ t: 'text', x: c === 0 ? xs[c] + NW : xs[c], y: TOP - 14, text: (view.cols[c].name || '').toUpperCase(), size: 10.5, weight: 600,
        fill: INK3, anchor: c === 0 ? 'end' : 'start', spacing: 0.8 });
    });
    shapes.push({ t: 'text', x: 24, y: 36, text: o.title || '', size: 21, weight: 600, fill: INK, anchor: 'start' });
    if (o.subtitle) shapes.push({ t: 'text', x: 24, y: 60, text: fit(o.subtitle, 13.5, 400, W - 48), size: 13.5, weight: 400, fill: INK3, anchor: 'start' });
    let fy = H - BOTTOM + 34;
    (o.footer || []).forEach((line) => {
      shapes.push({ t: 'text', x: 24, y: fy, text: fit(line, 11, 400, W - 210), size: 11, weight: 400, fill: INK3, anchor: 'start' });
      fy += 15;
    });
    shapes.push({ t: 'text', x: W - 24, y: H - 18, text: 'filing-flows.com', size: 12, weight: 600, fill: '#17734a', anchor: 'end' });
    return { W, H, bg: BG, shapes, pos };
  }

  // ---------------------------------------------------------------- the page
  const ST = { view: 'flow', fund: false, tier2: true, ovl: '', sort: 'attr', outlook: false, back: false, scen: 'base', shock: -20, fsup: null };

  function prefsLoad(ctx) {
    const p = ctx.prefs.get('chains', {}) || {};
    Object.assign(ST, { fund: !!p.fund, tier2: p.tier2 !== false, ovl: p.ovl || '', back: !!p.back });
  }
  function prefsSave(ctx) { ctx.prefs.set('chains', { fund: ST.fund, tier2: ST.tier2, ovl: ST.ovl, back: ST.back }); }

  async function index(app, ctx) {
    const here = ctx.live();
    ctx.setNav('chains');
    const ix = await ctx.getJSON('chains/index.json');
    if (!here()) return;
    const themes = {};
    (ix.chains || []).forEach((c) => (themes[c.theme || 'Other'] = themes[c.theme || 'Other'] || []).push(c));
    const card = (c) => `<a class="card chain-card" href="#chain-${esc(c.id)}">
      <div class="eyebrow">${esc(c.theme || '')}</div>
      <div class="t"><span>${esc(c.name)}</span></div>
      <div class="n muted">${esc(KIND[c.kind] || c.kind)}</div>
      <div class="big">${usd(c.kind === 'spend' ? c.spend : c.total)}</div>
      <div class="n">${c.kind === 'spend' ? 'spent in the last twelve months' : 'revenue in this theme, last twelve months'} · ${c.companies} companies</div>
      <div class="chain-tops">${(c.top || []).map((x) => `<span class="mono">${esc(x.t)}</span> ${usd(x.v)}`).join(' · ')}</div></a>`;
    const concepts = [];
    (ix.chains || []).forEach((c) => (c.layers || []).forEach((L) => { if (L.tickers && L.tickers.length) concepts.push({ c, L }); }));
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Supply chains &amp; trading themes</div>
      <h1>Where the money flows, industry by industry</h1>
      <p class="muted">Buyers’ spending traced to the listed suppliers it reaches, the customers and countries companies’ revenue comes from,
      and the hot themes grouped layer by layer — every figure read from SEC filings, trailing twelve months, in US dollars. The shade of a band
      says how much of it the filings state outright; the rest is an estimate, and each page says how it was made.</p></div>
      <section class="section"><div class="cards chain-cards">${Object.values(themes).flat().map(card).join('')}</div></section>
      <section class="section"><div class="section-head"><h2>Hot concepts</h2><span class="muted">Every layer of every chain as a basket of stocks · open them in the
        <a href="disclosures/#rotation/rrg~themes">rotation graph</a> to see which theme, or which part of a chain, the market is rotating into</span></div>
        <div class="tbl-wrap"><table><thead><tr><th>Concept</th><th>Chain</th><th>Companies</th></tr></thead><tbody>
        ${concepts.map(({ c, L }) => `<tr><td><span class="chain-dot" style="background:${esc(L.color)}"></span>${esc(L.name)}</td>
          <td><a href="#chain-${esc(c.id)}">${esc(c.name)}</a> · <a class="small" href="disclosures/#rotation/rrg~chain:${esc(c.id)}">rotation ↗</a></td>
          <td>${L.tickers.map((x) => `<a class="mono" href="#t-${esc(x)}">${esc(x)}</a>`).join(' ')}</td></tr>`).join('')}
        </tbody></table></div></section>
      <p class="muted small">${esc(ix.about || '')} Updated ${fdate((ix.generated || '').slice(0, 10))}.</p>`;
  }

  /* The buyers' own outlook: capital expenditures as guided in their latest earnings release (midpoint of a range),
     where they gave one for a year after the twelve months shown; everything downstream scaled in proportion through
     the balanced matrix. Buyers without an outlook keep their last twelve months. */
  function guided(d) {
    const out = {};
    (d.buyers || []).forEach((b) => {
      const r = b.guide && (b.guide.rows || []).find((x) => x.lo && x.year && +x.year >= +String(d.asof || '').slice(0, 4));
      if (r && b.capex > 0) out[b.t] = { f: ((r.lo + r.hi) / 2) / b.capex, mid: (r.lo + r.hi) / 2, year: r.year, text: r.text, url: b.guide.url };
    });
    return out;
  }
  /* Scale a money-flow view: each buyer's links by fb(buyer), each supplier's by fs(supplier); layers and the rest
     follow from the sums. */
  function scaleView(d, v, fb, fs, sub) {
    const buyers = new Set((d.buyers || []).map((b) => b.t));
    const sups = new Set((d.companies || []).filter((c) => c.role !== 'tier2').map((c) => c.id));
    const links = v.links.map((l) => {
      let f = 1;
      if (buyers.has(l.s)) f = fb(l.s);
      else if (buyers.has(l.t) && String(l.s).startsWith('F:')) f = fb(l.t);
      else if (String(l.s).startsWith('L:') && sups.has(l.t)) f = fs(l.t);
      else if (sups.has(l.s)) f = fs(l.s);
      return Object.assign({}, l, { v: l.v * f });
    });
    const inflow = {}, outflow = {};
    links.forEach((l) => { outflow[l.s] = (outflow[l.s] || 0) + l.v; inflow[l.t] = (inflow[l.t] || 0) + l.v; });
    // "not traced" keeps what the buyers spend beyond what the suppliers book; a layer is the sum of its suppliers
    const nodes = v.nodes.map((n) => Object.assign({}, n, { v: Math.max(inflow[n.id] || 0, outflow[n.id] || 0) || n.v * (buyers.has(n.id) ? fb(n.id) : 1),
      sub: sub ? sub(n) || n.sub : n.sub }));
    const lay = {};
    links.filter((l) => String(l.s).startsWith('L:')).forEach((l) => (lay[l.s] = (lay[l.s] || 0) + l.v));
    const into = {};
    links.filter((l) => String(l.t).startsWith('L:')).forEach((l) => (into[l.t] = (into[l.t] || 0) + l.v));
    links.filter((l) => String(l.t).startsWith('L:')).forEach((l) => { if (into[l.t] > 0 && lay[l.t] != null) l.v *= lay[l.t] / into[l.t]; });
    const spent = {};
    links.filter((l) => buyers.has(l.s) && l.t !== '_untraced').forEach((l) => (spent[l.s] = (spent[l.s] || 0) + l.v));
    links.filter((l) => buyers.has(l.s) && l.t === '_untraced').forEach((l) => {
      const n = v.nodes.find((x) => x.id === l.s);
      const total = (n ? n.v : 0) * fb(l.s);
      l.v = Math.max(total - (spent[l.s] || 0), 0);
    });
    const io = {}, oo = {};
    links.forEach((l) => { oo[l.s] = (oo[l.s] || 0) + l.v; io[l.t] = (io[l.t] || 0) + l.v; });
    nodes.forEach((n) => { if (io[n.id] || oo[n.id]) n.v = Math.max(io[n.id] || 0, oo[n.id] || 0); });
    return { cols: v.cols, nodes, links: links.filter((l) => l.v > 0) };
  }
  function scaleByOutlook(d, v) {
    const g = guided(d);
    if (!Object.keys(g).length) return v;
    const fb = (b) => (g[b] ? g[b].f : 1);
    const sup = {}, tot = {};
    (d.matrix || []).forEach((m) => { sup[m.s] = (sup[m.s] || 0) + m.v * fb(m.b); tot[m.s] = (tot[m.s] || 0) + m.v; });
    return scaleView(d, v, fb, (s) => (tot[s] ? sup[s] / tot[s] : 1), (n) => (g[n.id] ? `outlook ${g[n.id].year}` : null));
  }
  function scaleByForecast(d, v) {
    const F = ((d.model || {}).factors || {})[ST.scen] || { b: {}, s: {} };
    const out = scaleView(d, v, (b) => (F.b[b] != null ? F.b[b] : 1), (s) => (F.s[s] != null ? F.s[s] : 1),
      (n) => (F.b[n.id] != null ? `next 4 quarters ${F.b[n.id] >= 1 ? '+' : '−'}${Math.abs(100 * (F.b[n.id] - 1)).toFixed(0)}%` : null));
    out.links.forEach((l) => { l.k = 0; l.why = `forecast (${SCEN_L[ST.scen].toLowerCase()})${l.why ? ' · ' + l.why : ''}`; });   // nothing here is reported yet
    return out;
  }
  function viewOf(d) {
    const fc = ST.view === 'forecast' && hasModel(d);
    const v = fc ? d.views.flow : (d.views[ST.view] || d.views.flow);
    if ((ST.view !== 'flow' && !fc) || d.kind !== 'spend') return v;
    let nodes = v.nodes.slice(), links = v.links.slice(), cols = v.cols.slice();
    if (!ST.tier2) {
      const t2 = new Set(nodes.filter((n) => n.col === 3).map((n) => n.id));
      nodes = nodes.filter((n) => !t2.has(n.id));
      links = links.filter((l) => !t2.has(l.t));
      cols = cols.slice(0, 3);
    }
    if (ST.fund && d.funding && d.funding.length) {
      cols = [{ id: 'funding', name: 'Paid for with' }].concat(cols);
      nodes = nodes.map((n) => Object.assign({}, n, { col: n.col + 1 }));
      const src = {};
      d.funding.forEach((f) => {
        const id = 'F:' + f.src;
        if (!src[id]) src[id] = { id, col: 0, label: f.label, v: 0, color: f.src === 'lease' ? '#5b7fa6' : f.src === 'unknown' ? GREY : '#4d6b57', est: f.src === 'unknown' };
        src[id].v += f.v;
        links.push({ s: id, t: f.b, v: f.v, k: f.src === 'unknown' ? 0 : 0.5, why: f.src === 'lease' ? 'assets taken on under finance leases' : 'pro rata to the buyer’s cash sources' });
      });
      nodes = Object.values(src).concat(nodes);
    }
    if (fc) return scaleByForecast(d, { cols, nodes, links });
    return ST.outlook ? scaleByOutlook(d, { cols, nodes, links }) : { cols, nodes, links };
  }

  function subtitleOf(d) {
    const c = d.coverage;
    const per = `Trailing twelve months to ${fdate(d.asof)}${d.oldest && d.oldest !== d.asof ? ` (latest filings; some end ${fdate(d.oldest)})` : ''}`;
    if (ST.view === 'profit') return `${per} · gross profit on the revenue attributed to this chain`;
    if (ST.view === 'cash') return `${per} · where the companies’ cash came from and went (cash-flow statements)`;
    if (ST.view === 'forecast' && hasModel(d)) {
      const M = d.model, gd = Object.keys(M.guided || {});
      return `Forecast, next four quarters after ${M.last_x} · ${SCEN_L[ST.scen]} · buyers’ capex ${gd.length ? `as guided by ${gd.join(', ')}, ` : ''}else their damped trend · suppliers by the fitted model`;
    }
    if (d.kind === 'spend' && c && ST.outlook && ST.view === 'flow') {
      const g = guided(d), names = Object.keys(g);
      if (names.length) return `Outlook: ${names.map((t) => `${t} ${usd(g[t].mid)} (${g[t].year})`).join(', ')} as guided in their latest earnings releases; other buyers at their last twelve months; suppliers scaled in proportion`;
    }
    if (d.kind === 'spend' && c) return `${per} · ${usd(c.spend)} spent · ${usd(c.traced)} traced to ${c.suppliers} listed suppliers (${pct(c.traced / c.spend)}) · ${usd(c.untraced)} not traced`;
    return per;
  }

  async function page(app, id, ctx) {
    const here = ctx.live();
    ctx.setNav('chains');
    prefsLoad(ctx);
    const d = await ctx.getJSON(`chains/${id}.json`);
    if (!here()) return;
    const order = (d.layers || []).map((L) => L.id);
    app.innerHTML = `<div class="page-head"><div class="crumbs"><a href="#chains">Chains</a><span>›</span><span>${esc(d.theme || '')}</span></div>
      <h1>${esc(d.name)}</h1>
      <p class="intro">${esc(d.about || '')}</p>
      <div class="meta"><span>${esc(KIND[d.kind] || '')}</span><span>Trailing twelve months to ${fdate(d.asof)}</span><span>${(d.companies || []).length} companies</span>
        <a href="disclosures/#rotation/rrg~chain:${esc(d.id)}">Layers in the rotation graph ↗</a>
        ${d.missing && d.missing.length ? `<span title="not on the site yet, or no filing read yet">Not on file yet: ${d.missing.map(esc).join(', ')}</span>` : ''}</div></div>
      <div class="toolbar chain-tools">
        <div class="seg" role="group" aria-label="View">${viewsFor(d).map(([k, l]) => `<button type="button" data-cv="${k}" class="${ST.view === k ? 'on' : ''}">${l}</button>`).join('')}</div>
        ${hasModel(d) ? `<label class="dec-toggle" id="cscenw" ${ST.view === 'forecast' ? '' : 'hidden'}>Case <select id="cscen">${Object.entries(SCEN_L).map(([k, l]) => `<option value="${k}" ${ST.scen === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>` : ''}
        ${d.kind === 'spend' ? `<label class="dec-toggle"><input type="checkbox" id="cfund" ${ST.fund ? 'checked' : ''}> How the buyers paid</label>
          <label class="dec-toggle"><input type="checkbox" id="ctier" ${ST.tier2 ? 'checked' : ''}> Suppliers’ suppliers</label>
          ${Object.keys(guided(d)).length ? `<label class="dec-toggle" title="Capital expenditures as guided in the buyers' latest earnings releases"><input type="checkbox" id="cout" ${ST.outlook ? 'checked' : ''}> Outlook year (${Object.keys(guided(d)).length} of ${(d.buyers || []).length} buyers guided)</label>` : ''}
          ${(d.stakes || []).length ? `<label class="dec-toggle"><input type="checkbox" id="cback" ${ST.back ? 'checked' : ''}> Stakes flowing back</label>` : ''}` : ''}
        <label class="dec-toggle">Market money <select id="covl"><option value="">off</option></select></label>
        <span class="chain-legend"><i class="sw dark"></i> stated in filings <i class="sw light"></i> estimated <i class="sw hatch"></i> not traced</span>
      </div>
      <div class="chain-chart" id="cchart"></div>
      <div class="export chain-export"><span>Save</span><button class="pill" data-cx="png">PNG</button><button class="pill" data-cx="jpg">JPG</button><button class="pill" data-cx="pdf">PDF</button></div>
      <div class="chain-tip" id="ctip" hidden></div>
      <section class="section" id="cmodel"></section>
      <section class="section" id="cnet" hidden></section>
      <section class="section" id="cbasket" hidden></section>
      <section class="section" id="creturn"></section>
      <section class="section" id="cpost"></section>
      <section class="section" id="ctables"></section>
      <section class="section" id="cmarket"></section>
      <section class="section" id="cevents"></section>
      <details class="section method-note"><summary>How this chain is built</summary>${methodText(d)}</details>`;
    let overlay = null, scene = null;
    const draw = () => {
      const v = viewOf(d);
      scene = layout(v, {
        title: `${d.name} — ${(viewsFor(d).find((x) => x[0] === ST.view) || VIEWS[0])[1].toLowerCase()}`, subtitle: subtitleOf(d), layerOrder: order,
        overlay: ST.view === 'flow' || ST.view === 'profit' ? overlay : null,
        back: ST.view === 'flow' && ST.back ? (d.stakes || []).slice(0, 8) : null,
        footer: [ST.view === 'forecast' ? 'Forecast, not reported figures: the buyers’ capex from their guidance where given, else a fading trend; each supplier by its model fitted on SEC filings (see the forecast model below).'
          : `Source: SEC EDGAR filings (10-K, 10-Q, 20-F, 6-K), read by fixed rules. Light bands are estimates: ${d.kind === 'spend' ? 'assumed shares balanced across buyers' : 'assumed shares'}; dark bands are stated in the filings.`,
          'Figures are read automatically and can contain errors; check the filings before relying on them. Not investment advice.'],
      });
      const host = document.getElementById('cchart');
      host.innerHTML = S.toSVG(scene, `${d.name}: ${(viewsFor(d).find((x) => x[0] === ST.view) || VIEWS[0])[1]}`);
      bindChart(host, v, d);
    };
    const tip = document.getElementById('ctip');
    function bindChart(host, v, dd) {
      const svg = host.querySelector('svg');
      if (!svg) return;
      const nodes = new Map(v.nodes.map((n) => [n.id, n]));
      const show = (html, ev) => {
        tip.innerHTML = html;
        tip.hidden = false;
        const r = host.getBoundingClientRect();
        tip.style.left = `${host.offsetLeft + Math.min(ev.clientX - r.left + 14, r.width - 300)}px`;
        tip.style.top = `${ev.clientY - r.top + host.offsetTop + 14}px`;
      };
      svg.addEventListener('mousemove', (ev) => {
        const band = ev.target.closest && ev.target.closest('.band');
        const g = ev.target.closest && ev.target.closest('[data-node]');
        host.classList.toggle('hov', !!(band || g));
        svg.querySelectorAll('.band.on').forEach((p) => p.classList.remove('on'));
        if (band) {
          band.classList.add('on');
          const l = v.links.find((x) => x.s === band.dataset.s && x.t === band.dataset.t);
          if (!l) return;
          const a = nodes.get(l.s), b = nodes.get(l.t);
          show(`<b>${esc(a ? a.t || a.label : l.s)} → ${esc(b ? b.t || b.label : l.t)}</b><br>${usd(l.v)}` +
            `<br><span class="muted">${l.k >= 0.995 ? 'stated in the filings' : l.k > 0.005 ? `${pct(l.k)} stated in the filings, the rest estimated` : 'estimated'}</span>` +
            (l.why ? `<br><span class="muted">${esc(l.why)}</span>` : ''), ev);
        } else if (g) {
          const n = nodes.get(g.dataset.node);
          if (!n) return;
          svg.querySelectorAll('.band').forEach((p) => { if (p.dataset.s === n.id || p.dataset.t === n.id) p.classList.add('on'); });
          const row = (dd.companies || []).find((c) => c.id === n.id || (n.t && c.t === n.t && c.layer === n.layer));
          show(`<b>${esc(n.t || n.label)}</b>${n.sub ? ` <span class="muted">${esc(n.sub)}</span>` : n.t && n.label !== n.t ? ` <span class="muted">${esc(n.label)}</span>` : ''}<br>${usd(n.v)}` +
            (row ? `<br><span class="muted">${esc(row.line)}${row.share != null && row.share < 0.999 ? ` · ${pct(row.share)} of it to this chain` : ''}${row.yoy != null ? ` · ${sgn(row.yoy)} Y/Y` : ''}</span>` : '') +
            (n.cik ? '<br><span class="muted">Click for the company’s page</span>' : ''), ev);
        } else tip.hidden = true;
      });
      svg.addEventListener('mouseleave', () => { tip.hidden = true; host.classList.remove('hov'); });
      svg.addEventListener('click', (ev) => {
        const g = ev.target.closest && ev.target.closest('[data-node]');
        const n = g && nodes.get(g.dataset.node);
        if (n && n.cik) location.hash = `c-${n.cik}`;
      });
    }
    app.querySelectorAll('[data-cv]').forEach((b) => b.addEventListener('click', () => {
      ST.view = b.dataset.cv;
      app.querySelectorAll('[data-cv]').forEach((x) => x.classList.toggle('on', x === b));
      const sw = document.getElementById('cscenw');
      if (sw) sw.hidden = ST.view !== 'forecast';
      draw();
    }));
    const fund = document.getElementById('cfund'), tier = document.getElementById('ctier');
    if (fund) fund.addEventListener('change', () => { ST.fund = fund.checked; prefsSave(ctx); draw(); });
    if (tier) tier.addEventListener('change', () => { ST.tier2 = tier.checked; prefsSave(ctx); draw(); });
    const scen = document.getElementById('cscen');
    if (scen) scen.addEventListener('change', () => { ST.scen = scen.value; draw(); });
    const outl = document.getElementById('cout'), back = document.getElementById('cback');
    if (outl) outl.addEventListener('change', () => { ST.outlook = outl.checked; draw(); });
    if (back) back.addEventListener('change', () => { ST.back = back.checked; prefsSave(ctx); draw(); });
    app.querySelectorAll('[data-cx]').forEach((b) => b.addEventListener('click', async () => {
      if (!scene) return;
      const blob = await S.exportScene(scene, b.dataset.cx, { scale: 2 });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `filing-flows-${d.id}-${ST.view}.${b.dataset.cx}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }));
    await (ctx.fontsReady ? ctx.fontsReady() : Promise.resolve());
    if (!here()) return;
    draw();
    if (hasModel(d)) { document.getElementById('cmodel').innerHTML = modelSection(d); bindModel(d); }
    if (window.FFModel) window.FFModel.concept(document.getElementById('cbasket'), d.id);
    if (window.FFNetwork) window.FFNetwork.concept(document.getElementById('cnet'), d.id);   // web/network.js
    if (d.returns && d.returns.buyers && d.returns.buyers.length) document.getElementById('creturn').innerHTML = returnsSection(d);
    else if (d.model && d.model.error) document.getElementById('cmodel').innerHTML = `<p class="muted small">Forecast model: not yet — ${esc(d.model.error)}; the scan collects the buyers’ history over its next runs.</p>`;
    document.getElementById('ctables').innerHTML = tables(d);
    bindSort(d);
    document.getElementById('cpost').innerHTML = postsBox(d);
    bindPosts(app);
    // the market's money over the companies (Disclosures hub: combined 13F / insider / official flows)
    const sel = document.getElementById('covl');
    hub('smart/combined/index.json').then((ix) => {
      if (!ix || !here()) { sel.closest('label').hidden = true; return; }
      sel.innerHTML = '<option value="">off</option>' + (ix.periods || []).map((p) => `<option value="${esc(p.key)}">${esc(p.label)}</option>`).join('');
      sel.value = (ix.periods || []).some((p) => p.key === ST.ovl) ? ST.ovl : '';
      const apply = async () => {
        ST.ovl = sel.value;
        prefsSave(ctx);
        if (!ST.ovl) { overlay = null; draw(); document.getElementById('cmarket').innerHTML = ''; return; }
        const pd = await hub(`smart/combined/${ST.ovl}.json`);
        if (!pd || !here()) return;
        const F = pd.fields || [], G = (pd.groups || ix.groups || ['f13', 'etf', 'ins', 'gov']);
        overlay = {};
        (pd.rows || []).forEach((r) => {
          const o = {};
          F.forEach((f, i) => (o[f] = r[i]));
          o.net = G.reduce((a, g) => a + (o[g + '_usd'] || 0), 0);
          overlay[String(o.ticker).toUpperCase()] = o;
        });
        draw();
        document.getElementById('cmarket').innerHTML = marketTable(d, overlay, ix, G);
      };
      sel.addEventListener('change', apply);
      if (ST.ovl) apply();
    });
    hub('market/events8k.json').then((ev) => {
      if (!ev || !here()) return;
      const tick = new Set((d.companies || []).map((c) => c.t).concat((d.buyers || []).map((b) => b.t)));
      const rows = (ev.rows || []).filter((r) => tick.has(String(r.ticker || '').toUpperCase())).slice(0, 25);
      if (!rows.length) return;
      document.getElementById('cevents').innerHTML = `<div class="section-head"><h2>Recent 8-Ks in this chain</h2><span class="muted">Deals, guidance and other events the companies filed in the last ${esc(ev.days || '')} days</span></div>
        <div class="tbl-wrap"><table><thead><tr><th>Filed</th><th>Company</th><th>What</th><th>In their words</th></tr></thead><tbody>${rows.map((r) => `<tr>
          <td>${fdate(r.filed)}</td><td class="mono"><a href="#t-${esc(r.ticker)}">${esc(r.ticker)}</a></td><td>${esc(r.label || r.code || '')}</td>
          <td class="small">${esc((r.guidance_quote || r.quote || '').slice(0, 260))} <a href="${esc(r.url)}" target="_blank" rel="noopener">filing ↗</a></td></tr>`).join('')}</tbody></table></div>`;
    });
  }

  function marketTable(d, ov, ix, G) {
    const per = (ix.periods || []).find((p) => p.key === ST.ovl) || {};
    const L = (d.layers || []).map((l) => {
      const ts = (d.companies || []).filter((c) => c.layer === l.id).map((c) => c.t);
      const rows = ts.map((t) => ov[t]).filter(Boolean);
      const sum = (g) => rows.reduce((a, r) => a + (r[g + '_usd'] || 0), 0);
      return { l, ts, net: rows.reduce((a, r) => a + r.net, 0), by: G.map((g) => [g, sum(g)]) };
    });
    const names = ix.labels || {};
    return `<div class="section-head"><h2>The market’s money in this chain</h2><span class="muted">${esc(per.label || '')} · net dollars bought (+) or sold (−), by layer</span></div>
      <div class="tbl-wrap"><table><thead><tr><th>Layer</th>${G.map((g) => `<th class="num">${esc(names[g] || g)}</th>`).join('')}<th class="num">Net</th><th>Companies</th></tr></thead><tbody>
      ${L.map((x) => `<tr><td><span class="chain-dot" style="background:${esc(x.l.color)}"></span>${esc(x.l.name)}</td>${x.by.map(([, v]) => `<td class="num ${v > 0 ? 'pos' : v < 0 ? 'neg' : ''}">${v ? usd(v) : '—'}</td>`).join('')}
        <td class="num ${x.net > 0 ? 'pos' : x.net < 0 ? 'neg' : ''}"><b>${x.net ? usd(x.net) : '—'}</b></td>
        <td class="small">${x.ts.map((t) => { const r = ov[t]; return `<span class="mono">${esc(t)}</span>${r && r.net ? ` <span class="${r.net > 0 ? 'pos' : 'neg'}">${usd(r.net)}</span>` : ''}`; }).join(' · ')}</td></tr>`).join('')}
      </tbody></table></div><p class="muted small">From the <a href="disclosures/#allflows">Disclosures hub</a>: 13F managers, active ETFs, insiders (Form 4) and officials’ trades in the period.</p>`;
  }

  function tables(d) {
    let h = '';
    const L = Object.fromEntries((d.layers || []).map((l) => [l.id, l]));
    const dot = (id) => (L[id] ? `<span class="chain-dot" style="background:${esc(L[id].color)}"></span>` : '');
    if (d.kind === 'spend') {
      const w = (d.wallet || []).slice().sort((a, b) => (b.cents || 0) - (a.cents || 0));
      h += `<div class="section-head"><h2>Where each $1 goes</h2><span class="muted">Cents of every dollar these buyers spent, by supplier · a year earlier where the filings allow</span></div>
        <div class="wallet">${w.map((x) => `<div class="wrow"><span class="mono">${esc(x.t)}</span><span class="wbar"><i style="width:${Math.min(100, (x.cents || 0) * 3)}%;background:${esc((L[x.layer] || {}).color || '#7a7974')}"></i></span>
          <b>${x.cents != null ? x.cents.toFixed(1) + '¢' : '—'}</b><span class="muted small">${x.cents_py != null ? `a year earlier ${x.cents_py.toFixed(1)}¢` : ''}</span></div>`).join('')}</div>`;
      h += `<div class="section-head"><h2>Buyers</h2></div><div class="tbl-wrap"><table><thead><tr><th>Buyer</th><th class="num">Capex, 12 months</th><th class="num">Y/Y</th>
        <th class="num">Finance leases</th><th class="num">Op. cash flow</th><th class="num">Capex ÷ cash flow</th><th>Outlook in the latest earnings release</th></tr></thead><tbody>
        ${(d.buyers || []).map((b) => `<tr><td><span class="mono">${esc(b.t)}</span> <a href="#c-${b.cik}">${esc(b.name)}</a></td><td class="num">${usd(b.capex)}</td>
          <td class="num">${b.capex_py ? sgn(b.capex / b.capex_py - 1) : '—'}</td><td class="num">${b.lease ? usd(b.lease) : '—'}</td><td class="num">${usd(b.ocf)}</td>
          <td class="num">${b.ocf > 0 ? pct(b.capex / b.ocf) : '—'}</td>
          <td class="small">${b.guide && b.guide.rows && b.guide.rows.length ? `${esc(b.guide.rows[0].text)} <a href="${esc(b.guide.url)}" target="_blank" rel="noopener">${fdate(b.guide.filed)} ↗</a>` : '<span class="muted">none stated in the release</span>'}</td></tr>`).join('')}
        </tbody></table></div>`;
    }
    if (d.customers) {
      const tot = d.customers.reduce((a, c) => a + c.v, 0);
      h += `<div class="section-head"><h2>Who pays</h2></div><div class="wallet">${d.customers.filter((c) => c.v > 0).map((c) => `<div class="wrow"><span>${esc(c.name)}</span>
        <span class="wbar"><i style="width:${tot ? (100 * c.v / tot).toFixed(1) : 0}%"></i></span><b>${usd(c.v)}</b></div>`).join('')}</div>`;
    }
    if (d.regions) {
      const tot = d.regions.reduce((a, c) => a + c.v, 0);
      h += `<div class="section-head"><h2>By country or region</h2><span class="muted">As each company reports its revenue by geography</span></div>
        <div class="wallet">${d.regions.filter((c) => c.v > 0).sort((a, b) => b.v - a.v).map((c) => `<div class="wrow"><span>${esc(c.name)}</span>
        <span class="wbar"><i style="width:${tot ? (100 * c.v / tot).toFixed(1) : 0}%"></i></span><b>${usd(c.v)}</b><span class="muted small">${tot ? pct(c.v / tot) : ''}</span></div>`).join('')}</div>`;
    }
    const rows = (d.companies || []).filter((c) => c.role !== 'tier2');
    const t2 = (d.companies || []).filter((c) => c.role === 'tier2');
    const cust = (c) => (c.customers || []).map((x) => `${esc(x.label)}${x.pct != null ? ' ' + pct(x.pct) : ''}`).join(', ');
    h += `<div class="section-head"><h2>Companies</h2><span class="muted">The revenue line used, the share taken for this chain, and what the filings say about customers</span></div>
      <div class="tbl-wrap"><table class="chain-co"><thead><tr><th data-cs="t">Company</th><th>Layer</th><th>Line used</th><th class="num" data-cs="base">Line, 12 months</th>
      <th class="num" data-cs="share">Share</th><th class="num" data-cs="attr">${d.kind === 'spend' ? 'From these buyers' : 'In this theme'}</th><th class="num" data-cs="yoy">Y/Y</th>
      <th class="num" data-cs="gm">Gross margin</th><th class="num" data-cs="rpo">Backlog (RPO)</th><th>Major customers in the filing</th></tr></thead>
      <tbody id="ccorows">${coRows(rows, dot, cust)}</tbody></table></div>`;
    if (t2.length) {
      h += `<div class="section-head"><h3>Suppliers’ suppliers</h3></div><div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Line used</th><th class="num">Line, 12 months</th>
        <th class="num">Drawn</th><th>How</th></tr></thead><tbody>${t2.map((c) => `<tr><td><span class="mono">${esc(c.t)}</span> <a href="#c-${c.cik}">${esc(c.name)}</a></td>
        <td class="small">${esc(c.line)}</td><td class="num">${usd(c.base)}</td><td class="num">${usd(c.attr)}</td><td class="small muted">${esc(c.note || '')}</td></tr>`).join('')}</tbody></table></div>`;
    }
    if (d.matrix && d.matrix.length) {
      h += `<details><summary>Who buys from whom (the balanced matrix, largest cells)</summary><div class="tbl-wrap"><table><thead><tr><th>Buyer</th><th>Supplier</th><th class="num">Amount</th><th>How</th></tr></thead><tbody>
        ${d.matrix.filter((m) => m.b !== '_other').slice(0, 60).map((m) => `<tr><td class="mono">${esc(m.b)}</td><td class="mono">${esc(m.s)}</td><td class="num">${usd(m.v)}</td>
        <td class="small">${m.named ? '<b>named in the supplier’s filing</b>' : '<span class="muted">estimated (balanced)</span>'}</td></tr>`).join('')}</tbody></table></div></details>`;
    }
    if (d.stakes && d.stakes.length) {
      h += `<div class="section-head"><h3>Money flowing back</h3><span class="muted">Shares of this chain’s companies held by companies in it (their latest 13F)</span></div>
        <div class="tbl-wrap"><table><thead><tr><th>Holder</th><th>Holds</th><th class="num">Value</th><th>Quarter</th></tr></thead><tbody>${d.stakes.map((s) => `<tr>
        <td class="mono">${esc(s.from)}</td><td class="mono">${esc(s.to)}</td><td class="num">${usd(s.v)}</td><td>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${fdate(s.period)} ↗</a>` : fdate(s.period)}</td></tr>`).join('')}</tbody></table></div>`;
    }
    return h;
  }

  function coRows(rows, dot, cust) {
    const k = ST.sort;
    const val = (c) => (k === 't' ? c.t : k === 'gm' ? (c.gm == null ? -1 : c.gm) : c[k] == null ? -Infinity : c[k]);
    rows = rows.slice().sort((a, b) => (k === 't' ? String(val(a)).localeCompare(val(b)) : val(b) - val(a)));
    return rows.map((c) => `<tr><td><span class="mono">${esc(c.t)}</span> <a href="#c-${c.cik}">${esc(c.name)}</a>${c.cur ? ` <span class="muted small">(${esc(c.cur)}, converted)</span>` : ''}</td>
      <td>${dot(c.layer)}</td><td class="small">${esc(c.line)}${/not found/.test(c.how) ? ' <span class="tag" title="the configured revenue line was not found in the latest filings">line not found</span>' : ''}</td>
      <td class="num">${usd(c.base)}</td><td class="num">${c.share != null ? pct(c.share) : '—'}</td><td class="num"><b>${usd(c.attr)}</b></td>
      <td class="num">${c.yoy != null ? sgn(c.yoy) : '—'}</td><td class="num">${c.gm != null ? pct(c.gm) : '—'}</td>
      <td class="num">${c.rpo ? `${usd(c.rpo)}${c.rev ? ` <span class="muted small">${(c.rpo / c.rev).toFixed(1)}×</span>` : ''}` : '—'}</td>
      <td class="small">${cust(c) || '<span class="muted">none named</span>'}</td></tr>`).join('');
  }

  function bindSort(d) {
    const L = Object.fromEntries((d.layers || []).map((l) => [l.id, l]));
    const dot = (id) => (L[id] ? `<span class="chain-dot" style="background:${esc(L[id].color)}" title="${esc(L[id].name)}"></span>${esc(L[id].name)}` : '');
    const cust = (c) => (c.customers || []).map((x) => `${esc(x.label)}${x.pct != null ? ' ' + pct(x.pct) : ''}`).join(', ');
    const body = document.getElementById('ccorows');
    if (!body) return;
    const rows = (d.companies || []).filter((c) => c.role !== 'tier2');
    body.innerHTML = coRows(rows, dot, cust);
    document.querySelectorAll('.chain-co [data-cs]').forEach((th) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => { ST.sort = th.dataset.cs; body.innerHTML = coRows(rows, dot, cust); });
    });
  }

  // ---------------------------------------------------------------- the forecast model (pipeline/chainmodel.py)
  const qn = (l) => { const m = /^(\d{4})Q(\d)$/.exec(l || ''); return m ? +m[1] * 4 + +m[2] - 1 : null; };
  const ql = (k) => `${Math.floor(k / 4)}Q${(k % 4) + 1}`;
  const cents = (x) => (x == null ? '—' : `${(100 * x).toFixed(1)}¢`);

  function lineChart(series, o) {
    // series: [{pts: [[label, v]], color, dash, w, band: [[label, lo, hi]], name}] · values in $B
    const W = 760, H = 250, L = 56, R = 14, T = 14, B = 34;
    const labs = [...new Set(series.flatMap((s) => (s.pts || []).map((p) => p[0]).concat((s.band || []).map((p) => p[0]))))]
      .sort((a, b) => qn(a) - qn(b));
    if (labs.length < 2) return '';
    const k0 = qn(labs[0]), k1 = qn(labs[labs.length - 1]);
    const vals = series.flatMap((s) => (s.pts || []).map((p) => p[1]).concat((s.band || []).flatMap((p) => [p[1], p[2]]))).filter((v) => v != null && isFinite(v));
    let lo = Math.min(0, ...vals), hi = Math.max(...vals) * 1.06 || 1;
    const x = (l) => L + (qn(l) - k0) / Math.max(k1 - k0, 1) * (W - L - R), y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const step = Math.pow(10, Math.floor(Math.log10(hi / 4 || 1))), tick = [1, 2, 2.5, 5, 10].map((m) => m * step).find((t2) => hi / t2 <= 5) || step;
    let g = '';
    for (let v = 0; v <= hi; v += tick) g += `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="#e5e3dd"/><text x="${L - 6}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#6b6a66">${usd(v * 1e9)}</text>`;
    const every = Math.ceil(labs.length / 10);
    labs.forEach((l, i) => { if ((i % every === 0 && labs.length - 1 - i >= every / 2) || i === labs.length - 1) g += `<text x="${x(l).toFixed(1)}" y="${H - 12}" text-anchor="middle" font-size="11" fill="#6b6a66">${esc(l)}</text>`; });
    if (o && o.split) g += `<line x1="${x(o.split).toFixed(1)}" x2="${x(o.split).toFixed(1)}" y1="${T}" y2="${H - B}" stroke="#9a9893" stroke-dasharray="3 3"/><text x="${(x(o.split) + 4).toFixed(1)}" y="${T + 10}" font-size="10.5" fill="#6b6a66">forecast →</text>`;
    series.forEach((s) => {
      if (s.band && s.band.length) {
        const up = s.band.map((p) => `${x(p[0]).toFixed(1)},${y(p[2]).toFixed(1)}`), dn = s.band.slice().reverse().map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`);
        g += `<polygon points="${up.concat(dn).join(' ')}" fill="${s.color}" fill-opacity=".14"/>`;
      }
      const pts = (s.pts || []).filter((p) => p[1] != null);
      if (pts.length) g += `<polyline points="${pts.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')}" fill="none" stroke="${s.color}" stroke-width="${s.w || 2}"${s.dash ? ` stroke-dasharray="${s.dash}"` : ''}/>`;
    });
    const leg = series.filter((s) => s.name).map((s) => `<span><i style="background:${s.color}${s.dash ? ';opacity:.6' : ''}"></i>${esc(s.name)}</span>`).join('');
    return `<svg class="mchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc((o && o.aria) || 'chart')}">${g}</svg><div class="mleg">${leg}</div>`;
  }

  function xMap(M) {
    const X = {};
    (M.x || []).forEach(([l, v]) => (X[qn(l)] = v));
    return X;
  }
  function pathMap(M, sc) {
    const X = xMap(M);
    ((M.x_path || {})[sc] || []).forEach(([l, v]) => (X[qn(l)] = v));
    return X;
  }
  function impact(M, r, shock) {
    // ΔR over the supplier's next four quarters when the buyers' future capex moves by `shock` (a fraction)
    const lags = M.lags || [-1, 0, 1, 2], last = qn(M.last_x);
    const b = r.b || (M.profiles[r.profile] || [0.25, 0.25, 0.25, 0.25]).map((w) => w * r.share0);
    const X = pathMap(M, 'base');
    const lastY = qn((r.hist[r.hist.length - 1] || [])[0]);
    let d0 = 0;
    for (let k = lastY + 1; k <= lastY + 4; k++) lags.forEach((l, i) => { const kk = k - l; if (kk > last && X[kk] != null) d0 += b[i] * X[kk] * shock; });
    return d0;
  }

  function modelSection(d) {
    const M = d.model, bt = M.backtest;
    const X = (M.x || []).slice(-16);
    const cap = lineChart([
      { pts: X, color: '#1d1d1b', name: 'Buyers’ capex, reported' },
      { pts: [X[X.length - 1]].concat(M.x_path.base.slice(0, 6)), color: '#2f6db3', name: 'Base path' },
      { pts: [X[X.length - 1]].concat(M.x_path.down.slice(0, 6)), color: '#b8432f', dash: '5 4', name: '−20%' },
      { pts: [X[X.length - 1]].concat(M.x_path.up.slice(0, 6)), color: '#17734a', dash: '5 4', name: '+20%' },
    ], { split: M.last_x, aria: 'Buyers’ combined capital expenditures by quarter, with the forecast paths' });
    const rows = M.suppliers.slice().sort((a, b) => (b.chain_now || 0) - (a.chain_now || 0));
    const gd = Object.entries(M.guided || {});
    let h = `<div class="section-head"><h2>Forecast model</h2><span class="muted">How each supplier’s revenue follows the buyers’ capex — fitted on the filings, tested out of sample</span></div>
      <p class="muted">Each supplier’s quarterly revenue line = the rest of its business (a level and a trend) + its share of the buyers’ combined capex a quarter ahead,
      in the same quarter, and one and two quarters later. The share starts from the balanced chain above (the prior) and the reported quarters update it
      (Bayesian regression). The buyers’ capex ahead: ${gd.length ? gd.map(([t, g]) => `${esc(t)} ${usd(g.mid * 1e9)} guided for ${g.year}`).join(', ') + '; the others their' : 'their'} damped trend.</p>`;
    if (bt) {
      h += `<p><b>Out of sample</b>, one quarter ahead, ${bt.suppliers} suppliers: the model missed by ${pct(bt.mape, 1)} on average given the buyers’ actual capex,
        ${pct(bt.mape_uncond, 1)} with their capex projected as well; repeating the last quarter missed by ${pct(bt.mape_rw, 1)} and growing it at its last-year rate by
        ${pct(bt.mape_growth, 1)}. The full model beat “last quarter” for ${bt.beats_rw} and “last-year growth” for ${bt.beats_growth} of the ${bt.suppliers} suppliers;
        its 80% intervals held ${pct(bt.cover80)} of the time.</p>`;
    }
    h += `<div class="mbox">${cap}</div>`;
    h += `<div class="section-head"><h3>What if the buyers spend more or less?</h3></div>
      <div class="toolbar"><label class="dec-toggle">Buyers’ capex over the next four quarters vs the base path
        <input type="range" id="mshock" min="-40" max="40" step="5" value="${ST.shock}"> <b id="mshockv">${ST.shock > 0 ? '+' : ''}${ST.shock}%</b></label></div>
      <div class="tbl-wrap"><table><thead><tr><th>Supplier</th><th>Line forecast</th><th class="num">Next 4 quarters, base</th><th class="num">Change</th>
        <th class="num">% of the line</th><th class="num">80% range, base</th></tr></thead><tbody id="mimpact"></tbody></table></div>`;
    h += `<div class="section-head"><h3>The fitted links</h3><span class="muted">Revenue per dollar of the buyers’ capex: assumed (prior) and after the filings (posterior), 80% intervals</span></div>
      <div class="tbl-wrap"><table class="small"><thead><tr><th>Supplier</th><th>Line</th><th class="num">Quarters</th><th class="num">Prior ¢/$</th><th class="num">Fitted ¢/$</th>
        <th class="num">Data weight</th><th class="num">Timing</th><th class="num">R²</th><th class="num">Error: model / full / last q / growth</th><th class="num">80% held</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td class="mono">${esc(r.t)}</td><td>${esc(r.y_kind)}</td><td class="num">${r.first ? `${r.n} (${esc(r.first)}–${esc(r.last)})` : esc(r.n)}</td>
        <td class="num">${cents(r.share0)}${r.share0_lo != null ? ` <span class="muted">${cents(Math.max(r.share0_lo, 0))}–${cents(r.share0_hi)}</span>` : ''}</td>
        <td class="num">${r.share != null ? `<b>${cents(r.share)}</b> <span class="muted">${cents(Math.max(r.share_lo, 0))}–${cents(r.share_hi)}</span>` : `<span class="muted">${esc(r.note || '')}</span>`}</td>
        <td class="num">${r.dataw != null ? pct(r.dataw) : '—'}</td>
        <td class="num">${r.lag == null ? '—' : Math.abs(r.lag) < 0.25 ? 'with capex' : r.lag < 0 ? `${(-r.lag).toFixed(1)} q ahead` : `${r.lag.toFixed(1)} q after`}</td>
        <td class="num">${r.r2 != null ? r.r2.toFixed(2) : '—'}</td>
        <td class="num">${r.bt ? `${pct(r.bt.mape, 1)} / ${pct(r.bt.mape_uncond, 1)} / ${pct(r.bt.mape_rw, 1)} / ${pct(r.bt.mape_growth, 1)}` : '—'}</td>
        <td class="num">${r.bt ? pct(r.bt.cover80) : '—'}</td></tr>`).join('')}</tbody></table></div>`;
    const withFc = rows.filter((r) => r.fc && r.fc.base && r.fc.base.length);
    if (withFc.length) {
      const pick = withFc.find((r) => r.id === ST.fsup) || withFc[0];
      ST.fsup = pick.id;
      h += `<div class="section-head"><h3>One supplier, quarter by quarter</h3></div>
        <div class="toolbar"><label class="dec-toggle">Supplier <select id="mfsup">${withFc.map((r) => `<option value="${esc(r.id)}" ${r.id === pick.id ? 'selected' : ''}>${esc(r.t)} · ${esc(r.y_kind)}</option>`).join('')}</select></label></div>
        <div class="mbox" id="mfchart">${supChart(pick)}</div>`;
    }
    h += `<details><summary>How the model works, and what it cannot know</summary>
      <p>y<sub>t</sub> = a + c·t + Σ b<sub>ℓ</sub>·X<sub>t−ℓ</sub> + e<sub>t</sub>, ℓ = −1 (the supplier books revenue a quarter before the buyers pay — chips shipped to server makers),
      0, 1 and 2 (billed as work is done, delivered later). X = the buyers’ combined cash capital expenditures by calendar quarter (a fiscal quarter counts in the
      calendar quarter holding most of its days). Σ b is the supplier’s revenue per dollar of capex. The prior centres Σ b on the balanced chain above and spreads it
      over the lags by layer (chips and gear early, power and construction later); the level and the trend are almost free. The posterior is the conjugate
      Gaussian one with the noise variance re-estimated; “data weight” is how much the filings narrowed the share’s uncertainty (0%: the prior alone).</p>
      <p>Tested out of sample with a rolling origin: fitted on the quarters up to one, it predicts the next, once with the buyers’ actual capex (how good the supply
      link is) and once with their capex projected from their own trend (the whole forecast). Ahead, the buyers’ capex follows their guidance where their latest
      earnings release gave a number for the year (spread over the quarters left after what they already spent), else a trend that fades. The cases move that path
      by ±20%. Intervals are 80% predictive ranges from the posterior: they hold the parameters’ and the residuals’ uncertainty, not a change in the buyers’ plans —
      that is what the cases are for.</p>
      <p>What it cannot know: units and prices (no bill of materials is in the filings), orders not yet in revenue, customers outside the chain that move with it
      (enterprise, sovereign and Chinese buyers end up in the level and trend), and a change in a supplier’s share that has not shown in its revenue yet. With a dozen
      quarters per supplier, the shares are estimates with wide ranges; the error table says how much to trust each one.</p></details>`;
    return h;
  }

  function supChart(r) {
    const hist = r.hist.slice(-14), fit = (r.fit || []).filter((p) => qn(p[0]) >= qn(hist[0][0]));
    const last = hist[hist.length - 1];
    const join = (a) => [[last[0], last[1]]].concat(a.map((p) => [p[0], p[1]]));
    return lineChart([
      { pts: hist, color: '#1d1d1b', name: `${r.t} reported (${r.y_kind})` },
      { pts: fit.map((p) => [p[0], p[2]]), color: '#9a9893', dash: '3 3', name: 'Model fit' },
      { pts: join(r.fc.base), color: '#2f6db3', band: r.fc.base.map((p) => [p[0], p[2], p[3]]), name: 'Forecast, base (80% range)' },
      { pts: join(r.fc.down), color: '#b8432f', dash: '5 4', name: 'Buyers −20%' },
      { pts: join(r.fc.up), color: '#17734a', dash: '5 4', name: 'Buyers +20%' },
    ], { split: last[0], aria: `${r.t}: reported, fitted and forecast quarterly revenue` });
  }

  function bindModel(d) {
    const M = d.model;
    const body = document.getElementById('mimpact'), sl = document.getElementById('mshock'), lab = document.getElementById('mshockv');
    const paint = () => {
      const sh = ST.shock / 100;
      const rows = M.suppliers.map((r) => {
        const base = r.fc && r.fc.base ? r.fc.base.reduce((a, p) => a + p[1], 0) : null;
        const lo = r.fc && r.fc.base ? r.fc.base.reduce((a, p) => a + p[2], 0) : null, hi = r.fc && r.fc.base ? r.fc.base.reduce((a, p) => a + p[3], 0) : null;
        return { r, base, lo, hi, dv: impact(M, r, sh) };
      }).sort((a, b) => Math.abs(b.dv) - Math.abs(a.dv));
      body.innerHTML = rows.map(({ r, base, lo, hi, dv }) => `<tr><td class="mono">${esc(r.t)}</td><td class="small">${esc(r.y_kind)}</td>
        <td class="num">${base != null ? usd(base * 1e9) : '<span class="muted">prior only</span>'}</td>
        <td class="num ${dv > 0 ? 'pos' : dv < 0 ? 'neg' : ''}">${dv ? (dv > 0 ? '+' : '−') + usd(Math.abs(dv) * 1e9) : '—'}</td>
        <td class="num">${base ? sgn(dv / base, 1) : '—'}</td><td class="num muted">${lo != null ? `${usd(lo * 1e9)}–${usd(hi * 1e9)}` : '—'}</td></tr>`).join('');
      lab.textContent = `${ST.shock > 0 ? '+' : ''}${ST.shock}%`;
    };
    if (sl) { sl.addEventListener('input', () => { ST.shock = +sl.value; paint(); }); paint(); }
    const sel = document.getElementById('mfsup');
    if (sel) sel.addEventListener('change', () => {
      ST.fsup = sel.value;
      const r = M.suppliers.find((x) => x.id === sel.value);
      if (r) document.getElementById('mfchart').innerHTML = supChart(r);
    });
  }

  // ---------------------------------------------------------------- what the spending costs and earns (capexreturn.py)
  function returnsSection(d) {
    const R = d.returns, C = R.combined, rows = R.buyers.slice().sort((a, b) => b.capex_ttm - a.capex_ttm);
    const B = (v) => (v == null ? '—' : usd(v * 1e9));
    const hist = C.dep_hist, last = hist[hist.length - 1];
    const lead = (sc) => [last].concat(C.dep_path[sc].slice(0, 8));
    const chart = lineChart([
      { pts: hist, color: '#1d1d1b', name: 'Depreciation, reported (combined)' },
      { pts: lead('base'), color: '#2f6db3', name: 'Ahead: base capex path' },
      { pts: lead('down'), color: '#b8432f', dash: '5 4', name: 'Capex −20%' },
      { pts: lead('up'), color: '#17734a', dash: '5 4', name: 'Capex +20%' },
    ], { split: last[0], aria: 'The buyers’ combined depreciation, reported and projected' });
    const ratio = C.need_covered ? C.d_oi / C.need_covered : null;
    let h = `<div class="section-head"><h2>What the spending costs, and what it has earned</h2><span class="muted">Depreciation still to come, the return so far, free cash flow — each buyer from its own filings</span></div>
      <p>These ${rows.length} buyers charged <b>${B(C.dep_ttm)}</b> of depreciation in the last twelve months against <b>${B(C.capex_ttm)}</b> of capex.
      Over the next four quarters the charge rises to <b>${B(C.dep_next4.base)}</b> — almost all of it set by what is already spent: spending 20% less moves it only to ${B(C.dep_next4.down)}.
      The last two years’ capex (${B(C.capex_8q)}) needs about <b>${B(C.need)}</b> a year of extra operating profit to pay its depreciation and earn ${pct(R.hurdle)} before tax;
      ${ratio != null ? `the buyers added <b>${B(C.d_oi)}</b> of operating profit over those two years — ${pct(ratio)} of what their part of the spending needs.` : ''}</p>
      <div class="mbox">${chart}</div>
      <div class="tbl-wrap"><table class="small"><thead><tr><th>Buyer</th><th class="num">Capex, 12 months</th><th class="num">Depreciation, 12 months</th>
        <th class="num">Effective life</th><th class="num">Depreciation, next 4 q (−20% / +20%)</th><th class="num">Next years (base)</th>
        <th class="num">Profit needed a year</th><th class="num">Operating profit added, 2 years</th><th class="num">Covered</th><th class="num">Return on PP&amp;E added</th>
        <th class="num">Free cash flow, next 4 q (−20% / +20%)</th><th class="num">−20% capex: EPS, 2 years</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td class="mono">${esc(r.t)}</td><td class="num">${B(r.capex_ttm)}</td><td class="num">${B(r.dep_ttm)}${r.da_used ? ' <span class="muted" title="depreciation and amortization: depreciation alone is not tagged">D&amp;A</span>' : ''}</td>
        <td class="num" title="fitted on the reported depreciation; typical miss ${B(r.rms)} a quarter">${r.life_y} y</td>
        <td class="num"><b>${B(r.dep_next4.base)}</b> <span class="muted">${B(r.dep_next4.down)} / ${B(r.dep_next4.up)}</span></td>
        <td class="num">${Object.entries(r.dep_years.base || {}).slice(0, 2).map(([y, v]) => `${y}: ${B(v)}`).join(' · ') || '—'}</td>
        <td class="num">${B(r.need)}</td><td class="num">${B(r.d_oi)}</td>
        <td class="num ${r.cover == null ? '' : r.cover >= 1 ? 'pos' : 'neg'}">${r.cover != null ? pct(r.cover) : '—'}</td>
        <td class="num">${r.roic_incr != null ? pct(r.roic_incr, 1) : '—'}</td>
        <td class="num ${r.fcf_next4.base.fcf < 0 ? 'neg' : ''}"><b>${B(r.fcf_next4.base.fcf)}</b> <span class="muted">${B(r.fcf_next4.down.fcf)} / ${B(r.fcf_next4.up.fcf)}</span></td>
        <td class="num">${r.down_eps_2y != null ? `+$${r.down_eps_2y.toFixed(2)}` : '—'}</td></tr>`).join('')}</tbody></table></div>
      <details><summary>How these are worked out</summary>
      <p><b>Depreciation.</b> Each quarter’s capex is depreciated in equal parts over L quarters from the next quarter; L is the life that best reproduces the depreciation each
      company reported over the last three years (with a constant for assets older than the eight years on file). It is an effective life: servers and network gear
      (about six years at most of these companies), buildings (decades) and construction not yet in service, together. Ahead, the same rule runs on the forecast’s capex path.</p>
      <p><b>Profit needed.</b> The last eight quarters’ capex × (1 ÷ the effective life in years + ${pct(R.hurdle)}): a year of its depreciation plus a ${pct(R.hurdle)} pre-tax return.
      Set against the operating profit the company added over the same two years — which also holds everything else in its business, good and bad.
      <b>Return on PP&amp;E added</b>: that operating profit after ${pct(R.tax)} tax ÷ the net property and equipment added in the two years.</p>
      <p><b>Free cash flow.</b> Operating cash flow of the last twelve months grown at its last-year rate (held within −20% and +40%), minus each case’s capex.
      <b>EPS</b>: the −20% case’s lower depreciation over the next eight quarters, after tax, per diluted share — before any effect on revenue.</p></details>`;
    return h;
  }

  // ---------------------------------------------------------------- posts for X
  const URL_LEN = 23;
  const xlen = (s) => s.replace(/https?:\/\/\S+/g, 'x'.repeat(URL_LEN)).length;
  function trimTo(lines, head, tail, max) {
    const out = [head];
    for (const l of lines) { if (xlen(out.concat([l, tail]).join('\n')) > max) break; out.push(l); }
    out.push(tail);
    return out.join('\n');
  }
  function posts(d, url) {
    const P = [];
    const per = `last 12 months, from SEC filings`;
    if (d.kind === 'spend') {
      const w = (d.wallet || []).slice().sort((a, b) => (b.cents || 0) - (a.cents || 0)).filter((x) => x.cents);
      const c = d.coverage || {};
      P.push(trimTo(w.slice(0, 10).map((x) => `$${x.t} ${x.cents.toFixed(1)}¢${x.cents_py != null ? ` (${x.cents_py.toFixed(1)}¢ a year ago)` : ''}`),
        `Where $1 of ${d.name.replace(/ capex$/i, '')} spending goes (${per}):`,
        `${usd(c.spend)} spent by ${(d.buyers || []).map((b) => '$' + b.t).join(' ')}; ${pct(c.traced / c.spend)} traced to listed suppliers.\n${url}`, 280));
      const b = (d.buyers || []).slice().sort((x, y) => y.capex - x.capex);
      P.push(trimTo(b.map((x) => `$${x.t} ${usd(x.capex)}${x.capex_py ? ` (${sgn(x.capex / x.capex_py - 1)} Y/Y)` : ''}${x.ocf > 0 ? `, ${pct(x.capex / x.ocf)} of op. cash flow` : ''}`),
        `${d.name}: who is spending (${per}):`, url, 280));
    }
    if (d.customers) {
      const tot = d.customers.reduce((a, c) => a + c.v, 0);
      P.push(trimTo(d.customers.filter((c) => c.v > 0).map((c) => `${c.name}: ${usd(c.v)} (${pct(c.v / tot)})`),
        `Who pays: ${d.name} (${per}):`, url, 280));
    }
    if (d.regions) {
      const tot = d.regions.reduce((a, c) => a + c.v, 0);
      P.push(trimTo(d.regions.filter((c) => c.v > 0).sort((a, b) => b.v - a.v).map((c) => `${c.name}: ${pct(c.v / tot)} (${usd(c.v)})`),
        `${d.name}: where the revenue comes from (${per}):`, url, 280));
    }
    const rows = (d.companies || []).filter((c) => c.role !== 'tier2').sort((a, b) => b.attr - a.attr);
    if (d.kind !== 'spend') {
      const tot = rows.reduce((a, c) => a + c.attr, 0);
      P.push(trimTo(rows.slice(0, 10).map((c) => `$${c.t} ${usd(c.attr)}${c.yoy != null ? ` (${sgn(c.yoy)} Y/Y)` : ''}`),
        `${d.name}: ${usd(tot)} of revenue (${per}):`, url, 280));
    }
    if (hasModel(d)) {                                    // the forecast model's stress case
      const M = d.model;
      const hit = M.suppliers.map((r) => { const base = r.fc && r.fc.base ? r.fc.base.reduce((a, p) => a + p[1], 0) : null; return { r, base, dv: impact(M, r, -0.2) }; })
        .filter((x) => x.base && x.dv).sort((a, b) => a.dv / a.base - b.dv / b.base);
      if (hit.length > 2) {
        P.push(trimTo(hit.slice(0, 8).map((x) => `$${x.r.t} ${sgn(x.dv / x.base, 1)} (${usd(x.dv * 1e9)})`),
          `If the ${d.name.replace(/ capex$/i, '')} buyers spent 20% less over the next four quarters, revenue would move by (model fitted on SEC filings):`,
          `Each line: the supplier's link to their capex, estimated from its own history and tested out of sample.\n${url}`, 280));
      }
    }
    if (d.returns && d.returns.buyers && d.returns.buyers.length > 1) {
      const R = d.returns, C = R.combined, B = (v) => usd(v * 1e9);
      P.push(trimTo(R.buyers.slice().sort((a, b) => b.dep_next4.base - a.dep_next4.base).map((r) =>
        `$${r.t} ${B(r.dep_ttm)} → ${B(r.dep_next4.base)}${r.cover != null ? ` · profit added ${pct(r.cover)} of what its capex needs` : ''}`),
        `The depreciation wave (${d.name}): ${B(C.dep_ttm)} in the last 12 months → ${B(C.dep_next4.base)} in the next 4 quarters, mostly set by capex already spent:`,
        `From SEC filings: effective lives fitted on reported depreciation.\n${url}`, 280));
    }
    const gp = rows.filter((c) => c.gm != null).map((c) => ({ t: c.t, v: c.attr * c.gm, gm: c.gm })).sort((a, b) => b.v - a.v);
    if (gp.length > 2) {
      P.push(trimTo(gp.slice(0, 8).map((x) => `$${x.t} ${usd(x.v)} (${pct(x.gm)} margin)`), `Who keeps the profit in ${d.name} (gross profit, ${per}):`, url, 280));
    }
    return P;
  }
  function postsBox(d) {
    const url = `${location.origin}${location.pathname}#chain-${d.id}`;
    return `<div class="section-head"><h2>Posts for X</h2><span class="muted">Written by fixed rules from the figures above</span></div>
      ${posts(d, url).map((p) => `<div class="xpost"><pre>${esc(p)}</pre><div class="xpost-tools"><span class="muted small">${xlen(p)}/280</span>
        <button class="pill" data-copy>Copy</button><a class="pill" target="_blank" rel="noopener" href="https://x.com/intent/post?text=${encodeURIComponent(p)}">Post on X ↗</a></div></div>`).join('')}`;
  }
  function bindPosts(root) {
    root.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', () => {
      const text = b.closest('.xpost').querySelector('pre').textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(() => { b.textContent = 'Copied'; setTimeout(() => (b.textContent = 'Copy'), 1500); })
        .catch(() => { b.textContent = 'Select and copy'; });
    }));
  }

  function methodText(d) {
    const parts = [`<p>Every company figure is the trailing twelve months from its SEC filings: the latest 10-K’s year plus the latest 10-Q’s year to date
      minus the same months a year earlier (foreign filers: their latest results, converted to dollars). A company’s revenue line is the segment or
      product line named in the chain’s configuration where the filing tags one; otherwise its total revenue, flagged “line not found”.</p>`];
    if (d.kind === 'spend') {
      parts.push(`<p><b>Buyers</b> spend their capital expenditures (cash purchases of property and equipment${d.spend_label && /lease/.test(d.spend_label) ? ', plus assets taken on under finance leases where tagged' : ''}).
        <b>Suppliers</b> are counted for the part of their revenue line that comes from these buyers: what their filing names (a major customer
        that is one of the buyers, e.g. “Microsoft accounted for 26% of revenue”) and otherwise an assumed share, shown in the table. Servers and
        contract manufacturers count only their gross profit: the chips and memory inside a server are already counted at the chip makers.
        High-bandwidth memory is counted inside the accelerators, so memory makers count the rest.</p>
        <p>The buyer × supplier matrix is balanced with RAS (iterative proportional fitting), the method used for input-output tables: named
        cells stay fixed; the other cells start from each buyer’s size × each supplier’s size (× a preference where one is known, such as Google
        for Broadcom’s custom chips) and are scaled until every supplier’s column adds up to its revenue from these buyers and every buyer’s row
        to what it spent that suppliers account for. What the buyers spent that no listed supplier accounts for — buildings, land, foreign and private
        suppliers, in-house work — is a node of its own (${esc(d.untraced_note || '')}). When the suppliers’ estimates add up to more than the buyers spent,
        the rest is shown as other buyers.</p>
        <p><b>How the buyers paid</b> splits each buyer’s capital expenditures pro rata to its cash sources in the same twelve months (operating cash
        flow, new borrowing, share sales…), and adds its finance leases. <b>Suppliers’ suppliers</b> are estimated out of the suppliers’ cost of goods.</p>
        <p><b>Outlook year</b> replaces a buyer’s last twelve months with the capital expenditures it guided for a coming year in its latest earnings
        release (the midpoint of a range; the sentence is quoted in the buyers table); every supplier is scaled by how much of its column came from
        the buyers that moved. <b>Stakes flowing back</b> are shares of a chain company held by another one, from the holder’s latest 13F: money
        that goes out as an investment and can come back as orders.</p>`);
    } else if (d.kind === 'customers') {
      parts.push('<p>Customers come from the companies’ concentration disclosures (a customer’s share of revenue) and revenue tagged by customer, where the filings name them; otherwise from the assumed shares shown in the configuration. The rest is “other customers”.</p>');
    } else if (d.kind === 'geo') {
      parts.push('<p>Countries and regions are the companies’ own geographic revenue breakdown (by customer location), mapped to the regions shown; a company that does not break its revenue down by country appears as “not broken down”.</p>');
    }
    parts.push('<p><b>Profit pool</b>: gross profit on the revenue attributed to the chain (the company’s twelve-month gross margin). <b>Cash in &amp; out</b>: the companies’ cash-flow statements for the same twelve months — operating cash flow, borrowing and share sales in; capital expenditures, acquisitions, buybacks, dividends, debt repaid and cash burned out.</p>');
    parts.push('<p>The chains, their companies and the assumed shares are in <span class="mono">config/chains.json</span>; edit it and the next scan redraws them.</p>');
    return parts.join('');
  }

  /* Sentences about one company's place in a chain (the X report generator's "Supply chains" part). */
  function lines(d, tk) {
    const T = String(tk || '').toUpperCase(), out = [];
    const per = `in the last twelve months (to ${fdate(d.asof)})`;
    const b = (d.buyers || []).find((x) => x.t === T);
    if (b && d.coverage) {
      out.push(`${d.name}: $${T} spent ${usd(b.capex)}${b.capex_py ? ` (${sgn(b.capex / b.capex_py - 1)} Y/Y)` : ''} ${per}, ${pct(b.capex / d.coverage.spend)} of the ${usd(d.coverage.spend)} the chain’s ${(d.buyers || []).length} buyers spent` +
        `${b.ocf > 0 ? `; that is ${pct(b.capex / b.ocf)} of its operating cash flow` : ''}.`);
      if (b.guide && b.guide.rows && b.guide.rows.length) out.push(`Its latest earnings release: “${b.guide.rows[0].text}”`);
    }
    (d.companies || []).filter((c) => c.t === T).forEach((c) => {
      const L = (d.layers || []).find((x) => x.id === c.layer);
      if (d.kind === 'spend' && c.role !== 'tier2') {
        const w = (d.wallet || []).find((x) => x.id === c.id);
        out.push(`${d.name}: $${T} (${L ? L.name : ''}) takes ${w && w.cents != null ? w.cents.toFixed(1) + '¢' : '—'} of every $1 the buyers spend` +
          `${w && w.cents_py != null ? ` (${w.cents_py.toFixed(1)}¢ a year earlier)` : ''} — ${usd(c.attr)} ${per}, from ${c.line}${c.share != null && c.share < 0.999 ? ` × ${pct(c.share)}` : ''}` +
          `${(c.named || []).length ? `; named in its filing: ${c.named.map((n) => '$' + n.b).join(', ')}` : ''}.`);
      } else if (c.role === 'tier2') {
        out.push(`${d.name}, second tier: $${T} supplies the chain’s chip makers — about ${usd(c.attr)} ${per} (estimated).`);
      } else {
        const tot = (d.companies || []).filter((x) => x.layer === c.layer).reduce((a, x) => a + x.attr, 0);
        out.push(`${d.name} · ${L ? L.name : ''}: $${T} ${usd(c.attr)} ${per}, ${tot ? pct(c.attr / tot) : '—'} of the layer${c.yoy != null ? ` (${sgn(c.yoy)} Y/Y)` : ''}` +
          `${c.flows && Object.keys(c.flows).length ? `; who pays: ${Object.entries(c.flows).sort((a, b2) => b2[1] - a[1]).slice(0, 3).map(([k, v]) => `${k === 'usgov' ? 'U.S. government' : k} ${usd(v)}`).join(', ')}` : ''}` +
          `${c.china != null ? `; China ${pct(c.china)} of revenue` : ''}.`);
      }
    });
    return out;
  }

  global.FFChains = { index, page, layout, posts, lines };
})(window);
