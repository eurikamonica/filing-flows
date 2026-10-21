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
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "Revenues", "SalesRevenueNet"),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
    "tax_expense": ("IncomeTaxExpenseBenefit",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "eps": ("EarningsPerShareDiluted",),
}
UNITS = {x: "shares" if x == "diluted_shares" else "USD/shares" if x == "eps" else "USD" for x in TAGS}
MIN_HISTORY = 8


def med(values, default=None):
    a=[float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(a) if a else default


def bound(x, lo, hi):
    return max(lo,min(hi,x))


def quarterly(facts):
    """Choose earliest-filed directly reported 70-110 day tag in its own units."""
    raw=facts.get("facts",{}).get("us-gaap",{})
    byfield={}
    for field,tags in TAGS.items():
        # Do not mix synonyms in one quarter: one consistent tagged metric per issuer.
        tag=next((t for t in tags if raw.get(t,{}).get("units",{}).get(UNITS[field])),None)
        if not tag:continue
        records={}
        for x in raw[tag]["units"][UNITS[field]]:
            if x.get("form") not in ("10-Q","10-K") or not all(k in x for k in ("start","end","filed","val")):continue
            try:
                days=(iso(x["end"])-iso(x["start"])).days
                lag=(iso(x["filed"])-iso(x["end"])).days
                v=float(x["val"])
            except (ValueError,TypeError,OverflowError):
                continue
            if not (70<=days<=110 and 0<=lag<=200 and math.isfinite(v)):continue
            if field=="diluted_shares" and not (1e3<v<1e13):continue
            r={"val":v,"filed":x["filed"],"tag":tag,"accn":x.get("accn","")}
            old=records.get(x["end"])
            if old is None or (r["filed"],r["accn"])<(old["filed"],old["accn"]):
                records[x["end"]]=r
        byfield[field]=records
    quarters=[]
    ends=sorted(set().union(*(set(v) for v in byfield.values())))
    for end in ends:
        row={"end":end,"fields":{},"source":"SEC_COMPANYFACTS_FIRST_FILED_DIRECT"}
        for field,records in byfield.items():
            if end in records:row["fields"][field]=records[end]
        quarters.append(row)
    return quarters


def observations(series,cutoff):
    """Only entirely public quarterly records; joins demand same fiscal end."""
    result=[]
    for row in series:
        fields=row.get("fields",{})
        need=("revenue","operating_income","tax_expense","net_income","diluted_shares","eps")
        if any(k not in fields for k in need):continue
        if any(iso(fields[k]["filed"]) >= iso(cutoff) for k in need):continue
        try:
            v={k:float(x["val"]) for k,x in fields.items()}
        except (ValueError,KeyError,TypeError):continue
        if not all(math.isfinite(x) for x in v.values()):continue
        if v["revenue"]<=0 or v["diluted_shares"]<=1000:continue
        if "pretax_income" not in v:v["pretax_income"]=v["net_income"]+v["tax_expense"]
        # Verify reported GAAP EPS and net income/share count are compatible.
        # Some filers include noncontrolling interests or have split regimes: abstain.
        calc=v["net_income"]/v["diluted_shares"]
        if abs(calc-v["eps"])>max(.25,.30*abs(v["eps"])):continue
        # Reject observations in which units or large share-regime shifts are dubious.
        result.append({**v,"end":row["end"],
          "filed":max(fields[k]["filed"] for k in need),
          "source_tags":{k:fields[k]["tag"] for k in need}})
    return sorted(result,key=lambda z:z["end"])


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


def backtest(series,years=(2024,2025,2026)):
    # Hold out target filings. Forecast origin: one day after prior reported quarter,
    # using only the companyfacts that had then become public.
    eligible=observations(series,"2100-01-01")
    rows=[]
    for j in range(MIN_HISTORY,len(eligible)):
        target=eligible[j]
        if iso(target["end"]).year not in years:continue
        prior=eligible[:j]
        cutoff=(iso(prior[-1]["filed"])+dt.timedelta(days=1)).isoformat()
        if iso(target["filed"])<=iso(cutoff):continue
        y=forecast(series,cutoff,target=target["end"],allow_dist=True)
        if not y:continue
        rows.append({"end":target["end"],"cutoff":cutoff,"filed":target["filed"],
                     "actual":target["eps"],"forecast":y["point"],
                     "same_quarter_last_year":y["eps_gaap_last_year"],
                     "stage":y["company_stage"],"tax_spike_known":bool(y["confirmed_events"]),
                     "interval":y.get("distribution",{}),"gaap_yoy_base":y["eps_gaap_last_year"]})
    n=len(rows)
    def mae(k):
        return round(sum(abs(x[k]-x["actual"]) for x in rows)/n,4) if n else None
    p=[r for r in rows if r["interval"].get("status")=="EMPIRICAL_UNCALIBRATED"]
    calibrated={"n":len(p),
                "empirical_80pct_interval_coverage":round(sum(
                  r["interval"]["p10"]<=r["actual"]<=r["interval"]["p90"] for r in p)/len(p),4) if p else None,
                "brier_gaap_yoy_direction":round(sum(
                  (r["interval"]["p_yoy_increase"]-float(r["actual"]>r["gaap_yoy_base"]))**2
                   for r in p)/len(p),5) if p else None,
                "status":"OUT_OF_TIME_DIAGNOSTIC_NOT_FORMALLY_CALIBRATED"}
    return {"n":n,"method":"STRICT_FIRST_FILED_FUNDAMENTALS_WALKFORWARD",
            "probability_validation":calibrated,
            "mae_model":mae("forecast"),"mae_seasonal":mae("same_quarter_last_year"),
            "by_year":{str(y):{"n":len([r for r in rows if iso(r["end"]).year==y]),
                     "mae_model":round(sum(abs(r["forecast"]-r["actual"]) for r in rows if iso(r["end"]).year==y)/
                                       len([r for r in rows if iso(r["end"]).year==y]),4)
                                     if any(iso(r["end"]).year==y for r in rows) else None}
                       for y in years},
            "rows":rows}


def build(store,out):
    root=Path(store);dst=Path(out);dst.mkdir(parents=True,exist_ok=True)
    aggregate=[]
    for file in sorted(root.glob("*.json")):
        if file.name=="progress.json":continue
        d=read(file,{})
        series=d.get("quarters",[])
        if not series:continue
        asof=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).date().isoformat()
        events=read(Path(store).parent/"eps-events"/file.name,{})
        pred=forecast(series,asof,events=events.get("events",[]),allow_dist=True)
        bt=backtest(series)
        if pred is not None:
            tested=bt["n"]>=8 and bt["mae_model"] is not None and bt["mae_seasonal"] is not None
            beat_baseline=tested and bt["mae_model"]<bt["mae_seasonal"]
            pred["promotion_gate"]={
                "status":"RESEARCH_ONLY_INSUFFICIENT_BACKTEST" if not tested else (
                    "RESEARCH_ONLY_BASELINE_BETTER" if not beat_baseline else "PASSED_SEASONAL_BACKTEST_GATE"),
                "n":bt["n"],"baseline_mae":bt["mae_seasonal"],
                "model_mae":bt["mae_model"],
                "evidence_note":"Historical comparison only; even a passed gate does not establish accuracy vs Street EPS."}
        for r in bt["rows"]:aggregate.append({"cik":file.stem,**r})
        write(dst/file.name,{"cik":d.get("cik"),"ticker":d.get("ticker"),
            "source":"SEC_FIRST_FILED_COMPANYFACTS_FUNDAMENTALS",
            "as_of":asof,"forecast":pred,"backtest":{k:v for k,v in bt.items() if k!="rows"}})
    n=len(aggregate)
    mae=lambda key: round(sum(abs(r[key]-r["actual"]) for r in aggregate)/n,4) if n else None
    eligible=[x for x in aggregate if x.get("interval",{}).get("status")=="EMPIRICAL_UNCALIBRATED"]
    coverage=(sum(x["interval"]["p10"]<=x["actual"]<=x["interval"]["p90"] for x in eligible)
              /len(eligible)) if eligible else None
    brier=(sum((x["interval"]["p_yoy_increase"]-float(x["actual"]>x["gaap_yoy_base"]))**2
             for x in eligible)/len(eligible)) if eligible else None
    write(dst/"backtest.json",{"n":n,"companies":len({x["cik"] for x in aggregate}),
        "probability_validation":{"n":len(eligible),"coverage_80":round(coverage,4) if coverage is not None else None,
                                 "brier_yoy":round(brier,5) if brier is not None else None,
                                 "status":"INDEPENDENT_CHRONOLOGICAL_DIAGNOSTIC_NO_CALIBRATION_CLAIM"},
        "mae_model":mae("forecast"),"mae_seasonal":mae("same_quarter_last_year"),
        "label":"STRICT_FIRST_FILED_FUNDAMENTAL_GAAP_EPS","by_stage":{
            s:{"n":len([r for r in aggregate if r["stage"]==s])} for s in sorted({r["stage"] for r in aggregate})},
        "notes":["Only directly reported quarter XBRL facts; Q4 missing when not directly tagged.",
                 "Quarter-end source tags may differ between filers; excludes incompatible net-income-to-EPS units.",
                 "Not calibrated: company-specific forecast percentiles are illustrative until tested."]})
    print("Fundamental EPS",n,"PIT records from",len({x["cik"] for x in aggregate}),"issuers")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--store",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    build(args.store,args.out)
