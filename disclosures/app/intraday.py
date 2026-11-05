"""Move odds, intraday: the market's and the sectors' move so far today, against their own history at the same time
of day, and what followed — to the close and over the next days.

Every five minutes through the US session (the relay .github/workflows/intraday.yml) the Yahoo Finance chart API is read
for each asset of the hub's "Market & sectors" (the indices, the market ETFs, the sectors, the styles): today's
five-minute bars and the last price. Its history at each time of day comes from the hourly bars of the last two years
(range 730d, interval 60m; cache/h60/<KEY>.json, refreshed once a day): for every full session, the price at the open
and at 10:30, 11:30 … 15:30 and 4 pm as a move from the previous session's 4 pm price. Now is read at the nearest of
those marks:

  so far       the move from the previous close, its percentile among every day's move by that time (mid-ranks), how
               often one this far comes (1 in N days), and the distribution of the move by that time (fixed bands)
  similar      the 60 days whose move by that time was nearest: from that time to the close (quantiles, and ten bands
               of a round size near half its usual spread; the share that closed above that price; the share that
               closed above the previous close), the close it points to, the path to the close mark by mark (a fan), and
               the next day, 5 days and 21 days after such days
  base         the same for every day, for comparison
  VWAP         today's VWAP after each five-minute bar (the typical price weighted by volume) and the price against it;
               every day's gap to its VWAP at that mark (from the hourly bars: highs, lows, closes, volumes), the 60 days
               nearest to today's gap — the share that closed above their VWAP, that came back to it before the close,
               the move to the close, the next days — and, for ten bands of the gap, the share above VWAP at the close
               and the share that came back (the probability chart); an asset with no volume (some indices) has none

Each asset says whether its reading is from today's session (`today`: before the open Yahoo still shows the last
close); `session.short` marks an early close, when the odds to 4 pm don't apply.

live.json (schema intraday.v1) is force-pushed to the branch intraday-live, one commit, each scan (the history cache
stays in the Actions cache under a key a day); the hub reads it from raw.githubusercontent.com (docs/intraday-view.js).
Prices as Yahoo publishes them (some may be delayed); the time of each is in the file. History, not a forecast.

    python app/intraday.py --out OUT [--cache DIR]   one scan: OUT/live.json; the history in DIR (default OUT/cache/h60/)
    python app/intraday.py --session                 exit 0 while the regular session is open or opens within 20 minutes
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import consensus as CS
import moves as M
import paths as P
import rotation_history as RH

SCHEMA = 'intraday.v1'
ET, UTC = ZoneInfo('America/New_York'), dt.timezone.utc
MARKS = ('09:30', '10:30', '11:30', '12:30', '13:30', '14:30', '15:30', '16:00')   # the open, each hourly bar's close, 4 pm
K_SIMILAR, MIN_DAYS = 60, 120
EDGES = [-0.03, -0.025, -0.02, -0.015, -0.01, -0.005, 0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03]
QS = (0.1, 0.25, 0.5, 0.75, 0.9)
NEXT = (1, 5, 21)


def assets():
    """[(key, Yahoo symbol, name, kind)] — the hub's Market & sectors, in its order."""
    out, seen = [], set()
    for t in list(M.INDEX_NAMES) + list(M.MARKET) + [x for x, _, _ in RH.SECTOR_ETFS] + [x for x, _ in RH.STYLE_ETFS]:
        if t in seen:
            continue
        seen.add(t)
        kind = 'index' if t in M.INDEX_NAMES else 'market' if t in M.MARKET else 'sector' if t in M.SECTOR_NAME else 'style'
        name = M.MARKET.get(t) or M.INDEX_NAMES.get(t) or (M.SECTOR_NAME.get(t) and f'{M.SECTOR_NAME[t]} sector ({t})') or f'{M.STYLE_NAME.get(t, t)} ({t})'
        out.append((t, P.YAHOO_SYMBOL.get(t, t), name, kind))
    return out


def _r(v, d=5):
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def et_of(ts):
    return dt.datetime.fromtimestamp(int(ts), UTC).astimezone(ET)


# ------------------------------------------------------------------ the Yahoo chart API (as app/ladders.py reads it)
def chart(h, sym, rng, interval):
    d = h.json(f'{CS.YQ}/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval={interval}&includePrePost=false')
    res = ((d or {}).get('chart') or {}).get('result') or []
    if not res:
        raise RuntimeError(f'no chart for {sym}')
    return res[0]


