"""Gamma: SIC-wide industry growth diagnostics, not a theme-specific chain.

Builds gamma/index.json and gamma/<SIC>.json entirely from the existing SEC
store at site-render time. No extra network/API credentials are required.

Distributions are descriptive, not calibrated forecasts or probability of beating
consensus. Client-supplied expectations are scenarios until a point-in-time
consensus dataset is available. Relationships are source-labeled and incomplete.
"""
import datetime as dt
import json
import math
import os
import re
from collections import defaultdict

from . import chains, sectors


def _qnum(end):
    d = dt.date.fromisoformat(end) - dt.timedelta(days=45)
    return d.year * 4 + (d.month - 1) // 3


def _growth(series):
    """Use actual 3-month amounts; reject gaps and nonpositive denominators."""
    hist = sorted((e, float(v)) for e, v in series.items()
                  if v is not None and math.isfinite(float(v)) and float(v) > 0)
    rows = []
    for i, (end, value) in enumerate(hist):
        prior = hist[i - 1] if i else None
        delta = (dt.date.fromisoformat(end) - dt.date.fromisoformat(prior[0])).days if prior else None
        qoq = value / prior[1] - 1 if delta is not None and 55 <= delta <= 125 else None
        matches = [(abs((dt.date.fromisoformat(end) - dt.date.fromisoformat(d)).days - 365), v)
                   for d, v in hist[:i] if 330 <= (dt.date.fromisoformat(end) - dt.date.fromisoformat(d)).days <= 400]
        yoy = value / min(matches)[1] - 1 if matches else None
        rows.append({"end": end, "quarter": _qnum(end), "revenue": value,
                     "yoy": round(yoy, 6) if yoy is not None else None,
                     "qoq": round(qoq, 6) if qoq is not None else None})
    return rows


def _quantile(values, p):
    v = sorted(x for x in values if x is not None and math.isfinite(x))
    if not v:
        return None
    k = (len(v) - 1) * p
    a, b = math.floor(k), math.ceil(k)
    return v[a] * (b - k) + v[b] * (k - a) if a != b else v[a]


def _dist(values):
    v = sorted(x for x in values if x is not None and math.isfinite(x))
    return {"n": len(v), "p10": _quantile(v, .1), "p25": _quantile(v, .25),
            "median": _quantile(v, .5), "p75": _quantile(v, .75),
            "p90": _quantile(v, .9), "min": v[0] if v else None, "max": v[-1] if v else None}


def _stage(rows, reference):
    """Transparent descriptive labels; not a fitted HMM or HSMM."""
    yoy_rows = [r["yoy"] for r in rows if r["yoy"] is not None]
    if not yoy_rows:
        return "unknown"
    g = yoy_rows[-1]
    prior = yoy_rows[-2] if len(yoy_rows) >= 2 else None
    median = _quantile(reference, .5) if reference else 0.0
    upper = _quantile(reference, .75) if len(reference) >= 5 else max(median, .20)
    if g < -.05 and (prior is None or g <= prior):
        return "contraction"
    if prior is not None and prior <= median and g > median and g - prior >= .08:
        return "reacceleration"
    if g > max(upper, .15) and (prior is None or g >= prior):
        return "expansion"
    if prior is not None and g >= 0 and g < prior - .04:
        return "deceleration"
    if abs(g) <= .10:
        return "mature"
    return "transition"


