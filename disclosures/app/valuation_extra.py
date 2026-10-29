"""More ways to value a company, for the Fair value view (app/valuation.py calls extra() for every company), and the
return today's price implies.

Lenses (football items with 'lens': True — shown with their algebra in the appendix, kept out of the stage-weighted value
and the headline range until the walk-forward ledger has scored them):

  Graham number                 √(22.5 × EPS × book value per share): the most a defensive investor should pay — at most
                                15× earnings and 1.5× book (22.5 = 15 × 1.5). Range: the product of the two multiples
                                from 15 (10 × 1.5) to 30 (15 × 2).
  Graham formula (revised)      EPS × (8.5 + 2g) × 4.4 ÷ Y: 8.5 = the P/E of a company that does not grow, g = expected
                                yearly growth in percent (analysts' next-year EPS growth, else its own revenue growth,
                                0–15%), 4.4 = the AAA corporate yield in 1962, Y = Moody's Aaa yield today (FRED DAAA).
  Net current asset value       (current assets − total liabilities − other claims) ÷ shares: what holders would keep if
    (net-net)                   the fixed assets were worth nothing; Graham bought below two-thirds of it.
  Lynch fair P/E (PEGY)         EPS × (growth + dividend yield, in percent): Peter Lynch's rule that a fairly priced
                                company's P/E equals its growth rate plus its yield (P/E between 5 and 40).
  Earnings power value (EPV)    Greenwald: the value of today's business if it never grows — normalized operating profit
                                (the average margin of up to five years × today's revenue) × (1 − tax) + D&A − maintenance
                                capex (capex less the part that funded growth: PP&E ÷ revenue × last year's revenue gain),
                                divided by the WACC, less net debt. Price − EPV is what the market pays for growth.
  FCFE DCF                      the cash left for shareholders: net income − (1 − d) × (capex − D&A + ΔWC), d = the debt
                                share of capital (new borrowing funds that share of reinvestment), five years on the DCF's
                                growth path, then a perpetuity of net income × (1 − g ÷ ROE), discounted at the cost of
                                equity.
  H-model dividend discount     D₀ × [(1 + g_L) + H × (g_S − g_L)] ÷ (kₑ − g_L): dividend growth falls in a straight line
                                from g_S (ROE × retention, 0–10%) to g_L (the terminal growth) over 2H = 10 years.
  Real option to expand         Black-Scholes: the expansion (the revenue it adds by year 5 on its growth path × the mature
                                margin — the peer median, or today's when already profitable — valued as a growing
                                perpetuity, discounted) is the underlying; the capital it needs (that revenue ÷ its sales-to-
                                capital ratio) is the strike; the stock's own volatility; 5 years; the 5-year Treasury.
                                Value = (assets in place, today's NOPAT ÷ WACC + the option − net debt) ÷ shares.
  EV/Sales fair multiple        ln(EV/Sales) = a + b₁ growth + b₂ ln(operating margin, at least 0.5%) + b₃ loss flag +
    (multi-factor fit)          b₄ ln(revenue) + sector effects (EV/Sales = EV/EBIT × margin, so the margin enters in logs), a
                                ridge regression across every covered non-financial company; its fitted EV/Sales ± one
                                residual standard error.

Implied return (out['implied_return']): the yearly return today's price gives a buyer if the model is right — the
discount rate at which the base-case DCF equals the price; owner-earnings yield + long-run growth (Gordon); Easton's
PEG / MPEG model from analysts' next two years of EPS and the dividend; the cost of equity at which residual income equals
the price. Their median, against the cost of equity and the WACC.

EPV split (out['epv']): EPV per share, today's price and tangible book per share — the price's split between the
business as it is and its growth (Greenwald's franchise test: EPV above the asset value means a moat).
"""
import math

GRAHAM_PE, GRAHAM_PB = 15.0, 1.5
GRAHAM_NO_GROWTH = 8.5
GRAHAM_Y0 = 4.4                 # the AAA yield in 1962, Graham's base
G_CAP_GRAHAM = 0.15
H_YEARS = 5                     # H-model: half the fade (10 years from g_S to g_L)
OPT_YEARS = 5
SALES_TO_CAPITAL = 1.5          # when its own invested capital is not on file (Damodaran's US median is about 1.5)
FIT_MIN = 60                    # companies needed for the multi-factor fit
RIDGE = 1.0


def fin(v):
    return v is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_call(S, K, T, r, sigma):
    """Black-Scholes call. S, K > 0."""
    if not (S > 0 and K > 0 and T > 0 and sigma > 0):
        return max(0.0, S - K * math.exp(-r * T))
    d1 = (math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2)


def _bvps(F):
    sh, eq = F.get('shares'), F.get('equity')
    return eq / sh if fin(sh) and sh > 0 and fin(eq) else None


def _nd(F):
    return (F.get('debt') or 0) - (F.get('cash') or 0) + (F.get('claims') or 0)


def eps_growth(F, cons_c):
    """Expected yearly EPS growth: analysts' next-year EPS growth (3+ analysts), else its own revenue growth."""
    per = {p.get('period'): p for p in ((cons_c or {}).get('analysts') or {}).get('periods') or []}
    for key in ('+1y', '0y'):
        e = (per.get(key) or {}).get('eps') or {}
        if fin(e.get('growth')) and fin(e.get('numberOfAnalysts')) and e['numberOfAnalysts'] >= 3 and -0.9 < e['growth'] < 3:
            return e['growth'], f"analysts' {'next' if key == '+1y' else 'current'}-year EPS growth ({int(e['numberOfAnalysts'])} analysts)"
    if fin(F.get('g0')):
        return F['g0'], 'its own revenue growth, last four quarters on the four before'
    return None, None


