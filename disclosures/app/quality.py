"""Quality metrics and factor research (Disclosures → Quality, the "Quality" view of each company page, the X posts of
pipeline/posts_quality.py). Kept on the branch "research-quality" by .github/workflows/research-quality.yml; scan.yml
publishes its public/ at disclosures/data/research/quality/.

  collect  SEC XBRL frames the hub does not cache yet (one request = one figure for every filer for one period):
           balance-sheet instants at each calendar quarter end (CY2025Q2I …) and the cash-flow / tax / share figures of
           each fiscal year (annual frames CY2021 …). The income-statement frames (revenue, gross profit, operating and
           net income, quarterly and annual) are the hub's own cache (app/frames.py), read in place.
  build    public/ — per company: Piotroski F (9 checks), Altman Z (Z for manufacturers, Z'' otherwise), Beneish M
           (8 indices), shareholder yield, FCF yield before and after stock compensation, owner earnings (Greenwald
           maintenance capex), ROIC, incremental ROIC, ROIC − WACC, operating leverage with a fixed / variable cost
           split, accruals, gross profitability, asset growth, net share issuance; per sector the growth-adjusted
           valuation line (EV/Sales against growth + operating margin) and margin mean reversion; walk-forward factor
           backtests (monthly rank IC, quintile spreads) and a composite ranking frozen each month in a ledger.

Every published number keeps its parts so a reader can check it. Fundamentals are the companies' own XBRL tags as
the SEC's frames API returns them (fiscal years mapped to the nearest calendar period); prices are the hub's daily
closes (app/prices.py). Backtests use only what was public at the time: a fiscal year from 90 days after its end, a
quarter from 45 days after its end. Not investment advice.

    python disclosures/app/quality.py collect --root rq --minutes 20
    python disclosures/app/quality.py build --root rq --frames-root disclosures/docs/data \
        --prices disclosures/docs/data/cache/prices --site-index site/index.json [--valuation rv/public] [--rates debt/public/rates.json]
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, read_json, write_json  # noqa: E402
import frames as FR  # noqa: E402

API = 'https://data.sec.gov/api/xbrl/frames/{tax}/{concept}/{unit}/{period}.json'
# (field, [(taxonomy, concept, unit)] in order of preference)
INSTANT = [
    ('assets', [('us-gaap', 'Assets', 'USD')]),
    ('ca', [('us-gaap', 'AssetsCurrent', 'USD')]),
    ('cl', [('us-gaap', 'LiabilitiesCurrent', 'USD')]),
    ('liab', [('us-gaap', 'Liabilities', 'USD')]),
    ('eq', [('us-gaap', 'StockholdersEquity', 'USD'),
            ('us-gaap', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest', 'USD')]),
    ('re', [('us-gaap', 'RetainedEarningsAccumulatedDeficit', 'USD')]),
    ('cash', [('us-gaap', 'CashAndCashEquivalentsAtCarryingValue', 'USD')]),
    ('ltd', [('us-gaap', 'LongTermDebt', 'USD')]),
    ('ltd_nc', [('us-gaap', 'LongTermDebtNoncurrent', 'USD')]),
    ('ltd_c', [('us-gaap', 'LongTermDebtCurrent', 'USD')]),
    ('ar', [('us-gaap', 'AccountsReceivableNetCurrent', 'USD')]),
    ('ppe', [('us-gaap', 'PropertyPlantAndEquipmentNet', 'USD')]),
    ('so', [('dei', 'EntityCommonStockSharesOutstanding', 'shares')]),
]
ANNUAL = [
    ('ocf', [('us-gaap', 'NetCashProvidedByUsedInOperatingActivities', 'USD')]),
    ('capex', [('us-gaap', 'PaymentsToAcquirePropertyPlantAndEquipment', 'USD')]),
    ('da', [('us-gaap', 'DepreciationDepletionAndAmortization', 'USD'), ('us-gaap', 'DepreciationAndAmortization', 'USD')]),
    ('sbc', [('us-gaap', 'ShareBasedCompensation', 'USD'), ('us-gaap', 'AllocatedShareBasedCompensationExpense', 'USD')]),
    ('buyback', [('us-gaap', 'PaymentsForRepurchaseOfCommonStock', 'USD')]),
    ('div', [('us-gaap', 'PaymentsOfDividendsCommonStock', 'USD'), ('us-gaap', 'PaymentsOfDividends', 'USD')]),
    ('issue', [('us-gaap', 'ProceedsFromIssuanceOfCommonStock', 'USD')]),
    ('interest', [('us-gaap', 'InterestExpense', 'USD')]),
    ('tax', [('us-gaap', 'IncomeTaxExpenseBenefit', 'USD')]),
    ('pretax', [('us-gaap', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'USD')]),
    ('sga', [('us-gaap', 'SellingGeneralAndAdministrativeExpense', 'USD')]),
    ('dil', [('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding', 'shares')]),
    ('eps', [('us-gaap', 'EarningsPerShareDiluted', 'USD-per-shares')]),
]
# income statement, annual and quarterly: the hub's frames cache (app/frames.py)
HUB_ANNUAL = [('rev', FR.REVENUE), ('gp', ['GrossProfit']), ('cogs', FR.COST), ('oi', ['OperatingIncomeLoss']), ('ni', ['NetIncomeLoss'])]
FIN_SECTORS = {'financials', 'real-estate'}
MIN_MCAP = 300e6                                      # the research universe: smaller companies are left out
FY_LAG, Q_LAG = 90, 45                                # days after a period's end before its figures count as public
DEFAULT_RF, ERP, TAX = 0.0425, 0.05, 0.21


# ---------------------------------------------------------------- frames
def _qpath(root, tax, concept, unit, period):
    return Path(root) / 'cache' / 'qframes' / f'{tax}.{concept}.{unit}.{period}.json.gz'


def _read_gz(p):
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def instant_periods(n=13, today=None):
    return [p + 'I' for p in FR.calendar_quarters(n, today)]


def annual_periods(today=None):
    years = FR.calendar_years(FR.calendar_quarters(24, today))
    return [y for y in years if int(y[2:]) >= 2020]


def collect(client, root, minutes=20, refresh_days=3, today=None):
    """Fetch the missing frames (the recent periods again every few days while late filers report)."""
    root = Path(root)
    t0 = time.time()
    state_p = root / 'cache' / 'qframes' / 'state.json'
    state = read_json(state_p, {})
    inst, ann = instant_periods(13, today), annual_periods(today)
    recent = set(inst[-2:]) | set(ann[-2:])
    fresh_after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=refresh_days)).isoformat()
    jobs = [(spec, p, False) for _, specs in INSTANT for spec in specs for p in inst]
    jobs += [(spec, p, True) for _, specs in ANNUAL for spec in specs for p in ann]
    fetched = errors = skipped = 0
    for (tax, concept, unit), period, annual in jobs:
        key = f'{tax}.{concept}.{unit}.{period}'
        p = _qpath(root, tax, concept, unit, period)
        when = state.get(key)
        if p.exists() and (period not in recent or (when and when > fresh_after)):
            continue
        if time.time() - t0 > minutes * 60:
            skipped += 1
            continue
        try:
            body = client.json(API.format(tax=tax, concept=concept, unit=unit, period=period), sec=True)
            rows = [r for r in body.get('data', []) if r.get('val') is not None]
            vals = ({str(r['cik']): [r['val'], r.get('end')] for r in rows} if annual else {str(r['cik']): r['val'] for r in rows})
        except Exception as exc:                          # noqa: BLE001
            if 'HTTP 404' in str(exc):
                vals = {}
            else:
                errors += 1
                print(f'quality frames {key}: {str(exc)[:160]}', flush=True)
                continue
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.tmp')
        with gzip.open(tmp, 'wt', encoding='utf-8') as f:
            json.dump(vals, f, separators=(',', ':'))
        tmp.replace(p)
        state[key] = now()
        fetched += 1
    write_json(state_p, state)
    return {'status': 'ok' if not errors and not skipped else 'partial', 'fetched': fetched, 'errors': errors,
            'left_for_next_run': skipped, 'seconds': round(time.time() - t0)}


# ---------------------------------------------------------------- the panel
def fiscal_years(root, hub_root, today=None):
    """{cik: [record, …]} oldest first: one record per fiscal year (its end date), flows from the annual frames and the
    balance sheet at the calendar quarter end nearest the fiscal year end."""
    out = {}

    def put(cik, end, field, val):
        if end is None or val is None:
            return
        rec = out.setdefault(cik, {}).setdefault(end, {'end': end})
        rec.setdefault(field, val)                       # the first concept in the preference order wins

    ann = annual_periods(today)
    for field, concepts in HUB_ANNUAL:
        for concept in concepts:
            for y in ann:
                for cik, row in FR.load(hub_root, concept, y).items():
                    if isinstance(row, list) and len(row) == 2:
                        put(cik, row[1], field, row[0])
    for field, specs in ANNUAL:
        for tax, concept, unit in specs:
            for y in ann:
                for cik, row in _read_gz(_qpath(root, tax, concept, unit, y)).items():
                    if isinstance(row, list) and len(row) == 2:
                        put(cik, row[1], field, row[0])
    inst = {}
    for field, specs in INSTANT:
        for tax, concept, unit in specs:
            for p in instant_periods(13, today):
                for cik, v in _read_gz(_qpath(root, tax, concept, unit, p)).items():
                    inst.setdefault(cik, {}).setdefault(p[:-1], {}).setdefault(field, v)
    res = {}
    for cik, by_end in out.items():
        recs = []
        for end in sorted(by_end):
            r = dict(by_end[end])
            try:
                q = FR._quarter_of(end)
            except ValueError:
                continue
            bs = (inst.get(cik) or {}).get(q) or {}
            for k, v in bs.items():
                r.setdefault(k, v)
            if r.get('ltd') is None and (r.get('ltd_nc') is not None or r.get('ltd_c') is not None):
                r['ltd'] = (r.get('ltd_nc') or 0) + (r.get('ltd_c') or 0)
            if r.get('liab') is None and r.get('assets') is not None and r.get('eq') is not None:
                r['liab'] = r['assets'] - r['eq']
            if r.get('gp') is None and r.get('rev') is not None and r.get('cogs') is not None:
                r['gp'] = r['rev'] - r['cogs']
            recs.append(r)
        # an annual frame row for a 52/53-week year can sit a few days from the instant; drop near-duplicates
        clean = []
        for r in recs:
            if clean and (dt.date.fromisoformat(r['end']) - dt.date.fromisoformat(clean[-1]['end'])).days < 300:
                clean[-1] = {**clean[-1], **{k: v for k, v in r.items() if v is not None}}
                continue
            clean.append(r)
        if clean:
            res[cik] = clean
    return res


def latest_instant(root, cik, field, today=None):
    """The newest balance-sheet value of a field (e.g. shares outstanding) and its quarter."""
    for tax, concept, unit in dict(INSTANT)[field]:
        for p in reversed(instant_periods(13, today)):
            v = _read_gz(_qpath(root, tax, concept, unit, p)).get(str(cik))
            if v is not None:
                return v, p[:-1]
    return None, None


def instants(root, field, today=None):
    """{period: {cik: value}} for one balance-sheet field over the last 13 quarter ends."""
    out = {}
    for tax, concept, unit in dict(INSTANT)[field]:
        for p in instant_periods(13, today):
            for cik, v in _read_gz(_qpath(root, tax, concept, unit, p)).items():
                out.setdefault(p[:-1], {}).setdefault(cik, v)
    return out


def quarter_end(period):
    y, q = int(period[2:6]), int(period[-1])
    return (dt.date(y, 3 * q, 1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)


# ---------------------------------------------------------------- prices
def load_prices(folder, tickers):
    """{ticker: (dates, closes)} from the hub's price cache (cache/prices/<T>.json.gz rows [date, close, volume])."""
    out = {}
    for t in tickers:
        p = Path(folder) / f'{t}.json.gz'
        if not p.exists():
            continue
        rows = (_read_gz(p) or {}).get('rows') or []
        rows = [r for r in rows if len(r) > 1 and r[1]]
        if len(rows) >= 40:
            out[t] = ([r[0] for r in rows], [float(r[1]) for r in rows])
    return out


