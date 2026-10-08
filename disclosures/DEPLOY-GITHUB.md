# GitHub Actions and Pages — v4

For your existing v3 site, use **UPGRADE-EXISTING.md** to preserve progress. For a fresh installation, follow the steps below. Do not install in the original `filing-flows` repository.

## Fresh installation

1. Create an independent repository, or use `Filing-Flows-Disclosure-Lab` only if deliberately replacing its data.
2. Extract the ZIP. Upload its contents with `app/`, `docs/`, `config/`, `tests/` and `automation/` at the repository root. Include every bundled file under `docs/data/`.
3. Use GitHub Desktop or multiple browser uploads: GitHub's browser allows 100 files per upload and 25 MiB per file. The package has more than 100 files, with every individual file below 25 MiB.
4. Settings → Pages → Source → **GitHub Actions**.
5. In the web editor create `.github/workflows/update-and-deploy.yml`, copying all of `automation/update-and-deploy.yml`. The visible template itself is inert. Git users can instead run `py -3.12 automation/install-workflow.py` before committing.
6. Actions → Collect disclosures and deploy → Run workflow → **all**. Inspect logs and the Pages deployment result. One run advances batches; it does not finish the universe.

For the user's existing repository, the URL remains:
`https://eurikamonica.github.io/Filing-Flows-Disclosure-Lab/`

## Manual inputs

| Input | Meaning |
|---|---|
| module | all, holdings, congress, cot, banks, npx, markets |
| batch_size | Optional positive integer for entity/filer/PDF count; N-PX document count stays separately configured |
| manager_cik | Prioritize one 13F manager or N-PX filer; select the matching module |
| report_id | Prioritize one supported House report; select congress |
| bank_cert | Prioritize one FDIC bank; select banks |
| market_id | Prioritize one dataset-code from the COT directory; select cot |
| revalidate | Request fresh retrieval for that selected batch rather than ordinary reuse/eligibility |

Examples:

- banks + bank_cert **14**
- cot + market_id **gpe5-46if-13874+**
- npx + manager_cik **1000249**
- holdings + manager_cik **1067983**
- congress + report_id **house-20035553**

A recently processed priority item can be skipped unless revalidate is selected. Unsupported House types remain unsupported. The public website cannot start authenticated GitHub jobs.

## Automatic runs

- `7,22,37,52 * * * *`: 13F batch.
- `17 * * * *`: House/PDF batch.
- `43 0-9,11-23 * * *`: COT + banks + N-PX (`markets`); 10:43 is covered by the daily all-module run.
- `43 10 * * *`: all modules; Sunday also requests revalidation of that batch.

Concurrency serializes runs. GitHub schedules/pending jobs are best effort: frequent triggers can be delayed or superseded in the pending queue, especially when collection takes longer than the interval. Monitor actual logs rather than assuming every nominal trigger ran.

Default budgets: 8 13F managers, 30 House documents, 10 COT markets, 20 banks, 4 N-PX filer scans and 12 N-PX documents per applicable run. Increase gradually based on observed duration and the 40-minute job limit. A large backfill requires many successful runs; no instant full-market or fixed completion-time promise is made.

## Contact, optional keys and permissions

SEC User-Agent defaults to **Eurika eurikamonica@gmail.com**. Optional Actions secrets: SEC_USER_AGENT, FDIC_API_KEY and CFTC_APP_TOKEN. Do not put API keys in public configuration. No SEC login is used for these public downloads.

The workflow declares contents:write, pages:write and id-token:write. Repository/organization policies must permit the snapshot commit and deployment. It does not bypass protected branches.

## Files to retain

- `docs/data/live.json` and live.js: entry snapshot.
- `docs/data/catalogs/`: complete source-specific catalogs loaded on demand.
- `docs/data/shards/`: browser data for quarters, reports, market/bank histories and vote chunks.
- `docs/data/cache/`, discovery-state.json, npx-queue-state.json: collector state; committed but excluded from the public Pages artifact.
- Raw downloads in storage/: uploaded as an Actions artifact with 30-day retention, not committed or included in this ZIP.

Completed runs preserve progress through commits. A terminated run before publication/commit can lose that in-flight batch. Keeping old files is essential for incremental reuse. Full historical coverage will eventually need durable object storage/database capacity beyond a Git repository. This ZIP provisions no external service.

## Check after deployment

- Hard-refresh for v4 assets.
- Explore directory → switch among all five source catalogs.
- Open an available bank and COT market; confirm dates, units and CSV.
- N-PX → choose a large filing, load its next chunk, and confirm loaded count grows. Search/chart/CSV scope is loaded rows only.
- Health → distinguish catalog size, scanned/processed entities and pending work.
- Check mobile layout, treemap keyboard selection and OCR form interactions. Browser QA was unavailable during preparation.

Missing data files produce explicit load errors. A successful source run with pending work is not complete coverage. Congressional OCR candidates are not automatically promoted to holdings.

Official upload documentation: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
