"""The site's standard earnings Sankey (pipeline/sankey.py) for every period of a registration statement, with the
rule-based analysis (pipeline/analysis.py), the period each one is compared with (the same length of time a year
earlier: H1 2026 against H1 2025, FY 2025 against FY 2024) and where every figure was read.

The reviewed Anthropic tables (pipeline/ipo.py anthropic) keep the filing's own lines: its cost lines by their own names
(it reports no cost of revenue or gross profit), its non-operating lines one by one (the fair-value change of its
convertible notes, derivatives and SAFEs is most of the net loss) and the same non-cash items in the cash bridge, so
nothing large hides in "Interest & other" or "Working capital & other". Periods read from inline XBRL tags use the
standard lines. A period whose figures do not add up gets no chart, and says why.
"""
import datetime as dt

from . import analysis, sankey
from .model import normalize
from .sankey import Fmt, NOTE_KEYS

VERSION = 1

# the reviewed adapter's keys (pipeline/ipo.py OPERATING / INCOME / CASH) -> the chart's lines, in the statement's order
COST = [("compute", "Compute &amp; infrastructure"), ("personnel", "Personnel"),
        ("selling", "Sales, marketing &amp; partnerships"), ("other_operating", "Other operating &amp; admin"),
        ("settlement", "Bartz settlement")]
NONOP = [("interest_income", "Interest income", None),
         ("fair_value", "Fair value of notes &amp; SAFEs", "non-cash: convertible notes, derivatives, SAFEs"),
         ("other_income", "Other income (expense), net", None)]
BRIDGE = [("fair_value_addback", "Fair value of notes &amp; SAFEs", "non-cash, added back"),
          ("other_instruments", "Other financial instruments", "non-cash fair value, added back"),
          ("donation", "Donation matching liability", "non-cash, added back")]
