"""Long history for the rotation charts: the branch "rotation-history" (.github/workflows/rotation-history.yml).

  collect  weekly closes (dividend- and split-adjusted, and as traded), weekly volume, dividends and splits since each
           listing — Yahoo's weekly chart, Stooq's daily file resampled to weeks as the fallback (closes and volume
           only) — for SPY (the benchmark), the SPDR sector
           ETFs, a set of style / size / asset-class ETFs and every company of the Sankey site, largest first. A run
           takes a batch of new tickers and refreshes the stalest ones (the last months only), within a time budget;
           failures wait longer after each try. Progress lives in state.json, so any run can stop and the next goes on.
  frames   the SEC XBRL frames of revenue, operating income, gross profit, net income and cost of revenue back to 2009
           (app/frames.py into the same folder; quarters on file are final and never fetched again)
  build    public/ — what the site loads:
             rrg.json                 one Friday grid since 2000: SPY, the ETFs and one index per site sector
                                      (the site's companies, weighted by the log of revenue), closes and volume; the
                                      charts compute the RRG (RS-Ratio, RS-Momentum) from these in the browser
             t/<TICKER>.json          one company's weekly closes and volume, loaded when a chart traces it; once fetched
                                      with events also p (the close as traded, split-adjusted), d ([[week, dividend per
                                      share]], weeks counted from start) and sp ([[week, split ratio]])
             rotation-long.json       the momentum clock's variables (app/rotation.py) for 70 quarters (since 2009Q2, so
                                      the arrows and charts start in 2010)
             rotation-long-monthly.json  … and month by month since 2008, from the weekly closes
             rank/                    the video studio's leaderboards (rank_panel): every company's month-end total-return
                                      close, monthly dollar volume and market value, and quarterly revenue, gross profit,
                                      operating income, net income and equity from the SEC frames

    python app/rotation_history.py collect --root hist --site-index site/index.json --batch 300 --minutes 25
    python app/rotation_history.py frames  --root hist --quarters 76
    python app/rotation_history.py build   --root hist --site-data site --data docs/data
"""
import argparse
import bisect
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
FORMAT = 3                                        # state.json format: 1 held quarterly bars from range=max; 2 had no
                                                  # dividends, splits or closes as traded — each fetched again in full
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
    """[(date, close, volume or None[, close as traded])] in any order → [[friday, the week's last close, its volume[,
    its last close as traded]]] by week. Daily rows add up their volume; weekly bars (add_volume=False) already hold the
    week's, and a second bar for the same week (Yahoo's latest day of an unfinished week) replaces it."""
    weeks = {}
    for row in sorted(days, key=lambda r: r[0]):
        d, c, v = row[:3]
        p = row[3] if len(row) > 3 else None
        if c is None or not math.isfinite(c) or c <= 0:
            continue
        k = friday(d).isoformat()
        w = weeks.get(k)
        weeks[k] = [k, c, ((w[2] if w else 0) + (v or 0)) if add_volume else (v or (w[2] if w else 0)),
                    p if p is not None and math.isfinite(p) and p > 0 else None]
    return [[k, sig(c), int(v)] + ([sig(p)] if p is not None else []) for k, c, v, p in (weeks[k] for k in sorted(weeks))]


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
    traded = (q.get('close') or []) if adj else []          # split-adjusted, not for dividends (market value, the price line)
    off = ((r.get('meta') or {}).get('gmtoffset') or 0)
    days = []
    for i, ts in enumerate(stamps):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        d = dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).date()
        p = traded[i] if i < len(traded) and traded[i] is not None else None
        days.append((d, float(c), vols[i] if i < len(vols) and vols[i] is not None else None) + ((float(p),) if p is not None else ()))
    rows = weekly_rows(days, add_volume=False)
    if not rows:
        raise ValueError('no weekly rows in the chart response')
    check_weekly(rows)
    return rows


