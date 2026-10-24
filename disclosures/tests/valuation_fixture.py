"""Synthetic inputs for app/valuation.py tests: SEC frames, daily prices, the debt and consensus modules' public files and
the site's company list, for operating companies, banks, insurers and REITs (no network)."""
import datetime as dt
import gzip
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import valuation as V  # noqa: E402

TODAY = dt.date(2026, 10, 19)


def business_days(start, end):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def write_prices(folder, ticker, days, closes):
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / f'{ticker}.json.gz', 'wt', encoding='utf-8') as f:
        json.dump({'ticker': ticker, 'rows': [[d, round(c, 4), 1_000_000] for d, c in zip(days, closes)]}, f)


def make(base, n_ind=30, n_bank=14, n_ins=13, n_reit=8, n_pre=4, n_prerev=1):
    base = Path(base)
    root, prices, debt, cons = base / 'val', base / 'prices', base / 'debt', base / 'cons'
    rng = random.Random(7)
    periods = V.calendar_quarters(18, TODAY)
    years = sorted({p[:6] for p in periods})
    days = business_days(dt.date(2022, 6, 1), dt.date(2026, 10, 16))
    mret = [rng.gauss(0.0004, 0.011) for _ in days]
    spy, c = [], 400.0
    for r in mret:
        c *= math.exp(r)
        spy.append(c)
    write_prices(prices, 'SPY', days, spy)
    frames = {}

    def put(concept, period, cik, v):
        frames.setdefault((concept, period), {})[str(cik)] = v
    companies, debt_rows, cons_rows = [], [], []
    CF = ['cik', 'ticker', 'name', 'sector', 'price', 'next_earnings', 'eps_q', 'eps_q_n', 'rev_q', 'eps_rev_30d', 'target_mean', 'rating_mean', 'pm_beat_prob',
          'pm_eps_strike', 'pm_report_date', 'pm_implied_price', 'pm_price_date', 'our_price', 'our_date', 'beat_rate', 'poly_markets', 'kalshi_events']
    spec = ([('industrial', ['3674', '7372', '2080'][i % 3], 'technology' if i % 3 < 2 else 'consumer') for i in range(n_ind)]
            + [('bank', '6021', 'financials')] * n_bank + [('insurer', '6331', 'financials')] * n_ins + [('reit', '6798', 'real_estate')] * n_reit
            + [('preprofit', '7372', 'technology')] * n_pre + [('prerev', '2836', 'health')] * n_prerev)
    for i, (kind, sic, sector) in enumerate(spec):
        cik, tk = 100000 + i, f'T{i:03d}'
        shares = rng.uniform(2e8, 2e9)
        beta = rng.uniform(0.6, 1.6)
        q_rev = rng.uniform(1e9, 2e10)
        g = rng.uniform(-0.01, 0.06)
        m = rng.uniform(0.08, 0.35)
        if kind == 'preprofit':                       # growing fast, still losing money
            q_rev, g, m = rng.uniform(1e8, 1e9), 0.06, -0.15
        elif kind == 'prerev':                        # a drug developer: a few million of revenue, a large loss
            q_rev, g, m = 2e6, 0.0, -20.0
        rev = [q_rev * (1 + g) ** k * (1 + rng.gauss(0, 0.02)) for k in range(len(periods))]
        oi = [r * (m + rng.gauss(0, 0.01)) for r in rev]
        ni = [o * 0.78 for o in oi]
        equity = sum(ni[-4:]) * rng.uniform(3, 8)
        goodwill = equity * (0.1 if kind == 'bank' else 0.2)
        if kind == 'bank':
            rotce = rng.uniform(0.06, 0.2)
            tbv = equity - goodwill
            ni = [tbv * rotce / 4 * (1 + rng.gauss(0, 0.02)) for _ in periods]
            target_mcap = tbv * (0.4 + 8 * rotce + rng.gauss(0, 0.08))
        elif kind == 'insurer':
            roe = rng.uniform(0.05, 0.2)
            ni = [equity * roe / 4 for _ in periods]
            target_mcap = equity * (0.6 + 6 * roe + rng.gauss(0, 0.1))
            prem = [r * 0.9 for r in rev]
            for p, pv in zip(periods, prem):
                put('PremiumsEarnedNet', p, cik, pv)
                put('PolicyholderBenefitsAndClaimsIncurredNet', p, cik, pv * 0.65)
                put('DeferredPolicyAcquisitionCostAmortizationExpense', p, cik, pv * 0.2)
                put('OtherUnderwritingExpense', p, cik, pv * 0.08)
        elif kind == 'reit':
            target_mcap = sum(ni[-4:]) * 2.2 * rng.uniform(10, 20)
        elif kind in ('preprofit', 'prerev'):
            equity = sum(rev[-4:]) * 1.5 if kind == 'preprofit' else 9e8
            goodwill = equity * 0.1
            ni = list(oi)
            target_mcap = sum(rev[-4:]) * rng.uniform(3, 8) if kind == 'preprofit' else 1.5e9
        else:
            target_mcap = sum(oi[-4:]) * rng.uniform(12, 30)
        eps = [v / shares for v in ni]
        for p, a, b, cc, e in zip(periods, rev, oi, ni, eps):
            put('Revenues', p, cik, a)
            put('OperatingIncomeLoss', p, cik, b)
            put('NetIncomeLoss', p, cik, cc)
            put('EarningsPerShareDiluted', p, cik, round(e, 4))
            put('WeightedAverageNumberOfDilutedSharesOutstanding', p, cik, shares)
        for p in periods[-6:]:
            put('StockholdersEquity', p + 'I', cik, equity)
            put('Goodwill', p + 'I', cik, goodwill)
            put('IntangibleAssetsNetExcludingGoodwill', p + 'I', cik, 0.0)
            put('CashAndCashEquivalentsAtCarryingValue', p + 'I', cik, 8e8 if kind == 'prerev' else sum(rev[-4:]) * (0.5 if kind == 'preprofit' else 0.1))
            put('LongTermDebt', p + 'I', cik, sum(rev[-4:]) * 0.3)
        for y in years[-3:]:
            end = f'{int(y[2:6])}-12-31'
            put('DepreciationDepletionAndAmortization', y, cik, [sum(rev[-4:]) * (0.4 if kind == 'reit' else 0.04), end])
            put('PaymentsToAcquirePropertyPlantAndEquipment', y, cik, [sum(rev[-4:]) * 0.05, end])
            put('IncomeTaxExpenseBenefit', y, cik, [sum(oi[-4:]) * 0.2, end])
            put('IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', y, cik, [sum(oi[-4:]), end])
            if kind == 'reit':
                put('GainsLossesOnSalesOfInvestmentRealEstate', y, cik, [sum(ni[-4:]) * 0.1, end])
            if kind in ('bank', 'insurer', 'reit'):           # dividends: the Gordon models of financials and REITs
                put('PaymentsOfDividends', y, cik, [sum(ni[-4:]) * (0.9 if kind == 'reit' else 0.35), end])
        price_now = target_mcap / shares
        idio = [rng.gauss(0, 0.012) for _ in days]
        path, c = [], 1.0
        for r, e in zip(mret, idio):
            c *= math.exp(beta * r + e)
            path.append(c)
        scale = price_now / path[-1]
        write_prices(prices, tk, days, [x * scale for x in path])
        companies.append({'cik': cik, 'ticker': tk, 'name': f'Test Company {i}', 'sector': sector, 'industry': 'Test', 'sic': sic, 'revenue': rev[-1]})
        if kind == 'industrial' and i % 2 == 0:
            dd = rng.uniform(1.0, 9.0)
            V.write_json(debt / 'c' / f'{cik}.json', {'cik': cik, 'ticker': tk, 'snapshot': {'shares': shares, 'equity': equity},
                                                    'analysis': {'total_debt': sum(rev[-4:]) * 0.3, 'cash_and_investments': sum(rev[-4:]) * 0.1,
                                                                 'implied': {'dd': dd, 'pd_1y': 0.5 * math.erfc(dd / math.sqrt(2)), 'calibrated_5y_bps': 40 + 600 / dd,
                                                                             'rating_band': 'BBB'},
                                                                 'altman_z': rng.uniform(0.8, 6), 'cushion_score': rng.randint(10, 95), 'effective_rate': 0.05}})
        if i % 3 == 0:
            V.write_json(cons / 'c' / f'{cik}.json', {'cik': cik, 'ticker': tk, 'analysts': {'targets': {'mean': price_now * 1.1, 'low': price_now * 0.8, 'high': price_now * 1.4, 'n': 12}},
                                                    'markets': [{'implied_price': {'q10': price_now * 0.9, 'median': round(price_now * 1.02, 2), 'q90': price_now * 1.15}}],
                                                    'ours': [{'horizon': 'next quarter', 'date': '2026-12-31', 'price': price_now * 1.03, 'lo80': price_now * 0.85, 'hi80': price_now * 1.2}]})
            cons_rows.append([cik, tk, f'Test Company {i}', sector, price_now] + [None] * 10 + [round(price_now * 1.02, 2), '2026-10-30', price_now * 1.03, '2026-12-31', None, 1, 0])
    for (concept, period), vals in frames.items():
        V.write_json(V.frame_path(root, concept, period), vals, gz=True)
    V.write_json(debt / 'index.json', {'fields': [], 'rows': debt_rows, 'market': {'treasury_1y': 0.045, 'treasury_5y': 0.047}})
    V.write_json(debt / 'rates.json', {'series': {'DGS10': {'last': ['2026-10-15', 4.6], 'monthly': []}}})
    V.write_json(cons / 'index.json', {'fields': CF, 'rows': cons_rows})
    V.write_json(root / 'site' / 'index.json', {'companies': companies})
    return {'root': root, 'prices': prices, 'debt': debt, 'cons': cons, 'companies': companies}
