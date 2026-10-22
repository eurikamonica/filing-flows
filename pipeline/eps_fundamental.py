"""SEC first-filed, fundamental-led quarterly GAAP EPS forecasting.

Only original direct-quarter XBRL values; market/13F/FRED inputs are NOT silently
mixed into trained EPS parameters. Event overlays require dated, sourced evidence.
All backtest origins precede their target filing. Uncertainty is *empirical and
uncalibrated* unless coverage has separately been verified.
"""
import argparse
import datetime as dt
import json
import math
import statistics
from pathlib import Path

from .eps_gaap import iso, read, write, yearago, add_months

TAGS = {
    # each quarter takes the first tag (in this order) that has it; revenue takes the largest, so a company that moved
    # from SalesRevenueNet to the ASC 606 tag, or tags a subset under one of them, keeps its total
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet", "RevenuesNetOfInterestExpense"),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
    "tax_expense": ("IncomeTaxExpenseBenefit",),
    "net_income": ("NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"),
    # basic figures only where a quarter has no diluted one (Berkshire reports basic only)
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
                       "WeightedAverageNumberOfSharesOutstandingBasic"),
    "eps": ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"),
}
UNITS = {x: "shares" if x == "diluted_shares" else "USD/shares" if x == "eps" else "USD" for x in TAGS}
FLOWS = ("revenue", "operating_income", "pretax_income", "tax_expense", "net_income")
MIN_HISTORY = 8
SERIES_V = 2                   # quarterly(): per-quarter tag fallback, derived fourth quarters, checked EPS