def yahoo_events(payload):
    """{'div': [[ex-date, amount per share]], 'split': [[date, new shares per old share]]} from a chart answer
    (amounts adjusted for later splits, like the closes)."""
    r = (((payload or {}).get('chart') or {}).get('result') or [{}])[0] or {}
    ev, off = r.get('events') or {}, ((r.get('meta') or {}).get('gmtoffset') or 0)
    day = lambda e, k: dt.datetime.fromtimestamp(int(e.get('date') or k) + off, dt.timezone.utc).date().isoformat()
    div, split = {}, {}
    for k, e in (ev.get('dividends') or {}).items():
        a = e.get('amount')
        if a is not None and math.isfinite(float(a)) and float(a) > 0:
            div[day(e, k)] = div.get(day(e, k), 0) + float(a)
    for k, e in (ev.get('splits') or {}).items():
        n, m = e.get('numerator'), e.get('denominator')
        if n and m and float(n) > 0 and float(m) > 0 and float(n) != float(m):
            split[day(e, k)] = float(n) / float(m)
    return {'div': [[d, sig(v)] for d, v in sorted(div.items())], 'split': [[d, sig(v)] for d, v in sorted(split.items())]}


def merge_events(old, new):
    """The events of a refresh (the last months) added to those on file; the newer answer wins for the same day."""
    if not old:
        return new
    if not new:
        return old
    out = {}
    for k in ('div', 'split'):
        by = {d: v for d, v in old.get(k) or []}
        by.update({d: v for d, v in new.get(k) or []})
        out[k] = [[d, by[d]] for d in sorted(by)]
    return out


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
    """The weeks of a refresh merged into those on file. Yahoo restates every earlier close after each new dividend or
    split (adjusted closes, closes as traded and volume), so the rows on file are first put on the new basis — scaled
    by the ratio of the two answers in the first week they share (every dividend or split after that week moves every
    earlier week by the same factor). Without it each new dividend would leave a step down where the refresh starts."""
    old, new = old or [], new or []
    if old and new:
        at = {r[0]: r for r in old}
        k = next((r for r in new if r[0] in at), None)
        if k is not None:
            o = at[k[0]]
            ka = k[1] / o[1] if o[1] and k[1] else 1.0
            kp = k[3] / o[3] if len(k) > 3 and len(o) > 3 and o[3] and k[3] else None
            if not (0.001 < ka < 1000) or (kp is not None and not (0.001 < kp < 1000)):
                ka, kp = 1.0, None
            if abs(ka - 1) > 1e-9 or (kp is not None and abs(kp - 1) > 1e-9):
                old = [[r[0], sig(r[1] * ka), (int(round(r[2] / kp)) if kp and r[2] is not None else r[2])]
                       + ([sig(r[3] * kp) if kp else r[3]] if len(r) > 3 else []) if r[0] < k[0] else r for r in old]
    by = {r[0]: r for r in old}
    by.update({r[0]: r for r in new})
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


def fetch(client, ticker, full=True, sources=('yahoo', 'stooq'), with_events=False):
    """(weekly rows, source) — the whole history (full) or the last six months; raises with every source's error.
    with_events: (rows, source, events or None) — Yahoo's dividends and splits; Stooq has none."""
    problems = []
    for src in sources:
        try:
            if src == 'yahoo':
                p2 = int(time.time()) + 86400
                p1 = int(dt.datetime(1999, 12, 27, tzinfo=dt.timezone.utc).timestamp()) if full else p2 - 200 * 86400
                body = client.json(YAHOO.format(s=symbol(ticker), p1=p1, p2=p2))
                rows = parse_yahoo(body)
                return (rows, 'yahoo', yahoo_events(body)) if with_events else (rows, 'yahoo')
            if src == 'stooq':
                rows = parse_stooq(client.get(STOOQ.format(s=symbol(ticker).lower() + '.us')).decode('utf-8', 'replace'))
                rows = rows if full else rows[-30:]
                return (rows, 'stooq', None) if with_events else (rows, 'stooq')
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
                       'filed': r.get('filed') or '', 'sic': str(r.get('sic') or ''), 'ind': r.get('industry') or ''}
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
            rows, src, ev = fetch(client, t, full=full or not load(root, t), with_events=True)
            doc = load(root, t) if not full else None
            if doc:                                    # a refresh: the last months merged into what is on file
                rows = merge(doc['rows'], rows)
                ev = merge_events(doc.get('ev'), ev) if 'ev' in doc else None   # events only once a full answer had them
            out = {'ticker': t, 'source': src, 'fetched_at': now(), 'rows': rows}
            if ev is not None:
                out['ev'] = ev
            save(root, t, out)
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


