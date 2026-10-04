"""Normalize raw XBRL quarter values into one consistent income-statement + cash-flow structure."""

ITEM_LABELS = {"cor": "Cost of revenue", "rd": "Research &amp; development", "sm": "Sales &amp; marketing",
               "ga": "General &amp; admin", "sga": "SG&amp;A", "other_opex": "Other operating costs"}


def _close(a, b, tol=0.01):
    return a is not None and b is not None and abs(a - b) <= tol * max(abs(a), abs(b), 1)


def normalize(raw):
    """Returns a dict of consistent quarter values, or None when the core lines are missing."""
    if not raw or not raw.get("revenue") or raw["revenue"] <= 0:
        return None
    R = raw["revenue"]
    ni, pl, nci = raw.get("ni"), raw.get("pl"), raw.get("nci")
    if ni is None and pl is None:
        return None
    if pl is None:
        pl = ni + (nci or 0)
    if ni is None:
        ni = pl - (nci or 0)
    nci = pl - ni
    tax, pretax = raw.get("tax"), raw.get("pretax")
    if pretax is None and tax is not None:
        pretax = pl + tax
    if tax is None and pretax is not None:
        tax = pretax - pl
    if pretax is None:
        pretax, tax = pl, 0.0
    flags = []
    if not _close(pretax - tax, pl, 0.005):          # inconsistent tags: trust net income and tax
        pretax = pl + tax
        flags.append("pretax_fixed")
    oi = raw.get("oi")
    if oi is None and raw.get("costs_total") is not None:
        oi = R - raw["costs_total"]
        flags.append("oi_derived")
    if oi is None:
        oi = pretax
        flags.append("oi_missing")
    nonop = pretax - oi

    gp, cor = raw.get("gp"), raw.get("cor")
    gp_path = gp is not None and 0 < gp <= R
    if gp_path:
        cor = R - gp
        pool = gp - oi                                  # operating expenses
    else:
        gp = None
        pool = R - oi                                   # all operating costs
    items = []
    if not gp_path and cor is not None and 0 < cor < pool:
        items.append(("cor", cor))
    if raw.get("rd"):
        items.append(("rd", raw["rd"]))
    sm, ga, sga = raw.get("sm"), raw.get("ga"), raw.get("sga")
    if sm and ga and (sga is None or _close(sm + ga, sga)):
        items += [("sm", sm), ("ga", ga)]
    elif sga:
        items.append(("sga", sga))
    else:
        items += [(k, v) for k, v in (("sm", sm), ("ga", ga)) if v]
    items = [(k, v) for k, v in items if v and v > 0]
    used = sum(v for _, v in items)
    if pool <= 0 or used > pool * 1.005:
        items = []                                      # tags overlap: show the total only
    elif pool - used > max(0.005 * pool, 1):
        items.append(("other_opex", pool - used))
    if len(items) == 1:
        items = []

    ocf, da, sbc = raw.get("ocf"), raw.get("da"), raw.get("sbc")
    # what the D&A figure holds: depreciation alone when that is all the filing tags (or the release prints)
    dep_only = (da is not None and raw.get("dep") is not None and raw.get("amort") is None
                and abs(da - raw["dep"]) <= 0.001 * abs(da) + 1)
    if da is not None and da < 0:
        da = None
    if sbc is not None and sbc < 0:
        sbc = None
    return {
        "R": R, "gp": gp, "cor": cor if gp_path else (cor if cor and cor < pool else None), "gp_path": gp_path,
        "pool": pool, "items": items, "oi": oi, "nonop": nonop, "pretax": pretax, "tax": tax,
        "ni": ni, "nci": nci, "pl": pl, "ocf": ocf, "da": da or 0.0, "sbc": sbc or 0.0,
        "capex": raw.get("capex"), "flags": flags,
        "da_label": "Depreciation" if dep_only else "Depreciation &amp; amortization",
    }


def quantities(N, lines=None):
    """Signed quantities used to value every node in any period (same keys across periods)."""
    if not N:
        return {}
    Q = {"revenue": N["R"], "gp": N["gp"], "cor": N["cor"], "opex": N["pool"] if N["gp_path"] else None,
         "costs": N["pool"] if not N["gp_path"] else None, "oi": N["oi"], "nonop": N["nonop"],
         "pretax": N["pretax"], "tax": N["tax"], "nci": N["nci"], "ni": N["ni"], "pl": N["pl"],
         "ocf": N["ocf"], "da": N["da"], "sbc": N["sbc"]}
    for k, v in N["items"]:
        Q["item:" + k] = v
    if N["ocf"] is not None:
        r = N["ocf"] - N["pl"] - N["da"] - N["sbc"]
        Q["r"] = r
        Q["r_nci"] = r + N["nci"]
        Q["ni_to_ocf"] = N["ni"] + min(r + N["nci"], 0)
        Q["bridge"] = N["da"] + N["sbc"] + max(r, 0) + max(N["pl"], 0) + max(-N["ocf"], 0)
        if N.get("capex") is not None:                    # operating cash flow -> capital expenditures + free cash flow
            Q["capex"] = N["capex"]
            Q["fcf"] = N["ocf"] - N["capex"]
            Q["fcf_neg"] = N["capex"] - N["ocf"]          # the part of capex operating cash flow did not cover
            Q["capex_from_ocf"] = min(N["capex"], max(N["ocf"], 0))
    Q["pretax_less_nci"] = N["pretax"] - N["nci"]
    Q["opcosts"] = N["R"] - N["oi"]
    Q["funding"] = N["R"] + max(N["nonop"], 0) + max(-N["tax"], 0) + max(-N["pl"], 0)
    Q["netloss"] = -N["pl"]
    Q["taxben"] = -N["tax"]
    for lid, v in (lines or {}).items():
        Q["line:" + lid] = v
    return Q
