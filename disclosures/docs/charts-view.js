/* More charts — one company's latest quarter seen four more ways (the "More charts" view of each company page, listed in
   views.json): the margin ladder (gross, operating and net margin this quarter against the last one and a year ago),
   a Marimekko of its revenue lines (width: revenue, height: growth), and its rank among the largest companies of its
   industry quarter by quarter (revenue or operating margin, from the hub's leaderboard panels).
   window.MoreChartsView.render(el, {company, cik, hub, here}) — company: the site's data/c/<cik>.json, already loaded. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? '$' + (a / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(0) + 'M' : '$' + Math.round(a).toLocaleString('en-US')); };
  const pc = (v, d = 1) => (fin(v) ? (v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—');
  const pts = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(1) + ' pts' : '—');
  const PAL = ['#3b6fb6', '#e07b39', '#4f9d69', '#b5487a', '#8a6fc4', '#c9a227', '#2e9fa8', '#a35a3a', '#6b7d93', '#d2595f', '#5c8a2f', '#9b6bb0'];
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.mc{display:grid;gap:14px}.mc .mc-card{border:1px solid var(--line,#d0d5dd);border-radius:8px;padding:12px 14px;min-width:0}
.mc h3{margin:0 0 4px;font-size:1rem}.mc .mc-sub{font-size:.84rem;opacity:.8;margin:0 0 8px}.mc svg{display:block;width:100%;height:auto;max-width:820px}
.mc .mc-seg{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 8px}.mc .mc-seg button{border:1px solid var(--line,#d0d5dd);background:transparent;border-radius:999px;padding:3px 10px;cursor:pointer;color:inherit;font:inherit;font-size:.82rem}
.mc .mc-seg button.on{background:var(--ink,#1d1d1b);color:var(--paper,#fff)}.mc .muted{opacity:.75;font-size:.82rem}.mc .mc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}`;
    document.head.appendChild(s);
  }
  const node = (q, id) => (q.nodes || []).find((n) => n.id === id);

  // ---- the margin ladder: three rungs, a dot a period, the move in points
  function ladder(q) {
    const rev = node(q, 'revenue');
    if (!rev || !rev.v) return '';
    const rungs = [['gp', 'Gross margin'], ['oi', 'Operating margin'], ['net', 'Net margin']].map(([id, lab]) => {
      const n = node(q, id);
      if (!n) return null;
      const m = (k) => (fin(n[k]) && fin(rev[k]) && rev[k] ? n[k] / rev[k] : null);
      return { lab, v: m('v'), q: m('q'), y: m('y') };
    }).filter((r) => r && fin(r.v));
    if (!rungs.length) return '';
    const all = rungs.flatMap((r) => [r.v, r.q, r.y]).filter(fin), lo = Math.min(0, ...all), hi = Math.max(...all, 0.05);
    const W = 640, L = 130, R = 20, rowH = 54, H = rungs.length * rowH + 40, X = (v) => L + (v - lo) / ((hi - lo) || 1) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Margin ladder">`;
    [0, 0.25, 0.5, 0.75, 1].map((f) => lo + f * (hi - lo)).forEach((v) => { s += `<line x1="${X(v)}" x2="${X(v)}" y1="18" y2="${H - 20}" stroke="currentColor" stroke-opacity=".12"/><text x="${X(v)}" y="${H - 6}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".7">${pc(v, 0)}</text>`; });
    rungs.forEach((r, i) => {
      const y = 30 + i * rowH;
      s += `<text x="${L - 10}" y="${y + 4}" font-size="12" text-anchor="end" fill="currentColor">${esc(r.lab)}</text><line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="currentColor" stroke-opacity=".2"/>`;
      if (fin(r.y)) s += `<line x1="${X(r.y)}" x2="${X(r.v)}" y1="${y}" y2="${y}" stroke="${r.v >= r.y ? '#17734a' : '#b42318'}" stroke-width="5" stroke-opacity=".45"/>`;
      [['y', '#9aa4b2', 'a year ago'], ['q', '#e07b39', 'last quarter'], ['v', '#1d1d1b', 'this quarter']].forEach(([k, col, nm]) => { if (fin(r[k])) s += `<circle cx="${X(r[k])}" cy="${y}" r="${k === 'v' ? 7 : 5}" fill="${col}"><title>${esc(r.lab)}, ${nm}: ${pc(r[k])}</title></circle>`; });
      s += `<text x="${X(r.v)}" y="${y - 12}" font-size="11" text-anchor="middle" fill="currentColor"><tspan font-weight="600">${pc(r.v)}</tspan> · Y/Y ${pts(fin(r.y) ? r.v - r.y : null)} · Q/Q ${pts(fin(r.q) ? r.v - r.q : null)}</text>`;
    });
    s += `<circle cx="${L}" cy="10" r="4" fill="#9aa4b2"/><text x="${L + 8}" y="13" font-size="10" fill="currentColor">a year ago</text><circle cx="${L + 90}" cy="10" r="4" fill="#e07b39"/><text x="${L + 98}" y="13" font-size="10" fill="currentColor">last quarter</text><circle cx="${L + 190}" cy="10" r="5" fill="#1d1d1b"/><text x="${L + 198}" y="13" font-size="10" fill="currentColor">${esc(q.label)}</text></svg>`;
    return `<div class="mc-card"><h3>Margin ladder</h3><p class="mc-sub">Each rung is a margin of revenue: where it stood a year ago, last quarter and in ${esc(q.label)}. Green: up on the year; red: down.</p>${s}</div>`;
  }

  // ---- revenue lines as a Marimekko: width ∝ revenue, height = growth on the year
  function marimekko(q) {
    const lines = (q.nodes || []).filter((n) => n.col === 0 && /^L:/.test(n.id) && fin(n.v) && n.v > 0);
    if (lines.length < 2) return '';
    const tot = lines.reduce((a, n) => a + n.v, 0);
    const G = lines.map((n) => ({ name: n.name, v: n.v, g: fin(n.y) && n.y > 0 ? n.v / n.y - 1 : null, add: fin(n.y) ? n.v - n.y : null })).sort((a, b) => b.v - a.v);
    const gs = G.map((x) => x.g).filter(fin), gmax = Math.max(0.05, ...gs.map(Math.abs));
    const W = 720, H = 300, L = 46, R = 10, T = 20, B = 74, mid = T + (H - T - B) / 2, Yh = (g) => g / gmax * (H - T - B) / 2;
    let x = L, s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Revenue lines: share of revenue and growth">`;
    s += `<line x1="${L}" x2="${W - R}" y1="${mid}" y2="${mid}" stroke="currentColor" stroke-opacity=".5"/><text x="${L - 6}" y="${mid - Yh(gmax) + 4}" font-size="10" text-anchor="end" fill="currentColor">${pc(gmax, 0)}</text><text x="${L - 6}" y="${mid + 4}" font-size="10" text-anchor="end" fill="currentColor">0%</text><text x="${L - 6}" y="${mid + Yh(gmax) + 4}" font-size="10" text-anchor="end" fill="currentColor">−${pc(gmax, 0)}</text>`;
    G.forEach((n, i) => {
      const w = n.v / tot * (W - L - R), g = fin(n.g) ? n.g : 0, h = Math.abs(Yh(g)), y = g >= 0 ? mid - h : mid;
      s += `<rect x="${x + 1}" y="${y}" width="${Math.max(1, w - 2)}" height="${Math.max(1.5, h)}" fill="${PAL[i % PAL.length]}" fill-opacity="${fin(n.g) ? 0.85 : 0.3}"><title>${esc(n.name)}: ${big(n.v)} (${pc(n.v / tot, 0)} of revenue), ${fin(n.g) ? pc(n.g) + ' on the year' : 'no year-ago figure'}</title></rect>`;
      if (w > 34) s += `<text x="${x + w / 2}" y="${g >= 0 ? y - 4 : y + h + 12}" font-size="10" text-anchor="middle" fill="currentColor">${fin(n.g) ? pc(n.g, 0) : '—'}</text>`;
      if (w > 46) s += `<text transform="translate(${x + w / 2},${H - B + 10}) rotate(35)" font-size="10" fill="currentColor">${esc(String(n.name).slice(0, 22))}</text>`;
      x += w;
    });
    s += '</svg>';
    const top = G.filter((n) => fin(n.add)).sort((a, b) => b.add - a.add)[0];
    return `<div class="mc-card"><h3>Revenue lines: size and growth</h3><p class="mc-sub">Each block's width is its share of ${esc(q.label)} revenue (${big(tot)}), its height its growth on the year. ${top && top.add > 0 ? `The most added: ${esc(top.name)}, ${big(top.add)}.` : ''}</p>${s}
      <p class="muted">The revenue lines the company tags in its own XBRL (products, services, segments or regions — whichever it reports).</p></div>`;
  }

  // ---- rank among the industry's largest, quarter by quarter (the hub's leaderboard panels)
  const PANEL = {};
  const panel = (hub, name) => PANEL[hub + name] || (PANEL[hub + name] = fetch(`${hub}data/market/history/rank/${name}.json`).then((r) => (r.ok ? r.json() : null)).then((d) => (d && Array.isArray(d.rows) ? d.rows : d)).catch(() => null));
  let SITE = null;
  const siteIndex = () => SITE || (SITE = fetch('data/index.json').then((r) => (r.ok ? r.json() : null)).catch(() => null));
  const at = (row, i) => (row && row.length > 1 && i >= row[0] && i < row[0] + row.length - 1 ? row[1 + i - row[0]] : null);
  async function bump(el, c, hub, state) {
    const [meta, rev, oi, ix] = await Promise.all([panel(hub, 'meta'), panel(hub, 'q-rev'), panel(hub, 'q-oi'), siteIndex()]);
    if (!meta || !Array.isArray(meta.cos) || !Array.isArray(rev)) { el.innerHTML = '<p class="muted">The leaderboard panels are not published yet.</p>'; return; }
    const tk = String(((c.profile || {}).tickers || [])[0] || '').toUpperCase().replace(/\./g, '-'), sic = String((c.profile || {}).sic || '');
    const me = meta.cos.findIndex((x) => x[0] === tk);
    if (me < 0) { el.innerHTML = '<p class="muted">This company is not in the leaderboard panels.</p>'; return; }
    const sicOf = new Map(((ix && ix.companies) || []).map((x) => [String(x.ticker || '').toUpperCase().replace(/\./g, '-'), String(x.sic || '')]));
    const Q = meta.quarters || [], nq = Q.length, ttm = (row, q) => { let s = 0; for (let j = q - 3; j <= q; j++) { const v = at(row, j); if (!fin(v)) return null; s += v; } return s; };
    const last = (() => { for (let q = nq - 1; q >= 4; q--) if (fin(ttm(rev[me], q))) return q; return -1; })();
    if (last < 0) { el.innerHTML = '<p class="muted">Not enough quarters on file.</p>'; return; }
    let group = sic.slice(0, 3), peers = meta.cos.map((x, i) => i).filter((i) => (sicOf.get(meta.cos[i][0]) || '').slice(0, 3) === group && group);
    let gname = `SIC ${group}${(c.profile || {}).industry ? ' · ' + c.profile.industry : ''}`;
    if (peers.length < 5) { peers = meta.cos.map((x, i) => i).filter((i) => meta.cos[i][2] === meta.cos[me][2]); gname = (meta.sectors || {})[meta.cos[me][2]] || meta.cos[me][2]; }
    const size = (i) => ttm(rev[i], last) || 0;
    const pick = peers.filter((i) => size(i) > 0).sort((a, b) => size(b) - size(a)).slice(0, 10);
    if (!pick.includes(me)) { pick.pop(); pick.push(me); }
    const qs = []; for (let q = Math.max(3, last - 11); q <= last; q++) qs.push(q);
    const val = (i, q) => { const r = ttm(rev[i], q); if (state.m === 'rev') return r; const o = Array.isArray(oi) ? ttm(oi[i], q) : null; return fin(r) && fin(o) && r > 0 ? o / r : null; };
    const ranks = qs.map((q) => { const L = pick.map((i) => [i, val(i, q)]).filter((x) => fin(x[1])).sort((a, b) => b[1] - a[1]); return new Map(L.map(([i], k) => [i, k + 1])); });
    const n = pick.length, W = 760, H = 46 + n * 30, Lm = 54, Rm = 150, T = 24, X = (k) => Lm + k / Math.max(1, qs.length - 1) * (W - Lm - Rm), Y = (r) => T + (r - 1) * 30;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Rank in the industry by quarter">`;
    qs.forEach((q, k) => { if (k % 2 === 0 || k === qs.length - 1) s += `<text x="${X(k)}" y="${H - 6}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".7">${esc(Q[q] || '')}</text>`; });
    for (let r = 1; r <= n; r++) s += `<text x="${Lm - 12}" y="${Y(r) + 4}" font-size="10" text-anchor="end" fill="currentColor" opacity=".6">#${r}</text>`;
    pick.forEach((i, j) => {
      const isMe = i === me, col = isMe ? '#b42318' : PAL[j % PAL.length];
      const pts2 = qs.map((q, k) => (ranks[k].has(i) ? [X(k), Y(ranks[k].get(i))] : null));
      let d = '', pen = false;
      pts2.forEach((p) => { if (!p) { pen = false; return; } d += (pen ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1); pen = true; });
      s += `<path d="${d}" fill="none" stroke="${col}" stroke-width="${isMe ? 4 : 2}" stroke-opacity="${isMe ? 1 : 0.55}"/>`;
      pts2.forEach((p) => { if (p) s += `<circle cx="${p[0]}" cy="${p[1]}" r="${isMe ? 4.5 : 3}" fill="${col}"/>`; });
      const lp = pts2.filter(Boolean).pop();
      if (lp) s += `<text x="${lp[0] + 10}" y="${lp[1] + 4}" font-size="11" font-weight="${isMe ? 700 : 400}" fill="${col}">${esc(meta.cos[i][0])} ${state.m === 'rev' ? big(val(i, last)) : pc(val(i, last))}</text>`;
    });
    s += '</svg>';
    el.innerHTML = `<p class="mc-sub">The ${n} largest companies of ${esc(gname)} by revenue over the last four quarters, ranked each quarter by ${state.m === 'rev' ? 'trailing-four-quarter revenue' : 'trailing-four-quarter operating margin'}. ${esc(tk)} in red.</p>${s}
      <p class="muted">Calendar quarters from the companies' XBRL filings; today's companies only.</p>`;
  }

  async function render(el, opt) {
    css();
    const c = opt && opt.company, hub = (opt && opt.hub) || '';
    const q = c && (c.quarters || []).find((x) => /^Q/i.test(x.label || '') && (x.nodes || []).length);
    if (!q) { el.innerHTML = '<p class="muted">No detailed quarter on file for this company.</p>'; return; }
    const state = { m: 'rev' };
    el.innerHTML = `<div class="mc"><div class="mc-grid">${ladder(q)}${marimekko(q)}</div>
      <div class="mc-card"><h3>Rank in its industry, quarter by quarter</h3><div class="mc-seg" role="group" aria-label="Rank by"><button type="button" data-mcm="rev" class="on">Revenue</button><button type="button" data-mcm="om">Operating margin</button></div><div data-mcbump><p class="muted">Loading the leaderboard panels…</p></div></div>
      <p class="muted">From the company's filings (XBRL). The earnings Sankey, the profit bridge and EPS bridge are on the Earnings and Profit &amp; cash tabs.</p></div>`;
    const box = el.querySelector('[data-mcbump]');
    const draw = () => bump(box, c, hub, state).catch((e) => { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; });
    el.querySelectorAll('[data-mcm]').forEach((b) => b.addEventListener('click', () => { state.m = b.dataset.mcm; el.querySelectorAll('[data-mcm]').forEach((x) => x.classList.toggle('on', x === b)); box.innerHTML = '<p class="muted">Ranking…</p>'; draw(); }));
    draw();
  }
  window.MoreChartsView = { render };
})();
