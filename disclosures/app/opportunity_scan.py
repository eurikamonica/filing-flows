"""Opportunity scan (the hub's Opportunity → Scan): every stock's read from every model on the site in one row, a combined
score tested before it is shown, its probability, and a scoreboard of how each model has done out of sample.

One row per stock (Opportunity's universe, app/opportunity.py), with
  index         members.json (app/index_members.py): S&P 500, Nasdaq-100, Dow, S&P 400 / 600, Russell 1000 / 2000 / 3000
  opportunity   the chance of a higher price in 1 and 3 months, of a buy making money after costs, the 3-month range,
                the buy / short flag (app/opportunity.py)
  odds          the chance of touching +10% / −10% within 4 weeks and +20% / −20% within 13, of joining the S&P 500 and
                of a dividend cut within 12 months, Merton's default odds (app/odds.py)
  averages      Moving averages+ (app/ma_hybrid.py): the distance to the 200-day and the 40-week average and to the hybrid
                line, where that distance stands in the company's own history, the 50/200-day cross, guidance, the
                models' rank, its own season
  rrg           the hybrid RRG's 13-week forecast against SPY and its chance of beating it (app/rrg_hybrid.py)
  move          the latest day's move: its percentile in the company's own history, how often one that large comes, what
                followed the similar days a month later (app/moves.py, branch research-paths)
  highs / lows  at its highs, at an all-time / 52-week / 3-month low, in a narrow or a wide range, with what followed the
  / ranges      250 most similar days of other companies (app/highs.py, app/regimes.py)

Combined score. The models with a walk-forward forecast history of the next 13 weeks, kept by each in hist/cache/oos/
(app/oos_store.py): Opportunity's 3-month z-hat, the moving averages' 13-week forecast against SPY, the hybrid RRG's
stacked 13-week forecast. Each week each forecast is ranked across the liquid companies (0 to 1); the score is their
average, each weighted by its rank correlation with the later 13-week return against SPY in the years before (from
COMMON_FROM; the weights of a year come only from weeks whose outcome was known by its 1 January; a model with a
negative record weighs nothing), a model missing for a company left out of that company's average; the result ranked
again within the week (0–100). Tested from 2016 on the companies and weeks every model covers, against each model alone
and against equal weights: the weekly rank correlation (t: weeks ÷ 13 independent), the best − worst fifth in simple
returns against SPY after trading costs (app/rrg_hybrid.COST_TIERS, both legs in and out, no borrow fee) and a buyer's
measure — the top tenth against SPY and against the average company, after the top tenth's own costs in and out.
Its probability: the share of companies in the same tenth of the score that beat SPY over the next 13 weeks in the
CAL_YEARS years before (walk-forward from 2016, with the calibration table and the Brier skill against the base rate).
Each closed week the scores and probabilities of the most-traded companies and the S&P 500 are frozen (ledger) and
scored once 13 weeks have passed.

Rows are packed: each section ('opp', 'odds', 'ma' …) a list in the order of doc['cols'][section] (docs/opportunity-
scan.js unpacks them). Today's companies only (delisted names are missing). History and models, not investment advice.

    python app/opportunity_scan.py --public hist/public --oos hist/cache/oos --moves research-paths/public/moves \\
        --members site/members.json --ledger hist/ledger/opportunity-scan.json
"""
import argparse
import datetime as dt
import json
import math
import warnings
from pathlib import Path

import numpy as np

import forecast_book as FB
import ma_hybrid as MA
import oos_store
import rrg_hybrid as HY

VERSION = 1
H = 13
COMPONENTS = (('opp', 'opportunity-3m.npz', 'Opportunity, 3 months'), ('ma', 'ma-13.npz', 'Moving averages, 13 weeks'),
              ('rrg', 'rrg-13.npz', 'Hybrid RRG, 13 weeks'))
COMMON_FROM = 2013            # every model forecasts out of sample from here: the weights are learnt from these years on
TEST_FROM, SPLIT_AT = 2016, 2019
CAL_YEARS, CAL_MIN = 5, 3     # the probability: the beat rate of the score's tenth over the last 5 years, at least 3
DECILES = 10
MIN_NAMES = 50
MIN_IC_WEEKS = 52
LEDGER_MAX = 1200
RECENT_CROSS = 10             # trading days: a 50/200-day cross this recent is a flag
BIG_MOVE = 95                 # the latest day's move at or beyond this percentile of its own history (or 100 − it)
GUIDE_DAYS = 120              # a guidance release this recent is a flag (raised / lowered / kept or updated)
INDEX_ORDER = ('sp500', 'ndx', 'dji', 'sp400', 'sp600', 'r1000', 'r2000', 'r3000')
TOP = 0.9                     # the buyer's test: the top tenth of the score
SECTIONS = ('opp', 'odds', 'ma', 'rrg', 'move', 'hi', 'lo', 'rg')
fin, r_, years_of = HY.fin, HY.r_, HY.years_of


def rd(v, n):
    return round(float(v), n) if fin(v) else None


