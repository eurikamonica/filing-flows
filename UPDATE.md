# Proposed Updates for Filing Flows

> Author: ChatGPT (OpenAI)  
> Date: October 15, 2026  
> Status: Recommendations only; none of the changes below are implemented by this document.  
> Basis: The repository review summarized in [CHATGPT_REPOSITORY_UNDERSTANDING.md](CHATGPT_REPOSITORY_UNDERSTANDING.md), with the current root listing and scan/request workflows checked again when preparing this file.  
> Scope: This commit adds only `UPDATE.md`. Existing code, configuration, workflows, data, and documentation remain unchanged.

## Recommended direction

Improve financial traceability and operational visibility first, then make the charts easier to read, and finally expand financial statements and research features. Keep the current static-site architecture for the first stages. A framework rewrite or hosting migration is not a prerequisite.

These are proposed improvements, not a list of confirmed production failures. Existing features such as source citations, data checks, comparison requests, FCF preferences, and disclosure health views should be extended rather than rebuilt.

## Priorities

Effort estimates are relative implementation sizes, not delivery commitments. P1 items can proceed after the relevant P0 foundations; P2 is optional expansion.

| ID | Priority | Proposed update | User benefit | Effort |
| --- | --- | --- | --- | --- |
| U01 | P0 | Reconcile documentation with current implementation | A reliable setup and maintenance guide | Small |
| U02 | P0 | Add a dedicated offline CI gate for the earnings site | Catch parsing and rendering regressions before deployment | Medium |
| U03 | P0 | Publish unified freshness and queue status | Explain why a filing or request is not yet visible | Medium |
| U04 | P0 | Extend figure provenance and revision history | Distinguish reported, derived, preliminary, and revised figures | Medium–large |
| U05 | P1 | Improve Sankey readability and accessible interaction | Make dense charts easier to understand and export | Medium |
| U06 | P1 | Add a compact financial table and CSV export | Inspect the exact numbers behind charts | Medium |
| U07 | P1 | Make collection-to-publication state explicit | Prevent confusion between collected and published data | Medium |
| U08 | P1 | Expand FCF definition comparison | Explain differences between company and calculated FCF | Medium |
| U09 | P1 | Strengthen disclosure comparison and coverage display | Interpret holdings changes without overstating completeness | Medium–large |
| U10 | P1 | Make delivery and social publishing outcomes auditable | Track retries, duplicates, and failed external actions | Medium |
| U11 | P2 | Add balance-sheet and cash-flow statement views | Broaden the financial picture beyond earnings Sankeys | Large |
| U12 | P2 | Plan data storage from measured growth | Support larger history without an unnecessary migration | Medium–large |

## U01 — Reconcile documentation with the current implementation

**Observed basis:** The repository now includes `disclosures/`, while older embedded documentation still describes a separate package. Some text describes the project as having no language-model usage, although `pipeline/tweet.py` supports model-assisted posts. Disclosure documentation also contains hourly-publication wording, while the scan workflow is scheduled every 15 minutes.

**Proposed changes**

- Document current entry points, branch responsibilities, and collection/publication paths.
- Separate rule-based financial extraction and analysis from optional model-assisted social writing.
- Clearly mark standalone-package instructions as historical or move them to an archive.
- Describe each schedule as configured cadence, with execution and source latency caveats.
- Explain which root-level duplicate scripts/YAML files are templates, legacy files, or still-used tools after tracing their callers.

**Likely files:** `README.md`, `disclosures/README.md`, deployment guides.

**Acceptance:** A new maintainer can identify the active workflows, storage branches, optional services, and current deployment steps without contradictory instructions. No runtime behavior changes.

## U02 — Add a dedicated offline CI gate

**Observed basis:** The repository contains extensive earnings fixtures/tests and a Playwright checker. The inspected scan workflow builds and publishes without an explicit earnings test step; the disclosure workflow has its own checks. This is not a claim that every other workflow lacks testing.

**Proposed changes**

- Add a pull-request workflow scoped to earnings pipeline, frontend, scripts, and relevant workflow changes.
- Run `python -m pytest tests` with supported dependencies and offline fixtures.
- Build a fixture site and run JavaScript syntax checks.
- Run the existing Playwright checks against the fixture build where practical.
- Keep SMTP, SEC live requests, social posting, and production secrets out of this gate.
- Add focused cases for any newly fixed financial behavior rather than duplicating implementation logic in tests.

**Likely files:** A new `.github/workflows/ci.yml`, existing tests and fixture tooling.

**Acceptance:** A financial parsing regression or broken chart export fails CI on a controlled fixture. The normal offline test path does not require external credentials.

## U03 — Publish unified freshness and queue status

