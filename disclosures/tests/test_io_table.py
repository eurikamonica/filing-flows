"""io_table.py: one company's input-output account from a small synthetic 10-K — the identities (output = purchases +
value added; value added = pay + taxes on production + operating surplus; the surplus split), pay as disclosed, from
the headcount or from the industry, the cap on estimated taxes, the goods / services and resale splits of purchases,
revenue by segment, named customers, banks, and the headcount guard."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import io_table as IO
import notes as N

G = 'us-gaap:'
Y1, Y0 = ('2025-01-01', '2025-12-31'), ('2024-01-01', '2024-12-31')
E1, E0, EM = '2025-12-31', '2024-12-31', '2023-12-31'


def filing(extra=None, pay=None, bank=False):
    ctx, facts = {}, []

    def c(period, dims=None):
        key = (period, tuple(sorted((dims or {}).items())))
        cid = 'c' + str(abs(hash(key)) % 10 ** 9)
        ctx[cid] = ({'s': period[0], 'e': period[1]} if isinstance(period, tuple) else {'i': period}) | {'dims': dict(dims or {})}
        return cid

    def f(con, period, v, dims=None, u='USD'):
        facts.append({'c': con if ':' in con else G + con, 'v': float(v), 'ctx': c(period, dims), 'u': u, 'd': '-6', 'id': None})
    M = 1e6
    for y, k in ((Y1, 1.0), (Y0, 0.9)):
        f('Revenues', y, 1000 * M * k)
        f('CostOfRevenue', y, 600 * M * k); f('ResearchAndDevelopmentExpense', y, 50 * M * k); f('SellingGeneralAndAdministrativeExpense', y, 150 * M * k)
        f('OperatingIncomeLoss', y, 200 * M * k); f('DepreciationDepletionAndAmortization', y, 40 * M * k)
        f('ShareBasedCompensation', y, 10 * M * k); f('InterestExpense', y, 20 * M * k); f('IncomeTaxExpenseBenefit', y, 36 * M * k)
        f('NetIncomeLoss', y, 140 * M * k); f('PaymentsToAcquirePropertyPlantAndEquipment', y, 60 * M * k)
        if bank:
            f('IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', y, 176 * M * k)
            f('ProvisionForLoanLeaseAndOtherLosses', y, 30 * M * k)
        if pay:
            f('LaborAndRelatedExpense', y, pay * M * k)
    for e, fg, wip in ((E1, 90, 30), (E0, 80, 20), (EM, 70, 20)):
        f('InventoryFinishedGoodsNetOfReserves', e, fg * M); f('InventoryWorkInProcessNetOfReserves', e, wip * M)
        f('PropertyPlantAndEquipmentNet', e, 400 * M)
    seg = G + 'StatementBusinessSegmentsAxis'
    f('Revenues', Y1, 700 * M, {seg: 'x:AlphaMember'}); f('Revenues', Y1, 300 * M, {seg: 'x:BetaMember'})
    f('ConcentrationRiskPercentage1', Y1, 0.12, {G + 'ConcentrationRiskByBenchmarkAxis': G + 'RevenueFromContractWithCustomerProductAndServiceBenchmarkMember',
                                                 G + 'ConcentrationRiskByTypeAxis': G + 'CustomerConcentrationRiskMember', 'srt:MajorCustomersAxis': 'x:CustomerAMember'}, u='pure')
    for k, v in (extra or {}).items():
        f(k, Y1, v)
    F = {'reports': [], 'contexts': ctx, 'units': {}, 'facts': facts, 'pre': {}, 'cal': {}, 'def': {}, 'roles': {},
         'labels': {'x:AlphaMember': {'label': 'Alpha [Member]'}, 'x:BetaMember': {'label': 'Beta Segment [Member]'}, 'x:CustomerAMember': {'label': 'Customer A [Member]'}}}
    return N.Filing(F, {})


def line(io, k, g=None):
    return next(l for l in io['lines'] if l['k'] == k and (g is None or l['g'] == g))


class Account(unittest.TestCase):
    def test_identities(self):
        io = IO.build_io(filing(), {}, {G + 'Revenues': {'n2'}}, sic='3674')
        out, inter, va = line(io, 'output')['v'], line(io, 'inter')['v'], line(io, 'va')['v']
        self.assertEqual(line(io, 'dinv', 'output')['v'], 20e6)          # finished goods +10, work in process +10
        self.assertEqual(out, 1020e6)
        self.assertAlmostEqual(out, inter + va, delta=2)
        self.assertAlmostEqual(va, line(io, 'comp')['v'] + line(io, 'taxp')['v'] + line(io, 'gos')['v'], delta=2)
        gos = line(io, 'gos')['v']
        parts = sum(line(io, k)['v'] for k in ('da', 'interest', 'inctax', 'ni')) + line(io, 'dinv', 'gos')['v']
        rest = next((l['v'] for l in io['lines'] if l['k'] == 'gos_rest'), 0)
        self.assertAlmostEqual(gos, parts + rest, delta=0.005 * out)      # a remainder under 0.5% of output is not listed
        self.assertEqual(line(io, 'revenue')['notes'], ['n2'])             # the line links to its note
        self.assertEqual(line(io, 'revenue')['src'], '10-K')
        self.assertEqual(line(io, 'revenue')['v0'], 900e6)                 # and the year before
        self.assertEqual(io['comp_how'], 'industry')

    def test_pay_disclosed_or_from_headcount(self):
        io = IO.build_io(filing(pay=250), {}, {}, sic='3674')
        self.assertEqual((io['comp_how'], line(io, 'comp')['v'], line(io, 'comp')['src']), ('disclosed', 250e6, '10-K'))
        io = IO.build_io(filing(), {}, {}, sic='3674', employees={'employees': 1000})
        per = IO._json(IO.BEA_PAY)['lines']['20'][1]                       # computer and electronic products
        self.assertEqual(io['comp_how'], 'headcount')
        self.assertAlmostEqual(line(io, 'comp')['v'], 1000 * per + 10e6, delta=2)
        self.assertEqual(io['labor']['employees'], 1000)
        io = IO.build_io(filing(), {}, {}, sic='3674', employees={'employees': 5})   # $200M per employee: not a real headcount
        self.assertEqual(io['comp_how'], 'industry')
        self.assertIsNone(io['labor'])

    def test_tax_cap_and_purchase_groups(self):
        io = IO.build_io(filing(), {}, {}, sic='5331')                    # a retailer: BEA's taxes include sales tax
        spend = 1000e6 - 200e6 - 40e6
        self.assertLessEqual(line(io, 'taxp')['v'], IO.TAX_CAP * spend + 1)
        self.assertEqual([g['k'] for g in io['inputs']], ['resale', 'other'])
        self.assertEqual(io['inputs'][0]['v'], min(600e6, line(io, 'inter')['v']))
        io = IO.build_io(filing(), {}, {}, sic='3674')
        self.assertEqual([g['k'] for g in io['inputs']], ['goods', 'services'])
        self.assertAlmostEqual(sum(g['v'] for g in io['inputs']), line(io, 'inter')['v'], delta=2)
        goods = io['inputs'][0]
        self.assertTrue(goods['imports'] > 0 and goods['suppliers'])
        io = IO.build_io(filing(), {}, {}, sic='7372')                    # software: one group over the whole mix
        self.assertEqual([g['k'] for g in io['inputs']], ['all'])

    def test_splits_and_customers(self):
        io = IO.build_io(filing(), {}, {}, sic='3674')
        self.assertEqual(io['splits']['segment'], [['Alpha', 700e6], ['Beta', 300e6]])
        self.assertEqual(io['customers'], [['Customer A', 0.12]])

    def test_bank(self):
        io = IO.build_io(filing(bank=True, pay=300), {}, {}, sic='6021')
        self.assertTrue(io['financial'])
        self.assertEqual(line(io, 'finc')['v'], 30e6)                      # credit losses; interest is inside net revenue
        self.assertIn('Credit losses', io['fin_label'])
        self.assertFalse(any(l['k'] == 'interest' for l in io['lines']))
        out, inter, finc, va = (line(io, k)['v'] for k in ('output', 'inter', 'finc', 'va'))
        self.assertAlmostEqual(out, inter + finc + va, delta=2)

    def test_writedowns_are_not_purchases(self):
        base = IO.build_io(filing(), {}, {}, sic='2000')
        hit = IO.build_io(filing(extra={'GoodwillImpairmentLoss': 100e6, 'OperatingIncomeLoss': 0}), {}, {}, sic='2000')
        self.assertEqual(line(hit, 'impair')['v'], 100e6)
        # the impairment lowered operating income by 100 (200 → 100 after the duplicate fact is ignored, or 0): purchases do
        # not grow by it — it sits in the surplus as capital lost
        self.assertLessEqual(line(hit, 'inter')['v'], line(base, 'inter')['v'] + 1)

    def test_bank_revenue_is_not_fee_income(self):
        io = IO.build_io(filing(bank=True, extra={'RevenueFromContractWithCustomerExcludingAssessedTax': 50e6}), {}, {}, sic='6021')
        self.assertEqual(line(io, 'revenue')['v'], 1000e6)                 # Revenues, not the fee income of ASC 606

    def test_mix(self):
        io = IO._json(IO.BEA_IO)
        self.assertEqual(IO.bea_mix(io, '3674'), {'334413': 1.0})
        self.assertTrue(IO.bea_mix(io, '7370'))                            # a code ending in 0: its three-digit group
        pay = IO._json(IO.BEA_PAY)
        self.assertEqual(IO.pay_line(pay, '334413'), '20')
        self.assertEqual(IO.pay_line(pay, '452000'), '41')


if __name__ == '__main__':
    unittest.main()