def rdl(a, n):
    """A list of numbers rounded (counts stay whole), or None."""
    return [x if isinstance(x, int) or x is None else rd(x, n) for x in a] if isinstance(a, list) else None


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8')) if p else None
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ the combined score
def align(Z, ids, days):
    """An oos_store matrix on (ids, days): NaN where the model said nothing."""
    out = np.full((len(ids), len(days)), np.nan, np.float32)
    if not Z:
        return out
    ix = {t: i for i, t in enumerate(ids)}
    cols = np.searchsorted(days, Z['dates'])
    okc = (cols < len(days)) & (days[np.clip(cols, 0, len(days) - 1)] == Z['dates'])
    src, dst = np.where(okc)[0], cols[okc]
    for j, t in enumerate(Z['tickers']):
        i = ix.get(t)
        if i is not None:
            out[i, dst] = Z['X'][j, src]
    return out


def pct_ranks(X, ok):
    """Each week, X ranked across the names in ok with a value: 0 (the lowest) … 1 (the highest)."""
    out = np.full(X.shape, np.nan, np.float32)
    for t in range(X.shape[1]):
        m = ok[:, t] & np.isfinite(X[:, t])
        n = int(m.sum())
        if n >= MIN_NAMES:
            out[m, t] = np.argsort(np.argsort(X[m, t], kind='stable'), kind='stable') / (n - 1)
    return out


def weekly_ic(X, Y, ok):
    """Each week, the rank correlation of X with the later return Y across the names in ok."""
    ic = np.full(X.shape[1], np.nan)
    for t in range(X.shape[1]):
        m = ok[:, t] & np.isfinite(X[:, t]) & np.isfinite(Y[:, t])
        if m.sum() >= MIN_NAMES and np.ptp(X[m, t]) > 0:
            ic[t] = np.corrcoef(np.argsort(np.argsort(X[m, t])), np.argsort(np.argsort(Y[m, t])))[0, 1]
    return ic


def weights_by_year(ics, days, years):
    """{year: {model: weight}}: each model's mean weekly rank correlation over the weeks from COMMON_FROM whose outcome was
    known by 1 January of that year, negative ones as nothing; equal weights while no model has a year of record."""
    yrs = years_of(days)
    out = {}
    for Y in years:
        known = HY.known_before(days, H, Y) & (yrs >= COMMON_FROM)
        w = {}
        for k, ic in ics.items():
            v = ic[known]
            v = v[np.isfinite(v)]
            w[k] = max(0.0, float(v.mean())) if len(v) >= MIN_IC_WEEKS else 0.0
        out[Y] = w if sum(w.values()) > 0 else {k: 1.0 for k in ics}
    return out


def combine(pcts, wby, days):
    """The weighted average of the models' weekly ranks (a model missing for a name left out of its average)."""
    yrs = years_of(days)
    shape = next(iter(pcts.values())).shape
    num, den = np.zeros(shape), np.zeros(shape)
    for k, p in pcts.items():
        w = np.array([wby.get(int(y), {}).get(k, 0.0) for y in yrs])[None]
        m = np.isfinite(p)
        num += np.where(m, p * w, 0.0)
        den += np.where(m, np.broadcast_to(w, shape), 0.0)
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(den > 0, num / den, np.nan)


def top_tests(X, Y, ok, cost):
    """Per week, a buyer's measure: the top tenth by X against SPY and against the average of every name, in simple
    returns, after the top tenth's own trading costs in and out; and the bottom tenth against the average (no cost: a
    name left out costs nothing)."""
    W = X.shape[1]
    vs_spy, vs_all, bot = np.full(W, np.nan), np.full(W, np.nan), np.full(W, np.nan)
    Ys = np.expm1(Y)
    for t in range(W):
        m = ok[:, t] & np.isfinite(X[:, t]) & np.isfinite(Y[:, t])
        if m.sum() < MIN_NAMES:
            continue
        x, y, c = X[m, t], Ys[m, t], cost[m, t]
        hi, lo = x >= np.quantile(x, TOP), x <= np.quantile(x, 1 - TOP)
        if hi.sum() < 5 or lo.sum() < 5:
            continue
        vs_spy[t] = y[hi].mean() - 2 * c[hi].mean()
        vs_all[t] = y[hi].mean() - y.mean() - 2 * c[hi].mean()
        bot[t] = y[lo].mean() - y.mean()
    return vs_spy, vs_all, bot


def calibrate(S, Y, ok, days):
    """S (each week's score as a rank, 0–1) → each name-week's probability of beating SPY over the next 13 weeks: the
    beat rate of its tenth of the score over the CAL_YEARS before (weeks known by 1 January; at least CAL_MIN years),
    from TEST_FROM. → (P, test {brier, brier_base, skill, table}, the rates now)."""
    yrs = years_of(days)
    dec = np.where(np.isfinite(S), np.minimum((np.nan_to_num(S) * DECILES).astype(int), DECILES - 1), -1)
    beat = Y > 0
    P, B = np.full(S.shape, np.nan), np.full(S.shape, np.nan)

    def rates(known):
        m = ok & np.isfinite(Y) & (dec >= 0) & known[None]
        if len(set(yrs[m.any(0)].tolist())) < CAL_MIN:
            return None, None
        return [float(beat[m & (dec == j)].mean()) if (m & (dec == j)).sum() >= 100 else float(beat[m].mean()) for j in range(DECILES)], float(beat[m].mean())
    for Yr in range(TEST_FROM, int(yrs[-1]) + 1):
        rt, base = rates(HY.known_before(days, H, Yr) & (yrs >= max(COMMON_FROM, Yr - CAL_YEARS)))
        if rt is None:
            continue
        te = ok & (dec >= 0) & (yrs == Yr)[None]
        P[te] = np.array(rt)[dec[te]]
        B[te] = base
    m = ok & np.isfinite(Y) & np.isfinite(P)
    test = None
    if m.sum() >= 1000:
        p, y, b = P[m], beat[m].astype(float), B[m]
        br, bb = float(np.mean((p - y) ** 2)), float(np.mean((b - y) ** 2))
        table = []
        for j in range(DECILES):
            mj = m & (dec == j)
            if mj.sum():
                table.append({'tenth': j + 1, 'said': r_(float(P[mj].mean()), 4), 'happened': r_(float(beat[mj].mean()), 4), 'n': int(mj.sum())})
        test = {'brier': r_(br, 5), 'brier_base': r_(bb, 5), 'skill': r_(1 - br / bb, 4) if bb > 0 else None, 'base_rate': r_(float(y.mean()), 4),
                'table': table, 'from': str(days[np.where(m.any(0))[0][0]])}
    t_last = len(days) - 1
    known_now = (np.arange(len(days)) + H <= t_last) & (yrs >= max(COMMON_FROM, int(yrs[t_last]) - CAL_YEARS))
    now, base_now = rates(known_now)
    return P, test, now, base_now


