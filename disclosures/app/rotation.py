"""Rotation data (4.4) for the momentum clock and the sector orbits: per company and calendar quarter, how profitability
moved (operating margin vs the same quarter a year earlier, in points; SEC XBRL frames, frames.py) and how the stock
moved (the quarter's return minus the S&P 500's, SPY as the benchmark), plus how busy trading was (average daily volume
vs the company's own average) and the latest 13F crowding. Sector "suns" average their companies (weighted by log revenue).

Built at publish time (automation/stage-public.py --site-data): the Sankey site's index gives tickers and sectors.
"""
import bisect
import datetime as dt
import gzip
import json
import math
import re
from pathlib import Path

import frames as FR


def _rows(root, ticker):
    p = Path(root) / 'cache' / 'prices' / (re.sub(r'[^A-Za-z0-9-]', '_', ticker.upper().replace('.', '-')) + '.json.gz')
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            return json.load(f)['rows']
    except Exception:
        return None


def _close(rows, day, gap=7):
    i = bisect.bisect_right(rows, [day, float('inf')]) - 1          # rows sorted by date: [date, close(, volume)]
    if i < 0:
        return None
    best = rows[i]
    if (dt.date.fromisoformat(day) - dt.date.fromisoformat(best[0])).days > gap:
        return None
    return best[1]


def _volume(rows, start, end):
    v = [r[2] for r in rows if start < r[0] <= end and len(r) > 2 and r[2]]
    return sum(v) / len(v) if len(v) >= 20 else None


def _qdates(period):
    """'CY2025Q3' → ('2025-06-30', '2025-09-30'): the previous quarter end and this one."""
    y, q = int(period[2:6]), int(period[-1])
    end = dt.date(y, 3 * q, 1) + dt.timedelta(days=32)
    end = end.replace(day=1) - dt.timedelta(days=1)
    start = dt.date(y, 3 * q - 2, 1) - dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def series(marg, rows, spy, periods, quarters=16):
    """Points for the periods that have a margin a year earlier and closes at both quarter ends."""
    pts = []
    for i, period in enumerate(periods):
        if i < 4 or period not in marg or periods[i - 4] not in marg:
            continue
        om, om_ago = marg[period][2], marg[periods[i - 4]][2]
        if abs(om) > 300 or abs(om_ago) > 300:
            continue
        start, end = _qdates(period)
        a, b = _close(rows, start), _close(rows, end)
        if not a or not b:
            continue
        sa, sb = (_close(spy, start), _close(spy, end)) if spy else (None, None)
        ret = b / a - 1
        pts.append({'cal': period, 'om': round(om, 2), 'dom': round(om - om_ago, 2), 'ret': round(ret, 4),
                    'rel': round(ret - (sb / sa - 1), 4) if sa and sb else round(ret, 4), 'rev': marg[period][0],
                    'vol': _volume(rows, start, end)})
    pts = pts[-quarters:]
    vols = [p['vol'] for p in pts if p['vol']]
    avg = sum(vols) / len(vols) if vols else None
    for p in pts:
        p['volz'] = round(p['vol'] / avg - 1, 3) if p['vol'] and avg else None
        p.pop('vol')
    return pts


def build(site_data, root, top=600, quarters=16):
    site_data, root = Path(site_data), Path(root)
    ix = json.loads((site_data / 'index.json').read_text(encoding='utf-8'))
    names = ix.get('sector_names') or {}
    latest = {}
    for r in ix.get('companies', []):
        if r.get('ticker') and (r['cik'] not in latest or (r.get('filed') or '') > (latest[r['cik']].get('filed') or '')):
            latest[r['cik']] = r
    flows = {}
    try:
        f = json.loads((root / 'market' / 'by-ticker.json').read_text(encoding='utf-8'))
        flows = {t.replace('-', '.'): dict(zip(f['fields'], v)) for t, v in f.get('rows', {}).items()}
    except Exception:
        pass
    periods = FR.calendar_quarters(quarters + 5)
    marg = FR.margins(root, periods)
    spy = _rows(root, 'SPY')
    out = []
    for r in sorted(latest.values(), key=lambda r: -(r.get('revenue') or 0)):
        if len(out) >= top:
            break
        m = marg.get(str(r['cik']))
        rows = _rows(root, r['ticker']) if m else None
        if not rows:
            continue
        pts = series(m, rows, spy, periods, quarters)
        if len(pts) < 3:
            continue
        fl = flows.get(r['ticker'].replace('-', '.')) or {}
        out.append({'t': r['ticker'], 'n': r.get('name'), 'cik': r['cik'], 's': r.get('sector') or 'other', 'ind': r.get('industry'),
                    'rev': r.get('revenue'), 'net13f': (fl.get('buyers', 0) - fl.get('sellers', 0)) if fl else None,
                    'usd13f': fl.get('usd_net'), 'pts': pts})
    # sector suns: revenue-weighted averages per calendar quarter (clipped so one outlier does not drag the sun)
    sectors = {}
    for co in out:
        w = math.log10(max(co['rev'] or 1e6, 1e6))
        for p in co['pts']:
            a = sectors.setdefault(co['s'], {}).setdefault(p['cal'], [0.0, 0.0, 0.0, 0])
            a[0] += w * max(-30, min(30, p['dom'])); a[1] += w * max(-1, min(1, p['rel'])); a[2] += w; a[3] += 1
    sun = {}
    for s, per in sectors.items():
        pts = [{'cal': cal, 'dom': round(a[0] / a[2], 2), 'rel': round(a[1] / a[2], 4), 'n': a[3]} for cal, a in sorted(per.items()) if a[3] >= 3]
        sun[s] = {'name': names.get(s, s), 'pts': pts[-quarters:]}
    return {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'benchmark': 'SPY' if spy else None,
            'note': ('x: operating margin minus the same quarter a year earlier (points). y: the stock\'s return over the fiscal '
                     'quarter minus the S&P 500 (SPY) over the same dates. Dot size: average daily trading volume in the quarter '
                     'against the company\'s own average. Sector suns weight companies by the log of revenue. Quarter-end closes '
                     'from daily prices; margins from the 10-Q / 10-K figures on Filing Flows.'),
            'companies': out, 'sectors': sun}
