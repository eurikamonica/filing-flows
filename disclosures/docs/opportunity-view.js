/* Opportunity — one stock's or ETF's odds (shared by the Disclosure Hub's Opportunity tab, its ETF page and the
   "Opportunity" view of each company page on the Sankey site, listed in views.json): for 1 week, 1 month and 3 months,
   the chance the price is higher, that a buy makes money after trading costs, that a short makes money after costs and
   the borrow fee, the likely range, the edge over the same name with no signal, the flag and the signals behind it —
   with the model's walk-forward record beside it.
   Data: data/market/history/opportunity-stocks/<A>.json (rotation-history) and data/etf/opportunity-etfs/<A>.json
   (etf-history), built by app/opportunity.py.
   window.OpportunityView.render(el, {ticker, hub, kind}) — hub: the path to the hub ('disclosures/' on the Sankey site,
   '' inside it); kind: 'stocks' | 'etfs' (default: stocks, then ETFs). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && Number.isFinite(+v);
  const P = (v, d = 0) => (fin(v) ? (100 * v).toFixed(d) + '%' : '—');
  const S = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(d) + '%' : '—');
  const pts = (v) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(100 * v).toFixed(1) + ' pts' : '—');
  const tk = (t) => String(t || '').trim().toUpperCase().replace(/\./g, '-');
  const shard = (t) => { const c = (t || '_')[0]; return /[A-Z0-9]/.test(c) ? c : '_'; };
  const H_NAME = { '1w': '1 week', '1m': '1 month', '3m': '3 months' };
  const PATHS = { stocks: 'data/market/history/opportunity-stocks/', etfs: 'data/etf/opportunity-etfs/' };
  const cache = {};
  let styled = false;
  function css() {
    if (styled || typeof document === 'undefined') return;
    styled = true;
    const s = document.createElement('style');
    s.textContent = `.opv{display:grid;gap:12px}.opv .opv-card{border:1px solid var(--line,#d0d5dd);border-radius:8px;padding:12px 14px;min-width:0;overflow:hidden}
.opv h3{margin:0 0 6px;font-size:1rem}.opv h4{margin:10px 0 4px;font-size:.9rem}.opv p{margin:4px 0}.opv .muted{color:var(--muted,#667085)}
.opv .opv-top{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px}.opv .opv-flag{display:inline-block;border-radius:999px;padding:3px 10px;font-weight:600;font-size:.86rem;border:1px solid var(--line,#d0d5dd)}
.opv .opv-flag.buy{background:color-mix(in srgb,#17734a 14%,transparent);color:#17734a;border-color:#17734a}.opv .opv-flag.short{background:color-mix(in srgb,#b42318 12%,transparent);color:#b42318;border-color:#b42318}
.opv .opv-score{font-size:1.5rem;font-weight:650}.opv .opv-score small{font-size:.8rem;font-weight:400;color:var(--muted,#667085)}
.opv table{border-collapse:collapse;width:100%;min-width:0!important;font-size:.86rem}.opv th{position:static;white-space:normal;font-weight:600}.opv td,.opv th{padding:4px 6px;border-bottom:1px solid var(--line,#e4e7ec);text-align:right;vertical-align:top}
.opv td:first-child,.opv th:first-child{text-align:left}.opv .opv-wrap{overflow-x:auto}.opv .up{color:#17734a}.opv .down{color:#b42318}
.opv .opv-bar{display:inline-block;position:relative;width:110px;height:8px;background:var(--line,#e4e7ec);border-radius:4px;vertical-align:middle;margin-right:6px}
.opv .opv-bar i{position:absolute;top:0;bottom:0;border-radius:4px}.opv .opv-bar b{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--muted,#98a2b3)}
.opv .opv-note{font-size:.82rem;color:var(--muted,#667085);line-height:1.45}`;
    document.head.appendChild(s);
  }
  function load(hub, kind, t) {
    const url = hub + PATHS[kind] + shard(t) + '.json';
    if (!cache[url]) cache[url] = fetch(url, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw Error('HTTP ' + r.status); return r.json(); })
      .catch((e) => { delete cache[url]; throw e; });
    return cache[url];
  }
  async function find(hub, t, kind) {
    const kinds = kind ? [kind] : ['stocks', 'etfs'];
    let err = null;
    for (const k of kinds) {
      try { const d = await load(hub, k, t); if (d.rows && d.rows[t]) return { d, r: d.rows[t], kind: k }; } catch (e) { err = e; }
    }
    return { err };
  }
  const flagText = (side, h) => (side === 'buy' ? `Buy flag · ${H_NAME[h] || h}` : side === 'short' ? `Short flag · ${H_NAME[h] || h}` : 'No clear opportunity');
  function bar(v, scale) {
    const w = Math.min(50, (50 * Math.abs(v)) / (scale || 1));
    return `<span class="opv-bar"><b></b><i style="${v >= 0 ? `left:50%;width:${w}%;background:#17734a` : `right:50%;width:${w}%;background:#b42318`}"></i></span>`;
  }
  function html(t, d, r, kind, hub) {
    const F = d.fields_h || [], ix = (k) => F.indexOf(k);
    const hs = Object.keys(d.horizons || H_NAME);
    const cell = (hk, k) => ((r.h || {})[hk] || [])[ix(k)];
    const cards = d.cards || {};
    const on = (hk, side) => !!((((cards[hk] || {}).flags || {})[side] || {}).on);
    let out = `<div class="opv"><div class="opv-card"><h3>Opportunity · ${esc(r.n || t)} <span class="muted">${esc(t)} · ${esc(r.s || '')}</span></h3>
<div class="opv-top"><span class="opv-flag ${esc(r.side)}">${esc(flagText(r.side, r.best_h))}</span>
<span class="opv-score">${fin(r.score) ? Math.round(r.score) : '—'}<small> / 100 score${fin(r.score) ? '' : ' (no horizon where flags have worked)'}</small></span>
<span class="muted">Week ending ${esc(d.asof || '')} · ${kind === 'etfs' ? 'ETF model' : 'stock model'}</span></div>
<p class="opv-note">Score: where this name's best edge ranks among every ${kind === 'etfs' ? 'ETF' : 'stock'} this week (100 = the strongest). The edge is how much the signals raise the chance a trade makes money, against the same name with no signal (its own volatility, costs and size). A flag needs a top-fifth edge, even odds or better that the trade makes money, and a horizon where such flags have made money out of sample.${r.htb ? ' <b>Under $5 or under $5M traded a week: likely hard to borrow, so it is never flagged as a short</b> (the short odds assume a 0.5% a year fee).' : ''}</p></div>`;
    out += `<div class="opv-card"><h4>The odds</h4><div class="opv-wrap"><table><thead><tr><th>Horizon</th><th>Higher</th><th>A buy makes money</th><th>A short makes money</th><th>Likely range (10–90%)</th><th>Middle</th><th>Round-trip cost</th><th>Edge</th><th>Flag</th></tr></thead><tbody>`;
    for (const hk of hs) {
      if (!(r.h || {})[hk]) continue;
      const pu = cell(hk, 'p_up'), side = cell(hk, 'side');
      const gate = [on(hk, 'buy') ? 'buy' : '', on(hk, 'short') ? 'short' : ''].filter(Boolean).join(' & ');
      out += `<tr><td>${esc(H_NAME[hk] || hk)}</td><td class="${pu >= 0.5 ? 'up' : 'down'}"><b>${P(pu)}</b></td><td>${P(cell(hk, 'p_buy'))}</td><td>${P(cell(hk, 'p_short'))}</td>
<td>${S(cell(hk, 'r_p10'))} to ${S(cell(hk, 'r_p90'))}</td><td>${S(cell(hk, 'r_p50'))}</td><td>${P(cell(hk, 'cost'), 2)}</td><td>${pts(cell(hk, 'edge'))}</td>
<td>${side && side !== 'none' ? `<span class="opv-flag ${esc(side)}">${esc(side)}</span>` : `<span class="muted" title="Flags at this horizon: ${esc(gate || 'none — they did not work out of sample')}">—</span>`}</td></tr>`;
    }
    out += `</tbody></table></div><p class="opv-note">A buy makes money when the price ends above the purchase after the round-trip cost (set by the dollar volume traded: 0.1% for the most liquid names, up to 2% for the thinnest); a short when it ends below, after the cost and the borrow fee. The range and the middle are from the model's own past errors.</p></div>`;
    const lab = d.labels || {};
    const dr = r.drivers || [];
    const sc = Math.max(0.05, ...dr.map((x) => Math.abs(x[1])));
    out += `<div class="opv-card"><h4>What moves it (${esc(H_NAME[r.best_h] || r.best_h || '')})</h4><table><tbody>${dr.map(([k, v]) => `<tr><td>${esc(lab[k] || k)}</td><td>${bar(v, sc)}<span class="${v >= 0 ? 'up' : 'down'}">${v >= 0 ? 'pushes up' : 'pushes down'}</span></td></tr>`).join('')}</tbody></table>
<p class="opv-note">Each signal's weight × where this name stands on it against every other name this week (in units of its own volatility).</p></div>`;
    const rec = hs.map((hk) => {
      const c = cards[hk] || {}, fb = (c.flags || {}).buy || {}, fs = (c.flags || {}).short || {};
      const one = (f, name) => (f.on ? `${name} flags on: they made money ${P(f.hit)} of the time (${fin(f.base_hit) ? P(f.base_hit) + ' expected for the same names with no signal, ' : ''}all names ${P(f.all_hit)}), median ${S(f.net_median)} vs ${S(f.all_net_median)}` : `${name} flags off: they did not make money often enough out of sample`);
      return `<li><b>${esc(H_NAME[hk] || hk)}</b>: higher-or-not called with AUC ${fin((c.up || {}).auc) ? (c.up.auc).toFixed(3) : '—'} (0.5 = a coin), Brier skill ${S((c.up || {}).skill)} over the base rate · ${one(fb, 'buy')} · ${one(fs, 'short')}</li>`;
    }).join('');
    const yrs = ((cards[hs[0]] || {}).years || []).join('–');
    out += `<div class="opv-card"><h4>How well this has worked</h4><p class="opv-note">Every year ${esc(yrs)} predicted only from the years before it (walk-forward), on ${kind === 'etfs' ? 'the ETFs on file' : "today's companies (delisted names are missing, which flatters the record a little)"}.</p><ul class="opv-note">${rec}</ul>
<p class="opv-note">For single names, the week-to-week direction is close to a coin flip; these odds lean, they do not predict. History and models, not investment advice. <a href="${esc(hub)}#opportunity/${esc(kind === 'etfs' ? 'etfs~' : '')}${esc(t)}">Every name, the model card and the track record →</a></p></div></div>`;
    return out;
  }
  async function render(el, opt) {
    css();
    const hub = (opt && opt.hub) || '', t = tk(opt && opt.ticker);
    if (!t) { el.innerHTML = '<p class="muted">No ticker.</p>'; return; }
    el.innerHTML = '<p class="muted">Reading the odds…</p>';
    const f = await find(hub, t, opt && opt.kind);
    if ((opt && opt.here && !opt.here()) || !el.isConnected) return;
    if (!f.r) {
      el.innerHTML = `<div class="opv"><div class="opv-card"><h3>Opportunity · ${esc(t)}</h3><p class="muted">${f.err && !/404/.test(f.err.message) ? 'The odds could not load (' + esc(f.err.message) + ').' : 'No odds for ' + esc(t) + ' yet: they cover the names with at least 60 weeks of weekly closes on file.'}</p></div></div>`;
      return;
    }
    el.innerHTML = html(t, f.d, f.r, f.kind, hub);
  }
  const api = { render, _html: html, _shard: shard };
  if (typeof window !== 'undefined') window.OpportunityView = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
