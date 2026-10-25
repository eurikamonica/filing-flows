"""Offline/fixture tests; no SEC requests and no market-data assumptions."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "disclosures" / "app"))
import hidden_leverage as HL


def fact(value, accession="0001000000-26-000005", end="2026-06-30", form="10-Q",
         filed="2026-08-01", start=None):
    f = {"val": value, "end": end, "filed": filed, "form": form, "accn": accession}
    if start:
        f["start"] = start
    return f


def companyfacts(tagged):
    return {"facts": {"us-gaap": {
        tag: {"units": {"USD": rows}} for tag, rows in tagged.items()
    }}}


class HiddenLeverageTests(unittest.TestCase):
    def test_same_date_only_and_missing_is_not_zero(self):
        cf = companyfacts({
            "PurchaseObligation": [fact(1_500_000_000, end="2025-12-31"),
                                   fact(2_250_000_000)],
            "GuaranteesMaximumPotentialAmountOfFuturePayments": [
                fact(45_000_000, end="2024-12-31")]
        })
        out = HL.extract(cf, "1234", "2026-06-30")
        self.assertEqual(len(out["categories"]), 1)
        self.assertEqual(out["categories"][0]["amount_usd"], 2_250_000_000)
        self.assertIsNone(HL.summarize(out)["guarantees"])
        self.assertEqual(out["coverage"], "numeric_evidence")

    def test_no_duration_units_or_unvalidated_facts(self):
        cf = companyfacts({"PurchaseObligation": [
            fact(700, start="2026-01-01"),  # cannot treat duration as instant
            fact(800, form="8-K"),           # no periodic source
            fact(-3),                       # reject negative/invalid
        ]})
        out = HL.extract(cf, 2, "2026-06-30")
        self.assertEqual(out["categories"], [])
        self.assertEqual(out["coverage"], "no_standard_tag_at_period")

    def test_maturity_kept_separate_no_double_count(self):
        cf = companyfacts({
            "PurchaseObligation": [fact(5_000)],
            "PurchaseObligationDueInNextTwelveMonths": [fact(1_000)],
            "PurchaseObligationDueInSecondYear": [fact(900)],
            "OperatingLeaseLiability": [fact(3_000)],
            "OperatingLeaseLiabilityPaymentsDue": [fact(4_000)],
        })
        out = HL.extract(cf, 4, "2026-06-30")
        rows = {x["key"]: x for x in out["categories"]}
        self.assertEqual(rows["purchase_broad"]["schedule"][:2], [1_000,900])
        self.assertEqual(rows["purchase_broad"]["amount_usd"], 5_000)
        self.assertEqual(rows["operating_lease"]["amount_usd"], 3_000)
        self.assertEqual(rows["lease_payments"]["amount_usd"], 4_000)
        self.assertFalse("hidden_debt_total" in out)
        self.assertTrue(rows["purchase_broad"]["source_url"].startswith("https://www.sec.gov/"))

    def test_maturity_without_total_is_not_fabricated(self):
        cf = companyfacts({"PurchaseObligationDueInNextTwelveMonths": [fact(4000)]})
        out = HL.extract(cf, 42, "2026-06-30")
        self.assertEqual(out["categories"][0]["amount_usd"], None)
        self.assertEqual(out["categories"][0]["schedule"][0], 4000)

    def test_newer_amendment_wins_at_same_date(self):
        cf = companyfacts({"PurchaseObligation": [
            fact(500, filed="2026-08-01"),
            fact(550, accession="0001000000-26-000006", filed="2026-09-12", form="10-Q/A")
        ]})
        out = HL.extract(cf, 1, "2026-06-30")
        self.assertEqual(out["categories"][0]["amount_usd"], 550)
        self.assertIn("000100000026000006", out["categories"][0]["source_url"])

    def test_text_signals_are_unverified_and_do_not_create_amounts(self):
        raw = (b"<html><body><div>We use certain take-or-pay contracts. "
               b"No variable interest entities existed. "
               b"Supplier finance programs are described in the notes.</div></body></html>")
        signals = HL.scan_filing_text(raw, 123, "0001000000-26-000005",
                                      "2026-10k.htm", "10-K", "2026-08-15")
        self.assertEqual({x["key"] for x in signals},
                         {"take_or_pay", "vie", "supplier_finance"})
        self.assertTrue(all(x["classification"] == "unverified_text_lead" for x in signals))
        self.assertFalse(any("amount_usd" in x for x in signals))

    def test_bogus_accession_cannot_create_fake_url(self):
        self.assertIsNone(HL.sec_url(123, "fake-accession"))

    def test_navigation_and_pipeline_are_wired(self):
        hub = (ROOT / "disclosures/docs/index.html").read_text()
        pipeline = (ROOT / "disclosures/app/debt.py").read_text()
        assert 'data-tab="hidden"' in hub
        assert 'src="hidden-leverage.js"' in hub
        assert "HL.extract(cf, cik" in pipeline
        assert "hidden' / 'index.json'" in pipeline


if __name__ == "__main__":
    unittest.main()
