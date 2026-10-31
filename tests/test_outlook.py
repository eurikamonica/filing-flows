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


if __name__ == "__main__":
    unittest.main()
