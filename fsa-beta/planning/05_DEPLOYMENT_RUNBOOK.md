# 05 — Isolated deployment runbook

Created by ChatGPT (OpenAI). **Instructions for future execution; no deployment was performed.**

## Recommended architecture

Use the laptop for local model inference/training and research calculations. Publish reviewed static HTML/CSS/JS and sanitized JSON to a **separate research-site repository**. Keep production Filing Flows hosting, DNS, workflows and databases unchanged.

GitHub Pages serves static files [S1]. It does not run the Python FSA server or a GPU inference process. A project site can use a branch root or `/docs` publishing source [S2]. Therefore, do not point the existing production repository's Pages setting at the beta branch to obtain a second site: that would change its publication source. A separate repository is the recommended isolation boundary.

| Mode | Use | Additional infrastructure | Limits |
| --- | --- | --- | --- |
| Local file / loopback | Prototype and private review | none beyond a browser; optional Python | Not accessible to other devices by default |
| Separate static site | Public demo, reviewed research snapshots | Separate repository and hosting configuration | No server secrets, live Python or GPU |
| Batch snapshots | Updated financial/macro views | Separate scheduled collector | Freshness depends on successful jobs, not a real-time guarantee |
| Static site + API | User-specific queries or live explanations | Separate HTTPS backend, authentication, budget controls | Ongoing operations/cost; optional later phase |

## A. Preview existing labs on Windows

Download the beta branch ZIP from:

https://github.com/eurikamonica/filing-flows/archive/refs/heads/beta/fsa-chatgpt.zip

Extract it into a new folder. In VS Code, open that extracted folder. Do not overwrite an existing local checkout that contains your QLoRA changes.

For the existing Story Desk, open a terminal in its directory:

```powershell
cd "C:\path\to\extracted-repository\fsa-beta\social-lab"
py -m http.server 8767 --bind 127.0.0.1
```

Open http://127.0.0.1:8767. No virtual-environment activation is required. If the Python launcher is unavailable, use the absolute path to an installed python.exe. Stop with Ctrl+C.

For the visual lab, use its directory and port 8766. Directly opening either index.html also works for basic use; browser clipboard/storage restrictions may differ. Complete each lab's existing manual acceptance checklist before publishing it. Proposed new modules in this planning package do not yet have runnable entry points.

## B. Prepare a clean publication folder

The example below copies only the current two static labs into a new sibling directory. Change the first path to your extracted repository. It deliberately refuses to reuse an existing destination. It does not copy models, Python services, training data, credentials or the old production site.

```powershell
$sourceRepo = "C:\path\to\extracted-repository"
$publishDir = Join-Path (Split-Path $sourceRepo -Parent) "filing-flows-research-site"
if (Test-Path $publishDir) { throw "Choose a new publication directory." }
New-Item -ItemType Directory -Path $publishDir | Out-Null
$publishDocs = Join-Path $publishDir "docs"
New-Item -ItemType Directory -Path $publishDocs | Out-Null

$labFiles = @{
    "visual-lab" = @("index.html", "app.js", "math.js", "style.css")
    "social-lab" = @("index.html", "app.js", "engine.js", "style.css")
}
foreach ($labName in $labFiles.Keys) {
    $targetLab = Join-Path $publishDocs $labName
    New-Item -ItemType Directory -Path $targetLab | Out-Null
    foreach ($fileName in $labFiles[$labName]) {
        $sourceFile = Join-Path (Join-Path $sourceRepo "fsa-beta\$labName") $fileName
        if (-not (Test-Path $sourceFile)) { throw "Missing source: $sourceFile" }
        Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $targetLab $fileName)
    }
}
@'
<!doctype html>
<!-- Created by ChatGPT (OpenAI). Independent research preview. -->
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Filing Flows Research Preview</title></head>
<body><h1>Independent Research Preview</h1>
<p>Experimental features. Fictional examples are labeled. Not investment advice.</p>
<ul><li><a href="./visual-lab/">Cash &amp; Cookie Visual Lab</a></li>
<li><a href="./social-lab/">Story Desk</a></li></ul>
<p>Created by ChatGPT (OpenAI).</p></body></html>
'@ | Set-Content -Encoding utf8 (Join-Path $publishDocs "index.html")
New-Item -ItemType File -Path (Join-Path $publishDocs ".nojekyll") | Out-Null
Set-Location $publishDir
py -m http.server 8768 --bind 127.0.0.1 --directory docs
```

