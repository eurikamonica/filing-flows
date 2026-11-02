"""Simulations for the companies a regular DCF cannot value (app/valuation.py calls run() for every company, after the
stage block and before the lenses).

Pipeline rNPV, solved from the price (out['rnpv']; drug developers without operating profit and with less than $100M
of revenue a year — whose value is mostly the pipeline — SIC 2833–2836 or 8731)
  A drug developer is worth its cash plus the risk-adjusted value of its drug programs. A program in phase k reaches the
  market with the industry's historical likelihood of approval (LOA) from that phase, and if it does, it earns sales
  that ramp up to a peak, hold, and fall away when exclusivity ends. No filing prices those peak sales, so the model
  runs backwards: what yearly peak sales per program make the price fair?

    EV the price puts on the pipeline   = market value − (cash − debt − other claims)
    each program's value per $1 of peak sales
                    f = Σₖ shapeₖ × mature margin × (1 − tax) ÷ (1 + r)^(L + k − ½),   L = years to launch
    cost still to pay                  B = this year's cash burn, every year until the first launch, discounted
    required peak sales per program    S = (EV + B) ÷ Σ LOAᵢ × fᵢ   (and for the lead program alone: (EV + B) ÷ LOA × f)

  Inputs: the programs from ClinicalTrials.gov (app/outside.py trial_programs: a sponsor's interventional studies grouped
  by drug, the highest active phase, the next primary completion); the phase transition rates and durations of BIO /
  Informa Pharma Intelligence / QLS, "Clinical Development Success Rates 2011–2020" (2021) — all indications, and oncology
  separately; the mature margin = the median quarterly operating margin of drug makers (SIC 283) with $10–50B of revenue
  since 2020 (the outside view's peer panel); the company's own WACC and cash burn. The programs are sponsored under the
  company's own name or a listed subsidiary (app/outside.py is_company) and number at most 30.
  Catalysts: each readout due within 18 months moves the value by LOA × f × S × (1 ÷ p − 1) if it succeeds and by
  −LOA × f × S if it fails, p = the phase's transition rate — an expected change of zero, by construction.

Schwartz–Moon simulation (a lens; companies with at least $25M of revenue and an operating loss, or negative free cash
flow at an operating margin under 5% — not profitable companies that invest more than they earn and borrow for it, such
as utilities, for which "no new money" would be meaningless)
  Schwartz and Moon (2000, 2001) valued companies like Amazon in 1999 as a simulation in which revenue growth and costs
  wander, the company carries a cash balance, and it goes bankrupt when the cash runs out. In yearly steps, 10 years,
  2,000 paths (the regime model's common random numbers). "The panel" is every SEC filer with the last complete year on
  file (sim_backtest.panel_now: the construction the backtest checks), not the covered companies — today's listed
  survivors, whose past losses all ended well enough for them to still be here:
    growth      g₁ = today's growth (analysts' next fiscal year when ≥ 3 cover it) + σ_g × ε;
                gₜ₊₁ = ḡ + φ × (gₜ − ḡ) + σ_g × ε: growth fades at the panel's persistence φ (pooled AR(1) of yearly growth,
                app/markov.py) toward ḡ = the median five-year revenue growth of its peers (same industry and size, the
                outside view of app/base_rates.py; 2.5–15%); σ_g = its own spread of yearly growth over the last five
                years shrunk toward the panel's growth surprise with the weight of four years (markov.shrunk_sd: its own
                spread alone made the 80% revenue range too narrow in the backtest, app/sim_backtest.py)
    margin      while negative: mₜ₊₁ = mₜ + a − κ_loss × mₜ + σ(mₜ) × η — the intercept and slope of one winsorized
                regression of the yearly margin change on the margin over every loss-making company-year since 2010, the
                surprise growing with the depth of the loss, σ = s0 + s1 × |m| (pulling toward the peer margin at κ_loss
                instead overstated, in the backtest, how many loss-makers turned profitable); once positive:
                mₜ₊₁ = mₜ + κ × (target − mₜ) + σ × η, target = the peer median operating margin (as the path-to-margin
                DCF), the panel's general pull-back and the spread of profitable companies' margin changes. η is
                correlated with ε at the panel's ρ
    cash flow   the site's FCFF (web/fsa.js, as the base DCF): NOPAT + D&A − capex − 10% of each revenue increase, with D&A
                and capex as today's shares of revenue and capex above D&A moving halfway to it by year 5 — so year 1 starts
                from the company's actual cash flow
    tax         21%, only on profit above the losses carried forward (net operating loss, NOL), which start at zero
    cash        cashₜ = cashₜ₋₁ × (1 + 1-year Treasury) + FCFF + stock-based pay (today's share of revenue: a cost in the
                value, but paid in shares, not cash) − interest on the debt outstanding; maturing debt is rolled over (as
                Schwartz and Moon, whose model has no maturities); a shortfall is drawn on the undrawn credit line (its
                filed remaining borrowing capacity, app/debt.py), which then bears interest; below zero with the line used
                up = bankrupt: the shares are worth nothing on that path (Schwartz–Moon's rule). Beside it, a stress: the
                chance the cash runs out if the debt the filed maturity schedule says falls due in years 1–5 cannot be
                refinanced and must be repaid
    value       survivors: Σ FCFF ÷ (1 + WACC)ᵗ + terminal value (NOPAT × (1 − g ÷ 15% ROIC) ÷ (WACC − g), zero if the
                margin is still negative in year 10) + cash − debt − claims, per share, floored at zero
  The point is the mean (a share that can go to zero is worth its average outcome, not its median); the bar is the
  10th–90th percentile. Also: the chance the cash runs out by each year, when operating profit arrives, and the value if
  every shortfall is instead raised by issuing shares at today's price (the path-to-margin DCF's convention).
"""
import datetime as dt
import math
import re

