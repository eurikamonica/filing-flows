"""index_members.py: index membership now (ETF holdings) and before (Wikipedia's S&P 500 changes, the Dow's history)."""
import datetime as dt, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import index_members as IM

CHANGES = """<h2>Selected changes</h2><table class="wikitable" id="changes"><tr><th rowspan="2">Date</th><th colspan="2">Added</th><th colspan="2">Removed</th><th rowspan="2">Reason</th></tr>
<tr><th>Ticker</th><th>Security</th><th>Ticker</th><th>Security</th></tr>
<tr><td rowspan="2">March 18, 2024</td><td>SMCI</td><td>Super Micro Computer</td><td>WHR</td><td>Whirlpool</td><td>cap<sup>[1]</sup></td></tr>
<tr><td>DECK</td><td>Deckers Brands</td><td>ZION</td><td>Zions Bancorporation</td><td>cap</td></tr>
<tr><td>June 17, 1997</td><td>CCI</td><td>Countrywide Credit Industries</td><td>USL</td><td>USLife</td><td>x</td></tr></table>"""
MEMBERS = """<table class="wikitable sortable" id="constituents"><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>Date added</th><th>CIK</th></tr>
<tr><td>SMCI</td><td>Supermicro</td><td>IT</td><td>2024-03-18</td><td>0001375365</td></tr><tr><td>DECK</td><td>Deckers Brands</td><td>CD</td><td>2024-03-18</td><td>0000910521</td></tr>
<tr><td>CCI</td><td>Crown Castle</td><td>RE</td><td>2012-03-14</td><td>0001051470</td></tr><tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>F</td><td>2010-02-16</td><td>0001067983</td></tr></table>"""
DOW = """<h3>June 26, 2018</h3><table class="wikitable"><tr><td>3M Company</td><td>General Electric Company ↓</td><td>Walgreens Boots Alliance, Inc. ↑</td></tr>
<tr><td>Apple Inc.</td><td>The Boeing Company</td><td>Caterpillar Inc.</td></tr><tr><td>Chevron Corporation</td><td>Cisco Systems, Inc.</td><td>The Coca-Cola Company</td></tr>
<tr><td>Intel Corporation</td><td>IBM</td></tr></table>
<h3>March 19, 2015</h3><table class="wikitable"><tr><td>3M Company</td><td>General Electric Company</td><td>Apple Inc. ↑</td></tr><tr><td>The Boeing Company</td><td>Caterpillar Inc.</td><td>Chevron Corporation</td></tr>
<tr><td>Cisco Systems, Inc.</td><td>The Coca-Cola Company</td><td>Intel Corporation</td></tr><tr><td>IBM</td><td>AT&amp;T Inc. ↓</td></tr></table>"""


class Parse(unittest.TestCase):
    def test_tables_with_spans(self):
        ch = IM.sp500_changes(IM.tables(CHANGES))
        self.assertEqual(ch[0], ('2024-03-18', 'SMCI', 'Super Micro Computer', 'WHR', 'Whirlpool'))
        self.assertEqual(ch[1][0], '2024-03-18')                                      # the date spans two rows
        self.assertEqual(ch[2][1:3], ('CCI', 'Countrywide Credit Industries'))
        m = IM.sp500_members(IM.tables(MEMBERS))
        self.assertEqual([x['symbol'] for x in m], ['SMCI', 'DECK', 'CCI', 'BRK-B'])
        self.assertEqual((m[0]['cik'], m[0]['added']), ('1375365', '2024-03-18'))

    def test_dow_compositions_leave_out_departures(self):
        comps = IM.dow_compositions(IM.tables(DOW))
        self.assertEqual([d for d, _ in comps], ['2015-03-19', '2018-06-26'])
        self.assertFalse(any('General Electric' in n for n in comps[1][1]))
        self.assertTrue(any('Walgreens' in n for n in comps[1][1]))
        self.assertEqual(IM.norm_name('The Coca-Cola Company'), 'coca cola')
        self.assertTrue(IM.same_company('Super Micro Computer', 'Supermicro'))
        self.assertFalse(IM.same_company('Countrywide Credit Industries', 'Crown Castle'))


