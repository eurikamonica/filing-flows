"""The video studio's leaderboards (web/studio.js, kind "rank"): one cross-section of every company of the site per
month and per quarter, so the browser can rank any of them by any measure, within a sector or a market-value range,
without loading thousands of files. Built by rotation_history.build into public/rank/ (the hub serves it at
disclosures/data/market/history/rank/).

  meta.json   companies [ticker, name, sector], the month grid (from 1990-01), the quarters (from 2009Q1), sector
              names, each company's latest market value (cap_now, $M) and what each file holds
  m-px.json   month-end close, adjusted for splits and dividends (total return)                 from the weekly closes
  m-dv.json   dollar volume traded in the month, $M (weekly volume × the week's close as traded)
  m-cap.json  month-end market value, $M: the close as traded × shares outstanding as of then
  q-rev.json, q-gp.json, q-oi.json, q-ni.json   the calendar quarter's revenue, gross profit, operating income and
              net income, $M (SEC XBRL frames; fourth quarters from the year less the three quarters before it)
  q-eq.json   stockholders' equity at the quarter's end, $M

Each file: {"rows": [[i0, v, v, …] | [] per company, in meta's order]} — i0 is the index of the first value on the
grid, null marks a gap.

Market value. Shares outstanding come from the cover page of each 10-Q / 10-K (dei:EntityCommonStockSharesOutstanding,
counted a few weeks after the quarter and never restated). A company with several share classes reports no single
cover figure (or one class only), so where the cover figure is missing or more than 25% below the diluted
weighted-average shares of the quarter, the weighted average is used (net income ÷ diluted EPS where neither is tagged;
a figure tagged in thousands is caught against its neighbours). Shares are put on today's basis with Yahoo's
split history (a share counted before a 2-for-1 split is two of today's), and multiplied by the month-end close as
traded (split-adjusted), so market value = the price then × the shares then. A share count is used for at most 400
days. Before the company's first XBRL filing (2009–2011), the counts come from the cover pages of its earlier 10-Ks and
10-Qs, read from EDGAR's text (cover_shares.py, from 1993; companies are read a batch at a time, largest first). Companies whose split history is not on file
yet (fetched before dividends and splits were kept) get no market value until their next full fetch.

Today's market value from Nasdaq's screener checks every company: where the latest share count differs by more than
0.55–1.8× (an ADR worth several shares, one class of several) the whole history is rescaled to it; by more than 10%
(shares issued or bought back since the last filing) today's count is added as the latest; a company without an SEC
share count in the last 400 days gets today's count held back at most five years (approx_cap in meta.json, flagged in
the studio). stats.check in meta.json reports how many agreed within 10% before these corrections.

A month's value is left out when it cannot be right (see plausible: a missing reverse split blows a micro cap up to
hundreds of billions, but not its trading); stats.implausible counts them.

Survivorship: today's companies only — names that were delisted, merged or went bankrupt are missing from earlier
leaderboards; the studio says so on the video.
"""
import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

NASDAQ = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
APPROX_YEARS = 5                                  # today's share count held back at most this long (no SEC count)


def sig(x, n=4):
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    v = float(f'{x:.{n}g}')
    return int(v) if v == int(v) and abs(v) < 1e15 else v


