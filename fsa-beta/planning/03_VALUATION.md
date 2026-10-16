# 03 — Valuation implementation

Created by ChatGPT (OpenAI). Proposed scenario tools, not investment recommendations or deployed features.

## M04A: Forward DCF

Start with five annual forecast periods and one explicit terminal convention. Keep historical reported data separate from editable forecast assumptions. Required inputs: revenue, EBIT margin, tax assumption, D&A, capex, change in operating working capital, WACC, terminal growth, net debt, other nonoperating claims/assets and diluted shares. Date the price and balance-sheet inputs. Support only one currency per scenario initially.

Use FCFF, not levered cash flow:

```text
Revenue[t] = Revenue[t−1] × (1 + growth[t])
EBIT[t] = Revenue[t] × EBIT_margin[t]
NOPAT[t] = EBIT[t] × (1 − tax_rate[t])
FCFF[t] = NOPAT[t] + DA[t] − Capex[t] − ChangeOperatingWC[t]
TV[N] = FCFF[N+1] / (WACC − g)
EV = sum(FCFF[t] / (1 + WACC)^t) + TV[N] / (1 + WACC)^N
EquityValue = EV − Debt − OtherClaims + NonoperatingCash + OtherNonoperatingAssets
PerShareValue = EquityValue / DilutedShares
```

Define net debt consistently if using a single net-debt input; do not add cash again. State the discounting convention (year-end for MVP). A tax benefit on negative EBIT is not automatic; require an explicit loss/tax mode.

The terminal year must model sustainable reinvestment. If using a terminal ROIC convention, terminal reinvestment rate = g / terminal_ROIC and FCFF[N+1] = NOPAT[N+1] × (1 − g / terminal_ROIC). Validate compatible growth/ROIC assumptions. A simple FCFF[N] × (1+g) alternative must be labeled as a simplifying assumption and cannot hide an implausible final-year reinvestment rate.

**Controls:** reject WACC ≤ g, WACC ≤ −1, nonpositive diluted shares and nonfinite inputs. Flag extreme terminal-value concentration and negative terminal cash flows for review; do not automatically turn them into a confident point estimate.

**Visuals:** forecast revenue/profit/FCFF small multiples; EV-to-equity waterfall; WACC × g sensitivity heatmap; explicit scenario table; share-count sensitivity. Every cell should expose its assumptions.

**Numeric fixtures:** a zero-growth perpetuity starting next year with FCFF 10 and WACC 10% has EV 100; subtract debt 20 and add nonoperating cash 5 gives equity 85; ten shares gives 8.5 per share. Compare an explicit five-year-plus-terminal calculation to the same perpetuity. Test cash double-counting, negative FCFF and invalid terminal spreads.

## M04B: Reverse DCF and expectations map

Solve for **one parameter at a time**, holding all others explicit: constant revenue growth, steady-state EBIT margin, or WACC. Default to growth or margin, with bounded domains selected by the user. Price alone cannot uniquely identify all operating assumptions.

1. Calculate target equity value = as-of price × matching diluted shares.
2. Convert to target EV with the same bridge as the forward model.
3. Define f(x) = modeled EV(x) − target EV.
4. Evaluate the domain and inspect sign changes; use bracketed bisection only within a valid bracket. Do not assume monotonicity for every parameterization.
5. Report no solution in bounds, multiple detected brackets, or nonconvergence explicitly. Never clamp to a boundary and call it the implied assumption.
6. Verify the solution by feeding it back through the forward model; display residual and numeric tolerance.
7. Provide a two-dimensional growth/margin grid as a set of assumption combinations, not a unique forecast.

**Acceptance:** create a synthetic price from known inputs, solve for the hidden growth input and recover it within configured tolerance; test impossible target values and zero/negative share counts.

## M04C: Valuation change bridge

Save scenario A and B with immutable input IDs and model version. Separate operating forecasts, discount assumptions, balance-sheet bridge and share count. A sequential contribution waterfall is order dependent: disclose the order. Do not describe it as a unique causal attribution. A later permutation-average decomposition may be offered with its method and computation cost.

## Implementation slices

1. Pure forward-calculation module with fixtures.
2. Scenario JSON import/export and validated inputs.
3. Browser display and sensitivity grid; table equivalent for every chart.
4. Reverse solver with failure states.
5. Evidence drawer and dated-price context.
6. Scenario comparison and export.

Proposed `valuation-lab/scenario-v1` fields include `as_of`, `currency`, `historical_source_ids`, `forecast`, `terminal_method`, `wacc`, `claims_bridge`, `shares`, `price`, `solver_bounds`, `assumptions`, and `model_version`. Save raw precision; round for presentation only. Do not fetch live prices or infer future forecasts silently.
