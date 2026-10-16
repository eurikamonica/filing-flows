# 04 — Macro and academic research implementation

Created by ChatGPT (OpenAI). Proposed modules; no collector or study has been run for this plan.

## M05: Macro vintage dashboard

**MVP universe:** a small reviewed list of output/growth, inflation, unemployment and interest-rate series. Select actual series IDs and inspect their units, frequency, seasonal adjustment and release calendar before implementation. Do not hardcode a label such as growth when the downloaded series is a level.

The FRED API documents real-time periods for historical information sets [S1] and API-key handling [S2]. Obtain a key through the user's account if needed and keep it in the collector environment. A vintage date alone may not establish intraday publication time.

**Proposed macro observation:** series_id, observation_date, value, unit, frequency, seasonal_adjustment, transformation, vintage_start, vintage_end, release_timestamp, timestamp_precision, retrieved_at, source_url, source_terms and raw_response_hash.

**Collector sequence:** fetch allowed series → preserve raw vintage response → normalize missing markers to null → validate units/dates → apply explicit transforms → write a versioned public snapshot → update the release manifest only after validation. On failure retain the previous good snapshot and mark stale; never substitute fictional numbers.

**Transformations:**

- Monthly YoY percentage = 100 × (x[t] / x[t−12] − 1), when mathematically appropriate and denominator positive.
- Quarterly annualized growth = 100 × ((x[t] / x[t−1])^4 − 1), only when that transformation matches the series. Do not annualize a series already expressed as an annualized growth rate.
- Keep level, change, YoY and standardized values separately labeled.
- Any standardization for historical inference must use only data available at that time. Full-sample z-scores must be labeled descriptive, not point-in-time.

**Views:** observed-period chart; release calendar; first/latest-vintage comparison; as-of-date selector; growth/inflation trajectory. Show stale age and transformation beside each series. Regime quadrants are user-defined descriptive classifications, not guaranteed market predictions.

**Acceptance:** a revision after the cutoff cannot appear in an earlier as-of view; missing monthly observations cannot be interpolated invisibly; different frequencies are not joined by simple row position.

## Company-macro exposure extension

Use one documented company metric and a small number of economically motivated macro variables. Align data by availability and fiscal periods, define lags, show sample size and uncertainty. Correlation is not causal pass-through. Compare a simple baseline before adding regressors. Avoid plotting strongly trending levels and treating their correlation as a predictive relationship.

## M06: Event-study studio

**MVP:** one event category and a manually reviewed sample; a single market-model baseline. Require dated total-return data and verified event timestamps. Document prices, dividends, splits, calendars, delistings and data rights before collecting a broad panel. Free coverage and clean historical universes must not be assumed.

**Suggested initial specification, editable:** estimation window trading days −250 to −30; event window −1 to +1, plus an exploratory −5 to +5 view. Freeze the chosen primary specification before comparing results.

```text
R_i,t = alpha_i + beta_i × R_m,t + error_i,t
AR_i,t = R_i,t − (estimated_alpha_i + estimated_beta_i × R_m,t)
CAR_i[a,b] = sum(AR_i,t for trading days a..b)
```

These are simple-return abnormal-return sums, not compounded portfolio wealth. Label a buy-and-hold abnormal-return measure separately if later supported. Define day 0 by exchange calendar and release time; after-close releases normally map to the next trading session under the selected convention. Date-only events require a stated conservative rule or exclusion.

**Execution steps:**

1. Validate event IDs, timestamps, company identifiers and same-company overlapping events.
2. Build trading-day alignment; exclude or explicitly flag insufficient estimation data.
3. Fit alpha/beta on estimation data only.
4. Produce event-level AR/CAR, sample counts and missingness.
5. Aggregate under a stated equal/event weighting scheme.
6. Add uncertainty only with a documented method. Cross-company events on the same date and repeated company events are dependent; naive independent-event intervals can mislead.
7. Export results together with code revision, parameter manifest, exclusions, input hashes and data-use notes.

**Visuals:** individual event paths, average CAR with valid uncertainty bands when implemented, distribution of event CARs, missingness chart and specification comparisons. Do not draw fabricated confidence intervals before an inference method exists.

**Acceptance fixtures:** identical stock/benchmark returns with alpha 0 and beta 1 produce zero AR; a synthetic single-session +2% residual produces +2 percentage points of CAR; after-close and holiday mapping are correct; future observations never enter estimation.

## Later academic modules

- Factor exposures: pin factor definitions and publication timing; display rolling coefficient uncertainty.
- Accrual anomaly: sort only on information published before portfolio formation; include a documented universe, delistings, rebalance lag and costs. Not an immediately deployable trading claim.
- Specification map: show all planned variants, not only favorable results; distinguish primary analysis from exploration.
- Reproducible export: include environment/dependency versions, random seed, parameter file, source IDs and excluded rows. Where data cannot be redistributed, supply retrieval instructions and hashes rather than the raw dataset.

## Sources

Checked October 16, 2026 UTC.

- [S1: FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
- [S2: FRED API keys](https://fred.stlouisfed.org/docs/api/api_key.html)
- [FRED observations parameters](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
