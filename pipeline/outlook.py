"""Forward-looking statements: what a company says it expects, in its own words, filing after filing — no language model.

Read from the MD&A of each 10-Q / 10-K (Item 2 / Item 7) and from each earnings release (8-K Exhibit 99), the sentences
in which the company looks ahead ("we expect", "we anticipate", "we plan to", "remains on track", "for fiscal 2027 we
target …"), leaving out the boilerplate (the safe-harbor paragraph, accounting standards to be adopted, "sufficient to
fund our operations for the next twelve months", option-pricing assumptions …). Each statement gets:

  topic   demand and revenue, margins and pricing, costs, supply and capacity, the economy and markets (rates, currency,
          consumers, geopolitics), capital spending, capital returns, financing, people and restructuring, deals,
          products, regulation and legal, tax, backlog and orders, AI
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
DEPTH = 4                      # MD&As caught up per company (the latest and three before it: a year of filings to compare)
REANNOTATE_PER_RUN = 25         # companies whose MD&As on file are read again per scan for their risks and estimates

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
    ("supply", r"supply(?: chain)?|suppliers?|shortages?|constrain\w*|capacity (?:constraints?|limitations?)|lead times?|availability|"
               r"sourc\w+|logistics|manufacturing (?:capacity|output|ramp)|ramp(?:ing)?|yield|production (?:levels?|rates?|ramp)|inventor\w+"),
    ("macro", r"econom\w+|macroeconomic|recession|interest rates?|foreign (?:currency|exchange)|currency|exchange rates?|"
              r"consumer (?:spending|demand|confidence)|geopolitic\w+|war|conflict|China|export (?:controls?|restrictions?)|trade (?:policy|tensions?)"),
    ("capex", r"capital expenditures?|capex|capital spending|invest(?:ment|ing)? in|capacity|(?:new|open\w*|build\w*) (?:\w+ )?(?:plants?|factor(?:y|ies)|facilit(?:y|ies)|stores?|data cent\w+|fabs?)|build[- ]out"),
    ("returns", r"repurchas\w+|buybacks?|dividends?|return (?:of )?capital to (?:share|stock)holders"),
    ("financing", r"debt|borrow\w*|credit facility|refinanc\w+|notes due|leverage|liquidity|interest expense|rating"),
    ("people", r"headcount|workforce|employees|hiring|restructur\w+|layoffs?|severance|reductions? in force|cost savings|efficienc\w+"),
    ("deals", r"acquisitions?|acquire|merger|divest\w+|dispos\w+|spin-?off|close (?:the|this) transaction|transaction (?:is|to) (?:expected to )?close"),
    ("products", r"launch\w*|product(?:s)? (?:introduction|pipeline|roadmap)|approval|FDA|new products?|roll ?out|platform"),
    ("legal", r"regulat\w+|litigation|lawsuits?|settlement|investigation|compliance|legislation|government|licens\w+"),
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


# ---------- the risks a filing lists, and the numbers that rest on estimates ----------
# The safe-harbor paragraph ("Actual results and outcomes could differ materially for a variety of reasons, including,
# among others, fluctuations in foreign exchange rates and energy prices, … tariff and trade policies, resource and supply
# volatility, including for memory chips, …") is boilerplate on its own, but its list changes: a risk added since the
# filing before (or one no longer named) says what management has started to worry about. Each item is split out and
# pinned to the lines it would move. The MD&A's "Critical Accounting Estimates" names the reported figures that rest on
# judgment (inventories, income taxes, useful lives …), with a sensitivity when the company gives one ("a 10% change in
# … would have changed … by $X million").
RISK_V = 2                     # bump when risks() / estimates() change: the MD&As on file are read again (refresh)
                               # 2: references ("those discussed in Part I, Item 1A …") are not risks; a page header ("PART II Item 7")
                               #    does not end the critical accounting estimates
FLS_PARA = re.compile(r"(?i)differ materially|cause (?:our )?actual results|actual (?:results|outcomes) (?:and outcomes )?(?:may|could|might)|"
                      r"factors that could cause|risks and uncertainties|materially (?:affected|different)|subject to (?:substantial |significant )?uncertaint")
LIST_INTRO = re.compile(r"(?i)(?:for a variety of reasons,? including,?(?:\s*(?:but not limited to|among others),?)?|"
                        r"(?:factors|risks|uncertainties|reasons)[^.;]{0,90}?\b(?:include|includes|including|are)\b,?(?:\s*(?:but (?:are )?not limited to|without limitation|among others),?)?|"
                        r"(?:factors|risks|uncertainties)[^.;]{0,40}?,?\s*such as|"
                        r"including,? (?:but not limited to|without limitation|among others),?|as a result of)\s*:?\s*")
RISK_LINES = [
    (r"foreign (?:exchange|currency)|currenc", ["revenue"]),
    (r"energy|fuel|power (?:prices|costs)|electricity", ["cor", "costs", "opex"]),
    (r"memory|chips?\b|semiconductor|component|resource and supply|supply|supplier|shortage|raw material|commodit", ["cor", "capex"]),
    (r"tariff|trade (?:polic|restriction|tension)|export control", ["cor", "costs"]),
    (r"inflation", ["cor", "costs", "opex"]),
    (r"interest rate", ["interest"]),
    (r"\btax", ["tax"]),
    (r"inventor", ["k~Inventor", "cor"]),
    (r"labor|workforce|wage|employee|talent|personnel", ["opex", "costs"]),
    (r"data cent|capacity|infrastructure|fulfillment|sortation|delivery|facilit|invest\w* in new|timing of (?:those )?investments", ["capex"]),
    (r"acquisition|strategic transaction|merger|divest", ["#cat:acq"]),
    (r"debt|credit|financing|liquidity|capital markets", ["#cat:debt"]),
    (r"litigation|claims|government investigations|legal|regulat|proceedings|compliance|antitrust", ["opex", "costs"]),
    (r"cyber|security (?:breach|incident)|data (?:privacy|protection)|system (?:failure|interruption)|outage|fraud", ["opex", "costs"]),
    (r"compet|pricing|price", ["revenue", "gp"]),
    (r"demand|spending|econom|recession|consumer|customer|market (?:conditions|demand|share)|markets|growth|internet|online|cloud|world events|geopolit|mix|payment|commercial agreement|technolog", ["revenue"]),
]
RISK_LINES = [(re.compile(r"(?i)" + p), ls) for p, ls in RISK_LINES]
EST_LINES = [
    (r"inventor", ["k~Inventor", "cor"]),
    (r"income tax|\btax", ["tax"]),
    (r"useful li|depreciat|property(?:,)? (?:plant )?and equipment|servers?\b|long-lived", ["da", "capex"]),
    (r"goodwill|intangible|impairment", ["opex", "costs"]),
    (r"revenue|returns? allowance|rebate|performance obligation|variable consideration|customer program", ["revenue"]),
    (r"lease", ["opex", "costs"]),
    (r"contingenc|litigation|legal|loss reserves", ["opex", "costs"]),
    (r"stock-based|share-based|equity award", ["sbc"]),
    (r"credit loss|allowance for (?:doubtful|credit)|receivable", ["revenue"]),
    (r"pension|postretirement|retirement benefit", ["opex", "costs"]),
    (r"warrant", ["cor"]),
    (r"business combination|acquisition|purchase price allocation", ["#cat:acq"]),
    (r"insurance|claims? reserves|self-insur", ["costs", "opex"]),
    (r"non-marketable|equity securities|investments?|fair value", ["nonop", "nonop_in"]),
]
EST_LINES = [(re.compile(r"(?i)" + p), ls) for p, ls in EST_LINES]
CAE_HEAD = re.compile(r"(?i)^critical accounting (?:estimates|policies|judgments)(?: and (?:estimates|judgments|policies))?\b")
CAE_END = re.compile(r"(?i)^(?:recent(?:ly)? (?:issued |adopted )?accounting|new accounting|accounting (?:standards|pronouncements)|"
                     r"liquidity|results of operations|overview|non-gaap|off-balance|contractual obligations|quantitative and qualitative|"
                     r"item\s*\d+[a-z]?\.?\s+\w|financial condition|capital resources|segment (?:results|information)|executive summary|outlook|guidance|"
                     r"(?:fiscal )?(?:20\d\d|first|second|third|fourth) (?:quarter|year)|three months|six months|nine months)")
CAE_REF = re.compile(r"(?i)no (?:material |significant )?changes? (?:to|in) (?:our )?critical accounting|"
                     r"(?:described|discussed|included|disclosed) in (?:item 7|part ii|our (?:20\d\d |most recent )?annual report|our form 10-k)")
SENS = re.compile(r"(?i)\b(?:a|an|each)\s+(?:hypothetical\s+|one\s+)?(\d+(?:\.\d+)?)\s*(%|percent(?:age points?)?|basis points?|bps)\s+"
                  r"(?:(?:increase|decrease|change|reduction|decline|rise|movement)\s+)?(?:in|of|to)\s+(.{3,90}?)\s+would\s+(?:have\s+)?"
                  r"(?:resulted in|result in|increased?|decreased?|reduced?|changed?|impacted?|affected?|had)\b[^.$]{0,90}?\$\s?([\d.,]+)\s*(million|billion|thousand)?")
EFFECT = re.compile(r"(?i)\b(?:impact|effect|benefit|charge|expense|provision|write-?down|adjustment)s?\b[^.]{0,80}?(?:\$\s?[\d.,]+\s*(?:million|billion)|\d+(?:\.\d+)?\s?%)")


def _text(p):
    return (p.get("text", "") if isinstance(p, dict) else str(p)).strip()


def _lines_of(t, table):
    """The lines a phrase would move: every rule it matches ("foreign exchange rates and energy prices": revenue and the
    costs), the bottom line when none does."""
    out = []
    for rx, ls in table:
        if rx.search(t):
            out += [x for x in ls if x not in out]
    return out[:5] or ["net"]


def _split_list(s):
    """'fluctuations in foreign exchange rates and energy prices, changes in global economic conditions, … including for
    memory chips, and customer demand and spending, …' → its items ('including …' stays with the item before it)."""
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    parts = [x for x in re.split(r";\s*", s) if x.strip()]
    if len(parts) < 3:
        parts = re.split(r",\s+(?![^()]*\))", s)
    # a list inside an item ("the outcomes of claims, litigation, government investigations, and other proceedings";
    # "fulfillment, sortation, delivery, and data center optimization"): short parts ending in an "and …" part of at most
    # four words are one item with the part before them
    parts = [x.strip() for x in parts if x.strip()]
    nw = lambda x: len(re.sub(r"(?i)^(?:and|or)\s+", "", x).split())
    merged, k = [], 0
    while k < len(parts):
        x = parts[k]
        if re.match(r"(?i)^(?:and|or)\s", x) and nw(x) <= 4 and merged:
            j = len(merged)
            while j > 0 and len(merged) - j < 5 and nw(merged[j - 1][0]) <= 3 and not merged[j - 1][1] and not re.match(r"(?i)^(?:and|or)\s", merged[j - 1][0]):
                j -= 1
            if j < len(merged):                       # at least one short part before it
                if j > 0 and not merged[j - 1][1] and not re.match(r"(?i)^(?:and|or)\s", merged[j - 1][0]) and nw(merged[j - 1][0]) > 3:
                    j -= 1                            # the longer part that heads the list ("the outcomes of claims")
                head = ", ".join(m[0] for m in merged[j:]) + ", " + x
                merged = merged[:j] + [(head, True)]
                k += 1
                continue
        merged.append((x, False))
        k += 1
    out = []
    for x, _ in merged:
        x = re.sub(r"(?i)^(?:and|or|as well as)\s+", "", x.strip()).strip(" ,")
        if not x:
            continue
        if out and re.match(r"(?i)^(?:including|particularly|especially|such as|in particular|notably)\b", x):
            out[-1] = f"{out[-1]}, {x}"
        else:
            out.append(x)
    return [x for x in out if 4 <= len(x) <= 160 and not re.search(r"(?i)\b(?:are described|see item|risk factors”?|in greater detail|"
                                                                 r"factors (?:detailed|discussed|described|listed|set forth)|in addition to (?:the|those)|"
                                                                 r"part i{1,2}\b|item 1a|form 10-[kq]|annual report|quarterly report|required by law|"
                                                                 r"this (?:report|filing|document)|herein|those (?:discussed|described|set forth|identified))", x)]


