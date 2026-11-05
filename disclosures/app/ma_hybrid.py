"""Moving averages+ (each company page's "Moving averages+" view and Rotation → Chart → Moving averages+;
rotation-history.yml): the usual moving averages of the price with the company's earnings and its own guidance mixed in,
weighted — and tested walk-forward against the moving averages alone before anything is shown.

Lines (weekly closes, split-adjusted; the 10- and 40-week averages are the weekly forms of the 50- and 200-day ones)
  MA10, MA40      simple averages of the last 10 and 40 weekly closes.
  earnings line   trailing four quarters' diluted EPS × the company's own median P/E of the last five years (at least
                  three years of it; positive earnings only) — the price the company's earnings would fetch at its usual
                  multiple (the FAST Graphs "normal P/E" line). Point in time: a quarter counts from the first weekly close
                  after its first filing (SEC companyfacts, as first filed: data branch eps-fundamental), every per-share
                  figure restated to the price file's split basis with the splits after its filing.
  guidance        the company's latest earnings release in the last 13 weeks that raised (+1), lowered or withdrew (−1)
                  or kept (0) its guidance (the hub's guidance history, cache/guidance: releases since 2023, most since
                  2024, only companies that guide).
  hybrid line     H = MA40^(1−w) × earnings line^w × (1 + g · guidance): the 40-week average blended with the earnings
                  line (weight w) and moved by the guidance (g). The page lets the viewer pick w and g; every pair on the
                  grid w ∈ {0, ¼, ½, ¾, 1} × g ∈ {0, 5%, 10%} is tested, and the pair picked each year from the years
                  before (and whether "above the line" or "below it" paid) is scored out of sample.

Models (the weights learnt rather than chosen): a ridge regression (λ = 30 on inputs ranked within the week) of the
h-week return against SPY less the panel's average that week, refitted every year on the weeks whose outcome was known
by 1 January, from 2010:
  moving averages            price vs MA40, MA10 vs MA40, price vs its 4-week average
  + fundamentals             the latest quarter's earnings surprise (EPS less the same quarter a year before, over the
                             spread of the last eight such changes) and sales growth (each for 13 weeks after its filing),
                             P/E against its own five-year median, earnings yield
  + guidance                 the guidance direction above
Scores from 2016 (2016–2018 and 2019 on also apart): the weekly rank correlation with the outcome (every week; the t
counts weeks ÷ h as independent), the best − worst fifth and the above − below line baskets in simple returns against SPY
(what an equal-weighted basket earns) after trading costs (one way by weekly dollar volume, as app/rrg_hybrid.py; no
borrow fee), each period's own rows. The classic rules — above the 40-week average, the 10-week above the 40-week — are
scored the same way.

Also, descriptive: what followed each kind of guidance release (raised, kept, lowered …) and each MD&A by its tone of
voice over 4 and 13 weeks, against the average company that week.

Daily averages (each company's daily chart, any N-day average): research-paths' daily bars (cache/ohlc: Yahoo's daily
closes, split-adjusted, refreshed each day after the close; most companies since late 2016). Tested two ways, price
above its N-day average − below and the crosses (shorter above longer − below), in simple returns after costs as above:
  weekly form, 2016 on    every company: the N-day average as the N/5-week average of weekly closes (none for 5 days)
  exact, daily closes     the companies with daily bars: each Friday's last close against its N-day averages, from the
                          first Friday with 250 trading days behind it (late 2017)
Macro (app/macro_history.py's macro.json, every reading as known that Friday — the weekly block from 2009, the
month-end values before it):
  funds                   SPY, QQQ, DIA, MDY, IWM since 1996: hold; hold while above the 40-week average, else cash at
                          the fed funds rate; and out only when below it and unemployment is above its 12-month average
                          (the growth-trend rule, Philosophical Economics, 2016) or the Sahm rule is on (the 3-month
                          unemployment rate 0.5 above its 12-month low; Sahm, 2019). Decided at each Friday's close, held
                          the next week, 5 bp a switch; 1996–2015 and 2016 on apart (the rules were published in 2016/2019).
  companies               above − below the 40-week average in each third of twelve readings (VIX, credit spread …),
                          each third from the reading's own past only (72 comparisons: a few |t| > 2 are expected by
                          chance); and a model letting the trend's weight move with five of them (the ranked trend × the
                          reading's z-score on its own past since 1995), against the averages alone — and, as a check on
                          how much that rests on what counts as normal, the same with the readings scaled on 2009 on only.
                          Recorded and frozen as models of their own; the line itself has no macro in it.

Recorded, not yet in the line (their history is too short to test it): the Fair value page's DCF value and its Monte
Carlo range, the chance it puts the value above the price, the base-rate chance of the growth the price implies
(research-valuation index.json, this week only — its own walk-forward since 2022 is on the Fair value page), and the
latest MD&A's tone. Each company's card shows them; the ledger freezes them every week, so their worth can be scored as
the record grows.

Each closed week the inputs and the models' scores for the 800 most-traded companies are frozen (ledger/ma-hybrid.json)
and scored when 13 and 26 weeks have passed. Today's companies only (delisted names are missing). History and models, not
investment advice.

  python app/ma_hybrid.py --public hist/public --fundamentals data/eps-fundamental \
      --guidance disclosures/docs/data/cache/guidance --bars research-paths/cache/ohlc --ledger hist/ledger/ma-hybrid.json
  python app/ma_hybrid.py --public hist/public --bars research-paths/cache/ohlc --bars-sha <commit> --daily
      (between weekly builds, once per research-paths commit: only the daily files and the rows' daily numbers)
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

import forecast_book as FB
import rrg_hybrid as HY
import transition_rrg as TR

VERSION = 2
HORIZONS = (13, 26)
FIT_FROM = 2010               # the first year of training data (first-filed EPS starts in 2009)
FIRST_OOS = 2013              # the first year forecast out of sample
TEST_FROM = 2016              # scores are reported from here …
SPLIT_AT = 2019               # … and for 2016–2018 and 2019 on apart (the moving averages' trend paid only in the second)
RIDGE = 30.0
WINSOR = (0.005, 0.995)
MA_SHORT, MA_LONG, MA_REV = 10, 40, 4
PE_WINDOW, PE_MIN = 260, 156  # the own median P/E: five years of weekly P/E, at least three
GUIDE_WEEKS = 13
DRIFT_WEEKS = 13              # an earnings surprise or sales growth counts for 13 weeks after its filing
STALE_DAYS = 200              # trailing EPS older than this (since its last quarter's end) is dropped
WS = (0.0, 0.25, 0.5, 0.75, 1.0)
GS = (0.0, 0.05, 0.10)
DEFAULT = (0.5, 0.05)         # the page's starting weights: half the earnings line, 5% for a guidance change
MIN_NAMES, MIN_SIDE = 50, 10
SERIES_WEEKS = 260            # weeks of each company's lines in its own file
LEDGER_MAX_LINES = 800
LAB = {'raised': 1, 'lowered': -1, 'withdrawn': -1, 'reaffirmed': 0, 'updated': 0, 'initiated': 0, 'narrowed': 0, 'mixed': 0,
       'widened': 0}
VAL_FIELDS = ('dcf_value', 'mc_p10', 'mc_p90', 'mc_p_above', 'p_implied', 'implied_growth', 'peer_pe_mid', 'target_mean', 'comb_ret',
              'graham_value', 'kind')      # the Fair value page's numbers (research-valuation index.json), this week only
MDNA_MIN = 3                  # an MD&A counts when at least 3 forward-looking statements were read from it
TONE_BINS = ((-1.01, 0.0, 'negative (below 0)'), (0.0, 0.2, 'neutral (0 to 0.2)'), (0.2, 1.01, 'positive (above 0.2)'))
NDAYS = (5, 10, 20, 30, 50, 60, 120, 200, 250)    # the N-day averages tested (and offered on the daily chart)
CROSSES = ((5, 20), (10, 60), (20, 60), (50, 200), (60, 250))
DAILY_ROWS = 1000             # daily closes in each company's daily file (≈ 4 years: a 250-day average over 3 of them)
DAILY_CLOSE_UTC = (21, 15)    # a cache row fetched before 21:15 UTC on its own day is not that day's close yet
DAILY_GAPS = (20, 50, 200)    # the rows' distances to these daily averages (the hub's lists)
CROSS_RECENT = 10             # trading days: a 50/200-day cross this recent is listed in the hub
MACRO_READINGS = ('vix', 'credit', 'dcredit', 'curve', 'dy10', 'claims', 'sahm', 'usd13', 'oil13', 'nfci', 'cpi', 'ff')
MACRO_MODEL = ('vix', 'credit', 'dcredit', 'claims', 'curve')   # the readings the trend's weight may move with
MACRO_MIN_WEEKS = 156         # a reading's thirds and z-score need three years of its own past
INDEX_FUNDS = ('SPY', 'QQQ', 'DIA', 'MDY', 'IWM')
INDEX_FROM, INDEX_SPLIT = 1996, 2016
SAHM_ON = 0.5
SWITCH_BP = HY.COST_TIERS[0][1]                    # a switch in an index fund: the most liquid tier, one way
INDEX_RULES = {'hold': 'Hold the fund', 'above40': 'Hold it while above its 40-week average, else cash',
               'trend_unemployment': '40-week average, out only if unemployment is also above its 12-month average',
               'trend_sahm': '40-week average, out only if the Sahm rule is also on'}
MODELS = {'ma': ['tr40', 'tr10_40', 'rev4'],
          'ma_fund': ['tr40', 'tr10_40', 'rev4', 'sue', 'srg', 'val', 'ey'],
          'hybrid': ['tr40', 'tr10_40', 'rev4', 'sue', 'srg', 'val', 'ey', 'guid'],
          'ma_macro': ['tr40', 'tr10_40', 'rev4'] + [f'tr40x{k}' for k in MACRO_MODEL] + [f'tr10x{k}' for k in MACRO_MODEL],
          'ma_macro_09': ['tr40', 'tr10_40', 'rev4'] + [f'tr40x{k}_09' for k in MACRO_MODEL] + [f'tr10x{k}_09' for k in MACRO_MODEL]}
MODEL_NAMES = {'ma': 'Moving averages alone', 'ma_fund': 'Moving averages + fundamentals',
               'hybrid': 'Moving averages + fundamentals + guidance', 'ma_macro': 'Moving averages × macro',
               'ma_macro_09': 'Moving averages × macro, the readings scaled on 2009 on only (a check)'}
FEATURE_NAMES = {'tr40': 'Price vs its 40-week average', 'tr10_40': '10-week average vs the 40-week', 'rev4': 'Price vs its 4-week average',
                 'sue': 'Earnings surprise (latest quarter)', 'srg': 'Sales growth (latest quarter, y/y)',
                 'val': 'P/E vs its own 5-year median', 'ey': 'Earnings yield', 'guid': 'Guidance raised / lowered'}
MACRO_SHORT = {'vix': 'VIX', 'credit': 'Credit spread', 'dcredit': 'Credit spread, 13-week change', 'claims': 'Jobless claims, y/y',
               'curve': 'Yield curve'}
FEATURE_NAMES.update({f'tr40x{k}': f'Price vs its 40-week average × {v}' for k, v in MACRO_SHORT.items()})
FEATURE_NAMES.update({f'tr10x{k}': f'10-week vs 40-week average × {v}' for k, v in MACRO_SHORT.items()})
FEATURE_NAMES.update({f'{a}x{k}_09': f'{FEATURE_NAMES[f"{a}x{k}"]} (scaled on 2009 on)' for a in ('tr40', 'tr10') for k in MACRO_SHORT})
fin, r_, years_of = HY.fin, HY.r_, HY.years_of


def sig(v, n=4):
    """A price-like value to n significant figures (None when not finite)."""
    if not fin(v) or v == 0:
        return None if not fin(v) else 0.0
    return float(f'{v:.{n}g}')


# ------------------------------------------------------------------ data
def grid(public):
    D = json.loads((Path(public) / 'rrg.json').read_text(encoding='utf-8'))
    g0 = np.datetime64(D['start'])
    W = int((np.datetime64(D['weeks']) - g0).astype(int) // 7) + 1
    return D, g0, W, g0 + 7 * np.arange(W)


def weekly_known(dnum, events, stale_days=STALE_DAYS):
    """events [(known day, period end day, value)] → per week the latest period's value known before that Friday."""
    out = np.full(len(dnum), np.nan)
    if not events:
        return out
    events = sorted(events)
    j, best_end, best = 0, None, np.nan
    for t in range(len(dnum)):
        while j < len(events) and events[j][0] < dnum[t]:
            if best_end is None or events[j][1] >= best_end:
                best_end, best = events[j][1], events[j][2]
            j += 1
        if best_end is not None and dnum[t] - best_end <= stale_days:
            out[t] = best
    return out


