"""Where each number on a chart comes from: the reported line (its name in the filing and its XBRL tag) or how it was
calculated. Shown in the node's note on the site, so a reader can check every figure against the filing."""
import re

from . import dims

YTD = "The quarter is the year-to-date figure minus the prior year-to-date (the statement shows year-to-date amounts)."


def label_for(concept, fx, roles):
    """The line's name as printed in the company's statement, else SEC's standard label, else the tag spaced out."""
    lab = dims.statement_label((roles or {}).get("us-gaap_" + concept)) or ((fx or {}).get("__labels__") or {}).get(concept)
    return lab if lab and " " in lab else dims.humanize(lab or concept)


def from_xbrl(fx, end, roles=None, annual=False):
    """{key: {"c", "l", "ytd", "how"}} for every figure read from SEC's XBRL company facts."""
    from . import facts
    return {k: {"c": "us-gaap:" + v["c"], "l": label_for(v["c"], fx, roles), "ytd": v["ytd"], "how": "xbrl"}
            for k, v in facts.provenance(fx, end, annual).items()}


def from_release(rel, raw):
    """The rows of the earnings release's tables the figures were read from."""
    out = {}
    for k, lab in list((rel.get("labels") or {}).items()) + list((rel.get("cf_labels") or {}).items()):
        if raw.get(k) is not None and lab:
            out.setdefault(k, {"l": lab[:1].upper() + lab[1:], "how": "release"})
    return out


def _quote(s):
    return f"“{s['l']}”" if s and s.get("l") else "the line"


def reported(s, period="q"):
    """One sentence for a figure taken from a reported line."""
    if not s:
        return None
    if s.get("how") == "release":
        return f"Reported line: {_quote(s)} in the earnings release’s tables (8-K, Exhibit 99.1)."
    tag = s.get("c") or ""
    own = ", the company’s own tag" if tag and not tag.startswith("us-gaap:") else ""
    where = "SEC’s XBRL company facts" if s.get("how") == "xbrl" else "the filing’s own XBRL data"
    out = f"Reported line: {_quote(s)} ({tag}{own}), from {where}."
    if period == "q" and s.get("ytd"):
        out += " " + YTD
    return out


FCF = ("Calculated: operating cash flow − capital expenditures. Proceeds from selling assets and finance-lease repayments "
       "are not netted, so it can differ from a free cash flow figure the company reports itself.")

CALC = {
    "cor_gp": "Calculated: revenue − gross profit.",
    "opex": "Calculated: gross profit − operating profit (all operating expenses together).",
    "costs": "Calculated: revenue − operating profit (all costs and expenses together).",
    "other_opex": "Calculated: operating costs − the cost lines shown separately (what the filing does not itemize).",
    "nonop": "Calculated: pre-tax earnings − operating profit (interest, investment results and other items).",
    "nci": "Calculated: net earnings including minority interests − net earnings attributable to shareholders.",
    "wc": "Calculated: operating cash flow − net earnings − depreciation & amortization − share-based compensation "
          "(the residual: working capital and other items).",
    "funding": "Calculated: revenue + other income + tax benefit + net loss (together they fund all costs).",
    "opcosts": "Calculated: revenue − operating profit.",
    "bridge": "Calculated: the sum of the cash sources flowing into it.",
    "loss_abs": "The net loss, the same figure as in the income statement.",
    "fcf_neg": "Calculated: capital expenditures − operating cash flow (the part of capex operating cash flow did not "
               "cover, paid from cash or financing).",
}


def attach(nodes, src, Nc, lines_struct=None, period="q", capex_src=None):
    """Give every node a `source` line: the reported line it was read from, or how it was calculated."""
    src = dict(src or {})
    if capex_src:                         # the capex line found for this period (standard tag, own tag or release row)
        lab = capex_src.get("label") or ""
        lab = lab if " " in lab or not lab else dims.humanize(lab)
        src["capex"] = {"c": capex_src.get("concept"), "l": lab[:1].upper() + lab[1:], "how": capex_src.get("how"),
                        "ytd": (src.get("capex") or {}).get("ytd", False)}
    flags = set(Nc.get("flags") or [])
    axis = (lines_struct or {}).get("axis")
    rev = src.get("revenue")
    for n in nodes:
        nid, out = n["id"], None
        get = lambda k: reported(src.get(k), period)
        if nid == "revenue":
            out = get("revenue")
            if out and rev and rev.get("how") == "xbrl":
                out += " When a company tags revenue more than one way, the largest (the total) is used."
        elif nid.startswith(("L:", "G:")):
            member = nid[2:]
            kind = "A subtotal the company reports" if nid.startswith("G:") else "A revenue line"
            out = (f"{kind}: revenue tagged {member} on {axis or 'a breakdown axis'} in the filing’s own XBRL "
                   "(the lines add up to total revenue).")
        elif nid == "gp":
            out = get("gp")
        elif nid == "cor":
            out = CALC["cor_gp"]
        elif nid == "I:cor":
            out = get("cor")
        elif nid in ("I:rd", "I:sm", "I:ga", "I:sga"):
            out = get(nid[2:])
        elif nid == "I:other_opex":
            out = CALC["other_opex"]
        elif nid == "opex":
            out = CALC["opex"]
        elif nid == "costs":
            out = CALC["costs"]
        elif nid == "oi":
            if "oi_derived" in flags:
                ct = src.get("costs_total")
                out = f"Calculated: revenue − total costs and expenses ({_quote(ct) if ct else 'as reported'}); the company does not report an operating income line."
            elif "oi_missing" in flags:
                out = "The filing has no operating income line, so operating profit is shown equal to pre-tax earnings."
            else:
                out = get("oi")
        elif nid in ("nonop_in", "nonop_out"):
            out = CALC["nonop"]
        elif nid == "pretax":
            out = get("pretax") or "Calculated: net earnings + income tax."
        elif nid in ("tax", "taxben"):
            out = get("tax") or "Calculated: pre-tax earnings − net earnings."
        elif nid in ("net", "netinc", "netloss"):
            out = get("ni") if n.get("name", "").startswith("Net earnings") and "attributable" in " ".join(
                str(x[1]) for x in n.get("lines") or []) else (get("pl") or get("ni"))
        elif nid == "nci":
            out = get("nci") or CALC["nci"]
        elif nid in ("ocf", "burn"):
            out = get("ocf")
        elif nid in ("da", "sbc"):
            out = get(nid)
        elif nid in ("wc_in", "wc_out"):
            out = CALC["wc"]
        elif nid == "capex":
            out = get("capex")
        elif nid == "fcf":
            out = FCF
        elif nid == "fcf_neg":
            out = CALC["fcf_neg"]
        elif nid == "total":
            out = CALC["funding"]
        elif nid == "opcosts":
            out = CALC["opcosts"]
        elif nid == "bridge":
            out = CALC["bridge"]
        elif nid == "loss_abs":
            out = CALC["loss_abs"]
        if out:
            n["source"] = re.sub(r"\s+", " ", out).strip()
    return nodes
