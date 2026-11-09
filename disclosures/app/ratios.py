"""Valuation beside the price — for every company of the move odds, its price ratios over its whole history, so that a
price at its all-time high (or low) can be read against its multiples:

  P/E   the close ÷ the last four first-filed quarterly diluted EPS (the SEC GAAP EPS store, data branch eps-gaap/;
        from 1 to 300: app/highs.py's P/E, positive only)
  P/S   the close ÷ the last four quarters' revenue per diluted share (the first-filed income statements, data branch
        eps-fundamental/: each quarter's revenue ÷ its diluted share count; from 0.01 to 300)

Both point in time: each quarter counts from the day its 10-Q or 10-K was filed (never a later restatement), four
consecutive quarters, the latest ended within 200 days. Stock splits are read from the diluted share count
(app/highs.py fix_splits), and a share count filed in thousands by mistake is put right (share_units). The closes are
split-adjusted, not dividend-adjusted.

For each ratio, against its own history: its all-time high and low (and whether today is one), the percentile of today
among every day on file and among the last five years, the range (10–90%, the median). Against its industry: the other
companies of the move odds in the same SIC industry (four digits), else its industry group (three), else its major
group (two), else its sector — the first with 6 or more priced that week — their median each week (today's companies:
survivors), its rank among them now, and its premium to their median over the years (its own percentile). And how the
price's moves split into the per-share figure and the multiple, over the last year, 3 and 5 years and the current run
of highs: price change = (1 + the per-share change) × (1 + the ratio's change) − 1.

Also, from the valuation research (research-valuation's public/c/<cik>.json): P/B and EV/EBITDA weekly since June 2022
(now, the median, today's percentile) and the peer medians of P/E, EV/EBITDA and EV/Sales (SIC peers from the SEC's
full list of companies).

Published in each company's file (app/moves.py: public/moves/a/<KEY>.json → ratios): the weekly series (each week's
last close) of the ratios and of their industry median, and the figures above; the highs, lows and ranges lists carry
each company's P/S and its percentiles (stamp). Descriptive history, not a forecast.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import warnings
from pathlib import Path

import numpy as np

import highs as HI

RATIOS = (('pe', 'P/E', 'EPS'), ('ps', 'P/S', 'revenue per share'))
CAP = 300.0                    # a ratio above this (earnings or sales near zero) is not counted
FLOOR = {'pe': 1.0, 'ps': 0.01}  # nor one under this (a one-off gain, or a figure filed in the wrong units)
MIN_DAYS = 126                 # days with the ratio before it is published
MIN_PEERS = 6                  # other companies priced in the week for an industry comparison
MIN_WEEKS = 52                 # weeks of the premium to the industry before its own percentile counts
Y5 = 1260                      # trading days in five years
SPANS = ((252, '1y'), (756, '3y'), (1260, '5y'))
LEVELS = ('industry', 'industry group', 'major group', 'sector')
# the SIC manual's industry groups (three digits) the companies of the move odds fall in most
SIC3 = {'131': 'Crude petroleum and natural gas', '138': 'Oil and gas field services', '153': 'Operative builders', '162': 'Heavy construction',
        '201': 'Meat products', '202': 'Dairy products', '203': 'Preserved fruits and vegetables', '204': 'Grain mill products', '206': 'Sugar and confectionery',
        '208': 'Beverages', '209': 'Miscellaneous food preparations', '211': 'Cigarettes', '221': 'Cotton fabric mills', '231': "Men's suits and coats",
        '232': "Men's and boys' furnishings", '233': "Women's outerwear", '242': 'Sawmills and planing mills', '243': 'Millwork, plywood and structural members',
        '251': 'Household furniture', '252': 'Office furniture', '262': 'Paper mills', '263': 'Paperboard mills', '265': 'Paperboard containers and boxes',
        '267': 'Converted paper products', '271': 'Newspapers', '272': 'Periodicals', '273': 'Books', '275': 'Commercial printing',
        '281': 'Industrial inorganic chemicals', '282': 'Plastics materials and synthetics', '283': 'Drugs', '284': 'Soaps, cleaners and toiletries',
        '285': 'Paints and allied products', '286': 'Industrial organic chemicals', '287': 'Agricultural chemicals', '289': 'Miscellaneous chemical products',
        '291': 'Petroleum refining', '301': 'Tires and inner tubes', '308': 'Miscellaneous plastics products', '314': 'Footwear', '321': 'Flat glass',
        '322': 'Glass and glassware', '324': 'Cement', '327': 'Concrete, gypsum and plaster products', '331': 'Steel works and blast furnaces',
        '333': 'Primary nonferrous metals', '335': 'Nonferrous rolling and drawing', '336': 'Nonferrous foundries', '341': 'Metal cans and containers',
        '342': 'Cutlery, handtools and hardware', '343': 'Plumbing and heating, except electric', '344': 'Fabricated structural metal products',
        '346': 'Metal forgings and stampings', '348': 'Ordnance and accessories', '349': 'Miscellaneous fabricated metal products', '351': 'Engines and turbines',
        '352': 'Farm and garden machinery', '353': 'Construction and related machinery', '354': 'Metalworking machinery', '355': 'Special industry machinery',
        '356': 'General industrial machinery', '357': 'Computer and office equipment', '358': 'Refrigeration and service machinery',
        '359': 'Industrial machinery, not elsewhere classified', '361': 'Electric distribution equipment', '362': 'Electrical industrial apparatus',
        '363': 'Household appliances', '364': 'Electric lighting and wiring equipment', '365': 'Household audio and video equipment',
        '366': 'Communications equipment', '367': 'Electronic components and accessories', '369': 'Miscellaneous electrical equipment',
        '371': 'Motor vehicles and equipment', '372': 'Aircraft and parts', '373': 'Ship and boat building', '374': 'Railroad equipment',
        '375': 'Motorcycles, bicycles and parts', '376': 'Guided missiles and space vehicles', '379': 'Miscellaneous transportation equipment',
        '381': 'Search and navigation equipment', '382': 'Measuring and controlling devices', '384': 'Medical instruments and supplies',
        '385': 'Ophthalmic goods', '386': 'Photographic equipment and supplies', '391': 'Jewelry and precious metal', '394': 'Toys and sporting goods',
        '399': 'Miscellaneous manufactures', '401': 'Railroads', '421': 'Trucking and courier services', '422': 'Public warehousing and storage',
        '441': 'Deep sea foreign transportation', '448': 'Water transportation of passengers', '451': 'Air transportation, scheduled',
        '452': 'Air transportation, nonscheduled', '458': 'Airports and terminal services', '461': 'Pipelines, except natural gas', '472': 'Passenger transportation arrangement',
        '473': 'Freight transportation arrangement', '481': 'Telephone communications', '483': 'Radio and television broadcasting',
        '484': 'Cable and other pay television services', '489': 'Communications services, not elsewhere classified', '491': 'Electric services',
        '492': 'Gas production and distribution', '493': 'Combination utility services', '494': 'Water supply', '495': 'Sanitary services',
        '501': 'Motor vehicles, parts and supplies (wholesale)', '504': 'Professional and commercial equipment (wholesale)', '505': 'Metals and minerals (wholesale)',
        '506': 'Electrical goods (wholesale)', '507': 'Hardware, plumbing and heating equipment (wholesale)', '508': 'Machinery, equipment and supplies (wholesale)',
        '509': 'Miscellaneous durable goods (wholesale)', '512': 'Drugs and proprietaries (wholesale)', '514': 'Groceries (wholesale)',
        '517': 'Petroleum products (wholesale)', '519': 'Miscellaneous nondurable goods (wholesale)', '521': 'Lumber and building materials dealers',
        '525': 'Hardware stores', '531': 'Department stores', '533': 'Variety stores', '539': 'Miscellaneous general merchandise stores', '541': 'Grocery stores',
        '551': 'New and used car dealers', '553': 'Auto and home supply stores', '554': 'Gasoline service stations', '559': 'Automotive dealers, not elsewhere classified',
        '561': "Men's and boys' clothing stores", '562': "Women's clothing stores", '565': 'Family clothing stores', '566': 'Shoe stores',
        '571': 'Furniture and home furnishings stores', '573': 'Radio, television and computer stores', '581': 'Eating and drinking places', '591': 'Drug stores',
        '594': 'Miscellaneous shopping goods stores', '596': 'Nonstore retailers', '599': 'Retail stores, not elsewhere classified', '602': 'Commercial banks',
        '603': 'Savings institutions', '609': 'Functions related to banking', '611': 'Federal credit agencies', '614': 'Personal credit institutions',
        '615': 'Business credit institutions', '616': 'Mortgage bankers and brokers', '621': 'Security brokers and dealers', '622': 'Commodity contracts brokers and dealers',
        '628': 'Security and commodity services', '631': 'Life insurance', '632': 'Medical service and health insurance', '633': 'Fire, marine and casualty insurance',
        '635': 'Surety insurance', '636': 'Title insurance', '641': 'Insurance agents, brokers and services', '651': 'Real estate operators and lessors',
        '653': 'Real estate agents and managers', '655': 'Land subdividers and developers', '671': 'Holding offices', '672': 'Investment offices',
        '679': 'Miscellaneous investing (REITs and others)', '701': 'Hotels and motels', '721': 'Laundry, cleaning and garment services', '726': 'Funeral service and crematories',
        '731': 'Advertising', '732': 'Credit reporting and collection', '734': 'Services to buildings', '735': 'Equipment rental and leasing',
        '736': 'Personnel supply services', '737': 'Computer and data processing services', '738': 'Miscellaneous business services',
        '751': 'Automotive rentals, no drivers', '781': 'Motion picture production and services', '783': 'Motion picture theaters', '794': 'Commercial sports',
        '799': 'Miscellaneous amusement and recreation', '801': 'Offices and clinics of medical doctors', '805': 'Nursing and personal care facilities',
        '806': 'Hospitals', '807': 'Medical and dental laboratories', '808': 'Home health care services', '809': 'Health and allied services, not elsewhere classified',
        '821': 'Elementary and secondary schools', '822': 'Colleges and universities', '824': 'Vocational schools', '829': 'Schools and educational services, not elsewhere classified',
        '835': 'Child day care services', '871': 'Engineering and architectural services', '872': 'Accounting, auditing and bookkeeping',
        '873': 'Research and testing services', '874': 'Management and public relations', '999': 'Nonclassifiable establishments'}
MORE = (('pb', 'P/B'), ('ev_ebitda', 'EV/EBITDA'), ('ev_sales', 'EV/Sales'))
SECTOR = {'technology': 'Technology', 'healthcare': 'Health care', 'financials': 'Financials', 'financial': 'Financials', 'energy': 'Energy',
          'industrials': 'Industrials', 'industrial': 'Industrials', 'materials': 'Materials', 'utilities': 'Utilities', 'real_estate': 'Real estate',
          'consumer_discretionary': 'Consumer discretionary', 'consumer_staples': 'Consumer staples', 'communication': 'Communication services',
          'communication_services': 'Communication services', 'other': 'Other'}


def sig(v, n=3):
    """A float to n significant digits (None when not finite)."""
    if v is None:
        return None
    v = float(v)
    if not math.isfinite(v):
        return None
    if v == 0:
        return 0.0
    d = max(0, n - 1 - int(math.floor(math.log10(abs(v)))))
    return round(v, d)


def _r(v, d=1):
    if v is None:
        return None
    v = float(v)
    return round(v, d) if math.isfinite(v) else None


def week_of(days):
    """Each day's week: its number counted from the week of Friday 2 January 1970 (Saturday and Sunday join the week
    before)."""
    t = np.asarray(days, dtype='datetime64[D]').astype(np.int64)        # days since Thursday 1 January 1970
    fri = t + (4 - (t + 3) % 7)                                         # that week's Friday (Monday = 0 … Sunday = 6)
    return (fri - 1) // 7


def friday(w):
    """Week number → the date of its Friday."""
    return (dt.date(1970, 1, 2) + dt.timedelta(days=7 * int(w))).isoformat()


def ttm(days, recs):
    """highs.ttm_eps, vectorized: the trailing four quarters' figure known on each day (by filing date; four consecutive
    quarters 250–300 days from the first end to the last, the latest ended within 200 days), NaN otherwise. recs:
    [(filed, end, value)]."""
    dn = np.asarray(days, dtype='datetime64[D]')
    out = np.full(len(dn), np.nan)
    if not recs or not len(dn):
        return out
    by_end = {}
    for filed, end, v in recs:
        if end not in by_end or filed < by_end[end][0]:
            by_end[end] = (filed, v)
    ends = sorted(by_end)
    known = []
    for i in range(3, len(ends)):
        e4 = ends[i - 3:i + 1]
        span = (dt.date.fromisoformat(e4[-1]) - dt.date.fromisoformat(e4[0])).days
        if not 250 <= span <= 300:
            continue
        known.append((max(by_end[e][0] for e in e4), sum(by_end[e][1] for e in e4), e4[-1]))
    if not known:
        return out
    known.sort()
    kd = np.array([k[0] for k in known], dtype='datetime64[D]')
    ke = np.array([k[2] for k in known], dtype='datetime64[D]')
    kv = np.array([k[1] for k in known], float)
    best = np.zeros(len(known), int)                                    # the latest quarter known by each filing
    cur = 0
    for j in range(len(known)):
        if ke[j] >= ke[cur]:
            cur = j
        best[j] = cur
    ix = np.searchsorted(kd, dn, side='right') - 1
    ok = ix >= 0
    b = best[np.clip(ix, 0, None)]
    ok &= (dn - ke[b]).astype(np.int64) <= 200
    out[ok] = kv[b[ok]]
    return out


def share_units(shares, trusted=None):
    """Share counts tagged in thousands (or millions) by mistake, put right (NVIDIA's 2010–11 filings tag 590,997 for
    591 million, ConocoPhillips' 2013–20 ones 1.24 million for 1.24 billion): a count more than 300 times off its
    reference that a factor of 1,000 or 1,000,000 brings within 2 times of it is multiplied or divided by that factor.
    The reference: the median of the eight nearest trusted quarters (their EPS agrees with net income ÷ shares: the
    store drops an EPS that does not), else of the eight nearest that are not themselves off the median of all by more
    than 300 times. A list of floats."""
    lg = np.log10(np.asarray(shares, float))
    n = len(lg)
    out = list(map(float, shares))
    ok = np.asarray(trusted, bool) if trusted is not None and np.sum(trusted) >= 2 else np.abs(lg - np.median(lg)) < 2.5
    ref_ix = np.nonzero(ok)[0]
    if len(ref_ix) < 2:
        return out
    for i in range(n):
        near = ref_ix[ref_ix != i]
        near = near[np.argsort(np.abs(near - i), kind='stable')[:8]]
        ref = float(np.median(lg[near]))
        off = lg[i] - ref
        if abs(off) < 2.5:
            continue
        for f in (3, 6):
            k = -f if off > 0 else f
            if abs(off + k) < 0.3:
                out[i] = out[i] * 10 ** k
                break
    return out


def per_share(quarters, field='revenue'):
    """First-filed quarterly figure per diluted share from the income statement store's quarters ([{'end', 'fields':
    {field: {val, filed}, 'diluted_shares': {val, filed}}}]), the share counts' unit slips put right (share_units) and
    restated across the splits they show: [(filed, end, per share)]."""
    rows = []
    for q in sorted(quarters or [], key=lambda q: q.get('end') or ''):
        f = q.get('fields') or {}
        x, sh = f.get(field) or {}, f.get('diluted_shares') or {}
        try:
            v, s = float(x['val']), float(sh['val'])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(v) and math.isfinite(s) and s > 0) or not q.get('end'):
            continue
        filed = max(x.get('filed') or '', sh.get('filed') or '')
        if filed:
            rows.append((q['end'], filed, v, s, 'eps' in f and 'net_income' in f and not sh.get('computed')))
    if not rows:
        return []
    shares = share_units([r[3] for r in rows], [r[4] for r in rows])
    recs = [{'end': e, 'filed': fd, 'eps': v / s, 'shares': s} for (e, fd, v, _, _), s in zip(rows, shares)]
    return HI.fix_splits(recs)


def ratio(px, per, lo=0.0):
    """Price ÷ a positive per-share figure, kept from lo to CAP."""
    with np.errstate(invalid='ignore', divide='ignore'):
        r = np.where(np.asarray(per, float) > 0, np.asarray(px, float) / per, np.nan)
    r[~((r > 0) & (r >= lo) & (r <= CAP))] = np.nan
    return r


def own_stats(days, r):
    """The ratio against its own history (daily): now, its high and low (value, day), today one of them, the percentile
    of today among every day and among the last five years, the range."""
    ok = np.isfinite(r)
    if ok.sum() < MIN_DAYS:
        return None
    ds = np.asarray(days)
    v, d = r[ok], ds[ok]
    now = float(r[-1]) if ok[-1] else None
    ih, il = int(np.argmax(v)), int(np.argmin(v))
    q = np.percentile(v, [10, 25, 50, 75, 90])
    st = {'now': sig(now), 'date': str(ds[-1]), 'from': str(d[0]), 'days': int(ok.sum()), 'hi': [sig(v[ih]), str(d[ih])], 'lo': [sig(v[il]), str(d[il])],
          'q': [sig(x) for x in q]}
    if now is not None:
        prior = v[:-1]
        st['at_hi'] = bool(len(prior) and now >= prior.max())
        st['at_lo'] = bool(len(prior) and now <= prior.min())
        st['pct'] = _r(100.0 * np.mean(v <= now))
        st['off_hi'] = _r(now / v[ih] - 1, 4)
        st['since_hi'] = int(len(r) - 1 - np.nonzero(ds == d[ih])[0][0])
    w = r[-Y5:]
    w5, d5 = w[np.isfinite(w)], ds[-Y5:][np.isfinite(w)]
    if len(w5) >= 252:
        i5h, i5l = int(np.argmax(w5)), int(np.argmin(w5))
        st['y5'] = {'from': str(d5[0]), 'q': [sig(x) for x in np.percentile(w5, [10, 50, 90])], 'hi': [sig(w5[i5h]), str(d5[i5h])], 'lo': [sig(w5[i5l]), str(d5[i5l])]}
        if now is not None:
            st['y5']['pct'] = _r(100.0 * np.mean(w5 <= now))
    return st


def splits(days, px, per, r, run_start=None):
    """The price's change split into the per-share figure's and the ratio's, over the last year, 3 and 5 years and
    the current run of highs: [{k, from, price, per, ratio}] (price = (1 + per) × (1 + ratio) − 1)."""
    t = len(r) - 1
    if t < 1 or not np.isfinite(r[t]):
        return []
    out = []
    spans = list(SPANS)
    if run_start:
        s = int(np.searchsorted(np.asarray(days), run_start))
        if 0 <= s < t:
            spans.append((t - s, 'run'))
    for span, k in spans:
        s = t - span
        if s < 0 or not (np.isfinite(r[s]) and per[s] > 0 and per[t] > 0 and px[s] > 0):
            continue
        out.append({'k': k, 'from': str(days[s]), 'price': _r(px[t] / px[s] - 1, 4), 'per': _r(per[t] / per[s] - 1, 4), 'ratio': _r(r[t] / r[s] - 1, 4)})
    return out


def load_fund(folder, ciks=None):
    """{cik: quarters} from the first-filed income statement store (data branch, eps-fundamental/<cik>.json)."""
    out = {}
    folder = Path(folder)
    if not folder.is_dir():
        return out
    want = None if ciks is None else {str(int(c)) for c in ciks if c}
    for p in folder.glob('*.json'):
        if want is not None and p.stem not in want:
            continue
        try:
            out[p.stem] = json.loads(p.read_text(encoding='utf-8')).get('quarters') or []
        except (OSError, ValueError):
            continue
    return out


def more_of(val_dir, cik):
    """P/B and EV/EBITDA weekly since June 2022 and the peer medians of the valuation research (research-valuation's
    public/c/<cik>.json: river and peers), or None."""
    try:
        doc = json.loads((Path(val_dir) / 'c' / f'{int(cik)}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    rv, pr = doc.get('river') or {}, doc.get('peers') or {}
    m = rv.get('metrics') or {}
    rows = []
    for k, lab in MORE:
        a = m.get(k) or {}
        b = pr.get(k) or {}
        now = a.get('current') if a.get('current') is not None else b.get('own')
        if now is None and b.get('p50') is None:
            continue
        pct = a.get('pct')
        rows.append({'k': k, 'label': lab, 'now': sig(now), 'mid': sig(a.get('median')), 'pct': _r(100 * pct) if pct is not None else None, 'weeks': a.get('weeks'),
                     'peer': {'mid': sig(b.get('p50')), 'p25': sig(b.get('p25')), 'p75': sig(b.get('p75')), 'n': b.get('n'), 'group': b.get('group')} if b.get('p50') is not None else None})
    pe = pr.get('pe') or {}
    if not rows and pe.get('p50') is None:
        return None
    out = {'from': rv.get('from'), 'rows': rows}
    if pe.get('p50') is not None:
        out['peer_pe'] = {'mid': sig(pe.get('p50')), 'p25': sig(pe.get('p25')), 'p75': sig(pe.get('p75')), 'n': pe.get('n'), 'group': pe.get('group'), 'own': sig(pe.get('own'))}
    return out


def _levels(a, names):
    """The peer groups a company can be compared in, most specific first: [(level, key, name)]."""
    out = []
    sic = str(a.get('sic') or '').strip()
    if len(sic) == 4 and sic.isdigit():
        out.append(('industry', 'SIC-' + sic, a.get('industry') or f'SIC {sic}'))
        out.append(('industry group', 'SIC-' + sic[:3], SIC3.get(sic[:3]) or f'SIC {sic[:3]}'))
        out.append(('major group', 'SIC-' + sic[:2], (names or {}).get(sic[:2]) or f'SIC {sic[:2]}'))
    if a.get('sector'):
        s = str(a['sector'])
        out.append(('sector', 'sector:' + s, SECTOR.get(s, s.replace('_', ' ').capitalize())))
    return out


def build(data, raws, assets, eps=None, fund=None, val_dir=None, names=None, runs=None, verbose=True):
    """{key: ratios block} for the companies of the move odds, and a status. data {key: (days, adjusted closes, last)};
    raws {key: (days, raw closes)}; assets [{key, kind, cik, sic, industry, sector, mcap, ticker}]; eps {cik: records}
    (highs.load_eps); fund {cik: quarters} (load_fund); names {two-digit SIC: name}; runs {key: the current run of
    highs' first day}."""
    eps, fund, raws, runs = eps or {}, fund or {}, raws or {}, runs or {}
    comps = [a for a in assets if a.get('kind') == 'stock' and a['key'] in data and a.get('cik')]
    rows = []                                                           # (asset, block, {ratio: (weeks, values)})
    for a in comps:
        key, cik = a['key'], str(int(a['cik']))
        days, closes = data[key][0], np.asarray(data[key][1], float)
        if len(days) < MIN_DAYS or not np.all(np.isfinite(closes)) or (closes <= 0).any():
            continue
        recs = {'pe': HI.fix_splits(eps.get(cik) or []) if eps.get(cik) else [], 'ps': per_share(fund.get(cik))}
        if not recs['pe'] and not recs['ps']:
            continue
        first = min(r[0] for v in recs.values() for r in v)              # nothing before the first filing on file
        i0 = max(0, int(np.searchsorted(np.asarray(days), first)) - 1)
        days = list(days[i0:])
        px = HI.raw_closes(days, closes[i0:], raws[key]) if key in raws else closes[i0:]
        wk = week_of(days)
        last = np.r_[np.nonzero(np.diff(wk))[0], len(wk) - 1]           # each week's last trading day
        blk, wser = {'as_of': str(days[-1])}, {}
        for k, _, _ in RATIOS:
            if not recs[k]:
                continue
            per = ttm(days, recs[k])
            r = ratio(px, per, FLOOR[k])
            st = own_stats(days, r)
            if not st:
                continue
            if st['now'] is None:                                       # why there is none today
                pt = per[-1]
                st['why'] = 'none' if not np.isfinite(pt) else 'loss' if pt <= 0 else 'high' if px[-1] / pt > CAP else 'low'
            sp = splits(days, px, per, r, runs.get(key))
            if sp:
                st['split'] = sp
            blk[k] = st
            wser[k] = (wk[last], r[last].astype(np.float32))
        if wser:
            rows.append((a, blk, wser))
    if not rows:
        return {}, {'companies': 0}
    W0 = min(int(s[0][0]) for _, _, w in rows for s in w.values())
    W1 = max(int(s[0][-1]) for _, _, w in rows for s in w.values())
    nw = W1 - W0 + 1
    M = {k: np.full((len(rows), nw), np.nan, np.float32) for k, _, _ in RATIOS}
    lastw = np.full(len(rows), -1, int)
    for i, (a, _, w) in enumerate(rows):
        for k, (wks, vals) in w.items():
            M[k][i, wks - W0] = vals
            lastw[i] = max(lastw[i], int(wks[-1]) - W0)
    members = {}
    for i, (a, _, _) in enumerate(rows):
        for lev, gk, gname in _levels(a, names):
            members.setdefault(gk, []).append(i)
    mcap = np.array([float(a.get('mcap') or 0) for a, _, _ in rows])
    used = {lev: 0 for lev in LEVELS}
    for i, (a, blk, _) in enumerate(rows):
        L = int(lastw[i])
        series, i_first = {}, nw
        for k, lab, _ in RATIOS:
            own = M[k][i]
            if k not in blk or not np.isfinite(own).any():
                continue
            i_first = min(i_first, int(np.argmax(np.isfinite(own))))
            for lev, gk, gname in _levels(a, names):
                peers = [j for j in members.get(gk, []) if j != i]
                if not peers:
                    continue
                P = M[k][peers]
                at = P[:, L]
                fin = np.isfinite(at)
                if fin.sum() < MIN_PEERS:
                    continue
                cnt = np.isfinite(P).sum(0)
                with warnings.catch_warnings():                          # (weeks with no peer priced: NaN, said nothing)
                    warnings.simplefilter('ignore', RuntimeWarning)
                    med = np.nanmedian(P, axis=0)
                med[cnt < MIN_PEERS] = np.nan
                vals = at[fin]
                ind = {'level': lev, 'key': gk, 'name': gname, 'n': int(fin.sum()), 'mid': sig(np.median(vals)),
                       'p25': sig(np.percentile(vals, 25)), 'p75': sig(np.percentile(vals, 75))}
                ov = own[L]
                if np.isfinite(ov):
                    ind['rank'] = _r(100.0 * (np.sum(vals < ov) + 0.5 * np.sum(vals == ov)) / len(vals))
                    with np.errstate(invalid='ignore', divide='ignore'):
                        rel = own / med
                    rf = rel[np.isfinite(rel)]
                    if np.isfinite(rel[L]):
                        ind['rel'] = sig(rel[L])
                        if len(rf) >= MIN_WEEKS:
                            ind['rel_pct'] = _r(100.0 * np.mean(rf <= rel[L]))
                            ind['rel_mid'] = sig(np.median(rf))
                            ind['rel_weeks'] = int(len(rf))
                pj = [peers[x] for x in np.nonzero(fin)[0]]
                pj.sort(key=lambda j: -mcap[j])
                ind['top'] = [[rows[j][0].get('ticker') or rows[j][0]['key'], sig(M[k][j, L])] for j in pj[:8]]
                blk[k]['ind'] = ind
                series[k + '_ind'] = med
                used[lev] += 1
                break
        if i_first >= nw:
            continue
        # the weekly series from the first week with a ratio to the company's last week
        enc = {}
        for k, _, _ in RATIOS:
            if k in blk:
                enc[k] = [sig(x) for x in M[k][i, i_first:L + 1]]
            if k + '_ind' in series:
                enc[k + '_ind'] = [sig(x) for x in series[k + '_ind'][i_first:L + 1]]
        blk['w'] = {'d0': friday(W0 + i_first), 'n': int(L + 1 - i_first), **enc}
    out = {}
    for a, blk, _ in rows:
        if 'w' not in blk:
            continue
        if val_dir:
            mo = more_of(val_dir, a['cik'])
            if mo:
                blk['more'] = mo
        out[a['key']] = blk
    stat = {'companies': len(out), 'pe': sum(1 for b in out.values() if 'pe' in b), 'ps': sum(1 for b in out.values() if 'ps' in b), 'industry_levels': used,
            'weeks': nw}
    if verbose:
        print('ratios:', json.dumps(stat), flush=True)
    return out, stat


def stamp(state, blk):
    """A company's ratios in a list row's state: P/E and P/S, their own and industry percentiles, at their own high or
    low (the highs, lows and ranges lists)."""
    if not state or not blk:
        return state
    for k in ('pe', 'ps'):
        b = blk.get(k)
        if not b or b.get('now') is None:
            continue
        if k == 'ps':
            state['ps'] = b['now']
        state[k + '_all'] = b.get('pct')
        state[k + '_5y'] = (b.get('y5') or {}).get('pct')
        state[k + '_ind'] = (b.get('ind') or {}).get('rank')
        if b.get('at_hi'):
            state[k + '_ath'] = True
        if b.get('at_lo'):
            state[k + '_atl'] = True
    return state