def risks(paras, limit=60):
    """The items of the safe-harbor risk list: [{t, lines}] in the filing's order."""
    out, seen = [], set()
    ps = [_text(p) for p in paras]
    last = -1
    for i, t in enumerate(ps):
        if not t or not FLS_PARA.search(t):
            continue
        # after the list (one paragraph or a few next to each other), only a further list of its own ("Additional factors
        # include …", the end of an earnings release)
        if out and i > last + 3 and not re.search(r"(?i)\b(?:other|additional|important|further) (?:risk )?factors\b|factors that (?:could|may|might)|variety of reasons", t):
            continue
        n0 = len(out)
        for s in sentences(t):
            m = LIST_INTRO.search(s) if FLS_PARA.search(s) or re.search(r"(?i)\bfactors\b", s) else None
            if not m:
                continue
            body = s[m.end():]
            items = _split_list(body) if len(body) > 30 else []
            if len(items) < 3:
                items = []                            # a pointer to the risk factors, not a list of its own
            # "… include the following:" and the items as bullets
            if not items and s.rstrip().endswith(":"):
                for q in ps[i + 1:i + 40]:
                    if not q or len(q) > 400:
                        break
                    items.append(re.sub(r"^[•·◦▪\-–—]\s*", "", q).rstrip(";,. "))
            for x in items:
                k = " ".join(sorted(words(x)))
                if k and k not in seen:
                    seen.add(k)
                    out.append({"t": x, "lines": _lines_of(x, RISK_LINES)})
            if len(out) >= limit:
                return out[:limit]
        if len(out) > n0:
            last = i
    return out


