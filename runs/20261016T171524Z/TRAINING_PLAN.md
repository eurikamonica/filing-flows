# TRAINING PLAN

Created by ChatGPT (OpenAI).

Gate 2 predeclared protocol:

```json
{
  "author": "Created by ChatGPT (OpenAI)",
  "gate2_authorized": true,
  "base": "Qwen/Qwen3-4B",
  "revision": "1cfa9a7208912126459214e8b04321603b3df60c",
  "rank": 8,
  "modules": [
    "q_proj",
    "v_proj"
  ],
  "dtype": "bfloat16",
  "quantization": "NF4 double quant",
  "max_length": 512,
  "microbatch": 1,
  "accumulation": 4,
  "smoke_steps": 20,
  "verification_pause_step": 10,
  "first_run_max_steps": 60,
  "first_run_wall_seconds": 1200,
  "total_wall_seconds": 3600,
  "temperature_stop_c": 86,
  "thermal_policy_origin": "Existing device experiment policy; operational cutoff, not an OEM safety certification",
  "min_free_gib": 16,
  "new_optimizer_on_main": true,
  "sealed_test_allowed": false,
  "selection": {
    "new_dev_correct_improvement": 1,
    "max_per_task_regression_questions": 1,
    "max_historical_regression_questions": 1,
    "max_format_regression_questions": 1,
    "abstention_no_regression": true,
    "latency_p50_max_factor": 2,
    "latency_p50_slack_seconds": 1
  },
  "data_sha256": "30cabd3fc025affb3af5c2b47fbf88c39f76b0f609ec7d0fee91654a6f16d2b6",
  "dev_sha256": "6cc07dcfebfd198430fcbc7c024b1e6d13e126143cee4a89290daa71a5978714"
}
```

One baseline, one 20-step smoke with a deliberate step-10 full resume, at most one 60-step bounded first-epoch run from the immutable historical champion (fresh optimizer/scheduler). It is a partial first epoch if 60 steps do not cover the corpus. No model sweep, rank change, auto-retry, offload or silent answer truncation. Stop the protocol on any OOM/nonfinite gradient/checkpoint error or temperature pause; do not keep cycling. A temporary loader-only test placeholder never exposes the real sealed test. Evaluation is greedy NF4/BF16, max_new_tokens=192, batch 1 and the same evidence budget before/after.

Counts are small (three dev questions/task, two regression/task); one-question tolerances are exploratory and do not establish production quality. Test remains sealed after this Gate 2 request. Both useful nonpadding input+answer tokens and supervised answer tokens are measured; active optimizer time is distinct from wall/load/save time.
