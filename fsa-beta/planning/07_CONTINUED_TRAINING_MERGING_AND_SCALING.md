# 07 — Continued training, adapter merging and genuine parameter scaling

Created by ChatGPT (OpenAI), October 16, 2026.

**Status: implementation instructions, not executed training.** This document adds no model weights, changes no running controller and deploys nothing. Intended for local Codex, working in an isolated experiment directory. Training and evaluation content should be English; progress explanations to the owner should be Chinese.

## 1. Interpret the supplied overnight report correctly

The user supplied a report with `finished_budget / ended`, a deadline of October 16 at 10:07 New York time, and these results:

| Candidate | Best validation | Reported final test | Completed cycles |
| --- | ---: | ---: | ---: |
| SmolLM2-1.7B-Instruct | 56.94% | 60.19% | 4 |
| Qwen2.5-Math-1.5B-Instruct | 87.50% | 81.25% | 1 |
| Qwen3-4B | 97.22% | 92.59% | 2 |
| Qwen3-1.7B | 81.94% | absent | 1 |
| Qwen3-0.6B | 20.83% | absent | 0 |

These numbers are user-reported, not independently reproduced here. The previous audit described nine general tasks and four arithmetic-only tasks; verify that this remains true for the final report. The math-only score is not directly comparable with the general score.

`training_incomplete` may describe the most recent attempted cycle while an earlier completed champion exists. It does not prove all prior training was lost. Inspect manifests rather than deleting or discarding artifacts. A score with zero completed cycles, as for 0.6B, may be a baseline or another artifact: identify its origin before calling it a trained result.

The final event says the Qwen3-1.7B test process ended with code 0 at 10:07:43 New York time, approximately 16 seconds beyond the nominal deadline. Its score is absent from the summary. Read its output, completion flag, question count and state; do not invent a result or rerun it blindly. Exit code 0 alone does not establish a complete evaluation.

The experiment reports that it ended. Verify live processes before starting another job; do not treat this report as proof that every Python process has stopped.

## 2. Define the goal and the meaning of B

B denotes approximately one billion model parameters, not the number of training examples or the sum of models on disk. No universal parameter threshold guarantees intelligence or financial reliability.

| Route | What changes | Correct description |
| --- | --- | --- |
| Continue training one 4B adapter | Learned task behavior | Fine-tuned 4B-based model |
| Merge adapter into its base | Packaging of learned delta | Standalone fine-tuned model, same base dimensions |
| Combine compatible adapters | Learned delta combination | Merged adapter/model; not automatically larger |
| Route requests across separate models | System behavior | Multi-model system, not one dense model |
| Distill approved teacher examples into 4B | Student behavior | Distilled 4B-based model |
| Adopt pretrained 8B and fine-tune it | Larger pretrained base | Genuine larger-parameter model, not grown from the old 4B |
| Add independent layers/width and train | Architecture and unique weights | Experimental expanded architecture; improvement must be demonstrated |

Never claim SmolLM2 1.7B + Qwen Math 1.5B + Qwen3 4B = a 7.2B dense model. Their weight shapes, tokenizers, architectures and learned representations are not interchangeable.

## 3. Immediate audit and preservation

Before any GPU work:

1. Read workspace instructions, git status, controller state, completed manifests and actual model revisions.
2. Preserve each completed champion and its tokenizer, configs, data hashes and raw validation/test outputs in a fresh archive. Never overwrite the existing overnight archive.
3. Distinguish adapter-only files from full model checkpoints and full-resume checkpoints. Record missing optimizer/RNG/scheduler state explicitly.
4. Resolve the missing 1.7B test summary and the provenance of the 0.6B validation score using existing outputs only.
5. Compare baselines and adapters on the same task sets, including exact denominators, decoding settings and evidence budgets. Report format, field correctness, numeric accuracy, source-ID reproduction and actual evidence support separately.
6. Extract errors by topic without claiming the final test remains unopened. It has now been inspected and must not become a repeatedly optimized benchmark.

Do not modify live processes, shared environments, production files or another Codex worktree. Use a new branch/worktree and `fsa-beta/model-expansion-lab/` for additions, with unique run IDs and a separately configured runtime directory.

