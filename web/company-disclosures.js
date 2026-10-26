/* Company-scoped disclosure summary and evidence view. Uses the Hub's published data. */
(function (root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const number = (v, suffix = '×') => finite(v) ? v.toLocaleString('en-US', {maximumFractionDigits:2}) + suffix : 'Not available';
  const money = v => finite(v) ? 'USD ' + Intl.NumberFormat('en-US', {notation:'compact', maximumFractionDigits:2}).format(v) : 'Not available';
  const list = v => Array.isArray(v) ? v : [];
  const cikOf = v => /^\d{1,10}$/.test(String(v)) ? String(Number(v)) : '';
  const date = v => esc(v || 'Not available');
  function source(item) {
    let u;
    try { u = new URL(item.source_url || item.url); } catch (_) { return ''; }
    if (u.protocol !== 'https:' || u.hostname !== 'www.sec.gov' || u.username || u.password) return '';
    return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">SEC ${esc(item.form || 'filing')}${item.filed ? ' · ' + esc(item.filed) : ''}</a>`;
  }
  const classes = {operating_commitment:'Contractual commitment',contingent:'Contingent maximum exposure',recognized:'Already recognized · reference',lease_payments:'Undiscounted lease payments · reference'};
  const metric = (name, value, note = '') => `<div class="cd-metric"><span>${esc(name)}</span><strong>${esc(value)}</strong>${note ? `<small>${esc(note)}</small>` : ''}</div>`;
  function category(row, full) {
    return `<article class="cd-evidence"><div class="cd-row"><h4>${esc(row.label || row.key)}</h4><strong>${esc(money(row.amount_usd))}</strong></div><p class="muted">${esc(classes[row.class] || 'Requires classification')} · As of ${date(row.as_of)} · ${source(row)}</p>${full ? `<p>${esc(row.warning || 'Categories may overlap; do not add to recognized debt or other rows.')}</p>${list(row.schedule).length ? `<div class="cd-metrics">${row.schedule.map((v,i) => metric(list(row.schedule_labels)[i] || `Period ${i+1}`, money(v))).join('')}</div>` : ''}<details><summary>XBRL evidence (${list(row.evidence).length})</summary>${list(row.evidence).map(e => `<p>${esc(e.tag)} · ${esc(money(e.value_usd))} · ${date(e.as_of)} · ${source(e)}</p>`).join('') || '<p>No individual facts published.</p>'}</details>` : ''}</article>`;
  }
  function leads(rows, title) {
    return `<details><summary>${esc(title)} (${list(rows).length})</summary><p class="muted">Review leads only; these are not confirmed debt or findings of misconduct.</p>${list(rows).map(r => `<article class="cd-evidence"><h4>${esc(r.label || r.key)}</h4><p>${esc(r.excerpt || r.context || '')}</p>${finite(r.amount_usd) ? `<p>${esc(money(r.amount_usd))} · ${esc(r.amount_kind || 'Extracted amount; requires review')}</p>` : ''}<p>${esc(r.warning || '')} ${source(r)}</p></article>`).join('') || '<p>No leads published; this does not establish absence of exposure.</p>'}</details>`;
  }
  function render(doc, cik, compact) {
    const a = doc.analysis || {}, h = doc.hidden_leverage || {}, r = doc.revenue_quality || {}, s = doc.snapshot || {};
    const cats = list(h.categories), flags = list(r.risk_flags), m = r.metrics || {};
    const header = `<div class="cd-heading"><div><p class="cd-eyebrow">Company disclosures</p><h2>${compact ? 'Debt, leverage & disclosure signals' : 'Disclosures & risk'}</h2></div>${compact ? `<a class="tag" href="#c-${cik}-risk">View evidence →</a>` : `<a class="tag" href="#c-${cik}-debt">Debt & rates →</a>`}</div><p class="muted">Latest available disclosure snapshot · USD amounts · independent of the selected earnings quarter.<br>Balance sheet: ${date(s.balance_date)} · Operating period: ${date(s.latest_period)} · Updated: ${date(doc.generated_at || doc.fetched_at)}</p>`;
    let html = `${header}<div class="cd-metrics">${metric('Recognized debt',money(a.total_debt))}${metric('Debt / EBITDA',number(a.leverage))}${metric('Net debt / EBITDA',number(a.net_leverage))}${metric('EBIT / interest',number(a.interest_coverage))}</div>`;
    if (!compact) html += `<div class="cd-metrics">${metric('Net debt',money(a.net_debt))}${metric('Liquidity',money(a.liquidity))}${metric('Due within 12 months',money(a.due_12m))}${metric('Due within 24 months',money(a.due_24m),'Includes the first 12 months')}</div><details><summary>Metric sources & basis</summary><p>Ratios use the published debt model. Operating figures can use trailing periods while balances use the balance-sheet date above. Missing or non-comparable ratios remain unavailable.</p>${Object.entries(doc.sources || {}).map(([k,v])=>`<p><strong>${esc(k)}</strong>: ${esc(v)}</p>`).join('')}</details>`;
    html += `<h3>Hidden Debt / Hidden Leverage</h3><p class="muted">As of ${date(h.as_of)} · Commitments, contingent exposures and recognized liabilities are separate categories. They overlap and are not a total hidden-debt figure.</p>${cats.length ? cats.slice(0,compact ? 3 : cats.length).map(row=>category(row,!compact)).join('') : '<p>No numeric evidence published for this company. This does not mean zero exposure.</p>'}`;
    if (compact && cats.length > 3) html += `<p><a href="#c-${cik}-risk">See all ${cats.length} evidence categories →</a></p>`;
    if (!compact) html += leads(h.footnote_tables,'Footnote tables · requires review') + leads(h.text_signals,'Unverified text signals');
    html += `<h3>Revenue quality / Cookie Jar signals</h3><p class="muted">Annual comparison: ${list(r.periods).map(date).join(' vs ') || date(r.as_of)} · ${esc(r.status || 'Not collected')}. Screening signals require filing review.</p><div class="cd-metrics">${metric('Receivables / revenue index',number(m.dsri))}${metric('Operating cash / net income',number(m.ocf_to_net_income),'Annual period, not the trailing debt model')}</div>${flags.length ? `<ul>${flags.map(f=>`<li><strong>${esc(f.label)}</strong>${compact ? '' : ': ' + esc(f.rule || '')}</li>`).join('')}</ul>` : `<p>${r.status === 'screened' ? 'No rule-based flags in the published screen; this is not an assurance of reporting quality.' : 'Annual comparison is incomplete or has not been collected.'}</p>`}`;
    if (!compact) {
      html += `<details><summary>Revenue-quality source facts</summary>${Object.entries(r.evidence || {}).map(([key,values])=>`<h4>${esc(key)}</h4>${list(values).filter(Boolean).map(e=>`<p>${esc(e.tag)} · ${esc(money(e.value_usd))} · Period ${date(e.end)} · ${source(e)}</p>`).join('')}`).join('') || '<p>No source facts published.</p>'}</details>${leads(r.text_leads,'Revenue-quality text leads')}`;
      html += `<h3>Credit agreements & covenants</h3>${list(doc.agreements).map(g=>`<article class="cd-evidence"><h4>${esc(g.title || g.agreement_kind)}</h4><p>${date(g.dated || g.date)} · ${esc(money(g.size))} · ${source(g)}</p>${list(g.covenants).map(v=>`<p>${esc(v.type)} · ${esc(v.direction)} ${esc(number(v.limit,v.unit || ''))}<br>${esc(v.text)}</p>`).join('')}</article>`).join('') || '<p>No agreement evidence collected.</p>'}`;
    }
    html += `<nav class="cd-links" aria-label="Related company analysis"><a href="#c-${cik}-debt">Debt & rates</a><a href="#c-${cik}-cash">Profit & cash</a><a href="#c-${cik}-x-filings">Company filings</a><a href="#c-${cik}-x-events">Material events</a></nav>`;
    return html;
  }
  async function mount(el, {cik, here = () => true, compact = false}) {
    if (!el) return;
    const id = cikOf(cik), token = {};
    el._disclosureRequest = token;
    const active = () => el.isConnected && here() && el._disclosureRequest === token;
    el.classList.add('company-disclosures');
    el.innerHTML = '<p role="status">Loading company disclosures…</p>';
    const controller = new AbortController(), timeout = setTimeout(()=>controller.abort(),15000);
    try {
      if (!id) throw Error('Invalid company identifier.');
      const response = await fetch(`disclosures/data/debt/c/${id}.json`, {signal:controller.signal,cache:'no-cache'});
      if (response.status === 404) {
        if (active()) el.innerHTML = '<h2>Company disclosures</h2><p>No debt or disclosure snapshot has been published for this company yet.</p>';
        return;
      }
      if (!response.ok) throw Error('Disclosure data could not be loaded.');
      const doc = await response.json();
      if (cikOf(doc.cik) !== id) throw Error('Disclosure data does not match this company.');
      if (active()) el.innerHTML = render(doc,id,compact);
    } catch (error) {
      if (active()) {
        el.innerHTML = '<h2>Company disclosures</h2><p role="status">Company disclosure data is temporarily unavailable.</p><button type="button">Retry</button>';
        el.querySelector('button').onclick = () => mount(el,{cik,here,compact});
      }
    } finally { clearTimeout(timeout); }
  }
  root.FFCompanyDisclosures = {mount};
})(window);
