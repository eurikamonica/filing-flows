"""The balance sheet rolled forward: two balance sheets (a quarter apart, or a year apart) and the income statement and
cash flow statement flows that explain the change in each account — the company page's "Balance sheet roll-forward".

  stock(t1) − stock(t0) = the flows of the period that touch the account + what the statements do not explain
  cash           Δ = operating + investing + financing cash flow (+ currency effect)      (the cash flow statement)
  receivables    Δ = −(the cash-flow statement's "change in receivables")                 (an increase uses cash)
  inventory      Δ = −(change in inventories)
  PP&E           Δ = capital expenditure − depreciation and amortisation (D&A covers intangibles too: approximate)
  investments    Δ = −(other investing cash flow: securities bought and sold, acquisitions, net)
  payables       Δ = +(change in payables)
  debt           Δ = net borrowing (issued − repaid)
  equity         Δ = net income + share-based compensation − buybacks − dividends − shares withheld + shares issued
  everything the flows do not explain is the account's residual (currency, acquisitions, reclassification, fair value,
  other comprehensive income): shown as a bar of its own, never spread over the others

The balances come from the same standard tags as the reformulated balance sheet (reform.LINES), read at each
quarter end; the quarter's flows are the ones already on the page (fsa: the net income → OCF bridge; capital: the
cash-flow sections by quarter). "y" entries compare a quarter end with the same quarter end a year earlier and add
the four quarters' flows (data_kind derived); "q" entries are one quarter (flows from three-month facts or year-to-date
differences, as the bridge reads them). Each account carries its tags; the page draws the figures and nothing else.
"""
from . import facts as F
from . import fsa as W
from . import reform as R

VERSION = 1
KEEP_Q, KEEP_Y = 8, 4
# account -> (side, name, reform line keys it adds up)
ACCOUNTS = [
    ("cash", "a", "Cash and equivalents", ["cash"]),
    ("inv_sec", "a", "Investments", ["sti", "lti", "secs", "eqsec", "eqm"]),
    ("ar", "a", "Receivables", ["ar", "orec"]),
    ("inv", "a", "Inventory", ["inv"]),
    ("ppe", "a", "Property, plant and equipment", ["ppe", "rou", "invprop"]),
    ("gw", "a", "Goodwill and intangibles", ["gw", "intang"]),
    ("oth_a", "a", "Other assets", []),
    ("ap", "l", "Payables", ["ap"]),
    ("debt", "l", "Debt", ["std", "ltdc", "ltd", "flease", "olease", "lease"]),
    ("oth_l", "l", "Other liabilities", []),
    ("eq", "e", "Equity", []),
]
LINE_GROUPS = {k: gs for k, _, _, _, _, gs in R.LINES}
# which cash-flow-statement lines explain which account, and with what sign on the account's balance
#   ("bridge", key, sign): a net income → OCF bridge item (fsa.NONCASH / fsa.WC keys), already a cash effect
#   ("cap", key, sign): a capital-allocation item (capital.py items), cash effect (+ inflow, − outflow)
#   ("p", key, sign): a figure of the quarter (ni)
FLOWS = {
    "cash": [("p", "ocf", +1, "Operating cash flow"), ("sec", "inv", +1, "Investing cash flow"), ("sec", "fin", +1, "Financing cash flow"), ("cap", "fx", +1, "Currency effect on cash")],
    "ar": [("bridge", "d_ar", -1, "Change in receivables (cash flow statement)"), ("bridge", "d_orec", -1, "Change in other receivables"), ("bridge", "d_casset", -1, "Change in contract assets")],
    "inv": [("bridge", "d_inv", -1, "Change in inventories (cash flow statement)")],
    "ppe": [("cap", "capex", -1, "Capital expenditure"), ("cap", "realestate", -1, "Real estate bought"), ("bridge", "da", -1, "Depreciation and amortisation")],
    "inv_sec": [("cap", "inv_other", -1, "Other investing (securities and acquisitions, net)"), ("cap", "sales", -1, "Asset and business sales"), ("bridge", "gain_inv", -1, "Gains on investments")],
    "gw": [("cap", "acq", -1, "Acquisitions, net of cash"), ("bridge", "impair", -1, "Impairments")],
    "oth_a": [("bridge", "d_oassets", -1, "Change in prepaid and other assets"), ("bridge", "dtax", -1, "Deferred taxes")],
    "ap": [("bridge", "d_ap", +1, "Change in payables (cash flow statement)")],
    "oth_l": [("bridge", "d_accr", +1, "Change in accrued liabilities"), ("bridge", "d_emp", +1, "Change in employee liabilities"), ("bridge", "d_contract", +1, "Change in deferred revenue"),
              ("bridge", "d_oliab", +1, "Change in other liabilities"), ("bridge", "d_tax", +1, "Change in income taxes payable"), ("bridge", "d_onet", +1, "Other operating capital")],
    "debt": [("cap", "borrow", +1, "Net borrowing (issued − repaid)")],
    "eq": [("p", "ni", +1, "Net income"), ("bridge", "sbc", +1, "Share-based compensation"), ("cap", "buyback", +1, "Share buybacks"), ("cap", "div", +1, "Dividends"),
           ("cap", "withhold", +1, "Shares withheld for taxes"), ("cap", "stock", +1, "Shares issued"), ("cap", "nci", +1, "Minority-interest flows")],
}
NOTES = {"ppe": "Depreciation and amortisation includes the amortisation of intangibles where the filing reports one line: the PP&E residual then carries the intangibles' share.",
         "gw": "Acquisitions add goodwill and intangibles at their allocated values, not at the cash paid; the residual is the difference and the amortisation.",
         "inv_sec": "Securities bought and sold sit in 'other investing' with everything else the section does not name.",
         "eq": "Other comprehensive income (currency translation, unrealised gains) moves equity without passing through net income: it is in the residual.",
         "cash": "The cash flow statement's cash can include restricted cash the balance sheet shows elsewhere: a small residual is that difference."}


