# Company quality visualization audit and implementation

Audit date: 2026-10-27. Base: 77917280a9c5152ddc34257b0ee6396bd488e1f2.
Scope: existing company pages, with published Apple and CoreWeave company documents and the deployed Quality/Debt renderers inspected. This is not a full-universe data-quality audit.

## Existing features retained

| Surface | Existing visualization | Action |
| --- | --- | --- |
| Profit & cash | Net income versus OCF; cash-flow accrual history; reserve rollforward | Retained; no duplicate bridge |
| Profit & cash | NI-to-OCF bridge with unexplained residual; collections versus revenue; cash conversion cycle | Retained; new historical working-capital chart complements selected-period detail |
| Capital allocation | Capital allocation figures and debt maturity columns | Retained |
| Debt & rates | Maturity wall, credit cushion, coverage/covenant information, debt history, convertible scenarios | Retained; Quality links to the existing page |
| Quality research | Piotroski/Altman/Beneish tables, operating cost scatter/fit, margin mean-reversion chart, annual facts table | Retained in its own container below company-data trends |
| Company quality measures | Published health metrics, formula table and source inputs | Retained; newly supports visual histories via a shared module |
| Disclosures & risk | Hidden leverage evidence and revenue-quality screening | Retained; not summed into a fabricated hidden debt total |

## Gaps addressed

- Sales/closing receivables/closing inventory share a common positive index base, explicitly labelled with the base date.
- DSO/DIO/DPO histories use a separate days axis, never a mixed currency/percentage axis.
- Selectable published health metric history includes signed percentage measures and multiples; no new scoring model is implied.
- FY and quarterly observations are kept separate, chronologically sorted; missing data and missing periods interrupt line segments.
- Every chart has an accessible HTML data table. An evidence-period selector exposes raw inputs, fact-specific balance dates, XBRL concepts and SEC filing links.
- Both Profit & cash and the company Quality route use the same module. The latter keeps charts available even if the separate research dataset is missing.
- Financial-sector caveat, coverage counts, proxy definitions and unavailable states are explicit. No unobserved peer percentiles, DA estimates or accounting verdicts are generated.

## Live coverage observed

The Apple research document was available. CoreWeave's independent research-quality document returned HTTP 404, while its company JSON contained fiscal-year and quarterly working-capital/health observations. The new view uses the latter without inventing missing Piotroski/Altman/Beneish scores.

## Validation

Node tests cover shared-base normalization, zero versus missing, period separation, missing-period line breaks, signed measures, source escaping, SEC evidence and accessible tables. Browser smoke checks use downloaded published documents without committing those snapshots or hardcoding live financial figures into production code. Site asset packaging is checked separately.

## Still outside this change

No peer database, discretionary-accrual estimator, AR aging extraction, customer concentration extraction, new debt model or forecast dataset is added. These need their own source coverage and methodology validation before plotting.
