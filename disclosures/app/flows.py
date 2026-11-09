"""Money flows (Rotation → RRG): big-money net buying and net money inflow, week by week. Kept on the branch
"research-flows" (.github/workflows/research-flows.yml); scan.yml publishes public/ at disclosures/data/research/flows/,
drawn by docs/rrg-flow.js on the RRG (the flow arrows, the money-flow quadrants and their guide).

US markets publish no "main force" (large-order) figures, so both measures are estimates from public files:

  big-money net buying   FINRA's daily short sale volume of off-exchange trades (the trade reporting facilities, where
                         dark-pool and block trades are reported). A dealer that fills a client's buy order from its own
                         book reports a short sale, so the short share of off-exchange volume rises when buyers dominate
                         there (the idea behind the "dark index", DIX). A week's net buying = 2 × (the week's short share −
                         the ticker's own short share over the 52 weeks before) × its off-exchange volume, in dollars at the
                         week's average price: above zero, more buying off-exchange than is usual for this ticker.
  net money inflow       Chaikin's money flow from the daily bars: each day's dollar volume weighted by where the close
                         sits in the day's range, ((close − low) − (high − close)) / (high − low) — +1 at the high, −1 at
                         the low — added up over the week.

Both are also read as a share of the ticker's dollar volume (turnover) over the same weeks, so a quiet ETF and a busy
stock read on one scale. FINRA's volumes are shares as traded and the daily bars are split-adjusted: a split shows as a
step in the ratio of the two volumes, which is found and taken out (split_steps).

  collect  cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt (the consolidated file, from 2018-08-01): each
           weekday once, newest first within a time budget, its short and total volume added to its week (the Friday)
           in cache/finra/<YYYY>.json.gz; state.json keeps the weekdays FINRA has no file for (holidays).
  build    public/t/<TICKER>.json for every ticker with daily bars (research-paths cache/ohlc/) and public/index.json:
           the tickers, the week grid, and what followed each quadrant — every ticker-week since the baseline begins,
           pooled, 4 and 13 weeks on against SPY, with the top and bottom fifths of each measure week by week.

    python app/flows.py collect --root F --minutes 20
    python app/flows.py build --root F --bars research-paths/cache/ohlc
"""
import argparse
import datetime as dt
import gzip
import io
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

FINRA = 'https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt'
FIRST_DAY = dt.date(2018, 8, 1)                # the first consolidated (CNMS) file
UA = 'FilingFlows/1.0 (+https://filing-flows.com)'   # a plain reader: no contact address is sent
SYM = re.compile(r'[A-Z][A-Z0-9-]{0,9}')
BASE_WEEKS = 52                                # the ticker's own normal short share: the 52 weeks before
BASE_MIN = 26                                  # … from at least this many of them
WINDOW = 4                                     # the guide's weeks per reading (the chart's default)
HORIZONS = (4, 13)                             # weeks on, for what followed each quadrant
MIN_DV = 5e6                                   # the pooled stats: tickers that traded at least $5M a week on average
USUAL = [2, 3, 4, 5, 10, 20]                   # split ratios (and their inverses, reverse splits)
RARER = [1.25, 1.5, 6, 7, 8, 12, 15, 25, 30, 40, 50]
QUADS = ['Accumulation', 'Quiet buying', 'Outflow', 'Distribution']   # as the RRG's: top-right, bottom-right, bottom-left, top-left
BENCH = 'SPY'


def friday(d):
    """The Friday of a weekday's week (the RRG's weekly grid is Fridays)."""
    return d + dt.timedelta(days=4 - d.weekday())


def norm_symbol(s):
    t = (s or '').strip().upper().replace('/', '-').replace('.', '-')
    return t if SYM.fullmatch(t) else None


