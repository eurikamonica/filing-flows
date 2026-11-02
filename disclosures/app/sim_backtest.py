"""Walk-forward backtest of the Fair value simulations (app/valuation.py calls run() during the build; the result is
published as public/backtest.json and a one-line summary goes into each company's regime and Schwartz–Moon sections).

The question each test answers: had the model been run in an earlier year, with only the data filed by then, how often
would what actually happened have fallen inside its range?

Data: the SEC's annual XBRL frames since CY2010 for every filer — not only the companies covered today, so companies
that later stopped filing are part of the test (their outcomes count where an outcome exists). Origins every second
year from 2013 to five years before the latest frame; at each origin every input is re-estimated from the years up to
it: the hidden Markov model and its regimes, growth persistence, loss-makers' margin pace (app/markov.py), and the
size-bucket median five-year growth. Up to 700 companies with at least $10M of revenue per origin (a fixed hash order,
so the sample does not depend on the outcome), 200 paths each, horizons of 1, 3 and 5 years.

  revenue      the regime model (HMM regimes, the company's own soft transitions, today's regime probabilities), the
               Schwartz–Moon growth process (its latest growth fading toward the size bucket's median five-year growth at
               the panel's persistence), and a naive benchmark (yearly growth drawn from its own last five years, as if
               they repeat). Scored: the share of actual revenues inside the 10th–90th percentile band (80% is right;
               less means the range is too narrow), below and above it, and the median error of the median forecast.
  margin       loss-making companies under the Schwartz–Moon margin process: coverage of the actual operating margin, and
               the predicted chance of an operating profit against the share that had one (calibration by bins).
  cash runs out  when year-end cash and debt are on file (frames CY…Q4I), loss-makers' chance of running out of cash within
               three years against the share that stopped filing within three years. Stopping covers failure,
               delisting and acquisition alike, so this is an upper bound on failures; the page says so.

Survivorship: a revenue or margin outcome exists only for companies still filing at the horizon; the cash test is the
one that counts the companies that stopped.
"""
import datetime as dt
import math
import zlib

import markov as MK

VERSION = 1                 # bump when the method changes: the build recomputes instead of reusing last month's result
HORIZONS = (1, 3, 5)
N = 200
MAX_COS = 700
FIT_MAX = 1500              # companies the hidden Markov model is fitted on at each origin (fixed hash order)
MIN_REV = 10e6
MIN_CASH_ROWS = 100         # loss-makers with cash on file the cash test needs before it is scored
MIN_SM_REV = 25e6           # the margin and cash tests: loss-makers with the revenue the Schwartz–Moon section needs
REFRESH_DAYS = 30
SD_SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)    # the regime model's growth spreads × each; the one whose 3-year range holds
                                           # closest to 80% is published and used on the company pages (regime_sd_scale)
CASH_CONCEPT = 'CashAndCashEquivalentsAtCarryingValue'
DEBT_CONCEPT = 'LongTermDebt'
SIZES = ((1e9, 'S'), (10e9, 'M'), (50e9, 'L'))


def fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def size_of(rev):
    for edge, k in SIZES:
        if rev < edge:
            return k
    return 'XL'


def cut(a, Y):
    """A company's annual figures up to year Y."""
    return {k: {y: v for y, v in (a.get(k) or {}).items() if int(y) <= Y} for k in ('rev', 'oi')}


