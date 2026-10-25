"""Price paths & patterns: daily bars for every valued company, then for each one the correlated price paths of seven
models, analog and correlated-asset historical simulations, and rule-based price-action readings — each checked out of
sample. Kept on the branch "research-paths" (.github/workflows/research-paths.yml); scan.yml publishes public/ at
disclosures/data/research/paths/, drawn by docs/paths-view.js (company page "Price paths & patterns" and the hub's
"Price paths" tab).

  collect   daily open / high / low / close, the dividend- and split-adjusted close and volume (Yahoo's daily chart, Stooq's
            daily file as the fallback) for the valued companies (research-valuation's index.json), the S&P 500 ETF (SPY)
            and the sector and style ETFs: ten years on the first fetch, then the last months merged in (a refresh restates
            every earlier adjusted close after a dividend or split, so the rows on file are rescaled to the new basis).
            cache/ohlc/<TICKER>.json.gz, state.json.
  build     public/c/<cik>.json per company, public/index.json, public/models.json (the walk-forward scorecard of every
            path model and analog method), public/rules.json (every price-action rule with its pooled, out-of-sample
            evidence), public/portfolios/{m,o}/… (13F managers' and officials' portfolios), public/ledger.json (each week's
            forecasts frozen, then scored), public/status.json.

Modules: paths_models.py (the seven path models), analogs.py (analogs, correlated peers, peer-conditional simulation),
price_action.py (the rules, the current reading, the pooled backtest).

    python app/paths.py collect --root P --universe val/public/index.json --minutes 25
    python app/paths.py build --root P [--people <hub data>/research/people]
"""
import argparse
import datetime as dt
import gzip
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import Client, now, read_json, write_json   # noqa: E402
import rotation_history as RH                           # noqa: E402  (ticker symbols, the sector and style ETFs)

YEARS = 10                                   # history asked for on the first fetch
REFRESH_DAYS = 1                             # a ticker on file is refreshed when its last fetch is older than this
REFRESH_SPAN = 120                           # days asked for on a refresh
YAHOO_D = ('https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit'
           '&includeAdjustedClose=true')
STOOQ_D = 'https://stooq.com/q/d/l/?s={s}&i=d'
ETFS = [RH.BENCH] + [t for t, _, _ in RH.SECTOR_ETFS] + ['QQQ', 'IWM', 'DIA', 'TLT', 'GLD']
SECTOR_ETF = {k: t for t, k, _ in RH.SECTOR_ETFS}
FORMAT = 1
HORIZON = 63                                 # trading days ahead (about 13 weeks)
WINDOW = 756                                 # three years of daily returns behind each path model
N_PATHS = 600                                # paths per model and company (the ensemble pools them)


def sig(x, n=6):
    return None if x is None or not isinstance(x, (int, float)) or not math.isfinite(x) else float(f'{x:.{n}g}')


# ------------------------------------------------------------------ parsing the daily bars
def parse_yahoo_daily(payload):
    """Yahoo's daily chart → {'t','o','h','l','c','ac','v'} (columns, oldest first). OHLC are split-adjusted as Yahoo
    serves them; 'ac' is also adjusted for dividends. Days without a close are dropped."""
    res = ((payload or {}).get('chart') or {}).get('result') or []
    if not res:
        raise ValueError('no chart result: ' + str(((payload or {}).get('chart') or {}).get('error'))[:160])
    r = res[0]
    stamps = r.get('timestamp') or []
    ind = r.get('indicators') or {}
    q = (ind.get('quote') or [{}])[0] or {}
    adj = ((ind.get('adjclose') or [{}])[0] or {}).get('adjclose') or []
    off = (r.get('meta') or {}).get('gmtoffset') or 0
    out = {k: [] for k in ('t', 'o', 'h', 'l', 'c', 'ac', 'v')}
    seen = set()
    for i, ts in enumerate(stamps):
        g = lambda k: (q.get(k) or [None] * len(stamps))[i] if i < len(q.get(k) or []) else None
        c = g('close')
        if c is None or not math.isfinite(c) or c <= 0:
            continue
        d = dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).date().isoformat()
        if d in seen:
            continue
        seen.add(d)
        o, h, lo, v = g('open'), g('high'), g('low'), g('volume')
        a = adj[i] if i < len(adj) and adj[i] is not None and math.isfinite(adj[i]) and adj[i] > 0 else c
        o = o if o is not None and math.isfinite(o) and o > 0 else c
        h = max(x for x in (h, o, c) if x is not None and math.isfinite(x))
        lo = min(x for x in (lo, o, c) if x is not None and math.isfinite(x) and x > 0)
        for k, x in (('t', d), ('o', sig(o)), ('h', sig(h)), ('l', sig(lo)), ('c', sig(c)), ('ac', sig(a)), ('v', int(v or 0))):
            out[k].append(x)
    if len(out['t']) < 2:
        raise ValueError('no daily rows in the chart response')
    check_daily(out['t'])
    return out


