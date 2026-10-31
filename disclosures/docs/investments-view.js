/* Investments — one company as an investor: what it earned on its investments over the last four quarters (SEC XBRL),
   and what it owns or bought, each graded by its evidence: A its own 13F and 13D/13G, B its own 8-K release, C another
   company's filing that names it as an investor. Data: data/research/investors/c/<cik>.json (app/investors.py).
   window.InvestmentsView.render(el, {cik, ticker, hub}) — the hub's Investors tab and the company page's "Investments". */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const usd = (v) => {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    return a >= 1e12 ? s + (a / 1e12).toFixed(2) + 'T' : a >= 1e9 ? s + (a / 1e9).toFixed(a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? s + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1) + 'M' : s + Math.round(a / 1e3) + 'K';
  };
  const pct = (v) => (fin(v) ? Math.round(100 * v) + '%' : '—');
  const GR = { A: ['#1f5f46', 'filed by the company itself: its 13F, or a 13D / 13G (over 5%)'], B: ['#4f7f6a', 'announced in its own 8-K release'],
    C: ['#8a7a4a', 'another company’s filing names it as an investor'] };
  const chip = (g) => `<span title="${esc((GR[g] || [])[1] || '')}" style="display:inline-block;min-width:16px;padding:0 4px;border-radius:4px;background:${(GR[g] || ['#888'])[0]};color:#fff;font:600 11px/16px monospace;text-align:center">${esc(g)}</span>`;
  const qlab = (p) => (p ? p.replace(/^CY(\d{4})Q(\d)$/, 'Q$2 $1') : '');
  function bars(series) {
    const pts = (series || []).slice(-8);
    if (pts.length < 2) return '';
    const W = 620, H = 170, top = 18, bot = 26, hi = Math.max(0, ...pts.map((p) => p[1])), lo = Math.min(0, ...pts.map((p) => p[1])), span = (hi - lo) || 1;
    const y0 = top + (H - top - bot) * hi / span, step = W / pts.length, bw = Math.min(46, step * 0.6);
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;height:auto" role="img" aria-label="Gains on investments by quarter">
      <line x1="0" x2="${W}" y1="${y0}" y2="${y0}" stroke="#d8d4cc"/>${pts.map((p, i) => {
      const h = Math.abs(p[1]) / span * (H - top - bot), x = i * step + (step - bw) / 2, y = p[1] >= 0 ? y0 - h : y0;
      return `<rect x="${x}" y="${y}" width="${bw}" height="${Math.max(1, h)}" rx="2" fill="${p[1] < 0 ? '#c0563d' : '#2e8b57'}"/>
        <text x="${x + bw / 2}" y="${p[1] >= 0 ? y - 4 : y + h + 12}" font-size="11" text-anchor="middle" fill="currentColor">${esc(usd(p[1]))}</text>
        <text x="${x + bw / 2}" y="${H - 8}" font-size="11" text-anchor="middle" fill="#6b6b6b">${esc(qlab(p[0]))}</text>`;
    }).join('')}</svg>`;
  }
  async function render(el, ctx) {
    const hub = (ctx && ctx.hub != null) ? ctx.hub : '';
    const site = hub ? hub.replace(/disclosures\/?$/, '') : '../';      // the main site, from the app, a search page or the hub
    el.innerHTML = '<p class="muted">Loading the investments…</p>';
    let d = null;
    try { const r = await fetch(`${hub}data/research/investors/c/${parseInt(ctx.cik, 10)}.json`, { cache: 'no-cache' }); d = r.ok ? await r.json() : null; } catch (e) { d = null; }
    if (!d && ctx.quiet) { el.innerHTML = ''; return; }
    if (!d) { el.innerHTML = '<p class="muted">No gains on investments are tagged in this company’s recent filings, or it is not among the companies read yet.</p>'; return; }
    const H = d.holdings || [], f = d.f13;
    const tiles = [['Gains on investments, 4 quarters', usd(d.gains), `${d.quarters} quarters to ${qlab((d.periods || []).slice(-1)[0])}`],
      ['Share of pre-tax income', pct(d.share), d.pretax ? 'pre-tax ' + usd(d.pretax) : ''], ['Equity-method income', usd(d.eqm), 'stakes it accounts for by share of profit'],
      f ? ['13F portfolio', usd(f.total), `${f.positions} listed positions, ${esc(f.period)}`] : null].filter(Boolean);
    const top = H.filter((h) => fin(h.price_gain)).sort((a, b) => b.price_gain - a.price_gain).slice(0, 3);
    const lead = `${esc(d.name)} booked <b>${usd(d.gains)}</b> of gains on investments over the last four quarters` + (fin(d.share) ? ` — ${pct(d.share)} of its pre-tax income` : '') + '.'
      + (top.length ? ` Its 13F points to where the latest quarter’s gains came from: ${top.map((h) => `${esc(h.name)} (${usd(h.price_gain)})`).join(', ')}.` : '')
      + (H.length ? ` ${H.length} holdings or investments are found in filings below.` : '');
    const row = (h) => {
      const name = h.cik ? `<a href="${esc(site)}#c-${esc(h.cik)}"><b>${esc(h.name)}</b></a>` : `<b>${esc(h.name)}</b>`;
      const also = (h.also || []).map((a) => `<br>${chip(a.grade)} <span class="sub">${esc(a.how)}${a.url ? ` · <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.date || 'filing')}</a>` : ''}${a.q ? ` — “${esc(String(a.q).slice(0, 220))}”` : ''}</span>`).join('');
      return `<tr><td>${chip(h.grade)}</td><td>${name}${h.t ? ` <span class="sub">${esc(h.t)}</span>` : ''}</td><td>${esc(h.how)}${h.status ? `<br><span class="sub">${esc(h.status)}</span>` : ''}</td>
        <td class="num">${usd(h.usd)}</td><td class="num ${fin(h.price_gain) ? (h.price_gain >= 0 ? 'positive' : 'negative') : ''}">${fin(h.price_gain) ? usd(h.price_gain) : '—'}</td>
        <td>${h.url ? `<a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.date || 'filing')}</a>` : esc(h.date || '')}${h.q ? `<br><span class="sub">“${esc(String(h.q).slice(0, 260))}”</span>` : ''}${also}</td></tr>`;
    };
    el.innerHTML = `<div class="section-head"><h3>Investments: what ${esc(d.t || d.name)} earns on them, and what it bought</h3></div>
      <p>${lead}</p>
      <div class="metrics" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px">${tiles.map((x) => `<div class="metric" style="border:1px solid var(--line,#ddd);border-radius:8px;padding:8px 10px"><span class="sub">${esc(x[0])}</span><br><b style="font-size:18px">${x[1]}</b><br><span class="sub">${x[2]}</span></div>`).join('')}</div>
      ${d.manager ? '<p class="sub">An asset manager: its 13F reports the funds it manages for clients, not its own investments, so it is not listed here; its gains are on its own balance sheet (seed capital, co-investments, carried interest).</p>' : ''}
      <h4>Gains on investments by quarter</h4>${bars(d.series)}
      ${H.length ? `<h4>What it owns or bought</h4><div class="tablebox tbl-wrap"><table><thead><tr><th></th><th>Company</th><th>How we know</th><th class="num">Value</th><th class="num">Price gain last quarter</th><th>Source</th></tr></thead><tbody>${H.map(row).join('')}</tbody></table></div>` : '<p class="muted">No holding is named in its filings or in other companies’ filings yet: its gains may come from private stakes no filing names.</p>'}
      ${(d.sold || []).length ? `<h4>Sold in the latest 13F quarter</h4><p>${d.sold.map((s) => `${esc(s.issuer)} (${usd(s.prev_usd)})`).join(' · ')}</p>` : ''}
      <p class="sub">${chip('A')} its own 13F (listed positions; the price gain is the shares held a quarter earlier × the change in price) or a 13D / 13G it filed · ${chip('B')} its own 8-K release · ${chip('C')} another company’s filing naming it as an investor (EDGAR full-text search: “investment from …”, “… invested”, “led by …”), with the sentence. Gains: ${esc(d.concept || '')} as tagged in its 10-Q / 10-K (realized and unrealized). A stake no filing names stays unknown. Not investment advice.</p>`;
  }
  window.InvestmentsView = { render };
})();
