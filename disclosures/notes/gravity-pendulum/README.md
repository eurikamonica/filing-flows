# Gravity field + serial pendulum — does the hypothesis predict?

Code: `disclosures/app/gravity_pendulum.py`. Data: branch `rotation-history` (2026-10-17): weekly adjusted closes of the site's
companies with ≥ 200 weeks on file (3,239), SPY and asset ETFs; 10-Q figures for the 246 core companies. At each origin only
companies with a close ≥ $3, ≥ $10M weekly dollar volume and three years of history (≈1,230 per period). Today's companies,
backfilled: survivorship flatters every model alike. Walk-forward test from 2012; Fama-MacBeth on the full sample.

## The model

- **Satellite** = company, **planet** = its sector (log-revenue weighted, the company itself left out), **star** = SPY,
  **other bodies** = TLT (rates), USO (oil), GLD (gold), EEM (emerging markets), IWM (small caps). FRED macro series are not
  reachable from the experiment machine; the bodies stand in for the economic layer.
- **Position** = cumulative log price relative to the parent (not the period return, which is a velocity).
- **Serial pendulum** = links between successive exponential averages of position: link 1 = x − E4 (T−n market data),
  link 2 = E4 − E13, link 3 = E13 − E52 (10-Q horizon), link 4 = E52 − E156 (economic cycle). A negative coefficient on the
  next period's velocity is a restoring force (gravity, k > 0); positive pushes away (momentum).
- Layers, nested: M0 damping (last velocity) → M1 + the four links → M2 + the planet's velocity and links (tidal coupling)
  → M3 + other bodies × the satellite's own 104-week exposure → M4 + 10-Q anchor (core) → M5 M3 with every term allowed to
  differ in high-volatility weeks (state dependence).

## 1. Out of sample (2012 – 2026)

Rank IC per period with 95% block-bootstrap interval; top-minus-bottom decile return per period (gross).

| Timescale | Model | IC | Decile spread / period | Sharpe (gross, ann.) | OOS R² |
|---|---|---:|---:|---:|---:|
| Week | M0 damping | +0.014 [+0.006, +0.023] | +0.13% [-0.03, +0.34] | 0.40 | +0.0000 |
| Week | M1 gravity (pendulum links) | +0.018 [+0.010, +0.027] | +0.22% [+0.07, +0.40] | 0.70 | +0.0002 |
| Week | M2 + tidal (planet) | +0.023 [+0.017, +0.031] | +0.28% [+0.15, +0.43] | 0.98 | +0.0003 |
| Week | M3 + other bodies | +0.021 [+0.013, +0.030] | +0.28% [+0.13, +0.43] | 0.94 | +0.0003 |
| Week | M5 M3 x volatility state | +0.023 [+0.016, +0.032] | +0.37% [+0.22, +0.54] | 1.15 | +0.0003 |
| Week | core 246 · M3 + other bodies | +0.024 [+0.015, +0.034] | +0.17% [+0.03, +0.31] | 0.57 | -0.0002 |
| Week | core 246 · M4 + 10-Q anchor | +0.024 [+0.015, +0.034] | +0.17% [+0.04, +0.31] | 0.59 | -0.0003 |
| Month (4 weeks) | M0 damping | +0.005 [-0.007, +0.020] | -0.03% [-0.55, +0.53] | -0.02 | -0.0002 |
| Month (4 weeks) | M1 gravity (pendulum links) | +0.014 [-0.001, +0.031] | +0.21% [-0.49, +0.88] | 0.17 | +0.0004 |
| Month (4 weeks) | M2 + tidal (planet) | +0.026 [+0.014, +0.039] | +0.54% [-0.02, +1.07] | 0.50 | +0.0006 |
| Month (4 weeks) | M3 + other bodies | +0.024 [+0.007, +0.044] | +0.42% [-0.30, +1.13] | 0.30 | -0.0003 |
| Month (4 weeks) | M5 M3 x volatility state | +0.019 [+0.005, +0.037] | +0.34% [-0.23, +0.97] | 0.27 | -0.0008 |
| Month (4 weeks) | core 246 · M3 + other bodies | +0.028 [+0.004, +0.053] | +0.64% [+0.03, +1.29] | 0.50 | -0.0002 |
| Month (4 weeks) | core 246 · M4 + 10-Q anchor | +0.028 [+0.005, +0.051] | +0.56% [-0.06, +1.20] | 0.45 | -0.0006 |
| Quarter (13 weeks) | M0 damping | -0.013 [-0.050, +0.013] | -0.58% [-3.17, +1.72] | -0.14 | -0.0002 |
| Quarter (13 weeks) | M1 gravity (pendulum links) | +0.015 [-0.006, +0.043] | +0.44% [-1.12, +2.57] | 0.11 | +0.0006 |
| Quarter (13 weeks) | M2 + tidal (planet) | +0.029 [+0.013, +0.050] | +1.14% [-0.18, +2.68] | 0.35 | +0.0008 |
| Quarter (13 weeks) | M3 + other bodies | +0.024 [-0.004, +0.058] | +1.69% [-0.57, +4.19] | 0.41 | +0.0013 |
| Quarter (13 weeks) | M5 M3 x volatility state | +0.043 [+0.009, +0.079] | +3.29% [+0.85, +5.80] | 0.72 | +0.0038 |
| Quarter (13 weeks) | core 246 · M3 + other bodies | +0.024 [-0.012, +0.076] | +1.45% [-0.48, +4.18] | 0.36 | -0.0031 |
| Quarter (13 weeks) | core 246 · M4 + 10-Q anchor | +0.023 [-0.012, +0.071] | +1.34% [-0.37, +3.73] | 0.36 | -0.0047 |

