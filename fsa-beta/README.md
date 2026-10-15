# FSA Beta — Created by ChatGPT (OpenAI)

A standalone, locally run financial-statement-analysis workbench for Filing Flows research.

**Status:** Beta implementation, not connected to the production site. All files introduced for this feature live under `fsa-beta/`. No production code, workflow, dependency file, database schema, or deployment setting is modified. The demo is fictional. Gemini integration is implemented and mock-tested; no live key was used. Optional LoRA scripts are supplied but no language-model adapter has been trained or evaluated in this environment.

## Start on Windows

Download this directory (or the repository ZIP), open a terminal in `fsa-beta`, and run:

```powershell
py -3.12 server.py
```

Open **http://127.0.0.1:8765**. Python 3.11+ and its standard library are sufficient for the workbench. No npm, activation script, cloud deployment, or production service is needed. Use the printed `127.0.0.1` URL, not `localhost`, because the server checks its Host header.

For macOS/Linux, use `python3 server.py`. Stop with Ctrl+C. `--port 8766` selects another loopback port.

The page loads a clearly labeled fictional two-year example. Import a JSON file or edit the input, then select **Analyze input**. Switch periods, inspect sources and formulas, ask a topic question locally, or export the calculated report. The signed bars extend the income/profit/cash view with reserves and operating/financing analysis; they do not reuse or modify the production Sankey renderer.

## What works now

- Income, operating profit, net income, OCF and calculated FCF comparison.
- Reserve rollforwards with additions, releases, utilization, other movements and reconciliation residuals.
- Accruals, accrual ratio and cash conversion, without filling missing values with zero.
- User-reviewed operating/financing classifications, NOA, NFO, estimated NOPAT and period RNOA.
- Equity and asset-classification reconciliation checks.
- Rule-based earnings-quality review language with evidence IDs; no automated fraud verdict.
- A trained local topic classifier for reserves, accruals, reformulation and FCF. Arithmetic remains in the engine.
- Optional server-side Gemini explanation, with a local call budget, cache and strict evidence-ID validation.
- Independent synthetic training data generation and optional Qwen3 LoRA training/evaluation scripts.

## Gemini free-tier setup

1. Create a **separate** project/key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Check [current pricing](https://ai.google.dev/gemini-api/docs/pricing) and [your project rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Confirm the chosen model has free quota and billing is disabled. This application cannot inspect or guarantee your Google billing state.
3. Set environment variables in the terminal that starts the server. Do not paste a key into the browser, commit it, or reuse production configuration.

```powershell
$env:FSA_BETA_GEMINI_KEY = Read-Host "Paste your separate Gemini API key"
$env:FSA_BETA_GEMINI_MODEL = "gemini-3.8-flash"
$env:FSA_BETA_FREE_PROJECT_CONFIRMED = "1"
$env:FSA_BETA_DAILY_CALLS = "10"
py -3.12 server.py
```

The model above appeared with a free tier in the official pricing page checked on October 15, 2026. Model availability and quota can change; choose a currently eligible model in your own project. `.env.example` documents settings but is not automatically loaded.

Only an explicit **Explain with Gemini** action invokes Google. The key stays server-side. Calls use the documented `generateContent` REST interface, which the current documentation still supports. There are no search tools, automatic retries, key rotation, provider fallback, or paid-model fallback. Local limits default to 10 attempts in a rolling 24-hour window and at least 10 seconds between new requests. Failed attempts count. Cache hits do not call Google. The local ceiling does not override Google's quota or billing.

The report and bounded source excerpts are transmitted. Google's unpaid-service terms describe use of submitted content and responses to improve products; use public financial material, not confidential documents. Returned prose remains labeled **unverified**: valid JSON and evidence IDs do not establish that every sentence is true. Gemini cannot replace calculated values in the financial report.

## Input and evidence

See [SCHEMA.md](SCHEMA.md) and [examples/demo.json](examples/demo.json). Include actual period boundaries, a common unit/currency, and source IDs on amounts. Quarterly input must already be quarterly, not cumulative YTD. Operating/financing classifications require review; banks and insurers need separate industry-specific treatment.

To copy supported figures from an existing exported company JSON without touching its source:

```powershell
py -3.12 adapter.py "C:\Downloads\company.json" ".runtime\company-draft.json"
```

Create `.runtime` first if needed. The adapter refuses to overwrite its source or an existing output. It is deliberately read-only and does not import production modules. It copies available earnings/cash-flow values, but does not invent quarter start dates, reserve movements, assets, or classification facts. Complete the draft before analyzing it. This Beta does not automatically download or parse SEC footnote tables.

## Train your own model

Read [TRAINING.md](TRAINING.md). The included local topic model can be rebuilt with:

```powershell
py -3.12 student.py --train
```

It is a small Naive Bayes classifier, not a generative financial LLM and not Gemini distillation. The optional LoRA path uses downloadable Qwen3 weights and independent data. Gemini responses are marked ineligible for training by this Beta; the training loader accepts only reviewed independent examples.

## Verification

From the repository root:

```text
python -m unittest discover -s fsa-beta/tests -v
node --check fsa-beta/web/app.js
```

Tests cover financial identities, missing data, rollforward gaps, invalid values, source IDs, time alignment, dataset leakage, and Gemini cache/budget/response handling using mocked calls. See [VALIDATION.md](VALIDATION.md) for executed checks and limits.

## Isolation and removal

The server binds only to `127.0.0.1`, serves an explicit file allowlist, checks Host/Origin and a per-process request token, and writes Gemini state only under `fsa-beta/.runtime/`. It exposes no file-writing API. Production workflows have no Beta entry point. No workflow was added or triggered.

Deleting `fsa-beta/` removes the feature. It is not published on GitHub Pages, which cannot hold a private server-side API key. Any later hosted deployment requires a separate backend and a deliberate integration decision.
