# Cash & Cookie Visual Lab

Created by ChatGPT (OpenAI), October 15, 2026.

An additive, independent English-language beta for Filing Flows. This directory introduces four experiences: profit versus operating cash flow, cash-flow-based accruals, a reserve rollforward waterfall, and Crumb, an interactive animated cookie jar. It does not modify or import existing production or beta files, use any API, send data, or connect to the existing FSA server. It is not deployed.

## Run locally

Download the `beta/fsa-chatgpt` branch, extract it, and open `fsa-beta/visual-lab/index.html` in your browser. There is no install step, Python environment, account or API key requirement. The local-file page uses classic scripts and no fetch calls.

Alternatively, from **this directory only**, run:

```powershell
py -m http.server 8766 --bind 127.0.0.1
```

Open http://127.0.0.1:8766 and stop with Ctrl+C. Do not serve the repository root. Port 8766 is separate from the earlier beta server on 8765. No change to that server's allowlist is needed.

## Explore

1. The first load uses a clearly labeled fictional three-year example.
2. Select a period to update KPIs and the reserve waterfall. The historical comparison and accrual chart retain all periods for context.
3. Inspect the numbers and source text below the charts.
4. In the separate fictional pet scenario, record a provision, settle an obligation, or reverse an estimate. These actions never change the imported financial report.
5. Pause animation, or use your operating system's reduced-motion setting.
6. Export the example JSON as a template. Edit a copy, then import it. Data stays in memory until you export; reloading resets it. Import does not write back to any source file.

## Accounting definitions

- Accruals = net income − operating cash flow, using matching reporting scope and duration. This is a cash-flow-based screening measure, not a full reconstruction of accrual accounts.
- Accrual ratio = accruals / ((opening total assets + closing total assets) / 2). Both asset balances must be positive. This is a period ratio, not annualized.
- Closing reserve = opening + additions − releases − utilization + other. `other` is signed; other inputs are nonnegative magnitudes.
- Difference = supplied closing − calculated closing. Absolute differences below 0.005 input units are treated as reconciled; this is numerical tolerance, not audit materiality.
- A release is shown as a pretax income benefit only when `release_in_income` is explicitly true and the rollforward reconciles. The flag is user supplied, not independently verified.
- Utilization is not automatically an earnings credit. Reserve balances are not cash balances.
- Positive accruals or reserve releases are not sufficient evidence of earnings manipulation. A cookie jar allegation requires evidence that estimates were excessive or otherwise inappropriately managed.

The pet assumes a liability provision expensed through profit: additions reduce pretax profit without immediate cash impact; cash settlements reduce the provision and cash without a new expense; reversals increase pretax profit without immediate cash impact. Taxes, discounting, asset capitalization and other reserve types are outside this teaching scenario. It is not a universal journal-entry engine. Cookie icons are decorative and capped at 16; the numeric balance is authoritative. No scores or rewards encourage profit manipulation.

## Import format

This is a deliberately separate format, **not** the earlier beta engine input or output schema. There is no automatic SEC extraction or adapter in this addition. Export the bundled demo to obtain a complete example.

```json
{
  "schema": "visual-lab-1",
  "company": "Example company",
  "unit": "USD millions",
  "demo": false,
  "periods": [{
    "label": "FY2025",
    "net_income": 130,
    "ocf": 85,
    "opening_assets": 900,
    "closing_assets": 1000,
    "source": "Supply filing URL, period dates, note/table and scope here.",
    "reserves": [{
      "name": "Warranty provision",
      "opening": 45,
      "additions": 28,
      "releases": 18,
      "utilization": 20,
      "other": 2,
      "closing": 37,
      "release_in_income": true
    }]
  }]
}
```

Use oldest-first periods with the same duration, scope, unit and currency. Quarterly OCF must be discrete-quarter, not cumulative YTD. The importer validates numeric types and shape but **cannot verify period comparability, source authenticity, reserve adequacy or accounting classification**. These remain manual review requirements. Omit unavailable numbers or use null; do not substitute zero. A complete reserve rollforward needs all six values, including sourced zeros. Import limit: 200 KB, 24 periods, 20 reserves per period, absolute numeric values up to 1e12. Text is rendered as text, never interpreted as HTML.

## Verification

```text
node --check app.js
node --check math.js
node test.cjs
```

The test covers accounting identities, negative accruals, genuine zero versus missing values, denominator constraints, incomplete and unreconciled rollforwards, distinct pet transaction effects, over-release rejection and malformed imports. See VALIDATION.md for actual execution results and limits.

## Isolation and removal

All new files are under `fsa-beta/visual-lab/` on the beta branch. There are no shared dependencies, package/config changes, production navigation links, workflows, remote calls or deployment changes. Delete this directory to remove this addition. Integrating a live company feed or adding it to the public website is a separate future change.
