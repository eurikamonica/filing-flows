# Spin Sankey Flo — Academy, Detective & SEC Case Studies

**Implementation:** `web/flo-academy.js` (standalone deterministic module) integrated with existing `web/mascot.js`, `web/app.js` Sankey node evidence panels and `web/index.html`. This PR does **not** replace Flo's SVG, eye-follow animations, color palette, local companion model or existing valuation/filing/option routers.

## Already implemented in Phase 1

| Feature | User entry | Real implementation |
|---|---|---|
| Flo Academy | Flo panel → Learn DCF, or "teach NVDA DCF step by step" | Seven-step stateful bilingual tutorial; Next/Previous/Stop and step-2 working FCFF form |
| SEC company context | From any company page / ticker | Latest processed filing date, *reported* operating income and cash-from-operations as **context**; original verified SEC URL; NEVER invents D&A/CapEx/working capital |
| Interactive FCFF | Learn DCF → Step 2 | User inputs EBIT, tax %, D&A, CapEx, change in operating NWC; calculates EBIT(1−T)+D&A−CapEx−ΔNWC with numeric validation |
| Cookie Jar Detective | "NVDA cookie jar" | Reads `data/c/{cik}.json.quality.reserves`, displays by-family latest balance/amount of releases and release/opening ratio, links to original Profit & Cash reserve waterfall |
| Reserve lab | "cookie jar simulation" | Add provision, use/settle, release a liability reserve; correctly separates P&L effect and immediate cash effect |
| Supplier rebate lab | "supplier rebate exercise" | Allocate a *hypothetical* purchasing rebate between already-sold units (COGS reduction) and unsold units (inventory cost reduction) |
| SEC cases | "Sunbeam case study", "Dell case study" | Curated historically sourced enforcement material with direct official SEC URLs and guided questions |
| Explain this number | Sankey node → "Ask Flo · explain this number" | Passes exact selected node label, reporting period, company CIK and original source URL to the *same* Spin Sankey Flo; explains recognized formula without inventing amounts |
| New mode shortcuts | Existing Flo panel | Learn DCF, Cookie Jar, SEC cases, Rebate lab beside the rotating suggested questions |

No new external AI service, subscription API, server endpoint, token, new mascot or backend collector is required. The module uses cached original source data already published by the site.

## P0 scope and accounting safeguards

- **Never** infer or accuse fraud from a reserve release ratio; it is a *screening lead*. A missing standardized rollforward is **unknown**, not "no fraud" or "zero".
- The short DCF lesson is a **teaching sequence**, not a published valuation for NVIDIA. EBIT is proxied by operating income *conditionally*, and reported operating cash flow is **not FCFF**. A tax-rate assumption is explicitly labeled as such; the 100/20%/8/12/5 = 71 exercise is hypothetical.
- Case studies are historical enforcement findings, not accusations against the currently selected company. Primary sources:
  - Sunbeam: https://www.sec.gov/enforcement-litigation/administrative-proceedings/33-7976 (SEC order; $35M 1996 improper reserves and supplier rebate deferrals).
  - Dell: https://www.sec.gov/newsroom/press-releases/2010-131-sec-charges-dell-senior-executives-disclosure-accounting-fraud (SEC press release; Intel exclusivity payments peaking at 76% of operating income in FY2007 Q1 and accounting allegations).
- A purchaser's cash receipt of a rebate does **not** mean immediate profit. The lab assumes a rebate reducing purchase price and earned under contractual terms; actual recognition needs contract analysis. The source case demonstrates why timing matters.
- Form actions validate numeric input locally; all dynamic user/issuer text is HTML-escaped and only SEC-hosted filing URLs are used in new evidence cards.
- UI includes bilingual prompt recognition and bilingual lesson/case text; full multilingual form-label translation is future scope.

## Architectural design

```
Sankey node click → original evidence drawer → [Ask Flo]
                                          ↘ FFMascot.explain({cik, label, period, docUrl})
Flo quick modes / typed question → mascot.js route → FFFloAcademy.match / handle
                                          ↘ source data/c/{cik}.json → quality.reserves
                                          ↘ SEC primary-source case registry
                                          ↘ FCFF / reserve / rebate exercise (local deterministic math)
```

`web/mascot.js` retains the controller; `web/flo-academy.js` handles specialized lesson/case/reconciliation calculations to prevent further inflating the mascot's routing script. Existing Flo question bank and legacy tests are retained.

## What is intentionally NOT implemented

This PR does **not** implement autonomous SEC footnote retrieval or full-text search, a probabilistic accounting-fraud model, multi-period same-company reserve forensic inference, a complete 3-statement model, editable forward-year DCF table, WACC calibration or research-note export. These require a validated normalized data API, additional source metadata and structured state. It does not deploy itself before merge.

## Verification and rollout

