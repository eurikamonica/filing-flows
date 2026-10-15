# A private financial AI: model choices and training path

Created by ChatGPT (OpenAI), October 15, 2026.

## Free weights are available

| Model | Published license | Suggested role in this Beta |
| --- | --- | --- |
| [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) | Apache 2.0 | First LoRA training/inference experiment |
| [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B) | Apache 2.0 | Larger bilingual specialist candidate after evaluating the small model |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | MIT | Alternative instruction model; not wired into the supplied trainer |
| [Gemma 3 1B IT](https://huggingface.co/google/gemma-3-1b-it) | Gemma terms; license acceptance required | Alternative small open-weight model, distinct from the hosted Gemini API |

These are practical candidates, not a claim that they are the latest or best models. Their official model cards/licenses were checked for this document. Free download does not mean free GPU time, hosting or electricity. Colab's free resources and GPU availability are variable, as its [FAQ](https://research.google.com/colaboratory/faq.html) explains.

Start with Qwen3-0.6B and short contexts. The supplied FP32 LoRA script favors simplicity and needs much more memory than quantized inference. Parameter storage alone is about 2.4 GB for 0.6B and 6.8 GB for 1.7B; actual training memory also includes activations, adapter gradients, runtime overhead and temporary buffers. A 16 GB GPU is a reasonable experiment target for the smaller model, not a tested guarantee. CPU execution is possible but slow. Measure peak memory before moving to larger models. QLoRA is a possible later optimization, not implemented here.

## Gemini and distillation

Technically, supervised examples from a capable teacher can help train a smaller specialist, but data quality, licensing, compute and held-out evaluations determine whether it is useful. An API key does not expose Gemini weights.

The [Gemini API terms](https://ai.google.dev/gemini-api/terms), checked October 15, 2026, restrict using the services to develop competing models and prohibit extracting or replicating service components. Personal use is not an explicit blanket exemption. The exact applicability to a specialized use requires checking the applicable terms/permission; this document does not conclude that every specialized training use is prohibited or permitted.

This Beta therefore separates Gemini explanations from independently authored training data. It does not harvest Gemini answers for training. If permission is established later, a teacher-data path would still need evidence checks, human review, provenance, source/date splits, numerical checks and comparison against the untuned base model. Never use Google Search grounding results as a training corpus under the cited grounding terms.

## What has actually been trained here

`student.py` trains a tiny Naive Bayes question-topic classifier from independent English/Chinese phrases. The saved model is `models/router.json`. It routes questions to deterministic calculations, which is useful for a limited offline interface. It has four topics and an unknown fallback. Its small developer-written evaluation set is a smoke test, not evidence of broad FSA competence.

No Qwen adapter has been trained in this delivery. The following optional scripts make that next experiment reproducible once weights, dependencies and compute are available.

## Optional LoRA experiment

Keep ML dependencies in their own environment. On Windows, these commands avoid PowerShell activation scripts:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv\Scripts\python.exe training.py --out .runtime/training.jsonl
.\.venv\Scripts\python.exe train_lora.py --data .runtime/training.jsonl --out adapters/qwen-fsa-v1
.\.venv\Scripts\python.exe evaluate_lora.py --adapter adapters/qwen-fsa-v1 --data .runtime/training.jsonl
```

Run inside `fsa-beta`. Initial model loading downloads weights from Hugging Face; it is not offline until those files are cached. The trainer uses PEFT LoRA on attention projections, masks prompt tokens from loss, and preserves a separate validation split. It rejects oversized examples rather than silently removing answers. It never uploads an adapter. Dependencies are compatibility ranges, not a hardware-tested lockfile; record installed versions and the base-model revision for a reproducible serious run.

`training.py` produces 400 formula-generated examples from 100 synthetic entities: 240 training, 80 validation, 80 test. All examples from one entity stay in one split. They cover accruals, FCF, accrual ratio, and reserve arithmetic. This is a pipeline smoke corpus, far too narrow to establish real-filing understanding. `evaluate_lora.py` reports numeric accuracy on the test split; it does not score source citation, explanation quality, or hallucinations. Run equivalent evaluation on the base model before claiming improvement from fine-tuning.

## Building a useful real corpus

Use owned or appropriately licensed materials. Public accessibility alone is not a blanket training license. Preserve filing accession, company, reporting period, excerpt, units and the exact answer derivation. Do not treat third-party textbook solutions as freely reusable.

Recommended task groups are:

- Extract a reserve rollforward and identify each signed movement.
- Distinguish utilization from a release through earnings.
- Identify direct, YTD-derived and unavailable quarterly facts.
- Classify operating versus financing items with a stated policy.
- Explain accrual changes using cited evidence and alternatives.
- Identify missing information and abstain from unsupported claims.

Independent reviewed JSONL rows use `origin: human_authored`, `review: human_verified`, `company_id`, `split`, `input`, and `output`. The current loader accepts these and formula-verified independent rows. Review labels are provenance declarations, not proof that review happened.

Split by company and time, deduplicate source passages and questions, and keep restatements from leaking into earlier-vintage tests. Evaluate exact numerical accuracy, units/period accuracy, citation support, correct abstention, reserve classification and unsupported allegations. Compare retrieval plus the base model against the adapter. Training should improve measured performance, not just lower training loss.

For a practical assistant, keep arithmetic in the deterministic engine and use a model for extraction, question understanding and supported explanation. Fresh filings should be retrieved as evidence; model weights are not a current financial database.