def forward_eps(cons_c):
    per = {p.get('period'): p for p in ((cons_c or {}).get('analysts') or {}).get('periods') or []}
    e0, e1 = ((per.get('0y') or {}).get('eps') or {}), ((per.get('+1y') or {}).get('eps') or {})
    if fin(e0.get('avg')) and fin(e1.get('avg')) and (e0.get('numberOfAnalysts') or 0) >= 3:
        return e0['avg'], e1['avg']
    return None, None


# ---------------------------------------------------------------- the lenses
def graham_number(V, F):
    eps, bv = F.get('eps'), _bvps(F)
    if not (fin(eps) and eps > 0 and fin(bv) and bv > 0):
        return None
    f = lambda k: math.sqrt(k * eps * bv)
    v, lo, hi = f(GRAHAM_PE * GRAHAM_PB), f(10 * 1.5), f(15 * 2.0)
    c = V.calc('Graham number = √(22.5 × EPS × book value per share);  22.5 = a P/E of 15 × a P/B of 1.5',
               [f'= √(22.5 × {V.ps(eps)} × {V.ps(bv)}) = {V.ps(v)}',
                f'Range: P/E × P/B from 15 (10 × 1.5) to 30 (15 × 2): {V.ps(lo)} – {V.ps(hi)}'],
               [['Diluted EPS, four quarters', V.ps(eps), V.src_of(F, 'eps')], ['Equity', V.money(F.get('equity')), V.src_of(F, 'equity')],
                ['Diluted shares', V.num(F.get('shares')), V.src_of(F, 'shares')]],
               [['Most a defensive investor pays', '15× earnings and 1.5× book', 'Benjamin Graham, The Intelligent Investor (1949; 1973 edition, ch. 14)']])
    return {'method': 'Graham number', 'low': lo, 'high': hi, 'point': v, 'calc': c, 'lens': True,
            'note': f'√(22.5 × EPS {V.ps(eps)} × book {V.ps(bv)})'}


def graham_formula(V, F, cons_c, aaa):
    eps = F.get('eps')
    g, gwhy = eps_growth(F, cons_c)
    if not (fin(eps) and eps > 0 and fin(g) and fin(aaa) and aaa > 0.5):
        return None
    gc = clamp(g, 0.0, G_CAP_GRAHAM)
    f = lambda gg: eps * (GRAHAM_NO_GROWTH + 2 * gg * 100) * GRAHAM_Y0 / aaa
    v, lo, hi = f(gc), f(max(0.0, gc - 0.03)), f(min(G_CAP_GRAHAM + 0.03, gc + 0.03))
    c = V.calc('Value = EPS × (8.5 + 2g) × 4.4 ÷ Y;  g = expected yearly growth in percent, Y = the AAA corporate yield today',
               [f'g = {V.pc(g)}' + (f' → capped to {V.pc(gc)}' if abs(gc - g) > 1e-9 else '') + f' ({gwhy})',
                f'= {V.ps(eps)} × (8.5 + 2 × {gc * 100:.1f}) × 4.4 ÷ {aaa:.2f} = {V.ps(v)}',
                f'Growth ±3 points: {V.ps(lo)} – {V.ps(hi)}'],
               [['Diluted EPS, four quarters', V.ps(eps), V.src_of(F, 'eps')], ["Moody's Aaa corporate yield", f'{aaa:.2f}%', 'FRED DAAA (via the Debt & rates module)']],
               [['8.5', 'the P/E of a company that does not grow', 'Graham, 1962 / 1974'], ['4.4', 'the AAA yield when Graham set the formula', 'Graham, 1974 revision'],
                ['Growth cap', f'0–{G_CAP_GRAHAM:.0%}', 'an assumption: the formula overstates value at high growth']])
    return {'method': 'Graham formula (revised)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c, 'lens': True,
            'note': f'EPS {V.ps(eps)} × (8.5 + 2 × {gc * 100:.0f}) × 4.4 ÷ AAA {aaa:.2f}%'}


def ncav(V, F):
    sh, ca, liab = F.get('shares'), F.get('ca'), F.get('liab')
    if not (fin(sh) and sh > 0 and fin(ca) and ca > 0 and fin(liab) and liab >= 0):
        return None
    n = ca - liab - (F.get('claims') or 0)
    v = n / sh
    c = V.calc('Net current asset value per share = (current assets − total liabilities − other claims) ÷ shares;  a net-net trades below two-thirds of it',
               [f'= ({V.money(ca)} − {V.money(liab)} − {V.money(F.get("claims") or 0)}) ÷ {V.num(sh)} = {V.ps(v)}',
                (f'Graham\'s buy price: ⅔ × {V.ps(v)} = {V.ps(v * 2 / 3)}' if v > 0 else 'Negative: the liabilities exceed the current assets — no net-net value')],
               [['Current assets', V.money(ca), V.src_of(F, 'ca', 'SEC XBRL frames (AssetsCurrent)')],
                ['Total liabilities', V.money(liab), V.src_of(F, 'liab', 'SEC XBRL frames (Liabilities)')], ['Diluted shares', V.num(sh), V.src_of(F, 'shares')]],
               [['Fixed assets, goodwill, the business itself', 'valued at 0', 'Graham, Security Analysis (1934): a liquidation floor']])
    if v <= 0:
        return {'method': 'Net current asset value (net-net)', 'negative': v}
    return {'method': 'Net current asset value (net-net)', 'low': v * 2 / 3, 'high': v, 'point': v, 'calc': c, 'lens': True,
            'note': f'current assets − all liabilities = {V.money(n)}; Graham bought below ⅔ ({V.ps(v * 2 / 3)})'}


