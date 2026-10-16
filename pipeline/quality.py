"""Earnings quality from SEC XBRL company facts: profit against operating cash flow, cash-flow accruals, and reserve
rollforwards (product warranty, credit losses on receivables and loans, restructuring), behind the company page's
"Profit and cash" section.

Adapted from the Cash & Cookie Visual Lab prototype on the beta/fsa-chatgpt branch (created by ChatGPT (OpenAI)): the same
definitions, fed with each company's own filings instead of a fictional example.

  accruals        = net income − operating cash flow, same period and same scope: ProfitLoss (which, like operating cash
                    flow, includes noncontrolling interests) when tagged, else NetIncomeLoss
  accrual ratio   = accruals ÷ average total assets (opening and closing balance); for the period, not annualised
  reserve roll    = opening + additions − releases − utilization + other = calculated closing
  difference      = reported closing − calculated closing: movements the filer did not tag (or tagged somewhere else)

Reserve rollforwards come from 10-K notes, so they are fiscal-year figures. Tags vary between filers (Product… or
StandardProduct…, ProvisionForDoubtfulAccounts or AccountsReceivableCreditLossExpenseReversal, …): every combination of
the candidate tags is tried and the one whose movements best explain the change in the balance is kept. A rollforward
whose untagged difference is over 25% of the balance is left out rather than drawn wrong.

    python -m pipeline.quality 320193        # print one company's figures (fetches its company facts from SEC)
"""
import itertools
import sys

from . import capital as K
from . import facts as F
from . import fsa as W
from . import history as H

VERSION = 4               # 2: working capital, the net income → OCF bridge, valuation inputs, evidence (pipeline/fsa.py)
                          # 3: capital allocation, share count and debt maturities (pipeline/capital.py)
                          # 4: every version of the headline figures, "As Known Then" (pipeline/history.py)
MAX_DIFF = 0.25            # untagged movement allowed, as a share of the larger of the opening and closing balance
TOLERANCE = 0.005          # under this share of the balance the rollforward counts as reconciled (rounding)
KEEP_Q, KEEP_FY = 8, 5

