# v4 coverage and display scope

COT discovers all codes in the configured Disaggregated/TFF futures-only datasets, including historical and consolidated codes. FDIC discovers active institutions by default; bank histories remain distinct from listed holding companies. N-PX uses separate filer and document queues. Its browser filters, charts and CSV apply to loaded vote chunks, with explicit loaded/total counts. Filings and amendments remain separate documents.

# v3 scope update

Discovery catalogs cover the configured index window. Catalog presence does not mean holdings have been downloaded. Per-source counts distinguish managers, documents, rows, pending items and unsupported codes. House names/districts are source labels, not guaranteed unique person IDs or current office. Missing filing dates stay blank.

Manager histories load from per-quarter JSON; compressed full-filing caches are for the collector. No total or midpoint is inferred for congressional asset ranges.

# Definitions and limitations

## Shared timing and missing values

Report dates, filing dates, acceptance times, first-seen times and collection times are different. Historical data may reflect later corrections. This is not a complete point-in-time database. Missing values remain null and display as an em dash; failures do not become zero positions.

Official and fictional datasets are separate. CSV exports cover the current filtered rows, not only the visible table page. Complex fields are JSON strings. Potential spreadsheet-formula text receives a protective prefix.

## 13F

The parser and tests were reused from the earlier `Filing-Flows-13F-Standalone.zip`, then integrated with the unified HTTP client and persisted snapshots.

Security identity is `CUSIP | share class | Put/Call flag | SH/PRN`. Options and common shares are not combined. Duplicate rows for the same identity are aggregated for display, while original filing rows remain available in the snapshot.

Values from filings before 2023-01-03 are converted from thousands to dollars; later-form values use dollars. The cutoff is based on filing date, not report period. Each file's information-table row count and value total are reconciled with the cover summary. A mismatch fails rather than silently publishing a suspect table.

Amendments:

- ORIGINAL starts a report-period base.
- RESTATEMENT replaces that base.
- NEW HOLDINGS adds entries to the available base.
- Missing bases or ambiguous multiple originals flag incomplete snapshots; comparisons are disabled.
- 13F-NT is a notice, not a zero-holdings report.
- Confidential omission flags remain visible. Even a structurally complete public table may omit confidential holdings.

Calculations:

- Weight = disclosed security value / sum of disclosed table values.
- Quantity change = current quantity − earlier quantity.
- Quantity change % = `(current / earlier − 1) × 100`; null when earlier quantity is zero/absent.
- Weight change in percentage points = `(current weight − earlier weight) × 100`.
- “New” and “not disclosed” refer to appearance in the compared public tables, not confirmed trade execution.

Price changes affect disclosed values even without quantity changes. Splits, reorganizations, transfers and reporting scope changes can affect quantities. The package does not apply corporate-action adjustments. Disclosed 13F value is not total AUM, and the data do not include a complete set of shorts or every asset class.

The history selector can compare any earlier available period. The security chart leaves an unreported security as a gap, not zero. A filing-date `as_of` cutoff is optional but does not replace a full historical publication-state archive.

## Congressional disclosures

Annual disclosed assets and PTR transactions are separate record types. Keep ownership labels (such as SP) and distinguish reported asset values from transaction amounts and income.

Amounts remain intervals. An open upper bound remains open. Asset charts show intervals rather than midpoint estimates; no “exact current portfolio value” is calculated. PTRs do not provide enough information to reconstruct a complete current portfolio.

Annual comparison is limited to reviewed excerpts. A missing reviewed row may reflect incomplete review or changes in disclosure, not a disposal. A new reviewed row is not proof of a purchase. The current comparison key is the reviewed asset name plus owner; name changes require human reconciliation.

The six included reviewed rows are partial, page-checked examples. All other extracted monetary ranges remain unclassified candidates, including possible income, liability, option-price and non-asset values. Confidence in OCR characters is not confidence in financial interpretation.

The House index year can differ from the filing year. Senate and state/local PDFs are import-only; they do not inherit House reporting rules. Congressional amendment consolidation and precision portfolio reconstruction are not implemented.

## COT

Only futures-only datasets are used. Disaggregated and TFF classifications differ and are kept separate.

- Net = long contracts − short contracts.
- Weekly change requires report dates exactly seven days apart.
- 52-observation index = `100 × (current net − window minimum) / (window maximum − window minimum)`.

The index is undefined with fewer than 52 valid observations or a constant range. It is a range position, not a percentile. Missing weeks mean 52 observations may cover more than 52 weeks. Separate spreading columns are not added to the net calculation. Open interest is a market-level measure. Contracts are not dollars or individually named fund positions.

## Banks

| Field | Original FDIC field | Unit / basis |
|---|---|---|
| assets | ASSET | USD thousands, period-end |
| deposits | DEP | USD thousands, period-end |
| loans_net | LNLSNET | USD thousands, net loans/leases |
| equity | EQ | USD thousands, period-end |
| net_income_ytd | NETINC | USD thousands, year-to-date |
| net_income_quarter | derived | USD thousands, standalone quarter |
| roa / roe | ROA / ROE | Original API percentage values |

Q1 standalone income equals Q1 YTD. Later quarters subtract the immediately preceding same-year quarter's YTD income. If that preceding quarter is unavailable, standalone income is null. Two-period growth uses `(current − baseline) / abs(baseline)` and is undefined for a zero/missing baseline.

These are bank legal entities identified by FDIC CERT, not automatically consolidated listed holding companies. Net loans/deposits and equity/assets are simple ratios, not regulatory capital adequacy ratios. Only selected Call Report-derived fields are included, not the full FFIEC schedules.

## N-PX

Reports are discovered through SEC submissions and relevant historical shards. XML vote tables are parsed by local element names, retaining original fields.

A proposal's total sharesVoted is not added to the shares in its individual voteRecord segments. Vote direction and alignment with management use separate fields. Shares on loan remain separate. Multiple proposals must not be summed into holdings.

The distribution chart counts vote segments, not share-weighted votes. Filtering a proposal by one direction retains all split-vote segments for that proposal. Management-opposition share is the count of AGAINST-management segments divided by explicitly FOR/AGAINST-management segments.

Each filing is viewed separately, including N-PX/A. Amendments are not automatically added to or treated as complete replacements of the original. Notices, legacy HTML, unsupported structures or absent vote tables remain marked; they do not mean zero holdings.