def for_weeks(dnum, events, weeks):
    """events [(known day, value)] → each value for `weeks` weeks from the first Friday after it is known."""
    out = np.full(len(dnum), np.nan)
    for day, v in sorted(events):
        k0 = int(np.searchsorted(dnum, day, side='right'))
        out[k0:k0 + weeks] = v
    return out


def day(s):
    return int(np.datetime64(str(s)[:10]).astype('datetime64[D]').astype(np.int64))


def company_fundamentals(quarters, splits, dnum):
    """First-filed quarters → weekly trailing EPS (split basis of the prices), and the latest quarter's earnings
    surprise and sales growth for the 13 weeks after its filing."""
    def basis(filed):
        f = 1.0
        for sd, r in splits:
            if sd > filed:
                f *= r
        return f
    q = []
    for qq in quarters or []:
        F = qq.get('fields') or {}
        try:
            rec = {'end': day(qq['end'])}
        except (KeyError, ValueError):
            continue
        e, rv, sh = F.get('eps'), F.get('revenue'), F.get('diluted_shares')
        if e and fin(e.get('val')) and e.get('filed'):
            fd = day(e['filed'])
            rec['eps'] = (fd, e['val'] / basis(fd))
        if rv and sh and fin(rv.get('val')) and fin(sh.get('val')) and sh['val'] > 0 and rv.get('filed') and sh.get('filed'):
            fd = max(day(rv['filed']), day(sh['filed']))
            rec['sps'] = (fd, rv['val'] / sh['val'] / basis(fd))
        q.append(rec)
    q.sort(key=lambda r: r['end'])
    ttm, sue, srg = [], [], []
    for i in range(len(q)):
        if i >= 3:
            four = q[i - 3:i + 1]
            if 250 <= four[-1]['end'] - four[0]['end'] <= 300 and all('eps' in r for r in four):
                ttm.append((max(r['eps'][0] for r in four), four[-1]['end'], sum(r['eps'][1] for r in four)))
        if i >= 4 and 330 <= q[i]['end'] - q[i - 4]['end'] <= 400:
            a, b = q[i], q[i - 4]
            if 'eps' in a and 'eps' in b:
                ch = [q[j]['eps'][1] - q[j - 4]['eps'][1] for j in range(max(4, i - 8), i) if 'eps' in q[j] and 'eps' in q[j - 4]]
                if len(ch) >= 4:
                    sd = float(np.std(ch, ddof=1))
                    if sd > 0:
                        sue.append((a['eps'][0], (a['eps'][1] - b['eps'][1]) / sd))
            if 'sps' in a and 'sps' in b and a['sps'][1] > 0 and b['sps'][1] > 0:
                srg.append((a['sps'][0], math.log(a['sps'][1] / b['sps'][1])))
    return weekly_known(dnum, ttm), for_weeks(dnum, sue, DRIFT_WEEKS), for_weeks(dnum, srg, DRIFT_WEEKS)


def company_guidance(path, dnum):
    """(weekly direction for 13 weeks after each labelled release, [(filed, label)] newest last)."""
    if not path or not Path(path).exists():
        return np.full(len(dnum), np.nan), []
    try:
        rel = json.loads(gzip.open(path).read()).get('releases') or []
    except (OSError, ValueError):
        return np.full(len(dnum), np.nan), []
    ev = sorted((day(r['filed']), r['label']) for r in rel if r.get('label') in LAB and r.get('filed'))
    return for_weeks(dnum, [(d, LAB[l]) for d, l in ev], GUIDE_WEEKS), ev


