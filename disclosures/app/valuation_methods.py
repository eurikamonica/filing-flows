"""Valuation methods for the companies a plain DCF does not fit, and the valuation appendix.

Methods (each a football item with its formula, inputs and assumptions in `calc`; base_rates.stage_block weighs them by
stage):
  Pre-revenue (revenue under $25M over four quarters and operating income ≤ 0) — a biotech or a start-up whose value is
    a pipeline no filing prices:
      Net cash (floor)              (cash − debt − claims) ÷ shares: what holders own if the pipeline is worth nothing
      Market-implied pipeline       EV = market value − net cash: what the price pays for everything not yet earning
                                    (a metric, not a method)
  Early-stage / pre-profit and every company burning cash (operating income ≤ 0, or free cash flow < 0):
      Path-to-margin DCF, dilution-adjusted
                                    the path-to-margin DCF (margin from today's to the peer median by year 5) with the
                                    cash it burns before break-even funded by new shares at today's price:
                                    value = equity ÷ (shares + max(0, Σ negative FCFF − cash) ÷ price)
      Exit-multiple (venture) method year-5 revenue on the growth path × the peer median operating margin × (1 − tax) ×
                                    the peer median P/E, discounted 5 years at the cost of equity + a 5-point stage
                                    premium (an assumption: venture and growth investors' hurdle above the CAPM rate),
                                    over the diluted share count
      Survival-weighted value       (1 − p) × the going-concern value + p × the liquidation value, p = the probability of
                                    failing within 5 years = 1 − (1 − blended one-year distress)^5; with no distress
                                    estimate, from the cash runway: p = clamp(0.5 − runway ÷ 10, 0.05, 0.5) (an
                                    assumption, stated); liquidation = tangible book × 0.8, floored at 0
  High growth and pre-profit:
      EV/Sales vs Rule of 40 (all-company fit)
                                    log(EV/Sales) = a + b × (revenue growth + free-cash-flow margin), fitted across every
                                    covered non-financial company (revenue ≥ $50M); the company's fitted EV/Sales ±1
                                    standard error × revenue → equity per share
  Banks, insurers (and REITs):
      Justified P/TBV / P/B (Gordon growth)
                                    P/B = (ROE − g) ÷ (kₑ − g), g = ROE × (1 − payout), capped at 0–4% (banks: tangible
                                    book and ROTCE; insurers: book and ROE)
      Dividend discount (Gordon)    DPS × (1 + g) ÷ (kₑ − g); g as above (REITs: the 2.5% terminal growth — they pay out
                                    most of what they earn)

Appendix (out['appendix']): the inputs with their sources, the fixed assumptions with their basis, the cost of capital
built up step by step, and for every method on the football field its formula, the company's numbers substituted, its
range and the weight its stage gives it; the methods that do not apply, with the reason."""
import math

PRE_REVENUE = 25e6          # four-quarter revenue below this, with an operating loss: pre-revenue
STAGE_PREMIUM = 0.05        # the exit-multiple method's hurdle above the cost of equity
LIQ_HAIRCUT = 0.8           # liquidation value = tangible book × 0.8
G_CAP = 0.04                # sustainable growth cap for the Gordon models


