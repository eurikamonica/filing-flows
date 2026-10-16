# Story Desk validation

Created by ChatGPT (OpenAI), October 15, 2026 (America/New_York).

## Executed

- Node syntax checks for `app.js` and `engine.js`: passed.
- `node test.cjs`: 18 named tests passed.
- Tests cover candidate ordering, margin percentage points, missing versus zero values, losses, unknown release treatment, demo/preliminary labeling, overlapping/YTD-length periods, invalid numeric types, negative release amounts, source requirements, unknown journal metrics, fractional counts, zoned timestamps and unsafe URL schemes.
- Code inspection: no network requests, third-party scripts, production imports or posting calls. Changes are new files only under this directory.

## Limits

Actual browser layout, clipboard, storage, file import/export, PNG output and MediaRecorder WebM output have not been end-to-end tested here. The earlier Chromium download attempt in this environment failed with an invalid/truncated archive, so no browser visual-verification claim is made. Syntax and pure-function tests do not establish UI/export correctness.

No model inference/training, live filing verification, analytics-account access, posting or deployment was performed. The manual review checkbox records an in-session user assertion only and is not an audit log.

## Manual acceptance checklist

1. Open index.html. Confirm fictional labels on evidence, chart and all drafts.
2. Select profit/OCF: NI 105 → 130, OCF 90 → 85, current accruals 45. Select margin: 17.5% → approximately 16.67%, approximately −0.83 percentage points.
3. Confirm PNG export is disabled until review, and changing story/input resets review. Check rendered source and labels before publishing.
4. Export input, reimport it, and test null OCF, zero OCF, negative NI, zero revenue, missing source and overlapping periods.
5. Edit and copy a draft. Deny clipboard access to test selection fallback. Confirm no publication occurs.
6. Play/pause/replay the animation; inspect all four totals against the README. Test reduced motion. Export WebM in a compatible desktop browser, keep the tab visible, and verify duration and final caption.
7. Add a zoned 24h journal snapshot with unknown clicks; check N/A ratio. Reject duplicate URL/window. Add a separate 72h snapshot. Export, reload, restore and confirm deduplication. Check denied-storage message.
8. Verify narrow-screen layout and keyboard access. Confirm no API calls in the browser network panel.
