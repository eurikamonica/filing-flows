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
  then the notes (NOTE_FLOWS: other comprehensive income, goodwill and intangibles recognised in acquisitions, the
  amortisation of intangibles inside D&A, lease assets and liabilities obtained without cash, unrealised gains in OCI)
  explain part of what the statements' lines leave; everything still unexplained is the account's residual (currency,
  reclassification, fair value, acquired working capital): shown as a bar of its own, never spread over the others

The balances come from the same standard tags as the reformulated balance sheet (reform.LINES), read at each
quarter end; the quarter's flows are the ones already on the page (fsa: the net income → OCF bridge; capital: the
cash-flow sections by quarter). "y" entries compare a quarter end with the same quarter end a year earlier and add
the four quarters' flows (data_kind derived); "q" entries are one quarter (flows from three-month facts or year-to-date
differences, as the bridge reads them). Each account carries its tags; the page draws the figures and nothing else.
"""
from . import facts as F
from . import fsa as W
from . import reform as R

VERSION = 2                     # 2: the notes' facts (OCI, goodwill acquired, lease additions, amortisation of intangibles)
KEEP_Q, KEEP_Y = 6, 3
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

# the notes: duration facts tagged outside the three statements that explain what the statements' lines leave
# (key, label, sign on the balance, concepts); `replaces` names a statement flow the note supersedes (the cash paid
# for acquisitions is a proxy for goodwill until the notes give the goodwill actually recognised)
NOTE_FLOWS = {
    "eq": [("oci", "Other comprehensive income", +1, ["OtherComprehensiveIncomeLossNetOfTax", "OtherComprehensiveIncomeLossNetOfTaxPortionAttributableToParent"], None),
           ("stock_acq", "Shares issued for acquisitions", +1, ["StockIssuedDuringPeriodValueAcquisitions"], None)],
    "gw": [("gw_acq", "Goodwill recognised in acquisitions", +1, ["GoodwillAcquiredDuringPeriod"], "acq"),
           ("int_acq", "Intangibles acquired", +1, ["FiniteLivedIntangibleAssetsAcquired"], None),
           ("amort_int", "Amortisation of intangibles", -1, ["AmortizationOfIntangibleAssets"], None),
           ("gw_fx", "Goodwill currency translation", +1, ["GoodwillForeignCurrencyTranslationGainLoss", "GoodwillTranslationAdjustments"], None)],
    "ppe": [("amort_int", "Amortisation of intangibles, inside D&A", +1, ["AmortizationOfIntangibleAssets"], None),
            ("rou_add", "Lease assets obtained for lease liabilities", +1, ["RightOfUseAssetObtainedInExchangeForOperatingLeaseLiability"], None),
            ("frou_add", "Finance-lease assets obtained", +1, ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"], None)],
    "debt": [("rou_add", "Lease liabilities obtained (non-cash)", +1, ["RightOfUseAssetObtainedInExchangeForOperatingLeaseLiability"], None),
             ("frou_add", "Finance-lease liabilities obtained (non-cash)", +1, ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"], None)],
    "inv_sec": [("oci_afs", "Unrealised gains on securities (in OCI)", +1, ["OtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax",
                                                                               "OtherComprehensiveIncomeUnrealizedHoldingGainLossOnSecuritiesArisingDuringPeriodNetOfTax"], None)],
}

# the detailed set: every balance-sheet line the reformulated balance sheet reads, with the flows that map to it;
# what cannot be split (investments, debt) stays merged. parent: the merged account the line belongs to.
DETAIL_ACCOUNTS = [
    ("cash", "a", "Cash and equivalents", ["cash"], "cash"),
    ("inv_sec", "a", "Investments and securities", ["sti", "lti", "secs", "eqsec", "eqm", "loans", "resale"], "inv_sec"),
    ("ar", "a", "Trade receivables", ["ar"], "ar"),
    ("orec", "a", "Other receivables", ["orec"], "ar"),
    ("inv", "a", "Inventory", ["inv"], "inv"),
    ("oca", "a", "Prepaid and other current assets", ["oca"], "oth_a"),
    ("ppe", "a", "Property, plant and equipment", ["ppe", "invprop"], "ppe"),
    ("rou", "a", "Lease right-of-use assets", ["rou"], "ppe"),
    ("gw", "a", "Goodwill", ["gw"], "gw"),
    ("intang", "a", "Intangible assets", ["intang"], "gw"),
    ("dta", "a", "Deferred tax assets", ["dta"], "oth_a"),
    ("onca", "a", "Other non-current assets", ["onca"], "oth_a"),
    ("oth_a", "a", "Other assets (untagged)", [], "oth_a"),
    ("deposits", "l", "Deposits and repos", ["deposits", "repo"], "oth_l"),
    ("ap", "l", "Payables", ["ap"], "ap"),
    ("accr", "l", "Accrued liabilities", ["accr"], "oth_l"),
    ("comp", "l", "Accrued compensation", ["comp"], "oth_l"),
    ("defrev", "l", "Deferred revenue", ["defrev", "defrevn"], "oth_l"),
    ("taxp", "l", "Income taxes payable", ["taxp", "taxpn"], "oth_l"),
    ("ocl", "l", "Other current liabilities", ["ocl"], "oth_l"),
    ("debt", "l", "Debt", ["std", "ltdc", "ltd"], "debt"),
    ("leases", "l", "Lease liabilities", ["flease", "olease", "lease"], "debt"),
    ("dtl", "l", "Deferred tax liabilities", ["dtl"], "oth_l"),
    ("pension", "l", "Pensions and provisions", ["pension", "prov"], "oth_l"),
    ("oncl", "l", "Other non-current liabilities", ["oncl"], "oth_l"),
    ("oth_l", "l", "Other liabilities (untagged)", [], "oth_l"),
    ("eq", "e", "Equity", [], "eq"),
]
DETAIL_FLOWS = {
    "cash": FLOWS["cash"], "inv_sec": FLOWS["inv_sec"], "inv": FLOWS["inv"], "ap": FLOWS["ap"], "eq": FLOWS["eq"],
    "ar": [("bridge", "d_ar", -1, "Change in receivables (cash flow statement)"), ("bridge", "d_casset", -1, "Change in contract assets")],
    "orec": [("bridge", "d_orec", -1, "Change in other receivables")],
    "oca": [("bridge", "d_oassets", -1, "Change in prepaid and other assets")],
    "ppe": [("cap", "capex", -1, "Capital expenditure"), ("cap", "realestate", -1, "Real estate bought"), ("bridge", "da", -1, "Depreciation and amortisation")],
    "gw": [("cap", "acq", -1, "Acquisitions, net of cash"), ("bridge", "impair", -1, "Impairments")],
    "dta": [("bridge", "dtax", -1, "Deferred taxes")],
    "accr": [("bridge", "d_accr", +1, "Change in accrued liabilities")], "comp": [("bridge", "d_emp", +1, "Change in employee liabilities")],
    "defrev": [("bridge", "d_contract", +1, "Change in deferred revenue")], "taxp": [("bridge", "d_tax", +1, "Change in income taxes payable")],
    "ocl": [("bridge", "d_oliab", +1, "Change in other liabilities"), ("bridge", "d_onet", +1, "Other operating capital")],
    "debt": [("cap", "borrow", +1, "Net borrowing (issued − repaid)")],
}
DETAIL_NOTES = {
    "eq": NOTE_FLOWS["eq"], "inv_sec": NOTE_FLOWS["inv_sec"],
    "gw": [("gw_acq", "Goodwill recognised in acquisitions", +1, ["GoodwillAcquiredDuringPeriod"], "acq"), ("gw_fx", "Goodwill currency translation", +1, ["GoodwillForeignCurrencyTranslationGainLoss", "GoodwillTranslationAdjustments"], None)],
    "intang": [("int_acq", "Intangibles acquired", +1, ["FiniteLivedIntangibleAssetsAcquired"], None), ("amort_int", "Amortisation of intangibles", -1, ["AmortizationOfIntangibleAssets"], None)],
    "ppe": [("amort_int", "Amortisation of intangibles, inside D&A", +1, ["AmortizationOfIntangibleAssets"], None), ("frou_add", "Finance-lease assets obtained", +1, ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"], None)],
    "rou": [("rou_add", "Lease assets obtained for lease liabilities", +1, ["RightOfUseAssetObtainedInExchangeForOperatingLeaseLiability"], None)],
    "leases": [("rou_add", "Lease liabilities obtained (non-cash)", +1, ["RightOfUseAssetObtainedInExchangeForOperatingLeaseLiability"], None), ("frou_add", "Finance-lease liabilities obtained (non-cash)", +1, ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"], None)],
}

NOTE_ONLY_IF = {"debt": lambda tags: any("Lease" in t for t in tags)}      # lease liabilities count only when the debt account holds them

NOTES = {"ppe": "Depreciation and amortisation includes the amortisation of intangibles where the filing reports one line: the PP&E residual then carries the intangibles' share.",
         "gw": "Acquisitions add goodwill and intangibles at their allocated values, not at the cash paid; the residual is the difference and the amortisation.",
         "inv_sec": "Securities bought and sold sit in 'other investing' with everything else the section does not name.",
         "eq": "Other comprehensive income (currency translation, unrealised gains) moves equity without passing through net income: it is in the residual.",
         "cash": "The cash flow statement's cash can include restricted cash the balance sheet shows elsewhere: a small residual is that difference."}

CF_LABELS = {"capex": "Capital expenditure", "realestate": "Real estate bought", "acq": "Acquisitions", "sales": "Asset and business sales", "inv_other": "Other investing (securities, net)",
             "buyback": "Share buybacks", "div": "Dividends", "withhold": "Shares withheld for taxes", "stock": "Shares issued", "borrow": "Net borrowing", "nci": "Minority-interest flows",
             "fin_other": "Other financing", "fx": "Currency effect on cash"}
INV_KEYS = ("capex", "realestate", "acq", "sales", "inv_other")
FIN_KEYS = ("buyback", "div", "withhold", "stock", "borrow", "nci", "fin_other")


def cash_flow(get):
    """the period's cash flow statement as the detailed card draws it: net income, the non-cash and working-capital
    items, OCF, the investing and financing lines, the currency effect, the change in cash; every figure a cash effect,
    with the unexplained part of each section as its own line. get(kind, key) -> value or None."""
    ni, ocf = get("p", "ni"), get("p", "ocf")
    if ni is None or ocf is None:
        return None
    nc = [[k, lab, get("bridge", k)] for k, lab, *_ in W.NONCASH]
    wc = [[k, lab, get("bridge", k)] for k, lab, *_ in W.WC]
    nc = [x for x in nc if x[2] is not None and abs(x[2]) >= 0.5]
    wc = [x for x in wc if x[2] is not None and abs(x[2]) >= 0.5]
    op_other = ocf - ni - sum(x[2] for x in nc + wc)
    inv = [[k, CF_LABELS[k], get("cap", k)] for k in INV_KEYS]
    fin = [[k, CF_LABELS[k], get("cap", k)] for k in FIN_KEYS]
    inv = [x for x in inv if x[2] is not None and abs(x[2]) >= 0.5]
    fin = [x for x in fin if x[2] is not None and abs(x[2]) >= 0.5]
    inv_t, fin_t, fx = get("sec", "inv"), get("sec", "fin"), get("cap", "fx")
    return {"ni": ni, "noncash": nc, "wc": wc, "op_other": op_other, "ocf": ocf,
            "inv": inv, "inv_total": inv_t, "inv_other_gap": (inv_t - sum(x[2] for x in inv)) if inv_t is not None else None,
            "fin": fin, "fin_total": fin_t, "fin_other_gap": (fin_t - sum(x[2] for x in fin)) if fin_t is not None else None,
            "fx": fx, "dcash": (ocf + (inv_t or 0) + (fin_t or 0) + (fx or 0)) if inv_t is not None and fin_t is not None else None}


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


def balances(fx, ev, start, end, accounts=None):
    """({account: open}, {account: close}, {account: tags}) with the plugs (other assets, other liabilities) from the
    totals at each date; (None, None, {}) without total assets, liabilities and equity at both dates"""
    accounts = accounts or ACCOUNTS
    ta = [_totals(fx, ev, d) for d in (start, end)]
    if any(v is None for t in ta for v in t):
        return None, None, {}
    o, c, tags = {}, {}, {}
    for row in accounts:
        k, side, _, keys = row[:4]
        if keys:
            o[k], c[k], tags[k] = _bal2(fx, ev, keys, start, end)
    for d, (assets, liab, eq) in zip((o, c), ta):
        d["oth_a"] = assets - sum(d.get(r[0]) or 0 for r in accounts if r[1] == "a" and r[3])
        d["oth_l"] = liab - sum(d.get(r[0]) or 0 for r in accounts if r[1] == "l" and r[3])
        d["eq"], d["_assets"], d["_liab"] = eq, assets, liab
    # a negative plug means two tagged lines overlap (one includes the other, as "other non-current assets" can include
    # deferred tax assets): the overlap is taken out of the largest "other" line of that side at both dates, so no
    # account is drawn below zero and the totals still match the filing
    for side, plug in (("a", "oth_a"), ("l", "oth_l")):
        if min(o[plug], c[plug]) < 0:
            pref = [r[0] for r in accounts if r[1] == side and r[3] and r[0] in ("onca", "oca", "oncl", "ocl", "inv_sec")]
            rest = sorted([r[0] for r in accounts if r[1] == side and r[3] and r[0] not in pref], key=lambda k: -((o.get(k) or 0) + (c.get(k) or 0)))
            host = next((k for k in pref + rest if (o.get(k) or 0) + min(0, o[plug]) >= 0 and (c.get(k) or 0) + min(0, c[plug]) >= 0), None)
            if host:
                for d in (o, c):
                    if d[plug] < 0:
                        d[host] = (d[host] or 0) + d[plug]
                        d[plug] = 0
                tags.setdefault(host, []).append("net of an overlap with the total")
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
    if kind == "note":
        return None
    return None


def _note(fx, ev, concepts, end):
    v, _, _ = W.first(fx, ev, concepts, end, False)
    return v


def _accounts(fx, ev, start, end, defs, flows, notes_map, get, note_get):
    """the account rows of one period for one account definition (the merged set, or the detailed one)"""
    o, c, tags_c = balances(fx, ev, start, end, defs)
    if not o or not c:
        return None, None, None
    accounts, unexplained = [], 0.0
    for row in defs:
        k, side, name, keys = row[:4]
        oo, cc = o.get(k), c.get(k)
        if oo is None and cc is None:
            continue
        if not keys and k not in ("oth_a", "oth_l", "eq") and not oo and not cc:
            continue
        oo, cc = oo or 0, cc or 0
        if keys and oo == 0 and cc == 0:
            continue
        fl = []
        for fk, key, sign, lab in flows.get(k, []):
            v = get(fk, key)
            if v is not None and abs(v) >= 0.5:
                fl.append([key, lab, sign * v])
        notes = []
        if k in notes_map and (k not in NOTE_ONLY_IF or NOTE_ONLY_IF[k](tags_c.get(k, []))):
            for nk, lab, sign, concepts, replaces in notes_map[k]:
                v = note_get(concepts)
                if v is None or abs(v) < 0.5:
                    continue
                notes.append([nk, lab, sign * v])
                if replaces:
                    fl = [x for x in fl if x[0] != replaces]
        explained = sum(x[2] for x in fl)
        from_notes = sum(x[2] for x in notes)
        delta = cc - oo
        rnd = lambda v: int(round(v))
        accounts.append({"k": k, "side": side, "name": name, "open": rnd(oo), "close": rnd(cc), "delta": rnd(delta), "flows": [[a, "", rnd(v)] for a, b, v in fl], "explained": rnd(explained),
                         "notes": [[a, "", rnd(v)] for a, b, v in notes], "from_notes": rnd(from_notes), "residual": rnd(delta - explained - from_notes),
                         **({"tags": sorted(set(tags_c.get(k, [])))} if defs is ACCOUNTS else {}), **({"parent": row[4]} if len(row) > 4 else {}), **({"note": NOTES[k]} if k in NOTES and defs is ACCOUNTS else {})})
        unexplained += abs(delta - explained - from_notes)
    return accounts, (o, c), unexplained


def _period(fx, ev, p, capq, start, end, label, kind, flows_of=None, note_of=None):
    bridge = {k: v for k, v, *_ in (p.get("bridge") or {}).get("items") or []} if p else {}
    get = (lambda fk, key: flows_of(fk, key)) if flows_of else (lambda fk, key: _flow(fk, key, p, capq, bridge))
    note_get = note_of if note_of else (lambda concepts: _note(fx, ev, concepts, end))
    accounts, oc, unexplained = _accounts(fx, ev, start, end, ACCOUNTS, FLOWS, NOTE_FLOWS, get, note_get)
    if not accounts:
        return None
    o, c = oc
    detail, _, _ = _accounts(fx, ev, start, end, DETAIL_ACCOUNTS, DETAIL_FLOWS, DETAIL_NOTES, get, note_get)
    cf = cash_flow(get)
    moved = sum(abs(a["delta"]) for a in accounts) or 1
    # the identity the two balance sheets obey, and the share of the movement the statements explain
    return {"kind": kind, "start": start, "end": end, "label": label, "accounts": accounts, "detail": detail or [],
            "totals": {"assets_open": o["_assets"], "assets_close": c["_assets"], "liab_open": o["_liab"], "liab_close": c["_liab"], "eq_open": o["eq"], "eq_close": c["eq"]},
            "identity_gap": (c["_assets"] - c["_liab"] - c["eq"]), "explained_share": round(1 - unexplained / moved, 3) if moved else None,
            "data_kind": "observed" if kind == "q" else "derived", **({"cf": cf} if cf else {})}


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
        def notes_summed(concepts, four=four):
            vals = [_note(fx, ev, concepts, p["end"]) for p in four]
            return None if any(v is None for v in vals) else sum(vals)
        r = _period(fx, ev, four[-1], None, start, four[-1]["end"], f"{four[-1].get('label')} vs a year earlier", "y", flows_of=summed, note_of=notes_summed)
        if r:
            r["quarters"] = [p.get("label") for p in four]
            out_y.append(r)
    out_y.reverse()
    if not out_q and not out_y:
        return None
    return {"v": VERSION, "labels": labels(), "q": out_q, "y": out_y}


def labels():
    """flow and note key -> label, once per company instead of once per account and period"""
    out = {}
    for m in (FLOWS, DETAIL_FLOWS):
        for rows in m.values():
            for _, key, _, lab in rows:
                out.setdefault(key, lab)
    for m in (NOTE_FLOWS, DETAIL_NOTES):
        for rows in m.values():
            for key, lab, *_ in rows:
                out.setdefault(key, lab)
    return out
