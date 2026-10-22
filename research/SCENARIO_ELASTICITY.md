# Company revenue scenarios & growth elasticities

## Scope and location

A **conditional, deterministic one-quarter revenue scenario** is shown under the existing **Growth model** on individual company pages. It reads the existing static site feeds, notably:

- \`data/model/c/<CIK>.json\`: next-quarter baseline (forecast YoY growth, revenue), the company/SIC-industry growth beta and uncertainty, and the SIC/sector growth beta.
- \`data/model/index.json\`: sector/aggregate-market growth beta and the aggregate market's baseline YoY revenue growth.

No external keys and no new data collectors are needed for this prototype. Neither an SEC filing number nor a stock-price target is invented. If the sector link is unavailable, market-shock controls are disabled and the peer residual scenario can still run. If the company growth model cannot be estimated, the scenario panel is not shown.

## Exact calculation and units

Define baseline company **revenue** growth \`g_i^0\` (fractional YoY) from the existing hierarchical model and changes to YoY growth in **percentage points**:

\`∆g_i_pp = β_i|industry × (β_industry|sector × β_sector|market × M_pp + I_pp) + e_GDP × GDP_pp + e_10Y × (Yield_bp / 100)\`

- \`M_pp\` = change in **aggregate SEC-company revenue-growth YoY**, *not* S&P 500 index return.
- \`I_pp\` = *industry-specific residual* growth shock, **net of** the sector/market effect, not the full peer-group shock again.
- \`GDP_pp\` = surprise in real GDP growth in percentage points.
- \`Yield_bp\` = surprise in the 10-year Treasury yield, in basis points.
- The three beta coefficients are already fitted by \`pipeline/hier.py\`, using quarterly year-on-year SEC filing growth. They can be posterior shrinkage coefficients or priors; they are **not causal treatment effects**.
- The two \`e\` values are manually specified **assumptions**, default **zero**. Do not describe them as historical regressions or empirically supported.
- Scenario \`g_i = g_i^0 + ∆g_i_pp/100\`. Revenue uses the *same prior-year-quarter base* as the existing forecast, so \`Revenue_scenario = Revenue_baseline × (1+g_i)/(1+g_i^0)\`. Output is suppressed when \`g_i <= −100%\`, or when the baseline dollar forecast is unavailable.

**Sensitivity vs elasticity:** The product \`β_i × β_industry × β_sector\` is a **growth transmission slope**, units pp/pp, and should not be mislabeled stock-return beta. If both the company and aggregate market have meaningful baseline growth, the *local level elasticity* of company revenue relative to aggregate revenue is approximately \`β_chain × (1+g_market^0)/(1+g_i^0)\`. It depends on the baseline growth rates and is not a fixed price elasticity.

The presets are **illustrative shocks only**, with no inferred probabilities. The tool does not re-estimate the prior 80% forecast bands, reprice equity, forecast EPS or forecast cash flow. The model forecast errors available on the current site do not validate the macro assumptions.

## Audit and upgrade plan

For a production empirical macro layer:

1. Collect GDP, CPI, Treasury yields, employment and appropriate industry drivers from FRED, preserving release timestamps and **ALFRED vintages** for point-in-time training. Avoid using subsequently revised macro values in historical trading backtests.
2. Join SEC 10-Q/10-K filing dates, actual quarter ends and SIC peer changes by **availability timestamp**. Use the existing site's comparable-quarter methodology, not a look-ahead quarterly join.
3. Estimate incremental macro sensitivity **conditional on** market/sector/industry factors. Use ridge, Bayesian shrinkage or partial pooling; enforce diagnostics on small samples and highly collinear drivers. Compare against current \`pipeline/hier.py\` and a naive growth-unchanged baseline on rolling time splits.
4. Add price sensitivity as a **separate model**: adjusted dividend-aware total returns and market index, sector/peer-residual returns, rates and revisions. Price beta must not be inferred from revenue beta. For loss-making firms, use conditional revenue, cash burn, future financing/dilution and EV/Sales sensitivity rather than unwarranted P/E assumptions.
5. Fit regime-conditional and potentially asymmetric sensitivities only where data support them; publish standard errors/intervals, sample size, fit dates, out-of-sample metrics and whether the beta uses own-company data or peer priors.

## Validation

Run:

\`\`\`sh
node --check web/scenario-elasticity.js
node --check web/model.js
node --test research/test_scenario_elasticity.js
\`\`\`

UI smoke test after the site is rebuilt: navigate to a company with a Growth model, open the scenario section, adjust one shock at a time, verify that contributions add up to the total and that a baseline scenario exactly reproduces the saved baseline.
