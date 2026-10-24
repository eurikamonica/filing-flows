"""Fair value & credit (research-valuation): many valuation methods side by side for every company, the price's split
between what the business earns now and what it is expected to grow into, a Monte Carlo DCF, each company's own cost of
capital, valuation bands, sector models for banks / insurers / REITs, and a blended distress probability.

  collect   SEC XBRL frames (one request = one figure for every filer for one calendar quarter; cached, final quarters
            never refetched): diluted EPS and shares, net income, operating income, revenue, equity, goodwill, intangibles,
            insurance and REIT lines; annual D&A, capex, tax and pretax income. And each covered company's main-site
            figures (data/c/<cik>.json → quality.val, revenue history, segments) from the published site, slimmed.
  build     public/ (published by scan.yml at disclosures/data/research/valuation/):
              index.json     one row per company (the hub's Valuation tab and the X posts)
              c/<cik>.json   the company page's "Fair value" view: football field, PVGO, Monte Carlo, WACC build-up,
                             valuation bands, the sector model and the credit panel
              peers.json     peer multiples by industry group; banks.json / insurers.json: the cross-section fits
              ledger.json    the frozen monthly snapshots (DCF value, P(value > price), distress) and their scores
              base_rates.json  the peer distributions (app/base_rates.py) by industry and size
              models.json    out-of-sample scores: the combined forecast (walk-forward), the valuation ledger, the Rotation
                             forecasts (forecast ledger), the hierarchical revenue model, Polymarket's implied prices
              markov.json    the regime model's panel prior (transition counts, regime growth, margin drift) by size bucket
              status.json

Inputs the build reads (each optional; a company is valued with what exists):
  --site      a folder with data/index.json and the slim c/ cache (collect writes it)
  --prices    the hub's daily closes: disclosures/docs/data/cache/prices/<T>.json.gz (rows [date, close, volume])
  --debt      public/ of the branch debt-history (app/debt.py): snapshot, Merton DD, calibrated CDS, Altman Z, cushion
  --consensus public/ of the branch consensus-history (app/consensus.py): analysts' targets, Polymarket price, our model
  --rotation  public/ of the branch rotation-history: forecast-ledger*.json (the Rotation forecasts, frozen and resolved)

Methods (every assumption is in the output, nothing is hidden):
  WACC        cost of equity = 10-year Treasury + Blume-adjusted beta (weekly log returns vs SPY, 2 years) × ERP (4.5%,
              a fixed assumption); cost of debt = 5-year Treasury + the debt module's bond-calibrated spread, else its
              effective rate (interest ÷ debt), else Treasury + 2%; tax = tax ÷ pretax (0–35%, else 21%); market weights.
  DCF         the main site's FCFF model (web/fsa.js, same formulas): revenue growth from the last four quarters vs the four
              before (−20%…40%), fading to terminal growth over 5 years; EBIT margin and D&A as a share of trailing revenue;
              capex as a share of trailing revenue, moving halfway to D&A by year 5 when it runs above D&A (an investment
              wave is not assumed to last forever); 10% of each revenue increase into working capital; terminal value with
              reinvestment = g ÷ ROIC (today's ROIC, 10–30%).
  Reverse     the constant revenue growth at which the model gives today's price (bisection inside a scanned bracket).
  Monte Carlo 2,000 scenarios seeded by ticker: growth ~ N(base, σ of the company's own YoY growth, 3–25%), margin ~
              N(base, σ of its own quarterly margins, 1–10 pts), WACC ~ N(WACC, 1 pt, ±3 pts), terminal growth ~ U(1.5%, 3%).
  Regimes     app/markov.py: a 10-year Monte Carlo in which revenue growth switches between high / steady / decline
              regimes by a Markov chain estimated from the company's own history and the whole panel; consensus revenue
              growth for years 1–2, margin drift by regime, stock-based compensation deducted. Every input is estimated.
  PVGO        no-growth value = NOPAT ÷ WACC − net debt (financials: net income ÷ cost of equity); the rest of the market
              value is the price of expected growth.
  Peers       median and interquartile range of P/E, EV/EBITDA, EV/Sales in the narrowest SIC group with ≥ 6 peers.
  Residual    book value + the discounted earnings above the cost of equity, ROE fading to the cost of equity over 10
  income      years, half of earnings retained.
  Banks       P/TBV regressed on ROTCE across banks; insurers P/B on ROE; REITs P/FFO (FFO ≈ net income + D&A − gains on
              property sales: AFFO is not standardized in XBRL and is not shown).
  Bands       weekly P/E and EV/Sales since the price history starts (mid-2022), with trailing figures known 60 days after
              each quarter's end; percentiles of that history.
  Distress    a weighted average of log-odds from up to four one-year default probabilities: Merton (equity-implied),
              the bond-calibrated CDS spread (1 − e^(−s/LGD), LGD 60%), Altman Z mapped to rating-equivalent default rates
              (logit = 0.622 − 2.143·Z: Z 1.1 → 15%, Z 3.0 → 0.3%), and the debt cushion score (logit = −0.5 − 0.07·score).
              NOT calibrated against realized defaults — no default history is available here; read it as a ranking.
  Early stage app/valuation_methods.py: pre-revenue companies (net cash floor, the value the price puts on the
  & cash burn pipeline), companies burning cash (the path-to-margin DCF with the dilution needed before break-even,
              the exit-multiple / venture method, a survival-weighted value), high growth (EV/Sales against the Rule of
              40 across every company); banks, insurers and REITs (justified P/TBV and P/B by Gordon growth, a dividend
              discount model).
  Appendix    for every company: each input with its source, each assumption with its basis, the WACC step by step,
              every method's formula with the company's numbers substituted, and the methods that do not apply and why.
  Outside     app/base_rates.py: every input read from what peers (SIC industry × size) actually did — base rates, the
  view        probabilities of the market-implied, Street and Polymarket views, a Monte Carlo drawn from peers, the
              company's stage and its methods, sensitivity (tornado, grids), river charts, and the combined forecast.

    python app/valuation.py collect --root val --site-url https://filing-flows.com --minutes 20
    python app/valuation.py build   --root val --prices data/cache/prices --debt debt/public --consensus cons/public
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_rates as BR
import valuation_methods as VMx  # noqa: E402
import markov  # noqa: E402  (regime-switching Monte Carlo, app/markov.py)

ERP = 0.045                 # equity risk premium: a fixed, stated assumption (not estimated here)
TERM_G = 0.025              # terminal growth of the base DCF
WC_SHARE = 0.10             # working capital: share of each revenue increase
YEARS = 5
MC_N = 2000
LGD = 0.6
LAG_DAYS = 60               # a quarter's figures are treated as known this many days after it ends
QUARTERS = 26               # the frames panel: calendar quarters since 2020 (base rates, river charts)
FRAMES = 'https://data.sec.gov/api/xbrl/frames/{tax}/{concept}/{unit}/{period}.json'
REVENUE = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'SalesRevenueNet']
# (taxonomy, concept, unit, kind): kind q = quarterly durations (+ annual frames to fill the fourth quarter), a = annual
# durations only (cash-flow lines are tagged year-to-date), i = instants at the last six quarter ends, iq = instants at
# every quarter end (equity: the P/B river). Revenue, operating and net income also get the annual frames back to CY2010
# (app/base_rates.py: 3-, 5- and 10-year base rates).
CONCEPTS = ([('us-gaap', c, 'USD', 'q') for c in REVENUE] + [
    ('us-gaap', 'OperatingIncomeLoss', 'USD', 'q'),
    ('us-gaap', 'NetIncomeLoss', 'USD', 'q'),
    ('us-gaap', 'EarningsPerShareDiluted', 'USD-per-shares', 'q'),
    ('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding', 'shares', 'q'),
    ('us-gaap', 'PremiumsEarnedNet', 'USD', 'q'),
    ('us-gaap', 'PolicyholderBenefitsAndClaimsIncurredNet', 'USD', 'q'),
    ('us-gaap', 'DeferredPolicyAcquisitionCostAmortizationExpense', 'USD', 'q'),
    ('us-gaap', 'OtherUnderwritingExpense', 'USD', 'q'),
    ('us-gaap', 'DepreciationDepletionAndAmortization', 'USD', 'a'),
    ('us-gaap', 'DepreciationAndAmortization', 'USD', 'a'),
    ('us-gaap', 'PaymentsToAcquirePropertyPlantAndEquipment', 'USD', 'a'),
    ('us-gaap', 'IncomeTaxExpenseBenefit', 'USD', 'a'),
    ('us-gaap', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'USD', 'a'),
    ('us-gaap', 'GainsLossesOnSalesOfInvestmentRealEstate', 'USD', 'a'),
    ('us-gaap', 'PaymentsOfDividends', 'USD', 'a'),
    ('us-gaap', 'PaymentsForRepurchaseOfCommonStock', 'USD', 'a'),
    ('us-gaap', 'ShareBasedCompensation', 'USD', 'a'),
    ('us-gaap', 'AllocatedShareBasedCompensationExpense', 'USD', 'a'),
    ('us-gaap', 'StockholdersEquity', 'USD', 'iq'),
    ('us-gaap', 'Goodwill', 'USD', 'i'),
    ('us-gaap', 'IntangibleAssetsNetExcludingGoodwill', 'USD', 'i'),
    ('us-gaap', 'CashAndCashEquivalentsAtCarryingValue', 'USD', 'i'),
    ('us-gaap', 'LongTermDebt', 'USD', 'i'),
])
BANK_SIC = ('602', '603', '6712', '6111', '6153')
INSURER_SIC = ('631', '632', '633', '635', '636', '639', '6411')
REIT_SIC = ('6798',)
UA = 'Mozilla/5.0 (X11; Linux x86_64) FilingFlows-valuation/1.0'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        if p.suffix == '.gz':
            with gzip.open(p, 'rt', encoding='utf-8') as f:
                return json.load(f)
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError, EOFError, zlib.error):
        return default


def write_json(path, obj, gz=False):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    tmp = p.with_name(p.name + '.tmp')
    if gz:
        with gzip.open(tmp, 'wt', encoding='utf-8') as f:
            f.write(txt)
    else:
        tmp.write_text(txt, encoding='utf-8')
    tmp.replace(p)


def fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _r(v, d=4):
    return round(v, d) if fin(v) else None


def clean(o):
    """JSON-safe: NaN / inf → None, floats rounded to 6 significant places."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float):
        if not math.isfinite(o):
            return None
        return float(f'{o:.6g}')
    return o


def pctile(xs, q):
    """Linear-interpolated percentile (q in 0..1) of a list."""
    xs = sorted(x for x in xs if fin(x))
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def rank_pct(xs, v):
    """The share of xs below v (0..1)."""
    xs = [x for x in xs if fin(x)]
    if not xs or not fin(v):
        return None
    return sum(1 for x in xs if x < v) / len(xs)


def stdev(xs):
    xs = [x for x in xs if fin(x)]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# ------------------------------------------------------------------ prices, returns, beta
def load_prices(prices_dir, ticker):
    """Daily [(date, close)] from the hub's price cache, or []. prices_dir may be a list of folders (the hub's cache,
    then this branch's top-up, collect_prices): the series reaching the latest day wins."""
    if not prices_dir or not ticker:
        return []
    best = []
    for folder in (prices_dir if isinstance(prices_dir, (list, tuple)) else [prices_dir]):
        if not folder:
            continue
        for t in (ticker.upper().replace('.', '-'), ticker.upper()):
            d = read_json(Path(folder) / f'{t}.json.gz')
            if d and d.get('rows'):
                rows = [(r[0], float(r[1])) for r in d['rows'] if len(r) > 1 and fin(r[1]) and r[1] > 0]
                if rows and (not best or rows[-1][0] > best[-1][0]):
                    best = rows
                break
    return best


YAHOO_CHART = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5y&interval=1d&events=div%2Csplit'
BROWSER_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


def site_weekly(doc):
    """[[date, close]] from a rotation-history weekly file (t/<T>.json: start, closes a week apart, adjusted)."""
    if not doc or not doc.get('start') or not doc.get('c'):
        return None
    d0 = dt.date.fromisoformat(doc['start'])
    rows = [[(d0 + dt.timedelta(days=7 * i)).isoformat(), float(v)] for i, v in enumerate(doc['c']) if fin(v) and v > 0]
    return rows or None


