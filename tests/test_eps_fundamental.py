"""Release-time, fundamental EPS arithmetic, event and probability guard tests."""
import datetime as dt
import unittest
from pipeline import eps_fundamental as F


def fixture():
    tags={"revenue":"RevenueFromContractWithCustomerExcludingAssessedTax",
          "operating_income":"OperatingIncomeLoss",
          "pretax_income":"IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "tax_expense":"IncomeTaxExpenseBenefit","net_income":"NetIncomeLoss",
          "diluted_shares":"WeightedAverageNumberOfDilutedSharesOutstanding",
          "eps":"EarningsPerShareDiluted"}
    data={tag:{"units":{F.UNITS[field]:[]}} for field,tag in tags.items()}
    for yr in range(2020,2027):
        for q in range(1,5):
            end=[dt.date(yr,3,31),dt.date(yr,6,30),
                 dt.date(yr,9,30),dt.date(yr,12,31)][q-1]
            if end>dt.date(2026,6,30):continue
            start=[dt.date(yr,1,1),dt.date(yr,4,1),
                   dt.date(yr,7,1),dt.date(yr,10,1)][q-1]
            filed=end+dt.timedelta(days=35)
            sales=30e9*(1.09**(yr-2020))*(1+.025*q)
            op=sales*.34
            pretax=op+.4e9
            tx=12e9 if (yr==2025 and q==3) else pretax*.22
            ni=pretax-tx
            shares=2e9
            values={"revenue":sales,"operating_income":op,"pretax_income":pretax,
                    "tax_expense":tx,"net_income":ni,"diluted_shares":shares,"eps":ni/shares}
            for field,tag in tags.items():
                data[tag]["units"][F.UNITS[field]].append({
                    "start":start.isoformat(),"end":end.isoformat(),
                    "filed":filed.isoformat(),"val":values[field],
                    "accn":f"orig-{yr}-{q}","form":"10-Q"})
    return {"cik":1326801,"facts":{"us-gaap":data}}


class TestFundamental(unittest.TestCase):
    def setUp(self):
        self.facts=fixture()
        self.series=F.quarterly(self.facts)

    def test_extraction_is_first_filing_and_direct_quarters(self):
        self.assertGreater(len(self.series),20)
        tag=self.facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
        tag.append({**tag[-1],"filed":"2026-12-15","val":900e9,"accn":"amended"})
        obj=F.quarterly(self.facts)
        self.assertLess(obj[-1]["fields"]["net_income"]["val"],100e9)

    def test_no_future_revenue_or_eps_at_cutoff(self):
        date="2026-08-15"
        first=F.forecast(self.series,date,target="2026-09-30")
        self.assertIsNotNone(first)
        changed=F.quarterly(self.facts)
        for row in changed:
            if row["end"]>"2026-06-30":
                row["fields"]["revenue"]["val"]=1e15
        second=F.forecast(changed,date,target="2026-09-30")
        self.assertEqual(first,second)

    def test_event_normalization_and_explicit_source(self):
        date="2026-08-15"
        doc=F.forecast(self.series,date,target="2026-09-30")
        self.assertIsNotNone(doc)
        self.assertGreater(doc["normalized_eps_last_year"],doc["eps_gaap_last_year"])
        self.assertGreater(doc["inputs"]["normalized_tax_rate"],0.1)
        self.assertLess(doc["inputs"]["normalized_tax_rate"],0.4)
        with_event=F.forecast(self.series,date,target="2026-09-30",events=[
            {"target_end":"2026-09-30","published_at":"2026-08-10","source_url":"https://www.sec.gov/a","eps_delta":-.2},
            {"target_end":"2026-09-30","published_at":"2026-11-02","source_url":"https://www.sec.gov/b","eps_delta":-99},
            {"target_end":"2026-09-30","published_at":"2026-08-10","source_url":"unknown","eps_delta":-99}])
        self.assertAlmostEqual(with_event["point"],doc["point"]-.2,delta=.0002)
        self.assertEqual(len(with_event["confirmed_events"]),1)

    def test_probability_and_named_scenarios(self):
        doc=F.forecast(self.series,"2026-08-15",target="2026-09-30",allow_dist=True)
        self.assertEqual(doc["scenarios"]["status"],"HISTORICAL_DRIVER_STRESS_NOT_PROBABILITY_QUANTILES")
        self.assertGreater(doc["scenarios"]["bull"]["eps"],doc["scenarios"]["bear"]["eps"])
        self.assertFalse(doc["distribution"].get("coverage_claim",False))
        self.assertEqual(F.probability(2,1,[])["status"],"INSUFFICIENT_PRIOR_WALKFORWARD_RESIDUALS")
        self.assertEqual(F.probability(2,1,[.1]*10)["status"],"EMPIRICAL_UNCALIBRATED")

    def test_future_comparable_quarter_is_not_mislabeled_as_next(self):
        # As-of mid-Q4 when last published XBRL is Q3, absent direct Q4
        # means N/A; never leap over Q4 into next year's Q1.
        rows=[r for r in self.series if r["end"][-5:]!="-12-31"]
        self.assertIsNone(F.forecast(rows,"2026-11-15"))

    def test_historical_walk_forward_does_not_use_post_cutoff_facts(self):
        a=F.backtest(self.series,years=(2025,2026))
        self.assertGreater(a["n"],0)
        for r in a["rows"]:
            self.assertLess(r["cutoff"],r["filed"])
        self.assertIsNotNone(a["mae_seasonal"])

    def test_wrong_units_are_not_silently_validated(self):
        old=len(F.observations(self.series,"2026-08-15"))
        changed=F.quarterly(self.facts)
        changed[-2]["fields"]["diluted_shares"]["val"]=2e6
        self.assertLess(len(F.observations(changed,"2026-08-15")),old)

if __name__=="__main__":
    unittest.main()
