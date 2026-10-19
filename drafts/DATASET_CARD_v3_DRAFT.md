# DATASET CARD — v3 (DRAFT, not built)

Status: **draft for owner review.** No data has been downloaded, generated, split or frozen for v3, and no training or evaluation is running. v2 is frozen and paused. Qwen3-8B is paused, and no 8B job runs on the GPU (see RELEASE_STATUS.md).

Base model under consideration: the retained Qwen3-4B champion (`runs/20261016T171524Z/archive/qwen4`). Inference stays local. The model fills fields that already exist in the `eurikamonica/filing-flows` pipeline:

| Task | Fills | Upstream definition (pinned to `main` @ `04226e2`) |
| --- | --- | --- |
| A | `why` of each revision event | `pipeline/history.py`, `compute()` → `events[*].why` |
| B | MD&A driver amounts | not yet mapped to a pipeline field (see open question 2) |
| C | `suggest` of each balance-sheet line | `pipeline/reform.py`, `compute()` → `lines[*].suggest` |

The JSON pushed to the `narratives` branch follows a schema that the cloud side will provide. The output shapes below are internal training targets. No push code is written until that schema arrives.

## 1. Scope

| ID | Task | Model output | Gold source |
| --- | --- | --- | --- |
| A | `revision_reason` | Reason label plus a verbatim quote from the filing | `pattern` from history.py (observed) plus a rule-proposed reason, then human review |
| B | `mdna_driver_amount` | Drivers of a stated change, each amount copied verbatim | Span annotation with a mechanical verbatim check |
| C | `bs_line_classification` | `op` or `fin` for a balance-sheet line | The `LINES` table in reform.py (Nissim–Penman) |

Out of scope: arithmetic (Python stays responsible), free-form narrative, the old v1/v2 task families and 8B.

## 2. Shared rules

- **SEC download** (owner-approved 2026-10-16):
  - `User-Agent: Filing Flows filingflows@gmail.com`
  - At most 10 requests per second overall. The limiter will be set to 8 per second for margin.
  - Retries back off exponentially; 403 and 429 responses are logged and never hammered.
  - Sources: EDGAR filing documents and indexes (`www.sec.gov/Archives/...`) and companyfacts (`data.sec.gov/api/xbrl/companyfacts/...`).
- **Downloaded text never enters git.** Raw filings and companyfacts are stored under `runs/<run>/sources/`, which `.gitignore` already excludes except `sources/manifest.json`. That manifest records URL, accession, SHA256, byte size and download time only.
- **Evidence in the prompt.** Every example carries its evidence passage(s) with a `source_id` (accession, document, character offsets). The model answers from the supplied evidence only.
- **Verbatim constraint.** Quotes and amounts must be exact substrings of the supplied evidence after one documented normalisation (Unicode NFC, whitespace collapsed). Code does the check. Gold quotes that fail are rejected at build time. Model answers that fail are scored wrong.
- **Abstention.** Each task includes unsupported cases. The expected output is then `insufficient_evidence` (A), an empty list (B), or `null` (C; see section 5).
- **Splits.** Splits are made by company; all filings of one company sit in one split. The sealed test is frozen by SHA256 before any training. Task C also holds out tags (section 5).
- **Provenance.** Each row records `label_kind`, one of `observed`, `rule_derived`, `human_reviewed` or `table_default`. No teacher-model answers and no fabricated source IDs.
- **Length.** Complete prompt plus answer is measured. Planned context is 1024 tokens. Examples that do not fit are excluded and counted, never truncated.
- **Language.** Prompts and answers are in English.

## 3. Task A — revision reason (`why`)

**Where examples come from.**
1. Run history.py's logic on SEC companyfacts. This uses a pinned read-only copy of the upstream logic; the upstream repository is not modified.
2. That yields revision events: accession, form, changed keys (`revenue`, `oi`, `ni`, `ocf`) and `pattern`.
3. Then download the changing filing and cut the passage that explains the change. Candidates are the 10-K/A or 10-Q/A explanatory note, 8-K Item 4.02, and the basis-of-presentation, "Revision of previously issued" or "Reclassifications" note.
4. `pattern` is observed from the numbers, so it is free gold. The reason inside the pattern is what the model adds.

**Ten labels, grouped under history.py's four patterns:**

| Pattern | Label | Meaning |
| --- | --- | --- |
| results | `restatement_non_reliance` | Restatement with non-reliance (8-K Item 4.02, "Big R") |
| results | `error_correction_revision` | Prior periods revised for an immaterial error ("little r") |
| results | `accounting_change_retrospective` | New standard adopted retrospectively, or a voluntary change in principle |
| presentation | `discontinued_operations` | Prior results recast to remove discontinued operations |
| presentation | `segment_recast` | Prior figures recast for a new segment structure |
| presentation | `income_statement_reclassification` | Other income-statement reclassification to conform to the current presentation |
| cash flow | `cash_flow_reclassification` | Reclassification within the cash-flow statement |
| amended | `amendment_restatement` | Amendment filed to restate or correct reported figures |
| amended | `amendment_tagging_or_clerical` | Amendment correcting XBRL tagging, typographical or clerical errors |
| — | `insufficient_evidence` | The supplied text does not state a reason (abstention, maps to no pattern) |

**Consistency rule.** history.py assigns `amended` from the form alone (any `/A`), before looking at which figures moved. So:
- For an `amended` event, only the two `amendment_*` labels or `insufficient_evidence` are valid.
- For any other pattern, the label must belong to that pattern's group or be `insufficient_evidence`.
- This is checked by code, both on gold rows and on model output. A mismatch counts as an error.

