# Upgrade the existing Disclosure Lab without resetting collection progress

Target your independent **eurikamonica/Filing-Flows-Disclosure-Lab** repository. Leave the original **eurikamonica/filing-flows** untouched.

1. Back up the existing repository and temporarily disable its collection workflow while uploading multiple batches.
2. Replace these code folders/files from the v4 ZIP at the repository root:
   - `app/`
   - `tests/`
   - `automation/`
   - `requirements.txt`
   - optional README/documentation and startup files
3. Open the repository's **docs** folder. Upload/replace these five files there:
   - `index.html`
   - `styles.css`
   - `app.js`
   - `extensions.js`
   - `dashboard.js`
4. **Keep the existing `docs/data/` folder.** Do not replace its snapshots, catalogs, caches, shards or queue state with the starter data in this ZIP. Also keep your own `config/reviewed-disclosures.csv`, `config/imports.json` and imported PDFs.
5. Update `config/settings.json`. Merge your existing preferences with these v4 additions (do not delete existing `since`, dataset IDs, contact, CIK seeds or other fields):

```json
{
  "cot": {
    "discover_all": true,
    "batch_size": 10,
    "refresh_hours": 168,
    "discovery_hours": 24
  },
  "banks": {
    "discover_all": true,
    "active_only": true,
    "batch_size": 20,
    "refresh_hours": 168,
    "discovery_hours": 24
  },
  "npx": {
    "discover_all": true,
    "discovery_since": "2025-01-01",
    "batch_size": 4,
    "document_batch_size": 12,
    "refresh_hours": 168
  }
}
```

This is a **merge fragment**, not a replacement for the whole settings file. If you never customized settings, replacing it with the complete v4 `config/settings.json` is simpler. Keep the supplied SEC name/email.

6. Edit `.github/workflows/update-and-deploy.yml` through GitHub's web editor. Replace its entire contents with the visible `automation/update-and-deploy.yml` in v4. Do not add a second deployment workflow.
7. Re-enable the workflow. Under Actions, run **module = markets**. It converts retained COT/bank rows into entity shards, starts broad discovery and advances N-PX queues. Existing 13F and House data remain.
8. After success, run **module = all** for the next full batch. Hard-refresh the site with Ctrl+F5.
9. Open Explore directory and select COT markets, FDIC banks or N-PX filers. Health shows processing counts. Check an available bank/COT chart and a multi-chunk N-PX report.

Repository URL and GitHub Pages URL stay the same. There is no deployment performed by the assistant.

If starting a new repository instead, upload the complete package including all bundled `docs/data/`; use `DEPLOY-GITHUB.md`. The package contains more than 100 files, so use GitHub Desktop or browser upload batches. It contains no dot-prefixed paths; the actual workflow path is created/edited through GitHub's editor.
