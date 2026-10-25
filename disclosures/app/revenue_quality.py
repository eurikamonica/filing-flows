"""SEC-sourced Cookie Jar Revenue *risk screening* beyond reserve accounts.

No fraud conclusion and no allegation. Uses issuer's own US-GAAP annual tagged
facts and keyword leads from its latest primary filing. Missing != zero.
Does not affect GAAP revenue, profitability, enterprise value or debt.
"""
import datetime as dt
import math
import re

FORMS = {"10-K", "10-K/A", "20-F", "40-F"}
TAGS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"),
    "receivables": ("AccountsReceivableNetCurrent", "AccountsNotesAndOtherReceivablesNetCurrent"),
    "contract_assets": ("ContractWithCustomerAssetCurrent", "ContractWithCustomerAssetNetCurrent"),
    "contract_liabilities": ("ContractWithCustomerLiabilityCurrent", "ContractWithCustomerLiability"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
}
LEADS = (
    ("bill_and_hold", "Bill-and-hold arrangements", r"\bbill[- ]and[- ]hold\b"),
    ("consignment", "Consignment / distributor sell-through", r"\bconsignment sales?\b|\bdistributor sell[- ]through\b"),
    ("contract_assets", "Unbilled revenue / contract assets", r"\bunbilled receivables?\b|\bcontract assets?\b"),
    ("variable_consideration", "Variable consideration / rebates / returns",
     r"\bvariable consideration\b|\bsales returns? and allowances\b|\bcustomer rebates?\b"),
    ("customer_acceptance", "Customer acceptance terms", r"\bcustomer acceptance (?:provisions?|criteria|terms)\b"),
    ("channel_inventory", "Channel inventory / incentives", r"\bchannel inventory\b|\bchannel incentives?\b"),
    ("related_party_sales", "Related-party revenue", r"\b(?:related.party|related parties) (?:revenue|sales|transactions)\b"),
    ("contract_modification", "Contract modifications", r"\bcontract modifications?\b"),
    ("revenue_recognition_change", "Revenue recognition policy change",
     r"\bchange(?:s|d)? in (?:our |the )?revenue recognition (?:policy|method)\b"),
    ("significant_financing", "Significant financing component", r"\bsignificant financing component\b"),
    ("receivable_sales", "Receivables sales / factoring",
     r"\b(?:sale|sales|factoring|securitization) of (?:accounts )?receivables\b"),
    ("deferred_revenue", "Deferred revenue / contract liabilities",
     r"\bdeferred revenue\b|\bcontract liabilit(?:y|ies)\b"),
)


def _pick(nodes, concepts, end, duration=False):
    options = []
    for priority, tag in enumerate(concepts):
        for row in ((nodes.get(tag) or {}).get("units") or {}).get("USD") or []:
            if (row.get("end") != end or row.get("form") not in FORMS
                    or not row.get("accn") or not row.get("filed")):
                continue
            val = row.get("val")
            if isinstance(val, bool) or not isinstance(val, (float, int)) or not math.isfinite(val):
                continue
            if duration:
                try:
                    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(row.get("start", ""))).days
                except (ValueError, TypeError):
                    continue
                if not 300 <= days <= 380:
                    continue
            elif row.get("start"):
                continue
            options.append((-priority, row["filed"], row["accn"], tag, float(val), row))
    if not options:
        return None
    _priority, _filed, _acc, tag, val, row = max(options)
    return {"value_usd": val, "tag": "us-gaap:" + tag,
            "accession": row["accn"], "filed": row["filed"],
            "end": end, "form": row["form"]}


def _annual_ends(nodes, as_of):
    ends = set()
    for tag in TAGS["revenue"]:
        for r in ((nodes.get(tag) or {}).get("units") or {}).get("USD") or []:
            if r.get("form") not in FORMS or not r.get("end") or r["end"] > as_of:
                continue
            try:
                days = (dt.date.fromisoformat(r["end"]) -
                        dt.date.fromisoformat(r.get("start", ""))).days
            except (ValueError, TypeError):
                continue
            if 300 <= days <= 380:
                ends.add(r["end"])
    return sorted(ends, reverse=True)


def _ratio(a, b):
    if a is None or b is None or b <= 0:
        return None
    return round(a / b, 4)


