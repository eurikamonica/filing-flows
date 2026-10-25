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
    if (positions.length < 1) return null;
    return { date, positions, date_basis: hold.date_basis || 'reported', source: hold.source || (hold.acc ? 'SEC N-PORT' : 'fund holdings disclosure'),
      accession: hold.acc || null, sectors: hold.sector_map || {}, equity_weight_covered: positions.reduce((s, p) => s + p[1], 0) };
  }
  function normalizeSnapshot(s) {
    if (!s || !isDate(s.date)) return null;
    const positions = sortedPositions(s.positions || []);
    if (positions.length < 1) return null;
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
  async function disclosedSource(st, api) {
    if (st.aw === '13f') {
      const cik = String(st.ac || '1067983').replace(/^0+/, '');
      if (!/^\d{1,10}$/.test(cik)) throw new Error('Enter a valid manager CIK');
      const doc = await api.json(api.hub + 'shards/holdings/' + cik + '.json');
      if (!doc) throw new Error('Manager holdings are not published yet');
      const rows = (doc.snapshots || []).filter(s => s.complete === true && (!st.from || s.period >= st.from) && (!st.to || s.period <= st.to));
      const snaps = await Promise.all(rows.map(async s => {
        const p = s.positions || await api.json(api.hub + s.positions_shard);
        if (!Array.isArray(p) || !(s.total_usd > 0)) throw new Error('Missing positions for ' + s.period);
        // Options and unresolved identifiers stay in the denominator/residual.
        return {date:s.period, source:'SEC 13F', positions:p.filter(r => (!r.put_call || r.put_call === 'NONE') && r.ticker)
          .map(r => [r.ticker, r.value_usd / s.total_usd]), filed:s.filed, sources:s.sources};
      }));
      return {name:doc.label || doc.name || cik, id:cik, snapshots:snaps,
        basis:'Share of reported 13F value', note:'Quarter-end reported long holdings, not current positions or total AUM. Options and unmatched securities remain in Other. Weight changes include price movement, not just trading. Latest amended reports may restate history; this is not a point-in-time backtest.', evidence:rows};
    }
    if (st.aw === 'official') {
      const doc = await api.json(api.hub + 'market/officials-trades.json');
      const person = String(st.ap || '').trim();
      if (!person) throw new Error('Enter the official’s disclosed name');
      const months = new Map();
      const evidence = [];
      for (const t of (doc && doc.trades || [])) {
        if (String(t.person || '').toLowerCase() !== person.toLowerCase() || !isDate(t.date) ||
          (st.from && t.date < st.from) || (st.to && t.date > st.to) || (st.ao && st.ao !== 'all' && t.type !== st.ao)) continue;
        const k = symbol(t.ticker_canon || t.ticker), v = Number(t.amount_min);
        if (!k || !Number.isFinite(v) || v <= 0) continue;
        const d = new Date(Date.UTC(+t.date.slice(0,4), +t.date.slice(5,7), 0)).toISOString().slice(0,10);
        if (!months.has(d)) months.set(d, new Map());
        const m = months.get(d); m.set(k, (m.get(k) || 0) + v); evidence.push(t);
      }
      return {name:person, id:person, snapshots:[...months].map(([date,m]) => {
        const total = [...m.values()].reduce((a,b)=>a+b,0);
        return {date, source:'Official PTR disclosed amount lower bounds', positions:[...m].map(([k,v])=>[k,v/total])};
      }), basis:'Monthly disclosed transaction lower-bound share', evidence,
        note:'NOT actual holdings or net exposure. Monthly composition uses disclosed transaction amount LOWER BOUNDS, not exact dollars; buys and sells are gross, never netted. Only ticker-resolved transactions are included. Months without records are not zero activity. Disclosure can lag the trade date. The published feed is capped at 4,000 recent transactions across all officials, so history and boundary months can be incomplete.'};
    }
    return null;
  }
  async function build(st, out, api) {
    const external = await disclosedSource(st, api);
    const indexed = !external && st.aw !== 'etf', ref = TRACKERS[st.at] || TRACKERS.dji;
    const ticker = indexed ? ref[1] : symbol(st.ah || 'SPY');
    if (!/^[A-Z][A-Z0-9-]{0,9}$/.test(ticker)) throw new Error('Enter a valid fund ticker');
    const [history, current] = external ? [{snapshots:external.snapshots}, null] : await Promise.all([
      api.json(api.hub + 'etf/weights/' + ticker + '.json'),
      api.json(api.hub + 'etf/e/' + ticker + '.json')
    ]);
    const all = snapshots(history, current, external && st.aw === 'official' ? '' : st.from, external && st.aw === 'official' ? '' : st.to);
    if (external) { out.notes.add(external.note); out.evidence = external.evidence; }
    if (!all.length) throw new Error(ticker + ': no source-dated constituent weights in this date range; choose a newer date or fund');
    const meta = await api.rankMeta().catch(() => null);
    const co = new Map(((meta && meta.cos) || []).map((r) => [symbol(r[0]), { name: r[1], sec: r[2] }]));
    const sources = [...new Set(all.map((x) => x.source))].join('; ');
    const from = all[0].date, to = all[all.length - 1].date;
    const label = external ? external.basis : indexed ? 'Index-tracker holdings proxy' : 'Actual fund disclosures';
    out.grid = all.map((s) => day(s.date));
    out.group = (st.style === 'stack' || (st.style === 'changes' && st.ag === 'sector')) ? 'sectors' : 'companies';
    out.fmt = percent; out.unit = '%'; out.actual = { fund: external ? external.id : ticker, source:st.aw, index: indexed ? st.at : null, reports: all.length };
    out.notes.add('Observed or reported source dates: ' + from + (from === to ? '' : ' to ' + to) + '. No synthetic 2016–2026 history.');
    if (all.some(s => s.date_basis === 'observed')) out.notes.add('Some sponsor workbook dates are retrieval OBSERVATIONS because the source did not expose a parseable holdings as-of date; they are NOT claimed to be report effective dates.');
    out.notes.add(label + '. Sources: ' + sources + (external ? '.' : '. Report weights use fund NAV, not constituent market capitalization.'));
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
    const sector = st.style === 'stack' || (st.style === 'changes' && st.ag === 'sector');
    const area = st.style === 'stack' || st.style === 'companies';
    const tables = all.map(s => {
      const m = new Map();
      s.positions.forEach(([k,w]) => {const key = sector ? secFor(s,k) : k; m.set(key,(m.get(key)||0)+w);});
      const sum = [...m.values()].reduce((a,b)=>a+b,0);
      if (area && sum > 1.000001) throw new Error('Exposures exceed 100%; use holdings bars instead of a 100% area chart');
      if (area || sector) m.set('other',(m.get('other')||0)+Math.max(0,1-sum));
      return m;
    });
    const n = Math.max(3, Math.min(20, +st.an || 12));
    let keys = [...new Set(tables.flatMap(m=>[...m.keys()]))];
    // Fixed membership across the entire animation prevents disappearing bands.
    if (area && !sector) {
      keys = keys.filter(k=>k!=='other').sort((a,b)=>Math.max(...tables.map(m=>m.get(b)||0))-Math.max(...tables.map(m=>m.get(a)||0))).slice(0,n);
      tables.forEach(m=>{const rest=[...m].filter(([k])=>!keys.includes(k)).reduce((s,[,v])=>s+v,0); m.set('other',rest);});
      keys.push('other');
    }
    out.series = keys.map(k=>({key:k,label:k==='other'?'Other / unclassified':sector?(SEC[k]||k):k,
      name:sector?(SEC[k]||k):((co.get(k)||{}).name||k), sec:sector?k:secFor(all[all.length-1],k),
      v:tables.map(m=>m.get(k)||0)}));
    out.metric = external ? external.basis : 'Reported NAV ' + (sector?'sector':'company') + ' weight';
    if (area && all.length >= 2) {
      out.kind='sectors'; out.stack={share:true,total:all.map(()=>1)};
      out.series.sort((a,b)=>b.v[b.v.length-1]-a.v[a.v.length-1]);
      out.notes.add('Other preserves the denominator: remaining companies, unmatched securities and unreported assets. Company bands are ticker/security level; share classes are not consolidated. Sector classifications may use current metadata.');
    } else {
      out.kind='rank'; out.rankN=n; out.order='desc';
      if (area) out.notes.add('Only one real portfolio snapshot is available: showing a dated static card, not an invented history.');
    }
    if (st.style === 'changes') {
      if (all.length < 2) throw new Error('Weight changes require at least two disclosed snapshots');
      out.series.forEach(s=>{s.v=s.v.slice(1).map((v,i)=>v-s.v[i]);});
      out.order='abs'; out.grid=out.grid.slice(1); out.fmt=v=>(v>=0?'+':'')+(100*v).toFixed(2)+' pp';
      out.metric='Weight change vs previous disclosed snapshot';
      out.notes.add('Changes are percentage points, not trade size or proof of rebalancing. Use the date range to select the comparison periods.');
    }
    const range = from === to ? from : from + ' → ' + to;
    const tag = external ? external.basis : indexed && st.at === 'dji' ? 'DIA tracking basket · price-weighted index proxy' : label + ' · ' + ticker;
    out.title = (external ? external.name : indexed ? ref[0] : ticker) + ': ' + (st.style === 'changes' ? 'weight changes' : (sector ? 'sector' : 'company') + ' weights') + (st.aw === 'official' ? ' · transaction lower bounds' : '');
    out.sub = range + ' · ' + tag + ' · ' + all.length + ' dated snapshot' + (all.length === 1 ? '' : 's') + (all.some(s => s.date_basis === 'observed') ? ' · observed date(s) included' : '');
    out.foot = st.aw === 'official' ? 'Transaction LOWER-BOUND composition · not actual holdings · limited recent feed' : st.aw === '13f' ? 'Quarter-end 13F reported value · not current holdings or total AUM' : from === to ? 'Single reported holdings snapshot — not a history' : 'Reported holdings dates only; transitions illustrative';
    return out;
  }
  root.FFActual = { TRACKERS, build, snapshots, normalizeSnapshot, snapshotFromDetail, sortedPositions, toSector, disclosedSource };
  if (typeof module !== 'undefined') module.exports = root.FFActual;
})(typeof globalThis !== 'undefined' ? globalThis : this);
