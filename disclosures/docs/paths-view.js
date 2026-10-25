/* Price paths & patterns — one company's correlated price paths (seven models and their ensemble), analog and
   correlated-asset historical simulations, and rule-based price action with each rule's pooled out-of-sample evidence.
   Shared by the Disclosure Hub (Price paths tab → one company, paths.js) and every company page of the Sankey site
   (views.json: window.PathsView.render(el, {cik, ticker, hub, here})). Data: data/research/paths/c/<cik>.json,
   models.json and rules.json (app/paths.py + paths_build.py, branch research-paths); text: paths-guide.json next to
   this file. Self-contained: colours from the host's CSS variables with fallbacks. No dependencies. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const px = (v) => (fin(v) ? '$' + num(v, v >= 1000 ? 0 : 2) : '—');
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const chg = (v, p0, d = 1) => (fin(v) && fin(p0) && p0 ? spct(v / p0 - 1, d) : '—');
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const md = (e) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(e || ''); return m ? MON[+m[2] - 1] + ' ' + (+m[3]) : String(e || ''); };
  const mdy = (e) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(e || ''); return m ? `${MON[+m[2] - 1]} ${+m[3]}, ${m[1]}` : String(e || ''); };
  const COL = { band: 'var(--rot-1, #2a78d6)', path: 'var(--muted, #888)', up: 'var(--mk-profit, #17734a)', down: 'var(--mk-cost, #c0392b)', ink: 'var(--ink, #222)',
    mute: 'var(--muted, #888)', warn: 'var(--q-warm, #d9822b)', surface: 'var(--surface, #fff)', line: 'var(--line, #e3e3e3)', zone: 'var(--accent, #2a78d6)' };
  const ORDER = ['ensemble', 'joint_bootstrap', 'block_bootstrap', 'fhs', 'factor', 'cholesky', 't_copula', 'dcc_garch'];
  const SHORT = { ensemble: 'Ensemble', joint_bootstrap: 'Joint bootstrap', block_bootstrap: 'Block bootstrap', fhs: 'FHS', factor: 'Factor',
    cholesky: 'Cholesky', t_copula: 't-copula', dcc_garch: 'DCC-GARCH' };
  const HERE = (typeof document !== 'undefined' && document.currentScript && document.currentScript.src) ? document.currentScript.src.replace(/[^/]*$/, '') : '';
  const store = {};
  const get = (u) => store[u] || (store[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .catch((e) => { delete store[u]; throw e; }));
  let CLIP = 0;

  function css() {
    if (typeof document === 'undefined' || !document.head || document.getElementById('pv-css')) return;
    const s = document.createElement('style'); s.id = 'pv-css';
    s.textContent = `.pv svg{display:block;width:100%;height:auto}.pv h3{margin:22px 0 6px;font-size:17px}.pv h4{margin:16px 0 4px;font-size:14.5px}
.pv .pv-sub{color:var(--muted,#777);font-size:13px;line-height:1.55;margin:0 0 10px;max-width:90ch}.pv .pv-g{stroke:var(--line,#e3e3e3);stroke-width:1}
.pv .pv-t{fill:var(--muted,#777);font-size:11px}.pv .pv-l{fill:var(--ink,#222);font-size:11.5px;paint-order:stroke;stroke:var(--surface,#fff);stroke-width:3px}
.pv-pills{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 8px}.pv-pill{font:inherit;font-size:12.5px;border:1px solid var(--line,#ddd);background:none;border-radius:999px;padding:3px 10px;cursor:pointer;color:var(--muted,#666)}
.pv-pill.on{color:var(--ink,#222);border-color:var(--ink,#222);font-weight:600}
.pv-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:6px 0 10px}.pv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:8px 10px;min-width:0}
.pv-card span{display:block;font-size:12px;color:var(--muted,#777)}.pv-card b{font-size:18px;font-variant-numeric:tabular-nums}.pv-card i{display:block;font-style:normal;font-size:12px;color:var(--muted,#777)}
.pv-wrap{overflow-x:auto;max-width:100%}.pv-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.pv-tbl th,.pv-tbl td{padding:5px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.pv-tbl .n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.pv-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}.pv-tbl tr.on td{background:color-mix(in srgb,var(--ink,#222) 5%,transparent)}
.pv-x{max-width:84ch}.pv-x p{margin:5px 0;font-size:13.5px;line-height:1.55}.pv-x b{font-weight:600}.pv-terms{font-size:12.5px;color:var(--muted,#666);line-height:1.6}
.pv-apx{border:1px solid var(--line,#ddd);border-radius:10px;padding:6px 12px;margin:6px 0;max-width:980px}.pv-apx summary{cursor:pointer;font-size:13.5px;line-height:1.6}
.pv-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted,#777);margin:4px 0 8px}.pv-legend b{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.pv-ev{display:inline-block;font-size:11.5px;border-radius:999px;padding:1px 8px;border:1px solid currentColor;white-space:nowrap}.pv-ev.strong{color:var(--mk-profit,#17734a)}.pv-ev.moderate{color:var(--rot-1,#2a78d6)}
.pv-ev.weak{color:var(--q-warm,#d9822b)}.pv-ev.none{color:var(--muted,#888)}.pv-up{color:var(--mk-profit,#17734a)}.pv-down{color:var(--mk-cost,#c0392b)}
.pv-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}@media (max-width:820px){.pv-two{grid-template-columns:minmax(0,1fr)}}
.pv-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:10px;max-width:90ch}
@media (max-width:640px){.pv .pv-tbl{display:block;overflow-x:auto;max-width:100%}.pv-card b{font-size:16px}}`;
    document.head.appendChild(s);
  }

  function ticks(lo, hi, n = 5) {
    const raw = (hi - lo) / n, p = 10 ** Math.floor(Math.log10(raw || 1)), st = [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw);
    const out = []; for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(6)); return out;
  }

  /* ---------- a fan chart: quantile bands over the horizon, optional sample paths and neighbor paths ---------- */
  // q: [[p05,p10,p25,p50,p75,p90,p95] per point]; days: labels per point; price0: today's price
  function fanSvg(q, price0, days, opt = {}) {
    if (!(q || []).length || !fin(price0)) return '<p class="pv-sub">Not enough data for this view.</p>';
    const F = opt.fmt || px;
    const W = 720, H = opt.h || 320, L = 62, R = 104, T = 14, B = 34, n = q.length;
    const all = [price0, ...q.flat().filter(fin), ...(opt.sample || []).flat().filter(fin), ...(opt.extra || []).flat().filter(fin)];
    const lo0 = Math.min(...q.map((r) => r[0]).filter(fin), price0), hi0 = Math.max(...q.map((r) => r[6]).filter(fin), price0);
    const span = hi0 - lo0 || price0 * 0.1;
    const ymin = Math.max(Math.min(...all), lo0 - span * 0.35) * 0.99, ymax = Math.min(Math.max(...all), hi0 + span * 0.35) * 1.01;
    const sx = (i) => L + i / n * (W - L - R), sy = (v) => T + (ymax - Math.min(ymax, Math.max(ymin, v))) / (ymax - ymin) * (H - T - B);
    const pt = (i, v) => sx(i).toFixed(1) + ',' + sy(v).toFixed(1);
    const band = (a, b) => [pt(0, price0), ...q.map((r, i) => pt(i + 1, r[a]))].join(' ') + ' ' + [...q.map((r, i) => pt(i + 1, r[b])).reverse(), pt(0, price0)].join(' ');
    const clip = 'pv-clip-' + (++CLIP);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.label || 'Range of simulated prices over the next 63 trading days')}"><defs><clipPath id="${clip}"><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></clipPath></defs>`;
    ticks(ymin, ymax).forEach((v) => { s += `<line class="pv-g" x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}"/><text class="pv-t" x="${L - 8}" y="${sy(v) + 4}" text-anchor="end">${F(v)}</text>`; });
    [[0, 6, 0.12], [1, 5, 0.18], [2, 4, 0.26]].forEach(([a, b, o]) => { s += `<polygon points="${band(a, b)}" style="fill:${opt.color || COL.band};opacity:${o}"/>`; });
    s += `<g clip-path="url(#${clip})">`;
    (opt.extra || []).forEach((p) => { s += `<polyline points="${[pt(0, price0), ...p.map((v, i) => pt(i + 1, v))].join(' ')}" style="fill:none;stroke:${COL.warn};stroke-width:1;opacity:.55"/>`; });
    (opt.sample || []).forEach((p) => { s += `<polyline points="${[pt(0, price0), ...p.map((v, i) => pt(i + 1, v))].join(' ')}" style="fill:none;stroke:${COL.path};stroke-width:.7;opacity:.4"/>`; });
    s += '</g>';
    s += `<polyline style="fill:none;stroke:${opt.color || COL.band};stroke-width:2;stroke-dasharray:6 4" points="${[pt(0, price0), ...q.map((r, i) => pt(i + 1, r[3]))].join(' ')}"/>`;
    s += `<line x1="${L}" x2="${W - R}" y1="${sy(price0)}" y2="${sy(price0)}" style="stroke:${COL.mute};stroke-dasharray:2 3"/><text class="pv-l" x="${W - R + 4}" y="${sy(price0) + 4}">today ${F(price0)}</text>`;
    const e = q[n - 1];
    [[6, '95%'], [5, '90%'], [3, 'median'], [1, '10%'], [0, '5%']].forEach(([k, l]) => { if (fin(e[k]) && Math.abs(sy(e[k]) - sy(price0)) > 9) s += `<text class="pv-l" x="${W - R + 4}" y="${sy(e[k]) + 4}">${l} ${F(e[k])}</text>`; });
    const lab = days || [];
    let lastX = -1e9;
    lab.forEach((d, i) => { const x = sx(i + 1); if (x - lastX >= 52 && (i === lab.length - 1 || sx(n) - x >= 40)) { s += `<text class="pv-t" x="${x}" y="${H - B + 16}" text-anchor="middle">${esc(md(d))}</text>`; lastX = x; } });
    s += `<text class="pv-t" x="${L}" y="${H - B + 16}" text-anchor="middle">today</text></svg>`;
    return s;
  }
  const fanLegend = (extra) => `<div class="pv-legend"><span><b style="background:${COL.band};opacity:.55"></b>middle 50 / 80 / 90% of the paths</span><span><b style="background:${COL.band}"></b>median (dashed)</span>${extra || ''}</div>`;

  /* ---------- explanations ---------- */
  function explain(x, terms) {
    if (!x) return '';
    return `<div class="pv-x"><p><b>What it is.</b> ${esc(x.what)}</p>${x.why ? `<p><b>Why it works.</b> ${esc(x.why)}</p>` : ''}${x.fits ? `<p><b>Fits.</b> ${esc(x.fits)}</p>` : ''}${x.watch ? `<p><b>Watch out.</b> ${esc(x.watch)}</p>` : ''}${terms || ''}</div>`;
  }
  function termsLine(G, text) {
    const hits = (G.glossary || []).filter(([t]) => t.split(/,\s*/).some((tok) => new RegExp('(^|[^A-Za-z0-9])' + tok.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![A-Za-z0-9])').test(text)));
    return hits.length ? `<p class="pv-terms"><b>Terms.</b> ${hits.map(([t, f]) => `${esc(t)} = ${esc(f.charAt(0).toLowerCase() + f.slice(1))}`).join(' · ')}</p>` : '';
  }

  /* ---------- 1. correlated price paths ---------- */
  function pathsSection(d, M, G, st) {
    const P = d.paths;
    if (!P || !(P.ensemble || P.models)) return `<h3>Correlated price paths</h3><p class="pv-sub">Not enough daily history yet for the path models (they need about a year of bars).</p>`;
    const key = st.model in (P.models || {}) || st.model === 'ensemble' ? st.model : 'ensemble';
    const sel = key === 'ensemble' ? P.ensemble : P.models[key];
    const p0 = d.price, end = (sel && sel.end) || {};
    const role = (r) => ({ stock: 'the stock', market: 'the market (S&P 500 ETF)', sector: 'its sector ETF', peer: 'peer' }[r] || r);
    const assets = (d.assets || []).map((a) => `${esc(a.t)} <span class="pv-sub" style="display:inline">(${role(a.role)}${fin(a.corr) ? `, correlation ${num(a.corr, 2)}` : ''})</span>`).join(' · ');
    const jm = ((sel || {}).joint || {}).market || {}, js = ((sel || {}).joint || {}).sector || {};
    const card = (label, val, note, cls) => `<div class="pv-card"><span>${label}</span><b class="${cls || ''}">${val}</b>${note ? `<i>${note}</i>` : ''}</div>`;
    let h = `<h3>Correlated price paths — next 63 trading days</h3><p class="pv-sub">${esc(G.paths_intro || '')}</p><p class="pv-sub">Simulated together: ${assets}. ${num(P.window_days)} days of returns to ${esc(mdy(d.as_of))}.</p>`;
    h += `<div class="pv-pills" role="group" aria-label="Model">${ORDER.filter((m) => m === 'ensemble' ? P.ensemble : (P.models || {})[m] && !P.models[m].error).map((m) => `<button type="button" class="pv-pill${m === key ? ' on' : ''}" data-pvm="${m}">${esc(SHORT[m])}</button>`).join('')}</div>`;
    if (!sel || sel.error) return h + `<p class="pv-sub">This model could not run for this company (${esc((sel || {}).error || 'no result')}).</p>`;
    h += `<div class="pv-cards">${card('Median in 63 days', px(end.p50), chg(end.p50, p0))}${card('80% range', `${px(end.p10)} – ${px(end.p90)}`, `${chg(end.p10, p0, 0)} to ${chg(end.p90, p0, 0)}`)}`
      + `${card('Ends 10%+ lower', pct(sel.p_down10), `20%+ lower: ${pct(sel.p_down20)}`, 'pv-down')}${card('Ends 10%+ higher', pct(sel.p_up10), `20%+ higher: ${pct(sel.p_up20)}`, 'pv-up')}`
      + `${card('Touches −10% on the way', pct(sel.p_touch_down10), 'at any point')}${card('Typical worst drawdown', pct((sel.mdd || {}).p50), `1 in 10 paths: ${pct((sel.mdd || {}).p90)}`)}`
      + `${card('If the market falls 10%', fin(jm.p_a_given_b) ? pct(jm.p_a_given_b) : '—', 'chance the stock falls 10% too')}${card('If its sector falls 10%', fin(js.p_a_given_b) ? pct(js.p_a_given_b) : '—', 'chance the stock falls 10% too')}`
      + `${card('Volatility', pct(sel.vol), 'annualized, simulated')}</div>`;
    h += fanSvg(sel.q, p0, P.days, { sample: key === 'ensemble' ? P.ensemble.sample : null }) + fanLegend(key === 'ensemble' ? `<span><b style="background:${COL.path}"></b>30 sample paths</span>` : '');
    const x = key === 'ensemble' ? (G.models || {}).ensemble : (G.models || {})[key];
    h += `<details class="pv-apx" open><summary><b>${esc((x || {}).name || SHORT[key])}</b> — what this model is</summary>${explain(x, termsLine(G, ((x || {}).what || '') + ' ' + ((x || {}).watch || '')))}</details>`;
    // every model side by side, with the walk-forward scorecard
    const S = (M && M.paths) || {};
    const rows = ORDER.filter((m) => (m === 'ensemble' ? P.ensemble : (P.models || {})[m]) && !((P.models || {})[m] || {}).error).map((m) => {
      const r = m === 'ensemble' ? P.ensemble : P.models[m], e = r.end || {}, sc = S[m] || {}, j = (r.joint || {}).market || {};
      return `<tr class="${m === key ? 'on' : ''}"><td><button type="button" class="pv-pill${m === key ? ' on' : ''}" data-pvm="${m}">${esc(SHORT[m])}</button></td><td class="n">${px(e.p50)}</td><td class="n">${px(e.p10)} – ${px(e.p90)}</td>`
        + `<td class="n">${pct(r.p_down10)}</td><td class="n">${pct(r.p_up10)}</td><td class="n">${pct((r.mdd || {}).p50)}</td><td class="n">${fin(j.p_a_given_b) ? pct(j.p_a_given_b) : '—'}</td>`
        + `<td class="n">${fin(sc.cover80) ? pct(sc.cover80) : '—'}</td><td class="n">${fin(sc.skill) ? spct(sc.skill, 1) : '—'}</td></tr>`;
    }).join('');
    h += `<h4>Every model side by side</h4><div class="pv-wrap"><table class="pv-tbl"><thead><tr><th>Model</th><th class="n">Median</th><th class="n">80% range</th><th class="n">P(−10%)</th><th class="n">P(+10%)</th><th class="n">Typical drawdown</th><th class="n">Falls with the market</th><th class="n">Scorecard: 80% range held</th><th class="n">Skill vs naive</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    h += `<p class="pv-sub">${esc(G.scorecard || '')}${M && M.tickers ? ` Sample: ${M.tickers.length} companies; built ${esc((M.built_at || '').slice(0, 10))}.` : ' The scorecard is computed weekly.'}</p>`;
    return h;
  }

  /* ---------- 2. analogs and correlated assets ---------- */
  function analogSection(d, M, G) {
    const A = d.analogs || {}, p0 = d.price, days = (d.paths || {}).days;
    const S = (M && M.analogs) || {};
    const score = (k) => { const s = S[k] || {}; return fin(s.cover80) ? ` Scorecard: the 80% range held ${pct(s.cover80)} of the time${fin(s.ic) ? `, rank correlation of the median with the outcome ${num(s.ic, 2)}` : ''}${fin(s.n) ? ` (${num(s.n)} forecasts)` : ''}.` : ''; };
    let h = `<h3>Historical analogs and correlated assets</h3><p class="pv-sub">What followed the past moments that looked most like today — in this stock's own history, in every stock's history, and in the situation of the assets that move with it.</p>`;
    const one = (k, title, extraNote) => {
      const r = A[k];
      const x = (G.analogs || {})[k];
      if (!r || r.error || !(r.q || []).length) return `<h4>${esc(title)}</h4><p class="pv-sub">${r && r.error ? 'Could not be computed (' + esc(r.error) + ').' : 'Not available for this company.'}</p>${x ? `<details class="pv-apx"><summary>What this method is</summary>${explain(x)}</details>` : ''}`;
      const e = r.end || {}, nb = r.neighbors || [];
      const lines = nb.filter((n) => (n.path || []).length).map((n) => n.path.map((v) => p0 * Math.exp(v)));
      let out = `<h4>${esc(title)}</h4><div class="pv-cards"><div class="pv-card"><span>Median after 63 days</span><b>${px(e.p50)}</b><i>${chg(e.p50, p0)}</i></div><div class="pv-card"><span>80% of outcomes</span><b>${px(e.p10)} – ${px(e.p90)}</b></div>`
        + `<div class="pv-card"><span>Share that rose</span><b>${pct(r.p_up)}</b><i>weighted by similarity</i></div>${fin(r.similarity) ? `<div class="pv-card"><span>How close the matches are</span><b>${num(r.similarity, 2)}</b><i>0 = no closer than random, 1 = identical</i></div>` : ''}</div>`;
      out += fanSvg(r.q, p0, days, { extra: lines, label: title }) + fanLegend(lines.length ? `<span><b style="background:${COL.warn}"></b>what followed the ${lines.length} closest matches</span>` : '');
      if (nb.length) out += `<div class="pv-wrap"><table class="pv-tbl"><thead><tr><th>Matched moment</th>${nb.some((n) => n.ticker) ? '<th>Stock</th>' : ''}<th class="n">Distance</th><th class="n">63 days later</th></tr></thead><tbody>${nb.map((n) => `<tr><td>${esc(mdy(n.date))}</td>${nb.some((m) => m.ticker) ? `<td>${esc(n.ticker || '')}</td>` : ''}<td class="n">${num(n.dist, 2)}</td><td class="n ${n.fwd >= 0 ? 'pv-up' : 'pv-down'}">${spct(Math.expm1(n.fwd || 0))}</td></tr>`).join('')}</tbody></table></div>`;
      out += `<p class="pv-sub">${esc(extraNote || '')}${score(k)}</p>`;
      if (x) out += `<details class="pv-apx"><summary>What this method is</summary>${explain(x)}</details>`;
      return out;
    };
    h += `<div class="pv-two"><div>${one('self', 'Its own history')}</div><div>${one('pooled', 'Every stock\'s history')}</div></div>`;
    const peers = A.peers || [];
    if (peers.length) {
      h += `<h4>The assets that move with it</h4><div class="pv-wrap"><table class="pv-tbl"><thead><tr><th>Asset</th><th class="n">Correlation (weekly, 2 years)</th><th class="n">Leads by</th><th class="n">Lead correlation</th><th class="n">p-value (corrected)</th></tr></thead><tbody>${peers.map((p) => `<tr><td>${esc(p.ticker)}</td><td class="n">${num(p.corr, 2)}</td><td class="n">${fin(p.best_lag) && (p.lead_p || 1) < 0.05 ? num(p.best_lag) + (p.best_lag === 1 ? ' week' : ' weeks') : '—'}</td><td class="n">${num(p.lead_corr, 2)}</td><td class="n">${fin(p.lead_p) ? (p.lead_p < 0.001 ? '<0.001' : num(p.lead_p, 3)) : '—'}</td></tr>`).join('')}</tbody></table></div>`;
      if ((G.analogs || {}).peers) h += `<details class="pv-apx"><summary>How the correlated assets are chosen</summary>${explain(G.analogs.peers)}</details>`;
    }
    h += `<div class="pv-two"><div>${one('peer', 'When it and its peers last looked like this')}</div><div>${leadlag(A.leadlag, p0, G, S)}</div></div>`;
    return h;
  }
  function leadlag(r, p0, G, S) {
    const x = (G.analogs || {}).leadlag;
    if (!r || r.error || !r.end) return `<h4>Lead–lag forecast</h4><p class="pv-sub">No correlated asset has led this stock significantly, so there is no lead–lag forecast.</p>${x ? `<details class="pv-apx"><summary>What this method is</summary>${explain(x)}</details>` : ''}`;
    const e = Array.isArray(r.end) ? { p10: r.end[1], p50: r.end[3], p90: r.end[5] } : r.end;
    const s = (S || {}).leadlag || {};
    return `<h4>Lead–lag forecast (next 21 trading days)</h4><div class="pv-cards"><div class="pv-card"><span>Median</span><b>${px(e.p50)}</b><i>${chg(e.p50, p0)}</i></div><div class="pv-card"><span>80% range</span><b>${px(e.p10)} – ${px(e.p90)}</b></div><div class="pv-card"><span>Leaders used</span><b>${num(r.n_leaders)}</b><i>fit R² ${num(r.r2_in, 2)}</i></div></div>`
      + `<p class="pv-sub">${fin(s.cover80) ? `Scorecard: 80% range held ${pct(s.cover80)} of the time.` : ''}</p>${x ? `<details class="pv-apx"><summary>What this method is</summary>${explain(x)}</details>` : ''}`;
  }

  /* ---------- 3. price action (filled in by priceSection below) ---------- */
  function evidenceTag(ev, h = '20') {
    const g = ev && typeof ev === 'object' ? (ev[h] || ev[String(h)] || 'none') : (ev || 'none');
    return `<span class="pv-ev ${esc(g)}">${esc(g)}</span>`;
  }
  let priceSection = () => '';

  /* ---------- the page ---------- */
  function draw(el, d, M, RU, G, st) {
    css();
    st = st || { model: 'ensemble' };
    G = G || {};
    let h = `<div class="pv"><p class="pv-sub">${(G.intro || []).map(esc).join(' ')}</p>`;
    h += `<p class="pv-sub">${esc(d.name || d.ticker)} at ${px(d.price)} (close of ${esc(mdy(d.as_of))}). Not investment advice.</p>`;
    h += `<div data-pvpaths>${pathsSection(d, M, G, st)}</div>`;
    h += analogSection(d, M, G);
    h += priceSection(d, RU, G);
    h += `<details class="pv-apx"><summary><b>Glossary</b> — every abbreviation on this page in full (${(G.glossary || []).length})</summary><div class="pv-wrap"><table class="pv-tbl"><thead><tr><th>Term</th><th>In full</th><th>What it means</th></tr></thead><tbody>${(G.glossary || []).map(([a, b, c]) => `<tr><td><b>${esc(a)}</b></td><td>${esc(b)}</td><td>${esc(c)}</td></tr>`).join('')}</tbody></table></div></details>`;
    h += `<p class="pv-note">Daily bars from Yahoo Finance (Stooq as the fallback), adjusted for splits and dividends. Built ${esc((d.as_of || ''))} by app/paths.py. Simulations describe a range of risk, not a prediction; analogs and price-action rules describe what followed similar situations in the past, graded by how they did out of sample.</p></div>`;
    el.innerHTML = h;
    const rebind = () => el.querySelectorAll('[data-pvm]').forEach((b) => b.addEventListener('click', () => {
      st.model = b.dataset.pvm;
      el.querySelector('[data-pvpaths]').innerHTML = pathsSection(d, M, G, st);
      rebind();
    }));
    rebind();
    if (typeof bindPrice === 'function') bindPrice(el, d, RU, G);
  }
  let bindPrice = null;

  async function render(el, ctx) {
    css();
    const hub = ctx && ctx.hub != null ? ctx.hub : '';
    const base = hub + 'data/research/paths/';
    el.innerHTML = '<p class="muted">Loading the price paths…</p>';
    const gP = get(HERE + 'paths-guide.json').catch(() => ({})), mP = get(base + 'models.json').catch(() => null), rP = get(base + 'rules.json').catch(() => null);
    let d;
    try { d = await get(base + `c/${Number(ctx.cik)}.json`); } catch (e) {
      el.innerHTML = `<p class="muted">No price paths for this company yet (${esc(e.message)}). They are built every day after the US close for the companies on the valuation page, once their daily bars are on file.</p>`;
      return;
    }
    const [G, M, RU] = await Promise.all([gP, mP, rP]);
    if (ctx.here && !ctx.here()) return;
    draw(el, d, M, RU, G);
  }

  /* ---------- a 13F manager's or an official's portfolio (people pages and the hub's Portfolios view) ---------- */
  function portfolioHtml(p, G, st, compact) {
    const key = st.model === 'ensemble' ? 'ensemble' : st.model in (p.models || {}) ? st.model : 'ensemble';
    const sel = key === 'ensemble' ? p.ensemble : p.models[key];
    if (!sel) return '<p class="pv-sub">No simulation for this portfolio.</p>';
    const e = sel.end || {}, j = ((sel.joint || {}).market) || {};
    const ix = (v) => (fin(v) ? spct(v / 100 - 1) : '—');
    const card = (label, val, note, cls) => `<div class="pv-card"><span>${label}</span><b class="${cls || ''}">${val}</b>${note ? `<i>${note}</i>` : ''}</div>`;
    let h = `<h3>Portfolio price paths — next 63 trading days</h3><p class="pv-sub">${p.approximate ? 'An approximation: officials disclose transactions in ranges, not positions, so the portfolio is their purchases minus sales over two years at the midpoint of each range. ' : 'The latest 13F, weighted by value. '}${pct(p.coverage)} of the weight has daily bars; the rest is left out and the weights renormalized. Simulated with the S&P 500 ETF by seven models; the portfolio starts at 100.</p>`;
    h += `<div class="pv-pills" role="group" aria-label="Model">${ORDER.filter((m) => m === 'ensemble' ? p.ensemble : (p.models || {})[m]).map((m) => `<button type="button" class="pv-pill${m === key ? ' on' : ''}" data-pvpm="${m}">${esc(SHORT[m])}</button>`).join('')}</div>`;
    h += `<div class="pv-cards">${card('Median in 63 days', ix(e.p50))}${card('80% range', `${ix(e.p10)} to ${ix(e.p90)}`)}${card('Ends 10%+ lower', pct(sel.p_down10), '', 'pv-down')}${card('Ends 10%+ higher', pct(sel.p_up10), '', 'pv-up')}`
      + `${card('Typical worst drawdown', pct((sel.mdd || {}).p50), `1 in 10 paths: ${pct((sel.mdd || {}).p90)}`)}${card('If the market falls 10%', fin(j.p_a_given_b) ? pct(j.p_a_given_b) : '—', 'chance the portfolio falls 10% too')}${card('Volatility', pct(sel.vol), 'annualized')}</div>`;
    const days = []; let d = new Date((p.as_of || '2026-01-01') + 'T00:00:00Z');
    while (days.length < 63) { d = new Date(d.getTime() + 864e5); if (d.getUTCDay() % 6) days.push(d.toISOString().slice(0, 10)); }
    const lab = []; for (let i = 4; i < 63; i += 5) lab.push(days[i]); if (lab.length < sel.q.length) lab.push(days[62]);
    h += fanSvg(sel.q, 100, lab, { label: 'Range of simulated portfolio values', fmt: (v) => num(v, 1) }) + fanLegend();
    if (!compact) {
      const x = key === 'ensemble' ? (G.models || {}).ensemble : (G.models || {})[key];
      h += `<details class="pv-apx"><summary><b>${esc((x || {}).name || SHORT[key])}</b> — what this model is</summary>${explain(x)}</details>`;
      h += `<h4>Holdings simulated</h4><div class="pv-wrap"><table class="pv-tbl"><thead><tr><th>Ticker</th><th class="n">Weight</th></tr></thead><tbody>${(p.holdings || []).slice(0, 25).map(([t, w]) => `<tr><td>${esc(t)}</td><td class="n">${pct(w, 1)}</td></tr>`).join('')}</tbody></table></div>`;
    }
    return h;
  }
  async function portfolio(el, ctx) {
    css();
    const hub = ctx && ctx.hub != null ? ctx.hub : '';
    const kind = ctx.kind === 'o' ? 'o' : 'm';
    el.innerHTML = '<p class="muted">Loading the portfolio paths…</p>';
    let p;
    try { p = await get(hub + `data/research/paths/portfolios/${kind}/${encodeURIComponent(ctx.id)}.json`); } catch (e) {
      el.innerHTML = ctx.compact ? '' : `<p class="muted">No portfolio paths yet (${esc(e.message)}).</p>`;
      return;
    }
    const G = await get(HERE + 'paths-guide.json').catch(() => ({}));
    const st = { model: 'ensemble' };
    const paint = () => {
      el.innerHTML = `<div class="pv">${portfolioHtml(p, G, st, ctx.compact)}${ctx.compact ? `<p class="pv-note">More in Price paths → portfolios (seven models, holdings used, explanations).</p>` : ''}</div>`;
      el.querySelectorAll('[data-pvpm]').forEach((b) => b.addEventListener('click', () => { st.model = b.dataset.pvpm; paint(); }));
    };
    paint();
  }

  const api = { render, draw, portfolio, fanSvg, ticks, explain, evidenceTag, _setPrice: (f, b) => { priceSection = f; bindPrice = b; } };
  if (typeof window !== 'undefined') window.PathsView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