def lynch_pegy(V, F, cons_c):
    eps, sh, price = F.get('eps'), F.get('shares'), F.get('price')
    g, gwhy = eps_growth(F, cons_c)
    if not (fin(eps) and eps > 0 and fin(g) and fin(price) and price > 0):
        return None
    y = (F.get('div') or 0) / sh / price if fin(sh) and sh > 0 and fin(F.get('div')) else 0.0
    gc = clamp(g, 0.0, 0.35)
    pe = lambda gg: clamp((gg + y) * 100, 5.0, 40.0)
    v, lo, hi = eps * pe(gc), eps * pe(max(0.0, gc - 0.05)), eps * pe(gc + 0.05)
    own = price / eps
    pegy = own / ((gc + y) * 100) if gc + y >= 0.005 else None
    c = V.calc('Fair P/E = growth + dividend yield, in percent (5–40);  value = EPS × fair P/E;  PEGY = P/E ÷ (growth + yield)',
               [f'growth {V.pc(g)}' + (f' → {V.pc(gc)}' if abs(gc - g) > 1e-9 else '') + f' ({gwhy}); dividend yield {V.pc(y)}',
                f'fair P/E = {gc * 100:.1f} + {y * 100:.1f} = {pe(gc):.1f} → {V.ps(eps)} × {pe(gc):.1f} = {V.ps(v)}',
                (f'today P/E {own:.1f} → PEGY {pegy:.2f} (below 1: cheap for its growth, above 2: dear)' if pegy else f'today P/E {own:.1f}; no growth or yield: PEGY not defined'),
                f'Growth ±5 points: {V.ps(lo)} – {V.ps(hi)}'],
               [['Diluted EPS, four quarters', V.ps(eps), V.src_of(F, 'eps')], ['Dividends paid, latest year', V.money(F.get('div') or 0), 'SEC XBRL frames (PaymentsOfDividends)']],
               [['Fair P/E = growth + yield', 'Peter Lynch, One Up on Wall Street (1989)', 'a rule of thumb, not a model of cash flows'],
                ['Growth used', f'0–35%; {gwhy}', 'analysts look one or two years ahead; Lynch meant several']])
    return {'method': 'Lynch fair P/E (PEGY)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c, 'lens': True,
            'note': f'fair P/E {pe(gc):.0f} = growth {gc * 100:.0f} + yield {y * 100:.1f}; today {own:.1f}' + (f' (PEGY {pegy:.2f})' if pegy else '')}


def epv(V, F, W, years):
    """Earnings power value and the growth split."""
    sh, rev, wacc = F.get('shares'), F.get('revenue'), (W or {}).get('wacc')
    if not (fin(sh) and sh > 0 and fin(rev) and rev > 0 and fin(wacc) and wacc > 0.02):
        return None, None
    ms = [m for _, m in (years or []) if fin(m)][-5:]
    if len(ms) >= 3:
        mbar, mhow = sum(ms) / len(ms), f'average EBIT margin of the last {len(ms)} years ({", ".join(V.pc(m, 0) for m in ms)})'
    elif fin(F.get('oi')):
        mbar, mhow = F['oi'] / rev, 'the last four quarters\' EBIT margin (fewer than three years on file)'
    else:
        return None, None
    if mbar <= 0:
        return None, None
    t = F.get('tax_rate', 0.21)
    ebit = mbar * rev
    da, capex = F.get('da') or 0.0, F.get('capex') or 0.0
    g0 = F.get('g0') if fin(F.get('g0')) else 0.0
    gain = max(0.0, rev - rev / (1 + g0)) if g0 > -0.9 else 0.0
    ppe = F.get('ppe')
    if fin(ppe) and ppe > 0:
        growth_capex = min(capex, ppe / rev * gain)
        maint, mtwhy = capex - growth_capex, f'capex {V.money(capex)} − growth capex (PP&E {V.money(ppe)} ÷ revenue × revenue gain {V.money(gain)} = {V.money(growth_capex)})'
    else:
        maint, mtwhy = min(capex, da) if capex > 0 else da, 'D&A (PP&E not on file: upkeep assumed to equal depreciation)'
    ae = ebit * (1 - t) + da - maint
    if ae <= 0:
        return None, None
    nd = _nd(F)
    per = lambda w: (ae / w - nd) / sh
    v, lo, hi = per(wacc), per(wacc + 0.01), per(max(0.03, wacc - 0.01))
    c = V.calc('EPV = adjusted earnings ÷ WACC − net debt;  adjusted earnings = normalized EBIT × (1 − t) + D&A − maintenance capex;  normalized EBIT = average margin × revenue',
               [f'normalized EBIT = {V.pc(mbar)} × {V.money(rev)} = {V.money(ebit)}  ({mhow})',
                f'maintenance capex = {V.money(maint)}  ({mtwhy})',
                f'adjusted earnings = {V.money(ebit)} × (1 − {V.pc(t, 0)}) + {V.money(da)} − {V.money(maint)} = {V.money(ae)}',
                f'EPV = {V.money(ae)} ÷ {V.pc(wacc)} {V.less_nd(nd)} = {V.money(ae / wacc - nd)} → ÷ {V.num(sh)} = {V.ps(v)}; WACC ±1 point: {V.ps(lo)} – {V.ps(hi)}'],
               [['Revenue, four quarters', V.money(rev), V.src_of(F, 'revenue')], ['D&A', V.money(da), V.src_of(F, 'da')], ['Capex', V.money(capex), V.src_of(F, 'capex')],
                ['PP&E, net', V.money(ppe), 'SEC XBRL frames (PropertyPlantAndEquipmentNet)'], ['Net debt', V.money(nd), 'debt − cash + other claims']],
               [['No growth', 'the business as it is, forever', 'Bruce Greenwald, Value Investing (2001)'], ['WACC', V.pc(wacc), 'build-up above']])
    tbv = ((F.get('equity') or 0) - (F.get('goodwill') or 0) - (F.get('intangibles') or 0)) / sh
    price = F.get('price')
    split = {'epv_ps': v, 'price': price, 'tangible_book_ps': tbv, 'margin_used': mbar, 'adjusted_earnings': ae,
             'growth_share': (1 - v / price) if fin(price) and price > 0 else None,
             'franchise': (v > tbv) if fin(tbv) else None,
             'note': 'Price above EPV: the market pays for growth. EPV above tangible book: the business earns more than its assets would cost '
                     'to rebuild — a sign of a moat (Greenwald). EPV below tangible book: the assets earn less than their cost.'}
    item = {'method': 'Earnings power value (EPV)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c, 'lens': True,
            'note': f'normalized margin {V.pc(mbar)}, no growth, ÷ WACC {V.pc(wacc)}' + (f'; the price pays {V.pc(split["growth_share"], 0)} for growth' if fin(split['growth_share']) and split['growth_share'] > 0 else '')}
    return item, split