def load(public, fundamentals, guidance=None):
    """The weekly grid, SPY and every company with weekly prices (rotation-history t/<T>.json) and first-filed
    quarters (eps-fundamental/<cik>.json, its ticker): closes (total return), split-adjusted closes, volume, trailing EPS,
    earnings surprise, sales growth, guidance."""
    public = Path(public)
    D, g0, W, days = grid(public)
    dnum = days.astype('datetime64[D]').astype(np.int64)

    def place(start, arr, scale=1.0):
        a = np.full(W, np.nan)
        o = int((np.datetime64(start) - g0).astype(int) // 7)
        v = np.array([np.nan if x is None else x * scale for x in arr], float)
        if o < W:
            a[max(0, o):o + len(v)] = v[max(0, -o):W - o]
        return a
    spy = place(D['bench']['start'], D['bench']['c'])
    names = D.get('tickers') or {}
    fund = {}
    for f in sorted(Path(fundamentals).glob('*.json')):
        try:
            x = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        t = x.get('ticker')
        if t and t in names and t not in fund:
            fund[t] = x
    rows = {k: [] for k in ('C', 'P', 'V', 'EPS', 'SUE', 'SRG', 'G')}
    ids, meta, events = [], {}, []
    for t in sorted(fund):
        p = public / 't' / f'{t}.json'
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        if not d.get('p') or sum(1 for x in d['c'] if x is not None) < MA_LONG + 13:
            continue
        s0 = np.datetime64(d['start'], 'D')
        splits = [(int((s0 + np.timedelta64(7 * int(k), 'D')).astype(np.int64)), float(r)) for k, r in (d.get('sp') or []) if r and r > 0]
        EPS, SUE, SRG = company_fundamentals(fund[t].get('quarters'), splits, dnum)
        cik = fund[t].get('cik')
        G, gev = company_guidance(Path(guidance) / f'{cik}.json.gz' if guidance and cik else None, dnum)
        for d_, lab in gev:                                 # each release: the first weekly close after it
            events.append((len(ids), int(np.searchsorted(dnum, d_, side='right')), lab))
        ids.append(t)
        meta[t] = {'cik': cik, 'name': (names.get(t) or {}).get('n') or t, 'sector': (names.get(t) or {}).get('s'),
                   'guidance': [(str(np.datetime64(int(a), 'D')), b) for a, b in gev[-20:]]}
        for k, a in (('C', place(d['start'], d['c'])), ('P', place(d['start'], d['p'])), ('V', place(d['start'], d.get('v') or [None] * len(d['c']), 1000.0)),
                     ('EPS', EPS), ('SUE', SUE), ('SRG', SRG), ('G', G)):
            rows[k].append(a.astype(np.float32))
    A = {k: (np.array(v, dtype=np.float64) if v else np.zeros((0, W))) for k, v in rows.items()}
    return {'days': days, 'spy': spy, 'ids': ids, 'meta': meta, 'events': events, **A}


def load_extras(A, valuation=None, outlook=None):
    """This week's Fair value numbers per company (no history: the valuation page keeps monthly snapshots only since
    October 2026, its own walk-forward since 2022), and every MD&A's tone of voice as of its filing (pipeline/outlook.py:
    the forward-looking statements read from Item 2 / Item 7, positive − negative over all, on file mostly from 2026)."""
    val, mdna_now, events = {}, {}, []
    if valuation and Path(valuation).exists():
        try:
            d = json.loads(Path(valuation).read_text(encoding='utf-8'))
            F = d.get('fields') or []
            ix = {f: k for k, f in enumerate(F)}
            if 'ticker' in ix:
                for r in d.get('rows') or []:
                    val[r[ix['ticker']]] = {k: r[ix[k]] for k in VAL_FIELDS if k in ix}
        except (OSError, ValueError, TypeError, IndexError):
            val = {}
    if outlook and Path(outlook).exists():
        dnum = A['days'].astype('datetime64[D]').astype(np.int64)
        by_cik = {A['meta'][t]['cik']: (i, t) for i, t in enumerate(A['ids']) if A['meta'][t].get('cik')}
        for f in Path(outlook).glob('*.json'):
            try:
                x = json.loads(f.read_text(encoding='utf-8'))
                cik = int(x.get('cik') or f.stem)
            except (OSError, ValueError, TypeError):
                continue
            if cik not in by_cik:
                continue
            i, t = by_cik[cik]
            docs = sorted([d for d in x.get('docs') or [] if d.get('kind') == 'mdna' and d.get('filed') and fin((d.get('counts') or {}).get('tone'))
                           and (d.get('counts') or {}).get('n', 0) >= MDNA_MIN], key=lambda d: d['filed'])
            for d in docs:
                events.append((i, int(np.searchsorted(dnum, day(d['filed']), side='right')), float(d['counts']['tone'])))
            if docs:
                c = docs[-1]['counts']
                mdna_now[t] = {'filed': docs[-1]['filed'][:10], 'form': docs[-1].get('form'), 'tone': r_(c.get('tone'), 3), 'n': c.get('n'),
                               'positive': c.get('positive'), 'negative': c.get('negative'), 'hedged': c.get('hedged')}
    return val, mdna_now, events


def mdna_events(days, A, ok, events):
    """What followed an MD&A by its tone (descriptive, the few seasons on file): the simple return against SPY over 4
    and 13 weeks from the first weekly close after the filing, less the average company's that week."""
    rel = np.diff(np.log(A['C']), axis=1, prepend=np.nan) - np.diff(np.log(A['spy']), prepend=np.nan)[None]
    out = {}
    for h in (4, 13):
        Ys = np.expm1(HY.fwd_sum(rel, h))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            avg = np.nanmean(np.where(ok, Ys, np.nan), 0)
        out[str(h)] = {}
        for lo, hi, lab in TONE_BINS:
            v = [Ys[i, k0] - avg[k0] for i, k0, tone in events
                 if lo <= tone < hi and 0 <= k0 < Ys.shape[1] and ok[i, k0] and fin(Ys[i, k0]) and fin(avg[k0])]
            if len(v) >= 10:
                a = np.array(v)
                out[str(h)][lab] = {'n': int(len(a)), 'mean': r_(a.mean()), 't': r_(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))), 2),
                                    'beat': r_((a > 0).mean(), 3)}
    ks = sorted({min(k0, len(days) - 1) for _, k0, _ in events})
    out['years'] = [str(days[ks[0]])[:4], str(days[ks[-1]])[:4]] if ks else None
    out['filings'] = len(events)
    return out


def guidance_events(days, A, ok):
    """What followed each kind of guidance release (descriptive): the simple return against SPY over 4 and 13 weeks from
    the first weekly close after the release, less the average company's that week; t over the releases."""
    rel = np.diff(np.log(A['C']), axis=1, prepend=np.nan) - np.diff(np.log(A['spy']), prepend=np.nan)[None]
    out = {}
    for h in (4, 13):
        Ys = np.expm1(HY.fwd_sum(rel, h))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            avg = np.nanmean(np.where(ok, Ys, np.nan), 0)
        by = {}
        for i, k0, lab in A['events']:
            if 0 <= k0 < Ys.shape[1] and ok[i, k0] and fin(Ys[i, k0]) and fin(avg[k0]):
                by.setdefault(lab, []).append(Ys[i, k0] - avg[k0])
        out[str(h)] = {}
        for lab, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
            a = np.array(v)
            if len(a) >= 10:
                out[str(h)][lab] = {'n': int(len(a)), 'mean': r_(a.mean()), 't': r_(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))), 2),
                                    'beat': r_((a > 0).mean(), 3)}
    yrs = sorted({str(days[min(k0, len(days) - 1)])[:4] for _, k0, _ in A['events']})
    out['years'] = [yrs[0], yrs[-1]] if yrs else None
    return out


# ------------------------------------------------------------------ daily closes
def symbol(t):
    """research-paths' file name for a ticker (app/rotation_history.symbol: class shares with '-')."""
    return (t or '').strip().upper().replace('/', '-').replace('.', '-').rstrip('*')


def read_gz(p):
    try:
        return json.loads(gzip.open(p).read())
    except (OSError, ValueError, EOFError):
        return None


def load_daily(bars, ids):
    """Each company's daily closes from research-paths' bars (cache/ohlc/<T>.json.gz, joined to <T>.base.json.gz when it
    has one — app/paths.py: Yahoo's daily chart, split-adjusted, restated after every split, refreshed each day after the
    close) → {ticker: (day numbers, closes)}. A last bar fetched before its own day's close (21:15 UTC) is dropped."""
    out = {}
    if not bars or not Path(bars).is_dir():
        return out
    for t in ids:
        s = symbol(t)
        rec = read_gz(Path(bars) / f'{s}.json.gz') if s else None
        if not rec:
            continue
        ts, cs = list(rec.get('t') or []), list(rec.get('c') or [])
        if rec.get('base'):
            b = read_gz(Path(bars) / f'{s}.base.json.gz')
            if not b:                                   # the recent part alone would be a short, misleading history
                continue
            ts, cs = list(b.get('t') or []) + ts, list(b.get('c') or []) + cs
        by = {d_[:10]: float(c) for d_, c in zip(ts, cs) if isinstance(d_, str) and fin(c) and c > 0}
        ds = sorted(by)
        try:
            f = dt.datetime.fromisoformat(str(rec.get('fetched_at')).replace('Z', '+00:00')).astimezone(dt.timezone.utc) if rec.get('fetched_at') else None
        except ValueError:
            f = None
        if ds and f and ds[-1] == f.date().isoformat() and (f.hour, f.minute) < DAILY_CLOSE_UTC:
            ds = ds[:-1]
        if len(ds) >= 2:
            out[t] = (np.array([day(x) for x in ds], np.int64), np.array([by[x] for x in ds]))
    return out


def sma(x, n):
    """Simple average of the last n values (NaN for the first n − 1)."""
    out = np.full(len(x), np.nan)
    if n >= 1 and len(x) >= n:
        c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def daily_on_grid(daily, ids, days):
    """The daily signals on the weekly grid: each Friday, the company's last close of that week (no later day) against its
    N-day averages ('above:N', log distance) and each cross ('cross:a/b', log of the a-day average over the b-day)."""
    dnum = days.astype('datetime64[D]').astype(np.int64)
    L, W = len(ids), len(days)
    out = {f'above:{n}': np.full((L, W), np.nan) for n in NDAYS}
    out.update({f'cross:{a}/{b}': np.full((L, W), np.nan) for a, b in CROSSES})
    lens = sorted(set(NDAYS) | {a for a, _ in CROSSES} | {b for _, b in CROSSES})
    for i, t in enumerate(ids):
        if t not in daily:
            continue
        dn, cl = daily[t]
        j = np.searchsorted(dn, dnum, side='right') - 1
        jj = np.clip(j, 0, None)
        inweek = (j >= 0) & (dnum - dn[jj] < 7)
        lc = np.log(cl)
        with np.errstate(divide='ignore', invalid='ignore'):
            lm = {n: np.log(sma(cl, n)) for n in lens}
        for n in NDAYS:
            out[f'above:{n}'][i] = np.where(inweek, lc[jj] - lm[n][jj], np.nan)
        for a, b in CROSSES:
            out[f'cross:{a}/{b}'][i] = np.where(inweek, lm[a][jj] - lm[b][jj], np.nan)
    return out


def daily_now(dn, cl):
    """A company's latest daily close against its 20-, 50- and 200-day averages, whether the 50-day is above the 200-day,
    and the latest cross of the two in the file [date, +1 golden / −1 death, trading days ago]."""
    out = {'d_asof': str(np.datetime64(int(dn[-1]), 'D')), 'd_close': sig(cl[-1], 5), 'x50_200': None, 'up50_200': None}
    for n in DAILY_GAPS:
        out[f'd{n}'] = r_(math.log(cl[-1] / cl[-n:].mean()), 4) if len(cl) >= n else None
    s = np.sign(sma(cl, 50) - sma(cl, 200))
    idx = np.where(np.isfinite(s) & (s != 0))[0]
    if len(idx):
        out['up50_200'] = int(s[idx[-1]])
        ch = np.where(s[idx][1:] != s[idx][:-1])[0]
        if len(ch):
            k = int(idx[ch[-1] + 1])
            out['x50_200'] = [str(np.datetime64(int(dn[k]), 'D')), int(s[k]), int(len(cl) - 1 - k)]
    return out


