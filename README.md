# Filing Flows

A static website that scans SEC EDGAR every hour for new 10-Q and 10-K filings and draws each one as an
income-statement and cash-flow Sankey in the *earnings-sankey* standard format: revenue lines → revenue →
gross profit / costs → operating profit → pre-tax → tax, minority interests, net earnings → operating cash flow.

- **Every filing** with XBRL revenue and net income gets a chart (latest three quarters kept).
- **Earnings releases (8-K, Item 2.02)** are read too, so a quarter appears days or weeks before its 10-Q/10-K.
  The press release tables are read by fixed rules, checked against the previous quarter's XBRL and required to
  reconcile; the chart is marked *preliminary* and is replaced automatically when the 10-Q/10-K is filed.
- **Starred companies** (`config/starred.txt`) keep eight quarters and are back-filled from their filing history.
- **Sector and industry charts** add up every company whose fiscal quarter ends in the same calendar quarter
  (SIC-code groups; the ten largest companies appear by name).
- **Click any node** to read what the company wrote about that line in the same filing (MD&A paragraphs, quoted
  verbatim). Company pages open with the first paragraphs of Item 1 *Business* from the latest 10-K.
- **Analysis paragraphs** are written by fixed rules from the numbers. No language model is used anywhere.
- **Comparison views**, vs the previous quarter and vs the same quarter a year earlier: the same chart with a dark
  strip on every band that grew and a `Δ = scale + mix` line per node.
- **History on first sight**: when a company's earnings 8-K is found, its last five 10-Q/10-K filings are fetched
  too (it then keeps six quarters), so comparisons and the quarter-by-quarter view work straight away.
- **Segments from releases**: revenue by business unit or product is read from the release when a table of rows
  adds up to total revenue; its other columns supply Q/Q and Y/Y when they match the earlier quarters in XBRL.
- **Export** PNG, JPG or PDF. Exports contain the chart only; the notes panel and note markers stay on screen.
- **Alerts for readers**: sign up with an e-mail code (no password), follow companies or sectors, receive each new
  chart with its analysis by e-mail or as a notification in the Android app.

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

## New charts as ready-to-post X threads (by e-mail)

Each new company quarter becomes a short X thread: headline figures with the chart (and the year-ago comparison
chart), the company in its own words (10-K Item 1, quoted), the analysis, a quote from the filing about revenue,
and the source (form, filing date, accession number). Everything comes from the site data; no language model
writes any of it. Every post fits X's 280-character limit.

By default the threads are **e-mailed** (one e-mail per hourly run that finds new charts): each post sits in its
own block with its character count, the first post has an "Open in X" link that pre-fills it, and the chart images
are attached. Post by hand; nothing is published automatically.

Set up (Gmail):

1. Turn on 2-Step Verification for the Google account, then create an app password at
   myaccount.google.com/apppasswords (name it "Filing Flows").
2. Add repository secrets `MAIL_USERNAME` (the Gmail address) and `MAIL_PASSWORD` (the 16-character app password,
   without spaces). Optional: `MAIL_TO` to send to another address.

Every company page also shows the quarter's thread with Copy buttons and an **Email me this thread** button. The
site is static, so the button opens a pre-filled GitHub issue; when you (the repository owner) press Create, the
workflow `.github/workflows/email-thread.yml` e-mails that quarter's thread with both charts and closes the issue.
Issues opened by anyone else are ignored.

Until the secrets exist, each run prints the threads it would send in the Actions log
("Send new charts as X threads" step).

Posting straight to X instead: set `"mode": "api"` in `config/x.json` and add `X_API_KEY`, `X_API_SECRET`,
`X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` (an app with Read and write permission at console.x.com). X's API is
pay-per-use: $0.015 per post, $0.20 per post with a link (docs.x.com/x-api/getting-started/pricing).

`config/x.json`

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | master switch |
| `mode` | `"email"` | `"email"` (send to yourself) or `"api"` (post through the X API) |
| `scope` | `"all"` | `"all"` or `"starred"` (only companies in `config/starred.txt`) |
| `min_revenue` | `1000000000` | only quarters with at least this revenue (USD); `0` for every company |
| `max_per_run` | `4` | threads per hourly run |
| `max_age_days` | `3` | skip filings older than this |
| `preliminary` | `true` | include quarters read from 8-K earnings releases |
| `include_link` | `false` | add a link to the chart page in the last post |
| `images` | `["standard", "year_ago"]` | charts attached to the first post |

A company quarter is sent once: when the 10-Q/10-K replaces an 8-K chart that was already sent, it is not sent again.

## Accounts and alerts (website + Android app)

