"""holders_history.py: SEC's 13F data sets read into who held each stock, quarter by quarter."""
import gzip, json, sys, tempfile, unittest, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import holders_history as HH

SUB_H = ['ACCESSION_NUMBER', 'FILING_DATE', 'SUBMISSIONTYPE', 'CIK', 'PERIODOFREPORT']
COV_H = ['ACCESSION_NUMBER', 'REPORTCALENDARORQUARTER', 'ISAMENDMENT', 'AMENDMENTNO', 'AMENDMENTTYPE', 'FILINGMANAGER_NAME', 'REPORTTYPE']
INF_H = ['ACCESSION_NUMBER', 'INFOTABLE_SK', 'NAMEOFISSUER', 'TITLEOFCLASS', 'CUSIP', 'FIGI', 'VALUE', 'SSHPRNAMT', 'SSHPRNAMTTYPE', 'PUTCALL',
         'INVESTMENTDISCRETION', 'OTHERMANAGER', 'VOTING_AUTH_SOLE', 'VOTING_AUTH_SHARED', 'VOTING_AUTH_NONE']
AAPL, MSFT, MDT, GOOG_A_OLD, GOOG_C = '037833100', '594918104', 'G5960L103', '38259P508', '02079K107'


def tsv(head, rows):
    return '\n'.join(['\t'.join(head)] + ['\t'.join(str(x) for x in r) for r in rows]) + '\n'


def dataset(path, filings):
    """filings: [(accession, filed DD-MON-YYYY, form, cik, period DD-MON-YYYY, amendment type, manager, report type,
    [(issuer, class, cusip, value, shares, SH/PRN, put/call)])]"""
    sub, cov, inf = [], [], []
    for acc, filed, form, cik, period, atype, name, rtype, lines in filings:
        sub.append([acc, filed, form, cik, period])
        cov.append([acc, period, 'Y' if form.endswith('/A') else 'N', '1' if form.endswith('/A') else '', atype, name, rtype])
        for k, (iss, cls, cusip, val, sh, typ, pc) in enumerate(lines):
            inf.append([acc, k + 1, iss, cls, cusip, '', val, sh, typ, pc, 'SOLE', '', sh, 0, 0])
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('SUBMISSION.tsv', tsv(SUB_H, sub))
        z.writestr('COVERPAGE.tsv', tsv(COV_H, cov))
        z.writestr('INFOTABLE.tsv', tsv(INF_H, inf))


def H(acc, filed, cik, period, name, lines, form='13F-HR', atype='', rtype='13F HOLDINGS REPORT'):
    return (acc, filed, form, cik, period, atype, name, rtype, lines)


