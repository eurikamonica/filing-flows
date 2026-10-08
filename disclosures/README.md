# Disclosures — part of Filing Flows

This folder is the Disclosure Hub (v4) as it lives inside the `filing-flows` repository, published at
`https://<user>.github.io/<repo>/disclosures/` next to the earnings Sankeys. The page uses the Filing Flows design
system (same header, type, colours, dark mode and theme preference), with links back to the Sankey sections.

- **Collection**: `.github/workflows/disclosures.yml` runs the package's schedules (15-minute 13F, hourly House, hourly
  markets, daily all) with `disclosures/` as its working directory and commits `disclosures/docs/data/` to `main`.
  Run it by hand under Actions → *Collect disclosures*; the inputs are the stand-alone package's.
- **Publishing**: the Sankey scan workflow copies `disclosures/docs` into `_site/disclosures/`
  (`automation/stage-public.py`; caches and queue state left out) on its normal hourly publish. No second Pages deploy.
- **Secrets**: the repository's `SEC_USER_AGENT`; `FDIC_API_KEY` and `CFTC_APP_TOKEN` optional.
- **Local preview**: `python disclosures/app/serve.py` → http://127.0.0.1:8080

## 4.1 — state and Canadian officials, optional cost estimates

| Jurisdiction | Source | How it is collected |
|---|---|---|
| US House | Clerk's annual indexes | unchanged (PDF → text/OCR → review desk) |
| New York State | COELIG index of statements (statewide officials, Senate, Assembly; `jurisdictions.ny.years`) | index pages → statement page → printable HTML statement → text candidates. NY discloses **value categories** (letters); fill `jurisdictions.ny.value_categories` from the current FDS instructions, otherwise reviewers enter the bounds |
| California | FPPC Public Official Financial Disclosure Portal (filings since 2025-01-01; statewide officials, legislators, judges and other §87200 filers) | JSON search per year (split by position / initial above the portal's 1,000-row cap) → redacted Form 700 PDF → text/OCR |
| Texas | Texas Ethics Commission | **imports only** — PFS copies are not published online; obtain them by open-records request and list them in `config/imports.json` with jurisdiction `Texas` |
| Canada (federal) | Office of the Conflict of Interest and Ethics Commissioner public registry | registry pages → declaration pages (HTML) → text candidates |
| Canada (SEDI) | SEDI insider reports | **probe + imports** — SEDI answers scheduled jobs with a bot-protection challenge; the Health card shows the probe result each run; saved reports can be imported |

All of these share the House pipeline: nothing becomes a holding or transaction until it is reviewed against the
source page. The Officials view has a jurisdiction filter; the Health card lists discovered / extracted / queued per
jurisdiction. The hourly House schedule now rotates through every jurisdiction (`congress.batch_size` documents per
run; `--report-id` prioritises one).

**Optional cost estimates** (`prices` in `config/settings.json`, module `prices` in Actions, toggle in the UI):
daily closes from Stooq and CUSIP→ticker from OpenFIGI (both keyless; `OPENFIGI_API_KEY` raises the mapping batch).
13F: quantity change × average daily close of the report quarter; reviewed transactions: close on or just before the
event date → implied share range. Labelled as estimates everywhere; actual execution prices are not disclosed.

The original package documentation follows. Where it mentions the separate `Filing-Flows-Disclosure-Lab`
repository, its own `update-and-deploy.yml` or the `docs/` folder at the repository root, read `disclosures/…`
and the workflow above instead.

---

# Disclosure Hub v4

English-first disclosure dashboard, separate from the original Filing Flows repository. The original repository has not been modified. SEC contact: **Eurika eurikamonica@gmail.com**.

## This release finishes three more automatic collection paths

| Module | Discovery scope | How processing advances |
|---|---|---|
| 13F | SEC index filers since 2025-01-01 | Rotating manager batches and priority CIKs; retained from v3 |
| House | All names in selected 2024–2026 indexes | O/P PDF batches and source-bound review; retained from v3 |
| COT | All discovered codes in Disaggregated and TFF futures-only datasets since 2023 | Market history batches, including consolidated codes containing `+` |
| Banks | FDIC active institutions, plus explicit/retained banks | Bank financial-history batches since 2020 |
| N-PX | SEC index filers since 2025; discovered filers' reports since 2024 | Separate filer-scan and document-download queues; no repeated fixed-list-only parsing |

COT does not include Legacy, futures/options-combined or supplemental reports. FDIC's active directory does not include every closed bank. House index names include candidates/former members and are not verified unique current officials. Senate/state/local automatic collection remains unimplemented; explicit PDF imports are supported.

## Bundled official snapshot

| Source | Catalog | Available data |
|---|---:|---|
| 13F | 11,792 filers | 5 processed managers, including a notice-only manager |
| House | 6,987 distinct reports | 25 extracted PDFs; 6 source-checked excerpts |
| COT | 507 dataset/code combinations | 12 market histories; 10,450 category observations |
| Banks | 4,223 institutions | 9 bank histories; 234 bank-quarter rows |
| N-PX | 11,495 discovered/explicit filers | 7 scanned filers; 18 downloaded reports; 5,183 vote-table rows |

These are **real initial processing counts, not claims that all catalog entries are complete**. COT/bank/N-PX queues continue on scheduled runs. A downloaded N-PX notice or unsupported legacy report is not zero holdings. Vote rows are not distinct companies or transactions.

## Faster interface and explicit data scope

The v3 blue/white workspace remains. Catalogs now load only when opened: the entry JSON is about 97 KB, rather than roughly 10 MB in v3. The executable entry data file is about 68 KB. These figures exclude the catalog/report files fetched on demand and the fictional demo file.

- One directory searches 13F managers, House reports, COT markets, FDIC banks and N-PX filers.
- Bank and COT charts load just the selected entity's history.
- N-PX loads the first 1,000 vote rows, with **Load next 1,000 rows** for subsequent chunks. Search, charts and CSV clearly apply to the loaded rows. Load all chunks before interpreting them as a complete parsed filing.
- Health distinguishes discovered, processed, scanned, pending and unsupported records.
- Existing 13F quarter comparisons, clickable treemap, centered weight-change bars and full-name congressional value intervals remain.

## Upgrade an existing v3 repository

**Read `UPGRADE-EXISTING.md` first. Do not overwrite your current `docs/data/` with the bundled starter snapshot if you want to preserve progress.** The code migrates v3 data on the next collection run. Keep reviewed CSV and imported reports.

The full ZIP also supports a new installation or a local preview. It contains no dot-prefixed files/folders. GitHub's actual workflow must be replaced via its web editor using `automation/update-and-deploy.yml`.

## Local preview on Windows

```powershell
py -3.12 app/serve.py
```

Open `http://127.0.0.1:8080`. Or double-click `START-WINDOWS.cmd`. Use the HTTP server rather than opening `docs/index.html` directly; JSON shards require it. No npm or virtual-environment activation script is needed.

## Collect locally

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 app/collect.py --only markets
py -3.12 app/collect.py --only banks --bank-cert 14 --revalidate
py -3.12 app/collect.py --only cot --market-id "gpe5-46if-13874+" --revalidate
py -3.12 app/collect.py --only npx --manager-cik 1000249 --revalidate
py -3.12 app/collect.py --only holdings --manager-cik 1067983
```

`markets` collects COT, banks and N-PX in one run. `--batch-size` overrides entity/filer/PDF batch size. N-PX's separate document budget is `npx.document_batch_size` in settings.

OCR requires Tesseract and Poppler in addition to pdfplumber. Actions installs OCR tools for runs that can process House/imported PDFs. Optional environment variables: `SEC_USER_AGENT`, `FDIC_API_KEY`, `CFTC_APP_TOKEN`.

## Defaults and cadence

- 13F: 8 managers per 15-minute scheduled run.
- House: 30 documents per hourly scheduled run.
- Hourly `markets`: up to 10 COT market histories, 20 banks, 4 N-PX filer scans and 12 N-PX documents.
- Daily all-module run; Sunday requests revalidation of that run's selected batches.
- Successful N-PX accession downloads are reused unless revalidation is requested. New amendments have separate accessions.
- COT/bank directories are refreshed daily; the current SEC index is checked at most hourly. Official index publication can lag actual submissions.
- Refresh eligibility, batch budgets and schedules do not guarantee a completion deadline. Actions queuing and source latency can delay work. Large backfills take many runs.

## Storage and reliability

`docs/data/catalogs/` contains browser catalogs. `shards/` contains entity histories, quarters, PDFs' extracted candidates and vote chunks. Keep `discovery-state.json`, `npx-queue-state.json` and `cache/` in the repository for incremental collection; the Pages artifact excludes these collector-only files.

Completed runs commit progress. Failures preserve prior valid entity data and report errors. If a runner is terminated mid-batch before publication/commit, that batch may need to rerun. Do not run simultaneous local collectors against one output directory.

This remains a GitHub-hosted pilot architecture. Full-market multi-year history may outgrow Git repository/Pages limits. Object storage and a database/queue are the next hosting step; none are provisioned or billed by this package.

## Verification

74 Python tests, 30 UI template checks and 8 asynchronous-loading checks pass. Real FDIC/COT discovery, repeated batches, the `+` market code, and N-PX XML downloads/parsing were exercised. Real-browser layout/interaction and GitHub Actions/Pages deployment were not tested in this environment.