1. Run `node tests/test_mascot.cjs` (legacy routing) and `node tests/test_flo_academy.cjs` (new exercises / provenance / missing data), plus syntax check of `web/flo-academy.js`, `web/mascot.js`, `web/app.js`.
2. On a company page, click a Sankey node, then **Ask Flo** in its evidence drawer. Confirm the right CIK/period/source is shown and the Flo dialogue opens.
3. Run `teach NVDA DCF step by step`: step 2 must show only *actually published* NVIDIA EBIT-proxy and OCF, while other inputs are labeled a fictional exercise.
4. Check a company with no tagged reserves: Flo must say **insufficient** rather than "no cookie jar".
5. Test manual reserve release: profit changes, cash stays constant; use: cash changes, profit does not change a second time.
6. Confirm clicking old Valuation/RRG/Options questions still routes to their pre-existing handlers.
7. Merge PR → rebuild standard Pages site, then smoke-test desktop/mobile Flo overlay. A draft PR alone does not update the site.

## Later phases

- P1: editable 5-year DCF scenario panel, model provenance and save/export, chart-node value derivation with per-fact XBRL accession, teaching-progress storage.
- P2: per-company quality detective with peer-normalized accrual and reserves, financial restatement history and citation cards; contract-aware rebate and Hidden Leverage labs; research-notebook integration.


## Phase 1 extension — Flo Spreadsheet Lab (Excel-style practice)

**Entry:** Flo quick mode "Spreadsheet Lab / Excel 模拟练习", or type "open Excel modeling lab", "three-statement spreadsheet practice" or "模拟 Excel".

**Delivered:** an interactive worksheet inside the SAME existing Spin Sankey Flo panel, using an expanded responsive desktop overlay and horizontally scrollable grid on mobile. This is a browser-based teaching simulator, NOT Microsoft Excel, and it does NOT create or import true XLSX files.

| Worksheet | Training outputs |
| --- | --- |
| Five-year DCF / FCFF | Revenue projections, EBIT, cash tax, depreciation, capital expenditure, changes in operating NWC, FCFF, discounted cash flow, Gordon terminal value, EV-to-equity and per-share value |
| Integrated three statements | EBIT, pretax/net income, indirect CFO, CFI, CFF, cash, PP&E, accounts receivable, inventory, payables, debt, retained equity, BS reconciliation |
| Trading comparable valuation | Peer EV/EBITDA ratios, peer median, target implied EV, net debt, diluted shares, estimated target equity/share |
| Dividend discount (DDM) | Five years of dividends, discounted payouts, perpetual terminal equity price, intrinsic price |
| DuPont ROE | Net margin, asset turnover, leverage multiplier, ROE and direct ROE reconciliation |
| Reserve rollforward | Provision, releases, utilization, other changes, reported closing, release/opening and balance-gap reconciliation |

**Real practice functions:** blue assumption cells, purple formula exercise cells, choose any cell, edit the formula bar, and recalculate automatically when submitted. Learners can switch to scenarios (Base, Bull, Bear / case-specific stress), use Hint, reveal formulas, Check work, reset each workbook, and export **calculated values** to CSV. In practice mode required formula cells are blank. The grader compares learner-computed results with a distinct instructor formula graph under the currently edited assumptions and requires a formula rather than a hardcoded static number.

**Formula support:** numeric values and bounded A1 cell references, absolute $B$16 references, ranges, +, -, *, /, exponentiation, parentheses, and SUM / AVERAGE / MEDIAN / MIN / MAX. Safe bounded parser, no eval, macros, arbitrary JavaScript, external functions or user-provided HTML. Cycle, invalid-reference, unsupported-function and zero-division errors are explicit. Valuation assumptions reject Gordon terminal calculation when WACC <= g or cost of equity <= g.

**Accounting guardrails:** all starter values in all six workbooks are **HYPOTHETICAL DATA ONLY**, not an issuer's SEC figures. The simplified 3-statement model omits dividends, restructuring, acquisitions and nonstandard transactions. Automated grading validates model calculations, not economic realism, accounting compliance or investment suitability. Formula CSV export is deliberately not implemented; computed values only, with a hypothetical-data heading.

**Implementation files:** web/flo-workbook.js, web/mascot.js, web/index.html, tests/test_flo_workbook.cjs; existing and fast Flo regression workflows include the new tests. The earlier SEC-backed company analysis and separate Academy tutorial remain unchanged.

**Future extensions:** save/restore custom workbook progress, import/export actual XLSX, multi-sheet intercompany schedules, historical SEC reconciliations, lesson progression and instructor grading. None of these are claimed complete in this PR.

## Phase 2 — SEC-verified company and enforcement workbooks

Implemented in the existing Spin Sankey Flo as the Real SEC Lab mode. Entry: NVDA real SEC Excel modeling lab; AAPL real SEC workbook; MSFT SEC financial model; Sunbeam SEC case spreadsheet; Dell SEC case workbook. The original mascot, guided DCF tutorial and six hypothetical sheets remain intact.

### Locked historical filings (USD millions, NOT a live stock-price feed)