def composite(public, oos, verbose=lambda *a: None):
    """The combined score: its walk-forward test and this week's scores (None without any model history)."""
    hists = {k: oos_store.load(Path(oos) / fname) for k, fname, _ in COMPONENTS} if oos else {}
    if not any(hists.values()):
        verbose('scan: no model has kept its forecast history yet (hist/cache/oos) — no combined score')
        return None
    D = HY.load(public)
    days, spy = D['days'], D['spy']
    co = D['panels']['companies']
    ids, C, V, liq = co['ids'], co['C'], co['V'], co['liq']
    raw = {}
    for k, _, label in COMPONENTS:
        z = hists.get(k)
        if z:
            raw[k] = align(z, ids, days)
            verbose(f'scan: {label}: {int(np.isfinite(raw[k]).sum())} name-weeks, model saved {z["meta"].get("saved_at")}')
    rel = np.diff(np.log(C), axis=1, prepend=np.nan) - np.diff(np.log(spy), prepend=np.nan)[None]
    Y = HY.fwd_sum(rel, H)
    cost = MA.costs(C, V)
    pcts = {k: pct_ranks(X, liq) for k, X in raw.items()}
    ics = {k: weekly_ic(pcts[k], Y, liq) for k in pcts}
    yrs = years_of(days)
    last = int(yrs[-1])
    wby = weights_by_year(ics, days, range(int(yrs[0]), last + 1))
    S0 = combine(pcts, wby, days)
    S = pct_ranks(S0, liq & np.isfinite(S0))
    E = pct_ranks(combine(pcts, {Yr: {k: 1.0 for k in pcts} for Yr in range(int(yrs[0]), last + 1)}, days), liq)
    every = liq & np.all([np.isfinite(p) for p in pcts.values()], 0)
    tests = {}
    for name, X, m in [('score', S, every), ('equal', E, every)] + [(k, pcts[k], every) for k in pcts] + [('score_all', S, liq & np.isfinite(S))]:
        ic, net, gross = MA.per_week(X, Y, m, cost, 'fifths')
        tests[name] = MA.summarize(days, H, ic, net, gross)
        vs_spy, vs_all, bot = top_tests(X, Y, m, cost)
        for per, sel in MA.periods(days).items():
            tests[name][per].update({'top_spy': MA.week_stats(vs_spy[sel], H), 'top_all': MA.week_stats(vs_all[sel], H),
                                     'bottom_all': MA.week_stats(bot[sel], H)})
    P, cal, rates_now, base_now = calibrate(S, Y, liq & np.isfinite(S), days)
    t = len(days) - 1
    while t > 0 and np.isfinite(S[:, t]).sum() < MIN_NAMES:       # this week: the latest week with scores
        t -= 1
    dec = np.where(np.isfinite(S[:, t]), np.minimum((np.nan_to_num(S[:, t]) * DECILES).astype(int), DECILES - 1), -1)
    now = {}
    for i, tk in enumerate(ids):
        if np.isfinite(S[i, t]):
            now[tk] = {'score': r_(100 * float(S[i, t]), 1), 'tenth': int(dec[i]) + 1, 'p_beat': r_(rates_now[dec[i]], 3) if rates_now else None,
                       'parts': [r_(float(pcts[k][i, t]), 2) if k in pcts and np.isfinite(pcts[k][i, t]) else None for k, _, _ in COMPONENTS]}
    out = {'asof': str(days[t]), 'components': [{'key': k, 'name': label, 'present': k in raw} for k, _, label in COMPONENTS], 'top': TOP,
           'weights_now': {k: r_(v, 4) for k, v in wby.get(int(yrs[t]), {}).items()},
           'weights_by_year': {str(Yr): {k: r_(v, 4) for k, v in w.items()} for Yr, w in wby.items() if Yr >= TEST_FROM},
           'ic_by_model': {k: {'mean': r_(float(np.nanmean(ic[yrs >= TEST_FROM])), 4) if np.isfinite(ic[yrs >= TEST_FROM]).any() else None} for k, ic in ics.items()},
           'tests': tests, 'calibration': cal, 'rates_now': [r_(x, 4) for x in rates_now] if rates_now else None, 'base_now': r_(base_now, 4),
           'cal_years': CAL_YEARS, 'test_from': TEST_FROM, 'common_from': COMMON_FROM}
    ledger_bits = {'days': days, 't': t, 'ids': ids, 'S': S, 'C': C, 'V': V, 'spy': spy, 'rel': rel, 'rates_now': rates_now, 'dec': dec, 'pcts': pcts}
    return out, now, ledger_bits


