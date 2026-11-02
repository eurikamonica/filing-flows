"""Peer tiers for the Fair value page (app/valuation.py): who a company is compared with, in three tiers beside the
plain median of its SIC group, the business-model map that prices each revenue segment, and the published peer list.

  Tier 1  broad      the narrowest SIC group with six or more peers (valuation.peer_range), plain and weighted
                     (app/peer_weights.py: market value, revenue, trading value, recency).
  Tier 2  matched    the same industry narrowed to companies that look like this one: a window ladder, tight → medium →
                     wide, the first giving six or more peers —
                       tight   same 3-digit SIC, the same stage, revenue ¼–4×, revenue growth ±10 points, operating margin ±10
                       medium  same 3-digit SIC, profitable or not alike, revenue 1/10–10×, growth ±15, margin ±15
                       wide    same 2-digit SIC, profitable or not alike, revenue 1/30–30×, growth ±25, margin ±25
           adjusted  the fair multiple for its own growth (and, for EV/Sales, its operating margin) on a fit across the
                     tier-1 group: ln(multiple) = a + b × growth (+ c × margin), ridge-shrunk, the company's own figures held
                     inside the group's 5th–95th percentiles; ± the fit's residual spread for the middle half.
  Tier 3  selected   comparable companies chosen by business model, each with its reason, in config/peer-map.json (per
                     company for the whole-company multiples, per business-model tag for segments); at least three on file.
  Segments  each revenue segment's business-model tag: the company's own override, then the tags' patterns in order; a
            generic name (Services, Products, Other …) is priced like the company itself rather than guessed from a word.
  Peer list public/peers-list.json: every company's figures the comparisons use (SIC, stage, market value, EV, revenue,
            growth, margin, trading value, P/E, EV/EBITDA, EV/Sales, P/FFO, their quarterly P/E and EV/Sales since 2022), so
            every median can be checked company by company and re-filtered on the page.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import peer_weights as PW

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'peer-map.json'
GENERIC = re.compile(r'^\s*(net sales\s*[–-]\s*)?(services?|products?|product sales|product revenues?|other|others|other revenues?|rev_more|'
                     r'services? and other|product and service,? other|sales|revenues?|basic|financing|subscriptions? and services)\s*$', re.I)
MIN_PEERS, MIN_SELECTED, MIN_FIT = 6, 3, 12
MIN_R2 = 0.10           # a fit explaining less than a tenth of the spread is shown, not used as a value
WINDOWS = ({'key': 'tight', 'sic': 3, 'stage': 'same', 'size': 4.0, 'growth': 0.10, 'margin': 0.10},
           {'key': 'medium', 'sic': 3, 'stage': 'profit', 'size': 10.0, 'growth': 0.15, 'margin': 0.15},
           {'key': 'wide', 'sic': 2, 'stage': 'profit', 'size': 30.0, 'growth': 0.25, 'margin': 0.25})
RIDGE = 0.15             # ridge penalty per observation on the standardized slopes (shrinks them about 13%)
FIT_X = {'pe': ('growth',), 'ev_ebitda': ('growth',), 'ev_sales': ('growth', 'margin'), 'p_ffo': ('growth',)}
ROW_FIELDS = ['cik', 'ticker', 'name', 'sic', 'sector', 'kind', 'stage', 'mcap', 'ev', 'revenue', 'growth', 'margin', 'dvol', 'pe', 'ev_ebitda', 'ev_sales', 'p_ffo',
              'date', 'pe_hist', 'evs_hist']


def fin(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def _r(v, d=4):
    return round(v, d) if fin(v) else None


# ---------------------------------------------------------------- the business-model map
def load_map(path=None):
    """The map (config/peer-map.json) with its patterns compiled; an empty map when the file is missing."""
    try:
        M = json.loads(Path(path or CONFIG).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        M = {}
    M.setdefault('tags', {})
    M.setdefault('order', list(M['tags']))
    M.setdefault('overrides', {})
    M.setdefault('companies', {})
    for t in M['tags'].values():
        t['_rx'] = [re.compile(p, re.I) for p in t.get('patterns') or []]
    return M


def segment_tag(M, ticker, name):
    """(tag or None, how): the company's own override, a generic name (priced like the company), the first matching tag."""
    nm = str(name or '').strip()
    ov = {k.lower(): v for k, v in (M['overrides'].get(str(ticker or '').upper()) or {}).items()}
    if nm.lower() in ov and ov[nm.lower()] in M['tags']:
        return ov[nm.lower()], 'override'
    if GENERIC.match(nm):
        return None, 'generic'
    for key in M['order']:
        t = M['tags'].get(key) or {}
        for rx in t.get('_rx') or []:
            if rx.search(nm):
                return key, f'rule “{rx.pattern}”'
    return None, 'no rule'