Readers sign up with their e-mail address only: the site sends a 6-digit code, they type it in, done (no password).
On the **Alerts** page they choose companies (or press **☆ Follow** on any company or sector page), sectors, "every
company above $X billion of revenue" or the starred list, and how often: as soon as a chart is out (checked hourly)
or one digest a day. Each alert e-mail carries the chart itself, the headline figures, the analysis, what changed
against the year-ago quarter, a quote from the filing, and links to the interactive chart and the filing.
Every e-mail has an unsubscribe link; the Alerts page also has **Delete my account**.

- **Preliminary, then final.** A quarter read from an 8-K earnings release is sent as *preliminary*. When the
  10-Q/10-K replaces it, the final version is sent too (setting on by default, can be turned off), marked *final*,
  with how the release compared with the filing ("Revenue and net earnings match the release. Revised: operating cash
  flow $1.6B in the release, $1.2B as filed"). The company page shows the same label and comparison.
- **✉ Email me** on every company page sends the quarter on screen (or all quarters, on the "All quarters" view) to
  the reader's own address, alerts on or off: old quarters included, as far back as the site keeps them (three
  quarters for most companies, six after an 8-K brought in the history, eight for starred ones). Signed-out readers
  sign in first and the request goes through afterwards. Up to 30 reports a day per reader; the Alerts page lists
  recent requests and whether they were sent. They go out within about 10 minutes (`.github/workflows/requests.yml`),
  or within a minute or two with the optional wake-up below.

Until the steps below are done the site simply hides the sign-up box and the Follow buttons.

### 1. Supabase (accounts and settings; free plan is enough)

1. Create a project at supabase.com. **SQL Editor** → paste `supabase/schema.sql` → Run.
2. **Authentication → Emails → SMTP Settings**: enable custom SMTP so codes can reach any address (the built-in
   sender only mails your own team): host `smtp.gmail.com`, port `465`, user = your Gmail address, password = the
   Gmail app password (the same one as `MAIL_PASSWORD`), sender name `Filing Flows`.
3. **Authentication → Emails → Templates**: in both **Magic Link** and **Confirm signup**, set the subject to
   `Your Filing Flows sign-in code` and the body to `supabase/email-otp-template.html` (it shows `{{ .Token }}`).
4. **Authentication → URL Configuration → Site URL**: your site address, e.g. `https://<user>.github.io/<repo>/`.
5. **Project Settings → API Keys**: copy the project URL, the *publishable* key (`sb_publishable_…`, or the legacy
   `anon` key) and the *secret* key (`sb_secret_…`, or the legacy `service_role` key).

### 2. GitHub settings (Settings → Secrets and variables → Actions)

| Where | Name | Value |
| --- | --- | --- |
| Variables | `SUPABASE_URL` | `https://<project>.supabase.co` |
| Variables | `SUPABASE_ANON_KEY` | the publishable key (safe to publish: every row is protected by row-level security) |
| Secrets | `SUPABASE_SERVICE_KEY` | the secret key (only the alert sender uses it) |
| Secrets | `MAIL_USERNAME`, `MAIL_PASSWORD` | already there if X threads are e-mailed to you |

Optional variables: `CONTACT_EMAIL` (shown on the privacy and terms pages; otherwise they point to GitHub issues), `MAIL_FROM` (e.g. `Filing Flows <alerts@yourdomain.com>`), `SMTP_HOST` / `SMTP_PORT` (another
provider, e.g. Resend: `smtp.resend.com`, `465`, user `resend`, password = API key), `MAIL_DAILY_LIMIT` (default 400),
`DIGEST_HOUR_UTC` (default 22, about 6 pm in New York), `SITE_URL` (a custom domain).

After the next hourly run the sign-up box appears on the home page, and the **alerts** job of the workflow sends the
e-mails right after each deploy. Upload `.github/workflows/requests.yml` as well for the **Email me** button.

Faster **Email me** (optional): Supabase can wake the GitHub workflow the moment a reader asks. Create a fine-grained
GitHub token (Settings → Developer settings → Fine-grained tokens; only this repository; permission *Contents: Read and
write*), enable **Database → Extensions → pg_net**, then run in the SQL Editor:

```sql
select vault.create_secret('github_pat_…', 'github_dispatch_token');
select vault.create_secret('<user>/<repo>', 'github_repo');
```

Renew the token before it expires; without it the 10-minute check still sends everything. Gmail sends about 500 messages a day, sign-in codes included; for more readers use
a provider with your own domain (Resend, Postmark, Amazon SES) through `SMTP_HOST`. Supabase limits sign-in e-mails to
30 an hour by default (Authentication → Rate Limits).

