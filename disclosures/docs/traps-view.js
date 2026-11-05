/* Analysis traps — one company's findings (pipeline/traps.py, data/traps/<cik>.json): the three to check first, then
   every rule with its status, the figures, the innocent explanations and what to look for in the filing. Shared by the
   "Analysis traps" view of each company page on the Sankey site (views.json) and the Hub's tab (traps.js).
   window.TrapsView.render(el, {cik, ticker, site, hub, here}) — site: the path to the Sankey site ('' there, '../' in the hub). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const big = (v) => { if (!fin(v)) return '—'; if (+v === 0) return '$0'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? '$' + (a / 1e9).toFixed(1) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(0) + 'M' : '$' + (a / 1e3).toFixed(0) + 'K'); };
  const WORD = { triggered: 'Triggered', clear: 'Not triggered', insufficient_data: 'Insufficient data', not_applicable: 'Not applicable', review: 'To review', expired: 'Out of date' };
  const CLS = { triggered: 'trig', clear: 'ok', insufficient_data: 'na', not_applicable: 'na', review: 'rev', expired: 'na' };
  const cache = {};
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.tv{display:grid;gap:12px;font-size:14px}.tv h3{margin:0 0 4px;font-size:15px}.tv .tv-id{font-family:var(--mono,monospace);font-size:12px;color:var(--muted,#6b6a66);margin-right:4px}
.tv .tv-st{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:999px;border:1px solid var(--line,#ddd);color:var(--muted,#6b6a66);vertical-align:middle;margin-left:6px}
.tv .tv-st.trig{color:#b42318;border-color:#f0b4ad}.tv .tv-st.rev{color:#8a5a00;border-color:#efd59a}.tv .tv-st.ok{color:#17734a;border-color:#b7dfc9}
.tv .tv-card{border:1px solid var(--line,#ddd);border-radius:8px;padding:10px 14px;background:var(--surface,transparent)}.tv .tv-card.trig{border-left:3px solid #b42318}.tv .tv-card.rev{border-left:3px solid #d9822b}
.tv p{margin:4px 0}.tv ul{margin:4px 0;padding-left:18px}.tv details summary{cursor:pointer;color:var(--muted,#6b6a66)}.tv table{border-collapse:collapse;width:100%;font-size:13px}.tv td{padding:2px 6px;border-bottom:1px solid var(--line,#eee)}.tv td.n{text-align:right;font-variant-numeric:tabular-nums}
.tv .muted{color:var(--muted,#6b6a66)}.tv .tv-small{font-size:12.5px}`;
    document.head.appendChild(s);
  }
  function load(site, cik) {
    const key = site + cik;
    if (!cache[key]) cache[key] = fetch(`${site}data/traps/${encodeURIComponent(cik)}.json`, { cache: 'no-cache' }).then((r) => {
      if (!r.ok) throw new Error(r.status === 404 ? 'No analysis-trap file for this company yet (it is written with the site; a company without a published quarter has none).' : 'HTTP ' + r.status);
      return r.json();
    }).catch((e) => { delete cache[key]; throw e; });
    return cache[key];
  }
  const PCT = /(_pct|_yoy|_growth|_change|share_of_delta|_share|latest_gap_pct|eps_growth_from_share_count)$/;
  function val(k, v) {
    if (v == null) return '—';
    if (Array.isArray(v)) return v.map((r) => (Array.isArray(r) ? r.join(' / ') : r)).join('; ');
    if (typeof v === 'string') return v;
    if (PCT.test(k)) return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(1) + '%';
    if (/^eps/.test(k)) return '$' + (+v).toFixed(2);
    if (/dso|cover_ratio|buybacks_over_sbc/.test(k)) return (+v).toFixed(1);
    if (/shares/.test(k)) return (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v.toLocaleString('en-US')) + ' shares';
    if (Math.abs(v) >= 1e5) return big(v);
    return Number.isInteger(v) ? v.toLocaleString('en-US') : (+v).toFixed(2);
  }
  const label = (k) => k.replace(/_/g, ' ').replace(/\bpct\b/, '%').replace(/\byoy\b/, 'y/y').replace(/\bttm\b/, '12 months').replace(/\bfy\b/, 'fiscal year').replace(/\bocf\b/, 'operating cash flow').replace(/\bfcf\b/, 'free cash flow').replace(/\bsbc\b/, 'stock compensation').replace(/\bwc\b/, 'working capital').replace(/\bdso\b/, 'DSO').replace(/\beps\b/, 'EPS');
  function one(f) {
    const st = f.status, head = `<h3><span class="tv-id">${esc(f.rule_id)}</span>${esc(f.name)}<span class="tv-st ${CLS[st]}">${WORD[st]}</span>` +
      (st === 'triggered' ? ` <span class="muted tv-small">severity ${esc(f.severity)} · confidence ${esc(f.confidence)}</span>` : f.confidence ? ` <span class="muted tv-small">confidence ${esc(f.confidence)}</span>` : '') + '</h3>';
    if (st === 'insufficient_data' || st === 'not_applicable' || st === 'expired') return `<div class="tv-card">${head}<p class="muted">${esc(f.reason || '')}</p></div>`;
    let h = `<div class="tv-card ${CLS[st]}">${head}<p>${esc(f.explanation)}</p>`;
    const obs = Object.entries(f.observed || {});
    if (obs.length) h += `<details><summary>The figures and how they are read</summary><table><tbody>${obs.map(([k, v]) => `<tr><td>${esc(label(k))}</td><td class="n">${esc(val(k, v))}</td></tr>`).join('')}</tbody></table><p class="muted tv-small">${esc(f.how)}</p>` +
      ((f.evidence || []).length ? `<p class="muted tv-small">Source: ${f.evidence.map((x) => (x.url ? `<a href="${esc(x.url)}" rel="nofollow">${esc(x.period)}</a>` : esc(x.period)) + (x.what ? ` (${esc(x.what)})` : '')).join(' · ')}</p>` : '') + '</details>';
    if (st === 'triggered' || st === 'review') {
      if ((f.alternative_explanations || []).length) h += `<p><b>What would explain it innocently</b></p><ul>${f.alternative_explanations.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`;
      if ((f.missing_evidence || []).length) h += `<p><b>What to look for in the filing</b></p><ul>${f.missing_evidence.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`;
    }
    return h + '</div>';
  }
  async function render(el, opt) {
    css();
    const site = opt.site != null ? opt.site : (opt.hub ? '' : '../');
    const here = () => el.isConnected && (typeof opt.here !== 'function' || opt.here());
    el.innerHTML = '<p class="muted">Reading the findings…</p>';
    let d;
    try { d = await load(site, opt.cik); } catch (e) { if (here()) el.innerHTML = `<div class="tv"><p class="muted">${esc(e.message)}</p></div>`; return; }
    if (!here()) return;
    const F = Object.fromEntries(d.findings.map((f) => [f.rule_id, f]));
    const pri = (d.priority || []).map((k) => F[k]).filter(Boolean);
    const s = d.summary || {};
    const lead = `${s.triggered || 0} of ${d.findings.length} rules triggered on the filings to ${esc(d.as_of || '')}` + (s.review ? `, ${s.review} to review` : '') + (s.insufficient_data ? `, ${s.insufficient_data} with insufficient data` : '') + (s.not_applicable ? `, ${s.not_applicable} not applicable` : '') + '.';
    el.innerHTML = `<div class="tv"><div><h3>Analysis traps: where the figures could mislead you</h3><p class="muted">${lead} Each is a question to verify, with the normal explanation that would produce the same figures; not a finding of manipulation, not a view on the stock. Rules v${esc(d.rule_version)}.</p></div>`
      + (pri.length ? `<div><p><b>Check these first</b></p>${pri.map((f) => `<div class="tv-card ${CLS[f.status]}"><p><b>${esc(f.name)}</b><span class="tv-st ${CLS[f.status]}">${WORD[f.status]}</span>${f.severity ? ` <span class="muted tv-small">severity ${esc(f.severity)}</span>` : ''}</p><p>${esc(f.explanation)}</p>${(f.alternative_explanations || [])[0] ? `<p class="muted tv-small">Innocent reading: ${esc(f.alternative_explanations[0])}.</p>` : ''}</div>`).join('')}</div>`
        : '<p>No rule is triggered on the latest filings.</p>')
      + `<div><p><b>Every rule</b></p>${d.findings.map(one).join('')}</div>`
      + `<p class="muted tv-small"><a href="${esc(site)}disclosures/analysis-traps/">Every rule and the companies it triggers on →</a> · <a href="${esc(site)}c/${esc(String(opt.ticker || '').toLowerCase().replace(/\./g, '-') || ('cik-' + opt.cik))}/analysis-traps/">This company's page →</a> · Not investment advice.</p></div>`;
  }
  window.TrapsView = { render, load };
})();
