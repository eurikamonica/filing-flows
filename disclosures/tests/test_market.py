import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import market


class PtrParsing(unittest.TestCase):
    def test_row_with_ticker_after_the_amount(self):
        c = {'excerpt': 'F S: New D: Sold 5,000 shares. SP NVIDIA Corporation - Common Stock P 07/26/2024 07/26/2024 $1,000,001 - (NVDA) [ST] $5,000,000 F S: New',
             'amount_min': 1000001, 'amount_max': 5000000}
        t = market.parse_ptr_candidate(c)
        self.assertEqual(t['ticker'], 'NVDA')
        self.assertEqual(t['type'], 'purchase')        # the "Sold 5,000 shares" note belongs to the previous row
        self.assertEqual(t['date'], '2024-07-26')
        self.assertEqual(t['owner'], 'SP')
        self.assertEqual(t['asset_type'], 'ST')

    def test_partial_sale_and_no_ticker(self):
        t = market.parse_ptr_candidate({'excerpt': 'Type Date Gains > $200? SP Microsoft Corporation - Common S (partial) 07/26/2024 07/26/2024 $1,000,001 - Stock (MSFT) [ST] $5,000,000 F S: New'})
        self.assertEqual((t['ticker'], t['type']), ('MSFT', 'partial sale'))
        t = market.parse_ptr_candidate({'excerpt': 'Type Date Gains > $200? SP REOF XXVI, LLC [AB] P 08/13/2024 08/13/2024 $250,001 - $500,000 F S: New'})
        self.assertEqual(t['ticker'], '')
        self.assertIsNone(market.parse_ptr_candidate({'excerpt': 'Asset Owner Value of Asset Income Type(s)'}))

    def test_account_number_in_parentheses_is_not_a_ticker(self):
        t = market.parse_ptr_candidate({'excerpt': ' S O: Morgan Stanley Active Assets (5) AbbVie Inc. Common Stock (ABBV) P 01/15/2025 01/31/2025 $1,001 - $15,000 [ST] '})
        self.assertEqual(t['ticker'], 'ABBV')


class Flows(unittest.TestCase):
    def test_split_detected_from_holder_ratios_and_price(self):
        moves = [(1000, 100, i) for i in range(8)] + [(1200, 100, 9)]
        self.assertEqual(market.split_factor(moves, 20.0, 200.0), 10)
        self.assertEqual(market.split_factor([(110, 100, 1), (90, 100, 2), (100, 120, 3)], 50, 48), 1)
        # quantities jumped 10x but the price did not fall: real buying, not a split
        self.assertEqual(market.split_factor(moves, 200.0, 200.0), 1)

    def test_conversion_pairs_vanished_line_with_its_successor(self):
        per = {'OLD': {'holders': 0, 'moves': [(0, 100, i) for i in range(20)]},
               'NEW': {'holders': 20, 'moves': [(100, 0, i) for i in range(20)]},
               'OTHER': {'holders': 50, 'moves': [(100, 0, i) for i in range(12)] + [(100, 0, 100 + i) for i in range(20)]}}
        skip, conv = market.conversions(per)
        self.assertEqual(conv['NEW']['from'], 'OLD')
        self.assertIn(('NEW', 3), skip)
        self.assertNotIn('OTHER', conv)

    def test_summarise_adjusts_splits_and_flags_first_quarter(self):
        raw = {'2026-03-31': {'A': {'issuer': 'A', 'holders': 5, 'moves': []}},
               '2026-06-30': {'A': {'issuer': 'A', 'holders': 5, 'moves': [(1000, 100, i) for i in range(5)]},
                              'IPO': {'issuer': 'IPO', 'holders': 4, 'moves': [(50, 0, i) for i in range(4)]}}}
        prices = {'2026-03-31': {'A': 100.0}, '2026-06-30': {'A': 10.0, 'IPO': 20.0}}
        s = market.summarise(raw, prices, {'2026-03-31': 5, '2026-06-30': 5})
        self.assertEqual(s['2026-06-30']['A']['add'], 0)        # 10-for-1 split, nobody bought
        self.assertEqual(s['2026-06-30']['A']['split'], 10)
        self.assertTrue(s['2026-06-30']['IPO']['first'])

    def test_periods(self):
        q, ytd, early = market.pick_periods({'2025-12-31': 1100, '2026-03-31': 1090, '2026-06-30': 1080, '2026-09-30': 40})
        self.assertEqual((q, ytd, early), ('2026-06-30', ['2026-03-31', '2026-06-30'], '2026-09-30'))