import markov as MK
import sim_backtest as SB

# BIO / Informa Pharma Intelligence / QLS Advisors, Clinical Development Success Rates 2011–2020 (2021)
PHASE_RATES = {'all': {'1': 0.520, '2': 0.289, '3': 0.578, 'nda': 0.906},
               'onc': {'1': 0.488, '2': 0.246, '3': 0.477, 'nda': 0.920}}
PHASE_YEARS = {'1': 2.3, '2': 3.6, '3': 3.3, 'nda': 1.3}
RATES_SOURCE = 'BIO / Informa Pharma Intelligence / QLS, Clinical Development Success Rates 2011–2020 (2021)'
SALES_SHAPE = [0.2, 0.4, 0.6, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.25, 0.1, 0.05]   # share of peak sales, years after launch
DRUG_SIC = set(range(2833, 2837)) | {8731}
MAX_PROGRAMS = 30
MAX_PIPELINE_REVENUE = 100e6     # above this the value includes products on sale, which the pipeline method does not separate
DRUG_TAX = 0.21
CATALYST_DAYS = 550
SM_YEARS = 10
SM_ROIC = 0.15
SM_TAX = 0.21
SM_MAX_MARGIN = 0.05        # negative free cash flow counts only below this operating margin (a utility funding its capex is not burning cash)
MIN_SM_REVENUE = 25e6
PHASE_KEY = {'EARLY_PHASE1': '1', 'PHASE1': '1', 'PHASE2': '2', 'PHASE3': '3'}


def fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _sic(F):
    try:
        return int(str(F.get('sic') or '0')[:4])
    except ValueError:
        return 0


# ---------------------------------------------------------------- the pipeline rNPV
def loa(phase, onc):
    """Likelihood of approval from the start of `phase` ('1', '2', '3'): the product of the transition rates to approval."""
    R = PHASE_RATES['onc' if onc else 'all']
    out = 1.0
    for k in ('1', '2', '3', 'nda')[('1', '2', '3').index(phase):]:
        out *= R[k]
    return out


def years_to_launch(phase, readout, today):
    """The current phase's remaining time (to its next primary completion when one is due, else half its average length)
    plus every later phase and the review."""
    rest = 0.0
    if readout:
        try:
            d = dt.date.fromisoformat((readout + '-15')[:10] if len(readout) == 7 else readout[:10])
            rest = max(0.25, (d - today).days / 365.25)
        except ValueError:
            readout = None
    if not readout:
        rest = PHASE_YEARS[phase] / 2
    for k in ('1', '2', '3', 'nda')[('1', '2', '3').index(phase) + 1:]:
        rest += PHASE_YEARS[k]
    return rest


def pv_per_peak(L, r, margin, tax=DRUG_TAX):
    """Present value of $1 of yearly peak sales of a drug launched in L years: the sales curve × margin × (1 − tax)."""
    return sum(s * margin * (1 - tax) / (1 + r) ** (L + k - 0.5) for k, s in enumerate(SALES_SHAPE, 1))


