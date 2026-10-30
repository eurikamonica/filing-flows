"""Forward-looking statements: what a company says it expects, in its own words, filing after filing — no language model.

Read from the MD&A of each 10-Q / 10-K (Item 2 / Item 7) and from each earnings release (8-K Exhibit 99), the sentences
in which the company looks ahead ("we expect", "we anticipate", "we plan to", "remains on track", "for fiscal 2027 we
target …"), leaving out the boilerplate (the safe-harbor paragraph, accounting standards to be adopted, "sufficient to
fund our operations for the next twelve months", option-pricing assumptions …). Each statement gets:

  topic   demand and revenue, margins and pricing, costs, capital spending, capital returns, financing, people and
          restructuring, deals, products, regulation and legal, tax, backlog and orders, AI
  tone    positive / negative / neutral (growth, improve, strong … against decline, pressure, headwind …)
  hedge   whether it is qualified (may, could, uncertain, subject to …)
  when    the period it is about when it names one ("fiscal 2027", "the fourth quarter", "second half")
  status  new / repeated / updated against the same kind of document before it (MD&A to MD&A, release to release);
          the statements of that earlier document no longer said are kept as "dropped"

and the guided figures among them (disclosures/app/guidance.py read(): "we expect capital expenditures of $1.2 to $1.4
billion for fiscal 2027"), which join the guidance record and its hit rate on the company page.

Store: <store>/outlook/<cik>.json {'cik', 'docs': [{kind ('mdna' | 'release'), form, accn, filed, end, url, statements,
dropped, items, counts}] newest first}. The main scan keeps each new filing's (build.py), and catches up a few
companies per run from their latest 10-Q / 10-K (refresh). publish → <out>/<cik>.json for the site.

    python -m pipeline.outlook publish --store store --out _site/data/outlook
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "disclosures" / "app"))

KEEP = 10                      # documents kept per company
REFRESH_PER_RUN = 30           # companies caught up per scan

FWD = re.compile(r"(?i)\b(?:expect(?:s|ed|ing)?|anticipat(?:e|es|ed|ing)|plan(?:s|ned)? to|intend(?:s|ed)? to|project(?:s|ed)?|"
                 r"forecast(?:s|ed)?|estimates? that|target(?:s|ed|ing)?|aim(?:s)? to|on track|outlook|guidance|going forward|"
                 r"we will|we'll|will (?:continue|remain|be|increase|decrease|grow|decline|benefit|impact|begin|complete|launch|"
                 r"reduce|improve|moderate|accelerate)|look forward to|believe .{0,80}\bwill\b|remain(?:s)? confident|"
                 r"(?:could|may|will likely) (?:pressure|weigh on|offset|reduce|lower|hurt|delay))\b")
WHO = re.compile(r"(?i)\b(?:we|our|us|the company|management)\b")
BOILER = re.compile(r"(?i)forward[- ]looking (?:statements?|information)|private securities litigation|safe harbor|actual results (?:may|could|might) "
                    r"differ|undue reliance|no obligation to (?:update|revise)|undertake no|cautionary|risk factors|could cause (?:actual|our)|"
                    r"differ materially|see (?:part|item) |intended to (?:provide|help|assist)|assist (?:the )?readers?|should (?:be )?read (?:this|in conjunction)|"
                    r"materially different from what we expect|good faith estimate|the following (?:discussion|management)")
SKIP = re.compile(r"(?i)\bASU\b|accounting (?:standards?|pronouncements?|guidance)|recently (?:issued|adopted)|(?:upon|on|the) adoption|"
                  r"effective for (?:fiscal|annual|interim)|not expect .{0,60}material (?:impact|effect)|sufficient to (?:fund|meet|satisfy|finance)|"
                  r"next twelve months and beyond|expected (?:term|volatility|dividend yield|life)|risk-free (?:interest )?rate|"
                  r"unrecognized (?:stock-based |share-based )?compensation|expected to be recognized over a weighted|amortization expense for|"
                  r"estimated (?:future )?amortization|deductible for (?:income )?tax|reclassified (?:into|to) earnings|fair value hierarch|"
                  r"plan assets|pension (?:benefit )?payments expected|expected long-term (?:rate of )?return|we are (?:currently )?evaluating the impact")
TOPICS = [
    ("demand", r"demand|revenue|sales|customers?|orders?|volume|traffic|subscribers?|bookings|market share|comparable (?:store )?sales|same-store"),
    ("margin", r"margins?|pricing|prices|price increases|mix|profitab\w+|gross profit|operating income|earnings per share|EPS"),
    ("costs", r"costs?|expenses?|inflation|tariffs?|freight|commodit\w+|raw materials?|labor costs|wage|input"),
    ("capex", r"capital expenditures?|capex|capital spending|invest(?:ment|ing)? in|capacity|(?:new|open\w*|build\w*) (?:\w+ )?(?:plants?|factor(?:y|ies)|facilit(?:y|ies)|stores?|data cent\w+|fabs?)|build[- ]out"),
    ("returns", r"repurchas\w+|buybacks?|dividends?|return (?:of )?capital to (?:share|stock)holders"),
    ("financing", r"debt|borrow\w*|credit facility|refinanc\w+|notes due|leverage|liquidity|interest expense|rating"),
    ("people", r"headcount|workforce|employees|hiring|restructur\w+|layoffs?|severance|reductions? in force|cost savings|efficienc\w+"),
    ("deals", r"acquisitions?|acquire|merger|divest\w+|dispos\w+|spin-?off|close (?:the|this) transaction|transaction (?:is|to) (?:expected to )?close"),
    ("products", r"launch\w*|product(?:s)? (?:introduction|pipeline|roadmap)|approval|FDA|new products?|roll ?out|platform"),
    ("legal", r"regulat\w+|litigation|lawsuits?|settlement|investigation|compliance|legislation|government"),
    ("tax", r"tax rate|income taxes|tax (?:expense|benefit)|effective tax|ETR(?:-adjusted)?"),
    ("backlog", r"backlog|remaining performance obligations|RPO|pipeline of|contracted|awards?"),
    ("ai", r"\bAI\b|artificial intelligence|generative|machine learning|GPU|accelerat\w+ comput\w+|data cent\w+"),
]
TOPICS = [(k, re.compile(r"(?i)\b(?:" + p + r")\b")) for k, p in TOPICS]
POS = re.compile(r"(?i)\b(?:grow\w*|increas\w+|improv\w+|strong\w*|higher|expan\w+|accelerat\w+|record|robust|benefit\w*|gain\w*|"
                 r"momentum|tailwinds?|recover\w*|upside|raise[sd]?|outperform\w*|solid|healthy|favorable)\b")
NEG = re.compile(r"(?i)\b(?:declin\w+|decreas\w+|lower|weak\w*|pressure[sd]?|headwinds?|soft\w*|slow\w*|challeng\w+|reduc\w+|loss(?:es)?|"
                 r"impair\w+|unfavorable|adverse\w*|delay\w*|uncertain\w*|volatil\w+|deteriorat\w+|downturn|shortfall|cut|tariffs?|disrupt\w+)\b")
HEDGE = re.compile(r"(?i)\b(?:may|might|could|uncertain\w*|subject to|depend\w* on|cannot (?:predict|assure|guarantee)|no assurance|if\b|"
                   r"there can be no|unable to predict|difficult to predict)\b")
WHEN = re.compile(r"(?i)\b(?:(?:the )?(?:first|second|third|fourth) (?:fiscal )?quarter(?: of (?:fiscal )?20\d\d)?|(?:fiscal|calendar) (?:year )?20\d\d|"
                  r"(?:full[- ]year|fiscal year) 20\d\d|(?:first|second) half(?: of (?:fiscal )?20\d\d)?|Q[1-4](?: ?(?:FY)?'?\d{2,4})?|"
                  r"next (?:twelve|12) months|(?:the )?remainder of (?:the |our )?(?:fiscal )?(?:year|20\d\d)|next (?:fiscal )?(?:year|quarter)|"
                  r"(?:by|through|in) (?:the end of )?(?:fiscal )?20\d\d|long[- ]term)\b")
STOP = set("the a an and or of to in on for with by as at from that this these those is are be been being was were it its our we us "
           "will would should could may might can expect expects expected anticipate anticipates plan plans continue continues "
           "company management also which than such into over under about approximately".split())


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", text or "") if s.strip()]


def is_forward(s):
    if not (40 <= len(s) <= 600) or BOILER.search(s) or SKIP.search(s):
        return False
    return bool(FWD.search(s) and WHO.search(s))


def topic_of(s):
    best, n = None, 0
    for k, rx in TOPICS:
        m = len(rx.findall(s))
        if m > n:
            best, n = k, m
    return best or "other"


def tone_of(s):
    p, q = len(POS.findall(s)), len(NEG.findall(s))
    return "positive" if p > q else "negative" if q > p else "neutral"


def words(s):
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP and len(w) > 2}


def numbers(s):
    return re.findall(r"\d+(?:\.\d+)?", s.replace(",", ""))


def similar(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / max(1, len(wa | wb))


def statements(paras, limit=60):
    """The forward-looking sentences of a document's paragraphs (text.paragraphs output or strings), in order."""
    out, seen = [], set()
    for p in paras:
        t = p.get("text", "") if isinstance(p, dict) else str(p)
        if not t or (isinstance(p, dict) and p.get("heading")):
            continue
        for s in sentences(t):
            s = re.sub(r"\s+", " ", s)
            key = s.lower()[:160]
            if key in seen or not is_forward(s):
                continue
            seen.add(key)
            w = WHEN.search(s)
            out.append({"t": s if len(s) <= 420 else s[:417].rsplit(" ", 1)[0] + "…", "topic": topic_of(s), "tone": tone_of(s),
                        "hedge": bool(HEDGE.search(s)), **({"when": w.group(0)} if w else {})})
            if len(out) >= limit:
                return out
    return out


