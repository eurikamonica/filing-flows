"""Momentum × RRG strategies (the hub's Momentum tab → Strategy picker): the companies that rose most over a ranking
period, bought when their RRG against SPY stands in a chosen quadrant and sold when it turns to another, or when they
drop out of the winners — back-tested since 2000 week by week; how each strategy has done lately against how it did
before (strategies fade); whether picking the one that led over the last years has paid; and the one that leads now,
with what it holds today, since when, how long its positions have lasted and the conditions that end them.

Data: the Move odds' daily adjusted closes of the valued companies (public/moves/a/; rrg_backtest.load), each week's
last close (rrg_backtest.grid). Today's companies only (survivorship): judge a strategy against the equal weight of the
same companies, which carries the same bias, rather than against SPY alone.

Each week, at its last close:
  momentum   the return over a ranking period — 12-1 (52 weeks less the latest 4), 6-1 (26 less 4) or the last 13
             weeks — as a percentile among the companies ranked that week (at least MIN_RANKED)
  RRG        the chart's weekly RRG against SPY (rrg_backtest.quadrants: Leading, Weakening, Lagging, Improving)
A strategy enters a company in the momentum band's top (10% or 20%) whose RRG stands in its entry quadrants and holds
it until the company drops below the band's exit (the top 20% or 40%: a buffer, so a name is not sold the week it
slips) or its RRG reaches the rule's exit quadrants (RULES). The portfolio holds its companies equal weight from one
week's close to the next (cash when it holds none); its turnover is the share sold plus the share bought each week.

Out (public/backtest/combo.json, schema combo-backtest.v1, the momentum back-test's shape for the series): per strategy
the month-end values of $1, statistics over the whole period and the last 10, 5, 3 years and year (with the gap to the
equal weight a year and the turnover, so the page takes costs off at any rate), each calendar year's return, its trades
(how long, how much, how often ahead of the equal weight over the same weeks) with a histogram of their lengths in
weeks, and the companies it holds now (since when, the return since); the walk-forward record — each January the
strategy whose information ratio against the equal weight (the weekly gap's mean over its spread, after COST a trade)
is best both lately and over the long run — the lower of its ratio over the last 3 years (or year) and since the start,
so a strategy that has faded scores low and so does one on a lucky run with no record behind it — among those holding
MIN_HELD companies or more on average, held that year — against the average strategy; and today's order by the same
score. (The rule is one of a dozen tried on this data: all of them beat the average strategy by between 0 and 4% a year,
in 13 to 16 of 22 years.)

    python app/combo_backtest.py --root pth          (after app/paths.py moves; writes pth/public/backtest/combo.json)
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
import momentum_backtest as MB  # noqa: E402
import rrg_backtest as RB  # noqa: E402

SCHEMA = 'combo-backtest.v1'
MEASURES = (('12-1', 52, 4), ('6-1', 26, 4), ('3m', 13, 0))          # (key, weeks back, latest weeks skipped)
BANDS = ((10, 20), (20, 40))                                          # enter in the top %, sold below the top %
# (key, entry quadrants (None: any), exit quadrants (None: none)) — quadrants as rrg_research: 0 Leading,
# 1 Weakening, 2 Lagging, 3 Improving
RULES = (('mom', None, None),            # momentum alone
         ('imp-fade', (3,), (1, 2)),     # enter in Improving; sold when RS-Momentum falls below 100
         ('imp-fail', (3,), (2,)),       # enter in Improving; sold if it falls back to Lagging
         ('lead-fade', (0,), (1, 2)),    # enter in Leading; sold when RS-Momentum falls below 100
         ('lead-trend', (0,), (2, 3)),   # enter in Leading; sold when RS-Ratio falls below 100
         ('up-fade', (0, 3), (1, 2)),    # enter in Leading or Improving; sold when RS-Momentum falls below 100
         ('up-fail', (0, 3), (2,)),      # enter in Leading or Improving; sold if it falls to Lagging
         ('dip-ride', (2,), (1,)))       # a winner in Lagging (a pullback); sold when it reaches Weakening
COST = 0.001                             # the cost of a trade the pick and the walk-forward record assume
PERIODS = (('all', None), ('10y', 10), ('5y', 5), ('3y', 3), ('1y', 1))
WINDOWS = (('3y', 156), ('1y', 52))      # the pick's recent window: the last 3 years, or the last year
MIN_HELD = 20                            # a pick holds 20 companies or more on average over its window: the strategies
                                         # that hold two or three led some windows by luck and lost the next year
MIN_RANKED = 200
FIRST = '2000-01-03'
DUR_BINS = 157                           # trade lengths 1 … 156 weeks, the last bin 157 and more


def key_of(rule, measure, band):
    return f'{rule}|{measure}|{band[0]}'


def percentiles(M):
    """Each column's values as percentiles in [0, 1] (1 the highest); NaN where missing or where the column ranks
    fewer than MIN_RANKED companies."""
    N, T = M.shape
    out = np.full((N, T), np.nan, dtype=np.float32)
    for t in range(T):
        v = M[:, t]
        ok = np.flatnonzero(np.isfinite(v))
        if len(ok) < MIN_RANKED:
            continue
        r = np.empty(len(ok))
        r[np.argsort(v[ok], kind='stable')] = np.arange(len(ok))
        out[ok, t] = r / (len(ok) - 1)
    return out


def momentum(C):
    """{measure: lines × weeks of the return over its ranking period, NaN without the closes}."""
    N, T = C.shape
    out = {}
    for k, back, skip in MEASURES:
        M = np.full((N, T), np.nan)
        with np.errstate(divide='ignore', invalid='ignore'):
            M[:, back:] = C[:, back - skip:T - skip] / C[:, :T - back] - 1
        out[k] = M
    return out


def simulate(r, pct, q, enter_q, exit_q, band, first):
    """One strategy week by week from `first`: the portfolio's return each week (decided at the close before), its
    turnover, the companies held, the trades (entry week, exit week, company) and the positions open at the end."""
    N, T = pct.shape
    top_in, top_out = 1 - band[0] / 100, 1 - band[1] / 100
    held = np.zeros(N, bool)
    since = np.full(N, -1)
    rp, tv, n = np.zeros(T), np.zeros(T), np.zeros(T)
    te, tx, tk = [], [], []
    eq = np.array(enter_q) if enter_q else None
    xq = np.array(exit_q) if exit_q else None
    for t in range(first, T):
        p, qt = pct[:, t], q[:, t]
        ok = np.isfinite(p)
        keep = ok & (p >= top_out)
        if xq is not None:
            keep &= ~np.isin(qt, xq)
        enter = ok & (p >= top_in) & (qt >= 0)
        if eq is not None:
            enter &= np.isin(qt, eq)
        new = (held & keep) | (~held & enter)
        out, inn = held & ~new, new & ~held
        if out.any():
            i = np.flatnonzero(out)
            te.append(since[i])
            tx.append(np.full(len(i), t))
            tk.append(i)
        since[inn] = t
        a, b = int(held.sum()), int(new.sum())
        tv[t] = (out.sum() / a if a else 0.0) + (inn.sum() / b if b else 0.0)
        held = new
        n[t] = b
        if b and t + 1 < T:
            rp[t + 1] = float(np.mean(r[held, t + 1]))
    cat = lambda xs: np.concatenate(xs) if xs else np.zeros(0, dtype=np.int64)  # noqa: E731
    return {'r': rp, 'tv': tv, 'n': n, 'te': cat(te), 'tx': cat(tx), 'tk': cat(tk), 'open': np.flatnonzero(held), 'since': since}


def stats(r, ew, b, tv, months_end, since):
    """rrg_backtest.stats on weeks plus the gap to the equal weight a year (and its t-statistic) and the turnover a
    week, from week `since` on."""
    s = RB.stats(r, b, months_end, since, 52)
    if s is None:
        return None
    x = r[since:] - ew[since:]
    sd = float(np.std(x, ddof=1)) if len(x) > 2 else 0.0
    s['excess'] = MB._r(float(np.mean(x)) * 52)
    s['t'] = MB._r(float(np.mean(x)) / sd * math.sqrt(len(x)), 2) if sd > 0 else None
    s['turn_w'] = MB._r(float(np.mean(tv[since - 1:len(tv) - 1])), 5)          # the turnover behind each week's return
    return s


def years(r, days, start):
    """Each calendar year's return from the weekly returns (the first year from the start)."""
    out, cur, g = [], None, 1.0
    for t in range(start, len(r)):
        y = days[t][:4]
        if cur is not None and y != cur:
            out.append([int(cur), MB._r(g - 1)])
            g = 1.0
        cur = y
        g *= 1 + r[t]
    if cur is not None:
        out.append([int(cur), MB._r(g - 1)])
    return out


