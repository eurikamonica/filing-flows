"""Short interest (4.6): FINRA's consolidated short interest, twice a month, for every listed stock.

Broker-dealers report the short positions they carry in their customers' and their own accounts as of two settlement
dates a month (mid-month and month-end); FINRA publishes the consolidated figures for exchange-listed and OTC stocks
about a week later. FINRA's Query API (no key needed for this dataset) is partitioned by settlement date: each run asks
which dates exist, then reads the newest dates not yet on file — up to `dates_per_run`, newest first, until
`keep_dates` dates (a year by default) are on file — 5,000 rows a request.

Kept per date (cache/shorts/<date>.json.gz): the stocks in SEC's listed-company tickers — short position, the previous
one, the change, average daily volume and days to cover as FINRA computes them.
Publish: market/short-interest.json — the newest date: rows for every stock with a meaningful position (searchable in
the hub, ✦ X per row), the largest rises and falls, the most days to cover; each row carries its last six dates. The
company pages get each ticker's year of dates (stage-public holders index).
"""
import datetime as dt
import gzip
import json
from pathlib import Path

from core import now, read_json, write_json

PARTS = 'https://api.finra.org/partitions/group/otcMarket/name/consolidatedShortInterest'
DATA = 'https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest'
PAGE = 5000
FIELDS = ['ticker', 'name', 'market', 'short', 'prev', 'change_pct', 'adv', 'dtc', 'split', 'revised']


def available_dates(client):
    body = json.loads(client.get(PARTS, headers={'Accept': 'application/json'}))
    out = sorted({p['partitions'][0] for p in body.get('availablePartitions') or [] if p.get('partitions')}, reverse=True)
    return [d for d in out if len(d) == 10]


def fetch_date(client, day, limit=None):
    """Every row FINRA has for one settlement date (paged)."""
    rows, offset = [], 0
    while True:
        body = client.post_json(DATA, {'limit': PAGE, 'offset': offset,
                                       'compareFilters': [{'compareType': 'EQUAL', 'fieldName': 'settlementDate', 'fieldValue': day}]},
                                headers={'Accept': 'application/json'})
        if not isinstance(body, list):
            raise ValueError(f'unexpected answer for {day}: {str(body)[:200]}')
        rows.extend(body)
        if len(body) < PAGE or (limit and len(rows) >= limit):
            return rows
        offset += PAGE


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _f(v, d=2):
    try:
        return round(float(v), d)
    except (TypeError, ValueError):
        return None


def compact(rows, listed):
    """FINRA rows → [ticker, name, market, short, prev, change %, ADV, days to cover, split flag, revision flag] for listed stocks."""
    out = []
    for r in rows:
        t = str(r.get('symbolCode') or '').upper().strip()
        if not t or (listed and t.replace('.', '-').replace('/', '-') not in listed):
            continue
        out.append([t, (r.get('issueName') or '').strip()[:60], r.get('marketClassCode') or '', _int(r.get('currentShortPositionQuantity')),
                    _int(r.get('previousShortPositionQuantity')), _f(r.get('changePercent')), _int(r.get('averageDailyVolumeQuantity')),
                    _f(r.get('daysToCoverQuantity')), r.get('stockSplitFlag') or None, r.get('revisionFlag') or None])
    return out


