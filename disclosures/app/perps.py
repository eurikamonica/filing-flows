"""An experiment beside the RRG's money flow (app/flows.py): crypto exchanges' perpetual futures on US stocks and ETFs.
OKX and Bitget publish, day by day, how much of each contract traded on the buy side of the taker (a buyer lifting the
offer) and on the sell side — the "active buy / active sell" split Chinese stock apps compute from tick data for their
money-flow figures. Here it is the flow of the exchanges' own traders (offshore, leveraged, around the clock), a small
fraction of the stock's own turnover, not the stock market's: an experiment, shown apart from the two measures.

  collect  OKX: every stock perpetual (instCategory 3) whose ticker has daily bars on the site, its daily taker sell and
           buy volume in dollars (rubik/stat/taker-volume-contract, unit 2: about the last 100 days); Bitget: every RWA
           perpetual likewise (taker-buy-sell, the last 30 days, in shares, × the day's average price from its daily
           candle). Days run from 16:00 UTC (midnight in Hong Kong), as the exchanges count them. Kept, merged, in
           cache/perps/<venue>.json: {ticker: {day: [buy, sell]}} — the history grows a run at a time.
  weekly   On the flows' Friday grid: a day counts in the week of its start (11:00 or 12:00 in New York); a weekend day
           in the week after. → {ticker: (buy[], sell[])} in dollars.
  stats    What the experiment shows so far, ticker-weeks pooled (each with $5M or more of perpetuals traded): the rank
           correlation of the week's net taker buying (% of the contracts' turnover) with the stock's return against
           SPY that week, its money flow and big-money buying that week, the next week's return against SPY, and the
           next week's net taker buying.

    python app/perps.py collect --root F
"""
import argparse
import datetime as dt
import json
import math
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UA = 'FilingFlows/1.0 (+https://filing-flows.com)'   # a plain reader: no contact address is sent
OKX = 'https://www.okx.com/api/v5'
BITGET = 'https://api.bitget.com/api/v2/mix'
ALIAS = {'BRKB': 'BRK-B', 'BRKA': 'BRK-A', 'BFB': 'BF-B'}   # the exchanges' names for class shares
MIN_WEEK = 5e6                     # the stats: a ticker-week with at least $5M of perpetuals traded


def http_json(url, timeout=30, tries=4):
    for k in range(tries):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'}), timeout=timeout) as r:
                return json.load(r)
        except HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 + 4 * k)
                continue
            return None
        except (URLError, TimeoutError, OSError, ValueError):
            time.sleep(2 + 4 * k)
    return None


def ticker_of(base):
    b = (base or '').upper()
    return ALIAS.get(b, b)


def okx_collect(tickers, get=http_json, pause=0.45, log=print):
    """{ticker: {day: [buy, sell]}} in dollars for OKX's stock perpetuals whose ticker is asked for."""
    inst = (get(f'{OKX}/public/instruments?instType=SWAP') or {}).get('data') or []
    out = {}
    for i in inst:
        if str(i.get('instCategory')) != '3' or i.get('settleCcy') != 'USDT':
            continue
        t = ticker_of(i['instId'].split('-')[0])
        if t not in tickers:
            continue
        r = (get(f"{OKX}/rubik/stat/taker-volume-contract?instId={i['instId']}&period=1D&limit=100&unit=2") or {}).get('data') or []
        time.sleep(pause)
        days = {}
        for ts, sell, buy in (row[:3] for row in r if len(row) >= 3):
            s, b = float(sell or 0), float(buy or 0)
            if s or b:
                days[day_of(ts)] = [b, s]
        if days:
            out.setdefault(t, {}).update(days)
    log(f'OKX: {len(out)} stock perpetuals read')
    return out


def bitget_collect(tickers, get=http_json, pause=0.6, log=print):
    """{ticker: {day: [buy, sell]}} in dollars for Bitget's RWA perpetuals whose ticker is asked for (shares × the day's
    average price from its daily candle)."""
    cs = (get(f'{BITGET}/market/contracts?productType=USDT-FUTURES') or {}).get('data') or []
    out = {}
    for c in cs:
        if c.get('isRwa') != 'YES' or c.get('symbolStatus') not in (None, 'normal'):
            continue
        t = ticker_of(c.get('baseCoin'))
        if t not in tickers:
            continue
        sym = c['symbol']
        tk = (get(f'{BITGET}/market/taker-buy-sell?symbol={sym}&period=1d&limit=30') or {}).get('data') or []
        time.sleep(pause)
        if not tk:
            continue
        cd = (get(f'{BITGET}/market/candles?symbol={sym}&productType=USDT-FUTURES&granularity=1D&limit=40') or {}).get('data') or []
        time.sleep(pause)
        px = {}
        for row in cd:
            try:
                base_v, quote_v = float(row[5]), float(row[6])
                px[day_of(row[0])] = quote_v / base_v if base_v > 0 else float(row[4])
            except (ValueError, IndexError, TypeError):
                continue
        days = {}
        for row in tk:
            d = day_of(row.get('ts'))
            p = px.get(d)
            b, s = float(row.get('buyVolume') or 0), float(row.get('sellVolume') or 0)
            if p and (b or s):
                days[d] = [b * p, s * p]
        if days:
            out.setdefault(t, {}).update(days)
    log(f'Bitget: {len(out)} stock perpetuals read')
    return out