def tag_pool(M, tag, R, tick2cik):
    """The ciks of a tag's broad pool: SIC prefixes, or its comps when it has none."""
    t = M['tags'].get(tag) or {}
    groups = [str(g) for g in t.get('groups') or []]
    if groups:
        return [c for c, r in R.items() if any(str(r.get('sic') or '').startswith(g) for g in groups)]
    return [tick2cik[x[0]] for x in t.get('comps') or [] if x[0] in tick2cik]


def comps(entries, R, tick2cik, metric, own):
    """([(cik, ticker, reason)] on file with the multiple, [tickers missing or without it])."""
    have, missing = [], []
    for e in entries or []:
        t, why = (e[0], e[1] if len(e) > 1 else '') if isinstance(e, (list, tuple)) else (e, '')
        c = tick2cik.get(str(t).upper())
        if c and c != own and fin((R.get(c) or {}).get(metric)):
            have.append((c, t, why))
        else:
            missing.append(t)
    return have, missing


def quartiles(vals):
    vals = [v for v in vals if fin(v)]
    if not vals:
        return None, None, None
    w = [1.0] * len(vals)
    return PW.wquantile(vals, w, 0.25), PW.wquantile(vals, w, 0.5), PW.wquantile(vals, w, 0.75)


# ---------------------------------------------------------------- tier 2: matched
def _fits(o, r, w):
    """None if r passes window w for the company o, else why not."""
    so, sr = str(o.get('sic') or ''), str(r.get('sic') or '')
    if len(so) < w['sic'] or sr[:w['sic']] != so[:w['sic']]:
        return f'outside SIC {so[:w["sic"]]}'
    if w['stage'] == 'same' and o.get('stage') and r.get('stage') != o.get('stage'):
        return 'a different stage'
    if w['stage'] == 'profit' and (fin(o.get('margin')) and fin(r.get('margin'))) and ((o['margin'] > 0) != (r['margin'] > 0)):
        return 'profitable vs not'
    ro, rr = o.get('revenue'), r.get('revenue')
    if fin(ro) and ro > 0:
        if not (fin(rr) and rr > 0) or not (ro / w['size'] <= rr <= ro * w['size']):
            return 'size outside the window'
    for k in ('growth', 'margin'):
        if fin(o.get(k)):
            if not fin(r.get(k)):
                return f'no {k} on file'
            if abs(r[k] - o[k]) > w[k] + 1e-12:
                return f'{k} outside ±{w[k] * 100:.0f} points'
    return None


def matched(R, own, metric):
    """Tier 2: the first window of the ladder with six or more peers that have the multiple."""
    o = R.get(own)
    if not o:
        return None
    tried = []
    for w in WINDOWS:
        mem = [c for c, r in R.items() if c != own and fin(r.get(metric)) and _fits(o, r, w) is None]
        tried.append([w['key'], len(mem)])
        if len(mem) >= MIN_PEERS:
            p25, p50, p75 = quartiles([R[c][metric] for c in mem])
            return {'window': w['key'], 'criteria': dict(w), 'members': mem, 'n': len(mem), 'p25': p25, 'p50': p50, 'p75': p75, 'tried': tried}
    return {'window': None, 'tried': tried, 'n': 0}


def why_not(R, own, c, w):
    """Why a company is out of window w (None: in)."""
    return _fits(R[own], R[c], w)


# ---------------------------------------------------------------- the adjusted multiple: a fit across the group
def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            return None
        M[i], M[p] = M[p], M[i]
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                M[r] = [a - f * c for a, c in zip(M[r], M[i])]
    return [M[i][n] / M[i][i] for i in range(n)]


