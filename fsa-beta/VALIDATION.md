# Validation record

Created by ChatGPT (OpenAI), October 15, 2026.

## Executed successfully

- `python -m unittest discover -s fsa-beta/tests -v`: **23 tests passed**.
- `node --check fsa-beta/web/app.js`: passed.
- `python -m compileall -q fsa-beta`: passed, including optional training/evaluation scripts.
- `python fsa-beta/student.py --train`: produced `models/router.json`; 8/8 developer-authored held-out topic examples passed. This is a tiny smoke set, not a generalization claim.
- `python fsa-beta/training.py --out fsa-beta/.runtime/training.jsonl`: 400 independent synthetic examples, split into 240 train / 80 validation / 80 test with entity separation.
- HTTP tests exercised the actual local server with temporary loopback ports: financial analysis and local questions succeeded; private file paths returned 404; missing token, foreign Origin and unexpected Host returned 403.
- Gemini mock tests exercised structured output, evidence rejection, cache reuse, throttling, and missing-key handling. No paid or live model call was made.

The fictional second-year example produces accruals of 35, FCF of 25, NOA of 500, NFO of 140, zero equity reconciliation residual, an accrual ratio of 35/850, and estimated period RNOA of 105/465. Its warranty release benefit is 20 before tax, conditional on the supplied income-statement classification. Values use USD millions.

## Not verified in this environment

- Browser rendering and interactions: Playwright was available but Chromium was not installed. The attempted browser download returned an invalid/truncated archive. No screenshot, mobile-layout or accessibility pass is claimed.
- Live Gemini eligibility, quota, provider response and billing configuration: no API key was supplied.
- Qwen LoRA runtime, GPU memory, training loss or post-training accuracy: model weights and ML training dependencies were not installed, and no adapter training was run. Syntax checking is not an ML integration test.
- Real filing extraction/coverage: the supplied adapter copies supported existing JSON fields, and required missing inputs remain explicit. Automatic footnote extraction is not implemented.
- Hosted deployment: none. The feature is on a separate Beta branch and is not merged into the production main branch.

The workbench has a constrained scope. A reconciled reserve or passing test is not an audit opinion, a measure of reserve adequacy, or proof of earnings manipulation.