| Company | FY ended | Revenue | Operating income (EBIT proxy) | Net income | D&A | Cash CapEx | Operating cash flow | OCF - CapEx |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NVDA | Jan 25, 2026 | 215,938 | 130,387 | 120,067 | 2,843 | 6,042 | 102,718 | 96,676 |
| AAPL | Sep 27, 2025 | 416,161 | 133,050 | 112,010 | 11,698 | 12,715 | 111,482 | 98,767 |
| MSFT | Jun 30, 2026 | 331,839 | 155,237 | 133,749 | NOT VERIFIED AS CLEAN D&A | 115,948 | 182,935 | 66,987 |

SEC primary evidence:
- https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm
- https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm
- https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm

Account for reporting scope: NVDA's FY2026 $6,042M cash investing line explicitly combines purchases of property/equipment AND intangible assets. Microsoft groups depreciation, amortization AND OTHER ($38,534M); it is NOT a clean D&A figure, so the model displays unavailable and does not generate a fabricated FCFF. Reported historical OCF less cash CapEx is NOT FCFF.

### Interactive exercise vs SEC fact

Gray SEC fact cells cannot be modified; blue tax and Δoperating NWC assumptions are explicitly marked NOT SEC; purple formula cells must be completed by the student. Full-year revenue, operating income, net income, standalone D&A when disclosed, cash CapEx and OCF are the inputs. Exercises grade operating margin, OCF−CapEx, FCF margin and CapEx intensity. An illustrative FCFF can be computed only when D&A is separately substantiated, and uses user-editable normalized tax and working-capital assumptions. It is NOT the issuer's reported FCFF, a professional DCF, or a current market quote.

### Historical SEC forensic case exercises

- Sunbeam: SEC administrative order https://www.sec.gov/enforcement-litigation/administrative-proceedings/33-7976 . SEC found $35M improper 1996 reserves, $2.75M premature Q2 1997 supplier rebates, originally reported 1997 income $189M and restated income $93M. Student calculates the $96M gap and the 50.8% reduction relative to originally reported income. The $35M reserve mechanism is NOT the entire restatement.
- Dell: https://www.sec.gov/newsroom/press-releases/2010-131-sec-charges-dell-senior-executives-disclosure-accounting-fraud . SEC described Intel exclusivity payments as 10% of FY2003 operating income, 38% for FY2006 and 76% for FY2007 Q1. Student calculates +66 and +38 percentage points, NOT unverified absolute dollar transfers.

These are historic SEC enforcement findings, NOT allegations about a company currently being viewed.

### Import the site's own latest processed complete SEC 10-K

On a current company page, the Flo lab shows Use latest fully processed 10-K from this site. The button fetches the first-party published data/c/{CIK}.json, selects the latest processed ANNUAL 10-K in years, checks official sec.gov/Archives filing provenance and native USD denomination, converts dollar values to USD millions, and reads report-specific earnings nodes. A depreciation-only node is NOT treated as D&A. Any missing source or partial data are displayed as unavailable. This is an opt-in same-origin read, NOT an external API or live quotes.

Files: web/flo-real-data.js, web/flo-real-workbook.js, web/mascot.js, web/index.html; tests/test_flo_real.cjs. Both standalone Academy checks and main offline checks execute the new tests.

Rollout: PR merge conflict must be resolved, CI rerun, and deployed Pages verified before labeling the feature live. Historical 10-K amounts remain frozen evidence unless the reader explicitly loads a newer processed SEC annual report.
## Phase 3 — Guided Financial Modeling Coach and Historical SEC Forensic Simulations

This phase adds `web/flo-coach.js` and `tests/test_flo_coach.cjs` to the ORIGINAL Spin Sankey Flo. It does NOT turn the mascot into a general artificial-intelligence agent and does not require a paid LLM or Microsoft Excel API.

### Learning flow (implemented inside both worksheet engines)

1. **Read the lesson objective and accounting rationale** (Chinese / English): the row, cell reference, formula concept, unit, sign and difference between reported and assumed values.
2. **Locate the cell** with Go to cell; build a working spreadsheet formula using the already supported safe cell interpreter (A1 and simple functions).
3. **Check & next** checks the learner formula against the teacher's reference calculation before advancing. An incorrect/blank formula leaves the learner on the same milestone. Previous and stepwise Hint remain available.
4. **Track learning milestones** with a live per-session progress bar; the model also shows overall formula grading and model-side numerical output.
5. **Answer a conceptual checkpoint** about the common accounting error (such as OCF versus FCFF, WACC versus Ke, or reserve releases versus fraud). Multiple choice gives immediate feedback with an explanation.
6. **Practice journal entries** in the dedicated accounting treatment simulator; inputs are hypothetical and deliberately segregated from primary SEC historical figures.

Guided tracks cover six original finance modeling templates (DCF, integrated 3 statements, comparable EV/EBITDA, DDM, DuPont ROE, reserve rollforward); three real historical issuer workbooks (NVDA, AAPL, MSFT); and five historical SEC enforcement workbooks (Sunbeam, Dell, WorldCom, Xerox, Waste Management). Thus 14 distinct course/case context keys are present. Each track is a multi-step explanation of selected key formulas, rather than a full teacher-written explanation of every individual spreadsheet formula.

