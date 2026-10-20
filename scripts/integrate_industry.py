"""Stage independently refreshed industry research data into GitHub Pages output.

Safe failure mode: absent industry data -> explicit 'not collected', not fake relations.
Run AFTER build_site.py and stage-public.py, BEFORE pages artifact upload.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
def load(path,default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError):
        return default

def save(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")

def resolved_company_index(industry):
    by_cik={}
    by_ticker={}
    for p in sorted((industry/"industry").glob("[0-9][0-9][0-9][0-9].json")):
        doc=load(p,{}) or {}
        for c in doc.get("companies",[]):
            cik=str(int(c["cik"])) if str(c.get("cik","")).isdigit() else None
            if not cik:
                continue
            rec={"cik":cik,"ticker":c.get("ticker"),"name":c.get("name"),
                 "sic":doc.get("sic"),"industry":doc.get("name")}
            by_cik[cik]=rec
            ticker=str(c.get("ticker") or "").upper()
            if ticker:
                by_ticker.setdefault(ticker,[]).append(cik)
    return by_cik,by_ticker

def merge_gamma(site,industry,by_cik):
    """Read-only evidence-respecting enrichment of existing Gamma industry JSON."""
    counts={"enriched_industries":0,"added_relations":0,"skipped_unresolved":0}
    gamma=site/"data"/"gamma"
    for src in (industry/"industry").glob("[0-9][0-9][0-9][0-9].json"):
        target=gamma/src.name
        if not target.is_file():
            continue  # keep Gamma's historic revenue coverage unchanged
        incoming=load(src,{}) or {}
        original=load(target,{}) or {}
        old=original.get("relationships") or []
        keys={(str(r.get("supplier_cik") or ""),str(r.get("customer_cik") or ""),
               str(r.get("source_url") or ""),str(r.get("relationship_type") or "")) for r in old}
        added=0
        for e in incoming.get("relationships",[]):
            source=str(e.get("source_url") or "")
            supp=by_cik.get(str(e.get("supplier_cik") or ""))
            cust=by_cik.get(str(e.get("customer_cik") or ""))
            if not supp or not cust:
                counts["skipped_unresolved"]+=1
                continue
            # Trust explicit ledger evidence grade, not inferred monetary amounts.
            evidence=e.get("evidence_level") or "inferred"
            key=(str(e.get("supplier_cik")),str(e.get("customer_cik")),
                 source,str(e.get("relationship_type") or ""))
            if key in keys:
                continue
            v=e.get("value_usd") if evidence=="disclosed" and source.startswith("https://www.sec.gov/") else None
            old.append({"supplier":supp.get("ticker") or supp["name"],
                        "customer":cust.get("ticker") or cust["name"],
                        "supplier_cik":supp["cik"],"customer_cik":cust["cik"],
                        "supplier_sic":supp["sic"],"customer_sic":cust["sic"],
                        "kind":e.get("relationship_type") or "supplier_customer",
                        "relationship_type":e.get("relationship_type"),"product":e.get("product"),
                        "evidence_level":evidence,
                        "source_url":source or None,
                        "accession_number":e.get("accession_number"),
                        "valid_from":e.get("valid_from"),"valid_to":e.get("valid_to"),
                        "value_usd":v,"value_type":"reported" if v is not None else None})
            keys.add(key)
            added+=1
        if added:
            original["relationships"]=old
            original["evidence_ledger_enriched"]=True
            save(target,original)
            counts["enriched_industries"]+=1
            counts["added_relations"]+=added
    return counts

def market_links(site,by_cik,by_ticker):
    source=site/"disclosures"/"data"/"consensus"/"markets.json"
    doc=load(source,{}) or {}
    rows=doc.get("rows") if isinstance(doc,dict) else None
    results=[]
    if isinstance(rows,list):
        for m in rows[:20000]:
            ticker=str(m.get("ticker") or "").upper()
            matches=list(set(by_ticker.get(ticker,[])))
            if len(matches)!=1:
                continue
            rec=by_cik[matches[0]]
            results.append({"market_title":m.get("title"),"source":m.get("source"),
                            "source_url":m.get("url"),"market_kind":m.get("kind"),
                            "end":m.get("end"),"price_implied_probability":m.get("p"),
                            "cik":rec["cik"],"ticker":ticker,"sic":rec["sic"],
                            "industry":rec["industry"],"link_type":"identity_match_only",
                            "causal_revenue_impact":"not_estimated",
                            "settlement_terms_reviewed":False})
    return {"source":"Filing Flows Consensus markets (if collected)",
            "mapping_method":"unique exact ticker to CIK identity; not a causal chain",
            "matched_events":len(results),
            "events":results[:4000],"limitation":"Ticker changes, unresolved identities, and contracts with different settlement terms are excluded."}

def stage(site,snapshot):
    now=datetime.now(timezone.utc).isoformat(timespec="seconds")
    site=Path(site)
    out=site/"data"/"industry-intelligence"
    if snapshot and (Path(snapshot)/"industry"/"index.json").is_file():
        shutil.copytree(snapshot,out,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.sqlite","*.sqlite3","*.db"))
        by_cik,by_ticker=resolved_company_index(out)
        merge=merge_gamma(site,out,by_cik)
        events=market_links(site,by_cik,by_ticker)
        save(out/"events.json",events)
        input_health=load(out/"health.json",{}) or {}
        underlying=input_health.get("sqlite_counts",{})
        state="partial" if not underlying.get("companies") else "collected"
    else:
        out.mkdir(parents=True,exist_ok=True)
        by_cik={}
        merge={"enriched_industries":0,"added_relations":0}
        events={"matched_events":0,"events":[],"limitation":"Collector snapshot not available"}
        save(out/"industry"/"index.json",{"industries":[],"coverage":{}})
        save(out/"forecast.json",{"status":"no_collector_snapshot","real_forecasts":[],
                                  "examples":None,"reason":"Research data not published yet"})
        save(out/"events.json",events)
        state="not_collected"
        underlying={}
    health={
        "generated_at":now,
        "build_run_id":os.environ.get("GITHUB_RUN_ID"),
        "source_commit":os.environ.get("GITHUB_SHA"),
        "collection":{"status":state,"companies":underlying.get("companies",0),
                      "with_sic":underlying.get("companies_with_sic",0),
                      "cash_capex_rows":underlying.get("capex_rows",0)},
        "parsing":{"status":"partial" if underlying.get("companies") else "not_started",
                   "documented_relations":underlying.get("verified_relations",0),
                   "note":"Company facts and SIC only. Contract NLP and custom taxonomy are not deployed."},
        "modeling":{"status":"research_only",
                    "note":"PR #38 scenario math is available; no validated supplier revenue forecasts."},
        "market_mapping":{"status":"identity_only","matched_events":events.get("matched_events",0),
                          "note":"Probability event impact is not inferred."},
        "publication":{"status":"artifact_prepared_unverified",
                       "note":"This file is generated BEFORE Pages deploy. Check Actions deploy/verification jobs for proof."},
        "gamma_integration":merge,
    }
    save(out/"integration-health.json",health)
    for src,dest in [("web/supplier-revenue.html","supplier-revenue/index.html"),
                     ("web/integration-health.html","integration-health/index.html")]:
        target=site/dest
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy(ROOT/src,target)
    return health

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--site",required=True)
    a.add_argument("--snapshot")
    args=a.parse_args()
    status=stage(args.site,args.snapshot)
    print(json.dumps(status,indent=2))
if __name__=="__main__":
    main()
