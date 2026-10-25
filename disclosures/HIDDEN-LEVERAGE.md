# Hidden Leverage & Contractual Obligations

**Status:** Proposed implementation; original Debt & Rates and Valuation inputs are preserved.

## Location and integration

- Website: Disclosures → Hidden leverage; URL /disclosures/#hidden.
- Deep link: /disclosures/#hidden/TICKER-or-CIK.
- Company page: Debt & Rates links to the evidence detail.
- Collector: disclosures/app/debt.py, running via .github/workflows/debt.yml.
- Output: debt-history/public/hidden/index.json and existing public/c/{cik}.json, augmented with the hidden_leverage object.
- Publication: .github/workflows/scan.yml stages debt-history/public/ to /disclosures/data/debt/ unchanged. No new paid APIs or secrets.

**Go-live:** merge this PR, run the scheduled debt collector, then the normal Pages deployment. A feature branch alone does NOT change the live website. Pre-existing companies are backfilled incrementally after merging using hidden_leverage_version=1.

## Provenance and evidence rules

- as_of: balance-sheet reporting date.
- categories: source accession, USD numeric fact, US-GAAP tag, same-date maturity buckets when available, EDGAR source.
- text_signals: phrase matching against a primary SEC filing, labeled UNVERIFIED TEXT LEAD.
- coverage: numeric_evidence, no_standard_tag_at_period, no_valid_balance_date, or unavailable.
- Missing means unknown, never zero.
- Only the matching USD **instant** at the exact reporting date is accepted, from 10-K/10-Q/amendment/20-F/40-F.
- Later amendments at that reporting date supersede earlier filings.
- Every reported numeric value retains original tag, accession, form, filing date and SEC URL.

## Analytical classes

| Class | Includes | Non-additivity rule |
|---|---|---|
| Operating commitments | Unconditional purchases, gross purchase obligations | Can be goods or services; can overlap with other contracts |
| Contingent | Max future guarantee payments | Maximum is not payable debt or expected loss |
| Recognized reference | Operating lease liability | Already recognized; never add it twice |
| Contractual payment reference | Undiscounted lease payments | Not the PV of the lease; overlaps the recognized liability |
| Text leads | SPE/VIE, take-or-pay, PPA, GPU/cloud capacity, supplier finance, keepwells, securitization, sale-and-leaseback, etc. | No inferred dollar amount; potential false positives / explicit negations |

**Important:** no Total Hidden Debt is calculated, and reported net debt, CDS, debt/EBITDA, EV, or DCF are not modified. Any adjusted-leverage scenario requires a separately reviewed treatment of recourse, PV, operating value received and overlaps.

## Deliberate limitations

SEC companyfacts generally omits dimensional details and filer-specific XBRL extension values. A significant uncommenced lease may appear only in tables or narrative footnotes. A keyword hit is only a lead, not proof of liability; a source may say the company has **no** VIE. The present version shows provenance-first data rather than inventing a comprehensive exposure. The debt collector refreshes companies over batches and live Pages publication can lag its input.

## Acceptance checklist

1. Offline Python tests pass; Node.js validates both scripts.
2. Debt collector outputs public/hidden/index.json and company objects with hidden_leverage.
3. Site staging emits disclosures/data/debt/hidden/index.json.
4. Disclosures → Hidden leverage opens cross-company screening and specific-company original source evidence.
5. Existing Debt & Rates numerical outputs remain unchanged.
6. Missing amounts are clearly labeled, never converted to 0; text is unverified.
7. Validate sample filers such as ORCL, MSFT, AMZN against SEC primary documents before publicizing coverage or hidden-debt rankings.

## Follow-on development

Expand to full SEC inline-XBRL and filing-footnote table extraction, contract-level identification, overlap/recourse graphs, uncommenced leases, cash-flow maturity ladders, discount rate assumptions, reconciliation to operating leases, and an optional valuation stress case that can be audited and switched off.
