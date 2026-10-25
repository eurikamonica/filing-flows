/* SEC 13F and Congressional disclosure weight videos.
 * 13F company weights are weights of the full reported 13F portfolio, not
 * normalized to the selected top-40 companies.
 * Officials' public PTRs describe transactions, NOT complete current holdings;
 * their midpoint-based transaction mix is always labelled an estimate.
 */
(function (root) {
  'use strict';
  const SECTORS = {
    technology: 'Technology', communication: 'Communication', 'consumer-disc': 'Consumer discretionary',
    'consumer-staples': 'Consumer staples', health: 'Health care', financials: 'Financials',
    'real-estate': 'Real estate', energy: 'Energy', materials: 'Materials', industrials: 'Industrials',
    utilities: 'Utilities', other: 'Other / unmapped', unshown: 'Not shown in top holdings'
  };
  const valid = n => n !== null && n !== undefined && Number.isFinite(Number(n));
  const pct = n => valid(n) ? (100 * Number(n)).toFixed(2) + '%' : '—';
  const symbol = s => String(s || '').trim().toUpperCase().replace(/\./g, '-');
  const rowsOf = doc => (doc && doc.rows || []).map(row =>
    Array.isArray(row) ? Object.fromEntries((doc.fields || []).map((k, i) => [k, row[i]])) : row);
  const stamp = s => /^\d{4}-\d{2}-\d{2}$/.test(String(s || '').slice(0,10)) ?
    String(s).slice(0,10) : null;
  const day = d => Date.parse(d + 'T00:00:00Z');
  const sectorMap = meta => new Map((((meta || {}).cos) || []).map(x => [symbol(x[0]), x[2] || 'other']));
  function popularManagers(index) {
    const rows = rowsOf(index).filter(r => r.cik && r.name);
    const hot = /berkshire|scion|pershing|appaloosa|soros|duquesne|bridgewater|tiger global|coatue|third point|citadel|millennium/i;
    return rows.sort((a, b) => Number(hot.test(b.name)) - Number(hot.test(a.name)) || Number(b.aum || 0) - Number(a.aum || 0));
  }
  const popularOfficials = index => rowsOf(index).filter(r => r.slug && r.name)
    .sort((a, b) => Number(b.trades || 0) - Number(a.trades || 0));
  function pick(list, key, wanted) {
    const q = String(wanted || '').trim().toLowerCase();
    if (!list.length) return null;
    if (!q) return list[0];
    return list.find(x => String(x[key]).toLowerCase() === q ||
      String(x.name).toLowerCase() === q || String(x.name).toLowerCase().includes(q)) || null;
  }
  function managerPositions(page, meta) {
    const sectors = sectorMap(meta), seen = new Map();
    const aum = valid(page.aum) && +page.aum > 0 ? +page.aum : null;
    (page.holdings || []).forEach(h => {
      if (!Array.isArray(h)) return;
      const ticker = symbol(h[0]), amount = valid(h[3]) && h[3] >= 0 ? +h[3] : null;
      const w = valid(h[2]) ? +h[2] : (aum && amount !== null ? amount / aum : null);
      if (!/^[A-Z][A-Z0-9-]{0,9}$/.test(ticker) || !valid(w) || w <= 0) return;
      const old = seen.get(ticker);
      seen.set(ticker, { ticker, name: String(h[1] || ticker), sector: sectors.get(ticker) || 'other',
        weight: (old ? old.weight : 0) + w, value_usd: (old && old.value_usd || 0) + (amount || 0),
        status: h[4] || null });
    });
    const positions = [...seen.values()].sort((a,b) => b.weight-a.weight);
    const covered = positions.reduce((s,p) => s+p.weight,0);
    // Partial top-holdings lists are never reweighted to 100%.
    if (!positions.length || covered > 1.025) throw Error('13F weight coverage is unavailable or exceeds 102.5%; verify source data.');
    return { positions, covered, unshown: Math.max(0,1-covered), denom: 'full reported 13F portfolio' };
  }
  function officialTransactions(page, meta) {
    const sectors = sectorMap(meta), seen = new Map();
    let ignored = 0;
    (page.recent || []).forEach(t => {
      if (!Array.isArray(t)) return;
      const ticker = symbol(t[1]), lo = t[3], hi = t[4];
      // Open-ended ranges and absent amounts cannot produce defensible midpoints.
      if (!/^[A-Z][A-Z0-9-]{0,9}$/.test(ticker) || !valid(lo) || !valid(hi) ||
          +lo < 0 || +hi < +lo || +hi <= 0) { ignored++; return; }
      const midpoint = (+lo + +hi)/2, prev = seen.get(ticker);
      seen.set(ticker, { ticker, name: ticker, sector: sectors.get(ticker) || 'other',
        value_usd: (prev ? prev.value_usd : 0) + midpoint,
        count: (prev ? prev.count : 0) + 1, weight: 0 });
    });
    const positions = [...seen.values()];
    const total = positions.reduce((n,p) => n+p.value_usd,0);
    if (!total) throw Error('No finite disclosed trade ranges are available for this official; cannot infer holdings.');
    positions.forEach(p => { p.weight = p.value_usd/total; });
    return { positions: positions.sort((a,b)=>b.weight-a.weight),
      covered: 1, unshown: 0, ignored, denom: 'finite-range disclosed trades only (NOT a portfolio)' };
  }
  function groupSectors(positions, unshown) {
    const by = new Map();
    positions.forEach(p => by.set(p.sector, (by.get(p.sector) || 0) + p.weight));
    if (unshown > .000001) by.set('unshown', unshown);
    return [...by.entries()].map(([k,w]) => ({ ticker:k, name:SECTORS[k]||k,
      sector:k==='unshown'?'other':k, weight:w })).sort((a,b)=>b.weight-a.weight);
  }
  function setupVideo(out, st, source, page, result, date, note) {
    const isSector = st.hv === 'sector';
    const positions = isSector ? groupSectors(result.positions, source === '13f' ? result.unshown : 0) : result.positions;
    const maxN = Math.max(3,Math.min(20,+st.an||12));
    const shown = positions.slice(0, Math.max(maxN,20));
    out.kind = 'rank'; out.grid = [day(date)]; out.rankN = maxN;
    out.order = 'desc'; out.fmt = pct; out.unit = '%';
    out.actual = {kind:source, date, filer:page.name, observed:1};
    out.series = shown.map(p => ({ key:p.ticker, label:isSector ? p.name : p.ticker,
      name:p.name, sec:p.sector, v:[p.weight] }));
    out.metric = source === '13f' ? 'Actual 13F ' + (isSector?'sector':'company') + ' weights' :
      'Estimated disclosed ' + (isSector?'sector':'company') + ' transaction mix';
    out.title = page.name + ': ' + out.metric;
    out.sub = date + (source==='13f' ? ' quarter end · SEC 13F · weights of total reported portfolio' :
      ' · Congressional disclosure · midpoint of finite transaction ranges');
    out.foot = source==='13f' ? 'Top reported 13F holdings only · source filing period' :
      'Disclosed transaction mix, NOT current portfolio holdings';
    out.notes.add(note);
    if (source === '13f') {
      out.notes.add('Top-position weights retain the FULL filed portfolio as denominator. Coverage ' + pct(result.covered) +
        '; ' + pct(result.unshown) + ' is not included in shown holdings. Sector view shows an explicit unshown remainder.');
      out.notes.add('13F filings are lagged and may omit shorts, non-13F assets and some derivatives; no share counts exist in this summary feed.');
    } else {
      out.notes.add('Congressional PTR records disclose transaction amount RANGES and cannot establish actual holdings or share counts. No actual portfolio weight is claimed.');
      if(result.ignored)out.notes.add(result.ignored + ' disclosed events excluded because ticker or finite dollar range was missing.');
    }
    out.notes.add('One authentic disclosure snapshot only. No historical transitions are fabricated.');
    return out;
  }
  async function build(st, out, api) {
    const source = st.hsrc === 'officials' ? 'officials' : '13f';
    const base = api.hub + 'research/people/';
    const index = await api.json(base + (source==='13f'?'managers':'officials') + '.json');
    if (!index || !Array.isArray(index.rows)) throw Error('Research People disclosures are not published; cannot make real 13F/Officials video.');
    const choices = source==='13f' ? popularManagers(index) : popularOfficials(index);
    const filer = pick(choices, source==='13f'?'cik':'slug', st.hid);
    if (!filer) throw Error('No disclosed ' + (source==='13f'?'13F manager':'official') + ' matches "' + st.hid + '"');
    const page = await api.json(base + (source==='13f'?'m/'+filer.cik:'o/'+filer.slug) + '.json');
    if (!page) throw Error('Disclosed record for ' + filer.name + ' is not published yet.');
    const meta = await api.rankMeta().catch(() => null);
    if (source==='13f') {
      const date = stamp(page.period);
      if (!date) throw Error('13F report period is missing or invalid; no fabricated date is allowed.');
      return setupVideo(out,st,source,page,managerPositions(page,meta),date,'SEC 13F summary · filed ' + (page.filed || 'date unavailable') + '; values reflect quarter-end holdings, NOT current market prices.');
    }
    const dates = (page.recent || []).map(r => stamp(r[0])).filter(Boolean).sort();
    const date = dates[dates.length-1];
    if (!date) throw Error('No dated Congressional PTR transaction records for this official.');
    return setupVideo(out,st,source,page,officialTransactions(page,meta),date,
      'Recent disclosed transactions only, through ' + date + '. Midpoints of bounded dollar ranges are used; buy and sell activity is not portfolio ownership.');
  }
  root.FFHoldingsVideo = {build, rowsOf, popularManagers, popularOfficials, managerPositions,
    officialTransactions, groupSectors};
  if (typeof module !== 'undefined') module.exports = root.FFHoldingsVideo;
})(typeof globalThis !== 'undefined' ? globalThis : this);
