"""Page audit: what the site is about to publish, checked company by company (run by scan.yml on every scan).

For every company on the site (data/index.json) and every period of its chart file (data/c/<cik>.json):
  label      a revenue line named like something that is not revenue — a balance-sheet item, an expense, a per-share
             figure, a volume, a table caption ("Three Months Ended …") or XBRL furniture ("[Member]", "This member
             stands for …"). Apple, Starbucks, Visa and Delta all had one in Nov 2026.
  mixed      an earnings release's lines that mix regions with products under one parent (Apple Q4 FY26)
  sum        lines that do not add up to revenue (1%), unless the chart says they add up to contract revenue
  leaf       a line larger than revenue
  page       the company's static page (c/<slug>/) missing, or showing another quarter or revenue than its data
  old8k      a preliminary quarter (8-K) still drawn 75 days after it was filed: its 10-Q / 10-K was not read
  data       a company in the index without its data file
Writes data/page-audit.json (the newest periods first), prints a summary, and with --github the worst items as
warnings and a table in the run's summary. It never stops the publish.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402

NONREV = re.compile(
    r"payable|receivable|goodwill|\binventor(y|ies)\b(?!.*(sales|revenue))|\bdebt\b|borrowings|liabilit|stockholders'|"
    r"shareholders'|retained earnings|intangible|accrued|salar|wages|weighted average|per (common |diluted |basic )?(share|unit)|"
    r"\bshares\b|\bvolumes?\b|\bmbpd\b|mmcf|\(in (millions|thousands)|three months|six months|nine months|"
    r"years? ended|fiscal q\d|non-gaap|\badjusted\b|ebitda|ebita\b|dividends? declared|earnings applicable|"
    r"preferred stock dividends|extinguishment|air traffic liability|sales volume|"
    r"^costs? of|\bexpenses$|^occupancy and|^professional fees$|^depreciation|^net (income|earnings|loss)\b|"
    r"income tax|stands for|element represents|\[(member|domain)\]|exchange (gain|loss)|^total assets|"
    r"except per|average (effective|daily|price|rate)", re.I)
# a line that says what kind of revenue it is ("debt placement fees", "minimum volume commitments", "reimbursed
# expenses", "sales of uranium inventory") is revenue, unless it is a cost or a caption whatever else it says
REVLIKE = re.compile(r"\b(revenues?|sales|fees?|commissions?|royalt(y|ies)|reimburs(ed|able|ements?)|minimum volume|"
                     r"volume[- ](based|related)|rentals?|subscriptions?|services?|products?)\b", re.I)
HARD = re.compile(r"^costs? of|research and development expenses?|stands for|element represents|\[(member|domain)\]|"
                  r"per (common |diluted |basic )?(share|unit)|weighted average|three months|six months|nine months|"
                  r"years? ended|\(in (millions|thousands)|^net (income|earnings|loss)\b|income tax|ebitda|non-gaap", re.I)
GEO = re.compile(r"\b(americas?|north america|latin america|south america|europe|emea|apac|asia|pacific|china|japan|"
                 r"india|germany|france|united kingdom|united states|u\.s\.|canada|mexico|brazil|korea|taiwan|"
                 r"australia|middle east|africa|international|domestic|rest of (the )?world|other countries)\b", re.I)
ORDER = ("data", "label", "mixed", "leaf", "page", "sum", "old8k")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def name(n):
    return html.unescape(n.get("name") or "")


def check_period(q):
    """Problems of one drawn period: [(check, detail)]."""
    out = []
    nodes = q.get("nodes") or []
    byid = {n["id"]: n for n in nodes}
    R = (byid.get("revenue") or {}).get("v")
    leaves = [n for n in nodes if n["id"].startswith("L:")]
    groups = [n for n in nodes if n["id"].startswith("G:")]
    if not leaves or not R:
        return out
    bad = [name(n) for n in leaves + groups if NONREV.search(name(n)) and (HARD.search(name(n)) or not REVLIKE.search(name(n)))]
    if bad:
        out.append(("label", "; ".join(bad)[:200]))
    codes = {c.get("code") for c in q.get("checks") or []}
    s = sum(n.get("v") or 0 for n in leaves)
    if abs(s - R) > 0.01 * abs(R) and "revenue_recon" not in codes:
        out.append(("sum", f"lines {s / 1e6:,.1f}M vs revenue {R / 1e6:,.1f}M ({(s - R) / R:+.1%})"))
    C = (byid.get("contract") or {}).get("v") if "revenue_recon" in codes else None   # lines into contract revenue
    big = [name(n) for n in leaves if (n.get("v") or 0) > 1.02 * max(R, C or 0)]      # (Continental: hedging losses)
    if big:
        out.append(("leaf", ", ".join(big)[:200]))
    if q.get("form") == "8-K":
        under = {}
        for link in q.get("links") or []:
            if str(link.get("s", "")).startswith("L:"):
                under.setdefault(link.get("t"), []).append(name(byid.get(link["s"], {})))
        for parent, labs in under.items():
            g = [x for x in labs if GEO.search(x)]
            if len(g) >= 2 and len(labs) - len(g) >= 2:
                out.append(("mixed", f"regions {g} with {[x for x in labs if x not in g]}"[:200]))
    return out


def audit(site, today=None):
    today = today or dt.date.today()
    data = os.path.join(site, "data")
    ix = _load(os.path.join(data, "index.json")) or {}
    items = []
    for r in ix.get("companies") or []:
        cik, tk = r.get("cik"), r.get("ticker") or str(r.get("cik"))
        c = _load(os.path.join(data, "c", f"{cik}.json"))
        if not c:
            items.append({"ticker": tk, "cik": cik, "period": r.get("label"), "latest": True, "check": "data",
                          "detail": "in the index, no data file"})
            continue
        periods = [(q, i == 0) for i, q in enumerate(c.get("quarters") or [])] + [(y, False) for y in c.get("years") or []]
        for q, latest in periods:
            for check, detail in check_period(q):
                items.append({"ticker": tk, "cik": cik, "period": f"{q.get('label')} {q.get('form', '')}".strip(),
                              "latest": latest, "check": check, "detail": detail})
        q0 = (c.get("quarters") or [{}])[0]
        if q0.get("form") == "8-K" and q0.get("filed"):
            age = (today - dt.date.fromisoformat(q0["filed"])).days
            if age > 75:
                items.append({"ticker": tk, "cik": cik, "period": q0.get("label"), "latest": True, "check": "old8k",
                              "detail": f"preliminary quarter filed {q0['filed']} ({age} days): its 10-Q / 10-K not read"})
        page = os.path.join(site, "c", seo.slug_for(r), "index.html")
        if os.path.isdir(os.path.join(site, "c")):
            if not os.path.exists(page):
                items.append({"ticker": tk, "cik": cik, "period": r.get("label"), "latest": True, "check": "page",
                              "detail": f"no static page c/{seo.slug_for(r)}/"})
            else:
                head = open(page, encoding="utf-8", errors="replace").read(6000)
                rev_fmt = (q0.get("headline") or {}).get("rev_fmt") or ""
                want = list(figures(rev_fmt))
                # the page rounds to three digits ($627M for the data's $627.0M): the same figure within either's rounding
                if want and not any(abs(v - w) <= h + hw + 1e-9 for w, hw in want[:1] for v, h in figures(head)):
                    items.append({"ticker": tk, "cik": cik, "period": r.get("label"), "latest": True, "check": "page",
                                  "detail": f"static page does not show this quarter's revenue ({rev_fmt})"})
    items.sort(key=lambda x: (not x["latest"], ORDER.index(x["check"]), x["ticker"]))
    counts = {k: {"periods": sum(1 for x in items if x["check"] == k),
                  "latest": sum(1 for x in items if x["check"] == k and x["latest"])} for k in ORDER}
    return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "companies": len(ix.get("companies") or []),
            "counts": counts, "items": items}


SCALE = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
MONEY = re.compile(r"(?<![\w.])(?:[A-Z]{1,3})?[$€£¥₹]\s?(\d[\d,]*(?:\.\d+)?)\s?([KMBT])?(?![\w])")


def figures(text):
    """Every money figure in a text: (value, half its last digit) — "$627M" is 627e6 give or take 0.5e6."""
    for m in MONEY.finditer(text or ""):
        num, unit = m.group(1).replace(",", ""), m.group(2) or ""
        dec = len(num.split(".")[1]) if "." in num else 0
        yield float(num) * SCALE[unit], 0.5 * 10 ** -dec * SCALE[unit]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default="_site")
    ap.add_argument("--out", default=None, help="default: <site>/data/page-audit.json")
    ap.add_argument("--github", action="store_true", help="warnings and a step summary for GitHub Actions")
    a = ap.parse_args(argv)
    rep = audit(a.site)
    out = a.out or os.path.join(a.site, "data", "page-audit.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, separators=(",", ":"))
    line = ", ".join(f"{k} {v['latest']}/{v['periods']}" for k, v in rep["counts"].items())
    print(f"page audit of {rep['companies']} companies (latest quarter / all periods): {line}")
    worst = [x for x in rep["items"] if x["latest"] and x["check"] in ("data", "label", "mixed", "leaf", "page")]
    for x in worst[:25]:
        msg = f"page audit · {x['check']} · {x['ticker']} {x['period']}: {x['detail']}"
        print(f"::warning::{msg}" if a.github else msg)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if a.github and summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Page audit\n{rep['companies']} companies. Latest quarter / all periods: {line}\n\n")
            f.write("| check | company | period | detail |\n|---|---|---|---|\n")
            for x in worst[:60]:
                f.write(f"| {x['check']} | {x['ticker']} | {x['period']} | {x['detail'].replace('|', '/')} |\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