def price_at(px, day):
    """The last close on or before a date (None before the series starts)."""
    dates, closes = px
    i = bisect.bisect_right(dates, day) - 1
    return closes[i] if i >= 0 else None


def month_ends(dates, start):
    out, last = [], None
    for d in dates:
        if d < start:
            continue
        if last and d[:7] != last[:7]:
            out.append(last)
        last = d
    if last:
        out.append(last)
    return out


def weekly_returns(px, end, weeks=104):
    dates, closes = px
    i = bisect.bisect_right(dates, end) - 1
    pts = []
    while i >= 0 and len(pts) <= weeks:
        pts.append(closes[i])
        i -= 5
    pts = pts[::-1]
    return [pts[k] / pts[k - 1] - 1 for k in range(1, len(pts)) if pts[k - 1]]


def beta(px, spy, end):
    a, b = weekly_returns(px, end), weekly_returns(spy, end)
    n = min(len(a), len(b))
    if n < 40:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    var = sum((x - mb) ** 2 for x in b)
    if not var:
        return None
    raw = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / var
    return round(min(3.0, max(0.3, 0.67 * raw + 0.33)), 3)          # Blume-adjusted, bounded


# ---------------------------------------------------------------- the scores
def _div(a, b):
    try:
        return None if a is None or b in (None, 0) else a / b
    except (TypeError, ZeroDivisionError):
        return None


def _r(v, d=4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, d)


