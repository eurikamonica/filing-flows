# Qwen3-4B continuation: basic-finance-v3 plus old-contract replay — results

Created by Claude (Anthropic), 2026-10-17. Owner instruction: continue training 4B; no temperature cutoff. 8B and v2 were not used.

## Setup

- **Start:** the 4B champion, `runs/20261016T171524Z/archive/qwen4`. Adapter warm-start with a fresh optimizer. Not resumed from the bfv3-only run.
- **Training mix:** 4123 rows (`plan.json`):
  - basic-finance-v3: 2400 rows, 120 per task.
  - Historical overnight corpus `initial-corpus-v4`, train split only: 1202 rows, stratified by task.
  - Gate 2 v1 train: 521 rows. basic_instruction is excluded because of its defective contract, and 11 rows are excluded for being over 384 tokens.
- **Exclusions:** all inputs of both evaluation protocols are excluded from training. The corpus sealed test was not read.
- **Validation (loss only):** the 138 basic-finance-v3 dev rows of the 13 protocol companies.
- **Hyperparameters:** NF4/BF16 QLoRA, rank 8 on q_proj and v_proj, context 384, microbatch 1, gradient accumulation 4, learning rate 5e-5, 900 steps. Exit 0, no OOM.
- **Wall time:** 1 h 54 min.
- **Resources:** peak CUDA allocation 4893 MiB. Maximum sampled GPU temperature 83 °C.
- **Loss:** mean train loss 0.0311. Validation loss by checkpoint:

| Step | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Val loss | 0.0589 | 0.0477 | 0.0324 | 0.0170 | 0.0165 | 0.0123 | 0.0119 | 0.0123 | **0.0115** |

- **Evaluated adapter:** `train/`, the checkpoint-900 weights. That checkpoint is both the best and the last one, so no separate last-checkpoint evaluation was needed.

## Results (same evaluator, greedy decoding)

| Protocol | Metric | Champion | bfv3 only (`4b-bfv3-20261017T062749Z`) | **bfv3 + replay** |
| --- | --- | --- | --- | --- |
| basic-finance-v3 dev, 40 questions | joint correct | 26/40 | 39/40 | **36/40** |
| | macro | 65.0% | 97.5% | **90.0%** |
| | numeric value | 13/26 | 25/26 | 22/26 |
| Gate 2 dev, 48 questions | joint correct | 29/48 | 20/48 | **36/48** |
| | macro (19 tasks) | 66.7% | 45.6% | **78.1%** |
| | new dev questions (30) | 11 | 8 | **19** |
| | historical regression (18) | 18 | 12 | **17** |
| | valid JSON | 48 | 47 | 48 |
| | median latency | 21.4 s | 21.6 s | 21.3 s |

On the same 40-question protocol, the 8B basic-finance-v3 run reached 65.0%.

**Gate 2 per-task changes, champion → mix:**

| Task | Champion | Mix |
| --- | --- | --- |
| amended_ytd | 0/3 | 2/3 |
| evidence_abstention | 0/3 | 3/3 |
| missing_field | 2/3 | 3/3 |
| reserve_calculation | 0/3 | 2/3 |
| regression: annual accrual ratio | 2/2 | 1/2 |

The single lost regression question is a sign error: the model answered +0.02 where −0.02 was expected.

**Remaining basic-finance-v3 errors:**
- Two accrual_ratio answers forget to divide by the average assets of 100: it answered −172 instead of −1.72, and −580 instead of −5.8. Labels in all three sources use fractions, so this is a model step omission, not a label conflict.
- One cash_conversion answer is rounded to 0.5 where 0.5025 was expected.
- One reserve_calculation answer is 692 where 702 was expected.

## Gate 2 predeclared selection criteria (`runs/20261016T171524Z/plan.json`)

| Criterion | Requirement | Mix vs champion | Pass |
| --- | --- | --- | --- |
| New dev improvement | ≥ +1 question | 11 → 19 | yes |
| Historical regression loss | ≤ 1 question | 18 → 17 | yes |
| Format regression | ≤ 1 question | 48 → 48 | yes |
| Abstention | no regression | 0 → 3 | yes |
| Per-task regression | ≤ 1 question | worst: accrual ratio −1 | yes |
| Latency p50 | ≤ 2× + 1 s | 21.4 s → 21.3 s | yes |

## Caveats

- The gains on both protocols are in-distribution. The Gate 2 new tasks improved through v1 replay rows from the same generator, and the bfv3 rows come from the same templates as their dev rows. This is not evidence of reading real filings.
- Gate 2 dev48 has now been used to compare several candidates, so it is no longer a clean selection set.
- The v1 data carries known contract limitations (DATA_QUALITY_REVIEW.md).
- **Promotion is the owner's decision.** This run passes the mechanical gate, but nothing has been promoted. The champion remains `archive/qwen4` until the owner decides.
