"""Long history for the rotation charts: the branch "rotation-history" (.github/workflows/rotation-history.yml).

  collect  weekly closes (dividend- and split-adjusted) and weekly volume since each listing — Yahoo's weekly chart
           ('max'), Stooq's daily file resampled to weeks as the fallback — for SPY (the benchmark), the SPDR sector
           ETFs, a set of style / size / asset-class ETFs and every company of the Sankey site, largest first. A run
           takes a batch of new tickers and refreshes the stalest ones (the last months only), within a time budget;
           failures wait longer after each try. Progress lives in state.json, so any run can stop and the next goes on.
  frames   the SEC XBRL frames of revenue, operating income, gross profit, net income and cost of revenue back to 2009
           (app/frames.py into the same folder; quarters on file are final and never fetched again)
  build    public/ — what the site loads:
             rrg.json                 one Friday grid since 2000: SPY, the ETFs and one index per site sector
                                      (the site's companies, weighted by the log of revenue), closes and volume; the
                                      charts compute the RRG (RS-Ratio, RS-Momentum) from these in the browser
             t/<TICKER>.json          one company's weekly closes and volume, loaded when a chart traces it
             rotation-long.json       the momentum clock's variables (app/rotation.py) for 64 quarters (since 2010)
             rotation-long-monthly.json  … and month by month since 2008, from the weekly closes

    python app/rotation_history.py collect --root hist --site-index site/index.json --batch 300 --minutes 25
    python app/rotation_history.py frames  --root hist --quarters 72
    python app/rotation_history.py build   --root hist --site-data site --data docs/data
"""
import argparse
import datetime as dt
import gzip
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import Client, now, read_json, write_json   # noqa: E402

BENCH = 'SPY'
# (ticker, the site's sector key, name)
SECTOR_ETFS = [('XLK', 'technology', 'Technology'), ('XLC', 'communication', 'Communication Services'),
               ('XLY', 'consumer-disc', 'Consumer Discretionary'), ('XLP', 'consumer-staples', 'Consumer Staples'),
               ('XLV', 'health', 'Health Care'), ('XLF', 'financials', 'Financials'), ('XLRE', 'real-estate', 'Real Estate'),
               ('XLE', 'energy', 'Energy'), ('XLB', 'materials', 'Materials'), ('XLI', 'industrials', 'Industrials'),
               ('XLU', 'utilities', 'Utilities')]
STYLE_ETFS = [('QQQ', 'Nasdaq-100'), ('DIA', 'Dow Jones Industrials'), ('RSP', 'S&P 500 equal weight'), ('MDY', 'S&P MidCap 400'),
              ('IWM', 'Russell 2000 small caps'), ('IWF', 'Russell 1000 Growth'), ('IWD', 'Russell 1000 Value'),
              ('MTUM', 'Momentum factor'), ('USMV', 'Minimum volatility'), ('SMH', 'Semiconductors'), ('XBI', 'Biotech'),
              ('KRE', 'Regional banks'), ('ITB', 'Home builders'), ('EFA', 'Developed markets ex-US'),
              ('EEM', 'Emerging markets'), ('TLT', 'Treasuries 20+ years'), ('GLD', 'Gold'), ('USO', 'Crude oil')]
START = dt.date(2000, 1, 7)                       # a Friday: the first week of the grid
# explicit dates: with range=max Yahoo quietly answers with quarterly bars, whatever the interval asked for
YAHOO = ('https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p1}&period2={p2}&interval=1wk&events=div%2Csplit'
         '&includeAdjustedClose=true')
FORMAT = 2                                        # state.json format: 1 held quarterly bars from range=max; fetched again
STOOQ = 'https://stooq.com/q/d/l/?s={s}&i=d'
REFRESH_DAYS = 6


def friday(d):
    """The Friday of a date's week (weekends belong to the week that just ended)."""
    return d + dt.timedelta(days=4 - d.weekday()) if d.weekday() <= 4 else d - dt.timedelta(days=d.weekday() - 4)


def symbol(ticker):
    t = (ticker or '').strip().upper().replace('/', '-').replace('.', '-').rstrip('*')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,9}', t):
        raise ValueError('unsupported ticker ' + repr(ticker))
    return t


def sig(x, n=6):
    return None if x is None or not math.isfinite(x) else float(f'{x:.{n}g}')


