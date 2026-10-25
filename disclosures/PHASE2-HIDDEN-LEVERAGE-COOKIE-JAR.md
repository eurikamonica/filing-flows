# Hidden Leverage — Phase 2 (SEC evidence) + Cookie Jar Revenue

**Status:** Research-stage candidates. Extracted values require issuer-footnote review. Extends Phase 1 in HIDDEN-LEVERAGE.md.

## Integration

- hidden_leverage_tables.py: bounded parse of latest SEC primary-document HTML; only named USD tables with identifiable annual payment years or a full current balance date.
- revenue_quality.py: two **comparable full fiscal years** from SEC companyfacts, plus primary filing text leads.
- debt.py: attaches hidden_leverage.footnote_tables and revenue_quality to a company's Debt & Rates document, adds two index counts and triggers a one-time v2 data backfill.
- hidden-leverage.js: standalone source-anchored evidence; original GAAP debt, net debt, implied CDS and valuations are untouched.

## Scope and treatment

| Evidence | Rule | Interpretation |
|---|---|---|
| Leases not yet commenced | explicitly named USD note and >=2 future years | nominal gross commitments, not borrowing |
| GPU/cloud minimum capacity | same | contractual services, not debt |
| Power purchase agreements | same | energy commitments, not debt |
| Supplier finance | named program, full balance date, *outstanding* table row | outstanding payable may already be in A/P |
| VIE/SPE support | VIE/support context, full balance date, explicit *maximum exposure* row | contingent maximum, not expected loss |

Data: accession, form, filing date, source document, table index, extract/context, raw table cells, USD unit scale and status "table_extracted_needs_review". No sum or artificial total. Absence means **unknown**, never zero. No foreign currency conversion, full inline-XBRL taxonomy mapping, PDF OCR, comprehensive footnote coverage or cross-category contract de-duplication yet.

HTML table inference does not establish cancellability, recourse, accounting treatment or double-counting. Any investment conclusion requires reconciling each candidate against the original note. Payments labeled by calendar year may in reality use a company's fiscal-year convention; the label requires review.

## Can Cookie Jar manipulation be outside reserve balances?

**Yes.** A reserve is only one mechanism for smoothing reported earnings. Risks worth examining separately are revenue-timing decisions (bill-and-hold, consignment, acceptance clauses), unbilled revenue and contract assets, deferred revenue release, factoring/receivable transfers, variable consideration and rebates, related-party sales, channel inventory incentives, contract amendments, capitalization of costs and other non-operating gains. Expense capitalization affects earnings rather than revenue directly.

Quantitative SEC screens, using stated annual facts:

- DSRI = (receivables/revenue)_t / (receivables/revenue)_(t-1), review if >1.25.
- Contract asset growth minus revenue growth >30 percentage points, alongside rising contract assets.
- Contract liability decline >20% accompanied by revenue growth >10%.
- Operating cash flow / positive net income <0.60 (earnings-quality context only).

Also flag **unverified text leads** (bill-and-hold, consignment, customer acceptance, contract modification, significant financing, deferred revenue, related-party revenue, variable consideration and receivable sales). Keywords in normal accounting notes are NOT proof of wrongdoing. Missing metrics are UNKNOWN, not clean. Consider sector, acquisitions, negative earnings, cash cycle and ASC 606 contract mix before interpreting anomalies.

## Go-live gates

1. Python Phase 1 and Phase 2 tests + JavaScript syntax checks must pass; offline CI also green.
2. Manually sample original SEC note tables for ORCL, MSFT, AMZN to verify numbers, dates, units, year-end conventions and overlaps. **No sourced amount is assumed before inspection.**
3. Keep original Debt & Rates calculations byte-for-byte unchanged.
4. After merge run the existing Debt and rates collection workflow (prioritize large filers), then the existing EDGAR Scan / Pages publishing workflow; verify the Hidden index and company links.
5. Provide visible provisional/review labels. Do not claim a complete contractual-obligations or fraud audit.

**Still future:** inline-XBRL extension/dimension parsing, full ASC 405-50 rollforward, contract-level dedupe, scenario reconciliation, more issuer-tested tables, manual evidence promotion, and a separate full Revenue Quality view integrating cash receipts, reserve movement and restatement/estimate changes.