def _bal2(fx, ev, keys, start, end):
    """the sum of the reform lines' balances at both dates, one tag per group and only tags with a balance at BOTH
    dates (a line tagged at the year end alone would otherwise show up as a movement); returns (open, close, tags)"""
    o = c = None
    tags = []
    for k in keys:
        for g in LINE_GROUPS.get(k, []):
            picked = None
            for concept in g:
                vo, _, _ = W.balance(fx, ev, [concept], start, 0, 7)
                vc, _, _ = W.balance(fx, ev, [concept], end, 0, 7)
                if vo is not None and vc is not None:
                    picked = (concept, vo, vc)
                    break
            if picked:
                o = (o or 0) + picked[1]
                c = (c or 0) + picked[2]
                tags.append(picked[0])
                if picked[0] in R.ALL_CURRENT_DEBT:
                    break
    return o, c, tags


def _totals(fx, ev, day):
    t = {}
    for k in ("assets", "liab", "le", "cse", "nci", "eq_all", "temp"):
        t[k], _, _ = W.balance(fx, ev, R.TOTALS[k], day, 0, 7)
    eq = t["eq_all"] if t["eq_all"] is not None else (None if t["cse"] is None else t["cse"] + (t["nci"] or 0))
    if t["liab"] is None and t["le"] is not None and eq is not None:
        t["liab"] = t["le"] - eq - (t["temp"] or 0)
    if eq is None and t["assets"] is not None and t["liab"] is not None:
        eq = t["assets"] - t["liab"] - (t["temp"] or 0)
    return t["assets"], t["liab"], eq


def balances(fx, ev, start, end):
    """({account: open}, {account: close}, {account: tags}) with the plugs (other assets, other liabilities) from the
    totals at each date; (None, None, {}) without total assets, liabilities and equity at both dates"""
    ta = [_totals(fx, ev, d) for d in (start, end)]
    if any(v is None for t in ta for v in t):
        return None, None, {}
    o, c, tags = {}, {}, {}
    for k, side, _, keys in ACCOUNTS:
        if keys:
            o[k], c[k], tags[k] = _bal2(fx, ev, keys, start, end)
    for d, (assets, liab, eq) in zip((o, c), ta):
        d["oth_a"] = assets - sum(d.get(k) or 0 for k, s, _, keys in ACCOUNTS if s == "a" and keys)
        d["oth_l"] = liab - sum(d.get(k) or 0 for k, s, _, keys in ACCOUNTS if s == "l" and keys)
        d["eq"], d["_assets"], d["_liab"] = eq, assets, liab
    return o, c, tags