**Two reasons are deliberately not labels:**
- Retroactive share-count changes only move EPS and shares, and history.py tracks only revenue, OI, NI and OCF.
- Measurement-period adjustments are recorded in the current period.

Neither produces a history.py event, so labels for them could never be used.

**Output (internal training target):**
```json
{"pattern": "results", "label": "error_correction_revision", "quote": "<verbatim sentence(s)>", "source_id": "<id>"}
```

**Labelling.** Candidate labels come from rules over the passage (Item 4.02 presence, heading phrases, keywords). Every train, dev and test label is then human-reviewed, and the reviewer confirms that the quote supports the label. Rules alone are not treated as gold.

**Metrics.**
- Pattern-consistency rate.
- Macro-F1 over labels.
- Quote validity (the verbatim check).
- Quote support (reviewed, dev only).

**Expected volume.** These events are rare per company, so the target is roughly 200–300 reviewed events. Per-label counts will be reported. Rare labels may be merged within their own pattern group.

## 4. Task B — MD&A driver amount extraction

**Input.** An MD&A results-of-operations passage plus a question about one line item and period.

**Output (internal training target):**
```json
{"drivers": [{"driver": "<phrase from text>", "amount_text": "$12.3 million", "direction": "increase", "quote": "<verbatim sentence>"}], "source_id": "<id>"}
```

**Rules.**
- `amount_text` must appear verbatim, including currency sign, scale word and parentheses. Code normalises it to a number afterwards; the model never does.
- Only amounts the text explicitly ties to the asked-about change count. If a driver has no amount, `amount_text` is `null`. If there are no drivers, the list is empty.

**Labelling.**
- Pattern rules ("primarily due to", "driven by", "partially offset by" near a currency amount) propose spans.
- A human confirms, adds or removes spans.
- `direction` is taken from the text, not from arithmetic.

**Metrics.** Exact-match span precision and recall on `amount_text`, the verbatim-violation rate (a hard error), and driver-phrase match (reviewed, dev only).

**Expected volume.** About 300–500 passages, to be fixed after 1024-token profiling.

## 5. Task C — balance-sheet line classification (`suggest`)

**Label source.** The `LINES` table in `pipeline/reform.py` (`main` @ `04226e2`): 27 lines and 66 standard `us-gaap` tags. Each tag inherits its line's default class, `op` or `fin`. By tag that is 36 `op` and 30 `fin`; by line it is 20 `op` and 7 `fin`. The table's own decisions are followed as written, for example cash is `fin` and operating lease liabilities are `op`. The table file and its SHA256 are pinned into the run manifest. If upstream changes the table, that is a new dataset version.

**Inputs.**
- One balance-sheet line taken from companyfacts: the company's own label, the tag and the side (asset or liability).
- Neighbouring lines.
- Optionally, a short excerpt from the filing's notes about that line.

**Output (internal training target):**
```json
{"cls": "fin", "tag": "us-gaap:ShortTermInvestments", "quote": null}
```

**Held-out tags.**
- About 20% of the 66 tags, which is 13, are held out from training entirely and used only in dev and test.
- The selection is stratified by class (about 7 `op` and 6 `fin`), uses a fixed seed and is recorded in the manifest before any data is built.
- Seven lines have exactly one tag (`inv`, `rou`, `gw`, `eqm`, `onca`, `ocl`, `oncl`). If one of those tags is drawn, that whole line becomes unseen.
- Results are reported in three groups: seen tag on a new company, held-out tag on a seen line, and held-out tag on an unseen line.

**Excluded from gold.**
- The derived residual lines `oth_a` and `oth_l` ("other, not tagged separately").
- Company extension tags.

Neither has a table answer.

## 6. Regression set

A fixed set of about 18 historical questions (as in run `20261016T171524Z`) guards JSON format and the old core tasks. It is used only as a "no large regression" check, not for model selection.

## 7. Open questions for the owner

1. **What `suggest` should mean.**
   - reform.py describes `suggest` as "a classification read from the filing's notes". That is a company-specific reading that can differ from the default `cls`, for example equity-method investments that are held purely as investments, or cash that is clearly operating.
   - Training on `LINES` defaults teaches the model to repeat the default, which the page already shows. For a tag that is in the table, a lookup gives the same answer exactly.
   - Option (a): keep the defaults as the training target, as instructed. Then the model's real use is unseen or company-specific tags, and the held-out evaluation measures that.
   - Option (b): add a small, human-reviewed set where a note supports a deviation from the default, with a quote. Only that set would justify a `suggest` that differs from `cls`.
   - Which do you want? The current draft does (a).
2. **Task B destination.** history.py and reform.py have no field for MD&A drivers. Will the cloud-side schema add one, or should task B be deferred?
3. **Human review.** Who reviews A labels and B spans, and how many hours are available? Without review they stay `rule_derived` and their scores are not trustworthy.
4. **Companies.** Reuse the 30 companies from run `20261016T171524Z` with a re-split, or use fresh ones? Fresh companies avoid overlap with earlier tests.

## 8. Planned split targets (confirmed after token profiling)

| Task | Train | Dev | Sealed test |
| --- | --- | --- | --- |
| A revision_reason | ~160 | ~50 | ~50 |
| B mdna_driver_amount | ~300 | ~80 | ~80 |
| C bs_line_classification | ~800 (53 tags) | ~200 | ~200 (incl. 13 held-out tags) |

These are planning targets. Actual counts, per-label and per-tag breakdowns, hashes and exclusions will go into the frozen card.
