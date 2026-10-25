# Changelog

## Weekly history from 1990; index membership, now and before

The weekly grid (`rotation_history.START`) now begins on 1990-01-05: rrg.json, every t/<SYM>.json, the industry and
sector indices, the studio's leaderboards (months from 1990) and the forecasts read the longer history as the collector
refetches each ticker since 1990 (format 3). `macro_history` takes its grid from `START`, and the gravity model places
macro.json by date. The ETF collector asks Yahoo for every week since 1990 (or the launch), so `etf/px/<SYM>.json`
carries the whole history. Before an ETF existed, the indices themselves (IDX-GSPC, IDX-NDX, IDX-DJI, IDX-RUT,
IDX-IXIC; price only) stand in.

`app/index_members.py` (run by `etf.build`, file `etf/members.json`): the indices each company belongs to now — from
the full holdings of the ETFs that track them (S&P 500: IVV / VOO / SPY; Nasdaq-100: QQQ; Dow: DIA; S&P 400: IJH /
MDY; S&P 600: IJR; Russell 1000: IWB; Russell 2000: IWM; Russell 3000: IWV) and Wikipedia's S&P 500 list (CIK, date
added) — and before: the S&P 500's dated changes since 1997 (kept in `config/sp500-history.json` from the page's
mid-2024 revision, which still carried the table; later monthly revisions when Wikipedia answers), the Dow's
historical components (one table per change, matched by name), the other indices from now on. A reused ticker is
kept apart by name (CCI was Countrywide Credit in 1997, Crown Castle now). The site's company pages show the tags
(“S&P 500 · since 1982”, “Former Dow 30 · 1999–2024”); the studio's leaderboards filter by index, by members at each
step (S&P 500, Dow) or today's. Tests: `tests/test_index_members.py`.

## The four indices around their centre (QQQ, SPY, IWM, DIA)

