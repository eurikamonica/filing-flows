"""What moved profit: a bridge from last year's operating income and net income to this year's, for each quarter
(against the same quarter a year earlier) and fiscal year — the "What moved profit" section of the company page.

Operating income, last year → this year:
  revenue growth at last year's gross margin   (revenue₁ − revenue₀) × gross margin₀
  gross margin change                          revenue₁ × (gross margin₁ − gross margin₀)
  each operating expense line                  −(expense₁ − expense₀): R&D, selling, general and administrative
  other operating items                        what the lines above leave unexplained in the change of operating income
                                               (restructuring, impairments, amortization: lines without their own tag)
Net income, last year → this year:
  operating income change, non-operating items change (interest, other income), then income tax split into the
  tax-rate effect −pretax₁ × (tax rate₁ − tax rate₀) and the tax on the change in profit −(pretax₁ − pretax₀) × tax
  rate₀, and what lies below the tax line (discontinued operations, minority interests, equity-method results).

Every bar is arithmetic on tagged figures, so the bars add up exactly. Price, volume and product mix cannot be told
apart from these figures: the revenue bar stays one bar, and each period carries an empty "mdna" list for amounts the
company quantifies itself in its MD&A ("higher volume added $120 million"), to be read from the filing's text.
"""
from . import facts as F
from . import fsa as W

KEEP_Q, KEEP_FY = 8, 5
INPUTS = ("revenue", "cor", "gp", "rd", "sga", "sm", "ga", "oi", "pretax", "tax", "ni")


def _read(fx, ev, end, annual):
    vals, refs = {}, {}
    for k in INPUTS:
        v, r = W.keyed(fx, ev, k, end, annual)
        if v is not None:
            vals[k], refs[k] = v, r
    if "gp" not in vals and "revenue" in vals and "cor" in vals:
        vals["gp"] = vals["revenue"] - vals["cor"]                  # derived: shown as such in the evidence
    return vals, refs


def bridge(a, b):
    """The bars from period a (last year) to period b (this year), from their figures; None without operating income
    and revenue in both. {"op": [[key, amount]], "below": [[key, amount]]}: each list adds up to the change."""
    if not all(k in a and k in b for k in ("revenue", "oi")):
        return None
    op = []
    if "gp" in a and "gp" in b and a["revenue"] > 0 and b["revenue"] > 0:
        m0, m1 = a["gp"] / a["revenue"], b["gp"] / b["revenue"]
        op.append(["rev", (b["revenue"] - a["revenue"]) * m0])
        op.append(["gm", b["revenue"] * (m1 - m0)])
        lines = ["rd", "sga"] if "sga" in a and "sga" in b else ["rd", "sm", "ga"]
        for k in lines:
            if k in a and k in b:
                op.append([k, -(b[k] - a[k])])
    else:                                                        # no cost of revenue: revenue, then all costs together
        op.append(["rev_all", b["revenue"] - a["revenue"]])
    op.append(["other_op", (b["oi"] - a["oi"]) - sum(x for _, x in op)])
    below = None
    if all(k in a and k in b for k in ("pretax", "ni")):
        below = [["d_oi", b["oi"] - a["oi"]], ["nonop", (b["pretax"] - b["oi"]) - (a["pretax"] - a["oi"])]]
        if "tax" in a and "tax" in b:
            if a["pretax"] > 0 and b["pretax"] > 0:
                r0, r1 = a["tax"] / a["pretax"], b["tax"] / b["pretax"]
                below += [["tax_rate", -b["pretax"] * (r1 - r0)], ["tax_base", -(b["pretax"] - a["pretax"]) * r0]]
            else:
                below.append(["tax", -(b["tax"] - a["tax"])])
            taxed = lambda p: p["pretax"] - p["tax"]
        else:
            taxed = lambda p: p["pretax"]
        below.append(["after_tax", (b["ni"] - taxed(b)) - (a["ni"] - taxed(a))])
    return {"op": op, "below": below}


def _prior(ends, end):
    xs = [e for e in ends if 350 <= (F.d(end) - F.d(e)).days <= 380]
    return max(xs) if xs else None


def compute(fx, ev, qe, ye, fye="1231"):
    """{"q": [...], "fy": [...]}: each period with its figures, last year's, their evidence and the bars, or None."""
    out = {}
    for kind, ends, keep in (("q", qe, KEEP_Q), ("fy", ye, KEEP_FY)):
        annual, rows = kind == "fy", []
        for e in ends[-keep:]:
            p = _prior(ends if annual else qe, e)
            if not p:
                continue
            b, rb = _read(fx, ev, e, annual)
            a, ra = _read(fx, ev, p, annual)
            br = bridge(a, b)
            if not br:
                continue
            lab = (lambda x: F.fiscal_year_label(x, fye)[0]) if annual else (lambda x: F.fiscal_label(x, fye)[0])
            rows.append({"end": e, "prev": p, "label": lab(e), "prev_label": lab(p), "cur": b, "pri": a,
                         "ev": {"cur": rb, "pri": ra}, **br, "mdna": None})
        if rows:
            out[kind] = rows
    return out or None