# role -> candidate tags, best first. "add" and "use" are magnitudes; "est", "net" and "other" are signed.
#   est   change in estimate for earlier periods: + adds to the reserve, − is a release back to profit
#   net   the period's whole charge when it is not split (a provision for credit losses): + additions, − release
#   other groups are added up, one tag per group (currency translation, acquisitions, recoveries)
FAMILIES = [
    {"id": "warranty", "name": "Product warranty reserve",
     "what": "accrued for expected repair and replacement costs of products already sold",
     "balance": ["ProductWarrantyAccrual", "StandardProductWarrantyAccrual"],
     "add": ["ProductWarrantyAccrualWarrantiesIssued", "StandardProductWarrantyAccrualWarrantiesIssued"],
     "est": ["ProductWarrantyAccrualPreexistingIncreaseDecrease", "StandardProductWarrantyAccrualPreexistingIncreaseDecrease"],
     "net": ["ProductWarrantyAccrualPeriodIncreaseDecrease", "StandardProductWarrantyAccrualPeriodIncreaseDecrease",
             "ProductWarrantyExpense"],
     "use": [["ProductWarrantyAccrualPayments", "StandardProductWarrantyAccrualPayments"]],
     "other": [["ProductWarrantyAccrualCurrencyTranslationIncreaseDecrease",
                "StandardProductWarrantyAccrualCurrencyTranslationIncreaseDecrease",
                "StandardProductWarrantyAccrualForeignCurrencyTranslationGainLoss",
                "StandardAndExtendedProductWarrantyAccrualForeignCurrencyTranslationGainLoss"],
               ["ProductWarrantyAccrualAdditionsFromBusinessAcquisition",
                "StandardProductWarrantyAccrualAdditionsFromBusinessAcquisition"]]},
    {"id": "receivables", "name": "Allowance for doubtful accounts",
     "what": "set aside for customer invoices that may not be collected",
     "balance": ["AccountsReceivableAllowanceForCreditLoss", "AllowanceForDoubtfulAccountsReceivable",
                 "AccountsReceivableAllowanceForCreditLossCurrent", "AllowanceForDoubtfulAccountsReceivableCurrent"],
     "net": ["AccountsReceivableCreditLossExpenseReversal", "ProvisionForDoubtfulAccounts"],
     "use": [["AccountsReceivableAllowanceForCreditLossWriteoff", "AllowanceForDoubtfulAccountsReceivableWriteOffs"]],
     "other": [["AccountsReceivableAllowanceForCreditLossRecovery", "AllowanceForDoubtfulAccountsReceivableRecoveries"]]},
    {"id": "loans", "name": "Allowance for loan and lease losses",
     "what": "set aside for loans and finance receivables that may not be repaid",
     "balance": ["FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", "FinancingReceivableAllowanceForCreditLosses"],
     "net": ["FinancingReceivableExcludingAccruedInterestCreditLossExpenseReversal", "FinancingReceivableCreditLossExpenseReversal",
             "FinancingReceivableAllowanceForCreditLossesProvisions", "ProvisionForLoanAndLeaseLosses",
             "ProvisionForLoanLossesExpensed", "ProvisionForLoanLeaseAndOtherLosses"],
     # gross write-offs with recoveries added back, or write-offs already net of recoveries (then no recoveries line)
     "use": [["FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoff",
              "FinancingReceivableAllowanceForCreditLossWriteoff", "FinancingReceivableAllowanceForCreditLossesWriteOffs"],
             ["FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoffAfterRecovery",
              "FinancingReceivableAllowanceForCreditLossWriteoffAfterRecovery"]],
     "other": [["FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossRecovery",
                "FinancingReceivableAllowanceForCreditLossRecovery", "FinancingReceivableAllowanceForCreditLossesRecovery",
                "FinancingReceivableAllowanceForCreditLossesRecoveries"],
               ["FinancingReceivableAllowanceForCreditLossForeignCurrencyTranslation"]]},
    {"id": "restructuring", "name": "Restructuring reserve",
     "what": "accrued for severance, exit and other restructuring costs not yet paid",
     "balance": ["RestructuringReserve"],
     "add": ["RestructuringReservePeriodExpense", "RestructuringCharges"],
     "est": ["RestructuringReserveAccrualAdjustment1", "RestructuringReserveAccrualAdjustment"],
     "use": [["RestructuringReserveSettledWithCash", "PaymentsForRestructuring"],
             ["RestructuringReserveSettledWithoutCash2", "RestructuringReserveSettledWithoutCash1",
              "RestructuringReserveSettledWithoutCash"]],
     "other": [["RestructuringReserveTranslationAndOtherAdjustment", "RestructuringReserveTranslationAdjustment"]]},
]
# balances the facts index keeps as point-in-time values (see facts.index_facts)
INSTANTS = {"Assets"} | {t for f in FAMILIES for t in f["balance"]} | W.INSTANT_CONCEPTS | K.INSTANT_CONCEPTS
SHARES = W.SHARE_CONCEPTS | K.SHARE_CONCEPTS


def _instant(fx, concept, day):
    f = (fx.get("__instants__") or {}).get(concept, {}).get(day)
    return f["val"] if f else None


def _year(fx, concept, end):
    per = fx.get(concept)
    return F._year_from(per, end) if per else None


def _first(fx, tags, end):
    """(value, tag) of the first tag with a full-year figure for the year ending `end`."""
    for t in tags:
        v = _year(fx, t, end)
        if v is not None:
            return v, t
    return None, None


def _choices(fx, tags, end):
    """[(value, tag)] of every tag with a full-year figure (the candidates to try), or [(None, None)]."""
    out = [(v, t) for t in tags for v in [_year(fx, t, end)] if v is not None]
    return out or [(None, None)]


