# Next-step forecasts for the rotation charts — backtest and experiments

Code: `disclosures/app/chaos_forecast.py` (site files), `disclosures/app/chaos_experiments.py` (this note's experiments), page: `disclosures/docs/chaos.js`.
Data: branch `rotation-history` built 2026-10-17 — 250 companies × 65 calendar quarters (CY2010Q3–CY2026Q3), 225 months (2008-01 – 2026-09), weekly adjusted closes since 2000. Today's companies only (survivorship).

## What a forecast is

Each dot sits in solar coordinates: company = market + (sector sun − market) + (company − sun). For every dot the engine
takes its position, velocity and acceleration (delay embedding, m = 3) in units of typical spread, finds the 60 (quarterly) /
100 (monthly) most similar past states of any company whose next step was already public, and averages their next steps
(Gaussian kernel). A stacked calibration learnt only from earlier forecasts then chooses, per coordinate and per
local-divergence tercile, how much of that step to trust versus *stay put* and *fall back to the sun*.
Price-based coordinates are known at the period's close; margins and growth are lagged one quarter (filed weeks later).
Companies without filed figures (e.g. no `OperatingIncomeLoss` tag) use a price-only phase space with its own calibration.

Price: `rel` (stock vs S&P) is a price coordinate, so next close = close × (1 + forecast rel + past average S&P return);
intervals are conformal in log price, scaled by the stock's trailing 8-quarter / 12-month move. On the weekly RRG the next
(RS-Ratio, RS-Momentum) is an exact function of next week's close (the browser's formula, ported and checked to 1e-14), so
the close whose next point is nearest the forecast is the price read back from it.

No look-ahead is tested directly: rewriting every value after an origin leaves that origin's forecasts bit-identical
(`tests/test_chaos_forecast.py`).

## 1. Scorecard (walk-forward, quarterly test CY2015Q1–CY2026Q2 = 46 quarters; monthly 2013-01–2026-08 = 164 months)

Planet layer (each company relative to its sector sun). *Arrow* = cosine of predicted vs actual step > 0 in the default plane
(quarterly dom × rel, monthly hi52 × rel). *Landing* = MSE of the next `rel` position vs the better naive rule (back to the sun).

| Model | Arrow right (q) | Arrow right (m) | rel landing vs sun (q) | rel landing IC, 95% CI (q) | rel landing IC (m) | Top−bottom fifth, pts (q) |
|---|---:|---:|---:|---:|---:|---:|
| Stay put | — | — | -100.1% | -0.008 [-0.050, 0.036] | -0.014 [-0.035, 0.007] | — |
| Back to the sun | 81.0% | 77.1% | 0.0% | — | — | — |
| Keep moving (momentum) | 31.3% | 35.3% | -489.3% | -0.011 [-0.051, 0.031] | -0.011 [-0.030, 0.009] | -0.87 [-2.52, 0.71] |
| Gravity (pooled AR(1)) | 81.0% | 76.2% | -0.3% | -0.008 [-0.050, 0.036] | 0.013 [-0.008, 0.034] | -0.61 [-2.40, 1.19] |
| Linear phase-space map (damped rotation) | 81.4% | 76.1% | 0.1% | 0.029 [-0.018, 0.075] | 0.004 [-0.022, 0.033] | 3.46 [0.99, 6.19] |
| Analogues, raw | 76.1% | 74.9% | -39.0% | 0.001 [-0.035, 0.041] | -0.004 [-0.023, 0.015] | 0.22 [-1.52, 2.25] |
| **Analogues, calibrated (site)** | 80.4% | 76.3% | -0.3% | -0.012 [-0.041, 0.016] | -0.002 [-0.018, 0.013] | 0.05 [-1.33, 1.34] |
| Placebo: analogues with shuffled next steps | 50.8% | 50.1% | -102.9% | -0.014 [-0.056, 0.030] | -0.014 [-0.035, 0.006] | -0.56 [-2.42, 1.28] |

