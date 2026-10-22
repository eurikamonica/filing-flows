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
    """First-filed quarterly diluted EPS: as tagged for the quarter, or a fourth quarter derived from the 10-K (fiscal
    year less nine months), checked against net income / diluted shares and the company's usual size
    (eps_fundamental.quarterly), and restated across stock splits. Each record keeps its own filing date."""
    from .eps_fundamental import quarterly
    out = []
    for r in quarterly(companyfacts):
        e = r["fields"].get("eps")
        if not e:
            continue
        sh = (r["fields"].get("diluted_shares") or {}).get("val")
        out.append({"end": r["end"], "start": e.get("start"), "filed": e["filed"], "eps": e["val"],
                    "form": e.get("form") or ("10-K" if e.get("derived") else "10-Q"), "accn": e.get("accn", ""),
                    "source": sec.companyfacts_url(companyfacts.get("cik", 0)), **({"derived": True} if e.get("derived") else {}),
                    **({"shares": sh} if sh else {})})
    return split_records(out)


def split_records(rows):
    """EPS restated across stock splits seen in the diluted share count (eps_fundamental.split_adjusted)."""
    from .eps_fundamental import SPLITS
    rows = [dict(r) for r in rows]
    for i in range(len(rows) - 1, 0, -1):
        a, b = rows[i - 1].get("shares"), rows[i].get("shares")
        if not a or not b:
            continue
        r = b / a
        k = next((x for x in SPLITS if abs(r / x - 1) < .04), None) or next((1 / x for x in SPLITS if abs(r * x - 1) < .04), None)
        if k:
            for row in rows[:i]:
                row["eps"] = row["eps"] / k
                if row.get("shares"):
                    row["shares"] = row["shares"] * k
                row["split_adjusted"] = round(k, 4)
    return rows


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


def model(seq, cutoff, target_end=None, residuals=True):
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
    for j in range(7,len(known) if residuals else 7):    # the walk-forward residuals only for a live forecast
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


def scale_of(prior):
    """The size of a company's EPS for relative errors: the mean |EPS| of its four quarters before the target."""
    last = [abs(x) for x in prior[-4:]]
    return max(0.10, sum(last) / len(last)) if last else 0.25


