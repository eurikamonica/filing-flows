/* Guidance — the hub tab: every company's guidance record in one table, and the guidance changes as 8-Ks report them.
   - Hit rate: how often what a company reported met or beat what it guided (periods judged, met or beaten, beaten, missed),
     its latest guidance move, raises and cuts over its record, and its forward-looking statements (new, no longer said, tone);
   - Latest changes: raised / lowered / reaffirmed / withdrawn … from the earnings releases of the last days (8-K feed).
   One company: OutlookView (outlook-view.js, also the "Outlook & guidance" view of each company page).
   Data: data/market/guidance-board.json (scripts/guidance_board.cjs). Deep links: #guidance/<view>, #guidance/<TICKER>. */
const gbStore = {};
function gbData() {
  const m = gbStore.b || (gbStore.b = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/market/guidance-board.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(d => { m.data = d; if (state.tab === 'guidance') render() }).catch(e => { m.err = e.message; if (state.tab === 'guidance') render() });
  return m;
}
const GB_VIEWS = [['hit', 'Hit rate: guided vs reported'], ['changes', 'Latest guidance changes (8-K)'], ['fls', 'Forward-looking statements'], ['one', 'One company']];
const GB_WORD = { raised: '▲ raised', lowered: '▼ lowered', narrowed: '→← narrowed', widened: '←→ widened', reaffirmed: '= reaffirmed', initiated: '✦ initiated',
  withdrawn: '✕ withdrawn', mixed: '▲▼ mixed', updated: 'updated' };
const gbTk = (t, cik) => `<button class="text-button" data-gbo="${esc(cik)}" data-gbt="${esc(t)}"><b>${esc(t)}</b></button>`;
const gbMove = (g) => g ? `<span class="${/raised/.test(g) ? 'positive' : /lowered|withdrawn/.test(g) ? 'negative' : ''}">${esc(GB_WORD[g] || g)}</span>` : '—';
function gbHit(B) {
  const S = [['rate', 'Hit rate'], ['n', 'Periods judged'], ['beat', 'Beaten most'], ['miss', 'Missed most'], ['raised', 'Raised most']];
  state.gbs = S.some(x => x[0] === state.gbs) ? state.gbs : 'rate';
  state.gbmin = state.gbmin || '3';
  const q = (state.gbq || '').trim().toUpperCase(), min = +state.gbmin, k = state.gbs;
  let L = B.rows.filter(r => r.n >= min && (!q || r.t.includes(q) || String(r.name || '').toUpperCase().includes(q)));
  L.sort((a, b) => (b[k] ?? -1) - (a[k] ?? -1) || b.n - a.n);
  exported = L;
  const tools = `<div class="toolbar">${field('gbs', 'Sort', S, k)}${field('gbmin', 'At least', [['1', '1 period judged'], ['3', '3 periods'], ['6', '6 periods'], ['10', '10 periods']], state.gbmin)}<div class="field"><label for="gbq">Ticker or name</label><input id="gbq" value="${esc(state.gbq || '')}" placeholder="e.g. CAT"></div></div>`;
  const note = `<div class="explain">Each guided period is held to the last guidance the company gave before reporting it: within or better than the range counts as met or beaten (a single figure within 1%, 0.25 pts for a rate). GAAP and basis-free figures only — adjusted guidance has no reported figure to hold it to. From the earnings releases' guidance (8-K) and figures guided in the 10-Q / 10-K MD&A. ${fmt(B.with_record)} companies have a guidance record; ${fmt(B.judged)} have periods already reported. The record fills as older releases are read.</div>`;
  if (!L.length) return tools + note + empty(q ? 'No company matches.' : B.judged ? `${fmt(B.judged)} compan${B.judged === 1 ? 'y has' : 'ies have'} periods judged, none yet with ${min} or more: lower “At least”, or check back as older releases are read.` : 'No guided period has been reported yet; the hit rate appears as older releases are read and the guided quarters are reported.');
  return tools + note + `<div class="tablebox"><table><thead><tr><th>Company</th><th>Hit rate</th><th>Met or beat</th><th>Beat</th><th>Missed</th><th>By metric</th><th>Latest guidance</th><th>Raised · lowered</th></tr></thead><tbody>
    ${L.slice(0, 200).map(r => `<tr><td>${gbTk(r.t, r.cik)}<br><span class="sub">${esc(r.name || '')}</span></td><td class="${r.rate >= 0.75 ? 'positive' : r.rate < 0.5 ? 'negative' : ''}"><b>${Math.round(100 * r.rate)}%</b></td>
      <td>${r.hit} of ${r.n}</td><td>${r.beat}</td><td class="${r.miss ? 'negative' : ''}">${r.miss}</td><td class="sub">${(r.metrics || []).map(m => `${esc(m[0])} ${m[1]}/${m[2]}`).join('<br>')}</td>
      <td>${r.g ? gbMove(r.g[0]) + `<br><span class="sub">${esc(r.g[1])}</span>` : '—'}</td><td>${r.raised || 0} · ${r.lowered || 0}</td></tr>`).join('')}</tbody></table></div>`;
}
function gbChanges(B) {
  const kinds = [...new Set(B.recent.map(r => r[3]))].sort();
  state.gbk = kinds.includes(state.gbk) ? state.gbk : '';
  const L = B.recent.filter(r => !state.gbk || r[3] === state.gbk);
  return `<div class="toolbar">${field('gbk', 'Change', [['', 'Every change'], ...kinds.map(k => [k, GB_WORD[k] || k])], state.gbk)}</div>
    <div class="explain">Guidance changes read from the earnings releases filed with 8-Ks over the last days: the release's own words ("raises", "trims", "reaffirms") and its ranges against the previous ones.</div>
    <div class="tablebox"><table><thead><tr><th>Filed</th><th>Company</th><th>Guidance</th><th>Release</th></tr></thead><tbody>
    ${L.map(r => `<tr><td>${esc(r[0])}</td><td>${gbTk(r[1], r[2] || '')}</td><td>${gbMove(r[3])}</td><td>${r[5] ? `<a href="${esc(r[5])}" target="_blank" rel="noopener">${esc(r[4] || 'Release')}</a>` : esc(r[4])}</td></tr>`).join('')}</tbody></table></div>`;
}
function gbFls(B) {
  const S = [['new', 'Most new statements'], ['dropped', 'Most no longer said'], ['tone', 'Most positive tone'], ['neg', 'Most negative tone'], ['n', 'Most statements']];
  state.gbf = S.some(x => x[0] === state.gbf) ? state.gbf : 'new';
  const L = B.rows.filter(r => r.fls && r.fls[2] >= 3).map(r => ({ r, f: r.fls }));
  const key = { new: x => x.f[3], dropped: x => x.f[5], tone: x => x.f[6] ?? -9, neg: x => -(x.f[6] ?? 9), n: x => x.f[2] }[state.gbf];
  L.sort((a, b) => key(b) - key(a));
  return `<div class="toolbar">${field('gbf', 'Rank by', S, state.gbf)}</div>
    <div class="explain">Forward-looking statements in each company's latest 10-Q or 10-K MD&A ("we expect", "we plan to", "remains on track"), against the filing before: new ones, figures updated, and those no longer said. Tone: positive minus negative statements, of all (−100 to +100). Boilerplate (the safe-harbor paragraph, accounting standards, liquidity sufficiency) is left out.</div>
    <div class="tablebox"><table><thead><tr><th>Company</th><th>Filing</th><th>Statements</th><th>New</th><th>Updated</th><th>No longer said</th><th>Tone</th><th>Hedged</th></tr></thead><tbody>
    ${L.slice(0, 200).map(({ r, f }) => `<tr><td>${gbTk(r.t, r.cik)}<br><span class="sub">${esc(r.name || '')}</span></td><td>${esc(f[0])}<br><span class="sub">${esc(f[1])}</span></td><td>${f[2]}</td><td>${f[3]}</td><td>${f[4]}</td><td>${f[5]}</td>
      <td class="${(f[6] || 0) > 0.1 ? 'positive' : (f[6] || 0) < -0.1 ? 'negative' : ''}">${f[6] == null ? '—' : (f[6] > 0 ? '+' : '') + Math.round(100 * f[6])}</td><td>${f[2] ? Math.round(100 * f[7] / f[2]) + '%' : '—'}</td></tr>`).join('')}</tbody></table></div>`;
}
function guidanceView() {
  state.gbv = GB_VIEWS.some(v => v[0] === state.gbv) ? state.gbv : 'hit';
  let out = `<div class="section-head"><h2>Guidance</h2><span class="tag">8-K · 10-Q · 10-K</span></div>
    <p class="sub">What companies say about the future and how it turned out: the guidance in their earnings releases, raised, lowered or reaffirmed; how often the reported figures met or beat it; and the forward-looking statements of their 10-Q and 10-K. Read by fixed rules from the filings, no language model.</p>
    <div class="toolbar">${field('gbv', 'View', GB_VIEWS, state.gbv)}</div>`;
  if (state.gbv === 'one') return out + `<div class="toolbar"><div class="field wide"><label for="gbone">Company (ticker)</label><input id="gbone" value="${esc(state.gbonet || '')}" placeholder="e.g. CAT · Enter"></div></div><div id="gb-one"></div>`;
  const b = gbData();
  if (b.err) return out + empty(`The guidance board could not load (${b.err}). It is rebuilt with every site update.`);
  if (!b.data) return out + empty('Loading…');
  return out + (state.gbv === 'changes' ? gbChanges(b.data) : state.gbv === 'fls' ? gbFls(b.data) : gbHit(b.data));
}
function bindGuidance() {
  if (state.tab !== 'guidance') return;
  ['gbv', 'gbs', 'gbmin', 'gbk', 'gbf'].forEach(id => { if ($(id)) $(id).onchange = e => { state[id] = e.target.value; render() } });
  if ($('gbq')) $('gbq').onchange = e => { state.gbq = e.target.value; render() };
  const one = (cik, t) => { state.gbv = 'one'; state.gbone = cik; state.gbonet = t; render(); };
  document.querySelectorAll('#workspace [data-gbt]').forEach(b => b.onclick = () => one(b.dataset.gbo, b.dataset.gbt));
  if ($('gbone')) $('gbone').onchange = e => {
    const t = e.target.value.trim().toUpperCase(), r = (((gbData().data) || {}).rows || []).find(x => x.t === t);
    one(r ? String(r.cik) : '', t);
  };
  if (state.gbv === 'one' && $('gb-one') && state.gbonet && window.OutlookView) window.OutlookView.render($('gb-one'), { cik: state.gbone, ticker: state.gbonet, hub: '' });
}
function guidanceDeepLink(arg) {
  const v = decodeURIComponent(arg || '').trim();
  if (GB_VIEWS.some(x => x[0] === v)) { state.gbv = v; return; }
  const r = (((gbData().data) || {}).rows || []).find(x => x.t === v.toUpperCase());
  state.gbv = 'one'; state.gbonet = v.toUpperCase(); state.gbone = r ? String(r.cik) : '';
}
window.HUB_NOTICES = Object.assign(window.HUB_NOTICES || {}, { guidance: guidanceNotice });
function guidanceNotice() {
  const b = gbData(), d = b.data;
  if (b.err) return { stale: true, text: 'Official derived view · Guidance board unavailable · ' + b.err };
  if (!d) return { stale: false, text: 'Official derived view · Guidance board loading…' };
  const age = (Date.now() - Date.parse(d.generated_at)) / 3600000;
  return { stale: !(age <= 12), text: `Official derived view · Guidance built ${d.generated_at} · ${fmt(d.companies)} companies · ${fmt(d.with_record)} with a guidance record · ${fmt(d.judged)} with periods judged · ${fmt((d.recent || []).length)} recent changes · rebuilt with every site update` + (age > 12 ? ' · stale' : '') };
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { guidance: guidanceView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { guidance: bindGuidance });
