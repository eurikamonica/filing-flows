"""etf.py: the ETF list, the SEC data sets (N-CEN, N-PORT, prospectus risk/return), market statistics and the build."""
import datetime as dt, gzip, io, json, sys, tempfile, unittest, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import etf as E
import etf_market as M


def tsv(cols, rows):
    return '\t'.join(cols) + '\n' + ''.join('\t'.join(str(r.get(c, '')) for c in cols) + '\n' for r in rows)


def make_zip(path, tables):
    with zipfile.ZipFile(path, 'w') as z:
        for name, text in tables.items():
            z.writestr(name, text)
    return path


NASDAQ = ('Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares\n'
          'Y|IVV|iShares Core S&P 500 ETF|P| |Y|100|N||IVV|IVV|N\n'
          'Y|SPY|SPDR S&P 500 ETF Trust|P| |Y|100|N||SPY|SPY|N\n'
          'Y|TQQQ|ProShares UltraPro QQQ|Q|G|Y|100|N||TQQQ|TQQQ|N\n'
          'Y|AAPL|Apple Inc. - Common Stock|Q|Q|N|100|N|N||AAPL|N\n'
          'Y|ZZZT|Test ETF|Q|G|Y|100|Y||ZZZT|ZZZT|N\n'
          'File Creation Time: 1018202617:00|||||||||||\n')
MF = {'fields': ['cik', 'seriesId', 'classId', 'symbol'], 'data': [[1100663, 'S000004310', 'C000012040', 'IVV'], [1174610, 'S000024908', 'C000073637', 'TQQQ']]}
COS = {'fields': ['cik', 'name', 'ticker', 'exchange'], 'data': [[884394, 'SPDR S&P 500 ETF TRUST', 'SPY', 'NYSE']]}


class Universe(unittest.TestCase):
    def test_list_and_match(self):
        rows = M.parse_nasdaq_dir(NASDAQ)
        self.assertEqual([r['symbol'] for r in rows], ['IVV', 'SPY', 'TQQQ'])          # stocks and test issues left out
        u = {e['symbol']: e for e in M.build_universe(rows, MF, COS)}
        self.assertEqual((u['IVV']['series'], u['IVV']['act']), ('S000004310', '40'))
        self.assertEqual((u['SPY']['cik'], u['SPY']['act']), (884394, '33'))
        self.assertTrue(u['TQQQ']['leveraged'])
        self.assertFalse(u['IVV']['leveraged'])
        self.assertEqual(M.issuer_of('iShares Core S&P 500 ETF'), 'iShares (BlackRock)')


class Market(unittest.TestCase):
    def test_stats(self):
        import datetime as dt
        w = [[(dt.date(2021, 1, 1) + dt.timedelta(days=7 * i)).isoformat(), 100 + i, 100 + i, 1000] for i in range(260)]
        st = M.market_stats(w)
        self.assertAlmostEqual(st['price'], 359)
        self.assertGreater(st['r1y'], 0)
        self.assertEqual(st['max_dd'], 0.0)
        self.assertAlmostEqual(st['dollar_vol'], sum(x[1] * 1000 for x in w[-13:]) / 13 / 5)
        w[0][2] = 0.0                                                    # a zero adjusted close in an old bar (it stopped the build)
        self.assertEqual(M.market_stats(w)['max_dd'], 0.0)

    def test_a_shorter_history_is_fetched_again_first(self):
        import datetime as dt
        root = Path(tempfile.mkdtemp())
        fresh = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat(timespec='seconds')
        E.write_json(root / 'state.json', {'market': {'OLD': {'at': fresh}, 'NEW': {'at': fresh, 'from': M.HISTORY_FROM}}})
        asked = []

        class H:
            def json(self, url):
                asked.append(url.split('/chart/')[1].split('?')[0])
                return {'chart': {'result': [{'timestamp': [631152000 + 86400 * 7 * i for i in range(3)], 'meta': {'currency': 'USD'},
                                              'indicators': {'quote': [{'close': [1, 2, 3], 'volume': [1, 1, 1]}]}}]}}
        out = M.collect_market(H(), root, [{'symbol': 'NEW', 'assets': 9e9}, {'symbol': 'OLD', 'assets': 1e9}], lambda h: None)
        self.assertEqual(asked, ['OLD'])                                   # fetched an hour ago, but with ten years only
        st = json.loads((root / 'state.json').read_text())
        self.assertEqual((st['market']['OLD']['from'], out['this_run']), (M.HISTORY_FROM, 1))

    def test_fund_summary(self):
        body = {'quoteSummary': {'result': [{'price': {'regularMarketPrice': {'raw': 101}, 'longName': 'X'}, 'summaryDetail': {'navPrice': {'raw': 100}, 'totalAssets': {'raw': 5e9}},
                                             'fundProfile': {'categoryName': 'Large Blend', 'family': 'F', 'feesExpensesInvestment': {'annualReportExpenseRatio': {'raw': 0.0009}}}}]}}
        f = M.parse_fund_summary(body)
        self.assertAlmostEqual(f['premium'], 0.01)
        self.assertEqual((f['y_category'], f['y_expense'], f['y_assets']), ('Large Blend', 0.0009, 5e9))


