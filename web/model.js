/* The growth model at four levels (pipeline/hier.py → data/model/): a box on company pages, industry (Gamma) pages,
 * sector pages and chain pages, and the #model overview. Each box says the entity's latest year-on-year growth, what
 * it follows (its parent's growth, with its beta), the next four quarters with 80% ranges, and how the model did out of
 * sample against "growth stays what it was". */
(function (global) {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const usd = (v) => {
    if (v == null || isNaN(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−' : '';
    if (a >= 0.95e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
    if (a >= 0.95e9) return `${s}$${(a / 1e9).toFixed(a >= 100e9 ? 0 : 1)}B`;
    if (a >= 0.95e6) return `${s}$${(a / 1e6).toFixed(a >= 100e6 ? 0 : 1)}M`;
    return `${s}$${(a / 1e3).toFixed(0)}K`;
  };
  const pct = (x, d) => (x == null || isNaN(x) ? '—' : `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(100 * x).toFixed(d == null ? 1 : d)}%`);
  const upct = (x, d) => (x == null || isNaN(x) ? '—' : `${(100 * x).toFixed(d == null ? 1 : d)}%`);
  const cache = new Map();
  function get(path) {
    if (!cache.has(path)) cache.set(path, fetch((global.FF_DATA || 'data/') + path).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    return cache.get(path);
  }

  function verdict(bt) {
    if (!bt) return '<span class="muted">too few quarters to test</span>';
    const win = bt.uncond < bt.naive;
    return `out of sample, one quarter ahead: the model missed by <b>${upct(bt.uncond)}</b>, “growth stays what it was” by ${upct(bt.naive)} — ` +
      `<span class="${win ? 'pos' : 'neg'}">${win ? 'the model is ahead' : 'the naive forecast is ahead'}</span>; its 80% ranges held ${upct(bt.cover80, 0)} of the time`;
  }
  function fcTable(fc, label) {
    if (!fc || !fc.length) return '<p class="muted small">No forecast: the year-ago quarters are not on file.</p>';
    return `<div class="tbl-wrap"><table class="small"><thead><tr><th>Quarter</th><th class="num">Growth Y/Y</th><th class="num">${esc(label || 'Revenue')}</th><th class="num">80% range</th></tr></thead><tbody>
      ${fc.map(([q, g, rev, lo, hi]) => `<tr><td>${esc(q)}</td><td class="num ${g > 0 ? 'pos' : g < 0 ? 'neg' : ''}">${pct(g)}</td><td class="num"><b>${rev != null ? usd(rev) : '—'}</b></td><td class="num muted">${lo != null ? `${usd(lo)} – ${usd(hi)}` : '—'}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function spark(series) {                    // the last 24 quarters of growth as bars
    if (!series || series.length < 4) return '';
    const W = 320, H = 60, n = series.length, w = W / n;
    const vals = series.map((r) => r[1]), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals) || 0.01;
    const y = (v) => H - 6 - (v - lo) / (hi - lo) * (H - 12), y0 = y(0);
    return `<svg class="mspark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="growth by quarter"><line x1="0" x2="${W}" y1="${y0.toFixed(1)}" y2="${y0.toFixed(1)}" stroke="#c9c7c0"/>` +
      series.map((r, i) => `<rect x="${(i * w + 1).toFixed(1)}" width="${Math.max(w - 2, 1).toFixed(1)}" y="${Math.min(y(r[1]), y0).toFixed(1)}" height="${Math.abs(y(r[1]) - y0).toFixed(1)}" fill="${r[1] >= 0 ? '#17734a' : '#b8432f'}"><title>${esc(r[0])}: ${pct(r[1])}</title></rect>`).join('') + '</svg>';
  }
  function modelLine(d, parentName) {
    const m = d.model;
    if (!m) return '';
    const own = m.own ? `fitted on its own ${m.n} quarters (${upct(m.dataw, 0)} of the beta from its own data, the rest from its ${esc(parentName)} peers)` : 'too few quarters of its own: the peers’ prior';
    return `<p class="small">Growth model: this quarter’s growth = ${pct(m.a, 1)} + <b>${m.rho.toFixed(2)}</b> × last quarter’s + <b>${m.gamma.toFixed(2)}</b> × ${esc(parentName)} growth (±${m.gamma_sd.toFixed(2)}); ${own}. Out of sample, ${verdict(m.bt).replace(/^out of sample, /, '')}.</p>`;
  }

  async function company(box, cik) {
    const d = await get(`model/c/${cik}.json`);
    if (!d || !box || !box.isConnected) return;
    const ind = d.industry_fc && d.industry_fc[0];
    box.innerHTML = `<div class="section-head"><h2>Growth model</h2><span class="muted">Revenue, year on year, against its industry — <a href="#model">how it works and how it has done</a></span></div>
      <div class="mgrid"><div><div class="mstat"><label>Latest Y/Y</label><b class="${d.g_now > 0 ? 'pos' : 'neg'}">${pct(d.g_now)}</b><span>${esc(d.last)}</span></div>
        <div class="mstat"><label>${esc(d.industry)}</label><b>${ind ? pct(ind[1]) : '—'}</b><span>industry, next quarter</span></div>
        ${spark(d.series)}</div>
        <div>${fcTable(d.fc)}</div></div>${modelLine(d, 'industry')}`;
    box.hidden = false;
  }

  async function industry(box, sic) {
    const d = await get(`model/i/${sic}.json`);
    if (!d || !box || !box.isConnected) return;
    const rows = (d.companies || []).filter((c) => c.model).slice(0, 40);
    box.innerHTML = `<div class="section-head"><h2>Growth model</h2><span class="muted">The industry’s same-company growth and forecast; each member’s beta to it — <a href="#model">how it works</a></span></div>
      <div class="mgrid"><div><div class="mstat"><label>Latest Y/Y</label><b class="${d.g_now > 0 ? 'pos' : 'neg'}">${pct(d.g_now)}</b><span>${esc(d.last)} · ${d.n_now} companies, ${usd(d.rev_ttm)} a year</span></div>${spark(d.series)}</div>
        <div>${fcTable(d.fc, 'Industry revenue')}</div></div>${modelLine(d, 'sector')}
      <div class="tbl-wrap"><table class="small"><thead><tr><th>Company</th><th class="num">Latest Y/Y</th><th class="num">Beta to industry</th><th class="num">Persistence</th><th class="num">Next quarter</th><th class="num">Model vs naive</th></tr></thead><tbody>
      ${rows.map((c) => `<tr><td><span class="mono">${esc(c.t)}</span> <a href="#c-${c.cik}">${esc(c.name)}</a></td><td class="num ${c.g_now > 0 ? 'pos' : 'neg'}">${pct(c.g_now)}</td>
        <td class="num">${c.model.gamma.toFixed(2)} <span class="muted">±${c.model.gamma_sd.toFixed(2)}</span></td><td class="num">${c.model.rho.toFixed(2)}</td>
        <td class="num">${c.fc && c.fc[0] ? `${pct(c.fc[0][1])}${c.fc[0][2] != null ? ' · ' + usd(c.fc[0][2]) : ''}` : '—'}</td>
        <td class="num">${c.model.bt ? `<span class="${c.model.bt.uncond < c.model.bt.naive ? 'pos' : 'neg'}">${upct(c.model.bt.uncond)} / ${upct(c.model.bt.naive)}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div>`;
    box.hidden = false;
  }

  async function sector(box, id) {
    const ix = await get('model/index.json');
    const d = ix && (ix.sectors || []).find((s) => s.id === id);
    if (!d || !box || !box.isConnected) return;
    const inds = (ix.industries || []).filter((i) => i.parent === id).slice(0, 30);
    box.innerHTML = `<div class="section-head"><h2>Growth model</h2><span class="muted">Same-company growth of the sector and its industries — <a href="#model">how it works</a></span></div>
      <div class="mgrid"><div><div class="mstat"><label>Latest Y/Y</label><b class="${d.g_now > 0 ? 'pos' : 'neg'}">${pct(d.g_now)}</b><span>${esc(d.last)} · ${d.n_now} companies</span></div>${spark(d.series)}</div>
        <div>${fcTable(d.fc, 'Sector revenue')}</div></div>${modelLine(d, 'market')}
      <div class="tbl-wrap"><table class="small"><thead><tr><th>Industry</th><th class="num">Companies</th><th class="num">Latest Y/Y</th><th class="num">Beta to sector</th><th class="num">Next quarter</th><th class="num">Model vs naive</th></tr></thead><tbody>
      ${inds.map((i) => `<tr><td><a href="#gamma-${esc(i.id)}">${esc(i.name)}</a></td><td class="num">${i.n_now || ''}</td><td class="num ${i.g_now > 0 ? 'pos' : 'neg'}">${pct(i.g_now)}</td>
        <td class="num">${i.model ? i.model.gamma.toFixed(2) : '—'}</td><td class="num">${i.fc && i.fc[0] ? pct(i.fc[0][1]) : '—'}</td>
        <td class="num">${i.model && i.model.bt ? `<span class="${i.model.bt.uncond < i.model.bt.naive ? 'pos' : 'neg'}">${upct(i.model.bt.uncond)} / ${upct(i.model.bt.naive)}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div>`;
    box.hidden = false;
  }

  async function concept(box, chainId) {
    const d = await get(`model/x/${chainId}.json`);
    if (!d || !box || !box.isConnected) return;
    const ix = await get('model/index.json');
    const layers = ((ix && ix.concepts) || []).filter((c) => c.kind === 'layer' && c.chain === chainId);
    const bu = d.bottom_up || [];
    box.innerHTML = `<div class="section-head"><h2>Growth model: the basket</h2><span class="muted">All of this chain’s companies as one revenue series, against the market — and the sum of each company’s own forecast</span></div>
      <div class="mgrid"><div><div class="mstat"><label>Latest Y/Y</label><b class="${d.g_now > 0 ? 'pos' : 'neg'}">${pct(d.g_now)}</b><span>${esc(d.last)} · ${d.n_now} companies, ${usd(d.rev_ttm)} a year</span></div>${spark(d.series)}</div>
        <div>${fcTable(d.fc, 'Basket revenue')}${bu.length ? `<p class="small muted">Bottom-up, the members’ own forecasts added: ${bu.map(([q, v, lo, hi, n]) => `${esc(q)} ${usd(v)} (${n})`).join(' · ')}</p>` : ''}</div></div>${modelLine(d, 'market')}
      ${layers.length ? `<div class="tbl-wrap"><table class="small"><thead><tr><th>Layer</th><th class="num">Companies</th><th class="num">Latest Y/Y</th><th class="num">Beta to market</th><th class="num">Next quarter</th><th class="num">Model vs naive</th></tr></thead><tbody>
      ${layers.map((L) => `<tr><td>${esc(L.name.split(' · ').slice(1).join(' · ') || L.name)} <span class="muted">${esc(L.zh || '')}</span></td><td class="num">${L.n_now || ''}</td><td class="num ${L.g_now > 0 ? 'pos' : 'neg'}">${pct(L.g_now)}</td>
        <td class="num">${L.model ? L.model.gamma.toFixed(2) : '—'}</td><td class="num">${L.fc && L.fc[0] ? pct(L.fc[0][1]) : '—'}</td>
        <td class="num">${L.model && L.model.bt ? `<span class="${L.model.bt.uncond < L.model.bt.naive ? 'pos' : 'neg'}">${upct(L.model.bt.uncond)} / ${upct(L.model.bt.naive)}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div>` : ''}`;
    box.hidden = false;
  }

  async function overview(app, ctx) {
    const here = ctx.live();
    ctx.setNav('model');
    const ix = await get('model/index.json');
    if (!here()) return;
    if (!ix) { app.innerHTML = '<div class="page-head"><h1>Growth model</h1><p class="muted">Not built yet: the next scan writes it.</p></div>'; return; }
    const S = ix.scores || {};
    const sc = (k, name) => {
      const s = S[k];
      if (!s) return '';
      return `<tr><td>${esc(name)}</td><td class="num">${s.entities}</td><td class="num">${upct(s.cond)}</td><td class="num"><b>${upct(s.uncond)}</b></td><td class="num">${upct(s.naive)}</td><td class="num">${upct(s.prior_only)}</td><td class="num">${s.beats_naive} of ${s.entities}</td><td class="num">${upct(s.cover80, 0)}</td></tr>`;
    };
    const m = ix.market;
    app.innerHTML = `<div class="page-head"><div class="eyebrow">One growth model, four levels</div><h1>Company, industry, sector, concept</h1>
      <p class="muted">Every company’s quarterly revenue, and every group’s (the sum of its members’, grown on the same companies), modelled the same way:
      this quarter’s year-on-year growth = a level + ρ × last quarter’s growth + γ × the parent’s growth. A company’s parent is its SIC industry, an industry’s
      its sector, a sector’s the market; a chain’s layer or a whole chain is a basket against the market. Each level’s prior comes from its siblings, so a company
      with three quarters on file is mostly its industry and one with thirty is mostly itself. Forecasts run top-down, four quarters ahead; every fit is tested
      out of sample, one quarter ahead, against the naive forecast that growth stays what it was.</p>
      <div class="meta"><span>Latest quarter ${esc(ix.asof)}</span><span>${ix.companies} companies</span><span>${(ix.industries || []).length} industries</span><span>${(ix.concepts || []).length} concepts</span><span>Built ${esc((ix.generated || '').slice(0, 10))}</span></div></div>
      <section class="section"><div class="section-head"><h2>How it has done</h2><span class="muted">Median one-quarter-ahead revenue error across the entities of each level</span></div>
      <div class="tbl-wrap"><table><thead><tr><th>Level</th><th class="num">Entities tested</th><th class="num">Model, parent known</th><th class="num">Model, full forecast</th><th class="num">Naive</th><th class="num">Prior alone</th><th class="num">Model beats naive</th><th class="num">80% ranges held</th></tr></thead>
      <tbody>${sc('sectors', 'Sectors')}${sc('industries', 'Industries (SIC)')}${sc('concepts', 'Concepts (chains and layers)')}${sc('companies', 'Companies')}</tbody></table></div>
      <p class="muted small">“Parent known” uses the parent’s actual growth for the quarter (how good the link is); “full forecast” forecasts the parent too. “Prior alone” is the
      siblings’ prior with no data of the entity’s own. A win at a level means the model’s median error is below the naive forecast’s.</p></section>
      <section class="section"><div class="section-head"><h2>The market</h2></div>
      <div class="mgrid"><div><div class="mstat"><label>Latest Y/Y</label><b class="${m.g_now > 0 ? 'pos' : 'neg'}">${pct(m.g_now)}</b><span>${esc(m.last)} · ${m.n_now} companies, ${usd(m.rev_ttm)} a year</span></div>${spark(m.series)}</div><div>${fcTable(m.fc, 'Market revenue')}</div></div>
      ${modelLine(Object.assign({}, m, { model: Object.assign({}, m.model, { gamma: m.model.rho, gamma_sd: 0 }) }), 'its own last quarter’s')}</section>
      <section class="section"><div class="section-head"><h2>Sectors</h2></div>
      <div class="tbl-wrap"><table><thead><tr><th>Sector</th><th class="num">Companies</th><th class="num">Latest Y/Y</th><th class="num">Beta to market</th><th class="num">Persistence</th><th class="num">Next quarter</th><th class="num">Next 4 quarters</th><th class="num">Model / naive</th></tr></thead><tbody>
      ${(ix.sectors || []).map((s) => `<tr><td><a href="#s-${esc(s.id)}">${esc(s.name)}</a></td><td class="num">${s.n_now}</td><td class="num ${s.g_now > 0 ? 'pos' : 'neg'}">${pct(s.g_now)}</td>
        <td class="num">${s.model ? s.model.gamma.toFixed(2) : '—'}</td><td class="num">${s.model ? s.model.rho.toFixed(2) : '—'}</td><td class="num">${s.fc && s.fc[0] ? pct(s.fc[0][1]) : '—'}</td>
        <td class="num">${s.fc && s.fc.length ? s.fc.map((f) => pct(f[1], 0)).join(' · ') : '—'}</td>
        <td class="num">${s.model && s.model.bt ? `<span class="${s.model.bt.uncond < s.model.bt.naive ? 'pos' : 'neg'}">${upct(s.model.bt.uncond)} / ${upct(s.model.bt.naive)}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div></section>
      <section class="section"><div class="section-head"><h2>Concepts</h2><span class="muted">Chains and their layers as baskets</span></div>
      <div class="tbl-wrap"><table class="small"><thead><tr><th>Concept</th><th class="num">Companies</th><th class="num">Latest Y/Y</th><th class="num">Beta to market</th><th class="num">Next quarter</th><th class="num">Next 4 quarters</th><th class="num">Model / naive</th></tr></thead><tbody>
      ${(ix.concepts || []).map((c) => `<tr><td>${c.kind === 'chain' ? `<a href="#chain-${esc(c.id)}"><b>${esc(c.name)}</b></a>` : `<span class="muted">↳</span> ${esc(c.name.split(' · ').slice(1).join(' · '))}`} <span class="muted">${esc(c.zh || '')}</span></td>
        <td class="num">${c.n_now || ''}</td><td class="num ${c.g_now > 0 ? 'pos' : 'neg'}">${pct(c.g_now)}</td><td class="num">${c.model ? c.model.gamma.toFixed(2) : '—'}</td>
        <td class="num">${c.fc && c.fc[0] ? pct(c.fc[0][1]) : '—'}</td><td class="num">${c.fc && c.fc.length ? c.fc.map((f) => pct(f[1], 0)).join(' · ') : '—'}</td>
        <td class="num">${c.model && c.model.bt ? `<span class="${c.model.bt.uncond < c.model.bt.naive ? 'pos' : 'neg'}">${upct(c.model.bt.uncond)} / ${upct(c.model.bt.naive)}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div></section>
      <section class="section"><div class="section-head"><h2>Industries</h2><span class="muted">By revenue; each opens its Gamma page with every member’s beta</span></div>
      <div class="tbl-wrap"><table class="small"><thead><tr><th>Industry</th><th>Sector</th><th class="num">Companies</th><th class="num">Latest Y/Y</th><th class="num">Beta to sector</th><th class="num">Next quarter</th><th class="num">Model / naive</th></tr></thead><tbody>
      ${(ix.industries || []).slice(0, 120).map((i) => `<tr><td><a href="#gamma-${esc(i.id)}">${esc(i.name)}</a></td><td class="muted">${esc(i.parent)}</td><td class="num">${i.n_now || ''}</td><td class="num ${i.g_now > 0 ? 'pos' : 'neg'}">${pct(i.g_now)}</td>
        <td class="num">${i.model ? i.model.gamma.toFixed(2) : '—'}</td><td class="num">${i.fc && i.fc[0] ? pct(i.fc[0][1]) : '—'}</td>
        <td class="num">${i.model && i.model.bt ? `<span class="${i.model.bt.uncond < i.model.bt.naive ? 'pos' : 'neg'}">${upct(i.model.bt.uncond)} / ${upct(i.model.bt.naive)}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div></section>
      <details class="section method-note"><summary>What the model is, and is not</summary>
      <p>Growth is revenue this quarter over the same quarter a year earlier, by calendar quarter (a fiscal quarter counts in the calendar quarter holding most of its
      days), in dollars (foreign filers converted at each quarter’s rate). A group’s growth is the sum over the members that have both quarters, so coverage changes
      are not growth. The regression is Bayesian with a structural prior — a ≈ 0, ρ ≈ 0.7, γ centred on the median beta of the entity’s siblings — chosen on a
      900-company sample because a loose prior, or one pooled from the siblings’ raw least-squares fits, forecast worse than the naive rule. The 80% ranges come from
      the posterior predictive, carrying the previous quarter’s uncertainty through ρ. Supply chains that spend (the AI data-center capex chain) also have their own
      model, where the suppliers follow the buyers’ capex with leads and lags — that one is on the chain’s page.</p>
      <p>It is a statistical model of reported growth, not of orders, guidance or prices; at the company level it is close to a tie with the naive forecast on the
      median, better given the industry’s actual growth, and the scores above say which levels it earns its keep at.</p></details>`;
  }

  global.FFModel = { company, industry, sector, concept, overview };
})(window);
