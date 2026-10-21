"""SEC GAAP diluted EPS point-in-time filing-series collector and walk-forward research.

Only direct 70-110 day USD/shares EarningsPerShareDiluted records. Earliest 10-Q/10-K
filing within 200 days of quarter end is retained; never use later restatements.
Prediction origin for historical Q[i] is the day AFTER prior-quarter SEC filing.
Adjusted/Street EPS and SEC GAAP EPS are deliberately NOT mixed.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path

from . import sec

TAG = "EarningsPerShareDiluted"
MIN_TRAIN = 7


def iso(x):
    return dt.date.fromisoformat(str(x)[:10])


def direct_eps(companyfacts):
    rows = (companyfacts.get("facts", {}).get("us-gaap", {}).get(TAG, {})
            .get("units", {}).get("USD/shares", []))
    out = {}
    for f in rows:
        if not all(k in f for k in ("start", "end", "filed", "val")):
            continue
        if f.get("form") not in ("10-Q", "10-K"):
            continue
        try:
            days = (iso(f["end"]) - iso(f["start"])).days
            lag = (iso(f["filed"]) - iso(f["end"])).days
            value = float(f["val"])
        except (TypeError, ValueError, OverflowError):
            continue
        if not 70 <= days <= 110 or not 0 <= lag <= 200 or not math.isfinite(value):
            continue
        end = f["end"]
        obj = {"end": end, "start": f["start"], "filed": f["filed"],
               "eps": value, "form": f["form"], "accn": f.get("accn", ""),
               "source": sec.companyfacts_url(companyfacts.get("cik", 0))}
        old = out.get(end)
        if old is None or (obj["filed"], obj["accn"]) < (old["filed"], old["accn"]):
            out[end] = obj
    return sorted(out.values(), key=lambda x: x["end"])


def yearago(rows, end):
    """Last-year comparable reported quarter (direct GAAP EPS), with date tolerance."""
    t=iso(end)
    candidates=[r for r in rows if 320 <= (t-iso(r["end"])).days <= 410]
    return min(candidates,key=lambda r:abs((t-iso(r["end"])).days-365)) if candidates else None


def add_months(t, k):
    import calendar
    yy=t.year+(t.month-1+k)//12
    mm=(t.month-1+k)%12+1
    return dt.date(yy,mm,min(t.day,calendar.monthrange(yy,mm)[1]))


def latest_growth(rows):
    for r in reversed(rows):
        p=yearago(rows,r["end"])
        if p and iso(p["filed"]) < iso(r["filed"]):
            return r["eps"]-p["eps"]
    return None


def fit_alpha(rows):
    """Stage-aware shrinkage of the latest known YoY EPS delta."""
    pairs=[]
    for j in range(6,len(rows)):
        hist=rows[:j]
        prev=yearago(hist,rows[j]["end"])
        trend=latest_growth(hist)
        if prev is None or trend is None:continue
        scale=max(.25,sum(abs(x["eps"]) for x in hist[-8:])/min(8,len(hist)))
        pairs.append((max(-8,min(8,trend/scale)),
                      max(-8,min(8,(rows[j]["eps"]-prev["eps"])/scale))))
    ridge=max(1.,len(pairs)*.2)
    coef=(sum(x*y for x,y in pairs)+.5*ridge)/(sum(x*x for x,y in pairs)+ridge)
    return max(-.5,min(1.5,coef)),len(pairs)


def estimate(rows, target_end, coef):
    old=yearago(rows,target_end)
    growth=latest_growth(rows)
    if old is None or growth is None:return None
    # First-filed SEC data can mix pre/post split EPS (e.g. 10:1).
    # Unless matching share-count evidence exists, ABSTAIN rather than fit a
    # spurious growth rate on per-share figures in incompatible regimes.
    last=rows[-3:]
    magnitudes=sorted(abs(x["eps"]) for x in last)
    typical=magnitudes[len(magnitudes)//2]
    if typical>.1 and abs(old["eps"])>4*typical:
        return None
    # Heavy-tailed changes require stronger regularisation, not infinite EPS.
    cap=2.0*max(abs(old["eps"]),typical,.5)
    projected=old["eps"]+max(-cap,min(cap,coef*growth))
    return projected,old["eps"]


def model(seq, cutoff, target_end=None):
    """PIT forecast on sparse first-filed quarterly tags; missing direct Q4 is not fabricated."""
    known=sorted((x for x in seq if iso(x["filed"]) < iso(cutoff)),
                 key=lambda x:x["end"])
    if len(known)<MIN_TRAIN:return None
    if target_end is None:
        for months in (3,6,9,12):
            target=add_months(iso(known[-1]["end"]),months).isoformat()
            if (iso(cutoff)-iso(target)).days<=90 and yearago(known,target):
                target_end=target;break
    if target_end is None:return None
    coef,n=fit_alpha(known)
    p=estimate(known,target_end,coef)
    if p is None:return None
    pred,baseline=p
    errors=[]
    for j in range(7,len(known)):
        old=known[:j]
        pastcoef,_=fit_alpha(old)
        test=estimate(old,known[j]["end"],pastcoef)
        if test is not None:errors.append(known[j]["eps"]-test[0])
    return {"eps_point":round(pred,4),"target_end":target_end,"lag4_eps":baseline,
            "lag1_eps":known[-1]["eps"],"coefficient_trend":round(coef,4),
            "train_quarters":len(known),"training_examples":n,
            "last_filed":known[-1]["filed"],"uncertainty":uncertainty(pred,errors,baseline),
            "basis":"SEC_GAAP_DILUTED_EPS","method":"SPARSE_YEAR_AGO_TREND_SHRINKAGE_WITH_SPLIT_GUARD"}


def model_point(known,cutoff,alpha):
    rows=sorted((x for x in known if iso(x["filed"])<iso(cutoff)),key=lambda x:x["end"])
    if not rows:return None
    target=add_months(iso(rows[-1]["end"]),3).isoformat()
    v=estimate(rows,target,alpha)
    return v[0] if v else None


def uncertainty(pred,residual,baseline):
    if len(residual)<10:
        return {"status":"INSUFFICIENT_CALIBRATION","n":len(residual),
                "p10":None,"p90":None,"p_yoy_growth":None}
    x=sorted(residual)
    lo=x[max(0,math.ceil((len(x)+1)*.10)-1)]
    hi=x[min(len(x)-1,math.ceil((len(x)+1)*.90)-1)]
    return {"status":"EMPIRICAL_RESIDUAL_RANGE_NOT_PROVEN_CALIBRATED",
            "n":len(x),"p10":round(pred+lo,4),"p90":round(pred+hi,4),
            "p_yoy_growth":round(sum(pred+r>baseline for r in residual)/len(residual),4)}


def backtest(seq,year=2025):
    ordered=sorted(seq,key=lambda x:x["end"])
    rows=[]
    for j in range(8,len(ordered)):
        tgt=ordered[j]
        if year is not None and iso(tgt["end"]).year!=year:continue
        cutoff=(iso(ordered[j-1]["filed"])+dt.timedelta(days=1)).isoformat()
        if iso(tgt["filed"])<=iso(cutoff):continue
        m=model(ordered[:j],cutoff,target_end=tgt["end"])
        if not m:continue
        rows.append({"quarter_end":tgt["end"],"as_of":cutoff,
                     "actual":tgt["eps"],"prediction":m["eps_point"],
                     "seasonal":m["lag4_eps"],"source_filed":tgt["filed"]})
    n=len(rows)
    return {"year":year,"n":n,"rows":rows,
            "model_mae":round(sum(abs(x["actual"]-x["prediction"]) for x in rows)/n,4) if n else None,
            "seasonal_mae":round(sum(abs(x["actual"]-x["seasonal"]) for x in rows)/n,4) if n else None,
            "status":"FIRST_FILED_SEC_GAAP_RETROSPECTIVE_WALK_FORWARD_SPARSE_Q4"}


def read(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError):return default


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")


def run(args):
    site=read(args.index,{}); allc=site.get("companies",[])
    candidates={str(x.get("cik")):x for x in allc if x.get("cik") and x.get("ticker")}
    store=Path(args.store)/"eps-gaap"
    fundamentals=Path(args.store)/"eps-fundamental"
    progress=read(store/"progress.json",{"cursor":0})
    # Prioritize AAPL and a round-robin: all collected companies remain available.
    priority=["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","JPM","WMT"]
    keys=sorted(candidates,key=lambda x:(
        0 if candidates[x].get("ticker") in priority else 1,
        priority.index(candidates[x]["ticker"]) if candidates[x].get("ticker") in priority else int(x)))
    if not keys: return
    picks=[]; pos=int(progress.get("cursor",0)) % len(keys)
    for _ in range(min(int(args.max_fetch),len(keys))):
        k=keys[pos];picks.append(k);pos=(pos+1)%len(keys)
    progress["cursor"]=pos
    now=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).date().isoformat()
    for cik in picks:
        try:
            facts=sec.get_json(sec.companyfacts_url(cik))
            seq=direct_eps(facts)
            if seq:write(store/(cik+".json"),{"records":seq,"updated_at":now})
            # Reuse the SAME SEC HTTP result; don't issue a duplicate network request.
            # Store all original first-filed facts and timestamps before training.
            from .eps_fundamental import quarterly
            fundamental_rows=quarterly(facts)
            if fundamental_rows:
                write(fundamentals/(cik+".json"),{
                    "cik":int(cik),"ticker":candidates[cik]["ticker"],
                    "quarters":fundamental_rows,"updated_at":now})
        except Exception as exc:
            print(f"::warning::GAAP EPS CIK {cik}: {str(exc)[:120]}",flush=True)
    write(store/"progress.json",progress)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    tests=[]
    for f in store.glob("*.json"):
        if f.stem=="progress" or f.stem not in candidates:continue
        series=read(f,{}).get("records",[])
        live=model(series,now)
        bt=backtest(series,2025)
        tests.extend([{**x,"ticker":candidates[f.stem].get("ticker")} for x in bt["rows"]])
        write(out/(f.stem+".json"),{"cik":int(f.stem),"ticker":candidates[f.stem]["ticker"],
              "as_of":now,"source":"SEC XBRL companyfacts earliest filing",
              "forecast":live,"backtest":{k:v for k,v in bt.items() if k!="rows"}})
    n=len(tests)
    write(out/"backtest.json",{"as_of":now,"year":2025,"n":n,"sample":"COLLECTED_COMPANIES_ONLY",
        "status":"SEC_FIRST_FILED_WALK_FORWARD_NO_POSTHOC_EXCLUSION",
        "model_mae":round(sum(abs(x["actual"]-x["prediction"]) for x in tests)/n,4) if n else None,
        "baseline_mae":round(sum(abs(x["actual"]-x["seasonal"]) for x in tests)/n,4) if n else None})
    print(f"GAAP EPS: fetched {len(picks)}, published {len(list(out.glob('*.json')))-1} companies, 2025 evaluated {n}")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--store",default="store")
    parser.add_argument("--index",default="_site/data/index.json")
    parser.add_argument("--out",default="_site/data/eps-gaap")
    parser.add_argument("--max-fetch",type=int,default=4)
    run(parser.parse_args())