# ------------------------------------------------------------------ this week's rows
def index_of(members):
    rows = (members or {}).get('rows') or {}
    return {t: [k for k in INDEX_ORDER if k in (r.get('now') or [])] for t, r in rows.items()}


def opportunity_rows(doc):
    if not doc:
        return {}
    F = doc.get('fields_h') or []
    ix = {k: i for i, k in enumerate(F)}
    out = {}
    for r in doc.get('rows') or []:
        h = r.get('h') or {}
        g = lambda hk, k: (h.get(hk) or [None] * len(F))[ix[k]] if k in ix and h.get(hk) else None
        p = lambda hk, k: rd(g(hk, k), 3)
        out[r['t']] = {'n': r.get('n'), 's': r.get('s'), 'up1m': p('1m', 'p_up'), 'up3m': p('3m', 'p_up'), 'buy1m': p('1m', 'p_buy'), 'buy3m': p('3m', 'p_buy'),
                       'r10': p('3m', 'r_p10'), 'r50': p('3m', 'r_p50'), 'r90': p('3m', 'r_p90'), 'side': r.get('side'), 'bh': r.get('best_h'),
                       'oscore': r.get('score'), 'drv': (r.get('drivers') or [[None]])[0][0], 'htb': r.get('htb')}
    return out


def odds_rows(doc):
    if not doc:
        return {}
    F = doc.get('fields') or []
    return {t: {k: rd(v, 3) for k, v in zip(F, row) if k != 'vol'} for t, row in (doc.get('rows') or {}).items()}


def ma_rows(doc):
    keep = {'close': None, 'gap40': 3, 'gap_hybrid': 3, 'hd_pct': 2, 'pct_ma': 2, 'pct_hybrid': 2, 'pct_macro': 2, 'd_asof': None, 'd_close': None,
            'd20': 3, 'd50': 3, 'd200': 3, 'x50_200': None, 'up50_200': None, 'guid': None, 'guid_last': None, 'seas13': 3, 'el': None, 'hybrid': None,
            'pe': None, 'pe_med': None, 'ma40': None}
    return {r['id']: {k: (rd(r.get(k), n) if n else r.get(k)) for k, n in keep.items() if r.get(k) is not None} for r in (doc or {}).get('rows') or []}


def rrg_rows(doc):
    out = {}
    for r in (doc or {}).get('rows') or []:
        h13 = r.get('h13') or {}
        c = r.get('classic') or [None, None]
        quad = None if not (fin(c[0]) and fin(c[1])) else ('leading' if c[0] >= 100 and c[1] >= 100 else 'weakening' if c[0] >= 100 else
                                                           'improving' if c[1] >= 100 else 'lagging')
        out[r.get('id')] = {'rel': rd(h13.get('rel'), 3), 'p': rd(h13.get('p'), 3), 'lo': rd(h13.get('lo'), 3), 'hi': rd(h13.get('hi'), 3), 'quad': quad}
    return out


def move_rows(doc):
    if not doc:
        return {}
    F = doc.get('fields') or []
    ix = {k: i for i, k in enumerate(F)}
    out = {}
    for r in doc.get('rows') or []:
        if r[ix['kind']] != 'stock':
            continue
        g = lambda k: r[ix[k]] if k in ix else None
        out[g('ticker')] = {'d': g('as_of'), 'last': g('last'), 'move': rd(g('move'), 4), 'pct': rd(g('pct'), 1), 'z': rd(g('z'), 2), 'every': rd(g('every'), 1),
                            'move5': rd(g('move5'), 3), 'move21': rd(g('move21'), 3), 'sim21': rdl(g('sim21'), 3), 'ext21': rdl(g('ext21'), 3),
                            'all21': rdl(g('all21'), 3), 'rvpct': rd(g('rvpct'), 0), 'd0': g('d0')}
    return out


def move_names(doc):
    """The companies' names as the move odds write them ("NVIDIA Corp", where Opportunity has the SEC's "NVIDIA CORP")."""
    F = (doc or {}).get('fields') or []
    if 'ticker' not in F or 'name' not in F:
        return {}
    i, j, k = F.index('ticker'), F.index('name'), F.index('kind') if 'kind' in F else None
    return {r[i]: r[j] for r in doc.get('rows') or [] if r[j] and (k is None or r[k] == 'stock')}


def _pp(a, k, sub='p', key='63'):
    v = (a or {}).get(k) or {}
    return rd((v.get(sub) or {}).get(key) if sub == 'p' else v.get(sub), 3)


def highs_rows(doc):
    out = {}
    for e in (doc or {}).get('now') or []:
        if e.get('group') != 'companies':
            continue
        st, an = e.get('state') or {}, e.get('analogues') or {}
        out[e['key']] = {'ath': bool(st.get('dd') == 0), 'age': st.get('age'), 'highs63': st.get('highs63'), 'dd': rd(st.get('dd'), 3),
                         'pull10_63': _pp(an, 't10'), 'gain_left': _pp(an, 'gain_left', 'p50'), 'fwd63': _pp(an, 'fwd63', 'p50'), 'fwd63_up': _pp(an, 'fwd63', 'up'),
                         'n': an.get('days')}
    return out


