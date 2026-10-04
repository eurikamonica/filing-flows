"""Automated data checks for one chart: things that are often errors (in a company's XBRL tags, in reading an earnings
release, or in deriving a quarter from year-to-date figures) and things that are real but easy to misread.

    checks(q, c, Nc, Nq, Ny) -> [{"level": "warn" | "note", "code": ..., "text": ...}]

"warn": probably a data problem; the chart says so in its header and footer, the owner's e-mail says to check before
posting, and automatic X posting skips it. "note": unusual but usually real; the chart explains it in the footer.
Nothing here changes a figure: the chart still shows what the filing says.
"""
import datetime as dt

DISCLAIMER = ("Figures are read automatically from SEC filings by fixed rules and can contain errors, in the company's own "
              "XBRL tags or in this reading; check the filing before relying on them. Not investment advice.")

JUMP_NOTE = 3.0          # revenue at least 3x (or at most a third of) the comparison quarter: unusual
JUMP_WARN = 10.0         # 10x: usually a units or period error
LONG_QUARTER = 95        # days: a 14-week quarter (a 53-week fiscal year)
SHORT_QUARTER = 84


def _days(a, b):
    try:
        return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days
    except (TypeError, ValueError):
        return None


def money(v):
    a, s = abs(v), "−" if v < 0 else ""
    if a >= 0.95e9:
        return f"{s}${a / 1e9:.1f}B"
    if a >= 1e8:
        return f"{s}${a / 1e9:.2f}B"
    if a >= 0.95e6:
        return f"{s}${a / 1e6:.1f}M"
    return f"{s}${a / 1e3:.0f}K"


def _ratio_words(x):
    return f"{x:.0f}×" if x >= 10 else f"{x:.1f}×"


def _quarter_days(c, end):
    """Length of the stored quarter ending `end`, from its own previous-quarter end."""
    q = (c.get("quarters") or {}).get(end) if end else None
    return _days(end, q.get("q1_end")) if q and q.get("q1_end") else None