def daily_file(t, name, dn, cl):
    """A company's daily closes for its chart: the last DAILY_ROWS, as a start date, the day gaps and the closes."""
    k0 = max(0, len(dn) - DAILY_ROWS)
    dn, cl = dn[k0:], cl[k0:]
    return {'id': t, 'name': name, 'start': str(np.datetime64(int(dn[0]), 'D')), 'asof': str(np.datetime64(int(dn[-1]), 'D')),
            'gap': [int(v) for v in np.diff(dn)], 'p': [sig(v, 5) for v in cl],
            'source': "Yahoo's daily closes, split-adjusted (research-paths' daily bars)"}


def write_daily(pub, daily, names):
    """public/ma-daily/<T>.json for every company listed this week; a file no longer listed goes."""
    folder = Path(pub) / 'ma-daily'
    folder.mkdir(parents=True, exist_ok=True)
    keep = set()
    for t, name in names.items():
        if t in daily:
            (folder / f'{t}.json').write_text(json.dumps(clean(daily_file(t, name, *daily[t])), separators=(',', ':')), encoding='utf-8')
            keep.add(f'{t}.json')
    for f in folder.glob('*.json'):
        if f.name not in keep:
            f.unlink()
    return len(keep)


# ------------------------------------------------------------------ macro
def month_end_day(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return day(dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))


def macro_load(public, days):
    """The macro file's readings on the weekly grid, each as known that Friday: its weekly block (from 2009) and, before
    it, its monthly block (month-end values as known then, app/macro_history.py) from the first Friday after the month end.
    → {'x': {key: array}, 'labels': {key: (label, unit)}, 'generated_at'} or None without the file."""
    p = Path(public) / 'macro.json'
    if not p.exists():
        return None
    try:
        M = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    W = len(days)
    dnum = days.astype('datetime64[D]').astype(np.int64)
    wk, mo = M.get('weekly') or {}, M.get('monthly') or {}
    me = np.array([month_end_day(m) for m in mo.get('months') or []], np.int64)
    j = np.searchsorted(me, dnum, side='left') - 1 if len(me) else np.full(W, -1)
    jj = np.clip(j, 0, None)
    use_m = (j >= 0) & (dnum - me[jj] <= 45) if len(me) else np.zeros(W, bool)
    g0 = None
    if wk.get('start'):                                   # the weekly block starts on a grid Friday: placed by its date
        k = int(np.searchsorted(days, np.datetime64(wk['start'])))
        g0 = k if k < W and str(days[k]) == wk['start'] else None
    x = {}
    for k in set(wk.get('data') or {}) | set(mo.get('data') or {}):
        a = np.full(W, np.nan)
        mv = (mo.get('data') or {}).get(k)
        if mv is not None and len(me) and len(mv) == len(me):
            v = np.array([np.nan if q is None else q for q in mv], float)
            a = np.where(use_m, v[jj], np.nan)
        wv = (wk.get('data') or {}).get(k)
        if wv is not None and g0 is not None:
            v = np.array([np.nan if q is None else q for q in wv], float)[:W - g0]
            a[g0:g0 + len(v)] = np.where(np.isfinite(v), v, a[g0:g0 + len(v)])
        x[k] = a
    labels = {f['key']: (f.get('label') or f['key'], f.get('unit') or '') for f in M.get('features') or [] if f.get('key')}
    return {'x': x, 'labels': labels, 'generated_at': M.get('generated_at'), 'weekly_from': g0}


def expanding(x, min_n=MACRO_MIN_WEEKS):
    """Each week: x's third (0 low / 1 middle / 2 high, −1 unknown), the two cut points and its z-score (clipped ±3), all
    against x's own earlier values only (at least min_n of them) — point in time."""
    n = len(x)
    third, cut, z = np.full(n, -1), np.full((n, 2), np.nan), np.full(n, np.nan)
    srt, s1, s2 = [], 0.0, 0.0

    def q(p):
        pos = p * (len(srt) - 1)
        lo = int(math.floor(pos))
        return srt[lo] + (pos - lo) * (srt[min(lo + 1, len(srt) - 1)] - srt[lo])
    for t in range(n):
        v = x[t]
        if not math.isfinite(v):
            continue
        k = len(srt)
        if k >= min_n:
            c1, c2 = q(1 / 3), q(2 / 3)
            cut[t] = (c1, c2)
            third[t] = 0 if v <= c1 else (1 if v <= c2 else 2)
            m = s1 / k
            sd = math.sqrt(max(s2 / k - m * m, 0.0))
            z[t] = min(3.0, max(-3.0, (v - m) / sd)) if sd > 0 else 0.0
        bisect.insort(srt, float(v))
        s1 += v
        s2 += v * v
    return third, cut, z


def trailing(a, k, how):
    """The mean or minimum of the last k values (all finite), per position of a 1-D array."""
    out = np.full(len(a), np.nan)
    if len(a) >= k:
        w = swv(a, k)
        ok_ = np.isfinite(w).all(1)
        with np.errstate(invalid='ignore'):
            out[k - 1:] = np.where(ok_, w.mean(1) if how == 'mean' else w.min(1), np.nan)
    return out


def macro_flags(mac):
    """Unemployment above its 12-month average (52 weeks of the rate as known) and the Sahm rule (its 3-month average 0.5
    or more above that average's low of the last 12 months), each as known that Friday."""
    un = mac['x'].get('unrate')
    if un is None:
        return None
    un12 = trailing(un, 52, 'mean')
    s3 = trailing(un, 13, 'mean')
    sahm = s3 - trailing(s3, 53, 'min')
    return {'unrate': un, 'unrate12': un12, 'unemp_up': np.where(np.isfinite(un12), un > un12, False),
            'sahm3': sahm, 'sahm_on': np.where(np.isfinite(sahm), sahm >= SAHM_ON - 1e-9, False),
            'known': np.isfinite(un12) & np.isfinite(sahm)}


# ------------------------------------------------------------------ lines and inputs
def moving(X, k):
    """Simple average of the last k weeks (NaN unless all k are there)."""
    if X.shape[1] < k:
        return np.full(X.shape, np.nan)
    w = swv(np.concatenate([np.full((X.shape[0], k - 1), np.nan), X], 1), k, axis=1)
    with np.errstate(invalid='ignore'):
        return np.where(np.isfinite(w).all(2), w.mean(2), np.nan)


def own_median_log(X, win=PE_WINDOW, need=PE_MIN):
    """Each week: the median of log X over the last `win` weeks (finite values), when at least `need` are."""
    out = np.full(X.shape, np.nan)
    lx = np.log(np.where(X > 0, X, np.nan))
    for i in range(X.shape[0]):
        r = lx[i]
        if np.isfinite(r).sum() < need:
            continue
        w = swv(np.concatenate([np.full(win - 1, np.nan), r]), win)
        n = np.isfinite(w).sum(1)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            out[i] = np.where(n >= need, np.nanmedian(w, 1), np.nan)
    return out


def lines(P, EPS):
    with np.errstate(invalid='ignore', divide='ignore'):
        pe = np.where(EPS > 0, P / EPS, np.nan)
        mpe = own_median_log(pe)
        el = np.where((EPS > 0) & np.isfinite(mpe), np.exp(mpe) * EPS, np.nan)
    return {'ma4': moving(P, MA_REV), 'ma10': moving(P, MA_SHORT), 'ma40': moving(P, MA_LONG), 'pe': pe, 'mpe': mpe, 'el': el}


def costs(C, V):
    """One-way trading cost by the 13-week mean weekly dollar volume (rrg_hybrid.COST_TIERS)."""
    dv = C * V
    L, W = dv.shape
    cs = np.concatenate([np.zeros((L, 1)), np.cumsum(np.where(np.isfinite(dv), dv, 0), 1)], 1)
    mdv = np.full((L, W), np.nan)
    if W > 13:
        mdv[:, 12:] = (cs[:, 13:] - cs[:, :-13]) / 13
    out = np.full((L, W), HY.COST_TIERS[-1][1] / 1e4)
    for lim, bp in reversed(HY.COST_TIERS[:-1]):
        out = np.where(mdv >= lim, bp / 1e4, out)
    return out


def inputs(A, Lns, mz=None):
    """The ranked inputs; with mz ({reading: z-score per week on its own past}) also the trend inputs × each reading
    (the trend's weight allowed to move with the macro: the 'ma_macro' model)."""
    P, EPS = A['P'], A['EPS']
    with np.errstate(invalid='ignore', divide='ignore'):
        lP = np.log(P)
        raw = {'tr40': lP - np.log(Lns['ma40']), 'tr10_40': np.log(Lns['ma10']) - np.log(Lns['ma40']), 'rev4': np.log(Lns['ma4']) - lP,
               'sue': np.clip(A['SUE'], -5, 5), 'srg': np.clip(A['SRG'], -1, 1), 'val': Lns['mpe'] - np.log(Lns['pe']),
               'ey': np.clip(np.where(P > 0, EPS / P, np.nan), -0.5, 0.5), 'guid': np.where(np.isfinite(A['G']), A['G'], 0.0)}
    ok = TR.liquid(A['C'], A['V']) & np.isfinite(raw['tr40']) & np.isfinite(raw['tr10_40']) & np.isfinite(raw['rev4'])
    Z = {}
    for k, X in raw.items():
        if k == 'guid':
            Z[k] = np.where(ok, X, np.nan)
            continue
        z = HY.xs_z(X, ok).astype(np.float64)
        Z[k] = z if k in ('tr40', 'tr10_40', 'rev4') else np.where(ok & ~np.isfinite(z), 0.0, z)   # missing: the average
    for k, zm in (mz or {}).items():
        m = np.where(np.isfinite(zm), zm, 0.0)[None]                  # before a reading has three years: no tilt
        Z[f'tr40x{k}'] = np.where(ok, Z['tr40'] * m, np.nan)
        Z[f'tr10x{k}'] = np.where(ok, Z['tr10_40'] * m, np.nan)
    return raw, Z, ok