### New SEC primary-source cases

| SEC case | Verified evidence | Exercises and caveats | Source |
| --- | --- | --- | --- |
| WorldCom | SEC complaint alleges pretax income was overstated approximately **$3,055M for FY2001** and **$797M for Q1 2002** | `=B3+B4` totals **$3,852M across two separate periods**, NOT an FY-only figure. Walk through improper capitalization of network line costs. | https://www.sec.gov/enforcement-litigation/litigation-releases/lr-17588 |
| Xerox | SEC alleged equipment revenue accelerated **by over $3,000M** and pretax earnings increased approximately **$1,500M**, 1997–2000 | SEC revenue is a **strict lower bound**, never a precise $3B. Training teaches timing of revenue vs cash, and forbids false precision in margin ratios. | https://www.sec.gov/enforcement-litigation/litigation-releases/lr-17465 |
| Waste Management | SEC described approximately **$1,700M** cumulative misstatement of pretax earnings for 1992–Q3 1997 | The reported amount belongs to the **entire multi-year period**. Depreciation/useful-life practice uses explicitly hypothetical PP&E cost and useful-life assumptions, NOT an invented historic depreciation schedule. | https://www.sec.gov/newsroom/press-releases/2002-44-waste-management-founder-five-other-former-top-officers-sued-massive-fraud |

Original Sunbeam ($35M reserves, 1997 original/restated income) and Dell (Intel payments as 10%/38%/76% of operating profit) labs are retained. All cases are historical SEC allegations/findings; case-exercise dollars are not always complete measures of the misconduct.

### Accounting mechanism simulator (entirely hypothetical)

Five simulation scenarios accept user-provided amounts and relevant useful lives, and return numerically calculated comparisons, journal entry examples, and scope caveats:

- **WorldCom / expense capitalization:** demonstrate capitalization of a **hypothetical** operating cost, current pretax/asset inflation, and simplified future depreciation. Immediate cash difference = zero, absent changing a real payment or its cash-flow classification.
- **Xerox / premature revenue:** show modeled income and receivable inflation, with no immediate cash received. Example does not infer actual Xerox fraud amounts from input.
- **Waste Management / depreciation useful life:** compare straight-line annual depreciation at original vs extended life, holding initial cash expenditure unchanged. Does not infer actual historical policy choices.
- **Sunbeam / reserve release:** show liability reduction and income increase for a valid estimate reversal, without treating release by itself as fraud.
- **Dell / supplier incentive dependency:** illustrative $100 operating-profit base with editable incentive share; NOT SEC-sourced incentive dollars.

### Safety, functionality and rollout

SEC historic observations are **read-only** and link to official primary-source URLs. Scenario assumptions are clearly separated. The calculator rejects invalid amounts, negative amounts, extreme inputs and useful lives outside 1–40 years. Every displayed case narrative and result is HTML escaped. The simulator does not claim to reconstruct a SEC-case historical journal, company tax effect, actual CFI/CFO reclassification or fraud verdict.

`tests/test_flo_coach.cjs` checks 14 lesson tracks, gate-on-correct-formula progression, Chinese hints, conceptual quiz feedback, three new SEC amount reconciliations and all five hypothetical scenario engines. The standalone Flo Academy workflow and the full site's offline CI run it together with the previous mascot/Academy/spreadsheet/SEC workbook tests.

UI loaded in `web/index.html`: `flo-coach.js` before `flo-real-workbook.js` and `mascot.js`. Chat shortcut **Forensic Case Lab** opens the WorldCom exercise directly; **Real SEC Lab** still supports source-labeled historical issuer cases. The text chat's **SEC Case Studies** topic also now includes WorldCom, Xerox, and Waste Management.

Draft PR #72 must still be merged, the current commit CI verified, and GitHub Pages deployment smoke-tested before claiming any of this is on the live website.
## Phase 4 — Adaptive case training, health-sector accounting and opt-in progress

### Newly grounded US SEC cases (historical allegations / enforcement, not current issuer diagnosis)

| Company | SEC evidence and explicitly scoped period | Workbook assignments | Source |
| --- | --- | --- | --- |
| HealthSouth | SEC 2003 complaint lists reported versus actual pretax earnings in USD millions: **FY1999 230 vs -191; FY2000 559 vs 194; FY2001 434 vs 9; H1 2002 340 vs 157**. Specific resulting differences: 421, 365, 425, 183. These four period differences sum to **1,394 USD M**, a mixed three-FY + six-month subset, NOT a single-year figure, not a complete reconstruction of journal entries or the full alleged fraud. | Learner computes each reporting-period difference, correctly handles NEGATIVE actual income, checks SUM(C3:C6), distinguishes H1 from full FY. | https://www.sec.gov/litigation/complaints/comphealths.htm |
| Bristol-Myers Squibb | SEC litigation describes approximately **$1,500M improperly recognized revenue** on consignment-like sales in 2000–2001; an independent **$150M civil settlement penalty** must not be mislabeled a revenue adjustment. Associated risks: channel stuffing, distributor carrying incentives, divestiture cookie-jar reserves. | Student converts the approximate revenue amount to $B units; uses an explicitly **HYPOTHETICAL $2,500M sales base** to practice adjusted revenue and how an unsupported hypothetical ratio is different from a published company ratio. | https://www.sec.gov/enforcement-litigation/litigation-releases/lr-18820 |

