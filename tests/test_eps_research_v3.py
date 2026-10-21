"""EPS cross-sectional tests: held-out releases, market separation, stable sector output."""
import json
import tempfile
import unittest
from pathlib import Path
from pipeline import eps_research as E


class TestWideEPS(unittest.TestCase):
    def rows(self):
        return {"ticker":"TEST","cik":1000,"sector":"technology",
            "analysts":{"surprises":[
                {"reported":"2025-01-21","quarter":"2024-12-31","eps_est":1,"eps_act":1.1},
                {"reported":"2025-04-21","quarter":"2025-03-31","eps_est":1,"eps_act":1.2},
                {"reported":"2025-07-21","quarter":"2025-06-30","eps_est":1,"eps_act":1.3},
                {"reported":"2025-10-21","quarter":"2025-09-30","eps_est":1,"eps_act":1.4},
            ]}}
    def test_count_first_two_train_only(self):
        z=E.score_company(self.rows())
        self.assertEqual(len(z),2)
        self.assertEqual(z[0]["trained_on"],2)
        self.assertEqual(z[0]["reported"],"2025-07-21")
    def test_past_only_no_future_label_leakage(self):
        doc=self.rows()
        a=E.score_company(doc)[0]
        doc["analysts"]["surprises"][-1]["eps_act"]=10000
        b=E.score_company(doc)[0]
        self.assertEqual(a["prediction"],b["prediction"])
    def test_absence_and_bad_values(self):
        doc={"ticker":"T","analysts":{"surprises":[{"eps_est":None,"eps_act":1,"reported":"2025-01-01"}]}}
        self.assertEqual(E.score_company(doc),[])
        self.assertEqual(E.metrics([])["n"],0)
    def test_robust_scores_retains_untrimmed_and_shared_trim(self):
        rows=[{"model_ae":.1,"baseline_ae":.2,"actual":1,"estimate":1,"prediction":1,"stage":"established"} for _ in range(19)]
        rows.append({"model_ae":1000,"baseline_ae":1000,"actual":1000,"estimate":1000,"prediction":0,"stage":"established"})
        m=E.metrics(rows)
        self.assertGreater(m["mae_model"],40)
        self.assertEqual(m["eps_under_20_cohort"]["n"],19)
        self.assertEqual(m["p95_paired_trimmed"]["n"],19)
        self.assertLess(m["p95_paired_trimmed"]["model_mae"],.2)
    def test_zero_sample_robust_null(self):
        self.assertIsNone(E.metrics([])["mae_model"])
    def test_archived_cross_company_report(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            (d/"c").mkdir()
            (d/"c"/"1000.json").write_text(json.dumps(self.rows()))
            (d/"market.json").write_text(json.dumps({"n":560,"brier":.137441,"brier_base_rate":.176327}))
            r=E.build(d/"c",d/"market.json",d/"result.json")
            self.assertEqual(r["overall"]["n"],2)
            self.assertEqual(r["by_year"]["2025"]["n"],2)
            self.assertEqual(r["resolved_prediction_markets"]["n"],560)
            self.assertEqual(r["status"],"RETROSPECTIVE_ANALYST_VINTAGES_UNVERIFIED")


if __name__=="__main__":unittest.main()
