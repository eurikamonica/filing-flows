# Hidden Leverage & Contractual Obligations — Phase 1

**Status:** PR implementation / review required. **Not a new GAAP debt measure.**
**Location:** Filing Flows → Disclosures → **Hidden leverage**, at `/disclosures/#hidden`; company deep link `/disclosures/#hidden/TICKER-or-CIK`.
**Principle:** show what a company owes, has committed to purchase, or may need to support, **without summing mutually overlapping exposures**.

## 1. What Phase 1 actually delivers

- Independent, responsive cross-company SEC evidence screener and company drilldown; original SEC source links, USD amounts, accession numbers, date, form and XBRL tags.
- SEC companyfacts extraction for **reported purchase obligations, maximum potential guarantee payments, operating lease liabilities and undiscounted lease payments**, including up-to-six maturity buckets *only where tagged*. An undisclosed total remains **unknown**, never a sum of buckets unless independently justified.
- A **24-structure taxonomy**: all 15 priority structures plus nine additional research classes. Primary-document keyword matches are explicitly **UNVERIFIED TEXT LEADS**; a match is not proof of a payable, recourse, materiality or consolidation.
- Screening lanes A (debt-like financing candidate), B (fixed future cash commitment), C (contingent exposure); mixed lanes denote facts that cannot be classified without reading contracts.
- Reuses the existing Debt & Rates collector, pre-existing company JSON, disclosure site and GitHub Pages publishing pipeline. **Net Debt / Debt-to-EBITDA / implied CDS / valuation inputs are unchanged.**
- Automated offline Python fixtures and JS syntax checks. No paid data API and no invented exposure amounts.

**This phase does *not* calculate a total hidden-debt figure, an automatic adjusted debt value, contract payment PV, a fixed-commitment coverage ratio, or an Oracle lease estimate.** These require documented accounting judgments and more complete filing-footnote extraction.

## 2. The 15 core structures

| # | Structure | Review lane | Analytical question |
|---|---|---|---|
| 1 | Take-or-pay contracts | B | Must the buyer pay a floor irrespective of usage? |
| 2 | Power purchase agreements (PPA) | B | What minimum capacity/energy payments remain? |
| 3 | Cloud / GPU capacity commitments | B | Noncancellable capacity reservations and utilization risk? |
| 4 | SPE / SPV / VIE financing | A/C | Who consolidates and who absorbs expected losses/supports debt? |
| 5 | Reverse factoring / supplier finance | A | Have trade payables become financing-like? Disclosed outstanding balances? |
| 6 | Receivables securitization | A | True sale, recourse, retained interests, repurchase or liquidity support? |
| 7 | Guarantees / keepwell | C | Maximum contractual guarantee vs probable cash loss? |
| 8 | Uncommenced leases | B | Signed but not yet commenced; future nominal payments? |
| 9 | Sale-and-leaseback | A/B | Is the transfer a qualifying sale and what payments persist? |
| 10 | Synthetic leases | A | Legal form vs retained economic control and risk? |
| 11 | JV funding commitments | B/C | Fixed capital-call schedule vs contingent support? |
| 12 | Construction / CapEx commitments | B | Unavoidable construction/equipment outlays and timing? |
| 13 | Residual-value guarantees | C | Loss exposure if residual asset prices decline? |
| 14 | Royalty / revenue-based financing | A | Economic borrowing vs operating royalty and repayment waterfall? |
| 15 | Put options / redeemable NCI | C | When can holders force redemption; where is it recognized? |

These are **screening lanes, not final GAAP classifications**. A structure marked A may already be on the balance sheet, may be an actual sale, or may be immaterial. A B contract often provides economic value (products/services); it is not equivalent to debt. A C maximum is not expected loss.

## 3. Additional nine structures

