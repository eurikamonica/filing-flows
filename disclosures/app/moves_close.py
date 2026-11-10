"""Move odds at the close: every asset's latest close minutes after 4 pm New York, not the next morning.

The nightly run (.github/workflows/research-paths.yml: app/paths.py collect, then app/moves.py) rebuilds public/moves/
from every asset's daily bars; GitHub starts it hours late and the site publishes it after, so the hub used to show the
close before last until the small hours. This step (.github/workflows/moves-close.yml, started by the intraday relay when
the session ends, by its schedule as a fallback) takes the files the nightly run published as they are (index.json and
a/<KEY>.json of the branch research-paths) and adds the sessions since:

  closes       each asset's last month of daily bars from Yahoo's chart API, eight at a time; the days after the last
               one on file whose session has ended (a bar of a session still open is left out), each day's log return of
               the adjusted close (the ratio of two adjusted closes of one answer: a dividend or a split since changes
               nothing)
  industries   the composite's return from its members' new returns: the mean of their clipped simple returns
               (moves.composite), on a day with five members or more and at least 60% of those on file the day before
  VIX term     the VIX's close over the VIX3M's, against the day before's
  numbers      every asset that gained a day, worked out again (moves.summary, moves.level_summary: the nightly's
               arithmetic) into its index.json row, and the market's breadth; a/<KEY>.json with the new days and its
               last close (its highs, lows, ranges and ratios blocks as the nightly run left them)

Written to OUT, published as the branch moves-live (one commit, force-pushed); docs/moves.js and docs/moves-view.js read
it from raw.githubusercontent.com while its closes are newer than the site's copy, until the nightly run catches up.

    python app/moves_close.py --base BASE --out OUT [--workers 8] [--minutes 8]    BASE: research-paths' public/moves/
    python app/moves_close.py --due            exit 0 when a US session has closed that the published files lack (or
                                               the live files were made in the first minutes after it: once more, for
                                               the closing prints)
"""
import argparse
import datetime as dt
import json
import math
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, write_json             # noqa: E402
import moves as M                             # noqa: E402
import paths as P                             # noqa: E402

CHART = 'https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d&events=div%2Csplit'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
REPO = 'eurikamonica/filing-flows'
LIVE_STATUS = f'https://raw.githubusercontent.com/{REPO}/moves-live/status.json'
BASE_STATUS = f'https://raw.githubusercontent.com/{REPO}/research-paths/public/moves/status.json'
GRACE = 10 * 60               # a session's bar is final this long after its regular end (the closing prints)
REDO_AFTER = 45 * 60          # live files made within FIRST of the end are made again after this (the official closes)
FIRST = 25 * 60
MAX_R = 3.0                   # a day's log return beyond this (×20) is a bad print: the asset waits for the nightly run
MIN_SHARE = 0.8               # the close is published once this share of the companies on the last day on file have it


# ------------------------------------------------------------------ Yahoo's daily bars
def get_json(url, tries=3, timeout=25):
    err = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            err = f'HTTP {exc.code}'
            if exc.code == 404:
                break
            time.sleep(3 * 2 ** k if exc.code == 429 else 1 + k)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            err = str(exc)[:80]
            time.sleep(1 + k)
    raise RuntimeError(err or 'request failed')


def closed_bars(payload, now_ts=None):
    """Yahoo's daily chart → (bars as paths.parse_yahoo_daily, the regular session's end): the last bar left out while its
    session has not ended (GRACE after the end), so that a session still open never counts as a close."""
    bars = P.parse_yahoo_daily(payload)
    meta = (((payload.get('chart') or {}).get('result') or [{}])[0].get('meta')) or {}
    reg = (meta.get('currentTradingPeriod') or {}).get('regular') or {}
    start, end, off = reg.get('start'), reg.get('end'), meta.get('gmtoffset') or 0
    now_ts = time.time() if now_ts is None else now_ts
    if start and end and bars['t']:
        day = dt.datetime.fromtimestamp(start + off, dt.timezone.utc).date().isoformat()
        if bars['t'][-1] >= day and now_ts < end + GRACE:
            bars = {k: v[:-1] for k, v in bars.items()}
    return bars, end