def listed_tickers(root):
    rows = read_json(Path(root) / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []
    return {str(r['ticker']).upper().replace('.', '-').replace('/', '-') for r in rows if r.get('ticker')}


def collect(client, root, cfg=None):
    cfg = cfg or {}
    cdir = Path(root) / 'cache' / 'shorts'
    cdir.mkdir(parents=True, exist_ok=True)
    have = {p.name[:10] for p in cdir.glob('????-??-??.json.gz')}
    dates = available_dates(client)
    keep = dates[:int(cfg.get('keep_dates', 24))]
    listed = listed_tickers(root)
    got, errors = [], []
    # the newest date is read again for a few days after it appears: FINRA revises late reports into it
    state = read_json(cdir / 'state.json', {})
    recheck = keep[:1] if keep and keep[0] in have and state.get('rechecks', {}).get(keep[0], 0) < int(cfg.get('rechecks', 3)) else []
    todo = recheck + [d for d in keep if d not in have]
    for day in todo[:int(cfg.get('dates_per_run', 4))]:
        try:
            rows = compact(fetch_date(client, day), listed if len(listed) > 5000 else None)
            if not rows:
                raise ValueError('no rows')
            with gzip.open(cdir / f'{day}.tmp', 'wt', encoding='utf-8') as f:
                json.dump({'date': day, 'fields': FIELDS, 'rows': rows, 'fetched_at': now()}, f, separators=(',', ':'))
            (cdir / f'{day}.tmp').replace(cdir / f'{day}.json.gz')
            got.append([day, len(rows)])
            if day in recheck:
                state.setdefault('rechecks', {})[day] = state.get('rechecks', {}).get(day, 0) + 1
        except Exception as exc:
            errors.append(f'{day}: {str(exc)[:160]}')
            print(f'short interest {day}: {exc}', flush=True)
    for p in cdir.glob('????-??-??.json.gz'):          # older than the window: dropped
        if keep and p.name[:10] < keep[-1]:
            p.unlink()
    state['rechecks'] = {k: v for k, v in state.get('rechecks', {}).items() if k in keep[:2]}
    state['updated_at'] = now()
    write_json(cdir / 'state.json', state)
    on_file = sorted(p.name[:10] for p in cdir.glob('????-??-??.json.gz'))
    return {'status': 'ok' if not errors else 'partial', 'fetched': got, 'errors': errors, 'on_file': len(on_file),
            'newest': on_file[-1] if on_file else None, 'available': len(dates), 'updated_at': now()}


def load_dates(root, n=None):
    """[(date, {ticker: row})] oldest first."""
    cdir = Path(root) / 'cache' / 'shorts'
    files = sorted(cdir.glob('????-??-??.json.gz'))
    if n:
        files = files[-n:]
    out = []
    for p in files:
        try:
            d = json.load(gzip.open(p, 'rt', encoding='utf-8'))
            out.append((d['date'], {r[0]: r for r in d['rows']}))
        except Exception:
            continue
    return out


def history_by_ticker(root, n=24):
    """ticker → [[date, short, change %, days to cover, ADV], …] oldest first (company pages)."""
    out = {}
    for day, rows in load_dates(root, n):
        for t, r in rows.items():
            out.setdefault(t, []).append([day, r[3], r[5], r[7], r[6]])
    return out


def publish(root, out_dir, min_short=500_000):
    dates = load_dates(root, 6)
    if not dates:
        return None
    day, rows = dates[-1]
    prev_day = dates[-2][0] if len(dates) > 1 else None
    hist = {}
    for d, rs in dates:
        for t, r in rs.items():
            hist.setdefault(t, []).append([d, r[3]])
    pick = []
    for t, r in rows.items():
        if (r[3] or 0) < min_short:
            continue
        pick.append({'ticker': t, 'name': r[1], 'market': r[2], 'short': r[3], 'prev': r[4], 'change_pct': r[5], 'adv': r[6],
                     'dtc': r[7], 'split': r[8], 'revised': r[9], 'change': (r[3] - r[4]) if r[3] is not None and r[4] is not None else None,
                     'hist': hist.get(t, [])})
    liquid = [r for r in pick if (r['adv'] or 0) >= 200_000]
    sig = [r for r in liquid if r['change_pct'] is not None and r['short'] >= 2_000_000 and not r['split']]
    data = {'generated_at': now(), 'settlement_date': day, 'previous_date': prev_day, 'dates': [d for d, _ in dates],
            'stocks': len(rows), 'shown': len(pick), 'min_short': min_short,
            'note': ('FINRA consolidated short interest: the short positions broker-dealers carry for customers and themselves '
                     'in each stock as of the settlement date, reported twice a month and published about a week later. '
                     'Days to cover = short position ÷ average daily volume, as FINRA computes it. A position is a snapshot, '
                     'not a trade; a stock split (flagged) changes the share counts.'),
            'top': {'rise': [r['ticker'] for r in sorted(sig, key=lambda r: -r['change_pct'])[:25]],
                    'fall': [r['ticker'] for r in sorted(sig, key=lambda r: r['change_pct'])[:25]],
                    'dtc': [r['ticker'] for r in sorted(liquid, key=lambda r: -(r['dtc'] or 0))[:25]],
                    'largest': [r['ticker'] for r in sorted(pick, key=lambda r: -(r['short'] or 0))[:25]]},
            'rows': sorted(pick, key=lambda r: -(r['short'] or 0))}
    path = Path(out_dir) / 'short-interest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)
    return {'date': day, 'rows': len(pick)}
