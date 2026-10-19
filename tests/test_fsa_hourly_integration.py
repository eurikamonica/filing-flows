"""CPU smoke tests for optional hourly training-pack and reviewed teacher data."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import fsa_lab_action
import fsa_distill_review


class HourlyTrainingIntegration(unittest.TestCase):
    def test_only_approved_hourly_rows_enter_train_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);hour=root/"hourly"/"2026-10-18"
            hour.mkdir(parents=True)
            examples=[
                {"id":"s","task":"journal_entry","input":"Q synthetic","output":'{"a":1}',
                 "training_eligible":True,"review_status":"synthetic_verified","source":{"kind":"synthetic"}},
                {"id":"bad-sec","task":"sec_revenue_growth","input":"Q SEC","output":'{"a":2}',
                 "training_eligible":True,"review_status":"needs_review","source":{"kind":"sec"}},
                {"id":"r","task":"research_fact","input":"Q research","output":'{"a":3}',
                 "training_eligible":True,"review_status":"human_verified_report_fact",
                 "source":{"kind":"research","rights":"licensed_for_training"}},
                {"id":"bad-rights","task":"research_fact","input":"Q bad","output":'{"a":4}',
                 "training_eligible":True,"review_status":"human_verified_report_fact",
                 "source":{"kind":"research","rights":"unknown"}}
            ]
            (hour/"17.json").write_text(json.dumps({"questions":examples}))
            train=fsa_lab_action.read_approved_hourly(root,100)
            self.assertEqual({x["input"] for x in train},{"Q synthetic","Q research"})
            self.assertEqual(len(fsa_lab_action.read_approved_hourly(root,1)),1)

    def test_teacher_output_needs_independent_gold_and_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);candidates=p/"proposals.jsonl";out=p/"approved.jsonl"
            records=[
                {"input":"Evidence=1+2; value?","task":"arithmetic","independent_gold":{"value":3},
                 "teacher_answer":{"value":3},"copyright_training_permission":True,
                 "review":{"human_verified":True,"reviewer":"QA1","source_checked":True}},
                {"input":"Evidence=4+4; value?","independent_gold":{"value":8},
                 "teacher_answer":{"value":9},"copyright_training_permission":True,
                 "review":{"human_verified":True,"reviewer":"QA1","source_checked":True}},
                {"input":"Evidence=2+5; value?","independent_gold":{"value":7},
                 "teacher_answer":{"value":7},"copyright_training_permission":True,
                 "review":{"human_verified":False,"reviewer":"QA1","source_checked":True}}
            ]
            candidates.write_text("\n".join(json.dumps(x) for x in records)+"\n")
            report=fsa_distill_review.review(candidates,out)
            self.assertEqual(report["accepted"],1)
            self.assertEqual(sum(report["rejected"].values()),2)
            self.assertEqual(json.loads(out.read_text().splitlines()[0])["split"],"train")

    def test_x_posts_from_the_local_model_corpus_join_the_pack_with_replay(self):
        import gzip
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lab=root/"lab";corpus=root/"corpus.jsonl.gz"
            head="Write one factual post for X from the facts below. Use only numbers that appear in the facts.\n\n"
            def ex(i,kind,hold,facts,post,cik=None):
                return {"id":f"x{i}","kind":kind,"hold":hold,"cik":cik,"prompt":head+"FORMAT: "+kind+"\n\n"+facts,
                        "target":post,"cashtags":[hold] if hold else ["AAPL"]}
            xs=[ex(1,"drawdown","CRWV","- $CRWV high $140, now $61","Remember the highs?\n\n$CRWV $140 → $61\n\nWhich one gets back there first?"),
                ex(2,"polymarket","META","- $META reports 2026-10-21: 64%","$META Oct 21: 64%. Too high? #Polymarket"),
                ex(3,"setup","MCD","- Down 20% YTD","$MCD going into Tuesday\n\n• Down roughly 20% YTD\n\nWhat's your read?"),   # held out
                ex(4,"versus","AAPL","- "+"x"*1200,"$AAPL or $META what stock would you rather have?"),                    # too long
                ex(5,"versus","PEP","- $PEP +5% this year","$PEP or $KO? Pick one."),
                ex(6,"versus","PEP","- $PEP +5% this year","$PEP or $KO? Pick one.")]                                          # duplicate
            with gzip.open(corpus,"wt",encoding="utf-8") as f:
                f.write("\n".join(json.dumps(x) for x in xs)+"\n")
            got=fsa_lab_action.read_x_posts(corpus,50)
            self.assertEqual(sorted(json.loads(r["output"])["post"][:8] for r in got),["$META Oc","$PEP or ","Remember"])
            for r in got:
                self.assertTrue(r["input"].startswith(fsa_lab_action.POST_INSTRUCTION+"\n\nFORMAT: "))
                self.assertTrue(r["task"].startswith("x_post:") and isinstance(json.loads(r["output"]),dict))
            self.assertIn("\n$CRWV $140 → $61\n",next(json.loads(r["output"])["post"] for r in got if r["task"]=="x_post:drawdown"))
            self.assertEqual(fsa_lab_action.read_x_posts(corpus,0),[])
            # the training pack: posts count as new rows, so the historical replay share stays at 30% or more
            P=fsa_lab_action.required_sources(lab)
            def put(path,items):
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text("\n".join(json.dumps(x) for x in items)+"\n")
            row=lambda i,src,task="bs":{"task":task,"split":"train","input":f"{src} q{i}","output":json.dumps({"v":i})}
            put(P["bfv4_train"],[row(i,"bf") for i in range(40)]);put(P["replay"],[row(i,"rp") for i in range(60)])
            put(P["owner_train"],[row(i,"ow","bs_line_classification") for i in range(5)])
            for k in ("bfv4_dev","bfv4_protocol","owner_protocol","bfv3_protocol"):put(P[k],[row(0,"dev-"+k)])
            P["gate2_protocol"].parent.mkdir(parents=True,exist_ok=True);P["gate2_protocol"].write_text(json.dumps({"validation":[]}))
            m=fsa_lab_action.assemble(lab,root/"out","finance_v4",7,10,5,0,posts_corpus=corpus,posts_count=3)
            self.assertEqual(m["counts"].get("x_posts"),3)
            self.assertGreaterEqual(m["counts"]["historical_replay"]/sum(m["counts"].values()),0.3)
            self.assertEqual(m["tasks"].get("x_post:versus"),1)


if __name__=="__main__":unittest.main()