def parse_stooq_daily(text):
    """Stooq's daily CSV (Date,Open,High,Low,Close,Volume) → the same columns; Stooq's closes are already adjusted for
    splits and dividends, so 'ac' = 'c'."""
    if '<html' in (text or '')[:400].lower() or 'Exceeded' in (text or '')[:200]:
        raise ValueError('Stooq answered with a page instead of CSV')
    lines = [x for x in (text or '').strip().splitlines() if x.strip()]
    if not lines or not lines[0].lower().startswith('date'):
        raise ValueError('not a Stooq CSV')
    head = [x.strip().lower() for x in lines[0].split(',')]
    ix = {k: head.index(k) for k in ('date', 'open', 'high', 'low', 'close') if k in head}
    iv = head.index('volume') if 'volume' in head else None
    out = {k: [] for k in ('t', 'o', 'h', 'l', 'c', 'ac', 'v')}
    for x in lines[1:]:
        p = x.split(',')
        try:
            o, h, lo, c = (float(p[ix[k]]) for k in ('open', 'high', 'low', 'close'))
            dt.date.fromisoformat(p[ix['date']])
        except (ValueError, IndexError, KeyError):
            continue
        if c <= 0:
            continue
        for k, v in (('t', p[ix['date']]), ('o', sig(o)), ('h', sig(max(h, o, c))), ('l', sig(min(lo, o, c))), ('c', sig(c)), ('ac', sig(c)),
                     ('v', int(float(p[iv])) if iv is not None and p[iv] else 0)):
            out[k].append(v)
    if len(out['t']) < 2:
        raise ValueError('no rows in the Stooq file')
    check_daily(out['t'])
    return out


