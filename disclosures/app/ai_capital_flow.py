"""AI cash CapEx research scenario; reuses pipeline.sec and pipeline.facts.

Reported numbers: SEC XBRL. Every 2027 estimate and all supplier
allocations are illustrative, NOT company guidance or supplier revenue.
Run: python -m disclosures.app.ai_capital_flow --output disclosures/docs/data/ai-capital-flow.json
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
from pipeline import sec, facts

BUYERS = ("GOOGL", "AMZN", "MSFT", "META", "ORCL")
CATEGORY = {"Compute & servers": .45, "Networking & optical": .15,
            "Memory & storage": .15, "DC infrastructure & power": .15,
            "Other / unallocated": .10}
VENDOR = {
    "Compute & servers": {"NVDA": .50, "AVGO": .10, "Unknown suppliers": .40},
    "Networking & optical": {"ANET": .25, "AVGO": .15, "Unknown suppliers": .60},
    "Memory & storage": {"MU": .25, "Unknown suppliers": .75},
    "DC infrastructure & power": {"Unknown suppliers": 1.0},
    "Other / unallocated": {"Unknown suppliers": 1.0},
}

def validate():
    for name, weights in [("category", CATEGORY), *VENDOR.items()]:
        if any(v < 0 or not math.isfinite(v) for v in weights.values()) or abs(sum(weights.values())-1) > 1e-9:
            raise ValueError(name + ": weights must be nonnegative and total 100%")

def actual_history(companyfacts):
    fx = facts.index_facts(companyfacts)
    result = []
    for end in facts.year_ends(fx):
        if end > dt.date.today().isoformat():
            continue
        capex = facts.value(fx, "capex", end, annual=True)
        if capex is None or capex < 0:
            continue
        result.append({
            "fiscal_year": int(end[:4]), "period_end": end,
            "cash_capex_usd": round(float(capex), 2),
            "revenue_usd": facts.value(fx, "revenue", end, annual=True),
            "ocf_usd": facts.value(fx, "ocf", end, annual=True),
            "da_usd": facts.value(fx, "da", end, annual=True),
            "tag": facts.source(fx, "capex", end, annual=True),
            "status": "reported_xbrl",
        })
    return result[-8:]

def projection(history, target=2027):
    if not history:
        return None
    last = history[-1]
    years = target-last["fiscal_year"]
    if years < 0:
        return None
    prev = next((r for r in reversed(history[:-1]) if r["fiscal_year"] < last["fiscal_year"]), None)
    growth = 0.0
    if prev and prev["cash_capex_usd"] > 0:
        growth = (last["cash_capex_usd"]/prev["cash_capex_usd"])**(1/(last["fiscal_year"]-prev["fiscal_year"]))-1
    growth = min(.4, max(-.25, growth))
    return {"value_usd": round(last["cash_capex_usd"]*(1+growth)**years, 2),
            "growth": growth, "base_year": last["fiscal_year"],
            "status": "illustrative_model_estimate" if years else "reported_xbrl"}

def build(histories, year=2027):
    validate()
    companies, links, warnings = [], [], []
    for ticker in BUYERS:
        history = histories.get(ticker, [])
        p = projection(history, year)
        companies.append({"ticker": ticker, "history": history, "prediction": p})
        if p is None:
            warnings.append(ticker + ": unavailable annual CapEx; not fabricated")
            continue
        for category, weight in CATEGORY.items():
            amount = p["value_usd"]*weight
            links.append({"source": "buyer:"+ticker, "target": "category:"+category,
                          "value_usd": amount, "status": p["status"]})
            for vendor, fraction in VENDOR[category].items():
                links.append({"source": "category:"+category, "target": "vendor:"+vendor,
                              "buyer": ticker, "value_usd": amount*fraction,
                              "status": "illustrative_attribution"})
    total = sum(c["prediction"]["value_usd"] for c in companies if c["prediction"])
    for layer in ("buyer:", "category:"):
        check = sum(l["value_usd"] for l in links if l["source"].startswith(layer))
        if abs(check-total) > max(.01, total*1e-9):
            raise AssertionError("CapEx conservation failed for " + layer)
    return {
        "schema_version": 1, "year": year, "currency": "USD",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "basis": "cash CapEx, company fiscal-year end",
        "status": "ILLUSTRATIVE_NOT_SUPPLIER_REVENUE",
        "companies": companies, "links": links, "category_weights": CATEGORY,
        "vendor_weights": VENDOR, "total_capex_usd": total, "warnings": warnings,
        "methodology": [
            "Historical cash CapEx: SEC XBRL via the existing pipeline.facts module.",
            "2027E: bounded past-growth extrapolation, NOT company guidance or consensus.",
            "Category/BOM shares and vendor assignments are unverified scenario assumptions.",
            "Supplier flow is an economic expenditure allocation, not GAAP vendor revenue.",
            "Do not sum GPU, HBM and full server gross sales across transaction levels.",
            "Different fiscal year ends and cash versus noncash leases limit comparability.",
            "Companyfacts has revised historical values: NOT a point-in-time backtest."
        ]
    }

def pull():
    ids_doc = sec.get_json("https://www.sec.gov/files/company_tickers.json")
    values = ids_doc.values() if isinstance(ids_doc, dict) else ids_doc
    ids = {v["ticker"].upper(): int(v["cik_str"]) for v in values}
    histories, errors = {}, []
    for ticker in BUYERS:
        if ticker not in ids:
            errors.append(ticker + ": missing from SEC ticker map")
            continue
        try:
            raw = sec.get_json(sec.companyfacts_url(ids[ticker]))
            histories[ticker] = actual_history(raw)
        except (OSError, RuntimeError, ValueError, sec.NotFound) as exc:
            errors.append(ticker + ": " + type(exc).__name__)
    return histories, errors

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=2027)
    p.add_argument("--output", default="disclosures/docs/data/ai-capital-flow.json")
    p.add_argument("--input-histories", help="offline fixture JSON, no SEC access")
    args = p.parse_args()
    if args.input_histories:
        histories = json.loads(Path(args.input_histories).read_text(encoding="utf-8"))
        errors = []
    else:
        histories, errors = pull()
    result = build(histories, args.year)
    result["warnings"].extend(errors)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print("Created", out, "buyers:", sum(c["prediction"] is not None for c in result["companies"]))

if __name__ == "__main__":
    main()
