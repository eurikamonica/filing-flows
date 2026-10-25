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
TEXT_RULES = (
    ("take_or_pay", "Take-or-pay contracts", r"\btake[- ]or[- ]pay\b"),
    ("ppa", "Power purchase agreements", r"\bpower purchase agreements?\b"),
    ("capacity", "Cloud / compute capacity commitments", r"\b(?:cloud|gpu|compute|data center) (?:capacity|purchase) commitments?\b"),
    ("uncommenced_leases", "Leases not yet commenced", r"\bleases? (?:that have|which have)? ?not yet commenced\b|\bleases? (?:not|yet to be) commenced\b"),
    ("supplier_finance", "Supplier finance / reverse factoring", r"\bsupplier finance (?:arrangements?|programs?)\b|\breverse factoring\b"),
    ("securitization", "Receivables securitization", r"\breceivables securiti[sz]ation\b"),
    ("vie", "Variable interest entities", r"\bvariable interest entit(?:y|ies)\b"),
    ("special_purpose", "Special purpose entities", r"\bspecial purpose (?:entities|entity|vehicles?|structures?)\b"),
    ("keepwell", "Keepwell / liquidity support", r"\bkeepwell agreements?\b|\bliquidity backstop\b"),
    ("residual_guarantee", "Residual value guarantees", r"\bresidual value guarantees?\b"),
    ("joint_venture", "Joint venture funding commitments", r"\b(?:joint venture|jv) (?:funding|capital) commitments?\b"),
    ("sale_leaseback", "Sale-and-leaseback transactions", r"\bsale[- ]and[- ]leaseback\b"),
    ("redeemable_nci", "Redeemable noncontrolling interests", r"\bredeemable noncontrolling interests?\b"),
)
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


def scan_filing_text(raw, cik, accession, document, form, filed, max_matches=18):
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