def sessions(res):
    """Hourly bars → {ET date: {p: [open, the close of each bar from 9:30 to 15:30], h, l, v: each bar's high, low and
    volume}} for full sessions only (seven bars)."""
    ts = res.get('timestamp') or []
    q = ((res.get('indicators') or {}).get('quote') or [{}])[0]
    col = {f: q.get(f) or [None] * len(ts) for f in ('open', 'high', 'low', 'close', 'volume')}
    by = {}
    for i, t in enumerate(ts):
        e = et_of(t)
        c = col['close'][i]
        if c is None or not (c > 0):
            continue
        by.setdefault(e.date().isoformat(), {})[e.strftime('%H:%M')] = tuple(col[f][i] for f in ('open', 'high', 'low', 'close', 'volume'))
    out = {}
    starts = list(MARKS[:-1])
    for d, bars in by.items():
        if not all(s in bars for s in starts):
            continue                                                  # a half day or a gap: left out
        o = bars['09:30'][0]
        if o is None or not (o > 0):
            continue
        B = [bars[s] for s in starts]
        out[d] = {'p': [float(o)] + [float(b[3]) for b in B],
                  'h': [float(b[1]) if b[1] and b[1] > 0 else float(b[3]) for b in B],
                  'l': [float(b[2]) if b[2] and b[2] > 0 else float(b[3]) for b in B],
                  'v': [float(b[4]) if b[4] and b[4] > 0 else 0.0 for b in B]}
    return out


def vwap_of(h, l, c, v):
    """The VWAP after each bar (the typical price, high + low + close over three, weighted by volume); None with no volume."""
    pv = vol = 0.0
    out = []
    for hi, lo, cl, vo in zip(h, l, c, v):
        pv += (hi + lo + cl) / 3 * vo
        vol += vo
        out.append(pv / vol if vol > 0 else None)
    return out


def history_of(sess, today=None):
    """{days, marks: days × 8 moves from the previous 4 pm, close: the 4 pm prices, vw: the VWAP at 10:30 … 4 pm, hi, lo:
    each hourly bar's high and low (all as moves from the previous 4 pm; vw None for an asset with no volume)} from full
    sessions before today."""
    days = sorted(d for d in sess if today is None or d < today)
    out = {'days': [], 'marks': [], 'close': [], 'vw': [], 'hi': [], 'lo': []}
    prev = None
    for d in days:
        v = sess[d]
        if prev is not None:
            mv = lambda xs: [x / prev - 1 for x in xs]
            vw = vwap_of(v['h'], v['l'], v['p'][1:], v['v'])
            out['days'].append(d)
            out['marks'].append(mv(v['p']))
            out['close'].append(v['p'][-1])
            out['vw'].append(None if any(x is None for x in vw) else mv(vw))
            out['hi'].append(mv(v['h']))
            out['lo'].append(mv(v['l']))
        prev = v['p'][-1]
    return out


def load_history(h, cache, key, ysym, today, fetch=True):
    """The asset's hourly history, from the cache when it was refreshed today, else from Yahoo (730 days of 60m bars)."""
    p = Path(cache) / f'{key}.json'
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
        if doc.get('refreshed') == today or not fetch:
            return doc
    except (OSError, ValueError):
        doc = None
    if not fetch:
        return doc
    try:
        try:
            res = chart(h, ysym, '730d', '60m')
        except RuntimeError:
            res = chart(h, ysym, '60d', '60m')
    except Exception:                                                  # noqa: BLE001
        if doc:
            return doc                                                 # the last day's history serves; the next scan tries again
        raise
    hist = history_of(sessions(res), today)
    old = {}
    if doc:
        cols = doc.get('cols') or [[]]
        for i, d in enumerate(cols[0]):
            old[d] = tuple(cols[c][i] if c < len(cols) else None for c in range(1, 6))
    rd = lambda xs, n=5: None if xs is None else [round(x, n) for x in xs]
    for i, d in enumerate(hist['days']):
        old[d] = (rd(hist['marks'][i], 6), round(hist['close'][i], 4), rd(hist['vw'][i]), rd(hist['hi'][i]), rd(hist['lo'][i]))
    days = sorted(old)
    doc = {'key': key, 'symbol': ysym, 'refreshed': today, 'marks': list(MARKS), 'fields': ['day', 'marks', 'close', 'vw', 'hi', 'lo'],
           'cols': [days] + [[old[d][c] for d in days] for c in range(5)]}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    return doc


