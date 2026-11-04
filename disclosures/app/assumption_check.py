"""Fixed numbers vs the market today, for the Fair value page (app/valuation.py): every number the valuation code fixes in
advance, beside what market prices or the covered companies' own figures say it is today, and what swapping the market's
numbers into a company's DCF would do to its value.

  market      read from prices: the implied equity risk premium (the market-value-weighted implied return of the 500
              largest covered companies less the 10-year Treasury), the 10-year nominal yield as the market's long-run
              nominal growth (expected inflation, the breakeven, plus the real TIPS yield), the premium the market asks of
              high-growth over mature companies (their median implied returns), what it pays for the assets of companies
              likely to fail (price ÷ tangible book where the one-year distress probability is 10% or more), the no-growth
              P/E (profitable companies growing within ±2%).
  data        read from the covered companies' filings: working capital per dollar of revenue, the effective tax rate,
              ROIC and revenue ÷ invested capital, how betas drift toward 1 (the slope of each company's last two years'
              beta on the two years before), how fast peer multiples revert (the quarterly persistence of log EV/Sales),
              the days from a quarter's end to its filing, the spread of raw WACCs.
  convention  a market convention the number follows (CDS recovery 40%: loss given default 60%).
  choice      a method choice with no market counterpart (forecast years, Monte Carlo draws, peer windows …), listed
              with why it is fixed.
Each company with a DCF gets its value with each market number swapped in alone, and with all of them together.
"""
from __future__ import annotations

import datetime as dt
import math