def fcfe_dcf(V, M, F, W, base):
    sh, ke, ni, rev, eq = F.get('shares'), (W or {}).get('ke'), F.get('ni'), F.get('revenue'), F.get('equity')
    if not (base and fin(sh) and sh > 0 and fin(ke) and fin(ni) and ni > 0 and fin(rev) and rev > 0 and fin(eq) and eq > 0):
        return None
    g = M.TERM_G
    if ke - g < 0.01:
        return None
    d = clamp((F.get('debt') or 0) / max(1.0, (F.get('debt') or 0) + eq), 0.0, 0.8)
    nm, da0 = ni / rev, (F.get('da') or 0) / rev
    capex = base['capex'] if isinstance(base['capex'], list) else [base['capex']] * M.YEARS
    roe = clamp(ni / eq, 0.08, 0.30)

    def val(k):
        r, pv, rows = rev, 0.0, []
        for t, gr in enumerate(base['growth']):
            r1 = r * (1 + gr)
            fcfe = r1 * nm - (1 - d) * ((capex[t] - da0) * r1 + M.WC_SHARE * (r1 - r))
            pv += fcfe / (1 + k) ** (t + 1)
            rows.append(fcfe)
            r = r1
        tv = r * (1 + g) * nm * (1 - g / roe) / (k - g)
        return (pv + tv / (1 + k) ** M.YEARS) / sh, rows, tv
    v, rows, tv = val(ke)
    lo, hi = val(ke + 0.01)[0], val(max(g + 0.01, ke - 0.01))[0]
    c = V.calc('FCFE = net income − (1 − d) × (capex − D&A + ΔWC);  value = Σ FCFE ÷ (1 + kₑ)ᵗ + terminal ÷ (1 + kₑ)⁵;  terminal = net income₆ × (1 − g ÷ ROE) ÷ (kₑ − g)',
               [f'net margin {V.pc(nm)}; d (debt share of capital) = {V.pc(d, 0)}; growth {", ".join(V.pc(x, 0) for x in base["growth"])}',
                'FCFE by year: ' + ', '.join(V.money(x) for x in rows),
                f'terminal = {V.money(tv)} (ROE {V.pc(roe)}, g {V.pc(g)}); ÷ (1 + {V.pc(ke)})^{M.YEARS}; per share {V.ps(v)}; kₑ ±1 point: {V.ps(lo)} – {V.ps(hi)}'],
               [['Net income, four quarters', V.money(ni), V.src_of(F, 'ni')], ['Equity', V.money(eq), V.src_of(F, 'equity')], ['Debt', V.money(F.get('debt')), V.src_of(F, 'debt')]],
               [['Cost of equity', V.pc(ke), 'CAPM build-up above'], ['Borrowing', f'keeps {V.pc(d, 0)} of reinvestment debt-funded', 'Damodaran: a steady debt ratio'],
                ['Growth path, capex, ΔWC', 'the DCF\'s', 'its own growth fading to terminal']])
    return {'method': 'FCFE DCF (cash to shareholders)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c, 'lens': True,
            'note': f'free cash flow to equity at kₑ {V.pc(ke)}; debt funds {V.pc(d, 0)} of reinvestment'}


def h_model(V, M, F, W):
    sh, ke, div = F.get('shares'), (W or {}).get('ke'), F.get('div')
    if not (fin(sh) and sh > 0 and fin(ke) and fin(div) and div > 0):
        return None
    d0 = div / sh
    gl = M.TERM_G
    roe = F['ni'] / F['equity'] if fin(F.get('ni')) and fin(F.get('equity')) and F['equity'] > 0 else None
    payout = clamp(div / F['ni'], 0.0, 1.0) if fin(F.get('ni')) and F['ni'] > 0 else 1.0
    gs = clamp(roe * (1 - payout), 0.0, 0.10) if fin(roe) else gl
    if ke - gl < 0.01:
        return None
    f = lambda k: d0 * ((1 + gl) + H_YEARS * (gs - gl)) / (k - gl)
    v, lo, hi = f(ke), f(ke + 0.01), f(max(gl + 0.01, ke - 0.01))
    c = V.calc('Value = D₀ × [(1 + g_L) + H × (g_S − g_L)] ÷ (kₑ − g_L);  growth falls in a straight line from g_S to g_L over 2H years',
               [f'D₀ = {V.money(div)} ÷ {V.num(sh)} = {V.ps(d0)}; g_S = ROE {V.pc(roe)} × (1 − payout {V.pc(payout, 0)}) → {V.pc(gs)}; g_L = {V.pc(gl)}; H = {H_YEARS}',
                f'= {V.ps(d0)} × [(1 + {V.pc(gl)}) + {H_YEARS} × ({V.pc(gs)} − {V.pc(gl)})] ÷ ({V.pc(ke)} − {V.pc(gl)}) = {V.ps(v)}; kₑ ±1 point: {V.ps(lo)} – {V.ps(hi)}'],
               [['Dividends paid, latest year', V.money(div), 'SEC XBRL frames (PaymentsOfDividends)'], ['Diluted shares', V.num(sh), V.src_of(F, 'shares')]],
               [['Cost of equity', V.pc(ke), 'CAPM build-up above'], ['Fade', f'{2 * H_YEARS} years', 'Fuller and Hsia (1984): the H-model'],
                ['Short-term growth cap', '0–10%', 'an assumption: dividends rarely grow faster for a decade']])
    return {'method': 'H-model dividend discount', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c, 'lens': True,
            'note': f'dividend {V.ps(d0)} growing {V.pc(gs)} fading to {V.pc(gl)} over {2 * H_YEARS} years'}


