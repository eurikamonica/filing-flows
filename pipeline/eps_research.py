"""Wide cross-sectional EPS research ledger; strictly labeled retrospective where sources lack vintages.

Source: consensus-history/public/c/<CIK>.json and public/calibration.json.
Training uses only earlier company surprise observations, never the tested row.
Historical analyst estimates supplied by Yahoo are retrospectively stored; NOT PIT audited.
No market, macro, rating or 13F factor is credited with EPS predictive skill without
a dated row-by-row feature snapshot. Separately report genuine prediction-market score.
"""
import argparse
import collections
import datetime as dt
import json
import math
from pathlib import Path


def date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def numeric(v):
    try:
        return v is not None and math.isfinite(float(v))
    except (ValueError, TypeError):
        return False


def clip(v, lo, hi):
    return max(lo, min(hi, v))


def correction(history, estimate):
    """Robust recency-weighted empirical Bayes surprise model; requires previous releases."""
    if not history:
        return 0.0
    recent = history[-8:]
    weights = [0.85 ** (len(recent) - 1 - k) for k in range(len(recent))]
    errs = [clip(r["actual"] - r["estimate"], -3, 3) for r in recent]
    weighted = sum(w * e for w, e in zip(weights, errs)) / sum(weights)
    k = len(recent)
    return clip(weighted * k / (k + 8), -.25 * max(abs(estimate), .5), .25 * max(abs(estimate), .5))


def score_company(doc, year=None):
    a = doc.get("analysts") or {}
    source = a.get("surprises") or doc.get("surprises") or []
    ordered = []
    for row in source:
        when = date(row.get("reported"))
        if not when or not numeric(row.get("eps_est")) or not numeric(row.get("eps_act")):
            continue
        ordered.append({"reported": when.isoformat(),
                        "quarter": str(row.get("quarter") or ""),
                        "estimate": float(row["eps_est"]), "actual": float(row["eps_act"])})
    ordered.sort(key=lambda r: (r["reported"], r["quarter"]))
    past, rows = [], []
    for r in ordered:
        # Predictions before two historical reports are not counted as trained models.
        if len(past) >= 2 and (year is None or r["reported"].startswith(str(year))):
            adjustment = correction(past, r["estimate"])
            prediction = r["estimate"] + adjustment
            rows.append({**r, "prediction": round(prediction, 6),
                         "model_ae": abs(prediction - r["actual"]),
                         "baseline_ae": abs(r["estimate"] - r["actual"]),
                         "stage": "loss" if r["estimate"] < 0 else ("small_eps" if abs(r["estimate"]) < .5 else "established"),
                         "trained_on": len(past)})
        past.append(r)
    return rows


def metrics(rows):
    n = len(rows)
    if not n:
        return {"n": 0, "mae_model": None, "mae_consensus": None,
                "rmse_model": None, "relative_mae_improvement": None}
    sm = sum(r["model_ae"] for r in rows) / n
    sb = sum(r["baseline_ae"] for r in rows) / n
    rm = math.sqrt(sum((r["actual"] - r["prediction"]) ** 2 for r in rows) / n)
    return {"n": n, "mae_model": round(sm, 5), "mae_consensus": round(sb, 5),
            "rmse_model": round(rm, 5),
            "relative_mae_improvement": round(1 - sm / sb, 5) if sb > 0 else None}


def build(consensus_dir, market_file, out_path):
    groups = collections.defaultdict(list)
    years = collections.defaultdict(list)
    stages = collections.defaultdict(list)
    allrows = []
    company_count = 0
    files = 0
    for path in sorted(Path(consensus_dir).glob("*.json")):
        files += 1
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows = score_company(doc)
        if not rows:
            continue
        company_count += 1
        ticker = str(doc.get("ticker") or "").upper()
        sector = str(doc.get("sector") or "unknown")
        for row in rows:
            r = {**row, "ticker": ticker, "cik": doc.get("cik"), "sector": sector}
            allrows.append(r)
            groups[sector].append(r)
            years[r["reported"][:4]].append(r)
            stages[r["stage"]].append(r)
    market = {}
    try:
        market = json.loads(Path(market_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    report = {
        "schema": "filing-flows-eps-research-v3",
        "status": "RETROSPECTIVE_ANALYST_VINTAGES_UNVERIFIED",
        "data_as_of": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "source": "consensus-history public company earnings surprise snapshots",
        "source_files_scanned": files,
        "companies_scored": company_count,
        "method": "Expanding per-company strictly earlier released surprise correction, exponential weights + shrinkage and 25% cap, benchmark current archived historical analyst EPS estimate",
        "limitations": [
            "Historical analyst estimates in current Yahoo records may have been revised after the actual report; these are not verified historical estimate vintages.",
            "Coverage and survival biases; companies with fewer than three observed surprise rows have no model evaluation.",
            "No 13F, FRED, Kalshi, ratings or supply-chain coefficients trained or included in this MAE.",
            "Market Brier scores evaluate resolved event contracts, never EPS numerical prediction or trade P&L.",
        ],
        "overall": metrics(allrows),
        "by_year": {k: metrics(v) for k, v in sorted(years.items())},
        "by_sector": {k: metrics(v) for k, v in sorted(groups.items())},
        "by_stage": {k: metrics(v) for k, v in sorted(stages.items())},
        "resolved_prediction_markets": {
            "provider": "Polymarket", "type": "beat_earnings",
            "n": market.get("n"), "brier": market.get("brier"),
            "base_rate_brier": market.get("brier_base_rate"),
            "base_rate": market.get("base_rate"), "bins": market.get("bins", []),
            "note": "Independent event probability score; not evidence that the EPS model beats consensus.",
        },
    }
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EPS V3 research: {files} archived company records, {company_count} scored, {len(allrows)} chronological retrospective observations")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--consensus", required=True)
    p.add_argument("--market", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    build(args.consensus, args.market, args.out)
