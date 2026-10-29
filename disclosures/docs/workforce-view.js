/* Workforce — one company's headcount from its own 10-Ks, revenue and profit per employee against its industry, and
   hiring or layoffs year on year (shared by the Disclosure Hub's Workforce tab and the "Workforce" view of each company
   page, listed in views.json). Data: data/research/employees/c/<cik>.json (app/employees.py, branch research-employees).
   window.WorkforceView.render(el, {cik, hub, here}) — hub: the path to the hub ('disclosures/' on the Sankey site, '' inside it). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const int = (v) => (fin(v) ? Math.round(v).toLocaleString('en-US') : '—');
  const pct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? '$' + (a / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + (a / 1e6).toFixed(a >= 1e7 ? 1 : 2) + 'M' : a >= 1e3 ? '$' + Math.round(a / 1e3) + 'K' : '$' + Math.round(a)); };
  const ord = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
  const pc = (v) => Math.min(99, Math.max(1, Math.round(100 * v)));
  const SECTOR = { technology: 'Technology', communication: 'Communication', 'consumer-disc': 'Consumer discretionary', 'consumer-staples': 'Consumer staples', health: 'Health care',
    financials: 'Financials', 'real-estate': 'Real estate', energy: 'Energy', materials: 'Materials', industrials: 'Industrials', utilities: 'Utilities', other: 'Other' };
  const group = (g) => (/^SIC /.test(g || '') ? 'its industry (' + g + ')' : SECTOR[g] || g || 'its peers');
  const cache = {};
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.wf{display:grid;gap:14px}.wf .wf-card{border:1px solid var(--line,#d0d5dd);border-radius:8px;padding:12px 14px;min-width:0}
.wf h3{margin:0 0 6px;font-size:1rem}.wf .wf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.wf .wf-k{font-size:.8rem;opacity:.75}.wf .wf-v{font-size:1.5rem;font-weight:600}.wf .wf-s{font-size:.82rem;opacity:.8}
.wf table{border-collapse:collapse;width:100%;min-width:0!important;font-size:.86rem}.wf td,.wf th{padding:4px 6px;border-bottom:1px solid var(--line,#e4e7ec);text-align:left;vertical-align:top;white-space:normal}
.wf td.n,.wf th.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.wf .scroll{overflow-x:auto;max-width:100%}.wf .up{color:#17734a}.wf .down{color:#b42318}
.wf blockquote{margin:4px 0;padding:6px 10px;border-left:3px solid var(--line,#d0d5dd);font-size:.84rem;opacity:.9}.wf svg{display:block;width:100%;height:auto;max-width:760px}.wf .muted{opacity:.75}`;
    document.head.appendChild(s);
  }
  function load(hub, cik) {
    const key = hub + cik;
    if (!cache[key]) cache[key] = fetch(`${hub}data/research/employees/c/${encodeURIComponent(cik)}.json`, { cache: 'no-cache' }).then((r) => {
      if (!r.ok) throw new Error(r.status === 404 ? 'No headcount read yet for this company (its 10-Ks are read a few hundred a day, largest companies first; some do not state a number)' : 'Workforce research unavailable (HTTP ' + r.status + ')');
      return r.json();
    }).catch((e) => { delete cache[key]; throw e; });
    return cache[key];
  }
  function chart(ys) {
    const Y = ys.filter((y) => fin(y.count));
    if (Y.length < 2) return '';
    const W = 640, H = 230, L = 20, R = 20, T = 26, B = 30, n = Y.length, bw = Math.min(70, (W - L - R) / n * 0.6);
    const max = Math.max(...Y.map((y) => y.count)), rv = Y.map((y) => y.rev_emp).filter(fin), rmax = rv.length ? Math.max(...rv) * 1.1 : 1;
    const X = (i) => L + (i + 0.5) * (W - L - R) / n, Yc = (v) => T + (1 - v / max) * (H - T - B), Yr = (v) => T + (1 - v / rmax) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Employees by year with revenue per employee">`;
    Y.forEach((y, i) => { s += `<rect x="${X(i) - bw / 2}" y="${Yc(y.count)}" width="${bw}" height="${H - B - Yc(y.count)}" fill="#8aa4c8"><title>${esc(y.period)}: ${int(y.count)} employees</title></rect><text x="${X(i)}" y="${H - 10}" font-size="11" text-anchor="middle" fill="currentColor">${esc(String(y.period).slice(0, 4))}</text><text x="${X(i)}" y="${Yc(y.count) - 4}" font-size="10" text-anchor="middle" fill="currentColor">${y.count >= 1e6 ? (y.count / 1e6).toFixed(2) + 'M' : y.count >= 1e4 ? Math.round(y.count / 1e3) + 'K' : int(y.count)}</text>`; });
    const pts = Y.map((y, i) => (fin(y.rev_emp) ? [X(i), Yr(y.rev_emp)] : null)).filter(Boolean);
    if (pts.length > 1) s += `<path d="${pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ')}" fill="none" stroke="#b54708" stroke-width="2.5"/>` + pts.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="#b54708"/>`).join('');
    s += `<text x="${L}" y="12" font-size="11" fill="#5b7bab">■ employees</text><text x="${W - R}" y="12" font-size="11" text-anchor="end" fill="#b54708">● revenue per employee</text></svg>`;
    return s + '<p class="muted">Bars: employees at each fiscal year end. Line: revenue per employee.</p>';
  }
  async function render(el, opt) {
    css();
    const hub = (opt && opt.hub) || '', cik = String((opt && opt.cik) || '').replace(/^0+/, '');
    if (!cik) { el.innerHTML = '<p class="muted">No company selected.</p>'; return; }
    el.innerHTML = '<p class="muted">Reading the workforce research…</p>';
    let d;
    try { d = await load(hub, cik); } catch (e) {
      if ((opt && opt.here && !opt.here()) || !el.isConnected) return;
      el.innerHTML = `<div class="wf"><div class="wf-card"><h3>Workforce</h3><p class="muted">${esc(e.message)}.</p></div></div>`;
      return;
    }
    if (opt && opt.here && !opt.here()) return;
    const r = d.row || {}, ys = d.years || [], last = ys[ys.length - 1] || {};
    const flag = r.flag === 'layoffs' ? '<span class="down">fewer people</span>' : r.flag === 'hiring' ? '<span class="up">hiring</span>' : r.flag ? `<span class="up">${esc(r.flag)}</span>` : '';
    const peerTxt = (v, p, med, f) => `${fin(p) ? ord(pc(p)) + ' percentile' : '—'} in ${esc(group(r.peer_group))}${fin(med) ? ` · median ${f(med)}` : ''}`;
    el.innerHTML = `<div class="wf"><div class="wf-card"><h3>Workforce · ${esc(r.name || '')} <span class="muted">${esc(r.ticker || '')}</span></h3>
      <div class="wf-grid">
        <div><div class="wf-k">Employees</div><div class="wf-v">${int(r.employees)}</div><div class="wf-s">as of ${esc(r.as_of || '—')}, as the 10-K states it</div></div>
        <div><div class="wf-k">Change in a year</div><div class="wf-v ${(r.change || 0) < 0 ? 'down' : (r.change || 0) > 0 ? 'up' : ''}">${pct(r.change)}</div><div class="wf-s">${fin(r.change_n) ? (r.change_n >= 0 ? '+' : '−') + int(Math.abs(r.change_n)) + ' people' : ''}${fin(r.rev_growth) ? ` · revenue ${pct(r.rev_growth)}` : ''} ${flag}</div></div>
        <div><div class="wf-k">Revenue per employee</div><div class="wf-v">${big(r.rev_emp)}</div><div class="wf-s">${peerTxt(r.rev_emp, r.rev_emp_pct, r.rev_emp_med, big)}</div></div>
        <div><div class="wf-k">Net income per employee</div><div class="wf-v">${big(r.ni_emp)}</div><div class="wf-s">${peerTxt(r.ni_emp, r.ni_emp_pct, r.ni_emp_med, big)}</div></div>
      </div>${chart(ys)}</div>
      <div class="wf-card"><h3>Year by year</h3><div class="scroll"><table><thead><tr><th>Fiscal year</th><th class="n">Employees</th><th class="n">Change</th><th class="n">Revenue</th><th class="n">Revenue / person</th><th class="n">Net income / person</th><th>Source</th></tr></thead>
        <tbody>${ys.slice().reverse().map((y) => `<tr><td>${esc(y.period)}</td><td class="n">${int(y.count)}</td><td class="n ${(y.change || 0) < 0 ? 'down' : (y.change || 0) > 0 ? 'up' : ''}">${pct(y.change)}</td><td class="n">${big(y.rev)}</td><td class="n">${big(y.rev_emp)}</td><td class="n">${big(y.ni_emp)}</td><td>${y.url ? `<a href="${esc(y.url)}" target="_blank" rel="noopener">10-K, ${esc(y.filed || '')}</a>` : ''}</td></tr>`).join('')}</tbody></table></div>
        ${last.sentence ? `<p class="wf-s">In its words (latest 10-K):</p><blockquote>${esc(last.sentence)}</blockquote>` : ''}
        <details><summary>Every sentence the numbers come from</summary>${ys.slice().reverse().map((y) => `<p class="wf-s"><b>${esc(y.period)}</b> · ${esc(y.where || '')}</p><blockquote>${esc(y.sentence || '')}</blockquote>`).join('')}</details></div>
      ${(d.peers || []).length ? `<div class="wf-card"><h3>Peers: ${esc(group(r.peer_group))}</h3><div class="scroll"><table><thead><tr><th>Company</th><th class="n">Employees</th><th class="n">Revenue / person</th><th class="n">Net income / person</th><th class="n">Change</th></tr></thead>
        <tbody>${d.peers.map((p) => `<tr${p[0] === r.ticker ? ' style="font-weight:600"' : ''}><td>${esc(p[0])} <span class="muted">${esc(p[1] || '')}</span></td><td class="n">${int(p[2])}</td><td class="n">${big(p[3])}</td><td class="n">${big(p[4])}</td><td class="n">${pct(p[5])}</td></tr>`).join('')}</tbody></table></div></div>` : ''}
      <p class="muted">Headcounts are what each company states in its 10-K (some count full-time staff only, some include part-time or contract workers — the sentence shows which). Revenue and net income: the company's XBRL facts for the matching fiscal year. A smaller workforce with growing revenue can mean efficiency or outsourcing; the filing's own words say which. Research, not investment advice.${hub ? ` <a href="${hub}#workforce">Every company →</a>` : ''}</p></div>`;
  }
  window.WorkforceView = { render };
})();