def build(base, out_path, log=print):
    t0 = time.monotonic()
    cal, spy, meta, L = RB.load(base)
    rows = [i for i, m in enumerate(meta) if m['group'] == 'companies']
    meta = [meta[i] for i in rows]
    g = RB.grid(cal, 'w')
    days = [cal[i] for i in g]
    C = RB.levels(L[rows])[:, g]
    del L
    B = RB.levels(spy[None, :])[0][g]
    N, T = C.shape
    log(f'combo backtest: {N} companies, {T} weeks {days[0]} … {days[-1]}')
    X, Y, q = RB.quadrants(C, B, 'w')
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.where(np.isfinite(C[:, 1:]) & np.isfinite(C[:, :-1]), C[:, 1:] / C[:, :-1] - 1, np.nan)
    r = np.concatenate([np.full((N, 1), np.nan), r], axis=1)
    ew = np.zeros(T)
    has = np.isfinite(r)
    ew[1:] = np.where(has[:, 1:].sum(0) > 0, np.nansum(r[:, 1:], 0) / np.maximum(has[:, 1:].sum(0), 1), 0.0)
    b = np.concatenate([[0.0], B[1:] / B[:-1] - 1])
    mom = momentum(C)
    pct = {k: percentiles(M) for k, M in mom.items()}
    del mom
    f0 = next(i for i, d in enumerate(days) if d >= FIRST)
    ranked = np.min([np.isfinite(p).sum(0) for p in pct.values()], axis=0)
    first = next(t for t in range(f0, T) if ranked[t] >= MIN_RANKED and (q[:, t] >= 0).sum() >= MIN_RANKED)
    start = first + 1                                                     # the first week with a portfolio's return
    months_end = [i for i in range(start, T) if i == T - 1 or days[i][:7] != days[i + 1][:7]]
    last = dt.date.fromisoformat(days[-1])
    since = {}
    for pname, yrs in PERIODS:
        if yrs is None:
            since[pname] = start
        else:
            cut = last.replace(year=last.year - yrs).isoformat()
            since[pname] = max(start, next((i for i, d in enumerate(days) if d > cut), start))
    I = np.cumprod(1 + ew)                                               # the equal weight's level, to judge trades
    doc = {'schema': SCHEMA, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'as_of': days[-1],
           'start': days[start], 'formed_from': days[first], 'companies': N, 'cost': COST, 'min_ranked': MIN_RANKED,
           'measures': [m[0] for m in MEASURES], 'bands': [list(x) for x in BANDS], 'rules': [x[0] for x in RULES],
           'rule_quadrants': {k: {'enter': list(e) if e else None, 'exit': list(x) if x else None} for k, e, x in RULES},
           'months': [days[i] for i in months_end], 'periods': {p: days[i] for p, i in since.items()},
           'series': {}, 'stats': {}, 'turn': {}, 'held': {}, 'years': {}, 'trades': {}, 'now': {}}
    nets, nheld = {}, {}
    held_keys = set()

    def put(name, rr, tv=None):
        v = np.cumprod(1 + rr[start:])
        doc['series'][name] = [MB._sig(float(v[i - start])) for i in months_end]
        doc['stats'][name] = {p: stats(rr, ew, b, tv if tv is not None else np.zeros(T), months_end, i) for p, i in since.items()}
        doc['years'][name] = years(rr, days, start)
    for rule, eq, xq in RULES:
        for mk, _, _ in MEASURES:
            for band in BANDS:
                k = key_of(rule, mk, band)
                s = simulate(r, pct[mk], q, eq, xq, band, first)
                put(k, s['r'], s['tv'])
                doc['turn'][k] = MB._r(float(np.mean(s['tv'][start - 1:T - 1])) * 52 / 252, 5)
                doc['held'][k] = MB._r(float(np.mean(s['n'][first:])), 1)
                net = s['r'].copy()
                net[1:] -= COST * s['tv'][:-1]
                nets[k] = net
                nheld[k] = s['n']
                # the trades: closed, then the ones still open (as far as they have come)
                d = s['tx'] - s['te']
                tr = C[s['tk'], s['tx']] / C[s['tk'], s['te']] - 1
                er = I[s['tx']] / I[s['te']] - 1
                br = B[s['tx']] / B[s['te']] - 1
                yrs_ = (T - first) / 52
                hist = np.bincount(np.clip(d, 1, DUR_BINS) - 1, minlength=DUR_BINS) if len(d) else np.zeros(DUR_BINS, int)
                doc['trades'][k] = {'n': int(len(d)), 'a_year': MB._r(len(d) / yrs_, 1) if yrs_ > 0 else None,
                                    'weeks_median': float(np.median(d)) if len(d) else None, 'weeks_mean': MB._r(float(np.mean(d)), 1) if len(d) else None,
                                    'mean': MB._r(float(np.mean(tr)), 4) if len(d) else None, 'median': MB._r(float(np.median(tr)), 4) if len(d) else None,
                                    'win': MB._r(float(np.mean(tr > 0))) if len(d) else None, 'beat_ew': MB._r(float(np.mean(tr > er))) if len(d) else None,
                                    'beat_spy': MB._r(float(np.mean(tr > br))) if len(d) else None, 'excess': MB._r(float(np.mean(tr - er)), 4) if len(d) else None,
                                    'hist': [int(x) for x in hist]}
                o = s['open']
                doc['now'][k] = [[meta[i]['key'], days[int(s['since'][i])], MB._r(float(C[i, -1] / C[i, int(s['since'][i])] - 1), 4)] for i in o]
                held_keys.update(int(i) for i in o)
                log(f'  {k}: {MB._r(doc["stats"][k]["all"]["cagr"])} a year, {doc["trades"][k]["n"]} trades, {len(o)} held now')
    put('spy', b)
    put('ew', ew)
    # today's readings of every company some strategy holds: the three momentum percentiles, RS-Ratio, RS-Momentum, quadrant
    doc['companies_now'] = {'fields': ['pct_' + m[0] for m in MEASURES] + ['x', 'y', 'q'],
                            'rows': {meta[i]['key']: [MB._r(float(pct[m[0]][i, -1]), 3) if np.isfinite(pct[m[0]][i, -1]) else None for m in MEASURES]
                                     + [MB._r(float(X[i, -1]), 2) if np.isfinite(X[i, -1]) else None, MB._r(float(Y[i, -1]), 2) if np.isfinite(Y[i, -1]) else None, int(q[i, -1])]
                                     for i in sorted(held_keys)}}
    # the walk-forward record: each January the leader over the trailing window (after COST a trade), held that year
    keys = list(nets)
    E = np.vstack([nets[k] - ew for k in keys])                          # strategies × weeks, the gap to the equal weight
    H = np.vstack([nheld[k] for k in keys])                              # strategies × weeks, the companies held
    ends = [t for t in range(start, T - 1) if days[t][:4] != days[t + 1][:4]]   # each year's last week

    def ratio(w):
        sd = w.std(1, ddof=1)
        return np.where(sd > 0, w.mean(1) / np.where(sd > 0, sd, 1) * math.sqrt(52), 0.0)

    def scores(t, W):
        """The score (the lower of the information ratio over the W weeks to week t and since the start), the two
        ratios, the gap a year over the W weeks, and whether the strategy held MIN_HELD companies or more on average
        over them."""
        w = E[:, t - W + 1:t + 1]
        ir, ia = ratio(w), ratio(E[:, start:t + 1])
        ok = H[:, t - W + 1:t + 1].mean(1) >= MIN_HELD
        return np.minimum(ir, ia), ir, ia, w.mean(1) * 52, ok
    doc['walk'] = {}
    for wname, W in WINDOWS:
        recs, pick_r, avg_r, t_first = [], np.zeros(T), np.zeros(T), None
        for j, t in enumerate(ends):
            if t - W + 1 < start:
                continue
            nxt = ends[j + 1] if j + 1 < len(ends) else T - 1
            score, ir, ia, gap, ok = scores(t, W)
            if not ok.any():
                continue
            p = int(np.argmax(np.where(ok, score, -np.inf)))
            fut = E[:, t + 1:nxt + 1]
            fx = fut.sum(1)                                              # the next year's summed weekly gap (≈ a year's gap)
            if t_first is None:
                t_first = t
            pick_r[t + 1:nxt + 1] = nets[keys[p]][t + 1:nxt + 1]
            avg_r[t + 1:nxt + 1] = np.mean([nets[k][t + 1:nxt + 1] for k in keys], axis=0)
            recs.append({'year': int(days[t + 1][:4]), 'pick': keys[p], 'pick_score': MB._r(float(score[p]), 2), 'pick_ir': MB._r(float(ir[p]), 2),
                         'pick_ir_all': MB._r(float(ia[p]), 2), 'pick_gap': MB._r(float(gap[p])), 'pick_next': MB._r(float(fx[p])),
                         'avg_next': MB._r(float(np.mean(fx))), 'best': keys[int(np.argmax(fx))], 'best_next': MB._r(float(np.max(fx))),
                         'rank': int(1 + np.sum(fx > fx[p])), 'partial': nxt == T - 1 and days[nxt][5:7] != '12'})
        if t_first is None:
            continue
        s0 = t_first + 1
        me = [i for i in months_end if i >= s0]
        grow = lambda x: [MB._sig(float(v)) for v in np.cumprod(1 + x[s0:])[[i - s0 for i in me]]]   # noqa: E731
        full = [x for x in recs if not x['partial']]
        doc['walk'][wname] = {'weeks': W, 'start': days[s0], 'months': [days[i] for i in me], 'records': recs,
                              'series': {'pick': grow(pick_r), 'avg': grow(avg_r), 'ew': grow(ew), 'spy': grow(b)},
                              'summary': {'years': len(full), 'pick_mean': MB._r(float(np.mean([x['pick_next'] for x in full]))) if full else None,
                                          'avg_mean': MB._r(float(np.mean([x['avg_next'] for x in full]))) if full else None,
                                          'pick_ahead_of_avg': int(sum(x['pick_next'] > x['avg_next'] for x in full)),
                                          'pick_ahead_of_ew': int(sum(x['pick_next'] > 0 for x in full)),
                                          'median_rank': float(np.median([x['rank'] for x in full])) if full else None, 'strategies': len(keys),
                                          'min_held': MIN_HELD}}
        # today's order by the same score to the latest week: [key, score, the ratio over the window, since the start,
        # the gap a year over the window after COST, companies held on average over it, eligible]
        score, ir, ia, gap, ok = scores(T - 1, W)
        order = sorted(range(len(keys)), key=lambda i: (not ok[i], -score[i]))
        doc['walk'][wname]['fields'] = ['key', 'score', 'ir', 'ir_all', 'gap', 'held', 'eligible']
        doc['walk'][wname]['now'] = [[keys[i], MB._r(float(score[i]), 2), MB._r(float(ir[i]), 2), MB._r(float(ia[i]), 2), MB._r(float(gap[i])),
                                      MB._r(float(H[i, T - W:].mean()), 1), bool(ok[i])] for i in order]
    (Path(out_path).parent).mkdir(parents=True, exist_ok=True)
    tmp = Path(str(out_path) + '.tmp')
    tmp.write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(out_path)
    log(f'combo backtest: {len(keys)} strategies to {out_path} in {time.monotonic() - t0:.0f}s')
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', required=True, help="research-paths' working copy (public/moves/ in, public/backtest/combo.json out)")
    a = ap.parse_args()
    root = Path(a.root)
    build(root / 'public' / 'moves', root / 'public' / 'backtest' / 'combo.json')


if __name__ == '__main__':
    main()