def compare(cur, prev):
    """Mark each statement new / repeated / updated against the earlier document's; return the earlier ones not said again."""
    used = set()
    for s in cur:
        best, bi = 0.0, None
        for i, o in enumerate(prev or []):
            if i in used:
                continue
            v = similar(s["t"], o["t"])
            if v > best:
                best, bi = v, i
        if best >= 0.55:
            used.add(bi)
            s["status"] = "repeated" if numbers(s["t"]) == numbers(prev[bi]["t"]) else "updated"
            if s["status"] == "updated":
                s["was"] = prev[bi]["t"]
        else:
            s["status"] = "new" if prev is not None else "first"
    return [o for i, o in enumerate(prev or []) if i not in used]


YEAR = re.compile(r"(?i)(?:year end(?:ing|ed)? (?:on )?(?:\w+ \d{1,2}, )?|fiscal (?:year )?|full[- ]year |calendar (?:year )?|for |in )(20\d\d)\b")


def _with_year(period, sentence):
    """'FY' or 'Q4' with no year: the year the sentence names ('for the year ending December 31, 2026' → FY2026)."""
    if re.search(r"\d{4}", period or ""):
        return period
    m = YEAR.search(sentence) or re.search(r"\b(20\d\d)\b", sentence)
    if not m:
        return None
    y = m.group(1)
    p = (period or "").strip()
    return f"FY{y}" if p in ("", "FY") else f"{p} {y}" if re.fullmatch(r"Q[1-4]", p) else None


