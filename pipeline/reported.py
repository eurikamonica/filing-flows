"""Figures a company reports itself, which can define a line differently from our own derivation. Today: free cash
flow. Our chart's free cash flow is operating cash flow − capital expenditures; Meta subtracts principal payments on
finance leases as well, Micron nets proceeds and government incentives against capex. A reader comparing the chart with
the company's earnings release must not find two different "free cash flows".

Three steps, in order:
  check     read the company's own reconciliation (operating cash flow → free cash flow) from its earnings release
            (8-K Exhibit 99.1). Accepted only when its operating cash flow equals SEC's figure for the same quarter
            (which also fixes the column and the units) and its own lines add up to its free cash flow.
  replace   when it does and free cash flow is positive, the chart draws the company's definition: operating cash flow
            splits into each item the company subtracts and its free cash flow ("company-reported").
  disclaim  when it cannot be drawn that way, the chart keeps operating cash flow − capex and says, on the node, in the
            data checks and in the footer, what the company reports.
"""
import re

from . import release

FCF_RE = re.compile(r"^(adjusted |non-gaap )?free cash flows?( ?(\((non-gaap|unaudited|fcf)\)|[—–-] ?non-gaap))?$")
OCF_RE = re.compile(r"^(net )?cash (provided by|from|generated (by|from)|provided by \(used in\)|\(used in\) provided by|"
                    r"used in|provided by \(used for\))( continuing)? operating activities$|^cash flows? from operating activities$"
                    r"|^(net )?cash (provided by|from) operations$|^operating cash flows?$")
SUBTOTAL_RE = re.compile(r"\b(total|subtotal)\b|^net (capital expenditures|capex|purchases|investment)")
SCALES = (1e6, 1e3, 1e9, 1.0)
MAX_PARTS = 6


def close(a, b, unit=1e6, tol=0.005):
    """Equal within tol, allowing for numbers printed rounded to `unit`."""
    return a is not None and b is not None and abs(a - b) <= max(tol * max(abs(a), abs(b)), 0.6 * unit)


def clean_label(s):
    s = re.sub(r"^\s*(less|plus|add|deduct)\s*[:\-–]?\s*", "", s or "", flags=re.I)
    s = re.sub(r"\s*\((\d{1,2}|[a-z]|[ivx]+)\)|\*+|†|‡", "", s).strip(" :,.")
    return s[:1].upper() + s[1:]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", clean_label(s).lower()).strip("-")[:60]


def short(label):
    """A few words for a definition line: 'capex', 'finance lease principal', or the label's first words."""
    k = (label or "").lower()
    if "finance lease" in k or "capital lease" in k:
        return "finance lease principal"
    if "principal" in k:                                             # paying for assets bought earlier, not capex
        return "principal payments"
    if not re.search(r"\b(repayments?|payments on)\b", k) and re.search(r"propert|equipment|capital expenditure|capex", k):
        return "capex"
    return _words(k, 4)


def _words(k, n):
    """The first n words, without a dangling 'of', 'on', 'and'..."""
    w = k.replace(",", "").split()[:n]
    while len(w) > 1 and w[-1] in ("of", "on", "for", "and", "the", "to", "from", "in", "related", "net"):
        w.pop()
    return " ".join(w)


def fcf_name(label):
    """The company's name for the line, without '(non-GAAP)' and the like: 'Free cash flow', 'Adjusted free cash flow'."""
    s = clean_label(label)
    s = re.sub(r"\s*(\((non-gaap|unaudited|fcf)\)|[—–-]\s*non-gaap)$", "", s, flags=re.I)
    s = re.sub(r"^non-gaap\s+", "", s, flags=re.I)
    return s[:1].upper() + s[1:]


def _period(ocf_row, fcf_row, comps, j, s):
    """The reconciliation in column j (units s): {"ocf", "fcf", "parts": [{"key", "label", "v"}]}, signs as the
    company applies them (negative = subtracted), or None when its lines do not add up."""
    if any(len(r["vals"]) <= j for r in comps + [fcf_row]):
        return None
    ocf, fcf = ocf_row["vals"][j] * s, fcf_row["vals"][j] * s
    keep = []
    for r in comps:
        v = r["vals"][j] * s
        if keep and SUBTOTAL_RE.search(r["key"]) and close(v, sum(x for _, x in keep), s):
            continue                                    # a subtotal of the lines above it
        keep.append((r, v))
    if close(ocf + sum(v for _, v in keep), fcf, s):
        parts = keep
    elif close(ocf - sum(abs(v) for _, v in keep), fcf, s):          # printed as positives under "Less:"
        parts = [(r, -abs(v)) for r, v in keep]
    else:
        return None
    return {"ocf": ocf, "fcf": fcf,
            "parts": [{"key": slug(r["label"]), "label": clean_label(r["label"]), "v": v} for r, v in parts if v]}


