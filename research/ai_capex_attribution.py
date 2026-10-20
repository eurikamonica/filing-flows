"""Research-only AI CapEx -> terminal spend -> vendor revenue timing model.

All inputs must be explicit. No synthetic scenario is a verified issuer forecast.
Uses standard library only. Terminal spending allocations sum to no more than CapEx;
upstream BOM supplier revenues must be modeled as a SEPARATE ledger, not added here.
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def quarter_index(q):
    if not isinstance(q, str) or len(q) != 6 or q[4] != "Q" or q[5] not in "1234" or not q[:4].isdigit():
        raise ValueError(f"Invalid quarter: {q!r}; use YYYYQ1...YYYYQ4")
    return int(q[:4]) * 4 + int(q[5]) - 1


def quarter_name(idx):
    return f"{idx // 4:04d}Q{idx % 4 + 1}"


def probability(value, label):
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be a number") from None
    if not math.isfinite(n) or not 0 <= n <= 1:
        raise ValueError(f"{label} must be between 0 and 1")
    return n


def validate(spec):
    if spec.get("demo_only") is not True:
        raise ValueError("Prototype requires demo_only=true: never mislabel assumptions as SEC data")
    quarter_index(spec.get("period"))
    if not isinstance(spec.get("categories"), dict) or not spec["categories"]:
        raise ValueError("categories must be a nonempty mapping")
    weights = 0.0
    for category, row in spec["categories"].items():
        weights += probability(row.get("weight"), category + ".weight")
        shares = row.get("suppliers", {})
        if not isinstance(shares, dict):
            raise ValueError(category + ".suppliers must be an object")
        share_total = sum(probability(v, category + "." + k) for k, v in shares.items())
        if share_total > 1 + 1e-9:
            raise ValueError(category + " supplier shares exceed 100%")
    if abs(weights - 1.0) > 1e-8:
        raise ValueError(f"Category weights must sum to 1 (got {weights})")
    lags = spec.get("recognition_lags", {"0": 1.0})
    if not isinstance(lags, dict) or not lags:
        raise ValueError("recognition_lags must be a nonempty mapping")
    total = 0.0
    for key, weight in lags.items():
        offset = int(key)
        if str(offset) != str(key) or abs(offset) > 12:
            raise ValueError("Recognition lag must be an integer quarter in [-12,12]")
        total += probability(weight, f"recognition_lags[{key}]")
    if abs(total - 1) > 1e-8:
        raise ValueError("recognition_lags must sum to 1")
    for case in spec.get("scenarios", []):
        cost = case.get("capex_usd")
        if not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            raise ValueError("Scenario capex_usd must be finite and nonnegative")


def calculate(spec):
    validate(spec)
    base_quarter = quarter_index(spec["period"])
    output = {"method": "scenario_only", "demo_only": True, "buyer": spec.get("buyer", "UNKNOWN"),
              "period": spec["period"], "currency": "USD", "scenarios": []}
    for case in spec.get("scenarios", []):
        spend = float(case["capex_usd"])
        edges, revenues = [], defaultdict(float)
        category_unallocated = {}
        for category, row in spec["categories"].items():
            budget = spend * float(row["weight"])
            used = 0.0
            for vendor, raw_share in row.get("suppliers", {}).items():
                allocated = budget * float(raw_share)
                used += allocated
                if allocated == 0:
                    continue
                # A terminal procurement attribution, not a verified vendor invoice.
                edges.append({"supplier": vendor, "customer": spec.get("buyer", "UNKNOWN"),
                              "category": category, "value_usd": round(allocated, 2),
                              "valid_period": spec["period"], "value_type": "terminal_spend_attribution",
                              "evidence_level": "illustrative_assumption", "source_url": None})
                for lag, fraction in spec.get("recognition_lags", {"0": 1.0}).items():
                    revenues[(vendor, quarter_name(base_quarter + int(lag)))] += allocated * float(fraction)
            category_unallocated[category] = round(max(0, budget - used), 2)
        vendor_totals = defaultdict(float)
        for edge in edges:
            vendor_totals[edge["supplier"]] += edge["value_usd"]
        output["scenarios"].append({
            "name": case.get("name", "Unnamed"), "capex_usd": spend,
            "terminal_edges": edges,
            "terminal_vendor_usd": dict(sorted(vendor_totals.items())),
            "unallocated_by_category_usd": category_unallocated,
            "revenue_timing_estimate_usd": [
                {"vendor": vendor, "period": period, "value_usd": round(amount, 2)}
                for (vendor, period), amount in sorted(revenues.items())],
            "note": "Revenue timing is hypothetical and not independently reconciled with SEC segment revenues."
        })
    return output


def main():
    cli = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    cli.add_argument("scenario_json", type=Path)
    cli.add_argument("--out", type=Path)
    args = cli.parse_args()
    spec = json.loads(args.scenario_json.read_text(encoding="utf-8"))
    result = calculate(spec)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
