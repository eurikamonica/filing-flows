/* Backtest (#backtest): "if I had bought $X of a company on a date" — what it is worth now against the same money in
   SPY (or another benchmark), the path day by day, and every disclosure along the way marked on it: earnings reports,
   insiders' Form 4 buys and sales, material 8-Ks. The address keeps the choice (#backtest/t=NVDA&from=2024-01-02&amt=10000&vs=SPY).
   Data: the move odds' daily returns (disclosures/data/research/paths/moves/a/<KEY>.json: ten years of closes as log
   returns in basis points, the price as traded, no dividends), the filings with their time of day (moves/n/<KEY>.json),
   the smart-money module's scored insider trades (smart/t/<KEY>.json), the earnings research (research/earnings/c/<T>.json).
   For dividends reinvested, a monthly plan or several tickers at once, the video studio's growth race (#studio/k=growth). */
(function (root) {
  'use strict';
  const U = root.FFUx;
  const { esc, t, usd, spct, day, fileT } = U;
  const MATERIAL = new Set(['1.01', '1.02', '1.03', '1.05', '2.01', '2.03', '2.04', '2.05', '2.06', '3.01', '4.01', '4.02', '5.01', '5.02']);
  const ITEM = { '1.01': 'material agreement', '1.02': 'agreement ended', '1.03': 'bankruptcy', '1.05': 'cyber incident', '2.01': 'acquisition or disposal completed', '2.03': 'new debt',
    '2.04': 'debt accelerated', '2.05': 'exit costs', '2.06': 'impairment', '3.01': 'delisting notice', '4.01': 'auditor change', '4.02': 'restatement', '5.01': 'change in control', '5.02': 'officers or directors' };
  function parse(arg) {
    const q = new URLSearchParams(String(arg || '').replace(/^\//, ''));
    const amt = Number(q.get('amt'));
    return { t: fileT(q.get('t') || 'NVDA'), from: /^\d{4}-\d{2}-\d{2}$/.test(q.get('from') || '') ? q.get('from') : '', amt: amt > 0 ? amt : 10000, vs: fileT(q.get('vs') || 'SPY') };
  }
  const serialize = (st) => `backtest/t=${encodeURIComponent(st.t)}&from=${st.from}&amt=${st.amt}&vs=${encodeURIComponent(st.vs)}`;
  // moves/a → { days: [ISO], px: [close] } (the last close as published; the rest from the log returns)
  function decode(doc) {
    if (!doc || !doc.last) return null;
    let days;
    if (doc.dates) days = doc.dates.slice();
    else {
      const d = new Date(doc.d0 + 'T00:00:00Z');
      days = [doc.d0];
      for (const ch of doc.gaps || '') { d.setUTCDate(d.getUTCDate() + parseInt(ch, 36)); days.push(d.toISOString().slice(0, 10)); }
    }
    const r = doc.r || [], n = Math.min(days.length, r.length + 1), px = new Array(n);
    let s = 0;
    for (let i = n - 1; i >= 0; i--) { px[i] = doc.last * Math.exp(-s); if (i > 0) s += r[i - 1] / 1e4; }
    return { days: days.slice(0, n), px, name: doc.name, last: doc.last, asOf: doc.as_of, links: doc.links || {}, names: doc.names || {} };
  }
  const idxFrom = (days, d) => { let lo = 0, hi = days.length; while (lo < hi) { const m = (lo + hi) >> 1; if (days[m] < d) lo = m + 1; else hi = m; } return lo; };
  function path(series, from, amt) {
    const i0 = idxFrom(series.days, from);
    if (i0 >= series.days.length) return null;
    const p0 = series.px[i0], sh = amt / p0, vals = [], days = [];
    let peak = -Infinity, mdd = 0, best = [0, ''], worst = [0, ''];
    for (let i = i0; i < series.days.length; i++) {
      const v = sh * series.px[i];
      vals.push(v); days.push(series.days[i]);
      if (v > peak) peak = v;
      const dd = v / peak - 1;
      if (dd < mdd) mdd = dd;
      if (i > i0) { const r = series.px[i] / series.px[i - 1] - 1; if (r > best[0]) best = [r, series.days[i]]; if (r < worst[0]) worst = [r, series.days[i]]; }
    }
    const yrs = (Date.parse(days[days.length - 1]) - Date.parse(days[0])) / (365.25 * 864e5);
    const end = vals[vals.length - 1];
    return { i0, start: days[0], p0, shares: sh, days, vals, end, ret: end / amt - 1, cagr: yrs > 0.5 ? Math.pow(end / amt, 1 / yrs) - 1 : null, yrs, mdd, best, worst, peak };
  }
  function marks(st, series, nd, sm, er, from) {
    const out = [];
    for (const h of (er && er.history) || []) if (h.reported && h.reported >= from) out.push({ d: h.reported, k: 'earnings', label: `Earnings: ${h.beat ? 'beat' : 'missed'} the EPS estimate${h.surprise != null ? ` by ${(100 * Math.abs(h.surprise)).toFixed(1)}%` : ''}` });
    for (const ev of (nd && nd.events) || []) {
      if (!ev || ev[0] < from || !/^8-K/.test(ev[2] || '')) continue;
      const items = String(ev[3] || '').split(',').map((s) => s.trim()).filter((c) => MATERIAL.has(c));
      if (!items.length) continue;
      out.push({ d: ev[0], k: 'event', label: (ev[4] || '').slice(0, 90) || `8-K: ${items.map((c) => ITEM[c] || c).join(', ')}` });
    }
    const F = (sm && sm.trade_fields) || ['date', 'actor', 'name', 'group', 'd', 'size'];
    for (const x of (sm && sm.trades) || []) { const r = Object.fromEntries(F.map((k, i) => [k, x[i]])); if (r.group === 'ins' && r.date >= from) out.push({ d: r.date, k: r.d > 0 ? 'buy' : 'sell', label: `${r.name} ${r.d > 0 ? 'bought' : 'sold'} ${U.money(r.size || 0)}`, usd: r.size || 0, ex: r.ex }); }
    out.sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : 0);
    return out;
  }
  const COLOR = { earnings: '#3b6ea5', event: '#c08a3e', buy: '#2e7d4f', sell: '#b8402f' };
  const GLYPH = { earnings: '●', event: '◆', buy: '▲', sell: '▼' };
  function draw(canvas, P, B, mk, st) {
    const dpr = root.devicePixelRatio || 1, W = canvas.clientWidth || 720, H = 300;
    canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.height = H + 'px';
    const g = canvas.getContext('2d'); g.scale(dpr, dpr);
    const css = getComputedStyle(document.documentElement), ink = css.getPropertyValue('--ink').trim() || '#222', muted = css.getPropertyValue('--muted').trim() || '#777', line = css.getPropertyValue('--line').trim() || '#ddd';
    const L = 56, R = 12, T = 16, Bm = 28, n = P.vals.length;
    const all = P.vals.concat(B ? B.vals : []);
    let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
    const X = (i) => L + (W - L - R) * (n > 1 ? i / (n - 1) : 0), Y = (v) => T + (H - T - Bm) * (hi - v) / (hi - lo);
    g.font = '11px IBM Plex Sans, system-ui, sans-serif'; g.fillStyle = muted; g.strokeStyle = line; g.lineWidth = 1;
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4, y = Y(v); g.beginPath(); g.moveTo(L, y); g.lineTo(W - R, y); g.stroke(); g.textAlign = 'right'; g.fillText(usd(v, 0), L - 6, y + 4); }
    g.textAlign = 'left'; g.fillText(P.days[0], L, H - 8); g.textAlign = 'right'; g.fillText(P.days[n - 1], W - R, H - 8);
    const plot = (vals, color, width) => { g.beginPath(); g.strokeStyle = color; g.lineWidth = width; const step = Math.max(1, Math.floor(vals.length / 1200)); for (let i = 0; i < vals.length; i += step) { const x = X(i), y = Y(vals[i]); if (i === 0) g.moveTo(x, y); else g.lineTo(x, y); } g.stroke(); };
    if (B) plot(B.vals, muted, 1.2);
    plot(P.vals, ink, 1.8);
    g.beginPath(); g.setLineDash([4, 4]); g.strokeStyle = muted; g.moveTo(L, Y(st.amt)); g.lineTo(W - R, Y(st.amt)); g.stroke(); g.setLineDash([]);
    const by = new Map(P.days.map((d, i) => [d, i]));
    g.font = '12px IBM Plex Sans, system-ui, sans-serif'; g.textAlign = 'center';
    for (const m of mk) { let i = by.get(m.d); if (i == null) i = idxFrom(P.days, m.d); if (i >= n) continue; const yoff = m.k === 'buy' || m.k === 'earnings' ? -8 : 16; g.fillStyle = COLOR[m.k]; g.fillText(GLYPH[m.k], X(i), Y(P.vals[i]) + yoff); }
  }
  async function render(app, A, arg) {
    const here = A && A.here ? A.here : () => true;
    if (A && A.setNav) A.setNav('backtest');
    const st = parse(arg);
    const save = () => { try { history.replaceState(null, '', '#' + serialize(st)); } catch (e) { /* file:// */ } };
    app.innerHTML = `<div class="page-head"><div class="eyebrow">Backtest · <a href="#studio/k=growth&t=${encodeURIComponent(st.t)},SPY">Video with dividends and a monthly plan →</a></div><h1>If I had bought on that day</h1>
      <p class="muted" style="max-width:72ch">Put a sum into one company on any day of the last ten years and see what it is worth now against the same money in the market, with every earnings report, insider trade and material 8-K along the way marked on the path.</p></div>
      <form id="bt-form" class="fx-row" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
        <label class="v-f"><span>Ticker</span><span class="v-in"><input id="bt-t" value="${esc(st.t)}" style="width:7em" autocomplete="off"></span></label>
        <label class="v-f"><span>Bought on</span><span class="v-in"><input id="bt-from" type="date" value="${esc(st.from)}"></span></label>
        <label class="v-f"><span>Amount</span><span class="v-in"><input id="bt-amt" type="number" min="1" step="100" value="${st.amt}" style="width:8em"><i>$</i></span></label>
        <label class="v-f"><span>Against</span><span class="v-in"><select id="bt-vs"><option value="SPY">S&amp;P 500 (SPY)</option><option value="QQQ">Nasdaq 100 (QQQ)</option><option value="IWM">Russell 2000 (IWM)</option><option value="sector">Its sector ETF</option></select></span></label>
        <button class="btn" type="submit">Run</button><button class="btn" type="button" id="bt-link">Copy link</button></form>
      <div id="bt-out"><p class="muted">Loading the price history…</p></div>`;
    const $ = (s) => app.querySelector(s);
    $('#bt-vs').value = ['SPY', 'QQQ', 'IWM'].includes(st.vs) ? st.vs : 'sector';
    $('#bt-form').addEventListener('submit', (e) => { e.preventDefault(); st.t = fileT($('#bt-t').value); st.from = $('#bt-from').value; st.amt = Number($('#bt-amt').value) || 10000; st.vs = $('#bt-vs').value; save(); run(); });
    $('#bt-link').addEventListener('click', () => { save(); navigator.clipboard && navigator.clipboard.writeText(location.href).catch(() => {}); $('#bt-link').textContent = 'Copied'; setTimeout(() => { $('#bt-link').textContent = 'Copy link'; }, 1500); });
    async function run() {
      const out = $('#bt-out');
      out.innerHTML = '<p class="muted">Loading…</p>';
      const key = st.t;
      const a = await U.hub(`research/paths/moves/a/${key}.json`);       // the prices first: no other file is asked for a ticker without them
      const S = decode(a);
      const [nd, sm, er] = S ? await Promise.all([U.hub(`research/paths/moves/n/${key}.json`), U.hub(`smart/t/${key}.json`), U.hub(`research/earnings/c/${key}.json`)]) : [];
      if (!here()) return;
      if (!S) { out.innerHTML = `<div class="q-warn">No daily price history for ${esc(key)} in the move-odds universe (about 1,800 listed companies and the main ETFs). Try another ticker.</div>`; return; }
      if (!st.from || st.from < S.days[0]) st.from = S.days[Math.max(0, S.days.length - 252)];
      if (st.from > S.days[S.days.length - 2]) st.from = S.days[S.days.length - 2];
      $('#bt-from').value = st.from; $('#bt-from').min = S.days[0]; $('#bt-from').max = S.days[S.days.length - 2];
      let vsKey = st.vs === 'sector' ? (S.links.sector || 'SPY') : st.vs;
      const bdoc = vsKey === key ? null : await U.hub(`research/paths/moves/a/${vsKey}.json`);
      if (!here()) return;
      const BS = decode(bdoc);
      const P = path(S, st.from, st.amt), B = BS ? path(BS, st.from, st.amt) : null;
      if (!P) { out.innerHTML = '<div class="q-warn">That date is after the last close on file.</div>'; return; }
      const mk = marks(st, S, nd, sm, er, P.start);
      const vsName = (S.names && S.names[vsKey]) || (BS && BS.name) || vsKey;
      const cls = (v) => (v > 0 ? 'positive' : v < 0 ? 'negative' : '');
      const buys = mk.filter((m) => m.k === 'buy'), sells = mk.filter((m) => m.k === 'sell');
      const byDay = new Map(P.days.map((d, i) => [d, i]));
      const at = (d) => { let i = byDay.get(d); if (i == null) i = idxFrom(P.days, d); return i < P.vals.length ? i : null; };
      const after = (i, h) => (i != null && i + h < P.vals.length ? P.vals[i + h] / P.vals[i] - 1 : null);
      out.innerHTML = `<div class="v-result" style="margin-top:12px"><div><small>${usd(st.amt, 0)} in ${esc(S.name || key)} on ${esc(day(P.start))}</small><strong class="${cls(P.ret)}">${usd(P.end, 0)}</strong><span class="muted">${spct(P.ret)} · ${P.shares.toFixed(P.shares < 10 ? 3 : 1)} shares at ${usd(P.p0)}, now ${usd(S.last)}${P.cagr != null ? ` · ${spct(P.cagr)} a year` : ''}</span></div>
          ${B ? `<div><small>The same in ${esc(vsName)}</small><strong class="${cls(B.ret)}">${usd(B.end, 0)}</strong><span class="muted">${spct(B.ret)}${B.cagr != null ? ` · ${spct(B.cagr)} a year` : ''} · ${esc(key)} ${P.end >= B.end ? 'ahead' : 'behind'} by ${usd(Math.abs(P.end - B.end), 0)}</span></div>` : ''}
          <div><small>Worst fall from a peak</small><strong class="negative">${spct(P.mdd)}</strong><span class="muted">best day ${spct(P.best[0])} (${esc(day(P.best[1]))}) · worst ${spct(P.worst[0])} (${esc(day(P.worst[1]))})</span></div></div>
        <div class="q-card" style="padding:10px 12px"><canvas id="bt-cv" style="width:100%;display:block"></canvas>
          <p class="muted q-small" style="margin:6px 0 0">Black: ${esc(key)} · grey: ${esc(vsName)} · dashed: the money put in. Marks: <span style="color:${COLOR.earnings}">●</span> earnings report <span style="color:${COLOR.event}">◆</span> material 8-K <span style="color:${COLOR.buy}">▲</span> insider buy <span style="color:${COLOR.sell}">▼</span> insider sale. Prices as traded, no dividends; closes through ${esc(day(S.asOf))}.</p></div>
        ${mk.length ? `<h3 style="margin-top:18px">Along the way <span class="muted" style="font-weight:400">${mk.length} disclosures${buys.length || sells.length ? ` · insiders ${buys.length} buy${buys.length === 1 ? '' : 's'} (${U.money(buys.reduce((s, m) => s + m.usd, 0))}), ${sells.length} sale${sells.length === 1 ? '' : 's'} (${U.money(sells.reduce((s, m) => s + m.usd, 0))})` : ''}</span></h3>
          <div class="tbl-wrap"><table class="v-table"><thead><tr><th>Date</th><th>What</th><th class="num">Your money then</th><th class="num">Next 5 sessions</th><th class="num">Next 21 sessions</th></tr></thead><tbody>${mk.slice().reverse().slice(0, 120).map((m) => { const i = at(m.d), a5 = after(i, 5), a21 = after(i, 21); return `<tr><td>${esc(day(m.d))}</td><td><span style="color:${COLOR[m.k]}">${GLYPH[m.k]}</span> ${esc(m.label)}</td><td class="num">${i != null ? usd(P.vals[i], 0) : '—'}</td><td class="num ${cls(a5)}">${spct(a5)}</td><td class="num ${cls(a21)}">${spct(a21)}</td></tr>`; }).join('')}</tbody></table></div>` : '<p class="muted">No earnings reports, insider trades or material 8-Ks on file for this stretch.</p>'}
        <p class="muted q-small">Descriptive, not advice: what the price did after a date, not what it will do. Daily closes from the move-odds data; dividends are not included (the video studio's growth race adds them). Insider trades are open-market Form 4 trades over the last 400 days as scored by the smart-money module; 8-Ks are those with a material item.</p>
        <p><a class="btn small" href="#t-${encodeURIComponent(key)}">${esc(S.name || key)}: the company →</a> <a class="btn small" href="disclosures/#moves/${encodeURIComponent(key)}">Move odds →</a></p>`;
      draw($('#bt-cv'), P, B, mk, st);
      const cv = $('#bt-cv'), redraw = () => { if (cv.isConnected) draw(cv, P, B, mk, st); else root.removeEventListener('resize', redraw); };
      root.addEventListener('resize', redraw);
    }
    run();
  }
  root.FFBacktest = { render, parse, serialize, decode, path, marks, idxFrom };
  if (typeof module !== 'undefined') module.exports = root.FFBacktest;
})(typeof globalThis !== 'undefined' ? globalThis : this);
