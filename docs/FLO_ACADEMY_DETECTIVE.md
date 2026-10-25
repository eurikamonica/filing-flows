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