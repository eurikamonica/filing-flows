"""Conservative Phase-2 SEC HTML footnote evidence for contractual obligations.

Only named USD tables with explicit fiscal/calendar year columns or rows
become payment ladders. Results remain REVIEW REQUIRED and non-additive.
This is not a GAAP debt calculation or a blanket inline-XBRL parser.
"""
import datetime as dt
import re
from html.parser import HTMLParser

SPECS = (
    ("uncommenced_leases", "Leases not yet commenced", "B",
     r"\bleases? (?:that |which )?(?:have )?not (?:yet )?commenced\b|\buncommenced leases?\b"),
    ("capacity", "Cloud / GPU capacity minimums", "B",
     r"\b(?:GPU|cloud|compute|data.cent(?:er|re))\b.{0,85}\b(?:minimum|capacity|commitments?|purchase obligations?)\b"),
    ("ppa", "Power purchase agreement minimums", "B",
     r"\b(?:power purchase agreements?|PPAs?)\b.{0,85}\b(?:minimum|payments?|commitments?|purchase)\b"),
    ("supplier_finance", "Supplier financing obligations", "A",
     r"\b(?:supplier finance (?:arrangements?|programs?)|reverse factoring|structured payables)\b"),
    ("vie_support", "VIE / SPE support obligations", "A/C",
     r"\b(?:variable interest entit(?:y|ies)|VIEs?|special.purpose (?:entit(?:y|ies)|vehicles?))\b.{0,110}\b(?:support|funding|guarantees?|commitment)\b"),
)
NUMBER = re.compile(r"^\s*\$?\s*(\d{1,3}(?:,\d{3})*|\d{4,12})(?:\.(\d{1,4}))?\s*$")
YEAR = re.compile(r"^(?:(?:FY|Fiscal)\s*|Remainder of fiscal\s*)?(20\d{2})$", re.I)
TOTAL = re.compile(r"^(?:total|aggregate|total minimum payments?|total commitments?|total obligations?)\b", re.I)
NEGATIVE = re.compile(r"\b(?:no|none|not subject to|no such|terminated|cancelled)\b", re.I)


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.history = ""
        self.current = None
        self.cell = None
        self.row = None
        self.tables = []
        self.ignore = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignore += 1
        if self.ignore:
            return
        if tag == "table":
            if self.current is None:
                self.current = {"context": self.history[-1100:], "rows": []}
        elif self.current is not None and tag == "tr":
            self.row = []
        elif self.current is not None and tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.ignore:
            self.ignore -= 1
            return
        if self.ignore:
            return
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split())[:200])
            self.cell = None
        elif tag == "tr" and self.row is not None and self.current is not None:
            if any(self.row):
                self.current["rows"].append(self.row[:24])
            self.row = None
        elif tag == "table" and self.current is not None:
            self.tables.append(self.current)
            self.current = None
            self.history = self.history[-900:]

    def handle_data(self, data):
        if self.ignore:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.current is None:
            self.history = (self.history + " " + data)[-1800:]


def _amount(value, multiplier):
    value = value.replace("\u00a0", " ").strip()
    if value in ("—", "-", "–", "N/A", "n/a", "") or "(" in value or ")" in value:
        return None
    m = NUMBER.fullmatch(value)
    if not m:
        return None
    amount = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
    return round(amount * multiplier, 2)


def _units(context, rows):
    """Require positive USD evidence; never silently assume currency or scale."""
    data = (context[-550:] + " " + " ".join(" ".join(r) for r in rows[:3]))[:4500]
    if re.search(r"\b(?:EUR|GBP|CAD|euros?|sterling)\b|[€£]", data, re.I):
        return None
    if not re.search(r"\bUSD\b|\bU\.S\. dollars?\b|\bdollars?\b|\$", data, re.I):
        return None
    m = re.search(r"\b(?:in|amounts? in)\s+(billions?|millions?|thousands?)\b", data, re.I)
    if not m:
        # A dollar sign on one cell provides currency but not scaling:
        # assume units ONLY for clearly dollar-denominated unscaled amounts.
        if not re.search(r"\$", data):
            return None
        return 1
    return {"billion": 1e9, "million": 1e6, "thousand": 1e3}[m.group(1).lower().rstrip("s")]


