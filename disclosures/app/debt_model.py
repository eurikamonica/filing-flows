"""Debt safety analysis for debt.py: coverage, leverage, liquidity against maturities, covenant headroom, rate
sensitivity, refinancing cost, Altman Z, convertibles (as debt and if converted) and the market-implied credit spread.

Implied CDS. Free CDS quotes do not exist, so the spread is implied from the stock: the Merton model treats equity as a
call option on the firm's assets with the debt as strike (default point = short-term debt + half the long-term debt, the
KMV convention). From the market value of equity, its volatility (52 weekly returns) and the Treasury rate it solves for
the asset value and volatility, giving the distance to default (DD), the risk-neutral default probability and a model
5-year spread  s = −ln(1 − LGD · Q(default by 5y)) / 5  with LGD = 60%. Merton spreads are known to be too low for
safe companies and too jumpy for risky ones, so the page also shows a version calibrated on real bond pricing: every
USD fixed-rate bond priced in a term sheet (its spread to Treasuries at issue) is paired with the model spread of its
issuer that week, and  log(issue spread) = a + b·log(model spread) + c·log(years)  is fitted across companies; the
calibrated 5-year implied spread uses that fit. Convertibles: when the stock trades above the conversion price, the
notes are likely to become shares, so the analysis is shown both ways — as debt, and if converted (debt down, shares up).
"""
import math

LGD = 0.6
NORM = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))


def merton(E, sigma_E, D, r, T=1.0, iters=60):
    """(asset value V, asset volatility sigma_V, distance to default) from equity value E, equity vol, default point D,
    rate r (decimal). Standard two-equation solve by fixed-point iteration."""
    if not (E and E > 0 and D and D > 0 and sigma_E and sigma_E > 0):
        return None
    V, sV = E + D, sigma_E * E / (E + D)
    for _ in range(iters):
        sT = sV * math.sqrt(T)
        d1 = (math.log(V / D) + (r + 0.5 * sV * sV) * T) / sT
        d2 = d1 - sT
        Nd1 = NORM(d1)
        V_new = (E + D * math.exp(-r * T) * NORM(d2)) / max(Nd1, 1e-9)
        sV_new = sigma_E * E / (max(Nd1, 1e-9) * V_new)
        if abs(V_new - V) < 1e-6 * V and abs(sV_new - sV) < 1e-7:
            V, sV = V_new, sV_new
            break
        V, sV = V_new, max(1e-4, min(3.0, sV_new))
    sT = sV * math.sqrt(T)
    dd = (math.log(V / D) + (r - 0.5 * sV * sV) * T) / sT
    return V, sV, dd


def merton_spread(V, sV, D, r, T=5.0):
    """Risk-neutral default probability by T and the implied spread (decimal) with LGD."""
    sT = sV * math.sqrt(T)
    d2 = (math.log(V / D) + (r - 0.5 * sV * sV) * T) / sT
    Q = NORM(-d2)
    return Q, -math.log(max(1e-12, 1 - LGD * Q)) / T


def default_point(current_debt, total_debt):
    if total_debt is None:
        return None
    cd = current_debt if current_debt is not None else 0.0
    cd = min(cd, total_debt)
    return cd + 0.5 * (total_debt - cd)


def implied(E, sigma_E, current_debt, total_debt, r):
    D = default_point(current_debt, total_debt)
    if not D or D <= 0:
        return None
    m = merton(E, sigma_E, D, r, 1.0)
    if not m:
        return None
    V, sV, dd = m
    pd1 = NORM(-dd)
    Q5, s5 = merton_spread(V, sV, D, r, 5.0)
    return {'dd': dd, 'pd_1y': pd1, 'q_5y': Q5, 'spread_5y_bps': s5 * 1e4, 'asset_value': V, 'asset_vol': sV, 'default_point': D}


