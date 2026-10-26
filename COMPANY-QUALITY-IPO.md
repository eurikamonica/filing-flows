# Company quality and IPO prospectus analysis

Company pages now include twelve transparent measures in **Profit & cash**. The
new **Companies → IPO & prospectuses** route (`#ipo`) opens the reviewed watchlist;
`#ipo-2130357` opens Anthropic. This adds to existing earnings, reserve, leverage,
and capital-allocation views; it does not replace their calculations.

## Company measures

Gross, operating, net, operating-cash and free-cash-flow margins; operating cash
conversion; stock-compensation, R&D and cash-CapEx intensity; cash-flow accruals;
return on average assets; and the current ratio. Each period includes formulas,
input amounts and references to the existing compact SEC evidence index.

FCF = OCF minus cash CapEx. Cash conversion requires positive net income. Average
assets require both opening and closing balances. Quarterly ROA/accrual ratios
are period measures, not annualized. Missing facts are unavailable, not zero.
Banks/insurers receive a comparability notice. There is no universal score,
fraud allegation, sector percentile or unsupported growth-stage classification.
Quality version 8 uses the existing incremental refresh queue: older companies
acquire the new measures as they are rebuilt, not all in the first deployment.

## Anthropic evidence and presentation

Source: public S-1 filed 2026-10-26, CIK 2130357, accession
`0001628280-26-067168`:
https://www.sec.gov/Archives/edgar/data/2130357/000162828026067168/anthropicpbc-sx1.htm

The source is HTML financial tables, not inline XBRL. The reviewed adapter checks
five exact period headers and the millions scale, retains raw cells and table
indexes, compares repeated tables, and rejects conflicting or unreconciled data.
The bundled snapshot records the original document SHA-256. A compact test
fixture preserves the two source tables (summary operations and cash flows).
FY 2023/2024/2025 and H1 2025/2026 are separate selections. The half-year cash
statement reports stock compensation of 279 million for H1 2025; this is used
for its cash reconciliation, rather than the 286 million in an operations
summary footnote, which has a different disclosed scope.

H1 2026, USD millions: revenue 16,286; operating loss (693); net loss (80,748);
operating cash 3,929; cash CapEx 482; FCF 3,447. Net loss includes financing
fair-value changes and is not cash burn. Gross profit/margin are unavailable:
compute expenses are not relabeled as cost of revenue.

Four reconciled Sankeys reuse the production chart renderer and PNG export:

1. Revenue and operating expenses.
2. Operating result, interest, financing fair value, other items and tax to net income.
3. Net income, noncash adjustments and working capital to operating cash.
4. Operating/investing/financing cash and FX to the change in cash, including restricted cash.

All bands are nonnegative widths. Negative equation terms are marked (−), and a
balancing loss is explicitly not financing. Node values are magnitudes; source
cards/evidence preserve signed reported values. This is an accounting
reconciliation, not a claim that all flow bands represent cash transactions.

IPO pricing, primary versus secondary proceeds, dilution, ownership, commitments
and future funding needs are not inferred from press estimates. Those analyses
require additional verified fields. No IPO proceeds or commitments Sankey is
invented when the filing lacks a quantified allocation.

## Collection and deployment

The verified Anthropic snapshot remains available offline on first deployment.
The market-wide collector described below replaces the initial seed-only watchlist
collector for production. Company quality version 8 still uses the existing
incremental earnings rebuild queue.

## Validation

- 86 Python tests passed (IPO/quality tests plus the existing pipeline suite,
  excluding six browser-dependent tests).
- JavaScript signed-flow conservation, missing-data, escaping and syntax checks passed.
- Static site assembly passed; all four H1 2026 charts rendered through the
  production Sankey layout/Canvas renderer and were inspected for layout.
- Full browser/mobile/PNG-download interaction validation could not run locally:
  the environment's Chromium download returned invalid archives. This remains
  a validation limitation, not a passing browser check.

