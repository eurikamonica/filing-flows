"""SEC GAAP diluted EPS research forecasts for static Filing Flows company pages.

Uses the SEC's originally filed quarter facts, never current restated EPS as a
historical feature. No claim that 13F, Polymarket or FRED are backtested here.
Data are built in GitHub Actions, not accessed from the browser.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, os, statistics, time, urllib.request
from pathlib import Path

TARGET_TICKERS = ("AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","WMT",
                  "KO","PG","XOM","CVX","HD","COST","V","MA","DIS","ORCL","ADBE",
                  "CRM","AVGO","AMD","INTC","BAC","GS","UNH","JNJ","PFE","IBM",
                  "CAT","BA","NKE","SBUX","LOW","MCD","CSCO","PEP","T","VZ")
FIELDS = ("lag1","lag2","lag3","lag4","lag5","lag8","trend","positive","season1","season2","season3","season4")
MIN_TRAIN = 40
UA = os.getenv("SEC_USER_AGENT", "").strip()
def iso_day(s):
    return dt.date.fromisoformat(str(s)[:10])
def quarter_dates(items):
    """Select FIRST filed standard 3-month EPS value for each period end.

    Multiple fiscal-year facts and restatements coexist in companyfacts.
    Q4 is omitted when the issuer does not separately tag 3-month diluted EPS.
    """
    by_end={}
    for v in items:
        try:
            if v.get("form") not in ("10-Q","10-K","10-Q/A","10-K/A"): continue
            if not v.get("start") or not v.get("end") or not v.get("filed"): continue
            span=(iso_day(v["end"])-iso_day(v["start"])).days
            if not 65<=span<=113:continue
            f=float(v["val"])
            if not math.isfinite(f) or abs(f)>1e4:continue
            end=str(v["end"])
            prior=by_end.get(end)
            k=(str(v["filed"]),0 if v["form"] in ("10-Q","10-K") else 1,
               str(v.get("accn","")))
            if prior is None or k<prior["_sort"]:
                by_end[end]={"end":end,"filed":str(v["filed"]),"eps":f,
                             "accession":v.get("accn",""),"_sort":k}
        except (ValueError,TypeError,KeyError):continue
    return sorted(({k:v for k,v in row.items() if k!="_sort"} for row in by_end.values()),
                  key=lambda x:x["end"])

def sec_eps(companyfacts):
    units=(companyfacts.get("facts",{}).get("us-gaap",{})
           .get("EarningsPerShareDiluted",{}).get("units",{}))
    return quarter_dates(units.get("USD/shares",[]))
def adjacent(series,a,b):
    diff=(iso_day(series[a]["end"])-iso_day(series[b]["end"])).days
    return 72*(a-b)<=diff<=118*(a-b)
def stage(prior):
    m=sum(prior[-4:])/4
    scale=max(.05,sum(abs(x) for x in prior[-8:])/8)
    sd=math.sqrt(sum((x-m)**2 for x in prior[-4:])/4)/scale
    if m<=0: return "turnaround_or_loss"
    if sd>1.3:return "cyclical"
    if (prior[-1]-prior[-5])/scale>.35:return "expansion"
    return "mature"
def row_from(series,i):
    if i<8:return None
    if not all(adjacent(series,i,i-j) for j in range(1,9)):return None
    prev=[x["eps"] for x in series[i-8:i]]
    scale=max(.1,sum(abs(v) for v in prev)/8)
    trend=(prev[-1]-prev[-5])/scale
    quarter=(iso_day(series[i]["end"]).month-1)//3
    x=[1]+[max(-8,min(8,prev[-j]/scale)) for j in (1,2,3,4,5,8)]+[
       max(-8,min(8,trend)),sum(v>0 for v in prev[-4:])/4]+[
       int(quarter==z) for z in range(4)]
    return {"x":x,"scale":scale,"y":series[i]["eps"],"lag4":prev[-4],
            "stage":stage(prev),"end":series[i]["end"],"filed":series[i]["filed"],
            "idx":i}
def next_row(series):
    # create a calendar placeholder so only already-filed observations become inputs
    if len(series)<8:return None
    last=iso_day(series[-1]["end"])
    est=last+dt.timedelta(days=91)
    fake={"end":est.isoformat(),"eps":0,"filed":""}
    rows=series+[fake]
    r=row_from(rows,len(rows)-1)
    if r is None:return None
    r["end_estimated"]=True
    return r
def solve(a,b):
    n=len(b); z=[a[i][:]+[b[i]] for i in range(n)]
    for j in range(n):
        p=max(range(j,n),key=lambda k:abs(z[k][j]))
        z[j],z[p]=z[p],z[j]
        if abs(z[j][j])<1e-12:return None
        u=z[j][j]
        for k in range(j,n+1):z[j][k]/=u
        for i in range(n):
            if i==j:continue
            v=z[i][j]
            for k in range(j,n+1):z[i][k]-=v*z[j][k]
    return [v[-1] for v in z]
def train(rows,lam=60):
    if len(rows)<MIN_TRAIN:return None
    n=len(FIELDS); a=[[0.]*n for _ in range(n)];b=[0.]*n
    for z in rows:
        y=max(-8,min(8,z["y"]/z["scale"]))
        w=min(1,5/max(1,abs(y)))
        for i,v in enumerate(z["x"]):
            b[i]+=w*v*y
            for j,t in enumerate(z["x"]):a[i][j]+=w*v*t
    for k in range(1,n):a[k][k]+=lam
    return solve(a,b)
def predict(model,row):
    return sum(a*b for a,b in zip(model,row["x"]))*row["scale"]
def calc_metric(rows,predictor):
    if not rows:return {"n":0}
    errs=[r["y"]-predictor(r) for r in rows]
    denom=sum(abs(r["y"]) for r in rows)
    return {"n":len(rows),
            "mae":round(sum(abs(v) for v in errs)/len(rows),4),
            "rmse":round(math.sqrt(sum(v*v for v in errs)/len(rows)),4),
            "wmape_pct":round(100*sum(abs(v) for v in errs)/denom,2) if denom else None,
            "yoy_direction_accuracy":round(sum((predictor(r)>r["lag4"])==(r["y"]>r["lag4"]) for r in rows)/len(rows),4)}
def quant(vals,p):
    if not vals:return None
    a=sorted(vals);return a[min(len(a)-1,max(0,math.ceil(p*(len(a)+1))-1))]
def api_rows(series,asof):
    return [r for r in series if r["filed"]<=asof]
def learn(series_by_ticker,asof):
    history={t:api_rows(s,asof) for t,s in series_by_ticker.items()}
    records=[(t,row_from(s,i)) for t,s in history.items() for i in range(8,len(s))]
    records=[(t,r) for t,r in records if r is not None and r["filed"]<=asof]
    train_rows=[r for t,r in records if r["end"][:4]<="2023"]
    validation=[r for t,r in records if r["end"][:4]=="2024"]
    test=[r for t,r in records if r["end"][:4]=="2025"]
    model=train(train_rows)
    if model is None:return {"status":"insufficient_data","records":len(records)}
    validation_residuals=[(r["y"]-predict(model,r))/r["scale"] for r in validation]
    metrics={"train_n":len(train_rows),"validation_n":len(validation),
             "test_n":len(test),"seasonal":calc_metric(test,lambda r:r["lag4"]),
             "stage_ridge":calc_metric(test,lambda r:predict(model,r)),
             "nominal80_coverage":None}
    width=quant([abs(v) for v in validation_residuals],.8)
    if width is not None and test:
        metrics["nominal80_coverage"]=round(sum(abs(r["y"]-predict(model,r))/r["scale"]<=width for r in test)/len(test),4)
    production_model=train([r for t,r in records if r["filed"]<=asof]) or model
    residuals=[(r["y"]-predict(production_model,r))/r["scale"] for t,r in records
               if r["end"][:4]>="2023" and r["end"][:4]<="2025"]
    entries={}
    for ticker,observed in history.items():
        f=next_row(observed)
        if f is None:continue
        m=predict(production_model,f)
        errs=validation_residuals if len(validation_residuals)>=20 else residuals
        lo=quant(errs,.1);hi=quant(errs,.9)
        p=sum(m+e*f["scale"]>f["lag4"] for e in errs)/len(errs) if errs else None
        entries[ticker]={"ticker":ticker,"last_reported":{"eps":observed[-1]["eps"],
                            "end":observed[-1]["end"],"filed":observed[-1]["filed"]},
                         "forecast_end_approx":f["end"],"forecast_eps":round(m,4),
                         "eps_p10":round(m+lo*f["scale"],4) if lo is not None else None,
                         "eps_p90":round(m+hi*f["scale"],4) if hi is not None else None,
                         "p_yoy_growth":round(p,4) if p is not None else None,
                         "last_year_same_q_eps":f["lag4"],
                         "stage":f["stage"],"historical_observations":len(observed),
                         "signal_status":{"13f":"not_backtested","polymarket":"not_backtested",
                          "fred_vintage":"not_backtested","upstream_eps":"unavailable",
                          "downstream_eps":"unavailable"}}
    return {"status":"research_sec_eps","generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "cutoff":asof,"source":"SEC companyfacts; us-gaap:EarningsPerShareDiluted; USD/shares",
            "scope":"real original-filed quarterly SEC GAAP EPS, exploratory backtest",
            "method":"2023 and earlier training; 2024 validation; untouched 2025 test; original filed facts; static research only",
            "limitations":["Universe is hand-picked liquid tickers; survivorship bias",
                           "Fiscal Q4 EPS may be absent; no invented annual-to-quarter EPS",
                           "Reported EPS is SEC GAAP, not consensus adjusted EPS",
                           "Q4 fiscal vs calendar matching requires caution",
                           "13F, macro vintages, supply chain and Polymarket not included in reported results",
                           "Filing date is day resolution, not first-publication intraday timestamp"],
            "metrics":metrics,"companies":entries}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--index",required=True);p.add_argument("--out",required=True)
    p.add_argument("--asof",default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    args=p.parse_args()
    result={"status":"unavailable","reason":"SEC EPS facts have not been retrieved","companies":{}}
    try:
        if "@" not in UA:raise RuntimeError("SEC_USER_AGENT not configured")
        ix=json.load(open(args.index,encoding="utf-8"))
        known={str(x.get("ticker","")).upper():x.get("cik") for x in ix.get("companies",[])}
        tickers=[t for t in TARGET_TICKERS if known.get(t)]
        data={}
        for tic in tickers:
            cik=int(known[tic])
            u=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
            try:
                req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept-Encoding":"gzip, deflate"})
                with urllib.request.urlopen(req,timeout=12) as resp:
                    raw=resp.read()
                    if resp.headers.get("Content-Encoding")=="gzip":
                        import gzip
                        raw=gzip.decompress(raw)
                    j=json.loads(raw)
                entries=sec_eps(j)
                if entries:data[tic]=entries
                print(tic,len(entries),flush=True)
            except Exception as exc: print(f"::warning::SEC EPS {tic}: {str(exc)[:120]}",flush=True)
            time.sleep(.16)
        if data:result=learn(data,args.asof)
        else:result={"status":"unavailable","reason":"SEC EPS Company Facts could not be retrieved",
                     "companies":{}}
        result["sample_tickers_requested"]=tickers
        result["sample_tickers_loaded"]=list(data)
    except Exception as exc:
        result={"status":"unavailable","reason":str(exc)[:200],"companies":{}}
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("EPS",result.get("status"),len(result.get("companies",{})),flush=True)

if __name__=="__main__":main()
