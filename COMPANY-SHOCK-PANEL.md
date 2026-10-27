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

## Expanded inputs, outputs and estimators (v2)

The panel now offers **16 shock inputs and 20 response variables**. The original four shocks remain visible; twelve additional inputs expand on demand. Additional factors are opt-in for fitting so missing new data do not invalidate the existing four-factor model. SPY is always an explicit contemporaneous control for stock outcomes and can now be shocked. In operating models it is included only if selected and follows the chosen factor lag.

| Added factor | History feature / transformation | Shock unit |
|---|---|---|
| 2Y Treasury | y2, 13-week change | bp (divide by 100) |
| 10Y real yield | real10, 13-week change | bp |
| 10Y–2Y curve | curve2, 13-week change | bp |
| Baa credit spread | credit, 13-week change | bp |
| CPI YoY inflation | cpi, 13-week change in YoY rate | pp |
| WTI | oil, 13-week percent change | % |
| VIX | vix, 13-week point change | index points |
| Payroll / retail / industrial production | payrolls / retail / ip, YoY growth levels | pp |
| Peer operating margin | selected-peer median quarterly margin | pp |
| SPY | quarterly adjusted total return | % |

Outputs additionally include gross margin, revenue QoQ growth (not seasonally adjusted), YoY changes in operating profit/net income/OCF divided by prior-year revenue, CapEx/R&D/SBC intensity, accruals/average assets, quarterly ROA, current ratio, DSO and CCC. Normalizing profit changes by positive prior-year revenue preserves interpretable results when profits are negative or cross zero. Days remain days, current ratios remain multiples, and percent-based outputs have percentage-point shocks. Latest health/working-capital data can provide only eight quarters for some outputs; fitted estimates remain unavailable until minimum history exists. Explicit manual assumptions can still be tested. No new fundamentals are fabricated or backfilled from today's ratios.

### Models

- **OLS + HAC**: existing joint regression and Newey–West intervals.
- **Ridge**: SSE + alpha × sum of squared standardized slopes. Intercept is unpenalized. Default alpha 10; the user can set a positive value up to 10,000. Training means/scales are estimated solely from training rows. Collinear factors are regularized; constant factors still fail. No Ridge coefficient interval is supplied.
- **Huber IRLS**: weighted least squares with weights min(1, 1.35 × robust scale / absolute residual), scale = 1.4826 × MAD of residuals, maximum 100 iterations. This is an IRLS implementation, not scikit-learn's joint scale/L2 solver. Singular, degenerate-scale and nonconvergent fits are withheld. No unimplemented robust coefficient interval is shown.
- **ARX(1) + HAC**: adds the previous observed response only when dates are 75–110 days apart. The conditional response to a one-quarter pulse is delta, phi×delta, phi²×delta, phi³×delta. Paths are withheld when |phi| >= 1. These are point sensitivities, not a causal impulse response or a cumulative cash-flow forecast; no path confidence bands are implemented.

Minimum complete-case sample remains max(24, 5 × parameter count), including the AR lag and market controls. Selecting many factors may therefore make a fit unavailable. Sample windows include all observations or the latest 32/40/60 observed quarters. Timing includes 0/1/2/4 quarters (13-week increments). Yield-curve inputs overlap with 2Y/10Y yields, so a compact specification is preferable; OLS rejects singular designs while Ridge does not imply that individual causal effects have been identified.

The model-comparison table restricts every estimator to the **same complete consecutive-quarter rows and same 75%/25% chronological split**. It reports train/test counts, RMSE, MAE and the training-mean baseline. No model is automatically selected or tuned on the holdout. ARX holdout evaluation is conditional one-step evaluation using the observed preceding outcome. A selected model's individual fit may use more eligible observations than the common comparison sample; these are separate diagnostics. Current revised macro/fundamental vintages and period-end peer alignment still prevent claims of point-in-time predictive performance.

### Independent valuation assumptions

A separate, explicitly user-entered calculator provides:

