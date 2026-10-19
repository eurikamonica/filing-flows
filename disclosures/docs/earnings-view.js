/* Earnings preview — one company's next report (and the results of the last ten days), shared by the Disclosure Hub
   (Earnings season tab) and the main site's company page ("Earnings preview" view, disclosures/views.json).
   window.EarningsPreviewView.render(el, {ticker, hub}) loads data/research/earnings/c/<TICKER>.json
   (app/earnings_season.py, branch research-earnings); renderDoc(el, doc) draws a document already loaded.
   Everything shown is from the published data: analysts' consensus, Polymarket's beat market, the options-implied move
   against the stock's usual move, our beat probability (frozen three days before the report) and our own estimates,
   the history of beats and moves, distributions, options and short-interest indicators, the non-GAAP gap. CSS prefix ep-. */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fin = (v) => v != null && v !== '' && Number.isFinite(+v);
  const num = (v, d = 0) => (fin(v) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
  const usd = (v, d = 2) => (fin(v) ? (v < 0 ? '−$' : '$') + num(Math.abs(v), d) : '—');
  const big = (v) => { if (!fin(v)) return '—'; const a = Math.abs(v), s = v < 0 ? '−' : ''; return s + (a >= 1e12 ? '$' + num(a / 1e12, 2) + 'T' : a >= 1e9 ? '$' + num(a / 1e9, a >= 1e10 ? 1 : 2) + 'B' : a >= 1e6 ? '$' + num(a / 1e6, 0) + 'M' : '$' + num(a, 0)); };
  const pct = (v, d = 0) => (fin(v) ? num(100 * v, d) + '%' : '—');
  const spct = (v, d = 1) => (fin(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(100 * v), d) + '%' : '—');
  const day = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || '')); return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }) : '—'; };
  const fname = (t) => String(t || '').toUpperCase().replace(/\./g, '-').replace(/[^A-Za-z0-9-]/g, '_');
  const C = { good: 'var(--mk-profit, #2e8b57)', bad: 'var(--mk-cost, #c0392b)', pm: '#8a4fd6', ours: '#2a78d6', an: '#d9822b', opt: '#16a085', mute: 'var(--muted, #888)' };

  function css() {
    if (document.getElementById('ep-css')) return;
    const s = document.createElement('style'); s.id = 'ep-css';
    s.textContent = `.ep h3{margin:22px 0 6px;font-size:16px}.ep .ep-sub{color:var(--muted,#777);font-size:13px;margin:0 0 10px;line-height:1.45;max-width:78ch}
.ep-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;margin:8px 0 6px}
.ep-card{border:1px solid var(--line,#ddd);border-radius:10px;padding:10px 12px;border-top:3px solid var(--k,var(--line,#ddd))}
.ep-card b{display:block;font-size:20px;font-variant-numeric:tabular-nums;margin-top:2px}.ep-card span{font-size:12px;color:var(--muted,#777)}
.ep table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}.ep th,.ep td{padding:5px 8px;border-bottom:1px solid var(--line,#e5e5e5);text-align:right}
.ep th:first-child,.ep td:first-child{text-align:left}.ep .pos{color:${C.good}}.ep .neg{color:${C.bad}}.ep .ep-tag{display:inline-block;font-size:11px;border:1px solid var(--line,#ccc);border-radius:20px;padding:1px 8px;margin-left:6px;color:var(--muted,#777)}
.ep svg{max-width:100%;height:auto}.ep .ep-legend span{display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:12px}.ep .ep-legend i{width:12px;height:3px;display:inline-block}`;
    document.head.appendChild(s);
  }
  const card = (k, label, value, sub) => `<div class="ep-card" style="--k:${k}"><span>${esc(label)}</span><b>${value}</b><span>${sub || ''}</span></div>`;
  const sgn = (v) => (fin(v) ? `<span class="${v > 0 ? 'pos' : v < 0 ? 'neg' : ''}">${spct(v)}</span>` : '—');

  function survivalChart(d) {
    const ks = d.strikes || [], pa = d.polymarket_above || [], oa = d.options_above || [];
    if (ks.length < 2) return '';
    const W = 560, H = 220, L = 46, R = 12, T = 12, B = 34;
    const lo = Math.min(...ks), hi = Math.max(...ks);
    const x = (k) => L + (k - lo) / Math.max(hi - lo, 1e-9) * (W - L - R), y = (p) => T + (1 - p) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Chance of finishing above each strike: Polymarket vs options">`;
    for (const p of [0, 0.25, 0.5, 0.75, 1]) s += `<line x1="${L}" x2="${W - R}" y1="${y(p)}" y2="${y(p)}" stroke="var(--line,#e5e5e5)"/><text x="${L - 6}" y="${y(p) + 4}" font-size="11" text-anchor="end" fill="currentColor">${p * 100}%</text>`;
    ks.forEach((k, i) => { if (i % Math.ceil(ks.length / 7) === 0) s += `<text x="${x(k)}" y="${H - 12}" font-size="11" text-anchor="middle" fill="currentColor">${esc(num(k, k < 10 ? 2 : 0))}</text>`; });
    const path = (vals) => vals.map((p, i) => (fin(p) ? `${i && fin(vals[i - 1]) ? 'L' : 'M'}${x(ks[i]).toFixed(1)},${y(p).toFixed(1)}` : '')).join(' ');
    if (oa.some(fin)) s += `<path d="${path(oa)}" fill="none" stroke="${C.opt}" stroke-width="2.2"/>`;
    s += `<path d="${path(pa)}" fill="none" stroke="${C.pm}" stroke-width="2.2" stroke-dasharray="5 4"/>`;
    pa.forEach((p, i) => { if (fin(p)) s += `<circle cx="${x(ks[i])}" cy="${y(p)}" r="3.5" fill="${C.pm}"><title>Polymarket: ${pct(p)} above ${num(ks[i], 2)}</title></circle>`; });
    return s + '</svg>';
  }

  function renderDoc(el, d) {
    css();
    if (!d) { el.innerHTML = '<p class="muted">No report on file for this company in the next three weeks or the last ten days.</p>'; return; }
    const c = d.consensus || {}, m = d.model || {}, pm = d.polymarket, im = d.implied, ours = d.ours || {}, o = d.options, sq = d.squeeze, ng = d.nongaap, rt = d.readthrough || {};
    let h = `<div class="ep">`;
    const when = d.days_to > 0 ? `in ${d.days_to} day${d.days_to === 1 ? '' : 's'}` : d.days_to === 0 ? 'today' : `${-d.days_to} day${d.days_to === -1 ? '' : 's'} ago`;
    h += `<h3>${esc(d.ticker)} reports ${esc(day(d.report_date))} <span class="ep-tag">${esc(when)}</span>${d.date_estimated ? '<span class="ep-tag">date estimated</span>' : ''}</h3>
      <p class="ep-sub">Quarter ending ${esc(d.quarter)} (${esc(d.season || '')}). Consensus from Yahoo Finance analysts; Polymarket's "beat quarterly earnings" market; the options-implied move from the CBOE term structure; our probability from a logistic model fitted on earlier reports, frozen ${3} days before the report. Not investment advice.</p>`;
    h += `<div class="ep-cards">`;
    if (fin(c.eps)) h += card(C.an, 'Consensus EPS', usd(c.eps), `${fin(c.eps_low) ? `${usd(c.eps_low)}–${usd(c.eps_high)} · ` : ''}${fin(c.n) ? num(c.n) + ' analysts' : ''}${fin(c.year_ago_eps) ? ` · year ago ${usd(c.year_ago_eps)}` : ''}`);
    if (fin(c.rev)) h += card(C.an, 'Consensus revenue', big(c.rev), fin(c.year_ago_rev) ? `year ago ${big(c.year_ago_rev)} (${spct(c.rev / c.year_ago_rev - 1)})` : '');
    if (pm) h += card(C.pm, 'Polymarket: beats', pct(pm.p), `EPS line ${usd(pm.strike)}${pm.basis ? ' ' + esc(pm.basis) : ''}${pm.url ? ` · <a href="${esc(pm.url)}" target="_blank" rel="noopener">market ↗</a>` : ''}`);
    if (fin(m.p)) h += card(C.ours, 'Our model: beats', pct(m.p), m.frozen ? `frozen ${esc(String(m.frozen_at || '').slice(0, 10))}${fin(m.frozen_p) ? ' at ' + pct(m.frozen_p) : ''}` : 'live (frozen 3 days before)');
    if (im && fin(im.move)) h += card(C.opt, 'Options-implied move', '±' + pct(im.move, 1), `${fin(d.avg_move) ? `usual move ±${pct(d.avg_move, 1)} (last ${d.moves_n})` : 'no past moves on file'} · expiry ${esc(im.expiry)}`);
    else if (fin(d.avg_move)) h += card(C.opt, 'Usual move after reports', '±' + pct(d.avg_move, 1), `average of the last ${d.moves_n} (close before → close after)`);
    if (fin(ours.eps)) h += card(C.ours, 'Our EPS estimate', usd(ours.eps), fin(c.eps) ? `vs consensus ${usd(c.eps)} (${spct(ours.eps / c.eps - 1)})` : '');
    if (fin(c.dispersion) || fin(c.revision_30d)) h += card(C.mute, 'Dispersion · 30-day revision', `${pct(c.dispersion)} · ${spct(c.revision_30d)}`, fin(c.revision_breadth) ? `revision breadth ${spct(c.revision_breadth, 0)} (up − down ÷ analysts)` : '');
    if (fin(d.beat_rate)) h += card(C.good, 'Beat rate', pct(d.beat_rate), `last ${(d.history || []).length} reports on file`);
    h += `</div>`;
    for (const r of (d.results || []).slice().reverse()) {
      h += `<h3>Result: ${esc(day(r.reported))}</h3><p class="ep-sub">EPS ${usd(r.act)} vs ${usd(r.est)} expected (${sgn(r.surprise)}) — <b class="${r.beat ? 'pos' : 'neg'}">${r.beat ? 'beat' : 'missed'}</b>.
        ${fin(r.polymarket_p) ? `Polymarket had ${pct(r.polymarket_p)} on a beat${(r.polymarket_p >= 0.5) === !!r.beat ? ' (right)' : ' (wrong)'}.` : ''}
        ${fin(r.model_p) ? `Our frozen model had ${pct(r.model_p)}${(r.model_p >= 0.5) === !!r.beat ? ' (right)' : ' (wrong)'}.` : ''}
        ${fin(r.move) ? `The stock moved ${sgn(r.move)} over the two sessions${fin(r.implied) ? ` against ±${pct(r.implied, 1)} implied` : ''}${fin(r.excess) ? ` (${sgn(r.excess)} vs SPY)` : ''}.` : ''}
        ${fin(r.pead) ? `Predicted drift over the next 60 sessions: ${sgn(r.pead)} vs SPY${r.pead_range ? ` (80% range ${spct(r.pead_range[0])} to ${spct(r.pead_range[1])})` : ''}.` : ''}</p>`;
    }
    if ((d.history || []).length) {
      h += `<h3>Recent reports</h3><table><thead><tr><th>Quarter</th><th>Reported</th><th>Estimate</th><th>Actual</th><th>Surprise</th><th>Move (2 sessions)</th><th>vs SPY</th></tr></thead><tbody>`;
      for (const x of d.history.slice().reverse()) h += `<tr><td>${esc(x.quarter)}</td><td>${esc(x.reported)}</td><td>${usd(x.est)}</td><td>${usd(x.act)}</td><td>${sgn(x.surprise)}</td><td>${sgn(x.move)}</td><td>${sgn(x.excess)}</td></tr>`;
      h += `</tbody></table>`;
    }
    if (fin(ours.eps) || fin(ours.rev)) h += `<h3>Our estimates</h3><p class="ep-sub">${esc(ours.method || '')}: EPS ${usd(ours.eps)}${fin(ours.eps_growth) ? ` (net income growth ${spct(ours.eps_growth)})` : ''}, revenue ${big(ours.rev)}${fin(ours.rev_growth) ? ` (revenue growth ${spct(ours.rev_growth)})` : ''}. Frozen beside the analysts' numbers before the report and scored after it — a simple baseline, so the Street usually wins; the scorecard says how often.</p>`;
    if (fin(rt.pred)) h += `<h3>Peer read-through</h3><p class="ep-sub">${num(rt.n_peers)} ${esc(d.sector)} companies already reported this season with an average EPS surprise of ${spct(rt.peer_mean)}; historically a company's surprise moved ${num(rt.beta, 2)}× its sector's, so the read-through points to ${sgn(rt.pred)}.</p>`;
    for (const x of d.distributions || []) {
      if (x.kind === 'price') h += `<h3>Price on ${esc(x.end)}: Polymarket vs options</h3><p class="ep-sub">${esc(x.title)}. Polymarket median ${usd(x.polymarket && x.polymarket.median)}, options (risk-neutral, expiry ${esc(x.expiry)}) median ${usd(x.options && x.options.median)}, 80% range ${usd(x.options && x.options.q10)}–${usd(x.options && x.options.q90)}.</p>
        <div class="ep-legend"><span><i style="background:${C.pm}"></i>Polymarket</span><span><i style="background:${C.opt}"></i>Options</span></div>${survivalChart(x)}`;
      else h += `<h3>EPS ladder on Polymarket</h3><p class="ep-sub">${esc(x.title)}: median ${usd(x.polymarket && x.polymarket.median)}, 80% range ${usd(x.polymarket && x.polymarket.q10)}–${usd(x.polymarket && x.polymarket.q90)} against a consensus of ${usd(x.consensus)}.</p>${survivalChart(x)}`;
    }
    if (o || sq || ng) {
      h += `<h3>Indicators</h3><table><tbody>`;
      if (o) h += `<tr><td>Implied vs realised volatility (30 days)</td><td>${pct(o.iv30, 1)} vs ${pct(o.rv30, 1)} — VRP ${sgn(o.vrp)}</td></tr><tr><td>Skew (25-delta) · put/call (open interest · volume)</td><td>${num(o.skew25, 3)} · ${num(o.pc_oi, 2)} · ${num(o.pc_vol, 2)}</td></tr>`;
      if (sq) h += `<tr><td>Short interest · days to cover · 1-month return</td><td>${pct(sq.short_pct, 1)} of shares · ${num(sq.dtc, 1)} days · ${sgn(sq.momentum)} (squeeze score ${num(sq.score, 2)})</td></tr>`;
      if (ng) h += `<tr><td>Street EPS vs GAAP (latest quarter)</td><td>gap ${pct(ng.gap_pct)} of Street EPS (before: ${pct(ng.gap_prev_mean)})${ng.flag ? ' — widening' : ''}</td></tr>`;
      h += `</tbody></table>`;
    }
    h += `<p class="ep-sub">Data: app/earnings_season.py (branch research-earnings), built ${esc(String(d.generated_at || '').slice(0, 16).replace('T', ' '))} UTC.</p></div>`;
    el.innerHTML = h;
  }

  async function render(el, opt) {
    opt = opt || {};
    const base = (opt.hub || '') + 'data/research/earnings/c/' + fname(opt.ticker) + '.json';
    el.innerHTML = '<p class="muted">Loading the earnings preview…</p>';
    try {
      const r = await fetch(base, { cache: 'no-cache' });
      if (r.status === 404) return renderDoc(el, null);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      renderDoc(el, await r.json());
    } catch (err) {
      el.innerHTML = `<p class="muted">The earnings preview could not load (${esc(err.message)}).</p>`;
    }
  }

  window.EarningsPreviewView = { render, renderDoc, survivalChart, fname };
})();
