# Model export, 8B download and production status

Created by ChatGPT (OpenAI).

## Actual operations

| Attempt | Status | Maximum logit errors |
| --- | --- | --- |
| initial_dispatch | failed | not measured |
| cpu_bfloat16 | failed | [0.625, 0.4375] |
| cpu_float16 | passed_smoke | [0.0546875, 0.0625] |

Initial attempt failed with meta tensors after PEFT default redispatch. It is retained as failed. CPU BF16 output texts matched but errors 0.625/0.4375 exceeded the predeclared 0.125 threshold. No threshold was relaxed. A separate CPU float16 comparison uses the same threshold and exact generated-text criterion. Parameter devices are checked and CUDA visibility is disabled for the corrected CPU workers.

FP16 export: `C:\Users\Oliver Hu\Downloads\filing-flows-beta-fsa-chatgpt\filing-flows-beta-fsa-chatgpt\fsa-beta\model-expansion-lab\operations\20261016T183600Z-fp16-merge\qwen4-merged-float16`. Raw before/after outputs, pinned base revision, adapter checksum and all export checksums are in its merge-status.json. Two-prompt equivalence is a packaging check; separate development and re-quantization checks remain necessary before model-service deployment.

## Qwen3-8B download

Status: completed
Revision: `b968826d9c46dd6066d109eabc6255188de91218`.
Expected safetensors bytes: 16381516776.
Local source: `C:\Users\Oliver Hu\Downloads\filing-flows-beta-fsa-chatgpt\filing-flows-beta-fsa-chatgpt\fsa-beta\model-expansion-lab\operations\20261016T182700Z\qwen3-8b-source`.
License metadata: apache-2.0. Subsequent 8B local inference has now completed; no 8B training or 4B-adapter loading into 8B was performed. See [Windows execution report](WINDOWS_QWEN3_8B.md).

Pinned official LFS SHA256 verification: True.

## Website and production inference

The user confirmed `eurikamonica/filing-flows` and local Windows Qwen3-8B inference. An authenticated loopback companion is ready at `http://127.0.0.1:8768`. NF4/BF16 and explicit CPU weight offload ran on the RTX 3050 Laptop 6GB. A real Edge preview returned the site's PLUG Q2 2026 revenue label with a checked literal quotation; an earlier malformed response remains recorded as failed. These are inference/interface smoke tests, not model training or a financial accuracy benchmark.

[Draft PR #2](https://github.com/eurikamonica/filing-flows/pull/2) contains the optional website interface and standalone local companion. Offline GitHub CI passed. No main-branch merge or website deployment occurred, respecting the owner's no-auto-merge instruction. No email/social publishing workflow was triggered. No database, secret or hosted inference setting was changed.

All local artifacts remain in this Beta; only the reviewed source changes were uploaded to the isolated remote branch. Weights and tokens were excluded. Exact resource readings, commands, outputs, rejected attempts and limitations are in [WINDOWS_QWEN3_8B.md](WINDOWS_QWEN3_8B.md).

## Owner decisions (2026-10-16)

Deployment target, decided by the owner. This supersedes the open question in the previous section.

- **Inference runs locally only**, on this Windows machine. No remote GPU endpoint, browser inference or hosted model service.
- **Results are published as JSON** to the `narratives` branch of `eurikamonica/filing-flows`. Not `main`. Website code, workflows and Pages configuration in that repository are out of scope and must not be modified.
- **The JSON schema will come from the cloud side.** No push/publish code is written until that schema is provided. This lab repository has no remote configured.
- As of 2026-10-16 the remote has no `narratives` branch. Creating it is left to the publishing side once the schema exists.
- Conflict to resolve: before these decisions, a separate Codex session pushed branch `beta/windows-qwen3-8b-20261016` and opened draft PR #2. Per the section above, that PR includes website interface code. This conflicts with "do not touch website code". The PR and branch were left untouched, pending the owner's decision.
- Model outputs map to existing pipeline fields:
  - Revision reasons fill `why` in `pipeline/history.py` events.
  - Balance-sheet classifications fill `suggest` in `pipeline/reform.py` lines.
  - The ten revision labels are grouped under history.py's `amended` / `results` / `presentation` / `cash flow` patterns.

Paused work:

- **Training on data-v2 is paused.** The prospective v2 dataset stays frozen as-is; no v2 training or evaluation run is to be started.
- **Qwen3-8B is paused.** This supersedes the "local Windows Qwen3-8B inference" confirmation recorded in the section above.
  - No 8B job runs on the GPU.
  - Do not start `local8b_runtime.py` or `local8b_service.py`.
  - The verified download stays on disk.
  - On 2026-10-16 around 15:55, the running `local8b_service.py` (PID 21708 and child 23540, listening on 127.0.0.1:8768) was stopped at the owner's request. GPU memory went back to 0 MiB. The `local8b_runtime.py` preflight (PID 32448 and 28916) had already exited.
- **SEC downloads are approved** for building the v3 data:
  - `User-Agent: Filing Flows filingflows@gmail.com`.
  - At most 10 requests per second.
  - Downloaded filing text is never committed to git.
- **Task C labels** come from the `LINES` table in `pipeline/reform.py` (Nissim–Penman). About 20% of its tags are held out from training.
- The next dataset round is redefined (revision-reason classification, MD&A driver amount extraction, balance-sheet operating/financing classification). See `drafts/DATASET_CARD_v3_DRAFT.md`. It is a draft for owner review only; no data build or training has started.