- EPS × P/E: reference price = annual EPS × multiple; scenario price multiplies both (1 + EPS change) and (1 + multiple change), including their cross term. Requires positive EPS and P/E.
- One-stage FCFF perpetuity: EV = **next-year** FCFF / (WACC − g). Rate inputs are percentages; changes are basis points. Both scenarios require positive cash flow, positive WACC and WACC > g. This is enterprise value, before net debt and other claims, not equity value or a complete multi-stage DCF.

The lab does not infer EPS, duration, debt, WACC, or peer valuation multiples, and does not add its assumptions to the statistical stock effect. JSON exports include model, regularization setting, history window, output units, comparison diagnostics and valuation assumptions/results. Missing inputs remain unknown; a blank shock no longer silently coerces to zero.

Validation adds Ridge collinearity/shrinkage, Huber outlier resistance, AR lag alignment and stable pulse paths, identical comparison samples, macro transformation units, loss-safe operating changes, working-capital units and valuation denominator guards. Browser tests exercise all four models, expanded controls, days-based scenarios, blank-input errors and the valuation lab.


## Faster history, usable defaults and validation recommendations (v3)

The shock panel now loads a compact supplemental history from the independent
`shock-history` branch (`public/c/<CIK>.json`, `public/status.json`), falling back
to the Pages copy in `data/shock-history/`. The collector runs every 10 minutes,
up to 900 companies / eight minutes per batch; scheduling can be delayed. It
reads one SEC companyfacts response per company and retains available quarters
since 2009. It prioritizes large followed companies and their industry peers,
then traverses the whole company index. New filings re-enter the queue; facts
otherwise refresh weekly. Failed issuers back off six hours; successful files
and the incremental ledger survive partial failures. A missing SEC contact
configuration fails explicitly, using the existing repository setting.

Supplemental cells fill gaps only, with issuer/currency checks and filing
references. Existing recent company values take precedence. Cash flow, CapEx,
R&D and SBC use quarterly durations or same-start YTD differences, including
FY minus nine months. Assets and current balances are historical period-end
facts. Gross profit can be revenue minus disclosed cost of revenue. DSO needs
opening/closing receivables; supplemental CCC requires disclosed inventory and
payables, never inferred zero inventory or accrued-liability substitutes.
Foreign-currency histories are not blended into USD. Genuine short listing
history, absent tags, and missing macro/price history remain unavailable.

**Use reliable defaults** selects a compact factor set by complete-case coverage
and usable variation, preferring more factors within 90% of the maximum sample
among the predeclared candidates. It does not rank specifications by R² or test
performance. Same-quarter timing, all history, OLS and an explicitly labelled
illustrative rate shock are the default. The selected output is preserved;
output choices show observed-quarter counts. Thresholds are unchanged.

**Recommend model** fixes the selected output/factors/timing/window and compares
OLS, Ridge (alpha 1/10/100), Huber, and ARX using two expanding four-quarter
validation blocks. The final max(6, ceil(20% × common observations)) quarters
are excluded from selection. All candidates share eligible dates; candidates
failing either training fit are unavailable. The lowest validation RMSE is
applied only if it beats a training-mean baseline. The final test is then
reported separately. Insufficient history produces no recommendation. This
is conditional retrospective association, not a claim of a universally optimal
model; revised vintages and one-step observed AR lags remain disclosed. After
selection, scenario coefficients use the full selected historical sample.

The UI shows source/complete sample counts, collector progress, per-factor
coverage bars, a missing-quarter timeline, actual/fitted time series and final
test predictions. Missing fit/holdout history is explained once rather than
repeated across overflowing table rows. Actual observations remain visible even
during macro outages. Peer requests are cached within the page, datasets are
cached by timing, and refitting computes only the selected output. Refresh
preserves input/model/valuation settings. JSON schema 3 exports coverage,
collector/source snapshots and selection/validation/final-test diagnostics.

Validation: 22 numerical/model checks, seven offline collector tests, and
Playwright desktop/mobile regression including refresh preservation and macro
outages. Primary data documentation:
https://www.sec.gov/search-filings/edgar-application-programming-interfaces