## 2. Which forces (Fama-MacBeth, standardised coefficients ×10⁴, Newey-West t)

| Term | Week | Month | Quarter | Reading |
|---|---:|---:|---:|---|
| v | -1.9 (t -1.1) | -3.9 (t -0.6) | +16.7 (t +0.6) | last velocity (damping / short-term reversal) |
| k1 | -4.3 (t -1.8) | -11.3 (t -1.6) | -40.9 (t -2.2) | short pendulum x − E4 |
| k2 | -0.5 (t -0.3) | +3.0 (t +0.4) | +14.9 (t +0.5) | E4 − E13 |
| k3 | -0.8 (t -0.4) | -0.9 (t -0.1) | -18.0 (t -0.5) | E13 − E52 |
| k4 | +4.4 (t +2.4) | +14.6 (t +1.8) | +38.4 (t +1.3) | long pendulum E52 − E156 |
| planet_v | -0.4 (t -0.2) | -0.2 (t -0.0) | -15.0 (t -0.5) | planet's last velocity |
| pk1 | +0.5 (t +0.2) | -6.9 (t -0.8) | -0.3 (t -0.0) | planet x − E4 |
| pk2 | -3.1 (t -1.3) | -2.4 (t -0.3) | -30.6 (t -0.7) | planet E4 − E13 |
| pk3 | -0.8 (t -0.4) | -6.3 (t -0.8) | +52.0 (t +1.3) | planet E13 − E52 |
| pk4 | -1.5 (t -1.0) | -2.6 (t -0.4) | -48.0 (t -1.7) | planet E52 − E156 |
| b_TLT | -3.3 (t -1.4) | -10.9 (t -1.4) | -19.1 (t -0.8) | other body × exposure |
| b_USO | -0.2 (t -0.2) | -3.0 (t -0.6) | -13.8 (t -0.8) | other body × exposure |
| b_GLD | -1.1 (t -0.6) | +8.8 (t +1.2) | -21.0 (t -0.7) | other body × exposure |
| b_EEM | +0.5 (t +0.4) | +8.6 (t +1.9) | +20.0 (t +1.1) | other body × exposure |
| b_IWM | -2.7 (t -1.5) | -2.3 (t -0.3) | -6.3 (t -0.3) | other body × exposure |

10-Q anchor terms (core 246, with everything above):

| Term | Week | Month | Quarter |
|---|---:|---:|---:|
| f_om | +0.4 (t +0.4) | +1.0 (t +0.3) | +15.1 (t +1.3) |
| f_revg | +1.1 (t +1.4) | +1.9 (t +0.6) | -5.8 (t -1.0) |
| f_dom | +0.4 (t +0.5) | +2.6 (t +0.9) | -19.1 (t -1.9) |

## 3. Robustness: both halves of the test, and costs

Net = gross decile spread minus 10 bp per side on both legs at the measured turnover.