def piotroski(cur, prev, prev2=None):
    """Piotroski (2000): nine pass / fail checks on the latest fiscal year against the one before."""
    a0, a1 = cur.get('assets'), prev.get('assets')
    a2 = (prev2 or {}).get('assets')
    roa = _div(cur.get('ni'), a1 or a0)
    roa_p = _div(prev.get('ni'), a2 or a1)
    cfo = _div(cur.get('ocf'), a1 or a0)
    lev, lev_p = _div(cur.get('ltd') or 0, a0), _div(prev.get('ltd') or 0, a1)
    cr, cr_p = _div(cur.get('ca'), cur.get('cl')), _div(prev.get('ca'), prev.get('cl'))
    sh, sh_p = cur.get('dil') or cur.get('so'), prev.get('dil') or prev.get('so')
    gm, gm_p = _div(cur.get('gp'), cur.get('rev')), _div(prev.get('gp'), prev.get('rev'))
    at, at_p = _div(cur.get('rev'), a1 or a0), _div(prev.get('rev'), a2 or a1)

    def chk(key, label, ok, detail):
        return {'key': key, 'label': label, 'pass': ok, 'detail': detail}
    sig = [
        chk('roa', 'Positive return on assets', None if roa is None else roa > 0, _r(roa)),
        chk('cfo', 'Positive operating cash flow', None if cur.get('ocf') is None else cur['ocf'] > 0, _r(cfo)),
        chk('droa', 'Return on assets up on the year', None if roa is None or roa_p is None else roa > roa_p, [_r(roa_p), _r(roa)]),
        chk('accrual', 'Cash flow above net income (low accruals)', None if cfo is None or roa is None else cfo > roa, [_r(cfo), _r(roa)]),
        chk('lev', 'Long-term debt / assets down', None if lev is None or lev_p is None or a0 is None or a1 is None else lev <= lev_p, [_r(lev_p), _r(lev)]),
        chk('liq', 'Current ratio up', None if cr is None or cr_p is None else cr > cr_p, [_r(cr_p, 3), _r(cr, 3)]),
        chk('shares', 'No new shares issued', None if not sh or not sh_p else sh <= sh_p * 1.005, [sh_p, sh]),
        chk('gm', 'Gross margin up', None if gm is None or gm_p is None else gm > gm_p, [_r(gm_p), _r(gm)]),
        chk('turn', 'Asset turnover up', None if at is None or at_p is None else at > at_p, [_r(at_p), _r(at)]),
    ]
    n = sum(s['pass'] is not None for s in sig)
    return {'score': sum(bool(s['pass']) for s in sig), 'n': n, 'signals': sig}


def altman(cur, mcap, manufacturer):
    """Altman Z (1968) for manufacturers, Z'' (1995) for other non-financial companies; zones as published."""
    ta, tl = cur.get('assets'), cur.get('liab')
    if not ta or not tl or cur.get('ca') is None or cur.get('cl') is None:
        return None
    wc = (cur['ca'] - cur['cl']) / ta
    re_ = (cur.get('re') or 0) / ta
    ebit = (cur.get('oi') if cur.get('oi') is not None else None)
    if ebit is None:
        return None
    ebit /= ta
    if manufacturer:
        if not mcap:
            return None
        parts = {'wc_ta': wc, 're_ta': re_, 'ebit_ta': ebit, 'mve_tl': mcap / tl, 'sales_ta': (cur.get('rev') or 0) / ta}
        z = 1.2 * wc + 1.4 * re_ + 3.3 * ebit + 0.6 * parts['mve_tl'] + 1.0 * parts['sales_ta']
        zone = 'safe' if z > 2.99 else 'grey' if z >= 1.81 else 'distress'
        model = 'Z'
    else:
        if cur.get('eq') is None:
            return None
        parts = {'wc_ta': wc, 're_ta': re_, 'ebit_ta': ebit, 'bve_tl': cur['eq'] / tl}
        z = 6.56 * wc + 3.26 * re_ + 6.72 * ebit + 1.05 * parts['bve_tl']
        zone = 'safe' if z > 2.6 else 'grey' if z >= 1.1 else 'distress'
        model = "Z''"
    return {'z': _r(z, 3), 'model': model, 'zone': zone, 'parts': {k: _r(v) for k, v in parts.items()}}


def beneish(cur, prev):
    """Beneish (1999) eight-variable M-score; above −1.78 screens as a possible earnings manipulator. Indices that need
    a figure the company does not tag (SG&A, depreciation) are set to 1 (neutral) and listed."""
    need = ('ar', 'rev', 'gp', 'assets', 'ca', 'ppe', 'ni', 'ocf')
    # every figure must be tagged (net income and cash flow may be zero); the divisors must not be zero
    if any(cur.get(k) is None for k in need) or any(prev.get(k) is None for k in need[:6]):
        return None
    if any(not cur.get(k) for k in ('rev', 'assets')) or any(not prev.get(k) for k in ('rev', 'assets')):
        return None
    neutral = []
    dsri = _div(cur['ar'] / cur['rev'], prev['ar'] / prev['rev'])
    gmi = _div(prev['gp'] / prev['rev'], cur['gp'] / cur['rev'])
    aqi = _div(1 - (cur['ca'] + cur['ppe']) / cur['assets'], 1 - (prev['ca'] + prev['ppe']) / prev['assets'])
    sgi = cur['rev'] / prev['rev']
    if cur.get('da') and prev.get('da'):
        depi = _div(prev['da'] / (prev['da'] + prev['ppe']), cur['da'] / (cur['da'] + cur['ppe']))
    else:
        depi = 1.0
        neutral.append('depi')
    if cur.get('sga') and prev.get('sga'):
        sgai = _div(cur['sga'] / cur['rev'], prev['sga'] / prev['rev'])
    else:
        sgai = 1.0
        neutral.append('sgai')
    if cur.get('cl') is not None and prev.get('cl') is not None:
        lvgi = _div((cur['cl'] + (cur.get('ltd') or 0)) / cur['assets'], (prev['cl'] + (prev.get('ltd') or 0)) / prev['assets'])
    else:
        lvgi = 1.0
        neutral.append('lvgi')
    tata = (cur['ni'] - cur['ocf']) / cur['assets']
    idx = {'dsri': dsri, 'gmi': gmi, 'aqi': aqi, 'sgi': sgi, 'depi': depi, 'sgai': sgai, 'lvgi': lvgi, 'tata': tata}
    if any(v is None or not math.isfinite(v) for v in idx.values()):
        return None
    m = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
    return {'m': _r(m, 3), 'flag': m > -1.78, 'idx': {k: _r(v, 3) for k, v in idx.items()}, 'neutral': neutral}