def collect_prices(root, hub_dir=None, limit=1500, minutes=6.0, workers=6, refresh_days=1, today=None, site_url=None):
    """Closes for the site's companies the hub does not price, or prices only with a stale file (its cache holds the
    tickers 13F managers and officials hold: CoreWeave and Nebius were missing, so they had no fair-value page).
    First the site's own weekly closes (the rotation history, published at disclosures/data/market/history/t/<T>.json:
    adjusted, the latest week included); for a ticker it lacks, five years of daily closes from Yahoo's chart API, which
    rate-limits shared runners (it is left after 25 refusals). Saved to this branch's cache/prices, which build() reads
    after the hub's, taking the more recent series; a ticker neither source knows is not asked again for 30 days."""
    import urllib.error
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    import prices as PR
    root = Path(root)
    own = root / 'cache' / 'prices'
    own.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today()
    missing = read_json(own / '_missing.json', {}) or {}
    ix = read_json(root / 'site' / 'index.json', {}) or {}
    cos = ix.get('companies') if isinstance(ix, dict) else ix
    cos = sorted([c for c in cos or [] if c.get('ticker') and c.get('cik')], key=lambda c: -(c.get('revenue') or 0))[:limit]
    fresh = (today - dt.timedelta(days=7)).isoformat()
    todo = []
    for c in cos:
        t = PR.clean_ticker(c['ticker'])
        if not re.fullmatch(r'[A-Z0-9-]{1,10}', t):
            continue
        hub = load_prices(hub_dir, t) if hub_dir else []
        if hub and hub[-1][0] >= fresh:
            continue                                       # the hub prices it
        mine = read_json(own / f'{t}.json.gz', {}) or {}
        got = (mine.get('fetched_at') or '')[:10]
        if got and (today - dt.date.fromisoformat(got)).days < refresh_days:
            continue
        miss = missing.get(t)
        if miss and (today - dt.date.fromisoformat(miss)).days < 30:
            continue
        todo.append(t)
    t0, blocked = time.monotonic(), [0]
    site = Http(UA, interval=0.0, timeout=30, retries=2) if site_url else None
    base = (site_url or '').rstrip('/') + '/disclosures/data/market/history/t/'

    def one(t):
        if time.monotonic() - t0 > minutes * 60:
            return t, None, None, 'budget'
        if site:
            try:
                rows = site_weekly(site.get(base + t + '.json'))
                if rows:
                    return t, rows, 'site-weekly', None
            except Exception:                               # noqa: BLE001  (404: not in the rotation history)
                pass
        if blocked[0] >= 25:
            return t, None, None, 'blocked'
        try:
            req = urllib.request.Request(YAHOO_CHART.format(symbol=t), headers={'User-Agent': BROWSER_UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                rows = PR.parse_yahoo(json.loads(r.read().decode('utf-8')), (today - dt.timedelta(days=5 * 366)).isoformat())
                return t, [[d, c] for d, c, *_ in rows], 'yahoo', None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                blocked[0] += 1
                time.sleep(5)
            return t, None, None, f'HTTP {e.code}'
        except Exception as e:                              # noqa: BLE001
            return t, None, None, str(e)[:80]
    saved, errs, by = 0, 0, {}
    with ThreadPoolExecutor(workers) as pool:
        for t, rows, src, err in pool.map(one, todo):
            if err in ('budget', 'blocked'):
                continue
            if rows:
                write_json(own / f'{t}.json.gz', {'ticker': t, 'source': src, 'fetched_at': now(), 'rows': rows}, gz=True)
                missing.pop(t, None)
                saved += 1
                by[src] = by.get(src, 0) + 1
            elif err and (err.startswith('HTTP 404') or 'No chart result' in err or 'No daily rows' in err):
                missing[t] = today.isoformat()
            else:
                errs += 1
    write_json(own / '_missing.json', missing)
    return {'wanted': len(todo), 'saved': saved, 'by_source': by, 'errors': errs, 'rate_limited': blocked[0]}


def weekly(daily):
    """The last close of each ISO week: [(date, close)]."""
    out, key = [], None
    for d, c in daily:
        k = dt.date.fromisoformat(d).isocalendar()[:2]
        if k == key:
            out[-1] = (d, c)
        else:
            out.append((d, c))
            key = k
    return out


def beta(stock, market, weeks=104):
    """(raw beta, Blume-adjusted beta, weeks, r²) from weekly log returns over the last `weeks` weeks, or None."""
    s, m = dict(weekly(stock)), dict(weekly(market))
    common = sorted(set(s) & set(m))[-(weeks + 1):]
    rs, rm = [], []
    for a, b in zip(common, common[1:]):
        if s[a] > 0 and s[b] > 0 and m[a] > 0 and m[b] > 0:
            rs.append(math.log(s[b] / s[a]))
            rm.append(math.log(m[b] / m[a]))
    if len(rs) < 52:
        return None
    ms, mm = sum(rs) / len(rs), sum(rm) / len(rm)
    cov = sum((x - ms) * (y - mm) for x, y in zip(rs, rm))
    var = sum((y - mm) ** 2 for y in rm)
    vs = sum((x - ms) ** 2 for x in rs)
    if var <= 0:
        return None
    b = cov / var
    r2 = cov * cov / (var * vs) if vs > 0 else None
    return b, 0.67 * b + 0.33, len(rs), r2


def annual_vol(daily, days=252):
    """Annualised volatility of the last year of closes: daily rows, or weekly ones (the site's weekly closes, a
    collect_prices fallback), told apart by the median gap between dates."""
    if len(daily) > 3:
        gaps = sorted((dt.date.fromisoformat(b[0]) - dt.date.fromisoformat(a[0])).days for a, b in zip(daily[-27:], daily[-26:]))
        if gaps[len(gaps) // 2] >= 5:
            days = 52
    xs = [math.log(b[1] / a[1]) for a, b in zip(daily[-days - 1:], daily[-days:]) if a[1] > 0 and b[1] > 0]
    sd = stdev(xs)
    return sd * math.sqrt(days) if sd else None


# ------------------------------------------------------------------ the DCF (same formulas as web/fsa.js)
def _at(v, t):
    return v[min(t, len(v) - 1)] if isinstance(v, (list, tuple)) else v


def dcf(x):
    """Forward FCFF DCF. x: rev0, years, growth (number or per-year list), margin, tax, da, capex, wc, wacc, g, terminal
    ('roic' | 'simple'), roic, debt, cash, claims, nonop, shares. Returns dict(ok, perShare, ev, equity, tvPv, rows) or
    dict(ok=False, errors)."""
    errs = []
    for k in ('rev0', 'tax', 'wc', 'wacc', 'g', 'debt', 'cash', 'claims', 'nonop', 'shares'):
        if not fin(x.get(k)):
            errs.append(f'{k} is missing')
    for k in ('growth', 'margin', 'da', 'capex'):
        v = x.get(k)
        if not all(fin(a) for a in (v if isinstance(v, (list, tuple)) else [v])):
            errs.append(f'{k} is missing')
    if not errs:
        if x['wacc'] <= x['g']:
            errs.append('WACC must be above terminal growth')
        if x['shares'] <= 0:
            errs.append('shares must be positive')
        if x.get('terminal', 'roic') == 'roic' and not (fin(x.get('roic')) and x['roic'] > 0 and x['g'] <= x['roic']):
            errs.append('terminal ROIC must be positive and above growth')
    if errs:
        return {'ok': False, 'errors': errs}
    rows, rev, pv = [], x['rev0'], 0.0
    nop = lambda e: e * (1 - x['tax']) if e > 0 or x.get('lossTax') == 'symmetric' else e
    for t in range(1, x['years'] + 1):
        prev = rev
        rev = prev * (1 + _at(x['growth'], t - 1))
        ebit = rev * _at(x['margin'], t - 1)
        fcff = nop(ebit) + rev * _at(x['da'], t - 1) - rev * _at(x['capex'], t - 1) - (rev - prev) * x['wc']
        df = (1 + x['wacc']) ** -t
        pv += fcff * df
        rows.append({'t': t, 'rev': rev, 'ebit': ebit, 'fcff': fcff, 'pv': fcff * df})
    last = rows[-1]
    if x.get('terminal', 'roic') == 'roic':
        nxt = nop(last['rev'] * (1 + x['g']) * _at(x['margin'], x['years'] - 1)) * (1 - x['g'] / x['roic'])
    else:
        nxt = last['fcff'] * (1 + x['g'])
    tv = nxt / (x['wacc'] - x['g'])
    tv_pv = tv * (1 + x['wacc']) ** -x['years']
    ev = pv + tv_pv
    eq = ev - x['debt'] - x['claims'] + x['cash'] + x['nonop']
    return {'ok': True, 'rows': rows, 'ev': ev, 'equity': eq, 'tvPv': tv_pv, 'perShare': eq / x['shares'],
            'tv_share': tv_pv / ev if ev > 0 else None}


def value(x):
    r = dcf(x)
    return r['perShare'] if r['ok'] else float('nan')


def solve(x, param, price, lo, hi, steps=120, tol=1e-7):
    """The single value of `param` in [lo, hi] at which the model gives `price` ({status, value}); 'none' / 'multiple' /
    'nonconvergent' otherwise — never clamped to a bound (web/fsa.js root1)."""
    f = lambda v: value({**x, param: v}) - price
    pts = [(lo + (hi - lo) * i / steps, None) for i in range(steps + 1)]
    pts = [(v, f(v)) for v, _ in pts]
    br = []
    for (a, fa), (b, fb) in zip(pts, pts[1:]):
        if not (fin(fa) and fin(fb)):
            continue
        if fa == 0:
            br.append((a, a))
        elif fa * fb < 0:
            br.append((a, b))
    if not br:
        return {'status': 'none'}
    if len(br) > 1:
        return {'status': 'multiple'}
    a, b = br[0]
    fa = f(a)
    for _ in range(200):
        if b - a <= tol:
            break
        m = (a + b) / 2
        fm = f(m)
        if not fin(fm):
            return {'status': 'nonconvergent'}
        if fm == 0:
            a = b = m
            break
        if fa * fm < 0:
            b = m
        else:
            a, fa = m, fm
    return {'status': 'ok', 'value': (a + b) / 2}


def fade(g0, gt, years=YEARS):
    """Year-by-year growth from g0 in year 1 toward gt (linear; year 5 is 80% of the way)."""
    return [g0 + (gt - g0) * t / years for t in range(years)]


def monte_carlo(base, price, sg, sm, n=MC_N, seed=0):
    """Scenario values per share around the base DCF inputs; percentiles, P(value > price) and a histogram."""
    rng = random.Random(seed)
    g0, m0, w0 = _at(base['growth'], 0), _at(base['margin'], 0), base['wacc']
    vals = []
    for _ in range(n):
        g = clamp(rng.gauss(g0, sg), -0.30, 0.60)
        m = clamp(rng.gauss(m0, sm), -0.50, 0.70)
        tg = rng.uniform(0.015, 0.03)
        w = clamp(rng.gauss(w0, 0.01), max(0.04, w0 - 0.03), w0 + 0.03)
        w = max(w, tg + 0.01)
        x = {**base, 'growth': fade(g, tg), 'margin': m, 'wacc': w, 'g': tg,
             'roic': max(base.get('roic', 0.15), tg + 0.01)}
        v = value(x)
        if fin(v):
            vals.append(v)
    if len(vals) < n * 0.5:
        return None
    vals.sort()
    q = {f'p{int(k * 100)}': pctile(vals, k) for k in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)}
    lo, hi = q['p5'], q['p95']
    bins = 30
    hist = [0] * bins
    if hi > lo:
        for v in vals:
            if lo <= v <= hi:
                hist[min(bins - 1, int((v - lo) / (hi - lo) * bins))] += 1
    return {'n': len(vals), **q, 'mean': sum(vals) / len(vals),
            'p_above': (sum(1 for v in vals if v > price) / len(vals)) if fin(price) and price > 0 else None,
            'hist': {'lo': lo, 'hi': hi, 'counts': hist},
            'assumptions': {'growth': [g0, sg], 'margin': [m0, sm], 'wacc': [w0, 0.01], 'terminal_growth': [0.015, 0.03]}}


# ------------------------------------------------------------------ cost of capital
def cost_of_debt(debt_rec, rates, interest, debt):
    """(pre-tax cost of debt, how) — bond-calibrated spread over the 5-year Treasury, else the effective rate."""
    an = (debt_rec or {}).get('analysis') or {}
    imp = an.get('implied') or {}
    r5 = rates.get('treasury_5y')
    spread = imp.get('calibrated_5y_bps') or imp.get('spread_5y_bps')
    if fin(spread) and fin(r5) and not an.get('bank'):
        return r5 / 100 + spread / 1e4, f'5-year Treasury {r5:.2f}% + model spread {spread:.0f} bp (bond-calibrated, app/debt.py)'
    eff = an.get('effective_rate')
    if fin(eff) and 0.005 <= eff <= 0.25:
        return eff, f'effective rate: interest expense ÷ debt = {eff * 100:.2f}% (app/debt.py)'
    if fin(interest) and fin(debt) and debt > 0 and 0.005 <= abs(interest) / debt <= 0.25:
        return abs(interest) / debt, 'interest expense ÷ debt'
    r10 = rates.get('treasury_10y') or 4.3
    return r10 / 100 + 0.02, '10-year Treasury + 2% (no rate on file)'


def wacc_of(F, rates, debt_rec, b):
    """The company's weighted average cost of capital with its build-up."""
    rf = (rates.get('treasury_10y') or 4.3) / 100
    beta_adj = b[1] if b else 1.0
    ke = rf + beta_adj * ERP
    kd, how = cost_of_debt(debt_rec, rates, F.get('interest'), F.get('debt'))
    t = F.get('tax_rate', 0.21)
    E, D = F.get('mcap'), max(0.0, F.get('debt') or 0.0)
    if not fin(E) or E <= 0:
        return None
    wd = D / (D + E)
    w = (1 - wd) * ke + wd * kd * (1 - t)
    return {'wacc': clamp(w, 0.05, 0.16), 'raw': w, 'rf': rf, 'erp': ERP, 'beta_raw': b[0] if b else None, 'beta': beta_adj,
            'beta_weeks': b[2] if b else None, 'beta_r2': b[3] if b else None, 'ke': ke, 'kd': kd, 'kd_how': how,
            'kd_after_tax': kd * (1 - t), 'tax': t, 'w_debt': wd, 'w_equity': 1 - wd,
            'beta_note': None if b else 'fewer than 52 weeks of prices: beta 1.0 assumed'}


# ------------------------------------------------------------------ frames panel (SEC XBRL frames)
def calendar_quarters(n=18, today=None):
    today = today or dt.date.today()
    y, q = today.year, (today.month - 1) // 3
    out = []
    for _ in range(n):
        if q == 0:
            y, q = y - 1, 4
        out.append(f'CY{y}Q{q}')
        q -= 1
    return out[::-1]


def quarter_end(period):
    y, q = int(period[2:6]), int(period[7])
    return (dt.date(y, 3 * q, 1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)


def _shift(period, k):
    y, q = int(period[2:6]), int(period[7]) - 1 + k
    return f'CY{y + q // 4}Q{q % 4 + 1}'


def _quarter_of(end):
    d = dt.date.fromisoformat(end[:10])
    best = None
    for y in (d.year - 1, d.year, d.year + 1):
        for q in range(1, 5):
            gap = abs((quarter_end(f'CY{y}Q{q}') - d).days)
            if best is None or gap < best[0]:
                best = (gap, f'CY{y}Q{q}')
    return best[1]


def frame_path(root, concept, period):
    return Path(root) / 'cache' / 'frames' / f'{concept}-{period}.json.gz'


def frame(root, concept, period):
    return read_json(frame_path(root, concept, period), {}) or {}


def quarterly(root, concept, periods, additive=True):
    """{period: {cik: value}} with the fourth quarter filled from the annual frame when the three before are on file
    (flows only: a weighted share count for the year minus three quarters' counts is not the fourth quarter's)."""
    span = [_shift(periods[0], -k) for k in (3, 2, 1)] + list(periods)
    q = {p: dict(frame(root, concept, p)) for p in dict.fromkeys(span)}
    years = (sorted({p[:6] for p in span}) + [f'CY{int(periods[-1][2:6]) + 1}']) if additive else []
    for year in years:
        for cik, row in frame(root, concept, year).items():
            if not isinstance(row, list) or not row[1]:
                continue
            last = _quarter_of(row[1])
            if last not in q or cik in q[last]:
                continue
            three = [q.get(_shift(last, -k), {}).get(cik) for k in (1, 2, 3)]
            if all(fin(v) for v in three):
                q[last][cik] = row[0] - sum(three)
    return {p: q[p] for p in periods}


def annual_latest(root, concept, years):
    """{cik: (value, end)} — the latest annual value of each filer across the annual frames."""
    out = {}
    for y in years:
        for cik, row in frame(root, concept, y).items():
            if isinstance(row, list) and fin(row[0]) and row[1] and (cik not in out or row[1] > out[cik][1]):
                out[cik] = (row[0], row[1])
    return out


def panel(root, periods):
    """Per company (cik → dict) series and latest figures from the cached frames."""
    years = sorted({p[:6] for p in periods})[-3:] + [f'CY{int(periods[-1][2:6]) + 1}']
    rev_q = {}
    for c in REVENUE:
        for p, vals in quarterly(root, c, periods).items():
            per = rev_q.setdefault(p, {})
            for cik, v in vals.items():
                per.setdefault(cik, v)
    Q = {'rev': rev_q}
    for key, c in (('oi', 'OperatingIncomeLoss'), ('ni', 'NetIncomeLoss'), ('eps', 'EarningsPerShareDiluted'),
                   ('sh', 'WeightedAverageNumberOfDilutedSharesOutstanding'), ('prem', 'PremiumsEarnedNet'),
                   ('claims', 'PolicyholderBenefitsAndClaimsIncurredNet'), ('dac', 'DeferredPolicyAcquisitionCostAmortizationExpense'),
                   ('uw', 'OtherUnderwritingExpense')):
        Q[key] = quarterly(root, c, periods, additive=key != 'sh')
    inst, eq_q = {}, {}
    for key, c in (('equity', 'StockholdersEquity'), ('goodwill', 'Goodwill'), ('intang', 'IntangibleAssetsNetExcludingGoodwill'),
                   ('cash', 'CashAndCashEquivalentsAtCarryingValue'), ('ltd', 'LongTermDebt')):
        latest = {}
        for k, p in enumerate(periods):
            for cik, v in frame(root, c, p + 'I').items():
                if fin(v):
                    latest[cik] = (v, p)
                    if key == 'equity':
                        eq_q.setdefault(cik, [None] * len(periods))[k] = v
        inst[key] = latest
    ann = {}
    for key, cs in (('da', ['DepreciationDepletionAndAmortization', 'DepreciationAndAmortization']),
                    ('capex', ['PaymentsToAcquirePropertyPlantAndEquipment']), ('tax', ['IncomeTaxExpenseBenefit']),
                    ('pretax', ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest']),
                    ('re_gains', ['GainsLossesOnSalesOfInvestmentRealEstate']), ('div', ['PaymentsOfDividends']),
                    ('buyback', ['PaymentsForRepurchaseOfCommonStock']),
                    ('sbc', ['ShareBasedCompensation', 'AllocatedShareBasedCompensationExpense'])):
        m = {}
        for c in cs:
            for cik, v in annual_latest(root, c, years).items():
                m.setdefault(cik, v)
        ann[key] = m
    out = {}
    ciks = set()
    for d in Q.values():
        for vals in d.values():
            ciks.update(vals)
    for cik in ciks:
        rec = {'q': {k: [Q[k][p].get(cik) for p in periods] for k in Q}}
        rec['inst'] = {k: inst[k][cik] for k in inst if cik in inst[k]}
        rec['ann'] = {k: ann[k][cik] for k in ann if cik in ann[k]}
        rec['eq_q'] = eq_q.get(cik) or [None] * len(periods)
        out[cik] = rec
    return out


def ttm(series, k=4):
    """Sum of the last k values when all present, else None."""
    xs = series[-k:]
    return sum(xs) if len(xs) == k and all(fin(v) for v in xs) else None


# ------------------------------------------------------------------ peers
def sic_groups(sic):
    s = str(sic or '')
    return [g for g in (s[:4], s[:3], s[:2]) if len(g) >= 2 and g.isdigit()]


def peer_stats(rows, metric, min_n=6):
    """{group: {n, p25, p50, p75}} of a multiple over companies, by SIC 4/3/2-digit groups and sector."""
    buckets = {}
    for r in rows:
        v = r.get(metric)
        if not fin(v):
            continue
        for g in sic_groups(r.get('sic')):
            buckets.setdefault('sic' + g, []).append((r['cik'], v))
        if r.get('sector'):
            buckets.setdefault('sec:' + r['sector'], []).append((r['cik'], v))
    return {g: xs for g, xs in buckets.items() if len(xs) >= min_n}


def peer_range(buckets, r, min_n=6):
    """(group label, n, p25, p50, p75) of the narrowest group with ≥ min_n other companies."""
    keys = ['sic' + g for g in sic_groups(r.get('sic'))] + (['sec:' + r['sector']] if r.get('sector') else [])
    for k in keys:
        xs = [v for c, v in buckets.get(k, []) if c != r['cik']]
        if len(xs) >= min_n:
            return k, len(xs), pctile(xs, 0.25), pctile(xs, 0.5), pctile(xs, 0.75)
    return None


# ------------------------------------------------------------------ residual income, regressions, credit
def residual_income(B0, roe0, ke, years=10, retain=0.5):
    """Book value + discounted residual income, ROE fading linearly to ke over `years`."""
    if not (fin(B0) and B0 > 0 and fin(roe0) and fin(ke) and ke > 0):
        return None
    B, v = B0, B0
    for t in range(1, years + 1):
        roe = roe0 + (ke - roe0) * t / years
        v += (roe - ke) * B / (1 + ke) ** t
        B *= 1 + retain * roe
    return v


def ols(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss = sum((y - my) ** 2 for y in ys)
    res = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    return {'a': a, 'b': b, 'n': n, 'r2': 1 - res / ss if ss > 0 else None, 'se': math.sqrt(res / (n - 2)) if n > 2 else None}


def logit(p):
    p = clamp(p, 1e-6, 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(z):
    return 1 / (1 + math.exp(-clamp(z, -40, 40)))


def distress(merton_pd=None, spread_bps=None, altman_z=None, cushion=None):
    """The blended one-year distress probability and its parts (see the module docstring)."""
    parts = []
    if fin(merton_pd):
        parts.append(('Merton (equity-implied)', 0.35, clamp(merton_pd, 1e-5, 0.95)))
    if fin(spread_bps) and spread_bps > 0:
        parts.append(('Bond-calibrated CDS spread', 0.30, clamp(1 - math.exp(-spread_bps / 1e4 / LGD), 1e-5, 0.95)))
    if fin(altman_z):
        parts.append(('Altman Z, rating-equivalent', 0.25, sigmoid(0.622 - 2.143 * altman_z)))
    if fin(cushion):
        parts.append(('Debt cushion score', 0.10, sigmoid(-0.5 - 0.07 * cushion)))
    if len(parts) < 2:
        return None
    wsum = sum(w for _, w, _ in parts)
    z = sum(w * logit(p) for _, w, p in parts) / wsum
    return {'pd': clamp(sigmoid(z), 1e-4, 0.6), 'parts': [{'name': n, 'weight': round(w / wsum, 3), 'pd': p} for n, w, p in parts],
            'calibrated': False}


# ------------------------------------------------------------------ valuation bands
def bands(daily, periods, eps_q, rev_q, shares, net_debt):
    """Weekly P/E and EV/Sales with trailing figures known LAG_DAYS after each quarter; percentiles of each history."""
    wk = weekly(daily)
    if len(wk) < 26:
        return None
    known = []
    for i in range(3, len(periods)):
        e4 = eps_q[i - 3:i + 1]
        r4 = rev_q[i - 3:i + 1]
        known.append(((quarter_end(periods[i]) + dt.timedelta(days=LAG_DAYS)).isoformat(),
                      sum(e4) if all(fin(v) for v in e4) else None, sum(r4) if all(fin(v) for v in r4) else None))
    if not known:
        return None
    dates = [k[0] for k in known]
    series = []
    for d, c in wk:
        j = bisect.bisect_right(dates, d) - 1
        if j < 0:
            continue
        _, e, r = known[j]
        pe = c / e if fin(e) and e > 0 and c / e <= 300 else None
        evs = ((c * shares + (net_debt or 0)) / r) if fin(r) and r > 0 and fin(shares) and shares > 0 else None
        series.append([d, _r(pe, 2), _r(evs, 3) if fin(evs) and 0 < evs <= 100 else None])
    out = {'from': series[0][0] if series else None, 'series': series[-260:]}
    for k, idx in (('pe', 1), ('evs', 2)):
        xs = [s[idx] for s in series if fin(s[idx])]
        if len(xs) >= 26:
            cur = next((s[idx] for s in reversed(series) if fin(s[idx])), None)
            out[k] = {'p10': pctile(xs, 0.1), 'p25': pctile(xs, 0.25), 'p50': pctile(xs, 0.5), 'p75': pctile(xs, 0.75),
                      'p90': pctile(xs, 0.9), 'min': min(xs), 'max': max(xs), 'current': cur, 'pct': rank_pct(xs, cur), 'weeks': len(xs)}
    return out if ('pe' in out or 'evs' in out) else None


# ------------------------------------------------------------------ sum of the parts
SEGMENT_MAP = [  # keywords in a revenue segment's name → the SIC group whose peers price it (EV/Sales)
    (r'cloud|software|subscription|saas|azure|aws|platform|digital services|services', '737'),
    (r'advertis|search|family of apps|youtube', '7370'),
    (r'semiconductor|chip|data center|gpu|compute|graphics', '367'),
    (r'iphone|ipad|mac\b|device|hardware|wearable|pc|server|storage|computer', '357'),
    (r'automotive|vehicle|cars?\b|trucks?', '371'),
    (r'pharma|drug|therapeut|oncology|vaccine|biolog', '283'),
    (r'medical|surgical|diagnostic|health care equipment', '384'),
    (r'insurance|premium|underwriting|reinsurance', '633'),
    (r'retail|stores|grocery|merchandise', '53'),
    (r'oil|gas|upstream|downstream|refining|chemical', '29'),
    (r'aerospace|defen[cs]e|aircraft', '372'),
    (r'electric|utility|power generation', '491'),
]


def segments_of(slim):
    """[(name, quarterly revenue)] of the leaf revenue segments on the latest Sankey (two or more), or []."""
    nodes = {n.get('id'): n for n in slim.get('nodes') or []}
    links = slim.get('links') or []
    into = {}
    for l in links:
        into.setdefault(l.get('t'), []).append(l)
    leaves = []

    def walk(t, depth=0):
        for l in into.get(t, []):
            s = l.get('s')
            if s in into and depth < 3:
                walk(s, depth + 1)
            elif fin(l.get('v')) and l['v'] > 0:
                n = nodes.get(s) or {}
                leaves.append((re.sub(r'&amp;', '&', str(n.get('name') or s)), l['v']))
    walk('revenue')
    return leaves if len(leaves) >= 2 else []


def sotp(segs, evs_buckets, own, shares, net_debt):
    """Sum of the parts on annualised segment revenue × the median EV/Sales of the peers each segment maps to."""
    if not segs or not fin(shares) or shares <= 0:
        return None
    parts, groups = [], set()
    for name, qv in segs:
        g = next((grp for rx, grp in SEGMENT_MAP if re.search(rx, name, re.I)), None)
        key = 'sic' + g if g else None
        xs = [v for c, v in evs_buckets.get(key, []) if c != own['cik']] if key else []
        if len(xs) < 6:
            pr = peer_range(evs_buckets, own)
            if not pr:
                return None
            key, mult, lo, hi = pr[0], pr[3], pr[2], pr[4]
        else:
            mult, lo, hi = pctile(xs, 0.5), pctile(xs, 0.25), pctile(xs, 0.75)
        groups.add(key)
        parts.append({'segment': name, 'revenue': qv * 4, 'group': key, 'ev_sales': mult, 'ev': qv * 4 * mult, 'ev_lo': qv * 4 * lo, 'ev_hi': qv * 4 * hi})
    if len(groups) < 2:
        return None
    nd = net_debt or 0
    ev, lo, hi = (sum(p[k] for p in parts) for k in ('ev', 'ev_lo', 'ev_hi'))
    return {'parts': parts, 'point': (ev - nd) / shares, 'low': (lo - nd) / shares, 'high': (hi - nd) / shares,
            'note': 'latest quarter ×4 for each segment, priced at the median EV/Sales of the industry its name maps to — a rough guide'}


# ------------------------------------------------------------------ one company
def kind_of(sic):
    s = str(sic or '')
    if s.startswith(BANK_SIC):
        return 'bank'
    if s.startswith(INSURER_SIC):
        return 'insurer'
    if s.startswith(REIT_SIC):
        return 'reit'
    return 'industrial'


def growth_history(revs):
    """(base growth: last four quarters vs the four before, σ of the quarterly YoY growth rates)."""
    g0 = None
    if len(revs) >= 8 and all(fin(v) for v in revs[-8:]) and sum(revs[-8:-4]) > 0:
        g0 = sum(revs[-4:]) / sum(revs[-8:-4]) - 1
    yoy = [revs[i] / revs[i - 4] - 1 for i in range(4, len(revs)) if fin(revs[i]) and fin(revs[i - 4]) and revs[i - 4] > 0]
    return g0, stdev(yoy[-12:]) if len(yoy) >= 4 else None


def implied_shares(ni, eps, k=4):
    """Net income ÷ diluted EPS over the latest quarters that have both (the median of up to k): the share count the
    reported EPS was computed on, whatever unit the filer tagged the count itself in. None when EPS is too small to
    divide by."""
    xs = [n / e for n, e in zip(ni, eps) if fin(n) and fin(e) and abs(e) >= 0.05 and n / e > 0]
    xs = xs[-k:]
    return sorted(xs)[len(xs) // 2] if xs else None


def plausible_shares(v, price=None, revenue=None):
    """A share count a listed company can have: 10 thousand to 30 billion and, for a company with $100M+ of revenue, a
    price-to-sales ratio between 0.025 and 2,000 at that count (Nutanix's 287,481 — thousands — would value a
    $2.5B-revenue company at $19M)."""
    if not (fin(v) and 1e4 <= v <= 3e10):
        return False
    if fin(price) and price > 0 and fin(revenue) and revenue >= 1e8:
        return 0.025 <= price * v / revenue <= 2000
    return True


def settle_shares(cands, price=None, revenue=None, implied=None):
    """(shares, source, note) from the sources in order of preference. A count that is implausible as filed (see
    plausible_shares) but a thousand or a million times another source (McDonald's diluted shares tagged as 711.1,
    Waters' as 98.2 billion) is read in shares; one implausible either way (Planet Fitness's 100 Class B shares, Erie's
    2,542) is passed over. Net income ÷ diluted EPS only helps decide a unit: as a share count it is unreliable (frames
    keep each quarter's EPS as first filed, before a split, and net income includes minority interests). None when no
    source is plausible: no per-share value beats a wrong one."""
    vals = [(n, v) for n, v in cands if fin(v) and v > 0]
    ref_ok = fin(implied) and implied > 0 and plausible_shares(implied, price, revenue)
    plain = [(v, n, None) for n, v in vals if plausible_shares(v, price, revenue)]
    refs = ([implied] if ref_ok else []) + [v for v, _, _ in plain]
    scaled = []
    for n, v in vals:
        if plausible_shares(v, price, revenue):
            continue
        for k in (1e3, 1e6, 1e-3, 1e-6):
            w = v * k
            if plausible_shares(w, price, revenue) and any(0.67 <= w / r <= 1.5 for r in refs):
                unit = {1e3: 'thousands', 1e6: 'millions', 1e-3: 'thousandths', 1e-6: 'millionths'}[k]
                scaled.append((w, n, f'Shares: {n} files {v:,.6g}, a count in {unit}; read as {w:,.0f}.'))
                break
    fixed = plain + scaled

    def passed_over(v, n, note):
        if note is None and vals and n != vals[0][0] and not (0.67 <= vals[0][1] / v <= 1.5):
            note = f'Shares: {vals[0][0]} files {vals[0][1]:,.6g}, which does not fit the other figures; {n} is used.'
        return v, n, note
    if fixed:
        return passed_over(*fixed[0])
    if vals:
        return None, None, 'Shares: no plausible count on file (' + ', '.join(f'{n} {v:,.6g}' for n, v in vals) + '); per-share values are left out.'
    return None, None, None


def company_inputs(cik, meta, P, slim, debt_rec, cons_c, price, periods):
    """The merged figures one company is valued with: the main site's trailing figures first, the frames second, the
    debt module's balance sheet third. Each value records where it came from."""
    q = (P or {}).get('q') or {}
    inst = (P or {}).get('inst') or {}
    ann = (P or {}).get('ann') or {}
    V = (slim or {}).get('val') or {}
    snap = (debt_rec or {}).get('snapshot') or {}
    src = {}

    def pick(key, *cands):
        for name, v in cands:
            if fin(v):
                src[key] = name
                return v
        return None
    revs = q.get('rev') or []
    F = {'cik': cik, 'ticker': meta.get('ticker'), 'name': meta.get('name'), 'sector': meta.get('sector'),
         'industry': meta.get('industry'), 'sic': meta.get('sic'), 'price': price}
    F['revenue'] = pick('revenue', ('main site (trailing)', V.get('revenue')), ('frames, 4 quarters', ttm(revs)), ('debt module', snap.get('revenue')))
    F['oi'] = pick('oi', ('main site (trailing)', V.get('oi')), ('frames, 4 quarters', ttm(q.get('oi') or [])), ('debt module', snap.get('operating_income')))
    F['ni'] = pick('ni', ('frames, 4 quarters', ttm(q.get('ni') or [])), ('debt module', snap.get('net_income')))
    F['eps'] = pick('eps', ('frames, 4 quarters', ttm(q.get('eps') or [])))
    F['da'] = pick('da', ('main site (trailing)', V.get('da')), ('debt module', snap.get('da')), ('frames, latest year', (ann.get('da') or (None,))[0]))
    F['capex'] = pick('capex', ('main site (trailing)', V.get('capex')), ('debt module', abs(snap['capex']) if fin(snap.get('capex')) else None),
                      ('frames, latest year', (ann.get('capex') or (None,))[0]))
    F['interest'] = pick('interest', ('debt module', snap.get('interest_expense')))
    F['sbc'] = pick('sbc', ('main site (trailing)', V.get('sbc')), ('frames, latest year', (ann.get('sbc') or (None,))[0]))
    pretax = pick('pretax', ('main site (trailing)', V.get('pretax')), ('debt module', snap.get('pretax_income')), ('frames, latest year', (ann.get('pretax') or (None,))[0]))
    tax = pick('tax', ('main site (trailing)', V.get('tax')), ('frames, latest year', (ann.get('tax') or (None,))[0]))
    F['tax_rate'] = clamp(tax / pretax, 0.0, 0.35) if fin(tax) and fin(pretax) and pretax > 0 else 0.21
    sh_q = [v for v in (q.get('sh') or []) if fin(v) and v > 0]
    implied = implied_shares(q.get('ni') or [], q.get('eps') or [])
    def fresh(day, days):                      # a count from long before the figures it is set against is stale
        end = V.get('end') or (slim or {}).get('end')
        try:
            return not end or not day or (dt.date.fromisoformat(end[:10]) - dt.date.fromisoformat(day[:10])).days <= days
        except ValueError:
            return True
    stale = {}
    if fin(V.get('diluted')) and not fresh(V.get('diluted_end'), 200):    # Coca-Cola Consolidated: a 2019 count, 2026 figures
        stale[V['diluted']], V = V.get('diluted_end'), {**V, 'diluted': None}
    if fin(V.get('outstanding')) and not fresh(V.get('outstanding_at'), 400):
        stale[V['outstanding']], V = V.get('outstanding_at'), {**V, 'outstanding': None}
    cover = snap.get('shares') if snap.get('shares') not in stale else None    # the debt module's undated copy of the same
    cands = [('main site (diluted)', V.get('diluted')), ('main site (outstanding)', V.get('outstanding')),
             ('frames, diluted weighted average', sh_q[-1] if sh_q else None), ('debt module (cover page)', cover),
             ('analysts (Yahoo)', ((cons_c or {}).get('analysts') or {}).get('shares'))]
    if fin(V.get('diluted')) and fin(V.get('outstanding')) and (V.get('outstanding_at') or '') > (V.get('diluted_end') or '9') \
            and V['outstanding'] > 1.3 * V['diluted']:
        # more shares on the cover page than the period's diluted count: a split or an issue since (KLA's 10-for-1) —
        # the cover page is the count the share price now applies to (one class can only be fewer, never more)
        cands.insert(0, ('main site (outstanding, after a split or issue)', V['outstanding']))
    F['shares'], src['shares'], F['shares_note'] = settle_shares(cands, price, F['revenue'], implied)
    if F['shares'] is None and stale:
        F['shares_note'] = ('Shares: the only counts on file are years old (' + ', '.join(f'{v:,.0f} at {d}' for v, d in stale.items())
                            + '; the filer no longer tags them); per-share values are left out.')
    F['shares_implied'] = implied
    if src.get('shares') is None:
        src.pop('shares', None)
    an = (debt_rec or {}).get('analysis') or {}
    F['debt'] = pick('debt', ('main site', V.get('debt') if V.get('debt_how') != 'no debt tagged' else None), ('debt module', an.get('total_debt')),
                     ('frames, long-term debt', (inst.get('ltd') or (None,))[0])) or 0.0
    F['cash'] = pick('cash', ('main site', V.get('cash_all')), ('debt module', an.get('cash_and_investments')),
                     ('frames, cash', (inst.get('cash') or (None,))[0])) or 0.0
    F['claims'] = V.get('claims') if fin(V.get('claims')) else 0.0
    F['equity'] = pick('equity', ('debt module', snap.get('equity')), ('frames', (inst.get('equity') or (None,))[0]))
    F['goodwill'] = (inst.get('goodwill') or (0.0,))[0] or 0.0
    F['intangibles'] = (inst.get('intang') or (0.0,))[0] or 0.0
    F['mcap'] = price * F['shares'] if fin(price) and fin(F['shares']) else None
    F['ev'] = F['mcap'] + F['debt'] - F['cash'] + F['claims'] if fin(F['mcap']) else None
    F['ebitda'] = F['oi'] + F['da'] if fin(F['oi']) and fin(F['da']) else None
    hist_rev = (slim or {}).get('rev_q') or revs
    F['g0'], F['sg'] = growth_history([v for v in hist_rev if fin(v)] if hist_rev else [])
    mq = [o / r for o, r in zip(q.get('oi') or [], revs) if fin(o) and fin(r) and r > 0]
    F['sm'] = stdev(mq[-12:]) if len(mq) >= 4 else None
    F['kind'] = kind_of(meta.get('sic'))
    if F['kind'] == 'insurer':
        prem, cl = ttm(q.get('prem') or []), ttm(q.get('claims') or [])
        dac, uw = ttm(q.get('dac') or []), ttm(q.get('uw') or [])
        F['combined_ratio'] = (cl + (dac or 0) + (uw or 0)) / prem if fin(prem) and prem > 0 and fin(cl) else None
        F['combined_ratio_parts'] = {'premiums_earned': prem, 'claims': cl, 'acquisition_costs': dac, 'other_underwriting': uw}
    if F['kind'] == 'reit':
        gains = (ann.get('re_gains') or (0.0,))[0] or 0.0
        F['ffo'] = F['ni'] + F['da'] - gains if fin(F['ni']) and fin(F['da']) else None
        F['ffo_parts'] = {'net_income': F['ni'], 'da': F['da'], 'gains_on_sales': gains}
    F['src'] = src
    F['eps_q'], F['rev_q'] = q.get('eps') or [], revs
    # yearly (trailing-twelve-month) growth and EBIT margin for the regime model: frames give revenue and operating income
    # on the same quarters; the main site's revenue history, when longer, extends the growth series (margins from frames)
    yf = markov.yearly(revs, q.get('oi') or [])
    ys = markov.yearly([v for v in hist_rev if fin(v)] if hist_rev and hist_rev is not revs else [])
    if len(ys) > len(yf):
        tail = [m for _, m in yf]
        F['years'] = [(g, None) for g, _ in ys[:len(ys) - len(tail)]] + [(g, m) for (g, _), m in zip(ys[len(ys) - len(tail):], tail)]
    else:
        F['years'] = yf
    return F


def analyse(F, ctx):
    """Everything the Fair value view shows for one company. ctx: rates, peer buckets, regressions, debt and consensus
    records, prices."""
    out = {'cik': F['cik'], 'ticker': F['ticker'], 'name': F['name'], 'sector': F['sector'], 'industry': F['industry'],
           'sic': F['sic'], 'kind': F['kind'], 'price': F['price'], 'price_date': ctx.get('price_date'), 'generated_at': now(),
           'inputs': {k: F.get(k) for k in ('revenue', 'oi', 'ni', 'eps', 'da', 'capex', 'interest', 'tax_rate', 'shares', 'debt', 'cash',
                                             'claims', 'equity', 'goodwill', 'intangibles', 'mcap', 'ev', 'ebitda', 'g0', 'sg', 'sm',
                                             'shares_implied')},
           'sources': F.get('src'), 'football': [], 'notes': [F['shares_note']] if F.get('shares_note') else []}
    price, sh = F['price'], F['shares']
    W = wacc_of(F, ctx['rates'], ctx.get('debt'), ctx.get('beta'))
    out['wacc'] = W
    fin_kind = F['kind'] in ('bank', 'insurer')
    # ---- DCF, reverse DCF, Monte Carlo (operating companies with positive operating income)
    base = None
    if W and not fin_kind and F['kind'] != 'reit' and fin(F['revenue']) and F['revenue'] > 0 and fin(F['oi']) and F['oi'] > 0 and fin(sh) and sh > 0:
        m0 = F['oi'] / F['revenue']
        g0 = clamp(F['g0'], -0.20, 0.40) if fin(F['g0']) else 0.05
        ic = (F['equity'] or 0) + F['debt'] - F['cash']
        roic_now = F['oi'] * (1 - F['tax_rate']) / ic if ic > 0 else None
        d0, c0 = (F['da'] or 0) / F['revenue'], (F['capex'] or 0) / F['revenue']
        capex = [c0 + ((c0 + d0) / 2 - c0) * t / (YEARS - 1) for t in range(YEARS)] if c0 > d0 else c0   # an investment wave halves toward D&A
        base = {'rev0': F['revenue'], 'years': YEARS, 'growth': fade(g0, TERM_G), 'margin': m0, 'tax': F['tax_rate'],
                'da': d0, 'capex': capex, 'wc': WC_SHARE, 'wacc': W['wacc'],
                'g': TERM_G, 'terminal': 'roic', 'roic': clamp(roic_now, 0.10, 0.30) if fin(roic_now) else 0.15,
                'debt': F['debt'], 'cash': F['cash'], 'claims': F['claims'], 'nonop': 0.0, 'shares': sh}
        r = dcf(base)
        if r['ok']:
            out['dcf'] = {'value': r['perShare'], 'ev': r['ev'], 'equity': r['equity'], 'tv_share': r['tv_share'],
                          'rows': [[x['t'], x['rev'], x['ebit'], x['fcff'], x['pv']] for x in r['rows']],
                          'assumptions': {k: base[k] for k in ('growth', 'margin', 'tax', 'da', 'capex', 'wc', 'wacc', 'g', 'roic')}}
            mk = markov.run(F, base, W, F.get('years'), (ctx.get('markov_prior') or {}).get(markov.bucket_of(F.get('mcap'))),
                            price, ctx.get('cons'), ctx.get('price_date'))
            if mk:
                out['markov'] = mk
                out['football'].append({'method': 'Regime-switching Monte Carlo 10th–90th', 'low': mk['p10'], 'high': mk['p90'],
                                        'point': mk['p50'], 'note': f"median {mk['p50']:.2f}; {mk['n']:,} paths, 10 years, Markov growth regimes"})
            if fin(price) and price > 0:
                s = solve({**base, 'growth': g0}, 'growth', price, -0.30, 0.60)
                out['reverse'] = {'status': s['status'], 'implied_growth': s.get('value'), 'history_growth': F['g0'],
                                  'note': 'the constant yearly revenue growth (5 years, then terminal) at which the model gives today\'s price'}
            sg = clamp(F['sg'], 0.03, 0.25) if fin(F['sg']) else 0.08
            sm = clamp(F['sm'], 0.01, 0.10) if fin(F['sm']) else 0.03
            mc = monte_carlo(base, price, sg, sm, seed=zlib.crc32(str(F['ticker']).encode()))
            if mc:
                out['mc'] = mc
                out['football'].append({'method': 'DCF — Monte Carlo 10th–90th percentile', 'low': mc['p10'], 'high': mc['p90'],
                                        'point': r['perShare'], 'note': f"base case {r['perShare']:.2f}; {mc['n']:,} scenarios"})
    elif not fin_kind and F['kind'] != 'reit':
        out['notes'].append('No DCF: operating income is not positive (or the figures are incomplete) — a cash-flow model on a loss would only restate the assumptions.')
    else:
        out['notes'].append('No free-cash-flow DCF: for banks, insurers and REITs the residual income and sector models below fit better.')
    # ---- PVGO
    if fin(F['mcap']) and F['mcap'] > 0 and W:
        if fin_kind and fin(F['ni']) and F['ni'] > 0:
            ng = F['ni'] / W['ke']
            out['pvgo'] = {'no_growth_equity': ng, 'per_share': ng / sh if fin(sh) and sh else None, 'growth_share': 1 - ng / F['mcap'],
                           'basis': 'net income ÷ cost of equity', 'earnings': F['ni'], 'rate': W['ke']}
        elif fin(F['oi']) and F['oi'] > 0:
            nopat = F['oi'] * (1 - F['tax_rate'])
            ng = nopat / W['wacc'] - F['debt'] + F['cash'] - F['claims']
            out['pvgo'] = {'no_growth_equity': ng, 'per_share': ng / sh if fin(sh) and sh else None, 'growth_share': 1 - ng / F['mcap'],
                           'basis': 'NOPAT ÷ WACC − net debt', 'earnings': nopat, 'rate': W['wacc']}
    # ---- peers
    peers = {}
    for metric, label, fn in (('pe', 'P/E vs peers', lambda m: m * F['eps'] if fin(F['eps']) and F['eps'] > 0 else None),
                              ('ev_ebitda', 'EV/EBITDA vs peers', lambda m: (m * F['ebitda'] - F['debt'] + F['cash'] - F['claims']) / sh
                               if fin(F['ebitda']) and F['ebitda'] > 0 and fin(sh) and sh else None),
                              ('ev_sales', 'EV/Sales vs peers', lambda m: (m * F['revenue'] - F['debt'] + F['cash'] - F['claims']) / sh
                               if fin(F['revenue']) and F['revenue'] > 0 and fin(sh) and sh else None)):
        if fin_kind and metric != 'pe':
            continue
        pr = peer_range(ctx['buckets'].get(metric, {}), F)
        if not pr:
            continue
        g, n, p25, p50, p75 = pr
        lo, mid, hi = fn(p25), fn(p50), fn(p75)
        own = F.get(metric) if fin(F.get(metric)) else ctx.get('own', {}).get(metric)
        peers[metric] = {'group': g, 'n': n, 'p25': p25, 'p50': p50, 'p75': p75, 'own': own}
        if fin(lo) and fin(hi) and fin(mid) and hi > 0:
            out['football'].append({'method': label, 'low': min(lo, hi), 'high': max(lo, hi), 'point': mid,
                                    'note': f'{n} peers ({group_label(g)}): median {p50:.1f}x, middle half {p25:.1f}–{p75:.1f}x'})
    out['peers'] = peers
    # ---- residual income
    if W and fin(F['equity']) and F['equity'] > 0 and fin(F['ni']) and fin(sh) and sh > 0:
        roe = F['ni'] / F['equity']
        ri = [residual_income(F['equity'], roe, W['ke'] + d) for d in (0.01, 0.0, -0.01)]
        if all(fin(v) for v in ri):
            out['residual_income'] = {'roe': roe, 'ke': W['ke'], 'book': F['equity'], 'value': ri[1] / sh}
            out['football'].append({'method': 'Residual income', 'low': ri[0] / sh, 'high': ri[2] / sh, 'point': ri[1] / sh,
                                    'note': f'book {F["equity"] / sh:.2f}/share, ROE {roe * 100:.1f}% fading to the {W["ke"] * 100:.1f}% cost of equity; ±1 pt'})
    # ---- sector models
    reg = ctx.get('regressions', {})
    if F['kind'] == 'bank':
        tbv = (F['equity'] or 0) - F['goodwill'] - F['intangibles']
        fit = reg.get('bank')
        if fit and tbv > 0 and fin(F['ni']) and fin(sh) and sh > 0:
            rotce = F['ni'] / tbv
            fitted = fit['a'] + fit['b'] * rotce
            band = (fit.get('se') or 0.3)
            out['sector_model'] = {'model': 'P/TBV vs ROTCE (banks)', 'tbv': tbv, 'rotce': rotce, 'ptbv': F['mcap'] / tbv if fin(F['mcap']) else None,
                             'fitted_ptbv': fitted, 'fit': fit}
            if fitted > 0:
                out['football'].append({'method': 'P/TBV vs ROTCE (bank peers)', 'low': max(0, fitted - band) * tbv / sh, 'high': (fitted + band) * tbv / sh,
                                        'point': fitted * tbv / sh, 'note': f'ROTCE {rotce * 100:.1f}% → fitted P/TBV {fitted:.2f}x across {fit["n"]} banks'})
    elif F['kind'] == 'insurer':
        fit = reg.get('insurer')
        sec = {'model': 'P/B vs ROE (insurers)', 'combined_ratio': F.get('combined_ratio'), 'combined_ratio_parts': F.get('combined_ratio_parts')}
        if fit and fin(F['equity']) and F['equity'] > 0 and fin(F['ni']) and fin(sh) and sh > 0:
            roe = F['ni'] / F['equity']
            fitted = fit['a'] + fit['b'] * roe
            band = fit.get('se') or 0.3
            sec.update({'roe': roe, 'pb': F['mcap'] / F['equity'] if fin(F['mcap']) else None, 'fitted_pb': fitted, 'fit': fit})
            if fitted > 0:
                out['football'].append({'method': 'P/B vs ROE (insurer peers)', 'low': max(0, fitted - band) * F['equity'] / sh,
                                        'high': (fitted + band) * F['equity'] / sh, 'point': fitted * F['equity'] / sh,
                                        'note': f'ROE {roe * 100:.1f}% → fitted P/B {fitted:.2f}x across {fit["n"]} insurers'})
        out['sector_model'] = sec
    elif F['kind'] == 'reit':
        sec = {'model': 'P/FFO (REITs)', 'ffo': F.get('ffo'), 'ffo_parts': F.get('ffo_parts'),
               'note': 'FFO ≈ net income + D&A − gains on property sales (NAREIT also adds impairments). AFFO is not standardized in XBRL and is not shown.'}
        ffo = F.get('ffo')
        if fin(ffo) and ffo > 0 and fin(F['mcap']):
            sec['p_ffo'] = F['mcap'] / ffo
            pr = peer_range(ctx['buckets'].get('p_ffo', {}), F)
            if pr and fin(sh) and sh > 0:
                g, n, p25, p50, p75 = pr
                sec['peers'] = {'n': n, 'p25': p25, 'p50': p50, 'p75': p75}
                out['football'].append({'method': 'P/FFO vs REIT peers', 'low': p25 * ffo / sh, 'high': p75 * ffo / sh, 'point': p50 * ffo / sh,
                                        'note': f'{n} REITs: median {p50:.1f}x FFO'})
        out['sector_model'] = sec
    # ---- sum of the parts
    so = sotp(ctx.get('segments') or [], ctx['buckets'].get('ev_sales', {}), F, sh, F['debt'] - F['cash'] + F['claims']) if not fin_kind else None
    if so:
        out['sotp'] = so
        out['football'].append({'method': 'Sum of the parts (segments × peer EV/Sales)', 'low': so['low'], 'high': so['high'], 'point': so['point'],
                                'note': so['note']})
    # ---- the market's and the analysts' numbers
    cons = ctx.get('cons') or {}
    a = cons.get('analysts') or {}
    T = a.get('targets') or {}
    if fin(T.get('mean')):
        lo, hi = (T.get('low') if fin(T.get('low')) else T['mean']), (T.get('high') if fin(T.get('high')) else T['mean'])
        out['football'].append({'method': "Analysts' price targets", 'low': lo, 'high': hi, 'point': T['mean'],
                                'note': f"{int(T['n'])} analysts, mean {T['mean']:.2f}" if fin(T.get('n')) else f"mean {T['mean']:.2f}"})
    pm = ctx.get('pm') or {}
    if fin(pm.get('price')):
        b = pm.get('bounds') or []
        lo = b[0] if len(b) == 2 and fin(b[0]) else pm['price']
        hi = b[1] if len(b) == 2 and fin(b[1]) else pm['price']
        out['football'].append({'method': 'Polymarket implied price', 'low': lo, 'high': hi, 'point': pm['price'],
                                'note': f"by {pm.get('date')}" if pm.get('date') else 'nearest dated market'})
    ours = next((o for o in cons.get('ours') or [] if o.get('horizon') == 'next quarter'), None) or (cons.get('ours') or [None])[0]
    if ours and fin(ours.get('price')):
        out['football'].append({'method': "Our model (Rotation forecast)", 'low': ours.get('lo80') if fin(ours.get('lo80')) else ours['price'],
                                'high': ours.get('hi80') if fin(ours.get('hi80')) else ours['price'], 'point': ours['price'],
                                'note': f"{ours.get('horizon')}, 80% range, to {ours.get('date')}"})
    rng52 = ctx.get('range52')
    if rng52:
        out['football'].append({'method': '52-week trading range', 'low': rng52[0], 'high': rng52[1], 'point': None, 'note': 'context, not a valuation'})
    # ---- bands
    if ctx.get('bands'):
        out['bands'] = ctx['bands']
    # ---- credit
    dr = ctx.get('debt') or {}
    an = dr.get('analysis') or {}
    imp = an.get('implied') or {}
    mpd, dd_ = imp.get('pd_1y'), imp.get('dd')
    if not fin(mpd) and fin(F['mcap']) and F['debt'] > 0 and ctx.get('vol'):
        try:
            import debt_model as DM
            m = DM.implied(F['mcap'], ctx['vol'], None, F['debt'], (ctx['rates'].get('treasury_1y') or 4.0) / 100)
            if m:
                mpd, dd_ = m['pd_1y'], m['dd']
        except Exception:                                   # noqa: BLE001
            pass
    spread = imp.get('calibrated_5y_bps') or imp.get('spread_5y_bps')
    D = distress(mpd, None if an.get('bank') else spread, None if fin_kind else an.get('altman_z'), an.get('cushion_score'))
    out['credit'] = {'distance_to_default': dd_, 'merton_pd_1y': mpd, 'cds_5y_bps': spread, 'rating_band': imp.get('rating_band'),
                     'altman_z': an.get('altman_z'), 'cushion_score': an.get('cushion_score'), 'effective_rate': an.get('effective_rate'),
                     'interest_coverage': an.get('interest_coverage'), 'distress': D,
                     'note': 'Distress blends up to four one-year default probabilities in log-odds. It is NOT calibrated against realized defaults; read it as a ranking.'}
    # ---- the outside view: base rates, consensus odds, stage, sensitivity, river, combined forecast (app/base_rates.py)
    out['_regs'] = reg
    if ctx.get('br'):
        BR.enrich(sys.modules[__name__], out, F, base if 'dcf' in out else None, W, ctx)
    out.pop('_regs', None)
    # ---- the appendix: inputs and sources, assumptions, the WACC and every method's algebra (app/valuation_methods.py)
    VMx.appendix(sys.modules[__name__], out, F, W, ctx.get('rates') or {})
    # ---- headline numbers for the index
    lows = [b['low'] for b in out['football'] if fin(b.get('low')) and b['method'] != '52-week trading range']
    highs = [b['high'] for b in out['football'] if fin(b.get('high')) and b['method'] != '52-week trading range']
    out['range'] = [min(lows), max(highs)] if lows and highs else None
    return out


def group_label(g):
    if g.startswith('sec:'):
        return 'sector ' + g[4:]
    return f'SIC {g[3:]}'


# ------------------------------------------------------------------ the ledger: frozen monthly snapshots, scored later
def ledger_update(root, rows, prices_dir, today=None):
    """Freeze this month's snapshot once (ticker → [price, DCF value, P(value > price), distress]), then score every older
    snapshot at 3, 6 and 12 months: Spearman IC of P(value > price) and of the DCF gap vs the forward return, and how often
    the price moved toward the DCF value."""
    today = today or dt.date.today()
    month = today.strftime('%Y-%m')
    ldir = Path(root) / 'cache' / 'ledger'
    p = ldir / f'{month}.json'
    if not p.exists() and rows:
        snap = {r['ticker']: [r['price'], r.get('dcf_value'), r.get('mc_p_above'), r.get('distress_pd'), r.get('target_mean'), r.get('pm_price'),
                              r.get('ov_mean'), (r['price'] * (1 + r['comb_ret'])) if fin(r.get('comb_ret')) else None, r.get('stage_value')]
                for r in rows if r.get('ticker') and fin(r.get('price'))}
        write_json(p, {'frozen_at': now(), 'month': month, 'fields': LEDGER_FIELDS, 'rows': snap})
    scores = []
    cache = {}

    def px_at(t, day):
        if t not in cache:
            cache[t] = load_prices(prices_dir, t)
        d = cache[t]
        i = bisect.bisect_right([x[0] for x in d], day) - 1
        return d[i][1] if i >= 0 else None
    for f in sorted(ldir.glob('*.json')):
        L = read_json(f, {}) or {}
        frozen = (L.get('frozen_at') or '')[:10]
        if not frozen:
            continue
        for h in (3, 6, 12):
            due = (dt.date.fromisoformat(frozen) + dt.timedelta(days=round(h * 30.44))).isoformat()
            if due > today.isoformat():
                continue
            pa, gap, hits = [], [], 0
            n_gap = n_ret = up = 0
            extra = {k: [] for k in LEDGER_SCORED}
            comb_err = zero_err = 0.0
            n_comb = 0
            for t, r in (L.get('rows') or {}).items():
                px, val, pab = (r + [None] * 3)[:3]
                end = px_at(t, due)
                if not (fin(px) and fin(end) and px > 0):
                    continue
                ret = end / px - 1
                n_ret += 1
                up += ret > 0
                if fin(pab):
                    pa.append((pab, ret))
                if fin(val) and val > 0:
                    g = val / px - 1
                    gap.append((g, ret))
                    n_gap += 1
                    hits += (g > 0) == (ret > 0)
                for k, i in LEDGER_SCORED.items():
                    v = r[i] if len(r) > i else None
                    if fin(v) and v > 0:
                        extra[k].append((v / px - 1, ret))
                cp = r[7] if len(r) > 7 else None
                if h == 3 and fin(cp) and cp > 0:
                    n_comb += 1
                    comb_err += abs(ret - (cp / px - 1))
                    zero_err += abs(ret)
            sc = {'month': L.get('month'), 'horizon_months': h, 'n': len(pa), 'ic_p_above': spearman(pa), 'ic_dcf_gap': spearman(gap),
                  'direction_hit_rate': hits / n_gap if n_gap else None, 'share_up': up / n_ret if n_ret else None,
                  **{f'ic_{k}': spearman(v) for k, v in extra.items()}, **{f'n_{k}': len(v) for k, v in extra.items()}}
            if n_comb:
                sc.update({'n_combined': n_comb, 'mae_combined': comb_err / n_comb, 'mae_no_change': zero_err / n_comb})
            scores.append(sc)
    snaps = sorted(f.stem for f in ldir.glob('*.json'))
    return {'generated_at': now(), 'snapshots': snaps, 'scores': scores,
            'note': 'A snapshot is frozen on the first build of each month and never changed. Scores appear 3, 6 and 12 months later. '
                    'share_up is the naive baseline for the direction hit rate; mae_no_change the naive baseline for the combined forecast.'}


LEDGER_FIELDS = ['price', 'dcf_value', 'mc_p_above', 'distress_pd', 'target_mean', 'pm_price', 'outside_mean', 'combined_price', 'stage_value']
LEDGER_SCORED = {'target_gap': 4, 'pm_gap': 5, 'outside_gap': 6, 'combined_gap': 7, 'stage_gap': 8}


def spearman(pairs):
    if len(pairs) < 10:
        return None
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    a, b = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else None


# ------------------------------------------------------------------ build
INDEX_FIELDS = ['cik', 'ticker', 'name', 'sector', 'kind', 'price', 'mcap', 'wacc', 'beta', 'kd', 'dcf_value', 'dcf_gap', 'mc_p_above', 'mc_p10', 'mc_p90',
                'implied_growth', 'history_growth', 'pvgo_share', 'pe', 'pe_pct', 'evs', 'evs_pct', 'peer_pe_mid', 'target_mean', 'pm_price', 'our_price',
                'range_low', 'range_high', 'distress_pd', 'distance_to_default', 'altman_z', 'cds_bps', 'ri_value', 'sector_value', 'combined_ratio', 'p_ffo',
                # the outside view (app/base_rates.py)
                'stage', 'stage_value', 'p_implied', 'p_implied_in', 'peer_group', 'peer_n', 'req_eps_g', 'p_street_eps', 'p_street_eps_in', 'p_street_rev',
                'req_rev_g', 'target_growth', 'p_target', 'pm_eps_strike', 'pm_req_eps_g', 'p_pm_eps_base', 'pm_beat_prob', 'p_pm_price',
                'ov_mean', 'ov_p10', 'ov_p90', 'ov_p_above', 'comb_ret', 'comb_lo', 'comb_hi', 'sens_driver', 'sens_swing', 'river_pe_pct',
                # the regime-switching Monte Carlo (app/markov.py)
                'mk_p50', 'mk_p_above', 'mk_state']


def outside_fields(A):
    """The outside-view columns of the index row."""
    co = A.get('consensus_odds') or {}
    mk, se, sr, st, pe, pp = (co.get(k) or {} for k in ('market', 'street_eps', 'street_rev', 'street_target', 'pm_eps', 'pm_price'))
    ov = (A.get('outside_view') or {}).get('mc') or {}
    cb = A.get('combined') or {}
    sens = A.get('sensitivity') or {}
    stg = A.get('stage') or {}
    rv = ((A.get('river') or {}).get('metrics') or {}).get('pe') or {}
    return {'stage': stg.get('stage'), 'stage_value': stg.get('value'), 'p_implied': mk.get('p_outside'), 'p_implied_in': mk.get('p_inside'),
            'peer_group': mk.get('group_label'), 'peer_n': mk.get('n'), 'req_eps_g': se.get('required'), 'p_street_eps': se.get('p_outside'),
            'p_street_eps_in': se.get('p_inside'), 'p_street_rev': sr.get('p_outside'), 'req_rev_g': sr.get('required'),
            'target_growth': st.get('required'), 'p_target': st.get('p_outside'), 'pm_eps_strike': pe.get('strike'), 'pm_req_eps_g': pe.get('required'),
            'p_pm_eps_base': pe.get('p_outside'), 'pm_beat_prob': pe.get('p_market'), 'p_pm_price': pp.get('p_outside'),
            'ov_mean': ov.get('mean'), 'ov_p10': ov.get('p10'), 'ov_p90': ov.get('p90'), 'ov_p_above': ov.get('p_above'),
            'comb_ret': cb.get('ret'), 'comb_lo': cb.get('lo'), 'comb_hi': cb.get('hi'), 'sens_driver': sens.get('driver'),
            'sens_swing': sens.get('driver_swing'), 'river_pe_pct': rv.get('pct')}


def _load_dir(d, name, default=None):
    return read_json(Path(d) / name, default) if d else default


def build(root, prices=None, debt=None, consensus=None, today=None, verbose=True, limit=None, rotation=None):
    root = Path(root)
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today()
    site_ix = read_json(root / 'site' / 'index.json', {}) or {}
    companies = site_ix.get('companies') if isinstance(site_ix, dict) else site_ix
    companies = [c for c in companies or [] if c.get('ticker') and c.get('cik')]
    periods = calendar_quarters(QUARTERS, today)
    P = panel(root, periods)
    M = sys.modules[__name__]
    debt_ix = _load_dir(debt, 'index.json', {}) or {}
    rates_doc = _load_dir(debt, 'rates.json', {}) or {}
    mk = debt_ix.get('market') or {}
    rates = {'treasury_1y': as_pct(mk.get('treasury_1y')), 'treasury_5y': as_pct(mk.get('treasury_5y')),
             'treasury_10y': as_pct(_rate10(rates_doc) or mk.get('treasury_10y'))}
    cons_ix = _load_dir(consensus, 'index.json', {}) or {}
    CF = cons_ix.get('fields') or []
    cons_rows = {str(r[CF.index('cik')]): dict(zip(CF, r)) for r in cons_ix.get('rows') or [] if 'cik' in CF and r[CF.index('cik')]}
    prices = [prices, root / 'cache' / 'prices']            # the hub's closes, then this branch's top-up (collect_prices)
    spy = load_prices(prices, 'SPY')
    # pass 1: inputs and multiples for every company
    Fs = {}
    for meta in companies:
        cik = str(meta['cik'])
        px = load_prices(prices, meta['ticker'])
        if not px:
            continue
        slim = read_json(root / 'site' / 'c' / f'{cik}.json.gz', {}) or {}
        drec = _load_dir(debt, f'c/{cik}.json')
        cons_c = _load_dir(consensus, f'c/{cik}.json') or {}
        F = company_inputs(cik, meta, P.get(cik), slim, drec, cons_c, px[-1][1], periods)
        F['_px'], F['_slim'], F['_debt'], F['_cons'] = px, slim, drec, cons_c
        if fin(F['mcap']) and F['mcap'] > 0:
            F['pe'] = F['price'] / F['eps'] if fin(F['eps']) and F['eps'] > 0 and F['price'] / F['eps'] <= 200 else None
            F['ev_ebitda'] = F['ev'] / F['ebitda'] if fin(F['ev']) and fin(F['ebitda']) and F['ebitda'] > 0 and 0 < F['ev'] / F['ebitda'] <= 100 else None
            F['ev_sales'] = F['ev'] / F['revenue'] if fin(F['ev']) and fin(F['revenue']) and F['revenue'] > 0 and 0 < F['ev'] / F['revenue'] <= 50 else None
            F['p_ffo'] = F['mcap'] / F['ffo'] if F['kind'] == 'reit' and fin(F.get('ffo')) and F['ffo'] > 0 and F['mcap'] / F['ffo'] <= 80 else None
            Fs[cik] = F
        if limit and len(Fs) >= limit:
            break
    # cost of capital for every company first (the WACC base rate needs the peers' WACCs)
    for F in Fs.values():
        F['_beta'] = beta(F['_px'], spy) if spy else None
        F['_W'] = wacc_of(F, rates, F['_debt'], F['_beta'])
    # the outside view: peer distributions (frames since 2020 and CY2010, multiples at every quarter since mid-2022)
    sic_of = {str(c['cik']): str(c.get('sic') or '') for c in companies}
    names = BR.industry_names(companies)
    D = BR.Dists()
    hist_info = BR.add_history(D, root, M, P, periods, sic_of)
    for cik, F in Fs.items():
        size = BR.size_of(F.get('revenue'))
        for m in ('pe', 'ev_sales', 'ev_ebitda'):
            D.add(m, F.get(m), F.get('sic'), size, today.year, cik)
        D.add('wacc', (F['_W'] or {}).get('wacc'), F.get('sic'), size, today.year, cik)
    o_rows, o_live = BR.origin_rows(M, Fs, P, periods, sic_of, today)
    for r in o_rows:
        F = Fs[r['cik']]
        if fin(r.get('e4')) and r['e4'] > 0 and fin(r['price']) and 0 < r['price'] / r['e4'] <= 200:
            D.add('pe_hist', r['price'] / r['e4'], r['sic'], r['size'], int(r['date'][:4]), r['cik'])
        if fin(r.get('shares')) and fin(r['price']) and r['r4'] > 0:
            evs = (r['price'] * r['shares'] + (F['debt'] or 0) - (F['cash'] or 0) + (F['claims'] or 0)) / r['r4']
            if 0 < evs <= 50:
                D.add('evs_hist', evs, r['sic'], r['size'], int(r['date'][:4]), r['cik'])
    D.finish({int(r['date'][:4]) for r in o_rows}, ('cagr5',))

    def cons_of(cik):
        snaps = (Fs[cik].get('_cons') or {}).get('snapshots') or []
        return [(d, v[5]) for d, v in snaps if isinstance(v, list) and len(v) > 5 and fin(v[5])]
    comb = BR.combined_model(M, Fs, o_rows, o_live, D, cons_of, today)
    paired = []
    rot = BR.score_rotation(rotation, read_json, paired, {F['ticker']: cik for cik, F in Fs.items()})
    pc = BR.pair_with_combined(paired, comb.get('_pred') or {})
    c3 = ((comb['horizons'].get('3m') or {}).get('scores') or {}).get('combined') or {}
    rq = (rot or {}).get('next quarter') or {}
    rcov = (rq.get('live') or rq.get('backtest') or {}).get('coverage80')
    comb['paired_with_rotation'] = pc
    comb['replace_rotation'] = bool(pc.get('n', 0) >= 200 and pc['mae_combined'] < 0.98 * pc['mae_rotation'] and fin(c3.get('coverage80'))
                                    and abs(c3['coverage80'] - 0.8) <= (abs(rcov - 0.8) if fin(rcov) else 1.0) + 0.05)
    br_ctx = {'D': D, 'names': names, 'periods': periods, 'combined': comb}
    rows_all = list(Fs.values())
    buckets = {m: peer_stats([r for r in rows_all if (m != 'p_ffo' or r['kind'] == 'reit')], m) for m in ('pe', 'ev_ebitda', 'ev_sales', 'p_ffo')}
    # cross-section fits for banks and insurers
    regs = {}
    pts = {'bank': [], 'insurer': []}
    for r in rows_all:
        if r['kind'] == 'bank' and fin(r['equity']) and fin(r['ni']) and fin(r['mcap']):
            tbv = r['equity'] - r['goodwill'] - r['intangibles']
            if tbv > 0:
                x, y = r['ni'] / tbv, r['mcap'] / tbv
                if 0 < x < 0.4 and 0.2 < y < 5:
                    pts['bank'].append((x, y, r['ticker']))
        if r['kind'] == 'insurer' and fin(r['equity']) and r['equity'] > 0 and fin(r['ni']) and fin(r['mcap']):
            x, y = r['ni'] / r['equity'], r['mcap'] / r['equity']
            if -0.1 < x < 0.5 and 0.2 < y < 8:
                pts['insurer'].append((x, y, r['ticker']))
    for k, xs in pts.items():
        if len(xs) >= 12:
            regs[k] = ols([p[0] for p in xs], [p[1] for p in xs])
            if regs[k]:
                regs[k]['points'] = [[round(p[0], 4), round(p[1], 3), p[2]] for p in xs]
    regs['rule40'] = VMx.rule40_fit(rows_all)          # ln(EV/Sales) on growth + FCF margin, every non-financial company
    # the regime model's prior: transitions, regime growth and margin behaviour across every covered company, by size
    mk_prior = markov.panel_prior({'years': r.get('years'), 'mcap': r.get('mcap')} for r in rows_all)
    write_json(pub / 'markov.json', clean({'generated_at': now(), 'thresholds': {'high': markov.THRESH_HIGH, 'decline': markov.THRESH_LOW},
                                           'k': markov.K_PRIOR, 'buckets': mk_prior}))
    # pass 2: the full analysis
    index, n_dcf = [], 0
    for cik, F in Fs.items():
        px, slim, drec, cons_c = F.pop('_px'), F.pop('_slim'), F.pop('_debt'), F.pop('_cons')
        b = F.pop('_beta', None)
        F.pop('_W', None)
        crow = cons_rows.get(cik) or {}
        pm = {}
        if fin(crow.get('pm_implied_price')):
            pm = {'price': crow['pm_implied_price'], 'date': crow.get('pm_price_date')}
            m = next((m for m in cons_c.get('markets') or [] if isinstance(m.get('implied_price'), dict) and fin(m['implied_price'].get('median'))
                      and abs(m['implied_price']['median'] - crow['pm_implied_price']) < 0.01), None)
            ip = (m or {}).get('implied_price') or {}
            if fin(ip.get('q10')) and fin(ip.get('q90')):
                pm['bounds'] = [ip['q10'], ip['q90']]
        last_year = [c for d, c in px if d >= (dt.date.fromisoformat(px[-1][0]) - dt.timedelta(days=365)).isoformat()]
        sh = F['shares']
        bd = bands(px, periods, F['eps_q'], F['rev_q'], sh, F['debt'] - F['cash'] + F['claims']) if fin(sh) else None
        ctx = {'rates': rates, 'buckets': buckets, 'regressions': regs, 'debt': drec, 'cons': cons_c, 'pm': pm, 'beta': b,
               'vol': annual_vol(px), 'segments': segments_of(slim), 'range52': [min(last_year), max(last_year)] if last_year else None,
               'bands': bd, 'price_date': px[-1][0], 'br': br_ctx, 'panel': P.get(cik) or {}, 'crow': crow,
               'river': BR.river(M, px, periods, P.get(cik), F) if fin(sh) else None, 'markov_prior': mk_prior}
        A = analyse(F, ctx)
        write_json(pub / 'c' / f'{cik}.json', clean(A))
        n_dcf += 'dcf' in A
        W = A.get('wacc') or {}
        mc = A.get('mc') or {}
        cr = A.get('credit') or {}
        sec = A.get('sector_model') or {}
        sec_val = next((x['point'] for x in A['football'] if x['method'].startswith(('P/TBV', 'P/B vs ROE', 'P/FFO'))), None)
        row = {'cik': int(cik), 'ticker': F['ticker'], 'name': F['name'], 'sector': F['sector'], 'kind': F['kind'], 'price': F['price'], 'mcap': F['mcap'],
               'wacc': W.get('wacc'), 'beta': W.get('beta'), 'kd': W.get('kd'), 'dcf_value': (A.get('dcf') or {}).get('value'),
               'mc_p_above': mc.get('p_above'), 'mc_p10': mc.get('p10'), 'mc_p90': mc.get('p90'),
               'implied_growth': (A.get('reverse') or {}).get('implied_growth'), 'history_growth': F['g0'],
               'pvgo_share': (A.get('pvgo') or {}).get('growth_share'), 'pe': F.get('pe'), 'pe_pct': ((bd or {}).get('pe') or {}).get('pct'),
               'evs': F.get('ev_sales'), 'evs_pct': ((bd or {}).get('evs') or {}).get('pct'),
               'peer_pe_mid': ((A.get('peers') or {}).get('pe') or {}).get('p50'), 'target_mean': ((cons_c.get('analysts') or {}).get('targets') or {}).get('mean'),
               'pm_price': pm.get('price'), 'our_price': crow.get('our_price'), 'range_low': (A.get('range') or [None, None])[0],
               'range_high': (A.get('range') or [None, None])[1], 'distress_pd': (cr.get('distress') or {}).get('pd'),
               'distance_to_default': cr.get('distance_to_default'), 'altman_z': cr.get('altman_z'), 'cds_bps': cr.get('cds_5y_bps'),
               'ri_value': (A.get('residual_income') or {}).get('value'), 'sector_value': sec_val, 'combined_ratio': sec.get('combined_ratio'),
               'p_ffo': sec.get('p_ffo')}
        mk = A.get('markov') or {}
        row.update({'mk_p50': mk.get('p50'), 'mk_p_above': mk.get('p_above'),
                    'mk_state': markov.STATES[mk['model']['start']] if mk.get('model') else None})
        row['dcf_gap'] = row['dcf_value'] / row['price'] - 1 if fin(row['dcf_value']) and fin(row['price']) and row['price'] > 0 else None
        row.update(outside_fields(A))
        index.append(row)
    index.sort(key=lambda r: -(r['mcap'] or 0))
    write_json(pub / 'index.json', clean({'generated_at': now(), 'fields': INDEX_FIELDS, 'rows': [[r.get(k) for k in INDEX_FIELDS] for r in index],
                                          'assumptions': {'erp': ERP, 'terminal_growth': TERM_G, 'years': YEARS, 'mc_scenarios': MC_N,
                                                          'treasury_10y': rates.get('treasury_10y'), 'treasury_5y': rates.get('treasury_5y')}}))
    write_json(pub / 'peers.json', clean({'generated_at': now(), 'metrics': {m: {g: {'n': len(xs), 'p25': pctile([v for _, v in xs], .25),
                                                                                       'p50': pctile([v for _, v in xs], .5), 'p75': pctile([v for _, v in xs], .75)}
                                                                                   for g, xs in b.items()} for m, b in buckets.items()}}))
    write_json(pub / 'banks.json', clean({'generated_at': now(), 'fit': regs.get('bank'), 'x': 'ROTCE', 'y': 'P/TBV'}))
    write_json(pub / 'insurers.json', clean({'generated_at': now(), 'fit': regs.get('insurer'), 'x': 'ROE', 'y': 'P/B'}))
    led = ledger_update(root, index, prices, today)
    write_json(pub / 'ledger.json', clean(led))
    write_json(pub / 'base_rates.json', clean({'generated_at': now(), 'min_obs': BR.MIN_OBS, 'min_companies': BR.MIN_COS, 'sizes': BR.SIZE_LABEL,
                                               'history': hist_info, 'metrics': BR.METRIC_LABEL, 'groups': BR.published_groups(D, names),
                                               'note': BR.__doc__.split('\n\n')[1]}))
    models = BR.models_doc(comb, led, rot, read_json(root / 'site' / 'model.json', {}) or {}, _load_dir(consensus, 'calibration.json', {}) or {})
    write_json(pub / 'models.json', clean(models))
    st = {'built_at': now(), 'companies': len(index), 'with_dcf': n_dcf, 'banks_fit': (regs.get('bank') or {}).get('n'),
          'rule40_fit': (regs.get('rule40') or {}).get('n'),
          'insurers_fit': (regs.get('insurer') or {}).get('n'), 'frames_companies': len(P), 'ledger_snapshots': len(led['snapshots']),
          'base_rate_windows': hist_info.get('five_year_windows'), 'combined_rows': comb.get('rows'),
          'with_stage': sum(1 for r in index if r.get('stage')), 'with_outside_mc': sum(1 for r in index if fin(r.get('ov_mean'))),
          'with_markov': sum(1 for r in index if fin(r.get('mk_p50'))),
          'markov_panel': {b: {'firms': v['firms'], 'transitions': v['transitions']} for b, v in mk_prior.items()}}
    write_json(pub / 'status.json', st)
    if verbose:
        print('valuation build: ' + json.dumps(st), flush=True)
    return st


def as_pct(v):
    """A rate in percent: app/debt.py keeps decimals (0.0425) in index.json and FRED's percent (4.25) in rates.json."""
    return (v * 100 if abs(v) < 0.3 else v) if fin(v) else None


def _rate10(rates_doc):
    """The latest 10-year Treasury (%) from app/debt.py's rates.json, whatever its exact layout."""
    if not isinstance(rates_doc, dict):
        return None
    for key in ('latest', 'now', 'current'):
        v = (rates_doc.get(key) or {}).get('DGS10') if isinstance(rates_doc.get(key), dict) else None
        if fin(v):
            return v
    s = (rates_doc.get('series') or {}).get('DGS10') if isinstance(rates_doc.get('series'), dict) else None
    if isinstance(s, dict):
        if isinstance(s.get('last'), (list, tuple)) and len(s['last']) > 1 and fin(s['last'][1]):
            return s['last'][1]
        s = s.get('daily') or s.get('monthly') or s.get('data')
    if isinstance(s, list) and s:
        last = s[-1]
        v = last[1] if isinstance(last, (list, tuple)) and len(last) > 1 else last
        return v if fin(v) else None
    return None


# ------------------------------------------------------------------ collect
class Http:
    def __init__(self, ua, interval=0.12, timeout=40, retries=4):
        self.ua, self.interval, self.timeout, self.retries, self.last = ua, interval, timeout, retries, 0.0

    def get(self, url):
        err = None
        for i in range(self.retries):
            time.sleep(max(0.0, self.interval - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={'User-Agent': self.ua, 'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read()
                    if r.headers.get('Content-Encoding') == 'gzip':
                        body = gzip.decompress(body)
                    return json.loads(body.decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise
                err = e
                time.sleep(2 * (i + 1) if e.code in (429, 503) else 1)
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
                err = e
                time.sleep(1 + i)
        raise err or RuntimeError('request failed')


def collect_frames(root, http, quarters=QUARTERS, refresh_days=3, deadline=None, today=None):
    """Fetch the frames the build needs; final periods once, the last two quarters / years every few days."""
    root = Path(root)
    state = read_json(root / 'cache' / 'frames' / 'state.json', {}) or {}
    periods = calendar_quarters(quarters, today)
    years = sorted({p[:6] for p in periods})
    recent = set(periods[-2:]) | set(years[-2:])
    fresh_after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=refresh_days)).isoformat()
    fetched = errors = 0
    jobs = []
    history = [f'CY{y}' for y in range(BR.ANNUAL_FROM, int(years[0][2:6]))]      # the annual base-rate windows since CY2010
    for tax, concept, unit, kind in CONCEPTS:
        if kind == 'q':
            jobs += [(tax, concept, unit, p, False) for p in periods + years]
        elif kind == 'a':
            jobs += [(tax, concept, unit, y, True) for y in years[-4:]]
        elif kind == 'iq':
            jobs += [(tax, concept, unit, p + 'I', False) for p in periods]
        else:
            jobs += [(tax, concept, unit, p + 'I', False) for p in periods[-6:]]
    for tax, concept, unit, kind in CONCEPTS:                                      # last: the long history (final, fetched once)
        if kind == 'q' and (concept in REVENUE or concept in BR.HISTORY_CONCEPTS):
            jobs += [(tax, concept, unit, y, True) for y in history]
    for tax, concept, unit, period, _ in jobs:
        if deadline and time.monotonic() > deadline:
            break
        key = f'{concept}-{period}'
        p = frame_path(root, concept, period)
        base_period = period[:-1] if period.endswith('I') else period
        if p.exists() and (base_period not in recent or (state.get(key) or '') > fresh_after):
            continue
        annual = len(base_period) == 6
        try:
            body = http.get(FRAMES.format(tax=tax, concept=concept, unit=unit, period=period))
            rows = [r for r in body.get('data', []) if fin(r.get('val'))]
            vals = {str(r['cik']): [r['val'], r.get('end')] for r in rows} if annual else {str(r['cik']): r['val'] for r in rows}
        except urllib.error.HTTPError as e:
            if e.code != 404:
                errors += 1
                print(f'frames {key}: HTTP {e.code}', flush=True)
                continue
            vals = {}
        except Exception as e:                              # noqa: BLE001
            errors += 1
            print(f'frames {key}: {str(e)[:120]}', flush=True)
            continue
        write_json(p, vals, gz=True)
        state[key] = now()
        fetched += 1
    write_json(root / 'cache' / 'frames' / 'state.json', state)
    return {'fetched': fetched, 'errors': errors, 'jobs': len(jobs)}


def slim_company(c):
    """What the build keeps of a main-site company file: the trailing figures, the revenue history, the segments."""
    q = (c.get('quality') or {})
    V = {k: v for k, v in (q.get('val') or {}).items() if k != 'refs' and not k.startswith('b_') and not isinstance(v, (dict, list))}
    revs = [x.get('wc', {}).get('rev') for x in q.get('q') or [] if isinstance(x.get('wc'), dict)]
    q0 = (c.get('quarters') or [{}])[0]
    nodes = [{'id': n.get('id'), 'name': n.get('name')} for n in q0.get('nodes') or [] if str(n.get('id', '')).startswith(('L:', 'G:'))]
    links = [{'s': l.get('s'), 't': l.get('t'), 'v': l.get('v')} for l in q0.get('links') or [] if l.get('color') == 'rev']
    return {'val': V, 'rev_q': revs, 'nodes': nodes, 'links': links, 'end': q0.get('end')}


def collect_site(root, site_url, limit=1500, workers=12, deadline=None):
    """The published site's company list and, for the largest companies with a ticker, their slim figures."""
    root = Path(root)
    base = site_url.rstrip('/')
    http = Http(UA, interval=0.0, timeout=30, retries=3)
    ix = http.get(base + '/data/index.json')
    write_json(root / 'site' / 'index.json', ix)
    cos = ix.get('companies') if isinstance(ix, dict) else ix
    cos = sorted([c for c in cos if c.get('ticker') and c.get('cik')], key=lambda c: -(c.get('revenue') or 0))[:limit]
    state = read_json(root / 'site' / 'state.json', {}) or {}
    todo = [c for c in cos if state.get(str(c['cik'])) != (c.get('filed') or c.get('end'))
            or not (root / 'site' / 'c' / f"{c['cik']}.json.gz").exists()]

    def one(c):
        if deadline and time.monotonic() > deadline:
            return c, None, 'budget'
        try:
            return c, slim_company(http.get(f"{base}/data/c/{c['cik']}.json")), None
        except Exception as e:                              # noqa: BLE001
            return c, None, str(e)[:80]
    got = errs = 0
    with ThreadPoolExecutor(workers) as pool:
        for c, s, err in pool.map(one, todo):
            if s is not None:
                write_json(root / 'site' / 'c' / f"{c['cik']}.json.gz", s, gz=True)
                state[str(c['cik'])] = c.get('filed') or c.get('end')
                got += 1
            elif err != 'budget':
                errs += 1
    write_json(root / 'site' / 'state.json', state)
    try:                                                    # the hierarchical revenue model's scores (pipeline/hier.py)
        write_json(root / 'site' / 'model.json', http.get(base + '/data/model/index.json'))
    except Exception:                                       # noqa: BLE001
        pass
    return {'companies': len(cos), 'fetched': got, 'errors': errs, 'cached': len(cos) - len(todo)}


HUB_PRICES = Path(__file__).resolve().parents[1] / 'docs' / 'data' / 'cache' / 'prices'


def collect(root, site_url, minutes=20.0, limit=1500, hub_prices=HUB_PRICES):
    t0 = time.monotonic()
    deadline = t0 + minutes * 60
    ua = os.environ.get('SEC_USER_AGENT', '').strip()
    out = {}
    if site_url:
        try:
            out['site'] = collect_site(root, site_url, limit=limit, deadline=t0 + minutes * 30)
        except Exception as e:                              # noqa: BLE001
            out['site'] = {'error': str(e)[:160]}
        try:                                                # closes for the companies the hub does not price
            out['prices'] = collect_prices(root, hub_prices, limit=limit, minutes=min(6.0, minutes / 3), site_url=site_url)
        except Exception as e:                              # noqa: BLE001
            out['prices'] = {'error': str(e)[:160]}
    if '@' in ua:
        out['frames'] = collect_frames(root, Http(ua), deadline=deadline)
    else:
        out['frames'] = {'skipped': 'SEC_USER_AGENT (name + contact e-mail) is not set'}
    out['seconds'] = round(time.monotonic() - t0)
    write_json(Path(root) / 'state.json', {'collected_at': now(), **out})
    print('valuation collect: ' + json.dumps(out), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', default='val')
    c.add_argument('--site-url', default=os.environ.get('SITE_URL', ''))
    c.add_argument('--minutes', type=float, default=20)
    c.add_argument('--limit', type=int, default=1500)
    b = sub.add_parser('build')
    b.add_argument('--root', default='val')
    b.add_argument('--prices', default='disclosures/docs/data/cache/prices')
    b.add_argument('--debt', default=None)
    b.add_argument('--consensus', default=None)
    b.add_argument('--rotation', default=None, help='public/ of rotation-history (forecast-ledger*.json)')
    args = ap.parse_args()
    if args.cmd == 'collect':
        collect(args.root, args.site_url, args.minutes, args.limit)
    else:
        build(args.root, args.prices, args.debt, args.consensus, rotation=args.rotation)
    return 0


if __name__ == '__main__':
    sys.exit(main())
