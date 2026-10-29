"""More company quality research for app/quality.py: manipulation risk, earnings persistence and stability, Quality
Minus Junk, and the quality of taxes, goodwill and non-GAAP earnings. Pure functions over the fiscal-year records of
quality.fiscal_years() (oldest first, figures in dollars); every result keeps its parts so a reader can check it.

  dechow(cur, prev, prev2)   Dechow, Ge, Larson & Sloan (2011) F-score, model 1: the predicted probability of a
                             misstatement (from SEC enforcement cases) over the 0.37% base rate; RSST accruals, change
                             in receivables and inventory, soft assets, change in cash sales, change in ROA, securities
                             issued. 1 = the base rate; above 1.85 substantial, above 2.45 high risk.
  cscore(cur, prev)          Montier (2008) C-score: six warning signs of "cooking the books" (0–6).
  jones(obs)                 Modified Jones (Dechow, Sloan & Sweeney 1995) discretionary accruals, performance-matched
                             as Kothari, Leone & Wasley (2005) do: total accruals regressed on 1/assets, revenue change
                             less receivables change, PP&E and ROA, by sector and year; the residual is the part the
                             model cannot explain.
  stability(recs, quarters)  how steady profit, cash flow and margins have been; earnings smoothness (Leuz et al. 2003).
  persistence(obs)           per sector: next year's ROA on this year's cash and accrual parts (Sloan 1996).
  qmj_inputs / qmj_scores    Asness, Frazzini & Pedersen (2019) Quality Minus Junk: profitability, growth, safety and
                             payout, each the mean of rank z-scores, then z-scored again.
  taxes(recs)                cash taxes paid against the tax expense, three-year sums.
  goodwill(recs, mcap)       goodwill and other intangibles against assets and equity, impairments, warning signs.
  nongaap(street, quarters, shares)  the "street" (adjusted) earnings per share analysts compare with, against GAAP.

Research screens, not accusations and not investment advice.
"""
import math

DECHOW_BASE = 0.0037                     # the unconditional misstatement rate of the Dechow et al. sample


def _div(a, b):
    try:
        return None if a is None or b in (None, 0) else a / b
    except (TypeError, ZeroDivisionError):
        return None


def _r(v, d=4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, d)


def _avg(a, b):
    return (a + b) / 2 if a and b else (a or b or None)