| Timescale · period · model | IC | gross spread | net of 10 bp | one-way turnover |
|---|---:|---:|---:|---:|
| week · 2012-2018 · M1 gravity | +0.017 [+0.006, +0.026] | +0.14% [-0.02, +0.27] | -0.19% [-0.35, -0.06] | 0.81 |
| week · 2012-2018 · M2 + tidal | +0.021 [+0.013, +0.029] | +0.20% [+0.07, +0.33] | -0.09% [-0.22, +0.04] | 0.72 |
| week · 2019-2026 · M1 gravity | +0.020 [+0.008, +0.034] | +0.29% [+0.05, +0.62] | +0.01% [-0.24, +0.33] | 0.71 |
| week · 2019-2026 · M2 + tidal | +0.025 [+0.015, +0.038] | +0.34% [+0.13, +0.62] | +0.08% [-0.13, +0.36] | 0.65 |
| month · 2012-2018 · M1 gravity | +0.005 [-0.015, +0.023] | -0.11% [-0.74, +0.47] | -0.41% [-1.04, +0.17] | 0.75 |
| month · 2012-2018 · M2 + tidal | +0.019 [+0.003, +0.035] | +0.31% [-0.17, +0.80] | +0.05% [-0.43, +0.53] | 0.66 |
| month · 2019-2026 · M1 gravity | +0.023 [-0.004, +0.043] | +0.50% [-0.77, +1.55] | +0.25% [-1.02, +1.30] | 0.61 |
| month · 2019-2026 · M2 + tidal | +0.033 [+0.012, +0.049] | +0.75% [-0.23, +1.59] | +0.50% [-0.47, +1.34] | 0.61 |
| quarter · 2012-2018 · M1 gravity | +0.002 [-0.033, +0.032] | -0.57% [-2.06, +0.67] | -0.80% [-2.29, +0.44] | 0.57 |
| quarter · 2012-2018 · M2 + tidal | +0.015 [-0.008, +0.043] | +0.70% [-0.82, +1.84] | +0.49% [-1.03, +1.64] | 0.52 |
| quarter · 2019-2026 · M1 gravity | +0.026 [-0.003, +0.067] | +1.37% [-1.14, +4.66] | +1.10% [-1.42, +4.39] | 0.69 |
| quarter · 2019-2026 · M2 + tidal | +0.043 [+0.023, +0.070] | +1.56% [-0.53, +4.21] | +1.31% [-0.78, +3.96] | 0.63 |

## 4. Planets and the star

| Timescale | Planets (sectors vs SPY): IC | top − bottom sector spread | Star (SPY): OOS R² vs past mean | direction right | share of up periods |
|---|---:|---:|---:|---:|---:|
| Week | +0.035 [+0.008, +0.064] | +0.20% [+0.04, +0.37] | -0.012 | 52.3% | 59.3% |
| Month (4 weeks) | +0.056 [+0.008, +0.109] | +0.73% [+0.12, +1.38] | -0.250 | 58.3% | 67.2% |
| Quarter (13 weeks) | +0.055 [-0.004, +0.128] | +2.37% [+0.73, +4.38] | -0.301 | 65.7% | 77.1% |

## 5. Physics of the fitted equations

The fitted M1 equation, written as a linear dynamical system in (position − its 156-week average, the other averages, velocity).
Half-life of the slowest mode = ln ½ / ln |λ_max| periods.

| Timescale | Layer | eigenvalues | oscillation? | slowest half-life | Lyapunov exponent (per year) |
|---|---|---|---|---:|---:|
| Week | satellites | 0.991, 0.958, 0.854, 0.602, -0.013 | no (all real) | 79 weeks | -0.45 |
| Week | planets | 0.986, 0.971, 0.839, 0.620, -0.008 | no (all real) | 49 weeks | -0.74 |
| Month (4 weeks) | satellites | 0.963, 0.844, 0.541, 0.129, -0.009 | no (all real) | 73 weeks | -0.49 |
| Month (4 weeks) | planets | 0.948, 0.880, 0.513, 0.138, -0.018 | no (all real) | 52 weeks | -0.70 |
| Quarter (13 weeks) | satellites | 0.876, 0.564, 0.161, -0.015, 0.001 | no (all real) | 68 weeks | -0.53 |
| Quarter (13 weeks) | planets | 0.854, 0.591, 0.178, -0.050, 0.001 | no (all real) | 57 weeks | -0.63 |

## Conclusions

1. **Gravity exists, but only on the short pendulum.** The shortest link (price vs its 4-week average) is restoring at every
   timescale; the longest link (52- vs 156-week average) pushes away — 1–3-year momentum, anti-gravity. Middle links ≈ 0.
2. **Tidal coupling is the layer that adds.** Satellites follow their planet: adding the sector's motion lifts IC at every
   timescale (week 0.018 → 0.023, month 0.014 → 0.026, quarter 0.015 → 0.030), positive in both halves of the test.
   Sectors themselves show momentum against the market (planet IC ≈ 0.04–0.06).