def revenue_history(root, companies, since='CY2009Q1', filed_after=46):
    """{ticker: (dates, revenues)}: each company's quarterly revenue from the SEC frames, dated when it was public —
    46 days after the quarter (the 10-Q deadline is 40–45 days). Used as of each week by sector_indices."""
    import frames as FR
    today = dt.date.today()
    n = (today.year - int(since[2:6])) * 4 + (today.month - 1) // 3 - (int(since[-1]) - 1)
    periods = FR.calendar_quarters(max(1, n))
    try:
        rev = FR.revenues(root, periods)
    except Exception:
        return {}
    out = {}
    for c in companies:
        per = rev.get(str(c.get('cik'))) or rev.get(c.get('cik')) or {}
        pts = []
        for p, v in per.items():
            y, q = int(p[2:6]), int(p[-1])
            end = dt.date(y + (q == 4), (3 * q) % 12 + 1, 1) - dt.timedelta(days=1)
            pts.append(((end + dt.timedelta(days=filed_after)).isoformat(), v))
        if pts:
            pts.sort()
            out[c['t']] = ([d for d, _ in pts], [v for _, v in pts])
    return out


SIC_LEVELS = (('sic4', 4), ('sic3', 3), ('sic2', 2))


def industry_benchmarks(companies, series, weeks, rev_hist=None, min_members=5, volumes=None, min_price=3.0,
                        min_dollar_volume=10e6, industries=None):
    """{ticker: {level, code, label, members, ex, all}}: per company the most specific industry group — SIC4, else SIC3,
    SIC2, the site sector — with at least min_members OTHER companies that have weekly prices, and two weekly indices on
    the full grid: 'ex' leaves the company out (the leave-one-out benchmark a company is compared with, so a dominant
    stock does not define its own peers), 'all' includes it (the industry's own line against the market). Log-revenue
    weights as reported by each week (rev_hist), weekly log returns over 50% skipped as bad ticks, a week needs three
    contributing members; levels start at 100. Membership is today's companies (survivorship, stated on the page).
    With volumes ({ticker: weekly shares on the series' weeks}), a member contributes a week only while it is liquid —
    close ≥ min_price and mean weekly dollar volume over the last 13 weeks ≥ min_dollar_volume — so small illiquid
    members do not bend the benchmark (notes/dual-rrg: against all members, an industry's trend mostly measured its
    illiquid members running further than its liquid ones).
    With industries (a dict), each industry some company is benchmarked against is also filled in once, keyed
    'level:code': {level, code, label, members, tickers (largest revenue first), all} — the industry's own line."""
    have = [c for c in companies if c['t'] in series]
    groups = {}
    for c in have:
        sic = re.sub(r'\D', '', c.get('sic') or '')
        keys = [(lvl, sic[:k]) for lvl, k in SIC_LEVELS if len(sic) >= k and sic[:k].strip('0')]
        if c.get('s') and c['s'] != 'other':
            keys.append(('sector', c['s']))
        c['_keys'] = keys
        for k in keys:
            groups.setdefault(k, []).append(c)
    W = len(weeks)

    def weight(c, i):
        if rev_hist is not None:
            h = rev_hist.get(c['t'])
            k = bisect.bisect_right(h[0], weeks[i]) - 1 if h else -1
            rv = h[1][k] if k >= 0 else None
        else:
            rv = c.get('rev')
        return math.log10(max(rv or 1e6, 1e6))

    def returns(c):
        f, cl = series[c['t']]
        r = [None] * W
        for i in range(max(1, f), min(W, f + len(cl))):
            j = i - f
            if j >= 1 and cl[j] is not None and cl[j - 1] is not None and cl[j] > 0 and cl[j - 1] > 0:
                x = math.log(cl[j] / cl[j - 1])
                r[i] = x if abs(x) <= 0.5 else None
        return r
    def liquid(c):
        if volumes is None or c['t'] not in volumes:
            return None
        f, cl = series[c['t']]
        vol = volumes[c['t']]
        ok = [False] * W
        win = []
        for i in range(f, min(W, f + len(cl))):
            j = i - f
            px, v = cl[j], (vol[j] if j < len(vol) else None)
            win.append(px * v if px is not None and v is not None else None)
            if len(win) > 13:
                win.pop(0)
            vals = [x for x in win if x is not None]
            ok[i] = px is not None and px >= min_price and len(vals) >= 10 and sum(vals) / len(vals) >= min_dollar_volume
        return ok
    rets = {}
    for c in have:
        r, ok = returns(c), liquid(c)
        rets[c['t']] = r if ok is None else [x if ok[i] and ok[i - 1] else None for i, x in enumerate(r)]
    wts = {c['t']: [weight(c, i) for i in range(W)] for c in have}
    totals = {}

    def total(key):
        if key not in totals:
            tot, den, n = [0.0] * W, [0.0] * W, [0] * W
            for c in groups[key]:
                r, wc = rets[c['t']], wts[c['t']]
                for i in range(W):
                    if r[i] is not None:
                        w = wc[i]
                        tot[i] += w * r[i]; den[i] += w; n[i] += 1
            totals[key] = (tot, den, n)
        return totals[key]

    def level(tot, den, n, own=None):
        lv, out = None, [None] * W
        for i in range(1, W):
            t_, d_, k_ = tot[i], den[i], n[i]
            if own is not None and own[0][i] is not None:
                t_ -= own[1][i] * own[0][i]; d_ -= own[1][i]; k_ -= 1
            if k_ >= 3 and d_ > 0:
                lv = (lv or 100.0) * math.exp(t_ / d_)
                out[i] = sig(lv)
        return out
    out = {}
    for c in have:
        key = next((k for k in c.pop('_keys') if len(groups[k]) - 1 >= min_members), None)
        if key is None:
            continue
        tot, den, n = total(key)
        r = rets[c['t']]
        own = (r, [wts[c['t']][i] if r[i] is not None else 0.0 for i in range(W)])
        name = c.get('ind') if key[0] == 'sic4' and c.get('ind') else ''
        label = (f'SIC {key[1]}' + (f' · {name}' if name else '') if key[0] != 'sector' else f'{key[1].replace("-", " ").title()} sector')
        k = f'{key[0]}:{key[1]}'
        if industries is not None and k in industries:
            whole = industries[k]['all']
        else:
            whole = level(tot, den, n)
            if industries is not None:
                names = [m.get('ind') for m in groups[key] if m.get('ind')]
                industries[k] = {'level': key[0], 'code': key[1], 'label': label, 'members': len(groups[key]),
                                 'ind': max(set(names), key=names.count) if names else '',
                                 'tickers': [m['t'] for m in sorted(groups[key], key=lambda m: -(m.get('rev') or 0))], 'all': whole}
        out[c['t']] = {'level': key[0], 'code': key[1], 'members': len(groups[key]), 'label': label,
                       'ex': level(tot, den, n, own), 'all': whole}
    return out