class Datasets(unittest.TestCase):
    def test_ncen(self):
        with tempfile.TemporaryDirectory() as d:
            acc, fid = '0001-26-1', '0001-26-1_0001100663_S000004310'
            p = make_zip(Path(d) / 'n.zip', {
                'SUBMISSION.tsv': tsv(['ACCESSION_NUMBER', 'FILING_DATE', 'REPORT_ENDING_PERIOD', 'CIK'], [{'ACCESSION_NUMBER': acc, 'FILING_DATE': '29-JUL-2026', 'REPORT_ENDING_PERIOD': '31-MAY-2026', 'CIK': '1100663'}]),
                'REGISTRANT.tsv': tsv(['ACCESSION_NUMBER', 'REGISTRANT_NAME', 'FILE_NUM', 'LEI'], [{'ACCESSION_NUMBER': acc, 'REGISTRANT_NAME': 'iShares Trust'}]),
                'PUBLIC_ACCOUNTANT.tsv': tsv(['ACCESSION_NUMBER', 'PUB_ACCOUNTANT_NAME'], [{'ACCESSION_NUMBER': acc, 'PUB_ACCOUNTANT_NAME': 'PwC'}]),
                'FUND_REPORTED_INFO.tsv': tsv(['FUND_ID', 'ACCESSION_NUMBER', 'FUND_NAME', 'SERIES_ID', 'IS_ETF', 'IS_INDEX', 'RETURN_AFTR_FEES_AND_EXPENSES', 'STDV_AFTR_FEES_AND_EXPENSES', 'NET_INCOME_SEC_LENDING'],
                                              [{'FUND_ID': fid, 'ACCESSION_NUMBER': acc, 'FUND_NAME': 'iShares Core S&P 500 ETF', 'SERIES_ID': 'S000004310', 'IS_ETF': 'Y', 'IS_INDEX': 'Y',
                                                'RETURN_AFTR_FEES_AND_EXPENSES': '-.03', 'STDV_AFTR_FEES_AND_EXPENSES': '.01', 'NET_INCOME_SEC_LENDING': '12345'},
                                               {'FUND_ID': 'x', 'ACCESSION_NUMBER': acc, 'FUND_NAME': 'A mutual fund', 'SERIES_ID': 'S1', 'IS_ETF': 'N'}]),
                'ETF.tsv': tsv(['FUND_ID', 'NUM_SHARES_PER_CREATION_UNIT', 'IS_FUND_IN_KIND_ETF'], [{'FUND_ID': fid, 'NUM_SHARES_PER_CREATION_UNIT': '50000', 'IS_FUND_IN_KIND_ETF': 'Y'}]),
                'AUTHORIZED_PARTICIPANT.tsv': tsv(['FUND_ID', 'PARTICIPANT_NAME', 'PURCHASE_VALUE', 'REDEEM_VALUE', 'CRD_NUM'], [{'FUND_ID': fid, 'PARTICIPANT_NAME': 'JANE STREET**', 'PURCHASE_VALUE': '1000', 'REDEEM_VALUE': '-400'}]),
                'ADVISER.tsv': tsv(['FUND_ID', 'ADVISER_NAME', 'ADVISER_TYPE'], [{'FUND_ID': fid, 'ADVISER_NAME': 'BlackRock Fund Advisors', 'ADVISER_TYPE': 'Advisor'}]),
                'SHARES_OUTSTANDING.tsv': tsv(['FUND_ID', 'CLASS_ID', 'TICKER', 'CLASS_NAME'], [{'FUND_ID': fid, 'CLASS_ID': 'C000012040', 'TICKER': 'IVV'}])})
            out = E.process_ncen(p)
            self.assertEqual(list(out), ['S000004310'])                                   # mutual funds left out
            r = out['S000004310']
            self.assertEqual((r['index'], r['track_diff'], r['lending_income'], r['filed']), (True, -0.03, 12345.0, '2026-07-29'))
            self.assertEqual(r['aps'], [['JANE STREET', 1000.0, -400.0, '']])
            self.assertEqual((r['etf']['creation_unit'], r['etf']['in_kind'], r['accountant']), (50000.0, True, ['PwC']))

    def test_rr(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_zip(Path(d) / 'r.zip', {
                'sub.tsv': tsv(['adsh', 'cik', 'name', 'form', 'filed'], [{'adsh': 'a1', 'cik': '1100663', 'name': 'iShares Trust', 'form': '485BPOS', 'filed': '20260428'}]),
                'num.tsv': tsv(['adsh', 'tag', 'ddate', 'series', 'class', 'measure', 'otherdims', 'value'],
                               [{'adsh': 'a1', 'tag': 'ManagementFeesOverAssets', 'series': 'S000004310', 'value': '0.0003'},
                                {'adsh': 'a1', 'tag': 'NetExpensesOverAssets', 'series': 'S000004310', 'otherdims': 'Class=C000012040;', 'value': '0.0003'},
                                {'adsh': 'a1', 'tag': 'AnnlRtrPct', 'series': 'S000004310', 'ddate': '20251231', 'value': '0.18'},
                                {'adsh': 'a1', 'tag': 'AvgAnnlRtrPct', 'ddate': '20251231', 'measure': 'SP500Index', 'value': '0.18'}]),
                'txt.tsv': tsv(['adsh', 'tag', 'series', 'class', 'otherdims', 'value'],
                               [{'adsh': 'a1', 'tag': 'ObjectivePrimaryTextBlock', 'series': 'S000004310', 'value': '<p>Seeks to track the S&amp;P 500.</p>'},
                                {'adsh': 'a1', 'tag': 'RiskTextBlock', 'series': 'S000004310', 'otherdims': 'Risk=ConcentrationRisk;', 'value': 'Concentration . The fund may concentrate.'}]),
                'lab.tsv': tsv(['adsh', 'tag', 'std', 'terse'], [{'adsh': 'a1', 'tag': 'SP500IndexMember', 'std': 'S&P 500® Index [Member]'}, {'adsh': 'a1', 'tag': 'ConcentrationRiskMember', 'std': 'Concentration Risk [Member]'}])})
            out = E.process_rr(p, {'S000004310'}, {'C000012040': 'S000004310'})
            r = out['S000004310']
            self.assertEqual(r['fees']['management'], 0.0003)
            self.assertEqual(r['class_fees']['C000012040']['net'], 0.0003)
            self.assertEqual(r['annual'][''], {'2025': 0.18})
            self.assertEqual(r['benchmarks'], ['S&P 500® Index'])                         # the index row without a series: one-series filing
            self.assertEqual(r['objective'], 'Seeks to track the S&P 500.')
            self.assertEqual(r['risks'][0][0], 'Concentration Risk')

    def test_nport(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_zip(Path(d) / 'p.zip', {
                'SUBMISSION.tsv': tsv(['ACCESSION_NUMBER', 'FILING_DATE', 'REPORT_DATE'], [{'ACCESSION_NUMBER': 'n1', 'FILING_DATE': '24-JUL-2026', 'REPORT_DATE': '31-MAY-2026'},
                                                                                         {'ACCESSION_NUMBER': 'n0', 'FILING_DATE': '24-JUN-2026', 'REPORT_DATE': '30-APR-2026'}]),
                'REGISTRANT.tsv': tsv(['ACCESSION_NUMBER', 'CIK', 'REGISTRANT_NAME'], [{'ACCESSION_NUMBER': 'n1', 'CIK': '1100663', 'REGISTRANT_NAME': 'iShares Trust'}]),
                'FUND_REPORTED_INFO.tsv': tsv(['ACCESSION_NUMBER', 'SERIES_NAME', 'SERIES_ID', 'NET_ASSETS', 'SALES_FLOW_MON1', 'REDEMPTION_FLOW_MON1', 'SALES_FLOW_MON3', 'REDEMPTION_FLOW_MON3'],
                                              [{'ACCESSION_NUMBER': 'n1', 'SERIES_NAME': 'IVV', 'SERIES_ID': 'S000004310', 'NET_ASSETS': '1000', 'SALES_FLOW_MON1': '10', 'REDEMPTION_FLOW_MON1': '4', 'SALES_FLOW_MON3': '7', 'REDEMPTION_FLOW_MON3': '9'},
                                               {'ACCESSION_NUMBER': 'n0', 'SERIES_NAME': 'IVV', 'SERIES_ID': 'S000004310', 'NET_ASSETS': '900'}]),
                'MONTHLY_TOTAL_RETURN.tsv': tsv(['ACCESSION_NUMBER', 'CLASS_ID', 'MONTHLY_TOTAL_RETURN1', 'MONTHLY_TOTAL_RETURN2', 'MONTHLY_TOTAL_RETURN3'], [{'ACCESSION_NUMBER': 'n1', 'CLASS_ID': 'C000012040', 'MONTHLY_TOTAL_RETURN1': '1', 'MONTHLY_TOTAL_RETURN2': '2', 'MONTHLY_TOTAL_RETURN3': '3'}]),
                'FUND_REPORTED_HOLDING.tsv': tsv(['ACCESSION_NUMBER', 'HOLDING_ID', 'ISSUER_NAME', 'ISSUER_TITLE', 'ISSUER_CUSIP', 'CURRENCY_VALUE', 'PERCENTAGE', 'PAYOFF_PROFILE', 'ASSET_CAT', 'ISSUER_TYPE', 'INVESTMENT_COUNTRY'],
                                                 [{'ACCESSION_NUMBER': 'n1', 'HOLDING_ID': 'h1', 'ISSUER_NAME': 'NVIDIA CORP', 'ISSUER_CUSIP': '67066G104', 'CURRENCY_VALUE': '80', 'PERCENTAGE': '8', 'PAYOFF_PROFILE': 'Long', 'ASSET_CAT': 'EC', 'ISSUER_TYPE': 'CORP', 'INVESTMENT_COUNTRY': 'US'},
                                                  {'ACCESSION_NUMBER': 'n1', 'HOLDING_ID': 'h2', 'ISSUER_NAME': 'Cash fund', 'ISSUER_CUSIP': '066922477', 'CURRENCY_VALUE': '20', 'PERCENTAGE': '2', 'PAYOFF_PROFILE': 'Long', 'ASSET_CAT': 'STIV', 'ISSUER_TYPE': 'RF', 'INVESTMENT_COUNTRY': 'US'},
                                                  {'ACCESSION_NUMBER': 'n0', 'HOLDING_ID': 'h0', 'ISSUER_NAME': 'old report', 'CURRENCY_VALUE': '1', 'PERCENTAGE': '1', 'ASSET_CAT': 'EC'}]),
                'IDENTIFIERS.tsv': tsv(['HOLDING_ID', 'IDENTIFIER_ISIN', 'IDENTIFIER_TICKER'], [{'HOLDING_ID': 'h1', 'IDENTIFIER_TICKER': 'NVDA'}, {'HOLDING_ID': 'h1', 'IDENTIFIER_ISIN': 'US67066G1040'}]),
                'SECURITIES_LENDING.tsv': tsv(['HOLDING_ID', 'LOAN_VALUE'], [{'HOLDING_ID': 'h1', 'LOAN_VALUE': '5'}])})
            out = E.process_nport(p, {'S000004310'})
            f = out['funds']['S000004310']
            self.assertEqual([r['date'] for r in f['reports']], ['2026-04-30', '2026-05-31'])
            self.assertEqual(f['reports'][-1]['flows'][0], ['2026-03', 10.0, 0.0, 4.0])
            self.assertEqual(f['reports'][-1]['flows'][2], ['2026-05', 7.0, 0.0, 9.0])
            h = out['holdings']['S000004310']                                              # only the latest report's portfolio
            self.assertEqual((h['n'], h['top'][0][4], h['top'][0][3], h['on_loan']), (2, 'NVDA', 'US67066G1040', 5))
            self.assertEqual(h['weights'], [['NVDA', 0.08, 80]])                           # equity only
            self.assertAlmostEqual(h['mix']['EC'], 0.08)
            self.assertNotIn('active', out)

    def test_nport_active_balances(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_zip(Path(d) / 'p.zip', {
                'SUBMISSION.tsv': tsv(['ACCESSION_NUMBER', 'FILING_DATE', 'REPORT_DATE'], [{'ACCESSION_NUMBER': 'a1', 'FILING_DATE': '24-JUL-2026', 'REPORT_DATE': '30-JUN-2026'}]),
                'FUND_REPORTED_INFO.tsv': tsv(['ACCESSION_NUMBER', 'SERIES_NAME', 'SERIES_ID', 'NET_ASSETS'], [{'ACCESSION_NUMBER': 'a1', 'SERIES_NAME': 'ARK Innovation ETF', 'SERIES_ID': 'S1', 'NET_ASSETS': '1000'}]),
                'FUND_REPORTED_HOLDING.tsv': tsv(['ACCESSION_NUMBER', 'HOLDING_ID', 'ISSUER_NAME', 'ISSUER_CUSIP', 'CURRENCY_VALUE', 'PERCENTAGE', 'PAYOFF_PROFILE', 'ASSET_CAT', 'BALANCE', 'UNIT'],
                                                 [{'ACCESSION_NUMBER': 'a1', 'HOLDING_ID': 'h1', 'ISSUER_NAME': 'TESLA', 'ISSUER_CUSIP': '88160R101', 'CURRENCY_VALUE': '600', 'PERCENTAGE': '60', 'PAYOFF_PROFILE': 'Long', 'ASSET_CAT': 'EC', 'BALANCE': '2', 'UNIT': 'NS'},
                                                  {'ACCESSION_NUMBER': 'a1', 'HOLDING_ID': 'h2', 'ISSUER_NAME': 'A BOND', 'ISSUER_CUSIP': '000000AA1', 'CURRENCY_VALUE': '300', 'PERCENTAGE': '30', 'PAYOFF_PROFILE': 'Long', 'ASSET_CAT': 'DBT', 'BALANCE': '300', 'UNIT': 'PA'},
                                                  {'ACCESSION_NUMBER': 'a1', 'HOLDING_ID': 'h3', 'ISSUER_NAME': 'SHORTED', 'ISSUER_CUSIP': '111111111', 'CURRENCY_VALUE': '-50', 'PERCENTAGE': '-5', 'PAYOFF_PROFILE': 'Short', 'ASSET_CAT': 'EC', 'BALANCE': '-5', 'UNIT': 'NS'}]),
                'IDENTIFIERS.tsv': tsv(['HOLDING_ID', 'IDENTIFIER_ISIN', 'IDENTIFIER_TICKER'], [{'HOLDING_ID': 'h1', 'IDENTIFIER_TICKER': 'TSLA'}])})
            out = E.process_nport(p, {'S1'}, holdings=False, active={'S1'})
            self.assertEqual(out['holdings'], {})                                          # no portfolio page without holdings=True
            a = out['active']['S1']
            self.assertEqual((a['date'], a['filed'], a['na']), ('2026-06-30', '2026-07-24', 1000.0))
            self.assertEqual(a['pos'], [['TSLA', '88160R101', 2.0, 600]])                  # long equity in shares only

    def test_active_series(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            E.save_gz(root / 'cache' / 'ncen' / '2026q2_ncen.json.gz', {'S1': {'index': False}, 'S2': {'index': True}, 'S3': {'index': False, 'multi_inverse': True}})
            E.save_gz(root / 'cache' / 'ncen' / '2025q4_ncen.json.gz', {'S2': {'index': False}, 'S4': {'index': False}})
            self.assertEqual(E.active_series(root), {'S1', 'S4'})                           # the newest census decides S2


class Build(unittest.TestCase):
    def test_build_joins(self):
        with tempfile.TemporaryDirectory() as d:
            root, hub = Path(d) / 'etf', Path(d) / 'hub'
            E.write_json(root / 'cache' / 'universe_src.json', {'nasdaq': M.parse_nasdaq_dir(NASDAQ), 'mf': MF, 'cos': COS})
            E.save_gz(root / 'cache' / 'nport_holdings.json.gz', {'source': 'x', 'holdings': {'S000004310': {'date': '2026-05-31', 'net_assets': 1e9, 'n': 2, 'top10': 1.0, 'mix': {'EC': 1.0},
                                                                                                     'top': [['NVIDIA', '', '67066G104', None, 'NVDA', 6e8, 0.6, 'EC', 'CORP', 'US', 'Long']],
                                                                                                     'weights': [['NVDA', 0.6, 6e8], ['AAPL', 0.4, 4e8]]}}})
            E.save_gz(root / 'cache' / 'ncen' / 'q.json.gz', {'S000004310': {'series': 'S000004310', 'index': True, 'track_diff': -0.03, 'aps': [['JANE STREET', 1000.0, -400.0, '']],
                                                                             'custodians': [['State Street Bank', False, False, '', 'US']], 'accountant': ['PwC'], 'advisers': [['BFA', 'Advisor', '1', False, None]]}})
            (hub / 'market').mkdir(parents=True); (hub / 'catalogs').mkdir()
            E.write_json(hub / 'market' / 'cusip-tickers.json', {'67066G104': 'NVDA', '464287200': 'IVV'})
            E.write_json(hub / 'market' / 'officials-trades.json', {'trades': [{'ticker': 'IVV', 'type': 'purchase', 'date': '2026-10-01', 'person': 'A'}]})
            E.write_json(hub / 'catalogs' / 'holdings.json', [])
            cons = Path(d) / 'cons'
            E.write_json(cons / 'index.json', {'fields': ['ticker', 'name', 'sector', 'price', 'target_mean', 'rating_mean', 'our_price', 'eps_rev_30d', 'next_earnings'],
                                                'rows': [['NVDA', 'NVIDIA', 'technology', 100, 150, 1.5, 110, 0.02, None], ['AAPL', 'Apple', 'technology', 100, 90, 2.0, None, -0.01, None]]})
            wk = [[(dt.date(2010, 2, 12) + dt.timedelta(days=7 * i)).isoformat(), 10 + i, 10 + i, 1e6] for i in range(60)]
            E.write_json(root / 'cache' / 'market' / 'TQQQ.json', {'symbol': 'TQQQ', 'weekly': wk})      # a leveraged ETF
            E.build(root, hub, cons, None, verbose=False)
            px = json.loads((root / 'public' / 'px' / 'TQQQ.json').read_text())            # the video studio's price file
            self.assertEqual((px['d0'], len(px['t']), px['t'][-1], px['c'][-1]), ('2010-02-12', 60, 413, 69))
            idx = json.loads((root / 'public' / 'index.json').read_text())
            rows = {r[0]: dict(zip(idx['fields'], r)) for r in idx['rows']}
            ivv = rows['IVV']
            self.assertEqual((ivv['asset_class'], ivv['strategy'], ivv['aps'], ivv['officials_1y']), ('Equity', 'Index', 1, 1))
            self.assertAlmostEqual(ivv['lt_target'], 0.6 * 0.5 + 0.4 * -0.1)
            by = json.loads((root / 'public' / 'by' / 'NVDA.json').read_text())
            self.assertEqual(by['rows'][0][:3], ['IVV', 'iShares Core S&P 500 ETF', 0.6])
            parties = json.loads((root / 'public' / 'parties.json').read_text())['tables']
            self.assertEqual(parties['aps'][0][:2], ['JANE STREET', 1])
            page = json.loads((root / 'public' / 'e' / 'IVV.json').read_text())
            self.assertEqual(page['look_through']['eps_up'], 0.6)
            self.assertEqual(rows['TQQQ']['asset_class'], 'Leveraged / inverse')

    def test_implied_flows_through_to_a_company(self):
        fl = {'IVV': (False, {'2026-07': (1000.0, 400.0), '2026-08': (0.0, 200.0), '2026-09': (500.0, 0.0)}),
              'QQQ': (False, {'2026-08': (300.0, 0.0), '2026-09': (100.0, 100.0)}),
              'SQQQ': (True, {'2026-09': (9e9, 0.0)})}
        f = E.implied_flows([['IVV', 0.1, 600.0], ['QQQ', 0.5, 400.0], ['SQQQ', 0.2, 1.0]], fl)
        self.assertEqual(f['months'], ['2026-07', '2026-08', '2026-09'])
        self.assertEqual(f['in'], [100, 150, 100])                     # 0.1 × 1000; 0.5 × 300; 0.1 × 500 + 0.5 × 100
        self.assertEqual(f['out'], [40, 20, 50])
        self.assertEqual(f['cov'], [0.6, 1.0, 1.0])                    # July: only IVV (60% of the dollars held) reported
        self.assertEqual(f['etfs'], [1, 2, 2])                         # the inverse fund is left out
        self.assertIsNone(E.implied_flows([['IVV', 0.1, 1.0]], {'IVV': (False, {'2026-09': (1.0, 0.0)})}))


if __name__ == '__main__':
    unittest.main()


class PriceFile(unittest.TestCase):
    """The video studio's and the ETF page's long price file: the close as traded, the total-return close, and the
    distributions read from where the two part."""

    def test_distributions_from_the_two_closes(self):
        import etf as E
        # $100 a share, a $1 distribution in week 3: Yahoo scales every earlier adjusted close by (1 − 1/100)
        close = [100.0, 101.0, 100.0, 102.0]
        adj = [c * 0.99 for c in close[:2]] + close[2:]
        weekly = [[f'2026-01-{5 + 7 * i:02d}', c, a, 1000] for i, (c, a) in enumerate(zip(close, adj))]
        px = E.price_file('TEST', 'Test ETF', weekly)
        self.assertEqual(px['t'], [0, 7, 14, 21])
        self.assertEqual(px['c'], close)
        self.assertEqual(len(px['div']), 1)
        self.assertEqual(px['div'][0][0], '2026-01-19')
        self.assertAlmostEqual(px['div'][0][1], 1.01, places=4)       # 1% of the close before the ex-week
        self.assertIsNone(E.price_file('X', 'X', weekly[:1]))