def today_of(res):
    """Today's five-minute bars and the last price: (price, time, previous close, [[minutes after 9:30, price]], hi, lo, session)."""
    meta = res.get('meta') or {}
    ts = res.get('timestamp') or []
    q = ((res.get('indicators') or {}).get('quote') or [{}])[0]
    col = {f: q.get(f) or [None] * len(ts) for f in ('high', 'low', 'close', 'volume')}
    path, vbars = [], []
    for i, t in enumerate(ts):
        c = col['close'][i]
        if c is None or not (c > 0):
            continue
        e = et_of(t)
        mins = (e.hour - 9) * 60 + e.minute - 30 + 5                   # a bar's close: its start + 5 minutes
        if 0 < mins <= 390:
            path.append([mins, float(c)])
            hi, lo, vo = col['high'][i], col['low'][i], col['volume'][i]
            vbars.append((mins, float(hi) if hi and hi > 0 else float(c), float(lo) if lo and lo > 0 else float(c), float(c), float(vo) if vo and vo > 0 else 0.0))
    vw = vwap_of([b[1] for b in vbars], [b[2] for b in vbars], [b[3] for b in vbars], [b[4] for b in vbars])
    vpath = [[b[0], x] for b, x in zip(vbars, vw) if x is not None]
    price = meta.get('regularMarketPrice') or (path[-1][1] if path else None)
    prev = meta.get('previousClose') or meta.get('chartPreviousClose')
    reg = ((meta.get('currentTradingPeriod') or {}).get('regular')) or {}
    return {'price': float(price) if price else None, 'time': int(meta['regularMarketTime']) if meta.get('regularMarketTime') else None,
            'prev': float(prev) if prev else None, 'path': path, 'vwap_path': vpath, 'start': reg.get('start'), 'end': reg.get('end')}


