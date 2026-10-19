"""Debt & rates: term sheets, prospectus covers, credit agreements, XBRL instruments, companyfacts figures, the safety
analysis, the implied CDS and the FDIC deposit summary — on small synthetic documents shaped like the real ones."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import debt_docs as D  # noqa: E402
import debt_facts as F  # noqa: E402
import debt_model as M  # noqa: E402
import debt  # noqa: E402

TERM_SHEET = """<html><body><p>Filed Pursuant to Rule 433</p><p>APPLE INC.</p><p>FINAL PRICING TERM SHEET</p>
<p>4.000% Notes due 2028 (“2028 Notes”)</p><table>
<tr><td>Issuer:</td><td>Apple Inc.</td></tr><tr><td>Principal Amount:</td><td>$1,500,000,000</td></tr>
<tr><td>Maturity:</td><td>May 12, 2028</td></tr><tr><td>Coupon:</td><td>4.000%</td></tr><tr><td>Price to Public:</td><td>99.804%</td></tr>
<tr><td>Benchmark Treasury:</td><td>3.750% due April 15, 2028</td></tr><tr><td>Benchmark Treasury Yield:</td><td>3.820%</td></tr>
<tr><td>Spread to Benchmark Treasury:</td><td>25 basis points</td></tr><tr><td>Yield:</td><td>4.070%</td></tr>
<tr><td>Trade Date:</td><td>May 5, 2025</td></tr><tr><td>Ratings:*</td><td>Aaa (stable) by Moody’s</td></tr></table>
<p>4.200% Notes due 2030 (“2030 Notes”)</p><table>
<tr><td>Principal Amount:</td><td>$1,000,000,000</td></tr><tr><td>Maturity:</td><td>May 12, 2030</td></tr><tr><td>Coupon:</td><td>4.200%</td></tr>
<tr><td>Price to Public:</td><td>99.830%</td></tr><tr><td>Benchmark Treasury Yield:</td><td>3.938%</td></tr>
<tr><td>Spread to Benchmark Treasury:</td><td>+30 bps</td></tr><tr><td>Yield to Maturity:</td><td>4.238%</td></tr></table></body></html>"""

MULTI = """<p>Final Term Sheet</p><p>U.S.$750,000,000 4.750% GLOBAL NOTES DUE 2033</p><p>U.S.$1,750,000,000 5.250% GLOBAL NOTES DUE 2036</p>
<table><tr><td>INTEREST RATE:</td><td>4.750% per annum for the 2033 Notes<br>5.250% per<br>annum for the 2036 Notes</td></tr>
<tr><td>AGGREGATE PRINCIPAL AMOUNT OFFERED:</td><td>$750,000,000 for the 2033 Notes<br>$1,750,000,000 for the 2036 Notes</td></tr>
<tr><td>MATURITY DATE:</td><td>April 30, 2033, for the 2033 Notes<br>October 30, 2036, for the 2036 Notes</td></tr></table>"""

CREDIT = """<p>EXECUTION VERSION</p><p>$5,000,000,000 REVOLVING CREDIT AGREEMENT dated as of March 6, 2026 among EXAMPLE CORP, as Borrower</p>
<p>“Applicable Margin” means, for Term SOFR Advances, 0.875% to 1.250% per annum based on the Public Debt Rating, and for Base Rate Advances 0.000% to 0.250%.
“Borrower” means Example Corp.</p><p>The Company agrees to pay a facility fee at a rate of 0.125% per annum.</p>
<p>“Maturity Date” means March 6, 2031.</p>
<p>Section 6.01 Financial Covenant. The Borrower shall ensure that the Consolidated Net Interest Coverage Ratio as at the last day of any fiscal quarter is not less than 3.0 to 1.0.</p>
<p>The Borrower may incur additional Indebtedness if, on a Pro Forma Basis, the Consolidated Leverage Ratio does not exceed 4.50 to 1.00.</p>"""

INSTANCE = """<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:ex="http://example.com">
<xbrli:context id="c1"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:DebtInstrumentAxis">ex:SeniorNotesDue2030Member</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="c2"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:DebtInstrumentAxis">ex:ConvertibleNotesDue2029Member</xbrldi:explicitMember><xbrldi:explicitMember dimension="us-gaap:LongtermDebtTypeAxis">us-gaap:ConvertibleDebtMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="c3"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">ex:SegAMember</xbrldi:explicitMember><xbrldi:explicitMember dimension="us-gaap:DebtInstrumentAxis">ex:SeniorNotesDue2030Member</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
<us-gaap:DebtInstrumentInterestRateStatedPercentage contextRef="c1">0.0450</us-gaap:DebtInstrumentInterestRateStatedPercentage>
<us-gaap:LongTermDebt contextRef="c1" unitRef="usd">1000000000</us-gaap:LongTermDebt>
<us-gaap:LongTermDebt contextRef="c3" unitRef="usd">999</us-gaap:LongTermDebt>
<us-gaap:DebtInstrumentFaceAmount contextRef="c2" unitRef="usd">500000000</us-gaap:DebtInstrumentFaceAmount>
<us-gaap:DebtInstrumentConvertibleConversionPrice1 contextRef="c2" unitRef="usdPerShare">50.00</us-gaap:DebtInstrumentConvertibleConversionPrice1>
</xbrli:xbrl>"""


def cf_of(**concepts):
    """A companyfacts-shaped dict: concept -> [(start|None, end, val, filed)]."""
    facts = {}
    for c, rows in concepts.items():
        facts[c] = {'units': {'USD': [{'start': s, 'end': e, 'val': v, 'filed': f, 'form': '10-Q'} for s, e, v, f in rows]}}
    return {'facts': {'us-gaap': facts, 'dei': {'EntityCommonStockSharesOutstanding': {'units': {'shares': [{'end': '2026-07-20', 'val': 1e9, 'filed': '2026-07-30'}]}}}}}


class TermSheets(unittest.TestCase):
    def test_two_tranches(self):
        r = D.parse_term_sheet(TERM_SHEET, '2025-05-05')
        self.assertEqual(len(r), 2)
        a, b = r
        self.assertEqual((a['coupon'], a['principal'], a['maturity'], a['spread_bps'], a['yield'], a['price']), (4.0, 1.5e9, '2028-05-12', 25.0, 4.07, 99.804))
        self.assertEqual((b['coupon'], b['spread_bps'], b['yield']), (4.2, 30.0, 4.238))
        self.assertIn('Aaa', a['ratings'])

    def test_values_listed_per_tranche(self):
        r = D.parse_term_sheet(MULTI, '2026-04-23')
        self.assertEqual([(x['coupon'], x['principal'], x['maturity']) for x in r], [(4.75, 7.5e8, '2033-04-30'), (5.25, 1.75e9, '2036-10-30')])

    def test_structured_notes_are_not_bonds(self):
        self.assertEqual(D.parse_term_sheet('<p>Structured Investments</p><p>Summary of Terms</p><p>Contingent Interest Rate: 9%</p>'), [])

    def test_prospectus_cover(self):
        r = D.parse_prospectus_cover('<p>$1,000,000,000 4.375% Notes due 2030</p><p>$500,000,000 Floating Rate Notes due 2027</p>', '2025-01-02')
        self.assertEqual([(x['coupon'] if not x['floating'] else 'fl', x['principal'], x['maturity_year']) for x in r], [(4.375, 1e9, 2030), ('fl', 5e8, 2027)])


class CreditAgreements(unittest.TestCase):
    def test_terms_and_covenants(self):
        a = D.parse_credit_agreement(CREDIT)
        self.assertEqual(a['kind'], 'credit_agreement')
        self.assertEqual((a['size'], a['dated'], a['maturity'], a['facility']), (5e9, '2026-03-06', '2031-03-06', 'revolving'))
        self.assertEqual(a['margin_pct'], [0.875, 1.25])
        self.assertEqual(a['fee_pct'], 0.125)
        cov = {c['type']: c for c in a['covenants']}
        self.assertEqual((cov['interest_coverage']['limit'], cov['interest_coverage']['direction'], cov['interest_coverage']['maintenance']), (3.0, 'min', True))
        self.assertFalse(cov['leverage']['maintenance'])     # an incurrence test, not a maintenance covenant

    def test_indenture_is_not_a_credit_agreement(self):
        self.assertEqual(D.parse_credit_agreement('<p>INDENTURE dated as of May 1, 2025 5.125% SENIOR NOTES</p>')['kind'], 'indenture')


class Instruments(unittest.TestCase):
    def test_instance(self):
        r = {i['name']: i for i in D.parse_instance(INSTANCE.encode(), {'SeniorNotesDue2030Member': '4.50% Senior Notes due 2030'})}
        n = r['4.50% Senior Notes due 2030']
        self.assertEqual((n['coupon'], n['carrying'], n['kind'], n['maturity_year']), (0.045, 1e9, 'notes', 2030))
        c = next(v for k, v in r.items() if 'Convertible' in k)
        self.assertEqual((c['kind'], c['conv_price'], c['face']), ('convertible', 50.0, 5e8))


class Facts(unittest.TestCase):
    def cf(self):
        q = lambda s, e, v: (s, e, v, '2026-07-30')
        return cf_of(DebtCurrent=[(None, '2026-06-30', 1e9, '2026-07-30')], LongTermDebtNoncurrent=[(None, '2026-06-30', 9e9, '2026-07-30')],
                     CashAndCashEquivalentsAtCarryingValue=[(None, '2026-06-30', 2e9, '2026-07-30')], Assets=[(None, '2026-06-30', 5e10, '2026-07-30')],
                     InterestExpense=[q('2025-01-01', '2025-12-31', 4e8), q('2025-01-01', '2025-06-30', 2e8), q('2026-01-01', '2026-06-30', 2.4e8)],
                     OperatingIncomeLoss=[q('2025-01-01', '2025-12-31', 3e9), q('2025-01-01', '2025-06-30', 1.4e9), q('2026-01-01', '2026-06-30', 1.6e9)],
                     LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths=[(None, '2025-12-31', 1.2e9, '2026-02-01')],
                     LongTermDebt=[(None, '2019-12-31', 1, '2020-02-01')])
    def test_snapshot(self):
        s, src = F.snapshot(self.cf())
        self.assertEqual((s['total_debt'], s['cash'], s['current_debt'], s['balance_date']), (1e10, 2e9, 1e9, '2026-06-30'))
        self.assertAlmostEqual(s['interest_expense'], 4.4e8)      # FY 400 + H1 240 − prior H1 200
        self.assertAlmostEqual(s['operating_income'], 3.2e9)
        self.assertEqual(s['maturities']['next12m'], 1.2e9)
        self.assertIn('DebtCurrent', src['total_debt'])

    def test_stale_debt_tag_is_dropped(self):
        cf = cf_of(LongTermDebt=[(None, '2019-12-31', 5e9, '2020-02-01')], Assets=[(None, '2026-06-30', 1e10, '2026-07-30')])
        self.assertIsNone(F.snapshot(cf)[0].get('total_debt'))


class Model(unittest.TestCase):
    def test_merton_more_debt_means_closer_to_default(self):
        a = M.implied(100e9, 0.3, 5e9, 20e9, 0.04); b = M.implied(100e9, 0.3, 20e9, 120e9, 0.04)
        self.assertGreater(a['dd'], b['dd'])
        self.assertLess(a['spread_5y_bps'], b['spread_5y_bps'])

    def test_calibration_is_monotone(self):
        pairs = [(dd, 40 * 2.718 ** (-0.15 * (dd - 10)), 7) for dd in [2, 3, 4, 5, 6, 8, 10, 12, 14] * 4]
        fit = M.fit_calibration(pairs)
        self.assertLess(fit['b'], 0)
        self.assertGreater(M.calibrated(3, fit), M.calibrated(12, fit))
        self.assertGreater(fit['r2'], 0.95)

    def test_convertibles_if_converted(self):
        snap = {'total_debt': 1e10, 'current_debt': 1e9, 'operating_income': 2e9, 'da': 5e8, 'interest_expense': 3e8, 'shares': 1e9, 'cash': 1e9}
        inst = [{'name': '2029 Convertible Notes', 'kind': 'convertible', 'face': 2e9, 'carrying': 2e9, 'coupon': 0.01, 'conv_price': 20.0},
                {'name': 'Senior notes', 'kind': 'notes', 'carrying': 8e9}]
        A = M.analyse(snap, inst, [], price=30.0, sigma_E=0.4, r1=0.04, r5=0.045)
        self.assertEqual(A['convertibles']['in_the_money_face'], 2e9)
        self.assertAlmostEqual(A['convertibles']['dilution'], 0.1)
        self.assertEqual(A['if_converted']['total_debt'], 8e9)
        self.assertLess(A['if_converted']['leverage'], A['leverage'])

    def test_covenant_headroom(self):
        m = {'leverage': 3.0, 'net_leverage': 2.0, 'ebitda_coverage': 6.0, 'liquidity': 5e9, 'total_debt': 1e10}
        ag = [{'title': 'Credit Agreement', 'covenants': [{'type': 'leverage', 'direction': 'max', 'limit': 4.0, 'unit': 'x', 'maintenance': True, 'text': 'Consolidated Leverage Ratio'},
                                                          {'type': 'interest_coverage', 'direction': 'min', 'limit': 3.0, 'unit': 'x', 'maintenance': True, 'text': ''}]}]
        c = {x['type']: x for x in M.covenant_headroom(ag, m, {})}
        self.assertAlmostEqual(c['leverage']['cushion'], 0.25)
        self.assertAlmostEqual(c['interest_coverage']['cushion'], 0.5)


class Banks(unittest.TestCase):
    def test_deposit_cost_from_year_to_date(self):
        fd = {'matched': True, 'holding': 'X', 'subsidiaries': {'1': {'name': 'X Bank', 'rows': [
            {'REPDTE': '20260331', 'DEP': 1000, 'DEPDOM': 1000, 'NTRTIME': 300, 'NTRTMLGJ': 100, 'NTRTMMED': 50, 'EDEPDOM': 5, 'DEPUNA': 400},
            {'REPDTE': '20260630', 'DEP': 1000, 'DEPDOM': 1000, 'NTRTIME': 300, 'NTRTMLGJ': 100, 'NTRTMMED': 50, 'EDEPDOM': 11, 'DEPUNA': 400}]}}}
        b = debt.bank_summary(fd)
        self.assertAlmostEqual(b['latest']['deposit_cost'], 4 * 6 / 1000)
        self.assertAlmostEqual(b['cd_share'], 0.3)
        self.assertEqual(b['latest']['time_small'], 150 * 1000.0)


if __name__ == '__main__':
    unittest.main()
