/* Beyond the filings — the hub tab: what free public data says about companies outside their filings. Clinical
   catalysts due (ClinicalTrials.gov), the latest recalls (FDA, CPSC, NHTSA), the Federal Register, political action
   committees (FEC), attention spikes (Wikipedia page views) and cost shocks by sector (FRED inputs against margins).
   One company: OutsideView (outside-view.js, also the "Beyond the filings" view of each company page).
   Data: data/research/outside/{index,lists,costs,status}.json (app/outside.py, branch research-outside).
   Deep links: #outside/<view>, #outside/<TICKER>. */
const ouStore = {};
function ouData(name) {
  const m = ouStore[name] || (ouStore[name] = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/research/outside/' + name + '.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(d => { m.data = d; if (state.tab === 'outside') render() }).catch(e => { m.err = e.message; if (state.tab === 'outside') render() });
  return m;
}
const OU_VIEWS = [['companies', 'Every company'], ['catalysts', 'Clinical catalysts due'], ['recalls', 'Latest recalls'], ['regulation', 'Federal Register'],
  ['attention', 'Attention spikes (Wikipedia)'], ['politics', 'Political action committees'], ['costs', 'Cost shocks by sector'], ['one', 'One company']];
const OU_PH = { EARLY_PHASE1: 'Early 1', PHASE1: '1', PHASE2: '2', PHASE3: '3', PHASE4: '4' };
const ouN = (v, d = 0) => v == null || !Number.isFinite(+v) ? '—' : (+v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
const ouTk = (t, cik) => `<button class="text-button" data-out="${esc(cik)}" data-outt="${esc(t)}"><b>${esc(t)}</b></button>`;
function ouRows(d) { const F = d.fields || []; return (d.rows || []).map(r => { const o = {}; F.forEach((k, i) => o[k] = r[i]); return o }) }
function ouCompanies(d) {
  const S = [['revenue', 'Revenue'], ['trials_active', 'Active trials'], ['phase3_active', 'Phase 3 active'], ['catalysts', 'Catalysts due'], ['recalls_12m', 'Recalls, 12 months'],
    ['class1', 'Class I recalls'], ['fedreg_12m', 'Federal Register, 12 months'], ['views_ratio', 'Attention: last week vs 90 days'], ['views_7d', 'Daily views'], ['pac_receipts', 'PAC raised']];
  state.ous = S.some(x => x[0] === state.ous) ? state.ous : 'revenue';
  const q = (state.ouq || '').trim().toUpperCase();
  let L = ouRows(d).filter(r => !q || r.ticker.includes(q) || String(r.name || '').toUpperCase().includes(q));
  const k = state.ous;
  L.sort((a, b) => (a[k] == null) - (b[k] == null) || b[k] - a[k]);
  exported = L;
  const page = state.page || 0, per = 50;
  return `<div class="toolbar">${field('ous', 'Sort', S, state.ous)}<div class="field"><label for="ouq">Ticker or name</label><input id="ouq" value="${esc(state.ouq || '')}" placeholder="e.g. PFE"></div></div>
    <div class="tablebox"><table><thead><tr><th>Company</th><th>Active trials</th><th>Phase 3</th><th>Catalysts due</th><th>Recalls 12m · 5y</th><th>Class I</th><th>Federal Register 12m</th><th>Views a day</th><th>vs 90 days</th><th>PAC raised</th></tr></thead><tbody>
    ${L.slice(page * per, page * per + per).map(r => `<tr><td>${ouTk(r.ticker, r.cik)}<br><span class="sub">${esc(r.name || '')}</span></td><td>${ouN(r.trials_active)}</td><td>${ouN(r.phase3_active)}</td><td>${ouN(r.catalysts)}</td>
      <td>${ouN(r.recalls_12m)} · ${ouN(r.recalls_5y)}</td><td class="${r.class1 ? 'negative' : ''}">${ouN(r.class1)}</td><td>${ouN(r.fedreg_12m)}</td><td>${ouN(r.views_7d)}</td>
      <td class="${(r.views_ratio || 0) >= 2 ? 'negative' : ''}">${r.views_ratio == null ? '—' : ouN(r.views_ratio, 1) + '×'}</td><td>${r.pac_receipts == null ? '—' : '$' + compact(r.pac_receipts)}</td></tr>`).join('')}
    </tbody></table></div><div class="pager"><span>${fmt(L.length)} companies · page ${page + 1} of ${Math.max(1, Math.ceil(L.length / per))}</span><button class="action" data-oupage="-1" ${page ? '' : 'disabled'}>Previous</button>
    <button class="action" data-oupage="1" ${(page + 1) * per < L.length ? '' : 'disabled'}>Next</button></div>`;
}
function ouCatalysts(d) {
  const C = d.catalysts || [];
  if (!C.length) return empty('No catalysts collected yet.');
  state.ouph = state.ouph || '';
  const L = C.filter(c => !state.ouph || c[5] === state.ouph);
  return `<div class="toolbar">${field('ouph', 'Phase', [['', 'Phase 2 and 3'], ['PHASE3', 'Phase 3'], ['PHASE2', 'Phase 2']], state.ouph)}</div>
    <div class="explain">Phase 2 and 3 studies led by listed companies whose primary completion — when the main result is in — falls in the next 18 months (the sponsor's estimate, often moved). Results tend to come out weeks to months later. ClinicalTrials.gov.</div>
    <div class="tablebox"><table><thead><tr><th>Due</th><th>Company</th><th>Phase</th><th>Study</th><th>Patients</th></tr></thead><tbody>
    ${L.slice(0, 300).map(c => `<tr><td>${esc(c[0] || '—')}</td><td>${ouTk(c[1], c[2])}</td><td>${esc(OU_PH[c[5]] || '—')}</td><td><a href="https://clinicaltrials.gov/study/${esc(c[3])}" target="_blank" rel="noopener">${esc(c[4])}</a><br><span class="sub">${esc(c[9] || '')}${c[10] ? ' · ' + esc(c[10]) : ''}</span></td><td>${ouN(c[8])}</td></tr>`).join('')}
    </tbody></table></div>`;
}
function ouRecalls(d) {
  const R = d.recalls || [];
  if (!R.length) return empty('No recalls matched yet.');
  state.ousrc = state.ousrc || '';
  const srcs = [...new Set(R.map(r => r[3]))].sort(), L = R.filter(r => !state.ousrc || r[3] === state.ousrc);
  return `<div class="toolbar">${field('ousrc', 'Source', [['', 'All sources']].concat(srcs.map(s => [s, s])), state.ousrc)}</div>
    <div class="explain">FDA enforcement reports (drugs, devices, food; Class I is the most serious), CPSC consumer-product recalls and NHTSA vehicle recalls, matched to listed companies by the recalling firm's name and known brands.</div>
    <div class="tablebox"><table><thead><tr><th>Date</th><th>Company</th><th>Source</th><th>Recall</th></tr></thead><tbody>
    ${L.slice(0, 300).map(r => `<tr><td>${esc(r[0])}</td><td>${ouTk(r[1], r[2])}</td><td>${esc(r[3])}${r[4] ? `<br><span class="sub ${r[4] === 'Class I' ? 'negative' : ''}">${esc(r[4])}</span>` : ''}</td>
      <td>${r[7] ? `<a href="${esc(r[7])}" target="_blank" rel="noopener">${esc(r[5])}</a>` : esc(r[5])}${r[6] ? `<br><span class="sub">${esc(r[6])}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
}
function ouRegulation(d, ix) {
  const R = d.regulation || [], top = ouRows(ix).filter(r => r.fedreg_12m).sort((a, b) => b.fedreg_12m - a.fedreg_12m).slice(0, 15);
  return `<div class="explain">Federal Register documents (rules, proposed rules, notices) that name a company, over the last 12 months: arms sales, permits, approvals, rate cases, enforcement. A name search, so some only mention it.</div>
    <h3>Named most often</h3><div class="tablebox"><table><thead><tr><th>Company</th><th>Documents, 12 months</th></tr></thead><tbody>${top.map(r => `<tr><td>${ouTk(r.ticker, r.cik)} <span class="sub">${esc(r.name)}</span></td><td>${ouN(r.fedreg_12m)}</td></tr>`).join('')}</tbody></table></div>
    <h3>The latest</h3><div class="tablebox"><table><thead><tr><th>Date</th><th>Company</th><th>Type</th><th>Document</th></tr></thead><tbody>
    ${R.slice(0, 200).map(r => `<tr><td>${esc(r[0])}</td><td>${ouTk(r[1], r[2])}</td><td>${esc(r[3])}</td><td><a href="${esc(r[6])}" target="_blank" rel="noopener">${esc(r[5])}</a><br><span class="sub">${esc(r[4])}</span></td></tr>`).join('')}</tbody></table></div>`;
}
function ouAttention(ix) {
  const L = ouRows(ix).filter(r => r.views_ratio != null && (r.views_7d || 0) >= 200).sort((a, b) => b.views_ratio - a.views_ratio).slice(0, 60);
  return `<div class="explain">Daily English Wikipedia views of each company's article (people, not bots) over the last week against the 90 days before. A spike follows news; attention often comes with heavier trading. Companies with at least 200 views a day.</div>
    <div class="tablebox"><table><thead><tr><th>Company</th><th>Views a day, last week</th><th>vs the 90 days before</th></tr></thead><tbody>
    ${L.map(r => `<tr><td>${ouTk(r.ticker, r.cik)} <span class="sub">${esc(r.name)}</span></td><td>${ouN(r.views_7d)}</td><td class="${r.views_ratio >= 2 ? 'negative' : ''}"><b>${ouN(r.views_ratio, 1)}×</b></td></tr>`).join('')}</tbody></table></div>`;
}
function ouPolitics(ix, st) {
  const L = ouRows(ix).filter(r => r.pac_receipts).sort((a, b) => b.pac_receipts - a.pac_receipts).slice(0, 100);
  if (!L.length) return empty(((st || {}).last_collect || {}).fec && st.last_collect.fec.skipped ? 'Political action committees need a free api.data.gov key (DATA_GOV_API_KEY); the FEC demo key allows ten requests an hour.' : 'No PACs matched yet.');
  return `<div class="explain">Corporate political action committees (FEC): money raised and given to candidates this election cycle. PAC money comes from employees' voluntary donations, not the company's treasury.</div>
    <div class="tablebox"><table><thead><tr><th>Company</th><th>Raised this cycle</th><th>To candidates</th></tr></thead><tbody>
    ${L.map(r => `<tr><td>${ouTk(r.ticker, r.cik)} <span class="sub">${esc(r.name)}</span></td><td>$${compact(r.pac_receipts)}</td><td>${r.pac_to_candidates == null ? '—' : '$' + compact(r.pac_to_candidates)}</td></tr>`).join('')}</tbody></table></div>`;
}
function ouCosts(C) {
  if (!C || !C.inputs || !C.sectors) return empty('Cost shocks need the FRED inputs; they are fetched on the next run.');
  const I = C.inputs, secs = Object.keys(C.sectors).filter(s => s !== 'other').sort(), names = (window.SECTOR_NAMES || {});
  state.oush = state.oush || '20';
  const sh = Math.log(1 + (+state.oush) / 100), m = state.oum === 'gm' ? 'gm' : 'om';
  const cell = f => { if (!f || f['b_' + m] == null) return '<td>—</td>'; const v = f['b_' + m] * sh, t = f['t_' + m]; const strong = t != null && Math.abs(t) >= 2;
    return `<td class="${v < 0 ? 'negative' : 'positive'}" title="t ${ouN(t, 1)}, ${f.n} company-quarters">${strong ? '<b>' : ''}${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(100 * v).toFixed(2)}${strong ? '</b>' : ''}</td>`; };
  return `<div class="toolbar">${field('oush', 'Each input', [['-20', '20% cheaper'], ['10', '10% dearer'], ['20', '20% dearer'], ['50', '50% dearer']], state.oush)}${field('oum', 'Margin', [['om', 'Operating margin'], ['gm', 'Gross margin']], m)}</div>
    <div class="explain">${esc(C.note || '')} Each cell: the change in the sector's margin, in percentage points, that its history pairs with that move in the input; bold where |t| ≥ 2.</div>
    <div class="tablebox"><table><thead><tr><th>Sector</th>${I.map(i => `<th title="${esc(i[2])}">${esc(i[1])}<br><span class="sub">last year ${i[4] == null ? '—' : (Math.expm1(i[4]) >= 0 ? '+' : '−') + Math.abs(100 * Math.expm1(i[4])).toFixed(0) + '%'}</span></th>`).join('')}</tr></thead><tbody>
    ${secs.map(s => `<tr><td>${esc(names[s] || s)}</td>${I.map(i => cell(C.sectors[s][i[0]])).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function outsideView() {
  state.ouv = OU_VIEWS.some(v => v[0] === state.ouv) ? state.ouv : 'companies';
  let out = `<div class="section-head"><h2>Beyond the filings</h2><span class="tag">FREE PUBLIC DATA · DAILY</span></div>
    <p class="sub">What free public data says about companies outside their 10-Q and 10-K: drug pipelines and the results due, recalls, regulation, political money, attention and cost shocks — from ClinicalTrials.gov, the FDA, CPSC, NHTSA, the Federal Register, the FEC, Wikipedia and FRED. Matched by name, conservatively: a company with no match shows nothing, not "none".</p>
    <div class="toolbar">${field('ouv', 'View', OU_VIEWS, state.ouv)}</div>`;
  const ix = ouData('index'), li = ouData('lists'), st = ouData('status');
  if (ix.err) return out + empty(`Beyond the filings could not load (${ix.err}). It is rebuilt daily by the research-outside workflow.`);
  if (state.ouv === 'one' && !state.ouone && state.ouonet && ix.data) { const r = ouRows(ix.data).find(x => x.ticker === state.ouonet); if (r) state.ouone = String(r.cik); }
  if (state.ouv === 'one') return out + `<div class="toolbar"><div class="field wide"><label for="ouone">Company (ticker)</label><input id="ouone" value="${esc(state.ouonet || '')}" placeholder="e.g. PFE · Enter"></div></div><div id="ou-one"></div>`;
  if (state.ouv === 'costs') { const c = ouData('costs'); return out + (c.data ? ouCosts(c.data) : c.err ? empty(c.err) : empty('Loading…')); }
  if (!ix.data || (['catalysts', 'recalls', 'regulation'].includes(state.ouv) && !li.data)) return out + empty('Loading…');
  const v = state.ouv;
  out += v === 'companies' ? ouCompanies(ix.data) : v === 'catalysts' ? ouCatalysts(li.data) : v === 'recalls' ? ouRecalls(li.data) : v === 'regulation' ? ouRegulation(li.data, ix.data)
    : v === 'attention' ? ouAttention(ix.data) : ouPolitics(ix.data, st.data);
  return out;
}
function bindOutside() {
  if (state.tab !== 'outside') return;
  ['ouv', 'ous', 'ouph', 'ousrc', 'oush', 'oum'].forEach(id => { if ($(id)) $(id).onchange = e => { state[id] = e.target.value; state.page = 0; render() } });
  if ($('ouq')) $('ouq').onchange = e => { state.ouq = e.target.value; state.page = 0; render() };
  document.querySelectorAll('#workspace [data-oupage]').forEach(b => b.onclick = () => { state.page = Math.max(0, (state.page || 0) + +b.dataset.oupage); render() });
  const one = (cik, t) => { state.ouv = 'one'; state.ouone = cik; state.ouonet = t; render(); };
  document.querySelectorAll('#workspace [data-out]').forEach(b => b.onclick = () => one(b.dataset.out, b.dataset.outt));
  if ($('ouone')) $('ouone').onchange = e => {
    const t = e.target.value.trim().toUpperCase(), r = ouRows((ouData('index').data) || {}).find(x => x.ticker === t);
    if (r) one(String(r.cik), r.ticker); else $('ou-one').innerHTML = `<p class="muted">${esc(t)}: nothing matched for that ticker.</p>`;
  };
  if (state.ouv === 'one' && $('ou-one') && state.ouone && window.OutsideView) window.OutsideView.render($('ou-one'), { cik: state.ouone, hub: '' });
}
function outsideDeepLink(arg) {
  const v = decodeURIComponent(arg || '').trim();
  if (OU_VIEWS.some(x => x[0] === v)) { state.ouv = v; return; }
  const r = ouRows((ouData('index').data) || {}).find(x => x.ticker === v.toUpperCase());
  state.ouv = 'one'; state.ouonet = v.toUpperCase(); state.ouone = r ? String(r.cik) : '';
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { outside: outsideView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { outside: bindOutside });