3. **Other bodies and the 10-Q anchor add nothing** at these horizons (all |t| < 2; IC unchanged or lower).
4. **The star is not predictable** from its own pendulum or the other bodies (negative OOS R²).
5. **Not chaos.** Every fitted system is stable and overdamped: real eigenvalues below 1, no orbital oscillation, negative
   Lyapunov exponents (≈ −0.5 per year for satellites, ≈ −0.7 for planets). The slowest mode decays with a half-life of
   about 68–79 weeks for satellites and 49–57 weeks for planets, nearly the same at all three timescales — a consistent clock. Letting coefficients change in volatile weeks (M5) helps
   only at the quarterly horizon and only once in many trials: a hint of state dependence, not established.
6. **Real but small, and not tradeable in this form.** IC ≈ 0.02–0.03 over ≈ 1,230 companies is statistically solid, but a
   weekly or monthly decile long-short turns over 60–80% per rebalance; after 10 bp per side the net spread's interval
   includes zero in every period tested.

Compared with the first experiment (250 companies, period returns as positions: IC ≈ 0), the two changes that mattered were
position = cumulative relative price, and breadth (≈ 1,230 companies per period).

## 6. Lower turnover: can the signal survive costs? (`gravity_portfolio.py`, `portfolio.json`)

Sector-neutral long-short on the weekly M2 signal (about 1,230 liquid companies). 48 rules = score smoothing (span 1/4/13/26
weeks) × exit buffer (leave the leg below the top / bottom 90/80/70/50%) × rebalancing (every 1/4/13 weeks), 10 bp per side.
The rule was chosen on 2012–2018 only (best net Sharpe) and 2019–2026 is reported once.

| Rule | Period | Net return / year (95% CI) | Net Sharpe | Turnover / year |
|---|---|---:|---:|---:|
| No reduction (weekly, top/bottom 10%) | 2012–2018 | -4.4% | -0.49 | 75× |
| No reduction | 2019–2026 | +4.2% | 0.23 | 67× |
| **Chosen: rebalance every 4 weeks, enter top/bottom 10%, leave below top/bottom 50%** | 2012–2018 (selection) | +3.2% [-1.3, +8.3] | 0.52 | 8.5× |
| Chosen | **2019–2026 (untouched)** | **+9.4% [+2.7, +17.7]** | 0.77 | 7.1× |

Chosen rule on 2019–2026 at other costs: 5bp +10.1% [+3.4, +18.5], 10bp +9.4% [+2.7, +17.7], 20bp +8.0% [+1.2, +16.3], 30bp +6.5% [-0.3, +14.8].

Net by calendar year (10 bp): 2012 +6.1%, 2013 -3.8%, 2014 +2.6%, 2015 +1.6%, 2016 +4.1%, 2017 +9.4%, 2018 +2.2%, 2019 +6.8%, 2020 +13.8%, 2021 -9.4%, 2022 +9.0%, 2023 +17.9%, 2024 +12.6%, 2025 +21.6%, 2026 +1.0%.
All 48 rules are positive on 2019–2026 and 46 on 2012–2018, so the result is not one lucky rule;
but 2012–2018 alone is not significant, and the universe is today's companies only — buying recent losers against their
sector (the restoring short pendulum) is exactly what survivorship flatters most. Treat this as promising, not proven.

## 7. On the site (Rotation → Next step)

The price coordinate (stock vs the S&P) and the price now come from this model where it covers the company (liquid, three
years of history); the other coordinates keep the analogues. On the RRG the model forecasts next week's price and the step is
computed from it with the chart's exact formula. Scores on the site's own calendars and companies:

| Chart | Gravity + tidal: price IC (95% CI) | Analogues: price IC | 80% range held |
|---|---:|---:|---:|
| Quarterly (10,010 forecasts) | +0.035 [-0.007, +0.075] | +0.005 [-0.026, +0.037] | 80.5% |
| Monthly (37,252 forecasts) | +0.011 [-0.013, +0.033] | +0.001 [-0.017, +0.020] | 81.0% |
| RRG weekly (386 weeks) | +0.012 [-0.002, +0.024] | +0.005 [-0.001, +0.011] (read back) | step right 77.3% vs analogues 76.1% |

Better than the analogues everywhere, but on the site's ~220 large companies the interval still includes zero: the effect
(IC ≈ 0.01–0.035) needs the breadth of the broad test to be detected.