| Structure | Review lane | Potential accounting / cash-flow issue |
|---|---|---|
| Repo / sale-and-repurchase | A | Secured borrowing, derecognition, collateral |
| Customer prepayments | B | Performance obligation, advance revenue and refunds |
| Commodity streaming agreements | A/B | Up-front project financing against future production |
| Tax equity financing | A/C | Sponsor buybacks, minimum returns, partnership control |
| Pension funding deficit | B/C | Mandatory contributions and pension shortfall |
| Asset retirement obligations | B/C | Recognized decommissioning liabilities and future cash settlement |
| Deferred acquisition consideration | A/C | Deferred purchase price/seller financing |
| Earn-outs | C | Conditional acquisition purchase-price payments |
| Liquidity backstops | C | Lines, LOCs and support to funds or SPVs |

Some primary filings may describe a negative statement ("no variable interest entities"). A text hit merely asks an analyst to inspect that passage. Missing hits **do not imply no exposure**.

## 4. Three layers, no double counting

**A — Financing debt candidates:** supplier finance, recourse securitization, some SPE support or other arrangements *only after* reviewing legal recourse, accounting recognition, financing substance and overlap with reported debt.

**B — Fixed contractual obligations:** minimum purchase payments, PPAs, capacity contracts, construction commitments, uncommenced leases. Evaluate **cash timing** and the associated receipt of services/assets. Keep gross nominal future payments distinct from any debt-equivalent estimate.

**C — Contingent exposures:** guarantees, residual guarantees, redemption rights, JV backstops. Separate contractual maximum, expected loss, stress-case payout and probability (where supportable).

| Output | Phase 1 | Interpretation |
|---|---|---|
| GAAP borrowings/net debt | Already exists; preserved | Current reported leverage reference |
| Tagged gross purchase commitments | Available where SEC tag exists | May include goods/services, overlap with other rows |
| Maximum possible guarantees | Available where tagged | Not necessarily payable or incremental |
| Recognized operating leases | Available where tagged | **Already recognized**, do not re-add |
| Undiscounted operating lease payments | Available where tagged | Not the PV; typically overlaps recognized lease liability |
| Contract keyword leads | Available from one periodic primary document | Unverified indication, with original excerpt/source |
| Uncommenced lease amount | **Not implemented** | Often narrative, custom-tagged, or footnote table only |
| Supplier finance amount / true-recourse assessment | **Not implemented** | Must parse company-specific notes and ASC 405-50 disclosures |
| Adjusted Net Debt & commitment coverage | **Not implemented** | Later optional reconciled scenario |

A non-GAAP reconciliation, **once verified**, could use:

\[
\text{Adjusted Net Debt}
=\text{Recognized Debt}+\text{Incremental Debt-like Obligations}-\text{Available Cash}
\]

Avoid adding leases twice: the exact definition of "Recognized Debt" must say whether already-recognized finance/operating lease liabilities are included.

A *separate* contractual sensitivity measure may discount unavoidable minimum payments:

\[
PV_{\text{commitments}}=\sum_{t=1}^{T}\frac{C^{\min}_t}{(1+r)^t}
\]

This is **not automatically debt**; determine cancellation rights, goods/services received, renewal assumptions, nominal versus present-value basis, and schedule overlap first. A future fixed-commitment coverage ratio should use cash flow **before** the exact obligations included in its denominator. This ratio is not a GAAP measure and should never be treated as equivalent to interest coverage.

## 5. SEC sources and extraction contract

**Source hierarchy:** periodic 10-K/10-Q/20-F/40-F → accompanying notes, commitments/contingencies and MD&A → primary filing text → companyfacts US-GAAP standardized facts. Company-specific extension tags, dimensions and footnote tables require next-phase ingestion. The 2020 SEC MD&A rule changes removed the old single mandatory contractual-obligations table; a single table search is insufficient.

- **Quantitative extraction:** require an exact report-date, USD, instant fact from permitted periodic forms, valid accession/filing date; choose the latest same-date amendment when applicable.
- **Numeric metadata:** `categories[].{key,class,amount_usd,reported_total,schedule,schedule_labels,source_url,accession,form,filed,as_of,evidence[]}`.
- **Qualitative screening:** `text_signals[].{key,label,excerpt,classification,review_lane,source_url,accession,form,filed}`. Classification is always `unverified_text_lead`. No dollar amount may be invented from text.
- **Taxonomy:** `public/hidden/index.json.taxonomy[]`: `key`, `label`, `review_lane`, `evidence_type=text_lead`, `status=screening_only`.
- **Coverage states:** `numeric_evidence`, `no_standard_tag_at_period`, `no_valid_balance_date`, or unavailable. None of these denotes an exhaustive audit of liabilities.
- **Provenance:** SEC document URL must link to the specific accession and (when known) primary filing; unrecognized/non-USD/custom tags must not be silently interpreted.