def estimates(paras):
    """The MD&A's critical accounting estimates: [{name, t, lines, sens: [{pct, unit, of, usd}], effect}], or
    [{'ref': True}] when the section points to the annual report without listing them."""
    rows = [(p.get("heading", False) if isinstance(p, dict) else len(_text(p)) <= 90 and not _text(p).endswith("."), _text(p)) for p in paras]
    starts = [i for i, (h, t) in enumerate(rows) if CAE_HEAD.match(t) and len(t) <= 120]
    if not starts:
        return []
    body = []
    for h, t in rows[starts[-1] + 1:]:
        if re.match(r"(?i)^table of contents$|^\d+$|^(?:part\s+i{1,3}\s*)?(?:item\s*\d+[a-z]?\.?)?$|^part\s+i{1,3}\b.{0,12}$", t):
            continue                                  # a page's header or number ("PART II Item 7")
        if h and CAE_END.match(t):
            break
        body.append((h, t))
        if len(body) > 80:
            break
    out, cur, parent = [], None, None
    for h, t in body:
        if h and len(t) <= 90:
            if cur and not cur["_body"]:
                parent = cur["name"]                  # a heading with only sub-headings under it ("Revenue Recognition")
                out.pop()
            cur = {"name": f"{parent} — {t}" if parent and cur is not None and not cur["_body"] else t, "_body": []}
            out.append(cur)
            continue
        if cur is None:
            cur = {"name": None, "_body": []}
            out.append(cur)
        cur["_body"].append(t)
    res = []
    for e in out:
        txt = " ".join(e["_body"])
        if not e["name"]:
            if CAE_REF.search(txt):
                res.append({"ref": True, "t": sentences(txt)[0][:300] if txt else ""})
            continue
        if not txt:
            continue
        sens = []
        for m in SENS.finditer(txt):
            mult = {"million": 1e6, "billion": 1e9, "thousand": 1e3}.get((m.group(5) or "million").lower(), 1e6)
            try:
                usd = float(m.group(4).replace(",", "")) * mult
            except ValueError:
                continue
            sens.append({"pct": float(m.group(1)), "unit": "bps" if re.match(r"(?i)b", m.group(2)) else "pct", "of": m.group(3).strip()[:90],
                         "usd": usd, "t": next((s for s in sentences(txt) if m.group(0)[:40] in s), m.group(0))[:300]})
        eff = next((s for s in sentences(txt) if EFFECT.search(s) and not SENS.search(s)), None)
        # the sentence that says what is estimated ("… based on certain estimates and judgments …"), else the first
        ss = sentences(txt)
        first = next((x for x in ss if re.search(r"(?i)estimat|judg(?:e)?ment|assum|uncertain|forecast|significant", x) and x != eff), ss[0] if ss else "")
        res.append({"name": e["name"][:90], "t": first[:300] + ("…" if len(first) > 300 else ""), "lines": _lines_of(e["name"] + " " + first, EST_LINES),
                    **({"sens": sens[:3]} if sens else {}), **({"effect": eff[:300]} if eff else {})})
    if not res and CAE_REF.search(" ".join(t for _, t in body)):
        res.append({"ref": True, "t": sentences(" ".join(t for _, t in body))[0][:300]})
    return res[:16]


