# Filing Flows

A static website that scans SEC EDGAR every hour for new 10-Q and 10-K filings and draws each one as an
income-statement and cash-flow Sankey in the *earnings-sankey* standard format: revenue lines → revenue →
gross profit / costs → operating profit → pre-tax → tax, minority interests, net earnings → operating cash flow.

- **Every filing** with XBRL revenue and net income gets a chart (latest three quarters kept).
- **Starred companies** (`config/starred.txt`) keep eight quarters and are back-filled from their filing history.
- **Sector and industry charts** add up every company whose fiscal quarter ends in the same calendar quarter
  (SIC-code groups; the ten largest companies appear by name).
- **Click any node** to read what the company wrote about that line in the same filing (MD&A paragraphs, quoted
  verbatim). Company pages open with the first paragraphs of Item 1 *Business* from the latest 10-K.
- **Analysis paragraphs** are written by fixed rules from the numbers. No language model is used anywhere.
- **Comparison view**: the same chart with a dark strip on every band that grew since the previous quarter and a
  `Δ = scale + mix` line per node.
- **Export** PNG, JPG or PDF. Exports contain the chart only; the notes panel and note markers stay on screen.

## Deploy (GitHub Pages, about five minutes)

1. Create a GitHub repository and push this folder to its `main` branch.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Secrets and variables → Actions → New repository secret**
   `SEC_USER_AGENT` = `Your Name your.email@example.com`. The SEC rejects requests without a contact; a secret
   (rather than a variable) keeps the email out of the public Actions logs.
4. **Actions → Scan EDGAR and publish → Run workflow.** For the first run set `backfill_days` to 3–7 so the
   site starts with recent filings instead of only the last hour.
5. The workflow then runs every hour (`17 * * * *`). The site is at `https://<user>.github.io/<repo>/`.

State (which filings were seen, the per-company data) lives on a `data` branch that the workflow rewrites as a
single commit each run, so `main` history stays clean. Delete the branch to start over.

GitHub disables scheduled workflows in public repositories after 60 days without activity on the default branch;
re-enable it from the Actions tab or push any commit.

### Star a company

Add its ticker to `config/starred.txt` (one per line) and commit. The next hourly run back-fills its last eight
10-Q/10-K filings. The home page links to the file when the site runs on GitHub Pages.

## How it works

```
EDGAR "getcurrent" feed (10-Q, 10-K) ─┐
EDGAR daily index (backfill)         ─┴─► pending queue (state.json)
                                             │  retried hourly until XBRL facts appear (up to 24 h)
                                             ▼
   data.sec.gov/submissions  ──► profile, SIC sector, period end, primary document
   data.sec.gov/companyfacts ──► quarter values (3-month facts, or YTD − prior YTD)
   filing XBRL instance      ──► revenue lines / segments (dimensional facts that add up to revenue)
   filing HTML               ──► MD&A paragraphs per line item, Item 1 Business introduction
                                             ▼
   pipeline/sankey.py  nodes + links + label lines (share of parent, Y/Y, Q/Q, Δ = scale + mix)
   pipeline/analysis.py rule-based paragraphs and "what changed" bullets
   pipeline/sectors.py calendar-quarter sums by sector and SIC industry
                                             ▼
   _site/data/*.json  ──►  web/ (sankey.js lays out and draws; app.js routes pages)
```

| Path | Purpose |
| --- | --- |
| `pipeline/sec.py` | HTTP client (User-Agent, ≤ 8 requests/s, retries; fixture mode for tests) |
| `pipeline/scan.py` | new filings from the Atom feed and daily form index |
| `pipeline/facts.py` | XBRL concept lists and quarterisation |
| `pipeline/dims.py` | revenue breakdown from the filing's XBRL instance |
| `pipeline/model.py` | one consistent statement per quarter (derived operating profit, cost items, cash bridge) |
| `pipeline/sankey.py` | chart spec in the standard format (profit view, loss "funding" view) |
| `pipeline/text.py` | MD&A note matching and Item 1 introduction |
| `pipeline/build.py` | `run` (scan + process + render) and `render` |
| `web/sankey.js` | layout (column spacing from label widths, collision-free labels), SVG, canvas/PDF export |
| `web/app.js` | pages: latest filings, company (quarters, compare, notes, history), sector, industry, method |
| `scripts/build_site.py` | copies `web/` and data into `_site/` (or a single inlined page with `--inline`) |

## Run locally

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your.email@example.com"
python -m pipeline.build run --store store --out _site/data --backfill-days 2 --max-filings 200
python scripts/build_site.py --data _site/data --out _site
python -m http.server -d _site 8000        # open http://localhost:8000
```

Offline, with the bundled fixtures (Apple, Meta, CoreWeave, Berkshire Hathaway):

```bash
SEC_FIXTURES=tests/fixtures SEC_USER_AGENT="test test@example.com" \
  python -m pipeline.build run --store /tmp/store --out /tmp/site/data
python scripts/build_site.py --data /tmp/site/data --out /tmp/site
python -m pytest tests/test_pipeline.py            # pipeline tests
python tests/e2e.py /tmp/site --shots /tmp/shots   # browser test (needs: pip install playwright; playwright install chromium)
```

## Definitions

- Percentages on labels: each item's share of the node it splits from or flows into.
- Y/Y and Q/Q: change against the same quarter a year earlier and the previous quarter; `n/m` when either value is ≤ 0.
- Operating profit is derived as revenue minus total costs when a company does not tag it (noted in the footer).
- Quarterly cash flows, and every fourth quarter from a 10-K, are year-to-date minus the prior year-to-date.
- Working capital & other = operating cash flow minus net earnings and the listed non-cash items.
- FCF = operating cash flow minus capital expenditures (companies' own FCF definitions may differ).
- Comparison view: band width is the current quarter; the dark strip is the increase since the previous quarter.
  `scale = (parent_now − parent_prior) × child_prior / parent_prior`, `mix = parent_now × (share_now − share_prior)`.

## Limits

- Banks, insurers, REITs and funds whose statements do not run from revenue to net income may be skipped or shown
  coarsely; custom XBRL tags fall into "Other operating costs".
- Notes appear only when the MD&A has a heading or sentence that names the line; otherwise the panel says so.
- Amended filings (10-Q/A, 10-K/A) are ignored.
- Data is as filed with the SEC; this is not investment advice.
