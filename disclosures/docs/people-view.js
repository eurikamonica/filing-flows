/* Insiders+ — one company's view on the main site (company page → "Insiders+", listed in disclosures/views.json) and
   usable by the hub: the company's recent Form 4 trades beside the history of similar trades (event study), the 13F
   managers among the tracked ones that hold it, and the analysts' price-target record for the stock.
   window.PeopleView.render(el, {ticker, cik, hub}) reads data/research/people/*.json (app/people.py). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const sp = (v) => (fin(v) ? `<span style="color:${v > 0 ? 'var(--mk-profit,#2e8b57)' : v < 0 ? 'var(--mk-cost,#c0392b)' : 'inherit'}">${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(v) * 100, 1)}%</span>` : '—');
  const usd = (v) => (fin(v) ? '$' + (Math.abs(v) >= 1e9 ? num(v / 1e9, 2) + 'B' : Math.abs(v) >= 1e6 ? num(v / 1e6, 1) + 'M' : Math.abs(v) >= 1e3 ? num(v / 1e3, 0) + 'K' : num(v)) : '—');
  const cell = (c) => esc(String(c || '').replace(/\|/g, ' · '));
  const get = async (hub, rel) => { const r = await fetch(hub + 'data/research/people/' + rel, { cache: 'no-cache' }); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); };
  const rows = (d) => (d.rows || []).map((r) => { const o = {}; (d.fields || []).forEach((k, i) => { o[k] = r[i]; }); return o; });

  function css() {
    if (document.getElementById('pv-css')) return;
    const s = document.createElement('style'); s.id = 'pv-css';
    s.textContent = `.pv h3{margin:20px 0 6px;font-size:16px}.pv p.sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45}
.pv table{width:100%;border-collapse:collapse;font-size:13px}.pv th,.pv td{padding:6px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:left;vertical-align:top}
.pv th{color:var(--muted,#777);font-weight:500;font-size:12px}.pv td.n{text-align:right;font-variant-numeric:tabular-nums}.pv .wrap{overflow-x:auto}`;
    document.head.appendChild(s);
  }

  async function render(el, opt) {
    css();
    const t = String(opt.ticker || '').toUpperCase().replace(/\./g, '-'), hub = opt.hub || 'disclosures/';
    el.innerHTML = '<div class="pv"><p class="sub">Reading the data…</p></div>';
    const box = el.firstChild;
    const [ic, pt, mg] = await Promise.all([get(hub, 'insider_context.json').catch(() => null), get(hub, 'pt_hits.json').catch(() => null), get(hub, 'managers.json').catch(() => null)]);
    if (opt.here && !opt.here()) return;
    let out = '';
    const mine = ((ic && ic.recent) || []).filter((x) => String(x.ticker || '').toUpperCase().replace(/\./g, '-') === t);
    out += `<h3>Recent insider trades, with the history of similar ones</h3><p class="sub">${esc((ic && ic.note) || 'Open-market Form 4 trades scored against SPY over the 63 trading days after disclosure.')}</p>`;
    out += mine.length ? `<div class="wrap"><table><thead><tr><th>Date</th><th>Insider</th><th>Role</th><th>Side</th><th class="n">Value</th><th>Similar trades, 3 months after</th><th>95% interval</th><th class="n">n</th></tr></thead><tbody>${
      mine.map((x) => { const e = x.expected; return `<tr><td>${esc(x.date)}</td><td>${esc(x.insider)}</td><td>${esc(x.role)}</td><td>${esc(x.side)}</td><td class="n">${usd(x.value)}</td><td>${x.plan ? '10b5-1 plan: not scored' : e ? `${sp(e.mean)} <span class="sub">(${cell(x.cell)})</span>` : '—'}</td><td>${e ? `${sp(e.lo)} to ${sp(e.hi)}` : '—'}</td><td class="n">${e ? num(e.n) : '—'}</td></tr>`; }).join('')}</tbody></table></div>`
      : '<p class="sub">No open-market insider trade in the latest Form 4 batch for this company.</p>';
    const hold = ((mg && rows(mg)) || []);
    if (pt) {
      const r = rows(pt).find((x) => String(x.ticker || '').toUpperCase().replace(/\./g, '-') === t);
      out += `<h3>Analysts' price targets</h3><p class="sub">${esc(pt.note || '')}</p>`;
      out += r ? `<p>${num(r.targets)} monthly targets tracked since ${esc(pt.tracking_since || '—')}: ${num(r.resolved)} with their 12 months over, ${num(r.hits)} reached (${fin(r.hit_rate) ? num(r.hit_rate * 100, 0) + '%' : '—'}); ${num(r.pending)} still open, ${num(r.touched_so_far)} touched so far${fin(r.median_error_12m) ? `; price against the target 12 months on: ${sp(r.median_error_12m)} (median)` : ''}.</p>`
        : '<p class="sub">No consensus snapshots for this stock yet.</p>';
    }
    if (hold.length) out += `<h3>Tracked 13F managers</h3><p class="sub">The largest managers' pages (People &amp; index) show whether they hold ${esc(t)} and what copying their 13Fs returned.</p><p><a href="${esc(hub)}#people/managers">Open People &amp; index →</a></p>`;
    box.innerHTML = out;
  }
  window.PeopleView = { render };
})();
