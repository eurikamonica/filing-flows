"""Options disclosure (4.5): option chains from CBOE's free delayed quotes (about 15 minutes late), summarised per
underlying once a day after the close:

  IV30 (CBOE's 30-day implied volatility) · put/call open interest · the IV smile of three expiries · the ATM IV term
  structure · open interest by strike · dealer gamma exposure (GEX) by strike, the call wall, the put wall, an approximate
  gamma flip · max pain of the nearest monthly expiry · 25-delta skew · the price distribution the options imply at up to
  nine expiries (the price paths: quantiles and max pain per expiry)

Price paths (detail 'paths'): per expiry the forward from put-call parity at the strikes nearest spot, the out-of-the-
money IV smile turned into total variance by log-moneyness (linear between strikes, flat beyond the last quoted one),
undiscounted Black call prices on a fine strike grid, and the risk-neutral CDF 1 + dC/dK (Breeden-Litzenberger), made
monotone; the quantiles 2.5 … 97.5%. Too few quoted strikes: a lognormal at the ATM IV. Risk-neutral, not a forecast of
where the price will go: it carries the market's price of risk (fatter downside) and no drift view.

GEX uses the common simplification that dealers are long the calls and short the puts customers hold: per strike,
gamma × open interest × 100 × spot² × 1% (calls +, puts −), in dollars per 1% move. It is a model, not a disclosure.

Underlyings: the indexes and ETFs in config options.always, plus the most-held stocks in 13F (market/by-ticker.json),
the hottest Signals names and the watched funds' largest holdings, up to options.max_tickers.
Cache:   cache/options/history.json (a daily row per underlying, kept for options.keep_days)
Publish: market/options.json (the summary table) and market/options/<TICKER>.json (one underlying's charts)
"""
import bisect
import datetime as dt
import json
import math
import re
from pathlib import Path

from core import now, read_json, write_json

URL = 'https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json'
SYM = re.compile(r'^([A-Z]+)(\d{6})([CP])(\d{8})$')
INDEXES = {'SPX', 'NDX', 'RUT', 'VIX', 'XSP', 'DJX'}


def cboe_symbol(ticker):
    t = ticker.upper().replace('.', '-')
    return '_' + t if t in INDEXES else t


def parse_chain(payload):
    """(spot, iv30, [contracts]) with expiry (ISO), type, strike."""
    data = (payload or {}).get('data') or {}
    spot = data.get('current_price') or data.get('close')
    out = []
    for o in data.get('options') or []:
        m = SYM.match(o.get('option') or '')
        if not m:
            continue
        y = m.group(2)
        try:
            exp = dt.date(2000 + int(y[:2]), int(y[2:4]), int(y[4:6])).isoformat()
        except ValueError:
            continue
        out.append({'exp': exp, 'type': m.group(3), 'k': int(m.group(4)) / 1000, 'iv': o.get('iv') or 0, 'oi': o.get('open_interest') or 0,
                    'vol': o.get('volume') or 0, 'delta': o.get('delta') or 0, 'gamma': o.get('gamma') or 0,
                    'bid': o.get('bid') or 0, 'ask': o.get('ask') or 0})
    return spot, data.get('iv30'), data.get('iv30_change'), out


def _pick_expiries(exps, today):
    """Nearest expiry at least a week out, the one closest to 30 days, the one closest to 90 days."""
    days = {e: (dt.date.fromisoformat(e) - today).days for e in exps}
    future = [e for e in exps if days[e] >= 0]
    if not future:
        return []
    near = min((e for e in future if days[e] >= 7), key=lambda e: days[e], default=future[0])
    m30 = min(future, key=lambda e: abs(days[e] - 30))
    m90 = min(future, key=lambda e: abs(days[e] - 90))
    return list(dict.fromkeys([near, m30, m90]))


def _monthly(exps):
    """Third-Friday expiries (the standard monthlies)."""
    out = []
    for e in exps:
        d = dt.date.fromisoformat(e)
        if d.weekday() == 4 and 15 <= d.day <= 21:
            out.append(e)
    return out


