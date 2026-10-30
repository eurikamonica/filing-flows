/* Odds for one company (shared by the hub's Odds tab and the company pages, through views.json): the chance its price
   falls or rises 10% within 4 weeks and 20% within 13, that it beats SPY over 13 and 52 weeks, that it joins the S&P
   500 within a year, that it cuts its dividend within a year, and Merton's 1-year default probability — each next to
   the typical stock's odds and the model's walk-forward record. Data: data/market/history/odds.json and odds-stocks.json
   (app/odds.py, rotation-history).
   window.OddsView.render(el, {ticker, hub}) — hub: the path to the hub ('disclosures/' on the Sankey site, '' inside). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const tk = (t) => String(t || '').trim().toUpperCase().replace(/\./g, '-');
  const pc = (v, d) => (fin(v) ? (v < 0.001 ? '&lt;0.1%' : (v * 100).toFixed(d == null ? (v < 0.1 ? 1 : 0) : d) + '%') : '—');
  const cache = {};
  function get(hub, name) {
    const url = hub + 'data/market/history/' + name;
    if (!cache[url]) cache[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json(); }).catch((e) => { delete cache[url]; throw e; });
    return cache[url];
  }
  function css() {
    if (typeof document === 'undefined' || document.getElementById('odv-css')) return;
    const s = document.createElement('style');
    s.id = 'odv-css';
    s.textContent = `.odv{display:grid;gap:12px}.odv-card{border:1px solid var(--line,#dedcd5);border-radius:10px;background:var(--surface,#fff);padding:12px 14px}
.odv-card h3,.odv-card h4{margin:0 0 6px}.odv-row{display:grid;grid-template-columns:minmax(150px,1.3fr) 64px minmax(90px,2fr) minmax(110px,1fr);gap:8px;align-items:center;padding:5px 0;border-bottom:1px solid var(--line,#eee)}
.odv-row:last-child{border-bottom:0}.odv-p{font-weight:700;font-variant-numeric:tabular-nums;text-align:right}.odv-bar{position:relative;height:10px;background:var(--bg,#f3f2ee);border-radius:5px}
.odv-bar i{position:absolute;left:0;top:0;bottom:0;border-radius:5px;background:var(--accent,#17734a)}.odv-bar b{position:absolute;top:-3px;bottom:-3px;border-left:2px solid var(--ink,#222)}
.odv-note{color:var(--muted,#6b6a66);font-size:.8rem;margin:4px 0 0}.odv-rec{color:var(--muted,#6b6a66);font-size:.78rem}
@media (max-width:640px){.odv-row{grid-template-columns:1fr 56px;}.odv-row .odv-bar,.odv-row .odv-rec{grid-column:1/-1}}`;
    document.head.appendChild(s);
  }
  const LINES = [
    ['dn10_4', 'Falls 10% within 4 weeks'], ['up10_4', 'Rises 10% within 4 weeks'], ['dn20_13', 'Falls 20% within 13 weeks'], ['up20_13', 'Rises 20% within 13 weeks'],
    ['beat13', 'Beats SPY over 13 weeks'], ['beat52', 'Beats SPY over 52 weeks'], ['sp500_12m', 'Added to the S&P 500 within a year'],
    ['divcut_12m', 'Cuts or skips its dividend within a year'], ['merton_1y', 'Defaults within a year (Merton)'],
  ];
  function rec(c) {
    if (!c) return 'no record yet';
    const sk = fin(c.skill) ? (c.skill > 0.005 ? `${(c.skill * 100).toFixed(0)}% better than the base rate` : c.skill < -0.005 ? `${(-c.skill * 100).toFixed(0)}% worse than the base rate` : 'no better than the base rate') : '';
    return `record: AUC ${fin(c.auc) ? c.auc.toFixed(2) : '—'} · ${sk}`;
  }
  function row(label, p, base, c, note) {
    const mx = Math.max(p || 0, base || 0) > 0.5 ? 1 : Math.max(p || 0, base || 0) > 0.2 ? 0.6 : Math.max(p || 0, base || 0) > 0.05 ? 0.25 : 0.06;
    const w = (v) => Math.min(100, (v / mx) * 100).toFixed(1);
    return `<div class="odv-row"><span>${esc(label)}${note ? `<br><span class="odv-rec">${esc(note)}</span>` : ''}</span><span class="odv-p">${pc(p)}</span>
<span class="odv-bar" title="this stock ${pc(p)} · typical ${pc(base)}"><i style="width:${fin(p) ? w(p) : 0}%"></i>${fin(base) ? `<b style="left:${w(base)}%"></b>` : ''}</span><span class="odv-rec">${fin(base) ? 'typical ' + pc(base) + ' · ' : ''}${esc(rec(c))}</span></div>`;
  }
  function html(t, d, s, hub) {
    const F = s.fields, v = s.rows[t];
    const at = (k) => v[F.indexOf(k)];
    const M = d.models || {};
    let out = `<div class="odv"><div class="odv-card"><h3>Odds · ${esc(t)}</h3><p class="odv-note">Week ending ${esc(s.asof)}. Each line: this stock's probability, the bar's black mark the typical stock's (the base rate), and how well the model has done in years it had not seen (AUC: 0.5 is a coin flip, 1 perfect; skill: how much it beats always saying the base rate).</p></div>`;
    out += `<div class="odv-card"><h4>Price moves (weekly closes)</h4>${['dn10_4', 'up10_4', 'dn20_13', 'up20_13'].map((k) => row(LINES.find((x) => x[0] === k)[1], at(k), M[k] && M[k].card && M[k].card.base, M[k] && M[k].card)).join('')}
<p class="odv-note">From its own volatility (${pc(at('vol'), 0)} a year) as a random walk's chance of reaching the level, recalibrated on past years.</p></div>`;
    const bt = ['beat13', 'beat52'].filter((k) => fin(at(k)));
    if (bt.length) out += `<div class="odv-card"><h4>Against the S&P 500</h4>${bt.map((k) => row(LINES.find((x) => x[0] === k)[1], at(k), M[k] && M[k].card && M[k].card.base, M[k] && M[k].card)).join('')}<p class="odv-note">Momentum against SPY, the distance from the 52-week high and volatility have not told winners from losers in the years tested — these odds stay near the base rate on purpose.</p></div>`;
    const ev = [];
    if (fin(at('sp500_12m'))) ev.push(row(LINES[6][1], at('sp500_12m'), M.sp500_12m && M.sp500_12m.card && M.sp500_12m.card.base, M.sp500_12m && M.sp500_12m.card, 'not in the index now; from its market value and rank, earnings and trading'));
    if (fin(at('divcut_12m'))) ev.push(row(LINES[7][1], at('divcut_12m'), M.divcut_12m && M.divcut_12m.card && M.divcut_12m.card.base, M.divcut_12m && M.divcut_12m.card, 'from its yield, payout ratio, earnings and price'));
    if (fin(at('merton_1y'))) ev.push(row(LINES[8][1], at('merton_1y'), null, null, 'from Debt & rates\' distance to default; risk-neutral, not checked against defaults (the companies on file are survivors)'));
    if (ev.length) out += `<div class="odv-card"><h4>Events</h4>${ev.join('')}</div>`;
    out += `<p class="odv-note">History and models, not investment advice. <a href="${esc(hub)}#odds/${esc(t)}">The market's odds, the leaders and every model's track record →</a></p></div>`;
    return out;
  }
  async function render(el, opt) {
    css();
    const hub = (opt && opt.hub) || '', t = tk(opt && opt.ticker);
    if (!t) { el.innerHTML = '<p class="muted">No ticker.</p>'; return; }
    el.innerHTML = '<p class="muted">Reading the odds…</p>';
    let d, s, err;
    try { [d, s] = await Promise.all([get(hub, 'odds.json'), get(hub, 'odds-stocks.json')]); } catch (e) { err = e; }
    if ((opt && opt.here && !opt.here()) || !el.isConnected) return;
    if (err || !s || !s.rows[t]) {
      el.innerHTML = `<div class="odv"><div class="odv-card"><h3>Odds · ${esc(t)}</h3><p class="muted">${err ? 'The odds could not load (' + esc(err.message) + ').' : 'No odds for ' + esc(t) + ': they cover the stocks of the universe ($5 and up, $5M a week of trading, a year of closes) and the ETFs.'}</p></div></div>`;
      return;
    }
    el.innerHTML = html(t, d, s, hub);
  }
  const api = { render, _html: html };
  if (typeof window !== 'undefined') window.OddsView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
