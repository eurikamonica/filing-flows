# EVALUATION REPORT

Created by ChatGPT (OpenAI).

Development comparison only. No new sealed-test scoring.

| Metric | Starting champion | Continued candidate |
| --- | --- | --- |
| new_correct | 11 | 16 |
| regression_correct | 18 | 17 |
| valid_json | 48 | 48 |
| content_correct | 30 | 33 |
| source_id_correct | 29 | 32 |
| latency_p50_s | 20.585268399998313 | 8.189276900004188 |
| macro_accuracy | 0.6666666666666666 | 0.7280701754385965 |

Predeclared gate: {"new_dev_improvement": true, "historical_retention": true, "format_retention": true, "abstention_retention": true, "latency": true, "per_task_retention": true}

Task counts and raw answers are baseline.json and candidate.json. Evidence support remains a limited supplied-context check, not an SEC entailment audit. Final test is still sealed; further tuning must not inspect it.

## Detailed development counts

The new pilot has 30 questions (3/task); historical validation regression has 18 (2/task). Combined macro is the mean of 19 task accuracies, not the 48-question micro accuracy. Neither is the 108-question historical test score.

| Task | Starting correct/rows | Continued correct/rows |
| --- | --- | --- |
| accrual_ratio | 0/3 | 0/3 |
| amended_ytd | 0/3 | 0/3 |
| basic_instruction | 0/3 | 3/3 |
| evidence_abstention | 0/3 | 0/3 |
| excerpt_heading | 3/3 | 3/3 |
| field_extraction | 3/3 | 3/3 |
| filing_route | 0/3 | 0/3 |
| missing_field | 2/3 | 3/3 |
| reserve_calculation | 0/3 | 1/3 |
| table_location | 3/3 | 3/3 |
| regression:Compute free cash flow. | 2/2 | 2/2 |
| regression:Compute the annual accrual ratio. | 2/2 | 1/2 |
| regression:Compute the closing reserve; no other movements. | 2/2 | 2/2 |
| regression:Compute total accruals. | 2/2 | 2/2 |
| regression:chart_data | 2/2 | 2/2 |
| regression:field_extraction | 2/2 | 2/2 |
| regression:filing_type | 2/2 | 2/2 |
| regression:missing_data | 2/2 | 2/2 |
| regression:note_provenance | 2/2 | 2/2 |

Source-ID denominators: baseline 33, candidate 33. Content excludes source_id; JSON failures still count as wrong. Actual issuer-evidence entailment is not independently scored.

## Data quality overrides use approval

Raw selection.json records the original metric gate pass and is not edited. Subsequent semantic review found an underspecified basic_instruction contract (and implicit output keys in other families). These v1 numbers are engineering diagnostics, not a clean capability-improvement benchmark. quality-decision.json rejects candidate promotion and retains the starting champion. Corrected data-v2 is prospective and has never been trained/evaluated; neither v1 nor v2 sealed test was scored. The full original-note/human-review Gate 1 objective remains unmet. See DATA_QUALITY_REVIEW.md. No extra GPU run was launched to obtain a preferred result.

## Resource measurements

Training phase summaries with actual token counts, optimizer-active time and throughput are in phase-summary.json; per-step temperature/physical GPU readings and RSS are in outputs/*/memory.jsonl. Job wall times are in jobs.jsonl. Wall time minus optimizer-active time includes model loading, CPU packing, validation, save and teardown; these components were not individually timed. No explicit cooling/retry loop ran.

```json
[
  {
    "run": "first-epoch",
    "status": "completed",
    "global_step": 60,
    "resumed_global_step": 0,
    "stop_reason": null,
    "error": null,
    "memory": {
      "cuda_available": true,
      "device": "NVIDIA GeForce RTX 3050 6GB Laptop GPU",
      "allocated_mib": 3334.13623046875,
      "reserved_mib": 5326.0,
      "peak_allocated_mib": 5032.9140625,
      "peak_reserved_mib": 5326.0,
      "free_mib": 0.0,
      "total_mib": 6143.5
    },
    "active_optimizer_seconds": 427.2263643001206,
    "process_rss_mib": 1784.50390625,
    "useful_tokens_per_training_epoch": 163016,
    "supervised_tokens_per_training_epoch": 52539,
    "consumed_nonpadding_tokens": 62383,
    "consumed_supervised_tokens": 20264,
    "useful_nonpadding_tokens_per_second": 146.01861030321808
  },
  {
    "run": "smoke",
    "status": "completed",
    "global_step": 20,
    "resumed_global_step": 10,
    "stop_reason": null,
    "error": null,
    "memory": {
      "cuda_available": true,
      "device": "NVIDIA GeForce RTX 3050 6GB Laptop GPU",
      "allocated_mib": 3334.13623046875,
      "reserved_mib": 5340.0,
      "peak_allocated_mib": 5030.80859375,
      "peak_reserved_mib": 5340.0,
      "free_mib": 0.0,
      "total_mib": 6143.5
    },
    "active_optimizer_seconds": 75.80791489998228,
    "process_rss_mib": 1762.90625,
    "useful_tokens_per_training_epoch": 163016,
    "supervised_tokens_per_training_epoch": 52539,
    "consumed_nonpadding_tokens": 10361,
    "consumed_supervised_tokens": 3433,
    "useful_nonpadding_tokens_per_second": 136.6743830597354
  }
]
```

The smoke test consists of 10 initial updates plus 10 resumed updates (global_step 20). It is not 10+20 new updates. The main run has 60 fresh updates and is initialized from the archived champion rather than the smoke weights. Sampled resource peaks are in sampled-resource-peaks.json.

Gate 3 merge/export and Gate 4 scaling were prepared/deferred, not executed. Gate 5 sealed testing is not part of this bounded Gate 2 run. Next safe read-only command from Beta: `.\.venv\Scripts\python.exe model-expansion-lab/status.py`. Re-running protocol.py execute against this completed run is not a supported continuation command; a future experiment needs a newly declared run/budget and appropriate compatible checkpoint.

## Measured development comparison

![Fixed development comparison](DEV_COMPARISON.png)
