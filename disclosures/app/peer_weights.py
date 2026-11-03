"""Weighted peer multiples for the Fair value page (app/valuation.py): the peers' multiples weighted by how big and how
traded each peer is and by how recent each quarter is, so that small, thinly traded peers and old quarters move the
result less than in the plain median (valuation.peer_range: every peer counted alike, and only today's multiple).

  size weight   each peer's share of the group's market value, of its revenue and of its trading value (the median
                daily close × volume over the last 63 sessions), combined as their geometric mean (a measure a peer
                lacks is left out of its mean; a measure most peers lack is left out for all), renormalized and capped
                at CAP (20%), the excess shared out among the rest — so a giant weighs most but is never the whole answer.
  time weight   a peer's multiple today and at every quarter since mid-2022 (60 days after the quarter ends, the outside
                view's origins), each weighted 0.5 ^ (age ÷ HALF_LIFE) with a one-year half-life and renormalized within
                the peer: the last year carries about half of its weight, three years ago an eighth as much as today.
                A multiple with no quarterly history (EV/EBITDA, P/FFO) counts today only.
  observation   weight = its peer's size weight × its time weight within the peer.
  result        the weighted 25th, 50th and 75th percentiles (linear between the observations' weight midpoints, so
                equal weights give the plain percentiles); the effective number of peers 1 ÷ Σ w² (how many equal
                peers the weights amount to); the largest weights; and the median under each weight alone (market
                value, revenue, trading value, time) beside the plain one.
"""
from __future__ import annotations

import math

HALF_LIFE = 1.0          # years: a peer's multiple a year ago counts half as much as today's
MAX_AGE = 5.0            # years of quarters kept
CAP = 0.20               # no peer above 20% of the weight
DVOL_DAYS = 63           # sessions of close × volume for the trading value
PARTS = (('mcap', 'market value'), ('revenue', 'revenue'), ('dvol', 'trading value'))
LABEL = {'equal': 'every peer alike, today only (the plain median)', 'mcap': 'by market value', 'revenue': 'by revenue', 'dvol': 'by trading value',
         'time': 'by recency only (quarters since 2022, half-life one year)', 'all': 'market value × revenue × trading value, and recency'}


