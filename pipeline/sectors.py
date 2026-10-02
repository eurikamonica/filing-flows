"""Sector mapping from SIC codes and industry / sector aggregate Sankeys."""
from .model import normalize

SECTORS = {
    "technology": "Technology", "communication": "Communication Services", "consumer-disc": "Consumer Discretionary",
    "consumer-staples": "Consumer Staples", "health": "Health Care", "financials": "Financials",
    "real-estate": "Real Estate", "energy": "Energy", "materials": "Materials", "industrials": "Industrials",
    "utilities": "Utilities", "other": "Other",
}

_RANGES = [
    (100, 999, "consumer-staples"), (1000, 1299, "materials"), (1300, 1399, "energy"), (1400, 1499, "materials"),
    (1500, 1799, "industrials"), (2000, 2199, "consumer-staples"), (2200, 2399, "consumer-disc"),
    (2400, 2499, "materials"), (2500, 2599, "consumer-disc"), (2600, 2699, "materials"),
    (2700, 2799, "communication"), (2800, 2829, "materials"), (2830, 2836, "health"), (2840, 2844, "consumer-staples"),
    (2845, 2899, "materials"), (2900, 2999, "energy"), (3000, 3399, "materials"), (3400, 3569, "industrials"),
    (3570, 3579, "technology"), (3580, 3599, "industrials"), (3600, 3629, "industrials"), (3630, 3639, "consumer-disc"),
    (3640, 3699, "technology"), (3710, 3716, "consumer-disc"), (3700, 3799, "industrials"), (3800, 3839, "industrials"),
    (3840, 3851, "health"), (3852, 3899, "industrials"), (3900, 3999, "consumer-disc"), (4000, 4799, "industrials"),
    (4800, 4899, "communication"), (4900, 4999, "utilities"), (5122, 5122, "health"), (5000, 5199, "industrials"),
    (5400, 5499, "consumer-staples"), (5912, 5912, "consumer-staples"), (5200, 5999, "consumer-disc"),
    (6798, 6798, "real-estate"), (6500, 6599, "real-estate"), (6000, 6799, "financials"),
    (7370, 7379, "technology"), (7000, 7299, "consumer-disc"), (7300, 7399, "industrials"),
    (7800, 7999, "communication"), (8000, 8099, "health"), (8100, 8999, "industrials"),
]


def sector_of(sic):
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return "other"
    for lo, hi, sec in _RANGES:            # specific ranges are listed before broad ones
        if lo <= s <= hi:
            return sec
    return "other"


SUM_KEYS = ["revenue", "oi", "pretax", "tax", "ni", "pl", "nci", "ocf", "da", "sbc", "capex", "cor", "rd"]


def aggregate_raw(raws):
    """Sum company quarter values into one synthetic statement (detail lines only when every company has them)."""
    out = {}
    for k in SUM_KEYS:
        vals = [r.get(k) for r in raws]
        if k in ("revenue", "pretax", "tax", "pl", "ni"):
            out[k] = sum(v or 0 for v in vals)
        elif k in ("nci", "rd", "da", "sbc"):
            out[k] = sum(v or 0 for v in vals) or None
        else:
            out[k] = sum(vals) if all(v is not None for v in vals) else None
    return out


def company_raw(N):
    """Back from a normalized company quarter to summable raw values."""
    items = dict(N["items"])
    return {"revenue": N["R"], "oi": N["oi"], "pretax": N["pretax"], "tax": N["tax"], "ni": N["ni"], "pl": N["pl"],
            "nci": N["nci"], "ocf": N["ocf"], "da": N["da"], "sbc": N["sbc"], "capex": N.get("capex"),
            "cor": N["cor"] if N.get("cor") else items.get("cor"), "rd": items.get("rd")}


def aggregate(members, top=10):
    """members: list of (label, Nc, Nq, Ny). Returns (Nc, Nq, Ny, lines_struct, lines_vals)."""
    members = sorted(members, key=lambda m: -m[1]["R"])
    head, tail = members[:top], members[top:]
    leaves = [{"id": f"m{i}", "label": m[0]} for i, m in enumerate(head)]
    if tail:
        leaves.append({"id": "others", "label": f"{len(tail)} other companies"})
    struct = {"leaves": leaves, "groups": [], "axis": "company"}

    def agg(idx):
        sel = [m[idx] for m in members]
        if idx and sum(1 for x in sel if x) < len(sel):
            have = sum(m[1]["R"] for m in members if m[idx])
            if have < 0.9 * sum(m[1]["R"] for m in members):
                return None, None
        raws = [company_raw(x) for x in sel if x]
        vals = {f"m{i}": m[idx]["R"] for i, m in enumerate(head) if m[idx]}
        if tail:
            vals["others"] = sum(m[idx]["R"] for m in tail if m[idx])
        n = normalize(aggregate_raw(raws))
        if n is not None and len(vals) < len(leaves):
            vals = None
        return n, vals

    (Nc, vc), (Nq, vq), (Ny, vy) = agg(1), agg(2), agg(3)
    return Nc, Nq, Ny, struct, (vc, vq, vy)