def summary(rows, pred="prediction", base="seasonal"):
    """Errors of a forecast against a baseline, robust to the odd huge figure: median absolute error, mean relative
    error (|error| / the company's usual |EPS|, capped at 5) and how often the forecast was the closer one. The plain
    mean absolute error in dollars is kept but is dominated by a few high-EPS companies."""
    rows = [r for r in rows if r.get(pred) is not None and r.get(base) is not None and r.get("actual") is not None]
    n = len(rows)
    if not n:
        return {"n": 0}
    ea = [abs(r[pred] - r["actual"]) for r in rows]
    eb = [abs(r[base] - r["actual"]) for r in rows]
    rel = lambda e, r: min(e / (r.get("scale") or max(0.10, abs(r["actual"]))), 5)
    med = lambda a: sorted(a)[len(a) // 2] if len(a) % 2 else (sorted(a)[len(a) // 2 - 1] + sorted(a)[len(a) // 2]) / 2
    return {"n": n, "median_ae_model": round(med(ea), 4), "median_ae_baseline": round(med(eb), 4),
            "rel_error_model": round(sum(rel(e, r) for e, r in zip(ea, rows)) / n, 4),
            "rel_error_baseline": round(sum(rel(e, r) for e, r in zip(eb, rows)) / n, 4),
            "closer_share": round(sum(x < y for x, y in zip(ea, eb)) / n, 4),
            "mae_model": round(sum(ea) / n, 4), "mae_baseline": round(sum(eb) / n, 4)}


def backtest(seq, year=None, years=(2023, 2024, 2025, 2026)):
    """Walk-forward: each quarter forecast the day after the previous quarter was filed, from the filings public then."""
    ordered = sorted(seq, key=lambda x: x["end"])
    rows = []
    for j in range(8, len(ordered)):
        tgt = ordered[j]
        y = iso(tgt["end"]).year
        if (year is not None and y != year) or (year is None and y not in years):
            continue
        cutoff = (iso(ordered[j - 1]["filed"]) + dt.timedelta(days=1)).isoformat()
        if iso(tgt["filed"]) <= iso(cutoff):
            continue
        m = model(ordered[:j], cutoff, target_end=tgt["end"], residuals=False)
        if not m:
            continue
        prior = [x["eps"] for x in ordered[:j] if iso(x["filed"]) < iso(cutoff)]
        rows.append({"quarter_end": tgt["end"], "as_of": cutoff, "actual": tgt["eps"], "prediction": m["eps_point"],
                     "seasonal": m["lag4_eps"], "source_filed": tgt["filed"], "scale": round(scale_of(prior), 4),
                     **({"derived": True} if tgt.get("derived") else {})})
    out = {"year": year, "years": list(years) if year is None else [year], "rows": rows, **summary(rows),
           "status": "FIRST_FILED_SEC_GAAP_WALK_FORWARD_Q4_DERIVED_FROM_10K"}
    out["model_mae"], out["seasonal_mae"] = out.get("mae_model"), out.get("mae_baseline")
    return out


def gate(bt, min_n=6):
    """Show the seasonal model's forecast only where, walked forward on this company's own filings, it beat
    "same quarter last year" on relative error; otherwise the year-ago figure is the reference."""
    ok = bt.get("n", 0) >= min_n and bt["rel_error_model"] < bt["rel_error_baseline"]
    return {"status": "PASSED" if ok else ("TOO_FEW_TESTS" if bt.get("n", 0) < min_n else "YEAR_AGO_BETTER"),
            "n": bt.get("n", 0), "rel_error_model": bt.get("rel_error_model"), "rel_error_year_ago": bt.get("rel_error_baseline")}


def read(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError):return default


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")


def save_from_facts(root, cik, facts, ticker=None, today=None):
    """Keep a company's EPS series from a companyfacts download (the main scan calls this for every company it
    fetches, so the EPS store fills without extra requests): store/eps-gaap/<cik>.json (EPS) and
    store/eps-fundamental/<cik>.json (the income statement lines the fundamental model uses)."""
    from .eps_fundamental import quarterly, SERIES_V
    today = today or dt.date.today().isoformat()
    cik = str(int(cik))
    q = quarterly(facts)
    if not q:
        return False
    recs = direct_eps(facts)
    last = max((r["fields"][k]["filed"] for r in q for k in r["fields"]), default=None)
    gpath, fpath = Path(root) / "eps-gaap" / f"{cik}.json", Path(root) / "eps-fundamental" / f"{cik}.json"
    ticker = ticker or read(fpath, {}).get("ticker")
    if recs:
        write(gpath, {"records": recs, "updated_at": today, "v": SERIES_V, "last_filed": last})
    write(fpath, {"cik": int(cik), "ticker": ticker, "quarters": q, "updated_at": today, "v": SERIES_V, "last_filed": last})
    return True


def run(args):
    site = read(args.index, {})
    allc = site.get("companies", [])
    info = {}
    for x in allc:                                   # one entry per company: its newest filing and revenue
        if not x.get("cik") or not x.get("ticker"):
            continue
        k = str(x["cik"])
        cur = info.get(k)
        if cur is None or (x.get("filed") or "") > (cur.get("filed") or ""):
            info[k] = x
    store = Path(args.store) / "eps-gaap"
    from .eps_fundamental import SERIES_V
    now = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).date().isoformat()
    todo = []
    for k, x in info.items():                        # never read, read before this version, or a newer filing since
        f = read(Path(args.store) / "eps-fundamental" / f"{k}.json", {})
        stale = f.get("v") != SERIES_V or not f.get("last_filed") or (x.get("filed") or "") > f["last_filed"]
        if stale:
            todo.append((0 if f.get("v") != SERIES_V else 1, -(x.get("revenue") or 0), k))
    todo.sort()
    import time
    t0, fetched = time.monotonic(), 0
    for _, _, k in todo[: int(args.max_fetch)]:
        if time.monotonic() - t0 > args.budget:
            break
        try:
            facts = sec.get_json(sec.companyfacts_url(k))
            save_from_facts(args.store, k, facts, info[k].get("ticker"), now)
            fetched += 1
        except Exception as exc:
            print(f"::warning::GAAP EPS CIK {k}: {str(exc)[:120]}", flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tests, published, shown = [], 0, 0
    for f in store.glob("*.json"):
        if f.stem == "progress" or f.stem not in info:
            continue
        series = read(f, {}).get("records", [])
        live = model(series, now)
        bt = backtest(series)
        g = gate(bt)
        tests.extend([{**x, "ticker": info[f.stem].get("ticker")} for x in bt["rows"]])
        ref = None
        if live:
            ref = {"target_end": live["target_end"], "year_ago_eps": live["lag4_eps"], "last_eps": live["lag1_eps"]}
            if g["status"] != "PASSED":
                live = None
            else:
                shown += 1
        write(out / (f.stem + ".json"), {"cik": int(f.stem), "ticker": info[f.stem]["ticker"], "as_of": now,
              "source": "SEC XBRL companyfacts, first filed", "forecast": live, "reference": ref, "gate": g,
              "backtest": {k: v for k, v in bt.items() if k != "rows"}})
        published += 1
    s = summary(tests)
    write(out / "backtest.json", {"as_of": now, "years": [2023, 2024, 2025, 2026], "sample": "COLLECTED_COMPANIES_ONLY",
          "status": "SEC_FIRST_FILED_WALK_FORWARD_NO_POSTHOC_EXCLUSION", **s,
          "baseline": "same quarter last year", "model_mae": s.get("mae_model"), "baseline_mae": s.get("mae_baseline")})
    print(f"GAAP EPS: fetched {fetched} ({len(todo)} waiting), published {published} companies, "
          f"forecast shown for {shown} (beat year-ago); walk-forward {s.get('n', 0)} quarters")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--store",default="store")
    parser.add_argument("--index",default="_site/data/index.json")
    parser.add_argument("--out",default="_site/data/eps-gaap")
    parser.add_argument("--max-fetch",type=int,default=150)
    parser.add_argument("--budget",type=float,default=240,help="seconds of downloading per run")
    run(parser.parse_args())