def lows_rows(doc):
    out = {}
    for reg in ('3m', '52w', 'atl'):                                   # the most extreme one wins: all-time over 52-week over 3-month
        for e in ((doc or {}).get('now') or {}).get(reg) or []:
            if e.get('group') != 'companies':
                continue
            an = e.get('analogues') or {}
            out[e['key']] = {'reg': reg, 'fwd63': _pp(an, 'fwd63', 'p50'), 'fwd63_up': _pp(an, 'fwd63', 'up'), 'next_low63': _pp(an, 'next_low'),
                             'r10_63': _pp(an, 'r10'), 'n': an.get('days'), 'dd': rd((e.get('state') or {}).get('dd_ath'), 3)}
    return out


def ranges_rows(doc):
    out = {}
    for reg in ('wide', 'narrow'):
        for e in ((doc or {}).get('now') or {}).get(reg) or []:
            if e.get('group') != 'companies':
                continue
            an = e.get('analogues') or {}
            out[e['key']] = {'reg': reg, 'break21': _pp(an, 'breakout', 'p', '21'), 'up_first': an.get('up_first'), 'fwd63': _pp(an, 'fwd63', 'p50'),
                             'fwd63_up': _pp(an, 'fwd63', 'up'), 'n': an.get('days'), 'width': rd((e.get('state') or {}).get('width'), 3)}
    return out


def recent(day, asof, days):
    try:
        return 0 <= (dt.date.fromisoformat(str(asof)[:10]) - dt.date.fromisoformat(str(day)[:10])).days <= days
    except (TypeError, ValueError):
        return False


def flags_of(r, asof=None):
    """Short codes the page filters on."""
    f = []
    o, a, mv = r.get('opp') or {}, r.get('ma') or {}, r.get('move') or {}
    if o.get('side') in ('buy', 'short'):
        f.append(o['side'])
    above = a.get('d200') if fin(a.get('d200')) else a.get('gap40')
    if fin(above):
        f.append('above200' if above > 0 else 'below200')
    x = a.get('x50_200')
    if isinstance(x, list) and len(x) == 3 and fin(x[2]) and x[2] <= RECENT_CROSS:
        f.append('golden' if x[1] > 0 else 'death')
    if r.get('hi'):
        f.append('ath' if r['hi'].get('ath') else 'high')
    if r.get('lo'):
        f.append({'atl': 'atl', '52w': 'low52', '3m': 'low3m'}[r['lo']['reg']])
    if r.get('rg'):
        f.append(r['rg']['reg'])
    if fin(mv.get('pct')):
        if mv['pct'] >= BIG_MOVE:
            f.append('bigup')
        elif mv['pct'] <= 100 - BIG_MOVE:
            f.append('bigdown')
    g = a.get('guid_last')
    if isinstance(g, list) and len(g) == 2 and a.get('guid') is not None and (asof is None or recent(g[0], asof, GUIDE_DAYS)):
        f.append({'raised': 'raised', 'lowered': 'lowered', 'withdrawn': 'lowered'}.get(g[1], 'guided'))
    if fin(a.get('hd_pct')):
        if a['hd_pct'] >= 0.9:
            f.append('far_above')
        elif a['hd_pct'] <= 0.1:
            f.append('far_below')
    od = r.get('odds') or {}
    if fin(od.get('sp500_12m')) and od['sp500_12m'] >= 0.1 and 'sp500' not in (r.get('ix') or []):
        f.append('sp500_cand')
    if fin(od.get('divcut_12m')) and od['divcut_12m'] >= 0.2:
        f.append('divcut')
    return f


def rows_now(sources, idx, comp_now, asof=None):
    opp = opportunity_rows(sources.get('opportunity'))
    odd, mar, rrg = odds_rows(sources.get('odds_stocks')), ma_rows(sources.get('ma_rows')), rrg_rows(sources.get('rrg_companies'))
    mov, his, los, rgs = move_rows(sources.get('moves')), highs_rows(sources.get('highs')), lows_rows(sources.get('lows')), ranges_rows(sources.get('ranges'))
    names = move_names(sources.get('moves'))
    rows = []
    for t, o in opp.items():
        n, sec = o.pop('n'), o.pop('s')
        r = {'t': t, 'n': names.get(t) or n, 's': sec, 'ix': idx.get(t) or [], 'opp': {k: v for k, v in o.items() if v is not None}}
        for key, src in (('odds', odd), ('ma', mar), ('rrg', rrg), ('move', mov), ('hi', his), ('lo', los), ('rg', rgs)):
            v = src.get(t)
            if v:
                r[key] = {k: x for k, x in v.items() if x is not None}
        c = comp_now.get(t)
        if c:
            r.update({'score': c['score'], 'tenth': c['tenth'], 'p_beat': c['p_beat'], 'parts': c['parts']})
        r['f'] = flags_of(r, asof)
        rows.append(r)
    rows.sort(key=lambda r: -(r.get('score') if fin(r.get('score')) else -1))
    return rows