def _named_edges(out, root, member=None):
    """Read prior Chains snapshots; never promote allocations to verified invoices."""
    path = os.path.join(root, "chains", "index.json")
    try:
        with open(path, encoding="utf-8") as f:
            listing = json.load(f).get("chains") or []
    except (OSError, ValueError):
        return
    for ch in listing:
        try:
            with open(os.path.join(root, "chains", ch["id"] + ".json"), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        kind = data.get("kind")
        if kind == "spend":
            ids = {c["id"]: c["t"] for c in data.get("companies", [])}
            for m in data.get("matrix", []):
                buyer, supplier = m.get("b"), ids.get(m.get("s"))
                if m.get("named") and buyer and supplier and (member is None or buyer in member or supplier in member):
                    out.append({"supplier": supplier, "customer": buyer, "kind": "named_customer",
                                "note": "Customer named in supplier filing; displayed chain allocation is modeled",
                                "chain": ch["id"], "source": "chain_customer_disclosure"})
        elif kind == "customers":
            for c in data.get("companies", []):
                for named in c.get("named") or []:
                    supplier, customer = c.get("t"), named.get("b")
                    if supplier and customer and (member is None or supplier in member or customer in member):
                        out.append({"supplier": supplier, "customer": customer, "kind": "named_customer",
                                    "note": "Named customer in SEC filing; identity matched in this chain",
                                    "chain": ch["id"], "source": "chain_customer_disclosure"})



def _company_name_key(label):
    """Conservative name key for direct named-customer matches, never fuzzy tickers."""
    s = re.sub(r"[^a-z0-9]+", " ", (label or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"\b(inc|incorporated|corp|corporation|company|co|limited|ltd|plc|the)\b", "", s)).strip()


def _direct_customer_edges(store, index):
    """Extract named customer disclosures for any SIC, not only themed chains.

    Unmatched names remain labels (not assumed to be listed companies).
    """
    by_name = defaultdict(list)
    for p in index:
        key = _company_name_key(p.get("name"))
        if key:
            by_name[key].append(p)
    edges = []
    for p in index:
        try:
            co = chains.Co(p["cik"], store.company(p["cik"]), ticker=p.get("ticker"))
            named = co.customers()
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            print(f"::warning::gamma named customers {p['cik']}: {str(e)[:80]}")
            continue
        for c in named:
            label = (c.get("label") or "").strip()
            key = _company_name_key(label)
            if not key or len(key) < 3 or re.search(r"\b(customer|customers|client|clients|unknown|unnamed|other)\b", key):
                continue
            matches = by_name.get(key) or []
            match = matches[0] if len(matches) == 1 else None
            supplier = p.get("ticker") or str(p["cik"])
            customer = (match or {}).get("ticker") or label
            if supplier == customer:
                continue
            edges.append({"supplier": supplier, "customer": customer,
                          "customer_cik": match["cik"] if match else None,
                          "supplier_cik": p["cik"],
                          "kind": "named_customer", "note": "Customer named in SEC XBRL filing; amount and current status require filing review",
                          "source": "sec_xbrl_customer_disclosure",
                          "share": c.get("pct"), "period": c.get("period")})
    return edges

def build(store, out, index):
    """Cover every SIC code represented in the rendered company universe."""
    os.makedirs(os.path.join(out, "gamma"), exist_ok=True)
    industry = defaultdict(list)
    for p in index:
        sic = str(p.get("sic") or "").strip().zfill(4)
        if not re.fullmatch(r"\d{4}", sic) or sic == "0000":
            continue
        co = chains.Co(p["cik"], store.company(p["cik"]), ticker=p.get("ticker"))
        rows = _growth(co.history("revenue"))
        if not rows:
            continue
        # Short enough for mobile, but preserve recent history and quarterly labels.
        latest = rows[-1]
        industry[sic].append({"cik": p["cik"], "ticker": p.get("ticker") or "",
                              "name": p.get("name") or "", "sic": sic,
                              "sector": p.get("sector") or sectors.sector_of(sic),
                              "revenue_usd": p.get("revenue"), "end": latest["end"],
                              "quarter": latest["quarter"], "history": rows[-24:]})
    all_named_edges = _direct_customer_edges(store, index)
    _named_edges(all_named_edges, out)  # add named chains links once; never include estimated ones
    cik_by_ticker = {p.get("ticker"): p["cik"] for p in index if p.get("ticker")}
    for edge in all_named_edges:
        edge.setdefault("supplier_cik", cik_by_ticker.get(edge["supplier"]))
        edge.setdefault("customer_cik", cik_by_ticker.get(edge["customer"]))
    listing = []
    for sic, members in sorted(industry.items()):
        members.sort(key=lambda r: -(r.get("revenue_usd") or 0))
        # Latest calendar quarter represented by >= 2 companies when possible.
        counts = defaultdict(int)
        for m in members:
            for r in m["history"][-4:]:
                if r["yoy"] is not None:
                    counts[r["quarter"]] += 1
        comparable = max((k for k, n in counts.items() if n >= 2), default=max(counts, default=None))
        active = []
        for m in members:
            r = next((r for r in reversed(m["history"]) if r["quarter"] == comparable), None)
            if r:
                m["current"] = {"end": r["end"], "yoy": r["yoy"], "qoq": r["qoq"]}
                active.append(m)
        reference = [m["current"]["yoy"] for m in active if m["current"]["yoy"] is not None]
        for m in members:
            past = [r for r in m["history"] if r["quarter"] <= comparable] if comparable is not None else m["history"]
            m["stage"] = _stage(past, reference)
        yoy = [m["current"]["yoy"] for m in active if m["current"]["yoy"] is not None]
        qoq = [m["current"]["qoq"] for m in active if m["current"]["qoq"] is not None]
        pooled_y = [r["yoy"] for m in members for r in m["history"] if r["yoy"] is not None]
        pooled_q = [r["qoq"] for m in members for r in m["history"] if r["qoq"] is not None]
        name = next((p.get("industry") for p in index if str(p.get("sic") or "").zfill(4) == sic and p.get("industry")), "SIC " + sic)
        tickers = {m["ticker"] for m in members if m["ticker"]}
        edges = [e for e in all_named_edges if e["supplier"] in tickers or e["customer"] in tickers]
        # Deduplicate relationships, preserving source provenance; do not assume completeness.
        relationships = list({(e["supplier"], e["customer"], e["source"], e.get("chain")): e for e in edges}.values())
        doc = {"sic": sic, "name": name, "sector": members[0]["sector"],
               "period": (str(comparable // 4) + "Q" + str(comparable % 4 + 1)) if comparable is not None else None,
               "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
               "summary": {"yoy": _dist(yoy), "qoq": _dist(qoq),
                           "pooled_yoy": _dist(pooled_y), "pooled_qoq": _dist(pooled_q)},
               "companies": members, "relationships": relationships,
               "method": "SEC SIC; quarter growth from positive, comparable reported quarterly revenue. Latest calendar-quarter cross section, historical pooled comparisons; descriptive stage heuristics. Relationships only where named in existing Chains data; incomplete coverage."}
        with open(os.path.join(out, "gamma", sic + ".json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"))
        listing.append({"sic": sic, "name": name, "sector": members[0]["sector"],
                        "count": len(members), "observed": len(active), "period": doc["period"],
                        "median_yoy": doc["summary"]["yoy"]["median"], "named_links": len(relationships)})
    with open(os.path.join(out, "gamma", "index.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "industry_scheme": "SEC SIC", "industries": listing,
                   "sector_names": sectors.SECTORS,
                   "universe": sum(len(v) for v in industry.values())}, f, separators=(",", ":"))
    print(f"gamma: {len(listing)} SIC industries, {sum(len(v) for v in industry.values())} company records")
    return listing