**Observed basis:** Financial processing has pending filings, retry windows, history backfills, rereads, and a time budget. Disclosure modules already expose source health. Users need to distinguish source availability, processing, and website publication.

**Proposed changes**

- Extend existing health concepts to an earnings status manifest.
- Include separate timestamps for last attempt, last successful collection, data generation, and publication.
- Show pending counts by reason, including XBRL not available, budget deferred, retrying, and permanently unsupported.
- Show request states on company pages using the existing queues.
- Use timezone-aware timestamps; distinguish filing date, financial period end, and collection time.

**Likely files:** `pipeline/build.py`, `pipeline/custom.py`, `scripts/build_site.py`, `web/app.js`.

**Acceptance:** A user can tell whether a missing chart is waiting on SEC, waiting in a queue, failed, or collected but not yet published. A failed collection cannot display a new success timestamp.

## U04 — Extend provenance and preserve revisions

**Observed basis:** Node sources and derived-value flags already exist. Companyfacts indexing favors newer filings for the same period, so current historical values may incorporate later revisions.

**Proposed changes**

- Extend existing provenance with taxonomy, tag, unit, start/end dates, source accession, and selection method where available.
- For YTD subtraction, retain both contributing facts and their accessions.
- Label figures as directly reported, derived, preliminary release, or revised.
- Preserve an immutable source/version record before replacing stored values.
- Introduce a versioned schema and a resumable migration for existing stores.
- Offer “latest available” versus “as originally captured” only when the necessary history has actually been retained. Do not imply unavailable historical vintages can be reconstructed.

**Likely files:** `pipeline/facts.py`, `pipeline/sources.py`, `pipeline/build.py`, `pipeline/release.py`.

**Acceptance:** A displayed revised amount can be traced to the specific source version; a derived quarter shows both operands. Existing charts remain readable during migration.

## U05 — Improve Sankey readability and accessibility

**Observed basis:** Layout and drawing are centralized in `web/sankey.js`; financial semantics come from the Python chart specification. Existing end-to-end checks already address overlap, exports, and mobile overflow. This recommendation is not based on a new visual audit of the live site.

**Proposed changes**

- Test representative dense, loss-making, negative-OCF, and multi-segment charts before choosing layout changes.
- Offer a concise default view with optional expense/segment detail, preserving totals.
- Strengthen hierarchy between company, period, figures, comparison labels, and source notes.
- Provide a visible legend for negative flows, growth strips, and decrease hatching.
- Add keyboard-accessible node selection, clear focus, and a textual table alternative.
- Keep export layout aligned with the screen chart and preserve source/definition labels.
- Use adaptive spacing rather than shrinking all labels to fit dense charts.

**Likely files:** `web/sankey.js`, `web/app.js`, `web/styles.css`, `tests/e2e.py`.

**Acceptance:** Representative fixtures have no overlapping labels or page-level mobile overflow. Nodes can be inspected with a keyboard. PNG and PDF preserve the selected financial definition and readable labels.

## U06 — Add a financial table and CSV export

**Proposed changes**

- Show current, previous-quarter, and prior-year values beside the chart.
- Include absolute change, percentage change where meaningful, margins, units, and source links.
- Distinguish zero, missing, unsupported, and not meaningful.
- Export amounts at stored precision, with displayed rounding documented.
- Include the selected FCF/revenue basis, period type, and preliminary/final state.
- Prevent annual values from being mislabeled as quarterly values.

**Likely files:** `web/app.js`, chart payload generation.

**Acceptance:** Table, chart, and CSV reconcile for the same selected view. Missing values remain missing, and percentage changes across nonpositive bases follow a documented rule.

## U07 — Make collection and publication state explicit

**Observed basis:** Disclosure collection commits snapshots to main, while a separate scan checkout stages and publishes the disclosure site. Independent jobs can therefore publish a snapshot older than the newest collection.

**Proposed changes**

- Record the exact disclosure snapshot/version included in each site build.
- Make collection and publication timestamps visible together.
- Consider a lightweight publication request after collection, while retaining a single coordinated Pages deployment path.
- Validate generated JSON and required files before replacing a good published snapshot.
- Test interrupted collection and concurrent updates using controlled temporary stores.

**Likely files:** `.github/workflows/disclosures.yml`, `.github/workflows/scan.yml`, `disclosures/automation/stage-public.py`.

**Acceptance:** Every published build identifies the snapshot it contains. Concurrent collection cannot create an internally inconsistent staged snapshot.

## U08 — Explain FCF differences with a reconciliation panel

**Observed basis:** Company-reported FCF parsing, fallback notes, and reader preferences already exist.

**Proposed changes**

