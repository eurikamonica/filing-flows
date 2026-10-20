"""Incremental public SEC supply-chain research collector and forecast evidence adapter.

Owns *only* a dedicated SQLite research DB + published derived JSON.
No website import, unsourced relationship assertion, or trading is performed here.
"""
import argparse
from datetime import datetime, timezone, date
import json
from pathlib import Path
import re
import sys

from research.industry_supply_chain import ledger, sec_capex
from research.ai_capex_attribution import calculate

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def atomic_json(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(path)

def resolved_cik(con,ticker):
    """Unique company identity only; ticker collisions stay unresolved."""
    if not isinstance(ticker,str) or not re.fullmatch(r"[A-Z0-9.-]{1,12}",ticker.upper()):
        return None
    rows=con.execute("SELECT cik FROM companies WHERE UPPER(ticker)=?",(ticker.upper(),)).fetchall()
    return rows[0]["cik"] if len(rows)==1 else None

def quarter_end(label):
    idx=ledger.dt.date(int(label[:4]),int(label[5])*3,1)
    from calendar import monthrange
    return idx.replace(day=monthrange(idx.year,idx.month)[1]).isoformat()

def model_scenario(con, spec, as_of):
    """Use PR #38's calculator; keep assumptions in a separate estimated ledger.

    A scenario is not called 'verified', including with real tickers or XBRL CapEx.
    No base 8B/LLM-generated financial value becomes a reported actual.
    """
    result=calculate(spec)             # calculator enforces demo_only=True
    buyer=resolved_cik(con,spec.get("buyer_ticker"))
    unmatched=set()
    n=0
    out=[]
    for case in result["scenarios"]:
        estimates=[]
        for row in case["revenue_timing_estimate_usd"]:
            vendor=resolved_cik(con,row["vendor"])
            if not buyer or not vendor:
                unmatched.add(row["vendor"])
                continue
            recognition=quarter_end(row["period"])
            amount=float(row["value_usd"])
            con.execute("""INSERT INTO attributed_revenue
                (scenario,buyer_cik,supplier_cik,category,recognition_period,usd,as_of,evidence_level,method)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(scenario,buyer_cik,supplier_cik,category,recognition_period,as_of)
                DO UPDATE SET usd=excluded.usd""",
                ("DEMO:"+case["name"],buyer,vendor,"terminal_spend",
                 recognition,amount,as_of,"estimated","illustrative_BOM_share_plus_lag"))
            n+=1
            estimates.append({"supplier":row["vendor"],"supplier_cik":vendor,
                              "period":row["period"],"end":recognition,"usd":amount,
                              "actual_segment_revenue_usd":None,
                              "reconciliation":"Not verified; no matched segment actual"})
        out.append({"name":case["name"],"capex_usd":case["capex_usd"],
                    "terminal_vendor_usd":case["terminal_vendor_usd"],
                    "unallocated_by_category_usd":case["unallocated_by_category_usd"],
                    "recognized_revenue_scenarios":estimates})
    con.commit()
    return {"status":"illustrative_only","demo_only":True,"buyer":spec["buyer"],
            "buyer_ticker":spec.get("buyer_ticker"),"buyer_cik":buyer,
            "period":spec["period"],"as_of":as_of,"scenarios":out,
            "unresolved_supplier_tickers":sorted(unmatched),
            "inserted_estimate_rows":n,
            "note":"No supplier sales forecasts validated. Scenario assumptions are not SEC invoices."}

def publish(con, dest, status, scenario_input=None):
    dest=Path(dest)
    at=now()
    coverage=ledger.coverage(con)
    ledger.export_graphs(con,dest/"industry")
    forecast={"status":"no_reviewed_forecast","as_of":at,"real_forecasts":[],
              "examples":None,"coverage":coverage,
              "reason":"No verified buyer procurement/BOM shares, no matched supplier segment revenue actuals. Never infer numbers from CapEx alone."}
    if scenario_input:
        spec=json.loads(Path(scenario_input).read_text(encoding="utf-8"))
        forecast["examples"]=model_scenario(con,spec,at)
        forecast["status"]="illustrative_example_available"
    atomic_json(dest/"forecast.json",forecast)
    audit={"generated_at":at,"collector_status":status,
           "sqlite_counts":ledger.coverage(con),
           "pipeline":{"collection":{"status":"partial" if status.get("errors") else "ok",
                                      "checked":status.get("checked",0)},
                       "parsing":{"status":"partial","note":"SEC XBRL cash CapEx, no contract/EX-10 extraction yet"},
                       "modeling":{"status":"research_only","note":"No validated financial forecasts"},
                       "publication":{"status":"snapshot_prepared","note":"Pages deploy must be checked separately"}},
           "limitations":["CIK coverage is not full SIC supplier coverage",
                          "Missing fiscal facts are not zero",
                          "No real market share data is inferred",
                          "Market price odds are not confirmed contracts"]}
    atomic_json(dest/"health.json",audit)
    return audit

def collect(args):
    db=Path(args.db)
    db.parent.mkdir(parents=True,exist_ok=True)
    with ledger.open_db(db) as con:
        companies=con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if companies==0:
            data=sec_capex.get_json("https://www.sec.gov/files/company_tickers.json",args.agent)
            sec_capex.universe(con,data)
        # Do not overwrite status with 'success' when every target fails.
        status=sec_capex.refresh(con,args.agent,args.batch,args.refresh_days)
        status["company_inventory"]=con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        audit=publish(con,args.public,status,args.scenario)
    return audit

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",required=True)
    parser.add_argument("--public",required=True)
    parser.add_argument("--agent",default="")
    parser.add_argument("--batch",type=int,default=25)
    parser.add_argument("--refresh-days",type=int,default=14)
    parser.add_argument("--scenario",default=None,help="Explicit demo-labelled example only")
    parser.add_argument("--offline",action="store_true",
                        help="Publish from existing SQLite without hitting the SEC")
    a=parser.parse_args()
    if not 1<=a.batch<=100:
        parser.error("batch must be 1..100")
    if a.offline:
        with ledger.open_db(a.db) as con:
            audit=publish(con,a.public,{"checked":0,"errors":[],"mode":"offline"},a.scenario)
    else:
        if "@" not in a.agent:
            parser.error("SEC_USER_AGENT is required for network collection")
        audit=collect(a)
    print(json.dumps(audit,indent=2))
if __name__=="__main__":
    main()