New sources do not overwrite existing NVDA/AAPL/MSFT annual 10-K lab, Sunbeam/Dell/WorldCom/Xerox/Waste Management original SEC primary evidence, and historical/future assumption segregation. Two new worksheet IDs: HEALTHSOUTH and BRISTOL. Case registry and linked chat search were expanded accordingly.

### Learning features actually implemented

- **16 learning pathways:** six spreadsheet model types, three SEC issuer report worksheets and seven SEC historical enforcement cases (Sunbeam, Dell, WorldCom, Xerox, Waste Management, HealthSouth, Bristol-Myers). Every path includes bilingual incremental prompts, specific formulas, source flags and concept questions.
- **Adaptive quizzes:** additional multi-question drills for DCF/3-statements/comparables/DDM/DuPont/reserves and for both new enforcement cases. Correct answers advance to the next quiz, wrong choices give an explanation; per-session counts are maintained. Quizzes measure conceptual awareness, not a model's economic validity.
- **Private error notebook:** spreadsheet Check/Grade buttons log incorrect formula cells and counts. Review mistakes focuses the most frequently missed cell (earliest model dependency where counts tie), instead of merely displaying total score. This is an error review guide, not a general automated root-cause theorem prover.
- **Mode toggle:** guided (hints), practice, and exam. Exam hides formula and lesson hints and reference-formula reveal buttons; concept quizzes still provide feedback. All three use the same bounded arithmetic interpreter, not an AI grader.
- **Opt-in local persistence:** explicit Save/Restore/Clear course controls use **this browser's localStorage**, not a server API. Saved data include only learner input cells, formula progress, anonymous per-course error counts, selected mode and current milestone. Lock-protected SEC reported cells are never stored as input and **cannot** be overwritten on restoration. Original SEC source URI is checked so user work from a different annual filing cannot be imported into a new source. No cloud sync or background monitoring.
- **Two more hypothetical accounting simulations:** HealthSouth-style unsupported accrual/asset inflation and Bristol-Myers-like deferred distributor revenue, with simplified journal effects. These are mechanics only, NOT reconstruction of historic SEC journal entries. Total simulation scenarios now seven.
- **One-click navigation:** updated Flo quick-chip entries for HealthSouth and channel-stuffing case exercises.

### QA and deployment

New modules: `web/flo-practice.js` (local-only saving, review and mode), `tests/test_flo_practice.cjs`; modified `web/flo-coach.js`, `web/flo-real-data.js`, `web/flo-real-workbook.js`, `web/flo-workbook.js`, `web/index.html`, `web/mascot.js`, `web/flo-academy.js`, CI workflows.

Standalone tests directly executed: `tests/test_flo_practice.cjs` **216 assertions passed**, and existing `tests/test_flo_coach.cjs` **153 passed**, after resolving nested downstream-error priority and official historical complaint source URL allowlisting. CI results on latest HEAD must be checked separately. Do not mark this as live until the draft PR is reviewed, merged and the GitHub Pages build publishes the assets.

### Deferred

True XLSX import/export, richer multicurrency and annual segment SEC normalizer, complete historical accounting journal recreation, multi-step free-text semantic grading, teacher dashboards, and server-synced exercise progress are NOT claimed implemented. They require added source validation and/or explicit privacy/data-storage decisions.
## Flo Published Pulse — in-page notifications without forced refresh (current extension)

This capability stays inside the existing Spin Sankey Flo mascot. The HTML page stays mounted while `web/flo-alerts.js` checks the **published** static manifest `disclosures/data/market/flo-alerts.json` every two minutes. It does not refresh the document, make direct SEC/Yahoo requests, need an external API key, play audio, enable OS push or continue monitoring when the tab is closed.

The Pages staging step in `.github/workflows/scan.yml` generates this compact feed from already staged data with `scripts/build_flo_alerts.py`, separating **event time**, **scanner collection status**, **price-as-of** and **site manifest generated time**. Events are source-evidence records, not alerts generated by an LLM.

### Source contract