def symbol_of(doc):
    """The Yahoo symbol of an asset on file, or None (a composite, a ratio)."""
    k = doc.get('key')
    if k in P.YAHOO_SYMBOL:
        return P.YAHOO_SYMBOL[k]
    if doc.get('kind') in ('industry',) or k == 'VIX-TERM' or not doc.get('ticker'):
        return None
    return k


def fetch_all(docs, workers=8, minutes=8.0, get=None, now_ts=None):
    """{key: bars} for every asset with a Yahoo symbol, within `minutes`; and the errors."""
    get = get or (lambda sym: get_json(CHART.format(sym=urllib.parse.quote(sym))))
    t0 = time.monotonic()
    todo = [(k, symbol_of(d)) for k, d in docs.items()]
    todo = [(k, s) for k, s in todo if s]

    def one(item):
        k, s = item
        if time.monotonic() - t0 > minutes * 60:
            return k, None, 'time'
        try:
            return k, closed_bars(get(s), now_ts)[0], None
        except Exception as exc:                                       # noqa: BLE001
            return k, None, str(exc)[:80]
    got, errors = {}, []
    with ThreadPoolExecutor(max(1, workers)) as pool:
        for k, b, err in pool.map(one, todo):
            if b:
                got[k] = b
            elif err:
                errors.append(f'{k}: {err}')
    return got, errors


# ------------------------------------------------------------------ the days since
def new_returns(days, bars):
    """[(day, log return)] of the bars' days after the last one on file, from the bars' own adjusted closes; [] when
    the bars do not reach back to that day (a longer gap waits for the nightly run) or a return is a bad print."""
    if not days or not bars or not bars.get('t'):
        return []
    last = days[-1]
    try:
        i = bars['t'].index(last)
    except ValueError:
        return []
    out = []
    for j in range(i + 1, len(bars['t'])):
        a0, a1 = bars['ac'][j - 1], bars['ac'][j]
        if not (a0 and a1 and a0 > 0 and a1 > 0):
            return []
        r = math.log(a1 / a0)
        if abs(r) > MAX_R:
            return []
        out.append((bars['t'][j], r))
    return out


def composite_returns(doc, members, added):
    """An industry composite's new days: each day's mean clipped simple return of the members with a return that day,
    when five or more of them have one and at least 60% of the members on file the composite's last day."""
    last = doc.get('as_of')
    on_file = [m for m in members if last in m['days_set']]
    by_day = {}
    for m in members:
        for d, r in added.get(m['key'], []):
            if d > last:
                s = by_day.setdefault(d, [0.0, 0])
                s[0] += float(np.clip(math.expm1(r), *M.CLIP))
                s[1] += 1
    out = []
    for d in sorted(by_day):
        tot, n = by_day[d]
        if n < max(M.MIN_MEMBERS, 0.6 * len(on_file)):
            break                                      # a day for which only a few members' bars are in: not yet
        out.append((d, math.log1p(tot / n)))
    return out


def term_returns(doc, vix, vix3m):
    """The VIX term structure's new days: log changes of VIX ÷ VIX3M (raw closes), and the last ratio."""
    if not vix or not vix3m:
        return [], None
    a = dict(zip(vix['t'], vix['c']))
    b = dict(zip(vix3m['t'], vix3m['c']))
    common = sorted(d for d in set(a) & set(b) if a[d] and b[d])
    last = doc.get('as_of')
    if last not in common:
        return [], None
    i = common.index(last)
    out, ratio = [], None
    for d0, d1 in zip(common[i:], common[i + 1:]):
        r0, r1 = a[d0] / b[d0], a[d1] / b[d1]
        out.append((d1, math.log(r1 / r0)))
        ratio = r1
    return out, (round(ratio, 4) if ratio else None)


def extended(doc, add):
    """The asset's file with the new days: its returns encoded again (whole basis points, as moves.py writes them)."""
    days, r = P.decode_returns(doc)
    bp = np.rint(np.asarray(r) * 1e4).astype(int).tolist() + [int(round(x * 1e4)) for _, x in add]
    all_days = list(days) + [d for d, _ in add]
    closes = np.exp(np.concatenate([[0.0], np.cumsum(np.asarray(bp, float) / 1e4)]))
    enc = P.encode_returns(all_days, closes)
    out = {k: v for k, v in doc.items() if k not in ('d0', 'gaps', 'dates', 'r')}
    out.update(enc)
    out['as_of'] = all_days[-1]
    return out


