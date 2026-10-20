# Filing Flows — all-SIC supply-chain evidence ledger (P1 foundation)

This prototype creates a **single common schema** for every SIC industry, SEC company (CIK), named supplier/customer edge, official evidence document, reported cash CapEx, and scenario revenue attribution. No business is invented and no supply-chain coverage is promised until its evidence has been ingested. In particular, `company_tickers.json` supplies tickers but **not** SIC; `submissions/CIK....json` supplies SIC after a separate bounded SEC request.

The database is a local SQLite file, intentionally **not** automatically uploaded into GitHub's public code branch. Browser Gamma/Chains integration and robust hosted storage are future phases. Existing production Gamma/Chains code is untouched.

## Commands

From the repository root with Python 3.11+ (standard library only):

```bash
python research/industry_supply_chain/ledger.py --db /tmp/filing-supply.sqlite init
# Use an accurate business/operator identification string with a valid contact.
export SEC_USER_AGENT="Filing Flows Research contact@example.com"
# Seed actual SEC-listed issuers; CIK/name/ticker only, SIC currently missing.
python research/industry_supply_chain/sec_capex.py --db /tmp/filing-supply.sqlite --fetch-universe
# Retrieve up to 20 issuers per invocation (resume based on collector_status).
python research/industry_supply_chain/sec_capex.py --db /tmp/filing-supply.sqlite --max-issuers 20 --refresh-days 14
# If an existing full Filing Flows site build has generated Gamma files:
python research/industry_supply_chain/ledger.py --db /tmp/filing-supply.sqlite import-gamma --site _site/data
python research/industry_supply_chain/ledger.py --db /tmp/filing-supply.sqlite coverage
python -m unittest discover -s research/industry_supply_chain -p 'test_ledger.py' -v
```

On Windows, replace `export ...` with PowerShell `$env:SEC_USER_AGENT = 'Filing Flows Research real-contact@domain.com'`, and pick any writable Windows DB path. Do not copy the illustrative placeholder email into a live SEC request. The official SEC site imposes access/rate limits: the collector uses a user agent, pacing, bounded requests, three retries for transient errors, and an error ledger. If it returns HTTP 403/429, troubleshoot access rather than evading throttling. Repeated runs gradually fill the universe; SEC reference entities are not a full census of privately held global suppliers.

## Tables and semantics

| Table | Key | Rules |
| --- | --- | --- |
| industries | `sic` | Four-digit SEC SIC, includes empty/no-relationship sectors |
| companies | `cik` | Single U.S. SEC registrant identity, ticker may change |
| evidence | `evidence_id` | SEC accession/source URL/excerpt and observation timestamp |
| relations | `supplier_cik, customer_cik` | Direction is goods/services supplier→customer, no amount by default |
| financials | `cik, metric, period_end, accession` | Tracks financial figures as filed, corrections and filing times |
| attributed_revenue | scenario/buyer/supplier/category/period/as_of | Model estimates **separate** from official revenue |
| collector_status | `cik, feed` | Durable processing progress and error details |

A relation is disclosed **only** if a traceable SEC document, accession and filing date exist. Importing Gamma/Chains existing links without those fields yields `inferred`, never `disclosed`; unknown CIK pairings are skipped, not guessed via name similarity. No dollar width exists without an explicit supported amount. A reported transaction amount may be entered only with the evidence and manually checked attribution. A 10-K/10-Q name alone does *not* verify an exact transaction amount.

Cash CapEx is read from SEC XBRL `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`. The collector prefers directly reported three-month values and derives quarters from two same-start YTD facts only when the difference is nonnegative and periods are compatible. It records original `period_end`, `fy`, `fp`, `filed`, accession and tag. Missing/rejected facts remain **missing**, never zero. It does not yet normalize financing leases or company-specific CapEx definitions and cannot infer management guidance simply from XBRL.

## Revenue cross-validation and time-vintage discipline

`reconcile` only compares scenario attributed revenue with *independently entered and period-matched supplier segment revenue*. An absent segment actual returns a **null** error, not a pretend zero. Actuals filed after the given `--as-of` are excluded. Interpret remaining differences as forecast/coverage residuals, not hidden-customer proof. CapEx to vendor revenue timing is handled in the separate [CapEx scenario PR #38](https://github.com/eurikamonica/filing-flows/pull/38); integration is deferred until both sets of tests pass.

The system must ultimately preserve separate ledgers for terminal buyer CapEx allocations and multi-tier recognized accounting revenues, since adding a server OEM invoice, NVIDIA GPU value and Micron HBM value will otherwise double count the same equipment.

## Work still needed before 'all-market, all-industry' is truthful

1. Complete SEC public-company and SIC ingestion with documented coverage; ingest external/private/non-U.S. suppliers under verified identifiers without inventing CIKs.
2. Parse 10-K Item 1/7/8, 10-Q and EX-10/8-K contracts, run corporate entity resolution and require reviewed evidence for high-impact edges.
3. Add historical SIC/NAICS/GICS and product taxonomy; SIC alone does not uniquely identify GPU versus HBM versus datacenter services.
4. BOM unit/ASP extraction, project calendars, actual order/invoice evidence, equipment/finance-lease accounting and supplier attribution across layers.
5. Vintage-aware walk-forward training/validation by 2023–25 vs 2026, uncertainty intervals and an unconstrained 'Others' residual.
6. Persist indexed snapshots in dedicated object storage/DB, export compact API/JSON to Gamma, Chains and Revenue Forecast views.

The code is a **research foundation**, not a trained model or a claim that named companies transact with one another.
