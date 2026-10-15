"""What a company told the SEC around a price move: its 8-K current reports of the last days, item by item.

    python -m pipeline.events 1045810            # the 8-Ks NVIDIA filed in the last 3 days, with the key sentence

An 8-K lists the events it reports as numbered items (2.02 results, 5.02 an officer leaving or joining, 1.01 a material
agreement …). For a mover, pipeline/engage.py calls explain(): the most material 8-K item filed on the day of the move or
the day before, with one or two sentences of the filing's own text — the earnings release headline for 2.02 and 7.01,
the item's paragraph for everything else — and the SEC link. The post may say what the company filed; it never says the
filing caused the move.
"""
import datetime as dt
import re
import sys

from . import sec, text as T

ITEMS = {
    "1.01": "entered into a material agreement", "1.02": "ended a material agreement", "1.03": "bankruptcy or receivership",
    "1.05": "a material cybersecurity incident", "2.01": "completed an acquisition or disposition",
    "2.02": "results of operations (earnings)", "2.03": "a new financial obligation", "2.04": "a triggering event on debt",
    "2.05": "exit or restructuring costs", "2.06": "a material impairment", "3.01": "a delisting or listing-rule notice",
    "3.02": "an unregistered sale of shares", "3.03": "changes to shareholders' rights", "4.01": "a change of auditor",
    "4.02": "a restatement: earlier financial statements should no longer be relied on", "5.01": "a change in control",
    "5.02": "a director or officer leaving, joining or changing pay", "5.03": "bylaw or fiscal-year changes",
    "5.07": "shareholder vote results", "7.01": "a Regulation FD disclosure (often guidance or a presentation)",
    "8.01": "other events", "9.01": "financial statements and exhibits",
}
# most material first: what most plausibly moves a stock
PRIORITY = ["1.03", "4.02", "1.05", "2.02", "5.01", "2.01", "1.01", "5.02", "2.06", "2.05", "3.01", "2.04", "7.01", "8.01",
            "1.02", "2.03", "3.02", "3.03", "4.01", "5.07", "5.03"]
BOILER = re.compile(r"(?i)^(the information (in|contained in) this|this current report|pursuant to the requirements|"
                    r"forward[- ]looking statements|exhibit (no|number)|signatures?$|item \d\.\d\d)")


def recent_8ks(cik, since, sub=None):
    """[{accn, form, filed, accepted, items, primary}] filed on or after `since` (ISO date), newest first."""
    sub = sub or sec.get_json(sec.submissions_url(cik))
    r = (sub.get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(r.get("form", [])):
        if form not in ("8-K", "8-K/A") or (r["filingDate"][i] or "") < since:
            continue
        items = [x.strip() for x in str((r.get("items") or [""] * (i + 1))[i] or "").split(",") if x.strip()]
        out.append({"accn": r["accessionNumber"][i], "form": form, "filed": r["filingDate"][i],
                    "accepted": (r.get("acceptanceDateTime") or [""] * (i + 1))[i], "items": items,
                    "primary": r["primaryDocument"][i]})
    return out


def _sentences(paras, n=2, limit=420):
    out = []
    for p in paras:
        t = p["text"] if isinstance(p, dict) else str(p)
        if len(t) < 50 or BOILER.search(t):
            continue
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"])", t):
            if len(s) > 30:
                out.append(s.strip())
            if len(out) >= n:
                break
        if len(out) >= n:
            break
    txt = " ".join(out)
    return txt if len(txt) <= limit else txt[:limit].rsplit(" ", 1)[0] + "…"


def _item_text(paras, code):
    """The first sentences after the "Item 5.02" heading of the 8-K body."""
    start = None
    for i, p in enumerate(paras):
        if re.match(rf"(?i)^item\s*{re.escape(code)}\b", p["text"]):
            start = i
    if start is None:
        return ""
    body = []
    for p in paras[start + 1:]:
        if re.match(r"(?i)^item\s*\d\.\d\d\b", p["text"]):
            break
        body.append(p)
    return _sentences(body)


def _exhibit_name(cik, accn, primary):
    idx = sec.get_json(sec.filing_index_url(cik, accn))
    names = [i["name"] for i in idx.get("directory", {}).get("item", []) if re.search(r"\.html?$", i["name"], re.I)]
    for pat in (r"ex[-_]?99[-_.]?0?1(?!\d)", r"ex[-_]?99", r"press|release"):
        hits = [n for n in names if re.search(pat, n, re.I) and n != primary]
        if hits:
            return hits[0]
    return None


def describe(cik, f):
    """The filing's most material item with its key sentences and links."""
    items = [c for c in f["items"] if c in ITEMS and c != "9.01"] or f["items"]
    code = min(items, key=lambda c: PRIORITY.index(c) if c in PRIORITY else 99) if items else None
    url = sec.doc_url(cik, f["accn"], f["primary"])
    quote, source = "", url
    try:
        body = T.paragraphs(sec.get(url))
        quote = _item_text(body, code) if code else ""
        if code in ("2.02", "7.01", "8.01") or not quote:          # the substance is usually in the press release
            ex = _exhibit_name(cik, f["accn"], f["primary"])
            if ex:
                source = sec.doc_url(cik, f["accn"], ex)
                quote = _sentences(T.paragraphs(sec.get(source))) or quote
    except (Exception, SystemExit) as err:
        print(f"::warning::8-K {f['accn']} not read ({str(err)[:120]})")
    return {"code": code, "label": ITEMS.get(code, "a current report"), "items": f["items"], "filed": f["filed"],
            "accepted": f["accepted"], "quote": quote, "url": source, "index": sec.filing_index_url(cik, f["accn"]).replace("/index.json", "/"),
            "form": f["form"]}


def explain(cik, day=None, back_days=1):
    """The most material 8-K filed on `day` (default today, New York) or up to back_days before it, or None."""
    day = day or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)).date()
    since = (day - dt.timedelta(days=back_days + (2 if day.weekday() == 0 else 0))).isoformat()    # Monday: Friday's
    try:
        filings = recent_8ks(cik, since)
    except (Exception, SystemExit) as err:          # SystemExit: SEC_USER_AGENT missing in this workflow
        print(f"::warning::8-Ks of {cik} not listed ({str(err)[:120]})")
        return None
    if not filings:
        return None
    best = min(filings, key=lambda f: min([PRIORITY.index(c) for c in f["items"] if c in PRIORITY] or [99]))
    return describe(cik, best)


if __name__ == "__main__":
    for c in sys.argv[1:]:
        for f in recent_8ks(c, (dt.date.today() - dt.timedelta(days=3)).isoformat()):
            d = describe(c, f)
            print(f"{f['filed']} {f['form']} items {','.join(f['items'])} → {d['code']} {d['label']}\n   {d['quote']}\n   {d['url']}")