def rnpv(F, W, out, trials, mature, today, VMx):
    """The 'rnpv' block, or (None, why)."""
    if _sic(F) not in DRUG_SIC:
        return None, None
    oi = F.get('oi')
    if fin(oi) and oi > 0:
        return None, 'profitable already: its value rests on drugs it sells, which the DCF and multiples cover'
    if fin(F.get('revenue')) and F['revenue'] >= MAX_PIPELINE_REVENUE:
        return None, (f'it already has {VMx.money(F["revenue"])} of revenue a year: its value includes products on sale, which this method '
                      'does not separate from the pipeline')
    progs = (trials or {}).get('programs')
    if not trials:
        return None, 'no ClinicalTrials.gov studies found under its name (Beyond the filings)'
    if progs is None:
        return None, 'the drug-program list arrives with the next Beyond the filings build'
    PF = (trials.get('program_fields') or ['drug', 'phase', 'active', 'studies', 'conditions', 'next_primary_completion', 'oncology', 'other_names'])
    rows = [dict(zip(PF, r)) for r in progs]
    rows = [r for r in rows if r.get('phase') in PHASE_KEY]
    if not rows:
        return None, 'no drug program in phase 1–3 (phase 4 means already marketed)'
    if len(rows) > MAX_PROGRAMS:
        return None, f'{len(rows)} programs under its name — more than one company plausibly runs, so the match is not trusted'
    W = W or {}
    r = W.get('wacc')
    sh, mcap, price = F.get('shares'), F.get('mcap'), F.get('price')
    if not (fin(r) and fin(sh) and sh > 0 and fin(mcap) and mcap > 0 and fin(price) and price > 0 and mature and fin(mature.get('p50'))):
        return None, 'needs the WACC, the share count, the price and the drug makers\' margin'
    r = max(r, 0.06)
    margin = clamp(mature['p50'], 0.10, 0.45)
    nc = (F.get('cash') or 0) - (F.get('debt') or 0) - (F.get('claims') or 0)
    ev = mcap - nc
    m = ((out.get('stage') or {}).get('metrics') or {})
    fcf = m.get('fcf') if fin(m.get('fcf')) else VMx.fcf_of(F)
    burn = max(0.0, -fcf) if fin(fcf) else 0.0
    P = []
    for x in rows:
        ph = PHASE_KEY[x['phase']]
        onc = bool(x.get('oncology'))
        L = years_to_launch(ph, x.get('next_primary_completion') if x.get('active') else None, today)
        p_ok = loa(ph, onc)
        P.append({'drug': x.get('drug'), 'other_names': x.get('other_names') or [], 'phase': ph, 'oncology': onc, 'conditions': x.get('conditions'),
                  'active': bool(x.get('active')), 'studies': x.get('studies'), 'readout': x.get('next_primary_completion'),
                  'loa': p_ok, 'p_next': PHASE_RATES['onc' if onc else 'all'][ph], 'years_to_launch': L})
    Lmin = min(p['years_to_launch'] for p in P)

    def solve(rate):
        for p in P:
            p['f'] = pv_per_peak(p['years_to_launch'], rate, margin)
        pvb = sum(burn * min(1.0, Lmin - (t - 1)) / (1 + rate) ** (t - 0.5) for t in range(1, math.ceil(Lmin) + 1))
        tot = sum(p['loa'] * p['f'] for p in P)
        need = ev + pvb
        lead = max(P, key=lambda p: p['loa'] * p['f'])
        return (max(0.0, need) / tot if tot > 0 else None), (max(0.0, need) / (lead['loa'] * lead['f']) if lead['f'] > 0 else None), pvb, lead
    s_lo, _, _, _ = solve(r - 0.02)
    s_hi, _, _, _ = solve(r + 0.02)
    S, S_lead, pvb, lead = solve(r)                          # last: leaves each program's f at the company's own rate
    if S is None:
        return None, 'the programs\' value could not be computed'
    p_none = 1.0
    for p in P:
        p_none *= 1 - p['loa']
        p['value_ps'] = p['loa'] * p['f'] * S / sh
    cutoff = (today + dt.timedelta(days=CATALYST_DAYS)).isoformat()
    cats = []
    for p in P:
        if p['active'] and p['readout'] and p['readout'][:10] <= cutoff and p['readout'][:7] >= today.isoformat()[:7]:
            base = p['loa'] * p['f'] * S / sh
            up, down = base * (1 / p['p_next'] - 1), -base
            cats.append({'drug': p['drug'], 'phase': p['phase'], 'date': p['readout'], 'p_success': p['p_next'],
                         'up_ps': up, 'down_ps': down, 'up_pct': up / price, 'down_pct': down / price})
    cats.sort(key=lambda c: c['date'])
    R = PHASE_RATES
    calc = VMx.calc('Required peak sales per program S = (EV the price puts on the pipeline + PV of the cash burn until the first launch) ÷ Σ LOAᵢ × fᵢ;  '
                    'fᵢ = Σₖ shareₖ × margin × (1 − tax) ÷ (1 + r)^(Lᵢ + k − ½)',
                    [f'EV of the pipeline = market value {VMx.money(mcap)} − net cash {VMx.money(nc)} = {VMx.money(ev)}',
                     f'cash burn {VMx.money(burn)} a year until the first launch in {Lmin:.1f} years, discounted at {VMx.pc(r)} = {VMx.money(pvb)}',
                     'programs: ' + '; '.join(f'{p["drug"]} (phase {p["phase"]}{", oncology" if p["oncology"] else ""}): LOA {VMx.pc(p["loa"])}, launch in {p["years_to_launch"]:.1f} years, '
                                             f'f = {p["f"]:.3f}' for p in P[:12]) + (f'; and {len(P) - 12} more' if len(P) > 12 else ''),
                     f'Σ LOA × f = {sum(p["loa"] * p["f"] for p in P):.3f} → S = ({VMx.money(ev)} + {VMx.money(pvb)}) ÷ {sum(p["loa"] * p["f"] for p in P):.3f} = {VMx.money(S)} a year per program',
                     f'the lead program alone ({lead["drug"]}): {VMx.money(S_lead)} a year at peak',
                     f'discount rate ±2 points: {VMx.money(s_lo)} – {VMx.money(s_hi)} per program',
                     f'chance that no program is approved = Π (1 − LOAᵢ) = {VMx.pc(p_none)} (programs treated as independent)'],
                    [['Market value', VMx.money(mcap), 'price × diluted shares'], ['Cash and investments', VMx.money(F.get('cash')), VMx.src_of(F, 'cash')],
                     ['Debt', VMx.money(F.get('debt')), VMx.src_of(F, 'debt')], ['Cash burn (free cash flow)', VMx.money(-burn), 'operating income + D&A − capex, four quarters'],
                     ['Programs', f'{len(P)}', f'ClinicalTrials.gov, sponsor {trials.get("sponsor")} (Beyond the filings)']],
                    [['Phase transition rates (all / oncology)', ' · '.join(f'{k}: {R["all"][k] * 100:.1f}% / {R["onc"][k] * 100:.1f}%' for k in ('1', '2', '3', 'nda')), RATES_SOURCE],
                     ['Phase lengths', ' · '.join(f'{k}: {v} years' for k, v in PHASE_YEARS.items()), RATES_SOURCE + '; the current phase ends at its next primary completion, else halfway'],
                     ['Sales curve after launch', ', '.join(f'{int(s * 100)}%' for s in SALES_SHAPE) + ' of peak', 'an assumption: five years to peak, five at peak, then exclusivity ends'],
                     ['Mature margin', VMx.pc(margin), f'median quarterly operating margin of {mature.get("label") or "drug makers"} ({mature.get("n")} quarters) since 2020'],
                     ['Tax on drug profits', VMx.pc(DRUG_TAX, 0), 'US federal rate (an assumption)'], ['Discount rate', VMx.pc(r), 'the company\'s WACC (build-up above), at least 6%'],
                     ['Costs after the first launch', 'inside the mature margin', 'a mature drug maker\'s margin already pays for its research and selling']])
    out_doc = {'ev': ev, 'net_cash': nc, 'burn': burn, 'pv_burn': pvb, 'margin': margin, 'rate': r, 'required_peak': S, 'required_peak_lo': s_lo,
               'required_peak_hi': s_hi, 'required_peak_lead': S_lead, 'lead': lead['drug'], 'p_none': p_none, 'expected_approvals': sum(p['loa'] for p in P),
               'first_launch_years': Lmin, 'sponsor': trials.get('sponsor'), 'net_cash_ps': nc / sh,
               'programs': [{k: p[k] for k in ('drug', 'other_names', 'phase', 'oncology', 'conditions', 'active', 'studies', 'readout', 'loa', 'p_next',
                                               'years_to_launch', 'f', 'value_ps')} for p in P],
               'catalysts': cats[:12], 'calc': calc, 'mature': {k: mature.get(k) for k in ('label', 'n', 'p25', 'p50', 'p75')},
               'note': ('The price is solved backwards: these are the peak sales the market must expect, not a forecast. Programs are grouped from '
                        'ClinicalTrials.gov by drug name — a drug listed under both a code name and a generic name that never appear together counts '
                        'twice. Success rates are industry averages; a specific drug can be far better or worse. Not investment advice.')}
    return out_doc, None


