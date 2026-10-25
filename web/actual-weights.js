/* Independent actual ETF / index-tracker holdings videos.
 * Unlike the existing Sector Weights, these NEVER compute company market-cap
 * shares. Reports are tied to their original as-of dates. Missing snapshots
 * are not backfilled with today's portfolio.
 */
(function (root) {
  'use strict';
  const TRACKERS = {
    dji: ['Dow Jones Industrial Average', 'DIA', 'price-weighted'],
    sp500: ['S&P 500', 'SPY', 'float-adjusted market-cap-weighted'],
    ndx: ['Nasdaq-100', 'QQQ', 'modified market-cap-weighted'],
    sp400: ['S&P MidCap 400', 'IJH', 'float-adjusted market-cap-weighted'],
    sp600: ['S&P SmallCap 600', 'IJR', 'float-adjusted market-cap-weighted'],
    r1000: ['Russell 1000', 'IWB', 'float-adjusted market-cap-weighted'],
    r2000: ['Russell 2000', 'IWM', 'float-adjusted market-cap-weighted'],
    r3000: ['Russell 3000', 'IWV', 'float-adjusted market-cap-weighted']
  };
  const SEC = {
    technology: 'Technology', communication: 'Communication', 'consumer-disc': 'Consumer discretionary',
    'consumer-staples': 'Consumer staples', health: 'Health care', financials: 'Financials',
    'real-estate': 'Real estate', energy: 'Energy', materials: 'Materials', industrials: 'Industrials',
    utilities: 'Utilities', other: 'Other / unclassified'
  };
  const GICS = {
    'information technology': 'technology', technology: 'technology',
    'communication services': 'communication', 'consumer discretionary': 'consumer-disc',
    'consumer staples': 'consumer-staples', 'health care': 'health',
    healthcare: 'health', financials: 'financials', 'real estate': 'real-estate',
    energy: 'energy', materials: 'materials', industrials: 'industrials',
    utilities: 'utilities'
  };
  const valid = (v) => v != null && Number.isFinite(Number(v));
  const symbol = (s) => String(s || '').trim().toUpperCase().replace(/\./g, '-');
  const percent = (v) => valid(v) ? (100 * Number(v)).toFixed(2) + '%' : '—';
  const day = (d) => Date.parse(d + 'T00:00:00Z');
  const isDate = (d) => /^\d{4}-\d{2}-\d{2}$/.test(d || '') && Number.isFinite(day(d));
  const toSector = (v) => GICS[String(v || '').toLowerCase().trim()] || (SEC[v] ? v : 'other');
  const sortedPositions = (raw) => {
    const seen = new Map();
    (raw || []).forEach((p) => {
      const ticker = symbol(p && p[0]), w = p && Number(p[1]);
      if (!/^[A-Z][A-Z0-9-]{0,9}$/.test(ticker) || !Number.isFinite(w) || w <= 0) return;
      seen.set(ticker, (seen.get(ticker) || 0) + w);
    });
    return [...seen.entries()].sort((a, b) => b[1] - a[1]);
  };
  function snapshotFromDetail(doc) {
    const hold = doc && doc.holdings || {}, date = String(hold.date || '').slice(0, 10);
    if (!isDate(date)) return null;
    const positions = sortedPositions(doc.weights || []);
    if (positions.length < 2) return null;
    return { date, positions, date_basis: hold.date_basis || 'reported', source: hold.source || (hold.acc ? 'SEC N-PORT' : 'fund holdings disclosure'),
      accession: hold.acc || null, sectors: hold.sector_map || {}, equity_weight_covered: positions.reduce((s, p) => s + p[1], 0) };
  }
  function normalizeSnapshot(s) {
    if (!s || !isDate(s.date)) return null;
    const positions = sortedPositions(s.positions || []);
    if (positions.length < 2) return null;
    return { date: s.date, positions, date_basis: s.date_basis || 'reported', source: String(s.source || 'fund holdings disclosure'),
      accession: s.accession || null, sectors: s.sectors || {},
      equity_weight_covered: positions.reduce((n, p) => n + p[1], 0) };
  }
  function snapshots(history, current, from, to) {
    const by = new Map();
    (history && history.snapshots || []).forEach((s) => { const x = normalizeSnapshot(s); if (x) by.set(x.date, x); });
    // Publish latest if the ETF is not among the funds whose histories are tracked.
    const latest = snapshotFromDetail(current);
    if (latest && !by.has(latest.date)) by.set(latest.date, latest);
    return [...by.values()].filter((s) => (!from || s.date >= from) && (!to || s.date <= to))
      .sort((a, b) => a.date.localeCompare(b.date));
  }
  async function build(st, out, api) {
    const indexed = st.aw !== 'etf', ref = TRACKERS[st.at] || TRACKERS.dji;
    const ticker = indexed ? ref[1] : symbol(st.ah || 'SPY');
    if (!/^[A-Z][A-Z0-9-]{0,9}$/.test(ticker)) throw new Error('Enter a valid fund ticker');
    const [history, current] = await Promise.all([
      api.json(api.hub + 'etf/weights/' + ticker + '.json'),
      api.json(api.hub + 'etf/e/' + ticker + '.json')
    ]);
    const all = snapshots(history, current, st.from, st.to);
    if (!all.length) throw new Error(ticker + ': no source-dated constituent weights in this date range; choose a newer date or fund');
    const meta = await api.rankMeta().catch(() => null);
    const co = new Map(((meta && meta.cos) || []).map((r) => [symbol(r[0]), { name: r[1], sec: r[2] }]));
    const sources = [...new Set(all.map((x) => x.source))].join('; ');
    const from = all[0].date, to = all[all.length - 1].date;
    const who = indexed ? ref[0] + ' (via ' + ticker + ')' : ((current && current.name) || (history && history.name) || ticker);
    const label = indexed ? 'Index-tracker holdings proxy' : 'Actual fund disclosures';
    out.grid = all.map((s) => day(s.date));
    out.fmt = percent; out.unit = '%'; out.actual = { fund: ticker, index: indexed ? st.at : null, reports: all.length };
    out.notes.add('Observed or reported source dates: ' + from + (from === to ? '' : ' to ' + to) + '. No synthetic 2016–2026 history.');
    if (all.some(s => s.date_basis === 'observed')) out.notes.add('Some sponsor workbook dates are retrieval OBSERVATIONS because the source did not expose a parseable holdings as-of date; they are NOT claimed to be report effective dates.');
    out.notes.add(label + '. Sources: ' + sources + '. Report weights use fund NAV, not constituent market capitalization.');
    if (indexed) {
      out.notes.add('Index weights are proxied by ' + ticker + ' portfolio holdings, not licensed official index weight files; tracking differences and cash may exist.');
      if (st.at === 'dji') out.notes.add('Dow 30 is PRICE-weighted. DIA replicates its price-weighted basket; never apply market-cap weights to Dow.');
      else out.notes.add(ref[0] + ' index methodology: ' + ref[2] + '. Tracker positions are a disclosed proxy.');
    }
    if (all.length > 1) out.notes.add('Frames interpolate VISUALLY between actual snapshots; no holdings are asserted for interim dates.');
    const secFor = (s, ticker) => {
      const reported = (s.sectors || {})[ticker];
      return reported ? toSector(reported) : toSector((co.get(ticker) || {}).sec);
    };
    if (st.style === 'stack' && all.length >= 2) {
      const grouped = all.map((s) => {
        const totals = {};
        s.positions.forEach(([k, w]) => {
          const sec = secFor(s, k);
          totals[sec] = (totals[sec] || 0) + w;
        });
        const equity = Object.values(totals).reduce((a, b) => a + b, 0);
        if (equity > 1.025) throw new Error(ticker + ': equity weight is over 102.5% of NAV; use holdings bars for leveraged exposures');
        totals.other = (totals.other || 0) + Math.max(0, 1 - equity);
        return totals;
      });
      const secs = Object.keys(SEC).filter((k) => grouped.some((g) => (g[k] || 0) > 0));
      out.kind = 'sectors'; out.stack = { share: true, total: all.map(() => 1) };
      out.series = secs.map((s) => ({ key: s, label: SEC[s], name: SEC[s], sec: s, v: grouped.map((g) => g[s] || 0) }))
        .sort((a, b) => b.v[b.v.length - 1] - a.v[a.v.length - 1]);
      out.metric = 'Reported fund NAV sector weight';
      out.notes.add('Sectors use source-provided sector tags where available, otherwise Filing Flows classifications; Other includes cash, unmatched securities and coverage gaps, not necessarily a real GICS sector.');
    } else {
      if (st.style === 'stack') out.notes.add('Only one real portfolio snapshot is available: showing a dated static holdings bar card instead of inventing a changing area chart.');
      const sectorBars = st.style === 'stack';
      const table = all.map((s) => {
        const m = new Map();
        s.positions.forEach(([ticker, weight]) => {
          const k = sectorBars ? secFor(s, ticker) : ticker;
          m.set(k, (m.get(k) || 0) + weight);
        });
        return m;
      });
      const choice = new Set();
      table.forEach((m) => [...m].sort((a, b) => b[1] - a[1])
        .slice(0, Math.max(3, Math.min(25, +st.an || 12)) + 5).forEach(([k]) => choice.add(k)));
      out.kind = 'rank'; out.rankN = Math.max(3, Math.min(20, +st.an || 12)); out.order = 'desc';
      out.series = [...choice].map((k) => ({ key: k, label: sectorBars ? (SEC[k] || k) : k,
        name: sectorBars ? (SEC[k] || k) : ((co.get(k) || {}).name || k),
        sec: sectorBars ? k : secFor(all[all.length - 1], k),
        v: table.map((m) => m.has(k) ? m.get(k) : null) }));
      out.metric = sectorBars ? 'Reported NAV sector weights' : 'Reported holding weights';
      if (all.some((s) => s.equity_weight_covered < .985)) out.notes.add('Not all fund assets are in the disclosed equity list. Bars retain original NAV weights; missing holdings are NOT rescaled to 100%.');
    }
    const range = from === to ? from : from + ' → ' + to;
    const tag = indexed && st.at === 'dji' ? 'DIA tracking basket · price-weighted index proxy' : label + ' · ' + ticker;
    out.title = (indexed ? ref[0] : ticker) + ': actual ' + (st.style === 'stack' ? 'sector' : 'holding') + ' weights';
    out.sub = range + ' · ' + tag + ' · ' + all.length + ' dated snapshot' + (all.length === 1 ? '' : 's') + (all.some(s => s.date_basis === 'observed') ? ' · observed date(s) included' : '');
    out.foot = from === to ? 'Single reported holdings snapshot — not a history' : 'Reported holdings dates only; transitions illustrative';
    return out;
  }
  root.FFActual = { TRACKERS, build, snapshots, normalizeSnapshot, snapshotFromDetail, sortedPositions, toSector };
  if (typeof module !== 'undefined') module.exports = root.FFActual;
})(typeof globalThis !== 'undefined' ? globalThis : this);
