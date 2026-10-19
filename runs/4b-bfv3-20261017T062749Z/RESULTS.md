# Qwen3-4B continuation on basic-finance-v3 — results

Created by Claude (Anthropic), 2026-10-17. Owner decision: train 4B on basic-finance-v3 and use no temperature cutoff. 8B and v2 were not used.

## Setup

- **Start:** the 4B champion adapter, `runs/20261016T171524Z/archive/qwen4`. Adapter warm-start with a fresh optimizer.
- **Data:** `runs/corpus-v3-20261016T230644Z`, 3600 training rows. Validation loss used the 138 dev rows of the 13 dev-protocol companies. The corpus sealed test was not read.
- **Training:** NF4/BF16 QLoRA, rank 8 on q_proj and v_proj, context 384, microbatch 1, gradient accumulation 4, learning rate 5e-5. 900 steps, which is one epoch. Exit 0, no OOM.
- **Wall time:** 1 h 56 min (train_runtime 6966 s).
- **Resources:** peak CUDA allocation 4741 MiB. The maximum sampled GPU temperature during training was 86 °C.
- **Loss:** mean train loss 0.0179. Validation loss by checkpoint:

| Step | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Val loss | 0.0227 | 0.0129 | 0.0162 | 0.0076 | 0.0082 | 0.0109 | 0.0092 | 0.0074 | **0.0061** |

- **Evaluated adapter:** `train/`, which is the checkpoint-900 weights (the lowest validation loss).
- **Decoding:** greedy, thinking disabled. Scoring: `bfv3_4b.py` (bfv3 uses the same scoring as train8b; Gate 2 uses the same scoring as evaluate_lab).

## Results

| Protocol | Metric | Champion (before) | After 900 steps |
| --- | --- | --- | --- |
| basic-finance-v3 dev, 40 questions | joint correct | 26/40 | **39/40** |
| | macro | 65.0% | **97.5%** |
| | numeric value | 13/26 | 25/26 |
| | valid JSON / source_id | 38 / 38 | 40 / 40 |
| Gate 2 dev, 48 questions | joint correct | 29/48 | **20/48** |
| | macro (19 tasks) | 66.7% | **45.6%** |
| | historical regression | 18/18 | **12/18** |
| | field_extraction | 3/3 | 0/3 |

For reference, the 8B basic-finance-v3 run reached 65.0% on the same 40-question protocol (`runs/8b-v3-20261016T230702Z`).

## Interpretation

- **The basic-finance-v3 gain is in-distribution.** Training and dev rows come from the same generator and templates, with different numbers and entities. The gain shows that the model learned these task formats. It does not show financial reasoning on real filings.
- **Gate 2 regression is mostly output-contract drift.**
  - On the old prompts, the model now often writes the answer under `calculation` instead of `value`.
  - In field_extraction it drops `source_id` and adds extra keys.
  - Several lost answers have the right number under the wrong key, for example free cash flow 406, total accruals −820 and closing reserve 600.
  - Others are real arithmetic or formula errors: the accrual ratio and one reserve case.
- **Decision:** not promoted. The predeclared Gate 2 retention criterion (historical regression and per-task retention) fails clearly. The champion stays `archive/qwen4`.

## Next-step options (not started)

- Mix replay rows in the old output contract (Gate 2 train families) with basic-finance-v3, then retrain from the champion.
- Use a shorter or lower-LR continuation, choosing the checkpoint by a combined bfv3 + Gate 2 generation score instead of validation loss alone.