def pack(rows):
    """Each section of each row as a list in a shared key order (doc['cols']): the key names once, not once a row."""
    cols = {}
    for sec in SECTIONS:
        keys = []
        for r in rows:
            for k in r.get(sec) or {}:
                if k not in keys:
                    keys.append(k)
        cols[sec] = keys
    out = []
    for r in rows:
        p = {k: v for k, v in r.items() if k not in SECTIONS}
        for sec in SECTIONS:
            if r.get(sec):
                p[sec] = [r[sec].get(k) for k in cols[sec]]
        out.append(p)
    return cols, out


# ------------------------------------------------------------------ the scoreboard
def verdict_skill(s):
    return None if not fin(s) else 'useful' if s >= 0.02 else 'small' if s >= 0.005 else 'none'


def verdict_rank(ic, net):
    if not ic or not fin(ic.get('mean')):
        return None
    if ic['mean'] <= 0:
        return 'none'
    if net and fin(net.get('mean')) and net['mean'] > 0 and fin(net.get('t')) and net['t'] >= 2:
        return 'pays'
    return 'ranks' if fin(ic.get('t')) and ic['t'] >= 2 else 'weak'


def scoreboard(sources, comp):
    """Every model's out-of-sample record, as each publishes it, side by side: what it answers, the measure, a verdict."""
    out = []
    o = sources.get('opportunity') or {}
    for hk, c in (o.get('cards') or {}).items():
        up = c.get('up') or {}
        out.append({'key': f'opp:{hk}', 'group': 'Opportunity', 'model': f"Higher in {({'1w': '1 week', '1m': '1 month', '3m': '3 months'}).get(hk, hk)}", 'kind': 'probability',
                    'skill': r_(up.get('brier_skill'), 4), 'auc': r_(up.get('auc'), 3), 'ic': r_(c.get('ic_mean'), 4), 'ic_t': r_(c.get('ic_t'), 1),
                    'flags': {k: bool((c.get(k) or {}).get('flag_ok')) for k in ('buy', 'short')}, 'years': c.get('oos_years'),
                    'verdict': verdict_skill(up.get('brier_skill'))})
    od = sources.get('odds') or {}
    names = {'dn10_4': 'Touches −10% within 4 weeks', 'up10_4': 'Touches +10% within 4 weeks', 'dn20_13': 'Touches −20% within 13 weeks',
             'up20_13': 'Touches +20% within 13 weeks', 'beat13': 'Beats SPY over 13 weeks', 'beat52': 'Beats SPY over 52 weeks',
             'sp500_12m': 'Joins the S&P 500 within 12 months', 'divcut_12m': 'Cuts its dividend within 12 months'}
    for k, m in (od.get('models') or {}).items():
        cd = m.get('card') or {}
        out.append({'key': f'odds:{k}', 'group': 'Odds', 'model': names.get(k, k), 'kind': 'probability', 'skill': r_(cd.get('skill'), 4), 'auc': r_(cd.get('auc'), 3),
                    'base': r_(cd.get('base'), 4), 'n': cd.get('n'), 'verdict': verdict_skill(cd.get('skill'))})
    ma = (sources.get('ma') or {}).get('scores') or {}
    names_ma = {'ma': 'Moving averages alone', 'hybrid': 'Moving averages + fundamentals + guidance', 'ma_macro': 'Moving averages × macro',
                'ma_time': 'Moving averages + the calendar', 'ma_dist': 'Moving averages + distance to the line'}
    for h in ('13', '26'):
        for k, nm in names_ma.items():
            s = ((ma.get('models') or {}).get(h) or {}).get(k)
            if s:
                p0 = next(iter(s))
                out.append({'key': f'ma:{k}:{h}', 'group': 'Moving averages+', 'model': f'{nm}, {h} weeks', 'kind': 'ranking', 'ic': r_((s[p0].get('ic') or {}).get('mean'), 4),
                            'ic_t': r_((s[p0].get('ic') or {}).get('t'), 1), 'net': r_((s[p0].get('net') or {}).get('mean'), 4), 'net_t': r_((s[p0].get('net') or {}).get('t'), 1),
                            'period': p0, 'verdict': verdict_rank(s[p0].get('ic'), s[p0].get('net'))})
    rh = ((sources.get('rrg') or {}).get('panels') or {}).get('companies') or {}
    for h in ('13', '4', '1'):
        sc = (rh.get('scores') or {}).get(h) or {}
        ic = (sc.get('ic') or {}).get('hybrid') or {}
        if ic:
            bw = sc.get('best_minus_worst') or {}
            out.append({'key': f'rrg:{h}', 'group': 'Hybrid RRG', 'model': f"Hybrid RRG, {h} week{'' if h == '1' else 's'}", 'kind': 'ranking', 'ic': r_(ic.get('ic'), 4), 'ic_t': r_(ic.get('t'), 1),
                        'net': r_(bw.get('mean'), 4), 'net_t': r_(bw.get('t'), 1),
                        'verdict': verdict_rank({'mean': ic.get('ic'), 't': ic.get('t')}, {'mean': bw.get('mean'), 't': bw.get('t')})})
        bs = sc.get('beat_spy') or {}
        if h == '13' and bs:
            out.append({'key': 'rrg:beat13', 'group': 'Hybrid RRG', 'model': 'Its chance of beating SPY, 13 weeks', 'kind': 'probability', 'skill': r_(bs.get('brier_skill'), 4),
                        'base': r_(bs.get('base_rate'), 4), 'verdict': verdict_skill(bs.get('brier_skill'))})
    if comp:
        for k, label in (('score_all', 'Combined score (these models, weighted by their records)'), ('equal', 'The same, equal weights (a check)')):
            s = comp['tests'].get(k) or {}
            p0 = next(iter(s)) if s else None
            if p0:
                g = lambda m, f: r_(((s[p0].get(m) or {}).get(f)), 4 if f == 'mean' else 1)
                out.append({'key': f'combined:{k}', 'group': 'Combined', 'model': label, 'kind': 'ranking', 'ic': g('ic', 'mean'), 'ic_t': g('ic', 't'), 'net': g('net', 'mean'),
                            'net_t': g('net', 't'), 'top': g('top_spy', 'mean'), 'top_t': g('top_spy', 't'), 'top_all': g('top_all', 'mean'),
                            'top_all_t': g('top_all', 't'), 'bottom_all': g('bottom_all', 'mean'), 'bottom_all_t': g('bottom_all', 't'), 'period': p0,
                            'verdict': verdict_rank(s[p0].get('ic'), s[p0].get('net'))})
        cal = comp.get('calibration') or {}
        if cal:
            out.append({'key': 'combined:p', 'group': 'Combined', 'model': 'Its probability of beating SPY over 13 weeks', 'kind': 'probability', 'skill': cal.get('skill'),
                        'base': cal.get('base_rate'), 'verdict': verdict_skill(cal.get('skill'))})
    for k, g, what in (('hist:regimes', 'Highs, lows and ranges', 'what followed the 250 most similar days of other companies'),
                       ('hist:moves', 'Move odds', "what followed the company's own similar days")):
        out.append({'key': k, 'group': g, 'model': what, 'kind': 'history', 'verdict': 'history'})
    return out


