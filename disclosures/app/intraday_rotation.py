"""Intraday rotation and money flow (Rotation → Intraday RRG, docs/rrg-intraday.js): every five minutes through the
session (the relay .github/workflows/intraday.yml: intraday.py writes it after live.json), the five-minute bars of the
RRG's ETF universes — the sectors, the index ETFs, the styles, the industries, the countries and regions, bonds and
commodities — for the hub's intraday Relative Rotation Graph and its money-inflow screen.

  bars   today's from the Yahoo chart API (range 1d, interval 5m: the requests intraday.py made for the same symbols are
         reused) and the sessions before from range 1mo (about 21; cache/m5/<TICKER>.json, fetched once a day). Bar k of
         a session closes at 9:30 + 5k minutes (78 a day, fewer on an early close); the last price, which Yahoo sends as
         a point between two marks, closes the bar it falls in.
  grid   the five sessions before today and today to its last bar, bar by bar: each line's closes on it (a bar with no
         trade keeps the close before), as log moves from the line's first close in tenths of a basis point,
         delta-coded, and each session's opening price (o) — so the browser can leave out the gaps overnight. It
         computes the RRG against SPY with the weekly and daily charts' own formula (rrg-lab.js states: RS smoothed,
         its trend, the gap and its change, each in standard units of the sessions on the grid).
  flow   Chaikin's money flow bar by bar, as in the weekly money flows (app/flows.py): each bar's dollars (its volume ×
         its typical price, high + low + close over three) weighted by where it closed in its range,
         ((close − low) − (high − close)) / (high − low) — +1 at the high, −1 at the low. Today's bars (dollars and the
         net, in thousands) and, at the last complete bar, against the 20 sessions before at the same bar:
           share   the net as a share of the dollars traded today (and over the last 30 and 60 minutes)
           rvol    today's dollars against the median of those sessions' by the same bar (relative volume)
           rank    the share of those sessions whose inflow share by that bar was below today's; z, how many standard
                   deviations today's stands from their mean
         US markets publish no large-order figures: the flow is an estimate from the bars, not a count of buyers.

rotation.json (schema intraday-rotation.v1) is published with live.json on the branch intraday-live.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import statistics
from pathlib import Path
from zoneinfo import ZoneInfo

import moves as M
import paths as P
import rotation_history as RH

SCHEMA = 'intraday-rotation.v1'
ET, UTC = ZoneInfo('America/New_York'), dt.timezone.utc
BENCH = 'SPY'
PRIOR = 5                     # sessions before today on the RRG's grid (its trend and its standard units)
NORM, MIN_NORM = 20, 10       # sessions behind the relative volume and the inflow rank (at least)
KEEP = 30                     # sessions kept in the cache
Q = 1e5                       # closes as log moves in tenths of a basis point
# the RRG's universes (docs/rrg.js and rrg-lab.js RRGL_UNI), in its order; the page takes them from the file
GROUPS = [
    ('sectors', 'Sector ETFs (SPDR)', [t for t, _, _ in RH.SECTOR_ETFS]),
    ('idxetf', 'Index ETFs (QQQ · DIA · IWM · MDY · IJR · RSP)', ['QQQ', 'DIA', 'IWM', 'MDY', 'IJR', 'RSP']),
    ('styles', 'Style, size and asset ETFs', [t for t, _ in RH.STYLE_ETFS]),
    ('indcyc', 'Industry ETFs · cyclical', ['KBE', 'KRE', 'XHB', 'ITB', 'XRT', 'XOP', 'OIH', 'XME', 'ITA', 'IYT', 'JETS', 'VNQ']),
    ('indgro', 'Industry ETFs · growth and themes', ['IGV', 'SMH', 'IBB', 'XBI', 'ARKK', 'TAN', 'ICLN', 'URA']),
    ('countries', 'Countries (ETFs in dollars)', ['EWJ', 'FXI', 'MCHI', 'KWEB', 'EWZ', 'INDA', 'EWG', 'EWU', 'EWC', 'EWA', 'EWT', 'EWY', 'EWW', 'EWH']),
    ('regions', 'World regions (ETFs in dollars)', ['VTI', 'ACWI', 'VEA', 'EFA', 'VWO', 'EEM']),
    ('bonds', 'Bonds (Treasuries, credit, inflation-linked)', ['SHY', 'IEF', 'TLT', 'TIP', 'AGG', 'LQD', 'HYG', 'EMB', 'MUB']),
    ('commod', 'Commodities and gold miners', ['GLD', 'SLV', 'USO', 'UNG', 'DBC', 'DBA', 'GDX']),
]


def tickers():
    """SPY first, then every line of every group once."""
    out = [BENCH]
    for _, _, ts in GROUPS:
        out += [t for t in ts if t not in out]
    return out


def names():
    n = {t: f'{nm} sector' for t, _, nm in RH.SECTOR_ETFS}
    n.update({t: nm for t, nm in RH.STYLE_ETFS})
    n.update({t: nm for t, nm, _ in P.MOVES_MORE_ETFS})
    n.update({t: re.sub(r'\s*\([A-Z]+\)$', '', nm) for t, nm in M.MARKET.items()})
    return n


def _r(v, d=4):
    return None if v is None or not math.isfinite(v) else round(float(v), d)


# ------------------------------------------------------------------ bars
def bars_of(res):
    """A Yahoo five-minute chart → {ET date: {k: [high, low, close, volume]}}, bar k closing at 9:30 + 5k minutes; a
    point between two marks (the last price) closes the bar it falls in, and 4 pm's closes the last bar."""
    ts = res.get('timestamp') or []
    q = ((res.get('indicators') or {}).get('quote') or [{}])[0]
    col = {f: q.get(f) or [None] * len(ts) for f in ('high', 'low', 'close', 'volume')}
    out = {}
    for i, t in enumerate(ts):
        c = col['close'][i]
        if c is None or not c > 0:
            continue
        e = dt.datetime.fromtimestamp(int(t), UTC).astimezone(ET)
        m = (e.hour - 9) * 60 + e.minute - 30
        if not 0 <= m <= 390:
            continue
        k = min(m // 5 + 1, 78)
        hi, lo, vo = col['high'][i], col['low'][i], col['volume'][i]
        hi = float(hi) if hi and hi > 0 else float(c)
        lo = float(lo) if lo and lo > 0 else float(c)
        vo = float(vo) if vo and vo > 0 else 0.0
        day = out.setdefault(e.date().isoformat(), {})
        if k in day:
            b = day[k]
            day[k] = [max(b[0], hi), min(b[1], lo), float(c), b[3] + vo]
        else:
            day[k] = [hi, lo, float(c), vo]
    return out


def opens_of(res):
    """{ET date: the session's opening price (its first five-minute bar's open)}."""
    ts = res.get('timestamp') or []
    q = ((res.get('indicators') or {}).get('quote') or [{}])[0]
    op = q.get('open') or [None] * len(ts)
    out = {}
    for i, t in enumerate(ts):
        e = dt.datetime.fromtimestamp(int(t), UTC).astimezone(ET)
        if (e.hour, e.minute) == (9, 30) and op[i] and op[i] > 0:
            out[e.date().isoformat()] = float(op[i])
    return out


def history(h, cache, t, ysym, today, chart, fetch=True):
    """The sessions before today, bar by bar, and their opening prices: (days, opens), from the cache when it was
    fetched today, else Yahoo's last month."""
    p = Path(cache) / f'{t}.json'
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
        if 'opens' not in doc:
            doc = None                                                 # an older cache: fetched again
    except (OSError, ValueError):
        doc = None
    unpack = lambda d: ({day: {int(k): b for k, b in bars.items()} for day, bars in (d.get('days') or {}).items()}, dict(d.get('opens') or {}))
    if doc and (doc.get('refreshed') == today or not fetch):
        return unpack(doc)
    if not fetch:
        return {}, {}
    try:
        res = chart(h, ysym, '1mo', '5m')
    except Exception:                                                  # noqa: BLE001 — yesterday's serves; the next scan tries again
        if doc:
            return unpack(doc)
        raise
    old, oo = unpack(doc) if doc else ({}, {})
    rd = lambda b: [round(x, 4) for x in b[:3]] + [round(b[3])]       # as kept: the next scans read the same numbers
    old.update({d: {k: rd(b) for k, b in bars.items()} for d, bars in bars_of(res).items() if d < today})   # today's comes with every scan
    oo.update({d: round(o, 4) for d, o in opens_of(res).items() if d < today})
    days = {d: old[d] for d in sorted(old)[-KEEP:]}
    opens = {d: oo[d] for d in days if d in oo}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'ticker': t, 'symbol': ysym, 'refreshed': today, 'opens': opens,
                             'days': {d: {str(k): b for k, b in sorted(bars.items())} for d, bars in days.items()}},
                            separators=(',', ':')), encoding='utf-8')
    return days, opens