# ---------------------------------------------------------------- the Schwartz–Moon simulation
def liquidity(F, drec):
    """(undrawn credit line, [debt due in years 1–5] or None, as-of date) from the debt module (app/debt.py): the
    remaining borrowing capacity it reads from the filings (LineOfCreditFacilityRemainingBorrowingCapacity) and the
    filed maturity schedule (LongTermDebtMaturitiesRepayments…), the total capped at the debt on the balance sheet."""
    a, sn = (drec or {}).get('analysis') or {}, (drec or {}).get('snapshot') or {}
    room = a.get('revolver_available') if fin(a.get('revolver_available')) else sn.get('revolver_available')
    room = room if fin(room) and room > 0 else 0.0
    mt = sn.get('maturities') or {}
    y1 = mt.get('next12m') if fin(mt.get('next12m')) else mt.get('rest_of_year')
    raw = [y1] + [mt.get(k) for k in ('y2', 'y3', 'y4', 'y5')]
    if not any(fin(v) for v in raw):
        return room, None, None
    left, due = max(0.0, F.get('debt') or 0.0), []
    for v in raw:
        v = min(max(0.0, v), left) if fin(v) else 0.0
        due.append(v)
        left -= v
    return room, due, mt.get('as_of')


def schwartz_moon(F, W, out, prior_b, rates, cons_c, price_date, tm, n=MK.N_PATHS, g_bar=None, drec=None):
    """(football item, section block) or (None, why)."""
    rev, sh, price = F.get('revenue'), F.get('shares'), F.get('price')
    oi = F.get('oi')
    if F.get('kind') != 'industrial':
        return None, None
    m_ = (out.get('stage') or {}).get('metrics') or {}
    fcf = m_.get('fcf')
    burning = (fin(oi) and oi <= 0) or (fin(fcf) and fcf < 0 and fin(oi) and fin(rev) and rev > 0 and oi / rev < SM_MAX_MARGIN)
    if not burning:
        return None, None
    if not (fin(rev) and rev >= MIN_SM_REVENUE):
        return None, 'needs at least $25M of revenue over four quarters (pre-revenue companies: the pipeline and net-cash methods)'
    W = W or {}
    if not (fin(sh) and sh > 0 and fin(price) and price > 0 and fin(W.get('wacc')) and fin(oi) and prior_b and fin(tm)):
        return None, 'needs the WACC, the share count, the peer margin and the panel statistics'
    wacc = W['wacc']
    gT = MK.TERM_G
    gbar, gbar_how = (clamp(g_bar[0], gT, 0.15), g_bar[1]) if g_bar and fin(g_bar[0]) else (gT, 'no peer history: the terminal growth')
    cons, _, cons_how = MK.consensus_growth(cons_c, price_date)
    g0 = cons[0] if cons else (clamp(F['g0'], -0.3, 1.0) if fin(F.get('g0')) else 0.0)
    phi, sg_panel = prior_b.get('g_phi', MK.DEFAULT_AR[0]), prior_b.get('g_res_sd', MK.DEFAULT_AR[1])
    sg, sg_how = growth_spread(F, sg_panel)
    m0 = oi / rev
    kap = prior_b.get('kappa', 0.3)                          # once profitable: the panel's general pull-back
    kl = prior_b.get('loss_kappa', 0.2)                      # while losing money: loss-makers' average yearly change,
    la = prior_b.get('loss_a', -0.01)                        # a − κ_loss × m, from one regression (see the backtest)
    s0, s1, sp = prior_b.get('loss_sd0', 0.05), prior_b.get('loss_sd1', 0.4), prior_b.get('prof_sd', 0.035)
    rho = prior_b.get('rho_gm', 0.0)
    rq = math.sqrt(max(0.0, 1 - rho * rho))
    d0, c0 = (F.get('da') or 0) / rev, (F.get('capex') or 0) / rev
    capex = [c0 + ((c0 + d0) / 2 - c0) * min(t, 4) / 4 for t in range(SM_YEARS)] if c0 > d0 else [c0] * SM_YEARS   # the base DCF's rule
    cash0, debt, claims = F.get('cash') or 0.0, F.get('debt') or 0.0, F.get('claims') or 0.0
    room0, due, due_asof = liquidity(F, drec)
    sbc0 = clamp(F['sbc'] / rev, 0.0, 0.5) if fin(F.get('sbc')) and F['sbc'] > 0 else 0.0   # paid in shares, not cash
    panel = prior_b.get('source') or 'the covered companies since 2010 (app/markov.py)'
    due_t = (due or []) + [0.0] * SM_YEARS
    kd = W.get('kd') if fin(W.get('kd')) else 0.06
    rc = (rates.get('treasury_1y') or 4.0) / 100 if fin(rates.get('treasury_1y')) else 0.04
    m_lo = min(-0.5, m0 - 0.5)
    U, Zg, Zm = MK.draws(n, SM_YEARS)
    T = SM_YEARS
    vals, vals_dil, dil = [], [], []
    fail_year = [0] * (T + 1)                               # fail_year[t]: paths that ran out of cash in year t (0: never)
    fail_norefi = [0] * (T + 1)                             # the same if no maturing debt can be refinanced
    profit_year = [0] * (T + 1)
    revs = [[0.0] * n for _ in range(T)]
    mars = [[0.0] * n for _ in range(T)]
    cap = max(wacc - gT, 0.01)
    for i in range(n):
        rv, m, g, cash, nol, pv, df = rev, m0, g0, cash0, 0.0, 0.0, 1.0
        alive, failed_at, first_profit, new_sh, cash_d = True, 0, 0, 0.0, cash0
        debt_a, room_a, debt_d, room_d = debt, room0, debt, room0    # debt outstanding and credit line left, each convention
        cash_r, debt_r, room_r, failed_r = cash0, debt, room0, 0
        for t in range(T):
            k = i * T + t
            e = Zg[k]
            eta = rho * e + rq * Zm[k]
            g = (g0 if t == 0 else gbar + phi * (g - gbar)) + sg * e
            g = clamp(g, MK.G_CLIP[0], MK.G_CLIP[1])
            prev = rv
            rv = prev * (1 + g)
            m = clamp(m + (la - kl * m + (s0 + s1 * -m) * eta if m < 0 else kap * (tm - m) + sp * eta), m_lo, 0.7)
            ebit = rv * m
            if ebit > 0:
                taxable = max(0.0, ebit - nol)
                nol = max(0.0, nol - ebit)
                tax = taxable * SM_TAX
            else:
                nol += -ebit
                tax = 0.0
            fcff = ebit - tax + rv * (d0 - capex[t]) - (rv - prev) * 0.10
            df /= 1 + wacc
            pv += fcff * df
            revs[t][i] = rv
            mars[t][i] = m
            if ebit > 0 and not first_profit:
                first_profit = t + 1
            if alive:                                       # maturing debt is rolled over; the credit line covers a shortfall
                cash = cash * (1 + rc) + fcff + sbc0 * rv - kd * debt_a
                if cash < 0 < room_a:
                    draw = min(-cash, room_a)
                    cash, room_a, debt_a = cash + draw, room_a - draw, debt_a + draw
                if cash < 0:
                    alive, failed_at = False, t + 1
            if due is not None and not failed_r:            # the stress: the debt due each year must be repaid from cash
                cash_r = cash_r * (1 + rc) + fcff + sbc0 * rv - kd * debt_r - due_t[t]
                debt_r -= due_t[t]
                if cash_r < 0 < room_r:
                    draw = min(-cash_r, room_r)
                    cash_r, room_r, debt_r = cash_r + draw, room_r - draw, debt_r + draw
                if cash_r < 0:
                    failed_r = t + 1
            cash_d = cash_d * (1 + rc) + fcff + sbc0 * rv - kd * debt_d
            if cash_d < 0 < room_d:
                draw = min(-cash_d, room_d)
                cash_d, room_d, debt_d = cash_d + draw, room_d - draw, debt_d + draw
            if cash_d < 0:                                  # the other convention: raise the shortfall in new shares
                new_sh += -cash_d / price
                cash_d = 0.0
        nxt = rv * (1 + gT)
        tv = nxt * m * (1 - SM_TAX) * (1 - gT / SM_ROIC) / cap if m > 0 else 0.0
        eq = pv + tv * df + cash0 - debt - claims
        vals.append(max(0.0, eq) / sh if alive else 0.0)
        vals_dil.append(max(0.0, eq) / (sh + new_sh))
        dil.append(new_sh / sh)
        fail_year[failed_at] += 1
        fail_norefi[failed_r] += 1
        if first_profit and (alive or first_profit <= failed_at):
            profit_year[first_profit] += 1
    s = MK.summarize(vals, price)
    if not s:
        return None, 'the simulation did not produce enough values'
    surv, cum = [], 0
    for t in range(1, T + 1):
        cum += fail_year[t]
        surv.append(1 - cum / n)
    prof, cum = [], 0
    for t in range(1, T + 1):
        cum += profit_year[t]
        prof.append(cum / n)
    q = lambda xs, p: MK.pctile(xs, p)                      # noqa: E731
    fan = {'revenue': [[q(revs[t], 0.1), q(revs[t], 0.5), q(revs[t], 0.9)] for t in range(T)],
           'margin': [[q(mars[t], 0.1), q(mars[t], 0.5), q(mars[t], 0.9)] for t in range(T)]}
    mean_dil = sum(vals_dil) / n
    med_dil = MK.pctile(dil, 0.5)
    p_fail5, p_fail10 = 1 - surv[4], 1 - surv[-1]
    norefi = [sum(fail_norefi[1:t + 1]) / n for t in (5, 10)] if due is not None else None
    burn = fcf + sbc0 * rev if fin(fcf) else None          # the cash it uses: free cash flow before the stock-based pay
    runway = (cash0 + room0) / -burn if fin(burn) and burn < 0 else None    # cash and the undrawn credit line at today's burn
    calc = {'formula': 'Value = mean over paths of: 0 if the cash runs out, else (Σ FCFFₜ ÷ (1 + WACC)ᵗ + TV ÷ (1 + WACC)¹⁰ + cash − debt − claims) ÷ shares, floored at 0;  '
                       'gₜ₊₁ = ḡ + φ(gₜ − ḡ) + σ_g ε;  mₜ₊₁ = mₜ + a − κ_loss mₜ + σ(mₜ) η while mₜ < 0, mₜ + κ(target − mₜ) + σ η once profitable;  FCFFₜ = NOPATₜ + D&A − capex − 10% × ΔRevenueₜ;  cashₜ = cashₜ₋₁(1 + r) + FCFFₜ + stock-based payₜ − interest (+ credit-line draws)',
            'steps': [f'start: revenue {_money(rev)}, growth {g0 * 100:+.1f}%{" (analysts)" if cons else ""}, operating margin {m0 * 100:.1f}%, cash {_money(cash0)}, debt {_money(debt)}',
                      f'growth fades toward ḡ = {gbar * 100:.1f}% with persistence φ = {phi:.2f}, spread σ_g = {sg * 100:.1f} points; while losing money the margin changes by '
                      f'{la * 100:+.1f} points − {kl:.2f} × the margin a year (surprise σ = {s0 * 100:.1f} + {s1:.2f} × |m| points), once profitable it is pulled toward '
                      f'{tm * 100:.1f}% at κ = {kap:.2f} (σ = {sp * 100:.1f} points); shock correlation ρ = {rho:.2f}',
                      f'D&A {d0 * 100:.1f}% and capex {c0 * 100:.1f}% of revenue' + (f', capex moving to {capex[-1] * 100:.1f}% by year 5' if c0 > d0 else ''),
                      f'liquidity: cash {_money(cash0)} + undrawn credit line {_money(room0)}; debt due in years 1–5: '
                      + (' / '.join(_money(v) for v in due) + (f' (schedule as of {due_asof})' if due_asof else '') + ', rolled over' if due is not None else 'no filed schedule'),
                      f'{n:,} paths × {T} years: cash runs out by year 5 in {p_fail5 * 100:.0f}% of paths, by year 10 in {p_fail10 * 100:.0f}%; '
                      f'operating profit reached by year 5 in {prof[4] * 100:.0f}%'
                      + (f'; if none of the maturing debt could be refinanced, the cash would run out by year 5 in {norefi[0] * 100:.0f}%' if norefi else ''),
                      f'mean value {_ps(s["mean"])} (10th–90th percentile {_ps(s["p10"])} – {_ps(s["p90"])}; median {_ps(s["p50"])})',
                      f'if every shortfall is raised in new shares at today\'s {_ps(price)} instead: mean {_ps(mean_dil)}, median dilution {med_dil * 100:.0f}%'],
            'inputs': [['Revenue, four quarters', _money(rev), 'SEC XBRL frames / main site'], ['Operating income, four quarters', _money(oi), 'SEC XBRL frames / main site'],
                       ['Cash and investments', _money(cash0), 'SEC XBRL frames / main site'], ['Debt', _money(debt), 'SEC XBRL frames / main site'],
                       ['Diluted shares', f'{sh:,.0f}', 'SEC XBRL frames / main site']],
            'assumptions': [['Starting growth', f'{g0 * 100:+.1f}%', cons_how or 'last four quarters vs the four before'],
                            ['Growth persistence φ', f'{phi:.2f}', f'pooled AR(1) of yearly growth, {prior_b.get("g_pairs")} pairs: {panel}'],
                            ['Growth it fades toward ḡ', f'{gbar * 100:.1f}%', gbar_how],
                            ['Growth spread σ_g', f'{sg * 100:.1f} points', sg_how],
                            ['Target margin', f'{tm * 100:.1f}%', 'peer median operating margin (SIC industry × size)'],
                            ['Margin change while losing money', f'{la * 100:+.1f} points − {kl:.2f} × the margin a year, σ = {s0 * 100:.1f} + {s1:.2f} × |m| points',
                             f'one winsorized regression of the yearly margin change on the margin over {prior_b.get("loss_n")} loss-making company-years: {panel} '
                             '(app/markov.py); the backtest found that pulling loss-makers toward the peer margin instead overstated how many turned profitable'],
                            ['Margin pace once profitable', f'κ = {kap:.2f}, σ = {sp * 100:.1f} points', 'the panel\'s pull-back; profitable companies\' margin changes'],
                            ['D&A, capex, working capital', f'{d0 * 100:.1f}%, {c0 * 100:.1f}% of revenue; 10% of each increase', 'the filings; the base DCF\'s rules (capex above D&A moves halfway to it by year 5)'],
                            ['Shock correlation ρ', f'{rho:.2f}', f'growth surprises vs margin changes ({prior_b.get("rho_n")} pairs): {panel}'],
                            ['Tax', '21% above the losses carried forward', 'US federal rate; losses carried forward start at zero (not in the frames)'],
                            ['Interest on cash / on debt', f'{rc * 100:.2f}% / {kd * 100:.2f}%', '1-year Treasury / the company\'s cost of debt'],
                            ['Stock-based pay', f'{sbc0 * 100:.1f}% of revenue', 'the filings; a cost in the value (inside operating income), but paid in shares, '
                             'so added back in the cash track' if sbc0 > 0 else 'none on file'],
                            ['Undrawn credit line', _money(room0), 'remaining borrowing capacity in the filings (app/debt.py); drawn when the cash runs short' if room0 > 0 else 'none on file'],
                            ['Debt due, years 1–5', ' / '.join(_money(v) for v in due) if due is not None else 'no schedule on file',
                             'the filed maturity schedule (app/debt.py): rolled over in the simulation; repaid from cash in the stress beside it' if due is not None else 'only interest is paid'],
                            ['Bankruptcy', 'cash below zero', 'Schwartz–Moon (2000): no new money is assumed; the other convention is shown beside it'],
                            ['Terminal value', f'{gT * 100:.1f}% growth, ROIC {SM_ROIC * 100:.0f}%', 'zero when the year-10 margin is still negative'],
                            ['Method', 'Schwartz & Moon, "Rational pricing of internet companies" (2000); "… revisited" (2001)', '']],
            'source': None, 'kind': 'model'}
    item = {'method': 'Schwartz–Moon simulation (cash can run out)', 'low': s['p10'], 'high': s['p90'], 'point': s['mean'], 'lens': True, 'calc': calc,
            'note': f'mean of {n:,} paths; cash runs out by year 5 in {p_fail5 * 100:.0f}%, operating profit by year 5 in {prof[4] * 100:.0f}%'}
    block = {'n': n, 'years': T, **{k: s[k] for k in ('mean', 'p5', 'p10', 'p25', 'p50', 'p75', 'p90', 'p95', 'p_above', 'hist')},
             'p_zero': sum(1 for v in vals if v <= 0) / n, 'survival': surv, 'profit_by': prof, 'p_fail5': p_fail5, 'p_fail10': p_fail10,
             'p_fail5_norefi': norefi[0] if norefi else None, 'p_fail10_norefi': norefi[1] if norefi else None,
             'fan': fan, 'dilution': {'mean_value': mean_dil, 'median_new_shares': med_dil, 'p90_new_shares': MK.pctile(dil, 0.9)},
             'runway_years': runway, 'inputs': {'g0': g0, 'phi': phi, 'sg': sg, 'sg_how': sg_how, 'm0': m0, 'target_margin': tm, 'kappa': kap, 'kappa_loss': kl, 'a_loss': la,
                                                'sd_loss': [s0, s1], 'sd_profit': sp, 'da': d0, 'capex': c0, 'g_bar': gbar, 'rho': rho,
                                                'cash': cash0, 'debt': debt, 'kd': kd, 'r_cash': rc, 'wacc': wacc, 'consensus': bool(cons),
                                                'credit_line': room0, 'due': due, 'due_as_of': due_asof, 'sbc': sbc0, 'panel': panel}}
    return (item, block), None