PROBS = (0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975)
PATH_DAYS = (7, 14, 30, 60, 90, 180, 270, 365)


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _black_call(F, K, w):
    """Undiscounted Black call with total variance w = IV² × T."""
    if w <= 0:
        return max(F - K, 0.0)
    sd = math.sqrt(w)
    d1 = (math.log(F / K) + 0.5 * w) / sd
    return F * _ncdf(d1) - K * _ncdf(d1 - sd)


def _mid(c):
    return (c['bid'] + c['ask']) / 2 if c['bid'] > 0 and c['ask'] >= c['bid'] else None


def forward(rows, spot):
    """The forward from put-call parity (F ≈ K + C − P, undiscounted) at the three strikes nearest spot with both
    quoted; spot when none is."""
    by = {}
    for c in rows:
        m = _mid(c)
        if m is not None:
            by.setdefault(c['k'], {})[c['type']] = m
    ks = sorted((k for k, v in by.items() if 'C' in v and 'P' in v), key=lambda k: abs(k - spot))[:3]
    if not ks:
        return spot
    f = sorted(k + by[k]['C'] - by[k]['P'] for k in ks)[len(ks) // 2]
    return f if 0.5 * spot < f < 1.5 * spot else spot


def _smile_fit(xs, ws):
    """Total variance w(x) by log-moneyness x: a quadratic fitted by least squares (weighted toward the money) over the
    quoted strikes, continued linearly beyond them with the end slopes (|slope| ≤ 2, Lee's bound), floored at a fifth
    of the at-the-money variance. Smooth, so the density it implies has no spikes at the quoted strikes."""
    i0 = min(range(len(xs)), key=lambda i: abs(xs[i]))
    sd = math.sqrt(max(ws[i0], 1e-8))
    W = [math.exp(-0.5 * (x / (2 * sd)) ** 2) + 0.02 for x in xs]
    S = [[sum(w * x ** (a + b) for w, x in zip(W, xs)) for b in range(3)] for a in range(3)]
    y = [sum(w * v * x ** a for w, v, x in zip(W, ws, xs)) for a in range(3)]
    try:                                                     # 3 × 3 normal equations (Cramer)
        det = lambda M: (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])  # noqa: E731
                         + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
        D = det(S)
        if abs(D) < 1e-30:
            return None
        c = [det([[y[r] if j == a else S[r][j] for j in range(3)] for r in range(3)]) / D for a in range(3)]
    except (OverflowError, ZeroDivisionError):
        return None
    lo, hi = xs[0], xs[-1]
    q = lambda x: c[0] + c[1] * x + c[2] * x * x             # noqa: E731
    dl = max(-2.0, min(2.0, c[1] + 2 * c[2] * lo))
    dh = max(-2.0, min(2.0, c[1] + 2 * c[2] * hi))
    w_atm = q(0.0)
    if not (w_atm > 0):
        return None
    floor = 0.2 * w_atm

    def w(x):
        v = q(lo) + dl * (x - lo) if x < lo else q(hi) + dh * (x - hi) if x > hi else q(x)
        return max(v, floor)
    return w


