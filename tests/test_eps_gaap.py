"""Offline SEC GAAP EPS PIT backtest invariants."""
import datetime as dt
import unittest
from pipeline import eps_gaap as E

class TestEPSGAAP(unittest.TestCase):
    def test_earliest_filing_wins_over_restatement(self):
        facts={"cik":320193,"facts":{"us-gaap":{"EarningsPerShareDiluted":{"units":{"USD/shares":[
          {"start":"2024-01-01","end":"2024-03-31","filed":"2024-05-01","val":1.10,"form":"10-Q","accn":"A"},
          {"start":"2024-01-01","end":"2024-03-31","filed":"2025-05-01","val":1.40,"form":"10-Q","accn":"B"},
          {"start":"2024-01-01","end":"2024-12-31","filed":"2025-03-01","val":4.80,"form":"10-K","accn":"C"},
        ]}}}}}
        x=E.direct_eps(facts)
        self.assertEqual(len(x),1)
        self.assertEqual(x[0]["eps"],1.10)
    def synthetic(self):
        end=dt.date(2021,3,31);rows=[]
        for i in range(24):
            # Real calendar quarter ends, stable 90-day changes.
            yy=2021+i//4;q=i%4
            ends=[dt.date(yy,3,31),dt.date(yy,6,30),dt.date(yy,9,30),dt.date(yy,12,31)]
            e=ends[q];f=e+dt.timedelta(days=35)
            rows.append({"end":e.isoformat(),"filed":f.isoformat(),"eps":1+.07*i+(q*.17)})
        return rows
    def test_prediction_uses_prior_public_only(self):
        x=self.synthetic()
        cutoff=(E.iso(x[16]["filed"])+dt.timedelta(days=1)).isoformat()
        orig=E.model(x,cutoff)
        self.assertIsNotNone(orig)
        leaked=[dict(y) for y in x]
        for j in range(17,len(leaked)):leaked[j]["eps"]=9000
        self.assertEqual(E.model(leaked,cutoff),orig,"future released EPS leaked into training")
    def test_walk_forward_target_year(self):
        x=self.synthetic()
        b=E.backtest(x,2025)
        self.assertEqual(b["n"],4)
        self.assertTrue(b["model_mae"] >= 0)
        self.assertEqual(b["status"],"FIRST_FILED_SEC_GAAP_WALK_FORWARD_Q4_DERIVED_FROM_10K")
        self.assertIn("rel_error_model",b)
        self.assertIn(E.gate(b)["status"],("PASSED","TOO_FEW_TESTS","YEAR_AGO_BETTER"))
    def test_no_insufficient_intervals_claim(self):
        x=self.synthetic()[:8]
        f=E.model(x,"2023-02-15")
        self.assertIsNotNone(f)
        self.assertIsNone(f["uncertainty"]["p10"])
    def test_missing_q4_does_not_invalidate_other_quarters(self):
        x=[r for r in self.synthetic() if E.iso(r["end"]).month!=12]
        f=E.model(x,"2025-01-01",target_end="2025-03-31")
        self.assertIsNotNone(f)
        self.assertEqual(f["target_end"],"2025-03-31")
    def test_missing_seasonal_comparator_refused(self):
        x=[r for r in self.synthetic() if E.iso(r["end"]).month!=12]
        self.assertIsNone(E.model(x,"2025-01-01",target_end="2024-12-31"))

if __name__=="__main__":
    unittest.main()


def test_fourth_quarter_derived_and_bad_eps_dropped():
    """Q4 = the 10-K year less the nine months; an EPS figure that disagrees with net income / shares is dropped."""
    def f(start, end, filed, val, form):
        return {"start": start, "end": end, "filed": filed, "val": val, "form": form, "accn": filed}
    eps = [f("2025-01-01", "2025-03-31", "2025-05-01", 1.0, "10-Q"), f("2025-04-01", "2025-06-30", "2025-08-01", 1.1, "10-Q"),
           f("2025-07-01", "2025-09-30", "2025-11-01", 650000.0, "10-Q"),          # a scale error in the filing
           f("2025-01-01", "2025-09-30", "2025-11-01", 3.3, "10-Q"), f("2025-01-01", "2025-12-31", "2026-02-20", 4.6, "10-K")]
    ni = [f(x["start"], x["end"], x["filed"], v, x["form"]) for x, v in zip(eps, (1e9, 1.1e9, 1.2e9, 3.3e9, 4.6e9))]
    sh = [f(x["start"], x["end"], x["filed"], 1e9, x["form"]) for x in eps]
    facts = {"cik": 1, "facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": eps}},
                                             "NetIncomeLoss": {"units": {"USD": ni}},
                                             "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": sh}}}}}
    recs = {r["end"]: r for r in E.direct_eps(facts)}
    assert "2025-09-30" not in recs                                  # 650,000 per share is not kept
    q4 = recs["2025-12-31"]
    assert q4.get("derived") and abs(q4["eps"] - 1.3) < 1e-9 and q4["filed"] == "2026-02-20"
