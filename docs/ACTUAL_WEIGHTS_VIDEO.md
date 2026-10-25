# Actual ETF / Index Weights video (new, additive)

The existing Sector Weights video is **not** modified. It continues to display total market-capitalization shares of the selected companies.

## New Video Studio mode

Video Studio now includes "Actual ETF / index weights", with an index-tracking-ETF option and an ETF-ticker option. There is a holdings bar race or sector share area view. The usual preview, share links, MP4 export and end card remain available.

In index mode, the selected fund is a **tracking proxy**, not an official licensed index data feed:

- Dow Jones Industrial Average: DIA (DJIA itself is **price-weighted**; weights proportional to constituent share price, NOT capitalization).
- S&P 500: SPY (S&P uses float-adjusted market capitalization).
- Nasdaq-100: QQQ (modified market capitalization weighting).
- S&P MidCap 400: IJH; S&P SmallCap 600: IJR; Russell 1000: IWB; Russell 2000: IWM; Russell 3000: IWV.

Official Dow method: https://www.spglobal.com/spdji/en/methodology/article/dow-jones-averages-methodology/

DIA's actual disclosed NAV holdings weights are a price-weighted tracking **proxy**. They can deviate slightly from published DJIA index weights because of fund cash and tracking. Do not label these as official index weights; never substitute the companies' market capitalizations for Dow's price weighting. Past splits cannot be reverse-engineered from today's split-adjusted prices.

## Data and safety boundaries

The existing ETF builder additionally invokes disclosures/app/actual_weights.py. ETF-history branch persists real disclosure-date snapshots in cache/actual_weights/ and publishes weights/<TICKER>.json. The deployment already copies the complete ETF public folder into disclosures/data/etf/.

Source: ETF pages (e/<TICKER>.json) created from fund sponsor filings or SEC N-PORT; source dates are holdings.date, not scrape time or build time.

Historical data coverage begins only when this module accumulates disclosed snapshots. Existing past-only membership lists, today's constituents, or today's prices are **never** substituted for historic portfolio weights. The top 250 ETFs by assets plus core index trackers get persistent snapshots; other ETFs can still produce current one-report videos if holdings are available.

No data means an explicit error; one date means a single-date bar card. Two or more real report dates allow a transition animation with a visible disclaimer: intermediate frames are *visual interpolation*, not measured holdings. A report with the same date replaces its earlier snapshot, rather than creating fake higher-frequency data.

Holdings bar weights are original fund NAV weights, never normalized to an observed subset. The sector share chart groups genuine holdings and puts uncovered assets, cash and unmapped holdings into Other. Sector names may come from the fund's own tags or the site's classification; do not call them official GICS when they are inferred. ETF snapshots record up to 600 positions and retain up to 60 disclosed dates.

## Regression checks

Run:
- python -m unittest disclosures.tests.test_actual_weights
- node tests/test_actual_weights.cjs
- node --check web/actual-weights.js
- node --check web/studio.js

The offline CI job includes the new JavaScript test, and its disclosures test discovery covers the new Python unit test.