def real_option(V, M, F, W, base, tm, vol, r5):
    """The option to grow into a mature business: assets in place + a Black-Scholes call."""
    sh, rev, wacc = F.get('shares'), F.get('revenue'), (W or {}).get('wacc')
    if not (base and fin(sh) and sh > 0 and fin(rev) and rev > 0 and fin(wacc) and wacc > M.TERM_G + 0.01 and fin(tm) and tm > 0 and fin(vol) and vol > 0):
        return None
    g = M.TERM_G
    rev5 = rev
    for gr in base['growth']:
        rev5 *= 1 + gr
    t = F.get('tax_rate', 0.21)
    inc = rev5 - rev                                         # the expansion: the revenue it adds by year 5
    if inc <= 0:
        return None
    S = inc * tm * (1 - t) * (1 - g / 0.15) * (1 + g) / (wacc - g) / (1 + wacc) ** OPT_YEARS     # new capital earns 15% after
    ic = (F.get('equity') or 0) + (F.get('debt') or 0) - (F.get('cash') or 0)
    s2c = rev / ic if ic > 0 and 0.2 < rev / ic < 10 else SALES_TO_CAPITAL
    K = inc / s2c
    if not (S > 0 and K > 0):
        return None
    rf = (r5 if fin(r5) else 4.0) / 100
    sig = clamp(vol, 0.25, 1.2)
    nopat = (F.get('oi') or 0) * (1 - t)
    aip = max(0.0, nopat / wacc) if nopat > 0 else 0.0
    nd = _nd(F)
    per = lambda s: (aip + bs_call(S, K, OPT_YEARS, rf, s) - nd) / sh
    v, lo, hi = per(sig), per(clamp(sig - 0.25, 0.1, 2)), per(sig + 0.25)
    call = bs_call(S, K, OPT_YEARS, rf, sig)
    if v <= 0 and lo <= 0:
        return None
    c = V.calc('Value = (assets in place + C − net debt) ÷ shares;  C = S·N(d₁) − K·e^(−rT)·N(d₂), d₁ = [ln(S ÷ K) + (r + σ²/2)T] ÷ σ√T, d₂ = d₁ − σ√T',
               [f'S = the expansion in year {OPT_YEARS}: the revenue it adds {V.money(inc)} (to {V.money(rev5)}) × margin {V.pc(tm)} × (1 − tax), as a growing perpetuity, discounted = {V.money(S)}',
                f'K = capital to build it: {V.money(inc)} ÷ sales-to-capital {s2c:.2f} = {V.money(K)}',
                f'σ = {V.pc(sig, 0)} (its stock, a year of daily closes), T = {OPT_YEARS} years, r = {V.pc(rf, 2)} → C = {V.money(call)}',
                f'assets in place = NOPAT {V.money(nopat)} ÷ WACC = {V.money(aip)}; value = ({V.money(aip)} + {V.money(call)} {V.less_nd(nd)}) ÷ {V.num(sh)} = {V.ps(v)}',
                f'σ ±25 points: {V.ps(lo)} – {V.ps(hi)}'],
               [['Revenue, four quarters', V.money(rev), V.src_of(F, 'revenue')], ['Operating income', V.money(F.get('oi')), V.src_of(F, 'oi')],
                ['Stock volatility', V.pc(vol, 0), 'daily closes, last year (annualized)']],
               [['Mature margin', V.pc(tm), 'peer median operating margin'], ['Growth path', ', '.join(V.pc(x, 0) for x in base['growth']), 'the DCF\'s'],
                ['Volatility of the project', 'the stock\'s', 'an assumption: the business is riskier than the market sees only through its price'],
                ['Return on new capital in perpetuity', '15%', 'an assumption'], ['Method', 'Black-Scholes (1973); real options: Myers (1977), Damodaran', '']])
    return {'method': 'Real option to expand', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c, 'lens': True,
            'note': f'option worth {V.money(call)}: underlying {V.money(S)}, cost {V.money(K)}, σ {V.pc(sig, 0)}'}


# ---------------------------------------------------------------- the multi-factor fit (every covered non-financial company)
def _feat(r):
    """[growth, ln(operating margin, floored at 0.5%), loss flag, ln(revenue in $B)]: EV/Sales = EV/EBIT × margin, so the margin
    enters in logs; a loss-maker's margin carries no such meaning, the flag takes its place."""
    rev, oi, g = r.get('revenue'), r.get('oi'), r.get('g0')
    if not (fin(rev) and rev >= 5e7 and fin(oi) and fin(g)):
        return None
    m = oi / rev
    return [clamp(g, -0.5, 1.0), math.log(clamp(m, 0.005, 0.6)), 1.0 if m <= 0 else 0.0, math.log(rev / 1e9)]