| Event | Verified stable identity | Real source / caveat | Flo action |
| --- | --- | --- | --- |
| 8-K / 8-K/A | EDGAR accession number | Official SEC filing and acceptance/filing dates. Item topic + excerpt are source-derived, **not proof of market impact**. | Red accent, concerned face for high-priority filings, short shake; explains restatement, audit changes, equity offerings, M&A, bankruptcy, impairment, cybersecurity, guidance and CEO/CFO changes, linking original filing. |
| 13F | Filing-manager CIK with period/filed date, or newly indexed manager/date | Prefer tracked fund parsed changes in SEC-linked watchlist. Also check `catalogs/holdings.json` for **newly indexed filing dates** when the watchlist lags; if no parsed holdings, say so and do NOT invent added, reduced or exited ticker weights. The 13F is a delayed quarter-end holdings disclosure, **not a filing-date trade**. | Blue accent, mascot wave + spin; explains quarter end vs filing date, quantity changes/splits, source lag. |
| News releases | Original feed ID | PR Newswire/SEC/FDA source URL + issuer ticker match. Headlines are **unverified source claims**, not independently checked by Filing Flows. | Mint/green accent and news notification. |
| Stock move | Ticker + actual EOD as-of date | `extremes.json` verified `chg1d` and close; min 5% magnitude; stale daily bars dropped. **Not intraday or real-time trades**, no invented volume or reasons. | Yellow accent, Flo hops on up moves or worries on down moves; links to fundamental analysis. |

### Improved UI and analysis

- On first visit, Flo establishes a historical event baseline **without spamming historic alerts**. On subsequent polls, only unseen, still-relevant event IDs are eligible. Up to 1,000 seen IDs are retained locally to avoid duplicate popups across site builds and sessions.
- **One attention-grabbing popup per five minutes** maximum (persistent page/browser cooldown), while all additional findings remain in the inbox and count. Repeated static builds, price supplementation and reopened panels do not fabricate new events.
- The popup can be dismissed without opening chat, and offers **Ask Flo**, **Inbox** and **Mute**. Flo does not forcibly open the panel; detailed analysis begins on a user click. No sound is used. Reduced-motion preference removes special animation.
- Inbox provides locally stored watch tickers, quiet mode, category switches, source health and **last attempted vs last successful/partial SEC scan**, the most recent filing date and any retry queue. It never shows a partial scan as a full success.
- The answer cites the exact 8-K item, manager/filer, reported 13F quarter date, or dated EOD price with explicit limits. Related published events for the **same ticker within three days** are displayed as independent leads, with their individual source links and a non-causality warning.
- Users can ask Flo directly: *“最近扫描有什么新消息”*, *“What changed since the last scan?”*, or the **Recent scans** quick mode. The question is answered only from the validated in-page published feed; ordinary ticker valuations and generic SEC filing questions stay on the original analysis handlers.
- Cached company reports and valuation JSON are invalidated after a newer published alert snapshot is detected. This re-fetches on the **next question**, not by reloading the webpage.

### Verification

Offline `tests/test_flo_alert_feed.py` checks source schemas, 8-K/13F/news/price expiry, fraudulent links, EDGAR Eastern timezone assumptions and catalog-indexed 13F fallback with a clear 'not parsed' label. `tests/test_flo_alerts.cjs` (33 assertions directly executed) checks no first-visit spam, deduplication, XSS escaping, detailed 8-K playbooks, cross-source independence, routing, and 13F lag cautions. `tests/test_flo_alert_browser.cjs` tests a tab left open through a new published scan, pop-up, Flo action and quiet mode. Dedicated Flo/Pulse workflows and the full offline CI run these tests.

### Explicit limitations

Polling the published **static** manifest is not WebSockets, an always-on service worker or push-notification service. The collector may run every 15 minutes but site staging may be slower; a tab must remain open, active/online for updates. A new source item that is too old for the freshness window is displayed only as historical context or dropped, not surfaced as breaking. No browser push permission, trade execution, predicted price movement, automatic fraud conclusions or proof that a news story caused a stock move is provided.


### Flo Pulse refinements — alert priority and indexed 13F provenance

- Added persistent **Info / Medium / High** minimum-severity filtering in the Flo Pulse inbox, alongside the existing per-kind checkboxes, ticker watchlist and quiet mode. Filters affect alert presentation, not the underlying SEC scan.
- Recognize the precise SEC EDGAR manager index URL `https://www.sec.gov/edgar/browse/?CIK=<digits>&owner=exclude` as a legitimate 13F source, without trusting malformed index query strings or look-alike hosts. This fixes the previously silent loss of *indexed, not yet fully parsed* 13F notifications. Such notices explicitly do **not** claim confirmed manager trades or position changes.
- Added regression checks for authorized indexed 13F hyperlinks, malicious CIK/redirect parameters, and priority-suppression behavior. The current pulse suite reports 40 passing checks via direct execution of `tests/test_flo_alerts.cjs`.
- Existing source-level scan-health panel distinguishes scan attempts, success/partial success, latest filing dates and retry queues; retained as-is instead of duplicating it. Existing 2-minute active-tab polling, first-load baseline, deduplication, quiet mode and per-event actions are preserved.

This PR is not published until merged and deployed; static scan alerts remain bounded by the freshness of the site's generated data. Priority labels are rules-based screening categories, not investment recommendations.

