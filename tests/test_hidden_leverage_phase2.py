"""Offline regression fixtures for Phase-2 source-anchored disclosure screens."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "disclosures" / "app"))
import hidden_leverage_tables as HT
import revenue_quality as RQ


def f(val, end, start=None, acc="0001234567-26-000010", filed="2026-09-15"):
    out = dict(val=val, end=end, form="10-K", filed=filed, accn=acc)
    if start:
        out["start"] = start
    return out


def facts(rows):
    return {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in rows.items()}}}


CURRENT, PREV = "2026-06-30", "2025-06-30"


class HiddenPhase2Tests(unittest.TestCase):
    def parse(self, html):
        return HT.extract_tables(html.encode(), 1234567, "0001234567-26-000010",
                                 "filing.htm", "10-K", "2026-09-15", CURRENT)

    def test_named_uncommenced_lease_annual_usd(self):
        html = """<p>We have entered into leases that have not yet commenced.
          The expected minimum annual lease payments (in millions of U.S. dollars):</p>
          <table><tr><th>Year</th><th>Payments</th></tr>
          <tr><td>2027</td><td>$ 700</td></tr>
          <tr><td>2028</td><td>650</td></tr><tr><td>2029</td><td>500</td></tr>
          <tr><td>Total</td><td>1850</td></tr></table>"""
        rows = self.parse(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "uncommenced_leases")
        self.assertEqual([p["amount_usd"] for p in rows[0]["payments"]],
                         [700e6, 650e6, 500e6])
        self.assertEqual(rows[0]["status"], "table_extracted_needs_review")
        self.assertIsNone(rows[0]["amount_usd"])
        self.assertIn("/000123456726000010/filing.htm", rows[0]["source_url"])

    def test_gpu_year_columns(self):
        html = """<p>GPU capacity commitments for our cloud datacenter
          under minimum purchase contracts (USD in billions)</p>
          <table><tr><th>Minimums</th><th>2027</th><th>2028</th></tr>
          <tr><td>Minimum commitments</td><td>1.2</td><td>1.3</td></tr></table>"""
        rows = self.parse(html)
        self.assertEqual(rows[0]["key"], "capacity")
        self.assertEqual([p["amount_usd"] for p in rows[0]["payments"]], [1.2e9, 1.3e9])

    def test_foreign_currency_not_mislabeled_usd(self):
        html = """<p>Uncommenced leases, EUR in millions:</p><table>
             <tr><td>2027</td><td>200</td></tr>
             <tr><td>2028</td><td>300</td></tr></table>"""
        self.assertEqual(self.parse(html), [])

    def test_no_ambiguous_amounts_or_suppliers_as_debt(self):
        html = """<p>Supplier finance arrangements (USD in millions)</p>
          <table><tr><td>2027</td><td>800</td></tr>
          <tr><td>2028</td><td>900</td></tr></table>"""
        self.assertEqual(self.parse(html), [])
        self.assertEqual(self.parse("<p>Uncommenced leases</p><table><tr><td>2027</td><td>100</td></tr><tr><td>2028</td><td>200</td></tr></table>"), [])

    def test_reported_uncommenced_total_without_payment_schedule(self):
        microsoft = """<p>As of June 30, 2026, we had additional leases,
          primarily for datacenters, that had not yet commenced of
          $329.1 billion, with some arrangements subject to conditions.</p>"""
        found = self.parse(microsoft)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["amount_usd"], 329_100_000_000)
        self.assertEqual(found[0]["payments"], [])
        self.assertEqual(found[0]["status"], "narrative_amount_needs_review")
        oracle = """<p>As of June 30, 2026, we had $260 billion of
          additional lease commitments, substantially all related to data
          center arrangements, that are generally expected to commence
          between fiscal 2027 and fiscal 2029.</p>"""
        self.assertEqual(self.parse(oracle)[0]["amount_usd"], 260_000_000_000)
        self.assertEqual(self.parse(oracle.replace("June 30, 2026", "May 31, 2026")), [])

    def test_dated_supplier_finance_balances_not_nominal_payments(self):
        html = """<p>Supplier finance program, as of June 30, 2026 (USD in millions).</p>
           <table><tr><th>Balance</th><th>2026</th><th>2025</th></tr>
           <tr><td>Confirmed supplier obligations outstanding</td><td>350</td><td>290</td></tr></table>"""
        row = self.parse(html)[0]
        self.assertEqual(row["key"], "supplier_finance")
        self.assertEqual(row["amount_usd"], 350e6)
        self.assertEqual(row["payments"], [])
        self.assertEqual(row["amount_kind"], "reported_supplier_finance_balance")
        self.assertEqual(self.parse(html.replace("June 30, 2026", "December 31, 2025")), [])

    def test_vie_maximum_not_modeled_as_expected_loss(self):
        html = """<p>Variable interest entities support commitment as of June 30, 2026,
           expressed in millions of U.S. dollars.</p>
           <table><tr><th>Exposure</th><th>2026</th><th>2025</th></tr>
           <tr><td>Maximum exposure to loss</td><td>175</td><td>145</td></tr></table>"""
        row = self.parse(html)[0]
        self.assertEqual(row["key"], "vie_support")
        self.assertEqual(row["amount_usd"], 175e6)
        self.assertEqual(row["amount_kind"], "maximum_support_exposure_not_expected_loss")

    def test_no_incorrect_past_year_or_manufactured_single_amount(self):
        html = """<p>Uncommenced leases USD millions</p><table>
         <tr><td>2025</td><td>$ 100</td></tr>
         <tr><td>2027</td><td>$ 200</td></tr></table>"""
        self.assertEqual(self.parse(html), [])


class CookieRevenueTests(unittest.TestCase):
    def test_annual_dsri_and_contract_assets_risks(self):
        data = facts({
            "RevenueFromContractWithCustomerExcludingAssessedTax": [
                f(1000, PREV, "2024-07-01"), f(1100, CURRENT, "2025-07-01")],
            "AccountsReceivableNetCurrent": [f(100, PREV), f(160, CURRENT)],
            "ContractWithCustomerAssetCurrent": [f(30, PREV), f(60, CURRENT)],
            "ContractWithCustomerLiabilityCurrent": [f(200, PREV), f(140, CURRENT)],
            "NetCashProvidedByUsedInOperatingActivities": [
                f(100, PREV, "2024-07-01"), f(40, CURRENT, "2025-07-01")],
            "NetIncomeLoss": [f(80, PREV, "2024-07-01"), f(100, CURRENT, "2025-07-01")],
        })
        r = RQ.extract(data, 1234567, CURRENT)
        self.assertEqual(r["status"], "screened")
        self.assertEqual(r["periods"], [CURRENT, PREV])
        self.assertAlmostEqual(r["metrics"]["dsri"], 1.4545, places=3)
        self.assertEqual({x["key"] for x in r["risk_flags"]},
                         {"dsri", "unbilled_growth", "deferred_release", "cash_conversion"})
        self.assertTrue(r["evidence"]["contract_assets"][0]["source_url"].startswith("https://www.sec.gov/"))

    def test_missing_prior_or_quarterly_facts_never_zero(self):
        a = facts({"RevenueFromContractWithCustomerExcludingAssessedTax": [
            f(250, CURRENT, "2026-04-01"), f(1000, CURRENT, "2025-07-01")]})
        self.assertEqual(RQ.extract(a, 123, CURRENT)["status"], "missing_annual_comparison")
        self.assertEqual(RQ.extract({}, 123, CURRENT)["risk_flags"], [])

    def test_no_mixed_financial_periods(self):
        a = facts({"Revenues": [
            f(100, "2024-06-30", "2023-07-01"),
            f(110, CURRENT, "2025-07-01")]})
        self.assertEqual(RQ.extract(a, 123, CURRENT)["status"], "missing_annual_comparison")

    def test_text_is_lead_not_accusation(self):
        raw = b"<p>Bill-and-hold arrangements and unbilled contract assets. No sales returns.</p>"
        leads = RQ.scan_text(raw, 123, "0001234567-26-000010", "a.htm", "10-K", "2026-09-15")
        keys = {r["key"] for r in leads}
        self.assertIn("bill_and_hold", keys)
        self.assertIn("contract_assets", keys)
        self.assertTrue(all(x["classification"] == "unverified_text_lead" for x in leads))
        self.assertTrue(all("amount_usd" not in x for x in leads))

    def test_old_debt_model_unmodified(self):
        debt = (ROOT / "disclosures/app/debt.py").read_text()
        self.assertIn("'revenue_quality': rec.get('revenue_quality') or {}", debt)
        self.assertIn("'hidden_leverage': rec.get('hidden_leverage') or {}", debt)
        self.assertIn("HLT.extract_tables(", debt)
        self.assertIn("hidden_leverage_version=2", debt)


if __name__ == "__main__":
    unittest.main()
