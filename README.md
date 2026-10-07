# Filing Flows

A static website that scans SEC EDGAR every 15 minutes for new 10-Q and 10-K filings and draws each one as an
income-statement and cash-flow Sankey in the *earnings-sankey* standard format: revenue lines → revenue →
gross profit / costs → operating profit → pre-tax → tax, minority interests, net earnings → operating cash flow.

- **Every filing** with XBRL revenue and net income gets a chart (the latest seven quarters and two fiscal years are kept).
- **Earnings releases (8-K, Item 2.02)** are read too, so a quarter appears days or weeks before its 10-Q/10-K.
  The press release tables are read by fixed rules, checked against the previous quarter's XBRL and required to
  reconcile; the chart is marked *preliminary* and is replaced automatically when the 10-Q/10-K is filed.
- **Starred companies** (`config/starred.txt`) keep eight quarters and are back-filled from their filing history.
- **Sector and industry charts** add up every company whose fiscal quarter ends in the same calendar quarter
  (SIC-code groups; the ten largest companies appear by name).
- **Free cash flow**: operating cash flow splits into capital expenditures and free cash flow. When capex is larger
  than operating cash flow, all of it goes to capex and the gap enters as *Negative free cash flow* (paid from cash or
  financing), so no band ever has a negative width.
- **Company-reported free cash flow** (`pipeline/reported.py`): companies define free cash flow differently (Meta
  also subtracts finance-lease principal; Micron nets asset sales and government incentives). For each quarter the
  free cash flow reconciliation is read from the company's earnings release (8-K, Exhibit 99.1) and accepted only
  when its operating cash flow equals SEC's figure for that quarter and its own lines add up. Then the chart draws the
  company's definition, labelled *company-reported*, with each item it subtracts as its own band (the year-ago
  quarter on the same definition; trends only line up quarters on the same definition). When it cannot be drawn
  (negative, or the table cannot be read), the chart keeps *Free cash flow (OCF − capex)* and names the company's
  figure on the node, in the data checks and in the footer. Latest quarters stored earlier are checked 30 per scan.
  Readers choose under **Alerts → Company-reported or calculated figures** (`subscriptions.fcf_basis`; run
  `supabase/schema.sql` again to add the column): *company-reported* (`noted`: the company's figures, and a chart
  drawn by the formula says so and why — no earnings release found, not in the release, did not match SEC data, or
  not checked); *company-reported first, then calculated* (`company`, the default: the same without the note); or
  *calculated throughout* (`ocf`: free cash flow = OCF − capex and revenue = what the revenue lines add up to, for
  every company, with the company's own figures named on the chart). The site data carries what each choice changes
  (`fcf_alt`: the quarter calculated throughout; `fcf_note`: the note), and company pages and that reader's e-mails
  show the one they chose. Full fiscal years always use the formula for free cash flow.
- **Total revenue and the revenue lines**: revenue is the income statement's total (`us-gaap:Revenues`) when the
  company tags it, even when another tag is larger (Vistra: $4.40B of revenue from contracts with customers, $4.02B of
  total revenues after −$0.38B of other revenues such as hedging results). Revenue lines that add up to contract
  revenue rather than the total flow into a *Revenue from contracts with customers* node, which splits into revenue and
  *Other revenues (net loss)*; when other revenues are positive they enter as one more line.
- **Cash-flow bridge figures** come from the cash-flow statement's tags: when the income statement tags a narrower
  D&A (Vistra: $445M) than the cash-flow statement adds back ($645M, nuclear fuel amortization included), the tag
  reported only year to date (the cash-flow statement's) is used. Stored quarters are read again a few companies per run.
- **Data checks** (`pipeline/checks.py`): periods of unusual length, revenue jumps, odd margins, cash flow out of
  scale, and definitions that differ from the company's are listed under every chart; probable errors are marked on
  the chart, the owner's e-mail says to check before posting, and automatic X posting holds them. Every chart and
  e-mail carries a disclaimer that figures are read by fixed rules and can contain errors.
- **Every node says where its number comes from**: the reported line as printed in the filing and its XBRL tag
  (and, for a quarter read from year-to-date figures, that it is year-to-date minus the prior year-to-date), the row
  of the earnings release, or the calculation (for example operating expenses = gross profit − operating profit).
  Under it is the full citation (company, form, period, filing date, accession number) with links to the filing
  itself, SEC's inline XBRL viewer, SEC's XBRL data for that tag across all periods, and the filing index.
  Quarters stored before this was added get their source lines filled in from SEC company facts during later scans.
- **Drag and zoom** (optional, Alerts → On company pages; off by default): hold the left mouse button on an empty part of
  a chart to move it (the pointer turns into a hand), use the wheel to zoom around the pointer, double-click or *Reset
  view* to see it whole. Only the on-screen view changes; exports are the whole chart (`subscriptions.chart_drag_zoom`).
- **Click any node** for a small chart of that line over the last five quarters on file (amount as columns, change
  against a year earlier and against the previous quarter as lines; hover a quarter for its figures), and for what the company wrote about that line in the same filing (MD&A paragraphs, quoted
  verbatim). Company pages open with the first paragraphs of Item 1 *Business* from the latest 10-K; a company
  without a 10-K yet (a recent listing) gets the "About …" paragraph of its earnings release, or else the description
  of business in Note 1 of its 10-Q, labelled with where it came from.
- **Analysis paragraphs** are written by fixed rules from the numbers. No language model is used anywhere.
- **Comparison views**, vs the previous quarter and vs the same quarter a year earlier: the same chart with a dark
  strip on every band that grew and a `Δ = scale + mix` line per node. **Show decreases** (off by default) also draws
  what each line lost as a hatched area with a dashed outline beside its band; signed-in readers' choice is saved to
  their account and used for their e-mailed charts too.
- **History on first sight**: when a company first appears (a 10-Q, 10-K or earnings 8-K), its last five 10-Qs and
  last two 10-Ks are fetched too, so comparisons and the quarter-by-quarter view work straight away. Companies stored
  before this default get it a few at a time on later runs.
- **Full fiscal years**: each 10-K also gets a full-year chart (pill *FY25 · full year* on the company page, compared
  with the year before), next to its fourth quarter.
- **Compare any two periods** (readers who switch it on under Alerts): a ⇄ button on company pages opens a table of
  every quarter and fiscal year SEC's XBRL data has for the company (from 2009–2011 on, up to 18 years). Tick two
  quarters or two fiscal years; the request workflow reads both from SEC and draws the comparison Sankey within a few
  minutes (the browser cannot read SEC itself). The result stays in the reader's list on that company's page.
- **Search every SEC company**: the search box also lists companies the site has not drawn yet (SEC's ticker list,
  `data/companies.json`). Their page offers **Build its charts**: the next scan fetches the default five 10-Qs and
  two 10-Ks and the page fills in by itself.
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
5. The workflow then runs every 15 minutes (`4,19,34,49 * * * *`; GitHub often starts scheduled runs 5–20 minutes late
   and skips some when busy: see *Scan more often* below). The site is at `https://<user>.github.io/<repo>/`.

State (which filings were seen, the per-company data) lives on a `data` branch that the workflow rewrites as a
single commit each run, so `main` history stays clean. Delete the branch to start over.

GitHub disables scheduled workflows in public repositories after 60 days without activity on the default branch;
re-enable it from the Actions tab or push any commit.

### Scan more often

The workflow is scheduled every 15 minutes, but GitHub starts scheduled runs late (often 5–20 minutes) and skips some
when it is busy. For runs on time, let Supabase's clock start them (free plan included):

1. A fine-grained GitHub token (Settings → Developer settings → Fine-grained tokens): only this repository, permission
   *Contents: Read and write*. The token from the optional wake-up below works too.
2. Supabase → **Database → Extensions**: enable `pg_net` and `pg_cron`. Run `supabase/schema.sql` again (it adds the
   function `github_dispatch`, which only the database itself may call).
3. SQL Editor (leave out the first two lines if the wake-up secrets already exist):

```sql
select vault.create_secret('github_pat_…', 'github_dispatch_token');
select vault.create_secret('<user>/<repo>', 'github_repo');
select cron.schedule('filing-flows-scan', '*/10 * * * *', $$select public.github_dispatch('scan')$$);
```

Runs started this way show as *repository_dispatch* on the Actions page. Stop with
`select cron.unschedule('filing-flows-scan');`. A run that is still busy when the next one is due simply makes the next
one wait. Faster scans mostly help earnings releases (8-K), which are read straight from the press release; a 10-Q/10-K
still waits for SEC's XBRL data, which can lag the filing by hours (retried every scan for up to 24 hours). Readers on
"as soon as a chart is out" get one e-mail per run that finds new charts for them.

### Star a company

Add its ticker to `config/starred.txt` (one per line) and commit. The next run back-fills its last eight
10-Q/10-K filings. The home page links to the file when the site runs on GitHub Pages.

### Your own domain and server

GitHub Pages keeps running; your own server is added next to it.

1. Repository variable `SELF_HOST` = `true`: every scan also pushes the built site to the branch `site` (newest copy only).
2. The server pulls that branch every few minutes and serves it as static files, e.g. with Caddy (automatic HTTPS):
   `git clone --depth 1 --branch site https://github.com/<you>/<repo>.git /srv/filing-flows`, then a cron line
   `*/5 * * * * cd /srv/filing-flows && git fetch -q --depth 1 origin site && git reset -q --hard FETCH_HEAD`.
   The server needs no GitHub key: it only reads the public repository.
3. Repository variable `SITE_URL` = `https://your-domain/`: links in e-mails, X threads and the Android app use it.
   In Supabase (Authentication → URL Configuration) set the Site URL to it and add `https://your-domain/**` to the
   redirect URLs.
4. Sending from your domain instead of a personal mailbox (e.g. Resend): `SMTP_HOST` = `smtp.resend.com`,
   `SMTP_PORT` = `465`, `MAIL_FROM` = `Filing Flows <alerts@mail.your-domain>` (variables), `MAIL_USERNAME` = `resend`,
   `MAIL_PASSWORD` = the API key and `MAIL_TO` = where your own copies go (secrets); the same SMTP settings in
   Supabase → Authentication → Emails → SMTP Settings for the sign-in codes.

## The owner's daily report and ready-to-post X threads (by e-mail)

Each new company quarter becomes a short X thread, numbered 1/7, 2/7 …:

1. **Headline and charts**: ticker, company, quarter; which filing and when (`10-Q filed Jul 31, 2026 · quarter ended
   Jun 27`); revenue, margins, net earnings, operating cash flow; and what the attached images show (*Charts: Q3 FY26
   revenue to cash; vs Q3 FY25 (dark = growth)*).
2. **What the company does**: its SEC industry and sector, and where the quarter's revenue came from (each segment or
   product line with its amount and share).
3. **The company in its own words**: the opening of Item 1 of its 10-K (or its earnings release / 10-Q), quoted, with
   where it is from.
4. **Analysis**: one post per paragraph (revenue, profit, cash).
5. **From the filing**: what the 10-Q/10-K says about revenue or its largest line, quoted.
6. **Source**: company, form, period, filing date, accession number.

Everything comes from the site data; no language model writes any of it. Every post fits X's 280-character limit.

**Daily report (default).** Every morning at 8:00 (owner's time zone; set on the `#owner` page) one e-mail carries every
filing since the last report, largest first: a table of contents, then for each company the filing, what the company
does, its description, both charts with what they show, the analysis, what changed and the X thread post by post (with
an "Open post 1 in X" link). Companies below the owner's revenue minimum (default $1B a quarter) are left out, unless
the owner picks **the full report** (every company that filed: the largest 20 in full, the rest listed). It goes to
the addresses in Supabase's `site_owners` table (else `MAIL_TO`, else `MAIL_USERNAME`). Mornings with nothing new send
nothing. The scan's sending step sends it, so it arrives with the first scan after 8:00 (within a few hours at most;
see *Scan more often* for an on-time clock). Nothing is published automatically.

Set up (Gmail):

1. Turn on 2-Step Verification for the Google account, then create an app password at
   myaccount.google.com/apppasswords (name it "Filing Flows").
2. Add repository secrets `MAIL_USERNAME` (the Gmail address) and `MAIL_PASSWORD` (the 16-character app password,
   without spaces). Optional: `MAIL_TO` to send to another address.

**Owner tools** (`https://<you>.github.io/<repo>/#owner`), hidden from readers. With accounts switched on, only
addresses on the owner list can use them: run `insert into public.site_owners (email) values ('you@example.com');` once
in the Supabase SQL Editor (after `supabase/schema.sql`) and sign in with that address. The list cannot be read through
the site.

- **X thread on company pages** (per browser): under each quarter, the filing, what each image shows with **Save PNG**,
  every post with its role and **Copy**, and **Email me this thread**.
- **Settings** (saved in Supabase, table `owner_settings`, readable and changeable by the owner only):
  - *Email me this thread*: **straight to my inbox** (default; a queued request that `requests.yml` sends within a
    couple of minutes, both chart PNGs attached) or **open a GitHub issue** (the older way: press Create, and
    `.github/workflows/email-thread.yml` sends it; issues opened by anyone else are ignored).
  - *Daily report*: on/off, the hour (your browser's time zone is saved with it), and which companies: those over the
    revenue minimum, or every company that filed (the full report).
  - *Reader version* (on the owner's **Alerts** page): off by default, so the owner gets only the owner report. On: the
    owner also gets the reader e-mails their own alert settings ask for, and "Send a daily report now" sends both.
  - *Also e-mail new X threads right after each scan* (off by default; the behaviour before the daily report).
- **Send a daily report now**: pick a filing date, today or one of the five days before, and that day's report arrives
  within a few minutes.

Without accounts the same settings can go in `config/x.json` (`daily_on`, `daily_hour`, `tz`, `min_revenue`,
`instant_threads`, `daily_scope`: `"min_revenue"` or `"all"`). Until the mail secrets exist, each run prints the threads it would send in the Actions log.

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
| `max_per_run` | `4` | threads per run (with *instant* threads or the X API) |
| `max_age_days` | `3` | skip filings older than this |
| `preliminary` | `true` | include quarters read from 8-K earnings releases |
| `include_link` | `false` | add a link to the chart page in the last post |
| `images` | `["standard", "year_ago"]` | charts attached to the first post |
| `headline_tag` | `"#earnings"` | hashtag in the first post, in place of the word "results" (`""`: no hashtag there) |
| `hashtags` | `["#stocks", "#investing"]` | hashtags on the last post, as many as fit (`[]`: none) |

A company quarter is sent once: when the 10-Q/10-K replaces an 8-K chart that was already sent, it is not sent again.

## Accounts and alerts (website + Android app)

Readers sign up with their e-mail address only: the site sends a 6-digit code, they type it in, done (no password).
On the **Alerts** page they choose companies (or press **☆ Follow** on any company or sector page), sectors, "every
company above $X billion of revenue" or the starred list, and how often: a **daily report** every morning at 8:00 their
own time (the default; the hour can be changed, the time zone comes from their browser) or as soon as a chart is out
(checked every 15 minutes). The daily report covers the companies they follow (the default) or, if they choose,
**every company that filed** (the full report: the ones they follow first, the first 15 in full, the rest listed with
links, at most 150 in the list and the rest on the site). The daily report lists every company first, then for each one the filing and its date, what
the company does (industry, revenue by line, its own description), the chart, the analysis and what changed. Each alert
e-mail carries the chart itself, the headline figures, the analysis, what changed against the year-ago quarter, a quote
from the filing, and links to the interactive chart and the filing.
- **Daily report of any day** (home page): pick today or one of the five days before and **Email me the report**:
  that day's filings for the companies the reader follows (every company above $1B when they follow none yet), or
  every filing of that day for readers who chose the full report.
  Days without filings (weekends) are greyed out.
Every e-mail has an unsubscribe link; the Alerts page also has **Delete my account**.

- **What each e-mail holds** (Alerts → *In each e-mail*). Always this quarter's chart (tap it for the interactive
  one), the analysis and what changed. Optional: the chart compared with the previous quarter, compared with the same
  quarter a year earlier (optionally with decreases hatched), **Detail** (every line of the chart with its change
  against a year earlier and the previous quarter, instead of only the three main changes), and a **history** chart (revenue, operating profit, net earnings and operating cash flow for
  every quarter on file, also shown on the site's "All quarters" view). Attached files: the charts as **PNG** (default)
  or **JPG** at 2400 px, and a **PDF report** (on by default): the company profile from its 10-K (also at the top of
  each company in the e-mail), every chart as
  vector graphics, the analysis, what changed, the filing's own words and the filing details. An e-mail stays under
  15 MB (`MAIL_MAX_BYTES`); files that do not fit are left out with a note.

- **Compare any two periods** (Alerts → *On company pages*, off by default): see the feature list above. At most
  20 comparisons a day per reader; needs `requests.yml` and the `SEC_USER_AGENT` secret, which it shares with the scan.
- **Build a company** from the search: at most 10 a day per reader, and at most 25 companies per scan for all readers
  together (the rest wait for the next scan). `requests.yml` starts the scan straight away (it has `actions: write`
  for that); otherwise the next scan picks it up. The site owner can skip the sign-in: **Actions → Scan EDGAR
  and publish → Run workflow → companies** = `MS, GS` (tickers or CIKs), or add tickers to `config/starred.txt`.

- **Preliminary, then final.** A quarter read from an 8-K earnings release is sent as *preliminary*. When the
  10-Q/10-K replaces it, the final version is sent too (setting on by default, can be turned off), marked *final*,
  with how the release compared with the filing ("Revenue and net earnings match the release. Revised: operating cash
  flow $1.6B in the release, $1.2B as filed"). The company page shows the same label and comparison.
- **✉ Email me** on every company page sends the quarter or fiscal year on screen (or all quarters, on the "All quarters" view) to
  the reader's own address, alerts on or off: old quarters included, as far back as the site keeps them (seven
  quarters and two fiscal years for most companies, eight quarters and three years for starred ones). Signed-out readers
  sign in first and the request goes through afterwards. Up to 30 reports a day per reader; the Alerts page lists
  recent requests and whether they were sent. They go out within about 10 minutes (`.github/workflows/requests.yml`),
  or within a minute or two with the optional wake-up below.

Until the steps below are done the site simply hides the sign-up box and the Follow buttons.

### 1. Supabase (accounts and settings; free plan is enough)

1. Create a project at supabase.com. **SQL Editor** → paste `supabase/schema.sql` → Run. Run it again after each
   update of this repository: it only adds what is new (for example the e-mail content options) and keeps the data.
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
`DIGEST_HOUR` / `DIGEST_TZ` (default 8 and `America/New_York`: the daily report time for readers whose own is not saved
yet; each reader's browser time zone is saved with their alerts), `SITE_URL` (a custom domain).

After the next run the sign-up box appears on the home page, and the **alerts** job of the workflow sends the
e-mails right after each deploy. Upload `.github/workflows/requests.yml` as well for **Email me**, **Compare any two
periods** and **Build its charts**.

Faster **Email me**, comparisons and company builds (optional): Supabase can wake the GitHub workflows the moment a
reader asks. Create a fine-grained
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

`android/` is a Kotlin app built around native screens, with the site's pages only where they are interactive:

- **Following** and **Latest** tabs are native lists of charts (ticker, quarter, form, revenue and Y/Y, a badge for 8-K
  preliminary or final). Latest has search, which also lists companies the site has no chart for yet (SEC's list,
  `data/companies.json`, kept for a day); opening one shows the site's **Build its charts** page. Both lists pull to
  refresh and keep working offline from a cached `data/index.json`.
- **Home-screen widget** with the three newest charts of what the reader follows (or the newest overall), each one tap
  from its chart; **launcher shortcuts** (long-press the icon) for Following, Latest and Alerts.
- A **background check** every 30 minutes (WorkManager) shows a notification for each new chart that matches what the
  reader follows (tap → that chart), including the final 10-Q/10-K after an 8-K chart unless that setting is off.
- A chart opens under a native toolbar (back, share link); the page's **Share** button hands the chart image to the
  Android share sheet and exports are saved to Downloads. **Sectors** and **Alerts** (sign-in, settings) are the
  site's pages; inside the app the site hides its own header. Links to the site (for example in alert e-mails) can
  open in the app.
- **Money** tab (app only, not on the website): personal bookkeeping kept on the phone, no sign-in and nothing sent
  anywhere (`files/books.json`; Android's own backup includes it). Every entry is a journal entry whose debits equal
  its credits, entered as *Spending*, *Income*, *Transfer* (saving, investing, paying a card, borrowing, repaying),
  *Opening balance* or a free *Journal entry* with any number of lines; each form shows the entry it will record. For a
  month, a year or all time the tab shows:
  - the **journal** (date, accounts, debit and credit columns; tap an entry to edit or delete it);
  - **T-accounts** for every account with activity (balance brought forward, debits left, credits right, totals, balance);
  - a **Sankey** of income into spending (red) and savings (green), or savings used when spending is larger (slate),
    each line with its share and the change against the previous month or year;
  - the **income statement**, **balance sheet** (assets = liabilities + equity, checked) and **cash flow statement**
    (direct method: cash & bank accounts; operating, investing and financing by the account on the other side; plus
    the reconciliation from savings to operating cash flow), the first two with the previous period alongside.
  Accounts (add, rename, archive; each balance-sheet account's type decides its cash-flow section), a currency symbol,
  an example month to explore, CSV export of the journal, and a JSON backup to restore on another phone.

It needs no server of its own. These native parts are also what keeps Google Play from treating it as a website
wrapper (Minimum functionality / Webview policies): show them in the store screenshots and description.

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
                                             │  retried every scan until XBRL facts appear (up to 24 h)
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
| `pipeline/owner.py` | the owner's daily report, owner settings, X threads on request |
| `pipeline/notify.py` | reader alerts and **Email me** requests: matches charts to subscriptions, e-mails chart + analysis, records deliveries |
| `pipeline/custom.py` | readers' requests answered from SEC: any two periods as one comparison chart; companies to build in the next scan |
| `supabase/schema.sql` | accounts, report requests, row-level security, unsubscribe and delete-account functions (safe to run again) |
| `android/` | Kotlin app: native chart lists, home-screen widget, shortcuts, background checks and notifications; chart pages in a WebView (built by `.github/workflows/android.yml`) |
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
- Capital expenditures: the company's own cash-flow line, from SEC's standard XBRL tags (the general ones, then those
  oil & gas, real-estate and utility filers use; the largest when several are tagged, so a small sub-line is never
  taken for the total); when none is tagged, the filing's own XBRL is searched for the line by its printed name
  ("Purchases of property and equipment", "Capital expenditures" ...), which also finds company-specific tags.
  Clicking the Capex node shows the line and the tag used.
- FCF = operating cash flow minus capital expenditures; asset-sale proceeds and finance-lease repayments are not netted
  (companies' own FCF definitions may differ).
- Comparison view: band width is the current quarter; the dark strip is the increase since the previous quarter.
  A requested comparison works the same way: band width is the first period, the strip the increase over the second.
  With *Show decreases*, every band and node keeps room for its larger value of the two quarters, and the part the
  current quarter does not fill is hatched: that is the decrease.
  `scale = (parent_now − parent_prior) × child_prior / parent_prior`, `mix = parent_now × (share_now − share_prior)`.

## Limits

- Banks, insurers, REITs and funds whose statements do not run from revenue to net income may be skipped or shown
  coarsely; custom XBRL tags fall into "Other operating costs".
- Notes appear only when the MD&A has a heading or sentence that names the line; otherwise the panel says so.
- Amended filings (10-Q/A, 10-K/A) are ignored.
- Data is as filed with the SEC; this is not investment advice.
