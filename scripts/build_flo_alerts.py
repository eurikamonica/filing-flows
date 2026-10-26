"""Build compact Flo events from staged public data. No direct SEC network calls."""
import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import re

SEC = re.compile(r"^https://(?:www\.)?sec\.gov/Archives/")
NEWS = re.compile(r"^https://(?:www\.)?(?:sec\.gov|prnewswire\.com|fda\.gov)/")
SEC_BROWSE = re.compile(r"^https://(?:www\.)?sec\.gov/edgar/browse/\?CIK=\d+&owner=exclude$")
TK = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
HIGH = {"bankruptcy", "restatement", "cyber", "delisting", "impairment", "auditor"}
MED = {"deal", "control", "offering", "debt", "guidance", "ceo", "cfo"}


def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def date(value, eastern=False):
    try:
        s = str(value or "").strip()
        if len(s) == 10:
            s += "T00:00:00+00:00"
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo('America/New_York') if eastern else timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def stamp(value, eastern=False):
    d = date(value,eastern=eastern)
    return d.isoformat().replace("+00:00", "Z") if d else ""


def recent(value, now, days=4):
    d = date(value)
    return bool(d and now - timedelta(days=days) <= d <= now + timedelta(minutes=5))


def small(value, maximum=160):
    return " ".join(str(value or "").split())[:maximum]


def symbol(value):
    s = small(value, 10).upper()
    return s if TK.fullmatch(s) else ""