- Add a side-by-side reconciliation of OCF, capex, additional company adjustments, and FCF.
- Show why company-reported FCF was accepted or rejected for that period.
- Flag definition changes across periods before drawing a continuous trend.
- Keep quarterly and annual definition choices explicit.
- Preserve the same basis in the chart, table, email, and exports.

**Likely files:** `pipeline/reported.py`, `pipeline/build.py`, `web/app.js`, `pipeline/notify.py`.

**Acceptance:** The panel explains the difference numerically. A trend does not silently combine incompatible definitions.

## U09 — Strengthen disclosure comparison and coverage

**Proposed changes**

- Extend existing comparison views with explicit report-period and filing-date selection.
- Treat amendments, security identifiers, share classes, and put/call positions explicitly.
- Show share changes, reported-value changes, and weight changes as different measures.
- Distinguish a missing/unprocessed report from a verified position exit.
- Keep reviewed officials' records separate from unreviewed OCR candidates.
- Display mapping coverage and unmatched securities in ticker-based reverse lookups.
- Label price-based cost estimates as estimates.

**Likely files:** `disclosures/app/holdings13f/`, disclosure UI/data payloads, `stage-public.py`.

**Acceptance:** An apparent exit requires sufficient comparable report coverage. Reverse lookups disclose unresolved mappings and never imply complete institutional ownership.

## U10 — Audit delivery and publishing outcomes

**Observed basis:** Delivery state, request queues, and posting state already exist. These should be examined and extended before adding a replacement queue.

**Proposed changes**

- Review duplicate protection across email, Buffer, and direct publishing separately.
- Define idempotency identifiers using recipient/channel, company, period, version, and report/post kind as appropriate.
- Record prepared, submitted, confirmed, failed, and uncertain outcomes.
- Handle timeouts where an external service may have accepted an action before the local process stopped.
- Add an owner view for failed requests and retry eligibility.
- Keep core financial figures sourced from structured data when model wording is used.

**Likely files:** `pipeline/notify.py`, `pipeline/social.py`, `pipeline/buffer.py`, `pipeline/custom.py`, Supabase schema if needed.

**Acceptance:** A retry does not automatically duplicate a confirmed action. Uncertain outcomes are visible and follow a documented recovery path. Automated tests use mocked services.

## U11 — Add balance-sheet and cash-flow statement views

**Proposed expansion**

- Balance sheet: assets versus liabilities/equity, with current/noncurrent detail where reliable.
- Cash flow: beginning-to-ending cash bridge, operating cash-flow construction, and FCF reconciliation.
- Additional bridges: PP&E, net debt, and retained earnings only where source coverage supports reconciliation.

Start with an agreed financial schema and fixtures across several industries. Balance-sheet instants differ from duration facts used in the current earnings extraction. Resolve consolidated versus attributable equity, restricted cash, acquisitions, FX, and noncash changes before claiming reconciliation.

**Likely files:** New extraction/model/view modules, plus existing company pages and source infrastructure.

**Acceptance:** Each bridge reconciles to explicitly identified statement totals or shows an explained residual. Missing components are not silently filled with zero. A separate view avoids overloading the earnings Sankey.

## U12 — Measure storage growth before migration

**Observed basis:** Earnings state is rewritten on a data branch, while disclosure snapshots and shards are committed to main. These different persistence patterns merit separate measurement.

**Proposed changes**

- Measure clone size, snapshot size, file counts, commit growth, build duration, and browser transfer size.
- Define retention rules for caches, evidence, versions, and derived artifacts.
- Continue lazy-loading catalogs/history where appropriate.
- Evaluate compressed static shards or object storage when measured limits justify the change.
- Keep public data URLs and recoverable backups stable during any migration.

**Acceptance:** A storage decision includes measured bottlenecks, expected cost, a migration plan, and rollback. No migration is required simply to complete the earlier updates.

## Suggested implementation sequence

1. **First release:** U01, U02, and the basic freshness manifest from U03.
2. **Financial trust:** U04 and U08, with a compatible store migration.
3. **Reading experience:** U05 and U06, using representative fixture charts.
4. **Operational reliability:** Complete U03, U07, and U10.
5. **Research depth:** U09, followed by U11 when the financial schema is ready.
6. **Scale:** U12 based on measured growth.

For the next code change, my recommendation is **U02 plus the basic part of U03**: establish a repeatable offline quality gate and expose where updates are waiting. This supports later financial and visual work without a broad rewrite.

## Review limits

These recommendations are based on source reading, not a fresh production audit or executed benchmark. Provider availability, deployed database state, actual delivery success, complete data coverage, and current live-chart appearance remain unverified. Implementation should begin by checking the relevant current files and reproducing the specific behavior with fixtures.
