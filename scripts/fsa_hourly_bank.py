#!/usr/bin/env python3
"""Hourly FSA practice generator. Never trains, deploys, or promotes a model."""
import argparse,json,hashlib,random,math,os,time,urllib.request
from pathlib import Path
from collections import Counter
from datetime import date,datetime,timezone

CIKS={"AAPL":320193,"MSFT":789019,"NVDA":1045810,"AMZN":1018724,"TSLA":1318605}
TAGS=["RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"]

def put(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def q(kind,inp,gold,source,priority="P0",ready=False,checks=()):
    uid=json.dumps([kind,inp,gold,source.get("url")],sort_keys=True)
    return {"id":hashlib.sha256(uid.encode()).hexdigest()[:24],"task":kind,
            "input":inp,"output":json.dumps(gold,separators=(",",":")),
            "expected":gold,"source":source,"priority":priority,
            "review_status":"synthetic_verified" if source["kind"]=="synthetic" else "needs_review",
            "training_eligible":bool(ready),"checks":list(checks)}

def synthetic(seed,n):
    r=random.Random(seed);out=[]
    for i in range(n):
        k=i%6;s={"kind":"synthetic","seed":seed,"example":i}
        if k==0:
            v=r.randint(100,800)+i*1000
            e=[{"account":"PPE","debit":v,"credit":0},{"account":"Cash","debit":0,"credit":v}]
            assert sum(x["debit"] for x in e)==sum(x["credit"] for x in e)
            out.append(q("journal_entry",f"Pay USD {v} cash for PPE. Give balanced debit/credit journal entries JSON.",{"entries":e},s,ready=True,checks=["DR PPE; CR Cash","DR=CR"]))
        elif k==1:
            c,inv,ppe=r.randint(70,230),r.randint(90,210),r.randint(100,300)
            liab=r.randint(80,140);eq=c+inv+ppe-liab
            borrow=r.randint(10,80);buy=r.randint(10,60)
            assets=c+inv+ppe+borrow
            assert assets==liab+borrow+eq
            inp=f"Begin cash={c}, inventory={inv}, PPE={ppe}, debt={liab}, equity={eq}. Borrow {borrow}, buy PPE for cash {buy}. Return final assets, debt, equity and balance equality JSON."
            out.append(q("accounting_equation",inp,{"assets":assets,"debt":liab+borrow,"equity":eq,"balanced":True},s,ready=True,checks=["Equipment is asset swap","A=L+E"]))
        elif k==2:
            sales,cost,capex,loan=r.randint(90,210),r.randint(15,65),r.randint(5,35),r.randint(10,50)
            ni=sales-cost;bs={"cash":100+sales-capex+loan,"inventory":80-cost,
                              "ppe":100+capex,"debt":80+loan,"equity":200+ni}
            assert bs["cash"]+bs["inventory"]+bs["ppe"]==bs["debt"]+bs["equity"]
            inp=f"Begin USD: Cash=100, Inventory=80, PPE=100, Debt=80, Equity=200. Cash revenue {sales}, inventory COGS {cost}, cash CapEx {capex}, cash debt proceeds {loan}. No other activity. Derive IS, BS, SCF."
            gold={"IS":{"revenue":sales,"COGS":cost,"NI":ni},"BS":bs,
                  "SCF":{"CFO":sales,"CFI":-capex,"CFF":loan,"cash_change":sales-capex+loan}}
            out.append(q("three_statements",inp,gold,s,ready=True,
                         checks=["NI = Sales - COGS","CFO=NI+inventory decrease","Assets=Liabilities+Equity","Cash roll-forward"]))
        elif k==3:
            ni,ocf,assets=r.randint(-100,200),r.randint(20,250),r.choice([100,200,400,800,1000])
            inp=f"Evidence S1: NI={ni}, OCF={ocf}, average assets={assets} USD millions. Compute accrual ratio (NI-OCF)/average assets as a fraction. Return JSON value/source_id S1."
            out.append(q("accrual_ratio",inp,{"value":round((ni-ocf)/assets,8),"source_id":"S1"},s,ready=True,
                         checks=["Correct negative sign","Fraction not percent"]))
        elif k==4:
            prev=r.randint(100,1000);cur=prev+r.randint(-90,90)
            inp=f"Evidence S1: sales previous={prev} current={cur} (both USD millions). Compute period change as fraction JSON value/source_id S1."
            out.append(q("numeric_sign_units",inp,{"value":round((cur-prev)/prev,8),"source_id":"S1"},s,"P1",True,
                         ["YoY denominator previous","No unit or scale mistake"]))
        else:
            amount=r.randint(10,200)+i*150
            inp=f"Evidence S1 contains cash of {amount} USD millions but no long-term debt figure. Return JSON long_term_debt=null and reason=insufficient_evidence."
            out.append(q("evidence_abstention",inp,{"long_term_debt":None,"reason":"insufficient_evidence"},s,"P2",True,
                         ["No unsupported inference"]))
    return out

def annual(concepts,tags):
    for tag in tags:
        items={}
        for x in concepts.get(tag,{}).get("units",{}).get("USD",[]):
            try:
                days=(date.fromisoformat(x["end"])-date.fromisoformat(x["start"])).days
                ok=x.get("form")=="10-K" and x.get("fp")=="FY" and 325<=days<=380 and isinstance(x["val"],(float,int)) and math.isfinite(x["val"])
                if ok and (x["end"] not in items or x.get("filed","")>items[x["end"]].get("filed","")):items[x["end"]]=x
            except (KeyError,ValueError,TypeError):pass
        if items:return tag,sorted(items.values(),key=lambda x:x["end"],reverse=True)
    return None,[]

def from_sec(doc,ticker,url):
    usgaap=doc.get("facts",{}).get("us-gaap",{});out=[]
    tag,revs=annual(usgaap,TAGS)
    if len(revs)>1:
        cur,prev=revs[:2]
        gap=(date.fromisoformat(cur["end"])-date.fromisoformat(prev["end"])).days
        if prev["val"]>0 and 320<=gap<=400:
            inp=f"Official SEC companyfacts {ticker} {tag}: FY ending {prev['end']} revenue USD {prev['val']}; FY ending {cur['end']} revenue USD {cur['val']}. Compute YoY revenue growth FRACTION and source_id SEC."
            src={"kind":"sec","url":url,"ticker":ticker,"tag":tag,"accessions":[prev.get("accn"),cur.get("accn")]}
            out.append(q("sec_revenue_growth",inp,{"value":round((cur["val"]-prev["val"])/prev["val"],8),"source_id":"SEC"},src,"P1",False,["Same tag, annual period, USD","Cross-check original filing"]))
    x,ocfs=annual(usgaap,["NetCashProvidedByUsedInOperatingActivities"])
    y,capexes=annual(usgaap,["PaymentsToAcquirePropertyPlantAndEquipment"])
    by_end={v["end"]:v for v in capexes}
    for a in ocfs:
        b=by_end.get(a["end"])
        if b and b["start"]==a["start"] and b.get("accn")==a.get("accn"):
            inp=f"SEC {ticker} FY {a['end']}: CFO USD {a['val']}, PPE purchases USD {b['val']}. Compute simple FCF=CFO-PPE purchases. JSON value/source_id SEC."
            source={"kind":"sec","url":url,"ticker":ticker,"accession":a.get("accn"),"tags":[x,y]}
            val=a["val"]-b["val"]
            out.append(q("sec_fcf",inp,{"value":int(val) if float(val).is_integer() else val,"source_id":"SEC"},source,"P1",False,["Verify exact same period/accession","FCF definition CFO less capex"]))
            break
    return out

def fetch_sec(agent):
    if not agent or "@" not in agent:return [],["SEC_USER_AGENT missing: skipped real SEC data"]
    out=[];warnings=[]
    for ticker,cik in CIKS.items():
        url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        try:
            req=urllib.request.Request(url,headers={"User-Agent":agent,"Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=15) as resp: doc=json.loads(resp.read(9000000))
            if doc.get("cik")!=cik:raise ValueError("CIK mismatch")
            out+=from_sec(doc,ticker,url)
        except (OSError,ValueError,KeyError) as exc:warnings.append(f"{ticker} SEC {type(exc).__name__}")
        time.sleep(1.2)
    return out,warnings

def from_reports(filename):
    p=Path(filename)
    if not p.is_file():return [],["No approved report manifest found"]
    registry=json.loads(p.read_text(encoding="utf-8"));out=[];warnings=[]
    for doc in registry:
        name=doc.get("id","unnamed")
        if not(doc.get("review_status")=="approved" and
               doc.get("ml_rights") in ("owned","licensed_for_training","public_domain") and
               doc.get("public_redistribution_allowed") is True and doc.get("rights_evidence")):
            warnings.append(f"{name}: unapproved rights or human review");continue
        for fact in doc.get("facts",[])[:20]:
            if not fact.get("verified") or any(k not in fact for k in ("name","value","unit","period","locator")):continue
            value=fact["value"]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):continue
            source={"kind":"research","url":doc.get("source_url"),"id":name,"locator":fact["locator"],"rights":doc["ml_rights"]}
            inp=f"Evidence S1 from licensed research {name} ({fact['locator']}): {fact['name']} in {fact['period']} = {value} {fact['unit']}. Extract JSON value, unit, period, source_id."
            gold={"value":value,"unit":fact["unit"],"period":fact["period"],"source_id":name}
            item=q("research_fact",inp,gold,source,"P1",True,["Permission approved","Human verified numeric fact"])
            item["review_status"]="human_verified_report_fact";out.append(item)
    return out,warnings

def error_report(filename):
    if not filename or not Path(filename).is_file():return {"seen":0,"wrong":0,"by_task":{}}
    doc=json.loads(Path(filename).read_text(encoding="utf-8"));all_rows=[]
    for v in doc.get("protocols",{}).values():all_rows+=v.get("examples",v.get("details",[]))
    failed=Counter(x.get("task","unknown") for x in all_rows if not x.get("correct",True))
    return {"seen":len(all_rows),"wrong":sum(failed.values()),"by_task":dict(failed)}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--out",required=True);a.add_argument("--hour")
    a.add_argument("--count",type=int,default=18)
    a.add_argument("--reports",default="research_reports/approved_manifest.json")
    a.add_argument("--seen");a.add_argument("--evaluation")
    a.add_argument("--user-agent",default=os.environ.get("SEC_USER_AGENT",""))
    p=a.parse_args()
    if not 6<=p.count<=48:a.error("Expected 6..48 synthetic questions")
    hour=datetime.strptime(p.hour,"%Y-%m-%dT%H").replace(tzinfo=timezone.utc) if p.hour else datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
    seen=set(Path(p.seen).read_text(encoding="utf-8").splitlines()) if p.seen and Path(p.seen).is_file() else set()
    rows=synthetic(int(hour.timestamp()//3600),p.count)
    sec,sec_warnings=fetch_sec(p.user_agent);rows+=sec
    reports,report_warnings=from_reports(p.reports);rows+=reports
    emitted=[]
    for item in rows:
        if item["id"] not in seen:
            seen.add(item["id"]);item["generated_utc"]=hour.isoformat();emitted.append(item)
    errors=error_report(p.evaluation)
    tasks=[
      {"priority":"P0","title":"Historical replay","next":"Keep >=30% reviewed earlier exercises; check regressions"},
      {"priority":"P0","title":"FSA journal entries and three statements","next":"Verify debits=credits, BS and cash bridge"},
      {"priority":"P1","title":"Real SEC extraction","next":"Cross-check original 10-K/10-Q and accession/units"},
      {"priority":"P1","title":"Wrong-answer mining","next":"Prioritize sign, scale, ratio and unit errors","weak_tasks":errors["by_task"]},
      {"priority":"P2","title":"Reasoning and abstention","next":"Require stepwise verification and unsupported-value nulls"},
      {"priority":"P2","title":"Larger model distillation","next":"Queue teacher answers; require independent gold verification"},
      {"priority":"P1","title":"Research rights gate","next":"Human-approved licensed/public-domain/owned factual excerpts only"}]
    counts=dict(Counter(r["task"] for r in emitted))
    bank={"hour_utc":hour.isoformat(),"new_questions":len(emitted),"task_counts":counts,
          "training_eligible":sum(x["training_eligible"] for x in emitted),
          "requires_review":sum(not x["training_eligible"] for x in emitted),
          "warnings":sec_warnings+report_warnings,"questions":emitted}
    base=Path(p.out)
    put(base/"hourly_bank.json",bank)
    put(base/"tasks.json",{"hour_utc":hour.isoformat(),"tasks":tasks,"error_summary":errors})
    (base/"seen_ids.txt").write_text("\n".join(sorted(seen))+"\n",encoding="utf-8")
    summary=[f"# Hourly FSA question bank: {hour.isoformat()}",
             f"New questions: {len(emitted)}. Ready: {bank['training_eligible']}; needs review: {bank['requires_review']}.",
             "","## Backlog"]
    summary += [f"- {v['priority']} {v['title']}: {v['next']}" for v in tasks]
    summary += ["","## Generated question categories"]+[f"- {k}: {v}" for k,v in sorted(counts.items())]
    summary += ["","Synthetic exercises are not real filings. SEC questions require source review before training."]
    (base/"SUMMARY.md").write_text("\n".join(summary)+"\n",encoding="utf-8")
    print(json.dumps({"new":len(emitted),"tasks":counts,"warnings":bank["warnings"]},ensure_ascii=False))
if __name__=="__main__":main()
