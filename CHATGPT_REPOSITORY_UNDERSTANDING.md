# ChatGPT's Understanding of the Filing Flows Repository

> Author: ChatGPT (OpenAI)  
> Review date: October 15, 2026 (Asia/Shanghai)  
> Repository and branch: `eurikamonica/filing-flows`, `main`  
> Main commit observed during the review: `a57ea80e29fcc6e83c093522577a1eade75e655e`  
> Status: An architectural and functional interpretation based on reading repository files. This is not the repository author's official specification, a complete audit, or a production acceptance report. Automated data commits occur in this repository; this review is not an exhaustive inspection of every file at one pinned commit.
>
> Change scope: This task added this Markdown document and then translated it into English. Existing code, configuration, workflows, data, the original README, and other files are unchanged by these documentation commits.

## 1. Overall understanding

Filing Flows is a system for acquiring SEC disclosures, parsing them with rules, normalizing financial definitions, producing traceable visualizations, and distributing subscription reports. The browser primarily consumes generated static JSON. Python and GitHub Actions handle SEC access, chart generation, email processing, and social publishing. Supabase optionally provides accounts, preferences, and request queues.

The current repository extends beyond the original earnings Sankey website. It includes the Disclosure Hub, an Android client, email subscriptions, owner reports, X/Buffer publishing, and engagement tools. The current main website uses plain JavaScript, HTML, and CSS, with a Python data pipeline. Earlier FastAPI/React designs should not be assumed to describe this implementation.

Its central value is turning financial data from different companies, tags, and reporting periods into consistent charts while retaining sources, calculation methods, checks, and choices of financial definition.

## 2. Directories and responsibilities

| Location | My understanding of its responsibility |
| --- | --- |
| `pipeline/build.py` | Orchestration, state storage, filing processing, history backfill, rereads, time budgets, and website data generation |
| `pipeline/sec.py`, `pipeline/scan.py` | SEC access and discovery through recent filings and historical daily indexes |
| `pipeline/facts.py` | Companyfacts tag mapping, quarterly/annual values, YTD differencing, and period selection |
| `pipeline/dims.py` | Product and business-segment revenue from filing XBRL instances and label files |
| `pipeline/release.py` | Earnings-release tables in 8-K filings and preliminary financial data |
| `pipeline/reported.py` | Company-reported FCF reconciliation, chart eligibility, definitions, and fallback explanations |
| `pipeline/model.py` | Normalization into a consistent income-statement and cash-flow structure |
| `pipeline/sankey.py` | Chart specifications containing financial nodes, links, and comparison values |
| `pipeline/checks.py`, `pipeline/sources.py` | Data checks and explanations of where individual figures come from |
| `pipeline/text.py`, `pipeline/analysis.py` | Filing text extraction and rule-generated analysis |
| `web/app.js` | Pages, routing, search, accounts, preferences, comparison requests, and owner tools |
| `web/sankey.js` | Chart layout and a drawing scene shared by SVG interaction and exports |
| `web/styles.css`, `web/index.html` | Website styling and page shell |
| `scripts/build_site.py`, `scripts/seo.py` | Static assembly, public configuration, search-engine pages, and domain files |
| `pipeline/custom.py` | Asynchronous requests for company builds, historical comparisons, and rereads |
| `pipeline/notify.py`, `pipeline/owner.py` | Reader notifications and owner reports |
| `pipeline/social.py`, `pipeline/tweet.py`, `pipeline/buffer.py`, `pipeline/engage.py` | Posts, images, model-assisted writing, Buffer queues, and engagement content |
| `config/` | Starred companies, publishing settings, and writing guides |
| `supabase/schema.sql` | Account tables, RLS, request limits, and optional workflow wake-ups |
| `disclosures/` | Integrated holdings, official disclosures, and other market/public-data modules |
| `android/` | Android project; the manifest includes main/chart activities, notification permissions, and link handling |
| `tests/` | Offline pipeline tests, fixtures, and Playwright end-to-end checks |
| `.github/workflows/` | Workflow definitions recognized and executed by GitHub Actions |

The root also contains `scan.py`, `sec.py`, and several YAML files. Actual execution should be traced through the `pipeline.*` modules and `.github/workflows/*.yml` files that workflows invoke. Similarly named root files do not automatically become execution entry points.

## 3. From an SEC filing to a website chart

1. `pipeline.scan` discovers 10-Q, 10-K, and 8-K filings. The earnings path for 8-K focuses on earnings releases; it does not turn every 8-K into a quarterly income chart.
2. `build.py` uses accession numbers, processed state, and pending retries to select work, then reads submissions, companyfacts, and necessary filing documents.
3. `facts.py` extracts non-dimensional amounts. `dims.py` adds product/segment data from instances. `release.py` handles release tables.
4. `model.normalize()` standardizes the financial structure, derives necessary residuals or missing items, and records flags.
5. `sankey.py` creates chart specifications, combined with sources, checks, comparisons, and explanatory text for website data.
6. `scripts/build_site.py` assembles `web/` and generated data; `stage-public.py` adds the disclosure site.
7. Actions deploys Pages. Reader notifications and Buffer queue processing run under their own conditions.

