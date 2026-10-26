"""No external quote/SEC request; prove 5-minute calculations and feed provenance."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from scripts import flo_momentum as M

NOW=datetime(2026,10,26,14,50,tzinfo=timezone.utc)  # 10:50 NY

def candle(m,close,volume=10000):
    t=NOW-timedelta(minutes=m)
    return {"t":M.stamp(t),"c":close,"v":volume,"h":close,"l":close,"o":close}
def quotes(price=105, volume=10000):
    # Last closed minute at 14:49Z; previous at 14:44Z = exact 5min.
    rows=[candle(i,100+(6-i)) for i in range(1,8)]
    rows[0]["c"]=price
    return rows

class MomentumTests(unittest.TestCase):
    def test_exact_five_minutes(self):
        result=M.calculate({"AAPL":quotes()},NOW)
        self.assertIn("AAPL",result)
        item=result["AAPL"]
        # 14:49 close 105, 14:44 close 100 -> +5%
        self.assertAlmostEqual(item["five_min_pct"],5.0)
        self.assertEqual(item["asof"],M.stamp(NOW-timedelta(minutes=1)))
        self.assertEqual(item["prev_asof"],M.stamp(NOW-timedelta(minutes=6)))
        self.assertTrue(item["volume_complete"])
        self.assertEqual(item["volume_5m"],50000)

    def test_missing_start_or_stale_rejected(self):
        rows=quotes()
        self.assertNotIn("NVDA", M.calculate({"NVDA": [b for b in rows if b["t"] != M.stamp(NOW-timedelta(minutes=6))]}, NOW))
        self.assertNotIn("NVDA",M.calculate({"NVDA":rows},NOW+timedelta(minutes=30)))
        self.assertNotIn("NVDA",M.calculate({"NVDA":[{**r,"c":-1} for r in rows]},NOW))
        self.assertNotIn("NVDA",M.calculate({"NVDA":[{**r,"t":"bogus"} for r in rows]},NOW))
        with self.assertRaises(ValueError):
            M.calculate({"NVDA":rows},NOW,feed="nonsense")

    def test_incomplete_volume_not_claimed_complete(self):
        rows=[r for r in quotes() if r["t"] != M.stamp(NOW-timedelta(minutes=4))]
        x=M.calculate({"NVDA":rows},NOW)["NVDA"]
        self.assertAlmostEqual(x["five_min_pct"],5)
        self.assertFalse(x["volume_complete"])
        self.assertEqual(x["volume_5m"],40000)

    def test_no_premarket_fake_regular(self):
        early=datetime(2026,10,26,12,0,tzinfo=timezone.utc)
        rows=[{"t":M.stamp(early-timedelta(minutes=i)),"c":100+i,"v":100} for i in range(7)]
        self.assertEqual(M.calculate({"AAPL":rows},early),{})

    def test_sp500_current_parser_rejects_incomplete(self):
        html='<table id="constituents"><tr><th>Symbol</th></tr>'+''.join(
            '<tr><td>T'+str(i)+'</td><td>Name</td></tr>' for i in range(500))+'</table>'
        x=M.sp500_from_wikipedia(NOW,fetch=lambda url:html)
        self.assertEqual(len(x["symbols"]),500)
        self.assertEqual(x["as_of"],"2026-10-26")
        with self.assertRaises(ValueError):
            M.sp500_from_wikipedia(NOW,fetch=lambda url:'<table>No members</table>')

    def test_constituents_must_be_dated_and_complete(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"russell1000.json"
            p.write_text(json.dumps({"as_of":"2026-10-01","source":"Contracted index vendor",
                                     "symbols":["T"+str(i) for i in range(1000)]}))
            a=M.curated_universe(p,NOW)
            self.assertEqual(len(a["symbols"]),1000)
            self.assertIsNone(M.curated_universe(p,NOW+timedelta(days=150)))
            p.write_text(json.dumps({"as_of":"2026-10-01","source":"","symbols":["AAPL"]*1000}))
            self.assertIsNone(M.curated_universe(p,NOW))
            self.assertIsNone(M.curated_universe(Path(d)/"russell2000.json",NOW))

    def test_market_coverage_and_relay(self):
        defs={"sp500":{"symbols":["AAA","BBB","CCC"],"as_of":"2026-10-26",
                       "source":"fixture","status":"current_snapshot_unofficial"},
              "russell1000":{"symbols":[],"as_of":None,"source":"","status":"unavailable"},
              "russell2000":{"symbols":[],"as_of":None,"source":"","status":"unavailable"}}
        moves={t:{"ticker":t,"five_min_pct":pct,"turnover_5m_usd":1000,
                  "price":100,"volume_5m":100,"volume_complete":True,
                  "prev_asof":M.stamp(NOW-timedelta(minutes=6)),"asof":M.stamp(NOW-timedelta(minutes=1))}
               for t,pct in [("AAA",3),("BBB",8)]}
        first=M.rank_universes(defs,moves,{},NOW,"iex")
        self.assertEqual(first["sp500"]["leaders"][0]["ticker"],"BBB")
        self.assertEqual(first["sp500"]["ranking_status"],"partial")
        self.assertEqual(first["sp500"]["coverage_pct"],66.7)
        prior={"generated_at":M.stamp(NOW-timedelta(minutes=5)),"feed":"iex","universes":first}
        second=M.rank_universes(defs,moves,prior,NOW,"iex")
        self.assertEqual(second["sp500"]["leaders"][0]["streak"],2)
        self.assertFalse(second["sp500"]["leaders"][0]["new_entry"])
        third=M.rank_universes(defs,moves,prior,NOW,"sip")
        self.assertEqual(third["sp500"]["leaders"][0]["streak"],1)
        self.assertEqual(third["russell2000"]["ranking_status"],"unavailable")

    def test_alpaca_pagination_and_feed_handling(self):
        count=[0]
        def fake_fetch(url, headers):
            count[0]+=1
            self.assertIn("timeframe=1Min",url)
            self.assertIn("feed=iex",url)
            if count[0]==1:return {"bars":{"NVDA":quotes()},"next_page_token":"next"}
            self.assertIn("page_token=next",url)
            return {"bars":{"NVDA":[]},"next_page_token":None}
        data=M.alpaca_bars(["NVDA"],NOW,"iex","KEY","SECRET",fake_fetch)
        self.assertEqual(len(data["NVDA"]),7)
        self.assertEqual(count[0],2)
        with self.assertRaises(ValueError):
            M.alpaca_bars(["NVDA"],NOW,"sip","","",fake_fetch)

    def test_supabase_guarded_publication(self):
        calls=[]
        def fake_fetch(url,headers,body=None):
            calls.append((url,headers,body))
            return {}
        payload={"generated_at":M.stamp(NOW),"schema":1}
        M.publish("https://example.supabase.co","SECRET",payload,False,fake_fetch)
        self.assertFalse(json.loads(calls[-1][2])["is_public"])
        self.assertNotIn("SECRET",calls[-1][2].decode())
        self.assertIn("on_conflict=name",calls[-1][0])
        self.assertEqual(M.read_previous("https://example.supabase.co","SECRET",
           lambda url,headers:[{"payload":{"feed":"iex"}}]),{"feed":"iex"})

if __name__=="__main__":
    unittest.main()