def checks(q, c, Nc, Nq=None, Ny=None, annual=False):
    """q: the stored quarter (or fiscal year, annual=True); c: the company; N*: normalized figures (model.normalize)."""
    out = []

    def add(level, code, text):
        out.append({"level": level, "code": code, "text": text})

    R = Nc["R"]
    # the length of the period (53-week fiscal years have one 14-week quarter)
    cur = _days(q.get("end"), q.get("q1_end")) if q.get("q1_end") and not annual else None
    py = None if annual else _quarter_days(c, q.get("py_end"))
    year = _days(q.get("end"), q.get("py_end")) if annual and q.get("py_end") else None
    if year and year >= 369:
        add("note", "long_year", f"This fiscal year has 53 weeks ({year} days since the year before ended): growth rates "
                                 "include an extra week.")
    elif cur and cur >= LONG_QUARTER and (py is None or py < LONG_QUARTER):
        add("note", "long_quarter", f"This quarter has 14 weeks ({cur} days) against 13 in the quarters it is compared with: "
                                    "growth rates include an extra week.")
    elif py and py >= LONG_QUARTER and cur and cur < LONG_QUARTER:
        add("note", "long_quarter_py", f"The year-ago quarter had 14 weeks ({py} days); this one has 13: Y/Y growth is "
                                       "understated by about a week.")
    elif cur and cur < SHORT_QUARTER:
        add("warn", "short_quarter", f"This period covers only {cur} days since the previous quarter: check the filing's period.")

    # revenue jumps: real growth, a fourth quarter derived from restated annual figures, or a units / period error
    derived = q.get("form") == "10-K" and not annual  # a 10-K quarter = the year minus the first nine months
    for N, words in ((Ny, "the year before" if annual else "the year-ago quarter"), (Nq, "the previous quarter")):
        if not N or not N.get("R") or N["R"] <= 0:
            continue
        x = R / N["R"]
        big = max(x, 1 / x)
        if big < JUMP_NOTE:
            continue
        rel = _ratio_words(x) if x >= 1 else f"{x * 100:.1f}% of" if x < 0.1 else f"{x * 100:.0f}% of"
        then = f"{words} ({money(N['R'])} then)"
        if derived and big >= 5:
            add("warn", "derived_jump", f"Revenue is {rel} {then}. This fourth quarter is the year minus the first nine "
                                        "months, so restated or reclassified annual figures can distort it: check the 10-K.")
        elif big >= JUMP_WARN and N["R"] >= 1e7 and R >= 1e6:
            add("warn", "revenue_jump", f"Revenue is {rel} {then}: check units and periods in the filing.")
        else:
            add("note", "revenue_jump", f"Revenue is {rel} {then}: an unusually large change; the figures are as filed.")
        break

    # income statement shapes that are rare
    if Nc.get("gp") is not None and Nc["gp"] > 0.95 * R:
        add("note", "gross_margin", f"Gross margin is {Nc['gp'] / R * 100:.0f}%: almost no cost of revenue is tagged.")
    if Nc["pl"] > R:
        add("note", "net_over_revenue", "Net earnings exceed revenue: usually investment gains, a sale or a tax benefit "
                                        "(see other income and tax).")
    if Nc["pretax"] > 0.02 * R:
        rate = Nc["tax"] / Nc["pretax"]
        if rate > 0.6 or rate < -0.5:
            add("note", "tax_rate", f"Effective tax rate {rate * 100:.0f}%: one-off tax items are likely.")
    if "pretax_fixed" in Nc.get("flags", []):
        add("note", "pretax_fixed", "Pre-tax earnings minus tax did not equal net earnings in the filing (often discontinued "
                                    "operations or equity-method income); pre-tax is shown as net earnings plus tax.")
    if "oi_missing" in Nc.get("flags", []):
        add("note", "oi_missing", "The filing has no operating income figure: operating profit is shown equal to pre-tax "
                                  "earnings.")
    other = dict(Nc.get("items") or []).get("other_opex")
    if other and Nc["pool"] > 0.1 * R and other > 0.5 * Nc["pool"]:
        add("note", "other_costs", f"Other operating costs ({money(other)}, {other / Nc['pool'] * 100:.0f}% of the total) are "
                                   "the costs the filing's tags do not break out, such as the cost of services; the income "
                                   "statement has the split.")

    # cash flow
    ocf = Nc.get("ocf")
    if ocf is not None:
        if abs(ocf) > 5 * R and abs(ocf) > 3 * abs(Nc["pl"]) + 0.05 * R:     # out of scale with revenue AND earnings
            add("warn", "ocf_scale", f"Operating cash flow ({money(ocf)}) is {abs(ocf) / R:.0f}× revenue: check units and "
                                     "the period (cash flows are year-to-date in 10-Qs).")
        elif ocf > R:
            add("note", "ocf_over_revenue", f"Operating cash flow is {ocf / R * 100:.0f}% of revenue: unusual, usually "
                                            "customer prepayments or a large working-capital swing; as filed.")
        capex = Nc.get("capex")
        if capex is not None and capex < -0.01 * R:
            add("warn", "capex_negative", f"Capital expenditures came out negative ({money(capex)}): usually a restated "
                                          "year-to-date figure; check the cash flow statement.")
        if capex and capex > 0.05 * R and not Nc["da"]:
            add("note", "da_missing", "Depreciation is not tagged separately: it sits in working capital & other.")
        # free cash flow as the company defines it (pipeline/reported.py): drawn, or named beside ours
        from .reported import definition
        use, said = Nc.get("co_fcf_use"), Nc.get("co_fcf_said")
        ours = ocf - capex if capex else None
        if use:
            add("note", "fcf_company", f"{use['name']} is the company's own figure from its earnings release "
                                       f"({money(use['fcf'])} = {definition(use['parts'])})"
                                       + (f"; operating cash flow − capex alone would be {money(ours)}." if ours is not None
                                          and abs(ours - use['fcf']) > 0.02 * abs(use['fcf']) else "."))
        elif said:
            add("note", "fcf_definition", f"The company reports {said['name'].lower()} of {money(said['fcf'])} "
                                          f"({said['definition']}); this chart shows operating cash flow − capex"
                                          + (f" ({money(ours)})." if ours is not None else "."))

    # the earnings release did not match the 10-Q/10-K that replaced it
    rc = q.get("from_release") if isinstance(q.get("from_release"), dict) else {}
    bad = [f.get("name") or f.get("key") for f in rc.get("fields") or [] if isinstance(f, dict) and not f.get("ok", True)]
    if bad:
        add("note", "release_mismatch", "The earlier earnings release differed from this filing on " +
                                        ", ".join(x.lower() for x in bad) + "; the chart shows the filing.")
    return out


def has_warning(found):
    return any(x["level"] == "warn" for x in found or [])


# ------------------------------------------------------------------ for the e-mails
def lines(q):
    """A chart's checks as sentences: "Data check: …" for a probable error, "Note: …" for the rest."""
    return [f"{'Data check' if x['level'] == 'warn' else 'Note'}: {x['text']}" for x in q.get("checks") or []]


def html_box(q, owner=False):
    """The checks as a small box for an e-mail ("" when there are none); amber when one flags a probable error."""
    import html as H
    found = q.get("checks") or []
    if not found:
        return ""
    warn = has_warning(found)
    head = ("Check before posting: a probable data error" if owner else "Data check: please verify in the filing") if warn \
        else "Notes on these figures"
    items = "".join(f'<li style="margin:0 0 3px">{H.escape(x["text"])}</li>' for x in found)
    return (f'<div style="margin:0 0 12px;padding:8px 12px;border-radius:6px;background:{"#fbefd9" if warn else "#f3f2ee"};'
            f'font:13.5px/1.5 Helvetica,Arial,sans-serif;color:{"#5c3300" if warn else "#3d3c39"}">'
            f'<div style="font-weight:600;margin-bottom:3px">{H.escape(head)}</div>'
            f'<ul style="margin:0;padding-left:18px">{items}</ul></div>')
