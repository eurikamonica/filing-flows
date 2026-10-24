/* Money flow Beta 1.0 (web/beta/money-flow.html): data/gamma/io-beta/<key>.json from pipeline/ioflow_beta.py.
   Drawn with the site's own Sankey (web/chains.js layout + web/sankey.js); every band and node opens its provenance. */
(function () {
  'use strict';
  const DATA = '../data/gamma/io-beta/';
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  function usd(v) {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    if (a >= 1e12) return s + (a / 1e12).toFixed(2) + 'T';
    if (a >= 1e9) return s + (a / 1e9).toFixed(a >= 1e11 ? 0 : a >= 1e10 ? 1 : 2) + 'B';
    if (a >= 1e6) return s + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + 'M';
    if (a >= 1e3) return s + (a / 1e3).toFixed(0) + 'K';
    return s + a.toFixed(0);
  }
  const pct = (v, d = 0) => (fin(v) ? (100 * v).toFixed(d) + '%' : '—');
  const range = (o) => (o && fin(o.lo) && fin(o.hi) ? `range ${usd(o.lo)} – ${usd(o.hi)}` : '');
  const grade = (g) => `<span class="g g-${esc(g)}" title="${esc(GR[g] || '')}">${esc(g)}</span>`;
  const GR = { A: 'Filed figure (SEC financial statements)', B: 'Computed from filed figures, or stated in the filing’s text',
    C: 'Industry average (input-output tables: BEA, FIGARO, ADB) applied to filed figures', D: 'Modelled allocation — not verified purchases' };
  const SUBL = { A: 'filed', B: 'computed from filings', C: 'estimate', D: 'modelled allocation' };
  const cache = {};
  const getJSON = (u) => cache[u] || (cache[u] = fetch(u, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }));
  const narrow = () => window.matchMedia('(max-width: 760px)').matches;
  let full = false;

  async function boot() {
    let idx = null;
    try { idx = await getJSON(DATA + 'index.json'); } catch (e) { /* no beta data yet */ }
    const body = $('#mf-body');
    if (!idx || !(idx.levels || []).length) { body.innerHTML = '<p class="muted">The beta data is not built yet: it appears after the next scan.</p>'; return; }
    $('#mf-list').innerHTML = idx.levels.map((l) => `<option value="${esc(l.key)}">${esc(l.title)} · ${l.companies} co.</option>`).join('');
    const go = () => {
      const q = $('#mf-q').value.trim().toLowerCase();
      if (!q) return;
      const hit = idx.levels.find((l) => l.key.toLowerCase() === q) || idx.levels.find((l) => l.title.toLowerCase().includes(q));
      if (hit) location.hash = hit.key; else body.innerHTML = `<p class="muted">No level matches “${esc(q)}”.</p>`;
    };
    $('#mf-go').addEventListener('click', go);
    $('#mf-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    const route = () => {
      const key = decodeURIComponent(location.hash.slice(1)) || new URLSearchParams(location.search).get('key') || '';
      if (key) show(key, idx); else body.innerHTML = '<p class="muted">Pick an industry (SIC code), a major group or a sector above.</p>' + failedNote(idx);
    };
    window.addEventListener('hashchange', route);
    route();
  }

  function failedNote(idx) {
    const f = idx.failed || [];
    return f.length ? `<details class="mf-note"><summary>${f.length} level(s) held back by the checks</summary><ul>${f.slice(0, 30).map((x) =>
      `<li><b>${esc(x.title)}</b>: ${esc((x.why || []).join('; '))}</li>`).join('')}</ul></details>` : '';
  }

  async function show(key, idx) {
    const body = $('#mf-body');
    body.innerHTML = '<p class="muted">Loading…</p>';
    let d;
    try { d = await getJSON(DATA + encodeURIComponent(key) + '.json'); } catch (e) {
      const f = (idx.failed || []).find((x) => x.key === key);
      body.innerHTML = f ? `<p>This level was <b>held back by the checks</b>: ${esc(f.why.join('; '))}.</p>` : '<p class="muted">No beta data for this level.</p>';
      return;
    }
    $('#mf-q').value = key;
    const F = d.filed || {}, E = d.estimate || {}, R = d.related || {};
    const lv = [['industry', 'This industry', R.industry], ['major', 'Major group', R.major], ['sector', 'Sector', R.sector]];
    const have = new Set(idx.levels.map((l) => l.key));
    let h = `<h2 style="font-size:19px;margin:6px 0 2px">${esc(d.title)}</h2>
      <p class="mf-sub">${esc(d.companies)} ${d.companies === 1 ? 'company' : 'companies'} · four quarters to the latest filing · BEA ${esc(d.source.io_year)} input-output, scaled to ${esc(d.source.scale_year)}</p>
      <div class="mf-pick" role="group" aria-label="Level">${lv.map(([k, lab, v]) => `<button type="button" class="mf-btn" data-lv="${esc(v || '')}" aria-pressed="${v === d.key}" ${v && have.has(v) ? '' : 'disabled'}>${lab}</button>`).join('')}</div>`;
    // the two layers
    h += `<div class="mf-h2">${grade('A')} From the filings</div><div class="mf-cards">
      ${card('Revenue', usd(F.revenue), 'four quarters, as filed')}
      ${card('Operating income', usd(F.oi), 'as filed')}
      ${card('Depreciation & amortization', usd(F.da), 'as filed')}
      ${card('Capital spending', usd(F.capex), 'as filed')}
      ${card('Operating cash flow', usd(F.ocf), F.ocf_n < d.companies ? `${F.ocf_n} of ${d.companies} companies report it` : 'as filed (CFO)')}
      ${card('Free cash flow', usd(F.fcf), 'operating cash flow − capital spending')}</div>
      <div class="mf-h2">${grade('B')} Computed from the filings</div><div class="mf-cards">
      ${card('EBITDA − capital spending', usd(F.ebitda_capex), 'operating income + D&A − capital spending. Not cash flow: before interest, tax and working capital')}
      ${(E.outside || {}).v ? card('Costs outside the US (not split)', usd(E.outside.v), 'no multi-country table covers it') : ''}
      ${card('US share of revenue', d.geo_n ? `${d.geo_n} of ${d.companies}` : 'not stated', d.geo_n ? 'companies state it in their 10-K; the rest are treated as all-US' : 'no company states it: all costs are split as if in the US')}</div>
      <div class="mf-h2">${grade('C')} Estimated from industry averages (BEA; FIGARO and ADB abroad)</div><div class="mf-cards">
      ${card('Purchased inputs — US', usd((E.purchases || {}).v), [range(E.purchases), merr(d, 'purchases')].filter(Boolean).join(' · '), true)}
      ${card('Employees — US', usd((E.employees || {}).v), [range(E.employees), merr(d, 'employees')].filter(Boolean).join(' · '), true)}
      ${card('Taxes on production — US', usd((E.taxes || {}).v), range(E.taxes), true)}
      ${card('Imports into the US', usd((E.imports || {}).v), 'by country of origin in the chart', true)}
      ${(E.purchases_out || {}).v ? card('Purchased inputs — outside the US', usd(E.purchases_out.v), [range(E.purchases_out), merr(d, 'purchases_out')].filter(Boolean).join(' · '), true) : ''}
      ${(E.employees_out || {}).v ? card('Employees — outside the US', usd(E.employees_out.v), 'FIGARO splits employee pay', true) : ''}
      ${(E.other_out || {}).v ? card('Employees & other costs — outside the US', usd(E.other_out.v), 'not separated: this table has no employee pay', true) : ''}</div>
      ${tablesNote(d)}`;
    h += `<div class="mf-legend"><span>Bands, darkest to lightest:</span>${['A', 'B', 'C', 'D'].map((g) =>
      `<span><i class="sw" style="background:rgba(47,109,179,${(0.15 + 0.37 * d.shade[g]).toFixed(2)})"></i>${grade(g)} ${esc(SUBL[g])}</span>`).join('')}</div>`;
    h += `<div class="mf-mob"><button type="button" class="mf-btn" id="mf-full">${full ? 'Show the first two columns' : 'Show the suppliers too (scroll sideways)'}</button></div>`;
    h += `<div id="mf-share"></div><div class="mf-chart" id="mf-chart"></div><p class="mf-dens" id="mf-dens"></p>
      <div class="mf-panel" id="mf-panel"><b>Click any band or bar</b> to see its source, formula, range and evidence grade.</div>`;
    h += members(d) + stated(d) + method(d);
    body.innerHTML = h;
    body.querySelectorAll('[data-lv]').forEach((b) => b.addEventListener('click', () => { if (b.dataset.lv) location.hash = b.dataset.lv; }));
    const fb = $('#mf-full');
    if (fb) fb.addEventListener('click', () => { full = !full; show(key, idx); });
    draw(d);
  }

  function merr(d, c) {
    const e = (d.model_error || {})[c];
    return e && fin(e.rel) ? `model error ±${pct(e.rel, 0)}` : '';
  }
  function errText(e) {
    return `${fin(e.rel) ? `±${pct(e.rel, 1)} · ` : ''}${Object.entries(e.vals || {}).map(([k, v]) => `${esc(k)} ${pct(v, 1)}`).join(' · ')} <span class="muted">(${esc(e.what)})</span>`;
  }
  function tablesNote(d) {
    const errs = Object.entries(d.model_error || {});
    const t = Object.values(d.tables || {}).map((x) => x.label).join(', ');
    return `<p class="mf-note" style="margin-top:6px">${t ? 'Multi-country tables: ' + esc(t) + '. ' : 'No multi-country table loaded: costs outside the US stay unsplit. '}` +
      (errs.length ? 'Model error, where the tables disagree: ' + errs.map(([c, e]) => `<b>${esc(c.replace('_out', ' (outside the US)'))}</b> ${errText(e)}`).join('; ') + '.' : '') + '</p>';
  }

  function card(label, value, note, est) {
    return `<div class="mf-card${est ? ' est' : ''}"><span>${esc(label)}</span><b>${value}</b>${note ? `<i>${esc(note)}</i>` : ''}</div>`;
  }

  // the analysis and the post for X, by rule from the level's figures
  function postFor(d, vin) {
    const F = d.filed || {}, rev = F.revenue || d.revenue || 0, share = (v) => (rev ? Math.round(100 * v / rev) + '%' : '—');
    const clean = (l) => String(l || '').replace(/\s*\((estimate|filed|computed[^)]*|not split[^)]*)\)/gi, '').trim();
    const uses = d.nodes.filter((n) => n.col === 1 && (vin[n.id] || 0) > 0).map((n) => [clean(n.label), vin[n.id]]).sort((a, b) => b[1] - a[1]);
    const sup = d.nodes.filter((n) => n.col === 3 && n.cik && (vin[n.id] || 0) > 0).map((n) => [n.label, vin[n.id], n.grade]).sort((a, b) => b[1] - a[1]);
    const told = sup.filter((x) => x[2] === 'B'), cty = d.nodes.filter((n) => /^c:/.test(n.id) && n.id !== 'c:other' && (vin[n.id] || 0) > 0).map((n) => [n.label, vin[n.id]]).sort((a, b) => b[1] - a[1]);
    const me = (d.model_error || {}).purchases;
    return { title: 'Money flow (beta) — ' + d.title,
      paras: [`${d.title}: ${usd(rev)} of revenue over four quarters across ${d.companies} ${d.companies === 1 ? 'company' : 'companies'} (filed). Operating cash flow ${usd(F.ocf)}, capital spending ${usd(F.capex)}, free cash flow ${usd(F.fcf)}.`,
        uses.length ? 'Where the revenue goes: ' + uses.slice(0, 5).map(([l, v]) => `${l} ${usd(v)} (${share(v)})`).join(', ') + '.' : '',
        cty.length ? 'Bought abroad or imported, by country (estimated): ' + cty.slice(0, 4).map(([l, v]) => `${l} ${usd(v)}`).join(', ') + '.' : '',
        told.length ? 'Suppliers a filing names: ' + told.slice(0, 3).map(([l, v]) => `${l} ${usd(v)}`).join(', ') + '.' : '',
        sup.some((x) => x[2] !== 'B') ? 'Largest modelled suppliers (an allocation by industry, not verified purchases): ' + sup.filter((x) => x[2] !== 'B').slice(0, 3).map(([l, v]) => `${l} ${usd(v)}`).join(', ') + '.' : '',
        me && fin(me.rel) ? `Model error on purchased inputs: ±${pct(me.rel, 0)} across ${Object.keys(me.vals || {}).join(', ')}.` : ''],
      lines: [`Where ${d.title}'s ${usd(rev)} goes (4Q):`, uses.length ? uses.slice(0, 3).map(([l, v]) => `${l} ${share(v)}`).join(' · ') + '.' : '', `OCF ${usd(F.ocf)} · FCF ${usd(F.fcf)} (filed).`,
        cty.length ? 'Abroad: ' + cty.slice(0, 3).map(([l]) => l).join(', ') + '.' : '', me && fin(me.rel) ? `Model error ±${pct(me.rel, 0)}.` : '', 'Beta: IO-table estimates (BEA, FIGARO, ADB, OECD).'] };
  }
  function sceneFor(d, ncol, vin, vout) {
    const nodes = d.nodes.filter((n) => n.col < ncol).map((n) => ({ id: n.id, col: n.col, t: n.label, label: n.col === 0 ? n.label : SUBL[n.grade],
      v: Math.max(vin[n.id] || 0, vout[n.id] || 0), color: n.color, cik: n.cik, grade: n.grade })).filter((n) => n.v > 0);
    const ids = new Set(nodes.map((n) => n.id));
    const links = d.links.filter((l) => ids.has(l[0]) && ids.has(l[1])).map((l) => {
      const p = d.prov[l[0] + '|' + l[1]] || {};
      return { s: l[0], t: l[1], v: l[2], k: d.shade[p.grade] != null ? d.shade[p.grade] : 0.2 };
    });
    const cols = d.cols.slice(0, ncol).map((c, i) => ({ id: 'c' + i, name: `${c.name} · % of ${usd(c.den)}` }));
    return window.FFChains.layout({ cols, nodes, links }, {
      title: 'Money flow (beta 1.1) — ' + d.title,
      subtitle: `${usd(d.revenue)} revenue over four quarters · ${d.companies} ${d.companies === 1 ? 'company' : 'companies'} · darker bands are filed or computed figures, lighter ones estimates`,
      footer: ['Beta 1.1. Filed figures from SEC filings; US spending split by BEA input-output (' + d.source.io_year + ', scaled to ' + d.source.scale_year + '), spending abroad and imports by origin by ' + (Object.values(d.tables || {}).map((t) => t.label).join(', ') || 'no multi-country table') + '; suppliers by revenue share unless a filing names them (✓).',
        'Supplier amounts without ✓ are a modelled allocation, not verified purchases. Not investment advice.'] });
  }
  function draw(d) {
    const host = $('#mf-chart');
    if (!window.FFChains || !window.Sankey) { host.innerHTML = '<p class="muted" style="padding:12px">The chart library did not load.</p>'; return; }
    const compact = narrow() && !full;
    const ncol = compact ? 2 : 4;
    const vin = {}, vout = {};
    d.links.forEach((l) => { vout[l[0]] = (vout[l[0]] || 0) + l[2]; vin[l[1]] = (vin[l[1]] || 0) + l[2]; });
    const sh = $('#mf-share');                          // the saved picture is always the full four-column chart
    if (sh && window.FFShare) sh.innerHTML = window.FFShare.bar({ key: 'money-flow-beta-' + d.key, title: 'Money flow (beta) — ' + d.title, scene: () => sceneFor(d, 4, vin, vout), post: () => postFor(d, vin) });
    if (compact) return drawList(d, host, vin);
    const scene = sceneFor(d, ncol, vin, vout);
    host.classList.toggle('compact', compact);
    host.innerHTML = window.Sankey.toSVG(scene, 'Money flow (beta)');
    $('#mf-dens').innerHTML = d.cols.slice(0, ncol).map((c, i) => `<b>Column ${i + 1}</b> percentages are of ${usd(c.den)}: ${esc(c.den_what)}.`).join(' ') +
      (compact ? ' On a phone the first two columns are shown; the button above adds the suppliers.' : '');
    const svg = host.querySelector('svg');
    const byId = new Map(d.nodes.map((n) => [n.id, n]));
    svg.addEventListener('click', (ev) => {
      const band = ev.target.closest && ev.target.closest('.band');
      const g = ev.target.closest && ev.target.closest('[data-node]');
      svg.querySelectorAll('.band.on').forEach((p) => p.classList.remove('on'));
      host.classList.toggle('sel', !!(band || g));
      if (band) {
        band.classList.add('on');
        panelLink(d, band.dataset.s, band.dataset.t, byId);
      } else if (g) {
        const id = g.dataset.node;
        svg.querySelectorAll('.band').forEach((p) => { if (p.dataset.s === id || p.dataset.t === id) p.classList.add('on'); });
        panelNode(d, id, byId, vin, vout);
      }
    });
  }

  // on a phone: where the revenue goes, as readable bars (the full chart is one tap away)
  function drawList(d, host, vin) {
    const byId = new Map(d.nodes.map((n) => [n.id, n]));
    const rows = d.nodes.filter((n) => n.col === 1 && (vin[n.id] || 0) > 0).map((n) => [n, vin[n.id]]).sort((a, b) => b[1] - a[1]);
    const tot = rows.reduce((a, r) => a + r[1], 0) || 1;
    host.classList.add('compact');
    host.innerHTML = `<div style="padding:12px 12px 6px"><b style="font-size:15px">Where ${usd(tot)} goes</b><div class="muted" style="font-size:12.5px;margin:2px 0 10px">% of revenue · tap a row for its formula</div>` +
      rows.map(([n, v]) => `<button type="button" data-row="${esc(n.id)}" style="display:block;width:100%;text-align:left;border:0;background:none;padding:6px 0;cursor:pointer;color:inherit;font:inherit">
        <span style="display:flex;justify-content:space-between;gap:8px;font-size:14px"><span>${grade(n.grade)} ${esc(n.label)}</span><b style="white-space:nowrap">${usd(v)} · ${pct(v / tot, v / tot < 0.1 ? 1 : 0)}</b></span>
        <span style="display:block;height:8px;border-radius:4px;margin-top:4px;background:${esc(n.color)};opacity:${n.grade === 'A' || n.grade === 'B' ? 1 : 0.45};width:${Math.max(1.5, 100 * v / tot).toFixed(1)}%"></span></button>`).join('') + '</div>';
    host.querySelectorAll('[data-row]').forEach((b) => b.addEventListener('click', () => {
      const id = b.dataset.row;
      const l = d.links.filter((x) => x[1] === id);
      if (l.length === 1) panelLink(d, l[0][0], id, byId); else panelNode(d, id, byId, vin, {});
    }));
    $('#mf-dens').innerHTML = `Percentages are of ${usd(tot)}: revenue (plus borrowing where spending exceeded it). The button above shows the full chart with the supplying industries and suppliers.`;
  }

  function panelLink(d, s, t, byId) {
    const p = d.prov[s + '|' + t];
    const a = byId.get(s), b = byId.get(t);
    if (!p) return;
    const rows = [['Evidence', `${grade(p.grade)} ${esc(GR[p.grade])}`], ['Amount', usd(p.v)]];
    if (fin(p.lo) && fin(p.hi) && (p.lo !== p.v || p.hi !== p.v)) rows.push(['Range', `${usd(p.lo)} – ${usd(p.hi)} <span class="muted">(${esc(p.range_how || '10th–90th percentile of similar BEA industries')})</span>`]);
    if (fin(p.coef)) rows.push(['Coefficient', pct(p.coef, 1)]);
    if (p.formula) rows.push(['Formula', esc(p.formula)]);
    if (p.source) rows.push(['Source', esc(p.source) + (p.url ? ` · <a href="${esc(p.url)}" target="_blank" rel="noopener">filing ↗</a>` : '')]);
    if (p.note) rows.push(['Note', `<b>${esc(p.note)}</b>`]);
    if (p.err) rows.push(['Model error', errText(p.err)]);
    $('#mf-panel').innerHTML = `<h3>${esc(a ? a.label : s)} → ${esc(b ? b.label : t)}</h3><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>` +
      (p.quote ? `<blockquote>“${esc(p.quote)}”</blockquote>` : '');
  }

  function panelNode(d, id, byId, vin, vout) {
    const n = byId.get(id);
    if (!n) return;
    const v = Math.max(vin[id] || 0, vout[id] || 0);
    const m = n.cik ? (d.members || []).find((x) => x.cik === n.cik) : null;
    let extra = '';
    if (m && n.col === 0) {
      extra = `<dl><dt>Revenue</dt><dd>${usd(m.revenue)} ${grade('A')}</dd><dt>Operating income</dt><dd>${usd(m.oi)}</dd><dt>D&amp;A</dt><dd>${usd(m.da)}</dd>
        <dt>Capital spending</dt><dd>${usd(m.capex)}</dd><dt>Operating cash flow</dt><dd>${usd(m.ocf)}</dd><dt>Free cash flow</dt><dd>${usd(m.fcf)}</dd>
        <dt>US share of revenue</dt><dd>${m.us != null ? pct(m.us) + ' ' + grade('B') : 'not stated: costs split as if all in the US'}</dd>
        <dt>Source</dt><dd>${esc(m.form || '')} to ${esc(m.end)}${m.doc ? ` · <a href="${esc(m.doc)}" target="_blank" rel="noopener">filing ↗</a>` : ''}</dd></dl>` +
        (m.geo ? `<blockquote>“${esc(m.geo.text)}”</blockquote>` : '');
    }
    $('#mf-panel').innerHTML = `<h3>${esc(n.label)} ${grade(n.grade)}</h3><p style="margin:0">${usd(v)} · ${esc(GR[n.grade])}</p>${extra}` +
      (n.cik && n.col > 0 ? `<p style="margin:6px 0 0"><a href="../#c-${encodeURIComponent(n.cik)}">Company page ↗</a></p>` : '') +
      '<p class="muted" style="margin:6px 0 0">Its bands are highlighted; click one for its formula.</p>';
  }

  function members(d) {
    const ms = d.members || [];
    if (!ms.length) return '';
    return `<div class="mf-h2">Companies: what their filings say</div><div class="mf-wrap"><table class="mf-tbl"><thead><tr><th>Company</th><th class="n">Revenue</th><th class="n">Op. income</th><th class="n">D&amp;A</th><th class="n">Capex</th><th class="n">Op. cash flow</th><th class="n">Free cash flow</th><th class="n">US share</th><th>Abroad split by</th><th>Industry mix</th></tr></thead><tbody>` +
      ms.map((m) => `<tr><td><a href="../#c-${m.cik}"><b>${esc(m.ticker || m.name)}</b></a> <span class="muted">SIC ${esc(m.sic)}</span></td><td class="n">${usd(m.revenue)}</td><td class="n">${usd(m.oi)}</td><td class="n">${usd(m.da)}</td><td class="n">${usd(m.capex)}</td><td class="n">${usd(m.ocf)}</td><td class="n">${usd(m.fcf)}</td>
        <td class="n">${m.us != null ? `<span title="${esc(m.geo.text)}">${pct(m.us)}</span>` : '<span class="muted">not stated</span>'}</td>
        <td>${m.abroad ? esc(m.abroad) + (m.home ? ` · home ${esc(m.home)}` : '') : '<span class="muted">—</span>'}</td>
        <td>${m.segments ? m.segments.map((s) => `${esc(s.segment)} ${pct(s.share)} → ${esc(s.bea_name)}`).join('<br>') : '<span class="muted">its SIC code</span>'}</td></tr>`).join('') +
      '</tbody></table></div>';
  }

  function stated(d) {
    const ss = d.stated || [];
    return `<div class="mf-h2">${grade('B')} Supply relationships named in filings</div>` + (ss.length ? `<div class="mf-wrap"><table class="mf-tbl"><thead><tr><th>Buyer</th><th>Supplier</th><th class="n">Stated</th><th class="n">Drawn</th><th>Evidence</th></tr></thead><tbody>` +
      ss.map((s) => `<tr><td>${esc(s.buyer)}</td><td><a href="../#c-${s.cik}">${esc(s.t || s.name)}</a></td><td class="n">${usd(s.usd)}</td><td class="n">${s.drawn ? usd(s.drawn) + (s.capped ? ' (capped)' : '') : '<span class="muted">not drawn</span>'}</td>
        <td>${esc(s.form || '10-K')} ${esc(s.fy || '')} · ${s.by === 'self' ? 'the buyer names it' : 'the supplier names the buyer'}${s.url ? ` · <a href="${esc(s.url)}" target="_blank" rel="noopener">filing ↗</a>` : ''}${s.q ? `<br><span class="muted">“${esc(s.q)}”</span>` : ''}</td></tr>`).join('') +
      '</tbody></table></div><p class="mf-note">Drawn as solid bands (✓) through the supplier’s industry, taken out of that industry’s modelled allocation; capped where a stated amount exceeds the model’s purchases from the industry.</p>'
      : '<p class="mf-note">No filing of these companies or their suppliers names a supply relationship with dollars: every supplier amount here is a modelled allocation.</p>');
  }

  function method(d) {
    return `<div class="mf-h2">How this is built</div><div class="mf-note">
      <p><b>Grades.</b> ${['A', 'B', 'C', 'D'].map((g) => `${grade(g)} ${esc(GR[g])}`).join(' · ')}.</p>
      <p><b>Spending.</b> Revenue − operating income − D&amp;A (four quarters, filed) is the cash operating cost. The US share of it (from the 10-K’s own sentence on revenue outside the United States, where there is one) is split into purchased inputs, employees and taxes on production as BEA’s Use table splits the industry’s spending; the rest is “Costs outside the US (not split)”. A company that reports business segments has each segment matched by name to a BEA industry of the same kind.</p>
      <p><b>Outside the US (Beta 1.1).</b> The share of costs outside the US (the 10-K’s own sentence), and all of a foreign filer’s costs (its home country from its SEC registration), are split like that country’s industry in the multi-country tables: Eurostat FIGARO first (the only one with employee pay), then ADB MRIO, then OECD ICIO when it is loaded. US imports and purchases abroad are shown by the country they are bought in. Industries are matched through ISIC divisions.</p>
      <p><b>Model error.</b> The same industry looks different in each table (definitions, years, how imports are allocated). Where two or more tables cover it, half the spread of their figures (purchased inputs ÷ output) is shown as the model error and widens the range.</p>
      <p><b>Ranges.</b> The 10th–90th percentile of the same coefficient among similar BEA industries (same first three digits of the code): how much the estimate moves if the company looks like a neighbouring industry.</p>
      <p><b>What is left.</b> Revenue − cash operating cost − capital spending = operating income + D&amp;A − capital spending (“EBITDA − capital spending”). It is not operating cash flow, which is shown beside it as filed.</p>
      <p><b>Checks passed before publishing:</b></p><ul class="mf-checks">${(d.checks || []).map((c) => `<li>✓ ${esc(c)}</li>`).join('')}</ul>
      <p>Sources: SEC filings; <a href="https://www.bea.gov/industry/input-output-accounts-data" target="_blank" rel="noopener">BEA input-output accounts</a> (${esc(d.source.use || '')}); BEA fixed assets; Census SIC/NAICS concordances. Built ${esc((d.generated || '').slice(0, 10))}.</p></div>`;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
