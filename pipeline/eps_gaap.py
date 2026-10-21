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


def model(seq, cutoff):
    """Fit autoregressive slope on training labels available strictly before cutoff."""
    known = [x for x in seq if iso(x["filed"]) < iso(cutoff)]
    known.sort(key=lambda x: x["end"])
    if len(known) < MIN_TRAIN:
        return None
    # Require stable fiscal-quarter sequence: four quarter index positions really one year.
    def consecutive(a,b):
        return 65 <= (iso(b["end"])-iso(a["end"])).days <= 115
    if not all(consecutive(a,b) for a,b in zip(known[-6:],known[-5:])):
        return None
    scale = max(.25, sum(abs(x["eps"]) for x in known[-8:]) / min(8,len(known)))
    examples = []
    for j in range(5,len(known)):
        if not all(consecutive(known[k],known[k+1]) for k in range(j-5,j)):
            continue
        examples.append((max(-8,min(8,(known[j-1]["eps"]-known[j-5]["eps"])/scale)),
                         max(-8,min(8,(known[j]["eps"]-known[j-4]["eps"])/scale))))
    ridge = max(1.,len(examples)*.2)
    alpha=(sum(x*y for x,y in examples)+ridge*.5)/(sum(x*x for x,y in examples)+ridge)
    alpha=max(-.5,min(1.5,alpha))
    baseline=known[-4]["eps"]
    pred=baseline+alpha*(known[-1]["eps"]-known[-5]["eps"])
    # Errors estimated using prior-only recursive predictions; no target leakage.
    residual=[]
    for j in range(7,len(known)):
        origin=iso(known[j-1]["filed"])+dt.timedelta(days=1)
        prev=model_point(known[:j],origin,alpha)
        if prev is not None:
            residual.append(known[j]["eps"]-prev)
    return {"eps_point": round(pred,4),"lag4_eps":baseline,"lag1_eps":known[-1]["eps"],
            "coefficient_trend":round(alpha,4),"train_quarters":len(known),
            "training_examples":len(examples),"last_filed":known[-1]["filed"],
            "uncertainty":uncertainty(pred,residual,baseline),"basis":"SEC_GAAP_DILUTED_EPS"}


def model_point(known,cutoff,alpha):
    before=[x for x in known if iso(x["filed"])<iso(cutoff)]
    if len(before)<5:return None
    return before[-4]["eps"]+alpha*(before[-1]["eps"]-before[-5]["eps"])


def uncertainty(pred,residual,baseline):
    # Conformal interval with one-sided empirical tails only if >=10 prior errors.
    if len(residual)<10:
        return {"status":"INSUFFICIENT_CALIBRATION","n":len(residual),
                "p10":None,"p90":None,"p_yoy_growth":None}
    x=sorted(residual)
    lo=x[max(0,math.ceil((len(x)+1)*.10)-1)]
    hi=x[min(len(x)-1,math.ceil((len(x)+1)*.90)-1)]
    return {"status":"EMPIRICAL_RESIDUAL_RANGE_NOT_PROVEN_CALIBRATED","n":len(x),
            "p10":round(pred+lo,4),"p90":round(pred+hi,4),
            "p_yoy_growth":round(sum(pred+r>baseline for r in residual)/len(residual),4)}


def backtest(seq,year=2025):
    """All predictions built with filings already public at prior filing + 1 day."""
    ordered=sorted(seq,key=lambda x:x["end"])
    rows=[]
    for j in range(8,len(ordered)):
        tgt=ordered[j]
        if iso(tgt["end"]).year!=year:continue
        cutoff=iso(ordered[j-1]["filed"])+dt.timedelta(days=1)
        if iso(tgt["filed"])<=cutoff:continue
        m=model(ordered[:j],cutoff)
        if not m:continue
        rows.append({"quarter_end":tgt["end"],"as_of":cutoff.isoformat(),
                     "actual":tgt["eps"],"prediction":m["eps_point"],
                     "seasonal":ordered[j-4]["eps"],"source_filed":tgt["filed"]})
    n=len(rows)
    return {"year":year,"n":n,"rows":rows,
            "model_mae":round(sum(abs(x["actual"]-x["prediction"]) for x in rows)/n,4) if n else None,
            "seasonal_mae":round(sum(abs(x["actual"]-x["seasonal"]) for x in rows)/n,4) if n else None,
            "status":"FIRST_FILED_SEC_GAAP_RETROSPECTIVE_WALK_FORWARD"}


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
