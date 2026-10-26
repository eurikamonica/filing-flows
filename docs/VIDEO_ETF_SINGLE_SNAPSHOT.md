# ETF / 13F Holdings Video — Safe One-Snapshot Fallback

## Screenshot / production symptom

In Video Studio, choosing **ETF / 13F / officials history → ETF disclosed holdings → SPY → Group changes: Company** returned a near-empty video canvas with:

`Weight changes require at least two disclosed snapshots`

This was not principally an MP4 encoder failure. The existing Video Studio intentionally refuses to calculate a percentage-point holding-weight change from one report.

## Root cause verified against the data branch

On the `etf-history` GitHub data branch, `public/e/SPY.json` is available with **505 sponsor-holdings weight rows** and a displayed date **2026-10-25**. However `public/weights/SPY.json` and even `public/weights/` are absent, and `public/status.json` has no `actual_weights` status field. The last inspected data build was **2026-10-25 09:21 UTC**, prior to the newer source-dated capture code being merged and published.

**Do not fabricate older holdings, infer manager trades from changes, or pretend the current sponsor file contains a historical comparison.** The new capture module `disclosures/app/actual_weights.py` persists real observations in `etf/cache/actual_weights/` and publishes `etf/public/weights/` on future runs. A genuine change chart becomes available only when at least two actual comparable snapshots have been captured and republished.

## Fix in this PR

- `web/actual-weights.js`: When **Changes** is requested but only ONE dated snapshot is available, render the *actual latest weight composition* as a dated **rank-card video** instead of an error/black canvas. Label the title, footer and notes **single disclosure / NO CHANGES**. Do not fabricate historical dates, previous weights or percentage-point deltas.
- `web/studio.js`: the prominent status message says **Only one real disclosure available · showing dated holdings, NOT weight changes**.
- Unknown legacy provenance: existing sponsor records lacking a `date_basis` field are marked `unknown`, not silently upgraded to `reported`; metadata states that 2026-10-25 is not a verified portfolio effective date. New pipeline capture uses the same conservative convention. Known `reported` and `observed` bases are preserved.
- No change to the existing **official index weights vs ETF NAV weights**, 13F portfolio denominator, sector grouping, actual weight formula or legacy Sector Weights view. With **2+** valid dated snapshots, original changes calculations continue unchanged.

## Source and refresh checks

The ETF data comes from `.github/workflows/etf.yml` (scheduled every four hours or manually dispatched). It builds the `etf-history` branch and `scan.yml` stages `etf-history/public/` into the deployed Disclosure Hub. The ETF workflow now prints a nonfatal status diagnostic for SPY/DIA/QQQ/IWM: published history count, recent dates, current holdings date, and source-date basis. Missing history or one snapshot produces a GitHub Actions warning/notice rather than silently behaving as if two snapshots existed.

A new workflow run must publish `public/weights/SPY.json` before the site can show a real series. Site refresh/clearing cache alone cannot create missing disclosure history. **Do not seed 2 entries by duplicating the same date or by calculating from historical prices.**

## Verification

- The existing `tests/test_disclosed_weight_views.cjs` now tests **2 real snapshots → percentage-point change**, **1 snapshot → static rank with no changes**, **current sponsor SPY holdings with no history JSON**, **missing-data reject**, **single 13F period → no invented trades**, and **legacy unknown date basis**.
- `disclosures/tests/test_actual_weights.py` now explicitly checks unknown versus reported/observed date semantics.
- Direct execution of the JavaScript suite passed. A separate integration test using `etf-history/public/e/SPY.json` in the browser module generated **`kind='rank'`**, `reports=1`, `fallback='single-disclosure'`, 505 underlying reported weight rows and the explicit date-provenance caveat.
- New GitHub Actions CI and ETF producer run results must be checked separately; this PR does not merge into `main` or deploy to production by itself.
