/* Hidden Leverage & Contractual Obligations — research evidence, not balance-sheet debt.
   Reads debt-history/public/hidden/index.json and each pre-existing c/<cik>.json.
   Never manufactures a numeric estimate from a textual filing hit. */
(function () {
  'use strict';
  const cache = {};
  const finite = x => x !== null && x !== undefined && Number.isFinite(Number(x));
  const money = x => finite(x) ? (window.DebtView ? DebtView.big(Number(x)) : '$' + fmt(Number(x))) : 'Not tagged';
  const sec = (url, title) => /^https:\/\/www\.sec\.gov\//.test(url || '') ?
    '<a target="_blank" rel="noopener" href="' + esc(url) + '">' + esc(title || 'SEC filing') + ' ↗</a>' : 'No source';
  const rowObj = (a, k) => a.reduce((o, v, i) => { o[k[i]] = v; return o; }, {});
  function load(path) {
    const o = cache[path] || (cache[path] = {});
    if (o.data || o.error || o.loading) return o;
    o.loading = true;
    fetch('data/debt/' + path + '.json').then(r => {
      if (!r.ok) throw Error('HTTP ' + r.status);
      return r.json();
    }).then(d => { o.data = d; o.loading = false; if (state.tab === 'hidden') render(); })
      .catch(e => { o.error = e.message; o.loading = false; if (state.tab === 'hidden') render(); });
    return o;
  }
  const classifications = {
    operating_commitment: 'Operating / contractual commitment',
    contingent: 'Contingent maximum exposure',
    recognized: 'Already recognized (reference)',
    lease_payments: 'Undiscounted lease payments (reference)'
  };
  function controls() {
    return '<div class="toolbar">' +
      field('hview', 'View', [['screen','Cross-company screen'], ['company','One company / evidence']], state.hview || 'screen') +
      (state.hview === 'company' ?
        '<div class="field wide"><label for="hq">Ticker or CIK</label><input id="hq" placeholder="e.g. ORCL" value="' + esc(state.hq || '') + '"></div>' :
        field('hfilter','Coverage', [['','All collected'],['numeric','With quantitative evidence'],['signals','Text leads'],['missing','No standard numeric tag']], state.hfilter || '') +
        '<div class="field wide"><label for="hsearch">Ticker / name</label><input id="hsearch" placeholder="Search company" value="' + esc(state.hsearch || '') + '"></div>') +
      '</div>';
  }
  function noData(text) { return '<div class="empty">' + esc(text) + '</div>'; }
  function evidence(c) {
    const sched = c.schedule || [], names = c.schedule_labels || [];
    const schedule = sched.some(finite) ?
      '<div class="hl-buckets">' + sched.map((v, i) => {
        const max = Math.max(1, ...sched.filter(finite).map(Number));
        return '<div class="hl-bucket"><span>' + esc(names[i] || 'Period ' + (i+1)) + '</span>' +
          '<div class="hl-track"><i style="width:' + (finite(v) ? Math.min(100,100*v/max) : 0) + '%"></i></div>' +
          '<b>' + (finite(v) ? money(v) : '—') + '</b></div>';
      }).join('') + '</div>' : '<p class="sub">No tagged maturity buckets at this reporting date.</p>';
    const sourceRows = (c.evidence || []).map(f =>
      '<tr><td>' + esc(f.tag || '') + '</td><td class="hl-number">' + money(f.value_usd) +
      '</td><td>' + esc(f.as_of || '') + '</td><td>' + sec(f.url, f.form + ' / ' + f.filed) + '</td></tr>').join('');
    return '<section class="panel hl-evidence"><div class="hl-flex"><div><h3>' + esc(c.label) + '</h3>' +
      '<p class="sub">' + esc(classifications[c.class] || c.class || '') + '</p></div>' +
      '<div class="hl-large">' + money(c.amount_usd) +
      '<small>' + (finite(c.amount_usd) ? 'Reported total, USD' : 'No total tagged') + '</small></div></div>' +
      '<p class="sub">This is not automatically incremental debt. ' + esc(c.warning || '') + '</p>' +
      schedule + '<details><summary>SEC XBRL evidence (' + (c.evidence || []).length + ' facts)</summary>' +
      '<div class="hl-scroll"><table class="hl-table"><thead><tr><th>Tag</th><th>Amount</th><th>Period</th><th>Original filing</th></tr></thead>' +
      '<tbody>' + sourceRows + '</tbody></table></div></details></section>';
  }
  function detail(d) {
    const h = d.hidden_leverage || {}, A = d.analysis || {}, rows = h.categories || [], signals = h.text_signals || [];
    let s = '<div class="panel"><div class="hl-flex"><div><h3>' + esc(d.name || d.ticker || '') +
      ' <span class="muted">' + esc(d.ticker || '') + '</span></h3>' +
      '<p class="sub">Reporting date ' + esc(h.as_of || 'unknown') + ' · ' + esc(h.coverage || 'not yet collected') + '</p></div>' +
      '<a href="#debt" class="tk">Debt &amp; rates ↗</a></div>' +
      '<div class="hl-kpis">' +
      '<div><span>Recognized borrowings (unchanged)</span><b>' + money(A.total_debt) + '</b></div>' +
      '<div><span>Existing net debt (unchanged)</span><b>' + money(A.net_debt) + '</b></div>' +
      '<div><span>Numeric disclosure groups</span><b>' + rows.length + '</b></div>' +
      '<div><span>Unverified text leads</span><b>' + signals.length + '</b></div></div></div>' +
      '<div class="explain">Amounts below are separate gross disclosures, not additive. A purchase agreement can contain goods/services, and a guarantee can be contingent. Recognized operating leases and undiscounted lease payments can overlap. No “hidden debt total” is computed; the original Debt &amp; Rates figures and valuation inputs are unchanged.</div>';
    if (!rows.length) s += noData('No matching standard US-GAAP commitment tags at this period. This does not imply zero commitments; company-specific tags, footnotes and uncommenced leases may require review.');
    else s += rows.map(evidence).join('');
    s += '<section class="panel"><h3>Contractual-structure leads from latest available filing</h3>' +
      '<p class="sub">Keyword detections only. They do not establish an actual payable, amount, recourse, consolidation conclusion, or financing classification.</p>';
    if (!signals.length) s += noData('No matching keywords have been collected. Check SEC footnotes manually for nonstandard disclosures.');
    else s += '<div class="hl-scroll"><table class="hl-table"><thead><tr><th>Possible structure</th><th>Review lane</th><th>Original excerpt</th><th>Evidence</th></tr></thead><tbody>' +
      signals.map(x => '<tr><td>' + esc(x.label) + '</td><td>' + esc(x.review_lane || 'Review') + '</td><td><span class="hl-excerpt">' + esc(x.excerpt) +
        '</span><small class="hl-muted">UNVERIFIED TEXT LEAD</small></td><td>' + sec(x.source_url,x.form + ' · ' + x.filed) +
        '</td></tr>').join('') + '</tbody></table></div>';
    s += '</section>';
    // Phase 2: source-anchored candidate schedules, kept OUTSIDE standardized debt amounts.
    const tables = h.footnote_tables || [];
    s += '<section class="panel"><h3>SEC footnote payment schedules · Phase 2</h3>' +
      '<p class="sub">Only explicitly dated USD annual tables are included. Every row requires review: the table may cover purchases or services, not borrowing. Amounts never add to net debt or each other.</p>';
    if (!tables.length) s += noData('No clearly named USD annual schedule extracted from the latest filing. Not evidence that the issuer has no obligations.');
    else s += tables.map(t => '<div class="hl-evidence"><div class="hl-flex"><h3>' + esc(t.label || t.key) +
      '</h3><span class="muted">Review required · ' + esc(t.review_lane || '') + '</span></div>' +
      '<p class="sub">' + esc(t.context || '') + '</p>' +
      (finite(t.amount_usd) ? '<p><strong>Reported candidate balance / maximum: ' + money(t.amount_usd) + '</strong> · ' + esc(t.amount_kind || '') + '</p>' : '') +
      ((t.payments || []).length ? '<div class="hl-scroll"><table class="hl-table">' : '') +
      '<thead><tr><th>Payment year</th><th>Nominal USD</th><th>Original filing</th></tr></thead><tbody>' +
      (t.payments || []).map(p => '<tr><td>' + esc(String(p.year)) + '</td><td class="hl-number">' +
        money(p.amount_usd) + '</td><td>' + sec(t.source_url, t.form + ' · ' + t.filed) +
        '</td></tr>').join('') + ((t.payments || []).length ? '</tbody></table></div>' : '') +
      '<small class="hl-muted">' + esc(t.warning || '') + ' · Table #' + esc(String(t.table_index)) +
      '</small></div>').join('');
    s += '</section>';
    const rq = d.revenue_quality || {}, m = rq.metrics || {};
    const pct = v => finite(v) ? (100 * Number(v)).toFixed(1) + '%' : 'Unknown';
    const ratio = v => finite(v) ? Number(v).toFixed(2) + 'x' : 'Unknown';
    s += '<section class="panel"><h3>Cookie Jar Revenue · beyond reserve accounts</h3>' +
      '<p class="sub">Checks annual SEC receivables, contract assets, contract liabilities and cash conversion. A signal does not establish revenue manipulation; growth, acquisitions, billing cycles and receivable sales can explain differences.</p>';
    if (!rq.status || rq.status === 'missing_annual_comparison' || rq.status === 'incomplete') {
      s += noData('Two comparable annual filing periods are not available. Unknown, not a clean audit result.');
    } else {
      s += '<p class="sub">Annual periods: ' + esc((rq.periods || []).join(' versus ')) + '</p>' +
        '<div class="hl-scroll"><table class="hl-table"><thead><tr><th>Screen</th><th>Value</th></tr></thead><tbody>' +
        [['Revenue growth', pct(m.revenue_growth)], ['Receivables growth', pct(m.receivables_growth)],
         ['Contract assets growth', pct(m.contract_assets_growth)],
         ['Contract liabilities growth', pct(m.contract_liabilities_growth)],
         ['Receivables / sales index (DSRI)', ratio(m.dsri)],
         ['Operating cash / net income', ratio(m.ocf_to_net_income)]]
          .map(a => '<tr><td>' + esc(a[0]) + '</td><td class="hl-number">' + esc(a[1]) + '</td></tr>').join('') +
        '</tbody></table></div>' +
        '<p class="sub">' + (rq.risk_flags || []).length + ' quantitative review prompts. ' +
        ((rq.risk_flags || []).length ? (rq.risk_flags || []).map(f => esc(f.label + ': ' + f.rule)).join(' · ') :
         'No selected thresholds triggered; this is NOT proof of correctly stated revenue.') + '</p>' +
        '<details><summary>SEC numeric evidence by period</summary><div class="hl-scroll"><table class="hl-table"><thead><tr>' +
        '<th>Item</th><th>Period</th><th>Reported USD</th><th>Source</th></tr></thead><tbody>' +
        Object.entries(rq.evidence || {}).map(([key, a]) => (a || []).filter(Boolean).map(f =>
          '<tr><td>' + esc(key + ' / ' + (f.tag || '')) + '</td><td>' + esc(f.end || '') +
          '</td><td class="hl-number">' + money(f.value_usd) + '</td><td>' +
          sec(f.source_url, f.form + ' · ' + f.filed) + '</td></tr>').join('')).join('') +
        '</tbody></table></div></details>';
    }
    const leads = rq.text_leads || [];
    s += '<details><summary>Revenue recognition filing text leads (' + leads.length + ')</summary>' +
      '<p class="sub">Unverified keywords from the issuer filing; ordinary accounting policies frequently match.</p>' +
      '<div class="hl-scroll"><table class="hl-table"><thead><tr><th>Mechanism</th><th>Excerpt</th><th>Source</th></tr></thead><tbody>' +
      leads.map(t => '<tr><td>' + esc(t.label) + '</td><td>' + esc(t.excerpt) + '</td><td>' +
        sec(t.source_url, t.form + ' · ' + t.filed) + '</td></tr>').join('') + '</tbody></table></div></details></section>';
    if (h.warnings) s += '<div class="explain">' + h.warnings.map(esc).join(' · ') + '</div>';
    return s;
  }
  function taxonomyPanel(items) {
    if (!Array.isArray(items) || !items.length) return '';
    return '<details class="panel"><summary>Research taxonomy · 15 primary + 9 additional structures</summary>' +
      '<p class="sub">A = financing review, B = fixed commitment review, C = contingent exposure review. Mixed lanes require contract-specific classification. A text match is not verified debt; no match is not proof of absence.</p>' +
      '<div class="hl-scroll"><table class="hl-table"><thead><tr><th>Structure</th><th>Review lane</th><th>Evidence status</th></tr></thead><tbody>' +
      items.map(x => '<tr><td>' + esc(x.label) + '</td><td>' + esc(x.review_lane) +
        '</td><td>Keyword screening only</td></tr>').join('') +
      '</tbody></table></div></details>';
  }
  function screen(data) {
    const a = data.rows || [], query = (state.hsearch || '').trim().toUpperCase();
    let rows = a.filter(x => !query ||
      String(x.ticker || '').toUpperCase().includes(query) ||
      String(x.cik || '').includes(query) || String(x.name || '').toUpperCase().includes(query));
    if (state.hfilter === 'numeric') rows = rows.filter(x => x.categories > 0);
    if (state.hfilter === 'signals') rows = rows.filter(x => x.signals > 0);
    if (state.hfilter === 'missing') rows = rows.filter(x => !x.categories);
    rows.sort((a,b) => (b.categories || 0) - (a.categories || 0) || (b.signals || 0) - (a.signals || 0));
    exported = rows;
    return '<div class="panel"><h3>' + fmt(rows.length) + ' companies · ' +
      fmt(a.filter(x => x.categories > 0).length) + ' with standardized quantitative evidence</h3>' +
      '<p class="sub">Independent SEC filing extraction, updated with the Debt &amp; Rates collector. Figures shown only when the tag and reporting date match. Text leads are unverified. Use the original SEC filing for confirmation.</p></div>' +
      '<div class="section-head"><h3>Commitments screener</h3><button class="action" id="csv">Export CSV ↓</button></div>' +
      '<div class="hl-scroll"><table class="hl-table"><thead><tr><th>Company</th><th>As of</th><th>Debt</th><th>Purchase obligations</th>' +
      '<th>Gross purchase</th><th>Max guarantee</th><th>Operating lease liability</th><th>Footnote tables</th><th>Revenue prompts</th><th>Evidence</th></tr></thead><tbody>' +
      rows.slice(0,250).map(r =>
        '<tr><td><button type="button" class="text-button" data-hc="' + esc(r.cik) + '"><strong>' +
        esc(r.ticker || r.cik) + '</strong></button><small class="hl-muted">' + esc(r.name || '') + '</small></td>' +
        '<td>' + esc(r.as_of || '—') + '</td><td>' + money(r.recognized_debt) +
        '</td><td>' + money(r.purchase) + '</td><td>' + money(r.purchase_broad) +
        '</td><td>' + money(r.guarantees) + '</td><td>' + money(r.operating_lease) +
        '</td><td>' + (r.footnote_tables || 0) + '</td><td>' + (r.cookie_risk_flags || 0) +
        '</td><td>' + (r.categories || 0) + ' tags · ' + (r.signals || 0) + ' leads</td></tr>').join('') +
      '</tbody></table></div>' +
      (rows.length > 250 ? '<p class="sub">Showing 250 of ' + fmt(rows.length) + ' companies. Narrow by company or export the full data.</p>' : '') + taxonomyPanel(data.taxonomy);
  }
  function view() {
    if (state.mode === 'demo') return head('Hidden leverage & contractual obligations', 'This module uses official filings only.', 'SEC') +
      noData('Choose Official snapshot above. No fictional debt or commitments are supplied.');
    state.hview = state.hview === 'company' ? 'company' : 'screen';
    let out = head('Hidden leverage & contractual obligations',
      'Unrecorded contracts, contingent guarantees and lease exposures — alongside existing debt, without counting them twice.',
      'SEC XBRL · 10-K / 10-Q') + controls();
    const ix = load('hidden/index');
    if (ix.error) return out + noData('Hidden Leverage index not yet published (' + ix.error +
      '). Once the debt collector rebuilds on the updated code and Pages deploys, SEC evidence will appear.');
    if (!ix.data) return out + noData('Loading SEC commitments index…');
    if (state.hview === 'screen') return out + screen(ix.data);
    const q = (state.hq || '').trim().toUpperCase();
    if (!q) return out + noData('Choose a company from the screener or enter a ticker.');
    const found = (ix.data.rows || []).find(r => String(r.ticker || '').toUpperCase() === q || String(r.cik) === q);
    if (!found) return out + noData('No collected debt/commitment record yet for ' + q + '.');
    const c = load('c/' + found.cik);
    if (c.error) return out + noData('Company report unavailable: ' + c.error);
    if (!c.data) return out + noData('Loading company evidence…');
    return out + detail(c.data);
  }
  function bind() {
    if (state.tab !== 'hidden') return;
    for (const id of ['hview', 'hfilter']) if (document.getElementById(id)) {
      document.getElementById(id).onchange = e => { state[id] = e.target.value; render(); };
    }
    for (const id of ['hq','hsearch']) if (document.getElementById(id)) {
      const el = document.getElementById(id);
      el.onchange = e => { state[id] = e.target.value; render(); };
      el.onkeydown = e => { if (e.key === 'Enter') el.blur(); };
    }
    document.querySelectorAll('#workspace [data-hc]').forEach(el => {
      el.onclick = () => { state.hview = 'company'; state.hq = el.dataset.hc; render(); window.scrollTo({top:0,behavior:'smooth'}); };
    });
  }
  window.hiddenDeepLink = function(q) { state.hview = 'company'; state.hq = decodeURIComponent(q); };
  window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, {hidden: view});
  window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, {hidden: bind});
})();