## Phase 6 — Cross-Signal Timelines and Watchlist Research Brief

Delivered to feature PR #72; NOT live until main merge and Pages verification. No paid news or market API, no extra EDGAR polling, no forced reload or automatic trading. This module reads only the static, already-published site Flo Pulse JSON and reuses its foreground two-minute refresh, deduplication, rate limiting, quiet mode and mascot animations.

### Research timeline for an individual ticker

Entry points: type **NVDA 事件时间线**, **$NVDA filing timeline** or **NVDA event timeline**; click **Timeline** from the new-event toast or in an inbox row; or use the inbox ticker selector.

New web/flo-timeline.js consolidates separately sourced 8-K SEC filings, 13F disclosures (including stock symbols carried in the 13F change list), approved-source news headlines and published daily-close price observations. Default output is limited to the last 14 days and at most 20 individual observations, further capped by the small already-published feed. It is not exhaustive.

Time semantics: 8-K/news show event timestamps when available; 13F shows actual FILING DATE and separate QUARTER-END HOLDINGS PERIOD; delayed price data show their PRICE-AS-OF-CLOSE DATE rather than implying any intraday move or midnight trading time. Sources are URL-allowlisted and titles escaped to resist injected HTML.

Signals of two or more distinct types within 72 hours are identified as temporally co-observed ONLY. They are NOT causal evidence of 8-K/press release/13F explaining the stock-price change. Manager holdings as of quarter end are NOT trades on the filing date. Event-study returns, causal attributions, share-price predictions and unverified trading volumes are not calculated.

### Watchlist brief

Users set a symbol watchlist in the original Flo Pulse inbox, then click **Watchlist brief** or ask **我的关注股票最新动态** / **watchlist brief**. Flo shows counts of published SEC 8-Ks, 13Fs, news and end-of-day price snapshots for each watched ticker, last observed timestamp and how many overlapping source-type windows appear. Zero matches explicitly mean limited feed coverage, NOT proof no filings occurred.

### Technical files and safeguards

- New web/flo-timeline.js: safely grouped, deduplicated and time-scoped evidence; original SEC links and non-causal teaching notes.
- web/index.html loads timeline helper before web/flo-alerts.js.
- web/flo-alerts.js now includes popup and inbox Timeline actions, language-route support, a watched-ticker brief and six-hour stale-feed warning.
- tests/test_flo_timeline.cjs covers multiple event types, two-ticker isolation, old/future items, malicious URLs and HTML escaping, timestamp precision and watched-symbol rollups (50 passing direct checks); tests/test_flo_alerts.cjs existing alert contract (40 direct checks).
- tests/test_flo_alert_browser.cjs updated to cover browser-tab no-refresh popup → timeline click → Flo reply; GitHub Actions dedicated pulse, Academy and full offline CI now run the new test.

**Not yet deployed:** PR #72 must be reviewed, merged and the static Pages build verified. It is not an always-on server agent, real-time exchange ticker feed or SEC push-notification system.
## Phase 7 — Flo Evidence-to-Model Research and Market-relative Daily Context

**Implementation branch only; PR #72 is not production until reviewed, merged and Pages-deployed.** This phase extends the existing on-page, no-reload Flo Pulse event research. It does not introduce a paid model, new brokerage/market connection, or EDGAR push service.

### From a published 8-K to a specific financial research checklist

New `web/flo-impact.js` builds bilingual SEC research cards with primary evidence links, accepted timestamps, published manifest freshness and formula checklists. The cards are conditional on the site's scanner-assigned event topics; these are **hypotheses to verify from the SEC document**, NOT assertions that the tagged transaction closed or that an alleged breach occurred. Key categories:

| Scanner topic | Research steps / mathematical prompt |
| --- | --- |
| Restatement | Reconcile original and corrected earnings, equity and EPS; inspect auditor and debt-covenant implications. A restatement is not necessarily a cash payment. |
| Offering | Distinguish authorization, announced deal and actual shares issued; pro forma diluted shares, net proceeds and dilution. |
| Debt | Confirm contractual principal, interest rate, maturity, covenants and EBIT-to-interest coverage; do not substitute borrowed cash for profit. |
| Acquisition | Confirm whether transaction closed, consideration allocation, goodwill assumptions, synergies and integration costs. |
| Guidance | Compare fiscal periods and GAAP/non-GAAP definitions before computing new-minus-old midpoint. |
| Impairment | Identify asset class, noncash charge, effective dates, taxes and covenants. |
| Repurchase | Separate authorized program from actual cash-spent repurchases; no fabricated share-count change. |
| Cybersecurity / auditor changes | Source materiality and effects only from disclosure; review Item 4.01 and letters when relevant. |

SEC 13F research cards show separately labeled **filing date vs quarter-end holdings period**, advise comparison of split-adjusted positions and warn that 13F changes are not trades made on filing date. Published news remains unverified without reading original documents.

### Optional daily-close market-relative comparison (not an event study)

