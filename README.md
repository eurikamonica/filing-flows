# Local fallback model

Base: `Qwen/Qwen3-0.6B` + LoRA (`adapter/`), trained by `.github/workflows/train-local-model.yml` on posts built from the site's data (`pipeline/corpus.py`); used by the posting workflows only after every API model failed (`pipeline/local_model.py`).

- Production adapter: **88%** of held-out posts publishable (promoted 2026-10-16T19:17 UTC)
- Last run 2026-10-17T13:20 UTC: 236 examples, loss 0.0819 → 0.0617, work adapter 92% vs production 98%
- Corpus: 13677 examples event8k 969, insider 910, post 11559, post_holders 239
- Held-out: companies whose CIK hash ends in a fixed tenth are never trained on.

Every run: `reports.jsonl`.