`app/index_rrg.py` (run by `chaos_forecast.build`, file `index-rrg.json`; its own frozen ledger `ledger/index.json`,
`index-ledger.json`, run by `forecast_ledger.update`). SPY overlaps the other three, so against SPY the RRG only says
"more tech or more value than the S&P" and SPY itself cannot be drawn. Each index is measured against the centre of
the four — their volatility-weighted geometric mean (weights ∝ 1 / the 26-week volatility known when the week starts;
the weighted relative moves add up to zero) — and the centre against cash (FRED DGS3MO). Fixed in advance: four
centres (SPY, equal-weight, volatility-weighted, cash), chosen on weekly origins 2003–2011 by the quadrant matrix's
Brier skill against the weaker of two baselines (ties within 0.002 by RS-Momentum's correlation with the next four
weeks), reported from 2012 for all. Result: SPY 5.11%, equal 5.14%, volatility-weighted 5.17%, cash 3.66% on
2003–2011 — the first three tie, the volatility-weighted centre has the highest correlation and is used; from 2012 all
four score 5.2–5.4%, and RS-Momentum does not predict the next four weeks' relative return for any centre (Spearman
−0.02 to −0.06). The published model (weekly origins, block bootstrap, independent origins = weeks / h): quadrant odds
calibrated at 1 and 4 weeks, experimental at 13; conditioning on the centre's quadrant against cash adds nothing; the
weekly chain calibrated at 1 week; "which index leads next" loses to "the leader stays" (history only). Joint replay
price ranges: the last three years (chosen on 2003–2011 over the volatility-scaled ten-year replay) cover 75% / 45–48%
at 4 and 13 weeks from 2012 (experimental; the scaled replay did better out of sample: 76–78%). The hub's RRG shows it
as Lines → "The four indices around their centre" (`docs/rrg-index.js`): odds, routes, replayed prices, next week's
close for each quadrant (the index's own weight in the centre taken out), the leader, the comparison and the ledger.
Tests: `tests/test_index_rrg.py`.

The weekly collector's full fetch reaches back to 1990, and the S&P 500, Nasdaq-100, Dow, Russell 2000 and Nasdaq
Composite indices themselves are kept (price only, `t/IDX-*.json`) for the years before their ETFs.

## Video studio data: leaderboards, stock dividends, market value, P/E and P/B

`app/rank_panel.py` (run by `rotation_history.build`) publishes `public/rank/` for the studio's leaderboards: every
company of the site's month-end total-return close, monthly dollar volume and month-end market value since 2000, and
quarterly revenue, gross profit, operating income, net income and equity from the SEC frames (2009 on), one file per
measure, so the browser ranks any measure within a sector and a market-value range. Market value = the month-end close
as traded × shares outstanding then: the 10-Q / 10-K cover-page count (dei, never restated), the diluted weighted
average where a company has several share classes, net income ÷ diluted EPS where neither is tagged; put on today's
basis with Yahoo's split history; weighted averages restated after a later split are put back on the right basis, and a
count tagged in thousands (or millions) is caught against its neighbours. Nasdaq's screener (one request) checks today's
value: an ADR or class basis (off by more than 0.55–1.8×) rescales the history, a recent issue or buyback (more than
10%) adds today's count; about 50 companies without an SEC count get today's count held back five years at most,
flagged. Backstops drop a value above $15 trillion, worth more than 10,000 months of trading, or with twenty times
today's share count. `frames.py` collects the cover-page shares, diluted weighted-average shares, diluted EPS and
equity (`EXTRA`), and skips a fourth quarter derived from a year tagged at another scale (Arista's 2025 net income,
3,511 for $3.5 billion, left a fourth quarter of minus $2.6 billion; the momentum clock's figures are fixed too).

The weekly collector keeps Yahoo's dividends and splits and the close as traded (cache format 3: every ticker is fetched
again in full once); `t/<SYM>.json` gains `p` (the close as traded), `d` (dividends by week) and `sp` (splits), so a
stock's growth video can split dividends out or leave them out. A refresh no longer loses dividends: Yahoo restates
every earlier adjusted close after each new dividend or split, and the rows on file were merged on the old basis (each
dividend since the first full fetch fell out of the total return as a step down where the refresh began); they are now
rescaled to the new basis in the first week the two answers share. Tests: `tests/test_rank_panel.py`.

## Company pages: Rotation (RRG) — against the S&P 500 and against the industry, with prices, ranges and transitions

A company page gains *Valuation & expectations → Rotation (RRG)* (`docs/rrg-company-view.js`, listed in views.json):
two Relative Rotation Graphs, the company against SPY (its industry in grey) and against its industry without itself.
Each has (1) the close next week that puts it in each quadrant — the closes at which RS-Ratio and RS-Momentum cross 100,
solved exactly from the formula with the benchmark flat; (2) replayed ranges — every 13-week run of its weekly moves
against the benchmark in the last 156 weeks, replayed from this week through the formula: the trajectory fan, 80% boxes
at 4 and 13 weeks, and price / RS-Ratio / RS-Momentum ranges 1, 4 and 13 weeks on; (3) the Markov matrix at 1, 4 or 13
weeks (by the industry's quadrant for the industry chart), its row highlighted, with its out-of-sample scores and label;
(4) the weekly chain's quadrant probabilities for weeks 1–13 and its most common paths. Probabilities show only for
calibrated or experimental heads and liquid companies; the rest as history.

`transition_rrg.band_check` checks the replayed ranges walk-forward from 2012 (origins every 13 weeks, liquid
companies; fixed in advance: calibrated when the 80% and 50% coverages are within 3 points of nominal). Against SPY the
80% / 50% price ranges held 80.5% / 52.2% at 1 week (calibrated), 77.4% / 48.1% at 4 weeks (calibrated), 73.6% / 45.8%
at 13 weeks (experimental: too narrow); against the industry 82.7% / 54.3% (experimental), 78.7% / 49.5% (calibrated),
73.9% / 46.0% (experimental). A pure random walk gives the same 13-week shortfall (73–75%): three years hold only about
a dozen independent 13-week runs. JS and Python step the formula identically (tests on both sides).

## RRG quadrant odds and future paths, gated walk-forward (research specification v5 §4.4, §8.3, §8.4, §11)

`app/transition_rrg.py` (run by `chaos_forecast.build`, file `rrg-transition-model.json` on the branch
rotation-history) estimates where a line on the weekly 14-week RRG stands 1, 4 and 13 weeks later from smoothed
empirical transition matrices (row → (N + 10 · prior) / (N + 10)), for three kinds of line: sectors and ETFs against
SPY (40 lines), the site's companies against SPY, and companies against their leave-one-out industry (dual RRG);
companies count only while liquid. The RRG is the chart's own formula, vectorised (identical to `rrg_series`).

Fixed before any result was seen: which matrix each line reads (quadrant only for the two market groups, the
industry's quadrant × the company's quadrant for the dual RRG), the weekly chain for paths ((quadrant, direction of the
last step), or (industry quadrant, company quadrant)), the baselines (stays in its quadrant; the usual quadrant
shares), the test (walk-forward from 2012-01-06, origins spaced by the horizon, only pairs whose outcome was known at
the origin; Brier and log-loss skill with 95% bootstrap intervals over origins; classwise calibration error, 10 bins)
and the labels: *calibrated* (both intervals above zero, error ≤ 2 points, ≥ 50 origins and 2,000 predictions),
*experimental* (beats both, not all of that), *descriptive only* (loses to a baseline: history, not a forecast),
*insufficient data*.

First results (2002–2026 pairs, today's companies): every head beats both baselines at every horizon. Labels of the
heads the chart uses — sectors / ETFs: 1 week calibrated, 4 and 13 weeks experimental (calibration error 2.3 and 3.8
points); companies vs SPY: 1 and 4 weeks calibrated, 13 weeks experimental (2.5 points); companies vs their industry:
calibrated at 1, 4 and 13 weeks. Brier skill over staying put: about 4% at 1 week, 10–11% at 4 weeks, 2–4% at 13
weeks; over the usual shares: 46%, 13% and 1.6–2.4%. Conditioning on the industry's quadrant adds nothing measurable
over the company's own quadrant (13 weeks: 2.26% vs 2.25%). The weekly chain is calibrated at 1 week and experimental
at 4 and 13 (it spreads weight onto moves that hardly happen, calibration error 2.7–5.0 points), so the direct matrices give the
odds at 1, 4 and 13 weeks and the chain gives the weeks between and the paths.

The RRG (2-D, weekly, 14 weeks) gains *Quadrant odds and paths*: every line's odds at the chosen horizon with its
label (grey history shares where the label is not calibrated or experimental), and for one picked line its odds at 1,
4 and 13 weeks with the scores, each quadrant's probability for weeks 1–13, the five most common 13-week paths
(seeded simulation), and on the chart its odds in each quadrant's corner and its three most common paths. Shown for
the latest week only (the matrices are fitted on the whole history). Industry indices, baskets and illiquid companies
have no model. `tests/test_transition_rrg.py`: formula parity, codes, liquidity, smoothing, predictions at an origin
unchanged by scrambling every later week, the label rules, a known chain recovered and called calibrated, noise not
called a forecast, the published file.

## Dual RRG: companies against their industry without themselves (research specification v5 §4.2, §15.4)

`rotation_history.industry_benchmarks` gives every company with weekly prices an industry benchmark — the most
specific of SIC4, SIC3, SIC2 or the site sector with at least five other companies — as two weekly indices in its
`t/<T>.json`: `bx` without the company (leave-one-out, so a dominant stock does not define its own peers) and `bi` with
it, weighted by the log of revenue reported by each week. The RRG gains “Companies against: their industry without
themselves”: each company against its leave-one-out industry, and each of those industries against SPY, on one chart.
`chaos-rrg.json` `transitions.dual` describes, by where the industry stood against SPY and the company against its
industry, where the company was 1, 4 and 13 weeks later (descriptive only). Membership is today's companies. A member
counts in a week only while liquid (≥ $3, ≥ $10M weekly dollar volume over 13 weeks): Experiment 1 (`notes/dual-rrg/`)
showed that against all members an industry's trend mostly measured illiquid members running further than liquid
ones; its pre-registered "second layer adds information" result does not survive a liquid-peer benchmark (post-hoc
check, reported as such).

## RRG: the mechanical baseline and quadrant transitions (research specification v5, P1-05)

The weekly RRG backtest now scores the mechanical step (G0: no relative move next week, the smoothing carried
forward) beside the analogues, rotation continuation and the linear map, with each model's skill beyond G0 and how
often each gets next week's quadrant right (staying put included). `chaos-rrg.json` gains `transitions`: descriptive
quadrant-to-quadrant shares after 1, 4 and 13 weeks for sectors / sector ETFs and for companies against the S&P 500,
with Wilson intervals, the range across years and the count of non-overlapping windows; shown under the RRG.

## Rotation axis registry (research specification v5, P0-02)

`app/axis_registry.py` gives every Rotation X/Y/Z variable one contract — cadence, when an observation is public
(price variables at the period's close, filed ones a period later), missing policy (unknown, not zero; 13F and
officials only in covered quarters), transforms, smoothings, whether a forecast is published (`experimental`) or not
(`descriptive_only`) — and two ids: `semantic_axis_spec_id` (what a chart configuration means; a data refresh never
changes it) and `prediction_artifact_id` (plus the run's versions, origin and cutoff). `rotation.json` vars carry the
contract fields; the forecast files carry the id of what they forecast; the Momentum clock and 3-D captions show the
id of the configuration on screen, computed in the browser with the same canonical JSON and SHA-256 as Python
(`tests/test_axis_registry.py` checks the keys, the price/filed split, the controls and the ids against rotation.py,
chaos_forecast.py and rotation.js). `data/market/axis-registry.json` is published with the hub.

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
every close after week T and check that earlier forecasts are bit-identical). Quarterly/monthly origins before the test start
are labelled an in-sample warm-up. Sector suns and the market centre (Rotation chart, `rotation-long.json`, the monthly
forecast panel), the weekly site-sector indices and the gravity model's planets are now rebuilt as of each period: clip bounds over the periods up
to then, weights = the revenue reported by then (the quarter before; weekly: 46 days after the quarter, SEC frames).
The latest period is all but unchanged; earlier suns move slightly. Only survivorship (today's companies) remains, and
is stated in `caveats`. Ledger origins frozen before this change are kept as they were. Tests:
`tests/test_temporal_integrity.py`.

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