## 4. Recommended sequence

**Primary track:** audit and strengthen Qwen3-4B on realistic evidence tasks. It is the leading general-task candidate in the supplied results, not a proven general financial analyst.

**Efficiency track:** recover the existing 1.7B result and compare performance/latency on identical tasks. Keep it if its smaller footprint offers a useful tradeoff.

**Math track:** use deterministic Python for production arithmetic. Keep the math model as a separately measured experiment; do not let it replace numeric validation.

**Size track:** prepare an 8B feasibility package after the 4B experiment is stable. Do not start an automatic multi-model overnight sweep or assume more parameters will repair poor data.

**Architecture research track:** optional small depth-expansion experiment with independently copied weights. Keep separate from the reliable model and do not describe it as a trained large model before measurement.

## 5. Build the next dataset and a new untouched test

The old test is now a historical benchmark. Before training again, create a new versioned train/dev/test split by company and document, controlling repeated annual footnotes, source paragraphs, paraphrases and synthetic template families. Keep the new final test sealed until a predeclared candidate is selected. Freeze hashes and split membership.

Start with a deliberately small audited set, then scale according to observed coverage. A planning target of several hundred reviewed training examples and 100–200 reviewed evaluation questions is a workflow target, not a guarantee of adequacy. Report counts per task and uncertainty; do not hide weak tasks behind a high average.

Include:

- Item and Note routing; company-specific numbering and cross-references.
- Original note/table extraction with years, units, negatives and source location.
- Evidence-grounded explanations and unsupported-claim rejection.
- Missing data, conflicting periods, amended filings and YTD-versus-quarter cases.
- Reserve utilization versus reversal, claims and estimate revisions.
- Structured calculation requests checked by independent code.
- A small regression set for previously working tasks and basic English instruction following.

Maintain observed, derived, hypothetical and teacher-generated labels. SEC companyfacts/website summary JSON is not a full footnote corpus. Do not train on fabricated source IDs or unverified teacher answers. Open textbooks require documented permissions; free access is not a universal training license.

Use CPU parsing, pretokenization and retrieval. Preserve table headers and relevant context; measure complete input-plus-answer token lengths. No silent truncation of gold answers. Keep RAG evidence in the inference interface, so new filings need not be memorized through retraining.

## 6. Continue Qwen3-4B with bounded experiments

Check exactly how the previously reported 4B run fit on the machine: quantization, precision, offload, actual context, trainable modules and batch. Do not infer configuration or spare capacity from successful completion alone.

1. Load an immutable copy of the selected champion; run a small regression baseline.
2. For continuation on a new corpus, start a new named run from adapter weights with explicitly fresh optimizer/scheduler state. Full checkpoint resume is reserved for compatible interrupted runs, retaining its original configuration and data assumptions.
3. Use the already verified environment. Freeze dependency versions and model/tokenizer revisions.
4. Start with one GPU job, microbatch 1, gradient checkpointing, training cache disabled and assistant-answer-only supervision where correctly supported.
5. Keep rank/modules initially unchanged. Later compare rank 8 versus 16 only as a controlled experiment; higher rank does not change the base architecture to more B.
6. Select context length from actual sample needs. Benchmark 512 only for genuinely short complete examples, then 1024 if feasible; do not mutilate note tasks to fit an arbitrary length.
7. Run 20–50 optimizer steps as a smoke test with save/resume verification. Then run a bounded first epoch with a declared maximum step/time budget.
8. Select using development task metrics and inspect loss separately. Keep numerical inference and evidence correctness distinct from JSON validity.
9. Stop on OOM, nonfinite loss, corrupted checkpoints or persistent thermal cycling. Preserve the last complete checkpoint and report the cause; do not endlessly retry identical failures.
10. Log useful nonpadding tokens/s, optimizer steps, GPU memory, RAM, wall time spent training versus loading/cooling, and temperature. Keep effective batch comparable when benchmarking microbatch changes.

Set thermal limits from the actual device/OEM context and existing validated policy, not an invented universal safe temperature. Offload is an explicit speed/capacity experiment; inference dispatch is not automatically training-compatible.