# ------------------------------------------------------------------ the grid and the flow
def on_grid(days, slots, bars_by_day):
    """The closes bar by bar on the grid; a bar with no trade keeps the close before; the line's first bars missing:
    its first close. None when it has no bar at all."""
    out, last = [], None
    for d, n in zip(days, slots):
        bars = bars_by_day.get(d) or {}
        for k in range(1, n + 1):
            b = bars.get(k)
            if b:
                last = b[2]
            out.append(last)
    first = next((c for c in out if c is not None), None)
    if first is None:
        return None
    return [first if c is None else c for c in out]


def code(closes):
    """(first close, [0, Δq …]): q = round(1e5 × ln(close / first)), tenths of a basis point, no drift in the coding."""
    c0 = closes[0]
    q = [round(Q * math.log(c / c0)) for c in closes]
    return c0, [0] + [b - a for a, b in zip(q, q[1:])]


def decode(c0, d):
    out, q = [], 0
    for x in d:
        q += x
        out.append(c0 * math.exp(q / Q))
    return out


def flows(bars, k_last):
    """Bar by bar to bar k_last: (dollars, the net that flowed in) — Chaikin: the bar's dollars × where it closed in its
    range, +1 at the high, −1 at the low; a bar with no trade 0."""
    dv, nf = [], []
    for k in range(1, k_last + 1):
        b = bars.get(k)
        if not b or not b[3] > 0:
            dv.append(0.0)
            nf.append(0.0)
            continue
        hi, lo, c, v = b
        d = v * (hi + lo + c) / 3
        dv.append(d)
        nf.append(d * ((c - lo) - (hi - c)) / (hi - lo) if hi > lo else 0.0)
    return dv, nf


