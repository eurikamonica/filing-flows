"""SEC evidence for the Hidden Leverage & Contractual Obligations module.

This is a research view, not GAAP debt. Purchase commitments may be operating
costs; guarantees are contingent; lease payments may already have an associated
recognized liability. Never sum all categories, or add them to net debt.
Only accept USD facts at the reported balance date, with SEC accession evidence.
"""
import re
from urllib.parse import quote

# Each family is deliberately non-additive to every other family.
# Group names are analytical classifications, not accounting treatments.
FAMILIES = (
    ("purchase", "Unconditional purchase obligations", "operating_commitment",
     ("UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount",
      "UnconditionalPurchaseObligation"),
     ("UnrecordedUnconditionalPurchaseObligationBalanceOnFirstAnniversary",
      "UnrecordedUnconditionalPurchaseObligationBalanceOnSecondAnniversary",
      "UnrecordedUnconditionalPurchaseObligationBalanceOnThirdAnniversary",
      "UnrecordedUnconditionalPurchaseObligationBalanceOnFourthAnniversary",
      "UnrecordedUnconditionalPurchaseObligationBalanceOnFifthAnniversary",
      "UnrecordedUnconditionalPurchaseObligationDueAfterFiveYears")),
    ("purchase_broad", "Purchase obligations, gross (potential overlap)", "operating_commitment",
     ("PurchaseObligation",),
     ("PurchaseObligationDueInNextTwelveMonths",
      "PurchaseObligationDueInSecondYear",
      "PurchaseObligationDueInThirdYear",
      "PurchaseObligationDueInFourthYear",
      "PurchaseObligationDueInFifthYear",
      "PurchaseObligationDueAfterFifthYear")),
    ("guarantees", "Maximum potential guarantee payments", "contingent",
     ("GuaranteeObligationsMaximumPotentialAmountOfFuturePayments",
      "GuaranteesMaximumPotentialAmountOfFuturePayments"), ()),
    ("operating_lease", "Recognized operating lease liability (reference)", "recognized",
     ("OperatingLeaseLiability",), ()),
    ("lease_payments", "Undiscounted operating lease payments (reference)", "lease_payments",
     ("OperatingLeaseLiabilityPaymentsDue",),
     ("OperatingLeaseLiabilityPaymentsDueNextTwelveMonths",
      "OperatingLeaseLiabilityPaymentsDueYearTwo",
      "OperatingLeaseLiabilityPaymentsDueYearThree",
      "OperatingLeaseLiabilityPaymentsDueYearFour",
      "OperatingLeaseLiabilityPaymentsDueYearFive",
      "OperatingLeaseLiabilityPaymentsDueAfterYearFive")),
)
BUCKETS = ("Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Thereafter")
# Screening taxonomy: leads only, not automatic accounting treatment.
# A = investigate financing/debt-like recourse; B = fixed operating/capital
# commitments; C = contingent support. A/B/C candidates require contract review.
# STRUCTURES includes the 15 core types and nine further structures; distinct
# VIE/SPE and keepwell phrase patterns intentionally map to the same family.
STRUCTURES = (
    ("take_or_pay", "Take-or-pay contracts", "B", r"\btake[- ]or[- ]pay\b"),
    ("ppa", "Power purchase agreements", "B", r"\bpower purchase agreements?\b"),
    ("capacity", "Cloud / GPU capacity commitments", "B", r"\b(?:cloud|GPU|compute|data[\s-]cent(?:er|re)) (?:capacity|purchase|infrastructure) commitments?\b|\bGPU reservation agreements?\b"),
    ("vie", "SPE / SPV / VIE financing", "A/C", r"\bvariable interest entit(?:y|ies)\b|\bspecial[- ]purpose (?:entities|entity|vehicles?|structures?)\b"),
    ("supplier_finance", "Supplier finance / reverse factoring", "A", r"\bsupplier finance (?:arrangements?|programs?)\b|\breverse factoring\b|\bstructured payables\b"),
    ("securitization", "Receivables securitization", "A", r"\breceivables securiti[sz]ation\b|\baccounts receivable securiti[sz]ation\b"),
    ("guarantee_support", "Guarantees / keepwell support", "C", r"\b(?:parent|financial|debt|payment) guarantees?\b|\bkeepwell agreements?\b"),
    ("uncommenced_leases", "Uncommenced leases", "B", r"\bleases? (?:that have|which have)? ?not yet commenced\b|\b(?:uncommenced leases?|leases? (?:not|yet to be) commenced)\b"),
    ("sale_leaseback", "Sale-and-leaseback", "A/B", r"\bsale[- ]and[- ]leaseback\b|\bsale[- ]leaseback\b"),
    ("synthetic_lease", "Synthetic leases", "A", r"\bsynthetic leases?\b"),
    ("joint_venture", "Joint venture funding commitments", "B/C", r"\b(?:joint venture|JV) (?:funding|capital|contribution) commitments?\b"),
    ("construction_capex", "Construction / CapEx commitments", "B", r"\b(?:construction|capital expenditure|capital spending|capital investment|equipment purchase) commitments?\b"),
    ("residual_guarantee", "Residual value guarantees", "C", r"\bresidual value guarantees?\b"),
    ("royalty_revenue_financing", "Royalty / revenue-based financing", "A", r"\b(?:royalty[- ]based|revenue[- ]based) financ(?:ing|e)\b|\broyalty financing arrangements?\b"),
    ("redeemable_nci", "Put options / redeemable NCI", "C", r"\bredeemable noncontrolling interests?\b|\bput options? (?:held by|granted to) (?:the )?(?:noncontrolling|minority)\b"),
    ("repo_financing", "Repo / sale-and-repurchase", "A", r"\brepurchase agreements?\b|\bsale[- ]and[- ]repurchase\b"),
    ("customer_prepayments", "Customer prepayments", "B", r"\bcustomer (?:prepayments?|advance payments?|deposits)\b"),
    ("streaming", "Commodity streaming agreements", "A/B", r"\b(?:metal|silver|gold|commodity) streaming agreements?\b"),
    ("tax_equity", "Tax equity financing", "A/C", r"\btax equity (?:financing|investments?|partnerships?)\b"),
    ("pension_deficit", "Pension funding deficit", "B/C", r"\b(?:underfunded|unfunded) pension (?:obligations?|plans?|liabilit(?:y|ies))\b|\bpension funding deficits?\b"),
    ("asset_retirement", "Asset retirement obligations", "B/C", r"\basset retirement obligations?\b|\bdecommissioning (?:liabilit(?:y|ies)|obligations?)\b"),
    ("deferred_acquisition", "Deferred acquisition consideration", "A/C", r"\bdeferred (?:acquisition|purchase) consideration\b"),
    ("earnouts", "Contingent earn-outs", "C", r"\bearn[- ]outs?\b|\bcontingent (?:acquisition|purchase) consideration\b"),
    ("liquidity_backstop", "Liquidity backstops", "C", r"\bliquidity backstops?\b|\bliquidity support (?:facility|facilities|agreement)\b"),
)
TEXT_RULES = tuple((key, label, pattern) for key, label, _lane, pattern in STRUCTURES)
REVIEW_LANES = {key: lane for key, _label, lane, _pattern in STRUCTURES}


