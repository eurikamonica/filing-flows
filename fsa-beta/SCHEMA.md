# FSA Beta data and accounting definitions

Created by ChatGPT (OpenAI).

The input is JSON with `schema_version: 1`, `company`, `currency`, `unit`, `demo`, `sources`, and `periods`. `sources` maps an evidence ID to an object containing an excerpt and optional URL/accession. Evidence content is user supplied; reference validation does not verify authenticity.

Periods are oldest first, nonoverlapping, and have `label`, `kind` (`quarter` or `annual`), `start`, `end`, `values`, optional `operating_tax_rate`, and optional `reserves`. Amounts share the document's currency/unit. Fiscal periods of 75–105 inclusive days are accepted as quarters and 350–380 days as years. Transition periods and YTD observations must be normalized separately. Averages require consecutive, same-kind periods.

Each populated financial cell is `{"value": 100, "source_ids": ["filing-1"]}`. Omit unavailable fields or set the entire cell to null. Zero means a verified zero. Nonfinite values and booleans are rejected. Capex uses a positive expenditure magnitude.

| Field | Meaning |
| --- | --- |
| revenue | Total revenue for the period |
| operating_income | Period operating income/loss |
| net_income | Period net income; use the same consolidation scope as OCF |
| ocf | Period operating cash flow, signed |
| capex | Period capital expenditures, nonnegative magnitude |
| assets | Total assets at period end |
| operating_assets / operating_liabilities | Reviewed operating classification at period end |
| financial_assets / financial_liabilities | Reviewed financing classification at period end |
| equity | Equity at period end, matching the scope of the other classifications |

Operating tax rate is an explicit assumption in [0,1]. It produces an **estimate** of NOPAT; it is not a fully tax-allocated reformulated income statement. The engine does not infer the rate from a negative or distorted pretax denominator.

| Metric | Formula and limit |
| --- | --- |
| Accruals | Net income − OCF; a cash-flow-based screening measure |
| Accrual ratio | Accruals / average total assets; requires positive average assets |
| Cash conversion | OCF / net income; only when net income is positive |
| FCF | OCF − capex; not company-reported adjusted FCF |
| NOA | Operating assets − operating liabilities |
| NFO | Financial liabilities − financial assets |
| Estimated NOPAT | Operating income × (1 − assumed operating tax rate) |
| RNOA | Estimated NOPAT / average NOA; requires positive average NOA; period return, not annualized |
| Equity reconciliation | NOA − NFO − equity |
| Asset reconciliation | Operating assets + financial assets − total assets |

A reserve contains `name`, `release_in_income` (boolean), and six financial cells: `opening`, `additions`, `releases`, `utilization`, `other`, `closing`. All movements except `other` use nonnegative magnitudes. `other` is signed (FX, acquisitions, reclassifications, etc.). All six values are required for reconciliation, including an explicitly sourced zero when applicable.

`closing = opening + additions − releases − utilization + other`

Utilization is a use/write-off against the reserve, not automatically a credit to current earnings. A release is labeled a pretax benefit only if the user specifies `release_in_income: true` and the rollforward reconciles. No amount is labeled as a cookie jar solely because a reserve decreased. The current threshold for a reconciliation gap is the larger of 0.01 input units or 0.1% of the relevant closing balance; it is a numerical tolerance, not an audit materiality threshold.

Positive accruals, a release, or a reconciliation gap trigger review text. They do not generate a fraud probability. Unavailable evidence does not imply a clean result. Reserve adequacy needs claims/loss history, business conditions, changes in assumptions, and company-specific note review beyond this calculation.
