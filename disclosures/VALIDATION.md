# v4 validation

## Executed

- 74 Python unit tests, including inherited SEC/13F/congress tests, CFTC `+` code/rename handling, FDIC count/duplicate validation, entity-queue continuation, stale-data retention, N-PX document-queue continuation independent of filer scans, 1,000-row vote chunks, catalog loading and persisted queue state.
- 30 Node UI template/logic checks across official/demo views and all five directory types.
- 8 asynchronous checks for manager/quarter fetching, errors, progressive vote-chunk loading and catalog loading. These use mocked network responses and are not browser tests.
- Python compile and JavaScript syntax checks; workflow YAML structure check.
- Live FDIC active-institution directory retrieval: 4,223 entries; new bank histories downloaded across consecutive batches.
- Live CFTC grouped market discovery: 507 dataset/code combinations within the configured Disaggregated/TFF futures-only scope; includes code 13874+, which was downloaded successfully after adding explicit support for plus signs.
- Live N-PX submissions and XML retrieval: 18 downloaded filings across 7 scanned filers, yielding 5,183 vote rows. Some downloaded reports have no supported structured vote table; they retain that status rather than being declared zero holdings.
- Real successive batches advanced counts: bank histories 3 → 7 → 9; COT histories 3 → 9 → 11 → 12; N-PX downloaded filings 2 → 14 → 18. Source-specific error status cleared after the COT code fix.
- v3's SEC 13F and House catalogs and extracted records are retained, not claimed freshly recollected in v4.
- ZIP audit checks CRC, no dot-prefixed components and individual file sizes below 25 MiB.

See notes/v4-collection-runs.json and notes/v4-summary.json for actual v4 run summaries. Older notes describe earlier baselines only.

## Not executed / limitations

No actual browser rendering/interaction test, GitHub Actions runner, repository push or Pages deployment. No full download of every discovered entity. No exhaustive financial validation of OCR. House reviewed data remain six partial excerpts; Senate/state/local automatic discovery remains absent. COT excludes other report families; FDIC defaults to active institutions. These are explicitly scoped public-disclosure datasets, not exact real-time portfolios.