This architecture combines scheduled batch processing, incremental storage, and static publishing. Automatic updates after new filings do not imply a second-by-second market feed. GitHub queues, SEC companyfacts latency, batch budgets, and deployment time affect when readers see updates.

### State and publication are separate

- `main` holds source code and data committed by the disclosure module.
- The earnings pipeline stores state such as `store/state.json` and `store/companies/{CIK}.json` on the `data` branch, restored and saved by the scanning workflow.
- `_site/` is a build output supplied to the Pages artifact and deployment jobs.
- When `SELF_HOST` is enabled, built files can also be pushed to the `site` branch.
- `media` is used by social-image publishing and is distinct from the financial state branch.

The presence or absence of fresh earnings JSON on main alone does not establish whether earnings collection succeeded. Disclosure storage and earnings-pipeline storage follow different paths.

## 4. Financial definitions and parsing rules

### 4.1 Quarterly values may require cumulative differencing

`facts.py` first looks for quarterly durations. When only cumulative values are available, it attempts differences between cumulative periods with the same start date:

```text
Q2 = First six months − First quarter
Q3 = First nine months − First six months
Q4 = Full year − First nine months
```

The code matches quarterly and annual durations using day ranges, including 52/53-week fiscal years. Fiscal quarters should therefore be distinguished from calendar quarters. Industry aggregation has its own calendar-quarter grouping rule.

The companyfacts index retains the more recently filed fact for the same period. This can incorporate later updates, but historical charts may consequently differ from what was first disclosed at the time. This review does not establish that the repository is a point-in-time backtesting database.

### 4.2 Revenue tags have selection priorities

Companies use different revenue tags. `facts.CONCEPTS` lists candidates, with rules beyond simply taking the largest number:

- When available, `Revenues` takes priority as total income-statement revenue.
- Without that tag, the applicable candidate-selection rules are used.
- Revenue from customer contracts can differ from total revenue, for example when other revenues include net losses.
- Product/segment lines are checked against totals; the partition tolerance in `dims.py` is 0.4%.
- Lines matching contract revenue, or matching neither total, receive different reconciliation and display treatment.

This is a general adaptation mechanism, rather than a fixed product list copied from one company.

### 4.3 Income and cash-flow bridges

`model.py` explicitly implements:

```text
Net non-operating income = Pretax income − Operating income
Calculated FCF = Operating cash flow − Capital expenditures
```

The system also handles gross-profit paths, operating-cost breakdowns, noncontrolling interests, tax benefits, losses, and the bridge from earnings to operating cash flow.

Some missing or inconsistent amounts are derived using accounting identities and flagged. Overlapping expense tags can cause a fallback to aggregate costs. A chart node is therefore not necessarily a separately reported line item. In particular, the residual cash-flow adjustment should not automatically be interpreted entirely as working-capital changes.

Sankey bands use nonnegative widths to represent signed economic values. Losses, negative operating cash flow, and capex exceeding OCF are represented through dedicated nodes or flow directions. Labels, signs, and explanations are essential to interpretation.

### 4.4 Company-reported FCF and calculated FCF are distinct

`reported.py` reads company FCF reconciliations from earnings releases. Acceptance requires the relevant OCF to match the SEC quarterly figure and the reconciliation to add up. When eligible, the chart can use the company's definition. Otherwise, it retains the calculated definition and explains the company's figure or the fallback reason.

Company definitions may deduct finance-lease principal or adjust capex for asset sales and government incentives. Such differences are not automatically calculation errors.

The account preference `fcf_basis` has three choices:

| Value | My understanding |
| --- | --- |
| `company` | Prefer the company definition; fall back to calculation when unavailable |
| `noted` | Prefer the company definition and explicitly explain why it could not be used |
| `ocf` | Use the calculated definition while retaining relevant company-definition information |

The calculated view may also affect revenue-line reconciliation, beyond FCF alone. Current documentation and build logic distinguish annual FCF treatment from quarterly company-reported treatment.

## 5. Charts and frontend

The main site uses hash routes for companies, fiscal years, sectors, accounts, and owner tools. Its current frontend is plain JavaScript.

Python determines financial semantics, nodes, and links. `web/sankey.js` determines layout and drawing. Screen SVG and PNG/JPG/PDF exports share a scene representation, allowing screen-only interaction markers to be excluded from exports.

Features visible in the reviewed implementation include:

- Standard, quarter-over-quarter, and year-over-year charts, with dark growth strips and optional decrease hatching.
- Node-level historical trends, source citations, and filing-text explanations.
- Quarterly/annual switching and sector/industry aggregation.
- Optional drag/zoom, PNG/JPG/PDF export, and theme preferences.
- Requests to build previously unavailable companies and compare two periods of the same type.
- Company-page holdings information generated by the disclosure module.

Requested historical comparisons require backend work to read SEC data and generate results. The browser button does not perform the entire SEC retrieval process locally.

## 6. Accounts, notifications, and permissions

