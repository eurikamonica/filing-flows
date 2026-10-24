/* Chart share — every chart that carries a share bar can be saved as PNG or JPG (a card: title, the chart, source and
   date), copied as an image, and turned into a post for X with its analysis, written by rules from the numbers the chart
   draws (no language model).
   A view marks its chart and places a bar:
     <div data-ffs-chart="meta-rrg-spy">…<svg>…</svg>…</div>  (an <svg> or a <canvas> inside, or a Sankey scene)
     FFShare.bar({ key: 'meta-rrg-spy', title, subtitle, source, scene?: () => sceneForSankeyExport,
                   post: () => ({ title, paras: [...], post: 'text', link? }) })  → HTML
   Clicks are handled once for the whole document, so a view that redraws only has to call bar() again.
   Shared by the Disclosure Hub (index.html) and the Sankey site (loaded on demand from disclosures/chart-share.js).
   window.FFShare: bar, image(key, 'png' | 'jpg') → Blob, analysis(key), fit, xlen, register. No dependencies. */
(function () {
  if (typeof window === 'undefined') return;
  if (window.FFShare) return;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const xlen = (s) => String(s).replace(/https?:\/\/\S+/g, 'x'.repeat(23)).replace(/[\u{1F300}-\u{1FAFF}☀-➿]/gu, 'xx').length;
  // lines in order of importance, dropped from the end (never the first) until the post fits with its link
  function fit(lines, link, max = 280) {
    const L = lines.filter(Boolean), end = link ? ' ' + link : '';
    while (L.length > 1 && xlen(L.join(' ') + end) > max) L.pop();
    let s = L.join(' ');
    if (xlen(s + end) > max) s = s.slice(0, Math.max(0, s.length - (xlen(s + end) - max) - 1)).replace(/\s+\S*$/, '') + '…';
    return (s + end).trim();
  }
  const qk = (k) => (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(k) : String(k).replace(/["\\]/g, '\\$&'));
  const specs = new Map();
  function register(spec) { if (spec && spec.key) specs.set(spec.key, spec); return spec; }

  function css() {
    if (typeof document === 'undefined' || document.getElementById('ffs-css')) return;
    const s = document.createElement('style'); s.id = 'ffs-css';
    s.textContent = `.ffs-bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0 10px;font-size:12px;color:var(--muted,#777)}
.ffs-bar button{font:inherit;font-size:12px;padding:3px 10px;border-radius:8px;border:1px solid var(--line,#ccc);background:none;color:inherit;cursor:pointer}
.ffs-bar button:hover{border-color:var(--ink,#222);color:var(--ink,#222)}.ffs-bar .ffs-msg{margin-left:4px}
.ffs-post{border:1px solid var(--line,#ddd);border-radius:12px;padding:10px 12px;margin:4px 0 12px;background:var(--surface,transparent)}
.ffs-post h5{margin:0 0 6px;font-size:13px}.ffs-post p{margin:6px 0;font-size:13px;line-height:1.5;color:var(--ink,inherit)}
.ffs-post textarea{width:100%;box-sizing:border-box;min-height:92px;font:inherit;font-size:13px;line-height:1.45;padding:8px 10px;border:1px solid var(--line,#ddd);border-radius:8px;background:var(--bg,#fff);color:inherit;resize:vertical}
.ffs-post .ffs-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px;font-size:12px;color:var(--muted,#777)}
.ffs-post button{font:inherit;font-size:12px;padding:3px 10px;border-radius:8px;border:1px solid var(--line,#ccc);background:none;color:inherit;cursor:pointer}
.ffs-post button.ffs-primary{background:var(--accent,#2a78d6);border-color:var(--accent,#2a78d6);color:#fff}.ffs-over{color:var(--mk-cost,#c0392b)}`;
    document.head.appendChild(s);
  }
  function bar(spec) {
    if (!spec || !spec.key) return '';
    register(spec); css();
    const k = esc(spec.key);
    return `<div class="ffs-bar" data-ffs-bar="${k}"><span>Save or post this chart:</span><button type="button" data-ffs="png" data-ffs-k="${k}">PNG</button><button type="button" data-ffs="jpg" data-ffs-k="${k}">JPG</button>` +
      `<button type="button" data-ffs="copy" data-ffs-k="${k}">Copy image</button>${spec.post ? `<button type="button" data-ffs="post" data-ffs-k="${k}">Post for X + analysis</button>` : ''}<span class="ffs-msg" data-ffs-msg="${k}" role="status"></span></div><div data-ffs-out="${k}"></div>`;
  }

  /* ---------- the picture ---------- */
  const PROPS = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'fill-opacity', 'stroke-opacity',
    'font-family', 'font-size', 'font-weight', 'font-style', 'letter-spacing', 'paint-order', 'text-anchor', 'dominant-baseline', 'visibility', 'display'];
  const sel = (key) => document.querySelector(`[data-ffs-chart="${qk(key)}"]`);
  function chartEl(key) {
    const box = sel(key); if (!box) return null;
    if (/^(svg|canvas)$/i.test(box.tagName)) return box;
    return box.querySelector('canvas') || box.querySelector('svg');
  }
  function svgImage(svg) {                               // the SVG with every computed style written in: it draws alone
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
    return new Promise((res, rej) => { const img = new Image(); img.onload = () => res({ img, w, h }); img.onerror = () => rej(new Error('the chart could not be drawn')); img.src = src; });
  }
  function colors() {
    const cs = getComputedStyle(document.body), root = getComputedStyle(document.documentElement);
    const v = (n, d) => (root.getPropertyValue(n) || '').trim() || d;
    let bg = cs.backgroundColor; if (!bg || /rgba\(0, 0, 0, 0\)|transparent/.test(bg)) bg = v('--bg', '#ffffff');
    return { bg, ink: v('--ink', cs.color || '#1d1d1b'), muted: v('--muted', '#6b6a66'), font: cs.fontFamily || 'system-ui, sans-serif' };
  }
  function wrap(ctx, text, maxW) {
    const words = String(text || '').split(/\s+/), out = []; let line = '';
    words.forEach((w) => { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t; });
    if (line) out.push(line);
    return out;
  }
  async function card(spec, el) {
    const scale = 2, C = colors();
    let pic;
    if (/^canvas$/i.test(el.tagName)) pic = { img: el, w: el.clientWidth || el.width / (window.devicePixelRatio || 1), h: el.clientHeight || el.height / (window.devicePixelRatio || 1) };
    else pic = await svgImage(el);
    const W = Math.max(640, Math.round(pic.w)) + 48, pad = 24;
    const meas = document.createElement('canvas').getContext('2d');
    meas.font = `600 20px ${C.font}`; const tl = wrap(meas, spec.title || '', W - 2 * pad);
    meas.font = `13px ${C.font}`; const sl = spec.subtitle ? wrap(meas, spec.subtitle, W - 2 * pad) : [];
    const day = new Date().toISOString().slice(0, 10), host = (typeof location !== 'undefined' && /^https?:/.test(location.protocol)) ? location.host : 'Filing Flows';
    const foot = [spec.source || '', `${host} · ${day} · History and models, not investment advice.`].filter(Boolean);
    meas.font = `11px ${C.font}`; const fl = foot.flatMap((f) => wrap(meas, f, W - 2 * pad));
    const ch = Math.round(pic.h * ((W - 2 * pad) / pic.w > 1 ? 1 : (W - 2 * pad) / pic.w)), cw = Math.round(pic.w * (ch / pic.h));
    const H = pad + tl.length * 26 + (sl.length ? 4 + sl.length * 18 : 0) + 12 + ch + 12 + fl.length * 15 + pad;
    const c = document.createElement('canvas'); c.width = W * scale; c.height = H * scale;
    const x = c.getContext('2d'); x.scale(scale, scale);
    x.fillStyle = C.bg; x.fillRect(0, 0, W, H);
    let y = pad + 18;
    x.fillStyle = C.ink; x.font = `600 20px ${C.font}`; tl.forEach((l) => { x.fillText(l, pad, y); y += 26; });
    y -= 26 - 4;
    x.fillStyle = C.muted; x.font = `13px ${C.font}`; sl.forEach((l) => { y += 18; x.fillText(l, pad, y); });
    y += 12;
    x.drawImage(pic.img, pad + (W - 2 * pad - cw) / 2, y, cw, ch);
    y += ch + 12;
    x.fillStyle = C.muted; x.font = `11px ${C.font}`; fl.forEach((l) => { y += 11; x.fillText(l, pad, y); y += 4; });
    return c;
  }
  async function image(key, fmt) {
    const spec = specs.get(key); if (!spec) throw new Error('this chart is not on the page any more');
    if (spec.scene && window.Sankey && window.Sankey.exportScene) {
      const sc = spec.scene(); if (sc) return window.Sankey.exportScene(sc, fmt === 'jpg' ? 'jpg' : 'png', { scale: 2 });
    }
    const el = chartEl(key); if (!el) throw new Error('the chart is not drawn');
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    const c = await card(spec, el);
    return new Promise((res) => c.toBlob(res, fmt === 'jpg' ? 'image/jpeg' : 'image/png', 0.93));
  }
  const fname = (key, fmt) => `filing-flows-${String(key).replace(/[^a-z0-9-]+/gi, '-').toLowerCase()}-${new Date().toISOString().slice(0, 10)}.${fmt}`;

  /* ---------- the post ---------- */
  function analysis(key) {
    const spec = specs.get(key); if (!spec || !spec.post) return null;
    const p = spec.post() || {};
    const link = p.link === undefined ? (typeof location !== 'undefined' && /^https?:/.test(location.protocol) ? location.href : '') : p.link;
    return { title: p.title || spec.title || '', paras: (p.paras || []).filter(Boolean), post: p.lines ? fit(p.lines, link) : fit([p.post || ''], link) };
  }
  function postBox(key) {
    const a = analysis(key); if (!a) return '';
    const n = xlen(a.post), k = esc(key);
    return `<div class="ffs-post"><h5>${esc(a.title)}</h5>${a.paras.map((x) => `<p>${esc(x)}</p>`).join('')}
      <textarea data-ffs-ta="${k}" aria-label="Post text" spellcheck="true">${esc(a.post)}</textarea>
      <div class="ffs-row"><button type="button" class="ffs-primary" data-ffs="copypost" data-ffs-k="${k}">Copy post</button><button type="button" data-ffs="copyall" data-ffs-k="${k}">Copy analysis + post</button>
      <button type="button" data-ffs="copy" data-ffs-k="${k}">Copy image</button><button type="button" data-ffs="png" data-ffs-k="${k}">PNG</button>
      <a href="https://x.com/intent/post?text=${encodeURIComponent(a.post)}" target="_blank" rel="noopener" data-ffs-x="${k}">Open in X ↗</a>
      <span data-ffs-n="${k}" class="${n > 280 ? 'ffs-over' : ''}">${n}/280</span></div>
      <p style="font-size:11.5px;color:var(--muted,#777)">X's link cannot carry a picture: copy the image (or save the PNG) and paste it into the post.</p></div>`;
  }
  async function copyText(t) {
    try { await navigator.clipboard.writeText(t); return true; } catch (e) {
      const ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; } ta.remove(); return ok;
    }
  }
  function say(key, t) { document.querySelectorAll(`[data-ffs-msg="${qk(key)}"]`).forEach((e) => { e.textContent = t; }); }
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('click', async (ev) => {
      const b = ev.target && ev.target.closest && ev.target.closest('[data-ffs]'); if (!b) return;
      const key = b.getAttribute('data-ffs-k'), act = b.getAttribute('data-ffs');
      try {
        if (act === 'png' || act === 'jpg') {
          say(key, 'Drawing…');
          const blob = await image(key, act), a = document.createElement('a');
          a.href = URL.createObjectURL(blob); a.download = fname(key, act); document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 4000); say(key, 'Saved ' + act.toUpperCase());
        } else if (act === 'copy') {
          if (!navigator.clipboard || typeof ClipboardItem === 'undefined') { say(key, 'This browser cannot copy images: save the PNG'); return; }
          await navigator.clipboard.write([new ClipboardItem({ 'image/png': image(key, 'png') })]); say(key, 'Image copied');
        } else if (act === 'post') {
          const out = document.querySelector(`[data-ffs-out="${qk(key)}"]`); if (!out) return;
          out.innerHTML = out.innerHTML ? '' : postBox(key);
        } else if (act === 'copypost' || act === 'copyall') {
          const ta = document.querySelector(`[data-ffs-ta="${qk(key)}"]`), a = analysis(key);
          const t = act === 'copypost' ? (ta ? ta.value : a.post) : [a.title, ...a.paras, ta ? ta.value : a.post].join('\n\n');
          say(key, (await copyText(t)) ? 'Copied' : 'Could not copy');
        }
      } catch (e) { say(key, 'Could not: ' + (e && e.message || e)); }
    });
    document.addEventListener('input', (ev) => {
      const ta = ev.target; if (!ta || !ta.getAttribute || !ta.hasAttribute('data-ffs-ta')) return;
      const k = ta.getAttribute('data-ffs-ta'), n = xlen(ta.value), q = qk(k);
      const e = document.querySelector(`[data-ffs-n="${q}"]`); if (e) { e.textContent = n + '/280'; e.className = n > 280 ? 'ffs-over' : ''; }
      const x = document.querySelector(`[data-ffs-x="${q}"]`); if (x) x.href = 'https://x.com/intent/post?text=' + encodeURIComponent(ta.value);
    });
  }
  window.FFShare = { bar, image, analysis, postBox, fit, xlen, register, specs };
})();