`scripts/build_flo_alerts.py` now passes through `benchmarks` for SPY, QQQ and IWM ONLY WHEN the site's existing staged `extremes.json` contains named, valid same-day closing rows for those indices. The baseline remains absent if those rows are missing. Index context does NOT generate an alert (e.g. SPY +0.82% is not labeled extreme). Actual returned percentages are taken from the same prices file as the observed stock and never guessed.

On a **price event only**, the card computes:

`Same-date market-relative daily change (percentage points) = stock daily change % − published index daily change %`.

The computation requires the exact SAME `price_asof` string and validated positive published closing price. A missing SPY/QQQ/IWM benchmark, mismatched date, invalid percentage or old snapshot yields an explicit unavailable state. Even where populated, **this is not cumulative abnormal return (CAR), a historical event-study estimate, an intraday impact, causal attribution, or a real-time trading signal**.

### Flo assistant and UI integration

- New `web/flo-impact.js` loaded between `web/flo-timeline.js` and `web/flo-alerts.js` on the root site.
- Existing no-refresh event popups now have a **Research / 财务影响核查** button; the inbox also provides a per-event Research action. Both open the study card within the original Flo bot without forcing a reload.
- Bilingual chat intents include `NVDA 8-K impact analysis`, `NVDA 披露财务影响`, and `NVDA 相对大盘涨跌幅`. The router chooses the newest matching published event, not simply the JSON list's first position, and refuses to invent missing events.
- If the upstream scanner publishes an event without same-date benchmarks, the research card still contains the source evidence and appropriate accounting checklist, but explicitly refuses a numeric index comparison.

### QA

- `tests/test_flo_impact.cjs`: checks conditional SEC accounting topics and related formulas, original-source controls and escaped titles, same-day SPY/QQQ comparisons, stale IWM omission, no numeric results for mismatched days, nonexistent market baselines and invalid changes. 32 assertions passed in direct execution.
- `tests/test_build_flo_alerts.py`: new cases for benchmark metadata sourced from the same generated-date price file, baseline omission on stale/missing data and no automatic alert from a small SPY/QQQ daily change.
- `tests/test_flo_alert_browser.cjs`: verifies the new popup Research action and SEC restatement explanation in the same open browser tab.
- The Flo Pulse, Flo Academy and full-site offline GitHub Actions now load and execute the new module/test.

### Still not completed

A research-grade historical **event study** would require timestamp-aware event alignment, trading-calendar data, validated pre-event estimation windows, split-adjusted stock and benchmark histories, bid-ask/liquidity context, event overlap controls, and out-of-sample reporting. The site does not yet guarantee that data for every ticker. Do NOT advertise computed abnormal returns, statistical p-values or historical causal outcomes until those sources and validation are implemented.

## Phase 8 — Five-minute index-constrained intraday gain scanner (activation gated)

New standalone implementation: [FLO_5M_MOMENTUM.md](FLO_5M_MOMENTUM.md).

- Server minute bar collector: scripts/flo_momentum.py (Alpaca 1Min bars, precise bar endpoints 5 minutes apart, strict timestamps, US regular trading hours, multiple stock pagination and publisher-only secrets).
- Source-traceable membership: current unofficial S&P 500 constituent fetch, and Russel 1000/2000 ONLY when complete, recent, properly sourced/licensed snapshots have been installed. Stale/missing index data explicitly block that scope. The existing June 2024 S&P historical file is not presented as today's components.
- Durable relay: last completed public/private Supabase scan, top-60 rank, prior rank and consecutive scans in top, coverage ratio per index. Partial coverage is always disclosed.
- New root-site Flo 5m panel: universe selector, minimum 5m gain, minimum 5m dollar turnover, minimum top-list streak, quiet setting, minute-data source and validity state. Live-page polling of the authorized published snapshot once a minute; first load never raises a historical new-leader popup, with five-minute notification cooldown. Flo quick-question and English/Chinese natural-language routing are included in the existing mascot.
- Security: db/flo-momentum.sql uses Supabase RLS (anon has SELECT only after is_public=true), server-only Alpaca and service keys. Site operator must explicitly set FLO_MINUTE_PUBLIC_LICENSED=true AFTER confirming supplier/exchange market data redistribution rights. Without this, no public minute data; never pretend daily-close extremes.json is five-minute movement.
- Producer schedule .github/workflows/flo-momentum.yml approximately each 5 minutes on business weekdays; Actions cron lateness is possible, so stale output older than twelve minutes is denied. An always-on licensed SIP streaming collector is NOT implemented.
- Tests: tests/test_flo_momentum.py and tests/test_flo_momentum.cjs; dedicated Flo momentum validation workflow and established Flo Pulse/CI checks, source-anchored formula and alert gates.

The feature is committed to a proposal branch. Real-world activation requires migration, API/secrets setup, accurate index memberships, data rights, CI and final Pages build. Do not report Russell rankings while lists are unavailable or claim guaranteed realtime market-wide performance from an IEX-only feed.