# ------------------------------------------------------------------ ledger
def ledger_update(book, bits, rows):
    days, t, ids, S = bits['days'], bits['t'], bits['ids'], bits['S']
    asof = str(days[t])
    by = {r['t']: r for r in rows}
    dv = np.nan_to_num(bits['C'][:, t] * np.nan_to_num(bits['V'][:, max(0, t - 12):t + 1]).mean(1), nan=-1)
    have = [i for i in range(len(ids)) if np.isfinite(S[i, t])]
    top = set(sorted(have, key=lambda i: -dv[i])[:LEDGER_MAX])
    keep = [i for i in have if i in top or 'sp500' in ((by.get(ids[i]) or {}).get('ix') or [])]
    if keep:
        FB.freeze(book, f'scan:{H}', asof, asof, {'ids': [ids[i] for i in keep], 'score': [r_(100 * float(S[i, t]), 1) for i in keep],
                                                  'p_beat': [(by.get(ids[i]) or {}).get('p_beat') for i in keep],
                                                  'parts': {k: [r_(float(p[i, t]), 3) if np.isfinite(p[i, t]) else None for i in keep] for k, p in bits['pcts'].items()}},
                  meta={'model': f'opportunity_scan v{VERSION}'})
    ix = {k: i for i, k in enumerate(ids)}
    for key, e in FB.entries(book, f'scan:{H}', resolved=False):
        k0 = int(np.searchsorted(days, np.datetime64(e['asof'])))
        if k0 >= len(days) or str(days[k0]) != e['asof'] or k0 + H > len(days) - 1:
            continue
        out = []
        for k in e['forecast']['ids']:
            i = ix.get(k)
            s = bits['rel'][i, k0 + 1:k0 + H + 1] if i is not None else None
            out.append(r_(float(s.sum()), 5) if s is not None and np.isfinite(s).all() else None)
        FB.resolve(book, f'scan:{H}', key, {'rel': out})


def ledger_scores(book):
    ents = FB.entries(book, f'scan:{H}', resolved=True)
    ics, spreads, bs, bb = [], [], [], []
    for _, e in ents:
        f, y = e['forecast'], (e['actual'] or {}).get('rel') or []
        v = [(a, p, c) for a, p, c in zip(f.get('score') or [], f.get('p_beat') or [], y) if fin(a) and fin(c)]
        if len(v) < 20:
            continue
        a = np.array([x[0] for x in v]); c = np.array([x[2] for x in v])
        ics.append(float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(c)))[0, 1]))
        q = np.quantile(a, [0.1, 0.9])
        spreads.append(float(np.expm1(c[a >= q[1]]).mean() - np.expm1(c[a <= q[0]]).mean()))
        pv = [(x[1], x[2] > 0) for x in v if fin(x[1])]
        if pv:
            bs.append(float(np.mean([(p - y_) ** 2 for p, y_ in pv])))
            rate = np.mean([y_ for _, y_ in pv])
            bb.append(float(np.mean([(rate - y_) ** 2 for _, y_ in pv])))
    return {'resolved_weeks': len(ics), 'pending_weeks': len(FB.entries(book, f'scan:{H}', resolved=False)), 'ic': r_(np.mean(ics)) if ics else None,
            'top_minus_bottom_tenth': r_(np.mean(spreads)) if spreads else None, 'brier': r_(np.mean(bs), 5) if bs else None,
            'brier_same_week_rate': r_(np.mean(bb), 5) if bb else None}