def fin(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def _q(xs, p):
    xs = sorted(x for x in xs if fin(x))
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _med(xs):
    return _q(xs, 0.5)


def _entry(key, label, fixed, market, kind, how, feeds, n=None, low=None, high=None, fixed_text=None, market_text=None, note=None, src=None):
    e = {'key': key, 'label': label, 'fixed': fixed, 'market': market, 'kind': kind, 'how': how, 'feeds': feeds}
    for k, v in (('n', n), ('low', low), ('high', high), ('fixed_text', fixed_text), ('market_text', market_text), ('note', note), ('src', src)):
        if v is not None:
            e[k] = v
    if fin(fixed) and fin(market):
        e['gap'] = market - fixed
    return e


def persistence(hist):
    """Pooled AR(1) coefficient of each company's quarterly log multiple around its own mean (consecutive quarters only),
    with Kendall's correction for the downward bias of a short demeaned series: ρ + (1 + 3ρ) ÷ T."""
    num = den = 0.0
    n = series = 0
    for xs in (hist or {}).values():
        s = sorted(((a, math.log(v)) for v, a in xs if fin(v) and v > 0 and fin(a)), key=lambda t: -t[0])   # oldest first
        if len(s) < 6:
            continue
        m = sum(v for _, v in s) / len(s)
        series += 1
        for (a0, x0), (a1, x1) in zip(s, s[1:]):
            if 0.15 <= a0 - a1 <= 0.35:
                num += (x0 - m) * (x1 - m)
                den += (x0 - m) ** 2
                n += 1
    if den <= 0 or not series:
        return None, n
    rho, T = num / den, n / series + 1
    return min(0.999, rho + (1 + 3 * rho) / T), n


def market_estimates(M, Fs, R, rows, market, rates, bases, filings, hist, today, betas=None, raw_wacc=None):
    """The table: one entry per fixed number (see the module's docstring). M: the valuation module (its constants)."""
    import valuation_extra as VX
    import valuation_methods as VMx
    import peer_weights as PW
    import peer_tiers as PT
    out = []
    y10 = rates.get('treasury_10y') / 100 if fin(rates.get('treasury_10y')) else None
    real = (market or {}).get('earnings_yield', {}).get('real10')
    ie = (market or {}).get('implied_erp') or {}
    ey = ((market or {}).get('earnings_yield') or {}).get('gap_real')        # earnings yield less the real 10-year yield
    nonfin = [F for F in Fs.values() if F.get('kind') not in ('bank', 'insurer', 'reit')]
    # ---- market
    out.append(_entry('erp', 'Equity risk premium', M.ERP, ie.get('erp'), 'market',
                      'the market-value-weighted implied return of the 500 largest covered companies (each the median of its DCF, owner-earnings, '
                      'Easton and residual-income implied costs of capital) less the 10-year Treasury' + (f" ({ie.get('implied_return', 0) * 100:.2f}% − "
                                                                                                         f"{(ie.get('y10') or 0) * 100:.2f}%)" if ie else '')
                      + (f'; the earnings yield of the 500 largest less the real 10-year yield gives {ey * 100:.2f}% (the range)' if fin(ey) else ''),
                      'every cost of equity and WACC: the DCFs, residual income, the dividend models', n=ie.get('companies'),
                      low=min(x for x in (ie.get('erp'), ey) if fin(x)) if fin(ie.get('erp')) or fin(ey) else None,
                      high=max(x for x in (ie.get('erp'), ey) if fin(x)) if fin(ie.get('erp')) or fin(ey) else None))
    be = y10 - real if fin(y10) and fin(real) else None
    tg_how = ('the 10-year Treasury yield, the market\'s long-run nominal rate: expected inflation (the breakeven, '
              + (f'{be * 100:.2f}%' if fin(be) else 'nominal less real yield') + ') plus the real TIPS yield (' + (f'{real * 100:.2f}%' if fin(real) else '—')
              + '); the usual ceiling for growth forever, since no company outgrows the economy for ever. The breakeven alone is the floor: inflation, no real growth')
    out.append(_entry('terminal_g', 'Terminal growth (base DCF, regime Monte Carlo)', M.TERM_G, y10, 'market', tg_how, 'the terminal value of the DCFs',
                      low=be, high=y10))
    out.append(_entry('g_cap', 'Growth cap of the Gordon models', VMx.G_CAP, y10, 'market', 'the same long-run nominal rate as above',
                      'justified P/B and P/TBV, the dividend discount model', low=be, high=y10))
    hg = [r.get('icc') for r in rows if fin(r.get('icc')) and (R.get(str(r['cik'])) or {}).get('stage') == 'high_growth']
    mt = [r.get('icc') for r in rows if fin(r.get('icc')) and (R.get(str(r['cik'])) or {}).get('stage') == 'mature']
    sp = _med(hg) - _med(mt) if len(hg) >= 10 and len(mt) >= 10 else None
    out.append(_entry('stage_premium', 'Stage premium of the exit-multiple method', VMx.STAGE_PREMIUM, sp, 'market',
                      f'the median implied return of high-growth companies less that of mature ones ({len(hg)} and {len(mt)} companies): the extra return the '
                      'market asks of growth today; pre-profit companies have no implied return, so this is a lower bound for them',
                      'the exit-multiple (venture) method'))
    ptbv = []
    for r in rows:
        F = Fs.get(str(r['cik'])) or {}
        tbv = (F.get('equity') or 0) - (F.get('goodwill') or 0) - (F.get('intangibles') or 0)
        if fin(r.get('distress_pd')) and r['distress_pd'] >= 0.10 and tbv > 0 and fin(F.get('mcap')) and F.get('kind') not in ('bank', 'insurer'):
            ptbv.append(F['mcap'] / tbv)
    out.append(_entry('liq_haircut', 'Liquidation value: share of tangible book recovered', VMx.LIQ_HAIRCUT, _med(ptbv) if len(ptbv) >= 10 else None, 'market',
                      f'the median price ÷ tangible book of the {len(ptbv)} covered companies with a one-year distress probability of 10% or more: what the market '
                      'pays for the assets of companies that may fail (a going-concern price, so an upper bound for a forced sale)',
                      'the survival-weighted value, tangible book', n=len(ptbv), low=_q(ptbv, 0.25), high=_q(ptbv, 0.75)))
    pes = [F['pe'] for F in Fs.values() if fin(F.get('pe')) and fin(F.get('g0')) and abs(F['g0']) <= 0.02]
    out.append(_entry('graham_pe', 'No-growth P/E (Graham formula)', VX.GRAHAM_NO_GROWTH, _med(pes) if len(pes) >= 10 else None, 'market',
                      f'the median P/E of the {len(pes)} profitable covered companies whose revenue grew within ±2% over the last four quarters', 'the Graham formula',
                      n=len(pes), low=_q(pes, 0.25), high=_q(pes, 0.75)))
    out.append(_entry('rf_fallback', '10-year Treasury when none is on file', 0.043, y10, 'market', 'the 10-year Treasury yield today (used only when the rates feed is missing)',
                      'the cost of equity, the cost of debt fallback'))
    # ---- data
    wc = [((F.get('ca') or 0) - (F.get('cash') or 0) - F['cl']) / F['revenue'] for F in nonfin
          if fin(F.get('ca')) and fin(F.get('cl')) and fin(F.get('revenue')) and F['revenue'] > 0]
    wc = [x for x in wc if -1 < x < 2]
    out.append(_entry('wc_share', 'Working capital per dollar of new revenue', M.WC_SHARE, _med(wc) if len(wc) >= 30 else None, 'data',
                      f'the median non-cash working capital (current assets − cash − current liabilities) ÷ revenue of {len(wc)} non-financial companies: in a '
                      'steady state each new dollar of revenue ties up the same share', 'the DCFs', n=len(wc), low=_q(wc, 0.25), high=_q(wc, 0.75)))
    tx = [F['tax_rate'] for F in Fs.values() if fin(F.get('tax_rate')) and not F.get('_tax_default')]
    out.append(_entry('tax_default', 'Tax rate when the company\'s own is not usable', 0.21, _med(tx) if len(tx) >= 30 else None, 'data',
                      f'the median effective tax rate (tax ÷ pretax income, 0–35%) of the {len(tx)} companies whose own rate is usable',
                      'every after-tax figure of the companies without a usable rate', n=len(tx), low=_q(tx, 0.25), high=_q(tx, 0.75)))
    roic, s2c = [], []
    for F in nonfin:
        ic = (F.get('equity') or 0) + (F.get('debt') or 0) - (F.get('cash') or 0)
        if ic > 0 and fin(F.get('oi')) and fin(F.get('revenue')) and F['revenue'] > 0:
            roic.append(F['oi'] * (1 - (F.get('tax_rate') or 0.21)) / ic)
            s2c.append(F['revenue'] / ic)
    roic = [x for x in roic if -1 < x < 2]
    out.append(_entry('roic_clamp', 'Terminal ROIC: the band its own ROIC is held in', None, _med(roic) if len(roic) >= 30 else None, 'data',
                      f'the 10th–90th percentile of today\'s return on invested capital (NOPAT ÷ equity + debt − cash) across {len(roic)} non-financial companies '
                      '(the median beside it)', 'the terminal value of the DCFs', n=len(roic), low=_q(roic, 0.10), high=_q(roic, 0.90),
                      fixed_text='10–30%'))
    s2c = [x for x in s2c if 0.05 < x < 20]
    out.append(_entry('sales_to_capital', 'Revenue per dollar of invested capital (when its own is missing)', VX.SALES_TO_CAPITAL, _med(s2c) if len(s2c) >= 30 else None,
                      'data', f'the median revenue ÷ invested capital of {len(s2c)} non-financial companies', 'the reinvestment of the real-option and FCFE lenses',
                      n=len(s2c), low=_q(s2c, 0.25), high=_q(s2c, 0.75)))
    if betas:
        xs = [(a, b) for a, b in betas if fin(a) and fin(b) and -1 < a < 4 and -1 < b < 4]
        if len(xs) >= 30:
            mx, my = sum(a for a, _ in xs) / len(xs), sum(b for _, b in xs) / len(xs)
            sl = sum((a - mx) * (b - my) for a, b in xs) / sum((a - mx) ** 2 for a, _ in xs)
            out.append(_entry('blume', 'Weight on a company\'s own beta (Blume adjustment)', 0.67, sl, 'data',
                              f'the slope of each company\'s beta over the last two years on its beta over the two years before, across {len(xs)} companies '
                              f'(intercept {my - sl * mx:.2f}): how much of a measured beta survives into the next period', 'every cost of equity', n=len(xs),
                              src='daily prices'))
    if raw_wacc:
        rw = [w for w in raw_wacc if fin(w)]
        out.append(_entry('wacc_clamp', 'The band the WACC is held in', None, _med(rw), 'data',
                          f'the 5th–95th percentile of the unclamped WACC across {len(rw)} companies (the median beside it)', 'the DCFs', n=len(rw),
                          low=_q(rw, 0.05), high=_q(rw, 0.95), fixed_text='5–16%', src='prices, rates and filings'))
    rho, nr = persistence((hist or {}).get('ev_sales'))
    hl = math.log(0.5) / math.log(rho) * 0.25 if fin(rho) and 0 < rho < 1 else None
    out.append(_entry('half_life', 'Half-life of a peer\'s past multiples (weighted peers)', PW.HALF_LIFE, hl, 'data',
                      f'how fast a company\'s EV/Sales returns toward its own mean: quarterly persistence {rho:.2f} over {nr} quarter pairs, a half-life of '
                      f'{hl:.1f} years (corrected for the downward bias of short series)' if fin(hl) else 'not enough quarterly history', 'the weighted peer multiples',
                      n=nr, src='prices and filings'))
    lags = []
    for c in filings or []:
        try:
            lags.append((dt.date.fromisoformat(str(c['filed'])[:10]) - dt.date.fromisoformat(str(c['end'])[:10])).days)
        except (KeyError, ValueError, TypeError):
            continue
    lags = [x for x in lags if 0 < x < 200]
    out.append(_entry('lag_days', 'Days after a quarter ends before its figures count as known', M.LAG_DAYS, _q(lags, 0.9) if len(lags) >= 30 else None, 'data',
                      f'the 90th percentile of the days from the period\'s end to the filing of the latest 10-Q / 10-K of {len(lags)} companies (median '
                      f'{_med(lags):.0f} days): by then nine in ten have filed' if lags else 'no filing dates', 'the base rates, the valuation bands, the backtests',
                      n=len(lags), src='filing dates (SEC)'))
    # ---- convention and definition
    out.append(_entry('lgd', 'Loss given default (credit spreads)', M.LGD, 0.60, 'convention',
                      'the ISDA standard CDS contract assumes a 40% recovery for senior unsecured debt, a 60% loss', 'the distress probability from bond spreads'))
    out.append(_entry('graham_y0', 'Graham\'s base Aaa yield', VX.GRAHAM_Y0, None, 'definition',
                      'Graham\'s formula divides by today\'s Aaa yield and multiplies by his 1962 yield of 4.4%: the 4.4% is part of the formula, today\'s yield '
                      'is already the market\'s', 'the Graham formula', fixed_text='4.4%', market_text=(f"{rates['aaa']:.2f}% today" if fin(rates.get('aaa')) else None)))
    # ---- choices
    for key, label, val, why in (
            ('years', 'Forecast years of the DCF', f'{M.YEARS}', 'long enough for growth to fade toward the terminal rate, short enough to forecast; the terminal value carries the rest'),
            ('mc_n', 'Monte Carlo scenarios', f'{M.MC_N:,}', 'enough draws for stable percentiles; seeded by ticker so a page does not change between builds'),
            ('peer_min', 'Peers a group needs', f'{PT.MIN_PEERS}', 'fewer make the median one company\'s multiple'),
            ('peer_cap', 'Largest weight of one peer', f'{PW.CAP:.0%}', 'a giant weighs most but is never the whole answer'),
            ('windows', 'Matched-peer windows', 'tight / medium / wide', 'fixed before any result was seen; scored in the ledger'),
            ('multiple_caps', 'Multiples kept', 'P/E 0–200×, EV/EBITDA 0–100×, EV/Sales 0–50×', 'beyond them the figure is a near-zero denominator, not a price'),
            ('markov', 'Regime thresholds', 'high growth ≥ 10%, decline < 0%', 'the Markov model\'s states; its transitions are estimated, the cut-offs are not')):
        out.append({'key': key, 'label': label, 'fixed_text': val, 'kind': 'choice', 'how': why, 'feeds': ''})
    return {'generated_at': today, 'entries': out,
            'note': 'Fixed numbers are set in the code before any result is seen, so that a page cannot be tuned to a wanted answer. The market and data '
                    'estimates beside them change with every build; a gap is a reason to look, not an automatic switch. Each company\'s DCF is shown with the '
                    'market numbers swapped in below.'}


def dcf_swaps(M, sw, est):
    """The company's base DCF with each market number swapped in (erp, terminal growth, working capital, the ROIC band, the tax
    rate when its own was not usable) and all together. sw: {'base', 'W', 'roic_now', 'tax_default'} from valuation.analyse."""
    if not sw or not sw.get('base'):
        return None
    E = {e['key']: e for e in est.get('entries') or []}
    base, W = dict(sw['base']), sw['W']
    v0 = M.value(base)
    if not fin(v0):
        return None
    changes = {}
    erp = (E.get('erp') or {}).get('market')
    if fin(erp) and fin(W.get('beta')) and fin(W.get('rf')):
        ke = W['rf'] + W['beta'] * erp
        changes['erp'] = ('wacc', M.clamp(W['w_equity'] * ke + W['w_debt'] * W['kd_after_tax'], 0.05, 0.16), erp, W.get('erp'))
    g = (E.get('terminal_g') or {}).get('market')
    if fin(g):
        changes['terminal_g'] = ('g', g, g, base['g'])
    gl = (E.get('terminal_g') or {}).get('low')
    if fin(gl):
        changes['terminal_g_floor'] = ('g', gl, gl, base['g'])
    wc = (E.get('wc_share') or {}).get('market')
    if fin(wc):
        changes['wc_share'] = ('wc', wc, wc, base['wc'])
    rc = E.get('roic_clamp') or {}
    if fin(rc.get('low')) and fin(rc.get('high')) and fin(sw.get('roic_now')):
        changes['roic_clamp'] = ('roic', M.clamp(sw['roic_now'], max(0.02, rc['low']), rc['high']), M.clamp(sw['roic_now'], max(0.02, rc['low']), rc['high']), base['roic'])
    tx = (E.get('tax_default') or {}).get('market')
    if sw.get('tax_default') and fin(tx):
        changes['tax_default'] = ('tax', tx, tx, base['tax'])

    def safe(x):                                            # growth stays under the WACC and the ROIC, as the DCF requires
        x['g'] = min(x['g'], x['wacc'] - 0.01, (x.get('roic') or 1) - 0.005)
        return M.value(x)
    rows, allx = [], dict(base)
    for k, (param, val, shown, fixed) in changes.items():
        v = safe({**base, param: val})
        if k != 'terminal_g_floor':                         # all together: the central estimates (the floor is shown on its own)
            allx[param] = val
        rows.append({'key': k, 'param': param, 'fixed': fixed, 'market': shown, 'used': val, 'value': v if fin(v) else None,
                     'change': v / v0 - 1 if fin(v) and v0 else None})
    va = safe(allx) if rows else None
    return {'value': v0, 'rows': rows, 'all': va if fin(va) else None, 'all_change': va / v0 - 1 if fin(va) and v0 else None,
            'wacc': base['wacc'], 'wacc_market': (changes.get('erp') or (None, None))[1]}


APPENDIX_KEYS = {'Equity risk premium': 'erp', 'Terminal growth': 'terminal_g', 'Working capital': 'wc_share',
                 'Stage premium (exit-multiple method)': 'stage_premium', 'Liquidation haircut': 'liq_haircut', 'Gordon growth cap': 'g_cap'}


def annotate(A, est):
    """Add today's market or data estimate to the basis of the appendix's fixed assumptions."""
    E = {e['key']: e for e in est.get('entries') or []}
    for row in ((A.get('appendix') or {}).get('assumptions') or []):
        e = E.get(APPENDIX_KEYS.get(row[0])) if isinstance(row, list) and len(row) >= 3 else None
        if not e or not fin(e.get('market')) or 'today:' in str(row[2]):
            continue
        m = e['market']
        txt = (f'distressed companies trade at {m:.2f}× tangible book' if e['key'] == 'liq_haircut' else f'{m * 100:.2f}%')
        row[2] = f"{row[2]} · {'market' if e['kind'] == 'market' else 'data'} today: {txt}"

