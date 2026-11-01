"""Append dated ETF portfolio disclosures for the independent Actual Weights video.

This must never rewrite or infer the Video Studio's existing market-cap-based
Sector Weights. Only weights disclosed by the fund for an identifiable as-of
date are saved. The kept snapshots start at the FIRST one we actually collected;
the quarterly block (every ETF with two or more public N-PORT quarter-end
reports since 2019, etf.history_by_symbol) is read from the SEC's N-PORT data
sets — the fund's own reports for those dates, nothing interpolated.
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
    basis = hold.get("date_basis") if hold.get("date_basis") in ("reported", "observed") else "reported" if hold.get("acc") else "unknown"   # an N-PORT report date
    return {"date": date, "date_basis": basis, "source": source, "accession": hold.get("acc"),
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


def with_sectors(snap, sector_of):
    """The snapshot with 'sector_weights' (sector key → weight) added from its positions, when it has none: the lines
    the classifier cannot place, and equity lines beyond the positions listed, in 'other'."""
    if not sector_of or snap.get("sector_weights"):
        return snap
    sec, listed = {}, 0.0
    for t, w in snap.get("positions") or []:
        k = sector_of(t) or "other"
        sec[k] = sec.get(k, 0.0) + w
        listed += w
    rest = float(snap.get("equity_weight_covered") or listed) - listed
    if rest > 1e-6:
        sec["other"] = sec.get("other", 0.0) + rest
    return {**snap, "sector_weights": {k: round(v, 6) for k, v in sorted(sec.items(), key=lambda x: -x[1]) if v > 5e-7}}


def quarterly_block(snaps):
    """The quarter-end N-PORT snapshots (etf.history_by_symbol) as columns, the way the history is published: the same
    names in every quarter (largest first) and the sector keys, with weights in hundred-thousandths of net assets
    (actual-weights.js turns them back into snapshots)."""
    snaps = [x for x in snaps or [] if isinstance(x, dict) and DATE.fullmatch(str(x.get("date") or "")) and x.get("positions")]
    if not snaps:
        return None
    peak, secs = {}, {}
    for x in snaps:
        for t, w in x["positions"]:
            peak[t] = max(peak.get(t, 0.0), w)
        for k, w in (x.get("sector_weights") or {}).items():
            secs[k] = max(secs.get(k, 0.0), w)
    names = sorted(peak, key=lambda t: -peak[t])
    keys = sorted(secs, key=lambda k: (k == "other", -secs[k]))
    return {"source": "SEC Form N-PORT data sets (public quarter-end reports)",
            "note": "Each quarter lists the fund's largest names (the same names in every quarter, weights exact) and its "
                    "sector weights over every long equity line; the rest of the portfolio is Other.",
            "unit": 1e-5, "dates": [x["date"] for x in snaps], "acc": [x.get("accession") for x in snaps],
            "eq": [round(float(x.get("equity_weight_covered") or 0), 4) for x in snaps], "n": [x.get("n") for x in snaps],
            "na": [round(x["net_assets"]) if x.get("net_assets") else None for x in snaps], "names": names,
            "w": [[round(dict(x["positions"]).get(t, 0.0) * 1e5) for t in names] for x in snaps], "sectors": keys,
            "sw": [[round((x.get("sector_weights") or {}).get(k, 0.0) * 1e5) for k in keys] for x in snaps]}


def capture(root, pub, index_rows, quarterly=None, sector_of=None):
    """Persist dated snapshots on the ETF data branch, publish read-only JSON.

    The highest-AUM ETFs and reference index trackers accrue history; all other
    funds remain viewable as a single sourced report through existing e/*.json.
    Data branch cache is persistent across builds (see etf.yml).
    quarterly: {symbol: [snapshot …]} — every ETF's quarter-end N-PORT portfolios
    (etf.history_by_symbol), published with the kept snapshots; sector_of: ticker →
    sector key, for the published snapshots' sector weights.
    """
    root, pub = Path(root), Path(pub)
    cache = root / "cache" / "actual_weights"
    dest = pub / "weights"
    cache.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    quarterly = quarterly or {}
    ranked = sorted(index_rows or [], key=lambda r: float(r.get("aum") or 0), reverse=True)
    names = {r.get("symbol"): r.get("name") for r in index_rows or [] if r.get("symbol")}
    selected = set(INDEX_TRACKERS) | {r["symbol"] for r in ranked[:MAX_TRACKED_FUNDS] if r.get("symbol")}
    kept = {}
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
            path.write_text(json.dumps(record, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
            kept[symbol] = record
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print("actual weights skipped", symbol, type(exc).__name__, str(exc)[:100], flush=True)
    written = with_quarters = 0
    for symbol in sorted(set(kept) | {s for s, q in quarterly.items() if TICKER.fullmatch(s or "") and len(q or []) >= 2}):
        try:
            rec = kept.get(symbol) or {"symbol": symbol, "name": names.get(symbol) or symbol, "snapshots": [],
                                       "note": "Quarter-end portfolios from the fund's public N-PORT reports; no interpolation of undisclosed dates."}
            out = {**rec, "snapshots": [with_sectors(x, sector_of) for x in rec.get("snapshots") or []]}
            block = quarterly_block(quarterly.get(symbol)) if len(quarterly.get(symbol) or []) >= 2 else None
            if block:
                out["quarterly"] = block
                with_quarters += 1
            if not out["snapshots"] and not block:
                continue
            (dest / (symbol + ".json")).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
            written += 1
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print("actual weights skipped", symbol, type(exc).__name__, str(exc)[:100], flush=True)
    return {"tracked": len(selected), "published": written, "with_quarterly_history": with_quarters}
