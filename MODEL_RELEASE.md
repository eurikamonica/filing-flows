# Qwen3-4B FSA lab model — release notes (2026-10-18)

> **Update 2026-10-19:** a continuous training loop now runs, see `CONTINUOUS_STATUS.md` and `continuous/PROTOCOL.md`.
> - **Current champion and its Q8_0 GGUF:** listed at the top of `CONTINUOUS_STATUS.md`. The GGUF is in `exports/<champion>/gguf/`.
> - **Exports of the 2026-10-18 champion (`qwen4-bfv3mix-20261017`):** the bf16 merge, Q8_0 and Q4_K_M described below are superseded. They are no longer in this branch snapshot. Its adapter remains in `champions/`.
> - **Branch history:** the remote branch is a single-commit snapshot, re-pushed every cycle. The full history is kept locally.

Created by Claude (Anthropic) at the owner's request. This branch is a self-contained lab snapshot. It holds code, reports, training and evaluation data, and model weights. It contains no website code and does not touch `main` or `narratives`.

## Model

The model is a Qwen/Qwen3-4B (revision `1cfa9a72…`) LoRA continuation, trained locally on an RTX 3050 6 GB.

| Artifact | Path | Size | Use |
| --- | --- | --- | --- |
| LoRA adapter (champion) | `champions/qwen4-bfv3mix-20261017/` | 12 MB | PEFT on the NF4 4-bit base, as trained |
| Merged model, bf16 safetensors | `exports/qwen4-bfv3mix-nf4merged-bf16/` (5 shards) | 7.6 GB | transformers |
| **GGUF Q8_0 (recommended)** | `exports/gguf/qwen3-4b-fsa-bfv3mix-Q8_0-0000{1,2,3}-of-00003.gguf` | 4.3 GB | llama.cpp / Ollama |
| GGUF Q4_K_M (not recommended) | `exports/gguf/qwen3-4b-fsa-bfv3mix-Q4_K_M-0000{1,2}-of-00002.gguf` | 2.5 GB | see results below |

**Storage and sharding:**
- Large files are stored with Git LFS.
- GitHub LFS rejects files over 2 GiB, so every weight file is split into shards under 1.9 GB.
- **GGUF:** the files are split with `llama-gguf-split`. Point llama.cpp at the first shard (`-m …-00001-of-0000N.gguf`) and it loads the remaining shards itself. To get a single file, use `llama-gguf-split --merge <first shard> out.gguf`. The split Q8_0 reproduces the unsplit result on basic-finance-v3 dev (36/40).
- **safetensors:** the shards are a byte-identical re-sharding of the merge (`RESHARD.md`).

**Checksums:** `champions/.../SHA256SUMS`, `exports/gguf/SHA256SUMS`, `exports/qwen4-bfv3mix-nf4merged-bf16/SHA256SUMS` and `merge-status.json`.

**How it was trained** (`runs/4b-bfv3mix-20261017T211441Z/`):
- Start: the Gate 0–2 4B champion.
- 900 QLoRA steps on 4123 rows, rank 8 on q_proj and v_proj, context 384, learning rate 5e-5.
- Training mix: basic-finance-v3 (2400 rows), the historical overnight corpus (1202 rows, train split) and Gate 2 v1 train rows (521). The historical and v1 rows replay the old output formats so the model does not forget them.

**How it was merged** (`merge_champion_nf4.py`): the adapter was trained on the NF4-quantized base. So the merge first dequantizes that NF4 base and then adds the LoRA delta. On 7 check prompts, the merged model's greedy outputs equal the NF4+LoRA reference exactly.

A first merge into the full-precision base is kept locally only (`exports/superseded-fp16-merge`, not published). Exported as Q8_0 GGUF it lost 8 of the Gate 2 questions, which is why the NF4-faithful merge replaced it.

**Prompting:** use the chat template with `enable_thinking=false`. Outputs are a single JSON object following the contract stated in the prompt.

## Evaluation (greedy decoding, development protocols)

| Protocol | Pre-continuation champion | Champion (NF4 + LoRA) | GGUF Q8_0 | GGUF Q4_K_M |
| --- | --- | --- | --- | --- |
| basic-finance-v3 dev, 40 questions | 26 | 36 | 36 | 34 |
| Gate 2 dev, 48 questions (30 new + 18 regression) | 29 | 36 | 36 | 20 |
| of which historical regression | 18/18 | 17/18 | 17/18 | 12/18 |
| basic-finance-v4 dev, 90 questions (fresh) | — | 87 | 86 | 81 |
| Median latency (basic-finance-v4) | — | 4.6 s | 0.52 s | 0.40 s |

Q4_K_M keeps most basic-finance accuracy but loses the old output contracts (Gate 2: 36 → 20). Use Q8_0.

**Caveats:**
- All protocols are in-distribution: they come from the same generators as the training data.
- Gate 2 dev has been used to compare several candidates.
- None of this demonstrates reading real filings.
- No sealed test has been scored.

## Data in this branch

| Dataset | Path | Rows train / dev / sealed | Notes |
| --- | --- | --- | --- |
| Gate 2 v1 / v2 | `runs/20261016T171524Z/data*/` | 628 / 218 / 237 (v1) | v2 was never trained on |
| basic-finance-v3 | `runs/corpus-v3-20261016T230644Z/` | 3600 / 160 / 160 | built by an earlier Codex session |
| basic-finance-v4 | `runs/corpus-bf-v4-20261018T052227Z/` | 6225 / 358 / 360 | 100 new companies, fresh 90-question dev protocol |
| owner v3, tasks A + C | `runs/v3-data-20261018T052500Z/` | A 146/36/31, C 487/189/176 | from SEC EDGAR; raw filings in `sources/` (LFS) |
| training packs | `runs/4b-bfv3*/train-packed.jsonl` | — | exact rows each run trained on |

**Notes on the data:**
- **Sealed tests are published too**, at the owner's choice. They are no longer unseen, so any future model needs new test sets.
- **Owner v3 task A labels** (revision reasons) are rule-derived and not human-reviewed. See that run's DATASET_CARD.md.
- **Task C labels** come from `pipeline/reform.py` LINES @ `04226e2`, with 13 tags held out.
- **Not yet trained on:** owner v3 tasks A and C, and basic-finance-v4.
- **Historical corpus:** the full `initial-corpus-v4.jsonl` lives outside this lab. Only its sampled training rows are included, inside the mix training pack.

## Reproduce

- `bfv3_4b.py`: pack data and evaluate an adapter.
- `merge_champion_nf4.py`: NF4-faithful merge.
- `eval_gguf.py`: evaluate a GGUF through llama-server.
- Tools used: llama.cpp b11381 for conversion, quantization and serving.