class History(unittest.TestCase):
    def test_sp500_walks_back_and_a_reused_ticker_stays_apart(self):
        base = {'as_of': '2024-06-01', 'members': [['SMCI', '1375365'], ['DECK', '910521'], ['CCI', '1051470']],
                'changes': IM.sp500_changes(IM.tables(CHANGES))}
        d = Path(tempfile.mkdtemp()); p = d / 'base.json'; p.write_text(json.dumps(base))
        old, IM.BASE = IM.BASE, p
        try:
            iv = IM.sp500_history({'sp500_now': IM.sp500_members(IM.tables(MEMBERS))}, {'1375365': 'SMCI', '910521': 'DECK', '1051470': 'CCI'},
                                  {'SMCI': 'Super Micro Computer', 'DECK': 'Deckers Brands', 'CCI': 'Crown Castle'})
        finally:
            IM.BASE = old
        self.assertEqual(iv['SMCI'], [['2024-03-18', None]])
        self.assertEqual(iv['WHR'], [[None, '2024-03-18']])
        self.assertEqual(iv['CCI'], [['2012-03-14', None]])                            # not Countrywide's 1997 addition

    def test_dow_past_names_reach_todays_tickers(self):
        cache = {'dow': [['2013-09-23', ['Exxon Mobil Corporation  (formerly Exxon Corporation)', 'United Technologies Corporation', 'Apple Inc.']],
                         ['2020-08-31', ['Raytheon Technologies Corporation', 'Apple Inc.']]]}
        iv = IM.dow_history(cache, {'apple': 'AAPL'})
        self.assertEqual(iv['XOM'], [['2013-09-23', '2020-08-31']])
        self.assertEqual(iv['RTX'], [['2013-09-23', None]])                            # United Technologies carried on as RTX
        self.assertEqual(iv['AAPL'], [['2013-09-23', None]])

    def test_build_now_and_former(self):
        root = Path(tempfile.mkdtemp())
        (root / 'cache' / 'members').mkdir(parents=True)
        cache = {'sp500_now': IM.sp500_members(IM.tables(MEMBERS)), 'dow': IM.dow_compositions(IM.tables(DOW))}
        (root / 'cache' / 'members' / 'wiki.json').write_text(json.dumps(cache))
        by = {t: [['QQQ', 0.01, 1e9]] for t in [f'T{i}' for i in range(95)] + ['SMCI']}
        by.update({'AAPL': [['DIA', 0.03, 1e9], ['IWB', 0.05, 1e9]]})
        cos = [{'ticker': 'AAPL', 'cik': 320193, 'name': 'Apple Inc.'}, {'ticker': 'GE', 'cik': 40545, 'name': 'General Electric Co'},
               {'ticker': 'SMCI', 'cik': 1375365, 'name': 'Super Micro Computer, Inc.'}]
        out = IM.build(root, by, root / 'pub', cos, today=dt.date(2026, 10, 25), fetch=False)
        self.assertEqual(out['ndx'], 96)
        doc = json.loads((root / 'pub' / 'members.json').read_text())
        self.assertIn('ndx', doc['rows']['SMCI']['now'])
        self.assertIn('sp500', doc['rows']['SMCI']['now'])                             # from Wikipedia: no S&P tracker held
        self.assertEqual(doc['rows']['GE']['was']['dji'], [['2015-03-19', '2018-06-26']])
        self.assertEqual(doc['rows']['AAPL']['was']['dji'], [['2015-03-19', None]])
        later = IM.build(root, {t: v for t, v in by.items() if t != 'T3'}, root / 'pub', cos, today=dt.date(2026, 11, 20), fetch=False)
        doc = json.loads((root / 'pub' / 'members.json').read_text())
        self.assertEqual(doc['rows']['T3']['was']['ndx'], [['2026-10-25', '2026-10-25']])  # gone from QQQ: a former member


if __name__ == '__main__':
    unittest.main()
