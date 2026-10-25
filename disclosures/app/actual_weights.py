"""Append dated ETF portfolio disclosures for the independent Actual Weights video.

This must never rewrite or infer the Video Studio's existing market-cap-based
Sector Weights. Only weights disclosed by the fund for an identifiable as-of
date are saved. History starts at the FIRST snapshot we actually collected.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

INDEX_TRACKERS = ("DIA", "SPY", "QQQ", "IJH", "IJR", "IWB", "IWM", "IWV")
MAX_TRACKED_FUNDS = 250
MAX_SNAPSHOTS = 60
MAX_POSITIONS = 600
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TICKER = re.compile(r"^[A-Z][A-Z0-9-]{0,9}$")


def compact_positions(weights):
    """NAV weights, not percentages, not market-cap weights; preserve omissions."""
    totals = {}
    for row in weights or []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        symbol = str(row[0] or "").strip().upper().replace(".", "-")
        try:
            weight = float(row[1])
        except (TypeError, ValueError, OverflowError):
            continue
        if not TICKER.fullmatch(symbol) or not math.isfinite(weight) or weight <= 0:
            continue
        totals[symbol] = totals.get(symbol, 0.0) + weight
    return [[key, round(w, 8)] for key, w in
            sorted(totals.items(), key=lambda x: -x[1])[:MAX_POSITIONS] if w > 0]


def take_snapshot(doc):
    """One immutable source-date portfolio; no historical extrapolation."""
    hold = doc.get("holdings") or {}
    date = str(hold.get("date") or "")[:10]
    if not DATE.fullmatch(date):
        return None
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        return None
    positions = compact_positions(doc.get("weights"))
    if len(positions) < 2:
        return None
    source = hold.get("source") or ("SEC N-PORT" if hold.get("acc") else "fund holdings disclosure")
    return {"date": date, "date_basis": hold.get("date_basis") or "reported", "source": source, "accession": hold.get("acc"),
            "positions": positions, "sectors": hold.get("sector_map") or {},
            "equity_weight_covered": round(sum(w for _, w in positions), 6)}


def merge_snapshots(old, new):
    """One record per original report date; newest correction wins."""
    by_date = {}
    for snap in old or []:
        if isinstance(snap, dict) and DATE.fullmatch(str(snap.get("date") or "")) and snap.get("positions"):
            by_date[snap["date"]] = snap
    if new:
        by_date[new["date"]] = new
    return [by_date[d] for d in sorted(by_date)[-MAX_SNAPSHOTS:]]


def capture(root, pub, index_rows):
    """Persist dated snapshots on the ETF data branch, publish read-only JSON.

    The highest-AUM ETFs and reference index trackers accrue history; all other
    funds remain viewable as a single sourced report through existing e/*.json.
    Data branch cache is persistent across builds (see etf.yml).
    """
    root, pub = Path(root), Path(pub)
    cache = root / "cache" / "actual_weights"
    dest = pub / "weights"
    cache.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    ranked = sorted(index_rows or [], key=lambda r: float(r.get("aum") or 0), reverse=True)
    selected = set(INDEX_TRACKERS) | {r["symbol"] for r in ranked[:MAX_TRACKED_FUNDS] if r.get("symbol")}
    written = 0
    for symbol in sorted(selected):
        if not TICKER.fullmatch(symbol):
            continue
        details = pub / "e" / (symbol + ".json")
        if not details.is_file():
            continue
        try:
            doc = json.loads(details.read_text(encoding="utf-8"))
            snap = take_snapshot(doc)
            path = cache / (symbol + ".json")
            old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            history = merge_snapshots(old.get("snapshots"), snap)
            if not history:
                continue
            record = {"symbol": symbol, "name": doc.get("name") or symbol, "snapshots": history,
                      "note": "Only actual source-dated holdings; no historical backfill, no interpolation of undisclosed dates."}
            raw = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
            path.write_text(raw, encoding="utf-8")
            (dest / (symbol + ".json")).write_text(raw, encoding="utf-8")
            written += 1
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print("actual weights skipped", symbol, type(exc).__name__, str(exc)[:100], flush=True)
    return {"tracked": len(selected), "published": written}
