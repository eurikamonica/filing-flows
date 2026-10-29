/* Beyond the filings — one company outside its 10-Q and 10-K (the "Beyond the filings" view of each company page, listed
   in views.json; the Disclosure Hub's tab of the same name draws the cross-company lists): its clinical pipeline
   (ClinicalTrials.gov), recalls (FDA, CPSC, NHTSA), the Federal Register documents that name it, its political action
   committee (FEC), attention (Wikipedia page views) and how its margins have moved with energy, wage and metal costs.
   Data: data/research/outside/c/<cik>.json and costs.json (app/outside.py, branch research-outside).
   window.OutsideView.render(el, {cik, hub, here}) — hub: the path to the hub ('disclosures/' on the Sankey site, '' inside it). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? (+v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e9 ? '$' + (a / 1e9).toFixed(1) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? '$' + (a / 1e3).toFixed(0) + 'K' : '$' + Math.round(a)); };
  const pts = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(1) + ' pts' : '—');
  const pc = (v, d = 0) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—');
  const PH = { EARLY_PHASE1: 'Early phase 1', PHASE1: 'Phase 1', PHASE2: 'Phase 2', PHASE3: 'Phase 3', PHASE4: 'Phase 4' };
  const ST = { RECRUITING: 'recruiting', ACTIVE_NOT_RECRUITING: 'active, not recruiting', NOT_YET_RECRUITING: 'not yet recruiting', ENROLLING_BY_INVITATION: 'by invitation' };
  const TYPE = { Rule: 'Rule', 'Proposed Rule': 'Proposed rule', Notice: 'Notice', 'Presidential Document': 'Presidential document' };
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.ov{display:grid;gap:14px}.ov .ov-card{border:1px solid var(--line,#d0d5dd);border-radius:8px;padding:12px 14px;min-width:0;overflow:hidden}
.ov h3{margin:0 0 6px;font-size:1rem}.ov .ov-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}.ov .ov-big{font-size:1.5rem;font-weight:600;margin-right:6px}
.ov table{border-collapse:collapse;width:100%;min-width:0!important;font-size:.85rem}.ov td,.ov th{padding:3px 6px;border-bottom:1px solid var(--line,#e4e7ec);text-align:left;vertical-align:top;white-space:normal;overflow-wrap:anywhere}
.ov th{position:static}.ov td.n,.ov th.n{text-align:right;white-space:nowrap;overflow-wrap:normal;font-variant-numeric:tabular-nums}.ov .muted{opacity:.75;font-size:.82rem}.ov svg{display:block;width:100%;height:auto;max-width:820px}
.ov .ov-bar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:.85rem}.ov .ov-bar b{display:inline-block;height:12px;border-radius:3px;background:#3b6fb6}.ov .ov-bar span{min-width:92px}
.ov .ov-wide{grid-column:1/-1}.ov td.d{white-space:nowrap;overflow-wrap:normal}.ov td.l{min-width:9em}.ov .bad{color:#b42318}.ov .ok{color:#17734a}.ov .ov-tag{display:inline-block;font-size:.72rem;border:1px solid currentColor;border-radius:999px;padding:0 6px;opacity:.8}`;
    document.head.appendChild(s);
  }
  const cache = {};
  const load = (hub, path) => (cache[hub + path] = cache[hub + path] || fetch(`${hub}data/research/outside/${path}`, { cache: 'no-cache' }).then((r) => {
    if (!r.ok) { const e = new Error(r.status === 404 ? 'none' : 'HTTP ' + r.status); e.status = r.status; throw e; }
    return r.json();
  }).catch((e) => { delete cache[hub + path]; throw e; }));

  function pipeline(t) {
    if (!t) return '';
    const P = Object.keys(PH), m = Math.max(1, ...P.map((p) => (t.phases[p] || {}).active || 0));
    const bars = P.map((p) => { const a = (t.phases[p] || {}).active || 0; return `<div class="ov-bar"><span>${PH[p]}</span><b style="width:${Math.max(a ? 3 : 0, 70 * a / m)}%"></b>${num(a)} <span class="muted">of ${num((t.phases[p] || {}).all)}</span></div>`; }).join('');
    const due = (t.due || []).slice(0, 12);
    return `<div class="ov-card"><h3>Clinical pipeline</h3><p><span class="ov-big">${num(t.active)}</span>active studies · ${num(t.studies)} on record · ${num(t.completed_2y)} completed in the last two years</p>
      ${bars}<p class="muted">Active studies by their highest phase (bar), of all studies in that phase ever registered. Lead sponsor on ClinicalTrials.gov: ${esc(t.sponsor)}.</p>
      ${due.length ? `<h3 style="margin-top:10px">Primary completions due (phase 2 and 3, next 18 months)</h3><table><thead><tr><th>Due</th><th>Phase</th><th>Study</th><th class="n">Patients</th></tr></thead><tbody>
      ${due.map((s) => `<tr><td class="d">${esc(s[4] || '—')}</td><td>${esc(PH[s[2]] || '—')}</td><td><a href="https://clinicaltrials.gov/study/${esc(s[0])}" target="_blank" rel="noopener">${esc(s[1])}</a><br><span class="muted">${esc(s[6])}${s[7] ? ' · ' + esc(s[7]) : ''} · ${esc(ST[s[3]] || s[3])}</span></td><td class="n">${num(s[5])}</td></tr>`).join('')}</tbody></table>
      <p class="muted">The date the main result is expected (the sponsor's estimate, often moved). Results are usually announced after it — a catalyst for the stock.</p>` : ''}
      ${(t.conditions || []).length ? `<p class="muted">Most studied in active trials: ${t.conditions.slice(0, 8).map(([c, n]) => `${esc(c)} (${n})`).join(', ')}.</p>` : ''}</div>`;
  }
  function recalls(r) {
    if (!r) return '';
    const yrs = r.by_year || [], m = Math.max(1, ...yrs.map((y) => y[1]));
    return `<div class="ov-card"><h3>Recalls</h3><p><span class="ov-big ${r.last_12m ? 'bad' : ''}">${num(r.last_12m)}</span>in the last 12 months · ${num(r.n)} in five years${r.class1 ? ` · <b class="bad">${num(r.class1)} Class I</b> (the most serious)` : ''}${r.units_12m ? ` · ${num(r.units_12m)} vehicles affected this year` : ''}</p>
      ${yrs.map(([y, n]) => `<div class="ov-bar"><span>${esc(y)}</span><b style="width:${70 * n / m}%;background:#b54708"></b>${n}</div>`).join('')}
      <p class="muted">${Object.entries(r.by_source || {}).map(([s, n]) => `${esc(s)}: ${n}`).join(' · ')}</p>
      <table><thead><tr><th>Date</th><th>Recall</th></tr></thead><tbody>${(r.latest || []).slice(0, 8).map((x) => `<tr><td class="d">${esc(x.date)}<br><span class="muted">${esc(x.source)}</span></td>
        <td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.what)}</a>` : esc(x.what)}<br><span class="muted">${[x.class ? (x.class === 'Class I' ? '<b class="bad">Class I</b>' : esc(String(x.class).toLowerCase())) : '', x.why ? esc(String(x.why).length > 110 ? String(x.why).slice(0, 108) + '…' : x.why) : '', x.firm ? 'as ' + esc(x.firm) : ''].filter(Boolean).join(' · ')}</span></td></tr>`).join('')}</tbody></table>
      <p class="muted">FDA enforcement reports (drugs, devices, food), CPSC consumer products and NHTSA vehicles, matched by the recalling firm's name (its own and its known brands). A company not matched shows nothing here — not "no recalls".</p></div>`;
  }
  function regulation(f) {
    if (!f) return '';
    return `<div class="ov-card"><h3>In the Federal Register</h3><p><span class="ov-big">${num(f.count)}</span>documents named “${esc(f.query)}” since ${esc(f.since)}</p>
      ${(f.agencies_recent || []).length ? `<p class="muted">Agencies (latest 20): ${f.agencies_recent.map(([a, n]) => `${esc(a)} (${n})`).join(', ')}</p>` : ''}
      <table><tbody>${(f.docs || []).slice(0, 8).map((d) => `<tr><td class="d">${esc(d[0])}<br><span class="ov-tag">${esc(TYPE[d[1]] || d[1])}</span></td><td><a href="${esc(d[4])}" target="_blank" rel="noopener">${esc(d[3])}</a><br><span class="muted">${esc(d[2])}</span></td></tr>`).join('')}</tbody></table>
      <p class="muted">Rules, proposed rules and notices: arms sales, permits, approvals, enforcement, rate cases. A search for the company's name, so an occasional document only mentions it.</p></div>`;
  }
  function politics(p) {
    if (!p) return '';
    const cy = Object.entries(p.cycles || {}).sort((a, b) => b[0] - a[0]);
    return `<div class="ov-card"><h3>Political action committee</h3><table><thead><tr><th>Cycle</th><th class="n">Raised</th><th class="n">Spent</th><th class="n">To candidates</th></tr></thead><tbody>
      ${cy.map(([c, v]) => `<tr><td>${esc(+c - 1)}–${esc(c)}</td><td class="n">${big(v.receipts)}</td><td class="n">${big(v.disbursements)}</td><td class="n">${big(v.to_candidates)}</td></tr>`).join('')}</tbody></table>
      ${(p.top_recipients || []).length ? `<p class="muted">Largest recipients this cycle: ${p.top_recipients.slice(0, 10).map(([n, v]) => `${esc(n)} ${big(v)}`).join(' · ')}</p>` : ''}
      <p class="muted">${(p.pacs || []).map((x) => `<a href="https://www.fec.gov/data/committee/${esc(x[0])}/" target="_blank" rel="noopener">${esc(x[1])}</a>`).join(' · ')} — FEC filings. A PAC's money comes from employees' voluntary donations, not the company's treasury.</p></div>`;
  }
  function attention(a) {
    if (!a || !(a.weeks || []).length) return '';
    const W = 640, H = 160, L = 46, B = 22, T = 8, R = 8, w = a.weeks, vals = w.map((x) => x[1]), hi = Math.max(...vals) || 1;
    const X = (i) => L + i / Math.max(1, w.length - 1) * (W - L - R), Y = (v) => T + (1 - v / hi) * (H - T - B);
    const path = w.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(x[1]).toFixed(1)}`).join(' ');
    const yr = [...new Set(w.map((x) => x[0].slice(0, 4)))];
    return `<div class="ov-card"><h3>Attention: Wikipedia page views</h3><p><span class="ov-big ${fin(a.ratio) && a.ratio >= 2 ? 'bad' : ''}">${fin(a.ratio) ? num(a.ratio, 1) + '×' : '—'}</span>the last week's daily views (${num(a.avg7)}) against the 90 days before (${num(a.avg90)})</p>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly Wikipedia page views"><path d="${path}" fill="none" stroke="#3b6fb6" stroke-width="2"/>
      <text x="${L - 4}" y="${T + 9}" font-size="10" text-anchor="end">${num(hi)}</text><text x="${L - 4}" y="${H - B}" font-size="10" text-anchor="end">0</text>
      ${yr.map((y) => { const i = w.findIndex((x) => x[0].startsWith(y)); return i > 0 ? `<text x="${X(i)}" y="${H - 6}" font-size="10" text-anchor="middle">${y}</text>` : ''; }).join('')}</svg>
      <p class="muted">Weekly views of “${esc(String(a.article || '').replace(/_/g, ' '))}” on English Wikipedia (people, not bots). Busiest days this year: ${(a.peaks || []).map((p) => `${esc(p[0])} (${num(p[1])})`).join(', ')}. Spikes follow news; a rise in attention often comes with heavier trading.</p></div>`;
  }
  function costs(c, C) {
    if (!c || !C || !C.inputs) return '';
    const sec = (C.sectors || {})[c._sector] || {};
    const rows = C.inputs.filter(([k]) => c[k] && (fin(c[k].shrunk_om) || fin(c[k].shrunk_gm)));
    if (!rows.length) return '';
    return `<div class="ov-card ov-wide"><h3>Cost shocks: margins against input prices</h3><div style="overflow-x:auto"><table><thead><tr><th>Input</th><th class="n">Last year</th><th class="n">Gross margin per +10%</th><th class="n">Operating margin per +10%</th><th class="n">Sector (op.)</th><th class="n">Effect of last year's move</th></tr></thead><tbody>
      ${rows.map(([k, l, sid, q, yoy]) => { const f = c[k], s = sec[k] || {}, b = fin(f.shrunk_om) ? f.shrunk_om : f.shrunk_gm; return `<tr><td class="l">${esc(l)}<br><span class="muted">${esc(sid)}${q ? ' · ' + esc(q) : ''}</span></td><td class="n">${pc(fin(yoy) ? Math.expm1(yoy) : null)}</td>
        <td class="n">${pts(fin(f.shrunk_gm) ? f.shrunk_gm * Math.log(1.1) : null)}</td><td class="n">${pts(fin(f.shrunk_om) ? f.shrunk_om * Math.log(1.1) : null)}</td><td class="n">${pts(fin(s.b_om) ? s.b_om * Math.log(1.1) : null)}</td>
        <td class="n">${pts(fin(b) && fin(yoy) ? b * yoy : null)}</td></tr>`; }).join('')}</tbody></table></div>
      <p class="muted">Year-on-year change in the company's quarterly margins against the year-on-year change of each input price (${num(Math.max(...rows.map(([k]) => c[k].n || 0)))} quarters at most), blended with its sector's (the fewer the quarters, the more the sector counts). One input at a time: oil, diesel and jet fuel move together and share an effect. A history, not a forecast; contracts, hedges and pricing power change it.</p></div>`;
  }
  async function render(el, opt) {
    css();
    const hub = (opt && opt.hub) || '', cik = String((opt && opt.cik) || '').replace(/^0+/, '');
    el.innerHTML = '<p class="muted">Reading what public data says beyond the filings…</p>';
    let d = null, C = null;
    try { [d, C] = await Promise.all([load(hub, `c/${cik}.json`).catch((e) => { if (e.status === 404) return null; throw e; }), load(hub, 'costs.json').catch(() => null)]); }
    catch (e) { if (el.isConnected) el.innerHTML = `<div class="ov-card"><p class="muted">Beyond the filings is temporarily unavailable (${esc(e.message)}).</p></div>`; return; }
    if ((opt && opt.here && !opt.here()) || !el.isConnected) return;
    if (!d) { el.innerHTML = '<div class="ov"><div class="ov-card"><h3>Beyond the filings</h3><p class="muted">Nothing matched for this company yet: no clinical trials, recalls, Federal Register documents, PAC or Wikipedia article found under its name. Matching is by name and conservative, so this is not proof of none.</p></div></div>'; return; }
    if (d.costs) d.costs._sector = d.sector;
    const parts = [pipeline(d.trials), recalls(d.recalls), regulation(d.fedreg), politics(d.fec), attention(d.attention), costs(d.costs, C)].filter(Boolean);
    el.innerHTML = `<div class="ov"><div class="ov-card"><h3>${esc(d.name)} <span class="muted">${esc(d.ticker)} · beyond the filings</span></h3>
      <p class="muted">Free public sources outside the 10-Q and 10-K: ClinicalTrials.gov, FDA, CPSC and NHTSA recalls, the Federal Register, the FEC, Wikipedia and FRED. Updated daily. ${hub ? `<a href="${hub}#outside">Every company →</a>` : ''}</p></div>
      <div class="ov-grid">${parts.join('')}</div></div>`;
  }
  window.OutsideView = { render };
})();