def multifactor_fit(rows, ridge=None):
    """Ridge regression of ln(EV/Sales) on growth, operating margin, ln(revenue) and sector effects."""
    pts = []
    for r in rows:
        if r.get('kind') != 'industrial' or not fin(r.get('ev_sales')) or not (0.05 < r['ev_sales'] <= 50):
            continue
        x = _feat(r)
        if x:
            pts.append((x, r.get('sector') or 'other', math.log(r['ev_sales'])))
    if len(pts) < FIT_MIN:
        return None
    secs = sorted({s for _, s, _ in pts if sum(1 for _, t, _ in pts if t == s) >= 15})
    X = [x + [1.0 if s == k else 0.0 for k in secs] for x, s, _ in pts]
    y = [v for _, _, v in pts]
    n, p = len(X), len(X[0])
    mx = [sum(row[j] for row in X) / n for j in range(p)]
    my = sum(y) / n
    Xc = [[row[j] - mx[j] for j in range(p)] for row in X]
    yc = [v - my for v in y]
    lam = RIDGE if ridge is None else ridge
    A = [[sum(Xc[i][a] * Xc[i][b] for i in range(n)) + (lam if a == b else 0.0) for b in range(p)] for a in range(p)]
    bvec = [sum(Xc[i][a] * yc[i] for i in range(n)) for a in range(p)]
    beta = _solve(A, bvec)
    if beta is None:
        return None
    a0 = my - sum(beta[j] * mx[j] for j in range(p))
    res = [y[i] - a0 - sum(beta[j] * X[i][j] for j in range(p)) for i in range(n)]
    se = math.sqrt(sum(e * e for e in res) / max(1, n - p - 1))
    ss = sum(v * v for v in yc)
    return {'a': a0, 'b': beta[:4], 'sectors': {k: beta[4 + i] for i, k in enumerate(secs)}, 'se': se, 'n': n,
            'r2': 1 - sum(e * e for e in res) / ss if ss > 0 else None}


def _solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def multifactor_item(V, F, fit):
    sh, rev = F.get('shares'), F.get('revenue')
    x = _feat(F)
    if not (fit and x and fin(sh) and sh > 0 and F.get('kind') == 'industrial'):
        return None
    sec = fit['sectors'].get(F.get('sector') or 'other', 0.0)
    mid = fit['a'] + sum(b * v for b, v in zip(fit['b'], x)) + sec
    nd = _nd(F)
    per = lambda lm: (math.exp(lm) * rev - nd) / sh
    v, lo, hi = per(mid), per(mid - fit['se']), per(mid + fit['se'])
    c = V.calc('ln(EV/Sales) = a + b₁ × growth + b₂ × ln(operating margin, at least 0.5%) + b₃ × loss flag + b₄ × ln(revenue, $B) + sector effect;  '
               'value = (fitted EV/Sales × revenue − net debt) ÷ shares',
               [f'= {fit["a"]:.3f} + {fit["b"][0]:.3f} × {x[0]:.3f} + {fit["b"][1]:.3f} × {x[1]:.3f} + {fit["b"][2]:.3f} × {x[2]:.0f} + {fit["b"][3]:.3f} × {x[3]:.3f} + {sec:.3f} ({F.get("sector") or "other"}) = {mid:.3f}',
                f'→ EV/Sales {V.xm(math.exp(mid))}; = ({V.xm(math.exp(mid))} × {V.money(rev)} {V.less_nd(nd)}) ÷ {V.num(sh)} = {V.ps(v)}',
                f'±1 residual standard error ({fit["se"]:.2f} in logs): {V.ps(lo)} – {V.ps(hi)}'],
               [['Revenue, four quarters', V.money(rev), V.src_of(F, 'revenue')], ['Revenue growth', V.pc(F.get('g0')), 'last four quarters vs the four before'],
                ['Operating margin', V.pc(F['oi'] / rev), 'operating income ÷ revenue'], ['Net debt', V.money(nd), 'debt − cash + other claims']],
               [['Fit', f'{fit["n"]} companies, R² {fit["r2"]:.2f}' if fin(fit.get('r2')) else f'{fit["n"]} companies',
                 'every covered non-financial company with revenue ≥ $50M, today; ridge λ = 1']])
    return {'method': 'EV/Sales fair multiple (multi-factor fit)', 'low': min(lo, hi), 'high': max(lo, hi), 'point': v, 'calc': c, 'lens': True,
            'note': f'what the market pays for {V.pc(x[0], 0)} growth and a {V.pc(F["oi"] / rev, 0)} margin at its size and sector: {V.xm(math.exp(mid))} sales'}


