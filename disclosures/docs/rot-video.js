/* The hub's chart players as video files — the Relative Rotation Graph and the other rotation charts played week by
   week (rotation.js rotPlayer → rotExport). Every frame the Play button would show is drawn on the page, rasterised
   with its computed styles (chart-share.js svgImage; a canvas chart is copied as it is), composed on a 1920×1080 /
   1080×1080 / 1080×1920 canvas with the chart's title, subtitle, the period shown, the source and the date, and
   encoded in the browser: WebCodecs (H.264, else VP9) into an MP4 with mp4-muxer — the Video Studio's way — or, where
   the browser has no encoder, a real-time recording of the frames (MediaRecorder, usually WebM).
   RotVideo.exportFrames({title, subtitle, source, host, fps, ms, hold: [first, last] seconds, shape, frames,
                          element: async (k) => <svg> | <canvas>, label: (k) => text, progress, cancelled})
     → {blob, w, h, fps, seconds, frames} or 'cancelled'. No dependencies beyond the MP4 writer, loaded when first used. */
(function (root) {
  'use strict';
  if (root.RotVideo) return;
  const doc = () => root.document || (typeof document !== 'undefined' ? document : null);   // the hub's page; the tests run the pure parts without one
  const MUXER = 'https://cdn.jsdelivr.net/npm/mp4-muxer@5.1.5/build/mp4-muxer.js';
  let muxLoad = null;
  const loadMuxer = () => muxLoad || (muxLoad = root.Mp4Muxer ? Promise.resolve(root.Mp4Muxer) : new Promise((ok, bad) => {
    const s = doc().createElement('script'); s.src = MUXER; s.onload = () => ok(root.Mp4Muxer); s.onerror = () => { muxLoad = null; bad(new Error('the MP4 writer did not load')); }; doc().head.appendChild(s);
  }));
  const tick = (ms) => new Promise((r) => setTimeout(r, ms || 0));
  async function pickCodec(w, h, fps) {
    if (typeof VideoEncoder === 'undefined') return null;
    for (const codec of ['avc1.640028', 'avc1.640033', 'avc1.4D4028', 'avc1.42E028', 'avc1.42E033']) {
      try { const r = await VideoEncoder.isConfigSupported({ codec, width: w, height: h, bitrate: 8e6, framerate: fps, avc: { format: 'avc' } }); if (r.supported) return { codec, mux: 'avc' }; } catch (e) { /* next */ }
    }
    for (const codec of ['vp09.00.40.08', 'vp09.00.31.08']) {
      try { const r = await VideoEncoder.isConfigSupported({ codec, width: w, height: h, bitrate: 8e6, framerate: fps }); if (r.supported) return { codec, mux: 'vp9' }; } catch (e) { /* next */ }
    }
    return null;
  }
  const colors = () => (root.FFShare && root.FFShare.colors ? root.FFShare.colors() : { bg: '#ffffff', ink: '#1d1d1b', muted: '#6b6a66', font: 'system-ui, sans-serif' });
  function wrap(ctx, text, maxW) {                     // words on lines no wider than maxW (chart-share.js's)
    const words = String(text || '').split(/\s+/), out = []; let line = '';
    words.forEach((w) => { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t; });
    if (line) out.push(line);
    return out;
  }
  // one chart as a picture: an <svg> with its styles written in (drawn alone), a <canvas> as it is
  async function picture(el) {
    if (!el) throw new Error('the chart is not drawn');
    if (/^canvas$/i.test(el.tagName)) return { img: el, w: el.width, h: el.height };
    if (!root.FFShare || !root.FFShare.svgImage) throw new Error('the chart cannot be drawn as a picture');
    return root.FFShare.svgImage(el);
  }
  // the layout of a video frame: title, subtitle, the chart fitted below them, the period at the bottom right, source and date
  function layout(ctx, o, w, h) {
    const C = colors(), pad = Math.round(w * 0.03), big = w >= h;
    const ts = Math.round((big ? h : w) / 26), ss = Math.round(ts * 0.6), fs = Math.round(ts * 0.44);
    ctx.font = `600 ${ts}px ${C.font}`; const tl = wrap(ctx, o.title || '', w - 2 * pad).slice(0, 2);
    ctx.font = `${ss}px ${C.font}`; const sl = o.subtitle ? wrap(ctx, o.subtitle, w - 2 * pad).slice(0, big ? 2 : 3) : [];
    const day = new Date().toISOString().slice(0, 10);
    const foot = [o.source || '', `${o.host || 'Filing Flows'} · ${day} · History and models, not investment advice.`].filter(Boolean);
    ctx.font = `${fs}px ${C.font}`; const fl = foot.flatMap((f) => wrap(ctx, f, w - 2 * pad)).slice(0, 3);
    const top = pad + tl.length * Math.round(ts * 1.3) + (sl.length ? sl.length * Math.round(ss * 1.4) + Math.round(ss * 0.4) : 0) + Math.round(ts * 0.5);
    const bottom = pad + fl.length * Math.round(fs * 1.4) + Math.round(fs * 0.6);
    return { C, pad, ts, ss, fs, tl, sl, fl, top, bottom };
  }
  function compose(ctx, o, w, h, L, pic, label) {
    const { C, pad, ts, ss, fs, tl, sl, fl, top, bottom } = L;
    ctx.fillStyle = C.bg; ctx.fillRect(0, 0, w, h);
    let y = pad + ts;
    ctx.fillStyle = C.ink; ctx.font = `600 ${ts}px ${C.font}`; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    tl.forEach((l) => { ctx.fillText(l, pad, y); y += Math.round(ts * 1.3); });
    if (sl.length) { y += Math.round(ss * 0.2); ctx.fillStyle = C.muted; ctx.font = `${ss}px ${C.font}`; sl.forEach((l) => { ctx.fillText(l, pad, y); y += Math.round(ss * 1.4); }); }
    const aw = w - 2 * pad, ah = h - top - bottom, k = Math.min(aw / pic.w, ah / pic.h), cw = Math.round(pic.w * k), ch = Math.round(pic.h * k);
    ctx.drawImage(pic.img, pad + Math.round((aw - cw) / 2), top + Math.round((ah - ch) / 2), cw, ch);
    y = h - pad - (fl.length - 1) * Math.round(fs * 1.4);
    ctx.fillStyle = C.muted; ctx.font = `${fs}px ${C.font}`;
    fl.forEach((l) => { ctx.fillText(l, pad, y); y += Math.round(fs * 1.4); });
    if (label) { ctx.textAlign = 'right'; ctx.fillStyle = C.ink; ctx.font = `600 ${Math.round(ts * 0.8)}px ${C.font}`; ctx.fillText(label, w - pad, h - pad); }
  }
  // which chart frame a moment of the video shows: the first held `hold[0]` s, then one every `ms`, the last held `hold[1]` s
  function schedule(o) {
    const fps = +o.fps || 30, ms = Math.max(16, +o.ms || 110), n = Math.max(1, o.frames | 0), hold = o.hold || [0.6, 2];
    const seconds = hold[0] + (n - 1) * ms / 1000 + hold[1], N = Math.max(1, Math.round(seconds * fps));
    const at = (i) => Math.max(0, Math.min(n - 1, Math.floor((i / fps - hold[0]) * 1000 / ms + 1e-9)));
    return { fps, n, seconds, N, at };
  }
  async function exportFrames(o) {
    const dim = { '16x9': [1920, 1080], '9x16': [1080, 1920], '1x1': [1080, 1080] }[o.shape] || [1920, 1080], w = dim[0], h = dim[1];
    const S = schedule(o), canvas = doc().createElement('canvas'); canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d'), L = layout(ctx, o, w, h);
    let cur = -1, pic = null;
    const frame = async (i) => {                           // draws video frame i; the chart is rasterised once per chart frame
      const k = S.at(i);
      if (k !== cur) { pic = await picture(await o.element(k)); cur = k; }
      compose(ctx, o, w, h, L, pic, o.label ? o.label(k) : '');
    };
    const pick = await pickCodec(w, h, S.fps);
    if (!pick) return record(o, S, canvas, frame);
    const M = await loadMuxer();
    const muxer = new M.Muxer({ target: new M.ArrayBufferTarget(), video: { codec: pick.mux, width: w, height: h, frameRate: S.fps }, fastStart: 'in-memory' });
    let failed = null;
    const enc = new VideoEncoder({ output: (chunk, meta) => muxer.addVideoChunk(chunk, meta), error: (e) => { failed = e; } });
    enc.configure({ codec: pick.codec, width: w, height: h, bitrate: 9e6, framerate: S.fps, ...(pick.mux === 'avc' ? { avc: { format: 'avc' } } : {}) });
    for (let i = 0; i < S.N; i++) {
      if (failed) throw failed;
      if (o.cancelled && o.cancelled()) { enc.close(); return 'cancelled'; }
      await frame(i);
      const vf = new VideoFrame(canvas, { timestamp: Math.round(i * 1e6 / S.fps), duration: Math.round(1e6 / S.fps) });
      enc.encode(vf, { keyFrame: i % (S.fps * 2) === 0 }); vf.close();
      while (enc.encodeQueueSize > 12) await tick(4);
      if (i % 6 === 0 && o.progress) { o.progress(i / S.N); await tick(0); }
    }
    await enc.flush(); enc.close();
    if (failed) throw failed;
    muxer.finalize();
    if (o.progress) o.progress(1);
    return { blob: new Blob([muxer.target.buffer], { type: 'video/mp4' }), codec: pick.codec, w, h, fps: S.fps, seconds: Math.round(S.seconds), frames: S.N };
  }
  // no WebCodecs: the frames drawn in real time on the canvas and recorded as they go (the file is what the browser can write)
  function record(o, S, canvas, frame) {
    return new Promise((ok, bad) => {
      if (!canvas.captureStream || typeof MediaRecorder === 'undefined') { bad(new Error('this browser cannot make video files (no WebCodecs, no MediaRecorder)')); return; }
      const stream = canvas.captureStream(S.fps), type = ['video/mp4;codecs=avc1', 'video/webm;codecs=vp9', 'video/webm'].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      const rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 8e6 } : undefined), parts = [];
      rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };
      let stopped = false;
      rec.onstop = () => ok(stopped ? 'cancelled' : { blob: new Blob(parts, { type: type.split(';')[0] || 'video/webm' }), codec: type || 'default', w: canvas.width, h: canvas.height, fps: S.fps, seconds: Math.round(S.seconds), frames: S.N, recorded: true });
      const t0 = performance.now();
      let busy = false;
      rec.start(250);
      (async function loop() {
        if (o.cancelled && o.cancelled()) { stopped = true; rec.stop(); return; }
        const i = Math.min(S.N - 1, Math.floor((performance.now() - t0) / 1000 * S.fps));
        if (!busy) { busy = true; try { await frame(i); } catch (e) { bad(e); return; } busy = false; }
        if (o.progress) o.progress(i / S.N);
        if (i < S.N - 1) requestAnimationFrame(loop); else setTimeout(() => rec.stop(), 150);
      })();
    });
  }
  const api = { exportFrames, schedule, layout, compose };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.RotVideo = api;
})(typeof window !== 'undefined' ? window : this);
