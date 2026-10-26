"""Official IR transcript discovery + SEC 8-K Item 2.02 evidence.

SEC 8-K is an earnings-release signal, NEVER a transcript. Only approved
company IR pages with validated transcript content are labeled as transcripts.
All publicly published records are metadata and source links (no wholesale
third-party text redistribution). Raw fetched bytes stay in storage/ and are
not shipped by the Pages build.
"""
import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, urlparse

from core import Client, now, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SPEAKER = re.compile(r"(?m)^([A-Z][A-Z .,'-]{4,65}):\s*$")
TRANSCRIPT = re.compile(r"(?im)^\s*Transcript\s*$")
DATE = re.compile(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
                  r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
                  r"\s+\d{1,2},?\s+\d{4})", re.I)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "noscript"):
            self.skip += 1
        if not self.skip and tag in ("p", "div", "section", "br", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "noscript"):
            self.skip = max(0, self.skip - 1)
        if not self.skip and tag in ("p", "div", "section", "br", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        return "\n".join(re.sub(r"\s+", " ", l).strip() for l in raw.splitlines() if l.strip())


def inspect_ir_html(body):
    """Require a visible transcript section AND named speaker turns; no guessing."""
    parser = VisibleText()
    parser.feed(body.decode("utf-8", "replace"))
    text = parser.text()
    match = TRANSCRIPT.search(text)
    if not match:
        return None
    section = text[match.end():]
    speakers = sorted(set(SPEAKER.findall(section)))
    if len(section) < 1500 or len(speakers) < 2:
        return None
    date_match = DATE.search(text[:match.end() + 300])
    event_date = None
    if date_match:
        try:
            event_date = dt.datetime.strptime(date_match.group(1).replace(",", ""), "%B %d %Y").date().isoformat()
        except ValueError:
            pass
    return {
        "transcript_status": "verified_official_link",
        "speaker_count": len(speakers),
        "content_sha256": hashlib.sha256(section.encode("utf-8")).hexdigest(),
        "event_date": event_date,
        "validation": "heading_and_multiple_speaker_turns",
    }


def sec_evidence(payload, ticker, cik, today, days=180, limit=8):
    """Only 8-K Item 2.02; do not mislabel as a conference call."""
    recent = ((payload.get("filings") or {}).get("recent") or {})
    items = []
    forms = recent.get("form") or []
    cutoff = today - dt.timedelta(days=days)
    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue
        filing_items = str((recent.get("items") or [""] * len(forms))[i])
        if "2.02" not in [x.strip() for x in filing_items.split(",")]:
            continue
        try:
            filed = str(recent["filingDate"][i])[:10]
            accession = str(recent["accessionNumber"][i])
            doc = str(recent["primaryDocument"][i])
            if dt.date.fromisoformat(filed) < cutoff:
                continue
            if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                continue
            if not re.fullmatch(r"[a-zA-Z0-9._-]+", doc) or doc.startswith("."):
                continue
        except (IndexError, KeyError, ValueError, TypeError):
            continue
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
               f"{accession.replace('-', '')}/{quote(doc)}")
        items.append({
            "id": "sec:" + accession, "ticker": ticker, "kind": "sec_earnings_evidence",
            "date": filed, "filed_date": filed, "accession": accession,
            "form": form, "items": filing_items, "sec_url": url,
            "transcript_status": "not_verified",
            "note": "8-K Item 2.02 earnings disclosure, not an earnings-call transcript.",
        })
        if len(items) >= limit:
            break
    return items


def microsoft_candidates(today):
    """Last two fiscal quarters + current quarter. 404 is an expected future event."""
    fy = today.year + (1 if today.month >= 7 else 0)
    quarter = ((today.month - 7) % 12) // 3 + 1
    result = []
    for offset in (0, -1, -2):
        ordinal = (fy * 4 + quarter - 1) + offset
        y, q0 = divmod(ordinal, 4)
        result.append(f"https://www.microsoft.com/en-us/investor/events/fy-{y}/earnings-fy-{y}-q{q0 + 1}")
    return result


def _trusted(url, hosts):
    p = urlparse(url)
    return p.scheme == "https" and p.hostname in set(hosts) and not p.username and not p.password