def _pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def adjusted(R, own, metric, ciks):
    """The fair multiple for the company's own growth (and margin) on a ridge fit of ln(multiple) across ciks."""
    o = R.get(own) or {}
    xk = FIT_X.get(metric, ('growth',))
    if not all(fin(o.get(k)) for k in xk):
        return None
    pts = [(c, [R[c][k] for k in xk], math.log(R[c][metric])) for c in ciks
           if c != own and fin((R.get(c) or {}).get(metric)) and R[c][metric] > 0 and all(fin(R[c].get(k)) for k in xk)]
    pts = [(c, [min(1.0, max(-0.5, x)) if k == 'growth' else min(0.6, max(-1.0, x)) for k, x in zip(xk, xs)], y) for c, xs, y in pts]
    n = len(pts)
    if n < MIN_FIT:
        return None
    mu = [sum(p[1][j] for p in pts) / n for j in range(len(xk))]
    sd = [math.sqrt(sum((p[1][j] - mu[j]) ** 2 for p in pts) / n) or 1.0 for j in range(len(xk))]
    Z = [[(p[1][j] - mu[j]) / sd[j] for j in range(len(xk))] for p in pts]
    ys = [p[2] for p in pts]
    ym = sum(ys) / n
    k = len(xk)
    A = [[sum(z[i] * z[j] for z in Z) + (RIDGE * n if i == j else 0.0) for j in range(k)] for i in range(k)]
    b = [sum(z[i] * (y - ym) for z, y in zip(Z, ys)) for i in range(k)]
    beta = _solve(A, b)
    if beta is None:
        return None
    pred = [ym + sum(beta[j] * z[j] for j in range(k)) for z in Z]
    res = [y - p for y, p in zip(ys, pred)]
    s = math.sqrt(sum(e * e for e in res) / max(1, n - k - 1))
    tot = sum((y - ym) ** 2 for y in ys)
    xo, clamped = [], False
    for j, key in enumerate(xk):
        lo, hi = _pct([p[1][j] for p in pts], 0.05), _pct([p[1][j] for p in pts], 0.95)
        v = o[key]
        if v < lo or v > hi:
            clamped = True
        xo.append(min(hi, max(lo, v)))
    yo = ym + sum(beta[j] * (xo[j] - mu[j]) / sd[j] for j in range(k))
    slopes = {key: beta[j] / sd[j] for j, key in enumerate(xk)}     # per unit (1.0 = 100 points) of the raw figure
    return {'p50': math.exp(yo), 'p25': math.exp(yo - 0.6745 * s), 'p75': math.exp(yo + 0.6745 * s), 'n': n, 'r2': 1 - sum(e * e for e in res) / tot if tot else None,
            'per10': {key: math.exp(0.1 * v) - 1 for key, v in slopes.items()}, 'x': {key: _r(o[key]) for key in xk}, 'used': {key: _r(v) for key, v in zip(xk, xo)},
            'clamped': clamped, 'resid_sd': s, 'members': [p[0] for p in pts]}


# ---------------------------------------------------------------- tier 3: selected
def selected(M, R, tick2cik, own, ticker, metric, entries=None):
    """Tier 3: the selected comps for a company (config 'companies') or a tag's comps (entries); None under three."""
    entries = entries if entries is not None else ((M['companies'].get(str(ticker or '').upper()) or {}).get('comps') or [])
    if not entries:
        return None
    have, missing = comps(entries, R, tick2cik, metric, own)
    out = {'comps': [[t, why, _r(R[c][metric], 3)] for c, t, why in have], 'missing': missing, 'members': [c for c, _, _ in have], 'n': len(have)}
    if len(have) >= MIN_SELECTED:
        out['p25'], out['p50'], out['p75'] = quartiles([R[c][metric] for c, _, _ in have])
    return out


# ---------------------------------------------------------------- the published peer list
def rows_doc(R, hist, today):
    """public/peers-list.json: one row per company (ROW_FIELDS); the quarterly P/E and EV/Sales aligned to 'ages' (years
    before today of each quarter origin, the same calendar quarters for every company; null where not on file)."""
    ages = sorted({round(a, 3) for m in ('pe', 'ev_sales') for xs in (hist.get(m) or {}).values() for _, a in xs if 0 < a <= PW.MAX_AGE})
    pos = {a: i for i, a in enumerate(ages)}

    def aligned(xs):
        out = [None] * len(ages)
        for v, a in xs or []:
            i = pos.get(round(a, 3))
            if i is not None and fin(v):
                out[i] = round(v, 2)
        return out if any(x is not None for x in out) else None
    rows = []
    for c, r in R.items():
        rows.append([int(c) if str(c).isdigit() else c, r.get('ticker'), r.get('name'), r.get('sic'), r.get('sector'), r.get('kind'), r.get('stage'),
                     _r(r.get('mcap'), -6), _r(r.get('ev'), -6), _r(r.get('revenue'), -5), _r(r.get('growth')), _r(r.get('margin')), _r(r.get('dvol'), -4),
                     _r(r.get('pe'), 2), _r(r.get('ev_ebitda'), 2), _r(r.get('ev_sales'), 3), _r(r.get('p_ffo'), 2), r.get('date'),
                     aligned((hist.get('pe') or {}).get(c)), aligned((hist.get('ev_sales') or {}).get(c))])
    rows.sort(key=lambda x: -(x[7] or 0))
    return {'fields': ROW_FIELDS, 'ages': ages, 'rows': rows, 'as_of': str(today), 'half_life': PW.HALF_LIFE, 'cap': PW.CAP, 'windows': list(WINDOWS),
            'note': 'Every company the peer comparisons can use, with the figures they use: SIC industry, stage, market value, enterprise value, '
                    'revenue (four quarters), revenue growth (four quarters vs the four before), operating margin, trading value (median daily close × '
                    'volume, 63 sessions), the multiples today (P/E 0–200×, EV/EBITDA 0–100×, EV/Sales 0–50×, else left out) and P/E and EV/Sales at '
                    'each quarter since 2022 (aligned to ages, in years before today).'}