def quant(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def origin_panel(A, Y, prev_fit=None):
    """Everything the models need at origin Y, from the years up to Y only."""
    hist = {}
    for cik, a in A.items():
        ys, last = MK.annual_years(cut(a, Y))
        if len(ys) >= 2 and last == Y:
            hist[cik] = ys
    G = list(hist.values())
    if len(G) < 60:
        return None
    fit_on = [hist[c] for c in _sample(hist, Y, FIT_MAX)]
    fit = MK.hmm_fit([[g for g, _ in ys] for ys in fit_on], init=prev_fit, iters=80)
    stats = MK._stats(G, None, fit)
    gbar, margins = {}, {}
    for cik, a in A.items():
        rev, oi = a.get('rev') or {}, a.get('oi') or {}
        for y in range(Y - 4, Y + 1):
            r0, r1 = rev.get(y - 5), rev.get(y)
            if fin(r0) and fin(r1) and r0 >= MIN_REV and r1 > 0:
                gbar.setdefault(size_of(r0), []).append(clamp((r1 / r0) ** 0.2 - 1, -0.5, 1.0))
        r, o = rev.get(Y), oi.get(Y)
        if fin(r) and r >= MIN_REV and fin(o):
            margins.setdefault(size_of(r), []).append(clamp(o / r, -1.0, 1.0))
    return {'hist': hist, 'fit': fit, 'stats': stats,
            'gbar': {k: quant(v, 0.5) for k, v in gbar.items() if len(v) >= 40},
            'margin': {k: quant(v, 0.5) for k, v in margins.items() if len(v) >= 40}}


def _sample(ciks, Y, k=MAX_COS):
    return sorted(ciks, key=lambda c: zlib.crc32(f'{c}:{Y}'.encode()))[:k]


def growth_paths(model, ys, O, U, Zg, scale=1.0):
    """Cumulative log revenue at each horizon year 1..5 for N paths, under one of the three growth models (scale: the
    regime model's growth spreads × this)."""
    st = O['stats']
    gs = [g for g, _ in ys]
    T = max(HORIZONS)
    out = [[0.0] * N for _ in range(T)]
    if model == 'regime':
        fit = O['fit']
        if fit:
            post = MK.hmm_posterior(gs, fit)
            P = MK.posterior(post['xi'], st['P'])
            sp = post['now']
            tot = sum(sp)
            p = {'start_p': [v / tot for v in sp], 'start': 0}
        else:
            own = [[0] * 3 for _ in range(3)]
            s_ = [MK.state_of(g) for g in gs]
            for a, b in zip(s_, s_[1:]):
                own[a][b] += 1
            P = MK.posterior(own, st['P'])
            p = {'start': s_[-1]}
        s0 = MK.start_states(p, N)
        cum = [(r[0], r[0] + r[1]) for r in P]
        for i in range(N):
            s, lr = s0[i], 0.0
            for t in range(T):
                k = i * T + t
                c = cum[s]
                s = 0 if U[k] < c[0] else (1 if U[k] < c[1] else 2)
                lr += math.log(1 + clamp(st['g'][s] + scale * st['g_sd'][s] * Zg[k], *MK.G_CLIP))
                out[t][i] = lr
        return out
    own_sd = MK._winsor_mean_sd(gs[-5:])[1] if len(gs) >= 3 else None
    if model == 'schwartz_moon':
        gbar = O['gbar'].get(O['_size'], MK.TERM_G)
        gbar = clamp(gbar, MK.TERM_G, 0.15)
        phi, sg = st['g_phi'], clamp(MK.shrunk_sd(gs, st['g_res_sd'])[0], 0.03, 0.40)
        g0 = clamp(gs[-1], -0.3, 1.0)
        for i in range(N):
            g, lr = g0, 0.0
            for t in range(T):
                k = i * T + t
                g = clamp((g0 if t == 0 else gbar + phi * (g - gbar)) + sg * Zg[k], *MK.G_CLIP)
                lr += math.log(1 + g)
                out[t][i] = lr
        return out
    mu = sum(gs[-5:]) / len(gs[-5:])                        # naive: its last five years repeat
    sd = clamp(own_sd, 0.02, 0.60) if fin(own_sd) else st['g_res_sd']
    for i in range(N):
        lr = 0.0
        for t in range(T):
            k = i * T + t
            lr += math.log(1 + clamp(mu + sd * Zg[k], *MK.G_CLIP))
            out[t][i] = lr
    return out


def margin_paths(m0, O, Zg, Zm):
    """Operating margin at each horizon year for N paths under the Schwartz–Moon margin process (its surprise correlated
    with the growth surprise at the panel's ρ, as on the company pages)."""
    st = O['stats']
    rho = st.get('rho_gm', 0.0)
    rq = math.sqrt(max(0.0, 1 - rho * rho))
    tm = clamp(O['margin'].get(O['_size'], 0.08), 0.08, 0.35)
    kl, la, s0, s1, sp, kap = st['loss_kappa'], st['loss_a'], st['loss_sd0'], st['loss_sd1'], st['prof_sd'], st['kappa']
    T = max(HORIZONS)
    lo = min(-0.5, m0 - 0.5)
    out = [[0.0] * N for _ in range(T)]
    for i in range(N):
        m = m0
        for t in range(T):
            k = i * T + t
            e = rho * Zg[k] + rq * Zm[k]
            m = clamp(m + (la - kl * m + (s0 + s1 * -m) * e if m < 0 else kap * (tm - m) + sp * e), lo, 0.7)
            out[t][i] = m
    return out


def _score(rows):
    """rows: [(p10, p50, p90, actual, pit)] → coverage, below, above, n, the median error and a PIT histogram."""
    n = len(rows)
    if not n:
        return None
    inside = sum(1 for lo, _, hi, a, _ in rows if lo <= a <= hi)
    below = sum(1 for lo, _, _, a, _ in rows if a < lo)
    pit = [0] * 10
    for *_, u in rows:
        pit[min(9, int(u * 10))] += 1
    return {'n': n, 'coverage': inside / n, 'below': below / n, 'above': (n - inside - below) / n,
            'median_error': quant([abs(a - m) for _, m, _, a, _ in rows], 0.5), 'pit': [c / n for c in pit]}


def complete_year(A, now_year):
    """The latest calendar year whose annual frames are complete: at least 90% as many companies with revenue as the year
    before (the current year, and a year whose reports are still coming in, are not)."""
    n = {}
    for a in A.values():
        for y, v in (a.get('rev') or {}).items():
            if fin(v):
                n[int(y)] = n.get(int(y), 0) + 1
    ys = [y for y in sorted(n) if y < now_year]
    for y in reversed(ys):
        if n.get(y - 1) and n[y] >= 0.9 * n[y - 1]:
            return y
    return ys[-1] if ys else None


def balances(frame, years):
    """{'cash': {cik: {year: v}}, 'debt': {…}} from the year-end instant frames (frame(concept, period) → {cik: v})."""
    out = {'cash': {}, 'debt': {}}
    for key, concept in (('cash', CASH_CONCEPT), ('debt', DEBT_CONCEPT)):
        for y in years:
            for cik, v in (frame(concept, f'CY{y}Q4I') or {}).items():
                v = v[0] if isinstance(v, list) else v
                if fin(v):
                    out[key].setdefault(str(cik), {})[y] = v
    return out


def reuse(prev, last_year, today):
    """Last month's result when it was made by this version from the same years and is under REFRESH_DAYS old."""
    try:
        made = dt.date.fromisoformat(str(prev.get('generated_at', ''))[:10])
    except ValueError:
        return None
    if prev.get('version') == VERSION and prev.get('last_year') == last_year and (today - made).days < REFRESH_DAYS:
        return prev
    return None


def run(A, last_year, bal=None, log=print):
    """The whole backtest from the annual frames A ({cik: {'rev': {y: v}, 'oi': {y: v}, 'ni': {y: v}}}), the last complete
    year and the year-end balances (balances())."""
    t0 = dt.datetime.now()
    bal = bal or {}
    U, Zg, Zm = MK.draws(N, max(HORIZONS))
    models = ('regime', 'schwartz_moon', 'naive')
    runs = [(m, 1.0) for m in models] + [('regime', f) for f in SD_SCALES if f != 1.0]
    rev_rows = {(m, f): {h: [] for h in HORIZONS} for m, f in runs}
    mar_rows = {h: [] for h in HORIZONS}
    prof_rows = {h: [] for h in HORIZONS}
    cash_rows = []
    origins, prev = [], None
    for Y in range(2013, last_year - max(HORIZONS) + 1, 2):
        O = origin_panel(A, Y, prev)
        if not O:
            continue
        prev = O['fit'] or prev
        origins.append({'year': Y, 'companies': len(O['hist']), 'method': O['stats']['method'],
                        'regimes': [round(v, 4) for v in O['stats']['g']]})
        elig = [c for c, ys in O['hist'].items() if fin((A[c].get('rev') or {}).get(Y)) and A[c]['rev'][Y] >= MIN_REV]
        for cik in _sample(elig, Y):
            a = A[cik]
            rev, oi = a.get('rev') or {}, a.get('oi') or {}
            r0 = rev[Y]
            O['_size'] = size_of(r0)
            ys = O['hist'][cik]
            for m, f in runs:
                paths = growth_paths(m, ys, O, U, Zg, f)
                for h in HORIZONS:
                    act = rev.get(Y + h)
                    if not (fin(act) and act > 0):
                        continue
                    la = math.log(act / r0)
                    xs = sorted(paths[h - 1])
                    rev_rows[(m, f)][h].append((quant(xs, 0.1), quant(xs, 0.5), quant(xs, 0.9), la, sum(1 for x in xs if x <= la) / N))
            m0 = oi.get(Y) / r0 if fin(oi.get(Y)) else None
            if fin(m0) and m0 < 0 and r0 >= MIN_SM_REV:
                mp = margin_paths(clamp(m0, -3.0, 0.0), O, Zg, Zm)
                for h in HORIZONS:
                    ra, oa = rev.get(Y + h), oi.get(Y + h)
                    if not (fin(ra) and ra > 0 and fin(oa)):
                        continue
                    ma = clamp(oa / ra, -3.0, 1.0)
                    xs = sorted(mp[h - 1])
                    mar_rows[h].append((quant(xs, 0.1), quant(xs, 0.5), quant(xs, 0.9), ma, sum(1 for x in xs if x <= ma) / N))
                    prof_rows[h].append((sum(1 for x in xs if x > 0) / N, ma > 0))
                cash = ((bal.get('cash') or {}).get(cik) or {}).get(Y)
                if fin(cash) and cash > 0 and Y + 3 <= last_year:
                    debt = ((bal.get('debt') or {}).get(cik) or {}).get(Y)
                    debt = debt if fin(debt) and debt > 0 else 0.0
                    p_out = cash_out_chance(r0, m0, cash, debt, ys, O, mp, U, Zg)
                    stopped = not any(fin((a.get(f) or {}).get(y)) for f in ('rev', 'oi', 'ni') for y in range(Y + 1, Y + 4))
                    cash_rows.append((p_out, stopped))
        log(f'backtest origin {Y}: {len(O["hist"])} companies, {min(len(elig), MAX_COS)} sampled')
    out = {'version': VERSION, 'last_year': last_year, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'origins': origins, 'paths': N, 'companies_per_origin': MAX_COS,
           'horizons': list(HORIZONS), 'revenue': {m: {str(h): _score(rev_rows[(m, 1.0)][h]) for h in HORIZONS} for m in models},
           'margin_loss_makers': {str(h): _score(mar_rows[h]) for h in HORIZONS},
           'profit_calibration': {str(h): calibration(prof_rows[h]) for h in HORIZONS},
           'cash_out': calibration(cash_rows) if len(cash_rows) >= MIN_CASH_ROWS else None,
           'cash_out_n': len(cash_rows), 'seconds': round((dt.datetime.now() - t0).total_seconds())}
    by_scale = {f: _score(rev_rows[('regime', f)][3]) for f in SD_SCALES}
    ok = {f: x for f, x in by_scale.items() if x}
    best = min(ok, key=lambda f: (abs(ok[f]['coverage'] - 0.8), f)) if ok else 1.0
    out['regime_sd_scale'] = best
    out['regime_scales'] = {str(f): {'coverage_3y': x['coverage'], 'below_3y': x['below'], 'above_3y': x['above']} for f, x in ok.items()}
    out['revenue']['regime_scaled'] = {str(h): _score(rev_rows[('regime', best)][h]) for h in HORIZONS}
    out['summary'] = summary(out)
    return out


def cash_out_chance(r0, m0, cash, debt, ys, O, mp, U, Zg):
    """A loss-maker's chance of running out of cash within three years from origin data: the Schwartz–Moon growth and
    margin paths, free cash flow ≈ operating income less 10% of any revenue increase for working capital (no tax while losing
    money; depreciation and capital spending are not in the history and are taken to cancel), 6% interest on debt."""
    st = O['stats']
    gs = [g for g, _ in ys]
    gbar = clamp(O['gbar'].get(O['_size'], MK.TERM_G), MK.TERM_G, 0.15)
    phi, sg = st['g_phi'], clamp(MK.shrunk_sd(gs, st['g_res_sd'])[0], 0.03, 0.40)
    g0 = clamp(gs[-1], -0.3, 1.0)
    T = max(HORIZONS)
    out = 0
    for i in range(N):
        g, r, x = g0, r0, cash
        for t in range(3):
            k = i * T + t
            g = clamp((g0 if t == 0 else gbar + phi * (g - gbar)) + sg * Zg[k], *MK.G_CLIP)
            prev, r = r, r * (1 + g)
            x += r * mp[t][i] - (r - prev) * 0.10 - 0.06 * debt
            if x < 0:
                out += 1
                break
    return out / N


def calibration(rows, edges=(0.0, 0.1, 0.3, 0.6, 1.0001)):
    """rows: [(predicted probability, happened)] → by bin: n, mean prediction, observed share; and the Brier score
    against the base rate's."""
    if not rows:
        return None
    bins = []
    for lo, hi in zip(edges, edges[1:]):
        b = [(p, y) for p, y in rows if lo <= p < hi]
        if b:
            bins.append({'from': lo, 'to': min(hi, 1.0), 'n': len(b), 'predicted': sum(p for p, _ in b) / len(b),
                         'observed': sum(1 for _, y in b if y) / len(b)})
    base = sum(1 for _, y in rows if y) / len(rows)
    brier = sum((p - (1 if y else 0)) ** 2 for p, y in rows) / len(rows)
    brier0 = sum((base - (1 if y else 0)) ** 2 for _, y in rows) / len(rows)
    return {'n': len(rows), 'bins': bins, 'base_rate': base, 'brier': brier, 'brier_base': brier0,
            'skill': 1 - brier / brier0 if brier0 > 0 else None}


def summary(out):
    """The few numbers each company page shows."""
    rv = out.get('revenue') or {}
    s = {}
    s['regime_sd_scale'] = out.get('regime_sd_scale', 1.0)
    for m in ('regime', 'regime_scaled', 'schwartz_moon', 'naive'):
        x = (rv.get(m) or {}).get('3') or {}
        if x:
            s[m] = {'coverage_3y': x['coverage'], 'below_3y': x['below'], 'above_3y': x['above'], 'n_3y': x['n']}
    mg = (out.get('margin_loss_makers') or {}).get('3') or {}
    if mg:
        s['margin'] = {'coverage_3y': mg['coverage'], 'n_3y': mg['n']}
    pc = (out.get('profit_calibration') or {}).get('3') or {}
    if pc:
        s['profit'] = {'skill_3y': pc.get('skill'), 'n_3y': pc.get('n')}
    if out.get('cash_out'):
        s['cash_out'] = {'skill': out['cash_out'].get('skill'), 'n': out['cash_out']['n'], 'base_rate': out['cash_out']['base_rate']}
    s['origins'] = [o['year'] for o in out.get('origins') or []]
    return s


def _verdict(c):
    return 'about right' if abs(c - 0.8) <= 0.05 else ('too narrow' if c < 0.8 else 'too wide')


def for_page(s, model):
    """The backtest line a company's regime ('regime') or Schwartz–Moon ('schwartz_moon') section shows: {'text', ...}."""
    if not s or not s.get(model):
        return None
    f = s.get('regime_sd_scale') or 1.0
    raw = s[model]
    if model == 'regime' and f != 1.0 and s.get('regime_scaled'):
        x = s['regime_scaled']
    else:
        x = raw
    o = s.get('origins') or []
    span = f'{o[0]}–{o[-1]}' if len(o) > 1 else (str(o[0]) if o else '')
    side = ('mostly on the downside' if x['below_3y'] > 1.5 * x['above_3y'] else 'mostly on the upside' if x['above_3y'] > 1.5 * x['below_3y']
            else 'on both sides')
    t = (f"Backtest (run in {span} on every filer's data as of then, {x['n_3y']:,} outcomes"
         + (", without analysts' consensus" if model == 'regime' else '') + f"): the 80% range of revenue three years out held "
         f"{x['coverage_3y'] * 100:.0f}% of what happened ({x['below_3y'] * 100:.0f}% fell below it, {x['above_3y'] * 100:.0f}% above) — "
         f"{_verdict(x['coverage_3y'])}" + (f', misses {side}' if _verdict(x['coverage_3y']) != 'about right' else '') + '.')
    if model == 'regime' and x is not raw:
        t += (f" That is with every regime's growth spread × {f:g}, the one number fitted on these outcomes (and used here): as the hidden Markov model "
              f"estimates them, the range held {raw['coverage_3y'] * 100:.0f}% ({raw['below_3y'] * 100:.0f}% below, {raw['above_3y'] * 100:.0f}% above) — "
              'a single year\'s regime spread understates how far revenue can drift over several.')
    out = {'model': model, 'sd_scale': f if model == 'regime' else None, 'coverage_3y': x['coverage_3y'], 'below_3y': x['below_3y'], 'above_3y': x['above_3y'], 'n_3y': x['n_3y'], 'origins': o}
    if model == 'schwartz_moon':
        mg, pf, co = s.get('margin') or {}, s.get('profit') or {}, s.get('cash_out')
        if mg:
            t += f" Loss-makers' operating margin three years out: inside its 80% range {mg['coverage_3y'] * 100:.0f}% of the time ({mg['n_3y']:,} outcomes)."
        if pf and fin(pf.get('skill_3y')):
            t += (f" The chance of an operating profit within three years scores {pf['skill_3y']:+.2f} against simply using the share that got there "
                  '(Brier skill: above 0 is better than that base rate).')
        t += (f" Cash running out within three years: Brier skill {co['skill']:+.2f} against the share that stopped filing ({co['n']:,} loss-makers; stopping "
              'includes acquisitions, so it overstates failures).' if co and fin(co.get('skill')) else
              ' Running out of cash is not scored yet: the year-end cash balances before 2025 are still being collected.')
        out.update({'margin': mg or None, 'profit': pf or None, 'cash_out': co})
    out['text'] = t
    return out


PANEL_KEYS = ('loss_kappa', 'loss_a', 'loss_sd0', 'loss_sd1', 'prof_sd', 'loss_n', 'g_phi', 'g_a', 'g_res_sd', 'g_pairs', 'rho_gm', 'rho_n',
              'kappa', 'kappa_n', 'm_sd')


def panel_now(A, Y):
    """The Schwartz–Moon section's panel statistics — growth persistence and surprise, loss-makers' margin regression,
    the profitable pull-back, the shock correlation — as of the last complete year Y, built exactly as at each backtest
    origin: every SEC filer with year Y on file and its run of years with $10M+ of revenue (app/markov.py _stats). Not the
    covered companies' panel: those are today's listed survivors, whose past losses all ended well enough to still be
    here (their loss-makers' margins improve about twice as fast)."""
    hist = []
    for a in A.values():
        ys, last = MK.annual_years(cut(a, Y))
        if len(ys) >= 2 and last == Y:
            hist.append(ys)
    if len(hist) < 60:
        return None
    st = MK._stats(hist, None, None)
    out = {k: st[k] for k in PANEL_KEYS if k in st}
    out.update({'firms': len(hist), 'year': Y,
                'source': f'every SEC filer with {Y} on file ({len(hist):,} companies, annual frames since 2010) — the panel the backtest checks'})
    return out