class Tickers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'cache' / 'prices').mkdir(parents=True)
        (root / 'cache' / 'prices' / 'sec-tickers.json').write_text(json.dumps({'rows': [
            {'ticker': 'NVDA', 'title': 'NVIDIA CORP'}, {'ticker': 'BRK-B', 'title': 'BERKSHIRE HATHAWAY INC'},
            {'ticker': 'AAPL', 'title': 'Apple Inc.'}]}))
        (root / 'cache' / 'prices' / 'cusips.json').write_text(json.dumps({'438516106': {'ticker': 'HONGBP', 'name': 'HONEYWELL', 'security_type': 'Common Stock'}}))
        self.u = market.Universe(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_checks(self):
        self.assertTrue(self.u.known('BRK.B'))
        self.assertEqual(self.u.name_check('NVDA', 'NVIDIA Corporation - Common Stock'), 'matches')
        self.assertEqual(self.u.name_check('AAPL', 'Alphabet Inc. - Class A'), 'check')
        self.assertEqual(self.u.suggest('Apple Inc. Common Stock'), ('AAPL', 'high'))
        self.assertEqual(self.u.cusip_ticker.get('438516106', ''), '')      # a currency-suffixed OpenFIGI line is no ticker


if __name__ == '__main__':
    unittest.main()


import insiders

FORM4 = b'''<?xml version="1.0"?>
<ownershipDocument><schemaVersion>X0508</schemaVersion><documentType>4</documentType>
<issuer><issuerCik>0001045810</issuerCik><issuerName>NVIDIA CORP</issuerName><issuerTradingSymbol>NVDA</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>Chief Financial Officer</officerTitle></reportingOwnerRelationship></reportingOwner>
<aff10b5One>0</aff10b5One>
<nonDerivativeTable>
<nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>2026-10-13</value></transactionDate>
<transactionCoding><transactionFormType>4</transactionFormType><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>10000</value></transactionShares><transactionPricePerShare><value>180.50</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
<postTransactionAmounts><sharesOwnedFollowingTransaction><value>50000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
<ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></nonDerivativeTransaction>
<nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>2026-10-13</value></transactionDate>
<transactionCoding><transactionCode>F</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>500</value></transactionShares><transactionPricePerShare><value>180</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction>
</nonDerivativeTable></ownershipDocument>'''


class Insiders(unittest.TestCase):
    def test_purchase_kept_withholding_skipped(self):
        txt = b'<SEC-DOCUMENT>...<XML>\n' + FORM4 + b'\n</XML>...'
        rows = insiders.parse_form4(insiders.xml_from_submission(txt), '0001-26-000001', 'https://www.sec.gov/x/')
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r['ticker'], r['role'], r['code'], r['value'], r['issuer_cik']), ('NVDA', 'CFO', 'P', 1805000, '1045810'))

    def test_cluster(self):
        import datetime as dt
        d = dt.date.today().isoformat()
        tr = [{'ticker': 'ABC', 'issuer': 'ABC', 'issuer_cik': '1', 'insider': n, 'role': 'Director', 'code': 'P', 'date': d, 'value': 60000}
              for n in ('A', 'B', 'C')]
        s = insiders.summary(tr)[0]
        self.assertTrue(s['cluster'])
        self.assertEqual(s['buy_value'], 180000)


import frames, rotation


class Rotation(unittest.TestCase):
    def test_series_from_frames_and_prices(self):
        periods = ['CY2024Q1', 'CY2024Q2', 'CY2024Q3', 'CY2024Q4', 'CY2025Q1', 'CY2025Q2']
        fig = {p: {'rev': r, 'oi': r * m / 100, 'gp': r * 0.5, 'ni': None}
               for p, r, m in zip(periods, [100, 100, 100, 100, 110, 120], [10, 11, 12, 13, 15, 12])}
        rows = [['2024-12-31', 100.0, 1000], ['2025-03-31', 110.0, 1000], ['2025-06-30', 99.0, 3000]]
        spy = [['2024-12-31', 500.0], ['2025-03-31', 500.0], ['2025-06-30', 550.0]]
        pts = rotation.series(fig, rows, spy, periods, f13={'CY2025Q2': 7}, gov={'CY2025Q1': 0})
        self.assertEqual([p['cal'] for p in pts], ['CY2025Q1', 'CY2025Q2'])
        self.assertEqual(pts[0]['dom'], 5.0)                  # 15% vs 10% a year earlier
        self.assertAlmostEqual(pts[0]['rel'], 10.0)           # +10% vs a flat market (percent)
        self.assertAlmostEqual(pts[1]['rel'], -20.0, places=3)
        self.assertAlmostEqual(pts[0]['revg'], 10.0)          # 110 vs 100 a year earlier
        self.assertAlmostEqual(pts[1]['reva'], 10.0)          # 20% growth after 10%
        self.assertAlmostEqual(pts[1]['rel6'], -11.0, places=3)   # 99/100 − 1 vs 550/500 − 1
        self.assertEqual(pts[0]['dgm'], 0.0)
        self.assertIsNone(pts[0]['nm'])
        self.assertEqual((pts[1]['f13'], pts[0]['gov'], pts[0]['f13']), (7, 0, None))

    def test_calendar_quarters(self):
        import datetime as dt
        self.assertEqual(frames.calendar_quarters(3, dt.date(2026, 1, 5)), ['CY2025Q2', 'CY2025Q3', 'CY2025Q4'])

    def test_fourth_quarter_from_the_annual_frame(self):
        import gzip, json, tempfile
        root = tempfile.mkdtemp()

        def put(concept, period, vals):
            p = frames.path_for(root, concept, period)
            p.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(p, 'wt') as f:
                json.dump(vals, f)
        for q, v in (('CY2024Q4', 90), ('CY2025Q1', 100), ('CY2025Q2', 110)):
            put('Revenues', q, {'1': v})
        put('Revenues', 'CY2025', {'1': [420, '2025-09-27']})      # fiscal year ending in September: Q3 is the missing one
        got = frames.quarterly(root, 'Revenues', ['CY2025Q1', 'CY2025Q2', 'CY2025Q3'])
        self.assertEqual(got['CY2025Q3'], {'1': 120})
        self.assertEqual(frames._quarter_of('2026-01-31'), 'CY2025Q4')