def share(dv, nf):
    s = sum(dv)
    return sum(nf) / s if s > 0 else None


def norms(hist, before, k):
    """The NORM sessions before `before` that reach bar k: their dollars by bar k and their inflow share by bar k."""
    cum, shares = [], []
    for d in sorted(x for x in hist if x < before)[-NORM:]:
        bars = hist[d]
        if not bars or max(bars) < k:
            continue                                                   # an early close: no bar k
        dv, nf = flows(bars, k)
        s = sum(dv)
        if s > 0:
            cum.append(s)
            shares.append(sum(nf) / s)
    return cum, shares


def reading(today_bars, k, hist, before):
    """The flow at bar k against the sessions before."""
    dv, nf = flows(today_bars, k)
    out = {'k': k, 'dv': _r(sum(dv), 0), 'net': _r(sum(nf), 0), 'share': _r(share(dv, nf)),
           'm30': _r(share(dv[-6:], nf[-6:])), 'h1': _r(share(dv[-12:], nf[-12:]))}
    vw = [(b[0] + b[1] + b[2]) / 3 * b[3] for kk, b in today_bars.items() if kk <= k and b[3] > 0]
    vo = sum(b[3] for kk, b in today_bars.items() if kk <= k and b[3] > 0)
    out['vwap'] = _r(sum(vw) / vo) if vo > 0 else None
    cum, shares = norms(hist, before, k)
    out['n'] = len(shares)
    if len(cum) >= MIN_NORM:
        med = statistics.median(cum)
        out['rvol'] = _r(sum(dv) / med, 3) if med > 0 else None
    sh = out['share']
    if sh is not None and len(shares) >= MIN_NORM:
        out['rank'] = _r((sum(1 for s in shares if s < sh) + 0.5 * sum(1 for s in shares if s == sh)) / len(shares), 3)
        sd = statistics.stdev(shares)
        out['z'] = _r((sh - statistics.fmean(shares)) / sd, 2) if sd > 0 else None
    return out


