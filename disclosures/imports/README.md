# PDF imports

Place public disclosure PDFs obtained through the appropriate official access process here, then add entries to `config/imports.json`. Imports may cover Senate, state or local disclosures. No Senate or state/local scraper is included.

Example manifest (replace all example values with the actual report):

```json
[
  {
    "path": "imports/report.pdf",
    "report_id": "senate-unique-report-id",
    "person": "Exact filer name from report",
    "jurisdiction": "US Senate",
    "report_type": "Annual",
    "filed_date": "2026-05-15",
    "source_url": "https://efdsearch.senate.gov/search/home/",
    "force_ocr": false
  }
]
```

Use a report-specific official URL when available, not a guessed document address. A portal URL is only a fallback and does not pinpoint a report. `filed_date` is the actual filing date, not today's date. Keep report IDs unique.

The collector extracts text first, then uses OCR for pages with fewer than 60 non-whitespace text characters. Set `force_ocr: true` for a poor or misleading text layer. Run `python app/collect.py --only congress` and review candidates.

Do not add passwords, cookies, session tokens or private documents to a public repository. Only `docs/` is deployed to Pages, but files committed elsewhere remain visible in a public repository.
