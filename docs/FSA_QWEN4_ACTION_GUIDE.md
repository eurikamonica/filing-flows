# Isolated Qwen3-4B FSA Actions

This experimental controller never modifies the main model, production website, narratives, or existing lab branch. It does not auto-merge, publish weights, or promote a candidate.

## Activate
Review the feature PR and merge it only after reviewing the security trade-offs. A workflow_dispatch workflow normally needs to exist on the default branch for the Actions UI to list it. Select Actions -> FSA Qwen3-4B Experimental Lab -> Run workflow.

## Modes
- audit: Uses a normal GitHub-hosted CPU, verifies preexisting splits against publicly recorded open protocols, creates a deterministic training sample and JSON manifest. No model is loaded.
- benchmark: Requires a Windows self-hosted GPU runner with custom label fsa-gpu; scores the existing champion (or a candidate inside this particular run) on open BFv4/BFv3/Gate2 development questions.
- train: Runs Qwen3-4B NF4 QLoRA continuation for up to 50, 100, or 200 optimizer steps. Defaults to a fresh deterministic sample of 1,200 basic-finance-v4 train questions and 600 earlier train/replay questions; old output contracts are deliberately included to reduce forgetting. The "mixed" objective additionally includes up to 150 unreviewed owner task-C labels. Owner task A is excluded pending human review. Final candidate remains on the runner and is not promoted.
- ask: Takes one self-contained prompt in the question input; prints a JSON answer to the Action logs and provides answer.json as an artifact. Never send secrets or sensitive information in public workflow inputs.

## Preparing your Windows RTX 3050 runner
1. In GitHub repository Settings -> Actions -> Runners, register a self-hosted Windows x64 runner. Give it custom label fsa-gpu; use a dedicated, isolated Windows account and only dispatch trusted branches.
2. Install Git LFS, Python 3.11 and NVIDIA CUDA-compatible packages. Recommended packages include CUDA-enabled torch, transformers >=4.51,<5, peft, accelerate, bitsandbytes, datasets and safetensors; verify torch.cuda.is_available() first. Ensure sufficient system RAM, page file, and free disk space.
3. The workflow fetches the specified lab reference including LFS adapter weights; Hugging Face base Qwen3-4B is downloaded/cached separately. Neither the runner nor the downloaded model is provided by the GitHub Actions hosted CPU.
4. Start with audit. Then use benchmark before a 50-step train. Read artifacts and logs. If high GPU memory use, OOM, excessive time or training divergence occur, stop and investigate. The 4B training may require parameter adjustments on 6GB hardware.

## Example ask input
Return only one JSON object with fields value and source_id. Evidence S1: net_income=120, operating_cash_flow=90, average_total_assets=300. All amounts USD millions. Calculate annual accrual ratio as (net_income - OCF) / average_total_assets as a fraction. Use source_id S1.

Expected output: {"value":0.1,"source_id":"S1"}.

## Caveats
Benchmark runs use already-public development protocols, not sealed tests. The new strict scorer differs from the original Gate2 special arithmetic scorer. Comparing them is diagnostic only, not a clean promotion test. The synthetic basic-finance task generator is related to old training, so improvements do not establish comprehension of unseen real filings. The owner Task A revision reason data are rule-derived and unreviewed. Prefer the existing Q8_0 GGUF for local llama.cpp inference; Q4_K_M regressed strongly on the old-contract suite.

No hosted GPU training has happened in this implementation. GitHub Actions and LFS use may count toward account quotas; remote runners and uploaded artifacts must be secured.
