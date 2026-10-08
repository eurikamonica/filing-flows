# v3 acquisition update

The default surname filter is now empty: all names in selected House indexes are cataloged. O/P documents enter the rotating PDF queue; other codes remain visible as unsupported. Directory metadata is not parsed asset data. The reviewed-record workflow below still applies. Run a specific report using Actions report_id or --report-id.

# Congressional disclosures and PDF/OCR review

## Automatic House acquisition

The collector reads the official overview's actual annual ZIP links, downloads each configured year index, and selects configured last names. The verified House routes for filing codes `P` (PTR) and `O` (annual) are supported; other codes are reported as unsupported instead of silently classified. An HTTP response must be a PDF before it is parsed.

The index `Year` is preserved separately from `FilingDate`. An annual report for 2025 can be filed in 2026 and appear in the 2025 archive.

Initial configuration tracks Pelosi across index years 2024–2026, up to 20 matching supported reports per year. This is a watchlist, not a nationwide database.

A known report is reused between runs. New report IDs are downloaded. `--revalidate` rechecks the source bytes of known documents, including replacements at an existing URL. The supplied Sunday daily job enables this option. Same-URL revisions may therefore remain undetected until revalidation; this is not instantaneous revision monitoring.

## OCR pipeline

1. Save the original PDF with its SHA-256.
2. Extract text and word coordinates with pdfplumber.
3. If a page has fewer than 60 non-whitespace text characters, render that page using Poppler and run Tesseract with English language data.
4. Retain extraction method and mean word confidence for each page.
5. Pair monetary range bounds using their visual positions, helping separate asset-value and income columns.
6. Store candidate intervals with page, original-document hash and nearby source text.
7. Publish candidates only in the separate review desk. They do not enter the Congress holdings/transactions view until reviewed.

Text density is only a heuristic. A corrupt text layer can pass the threshold. Use forced OCR when needed, and always check the source page. The word confidence is not a calibrated probability that the asset, owner or amount is correct.

A limited preview minimization rule omits residential-address wording matching a home-property label. It is not a universal privacy filter. Review the public snapshot before broad publication; original page text remains in the run's evidence files.

## Review workflow

1. Open **PDF / OCR**.
2. Select the document and candidate interval.
3. Open the official PDF at the linked page.
4. Check whether the amount represents an asset, a transaction, income, a liability, or another value. Ignore unrelated candidates.
5. Choose `Disclosed asset` or `Transaction` only for a verified record.
6. Fill the exact asset name/class, original owner label and optional verified ticker.
7. Keep the disclosed lower/upper bounds. Do not replace them with a midpoint.
8. For an asset, provide the report's valuation basis. Enter a valuation date only if supported.
9. For a transaction, enter its type and event date, which are distinct from the filing date.
10. Enter reviewer and review date, then **Keep as reviewed in this session**.
11. Export `reviewed-disclosures.csv`. The export includes the pre-existing reviewed records plus your session changes.
12. Save it to `config/reviewed-disclosures.csv`, commit/upload it to the independent repository, and run the Congress collector.

Browser review changes are session-only and are lost on reload unless exported. There is no automatic GitHub write or server-side user account. Demo exports are named `DEMO-reviewed-disclosures.csv` and must not replace the official reviewed file.

The Python importer rejects missing IDs, duplicate IDs, source-hash mismatches, invalid pages, reversed ranges, missing review information and incomplete transaction/asset fields. A PDF changed by a later revalidation requires review against the new hash.

### CSV fields

| Field | Meaning |
|---|---|
| `id` | Unique reviewed row identifier, usually the candidate ID |
| `report_id` | Exact report ID from the collected/imported report |
| `source_sha256` | Hash of that PDF; binds review to its version |
| `page` | 1-based source page |
| `kind` | `asset` or `transaction` |
| `asset` / `ticker` | Original asset/class; optional explicit/verified ticker |
| `owner` | Original ownership label, e.g. SP; do not assume it is the member personally |
| `transaction_type` / `transaction_date` | purchase, sale, exchange or other; actual event date |
| `amount_min` / `amount_max` | Inclusive USD bounds; blank upper bound means open-ended |
| `valuation_date` / `valuation_basis` | Source-supported valuation date and explanation |
| `reviewer` / `reviewed_at` | Person checking the source; ISO review date |
| `notes` | Source qualifications and corrections |

For an original “Over $1,000,000” category, store `amount_min=1000001` and leave the upper bound blank. Source categories use whole-dollar thresholds in this model; do not invent precision beyond the report.

The included six reviewed rows were checked against rendered source pages during package preparation and are labeled `Source check (assistant)`. They are examples of the workflow, not a claim that every row in those annual reports was verified.

## Senate, state and local imports

There is no national uniform state/local financial-disclosure form. Obtain the public document through the appropriate portal or request process, place the PDF in `imports/`, and add its metadata to `config/imports.json`. See `imports/README.md`.

For Senate eFD, this package does not automate access acknowledgments, session setup, searches or downloads. It processes a PDF after you have obtained it. State/local reports use the same import/review pipeline, with their own jurisdiction, form name and valuation basis preserved.

Amendments are separate documents. This version does not automatically merge congressional amendments into an exact consolidated portfolio. Use notes to identify the relationship and review the source.

## Local OCR tools

GitHub Actions installs the required tools automatically. Locally, check:

```powershell
py -3.12 -m pip install -r requirements.txt
tesseract --version
pdftoppm -v
```

On Windows, follow Tesseract's official installation guide and install a Poppler distribution containing `pdftoppm`. Add their executable directories to PATH. If those commands are not found, text-layer PDFs may still parse, but scanned pages will fail explicitly.

To inspect one PDF without changing the dashboard:

```powershell
py -3.12 app/ocr_document.py imports/report.pdf --output storage/report-pages.json
py -3.12 app/ocr_document.py imports/report.pdf --force-ocr --output storage/report-ocr.json
```

This writes extraction JSON only. To add a document to the dashboard, use the imports manifest and the collector.

## Source access and use

House and Senate disclosure portals publish restrictions on obtaining/using these reports, including restrictions on commercial purposes with a stated news/communications-media exception. Free access is not a blanket reuse license. Check the official conditions for the intended publication; this project does not determine that a particular business model qualifies.

- House: https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch
- Senate: https://www.ethics.senate.gov/public/index.cfm/financialdisclosure
- Tesseract installation: https://tesseract-ocr.github.io/tessdoc/Installation.html
- pdfplumber: https://github.com/jsvine/pdfplumber
