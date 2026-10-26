"""Phase 2: bounded official IR discovery + metadata-only transcript intelligence.

Stacks on Phase 1 without changing its SEC scanner or other disclosure modules.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import earnings_calls as EC
import earnings_call_intel as INT
from core import Client, now, read_json, write_json


def phase2_scan(config, client, previous=None, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    previous = previous or {}
    result = EC.scan(config, client, previous, today)
    old = previous.get("rows") or []
    old_by_id = {r["id"]: r for r in old}
    new_by_id = {r["id"]: r for r in result["rows"]}
    issues = list(result.get("errors") or [])
    per_source = dict(result.get("company_status") or {})
    for co in config.get("companies", []):
        ticker = co["ticker"].upper()
        hosts = co.get("allowed_ir_hosts") or []
        statuses = per_source.setdefault(ticker, {})
        landing_pages = co.get("ir_indexes") or []
        found = []
        for index_url in landing_pages[:config.get("max_ir_indexes_per_company", 2)]:
            if not INT.trusted(index_url, hosts):
                issues.append(ticker + " invalid IR index allowlist")
                statuses["ir_discovery"] = "blocked"
                continue
            try:
                html = client.get(index_url)
                if len(html) > 3_000_000:
                    raise ValueError("IR index too large")
                found += INT.discover_links(index_url, html, hosts, limit=12)
                statuses["ir_discovery"] = "ok"
            except Exception as exc:
                statuses["ir_discovery"] = "partial"
                issues.append(ticker + " IR index: " + str(exc)[:125])
        uniq = {x["url"]: x for x in found}
        found = list(uniq.values())[:config.get("max_discovery_candidates_per_company", 8)]
        for link in found:
            url = link["url"]
            digest = hashlib.sha256(url.encode()).hexdigest()[:18]
            ident = "ir_candidate:" + ticker + ":" + digest
            # Unknown event dates must NOT be populated with an invented filing date.
            prior = old_by_id.get(ident)
            candidate = {
                "id": ident, "ticker": ticker, "kind": "official_ir_candidate",
                "date": prior.get("date") if prior else None,
                "ir_url": url, "candidate_type": link["kind"],
                "label": link["label"], "transcript_status": "discovered_not_verified",
                "discovered_at": prior.get("discovered_at", now()) if prior else now(),
                "source": "Issuer official IR (unverified content)",
            }
            new_by_id[ident] = candidate
        # Limited HTML-only verification. PDFs/audio are link candidates, never
        # misclassified by passing binary data through an HTML parser.
        verified_here = 0
        for link in found:
            if verified_here >= config.get("max_verify_html_per_company", 2):
                break
            if link["kind"] != "transcript_html_candidate" or ".pdf" in link["url"].lower():
                continue
            try:
                html = client.get(link["url"])
                info = EC.inspect_ir_html(html)
                turns = INT.split_turns(html) if info else []
                if not info or not turns or not info.get("event_date"):
                    continue
                event = info["event_date"]
                ident = "ir:" + ticker + ":" + event
                intel = INT.guidance_and_questions(
                    turns, ticker, co.get("management_speakers") or [])
                row = {
                    "id": ident, "ticker": ticker, "kind": "official_ir_transcript",
                    "date": event, "ir_url": link["url"],
                    "source": "Official Investor Relations",
                    **{k: v for k, v in info.items() if k != "event_date"}, **intel,
                    "verified_at": old_by_id.get(ident, {}).get("verified_at", now()),
                }
                new_by_id[ident] = row
                verified_here += 1
            except Exception as exc:
                issues.append(ticker + " transcript: " + str(exc)[:125])
                statuses["ir_verification"] = "partial"

    # Add question/quant analytics to Phase-1-verified HTML sources.
    max_enrich = config.get("max_enrich_verified_per_run", 6)
    enriched = 0
    for r in sorted(new_by_id.values(), key=lambda x: x.get("date") or "", reverse=True):
        if r.get("kind") != "official_ir_transcript":
            continue
        if r.get("guidance") is not None and r.get("quantitative_exercises") is not None:
            continue
        if enriched >= max_enrich:
            # Retain earlier approved intelligence if present.
            old_r = old_by_id.get(r["id"], {})
            for key in ("guidance", "analyst_questions", "qa_topic_counts",
                        "quantitative_exercises", "qa_count_detected", "extraction"):
                if key in old_r:
                    r[key] = old_r[key]
            continue
        ir = r.get("ir_url", "")
        cfg = next((x for x in config["companies"] if x["ticker"].upper() == r["ticker"]), None)
        if not cfg or not INT.trusted(ir, cfg.get("allowed_ir_hosts") or []):
            continue
        try:
            turns = INT.split_turns(client.get(ir))
            if not turns:
                continue
            r.update(INT.guidance_and_questions(turns, r["ticker"],
                                                 cfg.get("management_speakers") or []))
            r["verified_at"] = old_by_id.get(r["id"], {}).get("verified_at", now())
            enriched += 1
        except Exception as exc:
            issues.append(r["ticker"] + " analysis: " + str(exc)[:125])
            for key in ("guidance", "analyst_questions", "qa_topic_counts",
                        "quantitative_exercises", "qa_count_detected", "extraction"):
                if key in old_by_id.get(r["id"], {}):
                    r[key] = old_by_id[r["id"]][key]

    # Only compare the same exact fiscal guidance horizon and reporting units.
    for ticker in {r["ticker"] for r in new_by_id.values()}:
        histories = sorted((r for r in new_by_id.values() if r["ticker"] == ticker
                            and r.get("kind") == "official_ir_transcript"),
                           key=lambda x: x.get("date") or "")
        for idx, row in enumerate(histories):
            prior = histories[:idx]
            row["guidance_changes"] = INT.guidance_changes(row, prior)
            if prior:
                latest = prior[-1]
                current_counts, old_counts = row.get("qa_topic_counts", {}), latest.get("qa_topic_counts", {})
                row["qa_topic_changes"] = {
                    k: current_counts.get(k, 0) - old_counts.get(k, 0)
                    for k in set(current_counts) | set(old_counts)
                    if current_counts.get(k, 0) != old_counts.get(k, 0)
                }
                row["comparison_period"] = latest.get("date")

    # Preserve verified_at across routine re-scans, so Flo never mistakes a
    # refresh of the same transcript for a fresh conference call.
    for row in new_by_id.values():
        if row["kind"] == "official_ir_transcript":
            row["verified_at"] = old_by_id.get(row["id"], {}).get("verified_at", row.get("verified_at", now()))
    rows = sorted(new_by_id.values(), key=lambda r: (r.get("date") or "", r["id"]), reverse=True)
    result.update({
        "version": 2, "rows": rows[:500], "company_status": per_source,
        "errors": issues[:50], "status": "partial" if issues else "ok",
        "counts": {
            "official_transcripts": sum(r["kind"] == "official_ir_transcript" for r in rows),
            "official_ir_candidates": sum(r["kind"] == "official_ir_candidate" for r in rows),
            "sec_earnings_evidence": sum(r["kind"] == "sec_earnings_evidence" for r in rows),
            "guidance_ranges": sum(len(r.get("guidance", [])) for r in rows),
            "quantitative_exercises": sum(len(r.get("quantitative_exercises", [])) for r in rows),
        },
        "latest_source_date": max((r.get("date") or "" for r in rows), default="") or None,
        "rights": "Public metadata and original-source links only; calculations based on unreconciled management speech.",
    })
    # A partial batch never overwrites the last globally complete scan timestamp.
    result["last_success"] = now() if not issues else previous.get("last_success")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EC.ROOT / "config/earnings_calls.json")
    parser.add_argument("--output", type=Path, default=EC.ROOT / "docs/data/earnings-calls/index.json")
    parser.add_argument("--storage", type=Path, default=EC.ROOT / "storage/earnings-calls")
    args = parser.parse_args()
    config = read_json(args.config, {})
    cfg = read_json(EC.ROOT / "config/settings.json", {})
    options = dict(cfg.get("http", {}))
    options["extra_hosts"] = sorted({host for co in config.get("companies", [])
                                     for host in co.get("allowed_ir_hosts", [])})
    client = Client(args.storage, options)
    out = phase2_scan(config, client, read_json(args.output, {}))
    write_json(args.output, out)
    print(json.dumps({"status": out["status"], "counts": out["counts"], "errors": out["errors"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