class Options13F(unittest.TestCase):
    def test_positions_and_changes(self):
        class U:
            cusip_ticker = {'111111111': 'ABC'}
            cusip_type = {}
            def name(self, t):
                return 'Abc Corp'
        mgrs = [{'cik': '1', 'name': 'Fund One'}, {'cik': '2', 'name': 'Fund Two'}]
        opts = {0: {'2026-03-31': {('111111111', 'PUT'): [100, 1000, 'ABC CORP']},
                    '2026-06-30': {('111111111', 'PUT'): [300, 3600, 'ABC CORP'], ('111111111', 'CALL'): [50, 600, 'ABC CORP']}},
                1: {'2026-03-31': {('111111111', 'CALL'): [200, 2000, 'ABC CORP']}, '2026-06-30': {}}}
        cov = {'2026-03-31': 2, '2026-06-30': 2}
        o = market.options13f(opts, mgrs, U(), cov, '2026-06-30', {})
        r = o['rows'][0]
        self.assertEqual((r['ticker'], r['put_usd'], r['call_usd'], r['put_mgrs'], r['call_mgrs']), ('ABC', 3600, 600, 1, 1))
        self.assertEqual(r['d_put_usd'], 2400)               # 200 more shares at 12
        self.assertEqual((r['new_call'], r['closed_call']), (1, 1))
        kinds = sorted(m['kind'] for m in o['moves'])
        self.assertEqual(kinds, ['added', 'closed', 'new'])
        self.assertEqual(o['books'][0]['manager'], 'Fund One')


import options


def _chain(spot=100.0):
    """A small synthetic chain: two expiries (a monthly and one ~30 days out), strikes 80–120."""
    rows = []
    for exp, days in (('261120', 36), ('261218', 64)):           # 2026-11-20 and 2026-12-18 are third Fridays
        for k in range(80, 125, 5):
            for t in 'CP':
                m = (k - spot) / spot
                rows.append({'option': f'XYZ{exp}{t}{k * 1000:08d}', 'iv': round(0.30 + (0.4 * m * m) - (0.05 * m), 4),
                             'open_interest': 1000 if (t == 'P' and k == 90) or (t == 'C' and k == 110) else 100, 'volume': 10,
                             'delta': (0.5 - m * 2) if t == 'C' else (-0.5 - m * 2), 'gamma': max(0.0, 0.05 - abs(m) * 0.2),
                             'bid': 1.0, 'ask': 1.2})
    return {'timestamp': '2026-10-15 16:15:00', 'data': {'current_price': spot, 'iv30': 31.2, 'iv30_change': 0.4, 'options': rows}}


class Options(unittest.TestCase):
    def test_summary(self):
        import datetime as dt
        spot, iv30, chg, chain = options.parse_chain(_chain())
        s, d = options.summarise('XYZ', spot, iv30, chg, chain, today=dt.date(2026, 10, 15))
        self.assertEqual((s['call_wall'], s['put_wall']), (110, 90))
        self.assertEqual(s['max_pain_exp'], '2026-11-20')
        self.assertTrue(80 <= s['max_pain'] <= 120)
        self.assertEqual(len(d['term']), 2)
        self.assertTrue(d['smiles'] and all(len(x['pts']) >= 5 for x in d['smiles']))
        self.assertAlmostEqual(s['pc_oi'], 1.0)                      # symmetric open interest
        self.assertEqual(options.cboe_symbol('SPX'), '_SPX')
