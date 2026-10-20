"""Read-only prediction-market evidence normalization and scenario shocks.

Never assume two markets have identical resolution terms from ticker/title alone.
A probability is a price-based indication, not a guaranteed event frequency.
"""
from datetime import date
import math
import re


def numeric_probability(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        v=float(v)
    except (TypeError,ValueError):
        return None
    return v if math.isfinite(v) and 0<=v<=1 else None


def normalize(row):
    """Normalize existing consensus market rows without changing original source fields."""
    source=row.get("source")
    if source not in ("polymarket","kalshi"):
        raise ValueError("Unknown venue")
    p=numeric_probability(row.get("p"))
    volume=row.get("volume")
    try:
        volume=float(volume) if volume is not None else None
        if volume is not None and (not math.isfinite(volume) or volume<0):
            volume=None
    except (TypeError,ValueError):
        volume=None
    return {
        "source":source,"id":str(row.get("id") or row.get("url") or ""),
        "title":str(row.get("title") or ""),"ticker":row.get("ticker"),
        "kind":row.get("kind"),"resolution_date":str(row.get("end") or "")[:10] or None,
        "price_implied_probability":p,"volume_reported":volume,
        "volume_unit":row.get("volume_unit") or "provider_reported_unknown",
        "resolution_terms_url":row.get("resolution_terms_url"),
        "source_url":row.get("url"),"collected_at":row.get("collected_at"),
        "status":"closed" if row.get("closed") else "open",
        "mapping_quality":"unverified"
    }


def cross_venue_comparison(left,right):
    """Compare only when an independently reviewed common event key is identical.

    Matching ticker, similar names, or close dates is NOT enough.
    """
    if left["source"]==right["source"]:
        return {"comparable":False,"reason":"same venue"}
    if not left.get("reviewed_event_key") or left["reviewed_event_key"]!=right.get("reviewed_event_key"):
        return {"comparable":False,"reason":"No identical reviewer-approved resolution contract"}
    if not left.get("settlement_verified") or not right.get("settlement_verified"):
        return {"comparable":False,"reason":"Settlement terms not verified"}
    a=numeric_probability(left.get("price_implied_probability"))
    b=numeric_probability(right.get("price_implied_probability"))
    if a is None or b is None:
        return {"comparable":False,"reason":"Incomplete probability"}
    return {"comparable":True,"delta_probability_points":round((a-b)*100,3),
            "left_venue":left["source"],"right_venue":right["source"],
            "note":"Quote difference, not necessarily an executable arbitrage; depth, spread, fees and settlement differ."}


def binary_event_impact(p,base_usd,if_yes_usd,if_no_usd):
    """Expected modeled revenue for mutually exclusive YES/NO scenarios.

    This method does NOT infer contracts, allocate upstream BOM amounts, nor turn
    crowd odds into issuer management guidance. Client supplies causal impacts.
    """
    p=numeric_probability(p)
    if p is None:
        raise ValueError("Invalid implied probability")
    values=(base_usd,if_yes_usd,if_no_usd)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
        raise ValueError("Scenario dollar inputs must be finite numerical estimates")
    expected=p*if_yes_usd+(1-p)*if_no_usd
    return {"base_revenue_usd":base_usd,"if_yes_revenue_usd":if_yes_usd,
            "if_no_revenue_usd":if_no_usd,"market_implied_weight":p,
            "weighted_revenue_usd":expected,"weighted_change_from_base_usd":expected-base_usd,
            "evidence_level":"model_estimate",
            "warning":"Scenario impacts are researcher inputs; probability is market price, not a verified forecast."}


def brier_score(rows):
    """Score held-out resolved YES/NO market observations with as-of timestamps."""
    squared=[]
    for row in rows:
        p=numeric_probability(row.get("price_implied_probability"))
        actual=row.get("resolved_yes")
        q=row.get("quote_time")
        closed=row.get("resolved_at")
        # no leakage: probability quote must strictly predate the known result
        if p is None or not isinstance(actual,bool) or not q or not closed or not q<closed:
            continue
        squared.append((p-float(actual))**2)
    return {"n":len(squared),"brier":sum(squared)/len(squared) if squared else None,
            "policy":"Pre-resolution quotes only; count each resolved independent market once."}