# ------------------------------------------------------------------ the file
def build(h, cache, chart, now=None, fetch_history=True, log=print):
    """rotation.json: every line's closes on the grid, today's flow bar by bar and its reading at the last full bar."""
    now = now or dt.datetime.now(UTC)
    today = now.astimezone(ET).date().isoformat()
    nm = names()
    raw = {}
    for t in tickers():
        try:
            raw[t] = chart(h, t, '1d', '5m')
        except Exception as exc:                                       # noqa: BLE001 — one line's failure never stops the rest
            log(f'rotation {t}: {str(exc)[:120]}')
    if BENCH not in raw:
        raise RuntimeError('no bars for SPY')
    tb = {t: bars_of(r) for t, r in raw.items()}
    if not tb[BENCH]:
        raise RuntimeError("no bars for SPY's session")
    sday = max(tb[BENCH])                                              # the session shown: today's, or the last one before the open
    K = max(tb[BENCH][sday])
    meta = raw[BENCH].get('meta') or {}
    reg = (meta.get('currentTradingPeriod') or {}).get('regular') or {}
    is_open = bool(reg.get('start') and reg.get('end') and reg['start'] <= now.timestamp() < reg['end'] and sday == today)
    end_k = dt.datetime.fromisoformat(f'{sday}T09:30').replace(tzinfo=ET) + dt.timedelta(minutes=5 * K)
    kf = K - 1 if is_open and now < end_k and K > 1 else K           # the bar still forming is read at the next scan
    hist, opens = {}, {}
    for t in raw:
        try:
            hist[t], opens[t] = history(h, cache, t, t, today, chart, fetch=fetch_history)
        except Exception as exc:                                       # noqa: BLE001
            log(f'rotation {t} history: {str(exc)[:120]}')
            hist[t], opens[t] = {}, {}
        opens[t].update(opens_of(raw[t]))
    hb = hist.get(BENCH) or {}
    prior = sorted(d for d in hb if d < sday)[-PRIOR:]
    days = prior + [sday]
    slots = [max(hb[d]) for d in prior] + [K]
    doc = {'schema': SCHEMA, 'generated_at': now.isoformat(timespec='seconds'), 'bench': BENCH, 'bar': 5,
           'source': 'Yahoo Finance chart API, five-minute bars (prices as published; some may be delayed)',
           'session': {'date': sday, 'open': is_open, 'k': K, 'kf': kf, 'short': (not is_open) and K < 78,
                       'last': (dt.datetime(2000, 1, 1, 9, 30) + dt.timedelta(minutes=5 * K)).strftime('%H:%M')},
           'days': days, 'slots': slots,
           'groups': [[g, label, [t for t in ts if t in raw]] for g, label, ts in GROUPS],
           'assets': {}}
    for t, r in raw.items():
        by = dict(hist.get(t) or {})
        by[sday] = tb[t].get(sday) or {}
        closes = on_grid(days, slots, by)
        if not closes or not by[sday]:
            log(f'rotation {t}: no bars for the session')
            continue
        m = r.get('meta') or {}
        c0, d = code(closes)
        dv, nf = flows(by[sday], K)
        a = {'name': nm.get(t, t), 'price': _r(m.get('regularMarketPrice') or closes[-1]), 'prev': _r(m.get('previousClose') or m.get('chartPreviousClose')),
             'c0': _r(c0, 6), 'c': d, 'o': [_r(opens[t].get(day)) for day in days],
             'dv': [round(x / 1e3) for x in dv], 'nf': [round(x / 1e3) for x in nf],
             'now': reading(by[sday], kf, hist.get(t) or {}, sday)}
        doc['assets'][t] = a
    return doc


def write(doc, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / 'rotation.json.tmp'
    tmp.write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(out / 'rotation.json')