def fit_calibration(pairs, min_n=25):
    """pairs: [(distance to default, issue spread bps, years)]. OLS of log(spread) on DD (capped at 15) and log(years);
    the DD slope is kept negative and moderate so the map stays monotone outside the data."""
    rows = [(min(15.0, max(-2.0, d)), math.log(s), math.log(max(0.5, y))) for d, s, y in pairs if d is not None and s and s > 0 and y]
    if len(rows) < min_n:
        return None
    n = len(rows)
    X = [[1.0, a, c] for a, _, c in rows]; Y = [b for _, b, _ in rows]
    XtX = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(3)] for i in range(3)]
    XtY = [sum(X[k][i] * Y[k] for k in range(n)) for i in range(3)]
    for i in range(3):
        XtX[i][i] += 1e-6
    beta = _solve3(XtX, XtY)
    if beta is None:
        return None
    if not (-0.8 <= beta[1] <= -0.02):
        b = min(-0.02, max(-0.8, beta[1]))
        Yr = [y - b * x[1] for y, x in zip(Y, X)]
        A2 = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in (0, 2)] for i in (0, 2)]
        y2 = [sum(X[k][i] * Yr[k] for k in range(n)) for i in (0, 2)]
        det = A2[0][0] * A2[1][1] - A2[0][1] * A2[1][0]
        if abs(det) < 1e-12:
            return None
        beta = [(y2[0] * A2[1][1] - A2[0][1] * y2[1]) / det, b, (A2[0][0] * y2[1] - A2[1][0] * y2[0]) / det]
    pred = [sum(b * x for b, x in zip(beta, X[k])) for k in range(n)]
    my = sum(Y) / n
    ss_res = sum((Y[k] - pred[k]) ** 2 for k in range(n)); ss_tot = sum((y - my) ** 2 for y in Y)
    resid = sorted(Y[k] - pred[k] for k in range(n))
    return {'a': beta[0], 'b': beta[1], 'c': beta[2], 'n': n, 'x': 'distance_to_default', 'r2': 1 - ss_res / ss_tot if ss_tot > 0 else None,
            'resid_p10': resid[int(.1 * (n - 1))], 'resid_p90': resid[int(.9 * (n - 1))]}


