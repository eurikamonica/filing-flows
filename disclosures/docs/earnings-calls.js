/* Earnings Call Intelligence: issuer IR links and SEC 8-K Item 2.02 evidence.
   No full-text redistribution, no claim that an 8-K is a conference call. */
(function () {
  'use strict';
  const store = {data: null, error: '', loading: false};
  function load() {
    if (store.data || store.error || store.loading) return;
    store.loading = true;
    fetch('data/earnings-calls/index.json', {cache: 'no-cache'})
      .then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json(); })
      .then(d => {store.data = d; store.loading = false; if (state.tab === 'calls') render();})
      .catch(e => {store.error = e.message; store.loading = false; if (state.tab === 'calls') render();});
  }
  function view() {
    if (state.mode === 'demo') return head('Earnings Call Intelligence',
      'Official-source evidence only. There is no synthetic transcript demo.', 'SEC + ISSUER IR') +
      empty('Select Official snapshot to view company IR links and earnings-release evidence.');
    load();
    let out = head('Earnings Call Intelligence',
      'Official company transcript links paired with SEC 8-K Item 2.02 evidence. A filing is not proof that a call happened.',
      'OFFICIAL IR / SEC');
    const d = store.data;
    if (!d) return out + empty(store.error ?
      'The earnings-call index has not been published yet (' + store.error + '). Run the Earnings Calls workflow and deploy Pages.' :
      'Loading official IR and SEC earnings evidence…');
    const rows = d.rows || [];
    const tickers = [...new Set(rows.map(r => r.ticker))].sort();
    const ticker = state.ecTicker || '';
    const kind = state.ecKind || '';
    const tickOptions = [['', 'All companies'], ...tickers.map(t => [t, t])];
    const kindOptions = [['', 'Both evidence types'], ['official_ir_transcript', 'Verified official transcript links'], ['sec_earnings_evidence', 'SEC Item 2.02 evidence']];
    function selector(id, label, options, value) {
      return '<div class="field"><label for="' + id + '">' + esc(label) + '</label><select id="' + id + '">' +
        options.map(a => '<option value="' + esc(a[0]) + '"' + (value === a[0] ? ' selected' : '') + '>' +
          esc(a[1]) + '</option>').join('') + '</select></div>';
    }
    out += '<div class="toolbar">' + selector('ec-ticker', 'Company', tickOptions, ticker) +
      selector('ec-kind', 'Source type', kindOptions, kind) + '</div>';
    out += '<div class="explain">Collector status: <b>' + esc(d.status || 'unknown') +
      '</b> · Last attempted: ' + esc(d.last_attempt || '—') +
      ' · Last complete success: ' + esc(d.last_success || '—') +
      ' · Latest source date: ' + esc(d.latest_source_date || '—') +
      ' · Published site build: ' + esc((window.HUB_BUILD || {}).published_at || 'unavailable') +
      '<br>Coverage is a limited initial watchlist; not all issuers have an onboarded IR parser. ' +
      'Transcript links are verified against official issuer pages; SEC 8-K is earnings-release evidence only. ' +
      'See original sources for complete statements and reuse terms.</div>';
    if ((d.errors || []).length) out += '<div class="explain">Partial collection: ' +
      esc(d.errors.slice(0, 3).join('; ')) + '</div>';
    const filtered = rows.filter(r => (!ticker || r.ticker === ticker) && (!kind || r.kind === kind));
    out += '<div class="metrics">' +
      kpi('Official transcript links', d.counts?.official_transcripts || 0, 'Validated company IR pages') +
      kpi('SEC earnings disclosures', d.counts?.sec_earnings_evidence || 0, '8-K Item 2.02; not transcript') +
      kpi('Shown in filter', filtered.length, 'Sorted by source date') + '</div>';
    if (!filtered.length) return out + empty('No matching official evidence collected yet. This does not mean no earnings call occurred.');
    out += '<div class="section-head"><h3>Official-source timeline</h3></div><div class="tablebox"><table><thead><tr>' +
      '<th>Company / source date</th><th>Record classification</th><th>Original public sources</th><th>Evidence</th></tr></thead><tbody>';
    for (const r of filtered.slice(0, 100)) {
      const ir = r.kind === 'official_ir_transcript';
      out += '<tr><td><b>' + esc(r.ticker) + '</b><br>' + esc(r.date || '—') + '</td><td>' +
        (ir ? 'Official transcript verified' : 'SEC earnings release (8-K)') +
        '</td><td>' + (ir ? link(r.ir_url, 'Read official IR transcript') + '<br>' : '') +
        (r.sec_url ? link(r.sec_url, 'Open SEC filing') : '—') +
        '</td><td>' + (ir ? esc(String(r.speaker_count || 0)) + ' detected speakers · Official source link' :
          'Item ' + esc(r.items || '2.02') + ' · Not a transcript') + '</td></tr>';
    }
    return out + '</tbody></table></div><p class="sub">Source links are retained; complete transcript text is not republished on this page.</p>';
  }
  function bind() {
    if (state.tab !== 'calls') return;
    for (const [id, key] of [['ec-ticker', 'ecTicker'], ['ec-kind', 'ecKind']]) {
      const node = document.getElementById(id);
      if (node) node.onchange = e => { state[key] = e.target.value; render(); };
    }
  }
  window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, {calls: view});
  window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, {calls: bind});
})();
