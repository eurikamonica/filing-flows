/* Investors — the hub tab: which listed companies earn the most on their investments (gains over the last four quarters,
   SEC XBRL), the share of their pre-tax income it made, and what they own or bought (their own 13F and 13D/13G, their
   8-K releases, other companies' filings naming them as an investor). One company: InvestmentsView (investments-view.js,
   also the company page's "Investments" view). Data: data/research/investors/index.json (app/investors.py).
   Deep links: #investors/<view>, #investors/<TICKER>. */
const ivStore = {};
function ivData() {
  const m = ivStore.i || (ivStore.i = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/research/investors/index.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(d => { const F = d.fields; d.list = (d.rows || []).map(r => Object.fromEntries(F.map((k, i) => [k, r[i]]))); m.data = d; if (state.tab === 'investors') render() })
    .catch(e => { m.err = e.message; if (state.tab === 'investors') render() });
  return m;
}
const IV_VIEWS = [['top', 'Largest gains on investments'], ['share', 'Gains as a share of profit'], ['losses', 'Largest losses'], ['one', 'One company']];
const ivUsd = v => v == null || !Number.isFinite(+v) ? '—' : (v < 0 ? '−' : '') + '$' + compact(Math.abs(v));
const ivQ = p => p ? p.replace(/^CY(\d{4})Q(\d)$/, 'Q$2 $1') : '';
function ivTable(L) {
  return `<div class="tablebox"><table><thead><tr><th>#</th><th>Company</th><th>Gains, 4 quarters</th><th>Share of pre-tax</th><th>Equity-method income</th><th>Largest price gain last quarter</th><th>What it owns or bought</th></tr></thead><tbody>
    ${L.slice(0, 200).map((r, i) => `<tr><td>${i + 1}</td><td><button class="text-button" data-ivt="${esc(r.t)}" data-ivc="${esc(r.cik)}"><b>${esc(r.t)}</b></button><br><span class="sub">${esc(r.name || '')}</span></td>
      <td class="${r.gains >= 0 ? 'positive' : 'negative'}"><b>${ivUsd(r.gains)}</b><br><span class="sub">${r.quarters} quarters</span></td><td>${r.share == null ? '—' : Math.round(100 * r.share) + '%'}</td>
      <td>${ivUsd(r.eqm)}</td><td>${r.top_gainer ? `${esc(r.top_gainer)}<br><span class="sub">${ivUsd(r.top_gain)}</span>` : '—'}</td>
      <td class="sub">${(r.holdings || []).length ? (r.holdings || []).map(esc).join(' · ') + (r.n_holdings > 5 ? ` · +${r.n_holdings - 5}` : '') : r.read ? 'none named in filings' : 'not read yet'}</td></tr>`).join('')}</tbody></table></div>`;
}
function investorsView() {
  state.ivv = IV_VIEWS.some(v => v[0] === state.ivv) ? state.ivv : 'top';
  let out = `<div class="section-head"><h2>Investors</h2><span class="tag">10-Q · 10-K · 13F · 13D/G · 8-K</span></div>
    <p class="sub">Which listed companies earn the most on their investments, and what they bought: gains on investments as their own income statements tag them, and the holdings their filings — and other companies' filings — name.</p>
    <div class="toolbar">${field('ivv', 'View', IV_VIEWS, state.ivv)}<div class="field"><label for="ivq">Ticker or name</label><input id="ivq" value="${esc(state.ivq || '')}" placeholder="e.g. NVDA · Enter"></div></div>`;
  if (state.ivv === 'one') return out + `<div id="iv-one"></div>`;
  const m = ivData();
  if (m.err) return out + empty(`The investors research could not load (${m.err}). It is rebuilt daily by the research-investors workflow.`);
  if (!m.data) return out + empty('Loading…');
  const D = m.data, q = (state.ivq || '').trim().toUpperCase();
  let L = D.list.filter(r => !q || String(r.t || '').includes(q) || String(r.name || '').toUpperCase().includes(q));
  if (state.ivv === 'share') L = L.filter(r => r.share != null && r.gains > 0 && (r.pretax || 0) > 1e8).sort((a, b) => b.share - a.share);
  else if (state.ivv === 'losses') L = L.filter(r => r.gains < 0).sort((a, b) => a.gains - b.gains);
  else L = L.filter(r => r.gains > 0);
  exported = L;
  const tot = D.list.filter(r => r.gains > 0).slice(0, 10).reduce((a, r) => a + r.gains, 0);
  out += `<div class="explain">Gains on investments over the four calendar quarters ${esc(ivQ((D.periods || [])[0]))} – ${esc(ivQ((D.periods || []).slice(-1)[0]))}, as each company tags them in its 10-Q and 10-K (realized and unrealized; fourth quarters from the annual report). The ten largest made ${ivUsd(tot)}. What they own: A their own 13F and 13D/13G, B their own 8-K releases, C other companies' filings naming them as an investor — click a company for the evidence. A stake no filing names stays unknown. Not investment advice.</div>`;
  return out + (L.length ? ivTable(L) : empty('No company matches.'));
}
function bindInvestors() {
  if (state.tab !== 'investors') return;
  if ($('ivv')) $('ivv').onchange = e => { state.ivv = e.target.value; render() };
  const one = (cik, t) => { state.ivv = 'one'; state.ivc = cik; state.ivt = t; render(); };
  if ($('ivq')) $('ivq').onchange = e => {
    const t = e.target.value.trim().toUpperCase(), r = ((ivData().data || {}).list || []).find(x => x.t === t);
    if (r) one(String(r.cik), r.t); else { state.ivq = e.target.value; render(); }
  };
  document.querySelectorAll('#workspace [data-ivt]').forEach(b => b.onclick = () => one(b.dataset.ivc, b.dataset.ivt));
  if (state.ivv === 'one' && $('iv-one') && window.InvestmentsView) {
    if (!state.ivc) { $('iv-one').innerHTML = '<p class="sub">Type a ticker above (e.g. NVDA, GOOGL, BRK-B).</p>'; return; }
    window.InvestmentsView.render($('iv-one'), { cik: state.ivc, ticker: state.ivt, hub: '' });
  }
}
function investorsDeepLink(arg) {
  const v = decodeURIComponent(arg || '').trim();
  if (IV_VIEWS.some(x => x[0] === v)) { state.ivv = v; return; }
  const r = ((ivData().data || {}).list || []).find(x => x.t === v.toUpperCase());
  state.ivv = 'one'; state.ivt = v.toUpperCase(); state.ivc = r ? String(r.cik) : '';
}
function investorsNotice() {
  const m = ivData(), d = m.data;
  if (m.err) return { stale: true, text: 'Official derived view · Investors unavailable · ' + m.err };
  if (!d) return { stale: false, text: 'Official derived view · Investors loading…' };
  const age = (Date.now() - Date.parse(d.generated_at)) / 3600000;
  return { stale: !(age <= 36), text: `Official derived view · Investors built ${d.generated_at} · ${fmt(d.list.length)} companies with gains on investments tagged · rebuilt daily` + (age > 36 ? ' · stale' : '') };
}
window.HUB_NOTICES = Object.assign(window.HUB_NOTICES || {}, { investors: investorsNotice });
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { investors: investorsView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { investors: bindInvestors });
