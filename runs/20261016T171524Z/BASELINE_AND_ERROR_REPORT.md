# BASELINE AND ERROR REPORT

Created by ChatGPT (OpenAI).

Historical benchmark, already opened; not a fresh tuning set.

| Model | Baseline dev | Champion dev | Final test |
| --- | --- | --- | --- |
| smol17 | 0.013888888888888888 | 0.5694444444444444 | 65/108 observed; expected 108 (completed) |
| math15 | 0.0 | 0.875 | 39/48 observed; expected 48 (completed) |
| qwen4 | 0.0 | 0.9722222222222222 | 100/108 observed; expected 108 (completed) |
| qwen17 | 0.3055555555555556 | 0.8194444444444444 | 59/72 observed; expected 108 (stopped) |
| qwen06 | 0.20833333333333334 | 0.20833333333333334 | not run |

Raw old-test failures are historical-errors.json. The Math score covers 4 tasks; general scores cover 9. Arithmetic uses numeric tolerances; JSON format and source ID reproduction are not proof of evidence support. The 1.7B partial test must not be presented as a full test. Exact decoding, revision, question denominators and raw outputs are preserved in archive/*/*validation.json and *test.json. General historical inference: greedy max_new_tokens=192, no thinking, batch 2 except 4B batch 1; FP16 for small models, NF4 quantized 4B. Latencies are recorded in each score JSON; they include evaluation after load, not full end-to-end load time.

## Reconciled metrics

Exact denominators, JSON pass, joint correctness, source-ID reproduction and measured evaluation latency for every preserved completed validation artifact are in historical-metrics.json. Evidence entailment is not independently verified. Baselines and adapters are comparable within each recorded model/task/decoding setup; cross-model precision and Math task differences remain explicit. No missing baseline was inferred from zero interface scores.

New fixed development baseline status: completed; saved raw questions: 48. This uses NF4/BF16 and therefore is not a re-run of the old FP16 small-model experiment.
