# Validation record

Created by ChatGPT (OpenAI), October 15, 2026.

## Executed

- `node --check app.js` and `node --check math.js`: passed on Node 24.19.0.
- `node test.cjs`: passed 18 assertions covering accrual formulas, missing values, zero, denominator constraints, reserve reconciliation, pet transaction effects, nonmutation of input state, invalid transactions and malformed imports.
- Reviewed standalone paths: no production imports, external scripts, fetch calls or API keys; all deliverables are new files in this directory.

## Not verified

Playwright was available, but no browser executable was installed. Chromium installation failed because the downloaded ZIP was truncated/invalid. Consequently, actual browser layout, animations, file import/download interaction and mobile rendering have **not** been visually or end-to-end validated. Syntax and accounting tests do not substitute for browser testing.

No production deployment, automated live filing ingestion, real-company financial verification, LLM invocation or training was performed.

## Manual browser acceptance

1. Open index.html; confirm the fictional label, three period labels and zero baselines.
2. Select FY2025: accruals 45; ratio approximately 4.74%; reserve closing 37 with zero difference.
3. Click each pet action after resetting: provision 10 -> reserve 60 / pretax profit 90 / cash 100; settlement 10 -> 40 / 100 / 90; reversal 10 -> 40 / 110 / 100.
4. Attempt reversal 100 from opening reserve 50; verify rejection and unchanged totals.
5. Export the demo and reimport it. Test a null OCF, malformed numeric text, missing reserve movements and an intentionally incorrect closing balance. Missing values must not become zeros.
6. Test pause/resume, OS reduced motion, keyboard controls and narrow viewport scrolling. Verify the numeric reserve balance stays readable even when decorative cookie capacity is reached.
7. Confirm no network request to a financial API or model provider occurs.