A = lambda val, sh: ('APPLE INC', 'COM', AAPL, val, sh, 'SH', '')
M = lambda val, sh: ('MICROSOFT CORP', 'COM', MSFT, val, sh, 'SH', '')
SETS = {
    # Q1 2024 reports (filed in May); BlackRock under its old CIK; one manager reporting thousands in 2024
    '01mar2024-31may2024_form13f.zip': [
        H('a1', '14-MAY-2024', 1364742, '31-MAR-2024', 'BlackRock Inc.', [A(1_710_000_000, 10_000_000), M(4_200_000_000, 10_000_000)]),
        H('a2', '14-MAY-2024', 102909, '31-MAR-2024', 'VANGUARD GROUP INC', [A(2_052_000_000, 12_000_000)]),
        H('a3', '15-MAY-2024', 999, '31-MAR-2024', 'SMALL FUND LLC', [A(17_100, 100), M(42_000, 100), A(1, 5, ), ('MEDTRONIC PLC', 'SHS', MDT, 900, 10, 'SH', '')]),
        H('a4', '15-MAY-2024', 777, '31-MAR-2024', 'NOTICE FILER', [], form='13F-NT', rtype='13F NOTICE'),
        H('a5', '15-MAY-2024', 555, '31-MAR-2024', 'OPTIONS FUND', [A(171_000_000, 1_000_000), ('APPLE INC', 'CALL', AAPL, 50_000_000, 300_000, 'SH', 'Call'),
                                                                 ('APPLE INC', 'NOTE', AAPL, 1_000_000, 1_000_000, 'PRN', '')]),
        H('a6', '15-MAY-2024', 444, '31-MAR-2024', 'MDT HOLDER A', [('MEDTRONIC PLC', 'SHS', MDT, 8_700_000, 100_000, 'SH', '')]),
        H('a7', '15-MAY-2024', 333, '31-MAR-2024', 'MDT HOLDER B', [('MEDTRONIC PLC', 'SHS', MDT, 8_700_000, 100_000, 'SH', '')]),
        H('a8', '15-MAY-2024', 222, '31-MAR-2024', 'MDT HOLDER C', [('MEDTRONIC PLC', 'SHS', MDT, 870_000, 10_000, 'SH', '')]),
    ],
    # Q2 2024 reports; Vanguard's second filer; a restatement of the small fund's Q1 and its new-holdings amendment
    '01jun2024-31aug2024_form13f.zip': [
        H('b1', '13-AUG-2024', 1364742, '30-JUN-2024', 'BlackRock Inc.', [A(2_100_000_000, 10_000_000)]),
        H('b2', '13-AUG-2024', 102909, '30-JUN-2024', 'VANGUARD GROUP INC', [A(2_100_000_000, 10_000_000)]),
        H('b3', '14-AUG-2024', 2100119, '30-JUN-2024', 'VANGUARD CAPITAL MANAGEMENT LLC', [A(1_050_000_000, 5_000_000)]),
        H('b4', '01-JUL-2024', 999, '31-MAR-2024', 'SMALL FUND LLC', [A(25_650, 150)], form='13F-HR/A', atype='RESTATEMENT'),
        H('b5', '02-JUL-2024', 999, '31-MAR-2024', 'SMALL FUND LLC', [M(84_000, 200)], form='13F-HR/A', atype='NEW HOLDINGS'),
        H('b6', '14-AUG-2024', 555, '30-JUN-2024', 'OPTIONS FUND', [A(210, 1_000_000)]),       # thousands, in 2024: ×1000
    ],
    # Q3 2024; BlackRock under its new CIK from here
    '01sep2024-30nov2024_form13f.zip': [
        H('c1', '13-NOV-2024', 2012383, '30-SEP-2024', 'BlackRock, Inc.', [A(2_330_000_000, 10_000_000)]),
        H('c2', '13-NOV-2024', 102909, '30-SEP-2024', 'VANGUARD GROUP INC', [A(3_495_000_000, 15_000_000)]),
    ],
    '01dec2024-28feb2025_form13f.zip': [
        H('d1', '12-FEB-2025', 2012383, '31-DEC-2024', 'BlackRock, Inc.', [A(2_500_000_000, 10_000_000)]),
    ],
}
PAGE_HTML = ''.join(f'<a href="/files/structureddata/data/form-13f-data-sets/{n}">x</a>' for n in SETS) + '<a href="/other.zip">no</a>'


