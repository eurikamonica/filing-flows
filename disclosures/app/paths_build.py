"""The build step of app/paths.py: from the daily bars on file to public/ (see paths.py for the files and their meaning).

Per company (paths of 63 trading days, about 13 weeks):
  paths      the seven path models of paths_models.py on three years of daily log returns of the stock, the S&P 500 ETF
             (SPY), its sector ETF and its two most correlated peers, 600 paths each; their quantiles every five trading
             days, the probabilities of ending 10% / 20% lower or higher, drawdowns, and how the stock moves when the
             market or its sector falls 10% (the joint, correlated part); the ensemble pools every model's paths.
  analogs    analogs.py: its own most similar past windows, the most similar windows of every stock, its correlated peers
             (with the weeks by which they lead it), what it did when it and its peers last looked like today, and the
             lead–lag forecast when a significant leader exists.
  pa         price_action.py: the last 120 daily bars, the current reading of every family of rules, the overlays to draw,
             and the signals of the last ten bars with each rule's pooled out-of-sample evidence.
Across companies: the pooled backtest of every price-action rule (rules.json), the walk-forward scorecard of every path
model and analog method on a fixed sample of companies (models.json, recomputed weekly), portfolios of 13F managers and
officials, and the ledger: every Friday's forecasts frozen and scored 63 trading days later.
"""
import datetime as dt
import gzip
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json   # noqa: E402
import paths as P                             # noqa: E402
import paths_models as PM                     # noqa: E402
import analogs as AN                          # noqa: E402
import price_action as PA                     # noqa: E402

STEP = 5                                      # a point every five trading days on the published fans
QS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
BARS_SHOWN = 120
SCORE_DAYS = 7                                # the scorecards are recomputed when older than this
SCORE_TICKERS = 40
SCORE_EVERY = 126                             # trading days between walk-forward origins
LEDGER_KEEP = 120                             # frozen weeks kept


def sig(x, n=4):
    return None if x is None or not isinstance(x, (int, float)) or not math.isfinite(x) else float(f'{x:.{n}g}')


def rnd(o, n=4):
    """Round every float in a JSON-ready structure to n significant digits; NaN/inf → None."""
    if isinstance(o, float):
        return sig(o, n)
    if isinstance(o, (np.floating,)):
        return sig(float(o), n)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return [rnd(x, n) for x in o.tolist()]
    if isinstance(o, dict):
        return {k: rnd(v, n) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [rnd(x, n) for x in o]
    return o


# ------------------------------------------------------------------ bars → aligned arrays
def bars_of(root, ticker):
    b = P.load(root, ticker)
    if not b or len(b.get('t') or []) < 300:
        return None
    return {'t': b['t'], **{k: np.asarray(b[k], dtype=float) for k in ('o', 'h', 'l', 'c', 'ac', 'v')}}


def aligned_returns(series, days=None):
    """{name: bars} → (dates, R) daily log returns of the adjusted closes on the dates every series has, oldest first."""
    common = None
    for b in series.values():
        common = set(b['t']) if common is None else common & set(b['t'])
    dates = sorted(common or [])
    if days:
        dates = dates[-(days + 1):]
    cols = []
    for b in series.values():
        at = {d: i for i, d in enumerate(b['t'])}
        cols.append(b['ac'][[at[d] for d in dates]])
    X = np.log(np.column_stack(cols)) if cols else np.zeros((0, 0))
    return dates[1:], np.diff(X, axis=0)


def business_days(start, n):
    """The next n weekdays after `start` (holidays ignored: labels for the fan's x axis)."""
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.isoformat())
    return out


def fan(summary):
    """paths_models.summarize → the published fan: quantile prices every STEP days (day 0 = today's price)."""
    q = summary['q']
    idx = list(range(STEP - 1, len(q), STEP))
    if idx[-1] != len(q) - 1:
        idx.append(len(q) - 1)
    return [q[i] for i in idx], idx