def parse_fcf(tables, ocf_cur, ocf_py=None):
    """The company's free cash flow from its release tables: {"name", "cur": period, "py": period or None}, or None.
    ocf_cur / ocf_py: SEC's operating cash flow for this quarter and the year-ago quarter (the anchors)."""
    if not ocf_cur:
        return None
    for t in tables or []:
        rows = [r for r in t["rows"] if r.get("label") and r.get("vals") and not r.get("pct")]
        fi = next((i for i, r in enumerate(rows) if FCF_RE.match(r["key"])), None)
        if fi is None:
            continue
        oi = next((i for i in range(fi - 1, -1, -1) if OCF_RE.match(rows[i]["key"])), None)
        if oi is None or not 1 <= fi - oi - 1 <= MAX_PARTS:
            continue
        ocf_row, fcf_row, comps = rows[oi], rows[fi], rows[oi + 1:fi]
        found = {}
        for which, ref in (("cur", ocf_cur), ("py", ocf_py)):
            if not ref:
                continue
            for j, v in enumerate(ocf_row["vals"]):
                if which == "py" and found.get("cur", {}).get("col") == j:
                    continue
                s = next((s for s in SCALES if close(v * s, ref, s, 0.002)), None)
                if s:
                    got = _period(ocf_row, fcf_row, comps, j, s)
                    if got:
                        found[which] = dict(got, col=j)
                        break
        if found.get("cur"):
            return {"name": fcf_name(fcf_row["label"]), "cur": found["cur"], "py": found.get("py")}
    return None


def netted(period):
    """[{"key", "label", "amount" > 0 subtracted, "extra"}] largest first: amounts the company adds back (proceeds from
    asset sales, incentives) are netted against its largest deduction (so no band runs backwards). None if impossible."""
    if not period:
        return None
    ded = sorted([p for p in period["parts"] if p["v"] < 0], key=lambda p: p["v"])
    add = [p for p in period["parts"] if p["v"] > 0]
    if not ded:
        return None
    out = [{"key": p["key"], "label": p["label"], "amount": -p["v"], "extra": []} for p in ded]
    if add:
        a = sum(p["v"] for p in add)
        out[0]["amount"] -= a
        out[0]["label"] += ", net"
        out[0]["netted"] = a
        out[0]["netted_words"] = " and ".join(p["label"][:1].lower() + p["label"][1:] for p in add)
        if out[0]["amount"] <= 0:
            return None
    return out


def for_chart(co, ocf, ocf_py=None):
    """(use, use_py): the company's definition to draw for this quarter (and the year-ago quarter, same items), or
    (None, None) when it cannot be drawn: no figure, a negative or zero free cash flow, or a different operating cash
    flow (the 10-Q restated the release)."""
    cur = (co or {}).get("cur")
    if not cur or cur["fcf"] <= 0 or not ocf or not close(cur["ocf"], ocf, 1e6, 0.01):
        return None, None
    parts = netted(cur)
    if not parts or not close(ocf - sum(p["amount"] for p in parts), cur["fcf"], 1e6, 0.01):
        return None, None
    use = {"name": fcf_name(co.get("name") or "Free cash flow"), "fcf": ocf - sum(p["amount"] for p in parts), "parts": parts,
           "reported": cur["fcf"]}
    use_py = None
    py_parts = netted(co.get("py"))
    if py_parts and ocf_py and close(co["py"]["ocf"], ocf_py, 1e6, 0.01) \
            and [p["key"] for p in py_parts] == [p["key"] for p in parts] and co["py"]["fcf"] > 0:
        use_py = {"name": use["name"], "fcf": ocf_py - sum(p["amount"] for p in py_parts), "parts": py_parts}
    return use, use_py


def definition(parts):
    """'OCF − capex − finance lease principal' (an item named alike twice is spelt out, so no 'capex − capex')."""
    words = [short(p["label"]) for p in parts]
    words = [w if words.count(w) == 1 else _words(p["label"].lower(), 5) for w, p in zip(words, parts)]
    return "OCF − " + " − ".join(words)