def fin(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- formatting for the appendix (strings, ready to show)
def money(v):
    if not fin(v):
        return '—'
    a, s = abs(v), '−' if v < 0 else ''
    for d, u in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if a >= d:
            return f'{s}${a / d:,.{2 if a / d < 100 else 1}f}{u}'
    return f'{s}${a:,.0f}'


def ps(v):
    return '—' if not fin(v) else (f'−${abs(v):,.2f}' if v < 0 else f'${v:,.2f}')


def pc(v, d=1):
    return '—' if not fin(v) else f'{v * 100:.{d}f}%'


def xm(v, d=2):
    return '—' if not fin(v) else f'{v:.{d}f}x'


def num(v, d=0):
    return '—' if not fin(v) else f'{v:,.{d}f}'


def less_nd(nd):
    """'− net debt $X' or '+ net cash $X' — the step that takes an enterprise value to equity."""
    return f'− net debt {money(nd)}' if not fin(nd) or nd >= 0 else f'+ net cash {money(-nd)}'


def calc(formula, steps, inputs=(), assumptions=(), source=None, kind='model'):
    """formula: the algebra; steps: the same with the numbers in; inputs: [label, value, source]; assumptions:
    [label, value, basis]."""
    return {'formula': formula, 'steps': list(steps), 'inputs': [list(i) for i in inputs], 'assumptions': [list(a) for a in assumptions],
            'source': source, 'kind': kind}


SOURCE_NAMES = [   # valuation.company_inputs' short source names → what they are
    ('main site (trailing)', "SEC 10-K / 10-Q, trailing four quarters (the main site's reading of the filings)"),
    ('main site (diluted)', "SEC 10-K / 10-Q, diluted shares (the main site's reading)"),
    ('main site (outstanding, after a split or issue)', 'SEC filing cover page: shares outstanding (after a split or issue)'),
    ('main site (outstanding)', 'SEC filing cover page: shares outstanding'),
    ('main site', "SEC 10-K / 10-Q balance sheet (the main site's reading)"),
    ('frames, 4 quarters', 'SEC XBRL frames: the sum of the last four quarters'),
    ('main site (pretax − tax)', "SEC 10-K / 10-Q, trailing four quarters: pretax income − income tax (the main site's reading)"),
    ('frames, latest year', 'SEC XBRL frames: the latest fiscal year'),
    ('frames, diluted weighted average', 'SEC XBRL frames: diluted weighted-average shares'),
    ('frames, long-term debt', 'SEC XBRL frames: long-term debt'),
    ('frames, cash', 'SEC XBRL frames: cash and equivalents'),
    ('frames', 'SEC XBRL frames: the latest balance sheet'),
    ('debt module (cover page)', 'Debt & rates module: the filing cover page'),
    ('debt module', 'Debt & rates module (app/debt.py, from the 10-K / 10-Q)'),
    ('analysts (Yahoo)', 'analysts (Yahoo Finance)')]


def nice_src(name):
    if not name:
        return name
    for k, v in SOURCE_NAMES:
        if name == k:
            return v
    return name


def src_of(F, key, default='SEC XBRL frames'):
    return nice_src((F.get('src') or {}).get(key)) or default


# ---------------------------------------------------------------- the methods
def pre_revenue(F):
    rev, oi = F.get('revenue'), F.get('oi')
    return (not fin(rev) or rev < PRE_REVENUE) and (not fin(oi) or oi <= 0)


def fcf_of(F):
    if not (fin(F.get('oi')) and fin(F.get('revenue'))):
        return None
    t = F.get('tax_rate', 0.21) if F['oi'] > 0 else 0.0
    return F['oi'] * (1 - t) + (F.get('da') or 0) - (F.get('capex') or 0)


def net_cash_floor(F):
    sh = F.get('shares')
    if not (fin(sh) and sh > 0):
        return None
    nc = (F.get('cash') or 0) - (F.get('debt') or 0) - (F.get('claims') or 0)
    v = max(nc, 0) / sh
    ev = F['mcap'] - nc if fin(F.get('mcap')) else None
    c = calc('Net cash per share = (cash − debt − other claims) ÷ diluted shares, floored at 0',
             [f'= ({money(F.get("cash"))} − {money(F.get("debt"))} − {money(F.get("claims"))}) ÷ {num(sh)} = {ps(nc / sh)} → {ps(v)}',
              f'Market-implied value of the pipeline (EV) = market value − net cash = {money(F.get("mcap"))} − {money(nc)} = {money(ev)}'],
             [['Cash and investments', money(F.get('cash')), src_of(F, 'cash')], ['Debt', money(F.get('debt')), src_of(F, 'debt')],
              ['Diluted shares', num(sh), src_of(F, 'shares')]],
             [['Pipeline', 'valued at 0', 'a floor: no filing prices a drug trial or an unlaunched product']])
    return {'method': 'Net cash (floor)', 'low': v * 0.9, 'high': v, 'point': v, 'calc': c,
            'note': f'cash − debt = {money(nc)}; the price pays {money(ev)} for the pipeline'}, ev


def path_dilution(M, pb, F):
    """The path-to-margin DCF with the cash burned before break-even funded by new shares at today's price."""
    r = M.dcf(pb)
    price, sh = F.get('price'), pb.get('shares')
    if not (r.get('ok') and fin(price) and price > 0 and fin(sh) and sh > 0):
        return None
    burn = -sum(x['fcff'] for x in r['rows'] if x['fcff'] < 0)
    gap = max(0.0, burn - (pb.get('cash') or 0))
    new = gap / price
    v = r['equity'] / (sh + new)
    return v, burn, gap, new, r


def path_dilution_item(M, pb, F, tm, m0):
    res = [path_dilution(M, {**pb, 'margin': [m0 + (t - m0) * (k + 1) / M.YEARS for k in range(M.YEARS)]}, F) for t in (tm - 0.05, tm, tm + 0.05)]
    if not all(res):
        return None
    v, burn, gap, new, r = res[1]
    sh = pb['shares']
    c = calc('Value per share = equity value ÷ (shares + new shares); new shares = max(0, cash burned before break-even − cash today) ÷ price',
             [f'Margin path: {pc(m0)} today → {pc(tm)} in year {M.YEARS} (straight line); growth {", ".join(pc(g, 0) for g in pb["growth"])}',
              f'FCFF by year: {", ".join(money(x["fcff"]) for x in r["rows"])}; cash burned (negative years) = {money(burn)}',
              f'Funding gap = max(0, {money(burn)} − {money(pb.get("cash"))}) = {money(gap)} → {num(new)} new shares at {ps(F["price"])}',
              f'Equity value = EV {money(r["ev"])} − debt {money(pb["debt"])} + cash {money(pb["cash"])} = {money(r["equity"])}',
              f'= {money(r["equity"])} ÷ ({num(sh)} + {num(new)}) = {ps(v)}  (target margin ±5 points: {ps(min(x[0] for x in res))} – {ps(max(x[0] for x in res))})'],
             [['Revenue, four quarters', money(F.get('revenue')), src_of(F, 'revenue')], ['Operating income', money(F.get('oi')), src_of(F, 'oi')],
              ['Cash', money(F.get('cash')), src_of(F, 'cash')], ['Diluted shares', num(sh), src_of(F, 'shares')]],
             [['Target operating margin', pc(tm), 'peer median operating margin (SIC industry × size, base rates)'],
              ['WACC', pc(pb['wacc']), 'the company\'s cost of capital (build-up above)'], ['Terminal growth', pc(pb['g']), 'fixed assumption'],
              ['New shares priced at', ps(F['price']), 'today\'s price: an assumption — raising money in a downturn costs more']])
    return {'method': 'Path-to-margin DCF, dilution-adjusted', 'low': min(x[0] for x in res), 'high': max(x[0] for x in res), 'point': v, 'calc': c,
            'note': f'{money(gap)} still to raise before break-even → {num(new)} new shares ({pc(new / sh, 0)} dilution)'}


def exit_multiple(M, pb, F, W, tm, pe, new_shares=0.0):
    sh = F.get('shares')
    if not (W and fin(W.get('ke')) and pe and fin(pe.get('p50')) and pe['p50'] > 0 and fin(sh) and sh > 0):
        return None
    rev5 = F['revenue']
    for g in pb['growth']:
        rev5 *= 1 + g
    ni5 = rev5 * tm * (1 - F.get('tax_rate', 0.21))
    r = W['ke'] + STAGE_PREMIUM
    shares = sh + (new_shares or 0)
    val = lambda rate, mult: ni5 * mult / (1 + rate) ** M.YEARS / shares
    v = val(r, pe['p50'])
    lo, hi = val(r + 0.025, pe['p25']), val(r - 0.025, pe['p75'])
    c = calc(f'Value per share = (revenue in year {M.YEARS} × target margin × (1 − tax) × exit P/E) ÷ (1 + kₑ + stage premium)^{M.YEARS} ÷ diluted shares',
             [f'Revenue in year {M.YEARS} = {money(F["revenue"])} × {" × ".join(f"(1 + {pc(g, 0)})" for g in pb["growth"])} = {money(rev5)}',
              f'Net income in year {M.YEARS} = {money(rev5)} × {pc(tm)} × (1 − {pc(F.get("tax_rate", 0.21), 0)}) = {money(ni5)}',
              f'Equity value then = {money(ni5)} × {xm(pe["p50"], 1)} = {money(ni5 * pe["p50"])}',
              f'Today = {money(ni5 * pe["p50"])} ÷ (1 + {pc(W["ke"])} + {pc(STAGE_PREMIUM, 0)})^{M.YEARS} ÷ {num(shares)} shares = {ps(v)}',
              f'Range: P/E {xm(pe["p25"], 1)} at a hurdle 2.5 points higher → {ps(lo)}; P/E {xm(pe["p75"], 1)} at 2.5 points lower → {ps(hi)}'],
             [['Revenue, four quarters', money(F.get('revenue')), src_of(F, 'revenue')], ['Tax rate', pc(F.get('tax_rate', 0.21), 0), 'tax ÷ pretax income (0–35%, else 21%)'],
              ['Diluted shares (with the funding need)', num(shares), src_of(F, 'shares')]],
             [['Growth path', ', '.join(pc(g, 0) for g in pb['growth']), 'its own growth fading to terminal (the DCF\'s path)'],
              ['Target margin', pc(tm), 'peer median operating margin'], ['Exit P/E', f'{xm(pe["p25"], 1)} / {xm(pe["p50"], 1)} / {xm(pe["p75"], 1)}', f'peer P/E, {pe.get("label") or "peers"} ({pe.get("n")} observations)'],
              ['Hurdle rate', pc(r), f'cost of equity {pc(W["ke"])} + {pc(STAGE_PREMIUM, 0)} stage premium (an assumption)']])
    return {'method': 'Exit-multiple (venture) method', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c,
            'note': f'year-{M.YEARS} earnings {money(ni5)} × {xm(pe["p50"], 1)} peer P/E, discounted at {pc(r)}'}


def survival_weighted(F, going, pd1, runway):
    sh = F.get('shares')
    if not (going and fin(going.get('point')) and fin(sh) and sh > 0):
        return None
    tbv = (F.get('equity') or 0) - (F.get('goodwill') or 0) - (F.get('intangibles') or 0)
    liq = max(0.0, tbv) * LIQ_HAIRCUT / sh
    if fin(pd1):
        p = clamp(1 - (1 - pd1) ** 5, 0.01, 0.9)
        how = [f'p(fail within 5 years) = 1 − (1 − {pc(pd1)})^5 = {pc(p)}', 'one-year distress: the blended Merton / CDS / Altman / cushion estimate (credit panel)']
    elif fin(runway):
        p = clamp(0.5 - runway / 10, 0.05, 0.5)
        how = [f'p(fail within 5 years) = clamp(0.5 − runway {runway:.1f} years ÷ 10, 5%, 50%) = {pc(p)}', 'no distress estimate: from the cash runway (an assumption)']
    else:
        return None
    pts = {k: (1 - p) * going[k] + p * liq for k in ('low', 'point', 'high') if fin(going.get(k))}
    if 'point' not in pts:
        return None
    c = calc('Value per share = (1 − p) × going-concern value + p × liquidation value',
             how[:1] + [f'Liquidation value = max(0, tangible book {money(tbv)}) × {LIQ_HAIRCUT:.0%} ÷ {num(sh)} = {ps(liq)}',
                        f'= (1 − {pc(p)}) × {ps(going["point"])} + {pc(p)} × {ps(liq)} = {ps(pts["point"])}'],
             [['Tangible book (equity − goodwill − intangibles)', money(tbv), 'SEC XBRL frames / debt module'], ['Diluted shares', num(sh), src_of(F, 'shares')]],
             [['Going-concern value', ps(going['point']), going['method']], ['Failure probability', pc(p), how[1]],
              ['Liquidation haircut', f'{(1 - LIQ_HAIRCUT):.0%} off tangible book', 'an assumption for a forced sale']])
    return {'method': 'Survival-weighted value', 'low': min(pts.get('low', pts['point']), pts.get('high', pts['point'])),
            'high': max(pts.get('low', pts['point']), pts.get('high', pts['point'])), 'point': pts['point'], 'calc': c,
            'note': f'{pc(p, 0)} chance of failing within 5 years; liquidation {ps(liq)}/share'}


def rule40_fit(rows):
    """log(EV/Sales) on (growth + FCF margin) across the covered non-financial companies with revenue ≥ $50M."""
    pts = []
    for r in rows:
        if r.get('kind') != 'industrial' or not fin(r.get('ev_sales')) or not fin(r.get('g0')) or not fin(r.get('revenue')) or r['revenue'] < 5e7:
            continue
        f = fcf_of(r)
        if not fin(f):
            continue
        x = clamp(r['g0'], -0.5, 1.0) + clamp(f / r['revenue'], -1.0, 0.6)
        if 0.05 < r['ev_sales'] <= 50:
            pts.append((x, math.log(r['ev_sales'])))
    n = len(pts)
    if n < 30:
        return None
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx <= 0:
        return None
    b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    a = my - b * mx
    se = math.sqrt(sum((p[1] - a - b * p[0]) ** 2 for p in pts) / (n - 2))
    ss = sum((p[1] - my) ** 2 for p in pts)
    return {'a': a, 'b': b, 'se': se, 'n': n, 'r2': 1 - se * se * (n - 2) / ss if ss > 0 else None}


def rule40_item(F, fit):
    sh, rev = F.get('shares'), F.get('revenue')
    f = fcf_of(F)
    if not (fit and fin(sh) and sh > 0 and fin(rev) and rev > 0 and fin(F.get('g0')) and fin(f)):
        return None
    x = clamp(F['g0'], -0.5, 1.0) + clamp(f / rev, -1.0, 0.6)
    nd = (F.get('debt') or 0) - (F.get('cash') or 0) + (F.get('claims') or 0)
    per = lambda lm: (math.exp(lm) * rev - nd) / sh
    mid = fit['a'] + fit['b'] * x
    v, lo, hi = per(mid), per(mid - fit['se']), per(mid + fit['se'])
    c = calc('ln(EV/Sales) = a + b × (revenue growth + free-cash-flow margin); value per share = (fitted EV/Sales × revenue − net debt) ÷ shares',
             [f'Rule of 40 = {pc(F["g0"])} growth + {pc(f / rev)} FCF margin = {x * 100:.1f}',
              f'ln(EV/Sales) = {fit["a"]:.3f} + {fit["b"]:.3f} × {x:.3f} = {mid:.3f} → EV/Sales {xm(math.exp(mid))}',
              f'= ({xm(math.exp(mid))} × {money(rev)} {less_nd(nd)}) ÷ {num(sh)} = {ps(v)}; ±1 standard error ({fit["se"]:.2f} in logs): {ps(lo)} – {ps(hi)}'],
             [['Revenue, four quarters', money(rev), src_of(F, 'revenue')], ['Revenue growth', pc(F['g0']), 'last four quarters vs the four before'],
              ['Free cash flow', money(f), 'operating income × (1 − tax) + D&A − capex'], ['Net debt', money(nd), 'debt − cash + other claims']],
             [['Fit', f'a = {fit["a"]:.3f}, b = {fit["b"]:.3f}, n = {fit["n"]}, R² = {fit["r2"]:.2f}' if fin(fit.get('r2')) else f'n = {fit["n"]}',
               'every covered non-financial company with revenue ≥ $50M, today']])
    return {'method': 'EV/Sales vs Rule of 40 (all-company fit)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c,
            'note': f'Rule of 40 = {x * 100:.0f} → fitted EV/Sales {xm(math.exp(mid))} across {fit["n"]} companies'}


def sustainable_g(roe, payout):
    return clamp(roe * (1 - clamp(payout, 0.0, 1.0)), 0.0, G_CAP) if fin(roe) else 0.0


def justified_book(F, W, div, bank):
    sh, ke = F.get('shares'), (W or {}).get('ke')
    eq = F.get('equity')
    if not (fin(sh) and sh > 0 and fin(ke) and fin(eq) and eq > 0 and fin(F.get('ni'))):
        return None
    book = eq - (F.get('goodwill') or 0) - (F.get('intangibles') or 0) if bank else eq
    if book <= 0:
        return None
    roe = F['ni'] / book
    payout = (div or 0) / F['ni'] if F['ni'] > 0 else 1.0
    g = sustainable_g(roe, payout)
    if ke - g < 0.01 or roe <= g:
        return None
    per = lambda k: book / sh * (roe - g) / (k - g)
    v, lo, hi = per(ke), per(ke + 0.01), per(max(ke - 0.01, g + 0.01))
    B, R = ('TBV', 'ROTCE') if bank else ('B', 'ROE')
    c = calc(f'Justified P/{B} = ({R} − g) ÷ (kₑ − g); g = {R} × (1 − payout), capped at 0–{G_CAP:.0%}; value per share = {"tangible book" if bank else "book"} per share × justified P/{B}',
             [f'{R} = net income {money(F["ni"])} ÷ {"tangible " if bank else ""}book {money(book)} = {pc(roe)}',
              f'payout = dividends {money(div or 0)} ÷ net income = {pc(payout, 0)} → g = {pc(roe)} × (1 − {pc(payout, 0)}) → {pc(g)}',
              f'P/{B} = ({pc(roe)} − {pc(g)}) ÷ ({pc(ke)} − {pc(g)}) = {xm((roe - g) / (ke - g))}',
              f'= {ps(book / sh)} × {xm((roe - g) / (ke - g))} = {ps(v)}; cost of equity ±1 point: {ps(lo)} – {ps(hi)}'],
             [['Net income, four quarters', money(F['ni']), src_of(F, 'ni')], ['Equity', money(eq), src_of(F, 'equity')],
              *([['Goodwill + intangibles', money((F.get('goodwill') or 0) + (F.get('intangibles') or 0)), 'SEC XBRL frames']] if bank else []),
              ['Dividends paid, latest year', money(div or 0), 'SEC XBRL frames (PaymentsOfDividends)'], ['Diluted shares', num(sh), src_of(F, 'shares')]],
             [['Cost of equity', pc(ke), 'CAPM: 10-year Treasury + beta × ERP (build-up above)'], ['Growth cap', f'0–{G_CAP:.0%}', 'an assumption: a bank cannot outgrow the economy forever']])
    return {'method': f'Justified P/{B} (Gordon growth)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c,
            'note': f'{R} {pc(roe)}, g {pc(g)}, kₑ {pc(ke)} → P/{B} {xm((roe - g) / (ke - g))}'}


def ddm(F, W, div, reit, M):
    sh, ke = F.get('shares'), (W or {}).get('ke')
    if not (fin(sh) and sh > 0 and fin(ke) and fin(div) and div > 0):
        return None
    dps = div / sh
    if reit:
        g, gwhy = M.TERM_G, 'the base terminal growth (REITs pay out most of what they earn)'
    else:
        roe = F['ni'] / F['equity'] if fin(F.get('ni')) and fin(F.get('equity')) and F['equity'] > 0 else None
        g = sustainable_g(roe, div / F['ni'] if fin(F.get('ni')) and F['ni'] > 0 else 1.0)
        gwhy = f'ROE × (1 − payout), capped at 0–{G_CAP:.0%}'
    if ke - g < 0.01:
        return None
    per = lambda k: dps * (1 + g) / (k - g)
    v, lo, hi = per(ke), per(ke + 0.01), per(max(ke - 0.01, g + 0.01))
    c = calc('Value per share = DPS × (1 + g) ÷ (kₑ − g)  (Gordon growth dividend discount)',
             [f'DPS = dividends {money(div)} ÷ {num(sh)} shares = {ps(dps)}',
              f'= {ps(dps)} × (1 + {pc(g)}) ÷ ({pc(ke)} − {pc(g)}) = {ps(v)}; cost of equity ±1 point: {ps(lo)} – {ps(hi)}'],
             [['Dividends paid, latest year', money(div), 'SEC XBRL frames (PaymentsOfDividends)'], ['Diluted shares', num(sh), src_of(F, 'shares')]],
             [['Cost of equity', pc(ke), 'CAPM build-up above'], ['Dividend growth', pc(g), gwhy]])
    return {'method': 'Dividend discount (Gordon)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c,
            'note': f'dividend {ps(dps)}/share growing {pc(g)}, discounted at {pc(ke)}'}


# ---------------------------------------------------------------- the appendix
def _wacc_steps(W):
    if not W:
        return None
    return {'formula': 'WACC = wₑ × kₑ + w_d × k_d × (1 − t);  kₑ = r_f + β × ERP',
            'steps': [f'β (Blume-adjusted) = 0.67 × raw β {num(W.get("beta_raw"), 2)} + 0.33 = {num(W.get("beta"), 2)}'
                      + (f'  ({W.get("beta_weeks")} weekly returns vs SPY, R² {num(W.get("beta_r2"), 2)})' if W.get('beta_weeks') else f'  ({W.get("beta_note") or ""})'),
                      f'kₑ = {pc(W["rf"], 2)} + {num(W["beta"], 2)} × {pc(W["erp"])} = {pc(W["ke"], 2)}',
                      f'k_d = {pc(W["kd"], 2)}  ({W.get("kd_how")}); after tax {pc(W["kd"], 2)} × (1 − {pc(W["tax"], 0)}) = {pc(W["kd_after_tax"], 2)}',
                      f'weights (market values): equity {pc(W["w_equity"], 0)}, debt {pc(W["w_debt"], 0)}',
                      f'WACC = {pc(W["w_equity"], 0)} × {pc(W["ke"], 2)} + {pc(W["w_debt"], 0)} × {pc(W["kd_after_tax"], 2)} = {pc(W["raw"], 2)}'
                      + (f' → bounded to {pc(W["wacc"], 2)} (5–16%)' if fin(W.get('raw')) and abs(W['raw'] - W['wacc']) > 1e-9 else '')]}


def _derived(b, out, F, W, M):
    """A formula for the methods valuation.analyse draws without a calc of their own, from what it stored."""
    name, sh = b['method'], F.get('shares')
    d, mc = out.get('dcf') or {}, out.get('mc') or {}
    if name.startswith('DCF — Monte Carlo') and d:
        a = d.get('assumptions') or {}
        rows = d.get('rows') or []
        return calc('FCFF = EBIT × (1 − t) + D&A − capex − ΔWC;  EV = Σ FCFF/(1+WACC)^t + TV/(1+WACC)^5;  TV = NOPAT₆ × (1 − g ÷ ROIC) ÷ (WACC − g);  '
                    'value = (EV − debt + cash − claims) ÷ shares',
                    [f'growth by year {", ".join(pc(g, 0) for g in (a.get("growth") or []))}; EBIT margin {pc(a.get("margin"))}; D&A {pc(a.get("da"))} of revenue; '
                     f'capex {", ".join(pc(c) for c in a["capex"]) if isinstance(a.get("capex"), list) else pc(a.get("capex"))} of revenue; ΔWC {pc(a.get("wc"), 0)} of each revenue increase',
                     'FCFF by year: ' + ', '.join(f'{r[0]}: {money(r[3])}' for r in rows),
                     f'EV = {money(d.get("ev"))} (terminal value {pc(d.get("tv_share"), 0)} of it); equity = {money(d.get("equity"))}; ÷ {num(sh)} = {ps(d.get("value"))}',
                     f'Monte Carlo: {num(mc.get("n"))} scenarios, 10th–90th percentile {ps(mc.get("p10"))} – {ps(mc.get("p90"))}; P(value > price) = {pc(mc.get("p_above"), 0)}' if mc else ''],
                    [['Revenue, four quarters', money(F.get('revenue')), src_of(F, 'revenue')], ['Operating income', money(F.get('oi')), src_of(F, 'oi')],
                     ['D&A', money(F.get('da')), src_of(F, 'da')], ['Capex', money(F.get('capex')), src_of(F, 'capex')],
                     ['Debt', money(F.get('debt')), src_of(F, 'debt')], ['Cash', money(F.get('cash')), src_of(F, 'cash')], ['Diluted shares', num(sh), src_of(F, 'shares')]],
                    [['WACC', pc(a.get('wacc')), 'build-up above'], ['Terminal growth', pc(a.get('g')), 'fixed assumption'], ['Terminal ROIC', pc(a.get('roic')), "today's ROIC, bounded to 10–30%"],
                     ['Monte Carlo spreads', 'growth σ, margin σ from its own history; WACC ±1 pt; terminal growth 1.5–3%', 'the company\'s own variability']])
    if name.startswith('Regime-switching') and out.get('markov'):
        mk = out['markov']
        return calc('10-year Monte Carlo: revenue growth switches between high / steady / decline regimes by a Markov chain; margin drifts by regime; '
                    'value = Σ discounted FCFF − SBC + terminal, per share',
                    [f'{num(mk.get("n"))} paths; median {ps(mk.get("p50"))}, 10th–90th {ps(mk.get("p10"))} – {ps(mk.get("p90"))}'],
                    [], [['Transition matrix', 'its own history + the panel prior (markov.json)', 'app/markov.py']])
    pe = (out.get('peers') or {})
    for key, nm, base_label, base_val in (('pe', 'P/E vs peers', 'EPS, four quarters', F.get('eps')),
                                          ('ev_ebitda', 'EV/EBITDA vs peers', 'EBITDA, four quarters', F.get('ebitda')),
                                          ('ev_sales', 'EV/Sales vs peers', 'Revenue, four quarters', F.get('revenue'))):
        if name == nm and key in pe:
            p = pe[key]
            nd = (F.get('debt') or 0) - (F.get('cash') or 0) + (F.get('claims') or 0)
            st = ([f'= {xm(p["p50"], 1)} × {ps(base_val)} = {ps(b.get("point"))}  (middle half of peers {xm(p["p25"], 1)} – {xm(p["p75"], 1)} → {ps(b.get("low"))} – {ps(b.get("high"))})']
                  if key == 'pe' else
                  [f'= ({xm(p["p50"], 1)} × {money(base_val)} {less_nd(nd)}) ÷ {num(sh)} = {ps(b.get("point"))}  (peers {xm(p["p25"], 1)} – {xm(p["p75"], 1)} → {ps(b.get("low"))} – {ps(b.get("high"))})'])
            return calc('Value per share = peer median P/E × EPS' if key == 'pe' else f'Value per share = (peer median {nm.split(" vs")[0]} × {base_label.split(",")[0]} − net debt) ÷ shares',
                        st, [[base_label, ps(base_val) if key == 'pe' else money(base_val), 'SEC XBRL frames / main site'], ['Net debt', money(nd), 'debt − cash + claims']],
                        [['Peer group', f'{p.get("n")} companies', f'narrowest SIC group with ≥ 6 peers ({p.get("group")})'], ['Own multiple today', xm(p.get('own'), 1), 'market value ÷ the same figure']])
    if name == 'Residual income' and out.get('residual_income'):
        ri = out['residual_income']
        return calc('Value = book + Σ (ROEₜ − kₑ) × Bookₜ₋₁ ÷ (1 + kₑ)ᵗ over 10 years; ROE fades linearly to kₑ; half of earnings retained',
                    [f'book {money(ri.get("book"))} ({ps(ri["book"] / sh) if fin(sh) and sh else "—"}/share), ROE {pc(ri.get("roe"))}, kₑ {pc(ri.get("ke"))}',
                     f'= {ps(ri.get("value"))} per share; kₑ ±1 point: {ps(b.get("low"))} – {ps(b.get("high"))}'],
                    [['Equity', money(F.get('equity')), src_of(F, 'equity')], ['Net income, four quarters', money(F.get('ni')), src_of(F, 'ni')]],
                    [['Cost of equity', pc(ri.get('ke')), 'CAPM build-up above'], ['Fade', '10 years to kₑ', 'fixed assumption'], ['Retention', '50%', 'fixed assumption']])
    sm = out.get('sector_model') or {}
    if name.startswith('P/TBV vs ROTCE') and sm.get('fit'):
        f = sm['fit']
        return calc('P/TBV = a + b × ROTCE (fitted across banks); value per share = fitted P/TBV × tangible book per share',
                    [f'ROTCE = {money(F.get("ni"))} ÷ TBV {money(sm.get("tbv"))} = {pc(sm.get("rotce"))}',
                     f'P/TBV = {f["a"]:.3f} + {f["b"]:.3f} × {sm.get("rotce", 0):.4f} = {xm(sm.get("fitted_ptbv"))} (today {xm(sm.get("ptbv"))})',
                     f'= {xm(sm.get("fitted_ptbv"))} × {ps(sm["tbv"] / sh) if fin(sh) and sh else "—"} = {ps(b.get("point"))}; ± the fit\'s standard error: {ps(b.get("low"))} – {ps(b.get("high"))}'],
                    [['Tangible book', money(sm.get('tbv')), 'equity − goodwill − intangibles (SEC XBRL frames)'], ['Net income', money(F.get('ni')), src_of(F, 'ni')]],
                    [['Fit', f'{f.get("n")} banks', 'every covered bank today (banks.json)']])
    if name.startswith('P/B vs ROE') and sm.get('fit'):
        f = sm['fit']
        return calc('P/B = a + b × ROE (fitted across insurers); value per share = fitted P/B × book per share',
                    [f'ROE = {pc(sm.get("roe"))}; P/B = {f["a"]:.3f} + {f["b"]:.3f} × {sm.get("roe", 0):.4f} = {xm(sm.get("fitted_pb"))} (today {xm(sm.get("pb"))})',
                     f'= {ps(b.get("point"))}; ± standard error {ps(b.get("low"))} – {ps(b.get("high"))}'],
                    [['Equity', money(F.get('equity')), src_of(F, 'equity')], ['Combined ratio', pc(sm.get('combined_ratio')), 'claims + acquisition + underwriting costs ÷ premiums']],
                    [['Fit', f'{f.get("n")} insurers', 'insurers.json']])
    if name.startswith('P/FFO') and sm.get('ffo'):
        fp, pr = sm.get('ffo_parts') or {}, sm.get('peers') or {}
        return calc('FFO = net income + D&A − gains on property sales; value per share = peer median P/FFO × FFO ÷ shares',
                    [f'FFO = {money(fp.get("net_income"))} + {money(fp.get("da"))} − {money(fp.get("gains_on_sales"))} = {money(sm["ffo"])}',
                     f'= {xm(pr.get("p50"), 1)} × {money(sm["ffo"])} ÷ {num(sh)} = {ps(b.get("point"))}  ({xm(pr.get("p25"), 1)} – {xm(pr.get("p75"), 1)})'],
                    [['Net income, D&A, gains', 'see above', 'SEC XBRL frames']], [['Peers', f'{pr.get("n")} REITs', 'P/FFO of every covered REIT']])
    if name.startswith('Sum of the parts') and out.get('sotp'):
        so = out['sotp']
        return calc('Value = (Σ segment revenue × its peer EV/Sales − net debt) ÷ shares',
                    [f'{s.get("segment")}: {money(s.get("revenue"))} (latest quarter × 4) × {xm(s.get("ev_sales"), 1)} = {money(s.get("ev"))}' for s in (so.get('parts') or [])][:8]
                    + [f'= {ps(b.get("point"))} ({ps(b.get("low"))} – {ps(b.get("high"))} at the peers\' quartiles)'],
                    [['Segments', f'{len(so.get("parts") or [])}', 'the 10-K/10-Q segment note (main site)']], [['Multiples', 'median EV/Sales of the industry each segment name maps to', 'peers.json']])
    if name in ("Analysts' price targets", 'Polymarket implied price') or name.startswith(('Our model', 'Rotation forecast', 'Combined forecast', '52-week')):
        srcs = {"Analysts' price targets": 'Yahoo Finance consensus targets (app/consensus.py)', 'Polymarket implied price': 'Polymarket price-range markets (app/consensus.py)',
                '52-week trading range': 'daily closes'}
        return calc('Not a model of value: an outside or market figure shown for comparison', [b.get('note') or ''], [],
                    [['Source', srcs.get(name, 'the Rotation / combined forecasts (forecast ledger, walk-forward)'), '']], kind='reference')
    if name.startswith('Stage-weighted'):
        used = (out.get('stage') or {}).get('used') or []
        return calc('Stage-weighted value = Σ weight × central value of the stage\'s methods (weights renormalized over the methods available)',
                    [' + '.join(f'{u["weight"] * 100:.0f}% × {ps(u["point"])} ({u["method"]})' for u in used) + f' = {ps(b.get("point"))}'], [],
                    [['Weights', (out.get('stage') or {}).get('label', ''), 'fixed by stage before any result was seen (base_rates.STAGES)']], kind='blend')
    if name.startswith('Outside view'):
        return calc('The same DCF with growth, margin, WACC and terminal growth drawn from what peers did (SIC industry × size) instead of its own history',
                    [b.get('note') or ''], [], [['Peer distributions', 'base_rates.json', 'SEC XBRL frames since 2010']])
    return calc('', [b.get('note') or ''], [], [])


CANDIDATES = {   # every method the build knows, by company type: what it needs (for "not used, because …")
    'industrial': ['DCF — Monte Carlo 10th–90th percentile', 'Regime-switching Monte Carlo 10th–90th', 'Outside view — base-rate Monte Carlo',
                   'P/E vs peers', 'EV/EBITDA vs peers', 'EV/Sales vs peers', 'Residual income', 'Owner earnings capitalized',
                   'Shareholder yield (dividends + buybacks)', 'Normalized (mid-cycle) P/E', 'Normalized (mid-cycle) DCF', 'Path-to-margin DCF',
                   'Path-to-margin DCF, dilution-adjusted', 'Exit-multiple (venture) method', 'Survival-weighted value',
                   'EV/Sales vs Rule of 40 (all-company fit)', 'Tangible book (asset value)', 'Net cash (floor)', 'Sum of the parts (segments × peer EV/Sales)'],
    'bank': ['Residual income', 'P/TBV vs ROTCE (bank peers)', 'Justified P/TBV (Gordon growth)', 'Dividend discount (Gordon)', 'P/E vs peers'],
    'insurer': ['Residual income', 'P/B vs ROE (insurer peers)', 'Justified P/B (Gordon growth)', 'Dividend discount (Gordon)', 'P/E vs peers'],
    'reit': ['P/FFO vs REIT peers', 'Dividend discount (Gordon)', 'Residual income', 'P/E vs peers'],
}
WHY_NOT = {
    'DCF — Monte Carlo 10th–90th percentile': 'needs positive operating income (a cash-flow model on a loss only restates its assumptions); not used for banks, insurers or REITs',
    'Regime-switching Monte Carlo 10th–90th': 'needs the DCF and at least a few years of revenue history',
    'Outside view — base-rate Monte Carlo': 'needs the DCF and enough peer history',
    'P/E vs peers': 'needs positive EPS and six or more peers in its SIC group',
    'EV/EBITDA vs peers': 'needs positive EBITDA and six or more peers',
    'EV/Sales vs peers': 'needs revenue and six or more peers',
    'Residual income': 'needs positive equity and net income',
    'Owner earnings capitalized': 'needs positive owner earnings (net income + D&A − capex)',
    'Shareholder yield (dividends + buybacks)': 'pays no dividends and buys back no shares',
    'Normalized (mid-cycle) P/E': 'only for cyclical companies (industry or margin σ above 8 points)',
    'Normalized (mid-cycle) DCF': 'only for cyclical companies',
    'Path-to-margin DCF': 'only for companies with an operating loss and revenue growth ≥ 10%',
    'Path-to-margin DCF, dilution-adjusted': 'only for companies with an operating loss and revenue growth ≥ 10%',
    'Exit-multiple (venture) method': 'only for pre-profit companies with a peer P/E',
    'Survival-weighted value': 'only for companies burning cash (negative free cash flow) with a going-concern value and a failure estimate',
    'EV/Sales vs Rule of 40 (all-company fit)': 'only for high-growth and pre-profit companies',
    'Tangible book (asset value)': 'only at the decline / turnaround and pre-revenue stages',
    'Net cash (floor)': 'only for pre-revenue companies',
    'Sum of the parts (segments × peer EV/Sales)': 'needs two or more reported segments',
    'P/TBV vs ROTCE (bank peers)': 'needs positive tangible book and the bank fit',
    'P/B vs ROE (insurer peers)': 'needs positive book and the insurer fit',
    'Justified P/TBV (Gordon growth)': 'needs positive tangible book, net income and ROTCE above its growth',
    'Justified P/B (Gordon growth)': 'needs positive book, net income and ROE above its growth',
    'Dividend discount (Gordon)': 'pays no dividend (or its cost of equity is within a point of its growth)',
    'P/FFO vs REIT peers': 'needs positive FFO and REIT peers',
}


def fit_reason(name, F, out):
    """Why this method applies to this company, in one or two sentences from its own figures (the appendix's
    "Why it applies here"; what each method is and why it works in general is in docs/valuation-guide.json)."""
    import valuation_extra as VX
    lens = VX.fit_reason(name, F, out)
    if lens:
        return lens
    st = out.get('stage') or {}
    m = st.get('metrics') or {}
    rev, oi, ni, eps, g0 = F.get('revenue'), F.get('oi'), F.get('ni'), F.get('eps'), F.get('g0')
    peers = out.get('peers') or {}
    stage = f'the {st["label"].lower()} stage' if st.get('label') else 'its stage'
    grow = f', revenue growth {pc(g0, 0)}' if fin(g0) else ''
    fcf = m.get('fcf') if fin(m.get('fcf')) else fcf_of(F)

    def peer(key, what):
        p = peers.get(key) or {}
        grp = str(p.get('group') or '').replace('sic', 'SIC ').replace('sec:', 'sector ')
        return f'{what}, and {p["n"]} peers ({grp}) have the multiple.' if p.get('n') else f'{what}.'
    if name.startswith('DCF — Monte Carlo'):
        return (f'Operating income is positive ({money(oi)} over four quarters{grow}), so its margins can be projected and '
                'its cash flows discounted.')
    if name.startswith('Regime-switching'):
        return 'It has a DCF and enough quarters of revenue history to estimate how often its growth switches regime.'
    if name.startswith('Outside view'):
        return ((f'Its recent revenue growth is {pc(g0, 0)}. ' if fin(g0) else '') + 'This checks its own DCF against what companies of '
                'its industry and size actually achieved, so that optimism in its forecast is caught.')
    if name == 'P/E vs peers':
        return peer('pe', f'EPS is positive ({ps(eps)} over four quarters)')
    if name == 'EV/EBITDA vs peers':
        return peer('ev_ebitda', f'EBITDA is positive ({money(F.get("ebitda"))})')
    if name == 'EV/Sales vs peers':
        why = ' — the measure that still works without profit' if fin(oi) and oi <= 0 else ''
        return peer('ev_sales', f'It has revenue ({money(rev)} over four quarters){why}')
    if name == 'Residual income':
        return (f'Equity is positive ({money(F.get("equity"))}) and so is net income ({money(ni)}), so the return it earns on '
                'book value can be compared with what shareholders require.')
    if name == 'Owner earnings capitalized':
        return (f'Owner earnings are positive ({money(m.get("owner_earnings"))} = net income + D&A − capex), and at {stage} '
                'today\'s cash earnings are a sound base.')
    if name.startswith('Shareholder yield'):
        sy = m.get('shareholder_yield')
        return 'It returns cash to shareholders through dividends or buybacks' + (f' ({pc(sy)} of market value a year).' if fin(sy) else '.')
    if name.startswith('Normalized'):
        sig = m.get('margin_sigma')
        return (f'It is at the cyclical stage ({st.get("why") or "a cyclical industry"})'
                + (f'; its quarterly operating margin has a σ of {sig * 100:.0f} points' if fin(sig) else '')
                + (f', so the mid-cycle margin ({pc(m.get("mid_cycle_margin"))}) replaces the latest one.' if fin(m.get('mid_cycle_margin')) else
                   ', so a mid-cycle margin replaces the latest one.'))
    if name.startswith('Path-to-margin DCF'):
        tm = m.get('target_margin')
        s = (f'It has an operating loss ({money(oi)})' + (f' with revenue growth of {pc(g0, 0)}' if fin(g0) else '')
             + ', so a DCF needs a path to profit' + (f' — here to the peer median margin of {pc(tm)} by year five.' if fin(tm) else '.'))
        return s + (' Its losses must be funded, and the new shares that would take are counted.' if 'dilution' in name else '')
    if name.startswith('Exit-multiple'):
        return f'It is not yet profitable ({money(oi)} operating income{grow}), so its value lies in what it can earn once it matures.'
    if name.startswith('Survival-weighted'):
        rw = m.get('cash_runway_years')
        return (f'It is burning cash (free cash flow {money(fcf)} a year' + (f', a runway of {num(rw, 1)} years' if fin(rw) else '')
                + '), so its value must allow for the chance it does not survive.')
    if name.startswith('EV/Sales vs Rule of 40'):
        r40 = m.get('rule_of_40')
        return (f'At {stage}, growth and cash generation drive the price: its Rule of 40 score is ' + (f'{num(r40, 0)}' if fin(r40) else 'not available')
                + (f' (growth {pc(g0, 0)} + free-cash-flow margin {pc(m.get("fcf_margin"), 0)}).' if fin(g0) and fin(m.get('fcf_margin')) else '.'))
    if name.startswith('Tangible book'):
        tb = m.get('tangible_book_ps')
        return f'At {stage} what its assets would fetch matters' + (f'; tangible book is {ps(tb)} a share.' if fin(tb) else '.')
    if name.startswith('Net cash'):
        return (f'It is pre-revenue ({money(rev)} of revenue over four quarters, with an operating loss): its cash is the one solid number, '
                'and the rest of the price is a bet on its pipeline.')
    if name.startswith('Sum of the parts'):
        n = len((out.get('sotp') or {}).get('parts') or [])
        return f'It reports {n} revenue segments, which can deserve different multiples.'
    if name.startswith(('P/TBV vs ROTCE', 'Justified P/TBV')):
        return 'It is a bank: its balance sheet is its business, so value follows its tangible book and the return it earns on it.'
    if name.startswith(('P/B vs ROE', 'Justified P/B')):
        return 'It is an insurer: its equity backs the policies it writes, so value follows its book and the return it earns on it.'
    if name.startswith('Dividend discount'):
        return 'It pays a steady dividend, which for its owners is the cash the business hands over.'
    if name.startswith('P/FFO'):
        return 'It is a REIT, so funds from operations (FFO), not net income, measures its recurring earnings.'
    if name.startswith('Stage-weighted'):
        return (f'Its stage is “{st.get("label", "—")}”' + (f' — {st["why"]} —' if st.get('why') else '')
                + ' which fixes these methods and their weights in advance.')
    return 'Shown for comparison; not part of the stage-weighted value.'


def appendix(M, out, F, W, rates):
    """Every input with its source, every assumption with its basis, the cost of capital step by step, and every
    method's formula with this company's numbers — then the methods that do not apply."""
    src = F.get('src') or {}
    inputs = [[lab, fmt(F.get(k)), nice_src(src.get(k)) or dflt] for lab, k, fmt, dflt in (
        ('Price', 'price', ps, 'daily close (the hub\'s price cache)'), ('Revenue, four quarters', 'revenue', money, 'SEC XBRL frames'),
        ('Operating income, four quarters', 'oi', money, 'SEC XBRL frames'), ('Net income, four quarters', 'ni', money, 'SEC XBRL frames'),
        ('Diluted EPS, four quarters', 'eps', ps, 'SEC XBRL frames'), ('D&A', 'da', money, 'SEC XBRL frames'), ('Capital spending', 'capex', money, 'SEC XBRL frames'),
        ('Interest expense', 'interest', money, 'debt module'), ('Stock-based compensation', 'sbc', money, 'SEC XBRL frames'),
        ('Tax rate', 'tax_rate', lambda v: pc(v, 0), 'tax ÷ pretax income (0–35%, else 21%)'), ('Diluted shares', 'shares', num, 'SEC XBRL frames'),
        ('Debt', 'debt', money, 'SEC XBRL frames'), ('Cash and investments', 'cash', money, 'SEC XBRL frames'),
        ('Other claims (minority interest, preferred)', 'claims', money, 'main site'), ('Equity', 'equity', money, 'SEC XBRL frames'),
        ('Goodwill', 'goodwill', money, 'SEC XBRL frames'), ('Intangibles', 'intangibles', money, 'SEC XBRL frames'),
        ('Market value', 'mcap', money, 'price × diluted shares'), ('Enterprise value', 'ev', money, 'market value + debt − cash + claims'),
        ('Revenue growth', 'g0', pc, 'last four quarters vs the four before (main site revenue history)'),
        ('Total assets', 'assets', money, 'SEC XBRL frames (Assets)'), ('Current assets', 'ca', money, 'SEC XBRL frames (AssetsCurrent)'),
        ('Total liabilities', 'liab', money, 'SEC XBRL frames (Liabilities)'), ('PP&E, net', 'ppe', money, 'SEC XBRL frames (PropertyPlantAndEquipmentNet)'),
        ('Dividends paid, latest year', 'div', money, 'SEC XBRL frames (PaymentsOfDividends)'),
        ('Buybacks, latest year', 'buyback', money, 'SEC XBRL frames (PaymentsForRepurchaseOfCommonStock)')) if fin(F.get(k))]
    glob = [['Equity risk premium', pc(M.ERP), 'a fixed assumption (long-run US average, not estimated here)'],
            ['10-year Treasury', pc((rates.get('treasury_10y') or 0) / 100, 2) if fin(rates.get('treasury_10y')) else '—', 'FRED DGS10 (via app/debt.py)'],
            ['5-year Treasury', pc((rates.get('treasury_5y') or 0) / 100, 2) if fin(rates.get('treasury_5y')) else '—', 'US Treasury yield curve (app/debt.py)'],
            ['Terminal growth', pc(M.TERM_G), 'a fixed assumption: about long-run nominal GDP growth, below the risk-free rate'],
            ['Forecast years', str(M.YEARS), 'fixed'], ['Working capital', f'{M.WC_SHARE:.0%} of each revenue increase', 'a fixed assumption'],
            ['Monte Carlo scenarios', num(M.MC_N), 'seeded by ticker (reproducible)'],
            ['Stage premium (exit-multiple method)', pc(STAGE_PREMIUM, 0), 'an assumption: the hurdle growth investors add to the CAPM rate'],
            ['Liquidation haircut', f'{1 - LIQ_HAIRCUT:.0%}', 'an assumption for a forced sale of tangible assets'],
            ['Gordon growth cap', f'0–{G_CAP:.0%}', 'an assumption'],
            ["Moody's Aaa corporate yield", f'{rates["aaa"]:.2f}%' if fin(rates.get('aaa')) else '—', 'FRED DAAA (via app/debt.py): the Graham formula\'s Y']]
    st = out.get('stage') or {}
    wts = {u['method']: u['weight'] for u in st.get('used') or []}
    methods, seen = [], set()
    for b in out.get('football') or []:
        c = b.pop('calc', None) or _derived(b, out, F, W, M)
        seen.add(b['method'])
        methods.append({'method': b['method'], 'low': b.get('low'), 'point': b.get('point'), 'high': b.get('high'), 'weight': wts.get(b['method']), **c,
                        'fit': fit_reason(b['method'], F, out)})
    kind = F.get('kind') if F.get('kind') in CANDIDATES else 'industrial'
    import valuation_extra as VX
    lens = VX.CANDIDATES if kind == 'industrial' else [m for m in VX.CANDIDATES if m in ('Graham number', 'Graham formula (revised)', 'Lynch fair P/E (PEGY)', 'H-model dividend discount')]
    why = {**WHY_NOT, **VX.WHY_NOT, **(out.get('lens_why') or {})}
    not_used = [{'method': m, 'why': why.get(m, 'not enough data')} for m in CANDIDATES[kind] + lens if m not in seen]
    out['appendix'] = {'inputs': inputs, 'assumptions': glob, 'wacc': _wacc_steps(W), 'methods': methods, 'not_used': not_used,
                       'stage': {'key': st.get('stage'), 'label': st.get('label'), 'why': st.get('why'), 'rule': st.get('rule'),
                                 'weights': [[m['method'], m['weight']] for m in st.get('methods') or []
                                             if kind == 'industrial' or m['method'] in CANDIDATES[kind]]},   # a bank is not shown the insurer fit
                       'note': 'Every figure above is from the company\'s SEC filings (XBRL frames, or the main site\'s reading of its 10-K/10-Q), '
                               'the hub\'s daily prices, the debt module or the consensus module, as each line says; every assumption is fixed '
                               'in the code before any result is seen. History and models, not investment advice.'}
    return out['appendix']