def guided_items(stmts):
    """The guided figures among the statements (guidance.read, sentence by sentence so each keeps its own year), with a
    period and a range."""
    try:
        import guidance as G
    except Exception:
        return []
    keep = ("metric", "name", "basis", "period", "unit", "lo", "hi", "approx", "bound", "said", "scope")
    out, seen = [], set()
    for s in stmts:
        try:
            r = G.read([s["t"]]) or {}
        except Exception:
            continue
        for it in r.get("items") or []:
            per = _with_year(it.get("period"), s["t"])
            if it.get("lo") is None or not per:
                continue
            k = (it.get("metric"), it.get("basis"), it.get("unit"), per)
            if k in seen:
                continue
            seen.add(k)
            out.append({**{kk: it.get(kk) for kk in keep if it.get(kk) not in (None, "")}, "period": per})
    return out


def counts(stmts):
    n = len(stmts)
    c = {"n": n, "positive": sum(s["tone"] == "positive" for s in stmts), "negative": sum(s["tone"] == "negative" for s in stmts),
         "hedged": sum(s["hedge"] for s in stmts), "new": sum(s.get("status") == "new" for s in stmts),
         "updated": sum(s.get("status") == "updated" for s in stmts)}
    c["tone"] = round((c["positive"] - c["negative"]) / n, 3) if n else None
    topics = {}
    for s in stmts:
        topics[s["topic"]] = topics.get(s["topic"], 0) + 1
    c["topics"] = sorted(topics.items(), key=lambda x: -x[1])
    return c


