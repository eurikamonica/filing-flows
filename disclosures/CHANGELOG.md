# Changelog

## Crowd Flow clocks (research specification v5, first slice: P0-03, P0-04, P1-05, part of P0-01)

The Hype map keeps the original Signals map as *legacy snapshot* and adds two views with one clock each:
*quarter-aligned* (the same quarter on both axes, retrospective) and *public as of the 13F deadline* (only filings filed
before the first close after the deadline, the trailing three months to it, and what the stock did next against SPY).
13F changes count only comparable managers (complete, non-confidential reports for both quarters); missing filings are
unknown, not zero, and coverage is shown. Every checkpoint sees each report as it stood then, so later amendments and
late filings never rewrite an earlier as-of state (truncation invariance, tested end to end). New
`market/crowd-transitions.json` and `transition-matrix.js`: descriptive quarter-to-quarter quadrant transitions with
sample sizes, intervals and baselines, post-deadline returns by quadrant with a shuffled control, and the calendar-only
filing-arrival baseline. Officials' PTRs appear as separate marks. The forecast ledger keeps each late-added company's
own first publication time and scores late rows apart.

Look-ahead audit of the Rotation forecasts (spec v5 §1.1): the weekly RRG analogues' metric and the benchmark drift
added to their prices now use only the weeks before each origin (`causal_scale`, `expanding_log_drift`; tests change
every close after week T and check that earlier forecasts are bit-identical). Still retrospective, now labelled on the
page and in `caveats`: quarterly/monthly origins before the test start are an in-sample warm-up, and the sector suns /
market centre use full-history clip bounds, latest-revenue weights and today's companies.

## Rotation: next step and the 3-D / 4-D solar system

Rotation gains a *Next step* control (momentum clock, solar system, 3-D box, RRG) and a new chart, *Solar system 3-D / 4-D*
(market or one sector, a third coordinate or time as depth; in a sector every company keeps its trail, also in the 2-D
solar view). Forecasts by the method of analogues in delay-embedded solar coordinates (`app/chaos_forecast.py`), calibrated
walk-forward, with the price read from the stock-vs-S&P coordinate (quarters, months) or by inverting the RRG's exact
one-week map. Built by the rotation-history workflow; tests in `tests/test_chaos_forecast.py` (including a check that
changing the future leaves past forecasts bit-identical); backtest and chaos tests in `notes/chaos-forecast/`.

## 4.1.0

Officials' disclosures beyond the US House: New York State (COELIG statements, HTML, value categories), California
(FPPC Public Official Financial Disclosure Portal, Form 700 PDFs since 2025), Canada (federal public registry
declarations); Texas and Canada SEDI as imports with an honest status (no public online PFS viewer; SEDI bot
protection probed every run). Optional price-based cost estimates: Stooq daily closes + OpenFIGI CUSIP→ticker;
13F quantity change × quarter-average close, reviewed transactions priced on their date; toggle in the UI, stored
per browser. Jurisdiction filter, per-jurisdiction health table, `prices` module. HTTP client gained POST/JSON,
cookies and challenge-page detection. Verified against the live sources: California downloads use the portal's
`GET GetRedactedFormPdf?indexID&fileNameInfo.*` call; New York statements are served as PDFs; the Canadian registry
lives at ethicscanada.ca (profile pages); SEDI is probed at its root. Per-jurisdiction batch shares, cursors for the
NY index, CA partition rotation and the Canada listing, resilient data commits.

## 4.0.0

Broad COT and active-FDIC catalogs with rotating history queues; two-stage N-PX discovery/download queue; per-entity histories and 1,000-row vote chunks; demand-loaded catalogs; priority bank/market inputs and hourly markets run; v3 data migration; source-count validation and COT consolidated-code support.

## 3.0.0

SEC 13F/N-PX index discovery; unfiltered House index catalog; durable batching and priority Actions inputs; quarter shards and compressed caches; directory and coverage counters; redesigned responsive workspace; complete asset names and compact intervals; centered weight-change bars; position sorting; treemap-to-security selection; missing House dates no longer discard an index; large-manager security menu lookup optimized.

## 2.0.0

Integrated prior 13F library and tests, House watchlist PDF/OCR, reviewed records, English interface and Actions/Pages template.

## 1.1

Configured COT, bank financials and N-PX; SEC contact set to Filing Flows filingflows@gmail.com.