def fin(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def wquantile(vals, ws, q):
    """The weighted q-quantile (0..1): linear between the points at each observation's weight midpoint, rescaled so the
    lowest sits at 0 and the highest at 1 (equal weights give the plain linear percentile)."""
    pairs = sorted((v, w) for v, w in zip(vals, ws) if fin(v) and fin(w) and w > 0)
    if not pairs:
        return None
    if len(pairs) == 1:
        return pairs[0][0]
    tot = sum(w for _, w in pairs)
    w0, wl = pairs[0][1], pairs[-1][1]
    span = tot - (w0 + wl) / 2
    pos, c = [], 0.0
    for v, w in pairs:
        pos.append((c + w / 2 - w0 / 2) / span)
        c += w
    if q <= 0:
        return pairs[0][0]
    if q >= 1:
        return pairs[-1][0]
    for i in range(1, len(pairs)):
        if pos[i] >= q:
            a, b = pos[i - 1], pos[i]
            t = (q - a) / (b - a) if b > a else 0.0
            return pairs[i - 1][0] + t * (pairs[i][0] - pairs[i - 1][0])
    return pairs[-1][0]


def cap_weights(w, cap=CAP):
    """Weights summing to 1 with none above cap, the excess shared out among the rest in proportion (when the cap can
    hold: n × cap ≥ 1)."""
    tot = sum(w.values())
    if not tot:
        return w
    w = {k: v / tot for k, v in w.items()}
    if len(w) * cap < 1:
        return w
    fixed = set()
    for _ in range(len(w)):
        over = [k for k, v in w.items() if v > cap + 1e-12 and k not in fixed]
        if not over:
            break
        fixed |= set(over)
        free = [k for k in w if k not in fixed]
        rest = 1 - cap * len(fixed)
        ft = sum(w[k] for k in free)
        w = {k: (cap if k in fixed else (w[k] / ft * rest if ft else rest / max(1, len(free)))) for k in w}
    return w


def size_weights(ciks, info, parts=('mcap', 'revenue', 'dvol'), cap=CAP):
    """{cik: weight} from the peers' shares of each size measure (geometric mean, capped), and the measures used."""
    shares, used = {}, []
    for k in parts:
        vals = {c: (info.get(c) or {}).get(k) for c in ciks}
        vals = {c: v for c, v in vals.items() if fin(v) and v > 0}
        if len(vals) < max(2, (len(ciks) + 1) // 2):
            continue                                        # most peers lack it: left out for all
        tot = sum(vals.values())
        shares[k] = {c: v / tot for c, v in vals.items()}
        used.append(k)
    if not shares:
        return {c: 1 / len(ciks) for c in ciks}, []
    w = {}
    for c in ciks:
        xs = [shares[k][c] for k in used if c in shares[k]]
        w[c] = math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else None
    have = [v for v in w.values() if v]
    floor = min(have) if have else 1.0
    w = {c: (v if v else floor) for c, v in w.items()}     # a peer with none of the measures: the smallest weight
    return cap_weights(w, cap), used


def observations(ciks, cur, hist, sw, use_time=True):
    """(values, weights): each peer's multiple today (and, with use_time, at each past quarter), its size weight spread
    over them by recency."""
    vals, ws = [], []
    for c in ciks:
        obs = [(cur[c], 0.0)] if fin(cur.get(c)) else []
        if use_time:
            obs += [(v, a) for v, a in (hist.get(c) or []) if fin(v) and fin(a) and 0 < a <= MAX_AGE]
        if not obs:
            continue
        t = [0.5 ** (a / HALF_LIFE) for _, a in obs]
        tt = sum(t)
        for (v, _), x in zip(obs, t):
            vals.append(v)
            ws.append(sw.get(c, 0) * x / tt)
    return vals, ws


def weighted(ciks, cur, hist, info, ticker_of=None):
    """The weighted peer multiple for the peers ciks: {p25, p50, p75, n, n_obs, n_eff, top, parts, by, …} or None."""
    ciks = [c for c in ciks if fin(cur.get(c))]
    if len(ciks) < 2:
        return None
    hist = hist or {}
    sw, used = size_weights(ciks, info)
    vals, ws = observations(ciks, cur, hist, sw, True)
    if not vals:
        return None
    timed = any(hist.get(c) for c in ciks)
    out = {'p25': wquantile(vals, ws, 0.25), 'p50': wquantile(vals, ws, 0.5), 'p75': wquantile(vals, ws, 0.75), 'n': len(ciks), 'n_obs': len(vals),
           'n_eff': 1 / sum(v * v for v in sw.values()), 'parts': used, 'timed': timed, 'half_life': HALF_LIFE, 'cap': CAP,
           'top': [[(ticker_of or {}).get(c, c), round(w, 4)] for c, w in sorted(sw.items(), key=lambda kv: -kv[1])[:5]]}
    eq = {c: 1 / len(ciks) for c in ciks}
    by = {'equal': wquantile(*observations(ciks, cur, {}, eq, False), 0.5)}
    for k in ('mcap', 'revenue', 'dvol'):
        s, u = size_weights(ciks, info, parts=(k,))
        by[k] = wquantile(*observations(ciks, cur, {}, s, False), 0.5) if u else None
    by['time'] = wquantile(*observations(ciks, cur, hist, eq, True), 0.5) if timed else None
    out['by'] = by
    return out


def dollar_volume(rows, days=DVOL_DAYS):
    """The median close × volume over the last `days` rows [date, close, volume] (None without volumes)."""
    xs = sorted(r[1] * r[2] for r in rows[-days:] if len(r) > 2 and fin(r[1]) and fin(r[2]) and r[1] > 0 and r[2] > 0)
    if len(xs) < days // 3:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def note(w, plain, label='peers'):
    """One line for the football field."""
    parts = ', '.join(dict(PARTS)[k] for k in w.get('parts') or []) or 'equal size'
    t = '; quarters since 2022 fading by half each year' if w.get('timed') else '; today only (no quarterly history)'
    return (f"{w['n']} {label} weighted by {parts}{t}: median {w['p50']:.1f}x"
            + (f' (plain {plain:.1f}x)' if fin(plain) else '') + f", middle half {w['p25']:.1f}–{w['p75']:.1f}x; {w['n_eff']:.1f} effective peers")
