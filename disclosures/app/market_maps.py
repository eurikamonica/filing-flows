"""Market maps (Disclosures → Market maps): where the disclosed money moved, what the best-known 13F portfolios look like,
the market as a heatmap, who is crowded into what, when corporate debt falls due, and two gauges of the whole market
(valuation and liquidity). Kept on the branch "research-market" by .github/workflows/research-market.yml; scan.yml
publishes its public/ at data/research/market/.

  collect   fetches what the hub does not already have: FRED series (Fed balance sheet, Treasury General Account,
            reverse repo, high-yield spread, curve, 10-year yields, GDP, the Fed's Z.1 market value of corporate equities,
            the S&P 500), Robert Shiller's monthly S&P data (CAPE, earnings, dividends, the real total return) and one
            Nasdaq screener snapshot (market cap, day's move and sector of every listed stock)
  build     public/ from those and the hub's own data (read from its published files / data branches):
              flows.json        money-flow Sankey per period: groups → sectors → stocks, net buying and net selling apart
                                (smart money's combined flows: 13F managers, active ETFs, insiders, insiders' 10b5-1 plan
                                trades, officials)
              managers.json     the watched 13F managers' portfolios by sector, this quarter against the one before,
                                and each manager's top holdings quarter by quarter (the bar chart race)
              heatmap.json      a squarified treemap of the largest stocks (size = market cap, grouped by sector) with the
                                colour metrics: the day's move, 52-week position, smart-money score, beat rate, short-interest
                                change, analysts' target upside
              network.json      watched managers ↔ the stocks they share (a force layout computed here), a crowding index per
                                stock and a walk-forward check of crowded against uncrowded names
              maturity.json     the debt maturity wall: what falls due each year by rating band, market-wide and per company
              thermometer.json  Buffett indicator, Shiller CAPE, the excess CAPE yield and the forward P/E, each with its
                                percentile and, where the history allows, the fit to the next ten years' real return
              liquidity.json    net liquidity (Fed balance sheet − TGA − reverse repo), the high-yield spread and the curve, weekly
              img/              PNG / GIF renders for the X posts (heatmap, the race of the largest portfolio)
              status.json

    python disclosures/app/market_maps.py collect --root rm
    python disclosures/app/market_maps.py build --root rm --smart smart/public --consensus cons/public --debt debt/public \
        --hub hub/disclosures/docs/data
"""
import argparse
import bisect
import csv
import datetime as dt
import gzip
import io
import json
import math
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = 'Mozilla/5.0 (X11; Linux x86_64) FilingFlows/1.0 (public data reader)'
FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}'
FRED_API = ('https://api.stlouisfed.org/fred/series/observations?series_id={id}&api_key={key}&file_type=json'
            '&observation_start={start}')
SHILLER = 'http://www.econ.yale.edu/~shiller/data/ie_data.xls'
MULTPL = 'https://www.multpl.com/shiller-pe/table/by-month'
# id: (label, unit, first date asked for)
FRED_SERIES = {
    'WALCL': ('Fed balance sheet (total assets)', '$ millions', '2002-12-01'),
    'WTREGEN': ('Treasury General Account', '$ millions', '2002-12-01'),
    'RRPONTSYD': ('Overnight reverse repo', '$ billions', '2003-01-01'),
    'BAMLH0A0HYM2': ('High-yield option-adjusted spread', '%', '1997-01-01'),
    'T10Y2Y': ('10-year minus 2-year Treasury', 'pts', '1990-01-01'),
    'DGS10': ('10-year Treasury yield', '%', '1990-01-01'),
    'DFII10': ('10-year real yield (TIPS)', '%', '2003-01-01'),
    'GDP': ('Gross domestic product (nominal, annual rate)', '$ billions', '1945-01-01'),
    'NCBEILQ027S': ('Corporate equities, market value (Fed Z.1, nonfinancial corporations)', '$ millions', '1945-01-01'),
    'SP500': ('S&P 500', 'index', '2010-01-01'),
}
SECTORS = {'technology': 'Technology', 'communication': 'Communication', 'consumer-disc': 'Consumer discretionary',
           'consumer-staples': 'Consumer staples', 'health': 'Health care', 'financials': 'Financials', 'industrials': 'Industrials',
           'energy': 'Energy', 'materials': 'Materials', 'utilities': 'Utilities', 'real-estate': 'Real estate', 'other': 'Other'}
NASDAQ_SECTOR = {'technology': 'technology', 'telecommunications': 'communication', 'consumer discretionary': 'consumer-disc',
                 'consumer staples': 'consumer-staples', 'health care': 'health', 'finance': 'financials', 'industrials': 'industrials',
                 'energy': 'energy', 'basic materials': 'materials', 'utilities': 'utilities', 'real estate': 'real-estate'}