def _flow(kind, key, p, capq, bridge):
    if kind == "p":
        return p.get(key)
    if kind == "bridge":
        return bridge.get(key)
    if kind == "cap":
        return (capq or {}).get("items", {}).get(key)
    if kind == "sec":
        return (capq or {}).get(key)
    return None


def _period(fx, ev, p, capq, start, end, label, kind, flows_of=None):
    o, c, tags_c = balances(fx, ev, start, end)
    if not o or not c:
        return None
    bridge = {k: v for k, v, *_ in (p.get("bridge") or {}).get("items") or []} if p else {}
    accounts, unexplained = [], 0.0
    for k, side, name, keys in ACCOUNTS:
        oo, cc = o.get(k), c.get(k)
        if oo is None and cc is None:
            continue
        oo, cc = oo or 0, cc or 0
        fl = []
        for fk, key, sign, lab in FLOWS.get(k, []):
            v = flows_of(fk, key) if flows_of else _flow(fk, key, p, capq, bridge)
            if v is not None and abs(v) >= 0.5:
                fl.append([key, lab, sign * v])
        explained = sum(x[2] for x in fl)
        delta = cc - oo
        accounts.append({"k": k, "side": side, "name": name, "open": oo, "close": cc, "delta": delta, "flows": fl, "explained": explained,
                         "residual": delta - explained, "tags": sorted(set(tags_c.get(k, []))), **({"note": NOTES[k]} if k in NOTES else {})})
        unexplained += abs(delta - explained)
    moved = sum(abs(a["delta"]) for a in accounts) or 1
    # the identity the two balance sheets obey, and the share of the movement the statements explain
    return {"kind": kind, "start": start, "end": end, "label": label, "accounts": accounts,
            "totals": {"assets_open": o["_assets"], "assets_close": c["_assets"], "liab_open": o["_liab"], "liab_close": c["_liab"], "eq_open": o["eq"], "eq_close": c["eq"]},
            "identity_gap": (c["_assets"] - c["_liab"] - c["eq"]), "explained_share": round(1 - unexplained / moved, 3) if moved else None,
            "data_kind": "observed" if kind == "q" else "derived"}


def compute(fx, ev, q, cap):
    """{"v", "q": [...], "y": [...]} or None. q: the quality section's quarters (fsa periods); cap: capital.compute output."""
    capq = {x["end"]: x for x in (cap or {}).get("q") or []}
    qs = [p for p in (q or []) if p.get("start") and p.get("end")][-KEEP_Q:]
    out_q = []
    for p in qs:
        r = _period(fx, ev, p, capq.get(p["end"]), p["start"], p["end"], p.get("label"), "q")
        if r:
            out_q.append(r)
    out_y = []
    ends = [p["end"] for p in qs]
    for i in range(len(qs) - 1, 2, -1):                        # the last KEEP_Y quarter ends with four quarters behind them
        if len(out_y) >= KEEP_Y:
            break
        four = qs[i - 3:i + 1]
        if any(F.d(b["end"]) - F.d(a["end"]) > F.dt.timedelta(days=100) for a, b in zip(four, four[1:])):
            continue
        start = four[0]["start"]
        if not start or (F.d(four[-1]["end"]) - F.d(start)).days < 350:
            continue
        def summed(fk, key, four=four):
            vals = []
            for p in four:
                br = {k: v for k, v, *_ in (p.get("bridge") or {}).get("items") or []}
                vals.append(_flow(fk, key, p, capq.get(p["end"]), br))
            if all(v is None for v in vals):
                return None
            if any(v is None for v in vals):                   # a quarter without the line: the sum would be short
                return None
            return sum(vals)
        r = _period(fx, ev, four[-1], None, start, four[-1]["end"], f"{four[-1].get('label')} vs a year earlier", "y", flows_of=summed)
        if r:
            r["quarters"] = [p.get("label") for p in four]
            out_y.append(r)
    out_y.reverse()
    if not out_q and not out_y:
        return None
    return {"v": VERSION, "q": out_q, "y": out_y}
