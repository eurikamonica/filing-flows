/* Company overview card: one compact panel at the top of a company's Earnings page that gathers what the site and the
   Disclosure Hub know — the latest quarter, a valuation snapshot, analysts and Polymarket, the smart-money score,
   insider trades, the 13F flow, short interest, the debt cushion, the 52-week position and the next report.
   Every tile is optional: a file the hub has not published (or a company it does not cover) simply leaves its tile out.
   Sources: data/c/<cik>.json (passed in), disclosures/data/consensus/c/<cik>.json, holders/<TICKER>.json,
   smart/t/<TICKER>.json, debt/c/<cik>.json, market/extremes.json (only when the consensus file has no prices). */
(function (root) {
  'use strict';
  const U = root.FFUx;
  const { esc, t, fin, num, money, usd, pct, spct, day, fileT } = U;

  // the latest close and the 52-week range from the consensus file's daily prices ([[date, close]])
  function range52(prices) {
    const P = (prices || []).filter((p) => p && fin(p[1]));
    if (P.length < 20) return null;
    const last = P[P.length - 1], since = new Date(Date.parse(last[0]) - 365 * 864e5).toISOString().slice(0, 10);
    const yr = P.filter((p) => p[0] >= since);
    const hi = Math.max(...yr.map((p) => +p[1])), lo = Math.min(...yr.map((p) => +p[1]));
    return { date: last[0], close: +last[1], hi, lo, from_hi: last[1] / hi - 1, from_lo: last[1] / lo - 1 };
  }
  // trailing four quarters of revenue when the site has four consecutive quarters
  function ttm(c, key) {
    const Q = (c.quarters || []).filter((q) => q.headline && fin(q.headline[key]));
    if (Q.length < 4) return null;
    const ends = Q.slice(0, 4).map((q) => Date.parse(q.end));
    if (ends[0] - ends[3] > 300 * 864e5) return null;                 // a gap: not four consecutive quarters
    return Q.slice(0, 4).reduce((a, q) => a + q.headline[key], 0);
  }

  function facts(ctx, F) {
    const { c, q, ticker, cik } = ctx;
    const h = (q && q.headline) || {}, tiles = [];
    const tile = (label, value, sub, href, tone) => tiles.push({ label, value, sub, href, tone });
    // latest quarter
    if (fin(h.revenue)) tile(`${U.dec(q.label)} revenue`, money(h.revenue), [fin(h.yoy) ? `${h.yoy >= 0 ? '+' : '−'}${num(Math.abs(h.yoy), 0)}% Y/Y` : '', fin(h.om) ? `op. margin ${num(h.om, 1)}%` : ''].filter(Boolean).join(' · '), null, fin(h.yoy) ? (h.yoy >= 0 ? 'good' : 'bad') : '');
    if (fin(h.ni)) tile('Net earnings', money(h.ni), fin(h.ocf) ? `operating cash flow ${money(h.ocf)}` : '', `#c-${cik}-cash`, h.ni >= 0 ? 'good' : 'bad');
    // price, valuation
    const cons = F.cons, a = (cons && cons.analysts) || {};
    const r52 = range52(cons && cons.prices) || F.ext;
    const price = fin(a.price) ? +a.price : r52 ? r52.close : null;
    const sh = U.shares(c);
    if (fin(price)) {
      const mcap = sh ? price * sh.v : null, rev4 = ttm(c, 'revenue'), ni4 = ttm(c, 'ni');
      const bits = [];
      if (fin(mcap)) bits.push(`market cap ≈ ${money(mcap)}`);
      if (fin(mcap) && fin(rev4) && rev4 > 0) bits.push(`P/S ${num(mcap / rev4, 1)}`);
      if (fin(mcap) && fin(ni4) && ni4 > 0) bits.push(`P/E ${num(mcap / ni4, 1)}`);
      tile('Price', usd(price), bits.join(' · ') || (a.as_of ? `as of ${day(a.as_of)}` : ''), `#c-${cik}-value`);
    }
    if (r52) tile('52-week range', `${spct(r52.from_hi, 0)} from high`, `${usd(r52.lo, 2)} – ${usd(r52.hi, 2)}${r52.date ? ` · ${day(r52.date)}` : ''}`, null, r52.from_hi > -0.05 ? 'good' : r52.from_lo < 0.05 ? 'bad' : '');
    // analysts and Polymarket
    const T = a.targets || {};
    if (fin(T.mean)) tile("Analysts' target", usd(T.mean), [fin(price) && price ? `${spct(T.mean / price - 1)} from price` : '', fin(T.n) ? `${num(T.n)} analysts` : ''].filter(Boolean).join(' · '), `#c-${cik}-consensus`);
    const nx = a.next_earnings || {}, q0 = (a.periods || []).find((p) => p.period === '0q') || {};
    const beat = ((cons && cons.markets) || []).find((m) => m.kind === 'beat' && !m.closed && fin(m.p));
    if (nx.date) tile('Next report', day(nx.date), fin((q0.eps || {}).avg) ? `EPS est. ${usd(q0.eps.avg)}${nx.estimate ? ' · date estimated' : ''}` : (nx.estimate ? 'date estimated' : ''), `#c-${cik}-consensus`);
    if (beat) {
      const seen = U.store.get('pm:' + fileT(ticker), null), moved = seen && seen.p != null && Math.abs(beat.p - seen.p) >= 0.005 ? beat.p - seen.p : null;
      tile('Polymarket: beats EPS?', pct(beat.p), [fin(beat.eps_strike) ? `line ${usd(beat.eps_strike)}` : '', moved != null ? `${moved > 0 ? '+' : '−'}${num(Math.abs(moved) * 100, 0)} pts since your last visit` : ''].filter(Boolean).join(' · '), `#c-${cik}-consensus`);
      U.store.set('pm:' + fileT(ticker), { p: beat.p, at: new Date().toISOString().slice(0, 10) });
    }
    // smart money
    const S = F.smart && F.smart.now;
    if (S && fin(S.S)) tile('Smart-money score', `${S.S > 0 ? '+' : S.S < 0 ? '−' : ''}${num(Math.abs(S.S), 0)}`, `of ±100 · ${num(S.n)} disclosed traders, weighted by record`, `disclosures/#smart/${encodeURIComponent(fileT(ticker))}`, S.S >= 20 ? 'good' : S.S <= -20 ? 'bad' : '');
    // insiders, last 90 days
    const H = F.holders || {};
    const since90 = new Date(Date.now() - 90 * 864e5).toISOString().slice(0, 10);
    const ins = (H.insiders || []).filter((x) => (x.date || '') >= since90);
    if (ins.length) {
      const buys = ins.filter((x) => x.code === 'P'), sells = ins.filter((x) => x.code === 'S');
      const bv = buys.reduce((s, x) => s + (x.value || 0), 0), sv = sells.reduce((s, x) => s + (x.value || 0), 0);
      tile('Insiders, 90 days', buys.length ? `${buys.length} buy${buys.length > 1 ? 's' : ''} · ${money(bv)}` : `${sells.length} sale${sells.length > 1 ? 's' : ''}`,
        [sells.length && buys.length ? `${sells.length} sales · ${money(sv)}` : sells.length ? money(sv) + ' sold' : '', ins[0] ? `latest ${day(ins[0].date)}` : ''].filter(Boolean).join(' · '), 'disclosures/#insiders', buys.length ? 'good' : '');
    }
    // 13F flow (the quarter's buyers / sellers among the managers the hub reads)
    const fl = H.flows;
    if (fl && (fin(fl.buyers) || fin(fl.sellers))) tile('13F managers', `${num(fl.buyers)} buyers · ${num(fl.sellers)} sellers`, [fin(fl.usd_net) ? `net ${fl.usd_net >= 0 ? '+' : '−'}${money(Math.abs(fl.usd_net))}` : '', fl.label || ''].filter(Boolean).join(' · '), 'disclosures/#flows', fin(fl.usd_net) ? (fl.usd_net >= 0 ? 'good' : 'bad') : '');
    // short interest (FINRA, twice a month)
    const sh2 = (H.short || []).filter((x) => x && fin(x[1]));
    if (sh2.length) {
      const last = sh2[sh2.length - 1], prev = sh2.length > 1 ? sh2[sh2.length - 2] : null;
      tile('Short interest', `${num(last[1] / 1e6, 1)}M shares`, [prev && prev[1] ? `${spct(last[1] / prev[1] - 1)} since ${day(prev[0])}` : '', `as of ${day(last[0])}`].filter(Boolean).join(' · '), 'disclosures/#shorts');
    }
    // debt cushion
    const A = (F.debt && F.debt.analysis) || {};
    if (fin(A.cushion_score) || fin(A.net_leverage)) tile('Debt cushion', fin(A.cushion_score) ? `${num(A.cushion_score)}/100` : `${num(A.net_leverage, 1)}× net debt/EBITDA`,
      [fin(A.cushion_score) && fin(A.net_leverage) ? `net debt/EBITDA ${num(A.net_leverage, 1)}×` : '', fin(A.interest_coverage) ? `interest cover ${num(A.interest_coverage, 1)}×` : ''].filter(Boolean).join(' · '), `#c-${cik}-debt`,
      fin(A.cushion_score) ? (A.cushion_score >= 60 ? 'good' : A.cushion_score < 35 ? 'bad' : '') : '');
    return tiles;
  }

  async function load(ctx) {
    const { cik, ticker } = ctx, T = fileT(ticker);
    const [cons, holders, smart, debt] = await Promise.all([
      cik ? U.hub(`consensus/c/${+cik}.json`) : null,
      T ? U.hub(`holders/${encodeURIComponent(String(ticker).toUpperCase())}.json`) : null,
      T ? U.hub(`smart/t/${T.replace(/[^A-Za-z0-9-]/g, '_')}.json`) : null,
      cik ? U.hub(`debt/c/${+cik}.json`) : null]);
    let ext = null;
    if (T && !range52(cons && cons.prices)) {                       // no daily prices in the consensus file: the hub's highs / lows
      const X = await U.hub('market/extremes.json');
      if (X && X.fields) {
        const row = (X.rows || []).find((r) => String(r[0]).toUpperCase().replace(/\./g, '-') === T);
        if (row) {
          const r = Object.fromEntries(X.fields.map((f, i) => [f, row[i]]));
          if (fin(r.close) && fin(r.hi52) && fin(r.lo52)) ext = { date: X.asof, close: r.close, hi: r.hi52, lo: r.lo52, from_hi: r.from_hi, from_lo: r.from_lo };
        }
      }
    }
    return { cons, holders, smart, debt, ext };
  }

  async function mount(el, ctx) {
    if (!el) return;
    el.innerHTML = '';
    const F = await load(ctx);
    if (ctx.here && !ctx.here()) return;
    const tiles = facts(ctx, F);
    if (tiles.length < 2) return;                                     // nothing beyond the chart itself: no card
    el.className = 'fx-ov';
    el.innerHTML = `<div class="fx-ov-head"><h2>Overview</h2><span class="muted">From this site and the Disclosure Hub · each tile links to its source</span>
      <button type="button" class="btn fx-ov-csv" title="Every line item of every quarter on this page, as a spreadsheet">Figures as CSV ↓</button></div>
      <div class="fx-ov-grid">${tiles.map((x) => `<${x.href ? `a href="${esc(x.href)}"` : 'div'} class="fx-tile${x.tone ? ' ' + x.tone : ''}"><small>${t(x.label)}</small><b>${esc(x.value)}</b>${x.sub ? `<span>${esc(x.sub)}</span>` : ''}</${x.href ? 'a' : 'div'}>`).join('')}</div>`;
    el.querySelector('.fx-ov-csv').addEventListener('click', () => U.csv(figuresRows(ctx.c), `${fileT(ctx.ticker) || ctx.cik}-figures`));
    const sx = ctx.ticker ? await U.site('search.json') : null;
    if (sx && (sx.feeds || []).includes(fileT(ctx.ticker)) && document.head && !document.querySelector('link[data-fx-feed]')) {   // the company's own feed
      const l = document.createElement('link');
      l.rel = 'alternate'; l.type = 'application/atom+xml'; l.dataset.fxFeed = '1';
      l.title = `${U.dec(ctx.c.profile.name)} — filings and disclosures`; l.href = `feeds/c/${encodeURIComponent(fileT(ctx.ticker))}.xml`;
      document.head.appendChild(l);
    }
  }
  // every node of every quarter on the site: one row per quarter and line
  function figuresRows(c) {
    const out = [];
    for (const q of c.quarters || []) {
      for (const n of q.nodes || []) out.push({ quarter: U.dec(q.label), end: q.end, form: q.form, filed: q.filed, line: U.dec(n.name), value: n.v, prior_quarter: n.q, year_ago: n.y });
    }
    return out;
  }
  root.FFOverview = { mount, facts, range52, ttm, figuresRows, load };
  if (typeof module !== 'undefined') module.exports = root.FFOverview;
})(typeof globalThis !== 'undefined' ? globalThis : this);