# where a node's figure is in the statements (the period's evidence keys)
EVIDENCE = {"revenue": "revenue", "opcosts": "opex", "tax": "tax", "netloss": "ni", "loss_abs": "ni", "net": "ni",
            "netinc": "ni", "pretax": "pretax", "oi": "oi", "ocf": "ocf", "burn": "ocf", "da": "da", "sbc": "sbc",
            "capex": "capex_signed"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _d(s):
    return dt.date.fromisoformat(s)


def months(p):
    return round(((_d(p["end"]) - _d(p["start"])).days + 1) / 30.44)


def label(p):
    """'FY 2025', 'H1 2026', 'Q2 2026', '9M 2026', or '6M to Mar 2026' for periods that do not end with a calendar
    quarter of the same length; a reviewed label is kept."""
    if p.get("label") and "→" not in p["label"]:
        return p["label"]
    m, end = months(p), _d(p["end"])
    cal = end.month == 12 if m == 12 else end.month == 6 if m == 6 else end.month == 9 if m == 9 else end.month % 3 == 0
    if m == 12:
        return f"FY {end.year}" if cal else f"FY to {MONTHS[end.month - 1]} {end.year}"
    if m == 6 and cal:
        return f"H1 {end.year}"
    if m == 9 and cal:
        return f"9M {end.year}"
    if m == 3 and cal:
        return f"Q{end.month // 3} {end.year}"
    return f"{m}M to {MONTHS[end.month - 1]} {end.year}"


def prior_of(p, periods):
    """The same length of time ending about a year before (within 10 days), or None."""
    want = _d(p["end"]).replace(year=_d(p["end"]).year - 1) if not (_d(p["end"]).month == 2 and _d(p["end"]).day == 29) \
        else _d(p["end"]) - dt.timedelta(days=366)
    best = None
    for q in periods:
        if q is p or months(q) != months(p):
            continue
        gap = abs((_d(q["end"]) - want).days)
        if gap <= 10 and (best is None or gap < best[0]):
            best = (gap, q)
    return best[1] if best else None


def raw_of(p, method):
    """The model's raw values (pipeline/model.py normalize) of one prospectus period."""
    v = p["values"]
    if method != "reviewed_html_tables":
        return dict(v)                               # inline XBRL: the standard concepts (facts.CONCEPTS) already
    return {"revenue": v["revenue"], "oi": v["oi"], "pretax": v["pretax"], "tax": v["tax"], "ni": v["ni"], "pl": v["ni"],
            "costs_total": v["opex"], "ocf": v["ocf"], "da": v["da"], "sbc": v["sbc"], "capex": v.get("capex"),
            # every line the statement has, zeros too: a line absent a year earlier compares with zero (n/m)
            "cost_lines": [(k, lab, v[k]) for k, lab in COST if k in v],
            "nonop_lines": [(k, lab, v[k], note) for k, lab, note in NONOP if k in v],
            "bridge_lines": [(k, lab, v[k], note) for k, lab, note in BRIDGE if k in v]}


def _date(s):
    d = _d(s)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def _span(p):
    m = months(p)
    words = {12: "Fiscal year", 9: "Nine months", 6: "Six months", 3: "Three months"}.get(m, f"{m} months")
    return f"{words} ended {_date(p['end'])}"


def _lower(s):
    return s[:1].lower() + s[1:]


def _reword(text, m):
    """Analysis written for quarters, reworded for a half year or a year."""
    period = "year" if m == 12 else "period"
    for a, b in (("The quarter ended", f"The {period} ended"), ("Loss-making quarter", f"Loss-making {period}")):
        text = text.replace(a, b)
    return text


def note_keys(method):
    """{key: words} the reader looks for in the MD&A (pipeline/ipo_reader.py node notes): one key per chart line."""
    keys = {"revenue": ["revenue", "revenues", "net sales"], "tax": NOTE_KEYS["tax"], "ocf": NOTE_KEYS["ocf"],
            "net": NOTE_KEYS["net"], "sbc": NOTE_KEYS["sbc"], "da": NOTE_KEYS["da"], "capex": NOTE_KEYS["capex"],
            "costs": ["operating expenses", "costs and expenses"]}
    if method == "reviewed_html_tables":
        from .ipo import CASH, INCOME
        for k, _ in COST:
            keys[k] = [INCOME[k].lower()]
        for k, _, _ in NONOP:
            keys[k] = [INCOME[k].lower()]
        for k, _, _ in BRIDGE:
            keys[k] = [CASH[k].lower()]
    else:
        for k in ("cor", "gp", "rd", "sm", "ga", "sga", "nonop", "oi"):
            keys[k] = NOTE_KEYS[k]
    return keys


def _note_key(nid):
    """The node's key in note_keys: 'I:compute' -> 'compute', 'NL:fair_value' -> 'fair_value'."""
    if ":" in nid:
        return nid.split(":", 1)[1]
    return {"netloss": "net", "loss_abs": "net", "netinc": "net", "opcosts": "costs", "total": "costs",
            "nonop_in": "nonop", "nonop_out": "nonop", "burn": "ocf"}.get(nid, nid)


def _source(nid, p, doc):
    """Where the node's figure is: the statement line and the cell as printed, or the inline XBRL tag."""
    key = EVIDENCE.get(nid) or (nid.split(":", 1)[1] if ":" in nid else None)
    ev = (p.get("evidence") or {}).get(key) if key else None
    if not ev:
        return None
    if ev.get("cell") is not None:
        where = "statement of operations" if ev.get("statement") == "income" else "statement of cash flows"
        unit = " (in millions)" if ev.get("scale") == 1000000 else ""
        return f"{where[:1].upper() + where[1:]}: “{ev['label']}”, {ev['cell']}{unit}, {_lower(_span(p))}."
    return f"Inline XBRL tag {ev['label']} in the {doc.get('form', 'registration statement')}, {_lower(_span(p))}."


def footer(doc, p, prior, kind, Nc, reviewed):
    when = f"{doc.get('form', 'Registration statement')} filed {_date(doc['filed'])}" if doc.get("filed") else doc.get("form", "")
    how = ("read from its statement of operations and statement of cash flows (reviewed table mapping)" if reviewed
           else "read from the inline XBRL tags of its financial statements")
    lines = [f"Source: the company’s registration statement ({when}), {how}. {_span(p)}"
             f"{' (unaudited)' if months(p) < 12 else ''}. Percentages show each item’s share of the node it splits from or "
             f"flows into. Y/Y compares {('with ' + label(prior)) if prior else 'nothing: the filing has no earlier period of the same length'}; "
             "n/m = not meaningful (a comparison period was ≤ 0 or changed sign)."]
    if reviewed:
        lines.append("The prospectus reports no cost of revenue or gross profit: its operating expenses are drawn as its own "
                     "lines. The fair-value change of convertible notes, derivative liabilities and SAFEs is non-cash: the "
                     "cash flow statement adds it back, so it appears twice, once in each statement.")
    elif "oi_derived" in Nc["flags"]:
        lines.append("Operating profit = revenue minus total costs and expenses (derived; the filing does not tag operating income).")
    if kind == "loss":
        lines.append("Loss-making period: revenue, other income and the net loss together fund all costs; the cash bridge "
                     "starts from non-cash charges.")
    lines.append("Working capital &amp; other is the residual between operating cash flow and the listed items."
                 + (sankey_fcf_def() if Nc.get("capex") else ""))
    lines.append("Derived here, not line items in the filing: costs &amp; expenses (the funding total), working capital "
                 "&amp; other, operating cash sources and free cash flow.")
    return lines


def sankey_fcf_def():
    return (" Free cash flow = operating cash flow − capital expenditures (purchases of property and equipment). The IPO "
            "proceeds, offering price and dilution are not inferred.")


def headline(f, Nc, Ny):
    def g(a, b):
        return None if a is None or b is None or a <= 0 or b <= 0 else (a / b - 1) * 100
    fcf = Nc["ocf"] - Nc["capex"] if Nc.get("ocf") is not None and Nc.get("capex") is not None else None
    return {"revenue": Nc["R"], "rev_fmt": f.money(Nc["R"]), "yoy": g(Nc["R"], Ny and Ny["R"]),
            "oi": Nc["oi"], "oi_fmt": f.money(Nc["oi"]), "om": Nc["oi"] / Nc["R"] * 100,
            "ni": Nc["pl"], "ni_fmt": f.money(Nc["pl"]), "nm": Nc["pl"] / Nc["R"] * 100,
            "ocf": Nc.get("ocf"), "ocf_fmt": f.money(Nc["ocf"]) if Nc.get("ocf") is not None else None,
            "fcf": fcf, "fcf_fmt": f.money(fcf) if fcf is not None else None,
            "prior": {"revenue": Ny["R"], "oi": Ny["oi"], "ni": Ny["pl"], "ocf": Ny.get("ocf")} if Ny else None}


def reader_periods(doc):
    """[(period key, months, end)] the reader looks for in the MD&A comparisons (pipeline/ipo_reader.py node_notes)."""
    return [(f"{p['start']}_{p['end']}", months(p), p["end"]) for p in doc.get("periods") or ()
            if p.get("start") and p.get("end")]


def period_chart(doc, p, periods, notes=None):
    """One period's chart in the site's payload format (pipeline/build.py year_payload), or {"error"}. notes: the
    reader's MD&A passages ({period key or "*": {line key: [...]}}), quoted on the chart's nodes."""
    reviewed = doc.get("method") == "reviewed_html_tables"
    prior = prior_of(p, periods)
    Nc = normalize(raw_of(p, doc.get("method")))
    Ny = normalize(raw_of(prior, doc.get("method"))) if prior else None
    lab, plab = label(p), label(prior) if prior else None
    base = {"key": f"{p['start']}_{p['end']}", "label": lab, "start": p["start"], "end": p["end"], "months": months(p),
            "vs": plab, "vs_key": f"{prior['start']}_{prior['end']}" if prior else None}
    if not Nc:
        return {**base, "error": "No chart: revenue is zero or missing, or net income is missing."}
    # the money unit from the largest flow: a loss many times revenue reads in billions, not "$8,309.0M"
    big = max(Nc["R"], abs(Nc["pl"]), abs(Nc["oi"]), abs(Nc.get("ocf") or 0))
    try:
        nodes, links, kind = sankey.build(Nc, None, Ny, scale=big)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
        return {**base, "error": f"The figures do not add up into a chart ({str(e)[:120]})."}
    by_words = {**(notes or {}).get("*", {}), **(notes or {}).get(base["key"], {})}
    for n in nodes:
        n.pop("notekeys", None)
        for ln in n.get("lines") or []:                       # no previous quarter: Y/Y only
            if ln[0] == "mut" and ln[1].startswith("Y/Y "):
                ln[1] = ln[1].split(" · Q/Q ")[0]
            elif ln[0] == "mut":
                ln[1] = ln[1].replace("Y/Y, Q/Q compare", "Y/Y compares")
        n.pop("q", None)
        n.pop("cmp", None)
        src = _source(n["id"], p, doc)
        if src:
            n["source"] = src
        nk = _note_key(n["id"])
        if by_words.get(nk):
            n["notes"] = by_words[nk]
    for ln in links:
        ln.pop("q", None)
    f = Fmt(big)
    name = doc.get("name") or "The company"
    m = months(p)
    compare_y = None
    if Ny and plab:
        compare_y = {"vs": plab, "title": f"{name} {lab} vs {plab}: what changed",
                     "bullets": [_reword(b, m) for b in analysis.compare_bullets(f, plab, Nc, Ny)]}
    text = [_reword(x, m) for x in analysis.paragraphs(f, lab, Nc, None, Ny, py_label=plab or "a year earlier")]
    source_url = doc.get("source_url")
    acc = doc.get("accession")
    index = (f"https://www.sec.gov/Archives/edgar/data/{int(doc['cik'])}/{acc.replace('-', '')}/{acc}-index.html"
             if acc and doc.get("cik") else None)
    return {
        **base, "period": "fy", "compare": None, "compare_y": compare_y, "preliminary": False,
        "form": doc.get("form"), "filed": doc.get("filed"), "doc_url": source_url, "index_url": index, "kind": kind,
        "title": f"{name} {lab} earnings &amp; cash flow",
        "subtitle": f"{_span(p)} · GAAP · " + (f"Y/Y vs. {plab}" if plab else "no earlier period of the same length"),
        "footer": footer(doc, p, prior, kind, Nc, reviewed), "nodes": nodes, "links": links,
        "cite": {"text": f"{name} · {doc.get('form', '')} filed {_date(doc['filed']) if doc.get('filed') else ''} · {_span(p)}",
                 **({"doc": source_url} if source_url else {}), **({"index": index} if index else {})},
        "analysis": text, "headline": headline(f, Nc, Ny),
    }


def charts(doc, notes=None):
    """{"v", "periods": [chart...], "default"} for a parsed prospectus: every period, newest first (the longest of
    those ending last is the default)."""
    periods = [p for p in doc.get("periods") or () if p.get("values") and p.get("start") and p.get("end")]
    if not periods:
        return None
    order = sorted(periods, key=lambda p: (p["end"], months(p)), reverse=True)
    out = [period_chart(doc, p, periods, notes) for p in order]
    ok = [c for c in out if not c.get("error")]
    return {"v": VERSION, "periods": out, "default": ok[0]["key"] if ok else None}
