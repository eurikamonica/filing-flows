# Company shock panel

Route: `#c-<CIK>-shock`; company → Relationships & model → Shock panel.
The existing revenue elasticity calculator is preserved. This is a separate descriptive multi-output laboratory, not a causal model or a price target.

## Inputs and outputs

| Input | User unit | Fitted factor |
|---|---|---|
| 10Y Treasury | basis points | 13-week DGS10 change in percentage points; user bp / 100 |
| Broad US dollar | percent appreciation | 13-week percentage change of DTWEXBGS |
| Employment | unemployment percentage points | 13-week UNRATE change; positive means weaker employment |
| Peer results | revenue growth percentage points | median of up to five selected same-SIC peers' latest quarterly revenue YoY growth |

Outcomes are revenue YoY growth, operating/net/operating-cash/free-cash margins, quarterly stock total return, and split-adjusted stock price return excluding dividends. Cash metrics with too little historical data are unavailable, not imputed. Total returns use adjusted series including dividends; the separate price-return outcome requires `p` (split-adjusted closes excluding dividends). It never substitutes total returns when price data are unavailable. Each output has its own coefficient set; do not add operating and stock contributions.

## Data and timing

Reuses the production company's `data/c/<CIK>.json`, ten years of `quality.hist`, recent `quality.q.health`, site company index, and existing `disclosures/data/market/history/macro.json` plus `t/<TICKER>.json` and `t/SPY.json`. No new API keys, artificial data or assumptions masquerading as fitted coefficients. Source failures remain visible. The build script copies top-level web assets; scan push triggers include both new assets.

Historical figures use latest recorded versions; Q4 can be derived as FY less three consecutive quarters. Peer membership defaults to at most five largest current same-SIC companies by available revenue; the user can select up to five from the top 30. The target company is excluded. Peer observations end on/before the factor date and cannot be older than 120 days. Basket membership can vary by date; this is not a survivor-bias-free historical industry index. Fiscal quarter timing differs across peers.

Macro uses the existing history's approximate publication delays and current revised vintages. Peer alignment is by period end, not filing availability. Displayed correlations and chronological holdout are retrospective, not point-in-time trading backtests. The data do not isolate announcement surprises or identify causal effects. Source observation dates and snapshot dates are both shown.

## Estimator and scenarios

OLS with intercept and selected factors. Stock model additionally controls for same-quarter SPY total return, held fixed in scenarios. Factors can be contemporaneous, 13 weeks earlier, or 26 weeks earlier. Outcomes use fiscal quarters for operations and non-overlapping calendar quarters for returns. Macro changes use 13-week windows; calendar/fiscal quarter lengths can differ slightly.

Minimum sample: max(24 quarters, 5 × number of parameters). Complete-case rows only. Fit standardizes X, rejects constant or collinear factors, and rejects an infinity-norm condition number above 100,000. Newey-West/Bartlett covariance uses four quarterly lags and finite-sample n/(n-p) correction. Intervals use 1.96 normal approximation and are not exact finite-sample coverage guarantees. All coefficients are in outcome percentage points per factor unit.

`Delta outcome = sum(beta_j * input_j)` with rate inputs converted from bp to pp. The scenario interval uses the full coefficient covariance, not a sum of individual interval widths. It includes only coefficient uncertainty; it is not a future-return interval. Nonzero shocks with unavailable/omitted coefficients cannot be evaluated. Manual mode requires explicit entries; blank is unknown, explicit zero is zero. Changing outcomes clears manual coefficients.

The historical baseline is the latest available actual quarter, not a forecast. Revenue scenario level = reference revenue + year-ago revenue × Delta YoY growth / 100. Margin scenario amount change = reference revenue × Delta margin / 100, holding revenue fixed. Negative revenue scenarios are marked not meaningful. No unobserved forecast prices or debt exposures are inserted.

If enough data exist, the first 75% of complete observations train a diagnostic model evaluated on the final 25%; compare RMSE with a training-mean baseline. Minimum training rules still apply. This does not cure vintage, endogeneity, omitted-variable or peer-selection bias.

## UI and audit

Four shock inputs, illustrative combined presets, factor selection, peer selector, lag selector, explicit assumption mode, signed contribution bars, fitted/observed plot, coefficient table, sample size/date range, R², RMSE, chronological holdout, JSON scenario export and complete fitted-sample CSV export. The page uses the existing website theme and responsive mobile layout. Scenario JSON contains source paths, input units, peers, coefficients, sample dates and limitations.

## Validation

`node --test tests/test_shock_panel.cjs` covers coefficient recovery, covariance scenario intervals, bp conversion, missing/collinear inputs, financial loss handling, safe Q4 derivation, temporal alignment, nonoverlapping return samples and CSV escaping.

`node tests/test_shock_panel_browser.cjs` (Playwright) covers desktop/mobile mount, peer exclusion, source-text escaping, unknown vs explicit manual coefficients, outcome reset, export, fitted model rendering and failed macro requests. Dedicated GitHub Actions workflow runs both suites.

Sources: https://fred.stlouisfed.org/series/DGS10 ; https://fred.stlouisfed.org/series/DTWEXBGS ; https://fred.stlouisfed.org/series/UNRATE ; SEC filing versions linked by the existing company revisions and quality pages. OLS/HAC methodological reference: https://www.statsmodels.org/stable/regression.html .
