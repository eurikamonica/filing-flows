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
