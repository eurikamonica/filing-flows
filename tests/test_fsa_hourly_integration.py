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


if __name__=="__main__":unittest.main()