def extract(cf, cik, as_of):
    """Two consecutive comparably dated annual observations or UNKNOWN."""
    from hidden_leverage import sec_url
    out = {"status": "missing_annual_comparison", "as_of": as_of,
           "metrics": {}, "risk_flags": [], "evidence": {},
           "text_leads": [], "method": "US-GAAP annual same-period SEC filing facts"}
    if not as_of or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(as_of)):
        return out
    nodes = ((cf or {}).get("facts") or {}).get("us-gaap") or {}
    years = _annual_ends(nodes, as_of)
    if len(years) < 2:
        return out
    current = years[0]
    previous = next((x for x in years[1:]
                     if 300 <= (dt.date.fromisoformat(current) -
                                dt.date.fromisoformat(x)).days <= 430), None)
    if not previous:
        return out
    obs = {}
    for field, tags in TAGS.items():
        is_duration = field in {"revenue", "operating_cash_flow", "net_income"}
        obs[field] = (_pick(nodes, tags, current, is_duration),
                      _pick(nodes, tags, previous, is_duration))
    def val(field, i=0):
        x = obs[field][i]
        return x["value_usd"] if x else None
    def growth(field):
        a, b = val(field), val(field, 1)
        return None if a is None or b is None or b <= 0 else round(a / b - 1, 4)

    rev, rev_prev = val("revenue"), val("revenue", 1)
    ar, ar_prev = val("receivables"), val("receivables", 1)
    # Always require positive revenue and receivables for DSRI.
    dsri = (_ratio(_ratio(ar, rev), _ratio(ar_prev, rev_prev))
            if all(v is not None and v > 0 for v in (rev, rev_prev, ar, ar_prev)) else None)
    ocf_to_ni = (_ratio(val("operating_cash_flow"), val("net_income"))
                 if val("net_income") is not None and val("net_income") > 0 else None)
    metrics = {
        "revenue_growth": growth("revenue"),
        "receivables_growth": growth("receivables"),
        "contract_assets_growth": growth("contract_assets"),
        "contract_liabilities_growth": growth("contract_liabilities"),
        "dsri": dsri,
        "ocf_to_net_income": ocf_to_ni,
    }
    flags = []
    if dsri is not None and dsri > 1.25:
        flags.append({"key": "dsri", "label": "Receivables are rising faster than sales",
                      "value": dsri, "rule": "DSRI > 1.25 (screening heuristic)"})
    g_ca, g_rev = metrics["contract_assets_growth"], metrics["revenue_growth"]
    if g_ca is not None and g_rev is not None and g_ca - g_rev > 0.30 and g_ca > 0:
        flags.append({"key": "unbilled_growth",
                      "label": "Contract assets grow materially faster than revenue",
                      "value": round(g_ca - g_rev, 4),
                      "rule": "Contract asset growth - revenue growth > 30pp"})
    g_cl = metrics["contract_liabilities_growth"]
    if g_cl is not None and g_rev is not None and g_cl < -0.20 and g_rev > 0.10:
        flags.append({"key": "deferred_release",
                      "label": "Contract liabilities decline while revenue increases",
                      "value": g_cl,
                      "rule": "Contract liabilities < -20% and revenue growth > 10%"})
    if ocf_to_ni is not None and ocf_to_ni < 0.6:
        flags.append({"key": "cash_conversion",
                      "label": "Operating cash flow below reported net income",
                      "value": ocf_to_ni,
                      "rule": "OCF / positive net income < 0.60 (not revenue-specific)"})
    out.update({"status": "screened" if rev is not None and rev_prev is not None else "incomplete",
                "periods": [current, previous], "metrics": metrics,
                "risk_flags": flags,
                "evidence": {name: [
                    ({**x, "source_url": sec_url(cik, x["accession"])} if x else None)
                    for x in values] for name, values in obs.items()},
                "warning": "Signals are diagnostic prompts, not findings of manipulation. "
                           "Sector, acquisitions, factoring and recognition policy may explain changes. "
                           "Financial firms need industry-specific interpretation."})
    return out


def scan_text(raw, cik, accession, document, form, filed):
    """Flag possible recognition mechanics, including those outside reserves."""
    from hidden_leverage import sec_url
    from debt_docs import to_text
    if not raw or not accession:
        return []
    body = to_text(raw[:4_000_000])
    url = sec_url(cik, accession, document)
    result = []
    for key, label, pattern in LEADS:
        hit = re.search(pattern, body, re.I)
        if hit:
            result.append({
                "key": key, "label": label,
                "excerpt": " ".join(body[max(0, hit.start()-110):hit.end()+150].split())[:300],
                "classification": "unverified_text_lead", "source_url": url,
                "accession": accession, "form": form, "filed": filed
            })
    return result