def weekly_rows(days, add_volume=True):
    """[(date, close, volume or None)] in any order → [[friday, the week's last close, its volume]] by week. Daily rows
    add up their volume; weekly bars (add_volume=False) already hold the week's, and a second bar for the same week
    (Yahoo's latest day of an unfinished week) replaces it."""
    weeks = {}
    for d, c, v in sorted(days, key=lambda r: r[0]):
        if c is None or not math.isfinite(c) or c <= 0:
            continue
        k = friday(d).isoformat()
        w = weeks.get(k)
        weeks[k] = [k, c, ((w[2] if w else 0) + (v or 0)) if add_volume else (v or (w[2] if w else 0))]
    return [[k, sig(c), int(v)] for k, c, v in (weeks[k] for k in sorted(weeks))]


def parse_yahoo(payload):
    res = ((payload or {}).get('chart') or {}).get('result') or []
    if not res:
        raise ValueError('no chart result: ' + str(((payload or {}).get('chart') or {}).get('error'))[:160])
    r = res[0]
    stamps = r.get('timestamp') or []
    ind = r.get('indicators') or {}
    q = (ind.get('quote') or [{}])[0]
    adj = ((ind.get('adjclose') or [{}])[0] or {}).get('adjclose')
    closes, vols = adj or q.get('close') or [], q.get('volume') or []
    off = ((r.get('meta') or {}).get('gmtoffset') or 0)
    days = []
    for i, ts in enumerate(stamps):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        d = dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).date()
        days.append((d, float(c), vols[i] if i < len(vols) and vols[i] is not None else None))
    rows = weekly_rows(days, add_volume=False)
    if not rows:
        raise ValueError('no weekly rows in the chart response')
    check_weekly(rows)
    return rows


