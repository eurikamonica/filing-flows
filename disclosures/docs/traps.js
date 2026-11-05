/* Analysis traps tab (Disclosure Hub): the ten rules with how many companies each triggers on (data/traps/index.json),
   a company's findings through traps-view.js. #traps/NVDA opens a company. */
const trStore = {};
function trData() {
  const m = trStore.d || (trStore.d = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('../data/traps/index.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(async d => { d.list = (d.rows || []).map(r => Object.fromEntries(d.fields.map((k, i) => [k, r[i]])));
      d.changes = await fetch('../data/traps/changes.json', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null).then(c => (c && c.changes) || []).catch(() => []);
      m.data = d; if (state.tab === 'traps') render() })
    .catch(e => { m.err = e.message; if (state.tab === 'traps') render() });
  return m;
}
function trapsView() {
  const t = String(state.trt || '').trim().toUpperCase().replace(/[./]/g, '-');
  let out = head('Analysis traps', 'Where a company\'s figures could mislead a reader — free cash flow up, EPS up, low net debt, adjusted profit — checked on every filing by ten rules, each with the innocent explanation that would produce the same figures. A triggered rule is a question to verify, not a verdict.', 'RESEARCH');
  out += `<div class="toolbar"><div class="field wide"><label for="trt">Ticker</label><input id="trt" value="${esc(state.trt || '')}" placeholder="e.g. NVDA, AAPL · Enter"></div></div>`;
  const m = trData();
  if (t) return out + `<div id="tr-one" data-k="${esc(t)}" style="margin-top:10px"></div>`;
  if (m.err) return out + empty('The findings index is not available (' + esc(m.err) + ').');
  if (!m.data) return out + empty('Reading the findings…');
  const d = m.data, n = d.list.length;
  const counts = Object.fromEntries(Object.keys(d.rules).map(k => [k, d.list.filter(r => (r.triggered || []).includes(k)).length]));
  out += `<p class="muted">${n} companies evaluated · rules v${esc(d.rule_version)} · ${esc(d.generated_at)}</p>`;
  out += '<div class="tbl-wrap"><table><thead><tr><th>Rule</th><th>The trap</th><th class="num">Companies triggered</th><th>Largest, by the latest quarter</th></tr></thead><tbody>'
    + Object.entries(d.rules).map(([k, r]) => {
      const hits = d.list.filter(x => (x.triggered || []).includes(k)).slice(0, 12);
      return `<tr><td class="mono">${esc(k)}</td><td><b>${esc(r.name)}</b><br><span class="muted">${esc(r.blurb)}</span></td><td class="num">${counts[k]}</td><td>${hits.map(x => `<a href="#traps/${esc(x.ticker)}">${esc(x.ticker)}</a>`).join(', ')}</td></tr>`;
    }).join('') + '</tbody></table></div>';
  const CH = { new: 'newly triggered', released: 'no longer triggered', severity: 'severity changed', review: 'now to review', lapsed: 'no longer checkable' };
  const ch = (d.changes || []).slice(0, 30);
  out += '<h3 style="margin:18px 0 6px">What a newer filing changed</h3><p class="muted">Each rule is re-run when a company files; a trap that appears, goes or changes severity between two filings is listed here (a change to a rule on this site is not).</p>';
  out += ch.length ? '<div class="tbl-wrap"><table><thead><tr><th>Date</th><th>Company</th><th>Rule</th><th>Change</th><th>On the filing to</th><th>Figures</th></tr></thead><tbody>'
    + ch.map(c => `<tr><td class="mono">${esc(c.date)}</td><td><a href="#traps/${esc(c.ticker)}">${esc(c.ticker)}</a> <span class="muted">${esc(c.name)}</span></td><td class="mono">${esc(c.rule)}</td><td><b>${esc(CH[c.kind] || c.kind)}</b>${c.kind === 'severity' ? ` (${esc(c.from_severity)} → ${esc(c.severity)})` : c.severity && c.kind === 'new' ? ` · ${esc(c.severity)}` : ''}</td><td class="mono">${esc(c.as_of)}<span class="muted"> (was ${esc(c.prev_as_of || '—')})</span></td><td class="muted">${esc(String(c.explanation || '').split('. ')[0])}</td></tr>`).join('') + '</tbody></table></div>'
    : empty('No change yet: the changes are found by comparing each company\'s findings with those of its previous filing, from the next scans on.');
  out += '<p class="muted">Statuses: triggered, to review, not triggered, insufficient data, not applicable, out of date. Missing data is never shown as clear; severity and confidence are kept apart. <a href="analysis-traps/">The rules explained, with every company by rule →</a> · <a href="analysis-traps/practice/">Practice on real filings →</a></p>';
  return out;
}
function bindTraps() {
  if (state.tab !== 'traps') return;
  if ($('trt')) { $('trt').onchange = e => { state.trt = e.target.value; render() }; $('trt').onkeydown = e => { if (e.key === 'Enter') e.target.blur() } }
  const el = $('tr-one');
  if (el && window.TrapsView && !el.dataset.on) {
    el.dataset.on = '1';
    const t = el.dataset.k;
    fetch('../data/index.json', { cache: 'no-cache' }).then(r => r.json()).then(ix => {
      const row = (ix.companies || []).find(c => String(c.ticker || '').toUpperCase().replace(/[./]/g, '-') === t);
      if (!row) { el.innerHTML = empty('No company on the site with that ticker.'); return; }
      window.TrapsView.render(el, { cik: row.cik, ticker: row.ticker, site: '../', here: () => state.tab === 'traps' });
    }).catch(e => { el.innerHTML = empty('Could not read the company index (' + esc(e.message) + ').') });
  }
}
function trapsDeepLink(arg) { state.trt = String(decodeURIComponent(arg || '')).toUpperCase() }
function trapsNotice() { const m = trData(); return m.err ? { stale: true, text: 'Official derived view · Analysis traps unavailable · ' + m.err } : m.data ? { stale: false, text: `Official derived view · Analysis traps built ${m.data.generated_at} · ${m.data.list.length} companies · rebuilt with the site` } : { stale: false, text: 'Official derived view · Analysis traps loading…' } }
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { traps: trapsView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { traps: bindTraps });
window.HUB_NOTICES = Object.assign(window.HUB_NOTICES || {}, { traps: trapsNotice });
window.trapsDeepLink = trapsDeepLink;