def check_daily(days):
    """Refuse bars that are not daily (a source answering with weekly or monthly bars)."""
    if len(days) >= 20:
        gaps = sorted((dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days for a, b in zip(days, days[1:]))
        if gaps[len(gaps) // 2] > 3:
            raise ValueError(f'bars are {gaps[len(gaps) // 2]} days apart, not daily')


def merge(old, new):
    """A refresh merged into the bars on file. After a dividend Yahoo restates every earlier adjusted close, and after a
    split every earlier open / high / low / close and volume; the rows on file are put on the new basis by the ratios of
    the two answers on the first day they share, then the overlapping days are taken from the new answer."""
    if not old or not old.get('t'):
        return new
    if not new or not new.get('t'):
        return old
    at = {d: i for i, d in enumerate(old['t'])}
    first = next((j for j, d in enumerate(new['t']) if d in at), None)
    if first is None:                                       # no shared day: the refresh starts after a gap
        f_ac = f_c = 1.0
    else:
        i = at[new['t'][first]]
        f_ac = new['ac'][first] / old['ac'][i] if old['ac'][i] else 1.0
        f_c = new['c'][first] / old['c'][i] if old['c'][i] else 1.0
    cut = new['t'][0]
    keep = [i for i, d in enumerate(old['t']) if d < cut]
    out = {k: [] for k in ('t', 'o', 'h', 'l', 'c', 'ac', 'v')}
    for i in keep:
        out['t'].append(old['t'][i])
        for k in ('o', 'h', 'l', 'c'):
            out[k].append(sig(old[k][i] * f_c))
        out['ac'].append(sig(old['ac'][i] * f_ac))
        out['v'].append(int(old['v'][i] / f_c) if f_c else old['v'][i])
    for k in out:
        out[k] += list(new[k])
    return out


# ------------------------------------------------------------------ the cache
def cache_path(root, ticker, part=''):
    return Path(root) / 'cache' / 'ohlc' / (RH.symbol(ticker) + part + '.json.gz')


def _read_gz(p):
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_gz(p, doc):
    """Deterministic gzip (no timestamp in the header): an unchanged file is byte-identical, so git sees no change."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    raw = json.dumps(doc, separators=(',', ':')).encode('utf-8')
    with open(tmp, 'wb') as fh, gzip.GzipFile(fileobj=fh, mode='wb', mtime=0) as gz:
        gz.write(raw)
    tmp.replace(p)


def load(root, ticker):
    """The bars on file: the base (everything before the last two months, rewritten only when a dividend or a split
    restates history) joined to the recent part (rewritten every refresh)."""
    rec = _read_gz(cache_path(root, ticker))
    if not rec:
        return None
    base = _read_gz(cache_path(root, ticker, '.base')) if rec.get('base') else None
    if base:
        for k in ('t', 'o', 'h', 'l', 'c', 'ac', 'v'):
            rec[k] = base[k] + rec[k]
    rec.pop('base', None)
    return rec


def save(root, ticker, doc):
    cut = (dt.date.today().replace(day=1) - dt.timedelta(days=40)).replace(day=1).isoformat()
    i = next((j for j, d in enumerate(doc['t']) if d >= cut), len(doc['t']))
    cols = ('t', 'o', 'h', 'l', 'c', 'ac', 'v')
    meta = {k: v for k, v in doc.items() if k not in cols}
    if i > 0:
        _write_gz(cache_path(root, ticker, '.base'), {k: doc[k][:i] for k in cols})
    else:
        cache_path(root, ticker, '.base').unlink(missing_ok=True)
    _write_gz(cache_path(root, ticker), {**meta, 'base': i > 0, **{k: doc[k][i:] for k in cols}})


def fetch(client, ticker, full=True, sources=('yahoo', 'stooq')):
    """(bars, source): ten years (full) or the last REFRESH_SPAN days; raises with every source's error."""
    problems = []
    for src in sources:
        try:
            if src == 'yahoo':
                p2 = int(time.time()) + 86400
                p1 = p2 - (YEARS * 366 + 2) * 86400 if full else p2 - REFRESH_SPAN * 86400
                return parse_yahoo_daily(client.json(YAHOO_D.format(s=RH.symbol(ticker), p1=p1, p2=p2))), 'yahoo'
            if src == 'stooq':
                bars = parse_stooq_daily(client.get(STOOQ_D.format(s=RH.symbol(ticker).lower() + '.us')).decode('utf-8', 'replace'))
                if not full:
                    bars = {k: v[-REFRESH_SPAN:] for k, v in bars.items()}
                else:
                    since = (dt.date.today() - dt.timedelta(days=YEARS * 366)).isoformat()
                    i0 = next((i for i, d in enumerate(bars['t']) if d >= since), 0)
                    bars = {k: v[i0:] for k, v in bars.items()}
                return bars, 'stooq'
        except Exception as exc:
            problems.append(f'{src}: {str(exc)[:160]}')
    raise RuntimeError(' | '.join(problems))


def universe(index_path):
    """[{'t', 'cik', 'name', 'sector', 'kind', 'mcap'}] of the valued companies (research-valuation's index.json), largest
    first, then the ETFs."""
    ix = read_json(index_path, {}) if index_path else {}
    F = ix.get('fields') or []
    rows = [dict(zip(F, r)) for r in ix.get('rows') or []]
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: -(r.get('mcap') or 0)):
        try:
            t = RH.symbol(r.get('ticker') or '')
        except ValueError:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append({'t': t, 'cik': r.get('cik'), 'name': r.get('name'), 'sector': r.get('sector') or 'other', 'kind': r.get('kind'),
                    'mcap': r.get('mcap')})
    return out


def collect(client, root, tickers, batch=2000, refresh=2500, minutes=25.0, first=()):
    """Fetch up to `batch` tickers never fetched (in order) and refresh up to `refresh` stale ones (oldest first), within
    `minutes`. Failures back off 1, 2, 4 … 30 days. Returns what was done."""
    root = Path(root)
    state = read_json(root / 'state.json', {})
    if state.get('format', 0) < FORMAT:
        state = {'format': FORMAT, 'tickers': {}}
    tk = state.setdefault('tickers', {})
    t0, today = time.monotonic(), dt.datetime.now(dt.timezone.utc)
    stale = (today - dt.timedelta(days=REFRESH_DAYS) + dt.timedelta(hours=2)).isoformat()
    first = {RH.symbol(t) for t in first if t}
    ok_now = lambda t: (tk.get(t) or {}).get('retry_after', '') <= today.isoformat()
    new = [t for t in tickers if t in first or (not (tk.get(t) or {}).get('fetched_at') and ok_now(t))]
    old = sorted((t for t in tickers if t not in first and (tk.get(t) or {}).get('fetched_at', '9') < stale and ok_now(t)),
                 key=lambda t: tk[t]['fetched_at'])
    done = {'new': 0, 'refreshed': 0, 'failed': 0, 'skipped_time': 0}
    plan = [(t, True) for t in new[:batch]] + [(t, False) for t in old[:refresh]]
    for i, (t, full) in enumerate(plan):
        if time.monotonic() - t0 > minutes * 60:
            done['skipped_time'] = len(plan) - i
            break
        info = tk.setdefault(t, {})
        try:
            have = None if full else load(root, t)
            bars, src = fetch(client, t, full=full or not have)
            if have:
                bars = merge(have, bars)
            save(root, t, {'ticker': t, 'source': src, 'fetched_at': now(), **bars})
            info.update(fetched_at=now(), source=src, first=bars['t'][0], last=bars['t'][-1], days=len(bars['t']), fails=0)
            info.pop('error', None)
            info.pop('retry_after', None)
            done['new' if full or not have else 'refreshed'] += 1
        except Exception as exc:
            n = int(info.get('fails') or 0) + 1
            info.update(fails=n, error=str(exc)[:300], tried_at=now(),
                        retry_after=(today + dt.timedelta(days=min(30, 2 ** (n - 1)))).isoformat())
            done['failed'] += 1
        if i % 50 == 49:
            write_json(root / 'state.json', state)
    have = [t for t in tickers if (tk.get(t) or {}).get('fetched_at')]
    state['summary'] = {'updated_at': now(), 'universe': len(tickers), 'on_file': len(have),
                        'waiting': sum(1 for t in tickers if t not in have and not (tk.get(t) or {}).get('fails')),
                        'failing': sum(1 for t in tickers if t not in have and (tk.get(t) or {}).get('fails')), 'last_run': done}
    write_json(root / 'state.json', state)
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['collect', 'build'])
    ap.add_argument('--root', default='paths')
    ap.add_argument('--universe', default=None, help="research-valuation's public/index.json")
    ap.add_argument('--people', default=None, help="the hub's research/people folder (managers.json, m/, officials.json, o/)")
    ap.add_argument('--batch', type=int, default=2000)
    ap.add_argument('--refresh', type=int, default=2500)
    ap.add_argument('--minutes', type=float, default=25)
    ap.add_argument('--tickers', default='')
    ap.add_argument('--limit', type=int, default=0, help='build: only the first N companies (tests)')
    a = ap.parse_args()
    if a.cmd == 'collect':
        import tempfile
        cfg = read_json(Path(__file__).resolve().parents[1] / 'config' / 'settings.json', {})
        http = cfg.get('http', {})
        client = Client(tempfile.mkdtemp(prefix='paths-raw-'),
                        {**http, 'host_intervals': {**http.get('host_intervals', {}), 'query1.finance.yahoo.com': 0.6, 'stooq.com': 1.0}})
        extra = [t for t in re.split(r'[\s,;]+', a.tickers or '') if t]
        tickers = list(dict.fromkeys([RH.symbol(t) for t in extra] + ETFS + [c['t'] for c in universe(a.universe)]))
        print(json.dumps(collect(client, a.root, tickers, a.batch, a.refresh, a.minutes, first=extra)))
    else:
        import paths_build
        print(json.dumps(paths_build.build(a.root, a.universe, a.people, limit=a.limit)))


if __name__ == '__main__':
    main()