def public_taxonomy():
    """Machine-readable scope; a screening lane is not a verified debt decision."""
    return [{"key": key, "label": label, "review_lane": lane, "evidence_type": "text_lead",
             "status": "screening_only"} for key, label, lane, _pattern in STRUCTURES]

FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F"}


def sec_url(cik, accession, primary_document=None):
    """Link to the filed SEC document/directory, never a generic search result."""
    if not str(accession or "").replace("-", "").isdigit():
        return None
    base = "https://www.sec.gov/Archives/edgar/data/{}/{}/".format(
        int(cik), str(accession).replace("-", ""))
    if primary_document and re.fullmatch(r"[\w.+-]+", primary_document):
        return base + quote(primary_document)
    return base


def _fact(cf, concepts, date):
    """Select a non-dimensional USD instant at the EXACT same reporting date.

    A later amendment/restatement supersedes an earlier accession on this date.
    Avoid mixing disclosure years, dimension members, currencies or duration facts.
    """
    nodes = (cf.get("facts") or {}).get("us-gaap") or {}
    found = []
    for order, name in enumerate(concepts):
        node = nodes.get(name) or {}
        for r in (node.get("units") or {}).get("USD") or []:
            if (r.get("end") != date or r.get("start") or r.get("form") not in FORMS
                    or not r.get("accn") or not r.get("filed")
                    or not isinstance(r.get("val"), (int, float))
                    or isinstance(r.get("val"), bool) or r["val"] < 0):
                continue
            found.append((r["filed"], -order, r.get("accn"), name, float(r["val"]), r.get("form")))
    if not found:
        return None
    filed, _, acc, concept, amount, form = max(found)
    return {"value_usd": amount, "tag": "us-gaap:" + concept, "accession": acc,
            "filed": filed, "form": form, "as_of": date}