**Reading.** The arrows point the right way ~80% (quarters) / ~76% (months) of the time — far above the 50% placebo —
but *back to the sun* scores the same: the predictable part of a dot's motion is gravity toward its sector average
(stock-vs-S&P returns do not persist, so last period's outlier snaps back). Where the price coordinate lands is not
predictable: every model's IC is within ±0.04 of zero. The one interval that clears zero is the linear map's quarterly
top-minus-bottom spread (+3.5 pts, CI 1.0–6.2), with its IC still spanning zero — a hint, not an edge.

## 2. Landing skill by coordinate (vs the better of stay put / back to the sun; quarterly)

| Coordinate | Analogues, calibrated | Linear map | Gravity AR(1) | Stay put vs sun |
|---|---:|---:|---:|---:|
| rel | -0.003 | 0.001 | -0.003 | 0.500 |
| rel6 | 0.407 | 0.427 | 0.230 | -0.035 |
| vola | 0.224 | 0.305 | 0.207 | -0.185 |
| volz | 0.205 | 0.019 | 0.211 | -0.153 |
| rs | 0.218 | 0.132 | 0.220 | -0.138 |
| mom121 | 0.170 | 0.470 | 0.123 | -0.724 |
| hi52 | 0.159 | 0.160 | 0.161 | -0.495 |
| dom | 0.062 | 0.192 | 0.025 | 0.341 |
| om | 0.221 | 0.060 | 0.157 | -0.311 |
| dgm | 0.001 | -0.366 | 0.016 | 0.279 |
| gm | 0.084 | -0.014 | 0.041 | -2.239 |
| dnm | 0.031 | -0.404 | -0.000 | 0.444 |
| nm | 0.148 | -0.074 | 0.157 | 0.092 |
| revg | 0.134 | 0.141 | 0.126 | 0.225 |
| reva | -0.014 | 0.026 | -0.001 | 0.556 |

Slow coordinates — volatility, volume, RS rating, 12-1 momentum, distance from the 52-week high, operating-margin level,
revenue growth — land 10–38% closer than the best naive rule. Overlapping windows (rel6, mom121) are partly mechanical: next
period's two-quarter return contains this quarter's. Margin *changes* (dom, dgm, dnm) and growth acceleration are noise.

## 3. Embedding grid (`grid.csv`)

| freq | phase space | m | k | arrow right | slow-coordinate landing skill (calibrated) | raw | linear | rel IC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| q | price | 1 | 60 | 80.3% | 0.100 | -0.233 | -0.220 | 0.022 |
| q | price | 2 | 60 | 80.9% | 0.122 | -0.209 | -0.175 | 0.009 |
| q | price | 3 | 60 | 80.9% | 0.126 | -0.216 | -0.163 | 0.016 |
| q | price+fund | 1 | 60 | 80.7% | 0.109 | -0.084 | -0.054 | 0.010 |
| q | price+fund | 2 | 60 | 80.7% | 0.129 | -0.066 | 0.039 | 0.006 |
| q | price+fund | 3 | 60 | 80.4% | 0.145 | -0.088 | 0.077 | 0.007 |
| q | price+fund+volume | 1 | 60 | 80.2% | 0.109 | -0.071 | -0.028 | 0.003 |
| q | price+fund+volume | 2 | 60 | 80.6% | 0.133 | -0.056 | 0.064 | 0.005 |
| q | price+fund+volume | 3 | 60 | 80.4% | 0.145 | -0.082 | 0.126 | -0.001 |
| m | price | 1 | 100 | 76.3% | 0.129 | 0.118 | 0.127 | -0.003 |
| m | price | 2 | 100 | 76.3% | 0.147 | 0.125 | 0.174 | 0.004 |
| m | price | 3 | 100 | 76.3% | 0.164 | 0.133 | 0.190 | -0.004 |
| m | price+rs | 1 | 100 | 76.4% | 0.117 | 0.126 | 0.122 | -0.007 |
| m | price+rs | 2 | 100 | 76.3% | 0.125 | 0.130 | 0.168 | -0.002 |
| m | price+rs | 3 | 100 | 76.3% | 0.153 | 0.143 | 0.188 | -0.008 |

The arrow hit rate does not move with the phase space, m or k (it is gravity). Acceleration (m = 3) helps the landing
of slow coordinates a little — the signature of an oscillator. Raw quarterly analogues overfit (negative skill); the
calibration is what makes them usable. Monthly, a plain linear map beats the analogues on slow coordinates.

## 4. Is it chaos? S-map nonlinearity test (`smap.csv`)

Sugihara (1994): fit locally weighted linear maps with weights exp(−θ·d/d̄). θ = 0 is one global linear map; larger θ is
more local. State-dependent (nonlinear) dynamics — what low-dimensional chaos needs — show skill that rises clearly with θ.

| freq | coordinate | skill θ=0 (linear) | best θ | skill at best θ | gain over linear |
|---|---|---:|---:|---:|---:|
| q | rel | 0.007 | 0.5 | 0.009 | 0.002 |
| q | rel6 | 0.437 | 0.5 | 0.438 | 0.001 |
| q | vola | 0.291 | 2 | 0.297 | 0.006 |
| q | volz | -0.107 | 2 | -0.093 | 0.013 |
| q | rs | 0.147 | 4 | 0.164 | 0.017 |
| q | mom121 | 0.241 | 4 | 0.266 | 0.025 |
| q | hi52 | 0.161 | 2 | 0.165 | 0.004 |
| q | dom | 0.001 | 1 | 0.009 | 0.007 |
| q | om | -0.311 | 0.5 | -0.305 | 0.005 |
| q | dgm | 0.007 | 0.5 | 0.009 | 0.002 |
| q | gm | -3.138 | 2 | -3.101 | 0.037 |
| q | dnm | -0.014 | 1 | -0.009 | 0.005 |
| q | nm | 0.035 | 0.5 | 0.038 | 0.004 |
| q | revg | 0.201 | 0.25 | 0.204 | 0.003 |
| q | reva | 0.024 | 2 | 0.044 | 0.020 |
| m | rel | -0.004 | 1 | 0.003 | 0.007 |
| m | rel3 | 0.464 | 1 | 0.469 | 0.005 |
| m | rel6 | -0.034 | 4 | 0.004 | 0.038 |
| m | volz | 0.213 | 2 | 0.224 | 0.010 |
| m | rs | -0.584 | 8 | -0.425 | 0.159 |
| m | mom121 | -3.420 | 8 | -3.071 | 0.349 |
| m | hi52 | 0.068 | 4 | 0.078 | 0.009 |

Gains over the global linear map are ≤ 0.04 for every quarterly coordinate (≤ 0.01 for most); the price coordinate `rel`
has skill ≈ 0 at every θ. The two larger monthly gains (RS rating, 12-1 momentum) are on coordinates where even the best
map lands worse than *stay put*. Verdict: mostly linear, persistent mean reversion plus noise, with mild state dependence
(volatility, RS rating). No evidence of exploitable low-dimensional chaos.

## 5. Skill against horizon (`horizon.csv`, correlation of analogue forecast with the actual position h steps ahead)

| freq | coordinate | h=1 | h=2 | h=3 | h=4 |
|---|---|---:|---:|---:|---:|
| q | rel | 0.007 | 0.5 | 0.009 | 0.002 |
| q | vola | 0.291 | 2 | 0.297 | 0.006 |
| q | volz | -0.107 | 2 | -0.093 | 0.013 |
| q | rs | 0.147 | 4 | 0.164 | 0.017 |
| q | mom121 | 0.241 | 4 | 0.266 | 0.025 |
| q | hi52 | 0.161 | 2 | 0.165 | 0.004 |
| q | om | -0.311 | 0.5 | -0.305 | 0.005 |
| q | revg | 0.201 | 0.25 | 0.204 | 0.003 |
| m | rel | -0.004 | 1 | 0.003 | 0.007 |
| m | volz | 0.213 | 2 | 0.224 | 0.010 |
| m | rs | -0.584 | 8 | -0.425 | 0.159 |
| m | mom121 | -3.420 | 8 | -3.071 | 0.349 |
| m | hi52 | 0.068 | 4 | 0.078 | 0.009 |

Chaos gives high short-range skill that collapses quickly; noise gives none at any range. Here the price coordinate
has ~0.02–0.07 at every horizon, and slow coordinates decay smoothly (volatility 0.57 → 0.44 over four quarters): persistence.

## 6. Local divergence (the "Lyapunov" diagnostic)

| local divergence (quintile) | mean |error| in spreads | analogue spread |
|---|---:|---:|
| -2.49 … -0.29 | 1.58 | 1.67 |
| -0.29 … -0.08 | 1.17 | 1.34 |
| -0.08 … 0.07 | 1.10 | 1.25 |
| 0.07 … 0.23 | 1.03 | 1.20 |
| 0.23 … 1.30 | 0.94 | 1.20 |

Higher divergence comes with *smaller* errors: low values mean the analogues started far away (an extreme, sparsely
visited state) and were pulled back together toward the centre. The finite-time stretching rate does not flag
unpredictable regions; the analogues' spread does, and it is what the cones show. The site still reports the value
per dot as a diagnostic, never as a Lyapunov exponent.

## 7. Weekly RRG (250 companies, 772 weeks, 2012-01-06 – 2026-10-16, 14-week window)

| Model | step skill vs standing still | arrow right | mean cosine |
|---|---:|---:|---:|
| Analogues | 22.8% | 76.1% | 0.488 |
| Linear map | 23.5% | 76.7% | 0.497 |
| Keep rotating at the same speed | -712.2% | 66.4% | 0.313 |

Price read back from the forecast point: IC 0.005 [-0.001, 0.011]; sign right 50.0% (forecasts exactly on the grid's zero, 10.1%, left out);
the analogues' own next returns: IC 0.005 [0.000, 0.011]. A 1% relative move shifts next week's point by only 0.19 RRG units
(median) — the point is mostly fixed by the past through the averaging, so where it goes is easy and the price behind it is
barely identified. Continuing the rotation at constant speed points roughly right but overshoots badly.

## 8. Price ranges

| | forecasts | direction right | moves that were up | 80% range held (95% CI over periods) | 95% range held |
|---|---:|---:|---:|---:|---:|
| Quarterly | 9,907 | 61.0% | 61.3% | 83.1% (78.5%–86.9%) | 95.7% (92.5%–97.9%) |
| Monthly | 38,267 | 57.0% | 57.1% | 81.4% (79.3%–83.3%) | 95.9% (94.8%–96.8%) |

Direction equals the base rate of up moves: no timing skill. The ranges are honest — they hold close to their nominal
rates once built in log price with the stock's own scale (in return space with the analogues' spread they held only 69–75%).

## Limits

- Today's companies, backfilled: survivorship flatters every model equally but makes the universe unrepresentative.
- 46 test quarters is short for quarterly statistics; the monthly test (164 months) is the more reliable one.
- Fundamentals are the SEC frames as published now; restatements are not point-in-time.
- Interval scale uses the stock's own trailing moves; regime breaks (2020, 2022) still widen misses within a period.

## Ideas that would be worth testing next

- Rank-based target (cross-sectional rank of next rel) with the linear phase-space map, where the only non-zero hint was.
- Calibrated linear map alongside calibrated analogues (only the raw linear map was scored here).
- RRG on monthly frequency, where the smoothing window covers a meaningful horizon for prices.
- Re-run every quarter: the scorecard on the page updates with each build, so drift in skill is visible.