# ------------------------------------------------------------------ the odds
def q_(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    return {f'p{round(100 * p)}': _r(np.quantile(x, p)) for p in QS} | {'n': int(len(x)), 'up': _r((x > 0).mean(), 3)}


def rest_edges(spread):
    """Ten bands for the move from now to the close: steps of a round size near half its spread, ±4 steps."""
    if not (spread > 0):
        return None
    steps = np.array([0.0005, 0.001, 0.0025, 0.005, 0.01, 0.02])
    s = float(steps[np.argmin(np.abs(np.log(steps / (spread / 2))))])
    return [round(s * i, 6) for i in range(-4, 5)]


def nearest_mark(minutes):
    """The index of the mark nearest to `minutes` after 9:30 (0 = the open … 7 = 4 pm)."""
    at = [0, 60, 120, 180, 240, 300, 360, 390]
    return int(np.argmin([abs(minutes - a) for a in at]))


def analyse(hist, move, j, price, k=K_SIMILAR):
    """The odds at mark j for a move so far of `move` (module docstring)."""
    days, Mx, C = hist['cols'][0], np.asarray(hist['cols'][1], float), np.asarray(hist['cols'][2], float)
    if len(days) < MIN_DAYS or not np.isfinite(move):
        return None
    m = Mx[:, j]
    ok = np.isfinite(m)
    n = int(ok.sum())
    below, same = int((m[ok] < move).sum()), int((m[ok] == move).sum())
    pct = 100.0 * (below + 0.5 * same) / n
    tail = (m[ok] <= move).mean() if move < np.median(m[ok]) else (m[ok] >= move).mean()
    rest = (1 + Mx[:, 7]) / (1 + m) - 1
    nxt = {s: np.array([C[i + s] / C[i] - 1 if i + s < len(C) else np.nan for i in range(len(C))]) for s in NEXT}
    idx = np.nonzero(ok)[0]
    sim = idx[np.argsort(np.abs(m[idx] - move), kind='mergesort')[:k]]
    fin_rest = rest[idx][np.isfinite(rest[idx])]
    edges = rest_edges(float(np.std(fin_rest))) if j < 7 and len(fin_rest) else None

    def block(sel, with_fan):
        r = rest[sel]
        b = {'n': int(len(sel)), 'rest': q_(r), 'above': _r((r > 0).mean(), 3), 'green': _r((Mx[sel, 7] > 0).mean(), 3),
             'next': {str(s): q_(nxt[s][sel]) for s in NEXT}}
        if edges:
            rr = r[np.isfinite(r)]
            b['rest_dist'] = np.bincount(np.searchsorted(np.asarray(edges), rr, side='right'), minlength=len(edges) + 1).tolist()
        if with_fan:
            b['fan'] = [[kk, *[_r(np.nanquantile((1 + Mx[sel, kk]) / (1 + m[sel]) - 1, p)) for p in QS]] for kk in range(j, 8)]
            qr = b['rest']
            b['close'] = [_r(price * (1 + qr[f'p{round(100 * p)}']), 4) for p in (0.1, 0.5, 0.9)] if qr and price else None
            b['moves_by_then'] = [_r(float(m[sel].min())), _r(float(m[sel].max()))]
        return b
    hist_counts = np.bincount(np.searchsorted(np.asarray(EDGES), m[ok], side='right'), minlength=len(EDGES) + 1).tolist()
    return {'mark': MARKS[j], 'j': j, 'days': n, 'from': days[0], 'pct': _r(pct, 1), 'every': _r(1 / tail, 1) if tail > 0 else None,
            'dist': hist_counts, 'rest_edges': edges, 'similar': block(sim, True), 'base': block(idx, False)}


def vwap_odds(hist, gap, j, k=K_SIMILAR):
    """Price against VWAP at mark j (1 = 10:30 … 7 = 4 pm), today's `gap` (price / VWAP - 1): its rank among every
    day's gap by then; the 60 days nearest to it and every day — the close against that day's VWAP (the share above),
    a return to VWAP before the close (a later hourly bar's range held its VWAP, or the gap changed sign at a later
    mark), the move to the close, the next days; and, for each of ten bands of the gap, the share that closed above
    VWAP, the share that came back to it and the median move to the close (the probability chart)."""
    cols = hist.get('cols') or []
    if j < 1 or len(cols) < 6 or not np.isfinite(gap):
        return None
    pad = lambda rows: np.array([r if r else [np.nan] * 7 for r in rows], float)
    days, Mx, C, VW, HI, LO = cols[0], np.asarray(cols[1], float), np.asarray(cols[2], float), pad(cols[3]), pad(cols[4]), pad(cols[5])
    g = (1 + Mx[:, j]) / (1 + VW[:, j - 1]) - 1
    end = (1 + Mx[:, 7]) / (1 + VW[:, 6]) - 1
    idx = np.nonzero(np.isfinite(g) & np.isfinite(end))[0]
    if len(idx) < MIN_DAYS:
        return None
    rest = (1 + Mx[:, 7]) / (1 + Mx[:, j]) - 1
    back = np.zeros(len(g), bool)
    for b in range(j, 7):                                              # the hourly bars after mark j
        gb = (1 + Mx[:, b + 1]) / (1 + VW[:, b]) - 1
        back |= np.isfinite(gb) & (np.sign(gb) * np.sign(g) < 0)
        back |= np.isfinite(LO[:, b]) & np.isfinite(HI[:, b]) & (LO[:, b] <= VW[:, b]) & (VW[:, b] <= HI[:, b])
    nxt = {s: np.array([C[i + s] / C[i] - 1 if i + s < len(C) else np.nan for i in range(len(C))]) for s in NEXT}
    sim = idx[np.argsort(np.abs(g[idx] - gap), kind='mergesort')[:k]]

    def block(sel):
        b = {'n': int(len(sel)), 'above': _r((end[sel] > 0).mean(), 3), 'end': q_(end[sel]), 'next': {str(s): q_(nxt[s][sel]) for s in NEXT}}
        if j < 7:
            b |= {'back': _r(back[sel].mean(), 3), 'rest': q_(rest[sel])}
        return b
    gi = g[idx]
    below, same = int((gi < gap).sum()), int((gi == gap).sum())
    edges = rest_edges(float(np.std(gi)))
    bins = []
    if edges:
        at = np.searchsorted(np.asarray(edges), gi, side='right')
        for bi in range(len(edges) + 1):
            sel = idx[at == bi]
            bins.append([int(len(sel)), _r((end[sel] > 0).mean(), 3) if len(sel) else None,
                         _r(back[sel].mean(), 3) if len(sel) and j < 7 else None, _r(float(np.median(rest[sel]))) if len(sel) and j < 7 else None])
    return {'mark': MARKS[j], 'j': j, 'days': int(len(idx)), 'from': days[idx[0]], 'gap': _r(gap), 'pct': _r(100.0 * (below + 0.5 * same) / len(idx), 1),
            'edges': edges, 'bins': bins, 'similar': block(sim) | {'gaps': [_r(float(g[sim].min())), _r(float(g[sim].max()))]}, 'base': block(idx)}


def scan(h, cache, now=None, fetch_history=True, log=print):
    """One pass over every asset: today's price and path, the odds at the nearest mark."""
    now = now or dt.datetime.now(UTC)
    today = now.astimezone(ET).date().isoformat()
    out = {'schema': SCHEMA, 'generated_at': now.isoformat(timespec='seconds'), 'source': 'Yahoo Finance chart API (prices as published; some may be delayed)',
           'marks': list(MARKS), 'edges': EDGES, 'k': K_SIMILAR, 'session': None, 'assets': {}}
    for key, ysym, name, kind in assets():
        try:
            live = today_of(chart(h, ysym, '1d', '5m'))
        except Exception as exc:                                       # noqa: BLE001 — one asset's failure never stops the scan
            log(f'intraday {key}: {str(exc)[:120]}')
            continue
        if out['session'] is None and live['start'] and live['end']:
            out['session'] = {'date': et_of(live['start']).date().isoformat(), 'start': et_of(live['start']).isoformat(), 'end': et_of(live['end']).isoformat(),
                              'open': live['start'] <= now.timestamp() < live['end'],
                              'short': live['end'] - live['start'] < 6 * 3600}     # an early close (1 pm): the 4 pm odds don't apply
        if not live['price'] or not live['prev'] or not live['time']:
            continue
        t_et = et_of(live['time'])
        mins = (t_et.hour - 9) * 60 + t_et.minute - 30
        on_day = out['session'] and t_et.date().isoformat() == out['session']['date']
        move = live['price'] / live['prev'] - 1
        a = {'key': key, 'name': name, 'kind': kind, 'symbol': ysym, 'price': _r(live['price'], 4), 'prev': _r(live['prev'], 4), 'move': _r(move, 5),
             'time': t_et.isoformat(), 'today': bool(on_day and mins >= 0), 'path': [[x, _r(p / live['prev'] - 1, 5)] for x, p in live['path']],
             'hi': _r(max(p for _, p in live['path']) / live['prev'] - 1) if live['path'] else None, 'lo': _r(min(p for _, p in live['path']) / live['prev'] - 1) if live['path'] else None}
        if live['vwap_path']:                                          # today's VWAP from the five-minute bars (no volume: none)
            vw_now = live['vwap_path'][-1][1]
            a['vwap'] = _r(vw_now, 4)
            a['vs_vwap'] = _r(live['price'] / vw_now - 1)
            a['vwap_path'] = [[x, _r(v / live['prev'] - 1)] for x, v in live['vwap_path']]
        if on_day and 0 <= mins:
            try:
                hist = load_history(h, cache, key, ysym, today, fetch=fetch_history)
            except Exception as exc:                                   # noqa: BLE001
                log(f'intraday {key} history: {str(exc)[:120]}')
                hist = None
            if hist:
                j = nearest_mark(min(mins, 390))
                odds = analyse(hist, move, j, live['price'])
                if odds:
                    a['odds'] = odds
                if 'vs_vwap' in a:
                    vo = vwap_odds(hist, a['vs_vwap'], j)
                    if vo:
                        a['vwap_odds'] = vo
        out['assets'][key] = a
    return out


def session_open(h, now=None, ahead_min=20):
    now = now or dt.datetime.now(UTC)
    live = today_of(chart(h, 'SPY', '1d', '5m'))
    if not live['start'] or not live['end']:
        return False
    return live['start'] - ahead_min * 60 <= now.timestamp() < live['end'] + 10 * 60


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', help='the folder published as the branch intraday-live (live.json)')
    ap.add_argument('--cache', help='the hourly history cache (default OUT/cache/h60)')
    ap.add_argument('--session', action='store_true', help='exit 0 while the regular session is open (or opens within 20 minutes)')
    a = ap.parse_args()
    h = CS.Http({'query2.finance.yahoo.com': 0.4})
    if a.session:
        try:
            sys.exit(0 if session_open(h) else 1)
        except Exception as exc:                                       # noqa: BLE001
            print(f'session: {exc}', file=sys.stderr)
            sys.exit(1)
    if not a.out:
        ap.error('--out is required for a scan')
    out = Path(a.out)
    doc = scan(h, Path(a.cache) if a.cache else out / 'cache' / 'h60')
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / 'live.json.tmp'
    tmp.write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    tmp.replace(out / 'live.json')
    s = doc.get('session') or {}
    print(f"intraday: {len(doc['assets'])} assets, session {s.get('date')} {'open' if s.get('open') else 'closed'}, "
          f"{sum(1 for x in doc['assets'].values() if x.get('odds'))} with odds, {sum(1 for x in doc['assets'].values() if x.get('vwap_odds'))} with VWAP odds, "
          f"{h.calls} requests", flush=True)


if __name__ == '__main__':
    main()
