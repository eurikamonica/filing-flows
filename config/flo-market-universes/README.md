# Flo Market Momentum: index-membership requirements

S&P 500: the producer fetches the *current* Wikipedia S&P 500 constituents at run time, and refuses scanning unless 450-520 valid tickers were found. This unofficial list is dated and labeled, and a stale 2024 file is never used as current membership.

Russell 1000 and Russell 2000: add russell1000.json and russell2000.json here with complete licensed constituent lists. Input format:
{ "as_of": "2026-10-01", "source": "Licensed FTSE Russell constituency, effective date 2026-10-01", "symbols": ["AAAA", "BBBB"] }

The above is only a SCHEMA EXAMPLE; fake tickers are not data. The parser rejects lists below 600 tickers, duplicates-heavy lists, and snapshots older than 110 days. Do not substitute IWB/IWM ETF holdings for index constituents. Index compositions can change between reconstitutions.

Backend: Alpaca multi-stock 1Min candles (IEX = ONE exchange, NOT national consolidated SIP). Workflow runs every 5 minutes when GitHub scheduling permits; delays are expected. Secrets ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY and SUPABASE_SERVICE_KEY stay on GitHub Actions only. SUPABASE_URL in repository variables.

To expose any licensed minute data publicly, confirm your Alpaca/exchange market-data redistribution rights and then explicitly set repository variable FLO_MINUTE_PUBLIC_LICENSED=true. The Supabase RLS default is deny-all for the public when unset. This is a legal/data-contract gate, not a market-data subscription check.

Run db/flo-momentum.sql once in Supabase SQL editor. Real five-minute ranking is unavailable until this setup and the index membership data are valid. No simulated returns are emitted on failure.
