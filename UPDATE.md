# Filing Flows — Update Record and Feature Roadmap

> Author: ChatGPT (OpenAI)  
> Date: October 15, 2026  
> Status: Source-verified progress plus proposed work; this document implements no runtime features.  
> Basis: The repository review summarized in [CHATGPT_REPOSITORY_UNDERSTANDING.md](CHATGPT_REPOSITORY_UNDERSTANDING.md), with the current root listing and scan/request workflows checked again when preparing this file.  
> Scope: This refresh modifies only `UPDATE.md`. Existing code, configuration, workflows and other documentation remain unchanged.


## October 15 update — Current implementation and revised roadmap

Prepared by **ChatGPT (OpenAI)**. This section supersedes the original implementation order below where they differ. It records source-level observations and proposals separately.

### Verified repository changes

Review baseline: main commit [66d4c882](https://github.com/eurikamonica/filing-flows/commit/66d4c882c3d0c70663dccb8cdc6f4b92c1db6703).

| Area | Observed change | Status and limits |
| --- | --- | --- |
| Rotation visualization | [1933ba02](https://github.com/eurikamonica/filing-flows/commit/1933ba026aa52911465a187a6437873fbd8a25fd) adds a rotatable 3-D canvas, monthly price-derived observations over 48 complete months, signed-log/rank/standard-score scales and smoothing. | Implemented in main source. Quarterly fundamentals interpolated into monthly views are not monthly reported fundamentals. No fresh browser or production-data validation is claimed here. |
| SEO company pages | [1f3e415f](https://github.com/eurikamonica/filing-flows/commit/1f3e415f050df245c4ffe93133e4586913dab221) embeds the latest-quarter Sankey using the shared renderer and adds a wider chart container. | Implemented in main source. The chart is drawn with JavaScript; a table and noscript explanation remain. Repository implementation does not establish search indexing or deployment of this exact commit. |
| Disclosure snapshots | Recent main commits refresh disclosure data and source status. | A collection commit is not evidence that all sources succeeded or that the identical snapshot is already published. |
| Advanced FSA workbench | [Separate Beta branch](https://github.com/eurikamonica/filing-flows/tree/beta/fsa-chatgpt/fsa-beta) contains reserve rollforwards, accruals, operating/financing reformulation, reconciliation and earnings-quality explanations. | Isolated local implementation; not integrated into the production site. Inputs still require supported structured data and reviewed classifications. |
| Optional Gemini explanations | Beta includes server-side configuration, caching, call limits and evidence-ID validation. | Mock-tested only. Live quota, billing and response quality have not been validated. |
| Local AI training | Beta includes synthetic-data generation, a topic classifier and optional Qwen LoRA training/evaluation scripts. | The classifier is not a generative financial model. No LLM adapter training or measured accuracy improvement has occurred. |
| Model acquisition | Qwen3-0.6B weights and tokenizer were downloaded in the assistant work environment; the weight SHA-256 was checked. | Not installed on the user's laptop. A persistent package-save attempt failed. Weights are not committed to this repository. |

The Beta [validation record](https://github.com/eurikamonica/filing-flows/blob/beta/fsa-chatgpt/fsa-beta/VALIDATION.md) records 23 passing unit/HTTP tests, Python compilation and JavaScript syntax checks. Browser rendering, live Gemini calls and LoRA execution remain unverified. Its earlier statement that weights were not installed describes that validation run; the later download above does not establish a successful ML runtime.

### Revised implementation order

1. **Trust and reproducibility:** retain U02–U04; add explicit observed/interpolated/revised labels to the new rotation views.
2. **Useful FSA output:** implement B01–B03 below against reviewed English examples before expanding model size.
3. **Local training:** implement B04–B05; compare the unmodified model with the adapter on a locked test set.
4. **Website delivery:** implement B06 as a separate static Beta artifact. No always-on GPU is necessary for precomputed analysis.
5. **User experience and discovery:** implement B07–B09, extending the existing charts and SEO pages.
6. **Optional interactive AI:** B10 only after measured demand and reliability justify a hosted inference backend.

### New feature recommendations

| ID | Priority | Proposed feature | Concrete deliverable |
| --- | --- | --- | --- |
| B01 | P0 | Evidence-backed English filing extraction | Financial values with period, unit, source accession, excerpt and review status |
| B02 | P0 | Reserve movement and earnings-quality workbench | Reconciled rollforwards, release classification and explicit unresolved differences |
| B03 | P1 | Auditable statement reformulation | Editable operating/financing mapping, NOA/NFO/NOPAT/RNOA and bridges |
| B04 | P0 | Laptop training preflight and smoke run | GPU/VRAM/dependency/disk check, bounded training run and measured resource report |
| B05 | P0 | Financial evaluation and model registry | Locked company/year holdouts, baseline comparison and versioned adapter metadata |
| B06 | P1 | Local analysis to static Beta publishing | Versioned JSON manifest, validation gate, review status and rollback |
| B07 | P1 | Rotation methodology and data-availability controls | Reported versus interpolated values, benchmark coverage and availability-date mode |
| B08 | P1 | SEO and shareable research pages | Indexing diagnostics, accessible chart/table consistency and stable share links |
| B09 | P2 | Comparable earnings-quality history | Definition-consistent trends and explainable review flags |
| B10 | P2 | Optional cited filing Q&A | Retrieval-backed English answers through an authenticated inference backend |

### B01–B03 — Financial analysis that can be inspected

**B01: Extraction.** Read a bounded filing section or table rather than an entire 10-K in a small-model prompt. Produce English JSON containing company/CIK, accession, statement period boundaries, fiscal period, currency, scale, reported label, normalized concept, value and source excerpt. Missing information must remain null with a reason. Treat documents as evidence, not instructions to the model.

Acceptance: a reviewed fixture set checks exact amounts, signs, units, periods and source alignment. The interface distinguishes reported facts, derived calculations and generated interpretation. A valid source identifier alone is not proof that an explanation is supported.

**B02: Reserves.** Extend the existing Beta rollforward to allowance for credit losses, warranties, inventory allowances and restructuring provisions using category-specific schemas. Separate additions, releases, utilization, acquisitions/FX and other movements. Check:

`closing = opening + additions - releases - utilization + other`

Do not assume every decline is an income-statement benefit: utilization can reduce a reserve without increasing profit. A release-benefit claim needs explicit evidence of its accounting treatment. Do not equate a reconciled reserve with an adequate reserve or describe a flag as proof of a cookie-jar practice.

Acceptance: the bridge reconciles within a disclosed rounding tolerance or displays a residual; unsupported profit effects remain unresolved.

**B03: Reformulation.** Provide reviewed operating/financing classifications and an adjustment ledger. Record tax assumptions, leases, pensions, excess cash and noncontrolling interests explicitly. Use consistent opening/closing balances and distinguish annual, quarterly and trailing-period returns.

Acceptance: displayed totals reconcile to the source statements and each adjustment is reversible and sourced. Banks and insurers require separate treatment rather than the default industrial-company mapping.

### B04–B05 — Train locally, measure before upgrading

The current hardware information is incomplete: the user reported an RTX 3050 and 32 GB system RAM, while the supplied Windows summary displays 8 GB graphics memory and multiple GPUs without identifying the NVIDIA model. Confirm dedicated VRAM with:

`nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv`

Do not treat system/shared memory as CUDA VRAM. The screenshot also indicates approximately 42 GB of remaining disk space; avoid duplicate model downloads and retain only a small number of checkpoints. Do not publish device identifiers.

**B04 proposed starting experiment:** Qwen3-0.6B, English extraction examples, sequence length 512 including input and output, microbatch 1, gradient accumulation 16, LoRA rank 8, gradient checkpointing and training KV cache disabled. Consider 4-bit QLoRA where dependencies and hardware support it. These are starting settings, not a measured fit guarantee. Run 20–50 steps and record peak VRAM, step time, loss and free disk before expanding. Confirm training targets are not truncated.

Advance to Qwen3-1.7B only after baseline measurements. The English project does not need multiple simultaneously loaded models. Separate models can review shared evidence sequentially; adapters cannot be assumed portable between architectures.

**B05 evaluation:** split by company and time, keep related filings/amendments together and prevent synthetic template/entity leakage. Evaluate schema validity, exact numeric extraction, unit/period correctness, source support, appropriate abstention and formula reconciliation separately. Compare the base model, fine-tuned model and deterministic baseline where applicable. Report denominators and errors, not only one aggregate accuracy score.

Store base-model revision, adapter version, training-data version, settings and evaluation report together. Model weights and caches belong outside normal Git history. The existing synthetic examples are a pipeline test, not sufficient evidence of real-filing quality. Additional human-reviewed real examples are required.

### B06 — Local analysis to the website without an always-on GPU

Proposed flow: local filing preparation → model extraction → deterministic calculations → validation/review → static JSON export → separate Beta site build.

Define a versioned artifact containing source accessions, financial period, source availability time, generation time, model/adapter version, checks, review status and explanations. Generate outputs in a temporary directory and publish an immutable manifest only after all required files validate. Keep the last good version for rollback. Failed runs must not replace valid data with empty output.

Acceptance: a user can open a precomputed analysis while the training computer is off. A new analysis requires another processing/publishing run. Store runtime, data and publishing configuration separately from production. This document does not add a deployment workflow or authorize an automatic merge of Beta code into main.

### B07 — Make new rotation views interpretable

- Show separate dates for fiscal period end, filing availability and market observation.
- Label interpolated quarterly values visibly; offer reported-points-only and last-known-value modes.
- Use availability timestamps for research/backtest views. Smooth chart paths are not evidence that a future filing was knowable earlier.
- Document whether scaling, clipping, volume baselines and universe selection use full-history information; use past-only fitting for predictive evaluation.
- Review the new monthly relative-return fallback: the inspected implementation can subtract zero when SPY data is unavailable. Prefer null plus a coverage reason for a metric labeled “versus S&P 500,” rather than silently displaying raw return.
- Keep exploratory axis scans distinct from out-of-sample validation; record the number of tested combinations and use chronological evaluation.
- Add keyboard/table alternatives and reduced-motion controls for 3-D and animated views.

Acceptance: a synthetic late-filing fixture cannot influence an earlier availability-date view; missing benchmark observations cannot masquerade as relative returns. These are proposed checks, not an executed audit of the new charts.

### B08–B10 — Discovery, comparison and optional questions

**B08:** extend existing SEO rather than rebuilding it. Verify generated company-page canonical URLs, sitemap membership, HTTP status and visible table/chart consistency. Ensure the static heading and table use the same financial snapshot as the dynamically fetched chart, or disclose a version mismatch. Inspect Search Console separately for indexing; HTTP 200 does not prove indexing. Add stable links encoding company, period and selected definition, plus source-bearing exports. Public Beta pages should be deliberately included or excluded from indexing according to their readiness.

**B09:** add comparable historical accruals, cash conversion and reserve movements with metric definitions and sector context. Distinguish rule-triggered review flags from calibrated probabilities. Do not combine incompatible periods or definitions into a single score. Start with explainable individual measures before considering a composite earnings-quality score.

**B10:** when interactive Q&A is justified, retrieve the relevant filing passages and send them to a separately hosted model backend. Keep numeric calculations in the engine and cite the selected filing version. Include authentication where appropriate, request limits and latency measurement. A static website cannot itself keep a server-side API secret or run a Python inference server.

Gemini remains an optional explanation provider. Verify current provider quota and terms before use; local request limits do not guarantee free billing. The current Beta excludes Gemini outputs from training. Do not assume a free tier or personal use automatically permits distillation.

### Recommended next deliverable

Build **one end-to-end, reviewed English reserve-analysis example**: source excerpt → structured extraction → reconciliation → short explanation → static Beta JSON/page. Then evaluate the same workflow on held-out companies before scaling the model or adding more providers.

### Scope of this documentation refresh

Only the root `UPDATE.md` is changed. Existing production code, data, workflows and the Beta branch are not modified by this refresh. Earlier U01–U12 recommendations below are retained as a backlog; their observations reflect the earlier review and must be rechecked before implementation.

## Earlier roadmap — retained backlog

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