Supabase is optional. With it configured, readers can sign in using an email code, save follows and display preferences, request reports, and manage email delivery.

`schema.sql` defines tables and associated functions for `subscriptions`, `deliveries`, `send_requests`, `chart_requests`, `company_requests`, `reread_requests`, `site_owners`, and `owner_settings`.

Authorization is intended to rely on database RLS, authenticated identity, and owner verification. Hiding frontend buttons alone is insufficient. The public anon key and server-side service key have different purposes; the latter is supplied through workflow environments. This review did not read secrets or verify whether the deployed database has applied the current schema.

Reader alerts, owner reports, on-demand reports, and social posts are separate jobs. Their code being present does not establish that SMTP, Supabase, Buffer, or model providers are currently configured successfully.

## 7. Disclosure Hub in the current repository

The beginning of `disclosures/README.md` explicitly states that this module now lives in the original repository and is published at `/disclosures/`. The current structure therefore includes an integrated disclosure subsystem.

It contains 13F holdings, officials' disclosures, COT, FDIC bank data, and N-PX, with additional entry points for price estimates, market views, Form 4 insiders, and options. The officials workflow includes PDF/OCR extraction, candidates, and human review. A collector's presence does not establish complete coverage of every jurisdiction, person, or historical period.

`stage-public.py`:

- Adds the disclosure static site to the main build.
- Excludes collector-only caches and queue state.
- Generates a ticker-based holders index for earnings company pages.

Each dataset retains its own meaning: 13F describes reported holdings, officials' disclosures can use value ranges, estimated prices are not execution prices, COT describes trader categories, bank entities may differ from listed holding companies, and N-PX describes voting disclosures. Sources, reporting periods, processing progress, and review status should guide interpretation.

The disclosure README retains older standalone-package text, including statements that the original repository was unchanged or that some state-level automation was unimplemented. Its integration notes and current implementation should be consulted when interpreting those historical statements.

## 8. Automation entry points

The following reflects reviewed workflow definitions. Cron times use UTC; configured frequency does not guarantee completion times.

| Workflow | Purpose |
| --- | --- |
| `scan.yml` | Scans, builds, and deploys at minutes 4/19/34/49; supports manual and dispatch triggers; conditionally notifies readers and queues Buffer posts after deployment |
| `disclosures.yml` | Holdings at minutes 7/22/37/52; congress hourly at :17; markets at :43 in most hours and all modules at 10:43; insiders at :28/:58; options at 21:20 on weekdays |
| `requests.yml` | Reader-request workflow entry point |
| `email-thread.yml`, `mail-test.yml` | Separate email-thread and email-test entry points |
| `post-to-x.yml`, `engage.yml`, `movers.yml` | Separate social publishing, engagement, and market-mover entry points |
| `android.yml` | Android build entry point |

The disclosure collector commits `disclosures/docs/data/` to main; the earnings scan incorporates the disclosure site into publication. These are separate operations, so successful collection and publication of fresh data should be evaluated separately.

`scan.yml` uses Python 3.11, while `disclosures.yml` uses Python 3.12. The earnings pipeline enforces a run budget, distributing backfills, rereads, and new filings across runs.

## 9. Rules and language-model boundaries

Financial extraction, normalization, Sankey construction, and regular analysis paragraphs are primarily implemented through fixed rules.

The entire repository cannot be described as having no language-model usage. `pipeline/tweet.py` explicitly supports model-written posts using guides, figures, and filing excerpts. It checks properties such as length and cashtags and can fall back to rule-based wording. Provider availability depends on actual credentials and interfaces, which were not tested here.

My understanding is that models can assist distribution content while the financial pipeline supplies the core figures. The README's broad no-language-model statement should be interpreted in the context of the relevant financial-analysis path rather than applied to every module.

## 10. Review scope, limitations, and reading order

This review inspected root and major directory listings, READMEs, and key files covering earnings orchestration, value extraction and normalization, dimensions, company FCF, checks and source-related entry points, frontend behavior, static assembly, Supabase schema, scan/disclosure workflows, disclosure collection and publication integration, model-assisted posts, and test structure.

This review did not:

- Execute SEC collection, the full test suite, or browser end-to-end tests.
- Verify the accuracy of every company chart currently online.
- Read private configuration or send email, publish posts, or manually trigger workflows.
- Fully audit Android, every disclosure collector, or every third-party interface.
- Check every record or coverage statistic on the data branch or disclosure snapshots.

The repository contains offline financial tests, simulated endpoints, Playwright checks, and disclosure tests. Their presence establishes that checks are defined; this review does not claim they all currently pass.

For future maintenance, I would begin with `build.py → facts.py/dims.py/release.py → model.py/reported.py → sankey.py → web/sankey.js/app.js`, then follow requests, notifications, or disclosures for the specific feature involved.

My overall interpretation is that Filing Flows centers on a financial visualization pipeline with source and definition constraints. The static site presents its output, Supabase coordinates accounts and requests, Actions executes and publishes jobs, and the Disclosure Hub and distribution tools extend research and delivery around the same companies and securities.