def _annual(rows, multiplier, as_of):
    """Return year -> amount, with at least two explicit future years."""
    out = {}
    base_year = int(as_of[:4])
    # SEC HTML often splits "$", amount and spacer into distinct cells.
    # Accept only ONE numeric amount per row to avoid silently mixing operating
    # versus finance lease columns. Preserve the exact issuer-year label.
    for r in rows:
        if len(r) < 2:
            continue
        match = YEAR.fullmatch(r[0].strip())
        if match:
            year = int(match.group(1))
            amounts = [_amount(cell, multiplier) for cell in r[1:]]
            amounts = [n for n in amounts if n is not None]
            if base_year < year <= base_year + 25 and len(amounts) == 1:
                out.setdefault(year, amounts[0])
    if len(out) >= 2:
        return out
    # Year columns and exactly one named amounts row.
    for header_index, header in enumerate(rows[:5]):
        year_cols = []
        for i, v in enumerate(header):
            m = YEAR.fullmatch(v.strip())
            if m and base_year < int(m.group(1)) <= base_year + 25:
                year_cols.append((i, int(m.group(1))))
        if len(year_cols) < 2:
            continue
        for row in rows[header_index + 1:header_index + 4]:
            if len(row) <= max(i for i, _ in year_cols):
                continue
            if not re.search(r"\b(?:minimum|payment|commitment|obligation|purchase|contract|lease|total)\b",
                             row[0], re.I):
                continue
            found = {year: _amount(row[i], multiplier) for i, year in year_cols}
            found = {k: v for k, v in found.items() if v is not None}
            if len(found) >= 2:
                return found
    return {}


def _period_balance(rows, context, multiplier, as_of, kind):
    """Strict balance-column extraction for supplier finance/VIE maximums.

    A reporting *year* alone is not adequate; require full reporting date,
    a dated year column and a specifically labeled outstanding/maximum row.
    """
    d = dt.date.fromisoformat(as_of)
    human = re.compile(r"\b" + d.strftime("%B") + r"\s+" + str(d.day) +
                       r",?\s+" + str(d.year) + r"\b", re.I)
    heading = context + " " + " ".join(" ".join(r) for r in rows[:3])
    if not (human.search(heading) or as_of in heading):
        return None
    label = (r"\b(?:confirmed|approved|valid|supplier).{0,50}"
             r"(?:outstanding|obligations? at period end)\b|"
             r"\b(?:outstanding|ending balance)\b.{0,50}\b(?:payables?|obligations?)\b"
             if kind == "supplier_finance" else
             r"\b(?:maximum|aggregate).{0,60}\b(?:exposure to loss|support obligations?|guarantees?)\b")
    for i, header in enumerate(rows[:4]):
        cols = [j for j, val in enumerate(header)
                if YEAR.fullmatch(val.strip()) and int(YEAR.fullmatch(val.strip()).group(1)) == d.year]
        if len(cols) != 1:
            continue
        col = cols[0]
        for row in rows[i+1:i+12]:
            if len(row) <= col or not re.search(label, row[0], re.I):
                continue
            value = _amount(row[col], multiplier)
            if value is not None:
                return value, row[0][:180]
    return None


def _narrative_uncommenced(raw, cik, accession, document, form, filed, as_of):
    """Recognize disclosed gross lease totals even when NO annual ladder exists.

    Example: 'As of June 30, 2026, we had additional leases ... not yet
    commenced of $329.1 billion.' Also supports 'we had $260 billion of
    additional lease commitments ... expected to commence'. No implied
    yearly allocation is derived.
    """
    from hidden_leverage import sec_url
    from debt_docs import to_text
    if not raw:
        return []
    d = dt.date.fromisoformat(as_of)
    date_re = re.compile(r"\bAs of\s+" + d.strftime("%B") + r"\s+" +
                         str(d.day) + r",?\s+" + str(d.year) + r"\b", re.I)
    text = " ".join(to_text(raw[:4_000_000]).split())
    amount_re = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,4})?)\s*"
                           r"(billion|million)\b", re.I)
    vals = []
    for date_hit in date_re.finditer(text):
        # Only the first qualifying amount in the same local disclosure sentence.
        frag = text[date_hit.end():date_hit.end() + 310]
        boundary = re.search(r"[.;](?:\s|$)", frag)
        if boundary:
            frag = frag[:boundary.start()]
        for m in amount_re.finditer(frag):
            context = frag[:m.start()] + " " + frag[m.end():]
            # A precise uncommenced lease description is required; do not
            # interpret a nearby regular lease liability or a guarantee.
            if not re.search(r"\b(?:additional (?:lease|leasing) (?:commitments?|obligations?)|"
                             r"additional leases?|uncommenced leases?)\b", context, re.I):
                continue
            if not re.search(r"\b(?:not yet commenced|not commenced|"
                             r"(?:expected|scheduled|will) to commence|not reflected)\b",
                             context, re.I):
                continue
            if re.search(r"\b(?:guarantee(?:d|s)?|borrowings?|lessor.s debt)\b",
                         frag[max(0, m.start()-35):m.end()+15], re.I):
                continue
            amount = float(m.group(1).replace(",", ""))
            amount *= 1e9 if m.group(2).lower() == "billion" else 1e6
            if amount < 0:
                continue
            vals.append({
                "key": "uncommenced_leases",
                "label": "Additional uncommenced lease commitments (narrative total)",
                "review_lane": "B", "amount_kind": "disclosed_nominal_lease_commitment",
                "amount_usd": amount, "payments": [],
                "status": "narrative_amount_needs_review", "confidence": "provisional",
                "currency": "USD", "as_of": as_of, "filed": filed, "form": form,
                "accession": accession,
                "source_url": sec_url(cik, accession, document),
                "context": ("As of " + d.strftime("%B") + " " + str(d.day) + ", " +
                            str(d.year) + " " + frag)[:410],
                "warning": "Narrative gross lease commitment, not commenced/recognized; "
                           "no annual amounts reported here. Conditions and overlaps require review."
            })
            break
    seen = set()
    out = []
    for v in vals:
        token = (v["key"], v["as_of"], v["amount_usd"])
        if token not in seen:
            out.append(v)
            seen.add(token)
    return out[:6]