def our_fcf(Nc):
    return Nc["ocf"] - Nc["capex"] if Nc.get("ocf") is not None and Nc.get("capex") else None


def find_release(rows, end, filed):
    """The earnings release (8-K, Item 2.02) of the quarter ending `end`: filed after the quarter ended and no later
    than the 10-Q/10-K (`filed`), the latest such. rows: submissions' recent filings."""
    hits = [r for r in rows if r.get("form", "").startswith("8-K") and "2.02" in (r.get("items") or "")
            and end < (r.get("filingDate") or "") <= (filed or "9999")]
    return max(hits, key=lambda r: r["filingDate"]) if hits else None


def from_release_doc(html, ocf_cur, ocf_py=None):
    return parse_fcf(release.read_tables(html), ocf_cur, ocf_py)


# ------------------------------------------------------------------ what the search found
# q["co_status"]: why a quarter has no company figure, so a chart drawn by the formula can say so (the "noted" choice)
#   found         a reconciliation that checks out (q["co_fcf"])
#   no_release    no earnings release (8-K, Item 2.02) between the quarter's end and its 10-Q/10-K
#   not_reported  the release has no free cash flow line
#   unmatched     it has one, but its operating cash flow or its own lines did not match SEC's figures
#   error         the release could not be read (tried again on later runs)
def status_of(tables, co):
    """The search result for one earnings release's tables and what parse_fcf made of them."""
    if co:
        return "found"
    for t in tables or []:
        if any(FCF_RE.match(r.get("key") or "") for r in t.get("rows") or []):
            return "unmatched"
    return "not_reported"


WHY = {   # status -> (a few words for the chart's node, the sentence for the data checks)
    "no_release": ("no earnings release found", "No earnings release (8-K, Item 2.02) was found for this quarter"),
    "not_reported": ("not in its earnings release", "The company’s earnings release does not report free cash flow"),
    "unmatched": ("did not match SEC data", "The company’s earnings release reports free cash flow, but its figures could not "
                                            "be matched to SEC’s operating cash flow for the quarter"),
    "unchecked": ("not checked", "This quarter was stored before company-reported free cash flow was looked up"),
    "not_found": ("not found", "No company-reported free cash flow was found for this quarter"),
    "annual": ("read for quarters only", "Company-reported free cash flow is read for quarters only"),
    "error": ("release could not be read", "The company’s earnings release could not be read"),
}


def formula_note(status, node_id, ours, money):
    """{"node", "line", "check", "footer"}: what a chart drawn by the formula says about the missing company figure."""
    short, long = WHY.get(status) or WHY["not_found"]
    calc = f"operating cash flow − capital expenditures ({money(ours)})" if ours is not None else \
        "operating cash flow − capital expenditures"
    return {"node": node_id, "line": f"company figure: {short}",
            "check": {"level": "note", "code": "fcf_formula", "text": f"{long}, so free cash flow is calculated: {calc}."},
            "footer": f"No company-reported free cash flow ({short}): free cash flow here is calculated by the formula."}


# ------------------------------------------------------------------ the reader's choice
BASES = ("company", "noted", "ocf")
# subscriptions.fcf_basis: the company's own figure where it is drawn, else the formula ("company", the default); the same,
# and a chart drawn by the formula says why ("noted"); or operating cash flow − capex for every company ("ocf")


def fcf_view(q, basis):
    """A site quarter or year (data/c/<cik>.json) as a reader who chose `basis` sees it:
    "ocf"    swaps in the version on operating cash flow − capex ("fcf_alt", written where the company's figure is drawn)
    "noted"  adds the note on a chart drawn by the formula ("fcf_note": a line on the node, a data check, a footer line)
    otherwise, or when the quarter has nothing to change, q as it is."""
    q = q or {}
    if basis == "ocf" and q.get("fcf_alt"):
        out = dict(q, **q["fcf_alt"])
    elif basis == "noted" and q.get("fcf_note"):
        n = q["fcf_note"]
        out = dict(q, nodes=[dict(x, lines=(x.get("lines") or []) + [["mut", n["line"]]]) if x.get("id") == n["node"] else x
                             for x in q.get("nodes") or []],
                   checks=(q.get("checks") or []) + [n["check"]], footer=(q.get("footer") or []) + [n["footer"]])
    else:
        return q
    out.pop("fcf_alt", None)
    out.pop("fcf_note", None)
    out["fcf_basis"] = basis
    return out
