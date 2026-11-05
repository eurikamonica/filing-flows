/* Independent actual ETF / index-tracker holdings videos.
 * Reports are tied to their original as-of dates. Missing snapshots are not backfilled with today's portfolio.
 * An index proxy (QQQ for the Nasdaq-100, SPY for the S&P 500 …) can reach back before the fund's first report (SEC's
 * N-PORT data sets begin Sep 30, 2019) the way the Sector weights video does: the index's members at each quarter-end
 * weighted by their market values (studio.js reconstructIndex) — marked as reconstructed on the video, in its subtitle
 * and notes, never as the fund's holdings. st.recon = '0' keeps the reports alone.
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
    return { date, positions, date_basis: ['reported','observed'].includes(hold.date_basis) ? hold.date_basis : 'unknown', source: hold.source || (hold.acc ? 'SEC N-PORT' : 'fund holdings disclosure'),
      accession: hold.acc || null, sectors: hold.sector_map || {}, equity_weight_covered: positions.reduce((s, p) => s + p[1], 0) };
  }
  // sector key → weight, computed by the ETF build over EVERY long equity line (quarter-end N-PORT snapshots list only the
  // largest names); finite positive weights only
  function sectorWeights(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const out = {};
    Object.entries(raw).forEach(([k, v]) => { const w = Number(v), key = toSector(k); if (Number.isFinite(w) && w > 0) out[key] = (out[key] || 0) + w; });
    return Object.keys(out).length ? out : null;
  }
  function normalizeSnapshot(s) {
    if (!s || !isDate(s.date)) return null;
    const positions = sortedPositions(s.positions || []);
    if (positions.length < 1) return null;
    const sw = sectorWeights(s.sector_weights), cov = Number(s.covered != null ? s.covered : s.partial ? s.equity_weight_covered : NaN);
    const out = { date: s.date, positions, date_basis: ['reported','observed'].includes(s.date_basis) ? s.date_basis : 'unknown', source: String(s.source || 'fund holdings disclosure'),
      accession: s.accession || null, sectors: s.sectors || {},
      equity_weight_covered: Number.isFinite(cov) && cov > 0 ? cov : positions.reduce((n, p) => n + p[1], 0) };
    if (sw) out.sector_weights = sw;
    if (s.partial) out.partial = true;
    return out;
  }
  // the quarterly block of etf/weights/<SYM>.json (app/actual_weights.py quarterly_block): the fund's public N-PORT
  // quarter-end reports as columns — the same largest names every quarter, weights in hundred-thousandths
  function quarterlySnapshots(q) {
    if (!q || !Array.isArray(q.dates) || !Array.isArray(q.names)) return [];
    const per = Math.round(1 / (Number(q.unit) > 0 ? Number(q.unit) : 1e-5));      // 100000: weights in hundred-thousandths
    return q.dates.map((date, i) => {
      const w = (q.w || [])[i] || [], sw = (q.sw || [])[i] || {}, sector_weights = {};
      (q.sectors || []).forEach((k, j) => { const v = (Number(sw[j]) || 0) / per; if (v > 0) sector_weights[k] = v; });
      return normalizeSnapshot({ date, date_basis: 'reported', source: 'SEC N-PORT (quarter-end)', accession: (q.acc || [])[i] || null,
        positions: q.names.map((t, j) => [t, (Number(w[j]) || 0) / per]), sector_weights, partial: true, covered: (q.eq || [])[i] });
    }).filter(Boolean);
  }
  function snapshots(history, current, from, to) {
    const by = new Map();
    quarterlySnapshots(history && history.quarterly).forEach((x) => by.set(x.date, x));
    (history && history.snapshots || []).forEach((s) => {
      const x = normalizeSnapshot(s); if (!x) return;
      const q = by.get(x.date);                           // a full snapshot on a quarter-end: its names, the quarter's sector weights
      if (q && q.partial) {
        if (q.sector_weights) x.sector_weights = q.sector_weights;
        // the same N-PORT report (or its date): the report date is the portfolio's reported as-of date
        if (x.date_basis === 'unknown' && (!x.accession || !q.accession || x.accession === q.accession)) x.date_basis = 'reported';
      }
      by.set(x.date, x);
    });
    // Publish latest if the ETF is not among the funds whose histories are tracked.
    const latest = snapshotFromDetail(current);
    if (latest && !by.has(latest.date)) by.set(latest.date, latest);
    return [...by.values()].filter((s) => (!from || s.date >= from) && (!to || s.date <= to))
      .sort((a, b) => a.date.localeCompare(b.date));
  }
  // the 13F records are too big for the Pages build: the Hub's data/remote.json names where they are read from instead
  // (stage-public.py write_remote; the Hub's own shardFetch does the same); without it they sit beside the other data
  async function shardBase(api) {
    const cfg = await Promise.resolve(api.json(api.hub + 'remote.json')).catch(() => null);
    return cfg && typeof cfg.base === 'string' && /^https:\/\//.test(cfg.base) && (cfg.prefixes || []).some((x) => 'shards/holdings/'.startsWith(x)) ? cfg.base : api.hub;
  }
  async function disclosedSource(st, api) {
    if (st.aw === '13f') {
      const cik = String(st.ac || '1067983').replace(/^0+/, '');
      if (!/^\d{1,10}$/.test(cik)) throw new Error('Enter a valid manager CIK');
      const base = await shardBase(api);
      // a report not yet enriched with tickers is named through the Hub's CUSIP map (market.py → market/cusip-tickers.json)
      const [doc, cmap] = await Promise.all([api.json(base + 'shards/holdings/' + cik + '.json'),
        Promise.resolve(api.json(api.hub + 'market/cusip-tickers.json')).catch(() => null)]);
      if (!doc) throw new Error('Manager holdings are not published yet');
      const tickerOf = (r) => r.ticker || (cmap && r.cusip && cmap[r.cusip]) || '';
      const rows = (doc.snapshots || []).filter(s => s.complete === true && (!st.from || s.period >= st.from) && (!st.to || s.period <= st.to));
      const snaps = await Promise.all(rows.map(async s => {
        const shard = String(s.positions_shard || ''), okPath = /^[A-Za-z0-9_+./-]+\.json$/.test(shard) && !shard.includes('..') && !shard.startsWith('/');
        const p = s.positions || (okPath ? await api.json(base + shard) : null);
        if (!Array.isArray(p) || !(s.total_usd > 0)) throw new Error('Missing positions for ' + s.period);
        // Options and unresolved identifiers stay in the denominator/residual.
        return {date:s.period, date_basis:'reported', source:'SEC 13F', positions:p.filter(r => (!r.put_call || r.put_call === 'NONE') && tickerOf(r))
          .map(r => [tickerOf(r), r.value_usd / s.total_usd]), filed:s.filed, sources:s.sources};
      }));
      if (!snaps.some(x => x.positions.length)) throw new Error((doc.label || doc.name || cik) + ': none of the reported positions could be matched to a ticker');
      return {name:doc.label || doc.name || cik, id:cik, snapshots:snaps,
        basis:'Share of reported 13F value', note:'Quarter-end reported long holdings, not current positions or total AUM. Options and unmatched securities remain in Other. Weight changes include price movement, not just trading. Latest amended reports may restate history; this is not a point-in-time backtest.', evidence:rows};
    }
    if (st.aw === 'official') {
      const person = String(st.ap || '').trim();
      if (!person) throw new Error('Enter the official’s disclosed name');
      // every disclosed trade of the official (market/officials/<slug>.json, app/market.py officials_by_person); the
      // shared feed (officials-trades.json) only when that file is missing: it keeps the newest 4,000 trades of everyone
      const slug = person.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60).replace(/-+$/, '');
      const own = slug ? await Promise.resolve(api.json(api.hub + 'market/officials/' + slug + '.json')).catch(() => null) : null;
      let rows, capped = false;
      if (own && Array.isArray(own.fields) && Array.isArray(own.trades)) {
        rows = own.trades.map((r) => ({ person: own.name, date: r[0], ticker: r[1], type: r[2], amount_min: r[3], amount_max: r[4] }));
      } else {
        const doc = await api.json(api.hub + 'market/officials-trades.json');
        rows = (doc && doc.trades || []).filter((t) => String(t.person || '').toLowerCase() === person.toLowerCase());
        capped = true;
      }
      const months = new Map();
      const evidence = [];
      for (const t of rows) {
        if (!isDate(t.date) || (st.from && t.date < st.from) || (st.to && t.date > st.to) || (st.ao && st.ao !== 'all' && t.type !== st.ao)) continue;
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
        note:'NOT actual holdings or net exposure. Monthly composition uses disclosed transaction amount LOWER BOUNDS, not exact dollars; buys and sells are gross, never netted. Only ticker-resolved transactions are included. Months without records are not zero activity. Disclosure can lag the trade date. '
          + (capped ? 'The published feed is capped at 4,000 recent transactions across all officials, so history and boundary months can be incomplete.'
                    : 'Every disclosed trade of this official on file (US House reports read by machine, Senate electronic reports), from ' + (own.first || '') + ' to ' + (own.last || '') + '.')};
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
    let all = snapshots(history, current, external && st.aw === 'official' ? '' : st.from, external && st.aw === 'official' ? '' : st.to);
    if (external) { out.notes.add(external.note); out.evidence = external.evidence; }
    // an index before its tracking fund's first report: the members and their market values, as the Sector weights video
    let recon = [], R = null;
    const reported0 = all.length ? all[0].date : null;
    // only for a start chosen before the first report: a blank start keeps the reports alone ("all on file")
    if (indexed && st.recon !== '0' && api.reconstruct && isDate(st.from)) {
      const first = reported0 || (isDate(st.to) ? new Date(day(st.to) + 864e5).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10));
      if (st.from < first) {
        R = await Promise.resolve(api.reconstruct(st.at, st.from, first)).catch(() => null);
        recon = ((R && R.snaps) || []).filter((x) => isDate(x.date) && x.date < first && x.date >= st.from).map((x) => {
          const y = Object.assign({}, x, { positions: sortedPositions(x.positions), date_basis: 'reconstructed', reconstructed: true }), sw = sectorWeights(x.sector_weights);
          if (sw) y.sector_weights = sw; else delete y.sector_weights;
          return y;
        }).filter((x) => x.positions.length);
      }
    }
    if (!all.length && !recon.length) throw new Error(ticker + ': no source-dated constituent weights in this date range; choose a newer date or fund');
    all = recon.concat(all);
    const [meta, extra] = await Promise.all([api.rankMeta().catch(() => null), Promise.resolve(api.json(api.hub + 'etf/sectors.json')).catch(() => null)]);
    const co = new Map(((meta && meta.cos) || []).map((r) => [symbol(r[0]), { name: r[1], sec: r[2] }]));
    const xsec = (extra && extra.sectors) || {};          // the ETF build's sector of every company ETFs hold (app/etf.py)
    const sources = [...new Set(all.map((x) => x.source))].join('; ');
    const from = all[0].date, to = all[all.length - 1].date;
    const label = external ? external.basis : indexed ? 'Index-tracker holdings proxy' : 'Actual fund disclosures';
    out.grid = all.map((s) => day(s.date));
    out.group = (st.style === 'stack' || (st.style === 'changes' && st.ag === 'sector')) ? 'sectors' : 'companies';
    out.fmt = percent; out.unit = '%'; out.actual = { fund: external ? external.id : ticker, source:st.aw, index: indexed ? st.at : null, reports: all.length - recon.length };
    if (recon.length) {
      const r0 = recon[0].date, r1 = recon[recon.length - 1].date, how = { price: 'share prices as traded (the Dow adds up its prices)', ndx: 'modified market values (the Nasdaq-100 caps its largest members; the caps here are an approximation)' }[R.how] || 'market values (every share outstanding; the index uses the shares that trade freely)';
      out.actual.reconTo = reported0 ? day(reported0) : Infinity; out.actual.recon = recon.length; out.actual.reconLast = day(r1); out.actual.reconHow = R.how;
      out.notes.add(`${r0} to ${r1}: RECONSTRUCTED, not the fund's holdings — the ${ref[0]}'s members at each quarter-end weighted by their ${how}, as the Sector weights video computes them.` + (reported0 ? ` From ${reported0}: ${ticker}'s reported holdings (SEC N-PORT and the sponsor's files).` : ''));
      const lo = recon.reduce((a, x) => (x.on_file < a.on_file ? x : a), recon[0]), hi = recon.reduce((a, x) => (x.on_file > a.on_file ? x : a), recon[0]);
      if (R.history && R.size) out.notes.add(`Members on file: ${lo.on_file} of the ${ref[0]}'s ${R.size} (${lo.date})${hi !== lo ? ' to ' + hi.on_file + ' (' + hi.date + ')' : ''}. Companies delisted, merged or bankrupt since are not on the site: the members on file share the whole index between them.`);
      if (R.thin) out.notes.add(`Up to ${R.thin}: too few of the members have prices on the site (from mid-1993) — left out.`);
      if (!R.history) out.notes.add(`${ref[0]}: membership history only from ${R.since || 'when the site began keeping it'} — before that, today's members are used: former members are left out and today's are counted in years before they joined (survivorship).`);
      if (R.how !== 'price') out.notes.add('Market values: each month-end close × the latest shares outstanding, put on today\'s basis with the split history — a company that has since bought back or issued many shares is smaller or larger here than it was. A company counts once, all its share classes together; the reports list each class (GOOGL and GOOG).');
      if (st.style === 'changes') out.notes.add('The change at ' + (reported0 || 'the switch') + ' compares a reconstruction with the fund\'s report: it shows the two methods as much as the portfolio.');
    }
    out.notes.add((recon.length ? 'Reported source dates: ' + (reported0 ? reported0 + ' to ' + to + '; before them, reconstructed quarter-ends (above).' : 'none in this range: every snapshot is reconstructed.')
      : 'Observed or reported source dates: ' + from + (from === to ? '' : ' to ' + to) + '. No synthetic history.'));
    if (all.some(s => s.date_basis === 'observed')) out.notes.add('Some sponsor workbook dates are retrieval OBSERVATIONS because the source did not expose a parseable holdings as-of date; they are NOT claimed to be report effective dates.');
    if (all.some(s => s.date_basis === 'unknown')) out.notes.add('At least one older holdings record lacks date provenance. Its displayed date must NOT be claimed as a verified portfolio effective/report date.');
    out.notes.add(label + '. Sources: ' + sources + (external ? '.' : '. Report weights use fund NAV, not constituent market capitalization.'));
    if (indexed) {
      out.notes.add('Index weights are proxied by ' + ticker + ' portfolio holdings, not licensed official index weight files; tracking differences and cash may exist.');
      if (st.at === 'dji') out.notes.add('Dow 30 is PRICE-weighted. DIA replicates its price-weighted basket; never apply market-cap weights to Dow.');
      else out.notes.add(ref[0] + ' index methodology: ' + ref[2] + '. Tracker positions are a disclosed proxy.');
    }
    if (all.length > 1) out.notes.add('Frames interpolate VISUALLY between actual snapshots; no holdings are asserted for interim dates.');
    if (all.some((s) => s.partial)) out.notes.add('Quarter-end snapshots come from the fund\'s public N-PORT reports (SEC data sets since 2019): the largest names, the same in every quarter, and sector weights over every long equity line.');
    // a reported sector first (a sponsor's file; '-' and blanks are no sector), then the site's companies, then the ETF build's map
    const secFor = (s, ticker) => {
      const reported = toSector((s.sectors || {})[ticker]);
      if (reported !== 'other') return reported;
      const known = toSector((co.get(ticker) || {}).sec);
      return known !== 'other' ? known : toSector(xsec[ticker]);
    };
    const sector = st.style === 'stack' || (st.style === 'changes' && st.ag === 'sector');
    const area = st.style === 'stack' || st.style === 'companies';
    let over = 0;
    const tables = all.map(s => {
      const m = new Map();
      if (sector && s.sector_weights) Object.entries(s.sector_weights).forEach(([k,w]) => m.set(k,(m.get(k)||0)+w));
      else s.positions.forEach(([k,w]) => {const key = sector ? secFor(s,k) : k; m.set(key,(m.get(key)||0)+w);});
      let sum = [...m.values()].reduce((a,b)=>a+b,0);
      if (area && sum > 1.02) throw new Error('Exposures exceed 100%; use holdings bars instead of a 100% area chart');
      // a report's equity lines can add up to a little over its net assets (liabilities net against the portfolio):
      // scaled to exactly 100% for the area chart, with a note
      if (area && sum > 1.000001) { for (const [k2, v2] of m) m.set(k2, v2 / sum); over = Math.max(over, sum); sum = 1; }
      if (area || sector) m.set('other',(m.get('other')||0)+Math.max(0,1-sum));
      return m;
    });
    if (over) out.notes.add('Some reports\' equity lines add up to more than their net assets (up to ' + (100 * over).toFixed(2) + '%): scaled to 100% for the area chart.');
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
    const missingChangeHistory = st.style === 'changes' && all.length < 2;
    if (st.style === 'changes') {
      if (missingChangeHistory) {
        // A single official ETF disclosure is useful in its own right,
        // but subtracting from a nonexistent prior period would be fabricated.
        out.kind = 'rank'; out.order = 'desc'; out.rankN = n;
        out.actual = { ...out.actual, fallback: 'single-disclosure', available_dates: [from] };
        out.metric = external ? external.basis : 'Reported NAV ' + (sector ? 'sector' : 'company') + ' weight';
        out.notes.add('Requested: weight CHANGES. Only one dated disclosure is available (' + from +
          '). Showing its actual reported weights as a SINGLE-DATE CARD, NOT a change. Select a wider date range or wait for a second real disclosure.');
        out.notes.add('No previous holdings were inferred, no weights were backfilled, and no percentage-point deltas were calculated.');
      } else {
        out.series.forEach(s=>{s.v=s.v.slice(1).map((v,i)=>v-s.v[i]);});
        out.order='abs'; out.grid=out.grid.slice(1); out.fmt=v=>(v>=0?'+':'')+(100*v).toFixed(2)+' pp';
        out.metric='Weight change vs previous disclosed snapshot';
        out.notes.add('Changes are percentage points, not trade size or proof of rebalancing. Use the date range to select the comparison periods.');
      }
    }
    const range = from === to ? from : from + ' → ' + to;
    const tag = external ? external.basis : indexed && st.at === 'dji' ? 'DIA tracking basket · price-weighted index proxy' : label + ' · ' + ticker;
    out.title = (external ? external.name : indexed ? ref[0] : ticker) + ': ' + (missingChangeHistory ? 'single dated ' + (sector ? 'sector' : 'company') + ' weight snapshot (no changes)' : st.style === 'changes' ? 'weight changes' : (sector ? 'sector' : 'company') + ' weights') + (st.aw === 'official' ? ' · transaction lower bounds' : '');
    out.sub = range + ' · ' + (recon.length ? 'reconstructed to ' + recon[recon.length - 1].date + (reported0 ? ', then ' + ticker + '\'s reports' : '') : tag) + ' · ' + all.length + ' dated snapshot' + (all.length === 1 ? '' : 's') + (all.some(s => s.date_basis === 'observed') ? ' · observed date(s) included' : '') + (all.some(s => s.date_basis === 'unknown') ? ' · date basis unverified' : '');
    out.foot = missingChangeHistory ? ('Only ' + from + ' is on file · single disclosed snapshot, not a weight-change history' +
      (st.aw === 'official' ? ' · transactions only, NOT holdings' : st.aw === '13f' ? ' · reported 13F values, NOT AUM' : ' · reported NAV weights'))
      : st.aw === 'official' ? 'Transaction LOWER-BOUND composition · not actual holdings · limited recent feed'
      : st.aw === '13f' ? 'Quarter-end 13F reported value · not current holdings or total AUM'
      : recon.length ? 'Before ' + (reported0 || 'the fund\'s first report') + ': reconstructed from the index members\' market values · then reported holdings · transitions illustrative'
      : from === to ? 'Single reported holdings snapshot — not a history' : 'Reported holdings dates only; transitions illustrative';
    return out;
  }
  root.FFActual = { TRACKERS, build, snapshots, normalizeSnapshot, snapshotFromDetail, sortedPositions, toSector, disclosedSource, quarterlySnapshots, sectorWeights };
  if (typeof module !== 'undefined') module.exports = root.FFActual;
})(typeof globalThis !== 'undefined' ? globalThis : this);
