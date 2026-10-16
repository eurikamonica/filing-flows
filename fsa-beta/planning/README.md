# Filing Flows: modular implementation and deployment plan

Created by ChatGPT (OpenAI), October 15, 2026 (America/New_York).

**Status: design documents only.** This addition creates no application modules, collectors, cloud resources, workflows or deployments. It does not modify existing files. The plans below distinguish existing beta prototypes from proposed work.

## Read in this order

| Document | Purpose |
| --- | --- |
| [01_DATA_AND_ISOLATION.md](01_DATA_AND_ISOLATION.md) | Module boundaries, data contracts, evidence and timing |
| [02_FINANCIAL_ANALYSIS.md](02_FINANCIAL_ANALYSIS.md) | Statement analysis, working capital and advanced FSA |
| [03_VALUATION.md](03_VALUATION.md) | Forward/reverse DCF, expectations maps and valuation bridges |
| [04_MACRO_AND_ACADEMIC.md](04_MACRO_AND_ACADEMIC.md) | Macro vintages, company exposure and reproducible research |
| [05_DEPLOYMENT_RUNBOOK.md](05_DEPLOYMENT_RUNBOOK.md) | Local preview, isolated static hosting, data refresh, optional backend |
| [06_IMPLEMENTATION_BACKLOG.md](06_IMPLEMENTATION_BACKLOG.md) | Small executable work packages and acceptance gates |

## Current baseline

Planning baseline: beta commit `a320dd95ac20f059fe6a629afec1b951e71fce83`.

- `fsa-beta/`: earlier standalone Python FSA workbench, optional model-related code and documentation.
- `fsa-beta/visual-lab/`: standalone profit/OCF, accrual and reserve charts plus interactive Cookie Jar scenario.
- `fsa-beta/social-lab/`: standalone candidate selection, evidence cards, PNG preparation, deterministic English drafts, journal and captioned animation code.
- The two browser labs use their own schemas. They are not an integrated financial data platform.
- Previous calculation tests passed, but browser visual/end-to-end verification was outstanding. WebM export is implemented but not verified in an actual browser here.
- A user screenshot reported local Qwen3-0.6B inference and a 20-step QLoRA trial. That is a local execution report, not independent validation of financial accuracy, a published model, or proof those changes exist in this remote beta branch.

## Proposed module split

All paths below are **proposed additions**, not existing executables.

| ID | New path under `fsa-beta/` | First deliverable | Runtime | Depends on |
| --- | --- | --- | --- | --- |
| M00 | `research-core/` | Evidence/period contracts and validation fixtures | Python + JSON | none |
| M01 | `evidence-lab/` | Evidence drawer and changes heatmap | Static browser | M00 |
| M02 | `working-capital-lab/` | Cash-cycle and NI-to-OCF explanation | Static browser + batch calculation | M00–01 |
| M03 | `reformulation-lab/` | Reviewed operating/financing mappings and RNOA | Static browser + batch calculation | M00–01 |
| M04 | `valuation-lab/` | DCF and one-variable reverse DCF | Static browser | M00–01 |
| M05 | `macro-lab/` | Macro release/vintage timeline | Batch collector + static browser | M00 |
| M06 | `research-lab/` | Event studies and reproducible exports | Local Python batch + static results | M00, dated prices/events |
| M07 | `research-export/` | Versioned module snapshots and release manifest | Local/batch Python | released modules |
| M08 | `narrative-lab/` | Optional locally generated sourced explanations | Local GPU; static output | M00 + held-out evaluation |

Keep future module assets local and use relative URLs. Do not change existing Sankey code, social publishing, production configuration, the earlier beta server, or production navigation to introduce these experiments.

## Recommended release sequence

1. Evidence and temporal correctness: M00–01.
2. Operating analysis: M02, then M03.
3. Expectations and valuation: M04.
4. Historical macro context: M05.
5. Academic experiments: M06.
6. Integrate reviewed exports through M07; consider model narration only after evaluation.

Deploy an independent static research site first. Train and compute on the laptop, publish only selected JSON/assets. A live model service is a later architecture decision, not needed for the initial website.

## Deferred extensions from the brainstorm

| Extension | Owning module | Additional prerequisite |
| --- | --- | --- |
| Segment explorer | M02 | Reviewed segment taxonomy; discontinued/reorganized segment history |
| Debt maturity wall | M02 | Footnote maturity tables, lease/debt definitions, currency normalization |
| Capital allocation map | M02 | Cash-use definitions that reconcile without double counting |
| Footnote diff / restatement replay | M01 | Original and amended filing versions; stable section matching |
| Reserve adequacy | M03 | Claims, write-offs, loss history and reserve-type-specific evidence |
| Residual income valuation | M04 | Clean-surplus reconciliation and explicit equity cost of capital |
| Dilution / buyback lab | M04 | Share-count bridge, share classes, option/SBC assumptions |
| Yield curve / inflation pipeline | M05 | Maturity/frequency alignment and transformation metadata |
| Factor and accrual-anomaly studies | M06 | Point-in-time universe, factor licenses, delistings, returns and costs |
| Company time replay / four lenses | M07 | Stable contracts and synchronized available-at timestamps |
| Additional Cookie Jar lessons | separate new lesson directory | Reviewed entries, accounting assumptions and accessible transcripts |

Avoid an opaque single earnings-quality score. Present evidence-backed dimensions and missing coverage instead. Estimates and assumptions must remain visibly distinct from observed disclosures.
