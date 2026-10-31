"""notes.py and xbrl_filing.py: a small synthetic 10-K — the reader, the report matching, the ties (sums, roll-forwards,
splits, cross-statement ties, balance sheet vs cash flow), the charts, the analysis and the written reading."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import notes as N
import xbrl_filing as X

G = 'us-gaap:'
Y1, Y0 = ('2025-01-01', '2025-12-31'), ('2024-01-01', '2024-12-31')
E1, E0, EM1 = '2025-12-31', '2024-12-31', '2023-12-31'
ROLE = lambda r: 'http://example.com/role/' + r


def synthetic(inv_gap=0.0, warranty_used=300.0):
    ctx, facts = {}, []

    def c(period, dims=None):
        key = (period, tuple(sorted((dims or {}).items())))
        cid = 'c' + str(abs(hash(key)) % 10 ** 9)
        ctx[cid] = ({'s': period[0], 'e': period[1]} if isinstance(period, tuple) else {'i': period}) | {'dims': dict(dims or {})}
        return cid

    def f(con, period, v, dims=None, u='USD', d='-6'):
        facts.append({'c': con if ':' in con else G + con, 'v': float(v), 'ctx': c(period, dims), 'u': u, 'd': d, 'id': None})
    M = 1e6
    for y, rev, cogs in ((Y1, 1000, 600), (Y0, 800, 500)):
        f('Revenues', y, rev * M); f('CostOfRevenue', y, cogs * M); f('GrossProfit', y, (rev - cogs) * M)
    f('Revenues', Y1, 700 * M, {G + 'StatementBusinessSegmentsAxis': 'x:AMember'}); f('Revenues', Y1, 300 * M, {G + 'StatementBusinessSegmentsAxis': 'x:BMember'})
    f('Revenues', Y0, 500 * M, {G + 'StatementBusinessSegmentsAxis': 'x:AMember'}); f('Revenues', Y0, 300 * M, {G + 'StatementBusinessSegmentsAxis': 'x:BMember'})
    for e, inv, cash in ((E1, 300, 120), (E0, 200, 100)):
        f('InventoryRawMaterialsNetOfReserves', e, inv * 0.4 * M); f('InventoryFinishedGoodsNetOfReserves', e, inv * 0.6 * M); f('InventoryNet', e, inv * M)
        f('CashAndCashEquivalentsAtCarryingValue', e, cash * M); f('CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents', e, cash * M)
        f('Assets', e, (inv + cash) * M); f('LiabilitiesAndStockholdersEquity', e, (inv + cash) * M)
    f('IncreaseDecreaseInInventories', Y1, (100 - inv_gap) * M)
    f('ProductWarrantyAccrual', E0, 500 * M); f('ProductWarrantyAccrualWarrantiesIssued', Y1, 400 * M); f('ProductWarrantyAccrualPayments', Y1, warranty_used * M)
    f('ProductWarrantyAccrual', E1, 600 * M)
    f('EarningsPerShareBasic', Y1, 4.0, u='USD/shares', d='2'); f('NetIncomeLoss', Y1, 400 * M); f('WeightedAverageNumberOfSharesOutstandingBasic', Y1, 100 * M, u='shares', d='-6')
    pre = {
        ROLE('Income'): [{'c': G + 'Revenues', 'depth': 1, 'pref': None}, {'c': G + 'CostOfRevenue', 'depth': 1, 'pref': None}, {'c': G + 'GrossProfit', 'depth': 1, 'pref': 'total'},
                         {'c': G + 'NetIncomeLoss', 'depth': 1, 'pref': None}, {'c': G + 'EarningsPerShareBasic', 'depth': 1, 'pref': None}],
        ROLE('Balance'): [{'c': G + 'CashAndCashEquivalentsAtCarryingValue', 'depth': 1, 'pref': None}, {'c': G + 'InventoryNet', 'depth': 1, 'pref': None},
                          {'c': G + 'Assets', 'depth': 1, 'pref': 'total'}, {'c': G + 'LiabilitiesAndStockholdersEquity', 'depth': 1, 'pref': 'total'}],
        ROLE('CashFlow'): [{'c': G + 'IncreaseDecreaseInInventories', 'depth': 1, 'pref': None}, {'c': G + 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents', 'depth': 1, 'pref': 'end'}],
        ROLE('Inventory'): [{'c': G + 'InventoryNetAbstract', 'depth': 0, 'pref': None}, {'c': G + 'InventoryRawMaterialsNetOfReserves', 'depth': 1, 'pref': None},
                            {'c': G + 'InventoryFinishedGoodsNetOfReserves', 'depth': 1, 'pref': None}, {'c': G + 'InventoryNet', 'depth': 1, 'pref': 'total'}],
        ROLE('InventoryNote'): [{'c': G + 'InventoryDisclosureTextBlock', 'depth': 0, 'pref': None}],
        ROLE('Warranty'): [{'c': G + 'ProductWarrantyAccrual', 'depth': 1, 'pref': 'start'}, {'c': G + 'ProductWarrantyAccrualWarrantiesIssued', 'depth': 1, 'pref': None},
                           {'c': G + 'ProductWarrantyAccrualPayments', 'depth': 1, 'pref': None}, {'c': G + 'ProductWarrantyAccrual', 'depth': 1, 'pref': 'end'}],
        ROLE('WarrantyNote'): [{'c': G + 'ProductWarrantyDisclosureTextBlock', 'depth': 0, 'pref': None}],
        ROLE('Segments'): [{'c': G + 'StatementBusinessSegmentsAxis', 'depth': 1, 'pref': None}, {'c': G + 'SegmentDomain', 'depth': 2, 'pref': None},
                           {'c': 'x:AMember', 'depth': 3, 'pref': None}, {'c': 'x:BMember', 'depth': 3, 'pref': None}, {'c': G + 'Revenues', 'depth': 1, 'pref': None}],
        ROLE('SegmentNote'): [{'c': G + 'SegmentReportingDisclosureTextBlock', 'depth': 0, 'pref': None}],
    }
    facts.append({'c': G + 'ProductWarrantyDisclosureTextBlock', 'v': '<p>Changes in the warranty accrual follow shipments.</p>', 'ctx': c(Y1), 'u': None, 'd': None, 'id': None})
    facts.append({'c': G + 'InventoryDisclosureTextBlock', 'v': '<p>Inventories rose with demand.</p><table><tr><td>1</td></tr></table>', 'ctx': c(Y1), 'u': None, 'd': None, 'id': None})
    cal = {ROLE('Income'): {G + 'GrossProfit': [(G + 'Revenues', 1.0), (G + 'CostOfRevenue', -1.0)]},
           ROLE('Inventory'): {G + 'InventoryNet': [(G + 'InventoryRawMaterialsNetOfReserves', 1.0), (G + 'InventoryFinishedGoodsNetOfReserves', 1.0)]}}
    dfn = {ROLE('Segments'): {'axes': {G + 'StatementBusinessSegmentsAxis': [G + 'SegmentDomain', 'x:AMember', 'x:BMember']}, 'items': set()}}
    labels = {'x:AMember': {'label': 'Segment A [Member]'}, 'x:BMember': {'label': 'Segment B [Member]'}, G + 'Revenues': {'label': 'Revenue'}}
    reports = [
        {'r': 'R2', 'short': 'Consolidated Statements of Income', 'role': ROLE('Income'), 'cat': 'Statements', 'parent': None, 'pos': 2, 'long': ''},
        {'r': 'R3', 'short': 'Consolidated Balance Sheets', 'role': ROLE('Balance'), 'cat': 'Statements', 'parent': None, 'pos': 3, 'long': ''},
        {'r': 'R4', 'short': 'Consolidated Statements of Cash Flows', 'role': ROLE('CashFlow'), 'cat': 'Statements', 'parent': None, 'pos': 4, 'long': ''},
        {'r': 'R5', 'short': 'Inventories (Notes)', 'role': ROLE('InventoryNote'), 'cat': 'Notes', 'parent': None, 'pos': 5, 'long': ''},
        {'r': 'R6', 'short': 'Product Warranty', 'role': ROLE('WarrantyNote'), 'cat': 'Notes', 'parent': None, 'pos': 6, 'long': ''},
        {'r': 'R7', 'short': 'Segment Information', 'role': ROLE('SegmentNote'), 'cat': 'Notes', 'parent': None, 'pos': 7, 'long': ''},
        {'r': 'R8', 'short': 'Inventories - Components (Narrative) (Details)', 'role': ROLE('Inventory'), 'cat': 'Details', 'parent': None, 'pos': 8, 'long': ''},
        {'r': 'R9', 'short': 'Changes in the Accrual (Detail)', 'role': ROLE('Warranty'), 'cat': 'Details', 'parent': None, 'pos': 9, 'long': ''},
        {'r': 'R10', 'short': 'Segment Information - Revenue (Details)', 'role': ROLE('Segments'), 'cat': 'Details', 'parent': ROLE('SegmentNote'), 'pos': 10, 'long': ''},
    ]
    crdr = {G + 'ProductWarrantyAccrual': 'credit', G + 'ProductWarrantyAccrualWarrantiesIssued': 'credit', G + 'ProductWarrantyAccrualPayments': 'debit'}
    F = {'reports': reports, 'contexts': ctx, 'units': {}, 'facts': facts, 'labels': labels, 'pre': pre, 'cal': cal, 'def': dfn, 'roles': {ROLE('WarrantyNote'): '995 - Disclosure - Product Warranty’s'}}
    return N.Filing(F, crdr)


def by_title(doc, text):
    return [c for c in doc['checks'] if text in c['title']]


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = N.build(synthetic(), {'ticker': 'TST', 'cik': 1, 'accession': 'x'})

    def test_reports_matched_to_notes(self):
        titles = {n['title']: [t['id'] for t in n['tables']] for n in self.doc['notes']}
        self.assertEqual(titles['Inventories (Notes)'], ['R8'])            # "(Narrative) (Details)" and "(Notes)" stripped
        self.assertEqual(titles['Product Warranty’s'], ['R9'])             # no parent, no name: by its place in the list and the note's words
        self.assertEqual(titles['Segment Information'], ['R10'])           # by its parent
        self.assertEqual(self.doc['fy'], 'FY2025')

    def test_checks(self):
        self.assertEqual(by_title(self.doc, 'Gross')[0]['status'], 'tie')
        self.assertEqual(by_title(self.doc, 'Total assets = total liabilities')[0]['status'], 'tie')
        self.assertEqual(by_title(self.doc, 'Cash at the end')[0]['status'], 'tie')
        roll = [c for c in self.doc['checks'] if c['kind'] == 'rollfwd']
        self.assertEqual(len(roll), 1)
        self.assertEqual(roll[0]['status'], 'tie')                       # 500 + 400 − 300 = 600 (directions from debit / credit)
        self.assertEqual([p[2] for p in roll[0]['parts']], [1, 1, -1])
        seg = [c for c in self.doc['checks'] if c['kind'] == 'members']
        self.assertTrue(seg and seg[0]['status'] == 'tie' and seg[0]['result'][1] == 1000e6)
        eps = by_title(self.doc, 'Basic EPS')[0]
        self.assertEqual(eps['status'], 'tie')
        inv = by_title(self.doc, 'Inventories: change on the balance sheet')[0]
        self.assertEqual(inv['status'], 'tie')
        self.assertEqual(inv['scope'], 'cf-bs')

    def test_gaps_are_flagged(self):
        d = N.build(synthetic(inv_gap=40, warranty_used=250), {'ticker': 'TST', 'cik': 1})
        inv = by_title(d, 'Inventories: change on the balance sheet')[0]
        self.assertEqual(inv['status'], 'info')                          # a cash flow vs balance sheet gap is explained, not an error
        self.assertAlmostEqual(inv['diff'], 40e6)
        roll = [c for c in d['checks'] if c['kind'] == 'rollfwd']
        self.assertEqual([c['status'] for c in roll], ['gap'])          # 500 + 400 − 250 ≠ 600
        self.assertAlmostEqual(abs(roll[0]['diff']), 50e6)

    def test_links_and_charts(self):
        bs = next(s for s in self.doc['statements'] if s['kind'] == 'bs')
        i = next(k for k, r in enumerate(bs['table']['rows']) if r.get('c') == G + 'InventoryNet')
        self.assertIn('n1', bs['lines'][i]['notes'])                        # the balance sheet line → the inventory note
        notes = {n['id']: n for n in self.doc['notes']}
        types = {t['id']: [c['type'] for c in t['charts']] for n in notes.values() for t in n['tables']}
        self.assertEqual(types['R8'][0], 'composition')
        self.assertEqual(types['R9'][0], 'waterfall')
        self.assertEqual(types['R10'][0], 'members')
        seg = notes['n3']['tables'][0]['charts'][0]
        self.assertEqual([m[0] for m in seg['members']], ['Segment A', 'Segment B'])     # "[Member]" stripped
        self.assertTrue(any('Inventories cover' in a for a in notes['n1']['analysis']))
        self.assertTrue(any('Segment A is the largest' in a for a in notes['n3']['analysis']))
        self.assertEqual(notes['n1']['text'], ['Inventories rose with demand.'])          # the prose without the table

    def test_reading_only_for_its_filing(self):
        with tempfile.TemporaryDirectory() as d:
            old = N.READS
            N.READS = Path(d)
            (Path(d) / 'TST.json').write_text(json.dumps({'accession': 'x', 'summary': ['s'], 'threads': [{'title': 't', 'text': 'x', 'notes': ['Product Warranty’s']}],
                                                         'notes': {'Segment Information': 'read'}}))
            try:
                r = N.curated_read({'ticker': 'TST', 'accession': 'x'}, self.doc['notes'])
                self.assertEqual(r['threads'][0]['notes'], ['n2'])
                self.assertEqual(r['notes'], {'n3': 'read'})
                self.assertIsNone(N.curated_read({'ticker': 'TST', 'accession': 'y'}, self.doc['notes']))
            finally:
                N.READS = old


class Pieces(unittest.TestCase):
    def test_notes_against_last_year(self):
        """Each note against the same note in last year's 10-K: sentences added, gone, the same with new figures, reworded;
        a note new this year and a note gone; the change score."""
        cur = [('n1', 'Inventories', 'Inventories rose with demand for our data center products during the year. '
                                     'Inventory reserves were $45 million at year end, compared with $30 million a year earlier. '
                                     'We entered into new purchase commitments with three suppliers for advanced packaging capacity.'),
               ('n2', 'Product Warranty', 'Changes in the warranty accrual follow shipments of our systems to customers each quarter.'),
               ('n3', 'Segment Information', 'We report two segments, Compute and Networking, based on how our chief decision maker reviews results.'),
               ('n4', 'Restructuring', 'In the fourth quarter we began a restructuring plan to reduce our workforce by about five percent.')]
        prev = [('Inventories', 'Inventories rose with demand for our data center products during the year. '
                                'Inventory reserves were $30 million at year end, compared with $22 million a year earlier. '
                                'Obsolete inventory was written off in the second quarter after a product transition ended.'),
                ('Product Warranties', 'Changes in the warranty accrual follow shipments of our systems to customers each quarter.'),
                ('Segment Information', 'We report two segments, Compute and Networking, based on how the chief decision maker reviews the results.'),
                ('Discontinued Operations', 'The sale of the legacy business closed in the first quarter of the year before.')]
        y = N.note_changes(cur, prev)
        inv = y['notes']['n1']
        self.assertEqual((inv['n_added'], inv['n_removed'], inv['n_updated']), (1, 1, 1))
        self.assertIn('purchase commitments', inv['added'][0])
        self.assertIn('written off', inv['removed'][0])
        self.assertIn('$30 million', inv['updated'][0][0])
        self.assertIn('$45 million', inv['updated'][0][1])
        self.assertEqual(y['notes']['n2']['score'], 0.0, 'retitled (Warranties → Warranty), unchanged')
        self.assertEqual((y['notes']['n3']['n_updated'], y['notes']['n3']['n_added']), (1, 0), 'reworded, not new')
        self.assertTrue(y['notes']['n4']['new'])
        self.assertEqual(y['gone'], ['Discontinued Operations'])
        self.assertGreater(inv['score'], y['notes']['n3']['score'])
        # in the build: last year's notes in, the yoy block out
        doc = N.build(synthetic(), {'ticker': 'TST', 'cik': 1, 'accession': 'x'},
                      {'prev_notes': {'notes': [('Inventories (Notes)', 'Inventories fell with demand across the whole of the product line.')], 'meta': {'fy': 'FY2024'}}})
        self.assertEqual(doc['yoy']['prev'], {'fy': 'FY2024'})
        self.assertEqual(doc['yoy']['new_notes'], 2, 'warranty and segments: no such note last year')
        self.assertNotIn('yoy', N.build(synthetic(), {'ticker': 'TST', 'cik': 1, 'accession': 'x'}), 'no last year on file: no block')

    def test_norm_title(self):
        self.assertEqual(N.norm_title('Investments (Narrative) (Details)'), 'investments')
        self.assertEqual(N.norm_title('Note 4 — Debt (Notes)'), 'debt')
        self.assertEqual(N.norm_title('Shareholders’ Equity'), N.norm_title("Shareholders' Equity"))

    def test_status(self):
        self.assertEqual(N._status(0.4e6, 1e6, 1e9), 'tie')
        self.assertEqual(N._status(2e6, 1e6, 1e9), 'round')
        self.assertEqual(N._status(50e6, 1e6, 1e9), 'gap')

    def test_reader(self):
        inst = '''<?xml version="1.0"?><xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
<context id="d"><entity><identifier scheme="x">1</identifier></entity><period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
<context id="a"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">x:AMember</xbrldi:explicitMember></segment></entity><period><instant>2025-12-31</instant></period></context>
<unit id="usd"><measure>iso4217:USD</measure></unit>
<us-gaap:Revenues contextRef="d" unitRef="usd" decimals="-6">1000000000</us-gaap:Revenues>
<us-gaap:Assets contextRef="a" unitRef="usd" decimals="-6">5000000</us-gaap:Assets></xbrl>'''
        pre = '''<?xml version="1.0"?><link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
<link:presentationLink xlink:role="http://e/role/IS"><link:loc xlink:label="a" xlink:href="x.xsd#us-gaap_IncomeStatementAbstract"/><link:loc xlink:label="b" xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_Revenues"/>
<link:presentationArc xlink:from="a" xlink:to="b" order="1" preferredLabel="http://www.xbrl.org/2003/role/totalLabel"/></link:presentationLink>
<link:calculationLink xlink:role="http://e/role/IS"><link:loc xlink:label="p" xlink:href="x.xsd#us-gaap_GrossProfit"/><link:loc xlink:label="c" xlink:href="x.xsd#us-gaap_CostOfRevenue"/>
<link:calculationArc xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" xlink:from="p" xlink:to="c" weight="-1"/></link:calculationLink></link:linkbase>'''
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'i.xml').write_text(inst)
            (Path(d) / 'p.xml').write_text(pre)
            ctx, units, facts = X.instance(Path(d) / 'i.xml')
            self.assertEqual(ctx['a']['dims'], {'us-gaap:StatementBusinessSegmentsAxis': 'x:AMember'})
            self.assertEqual({f['c']: f['v'] for f in facts}, {'us-gaap:Revenues': 1e9, 'us-gaap:Assets': 5e6})
            self.assertEqual(units['usd'], 'USD')
            pr = X.presentation(Path(d) / 'p.xml')['http://e/role/IS']
            self.assertEqual([(n['c'], n['depth'], n['pref']) for n in pr], [('us-gaap:IncomeStatementAbstract', 0, None), ('us-gaap:Revenues', 1, 'total')])
            self.assertEqual(X.calculation(Path(d) / 'p.xml'), {'http://e/role/IS': {'us-gaap:GrossProfit': [('us-gaap:CostOfRevenue', -1.0)]}})


if __name__ == '__main__':
    unittest.main()
