# 02 — Financial analysis implementation

Created by ChatGPT (OpenAI). All modules below are proposed.

## M01: Evidence drawer and change map

**MVP scope:** one reviewed company, two annual periods, six concepts: revenue, operating income, net income, OCF, capex and total assets. Build an independent page with period selectors, signed change bars, a concept-by-period heatmap, a tabular fallback and evidence drawer.

**Implementation steps:**

1. Build a read-only adapter from an explicitly selected input format to financial-observation-1.
2. Validate observations and generate a concept/period matrix. Mark gaps separately from zero.
3. Calculate absolute changes for compatible inputs. Display percentage change only with a positive prior denominator; otherwise show amounts and a sign-transition label.
4. Use a diverging heatmap with an explicit legend. Do not mix raw monetary changes and percentage changes on one color scale.
5. Clicking a cell opens source IDs, original labels, timestamps and derivation.
6. Export the visible table and a manifest, including the as-of cutoff.

**Acceptance:** every displayed nonmissing amount traces to evidence; loss-to-profit transitions do not yield misleading ordinary growth percentages; original source files remain byte-identical.

## M02: Working capital and cash conversion

**Required observations:** discrete-period sales and cost of sales; opening/closing receivables, inventories and trade payables; reported NI, OCF and cash-flow adjustments. Use average balances only when both endpoints exist.

For a period of D days:

- DSO = average trade receivables / credit sales × D. If credit sales are unavailable, total sales is an explicitly labeled proxy.
- DIO = average inventory / cost of sales × D.
- DPO = average trade payables / purchases × D. Cost of sales may be an explicit proxy, not silently treated as purchases.
- CCC = DSO + DIO − DPO.

Require positive appropriate flow denominators. Match scope; financial institutions and business models without relevant inventory need different treatments. Purchases estimated from inventory changes require an explicit simplifying assumption and may be invalid with acquisitions, FX and write-downs.

**Visuals:** three aligned days-series panels; CCC summary; reported NI-to-OCF waterfall. Use disclosed cash-flow adjustments for the waterfall. Balance-sheet deltas alone do not establish operating cash effects because of FX, acquisitions and noncash movements.

**Reconciliation:** residual = reported OCF − (NI + sum of included cash-flow adjustments). Show residual visibly. Do not invent components to eliminate it. Explain net-income scope differences where relevant.

**Acceptance case:** NI 100 + depreciation 20 − receivables cash impact 15 + payables cash impact 5 = OCF 110; supplied OCF 112 must show residual 2. Missing opening inventory blocks DIO rather than replacing it with closing inventory.

## M03: Reformulation and RNOA

**MVP:** nonfinancial companies only; two balance-sheet dates and a matching income period. Store a versioned mapping overlay instead of editing original line items. Each classification includes operating/financing/unclassified, rationale, reviewer and evidence ID. Require explicit treatment for cash, leases, pensions, investments, deferred taxes and minority interests.

Definitions, with a consistently scoped equity measure:

- NOA = operating assets − operating liabilities.
- NFO = financial liabilities − financial assets.
- Equity residual = NOA − NFO − equity.
- Estimated NOPAT = operating income × (1 − assumed operating tax rate), only in simplified mode. Label this an estimate, not full tax allocation.
- RNOA = period NOPAT / average NOA.
- Operating margin = NOPAT / revenue.
- Net operating asset turnover = revenue / average NOA.
- Their product equals period RNOA when denominators and scopes are consistent.

Block ordinary ratio interpretation with zero/negative average NOA. Do not annualize quarterly returns by default. Do not label bank-specific balance sheets with a generic industrial-company mapping.

**UI:** reported statement on the left, classification overlay on the right; impact preview; reset to imported mapping; visible unclassified totals; decomposition chart; explicit assumption badge.

**Acceptance:** changing a classification changes only the scenario; reset restores the previous overlay; mapping and equity residuals stay visible; missing NOPAT or opening NOA blocks RNOA.

## Extensions

Add segment views only with comparable segment definitions. Add capital-allocation diagrams only when cash sources and uses reconcile without treating financing inflows as OCF. Add reserve adequacy only after obtaining reserve-specific loss/claim history. Footnote diff should preserve original and amended documents and describe extraction uncertainty.

## Proposed new files per module

`index.html`, `app.js`, `style.css`, `calculate.py`, `fixtures/demo.json`, `tests/test_calculate.py`, `README.md`, `VALIDATION.md`. Use only the files needed by that module; these are not present yet. Avoid introducing a framework or rewriting earlier pages solely for consistency.