def rerisk(doc):
    """Each document's risks against the document of the same kind before it: new / repeated, and the ones no longer
    listed (kept as risks_dropped)."""
    by = {}
    for d in doc.get("docs") or []:
        if "risks" in d:
            by.setdefault(d.get("kind"), []).append(d)
    for ds in by.values():
        ds.sort(key=lambda d: (d.get("filed") or "", d.get("accn") or ""))
        prev = None
        for d in ds:
            used = set()
            for r in d["risks"]:
                best, bi = 0.0, None
                for j, o in enumerate(prev["risks"] if prev else []):
                    if j in used:
                        continue
                    v = similar(r["t"], o["t"])
                    if v > best:
                        best, bi = v, j
                if prev is not None and prev["risks"] and best >= 0.6:
                    used.add(bi)
                    r["status"] = "repeated"
                else:
                    r["status"] = "new" if prev is not None and prev["risks"] else "first"
            d["risks_dropped"] = ([{"t": o["t"], "lines": o.get("lines")} for j, o in enumerate(prev["risks"]) if j not in used][:12]
                                  if prev is not None and prev["risks"] else [])
            prev = d
    return doc


def annotate(entry, paras):
    """The risk list and the critical accounting estimates of one document, into its entry."""
    entry["risks"] = risks(paras)
    if entry.get("kind") == "mdna":
        entry["estimates"] = estimates(paras)
    entry["rv"] = RISK_V
    return entry