def implied_quantiles(rows, spot, T, probs=PROBS, n=1201):
    """(forward, ATM IV, quantiles [price per prob], method, strikes used) of the risk-neutral distribution at one
    expiry, from its out-of-the-money smile (Breeden-Litzenberger); None without a usable IV."""
    F = forward(rows, spot)
    pts = {}
    for c in rows:                                           # a live two-sided quote: an IV off an ask alone is noise
        m = _mid(c)
        if c['iv'] <= 0 or c['iv'] > 5 or m is None or c['ask'] - c['bid'] > max(0.15, 0.8 * m):
            continue
        if (c['type'] == 'P' and c['k'] < F) or (c['type'] == 'C' and c['k'] >= F):
            pts[c['k']] = c['iv']
    ks = sorted(pts)
    xs = [math.log(k / F) for k in ks]
    ws = [pts[k] ** 2 * T for k in ks]
    fit = _smile_fit(xs, ws) if len(ks) >= 5 and xs[0] < 0 < xs[-1] else None
    if fit:
        method, w_at = 'smile', fit
        atm = math.sqrt(w_at(0.0) / T)
    else:
        near = [c['iv'] for c in rows if 0 < c['iv'] <= 5 and abs(c['k'] - spot) <= 0.05 * spot and _mid(c) is not None]
        near = near or [c['iv'] for c in rows if 0 < c['iv'] <= 5 and abs(c['k'] - spot) <= 0.05 * spot]
        if not near:
            return None
        atm = sorted(near)[len(near) // 2]
        method, w0 = 'atm', atm * atm * T
        w_at = lambda x: w0                                 # noqa: E731 — a flat smile: the lognormal
    sd = math.sqrt(atm * atm * T)
    grid = [-9 * sd + 18 * sd * i / (n - 1) for i in range(n)]
    K = [F * math.exp(x) for x in grid]
    C = [_black_call(F, k, w_at(x)) for k, x in zip(K, grid)]
    cdf = [0.0] * n
    for i in range(n):
        lo, hi = max(0, i - 1), min(n - 1, i + 1)
        cdf[i] = min(1.0, max(0.0, 1 + (C[hi] - C[lo]) / (K[hi] - K[lo])))
    for i in range(1, n):                                    # a calendar of quotes can hold small arbitrage: monotone
        cdf[i] = max(cdf[i], cdf[i - 1])
    q = []
    for p in probs:
        j = bisect.bisect_left(cdf, p)
        if j <= 0:
            q.append(K[0])
        elif j >= n:
            q.append(K[-1])
        else:
            a = (p - cdf[j - 1]) / ((cdf[j] - cdf[j - 1]) or 1)
            q.append(K[j - 1] * (K[j] / K[j - 1]) ** a)
    return F, atm, q, method, len(ks) if method == 'smile' else 0


def max_pain_of(rows):
    rows = [c for c in rows if c['oi']]
    ks = sorted({c['k'] for c in rows})
    if not ks:
        return None
    pay = lambda s: sum(c['oi'] * (max(0, s - c['k']) if c['type'] == 'C' else max(0, c['k'] - s)) for c in rows)  # noqa: E731
    return min(ks, key=pay)


def walls_of(rows, spot, band=0.3):
    """(call wall, its open interest, put wall, its open interest) of one expiry: the call wall is the strike at or
    above spot (up to +30%) with the most call open interest — the ceiling — and the put wall the strike at or below
    spot (down to −30%) with the most put open interest — the floor. In-the-money contracts are left out, so the two
    bracket the price."""
    lo, hi = spot * (1 - band), spot * (1 + band)
    oi = {}
    for c in rows:
        if c['oi'] and lo <= c['k'] <= hi:
            a = oi.setdefault(c['k'], [0, 0])
            a[0 if c['type'] == 'C' else 1] += c['oi']
    cw = max((k for k in oi if oi[k][0] and k >= spot), key=lambda k: oi[k][0], default=None)
    pw = max((k for k in oi if oi[k][1] and k <= spot), key=lambda k: oi[k][1], default=None)
    return cw, oi[cw][0] if cw is not None else 0, pw, oi[pw][1] if pw is not None else 0


def price_paths(live, spot, today, days=PATH_DAYS, probs=PROBS):
    """Up to nine expiries (the nearest at least two days out and those closest to 1, 2 weeks, 1, 2, 3, 6, 9, 12
    months): per expiry the options-implied quantiles of the price, its max pain and its call and put walls."""
    exps = sorted({c['exp'] for c in live})
    dd = {e: (dt.date.fromisoformat(e) - today).days for e in exps}
    fut = [e for e in exps if 2 <= dd[e] <= 400]
    if not fut:
        return []
    pick = [fut[0]] + [min(fut, key=lambda e: abs(dd[e] - d)) for d in days if d <= dd[fut[-1]] + 15]
    out = []
    for e in sorted(set(pick)):
        rows = [c for c in live if c['exp'] == e]
        r = implied_quantiles(rows, spot, max(dd[e], 0.5) / 365.0, probs)
        if not r:
            continue
        F, atm, q, method, used = r
        sig5 = lambda v: float(f'{v:.5g}')                    # noqa: E731
        cw, cwo, pw, pwo = walls_of(rows, spot)
        out.append({'call_wall': cw, 'call_wall_oi': cwo, 'put_wall': pw, 'put_wall_oi': pwo,'exp': e, 'days': dd[e], 'fwd': sig5(F), 'atm_iv': round(atm, 4), 'method': method, 'strikes': used,
                    'q': [sig5(v) for v in q], 'max_pain': max_pain_of(rows), 'oi': sum(c['oi'] for c in rows)})
    return out


def summarise(ticker, spot, iv30, iv30_chg, chain, today=None, band=0.3):
    today = today or dt.date.today()
    if not spot or not chain:
        return None, None
    live = [c for c in chain if c['exp'] >= today.isoformat()]
    exps = sorted({c['exp'] for c in live})
    oi_call = sum(c['oi'] for c in live if c['type'] == 'C')
    oi_put = sum(c['oi'] for c in live if c['type'] == 'P')
    vol_call = sum(c['vol'] for c in live if c['type'] == 'C')
    vol_put = sum(c['vol'] for c in live if c['type'] == 'P')
    lo, hi = spot * (1 - band), spot * (1 + band)
    near = [c for c in live if lo <= c['k'] <= hi]
    # GEX by strike, all expiries
    gex = {}
    for c in near:
        g = c['gamma'] * c['oi'] * 100 * spot * spot * 0.01
        gex[c['k']] = gex.get(c['k'], 0) + (g if c['type'] == 'C' else -g)
    strikes = sorted(gex)
    net_gex = sum(gex.values())
    flip, run = None, 0.0
    for i, k in enumerate(strikes):                       # where cumulative GEX (low → high strikes) changes sign
        prev = run
        run += gex[k]
        if i and prev < 0 <= run or i and prev > 0 >= run:
            flip = k
    oi_by = {}
    for c in near:
        a = oi_by.setdefault(c['k'], [0, 0])
        a[0 if c['type'] == 'C' else 1] += c['oi']
    call_wall = max(oi_by, key=lambda k: oi_by[k][0]) if oi_by else None
    put_wall = max(oi_by, key=lambda k: oi_by[k][1]) if oi_by else None
    # max pain: nearest monthly expiry
    mons = [e for e in _monthly(exps) if (dt.date.fromisoformat(e) - today).days >= 2]
    max_pain, mp_exp = None, mons[0] if mons else None
    if mp_exp:
        max_pain = max_pain_of([c for c in live if c['exp'] == mp_exp])
    # term structure: ATM IV per expiry
    term = []
    for e in exps[:24]:
        rows = [c for c in live if c['exp'] == e and c['iv'] > 0]
        if not rows:
            continue
        k = min({c['k'] for c in rows}, key=lambda k: abs(k - spot))
        ivs = [c['iv'] for c in rows if c['k'] == k]
        term.append([e, round(sum(ivs) / len(ivs), 4)])
    # smiles: out-of-the-money IV by strike for three expiries
    smiles = []
    for e in _pick_expiries(exps, today):
        pts = sorted([c['k'], round(c['iv'], 4)] for c in live if c['exp'] == e and c['iv'] > 0 and (c['bid'] > 0 or c['oi'] > 0)
                     and lo <= c['k'] <= hi and ((c['type'] == 'P' and c['k'] <= spot) or (c['type'] == 'C' and c['k'] > spot)))
        if len(pts) >= 5:
            smiles.append({'exp': e, 'days': (dt.date.fromisoformat(e) - today).days, 'pts': pts})
    # 25-delta skew on the ~30-day expiry
    skew = None
    if smiles:
        e30 = min(smiles, key=lambda s: abs(s['days'] - 30))['exp']
        rows = [c for c in live if c['exp'] == e30 and c['iv'] > 0]
        p = min((c for c in rows if c['type'] == 'P'), key=lambda c: abs(c['delta'] + 0.25), default=None)
        cc = min((c for c in rows if c['type'] == 'C'), key=lambda c: abs(c['delta'] - 0.25), default=None)
        if p and cc and abs(p['delta'] + 0.25) < 0.1 and abs(cc['delta'] - 0.25) < 0.1:
            skew = round(p['iv'] - cc['iv'], 4)
    summary = {'ticker': ticker, 'spot': round(spot, 4), 'iv30': iv30, 'iv30_chg': iv30_chg,
               'pc_oi': round(oi_put / oi_call, 3) if oi_call else None, 'pc_vol': round(vol_put / vol_call, 3) if vol_call else None,
               'oi_call': oi_call, 'oi_put': oi_put, 'net_gex': round(net_gex), 'gamma_flip': flip, 'call_wall': call_wall,
               'put_wall': put_wall, 'max_pain': max_pain, 'max_pain_exp': mp_exp, 'skew25': skew, 'expiries': len(exps),
               'contracts': len(live)}
    detail = {**summary, 'gex': [[k, round(gex[k])] for k in strikes if gex[k]],
              'oi': [[k, v[0], v[1]] for k, v in sorted(oi_by.items()) if v[0] or v[1]], 'term': term, 'smiles': smiles,
              'paths': price_paths(live, spot, today), 'path_probs': list(PROBS)}
    return summary, detail


def underlyings(root, cfg):
    root = Path(root)
    picks = list(cfg.get('always', ['SPX', 'SPY', 'QQQ', 'IWM']))
    try:
        sig = json.loads((root / 'market' / 'signals.json').read_text(encoding='utf-8'))
        picks += [r['ticker'] for r in sig.get('rows', []) if r.get('heat', 0) >= 3][:int(cfg.get('from_signals', 25))]
    except Exception:
        pass
    try:
        by = json.loads((root / 'market' / 'by-ticker.json').read_text(encoding='utf-8'))
        held = sorted(by.get('rows', {}).items(), key=lambda kv: -(kv[1][5] or 0))          # holders
        picks += [t for t, _ in held[:int(cfg.get('from_13f', 60))]]
    except Exception:
        pass
    out = []
    for t in picks:
        t = t.upper().replace('.', '-')
        if re.fullmatch(r'[A-Z]{1,5}(-[A-Z])?', t) and t not in out:
            out.append(t)
    return out[:int(cfg.get('max_tickers', 90))]


# Explicitly prioritize requested and commonly viewed symbols. Do not depend on
# a ticker being inside the 13F hot list or below a broad-universe cutoff.
DEFAULT_FAST = (
    'AAPL', 'NVDA', 'MSFT', 'AMZN', 'META', 'GOOGL', 'GOOG', 'TSLA',
    'AVGO', 'AMD', 'PLTR', 'OKLO', 'IREN', 'CRWV', 'NBIS',
    'SPY', 'QQQ', 'IWM', 'SPX', 'TLT',
)


def _symbols(values):
    seen = set()
    out = []
    for value in values or ():
        t = str(value or '').strip().upper().replace('.', '-')
        if re.fullmatch(r'[A-Z]{1,5}(-[A-Z])?', t) and t not in seen:
            out.append(t)
            seen.add(t)
    return out


def fast_underlyings(root, cfg, requested=()):
    """Fast lane: explicit requests, priority missing paths, then hot names.

    Reading the already-published detail is cheap and targets precisely the
    failure mode where CBOE chain metrics exist but option-implied paths don't.
    """
    root = Path(root)
    priority = _symbols(cfg.get('fast_priority') or DEFAULT_FAST)
    wanted = _symbols(requested)
    regular = underlyings(root, cfg)
    def missing_paths(ticker):
        doc = read_json(root / 'market' / 'options' / (ticker + '.json'), {})
        return not isinstance(doc.get('paths'), list) or not doc['paths']
    order = wanted + [t for t in priority if missing_paths(t)] + priority
    order += [t for t in regular if missing_paths(t)]
    cap = max(1, min(50, int(cfg.get('fast_max_tickers', 22))))
    return _symbols(order)[:max(cap, len(wanted))]


def collect(client, root, cfg=None, *, fast=False, requested=()):
    """Publish a partial scan without erasing previously valid CBOE snapshots.

    A failed CBOE request does not turn a previously sourced ticker into "no
    options". Every successfully refreshed row has its own CBOE source timestamp;
    older retained rows must never be presented as updated just because another
    symbol was refreshed.
    """
    cfg = cfg or {}
    root = Path(root)
    today = dt.datetime.now(dt.timezone.utc).date()
    hist_path = root / 'cache' / 'options' / 'history.json'
    hist = read_json(hist_path, {})
    out_dir = root / 'market' / 'options'
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = root / 'market' / 'options.json'
    old = read_json(index_path, {})
    old_rows = old.get('rows') if isinstance(old.get('rows'), list) else []
    rows_by = {row['ticker']: dict(row) for row in old_rows
               if isinstance(row, dict) and row.get('ticker')}
    # Backfill provenance from existing detail JSON where legacy index rows
    # contain no per-ticker timestamp; do not invent a quote date.
    for t, row in rows_by.items():
        if not row.get('as_of'):
            detail = read_json(out_dir / (t + '.json'), {})
            if detail.get('as_of'):
                row['as_of'] = detail['as_of']
    targets = fast_underlyings(root, cfg, requested) if fast else underlyings(root, cfg)
    errors, updated = [], []
    for t in targets:
        try:
            payload = client.json(URL.format(sym=cboe_symbol(t)))
            spot, iv30, chg, chain = parse_chain(payload)
            s, d = summarise(t, spot, iv30, chg, chain, today)
            if not s:
                raise ValueError('no valid option chain / spot')
            stamp = payload.get('timestamp') or (payload.get('data') or {}).get('timestamp')
            s['as_of'] = stamp       # quote timestamp from CBOE, NOT scan time
            s['collected_at'] = now()
            # Write details only on successful parsing; preserve a previous
            # sourced detail and its paths when a request fails.
            write_json(out_dir / (t + '.json'), {
                **d, 'as_of': stamp, 'generated_at': s['collected_at']})
            rows_by[t] = s
            updated.append(t)
            h = [r for r in hist.get(t, []) if r[0] != today.isoformat()]
            h.append([today.isoformat(), s['spot'], s['iv30'], s['pc_oi'],
                      s['net_gex'], s['skew25']])
            keep = (today - dt.timedelta(days=int(cfg.get('keep_days', 400)))).isoformat()
            hist[t] = [r for r in h if r[0] >= keep]
        except Exception as exc:
            errors.append(f'{t}: {str(exc)[:120]}')
    write_json(hist_path, hist)
    for ticker, row in rows_by.items():
        ivs = [r[2] for r in hist.get(ticker, []) if len(r) > 2 and r[2] is not None]
        row['iv30_pct'] = (round(sum(v <= row['iv30'] for v in ivs) / len(ivs), 3)
                           if row.get('iv30') is not None and len(ivs) >= 20 else None)
        if ticker in updated or 'history' not in row:
            row['history'] = hist.get(ticker, [])[-60:]
    # Keep priority/recently rescanned symbols first without discarding others.
    order = list(dict.fromkeys(list(targets) + [r['ticker'] for r in old_rows
                                   if isinstance(r, dict) and r.get('ticker')] + list(rows_by)))
    rows = [rows_by[t] for t in order if t in rows_by]
    pub = {
        'generated_at': now(), 'rows': rows, 'errors': errors[:50],
        'scan': {'mode': 'supplement' if fast else 'full', 'requested': len(targets),
                 'updated': len(updated), 'retained': len(rows) - len(updated),
                 'failed': len(errors), 'updated_tickers': updated},
        'note': ('CBOE delayed quotes (usually about 15 minutes late); source as_of is per underlying. '
                 'The full universe refreshes after the close and priority symbols have supplemental '
                 'scans during weekdays. Failed requests retain older sourced snapshots; GEX is '
                 'a model, not a disclosure. Risk-neutral price paths are not price forecasts.')
    }
    write_json(index_path, pub)
    return {'status': 'ok' if updated else ('partial' if rows else 'error'),
            'underlyings': len(rows), 'updated': len(updated), 'attempted': len(targets),
            'errors': len(errors), 'updated_at': pub['generated_at']}


if __name__ == '__main__':
    import argparse
    import tempfile
    from core import Client

    ap = argparse.ArgumentParser(description='Lightweight CBOE options collection / missing-path repair')
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'docs' / 'data')
    ap.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'config' / 'settings.json')
    ap.add_argument('--fast', action='store_true', help='Prioritized supplemental scan, keeping other tickers')
    ap.add_argument('--tickers', default='', help='Comma-separated explicit tickers (fast lane)')
    args = ap.parse_args()
    settings = read_json(args.config, {})
    client = Client(tempfile.mkdtemp(prefix='ff-options-'), settings.get('http', {}))
    result = collect(client, args.root, settings.get('options', {}),
                     fast=args.fast, requested=args.tickers.split(',') if args.tickers else ())
    print(json.dumps(result))
    if result['status'] == 'error':
        raise SystemExit(1)