def sector_indices(companies, series, weeks, rev_hist=None):
    """One weekly index per site sector: the log-revenue-weighted mean of the members' weekly log returns, cumulated
    from 100 where three or more members have prices. series: ticker → (first, closes). With rev_hist (revenue_history)
    each week weighs a company by the revenue it had reported by then (floor $1M before any is on file), so a past
    week never uses revenue reported later; without it, today's revenue (the older behaviour)."""
    out = {}
    by = {}
    for c in companies:
        if c['t'] in series and c['s'] and c['s'] != 'other':      # "other" is not a sector
            by.setdefault(c['s'], []).append(c)
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
                if rev_hist is not None:
                    h = rev_hist.get(c['t'])
                    k = bisect.bisect_right(h[0], weeks[i]) - 1 if h else -1
                    rv = h[1][k] if k >= 0 else None
                else:
                    rv = c['rev']
                w = math.log10(max(rv or 1e6, 1e6))
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


def build(root, site_data=None, data_root=None, top_long=250, quarters_long=70, months_long=None, today=None):
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
    series, written, extra, docs = {}, 0, {}, {}
    meta = {c['t']: c for c in companies}
    wk = {w: i for i, w in enumerate(weeks)}
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
        if t in meta:
            docs[t] = doc
        ev = doc.get('ev')
        if ev is not None:                             # dividends (and the close as traded) for the studio's price lines
            n, x = len(c), {}
            traded = [[r[0], r[3], None] for r in doc['rows'] if len(r) > 3 and r[3]]
            f2, pc, _ = align(traded, weeks) if traded else (None, [], [])
            if f2 is not None and f2 >= f:
                pc = [None] * (f2 - f) + pc
                x['p'] = [sig(y, 5) for y in pc[:n]]
            d = {}
            for day, amt in ev.get('div') or []:
                i = wk.get(friday(dt.date.fromisoformat(day)).isoformat())
                if i is not None and f <= i < f + n:
                    d[i - f] = d.get(i - f, 0) + amt
            x['d'] = [[i, sig(a, 5)] for i, a in sorted(d.items())]
            x['sp'] = [[wk[friday(dt.date.fromisoformat(day)).isoformat()] - f, r] for day, r in ev.get('split') or []
                       if friday(dt.date.fromisoformat(day)).isoformat() in wk and wk[friday(dt.date.fromisoformat(day)).isoformat()] >= f]
            extra[t] = x
    rev_hist = revenue_history(root, companies) if companies else None
    # each company's industry benchmark (research spec v5 §4.2): the most specific SIC level with enough members, the
    # index without the company itself (bx) and with it (bi), weights = revenue reported by each week
    inds = {}
    bench_of = industry_benchmarks(companies, {t: (f, c) for t, (f, c, _) in series.items()}, weeks, rev_hist or None,
                                   volumes={t: [None if x is None else 1000.0 * x for x in v] for t, (f, c, v) in series.items()},
                                   industries=inds)
    for t, (f, c, v) in series.items():
        m = meta.get(t) or {}
        doc = {'t': t, 'n': m.get('n'), 's': m.get('s'), 'start': weeks[f], 'c': c, 'v': v, **extra.get(t, {})}
        b = bench_of.get(t)
        if b:                                       # the benchmarks on the company's own weeks (same start)
            doc.update(bl=b['label'], blevel=b['level'], bcode=b['code'], bid=f"{b['level']}:{b['code']}", bn=b['members'], bx=b['ex'][f:f + len(c)], bi=b['all'][f:f + len(c)])
        (pub / 't' / f'{t}.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
        written += 1
    idx = sector_indices(companies, {t: (f, c) for t, (f, c, _) in series.items()}, weeks, rev_hist or None)
    if rev_hist:                                   # for the gravity model's planet weights (gravity_pendulum.load)
        (pub / 'revenue-history.json').write_text(json.dumps({
            'note': 'Quarterly revenue per ticker from SEC frames, dated 46 days after the quarter (when it was public).',
            'rows': {t: [[d, sig(v, 4)] for d, v in zip(*h)] for t, h in rev_hist.items()}}, separators=(',', ':')), encoding='utf-8')
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
    # every industry a company is benchmarked against, as its own line (industry RRG: Markov odds, replays and the
    # move that puts it in each quadrant, per industry)
    ind_rows = []
    for k, v in sorted(inds.items(), key=lambda kv: (-kv[1]['members'], kv[0])):
        lv = v['all']
        first = next((i for i, x in enumerate(lv) if x is not None), None)
        if first is None:
            continue
        last = max(i for i, x in enumerate(lv) if x is not None) + 1
        ind_rows.append({'id': k, 'level': v['level'], 'code': v['code'], 'label': v['label'], 'ind': v['ind'], 'members': v['members'],
                     'tickers': v['tickers'], 'start': weeks[first], 'c': lv[first:last]})
    (pub / 'industries.json').write_text(json.dumps({
        'generated_at': now(), 'benchmark': BENCH, 'start': weeks[0], 'weeks': weeks[-1], 'rows': ind_rows,
        'note': ('One weekly index per industry that a company on the site is benchmarked against (the most specific SIC '
                 'level — SIC4, else SIC3, SIC2, the site sector — with at least five other companies with prices): weekly log '
                 'returns of its members, weighted by the log of the revenue each had reported by that week, a member counted '
                 'only while liquid (≥ $3, ≥ $10M a week), from the first week three members have prices; level 100 at the '
                 'start. Today\'s companies only (survivorship).')}, separators=(',', ':')), encoding='utf-8')
    bench = series.get(BENCH)
    rrg = {'generated_at': now(), 'benchmark': BENCH, 'weeks': weeks[-1], 'start': weeks[0],
           'bench': {'id': BENCH, 'start': weeks[bench[0]], 'c': bench[1], 'v': bench[2]} if bench else None,
           'series': ser,
           'tickers': {t: {'n': (meta.get(t) or {}).get('n'), 's': (meta.get(t) or {}).get('s'), 'rev': (meta.get(t) or {}).get('rev'),
                           'start': weeks[f]} for t, (f, _, _) in series.items() if t in meta},
           'units': {'c': 'weekly close, adjusted', 'v': 'weekly volume, thousands of shares'},
           'note': ('Weekly closes (Friday; adjusted for splits and dividends) from Yahoo Finance, Stooq as the fallback. Site '
                    'sector indices: the Sankey site’s companies in each sector, weekly log returns weighted by the log of '
                    'the revenue each had reported by that week (SEC frames, counted 46 days after the quarter), from the '
                    'first week three members have prices — today’s companies only, so the early years '
                    'leave out companies that no longer trade. The RRG lines are computed in the browser from these closes.')}
    (pub / 'rrg.json').write_text(json.dumps(rrg, separators=(',', ':')), encoding='utf-8')
    out = {'tickers_published': written, 'series': len(ser), 'weeks': len(weeks), 'industries': len(ind_rows),
           'with_dividends': len(extra)}
    try:                                           # the studio's leaderboards (rank_panel.py)
        import rank_panel
        out['rank'] = rank_panel.build(pub / 'rank', companies, docs, frames_root=root, today=today, names=names)
    except Exception as exc:                       # never lose the rest of the build to it
        out['rank'] = {'error': str(exc)[:300]}
    if site_data and data_root:
        import rotation
        months_long = months_long or max(48, (dt.date.today().year - 2008) * 12 + dt.date.today().month - 1)
        rows = lambda t: (load(root, symbol(t)) or {}).get('rows') if re.fullmatch(r'[A-Za-z0-9.\-]+', t or '') else None
        rot = rotation.build(site_data, data_root, top=top_long, quarters=quarters_long, months=months_long, prices=rows, frames_root=root,
                             vol_windows=(8, 24))       # volume against the last two years, not the whole history
        mon = rot.pop('monthly', None)
        rot['note'] = rot.get('note', '') + (' Long history: weekly closes since 2000 (branch rotation-history); volatility and '
                                             'volume from weekly figures, and volume against the trailing two years (eight '
                                             'quarters, 24 months), so they read slightly differently from the recent view.')
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
    ap.add_argument('--quarters', type=int, default=76)
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