# ------------------------------------------------------------------ models
def walk_forward(days, Z, ok, Ydm, cols, h):
    """Yearly ridge refits (training weeks whose h-week outcome was known by 1 January, from FIT_FROM), forecasts from
    FIRST_OOS. → (F, coefficients by year {col: per unit of the ranked input})."""
    yrs = years_of(days)
    L, W = Ydm.shape
    F = np.full((L, W), np.nan)
    coefs = {}
    for Y in range(FIRST_OOS, int(yrs[-1]) + 1):
        tr = ok & np.isfinite(Ydm) & HY.known_before(days, h, Y)[None] & (yrs >= FIT_FROM)[None]
        if tr.sum() < 2000:
            continue
        y = Ydm[tr]
        lo, hi = np.quantile(y, WINSOR)
        X = np.stack([Z[c][tr] for c in cols], 1)
        m = HY.ridge(X, np.clip(y, lo, hi), RIDGE)
        te = ok & (yrs == Y)[None]
        F[te] = HY.ridge_predict(m, np.stack([Z[c][te] for c in cols], 1))
        coefs[Y] = {c: r_(b / s, 6) for c, b, s in zip(cols, m['b'], m['sd'])}
    return F, coefs


def week_stats(xs, h):
    """Mean of per-week values, its t with weeks ÷ h counted as independent, share positive, weeks."""
    a = np.asarray([x for x in xs if fin(x)], float)
    if len(a) < 20:
        return None
    sd = a.std(ddof=1)
    return {'mean': r_(a.mean()), 't': r_(a.mean() / (sd / math.sqrt(max(len(a) / h, 2))), 2) if sd > 0 else None,
            'pos': r_((a > 0).mean(), 3), 'weeks': int(len(a))}


def per_week(X, Yrel, ok, cost, mode):
    """Per week: rank correlation (mode 'fifths') and the basket spread in simple returns after costs, both legs in and
    out: 'fifths' the best − worst fifth by X; 'sign' X > 0 against X < 0."""
    L, W = X.shape
    ic, net, gross = np.full(W, np.nan), np.full(W, np.nan), np.full(W, np.nan)
    Ys = np.expm1(Yrel)
    for t in range(W):
        m = ok[:, t] & np.isfinite(X[:, t]) & np.isfinite(Yrel[:, t])
        if m.sum() < MIN_NAMES:
            continue
        x, y, c = X[m, t], Ys[m, t], cost[m, t]
        if mode == 'fifths':
            if np.ptp(x) == 0:
                continue
            ra, rb = np.argsort(np.argsort(x)), np.argsort(np.argsort(Yrel[m, t]))
            ic[t] = np.corrcoef(ra, rb)[0, 1]
            q = np.quantile(x, [0.2, 0.8])
            hi_, lo_ = x >= q[1], x <= q[0]
        else:
            hi_, lo_ = x > 0, x < 0
        if hi_.sum() < MIN_SIDE or lo_.sum() < MIN_SIDE:
            continue
        gross[t] = y[hi_].mean() - y[lo_].mean()
        net[t] = gross[t] - 2 * c[hi_].mean() - 2 * c[lo_].mean()
    return ic, net, gross


def periods(days):
    yrs = years_of(days)
    last = int(yrs[-1])
    return {f'{TEST_FROM}–{last}': (yrs >= TEST_FROM), f'{TEST_FROM}–{SPLIT_AT - 1}': (yrs >= TEST_FROM) & (yrs < SPLIT_AT),
            f'{SPLIT_AT}–{last}': (yrs >= SPLIT_AT)}


def summarize(days, h, ic, net, gross):
    out = {}
    for name, sel in periods(days).items():
        out[name] = {'ic': week_stats(ic[sel], h), 'net': week_stats(net[sel], h), 'gross': week_stats(gross[sel], h)}
    return out


def hybrid_log(lns, w, g, G):
    """log H for weights (w, g): the 40-week average blended with the earnings line where there is one."""
    l40 = np.log(lns['ma40'])
    with np.errstate(invalid='ignore', divide='ignore'):
        lel = np.log(lns['el'])
        base = np.where(np.isfinite(lel), (1 - w) * l40 + w * lel, l40)
    return base + np.log1p(g * np.where(np.isfinite(G), G, 0.0))


def evaluate(days, A, lns, raw, Z, ok, cost, verbose=lambda *a: None):
    yrs = years_of(days)
    rel = np.diff(np.log(A['C']), axis=1, prepend=np.nan) - np.diff(np.log(A['spy']), prepend=np.nan)[None]
    out = {'models': {}, 'rules': {}, 'lines': {}, 'picks': {}, 'coefs': {}, 'ic_by_year': {}, 'net_by_year': {}}
    F_now = {}
    lP = np.log(A['P'])
    for h in HORIZONS:
        Y = HY.fwd_sum(rel, h)
        Ydm = HY.demean(Y, ok)
        out['models'][str(h)], out['coefs'][str(h)], out['ic_by_year'][str(h)], out['net_by_year'][str(h)] = {}, {}, {}, {}
        for name, cols in MODELS.items():
            if not all(c in Z for c in cols):                         # no macro file: no macro model
                continue
            F, coefs = walk_forward(days, Z, ok, Ydm, cols, h)
            ic, net, gross = per_week(F, Y, ok, cost, 'fifths')
            out['models'][str(h)][name] = summarize(days, h, ic, net, gross)
            out['coefs'][str(h)][name] = {str(k): v for k, v in coefs.items() if k >= TEST_FROM - 1}
            out['ic_by_year'][str(h)][name] = {str(Yr): r_(np.nanmean(ic[yrs == Yr]), 3) for Yr in range(TEST_FROM, int(yrs[-1]) + 1)
                                              if np.isfinite(ic[yrs == Yr]).sum() >= 10}
            out['net_by_year'][str(h)][name] = {str(Yr): r_(np.nanmean(net[yrs == Yr]), 4) for Yr in range(TEST_FROM, int(yrs[-1]) + 1)
                                               if np.isfinite(net[yrs == Yr]).sum() >= 10}
            F_now[(h, name)] = F
            s0 = out['models'][str(h)][name][list(periods(days))[0]]
            verbose(f"ma hybrid {h}w {name}: IC {(s0['ic'] or {}).get('mean')}, best − worst fifth after costs {(s0['net'] or {}).get('mean')}")
        out['rules'][str(h)] = {}
        for name, X in (('above40', raw['tr40']), ('cross', raw['tr10_40'])):
            _, net, gross = per_week(X, Y, ok, cost, 'sign')
            out['rules'][str(h)][name] = summarize(days, h, np.full(len(days), np.nan), net, gross)
        # the line grid and the yearly pick
        nets = {}
        out['lines'][str(h)] = {}
        for w in WS:
            for g in GS:
                X = lP - hybrid_log(lns, w, g, A['G'])
                _, net, gross = per_week(X, Y, ok, cost, 'sign')
                nets[(w, g)] = net
                out['lines'][str(h)][f'{w:g}|{g:g}'] = summarize(days, h, np.full(len(days), np.nan), net, gross)
        picks, oos = {}, np.full(len(days), np.nan)
        for Yr in range(TEST_FROM, int(yrs[-1]) + 1):
            known = HY.known_before(days, h, Yr) & (yrs >= FIRST_OOS)
            best = None
            for k, v in nets.items():
                vv = v[known]
                vv = vv[np.isfinite(vv)]
                if len(vv) < 52:
                    continue
                for sign in (1, -1):
                    if best is None or sign * vv.mean() > best[0]:
                        best = (sign * float(vv.mean()), k, sign)
            if best is None:
                continue
            picks[str(Yr)] = {'w': best[1][0], 'g': best[1][1], 'reading': 'trend' if best[2] > 0 else 'value'}
            cur = yrs == Yr
            oos[cur] = best[2] * nets[best[1]][cur]
        out['picks'][str(h)] = {'by_year': picks, 'oos': summarize(days, h, np.full(len(days), np.nan), oos, np.full(len(days), np.nan))}
    return out, F_now


WEEKS_A_YEAR = 365.25 / 7