def med(values, default=None):
    a=[float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(a) if a else default


def bound(x, lo, hi):
    return max(lo,min(hi,x))


def _days(start, end):
    return (iso(end) - iso(start)).days


def _periods(raw, tag, unit):
    """{(start, end): first-filed fact} of one tag from 10-Q/10-K filings, filed within 200 days of the period end."""
    out = {}
    for x in raw.get(tag, {}).get("units", {}).get(unit, []):
        if x.get("form") not in ("10-Q", "10-K") or not all(k in x for k in ("start", "end", "filed", "val")):
            continue
        try:
            lag = (iso(x["filed"]) - iso(x["end"])).days
            v = float(x["val"])
            _days(x["start"], x["end"])
        except (ValueError, TypeError, OverflowError):
            continue
        if not (0 <= lag <= 200 and math.isfinite(v)):
            continue
        r = {"val": v, "filed": x["filed"], "accn": x.get("accn", ""), "form": x["form"], "start": x["start"]}
        key = (x["start"], x["end"])
        old = out.get(key)
        if old is None or (r["filed"], r["accn"]) < (old["filed"], old["accn"]):
            out[key] = r
    return out


def _quarters_of(per, field):
    """Direct quarters {end: fact} and fourth quarters derived from the 10-K: {end: fact}. A fourth quarter is the
    fiscal year less the nine months to the third quarter (same start), both as first filed; it is public on the
    10-K's filing date, so a forecast made before then never sees it. Shares are weighted by days; EPS is the
    year's less the nine months' (the convention analysts use; checked against net income / shares later)."""
    direct, fy, nine = {}, [], {}
    for (s, e), r in per.items():
        d = _days(s, e)
        if 70 <= d <= 125:                            # 16-week quarters (Costco, Kroger) included
            old = direct.get(e)
            if old is None or r["filed"] < old["filed"]:
                direct[e] = r
        elif 350 <= d <= 380 and r["form"] == "10-K":
            fy.append((s, e, r))
        elif 250 <= d <= 290:
            nine[(s, e)] = r
    derived = {}
    for s, e, r in fy:
        if e in direct:
            continue
        cand = [(k, v) for k, v in nine.items() if abs(_days(k[0], s)) <= 7 and 80 <= _days(k[1], e) <= 125 and v["filed"] <= r["filed"]]
        if not cand:
            continue
        (s9, e9), r9 = min(cand, key=lambda kv: kv[1]["filed"])
        dq = _days(e9, e)
        if field == "diluted_shares":
            v = (r["val"] * _days(s, e) - r9["val"] * _days(s9, e9)) / dq
            if not (0.5 * r9["val"] <= v <= 2 * r9["val"]):
                continue
        else:
            v = r["val"] - r9["val"]
        derived[e] = {"val": v, "filed": r["filed"], "accn": r["accn"], "form": "10-K", "derived": True,
                      "start": (iso(e9) + dt.timedelta(days=1)).isoformat()}
    return direct, derived


def quarterly(facts):
    """First-filed quarterly figures per fiscal quarter: [{"end", "fields": {field: {val, filed, tag, accn, start,
    derived?}}}]. Each quarter takes the first tag that has it (revenue the largest), a fourth quarter not tagged on its
    own is derived from the 10-K, and an EPS figure that disagrees with net income / diluted shares, or is fifty times
    the company's usual size, is dropped (a scale or tagging error in the filing)."""
    raw = facts.get("facts", {}).get("us-gaap", {})
    byfield = {}
    for field, tags in TAGS.items():
        best = {}
        for tag in tags:
            per = _periods(raw, tag, UNITS[field])
            if not per:
                continue
            direct, derived = _quarters_of(per, field)
            for kind, got in ((0, direct), (1, derived)):
                for end, r in got.items():
                    if field == "diluted_shares" and not (1e3 < r["val"] < 1e13):
                        continue
                    cand = (kind, {**r, "tag": tag})
                    old = best.get(end)
                    if old is None or kind < old[0] or (kind == old[0] and field == "revenue" and r["val"] > old[1]["val"]):
                        best[end] = cand              # a direct figure over a derived one; else the first tag (revenue: largest)
        byfield[field] = {e: r for e, (_, r) in best.items()}
    quarters = []
    ends = sorted(set().union(*(set(v) for v in byfield.values()))) if byfield else []
    for end in ends:
        f = {field: dict(rec[end]) for field, rec in byfield.items() if end in rec}
        if "pretax_income" not in f and "net_income" in f and "tax_expense" in f:
            f["pretax_income"] = {"val": f["net_income"]["val"] + f["tax_expense"]["val"], "computed": True, "tag": "NetIncome+Tax",
                                  "filed": max(f["net_income"]["filed"], f["tax_expense"]["filed"]), "accn": f["net_income"]["accn"]}
        if "diluted_shares" not in f and "net_income" in f and "eps" in f and abs(f["eps"]["val"]) >= 0.01:
            sh = f["net_income"]["val"] / f["eps"]["val"]         # shares the EPS implies (Exxon tags no share count)
            if 1e3 < sh < 1e13:
                f["diluted_shares"] = {"val": sh, "computed": True, "tag": "NetIncome/EPS", "accn": f["eps"]["accn"],
                                       "filed": max(f["net_income"]["filed"], f["eps"]["filed"]), "derived": f["eps"].get("derived")}
        if "eps" not in f and "net_income" in f and "diluted_shares" in f and f["diluted_shares"]["val"] > 0:
            f["eps"] = {"val": round(f["net_income"]["val"] / f["diluted_shares"]["val"], 4), "computed": True, "tag": "NetIncome/Shares",
                        "filed": max(f["net_income"]["filed"], f["diluted_shares"]["filed"]), "accn": f["net_income"]["accn"],
                        "derived": f["net_income"].get("derived") or f["diluted_shares"].get("derived")}
        if "eps" in f and "net_income" in f and "diluted_shares" in f and f["diluted_shares"]["val"] > 0:
            calc = f["net_income"]["val"] / f["diluted_shares"]["val"]
            if abs(calc - f["eps"]["val"]) > max(0.15, 0.35 * abs(f["eps"]["val"]), 0.35 * abs(calc)):
                f.pop("eps")                         # EPS and net income / shares disagree: a units or tagging error
        row = {"end": end, "fields": f, "source": "SEC_COMPANYFACTS_FIRST_FILED"}
        if any(x.get("derived") for x in f.values()):
            row["derived"] = True
        quarters.append(row)
    eps = [abs(q["fields"]["eps"]["val"]) for q in quarters if "eps" in q["fields"]]
    if eps:
        typical = max(statistics.median(eps), 0.01)
        for q in quarters:
            e = q["fields"].get("eps")
            if e and (abs(e["val"]) > 50 * typical or abs(e["val"]) > 1e5):
                q["fields"].pop("eps")
    return quarters


def observations(series,cutoff):
    """Only entirely public quarterly records; joins demand same fiscal end."""
    result=[]
    for row in series:
        fields=row.get("fields",{})
        # operating income is optional: banks and insurers do not report it, so their path runs on pretax income
        need=("revenue","tax_expense","net_income","diluted_shares","eps")
        if any(k not in fields for k in need):continue
        use=need+tuple(k for k in ("operating_income","pretax_income") if k in fields)
        if any(iso(fields[k]["filed"]) >= iso(cutoff) for k in use):continue
        try:
            v={k:float(fields[k]["val"]) for k in use}
        except (ValueError,KeyError,TypeError):continue
        if not all(math.isfinite(x) for x in v.values()):continue
        if v["revenue"]<=0 or v["diluted_shares"]<=1000:continue
        if "pretax_income" not in v:v["pretax_income"]=v["net_income"]+v["tax_expense"]
        if "operating_income" not in v:v["operating_income"]=v["pretax_income"]   # the pretax path: no other income line
        v["derived"]=bool(row.get("derived"))
        # Verify reported GAAP EPS and net income/share count are compatible.
        # Some filers include noncontrolling interests or have split regimes: abstain.
        calc=v["net_income"]/v["diluted_shares"]
        if abs(calc-v["eps"])>max(.25,.30*abs(v["eps"])):continue
        # Reject observations in which units or large share-regime shifts are dubious.
        result.append({**v,"end":row["end"],
          "filed":max(fields[k]["filed"] for k in use),
          "source_tags":{k:fields[k].get("tag") for k in use}})
    return split_adjusted(sorted(result,key=lambda z:z["end"]))


SPLITS = (2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50)


def split_adjusted(rows):
    """Per-share history on today's share basis: where the diluted share count jumps between two quarters by a split
    ratio (2-for-1 ... 50-for-1, or a reverse split), the earlier quarters' EPS and shares are restated by it, so a
    year-ago comparison does not mix the two regimes. Each row as first filed otherwise."""
    rows = [dict(r) for r in rows]
    for i in range(len(rows) - 1, 0, -1):
        a, b = rows[i - 1]["diluted_shares"], rows[i]["diluted_shares"]
        if a <= 0 or b <= 0:
            continue
        r = b / a
        k = next((x for x in SPLITS if abs(r / x - 1) < .04), None) or next((1 / x for x in SPLITS if abs(r * x - 1) < .04), None)
        if not k:
            continue
        for row in rows[:i]:
            row["eps"] /= k
            row["diluted_shares"] *= k
            row["split_adjusted"] = round(k, 4)
    return rows


def stage(history):
    """Regime classifier evaluated solely from prior published fundamentals."""
    recent=history[-8:]
    rev=[x["revenue"] for x in recent]
    mar=[x["operating_income"]/x["revenue"] for x in recent]
    grow=[]
    for r in recent:
        prev=yearago(history,r["end"])
        if prev and prev["revenue"]>0:grow.append(r["revenue"]/prev["revenue"]-1)
    if med([x["net_income"] for x in recent],0)<0 or med(mar,0)<0:
        return "loss_making"
    if len(mar)>=4 and statistics.pstdev(mar)>.12:
        return "cyclical"
    if med(grow,0)>.20:return "high_growth"
    if med(grow,0)<-.08:return "contracting"
    return "mature"


def tax_rate(history):
    """Normalize one-off tax spikes: do not use 2025 META charge as recurring rate."""
    rates=[]
    for r in history[-16:]:
        pre=r["pretax_income"];tx=r["tax_expense"]
        if pre>0 and -.05<=tx/pre<=.48:rates.append(tx/pre)
    return bound(med(rates,.21),0,.40)


def unusual_tax(history,rate):
    z=[]
    for row in history[-16:]:
        pre=row["pretax_income"]
        if pre<=0:continue
        r=row["tax_expense"]/pre
        if r>.52 or r<-.15:
            z.append({"quarter":row["end"],"eps_impact":-(row["tax_expense"]-pre*rate)/row["diluted_shares"]})
    return z


def forecast(series,cutoff,target=None,events=(),allow_dist=False):
    hist=observations(series,cutoff)
    if len(hist)<MIN_HISTORY:return None
    guessed=target is None
    if target is None:
        latest=iso(hist[-1]["end"])
        target=add_months(latest,3).isoformat()
        # Do not silently skip an unsupported Q4 and label a more distant
        # quarter as the 'next reported' EPS forecast.
        if (iso(cutoff)-iso(target)).days>100 or yearago(hist,target) is None:
            return None
    if not target:return None
    yr=yearago(hist,target)
    if yr is None:return None
    if guessed:                       # the quarter's real end: a year after its year-ago quarter (52/53-week years too)
        prev=yearago(hist,hist[-1]["end"])
        step=(iso(hist[-1]["end"])-iso(prev["end"])).days if prev else 365
        target=(iso(yr["end"])+dt.timedelta(days=step if 360<=step<=372 else 365)).isoformat()
    recent=hist[-8:]
    st=stage(hist)
    rel=[r["revenue"]/yearago(hist,r["end"])["revenue"]-1 for r in recent
         if yearago(hist,r["end"]) and yearago(hist,r["end"])["revenue"]>0]
    if len(rel)<3:return None
    rg=bound(med(rel[-4:],0),-.65,1.25)
    # Stage-adaptive shrinkage of annual growth; cyclicals need seasonal anchor.
    strength={"loss_making":.35,"cyclical":.30,"high_growth":.75,
              "contracting":.40,"mature":.55}[st]
    rev=yr["revenue"]*(1+bound(strength*rg+(1-strength)*med(rel,0),-.65,1.5))
    margins=[r["operating_income"]/r["revenue"] for r in recent]
    mr=bound(med(margins[-4:],0),-1.5,1.5)
    m_y=yr["operating_income"]/yr["revenue"]
    margin=bound(.70*mr+.30*m_y,-1,1)
    # Nonoperating charges and other income are inferred from reported pretax less EBIT.
    nonop=bound(med([(r["pretax_income"]-r["operating_income"])/r["revenue"]
                   for r in recent],0),-.50,.50)
    rate=tax_rate(hist)
    pretax=rev*(margin+nonop)
    eps_pre=pretax*(1-rate if pretax>=0 else 1.0)
    # Shares: strictly prior diluted weighted-average counts, smooth extreme swings.
    ratios=[recent[i]["diluted_shares"]/recent[i-1]["diluted_shares"]-1
            for i in range(1,len(recent)) if recent[i-1]["diluted_shares"]>0]
    median_change=bound(med(ratios[-4:],0),-.025,.035)
    last_shares=hist[-1]["diluted_shares"]
    if yr["diluted_shares"]/last_shares>4 or last_shares/yr["diluted_shares"]>4:
        return None  # likely stock split, unverified regime
    shares=last_shares*(1+median_change)
    point=eps_pre/shares
    base_gaap=yr["eps"]
    # Past abnormal tax effects must be removed from last year's normalized EPS
    # BEFORE computing apples-to-apples growth; this is not a forecast charge.
    old_tax_extra=yr["tax_expense"]-yr["pretax_income"]*rate
    normalized_prior=base_gaap+old_tax_extra/yr["diluted_shares"]

    # Event overlays are allowed ONLY for documented public company-specific evidence.
    # 'eps_delta' is a confirmed post-tax per-share EPS effect, not guessed from headlines.
    confirmed=[]
    for event in events:
        try:
            if (event["target_end"]==target and iso(event["published_at"])<iso(cutoff)
                    and event.get("source_url","").startswith("https://")
                    and math.isfinite(float(event["eps_delta"]))):
                confirmed.append(event)
                point+=float(event["eps_delta"])
        except (KeyError,TypeError,ValueError):
            continue
    anomalies=unusual_tax(hist,rate)
    risk=min(.25,len(anomalies)/(len(hist)+8))
    event_effect=med([x["eps_impact"] for x in anomalies],0)
    if not math.isfinite(point) or abs(point)>1e5:return None
    vol=bound(statistics.pstdev(rel[-8:]) if len(rel)>1 else .08,.03,.35)
    mvol=bound(statistics.pstdev(margins[-8:]) if len(margins)>1 else .02,.012,.20)
    event_charge=min(0,event_effect) if anomalies else 0
    def eps_scenario(dr,dm,event=0):
        sales=max(0,rev*(1+dr))
        before=sales*(bound(margin+dm,-1,1)+nonop)
        return round(before*(1-rate if before>=0 else 1.)/shares+
                     sum(float(e["eps_delta"]) for e in confirmed)+event,4)
    out={"method":"FUNDAMENTAL_STAGE_EVENT_V1","basis":"SEC_GAAP_DILUTED_EPS",
         "target_end":target,"as_of":cutoff,"point":round(point,4),
         "company_stage":st,"inputs":{"revenue":round(rev,2),
             "operating_margin":round(margin,5),"nonoperating_margin":round(nonop,5),
             "normalized_tax_rate":round(rate,5),"diluted_shares":round(shares),
             "recent_revenue_yoy_median":round(med(rel[-4:],0),5)},
         "eps_gaap_last_year":base_gaap,
         "normalized_eps_last_year":round(normalized_prior,4),
         "predicted_eps_growth_gaap_yoy":round(point/abs(base_gaap)-1,4) if base_gaap>.05 else None,
         "predicted_eps_growth_normalized_yoy":round(point/normalized_prior-1,4)
                     if normalized_prior>.05 else None,
         "scenarios":{"bear":{"eps":eps_scenario(-vol,-mvol,event_charge),
                               "revenue_shock":-round(vol,4),"margin_shock":-round(mvol,4)},
                      "base":{"eps":round(point,4),"revenue_shock":0,"margin_shock":0},
                      "bull":{"eps":eps_scenario(vol,mvol),
                              "revenue_shock":round(vol,4),"margin_shock":round(mvol,4)},
                      "status":"HISTORICAL_DRIVER_STRESS_NOT_PROBABILITY_QUANTILES"},
         "quarters_train":len(hist),
         "confirmed_events":[{"published_at":e["published_at"],"source_url":e["source_url"],
                              "eps_delta":float(e["eps_delta"])} for e in confirmed],
         "event_risk":{"historical_tax_anomalies":len(anomalies),
                       "indicative_probability":round(risk,4),
                       "historical_median_eps_impact":round(event_effect,4)},
         "quality":"FUNDAMENTALS_WITH_PRIOR_DISCLOSURE_ONLY"}
    if allow_dist:
        # Walk-forward residual bootstrap without future labels, with tax-spike scenarios.
        errors=[]
        for j in range(max(8,len(hist)-36),len(hist)):
            prior=hist[:j]
            origin=(iso(prior[-1]["filed"])+dt.timedelta(days=1)).isoformat()
            estimate=forecast(series,origin,target=hist[j]["end"],allow_dist=False)
            if estimate and iso(hist[j]["filed"])>=iso(origin):
                errors.append(hist[j]["eps"]-estimate["point"])
        out["distribution"]=probability(point,yr["eps"],errors,risk,event_effect)
    return out


def quantile(a,p):
    values=sorted(a)
    if not values:return None
    k=(len(values)-1)*p
    lo=math.floor(k);hi=math.ceil(k)
    return values[lo]*(hi-k)+values[hi]*(k-lo) if hi!=lo else values[lo]


def probability(point,baseline,errors,event_risk=0,event_impact=0):
    """Deterministic posterior predictive empirical residual mixture, not calibrated."""
    if len(errors)<8:
        return {"status":"INSUFFICIENT_PRIOR_WALKFORWARD_RESIDUALS","n":len(errors),
                "p10":None,"p50":None,"p90":None,"p_yoy_increase":None}
    # Every historical residual is valid only after the original result was filed.
    samples=[point+e for e in errors]
    if event_risk>0 and event_impact!=0:
        # Deterministic allocation instead of random draws, bounded historical tax risk.
        n=min(len(samples),max(1,round(event_risk*len(samples))))
        samples=sorted(samples)
        for i in range(n):
            samples[i]+=event_impact
    return {"status":"EMPIRICAL_UNCALIBRATED","n":len(errors),
        "p10":round(quantile(samples,.10),4),
        "p50":round(quantile(samples,.50),4),
        "p90":round(quantile(samples,.90),4),
        "p_yoy_increase":round(sum(z>baseline for z in samples)/len(samples),4),
        "coverage_claim":False}


def backtest(series,years=(2023,2024,2025,2026)):
    """Walk-forward: each quarter forecast the day after the previous quarter was filed, from what was public then.
    rows: end, cutoff, filed, actual, forecast, year-ago, scale (the company's usual |EPS| then), stage."""
    eligible=observations(series,"2100-01-01")
    rows=[]
    for j in range(MIN_HISTORY,len(eligible)):
        target=eligible[j]
        if iso(target["end"]).year not in years:continue
        prior=eligible[:j]
        cutoff=(iso(prior[-1]["filed"])+dt.timedelta(days=1)).isoformat()
        if iso(target["filed"])<=iso(cutoff):continue
        y=forecast(series,cutoff,target=target["end"])
        if not y:continue
        last=[abs(x["eps"]) for x in prior[-4:]]
        rows.append({"end":target["end"],"cutoff":cutoff,"filed":target["filed"],
                     "actual":target["eps"],"forecast":y["point"],
                     "same_quarter_last_year":y["eps_gaap_last_year"],
                     "scale":round(max(.10,sum(last)/len(last)),4),
                     "stage":y["company_stage"],**({"derived":True} if target.get("derived") else {})})
    from .eps_gaap import summary
    s=summary(rows,"forecast","same_quarter_last_year")
    return {**s,"method":"STRICT_FIRST_FILED_FUNDAMENTALS_WALKFORWARD",
            "mae_model":s.get("mae_model"),"mae_seasonal":s.get("mae_baseline"),"rows":rows}


def build(store, out, consensus=None, guide=None, ledger=None, index=None):
    """The EPS model's outputs for every stored company (eps_blend.run)."""
    from . import eps_blend
    return eps_blend.run(store, out, consensus=consensus, guide=guide, ledger=ledger, index=index)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--store",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--consensus",help="consensus-history public/c (analyst estimates and past surprises)")
    p.add_argument("--guide",help="store/eps-guide (EPS guidance read from earnings releases)")
    p.add_argument("--ledger",help="store/eps-ledger.json (forecasts frozen before each report)")
    p.add_argument("--index",help="_site/data/index.json (which quarters have been reported)")
    args=p.parse_args()
    build(args.store,args.out,args.consensus,args.guide,args.ledger,args.index)