def extract_tables(raw, cik, accession, document, form, filed, as_of):
    """Parse auditable *candidates* from ONE SEC primary document, never debt."""
    if not raw or not as_of or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        return []
    if form not in {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F"}:
        return []
    from hidden_leverage import sec_url
    url = sec_url(cik, accession, document)
    if not url:
        return []
    parser = _Tables()
    try:
        source = raw[:4_000_000] if isinstance(raw, (bytes, str)) else ""
        parser.feed(source.decode("utf-8", "replace") if isinstance(source, bytes) else source)
        parser.close()
    except (ValueError, TypeError):
        return []
    evidence = []
    seen = set()
    for idx, tab in enumerate(parser.tables[:220]):
        rows = tab["rows"][:100]
        if not rows:
            continue
        context = " ".join(tab["context"].split())[-600:]
        context_tail = context[-420:]
        for key, label, lane, regex in SPECS:
            if not re.search(regex, context_tail, re.I):
                continue
            # Disallow immediate negated descriptions; a disclosed table must stand alone.
            if NEGATIVE.search(context_tail[-125:]):
                continue
            mult = _units(context, rows)
            if mult is None:
                continue
            annual = _annual(rows, mult, as_of)
            if key in ("supplier_finance", "vie_support"):
                balance = _period_balance(rows, context, mult, as_of, key)
                if not balance:
                    continue
                amount, row_label = balance
                signature = (key, as_of, amount)
                if signature in seen:
                    continue
                seen.add(signature)
                evidence.append({
                    "key": key, "label": label, "review_lane": lane,
                    "status": "table_extracted_needs_review", "confidence": "provisional",
                    "payments": [], "amount_usd": amount, "currency": "USD",
                    "scale": mult, "as_of": as_of, "filed": filed, "form": form,
                    "accession": accession, "source_url": url, "table_index": idx,
                    "context": context_tail[-260:], "matched_row": row_label,
                    "raw_rows": rows[:18],
                    "amount_kind": ("reported_supplier_finance_balance" if key == "supplier_finance"
                                    else "maximum_support_exposure_not_expected_loss"),
                    "warning": "Review issuer-specific accounting, recourse and balance-sheet overlap. "
                               "A supplier payable may already be reported; a VIE maximum is not expected loss."
                })
                continue
            if len(annual) < 2:
                continue
            payments = [{"year": year, "amount_usd": amount,
                         "row_or_column": str(year)}
                        for year, amount in sorted(annual.items())]
            signature = (key, tuple((x["year"], x["amount_usd"]) for x in payments))
            if signature in seen:
                continue
            seen.add(signature)
            evidence.append({
                "key": key, "label": label, "review_lane": lane,
                "status": "table_extracted_needs_review",
                "confidence": "provisional",
                "payments": payments, "amount_usd": None,
                "currency": "USD", "scale": mult,
                "as_of": as_of, "filed": filed, "form": form, "accession": accession,
                "source_url": url, "table_index": idx,
                "context": context_tail[-260:],
                "raw_rows": rows[:18],
                "warning": "Candidate annual nominal payments; verify table scope, cancellation, "
                           "overlap, units and fiscal-year labels against SEC note. Not incremental debt."
            })
    # Narrative disclosures may report a valid gross total without any annual
    # maturity table. Keep those disclosures distinct from payment schedules.
    narrative = _narrative_uncommenced(raw, cik, accession, document, form, filed, as_of)
    return (evidence + narrative)[:30]
