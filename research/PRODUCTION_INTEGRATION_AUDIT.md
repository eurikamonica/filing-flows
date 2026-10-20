# Filing Flows: production integration audit and rollout

Scope: GitHub Pages website (not an existing "site" branch). As of 2026-10-20, #36, #37, #39, #41 merged in website-source paths; #38 / #40 were research-only. Web fetch / browser proof of the deployment was unavailable during the original audit, so no false claim is made that live delivery was confirmed.

## Architecture

```
Public SEC tickers, submissions and companyfacts
  -> .github/workflows/industry-ledger.yml (every 2h, up to 60 issuers per run)
  -> industry-ledger-data branch: industry.sqlite (durable) + public/ derived JSON
  -> .github/workflows/scan.yml reads public/ during Pages build (15-minute site scan)
  -> scripts/integrate_industry.py stages /data/industry-intelligence/
       + adds evidence-graded edges to matching existing Gamma SIC JSON
       + maps Polymarket/Kalshi events to UNIQUE CIK/ticker and SIC, **identity only**
       + copies /supplier-revenue/ and /integration-health/
  -> actions/deploy-pages
  -> verify-integration job fetches ACTUAL public URLs and checks current run id
```

### Explicit rollout preconditions

- **Do not merge** without inspecting the new `Industry production integration checks` job and its unit tests.
- `SEC_USER_AGENT` is already used by `scan.yml`. It must be a real contact with a valid email. Never put the secret in public JSON.
- The collector will create the `industry-ledger-data` branch **only after this PR is merged and its workflow runs**. The initial Page build may show `not_collected`, accurately.
- Dedicated SQLite on a data branch is an interim GitHub-native persistence store for research, **not** a horizontally scalable database. Monitor blob/branch size. Graduate to managed DB/object storage before accumulation is too large.
- Collector processing is bounded and partial: the public ticker list does not contain SIC; requests to `submissions` and `companyfacts` are gradual. Global privately held suppliers are not included.
- Missing SEC facts, supplier links, forecasts and actual segment data remain missing. All imported relations show `evidence_level`; unsupported monetary weights are null.
- The PR #38 calculation is invoked only on `demo_only=true` examples; this does **not** constitute a validated forecast. Demo amounts are **never persisted to `financials` or `relations`**.
- Market-event mapping is **CIK identity only**; there are **no causal CapEx/Revenue impacts** inferred from market probabilities. Cross-venue matched settlement contracts still need separate review.

### Deployment verification

`scan.yml` now runs a separate `verify-integration` job **after** `deploy-pages`. It requests:

- `gamma.js` must include #36 Network Graph.
- `app.js` must include #37 quarterly 13F selector.
- `disclosures/app.js` must include #39 date controls.
- `disclosures/consensus.js` must include #41 market screening.
- `supplier-revenue/index.html`, `integration-health/index.html`, and `data/industry-intelligence/integration-health.json` must load. The last includes the **exact GitHub Actions run ID**.

An artifact's successful creation cannot prove browser-visible deployment. Actual deploy/smoke success is in the GitHub Actions workflow run and summary. The website health page deliberately displays publication as `artifact_prepared_unverified` because it is generated before Pages deploy.

### Acceptance checks

1. PR integration tests and syntax checks pass offline.
2. On first merged data collection, `industry-ledger-data` gains SQLite and `public/industry/index.json`; no secret tokens or SEC User-Agent contact email should appear in the public snapshot.
3. Site publication uses new exported evidence for matching SICs; old Gamma charts still load if collector is absent.
4. `/supplier-revenue/` displays coverage, missing formal forecasts and optional *clearly hypothetical* scenario entries; no dollar attribution is represented as an actual invoice.
5. `/integration-health/` reveals collection coverage, parsing limitations, identity-only market links and build metadata; run-specific public smoke check passes.

### Remaining items before declaring full production research

- Full SEC + global issuer/company coverage and parent/subsidiary entity matching, not just tickers.
- Scalable evidence storage; reviewed SEC Item 1, Item 7, EX-10 and material contract extraction; URL/accession section citations.
- Real BOM units, vendor market shares, product/tier accounting, recognition lag estimation and supplier **segment** revenue facts.
- 2023–2025 calibration with point-in-time data / 2026 holdout; errors with uncertain intervals.
- Verified market-event settlement-rule matching and a causal industry exposure methodology.
- Optional 8B extraction evaluation without automatically trusting LLM-derived amounts.

**Status note:** The only thing that turns a PR into verified online operation is a successful post-deploy browser/HTTP check. A merged PR alone is insufficient.