def build(root, now=None):
    now = now or datetime.now(timezone.utc)
    events = []
    statuses = {}
    k8 = read(root / "events8k.json")
    statuses["8k"] = k8.get("generated_at") or k8.get("updated_at") or ""
    for r in (k8.get("rows") or [])[:600]:
        if not isinstance(r, dict) or r.get("form", "8-K") not in ("8-K", "8-K/A"):
            continue
        tk, acc, url = symbol(r.get("ticker")), small(r.get("accession"), 36), str(r.get("url") or "")
        filed = str(r.get("filed") or "")
        if not tk or not acc or not SEC.match(url) or not recent(r.get("accepted") or filed, now):
            continue
        topics = [v for v in (r.get("topics") or []) if isinstance(v, str)]
        if not topics and (r.get("score") or 0) < 3:
            continue
        pr = "high" if HIGH.intersection(topics) else "medium" if MED.intersection(topics) else "info"
        events.append(dict(id="8k:" + acc, kind="8k", ticker=tk, priority=pr,
            title=small(r.get("headline") or r.get("label") or "New 8-K"),
            detail=small(r.get("guidance_quote") or r.get("quote"), 180),
            event_at=stamp(r.get("accepted"),eastern=True) if r.get("accepted") else stamp(filed), filed=filed[:10],
            form=r.get("form") or "8-K", topics=topics[:5], accession=acc, source_url=url, source_label="SEC 8-K",
            scope="An SEC filing, not a price forecast."))
    f13 = read(root / "watchlist.json")
    statuses["13f"] = f13.get("generated_at") or ""
    for r in (f13.get("funds") or [])[:100]:
        if not isinstance(r, dict):
            continue
        cik, filed, period, url = str(r.get("cik") or ""), str(r.get("filed") or ""), str(r.get("period") or ""), str(r.get("source") or "")
        if not cik.isdecimal() or not SEC.match(url) or not recent(filed, now, 7):
            continue
        changes = {}
        symbols = []
        for label,field in (("New","new"),("Added","added"),("Reduced","cut"),("Exited","exited")):
            vals=[symbol(x.get("ticker")) for x in (r.get(field) or [])[:25] if isinstance(x,dict)]
            vals=[x for x in vals if x]
            changes[label] = vals[:3]
            symbols.extend(vals[:10])
        symbols=list(dict.fromkeys(symbols))[:40]
        tk = symbols[0] if symbols else ""
        name = small(r.get("name") or r.get("filer") or "Institution")
        summary = "; ".join(label + ": " + ", ".join(vals) for label, vals in changes.items() if vals)
        events.append(dict(id="13f:" + cik + ":" + period + ":" + filed,
            kind="13f", ticker=tk, symbols=symbols, manager=name,
            priority="medium" if symbols else "info",
            title=name + " filed 13F",
            detail=small("Quarter ended " + period + (". " + summary if summary else ". Positions disclosed."),210),
            changes=changes, event_at=stamp(filed), filed=filed[:10], period_end=period,
            source_url=url, source_label="SEC 13F",
            scope="Holdings as of quarter-end, not trading actions on filing date."))
    # The tracked-manager watchlist is valuable for ticker-level change detail, but
    # it can still display the PREVIOUS quarter after a new SEC filing arrived.
    # Discover newer official 13F filing dates from the scan's main catalog, without
    # falsely assigning trades or portfolio changes to the filing date.
    try:
        with (root.parent / "catalogs" / "holdings.json").open(encoding="utf-8") as stream:
            catalog = json.load(stream)
    except (OSError, ValueError, UnicodeError):
        catalog = []
    if isinstance(catalog, list):
        for r in catalog:
            if not isinstance(r, dict) or r.get("kind") != "holdings":
                continue
            cik = str(r.get("cik") or "")
            filed = str(r.get("latest_filing") or "")
            if not cik.isdecimal() or not recent(filed, now, 7):
                continue
            # If a full tagged watchlist record exists for this same CIK/date,
            # prefer its specific EDGAR filing source and position details.
            if any(e.get("kind") == "13f" and e.get("id", "").startswith("13f:" + cik + ":")
                   and e.get("filed") == filed for e in events):
                continue
            link = "https://www.sec.gov/edgar/browse/?CIK=" + cik + "&owner=exclude"
            if not SEC_BROWSE.fullmatch(link):
                continue
            events.append(dict(
                id="13f:" + cik + ":indexed:" + filed, kind="13f", ticker="",
                priority="info", title=small(r.get("name") or "Institution") + " — 13F indexed",
                manager=small(r.get("name") or "Institution"), detail=(
                    "New SEC filing date indexed; holding rows " +
                    ("processed" if r.get("processed") is True else "not fully processed") +
                    ". Individual position changes are not inferred."),
                event_at=stamp(filed), filed=filed[:10], period_end="",
                parsed=r.get("processed") is True, source_url=link, source_label="SEC 13F catalog",
                scope="Indexed 13F notice, not a filing-day trade, quarter-end date, or proof of a full parsed holdings table."
            ))
    news = read(root / "news.json")
    statuses["news"] = news.get("generated_at") or ""
    for r in (news.get("rows") or [])[:300]:
        if not isinstance(r, dict) or not recent(r.get("published"), now, 2):
            continue
        symbols = [symbol(x) for x in (r.get("tickers") or [])]
        symbols = [x for x in symbols if x]
        url = str(r.get("url") or "")
        if not symbols or not NEWS.match(url):
            continue
        category = str(r.get("kind") or "release")
        events.append(dict(id="news:" + small(r.get("id") or url, 190),kind="news",
            ticker=symbols[0],priority="medium" if category in ("sec_action", "suspension", "fda") else "info",
            title=small(r.get("title")),symbols=symbols[:12],detail=small(r.get("source"), 80),
            event_at=stamp(r.get("published")),source_url=url,
            source_label=small(r.get("source") or "News", 50),
            scope="Headline from external source; its claims are not independently verified."))
    px = read(root / "extremes.json")
    statuses["price"] = px.get("generated_at") or ""
    cols = {str(k): i for i, k in enumerate(px.get("fields") or [])}
    last = next((cols[k] for k in ("close", "last", "price") if k in cols), None)
    ret = next((cols[k] for k in ("chg1d", "r1d", "day_change", "change", "pct_change", "ret_1d") if k in cols), None)
    tk_col = cols.get("ticker")
    # Optional end-of-day index context, sourced ONLY from this same as-of file.
    # A separate SPY/QQQ/IWM quote is not available for most daily extremes
    # files; in that case emit no benchmark rather than manufacture one.
    benchmarks = {}
    if None not in (last, ret, tk_col) and recent(px.get("asof"), now, 3):
        for row in (px.get("rows") or [])[:5000]:
            if not isinstance(row, list) or max(last, ret, tk_col) >= len(row):
                continue
            tk = symbol(row[tk_col])
            if tk not in ("SPY", "QQQ", "IWM") or tk in benchmarks:
                continue
            try:
                change, close = float(row[ret]), float(row[last])
            except (ValueError, TypeError, OverflowError):
                continue
            if not (-1 < change <= 5 and 0 < close < 1e8):
                continue
            benchmarks[tk] = {"asof": str(px.get("asof"))[:10],
                              "close": round(close, 4),
                              "change_pct": round(change * 100, 3),
                              "source": "same published extremes.json snapshot"}
    if None not in (last, ret, tk_col) and recent(px.get("asof"), now, 3):
        for row in (px.get("rows") or [])[:5000]:
            if not isinstance(row, list) or max(last, ret, tk_col) >= len(row):
                continue
            tk = symbol(row[tk_col])
            try:
                chg, close = float(row[ret]), float(row[last])
            except (ValueError, TypeError, OverflowError):
                continue
            if not tk or not (-1 <= chg <= 5) or close <= 0 or abs(chg) < .05:
                continue
            day = str(px.get("asof"))[:10]
            events.append(dict(id="price:" + tk + ":" + day,kind="price",ticker=tk,
                priority="medium" if abs(chg) >= .10 else "info",
                title=tk + " daily close " + format(chg, "+.1%"),
                detail="Close $" + format(close, ",.2f") + "; daily change " + format(chg, "+.1%") + ". Not a live quote.",
                event_at=stamp(day),price_asof=day,price=close,change_pct=round(100*chg,2),
                source_url="",source_label="Filing Flows daily-close snapshot",
                scope="Delayed daily close; NOT live/intraday price action."))
    events.sort(key=lambda x:(x["event_at"],{"high":2,"medium":1,"info":0}[x["priority"]]),reverse=True)
    unique = {}
    per_type = {"8k": 0, "13f": 0, "news": 0, "price": 0}
    for e in events:
        kind = e["kind"]
        if e["id"] in unique or per_type[kind] >= 30:
            continue
        unique[e["id"]] = e
        per_type[kind] += 1
        if len(unique) >= 120:
            break
    # Scan execution health is distinct from publication time and event date.
    # A partial/failed scan must never be presented as an up-to-date success.
    health = {}
    for kind, file in (("8k", "events8k-status.json"), ("news", "news-status.json"),
                       ("13f", "holdings-status.json"), ("price", "extremes-status.json")):
        stat = read(root.parent / file)
        if stat:
            health[kind] = {
                "status": small(stat.get("status") or "unknown", 18),
                "last_attempt": stamp(stat.get("last_attempt")),
                "last_success": stamp(stat.get("last_success") or stat.get("last_partial_success")),
                "latest_filing_date": small(stat.get("latest_filing_date"), 12),
                "failed_queue": stat.get("failed_queue") if isinstance(stat.get("failed_queue"), int) else None,
            }
    return dict(schema=1,generated_at=stamp(now),sources=statuses,scan_health=health,
        benchmarks=benchmarks,
        cadence="Only newly published static snapshots. GitHub Pages publishing may lag collecting.",
        events=list(unique.values()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("_site/disclosures/data/market"))
    a = p.parse_args()
    out = build(a.root)
    a.root.mkdir(parents=True, exist_ok=True)
    dest = a.root / "flo-alerts.json"
    dest.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("Flo alerts",len(out["events"]),"items",dest.stat().st_size,"bytes")


if __name__=="__main__":
    main()