def ndays_eval(days, A, ok, cost, dg=None):
    """Price above its N-day average − below, and each cross (the shorter average above the longer − below), in simple
    returns against SPY after costs. 'weekly': from 2016, each N-day average in its weekly form (the N/5-week average of
    weekly closes; none for 5 days), the same companies and weeks for every length. 'daily' (dg: the daily signals on
    the grid): exactly, on daily closes, from the first Friday with every average behind it — with the weekly form on
    the same companies and weeks beside it, to show what the weekly form misses."""
    rel = np.diff(np.log(A['C']), axis=1, prepend=np.nan) - np.diff(np.log(A['spy']), prepend=np.nan)[None]
    nanw = np.full(len(days), np.nan)
    wl = lambda n: int(round(n / 5))
    with np.errstate(divide='ignore', invalid='ignore'):
        lP = np.log(A['P'])
        lm = {k: np.log(moving(A['P'], k)) for k in sorted({wl(n) for n in NDAYS + sum(CROSSES, ()) if wl(n) >= 2})}
    wk = {f'above:{n}': lP - lm[wl(n)] for n in NDAYS if wl(n) >= 2}
    wk.update({f'cross:{a}/{b}': lm[wl(a)] - lm[wl(b)] for a, b in CROSSES if wl(a) >= 2})
    common = ok & np.isfinite(wk['above:250'])
    out = {'n': list(NDAYS), 'crosses': [list(c) for c in CROSSES], 'weeks_for': {str(n): wl(n) for n in NDAYS if wl(n) >= 2},
           'weekly': {}, 'daily': None}
    Ys = {h: HY.fwd_sum(rel, h) for h in HORIZONS}
    for h in HORIZONS:
        out['weekly'][str(h)] = {}
        for name, X in wk.items():
            _, net, gross = per_week(X, Ys[h], common, cost, 'sign')
            out['weekly'][str(h)][name] = summarize(days, h, nanw, net, gross)
    if dg:
        has = ok & np.isfinite(dg['above:250']) & np.isfinite(dg[f'cross:{CROSSES[-1][0]}/{CROSSES[-1][1]}'])
        cover = has.sum(0)
        good = np.where(cover >= MIN_NAMES)[0]
        if len(good):
            t0 = int(good[0])
            sl = slice(t0, None)
            P = sub_periods(days, t0)
            D = {'from': str(days[t0]), 'companies': int(np.median(cover[good])), 'periods': list(P), 'to': {}}
            for h in HORIZONS:
                D[str(h)] = {}
                last = None
                for name, X in dg.items():
                    _, net, gross = per_week(X[:, sl], Ys[h][:, sl], has[:, sl], cost[:, sl], 'sign')
                    same = None
                    if name in wk:                            # the weekly form on the same companies and weeks
                        _, sn, _ = per_week(wk[name][:, sl], Ys[h][:, sl], has[:, sl] & np.isfinite(wk[name][:, sl]), cost[:, sl], 'sign')
                        same = week_stats(sn, h)
                    D[str(h)][name] = {'periods': {p: {'net': week_stats(net[m], h), 'gross': week_stats(gross[m], h)} for p, m in P.items()},
                                       'weekly_form': same}
                    f = np.where(np.isfinite(net))[0]
                    if len(f):
                        last = max(last or 0, int(f[-1]) + t0)
                D['to'][str(h)] = str(days[last]) if last is not None else None
            out['daily'] = D
    return out


def sub_periods(days, t0):
    """The daily test's periods from its first week t0: all of it, and before / from SPLIT_AT when it spans both."""
    yrs = years_of(days)[t0:]
    y0, last = int(yrs[0]), int(yrs[-1])
    P = {f'{y0}–{last}': np.ones(len(yrs), bool)}
    if y0 < SPLIT_AT <= last:
        P[f'{y0}–{SPLIT_AT - 1}'] = yrs < SPLIT_AT
        P[f'{SPLIT_AT}–{last}'] = yrs >= SPLIT_AT
    return P