def growth_spread(F, panel_sd):
    """(σ_g, where it comes from): the company's spread of yearly growth shrunk toward the panel's growth surprise
    (markov.shrunk_sd: its own spread alone made the 80% revenue range too narrow in the backtest)."""
    gs = [g for g, _ in F.get('years') or [] if fin(g)]
    k = MK.SD_SHRINK_K
    if len(gs) >= 3:
        v, _ = MK.shrunk_sd(gs, panel_sd)
        how = (f'its yearly growth over the last {min(len(gs), 5)} years, shrunk toward the panel\'s growth surprise ({panel_sd * 100:.1f} points) '
               f'with the weight of {k:g} years: the spread that put about 80% of actual revenues inside the 80% range in the backtest')
    elif fin(F.get('sg')):
        v = math.sqrt((2 * F['sg'] ** 2 + k * panel_sd ** 2) / (2 + k))
        how = f'its quarterly year-on-year growth, shrunk toward the panel\'s growth surprise ({panel_sd * 100:.1f} points) with the weight of {k:g} years'
    else:
        v, how = panel_sd, 'the panel\'s growth surprise (AR(1) residual): too little own history'
    return clamp(v, 0.03, 0.40), how


def _money(v):
    if not fin(v):
        return '—'
    a, s = abs(v), '−' if v < 0 else ''
    for d, u in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if a >= d:
            return f'{s}${a / d:,.{2 if a / d < 100 else 1}f}{u}'
    return f'{s}${a:,.0f}'