def path(root, cik):
    return Path(root) / "outlook" / f"{int(cik)}.json"


def load(root, cik):
    p = path(root, cik)
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"cik": int(cik), "docs": []}


def keep(root, cik, kind, form, accn, filed, url, end, paras):
    """Add one document's forward-looking statements to <root>/outlook/<cik>.json (newest first). Returns the entry."""
    if not root:
        return None
    doc = load(root, cik)
    if any(d.get("accn") == accn for d in doc["docs"]):
        return None
    stmts = statements(paras)
    if not stmts:
        return None
    prev = next((d for d in sorted(doc["docs"], key=lambda d: d.get("filed") or "", reverse=True)
                 if d.get("kind") == kind and (d.get("filed") or "") <= (filed or "")), None)
    dropped = compare(stmts, prev["statements"] if prev else None)
    entry = {"kind": kind, "form": form, "accn": accn, "filed": filed, "end": end, "url": url, "statements": stmts,
             "dropped": [{"t": o["t"], "topic": o["topic"]} for o in dropped[:12]] if prev else [], "items": guided_items(stmts),
             **({"vs": prev["accn"]} if prev else {})}
    entry["counts"] = counts(stmts)
    entry["counts"]["dropped"] = len(dropped) if prev else 0
    doc["docs"] = sorted(doc["docs"] + [entry], key=lambda d: d.get("filed") or "", reverse=True)[:KEEP]
    p = path(root, cik)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, separators=(",", ":")))
    return entry


def refresh(store, sec, text, time_up, limit=REFRESH_PER_RUN):
    """Catch up: companies with no MD&A statements on file yet — their latest 10-Q / 10-K and the one before it (so the
    first view already shows what changed), largest first, within the run's time budget."""
    root = store.root if hasattr(store, "root") else None
    if not root:
        return 0
    todo = []
    for cik in store.ciks():
        if any(d.get("kind") == "mdna" for d in load(root, cik)["docs"]):
            continue                                 # new 10-Qs and 10-Ks are kept as the scan reads them (build.py)
        c = store.company(cik)
        qs = sorted((q for q in (c.get("quarters") or {}).values() if q.get("form") in ("10-Q", "10-K") and q.get("doc_url")),
                    key=lambda q: q.get("end") or "", reverse=True)
        if not qs:
            continue
        have = {d.get("accn") for d in load(root, cik)["docs"]}
        if qs[0].get("accn") in have:
            continue
        todo.append((-((qs[0].get("raw") or {}).get("revenue") or 0), cik, [q for q in qs[:2] if q.get("accn") not in have][::-1]))
    n = 0
    for _, cik, qs in sorted(todo)[:limit]:
        if time_up():
            break
        for q in qs:
            try:
                keep(root, cik, "mdna", q.get("form"), q.get("accn"), q.get("filed"), q.get("doc_url"), q.get("end"),
                     text.mdna(sec.get(q["doc_url"])))
            except Exception as e:
                print(f"  outlook skipped for {cik} {q.get('accn')}: {e}", file=sys.stderr)
        n += 1
    if todo:
        print(f"forward-looking statements: {n} companies caught up, {max(len(todo) - n, 0)} to go")
    return n


def publish(root, out):
    """<out>/<cik>.json per company, and <out>/index.json: per company the latest MD&A's counts (for the hub)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for p in sorted((Path(root) / "outlook").glob("*.json")):
        try:
            doc = json.loads(p.read_text())
        except Exception:
            continue
        if not doc.get("docs"):
            continue
        (out / p.name).write_text(json.dumps(doc, separators=(",", ":")))
        latest = doc["docs"][0]
        c = latest.get("counts") or {}
        index.append([doc["cik"], latest.get("kind"), latest.get("form"), latest.get("filed"), c.get("n"), c.get("new"), c.get("updated"),
                      c.get("dropped"), c.get("tone"), c.get("hedged"), len(latest.get("items") or [])])
    (out / "index.json").write_text(json.dumps({"fields": ["cik", "kind", "form", "filed", "n", "new", "updated", "dropped", "tone", "hedged", "items"],
                                                "rows": index}, separators=(",", ":")))
    return len(index)


def main():
    ap = argparse.ArgumentParser(description="forward-looking statements")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--store", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    print(f"forward-looking statements published for {publish(a.store, a.out)} companies")


if __name__ == "__main__":
    main()