def index_timing(public, days, mac, flags, t):
    """The fund rules (INDEX_RULES) for SPY, QQQ, DIA, MDY and IWM, each from 1996 or its own start: decided at each
    Friday's close on the total-return close and the macro as known then, held the next week; cash earns the fed funds
    rate as known; SWITCH_BP each switch. Annual return, volatility, the worst fall, time invested, switches, by period."""
    D = json.loads((Path(public) / 'rrg.json').read_text(encoding='utf-8'))
    W, g0 = len(days), days[0]

    def place(start, arr):
        a = np.full(W, np.nan)
        o = int((np.datetime64(start) - g0).astype(int) // 7)
        v = np.array([np.nan if q is None else q for q in arr], float)
        if o < W:
            a[max(0, o):o + len(v)] = v[max(0, -o):W - o]
        return a
    funds = {}
    if D.get('bench') and D.get('benchmark', 'SPY') == 'SPY':
        funds['SPY'] = place(D['bench']['start'], D['bench']['c'])
    for s in D.get('series') or []:
        if s.get('id') in INDEX_FUNDS and s['id'] not in funds and s.get('c'):
            funds[s['id']] = place(s['start'], s['c'])
    yrs = years_of(days)
    ff = mac['x'].get('ff')
    cash = np.where(np.isfinite(ff), ff / 100 / WEEKS_A_YEAR, 0.0) if ff is not None else np.zeros(W)
    last = int(yrs[t])
    per = {f'{INDEX_FROM}–{last}': (yrs >= INDEX_FROM), f'{INDEX_FROM}–{INDEX_SPLIT - 1}': (yrs >= INDEX_FROM) & (yrs < INDEX_SPLIT),
           f'{INDEX_SPLIT}–{last}': (yrs >= INDEX_SPLIT)}
    out = {'rules': INDEX_RULES, 'periods': list(per), 'switch_bp': SWITCH_BP, 'sahm_on': SAHM_ON, 'funds': {}}
    for name in [f for f in INDEX_FUNDS if f in funds]:
        c = funds[name]
        m40 = moving(c[None], MA_LONG)[0]
        above = np.where(np.isfinite(m40) & np.isfinite(c), c > m40, False)
        r = np.full(W, np.nan)
        r[1:] = c[1:] / c[:-1] - 1
        can = np.isfinite(m40) & np.isfinite(c) & flags['known'] & (yrs >= INDEX_FROM)
        can[t + 1:] = False
        if not can.any():
            continue
        start = int(np.argmax(can))
        pos = {'hold': np.ones(W, bool), 'above40': above, 'trend_unemployment': above | ~flags['unemp_up'], 'trend_sahm': above | ~flags['sahm_on']}
        u = np.arange(start + 1, t + 1)                               # the weeks earned, each decided the Friday before
        F = {'start': str(days[start]), 'rules': {}}
        for rule, p in pos.items():
            held = p[u - 1]
            sw = np.zeros(len(u), bool)
            sw[1:] = held[1:] != held[:-1]
            ret = np.where(held, r[u], cash[u - 1]) - sw * SWITCH_BP / 1e4
            F['rules'][rule] = {}
            for pname, ps in per.items():
                m = np.isfinite(ret) & ps[u]
                if m.sum() < 52:
                    F['rules'][rule][pname] = None
                    continue
                rr = ret[m]
                eq = np.cumprod(1 + rr)
                F['rules'][rule][pname] = {'cagr': r_(eq[-1] ** (WEEKS_A_YEAR / len(rr)) - 1, 4), 'vol': r_(rr.std(ddof=1) * math.sqrt(WEEKS_A_YEAR), 4),
                                           'maxdd': r_(float(np.min(eq / np.maximum.accumulate(eq) - 1)), 4), 'invested': r_(held[m].mean(), 3),
                                           'switches': int(sw[m].sum()), 'from': str(days[u[m][0]]), 'years': r_(len(rr) / WEEKS_A_YEAR, 1)}
        F['now'] = {'close': sig(c[t], 5), 'ma40': sig(m40[t], 5), 'gap40': r_(math.log(c[t] / m40[t]), 4) if fin(c[t]) and fin(m40[t]) else None,
                    'in': {rule: bool(p[t]) for rule, p in pos.items()}}
        out['funds'][name] = F
    out['now'] = {'asof': str(days[t]), 'unrate': r_(flags['unrate'][t], 2), 'unrate12': r_(flags['unrate12'][t], 3), 'unemp_up': bool(flags['unemp_up'][t]),
                  'sahm3': r_(flags['sahm3'][t], 3), 'sahm_on': bool(flags['sahm_on'][t]), 'ff': r_(ff[t], 2) if ff is not None else None}
    return out


def macro_regimes(days, A, raw, ok, cost, mac, ex, t):
    """Above − below the 40-week average (simple returns against SPY after costs) in each third of each macro reading,
    from 2016, the thirds from the reading's own past only; and where each reading stands this week."""
    yrs = years_of(days)
    sel = yrs >= TEST_FROM
    rel = np.diff(np.log(A['C']), axis=1, prepend=np.nan) - np.diff(np.log(A['spy']), prepend=np.nan)[None]
    out = {'period': f'{TEST_FROM}–{int(yrs[-1])}', 'readings': {}, 'now': {}, 'min_weeks': MACRO_MIN_WEEKS}
    tests = 0
    for h in HORIZONS:
        _, net, _ = per_week(raw['tr40'], HY.fwd_sum(rel, h), ok, cost, 'sign')
        out[str(h)] = {'all': week_stats(net[sel], h)}
        for k, (third, cut, z) in ex.items():
            out[str(h)][k] = [week_stats(net[sel & (third == j)], h) for j in range(3)]
            tests += sum(1 for c in out[str(h)][k] if c)
    for k, (third, cut, z) in ex.items():
        lab, unit = mac['labels'].get(k, (k, ''))
        out['readings'][k] = {'label': lab, 'unit': unit}
        out['now'][k] = {'value': r_(mac['x'][k][t], 3), 'third': int(third[t]), 'cut': [r_(cut[t, 0], 3), r_(cut[t, 1], 3)], 'z': r_(z[t], 2)}
    out['tests'] = tests
    return out


def macro_state(regimes, index):
    """This week's macro, as frozen in the ledger: each reading and its third, the unemployment flags, each fund's rules."""
    st_ = {k: [v['value'], v['third']] for k, v in ((regimes or {}).get('now') or {}).items()}
    if index:
        n = index.get('now') or {}
        st_.update({'unemp_up': n.get('unemp_up'), 'sahm3': n.get('sahm3'), 'sahm_on': n.get('sahm_on')})
        st_['funds'] = {f: v['now']['in'] for f, v in (index.get('funds') or {}).items()}
    return st_ or None


# ------------------------------------------------------------------ now
def pct_rank(v, ok):
    out = np.full(len(v), np.nan)
    m = ok & np.isfinite(v)
    if m.sum() >= 2:
        r = np.argsort(np.argsort(v[m]))
        out[m] = r / (m.sum() - 1)
    return out


def snapshot(val, mdna, tk, P):
    """A company's Fair value numbers and latest MD&A tone, with the price's distance to the DCF value (log)."""
    v = dict(val.get(tk) or {})
    if fin(v.get('dcf_value')) and v['dcf_value'] > 0 and fin(P) and P > 0:
        v['dcf_gap_now'] = r_(math.log(P / v['dcf_value']), 4)
    return (v or None), (mdna.get(tk) if mdna else None)


DAILY_KEYS = ('d_asof', 'd_close', 'x50_200', 'up50_200') + tuple(f'd{n}' for n in DAILY_GAPS)


def with_daily(row, daily):
    """A row's daily numbers (latest daily close vs its 20 / 50 / 200-day averages, the 50/200-day cross), or none."""
    row.update(daily_now(*daily[row['id']]) if row['id'] in (daily or {}) else {k: None for k in DAILY_KEYS})
    return row


def current_rows(days, A, lns, raw, ok, F_now, t, val=None, mdna=None, daily=None):
    rows = []
    s_ma, s_hy = F_now[(26, 'ma')][:, t], F_now[(26, 'hybrid')][:, t]
    s_mm = F_now[(26, 'ma_macro')][:, t] if (26, 'ma_macro') in F_now else np.full(len(s_ma), np.nan)
    p_ma, p_hy, p_mm = pct_rank(s_ma, ok[:, t]), pct_rank(s_hy, ok[:, t]), pct_rank(s_mm, ok[:, t])
    lHd = hybrid_log(lns, DEFAULT[0], DEFAULT[1], A['G'])[:, t]
    for i, tk in enumerate(A['ids']):
        if not ok[i, t]:
            continue
        m = A['meta'][tk]
        P = A['P'][i, t]
        rows.append({'id': tk, 'name': m['name'], 'cik': m['cik'], 'sector': m['sector'], 'close': sig(P, 5),
                     'ma10': sig(lns['ma10'][i, t]), 'ma40': sig(lns['ma40'][i, t]), 'el': sig(lns['el'][i, t]),
                     'pe': r_(lns['pe'][i, t], 1), 'pe_med': r_(math.exp(lns['mpe'][i, t]), 1) if fin(lns['mpe'][i, t]) else None,
                     'guid': int(A['G'][i, t]) if fin(A['G'][i, t]) else None, 'guid_last': m['guidance'][-1] if m['guidance'] else None,
                     'above40': bool(raw['tr40'][i, t] > 0), 'cross': bool(raw['tr10_40'][i, t] > 0),
                     'hybrid': sig(math.exp(lHd[i])) if fin(lHd[i]) else None,
                     'gap40': r_(raw['tr40'][i, t], 4), 'gap_hybrid': r_(math.log(P) - lHd[i], 4) if fin(lHd[i]) and fin(P) else None,
                     's_ma': r_(s_ma[i], 5), 's_hybrid': r_(s_hy[i], 5), 'pct_ma': r_(p_ma[i], 3), 'pct_hybrid': r_(p_hy[i], 3),
                     's_macro': r_(s_mm[i], 5), 'pct_macro': r_(p_mm[i], 3),
                     'sue': r_(raw['sue'][i, t], 2), 'srg': r_(raw['srg'][i, t], 4)})
        rows[-1]['val'], rows[-1]['mdna'] = snapshot(val or {}, mdna or {}, tk, P)
        with_daily(rows[-1], daily)
    return rows


def series_file(days, A, lns, i, t, row=None):
    """One company's lines for its chart: the last SERIES_WEEKS weekly closes, averages, earnings line, guidance, and this
    week's numbers from its row (P/E, its own median, the models' percentiles)."""
    lo = max(0, t - SERIES_WEEKS + 1)
    pick = lambda a: [sig(v) for v in a[i, lo:t + 1]]
    now = {k: row.get(k) for k in ('pe', 'pe_med', 'pct_ma', 'pct_hybrid', 'pct_macro', 's_ma', 's_hybrid', 's_macro', 'sue', 'srg', 'val', 'mdna')} if row else None
    return {'id': A['ids'][i], 'name': A['meta'][A['ids'][i]]['name'], 'start': str(days[lo]), 'p': pick(A['P']), 'ma10': pick(lns['ma10']),
            'ma40': pick(lns['ma40']), 'el': pick(lns['el']), 'g': [None if not fin(v) else int(v) for v in A['G'][i, lo:t + 1]],
            'guidance': A['meta'][A['ids'][i]]['guidance'], 'now': now}


# ------------------------------------------------------------------ ledger
def ledger_update(book, days, t, A, lns, raw, ok, F_now, val=None, mdna=None, macro=None):
    asof = str(days[t])
    rel = np.diff(np.log(A['C']), axis=1, prepend=np.nan) - np.diff(np.log(A['spy']), prepend=np.nan)[None]
    m = ok[:, t] & np.isfinite(F_now[(26, 'hybrid')][:, t])
    if m.sum() > LEDGER_MAX_LINES:
        dv = np.where(m, A['C'][:, t] * np.nan_to_num(A['V'][:, max(0, t - 12):t + 1]).mean(1), -np.inf)
        m = np.zeros_like(m)
        m[np.argsort(dv)[-LEDGER_MAX_LINES:]] = True
    idx = np.where(m)[0]
    with np.errstate(invalid='ignore', divide='ignore'):
        gap_el = np.log(A['P'][:, t]) - np.log(lns['el'][:, t])
    for h in HORIZONS:
        if len(idx):
            FB.freeze(book, f'ma:{h}', asof, asof, {'ids': [A['ids'][i] for i in idx],
                                                   's_ma': [r_(v, 5) for v in F_now[(h, 'ma')][idx, t]],
                                                   's_hybrid': [r_(v, 5) for v in F_now[(h, 'hybrid')][idx, t]],
                                                   'gap40': [r_(v, 4) for v in raw['tr40'][idx, t]],
                                                   'gap_el': [r_(v, 4) for v in gap_el[idx]],
                                                   'guid': [int(v) for v in raw['guid'][idx, t]],
                                                   'dcf_gap': [snapshot(val or {}, {}, A['ids'][i], A['P'][i, t])[0].get('dcf_gap_now')
                                                               if (val or {}).get(A['ids'][i]) else None for i in idx],
                                                   'p_above': [((val or {}).get(A['ids'][i]) or {}).get('mc_p_above') for i in idx],
                                                   'p_implied': [((val or {}).get(A['ids'][i]) or {}).get('p_implied') for i in idx],
                                                   'mdna_tone': [((mdna or {}).get(A['ids'][i]) or {}).get('tone') for i in idx],
                                                   's_macro': [r_(v, 5) for v in F_now[(h, 'ma_macro')][idx, t]] if (h, 'ma_macro') in F_now else None,
                                                   'macro': macro},
                      meta={'model': f'ma_hybrid v{VERSION}'})
        ix = {k: i for i, k in enumerate(A['ids'])}
        for key, e in FB.entries(book, f'ma:{h}', resolved=False):
            k0 = int(np.searchsorted(days, np.datetime64(e['asof'])))
            if k0 >= len(days) or str(days[k0]) != e['asof'] or k0 + h > t:
                continue
            out = []
            for k in e['forecast']['ids']:
                i = ix.get(k)
                s = rel[i, k0 + 1:k0 + h + 1] if i is not None else None
                out.append(r_(float(s.sum()), 5) if s is not None and np.isfinite(s).all() else None)
            FB.resolve(book, f'ma:{h}', key, {'rel': out})


def ledger_scores(book):
    out = {}
    for fam in sorted(book.get('families') or {}):
        ents = FB.entries(book, fam, resolved=True)
        ics, ls, ab, extra = [], [], [], {k: [] for k in ('dcf_gap', 'p_above', 'mdna_tone', 's_ma', 's_macro')}
        for _, e in ents:
            f, y = e['forecast'], (e['actual'] or {}).get('rel') or []
            for k in extra:                                       # the recorded valuation, odds, MD&A tone and the other models, ranked
                w = [(a, c) for a, c in zip(f.get(k) or [], y) if fin(a) and fin(c)]
                if len(w) >= 20 and np.ptp([a for a, _ in w]) > 0:
                    a_, c_ = np.array([q[0] for q in w]), np.array([q[1] for q in w])
                    sign = -1 if k == 'dcf_gap' else 1                 # dcf_gap is log(price ÷ value): cheap is negative
                    extra[k].append(float(np.corrcoef(np.argsort(np.argsort(sign * a_)), np.argsort(np.argsort(c_)))[0, 1]))
            v = [(a, g, c) for a, g, c in zip(f.get('s_hybrid') or [], f.get('gap40') or [], y) if fin(a) and fin(c)]
            if len(v) < 8:
                continue
            a = np.array([x[0] for x in v]); c = np.array([x[2] for x in v]); g = np.array([x[1] if fin(x[1]) else np.nan for x in v])
            if np.ptp(a) > 0:
                ics.append(float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(c)))[0, 1]))
                q = np.quantile(a, [0.2, 0.8])
                ls.append(float(np.expm1(c[a >= q[1]]).mean() - np.expm1(c[a <= q[0]]).mean()))
            if (g > 0).sum() >= 5 and (g < 0).sum() >= 5:
                ab.append(float(np.expm1(c[g > 0]).mean() - np.expm1(c[g < 0]).mean()))
        out[fam] = {'resolved_weeks': len(ics), 'pending_weeks': len(FB.entries(book, fam, resolved=False)),
                    'ic': r_(np.mean(ics)) if ics else None, 'best_minus_worst': r_(np.mean(ls)) if ls else None,
                    'above_minus_below40': r_(np.mean(ab)) if ab else None,
                    'ic_recorded': {k: ({'ic': r_(np.mean(v)), 'weeks': len(v)} if v else None) for k, v in extra.items()}}
    return out


# ------------------------------------------------------------------ everything
def closed_week(public, today=None):
    D, g0, W, days = grid(public)
    return days, HY.closed_week(days, today or dt.date.today())