def rollforward(fx, fam, start, end):
    """One reserve's movement over the fiscal year (start = the prior year end, end = this year end), or None."""
    best = None
    for bal in fam["balance"]:
        opening, closing = _instant(fx, bal, start), _instant(fx, bal, end)
        if opening is None or closing is None:
            continue
        use_groups = [[(v, t) for v, t in [_first(fx, g, end)] if v is not None] for g in fam.get("use", [])]
        # a write-off net of recoveries (second "use" group of loans) replaces gross write-offs + recoveries
        gross, after = (use_groups + [[], []])[:2] if fam["id"] == "loans" else (None, None)
        for (a, ta), (e, te), (n, tn) in itertools.product(_choices(fx, fam.get("add", []), end),
                                                            _choices(fx, fam.get("est", []), end),
                                                            _choices(fx, fam.get("net", []), end)):
            tags = {}
            additions = releases = 0.0
            known = False
            if a is not None:
                additions += abs(a); tags["add"] = ta; known = True
            if e is not None:
                if e > 0:
                    additions += e
                else:
                    releases += -e
                tags["est"] = te; known = True
            if n is not None and a is None and e is None:
                if n >= 0:
                    additions += n
                else:
                    releases += -n
                tags["net"] = tn; known = True
            elif n is not None and a is not None and e is None and tn and "PeriodIncreaseDecrease" in tn:
                d = n - abs(a)                                 # issued + changes in estimate = the period's charge
                additions += d if d > 0 else 0
                releases += -d if d < 0 else 0
                tags["net"] = tn
            utilization, other = None, None
            if fam["id"] == "loans" and not gross and after:
                utilization = abs(after[0][0]); tags["use"] = [after[0][1]]
            else:
                for g in (use_groups[:1] if fam["id"] == "loans" else use_groups):
                    for v, t in g:
                        utilization = (utilization or 0) + abs(v)
                        tags.setdefault("use", []).append(t)
            for g in fam.get("other", []):
                if fam["id"] == "loans" and g is fam["other"][0] and not gross and after:
                    continue                                  # recoveries are inside the net write-off
                v, t = _first(fx, g, end)
                if v is not None:
                    v = abs(v) if "Recover" in t else v       # recoveries add back to the allowance
                    other = (other or 0) + v
                    tags.setdefault("other", []).append(t)
            if (not known and utilization is None) or (opening == 0 and closing == 0):
                continue
            calc = opening + additions - releases - (utilization or 0) + (other or 0)
            diff = closing - calc
            scale = max(abs(opening), abs(closing), 1.0)
            cand = {"id": fam["id"], "name": fam["name"], "what": fam["what"], "start": start, "end": end,
                    "opening": opening, "additions": additions if known else None, "releases": releases if known else None,
                    "utilization": utilization, "other": other, "closing": closing, "calc": calc, "diff": diff,
                    "reconciled": abs(diff) <= TOLERANCE * scale,
                    # a change in estimate or a negative provision goes back through profit; payments do not
                    "release_in_income": bool(releases) and ("est" in tags or "net" in tags),
                    "tags": {"balance": bal, **tags}}
            if best is None or abs(diff) < abs(best["diff"]):
                best = cand
    if best is None or abs(best["diff"]) > MAX_DIFF * max(abs(best["opening"]), abs(best["closing"]), 1.0):
        return None
    return best


def _near(ends, end, lo, hi):
    """The latest of `ends` lo..hi days before `end`."""
    e0 = F.d(end)
    xs = [e for e in ends if lo <= (e0 - F.d(e)).days <= hi]
    return max(xs) if xs else None


def _assets_at(fx, day, lo=0, hi=7):
    """Total assets on `day`, or the nearest balance up to a week earlier (a 52/53-week year can end a few days off)."""
    per = (fx.get("__instants__") or {}).get("Assets") or {}
    if day in per:
        return per[day]["val"]
    e0 = F.d(day)
    xs = [k for k in per if lo <= (e0 - F.d(k)).days <= hi]
    return per[max(xs)]["val"] if xs else None