# ------------------------------------------------------------------ FINRA's daily files
def parse_day(text):
    """{symbol: (short volume, total volume)} from one day's file (Date|Symbol|ShortVolume|ShortExemptVolume|
    TotalVolume|Market); the trailing record count and anything unreadable are skipped."""
    out = {}
    for line in text.splitlines()[1:]:
        p = line.split('|')
        if len(p) < 5:
            continue
        sym = norm_symbol(p[1])
        try:
            sv, tv = float(p[2]), float(p[4])
        except ValueError:
            continue
        if not sym or not (tv > 0) or sv < 0 or not math.isfinite(sv + tv):
            continue
        a = out.get(sym)
        out[sym] = (a[0] + sv, a[1] + tv) if a else (sv, tv)
    return out


def http_get(url, timeout=60):
    """(status, text): 200 and the file, or the HTTP status FINRA answered (403 for a day with no file)."""
    try:
        with urlopen(Request(url, headers={'User-Agent': UA, 'Accept': 'text/plain,*/*'}), timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except HTTPError as e:
        return e.code, ''
    except (URLError, TimeoutError, OSError) as e:
        return 0, str(e)


class Store:
    """cache/finra/<YYYY>.json.gz (the year of the week's Friday), whole shares as traded, symbol by symbol:
    {'weeks': [fridays], 'days': {friday: [days]}, 'sv': {symbol: [short volume each week]}, 'tv': {symbol: [total]}}
    (0: no trades that week). In memory, week by week: {'weeks': {friday: {'days': [...], 's': {symbol: [sv, tv]}}}}."""

    def __init__(self, root):
        self.dir = Path(root) / 'cache' / 'finra'
        self.years, self.dirty = {}, set()

    def year(self, y):
        if y not in self.years:
            doc = read_year(self.dir / f'{y}.json.gz')
            W = {}
            for i, fr in enumerate(doc.get('weeks') or []):
                W[fr] = {'days': list((doc.get('days') or {}).get(fr, [])), 's': {}}
            for sym, a in (doc.get('sv') or {}).items():
                t = doc['tv'].get(sym) or []
                for i, fr in enumerate(doc['weeks']):
                    if i < len(t) and t[i]:
                        W[fr]['s'][sym] = [a[i], t[i]]
            self.years[y] = {'weeks': W}
        return self.years[y]

    def days(self):
        """Every day on file (from the years in the folder; read without loading the volumes into weeks)."""
        out = set()
        for p in sorted(self.dir.glob('*.json.gz')):
            y = int(p.name[:4])
            if y in self.years:
                for w in self.years[y]['weeks'].values():
                    out.update(w['days'])
            else:
                for d in (read_year(p).get('days') or {}).values():
                    out.update(d)
        return out

    def add(self, day, rows):
        fr = friday(day)
        W = self.year(fr.year)['weeks'].setdefault(fr.isoformat(), {'days': [], 's': {}})
        d = day.isoformat()
        if d in W['days']:
            return False
        W['days'] = sorted(W['days'] + [d])
        S = W['s']
        for sym, (sv, tv) in rows.items():
            a = S.get(sym)
            if a:
                a[0] += round(sv)
                a[1] += round(tv)
            else:
                S[sym] = [round(sv), round(tv)]
        self.dirty.add(fr.year)
        return True

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        for y in sorted(self.dirty):
            W = self.years[y]['weeks']
            weeks = sorted(W)
            syms = sorted({s for fr in weeks for s in W[fr]['s']})
            doc = {'weeks': weeks, 'days': {fr: W[fr]['days'] for fr in weeks},
                   'sv': {s: [W[fr]['s'].get(s, (0, 0))[0] for fr in weeks] for s in syms},
                   'tv': {s: [W[fr]['s'].get(s, (0, 0))[1] for fr in weeks] for s in syms}}
            raw = json.dumps(doc, separators=(',', ':')).encode('utf-8')
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb', mtime=0, compresslevel=9) as f:
                f.write(raw)
            tmp = self.dir / f'{y}.json.gz.tmp'
            tmp.write_bytes(buf.getvalue())
            tmp.replace(self.dir / f'{y}.json.gz')
        self.dirty = set()


def read_year(p):
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def weekdays(a, b):
    d, out = a, []
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def collect(root, minutes=20, today=None, get=http_get, pause=0.05, log=print):
    """Every weekday from 2018-08-01 to today not yet on file, newest first, until the time budget is spent. A day with
    no file (403/404) is remembered once it is four days old (a holiday); a newer one is asked again next run."""
    root = Path(root)
    today = today or dt.datetime.now(dt.timezone.utc).date()
    st_path = root / 'cache' / 'finra' / 'state.json'
    try:
        state = json.loads(st_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    none = set(state.get('none', []))
    store = Store(root)
    have = store.days()
    todo = [d for d in reversed(weekdays(FIRST_DAY, today)) if d.isoformat() not in have and d.isoformat() not in none]
    end, got, missing, errors = time.monotonic() + minutes * 60, 0, 0, 0
    for i, d in enumerate(todo):
        if time.monotonic() > end:
            break
        status, text = get(FINRA.format(d=d.strftime('%Y%m%d')))
        if status == 200 and text:
            rows = parse_day(text)
            if len(rows) > 500:                        # a real day has thousands of symbols
                store.add(d, rows)
                got += 1
            else:
                errors += 1
        elif status in (403, 404):
            missing += 1
            if (today - d).days > 4:
                none.add(d.isoformat())
        else:
            errors += 1
            log(f'FINRA {d}: {status} {text[:120]}')
            if errors >= 12:
                log('too many errors: stopping this run')
                break
        if got and got % 60 == 0:
            store.save()
        time.sleep(pause)
    store.save()
    left = len(todo) - got - missing
    state.update({'none': sorted(none), 'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                  'days_on_file': len(have) + got, 'last_run': {'fetched': got, 'no_file': missing, 'errors': errors, 'left': max(0, left)}})
    st_path.parent.mkdir(parents=True, exist_ok=True)
    st_path.write_text(json.dumps(state, indent=1), encoding='utf-8')
    log(f'FINRA short volume: {got} days fetched, {missing} with no file, {errors} errors, about {max(0, left)} left')
    return state


def load_finra(root, symbols=None):
    """(fridays, {symbol: (short[], total[])}) on one continuous weekly grid, None where a week has no figure — every
    symbol, or only those asked for."""
    folder = Path(root) / 'cache' / 'finra'
    docs = [read_year(p) for p in sorted(folder.glob('*.json.gz'))]
    allw = sorted({w for d in docs for w in d.get('weeks') or []})
    if not allw:
        return [], {}
    w0, w1 = dt.date.fromisoformat(allw[0]), dt.date.fromisoformat(allw[-1])
    grid = [(w0 + dt.timedelta(days=7 * i)).isoformat() for i in range((w1 - w0).days // 7 + 1)]
    pos = {w: i for i, w in enumerate(grid)}
    out = {}
    for d in docs:
        at = [pos[w] for w in d['weeks']]
        for sym, a in d['sv'].items():
            if symbols is not None and sym not in symbols:
                continue
            t = d['tv'][sym]
            o = out.get(sym)
            if o is None:
                o = out[sym] = ([None] * len(grid), [None] * len(grid))
            for k, i in enumerate(at):
                if t[k]:
                    o[0][i], o[1][i] = a[k], t[k]
        d.clear()                                      # one year at a time in memory
    return grid, out


# ------------------------------------------------------------------ the daily bars (research-paths cache/ohlc)
def read_gz(p):
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_bars(folder, ticker):
    """One ticker's daily bars: the base part (before the last two months) joined to the recent part."""
    folder = Path(folder)
    rec = read_gz(folder / f'{ticker}.json.gz')
    if not rec or not rec.get('t'):
        return None
    if rec.get('base'):
        base = read_gz(folder / f'{ticker}.base.json.gz')
        if base:
            for k in ('t', 'o', 'h', 'l', 'c', 'ac', 'v'):
                rec[k] = (base.get(k) or []) + (rec.get(k) or [])
    return rec


def weekly_bars(bars, grid):
    """On the weekly grid: dollar volume, Chaikin money flow (dollars), share volume and the week's last adjusted close."""
    n = len(grid)
    pos = {w: i for i, w in enumerate(grid)}
    dv, mf, vol, ac = [None] * n, [None] * n, [None] * n, [None] * n
    t, h, l, c, a, v = (bars.get(k) or [] for k in ('t', 'h', 'l', 'c', 'ac', 'v'))
    for j, d in enumerate(t):
        i = pos.get(friday(dt.date.fromisoformat(d)).isoformat())
        if i is None:
            continue
        cj, hj, lj, vj = (x[j] if j < len(x) else None for x in (c, h, l, v))
        if cj is None or vj is None or cj <= 0 or vj < 0:
            continue
        clv = ((cj - lj) - (hj - cj)) / (hj - lj) if hj is not None and lj is not None and hj > lj else 0.0
        clv = max(-1.0, min(1.0, clv))
        d_ = cj * vj
        dv[i] = (dv[i] or 0) + d_
        mf[i] = (mf[i] or 0) + clv * d_
        vol[i] = (vol[i] or 0) + vj
        if j < len(a) and a[j] is not None:
            ac[i] = a[j]
    return dv, mf, vol, ac


def snap(r):
    """A volume-ratio step as a split ratio: the nearest of the usual ones (2, 3, 4, 5, 10, 20 and their inverses) within
    15%, else a rarer one within 8%; None when it is neither (not a split)."""
    def nearest(cands, tol):
        best = None
        for c in cands:
            for x in (c, 1 / c):
                e = abs(math.log(r / x))
                if e < tol and (best is None or e < best[1]):
                    best = (x, e)
        return best
    a, b = nearest(USUAL, 0.15), nearest(RARER, 0.08)
    if a and b:
        return b[0] if b[1] < a[1] - 0.05 else a[0]
    return (a or b or (None,))[0]


def _sigma(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))


def split_steps(q, span=8, need=5, jump=math.log(1.8), gap=3):
    """FINRA counts shares as traded, the daily bars are split-adjusted: their ratio q (weekly off-exchange shares ÷ bar
    shares) steps at a split. → ({week: ratio}, cut): the clean steps at a usual split ratio, and `cut`, the first week
    after a step that is no split — one of 5× or more, or any step across `gap` weeks or more with no FINRA figure (the
    symbol then named another security in FINRA's files: everything before is left out; 0 when none). Read on the weeks
    with a figure: a step is the change of the median of log q between the `span` such weeks before and the `span` from
    it, placed by the two-week means, and it must stand out of those weeks' own swings (3 standard deviations)."""
    at = [i for i, x in enumerate(q) if x and x > 0]
    lq = [math.log(q[i]) for i in at]
    m = len(lq)
    med = lambda a: (sorted(a)[len(a) // 2] if len(a) % 2 else (sorted(a)[len(a) // 2 - 1] + sorted(a)[len(a) // 2]) / 2)
    d = [None] * m
    for w in range(need, m - need + 1):
        d[w] = med(lq[w:w + span]) - med(lq[max(0, w - span):w])

    def sharp(w):                                  # the step at w seen from two weeks on each side: where it is
        a, b = lq[max(0, w - 2):w], lq[w:w + 2]
        return abs(sum(b) / len(b) - sum(a) / len(a)) if a and b else 0.0
    found, w = [], 0
    while w < m:
        if d[w] is not None and abs(d[w]) > jump:
            run = [w]
            while run[-1] + 1 < m and d[run[-1] + 1] is not None and abs(d[run[-1] + 1]) > jump and (d[run[-1] + 1] > 0) == (d[w] > 0):
                run.append(run[-1] + 1)
            k = max(run, key=sharp)                    # the medians find the step, the two-week means place it
            found.append((k, max((d[i] for i in run), key=abs)))
            w = run[-1] + 1
        else:
            w += 1
    steps, cut = {}, 0
    for k, dk in reversed(found):                  # from the latest: a symbol change ends the history
        a, b = lq[max(0, k - span):k], lq[k:k + span]
        noise = max(_sigma(a), _sigma(b)) if len(a) >= 2 and len(b) >= 2 else 9.0
        ratio = snap(math.exp(dk))
        across = at[k] - at[k - 1] - 1 >= gap      # weeks with no FINRA figure between the two sides
        if ratio and abs(dk) >= 3 * noise and not across:
            steps[at[k]] = ratio
        elif abs(dk) > math.log(5) or across:
            cut = at[k]
            break
    return steps, cut


def ticker_flows(grid, fin, bars):
    """One ticker's weekly arrays on the grid (None where a week has no figure):
    dv, mf   dollar volume and Chaikin money flow (dollars, from the daily bars), ac the week's last adjusted close;
    ox       FINRA's off-exchange volume (shares as traded), r its short share, b the ticker's own short share — the
             average of the 52 weeks before (26 at least);
    dp       big-money net buying in dollars, 2 × (r − b) × the off-exchange dollars: FINRA's shares put in the bars'
             split-adjusted units (the splits found), left out where the two do not fit (an off-exchange share of the
             bars' volume under 1% or over 150%) and in a split's week and the one before."""
    n = len(grid)
    dv, mf, vol, ac = weekly_bars(bars, grid)
    sv, tv = fin if fin else ([None] * n, [None] * n)
    q = [tv[i] / vol[i] if tv[i] and vol[i] else None for i in range(n)]
    steps, cut = split_steps(q)
    ok = [i >= cut and sv[i] is not None and bool(tv[i]) for i in range(n)]
    r = [sv[i] / tv[i] if ok[i] else None for i in range(n)]
    ox = [tv[i] if ok[i] else None for i in range(n)]
    b = [None] * n
    tot, cnt = 0.0, 0
    for i in range(n):                              # a sliding window of the 52 weeks before
        if i - 1 >= 0 and r[i - 1] is not None:
            tot += r[i - 1]
            cnt += 1
        j = i - BASE_WEEKS - 1
        if j >= 0 and r[j] is not None:
            tot -= r[j]
            cnt -= 1
        if cnt >= BASE_MIN:
            b[i] = tot / cnt
    f, mult = [1.0] * n, 1.0                        # FINRA's shares into the bars' split-adjusted shares
    for i in range(n - 1, -1, -1):
        f[i] = mult
        if i in steps:
            mult *= steps[i]
    skip = set(steps) | {k - 1 for k in steps}
    dp = [None] * n
    for i in range(n):
        if b[i] is None or r[i] is None or not dv[i] or not vol[i] or i in skip:
            continue
        share = tv[i] * f[i] / vol[i]
        if 0.01 <= share <= 1.5:
            dp[i] = 2 * (r[i] - b[i]) * tv[i] * f[i] * dv[i] / vol[i]
    return {'dv': dv, 'mf': mf, 'ox': ox, 'r': r, 'b': b, 'dp': dp, 'ac': ac, 'splits': steps, 'cut': cut}


def window(F, i, L=WINDOW):
    """The reading at week i over the L weeks to it: x, big-money net buying as a share of the off-exchange volume
    (2 × the short share's excess over its own normal, weighted by each week's off-exchange shares); y, the money flow
    as a share of the dollar volume; the dollars of each (dp None when a week has none). None without every week."""
    if i - L + 1 < 0:
        return None
    sd = sm = sx = so = sp = 0.0
    dp_ok = True
    for j in range(i - L + 1, i + 1):
        if F['dv'][j] is None or F['mf'][j] is None or F['r'][j] is None or F['b'][j] is None or not F['ox'][j]:
            return None
        sd += F['dv'][j]
        sm += F['mf'][j]
        sx += 2 * (F['r'][j] - F['b'][j]) * F['ox'][j]
        so += F['ox'][j]
        if F['dp'][j] is None:
            dp_ok = False
        else:
            sp += F['dp'][j]
    if sd <= 0 or so <= 0:
        return None
    return {'x': 100 * sx / so, 'y': 100 * sm / sd, 'dp': sp if dp_ok else None, 'mf': sm, 'dv': sd}


def quad(x, y):
    """0 Accumulation (x ≥ 0, y ≥ 0), 1 Quiet buying (x ≥ 0, y < 0), 2 Outflow, 3 Distribution — the RRG's order."""
    return (0 if y >= 0 else 1) if x >= 0 else (2 if y < 0 else 3)


def _summary(vals):
    if not vals:
        return {'n': 0}
    s = sorted(vals)
    n = len(s)
    lo, hi = s[int(0.01 * (n - 1))], s[int(0.99 * (n - 1))]
    w = [min(hi, max(lo, v)) for v in s]
    return {'n': n, 'beat': round(sum(1 for v in s if v > 0) / n, 4), 'med': round(100 * s[n // 2], 2),
            'mean': round(100 * sum(w) / n, 2)}


def pooled_stats(flows, grid, bench_ac, etfs, L=WINDOW, horizons=HORIZONS):
    """What followed each quadrant: every (ticker, week) with a reading, h weeks on, its return against SPY's (adjusted
    closes), pooled — stocks and ETFs apart; the weeks overlap, so the counts are not independent tries. Also each
    week's top and bottom fifth by each measure (the reading ranked across tickers that week)."""
    pools = {'stocks': [], 'etfs': []}
    for t, F in flows.items():
        if t == BENCH:
            continue
        dvs = [v for v in F['dv'] if v]
        if not dvs or sum(dvs) / len(dvs) < MIN_DV:
            continue
        pools['etfs' if t in etfs else 'stocks'].append((t, F))
    out = {'L': L, 'h': list(horizons), 'from': None, 'to': None, 'pools': {}}
    first, last = None, None
    for name, items in pools.items():
        Q = {h: [[] for _ in range(4)] for h in horizons}
        ALL = {h: [] for h in horizons}
        by_week = {}
        for t, F in items:
            ac = F['ac']
            for i in range(len(grid)):
                R = window(F, i, L)
                if R is None or ac[i] is None or bench_ac[i] is None:
                    continue
                q = quad(R['x'], R['y'])
                for h in horizons:
                    j = i + h
                    if j >= len(grid) or ac[j] is None or bench_ac[j] is None or ac[i] <= 0 or bench_ac[i] <= 0:
                        continue
                    rel = (ac[j] / ac[i]) / (bench_ac[j] / bench_ac[i]) - 1
                    Q[h][q].append(rel)
                    ALL[h].append(rel)
                    by_week.setdefault((h, i), []).append((R['x'], R['y'], rel))
                    first = i if first is None else min(first, i)
                    last = i if last is None else max(last, i)
        ends = {}
        for h in horizons:
            tops = {'x': ([], []), 'y': ([], [])}
            for (hh, i), rows in by_week.items():
                if hh != h or len(rows) < 10:
                    continue
                for k, key in ((0, 'x'), (1, 'y')):
                    s = sorted(rows, key=lambda r: r[k])
                    m = max(1, len(s) // 5)
                    tops[key][0].extend(r[2] for r in s[-m:])
                    tops[key][1].extend(r[2] for r in s[:m])
            ends[str(h)] = {k: {'top': _summary(a), 'bottom': _summary(b)} for k, (a, b) in tops.items()}
        out['pools'][name] = {'tickers': len(items), 'all': {str(h): _summary(ALL[h]) for h in horizons},
                              'q': [{str(h): _summary(Q[h][q]) for h in horizons} for q in range(4)], 'fifths': ends}
    out['from'] = grid[first] if first is not None else None
    out['to'] = grid[last] if last is not None else None
    return out


def _k(v):
    """Dollars as whole thousands (None stays None)."""
    return None if v is None else int(round(v / 1000))


def _m(v):
    return None if v is None else int(round(v * 10000))


def etf_set():
    out = {BENCH}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import rotation_history as RH
        out |= {t for t, _, _ in RH.SECTOR_ETFS} | {t for t, _ in RH.STYLE_ETFS}
        import paths as P
        out |= set(P.ETFS) | {t for t, _, _ in P.MOVES_MORE_ETFS}
    except Exception:                                  # the stats only split ETFs from stocks
        pass
    return out


def build(root, bars, log=print):
    root, bars = Path(root), Path(bars)
    names = sorted({p.name[:-len('.json.gz')] for p in bars.glob('*.json.gz') if not p.name.endswith('.base.json.gz')})
    grid, fin = load_finra(root, {norm_symbol(t) for t in names if norm_symbol(t)})
    if not grid:
        log('no FINRA weeks on file yet')
        return None
    tickers = [t for t in names if norm_symbol(t) and not t.startswith('IDX-')]
    flows, splits = {}, {}
    for t in tickers:
        B = load_bars(bars, t)
        if not B:
            continue
        F = ticker_flows(grid, fin.get(norm_symbol(t)), B)
        if not any(v for v in F['dv']):
            continue
        flows[t] = F
        if F['splits'] or F['cut']:
            splits[t] = {**{grid[i]: round(r, 4) for i, r in F['splits'].items()}, **({'from': grid[F['cut']]} if F['cut'] else {})}
    pub = root / 'public'
    (pub / 't').mkdir(parents=True, exist_ok=True)
    written = 0
    for t, F in flows.items():
        i0 = next((i for i in range(len(grid)) if F['dv'][i] is not None), None)
        if i0 is None:
            continue
        doc = {'t': t, 'start': grid[i0], 'dv': [_k(v) for v in F['dv'][i0:]], 'mf': [_k(v) for v in F['mf'][i0:]],
               'ox': [_k(v) for v in F['ox'][i0:]], 'r': [_m(v) for v in F['r'][i0:]], 'b': [_m(v) for v in F['b'][i0:]],
               'dp': [_k(v) for v in F['dp'][i0:]]}
        (pub / 't' / f'{t}.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
        written += 1
    for old in (pub / 't').glob('*.json'):
        if old.stem not in flows:
            old.unlink()
    etfs = etf_set()
    bench = flows.get(BENCH)
    stats = pooled_stats(flows, grid, bench['ac'], etfs) if bench else None
    index = {'format': 1, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'start': grid[0],
             'weeks': grid[-1], 'tickers': sorted(flows), 'etfs': sorted(t for t in flows if t in etfs), 'quadrants': QUADS,
             'window': WINDOW, 'base_weeks': BASE_WEEKS, 'stats': stats, 'splits': splits,
             'units': {'dv': 'dollars, thousands', 'mf': 'dollars, thousands', 'dp': 'dollars, thousands',
                       'ox': 'off-exchange shares as traded, thousands',
                       'r': 'short share of off-exchange volume × 10,000', 'b': 'its average over the 52 weeks before × 10,000'},
             'source': "FINRA's daily short sale volume (consolidated NMS, off-exchange trades) and daily bars (Yahoo / Stooq)"}
    (pub / 'index.json').write_text(json.dumps(index, separators=(',', ':')), encoding='utf-8')
    (pub / 'status.json').write_text(json.dumps({'generated_at': index['generated_at'], 'weeks': grid[-1], 'tickers': written,
                                                 'first_week': grid[0], 'splits_found': len(splits)}, indent=1), encoding='utf-8')
    log(f'flows: {written} tickers, weeks {grid[0]} – {grid[-1]}, {len(splits)} with a split taken out')
    return index


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--minutes', type=float, default=20)
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--bars', required=True, help="research-paths' cache/ohlc/")
    a = ap.parse_args(argv)
    if a.cmd == 'collect':
        collect(a.root, a.minutes)
    else:
        build(a.root, a.bars)


if __name__ == '__main__':
    main()