def check_weekly(rows):
    """Refuse bars that are not weekly (a source answering with monthly or quarterly bars)."""
    if len(rows) >= 8:
        gaps = sorted((dt.date.fromisoformat(b[0]) - dt.date.fromisoformat(a[0])).days for a, b in zip(rows, rows[1:]))
        if gaps[len(gaps) // 2] > 10:
            raise ValueError(f'bars are {gaps[len(gaps) // 2]} days apart, not weekly')


def parse_stooq(text):
    if '<html' in (text or '')[:400].lower() or 'Exceeded' in (text or '')[:200]:
        raise ValueError('Stooq answered with a page instead of CSV')
    lines = [x for x in (text or '').strip().splitlines() if x.strip()]
    if not lines or not lines[0].lower().startswith('date'):
        raise ValueError('not a Stooq CSV: ' + (lines[0][:80] if lines else 'empty'))
    head = [h.strip().lower() for h in lines[0].split(',')]
    ic, iv = head.index('close'), head.index('volume') if 'volume' in head else None
    days = []
    for x in lines[1:]:
        p = x.split(',')
        try:
            days.append((dt.date.fromisoformat(p[0]), float(p[ic]), float(p[iv]) if iv is not None and p[iv] else None))
        except (ValueError, IndexError):
            continue
    rows = weekly_rows(days)
    if not rows:
        raise ValueError('no rows in the Stooq file')
    return rows


def merge(old, new):
    by = {r[0]: r for r in old or []}
    by.update({r[0]: r for r in new or []})
    return [by[k] for k in sorted(by)]


def cache_path(root, ticker):
    return Path(root) / 'cache' / 'weekly' / (symbol(ticker) + '.json.gz')


def load(root, ticker):
    try:
        with gzip.open(cache_path(root, ticker), 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(root, ticker, doc):
    p = cache_path(root, ticker)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p.with_suffix('.tmp'), 'wt', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
    p.with_suffix('.tmp').replace(p)


def fetch(client, ticker, full=True, sources=('yahoo', 'stooq')):
    """(weekly rows, source) — the whole history (full) or the last six months; raises with every source's error."""
    problems = []
    for src in sources:
        try:
            if src == 'yahoo':
                p2 = int(time.time()) + 86400
                p1 = int(dt.datetime(1999, 12, 27, tzinfo=dt.timezone.utc).timestamp()) if full else p2 - 200 * 86400
                return parse_yahoo(client.json(YAHOO.format(s=symbol(ticker), p1=p1, p2=p2))), 'yahoo'
            if src == 'stooq':
                rows = parse_stooq(client.get(STOOQ.format(s=symbol(ticker).lower() + '.us')).decode('utf-8', 'replace'))
                return (rows if full else rows[-30:]), 'stooq'
        except Exception as exc:
            problems.append(f'{src}: {str(exc)[:160]}')
    raise RuntimeError(' | '.join(problems))


# ------------------------------------------------------------------ which tickers, in which order
def site_companies(site_index):
    """The Sankey site's companies with a ticker, largest quarterly revenue first: [{t, n, cik, s, rev}]."""
    try:
        ix = json.loads(Path(site_index).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    best = {}
    for r in ix.get('companies', []) if isinstance(ix, dict) else ix:
        t = (r.get('ticker') or '').strip()
        try:
            t = symbol(t)
        except ValueError:
            continue
        if t not in best or (r.get('filed') or '') > (best[t].get('filed') or ''):
            best[t] = {'t': t, 'n': r.get('name'), 'cik': r.get('cik'), 's': r.get('sector') or 'other', 'rev': r.get('revenue') or 0,
                       'filed': r.get('filed') or ''}
    return sorted(best.values(), key=lambda r: -(r['rev'] or 0))


def universe(site_index, extra=()):
    """Every ticker to keep, in priority order: asked for now, the benchmark, the ETFs, then the site's companies."""
    out = [symbol(t) for t in extra if t]
    out += [BENCH] + [t for t, _, _ in SECTOR_ETFS] + [t for t, _ in STYLE_ETFS] + [c['t'] for c in site_companies(site_index)]
    return list(dict.fromkeys(out))


def collect(client, root, tickers, batch=300, refresh=400, minutes=25.0, refresh_days=REFRESH_DAYS, first=()):
    """Fetch up to `batch` tickers never fetched and refresh up to `refresh` stale ones (oldest first), within `minutes`.
    `first` (owner's request) is fetched in full again even when on file."""
    root = Path(root)
    state = read_json(root / 'state.json', {})
    if state.get('format', 1) < FORMAT:               # an older format: every ticker is fetched again
        for info in (state.get('tickers') or {}).values():
            info.pop('fetched_at', None)
        state['format'] = FORMAT
    tk = state.setdefault('tickers', {})
    t0, today = time.monotonic(), dt.datetime.now(dt.timezone.utc)
    stale_before = (today - dt.timedelta(days=refresh_days)).isoformat()
    first = {symbol(t) for t in first if t}
    new = [t for t in tickers if t in first or (t not in tk or not tk[t].get('fetched_at'))]
    new = [t for t in new if t in first or (tk.get(t) or {}).get('retry_after', '') <= today.isoformat()]
    old = sorted((t for t in tickers if t not in first and (tk.get(t) or {}).get('fetched_at', '9') < stale_before
                  and (tk.get(t) or {}).get('retry_after', '') <= today.isoformat()), key=lambda t: tk[t]['fetched_at'])
    done = {'new': 0, 'refreshed': 0, 'failed': 0, 'skipped_time': 0}
    asked = [t for t in new if t in first]
    plan = [(t, True) for t in asked + [t for t in new if t not in first][:batch]] + [(t, False) for t in old[:refresh]]
    for i, (t, full) in enumerate(plan):
        if time.monotonic() - t0 > minutes * 60:
            done['skipped_time'] = len(plan) - i
            break
        info = tk.setdefault(t, {})
        try:
            rows, src = fetch(client, t, full=full or not load(root, t))
            doc = load(root, t) if not full else None
            rows = merge(doc['rows'], rows) if doc else rows
            save(root, t, {'ticker': t, 'source': src, 'fetched_at': now(), 'rows': rows})
            info.update(fetched_at=now(), source=src, first=rows[0][0], last=rows[-1][0], weeks=len(rows), fails=0)
            info.pop('error', None)
            info.pop('retry_after', None)
            done['new' if full else 'refreshed'] += 1
        except Exception as exc:
            n = int(info.get('fails') or 0) + 1
            info.update(fails=n, error=str(exc)[:300], tried_at=now(),
                        retry_after=(today + dt.timedelta(days=min(30, 2 ** (n - 1)))).isoformat())
            done['failed'] += 1
        if i % 25 == 24:
            write_json(root / 'state.json', state)
    have = [t for t in tickers if (tk.get(t) or {}).get('fetched_at')]
    state['summary'] = {'updated_at': now(), 'universe': len(tickers), 'on_file': len(have),
                        'waiting': sum(1 for t in tickers if t not in have and not (tk.get(t) or {}).get('fails')),
                        'failing': sum(1 for t in tickers if t not in have and (tk.get(t) or {}).get('fails')),
                        'oldest_first_week': min((tk[t].get('first') for t in have if tk[t].get('first')), default=None),
                        'last_run': done}
    write_json(root / 'state.json', state)
    return done


# ------------------------------------------------------------------ the public files
def grid(today=None):
    """Every Friday from START to the current week's."""
    end = friday(today or dt.date.today())
    n = (end - START).days // 7 + 1
    return [(START + dt.timedelta(days=7 * i)).isoformat() for i in range(n)]


def align(rows, weeks):
    """rows → (index of the first week with a close, closes, volumes) on the grid; gaps inside the history carry the
    last close forward for at most two weeks, then stay empty."""
    at = {r[0]: r for r in rows or []}
    c, v = [None] * len(weeks), [None] * len(weeks)
    first, last_i = None, None
    for i, w in enumerate(weeks):
        r = at.get(w)
        if r:
            c[i], v[i] = r[1], (r[2] if len(r) > 2 else None)
            first = i if first is None else first
            last_i = i
        elif last_i is not None and i - last_i <= 2:
            c[i] = c[last_i]
    if first is None:
        return None, [], []
    return first, c[first:last_i + 1], v[first:last_i + 1]           # nothing carried past the last real close


def sector_indices(companies, series, weeks):
    """One weekly index per site sector: the log-revenue-weighted mean of the members' weekly log returns, cumulated
    from 100 where three or more members have prices. series: ticker → (first, closes)."""
    out = {}
    by = {}
    for c in companies:
        if c['t'] in series:
            by.setdefault(c['s'] or 'other', []).append(c)
    for sec, members in by.items():
        lvl, levels, counts = None, [None] * len(weeks), [0] * len(weeks)
        for i in range(1, len(weeks)):
            num = den = 0.0
            n = 0
            for c in members:
                f, cl = series[c['t']]
                j = i - f
                if j < 1 or j >= len(cl) or cl[j] is None or cl[j - 1] is None or cl[j] <= 0 or cl[j - 1] <= 0:
                    continue
                r = math.log(cl[j] / cl[j - 1])
                if abs(r) > 0.5:                      # a bad tick or an unadjusted split, not a week's move
                    continue
                w = math.log10(max(c['rev'] or 1e6, 1e6))
                num += w * r
                den += w
                n += 1
            counts[i] = n
            if n >= 3:
                lvl = (lvl or 100.0) * math.exp(num / den)
                levels[i] = sig(lvl)
            elif lvl is not None:
                levels[i] = None                        # too few members this week: a gap, the level waits
        first = next((i for i, x in enumerate(levels) if x is not None), None)
        if first is None:
            continue
        last = max(i for i, x in enumerate(levels) if x is not None) + 1
        out[sec] = (first, levels[first:last], counts[first:last], len(members))
    return out


def build(root, site_data=None, data_root=None, top_long=250, quarters_long=64, months_long=None, today=None):
    root = Path(root)
    pub = root / 'public'
    (pub / 't').mkdir(parents=True, exist_ok=True)
    weeks = grid(today)
    companies = site_companies(Path(site_data) / 'index.json') if site_data else []
    names = {}
    try:
        names = json.loads((Path(site_data) / 'index.json').read_text(encoding='utf-8')).get('sector_names') or {}
    except (OSError, ValueError, TypeError):
        pass
    series, written = {}, 0
    meta = {c['t']: c for c in companies}
    for p in sorted((root / 'cache' / 'weekly').glob('*.json.gz')):
        t = p.name[:-len('.json.gz')]
        doc = load(root, t)
        if not doc:
            continue
        f, c, v = align(doc['rows'], weeks)
        if f is None or sum(1 for x in c if x is not None) < 26:
            continue
        c = [sig(x, 5) for x in c]                     # five significant digits and volume in thousands keep the files small
        v = [None if x is None else int(sig(x / 1000, 3)) for x in v]
        series[t] = (f, c, v)
        m = meta.get(t) or {}
        (pub / 't' / f'{t}.json').write_text(json.dumps({'t': t, 'n': m.get('n'), 's': m.get('s'), 'start': weeks[f], 'c': c, 'v': v},
                                                        separators=(',', ':')), encoding='utf-8')
        written += 1
    idx = sector_indices(companies, {t: (f, c) for t, (f, c, _) in series.items()}, weeks)
    ser = []
    for t, sec, name in SECTOR_ETFS:
        if t in series:
            f, c, v = series[t]
            ser.append({'id': t, 'name': name + ' (' + t + ')', 'group': 'sector-etf', 'sector': sec, 'start': weeks[f], 'c': c, 'v': v})
    for t, name in STYLE_ETFS:
        if t in series:
            f, c, v = series[t]
            ser.append({'id': t, 'name': name + ' (' + t + ')', 'group': 'style-etf', 'start': weeks[f], 'c': c, 'v': v})
    for sec, (f, lv, n, members) in sorted(idx.items()):
        ser.append({'id': 's:' + sec, 'name': (names.get(sec) or sec.replace('-', ' ').title()) + ' · site companies', 'group': 'site-sector',
                    'sector': sec, 'members': members, 'start': weeks[f], 'c': lv, 'n': n})
    bench = series.get(BENCH)
    rrg = {'generated_at': now(), 'benchmark': BENCH, 'weeks': weeks[-1], 'start': weeks[0],
           'bench': {'id': BENCH, 'start': weeks[bench[0]], 'c': bench[1], 'v': bench[2]} if bench else None,
           'series': ser,
           'tickers': {t: {'n': (meta.get(t) or {}).get('n'), 's': (meta.get(t) or {}).get('s'), 'rev': (meta.get(t) or {}).get('rev'),
                           'start': weeks[f]} for t, (f, _, _) in series.items() if t in meta},
           'units': {'c': 'weekly close, adjusted', 'v': 'weekly volume, thousands of shares'},
           'note': ('Weekly closes (Friday; adjusted for splits and dividends) from Yahoo Finance, Stooq as the fallback. Site '
                    'sector indices: the Sankey site’s companies in each sector, weekly log returns weighted by the log of '
                    'revenue, from the first week three members have prices — today’s companies only, so the early years '
                    'leave out companies that no longer trade. The RRG lines are computed in the browser from these closes.')}
    (pub / 'rrg.json').write_text(json.dumps(rrg, separators=(',', ':')), encoding='utf-8')
    out = {'tickers_published': written, 'series': len(ser), 'weeks': len(weeks)}
    if site_data and data_root:
        import rotation
        months_long = months_long or max(48, (dt.date.today().year - 2008) * 12 + dt.date.today().month - 1)
        rows = lambda t: (load(root, symbol(t)) or {}).get('rows') if re.fullmatch(r'[A-Za-z0-9.\-]+', t or '') else None
        rot = rotation.build(site_data, data_root, top=top_long, quarters=quarters_long, months=months_long, prices=rows, frames_root=root)
        mon = rot.pop('monthly', None)
        rot['note'] = rot.get('note', '') + (' Long history: weekly closes since 2000 (branch rotation-history); volatility and '
                                             'volume from weekly figures, so they read slightly differently from the recent view.')
        rot['history'] = 'long'
        (pub / 'rotation-long.json').write_text(json.dumps(rot, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        if mon:
            (pub / 'rotation-long-monthly.json').write_text(json.dumps(mon, separators=(',', ':')), encoding='utf-8')
        out.update(long_companies=len(rot['companies']), long_quarters=[rot['quarters'][0], rot['quarters'][-1]] if rot['quarters'] else None,
                   long_months=len((mon or {}).get('months', [])))
    write_json(pub / 'status.json', {'built_at': now(), **out, 'collector': read_json(root / 'state.json', {}).get('summary')})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['collect', 'frames', 'build'])
    ap.add_argument('--root', default='hist')
    ap.add_argument('--site-index', default=None, help="the Sankey site's data/index.json (collect)")
    ap.add_argument('--site-data', default=None, help="the folder holding the Sankey site's index.json (build)")
    ap.add_argument('--data', default=None, help="the hub's data folder (13F, officials and options history for the long build)")
    ap.add_argument('--batch', type=int, default=300)
    ap.add_argument('--refresh', type=int, default=400)
    ap.add_argument('--minutes', type=float, default=25)
    ap.add_argument('--tickers', default='', help='fetch these first, in full (comma or space separated)')
    ap.add_argument('--quarters', type=int, default=72)
    a = ap.parse_args()
    cfg = read_json(Path(__file__).resolve().parents[1] / 'config' / 'settings.json', {})
    http = cfg.get('http', {})
    import tempfile
    client = Client(tempfile.mkdtemp(prefix='rh-raw-'),            # raw responses stay out of the branch
                    {**http, 'host_intervals': {**http.get('host_intervals', {}), 'query1.finance.yahoo.com': 0.8, 'stooq.com': 1.0,
                                                'data.sec.gov': 0.15}})
    if a.cmd == 'collect':
        extra = [t for t in re.split(r'[\s,;]+', a.tickers or '') if t]
        print(json.dumps(collect(client, a.root, universe(a.site_index, extra), a.batch, a.refresh, a.minutes, first=extra)))
    elif a.cmd == 'frames':
        import frames
        print(json.dumps(frames.collect(client, a.root, a.quarters)))
    else:
        print(json.dumps(build(a.root, a.site_data, a.data)))


if __name__ == '__main__':
    main()
