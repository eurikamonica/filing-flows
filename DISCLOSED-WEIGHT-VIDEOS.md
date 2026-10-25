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

## Validation

- `node tests/test_actual_weights.cjs`
- `node tests/test_disclosed_weight_views.cjs`
- `node tests/test_studio.cjs` (215 checks)
- `node --check web/studio.js`
- `git diff --check`

Tests cover residual preservation, disappearing holdings, signed changes, 13F option exclusion and original denominator, official lower bounds and buy filtering, and single-date behavior. Browser MP4 export and a production deployment have not been verified for this change.
