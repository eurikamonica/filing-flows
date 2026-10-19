# DATASET CARD — v3 owner build (`v3-data-20261018T052500Z`)

Status: **built, not human-reviewed.** No row has been reviewed by a person. No teacher model labelled anything. No training, inference or GPU use happened. Task B (MD&A) is deferred and was not built.

Builder: `build_v3_owner.py` (copy in this directory; the original is `model-expansion-lab/build_v3_owner.py`). Upstream logic is pinned in `upstream/history.py` and `upstream/reform.py` (eurikamonica/filing-flows `main` @ `04226e2`). Their SHA256 values are in `manifest.json`.

## Sources

- 59 fresh US 10-K filers. None of the CIKs used in earlier lab runs is included. Company list and names are in `manifest.json`.
- SEC companyfacts, submissions and filing primary documents were fetched with `User-Agent: Filing Flows filingflows@gmail.com` and a gap of at least 0.125 s between requests (8 req/s or less).
- **484 HTTP requests, all status 200.** There were no 403, 429, 5xx or network failures. About 1.28 GB is stored under `sources/`, which is git-ignored. `sources/manifest.json` lists URL, accession, SHA256, bytes and UTC time only.

## Splits (decided before any row was built)

- Split is by company, using seed 20261018 with a 70/15/15 split: 41 train, 9 dev, 9 sealed_test companies (`split-membership.json`).
- All rows of a company sit in one split.
- Task C held-out tags (`heldout-tags.json`, written before rows) are 13 of the 66 tags, chosen as 7 `op` and 6 `fin` with seed 20261018:
  - AccountsReceivableNetCurrent, AvailableForSaleSecuritiesDebtSecuritiesNoncurrent, ContractWithCustomerLiabilityCurrent, DeferredRevenueNoncurrent, FinanceLeaseLiabilityCurrent, InventoryNet, MarketableSecuritiesCurrent, MarketableSecuritiesNoncurrent, OtherAssetsNoncurrent, PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent, PrepaidExpenseCurrent, SeniorNotes, ShortTermInvestments.
  - The lines `inv` and `onca` are therefore wholly unseen.

| Task | train | dev | sealed_test |
| --- | --- | --- | --- |
| A revision_reason | 146 | 36 | 31 |
| C bs_line_classification | 487 | 189 | 176 |

`dev-protocol.jsonl` holds 17 A rows (up to 3 per label present in dev) and 40 C rows (20 held-out-tag, 20 seen-tag).

## Task C — what is observed and what is table default

- **Observed (companyfacts):**
  - The latest 10-K balance-sheet instant facts: tag, value and period end.
  - The concept `label`. This is the **taxonomy label from companyfacts, not the company's own line caption**.
- **Table default (`label_kind: table_default`):** `cls` is the class of the tag's line in reform.py `LINES`.
- **Selection:** reform.py selection is applied. That means one tag per candidate group (the first one present), the `COVERS` skips, `DebtCurrent` stopping the `std` line, and only non-zero lines kept.
- **Exclusions:**
  - `oth_a`/`oth_l` and extension tags never appear.
  - One company whose long-term debt is tagged only as `LongTermDebt` (outside the 66 tags) has no `ltd` row.
- **Neighbours:** 3–6 nearby lines are shown as side, label and value, without tags. In train, neighbours that carry a held-out tag are omitted.
- **Caps and drops:** rows are capped at 20 per tag per split (152 rows dropped). 164 train rows with held-out tags were dropped.
- **Evaluation groups:**

  | Split | seen_tag | heldout_tag_seen_line | heldout_tag_unseen_line |
  | --- | --- | --- | --- |
  | dev | 152 | 20 | 17 |
  | sealed_test | 139 | 20 | 17 |

- **Class balance:** train is 373 `op` / 114 `fin`.
- **Coverage gap:** 16 of the 66 tags never occur in this company set. Most are the later alternatives in the `ltd` group. They include the held-out tags MarketableSecuritiesCurrent, MarketableSecuritiesNoncurrent and SeniorNotes, so only 10 held-out tags are actually exercised. See `C_tags_never_observed` in `manifest.json`.
- **Deviation from draft:** the output is `{"cls","tag"}` without the draft's `"quote": null`, as instructed.

