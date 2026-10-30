/* Buyouts — the hub tab: which listed companies a private buyer could take over, and which are being talked about.
   - Candidates: every company's LBO at today's price plus 30% (IRR, the most a buyer could pay for 20% and how far that
     is from the price), the historical chance companies like it were bought within a year, the rumor signal, and a
     score that weighs the three;
   - Rumors & signals: headlines about sales and approaches, 8-Ks about strategic alternatives and proposals, 13Ds seeking
     a sale, announced deals;
   - History: the base rates year by year, what raised the odds (event rate by quintile of each figure), the premiums
     buyers paid (merger proxies), the latest deals with their premiums.
   One company: LBOView (lbo-view.js, also the "LBO & takeover" view of each company page).
   Data: data/research/lbo/{board,rumors,history,status}.json (app/lbo.py, app/lbo_board.cjs; branch research-lbo).
   Deep links: #buyouts/<view>, #buyouts/<TICKER>. */
const boStore = {};
function boData(name) {
  const m = boStore[name] || (boStore[name] = {});
  if (m.data || m.err || m.loading) return m;
  m.loading = fetch('data/research/lbo/' + name + '.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json() })
    .then(d => { m.data = d; if (state.tab === 'buyouts') render() }).catch(e => { m.err = e.message; if (state.tab === 'buyouts') render() });
  return m;
}
const BO_VIEWS = [['board', 'Buyout candidates'], ['rumors', 'Rumors & signals'], ['history', 'History: who gets bought'], ['one', 'One company']];
const BO_KIND = { news: 'News', '8-K': '8-K', '8-K deal': '8-K deal', '13D': '13D', deal: 'Agreed deal', 'SC 13E3': 'Going private', DEFM14A: 'Merger proxy', 'SC 14D9': 'Tender offer' };
const boTk = (t, cik) => `<button class="text-button" data-boo="${esc(cik)}" data-bot="${esc(t)}"><b>${esc(t)}</b></button>`;
const boPc = (v, d = 0) => v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(100 * v).toFixed(d)}%`;
const boP = (v, d = 1) => v == null ? '—' : `${(100 * v).toFixed(d)}%`;
function boRows(d) { const F = d.fields || []; return (d.rows || []).map(r => { const o = {}; F.forEach((k, i) => o[k] = r[i]); return o }) }
function boBoard(B) {
  const S = [['score', 'Buyout score (all three)'], ['max_vs_price', 'Buyout price above today'], ['irr', 'LBO IRR'], ['p_acquired', 'History: chance of being bought'], ['rumor', 'Rumors & signals']];
  state.bos = S.some(x => x[0] === state.bos) ? state.bos : 'score';
  state.bomin = state.bomin || '0.5';
  const q = (state.boq || '').trim().toUpperCase(), k = state.bos, minEv = +state.bomin * 1e9;
  let L = boRows(B).filter(r => (!q || r.ticker.includes(q) || String(r.name || '').toUpperCase().includes(q)) && (q || (r.ev || 0) >= minEv || k === 'rumor'));
  if (state.boclean !== 'all') L = L.filter(r => q || !(r.flags || []).length || k === 'rumor');
  L.sort((a, b) => (b[k] ?? -9) - (a[k] ?? -9));
  exported = L;
  const A = B.assumptions || {}, R = B.rates || {};
  return `<div class="toolbar">${field('bos', 'Rank by', S, k)}${field('bomin', 'Enterprise value at least', [['0', 'any'], ['0.5', '$0.5B'], ['2', '$2B'], ['10', '$10B']], state.bomin)}${field('boclean', 'Show', [['clean', 'buyable (no flags)'], ['all', 'every company']], state.boclean || 'clean')}<div class="field"><label for="boq">Ticker or name</label><input id="boq" value="${esc(state.boq || '')}" placeholder="e.g. WEN"></div></div>
    <div class="explain">Each company bought at today's price plus ${boP(A.premium, 0)}, with up to ${A.leverage}× EBITDA of new debt at SOFR ${R.base == null ? '' : R.base.toFixed(2) + '%'} + the high-yield B spread ${R.spread_b == null ? '' : R.spread_b.toFixed(2) + '%'} + 0.5%, five years of free cash flow repaying it, sold at today's multiple. "Buyout price" is the most a share for a ${boP(A.target, 0)} IRR — above today's price, borrowed money alone could justify a bid. History: how often companies with its figures were bought within a year. The score weighs the three (LBO 40%, history 35%, rumors 25%). Banks, insurers and REITs are left out; "flags" are companies already carrying over 6× EBITDA in net debt or larger than any buyout on record.</div>
    <div class="tablebox"><table><thead><tr><th>Company</th><th>Score</th><th>LBO IRR</th><th>Buyout price</th><th>vs today</th><th>EV / EBITDA</th><th>History</th><th>Latest signal</th></tr></thead><tbody>
    ${L.slice(0, 150).map(r => `<tr><td>${boTk(r.ticker, r.cik)}<br><span class="sub">${esc(r.name || '')}</span></td><td><b>${r.score ?? '—'}</b></td>
      <td class="${(r.irr || 0) >= (A.target || 0.2) ? 'positive' : ''}">${boP(r.irr)}</td><td>${r.max_price == null ? '—' : '$' + fmt(r.max_price, 2)}</td><td class="${(r.max_vs_price || -1) > 0 ? 'positive' : ''}">${boPc(r.max_vs_price)}</td>
      <td>${r.ev_ebitda == null ? '—' : fmt(r.ev_ebitda, 1) + '×'}${(r.flags || []).length ? `<br><span class="sub negative">${esc(r.flags.join(', '))}</span>` : ''}</td>
      <td>${boP(r.p_acquired)}${r.decile ? `<br><span class="sub">decile ${r.decile}</span>` : ''}</td>
      <td>${r.rumor_kind ? `<span class="sub">${esc(r.rumor_date || '')} · ${esc(BO_KIND[r.rumor_kind] || r.rumor_kind)}</span><br>${esc(r.rumor_text || '')}` : '—'}</td></tr>`).join('')}</tbody></table></div>`;
}
function boRumors(R) {
  const kinds = [...new Set(R.rows.map(r => r[3]))].sort();
  state.bok = kinds.includes(state.bok) ? state.bok : '';
  const L = R.rows.filter(r => !state.bok || r[3] === state.bok);
  return `<div class="toolbar">${field('bok', 'Kind', [['', 'Every kind'], ...kinds.map(k => [k, BO_KIND[k] || k])], state.bok)}</div>
    <div class="explain">Headlines from news searches for sales, approaches, take-private offers and talks (the headline, source and a link only), matched to listed companies by name or ticker; the companies' own 8-Ks about strategic alternatives, unsolicited or non-binding proposals and special committees; 13D purposes that speak of a sale or a proposal; merger proxies, tender-offer responses and going-private statements. A headline is not a deal.</div>
    <div class="tablebox"><table><thead><tr><th>Date</th><th>Company</th><th>Kind</th><th>What</th></tr></thead><tbody>
    ${L.slice(0, 300).map(r => `<tr><td>${esc(r[0] || '')}</td><td>${boTk(r[1], r[2])}</td><td>${esc(BO_KIND[r[3]] || r[3])}${r[7] === 'buyer' ? '<br><span class="sub">as the buyer</span>' : ''}</td><td>${r[6] ? `<a href="${esc(r[6])}" target="_blank" rel="noopener">${esc(r[4])}</a>` : esc(r[4])}${r[5] && r[3] === 'news' ? `<br><span class="sub">${esc(r[5])}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
}
function boHistory(H) {
  const m = (H.models || {}).acquired, pv = (H.models || {}).private, P = H.premiums || {}, F = H.features || {};
  if (!m) return empty('The history is being read (EDGAR form indexes and XBRL frames since 2011); it appears after the first full run.');
  const yr = (H.by_year || []).map(([y, n, a, p]) => `<tr><td>${y}</td><td>${fmt(n)}</td><td>${fmt(a)}</td><td>${boP(a / n, 2)}</td><td>${fmt(p)}</td></tr>`).join('');
  const lifts = Object.entries(H.lifts || {}).map(([k, qs]) => `<tr><td>${esc(F[k] || k)}</td>${qs.map(q => `<td title="${esc(q[0])} to ${esc(q[1])}">${boP(q[2], 2)}</td>`).join('')}</tr>`).join('');
  const QN = { q1: 'lowest fifth', q2: 'second fifth', q4: 'fourth fifth', q5: 'highest fifth', na: 'not reported' };
  const coef = Object.entries(m.coef || {}).filter(([k]) => k !== 'intercept').sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 12).map(([k, v]) => `<tr><td>${esc(F[k.split(':')[0]] || k)} — ${esc(QN[k.split(':')[1]] || '')}</td><td class="${v > 0 ? 'positive' : 'negative'}">${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}</td></tr>`).join('');
  const rec = (H.recent || []).slice(0, 80).map(r => `<tr><td>${esc(r[0])}</td><td>${r[2] ? boTk(r[2], r[1]) : esc(r[3])}</td><td>${esc(r[4])}${r[9] ? ' · going private' : ''}</td><td><b>${fmt(r[5], 1)}%</b><br><span class="sub">${esc(r[6] || '')}</span></td><td>${r[7] ? '$' + fmt(r[7], 2) : '—'}</td><td>${r[8] ? `<a href="${esc(r[8])}" target="_blank" rel="noopener">proxy ↗</a>` : ''}</td></tr>`).join('');
  return `<div class="explain">${esc(H.note || '')}</div>
    <div class="metrics">${kpi('Bought within a year', boP(m.base, 2), `of ${fmt(m.n)} company-years (${fmt(m.events)} deals)`)}${kpi('Model, out of time', 'AUC ' + (m.auc_test == null ? '—' : m.auc_test.toFixed(2)), `trained ${(m.train_years || []).join('–')}, tested ${(m.test_years || []).join('–')}`)}${kpi('Top tenth, tested', m.top_decile_rate == null || !m.base_test ? '—' : (m.top_decile_rate / m.base_test).toFixed(1) + '×', 'as often bought as the average')}${kpi('Premium paid, median', P.median == null ? '—' : fmt(P.median, 0) + '%', `middle half ${P.p25 == null ? '—' : fmt(P.p25, 0) + '–' + fmt(P.p75, 0) + '%'} · ${fmt(P.n)} proxies`)}</div>
    <h3>What raised the odds — share bought within a year, by quintile of each figure (lowest to highest)</h3>
    <div class="tablebox"><table><thead><tr><th>Figure</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Q5</th></tr></thead><tbody>${lifts}</tbody></table></div>
    <h3>The model's strongest weights (log-odds against the middle fifth of each figure; + raises the odds)</h3><div class="tablebox"><table><tbody>${coef}</tbody></table></div>
    ${pv ? `<p class="sub">Going private (Schedule 13E-3) on its own: ${boP(pv.base, 2)} a year, out-of-time AUC ${pv.auc_test == null ? '—' : pv.auc_test.toFixed(2)}.</p>` : ''}
    <h3>Year by year</h3><div class="tablebox"><table><thead><tr><th>Fiscal year</th><th>Companies</th><th>Bought the next year</th><th>Rate</th><th>Going private</th></tr></thead><tbody>${yr}</tbody></table></div>
    ${(P.by_sector || []).length ? `<h3>Premiums by sector</h3><div class="tablebox"><table><thead><tr><th>Sector</th><th>Proxies</th><th>Median</th><th>Middle half</th></tr></thead><tbody>${P.by_sector.map(s => `<tr><td>${esc(s[0])}</td><td>${fmt(s[1])}</td><td>${fmt(s[2], 0)}%</td><td>${fmt(s[3], 0)}–${fmt(s[4], 0)}%</td></tr>`).join('')}</tbody></table></div>` : ''}
    ${rec ? `<h3>Latest deals and the premium their proxies state</h3><div class="tablebox"><table><thead><tr><th>Filed</th><th>Company</th><th>Filing</th><th>Premium</th><th>Cash a share</th><th></th></tr></thead><tbody>${rec}</tbody></table></div>` : ''}`;
}
function buyoutsView() {
  state.bov = BO_VIEWS.some(v => v[0] === state.bov) ? state.bov : 'board';
  let out = `<div class="section-head"><h2>Buyouts</h2><span class="tag">LBO · HISTORY · RUMORS</span></div>
    <p class="sub">Which listed companies a private buyer could take over and at what price, how often companies like them were bought in the past, and what is being said about a sale now. A leveraged-buyout model on each company's own figures, every deal filing on EDGAR since 2011, news headlines and the companies' own filings.</p>
    <div class="toolbar">${field('bov', 'View', BO_VIEWS, state.bov)}</div>`;
  if (state.bov === 'one') return out + `<div class="toolbar"><div class="field wide"><label for="boone">Company (ticker)</label><input id="boone" value="${esc(state.boonet || '')}" placeholder="e.g. WEN · Enter"></div></div><div id="bo-one"></div>`;
  const name = state.bov === 'rumors' ? 'rumors' : state.bov === 'history' ? 'history' : 'board';
  const d = boData(name);
  if (d.err) return out + empty(`Buyouts could not load (${d.err}). It is rebuilt daily by the research-lbo workflow.`);
  if (!d.data) return out + empty('Loading…');
  return out + (name === 'rumors' ? boRumors(d.data) : name === 'history' ? boHistory(d.data) : boBoard(d.data));
}
function bindBuyouts() {
  if (state.tab !== 'buyouts') return;
  ['bov', 'bos', 'bomin', 'boclean', 'bok'].forEach(id => { if ($(id)) $(id).onchange = e => { state[id] = e.target.value; render() } });
  if ($('boq')) $('boq').onchange = e => { state.boq = e.target.value; render() };
  const one = (cik, t) => { state.bov = 'one'; state.boone = cik; state.boonet = t; render(); };
  document.querySelectorAll('#workspace [data-bot]').forEach(b => b.onclick = () => one(b.dataset.boo, b.dataset.bot));
  if ($('boone')) $('boone').onchange = e => {
    const t = e.target.value.trim().toUpperCase(), r = boRows((boData('board').data) || {}).find(x => x.ticker === t);
    if (r) one(String(r.cik), r.ticker); else $('bo-one').innerHTML = `<p class="muted">${esc(t)}: nothing on file for that ticker.</p>`;
  };
  if (state.bov === 'one' && $('bo-one') && state.boone && window.LBOView) window.LBOView.render($('bo-one'), { cik: state.boone, hub: '' });
}
function buyoutsDeepLink(arg) {
  const v = decodeURIComponent(arg || '').trim();
  if (BO_VIEWS.some(x => x[0] === v)) { state.bov = v; return; }
  const r = boRows((boData('board').data) || {}).find(x => x.ticker === v.toUpperCase());
  state.bov = 'one'; state.boonet = v.toUpperCase(); state.boone = r ? String(r.cik) : '';
}
window.HUB_NOTICES = Object.assign(window.HUB_NOTICES || {}, { buyouts: buyoutsNotice });
function buyoutsNotice() {
  const s = boData('status'), d = s.data;
  if (s.err) return { stale: true, text: 'Official derived view · Buyouts status unavailable · ' + s.err };
  if (!d) return { stale: false, text: 'Official derived view · Buyouts loading…' };
  const age = (Date.now() - Date.parse(d.built_at)) / 3600000;
  return { stale: !(age <= 36), text: `Official derived view · Buyouts built ${d.built_at} · ${fmt(d.companies)} companies · ${fmt(d.with_inputs)} with an LBO · ${fmt(d.with_history)} with a history score · ${fmt(d.with_rumors)} with rumors or signals · ${fmt(d.premiums)} premiums read · refreshed daily` + (age > 36 ? ' · stale' : '') };
}
window.HUB_VIEWS = Object.assign(window.HUB_VIEWS || {}, { buyouts: buyoutsView });
window.HUB_BINDS = Object.assign(window.HUB_BINDS || {}, { buyouts: bindBuyouts });
