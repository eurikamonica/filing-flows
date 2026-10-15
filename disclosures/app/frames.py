"""SEC XBRL "frames" (4.4): one request returns one figure for every filer for one calendar quarter, so 16 quarters of
revenue and operating income for all companies cost about 80 requests. Used by rotation.py for the momentum clock.

Cache: cache/frames/<concept>-CY2025Q3.json.gz = {"cik": value} (compact). Quarters older than the last two are final
and never fetched again; the recent ones are refreshed every few days while late filers report.
"""
import datetime as dt
import gzip
import json
from pathlib import Path

from core import now, read_json, write_json

URL = 'https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/{period}.json'
REVENUE = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax',
           'SalesRevenueNet']
CONCEPTS = REVENUE + ['OperatingIncomeLoss']


def calendar_quarters(n=17, today=None):
    """The last n complete calendar quarters, oldest first: ['CY2022Q3', …]."""
    today = today or dt.date.today()
    y, q = today.year, (today.month - 1) // 3          # the current (incomplete) quarter is q+1; the last complete is q
    out = []
    for _ in range(n):
        if q == 0:
            y, q = y - 1, 4
        out.append(f'CY{y}Q{q}')
        q -= 1
    return out[::-1]


def path_for(root, concept, period):
    return Path(root) / 'cache' / 'frames' / f'{concept}-{period}.json.gz'


def load(root, concept, period):
    p = path_for(root, concept, period)
    if not p.exists():
        return {}
    with gzip.open(p, 'rt', encoding='utf-8') as f:
        return json.load(f)


def collect(client, root, quarters=17, refresh_days=3):
    root = Path(root)
    state = read_json(root / 'cache' / 'frames' / 'state.json', {})
    periods = calendar_quarters(quarters)
    recent = set(periods[-2:])
    fetched = errors = 0
    for period in periods:
        for concept in CONCEPTS:
            key = f'{concept}-{period}'
            p = path_for(root, concept, period)
            when = state.get(key)
            if p.exists() and (period not in recent or (when and when > (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=refresh_days)).isoformat())):
                continue
            try:
                body = client.json(URL.format(concept=concept, period=period), sec=True)
                vals = {str(r['cik']): r['val'] for r in body.get('data', []) if r.get('val') is not None}
            except Exception as exc:
                if 'HTTP 404' in str(exc):            # no filer used this concept for the quarter (yet)
                    vals = {}
                else:
                    errors += 1
                    print(f'frames {key}: {exc}', flush=True)
                    continue
            p.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(p.with_suffix('.tmp'), 'wt', encoding='utf-8') as f:
                json.dump(vals, f, separators=(',', ':'))
            p.with_suffix('.tmp').replace(p)
            state[key] = now()
            fetched += 1
    write_json(root / 'cache' / 'frames' / 'state.json', state)
    return {'status': 'ok' if not errors else 'partial', 'fetched': fetched, 'errors': errors, 'periods': [periods[0], periods[-1]]}


def margins(root, periods):
    """{cik: {period: (revenue, operating income, margin %)}} for the periods."""
    out = {}
    for period in periods:
        rev = {}
        for concept in REVENUE:                         # first concept a company reports wins
            for cik, v in load(root, concept, period).items():
                rev.setdefault(cik, v)
        oi = load(root, 'OperatingIncomeLoss', period)
        for cik, r in rev.items():
            if cik in oi and r and r > 0:
                out.setdefault(cik, {})[period] = (r, oi[cik], 100.0 * oi[cik] / r)
    return out
