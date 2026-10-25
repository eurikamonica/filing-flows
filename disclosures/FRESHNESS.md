# Disclosure freshness and durable retries

## Problem

Several hub pages displayed the holdings module's October 18 timestamp even while their own collectors were running. Separately, two October 25 holdings jobs logged `holdings: ok` and then received runner shutdown signals during price enrichment; their final Git persistence steps never ran. Those logs establish the failure sequence, not the underlying reason the runner shut down.

## Changes

- Scheduled holdings, officials and all-source runs use `--defer-enrichment`. Holdings polling no longer loads every manager's history for optional prices or waits for market-view building. Price enrichment runs separately every six hours (`11 */6 * * *`, UTC); explicit market rebuilding runs every three hours (`41 */3 * * *`). Existing light collection continues rebuilding market views. Existing holdings poll frequency is unchanged.
- Persistence merges the shared `live.json` by module freshness after rebasing, regenerates `live.js`, and retains newer source status files. If price enrichment used older holdings/officials input, newer dependent cache/shard files are restored with the newer module header. A real local Git concurrency regression covers this case.
- Small `*-status.json` files distinguish `last_attempt`, `last_success`, `last_partial_success`, and `latest_filing_date`. A skipped poll or failed request never advances success. Unknown historical timestamps are left unknown rather than backfilled from the current clock.
- The hub reads the current page's own status. Stale data, errors and pending failures produce warnings even if a legacy source called itself `ok`. The site publication timestamp remains separate from source timestamps. Legacy payload completion timestamps are explicitly labeled.
- Rotation captures its input scan/view timestamps at build time. Rebuilding a chart does not imply its inputs were refreshed. Missing input timestamps are reported as unknown.
- Form 4's filing-date regex now decodes the submission header before applying a string pattern. Pending Form 4 filings survive feed rollover.
- 8-K and ownership feed failures and unprocessed entries are persisted, as are document/index error details and next retry times. HTTP 403 indexes are no longer marked complete. Failed 8-K reparses remain queued; batch limits include feed items.
- Senate session failures are saved with an access cooldown. Failed reports are not permanently abandoned after four attempts. Repeated polls retain the last valid data and blocked status; no challenge bypass or alternate identity is introduced.
- Retry delays grow from 15 minutes (60 for HTTP 403/429) to a maximum of 24 hours. Due entries can be attempted again; successful entries clear their failure state.

## Validation and rollout

Run:

```sh
python -m unittest discover -s disclosures/tests -p 'test_freshness_retry.py'
python -m unittest discover -s disclosures/tests -p 'test_ownership.py'
python -m unittest discover -s disclosures/tests -p 'test_events_news.py'
python -m unittest discover -s disclosures/tests -p 'test_market.py'
node disclosures/tests/test_freshness_ui.js
node --check disclosures/docs/freshness.js
node --check disclosures/docs/app.js
```

After merge, dispatch `Collect disclosures` with `module=holdings`, then verify the persisted holdings status and Pages output. Source status files appear as each collector next runs; until then the UI shows legacy/unknown fields. A new site build is needed for Rotation input provenance. Senate recovery still depends on the official endpoint accepting requests; handling and retrying a 403 cannot guarantee access. File-level persistence outside the shared live snapshot retains the existing workflow rebase behavior; this is not a transactional multi-writer database.
