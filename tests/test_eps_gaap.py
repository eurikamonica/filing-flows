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
        self.assertEqual(b["status"],"FIRST_FILED_SEC_GAAP_RETROSPECTIVE_WALK_FORWARD")
    def test_no_insufficient_intervals_claim(self):
        x=self.synthetic()[:8]
        f=E.model(x,"2024-01-01")
        self.assertIsNotNone(f)
        self.assertIsNone(f["uncertainty"]["p10"])
    def test_missing_quarter_refused(self):
        x=self.synthetic()
        del x[16]
        self.assertIsNone(E.model(x,"2026-12-31"))

if __name__=="__main__":
    unittest.main()