## Task A — what is observed and what is rule-derived

- **Observed:** the event (accession, form, changed keys, old and new values) and its `pattern`. These come from a faithful re-implementation of history.py `versions`/`moved`/`pattern`. The settings are:
  - Concept lists:
    - revenue = Revenues, RevenueFromContractWithCustomerExcludingAssessedTax, SalesRevenueNet ("Revenues" first, else the largest)
    - oi = OperatingIncomeLoss
    - ni = NetIncomeLoss, ProfitLoss
    - ocf = NetCashProvidedByUsedInOperatingActivities
  - The last 10 years; fy/q spans only.
  - A change counts if it exceeds 0.05% or $0.5M.
- **Events found:** 447 in total (results 203, presentation 189, cash flow 49, amended 6).
  - As in upstream, no form filter is applied, so 12 events come from DEF 14A/PRE 14A pay-versus-performance tags and 11 from 8-Ks.
  - At most 10 events per company were downloaded, prioritised as amended > results > cash flow > presentation, newest first.
- **Rule-derived (`label_kind: rule_derived`, `review: not_human_reviewed`):**
  - The label comes from keyword rules on single sentences, restricted to the event's pattern group.
  - Forward-looking or conditional sentences, negated sentences ("not been recast"), clawback/compensation text and exhibit titles ("amended and restated") are rejected.
  - For `results` events, an 8-K with Item 4.02 filed within 180 days before or 30 days after the event is searched first.
  - The gold `quote` is the triggering sentence. The evidence is the whole paragraph that contains it, plus a short heading above it if one exists. Passages are never truncated.
  - Prompt plus answer is at most 900 estimated tokens (4 chars/token). The maximum measured is 886 estimated tokens, and the longest passage is 2,038 chars.
- **Abstention:** `insufficient_evidence` with `quote: null` is used when no rule fires. The passage is then a basis-of-presentation, consolidation or amendment paragraph from the same filing in which no rule fires.
- **Exclusions:** 121 events were excluded because no usable passage was found.

| Label | train | dev | sealed_test | total |
| --- | --- | --- | --- | --- |
| accounting_change_retrospective | 16 | 13 | 0 | 29 |
| error_correction_revision | 3 | 0 | 0 | 3 |
| restatement_non_reliance | 1 | 0 | 0 | 1 |
| discontinued_operations | 19 | 7 | 6 | 32 |
| segment_recast | 14 | 2 | 3 | 19 |
| income_statement_reclassification | 26 | 3 | 7 | 36 |
| cash_flow_reclassification | 22 | 3 | 2 | 27 |
| amendment_restatement | 5 | 0 | 0 | 5 |
| amendment_tagging_or_clerical | 1 | 0 | 0 | 1 |
| insufficient_evidence | 39 | 8 | 13 | 60 |

**Known weaknesses (unreviewed):**
- The `results` labels are very thin. There is one non-reliance row and three error-correction rows, and none of either appears in dev or test.
- The amendment labels appear only in train.
- The sealed test has no `results`-group label other than abstention.
- Spot checks show the rules still pick some sentences that are true but not the actual cause of the change. Examples are disclosure-only ASU adoptions labelled `accounting_change_retrospective`, and discontinued-operations sentences in filings whose change had another cause.
- Several companies repeat near-identical boilerplate across quarters.
- The draft card requires human review before these labels are treated as gold. That review has not happened.

## Checks (`checks.json`, all passed)

- There is no company, document or input overlap across splits.
- Held-out tags are absent from train, both as targets and in input text.
- Every gold quote is a verbatim substring of its evidence after NFC normalisation and whitespace collapse.
- Pattern-group consistency holds.
- All outputs are valid JSON, match `expected`, and follow the contract keys.
- Every row sits in its assigned company split.
- All rows are within the length limit.
- No row is marked human-reviewed.
- There are no `oth_*` or extension tags.
- IDs are unique.
- The request budget (3000) was respected.

SHA256 values of `train.jsonl`, `dev.jsonl`, `sealed/test.jsonl`, `dev-protocol.jsonl`, `heldout-tags.json` and `split-membership.json` are in `manifest.json`. The sealed test is frozen by that hash.
