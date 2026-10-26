# Flo 5-Minute Momentum Relay

A configurable US index-component top-gainers scan implemented on PR #72. It does not pretend that static daily-close snapshots are live minute prices.

## Web and Flo chat

A **Flo · 5m** control opens a screen with S&P 500, Russell 1000 and Russell 2000 scope selectors, minimum 5-minute percentage gain, 5-minute dollar turnover, consecutive top-list streak, and quiet mode. Flo chat recognizes "S&P 500 五分钟涨幅榜", "Russell 2000 5m gainers", and similar prompts. The page fetches its authorized Supabase latest-snapshot projection once a minute while open. The first valid snapshot produces no retrospective popup. A new highest-ranked mover with sufficient gain may trigger a Flo jumping animation and small popup no more than once per five minutes.

For every returned stock the actual 1-minute candle end times must be EXACTLY 5 minutes apart. 5m % = (last candle close / previous candle close − 1) × 100. No exact start or end bar, impossible price, stale latest bar or outside regular US session => skip. Missing intermediate minute bars mark traded volume as incomplete. Only fully observed 5-minute turnover can pass a dollar-turnover filter.

## Market data source

The server producer scripts/flo_momentum.py uses Alpaca multi-symbol historical one-minute candles, authenticated only on the backend. IEX is free/single-venue and does NOT represent the consolidated US tape or guarantee comprehensive Russell coverage. SIP requires subscription/entitlement; delayed SIP is NOT realtime. The output includes feed name, precise as-of time and universe coverage. Under 80% of index members with usable exact five-minute bars, the ranking is explicitly labeled **partial observed subset** and is not described as the full index's actual top gainers.

S&P 500 membership is parsed from a current, unofficial Wikipedia constituent-table fetch and must be 450–520 tickers. The repository's June 2024 S&P historical constituents cannot be used as current members. Russell 1000 and Russell 2000 use independent, licensed curator-supplied dated files in config/flo-market-universes. Those scopes remain unavailable without them. Using an IWB/IWM ETF portfolio to pretend to know all Russell constituents is prohibited.

## Activation steps (operator)

1. Run db/flo-momentum.sql ONCE in Supabase SQL editor to create the guarded latest-snapshot table. Row level security defaults to not publicly readable.
2. Set GitHub Secrets: ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY, SUPABASE_SERVICE_KEY. Set repository Variables: SUPABASE_URL, FLO_MINUTE_FEED (iex / sip / delayed_sip).
3. If scanning Russell indices, upload complete, dated and legitimately sourced constituent lists: russell1000.json and russell2000.json as instructed by config/flo-market-universes/README.md. No Russell membership data is invented in this PR.
4. Only after reviewing the applicable exchange/market-data supplier redistribution licenses may the operator set FLO_MINUTE_PUBLIC_LICENSED=true. It is false by default. No restricted market prices or service/API keys are exposed in client JS.
5. After merge, .github/workflows/flo-momentum.yml requests a scan every 5 minutes from 13:00 to 22:55 UTC on US weekdays. GitHub cron can be late or skip runs and is not a hard real-time SLA. Use a persistent licensed websocket worker if guaranteed low-latency consolidated exchange coverage is needed.
6. Merge and publish the site's web/flo-momentum.js through the ordinary site deployment. The static webpage uses data/site.json's already-published Supabase URL and anon key to SELECT ONLY permitted rows. If the source is absent, outdated by 12+ minutes, private, or missing a valid membership, Flo states that the scan is unavailable. It NEVER falls back to daily extremes.json as fake minute data.

## QA and deliberate limitations

Tests: tests/test_flo_momentum.py (exact interval, trading-session, membership, API pagination, price/turnover, streak and rights gating) and tests/test_flo_momentum.cjs (frontend filters, time-staleness, missing memberships and no retrospective popup). Dedicated five-minute check and established Flo Pulse CI now run these tests.

Not yet built: server-side guaranteed websocket streaming, genuine full SIP data entitlements, a licensed official Russell membership feed, full market holidays calendar, corporate-action adjustments, an intraday event-study/causality analysis, and public quote-redistribution authorization. A PR commit or successful unit tests do NOT imply a production scanner is already publishing live data.
