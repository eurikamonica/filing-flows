"""pipeline/outlook.py: forward-looking statements — what counts, boilerplate left out, topics and tone, what changed
against the earlier document, the guided figures among them, the store and the published files."""
import json
import tempfile
import unittest
from pathlib import Path

from pipeline import outlook as O

MDNA_Q2 = [
    {"text": "Results of Operations", "heading": True},
    {"text": "Revenue increased 12% to $4.1 billion. We expect revenue growth to continue in the second half of 2026, driven by "
             "strong demand for our data center products. We plan to open two new plants in fiscal 2027."},
    {"text": "We expect capital expenditures of approximately $1.2 billion for fiscal 2026. Tariffs could pressure our margins "
             "in the fourth quarter, and we may not be able to pass on the higher costs."},
    {"text": "This report contains forward-looking statements within the meaning of the Private Securities Litigation Reform Act. "
             "Actual results may differ materially from what we expect."},
    {"text": "We do not expect the adoption of ASU 2023-09 to have a material impact on our consolidated financial statements. "
             "We believe our existing cash will be sufficient to fund our operations for at least the next twelve months."},
    {"text": "The expected term of options is 6.1 years and expected volatility is 32%."},
]
MDNA_Q3 = [
    {"text": "We expect revenue growth to continue in the second half of 2026, driven by strong demand for our data center products."},
    {"text": "We now expect capital expenditures of approximately $1.4 billion for fiscal 2026."},
    {"text": "We will reduce our workforce by about 5% and expect restructuring charges of $80 million in the fourth quarter of 2026."},
]


class Statements(unittest.TestCase):
    def test_what_counts(self):
        st = O.statements(MDNA_Q2)
        txt = " ".join(s["t"] for s in st)
        self.assertEqual(len(st), 4)
        self.assertIn("revenue growth to continue", txt)
        self.assertIn("two new plants", txt)
        self.assertNotIn("Revenue increased 12%", txt)                         # a past result
        self.assertNotIn("Private Securities", txt)                            # the safe harbor
        self.assertNotIn("ASU", txt)                                           # an accounting standard
        self.assertNotIn("sufficient to fund", txt)                            # liquidity boilerplate
        self.assertNotIn("volatility", txt)                                    # option-pricing assumptions

    def test_topic_tone_hedge_when(self):
        st = {s["t"][:20]: s for s in O.statements(MDNA_Q2)}
        rev = next(s for k, s in st.items() if k.startswith("We expect revenue"))
        self.assertEqual(rev["topic"], "demand")
        self.assertEqual(rev["tone"], "positive")
        self.assertFalse(rev["hedge"])
        self.assertEqual(rev["when"], "second half of 2026")
        tar = next(s for k, s in st.items() if k.startswith("Tariffs"))
        self.assertEqual(tar["tone"], "negative")
        self.assertTrue(tar["hedge"])
        self.assertEqual(next(s for k, s in st.items() if k.startswith("We plan"))["topic"], "capex")

    def test_compare_and_items(self):
        old, new = O.statements(MDNA_Q2), O.statements(MDNA_Q3)
        dropped = O.compare(new, old)
        status = {s["t"][:25]: s["status"] for s in new}
        self.assertEqual(status["We expect revenue growth "], "repeated")
        self.assertEqual(status["We now expect capital exp"], "updated")      # the same statement, a new figure
        self.assertEqual(status["We will reduce our workfo"], "new")
        self.assertTrue(any("two new plants" in d["t"] for d in dropped))
        items = O.guided_items(new)
        capex = next(i for i in items if i["metric"] == "capex")
        self.assertEqual((capex["lo"], capex["period"]), (1.4e9, "FY2026"))

    def test_supply_and_macro_topics(self):
        st = O.statements(["We will be shipping both Blackwell and Rubin systems in the future and we are currently experiencing certain supply constraints.",
                           "We expect foreign currency exchange rates and higher interest rates to weigh on consumer spending in fiscal 2027."])
        self.assertEqual([x["topic"] for x in st], ["supply", "macro"])

    def test_with_year(self):
        self.assertEqual(O._with_year("FY", "For the year ending December 31, 2026, we expect net income of $9 billion."), "FY2026")
        self.assertEqual(O._with_year("Q4", "in the fourth quarter of 2026"), "Q4 2026")
        self.assertEqual(O._with_year("Q3 FY2027", "anything"), "Q3 FY2027")
        self.assertIsNone(O._with_year("FY", "for the full year"))


