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
YEAR = re.compile(r"^(?:FY\s*)?(20\d{2})$")
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
    # Year in first column, payment in second; reject unspecified other columns.
    for r in rows:
        if len(r) != 2:
            continue
        match = YEAR.fullmatch(r[0].strip())
        if match:
            year = int(match.group(1))
            v = _amount(r[1], multiplier)
            if base_year < year <= base_year + 25 and v is not None:
                out.setdefault(year, v)
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
            # Outstanding supplier-finance balances are NOT payment schedules,
            # and VIE/guarantee maxima must not be relabeled as debt.
            if key in ("supplier_finance", "vie_support") or len(annual) < 2:
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
    return evidence[:24]
