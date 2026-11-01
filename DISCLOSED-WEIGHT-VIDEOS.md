# Disclosed portfolio and transaction composition videos

The Video studio's **ETF / 13F / officials weights** mode now provides holdings bars, sector share areas, company share areas and weight changes in percentage points. Existing Sector weights calculations and Dow weighting are unchanged.

## Inputs and denominators

- ETF / index proxy: existing `etf/weights/{ticker}.json` history and `etf/e/{ticker}.json` latest disclosure. NAV weights remain unscaled. Dow continues to use DIA as a price-weighted-index tracking proxy.
- 13F: `shards/holdings/{CIK}.json` and its complete dated position shards. Ordinary security values are divided by total reported 13F value, not AUM. Options and unresolved securities remain in the residual. Report dates, filing dates and amendment sources remain available in the built model's evidence. Latest amended snapshots are restated history, not point-in-time backtest data.
- Officials: `market/officials-trades.json`, exact disclosed person name and optional purchase/sale filter. Monthly company/sector composition uses disclosed dollar LOWER BOUNDS. It is neither a holdings reconstruction nor exact transaction value. Buys and sells are gross, not netted. The published feed contains at most 4,000 recent transactions across all people; boundary months and history can be incomplete. Annual asset-report holdings are not implemented by this change.

## Views

Company areas use fixed Top N names selected by maximum disclosed weight over the selected period, plus Other. Labels are ticker/security level: share classes are not consolidated into a legal issuer. Sector mapping prefers source tags and otherwise uses current rank metadata. Other includes undisplayed companies and coverage gaps; it is not a GICS sector.

A single disclosure yields a dated static card. No history is manufactured before the first report. Area animation between reports is illustrative. Exposures above 100% are rejected by the 100% area view, with holdings bars offered instead.

Weight changes compare adjacent selected disclosures, show signed percentage points, and rank by absolute magnitude so decreases remain visible. They include valuation effects and do not prove purchases, sales or active rebalancing. Select company or sector grouping. At least two disclosures are required.

The existing animation, end card, share URL and export pipeline is reused. New presets expose SPY company history, Berkshire 13F, ETF allocation changes and official transaction composition. Future builds' new source snapshots are picked up through the existing published endpoints; this PR adds no new crawler or schedule.

## Quarterly ETF history, the Hub's player and 13F crowding (November 2026)

- **Every ETF's quarter-end portfolios since 2019.** `app/etf.py` reads each SEC Form N-PORT data set once (`nport_weights`): every public quarter-end report of every ETF series, all long equity lines, kept compact on the `etf-history` branch (`cache/nport_weights/<set>.json.gz`, about 3 MB a set). Older sets are back-filled a few a run (newest first, to 2019 Q4). The build (`quarterly_history`, `history_by_symbol`) names each line by ticker (the fund's own, the CUSIP map, or the ticker other funds give for the same CUSIP/ISIN) and sector (the consensus data's, else the issuer's other share class, else the Select Sector SPDR / Vanguard sector ETF that holds it), and publishes per ETF a `quarterly` block in `etf/weights/{ticker}.json`: the fund's largest names — the same names every quarter, weights exact — and sector weights over every long equity line. `actual-weights.js` turns the block back into snapshots, uses the sector weights for sector areas, and scales a report whose equity lines add to a little over 100% of net assets (≤ 102%) to exactly 100%, with a note. `etf/sectors.json` publishes the build's sector of every company ETFs hold.
- **13F records where the Hub publishes them.** 13F shards are read from the place `data/remote.json` names (raw repository files; they are too big for Pages), and positions a report does not name by ticker are named through `market/cusip-tickers.json`. 13F report periods and N-PORT report dates count as reported dates.
- **The Hub's player** (`disclosures/docs/hub-video.js`): the ETF scanner's one-ETF page and the 13F holdings tab's manager view embed the studio engine (loaded when the panel scrolls into view; `studio.js` reads `FF_HUB` / `FF_DATA` for the Hub's paths) with stock bar race, stock areas, sector areas and changes, shape, length and look, play and **Export MP4**, and a link into the full studio.
- **Crowding** (`app/crowding.py` → `market/crowding.json`, `disclosures/docs/crowding.js`): per stock and quarter, over every 13F manager that filed — managers holding, managers with it among their ten largest stock positions (managers with 20+ stock positions), value held; score = 100 × √(breadth × top-ten share), an absolute 0–100 level. Sectors weight the stocks' scores by value; the tilt compares the managers' sector mix with the market's (Vanguard Total Stock Market's quarter-end N-PORT weights). Views: 13F holdings → Crowding (sector and stock tables, CSV, six videos), and the crowding of one ETF's or one manager's holdings with its own videos.

## Validation

- `node tests/test_actual_weights.cjs`
- `node tests/test_disclosed_weight_views.cjs`
- `node tests/test_studio.cjs` (215 checks)
- `node --check web/studio.js`
- `git diff --check`

Tests cover residual preservation, disappearing holdings, signed changes, 13F option exclusion and original denominator, official lower bounds and buy filtering, and single-date behavior. Browser MP4 export and a production deployment have not been verified for this change.

The November 2026 additions: `node tests/test_actual_weights_quarterly.cjs`, `disclosures/tests/test_etf_history.py`, `disclosures/tests/test_crowding.py`, `node disclosures/tests/test_crowding_view.cjs`; the Hub's player was run in headless Chromium against six real N-PORT sets (2025 Q2 – 2026 Q3) and a 701-manager 13F sample, and exported a 1920×1080, 30 fps, 12 s MP4.