Merge the PR and let the existing scan/Pages workflow finish before treating the
feature as live. A code branch or PR alone does not update production.

## Market discovery, analysis and monitoring

The production producer is now `pipeline.ipo_market`, backed by a SQLite accession
catalog and persistent retry queue on the independent `ipo-data` branch. The
reviewed seed remains a fallback, not an issuer allowlist. Every issuer appearing
in the configured SEC sources is eligible, including companies without a ticker.

Discovery reads the current Atom feeds, recent daily master indexes and quarterly
master indexes. It handles S-1/F-1/S-11 and amendments, public DRS/DRS/A,
424B1/424B3/424B4/424B5, EFFECT and RW/RW/A. Registration filings are not all IPOs:
source-language labels distinguish IPO language, resale language and unclassified
registrations. EFFECT/RW annotations require the same SEC file number and never
prove exchange listing. Confidential, unpublished drafts are not accessible.

Historical catch-up defaults to **2024-01-01 onward**, at two quarters per run,
newest first. `workflow_dispatch.backfill_from` can extend it back to 1994. The
UI reports completed/total quarters and remaining gaps. This is all-issuer
coverage of the scanned periods, not a claim that every historical SEC filing
has already been fetched or every financial statement has been parsed.

### Scheduling and publication

`.github/workflows/ipo-market.yml` targets a run every five minutes, with bounded
request timeouts and at most two requests/second. It also accepts an `ipo-scan`
repository dispatch for an external clock. GitHub/SEC latency is not guaranteed.
The queue saves discovery before document extraction, prioritizes both new and
old jobs, applies exponential retry delays, and retains unsupported tables for
review. A failed download does not erase issuer metadata or older parsed data.

A separate public data branch lets the UI check for updates every minute without
waiting for the full earnings/Pages build. Only a fixed public raw-GitHub path is
accepted. The site snapshot is a fallback and is labeled as such. A new snapshot
produces a Load updates banner; it does not reset a reader's selected period
silently. Hidden/inactive pages do not continue active network polling. The UI
marks stale monitor state after twenty minutes without a complete feed pass.
The regular site build stages the same branch as a local fallback.

### Analysis pages and evidence

`#ipo` provides name/CIK search, form, offering-language and analysis-state
filters, counts, history completeness and failures. `#ipo-CIK` shows a company;
`#ipo-CIK/ACCESSION` opens a specific version. Every discovered issuer gets a
page, including queued and failed downloads. Financial source tables preserve
original headers, rows and units instead of guessed numbers. Sections include
Use of Proceeds, Risk Factors, Dilution and ownership headings where found;
these are source excerpts, not model-generated investment conclusions.

Where standard XBRL facts support them, operating-cost and FCF reconciliations
are available. The Anthropic reviewed adapter retains all four original charts.
Unsupported untagged tables require a reviewed mapping before they can feed a
numerical model. Pages clearly separate latest discovered filing from selected
or last successfully parsed financials. Missing coverage is shown explicitly.

### Expanded validation

Fourteen focused Python tests cover market discovery without an issuer list,
accession deduplication, metadata-before-download persistence, bounded retry,
source failures, resumable history, SEC primary-document selection, file-number
lifecycle matching, missing-tag analysis, conservative resale classification and
standard XBRL prospectus support, alongside the original accounting tests.
A dedicated GitHub Actions check exercises desktop/mobile filters, unparsed
pages, source escaping, four Sankeys, period changes, PNG downloads, historical
routes and the live update banner. Local Chromium launch is blocked by the
execution environment's socket policy, so browser execution is delegated to CI
(the installed browser itself now downloads successfully).

Operational activation requires this PR's merge to main: GitHub schedules only
run from the default branch. The existing repository SEC_USER_AGENT secret or
variable supplies the real project identity; no contact is invented and no
secret is sent to browsers. After merge, inspect IPO market discovery and
analysis → latest run, then `data/ipo/status.json` / live `ipo-data/public/status.json`
before declaring monitoring active or historical backfill complete.