def yields(cur, mcap):
    """Shareholder yield (dividends + buybacks − new stock sold) and FCF yield before / after stock compensation."""
    if not mcap:
        return {}
    div, bb, iss = cur.get('div') or 0, cur.get('buyback') or 0, cur.get('issue') or 0
    fcf = (cur['ocf'] - (cur.get('capex') or 0)) if cur.get('ocf') is not None else None
    out = {'div_y': div / mcap, 'bb_y': (bb - iss) / mcap, 'sy': (div + bb - iss) / mcap}
    if fcf is not None:
        out['fcf'] = fcf
        out['fcf_y'] = fcf / mcap
        if cur.get('sbc') is not None:
            out['sbc'] = cur['sbc']
            out['fcf_sbc_y'] = (fcf - cur['sbc']) / mcap
    return {k: (_r(v, 5) if k.endswith('_y') or k == 'sy' else v) for k, v in out.items()}


def owner_earnings(recs):
    """Buffett's owner earnings with Greenwald's maintenance capex: growth capex = (PP&E / sales, averaged over the years
    on file) × the year's sales growth; maintenance = capex − growth capex (between 0 and capex)."""
    cur = recs[-1]
    if cur.get('ni') is None or cur.get('capex') is None:
        return None
    ratios = [r['ppe'] / r['rev'] for r in recs[-5:] if r.get('ppe') and r.get('rev')]
    prev = recs[-2] if len(recs) > 1 else None
    if not ratios or not prev or not prev.get('rev') or not cur.get('rev'):
        return None
    ppe_s = sum(ratios) / len(ratios)
    growth_capex = ppe_s * max(cur['rev'] - prev['rev'], 0)
    maint = min(max(cur['capex'] - growth_capex, 0), cur['capex'])
    oe = cur['ni'] + (cur.get('da') or 0) - maint
    return {'oe': oe, 'maint_capex': maint, 'growth_capex': growth_capex, 'ppe_sales': _r(ppe_s), 'da': cur.get('da'), 'ni': cur['ni']}


def invested(r):
    if r.get('eq') is None:
        return None
    return r['eq'] + (r.get('ltd') or 0) - (r.get('cash') or 0)


def tax_rate(r):
    t = _div(r.get('tax'), r.get('pretax'))
    return TAX if t is None or not 0 <= t <= 0.4 else t


def roic(recs):
    cur = recs[-1]
    if cur.get('oi') is None:
        return None
    nopat = cur['oi'] * (1 - tax_rate(cur))
    ic0 = invested(cur)
    ic1 = invested(recs[-2]) if len(recs) > 1 else None
    base = (ic0 + ic1) / 2 if ic0 is not None and ic1 is not None else ic0
    if not base or base <= 0:
        return None
    out = {'roic': _r(nopat / base), 'nopat': nopat, 'ic': ic0, 'tax_rate': _r(tax_rate(cur), 3)}
    old = recs[-3] if len(recs) > 2 else (recs[-2] if len(recs) > 1 else None)
    if old and old.get('oi') is not None and invested(old) is not None:
        d_ic = ic0 - invested(old)
        d_nopat = nopat - old['oi'] * (1 - tax_rate(old))
        if ic0 and d_ic > 0.02 * abs(ic0):
            out['roic_inc'] = _r(d_nopat / d_ic)
            out['inc_years'] = (dt.date.fromisoformat(cur['end']) - dt.date.fromisoformat(old['end'])).days // 360
    return out


def wacc(cur, mcap, b, rf):
    """A simple CAPM WACC: cost of equity rf + β × 5% equity risk premium (β from two years of weekly returns against
    SPY, Blume-adjusted); cost of debt = interest / debt (between rf + 0.5% and rf + 10%; rf + 2% when not tagged),
    after a 21% tax; weights: market cap and book debt."""
    if not mcap or b is None:
        return None
    debt = cur.get('ltd') or 0
    ke = rf + b * ERP
    kd = _div(cur.get('interest'), debt) if debt else None
    kd = rf + 0.02 if kd is None else min(max(kd, rf + 0.005), rf + 0.10)
    w = mcap / (mcap + debt)
    return {'wacc': _r(w * ke + (1 - w) * kd * (1 - TAX)), 'beta': b, 'ke': _r(ke), 'kd': _r(kd), 'w_equity': _r(w, 3), 'rf': rf, 'source': 'capm'}


def cost_structure(quarters):
    """Fixed and variable costs from the quarters on file: operating cost (revenue − operating income) regressed on
    revenue; DOL = contribution / operating income at the latest quarter."""
    pts = [(q['rev'], q['rev'] - q['oi']) for q in quarters if q.get('rev') and q.get('oi') is not None]
    if len(pts) < 8:
        return None
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if not sxx:
        return None
    v = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    f = my - v * mx
    ss = sum((p[1] - my) ** 2 for p in pts)
    r2 = 1 - sum((p[1] - (f + v * p[0])) ** 2 for p in pts) / ss if ss else None
    rev, oi = pts[-1][0], quarters[-1].get('oi')
    contrib = rev * (1 - v)
    dol = contrib / oi if oi and oi > 0 else None
    ok = 0 <= v <= 1.2 and f > 0 and r2 is not None and r2 >= 0.5 and dol is not None and 0 < dol < 50
    return {'fixed_q': f, 'var_ratio': _r(v, 4), 'r2': _r(r2, 3), 'dol': _r(dol, 2), 'reliable': bool(ok), 'n': n,
            'points': [[round(a), round(b)] for a, b in pts]}


def company_metrics(recs, mcap, manufacturer, financial, b=None, rf=DEFAULT_RF):
    """Every score for the latest fiscal year in recs (oldest first; needs the year before for most of them)."""
    cur = recs[-1]
    prev = recs[-2] if len(recs) > 1 else None
    prev2 = recs[-3] if len(recs) > 2 else None
    out = {'fy_end': cur['end']}
    if prev and not financial:
        out['piotroski'] = piotroski(cur, prev, prev2)
        out['beneish'] = beneish(cur, prev)
    if not financial:
        out['altman'] = altman(cur, mcap, manufacturer)
    out['yields'] = yields(cur, mcap)
    out['owner'] = owner_earnings(recs) if not financial else None
    out['roic'] = roic(recs) if not financial else None
    out['wacc'] = wacc(cur, mcap, b, rf)
    if out['roic'] and out['wacc']:
        out['spread'] = _r(out['roic']['roic'] - out['wacc']['wacc'])
    if prev:
        a0, a1 = cur.get('assets'), prev.get('assets')
        if a0 and a1 and cur.get('ni') is not None and cur.get('ocf') is not None:
            out['accruals'] = _r((cur['ni'] - cur['ocf']) / ((a0 + a1) / 2))
        if a0 and a1:
            out['asset_g'] = _r(a0 / a1 - 1)
        s0, s1 = cur.get('dil') or cur.get('so'), prev.get('dil') or prev.get('so')
        if s0 and s1:
            out['net_iss'] = _r(s0 / s1 - 1)
    if cur.get('gp') is not None and cur.get('assets'):
        out['gp_a'] = _r(cur['gp'] / cur['assets'])
    return out