def _ps(v):
    return '—' if not fin(v) else (f'−${abs(v):,.2f}' if v < 0 else f'${v:,.2f}')


# ---------------------------------------------------------------- everything, for one company
def target_margin(F, out, ctx, BR):
    """The peer median operating margin the path-to-margin DCF uses (the stage block's when it set one)."""
    tm = ((out.get('stage') or {}).get('metrics') or {}).get('target_margin')
    if fin(tm):
        return tm
    B = ctx.get('br') or {}
    if not B.get('D'):
        return None
    p = BR._peer(B['D'], 'opm_q', F.get('sic'), BR.size_of(F.get('revenue')), B.get('names') or {})
    return clamp(p['p50'], 0.08, 0.35) if p and fin(p.get('p50')) and p['p50'] > 0 else 0.15


def drug_margin(ctx, BR):
    """The median quarterly operating margin of drug makers (SIC 283) with $10–50B of revenue, widened by the outside
    view's rules when that group is thin."""
    B = ctx.get('br') or {}
    if not B.get('D'):
        return None
    p = BR._peer(B['D'], 'opm_q', '2834', 'L', B.get('names') or {})
    return {k: p[k] for k in ('label', 'n', 'p25', 'p50', 'p75')} if p else None


def run(M, VMx, BR, F, W, out, ctx):
    """Add the Schwartz–Moon lens and the pipeline rNPV to one company's analysis; reasons for what does not apply go to
    out['lens_why']."""
    why = out.setdefault('lens_why', {})
    tm = target_margin(F, out, ctx, BR)
    prior = (ctx.get('markov_prior') or {}).get(MK.bucket_of(F.get('mcap'))) or (ctx.get('markov_prior') or {}).get('all')
    if prior and ctx.get('sm_panel'):                       # every filer's dynamics, as the backtest checks them (sim_backtest.panel_now)
        prior = {**prior, **ctx['sm_panel']}
    gb = None
    B = ctx.get('br') or {}
    if B.get('D'):
        pk = BR._peer(B['D'], 'cagr5', F.get('sic'), BR.size_of(F.get('revenue')), B.get('names') or {})
        if pk and fin(pk.get('p50')):
            gb = (pk['p50'], f'median five-year revenue growth of {pk.get("label") or "its peers"} ({pk.get("n")} five-year windows since 2010)')
    res, reason = schwartz_moon(F, W, out, prior, ctx.get('rates') or {}, ctx.get('cons'), ctx.get('price_date'), tm, g_bar=gb, drec=ctx.get('debt'))
    if res:
        out['football'].append(res[0])
        out['schwartz_moon'] = res[1]
        out['schwartz_moon']['backtest'] = SB.for_page(ctx.get('backtest'), 'schwartz_moon')
    elif reason:
        why['Schwartz–Moon simulation (cash can run out)'] = reason
    today = dt.date.fromisoformat(ctx['price_date'][:10]) if ctx.get('price_date') else dt.date.today()
    rn, reason = rnpv(F, W, out, ctx.get('trials'), drug_margin(ctx, BR), today, VMx)
    if rn:
        out['rnpv'] = rn
    elif reason:
        out['rnpv_why'] = reason
    return out


CANDIDATES = ['Schwartz–Moon simulation (cash can run out)']
WHY_NOT = {'Schwartz–Moon simulation (cash can run out)': 'only for companies with at least $25M of revenue and an operating loss, or negative free cash flow at an operating margin under 5%'}


def fit_reason(name, F, out):
    if name.startswith('Schwartz–Moon'):
        sm = out.get('schwartz_moon') or {}
        rw = sm.get('runway_years')
        return ('It is losing money or burning cash' + (f' (about {rw:.1f} years of cash and credit line at today\'s burn)' if fin(rw) else '')
                + ', so whether the cash lasts until the business turns profitable is the question — the simulation lets growth and margins '
                'wander and counts the paths on which the money runs out.')
    return None