# ------------------------------------------------------------------ one company
def company(root, c, ctx):
    """Everything published for one company, or None without enough bars."""
    b = bars_of(root, c['t'])
    if not b:
        return None
    price0, as_of = float(b['c'][-1]), b['t'][-1]
    out = {'cik': c['cik'], 'ticker': c['t'], 'name': c.get('name'), 'sector': c.get('sector'), 'as_of': as_of, 'price': sig(price0, 6)}
    # the assets simulated together: the stock, the market, its sector ETF, its two most correlated peers
    try:
        peers = AN.correlated_peers(b['t'], b['ac'], ctx['universe_an'], window=504, top=8, max_lag=4, wm=ctx.get('wmatrix'), target_ticker=c['t'])
    except Exception:                                                   # noqa: BLE001
        peers = []
    peers = [p for p in peers or [] if p.get('ticker') not in P.ETFS]
    series = {c['t']: b}
    roles = [{'t': c['t'], 'role': 'stock'}]
    for t, role in ((P.RH.BENCH, 'market'), (P.SECTOR_ETF.get(c.get('sector') or ''), 'sector')):
        if t and t in ctx['bars'] and t != c['t']:
            series[t] = ctx['bars'][t]
            roles.append({'t': t, 'role': role})
    for p in peers[:2]:
        pb = ctx['bars'].get(p['ticker']) or bars_of(root, p['ticker'])
        if pb is not None:
            series[p['ticker']] = pb
            roles.append({'t': p['ticker'], 'role': 'peer', 'corr': sig(p.get('corr'), 3)})
    dates, R = aligned_returns(series, days=P.WINDOW)
    out['assets'] = roles
    col = {r['role']: i for i, r in enumerate(roles) if r['role'] in ('market', 'sector')}
    if len(R) >= 250:
        fut = business_days(as_of, P.HORIZON)
        pp = {'horizon': P.HORIZON, 'step': STEP, 'window_days': len(R), 'models': {}}
        pool = []
        for k, m in enumerate(PM.MODELS):
            try:
                sims = PM.simulate(R, m, horizon=P.HORIZON, n=P.N_PATHS, seed=1000 + k + int(c['cik'] or 0) % 997)
            except Exception as exc:                                    # noqa: BLE001
                pp['models'][m] = {'error': str(exc)[:160]}
                continue
            s = PM.summarize(sims, price0, col=0, qs=QS)
            q, idx = fan(s)
            row = {'q': q, 'end': s['end'], **{x: s.get(x) for x in ('p_down10', 'p_up10', 'p_down20', 'p_up20', 'p_touch_down10', 'vol')},
                   'mdd': s.get('mdd'), 'joint': {}}
            for role, j in col.items():
                row['joint'][role] = PM.joint(sims, a=0, b=j, thr=-0.10)
            pp['models'][m] = row
            pool.append(sims[: max(1, P.N_PATHS // 2)])
        if pool:
            ens = np.concatenate(pool, axis=0)
            s = PM.summarize(ens, price0, col=0, qs=QS)
            q, idx = fan(s)
            pp['ensemble'] = {'q': q, 'end': s['end'], **{x: s.get(x) for x in ('p_down10', 'p_up10', 'p_down20', 'p_up20', 'p_touch_down10', 'vol')},
                              'mdd': s.get('mdd'), 'joint': {role: PM.joint(ens, a=0, b=j, thr=-0.10) for role, j in col.items()},
                              'sample': [[p[i] for i in idx] for p in PM.sample_paths(ens, price0, col=0, k=30, seed=7)]}
            pp['days'] = [fut[i] for i in idx]
        out['paths'] = pp
    # analogs and correlated-asset historical simulation
    an = {'peers': peers}
    U = ctx['universe_an']
    leaders = [p for p in peers if p.get('lead_p') is not None and p['lead_p'] < 0.05]
    for key, fn in (('self', lambda: AN.self_analogs(b['t'], b['ac'], horizon=P.HORIZON)),
                    ('pooled', lambda: AN.pooled_analogs((b['t'], b['ac']), U, horizon=P.HORIZON, lib=ctx.get('library'))
                     if ctx.get('library') is not None else None),
                    ('peer', lambda: AN.peer_conditional((b['t'], b['ac']), [p['ticker'] for p in peers[:5]], U, horizon=P.HORIZON, target_ticker=c['t'])
                     if peers else None),
                    ('leadlag', lambda: AN.lead_lag_forecast((b['t'], b['ac']), leaders, U, horizon=21, target_ticker=c['t']) if leaders else None)):
        try:
            an[key] = slim_analog(fn(), price0)
        except Exception as exc:                                        # noqa: BLE001
            an[key] = {'error': str(exc)[:160]}
    out['analogs'] = an
    # price action
    try:
        st = PA.state(b['o'], b['h'], b['l'], b['c'], b['v'], b['t'])
        ov = PA.overlays(b['o'], b['h'], b['l'], b['c'], b['v'], b['t'], last=BARS_SHOWN)
        stats = ctx.get('rule_stats') or {}
        sigs = []
        for e in (st.get('recent') or []):
            rid = e.get('rule')
            sigs.append({**e, 'stats': stats.get(rid)})
        n = BARS_SHOWN
        out['pa'] = {'bars': {'t': b['t'][-n:], **{k: [sig(float(x), 6) for x in b[k][-n:]] for k in ('o', 'h', 'l', 'c')},
                              'v': [int(x) for x in b['v'][-n:]]},
                     'state': st, 'overlays': ov, 'signals': sigs}
    except Exception as exc:                                            # noqa: BLE001
        out['pa'] = {'error': str(exc)[:160]}
    return rnd(out)


def slim_analog(r, price0):
    """An analogs.py result trimmed for publication: the fan every STEP days and the end quantiles as prices
    (analogs.py works in cumulative log returns: q05 … q95), and the eight closest neighbors with their paths every
    STEP days (still log returns)."""
    if not r:
        return None
    keys = ('q05', 'q10', 'q25', 'q50', 'q75', 'q90', 'q95')
    out = {k: r[k] for k in ('p_up', 'similarity', 'mean', 'k', 'r2_in', 'n_leaders', 'point', 'n_train', 'as_of') if k in r}
    q = r.get('q')
    if isinstance(q, dict) and q.get('q50'):
        n = len(q['q50'])
        idx = list(range(STEP - 1, n, STEP))
        if idx and idx[-1] != n - 1:
            idx.append(n - 1)
        out['q'] = [[price0 * math.exp(q[k][i]) for k in keys] for i in idx]
    e = r.get('end') or r.get('q_end')
    if isinstance(e, dict):
        out['end'] = {'p' + k[1:]: price0 * math.exp(v) for k, v in e.items() if v is not None}
    if r.get('beta') is not None:
        out['leaders'] = r['beta'] if isinstance(r['beta'], (dict, list)) else None
    nb = []
    for x in (r.get('neighbors') or [])[:8]:
        path = x.get('path') or []
        nb.append({kk: x[kk] for kk in ('date', 'ticker', 'dist', 'fwd') if kk in x} |
                  {'path': [path[i] for i in range(STEP - 1, len(path), STEP)] if path else []})
    if nb:
        out['neighbors'] = nb
    return out


# ------------------------------------------------------------------ the shared context (built once, inherited by the workers)
CTX = {}


def _worker(args):
    root, c = args
    t0 = time.monotonic()
    try:
        doc = company(root, c, CTX)
    except Exception as exc:                                            # noqa: BLE001
        return c, None, {'error': f'{type(exc).__name__}: {str(exc)[:200]}'}, time.monotonic() - t0
    return c, doc, None, time.monotonic() - t0


def _detect(args):
    root, t = args
    b = bars_of(root, t)
    if not b:
        return t, None
    try:
        return t, (b['t'], b['ac'], PA.detect(b['o'], b['h'], b['l'], b['c'], b['v']))
    except Exception:                                                   # noqa: BLE001
        return t, None


def build(root, universe_path, people=None, limit=0, workers=None):
    root = Path(root)
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    comps = [c for c in P.universe(universe_path) if P.load(root, c['t'])]
    if limit:
        comps = comps[:limit]
    workers = workers or max(1, min(4, os.cpu_count() or 1))
    # shared inputs: every ETF's bars, every company's adjusted closes (for peers, analog libraries and portfolios)
    CTX.clear()
    CTX['bars'] = {t: b for t in P.ETFS if (b := bars_of(root, t)) is not None}
    uni = {}
    for c in comps:
        b = CTX['bars'].get(c['t']) or bars_of(root, c['t'])
        if b is not None:
            uni[c['t']] = (b['t'], b['ac'])
    for t, b in CTX['bars'].items():
        uni[t] = (b['t'], b['ac'])
    CTX['universe_ac'] = uni
    CTX['universe_an'] = AN.prepare_universe(uni)
    last = max((v[0][-1] for v in uni.values()), default=None)
    try:
        CTX['wmatrix'] = AN.weekly_matrix(CTX['universe_an'], last, 110)
    except Exception:                                                   # noqa: BLE001
        CTX['wmatrix'] = None
    try:                                     # every window whose 63 days ahead are known by the last bar
        CTX['library'] = AN.build_library(CTX['universe_an'], 60, P.HORIZON, 5, last)
    except Exception:                                                   # noqa: BLE001
        CTX['library'] = None
    status = {'built_at': now(), 'companies': 0, 'failed': 0, 'errors': []}
    # 1) the pooled price-action backtest (reused for a week)
    rules_path = pub / 'rules.json'
    rules = read_json(rules_path, {})
    if _stale(rules.get('built_at')) or limit:
        rules = pooled_rules(root, list(uni), workers)
        write_json(rules_path, rnd(rules))
    CTX['rule_stats'] = {r['id']: r.get('stats') for r in rules.get('rules') or []}
    # 2) every company
    index = []
    for c, doc, err, secs in _map(_worker, [(str(root), c) for c in comps], workers):
        if doc is None:
            status['failed'] += 1
            if err and len(status['errors']) < 20:
                status['errors'].append({'ticker': c['t'], **err})
            continue
        (pub / 'c' / f"{int(c['cik'])}.json").write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
        index.append(index_row(doc))
        status['companies'] += 1
    write_json(pub / 'index.json', {'generated_at': now(), 'fields': INDEX_FIELDS, 'rows': index})
    # 3) the scorecards (weekly), the ledger, the portfolios
    models_path = pub / 'models.json'
    models = read_json(models_path, {})
    if _stale(models.get('built_at')) or limit:
        models = scorecards(root, comps, uni)
        write_json(models_path, rnd(models))
    write_json(pub / 'ledger.json', rnd(ledger(root, pub)))
    if people:
        status['portfolios'] = portfolios(root, pub, Path(people), uni)
    status['seconds'] = round(time.monotonic() - t0)
    write_json(pub / 'status.json', status)
    return status


def _stale(at, days=SCORE_DAYS):
    try:
        return dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(at) > dt.timedelta(days=days)
    except (TypeError, ValueError):
        return True


def _map(fn, items, workers):
    if workers <= 1:
        for x in items:
            yield fn(x)
        return
    import multiprocessing as mp
    ctx = mp.get_context('fork')
    with ctx.Pool(workers) as pool:
        yield from pool.imap_unordered(fn, items, chunksize=4)


INDEX_FIELDS = ['cik', 'ticker', 'name', 'sector', 'price', 'as_of', 'p50', 'p10', 'p90', 'p_down10', 'p_up10', 'vol', 'mdd50',
                'crash_market', 'self_up', 'peer_up', 'always_in', 'structure', 'bull_signals', 'bear_signals', 'top_peer']


def index_row(d):
    e = ((d.get('paths') or {}).get('ensemble')) or {}
    end = e.get('end') or {}
    p0 = d.get('price') or 0
    pct = lambda v: sig(v / p0 - 1, 3) if v and p0 else None
    st = ((d.get('pa') or {}).get('state')) or {}
    sigs = (d.get('pa') or {}).get('signals') or []
    good = lambda s: ((s.get('stats') or {}).get('evidence') or {})
    strong = lambda s: any(v in ('strong', 'moderate') for v in (good(s).values() if isinstance(good(s), dict) else [good(s)]))
    peers = (d.get('analogs') or {}).get('peers') or []
    return [d.get('cik'), d.get('ticker'), d.get('name'), d.get('sector'), d.get('price'), d.get('as_of'),
            pct(end.get('p50')), pct(end.get('p10')), pct(end.get('p90')), e.get('p_down10'), e.get('p_up10'), e.get('vol'),
            (e.get('mdd') or {}).get('p50'), ((e.get('joint') or {}).get('market') or {}).get('p_a_given_b'),
            ((d.get('analogs') or {}).get('self') or {}).get('p_up'), ((d.get('analogs') or {}).get('peer') or {}).get('p_up'),
            _get(st, 'brooks', 'always_in') or st.get('always_in'), _get(st, 'structure', 'trend'),
            sum(1 for s in sigs if s.get('dir') in (1, 'bull') and strong(s)), sum(1 for s in sigs if s.get('dir') in (-1, 'bear') and strong(s)),
            peers[0]['ticker'] if peers else None]


def _get(d, *ks):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
    return d


# ------------------------------------------------------------------ the pooled price-action backtest
def pooled_rules(root, tickers, workers):
    pool = PA.Pool()
    n = 0
    for t, got in _map(_detect, [(str(root), t) for t in tickers if t not in P.ETFS], workers):
        if got:
            dates, ac, events = got
            pool.add(t, dates, ac, events)
            n += 1
    res = pool.result(split='2021-01-01', horizons=(5, 20, 60))
    rules = []
    for r in PA.RULES:
        rules.append({**{k: r.get(k) for k in ('id', 'name', 'family', 'dir', 'subjective', 'what', 'rule', 'source')}, 'stats': res.get(r['id'])})
    return {'built_at': now(), 'tickers': n, 'split': '2021-01-01', 'horizons': [5, 20, 60], 'rules': rules}


# ------------------------------------------------------------------ the walk-forward scorecards (a fixed sample)
def score_sample(comps):
    """A fixed, spread-out sample: every k-th company by market value (so it changes only when the universe does)."""
    ok = [c for c in comps if c['t'] not in P.ETFS]
    k = max(1, len(ok) // SCORE_TICKERS)
    return ok[::k][:SCORE_TICKERS]


def scorecards(root, comps, uni):
    sample = score_sample(comps)
    spy = bars_of(root, P.RH.BENCH)
    out = {'built_at': now(), 'tickers': [c['t'] for c in sample], 'horizon': P.HORIZON, 'window': P.WINDOW, 'paths': {}, 'analogs': {},
           'info': {'paths': getattr(PM, 'MODEL_INFO', {}), 'analogs': getattr(AN, 'METHOD_INFO', {})}}
    acc = {}
    for c in sample:
        b = bars_of(root, c['t'])
        if not b or spy is None:
            continue
        series = {c['t']: b, P.RH.BENCH: spy}
        sec = P.SECTOR_ETF.get(c.get('sector') or '')
        if sec and sec in CTX.get('bars', {}):
            series[sec] = CTX['bars'][sec]
        dates, R = aligned_returns(series)
        T = len(R)
        origins = list(range(P.WINDOW, T - P.HORIZON, SCORE_EVERY))
        if not origins:
            continue
        try:
            res = PM.evaluate_all(R, origins, horizon=P.HORIZON, window=P.WINDOW, n=300, seed=11)
        except Exception:                                               # noqa: BLE001
            continue
        for m, r in (res or {}).items():
            a = acc.setdefault(m, {'n': 0, 'cover80': 0.0, 'cover50': 0.0, 'pinball': 0.0, 'width80': 0.0})
            n = r.get('n') or 0
            if not n:
                continue
            for k in ('cover80', 'cover50', 'pinball', 'width80'):
                if r.get(k) is not None:
                    a[k] += r[k] * n
            a['n'] += n
    for m, a in acc.items():
        n = a['n'] or 1
        out['paths'][m] = {'n': a['n'], **{k: a[k] / n for k in ('cover80', 'cover50', 'pinball', 'width80')}}
    base = (out['paths'].get('naive') or {}).get('pinball')
    for m, r in out['paths'].items():
        r['skill'] = 1 - r['pinball'] / base if base else None
    for meth in ('self', 'pooled', 'peer', 'leadlag', 'naive'):
        try:
            last = max(v[0][-1] for v in uni.values())
            ods = [(dt.date.fromisoformat(last) - dt.timedelta(days=int(d))).isoformat() for d in range(182, 365 * 5, 182)]
            r = AN.evaluate_universe(meth, CTX.get('universe_an') or uni, [c['t'] for c in sample], sorted(ods), horizon=P.HORIZON,
                                     max_tickers=SCORE_TICKERS, max_origins=10)
            out['analogs'][meth] = {k: v for k, v in (r or {}).items() if k not in ('rows', 'pit')}
        except Exception as exc:                                        # noqa: BLE001
            out['analogs'][meth] = {'error': str(exc)[:160]}
    return out


# ------------------------------------------------------------------ the ledger: each Friday's forecasts frozen, then scored
def ledger(root, pub):
    """Freeze the week's ensemble and per-model end quantiles (first build of each week, keyed by the last bar's date
    week), resolve every frozen week whose horizon has passed against the actual close, and summarize by model."""
    lroot = Path(root) / 'cache' / 'ledger'
    lroot.mkdir(parents=True, exist_ok=True)
    ix = read_json(pub / 'index.json', {})
    rows = [dict(zip(ix.get('fields') or [], r)) for r in ix.get('rows') or []]
    as_of = max((r.get('as_of') or '' for r in rows), default='')
    if as_of:
        wk = RHfriday(as_of)
        path = lroot / f'{wk}.json'
        if not path.exists():
            frozen = {'week': wk, 'frozen_at': now(), 'as_of': as_of, 'rows': {}}
            for r in rows:
                d = read_json(pub / 'c' / f"{int(r['cik'])}.json", {})
                pp = d.get('paths') or {}
                fz = {'price': d.get('price'), 'as_of': d.get('as_of')}
                for m, x in list((pp.get('models') or {}).items()) + [('ensemble', pp.get('ensemble') or {})]:
                    e = x.get('end') or {}
                    if e.get('p50'):
                        fz[m] = [e.get('p10'), e.get('p25'), e.get('p50'), e.get('p75'), e.get('p90')]
                if len(fz) > 2:
                    frozen['rows'][d.get('ticker')] = fz
            write_json(path, frozen)
    weeks = sorted(p.stem for p in lroot.glob('*.json'))
    for old in weeks[:-LEDGER_KEEP]:
        (lroot / f'{old}.json').unlink(missing_ok=True)
    summary = []
    for wk in weeks[-LEDGER_KEEP:]:
        f = read_json(lroot / f'{wk}.json', {})
        res = f.get('resolved')
        if not res:
            res = resolve(root, f)
            if res:
                f['resolved'] = res
                write_json(lroot / f'{wk}.json', f)
        summary.append({'week': wk, 'n': len(f.get('rows') or {}), 'resolved': bool(res), 'models': (res or {}).get('models')})
    return {'generated_at': now(), 'horizon': P.HORIZON, 'weeks': summary}


def RHfriday(day):
    return P.RH.friday(dt.date.fromisoformat(day)).isoformat()


def resolve(root, frozen):
    """Score a frozen week once 63 trading days have passed for its rows: share of actual closes inside the 10–90% and
    25–75% ranges, and the mean absolute error of the median, per model."""
    acc, n_done = {}, 0
    for t, fz in (frozen.get('rows') or {}).items():
        b = P.load(root, t)
        if not b or fz.get('as_of') not in b['t']:
            continue
        i = b['t'].index(fz['as_of'])
        if i + P.HORIZON >= len(b['t']):
            return None                                                  # not yet: the horizon has not passed
        actual = b['c'][i + P.HORIZON]
        n_done += 1
        for m, q in fz.items():
            if m in ('price', 'as_of') or not q or None in q:
                continue
            a = acc.setdefault(m, {'n': 0, 'in80': 0, 'in50': 0, 'abs_err': 0.0})
            a['n'] += 1
            a['in80'] += int(q[0] <= actual <= q[4])
            a['in50'] += int(q[1] <= actual <= q[3])
            a['abs_err'] += abs(math.log(actual / q[2])) if q[2] and actual else 0
    if not n_done:
        return None
    return {'resolved_at': now(), 'rows': n_done,
            'models': {m: {'n': a['n'], 'cover80': a['in80'] / a['n'], 'cover50': a['in50'] / a['n'], 'mae_log': a['abs_err'] / a['n']}
                       for m, a in acc.items() if a['n']}}


# ------------------------------------------------------------------ portfolios of 13F managers and officials
def portfolio_series(holdings, uni, days=P.WINDOW + 1):
    """[(ticker, weight)] → (dates, daily log returns of the portfolio rebalanced to the weights each day, coverage =
    the share of the weight with bars). Holdings without bars are left out and the rest renormalized."""
    have = [(t, w) for t, w in holdings if t in uni and w and w > 0]
    cover = sum(w for _, w in have) / (sum(w for _, w in holdings if w and w > 0) or 1)
    if not have:
        return None, None, 0.0
    series = {t: {'t': uni[t][0], 'ac': uni[t][1]} for t, _ in have}
    if P.RH.BENCH in uni:
        series[P.RH.BENCH] = {'t': uni[P.RH.BENCH][0], 'ac': uni[P.RH.BENCH][1]}
    dates, R = aligned_returns(series, days=days)
    if len(R) < 250:
        return None, None, cover
    w = np.array([wt for _, wt in have], dtype=float)
    w /= w.sum()
    simple = np.expm1(R[:, :len(have)]) @ w
    port = np.log1p(simple)
    cols = [port] + ([R[:, -1]] if P.RH.BENCH in series else [])
    return dates, np.column_stack(cols), cover


def portfolio_doc(name, holdings, uni, seed):
    dates, R, cover = portfolio_series(holdings, uni)
    if R is None:
        return None
    price0 = 100.0
    out = {'name': name, 'coverage': cover, 'holdings': [[t, w] for t, w in holdings[:40]], 'models': {}}
    pool = []
    for k, m in enumerate(PM.MODELS):
        try:
            sims = PM.simulate(R, m, horizon=P.HORIZON, n=P.N_PATHS, seed=seed + k, factors=(1,))
        except Exception:                                               # noqa: BLE001
            continue
        s = PM.summarize(sims, price0, col=0, qs=QS)
        q, idx = fan(s)
        out['models'][m] = {'q': q, 'end': s['end'], 'p_down10': s.get('p_down10'), 'p_up10': s.get('p_up10'), 'mdd': s.get('mdd'),
                            'vol': s.get('vol'), 'joint': {'market': PM.joint(sims, 0, 1, -0.10)} if R.shape[1] > 1 else {}}
        pool.append(sims[: P.N_PATHS // 2])
    if pool:
        ens = np.concatenate(pool)
        s = PM.summarize(ens, price0, col=0, qs=QS)
        q, idx = fan(s)
        out['ensemble'] = {'q': q, 'end': s['end'], 'p_down10': s.get('p_down10'), 'p_up10': s.get('p_up10'), 'mdd': s.get('mdd'),
                           'vol': s.get('vol'), 'joint': {'market': PM.joint(ens, 0, 1, -0.10)} if R.shape[1] > 1 else {}}
    out['as_of'] = dates[-1]
    return rnd(out)


def official_holdings(o, months=24):
    """An official's disclosed purchases minus sales over the last `months` months (the hub's scored trades: date, ticker,
    d = +1 purchase / −1 sale, midpoint of the disclosed range), positive balances only → [(ticker, weight)]. An
    approximation: officials disclose ranges of transactions, not positions."""
    F = o.get('scored_fields') or []
    rows = [dict(zip(F, r)) for r in o.get('scored') or []]
    cut = (dt.date.today() - dt.timedelta(days=months * 31)).isoformat()
    bal = {}
    for r in rows:
        t, d = str(r.get('ticker') or '').strip().upper(), r.get('date') or ''
        if not t or d < cut or r.get('d') not in (1, -1):
            continue
        try:
            amt = float(r.get('midpoint') or 0)
        except (TypeError, ValueError):
            continue
        bal[t] = bal.get(t, 0) + r['d'] * amt
    pos = sorted(((t, v) for t, v in bal.items() if v > 0), key=lambda x: -x[1])
    tot = sum(v for _, v in pos) or 1
    return [(t, v / tot) for t, v in pos]


def portfolios(root, pub, people, uni):
    out = {'managers': [], 'officials': []}
    mg = read_json(people / 'managers.json', {})
    F = mg.get('fields') or []
    for r in (mg.get('rows') or [])[:200]:
        row = dict(zip(F, r))
        m = read_json(people / 'm' / f"{row.get('cik')}.json", None)
        if not m:
            continue
        HF = m.get('holdings_fields') or []
        hold = [dict(zip(HF, h)) for h in m.get('holdings') or []]
        hold = [(str(h.get('ticker') or '').upper(), float(h.get('weight') or 0)) for h in hold if h.get('ticker')]
        doc = portfolio_doc(m.get('name'), hold, uni, seed=int(m.get('cik') or 0) % 1000)
        if doc:
            (pub / 'portfolios' / 'm').mkdir(parents=True, exist_ok=True)
            write_json(pub / 'portfolios' / 'm' / f"{m.get('cik')}.json", doc)
            e = doc.get('ensemble') or {}
            out['managers'].append([m.get('cik'), m.get('slug'), m.get('name'), sig(doc['coverage'], 3), e.get('p_down10'), (e.get('mdd') or {}).get('p50')])
    of = read_json(people / 'officials.json', {})
    F = of.get('fields') or []
    for r in (of.get('rows') or [])[:200]:
        row = dict(zip(F, r))
        o = read_json(people / 'o' / f"{row.get('slug')}.json", None)
        if not o:
            continue
        hold = official_holdings(o)
        doc = portfolio_doc(o.get('name'), hold, uni, seed=sum(map(ord, o.get('slug') or '')) % 1000)
        if doc:
            doc['approximate'] = True
            (pub / 'portfolios' / 'o').mkdir(parents=True, exist_ok=True)
            write_json(pub / 'portfolios' / 'o' / f"{o.get('slug')}.json", doc)
            e = doc.get('ensemble') or {}
            out['officials'].append([o.get('slug'), o.get('name'), sig(doc['coverage'], 3), e.get('p_down10'), (e.get('mdd') or {}).get('p50')])
    write_json(pub / 'portfolios' / 'index.json', {'generated_at': now(), 'managers_fields': ['cik', 'slug', 'name', 'coverage', 'p_down10', 'mdd50'],
                                                    'managers': out['managers'], 'officials_fields': ['slug', 'name', 'coverage', 'p_down10', 'mdd50'],
                                                    'officials': out['officials']})
    return {'managers': len(out['managers']), 'officials': len(out['officials'])}
