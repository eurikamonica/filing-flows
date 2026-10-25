# CBOE options: prioritized supplemental scan and missing-path repair

## Verified production symptom

The previously published **2026-10-23** CBOE data contains AAPL in the summary (3,392 contracts) and in a detailed JSON file, but its details do **not** contain a `paths` key. The Sankey company page was testing `!c || !c.paths.length` and printing "option chain is not collected". That statement was false.

This PR changes the page to distinguish:
1. **No sourced option-chain detail** — source data not yet published, no market claim.
2. **Valid chain metrics but no implied price paths** — show dated spot, IV30, open interest and contract count; explain the missing risk-neutral model result.
3. **Valid modeled `paths`** — show the existing options-implied fan/path chart.

## What gets faster

- A new **independent, thin-checkout GitHub Actions workflow** scans popular CBOE underlyings twice hourly on US weekdays during 13:00–23:59 UTC. Scheduled runs may start late; this is *not* tick-level live data.
- Priorities include AAPL, NVDA, MSFT, AMZN, META, GOOGL, GOOG, TSLA, AVGO, AMD, PLTR, OKLO, IREN, CRWV, NBIS, SPY, QQQ, IWM, SPX and TLT. The first slots go to explicitly requested tickers and **popular tickers whose published details lack usable paths**.
- Uses the existing CBOE delayed-quote URL, source parser, risk-neutral pricing/quantile functions and source-date provenance; **no fabricated prices or option-implied distribution**.
- The original after-close full-universe scan continues unchanged in schedule. It still gathers the broader set of index / sector ETF / 13F / Signals names.
- Every successful scan **merges** into the published options index. A timeout, rate limit, unsupported ticker or CBOE outage retains earlier valid ticker data and detail. Old data keeps its original `as_of` source timestamp, never the scan's current time.
- This independent job does not pull 13F/N-PX shards, OCR PDFs or recompute the whole disclosure market, reducing avoidable overhead.
- Manual "Run workflow" accepts a comma-separated tickers list.

## Files

| File | Change |
| --- | --- |
| `disclosures/app/options.py` | Priority missing-path scan; source dates; merge-on-success; standalone Python command |
| `disclosures/config/settings.json` | Prioritized ticker list and fast scan limit |
| `disclosures/docs/option-paths.js` | Accurate missing-path vs missing-chain states |
| `disclosures/docs/options.js` | Explain supplemental cadence and delayed source |
| `.github/workflows/options-supplement.yml` | Independent 30-minute job and commit-to-main |
| `disclosures/tests/test_options_supplement.py` | Offline missing-path, prioritization, failure/retention regression tests |

## Operations

After merge, the new schedule is activated from the default branch. For immediate repair, open **Actions → Supplement popular option chains → Run workflow** with `tickers=AAPL,NVDA,MSFT`. Successful runs commit refreshed details to `disclosures/docs/data/market/options/<TICKER>.json` and the index. The usual Pages pipeline then stages data to the public website; a successful PR CI test does **not** mean that the live data is already repaired.

The collector keeps a rolling date-only daily history: repeat same-day polls replace the same day's stored observation rather than inventing many daily bars. The current JSON detail contains only the latest fetched distribution (as designed).

## Checks before considering this live

- Confirm AAPL detail now contains at least one `paths` object with realistic nonnegative days, genuine source timestamp and model provenance.
- Validate `NVDA` and `SPY` and compare source CBOE delayed quote timestamps.
- Confirm an intentionally failing / rate-limited ticker retains its older original `as_of` date.
- Confirm the full scheduled scan and new supplemental run can publish without data-loss conflicts.
- Confirm the company page renders meaningful *partial* data for a legacy record with missing `paths`.
- Be mindful that CBOE can respond 403/429 for certain underlyings; missing data remains missing rather than invented.

**Important:** Options-derived paths represent a *risk-neutral model distribution*, not a forecast. CBOE delayed data is not real-time or comprehensive exchange-wide historical options data.