**No financial-model changes.** Phase 1 deliberately keeps new evidence in `hidden_leverage` under each pre-existing `public/c/{cik}.json` and `public/hidden/index.json`. No new "total leverage" field is permitted.

## 6. Architecture and rollout

1. `disclosures/app/hidden_leverage.py` — taxonomy, same-period tag extraction, source links, recent filing text leads.
2. `disclosures/app/debt.py` — uses the existing SEC companyfacts fetch and periodic document; incremental company backfill is prioritized once via `hidden_leverage_version=1`. Produces `debt-history/public/hidden/index.json`.
3. `disclosures/docs/hidden-leverage.js`, `hidden-leverage.css` — screener, maturity bars, evidence links, taxonomy, company drilldown, missing-data states.
4. `disclosures/docs/index.html` and `debt-view.js` — navigation/deep links; the old debt module remains separate.
5. Existing `.github/workflows/debt.yml` runs the collector; existing `.github/workflows/scan.yml` stages debt-history data to `disclosures/data/debt/`.
6. `.github/workflows/hidden-leverage-checks.yml` and `tests/test_hidden_leverage.py` — offline regressions; requires test and UI review before merge.

**Go-live:** merge PR → run Debt & Rates collector → publish the debt-history output → run ordinary Pages scan/deploy → verify `/disclosures/#hidden` and `/disclosures/data/debt/hidden/index.json`. Pushing a branch and opening a PR do **not** deploy the feature. Existing companies are filled incrementally; early empty screens may reflect collection lag.

## 7. Validation / accounting acceptance gates

- [ ] All offline Python tests and JS syntax tests pass for the latest PR head.
- [ ] Rebuild emits index with **24 taxonomy entries** and original source evidence on numeric rows.
- [ ] Exactly-on-period validation rejects unrelated years, duration facts, currencies and unsupported SEC forms.
- [ ] Any missing total stays null; maturity schedules are displayed separately and not blindly summed.
- [ ] Original GAAP debt, net debt, implied CDS, ratios and valuation remain byte-for-byte unchanged at their calculation points.
- [ ] Text excerpt containing negation is still marked unverified, never positive proof.
- [ ] Confirm several representative companies (e.g., ORCL, MSFT, AMZN) against their actual filing notes. **Do not seed headline figures such as an Oracle $288B lease commitment without reconciling the filing and its measurement date.**
- [ ] Validate mobile layout, deep links, CSV, accessibility, 404/no-data states and collector/Pages scheduling.

## 8. Phase 2 (not included in this PR)

Footnote HTML tables/inline-XBRL extensions; quantitative **uncommenced** lease obligation ladders; ASC 405-50 supplier-finance balances/roll-forward; PPA and cloud capacity minima by year; VIE recourse/consolidation analysis; guarantee exposure graph; contract-level normalized issuer/beneficiary/asset identities; deduplication; rate assumptions and optional **scenario-only** reconciled adjusted net debt and fixed-commitment coverage. Add an evidence confidence level and human-review flags before rankings.

## 9. References and standards to consult

- SEC EDGAR filing archive and XBRL companyfacts: https://www.sec.gov/edgar/search/ and https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC MD&A modernization: https://www.sec.gov/files/rules/final/2020/33-10890.pdf
- US GAAP ASC 842 — leases, including leases not yet commenced (see issuer-specific notes).
- US GAAP ASC 405-50 — supplier finance program disclosures.
- US GAAP ASC 460 — guarantees; ASC 810 — consolidation / VIEs; ASC 860 — transfers / securitization.

**Research disclaimer:** This feature organizes issuer-reported evidence; it neither asserts debt treatment nor replaces reading the audited statements and contract terms.