def day_of(ms):
    """The exchanges' day (from 16:00 UTC) by the UTC date it starts on."""
    return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).date().isoformat()


def merge(path, new):
    try:
        old = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        old = {}
    for t, days in new.items():
        old.setdefault(t, {}).update(days)
    out = {t: dict(sorted(d.items())) for t, d in sorted(old.items())}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(out, separators=(',', ':')), encoding='utf-8')
    return out


def collect(root, tickers, log=print, venues=None):
    root = Path(root)
    venues = venues or {'okx': okx_collect, 'bitget': bitget_collect}
    got = {}
    for name, fn in venues.items():
        try:
            got[name] = merge(root / 'cache' / 'perps' / f'{name}.json', fn(set(tickers), log=log))
        except Exception as e:                            # an experiment: one venue failing stops nothing else
            log(f'{name}: {e}')
    return got


def friday_of(day):
    d = dt.date.fromisoformat(day)
    if d.weekday() >= 5:                                  # the weekend counts in the week after
        d += dt.timedelta(days=7 - d.weekday())
    return (d + dt.timedelta(days=4 - d.weekday())).isoformat()


def weekly(root, grid):
    """{ticker: (buy[], sell[])} on the weekly grid, dollars, both venues added up (None where nothing traded)."""
    pos = {w: i for i, w in enumerate(grid)}
    out = {}
    for p in sorted((Path(root) / 'cache' / 'perps').glob('*.json')):
        try:
            doc = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for t, days in doc.items():
            for d, (b, s) in days.items():
                i = pos.get(friday_of(d))
                if i is None:
                    continue
                a = out.get(t)
                if a is None:
                    a = out[t] = ([None] * len(grid), [None] * len(grid))
                a[0][i] = (a[0][i] or 0) + b
                a[1][i] = (a[1][i] or 0) + s
    return out


def _rank(a):
    s = sorted(range(len(a)), key=lambda i: a[i])
    r, i = [0.0] * len(a), 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and a[s[j + 1]] == a[s[i]]:
            j += 1
        for k in range(i, j + 1):
            r[s[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < 8:
        return None
    rx, ry = _rank(x), _rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def stats(perps, flows, grid, bench='SPY'):
    """The experiment so far (see the module's note): ticker-weeks pooled, rank correlations and their counts; and the
    week-by-week rank correlation with the next week's return against SPY, averaged."""
    B = flows.get(bench)
    if not B:
        return None
    ret = lambda F, i: (F['ac'][i] / F['ac'][i - 1]) if i > 0 and F['ac'][i] and F['ac'][i - 1] else None
    rows = []
    for t, (buy, sell) in perps.items():
        F = flows.get(t)
        if not F or t == bench:
            continue
        for i in range(len(grid)):
            b, s = buy[i] or 0, sell[i] or 0
            if b + s < MIN_WEEK:
                continue
            r, m = ret(F, i), ret(B, i)
            rn, mn = (ret(F, i + 1), ret(B, i + 1)) if i + 1 < len(grid) else (None, None)
            nb, ns = (buy[i + 1] or 0, sell[i + 1] or 0) if i + 1 < len(grid) else (0, 0)
            y = 100 * F['mf'][i] / F['dv'][i] if F['mf'][i] is not None and F['dv'][i] else None
            x = 200 * (F['r'][i] - F['b'][i]) if F['r'][i] is not None and F['b'][i] is not None else None
            rows.append({'t': t, 'i': i, 'net': 100 * (b - s) / (b + s),
                         'rel': None if r is None or m is None else math.log(r / m),
                         'nrel': None if rn is None or mn is None else math.log(rn / mn),
                         'y': y, 'x': x, 'pn': 100 * (nb - ns) / (nb + ns) if nb + ns >= MIN_WEEK else None})
    if not rows:
        return {'n': 0}

    def corr(k):
        p = [(r['net'], r[k]) for r in rows if r[k] is not None]
        v = spearman([a for a, _ in p], [b for _, b in p])
        return {'rho': None if v is None else round(v, 3), 'n': len(p)}
    ics = []
    for i in sorted({r['i'] for r in rows}):
        p = [(r['net'], r['nrel']) for r in rows if r['i'] == i and r['nrel'] is not None]
        v = spearman([a for a, _ in p], [b for _, b in p]) if len(p) >= 8 else None
        if v is not None:
            ics.append(v)
    nets = sorted(abs(r['net']) for r in rows)
    return {'n': len(rows), 'tickers': len({r['t'] for r in rows}), 'from': grid[min(r['i'] for r in rows)], 'to': grid[max(r['i'] for r in rows)],
            'rel': corr('rel'), 'y': corr('y'), 'x': corr('x'), 'next': corr('nrel'), 'persist': corr('pn'),
            'ic': {'mean': round(sum(ics) / len(ics), 3), 'weeks': len(ics), 'positive': sum(1 for v in ics if v > 0)} if ics else None,
            'median_abs': round(nets[len(nets) // 2], 2), 'min_week': MIN_WEEK}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--bars', required=True, help="research-paths' cache/ohlc/: the tickers the site has daily bars for")
    a = ap.parse_args(argv)
    names = {p.name[:-len('.json.gz')] for p in Path(a.bars).glob('*.json.gz') if not p.name.endswith('.base.json.gz')}
    collect(a.root, names)


if __name__ == '__main__':
    main()
