"""Bounded official SEC company universe / SIC / XBRL cash CapEx ingestion.

Run incrementally into the evidence-first SQLite ledger. The SEC index gives CIK/
ticker/name but not SIC: submissions for each issuer supplies SIC. Never imply a
full industry census until the coverage query confirms it.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .ledger import cik, sic, open_db, ensure_company, utcnow
except ImportError:
    from ledger import cik, sic, open_db, ensure_company, utcnow

SEC = "https://data.sec.gov/"
TAG = "PaymentsToAcquirePropertyPlantAndEquipment"


def get_json(url, agent, pause=0.45):
    if "@" not in agent or len(agent)<12:
        raise ValueError("Set a descriptive SEC_USER_AGENT with a real email")
    for i in range(3):
        time.sleep(pause)
        try:
            req=Request(url,headers={"User-Agent":agent,"Accept":"application/json",
                                    "Accept-Encoding":"identity"})
            with urlopen(req,timeout=30) as response:
                content=response.read(32*1024*1024+1)
            if len(content)>32*1024*1024:
                raise ValueError("SEC JSON exceeds configured size limit")
            return json.loads(content)
        except HTTPError as err:
            if err.code not in (429,500,502,503,504) or i==2:
                raise
            time.sleep(min(20,2**(i+2)))
        except URLError:
            if i==2:
                raise
            time.sleep(min(20,2**(i+2)))


def universe(con, data, at=None):
    """Accept official company_tickers.json object; register CIK even if SIC unknown."""
    at=at or utcnow()
    items=data.values() if isinstance(data,dict) else data
    n=0
    for r in items:
        if not isinstance(r,dict) or not r.get("cik_str") or not r.get("title"):
            continue
        ensure_company(con,{"cik":r["cik_str"],"name":r["title"],"ticker":r.get("ticker")},at)
        n+=1
    con.commit()
    return n


def days(start,end):
    try:
        return (dt.date.fromisoformat(end)-dt.date.fromisoformat(start)).days
    except (TypeError,ValueError):
        return 0


def quarterly_cash_capex(data, as_of=None):
    """Direct 3-month US-GAAP payments, or same-FY/YTD quarter differencing.

    Reject missing components, mismatched start dates, revisions filed after
    as-of, negative computed payments and unsupported currency. Period key is
    original fiscal end date, not a guessed calendar quarter.
    """
    units=(data.get("facts",{}).get("us-gaap",{}).get(TAG,{})
           .get("units",{}).get("USD",[]))
    source=[]
    for r in units:
        if (r.get("form") not in ("10-Q","10-K") or r.get("val") is None or
            not r.get("start") or not r.get("end") or not r.get("filed") or
            (as_of and r["filed"]>as_of)):
            continue
        elapsed=days(r["start"],r["end"])
        if 55<=elapsed<=380 and r["val"]>=0:
            source.append(r)
    # Point-in-time: latest accessible filing for a particular duration/context.
    by_context={}
    for r in source:
        k=(r["start"],r["end"],r.get("fy"),r.get("fp"))
        if k not in by_context or (r["filed"],r.get("accn",""))>(by_context[k]["filed"],by_context[k].get("accn","")):
            by_context[k]=r
    rows=list(by_context.values())
    answer={}
    for r in rows:
        elapsed=days(r["start"],r["end"])
        if 55<=elapsed<=115:
            candidate={**r,"quarterly_value":r["val"],"method":"direct_three_month"}
            prior=answer.get(r["end"])
            if prior is None or (r["filed"],r.get("accn",""))>(prior["filed"],prior.get("accn","")):
                answer[r["end"]]=candidate
    # YTD duration differencing: same exact fiscal-year start, near quarterly step.
    for current in rows:
        if days(current["start"],current["end"])<=115:
            continue
        options=[prior for prior in rows if prior["start"]==current["start"]
                 and prior["end"]<current["end"] and
                 55<=days(prior["end"],current["end"])<=115 and
                 days(prior["start"],prior["end"])>=55 and
                 (not as_of or prior["filed"]<=as_of)]
        if not options:
            continue
        prev=max(options,key=lambda r:(r["end"],r["filed"]))
        amount=current["val"]-prev["val"]
        if amount<0:
            continue
        row={**current,"quarterly_value":amount,"method":"ytd_difference",
             "subtracted_prior_accn":prev.get("accn"),
             "subtracted_prior_end":prev["end"]}
        existing=answer.get(current["end"])
        # Prefer a directly reported three-month fact when available.
        if existing is None:
            answer[current["end"]]=row
    return [answer[k] for k in sorted(answer)]


def save_submissions(con, identifier, payload, at=None):
    at=at or utcnow()
    code=sic(payload.get("sic"))
    row=con.execute("SELECT name,ticker FROM companies WHERE cik=?",(identifier,)).fetchone()
    name=payload.get("name") or (row["name"] if row else None)
    if not name:
        raise ValueError("SEC submission has no legal name")
    ensure_company(con,{"cik":identifier,"name":name,
                        "ticker":next(iter(payload.get("tickers") or []),row["ticker"] if row else ""),
                        "sic":code},at)
    if code:
        con.execute("UPDATE industries SET name=?,source=?,observed_at=? WHERE sic=? AND name LIKE 'SIC %'",
                    (payload.get("sicDescription") or ("SIC "+code),"SEC submissions",at,code))
    con.commit()
    return code


def save_cash_capex(con, identifier, payload, as_of=None, at=None):
    at=at or utcnow()
    count=0
    for row in quarterly_cash_capex(payload,as_of):
        accession=row.get("accn")
        if not accession:
            continue
        con.execute("""INSERT INTO financials
          (cik,metric,period_end,fiscal_year,fiscal_period,usd,source_tag,
           source_url,accession,filed_at,observed_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(cik,metric,period_end,accession) DO UPDATE SET
          usd=excluded.usd,observed_at=excluded.observed_at""",
            (identifier,"cash_capex",row["end"],row.get("fy"),row.get("fp"),
             row["quarterly_value"],"us-gaap:"+TAG+" / "+row["method"],
             SEC+"api/xbrl/companyfacts/CIK"+identifier.zfill(10)+".json",
             accession,row["filed"],at))
        count+=1
    con.commit()
    return count


def due_companies(con, cap, refresh_days=14, at=None):
    """Fair work queue: new issuers first, but reserve up to 20% of each batch
    for previously failed SEC requests after an 8-hour backoff (not 14 days).
    """
    at=at or dt.datetime.now(dt.timezone.utc)
    cutoff=(at-dt.timedelta(days=refresh_days)).isoformat()
    retry_cutoff=(at-dt.timedelta(hours=8)).isoformat()
    retries=con.execute("""SELECT c.cik FROM companies c
       JOIN collector_status s ON s.cik=c.cik AND s.feed='sec-companyfacts'
       WHERE s.status='error' AND s.last_checked<?
       ORDER BY s.last_checked ASC,c.cik ASC LIMIT ?""",
       (retry_cutoff,max(1,cap//5))).fetchall()
    fresh=con.execute("""SELECT c.cik FROM companies c
       LEFT JOIN collector_status s ON s.cik=c.cik AND s.feed='sec-companyfacts'
       WHERE s.last_checked IS NULL OR (s.status='ok' AND s.last_checked<?)
       ORDER BY CASE WHEN c.sic IS NULL THEN 0 ELSE 1 END,
                s.last_checked ASC,c.cik ASC LIMIT ?""",
       (cutoff,cap-len(retries))).fetchall()
    return [r["cik"] for r in retries]+[r["cik"] for r in fresh]


def refresh(con, agent, max_issuers=20, refresh_days=14):
    """No background promises: explicit bounded batch, durable errors/restarts."""
    result={"checked":0,"capex_rows":0,"sic_updated":0,"errors":[]}
    for identifier in due_companies(con,max_issuers,refresh_days):
        status="ok";failure=None
        try:
            profile=get_json(SEC+"submissions/CIK"+identifier.zfill(10)+".json",agent)
            if save_submissions(con,identifier,profile):
                result["sic_updated"]+=1
            facts=get_json(SEC+"api/xbrl/companyfacts/CIK"+identifier.zfill(10)+".json",agent)
            result["capex_rows"]+=save_cash_capex(con,identifier,facts)
        except (HTTPError,URLError,ValueError,KeyError,TypeError) as exc:
            status="error";failure=str(exc)[:280]
            result["errors"].append({"cik":identifier,"message":failure})
        con.execute("""INSERT INTO collector_status VALUES(?,?,?,?,?)
          ON CONFLICT(cik,feed) DO UPDATE SET last_checked=excluded.last_checked,
                   status=excluded.status,detail=excluded.detail""",
                    (identifier,"sec-companyfacts",utcnow(),status,failure))
        con.commit()
        result["checked"]+=1
    result["note"]="Bounded SEC requests; SIC remains null until a valid submissions profile is fetched. Missing cash CapEx is not zero."
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--agent",default=None,help="SEC_USER_AGENT with contact email; required for fetch")
    p.add_argument("--max-issuers",type=int,default=20)
    p.add_argument("--refresh-days",type=int,default=14)
    p.add_argument("--universe",type=Path,help="Previously downloaded official SEC company_tickers.json")
    p.add_argument("--fetch-universe",action="store_true",help="Fetch the public SEC ticker inventory with SEC_USER_AGENT")
    args=p.parse_args()
    if not 1<=args.max_issuers<=100 or args.refresh_days<1:
        raise ValueError("Bounded max-issuers (1 to 100) and positive refresh-days required")
    if args.universe and args.fetch_universe:
        raise ValueError("Choose --universe or --fetch-universe, not both")
    import os
    agent=args.agent or os.environ.get("SEC_USER_AGENT","")
    with open_db(args.db) as con:
        if args.universe:
            result={"imported":universe(con,json.loads(args.universe.read_text(encoding="utf-8")))}
        elif args.fetch_universe:
            result={"imported":universe(con,get_json("https://www.sec.gov/files/company_tickers.json",agent))}
        else:
            result=refresh(con,agent,args.max_issuers,args.refresh_days)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
