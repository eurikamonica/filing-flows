/* Filings radar — one company, shared by the Disclosure Hub (Filings radar → One company) and the main site's company
   page (the "Filings radar" view listed in disclosures/views.json). Self-contained:
     window.FilingsRadarView.render(element, {ticker, cik, hub}) reads <hub>data/research/filings/c/<TICKER>.json
     (app/filings_radar.py, branch research-filings) and draws what is on file: red flags (late filings, auditor changes,
     restatements, listing notices), SEC comment letter threads, buyback authorizations and dividends, offerings and the
     change in shares outstanding, the IPO and its lock-up, deals, CEO pay against the shareholder return, federal
     contracts, lobbying and officials' trades. Colours come from the host page's CSS variables. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, a >= 1e7 ? 0 : 1) + 'M' : a >= 1e3 ? '$' + num(a / 1e3, 0) + 'K' : '$' + num(a, 0)); };
  const pct = (v, d = 1) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const usd = (v, d = 2) => (fin(v) ? '$' + num(v, d) : '—');
  const day = (s) => (s ? String(s).slice(0, 10) : '—');
  const link = (u, l) => (/^https:\/\//.test(u || '') ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(l || 'Filing ↗')}</a>` : '');
  const SEV = { high: 'High', medium: 'Medium', low: 'Low' };
  const TOPIC = { revenue: 'revenue recognition', non_gaap: 'non-GAAP measures', segments: 'segments', impairment: 'impairment / goodwill', going_concern: 'going concern',
    crypto: 'crypto assets', liquidity: 'MD&A / liquidity', china: 'China / VIE structure', cyber: 'cybersecurity', controls: 'internal controls', tax: 'income taxes',
    related: 'related parties', acquisitions: 'acquisitions', reserves: 'reserves', climate: 'climate', ai: 'AI disclosure', leases: 'leases', stock_comp: 'stock compensation', inventory: 'inventory' };

  function css() {
    if (document.getElementById('frv-css')) return;
    const s = document.createElement('style'); s.id = 'frv-css';
    s.textContent = `.frv h3{margin:22px 0 6px;font-size:16px}.frv .frv-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45}
.frv-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:8px 0 6px}
.frv-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 12px}.frv-card b{display:block;font-size:19px;font-variant-numeric:tabular-nums;margin-top:2px}
.frv-card span{font-size:12px;color:var(--muted,#777)}
.frv-tbl{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0 8px}.frv-tbl th,.frv-tbl td{padding:6px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.frv-tbl td.n,.frv-tbl th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.frv-tbl th{font-weight:600;color:var(--muted,#666);font-size:12px}
.frv-wrap{overflow-x:auto}.frv-sev{display:inline-block;font-size:11px;padding:1px 8px;border-radius:9px;border:1px solid var(--line,#ddd)}
.frv-sev.high{color:var(--mk-cost,#c0392b);border-color:var(--mk-cost,#c0392b)}.frv-sev.medium{color:var(--q-warm,#d9822b);border-color:var(--q-warm,#d9822b)}
.frv-pos{color:var(--mk-profit,#2e8b57)}.frv-neg{color:var(--mk-cost,#c0392b)}.frv-note{font-size:12px;color:var(--muted,#777);line-height:1.5;margin-top:14px}
.frv q{display:block;font-size:12px;color:var(--muted,#777);margin:3px 0 0;max-width:72ch}`;
    document.head.appendChild(s);
  }
  const tbl = (head, rows, nums) => rows.length ? `<div class="frv-wrap"><table class="frv-tbl"><thead><tr>${head.map((h, i) => `<th${nums && nums.includes(i) ? ' class="n"' : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${nums && nums.includes(i) ? ' class="n"' : ''}>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '';
  const card = (label, value, sub) => `<div class="frv-card"><span>${esc(label)}</span><b>${value}</b>${sub ? `<span>${sub}</span>` : ''}</div>`;

  function flagLine(r) {
    if (r.kind === 'late') return `Filed ${esc(r.form)} — the ${r.form && r.form.indexOf('10-K') >= 0 ? 'annual' : 'quarterly'} report is late.${r.reason ? ` <q>${esc(r.reason)}</q>` : ''}${r.significant_change ? ' Expects a significant change in results.' : ''}`;
    if (r.kind === 'auditor') return `Auditor ${esc(r.change || 'changed')}${r.old ? `: ${esc(r.old)}` : ''}${r.new ? ` → ${esc(r.new)}` : ''}.${r.disagreements ? ' Disagreements reported.' : r.disagreements === false ? ' No disagreements.' : ''}${r.material_weakness ? ' Material weakness mentioned.' : ''}${r.going_concern ? ' Going-concern doubt mentioned.' : ''}`;
    if (r.kind === 'restatement') return `Earlier statements should no longer be relied on${(r.periods || []).length ? ` (periods ended ${r.periods.map(esc).join(', ')})` : ''}.${r.reason ? ` <q>${esc(r.reason)}</q>` : ''}`;
    if (r.kind === 'listing') return `${esc(r.exchange || 'Exchange')} notice: ${esc(r.reason || 'a listing rule')}${r.deadline ? `, until ${esc(r.deadline)} to regain compliance` : ''}.${r.determination ? ' <b>Delisting or suspension determination.</b>' : ''}`;
    return esc(r.label || r.kind);
  }

  function draw(el, d, opt) {
    const tk = d.ticker || opt.ticker || '';
    let h = `<div class="frv"><p class="frv-sub">Filings that flag trouble or change the share count, and the money around them, for ${esc(tk)}. From SEC EDGAR (8-K, NT 10-K / 10-Q, CORRESP / UPLOAD, S-3, 424B, DEFM14A, SC TO-T, DEF 14A XBRL), USAspending.gov and the Senate's lobbying filings.</p>`;
    const F = d.redflags || [], L = d.letters || [], B = d.buybacks || [], V = d.dividends || [], O = d.offerings || [], S = (d.shares || [])[0], R = (d.returns || [])[0];
    const P = (d.paycomp || [])[0], C = (d.contracts || [])[0], LB = (d.lobbying || [])[0], OFF = d.officials || [], DL = d.deals || [], IPO = (d.ipo || [])[0];
    h += `<div class="frv-cards">${card('Red flags (1 year)', num(F.length), F.length ? `latest ${esc(day(F[0].filed))}` : 'none on file')}${card('SEC letter threads', num(L.length), L.length ? `last ${esc(day(L[0].last))}` : 'none in 2 years')}${R ? card('Returned last year', pct(R.total_yield), `buybacks ${big(R.buybacks)} · dividends ${big(R.dividends)}`) : ''}${S ? card('Shares outstanding, 1 year', spct(S.change), `${num(S.shares_year_ago)} → ${num(S.shares)}`) : ''}${P ? card('CEO pay (total)', big(P.total), P.total_chg != null ? `${spct(P.total_chg)} vs the year before` : '') : ''}${C ? card('Federal contracts, 90 days', big(C.amount), 'obligations (USAspending)') : ''}${LB ? card('Lobbying, 4 quarters', big(LB.trailing4), (LB.issues || []).slice(0, 2).map(esc).join(', ')) : ''}</div>`;
    if (F.length) h += `<h3>Red flags</h3>` + tbl(['Filed', 'Severity', 'What', 'Source'], F.map((r) => [esc(day(r.filed)), `<span class="frv-sev ${esc(r.severity)}">${esc(SEV[r.severity] || r.severity)}</span>`, flagLine(r), link(r.url)]));
    if (L.length) h += `<h3>SEC comment letters</h3><p class="frv-sub">Released at least 20 business days after a review closed: these are finished reviews.</p>` + tbl(['Thread', 'Letters', 'Review of', 'Topics', 'Last letter'], L.map((t) => [`${esc(day(t.first))} → ${esc(day(t.last))}${t.closed ? ' · closed' : ''}`, num(t.n), esc((t.about_form || '—') + (t.about_period ? ' for ' + t.about_period : '')), (t.topics || []).map((x) => esc(TOPIC[x] || x)).join(', ') || '—', link((t.letters || []).slice(-1)[0] && t.letters.slice(-1)[0].url, 'Last letter ↗')]), [1]);
    if (B.length) h += `<h3>Buyback authorizations</h3>` + tbl(['Filed', 'Amount', '% of market cap', 'Expires', ''], B.map((r) => [esc(day(r.filed)), big(r.amount) + (r.increase ? ' (added)' : ''), pct(r.pct_mcap), r.no_expiration ? 'no expiration' : esc(r.expires || '—'), link(r.url)]), [1, 2]);
    if (V.length) h += `<h3>Dividends declared</h3>` + tbl(['Filed', 'Per share', 'Frequency', 'Record (= ex-date)', 'Payable', 'Change', 'Yield'], V.map((r) => [esc(day(r.filed)), usd(r.amount, 4), esc(r.freq || '—'), esc(r.record || '—'), esc(r.payable || '—'), esc(r.change || '—'), pct(r.yield, 2)]), [1, 6]);
    if (O.length || S) h += `<h3>Offerings and dilution</h3>` + (S ? `<p class="frv-sub">Shares outstanding ${num(S.shares_year_ago)} (${esc(S.year_ago || '')}) → ${num(S.shares)} (${esc(S.as_of || '')}): ${spct(S.change)}.</p>` : '') + tbl(['Filed', 'Form', 'Kind', 'Size', '% of market cap', ''], O.map((r) => [esc(day(r.filed)), esc(r.form), esc({ atm: 'at-the-market program', firm: 'offering', shelf: r.automatic ? 'automatic shelf' : 'shelf registration', other: 'other' }[r.kind] || r.kind), big(r.amount), pct(r.pct_mcap), link(r.url)]), [3, 4]);
    if (IPO) h += `<h3>IPO</h3><p class="frv-sub">Priced ${esc(IPO.date || IPO.filed)} at ${usd(IPO.price)} (${num(IPO.shares)} shares, ${big(IPO.raised)}) on ${esc(IPO.exchange || '—')}. Lock-up ${num(IPO.lockup_days)} days, ends ${esc(IPO.lockup_ends || '—')}. ${IPO.since_ipo != null ? `Since pricing: ${spct(IPO.since_ipo)}.` : ''} ${link(IPO.url, 'Prospectus ↗')}</p>`;
    if (DL.length) h += `<h3>Deals</h3>` + tbl(['Role', 'Target', 'Acquirer', 'Terms per share', 'Spread', 'Expected close', 'Status'], DL.map((x) => [esc(x.role), esc(x.target || '—') + (x.target_ticker ? ` (${esc(x.target_ticker)})` : ''), esc(x.acquirer || '—') + (x.acquirer_ticker ? ` (${esc(x.acquirer_ticker)})` : ''), [x.cash ? usd(x.cash) + ' cash' : '', x.ratio ? num(x.ratio, 4) + ' shares' : ''].filter(Boolean).join(' + '), spct(x.spread), esc(x.close_by || x.close_text || '—'), esc(x.status)]), [4]);
    if (P) h += `<h3>CEO pay against the shareholder return</h3><p class="frv-sub">Pay versus performance from the proxy statement (XBRL). TSR is the value of $100 invested at the start of the table.${P.misaligned ? ' <b>Pay rose 20%+ in a year the TSR value fell 10%+.</b>' : ''}</p>` + tbl(['Fiscal year end', 'Total pay', 'Actually paid', 'TSR ($100)', 'Peer TSR'], (P.years || []).slice().reverse().map((y) => [esc(y.fy_end), big(y.PeoTotalCompAmt), big(y.PeoActuallyPaidCompAmt), num(y.TotalShareholderRtnAmt, 0), num(y.PeerGroupTotalShareholderRtnAmt, 0)]), [1, 2, 3, 4]);
    if (OFF.length) h += `<h3>Officials who traded it</h3><p class="frv-sub">House and Senate periodic transaction reports in the last 120 days, beside the company's federal contracts and lobbying. A fact to note, not evidence of anything.</p>` + tbl(['Date', 'Official', 'Trade', 'Amount', 'Filed', ''], OFF.map((r) => [esc(r.date), esc(r.person) + ` <span class="frv-sub">(${esc(r.chamber)})</span>`, esc(r.type), r.amount_max ? `${big(r.amount_min)}–${big(r.amount_max)}` : `over ${big(r.amount_min)}`, esc(r.filed || '—'), link(r.source_url, 'Report ↗')]));
    if (!F.length && !L.length && !B.length && !V.length && !O.length && !S && !IPO && !DL.length && !P && !C && !LB) h += '<p class="frv-sub">Nothing on file for this company yet.</p>';
    h += `<p class="frv-note">Severity is a rule of thumb (an auditor resignation, disagreements, a restatement or a late annual report count as high), not a judgment of the company. Deal terms are read from the filing text; collars, CVRs and elections are not modelled. Not investment advice.</p></div>`;
    el.innerHTML = h;
  }

  async function render(el, opt = {}) {
    css();
    const tk = String(opt.ticker || '').toUpperCase().replace(/\./g, '-');
    if (!tk) { el.innerHTML = '<p class="frv-sub">No ticker for this company.</p>'; return; }
    el.innerHTML = '<p class="frv-sub">Loading the filings radar…</p>';
    const base = opt.hub == null ? '' : opt.hub;
    try {
      const r = await fetch(`${base}data/research/filings/c/${encodeURIComponent(tk.replace(/[^A-Z0-9-]/g, '_'))}.json`, { cache: 'no-cache' });
      if (opt.here && !opt.here()) return;
      if (r.status === 404) { css(); el.innerHTML = `<div class="frv"><p class="frv-sub">No red flags, SEC letters, buybacks, dividends, offerings, deals, CEO pay or contracts on file for ${esc(tk)} yet. The radar reads EDGAR's daily indexes every six hours.</p></div>`; return; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      draw(el, await r.json(), opt);
    } catch (e) {
      el.innerHTML = `<p class="frv-sub">The filings radar could not load (${esc(e.message)}).</p>`;
    }
  }
  window.FilingsRadarView = { render, flagLine, TOPIC };
})();