# ------------------------------------------------------------------ the whole step
def run(base, out, workers=8, minutes=8.0, get=None, now_ts=None, log=print):
    """Read BASE (research-paths' public/moves/), write OUT (index.json, a/, status.json); returns the status."""
    t0 = time.monotonic()
    base, out = Path(base), Path(out)
    ix = json.loads((base / 'index.json').read_text())
    fields = ix['fields']
    if fields != M.FIELDS:
        raise RuntimeError('index.json fields differ from moves.FIELDS: the nightly format changed')
    rows = {r[0]: dict(zip(fields, r)) for r in ix['rows']}
    docs = {}
    for k in rows:
        p = base / 'a' / f'{k}.json'
        if p.exists():
            docs[k] = json.loads(p.read_text())
    bars, errors = fetch_all(docs, workers, minutes, get, now_ts)
    log(f'bars: {len(bars)} of {sum(1 for d in docs.values() if symbol_of(d))} assets with a symbol; {len(errors)} errors')
    added, lasts = {}, {}
    for k, b in bars.items():
        days, _ = P.decode_returns(docs[k])
        add = new_returns(days, b)
        if add:
            added[k] = add
            i = b['t'].index(add[-1][0])
            lasts[k] = b['c'][i]
    # industries: from their members' new returns (members as moves.build groups them: the SIC code, and its first two digits)
    stocks = [{'key': k, 'sic': d.get('sic'), 'days_set': None} for k, d in docs.items() if d.get('kind') == 'stock' and d.get('sic')]
    for s in stocks:
        s['days_set'] = set(P.decode_returns(docs[s['key']])[0][-5:])
    for k, d in docs.items():
        if d.get('kind') != 'industry' or not k.startswith('SIC-'):
            continue
        code = k[4:]
        mem = [s for s in stocks if (s['sic'] == code if len(code) == 4 else str(s['sic'])[:2] == code)]
        add = composite_returns(d, mem, added)
        if add:
            added[k] = add
    if 'VIX-TERM' in docs:
        add, ratio = term_returns(docs['VIX-TERM'], bars.get('IDX-VIX'), bars.get('IDX-VIX3M'))
        if add:
            added['VIX-TERM'], lasts['VIX-TERM'] = add, ratio
    # every asset with new days: its file and its numbers again
    newdocs = {k: extended(docs[k], add) for k, add in added.items()}
    for k, v in lasts.items():
        if k in newdocs:
            newdocs[k]['last'] = v
    decoded = {}

    def series(k):
        if k not in decoded:
            decoded[k] = P.decode_returns(newdocs.get(k) or docs[k])
        return decoded[k]
    redone = 0
    for k in added:
        d = newdocs[k]
        days, r = series(k)
        try:
            if d.get('kind') == 'volatility':
                o = (d.get('links') or {}).get('outcome')
                outcome = None
                if o and (o in newdocs or o in docs):
                    od, orr = series(o)
                    outcome = (od, M.cum(orr))
                last = d.get('last') if d.get('last') else float(np.exp(M.cum(r)[-1]))
                s = M.level_summary(days, r, last, outcome)
            else:
                s = M.summary(days, r)
        except Exception as exc:                                       # noqa: BLE001
            errors.append(f'{k}: {str(exc)[:120]}')
            newdocs.pop(k, None)
            continue
        old = rows[k]
        s.update({f: old.get(f) for f in ('key', 'ticker', 'name', 'kind', 'sector', 'industry', 'cik', 'members', 'group')})
        s['last'] = d.get('last')
        rows[k] = {f: s.get(f) for f in fields}
        redone += 1
    out_rows = [[[M._r(x) for x in v] if isinstance(v, list) else M._r(v) for v in (r.get(f) for f in fields)] for r in rows.values()]
    ki, ai, pi = fields.index('kind'), fields.index('as_of'), fields.index('pct')
    st = [r for r in out_rows if r[ki] == 'stock']
    as_of = max((r[ai] for r in st), default=ix.get('as_of'))
    today = [r for r in st if r[ai] == as_of and r[pi] is not None]
    before = sum(1 for r in ix['rows'] if r[ki] == 'stock' and r[ai] == ix.get('as_of'))
    if as_of != ix.get('as_of') and len(today) < MIN_SHARE * before:
        raise RuntimeError(f'only {len(today)} of {before} companies have the close of {as_of} (Yahoo answered {len(bars)}): '
                           'not published, the next run tries again')
    breadth = {'stocks': len(today), 'down5': sum(1 for r in today if r[pi] <= 5) / len(today) if today else None,
               'up5': sum(1 for r in today if r[pi] >= 95) / len(today) if today else None}
    if out.exists():
        shutil.rmtree(out)
    (out / 'a').mkdir(parents=True)
    for k, d in docs.items():
        if k in newdocs:
            M._dump(out / 'a' / f'{k}.json', newdocs[k])
        else:
            shutil.copyfile(base / 'a' / f'{k}.json', out / 'a' / f'{k}.json')
    M._dump(out / 'index.json', {'format': ix.get('format', M.FORMAT), 'generated_at': now(), 'as_of': as_of, 'band': ix.get('band', M.BAND),
                                 'horizons': ix.get('horizons', list(M.HORIZONS)), 'breadth': {k: M._r(v) for k, v in breadth.items()},
                                 'fields': fields, 'rows': out_rows,
                                 'close': {'base_as_of': ix.get('as_of'), 'base_generated_at': ix.get('generated_at'), 'assets': redone}})
    status = {'built_at': now(), 'as_of': as_of, 'base_as_of': ix.get('as_of'), 'assets': len(out_rows), 'updated': redone,
              'fetched': len(bars), 'stocks_on_day': len(today), 'seconds': round(time.monotonic() - t0, 1), 'errors': errors[:40]}
    write_json(out / 'status.json', status)
    return status