def fresh(public, asof, max_days=3):
    p = Path(public) / 'ma-hybrid.json'
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        made = dt.datetime.fromisoformat(d.get('generated_at'))
    except (OSError, ValueError, TypeError):
        return False
    return d.get('version') == VERSION and d.get('asof') == asof and (dt.datetime.now(dt.timezone.utc) - made).days < max_days


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def daily_source(bars_sha=None):
    return {'bars_sha': bars_sha, 'daily_built_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}


def daily_needed(public, bars_sha):
    """True when the daily files were made from another research-paths commit than bars_sha (or not yet)."""
    R = read_json(Path(public) / 'ma-hybrid-rows.json')
    return bool(R) and (not bars_sha or R.get('bars_sha') != bars_sha)


def build(public, fundamentals, guidance=None, ledger=None, today=None, verbose=True, force=False, valuation=None, outlook=None,
          bars=None, bars_sha=None):
    t0 = dt.datetime.now()
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    days0, t_ = closed_week(public, today)
    if not force and fresh(public, str(days0[t_])):
        log(f'ma hybrid: week ending {days0[t_]} already built — kept')
        return None
    with warnings.catch_warnings(), np.errstate(all='ignore'):
        warnings.simplefilter('ignore', RuntimeWarning)
        A = load(public, fundamentals, guidance)
        days = A['days']
        t = HY.closed_week(days, today or dt.date.today())
        log(f'ma hybrid: {len(A["ids"])} companies with weekly prices and first-filed quarters')
        lns = lines(A['P'], A['EPS'])
        mac = macro_load(public, days)
        ex, mz, flags = {}, None, None
        if mac:
            ex = {k: expanding(mac['x'][k]) for k in MACRO_READINGS if k in mac['x']}
            mz = {k: ex[k][2] for k in MACRO_MODEL if k in ex}
            if mac.get('weekly_from'):                      # the check: each reading scaled on its weekly block only (2009 on)
                for k in MACRO_MODEL:
                    if k in mac['x']:
                        x09 = mac['x'][k].copy()
                        x09[:mac['weekly_from']] = np.nan
                        mz[f'{k}_09'] = expanding(x09)[2]
            flags = macro_flags(mac)
        raw, Z, ok = inputs(A, lns, mz)
        cost = costs(A['C'], A['V'])
        ev, F_now = evaluate(days, A, lns, raw, Z, ok, cost, log)
        ev['guidance_events'] = guidance_events(days, A, ok)
        val, mdna, mev = load_extras(A, valuation, outlook)
        ev['mdna_events'] = mdna_events(days, A, ok, mev) if mev else None
        daily = load_daily(bars, A['ids'])
        log(f'ma hybrid: daily closes for {len(daily)} companies')
        ev['ndays'] = ndays_eval(days, A, ok, cost, daily_on_grid(daily, A['ids'], days) if daily else None)
        ev['macro'] = None
        if mac:
            ev['macro'] = {'regimes': macro_regimes(days, A, raw, ok, cost, mac, ex, t) if ex else None,
                           'index': index_timing(public, days, mac, flags, t) if flags else None, 'generated_at': mac.get('generated_at')}
        rows = current_rows(days, A, lns, raw, ok, F_now, t, val, mdna, daily)
    pub = Path(public)
    (pub / 'ma').mkdir(parents=True, exist_ok=True)
    keep, by_id = set(), {r['id']: r for r in rows}
    for i, tk in enumerate(A['ids']):
        if ok[i, t]:
            (pub / 'ma' / f'{tk}.json').write_text(json.dumps(clean(series_file(days, A, lns, i, t, by_id.get(tk))), separators=(',', ':')), encoding='utf-8')
            keep.add(f'{tk}.json')
    for f in (pub / 'ma').glob('*.json'):                  # a company no longer liquid: its file goes
        if f.name not in keep:
            f.unlink()
    n_daily = write_daily(pub, daily, {r['id']: r['name'] for r in rows}) if daily else 0
    d_asof = max((r['d_asof'] for r in rows if r.get('d_asof')), default=None)
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'version': VERSION, 'asof': str(days[t]),
           'daily': {'asof': d_asof, 'companies': n_daily, 'folder': 'ma-daily', 'rows': DAILY_ROWS, 'n': list(NDAYS),
                     'crosses': [list(c) for c in CROSSES], 'gaps': list(DAILY_GAPS), 'cross_recent': CROSS_RECENT},
           'macro_readings': list(MACRO_READINGS), 'macro_model': list(MACRO_MODEL),
           'test_from': TEST_FROM, 'split_at': SPLIT_AT, 'horizons': list(HORIZONS), 'weights': {'w': list(WS), 'g': list(GS), 'default': list(DEFAULT)},
           'windows': {'ma_short': MA_SHORT, 'ma_long': MA_LONG, 'pe_window': PE_WINDOW, 'pe_min': PE_MIN, 'guide_weeks': GUIDE_WEEKS},
           'models': {k: {'name': MODEL_NAMES[k], 'inputs': [FEATURE_NAMES[c] for c in v]} for k, v in MODELS.items()},
           'features': FEATURE_NAMES, 'costs_bp': [[lim, bp] for lim, bp in HY.COST_TIERS], 'scores': ev, 'companies': len(A['ids']),
           'now': len(rows), 'with_earnings_line': sum(1 for r in rows if r['el']), 'with_guidance': sum(1 for r in rows if r['guid'] is not None),
           'with_valuation': sum(1 for r in rows if r.get('val') and fin(r['val'].get('dcf_value'))), 'with_mdna': sum(1 for r in rows if r.get('mdna')),
           'rows_file': 'ma-hybrid-rows.json', 'note': __doc__.split('\n\n')[0]}
    if ledger:
        book = FB.load(ledger)
        M = ev['macro'] or {}
        ledger_update(book, days, t, A, lns, raw, ok, F_now, val, mdna, macro_state(M.get('regimes'), M.get('index')) if M else None)
        FB.save(ledger, book)
        doc['ledger'] = ledger_scores(book)
    doc['seconds'] = round((dt.datetime.now() - t0).total_seconds(), 1)
    R = {'asof': doc['asof'], 'daily_asof': d_asof, 'rows': rows}
    if daily:
        R.update(daily_source(bars_sha))
    else:                                    # no bars this run: the daily files on file stay; no commit recorded, so the next
        R.update({'bars_sha': None,          # run's daily refresh brings the rows' daily numbers back
                  'daily_built_at': (read_json(pub / 'ma-hybrid-rows.json') or {}).get('daily_built_at')})
    (pub / 'ma-hybrid-rows.json').write_text(json.dumps(clean(R), separators=(',', ':')), encoding='utf-8')
    (pub / 'ma-hybrid.json').write_text(json.dumps(clean(doc), separators=(',', ':')), encoding='utf-8')
    log(f"ma hybrid: {len(rows)} companies now ({n_daily} with daily closes), written in {doc['seconds']}s")
    return doc


def build_daily(public, bars, bars_sha=None, verbose=True):
    """Between weekly builds: the daily files and the rows' daily numbers from the price cache as it is now. The weekly
    numbers and ma-hybrid.json are left as they are (their freshness decides the next weekly build)."""
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    pub = Path(public)
    rp = pub / 'ma-hybrid-rows.json'
    if not rp.exists():
        log('ma hybrid daily: no weekly build yet — nothing to refresh')
        return None
    R = json.loads(rp.read_text(encoding='utf-8'))
    rows = R.get('rows') or []
    daily = load_daily(bars, [r['id'] for r in rows])
    if not daily:
        log('ma hybrid daily: no daily closes found — kept as they were')
        return None
    for r in rows:
        with_daily(r, daily)
    n = write_daily(pub, daily, {r['id']: r.get('name') for r in rows})
    R['daily_asof'] = max((r['d_asof'] for r in rows if r.get('d_asof')), default=None)
    R.update(daily_source(bars_sha))
    rp.write_text(json.dumps(clean(R), separators=(',', ':')), encoding='utf-8')
    log(f"ma hybrid daily: {n} companies' daily closes, latest {R['daily_asof']}")
    return R


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--public', required=True)
    ap.add_argument('--fundamentals', help='eps-fundamental/ (data branch): first-filed quarters per company')
    ap.add_argument('--guidance', help='cache/guidance/ (the hub): guidance releases per company')
    ap.add_argument('--valuation', help="research-valuation's public/index.json: this week's Fair value numbers")
    ap.add_argument('--outlook', help='outlook/ (data branch): the MD&A statements read per company')
    ap.add_argument('--bars', help="cache/ohlc/ (branch research-paths): each company's daily bars")
    ap.add_argument('--bars-sha', help='the research-paths commit the bars come from (recorded; --daily-needed compares it)')
    ap.add_argument('--ledger')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--needed', action='store_true', help='exit 0 when this closed week still has to be built, 1 when it is done')
    ap.add_argument('--daily', action='store_true', help='only refresh the daily files and the daily numbers (needs --bars)')
    ap.add_argument('--daily-needed', action='store_true', help='exit 0 when the daily files are from another research-paths commit')
    a = ap.parse_args()
    if a.needed:
        days, t = closed_week(a.public)
        sys.exit(1 if fresh(a.public, str(days[t])) else 0)
    if a.daily_needed:
        sys.exit(0 if daily_needed(a.public, a.bars_sha) else 1)
    if a.daily:
        if not a.bars:
            ap.error('--daily needs --bars')
        build_daily(a.public, a.bars, a.bars_sha)
        return
    if not a.fundamentals:
        ap.error('--fundamentals is required to build')
    build(a.public, a.fundamentals, a.guidance, a.ledger, force=a.force, valuation=a.valuation, outlook=a.outlook, bars=a.bars,
          bars_sha=a.bars_sha)


if __name__ == '__main__':
    main()