class Store(unittest.TestCase):
    def test_keep_and_publish(self):
        with tempfile.TemporaryDirectory() as d:
            a = O.keep(d, 320193, "mdna", "10-Q", "A1", "2026-05-01", "u1", "2026-03-31", MDNA_Q2)
            self.assertEqual(a["counts"]["n"], 4)
            self.assertIsNone(O.keep(d, 320193, "mdna", "10-Q", "A1", "2026-05-01", "u1", "2026-03-31", MDNA_Q2))   # once
            b = O.keep(d, 320193, "mdna", "10-Q", "A2", "2026-08-01", "u2", "2026-06-30", MDNA_Q3)
            self.assertEqual(b["vs"], "A1")
            self.assertEqual(b["counts"]["new"], 1)
            self.assertGreaterEqual(b["counts"]["dropped"], 1)
            r = O.keep(d, 320193, "release", "8-K", "R1", "2026-07-30", "u3", None, MDNA_Q3)
            self.assertNotIn("vs", r)                                           # a release is compared with releases only
            doc = O.load(d, 320193)
            self.assertEqual([x["accn"] for x in doc["docs"]], ["A2", "R1", "A1"])
            out = Path(d) / "pub"
            self.assertEqual(O.publish(d, out), 1)
            ix = json.loads((out / "index.json").read_text())
            self.assertEqual(ix["rows"][0][:4], [320193, "mdna", "10-Q", "2026-08-01"])
            self.assertTrue((out / "320193.json").exists())

    def test_an_older_filing_caught_up_later_is_compared_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            b = O.keep(d, 1, "mdna", "10-Q", "A2", "2026-08-01", "u2", "2026-06-30", MDNA_Q3)    # the latest first (the scan)
            self.assertNotIn("vs", b)
            O.keep(d, 1, "mdna", "10-Q", "A1", "2026-05-01", "u1", "2026-03-31", MDNA_Q2)          # then the one before (catch-up)
            doc = O.load(d, 1)
            a2 = next(x for x in doc["docs"] if x["accn"] == "A2")
            self.assertEqual(a2["vs"], "A1")
            self.assertEqual(a2["counts"]["new"], 1)
            self.assertTrue(any("two new plants" in x["t"] for x in a2["dropped"]))
            self.assertEqual({x["t"][:25]: x["status"] for x in a2["statements"]}["We now expect capital exp"], "updated")
            self.assertTrue(all(x.get("status") == "first" for x in next(x for x in doc["docs"] if x["accn"] == "A1")["statements"]))


FLS_OLD = ("Forward-looking statements reflect management’s current expectations and are inherently uncertain. Actual results and "
           "outcomes could differ materially for a variety of reasons, including, among others, fluctuations in foreign exchange rates, "
           "changes in global economic conditions and customer demand and spending, inflation, interest rates, regional labor market "
           "constraints, world events, the outcomes of claims, litigation, government investigations, and other proceedings, fulfillment, "
           "sortation, delivery, and data center optimization, risks of inventory management, and payments risks. These risks are described "
           "in greater detail in Item 1A of Part II, “Risk Factors.”")
FLS_NEW = ("Forward-looking statements reflect management’s current expectations and are inherently uncertain. Actual results and "
           "outcomes could differ materially for a variety of reasons, including, among others, fluctuations in foreign exchange rates and "
           "energy prices, changes in global economic conditions, tariff and trade policies, resource and supply volatility, including for "
           "memory chips, and customer demand and spending, inflation, interest rates, regional labor market constraints, world events, the "
           "outcomes of claims, litigation, government investigations, and other proceedings, fulfillment, sortation, delivery, and data "
           "center optimization, risks of inventory management, the degree to which we enter into, maintain, and develop commercial "
           "agreements, and risks of fulfillment throughput and productivity. These risks are described in greater detail in Item 1A of "
           "Part II, “Risk Factors.”")