def months(start='2000-01', today=None):
    today = today or dt.date.today()
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while (y, m) <= (today.year, today.month):
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_end(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return (dt.date(y + (m == 12), 1 if m == 12 else m + 1, 1) - dt.timedelta(days=1)).isoformat()


def split_factor(splits, day):
    """Today's shares per share counted on `day`: the product of every split after it."""
    f = 1.0
    for d, r in splits or []:
        if d > day and r and r > 0:
            f *= r
    return f


def restated_bases(splits, end, within=900):
    """[1, r1, r1·r2, …]: the bases a figure for a period ending `end` can be on — later filings restate earlier periods
    for every split up to the day they are filed (up to about two and a half years later for a ten-year table)."""
    out, f = [1.0], 1.0
    lim = (dt.date.fromisoformat(end) + dt.timedelta(days=within)).isoformat()
    for d, r in sorted(splits or []):
        if end < d <= lim and r and r > 0:
            f *= r
            out.append(f)
    return out


def _near(points, day, before=120, after=120):
    best = None
    for d, v in points:
        gap = (dt.date.fromisoformat(d) - dt.date.fromisoformat(day)).days
        if -before <= gap <= after and (best is None or abs(gap) < best[0]):
            best = (abs(gap), v)
    return best[1] if best else None


def _num(x):
    try:
        v = float(str(x).replace('$', '').replace(',', '').strip())
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def nasdaq_caps(cache=None, fetch=True):
    """{ticker: [market value $, last price $]} from Nasdaq's stock screener (one request for every listed company); the
    last answer is kept in `cache` for a run where the request fails."""
    rows = None
    if fetch:
        try:
            req = urllib.request.Request(NASDAQ, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
                                                          'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'})
            with urllib.request.urlopen(req, timeout=40) as r:
                body = json.loads(r.read().decode('utf-8'))
            rows = {}
            for x in (((body or {}).get('data') or {}).get('rows')) or []:
                t = str(x.get('symbol') or '').strip().upper().replace('/', '-').replace('.', '-')
                m, p = _num(x.get('marketCap')), _num(x.get('lastsale'))
                if t and m and m > 0 and p and p > 0:
                    rows[t] = [m, p]
            if cache and rows:
                Path(cache).parent.mkdir(parents=True, exist_ok=True)
                Path(cache).write_text(json.dumps({'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'rows': rows},
                                                  separators=(',', ':')), encoding='utf-8')
        except Exception as exc:                    # noqa: BLE001 — the file on hand, or none
            print('rank panel: Nasdaq screener', str(exc)[:160])
            rows = None
    if rows is None and cache:
        try:
            rows = json.loads(Path(cache).read_text(encoding='utf-8')).get('rows')
        except (OSError, ValueError):
            rows = None
    return rows or {}


def share_history(dei, wavg, splits, eps_sh=None, now=None):
    """[(date, shares on today's basis)] from the cover-page counts, the quarterly diluted weighted averages (net income
    ÷ diluted EPS where none is tagged) and, to anchor the latest, today's count (Nasdaq's market value ÷ price).

    Cover counts are never restated: today's basis = the count × every split after its date. A weighted average is the
    last figure filed for that quarter, which a later filing may have restated for a split made after the quarter — and
    a few filers tag shares in thousands. Of the bases a figure can be on (each later split, × or ÷ 1,000), the one
    nearest the cover count of about the same time is taken when they agree within 25% (one class of several does
    not), else the one nearest the next quarter's figure (the latest: nearest today's count)."""
    def nearest(cands, target):
        return min(cands, key=lambda c: abs(math.log(c / target)))

    def scaled(cands, target):
        """Prefer the figure as filed (× bases); × or ÷ 1,000 only when that is what brings it within 3× of the target."""
        best = nearest(cands, target)
        if abs(math.log(best / target)) <= math.log(3):
            return best
        alt = nearest([c * k for c in cands for k in (1e-6, 1e-3, 1e3, 1e6)], target)
        return alt if abs(math.log(alt / target)) < math.log(1.5) else best

    # cover counts on today's basis, newest first: one tagged in thousands set right against the one after it (the
    # newest against today's count)
    dei_raw = [(d, v * split_factor(splits, d)) for d, v in dei or [] if v and v > 0]
    fixed = []
    for i in range(len(dei_raw) - 1, -1, -1):
        d, adj = dei_raw[i]
        ref = now if i == len(dei_raw) - 1 else (fixed[-1][1] if fixed else None)
        fixed.append((d, scaled([adj], ref) if ref else adj))
    fixed.reverse()
    raw = sorted((e, v) for e, v in wavg or [] if v and v > 0)
    ends = [e for e, _ in raw]                       # net income ÷ diluted EPS where no weighted average is tagged
    raw = sorted(raw + [(e, v) for e, v in eps_sh or [] if v and v > 0
                        and not any(abs((dt.date.fromisoformat(e) - dt.date.fromisoformat(x)).days) <= 20 for x in ends)])
    wa = [None] * len(raw)
    for j in range(len(raw) - 1, -1, -1):
        e, v = raw[j]
        cands = [v / b * split_factor(splits, e) for b in restated_bases(splits, e)]
        ref = _near(fixed, e, before=30, after=150)
        if ref and abs(math.log(scaled(cands, ref) / ref)) < math.log(1.25):
            wa[j] = (e, scaled(cands, ref))              # the basis (and scale) that matches the cleaned cover count
            continue
        target = wa[j + 1][1] if j + 1 < len(raw) else now
        wa[j] = (e, scaled(cands, target) if target else cands[0])
    out = []
    for d, adj in fixed:
        w = _near(wa, d, before=150, after=30)
        if w and 0.02 * w < adj < 0.75 * w:          # one share class of several: the weighted average covers all
            adj = w
        out.append((d, adj))
    have = [d for d, _ in out]
    for e, w in wa:                                  # quarters without a cover figure (several classes, none tagged)
        if not any(abs((dt.date.fromisoformat(e) - dt.date.fromisoformat(d)).days) <= 100 for d in have):
            out.append((e, w))
    out.sort()
    # a lone figure far from both neighbours (which agree with each other) is a slip, not a change in the share count
    keep = []
    for i, (d, v) in enumerate(out):
        if 0 < i < len(out) - 1:
            a, c = out[i - 1][1], out[i + 1][1]
            if 1 / 1.5 < a / c < 1.5 and min(abs(math.log(v / a)), abs(math.log(v / c))) > math.log(4):
                continue
        keep.append((d, v))
    return keep


def with_cover(dei, root, cik):
    """The XBRL cover counts, preceded by the counts read from the cover pages of the 10-Ks and 10-Qs filed before them
    (cover_shares.py, cache/cover/<CIK>.json: 1993 to the first XBRL filing)."""
    dei = list(dei or [])
    if not root or not cik:
        return dei
    try:
        import cover_shares
        old = cover_shares.points(root, cik)
    except Exception:
        return dei
    if not old:
        return dei
    first = min((d for d, _ in dei), default='9999')
    cut = (dt.date.fromisoformat(first) - dt.timedelta(days=30)).isoformat() if first != '9999' else '9999'
    return sorted([(d, v) for d, v in old if d < cut] + dei)


def asof(points, day, stale=400):
    """The last (date, value) on or before `day` — None when older than `stale` days."""
    best = None
    for d, v in points:
        if d <= day:
            best = (d, v)
        else:
            break
    if best and (dt.date.fromisoformat(day) - dt.date.fromisoformat(best[0])).days <= stale:
        return best[1]
    return None


def unit_slips(vals):
    """A quarter tagged at another scale (813.8 for $813.8 million) dropped: one at most a thousandth, or a thousand
    times, the typical size of its neighbours (two on each side)."""
    out = list(vals)
    for i, v in enumerate(vals):
        if v is None or v == 0:
            continue
        near = sorted(abs(x) for x in vals[max(0, i - 2):i] + vals[i + 1:i + 3] if x)
        if len(near) >= 2:
            mid = near[len(near) // 2]
            if abs(v) < 1e-3 * mid or abs(v) > 1e3 * mid:
                out[i] = None
    return out


def plausible(c, dv, shares, n_last):
    """A backstop for a reverse split missing from the history (the share count then × a price on today's basis): no
    value near $15 trillion, none worth 10,000 months of its trading, a count at most twenty times today's (buybacks never
    shrink one that far) — and a company worth $20 billion or more trades at least 0.1% of itself in a month (the
    thinnest real ones, ADRs of a foreign company, trade several times that; a reverse-split micro cap blown up to
    hundreds of billions trades a hundredth of it)."""
    if c > 15e12 or (dv and c > 1e4 * dv) or (n_last and shares > 20 * n_last):
        return False
    return c < 20e9 or bool(dv and c <= 1e3 * dv)


def trim(vals):
    """[v, v, …] on the grid → [i0, v, …] without the leading and trailing gaps, or []."""
    idx = [i for i, v in enumerate(vals) if v is not None]
    if not idx:
        return []
    return [idx[0]] + vals[idx[0]:idx[-1] + 1]


def monthly(rows, grid):
    """Weekly rows [[friday, adjusted close, volume, close as traded?]] → (month-end adjusted close, month-end close as
    traded, dollar volume in the month) on the month grid. The month-end close is the last week ending in the month
    (none when the month has no week on file)."""
    ends = [month_end(m) for m in grid]
    px, pt, dv = [None] * len(grid), [None] * len(grid), [None] * len(grid)
    j = 0
    for i, e in enumerate(ends):
        start = ends[i - 1] if i else (dt.date.fromisoformat(e).replace(day=1) - dt.timedelta(days=1)).isoformat()
        tot, n = 0.0, 0
        while j < len(rows) and rows[j][0] <= e:
            r = rows[j]
            if r[0] > start:
                p = r[3] if len(r) > 3 and r[3] else r[1]
                if r[2] and p:
                    tot += r[2] * p
                    n += 1
                px[i] = r[1]
                pt[i] = r[3] if len(r) > 3 and r[3] else None
            j += 1
        dv[i] = tot if n else None
    return px, pt, dv


def build(out_dir, companies, docs, frames_root=None, today=None, names=None, nasdaq=True):
    """companies: [{t, n, s, cik}] (the site's, largest first); docs: {ticker: cache doc {'rows', 'ev'?}}; nasdaq: fetch
    today's market values (the fallback for companies without an SEC share count, and the check of the others)."""
    import frames as FR
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today()
    grid = months('1990-01', today)
    nq = (today.year - 2009) * 4 + (today.month - 1) // 3
    periods = FR.calendar_quarters(max(1, nq), today) if frames_root else []
    figs, dei, wavg, eq, eps_sh = {}, {}, {}, {}, {}
    caps = nasdaq_caps(Path(frames_root) / 'cache' / 'nasdaq-caps.json', fetch=nasdaq) if frames_root else {}
    if frames_root:
        try:
            figs = FR.figures(frames_root, periods)
        except Exception as exc:                    # no frames on file: the price measures only
            print('rank panel: no frames', exc)
        dei = FR.points(frames_root, 'EntityCommonStockSharesOutstanding', periods, instant=True)
        wavg = FR.points(frames_root, 'WeightedAverageNumberOfDilutedSharesOutstanding', periods, instant=False)
        for p in periods:                           # shares = net income ÷ diluted EPS (|EPS| ≥ 2¢, same sign)
            for cik, row in FR.load(frames_root, 'EarningsPerShareDiluted', p).items():
                ni = ((figs.get(cik) or {}).get(p) or {}).get('ni')
                if isinstance(row, list) and row[0] and abs(row[0]) >= 0.02 and ni and ni / row[0] > 0 and row[1]:
                    eps_sh.setdefault(cik, []).append((row[1], ni / row[0]))
        for p in periods:                           # equity at each quarter's end; including minority interests where
            a = FR.load(frames_root, 'StockholdersEquity', p + 'I')           # the parent's alone is not tagged
            b = FR.load(frames_root, 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest', p + 'I')
            eq[p] = {k: v[0] for k, v in {**b, **a}.items() if isinstance(v, list) and v and v[0] is not None}
    cos, files = [], {k: [] for k in ('px', 'dv', 'cap', 'rev', 'gp', 'oi', 'ni', 'eq')}
    cap_now, seen = [], set()
    qlabels = [p[2:6] + p[6:] for p in periods]                # 'CY2019Q1' → '2019Q1'
    stats = {'companies': 0, 'with_cap': 0, 'with_fund': 0, 'splits_unknown': 0, 'approx_cap': [], 'check': {'n': 0, 'within_10pct': 0, 'off': []}}
    for c in companies:
        t = c['t']
        doc = docs.get(t)
        if not doc or t in seen or not doc.get('rows'):
            continue
        seen.add(t)
        rows = doc['rows']
        px, pt, dv = monthly(rows, grid)
        if sum(1 for v in px if v is not None) < 2:
            continue
        cik = str(c.get('cik') or '')
        cos.append([t, c.get('n') or t, c.get('s') or 'other'])
        files['px'].append(trim([sig(v, 4) for v in px]))
        files['dv'].append(trim([sig(v / 1e6, 3) if v else None for v in dv]))
        cap = [None] * len(grid)
        ev = doc.get('ev')
        n_now = caps[t][0] / caps[t][1] if t in caps else None
        sh = share_history(with_cover(dei.get(cik), frames_root, cik), wavg.get(cik), (ev or {}).get('split'), eps_sh.get(cik), now=n_now) if cik else []
        if ev is None:
            stats['splits_unknown'] += 1
        else:
            last_p = next((v for v in reversed(pt) if v), None)
            if (not sh or sh[-1][0] < (today - dt.timedelta(days=400)).isoformat()) and n_now and last_p:
                # no SEC share count of late: today's (Nasdaq's market value ÷ its price), held back APPROX_YEARS at most
                sh = [((today - dt.timedelta(days=d)).isoformat(), n_now) for d in range(int(365.25 * APPROX_YEARS), -1, -90)]
                stats['approx_cap'].append(t)
            elif sh and n_now and last_p:
                # against today's market value (Nasdaq): the share count of the latest month as Nasdaq has it
                r = asof(sh, today.isoformat()) / n_now
                stats['check']['n'] += 1
                stats['check']['within_10pct'] += abs(r - 1) <= 0.10
                if abs(math.log(r)) > math.log(1.25):
                    stats['check']['off'].append([t, round(r, 2)])
                if not 0.55 <= r <= 1.8:            # a basis, not a change: an ADR (several shares each), one class
                    sh = [(d, v / r) for d, v in sh]
                    stats['check'].setdefault('rescaled', []).append([t, round(r, 2)])
                elif abs(r - 1) > 0.10:              # shares issued or bought back since the last filing
                    sh = sh + [(today.isoformat(), n_now)]
            n_last = sh[-1][1] if sh else None
            for i, m in enumerate(grid):
                if pt[i] is None:
                    continue
                v = asof(sh, month_end(m))
                if v:
                    c = pt[i] * v
                    if not plausible(c, dv[i], v, n_last):
                        stats['implausible'] = stats.get('implausible', 0) + 1
                        continue
                    cap[i] = sig(c / 1e6, 4)
        files['cap'].append(trim(cap))
        cap_now.append(next((v for v in reversed(cap[-2:]) if v is not None), None))
        stats['with_cap'] += any(v is not None for v in cap)
        per = figs.get(cik) or {}
        for k in ('rev', 'gp', 'oi', 'ni'):
            files[k].append(trim(unit_slips([sig((per.get(p) or {}).get(k) / 1e6, 4) if (per.get(p) or {}).get(k) is not None else None for p in periods])))
        files['eq'].append(trim(unit_slips([sig(eq[p][cik] / 1e6, 4) if cik in eq.get(p, {}) else None for p in periods])))
        stats['with_fund'] += bool(per)
        stats['companies'] += 1
    meta = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'months': {'start': grid[0], 'n': len(grid)},
            'quarters': qlabels, 'sectors': names or {}, 'fields': ['ticker', 'name', 'sector'], 'cos': cos, 'cap_now': cap_now,
            'approx_cap': stats['approx_cap'],
            'files': {'m-px': 'month-end close, adjusted for splits and dividends', 'm-dv': 'dollar volume in the month, $M',
                      'm-cap': 'month-end market value, $M', 'q-rev': 'revenue in the calendar quarter, $M', 'q-gp': 'gross profit, $M',
                      'q-oi': 'operating income, $M', 'q-ni': 'net income, $M', 'q-eq': "stockholders' equity at the quarter's end, $M"},
            'stats': stats,
            'note': ("Today's companies on the site only (survivorship: names delisted, merged or bankrupt are missing). Weekly closes "
                     'from Yahoo Finance; figures from SEC XBRL frames (calendar quarters, 2009 on); market value = the month-end close '
                     "as traded × the latest cover-page shares outstanding (diluted weighted average where a company has several "
                     "share classes), put on today's basis with the split history.")}
    stats['check']['off'] = sorted(stats['check']['off'], key=lambda x: -abs(math.log(max(x[1], 1e-9))))[:40]
    stats['check']['rescaled'] = stats['check'].get('rescaled', [])[:60]
    (out_dir / 'meta.json').write_text(json.dumps(meta, separators=(',', ':')), encoding='utf-8')
    for k, rows in files.items():
        name = ('m-' if k in ('px', 'dv', 'cap') else 'q-') + k
        (out_dir / f'{name}.json').write_text(json.dumps({'rows': rows}, separators=(',', ':')), encoding='utf-8')
    return stats