def scan(config, client, previous=None, today=None):
    previous = previous or {}
    today = today or dt.datetime.now(dt.timezone.utc).date()
    old_rows = previous.get("rows") or []
    rows, errors, company_status = [], [], {}
    for company in config.get("companies", []):
        ticker = company["ticker"].upper()
        cik = int(company["cik"])
        old_sec = [r for r in old_rows if r.get("ticker") == ticker and r.get("kind") == "sec_earnings_evidence"]
        old_ir = [r for r in old_rows if r.get("ticker") == ticker and r.get("kind") == "official_ir_transcript"]
        c_status = {"sec": "ok", "ir": "unconfigured", "last_attempt": now()}
        try:
            response = client.json(SEC_SUBMISSIONS.format(cik=cik), sec=True)
            sec_rows = sec_evidence(response, ticker, cik, today, config.get("lookback_days", 180))
        except Exception as exc:
            sec_rows = old_sec
            c_status["sec"] = "error"
            errors.append(ticker + " SEC: " + str(exc)[:150])
        rows.extend(sec_rows)
        hosts = company.get("allowed_ir_hosts") or []
        urls = list(company.get("ir_event_pages") or [])
        if company.get("microsoft_autodiscover"):
            urls += microsoft_candidates(today)
        if urls:
            c_status["ir"] = "pending"
        valid = []
        seen = set()
        for url in urls[:config.get("max_ir_pages_per_company", 6)]:
            if url in seen:
                continue
            seen.add(url)
            if not _trusted(url, hosts):
                errors.append(ticker + " IR: rejected unapproved host")
                c_status["ir"] = "error"
                continue
            try:
                body = client.get(url)
                if len(body) > 3_000_000:
                    raise ValueError("IR page too large")
                info = inspect_ir_html(body)
                if not info:
                    continue
                event_date = info["event_date"] or company.get("seed_event_dates", {}).get(url)
                if not event_date:
                    continue  # no chronology without a date
                row = {
                    "id": "ir:" + ticker + ":" + event_date, "ticker": ticker,
                    "kind": "official_ir_transcript", "date": event_date,
                    "ir_url": url, "source": "Official Investor Relations",
                    **{k: v for k, v in info.items() if k != "event_date"}
                }
                nearest = sorted(sec_rows, key=lambda s: abs((dt.date.fromisoformat(s["date"]) - dt.date.fromisoformat(event_date)).days))
                if nearest and abs((dt.date.fromisoformat(nearest[0]["date"]) - dt.date.fromisoformat(event_date)).days) <= 7:
                    row["sec_url"] = nearest[0]["sec_url"]
                    row["sec_accession"] = nearest[0]["accession"]
                valid.append(row)
            except Exception as exc:
                # A forecast event URL can legitimately be 404 before the call takes place.
                if "HTTP 404" in str(exc):
                    continue
                errors.append(ticker + " IR: " + str(exc)[:150])
                c_status["ir"] = "error"
        ir_by_id = {r["id"]: r for r in old_ir}
        for row in valid:
            ir_by_id[row["id"]] = row
        rows.extend(ir_by_id.values())
        if valid and c_status["ir"] != "error":
            c_status["ir"] = "ok"
        company_status[ticker] = c_status
    uniq = {r["id"]: r for r in rows}
    rows = sorted(uniq.values(), key=lambda r: (r.get("date") or "", r["id"]), reverse=True)
    status = "partial" if errors else "ok"
    return {
        "version": 1, "source": "SEC EDGAR + issuer official IR",
        "generated_at": now(), "last_attempt": now(),
        "last_success": now() if status == "ok" else previous.get("last_success"),
        "status": status, "errors": errors[:30],
        "company_status": company_status, "rows": rows[:300],
        "counts": {"official_transcripts": sum(r["kind"] == "official_ir_transcript" for r in rows),
                   "sec_earnings_evidence": sum(r["kind"] == "sec_earnings_evidence" for r in rows)},
        "latest_source_date": max((r["date"] for r in rows), default=None),
        "rights": "Metadata and source links only; full transcripts remain on official IR sites.",
    }


def main():
    ap = argparse.ArgumentParser(description="Official IR transcript and SEC earnings-evidence scanner")
    ap.add_argument("--config", type=Path, default=ROOT / "config/earnings_calls.json")
    ap.add_argument("--output", type=Path, default=ROOT / "docs/data/earnings-calls/index.json")
    ap.add_argument("--storage", type=Path, default=ROOT / "storage/earnings-calls")
    args = ap.parse_args()
    config = read_json(args.config, {})
    settings = read_json(ROOT / "config/settings.json", {})
    options = dict(settings.get("http") or {})
    options["extra_hosts"] = sorted({h for c in config.get("companies", []) for h in c.get("allowed_ir_hosts", [])})
    client = Client(args.storage, options)
    result = scan(config, client, read_json(args.output, {}))
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "counts": result["counts"],
                      "errors": result["errors"], "last_attempt": result["last_attempt"]}))
    # Do not abort after partial failures: keep last-known-good evidence and commit per-source health.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