CAE = [
    {"text": "Critical Accounting Estimates", "heading": True},
    {"text": "Our financial statements are prepared in accordance with U.S. GAAP, which requires estimates.", "heading": False},
    {"text": "Inventories", "heading": True},
    {"text": "We charge cost of sales for inventory provisions to write down inventory to the lower of cost or net realizable value. "
             "The net effect on our gross margin from inventory provisions was an unfavorable impact of 2.6% in fiscal year 2026.", "heading": False},
    {"text": "Income Taxes", "heading": True},
    {"text": "We are subject to income taxes in the U.S. and foreign jurisdictions. A 1% change in our effective tax rate would have "
             "changed our income tax expense by approximately $85 million.", "heading": False},
    {"text": "Revenue Recognition", "heading": True},
    {"text": "Revenue Allowances", "heading": True},
    {"text": "For products sold with a right of return, we record a reduction to revenue for estimated returns.", "heading": False},
    {"text": "Recent Accounting Pronouncements", "heading": True},
    {"text": "We do not expect ASU 2023-09 to have a material impact.", "heading": False},
]


class Risks(unittest.TestCase):
    def test_the_list_split_into_items_and_pinned_to_lines(self):
        rs = O.risks([{"text": "Forward-Looking Statements", "heading": True}, {"text": FLS_NEW, "heading": False}])
        t = {r["t"]: r["lines"] for r in rs}
        self.assertIn("resource and supply volatility, including for memory chips", t)
        self.assertEqual(t["resource and supply volatility, including for memory chips"], ["cor", "capex"])
        self.assertIn("the outcomes of claims, litigation, government investigations, and other proceedings", t)
        self.assertIn("fulfillment, sortation, delivery, and data center optimization", t)
        self.assertIn("the degree to which we enter into, maintain, and develop commercial agreements", t)
        self.assertEqual(t["interest rates"], ["interest"])
        self.assertIn("cor", t["fluctuations in foreign exchange rates and energy prices"])     # the energy prices part
        self.assertIn("revenue", t["fluctuations in foreign exchange rates and energy prices"])
        self.assertEqual(t["risks of inventory management"][0], "k~Inventor")
        self.assertFalse(any("Risk Factors" in r["t"] for r in rs))

    def test_added_and_dropped_against_the_filing_before(self):
        with tempfile.TemporaryDirectory() as d:
            O.keep(d, 1018724, "mdna", "10-Q", "Q2", "2026-07-31", "u1", "2026-06-30", MDNA_Q2 + [{"text": FLS_OLD, "heading": False}])
            O.keep(d, 1018724, "mdna", "10-Q", "Q3", "2026-10-30", "u2", "2026-09-30", MDNA_Q3 + [{"text": FLS_NEW, "heading": False}])
            doc = O.load(d, 1018724)
            q3 = next(x for x in doc["docs"] if x["accn"] == "Q3")
            st = {r["t"]: r["status"] for r in q3["risks"]}
            self.assertEqual(st["tariff and trade policies"], "new")
            self.assertEqual(st["resource and supply volatility, including for memory chips"], "new")
            self.assertEqual(st["inflation"], "repeated")
            self.assertTrue(any(x["t"] == "payments risks" for x in q3["risks_dropped"]))
            q2 = next(x for x in doc["docs"] if x["accn"] == "Q2")
            self.assertTrue(all(r["status"] == "first" for r in q2["risks"]))


class Estimates(unittest.TestCase):
    def test_critical_accounting_estimates(self):
        es = O.estimates(CAE)
        names = [e["name"] for e in es]
        self.assertEqual(names, ["Inventories", "Income Taxes", "Revenue Recognition — Revenue Allowances"])
        tax = es[1]
        self.assertEqual(tax["lines"], ["tax"])
        self.assertEqual(tax["sens"][0]["pct"], 1.0)
        self.assertAlmostEqual(tax["sens"][0]["usd"], 85e6)
        self.assertIn("effective tax rate", tax["sens"][0]["of"])
        self.assertIn("2.6%", es[0]["effect"])
        self.assertEqual(es[0]["lines"][:2], ["k~Inventor", "cor"])
        self.assertEqual(es[2]["lines"], ["revenue"])

    def test_a_quarterly_report_pointing_to_the_annual_one(self):
        es = O.estimates([{"text": "Critical Accounting Estimates", "heading": True},
                          {"text": "There have been no material changes to our critical accounting estimates as described in our 2025 Annual Report on Form 10-K.", "heading": False},
                          {"text": "Liquidity and Capital Resources", "heading": True}])
        self.assertEqual(len(es), 1)
        self.assertTrue(es[0]["ref"])


if __name__ == "__main__":
    unittest.main()
