/* Hype map over time — 13F managers against the price, in views that never mix clocks (research spec v5 §6, §15.5):

     legacy_snapshot        the original Signals map (hub only, drawn by market.js): the latest report quarter's net managers
                            against each stock's trailing three months to today — a mixed-clock snapshot, kept as it was;
     quarter_aligned        report quarter q: comparable managers' net change against the price over the same quarter —
                            retrospective (those 13Fs were public only weeks later);
     public_knowledge_asof  the first close after the 45-day 13F deadline: only 13Fs filed before it, against the trailing
                            three months to it, with what the stock did next (4 and 12 weeks, minus SPY).

   Each dot is a stock its 13F flows flagged in that quarter of that view (crowded buy or exit, new money, big inflow or
   outflow — the quarter's own thresholds). New on the map = flagged this quarter but not the one before (ringed); left
   the map = the other way round (dashed). Trails join one stock's points across quarters of the same view. Diamonds:
   officials' purchases (◆) and sales (◇) — PTRs, a different source, never added to the 13F count. Shared by the
   Disclosure Hub (Signals → Hype map) and the company page ("Hype map", views.json):
   window.HypeView.render(el, {ticker, hub, legacy, view}). Data: data/market/hype-history.json (app/crowd_clocks.py).
   Below the map: the descriptive transition audit (transition-matrix.js, window.CrowdTransitions). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const spct = (v, d = 0) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const signed = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v)) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : '+'; return s + (a >= 1e9 ? '$' + num(a / 1e9, 1) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const qlabel = (p) => { const [y, m] = String(p).split('-'); return 'Q' + Math.ceil(+m / 3) + ' ' + y; };
  const day = (d) => { if (!d) return '—'; const x = new Date(d + 'T12:00:00Z'); return x.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }); };
  const FLAG = [[1, 'Crowded buy'], [2, 'New money'], [4, 'Big inflow'], [8, 'Crowded exit'], [16, 'Big outflow']];
  const flagWords = (f) => FLAG.filter(([b]) => f & b).map(([, w]) => w);
  // per view: where its quarters live and which point field is which
  const VIEWS = {
    quarter_aligned: { key: 'qa', label: 'Quarter-aligned (retrospective)', short: 'Quarter-aligned', y: 'price during the quarter', off: [10, 11], audit: 'quarter_aligned' },
    public_knowledge_asof: { key: 'pa', label: 'Public as of the 13F deadline', short: 'Public as of deadline', y: 'trailing 3 months to the decision day', off: [11, 12], audit: 'public_knowledge_asof_45d' },
  };
  const store = {};
  function load(hub, name) {
    const url = (hub || '') + 'data/market/' + (name || 'hype-history.json');
    return store[url] || (store[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .catch((e) => { delete store[url]; throw e; }));
  }
  function palette(el) {
    const cs = getComputedStyle(el), v = (n, f) => (cs.getPropertyValue(n) || '').trim() || f;
    return { buy: v('--mk-profit', '#17804f'), sell: v('--mk-cost', '#c0392b'), ink: v('--ink', '#222'), mute: v('--muted', '#8a8f98'),
      line: v('--line', '#d9d6cf'), acc: v('--accent', '#2a6fb0'), bg: v('--bg', '#fff'), neu: '#9aa0a6' };
  }
  const quarters = (D, view) => { const V = D.views[view] || {}; return V.periods || []; };
  const metaOf = (D, view, j) => { const V = D.views[view] || {}; return (V.clock || V.origins || [])[j] || {}; };
  const jLabel = (D, view, j) => { const m = metaOf(D, view, j), p = quarters(D, view)[j]; return qlabel(p) + (m.kind === 'live' ? ' (live, partial)' : ''); };

  // one quarter's point for a stock in a view: {x, y (display, clipped), raw, q} or null
  function point(row, view, j) {
    const q = (row[VIEWS[view].key] || [])[j];
    if (!q) return null;
    return fin(q[0]) && fin(q[5]) ? { x: q[0], y: Math.max(-0.6, Math.min(1.2, q[5])), raw: q[5], q } : null;
  }

  // the clock line under the controls: what X and Y are, and when they were known
  function clockLine(D, view, j) {
    const m = metaOf(D, view, j), p = quarters(D, view)[j];
    if (view === 'quarter_aligned') {
      const nc = m.not_comparable || {};
      return `<b>${esc(qlabel(p))}</b> · X: comparable managers (complete 13Fs for ${esc(qlabel(m.price_window ? m.price_window[0] : ''))} and ${esc(qlabel(p))}): <b>${num(m.comparable_managers)}</b> of ${num(m.prior_reporters)} that reported the quarter before` +
        ` <span class="muted">(not matched: ${num(nc.not_filed)} not filed, ${num(nc.confidential)} confidential, ${num(nc.gap)} skipped a quarter, ${num(nc.incomplete)} incomplete)</span>` +
        ` · Y: price ${esc(day(m.price_window && m.price_window[0]))} → ${esc(day(p))} (SPY ${spct(m.spy, 1)})` +
        ` · <span class="muted">retrospective: these 13Fs became public over the ~45 days after the quarter end, so this was not knowable at ${esc(day(p))}${m.finalised ? '' : ' · <b>still finalising</b> (late filers)'}</span>`;
    }
    if (m.kind === 'live') return `<b>${esc(qlabel(p))} — live, partial</b> · X: the 13Fs filed so far: <b>${num(m.comparable_managers_public)}</b> comparable managers of ${num(m.prior_reporters)} that reported the quarter before · Y: trailing 3 months ${esc(day(m.price_window && m.price_window[0]))} → ${esc(day(m.decision_day))} (latest close) · <span class="muted">most managers file in the last two weeks before the 45-day deadline; this point will move</span>`;
    const sf = m.spy_forward || {};
    return `<b>${esc(qlabel(p))}</b> · decision day <b>${esc(day(m.decision_day))}</b> (first close after the ${esc(day(m.anchor))} deadline) · X: comparable 13F pairs filed before it: <b>${num(m.comparable_managers_public)}</b> of ${num(m.prior_reporters)} managers` +
      ` · Y: trailing 3 months ${esc(day(m.price_window && m.price_window[0]))} → ${esc(day(m.decision_day))} · next 4 / 12 weeks: SPY ${sf['4w'] != null ? spct(sf['4w'], 1) : 'pending'} / ${sf['12w'] != null ? spct(sf['12w'], 1) : 'pending'}`;
  }

  function draw(el, D, st) {
    const C = palette(el), view = st.view, V = VIEWS[view], P = quarters(D, view), j = st.j, j0 = Math.min(st.j0, j);
    const rows = Object.entries(D.rows).filter(([, r]) => r[V.key]);
    const on = (r, k) => k >= 0 && r[V.key][k] && r[V.key][k][6];
    const map = rows.filter(([, r]) => on(r, j) && point(r, view, j));
    const isNew = (r) => j > 0 && on(r, j) && !on(r, j - 1);
    const left = j > 0 ? rows.filter(([, r]) => on(r, j - 1) && !on(r, j) && point(r, view, j)) : [];
    const shown = st.show === 'new' ? map.filter(([, r]) => isNew(r)) : st.show === 'left' ? [] : map;
    const focus = st.ticker && D.rows[st.ticker] ? st.ticker : null;
    const hot = map.filter(([, r]) => r[V.key][j][7] >= 2).sort((a, b) => Math.abs(b[1][V.key][j][0]) - Math.abs(a[1][V.key][j][0])).slice(0, 12);
    const trailSet = new Set(st.trails === 'all' ? shown.map(([t]) => t) : st.trails === 'labelled' ? hot.map(([t]) => t).concat(shown.filter(([, r]) => isNew(r)).slice(0, 6).map(([t]) => t)) : []);
    (st.pinned || []).forEach((t) => trailSet.add(t));
    if (focus) trailSet.add(focus);
    const trail = (t) => { const r = D.rows[t], pts = []; for (let k = j0; k <= j; k++) { const p = point(r, view, k); if (p) pts.push([k, p]); } return pts; };
    const xs = [], ys = [];
    shown.concat(st.show === 'left' || st.ghosts ? left : []).forEach(([, r]) => { const p = point(r, view, j); xs.push(p.x); ys.push(p.y); });
    trailSet.forEach((t) => trail(t).forEach(([, p]) => { xs.push(p.x); ys.push(p.y); }));
    if (focus) { const p = point(D.rows[focus], view, j); if (p) { xs.push(p.x); ys.push(p.y); } }
    const xmax = Math.max(10, ...xs.map(Math.abs)) * 1.05, ylo = Math.min(-0.2, ...ys) - 0.03, yhi = Math.max(0.2, ...ys) + 0.03;
    const W = 760, H = 440, L = 56, R = 20, T = 22, B = 44;
    const sx = (v) => L + (v + xmax) / (2 * xmax) * (W - L - R), sy = (v) => T + (yhi - v) / (yhi - ylo) * (H - T - B);
    const nice = (lo, hi, n) => { const raw = (hi - lo) / n, p = 10 ** Math.floor(Math.log10(raw)), s = [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw); const o = []; for (let v = Math.ceil(lo / s) * s; v <= hi + 1e-9; v += s) o.push(+v.toFixed(6)); return o; };
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Hype map, ${esc(V.short)}, ${esc(jLabel(D, view, j))}: net 13F managers against the price move" style="width:100%;height:auto;font:12px system-ui,sans-serif">`;
    s += `<defs><marker id="hv-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="${C.ink}" opacity=".7"/></marker></defs>`;
    nice(ylo, yhi, 5).forEach((v) => { s += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" stroke="${C.line}"/><text x="${L - 8}" y="${sy(v) + 4}" text-anchor="end" fill="${C.mute}">${spct(v)}</text>`; });
    nice(-xmax, xmax, 6).forEach((v) => { s += `<text x="${sx(v)}" y="${H - B + 16}" text-anchor="middle" fill="${C.mute}">${signed(v)}</text>`; });
    s += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${H - B}" stroke="${C.mute}"/><line x1="${L}" x2="${W - R}" y1="${sy(0)}" y2="${sy(0)}" stroke="${C.mute}"/>`;
    const qd = (x, y, t, a) => `<text x="${x}" y="${y}" text-anchor="${a}" fill="${C.mute}" font-style="italic" font-size="13">${t}</text>`;
    s += qd(W - R - 4, T + 14, 'Bought and rising', 'end') + qd(W - R - 4, H - B - 8, 'Bought while falling', 'end') + qd(L + 6, T + 14, 'Sold while rising', 'start') + qd(L + 6, H - B - 8, 'Sold and falling', 'start');
    s += `<text x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle" fill="${C.mute}">Comparable 13F managers in ${esc(qlabel(P[j]))}: added − cut${view === 'public_knowledge_asof' ? ' (filed before the decision day)' : ''}</text>`;
    s += `<text transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" fill="${C.mute}">Price, ${esc(V.y)}</text>`;
    const colour = (q) => (q[6] & 7 && !(q[6] & 24) ? C.buy : q[6] & 24 && !(q[6] & 7) ? C.sell : C.neu);
    const tipOf = (t, r, k, extra) => { const q = r[V.key][k], o = [q[V.off[0]], q[V.off[1]]];
      let x = `${t} ${r.name || ''} · ${jLabel(D, view, k)} (${V.short})\n${signed(q[0])} net comparable managers (${num(q[1])} added, ${num(q[2])} cut, ${num(q[3])} new positions) · est. net ${big(q[4])}\nMatched: ${q[8] == null ? '—' : q[8] + '%'} of the managers that held it the quarter before`;
      if (view === 'quarter_aligned') x += `${fin(q[9]) && q[9] !== q[0] ? ` · original count (every change on file): ${signed(q[9])}` : ''}\nPrice during the quarter: ${spct(q[5])}`;
      else x += `\nPrice, trailing 3 months to the decision day: ${spct(q[5])}\nNext 4 weeks vs SPY: ${q[9] == null ? 'pending' : spct(q[9], 1)} · next 12 weeks: ${q[10] == null ? 'pending' : spct(q[10], 1)}`;
      if (o[0] || o[1]) x += `\nOfficials (PTRs ${view === 'quarter_aligned' ? 'dated in the quarter' : 'filed in the 3 months before'}): ${num(o[0])} purchases, ${num(o[1])} sales`;
      return x + `\n${flagWords(q[6]).join(', ') || 'Not flagged'}${extra || ''}`; };
    trailSet.forEach((t) => {
      const pts = trail(t);
      if (pts.length < 2) return;
      const f = t === focus, pin = (st.pinned || []).includes(t);
      const d = pts.map(([, p], i) => (i ? 'L' : 'M') + sx(p.x).toFixed(1) + ',' + sy(p.y).toFixed(1)).join('');
      s += `<path d="${d}" fill="none" stroke="${f ? C.acc : C.ink}" stroke-width="${f ? 2.4 : pin ? 1.8 : 1.1}" opacity="${f ? 0.9 : pin ? 0.7 : 0.35}" marker-end="url(#hv-arrow)"/>`;
      pts.slice(0, -1).forEach(([k, p]) => { s += `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${f ? 3.2 : 2.2}" fill="${f ? C.acc : C.ink}" opacity="${f ? 0.8 : 0.35}"><title>${esc(t + ' · ' + qlabel(P[k]) + ': ' + signed(p.x) + ' managers, ' + spct(p.raw))}</title></circle>`;
        if (f || pin) s += `<text x="${sx(p.x) + 5}" y="${sy(p.y) - 5}" font-size="10" fill="${C.mute}">${esc(qlabel(P[k]).replace(' 20', " '"))}</text>`; });
    });
    if (st.show === 'left' || st.ghosts) left.forEach(([t, r]) => { const p = point(r, view, j);
      s += `<g data-hv="${esc(t)}" style="cursor:pointer"><circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="4.5" fill="none" stroke="${C.neu}" stroke-dasharray="2 2"><title>${esc(tipOf(t, r, j, '\nLeft the map: flagged in ' + qlabel(P[j - 1]) + ', not now'))}</title></circle></g>`; });
    const drawn = shown.slice();
    if (focus && !map.some(([t]) => t === focus) && point(D.rows[focus], view, j)) drawn.push([focus, D.rows[focus]]);
    const order = drawn.sort((a, b) => (a[1][V.key][j][7] - b[1][V.key][j][7]) || (isNew(a[1]) - isNew(b[1])));
    order.forEach(([t, r]) => {
      const p = point(r, view, j), q = r[V.key][j], h = q[7] >= 2, n = isNew(r), o = [q[V.off[0]], q[V.off[1]]];
      const cx = sx(p.x), cy = sy(p.y);
      s += `<g data-hv="${esc(t)}" style="cursor:pointer"><circle cx="${cx}" cy="${cy}" r="11" fill="transparent"/>` +
        (n ? `<circle cx="${cx}" cy="${cy}" r="${h ? 8.5 : 7.5}" fill="none" stroke="${C.acc}" stroke-width="2"/>` : '') +
        `<circle cx="${cx}" cy="${cy}" r="${h ? 5.2 : 4}" fill="${q[6] ? colour(q) : C.bg}" stroke="${q[6] ? C.bg : C.acc}" stroke-width="${q[6] ? 1 : 2}" opacity="${h ? 0.95 : 0.75}"><title>${esc(tipOf(t, r, j, n ? '\nNew on the map this quarter' : ''))}</title></circle>` +
        (st.off && o[0] ? `<path d="M${cx + 7} ${cy - 9}l3 3l-3 3l-3-3z" fill="${C.buy}" opacity=".85"><title>${esc(t + ': officials reported ' + o[0] + ' purchase' + (o[0] > 1 ? 's' : ''))}</title></path>` : '') +
        (st.off && o[1] ? `<path d="M${cx + 7} ${cy + 3}l3 3l-3 3l-3-3z" fill="${C.bg}" stroke="${C.sell}" stroke-width="1.2" opacity=".85"><title>${esc(t + ': officials reported ' + o[1] + ' sale' + (o[1] > 1 ? 's' : ''))}</title></path>` : '') + '</g>';
    });
    const boxes = [], lab = [];
    const want = [focus, ...(st.pinned || []), ...hot.map(([t]) => t), ...shown.filter(([, r]) => isNew(r)).sort((a, b) => Math.abs(b[1][V.key][j][0]) - Math.abs(a[1][V.key][j][0])).slice(0, 6).map(([t]) => t)];
    for (const t of want) {
      if (!t || lab.includes(t) || lab.length > 22) continue;
      const p = point(D.rows[t], view, j); if (!p) continue;
      const x = sx(p.x) + 12, y = sy(p.y) - 7, w = t.length * 7.2 + 4, b = [x, y - 11, x + w, y + 3];
      if (t !== focus && (b[2] > W - R || boxes.some((o) => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]))) continue;
      boxes.push(b); lab.push(t);
      s += `<text x="${x}" y="${y}" font-weight="700" font-size="${t === focus ? 14 : 12}" fill="${t === focus ? C.acc : C.ink}" paint-order="stroke" stroke="${C.bg}" stroke-width="3">${esc(t)}${isNew(D.rows[t]) ? ' ✦' : ''}</text>`;
    }
    if (focus && !point(D.rows[focus], view, j)) s += `<text x="${W - R - 4}" y="${T + 32}" text-anchor="end" fill="${C.acc}">${esc(focus)}: no comparable 13F change or price for ${esc(qlabel(P[j]))}</text>`;
    s += '</svg>';
    return { svg: s, map, left, isNew };
  }

  const quadOf = (q) => (!q || !fin(q[0]) || !fin(q[5]) ? null : q[0] === 0 || q[5] === 0 ? 'boundary' : q[0] > 0 ? (q[5] > 0 ? 'BR' : 'BF') : (q[5] > 0 ? 'SR' : 'SF'));
  const QUAD_WORD = { BR: 'Bought and rising', SR: 'Sold while rising', SF: 'Sold and falling', BF: 'Bought while falling', boundary: 'On an axis' };

  function render(el, opt) {
    opt = opt || {};
    const ticker = opt.ticker ? String(opt.ticker).toUpperCase().replace(/[./]/g, '-') : '';
    el.innerHTML = '<p class="muted">Loading the Hype map…</p>';
    return load(opt.hub).then((D) => {
      if (!D || !D.views || !D.rows) { el.innerHTML = '<p class="muted">The Hype map data is being rebuilt; try again after the next market build.</p>'; return; }
      const views = (opt.legacy ? ['legacy_snapshot'] : []).concat(Object.keys(VIEWS).filter((v) => quarters(D, v).length));
      if (!views.length) { el.innerHTML = '<p class="muted">No quarters on file yet.</p>'; return; }
      const st = { view: views.includes(opt.view) ? opt.view : views[0], j: 0, j0: 0, show: 'all', trails: ticker ? 'none' : 'labelled', ghosts: false, off: true, pinned: [], ticker };
      const lastOf = (v) => { const P = quarters(D, v); let k = P.length - 1; return k; };
      const setView = (v) => { st.view = v; if (VIEWS[v]) { st.j = lastOf(v); st.j0 = Math.max(0, st.j - 3); } };
      setView(st.view);
      const sel = (id, label, opts, v) => `<label style="display:inline-flex;flex-direction:column;gap:2px;font-size:12px;color:var(--muted,#777)">${label}<select data-hvc="${id}">${opts.map(([k, l]) => `<option value="${esc(k)}"${String(k) === String(v) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
      const vopts = views.map((v) => [v, v === 'legacy_snapshot' ? 'Legacy snapshot (original map)' : VIEWS[v].label]);
      function paint() {
        let h = `<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin:4px 0 8px">` + sel('view', 'View (clock)', vopts, st.view);
        if (st.view === 'legacy_snapshot') {
          const L = D.views.legacy_snapshot || {};
          h += `</div><p class="sub" style="margin:0 0 6px"><b>Mixed clocks.</b> X: net managers in ${L.report_quarter_end ? esc(qlabel(L.report_quarter_end)) + ` (every change on file, ${num(L.managers_filed)} managers)` : 'the latest well-covered report quarter (every change on file)'} · Y: each stock's trailing three months to its latest close${L.latest_close ? ' (' + esc(day(L.latest_close)) + ')' : ''}${L.signals_built_at ? ` · Signals built ${esc(L.signals_built_at.slice(0, 16).replace('T', ' '))} UTC` : ''}. The 13F quarter ended months before this price window: a picture of what is known now, not a quarter-to-quarter series — pick another view for that.</p>`;
          h += opt.legacy();
          h += `<div data-hv-tr style="margin-top:12px"></div>`;
          el.innerHTML = h; bind(); transitions('quarter_aligned'); return;
        }
        const V = VIEWS[st.view], P = quarters(D, st.view), j = st.j;
        const r = draw(el, D, st);
        const nNew = r.map.filter(([, x]) => r.isNew(x)).length;
        const row = ticker && D.rows[ticker];
        const qopts = P.map((p, k) => [k, jLabel(D, st.view, k)]);
        h += sel('j', 'Quarter', qopts, st.j) + sel('j0', 'Trails from', qopts.filter(([k]) => k <= st.j), Math.min(st.j0, st.j)) +
          sel('show', 'Show', [['all', 'Everything on the map'], ['new', 'New on the map only'], ['left', 'Left the map only']], st.show) +
          sel('trails', 'Trails', [['labelled', 'Labelled stocks'], ['all', 'Every stock shown'], ['none', 'Only pinned' + (ticker ? ' and ' + ticker : '')]], st.trails) +
          (opt.search !== false && !ticker ? `<label style="display:inline-flex;flex-direction:column;gap:2px;font-size:12px;color:var(--muted,#777)">Pin a ticker<input data-hvc="pin" placeholder="e.g. NVDA · Enter" style="width:120px"></label>` : '') +
          `<label style="font-size:12px;color:var(--muted,#777)"><input type="checkbox" data-hvc="ghosts"${st.ghosts ? ' checked' : ''}> show stocks that left the map</label>` +
          `<label style="font-size:12px;color:var(--muted,#777)"><input type="checkbox" data-hvc="off"${st.off ? ' checked' : ''}> officials' trades (◆ ◇)</label></div>`;
        h += `<p class="sub" style="margin:0 0 4px">${clockLine(D, st.view, j)}</p>`;
        h += `<p class="sub" style="margin:0 0 6px">${esc(jLabel(D, st.view, j))}: <b>${num(r.map.length)}</b> stocks on the map · <b>${num(nNew)}</b> new on it (ringed, ✦) · <b>${num(r.left.length)}</b> left it since ${j ? esc(qlabel(P[j - 1])) : 'the quarter before'}. Trails run ${esc(qlabel(P[Math.min(st.j0, j)]))} → ${esc(qlabel(P[j]))} within this view; click a dot to pin or unpin its trail.</p>`;
        h += r.svg;
        const pal = palette(el);
        h += `<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted,#777);margin-top:4px"><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${pal.buy}"></i> buy-side 13F flags</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${pal.sell}"></i> sell-side 13F flags</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;border:2px solid ${pal.acc}"></i> new on the map</span><span style="color:${pal.buy}">◆</span><span>officials' purchases</span><span style="color:${pal.sell}">◇</span><span>officials' sales (PTRs; a separate source)</span><span>price shown clipped to −60% … +120% (data unclipped)</span></div>`;
        if ((st.pinned || []).length) h += `<p class="sub">Pinned: ${st.pinned.map((t) => `<button type="button" data-hvu="${esc(t)}" style="cursor:pointer">${esc(t)} ×</button>`).join(' ')}</p>`;
        if (row && row[V.key]) {
          const pa = st.view === 'public_knowledge_asof';
          h += `<table class="fv-tbl" style="width:100%;margin-top:8px;font-size:13px"><thead><tr><th>Quarter</th><th style="text-align:right">Net comparable managers</th><th style="text-align:right">Added / cut</th><th style="text-align:right">Matched</th><th style="text-align:right">Est. net $</th><th style="text-align:right">${pa ? 'Trailing 3 months' : 'Price in quarter'}</th>${pa ? '<th style="text-align:right">Next 4w vs SPY</th><th style="text-align:right">Next 12w vs SPY</th>' : '<th style="text-align:right">Original count</th>'}<th>Quadrant</th><th>On the map</th></tr></thead><tbody>` +
            P.map((p, k) => { const q = row[V.key][k]; if (!q) return `<tr><td>${esc(jLabel(D, st.view, k))}</td><td colspan="${pa ? 9 : 8}" class="muted">no comparable 13F change on file</td></tr>`;
              const was = k > 0 && row[V.key][k - 1] && row[V.key][k - 1][6];
              return `<tr${k === st.j ? ' style="font-weight:600"' : ''}><td>${esc(jLabel(D, st.view, k))}</td><td style="text-align:right">${signed(q[0])}</td><td style="text-align:right">${num(q[1])} / ${num(q[2])}</td><td style="text-align:right">${q[8] == null ? '—' : q[8] + '%'}</td><td style="text-align:right">${big(q[4])}</td><td style="text-align:right">${spct(q[5])}</td>` +
                (pa ? `<td style="text-align:right">${q[9] == null ? '<span class="muted">pending</span>' : spct(q[9], 1)}</td><td style="text-align:right">${q[10] == null ? '<span class="muted">pending</span>' : spct(q[10], 1)}</td>` : `<td style="text-align:right">${signed(q[9])}</td>`) +
                `<td>${esc(QUAD_WORD[quadOf(q)] || '—')}</td><td>${q[6] ? (k > 0 && !was ? '<b>New</b> · ' : '') + esc(flagWords(q[6]).join(', ')) : (was ? '<span class="muted">left the map</span>' : '<span class="muted">—</span>')}</td></tr>`; }).reverse().join('') + '</tbody></table>';
        } else if (ticker) h += `<p class="sub">${esc(ticker)} has had no 13F flag or comparable change on file in these quarters.</p>`;
        const th = (D.views[st.view] || {}).thresholds || [];
        h += `<details style="margin-top:8px"><summary>How this view is built</summary><p class="sub">${esc((D.views[st.view] || {}).note || '')} ${esc(D.note || '')} Flag thresholds per quarter (crowded = net managers, new money = new positions): ${th.map((c, k) => `${esc(qlabel(P[k]))} ${num(c.crowd_net_managers)} / ${num(c.new_positions)}`).join(' · ')}. Prices: ${esc(D.price_basis || '')}.</p></details>`;
        h += `<div data-hv-tr style="margin-top:12px"></div>`;
        el.innerHTML = h;
        bind();
        const q = row && row[V.key] && row[V.key][st.j];
        transitions(V.audit, quadOf(q));
      }
      function transitions(view, quad) {
        const box = el.querySelector('[data-hv-tr]');
        if (!box || opt.transitions === false) return;
        const go = () => window.CrowdTransitions && window.CrowdTransitions.render(box, { hub: opt.hub, view, ticker, quad, compact: !!ticker });
        if (window.CrowdTransitions) go();
        else if (typeof document !== 'undefined') {
          const sc = document.createElement('script');
          sc.src = (opt.hub || '') + 'transition-matrix.js'; sc.onload = go; document.head.appendChild(sc);
        }
      }
      function bind() {
        el.querySelectorAll('[data-hvc]').forEach((c) => {
          const k = c.dataset.hvc;
          if (k === 'pin') { c.onkeydown = (e) => { if (e.key !== 'Enter') return; const t = c.value.trim().toUpperCase().replace(/[./]/g, '-'); if (D.rows[t] && !st.pinned.includes(t)) { st.pinned.push(t); paint(); } else c.style.outline = '2px solid #c0392b'; }; return; }
          c.onchange = () => { if (k === 'view') { setView(c.value); if (opt.onview) opt.onview(c.value); } else st[k] = (k === 'ghosts' || k === 'off') ? c.checked : (k === 'j' || k === 'j0') ? +c.value : c.value; if (k === 'j' && st.j0 > st.j) st.j0 = st.j; paint(); };
        });
        el.querySelectorAll('[data-hv]').forEach((g) => { g.onclick = () => { const t = g.dataset.hv; if (t === ticker) return; const i = st.pinned.indexOf(t); if (i >= 0) st.pinned.splice(i, 1); else st.pinned.push(t); paint(); }; });
        el.querySelectorAll('[data-hvu]').forEach((b) => { b.onclick = () => { st.pinned = st.pinned.filter((t) => t !== b.dataset.hvu); paint(); }; });
      }
      paint();
    }).catch((e) => { el.innerHTML = `<p class="muted">The Hype map could not load (${esc(e.message)}).</p>`; });
  }
  if (typeof window !== 'undefined') window.HypeView = { render, draw, load, point, quadOf, VIEWS };
})();