# ---------------------------------------------------------------- the return today's price implies
def implied_return(V, M, F, W, base, cons_c):
    price, sh = F.get('price'), F.get('shares')
    if not (fin(price) and price > 0 and fin(sh) and sh > 0):
        return None
    rows = []
    if base:
        s = M.solve(base, 'wacc', price, 0.03, 0.40)
        if s.get('status') == 'ok' and fin(s.get('value')):
            rows.append({'method': 'DCF at the price', 'r': s['value'], 'how': 'the discount rate at which the base-case DCF equals the price', 'vs': 'WACC'})
    oe = (F.get('ni') or 0) + (F.get('da') or 0) - (F.get('capex') or 0) if fin(F.get('ni')) else None
    if fin(oe) and oe > 0 and F.get('kind') == 'industrial':
        g = M.TERM_G
        rows.append({'method': 'Owner-earnings yield + growth', 'r': oe / sh / price * (1 + g) + g,
                     'how': f'owner earnings {V.ps(oe / sh)}/share ÷ price × (1 + {V.pc(g)}) + {V.pc(g)} (Gordon)', 'vs': 'cost of equity'})
    e1, e2 = forward_eps(cons_c)
    if fin(e1) and fin(e2) and e2 > e1 > 0:
        dps = (F.get('div') or 0) / sh if fin(F.get('div')) else 0.0
        a = dps / (2 * price)
        r = a + math.sqrt(a * a + (e2 - e1) / price)
        rows.append({'method': 'Easton MPEG (analysts\' EPS)', 'r': r,
                     'how': f'r = D/2P + √((D/2P)² + (EPS₂ − EPS₁)/P): EPS {V.ps(e1)} → {V.ps(e2)}, dividend {V.ps(dps)}', 'vs': 'cost of equity'})
    eq, ni = F.get('equity'), F.get('ni')
    if fin(eq) and eq > 0 and fin(ni) and fin(M.residual_income(eq, ni / eq, 0.08)):
        lo, hi, roe = 0.02, 0.40, ni / eq
        f = lambda k: M.residual_income(eq, roe, k) / sh - price
        if fin(f(lo)) and fin(f(hi)) and f(lo) * f(hi) < 0:
            for _ in range(80):
                mid = (lo + hi) / 2
                if f(lo) * f(mid) <= 0:
                    hi = mid
                else:
                    lo = mid
            rows.append({'method': 'Residual income at the price', 'r': (lo + hi) / 2, 'how': f'the cost of equity at which book + residual income (ROE {V.pc(roe)} fading) equals the price', 'vs': 'cost of equity'})
    rows = [r for r in rows if fin(r['r']) and -0.2 < r['r'] < 0.6]
    if not rows:
        return None
    rs = sorted(r['r'] for r in rows)
    med = rs[len(rs) // 2] if len(rs) % 2 else (rs[len(rs) // 2 - 1] + rs[len(rs) // 2]) / 2
    ke, wacc = (W or {}).get('ke'), (W or {}).get('wacc')
    return {'rows': rows, 'median': med, 'ke': ke, 'wacc': wacc, 'spread': med - ke if fin(ke) else None,
            'note': 'The yearly return a buyer at today\'s price earns if each model\'s assumptions hold (an implied cost of capital). Above the cost of '
                    'equity: the price leaves room; below: the price already asks for more than the models deliver.'}


# ---------------------------------------------------------------- everything, for one company
def extra(V, M, F, W, out, ctx, base):
    """Append the lenses to out['football'] and set out['implied_return'] and out['epv']."""
    cons_c = ctx.get('cons')
    fin_kind = F.get('kind') in ('bank', 'insurer')
    rates = ctx.get('rates') or {}
    items = [graham_number(V, F), graham_formula(V, F, cons_c, rates.get('aaa')), lynch_pegy(V, F, cons_c)]
    if not fin_kind:
        items.append(ncav(V, F))
        it, split = epv(V, F, W, F.get('years'))
        items.append(it)
        if split:
            out['epv'] = split
        items.append(fcfe_dcf(V, M, F, W, base) if F.get('kind') == 'industrial' else None)
        items.append(multifactor_item(V, F, (ctx.get('regressions') or {}).get('multifactor')))
        st = out.get('stage') or {}
        oi, g0, rev = F.get('oi'), F.get('g0'), F.get('revenue')
        tm = (st.get('metrics') or {}).get('target_margin')
        if not fin(tm) and fin(oi) and fin(rev) and rev > 0 and oi > 0:
            tm = oi / rev                                   # a fast grower already profitable: today's margin, scaled up
        if (not fin(oi) or oi <= 0 or fin(g0) and g0 >= 0.15) and fin(tm) and fin(g0) and fin(rev) and rev > 0:
            path = base or {'growth': M.fade(clamp(g0, -0.2, 0.6), M.TERM_G)}
            items.append(real_option(V, M, F, W, path, tm, ctx.get('vol'), rates.get('treasury_5y')))
    items.append(h_model(V, M, F, W))
    for it in items:
        if not it or not it.get('method'):
            continue
        if fin(it.get('point')):
            out['football'].append(it)
        elif fin(it.get('negative')):
            out.setdefault('lens_why', {})[it['method']] = (f'current assets less all liabilities is negative ({V.ps(it["negative"])} a share): '
                                                             'no net-net value — normal for a company funded by long-term debt')
    ir = implied_return(V, M, F, W, base, cons_c)
    if ir:
        out['implied_return'] = ir
    return out


CANDIDATES = ['Graham number', 'Graham formula (revised)', 'Net current asset value (net-net)', 'Lynch fair P/E (PEGY)', 'Earnings power value (EPV)',
              'FCFE DCF (cash to shareholders)', 'H-model dividend discount', 'Real option to expand', 'EV/Sales fair multiple (multi-factor fit)']
WHY_NOT = {
    'Graham number': 'needs positive EPS and positive book value',
    'Graham formula (revised)': 'needs positive EPS, a growth estimate and the AAA yield',
    'Net current asset value (net-net)': 'needs current assets and total liabilities on file (not for banks or insurers)',
    'Lynch fair P/E (PEGY)': 'needs positive EPS and a growth estimate',
    'Earnings power value (EPV)': 'needs a positive normalized operating margin and the WACC (not for banks or insurers)',
    'FCFE DCF (cash to shareholders)': 'needs the DCF, positive net income and positive equity',
    'H-model dividend discount': 'pays no dividend (or its cost of equity is within a point of the terminal growth)',
    'Real option to expand': 'only for loss-making or fast-growing (15%+) companies with a peer margin and a price history',
    'EV/Sales fair multiple (multi-factor fit)': 'only for non-financial companies with revenue ≥ $50M and the cross-company fit',
}


def fit_reason(name, F, out):
    """Why the lens applies to this company (the appendix's "Why it applies here"), or None for other methods."""
    if name == 'Graham number':
        return 'It has positive earnings and book value, the two things Graham asked a defensive investor to pay for — and to pay little for.'
    if name.startswith('Graham formula'):
        return 'It has positive earnings and a growth estimate; the formula prices that growth against today\'s AAA bond yield.'
    if name.startswith('Net current asset'):
        return ('Its current assets and liabilities are on file. Net-nets are rare among large companies; a positive figure is a floor '
                'that ignores everything the business owns beyond working capital.')
    if name.startswith('Lynch'):
        return 'It has positive earnings and a growth rate, so its P/E can be set against the growth and yield it delivers.'
    if name.startswith('Earnings power'):
        return 'It earns an operating profit over the cycle; EPV values that profit as if it never grew, which shows how much of the price is a bet on growth.'
    if name.startswith('FCFE'):
        return 'It is profitable with positive equity, so the cash left for shareholders after reinvestment and borrowing can be projected.'
    if name.startswith('H-model'):
        return 'It pays a dividend whose growth is likely to slow from today\'s pace to the economy\'s, which the H-model spreads over ten years.'
    if name.startswith('Real option'):
        return ('It is loss-making or growing fast: much of its value is the chance to become a larger, profitable business, which behaves like '
                'an option — worth more the more uncertain it is.')
    if name.startswith('EV/Sales fair multiple'):
        return 'It is a non-financial company with revenue on file, so the multiple the market pays companies with its growth, margin, size and sector applies.'
    return None



# ---------------------------------------------------------------- the market as a whole (pub/market.json)
FRED_CSV = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}'
MARKET_SERIES = {'NCBEILQ027S': 'Nonfinancial corporate equities, market value ($M, Fed Z.1)', 'GDP': 'Gross domestic product ($B, annual rate)',
                 'DFII10': '10-year TIPS real yield (%)', 'DGS10': '10-year Treasury yield (%)'}