A proposed development gate: no material regression on previously supported tasks, improved evidence/abstention behavior, and feasible latency. Define quantitative tolerances before running, based on sample sizes and intended use, rather than choosing them after seeing a favored candidate's score.

## 7. Merge adapters without misrepresenting size

### A. Adapter into its own base

Verify exact base revision, architecture, tokenizer, vocabulary and target module compatibility. Reload the original base at a supported nonquantized precision if required by the chosen merge path. Apply the correct adapter and use the framework's supported merge/export procedure. Do not assume every quantized model/adapter combination supports merging.

Write to a new output directory. Test fixed-prompt outputs and, where practical, logit differences before and after merge under matching precision. Small floating-point differences may occur; unexplained semantic regressions fail the export. Re-quantize a separate copy only after this check and evaluate that copy again.

### B. Multiple adapters from the same base

Only consider adapters with verified compatible provenance. Compare single-adapter, sequential multi-task fine-tuning, and a small fixed grid of weighted/TIES/DARE combinations on development data. PEFT documents adapter-merging methods [S1]. Merging can lose abilities; improvement is not guaranteed.

A cycle-2 adapter initialized from cycle-1 already carries its inherited update. Naively adding those two adapters can double-count their shared history. Record lineage; do not treat successive checkpoints as independent specialists.

Never merge the existing SmolLM2 and Qwen adapters by direct tensor averaging. Different Qwen sizes are not compatible merely because they share a family name.

### C. Cross-family knowledge transfer

Use independent model routing or reviewed teacher/student examples with permitted use and clear origin. Teachers run serially on limited hardware. Distillation transfers behavior into the student's existing size; it does not add the teachers' parameter counts.

## 8. A genuine larger base: 8B feasibility

Qwen3-8B is a documented larger pretrained candidate [S2], selected as a comparable family example rather than a claim that it is the newest/best option. Pin and inspect its actual revision, configuration and license before use. Existing 4B adapter tensors cannot simply be loaded into 8B; train a new adapter on the 8B base.

Approximate raw weight storage, decimal GB, ignoring metadata and runtime:

| Nominal size | FP16/BF16 (2 bytes/parameter) | Ideal 4-bit (0.5 bytes/parameter) |
| --- | ---: | ---: |
| 4B | 8 GB | 2 GB |
| 8B | 16 GB | 4 GB |
| 14B | 28 GB | 7 GB |

These are not total training-memory estimates. Quantization metadata, nonquantized tensors, activations, gradients, optimizer state, temporary buffers and generation KV cache add memory. A 6GB GPU is not guaranteed to train an 8B model merely because its ideal 4-bit weights are 4GB. CPU/RAM offload does not make transfers free or create GPU-speed memory.

Local work: prepare data, profile the existing 4B and estimate 8B loading headroom. Do not auto-download large weights without checking storage and experiment scope. If feasible, attempt only a bounded supported 8B preflight and a tiny training smoke test, not an overnight promise.

If capacity/throughput is inadequate, produce a portable training package for separately selected higher-memory hardware: pinned environment, dataset manifests, exact base revision, tested command, resume logic, budgets, output paths and evaluation script. Do not rent hardware or activate a paid service automatically. Hardware selection requires profiling; no fixed GPU capacity or free quota is guaranteed here.

Outcome naming: "8B financial-domain fine-tune based on [exact model]". Do not call it a foundation model pretrained from scratch.

## 9. Genuine architecture expansion: research-only

Adding independent layers/width can increase unique parameters, but it does not create learned competence automatically. Start with a small proof of concept, not an attempt to train a competitive large foundation model from scratch on the laptop.

### Depth-expansion pilot

1. Copy a small base into a new architecture experiment; preserve tokenizer and provenance.
2. Inspect its configuration and block implementation before changing layer count. Select a small number of inserted blocks rather than blindly doubling all layers.
3. Use independent parameter storage for inserted blocks and an explicit old-to-new layer map. A function-preserving or near-identity initialization must be derived for the actual residual-block implementation and tested, not assumed from simple copying.
4. Verify no accidental tensor aliases, valid position/cache behavior, complete state-dict loading and finite forward/backward passes. Test save/reload before training.
5. Report both unique parameter count and trainable parameter count. Count distinct weights correctly, including tied embeddings. For quantized models, report logical weight elements separately from packed storage size.
6. Compare the original and untrained expanded model on fixed prompts and held-out language loss. Large regression at initialization is a reason to revise the expansion, not to hide the baseline.
7. Use licensed domain text for a bounded adaptation phase, then reviewed instruction examples. Log token budget, trainable/frozen layers, retention tasks and evaluation.
8. Evaluate against the original model at comparable data and compute budgets. Keep the expanded model only if it shows a useful measured tradeoff.