Open http://127.0.0.1:8768 and inspect both links. Keep asset references relative so they work under a GitHub project-site path. The simple landing-page snippet is a runbook example, not a polished application implementation. Stop the server before continuing in the same terminal.

## C. Publish to a new repository

1. Create a new, empty GitHub repository under your account, for example `filing-flows-research`. Verify the chosen name is available. Do not enable imported production workflows.
2. Public static demo content should contain only information you intend to publish. Do not infer that a private repository automatically makes its Pages site private; verify hosting access controls if private access is required.
3. From the clean publication directory, review files and initialize the independent repository:

```powershell
Set-Location $publishDir
Get-ChildItem -Recurse -File
 git init
 git add docs
 git diff --cached --stat
 git commit -m "Add independent research preview by ChatGPT (OpenAI)"
 git branch -M main
 git remote add origin https://github.com/eurikamonica/filing-flows-research.git
 git remote -v
```

4. Confirm the remote is the **new** repository, then publish:

```powershell
git push -u origin main
```

Authentication uses your Git installation/account setup; do not paste a token into a committed file. If a repository already exists at that name, choose a new empty repository and update the URL; do not force-push.

5. In the **new repository only**, open Settings → Pages. Choose Deploy from a branch, then `main` and `/docs`, and save [S2]. If permissions or account eligibility block this setting, use another appropriate static host; do not change production settings as a workaround.
6. Use the URL shown by GitHub. The expected pattern for that example is `https://eurikamonica.github.io/filing-flows-research/`; it is a proposed address, not a verified live site.
7. Test the deployed nested pages, relative assets, PNG download, journal persistence, reduced motion and video export. Review mobile rendering. Record the release commit and observed results.
8. Keep the default research URL first. A future beta subdomain requires its own DNS/hosting configuration; do not replace the production apex domain, production CNAME or existing Pages source.

GitHub documents usage and size limits [S3]. Do not publish model weights, large training datasets or a growing video archive through this static site. Check current plan eligibility and limits before launch; no unlimited/free-hosting guarantee is made.

## D. Add new research modules after implementation

Release each module independently:

1. Build and test in its new beta directory.
2. Create a release manifest with source commit, schema versions, snapshot IDs, source as-of timestamps, tests and unresolved limitations.
3. Copy only allowlisted public assets and reviewed data into a new module subdirectory in the research publication repository.
4. Add the link to the research site's landing page, not the production navigation.
5. Commit and inspect the publication diff. Publish to the separate site only after acceptance.

Do not copy the entire `fsa-beta/` directory to a public web root. Do not include `.env`, adapters, model weights, private journals, full local logs or unreviewed uploads.

## E. Scheduled data refresh: later implementation

Add a collector workflow only to an isolated research data/deployment repository after collector code exists. Initially run it manually. Sequence: fetch → normalize → validate → calculate → package → verify hashes → publish. Source adapters use source-specific access rules and secret storage. Scheduling is best-effort; show last attempt, last success and data-as-of separately.

Write each snapshot to an immutable ID. Update the public manifest only after all referenced files validate. Publish old and new snapshot references together during transition so cached pages cannot request removed files. On partial failure leave the previous manifest active and expose stale status. Keep retention bounded.

Initial cadence should follow the actual release frequency: financial filings on a reasonable polling schedule; macro series around their release schedule; prices according to the data provider's permitted service. Do not assume a universal 15-minute refresh is meaningful or licensed.

## F. Optional live model/backend

Do not expose the laptop's training server publicly. Local QLoRA experiments and precomputed explanations can feed the static export path after review. If live inference is later justified, deploy an independent backend with narrow inputs, authentication, exact-origin CORS, request/body limits, timeouts, concurrency caps, caching, explicit cost limits and audited logs without secrets.

Backend returns sourced narrative separately from deterministic numeric results. Failure returns an unavailable explanation, not invented figures. A specific provider, GPU size and cost require measured latency/concurrency and a fresh pricing review. This plan does not select or provision a hosted GPU.

## Rollback and operations

For a bad research release, revert the specific publication commit in the **research repository**, inspect the reversal and push a new commit. Restore its earlier manifest and keep referenced snapshot files available. Do not force-reset production. Confirm the research site serves the intended version after deployment.

A browser-only journal is local to that origin/device; moving from local files to a hosted site does not transfer it. Export JSON before moving, then restore in the new origin. No server backup or user authentication is provided by the current labs.

## Sources

Checked October 16, 2026 UTC.

- [S1: What is GitHub Pages?](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [S2: Configure a publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [S3: GitHub Pages limits and usage](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
