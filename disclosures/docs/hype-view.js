/* Hype map over time — 13F money against the price, quarter by quarter: each dot is a stock its 13F flows flagged that
   quarter (crowded buy or exit, new money, big inflow or outflow), at net managers added − cut (→) and its price move
   (↑) during the quarter or over the three months after it. Pick the quarter, the price window and the range of quarters
   trails are drawn over; new on the map = flagged this quarter but not the one before (ringed); left the map = the other
   way round (faded). Shared by the Disclosure Hub (Signals → Hype map) and the main site's company page ("Hype map"
   view, views.json): window.HypeView.render(el, {ticker, hub}). Data: data/market/hype-history.json (app/market.py
   hype_history). Self-contained: colours from the host's CSS variables with fallbacks. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const spct = (v, d = 0) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const signed = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v)) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : '+'; return s + (a >= 1e9 ? '$' + num(a / 1e9, 1) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const qlabel = (p) => { const [y, m] = String(p).split('-'); return 'Q' + Math.ceil(+m / 3) + ' ' + y; };
  const FLAG = [[1, 'Crowded buy'], [2, 'New money'], [4, 'Big inflow'], [8, 'Crowded exit'], [16, 'Big outflow']];
  const flagWords = (f) => FLAG.filter(([b]) => f & b).map(([, w]) => w);
  const store = {};
  function load(hub) {
    const url = (hub || '') + 'data/market/hype-history.json';
    return store[url] || (store[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .catch((e) => { delete store[url]; throw e; }));
  }
  function palette(el) {
    const cs = getComputedStyle(el), v = (n, f) => (cs.getPropertyValue(n) || '').trim() || f;
    return { buy: v('--mk-profit', '#17804f'), sell: v('--mk-cost', '#c0392b'), ink: v('--ink', '#222'), mute: v('--muted', '#8a8f98'),
      line: v('--line', '#d9d6cf'), acc: v('--accent', '#2a6fb0'), bg: v('--bg', '#fff'), neu: '#9aa0a6' };
  }

  // one quarter's point for a stock: [x, y, row] or null
  function point(row, j, win) {
    const q = row.q[j];
    if (!q) return null;
    const y = win === 'in' ? q[3] : q[4];
    return fin(q[0]) && fin(y) ? { x: q[0], y: Math.max(-0.6, Math.min(1.2, y)), raw: y, q } : null;
  }

  function draw(el, D, st) {
    const C = palette(el), P = D.periods, j = st.j, j0 = Math.min(st.j0, j), win = st.win;
    const rows = Object.entries(D.rows);
    const on = (r, k) => k >= 0 && r.q[k] && r.q[k][5];
    const map = rows.filter(([, r]) => on(r, j) && point(r, j, win));
    const isNew = (r) => j > 0 && on(r, j) && !on(r, j - 1);
    const left = j > 0 ? rows.filter(([, r]) => on(r, j - 1) && !on(r, j) && point(r, j, win)) : [];
    let shown = st.show === 'new' ? map.filter(([, r]) => isNew(r)) : st.show === 'left' ? [] : map;
    const focus = st.ticker && D.rows[st.ticker] ? st.ticker : null;
    // the stocks whose trails are drawn
    const hot = map.filter(([, r]) => r.q[j][6] >= 2).sort((a, b) => Math.abs(b[1].q[j][0]) - Math.abs(a[1].q[j][0])).slice(0, 12);
    const trailSet = new Set(st.trails === 'all' ? shown.map(([t]) => t) : st.trails === 'labelled' ? hot.map(([t]) => t).concat(shown.filter(([, r]) => isNew(r)).slice(0, 6).map(([t]) => t)) : []);
    (st.pinned || []).forEach((t) => trailSet.add(t));
    if (focus) trailSet.add(focus);
    const trail = (t) => { const r = D.rows[t], pts = []; for (let k = j0; k <= j; k++) { const p = point(r, k, win); if (p) pts.push([k, p]); } return pts; };
    // axes from what is drawn
    const xs = [], ys = [];
    shown.concat(st.show === 'left' || st.ghosts ? left : []).forEach(([, r]) => { const p = point(r, j, win); xs.push(p.x); ys.push(p.y); });
    trailSet.forEach((t) => trail(t).forEach(([, p]) => { xs.push(p.x); ys.push(p.y); }));
    const xmax = Math.max(10, ...xs.map(Math.abs)) * 1.05, ylo = Math.min(-0.2, ...ys) - 0.03, yhi = Math.max(0.2, ...ys) + 0.03;
    const W = 760, H = 440, L = 56, R = 20, T = 22, B = 44;
    const sx = (v) => L + (v + xmax) / (2 * xmax) * (W - L - R), sy = (v) => T + (yhi - v) / (yhi - ylo) * (H - T - B);
    const nice = (lo, hi, n) => { const raw = (hi - lo) / n, p = 10 ** Math.floor(Math.log10(raw)), s = [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw); const o = []; for (let v = Math.ceil(lo / s) * s; v <= hi + 1e-9; v += s) o.push(+v.toFixed(6)); return o; };
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Hype map ${esc(qlabel(P[j]))}: net 13F managers against the price move" style="width:100%;height:auto;font:12px system-ui,sans-serif">`;
    s += `<defs><marker id="hv-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="${C.ink}" opacity=".7"/></marker></defs>`;
    nice(ylo, yhi, 5).forEach((v) => { s += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" stroke="${C.line}"/><text x="${L - 8}" y="${sy(v) + 4}" text-anchor="end" fill="${C.mute}">${spct(v)}</text>`; });
    nice(-xmax, xmax, 6).forEach((v) => { s += `<text x="${sx(v)}" y="${H - B + 16}" text-anchor="middle" fill="${C.mute}">${signed(v)}</text>`; });
    s += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${H - B}" stroke="${C.mute}"/><line x1="${L}" x2="${W - R}" y1="${sy(0)}" y2="${sy(0)}" stroke="${C.mute}"/>`;
    const qd = (x, y, t, a) => `<text x="${x}" y="${y}" text-anchor="${a}" fill="${C.mute}" font-style="italic" font-size="13">${t}</text>`;
    s += qd(W - R - 4, T + 14, 'Bought and rising', 'end') + qd(W - R - 4, H - B - 8, 'Bought while falling', 'end') + qd(L + 6, T + 14, 'Sold while rising', 'start') + qd(L + 6, H - B - 8, 'Sold and falling', 'start');
    s += `<text x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle" fill="${C.mute}">Net 13F managers in ${esc(qlabel(P[j]))} (added − cut)</text>`;
    s += `<text transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" fill="${C.mute}">Price ${win === 'in' ? 'during the quarter' : 'over the three months after'}</text>`;
    const colour = (q) => (q[5] & 7 && !(q[5] & 24) ? C.buy : q[5] & 24 && !(q[5] & 7) ? C.sell : C.neu);
    const tipOf = (t, r, q, extra) => `${t} ${r.name || ''}\n${signed(q[0])} net managers · ${num(q[1])} new positions · est. net ${big(q[2])}\nPrice during ${qlabel(P[q === r.q[j] ? j : r.q.indexOf(q)])}: ${spct(q[3])} · three months after: ${spct(q[4])}${q[7] ? ' (to date)' : ''}\n${flagWords(q[5]).join(', ') || 'Not flagged'}${extra || ''}`;
    // trails first, under the dots
    trailSet.forEach((t) => {
      const pts = trail(t);
      if (pts.length < 2) return;
      const f = t === focus, pin = (st.pinned || []).includes(t);
      const d = pts.map(([, p], i) => (i ? 'L' : 'M') + sx(p.x).toFixed(1) + ',' + sy(p.y).toFixed(1)).join('');
      s += `<path d="${d}" fill="none" stroke="${f ? C.acc : C.ink}" stroke-width="${f ? 2.4 : pin ? 1.8 : 1.1}" opacity="${f ? 0.9 : pin ? 0.7 : 0.35}" marker-end="url(#hv-arrow)"/>`;
      pts.slice(0, -1).forEach(([k, p]) => { s += `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${f ? 3.2 : 2.2}" fill="${f ? C.acc : C.ink}" opacity="${f ? 0.8 : 0.35}"><title>${esc(t + ' · ' + qlabel(P[k]) + ': ' + signed(p.x) + ' managers, ' + spct(p.raw))}</title></circle>`;
        if (f || pin) s += `<text x="${sx(p.x) + 5}" y="${sy(p.y) - 5}" font-size="10" fill="${C.mute}">${esc(qlabel(P[k]).replace(' 20', " '"))}</text>`; });
    });
    // left the map: faded, at where they are now
    if (st.show === 'left' || st.ghosts) left.forEach(([t, r]) => { const p = point(r, j, win);
      s += `<g data-hv="${esc(t)}" style="cursor:pointer"><circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="4.5" fill="none" stroke="${C.neu}" stroke-dasharray="2 2"><title>${esc(tipOf(t, r, r.q[j], '\nLeft the map: flagged in ' + qlabel(P[j - 1]) + ', not now'))}</title></circle></g>`; });
    // dots: the ordinary ones, then new entrants (ringed), then the hottest on top
    const order = shown.slice().sort((a, b) => (a[1].q[j][6] - b[1].q[j][6]) || (isNew(a[1]) - isNew(b[1])));
    order.forEach(([t, r]) => {
      const p = point(r, j, win), q = r.q[j], h = q[6] >= 2, n = isNew(r);
      s += `<g data-hv="${esc(t)}" style="cursor:pointer"><circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="11" fill="transparent"/>` +
        (n ? `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${h ? 8.5 : 7.5}" fill="none" stroke="${C.acc}" stroke-width="2"/>` : '') +
        `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${h ? 5.2 : 4}" fill="${colour(q)}" opacity="${h ? 0.95 : 0.7}" stroke="${C.bg}" stroke-width="1"><title>${esc(tipOf(t, r, q, n ? '\nNew on the map this quarter' : ''))}</title></circle></g>`;
    });
    // labels: the focus, pinned, hottest and new, without overlaps
    const boxes = [], lab = [];
    const want = [focus, ...(st.pinned || []), ...hot.map(([t]) => t), ...shown.filter(([, r]) => isNew(r)).sort((a, b) => Math.abs(b[1].q[j][0]) - Math.abs(a[1].q[j][0])).slice(0, 6).map(([t]) => t)];
    for (const t of want) {
      if (!t || lab.includes(t) || lab.length > 22) continue;
      const p = point(D.rows[t], j, win); if (!p) continue;
      const x = sx(p.x) + 8, y = sy(p.y) - 7, w = t.length * 7.2 + 4, b = [x, y - 11, x + w, y + 3];
      if (t !== focus && (b[2] > W - R || boxes.some((o) => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]))) continue;
      boxes.push(b); lab.push(t);
      s += `<text x="${x}" y="${y}" font-weight="700" font-size="${t === focus ? 14 : 12}" fill="${t === focus ? C.acc : C.ink}" paint-order="stroke" stroke="${C.bg}" stroke-width="3">${esc(t)}${isNew(D.rows[t]) ? ' ✦' : ''}</text>`;
    }
    if (focus && !point(D.rows[focus], j, win)) s += `<text x="${W - R - 4}" y="${T + 32}" text-anchor="end" fill="${C.acc}">${esc(focus)}: no 13F change or price for ${esc(qlabel(P[j]))}</text>`;
    s += '</svg>';
    return { svg: s, map, left, isNew };
  }

  function render(el, opt) {
    opt = opt || {};
    const ticker = opt.ticker ? String(opt.ticker).toUpperCase().replace(/[./]/g, '-') : '';
    el.innerHTML = '<p class="muted">Loading the Hype map…</p>';
    return load(opt.hub).then((D) => {
      if (!D || !(D.periods || []).length) { el.innerHTML = '<p class="muted">No quarters on file yet.</p>'; return; }
      const P = D.periods;
      const st = { j: P.length - 1, j0: Math.max(0, P.length - 4), win: 'after', show: 'all', trails: ticker ? 'none' : 'labelled', ghosts: false, pinned: [], ticker };
      const sel = (id, label, opts, v) => `<label style="display:inline-flex;flex-direction:column;gap:2px;font-size:12px;color:var(--muted,#777)">${label}<select data-hvc="${id}">${opts.map(([k, l]) => `<option value="${esc(k)}"${String(k) === String(v) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
      const qopts = P.map((p, k) => [k, qlabel(p)]);
      function paint() {
        const r = draw(el, D, st), j = st.j;
        const nNew = r.map.filter(([, x]) => r.isNew(x)).length;
        const row = ticker && D.rows[ticker];
        let h = `<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin:4px 0 8px">` +
          sel('j', 'Quarter', qopts, st.j) + sel('win', 'Price', [['after', 'Three months after the quarter'], ['in', 'During the quarter']], st.win) +
          sel('j0', 'Trails from', qopts.filter(([k]) => k <= st.j), Math.min(st.j0, st.j)) +
          sel('show', 'Show', [['all', 'Everything on the map'], ['new', 'New on the map only'], ['left', 'Left the map only']], st.show) +
          sel('trails', 'Trails', [['labelled', 'Labelled stocks'], ['all', 'Every stock shown'], ['none', 'Only pinned' + (ticker ? ' and ' + ticker : '')]], st.trails) +
          (opt.search !== false && !ticker ? `<label style="display:inline-flex;flex-direction:column;gap:2px;font-size:12px;color:var(--muted,#777)">Pin a ticker<input data-hvc="pin" placeholder="e.g. NVDA · Enter" style="width:120px"></label>` : '') +
          `<label style="font-size:12px;color:var(--muted,#777)"><input type="checkbox" data-hvc="ghosts"${st.ghosts ? ' checked' : ''}> show stocks that left the map</label></div>`;
        h += `<p class="sub" style="margin:0 0 6px">${esc(qlabel(P[j]))}: <b>${num(r.map.length)}</b> stocks on the map · <b>${num(nNew)}</b> new on it (ringed, ✦) · <b>${num(r.left.length)}</b> left it since ${j ? esc(qlabel(P[j - 1])) : 'the quarter before'}. Trails run ${esc(qlabel(P[Math.min(st.j0, j)]))} → ${esc(qlabel(P[j]))}; click a dot to pin or unpin its trail.</p>`;
        h += r.svg;
        h += `<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted,#777);margin-top:4px"><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${palette(el).buy}"></i> buy-side flags</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${palette(el).sell}"></i> sell-side flags</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;border:2px solid ${palette(el).acc}"></i> new on the map</span><span>larger: crowded buy or two buy flags</span><span>price clipped to −60% … +120%</span></div>`;
        if ((st.pinned || []).length) h += `<p class="sub">Pinned: ${st.pinned.map((t) => `<button type="button" data-hvu="${esc(t)}" style="cursor:pointer">${esc(t)} ×</button>`).join(' ')}</p>`;
        if (row) {
          h += `<table class="fv-tbl" style="width:100%;margin-top:8px;font-size:13px"><thead><tr><th>Quarter</th><th style="text-align:right">Net managers</th><th style="text-align:right">New positions</th><th style="text-align:right">Est. net $</th><th style="text-align:right">Price in quarter</th><th style="text-align:right">3 months after</th><th>On the map</th></tr></thead><tbody>` +
            P.map((p, k) => { const q = row.q[k]; if (!q) return `<tr><td>${esc(qlabel(p))}</td><td colspan="6" class="muted">no 13F change on file</td></tr>`;
              const was = k > 0 && row.q[k - 1] && row.q[k - 1][5];
              return `<tr${k === st.j ? ' style="font-weight:600"' : ''}><td>${esc(qlabel(p))}</td><td style="text-align:right">${signed(q[0])}</td><td style="text-align:right">${num(q[1])}</td><td style="text-align:right">${big(q[2])}</td><td style="text-align:right">${spct(q[3])}</td><td style="text-align:right">${spct(q[4])}${q[7] ? ' <span class="muted">to date</span>' : ''}</td><td>${q[5] ? (k > 0 && !was ? '<b>New</b> · ' : '') + esc(flagWords(q[5]).join(', ')) : (was ? '<span class="muted">left the map</span>' : '<span class="muted">—</span>')}</td></tr>`; }).reverse().join('') + '</tbody></table>';
        } else if (ticker) h += `<p class="sub">${esc(ticker)} has had no 13F flag or change on file in these quarters.</p>`;
        h += `<details style="margin-top:8px"><summary>How the map is built</summary><p class="sub">${esc(D.note || '')} Quarters with enough 13F filers on file: ${P.map(qlabel).join(', ')}. Thresholds per quarter (crowded = net managers, new money = new positions): ${(D.thresholds || []).map((c, k) => `${qlabel(P[k])} ${num(c.crowd_net_managers)} / ${num(c.new_positions)}`).join(' · ')}.</p></details>`;
        el.innerHTML = h;
        el.querySelectorAll('[data-hvc]').forEach((c) => {
          const k = c.dataset.hvc;
          if (k === 'pin') { c.onkeydown = (e) => { if (e.key !== 'Enter') return; const t = c.value.trim().toUpperCase().replace(/[./]/g, '-'); if (D.rows[t] && !st.pinned.includes(t)) { st.pinned.push(t); paint(); } else c.style.outline = '2px solid #c0392b'; }; return; }
          c.onchange = () => { st[k] = k === 'ghosts' ? c.checked : (k === 'j' || k === 'j0') ? +c.value : c.value; if (k === 'j' && st.j0 > st.j) st.j0 = st.j; paint(); };
        });
        el.querySelectorAll('[data-hv]').forEach((g) => { g.onclick = () => { const t = g.dataset.hv; if (t === ticker) return; const i = st.pinned.indexOf(t); if (i >= 0) st.pinned.splice(i, 1); else st.pinned.push(t); paint(); }; });
        el.querySelectorAll('[data-hvu]').forEach((b) => { b.onclick = () => { st.pinned = st.pinned.filter((t) => t !== b.dataset.hvu); paint(); }; });
      }
      paint();
    }).catch((e) => { el.innerHTML = `<p class="muted">The Hype map could not load (${esc(e.message)}).</p>`; });
  }
  if (typeof window !== 'undefined') window.HypeView = { render, draw, load };
})();
