"""SEC XBRL "frames" (4.4): one request returns one figure for every filer for one calendar quarter, so 21 quarters of
revenue, operating income, gross profit and net income for all companies cost a couple of hundred requests. Used by
rotation.py for the momentum clock and the solar system.

10-K filers rarely tag their fourth quarter on its own, so the annual frames (CY2025 …, with each row's fiscal year end)
fill it: fourth quarter = the year − the three quarters before it, when those three are on file.

Cache: cache/frames/<concept>-CY2025Q3.json.gz = {"cik": value}; annual: <concept>-CY2025.json.gz = {"cik": [value, end]}.
Quarters older than the last two (years older than the last one) are final and never fetched again; the recent ones are
refreshed every few days while late filers report.
"""
import datetime as dt
import gzip
import json
from pathlib import Path

from core import now, read_json, write_json

URL = 'https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/{period}.json'
REVENUE = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax',
           'SalesRevenueNet']
COST = ['CostOfRevenue', 'CostOfGoodsAndServicesSold']
CONCEPTS = REVENUE + ['OperatingIncomeLoss', 'GrossProfit', 'NetIncomeLoss'] + COST


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


def calendar_years(periods):
    return sorted({p[:6] for p in periods})


def _quarter_of(end):
    """The calendar quarter whose end is nearest to a date: '2025-09-27' → 'CY2025Q3', '2026-01-31' → 'CY2025Q4'."""
    d = dt.date.fromisoformat(end)
    best = None
    for y in (d.year - 1, d.year, d.year + 1):
        for q in range(1, 5):
            qe = (dt.date(y, 3 * q, 1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
            gap = abs((qe - d).days)
            if best is None or gap < best[0]:
                best = (gap, f'CY{y}Q{q}')
    return best[1]


def _shift(period, k):
    y, q = int(period[2:6]), int(period[-1]) - 1 + k
    return f'CY{y + q // 4}Q{q % 4 + 1}'


def collect(client, root, quarters=21, refresh_days=3):
    root = Path(root)
    state = read_json(root / 'cache' / 'frames' / 'state.json', {})
    periods = calendar_quarters(quarters)
    years = calendar_years(periods)
    recent = set(periods[-2:]) | set(years[-2:])
    fresh_after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=refresh_days)).isoformat()
    fetched = errors = 0
    for period in periods + years:
        annual = len(period) == 6
        for concept in CONCEPTS:
            key = f'{concept}-{period}'
            p = path_for(root, concept, period)
            when = state.get(key)
            if p.exists() and (period not in recent or (when and when > fresh_after)):
                continue
            try:
                body = client.json(URL.format(concept=concept, period=period), sec=True)
                rows = [r for r in body.get('data', []) if r.get('val') is not None]
                vals = ({str(r['cik']): [r['val'], r.get('end')] for r in rows} if annual
                        else {str(r['cik']): r['val'] for r in rows})
            except Exception as exc:
                if 'HTTP 404' in str(exc):            # no filer used this concept for the period (yet)
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


def quarterly(root, concept, periods):
    """{period: {cik: value}} for the periods, with missing quarters filled from the annual frames where the other three
    quarters of that fiscal year are on file."""
    span = [_shift(periods[0], -k) for k in (3, 2, 1)] + list(periods)
    q = {p: load(root, concept, p) for p in dict.fromkeys(span)}
    for year in calendar_years(span) + [f'CY{int(periods[-1][2:6]) + 1}']:
        for cik, row in load(root, concept, year).items():
            if not isinstance(row, list) or row[1] is None:
                continue
            last = _quarter_of(row[1])
            if last not in q or cik in q[last]:
                continue
            three = [q.get(_shift(last, -k), {}).get(cik) for k in (1, 2, 3)]
            if all(v is not None for v in three):
                q[last][cik] = row[0] - sum(three)
    return {p: q[p] for p in periods}


def margins(root, periods):
    """{cik: {period: (revenue, operating income, operating margin %)}} for the periods (kept for older callers)."""
    out = {}
    for cik, per in figures(root, periods).items():
        for period, f in per.items():
            if f.get('oi') is not None:
                out.setdefault(cik, {})[period] = (f['rev'], f['oi'], 100.0 * f['oi'] / f['rev'])
    return out


def figures(root, periods):
    """{cik: {period: {'rev', 'oi', 'gp', 'ni'}}} — revenue from the first revenue concept a company reports for the period;
    gross profit from GrossProfit, else revenue − cost of revenue. Only periods with positive revenue."""
    rev = {}
    for concept in REVENUE:
        for period, vals in quarterly(root, concept, periods).items():
            per = rev.setdefault(period, {})
            for cik, v in vals.items():
                per.setdefault(cik, v)
    other = {c: quarterly(root, c, periods) for c in ['OperatingIncomeLoss', 'GrossProfit', 'NetIncomeLoss'] + COST}
    out = {}
    for period, per in rev.items():
        for cik, r in per.items():
            if not r or r <= 0:
                continue
            gp = other['GrossProfit'][period].get(cik)
            if gp is None:
                cost = next((other[c][period][cik] for c in COST if cik in other[c][period]), None)
                gp = r - cost if cost is not None else None
            out.setdefault(cik, {})[period] = {'rev': r, 'oi': other['OperatingIncomeLoss'][period].get(cik), 'gp': gp,
                                               'ni': other['NetIncomeLoss'][period].get(cik)}
    return out
