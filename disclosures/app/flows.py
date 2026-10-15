"""Market-wide 13F flows (4.2): what the processed managers added, sold and net-bought, by security.

Built from the cached manager snapshots at publish time into docs/data/flows.json:
- "quarter": the latest report period that most managers have on file
- "ytd": every report period ending in the current calendar year, summed
Per security (CUSIP, with the ticker when the price module mapped it): shares added / sold / net, an estimated
dollar value of those changes at the quarter-end implied price (value ÷ shares of the reporting manager), how many
managers bought, sold, hold. Quantities compare consecutive quarter-end disclosures of the same manager — they are
not trades, and they only cover managers processed so far.
"""
import datetime as dt
import gzip
import json
import re
from pathlib import Path
from core import now, read_json


TOP = 60


def _security_rows(root, periods_for):
    """Yield (period, manager, change row) for complete snapshots whose period periods_for() accepts."""
    cache_dir = Path(root) / 'cache' / 'holdings'
    for path in sorted(cache_dir.glob('*.json.gz')):
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                m = json.load(f)
        except Exception:
            continue
        for s in m.get('snapshots', []):
            if not s.get('complete') or not periods_for(s.get('period', '')):
                continue
            for c in s.get('changes', []):
                if c.get('put_call') != 'NONE' or c.get('share_type') != 'SH' or not c.get('delta_shares'):
                    continue
                yield s['period'], m, c


def aggregate(root, periods_for, tickers):
    agg = {}
    for period, m, c in _security_rows(root, periods_for):
        key = c['cusip']
        a = agg.setdefault(key, {'cusip': key, 'issuer': c.get('issuer'), 'ticker': tickers.get(key), 'shares_added': 0, 'shares_sold': 0,
                                 'usd_added': 0.0, 'usd_sold': 0.0, 'buyers': set(), 'sellers': set(), 'holders': set(), 'new': 0, 'closed': 0,
                                 'periods': set(), 'largest_buy': None, 'largest_sell': None})
        d = c['delta_shares']
        price = (c['value_usd'] / c['shares']) if c.get('shares') and c.get('value_usd') else ((c.get('prior_value_usd') or 0) / c['prior_shares'] if c.get('prior_shares') else None)
        usd = abs(d) * price if price else 0.0
        a['periods'].add(period)
        if c.get('shares'):
            a['holders'].add(m['cik'])
        if d > 0:
            a['shares_added'] += d; a['usd_added'] += usd; a['buyers'].add(m['cik'])
            if c.get('status') == 'NEW': a['new'] += 1
            if not a['largest_buy'] or usd > a['largest_buy']['usd']:
                a['largest_buy'] = {'manager': m.get('label') or m.get('name'), 'cik': m['cik'], 'shares': d, 'usd': round(usd), 'period': period}
        else:
            a['shares_sold'] += -d; a['usd_sold'] += usd; a['sellers'].add(m['cik'])
            if c.get('status') == 'NOT DISCLOSED': a['closed'] += 1
            if not a['largest_sell'] or usd > a['largest_sell']['usd']:
                a['largest_sell'] = {'manager': m.get('label') or m.get('name'), 'cik': m['cik'], 'shares': -d, 'usd': round(usd), 'period': period}
    rows = []
    for a in agg.values():
        rows.append({**a, 'buyers': len(a['buyers']), 'sellers': len(a['sellers']), 'holders': len(a['holders']), 'periods': sorted(a['periods']),
                     'net_shares': a['shares_added'] - a['shares_sold'], 'usd_net': round(a['usd_added'] - a['usd_sold']),
                     'usd_added': round(a['usd_added']), 'usd_sold': round(a['usd_sold'])})
    return rows


def build_flows(root, cfg=None):
    root = Path(root)
    cusips = read_json(root / 'cache' / 'prices' / 'cusips.json', {})
    tickers = {c: v.get('ticker') for c, v in cusips.items() if v.get('ticker')}
    periods = set()
    for path in (root / 'cache' / 'holdings').glob('*.json.gz'):
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                for s in json.load(f).get('snapshots', []):
                    if s.get('complete'):
                        periods.add(s['period'])
        except Exception:
            continue
    if not periods:
        return None
    year = dt.datetime.now(dt.timezone.utc).year
    # the "current" quarter: the most recent period that a meaningful share of managers have filed for
    counts = {}
    for path in (root / 'cache' / 'holdings').glob('*.json.gz'):
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                for s in json.load(f).get('snapshots', []):
                    if s.get('complete'):
                        counts[s['period']] = counts.get(s['period'], 0) + 1
        except Exception:
            continue
    latest = max(periods)
    quarter = latest if counts.get(latest, 0) >= max(3, 0.2 * max(counts.values())) else max(p for p in periods if p != latest)
    windows = {'quarter': {'label': quarter, 'periods': [quarter], 'rows': aggregate(root, lambda p: p == quarter, tickers)},
               'ytd': {'label': f'{year} year to date', 'periods': sorted(p for p in periods if p.startswith(str(year))),
                       'rows': aggregate(root, lambda p: p.startswith(str(year)), tickers)}}
    out = {'generated_at': now(), 'managers_on_file': len(list((root / 'cache' / 'holdings').glob('*.json.gz'))), 'windows': {}}
    for key, w in windows.items():
        rows = w['rows']
        lists = {'added': sorted(rows, key=lambda r: -r['usd_added'])[:TOP], 'sold': sorted(rows, key=lambda r: -r['usd_sold'])[:TOP],
                 'net_buy': sorted([r for r in rows if r['usd_net'] > 0], key=lambda r: -r['usd_net'])[:TOP],
                 'net_sell': sorted([r for r in rows if r['usd_net'] < 0], key=lambda r: r['usd_net'])[:TOP],
                 'most_buyers': sorted(rows, key=lambda r: (-r['buyers'], -r['usd_added']))[:TOP],
                 'most_sellers': sorted(rows, key=lambda r: (-r['sellers'], -r['usd_sold']))[:TOP]}
        out['windows'][key] = {'label': w['label'], 'periods': w['periods'], 'securities': len(rows),
                               'managers': len({p for r in rows for p in []}) or None,
                               'totals': {'usd_added': round(sum(r['usd_added'] for r in rows)), 'usd_sold': round(sum(r['usd_sold'] for r in rows))},
                               'lists': lists}
    out['note'] = ('Changes between consecutive quarter-end 13F disclosures of the managers processed so far (not trades, not every holder); '
                   'dollar values estimate each change at the quarter-end implied price (value ÷ shares) of the reporting manager. '
                   'Common shares only; options and other quantity types excluded.')
    return out


def publish_flows(root):
    data = build_flows(root)
    if data is None:
        return None
    path = Path(root) / 'flows.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(path)
    return data