GROUP_LABEL = {'f13': '13F managers', 'etf': 'Active ETFs', 'ins': 'Insiders', 'plan': "Insiders' 10b5-1 plans", 'gov': 'Officials'}
RATING_BANDS = ['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'CCC', 'NR']


# ------------------------------------------------------------------ small helpers
def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def read_json(path, default=None):
    p = Path(path)
    try:
        if p.suffix == '.gz':
            with gzip.open(p, 'rt', encoding='utf-8') as f:
                return json.load(f)
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')


def _r(v, n=4):
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return round(float(v), n)


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def canon(t):
    return (t or '').strip().upper().replace('.', '-').replace('/', '-')


def get(url, timeout=30, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return body if binary else body.decode('utf-8', 'replace')


def percentile_of(values, v):
    """Share of the history at or below v (0..1)."""
    xs = sorted(x for x in values if x is not None)
    if not xs or v is None:
        return None
    return bisect.bisect_right(xs, v) / len(xs)


def ols(xs, ys):
    """y = a + b·x: (a, b, r², residuals) or None when fewer than 8 points."""
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 8:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx <= 0:
        return None
    b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    a = my - b * mx
    res = [p[1] - (a + b * p[0]) for p in pts]
    syy = sum((p[1] - my) ** 2 for p in pts)
    r2 = 1 - sum(e * e for e in res) / syy if syy > 0 else None
    return a, b, r2, res


def quantile(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# ------------------------------------------------------------------ collect: FRED, Shiller, Nasdaq
def parse_fred_csv(text):
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        try:
            d = dt.date.fromisoformat(row[0].strip())
        except ValueError:
            continue
        v = row[1].strip()
        if v in ('', '.', 'NA'):
            continue
        try:
            out.append((d.isoformat(), float(v)))
        except ValueError:
            continue
    return out


def fetch_fred(root, ids=None, max_age_h=20, budget_s=240):
    folder = Path(root) / 'cache' / 'fred'
    folder.mkdir(parents=True, exist_ok=True)
    got, failed, t0 = [], [], time.time()
    key = os.environ.get('FRED_API_KEY', '').strip()
    for sid in ids or FRED_SERIES:
        p = folder / f'{sid}.csv'
        if p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
            continue
        if time.time() - t0 > budget_s:
            failed.append(f'{sid}: time budget used up')
            continue
        start = FRED_SERIES.get(sid, ('', '', '1990-01-01'))[2]
        for attempt in range(3):
            try:
                if key:
                    body = json.loads(get(FRED_API.format(id=sid, key=key, start=start), 40))
                    text = 'observation_date,' + sid + '\n' + '\n'.join(f"{o['date']},{o['value']}" for o in body.get('observations', []))
                else:
                    text = get(FRED.format(id=sid, start=start), 40)
                rows = parse_fred_csv(text)
                if len(rows) < 8:
                    raise ValueError(f'only {len(rows)} rows')
                p.write_text(text, encoding='utf-8')
                got.append(sid)
                break
            except Exception as exc:                    # keep the old file; the next run tries again
                if attempt == 2:
                    failed.append(f'{sid}: {type(exc).__name__} {str(exc)[:100]}')
                time.sleep(2 + 3 * attempt)
        time.sleep(0.4)
    return got, failed


def load_fred(root):
    out = {}
    for sid in FRED_SERIES:
        p = Path(root) / 'cache' / 'fred' / f'{sid}.csv'
        if p.exists():
            out[sid] = parse_fred_csv(p.read_text(encoding='utf-8'))
    return out


def _shiller_month(v):
    """Shiller's dates are floats: 1871.01 = January, 1871.1 = October (the trailing zero is lost)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    y = int(f)
    m = int(round((f - y) * 100))
    if m == 1 and abs((f - y) - 0.1) < 1e-6:
        m = 10
    if not 1 <= m <= 12:
        return None
    return f'{y:04d}-{m:02d}'


def parse_shiller_rows(rows):
    """Shiller's "Data" sheet as a list of rows (cells) → [{month, price, dividend, earnings, cpi, gs10, real_tr, cape}].
    The header row is found by its "Date" and "CAPE" cells; the real total-return price is the second "Price" column
    after "Rate GS10" (the first is the real price)."""
    head = None
    for i, r in enumerate(rows[:40]):
        cells = [str(c).strip() for c in r]
        if cells and cells[0] == 'Date' and any(c == 'CAPE' for c in cells):
            head = i
            break
    if head is None:
        raise ValueError('Shiller sheet: header row not found')
    H = [str(c).strip() for c in rows[head]]
    col = {'price': 1, 'dividend': 2, 'earnings': 3, 'cpi': 4}
    col['gs10'] = next(i for i, c in enumerate(H) if c.replace(' ', '').lower() == 'rategs10')
    prices = [i for i, c in enumerate(H) if c == 'Price' and i > col['gs10']]
    col['real_tr'] = prices[1] if len(prices) > 1 else None
    col['cape'] = H.index('CAPE')
    out = []
    for r in rows[head + 1:]:
        if not r:
            continue
        m = _shiller_month(r[0])
        if not m:
            continue
        rec = {'month': m}
        for k, c in col.items():
            rec[k] = _num(r[c]) if c is not None and c < len(r) else None
        if rec['price'] is None:
            continue
        out.append(rec)
    return out


def parse_multpl(html):
    """multpl.com's monthly Shiller P/E table → [{month, cape}] (the fallback: CAPE only, no returns)."""
    out = []
    for m in re.finditer(r'<td>\s*([A-Z][a-z]{2} \d{1,2}, \d{4})\s*</td>\s*<td>\s*(?:&#x2002;|\s)*([\d.]+)', html):
        try:
            d = dt.datetime.strptime(m.group(1), '%b %d, %Y').date()
        except ValueError:
            continue
        out.append({'month': f'{d.year:04d}-{d.month:02d}', 'cape': float(m.group(2))})
    return sorted({r['month']: r for r in out}.values(), key=lambda r: r['month'])


def fetch_shiller(root):
    """cache/shiller.json: Shiller's data (xlrd reads the .xls), else multpl.com's CAPE table."""
    p = Path(root) / 'cache' / 'shiller.json'
    old = read_json(p, {}) or {}
    if old.get('fetched_at', '') > (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=6)).isoformat():
        return 'cached'
    try:
        import xlrd                                       # pip install xlrd (the .xls format)
        book = xlrd.open_workbook(file_contents=get(SHILLER, 60, binary=True))
        sh = book.sheet_by_name('Data')
        rows = [sh.row_values(i) for i in range(sh.nrows)]
        recs = parse_shiller_rows(rows)
        if len(recs) < 1000:
            raise ValueError(f'only {len(recs)} months')
        write_json(p, {'fetched_at': now(), 'source': 'shiller', 'rows': recs})
        return f'shiller {len(recs)} months'
    except Exception as exc:
        err = f'{type(exc).__name__} {str(exc)[:120]}'
    try:
        recs = parse_multpl(get(MULTPL, 40))
        if len(recs) < 100:
            raise ValueError(f'only {len(recs)} months')
        if old.get('source') == 'shiller':                  # keep the fuller file; refresh its CAPE tail only
            byk = {r['month']: r for r in old['rows']}
            for r in recs:
                byk.setdefault(r['month'], {'month': r['month'], 'price': None})['cape'] = r['cape']
            write_json(p, {**old, 'rows': sorted(byk.values(), key=lambda r: r['month'])})
            return f'shiller kept, CAPE tail from multpl ({err})'
        write_json(p, {'fetched_at': now(), 'source': 'multpl', 'rows': recs})
        return f'multpl {len(recs)} months ({err})'
    except Exception as exc2:
        return f'failed: {err}; multpl {type(exc2).__name__} {str(exc2)[:80]}'


def fetch_nasdaq(root):
    """cache/nasdaq.json: one Nasdaq screener snapshot (pipeline/quotes.py parse_nasdaq), trimmed."""
    sys.path.insert(0, str(HERE.parents[1]))
    from pipeline import quotes                            # noqa: E402 (the repository root is on the path in the workflow)
    allq = quotes.nasdaq_all()
    rows = {t: [q.get('name'), q.get('mcap'), q.get('chg_pct'), q.get('price'), q.get('sector'), q.get('industry')]
            for t, q in allq.items() if q.get('mcap')}
    asof = next((q.get('asof') for q in allq.values() if q.get('asof')), None)
    write_json(Path(root) / 'cache' / 'nasdaq.json', {'fetched_at': now(), 'asof': asof,
                                                       'fields': ['name', 'mcap', 'chg_pct', 'price', 'sector', 'industry'], 'rows': rows})
    return len(rows)


def collect(root):
    root = Path(root)
    got, failed = fetch_fred(root)
    sh = fetch_shiller(root)
    try:
        nq = fetch_nasdaq(root)
    except Exception as exc:
        nq = f'failed: {type(exc).__name__} {str(exc)[:120]}'
    st = {'collected_at': now(), 'fred_updated': got, 'fred_failed': failed, 'shiller': sh, 'nasdaq': nq}
    write_json(root / 'cache' / 'collect.json', st)
    print(json.dumps(st))
    return st


# ------------------------------------------------------------------ sectors
def sector_map(consensus=None, debt=None, nasdaq=None):
    """ticker → sector slug: the consensus file's sector, then the debt module's, then Nasdaq's."""
    out = {}
    for src in (nasdaq, debt, consensus):                  # later sources win
        if not src:
            continue
        F = src.get('fields') or []
        if isinstance(src.get('rows'), dict):              # the Nasdaq snapshot: {ticker: [name, mcap, chg, price, sector, industry]}
            for t, r in src['rows'].items():
                s = NASDAQ_SECTOR.get(str(r[4] or '').strip().lower())
                if s:
                    out[canon(t)] = s
            continue
        if 'ticker' not in F or 'sector' not in F:
            continue
        it, isec = F.index('ticker'), F.index('sector')
        for r in src.get('rows') or []:
            if r[it] and r[isec] in SECTORS:
                out[canon(r[it])] = r[isec]
    return out


# ------------------------------------------------------------------ flows: groups → sectors → stocks
def build_flows(smart_dir, sectors, top=24):
    """Per period of smart money's combined flows: a Sankey of net buying (group → sector → stock) and one of net
    selling, with each group's and each sector's net dollars."""
    ix = read_json(Path(smart_dir) / 'combined' / 'index.json')
    if not ix:
        return None
    out = {'generated_at': now(), 'source': 'data/smart/combined (app/smart.py)', 'periods': []}
    for per in ix.get('periods') or []:
        d = read_json(Path(smart_dir) / 'combined' / f"{per['key']}.json")
        if not d or not d.get('rows'):
            continue
        F = d['fields']
        groups = [f[:-4] for f in F if f.endswith('_usd')]
        rows = [dict(zip(F, r)) for r in d['rows']]
        res = {'key': per['key'], 'label': per.get('label'), 'start': per.get('start'), 'end': per.get('end'), 'note': per.get('note', ''),
               'groups': [{'id': g, 'label': GROUP_LABEL.get(g, g), 'buy': 0.0, 'sell': 0.0} for g in groups]}
        G = {g['id']: g for g in res['groups']}
        sec_net, stock_net = {}, {}
        for side in ('buy', 'sell'):
            sign = 1 if side == 'buy' else -1
            gs, ss = {}, {}                                  # (group, sector) and (sector, stock) dollars on this side
            for r in rows:
                t = canon(r.get('ticker'))
                s = sectors.get(t, 'other')
                for g in groups:
                    v = (r.get(g + '_usd') or 0) * sign
                    if v <= 0:
                        continue
                    G[g][side] += v
                    gs[(g, s)] = gs.get((g, s), 0) + v
                    ss[(s, t)] = ss.get((s, t), 0) + v
            by_stock = {}
            for (s, t), v in ss.items():
                by_stock[t] = by_stock.get(t, 0) + v
            keep = set(sorted(by_stock, key=lambda t: -by_stock[t])[:top])
            links = [{'from': GROUP_LABEL.get(g, g), 'to': SECTORS.get(s, s), 'v': round(v)} for (g, s), v in sorted(gs.items(), key=lambda kv: -kv[1])]
            rest = {}
            for (s, t), v in ss.items():
                if t in keep:
                    links.append({'from': SECTORS.get(s, s), 'to': '$' + t.replace('-', '.'), 'v': round(v)})
                else:
                    rest[s] = rest.get(s, 0) + v
            links += [{'from': SECTORS.get(s, s), 'to': f'Other {SECTORS.get(s, s).lower()}', 'v': round(v)} for s, v in rest.items() if v > 0]
            res[side] = {'total': round(sum(v for v in by_stock.values())), 'links': links}
        for r in rows:
            t = canon(r.get('ticker'))
            net = sum(r.get(g + '_usd') or 0 for g in groups)
            s = sectors.get(t, 'other')
            sec_net[s] = sec_net.get(s, 0) + net
            stock_net[t] = (net, r.get('name'))
        for g in res['groups']:
            g['buy'], g['sell'] = round(g['buy']), round(g['sell'])
            g['net'] = g['buy'] - g['sell']
        res['sectors'] = sorted([{'id': s, 'label': SECTORS.get(s, s), 'net': round(v)} for s, v in sec_net.items()], key=lambda x: -x['net'])
        ranked = sorted(stock_net.items(), key=lambda kv: -kv[1][0])
        res['top_in'] = [{'ticker': t, 'name': n, 'net': round(v)} for t, (v, n) in ranked[:10] if v > 0]
        res['top_out'] = [{'ticker': t, 'name': n, 'net': round(v)} for t, (v, n) in ranked[::-1][:10] if v < 0]
        out['periods'].append(res)
    return out


# ------------------------------------------------------------------ the watched managers' portfolios
def _positions(shard, cusips):
    """A 13F snapshot's long equity positions by ticker (options and unmapped CUSIPs set apart)."""
    pos, options, unmapped = {}, 0.0, 0.0
    for r in shard or []:
        v = r.get('value_usd') or 0
        if str(r.get('put_call') or '').upper() in ('PUT', 'CALL'):
            options += v
            continue
        if (r.get('share_type') or 'SH') != 'SH':
            continue
        t = r.get('ticker') or cusips.get(str(r.get('cusip') or '').upper())
        if not t:
            unmapped += v
            key = '#' + str(r.get('cusip') or r.get('issuer'))
            p = pos.setdefault(key, {'ticker': None, 'issuer': r.get('issuer'), 'usd': 0.0, 'shares': 0.0})
        else:
            t = canon(t)
            p = pos.setdefault(t, {'ticker': t, 'issuer': r.get('issuer'), 'usd': 0.0, 'shares': 0.0})
        p['usd'] += v
        p['shares'] += r.get('shares') or 0
    return pos, options, unmapped


def _thousands(snap, pos, opt, unm):
    """1000 when a snapshot's positions were read in thousands of dollars (its stated total is ~1000× their sum), else 1."""
    tot = sum(p['usd'] for p in pos.values()) + opt + unm
    stated = snap.get('total_usd') or 0
    return 1000 if tot and 500 < stated / tot < 2000 else 1


def build_managers(hub_dir, sectors, max_quarters=8, race_top=10):
    """Each watched manager (market/watchlist.json): the last quarter's portfolio by sector against the quarter before,
    and the top holdings quarter by quarter."""
    hub = Path(hub_dir)
    wl = read_json(hub / 'market' / 'watchlist.json', {}) or {}
    cusips = {str(k).upper(): v for k, v in (read_json(hub / 'market' / 'cusip-tickers.json', {}) or {}).items()}
    out = {'generated_at': now(), 'managers': []}
    for f in wl.get('funds') or []:
        cik = str(f.get('cik'))
        summ = read_json(hub / 'shards' / 'holdings' / f'{cik}.json', {}) or {}
        snaps = sorted([s for s in summ.get('snapshots') or [] if s.get('positions_shard')], key=lambda s: s['period'])[-max_quarters:]
        quarters = []
        for s in snaps:
            sh = read_json(hub / s['positions_shard'])
            if sh is None:
                continue
            pos, opt, unm = _positions(sh, cusips)
            k = _thousands(s, pos, opt, unm)
            if k != 1:
                for p in pos.values():
                    p['usd'] *= k
                opt, unm = opt * k, unm * k
            quarters.append({'period': s['period'], 'filed': s.get('filed'), 'pos': pos, 'options': opt, 'unmapped': unm})
        if not quarters:
            continue
        cur = quarters[-1]
        prev = quarters[-2] if len(quarters) > 1 else None
        tot = sum(p['usd'] for p in cur['pos'].values()) or 1
        ptot = sum(p['usd'] for p in prev['pos'].values()) if prev else 0
        secs = {}
        keys = set(cur['pos']) | (set(prev['pos']) if prev else set())
        for k in keys:
            a = cur['pos'].get(k)
            b = prev['pos'].get(k) if prev else None
            src = a or b
            s = sectors.get(src['ticker'] or '', 'other')
            usd, pusd = (a or {}).get('usd', 0.0), (b or {}).get('usd', 0.0)
            sh, psh = (a or {}).get('shares', 0.0), (b or {}).get('shares', 0.0)
            status = ('new' if not b else 'exited' if not a else 'added' if sh > psh * 1.005 else 'cut' if sh < psh * 0.995 else 'same') if prev else 'held'
            e = secs.setdefault(s, {'id': s, 'label': SECTORS.get(s, s), 'usd': 0.0, 'prev_usd': 0.0, 'positions': []})
            e['usd'] += usd
            e['prev_usd'] += pusd
            e['positions'].append({'ticker': src['ticker'], 'issuer': src['issuer'], 'usd': round(usd), 'prev_usd': round(pusd),
                                   'shares_chg': _r(sh / psh - 1, 4) if psh else None, 'status': status})
        for e in secs.values():
            e['positions'].sort(key=lambda p: -max(p['usd'], p['prev_usd']))
            e['w'] = _r(e['usd'] / tot, 4)
            e['prev_w'] = _r(e['prev_usd'] / ptot, 4) if ptot else None
            e['usd'], e['prev_usd'] = round(e['usd']), round(e['prev_usd'])
        race = []
        for q in quarters:
            qt = sum(p['usd'] for p in q['pos'].values()) or 1
            top = sorted((p for p in q['pos'].values() if p['ticker']), key=lambda p: -p['usd'])[:race_top]
            race.append({'period': q['period'], 'total': round(qt), 'top': [[p['ticker'], round(p['usd']), _r(p['usd'] / qt, 4)] for p in top]})
        out['managers'].append({'cik': cik, 'name': f.get('name') or summ.get('label'), 'filer': f.get('filer') or summ.get('name'),
                                'period': cur['period'], 'filed': cur['filed'], 'prev_period': prev['period'] if prev else None,
                                'total': round(tot), 'prev_total': round(ptot) if prev else None, 'options_usd': round(cur['options']),
                                'unmapped_usd': round(cur['unmapped']), 'positions': len(cur['pos']),
                                'sectors': sorted(secs.values(), key=lambda e: -e['usd']), 'race': race})
    # all watched managers together, quarter by quarter (a period counts once most of them have filed it)
    out['combined_race'] = combined_race(hub, wl, cusips, race_top + 5)
    return out


def combined_race(hub, wl, cusips, top):
    """The watched managers' summed long positions per quarter (all of their positions, not just each top ten)."""
    per = {}
    for f in wl.get('funds') or []:
        summ = read_json(hub / 'shards' / 'holdings' / f"{f.get('cik')}.json", {}) or {}
        for s in summ.get('snapshots') or []:
            if not s.get('positions_shard'):
                continue
            sh = read_json(hub / s['positions_shard'])
            if sh is None:
                continue
            pos, o, u = _positions(sh, cusips)
            k = _thousands(s, pos, o, u)
            d = per.setdefault(s['period'], {'managers': 0, 'pos': {}})
            d['managers'] += 1
            for key, p in pos.items():
                if p['ticker']:
                    d['pos'][key] = d['pos'].get(key, 0) + p['usd'] * k
    n = len(wl.get('funds') or [])
    out = []
    for period in sorted(per):
        d = per[period]
        if n and d['managers'] < max(2, n // 2):
            continue
        tot = sum(d['pos'].values()) or 1
        out.append({'period': period, 'managers': d['managers'], 'total': round(tot),
                    'top': [[t, round(v), _r(v / tot, 4)] for t, v in sorted(d['pos'].items(), key=lambda kv: -kv[1])[:top]]})
    return out


# ------------------------------------------------------------------ heatmap (squarified treemap)
def squarify(values, x, y, w, h):
    """Squarified treemap (Bruls, Huizing, van Wijk): rectangles [x, y, w, h] for positive values sorted descending."""
    out = [None] * len(values)
    idx = [i for i in sorted(range(len(values)), key=lambda i: -values[i]) if values[i] > 0]
    total = sum(values[i] for i in idx)
    if total <= 0 or w <= 0 or h <= 0:
        return out
    scale = w * h / total
    areas = {i: values[i] * scale for i in idx}

    def worst(row, side):
        s = sum(areas[i] for i in row)
        return max(max(side * side * areas[i] / (s * s), (s * s) / (side * side * areas[i])) for i in row)

    rest = idx[:]
    while rest:
        side = min(w, h)
        row = [rest.pop(0)]
        while rest and worst(row + [rest[0]], side) <= worst(row, side):
            row.append(rest.pop(0))
        s = sum(areas[i] for i in row)
        if w >= h:                                             # a column on the left
            cw = s / h if h else 0
            yy = y
            for i in row:
                hh = areas[i] / cw if cw else 0
                out[i] = [x, yy, cw, hh]
                yy += hh
            x, w = x + cw, w - cw
        else:                                                  # a row on top
            rh = s / w if w else 0
            xx = x
            for i in row:
                ww = areas[i] / rh if rh else 0
                out[i] = [xx, y, ww, rh]
                xx += ww
            y, h = y + rh, h - rh
    return out


def build_heatmap(nasdaq, sectors, extremes=None, smart_index=None, shorts=None, consensus=None, top=400):
    """The largest stocks as a treemap grouped by sector (layout in a 1000 × 620 box) with their colour metrics."""
    if not nasdaq or not nasdaq.get('rows'):
        return None
    ext = {}
    if extremes and extremes.get('fields'):
        F = extremes['fields']
        for r in extremes.get('rows') or []:
            e = dict(zip(F, r))
            lo, hi, c = e.get('lo52'), e.get('hi52'), e.get('close')
            ext[canon(e['ticker'])] = {'pos52': _r((c - lo) / (hi - lo), 3) if lo is not None and hi and c is not None and hi > lo else None,
                                       'ytd': e.get('ytd')}
    sm = {}
    if smart_index and smart_index.get('stock_fields'):
        F = smart_index['stock_fields']
        for r in smart_index.get('stocks') or []:
            e = dict(zip(F, r))
            sm[canon(e.get('ticker'))] = e.get('S')
    si = {canon(r.get('ticker')): r.get('change_pct') for r in (shorts or {}).get('rows') or []}
    cons = {}
    if consensus and consensus.get('fields'):
        F = consensus['fields']
        for r in consensus.get('rows') or []:
            e = dict(zip(F, r))
            up = e['target_mean'] / e['price'] - 1 if e.get('target_mean') and e.get('price') else None
            cons[canon(e.get('ticker'))] = (up, e.get('beat_rate'))
    F = nasdaq['fields']
    rows = []
    for t, r in nasdaq['rows'].items():
        q = dict(zip(F, r))
        t = canon(t)
        if not q.get('mcap') or re.search(r'\^|\$|-W$|-U$|-R$|-P[A-Z]?$', t):
            continue
        rows.append((t, q))
    rows.sort(key=lambda tq: -tq[1]['mcap'])
    rows = rows[:top]
    by_sec = {}
    for t, q in rows:
        by_sec.setdefault(sectors.get(t) or NASDAQ_SECTOR.get(str(q.get('sector') or '').lower()) or 'other', []).append((t, q))
    secs = sorted(by_sec.items(), key=lambda kv: -sum(q['mcap'] for _, q in kv[1]))
    W, H = 1000.0, 620.0
    srects = squarify([sum(q['mcap'] for _, q in v) for _, v in secs], 0, 0, W, H)
    out_secs, cells = [], []
    for (s, items), sr in zip(secs, srects):
        if not sr:
            continue
        pad = 1.0
        head = 14.0 if sr[3] > 40 and sr[2] > 60 else 0.0
        crects = squarify([q['mcap'] for _, q in items], sr[0] + pad, sr[1] + head + pad, max(0, sr[2] - 2 * pad), max(0, sr[3] - head - 2 * pad))
        mc = sum(q['mcap'] for _, q in items)
        chg = sum((q.get('chg_pct') or 0) * q['mcap'] for _, q in items) / mc if mc else None
        out_secs.append({'id': s, 'label': SECTORS.get(s, s), 'rect': [round(v, 1) for v in sr], 'mcap': round(mc), 'chg': _r(chg, 3)})
        for (t, q), cr in zip(items, crects):
            if not cr:
                continue
            up, br = cons.get(t, (None, None))
            cells.append([t, (q.get('name') or '')[:40], s, round(q['mcap']), [round(v, 1) for v in cr], _r(q.get('chg_pct'), 3),
                          (ext.get(t) or {}).get('pos52'), _r(sm.get(t), 1), _r(br, 3), _r(si.get(t), 2), _r(up, 4)])
    return {'generated_at': now(), 'asof': nasdaq.get('asof'), 'box': [W, H], 'sectors': out_secs,
            'fields': ['ticker', 'name', 'sector', 'mcap', 'rect', 'chg', 'pos52', 'smart', 'beat_rate', 'si_chg', 'pt_upside'],
            'metrics': [['chg', "Day's move (%)", 'diverging', 3], ['pos52', '52-week position (0 = low, 1 = high)', 'diverging-mid', 0.5],
                        ['smart', 'Smart-money score (−100 … +100)', 'diverging', 60], ['beat_rate', 'EPS beat rate, last 8 reports', 'diverging-mid', 0.5],
                        ['si_chg', 'Short-interest change since the previous report (%)', 'diverging-inv', 25],
                        ['pt_upside', "Analysts' mean target vs price", 'diverging', 0.3]],
            'cells': cells,
            'note': ('Size: market value from the Nasdaq screener (delayed); grouped by sector. Colours: the day\'s move, where the close sits '
                     'in its 52-week range, the smart-money score, the share of the last 8 reports that beat the EPS consensus, the change in '
                     'short interest (FINRA, twice a month) and the analysts\' mean target against the price. Not investment advice.')}


# ------------------------------------------------------------------ ownership network and crowding
def force_layout(nodes, edges, iters=300, seed=7):
    """Fruchterman–Reingold in a unit square (deterministic). nodes: [id]; edges: [(i, j, weight)]. → [[x, y]]"""
    rnd = random.Random(seed)
    n = len(nodes)
    if not n:
        return []
    pos = [[rnd.random(), rnd.random()] for _ in range(n)]
    k = math.sqrt(1.0 / n)
    t = 0.1
    for it in range(iters):
        disp = [[0.0, 0.0] for _ in range(n)]
        for i in range(n):
            xi, yi = pos[i]
            for j in range(i + 1, n):
                dx, dy = xi - pos[j][0], yi - pos[j][1]
                d2 = dx * dx + dy * dy + 1e-9
                f = k * k / d2
                disp[i][0] += dx * f
                disp[i][1] += dy * f
                disp[j][0] -= dx * f
                disp[j][1] -= dy * f
        for i, j, w in edges:
            dx, dy = pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]
            d = math.sqrt(dx * dx + dy * dy) + 1e-9
            f = d * d / k * (0.5 + min(w, 1.0))
            disp[i][0] -= dx / d * f
            disp[i][1] -= dy / d * f
            disp[j][0] += dx / d * f
            disp[j][1] += dy / d * f
        for i in range(n):
            dx, dy = disp[i]
            d = math.sqrt(dx * dx + dy * dy) + 1e-9
            pos[i][0] += dx / d * min(d, t)
            pos[i][1] += dy / d * min(d, t)
            pos[i][0] = min(1.0, max(0.0, pos[i][0]))
            pos[i][1] = min(1.0, max(0.0, pos[i][1]))
        t = max(0.002, t * 0.985)
    xs, ys = [p[0] for p in pos], [p[1] for p in pos]
    sx, sy = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
    return [[round((p[0] - min(xs)) / sx, 4), round((p[1] - min(ys)) / sy, 4)] for p in pos]


def crowding(holders_by_stock, n_managers):
    """Per stock: holders among the watched managers, their summed portfolio weight and the concentration (HHI of the
    holders' dollars) → a 0..100 index (half breadth, a quarter weight, a quarter concentration of its holder base)."""
    out = {}
    for t, hs in holders_by_stock.items():
        k = len(hs)
        wsum = sum(h['w'] for h in hs)
        tot = sum(h['usd'] for h in hs) or 1
        hhi = sum((h['usd'] / tot) ** 2 for h in hs)
        breadth = k / n_managers if n_managers else 0
        idx = 100 * (0.5 * breadth + 0.25 * min(1.0, wsum / 0.5) + 0.25 * (1 - hhi if k > 1 else 0))
        out[t] = {'holders': k, 'weight_sum': _r(wsum, 4), 'hhi': _r(hhi, 3), 'index': _r(idx, 1)}
    return out


def _close_on(rows, day):
    """The last close on or before day from [(date, close, volume)] rows."""
    i = bisect.bisect_right([r[0] for r in rows], day) - 1
    return rows[i][1] if i >= 0 else None


def build_network(managers, prices_dir=None, min_holders=2, max_stocks=70):
    """The watched managers and the stocks at least two of them hold (latest quarter), a force layout, the crowding index
    per stock and its change, and a walk-forward check: from 46 days after each quarter end (the 13F deadline), how the
    crowded names (held by 3 or more) did over the next 63 trading days against the ones only one manager held."""
    mans = managers.get('managers') or []
    if not mans:
        return None
    n = len(mans)
    # the latest quarter's full holder lists (positions, not only each top ten)
    hb = {}
    for m in mans:
        for e in m['sectors']:
            for p in e['positions']:
                if p['ticker'] and p['usd'] > 0:
                    hb.setdefault(p['ticker'], []).append({'cik': m['cik'], 'usd': p['usd'], 'w': p['usd'] / (m['total'] or 1),
                                                           'prev': p['prev_usd'] > 0})
    crowd = crowding(hb, n)
    for t, c in crowd.items():
        c['new_holders'] = sum(1 for h in hb[t] if not h['prev'])
    shared = sorted([t for t in hb if len(hb[t]) >= min_holders], key=lambda t: (-len(hb[t]), -sum(h['usd'] for h in hb[t])))[:max_stocks]
    nodes = [{'id': 'm:' + m['cik'], 'kind': 'manager', 'label': m['name'], 'size': m['total']} for m in mans]
    nodes += [{'id': 's:' + t, 'kind': 'stock', 'label': t, 'size': sum(h['usd'] for h in hb[t]), **crowd[t]} for t in shared]
    idx = {nd['id']: i for i, nd in enumerate(nodes)}
    edges = []
    for t in shared:
        for h in hb[t]:
            edges.append((idx['m:' + h['cik']], idx['s:' + t], h['w']))
    xy = force_layout([nd['id'] for nd in nodes], edges)
    for nd, p in zip(nodes, xy):
        nd['x'], nd['y'] = p
    # walk-forward: each quarter's crowded set against the single-holder names, priced from the hub's cache
    check = []
    if prices_dir and Path(prices_dir).is_dir():
        periods = sorted({q['period'] for m in mans for q in m['race']})
        for per in periods:
            hbq = {}
            for m in mans:
                q = next((x for x in m['race'] if x['period'] == per), None)
                for t, usd, w in (q or {}).get('top') or []:
                    hbq.setdefault(t, set()).add(m['cik'])
            if not hbq:
                continue
            start = (dt.date.fromisoformat(per) + dt.timedelta(days=46)).isoformat()
            rets = {}
            for t in hbq:
                pr = read_json(Path(prices_dir) / f'{t}.json.gz') or {}
                rows = [r for r in pr.get('rows') or [] if len(r) > 1 and r[1]]
                i0 = bisect.bisect_left([r[0] for r in rows], start)
                if i0 >= len(rows) or i0 + 63 >= len(rows):
                    continue
                rets[t] = rows[i0 + 63][1] / rows[i0][1] - 1
            crowded = [rets[t] for t in rets if len(hbq[t]) >= 3]
            single = [rets[t] for t in rets if len(hbq[t]) == 1]
            if len(crowded) >= 3 and len(single) >= 5:
                c, s = sum(crowded) / len(crowded), sum(single) / len(single)
                check.append({'period': per, 'from': start, 'crowded_n': len(crowded), 'single_n': len(single),
                              'crowded_ret': _r(c, 4), 'single_ret': _r(s, 4), 'spread': _r(c - s, 4)})
    spreads = [c['spread'] for c in check]
    return {'generated_at': now(), 'managers': n, 'nodes': nodes, 'edges': [[i, j, _r(w, 4)] for i, j, w in edges],
            'crowding': sorted([{'ticker': t, **c} for t, c in crowd.items() if c['holders'] >= 2], key=lambda r: -r['index'])[:60],
            'check': {'quarters': check, 'mean_spread': _r(sum(spreads) / len(spreads), 4) if spreads else None,
                      'hit_rate': _r(sum(1 for s in spreads if s > 0) / len(spreads), 3) if spreads else None,
                      'note': ('Crowded = held by 3 or more of the watched managers in that quarter\'s top ten, against names only one of them '
                               'held; returns over the 63 trading days from the 13F deadline (quarter end + 46 days), prices from the hub\'s '
                               'cache. A handful of quarters: read it as a description, not a tested signal.')},
            'note': ('Watched managers (the hub\'s 13F watchlist) and the stocks at least two of them hold in their latest 13F. Crowding index '
                     '(0–100): half how many of the managers hold it, a quarter their summed portfolio weight, a quarter how evenly the '
                     'holding is spread among them.')}


# ------------------------------------------------------------------ debt maturity wall
def build_maturity(debt_dir, today=None, years=10):
    """What falls due each year (face, else carrying value of each instrument; undrawn facilities left out) by the
    company's rating band, market-wide, and each company's own wall."""
    debt_dir = Path(debt_dir)
    ix = read_json(debt_dir / 'index.json')
    if not ix:
        return None
    today = today or dt.date.today()
    y0 = today.year
    F = ix['fields']
    band = {}
    for r in ix.get('rows') or []:
        e = dict(zip(F, r))
        band[str(e['cik'])] = (e.get('rating_band') or 'NR', e.get('ticker'), e.get('name'), e.get('sector'))
    wall = {b: [0.0] * (years + 2) for b in RATING_BANDS}       # past due / this year … +years, later
    by_co, n = {}, 0
    for p in sorted((debt_dir / 'c').glob('*.json')) if (debt_dir / 'c').is_dir() else []:
        d = read_json(p)
        if not d:
            continue
        b, tk, name, sec = band.get(str(d.get('cik')), ('NR', d.get('ticker'), d.get('name'), d.get('sector')))
        b = b if b in RATING_BANDS else ('NR' if not b else next((x for x in RATING_BANDS if str(b).startswith(x)), 'NR'))
        mine = {}
        for ins in d.get('instruments') or []:
            amt = ins.get('face') or ins.get('carrying')
            if ins.get('kind') == 'revolver':
                amt = ins.get('carrying')                       # only what is drawn
            mat = str(ins.get('maturity') or '')[:4]
            if not amt or amt <= 0 or not mat.isdigit():
                continue
            yr = int(mat)
            k = 0 if yr <= y0 else min(years + 1, yr - y0)
            wall[b][k] += amt
            mine[yr] = mine.get(yr, 0) + amt
        if mine:
            n += 1
            by_co[tk or str(d.get('cik'))] = {'name': name, 'band': b, 'sector': sec,
                                             'wall': [[y, round(v)] for y, v in sorted(mine.items())]}
    labels = [f'{y0} (incl. past due)'] + [str(y0 + i) for i in range(1, years + 1)] + [f'after {y0 + years}']
    totals = [sum(wall[b][i] for b in RATING_BANDS) for i in range(years + 2)]
    nxt = sorted(((tk, sum(v for y, v in c['wall'] if y == y0 + 1), c) for tk, c in by_co.items()), key=lambda x: -x[1])
    return {'generated_at': now(), 'asof_year': y0, 'companies': n, 'labels': labels, 'bands': RATING_BANDS,
            'wall': {b: [round(v) for v in wall[b]] for b in RATING_BANDS}, 'totals': [round(v) for v in totals],
            'next_year_top': [{'ticker': tk, 'name': c['name'], 'band': c['band'], 'usd': round(v)} for tk, v, c in nxt[:15] if v > 0],
            'by_company': by_co,
            'note': ('Each company\'s debt instruments as read from its latest 10-K / 10-Q (app/debt.py): face value, else carrying value, '
                     'by stated maturity; revolvers count only what is drawn. Rating band: the debt module\'s band for the issuer (implied '
                     'from its fundamentals and spreads where there is no agency rating; NR when neither). Coverage grows as the debt '
                     'module reads more companies — a total over the companies read, not the whole market.')}


# ------------------------------------------------------------------ valuation thermometer
def _months_add(m, k):
    y, mo = int(m[:4]), int(m[5:7])
    t = y * 12 + (mo - 1) + k
    return f'{t // 12:04d}-{t % 12 + 1:02d}'


def forward_real_return(sh, months=120):
    """month → annualised real total return over the next `months` (Shiller's real total-return price)."""
    tr = {r['month']: r.get('real_tr') for r in sh if r.get('real_tr')}
    out = {}
    for m, v in tr.items():
        w = tr.get(_months_add(m, months))
        if w and v:
            out[m] = (w / v) ** (12 / months) - 1
    return out


def _gauge(label, value, history, fit_x=None, fit_y=None, unit='', note='', invert=False, transform=None):
    """A gauge: value, percentile against its history, and the OLS fit of the next ten years' real return on it."""
    hist_vals = [v for _, v in history]
    g = {'label': label, 'value': _r(value, 4), 'unit': unit, 'percentile': _r(percentile_of(hist_vals, value), 3),
         'history_from': history[0][0] if history else None, 'history_n': len(history),
         'median': _r(quantile(hist_vals, 0.5), 4), 'series': [[d, _r(v, 4)] for d, v in history[-400:]], 'note': note}
    if fit_x is not None and value is not None:
        tf = transform or (lambda x: x)
        fit = ols([tf(x) for x in fit_x], fit_y)
        if fit:
            a, b, r2, res = fit
            mid = a + b * tf(value)
            g['fit'] = {'n': len(res), 'r2': _r(r2, 3), 'next10y_real': _r(mid, 4),
                        'lo80': _r(mid + quantile(res, 0.1), 4), 'hi80': _r(mid + quantile(res, 0.9), 4)}
    return g


def build_thermometer(root, consensus_market=None, today=None):
    root = Path(root)
    fred = load_fred(root)
    sh_doc = read_json(root / 'cache' / 'shiller.json', {}) or {}
    sh = sh_doc.get('rows') or []
    fwd = forward_real_return(sh) if sh_doc.get('source') == 'shiller' else {}
    gauges = {}
    # Shiller CAPE
    cape = [(r['month'], r['cape']) for r in sh if r.get('cape')]
    if cape:
        xs = [v for m, v in cape if m in fwd]
        ys = [fwd[m] for m, v in cape if m in fwd]
        gauges['cape'] = _gauge('Shiller CAPE (price / 10-year average real earnings)', cape[-1][1], cape, xs or None, ys or None,
                                note=f"Robert Shiller's monthly S&P data since {cape[0][0][:4]}; the fit regresses the next ten years' annualised real "
                                     "total return on the earnings yield 1/CAPE (overlapping ten-year windows: the r² flatters it).",
                                transform=lambda x: 1 / x)
        gauges['cape']['asof'] = cape[-1][0]
    # excess CAPE yield: 1/CAPE − (10-year yield − the last ten years' inflation)
    ecy = []
    cpi = {r['month']: r.get('cpi') for r in sh if r.get('cpi')}
    for r in sh:
        if not r.get('cape') or r.get('gs10') is None:
            continue
        c0 = cpi.get(_months_add(r['month'], -120))
        c1 = cpi.get(r['month'])
        if not c0 or not c1:
            continue
        infl = (c1 / c0) ** (1 / 10) - 1
        ecy.append((r['month'], 1 / r['cape'] - (r['gs10'] / 100 - infl)))
    if ecy:
        xs = [v for m, v in ecy if m in fwd]
        ys = [fwd[m] for m, v in ecy if m in fwd]
        gauges['ecy'] = _gauge('Excess CAPE yield (a proxy for the equity risk premium)', ecy[-1][1], ecy, xs or None, ys or None, unit='%',
                               note='1 / CAPE minus the real 10-year yield (the 10-year Treasury yield less the last ten years\' CPI inflation), '
                                    'as Shiller defines it. Higher = stocks cheaper against bonds.')
        gauges['ecy']['asof'] = ecy[-1][0]
    # Buffett indicator: the Fed's Z.1 market value of corporate equities / GDP, brought forward with the S&P 500
    eq, gdp, spx = fred.get('NCBEILQ027S') or [], fred.get('GDP') or [], fred.get('SP500') or []
    if eq and gdp:
        gq = {d[:7]: v for d, v in gdp}
        bi = [(d, (v / 1000) / gq[d[:7]]) for d, v in eq if d[:7] in gq and gq[d[:7]]]
        if bi:
            last_d, last_v = bi[-1]
            cur, cur_note, cur_d = last_v, f'Z.1 value for the quarter starting {last_d}', last_d
            if spx:
                q_end = (dt.date.fromisoformat(last_d) + dt.timedelta(days=92)).replace(day=1) - dt.timedelta(days=1)
                base = _close_on(spx, q_end.isoformat())
                if base:
                    cur = last_v * spx[-1][1] / base
                    cur_note = (f'Z.1 value for the quarter starting {last_d} ({last_v:.2f}x GDP), carried to {spx[-1][0]} with the S&P 500 '
                                f'({spx[-1][1]:,.0f} against {base:,.0f}); GDP held at its latest estimate')
                    cur_d = spx[-1][0]
            fx, fy = [], []
            for d, v in bi:
                m = _months_add(d[:7], 2)                         # the quarter's last month
                if m in fwd:
                    fx.append(v)
                    fy.append(fwd[m])
            gauges['buffett'] = _gauge('Buffett indicator (market value of US corporate equities / GDP)', cur, bi, fx or None, fy or None, unit='x',
                                       note=cur_note + '. Fit: the next ten years\' real total return of the S&P 500 (Shiller) on the ratio.')
            gauges['buffett']['asof'] = cur_d
    # forward P/E of the S&P 500 (bottom-up analysts' consensus, app/consensus.py) with the snapshots kept here
    hist_p = root / 'cache' / 'fwd_pe.json'
    hist = read_json(hist_p, []) or []
    spx_c = next((i for i in (consensus_market or {}).get('indices') or [] if i.get('id') == 'spx'), None)
    if spx_c and spx_c.get('fwd_pe'):
        day = spx_c.get('as_of') or (today or dt.date.today()).isoformat()
        hist = [h for h in hist if h[0] != day] + [[day, spx_c['fwd_pe']]]
        hist.sort()
        write_json(hist_p, hist)
    if hist:
        gauges['fwd_pe'] = _gauge('S&P 500 forward P/E (analysts\' next-twelve-months earnings)', hist[-1][1], [tuple(h) for h in hist], unit='x',
                                  note=f'Bottom-up consensus of the index members (Consensus tab); history kept since {hist[0][0]} — the percentile '
                                       'needs a few years of snapshots before it means much.')
        gauges['fwd_pe']['asof'] = hist[-1][0]
    if not gauges:
        return None
    return {'generated_at': now(), 'gauges': gauges, 'shiller_source': sh_doc.get('source'),
            'note': ('Each gauge with its percentile against its own history and, where the history reaches far enough, an ordinary '
                     'least-squares fit of the following ten years\' real total return of the S&P 500 on it (80% range from the fit\'s '
                     'residuals). Ten-year windows overlap, so the effective sample is small: a description of the past, not a forecast. '
                     'Not investment advice.')}


# ------------------------------------------------------------------ liquidity
def weekly(series, days):
    """The value known on each day of `days` (last observation on or before it)."""
    ds = [d for d, _ in series]
    out = []
    for day in days:
        i = bisect.bisect_right(ds, day) - 1
        out.append(series[i][1] if i >= 0 else None)
    return out


def build_liquidity(root, since='2015-01-07'):
    fred = load_fred(root)
    wal, tga, rrp = fred.get('WALCL') or [], fred.get('WTREGEN') or [], fred.get('RRPONTSYD') or []
    if not wal or not tga:
        return None
    d = dt.date.fromisoformat(since)
    while d.weekday() != 2:                                    # Wednesdays: the H.4.1 week
        d += dt.timedelta(days=1)
    last = max(wal[-1][0], tga[-1][0])
    days = []
    while d.isoformat() <= last:
        days.append(d.isoformat())
        d += dt.timedelta(days=7)
    W, T = weekly(wal, days), weekly(tga, days)
    R = weekly(rrp, days) if rrp else [0.0] * len(days)
    HY, CV, SP = weekly(fred.get('BAMLH0A0HYM2') or [], days), weekly(fred.get('T10Y2Y') or [], days), weekly(fred.get('SP500') or [], days)
    rows = []
    for i, day in enumerate(days):
        if W[i] is None or T[i] is None:
            continue
        net = W[i] / 1000 - T[i] / 1000 - (R[i] or 0)          # $ billions (WALCL, WTREGEN in millions; RRP in billions)
        rows.append([day, _r(net, 1), _r(W[i] / 1000, 1), _r(T[i] / 1000, 1), _r(R[i] or 0, 1), _r(HY[i], 2), _r(CV[i], 2), _r(SP[i], 2)])
    if len(rows) < 6:
        return None
    net = [r[1] for r in rows]
    chg = lambda k: _r(net[-1] - net[-1 - k], 1) if len(net) > k else None
    # how the 13-week change in net liquidity and the S&P 500's 13-week return moved together
    pairs = [(rows[i][1] - rows[i - 13][1], rows[i][7] / rows[i - 13][7] - 1) for i in range(13, len(rows))
             if rows[i][7] and rows[i - 13][7]]
    corr = None
    if len(pairs) > 20:
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        sy = math.sqrt(sum((y - my) ** 2 for y in ys))
        corr = _r(sum((x - mx) * (y - my) for x, y in pairs) / (sx * sy), 3) if sx and sy else None
    last_r = rows[-1]
    return {'generated_at': now(), 'fields': ['week', 'net', 'fed', 'tga', 'rrp', 'hy_spread', 'curve_10y2y', 'spx'], 'rows': rows,
            'latest': {'week': last_r[0], 'net': last_r[1], 'chg_1w': chg(1), 'chg_4w': chg(4), 'chg_13w': chg(13), 'chg_52w': chg(52),
                       'fed': last_r[2], 'tga': last_r[3], 'rrp': last_r[4], 'hy_spread': last_r[5], 'curve': last_r[6],
                       'hy_chg_4w': _r(last_r[5] - rows[-5][5], 2) if len(rows) > 4 and last_r[5] is not None and rows[-5][5] is not None else None,
                       'pctile_net': _r(percentile_of(net, last_r[1]), 3)},
            'corr_13w_spx': corr,
            'note': ('Net liquidity = the Fed\'s total assets (H.4.1, WALCL) minus the Treasury General Account (WTREGEN) minus the overnight '
                     'reverse repo (RRPONTSYD), in $ billions, each Wednesday since 2015; with the ICE BofA high-yield spread and the '
                     '10-year minus 2-year curve (FRED). The correlation of 13-week changes with the S&P 500 is descriptive, overlapping '
                     'windows, not a forecast.')}


# ------------------------------------------------------------------ images for the X posts (PIL only)
BG, INK, MUTED = (243, 242, 238), (29, 29, 27), (107, 106, 102)


def _font(size, bold=True):
    from PIL import ImageFont
    for name in (("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf") if bold else ("DejaVuSans.ttf", "LiberationSans-Regular.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _diverge(v, span):
    """Red ↔ grey ↔ green for a value in [−span, span]."""
    if v is None:
        return (205, 203, 197)
    x = max(-1.0, min(1.0, v / span)) if span else 0
    grey = (190, 188, 182)
    end = (23, 115, 74) if x > 0 else (234, 106, 82)
    a = abs(x)
    return tuple(round(grey[i] + (end[i] - grey[i]) * a) for i in range(3))


def render_heatmap_png(hm, path, width=1600):
    from PIL import Image, ImageDraw
    W, H = hm['box']
    s = width / W
    img = Image.new('RGB', (width, round(H * s) + 100), BG)
    dr = ImageDraw.Draw(img)
    dr.text((16, 14), f"Market map · {hm.get('asof') or ''} · size = market value, colour = day's move", fill=INK, font=_font(26))
    F = hm['fields']
    ich, irect, it = F.index('chg'), F.index('rect'), F.index('ticker')
    for c in hm['cells']:
        x, y, w, h = [v * s for v in c[irect]]
        y += 60
        dr.rectangle([x, y, x + w, y + h], fill=_diverge(c[ich], 3), outline=BG)
        if w > 46 and h > 26:
            fs = max(12, min(30, int(min(w / 4.2, h / 2.6))))
            dr.text((x + 4, y + 3), c[it].replace('-', '.'), fill=(255, 255, 255), font=_font(fs))
            if h > fs * 2.2 and c[ich] is not None:
                dr.text((x + 4, y + 5 + fs), f"{c[ich]:+.1f}%", fill=(255, 255, 255), font=_font(max(11, fs - 6), False))
    for sec in hm['sectors']:
        x, y, w, h = [v * s for v in sec['rect']]
        y += 60
        dr.rectangle([x, y, x + w, y + h], outline=INK, width=2)
        if w > 90 and h > 40:
            dr.text((x + 4, y + 1), sec['label'].upper(), fill=INK, font=_font(13))
    dr.text((16, img.height - 30), 'filing-flows.com · Nasdaq screener (delayed) · not investment advice', fill=MUTED, font=_font(16, False))
    img.save(path, optimize=True)
    return path


def render_race_gif(race, title, path, width=1000, bars=10, frame_ms=1300, last_ms=3500):
    """One frame per quarter: horizontal bars of the largest holdings (dollars), the same colour per ticker."""
    from PIL import Image, ImageDraw
    if len(race) < 2:
        return None
    pal = [(23, 115, 74), (52, 92, 160), (196, 120, 40), (130, 70, 150), (40, 140, 150), (170, 60, 80), (90, 120, 50),
           (70, 70, 70), (150, 110, 70), (60, 110, 200), (200, 80, 140), (110, 160, 90)]
    colour, frames = {}, []
    vmax = max((t[1] for q in race for t in q['top'][:bars]), default=1) or 1
    h = 110 + bars * 46
    for q in race:
        img = Image.new('RGB', (width, h), BG)
        dr = ImageDraw.Draw(img)
        dr.text((20, 16), title, fill=INK, font=_font(28))
        dr.text((20, 54), f"13F, quarter ended {q['period']} · total ${q['total'] / 1e9:,.1f}B", fill=MUTED, font=_font(18, False))
        for i, (t, usd, w) in enumerate(q['top'][:bars]):
            c = colour.setdefault(t, pal[len(colour) % len(pal)])
            y = 96 + i * 46
            L = round((width - 260) * usd / vmax)
            dr.rectangle([120, y, 120 + max(2, L), y + 34], fill=c)
            dr.text((20, y + 6), t.replace('-', '.'), fill=INK, font=_font(20))
            dr.text((130 + L, y + 6), f"${usd / 1e9:,.1f}B" + (f" · {w * 100:.0f}%" if w else ''), fill=INK, font=_font(17, False))
        dr.text((20, h - 26), 'filing-flows.com · SEC 13F filings · not investment advice', fill=MUTED, font=_font(14, False))
        frames.append(img)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[frame_ms] * (len(frames) - 1) + [last_ms], loop=0, optimize=True)
    return path


# ------------------------------------------------------------------ build
def build(root, smart=None, consensus=None, debt=None, hub=None, images=True, today=None):
    root = Path(root)
    pub = root / 'public'
    pub.mkdir(parents=True, exist_ok=True)
    st = {'built_at': now()}
    cons_ix = read_json(Path(consensus) / 'index.json') if consensus else None
    cons_mk = read_json(Path(consensus) / 'market.json') if consensus else None
    debt_ix = read_json(Path(debt) / 'index.json') if debt else None
    nasdaq = read_json(root / 'cache' / 'nasdaq.json')
    sectors = sector_map(cons_ix, debt_ix, nasdaq)
    st['sectors_known'] = len(sectors)

    def step(name, fn):
        try:
            doc = fn()
        except Exception as exc:                                # one broken part never stops the others
            st[name] = f'failed: {type(exc).__name__} {str(exc)[:160]}'
            print(f'::warning::market maps {name}: {st[name]}')
            return None
        if doc:
            write_json(pub / f'{name}.json', doc)
            st[name] = 'ok'
        else:
            st[name] = 'no data'
        return doc

    step('flows', lambda: build_flows(smart, sectors) if smart else None)
    mans = step('managers', lambda: build_managers(hub, sectors) if hub else None)
    hm = step('heatmap', lambda: build_heatmap(nasdaq, sectors, read_json(Path(hub) / 'market' / 'extremes.json') if hub else None,
                                               read_json(Path(smart) / 'index.json') if smart else None,
                                               read_json(Path(hub) / 'market' / 'short-interest.json') if hub else None, cons_ix))
    step('network', lambda: build_network(mans, Path(hub) / 'cache' / 'prices' if hub else None) if mans else None)
    step('maturity', lambda: build_maturity(debt, today) if debt else None)
    step('thermometer', lambda: build_thermometer(root, cons_mk, today))
    step('liquidity', lambda: build_liquidity(root))
    if images:
        img = pub / 'img'
        img.mkdir(exist_ok=True)
        made = []
        try:
            if hm:
                made.append(render_heatmap_png(hm, img / 'heatmap.png').name)
            for m in (mans or {}).get('managers', [])[:3]:
                if render_race_gif(m['race'], f"{m['name']}: largest holdings", img / f"race-{m['cik']}.gif"):
                    made.append(f"race-{m['cik']}.gif")
            cr = (mans or {}).get('combined_race') or []
            if render_race_gif(cr, 'Watched 13F managers combined: largest holdings', img / 'race-all.gif'):
                made.append('race-all.gif')
        except Exception as exc:
            st['images_error'] = f'{type(exc).__name__} {str(exc)[:120]}'
        st['images'] = made
    st['collect'] = read_json(root / 'cache' / 'collect.json', {})
    write_json(pub / 'status.json', st)
    print(json.dumps({k: v for k, v in st.items() if k != 'collect'}))
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cmd', choices=['collect', 'build'])
    ap.add_argument('--root', required=True, help='the research-market branch checkout')
    ap.add_argument('--smart', help='public/ of smart-history')
    ap.add_argument('--consensus', help='public/ of consensus-history')
    ap.add_argument('--debt', help='public/ of debt-history')
    ap.add_argument('--hub', help="the hub's data folder (disclosures/docs/data: market/, shards/holdings/, cache/prices/)")
    ap.add_argument('--no-images', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'collect':
        collect(a.root)
    else:
        build(a.root, a.smart, a.consensus, a.debt, a.hub, images=not a.no_images)
    return 0


if __name__ == '__main__':
    sys.exit(main())
