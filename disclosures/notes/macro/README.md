# Macro data and the long pendulum (October 2026)

`app/macro_history.py` collects 26 FRED series (rates, curve, credit spread, VIX, financial conditions, dollar, oil,
Fed balance sheet, claims, payrolls, unemployment, industrial production, retail sales, housing starts, sentiment,
CPI / core CPI / core PCE, M2) from 1990 and publishes `macro.json`, built every run of the Rotation history workflow.

**As published.** Every observation is placed at the day it became public: period end plus the usual release lag
(daily market series: next day; claims and NFCI: 5 days after the week; CPI: 15 days after the month; payrolls and
unemployment: 8; industrial production and retail sales: 17; housing starts: 19; M2: 26; core PCE: 30). A chart or a
model reading a week sees only what was public that week. Caveat: FRED serves the latest vintage, so revised series
(payrolls, production, retail sales, PCE) carry later revisions.

## Macro clock

Growth composite = z-scores (each standardised with data up to that month only) of payrolls y/y, industrial production
y/y, retail sales y/y, housing starts y/y, consumer sentiment, minus claims y/y, minus unemployment vs its 12-month low.
Inflation composite = CPI y/y, core CPI y/y, core PCE y/y, 10-year breakeven. The clock plots the 6-month change of each
(momentum); quadrants = the investment clock's phases.

Next-month forecast: ridge on the four coordinates and the last change, refitted every month on outcomes already known;
the 80% box from the 6.5th–93.5th percentiles of past errors on each axis (≈ 80% jointly).

| Walk-forward since 2005, 260 months | |
|---|---|
| Mean distance forecast → actual | 0.43 |
| "Stays where it is" | 0.46 |
| Step direction right | 66% |
| Inside the 80% box | 82% |

A small improvement over standing still; the clock moves slowly and mostly randomly month to month.

## Does macro improve the sector (planet) forecasts?

`gravity_pendulum.macro_planet_test`: the planet layer (sector vs SPY from its own pendulum) with and without a
"macro tide" — each sector's past-only 156-week beta to weekly changes in the 10-year yield, the curve, the credit
spread, VIX, the dollar and oil, times the factor's change over the last h weeks. Same weeks, same ridge, 2012–2026.

| Horizon | IC without | IC with macro tide | Difference (95% CI) |
|---|---|---|---|
| 1 week | 0.035 | 0.036 | +0.001 [−0.013, +0.015] |
| 4 weeks | 0.056 | 0.049 | −0.008 [−0.039, +0.023] |
| 13 weeks | 0.055 | 0.055 | +0.001 [−0.064, +0.050] |

No gain, so the site's price forecasts do not use it (planet_tide.json).

Phase-conditional sector ranking (`phase_sectors.json`): each month, rank the 9 long-history sector ETFs by their average
next-month return vs SPY in past months of the same phase. Monthly walk-forward from 2013: IC 0.055 [−0.007, 0.111];
best-ranked sector beat the average by 0.17% a month [−0.36%, +0.70%]. A tendency, not distinguishable from zero —
which is why the page's table says "read as tendencies, not rules".