def path(root, cik):
    return Path(root) / "outlook" / f"{int(cik)}.json"


def load(root, cik):
    p = path(root, cik)
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"cik": int(cik), "docs": []}


def restatus(doc):
    """Each document against the one before it of the same kind, oldest first — run again whenever a document arrives out
    of order (an older MD&A caught up after a newer one), so "new / updated / no longer said" always reads one step back."""
    by = {}
    for d in doc.get("docs") or []:
        by.setdefault(d.get("kind"), []).append(d)
    for ds in by.values():
        ds.sort(key=lambda d: (d.get("filed") or "", d.get("accn") or ""))
        prev = None
        for d in ds:
            for st in d.get("statements") or []:
                st.pop("status", None)
                st.pop("was", None)
            dropped = compare(d.get("statements") or [], prev["statements"] if prev else None)
            d["dropped"] = [{"t": o["t"], "topic": o["topic"]} for o in dropped[:12]] if prev else []
            if prev:
                d["vs"] = prev.get("accn")
            else:
                d.pop("vs", None)
            d["counts"] = counts(d.get("statements") or [])
            d["counts"]["dropped"] = len(dropped) if prev else 0
            prev = d
    return doc


def keep(root, cik, kind, form, accn, filed, url, end, paras):
    """Add one document's forward-looking statements to <root>/outlook/<cik>.json (newest first). Returns the entry."""
    if not root:
        return None
    doc = load(root, cik)
    if any(d.get("accn") == accn for d in doc["docs"]):
        return None
    paras = list(paras or [])
    stmts = statements(paras)
    extra = annotate({"kind": kind}, paras)
    if not stmts and not extra["risks"] and not extra.get("estimates"):
        return None
    prev = next((d for d in sorted(doc["docs"], key=lambda d: d.get("filed") or "", reverse=True)
                 if d.get("kind") == kind and (d.get("filed") or "") <= (filed or "")), None)
    dropped = compare(stmts, prev["statements"] if prev else None)
    entry = {"kind": kind, "form": form, "accn": accn, "filed": filed, "end": end, "url": url, "statements": stmts,
             "dropped": [{"t": o["t"], "topic": o["topic"]} for o in dropped[:12]] if prev else [], "items": guided_items(stmts),
             **({"vs": prev["accn"]} if prev else {})}
    entry["counts"] = counts(stmts)
    entry["counts"]["dropped"] = len(dropped) if prev else 0
    entry.update({k: v for k, v in extra.items() if k != "kind"})
    doc["docs"] = sorted(doc["docs"] + [entry], key=lambda d: d.get("filed") or "", reverse=True)[:KEEP]
    if any((d.get("filed") or "") > (filed or "") and d.get("kind") == kind for d in doc["docs"]):
        restatus(doc)                                # an older document arrived after newer ones: compare them again
    rerisk(doc)
    p = path(root, cik)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, separators=(",", ":")))
    return entry


