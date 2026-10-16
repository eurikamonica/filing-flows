# Filing Flows Story Desk

Created by ChatGPT (OpenAI), October 15, 2026 (America/New_York).

An independent, additive English-language social-content beta. All files are new under `fsa-beta/social-lab/`. Existing production code, earlier beta code, navigation, workflows, models and deployment settings are unchanged.

## Open

Download the `beta/fsa-chatgpt` branch ZIP, extract it, and open `fsa-beta/social-lab/index.html` in a desktop browser. No installation, API key or account is needed. For a local origin with more reliable clipboard/storage support, run this from **this directory only**:

```powershell
py -m http.server 8767 --bind 127.0.0.1
```

Open http://127.0.0.1:8767. Stop with Ctrl+C. Do not serve the repository root. This does not use or modify the earlier server on port 8765.

## Six additions

1. **Change selector:** rule-based candidates for profit/OCF comparisons, operating-margin changes and reserve releases. Profit-up/OCF-down is prioritized. Ordering is an editorial heuristic, not a trained reach predictor, valuation signal or fraud score.
2. **Evidence card:** original period values, dates, formulas, source text and supplied excerpts. All sources are user supplied and unverified by the application.
3. **Social chart:** a 1200 × 675 PNG with a common zero baseline, period legend, unit, source text and demo/preliminary status. Review checkbox required to download. Full source text remains in the evidence card/input export; long source text may be shortened on the PNG.
4. **Three English drafts:** news-style filing check, numeric contrast and explanation. Deterministic templates, editable before copying. No BREAKING claim is inferred from an old filing. No local LLM, Gemini, X account, scheduler or publishing API is connected.
5. **Posting journal:** manually enter 24h/72h observations, preserve unknown click/visit counts as null, calculate clicks/views when available, save in scoped browser storage, export JSON and restore by merging new URL/window combinations. Duplicate snapshots do not overwrite existing entries. Delete and reenter to correct a row. Browser storage is not a guaranteed backup.
6. **Cookie Jar lesson:** 12 seconds with English captions, replay/pause, a text transcript and optional WebM recording through browser MediaRecorder. Recorded video is silent. Keep the tab visible throughout recording. WebM requires a compatible browser/encoder; no MP4 conversion or direct social upload is included.

## Workflow

Load the fictional example, export it as a template, and edit a copy. Import the copy, select a story, inspect evidence, review the draft and check the review box before PNG export. Editing JSON invalidates existing story output until analyzed again. The pet animation is always a clearly labeled fictional lesson and never changes the financial data.

Copied text remains a draft. Nothing is posted, queued or sent anywhere. Post manually only after verifying factual and accounting context. The journal is populated manually; it does not retrieve X analytics or install website tracking. Website visits must come from your own available measurement process.

## Input contract

Use `schema: "story-desk-1"`, boolean `demo` and `preliminary`, string `company`, uppercase `ticker`, `unit`, and two period objects `previous` and `current`. Export the bundled example for a complete JSON template.

Each period requires `label`, `kind` (`annual` or `quarter`), `start`, `end`, `source`, and `excerpt`. Optional numeric fields are `net_income`, `ocf`, `revenue`, `operating_income`, `reserve_release`; optional `release_in_income` is boolean. Null or omitted means missing, not zero. Reserve release uses a nonnegative magnitude.

- Both periods must have matching kind, valid duration and nonoverlapping dates. Quarters: 75–105 inclusive days; years: 350–380 days. Transition periods need separate treatment.
- Supply oldest period first. Manual review must confirm comparable fiscal periods, currency, units, consolidation scope, GAAP/non-GAAP basis and discrete-quarter rather than cumulative YTD OCF. The app cannot detect YTD figures mislabeled with quarterly dates.
- Net income and OCF retain signed values. Margin requires positive revenue. Margin change is in percentage points, not relative percent growth.
- Reserve releases alone do not establish reserve adequacy or earnings manipulation. A user-supplied income-treatment flag is not independent evidence. This desk does not perform a reserve rollforward reconciliation; use the separate visual lab for that.
- Input file limit: 200 KB. Numeric absolute values must be at most 1e12. Text is inserted with textContent or drawn on canvas, not interpreted as HTML.

This schema is separate from the existing FSA engine and visual lab schemas. There is no automatic SEC extractor, data adapter or real-company feed in this addition. There are no fetch calls or external assets.

## Journal and draft limits

Each journal row has `url`, zoned ISO-like `published`, `format` (News, Contrast, Explanation, Cookie Jar), `window` (24h or 72h), nonnegative integer `views`, and nullable nonnegative integer `clicks`/`visits`. Maximum 2,000 rows, restore upload 2 MB. The displayed clicks/views ratio uses manually entered figures; it is not a platform-certified metric or causal result. Do not combine 24h and 72h snapshots as independent posts when evaluating performance.

The draft counter counts Unicode code points, **not X's weighted length**. Long company units, figures or wording can exceed the desired post limit. Edit and confirm in the platform composer before publishing. No link-shortening assumptions or final-length guarantees are made.

## Animation assumptions

The four stages show reserve / pretax profit / cash:

| Seconds | Action | Reserve | Pretax profit | Cash |
| --- | --- | ---: | ---: | ---: |
| 0–3 | Opening | 50 | 100 | 100 |
| 3–6 | Record provision 10 | 60 | 90 | 100 |
| 6–9 | Pay settlement 10 | 50 | 90 | 90 |
| 9–12 | Reverse estimate 10 | 40 | 100 | 90 |

Assumes a liability provision expensed through profit, settled with cash, no taxes. This is not universal treatment for every reserve. Reduced-motion preference suppresses the jar's bobbing; playback starts only on user action. Export embeds the same captions and assumptions.

## Validation and next steps

See VALIDATION.md. Calculation and validation tests passed; browser end-to-end and visual validation remain outstanding. Before public use, verify PNG readability, clipboard fallback, local storage recovery and complete WebM output in your actual browser.

Possible future additions: an independently tested read-only financial adapter; model-based wording evaluated against deterministic templates; provenance at individual-field level; MP4 export; and measured topic ranking. None are claimed implemented here.
