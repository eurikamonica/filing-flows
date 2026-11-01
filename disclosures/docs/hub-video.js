/* Holdings videos in the Hub — each ETF's and each 13F manager's stock weights and sector areas over time (ETF scanner,
   13F holdings) and the 13F crowding of stocks and sectors (crowding.js). Drawn by the site's Video Studio engine
   (../studio.js and ../actual-weights.js, loaded the first time a video panel comes into view), played on the page and
   exported as MP4 (WebCodecs; where the browser has no encoder, a real-time recording of the preview).

   HubVideo.slot(key, spec) returns a placeholder; after every render (window.HUB_BINDS) the player of that key — one DOM
   node kept across renders, so playback and the controls survive a re-render — takes its place.
   spec: {title, sub, file, styles: [[id, label]…], state: {k: 'actual', aw: 'etf', ah: 'XLK'} (a Video Studio state) or
          build: async ({style, n}, T) => V (a video built here: crowding), n: '12', noN: false} */
(function (root) {
  'use strict';
  const doc = root.document;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const H = {};
  // the views of a fund's or a manager's reported weights (Video Studio kind "actual")
  H.WEIGHT_STYLES = [['bars', 'Stock weights — bar race'], ['companies', 'Stock share areas'], ['stack', 'Sector share areas'],
    ['changes', 'Stock weight changes (pp)'], ['schanges', 'Sector weight changes (pp)']];
  const SHAPES = [['16x9', '16:9 wide'], ['9x16', '9:16 phone'], ['1x1', '1:1 square']];
  const LENGTHS = [['12', '12 s'], ['20', '20 s'], ['30', '30 s'], ['45', '45 s']];
  const LOOKS = [['bull', 'Dark'], ['clean', 'Light'], ['terminal', 'Terminal'], ['sunset', 'Sunset']];
  const NAMES = [['8', '8 names'], ['12', '12 names'], ['16', '16 names'], ['20', '20 names']];
  const players = new Map(), specs = new Map();
  let engine = null, styled = false;

  function css() {
    if (styled) return; styled = true;
    const s = doc.createElement('style');
    s.textContent = `.hv{margin:14px 0 4px}.hv-controls{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:flex-end;margin:8px 0}
.hv-controls label{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--muted,#6b6a66)}
.hv-controls select{min-width:0;max-width:100%}
.hv-stage{display:flex;justify-content:center;background:rgba(127,127,127,.08);border-radius:10px;padding:8px;overflow:hidden}
.hv-stage canvas{display:block;max-width:100%;height:auto;border-radius:6px}
.hv-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}.hv-bar .hv-scrub{flex:1 1 160px;min-width:120px}
.hv-prog{height:4px;background:rgba(127,127,127,.18);border-radius:2px;margin-top:6px;overflow:hidden}.hv-prog i{display:block;height:100%;width:0;background:var(--accent,#17734a)}
.hv-status{min-height:1.2em;margin:6px 0 0}.hv-notes{margin-top:4px}.hv-notes li{margin:2px 0}`;
    doc.head.appendChild(s);
  }
  function load(src) {
    return new Promise((ok, bad) => { const s = doc.createElement('script'); s.src = src; s.async = true; s.onload = ok; s.onerror = () => bad(new Error('could not load ' + src)); doc.head.appendChild(s); });
  }
  // the Video Studio engine: the Hub's data sit in data/, the site's in ../data/ (studio.js reads FF_HUB / FF_DATA)
  function studio() {
    if (!engine) {
      root.FF_HUB = root.FF_HUB || 'data/';
      root.FF_DATA = root.FF_DATA || '../data/';
      engine = (root.FFActual ? Promise.resolve() : load('../actual-weights.js'))
        .then(() => (root.FFStudio ? null : load('../studio.js')))
        .then(() => { if (!root.FFStudio || !root.FFStudio._t) throw new Error('the video engine did not load'); return root.FFStudio._t; });
      engine.catch(() => { engine = null; });
    }
    return engine;
  }
  H.engine = studio;
  const sel = (k, label, items, v) => `<label>${esc(label)}<select data-k="${k}">${items.map(([id, l]) => `<option value="${esc(id)}"${String(id) === String(v) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
  const optOf = (p) => ({ theme: p.theme, ar: p.ar, q: '1080', fps: '30', dur: +p.dur || 20, pace: 'steady', hold: 'auto' });
  // a Video Studio state for the player's view: weight changes by company or by sector are one style there
  function stateOf(p) {
    const style = p.style === 'schanges' ? 'changes' : p.style;
    return Object.assign({}, p.spec.state, { style, ag: p.style === 'schanges' ? 'sector' : 'company', an: String(p.n), theme: p.theme, ar: p.ar, dur: String(p.dur), end: '1' });
  }
  const enc = (st) => Object.entries(st).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');

  function create(key, spec) {
    css();
    const p = { key, spec, style: spec.style || spec.styles[0][0], n: spec.n || '12', ar: '16x9', dur: spec.dur || '20', theme: 'bull', t: 0, playing: false, V: null, token: 0, raf: 0, used: Date.now() };
    const node = doc.createElement('div');
    node.className = 'hv'; node.dataset.hvKey = key;
    node.innerHTML = `<div class="hv-controls">${sel('style', 'View', spec.styles, p.style)}${spec.noN ? '' : sel('n', 'Names', NAMES, p.n)}${sel('ar', 'Shape', SHAPES, p.ar)}${sel('dur', 'Length', LENGTHS, p.dur)}${sel('theme', 'Look', LOOKS, p.theme)}</div>
<div class="hv-stage"><canvas role="img" aria-label="${esc(spec.title || 'Holdings video')}"></canvas></div>
<div class="hv-bar"><button type="button" class="action hv-play" disabled>▶ Play</button><input class="hv-scrub" type="range" min="0" max="1000" value="620" aria-label="Position in the video"><button type="button" class="action primary hv-export" disabled>Export MP4 ↓</button>${spec.state ? '<a class="action hv-studio" target="_blank" rel="noopener">Open in Video Studio ↗</a>' : ''}</div>
<div class="hv-prog" hidden><i></i></div><p class="sub hv-status" aria-live="polite">The video loads when this panel comes into view.</p>
<details class="hv-notes"><summary>Sources and notes</summary><ul></ul></details>`;
    p.node = node;
    p.canvas = node.querySelector('canvas');
    node.querySelectorAll('select[data-k]').forEach((s) => s.addEventListener('change', () => {
      const k = s.dataset.k; p[k] = s.value;
      if (k === 'style' || k === 'n' || !p.V) rebuild(p, false);
      else { size(p); if (k === 'dur') p.t = Math.min(p.t, duration(p)); paint(p); link(p); }
    }));
    node.querySelector('.hv-play').addEventListener('click', () => (p.playing ? pause(p) : play(p)));
    node.querySelector('.hv-scrub').addEventListener('input', (e) => { if (!p.V) return; pause(p); p.t = (+e.target.value / 1000) * duration(p); paint(p, true); });
    node.querySelector('.hv-export').addEventListener('click', () => exportVideo(p));
    return p;
  }
  function status(p, text) { const el = p.node.querySelector('.hv-status'); if (el) el.textContent = text || ''; }
  function duration(p) { return p.T && p.V ? p.T.timing(p.V, optOf(p)).D : 20; }
  // the preview canvas: the export's shape at the width the page gives it, sharp on high-density screens
  function size(p) {
    const stage = p.node.querySelector('.hv-stage'), avail = Math.max(240, (stage && stage.clientWidth ? stage.clientWidth : 720) - 16);
    const [a, b] = { '16x9': [16, 9], '9x16': [9, 16], '1x1': [1, 1] }[p.ar] || [16, 9];
    let w = Math.min(avail, a >= b ? 1040 : 380), h = w * b / a;
    if (h > 680) { h = 680; w = h * a / b; }
    const dpr = Math.min(2, root.devicePixelRatio || 1);
    p.canvas.width = Math.round(w * dpr); p.canvas.height = Math.round(h * dpr);
    p.canvas.style.width = Math.round(w) + 'px'; p.canvas.style.height = Math.round(h) + 'px';
  }
  function paint(p, scrubbed) {
    const ctx = p.canvas.getContext('2d');
    if (!p.V || !p.T) return;
    try { p.T.draw(ctx, p.canvas.width, p.canvas.height, p.V, optOf(p), p.t); } catch (e) { status(p, 'The frame could not be drawn: ' + e.message); }
    if (!scrubbed) { const s = p.node.querySelector('.hv-scrub'); if (s) s.value = String(Math.round(1000 * p.t / Math.max(0.01, duration(p)))); }
  }
  function paintError(p, msg) {
    const ctx = p.canvas.getContext('2d'), W = p.canvas.width, Hh = p.canvas.height;
    ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, W, Hh);
    ctx.fillStyle = '#e8eef7'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = `600 ${Math.round(Math.min(W, Hh) / 24)}px "IBM Plex Sans", Arial, sans-serif`;
    const words = String(msg).split(' '), lines = [];
    let line = '';
    for (const w of words) { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > W * 0.86 && line) { lines.push(line); line = w; } else line = t; }
    lines.push(line);
    lines.slice(0, 4).forEach((l, i) => ctx.fillText(l, W / 2, Hh / 2 + (i - (Math.min(4, lines.length) - 1) / 2) * Math.min(W, Hh) / 16));
  }
  function play(p) {
    if (!p.V) return;
    const D = duration(p);
    if (p.t >= D - 0.01) p.t = 0;
    p.playing = true; p.t0 = performance.now() - p.t * 1000;
    p.node.querySelector('.hv-play').textContent = '❚❚ Pause';
    cancelAnimationFrame(p.raf);
    const loop = () => {
      if (!p.playing) return;
      if (!p.node.isConnected) { pause(p); return; }      // the page moved on: stop drawing
      p.t = (performance.now() - p.t0) / 1000;
      const D2 = duration(p);
      if (p.t >= D2) { p.t = D2; pause(p); }
      paint(p);
      if (p.playing) p.raf = requestAnimationFrame(loop);
    };
    p.raf = requestAnimationFrame(loop);
  }
  function pause(p) { p.playing = false; cancelAnimationFrame(p.raf); const b = p.node.querySelector('.hv-play'); if (b) b.textContent = '▶ Play'; }
  function link(p) {
    const a = p.node.querySelector('.hv-studio');
    if (a && p.T && p.spec.state) { try { a.href = '../#' + p.T.serialize(p.T.parseState(enc(stateOf(p)))); } catch (e) { a.removeAttribute('href'); } }
  }
  function notes(p) {
    const ul = p.node.querySelector('.hv-notes ul');
    if (!ul) return;
    const n = [...(p.V && p.V.notes ? p.V.notes : [])];
    if (p.V && p.V.foot) n.unshift(p.V.foot);
    ul.innerHTML = n.map((x) => `<li>${esc(x)}</li>`).join('') || '<li>No notes.</li>';
  }
  async function rebuild(p, keepT) {
    const my = ++p.token;
    pause(p); status(p, 'Loading the data…'); size(p);
    p.node.querySelector('.hv-play').disabled = true; p.node.querySelector('.hv-export').disabled = true;
    try {
      const T = p.T = await studio();
      let V;
      if (p.spec.build) {
        V = await p.spec.build({ style: p.style, n: +p.n }, T);
        V.endCard = true;
        T.finish(V, T.parseState('k=actual&style=bars'));
      } else {
        const st = T.parseState(enc(stateOf(p)));
        V = await T.build(st);
        V.style = st.style; V.scale = st.scale; V.endCard = true; V.dinc = st.dinc; V.dview = st.dview;
        T.finish(V, st);
      }
      if (my !== p.token) return;
      p.V = V; p.err = null;
      const D = duration(p);
      p.t = keepT ? Math.min(p.t, D) : D * 0.62;
      size(p); paint(p); notes(p); link(p);
      p.node.querySelector('.hv-play').disabled = false; p.node.querySelector('.hv-export').disabled = false;
      const frames = (V.grid || []).length;
      status(p, `${V.title || ''}${frames ? ` · ${frames} ${p.spec.unit || 'reports'}` : ''} · press Play, or Export MP4 for a ${p.ar === '9x16' ? '1080×1920' : p.ar === '1x1' ? '1080×1080' : '1920×1080'} video`);
    } catch (e) {
      if (my !== p.token) return;
      p.V = null; p.err = { msg: e.message || String(e), at: Date.now() };
      size(p); paintError(p, p.err.msg); status(p, p.err.msg); notes(p);
    }
  }
  // the fallback where WebCodecs is missing: record the preview canvas while it plays in real time
  function record(p, opt, onProgress) {
    return new Promise((ok, bad) => {
      const c = p.canvas;
      if (!c.captureStream || typeof MediaRecorder === 'undefined') { bad(new Error('this browser cannot make video files (no WebCodecs, no MediaRecorder)')); return; }
      const stream = c.captureStream(30), type = ['video/mp4;codecs=avc1', 'video/webm;codecs=vp9', 'video/webm'].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      const rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 8e6 } : undefined), parts = [];
      rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };
      let stopped = false;
      rec.onstop = () => ok(stopped ? 'cancelled' : { blob: new Blob(parts, { type: type.split(';')[0] || 'video/webm' }), recorded: true });
      const ctx = c.getContext('2d'), D = p.T.timing(p.V, opt).D, t0 = performance.now();
      rec.start(250);
      (function tick() {
        if (p.cancel) { stopped = true; rec.stop(); return; }
        const t = (performance.now() - t0) / 1000; p.T.draw(ctx, c.width, c.height, p.V, opt, Math.min(t, D)); onProgress(Math.min(1, t / D));
        if (t < D) requestAnimationFrame(tick); else setTimeout(() => rec.stop(), 120);
      })();
    });
  }
  const slug = (x) => String(x || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  async function exportVideo(p) {
    if (p.exporting) { p.cancel = true; status(p, 'Cancelling…'); return; }
    if (!p.V || !p.T) return;
    p.exporting = true; p.cancel = false; pause(p);
    const btn = p.node.querySelector('.hv-export'), prog = p.node.querySelector('.hv-prog'), began = performance.now();
    btn.textContent = 'Cancel'; prog.hidden = false;
    const set = (x) => { prog.firstElementChild.style.width = (100 * x).toFixed(1) + '%'; status(p, `Rendering ${Math.round(100 * x)}%…`); };
    try {
      const opt = optOf(p);
      let r = await p.T.exportMp4(p.V, opt, set, () => p.cancel);      // keeps going if the page moves on; Cancel stops it
      if (!r) { status(p, 'Recording the preview in real time (this browser has no video encoder)…'); r = await record(p, opt, set); }
      if (r === 'cancelled') { status(p, 'Export cancelled'); return; }
      const name = `filing-flows-${slug(p.spec.file || p.key)}-${slug(p.style)}-${p.ar}.${r.blob.type.includes('mp4') ? 'mp4' : 'webm'}`;
      const a = doc.createElement('a'); a.href = URL.createObjectURL(r.blob); a.download = name; doc.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 60000);
      H._last = r;
      status(p, `Saved ${name} · ${(r.blob.size / 1e6).toFixed(1)} MB${r.w ? ` · ${r.w}×${r.h}, ${r.fps} fps` : ''} · made in ${Math.round((performance.now() - began) / 1000)} s`);
    } catch (e) {
      status(p, 'The video could not be made: ' + (e.message || e));
    } finally { p.exporting = false; p.cancel = false; btn.textContent = 'Export MP4 ↓'; prog.hidden = true; }
  }

  H.slot = function (key, spec) {
    specs.set(key, spec);
    const p = players.get(key);
    if (p) { const changed = (p.spec.version || '') !== (spec.version || ''); p.spec = spec; if (changed && !p.exporting) { pause(p); p.V = null; } }
    return `<div class="hv-slot" data-hv="${esc(key)}"></div>`;
  };
  let seen = null;
  function watch(p) {
    if (p.V || p.watching) return;
    if (typeof IntersectionObserver === 'undefined') { rebuild(p, false); return; }
    p.watching = true;
    seen = seen || new IntersectionObserver((entries) => entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const q = [...players.values()].find((x) => x.node === e.target);
      seen.unobserve(e.target);
      if (q) { q.watching = false; if (!q.V) rebuild(q, false); }
    }), { rootMargin: '200px' });
    seen.observe(p.node);
  }
  // after every render: the players take their placeholders' places (the same node each time)
  H.attach = function () {
    doc.querySelectorAll('[data-hv]').forEach((slot) => {
      const key = slot.dataset.hv, spec = specs.get(key);
      if (!spec) return;
      let p = players.get(key);
      if (!p) { p = create(key, spec); players.set(key, p); }
      p.used = Date.now();
      slot.replaceWith(p.node);
      if (p.V) { size(p); paint(p); }
      else if (p.err && Date.now() - p.err.at < 30000) { size(p); paintError(p, p.err.msg); }   // a failed build: tried again after 30 s
      else watch(p);
    });
    if (players.size > 10) {                                // keep the ten players used last
      [...players.values()].filter((p) => !p.node.isConnected).sort((a, b) => a.used - b.used).slice(0, players.size - 10)
        .forEach((p) => { pause(p); players.delete(p.key); });
    }
  };
  H._players = players;
  root.HubVideo = H;
  root.HUB_BINDS = root.HUB_BINDS || {};
  root.HUB_BINDS.hubVideo = H.attach;
})(window);