def refresh(store, sec, text, time_up, limit=REFRESH_PER_RUN):
    """Catch up, largest companies first, within the run's time budget: those with no MD&A statements on file get their
    latest 10-Q / 10-K and the one before it (so the first view already shows what changed); then those with fewer than
    DEPTH get the next older one each run, so every company has a year of filings to follow its outlook through."""
    root = store.root if hasattr(store, "root") else None
    if not root:
        return 0
    todo = []
    for cik in store.ciks():
        docs = load(root, cik)["docs"]
        have = {d.get("accn") for d in docs if d.get("kind") == "mdna"}
        if len(have) >= DEPTH:
            continue                                 # new 10-Qs and 10-Ks are kept as the scan reads them (build.py)
        c = store.company(cik)
        qs = sorted((q for q in (c.get("quarters") or {}).values() if q.get("form") in ("10-Q", "10-K") and q.get("doc_url")),
                    key=lambda q: q.get("end") or "", reverse=True)[:DEPTH]
        if not qs:
            continue
        missing = [q for q in qs if q.get("accn") not in have and q.get("accn") not in {d.get("accn") for d in docs}]
        if not missing:
            continue
        first = not have
        size = -((qs[0].get("raw") or {}).get("revenue") or 0)
        todo.append((0 if first else 1, size, cik, (missing[:2] if first else missing[:1])[::-1]))
    n = 0
    for _, _, cik, qs in sorted(todo)[:limit]:
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
    if not time_up():
        reannotate(store, sec, text, time_up)
    return n


def reannotate(store, sec, text, time_up, limit=REANNOTATE_PER_RUN):
    """The MD&As on file read again for their risk list and critical accounting estimates (RISK_V), the two latest of
    each company (so the first view already shows the risks added or dropped), largest companies first."""
    root = store.root if hasattr(store, "root") else None
    if not root:
        return 0
    todo = []
    for cik in store.ciks():
        doc = load(root, cik)
        md = sorted((d for d in doc["docs"] if d.get("kind") == "mdna" and d.get("url")), key=lambda d: d.get("filed") or "", reverse=True)[:2]
        need = [d for d in md if d.get("rv") != RISK_V]
        if not need:
            continue
        c = store.company(cik)
        qs = sorted((q for q in (c.get("quarters") or {}).values() if q.get("form") in ("10-Q", "10-K")), key=lambda q: q.get("end") or "", reverse=True)
        size = -(((qs[0] if qs else {}).get("raw") or {}).get("revenue") or 0)
        todo.append((size, cik, [d.get("accn") for d in need]))
    n = 0
    for _, cik, accns in sorted(todo)[:limit]:
        if time_up():
            break
        doc = load(root, cik)
        for d in doc["docs"]:
            if d.get("accn") not in accns:
                continue
            try:
                annotate(d, text.mdna(sec.get(d["url"])))
            except Exception as e:
                print(f"  risks and estimates skipped for {cik} {d.get('accn')}: {e}", file=sys.stderr)
                d["rv_fail"] = d.get("rv_fail", 0) + 1
                if d["rv_fail"] >= 3:
                    d["rv"] = RISK_V                 # not tried again until RISK_V changes
        rerisk(doc)
        p = path(root, cik)
        p.write_text(json.dumps(doc, separators=(",", ":")))
        n += 1
    if todo:
        print(f"risks and critical accounting estimates: {n} companies read, {max(len(todo) - n, 0)} to go")
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
