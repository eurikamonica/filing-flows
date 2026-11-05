/* Moving averages+ — the usual moving averages of a share price with the company's earnings and its own guidance mixed
   in, weighted, and what that mix has been worth (app/ma_hybrid.py, branch rotation-history).
   · A company: its weekly close of the last five years, the 10- and 40-week averages (the weekly 50- and 200-day lines), the
     earnings line (trailing EPS × its own five-year median P/E) and the hybrid line H = MA40^(1−w) × earnings line^w ×
     (1 + g × guidance) — w and g picked here; guidance releases marked (▲ raised, ▼ lowered, ● kept); what "above the line"
     paid for the chosen weights since 2016, against the 40-week average alone; the models' rank of the company this week.
   · The hub (Rotation → Chart → Moving averages+): the tests — the models (moving averages alone, + fundamentals, +
     guidance), the classic rules, every weight on the grid and the pick made each year, what followed each kind of guidance
     release — the companies furthest from the line, and any ticker's chart.
   Data: data/market/history/ma-hybrid.json, ma-hybrid-rows.json, ma/<TICKER>.json. Self-contained: the main site's company
   page (views.json "mahybrid") and the hub use it, colours from the host's CSS variables.
   window.MAHybridView.render(el, {ticker, hub}) · .renderHub(el, {hub}). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v) => (fin(v) ? '$' + num(v, v >= 1000 ? 0 : v >= 1 ? 2 : 4) : '—');
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const gap = (lp) => (fin(lp) ? spct(Math.exp(lp) - 1) : '—');                 // a log distance as a percentage
  const store = {};
  const get = (u) => store[u] || (store[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .catch((e) => { delete store[u]; throw e; }));
  const COL = { p: 'var(--ink, #222)', m10: 'var(--rot-1, #2a78d6)', m40: 'var(--slate, #5b7fa6)', el: 'var(--q-warm, #d9822b)', h: 'var(--accent, #17734a)',
    up: 'var(--mk-profit, #17734a)', down: 'var(--mk-cost, #c0392b)', mute: 'var(--muted, #888)', line: 'var(--line, #e3e3e3)' };
  const WS = [0, 0.25, 0.5, 0.75, 1], GS = [0, 0.05, 0.1];
  const MODEL_ORDER = ['ma', 'ma_fund', 'hybrid'];
  const GLAB = { raised: 'raised', lowered: 'lowered', withdrawn: 'withdrawn', reaffirmed: 'kept', updated: 'updated', initiated: 'first given', narrowed: 'narrowed', mixed: 'mixed', widened: 'widened' };
  const GDIR = { raised: 1, lowered: -1, withdrawn: -1 };
  const ui = { w: null, g: null };

  function css() {
    if (typeof document === 'undefined' || document.getElementById('mh-css')) return;
    const s = document.createElement('style'); s.id = 'mh-css';
    s.textContent = `.mh h3{margin:22px 0 4px;font-size:17px}.mh h4{margin:14px 0 4px;font-size:14px}.mh .mh-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.5;max-width:86ch}
.mh svg{display:block;width:100%;height:auto}.mh .mh-chart{max-width:860px}.mh .mh-t{fill:var(--muted,#777);font-size:11px}.mh .mh-grid{stroke:var(--line,#e3e3e3)}
.mh-ctl{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 6px;align-items:center;font-size:13px;color:var(--muted,#666)}.mh-ctl select,.mh-ctl input{font:inherit;font-size:13px;padding:3px 6px;border:1px solid var(--line,#ccc);border-radius:6px;background:var(--surface,#fff);color:var(--ink,#222)}
.mh-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.mh-tbl th,.mh-tbl td{padding:5px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.mh-tbl td.n,.mh-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.mh-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}.mh-tbl tr.on td{background:color-mix(in srgb,var(--accent,#17734a) 10%,transparent);font-weight:600}
.mh-wrap{overflow-x:auto}.mh-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(165px,1fr));gap:8px;margin:6px 0 8px}.mh-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 10px}
.mh-card span{display:block;font-size:12px;color:var(--muted,#777)}.mh-card b{font-size:18px;font-variant-numeric:tabular-nums}.mh-card i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777)}
.mh-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.mh-legend b{display:inline-block;width:14px;height:3px;margin-right:5px;vertical-align:3px}
.mh-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:10px;max-width:92ch}.mh-sec{border-top:1px solid var(--line,#e5e5e5);margin-top:22px;padding-top:4px}
.mh .pos{color:var(--mk-profit,#17734a)}.mh .neg{color:var(--mk-cost,#c0392b)}.mh .muted{color:var(--muted,#777)}`;
    document.head.appendChild(s);
  }
  const tbl = (head, rows, numeric) => `<div class="mh-wrap"><table class="mh-tbl"><tr>${head.map((h, j) => `<th${numeric && numeric[j] ? ' class="n"' : ''}>${h}</th>`).join('')}</tr>${rows.map((r) => `<tr${r.on ? ' class="on"' : ''}>${(r.cells || r).map((c, j) => `<td${numeric && numeric[j] ? ' class="n"' : ''}>${c}</td>`).join('')}</tr>`).join('')}</table></div>`;
  const sgn = (v, txt) => `<span class="${fin(v) ? (v > 0 ? 'pos' : v < 0 ? 'neg' : '') : ''}">${txt}</span>`;
  const st = (s, d = 2) => (s && fin(s.mean) ? `${sgn(s.mean, spct(s.mean, d))} <span class="muted">(t ${num(s.t, 1)})</span>` : '—');
  const icTxt = (s) => (s && fin(s.mean) ? `${num(s.mean, 3)} <span class="muted">(t ${num(s.t, 1)})</span>` : '—');
  const key = (w, g) => `${w}|${g}`;

  // ------------------------------------------------------------------ the lines
  function hybrid(s, w, g) {
    return s.ma40.map((m, k) => {
      if (!fin(m) || m <= 0) return null;
      const e = s.el[k], dir = s.g[k];
      const base = fin(e) && e > 0 ? Math.exp((1 - w) * Math.log(m) + w * Math.log(e)) : m;
      return base * (1 + g * (fin(dir) ? dir : 0));
    });
  }
  function weekDate(s, k) {
    const d = new Date(s.start + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 7 * k); return d.toISOString().slice(0, 10);
  }
  function chart(s, w, g, width) {
    const Wd = Math.max(340, Math.min(860, width || 760)), Ht = Wd < 500 ? 300 : 340, L = 52, R = 10, T = 12, B = 26;
    const H = hybrid(s, w, g), n = s.p.length;
    const series = [['p', s.p], ['m10', s.ma10], ['m40', s.ma40], ['el', s.el], ['h', H]];
    const vals = series.flatMap(([, a]) => a.filter((v) => fin(v) && v > 0));
    if (!vals.length || n < 2) return '<p class="muted">Not enough weekly history to draw.</p>';
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pmin = Math.min(...s.p.filter(fin)), pmax = Math.max(...s.p.filter(fin));
    lo = Math.max(lo, pmin / 3); hi = Math.min(hi, pmax * 3);                    // a far-off earnings line is clipped, not the price
    const ly = (v) => Math.log(v), y0 = ly(lo) - 0.03 * (ly(hi) - ly(lo)), y1 = ly(hi) + 0.03 * (ly(hi) - ly(lo));
    const sx = (k) => L + (Wd - L - R) * k / (n - 1), sy = (v) => T + (Ht - T - B) * (1 - (ly(Math.min(Math.max(v, lo), hi)) - y0) / (y1 - y0));
    const f = (v) => v.toFixed(1);
    let out = `<svg viewBox="0 0 ${Wd} ${Ht}" role="img" aria-label="${esc(s.id)}: weekly close, 10- and 40-week averages, earnings line and hybrid line">`;
    const ticks = [];
    const span = Math.log10(hi / lo), step = Math.pow(10, Math.floor(Math.log10(hi - lo))) * (span > 0.6 ? 1 : 0.5);
    for (let v = Math.ceil(lo / step) * step; v <= hi && ticks.length < 9; v += step) ticks.push(v);
    ticks.forEach((v) => { out += `<line class="mh-grid" x1="${L}" x2="${Wd - R}" y1="${f(sy(v))}" y2="${f(sy(v))}"/><text class="mh-t" x="${L - 5}" y="${f(sy(v) + 4)}" text-anchor="end">${esc(usd(v))}</text>`; });
    for (let k = 0; k < n; k += 1) {
      const d = weekDate(s, k);
      if (d.slice(5, 7) === '01' && Number(d.slice(8, 10)) <= 7) out += `<line class="mh-grid" x1="${f(sx(k))}" x2="${f(sx(k))}" y1="${T}" y2="${Ht - B}"/><text class="mh-t" x="${f(sx(k))}" y="${Ht - 8}" text-anchor="middle">${d.slice(0, 4)}</text>`;
    }
    const path = (a, col, wdt, dash) => {
      let d = '', pen = false;
      a.forEach((v, k) => { if (fin(v) && v > 0) { d += (pen ? 'L' : 'M') + f(sx(k)) + ',' + f(sy(v)); pen = true; } else pen = false; });
      return d ? `<path d="${d}" style="fill:none;stroke:${col};stroke-width:${wdt};${dash ? 'stroke-dasharray:' + dash + ';' : ''}stroke-linejoin:round"/>` : '';
    };
    out += path(s.el, COL.el, 1.6, '') + path(s.ma10, COL.m10, 1.3, '5 3') + path(s.ma40, COL.m40, 1.6, '') + path(H, COL.h, 2.6, '') + path(s.p, COL.p, 1.4, '');
    (s.guidance || []).forEach(([d, lab]) => {                                      // guidance releases on the price line
      const k = Math.floor((Date.parse(d + 'T00:00:00Z') - Date.parse(s.start + 'T00:00:00Z')) / (7 * 864e5)) + 1;   // the first weekly close after it
      if (k < 0 || k >= n || !fin(s.p[k])) return;
      const x = sx(k), y = sy(s.p[k]), dir = GDIR[lab], col = dir > 0 ? COL.up : dir < 0 ? COL.down : COL.mute;
      const shape = dir > 0 ? `M${f(x)},${f(y - 13)}l5,8h-10z` : dir < 0 ? `M${f(x)},${f(y + 13)}l5,-8h-10z` : '';
      out += shape ? `<path d="${shape}" style="fill:${col}"><title>${esc(d)}: guidance ${esc(GLAB[lab] || lab)}</title></path>`
        : `<circle cx="${f(x)}" cy="${f(y - 9)}" r="3.5" style="fill:${col}"><title>${esc(d)}: guidance ${esc(GLAB[lab] || lab)}</title></circle>`;
    });
    return out + '</svg>';
  }
  const legend = (w, g) => `<div class="mh-legend"><span><b style="background:${COL.p}"></b>weekly close</span><span><b style="background:${COL.m10}"></b>10-week average (≈ 50-day)</span>
    <span><b style="background:${COL.m40}"></b>40-week average (≈ 200-day)</span><span><b style="background:${COL.el}"></b>earnings line</span>
    <span><b style="background:${COL.h};height:4px"></b>hybrid line (${pct(w)} earnings line, ${pct(g)} per guidance change)</span><span>▲ guidance raised · ▼ lowered · ● kept</span></div>`;

  // ------------------------------------------------------------------ one company
  function periodsOf(d) { const m = (((d.scores || {}).models || {})['26'] || {}).ma || {}; return Object.keys(m); }
  function controls(id, w, g) {
    return `<div class="mh-ctl"><label>Earnings line in the mix <select data-mh="w" id="${id}-w">${WS.map((v) => `<option value="${v}"${v === w ? ' selected' : ''}>${pct(v)}</option>`).join('')}</select></label>
      <label>Guidance moves the line by <select data-mh="g" id="${id}-g">${GS.map((v) => `<option value="${v}"${v === g ? ' selected' : ''}>${pct(v)}</option>`).join('')}</select></label></div>`;
  }
  function weightScores(d, w, g) {
    const P = periodsOf(d), Lw = (d.scores || {}).lines || {};
    const row = (h, k) => { const s = (Lw[h] || {})[k] || {}; return P.map((p) => st((s[p] || {}).net)); };
    const pick = (h) => { const by = ((((d.scores || {}).picks || {})[h] || {}).by_year) || {}; const ys = Object.keys(by).sort(); const p = ys.length ? by[ys[ys.length - 1]] : null;
      return p ? `${pct(p.w)} / ${pct(p.g)}, read as ${p.reading === 'trend' ? 'trend (above the line paid)' : 'value (below the line paid)'}` : '—'; };
    const rows = [];
    for (const h of ['13', '26']) {
      rows.push({ on: true, cells: [`Hybrid line (${pct(w)} / ${pct(g)}), ${h} weeks`, ...row(h, key(w, g))] });
      rows.push([`40-week average alone, ${h} weeks`, ...row(h, key(0, 0))]);
    }
    return tbl(['Above − below the line, after costs', ...P.map(esc)], rows, [0, 1, 1, 1]) +
      `<p class="mh-note">Every liquid company each week: those above the line against those below it, simple returns against SPY over the next 13 or 26 weeks, after trading costs, from ${esc(d.test_from)}. Positive: being above the line paid (a trend reading); negative: being below it did (a value reading). The weights picked this year from the years before: 13 weeks ${pick('13')}; 26 weeks ${pick('26')}.</p>`;
  }
  function companyHtml(s, d, row, w, g, width, id) {
    const n = s.p.length, k = n - 1, H = hybrid(s, w, g), P = s.p[k];
    const lg = (a, b) => (fin(a) && fin(b) && a > 0 && b > 0 ? Math.log(a / b) : null);
    const gl = (s.guidance || []).slice(-1)[0];
    const cards = [
      ['Weekly close', usd(P), `week ending ${esc(weekDate(s, k))}`],
      ['vs 40-week average', gap(lg(P, s.ma40[k])), usd(s.ma40[k]) + ' (≈ 200-day)'],
      ['vs 10-week average', gap(lg(P, s.ma10[k])), usd(s.ma10[k]) + ' (≈ 50-day)'],
      ['vs earnings line', fin(s.el[k]) ? gap(lg(P, s.el[k])) : '—', fin(s.el[k]) ? `${usd(s.el[k])}${row && fin(row.pe) ? ` · P/E ${num(row.pe, 1)} vs its median ${num(row.pe_med, 1)}` : ''}` : 'no line: earnings not positive or under 3 years of P/E'],
      ['vs hybrid line', gap(lg(P, H[k])), usd(H[k])],
      ['Guidance', gl ? esc(GLAB[gl[1]] || gl[1]) : '—', gl ? `latest release ${esc(gl[0])}` : 'none in the hub\'s record'],
    ];
    if (row && fin(row.pct_hybrid)) cards.push(['Models\' rank, 26 weeks', pct(row.pct_hybrid), `moving averages + fundamentals + guidance · alone: ${pct(row.pct_ma)}`]);
    let out = `<div class="mh-cards">${cards.map(([a, b, c]) => `<div class="mh-card"><span>${a}</span><b>${b}</b><i>${c}</i></div>`).join('')}</div>`;
    out += controls(id, w, g) + `<div class="mh-chart" data-mh-chart>${chart(s, w, g, width)}</div>` + legend(w, g);
    out += `<h4>What these weights have been worth</h4>` + weightScores(d, w, g);
    return out;
  }
  function lead(d) {
    const M = ((d.scores || {}).models || {})['26'] || {}, P = periodsOf(d), all = P[0], late = P[2];
    const a = (M.ma || {})[all] || {}, h = (M.hybrid || {})[all] || {}, al = (M.ma || {})[late] || {}, ae = (M.ma || {})[P[1]] || {};
    const ge = ((d.scores || {}).guidance_events || {})['13'] || {}, gr = ge.raised;
    return `<p class="mh-sub">The usual moving averages read as a trend: a price above its 40-week (≈ 200-day) average is said to be in an uptrend. Here the company's earnings (its earnings line, at its own usual P/E) and its guidance are mixed into the line, weighted, and every mix is tested walk-forward from ${esc(d.test_from)} on ${num(d.now)} liquid companies this week. ` +
      (a.net ? `Ranked by the moving averages alone, the best fifth of companies beat the worst by ${spct(a.net.mean, 1)} over 26 weeks after trading costs (t ${num(a.net.t, 1)}) — ${ae.net ? spct(ae.net.mean, 1) : '—'} in ${esc(P[1])}, ${al.net ? spct(al.net.mean, 1) : '—'} from ${esc(late.slice(0, 4))}. ` : '') +
      (h.net ? `With fundamentals and guidance added the rank correlation hardly moved (${num((h.ic || {}).mean, 3)} against ${num((a.ic || {}).mean, 3)}) and the basket did worse: ${spct(h.net.mean, 1)}. ` : '') +
      (gr ? `Guidance itself, ${esc(((d.scores || {}).guidance_events || {}).years ? d.scores.guidance_events.years.join('–') : '')} only: in the 13 weeks after a raise the company beat the average company by ${spct(gr.mean, 1)} (t ${num(gr.t, 1)}, ${num(gr.n)} releases). ` : '') +
      'Simple returns against SPY; history and models, not investment advice.</p>';
  }

  async function render(el, ctx) {
    css();
    const hub = (ctx && ctx.hub != null ? ctx.hub : ''), base = hub + 'data/market/history/';
    const T = String((ctx && ctx.ticker) || '').toUpperCase().replace(/\./g, '-');
    if (!T) { el.innerHTML = '<p class="muted">No ticker: the moving averages need a share price.</p>'; return; }
    el.innerHTML = '<p class="muted">Loading the moving averages…</p>';
    let s, d;
    try { [s, d] = await Promise.all([get(base + 'ma/' + T + '.json').catch(() => null), get(base + 'ma-hybrid.json')]); } catch (e) {
      el.innerHTML = `<p class="muted">Moving averages+ could not load (${esc(e.message)}).</p>`; return;
    }
    if (ctx && ctx.here && !ctx.here()) return;
    if (!s) { el.innerHTML = `<p class="muted">${esc(T)} is not in this week's set: it needs weekly prices and first-filed quarterly figures, a close of at least $3 and $10M traded a week.</p>`; return; }
    const row = s.now || null;
    const draw = () => {
      const w = ui.w != null ? ui.w : (d.weights || {}).default ? d.weights.default[0] : 0.5, g = ui.g != null ? ui.g : (d.weights || {}).default ? d.weights.default[1] : 0.05;
      el.innerHTML = `<div class="mh"><h3>${esc(T)} — moving averages with earnings and guidance</h3>${lead(d)}${companyHtml(s, d, row, w, g, el.clientWidth || 760, 'mh-' + T)}</div>`;
      el.querySelectorAll('select[data-mh]').forEach((x) => { x.onchange = () => { ui[x.dataset.mh] = Number(x.value); draw(); }; });
    };
    draw();
  }

  // ------------------------------------------------------------------ the hub
  function hubTables(d) {
    const S = d.scores || {}, P = periodsOf(d), out = [];
    const mods = (h) => MODEL_ORDER.map((m) => { const r = ((S.models || {})[h] || {})[m] || {};
      return [esc(((d.models || {})[m] || {}).name || m), ...P.map((p) => icTxt((r[p] || {}).ic)), ...P.map((p) => st((r[p] || {}).net))]; });
    for (const h of ['13', '26']) {
      out.push(`<h4>The models, ${h} weeks ahead</h4>` + tbl(['Model', ...P.map((p) => 'Rank corr. ' + esc(p)), ...P.map((p) => 'Best − worst fifth, net, ' + esc(p))], mods(h), [0, 1, 1, 1, 1, 1, 1]));
    }
    const rules = (h) => [['above40', 'Price above its 40-week average'], ['cross', '10-week average above the 40-week']].map(([k, n]) => {
      const r = ((S.rules || {})[h] || {})[k] || {}; return [esc(n) + `, ${h} weeks`, ...P.map((p) => st((r[p] || {}).net))]; });
    out.push('<h4>The classic rules</h4>' + tbl(['Above − below, after costs', ...P.map(esc)], rules('13').concat(rules('26')), [0, 1, 1, 1]));
    for (const h of ['13', '26']) {
      const Lw = (S.lines || {})[h] || {}, all = P[0];
      let best = null;
      WS.forEach((w) => GS.forEach((g) => { const v = ((Lw[key(w, g)] || {})[all] || {}).net; if (v && fin(v.mean) && (!best || v.mean > best[0])) best = [v.mean, w, g]; }));
      const rows = WS.map((w) => ({ on: best && best[1] === w, cells: [pct(w) + ' earnings line', ...GS.map((g) => st(((Lw[key(w, g)] || {})[all] || {}).net))] }));
      out.push(`<h4>Every weight on the grid, ${h} weeks, ${esc(all)}: above − below the hybrid line, after costs</h4>` + tbl(['', ...GS.map((g) => 'guidance ' + pct(g))], rows, [0, 1, 1, 1]));
      const pk = ((S.picks || {})[h] || {}), by = pk.by_year || {};
      out.push(`<p class="mh-note">Picked each year from the years before (weight, guidance, reading): ${Object.entries(by).map(([y, p]) => `${y} ${pct(p.w)}/${pct(p.g)} ${p.reading}`).join(' · ')}. Out of sample, the picks made ${st((((pk.oos || {})[all]) || {}).net)}.</p>`);
    }
    const ge = S.guidance_events || {};
    const labs = Object.keys(ge['13'] || {});
    if (labs.length) {
      out.push(`<h4>What followed each kind of guidance release (${esc((ge.years || []).join('–'))})</h4>` + tbl(['Release', 'Releases', '4 weeks vs the average company', '13 weeks', 'Beat the average, 13 weeks'],
        labs.map((l) => { const a = (ge['4'] || {})[l] || {}, b = ge['13'][l] || {}; return [esc(GLAB[l] || l), num(b.n), st(a), st(b), pct(b.beat)]; }), [0, 1, 1, 1, 1]) +
        '<p class="mh-note">From the first weekly close after the release (the day\'s reaction is not in it), simple returns against SPY less the average company\'s that week; the t treats releases as independent although many fall in the same weeks. The hub\'s guidance record starts in 2023 and is thin before 2024.</p>');
    }
    const cf = (((S.coefs || {})['26'] || {}).hybrid || {}), yrs = Object.keys(cf).sort(), last = yrs[yrs.length - 1];
    if (last) out.push(`<h4>The 26-week model's weights now (fitted on the years to ${esc(last - 1)})</h4>` + tbl(['Input', 'Return against the average company, 26 weeks'], Object.entries(cf[last]).map(([k, v]) => [esc((d.features || {})[k] || k), sgn(v, spct(v, 2))]), [0, 1]) +
      '<p class="mh-note">Per standard deviation of each input across the companies that week (log returns, before costs); guidance per raise (a cut counts −1), so its weight comes only from the years the guidance record covers (from 2023, thin before 2024).</p>');
    const Lg = d.ledger;
    out.push('<h4>Frozen record</h4>' + (Lg ? tbl(['Horizon', 'Weeks scored', 'Waiting', 'Rank corr.', 'Best − worst fifth', 'Above − below the 40-week'],
      Object.entries(Lg).map(([k, s]) => [esc(k.replace('ma:', '') + ' weeks'), num(s.resolved_weeks), num(s.pending_weeks), fin(s.ic) ? num(s.ic, 3) : '—', fin(s.best_minus_worst) ? spct(s.best_minus_worst, 2) : '—', fin(s.above_minus_below40) ? spct(s.above_minus_below40, 2) : '—']), [0, 1, 1, 1, 1, 1])
      : '<p class="muted">The record starts with the first closed week after this page went live.</p>'));
    out.push(`<p class="mh-note">Rank correlation: between the model's forecast and the next return against SPY across the companies, every week, averaged; the t counts weeks ÷ horizon as independent. Baskets: simple returns (what an equal-weighted basket earns), trading costs one way by weekly dollar volume (${(d.costs_bp || []).map((c) => `${num(c[1])} bp above $${num(c[0] / 1e6)}M`).join(', ')}), both legs in and out, no borrow fee. The earnings line counts a quarter from the first weekly close after its first filing; companies without positive earnings or three years of P/E use the 40-week average alone. Today's companies only: delisted names are missing.</p>`);
    return out.join('');
  }
  function listHtml(rows, w, g) {
    const R = (rows || []).filter((r) => fin(r.gap_hybrid));
    const top = R.slice().sort((a, b) => b.gap_hybrid - a.gap_hybrid).slice(0, 15), bot = R.slice().sort((a, b) => a.gap_hybrid - b.gap_hybrid).slice(0, 15);
    const cells = (r) => [`<a href="#" data-mh-t="${esc(r.id)}">${esc(r.id)}</a> <span class="muted">${esc(r.name || '')}</span>`, usd(r.close), gap(r.gap40), r.el ? gap(Math.log(r.close / r.el)) : '—', gap(r.gap_hybrid), r.guid_last ? esc(GLAB[r.guid_last[1]] || r.guid_last[1]) : '—', pct(r.pct_hybrid)];
    const head = ['Company', 'Close', 'vs 40-week', 'vs earnings line', 'vs hybrid line', 'Latest guidance', 'Models\' rank, 26w'];
    return `<h4>Furthest above the hybrid line (${pct(w)} / ${pct(g)})</h4>` + tbl(head, top.map(cells), [0, 1, 1, 1, 1, 0, 1]) + `<h4>Furthest below it</h4>` + tbl(head, bot.map(cells), [0, 1, 1, 1, 1, 0, 1]);
  }
  async function renderHub(el, ctx) {
    css();
    const hub = (ctx && ctx.hub != null ? ctx.hub : ''), base = hub + 'data/market/history/';
    el.innerHTML = '<p class="muted">Loading Moving averages+…</p>';
    let d, rows;
    try { [d, rows] = await Promise.all([get(base + 'ma-hybrid.json'), get(base + 'ma-hybrid-rows.json').catch(() => null)]); } catch (e) {
      el.innerHTML = `<p class="muted">Moving averages+ has not been published yet (${esc(e.message)}).</p>`; return;
    }
    const st_ = { t: (ctx && ctx.ticker) || '' };
    const draw = async () => {
      const dw = (d.weights || {}).default || [0.5, 0.05], w = ui.w != null ? ui.w : dw[0], g = ui.g != null ? ui.g : dw[1];
      let one = '';
      if (st_.t) {
        const T = st_.t.toUpperCase().replace(/\./g, '-');
        const s = await get(base + 'ma/' + T + '.json').catch(() => null);
        const row = (s && s.now) || (rows && (rows.rows || []).find((r) => r.id === T));
        one = s ? `<h3>${esc(T)} <span class="muted" style="font-weight:400">${esc(s.name || '')}</span></h3>` + companyHtml(s, d, row, w, g, el.clientWidth || 760, 'mh-hub')
          : `<p class="muted">${esc(T)} is not in this week's set (weekly prices and first-filed quarters, ≥ $3 and $10M traded a week).</p>`;
      }
      el.innerHTML = `<div class="mh"><h3>Moving averages+ — the 10- and 40-week averages with earnings and guidance mixed in</h3>${lead(d)}
        <div class="mh-ctl"><label>Ticker <input id="mh-q" value="${esc(st_.t)}" placeholder="e.g. NVDA · Enter" size="12"></label></div>${one}
        ${one ? '' : controls('mh-hub', w, g)}${rows ? listHtml(rows.rows, w, g) : ''}<div class="mh-sec"><h3>How it has done</h3>${hubTables(d)}</div></div>`;
      el.querySelectorAll('select[data-mh]').forEach((x) => { x.onchange = () => { ui[x.dataset.mh] = Number(x.value); refresh(rows); draw(); }; });
      const q = el.querySelector('#mh-q');
      if (q) q.onkeydown = (e) => { if (e.key === 'Enter') { st_.t = q.value.trim(); draw(); } };
      el.querySelectorAll('[data-mh-t]').forEach((a) => { a.onclick = (e) => { e.preventDefault(); st_.t = a.dataset.mhT; draw(); }; });
    };
    const refresh = (R) => {                                         // the list's gaps for the weights picked here
      const dw = (d.weights || {}).default || [0.5, 0.05], w = ui.w != null ? ui.w : dw[0], g = ui.g != null ? ui.g : dw[1];
      ((R || {}).rows || []).forEach((r) => {
        if (!fin(r.ma40) || !fin(r.close)) return;
        const base_ = fin(r.el) && r.el > 0 ? Math.exp((1 - w) * Math.log(r.ma40) + w * Math.log(r.el)) : r.ma40;
        const Hn = base_ * (1 + g * (fin(r.guid) ? r.guid : 0));
        r.hybrid = Hn; r.gap_hybrid = Math.log(r.close / Hn);
      });
    };
    refresh(rows);
    await draw();
  }

  const api = { render, renderHub, _chart: chart, _hybrid: hybrid, _company: companyHtml, _hub: hubTables, _list: listHtml, _lead: lead };
  if (typeof window !== 'undefined') window.MAHybridView = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