Each chart reaches a reader once (the 8-K version and the final 10-Q/10-K version count as two). Charts filed before a
reader signed up are not sent; **Email me** covers those.

### 3. Android app

`android/` is a small Kotlin app: the site in a full-screen WebView (same pages, same sign-in, exports saved to
Downloads) plus a background check every 30 minutes that reads `data/index.json` and shows a notification for each
new chart that matches what the reader follows (tap → that chart), including the final 10-Q/10-K after an 8-K chart
unless that setting is off. It needs no server of its own.

- **Build on GitHub** (nothing to install): upload `android/` and `.github/workflows/android.yml`. The **Android app**
  workflow builds `filing-flows.apk` and publishes it at `https://github.com/<you>/<repo>/releases/tag/android`; the
  Alerts page links there. Open that page on the phone, download, allow "install unknown apps" for the browser.
- **Keep updates installable**: without a signing key each build has a new signature and the phone refuses to update
  over the previous one (uninstall first). To fix that once: in Android Studio, **Build → Generate Signed App Bundle or
  APK → APK → Create new** keystore (alias `filingflows`), then in PowerShell
  `[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\filingflows.jks")) | Set-Clipboard` and add secrets
  `ANDROID_KEYSTORE_BASE64` (paste), `ANDROID_KEYSTORE_PASSWORD`, and `ANDROID_KEY_PASSWORD` if it differs. Keep the
  .jks file safe; never upload it to the repository.
- **Google Play**: with the signing-key secrets set, the workflow also produces `filing-flows.aab` (artifact
  *filing-flows-aab-for-google-play*), the bundle Play Console asks for. The 512 px icon and the 1024 × 500 feature
  graphic are in `android/store/`; the privacy policy is the site's `privacy.html`.
- **Build locally**: open `android/` in Android Studio (Meerkat Feature Drop or newer), Run. The site address is
  `filingflows.siteUrl` in `android/gradle.properties`.

Targets API 36 (required on Google Play since Aug 31, 2026) and runs on Android 8.0+ (API 26). Notifications need the Android 13+ permission prompt, shown the
first time the reader follows something in the app.

### Running parts on your own computer instead

- **Alert e-mails from your laptop** (Windows): follow the comments at the top of `scripts/alerts-laptop.ps1`
  (Python, `pip install -r requirements.txt playwright`, `playwright install chromium`, fill in
  `scripts/alerts.env`, register the 10-minute task with `schtasks`). Leave `SUPABASE_SERVICE_KEY` out of GitHub so the
  two never both send. The computer must be on and online at the scheduled times.
- **Supabase itself on your laptop**: the same `schema.sql` works on self-hosted Supabase (Docker; see
  supabase.com/docs/guides/self-hosting/docker). The website and the app must reach it over HTTPS from anywhere, so it
  also needs a fixed public address, e.g. a Cloudflare named tunnel on your own domain; then set `SUPABASE_URL` to that
  address. While the laptop sleeps nobody can sign in or change settings (charts keep working). The hosted free plan
  avoids that (it pauses a project after about a week of inactivity; the hourly alert check queries it every hour).

## How it works

```
EDGAR "getcurrent" feed (10-Q, 10-K, 8-K) ─┐
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
| `pipeline/release.py` | 8-K earnings releases: statement tables → quarter values (units, signs, YTD cash flow, reconciliation) |
| `pipeline/social.py` | X threads: candidates, text (fits 280 characters), chart PNGs via headless Chromium, e-mail or X API |
| `pipeline/notify.py` | reader alerts and **Email me** requests: matches charts to subscriptions, e-mails chart + analysis, records deliveries |
| `supabase/schema.sql` | accounts, report requests, row-level security, unsubscribe and delete-account functions (safe to run again) |
| `android/` | Kotlin WebView app with background checks and notifications (built by `.github/workflows/android.yml`) |
| `pipeline/text.py` | MD&A note matching and Item 1 introduction |
| `pipeline/build.py` | `run` (scan + process + render) and `render` |
| `web/sankey.js` | layout (column spacing from label widths, collision-free labels), SVG, canvas/PDF export |
| `web/app.js` | pages: latest filings, company (quarters, compare, notes, history), sector, industry, method, alerts |
| `scripts/build_site.py` | copies `web/` and data into `_site/` (or a single inlined page with `--inline`) |

## Run locally

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your.email@example.com"
python -m pipeline.build run --store store --out _site/data --backfill-days 2 --max-filings 200
python scripts/build_site.py --data _site/data --out _site
python -m http.server -d _site 8000        # open http://localhost:8000
```

Offline, with the bundled fixtures (Apple, Meta, CoreWeave, Berkshire Hathaway, plus two fictional companies that
exercise the 8-K reader):

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