def _period(fx, ev, end, prev, annual, fye, basis):
    profit, r_ni = W.keyed(fx, ev, basis, end, annual)
    ocf, r_ocf = W.keyed(fx, ev, "ocf", end, annual)
    if profit is None and ocf is None:
        return None
    label = F.fiscal_year_label(end, fye)[0] if annual else F.fiscal_label(end, fye)[0]
    a_o, r_ao, _ = W.balance(fx, ev, ["Assets"], prev) if prev else (None, None, None)
    a_c, r_ac, _ = W.balance(fx, ev, ["Assets"], end)
    wc, refs = W.working_capital(fx, ev, end, prev, annual)
    refs.update({k: r for k, r in (("ni", r_ni), ("ocf", r_ocf), ("assets_open", r_ao), ("assets_close", r_ac)) if r})
    br = W.bridge(fx, ev, end, annual)
    return {"end": end, "start": prev, "label": label, "ni": profit, "basis": basis, "ocf": ocf,
            "assets_open": a_o, "assets_close": a_c, "wc": wc, "bridge": br, "ev": refs}


def _fye_match(end, fye):
    """`end` falls within a week of the fiscal year-end date (MMDD) — not the trailing twelve months some 10-Qs tag
    (Amazon), nor any other 12-month span."""
    e = F.d(end)
    for y in (e.year - 1, e.year, e.year + 1):
        try:
            if abs((e - F.dt.date(y, int(fye[:2]), int(fye[2:]))).days) <= 7:
                return True
        except ValueError:                                    # 0229
            if abs((e - F.dt.date(y, int(fye[:2]), 28)).days) <= 8:
                return True
    return False


def _ends(fx, annual, fye="1231"):
    """Period ends with a net income figure (quarters directly or as year-to-date differences; fiscal years)."""
    keys = F.CONCEPTS["ni"] + F.CONCEPTS["pl"]
    ends = {e for c in keys for (s, e) in fx.get(c, {}) if F.d(e) >= F.d("2009-01-01")}
    ok = (lambda e: _fye_match(e, fye) and any(_year(fx, c, e) is not None for c in keys)) if annual else \
        (lambda e: any(fx.get(c) and F._quarter_from(fx[c], e) is not None for c in keys))
    return sorted(e for e in ends if ok(e))


def _basis(fx, ends, annual):
    """ProfitLoss (includes noncontrolling interests, the scope of operating cash flow) when every period has it,
    else NetIncomeLoss: one basis for the whole chart, so the bars compare like with like."""
    return "pl" if ends and all(F.value(fx, "pl", e, annual) is not None for e in ends) else "ni"


def compute(fx, fye="1231"):
    """The section's data for one company from its indexed company facts (facts.index_facts), or None if empty."""
    ev = W.Evidence(fx)
    qe = _ends(fx, False)
    assets = sorted((fx.get("__instants__") or {}).get("Assets") or {})
    q, basis = [], _basis(fx, qe[-KEEP_Q:], False)
    for e in qe[-KEEP_Q:]:
        p = _period(fx, ev, e, _near(qe, e, 75, 105) or _near(assets, e, 75, 105), False, fye, basis)
        if p:
            q.append(p)
    ye = _ends(fx, True, fye)
    y, reserves, basis = [], [], _basis(fx, ye[-KEEP_FY:], True)
    for e in ye[-KEEP_FY:]:
        prev = _near(ye, e, 350, 380) or _near(assets, e, 350, 380)
        p = _period(fx, ev, e, prev, True, fye, basis)
        if p:
            y.append(p)
        if prev:
            for fam in FAMILIES:
                r = rollforward(fx, fam, prev, e)
                if r:
                    r["label"] = F.fiscal_year_label(e, fye)[0]
                    reserves.append(r)
    if not (q or y):
        return None
    val = W.valuation_inputs(fx, ev, qe, ye)
    cap = K.compute(fx, ev, qe, ye, fye)
    hist = H.compute(fx, ev, fye)
    return W.compact({"v": VERSION, "unit": "USD", "q": q, "fy": y, "reserves": reserves, "val": val, "cap": cap,
                      "hist": hist, "src": ev.out()})


if __name__ == "__main__":
    from . import sec
    for cik in sys.argv[1:]:
        out = compute(F.index_facts(sec.get_json(sec.companyfacts_url(int(cik)))))
        import json
        print(json.dumps(out, indent=1)[:6000])