class Names(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(HH.window('2013q2_form13f.zip'), ('2013-04-01', '2013-06-30'))
        self.assertEqual(HH.window('2023q4_form13f.zip'), ('2023-10-01', '2023-12-31'))
        self.assertEqual(HH.window('https://x/01dec2025-28feb2026_form13f.zip'), ('2025-12-01', '2026-02-28'))
        self.assertIsNone(HH.window('form13f_readme.zip'))
        ls = HH.listing(PAGE_HTML)
        self.assertEqual([x[1] for x in ls], ['2024-03-01', '2024-06-01', '2024-09-01', '2024-12-01'])
        self.assertTrue(ls[0][0].startswith('https://www.sec.gov/files/structureddata/'))

    def test_dates_keys_and_pretty_names(self):
        self.assertEqual(HH.day('31-DEC-2023'), '2023-12-31')
        self.assertEqual(HH.day('12/31/2023'), '2023-12-31')
        self.assertEqual(HH.name_key('MEDTRONIC PLC'), HH.name_key('Medtronic plc'))
        self.assertEqual(HH.name_key('ACCENTURE PLC IRELAND'), 'ACCENTURE')
        self.assertEqual(HH.pretty('STATE STREET CORP', 93751), ['State Street', 'State Street'])
        self.assertEqual(HH.pretty('BANK OF NEW YORK MELLON CORP /DE/')[0], 'Bank of New York Mellon')
        self.assertEqual(HH.pretty('GEODE CAPITAL MANAGEMENT, LLC')[0], 'Geode Capital Management')
        self.assertEqual(HH.pretty('RENAISSANCE TECHNOLOGIES LLC')[1], 'Renaissance')
        self.assertEqual(HH.holder_key(2100119), 'f:vanguard')
        self.assertEqual(HH.holder_key(1364742), HH.holder_key(2012383))
        self.assertEqual(HH.holder_key(1067983), 'c1067983')

    def test_quarters_close_after_two_windows(self):
        self.assertFalse(HH.closes('2024-03-31', '2024-06-01'))
        self.assertTrue(HH.closes('2024-03-31', '2024-09-01'))
        self.assertEqual(HH.quarter_ends('2024-02-01', '2024-09-30'), ['2024-03-31', '2024-06-30', '2024-09-30'])


class Collect(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / 'src'
        self.src.mkdir()
        for n, fs in SETS.items():
            dataset(self.src / n, fs)
        self.calls = []

    def fetch(self, url, dest=None):
        name = url.rsplit('/', 1)[-1]
        if not (self.src / name).exists():
            raise HH.Missing(url)
        self.calls.append(name)
        Path(dest).write_bytes((self.src / name).read_bytes())
        return dest

    def run_all(self, minutes=60):
        return HH.collect(self.tmp / 'hh', minutes, page_html=PAGE_HTML, fetch=self.fetch, early=False)

    def test_quarters_families_amendments_and_units(self):
        r = self.run_all()
        self.assertEqual(r['left'], 0)
        root = self.tmp / 'hh'
        state = json.loads((root / 'cache' / 'sets.json').read_text())
        self.assertEqual([p for p in state['closed'] if p >= '2024'], ['2024-03-31', '2024-06-30'])   # Q3, Q4 2024 wait for later sets
        q1 = HH.read_gz(root / 'cache' / 'periods' / '2024-03-31.json.gz')
        holders, shares, usd, top = q1['rows'][AAPL]
        self.assertEqual(holders, 4)                     # BlackRock, Vanguard, the small fund, the options fund (not the notice)
        self.assertEqual(shares, 10_000_000 + 12_000_000 + 150 + 1_000_000)    # the restatement replaced 100 with 150; calls out
        top = {k: (s, v) for k, s, v in top}
        self.assertEqual(top['f:blackrock'], (10_000_000, 1_710_000_000))
        self.assertEqual(top['c999'], (150, 25_650))
        self.assertEqual(q1['rows'][MSFT][1], 10_000_000 + 200)               # the new holdings added to the restatement
        self.assertEqual(q1['names']['c999'], 'SMALL FUND LLC')
        q2 = HH.read_gz(root / 'cache' / 'periods' / '2024-06-30.json.gz')
        top2 = {k: (s, v) for k, s, v in q2['rows'][AAPL][3]}
        self.assertEqual(top2['f:vanguard'], (15_000_000, 3_150_000_000))     # two Vanguard filers, one holder
        self.assertEqual(top2['c555'], (1_000_000, 210_000))                   # reported in thousands: ×1000
        self.assertEqual(q2['rows'][AAPL][0], 4)                               # filers, not families
        self.assertTrue(HH.read_gz(root / 'cache' / 'periods' / '2024-12-31.json.gz')['open'])

    def test_a_cut_run_starts_again_where_quarters_are_open(self):
        r = HH.collect(self.tmp / 'hh', 0, page_html=PAGE_HTML, fetch=self.fetch, early=False)     # no time: one set, then stop
        self.assertEqual(r['read'], ['01mar2024-31may2024_form13f.zip'])
        self.assertEqual(r['left'], 3)
        self.calls.clear()
        r = self.run_all()
        self.assertEqual(self.calls[0], '01mar2024-31may2024_form13f.zip')     # Q1 2024 was open: its set read again
        self.assertEqual(r['left'], 0)
        q1 = HH.read_gz(self.tmp / 'hh' / 'cache' / 'periods' / '2024-03-31.json.gz')
        self.assertEqual(q1['rows'][AAPL][0], 4)                               # once, not twice
        self.calls.clear()
        self.run_all()                                   # nothing new on SEC's page: nothing read
        self.assertEqual(self.calls, [])
        new = '01mar2025-31may2025_form13f.zip'          # a new set: the open quarters' sets read again, then it
        dataset(self.src / new, [H('e1', '14-MAY-2025', 2012383, '31-MAR-2025', 'BlackRock, Inc.', [A(2_200_000_000, 10_000_000)])])
        page = PAGE_HTML + f'<a href="/files/structureddata/data/form-13f-data-sets/{new}">x</a>'
        HH.collect(self.tmp / 'hh', 60, page_html=page, fetch=self.fetch, early=False)
        self.assertEqual(self.calls, ['01sep2024-30nov2024_form13f.zip', '01dec2024-28feb2025_form13f.zip', new])
        state = json.loads((self.tmp / 'hh' / 'cache' / 'sets.json').read_text())
        self.assertIn('2024-09-30', state['closed'])
        self.assertEqual(HH.read_gz(self.tmp / 'hh' / 'cache' / 'periods' / '2024-09-30.json.gz')['rows'][AAPL][0], 2)

    def test_sets_the_page_leaves_out_by_their_address(self):
        ls = HH.with_early(HH.listing(PAGE_HTML))
        self.assertEqual(ls[0][0].rsplit('/', 1)[-1], '2013q2_form13f.zip')
        self.assertEqual(ls[len(ls) - 5][0].rsplit('/', 1)[-1], '2023q4_form13f.zip')
        self.assertEqual(ls[-4][1], '2024-03-01')
        r = HH.collect(self.tmp / 'hh', 60, page_html=PAGE_HTML, fetch=self.fetch)    # the guessed ones: not there, passed over
        self.assertEqual(r['left'], 0)
        self.assertEqual(self.calls, list(SETS))

    def test_build_tickers_families_and_names(self):
        self.run_all()
        hub = self.tmp / 'hub'
        (hub / 'market').mkdir(parents=True)
        (hub / 'cache' / 'prices').mkdir(parents=True)
        (hub / 'market' / 'cusip-tickers.json').write_text(json.dumps({AAPL: 'AAPL', MSFT: 'MSFT', GOOG_C: 'GOOG'}))
        (hub / 'cache' / 'prices' / 'sec-tickers.json').write_text(json.dumps({'rows': [
            {'ticker': 'AAPL', 'title': 'Apple Inc.', 'cik': 320193}, {'ticker': 'MDT', 'title': 'Medtronic plc', 'cik': 1613103},
            {'ticker': 'MSFT', 'title': 'MICROSOFT CORP', 'cik': 789019}]}))
        st = HH.build(self.tmp / 'hh', hub, min_usd=1_000_000)
        self.assertEqual(st['quarters'], 4)
        self.assertEqual(st['cusips_named'].get('by name'), 1)                 # Medtronic: its issuer name
        doc = json.loads((self.tmp / 'hh' / 'public' / 'c' / 'AAPL.json').read_text())
        self.assertEqual(doc['periods'], ['2024-03-31', '2024-06-30', '2024-09-30', '2024-12-31'])
        self.assertEqual(doc['open'], ['2024-09-30', '2024-12-31'])
        who = {w[0]: w for w in doc['who']}
        self.assertEqual(who['f:blackrock'][1], 'BlackRock')
        self.assertTrue({1364742, 2012383, 1006249} <= set(who['f:blackrock'][3]))      # its filers, old and new
        bl = [next((x for x in row if doc['who'][x[0]][0] == 'f:blackrock'), None) for row in doc['top']]
        self.assertTrue(all(bl))                         # BlackRock in every quarter, through the change of CIK
        self.assertEqual(doc['total'][0][0], 4)
        self.assertEqual(doc['top'][1][0][1], 15_000_000)                       # Vanguard first in Q2, both filers together
        self.assertEqual(json.loads((self.tmp / 'hh' / 'public' / 'c' / 'MDT.json').read_text())['total'][0][0], 3)   # the restatement dropped the small fund's
        ix = json.loads((self.tmp / 'hh' / 'public' / 'index.json').read_text())
        self.assertEqual(ix['rows'][0][0], 'AAPL')

    def test_mistyped_filings_stray_quarters_and_late_family_members(self):
        tmp = Path(tempfile.mkdtemp())
        root, hub = tmp / 'hh', tmp / 'hub'
        (root / 'cache' / 'periods').mkdir(parents=True)
        many = [[f'c{100 + k}', 1000, 100_000] for k in range(70)]           # 70 holders at $100 a share
        q = lambda p, rows, h=None: HH.write_gz(root / 'cache' / 'periods' / f'{p}.json.gz', {'period': p, 'filers': 99, 'names': {}, 'issuers': {}, 'rows': {AAPL: [h or len(rows), sum(r[1] for r in rows), sum(r[2] for r in rows), rows]}})
        q('2015-03-31', [['c1', 1000, 100_000]], h=1)                          # one filer early: a stray report
        q('2015-06-30', [['c913414', 5000, 500_000], ['c1006249', 4000, 400_000], ['c7', 9_000_000, 100_000]] + many)
        q('2015-09-30', [['c913414', 5000, 500_000]] + many)
        (hub / 'market').mkdir(parents=True)
        (hub / 'market' / 'cusip-tickers.json').write_text(json.dumps({AAPL: 'AAPL'}))
        HH.build(root, hub, min_usd=1)
        doc = json.loads((root / 'public' / 'c' / 'AAPL.json').read_text())
        self.assertEqual(doc['periods'], ['2015-06-30', '2015-09-30'])          # the stray quarter left out
        who = [w[0] for w in doc['who']]
        first = {who[w]: (sh, usd) for w, sh, usd in doc['top'][0]}
        self.assertEqual(first['f:blackrock'], (9000, 900_000))               # two BlackRock filers of 2015 as one
        self.assertEqual(first['c7'], (1000, 100_000))                        # 9 million shares worth $100,000: the smaller kept
        self.assertEqual(who[doc['top'][0][0][0]], 'f:blackrock')
        self.assertLess(doc['total'][0][1], 9_000_000)                        # the total bounded the same way

    def test_former_cusips_and_share_classes(self):
        tmp = Path(tempfile.mkdtemp())
        root, hub = tmp / 'hh', tmp / 'hub'
        (root / 'cache' / 'periods').mkdir(parents=True)
        mk = lambda cusip, sh, usd, who: {cusip: [len(who), sh, usd, [[w, sh // len(who), usd // len(who)] for w in who]]}
        HH.write_gz(root / 'cache' / 'periods' / '2015-06-30.json.gz', {'period': '2015-06-30', 'filers': 10, 'names': {'c1': 'ONE'}, 'issuers': {GOOG_A_OLD: ['GOOGLE INC', 'CL A']},
                                                                        'rows': mk(GOOG_A_OLD, 900, 500_000_000, ['c1', 'c2', 'c3'])})
        HH.write_gz(root / 'cache' / 'periods' / '2015-12-31.json.gz', {'period': '2015-12-31', 'filers': 10, 'names': {'c1': 'ONE'}, 'issuers': {},
                                                                        'rows': {**mk('02079K305', 900, 600_000_000, ['c1', 'c2', 'c3']), **mk(GOOG_C, 300, 200_000_000, ['c1', 'c2', 'c3'])}})
        (hub / 'market').mkdir(parents=True)
        (hub / 'market' / 'cusip-tickers.json').write_text(json.dumps({'02079K305': 'GOOGL', GOOG_C: 'GOOG'}))
        HH.build(root, hub, min_usd=1)
        doc = json.loads((root / 'public' / 'c' / 'GOOGL.json').read_text())
        self.assertEqual(doc['periods'], ['2015-06-30', '2015-12-31'])          # Google's CUSIP carries Alphabet back
        self.assertEqual(doc['total'][1][1:], [1200, 800_000_000])              # both classes together
        self.assertEqual(doc['classes'], ['GOOG', 'GOOGL'])
        self.assertFalse((root / 'public' / 'c' / 'GOOG.json').exists())



class Managers(unittest.TestCase):
    """Each filer's own quarter, from the same pass: the long equity book, its options, its largest positions and the
    book by sector, published for the managers of more than GIANT positions."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / 'src'
        self.src.mkdir()
        for n, fs in SETS.items():
            dataset(self.src / n, fs)
        self.hub = self.tmp / 'hub'
        (self.hub / 'market').mkdir(parents=True)
        (self.hub / 'cache' / 'prices').mkdir(parents=True)
        (self.hub / 'market' / 'cusip-tickers.json').write_text(json.dumps({AAPL: 'AAPL', MSFT: 'MSFT'}))
        (self.hub / 'cache' / 'prices' / 'sec-tickers.json').write_text(json.dumps({'rows': [
            {'ticker': 'AAPL', 'title': 'Apple Inc.'}, {'ticker': 'MSFT', 'title': 'MICROSOFT CORP'}, {'ticker': 'MDT', 'title': 'Medtronic plc'}]}))
        self.sec = self.tmp / 'meta.json'                 # the rank panel's meta: ticker → sector
        self.sec.write_text(json.dumps({'cos': [['AAPL', 'Apple Inc.', 'technology'], ['MSFT', 'Microsoft', 'technology']]}))
        self.etf = self.tmp / 'etf-sectors.json'           # the ETF build's: a ticker the meta lacks
        self.etf.write_text(json.dumps({'sectors': {'MDT': 'health', 'AAPL': 'industrials'}}))
        self.keep = (HH.MIN_BOOK, HH.MIN_BOOK_USD, HH.GIANT)
        HH.MIN_BOOK, HH.MIN_BOOK_USD, HH.GIANT = 1, 0, 0

    def tearDown(self):
        HH.MIN_BOOK, HH.MIN_BOOK_USD, HH.GIANT = self.keep

    def fetch(self, url, dest=None):
        name = url.rsplit('/', 1)[-1]
        if not (self.src / name).exists():
            raise HH.Missing(url)
        Path(dest).write_bytes((self.src / name).read_bytes())
        return dest

    def collect(self):
        return HH.collect(self.tmp / 'hh', 60, page_html=PAGE_HTML, fetch=self.fetch, early=False, hub=self.hub, sectors=[self.sec, self.etf])

    def test_books_options_sectors_and_the_largest_positions(self):
        self.collect()
        q1 = HH.read_gz(self.tmp / 'hh' / 'cache' / 'managers' / '2024-03-31.json.gz')
        self.assertEqual(q1['fields'], HH.MANAGER_FIELDS)
        usd, lines, put, call, top, sectors = q1['rows']['555']
        self.assertEqual((usd, lines, put, call), (171_000_000, 1, 0, 50_000_000))     # the call and the note left out of the book
        self.assertEqual(top, [[AAPL, 1_000_000, 171_000_000]])
        self.assertEqual(sectors, {'technology': 171_000_000})                         # the meta before the ETF build's
        small = q1['rows']['999']                                                      # the restatement, then its new holdings
        self.assertEqual(small[1], 2)
        self.assertEqual(small[5], {'technology': 25_650 + 84_000})
        self.assertEqual(q1['names']['555'], 'OPTIONS FUND')
        self.assertEqual(q1['rows']['444'][5], {}, 'Medtronic: no ticker before a build has named its CUSIP')
        self.assertIn(MDT, q1['issuers'])
        HH.build(self.tmp / 'hh', self.hub, min_usd=1)                                 # names it by its SEC listing (cusips.json)
        st = json.loads((self.tmp / 'hh' / 'cache' / 'sets.json').read_text())
        st['mversion'] = 0
        (self.tmp / 'hh' / 'cache' / 'sets.json').write_text(json.dumps(st))
        self.collect()                                                                  # read again: now a sector
        q1 = HH.read_gz(self.tmp / 'hh' / 'cache' / 'managers' / '2024-03-31.json.gz')
        self.assertEqual(q1['rows']['444'][5], {'health': 8_700_000})                  # through the ETF build's map
        q2 = HH.read_gz(self.tmp / 'hh' / 'cache' / 'managers' / '2024-06-30.json.gz')
        self.assertEqual(q2['rows']['555'][0], 210_000)                                # thousands: ×1000, as for the holders
        self.assertTrue(HH.read_gz(self.tmp / 'hh' / 'cache' / 'managers' / '2024-12-31.json.gz')['open'])

    def test_the_published_managers(self):
        self.collect()
        st = HH.build(self.tmp / 'hh', self.hub, min_usd=1)
        self.assertGreaterEqual(st['managers']['managers'], 5)
        doc = json.loads((self.tmp / 'hh' / 'public' / 'm' / '102909.json').read_text())
        self.assertEqual(doc['periods'], ['2024-03-31', '2024-06-30', '2024-09-30'])
        self.assertEqual(doc['usd'], [2_052_000_000, 2_100_000_000, 3_495_000_000])
        self.assertEqual(doc['top'][0], [['AAPL', 100_000]])                         # the whole book, in hundred-thousandths
        self.assertEqual(doc['unit'], 1e-5)
        self.assertEqual(doc['names']['AAPL'], 'Apple Inc.')
        self.assertEqual(doc['open'], ['2024-09-30'])
        self.assertEqual(doc['name'], 'Vanguard Group')
        small = json.loads((self.tmp / 'hh' / 'public' / 'm' / '999.json').read_text())
        keys = {k for k, _ in small['top'][0]}
        self.assertEqual(sum(w for _, w in small['top'][0]), 100_000)
        self.assertEqual(keys, {'AAPL', 'MSFT'})
        mdt = json.loads((self.tmp / 'hh' / 'public' / 'm' / '444.json').read_text())
        self.assertEqual(mdt['top'][0][0][0], 'MDT')                                   # named by the issuer's SEC listing name
        cus = json.loads((self.tmp / 'hh' / 'public' / 'cusips.json').read_text())['cusips']
        self.assertEqual(cus[AAPL], 'AAPL')
        ix = json.loads((self.tmp / 'hh' / 'public' / 'm' / 'index.json').read_text())
        self.assertEqual(ix['fields'], ['cik', 'name', 'first', 'last', 'lines', 'usd'])
        self.assertEqual(ix['rows'][0][0], 102909)                                     # the largest book first
        HH.GIANT = 5                                                                   # only the managers of over 5 lines
        HH.build(self.tmp / 'hh', self.hub, min_usd=1)
        self.assertEqual(list((self.tmp / 'hh' / 'public' / 'm').glob('*[0-9].json')), [])

    def test_unnamed_issuers_and_a_new_layout_reads_again(self):
        self.collect()
        root = self.tmp / 'hh'
        p = root / 'cache' / 'managers' / '2024-03-31.json.gz'
        d = HH.read_gz(p)
        d['rows']['444'][4] = [['999999990', 10, 5_000_000]]                         # a CUSIP no map names
        d['issuers']['999999990'] = ['HESS CORP', 'COM']
        HH.write_gz(p, d)
        HH.build(root, self.hub, min_usd=1)
        doc = json.loads((root / 'public' / 'm' / '444.json').read_text())
        self.assertEqual(doc['top'][0], [['~999999', round(5_000_000 / doc['usd'][0] / 1e-5)]])
        self.assertEqual(doc['names']['~999999'], 'Hess')
        state = json.loads((root / 'cache' / 'sets.json').read_text())
        self.assertEqual(state['mversion'], HH.MANAGERS_VERSION)
        state['mversion'] = 0                                                          # an older layout on file
        (root / 'cache' / 'sets.json').write_text(json.dumps(state))
        calls = []
        orig = self.fetch
        self.fetch = lambda url, dest=None: (calls.append(url.rsplit('/', 1)[-1]), orig(url, dest))[1]
        self.collect()
        self.assertEqual(calls, list(SETS))                                            # every data set read again
        self.assertEqual(json.loads((root / 'cache' / 'sets.json').read_text())['mversion'], HH.MANAGERS_VERSION)

    def test_ticker_sectors_from_the_sites_files(self):
        idx = self.tmp / 'index.json'
        idx.write_text(json.dumps({'companies': [{'ticker': 'BRK.B', 'sector': 'financials'}, {'ticker': 'X', 'sector': 'nope'}]}))
        t = HH.ticker_sectors([self.sec, self.etf, idx, self.tmp / 'missing.json'])
        self.assertEqual(t, {'AAPL': 'technology', 'MSFT': 'technology', 'MDT': 'health', 'BRK-B': 'financials'})


if __name__ == '__main__':
    unittest.main()