def _sd(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    if len(xs) < 3:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _debt_parts(r):
    """(current debt, long-term debt beyond a year) from the tags a company uses."""
    std = r.get('ltd_c') if r.get('ltd_c') is not None else r.get('std')
    std = std or 0
    if r.get('ltd_nc') is not None:
        lt = r['ltd_nc']
    elif r.get('ltd') is not None:
        lt = max(r['ltd'] - std, 0) if r.get('ltd_c') is not None else r['ltd']
    else:
        lt = 0
    return std, lt


# ---------------------------------------------------------------- manipulation risk
def dechow(cur, prev, prev2=None):
    need = ('assets', 'ca', 'cl', 'liab', 'ar', 'rev', 'ni', 'ppe')
    if any(cur.get(k) is None for k in need) or any(prev.get(k) is None for k in need):
        return None
    a0, a1 = cur['assets'], prev['assets']
    if not a0 or not a1 or a0 <= 0 or a1 <= 0 or not cur['rev'] or not prev['rev']:
        return None
    assumed = []

    def parts(r):
        std, lt = _debt_parts(r)
        cash = r.get('cash') or 0
        wc = (r['ca'] - cash) - (r['cl'] - std)
        nco = (r['assets'] - r['ca']) - (r['liab'] - r['cl'] - lt)
        fin = -(lt + std)
        return wc, nco, fin
    w0, n0, f0 = parts(cur)
    w1, n1, f1 = parts(prev)
    avg = (a0 + a1) / 2
    rsst = ((w0 - w1) + (n0 - n1) + (f0 - f1)) / avg
    ch_rec = (cur['ar'] - prev['ar']) / avg
    if cur.get('inv') is None or prev.get('inv') is None:
        ch_inv = 0.0
        assumed.append('inventory')
    else:
        ch_inv = (cur['inv'] - prev['inv']) / avg
    soft = (a0 - cur['ppe'] - (cur.get('cash') or 0)) / a0
    cs0 = cur['rev'] - (cur['ar'] - prev['ar'])
    if prev2 and prev2.get('ar') is not None:
        cs1 = prev['rev'] - (prev['ar'] - prev2['ar'])
    else:
        cs1 = prev['rev']
        assumed.append('cash sales a year earlier (revenue used)')
    ch_cs = cs0 / cs1 - 1 if cs1 and cs1 > 0 else None
    roa0 = cur['ni'] / avg
    roa1 = prev['ni'] / _avg(a1, (prev2 or {}).get('assets'))
    ch_roa = roa0 - roa1
    issued = (cur.get('issue') or 0) > 0 or (cur.get('debt_issue') or 0) > 0
    if cur.get('issue') is None and cur.get('debt_issue') is None:
        assumed.append('securities issued (not tagged: no)')
    if ch_cs is None:
        return None
    x = {'rsst_acc': rsst, 'ch_rec': ch_rec, 'ch_inv': ch_inv, 'soft_assets': soft, 'ch_cs': ch_cs, 'ch_roa': ch_roa, 'issue': 1.0 if issued else 0.0}
    w = {'rsst_acc': 0.790, 'ch_rec': 2.518, 'ch_inv': 1.191, 'soft_assets': 1.979, 'ch_cs': 0.171, 'ch_roa': -0.932, 'issue': 1.029}
    pv = -7.893 + sum(w[k] * v for k, v in x.items())
    p = 1 / (1 + math.exp(-pv))
    f = p / DECHOW_BASE
    band = 'high' if f > 2.45 else 'substantial' if f > 1.85 else 'above normal' if f > 1 else 'normal'
    return {'f': _r(f, 3), 'prob': _r(p, 5), 'band': band, 'x': {k: _r(v, 4) for k, v in x.items()}, 'w': w, 'assumed': assumed}


def cscore(cur, prev):
    """Montier's six signs; each None when a figure is missing. Score = signs present out of those that can be read."""
    def g(r, k):
        return r.get(k)

    def up(a, b):
        return None if a is None or b is None else a > b
    gap0 = None if g(cur, 'ni') is None or g(cur, 'ocf') is None else cur['ni'] - cur['ocf']
    gap1 = None if g(prev, 'ni') is None or g(prev, 'ocf') is None else prev['ni'] - prev['ocf']
    dso0, dso1 = _div(g(cur, 'ar'), g(cur, 'rev')), _div(g(prev, 'ar'), g(prev, 'rev'))
    cost0, cost1 = g(cur, 'cogs') or (cur['rev'] - cur['gp'] if cur.get('rev') and cur.get('gp') is not None else None), \
        g(prev, 'cogs') or (prev['rev'] - prev['gp'] if prev.get('rev') and prev.get('gp') is not None else None)
    dsi0, dsi1 = _div(g(cur, 'inv'), cost0), _div(g(prev, 'inv'), cost1)
    oca0, oca1 = _div(g(cur, 'oca'), g(cur, 'rev')), _div(g(prev, 'oca'), g(prev, 'rev'))
    dep0, dep1 = _div(g(cur, 'da'), g(cur, 'ppe')), _div(g(prev, 'da'), g(prev, 'ppe'))
    ag = _div(g(cur, 'assets'), g(prev, 'assets'))
    signs = [
        ('gap', 'Profit pulling away from operating cash flow', up(gap0, gap1), [gap1, gap0]),
        ('dso', 'Days sales outstanding up', up(dso0, dso1), [_r(dso1 and dso1 * 365, 1), _r(dso0 and dso0 * 365, 1)]),
        ('dsi', 'Days of inventory up', up(dsi0, dsi1), [_r(dsi1 and dsi1 * 365, 1), _r(dsi0 and dsi0 * 365, 1)]),
        ('oca', 'Other current assets up relative to revenue', up(oca0, oca1), [_r(oca1), _r(oca0)]),
        ('dep', 'Depreciation down relative to PP&E', None if dep0 is None or dep1 is None else dep0 < dep1, [_r(dep1), _r(dep0)]),
        ('ag', 'Total assets up more than 10% in a year', None if ag is None else ag > 1.10, _r(ag - 1 if ag else None)),
    ]
    n = sum(s[2] is not None for s in signs)
    if n < 4:
        return None
    return {'score': sum(bool(s[2]) for s in signs), 'n': n, 'signs': [{'key': k, 'label': l, 'on': v, 'detail': d} for k, l, v, d in signs]}


def _solve(A, b):
    """Gaussian elimination with partial pivoting; None when singular."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def ols_multi(X, y):
    """Least squares with an intercept: X rows of regressors → (coefficients with the intercept first, R²)."""
    rows = [[1.0] + list(x) for x in X]
    k = len(rows[0])
    if len(rows) < k + 3:
        return None, None
    XtX = [[sum(r[i] * r[j] for r in rows) for j in range(k)] for i in range(k)]
    Xty = [sum(r[i] * yy for r, yy in zip(rows, y)) for i in range(k)]
    beta = _solve(XtX, Xty)
    if beta is None:
        return None, None
    fit = [sum(b * v for b, v in zip(beta, r)) for r in rows]
    my = sum(y) / len(y)
    ss = sum((yy - my) ** 2 for yy in y)
    r2 = 1 - sum((yy - f) ** 2 for yy, f in zip(y, fit)) / ss if ss else None
    return beta, r2


def _winsor(vals, p=0.01):
    s = sorted(vals)
    lo, hi = s[int(p * (len(s) - 1))], s[int((1 - p) * (len(s) - 1))]
    return [min(max(v, lo), hi) for v in vals]


def jones_obs(recs):
    """One observation per fiscal year that has the year before: total accruals and the modified-Jones regressors."""
    out = []
    for i in range(1, len(recs)):
        c, p = recs[i], recs[i - 1]
        a1 = p.get('assets')
        # a company that was a shell a year before (assets a twentieth of today's) has no meaningful ratio
        if not a1 or a1 <= 0 or (c.get('assets') and a1 < 0.05 * c['assets']) or c.get('ni') is None or c.get('ocf') is None or c.get('rev') is None or p.get('rev') is None or c.get('ppe') is None:
            continue
        d_ar = (c['ar'] - p['ar']) if c.get('ar') is not None and p.get('ar') is not None else 0.0
        ta = (c['ni'] - c['ocf']) / a1
        if abs(ta) > 2:
            continue
        out.append({'end': c['end'], 'year': c['end'][:4], 'ta': ta, 'inv_a': 1e9 / a1,          # 1 / assets in $ billions
                    'drev': (c['rev'] - p['rev'] - d_ar) / a1, 'ppe': c['ppe'] / a1, 'roa': c['ni'] / a1, 'ar_tagged': c.get('ar') is not None})
    return out


def jones(obs, min_n=12):
    """obs: [{'key', 'group', 'ta', 'inv_a', 'drev', 'ppe', 'roa'}] → {key: {'da', 'na', 'group', 'n', 'r2', 'coef'}} — each
    group (sector and fiscal year) regressed on its own; variables winsorized at 1% and 99% for the fit."""
    groups = {}
    for o in obs:
        groups.setdefault(o['group'], []).append(o)
    res = {}
    for g, lst in groups.items():
        if len(lst) < min_n:
            continue
        cols = {k: _winsor([o.get(k, 0.0) for o in lst]) for k in ('ta', 'inv_a', 'drev', 'ppe', 'roa')}
        X = list(zip(cols['inv_a'], cols['drev'], cols['ppe'], cols['roa']))
        beta, r2 = ols_multi(X, cols['ta'])
        if beta is None:
            continue
        for o, x in zip(lst, X):                  # fitted on winsorized figures; the residual keeps the company's own accruals
            na = beta[0] + sum(b * v for b, v in zip(beta[1:], x))
            y = o['ta']
            res[o['key']] = {'da': _r(y - na, 4), 'na': _r(na, 4), 'ta': _r(y, 4), 'group': g, 'n': len(lst), 'r2': _r(r2, 3),
                             'coef': [_r(b, 5) for b in beta]}
    return res


# ---------------------------------------------------------------- persistence and stability
def stability(recs, quarters=None):
    """recs oldest first; quarters: [(period, {'rev', 'oi', 'gp', 'ni'})] consecutive calendar quarters, oldest first."""
    def per_a(r, k):                                  # a year with next to no assets (a shell) says nothing
        v = _div(r.get(k), r.get('assets'))
        return v if v is not None and r['assets'] > 0 and abs(v) <= 2 else None
    roa = [per_a(r, 'ni') for r in recs]
    cfoa = [per_a(r, 'ocf') for r in recs]
    gm = [_div(r.get('gp'), r.get('rev')) for r in recs]
    om = [_div(r.get('oi'), r.get('rev')) for r in recs]
    years = sum(1 for v in roa if v is not None)
    if years < 3:
        return None
    s_roa, s_cf = _sd(roa), _sd(cfoa)
    out = {'years': years, 'sd_roa': _r(s_roa), 'sd_cfoa': _r(s_cf), 'sd_gm': _r(_sd(gm)), 'sd_om': _r(_sd(om)),
           'smooth': _r(_div(s_roa, s_cf), 3) if s_cf and s_cf >= 0.005 else None, 'loss_years': sum(1 for r in recs if r.get('ni') is not None and r['ni'] < 0),
           'neg_ocf_years': sum(1 for r in recs if r.get('ocf') is not None and r['ocf'] < 0),
           'roa': [[r['end'], _r(v)] for r, v in zip(recs, roa) if v is not None],
           'cfoa': [[r['end'], _r(v)] for r, v in zip(recs, cfoa) if v is not None]}
    if quarters:
        ttm = []
        for i in range(3, len(quarters)):
            w = [f for _, f in quarters[i - 3:i + 1]]
            if all(f.get('rev') for f in w) and all(f.get('oi') is not None for f in w):
                ttm.append(sum(f['oi'] for f in w) / sum(f['rev'] for f in w))
        if len(ttm) >= 4:
            out['sd_ttm_om'] = _r(_sd(ttm))
            out['ttm_om'] = [_r(v) for v in ttm]
    return out


def persistence_obs(recs):
    """(cash ROA, accrual ROA, next year's ROA) pairs: Sloan's split of earnings into cash flow and accruals."""
    out = []
    for i in range(1, len(recs) - 1):
        p, c, n = recs[i - 1], recs[i], recs[i + 1]
        a = _avg(p.get('assets'), c.get('assets'))
        a_n = _avg(c.get('assets'), n.get('assets'))
        if not a or not a_n or c.get('ni') is None or c.get('ocf') is None or n.get('ni') is None:
            continue
        out.append((c['ocf'] / a, (c['ni'] - c['ocf']) / a, n['ni'] / a_n))
    return out


def persistence(obs, min_n=25):
    """obs: {group: [(cash ROA, accrual ROA, next ROA)]} → {group: {'a', 'b_cash', 'b_acc', 'b_roa', 'r2', 'n'}}: next year's
    ROA on this year's cash and accrual parts, and on ROA as a whole; accruals usually persist less (b_acc < b_cash)."""
    res = {}
    for g, lst in obs.items():
        if len(lst) < min_n:
            continue
        cash, acc, nxt = (_winsor([o[k] for o in lst]) for k in range(3))
        beta, r2 = ols_multi(list(zip(cash, acc)), nxt)
        one, r2b = ols_multi([(c + a,) for c, a in zip(cash, acc)], nxt)
        if beta is None or one is None:
            continue
        res[g] = {'a': _r(beta[0], 4), 'b_cash': _r(beta[1], 3), 'b_acc': _r(beta[2], 3), 'r2': _r(r2, 3),
                  'b_roa': _r(one[1], 3), 'r2_roa': _r(r2b, 3), 'n': len(lst)}
    return res


# ---------------------------------------------------------------- Quality Minus Junk
QMJ_PARTS = {
    'profitability': [('gpoa', 1), ('roe', 1), ('roa', 1), ('cfoa', 1), ('gmar', 1), ('acc', -1)],
    'growth': [('d_gpoa', 1), ('d_roe', 1), ('d_roa', 1), ('d_cfoa', 1), ('d_gmar', 1)],
    'safety': [('beta', -1), ('ivol', -1), ('lev', -1), ('evol', -1), ('z', 1)],
    'payout': [('eiss', -1), ('diss', -1), ('npop', 1)],
}


def qmj_inputs(recs, beta=None, ivol=None, z=None):
    """The measures behind QMJ for the latest fiscal year in recs (oldest first)."""
    cur = recs[-1]
    prev = recs[-2] if len(recs) > 1 else None
    a, e, rev = cur.get('assets'), cur.get('eq'), cur.get('rev')
    out = {}
    if a and a > 0:
        out['gpoa'] = _div(cur.get('gp'), a)
        out['roa'] = _div(cur.get('ni'), a)
        out['cfoa'] = _div(cur.get('ocf'), a)
        if cur.get('ni') is not None and cur.get('ocf') is not None:
            out['acc'] = (cur['ni'] - cur['ocf']) / a
        std, lt = _debt_parts(cur)
        out['lev'] = (std + lt) / a
    if e and e > 0:
        out['roe'] = _div(cur.get('ni'), e)
    if rev and rev > 0:
        out['gmar'] = _div(cur.get('gp'), rev)
    k = min(len(recs) - 1, 5)                          # growth over the longest span on file, up to five years
    if k >= 2:
        old = recs[-1 - k]
        ao, eo, ro = old.get('assets'), old.get('eq'), old.get('rev')

        def dgr(num, base):
            x0, x1 = cur.get(num), old.get(num)
            return None if x0 is None or x1 is None or not base or base <= 0 else (x0 - x1) / base / k
        out['d_gpoa'], out['d_roa'], out['d_cfoa'] = dgr('gp', ao), dgr('ni', ao), dgr('ocf', ao)
        out['d_roe'] = dgr('ni', eo)
        if cur.get('gp') is not None and old.get('gp') is not None and ro and ro > 0:
            out['d_gmar'] = (cur['gp'] - old['gp']) / ro / k
        out['growth_years'] = k
    roes = [_div(r.get('ni'), r.get('eq')) for r in recs[-5:] if r.get('eq') and r['eq'] > 0]
    out['evol'] = _sd(roes)
    out['beta'], out['ivol'], out['z'] = beta, ivol, z
    if prev:
        s0, s1 = cur.get('dil') or cur.get('so'), prev.get('dil') or prev.get('so')
        if s0 and s1:
            out['eiss'] = math.log(s0 / s1)
        d0, d1 = sum(_debt_parts(cur)), sum(_debt_parts(prev))
        if prev.get('assets'):
            out['diss'] = (d0 - d1) / prev['assets']
    pays = [(r.get('div') or 0) + (r.get('buyback') or 0) - (r.get('issue') or 0) for r in recs[-5:] if r.get('ni') is not None]
    prof = sum(r['ni'] for r in recs[-5:] if r.get('ni') is not None)
    if pays and prof > 0:
        out['npop'] = sum(pays) / prof
    return {k: (_r(v, 5) if isinstance(v, float) else v) for k, v in out.items()}


def _rank_z(vals):
    """{key: value} → {key: z-score of the rank} (AFP: each measure ranked, then standardized)."""
    keys = sorted(vals, key=lambda k: vals[k])
    n = len(keys)
    if n < 10:
        return {}
    r, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and vals[keys[j + 1]] == vals[keys[i]]:
            j += 1
        for k in range(i, j + 1):
            r[keys[k]] = (i + j) / 2
        i = j + 1
    m = (n - 1) / 2
    sd = math.sqrt(sum((v - m) ** 2 for v in r.values()) / n) or 1
    return {k: (v - m) / sd for k, v in r.items()}


def _zs(d):
    vals = [v for v in d.values() if v is not None]
    if len(vals) < 10:
        return {}
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) or 1
    return {k: (v - m) / sd for k, v in d.items() if v is not None}


def qmj_scores(inputs, min_share=0.5):
    """inputs: {key: qmj_inputs(...)} → {key: {'qmj', 'profitability', 'growth', 'safety', 'payout'}} (z-scores; a pillar
    needs half of its measures, QMJ three of the four pillars)."""
    z = {}
    for parts in QMJ_PARTS.values():
        for m, sign in parts:
            z[m] = _rank_z({k: sign * v[m] for k, v in inputs.items() if v.get(m) is not None and math.isfinite(v[m])})
    pillars = {}
    for p, parts in QMJ_PARTS.items():
        raw = {}
        for k in inputs:
            have = [z[m][k] for m, _ in parts if k in z[m]]
            if len(have) >= max(1, math.ceil(min_share * len(parts))):
                raw[k] = sum(have) / len(have)
        pillars[p] = _zs(raw)
    out = {}
    for k in inputs:
        have = {p: pillars[p][k] for p in QMJ_PARTS if k in pillars[p]}
        if len(have) >= 3:
            out[k] = {'raw': sum(have.values()) / len(have), **{p: _r(v, 3) for p, v in have.items()}}
    zz = _zs({k: v['raw'] for k, v in out.items()})
    for k, v in out.items():
        v['qmj'] = _r(zz.get(k), 3)
        v.pop('raw')
    return out


# ---------------------------------------------------------------- taxes, goodwill, non-GAAP
def taxes(recs, years=3):
    """Cash taxes paid against the tax expense over the last three fiscal years (both summed, so one odd year does not
    swing it). Ratio under 1: the company pays less tax in cash than it books (deferrals, credits, timing)."""
    rs = [r for r in recs[-years:] if r.get('tax') is not None and r.get('tax_paid') is not None]
    if not rs:
        return None
    paid, book = sum(r['tax_paid'] for r in rs), sum(r['tax'] for r in rs)
    pre = sum(r['pretax'] for r in rs if r.get('pretax') is not None) if all(r.get('pretax') is not None for r in rs) else None
    return {'years': len(rs), 'paid': paid, 'book': book, 'cash_to_book': _r(_div(paid, book), 3) if book and book > 0 else None,
            'cash_etr': _r(_div(paid, pre), 4) if pre and pre > 0 else None, 'book_etr': _r(_div(book, pre), 4) if pre and pre > 0 else None,
            'by_year': [[r['end'], r['tax_paid'], r['tax'], r.get('pretax')] for r in rs]}


def goodwill(recs, mcap=None):
    cur = recs[-1]
    gw, it, a, e = cur.get('gw'), cur.get('intang'), cur.get('assets'), cur.get('eq')
    if gw is None and it is None:
        return None
    total = (gw or 0) + (it or 0)
    imps = [[r['end'], r['gw_imp']] for r in recs if r.get('gw_imp')]
    tang = e - total if e is not None else None
    signs = []
    if tang is not None and tang < 0:
        signs.append('Goodwill and intangibles exceed shareholders\' equity (negative tangible equity)')
    if mcap and e and e > 0 and mcap < e and gw:
        signs.append('Market value below book equity: the goodwill impairment test is under pressure')
    if imps and any(r[0] >= recs[max(0, len(recs) - 3)]['end'] for r in imps):
        signs.append('A goodwill impairment in the last three fiscal years')
    hist = [[r['end'], r.get('gw'), r.get('intang'), r.get('assets'), r.get('eq')] for r in recs[-5:] if r.get('gw') is not None or r.get('intang') is not None]
    return {'gw': gw, 'intang': it, 'gw_assets': _r(_div(total, a), 4), 'gw_equity': _r(_div(total, e), 3) if e and e > 0 else None,
            'tangible_equity': tang, 'impairments': imps, 'signs': signs, 'history': hist}


def nongaap(street, quarters, shares, tolerance_days=46):
    """street: [{'quarter': 'YYYY-MM-DD' (period end), 'eps_act'}] (analysts' "actual", usually adjusted); quarters:
    [(period end ISO, net income)] calendar quarters; shares: diluted shares. The last four street quarters against GAAP
    EPS of the matching calendar quarters (net income ÷ the latest diluted shares, an approximation)."""
    import datetime as dt
    st = [s for s in street or [] if s.get('quarter') and s.get('eps_act') is not None]
    if len(st) < 4 or not shares or not quarters:
        return None
    st = sorted(st, key=lambda s: s['quarter'])[-4:]
    rows, used = [], set()
    for s in st:
        d = dt.date.fromisoformat(s['quarter'])
        best = min(quarters, key=lambda q: abs((dt.date.fromisoformat(q[0]) - d).days))
        if abs((dt.date.fromisoformat(best[0]) - d).days) > tolerance_days or best[1] is None or best[0] in used:
            return None
        used.add(best[0])
        rows.append([s['quarter'], s['eps_act'], _r(best[1] / shares, 4)])
    street_ttm, gaap_ttm = sum(r[1] for r in rows), sum(r[2] for r in rows)
    gap = (street_ttm - gaap_ttm) / abs(street_ttm) if street_ttm else None
    return {'street_ttm': _r(street_ttm, 3), 'gaap_ttm': _r(gaap_ttm, 3), 'gap': _r(gap, 4),
            'ratio': _r(street_ttm / gaap_ttm, 3) if gaap_ttm and gaap_ttm > 0 else None, 'quarters': rows}
