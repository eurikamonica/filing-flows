# 01 — Data contracts, evidence and isolation

Created by ChatGPT (OpenAI).

## Additive boundaries

Develop on an isolated beta branch/worktree. New modules may read immutable copies of existing exports through explicit adapters, but must not write to production data or import production modules with side effects. Do not silently change earlier beta schemas. Create named adapters and preserve originals. Each adapter must reject unsupported fields and report missing data.

Proposed components inside `research-core/`: `contracts/`, `fixtures/`, `validate.py`, `normalize.py`, `adapters/`, `tests/`, and an English README. These filenames are implementation targets.

## Financial observation v1

A proposed observation looks like this:

```json
{
  "schema_version": "financial-observation-1",
  "entity_id": "demo-001",
  "concept": "net_income",
  "value": 130,
  "currency": "USD",
  "unit_scale": 1000000,
  "period": {
    "kind": "annual",
    "start": "2025-01-01",
    "end": "2025-12-31"
  },
  "scope": "consolidated",
  "basis": "reported",
  "status": "fictional",
  "available_at": "2026-02-01T13:00:00Z",
  "available_at_precision": "illustrative",
  "retrieved_at": "2026-02-02T12:00:00Z",
  "source_ids": ["demo-source-1"],
  "version_id": "demo-v1",
  "supersedes": null,
  "missing_reason": null
}
```

This is a fictional schema example, not company data. Monetary base value = value × unit_scale. Normalize once; retain original reported value, label and unit in the evidence record. A metric must specify whether it expects base units or display units. Shares and percentages use distinct dimensions, not monetary unit scales.

Required distinctions:

- Duration versus instant observations. Balance-sheet assets are instants, not annual flows.
- Currency, unit scale, consolidation scope, GAAP/non-GAAP basis and discontinued operations.
- Filing publication/acceptance time, retrieval time and fiscal observation period.
- Reported, derived, assumed, manually adjusted and missing values.
- Amendment/revision lineage. Append a new version; do not erase what was available earlier.

A derived metric carries formula ID/version, input observation IDs, assumptions, output unit, rounding policy and calculation timestamp. Its available-at time cannot precede the latest required input. For historical research, user assumptions also need their own creation/as-of time.

## Evidence record

Store source ID, document URL, accession/version if available, document hash, filing type, section/table/page locator, original label, short excerpt, extraction method and review status. Link numbers to exact evidence IDs. Text extraction is not verification. Footnote tables and standard XBRL facts have different coverage.

The evidence drawer should show raw amount → normalization → formula → result. Missing evidence means an incomplete view, not a clean financial conclusion. Limit excerpt retention according to source permissions; avoid publishing bulk third-party documents without checking reuse rights.

## Period rules

1. Match entity, scope, currency and accounting basis before comparison.
2. Compare discrete quarters to comparable discrete quarters or annual values to annual values.
3. Convert a YTD flow to a quarter only with aligned same-year YTD inputs and compatible versions: Q2 = H1 − Q1; Q3 = 9M − H1; Q4 = FY − 9M. Retain both source IDs.
4. Do not difference balance-sheet instants as if they were cash flows.
5. For a trailing period, sum four valid consecutive quarters; reject gaps or incompatible scopes.
6. Specify treatment of 52/53-week years. Do not mechanically interpret all year-over-year differences as economic growth.
7. Null stays null. A verified zero remains a numeric zero.

## Historical availability

For an as-of query, select only versions whose available_at is no later than the cutoff. Date-only macro vintages do not establish intraday availability: label precision and use a conservative next-session rule unless an actual release timestamp is known. Retrieval time is not a substitute for original availability.

## Data retrieval architecture

Use a local or scheduled collector to fetch permitted public data, store raw responses privately where appropriate, normalize, validate, then export sanitized snapshots. The browser reads those snapshots. The SEC states that data.sec.gov does not support CORS, so direct cross-origin browser requests are not the planned integration [S1]. Follow current fair-access rules, identify the client as required, cache results, back off on throttling and retain the last valid snapshot.

Keep API keys out of HTML, JS, public JSON, logs and published artifacts. Public availability does not guarantee uniform redistribution rights for all market or macro series.

## Acceptance fixtures

Include mismatched currency, duplicate amended facts, zero versus null, negative income, YTD mislabeled as a quarter, missing Q3, 53-week periods, dates without precise timestamps, and derived metrics with later inputs. Expected result: reject incompatible calculations or explicitly mark them unavailable; never silently fill or annualize.

## Sources

Checked October 16, 2026 UTC.

- [S1: SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC automated access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
