#!/usr/bin/env python3
"""Stage independently reviewed teacher outputs for an optional future SFT run.

Never calls a paid model or accepts unverified teacher-generated finance facts.
"""
import argparse,hashlib,json,math
from pathlib import Path
from collections import Counter

def get_rows(file):
    with Path(file).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():yield json.loads(line)

def equal(a,b):
    if isinstance(b,dict):
        return isinstance(a,dict) and set(a)==set(b) and all(equal(a[k],b[k]) for k in b)
    if isinstance(b,list):
        return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if type(b) in (int,float):
        return type(a) in (int,float) and math.isfinite(a) and math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-8)
    return type(a)==type(b) and a==b

def review(input_file,output_file,holdout_file=None):
    protected=set()
    if holdout_file:
        for row in get_rows(holdout_file):
            protected.add(hashlib.sha256(row["input"].encode()).hexdigest())
    accepted=[];rejected=Counter();seen=set()
    for row in get_rows(input_file):
        question=row.get("input","");expected=row.get("independent_gold")
        teacher=row.get("teacher_answer");review=row.get("review")
        if not question or not isinstance(expected,dict) or not isinstance(review,dict):
            rejected["missing_source_or_verification"]+=1;continue
        if hashlib.sha256(question.encode()).hexdigest() in protected:
            rejected["heldout_collision"]+=1;continue
        if not review.get("human_verified") or not review.get("reviewer") or not review.get("source_checked"):
            rejected["not_human_reviewed"]+=1;continue
        if row.get("copyright_training_permission") is not True:
            rejected["rights_not_approved"]+=1;continue
        try:
            teacher_json=json.loads(teacher) if isinstance(teacher,str) else teacher
        except (ValueError,TypeError):
            rejected["bad_teacher_json"]+=1;continue
        if not equal(teacher_json,expected):
            rejected["teacher_fails_independent_gold"]+=1;continue
        key=hashlib.sha256(question.encode()).hexdigest()
        if key in seen:
            rejected["duplicate"]+=1;continue
        seen.add(key)
        # The training answer comes from checked GOLD, not raw model rationale.
        accepted.append({"id":key[:24],"split":"train","task":row.get("task","fsa_reviewed"),
                         "input":question,"output":json.dumps(expected,separators=(",",":")),
                         "origin":"teacher_proposal_independent_gold",
                         "review_status":"human_verified",
                         "evidence_locator":row.get("source_locator"),
                         "reviewer":review["reviewer"]})
    dest=Path(output_file);dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("w",encoding="utf-8") as f:
        for row in accepted:f.write(json.dumps(row,ensure_ascii=False)+"\n")
    summary={"accepted":len(accepted),"rejected":dict(rejected),
             "warning":"Use only after independent held-out evaluation; no model automatically retrained."}
    (dest.parent/(dest.stem+"-audit.json")).write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary))
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--candidates",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--holdout")
    a=p.parse_args();review(a.candidates,a.out,a.holdout)
