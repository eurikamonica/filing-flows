"""Momentum portfolios back-tested on daily closes (the hub's Momentum tab → Back-test): what buying the stocks that
rose most — or least — over a ranking period and holding them for a holding period would have returned since 2000.

Universe: the valued companies of the Move odds (research-paths public/moves/a/<KEY>.json, app/moves.py: daily
adjusted closes as log returns), each from its first close on file. They are today's companies: the ones that failed,
were bought or left the exchange are not in it (survivorship), which flatters every long portfolio, the losers' most.
Against SPY and the equal-weight average of the universe (rebalanced daily).

  ranking periods  the return over the last 1, 5, 10, 21 or 63 trading days (a day, a week, two weeks, a month, a
                   quarter), or 12-1: the last 252 days skipping the latest 21 (Jegadeesh & Titman 1993)
  holding periods  1, 5, 10, 21 or 63 trading days
  portfolios       top: the tenth of the ranked stocks that rose most, equal weight at the start; bottom: the tenth that
                   rose least; long-short: top less bottom (no financing cost, borrow fee or short rebate)

Overlapping portfolios (Jegadeesh & Titman 1993): at each close a portfolio is formed from the ranking up to that close
and held for K days from the next; the strategy holds the K latest, an equal share of the money each, so its return
does not depend on the day it began; each portfolio is bought and held (its weights drift with prices). A stock is
ranked when it has every return of the ranking period (12-1: 220 of its 231 days) and traded that day; at least 200
are ranked. A day a stock does not trade, it keeps its value. A day's return counts at most −50% / +100% (CLIP, as
the Move odds' industry composites): a bad print, or a restructuring the adjusted closes show as ×258, moves no
portfolio.

Trading: each day the oldest portfolio is sold and a new one bought — two-way turnover (1 − the share of names the two
have in common) × 2 ÷ K a day, the same for the bottom; the page takes trading costs off at that rate. No taxes.

backtest.json (schema momentum-backtest.v1): the month-end value of $1 in each strategy, SPY and the equal-weight
universe from the common start (the 63rd trading day of 2000, when every holding period has all its portfolios), and
per strategy and period (since then, the last ten and five years): the annual return, volatility (daily, annualised),
the return over the volatility, the maximum drawdown (daily closes), the share of months up and of months ahead of
SPY, beta and alpha (annual) against SPY on daily returns, the turnover and the stocks held.

    python app/momentum_backtest.py --root pth          (after app/paths.py moves; writes pth/public/backtest/)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths as P  # noqa: E402

SCHEMA = 'momentum-backtest.v1'
RANKS = [('1', 1), ('5', 5), ('10', 10), ('21', 21), ('63', 63), ('12-1', None)]
HOLDS = [1, 5, 10, 21, 63]
SIDES = ['top', 'bottom']
SHARE = 0.10                     # a tenth of the ranked stocks
MIN_RANKED = 200
FIRST = '2000-01-03'             # the first ranking day
WARM = '1998-12-01'              # the returns before it that a 12-1 ranking needs
SKIP, YEAR = 21, 252
MIN_12_1 = 220
PERIODS = [('all', None), ('10y', 10), ('5y', 5)]
CLIP = (math.log(0.5), math.log(2.0))   # a day's return at most −50% / +100%, as the Move odds' industry composites
                                         # (moves.CLIP): a bad print or a restructuring's ×258 moves no portfolio


def _r(v, n=4):
    return None if v is None or not math.isfinite(v) else round(float(v), n)


def _sig(v, n=4):
    """n significant digits: a growth of $1 that falls towards zero (a long-short of the one-day reversals) keeps its
    shape on a log scale."""
    return None if v is None or not math.isfinite(v) else float(f'{float(v):.{n}g}')


# ------------------------------------------------------------------ the data
def load(base, limit=0):
    """(calendar days, SPY's daily log returns on them, the stocks' keys, their log returns T × N with NaN where a
    stock did not trade or was not listed) from public/moves/."""
    base = Path(base)
    ix = json.loads((base / 'index.json').read_text())
    F = ix['fields']
    keys = sorted(r[F.index('key')] for r in ix['rows'] if r[F.index('kind')] == 'stock')
    if limit:
        keys = keys[:limit]
    sd, sr = P.decode_returns(json.loads((base / 'a' / 'SPY.json').read_text()))
    cal = [d for d in sd if d >= WARM]
    at = {d: i for i, d in enumerate(cal)}
    spy = np.full(len(cal), np.nan)
    for d, x in zip(sd[1:], sr):
        if d in at:
            spy[at[d]] = x
    L = np.full((len(cal), len(keys)), np.nan, dtype=np.float32)
    kept = []
    for i, k in enumerate(keys):
        p = base / 'a' / f'{k}.json'
        try:
            days, r = P.decode_returns(json.loads(p.read_text()))
        except (OSError, ValueError, KeyError):
            continue
        idx = np.fromiter((at.get(d, -1) for d in days[1:]), dtype=np.int64, count=len(r))
        ok = idx >= 0
        L[idx[ok], i] = r[ok]
        kept.append(i)
    L = np.clip(L[:, kept], *CLIP)
    return cal, spy, [keys[i] for i in kept], L


def signals(L):
    """{ranking: T × N ranking returns (NaN where a stock is not ranked that day)}."""
    have = np.isfinite(L)
    C = np.vstack([np.zeros((1, L.shape[1])), np.cumsum(np.where(have, L, 0.0), axis=0, dtype=np.float64)])   # C[t + 1] = Σ L[0..t]
    N = np.vstack([np.zeros((1, L.shape[1]), dtype=np.int32), np.cumsum(have, axis=0, dtype=np.int32)])
    T = L.shape[0]
    out = {}
    for name, J in RANKS:
        S = np.full(L.shape, np.nan, dtype=np.float32)
        if J:
            t = np.arange(J - 1, T)
            ret, cnt = C[t + 1] - C[t + 1 - J], N[t + 1] - N[t + 1 - J]
            S[t] = np.where(cnt == J, ret, np.nan)
        else:
            t = np.arange(YEAR - 1, T)                                  # 12-1: days t-251 … t-21
            ret, cnt = C[t + 1 - SKIP] - C[t + 1 - YEAR], N[t + 1 - SKIP] - N[t + 1 - YEAR]
            S[t] = np.where(cnt >= MIN_12_1, ret, np.nan)
        S[~have] = np.nan                                               # ranked only on a day it traded
        out[name] = S
    return out


def members(S, t, side):
    """The column indices of the tenth that rose most (top) or least (bottom) at close t; None under MIN_RANKED."""
    s = S[t]
    ok = np.flatnonzero(np.isfinite(s))
    if len(ok) < MIN_RANKED:
        return None
    n = max(1, int(math.ceil(SHARE * len(ok))))
    order = ok[np.argsort(s[ok], kind='stable')]
    return np.sort(order[-n:] if side == 'top' else order[:n])


# ------------------------------------------------------------------ the strategies
def run(cal, spy, L, log=print):
    """Daily returns of every strategy from the common start, turnover and holdings; (start index, dict)."""
    T = len(cal)
    first = next(i for i, d in enumerate(cal) if d >= FIRST)
    kmax = max(HOLDS)
    start = first + kmax                                                # every holding period has all its portfolios
    have = np.isfinite(L)
    Pix = np.exp(np.vstack([np.zeros((1, L.shape[1])), np.cumsum(np.where(have, L, 0.0), axis=0, dtype=np.float64)]))  # Pix[t + 1]: value after day t
    S = signals(L)
    out = {}
    for rname, _ in RANKS:
        for side in SIDES:
            t0 = time.monotonic()
            M = {}
            acc = {K: np.zeros(T) for K in HOLDS}
            held = {K: [] for K in HOLDS}
            for t in range(first, T - 1):
                m = members(S[rname], t, side)
                if m is None:
                    continue
                M[t] = m
                end = min(T - 1, t + kmax)
                rel = Pix[t + 2:end + 2, :][:, m] / Pix[t + 1, m]       # the value of each name on days t+1 … end
                V = rel.mean(axis=1)
                rc = np.diff(np.concatenate([[1.0], V])) / np.concatenate([[1.0], V[:-1]])
                for K in HOLDS:
                    k = min(K, len(rc))
                    acc[K][t + 1:t + 1 + k] += rc[:k]
            for K in HOLDS:
                r = acc[K] / K
                turn = []
                for t, m in M.items():
                    if t - K in M:
                        o = M[t - K]
                        turn.append(2.0 * (1.0 - len(np.intersect1d(m, o, assume_unique=True)) / max(len(m), len(o))) / K)
                out[(rname, K, side)] = {'r': r, 'turn': float(np.mean(turn)) if turn else None,
                                         'n': float(np.mean([len(m) for m in M.values()])) if M else None}
            log(f'  {rname} {side}: {len(M)} portfolios, {time.monotonic() - t0:.0f}s')
    for rname, _ in RANKS:
        for K in HOLDS:
            a, b = out[(rname, K, 'top')], out[(rname, K, 'bottom')]
            out[(rname, K, 'ls')] = {'r': np.maximum(a['r'] - b['r'], -0.99), 'turn': (a['turn'] or 0) + (b['turn'] or 0), 'n': a['n']}
    cnt = have.sum(axis=1)
    tot = np.where(have, np.expm1(L.astype(np.float64)), 0.0).sum(axis=1)
    ew = np.where(cnt >= MIN_RANKED, tot / np.maximum(cnt, 1), 0.0)
    out[('spy',)] = {'r': np.expm1(np.nan_to_num(spy)), 'turn': None, 'n': None}
    out[('ew',)] = {'r': ew, 'turn': None, 'n': None}
    return start, out, cnt


def stats(r, spy, days, months_end, since):
    """From day `since` on: the annual return, volatility, their ratio, the maximum drawdown, the share of months up
    and ahead of SPY, beta and alpha against SPY (daily)."""
    x, b = r[since:], spy[since:]
    if len(x) < 40:
        return None
    v = np.cumprod(1 + x)
    yrs = len(x) / YEAR
    cagr = v[-1] ** (1 / yrs) - 1
    vol = float(np.std(x, ddof=1) * math.sqrt(YEAR))
    dd = float(np.min(v / np.maximum.accumulate(v)) - 1)
    me = [i - since for i in months_end if i >= since]
    vm = np.concatenate([[1.0], v[me]])
    bm = np.concatenate([[1.0], np.cumprod(1 + b)[me]])
    mr, br = vm[1:] / vm[:-1] - 1, bm[1:] / bm[:-1] - 1
    cov = np.cov(x, b, ddof=1)
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else None
    alpha = float((np.mean(x) - (beta or 0) * np.mean(b)) * YEAR) if beta is not None else None
    return {'cagr': _r(cagr), 'vol': _r(vol), 'ratio': _r(cagr / vol if vol > 0 else None, 2), 'mdd': _r(dd),
            'up': _r(float(np.mean(mr > 0))), 'ahead': _r(float(np.mean(mr > br))), 'beta': _r(beta, 2), 'alpha': _r(alpha),
            'total': _r(v[-1] - 1, 3), 'from': days[since]}


def build(base, out_dir, limit=0, log=print):
    t0 = time.monotonic()
    cal, spy, keys, L = load(base, limit)
    log(f'momentum back-test: {len(keys)} stocks, {len(cal)} days {cal[0]} … {cal[-1]}')
    start, res, cnt = run(cal, spy, L, log)
    T = len(cal)
    spy_r = res[('spy',)]['r']
    months_end = [i for i in range(start, T) if i == T - 1 or cal[i][:7] != cal[i + 1][:7]]
    last = dt.date.fromisoformat(cal[-1])
    since = {}
    for pname, yrs in PERIODS:
        if yrs is None:
            since[pname] = start
        else:
            cut = last.replace(year=last.year - yrs).isoformat()
            since[pname] = max(start, next((i for i, d in enumerate(cal) if d > cut), start))
    doc = {'schema': SCHEMA, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'as_of': cal[-1],
           'start': cal[start], 'stocks': len(keys), 'share': SHARE, 'min_ranked': MIN_RANKED,
           'ranks': [r for r, _ in RANKS], 'holds': HOLDS, 'months': [cal[i] for i in months_end],
           'periods': {p: cal[i] for p, i in since.items()},
           'traded': [int(cnt[i]) for i in months_end],
           'series': {}, 'stats': {}, 'turn': {}, 'held': {}}
    for key, v in res.items():
        name = '|'.join(str(x) for x in key)
        g = np.cumprod(1 + v['r'][start:])
        doc['series'][name] = [_sig(float(g[i - start])) for i in months_end]
        doc['stats'][name] = {p: stats(v['r'], spy_r, cal, months_end, i) for p, i in since.items()}
        if v['turn'] is not None:
            doc['turn'][name] = _r(v['turn'], 5)
            doc['held'][name] = _r(v['n'], 1)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / 'momentum.json.tmp'
    tmp.write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(out / 'momentum.json')
    log(f'momentum back-test: {len(res)} lines to {out / "momentum.json"} in {time.monotonic() - t0:.0f}s')
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', required=True, help="research-paths' working copy (public/moves/ in, public/backtest/ out)")
    ap.add_argument('--limit', type=int, default=0, help='the first N stocks only (a check)')
    a = ap.parse_args()
    root = Path(a.root)
    build(root / 'public' / 'moves', root / 'public' / 'backtest', a.limit)


if __name__ == '__main__':
    main()
