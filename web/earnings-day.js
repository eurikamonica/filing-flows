/* Earnings day: the home page's picture of one day's filings, from data/index.json only.
   - how each sector's revenue grew (the median year-on-year change of the companies that filed that day),
   - growth against operating margin for the day's largest reporters (dot size = quarterly revenue),
   - the largest reporters as a table.
   A day picker covers the last week (filing dates on EDGAR, in the reader's own time zone, as the daily report).
   window.FFEarningsDay.mount(box, ix); summarize(ix, day) is the arithmetic, also run by tests/test_earnings_day.cjs. */
(function (root) {
  'use strict';
  const ENT = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };
  const dec = (s) => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, (m) => ENT[m]);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const t = (s) => esc(dec(s));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const sgn = (v, d) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}%`;
  function money(v) {
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    return a >= 0.95e12 ? `${s}$${(a / 1e12).toFixed(2)}T` : a >= 0.95e9 ? `${s}$${(a / 1e9).toFixed(1)}B` : `${s}$${(a / 1e6).toFixed(0)}M`;
  }
  const localISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

  // the filings of one day: the same entries as the daily report (pipeline/notify.py entries_for_day)
  function entries(ix, day) {
    const out = [], seen = new Set();
    (ix.companies || []).forEach((e) => {
      const found = [];
      if (e.filed === day || e.after_release === day) found.push(e);
      (e.also || []).forEach((a) => { if (a.filed === day) found.push(Object.assign({}, e, a, { prelim: a.form === '8-K' })); });
      found.forEach((x) => { const k = `${x.cik}:${x.end}:${x.form}`; if (!seen.has(k)) { seen.add(k); out.push(x); } });
    });
    return out;
  }
  const median = (xs) => { const v = xs.slice().sort((a, b) => a - b), n = v.length; return n ? (n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2) : null; };

  function summarize(ix, day, opt) {
    opt = opt || {};
    const E = entries(ix, day), names = ix.sector_names || {};
    const by = new Map();
    E.forEach((e) => { if (fin(e.yoy) && e.sector) { if (!by.has(e.sector)) by.set(e.sector, []); by.get(e.sector).push(+e.yoy); } });
    const sectors = [...by].map(([id, v]) => ({ id, name: dec(names[id] || id), n: v.length, median: median(v) }))
      .sort((a, b) => b.median - a.median);
    const big = E.filter((e) => fin(e.revenue) && e.revenue > 0).sort((a, b) => b.revenue - a.revenue);
    const dots = big.filter((e) => fin(e.yoy) && fin(e.om)).slice(0, opt.dots || 60);
    return { day, count: E.length, sectors, dots, top: big.slice(0, opt.top || 12) };
  }

  // a light-to-mid green: dark text stays readable on every step (contrast ≥ 7:1 on the darkest)
  function heat(v, hi) {
    const k = Math.max(0, Math.min(1, v / (hi || 30))), a = [241, 246, 242], b = [127, 191, 154];
    return '#' + a.map((x, i) => Math.round(x + (b[i] - x) * k).toString(16).padStart(2, '0')).join('');
  }

  function scatter(dots) {
    if (dots.length < 3) return '<p class="ed-empty">Too few companies with both figures that day for the chart.</p>';
    const W = 760, H = 330, L = 52, R = 748, T = 12, B = 290;
    const xs = dots.map((d) => +d.yoy).sort((a, b) => a - b), ys = dots.map((d) => +d.om).sort((a, b) => a - b);
    const q = (v, p) => v[Math.min(v.length - 1, Math.max(0, Math.round(p * (v.length - 1))))];
    const step = 20, lo = (v, m) => Math.floor(Math.min(m, v) / step) * step, hi = (v, m) => Math.ceil(Math.max(m, v) / step) * step;
    const x0 = lo(q(xs, 0.03), -10), x1 = hi(q(xs, 0.97), 40), y0 = lo(q(ys, 0.03), 0), y1 = hi(q(ys, 0.97), 40);
    const px = (v) => L + (Math.max(x0, Math.min(x1, v)) - x0) / (x1 - x0) * (R - L);
    const py = (v) => B - (Math.max(y0, Math.min(y1, v)) - y0) / (y1 - y0) * (B - T);
    let g = '';
    for (let v = x0; v <= x1; v += step) g += `<line class="${v === 0 ? 'zero' : 'grid'}" x1="${px(v)}" y1="${T}" x2="${px(v)}" y2="${B}"/><text class="tick" x="${px(v)}" y="${B + 16}" text-anchor="middle">${v > 0 ? '+' : ''}${v}%</text>`;
    for (let v = y0; v <= y1; v += step) g += `<line class="${v === 0 ? 'zero' : 'grid'}" x1="${L}" y1="${py(v)}" x2="${R}" y2="${py(v)}"/><text class="tick" x="${L - 6}" y="${py(v) + 4}" text-anchor="end">${v}%</text>`;
    const maxR = Math.sqrt(dots[0].revenue);
    const pts = dots.map((d) => ({ d, x: px(+d.yoy), y: py(+d.om), r: Math.max(3, Math.sqrt(d.revenue) / maxR * 18) }));
    const circles = pts.slice().reverse().map((p) => `<a href="#c-${+p.d.cik}" aria-label="${t(p.d.ticker || p.d.name)}: revenue ${money(p.d.revenue)}, ${sgn(+p.d.yoy, 1)} Y/Y, operating margin ${(+p.d.om).toFixed(1)}%">` +
      `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${p.r.toFixed(1)}"><title>${t(p.d.ticker || p.d.name)} · ${money(p.d.revenue)} · ${sgn(+p.d.yoy, 1)} Y/Y · ${(+p.d.om).toFixed(1)}% margin</title></circle></a>`).join('');
    // labels: the largest first, then the most extreme, never on top of one another
    const placed = pts.map((p) => [p.x - p.r * 0.7, p.y - p.r * 0.7, p.x + p.r * 0.7, p.y + p.r * 0.7]), want = pts.slice(0, 8).concat(pts.slice(8).sort((a, b) => Math.abs(b.d.yoy) + Math.abs(b.d.om) - Math.abs(a.d.yoy) - Math.abs(a.d.om)).slice(0, 6));
    let labels = '';
    want.forEach((p, k) => {
      const s = String(p.d.ticker || '').slice(0, 6);
      if (!s) return;
      const w = s.length * 7.6 + 2, x = p.x + p.r + 3 + w > R ? p.x - p.r - 3 - w : p.x + p.r + 3, y = p.y + 4;
      const box = [x, y - 11, x + w, y + 2], own = pts.indexOf(p);
      // the four largest may sit over a small dot; every label stays clear of the other labels
      if (placed.some((b, i) => i !== own && (k >= 4 || i >= pts.length) && !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) return;
      placed.push(box);
      labels += `<text class="lbl" x="${x.toFixed(1)}" y="${y.toFixed(1)}">${t(s)}</text>`;
    });
    return `<svg class="ed-scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="Revenue growth against operating margin for the ${dots.length} largest companies that filed">
      ${g}${circles}${labels}<text class="axis" x="${(L + R) / 2}" y="${H - 6}" text-anchor="middle">Revenue growth, year on year</text>
      <text class="axis" x="14" y="${(T + B) / 2}" text-anchor="middle" transform="rotate(-90 14 ${(T + B) / 2})">Operating margin</text></svg>`;
  }

  function render(el, S) {
    if (!S.count) { el.innerHTML = '<p class="ed-empty">No earnings filings on this day yet.</p>'; return; }
    const hi = Math.max(30, ...S.sectors.map((s) => s.median));
    el.innerHTML = `<div class="ed">
      <div class="ed-col">
        <section class="ed-card"><div class="ed-head"><h3>How each sector's revenue grew</h3><span class="muted">median year-on-year change of the companies that filed</span></div>
          ${S.sectors.length ? `<div class="ed-sectors">${S.sectors.map((s) => `<a class="ed-sec" href="#s-${esc(s.id)}" style="background:${heat(s.median, hi)}"><small>${t(s.name)}</small><b>${sgn(s.median, 1)}</b><span>${s.n} compan${s.n === 1 ? 'y' : 'ies'}</span></a>`).join('')}</div>
          <div class="ed-key"><span>+0%</span><i></i><span>+${Math.round(hi)}% or more</span></div>` : '<p class="ed-empty">No year-on-year figures among this day\'s filings.</p>'}</section>
        <section class="ed-card"><div class="ed-head"><h3>Growth vs operating margin</h3><span class="muted">the ${S.dots.length} largest reporters · dot size = quarterly revenue · click a dot for its chart</span></div>${scatter(S.dots)}</section>
      </div>
      <section class="ed-card"><div class="ed-head"><h3>Largest reporters</h3><span class="muted">by quarterly revenue</span></div>
        <div class="tbl-wrap"><table class="ed-top"><thead><tr><th>Company</th><th class="num">Revenue</th><th class="num">Y/Y</th><th class="num">Op. margin</th><th>Filing</th></tr></thead><tbody>
        ${S.top.map((e) => `<tr><td><a href="#c-${+e.cik}">${t(e.ticker || '')}</a> <span class="nm">${t(e.name)}</span></td><td class="num">${money(e.revenue)}</td>
          <td class="num ${fin(e.yoy) ? (e.yoy >= 0 ? 'pos' : 'neg') : ''}">${fin(e.yoy) ? sgn(+e.yoy, 1) : '—'}</td><td class="num">${fin(e.om) ? (+e.om).toFixed(1) + '%' : '—'}</td>
          <td><span class="mono">${t(e.form)}</span>${e.prelim ? ' <span class="tag prelim">prelim</span>' : ''}</td></tr>`).join('')}</tbody></table></div>
        <p class="ed-empty"><a href="#home" data-ed-all>All ${S.count} filings of the day, with filters ↓</a></p></section>
    </div>`;
  }

  function mount(box, ix, opt) {
    if (!box || !ix) return null;
    opt = opt || {};
    const now = opt.now || new Date();
    const days = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i), iso = localISO(d);
      days.push({ iso, i, n: entries(ix, iso).length, name: i === 0 ? 'Today' : i === 1 ? 'Yesterday' : d.toLocaleDateString('en-US', { weekday: 'short' }),
        short: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) });
    }
    let pick = (days.find((d) => d.n) || days[1]).iso;
    box.innerHTML = `<div class="section-head"><h2>Earnings day</h2><span class="muted">What the companies that filed reported, read from their filings</span></div>
      <div class="days" role="radiogroup" aria-label="Filing date">${days.map((d) => `<button type="button" class="day${d.iso === pick ? ' on' : ''}" role="radio"
        aria-checked="${d.iso === pick}" data-ed-day="${d.iso}" ${d.n ? '' : 'disabled'}><b>${d.name}</b><span>${d.short}</span><span class="n">${d.n ? `${d.n} filing${d.n === 1 ? '' : 's'}` : 'none yet'}</span></button>`).join('')}</div>
      <div data-ed-body></div>`;
    const body = box.querySelector('[data-ed-body]');
    const draw = () => {
      render(body, summarize(ix, pick));
      const all = body.querySelector('[data-ed-all]');
      if (all && opt.onAll) all.addEventListener('click', (ev) => { ev.preventDefault(); opt.onAll(pick); });
    };
    box.querySelectorAll('[data-ed-day]').forEach((b) => b.addEventListener('click', () => {
      pick = b.dataset.edDay;
      box.querySelectorAll('[data-ed-day]').forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-checked', String(x === b)); });
      draw();
      if (opt.onDay) opt.onDay(pick);
    }));
    draw();
    if (opt.onDay) opt.onDay(pick);
    return { pick: () => pick };
  }

  root.FFEarningsDay = { mount, summarize, entries, median, heat };
  if (typeof module !== 'undefined') module.exports = root.FFEarningsDay;
})(typeof globalThis !== 'undefined' ? globalThis : this);