def _solve3(A, b):
    M = [row[:] + [v] for row, v in zip(A, b)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            return None
        M[i], M[p] = M[p], M[i]
        for r in range(3):
            if r != i:
                f = M[r][i] / M[i][i]
                M[r] = [x - f * y for x, y in zip(M[r], M[i])]
    return [M[i][3] / M[i][i] for i in range(3)]


def calibrated(dd, fit, years=5.0):
    """Market-calibrated 5-year spread (bps) from the distance to default."""
    if dd is None or not fit:
        return None
    return min(5000.0, max(3.0, math.exp(fit['a'] + fit['b'] * min(15.0, max(-2.0, dd)) + fit['c'] * math.log(years))))


RATING_BANDS = [('AAA', 'BAMLC0A1CAAA'), ('AA', 'BAMLC0A2CAA'), ('A', 'BAMLC0A3CA'), ('BBB', 'BAMLC0A4CBBB'),
                ('BB', 'BAMLH0A1HYBB'), ('B', 'BAMLH0A2HYB'), ('CCC', 'BAMLH0A3HYC')]


def implied_rating(spread_bps, oas_now):
    """The rating band whose current ICE BofA option-adjusted spread is nearest (in log terms) to the implied spread."""
    if spread_bps is None or not oas_now:
        return None
    best = None
    for name, sid in RATING_BANDS:
        v = oas_now.get(sid)
        if v is None or v <= 0:
            continue
        d = abs(math.log(max(1.0, spread_bps)) - math.log(v * 100))
        if best is None or d < best[1]:
            best = (name, d)
    return best[0] if best else None


def safe_div(a, b):
    return None if a is None or b in (None, 0) else a / b


def analyse(snap, instruments, agreements, price=None, sigma_E=None, r1=None, r5=None, fit=None, oas_now=None, sofr=None):
    """Every safety figure for one company from its latest snapshot (debt_facts.snapshot), its instruments (XBRL), its
    credit agreements and the market (price, equity volatility, 1-year and 5-year Treasury yields in decimals)."""
    g = snap.get
    if g('total_debt') is None:                          # no standard debt tag: show what exists, compute no ratios on 0
        snap = dict(snap)
    debt_known = g('total_debt') is not None
    debt = g('total_debt') or 0.0
    cash = (g('cash') or 0.0) + (g('investments') or 0.0)
    ebit = g('operating_income')
    ebitda = None if ebit is None else ebit + (g('da') or 0.0)
    intexp = g('interest_expense')
    intexp = abs(intexp) if intexp is not None else None
    out = {'total_debt': debt if debt_known else None, 'cash_and_investments': cash or None,
           'net_debt': (debt - cash) if debt_known else None, 'ebitda': ebitda, 'ebit': ebit, 'interest_expense': intexp}
    out['leverage'] = safe_div(debt, ebitda) if debt_known and ebitda and ebitda > 0 else None
    out['net_leverage'] = safe_div(debt - cash, ebitda) if debt_known and ebitda and ebitda > 0 else None
    out['interest_coverage'] = safe_div(ebit, intexp) if intexp else None
    out['ebitda_coverage'] = safe_div(ebitda, intexp) if intexp else None
    ip = g('interest_paid')
    if ip and g('ocf') is not None:
        out['cash_coverage'] = (g('ocf') + abs(ip)) / abs(ip)
    fcf = None if g('ocf') is None else g('ocf') - abs(g('capex') or 0.0)
    out['fcf'] = fcf
    out['fcf_to_debt'] = safe_div(fcf, debt) if debt else None
    out['effective_rate'] = safe_div(intexp, debt) if debt and intexp else None
    # liquidity against what falls due
    rev_avail = g('revolver_available')
    if rev_avail is None:
        caps = [i for i in instruments if i.get('kind') == 'revolver' and i.get('capacity')]
        if caps:
            rev_avail = sum(max(0.0, (i.get('available') if i.get('available') is not None else i['capacity'] - (i.get('drawn') or i.get('carrying') or 0.0))) for i in caps)
    out['revolver_available'] = rev_avail
    liquidity = cash + (rev_avail or 0.0)
    out['liquidity'] = liquidity or None
    mats = g('maturities') or {}
    due12 = mats.get('next12m') if mats.get('next12m') is not None else (mats.get('rest_of_year') if mats.get('rest_of_year') is not None else g('current_debt'))
    due24 = None
    if due12 is not None and mats.get('y2') is not None:
        due24 = due12 + mats['y2']
    out['due_12m'] = due12
    out['due_24m'] = due24
    out['liquidity_to_due12'] = safe_div(liquidity, due12) if due12 else None
    out['liquidity_to_due24'] = safe_div(liquidity, due24) if due24 else None
    # floating-rate share and +100 bp
    fl = sum((i.get('carrying') or 0.0) for i in instruments if i.get('floating') and i.get('kind') not in ('revolver',) and (i.get('carrying') or 0) > 0)
    fl += sum((i.get('drawn') or i.get('carrying') or 0.0) for i in instruments if i.get('kind') == 'revolver')
    if g('variable_share') is not None and debt:
        fl = g('variable_share') * debt
    if g('commercial_paper'):
        fl = max(fl, g('commercial_paper'))
    fl = min(fl, debt) if debt else fl
    out['floating_debt'] = fl or None
    out['floating_share'] = safe_div(fl, debt) if debt else None
    out['plus100bp_interest'] = 0.01 * fl if fl else None
    out['plus100bp_share_of_ebit'] = safe_div(0.01 * fl, ebit) if fl and ebit and ebit > 0 else None
    # refinancing: what is due in two years, at today's market rate for this company vs the average rate paid
    # Altman Z (manufacturers' formula; not meaningful for banks and insurers)
    A = g('assets')
    if A and g('liabilities'):
        wc = (g('assets_current') or 0.0) - (g('liabilities_current') or 0.0)
        mve = price * g('shares') if price and g('shares') else None
        if mve is not None and g('revenue') is not None and ebit is not None:
            out['altman_z'] = (1.2 * wc / A + 1.4 * (g('retained_earnings') or 0.0) / A + 3.3 * ebit / A + 0.6 * mve / g('liabilities')
                               + 1.0 * g('revenue') / A)
    # market value and the implied spread, as debt and if converted
    mcap = price * g('shares') if price and g('shares') else None
    out['market_cap'] = mcap
    out['debt_to_ev'] = safe_div(debt, (mcap or 0) + debt - cash) if mcap and debt else None
    conv = convertibles(snap, instruments, price)
    out['convertibles'] = conv
    if mcap and sigma_E and r1 is not None and debt:
        cdebt = g('current_debt')
        m = implied(mcap, sigma_E, cdebt, debt, r1)
        if m:
            out['implied'] = {k: m[k] for k in ('dd', 'pd_1y', 'spread_5y_bps', 'asset_vol')}
            out['implied']['calibrated_5y_bps'] = calibrated(m['dd'], fit)
            out['implied']['rating_band'] = implied_rating(out['implied']['calibrated_5y_bps'] or m['spread_5y_bps'], oas_now)
        if conv and conv.get('in_the_money_face'):
            d2 = max(0.0, debt - conv['in_the_money_carrying'])
            E2 = mcap + conv['in_the_money_face']            # converted notes become equity worth at least their face
            m2 = implied(E2, sigma_E * mcap / E2, cdebt, d2, r1) if d2 > 0 else None
            out['if_converted'] = {'total_debt': d2, 'shares_added': conv['shares_if_converted'], 'dilution': conv.get('dilution'),
                                   'leverage': safe_div(d2, ebitda) if ebitda and ebitda > 0 else None,
                                   'interest_coverage': safe_div(ebit, (intexp or 0) - conv.get('coupon_saved', 0.0)) if intexp and ebit is not None and (intexp - conv.get('coupon_saved', 0.0)) > 0 else None,
                                   'implied_5y_bps': (calibrated(m2['dd'], fit) or m2['spread_5y_bps']) if m2 else (0.0 if d2 == 0 else None),
                                   'dd': m2['dd'] if m2 else None}
    # refinancing cost of what falls due within two years
    if due24 and r5 is not None:
        sp = None
        if out.get('implied'):
            sp = out['implied'].get('calibrated_5y_bps') or out['implied'].get('spread_5y_bps')
        mkt = r5 + (sp or 0) / 1e4
        out['market_rate_5y'] = mkt
        if out.get('effective_rate') is not None:
            out['refi_extra_interest'] = due24 * (mkt - out['effective_rate'])
    out['covenants'] = covenant_headroom(agreements, out, snap)
    if sofr is not None:
        for a in agreements:
            if a.get('margin_pct'):
                a['all_in_pct'] = [sofr + a['margin_pct'][0], sofr + a['margin_pct'][1]]
    out['cushion_score'] = cushion_score(out)
    return out


def convertibles(snap, instruments, price):
    conv = [i for i in instruments if i.get('kind') == 'convertible' and (i.get('carrying') or i.get('face'))]
    if any(i.get('conv_price') or i.get('conv_ratio') for i in conv):
        conv = [i for i in conv if i.get('conv_price') or i.get('conv_ratio')]
    rows = []
    this_year = __import__('datetime').date.today().year
    for i in conv:
        my = i.get('maturity_year') or (int(str(i['maturity'])[:4]) if i.get('maturity') else None)
        if my and my < this_year:
            continue                                     # matured: settled or converted already
        face = i.get('face') or i.get('carrying')
        if not face or (i.get('carrying') == 0):
            continue
        cp = i.get('conv_price') or (1000.0 / i['conv_ratio'] if i.get('conv_ratio') else None)
        r = {'name': i['name'], 'face': face, 'carrying': i.get('carrying') or face, 'coupon': i.get('coupon'), 'conv_price': cp,
             'maturity': i.get('maturity') or i.get('maturity_year')}
        if cp and price:
            r['moneyness'] = price / cp
            r['in_the_money'] = price >= cp
            r['shares'] = face / cp
        rows.append(r)
    if not rows and snap.get('convertible') and snap.get('conversion_price'):
        cp = snap['conversion_price']; face = snap['convertible']
        r = {'name': 'Convertible notes (company total)', 'face': face, 'carrying': face, 'conv_price': cp}
        if price:
            r.update(moneyness=price / cp, in_the_money=price >= cp, shares=face / cp)
        rows.append(r)
    if not rows:
        return None
    itm = [r for r in rows if r.get('in_the_money')]
    sh = snap.get('shares')
    out = {'notes': rows, 'total_face': sum(r['face'] for r in rows),
           'in_the_money_face': sum(r['face'] for r in itm), 'in_the_money_carrying': sum(r['carrying'] for r in itm),
           'shares_if_converted': sum(r.get('shares') or 0 for r in itm),
           'coupon_saved': sum((r.get('coupon') or 0) * r['face'] for r in itm)}
    if sh and out['shares_if_converted']:
        out['dilution'] = out['shares_if_converted'] / sh
    if snap.get('if_converted_shares'):
        out['reported_dilutive_shares'] = snap['if_converted_shares']
    return out


def covenant_headroom(agreements, m, snap):
    """Maintenance covenants against today's figures. The agreements define EBITDA and debt their own way (add-backs,
    netting cash), so this is an approximation from reported figures — the page says so."""
    out = []
    seen = set()
    for a in agreements:
        for c in a.get('covenants', []) or []:
            if not c.get('maintenance'):
                continue
            key = (c['type'], c['direction'])
            if key in seen:
                continue
            seen.add(key)
            actual, cushion = None, None
            net = 'net' in (c.get('text') or '').lower()
            if c['type'] == 'leverage' and c['direction'] == 'max' and c['unit'] == 'x':
                actual = m.get('net_leverage') if net else m.get('leverage')
                if actual is not None and c['limit']:
                    cushion = 1 - actual / c['limit']           # how far EBITDA can fall before the limit binds
            elif c['type'] in ('interest_coverage', 'fixed_charge') and c['direction'] == 'min' and c['unit'] == 'x':
                actual = m.get('ebitda_coverage')
                if actual is not None and actual > 0 and c['limit']:
                    cushion = 1 - c['limit'] / actual
            elif c['type'] == 'liquidity' and c['direction'] == 'min' and c['unit'] == 'usd':
                actual = m.get('liquidity')
                if actual:
                    cushion = (actual - c['limit']) / actual
            elif c['type'] == 'debt_to_cap' and c['direction'] == 'max':
                eq = snap.get('equity')
                if eq is not None and m.get('total_debt'):
                    actual = m['total_debt'] / (m['total_debt'] + eq)
                    lim = c['limit'] / 100 if c['limit'] > 1.5 else c['limit']
                    cushion = 1 - actual / lim if lim else None
            out.append({'type': c['type'], 'direction': c['direction'], 'limit': c['limit'], 'unit': c['unit'], 'actual': actual,
                        'cushion': cushion, 'agreement': a.get('title') or a.get('kind'), 'dated': a.get('dated'), 'text': c.get('text')})
    return out


def cushion_score(m):
    """0–100, higher = safer: an average of banded scores for coverage, leverage, liquidity vs maturities, implied
    distance to default and covenant cushion (only the parts that exist)."""
    parts = []
    def band(v, pts):
        if v is None:
            return None
        for lim, sc in pts:
            if v <= lim:
                return sc
        return pts[-1][1]
    ic = m.get('interest_coverage')
    if ic is not None:
        parts.append(band(ic, [(1, 5), (1.5, 20), (3, 45), (6, 70), (12, 88), (1e9, 100)]))
    lev = m.get('net_leverage')
    if lev is not None:
        parts.append(100 - band(lev, [(0, 0), (1, 10), (2, 25), (3, 45), (4, 65), (6, 85), (1e9, 95)]))
    lq = m.get('liquidity_to_due12')
    if lq is not None:
        parts.append(band(lq, [(0.5, 5), (1, 30), (2, 60), (4, 85), (1e9, 100)]))
    imp = m.get('implied') or {}
    if imp.get('dd') is not None:
        parts.append(band(imp['dd'], [(1, 5), (2, 25), (3, 50), (5, 75), (8, 90), (1e9, 100)]))
    cov = [c['cushion'] for c in m.get('covenants') or [] if c.get('cushion') is not None]
    if cov:
        parts.append(band(min(cov), [(0, 0), (0.1, 20), (0.25, 50), (0.5, 80), (1e9, 100)]))
    parts = [p for p in parts if p is not None]
    return round(sum(parts) / len(parts)) if len(parts) >= 2 else None