# ---------------------------------------------------------------- cross-section
def ols(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss = sum((y - my) ** 2 for y in ys)
    r2 = 1 - sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / ss if ss else None
    return a, b, r2


def ttm(qs, i):
    """Trailing four quarters ending at index i of a consecutive quarter list (None when one is missing)."""
    if i < 3:
        return None
    w = qs[i - 3:i + 1]
    periods = [p for p, _ in w]
    for k in range(1, 4):
        if FR._shift(periods[k - 1], 1) != periods[k]:
            return None
    rev = [f.get('rev') for _, f in w]
    oi = [f.get('oi') for _, f in w]
    if any(v is None for v in rev):
        return None
    return {'rev': sum(rev), 'oi': None if any(v is None for v in oi) else sum(oi), 'end': periods[-1]}


def growth_line(points, min_n=8):
    """log(EV/Sales) = a + b × (revenue growth % + operating margin %) per sector; residual < 0 = cheaper than peers with
    the same growth and margin."""
    pts = [p for p in points if p['ev_s'] and p['ev_s'] > 0 and p['r40'] is not None]
    if len(pts) < min_n:
        return None
    xs = [max(-100.0, min(150.0, p['r40'])) for p in pts]
    ys = [math.log(p['ev_s']) for p in pts]
    fit = ols(xs, ys)
    if not fit:
        return None
    a, b, r2 = fit
    for p, x, y in zip(pts, xs, ys):
        p['line_ev_s'] = round(math.exp(a + b * x), 3)
        p['resid'] = round(y - (a + b * x), 4)
    return {'a': round(a, 5), 'b': round(b, 6), 'r2': _r(r2, 3), 'n': len(pts)}


def spearman(a, b):
    n = len(a)
    if n < 10:
        return None

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


FACTORS = [  # key, label, sign (+1: higher is better)
    ('f_score', 'Piotroski F-score', 1), ('gp_a', 'Gross profit / assets', 1), ('accruals', 'Accruals (low)', -1),
    ('asset_g', 'Asset growth (low)', -1), ('net_iss', 'Net share issuance (low)', -1), ('sy', 'Shareholder yield', 1),
    ('fcf_sbc_y', 'FCF yield after stock comp', 1), ('resid', 'Cheap vs the growth-adjusted line', -1),
]


def pct_ranks(vals):
    """{key: percentile 0..1} for a {key: value} map (ties averaged)."""
    keys = sorted(vals, key=lambda k: vals[k])
    n = len(keys)
    if n < 2:
        return {k: 0.5 for k in keys}
    out, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and vals[keys[j + 1]] == vals[keys[i]]:
            j += 1
        for k in range(i, j + 1):
            out[keys[k]] = ((i + j) / 2) / (n - 1)
        i = j + 1
    return out


def composite(rows):
    """{ticker: score 0..1}: the mean of the factor percentiles a company has (signed so higher is better), at least
    four; equal weights fixed in advance (nothing fitted, so the walk-forward record has no look-ahead)."""
    per = {}
    for key, _, sign in FACTORS:
        vals = {t: sign * r[key] for t, r in rows.items() if r.get(key) is not None}
        for t, p in pct_ranks(vals).items():
            per.setdefault(t, []).append(p)
    return {t: sum(v) / len(v) for t, v in per.items() if len(v) >= 4}


def factor_test(monthly):
    """monthly: [(month, {ticker: {factor values…, 'ret': next-month return}})] → per factor and the composite: monthly
    rank IC, top − bottom quintile spread, their means, t-stat and hit rate, cumulative long-short."""
    out = {}
    keys = [(k, l, s) for k, l, s in FACTORS] + [('composite', 'Composite (equal-weight percentiles)', 1)]
    for key, label, sign in keys:
        ics, spreads, cum, series = [], [], 1.0, []
        for month, rows in monthly:
            xs = [(sign * r[key], r['ret']) for r in rows.values() if r.get(key) is not None and r.get('ret') is not None]
            if len(xs) < 30:
                continue
            ic = spearman([x for x, _ in xs], [y for _, y in xs])
            xs.sort()
            k = len(xs) // 5
            spread = sum(y for _, y in xs[-k:]) / k - sum(y for _, y in xs[:k]) / k
            if ic is None:
                continue
            ics.append(ic)
            spreads.append(spread)
            cum *= 1 + spread
            series.append([month, round(ic, 4), round(spread, 5), round(cum - 1, 4), len(xs)])
        if not ics:
            out[key] = {'label': label, 'months': 0, 'series': []}
            continue
        n = len(ics)
        m = sum(ics) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in ics) / (n - 1)) if n > 1 else None
        out[key] = {'label': label, 'months': n, 'mean_ic': round(m, 4), 't': round(m / sd * math.sqrt(n), 2) if sd else None,
                    'hit': round(sum(x > 0 for x in ics) / n, 3), 'mean_spread': round(sum(spreads) / n, 5),
                    'cum_spread': round(cum - 1, 4), 'series': series}
    return out


