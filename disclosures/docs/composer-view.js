/* Chart composer — one picture from several charts of a company or an ETF.
   On a company page (views.json "composer": #c-<cik>-x-composer) and in the Disclosure Hub (tab "Chart composer", any
   ticker — a stock or an ETF: #composer/SPY).
   1 Sources  tick the views to read: the earnings Sankey (latest quarter, the quarter against the one before, the latest
              fiscal year) and the Hub's chart views (rotation, fair value, price paths, options, move odds, highs and
              lows, quality, more charts). Each is drawn off-screen with the context a page gives it.
   2 Charts   every chart they drew (an <svg> or a <canvas> of a useful size, titled by the heading above it) as a
              thumbnail: tick the ones to use — the order you tick them is their order in the picture; titles editable.
   3 Picture  columns, size (natural, X 16:9, square, 4:5), title and subtitle → PNG, JPG or a copied image.
   A chart is drawn the way chart-share.js draws one (every computed style written into the SVG), a Sankey by its own
   exporter (window.Sankey). Everything happens in the browser; nothing is uploaded.
   window.ComposerView.render(el, { ticker, cik?, company?, hub, site?, here? }) */
(function (global) {
  'use strict';
  if (typeof window === 'undefined') return;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // [id, label, script (next to this file), global, what it needs: 'company' (a filer's figures) | 'ticker']
  const SOURCES = [
    ['sankey', 'Earnings Sankey — latest quarter', null, null, 'company'],
    ['sankey-q', 'Earnings Sankey — vs the quarter before (increase strips)', null, null, 'company'],
    ['sankey-fy', 'Earnings Sankey — latest fiscal year', null, null, 'company'],
    ['rotation', 'Rotation (RRG)', 'rrg-company-view.js', 'RRGCompanyView', 'ticker'],
    ['fairvalue', 'Fair value', 'fairvalue-view.js', 'FairValueView', 'company'],
    ['paths', 'Price paths & patterns', 'paths-view.js', 'PathsView', 'ticker'],
    ['options', 'Options: price paths', 'option-paths.js', 'FFOptionPaths', 'ticker'],
    ['moves', 'Move odds', 'moves-view.js', 'MovesView', 'ticker'],
    ['highs', 'Highs, lows & ranges', 'highs-view.js', 'HighsView', 'ticker'],
    ['quality', 'Quality', 'quality-view.js', 'QualityView', 'company'],
    ['charts', 'More charts', 'charts-view.js', 'MoreChartsView', 'company'],
  ];
  const DEFAULT = ['sankey', 'rotation', 'fairvalue', 'paths', 'moves'];
  const SIZES = [['natural', 'Natural size'], ['x', 'X post (16:9, 1600 × 900)'], ['square', 'Square (1080 × 1080)'], ['tall', 'Tall (4:5, 1080 × 1350)']];
  const DIMS = { x: [1600, 900], square: [1080, 1080], tall: [1080, 1350] };
  const HERE = (() => { try { const s = document.currentScript && document.currentScript.src; return s ? s.replace(/[^/]*$/, '') : ''; } catch (e) { return ''; } })();
  const PROPS = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'fill-opacity', 'stroke-opacity',
    'font-family', 'font-size', 'font-weight', 'font-style', 'letter-spacing', 'paint-order', 'text-anchor', 'dominant-baseline', 'visibility', 'display'];

  function css() {
    if (document.getElementById('cmp-css')) return;
    const s = document.createElement('style'); s.id = 'cmp-css';
    s.textContent = `.cmp{font-size:14px}.cmp h3{margin:18px 0 6px;font-size:16px}.cmp .cmp-sub{color:var(--muted,#6b6a66);font-size:13px;margin:2px 0 10px;line-height:1.5}
.cmp-src{display:flex;flex-wrap:wrap;gap:6px 14px;margin:6px 0 10px}.cmp-src label{display:flex;gap:6px;align-items:center;font-size:13px;cursor:pointer}
.cmp-src label.off{color:var(--muted,#6b6a66);cursor:default}.cmp button{font:inherit;font-size:13px;padding:5px 12px;border-radius:8px;border:1px solid var(--line,#ccc);background:none;color:inherit;cursor:pointer}
.cmp button.cmp-go{background:var(--ink,#1d1d1b);color:var(--bg,#fff);border-color:var(--ink,#1d1d1b)}.cmp button:disabled{opacity:.5;cursor:default}
.cmp-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}.cmp-msg{color:var(--muted,#6b6a66);font-size:12.5px}
.cmp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin:8px 0}
.cmp-card{position:relative;border:1px solid var(--line,#ddd);border-radius:10px;padding:8px;background:var(--surface,transparent);cursor:pointer}
.cmp-card.on{border-color:var(--ink,#1d1d1b);box-shadow:0 0 0 1px var(--ink,#1d1d1b) inset}.cmp-card img{width:100%;height:120px;object-fit:contain;background:var(--bg,#fff);border-radius:6px;display:block}
.cmp-card .cmp-n{position:absolute;top:6px;right:6px;min-width:22px;height:22px;border-radius:11px;background:var(--ink,#1d1d1b);color:var(--bg,#fff);font-size:12px;font-weight:600;display:none;align-items:center;justify-content:center}
.cmp-card.on .cmp-n{display:flex}.cmp-card .cmp-t{font-size:12.5px;font-weight:600;margin:6px 0 0;line-height:1.35}.cmp-card .cmp-v{font-size:11.5px;color:var(--muted,#6b6a66)}
.cmp-card input[type=text]{width:100%;box-sizing:border-box;font:inherit;font-size:12.5px;margin-top:6px;padding:3px 6px;border:1px solid var(--line,#ccc);border-radius:6px;background:var(--bg,#fff);color:inherit}
.cmp-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 14px;margin:6px 0}.cmp-form label{display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--muted,#6b6a66)}
.cmp-form input,.cmp-form select{font:inherit;font-size:13.5px;padding:5px 8px;border:1px solid var(--line,#ccc);border-radius:8px;background:var(--bg,#fff);color:var(--ink,inherit)}
.cmp-out img{max-width:100%;border:1px solid var(--line,#ddd);border-radius:8px;margin-top:8px}`;
    document.head.appendChild(s);
  }

  /* ---------- loading the views ---------- */
  const loading = {};
  function script(src) {
    if (!loading[src]) loading[src] = new Promise((res, rej) => {
      const sc = document.createElement('script'); sc.src = src; sc.async = true;
      sc.onload = () => res(); sc.onerror = () => { delete loading[src]; rej(new Error('could not load ' + src.replace(/^.*\//, ''))); };
      document.head.appendChild(sc);
    });
    return loading[src];
  }
  const get = (u) => fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  const tk = (t) => String(t || '').trim().toUpperCase().replace(/[./]/g, '-');
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const timeout = (p, ms) => Promise.race([p, wait(ms).then(() => { throw new Error('took too long'); })]);

  // a stock's company file (its Sankey quarters) when the context has none: the Hub looks the ticker up in the site index
  async function companyOf(ctx, site) {
    if (ctx.company) return ctx.company;
    try {
      const ix = await get(site + 'data/index.json');
      const row = (ix.companies || []).find((c) => tk(c.ticker) === tk(ctx.ticker));
      if (!row) return null;
      ctx.cik = ctx.cik || row.cik;
      return await get(site + `data/c/${row.cik}.json`);
    } catch (e) { return null; }
  }

  // the off-screen stage the views draw into: laid out (so styles and sizes are real) but invisible and inert
  function stage() {
    const d = document.createElement('div');
    d.className = 'cmp-stage'; d.setAttribute('aria-hidden', 'true'); d.inert = true;
    d.style.cssText = 'position:fixed;left:0;top:0;width:980px;opacity:0;pointer-events:none;z-index:-1;';
    document.body.appendChild(d);
    return d;
  }
  // wait until a view has stopped drawing: the number and size of its charts and its text unchanged over two looks
  async function settle(el, max = 7000) {
    let last = '', same = 0;
    for (let t = 0; t < max; t += 350) {
      const sig = [...el.querySelectorAll('svg,canvas')].map((x) => { const r = x.getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height); }).join(',') + '|' + el.textContent.length;
      same = sig === last ? same + 1 : 0;
      if (same >= 2 && !/^(Loading|Reading|Looking)/.test(el.textContent.trim())) return;
      last = sig;
      await wait(350);
    }
  }
  const HEAD = 'h1,h2,h3,h4,h5,h6';
  function titleOf(chart, root) {
    let t = '';
    root.querySelectorAll(HEAD).forEach((h) => { if (h.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING) t = h.textContent; });
    return t.replace(/\s+/g, ' ').trim().slice(0, 110);
  }
  // the charts a view drew: <svg> / <canvas> at least 260 × 110 on the page, not inside another one
  function chartsIn(root, src) {
    const out = [];
    root.querySelectorAll('svg,canvas').forEach((e) => {
      if (e.tagName.toLowerCase() === 'svg' && e.parentElement && e.parentElement.closest('svg')) return;
      const r = e.getBoundingClientRect();
      if (r.width < 260 || r.height < 110) return;
      if (e.tagName.toLowerCase() === 'canvas' && blank(e)) return;
      let title = '', sub = e.getAttribute('aria-label') || '', source = '';
      const box = e.closest('[data-ffs-chart]'), spec = box && window.FFShare && window.FFShare.specs && window.FFShare.specs.get(box.getAttribute('data-ffs-chart'));
      if (spec) { title = spec.title || ''; sub = spec.subtitle || sub; source = spec.source || ''; }
      title = title || titleOf(e, root) || src[1];
      out.push({ kind: 'el', el: e, view: src[1], title, sub: sub.slice(0, 160), source });
    });
    const seen = {};                                    // a title the view repeats (one chart per comparison): numbered
    out.forEach((c) => { seen[c.title] = (seen[c.title] || 0) + 1; if (seen[c.title] > 1) c.title += ` (${seen[c.title]})`; });
    return out;
  }
  function blank(c) {
    try {
      const x = document.createElement('canvas'); x.width = 24; x.height = 24;
      const g = x.getContext('2d'); g.drawImage(c, 0, 0, 24, 24);
      const d = g.getImageData(0, 0, 24, 24).data;
      for (let i = 3; i < d.length; i += 4) if (d[i]) return false;
      return true;
    } catch (e) { return false; }
  }

  /* ---------- drawing ---------- */
  function svgImage(svg) {                              // the SVG with every computed style written in: it draws alone
    const vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    const r = svg.getBoundingClientRect(), w = vb.length === 4 && vb[2] ? vb[2] : r.width, h = vb.length === 4 && vb[3] ? vb[3] : r.height;
    const clone = svg.cloneNode(true), a = [svg, ...svg.querySelectorAll('*')], b = [clone, ...clone.querySelectorAll('*')];
    a.forEach((el, i) => {
      const cs = getComputedStyle(el), t = b[i];
      if (!t || !t.style) return;
      PROPS.forEach((p) => { const v = cs.getPropertyValue(p); if (v) t.style.setProperty(p, v); });
    });
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', w); clone.setAttribute('height', h);
    clone.querySelectorAll('a').forEach((x) => x.removeAttribute('href'));
    const src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(clone));
    return new Promise((res, rej) => { const img = new Image(); img.onload = () => res({ img, w, h }); img.onerror = () => rej(new Error('a chart could not be drawn')); img.src = src; });
  }
  function blobImage(blob) {
    return new Promise((res, rej) => { const u = URL.createObjectURL(blob), img = new Image(); img.onload = () => res({ img, w: img.naturalWidth / 2, h: img.naturalHeight / 2, url: u }); img.onerror = () => rej(new Error('a chart could not be drawn')); img.src = u; });
  }
  // a chart as {img, w, h} (w, h in CSS pixels): a Sankey through its exporter, a <canvas> as it is, an <svg> restyled
  async function picture(c) {
    if (c.kind === 'sankey') {
      const S = window.Sankey, sc = S.layout(c.spec, c.opts || {});
      const p = await blobImage(await S.exportScene(sc, 'png', { scale: 2 }));
      return Object.assign(p, { w: sc.W, h: sc.H });
    }
    if (c.el.tagName.toLowerCase() === 'canvas') { const r = c.el.getBoundingClientRect(); return { img: c.el, w: r.width || c.el.width, h: r.height || c.el.height }; }
    return svgImage(c.el);
  }
  async function thumb(c) {
    const p = await picture(c), W = 420, H = Math.max(40, Math.round(W * p.h / p.w));
    const x = document.createElement('canvas'); x.width = W; x.height = Math.min(H, 600);
    const g = x.getContext('2d'); g.fillStyle = colors().bg; g.fillRect(0, 0, x.width, x.height);
    g.drawImage(p.img, 0, 0, W, H);
    if (p.url) URL.revokeObjectURL(p.url);
    return x.toDataURL('image/png');
  }
  function colors() {
    const cs = getComputedStyle(document.body), root = getComputedStyle(document.documentElement);
    const v = (n, d) => (root.getPropertyValue(n) || '').trim() || d;
    let bg = cs.backgroundColor; if (!bg || /rgba\(0, 0, 0, 0\)|transparent/.test(bg)) bg = v('--bg', '#ffffff');
    return { bg, ink: v('--ink', cs.color || '#1d1d1b'), muted: v('--muted', '#6b6a66'), line: v('--line', '#dddcd7'), font: cs.fontFamily || 'system-ui, sans-serif' };
  }
  function wrap(g, text, maxW, maxLines) {
    const words = String(text || '').split(/\s+/).filter(Boolean), out = []; let line = '';
    words.forEach((w) => { const t = line ? line + ' ' + w : w; if (g.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t; });
    if (line) out.push(line);
    if (maxLines && out.length > maxLines) { out.length = maxLines; out[maxLines - 1] = out[maxLines - 1].replace(/\s*\S*$/, '') + ' …'; }
    return out;
  }
  // the picture: a title block, the charts in a grid (each with its title), the sources and the site's name
  function compose(items, o) {
    const C = colors(), S = 2, pad = 36, gap = 28, n = items.length;
    const cols = o.cols === 'auto' ? (n <= 1 ? 1 : n <= 4 ? 2 : 3) : Math.max(1, Math.min(4, +o.cols || 1));
    const tileW = n === 1 && cols === 1 ? Math.max(720, Math.min(1400, Math.round(items[0].w))) : 760;
    const m = document.createElement('canvas').getContext('2d');
    const W = pad * 2 + cols * tileW + (cols - 1) * gap;
    m.font = `600 30px ${C.font}`; const tl = wrap(m, o.title, W - 2 * pad, 2);
    m.font = `15px ${C.font}`; const sl = o.subtitle ? wrap(m, o.subtitle, W - 2 * pad, 3) : [];
    const tiles = items.map((it) => {
      m.font = `600 17px ${C.font}`; const t = it.title ? wrap(m, it.title, tileW, 2) : [];
      m.font = `12.5px ${C.font}`; const s = it.sub && o.subs ? wrap(m, it.sub, tileW, 2) : [];
      const ch = Math.round(it.h * tileW / it.w);
      const top = (t.length ? 16 + 22 * (t.length - 1) : 0) + 16 * s.length + (t.length || s.length ? 10 : 0);   // text above the chart
      return { it, t, s, ch, top, h: top + ch };
    });
    const rows = []; for (let i = 0; i < tiles.length; i += cols) rows.push(tiles.slice(i, i + cols));
    const rowH = rows.map((r) => Math.max(...r.map((t) => t.h)));
    const day = new Date().toISOString().slice(0, 10), host = /^https?:/.test(location.protocol) ? location.host : 'filing-flows.com';
    const sources = [...new Set(items.map((it) => it.source).filter(Boolean))];
    m.font = `12px ${C.font}`;
    const foot = wrap(m, [sources.length ? 'Sources: ' + sources.join(' · ') : 'Data: SEC EDGAR filings and market prices; models and charts by Filing Flows.', `${host} · ${day} · History and models, not investment advice.`].join(' '), W - 2 * pad - 180, 4);
    const headH = tl.length * 38 + (sl.length ? 6 + sl.length * 21 : 0);
    const H = pad + headH + 22 + rowH.reduce((a, b) => a + b, 0) + gap * (rows.length - 1) + 24 + foot.length * 17 + pad;
    const c = document.createElement('canvas'); c.width = W * S; c.height = H * S;
    const g = c.getContext('2d'); g.scale(S, S);
    g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
    let y = pad + 28;
    g.fillStyle = C.ink; g.font = `600 30px ${C.font}`; tl.forEach((l) => { g.fillText(l, pad, y); y += 38; }); y -= 38;
    g.fillStyle = C.muted; g.font = `15px ${C.font}`; sl.forEach((l) => { y += 21; g.fillText(l, pad, y); });
    y += 22;
    g.strokeStyle = C.line; g.lineWidth = 1; g.beginPath(); g.moveTo(pad, y - 8); g.lineTo(W - pad, y - 8); g.stroke();
    rows.forEach((r, ri) => {
      r.forEach((t, ci) => {
        const x0 = pad + ci * (tileW + gap);
        let yy = y + 16;
        g.fillStyle = C.ink; g.font = `600 17px ${C.font}`; t.t.forEach((l, k) => { g.fillText(l, x0, yy + 22 * k); });
        yy = y + (t.t.length ? 16 + 22 * (t.t.length - 1) : 0);
        g.fillStyle = C.muted; g.font = `12.5px ${C.font}`; t.s.forEach((l) => { yy += 16; g.fillText(l, x0, yy); });
        g.drawImage(t.it.img, x0, y + t.top, tileW, t.ch);
      });
      y += rowH[ri] + gap;
    });
    y += 24 - gap;
    g.fillStyle = C.muted; g.font = `12px ${C.font}`; foot.forEach((l) => { y += 13; g.fillText(l, pad, y); y += 4; });
    g.fillStyle = C.ink; g.font = `600 17px ${C.font}`; g.textAlign = 'right'; g.fillText('Filing Flows', W - pad, H - pad + 4); g.textAlign = 'left';
    if (o.size === 'natural' || !DIMS[o.size]) return c;
    const [tw, th] = DIMS[o.size], out = document.createElement('canvas'); out.width = tw; out.height = th;
    const k = Math.min(tw / W, th / H), og = out.getContext('2d');
    og.fillStyle = C.bg; og.fillRect(0, 0, tw, th);
    og.imageSmoothingQuality = 'high';
    og.drawImage(c, (tw - W * k) / 2, (th - H * k) / 2, W * k, H * k);
    return out;
  }

  /* ---------- the view ---------- */
  async function render(el, ctx) {
    if (!el) return;
    css();
    ctx = Object.assign({}, ctx || {});
    const T = tk(ctx.ticker), hub = ctx.hub != null ? ctx.hub : '', site = ctx.site != null ? ctx.site : (hub ? '' : '../');
    const base = HERE || hub;
    const here = () => el.isConnected && (typeof ctx.here !== 'function' || ctx.here());
    document.querySelectorAll('.cmp-stage').forEach((s) => s.remove());
    if (!T && !ctx.company) { el.innerHTML = '<p class="muted">No ticker.</p>'; return; }
    el.innerHTML = '<p class="muted">Looking up the charts…</p>';
    const company = await companyOf(ctx, site);
    if (!here()) return;
    if (company && !window.Sankey) { try { await script(site + 'sankey.js'); } catch (e) { /* no Sankey here: the other charts still work */ } }
    const name = (company && company.profile && company.profile.name) || T;
    const has = (s) => s[4] !== 'company' || (s[0].startsWith('sankey') ? company && window.Sankey && (s[0] === 'sankey-fy' ? (company.years || []).some((y) => (y.nodes || []).length) : (company.quarters || []).some((q) => (q.nodes || []).length)) : !!(ctx.cik || company));
    const st = { src: new Set(DEFAULT.filter((id) => SOURCES.some((s) => s[0] === id && has(s)))), found: [], pick: [], cols: 'auto', size: 'x', subs: false,
      title: `${T ? T + ' — ' : ''}${name}`, subtitle: '' };
    let stg = null;
    const watch = setInterval(() => { if (!el.isConnected) { clearInterval(watch); if (stg) stg.remove(); } }, 2000);

    const draw = () => {
      let h = `<div class="cmp"><p class="cmp-sub">Pick charts of ${esc(name)} from the site's views and make <b>one picture</b> of them — for a post on X or a report. The views are drawn out of sight, the charts they make are listed; tick them in the order you want them.</p>`;
      h += `<h3>1 · Where to look</h3><div class="cmp-src">${SOURCES.map((s) => { const ok = has(s); return `<label class="${ok ? '' : 'off'}"${ok ? '' : ` title="${esc(s[4] === 'company' ? 'Needs a company that files with the SEC' : '')}"`}><input type="checkbox" data-cmp-src="${s[0]}"${st.src.has(s[0]) ? ' checked' : ''}${ok ? '' : ' disabled'}> ${esc(s[1])}</label>`; }).join('')}</div>`;
      h += `<div class="cmp-row"><button type="button" class="cmp-go" data-cmp="scan">Find the charts</button><span class="cmp-msg" data-cmp-msg></span></div>`;
      if (st.found.length) {
        h += `<h3>2 · Pick the charts</h3><p class="cmp-sub">${st.found.length} chart${st.found.length === 1 ? '' : 's'} found. Click to tick; the number is the place in the picture. Edit a title if you like.</p><div class="cmp-grid">`;
        h += st.found.map((c, i) => { const k = st.pick.indexOf(i); return `<div class="cmp-card${k >= 0 ? ' on' : ''}" data-cmp-card="${i}"><span class="cmp-n">${k + 1}</span><img alt="" src="${c.thumb || ''}"><div class="cmp-t">${esc(c.title)}</div><div class="cmp-v">${esc(c.view)}</div>${k >= 0 ? `<input type="text" data-cmp-title="${i}" value="${esc(c.title)}" aria-label="Title in the picture">` : ''}</div>`; }).join('');
        h += `</div><h3>3 · The picture</h3><div class="cmp-form">
          <label>Title<input type="text" data-cmp-f="title" value="${esc(st.title)}"></label>
          <label>Subtitle (optional)<input type="text" data-cmp-f="subtitle" value="${esc(st.subtitle)}" placeholder="e.g. What the charts say this week"></label>
          <label>Columns<select data-cmp-f="cols">${[['auto', 'Auto'], ['1', '1'], ['2', '2'], ['3', '3']].map(([v, l]) => `<option value="${v}"${st.cols === v ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          <label>Size<select data-cmp-f="size">${SIZES.map(([v, l]) => `<option value="${v}"${st.size === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
          <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" data-cmp-f="subs"${st.subs ? ' checked' : ''}> Each chart's description under its title</label></div>
          <div class="cmp-row"><button type="button" class="cmp-go" data-cmp="make"${st.pick.length ? '' : ' disabled'}>Make the picture (${st.pick.length})</button><button type="button" data-cmp="png" disabled>PNG</button><button type="button" data-cmp="jpg" disabled>JPG</button><button type="button" data-cmp="copy" disabled>Copy image</button><span class="cmp-msg" data-cmp-out-msg></span></div><div class="cmp-out"></div>`;
      }
      el.innerHTML = h + '</div>';
      bind();
    };
    const say = (t, k = 'data-cmp-msg') => { const m = el.querySelector(`[${k}]`); if (m) m.textContent = t; };
    let made = null;
    const download = (blob, ext) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `filing-flows-${(T || 'company').toLowerCase()}-charts-${new Date().toISOString().slice(0, 10)}.${ext}`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); };

    async function scan() {
      const btn = el.querySelector('[data-cmp="scan"]'); if (btn) btn.disabled = true;
      if (stg) stg.remove();
      stg = stage();
      const found = [], todo = SOURCES.filter((s) => st.src.has(s[0]) && has(s));
      for (let i = 0; i < todo.length; i++) {
        const s = todo[i];
        if (!here()) return;
        say(`Reading ${s[1]} … (${i + 1} of ${todo.length})`);
        try {
          if (s[0].startsWith('sankey')) {
            const spec = s[0] === 'sankey-fy' ? (company.years || []).find((y) => (y.nodes || []).length) : (company.quarters || []).find((q) => (q.nodes || []).length);
            const opts = s[0] === 'sankey-q' ? { compare: 'q' } : {};
            if (s[0] === 'sankey-q' && !(spec && spec.compare)) continue;
            const tt = String((spec.title || '').replace(/&amp;/g, '&')) + (s[0] === 'sankey-q' ? ' — vs the quarter before' : '');
            found.push({ kind: 'sankey', spec, opts, view: 'Earnings Sankey', title: tt, own: tt, sub: (spec.subtitle || '').replace(/&amp;/g, '&'), source: 'SEC filings (XBRL)' });
            continue;
          }
          if (!window[s[3]]) await timeout(script(base + s[2]), 15000);
          const box = document.createElement('div'); stg.appendChild(box);
          await timeout(Promise.resolve(window[s[3]].render(box, Object.assign({}, ctx, { ticker: T, company: company || ctx.company, hub, here }))), 25000);
          await settle(box);
          found.push(...chartsIn(box, s));
        } catch (e) { found.push(null); console.warn('composer:', s[0], e && e.message); }
      }
      st.found = found.filter(Boolean); st.pick = [];
      say(`Drawing ${st.found.length} thumbnails …`);
      for (const c of st.found) { try { c.thumb = await thumb(c); } catch (e) { c.thumb = ''; } }
      st.found = st.found.filter((c) => c.thumb);
      draw();
      say(st.found.length ? '' : 'No charts found in those views for this ticker: try other views.');
    }
    async function make() {
      const items = [];
      say('Drawing …', 'data-cmp-out-msg');
      try {
        if (document.fonts && document.fonts.ready) await document.fonts.ready;
        for (const i of st.pick) {                       // a Sankey's own title is in its picture: no second one above it
          const c = st.found[i], p = await picture(c);
          items.push(Object.assign({}, p, { title: c.own && c.title === c.own ? '' : c.title, sub: c.own ? '' : c.sub, source: c.source }));
        }
        const cv = compose(items, st);
        made = cv;
        const png = await new Promise((r) => cv.toBlob(r, 'image/png'));
        const out = el.querySelector('.cmp-out');
        if (out) out.innerHTML = `<img alt="The picture" src="${URL.createObjectURL(png)}">`;
        el.querySelectorAll('[data-cmp="png"],[data-cmp="jpg"],[data-cmp="copy"]').forEach((b) => { b.disabled = false; });
        say(`${cv.width} × ${cv.height} px`, 'data-cmp-out-msg');
        items.forEach((p) => { if (p.url) URL.revokeObjectURL(p.url); });
      } catch (e) { say('Could not draw it: ' + (e && e.message || e), 'data-cmp-out-msg'); }
    }
    function bind() {
      el.querySelectorAll('[data-cmp-src]').forEach((cb) => { cb.onchange = () => { if (cb.checked) st.src.add(cb.dataset.cmpSrc); else st.src.delete(cb.dataset.cmpSrc); }; });
      el.querySelectorAll('[data-cmp-card]').forEach((card) => {
        card.onclick = (ev) => {
          if (ev.target && ev.target.tagName === 'INPUT') return;
          const i = +card.dataset.cmpCard, k = st.pick.indexOf(i);
          if (k >= 0) st.pick.splice(k, 1); else st.pick.push(i);
          draw();
        };
      });
      el.querySelectorAll('[data-cmp-title]').forEach((inp) => { inp.oninput = () => { st.found[+inp.dataset.cmpTitle].title = inp.value; }; });
      el.querySelectorAll('[data-cmp-f]').forEach((f) => {
        const k = f.dataset.cmpF;
        f.oninput = f.onchange = () => { st[k] = f.type === 'checkbox' ? f.checked : f.value; };
      });
      const b = (k, fn) => { const x = el.querySelector(`[data-cmp="${k}"]`); if (x) x.onclick = fn; };
      b('scan', scan);
      b('make', make);
      b('png', () => made && made.toBlob((bl) => download(bl, 'png'), 'image/png'));
      b('jpg', () => made && made.toBlob((bl) => download(bl, 'jpg'), 'image/jpeg', 0.93));
      b('copy', async () => {
        if (!made) return;
        if (!navigator.clipboard || typeof ClipboardItem === 'undefined') { say('This browser cannot copy images: save the PNG', 'data-cmp-out-msg'); return; }
        try { await navigator.clipboard.write([new ClipboardItem({ 'image/png': new Promise((r) => made.toBlob(r, 'image/png')) })]); say('Image copied', 'data-cmp-out-msg'); } catch (e) { say('Could not copy: save the PNG', 'data-cmp-out-msg'); }
      });
    }
    draw();
  }
  global.ComposerView = { render, compose, chartsIn, SOURCES };
})(typeof window !== 'undefined' ? window : globalThis);
