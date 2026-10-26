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

`python -m pipeline.ipo --out _site/data/ipo --store store/ipo --refresh`
checks recent SEC submissions for S-1, S-1/A, F-1, F-1/A and 424B4 on the reviewed
watchlist. It uses the existing SEC client/User-Agent/rate limiting. Only a
successful parse replaces the current snapshot; accession snapshots are retained
under the persisted store. Separate last-attempt/last-success/error state is
published. Failed refreshes keep the previous filing and show a warning.

`pipeline/data/ipo/*.json` defines the initial reviewed watchlist (Anthropic only
in this release). Additional issuers require a verified seed. A conservative
standard-concept inline-XBRL reader supports duration statements, excludes
segments and pro forma scenarios, and rejects conflicting duplicate facts or
mixed currencies. Only fully supported reconciliations get charts. This is not
an all-market IPO discovery service. The HTML adapter deliberately rejects
changed column layouts until reviewed; unknown custom tags are not guessed.

The regular scan workflow refreshes the watchlist after site assembly and
persists it with the existing store. `build_site.py` includes an offline seed so
the route works on first deployment. New JS/CSS are included through the site's
asset discovery. CI runs the Python tests and signed-flow JavaScript checks.

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