def margin_reversion(qfig, sector_of, min_pairs=150):
    """Operating margins (trailing four quarters) drift back toward their sector's median: φ from pooled one-quarter
    pairs of (margin − sector median), estimated walk-forward; half-life in quarters; out-of-sample error against
    'no change'. Returns (stats per sector, forecasts per cik for the next four quarters)."""
    series = {}
    for cik, per in qfig.items():
        qs = sorted(per.items())
        for i in range(len(qs)):
            t = ttm(qs, i)
            if t and t['oi'] is not None and t['rev'] > 0:
                series.setdefault(cik, {})[t['end']] = max(-1.0, min(1.0, t['oi'] / t['rev']))
    by_q = {}
    for cik, s in series.items():
        sec = sector_of(cik)
        for q, m in s.items():
            by_q.setdefault((sec, q), []).append(m)
    med = {k: sorted(v)[len(v) // 2] for k, v in by_q.items() if len(v) >= 5}
    pairs = {}
    for cik, s in series.items():
        sec = sector_of(cik)
        for q, m in s.items():
            q2 = FR._shift(q, 1)
            if q2 in s and (sec, q) in med and (sec, q2) in med:
                d0, d1 = m - med[(sec, q)], s[q2] - med[(sec, q2)]
                pairs.setdefault(sec, []).append((q, d0, d1))
    allp = [p for v in pairs.values() for p in v]

    def phi(ps):
        num = sum(d0 * d1 for _, d0, d1 in ps)
        den = sum(d0 * d0 for _, d0, _ in ps)
        return min(0.999, max(0.0, num / den)) if den else None
    stats = {}
    for sec in sorted(set(list(pairs) + ['_all'])):
        ps = allp if sec == '_all' else pairs.get(sec, [])
        use = ps if len(ps) >= min_pairs else allp
        f = phi(use)
        quarters = sorted({q for q, _, _ in use})
        e_model = e_naive = n = 0
        for q in quarters[4:]:                            # walk-forward: φ from pairs that ended before q
            past = [p for p in use if FR._shift(p[0], 1) <= q and p[0] < q]
            fp = phi(past)
            if fp is None:
                continue
            for qq, d0, d1 in use:
                if qq == q:
                    e_model += abs(d1 - fp * d0)
                    e_naive += abs(d1 - d0)
                    n += 1
        stats[sec] = {'phi': _r(f, 3), 'half_life_q': _r(math.log(0.5) / math.log(f), 1) if f and 0 < f < 1 else None,
                      'pairs': len(use), 'own_pairs': len(ps) >= min_pairs, 'oos_n': n,
                      'oos_mae': _r(e_model / n, 4) if n else None, 'naive_mae': _r(e_naive / n, 4) if n else None}
    fc = {}
    for cik, s in series.items():
        sec = sector_of(cik)
        q = max(s)
        if (sec, q) not in med:
            continue
        st = stats.get(sec) if sec in stats else stats['_all']
        f = st['phi'] if st and st['phi'] is not None else None
        if f is None:
            continue
        d = s[q] - med[(sec, q)]
        fc[cik] = {'q': q, 'margin': _r(s[q]), 'sector_median': _r(med[(sec, q)]), 'phi': f,
                   'path': [_r(med[(sec, q)] + d * f ** h) for h in range(1, 5)],
                   'history': [[k, _r(v)] for k, v in sorted(s.items())[-12:]]}
    return stats, fc


# ---------------------------------------------------------------- build
def _sector_info(site_index):
    ix = read_json(site_index, {}) if site_index else {}
    rows = ix.get('companies') if isinstance(ix, dict) else ix
    out = {}
    for r in rows or []:
        try:
            out[str(int(r['cik']))] = r
        except (KeyError, TypeError, ValueError):
            continue
    return out, (ix.get('sector_names') if isinstance(ix, dict) else None) or {}


def _tickers(prices):
    st = read_json(Path(prices) / 'sec-tickers.json', {})
    by_cik = {}
    for r in st.get('rows') or []:
        if r.get('cik') and r.get('ticker'):
            by_cik.setdefault(str(int(r['cik'])), (r['ticker'].upper().replace('.', '-'), r.get('title') or ''))
    return by_cik


def _risk_free(rates_path):
    d = read_json(rates_path, {}) if rates_path else {}
    last = ((d.get('series') or {}).get('DGS10') or {}).get('last')
    if last and last[1] is not None:
        v = float(last[1])
        return v / 100 if v > 1 else v
    return DEFAULT_RF


def _valuation_wacc(folder):
    """WACC per ticker from workstream B's research/valuation (index.json: fields + rows with ticker and wacc), if any."""
    if not folder:
        return {}
    d = read_json(Path(folder) / 'index.json', {})
    F = d.get('fields') or []
    if 'ticker' not in F or 'wacc' not in F:
        return {}
    i, j = F.index('ticker'), F.index('wacc')
    return {str(r[i]).upper(): r[j] for r in d.get('rows') or [] if r[j] is not None}


def build(root, hub_root, prices, site_index=None, valuation=None, rates=None, today=None, out=None):
    root, out = Path(root), Path(out or Path(root) / 'public')
    t0 = time.time()
    today = today or dt.date.today()
    info, sector_names = _sector_info(site_index)
    names = _tickers(prices)
    fys = fiscal_years(root, hub_root, today)
    periods = FR.calendar_quarters(17, today)
    qfig = FR.figures(hub_root, periods)
    so_hist = instants(root, 'so', today)
    tick = {cik: names[cik][0] for cik in set(fys) | set(qfig) if cik in names}
    px = load_prices(prices, sorted(set(tick.values()) | {'SPY'}))
    spy = px.get('SPY')
    rf = _risk_free(rates)
    vw = _valuation_wacc(valuation)

    def sector_of(cik):
        return (info.get(cik) or {}).get('sector') or 'other'

    def sic_of(cik):
        try:
            return int((info.get(cik) or {}).get('sic') or 0)
        except ValueError:
            return 0

    def shares_now(cik, recs):
        for p in sorted(so_hist, reverse=True)[:3]:
            v = so_hist[p].get(cik)
            if v:
                return v
        return (recs[-1].get('dil') if recs else None) or None

    # -------- current metrics
    rows, comp, points = {}, {}, {}
    last_day = max((p[0][-1] for p in px.values()), default=today.isoformat())
    for cik, t in tick.items():
        recs = fys.get(cik) or []
        if t not in px or not recs:
            continue
        price = px[t][1][-1]
        sh = shares_now(cik, recs)
        mcap = price * sh if sh else None
        if not mcap or mcap < MIN_MCAP:
            continue
        sec = sector_of(cik)
        fin = sec in FIN_SECTORS
        man = 2000 <= sic_of(cik) <= 3999
        b = beta(px[t], spy, last_day) if spy else None
        m = company_metrics(recs, mcap, man, fin, b, rf)
        if t in vw and m.get('wacc'):
            m['wacc'] = {**m['wacc'], 'wacc': vw[t], 'source': 'research/valuation'}
            if m.get('roic'):
                m['spread'] = _r(m['roic']['roic'] - vw[t])
        qs = sorted((qfig.get(cik) or {}).items())
        t_now = ttm(qs, len(qs) - 1) if qs else None
        t_ago = None
        if t_now:
            back = FR._shift(t_now['end'], -4)
            idx = next((i for i, (p, _) in enumerate(qs) if p == back), None)
            t_ago = ttm(qs, idx) if idx is not None else None
        cs = cost_structure([f for _, f in qs[-12:]])
        debt, cash = recs[-1].get('ltd') or 0, recs[-1].get('cash') or 0
        ev = mcap + debt - cash
        growth = (t_now['rev'] / t_ago['rev'] - 1) if t_now and t_ago and t_ago['rev'] > 0 else None
        margin = (t_now['oi'] / t_now['rev']) if t_now and t_now['oi'] is not None and t_now['rev'] > 0 else None
        ev_s = ev / t_now['rev'] if t_now and t_now['rev'] > 0 and ev > 0 else None
        r40 = (growth * 100 + margin * 100) if growth is not None and margin is not None else None
        name = (info.get(cik) or {}).get('name') or names[cik][1]
        row = {'ticker': t, 'cik': int(cik), 'name': name, 'sector': sec, 'mcap': round(mcap), 'price': round(price, 2),
               'f_score': (m.get('piotroski') or {}).get('score') if (m.get('piotroski') or {}).get('n') == 9 else None,
               'f_n': (m.get('piotroski') or {}).get('n'),
               'z': (m.get('altman') or {}).get('z'), 'z_model': (m.get('altman') or {}).get('model'), 'z_zone': (m.get('altman') or {}).get('zone'),
               'm_score': (m.get('beneish') or {}).get('m'), 'm_flag': (m.get('beneish') or {}).get('flag'),
               'sy': m['yields'].get('sy'), 'div_y': m['yields'].get('div_y'), 'bb_y': m['yields'].get('bb_y'),
               'fcf_y': m['yields'].get('fcf_y'), 'fcf_sbc_y': m['yields'].get('fcf_sbc_y'),
               'oe_y': _r(m['owner']['oe'] / mcap, 5) if m.get('owner') else None,
               'roic': (m.get('roic') or {}).get('roic'), 'roic_inc': (m.get('roic') or {}).get('roic_inc'),
               'wacc': (m.get('wacc') or {}).get('wacc'), 'spread': m.get('spread'),
               'dol': cs['dol'] if cs and cs['reliable'] else None, 'fixed_q': round(cs['fixed_q']) if cs and cs['reliable'] else None,
               'var_ratio': cs['var_ratio'] if cs and cs['reliable'] else None,
               'accruals': m.get('accruals'), 'gp_a': m.get('gp_a'), 'asset_g': m.get('asset_g'), 'net_iss': m.get('net_iss'),
               'ev_s': _r(ev_s, 3), 'growth': _r(growth), 'margin': _r(margin), 'r40': _r(r40, 2), 'fy_end': m['fy_end']}
        rows[t] = row
        comp[t] = {'metrics': m, 'cost': cs, 'records': recs[-5:], 'ttm': t_now, 'ttm_year_ago': t_ago, 'ev': round(ev),
                   'debt': debt, 'cash': cash, 'shares': sh}
        points.setdefault(sec, []).append(row)
    lines = {}
    for sec, pts in points.items():
        tmp = [{'t': r['ticker'], 'ev_s': r['ev_s'], 'r40': r['r40']} for r in pts]
        fit = growth_line(tmp)
        if not fit:
            continue
        lines[sec] = fit
        for p in tmp:
            if 'resid' in p:
                rows[p['t']]['resid'] = p['resid']
                rows[p['t']]['line_ev_s'] = p['line_ev_s']
    scores = composite(rows)
    ranks = pct_ranks(scores)
    for t, s in scores.items():
        rows[t]['composite'] = round(s, 4)
        rows[t]['comp_rank'] = round(ranks[t], 4)
    mstats, mfc = margin_reversion(qfig, sector_of)
    for cik, f in mfc.items():
        t = tick.get(cik)
        if t in rows:
            rows[t]['margin_fc4'] = f['path'][-1]
            comp[t]['margins'] = f

    # -------- walk-forward factor history
    monthly = backtest(fys, qfig, so_hist, tick, px, sector_of, info)
    ftest = factor_test(monthly)
    ledger = update_ledger(root, rows, px, last_day)

    # -------- publish
    out.mkdir(parents=True, exist_ok=True)
    fields = ['ticker', 'cik', 'name', 'sector', 'mcap', 'price', 'f_score', 'f_n', 'z', 'z_model', 'z_zone', 'm_score', 'm_flag', 'sy',
              'div_y', 'bb_y', 'fcf_y', 'fcf_sbc_y', 'oe_y', 'roic', 'roic_inc', 'wacc', 'spread', 'dol', 'fixed_q', 'var_ratio',
              'accruals', 'gp_a', 'asset_g', 'net_iss', 'ev_s', 'growth', 'margin', 'r40', 'resid', 'line_ev_s', 'composite',
              'comp_rank', 'margin_fc4', 'fy_end']
    srt = sorted(rows.values(), key=lambda r: -r['mcap'])
    write_json(out / 'index.json', {
        'generated_at': now(), 'asof': last_day, 'rf': rf, 'erp': ERP, 'min_mcap': MIN_MCAP, 'fields': fields,
        'rows': [[r.get(k) for k in fields] for r in srt], 'sector_names': sector_names, 'lines': lines,
        'note': ('Fundamentals: companies\' own XBRL tags via the SEC frames API (latest fiscal year; the balance sheet at the '
                 'calendar quarter end nearest the fiscal year end). Prices: daily closes. Piotroski F only when all nine checks '
                 'can be made. Altman and Beneish are left out for financial and real-estate companies. Beneish flag: M above '
                 '−1.78, a statistical screen, not an accusation. WACC: a simple CAPM unless research/valuation has one. '
                 'Not investment advice.')})
    cdir = out / 'c'
    cdir.mkdir(exist_ok=True)
    for t, c in comp.items():
        write_json(cdir / f'{t}.json', _clean({'ticker': t, 'row': rows[t], **c, 'line': lines.get(rows[t]['sector']),
                                              'sector_name': sector_names.get(rows[t]['sector'], rows[t]['sector'])}))
    write_json(out / 'scatter.json', {'generated_at': now(), 'lines': lines, 'sector_names': sector_names,
                                      'points': {sec: [[r['ticker'], r['r40'], r['ev_s'], r.get('resid'), r['mcap']]
                                                       for r in sorted(pts, key=lambda r: -r['mcap'])[:250] if r.get('resid') is not None]
                                                 for sec, pts in points.items()}})
    write_json(out / 'factors.json', {'generated_at': now(), 'factors': ftest, 'universe': f'US filers with market cap ≥ ${MIN_MCAP / 1e6:.0f}M',
                                      'note': ('Monthly walk-forward: each month-end, each factor from the figures public by then '
                                               '(fiscal year + 90 days, quarter + 45 days); next month\'s price return (no dividends). '
                                               'IC: rank correlation with that return; spread: top − bottom fifth.')})
    write_json(out / 'ledger.json', ledger)
    write_json(out / 'margins.json', {'generated_at': now(), 'sectors': mstats, 'sector_names': sector_names})
    status = {'built_at': now(), 'asof': last_day, 'companies': len(rows), 'fiscal_years': sum(len(v) for v in fys.values()),
              'piotroski_9': sum(1 for r in rows.values() if r['f_score'] == 9), 'distress': sum(1 for r in rows.values() if r['z_zone'] == 'distress'),
              'beneish_flags': sum(1 for r in rows.values() if r['m_flag']), 'factor_months': max((f.get('months', 0) for f in ftest.values()), default=0),
              'ledger_months': len(ledger.get('months') or {}), 'seconds': round(time.time() - t0)}
    write_json(out / 'status.json', status)
    return status


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 6)
    return o


def backtest(fys, qfig, so_hist, tick, px, sector_of, info, start='2022-07-01'):
    """[(month, {ticker: factors + next-month return})] from the first month the prices allow."""
    if not px:
        return []
    ref = max(px.values(), key=lambda p: len(p[0]))[0]
    months = month_ends(ref, start)
    fy_avail = {}
    for cik, recs in fys.items():
        lst = []
        for i, r in enumerate(recs):
            avail = (dt.date.fromisoformat(r['end']) + dt.timedelta(days=FY_LAG)).isoformat()
            lst.append((avail, i))
        fy_avail[cik] = lst
    qs_by = {cik: sorted(per.items()) for cik, per in qfig.items()}
    out = []
    for mi in range(len(months) - 1):
        m, nxt = months[mi], months[mi + 1]
        rows = {}
        for cik, t in tick.items():
            p = px.get(t)
            recs = fys.get(cik)
            if not p or not recs:
                continue
            p0, p1 = price_at(p, m), price_at(p, nxt)
            if not p0 or not p1:
                continue
            idx = [i for a, i in fy_avail[cik] if a <= m]
            if len(idx) < 2:
                continue
            cur, prev = recs[idx[-1]], recs[idx[-2]]
            sh = cur.get('dil') or cur.get('so')
            if not sh:
                continue
            mcap = p0 * sh
            if mcap < MIN_MCAP:
                continue
            r = {'ret': p1 / p0 - 1}
            if sector_of(cik) not in FIN_SECTORS:
                f = piotroski(cur, prev, recs[idx[-3]] if len(idx) > 2 else None)
                if f['n'] == 9:
                    r['f_score'] = f['score']
            y = yields(cur, mcap)
            r['sy'], r['fcf_sbc_y'] = y.get('sy'), y.get('fcf_sbc_y')
            a0, a1 = cur.get('assets'), prev.get('assets')
            if a0 and a1:
                r['asset_g'] = a0 / a1 - 1
                if cur.get('ni') is not None and cur.get('ocf') is not None:
                    r['accruals'] = (cur['ni'] - cur['ocf']) / ((a0 + a1) / 2)
            if cur.get('gp') is not None and a0:
                r['gp_a'] = cur['gp'] / a0
            s1 = prev.get('dil') or prev.get('so')
            if s1:
                r['net_iss'] = sh / s1 - 1
            qs = qs_by.get(cik) or []
            pub = [i for i, (pp, _) in enumerate(qs) if (quarter_end(pp) + dt.timedelta(days=Q_LAG)).isoformat() <= m]
            if pub:
                tn = ttm(qs, pub[-1])
                back = FR._shift(qs[pub[-1]][0], -4) if tn else None
                ib = next((i for i, (pp, _) in enumerate(qs) if pp == back), None) if back else None
                ta = ttm(qs, ib) if ib is not None else None
                if tn and ta and ta['rev'] > 0 and tn['rev'] > 0 and tn['oi'] is not None:
                    ev = mcap + (cur.get('ltd') or 0) - (cur.get('cash') or 0)
                    if ev > 0:
                        r['_ev_s'] = ev / tn['rev']
                        r['_r40'] = (tn['rev'] / ta['rev'] - 1) * 100 + tn['oi'] / tn['rev'] * 100
                        r['_sec'] = sector_of(cik)
            rows[t] = r
        by_sec = {}
        for t, r in rows.items():
            if '_ev_s' in r:
                by_sec.setdefault(r['_sec'], []).append({'t': t, 'ev_s': r['_ev_s'], 'r40': r['_r40']})
        for pts in by_sec.values():
            if growth_line(pts):
                for pnt in pts:
                    if 'resid' in pnt:
                        rows[pnt['t']]['resid'] = pnt['resid']
        for r in rows.values():
            for k in ('_ev_s', '_r40', '_sec'):
                r.pop(k, None)
        for t, s in composite(rows).items():
            if t in rows:
                rows[t]['composite'] = s
        if len(rows) >= 30:
            out.append((m[:7], rows))
    return out


def update_ledger(root, rows, px, last_day):
    """Freeze this month's composite ranking once (never changed afterwards); score every frozen month whose next
    month-end close is on file: rank IC and top − bottom decile return."""
    p = Path(root) / 'ledger' / 'composite.json'
    led = read_json(p, {'months': {}})
    month = last_day[:7]
    ranked = sorted((r for r in rows.values() if r.get('composite') is not None), key=lambda r: -r['composite'])
    if month not in led['months'] and len(ranked) >= 50:
        k = max(10, len(ranked) // 10)
        led['months'][month] = {'frozen_at': now(), 'price_date': last_day, 'n': len(ranked),
                                'ranks': {r['ticker']: r['comp_rank'] for r in ranked},
                                'top': [[r['ticker'], r['composite']] for r in ranked[:k]],
                                'bottom': [[r['ticker'], r['composite']] for r in ranked[-k:]]}
        write_json(p, led)
    summary = []
    for mo, e in sorted(led['months'].items()):
        res = None
        start = e['price_date']
        y, m_ = int(mo[:4]), int(mo[5:7])
        nxt = f'{y + (m_ == 12)}-{m_ % 12 + 1:02d}'
        tops, bots = {t for t, _ in e['top']}, {t for t, _ in e['bottom']}
        pairs, top_r, bot_r = [], [], []
        for t, rank in e['ranks'].items():
            if t not in px:
                continue
            dates = px[t][0]
            i = bisect.bisect_left(dates, nxt + '-32') - 1          # the last close of the next month
            if i < 0 or dates[i][:7] != nxt:
                continue
            p0, p1 = price_at(px[t], start), px[t][1][i]
            if not p0 or not p1:
                continue
            ret = p1 / p0 - 1
            pairs.append((rank, ret))
            if t in tops:
                top_r.append(ret)
            elif t in bots:
                bot_r.append(ret)
        if len(pairs) >= 30 and top_r and bot_r:
            ic = spearman([a for a, _ in pairs], [b for _, b in pairs])
            res = {'ic': _r(ic, 4), 'top': _r(sum(top_r) / len(top_r), 5), 'bottom': _r(sum(bot_r) / len(bot_r), 5),
                   'spread': _r(sum(top_r) / len(top_r) - sum(bot_r) / len(bot_r), 5), 'n': len(pairs)}
        summary.append({'month': mo, 'frozen_at': e['frozen_at'], 'price_date': start, 'n': e['n'],
                        'top': e['top'][:15], 'bottom': e['bottom'][:15], 'result': res})
    done = [s['result'] for s in summary if s['result']]
    return {'generated_at': now(), 'months': {s['month']: s for s in summary},
            'scored': len(done), 'mean_ic': _r(sum(d['ic'] for d in done if d['ic'] is not None) / len(done), 4) if done else None,
            'mean_spread': _r(sum(d['spread'] for d in done) / len(done), 5) if done else None,
            'note': 'Each month the composite ranking is frozen once and never edited; the next month-end close scores it.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--minutes', type=float, default=20)
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--frames-root', required=True, help='the hub data folder whose cache/frames holds the income-statement frames')
    b.add_argument('--prices', required=True, help='the hub price cache (cache/prices with sec-tickers.json)')
    b.add_argument('--site-index', default=None, help="the Sankey site's index.json (sectors, SIC codes, names)")
    b.add_argument('--valuation', default=None, help='public/ of research-valuation (company WACC), when it exists')
    b.add_argument('--rates', default=None, help='rates.json of debt-history public/ (10-year Treasury), when it exists')
    a = ap.parse_args()
    if a.cmd == 'collect':
        from core import Client
        print(json.dumps(collect(Client(a.root, {}), a.root, a.minutes)), flush=True)
    else:
        print(json.dumps(build(a.root, a.frames_root, a.prices, a.site_index, a.valuation, a.rates)), flush=True)


if __name__ == '__main__':
    main()
