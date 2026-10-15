"""Options disclosure (4.5): option chains from CBOE's free delayed quotes (about 15 minutes late), summarised per
underlying once a day after the close:

  IV30 (CBOE's 30-day implied volatility) · put/call open interest · the IV smile of three expiries · the ATM IV term
  structure · open interest by strike · dealer gamma exposure (GEX) by strike, the call wall, the put wall, an approximate
  gamma flip · max pain of the nearest monthly expiry · 25-delta skew

GEX uses the common simplification that dealers are long the calls and short the puts customers hold: per strike,
gamma × open interest × 100 × spot² × 1% (calls +, puts −), in dollars per 1% move. It is a model, not a disclosure.

Underlyings: the indexes and ETFs in config options.always, plus the most-held stocks in 13F (market/by-ticker.json),
the hottest Signals names and the watched funds' largest holdings, up to options.max_tickers.
Cache:   cache/options/history.json (a daily row per underlying, kept for options.keep_days)
Publish: market/options.json (the summary table) and market/options/<TICKER>.json (one underlying's charts)
"""
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
        rows = [c for c in live if c['exp'] == mp_exp and c['oi']]
        ks = sorted({c['k'] for c in rows})
        if ks:
            pay = lambda s: sum(c['oi'] * (max(0, s - c['k']) if c['type'] == 'C' else max(0, c['k'] - s)) for c in rows)
            max_pain = min(ks, key=pay)
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
              'oi': [[k, v[0], v[1]] for k, v in sorted(oi_by.items()) if v[0] or v[1]], 'term': term, 'smiles': smiles}
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


def collect(client, root, cfg=None):
    cfg = cfg or {}
    root = Path(root)
    today = dt.date.today()
    hist_path = root / 'cache' / 'options' / 'history.json'
    hist = read_json(hist_path, {})
    out_dir = root / 'market' / 'options'
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    for t in underlyings(root, cfg):
        try:
            payload = client.json(URL.format(sym=cboe_symbol(t)))
            spot, iv30, chg, chain = parse_chain(payload)
            s, d = summarise(t, spot, iv30, chg, chain, today)
        except Exception as exc:
            errors.append(f'{t}: {str(exc)[:120]}')
            continue
        if not s:
            continue
        rows.append(s)
        (out_dir / f'{t}.json').write_text(json.dumps({**d, 'as_of': payload.get('timestamp'), 'generated_at': now()},
                                                      separators=(',', ':')), encoding='utf-8')
        h = [r for r in hist.get(t, []) if r[0] != today.isoformat()]
        h.append([today.isoformat(), s['spot'], s['iv30'], s['pc_oi'], s['net_gex'], s['skew25']])
        keep = (today - dt.timedelta(days=int(cfg.get('keep_days', 400)))).isoformat()
        hist[t] = [r for r in h if r[0] >= keep]
    write_json(hist_path, hist)
    for r in rows:                                       # IV30 percentile over the stored history
        ivs = [x[2] for x in hist.get(r['ticker'], []) if x[2] is not None]
        r['iv30_pct'] = round(sum(v <= r['iv30'] for v in ivs) / len(ivs), 3) if r.get('iv30') is not None and len(ivs) >= 20 else None
        r['history'] = hist.get(r['ticker'], [])[-60:]
    pub = {'generated_at': now(), 'rows': rows, 'errors': errors[:20],
           'note': ('CBOE delayed quotes (about 15 minutes late), summarised once a day after the close. GEX assumes dealers are '
                    'long calls and short puts (calls +, puts −) and is a model, not a disclosure; the gamma flip is approximated '
                    'from cumulative GEX by strike. Max pain uses the nearest monthly expiry.')}
    (root / 'market' / 'options.json').write_text(json.dumps(pub, separators=(',', ':')), encoding='utf-8')
    return {'status': 'ok' if rows else 'error', 'underlyings': len(rows), 'errors': len(errors), 'updated_at': now()}