# ------------------------------------------------------------------ is a close due?
def last_closed_session(get=None, now_ts=None):
    """(the last US session whose bar is final, its regular end): SPY's daily chart."""
    get = get or (lambda sym: get_json(CHART.format(sym=urllib.parse.quote(sym))))
    payload = get('SPY')
    bars, end = closed_bars(payload, now_ts)
    return (bars['t'][-1] if bars['t'] else None), end


def due(live=None, base=None, session=None, now_ts=None):
    """(due?, why): a session has closed that neither the live files nor the nightly's have, or the live files were made
    in the first minutes after this session's end and it is time for the official closes."""
    now_ts = time.time() if now_ts is None else now_ts
    day, end = session
    if not day:
        return False, 'no session found'
    have = max((x.get('as_of') or '' for x in (live, base) if x), default='')
    if day > have:
        return True, f'the session of {day} is not on file (published to {have or "nothing"})'
    if live and live.get('as_of') == day and end:
        from zoneinfo import ZoneInfo
        built = dt.datetime.fromisoformat(live['built_at']).timestamp() if live.get('built_at') else 0
        ends_that_day = dt.datetime.fromtimestamp(end, ZoneInfo('America/New_York')).date().isoformat() == day
        if ends_that_day and built < end + FIRST and now_ts > end + REDO_AFTER and not (base and base.get('as_of') == day):
            return True, f'the live files of {day} were made in the first minutes after the close: once more, with the closing prints'
    return False, f'up to date ({have})'


def _status(url):
    try:
        return get_json(url, tries=2, timeout=15)
    except Exception:                                                  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--base', help="research-paths' public/moves/ (index.json, a/)")
    ap.add_argument('--out', help='the folder published as the branch moves-live')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--minutes', type=float, default=8.0)
    ap.add_argument('--due', action='store_true', help='exit 0 when a close is due')
    a = ap.parse_args()
    if a.due:
        ok, why = due(_status(LIVE_STATUS), _status(BASE_STATUS), last_closed_session())
        print(why)
        sys.exit(0 if ok else 1)
    print(json.dumps(run(a.base, a.out, a.workers, a.minutes)))


if __name__ == '__main__':
    main()