# ------------------------------------------------------------------ everything
def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def daily_brief(ma):
    """What being above the 200-day average and a 50/200-day golden cross have paid (Moving averages+, daily closes)."""
    D = ((((ma or {}).get('scores') or {}).get('ndays') or {}).get('daily')) or {}
    if not D:
        return None
    p0 = (D.get('periods') or [None])[0]
    pick = lambda h, k: ((((D.get(h) or {}).get(k) or {}).get('periods') or {}).get(p0) or {}).get('net')
    return {'period': p0, 'from': D.get('from'), **{f'{k}:{h}': pick(h, k) for h in ('13', '26') for k in ('above:200', 'above:20', 'cross:50/200')}}


def market_brief(src):
    od = (src.get('odds') or {}).get('market') or {}
    mi = ((((src.get('ma') or {}).get('scores') or {}).get('macro') or {}).get('index')) or {}
    return {'recession_12m': (od.get('recession') or {}).get('p'), 'stress': (od.get('regime') or {}).get('p_stress'),
            'macro_now': mi.get('now'), 'spy': ((mi.get('funds') or {}).get('SPY') or {}).get('now'), 'rules': mi.get('rules')}


def build(public, oos=None, moves=None, members=None, ledger=None, verbose=True):
    t0 = dt.datetime.now()
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    pub = Path(public)
    src = {'opportunity': read_json(pub / 'opportunity-stocks.json'), 'odds': read_json(pub / 'odds.json'), 'odds_stocks': read_json(pub / 'odds-stocks.json'),
           'ma': read_json(pub / 'ma-hybrid.json'), 'ma_rows': read_json(pub / 'ma-hybrid-rows.json'), 'rrg': read_json(pub / 'rrg-hybrid.json'),
           'rrg_companies': read_json(pub / 'rrg-hybrid-companies.json'), 'market_models': read_json(pub / 'market-models.json')}
    if moves:
        for k, f in (('moves', 'index.json'), ('highs', 'highs.json'), ('lows', 'lows.json'), ('ranges', 'ranges.json')):
            src[k] = read_json(Path(moves) / f)
    if not src['opportunity']:
        log('scan: no opportunity-stocks.json — nothing to scan')
        return None
    mem = read_json(members)
    with warnings.catch_warnings(), np.errstate(all='ignore'):
        warnings.simplefilter('ignore', RuntimeWarning)
        res = composite(public, oos, log)
    comp, now, bits = res if res else (None, {}, None)
    rows = rows_now(src, index_of(mem), now, ((src.get('moves') or {}).get('as_of')) or src['opportunity'].get('asof'))
    asof = {k: (v or {}).get('asof') or (v or {}).get('as_of') or (v or {}).get('generated_at') for k, v in src.items() if v}
    ma_dist = ((src.get('ma') or {}).get('scores') or {}).get('distance') or {}
    dk = '0.5|0.05'
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'version': VERSION, 'asof': (comp or {}).get('asof') or src['opportunity'].get('asof'),
           'sources': asof, 'indexes': {k: v for k, v in ((mem or {}).get('indexes') or {}).items()}, 'composite': comp,
           'scoreboard': scoreboard({'opportunity': src['opportunity'], 'odds': src['odds'], 'ma': src['ma'], 'rrg': src['rrg']}, comp),
           'history': {'ma_bands': {h: {k: ((ma_dist.get('by') or {}).get(dk) or {}).get(h, {}).get(k) for k in ('n', 'd', 'back', 'q50', 'ret', 'ret_t')}
                                    for h in ('13', '26')} if ma_dist.get('by') else None,
                       'ma_regression': ma_dist.get('regression'), 'daily': daily_brief(src.get('ma'))},
           'market': market_brief(src),
           'counts': {'rows': len(rows), 'scored': sum(1 for r in rows if fin(r.get('score'))),
                      **{k: sum(1 for r in rows if k in r['ix']) for k in INDEX_ORDER}},
           'rules': {'recent_cross_days': RECENT_CROSS, 'big_move_pct': BIG_MOVE, 'guidance_days': GUIDE_DAYS, 'horizon_weeks': H}, 'note': __doc__.split('\n\n')[0]}
    if ledger and bits:
        book = FB.load(ledger)
        ledger_update(book, bits, rows)
        FB.save(ledger, book)
        doc['ledger'] = ledger_scores(book)
    doc['cols'], doc['rows'] = pack(rows)
    doc['cols']['parts'] = [k for k, _, _ in COMPONENTS]
    doc['seconds'] = round((dt.datetime.now() - t0).total_seconds(), 1)
    (pub / 'opportunity-scan.json').write_text(json.dumps(clean(doc), separators=(',', ':')), encoding='utf-8')
    log(f"scan: {len(rows)} stocks, {doc['counts']['scored']} with a combined score, written in {doc['seconds']}s")
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--public', required=True, help="rotation-history's public/: opportunity-stocks.json, odds*.json, ma-hybrid*.json, rrg-hybrid*.json")
    ap.add_argument('--oos', help='hist/cache/oos/: the models\' walk-forward forecast histories (app/oos_store.py)')
    ap.add_argument('--moves', help="research-paths' public/moves/: index.json, highs.json, lows.json, ranges.json")
    ap.add_argument('--members', help='members.json (app/index_members.py): index memberships')
    ap.add_argument('--ledger')
    a = ap.parse_args()
    build(a.public, a.oos, a.moves, a.members, a.ledger)


if __name__ == '__main__':
    main()