def extract(cf, cik, as_of, filed_documents=None):
    """Extract separately classified amounts. Missing != zero; never sum groups.

    Each disclosure has source accession, tag, filing date, reporting date and
    maturity buckets only if available at that same date.
    """
    data = {"as_of": as_of, "currency": "USD", "categories": [], "text_signals": [],
            "method": "SEC companyfacts XBRL; strict same-period USD instant facts",
            "warnings": ["Categories can overlap. Gross commitments are not debt.",
                         "Unreported and company-extension values may be missing.",
                         "Maturity buckets are contractual undiscounted dollars, not present value."]}
    if not as_of or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(as_of)):
        data["coverage"] = "no_valid_balance_date"
        return data
    documents = filed_documents or {}
    for ident, label, kind, total_tags, schedule_tags in FAMILIES:
        total = _fact(cf, total_tags, as_of)
        schedules = [_fact(cf, (tag,), as_of) for tag in schedule_tags]
        if total is None and not any(schedules):
            continue
        evidence = [total] if total else [f for f in schedules if f]
        basis = evidence[0]
        source_doc = documents.get(basis["accession"]) or ""
        out = {"key": ident, "label": label, "class": kind,
               "amount_usd": total["value_usd"] if total else None,
               "reported_total": total is not None,
               "schedule": [f["value_usd"] if f else None for f in schedules],
               "schedule_labels": list(BUCKETS[:len(schedule_tags)]),
               "source_url": sec_url(cik, basis["accession"], source_doc),
               "accession": basis["accession"], "form": basis["form"],
               "filed": basis["filed"], "as_of": as_of,
               "evidence": [dict(f, url=sec_url(cik, f["accession"], documents.get(f["accession"]))) for f in
                            ([total] if total else []) + [f for f in schedules if f]],
               "warning": "Do not add to recognized debt or other rows; categories may overlap."}
        data["categories"].append(out)
    data["coverage"] = ("numeric_evidence" if data["categories"] else "no_standard_tag_at_period")
    return data


def scan_filing_text(raw, cik, accession, document, form, filed, max_matches=24):
    """Text *leads*, NEVER numeric obligations or verified liabilities.

    Source text must be fetched from the exact recent 10-K or 10-Q. Suppress
    repeated matches; cap excerpt length, counts and scan cost.
    """
    if not raw or not accession:
        return []
    from debt_docs import to_text
    body = to_text(raw[:5_000_000] if isinstance(raw, bytes) else raw[:5_000_000])
    # Headings and table fragments are sometimes concatenated by HTML conversion.
    url = sec_url(cik, accession, document)
    result = []
    for key, label, regex in TEXT_RULES:
        m = re.search(regex, body, re.I)
        if not m:
            continue
        context = " ".join(body[max(0, m.start()-105):m.end()+150].split())[:300]
        result.append({"key": key, "label": label, "excerpt": context,
                       "source_url": url, "accession": accession,
                       "form": form, "filed": filed, "classification": "unverified_text_lead",
                       "review_lane": REVIEW_LANES.get(key, "review"),
                       "warning": "Phrase found; may describe a negation, another party, or an immaterial exposure."})
        if len(result) >= max_matches:
            break
    return result


def summarize(hl):
    """Single screener row without pretending overlapping categories are additive."""
    cats = hl.get("categories") or []
    get = lambda key: next((c.get("amount_usd") for c in cats if c.get("key") == key), None)
    return {"categories": len(cats), "signals": len(hl.get("text_signals") or []),
            "purchase": get("purchase"), "purchase_broad": get("purchase_broad"),
            "guarantees": get("guarantees"),
            "operating_lease": get("operating_lease"),
            "lease_payments": get("lease_payments"),
            "coverage": hl.get("coverage"), "as_of": hl.get("as_of")}