Some layer-replication implementations share base weights while giving replicas separate adapters. That increases computation and adapter capacity but must not be represented as the same number of fully independent new dense weights. Inspect installed PEFT behavior and report unique storage, not just apparent layer count [S3].

A wider network requires coordinated attention, feed-forward, normalization and sometimes head-dimension changes. MoE adds routing, expert initialization and load-balancing requirements. Both are deferred until the small depth pilot is reliable. A routed collection of existing complete models is not automatically a trained MoE network.

No model should be labeled "expanded to 8B" without a measured unique logical parameter count close to that claim and an architecture manifest. Parameter growth and capability improvement are separate acceptance criteria.

## 10. Deliverables and execution gates for local Codex

Add new files only under the isolated experiment directory:

- AUDIT.md: report reconciliation, actual process state and artifact inventory.
- DATASET_CARD.md: provenance, permissions, coverage, split hashes and contamination checks.
- BASELINE_AND_ERROR_REPORT.md: comparable tasks, counts, raw failures and latency.
- TRAINING_PLAN.md: run configuration, limits, precision, resume and stop conditions.
- MERGE_COMPATIBILITY.md: revisions, tokenizer, lineage, methods and equivalence results.
- PARAMETER_SCALING_REPORT.md: original/expanded unique and trainable counts, memory and initialization effects.
- EVALUATION_REPORT.md: development selection and one new sealed-test result for the preselected candidate.
- MODEL_CARD.md: exact base/adapter revisions, scope, limits and measured capability.
- manifest.json: hashes and all artifact paths; weights/checkpoints remain outside source control.

**Gate 0:** read-only audit and artifact preservation. Resolve absent/inconsistent scores.
**Gate 1:** fresh data/splits and retrieval baseline; no GPU required.
**Gate 2:** one controlled 4B continuation and development comparison.
**Gate 3:** compatible merge/export verification, if it provides a concrete deployment benefit.
**Gate 4:** choose either an 8B pretrained-base pilot or independent-layer research pilot; do not launch both automatically.
**Gate 5:** evaluate the preselected candidate on the new sealed test, produce model card and stop.

Once a final test is opened, further tuning requires a newly designated untouched final benchmark. Do not rerun a test until a desired score appears. Do not publish the model/site or modify production inference as part of this task.

## 11. Pasteable local Codex instruction

Read this entire document and the local workspace instructions. Execute Gate 0 and Gate 1 now using a new isolated worktree/directory. Preserve the completed overnight champions and identify the missing Qwen3-1.7B final-test result from existing artifacts. Do not interrupt other processes or start competing GPU jobs. Reconcile report scores with actual task denominators and model revisions. Prepare a fresh company/document-separated development and sealed-test dataset, keeping the old test as a historical benchmark. Then, if resource ownership and data readiness are established, execute one bounded Qwen3-4B continuation smoke test and at most the predeclared first training run. Use English training data and docs, Chinese progress reports, and ChatGPT (OpenAI) attribution. Prepare compatible adapter merging and parameter-scaling scripts as separate experiments, but do not claim merged families form one larger model. Do not rent compute, deploy, publish or start an unbounded overnight loop. Report actual execution, failed gates and the exact next runnable command separately from proposed work.

## Sources

Official sources consulted October 16, 2026. Installed versions must be checked before implementing their APIs.

- [S1: PEFT model merging](https://huggingface.co/docs/peft/developer_guides/model_merging)
- [S2: Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B)
- [S3: PEFT LoRA and layer replication](https://huggingface.co/docs/peft/developer_guides/lora)
- [PEFT quantization](https://huggingface.co/docs/peft/developer_guides/quantization)