def fetch_fred(root, http_get, ids=tuple(MARKET_SERIES)):
    """FRED's CSVs into cache/fred/<ID>.csv (whole history; small files). http_get(url) → text."""
    from pathlib import Path
    out = {}
    d = Path(root) / 'cache' / 'fred'
    d.mkdir(parents=True, exist_ok=True)
    for sid in ids:
        try:
            txt = http_get(FRED_CSV.format(id=sid))
            if txt and txt.count('\n') > 5:
                (d / f'{sid}.csv').write_text(txt, encoding='utf-8')
                out[sid] = txt.count('\n')
        except Exception as e:                              # noqa: BLE001 — the last file on hand stays
            out[sid] = 'error: ' + str(e)[:80]
    return out


def read_fred(root, sid):
    from pathlib import Path
    p = Path(root) / 'cache' / 'fred' / f'{sid}.csv'
    rows = []
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines()[1:]:
            a = line.split(',')
            try:
                rows.append((a[0], float(a[1])))
            except (ValueError, IndexError):
                pass
    return rows


def _pct_rank(xs, v):
    xs = [x for x in xs if fin(x)]
    return sum(1 for x in xs if x <= v) / len(xs) if xs and fin(v) else None


def market_view(root, rows, rates, today):
    """The market's valuation: the Buffett indicator (corporate equities ÷ GDP, Fed Z.1 since 1951), the covered companies'
    earnings yield against the 10-year nominal and real yields (the Fed model), and their market-value-weighted implied
    return less the 10-year yield — an implied equity risk premium."""
    out = {'generated_at': today}
    eq, gdp = read_fred(root, 'NCBEILQ027S'), dict(read_fred(root, 'GDP'))
    hist = [(d, v / 1e3 / gdp[d]) for d, v in eq if d in gdp and gdp[d] > 0]
    if hist:
        cur = hist[-1]
        vals = [v for _, v in hist]
        out['buffett'] = {'date': cur[0], 'ratio': cur[1], 'pct_rank': _pct_rank(vals, cur[1]), 'mean': sum(vals) / len(vals),
                          'median': sorted(vals)[len(vals) // 2], 'since': hist[0][0], 'series': [[d, round(v, 4)] for d, v in hist],
                          'how': 'market value of US nonfinancial corporate equities (Fed Z.1, FRED NCBEILQ027S) ÷ GDP (FRED GDP), quarterly; published about '
                                 'ten weeks after each quarter ends'}
    big = [r for r in rows if fin(r.get('mcap')) and r['mcap'] > 0]
    big.sort(key=lambda r: -r['mcap'])
    top = big[:500]
    ni = sum(r['ni'] for r in top if fin(r.get('ni')))
    cap = sum(r['mcap'] for r in top if fin(r.get('ni')))
    y10 = rates.get('treasury_10y')
    real = read_fred(root, 'DFII10')
    r10 = real[-1][1] if real else None
    if cap > 0:
        ey = ni / cap
        out['earnings_yield'] = {'companies': len([r for r in top if fin(r.get('ni'))]), 'ey': ey, 'pe': 1 / ey if ey > 0 else None,
                                 'y10': y10 / 100 if fin(y10) else None, 'real10': r10 / 100 if fin(r10) else None,
                                 'gap_nominal': ey - y10 / 100 if fin(y10) else None, 'gap_real': ey - r10 / 100 if fin(r10) else None,
                                 'how': 'trailing net income ÷ market value of the 500 largest covered companies (the Fed model compares it with the 10-year '
                                        'Treasury; against the real TIPS yield it is the cleaner comparison, since earnings grow with inflation)'}
    w = [(r['mcap'], r['icc']) for r in top if fin(r.get('icc'))]
    if w and fin(y10):
        icc = sum(a * b for a, b in w) / sum(a for a, _ in w)
        out['implied_erp'] = {'companies': len(w), 'implied_return': icc, 'y10': y10 / 100, 'erp': icc - y10 / 100,
                              'how': 'the market-value-weighted median implied return of the 500 largest covered companies (each the median of its DCF, '
                                     'owner-earnings, Easton and residual-income implied costs of capital) less the 10-year Treasury'}
    return out
